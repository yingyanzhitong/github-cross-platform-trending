from __future__ import annotations

import tempfile
import unittest
from json import dumps
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

from cross_platform_trending.translator import DescriptionTranslator


ANALYSIS = (
    "这是一款面向桌面用户的跨平台下载管理器，适合需要集中处理大量下载任务的个人"
    "用户和开发团队。项目使用 Rust 构建桌面客户端，通过任务队列统一调度下载、记录"
    "任务状态并处理失败重试，从而减少在多个工具之间切换、手工跟踪进度和重复启动任务"
    "的成本。它的核心能力包括：统一管理下载任务、展示执行进度、支持失败重试以及提供"
    "macOS 和 Windows 客户端，可用于日常文件获取、批量资源整理和需要持续观察任务"
    "状态的工作流。安装和使用前仍应核对项目发布说明、系统要求、安装包来源与签名，"
    "并根据仓库文档确认不同平台上的功能差异。"
)


def _software() -> list[dict[str, Any]]:
    return [
        {
            "name": "owner/example",
            "description": "A full-featured download manager.",
            "language": "Rust",
            "topics": ["download-manager", "desktop-app"],
            "_readme_excerpt": "Manage downloads and retry failed tasks.",
        }
    ]


class StubTranslator(DescriptionTranslator):
    def _request_translations(
        self,
        items: list[dict[str, str]],
    ) -> dict[str, str]:
        return {"owner/example": "owner/example：一款功能齐全的下载管理器。"}

    def _request_analyses(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, str]:
        return {"owner/example": ANALYSIS}


class BatchTranslator(DescriptionTranslator):
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.batch_sizes: list[int] = []
        self.analysis_batch_sizes: list[int] = []

    def _request_translations(
        self,
        items: list[dict[str, str]],
    ) -> dict[str, str]:
        self.batch_sizes.append(len(items))
        return {
            item["name"]: "一款用于测试分批翻译的跨平台软件。"
            for item in items
        }

    def _request_analyses(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, str]:
        self.analysis_batch_sizes.append(len(items))
        return {item["name"]: ANALYSIS for item in items}


