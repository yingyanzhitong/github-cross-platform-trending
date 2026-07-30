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


def _summary(report_path: Path, data_dir: Path) -> dict[str, Any]:
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
        "date": report_date,
        "generated_at": payload.get("generated_at"),
        "discovered_count": payload.get(
            "discovered_count",
            payload.get("candidate_count", 0),
        ),
        "candidate_count": payload.get("candidate_count", 0),
        "software_count": len(software),
        "daily_trending": daily_trending,
        "new_projects": new_projects,
        "warnings_count": len(payload.get("warnings") or []),
        "software_names": [item["name"] for item in software],
    }


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
    report_paths = sorted(
        (
            path
            for path in reports_dir.glob("*.md")
            if DATED_REPORT.fullmatch(path.name)
        ),
        reverse=True,
    )
    if not report_paths:
        raise ValueError(f"未找到历史日报：{reports_dir}")
    frontend_dir = site_dir / "dist"
    if not (frontend_dir / "index.html").exists():
        raise FileNotFoundError(f"缺少前端构建产物：{frontend_dir / 'index.html'}")

    summaries = [_summary(path, data_dir) for path in report_paths]
    manifest = {
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
        f"已构建 {len(manifest['reports'])} 份日报，"
        f"最新日期 {manifest['latest']}：{args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
