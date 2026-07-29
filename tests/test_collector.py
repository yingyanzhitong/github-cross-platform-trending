from __future__ import annotations

import unittest

from cross_platform_trending.collector import (
    classify_repository,
    parse_trending,
)


class ParseTrendingTests(unittest.TestCase):
    def test_extracts_repository_and_daily_stars(self) -> None:
        html = """
        <article class="Box-row">
          <h2 class="h3 lh-condensed">
            <a href="/owner/example">owner / example</a>
          </h2>
          <span class="d-inline-block float-sm-right">1,234 stars today</span>
        </article>
        """

        self.assertEqual(parse_trending(html), [("owner/example", 1234)])


class ClassifyRepositoryTests(unittest.TestCase):
    def test_accepts_paired_release_installers(self) -> None:
        repository = {
            "name": "example",
            "description": "A desktop application",
            "topics": [],
        }
        release = {
            "assets": [
                {"name": "example-macos.dmg"},
                {"name": "example-windows.exe"},
            ]
        }

        accepted, macos, windows = classify_repository(
            repository,
            "",
            release,
            is_trending=False,
        )

        self.assertTrue(accepted)
        self.assertIn("Release: example-macos.dmg", macos)
        self.assertIn("Release: example-windows.exe", windows)

    def test_accepts_trending_app_with_readme_evidence(self) -> None:
        repository = {
            "name": "example",
            "description": "A useful desktop app",
            "topics": [],
        }
        readme = "Install this app on macOS with Homebrew, or on Windows with WinGet."

        accepted, _, _ = classify_repository(
            repository,
            readme,
            None,
            is_trending=True,
        )

        self.assertTrue(accepted)

    def test_rejects_library_without_release_pair(self) -> None:
        repository = {
            "name": "example",
            "description": "A cross-platform library",
            "topics": ["library"],
        }
        readme = "This library supports macOS and Windows."

        accepted, _, _ = classify_repository(
            repository,
            readme,
            None,
            is_trending=True,
        )

        self.assertFalse(accepted)

    def test_rejects_framework_even_with_release_pair(self) -> None:
        repository = {
            "name": "example",
            "description": (
                "Build smaller, faster, and more secure desktop and mobile "
                "applications with a web frontend."
            ),
            "topics": ["desktop-app"],
        }
        release = {
            "assets": [
                {"name": "runtime-darwin.zip"},
                {"name": "runtime-win64.zip"},
            ]
        }

        accepted, _, _ = classify_repository(
            repository,
            "",
            release,
            is_trending=False,
        )

        self.assertFalse(accepted)

    def test_rejects_single_platform_project(self) -> None:
        repository = {
            "name": "example",
            "description": "A desktop app",
            "topics": ["desktop-app"],
        }

        accepted, _, windows = classify_repository(
            repository,
            "Download the macOS DMG.",
            None,
            is_trending=True,
        )

        self.assertFalse(accepted)
        self.assertEqual(windows, [])


if __name__ == "__main__":
    unittest.main()
