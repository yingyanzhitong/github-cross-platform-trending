from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collector import GitHubClient, collect
from .report import write_report
from .translator import DescriptionTranslator


def _token_from_gh() -> str | None:
    if os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"):
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成同时支持 macOS 与 Windows 的 GitHub 热门软件日报"
    )
    parser.add_argument("--limit", type=int, default=20, help="榜单最大项目数")
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=100,
        help="最多分析的候选仓库数",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="Markdown 报告目录",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="JSON 数据目录",
    )
    parser.add_argument(
        "--date",
        help="报告日期（YYYY-MM-DD），默认使用 Asia/Shanghai 当天",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1 or args.max_candidates < 1:
        print("--limit 和 --max-candidates 必须大于 0", file=sys.stderr)
        return 2

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    report_date = args.date or now.date().isoformat()
    generated_at = now.isoformat(timespec="seconds")

    client = GitHubClient(token=_token_from_gh())
    software, metadata = collect(
        client,
        limit=args.limit,
        max_candidates=args.max_candidates,
    )
    translator = DescriptionTranslator(
        token=client.token,
        cache_path=args.data_dir / "translations.json",
    )
    metadata["warnings"].extend(translator.enrich(software))
    dated_report, dated_data = write_report(
        report_date=report_date,
        software=software,
        metadata=metadata,
        generated_at=generated_at,
        report_dir=args.report_dir,
        data_dir=args.data_dir,
    )
    print(
        f"已生成 {len(software)} 个软件条目：{dated_report}，数据：{dated_data}"
    )
    for warning in metadata["warnings"]:
        print(f"警告：{warning}", file=sys.stderr)
    return 0
