from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


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


def _heat(item: dict[str, Any]) -> str:
    if item.get("trending_rank"):
        today = f"，今日 +{item['stars_today']:,} Stars" if item.get("stars_today") else ""
        return f"Daily Trending #{item['trending_rank']}{today}"
    return "近期活跃热门仓库"


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
                "| # | 软件 | 热度 | Stars | 主要语言 | 平台证据 |",
                "|---:|---|---|---:|---|---|",
            ]
        )
        for item in software:
            description_zh = item.get("description_zh") or item["description"]
            macos = "、".join(item["platform_evidence"]["macos"][:2])
            windows = "、".join(item["platform_evidence"]["windows"][:2])
            evidence = f"macOS 安装包：{macos}；Windows 安装包：{windows}"
            new_label = " 🆕 **NEW**" if item.get("is_new") else ""
            lines.append(
                "| {rank} | <a id=\"project-row-{rank}\"></a>[{name}]({url}){new_label} · "
                "[查看详情 ↓](#project-detail-{rank})<br>中文简介：{description} | {heat} | "
                "{stars:,} | {language} | {evidence} |".format(
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
            description_zh = item.get("description_zh") or item["description"]
            new_label = " 🆕 **NEW**" if item.get("is_new") else ""
            lines.extend(
                [
                    f"<a id=\"project-detail-{item['rank']}\"></a>",
                    "",
                    f"### {item['rank']}. [{item['name']}]({item['url']}){new_label}",
                    "",
                    f"[↑ 返回榜单中的本项目](#project-row-{item['rank']})",
                    "",
                    description_zh,
                    "",
                    f"- 热度：{_heat(item)}；累计 {item['stars']:,} 个星标 / {item['forks']:,} 次复刻",
                    f"- macOS 安装包：{'；'.join(item['platform_evidence']['macos'])}",
                    f"- Windows 安装包：{'；'.join(item['platform_evidence']['windows'])}",
                    f"- 最近推送：{item['pushed_at'] or '未知'}",
                ]
            )
            if item.get("latest_release"):
                release = item["latest_release"]
                tag = release.get("tag") or "Latest Release"
                lines.append(f"- 最新版本：[{tag}]({release['url']})")
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
