from __future__ import annotations

import base64
import json
import math
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from cross_platform_trending.translator import DescriptionTranslator


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "hot-rising"
REPORTS_DIR = ROOT / "reports" / "hot-rising"
TRANSLATIONS_PATH = DATA_DIR / "translations.json"
HISTORY_PATH = DATA_DIR / "stars-history.json"
USER_AGENT = (
    "github-cross-platform-trending/hot-rising "
    "(+https://github.com/yingyanzhitong/github-cross-platform-trending)"
)


@dataclass
class Candidate:
    full_name: str
    repo: dict[str, Any] = field(default_factory=dict)
    daily_rank: int | None = None
    daily_stars: int | None = None
    weekly_rank: int | None = None
    weekly_stars: int | None = None
    age_speed: float = 0.0
    age_speed_rank: int | None = None
    delta_1d: int | None = None
    delta_7d: int | None = None
    growth_1d: float | None = None
    growth_7d: float | None = None
    score: float = 0.0


def _gh_api(endpoint: str) -> Any:
    result = subprocess.run(
        ["gh", "api", endpoint],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _plain_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def fetch_trending(since: str) -> list[dict[str, Any]]:
    html = _fetch(f"https://github.com/trending?since={since}")
    rows: list[dict[str, Any]] = []
    metric_label = "today" if since == "daily" else "this week"
    articles = re.findall(
        r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>',
        html,
        re.S,
    )
    for article in articles:
        match = re.search(
            r'<h2[^>]*>.*?href="/([^"/]+/[^"/#?]+)"', article, re.S
        )
        if not match:
            continue
        text = _plain_html(article)
        metric = re.search(
            rf"([\d,]+)\s+stars\s+{re.escape(metric_label)}", text, re.I
        )
        rows.append(
            {
                "full_name": match.group(1).strip(),
                "stars_period": (
                    int(metric.group(1).replace(",", "")) if metric else None
                ),
            }
        )
    return rows


def _search(query: str, sort: str, pages: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        endpoint = (
            "search/repositories?q="
            + quote(query, safe="")
            + f"&sort={sort}&order=desc&per_page=100&page={page}"
        )
        payload = _gh_api(endpoint)
        page_items = payload.get("items", [])
        items.extend(page_items)
        if len(page_items) < 100:
            break
    return items


def _valid_repo(repo: dict[str, Any]) -> bool:
    name = str(repo.get("full_name") or "")
    description = str(repo.get("description") or "").strip()
    junk = re.compile(
        r"(^|[-_/])(test|demo|hello-world|my-project|collection-\d+)([-_/]|$)",
        re.I,
    )
    return bool(
        name
        and description
        and not repo.get("fork")
        and not repo.get("archived")
        and not repo.get("mirror_url")
        and int(repo.get("size") or 0) > 0
        and not junk.search(name)
    )


def _repo_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_history() -> dict[str, dict[str, int]]:
    if not HISTORY_PATH.exists():
        return {}
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def _history_delta(
    history: dict[str, dict[str, int]],
    full_name: str,
    stars: int,
    today: date,
    days: int,
) -> tuple[int | None, float | None]:
    target = today - timedelta(days=days)
    snapshot = history.get(target.isoformat(), {})
    if full_name not in snapshot:
        return None, None
    previous = int(snapshot[full_name])
    delta = stars - previous
    return delta, (delta / previous if previous else None)


def discover(
    today: date,
    *,
    max_candidates: int,
    max_analyzed: int,
) -> tuple[list[Candidate], dict[str, Any]]:
    warnings: list[str] = []
    try:
        daily = fetch_trending("daily")
    except Exception as error:  # noqa: BLE001 - persisted as collection warning
        daily = []
        warnings.append(f"Daily Trending 采集失败：{type(error).__name__}")
    try:
        weekly = fetch_trending("weekly")
    except Exception as error:  # noqa: BLE001 - persisted as collection warning
        weekly = []
        warnings.append(f"Weekly Trending 采集失败：{type(error).__name__}")

    queries = [
        (
            f"created:>={(today - timedelta(days=30)).isoformat()} "
            "stars:>25 fork:false archived:false",
            "stars",
            3,
        ),
        (
            f"created:>={(today - timedelta(days=180)).isoformat()} "
            "stars:>100 fork:false archived:false",
            "stars",
            2,
        ),
        (
            f"pushed:>={(today - timedelta(days=7)).isoformat()} "
            "stars:>500 fork:false archived:false",
            "updated",
            3,
        ),
        (
            f"pushed:>={(today - timedelta(days=30)).isoformat()} "
            "stars:>3000 fork:false archived:false",
            "stars",
            3,
        ),
    ]
    trending_names = {
        row["full_name"] for row in [*daily, *weekly]
    }
    search_limit = max(max_candidates - len(trending_names), 0)
    candidates: dict[str, Candidate] = {}
    for query, sort, pages in queries:
        for repo in _search(query, sort, pages):
            if len(candidates) >= search_limit:
                break
            if _valid_repo(repo):
                candidates.setdefault(repo["full_name"], Candidate(repo["full_name"], repo))
        if len(candidates) >= search_limit:
            break

    for rank, row in enumerate(daily, 1):
        candidate = candidates.setdefault(row["full_name"], Candidate(row["full_name"]))
        candidate.daily_rank = rank
        candidate.daily_stars = row["stars_period"]
    for rank, row in enumerate(weekly, 1):
        candidate = candidates.setdefault(row["full_name"], Candidate(row["full_name"]))
        candidate.weekly_rank = rank
        candidate.weekly_stars = row["stars_period"]

    for candidate in list(candidates.values()):
        if candidate.repo:
            continue
        try:
            repo = _gh_api(f"repos/{candidate.full_name}")
        except subprocess.CalledProcessError:
            candidates.pop(candidate.full_name, None)
            continue
        if _valid_repo(repo):
            candidate.repo = repo
        else:
            candidates.pop(candidate.full_name, None)

    history = _load_history()
    now = datetime.now(timezone.utc)
    for candidate in candidates.values():
        repo = candidate.repo
        stars = int(repo.get("stargazers_count") or 0)
        age_days = max((today - _repo_date(repo["created_at"]).date()).days, 1)
        candidate.age_speed = stars / age_days
        candidate.delta_1d, candidate.growth_1d = _history_delta(
            history, candidate.full_name, stars, today, 1
        )
        candidate.delta_7d, candidate.growth_7d = _history_delta(
            history, candidate.full_name, stars, today, 7
        )

    by_speed = sorted(candidates.values(), key=lambda item: item.age_speed, reverse=True)
    for rank, candidate in enumerate(by_speed, 1):
        candidate.age_speed_rank = rank

    for candidate in candidates.values():
        stars = int(candidate.repo.get("stargazers_count") or 0)
        pushed_days = max((now - _repo_date(candidate.repo["pushed_at"])).days, 0)
        candidate.score = (
            (150 - candidate.daily_rank if candidate.daily_rank else 0)
            + (110 - candidate.weekly_rank if candidate.weekly_rank else 0)
            + math.log1p(max(candidate.daily_stars or 0, 0)) * 12
            + math.log1p(max(candidate.weekly_stars or 0, 0)) * 8
            + math.log1p(max(candidate.delta_1d or 0, 0)) * 18
            + math.log1p(max(candidate.delta_7d or 0, 0)) * 12
            + math.log1p(candidate.age_speed) * 16
            + math.log1p(stars) * 2
            + max(14 - pushed_days, 0)
        )

    qualified = [
        candidate
        for candidate in candidates.values()
        if candidate.daily_rank
        or candidate.weekly_rank
        or (candidate.delta_1d is not None and candidate.delta_1d > 0)
        or (candidate.delta_7d is not None and candidate.delta_7d > 0)
        or (candidate.age_speed_rank is not None and candidate.age_speed_rank <= 250)
    ]
    qualified.sort(key=lambda item: (-item.score, item.full_name.lower()))
    return qualified[:max_analyzed], {
        "warnings": warnings,
        "daily_trending_discovered": len(daily),
        "weekly_trending_discovered": len(weekly),
        "candidate_count": len(candidates),
        "qualified_candidate_count": len(qualified),
        "history": history,
    }


def _readme(full_name: str) -> str:
    payload = _gh_api(f"repos/{full_name}/readme")
    content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    content = re.sub(r"```.*?```", " ", content, flags=re.S)
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", content)
    content = re.sub(r"[#>*_`|~-]+", " ", content)
    return re.sub(r"\s+", " ", content).strip()


def _short(value: str, limit: int = 600) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _evidence(candidate: Candidate) -> tuple[list[str], str]:
    evidence: list[str] = []
    types: list[str] = []
    if candidate.daily_rank:
        metric = (
            f"，页面公开 {candidate.daily_stars:,} stars today"
            if candidate.daily_stars is not None
            else ""
        )
        evidence.append(f"GitHub Daily Trending 第 {candidate.daily_rank} 名{metric}")
        types.append("Daily Trending")
    if candidate.weekly_rank:
        metric = (
            f"，页面公开 {candidate.weekly_stars:,} stars this week"
            if candidate.weekly_stars is not None
            else ""
        )
        evidence.append(f"GitHub Weekly Trending 第 {candidate.weekly_rank} 名{metric}")
        types.append("Weekly Trending")
    if candidate.delta_1d is not None:
        evidence.append(f"实际快照 1 日 Stars 增量 {candidate.delta_1d:+,}")
        types.append("实际 1 日增长")
    if candidate.delta_7d is not None:
        evidence.append(f"实际快照 7 日 Stars 增量 {candidate.delta_7d:+,}")
        types.append("实际 7 日增长")
    if not candidate.daily_rank and not candidate.weekly_rank and not any(
        delta is not None and delta > 0
        for delta in (candidate.delta_1d, candidate.delta_7d)
    ):
        evidence.append(
            f"年龄归一化估算 {candidate.age_speed:,.1f} Stars/天，"
            f"候选中第 {candidate.age_speed_rank} 名"
        )
        types.append("年龄归一化估算")
    return evidence, " / ".join(dict.fromkeys(types))


def _recent_names(today: date) -> set[str]:
    names: set[str] = set()
    for days in range(1, 8):
        path = DATA_DIR / f"{today - timedelta(days=days)}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        names.update(item["full_name"] for item in payload.get("items", []))
    return names


def analyze(
    candidates: Iterable[Candidate],
    today: date,
    *,
    limit: int,
    max_analyzed: int,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    recent = _recent_names(today)
    prepared: list[dict[str, Any]] = []
    attempted = 0
    warnings: list[str] = []

    for candidate in candidates:
        if len(prepared) == limit or attempted >= max_analyzed:
            break
        attempted += 1
        repo = candidate.repo
        try:
            readme = _readme(candidate.full_name)
            if len(readme) < 120:
                raise ValueError("README 有效文本不足 120 字符")
        except Exception as error:  # noqa: BLE001 - skip before analysis selection
            warnings.append(f"跳过 {candidate.full_name}：{error}")
            continue
        evidence, trend_type = _evidence(candidate)
        prepared.append(
            {
                "rank": len(prepared) + 1,
                "full_name": candidate.full_name,
                "name": candidate.full_name,
                "repository_name": repo["name"],
                "url": repo["html_url"],
                "description": str(repo["description"]).strip(),
                "trend_type": trend_type,
                "evidence": evidence,
                "stars": int(repo.get("stargazers_count") or 0),
                "language": repo.get("language") or "未知",
                "topics": repo.get("topics", []),
                "homepage": repo.get("homepage"),
                "license": (repo.get("license") or {}).get("spdx_id") or "未标注",
                "created_at": repo["created_at"],
                "pushed_at": repo["pushed_at"],
                "is_new": candidate.full_name not in recent,
                "daily_trending_rank": candidate.daily_rank,
                "weekly_trending_rank": candidate.weekly_rank,
                "stars_today": candidate.daily_stars,
                "stars_this_week": candidate.weekly_stars,
                "observed_delta_1d": candidate.delta_1d,
                "observed_delta_7d": candidate.delta_7d,
                "observed_growth_rate_1d": candidate.growth_1d,
                "observed_growth_rate_7d": candidate.growth_7d,
                "age_normalized_stars_per_day_estimate": round(candidate.age_speed, 3),
                "age_speed_candidate_rank": candidate.age_speed_rank,
                "ranking_score": round(candidate.score, 4),
                "readme_signal": _short(readme),
                "latest_release": None,
                "_readme_excerpt": readme[:6000],
            }
        )
    if len(prepared) != limit:
        raise RuntimeError(
            f"中文分析前门槛失败：分析尝试 {attempted}，可用 README {len(prepared)}，"
            f"需要 {limit} 条；最后警告：{warnings[-5:]}"
        )

    translator = DescriptionTranslator(cache_path=TRANSLATIONS_PATH)
    translator.enrich(prepared)
    for item in prepared:
        item["analysis_summary_zh"] = _analysis_summary(item)
        summary_length = len(item["analysis_summary_zh"])
        if not 200 <= summary_length <= 500:
            raise RuntimeError(
                f"{item['full_name']} 的中文简介为 {summary_length} 字，不在 200–500 字范围内"
            )
        item.pop("latest_release", None)
        item["name"] = item.pop("repository_name")
    return prepared, attempted, warnings


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _analysis_summary(item: dict[str, Any]) -> str:
    """将 README 分析整理为约 200–500 字、可直接阅读的一段简介。"""
    summary = str(item.get("analysis_summary_zh") or "").strip()
    if summary:
        return summary

    analysis = item.get("analysis_zh") or {}
    positioning = str(analysis.get("positioning") or "").strip()
    description = str(item.get("description_zh") or "").strip()
    implementation = str(analysis.get("implementation") or "").strip()
    problems_solved = str(analysis.get("problems_solved") or "").strip()
    capabilities = str(analysis.get("capabilities") or "").strip()
    use_cases = str(analysis.get("use_cases") or "").strip()
    considerations = str(analysis.get("considerations") or "").strip()
    lead = positioning or description
    parts = [lead.rstrip("。；； ")]
    if implementation:
        parts.append(f"README 显示，{implementation.rstrip('。；； ')}")
    if problems_solved:
        parts.append(f"该项目希望{problems_solved.rstrip('。；； ')}")
    if capabilities:
        parts.append(f"能力覆盖{capabilities.rstrip('。；； ')}")
    if use_cases:
        parts.append(use_cases.rstrip("。；； "))
    if considerations:
        parts.append(f"使用前还应留意{considerations.rstrip('。；； ')}")
    summary = "。".join(part for part in parts if part) + ("。" if parts else "")
    return summary[:500].rsplit("。", 1)[0] + "。" if len(summary) > 500 else summary


def render_report(payload: dict[str, Any]) -> str:
    items = payload["items"]
    metadata = payload["metadata"]
    lines = [
        f"# GitHub 热门增长仓库榜单 · {payload['date']}",
        "",
        (
            f"> 采集时间：{payload['collected_at']}；发现候选 "
            f"{metadata['candidate_count']} 个，深入分析 {metadata['analyzed_count']} 个，"
            f"最终入榜 {len(items)} 个。"
        ),
        "",
        "## 排名与证据说明",
        "",
        (
            "榜单综合 GitHub Daily Trending、Weekly Trending、实际 Stars 历史快照增量，"
            "以及近期仓库的年龄归一化 Stars 速度。真实 1 日/7 日增量仅在快照跨度满足时"
            "展示；其余速度均明确标注为 Trending 页面指标或年龄归一化估算。"
        ),
        "",
        "| 详情 ↘️ | 新增 | 仓库 | 中文简介 | 趋势类型 | 热度/增长证据 | Stars | 主要语言 | 最近推送时间 |",
        "|---:|:---:|---|---|---|---|---:|---|---|",
    ]
    for item in sorted(
        items,
        key=lambda candidate: not bool(candidate.get("is_new")),
    ):
        marker = "🟢" if item["is_new"] else ""
        evidence = "；".join(item["evidence"])
        lines.append(
            f'<a id="project-row-{item["rank"]}"></a>'
            f'[#{item["rank"]} ↘️](#project-detail-{item["rank"]}) | {marker} | '
            f'[{_escape_table(item["full_name"])}]({item["url"]}) | '
            f'{_escape_table(item["description_zh"])} | {_escape_table(item["trend_type"])} | '
            f'{_escape_table(evidence)} | {item["stars"]:,} | '
            f'{_escape_table(item["language"])} | {item["pushed_at"][:10]} |'
        )

    lines.extend(["", "## 项目详情", ""])
    for item in items:
        marker = " 🟢" if item["is_new"] else ""
        lines.extend(
            [
                f'<a id="project-detail-{item["rank"]}"></a>',
                f'### {item["rank"]}. [{item["full_name"]}]({item["url"]}){marker}',
                "",
                f'[↖️ 返回表格中的 #{item["rank"]}](#project-row-{item["rank"]})',
                "",
                "#### 中文分析",
                "",
                _analysis_summary(item),
                "",
            ]
        )
        lines.extend(
            [
                "",
                "#### 项目概况",
                "",
                f'- **仓库**：[{item["full_name"]}]({item["url"]})',
                f'- **Stars**：{item["stars"]:,}',
                f'- **主要语言**：{item["language"]}',
                f'- **Topics**：{"、".join(item["topics"]) if item["topics"] else "未标注"}',
                f'- **许可证**：{item["license"]}',
                f'- **最近推送**：{item["pushed_at"]}',
                "",
                "#### 热度与增长证据",
                "",
            ]
        )
        lines.extend(f"- {evidence}" for evidence in item["evidence"])
        lines.extend(["", "---", ""])
    return "\n".join(lines).rstrip() + "\n"


def _write_outputs(
    today: date,
    candidates: list[Candidate],
    discovery: dict[str, Any],
    *,
    limit: int,
    max_analyzed: int,
) -> dict[str, Any]:
    items, analyzed_count, analysis_warnings = analyze(
        candidates,
        today,
        limit=limit,
        max_analyzed=max_analyzed,
    )
    history = discovery.pop("history")
    history[today.isoformat()] = {
        candidate.full_name: int(candidate.repo.get("stargazers_count") or 0)
        for candidate in candidates
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    history_dates = sorted(history)
    payload = {
        "schema_version": 1,
        "date": today.isoformat(),
        "collected_at": datetime.now(timezone(timedelta(hours=8))).isoformat(
            timespec="seconds"
        ),
        "ranking": {
            "algorithm": (
                "Trending 排名奖励 + 实际快照增长 + 年龄归一化 Stars/天估算 + "
                "累计关注度与最近活跃度"
            ),
            "actual_snapshot_policy": (
                "仅当历史快照日期达到至少 1 天或 7 天跨度时计算对应增量与增长率"
            ),
            "sources": [
                "https://github.com/trending?since=daily",
                "https://github.com/trending?since=weekly",
                "https://api.github.com/search/repositories",
                "data/hot-rising/stars-history.json",
            ],
            "observation_window": {
                "snapshot_first_date": history_dates[0],
                "snapshot_last_date": history_dates[-1],
                "snapshot_coverage_days": (
                    date.fromisoformat(history_dates[-1])
                    - date.fromisoformat(history_dates[0])
                ).days
                + 1,
            },
        },
        "metadata": {
            **discovery,
            "analyzed_count": analyzed_count,
            "ranked_count": len(items),
            "analysis_count": len(items),
            "analysis_warnings": analysis_warnings,
            "daily_trending_ranked": sum(
                bool(item["daily_trending_rank"]) for item in items
            ),
            "weekly_trending_ranked": sum(
                bool(item["weekly_trending_rank"]) for item in items
            ),
            "new_count": sum(bool(item["is_new"]) for item in items),
        },
        "items": items,
    }
    data_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    report_text = render_report(payload)
    (DATA_DIR / f"{today}.json").write_text(data_text, encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(data_text, encoding="utf-8")
    (REPORTS_DIR / f"{today}.md").write_text(report_text, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(report_text, encoding="utf-8")
    return payload


def collect(
    target_date: date | None = None,
    *,
    limit: int = 100,
    max_candidates: int = 1000,
    max_analyzed: int = 600,
) -> dict[str, Any]:
    if limit < 1 or max_candidates < limit or max_analyzed < limit:
        raise ValueError("limit 必须大于 0，且不得超过候选和分析上限")
    today = target_date or datetime.now(timezone(timedelta(hours=8))).date()
    candidates, discovery = discover(
        today,
        max_candidates=max_candidates,
        max_analyzed=max_analyzed,
    )
    return _write_outputs(
        today,
        candidates,
        discovery,
        limit=limit,
        max_analyzed=max_analyzed,
    )
