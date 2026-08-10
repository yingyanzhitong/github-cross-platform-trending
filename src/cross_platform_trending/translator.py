from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


MODEL = "gpt-5.6-sol"
TRANSLATION_BATCH_SIZE = 25
ANALYSIS_BATCH_SIZE = 10
MAX_MODEL_RETRIES = 1
ANALYSIS_MIN_LENGTH = 200
ANALYSIS_MAX_LENGTH = 1000
ANALYSIS_FIELDS = (
    "positioning",
    "implementation",
    "problems_solved",
    "capabilities",
    "use_cases",
    "considerations",
)


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _is_mostly_chinese(text: str) -> bool:
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return chinese_count >= 4 and chinese_count >= latin_count


def _clean_translation(name: str, text: str) -> str:
    cleaned = text.strip()
    repository = name.rsplit("/", 1)[-1]
    for prefix in (name, repository):
        if cleaned.lower().startswith(prefix.lower()):
            remainder = cleaned[len(prefix) :].lstrip("：:：-— ")
            if remainder:
                return remainder
    return cleaned


def _chinese_segment(text: str) -> str:
    segments = [segment.strip() for segment in re.split(r"[|｜]", text)]
    segments.extend(
        segment.strip()
        for segment in re.findall(r"[（(]([^（）()]+)[）)]", text)
        if _contains_chinese(segment)
    )
    return max(
        segments,
        key=lambda segment: (
            len(re.findall(r"[\u4e00-\u9fff]", segment)),
            -len(re.findall(r"[A-Za-z]", segment)),
        ),
    )


