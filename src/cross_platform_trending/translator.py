from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4.1-mini"
USER_AGENT = "github-cross-platform-trending/0.3"
TRANSLATION_BATCH_SIZE = 25


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _fallback_description(item: dict[str, Any]) -> str:
    language = item.get("language") or "多种语言"
    return (
        "一款支持 macOS 和 Windows 的开源跨平台软件，"
        f"主要使用 {language} 开发。"
    )


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
    return max(
        segments,
        key=lambda segment: len(re.findall(r"[\u4e00-\u9fff]", segment)),
    )


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

    def _load_cache(self) -> dict[str, dict[str, str]]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return payload.get("translations", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self, translations: dict[str, dict[str, str]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": MODEL,
            "translations": dict(sorted(translations.items())),
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
                        "60 个汉字。"
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
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(
                f"GitHub Models 请求失败 ({error.code}): {detail}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"GitHub Models 网络请求失败：{error}") from error

        try:
            content = result["choices"][0]["message"]["content"]
            translated = json.loads(content)["translations"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("GitHub Models 返回了无法解析的翻译结果") from error
        return {
            str(item["name"]): str(item["description_zh"]).strip()
            for item in translated
        }

    def enrich(self, software: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        cache = self._load_cache()
        cache_changed = False
        pending: list[dict[str, str]] = []

        for item in software:
            description = str(item["description"]).strip()
            item["description_en"] = description
            if _contains_chinese(description):
                item["description_zh"] = _chinese_segment(description)
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
                pending.append(
                    {"name": item["name"], "description_en": description}
                )

        translated: dict[str, str] = {}
        if pending and self.token:
            for offset in range(0, len(pending), TRANSLATION_BATCH_SIZE):
                batch = pending[offset : offset + TRANSLATION_BATCH_SIZE]
                try:
                    translated.update(self._request_translations(batch))
                except RuntimeError as error:
                    start = offset + 1
                    end = offset + len(batch)
                    warnings.append(
                        f"第 {start}-{end} 条中文简介生成失败，已使用中文兜底：{error}"
                    )
        elif pending:
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
                cache[item["name"]] = {
                    "source": item["description_en"],
                    "zh": candidate,
                }
            else:
                item["description_zh"] = _fallback_description(item)

        if translated or cache_changed:
            self._save_cache(cache)
        return warnings
