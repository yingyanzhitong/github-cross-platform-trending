from __future__ import annotations

import base64
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
TRENDING_URL = "https://github.com/trending?since=daily"
USER_AGENT = "github-cross-platform-trending/0.5"

SEARCH_QUERIES = (
    "topic:desktop-app archived:false stars:>=100 pushed:>={recent}",
    "topic:cross-platform archived:false stars:>=100 pushed:>={recent}",
    "topic:macos topic:windows archived:false stars:>=20 pushed:>={recent}",
    "topic:electron archived:false stars:>=200 pushed:>={recent}",
    "topic:tauri archived:false stars:>=100 pushed:>={recent}",
    "topic:cli archived:false stars:>=500 pushed:>={recent}",
    "topic:terminal archived:false stars:>=500 pushed:>={recent}",
    "topic:productivity archived:false stars:>=500 pushed:>={recent}",
    "topic:note-taking archived:false stars:>=100 pushed:>={recent}",
    "topic:music-player archived:false stars:>=100 pushed:>={recent}",
    "topic:download-manager archived:false stars:>=100 pushed:>={recent}",
    "topic:editor archived:false stars:>=500 pushed:>={recent}",
    "topic:developer-tools archived:false stars:>=500 pushed:>={recent}",
    "topic:remote-desktop archived:false stars:>=100 pushed:>={recent}",
)

APP_TOPICS = {
    "app",
    "cli",
    "command-line",
    "desktop",
    "desktop-app",
    "developer-tools",
    "editor",
    "ide",
    "music-player",
    "productivity",
    "self-hosted",
    "shell",
    "software",
    "terminal",
    "tool",
    "tools",
}

EXCLUDED_TOPICS = {
    "algorithm",
    "awesome",
    "awesome-list",
    "boilerplate",
    "component-library",
    "course",
    "dataset",
    "documentation",
    "framework",
    "interview",
    "library",
    "manual",
    "template",
    "tutorial",
}

SOFTWARE_PATTERN = re.compile(
    r"\b(app|application|assistant|client|companion|desktop|editor|ide|"
    r"manager|player|self-hosted|server|shell|software|terminal|tool)\b|"
    r"command[- ]line",
    re.IGNORECASE,
)

NON_SOFTWARE_PATTERN = re.compile(
    r"\b(framework|library|sdk|template|boilerplate|cheatsheets?)\b|"
    r"\bbuild(?:ing)?\b.{0,120}\b(?:apps?|applications?)\b",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    repository: dict[str, Any]
    trending_rank: int | None = None
    stars_today: int = 0


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: int = 20):
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.timeout = timeout

    def _request(self, url: str, accept: str) -> bytes | None:
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for attempt in range(3):
            try:
                request = Request(url, headers=headers)
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as error:
                if error.code == 404:
                    return None
                if error.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                detail = error.read().decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"GitHub 请求失败 ({error.code}): {detail}") from error
            except URLError as error:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"网络请求失败: {error.reason}") from error
        return None

    def get_json(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        body = self._request(
            f"{GITHUB_API}{path}{query}",
            "application/vnd.github+json",
        )
        return json.loads(body) if body else None

    def get_text(self, url: str) -> str:
        body = self._request(url, "text/html,application/xhtml+xml")
        return body.decode("utf-8", errors="replace") if body else ""

    def repository(self, full_name: str) -> dict[str, Any] | None:
        return self.get_json(f"/repos/{quote(full_name, safe='/')}")

    def latest_release(self, full_name: str) -> dict[str, Any] | None:
        return self.get_json(
            f"/repos/{quote(full_name, safe='/')}/releases/latest"
        )

    def readme_excerpt(self, full_name: str, max_chars: int = 2000) -> str:
        payload = self.get_json(f"/repos/{quote(full_name, safe='/')}/readme")
        if not payload or payload.get("encoding") != "base64":
            return ""
        try:
            markdown = base64.b64decode(payload.get("content", "")).decode(
                "utf-8",
                errors="replace",
            )
        except (TypeError, ValueError):
            return ""
        markdown = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
        markdown = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", markdown)
        markdown = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
        markdown = re.sub(r"<[^>]+>", " ", markdown)
        markdown = re.sub(r"[#>*_`~=-]+", " ", markdown)
        return re.sub(r"\s+", " ", markdown).strip()[:max_chars]

    def search(self, query: str, per_page: int = 100) -> list[dict[str, Any]]:
        result = self.get_json(
            "/search/repositories",
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
            },
        )
        return result.get("items", []) if result else []


