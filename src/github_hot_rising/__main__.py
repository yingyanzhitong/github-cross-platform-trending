from __future__ import annotations

import argparse
import json
from datetime import date

from .collector import collect
from .validator import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 GitHub 热门增长仓库日报")
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--max-analyzed", type=int, default=600)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.validate_only:
        target = args.date or date.today()
        result = validate(target, expected_count=args.limit)
    else:
        payload = collect(
            target_date=args.date,
            limit=args.limit,
            max_candidates=args.max_candidates,
            max_analyzed=args.max_analyzed,
        )
        result = payload["metadata"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
