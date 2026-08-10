from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .translator import (
    ANALYSIS_MAX_LENGTH,
    ANALYSIS_MIN_LENGTH,
    normalize_analysis,
)


def mark_new_projects(
    report_date: str,
    software: list[dict[str, Any]],
    data_dir: Path,
    *,
    days: int = 7,
) -> None:
    """标记此前若干天的日报中从未出现过的项目。"""
    current_date = date.fromisoformat(report_date)
    recent_names: set[str] = set()

    for offset in range(1, days + 1):
        history_date = current_date - timedelta(days=offset)
        history_path = data_dir / f"{history_date.isoformat()}.json"
        if not history_path.exists():
            continue

        payload = json.loads(history_path.read_text(encoding="utf-8"))
        history_software = payload.get("software")
        if not isinstance(history_software, list):
            raise ValueError(f"历史数据格式无效：{history_path}")
        recent_names.update(
            item["name"].casefold()
            for item in history_software
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )

    for item in software:
        item["is_new"] = item["name"].casefold() not in recent_names


def _escape_table(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _analysis_summary(item: dict[str, Any]) -> str:
    """返回 200–1000 字、不分点的单段中文分析。"""
    source = item.get("analysis_zh") or item.get("analysis_summary_zh") or ""
    description = str(item.get("description_zh") or item.get("description") or "")
    return normalize_analysis(source, description=description)


def _heat(item: dict[str, Any]) -> str:
    if item.get("trending_rank"):
        today = f"，今日 +{item['stars_today']:,} Stars" if item.get("stars_today") else ""
        return f"Daily Trending #{item['trending_rank']}{today}"
    return "近期活跃热门仓库"


def _installer_download_link(item: dict[str, Any], evidence: str) -> str:
    filename = evidence.removeprefix("Release: ").strip()
    release = item.get("latest_release") or {}
    repository_url = str(item.get("url") or "").rstrip("/")
    tag = str(release.get("tag") or "")
    if not filename or not repository_url or not tag:
        return evidence

    download_url = (
        f"{repository_url}/releases/download/"
        f"{quote(tag, safe='')}/{quote(filename, safe='')}"
    )
    return f"[{filename}]({download_url})"


def _installer_links(
    item: dict[str, Any],
    platform: str,
    *,
    limit: int | None = None,
    separator: str = "；",
) -> str:
    evidence = item["platform_evidence"][platform]
    if limit is not None:
        evidence = evidence[:limit]
    return separator.join(_installer_download_link(item, value) for value in evidence)


def render_markdown(
    report_date: str,
    software: list[dict[str, Any]],
    metadata: dict[str, Any],
    generated_at: str,
) -> str:
    lines = [
        f"# GitHub 跨平台热门软件日报 · {report_date}",
        "",
        "> 自动筛选同时提供 macOS 与 Windows 安装包的 GitHub 热门软件。Latest Release 必须同时包含两端安装包。",
        "",
        f"- 生成时间：{generated_at}",
        f"- 发现候选：{metadata.get('discovered_count', metadata['candidate_count'])} 个",
        f"- 已分析候选：{metadata['candidate_count']} 个",
        f"- 入榜软件：{len(software)} 个",
        "- 新增标识：🟢 表示该仓库最近 7 天未曾入榜",
        "",
    ]
    if not software:
        lines.extend(
            [
                "今天没有候选项目通过跨平台软件证据筛选。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| 详情 ↘️ | 新增 | 软件 | 中文简介 | 热度 | Stars | 主要语言 | 平台证据 |",
                "|:---:|:---:|---|---|---|---:|---|---|",
            ]
        )
        for item in sorted(
            software,
            key=lambda candidate: not bool(candidate.get("is_new")),
        ):
            description_zh = item.get("description_zh") or item["description"]
            macos = _installer_links(item, "macos", limit=2, separator="、")
            windows = _installer_links(item, "windows", limit=2, separator="、")
            evidence = f"macOS 安装包：{macos}；Windows 安装包：{windows}"
            new_label = "🟢" if item.get("is_new") else "—"
            lines.append(
                "| <a id=\"project-row-{rank}\"></a>"
                "[#{rank} ↘️](#project-detail-{rank}) | {new_label} | "
                "[{name}]({url}) | {description} | {heat} | {stars:,} | "
                "{language} | {evidence} |".format(
                    rank=item["rank"],
                    name=item["name"],
                    url=item["url"],
                    new_label=new_label,
                    description=_escape_table(description_zh),
                    heat=_heat(item),
                    stars=item["stars"],
                    language=item["language"],
                    evidence=_escape_table(evidence),
                )
            )
        lines.append("")
        lines.append("## 项目详情")
        lines.append("")
        for item in software:
            new_label = " 🟢" if item.get("is_new") else ""
            topics = "、".join(str(topic) for topic in item.get("topics", [])[:10])
            lines.extend(
                [
                    f"<a id=\"project-detail-{item['rank']}\"></a>",
                    "",
                    f"### {item['rank']}. [{item['name']}]({item['url']}){new_label}",
                    "",
                    f"[↖️ 返回表格中的 #{item['rank']}](#project-row-{item['rank']})",
                    "",
                    "#### 中文分析",
                    "",
                    _analysis_summary(item),
                    "",
                    "#### 项目概况",
                    "",
                    f"- 热度：{_heat(item)}；累计 {item['stars']:,} 个星标 / {item['forks']:,} 次复刻",
                    f"- 主要语言：{item['language']}；许可证：{item.get('license') or '未标注'}",
                    f"- 主题标签：{topics or '未标注'}",
                    f"- 仓库创建：{item.get('created_at') or '未知'}",
                    f"- 最近推送：{item['pushed_at'] or '未知'}",
                ]
            )
            if item.get("homepage"):
                lines.append(f"- 项目主页：[{item['homepage']}]({item['homepage']})")
            lines.extend(
                [
                    "",
                    "#### 最新发布与安装",
                    "",
                ]
            )
            if item.get("latest_release"):
                release = item["latest_release"]
                tag = release.get("tag") or "Latest Release"
                published_at = release.get("published_at") or "未知"
                lines.append(
                    f"- 最新版本：[{tag}]({release['url']})；发布时间：{published_at}"
                )
            lines.extend(
                [
                    f"- macOS 安装包：{_installer_links(item, 'macos')}",
                    f"- Windows 安装包：{_installer_links(item, 'windows')}",
                ]
            )
            lines.append("")

    if metadata.get("warnings"):
        lines.extend(
            [
                "<details>",
                "<summary>采集警告</summary>",
                "",
                *[f"- {warning}" for warning in metadata["warnings"]],
                "",
                "</details>",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "筛选说明：GitHub Daily Trending 优先；同时补充近期活跃的 desktop-app、cross-platform、Electron、Tauri，以及带 macOS/Windows Topics 的仓库。该榜单使用可复核的启发式规则，不代表 GitHub 官方推荐。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    *,
    report_date: str,
    software: list[dict[str, Any]],
    metadata: dict[str, Any],
    generated_at: str,
    report_dir: Path,
    data_dir: Path,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    mark_new_projects(report_date, software, data_dir)
    for item in software:
        analysis = _analysis_summary(item)
        item["analysis_zh"] = analysis
        item["analysis_summary_zh"] = analysis
        summary_length = len(analysis)
        if not ANALYSIS_MIN_LENGTH <= summary_length <= ANALYSIS_MAX_LENGTH:
            raise ValueError(
                f"{item['name']} 的中文分析为 {summary_length} 字，"
                f"不在 {ANALYSIS_MIN_LENGTH}–{ANALYSIS_MAX_LENGTH} 字范围内"
            )
        if "\n" in analysis:
            raise ValueError(f"{item['name']} 的中文分析不是单段文本")

    payload = {
        "date": report_date,
        "generated_at": generated_at,
        **metadata,
        "software": software,
    }
    markdown = render_markdown(report_date, software, metadata, generated_at)

    dated_report = report_dir / f"{report_date}.md"
    latest_report = report_dir / "latest.md"
    dated_data = data_dir / f"{report_date}.json"
    latest_data = data_dir / "latest.json"

    dated_report.write_text(markdown, encoding="utf-8")
    latest_report.write_text(markdown, encoding="utf-8")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    dated_data.write_text(serialized, encoding="utf-8")
    latest_data.write_text(serialized, encoding="utf-8")
    return dated_report, dated_data