def parse_trending(html: str) -> list[tuple[str, int]]:
    """从 GitHub Trending 页面提取仓库名与今日新增 Star。"""
    repositories: list[tuple[str, int]] = []
    articles = re.findall(
        r'<article[^>]*class="[^"]*\bBox-row\b[^"]*"[^>]*>(.*?)</article>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for article in articles:
        heading = re.search(
            r"<h2\b.*?</h2>",
            article,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not heading:
            continue
        match = re.search(
            r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"',
            heading.group(0),
        )
        if not match:
            continue
        stars = re.search(
            r"([\d,]+)\s+stars?\s+today",
            unescape(re.sub(r"<[^>]+>", " ", article)),
            flags=re.IGNORECASE,
        )
        repositories.append(
            (match.group(1), int(stars.group(1).replace(",", "")) if stars else 0)
        )
    return repositories


def _release_evidence(release: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    macos: list[str] = []
    windows: list[str] = []
    for asset in (release or {}).get("assets", []):
        name = str(asset.get("name", ""))
        lower = name.lower()
        is_macos_pkg = lower.endswith(".pkg") and bool(
            re.search(
                r"(?:^|[-_.])(?:mac(?:os)?|osx|darwin|apple)(?:[-_.]|$)",
                lower,
            )
        )
        if lower.endswith(".dmg") or is_macos_pkg:
            macos.append(f"Release: {name}")
        if re.search(r"\.(?:exe|msi|msix)$", lower):
            windows.append(f"Release: {name}")
    return macos[:3], windows[:3]


def classify_repository(
    repository: dict[str, Any],
    release: dict[str, Any] | None,
) -> tuple[bool, list[str], list[str]]:
    """判断仓库是否是同时支持 macOS 与 Windows 的软件。"""
    release_macos, release_windows = _release_evidence(release)
    macos = release_macos[:5]
    windows = release_windows[:5]
    if not macos or not windows:
        return False, macos, windows

    topics = {str(topic).lower() for topic in repository.get("topics", [])}
    name = str(repository.get("name", "")).lower()
    description = str(repository.get("description") or "")
    has_release_pair = bool(release_macos and release_windows)
    excluded = (
        bool(topics & EXCLUDED_TOPICS)
        or any(
            topic.endswith(("-framework", "-library", "-package"))
            for topic in topics
        )
        or name.startswith("awesome-")
        or bool(NON_SOFTWARE_PATTERN.search(description))
    )
    positive = bool(topics & APP_TOPICS) or bool(SOFTWARE_PATTERN.search(description))

    accepted = has_release_pair and not excluded and positive
    return accepted, macos, windows


def _candidate_score(candidate: Candidate) -> float:
    repository = candidate.repository
    stars = int(repository.get("stargazers_count") or 0)
    if candidate.trending_rank is not None:
        return (
            10_000
            - candidate.trending_rank * 100
            + math.log1p(candidate.stars_today) * 20
        )

    pushed_at = repository.get("pushed_at")
    freshness = 0.0
    if pushed_at:
        pushed = datetime.fromisoformat(str(pushed_at).replace("Z", "+00:00"))
        age_days = max(0.0, (datetime.now(timezone.utc) - pushed).total_seconds() / 86400)
        freshness = max(0.0, 100 - age_days * 4)
    return math.log10(stars + 1) * 100 + freshness


def _analyze_candidate(
    client: GitHubClient,
    candidate: Candidate,
) -> dict[str, Any] | None:
    repository = candidate.repository
    full_name = str(repository["full_name"])
    release = client.latest_release(full_name)
    release_macos, release_windows = _release_evidence(release)
    if not release_macos or not release_windows:
        return None
    accepted, macos, windows = classify_repository(
        repository,
        release,
    )
    if not accepted:
        return None

    latest_release = None
    if release:
        latest_release = {
            "tag": release.get("tag_name"),
            "url": release.get("html_url"),
            "published_at": release.get("published_at"),
        }

    return {
        "name": full_name,
        "url": repository.get("html_url"),
        "description": str(repository.get("description") or "").strip() or "暂无项目简介",
        "homepage": repository.get("homepage") or None,
        "language": repository.get("language") or "未知",
        "topics": repository.get("topics", []),
        "license": (repository.get("license") or {}).get("spdx_id") or None,
        "created_at": repository.get("created_at"),
        "stars": int(repository.get("stargazers_count") or 0),
        "forks": int(repository.get("forks_count") or 0),
        "stars_today": candidate.stars_today,
        "trending_rank": candidate.trending_rank,
        "pushed_at": repository.get("pushed_at"),
        "latest_release": latest_release,
        "platform_evidence": {"macos": macos, "windows": windows},
        "score": round(_candidate_score(candidate), 2),
    }


def discover_candidates(
    client: GitHubClient,
    *,
    recent_days: int = 30,
    search_per_query: int = 100,
) -> tuple[list[Candidate], list[str]]:
    warnings: list[str] = []
    candidates: dict[str, Candidate] = {}

    try:
        trending = parse_trending(client.get_text(TRENDING_URL))
    except RuntimeError as error:
        trending = []
        warnings.append(f"Trending 页面读取失败：{error}")

    def load_trending(item: tuple[int, tuple[str, int]]) -> Candidate | None:
        rank, (full_name, stars_today) = item
        repository = client.repository(full_name)
        return Candidate(repository, rank, stars_today) if repository else None

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(load_trending, item)
            for item in enumerate(trending, start=1)
        ]
        for future in as_completed(futures):
            try:
                candidate = future.result()
                if candidate:
                    candidates[str(candidate.repository["full_name"])] = candidate
            except RuntimeError as error:
                warnings.append(f"Trending 仓库详情读取失败：{error}")

    recent = (date.today() - timedelta(days=recent_days)).isoformat()
    for template in SEARCH_QUERIES:
        query = template.format(recent=recent)
        try:
            for repository in client.search(query, search_per_query):
                full_name = str(repository["full_name"])
                candidates.setdefault(full_name, Candidate(repository))
        except RuntimeError as error:
            warnings.append(f"搜索查询失败（{query}）：{error}")

    return list(candidates.values()), warnings


def collect(
    client: GitHubClient,
    *,
    limit: int = 100,
    max_candidates: int = 1000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates, warnings = discover_candidates(client)
    candidates.sort(key=_candidate_score, reverse=True)
    candidates = candidates[:max_candidates]

    software: list[dict[str, Any]] = []
    analyzed_count = 0
    batch_size = max(100, min(200, limit * 2))
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        analyzed_count += len(batch)
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_map = {
                executor.submit(_analyze_candidate, client, candidate): candidate
                for candidate in batch
            }
            for future in as_completed(future_map):
                candidate = future_map[future]
                try:
                    result = future.result()
                    if result:
                        software.append(result)
                except RuntimeError as error:
                    warnings.append(
                        f"{candidate.repository.get('full_name')} 分析失败：{error}"
                    )
        if len(software) >= limit:
            break

    software.sort(key=lambda item: (-float(item["score"]), item["name"].lower()))
    software = software[:limit]
    for rank, item in enumerate(software, start=1):
        item["rank"] = rank

    metadata = {
        "candidate_count": analyzed_count,
        "discovered_count": len(candidates),
        "matched_count": len(software),
        "warnings": warnings,
    }
    return software, metadata


def enrich_readme_context(
    client: GitHubClient,
    software: list[dict[str, Any]],
) -> list[str]:
    """为最终入榜项目补充仅用于详情分析的 README 摘要。"""
    failures: list[str] = []

    def load(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
        return item, client.readme_excerpt(item["name"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(load, item): item for item in software}
        for future in as_completed(futures):
            item = futures[future]
            try:
                target, excerpt = future.result()
                target["_readme_excerpt"] = excerpt
            except RuntimeError:
                item["_readme_excerpt"] = ""
                failures.append(item["name"])

    if failures:
        return [
            f"{len(failures)} 个项目的 README 读取失败，详情分析已改用仓库元数据"
        ]
    return []
