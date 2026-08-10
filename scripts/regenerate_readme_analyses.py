from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from cross_platform_trending.report import render_markdown
from cross_platform_trending.translator import DescriptionTranslator
from github_hot_rising.collector import render_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = Path("/tmp/github-trending-readme-analyses.json")
PILOT_NAMES = (
    "TencentCloud/TencentDB-Agent-Memory",
    "esengine/DeepSeek-Reasonix",
    "google/skills",
    "rustdesk/rustdesk",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _dated_jsons(directory: Path) -> list[Path]:
    return sorted(directory.glob("20??-??-??.json"))


def _all_data_paths() -> tuple[list[Path], list[Path]]:
    cross = _dated_jsons(ROOT / "data") + [ROOT / "data" / "latest.json"]
    hot_dir = ROOT / "data" / "hot-rising"
    hot = _dated_jsons(hot_dir) + [hot_dir / "latest.json"]
    return cross, hot


def _source(item: dict[str, Any], *, hot: bool) -> dict[str, Any]:
    name = str(item.get("full_name") if hot else item.get("name"))
    description_en = str(
        item.get("description_en") or item.get("description") or ""
    )
    return {
        "name": name,
        "description_en": description_en,
        "description_zh": str(item.get("description_zh") or ""),
        "language": item.get("language") or "未知",
        "topics": item.get("topics", [])[:12],
        "homepage": item.get("homepage"),
        "license": item.get("license"),
        "latest_release": item.get("latest_release"),
    }


def _repository_sources() -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    cross_paths, hot_paths = _all_data_paths()
    for path in cross_paths:
        for item in _json(path).get("software", []):
            source = _source(item, hot=False)
            sources[source["name"]] = source
    for path in hot_paths:
        for item in _json(path).get("items", []):
            source = _source(item, hot=True)
            previous = sources.get(source["name"], {})
            sources[source["name"]] = {
                key: value or previous.get(key)
                for key, value in source.items()
            }
    return sources


def _clean_readme(markdown: str, max_chars: int = 9000) -> str:
    text = re.sub(r"<!--.*?-->", " ", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"```[^\n]*\n", " ", text)
    text = text.replace("```", " ")
    text = re.sub(r"^[ \t]*[#>*|=-]+[ \t]*", " ", text, flags=re.M)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _readme(name: str) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{name}/readme"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise RuntimeError(f"{name} README 获取失败：{detail[-1] if detail else '未知错误'}")
    payload = json.loads(result.stdout)
    if payload.get("encoding") != "base64" or not payload.get("content"):
        raise RuntimeError(f"{name} README 内容为空")
    markdown = base64.b64decode(payload["content"]).decode(
        "utf-8", errors="replace"
    )
    cleaned = _clean_readme(markdown)
    if len(cleaned) < 80:
        raise RuntimeError(f"{name} README 有效文本不足 80 字")
    return cleaned


def _load_checkpoint(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = _json(path)
    return {
        str(name): str(analysis)
        for name, analysis in payload.get("analyses", {}).items()
    }


def _save_checkpoint(path: Path, analyses: dict[str, str]) -> None:
    _write_json(path, {"analyses": dict(sorted(analyses.items()))})


def _generate_batch(items: list[dict[str, Any]]) -> dict[str, str]:
    translator = DescriptionTranslator(
        cache_path=Path("/tmp/unused-readme-analysis-cache.json"),
        timeout=300,
    )
    return translator._request_analyses(items)


def _generate(
    sources: dict[str, dict[str, Any]],
    names: list[str],
    checkpoint_path: Path,
    *,
    batch_size: int,
    workers: int,
) -> dict[str, str]:
    analyses = _load_checkpoint(checkpoint_path)
    pending_names = [name for name in names if name not in analyses]
    if not pending_names:
        return analyses

    readmes: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(12, workers * 4)) as pool:
        futures = {pool.submit(_readme, name): name for name in pending_names}
        for future in as_completed(futures):
            name = futures[future]
            readmes[name] = future.result()

    items = []
    for name in pending_names:
        source = dict(sources[name])
        source["readme_excerpt"] = readmes[name]
        items.append(source)
    batches = [items[index : index + batch_size] for index in range(0, len(items), batch_size)]

    lock = threading.Lock()
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_generate_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            requested = {str(item["name"]) for item in batch}
            try:
                generated = future.result()
            except Exception as error:  # noqa: BLE001 - 汇总批次错误后统一失败
                errors.append(f"{', '.join(sorted(requested))}: {error}")
                continue
            missing = requested - generated.keys()
            with lock:
                analyses.update(generated)
                _save_checkpoint(checkpoint_path, analyses)
            if generated:
                print(
                    f"已生成 {len(analyses)}/{len(names)}："
                    f"{', '.join(sorted(generated))}",
                    flush=True,
                )
            if missing:
                errors.append(
                    f"{', '.join(sorted(missing))}: "
                    "生成结果未通过长度、文风或 README 证据校验"
                )

    if errors:
        raise RuntimeError("\n".join(errors))
    return analyses


def _apply_to_data(analyses: dict[str, str]) -> tuple[int, int]:
    cross_paths, hot_paths = _all_data_paths()
    cross_count = 0
    hot_count = 0
    for path in cross_paths:
        payload = _json(path)
        for item in payload.get("software", []):
            analysis = analyses[str(item["name"])]
            item["analysis_zh"] = analysis
            item["analysis_summary_zh"] = analysis
            cross_count += 1
        _write_json(path, payload)
        report_name = "latest.md" if path.name == "latest.json" else f"{payload['date']}.md"
        report = render_markdown(
            payload["date"],
            payload["software"],
            payload,
            payload["generated_at"],
        )
        (ROOT / "reports" / report_name).write_text(report, encoding="utf-8")

    for path in hot_paths:
        payload = _json(path)
        for item in payload.get("items", []):
            analysis = analyses[str(item["full_name"])]
            item["analysis_zh"] = analysis
            item["analysis_summary_zh"] = analysis
            hot_count += 1
        _write_json(path, payload)
        report_name = "latest.md" if path.name == "latest.json" else f"{payload['date']}.md"
        (ROOT / "reports" / "hot-rising" / report_name).write_text(
            render_report(payload), encoding="utf-8"
        )
    return cross_count, hot_count


def _apply_to_caches(analyses: dict[str, str]) -> int:
    count = 0
    paths = (
        ROOT / "data" / "translations.json",
        ROOT / "data" / "hot-rising" / "translations.json",
    )
    for path in paths:
        payload = _json(path)
        translations = payload.setdefault("translations", {})
        for name, analysis in analyses.items():
            if name not in translations:
                continue
            translations[name]["analysis_zh"] = analysis
            count += 1
        _write_json(path, payload)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按各仓库 README 重新生成 200–1000 字中文介绍"
    )
    parser.add_argument("--pilot", action="store_true", help="只试写四个代表仓库")
    parser.add_argument("--names", nargs="*", help="只生成指定 owner/repository")
    parser.add_argument("--apply", action="store_true", help="回填全部历史数据与报告")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    args = parser.parse_args()

    sources = _repository_sources()
    if args.pilot:
        names = list(PILOT_NAMES)
    elif args.names:
        names = args.names
    else:
        names = sorted(sources)
    unknown = sorted(set(names) - sources.keys())
    if unknown:
        raise RuntimeError(f"历史数据中不存在：{', '.join(unknown)}")

    analyses = _generate(
        sources,
        names,
        args.checkpoint,
        batch_size=args.batch_size,
        workers=args.workers,
    )
    selected = {name: analyses[name] for name in names}
    if not args.apply:
        print(json.dumps(selected, ensure_ascii=False, indent=2))
        return
    if set(names) != set(sources):
        raise RuntimeError("--apply 只能在全部历史仓库均已生成时使用")
    cross_count, hot_count = _apply_to_data(selected)
    cache_count = _apply_to_caches(selected)
    print(
        f"已回填跨平台记录 {cross_count} 条、热门增长记录 {hot_count} 条、缓存 {cache_count} 条。"
    )


if __name__ == "__main__":
    main()
