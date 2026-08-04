from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


DATED_REPORT = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
MANAGED_OUTPUTS = ("assets", "reports", "index.html", "404.html", ".nojekyll")


def _remove_managed_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in MANAGED_OUTPUTS:
        target = output_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _software_summary(report_path: Path, data_dir: Path) -> dict[str, Any]:
    report_date = report_path.stem
    data_path = data_dir / f"{report_date}.json"
    if not data_path.exists():
        raise FileNotFoundError(f"报告缺少对应数据：{data_path}")

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    software = payload.get("software")
    if not isinstance(software, list):
        raise ValueError(f"历史数据格式无效：{data_path}")

    daily_trending = [
        {
            "rank": item["rank"],
            "name": item["name"],
            "trending_rank": item["trending_rank"],
            "stars_today": item.get("stars_today") or 0,
        }
        for item in software
        if item.get("trending_rank")
    ]
    new_projects = [
        {"rank": item["rank"], "name": item["name"]}
        for item in software
        if item.get("is_new")
    ]
    return {
        "report_type": "cross-platform",
        "date": report_date,
        "generated_at": payload.get("generated_at"),
        "discovered_count": payload.get(
            "discovered_count",
            payload.get("candidate_count", 0),
        ),
        "candidate_count": payload.get("candidate_count", 0),
        "item_count": len(software),
        "analysis_count": len(software),
        "daily_trending": daily_trending,
        "weekly_trending": [],
        "new_projects": new_projects,
        "warnings_count": len(payload.get("warnings") or []),
        "item_names": [item["name"] for item in software],
        "report_path": f"reports/{report_date}.md",
    }


def _hot_rising_summary(report_path: Path, data_dir: Path) -> dict[str, Any]:
    report_date = report_path.stem
    data_path = data_dir / f"{report_date}.json"
    if not data_path.exists():
        raise FileNotFoundError(f"报告缺少对应数据：{data_path}")

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(f"热门增长榜历史数据格式无效：{data_path}")
    metadata = payload.get("metadata") or {}

    def trending(kind: str) -> list[dict[str, Any]]:
        rank_key = f"{kind}_trending_rank"
        stars_key = "stars_today" if kind == "daily" else "stars_this_week"
        return [
            {
                "rank": item["rank"],
                "name": item["full_name"],
                "trending_rank": item[rank_key],
                "stars_today": item.get(stars_key) or 0,
            }
            for item in items
            if item.get(rank_key)
        ]

    return {
        "report_type": "hot-rising",
        "date": report_date,
        "generated_at": payload.get("collected_at"),
        "discovered_count": metadata.get("candidate_count", 0),
        "candidate_count": metadata.get("analyzed_count", 0),
        "item_count": len(items),
        "analysis_count": metadata.get("analysis_count", len(items)),
        "daily_trending": trending("daily"),
        "weekly_trending": trending("weekly"),
        "new_projects": [
            {"rank": item["rank"], "name": item["full_name"]}
            for item in items
            if item.get("is_new")
        ],
        "warnings_count": len(metadata.get("warnings") or [])
        + len(metadata.get("analysis_warnings") or []),
        "item_names": [item["full_name"] for item in items],
        "report_path": f"reports/hot-rising/{report_date}.md",
    }


def _dated_reports(reports_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in reports_dir.glob("*.md")
            if DATED_REPORT.fullmatch(path.name)
        ),
        reverse=True,
    )


def build_frontend(site_dir: Path) -> Path:
    package_path = site_dir / "package.json"
    if not package_path.exists():
        raise FileNotFoundError(f"缺少前端工程配置：{package_path}")

    subprocess.run(["npm", "run", "build"], cwd=site_dir, check=True)
    frontend_dir = site_dir / "dist"
    if not (frontend_dir / "index.html").exists():
        raise FileNotFoundError(f"前端构建产物无效：{frontend_dir}")
    return frontend_dir


def _normalize_frontend_text(output_dir: Path) -> None:
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix not in {".css", ".html", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        normalized = "\n".join(line.rstrip() for line in text.splitlines())
        if text.endswith("\n"):
            normalized += "\n"
        path.write_text(normalized, encoding="utf-8")


def build_site(
    *,
    reports_dir: Path,
    data_dir: Path,
    site_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    report_paths = _dated_reports(reports_dir)
    if not report_paths:
        raise ValueError(f"未找到历史日报：{reports_dir}")
    frontend_dir = site_dir / "dist"
    if not (frontend_dir / "index.html").exists():
        raise FileNotFoundError(f"缺少前端构建产物：{frontend_dir / 'index.html'}")

    summaries = [_software_summary(path, data_dir) for path in report_paths]
    catalogs = [
        {
            "id": "cross-platform",
            "name": "跨平台热门软件",
            "latest": summaries[0]["date"],
            "reports": summaries,
        }
    ]
    hot_report_dir = reports_dir / "hot-rising"
    hot_data_dir = data_dir / "hot-rising"
    hot_report_paths = _dated_reports(hot_report_dir)
    if hot_report_paths:
        hot_summaries = [
            _hot_rising_summary(path, hot_data_dir) for path in hot_report_paths
        ]
        catalogs.append(
            {
                "id": "hot-rising",
                "name": "GitHub 热门增长仓库",
                "latest": hot_summaries[0]["date"],
                "reports": hot_summaries,
            }
        )
    manifest = {
        "default_type": "cross-platform",
        "catalogs": catalogs,
        "latest": summaries[0]["date"],
        "reports": summaries,
    }

    _remove_managed_output(output_dir)
    shutil.copytree(frontend_dir, output_dir, dirs_exist_ok=True)
    shutil.copy2(frontend_dir / "index.html", output_dir / "404.html")
    _normalize_frontend_text(output_dir)

    report_output = output_dir / "reports"
    report_output.mkdir(parents=True)
    for report_path in report_paths:
        shutil.copy2(report_path, report_output / report_path.name)
    if hot_report_paths:
        hot_output = report_output / "hot-rising"
        hot_output.mkdir()
        for report_path in hot_report_paths:
            shutil.copy2(report_path, hot_output / report_path.name)
    (report_output / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建 GitHub Pages 日报浏览站")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    parser.add_argument("--skip-frontend-build", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.skip_frontend_build:
        build_frontend(args.site_dir)
    manifest = build_site(
        reports_dir=args.reports_dir,
        data_dir=args.data_dir,
        site_dir=args.site_dir,
        output_dir=args.output_dir,
    )
    print(
        f"已构建 {sum(len(item['reports']) for item in manifest['catalogs'])} 份日报，"
        f"包含 {len(manifest['catalogs'])} 类榜单：{args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
