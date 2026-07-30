from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_REPOSITORY = "yingyanzhitong/github-cross-platform-trending-pages"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def sync_pages(source_dir: Path, repository: str, message: str) -> str | None:
    if not (source_dir / "index.html").exists():
        raise FileNotFoundError(f"站点尚未构建：{source_dir / 'index.html'}")

    with tempfile.TemporaryDirectory(prefix="cross-platform-pages-") as directory:
        checkout = Path(directory) / "site"
        _run(
            "git",
            "clone",
            f"https://github.com/{repository}.git",
            str(checkout),
        )
        for child in checkout.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(source_dir, checkout, dirs_exist_ok=True)
        _run("git", "add", "-A", cwd=checkout)
        changed = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=checkout,
            check=False,
        ).returncode
        if changed == 0:
            return None

        _run("git", "config", "user.name", "masongzhi", cwd=checkout)
        _run("git", "config", "user.email", "masongzhi@bigo.sg", cwd=checkout)
        _run("git", "commit", "-m", message, cwd=checkout)
        _run("git", "push", "origin", "main", cwd=checkout)
        return _run("git", "rev-parse", "HEAD", cwd=checkout).stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步静态站点到公开 Pages 仓库")
    parser.add_argument("--source-dir", type=Path, default=Path("docs"))
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--message", default="chore: 同步跨平台软件日报")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    commit = sync_pages(args.source_dir, args.repository, args.message)
    if commit:
        print(f"Pages 仓库已更新：{commit}")
    else:
        print("Pages 仓库内容没有变化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
