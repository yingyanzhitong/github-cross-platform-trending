from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4.1-mini"
USER_AGENT = "github-cross-platform-trending/0.5"
TRANSLATION_BATCH_SIZE = 25
ANALYSIS_BATCH_SIZE = 10
MAX_MODEL_RETRIES = 2
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


def _fallback_description(item: dict[str, Any]) -> str:
    language = item.get("language") or "多种语言"
    return (
        "一款支持 macOS 和 Windows 的开源跨平台软件，"
        f"主要使用 {language} 开发。"
    )


def _fallback_analysis(item: dict[str, Any]) -> dict[str, str]:
    topics = "、".join(str(topic) for topic in item.get("topics", [])[:5])
    topic_summary = topics or "跨平台桌面软件"
    language = item.get("language") or "多种语言"
    return {
        "positioning": item["description_zh"],
        "implementation": (
            f"仓库主要使用 {language} 开发，公开主题涉及 {topic_summary}；"
            "具体架构与技术路径应以项目文档为准。"
        ),
        "problems_solved": (
            "为 macOS 与 Windows 用户提供同一套开源软件能力；"
            "更具体的目标问题应以项目说明为准。"
        ),
        "capabilities": (
            f"公开仓库主题主要涉及 {topic_summary}；"
            "具体功能范围与配置方式应以项目文档为准。"
        ),
        "use_cases": (
            "适合需要在 macOS 与 Windows 上使用此类开源工具，"
            "并愿意自行核对配置和兼容性的用户。"
        ),
        "considerations": (
            "榜单仅确认 Latest Release 提供双平台安装包；"
            "安装前仍应检查许可证、发布说明与安装包签名。"
        ),
    }


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


def _clean_analysis(analysis: dict[str, Any]) -> dict[str, str]:
    return {
        field: re.sub(r"[*_`#]+", "", str(analysis.get(field, ""))).strip()
        for field in ANALYSIS_FIELDS
    }


def _valid_analysis(analysis: Any) -> bool:
    if not isinstance(analysis, dict):
        return False
    cleaned = _clean_analysis(analysis)
    return all(cleaned[field] and _contains_chinese(cleaned[field]) for field in ANALYSIS_FIELDS)


class DescriptionTranslator:
    def __init__(
        self,
        *,
        token: str | None,
        cache_path: Path,
        timeout: int = 60,
    ):
        self.token = token
        self.cache_path = cache_path
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
            "model": MODEL,
            "translations": dict(sorted(translations.items())),
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _request_model(self, body: dict[str, Any], label: str) -> dict[str, Any]:
        for attempt in range(MAX_MODEL_RETRIES + 1):
            request = Request(
                MODELS_URL,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                    "X-GitHub-Api-Version": "2026-03-10",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read())
                break
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:300]
                retry_after = error.headers.get("Retry-After")
                remaining = error.headers.get("X-RateLimit-Remaining")
                reset_at = error.headers.get("X-RateLimit-Reset")
                is_rate_limited = error.code == 429 or bool(retry_after)
                if is_rate_limited and attempt < MAX_MODEL_RETRIES:
                    if retry_after and retry_after.isdigit():
                        delay = int(retry_after)
                    elif remaining == "0" and reset_at and reset_at.isdigit():
                        delay = max(1, int(reset_at) - int(time.time()) + 1)
                    else:
                        delay = 60 * (2**attempt)
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"GitHub Models {label}请求失败 ({error.code}): {detail}"
                ) from error
            except (URLError, TimeoutError) as error:
                raise RuntimeError(
                    f"GitHub Models {label}网络请求失败：{error}"
                ) from error

        try:
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"GitHub Models 返回了无法解析的{label}结果") from error

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
            raise RuntimeError("GitHub Models 返回了无法解析的翻译结果") from error
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
    ) -> dict[str, dict[str, str]]:
        properties = {
            field: {"type": "string"}
            for field in ANALYSIS_FIELDS
        }
        schema = {
            "type": "object",
            "properties": {
                "analyses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            **properties,
                        },
                        "required": ["name", *ANALYSIS_FIELDS],
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
                        "README 摘要、Topics、开发语言和主页，生成简体中文结构化分析。"
                        "positioning 具体说明这个项目是什么、为谁服务，不超过 90 个汉字；"
                        "implementation 说明它如何实现目标，优先提炼输入中明确出现的"
                        "架构、技术栈、数据流、部署方式或关键机制，不超过 160 个汉字；"
                        "problems_solved 说明它替用户解决的具体痛点、替代的旧流程或"
                        "降低的成本，不超过 120 个汉字；"
                        "capabilities 用 2 至 4 个分号分隔的具体核心能力，不超过 "
                        "160 个汉字；use_cases 说明适合的人群和工作流，不超过 100 "
                        "个汉字；considerations 说明部署依赖、账号或服务要求、成熟度、"
                        "许可证等需要注意的事实，不超过 100 个汉字。只使用输入中能"
                        "支持的事实，禁止猜测；资料不足时明确建议核对项目文档。"
                        "保留必要专有名词，不使用 Markdown；name 必须原样复制输入"
                        "中的完整 owner/repository，不得缩写。"
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
            raise RuntimeError("GitHub Models 返回了无法解析的详情分析结果") from error
        parsed: dict[str, dict[str, str]] = {}
        requested_names = {str(item["name"]) for item in items}
        for index, analysis in enumerate(analyses):
            if not _valid_analysis(analysis):
                continue
            name = str(analysis.get("name", ""))
            if name not in requested_names and index < len(items):
                name = str(items[index]["name"])
            if name in requested_names:
                parsed[name] = _clean_analysis(analysis)
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
        if pending_translations and self.token:
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
                    warnings.append(
                        f"第 {start}-{end} 条中文简介生成失败，已使用中文兜底：{error}"
                    )
        elif pending_translations:
            warnings.append("未提供 GitHub Token，中文简介已使用通用兜底")

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
                item["description_zh"] = _fallback_description(item)

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
                cleaned = _clean_analysis(cached_analysis)
                item["analysis_zh"] = cleaned
                if cleaned != cached_analysis:
                    cached["analysis_zh"] = cleaned
                    cache_changed = True
            else:
                pending_analyses.append(analysis_source)

        generated_analyses: dict[str, dict[str, str]] = {}
        if pending_analyses and self.token:
            for offset in range(0, len(pending_analyses), ANALYSIS_BATCH_SIZE):
                batch = pending_analyses[offset : offset + ANALYSIS_BATCH_SIZE]
                try:
                    generated_analyses.update(self._request_analyses(batch))
                except RuntimeError as error:
                    start = offset + 1
                    end = offset + len(batch)
                    warnings.append(
                        f"第 {start}-{end} 条详情分析生成失败，已使用中文兜底：{error}"
                    )
        elif pending_analyses:
            warnings.append("未提供 GitHub Token，项目详情分析已使用通用兜底")

        for item in software:
            if not item.get("analysis_zh"):
                candidate = generated_analyses.get(item["name"])
                if _valid_analysis(candidate):
                    cleaned = _clean_analysis(candidate)
                    item["analysis_zh"] = cleaned
                    cache.setdefault(item["name"], {}).update(
                        {
                            "analysis_source": analysis_fingerprints[item["name"]],
                            "analysis_zh": cleaned,
                        }
                    )
                    cache_changed = True
                else:
                    item["analysis_zh"] = _fallback_analysis(item)
            item.pop("_readme_excerpt", None)

        if cache_changed:
            self._save_cache(cache)
        return warnings
