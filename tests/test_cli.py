from __future__ import annotations

import unittest

from cross_platform_trending.cli import build_parser


class CliDefaultsTests(unittest.TestCase):
    def test_defaults_to_top_100(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.limit, 100)
        self.assertEqual(args.max_candidates, 1000)


if __name__ == "__main__":
    unittest.main()
