from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cross_platform_trending.report import render_markdown
from cross_platform_trending.translator import (
    ANALYSIS_MAX_LENGTH,
    ANALYSIS_MIN_LENGTH,
    normalize_analysis,
)
from github_hot_rising.collector import render_report


ROOT = Path(__file__).resolve().parents[1]


def _analysis(item: dict[str, Any], name: str) -> str:
    source = item.get("analysis_zh") or item.get("analysis_summary_zh") or ""
    description = str(item.get("description_zh") or item.get("description") or "")
    analysis = normalize_analysis(source, description=description)
    if not ANALYSIS_MIN_LENGTH <= len(analysis) <= ANALYSIS_MAX_LENGTH:
        raise ValueError(
            f"{name} 的中文分析为 {len(analysis)} 字，"
            f"不在 {ANALYSIS_MIN_LENGTH}–{ANALYSIS_MAX_LENGTH} 字范围内"
        )
    if "\n" in analysis:
        raise ValueError(f"{name} 的中文分析不是单段文本")
    return analysis


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _migrate_cross_platform(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    software = payload.get("software") or []
    for item in software:
        analysis = _analysis(item, str(item.get("name") or "未知仓库"))
        item["analysis_zh"] = analysis
        item["analysis_summary_zh"] = analysis
    _write_json(path, payload)

    report_name = "latest.md" if path.name == "latest.json" else f"{payload['date']}.md"
    report = render_markdown(
        payload["date"],
        software,
        payload,
        payload["generated_at"],
    )
    (ROOT / "reports" / report_name).write_text(report, encoding="utf-8")
    return len(software)


def _migrate_hot_rising(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    for item in items:
        name = str(item.get("full_name") or item.get("name") or "未知仓库")
        analysis = _analysis(item, name)
        item["analysis_zh"] = analysis
        item["analysis_summary_zh"] = analysis
    _write_json(path, payload)

    report_name = "latest.md" if path.name == "latest.json" else f"{payload['date']}.md"
    report = render_report(payload)
    (ROOT / "reports" / "hot-rising" / report_name).write_text(
        report,
        encoding="utf-8",
    )
    return len(items)


def _migrate_cache(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    migrated = 0
    for name, entry in (payload.get("translations") or {}).items():
        if not entry.get("analysis_zh"):
            continue
        entry["analysis_zh"] = _analysis(entry, str(name))
        migrated += 1
    _write_json(path, payload)
    return migrated


def main() -> None:
    cross_paths = sorted((ROOT / "data").glob("20??-??-??.json"))
    cross_paths.append(ROOT / "data" / "latest.json")
    hot_paths = sorted((ROOT / "data" / "hot-rising").glob("20??-??-??.json"))
    hot_paths.append(ROOT / "data" / "hot-rising" / "latest.json")

    cross_items = sum(_migrate_cross_platform(path) for path in cross_paths)
    hot_items = sum(_migrate_hot_rising(path) for path in hot_paths)
    cache_items = sum(
        _migrate_cache(path)
        for path in (
            ROOT / "data" / "translations.json",
            ROOT / "data" / "hot-rising" / "translations.json",
        )
    )
    print(
        f"已迁移跨平台项目 {cross_items} 条、热门增长项目 {hot_items} 条、"
        f"缓存分析 {cache_items} 条。"
    )


if __name__ == "__main__":
    main()
