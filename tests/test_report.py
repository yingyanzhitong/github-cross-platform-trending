from __future__ import annotations

import unittest

from cross_platform_trending.report import render_markdown


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
        self.assertIn("1,200 个星标 / 100 次复刻", markdown)


if __name__ == "__main__":
    unittest.main()
