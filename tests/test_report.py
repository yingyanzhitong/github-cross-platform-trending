from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cross_platform_trending.report import mark_new_projects, render_markdown


class RenderMarkdownTests(unittest.TestCase):
    def test_table_lists_new_projects_first_without_changing_detail_order(self) -> None:
        def table_item(rank: int, *, is_new: bool) -> dict[str, object]:
            return {
                "rank": rank,
                "name": f"owner/repo-{rank}",
                "url": f"https://github.com/owner/repo-{rank}",
                "description": "示例桌面应用",
                "description_zh": "示例桌面应用。",
                "stars": 1000 + rank,
                "forks": rank,
                "language": "Rust",
                "topics": [],
                "platform_evidence": {"macos": [], "windows": []},
                "pushed_at": "2026-08-06T00:00:00Z",
                "is_new": is_new,
            }

        software = [
            table_item(1, is_new=False),
            table_item(2, is_new=True),
            table_item(3, is_new=False),
            table_item(4, is_new=True),
        ]
        with (
            patch(
                "cross_platform_trending.report._installer_links",
                return_value="安装包",
            ),
            patch(
                "cross_platform_trending.report._heat",
                return_value="近期活跃热门仓库",
            ),
        ):
            markdown = render_markdown(
                "2026-08-06",
                software,
                {"candidate_count": 4, "warnings": []},
                "2026-08-06T08:30:00+08:00",
            )

        table, details = markdown.split("\n## 项目详情", 1)
        table_positions = [table.index(f'project-row-{rank}') for rank in (2, 4, 1, 3)]
        self.assertEqual(table_positions, sorted(table_positions))
        detail_positions = [
            details.index(f'project-detail-{rank}') for rank in (1, 2, 3, 4)
        ]
        self.assertEqual(detail_positions, sorted(detail_positions))

    def test_renders_repository_and_evidence(self) -> None:
        software = [
            {
                "rank": 1,
                "name": "owner/example",
                "url": "https://github.com/owner/example",
                "description": "Example desktop app",
                "description_zh": "一款示例桌面应用。",
                "trending_rank": 2,
                "stars_today": 88,
                "stars": 1200,
                "forks": 100,
                "language": "Rust",
                "license": "MIT",
                "topics": ["desktop-app", "download-manager"],
                "homepage": "https://example.com",
                "created_at": "2025-01-01T00:00:00Z",
                "platform_evidence": {
                    "macos": ["Release: example 1.0+arm64.dmg"],
                    "windows": ["Release: example 1.0+setup.exe"],
                },
                "pushed_at": "2026-07-29T00:00:00Z",
                "latest_release": {
                    "tag": "v1.0.0+stable",
                    "url": "https://github.com/owner/example/releases/tag/v1.0.0%2Bstable",
                    "published_at": "2026-07-29T01:00:00Z",
                },
                "is_new": True,
                "analysis_zh": {
                    "positioning": "面向桌面用户的跨平台下载管理工具。",
                    "implementation": "使用 Rust 构建桌面客户端，通过任务队列管理下载。",
                    "problems_solved": "解决多任务下载难以集中管理和失败后手动重试的问题。",
                    "capabilities": "管理下载任务；支持 macOS 与 Windows 客户端。",
                    "use_cases": "适合需要统一管理桌面下载任务的用户。",
                    "considerations": "使用前应核对项目文档与安装包签名。",
                },
            }
        ]

        markdown = render_markdown(
            "2026-07-29",
            software,
            {"candidate_count": 10, "warnings": []},
            "2026-07-29T08:30:00+08:00",
        )

        self.assertIn("owner/example", markdown)
        self.assertIn("| 详情 ↘️ | 新增 | 软件 | 中文简介 |", markdown)
        self.assertIn("| 🟢 |", markdown)
        self.assertIn("新增标识：🟢 表示该仓库最近 7 天未曾入榜", markdown)
        self.assertNotIn("NEW", markdown)
        self.assertNotIn("🆕", markdown)
        self.assertIn("| 一款示例桌面应用。 |", markdown)
        self.assertNotIn("Example desktop app", markdown)
        self.assertIn("Daily Trending #2", markdown)
        macos_download_url = (
            "https://github.com/owner/example/releases/download/"
            "v1.0.0%2Bstable/example%201.0%2Barm64.dmg"
        )
        windows_download_url = (
            "https://github.com/owner/example/releases/download/"
            "v1.0.0%2Bstable/example%201.0%2Bsetup.exe"
        )
        self.assertIn("[example 1.0+arm64.dmg]", markdown)
        self.assertIn("[example 1.0+setup.exe]", markdown)
        self.assertEqual(markdown.count(macos_download_url), 2)
        self.assertEqual(markdown.count(windows_download_url), 2)
        self.assertIn("macOS 安装包", markdown)
        self.assertIn("Windows 安装包", markdown)
        self.assertIn("1,200 个星标 / 100 次复刻", markdown)
        self.assertEqual(markdown.count("🟢"), 3)
        self.assertIn('<a id="project-row-1"></a>', markdown)
        self.assertIn("[#1 ↘️](#project-detail-1)", markdown)
        self.assertNotIn("| 平台证据 | 详情 |", markdown)
        self.assertIn('<a id="project-detail-1"></a>', markdown)
        self.assertIn("[↖️ 返回表格中的 #1](#project-row-1)", markdown)
        self.assertIn("#### 中文分析", markdown)
        self.assertIn("**项目是做什么的**：面向桌面用户的跨平台下载管理工具。", markdown)
        self.assertIn("**怎么做到的**：使用 Rust 构建桌面客户端", markdown)
        self.assertIn("**解决了什么问题**：解决多任务下载难以集中管理", markdown)
        self.assertIn("**核心能力**：管理下载任务", markdown)
        self.assertIn("#### 项目概况", markdown)
        self.assertIn("主要语言：Rust；许可证：MIT", markdown)
        self.assertIn("主题标签：desktop-app、download-manager", markdown)
        self.assertIn("#### 最新发布与安装", markdown)

    def test_marks_project_new_when_absent_from_previous_seven_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "2026-07-23.json").write_text(
                json.dumps({"software": [{"name": "owner/known"}]}),
                encoding="utf-8",
            )
            (data_dir / "2026-07-22.json").write_text(
                json.dumps({"software": [{"name": "owner/too-old"}]}),
                encoding="utf-8",
            )
            software = [
                {"name": "owner/known"},
                {"name": "owner/too-old"},
                {"name": "owner/new"},
            ]

            mark_new_projects("2026-07-30", software, data_dir)

        self.assertFalse(software[0]["is_new"])
        self.assertTrue(software[1]["is_new"])
        self.assertTrue(software[2]["is_new"])

    def test_same_day_snapshot_does_not_hide_new_label_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "2026-07-30.json").write_text(
                json.dumps({"software": [{"name": "owner/example"}]}),
                encoding="utf-8",
            )
            software = [{"name": "owner/example"}]

            mark_new_projects("2026-07-30", software, data_dir)

        self.assertTrue(software[0]["is_new"])


if __name__ == "__main__":
    unittest.main()
