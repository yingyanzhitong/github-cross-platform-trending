from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_pages import build_site


class BuildPagesTests(unittest.TestCase):
    def test_builds_report_manifest_and_copies_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            data = root / "data"
            site = root / "site"
            output = root / "docs"
            reports.mkdir()
            data.mkdir()
            (site / "assets").mkdir(parents=True)
            (site / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (site / "assets" / "app.js").write_text("", encoding="utf-8")
            (reports / "2026-07-30.md").write_text("# 日报", encoding="utf-8")
            (reports / "latest.md").write_text("# 最新", encoding="utf-8")
            (data / "2026-07-30.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-30T08:30:00+08:00",
                        "discovered_count": 1000,
                        "candidate_count": 600,
                        "warnings": [],
                        "software": [
                            {
                                "rank": 1,
                                "name": "owner/example",
                                "trending_rank": 2,
                                "stars_today": 88,
                                "is_new": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = build_site(
                reports_dir=reports,
                data_dir=data,
                site_dir=site,
                output_dir=output,
            )

            self.assertEqual(manifest["latest"], "2026-07-30")
            self.assertEqual(len(manifest["reports"]), 1)
            self.assertEqual(
                manifest["reports"][0]["software_names"],
                ["owner/example"],
            )
            self.assertEqual(len(manifest["reports"][0]["daily_trending"]), 1)
            self.assertEqual(len(manifest["reports"][0]["new_projects"]), 1)
            self.assertTrue((output / ".nojekyll").exists())
            self.assertTrue((output / "index.html").exists())
            self.assertTrue((output / "404.html").exists())
            self.assertTrue((output / "reports" / "2026-07-30.md").exists())
            self.assertFalse((output / "reports" / "latest.md").exists())


if __name__ == "__main__":
    unittest.main()
