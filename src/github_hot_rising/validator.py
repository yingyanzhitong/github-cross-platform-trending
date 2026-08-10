from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from cross_platform_trending.translator import (
    ANALYSIS_MAX_LENGTH,
    ANALYSIS_MIN_LENGTH,
    normalize_analysis,
)

from .collector import DATA_DIR, REPORTS_DIR


def validate(target: date, *, expected_count: int = 100) -> dict[str, int]:
    data_path = DATA_DIR / f"{target}.json"
    report_path = REPORTS_DIR / f"{target}.md"
    if not data_path.exists() or not report_path.exists():
        raise AssertionError(f"缺少 {target} 的热门增长榜数据或报告")
    if data_path.read_bytes() != (DATA_DIR / "latest.json").read_bytes():
        raise AssertionError("data/hot-rising/latest.json 与当天文件不一致")
    if report_path.read_bytes() != (REPORTS_DIR / "latest.md").read_bytes():
        raise AssertionError("reports/hot-rising/latest.md 与当天文件不一致")

    payload: dict[str, Any] = json.loads(data_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    items = payload.get("items") or []
    if len(items) != expected_count:
        raise AssertionError(f"入榜数为 {len(items)}，不是 {expected_count}")
    names = [item["full_name"] for item in items]
    if len(set(names)) != expected_count:
        raise AssertionError("榜单存在重复仓库")

    for item in items:
        if not item.get("url", "").startswith("https://github.com/"):
            raise AssertionError(f"{item['full_name']} URL 无效")
        if not item.get("evidence"):
            raise AssertionError(f"{item['full_name']} 缺少热度或增长证据")
        analysis = item.get("analysis_zh")
        if not isinstance(analysis, str) or analysis != normalize_analysis(analysis):
            raise AssertionError(f"{item['full_name']} 中文分析不是规范单段文本")
        if not re.search(r"[\u4e00-\u9fff]", analysis):
            raise AssertionError(f"{item['full_name']} 中文分析缺少中文内容")
        if not ANALYSIS_MIN_LENGTH <= len(analysis) <= ANALYSIS_MAX_LENGTH:
            raise AssertionError(
                f"{item['full_name']} 中文分析为 {len(analysis)} 字，"
                f"不在 {ANALYSIS_MIN_LENGTH}–{ANALYSIS_MAX_LENGTH} 字范围内"
            )
        if item.get("analysis_summary_zh") != analysis:
            raise AssertionError(f"{item['full_name']} 中文分析兼容字段不一致")

    analysis_blocks = re.findall(
        r"^#### 中文分析\n\n([^\n]+)\n\n#### 项目概况$",
        report,
        re.M,
    )

    checks = {
        "rows": len(re.findall(r'<a id="project-row-\d+"></a>', report)),
        "details": len(re.findall(r'<a id="project-detail-\d+"></a>', report)),
        "returns": len(
            re.findall(
                r"\[↖️ 返回表格中的 #\d+\]\(#project-row-\d+\)", report
            )
        ),
        "analysis": len(analysis_blocks),
        "overview": len(re.findall(r"^#### 项目概况$", report, re.M)),
        "evidence": len(re.findall(r"^#### 热度与增长证据$", report, re.M)),
    }
    for label, count in checks.items():
        if count != expected_count:
            raise AssertionError(f"{label} 数量为 {count}，不是 {expected_count}")
    if any(not ANALYSIS_MIN_LENGTH <= len(block) <= ANALYSIS_MAX_LENGTH for block in analysis_blocks):
        raise AssertionError("Markdown 中文分析存在长度不合格项")
    if "NEW" in report or "🆕" in report:
        raise AssertionError("报告含禁用的新增文案")
    expected_new = sum(bool(item.get("is_new")) for item in items)
    if report.count("🟢") != expected_new * 2:
        raise AssertionError("绿色新增标识与最近 7 天历史不一致")
    table = report.split("\n## 项目详情", 1)[0]
    table_ranks = [
        int(rank)
        for rank in re.findall(r'<a id="project-row-(\d+)"></a>', table)
    ]
    expected_ranks = [
        int(item["rank"])
        for item in sorted(
            items,
            key=lambda candidate: not bool(candidate.get("is_new")),
        )
    ]
    if table_ranks != expected_ranks:
        raise AssertionError("表格未将新增项目置顶或改变了原有稳定顺序")
    return {
        "items": expected_count,
        "details": checks["details"],
        "analysis": checks["analysis"],
        "new": expected_new,
    }
