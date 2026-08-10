from __future__ import annotations

import tempfile
import unittest
from json import dumps
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

from cross_platform_trending.translator import DescriptionTranslator, _valid_analysis


ANALYSIS = (
    "下载任务进入队列后，会由 Rust 编写的桌面客户端统一记录状态，并在网络中断后通过"
    "retry failed tasks 恢复失败任务。README 把 Manage downloads 作为主要入口，"
    "用户可以从任务列表观察单个文件的进度，而不必为每次中断重新创建下载。这个设计"
    "尤其适合需要连续获取大文件或一次整理多项资源的场合：客户端负责保存队列，重试"
    "机制处理临时失败，桌面界面则把执行结果集中呈现。仓库同时给出了构建客户端所需的"
    "Rust 工具链和不同系统的打包方式，准备自行编译的人可以直接沿着 README 的安装"
    "章节操作；只想使用成品时，则可从 release 页面选择与系统对应的安装包。"
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
                    "readme_evidence": [
                        "Manage downloads",
                        "retry failed tasks",
                    ],
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
                [
                    {
                        "name": "owner/example",
                        "readme_excerpt": (
                            "Manage downloads and retry failed tasks."
                        ),
                    }
                ]
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

    def test_rejects_formulaic_analysis_and_ungrounded_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            translator = ShortNameResponseTranslator(
                model_command="stub",
                cache_path=Path(directory) / "translations.json",
            )
            with patch.object(
                translator,
                "_request_model",
                return_value={
                    "analyses": [
                        {
                            "name": "owner/example",
                            "analysis_zh": "面向开发者" + ANALYSIS,
                            "readme_evidence": ["Manage downloads", "不存在"],
                        }
                    ]
                },
            ):
                self.assertEqual(
                    translator._request_analyses(_software()),
                    {},
                )

    def test_does_not_treat_keyboard_shortcut_as_markdown_list(self) -> None:
        analysis = ANALYSIS.replace(
            "下载任务进入队列后",
            "按下 Alt / Command + Space 后，下载任务进入队列",
        )

        self.assertTrue(_valid_analysis(analysis))

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
