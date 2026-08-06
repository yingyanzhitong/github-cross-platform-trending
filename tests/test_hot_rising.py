from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from github_hot_rising.collector import _history_delta, render_report
from github_hot_rising.validator import validate


ANALYSIS = {
    "positioning": "这是用于测试榜单生成的仓库。",
    "implementation": "它通过明确的数据结构和报告渲染函数生成日报。",
    "problems_solved": "它解决热门仓库证据难以集中查看的问题。",
    "capabilities": "生成结构化数据；生成可定位的 Markdown 报告。",
    "use_cases": "适合验证日报生成与页面展示流程。",
    "considerations": "测试数据不代表真实 GitHub 热度。",
}


def item(rank: int, *, is_new: bool) -> dict[str, object]:
    return {
        "rank": rank,
        "full_name": f"owner/repo-{rank}",
        "name": f"repo-{rank}",
        "url": f"https://github.com/owner/repo-{rank}",
        "description_zh": "用于验证热门增长榜的示例仓库。",
        "trend_type": "Daily Trending",
        "evidence": [f"GitHub Daily Trending 第 {rank} 名"],
        "stars": 1000 + rank,
        "language": "Python",
        "topics": ["trending"],
        "license": "MIT",
        "pushed_at": "2026-08-04T00:00:00Z",
        "is_new": is_new,
        "analysis_zh": ANALYSIS,
    }


class HotRisingReportTests(unittest.TestCase):
    def test_history_delta_requires_exact_observation_window(self) -> None:
        history = {
            "2026-08-04": {"owner/repo": 100},
            "2026-08-05": {"other/repo": 200},
        }

        delta, growth = _history_delta(
            history, "owner/repo", 130, date(2026, 8, 6), 1
        )

        self.assertIsNone(delta)
        self.assertIsNone(growth)

    def test_report_uses_distinct_title_and_bidirectional_anchors(self) -> None:
        payload = {
            "date": "2026-08-04",
            "collected_at": "2026-08-04T09:00:00+08:00",
            "metadata": {"candidate_count": 500, "analyzed_count": 2},
            "items": [item(1, is_new=True), item(2, is_new=False)],
        }

        report = render_report(payload)

        self.assertIn("# GitHub 热门增长仓库榜单", report)
        self.assertIn('[#1 ↘️](#project-detail-1)', report)
        self.assertIn('[↖️ 返回表格中的 #1](#project-row-1)', report)
        self.assertEqual(report.count("🟢"), 2)
        self.assertNotIn("NEW", report)

    def test_validator_checks_namespaced_latest_files(self) -> None:
        target = date(2026, 8, 4)
        payload = {
            "date": target.isoformat(),
            "collected_at": "2026-08-04T09:00:00+08:00",
            "metadata": {"candidate_count": 500, "analyzed_count": 2},
            "items": [item(1, is_new=True), item(2, is_new=False)],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            reports_dir = root / "reports"
            data_dir.mkdir()
            reports_dir.mkdir()
            data_text = json.dumps(payload, ensure_ascii=False)
            report_text = render_report(payload)
            (data_dir / f"{target}.json").write_text(data_text)
            (data_dir / "latest.json").write_text(data_text)
            (reports_dir / f"{target}.md").write_text(report_text)
            (reports_dir / "latest.md").write_text(report_text)

            with (
                patch("github_hot_rising.validator.DATA_DIR", data_dir),
                patch("github_hot_rising.validator.REPORTS_DIR", reports_dir),
            ):
                result = validate(target, expected_count=2)

        self.assertEqual(result["items"], 2)
        self.assertEqual(result["new"], 1)


if __name__ == "__main__":
    unittest.main()