class ShortNameResponseTranslator(DescriptionTranslator):
    def _request_model(
        self,
        body: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        if label == "翻译":
            return {
                "translations": [
                    {
                        "name": "example",
                        "description_zh": "跨平台桌面下载管理器。",
                    }
                ]
            }
        return {
            "analyses": [
                {
                    "name": "example",
                    "analysis_zh": ANALYSIS,
                }
            ]
        }


class DescriptionTranslatorTests(unittest.TestCase):
    def test_translates_and_caches_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "translations.json"
            software = _software()
            translator = StubTranslator(model_command="stub", cache_path=cache_path)

            warnings = translator.enrich(software)

            self.assertEqual(warnings, [])
            self.assertEqual(
                software[0]["description_zh"],
                "一款功能齐全的下载管理器。",
            )
            self.assertEqual(
                software[0]["description_en"],
                "A full-featured download manager.",
            )
            self.assertEqual(software[0]["analysis_zh"], ANALYSIS)
            self.assertNotIn("\n", software[0]["analysis_zh"])
            self.assertNotIn("_readme_excerpt", software[0])
            self.assertTrue(cache_path.exists())

            cached_software = _software()
            cached = DescriptionTranslator(model_command=None, cache_path=cache_path)
            self.assertEqual(cached.enrich(cached_software), [])
            self.assertEqual(
                cached_software[0]["description_zh"],
                "一款功能齐全的下载管理器。",
            )
            self.assertEqual(cached_software[0]["analysis_zh"], ANALYSIS)

    def test_fails_without_model_when_cache_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            software = _software()
            translator = DescriptionTranslator(
                model_command=None,
                cache_path=Path(directory) / "translations.json",
            )

            with self.assertRaisesRegex(RuntimeError, "未配置 Codex CLI"):
                translator.enrich(software)

    def test_translates_large_list_in_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            software = [
                {
                    "name": f"owner/example-{index}",
                    "description": f"Cross-platform example {index}.",
                    "language": "Rust",
                }
                for index in range(26)
            ]
            translator = BatchTranslator(
                model_command="stub",
                cache_path=Path(directory) / "translations.json",
            )

            warnings = translator.enrich(software)

            self.assertEqual(warnings, [])
            self.assertEqual(translator.batch_sizes, [25, 1])
            self.assertEqual(translator.analysis_batch_sizes, [10, 10, 6])
            self.assertTrue(
                all(item.get("description_zh") for item in software)
            )
            self.assertTrue(all(item.get("analysis_zh") for item in software))

    def test_keeps_only_chinese_part_of_bilingual_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            software = [
                {
                    "name": "owner/example",
                    "description": "跨平台剪贴板工具 | Cross-platform clipboard tool",
                    "language": "Rust",
                }
            ]
            translator = DescriptionTranslator(
                model_command=None,
                cache_path=Path(directory) / "translations.json",
            )

            with self.assertRaisesRegex(RuntimeError, "项目详情分析"):
                translator.enrich(software)

            self.assertEqual(software[0]["description_zh"], "跨平台剪贴板工具")

    def test_maps_short_model_name_back_to_full_repository_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            translator = ShortNameResponseTranslator(
                model_command="stub",
                cache_path=Path(directory) / "translations.json",
            )

            analyses = translator._request_analyses(
                [{"name": "owner/example"}]
            )

            self.assertIn("owner/example", analyses)

            translations = translator._request_translations(
                [
                    {
                        "name": "owner/example",
                        "description_en": "Cross-platform download manager.",
                    }
                ]
            )

            self.assertIn("owner/example", translations)

    def test_rewrites_english_heavy_bilingual_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            software = [
                {
                    "name": "owner/example",
                    "description": (
                        "一款开源音乐客户端 An open-source music client "
                        "for Windows and macOS"
                    ),
                    "language": "Vue",
                }
            ]
            translator = StubTranslator(
                model_command="stub",
                cache_path=Path(directory) / "translations.json",
            )

            translator.enrich(software)

            self.assertEqual(
                software[0]["description_zh"],
                "一款功能齐全的下载管理器。",
            )

    def test_prefers_chinese_parenthetical_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            software = [
                {
                    "name": "owner/example",
                    "description": (
                        "A fast desktop app built with Rust "
                        "（一款基于 Rust 的高性能桌面应用）"
                    ),
                    "language": "Rust",
                }
            ]
            translator = StubTranslator(
                model_command="stub",
                cache_path=Path(directory) / "translations.json",
            )

            translator.enrich(software)

            self.assertEqual(
                software[0]["description_zh"],
                "一款基于 Rust 的高性能桌面应用",
            )

    @patch("cross_platform_trending.translator.subprocess.run")
    def test_calls_codex_cli_with_json_schema(self, run: Any) -> None:
        run.return_value = CompletedProcess(
            args=[],
            returncode=0,
            stdout=dumps({"translations": []}, ensure_ascii=False),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            translator = DescriptionTranslator(
                model_command="codex",
                model="test-model",
                cache_path=Path(directory) / "translations.json",
            )
            schema = {
                "type": "object",
                "properties": {
                    "translations": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["translations"],
            }

            result = translator._request_model(
                {
                    "messages": [
                        {"role": "system", "content": "生成中文简介"},
                        {"role": "user", "content": "owner/example"},
                    ],
                    "response_format": {
                        "json_schema": {
                            "schema": schema,
                        }
                    },
                },
                "翻译",
            )

        self.assertEqual(result, {"translations": []})
        command = run.call_args.args[0]
        self.assertEqual(command[0:2], ["codex", "exec"])
        self.assertIn("--output-schema", command)
        self.assertEqual(command[command.index("--model") + 1], "test-model")
        self.assertIn("owner/example", command[-1])
        self.assertIs(run.call_args.kwargs["stdin"], __import__("subprocess").DEVNULL)


if __name__ == "__main__":
    unittest.main()
