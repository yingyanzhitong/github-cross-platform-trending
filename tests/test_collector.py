from __future__ import annotations

import base64
import unittest

from cross_platform_trending.collector import (
    GitHubClient,
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


class ReadmeExcerptTests(unittest.TestCase):
    def test_decodes_and_cleans_markdown(self) -> None:
        class StubClient(GitHubClient):
            def get_json(self, path, params=None):
                markdown = (
                    "# Example\n"
                    "[Documentation](https://example.com) for **desktop users**.\n"
                    "```shell\nignored command\n```\n"
                )
                return {
                    "encoding": "base64",
                    "content": base64.b64encode(markdown.encode()).decode(),
                }

        excerpt = StubClient().readme_excerpt("owner/example")

        self.assertEqual(excerpt, "Example Documentation for desktop users .")
        self.assertNotIn("ignored command", excerpt)
        self.assertNotIn("https://", excerpt)


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
            release,
        )

        self.assertTrue(accepted)
        self.assertIn("Release: example-macos.dmg", macos)
        self.assertIn("Release: example-windows.exe", windows)

    def test_rejects_readme_only_platform_evidence(self) -> None:
        repository = {
            "name": "example",
            "description": "A useful desktop app",
            "topics": [],
        }
        accepted, _, _ = classify_repository(
            repository,
            None,
        )

        self.assertFalse(accepted)

    def test_rejects_release_archives_without_installers(self) -> None:
        repository = {
            "name": "example",
            "description": "A useful desktop app",
            "topics": ["desktop-app"],
        }
        release = {
            "assets": [
                {"name": "example-darwin.zip"},
                {"name": "example-windows.zip"},
            ]
        }

        accepted, _, _ = classify_repository(
            repository,
            release,
        )

        self.assertFalse(accepted)

    def test_rejects_freebsd_pkg_as_macos_installer(self) -> None:
        repository = {
            "name": "example",
            "description": "A useful desktop app",
            "topics": ["desktop-app"],
        }
        release = {
            "assets": [
                {"name": "example-FreeBSD-amd64.pkg"},
                {"name": "example-Windows-installer.exe"},
            ]
        }

        accepted, macos, _ = classify_repository(
            repository,
            release,
        )

        self.assertFalse(accepted)
        self.assertEqual(macos, [])

    def test_rejects_library_without_release_pair(self) -> None:
        repository = {
            "name": "example",
            "description": "A cross-platform library",
            "topics": ["library"],
        }
        accepted, _, _ = classify_repository(
            repository,
            None,
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
                {"name": "runtime-macos.dmg"},
                {"name": "runtime-windows.exe"},
            ]
        }

        accepted, _, _ = classify_repository(
            repository,
            release,
        )

        self.assertFalse(accepted)

    def test_rejects_single_platform_project(self) -> None:
        repository = {
            "name": "example",
            "description": "A desktop app",
            "topics": ["desktop-app"],
        }
        release = {"assets": [{"name": "example-macos.dmg"}]}

        accepted, _, windows = classify_repository(
            repository,
            release,
        )

        self.assertFalse(accepted)
        self.assertEqual(windows, [])


if __name__ == "__main__":
    unittest.main()
