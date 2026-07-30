from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cross_platform_trending.report import mark_new_projects, render_markdown


class RenderMarkdownTests(unittest.TestCase):
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
                "platform_evidence": {
                    "macos": ["Release: example.dmg"],
                    "windows": ["Release: example.exe"],
                },
                "pushed_at": "2026-07-29T00:00:00Z",
                "latest_release": None,
                "is_new": True,
            }
        ]

        markdown = render_markdown(
            "2026-07-29",
            software,
            {"candidate_count": 10, "warnings": []},
            "2026-07-29T08:30:00+08:00",
        )

        self.assertIn("owner/example", markdown)
        self.assertIn("中文简介：一款示例桌面应用。", markdown)
        self.assertNotIn("Example desktop app", markdown)
        self.assertIn("Daily Trending #2", markdown)
        self.assertIn("example.dmg", markdown)
        self.assertIn("example.exe", markdown)
        self.assertIn("macOS 安装包", markdown)
        self.assertIn("Windows 安装包", markdown)
        self.assertIn("1,200 个星标 / 100 次复刻", markdown)
        self.assertEqual(markdown.count("🆕 **NEW**"), 2)
        self.assertIn('<a id="project-row-1"></a>', markdown)
        self.assertIn("[查看详情 ↓](#project-detail-1)", markdown)
        self.assertIn('<a id="project-detail-1"></a>', markdown)
        self.assertIn("[↑ 返回榜单中的本项目](#project-row-1)", markdown)

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