def _clean_analysis_text(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[*_`#]+", "", str(value or "")),
    ).strip()


def normalize_analysis(analysis: Any, *, description: str = "") -> str:
    """将新旧分析格式统一为不含 Markdown 的单段中文说明。"""
    if not isinstance(analysis, dict):
        cleaned = _clean_analysis_text(analysis)
        cleaned = re.sub(r"项目通过使用", "它使用", cleaned)
        cleaned = re.sub(r"项目通过(?=基于|借助|依靠|由)", "它", cleaned)
        cleaned = re.sub(r"项目通过(?=\s|[A-Za-z0-9])", "它通过", cleaned)
        cleaned = re.sub(
            r"它主要解决(?=减少|降低|避免|缓解|替代|统一|集中)",
            "它可以",
            cleaned,
        )
        cleaned = re.sub(r"核心能力包括(?!：)", "核心能力包括：", cleaned)
        return cleaned

    values = {
        field: _clean_analysis_text(analysis.get(field)).strip("。；，, ")
        for field in ANALYSIS_FIELDS
    }
    lead = values["positioning"] or _clean_analysis_text(description).strip("。；，, ")
    parts: list[str] = []
    if lead:
        parts.append(f"{lead}。")
    if values["implementation"]:
        implementation = values["implementation"]
        if implementation.startswith(("通过", "使用", "基于", "借助", "依靠", "由")):
            parts.append(f"它{implementation}。")
        else:
            parts.append(f"实现上，{implementation}。")
    if values["problems_solved"]:
        problems = values["problems_solved"]
        if problems.startswith("解决"):
            parts.append(f"它主要解决{problems.removeprefix('解决')}。")
        elif problems.startswith(("减少", "降低", "避免", "缓解", "替代", "统一", "集中")):
            parts.append(f"它可以{problems}。")
        else:
            parts.append(f"它旨在{problems}。")
    if values["capabilities"]:
        parts.append(f"核心能力包括：{values['capabilities']}。")
    if values["use_cases"]:
        parts.append(f"{values['use_cases']}。")
    if values["considerations"]:
        parts.append(f"使用时需要注意：{values['considerations']}。")
    return "".join(parts)


def _clean_analysis(analysis: Any, *, description: str = "") -> str:
    return normalize_analysis(analysis, description=description)


def _valid_analysis(analysis: Any) -> bool:
    cleaned = _clean_analysis(analysis)
    return (
        ANALYSIS_MIN_LENGTH <= len(cleaned) <= ANALYSIS_MAX_LENGTH
        and _contains_chinese(cleaned)
        and "\n" not in cleaned
        and not re.search(r"(?:^|\s)[-*+]\s", cleaned)
    )


class DescriptionTranslator:
    def __init__(
        self,
        *,
        cache_path: Path,
        model_command: str | None = "codex",
        model: str | None = None,
        timeout: int = 180,
    ):
        self.cache_path = cache_path
        self.model_command = model_command
        self.model = model or os.getenv("CROSS_PLATFORM_TRENDING_MODEL", MODEL)
        self.timeout = timeout

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return payload.get("translations", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self, translations: dict[str, dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": f"codex-cli/{self.model}",
            "translations": dict(sorted(translations.items())),
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _request_model(self, body: dict[str, Any], label: str) -> dict[str, Any]:
        if not self.model_command:
            raise RuntimeError("未配置 Codex CLI，无法生成中文内容")

        messages = body.get("messages", [])
        prompt = "\n\n".join(
            f"{message.get('role', 'user')}：\n{message.get('content', '')}"
            for message in messages
        )
        prompt += "\n\n请只返回符合给定 JSON Schema 的 JSON，不要解释或调用工具。"
        try:
            schema = body["response_format"]["json_schema"]["schema"]
        except (KeyError, TypeError) as error:
            raise RuntimeError(f"{label}请求缺少 JSON Schema") from error

        for attempt in range(MAX_MODEL_RETRIES + 1):
            with tempfile.TemporaryDirectory(prefix="cross-platform-trending-") as directory:
                schema_path = Path(directory) / "output-schema.json"
                schema_path.write_text(
                    json.dumps(schema, ensure_ascii=False),
                    encoding="utf-8",
                )
                command = [
                    self.model_command,
                    "exec",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--ignore-rules",
                    "--ignore-user-config",
                    "--color",
                    "never",
                    "--sandbox",
                    "read-only",
                    "--output-schema",
                    str(schema_path),
                    "--model",
                    self.model,
                    prompt,
                ]
                try:
                    result = subprocess.run(
                        command,
                        cwd=directory,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        check=False,
                    )
                except FileNotFoundError as error:
                    raise RuntimeError(
                        f"未找到 Codex CLI 命令：{self.model_command}"
                    ) from error
                except subprocess.TimeoutExpired as error:
                    if attempt < MAX_MODEL_RETRIES:
                        time.sleep(2**attempt)
                        continue
                    raise RuntimeError(
                        f"Codex CLI {label}请求超过 {self.timeout} 秒"
                    ) from error

            if result.returncode != 0:
                if attempt < MAX_MODEL_RETRIES:
                    time.sleep(2**attempt)
                    continue
                detail = result.stderr.strip().splitlines()
                summary = detail[-1][:300] if detail else "未知错误"
                raise RuntimeError(
                    f"Codex CLI {label}请求失败 ({result.returncode})：{summary}"
                )

            output = result.stdout.strip()
            candidates = [output, *reversed(output.splitlines())]
            for candidate in candidates:
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
            if attempt < MAX_MODEL_RETRIES:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Codex CLI 返回了无法解析的{label}结果")

        raise RuntimeError(f"Codex CLI {label}请求失败")

    def _request_translations(
        self,
        items: list[dict[str, str]],
    ) -> dict[str, str]:
        schema = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description_zh": {"type": "string"},
                        },
                        "required": ["name", "description_zh"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }
        body = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是开源软件编辑。把每条英文项目简介改写成准确、自然、"
                        "简洁的一句简体中文简介。保留产品名和必要专有名词，不添加"
                        "原文没有的功能，不重复仓库名，不使用 Markdown，不超过 "
                        "60 个汉字；name 必须原样复制输入中的完整 owner/repository。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(items, ensure_ascii=False),
                },
            ],
            "temperature": 0,
            "max_tokens": 2500,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "software_translations",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        try:
            translated = self._request_model(body, "翻译")["translations"]
        except (KeyError, TypeError) as error:
            raise RuntimeError("Codex CLI 返回了无法解析的翻译结果") from error
        parsed: dict[str, str] = {}
        requested_names = {str(item["name"]) for item in items}
        for index, translation in enumerate(translated):
            name = str(translation.get("name", ""))
            if name not in requested_names and index < len(items):
                name = str(items[index]["name"])
            if name in requested_names:
                parsed[name] = str(translation["description_zh"]).strip()
        return parsed

    def _request_analyses(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, str]:
        schema = {
            "type": "object",
            "properties": {
                "analyses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "analysis_zh": {
                                "type": "string",
                                "minLength": ANALYSIS_MIN_LENGTH,
                                "maxLength": ANALYSIS_MAX_LENGTH,
                            },
                        },
                        "required": ["name", "analysis_zh"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["analyses"],
            "additionalProperties": False,
        }
        body = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的开源软件分析编辑。根据每个仓库提供的简介、"
                        "README 摘要、Topics、开发语言、主页、许可证和发布信息，为每个"
                        "仓库生成 200 至 1000 字的简体中文分析。analysis_zh 必须是一个"
                        "连贯自然段，具体说明仓库的作用、服务对象、实现机制、解决的"
                        "问题、主要能力、适用场景和必要注意事项，但不要使用标题、列表、"
                        "分点、Markdown 或换行。只使用输入能够支持的事实，禁止猜测；"
                        "资料不足时明确建议核对项目文档。保留必要专有名词；name 必须"
                        "原样复制输入中的完整 owner/repository，不得缩写。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(items, ensure_ascii=False),
                },
            ],
            "temperature": 0,
            "max_tokens": 8000,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "software_analyses",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        try:
            analyses = self._request_model(body, "详情分析")["analyses"]
        except (KeyError, TypeError) as error:
            raise RuntimeError("Codex CLI 返回了无法解析的详情分析结果") from error
        parsed: dict[str, str] = {}
        requested_names = {str(item["name"]) for item in items}
        for index, analysis in enumerate(analyses):
            analysis_text = _clean_analysis(analysis.get("analysis_zh"))
            if not _valid_analysis(analysis_text):
                continue
            name = str(analysis.get("name", ""))
            if name not in requested_names and index < len(items):
                name = str(items[index]["name"])
            if name in requested_names:
                parsed[name] = analysis_text
        return parsed

    def enrich(self, software: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        cache = self._load_cache()
        cache_changed = False
        pending_translations: list[dict[str, str]] = []

        for item in software:
            item.pop("description_zh", None)
            description = str(item["description"]).strip()
            item["description_en"] = description
            if _contains_chinese(description):
                chinese_segment = _chinese_segment(description)
                if _is_mostly_chinese(chinese_segment):
                    item["description_zh"] = chinese_segment
                    continue
            cached = cache.get(item["name"], {})
            if cached.get("source") == description and _contains_chinese(
                cached.get("zh", "")
            ):
                cleaned = _clean_translation(item["name"], cached["zh"])
                item["description_zh"] = cleaned
                if cleaned != cached["zh"]:
                    cached["zh"] = cleaned
                    cache_changed = True
            else:
                pending_translations.append(
                    {"name": item["name"], "description_en": description}
                )

        translated: dict[str, str] = {}
        if pending_translations and self.model_command:
            for offset in range(
                0,
                len(pending_translations),
                TRANSLATION_BATCH_SIZE,
            ):
                batch = pending_translations[
                    offset : offset + TRANSLATION_BATCH_SIZE
                ]
                try:
                    translated.update(self._request_translations(batch))
                except RuntimeError as error:
                    start = offset + 1
                    end = offset + len(batch)
                    raise RuntimeError(
                        f"第 {start}-{end} 条中文简介生成失败：{error}"
                    ) from error
        elif pending_translations:
            raise RuntimeError("未配置 Codex CLI，无法生成缺失的中文简介")

        for item in software:
            if item.get("description_zh"):
                continue
            candidate = _clean_translation(
                item["name"],
                translated.get(item["name"], ""),
            )
            if candidate and _contains_chinese(candidate):
                item["description_zh"] = candidate
                cache.setdefault(item["name"], {}).update(
                    {
                        "source": item["description_en"],
                        "zh": candidate,
                    }
                )
                cache_changed = True
            else:
                raise RuntimeError(f"{item['name']} 的中文简介生成结果缺失或无效")

        pending_analyses: list[dict[str, Any]] = []
        analysis_fingerprints: dict[str, str] = {}
        for item in software:
            item.pop("analysis_zh", None)
            analysis_source = {
                "name": item["name"],
                "description_en": item["description_en"],
                "description_zh": item["description_zh"],
                "language": item.get("language") or "未知",
                "topics": item.get("topics", [])[:12],
                "homepage": item.get("homepage"),
                "license": item.get("license"),
                "latest_release": item.get("latest_release"),
                "readme_excerpt": item.get("_readme_excerpt", ""),
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    analysis_source,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            analysis_fingerprints[item["name"]] = fingerprint
            cached = cache.get(item["name"], {})
            cached_analysis = cached.get("analysis_zh")
            if (
                cached.get("analysis_source") == fingerprint
                and _valid_analysis(cached_analysis)
            ):
                cleaned = _clean_analysis(
                    cached_analysis,
                    description=item["description_zh"],
                )
                item["analysis_zh"] = cleaned
                if cleaned != cached_analysis:
                    cached["analysis_zh"] = cleaned
                    cache_changed = True
            else:
                pending_analyses.append(analysis_source)

        generated_analyses: dict[str, str] = {}
        if pending_analyses and self.model_command:
            for offset in range(0, len(pending_analyses), ANALYSIS_BATCH_SIZE):
                batch = pending_analyses[offset : offset + ANALYSIS_BATCH_SIZE]
                try:
                    generated_analyses.update(self._request_analyses(batch))
                except RuntimeError as error:
                    start = offset + 1
                    end = offset + len(batch)
                    raise RuntimeError(
                        f"第 {start}-{end} 条详情分析生成失败：{error}"
                    ) from error
        elif pending_analyses:
            raise RuntimeError("未配置 Codex CLI，无法生成缺失的项目详情分析")

        for item in software:
            if not item.get("analysis_zh"):
                candidate = generated_analyses.get(item["name"])
                if _valid_analysis(candidate):
                    cleaned = _clean_analysis(
                        candidate,
                        description=item["description_zh"],
                    )
                    item["analysis_zh"] = cleaned
                    cache.setdefault(item["name"], {}).update(
                        {
                            "analysis_source": analysis_fingerprints[item["name"]],
                            "analysis_zh": cleaned,
                        }
                    )
                    cache_changed = True
                else:
                    raise RuntimeError(
                        f"{item['name']} 的项目详情分析生成结果缺失或无效"
                    )
            item.pop("_readme_excerpt", None)

        if cache_changed:
            self._save_cache(cache)
        return warnings
