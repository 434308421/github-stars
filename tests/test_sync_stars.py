from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sync_stars  # noqa: E402


class FakeResponse:
    def __init__(self, payload, link=None):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = {"Link": link} if link else {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def api_entry(name, starred_at, **overrides):
    repo = {
        "id": 1,
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": "Example repository",
        "language": "Python",
        "topics": ["automation", "github"],
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "archived": False,
        "fork": False,
        "pushed_at": "2026-07-14T00:00:00Z",
    }
    repo.update(overrides)
    return {"starred_at": starred_at, "repo": repo}


class FetchStarredTests(unittest.TestCase):
    def test_fetches_all_pages_and_sends_expected_headers(self):
        page_two = (
            "https://api.github.com/users/434308421/starred?per_page=100&page=2"
        )
        opener = FakeOpener(
            [
                FakeResponse(
                    [api_entry("owner/first", "2026-07-15T00:00:00Z")],
                    f'<{page_two}>; rel="next"',
                ),
                FakeResponse([api_entry("owner/second", "2026-07-14T00:00:00Z")]),
            ]
        )

        result = sync_stars.fetch_starred(
            "434308421", "test-token", opener=opener, sleeper=lambda _: None
        )

        self.assertEqual(2, len(result))
        self.assertEqual(2, len(opener.requests))
        first_request, timeout = opener.requests[0]
        self.assertEqual(30, timeout)
        self.assertEqual(
            "application/vnd.github.star+json", first_request.get_header("Accept")
        )
        self.assertEqual("Bearer test-token", first_request.get_header("Authorization"))

    def test_rejects_pagination_urls_outside_github_api(self):
        opener = FakeOpener(
            [
                FakeResponse([], '<https://example.invalid/next>; rel="next"'),
                FakeResponse([]),
            ]
        )

        with self.assertRaises(sync_stars.SyncError):
            sync_stars.fetch_starred(
                "434308421",
                "test-token",
                opener=opener,
                sleeper=lambda _: None,
            )

        self.assertEqual(1, len(opener.requests))

    def test_retries_transient_github_api_errors(self):
        transient_error = HTTPError(
            url="https://api.github.com/users/434308421/starred",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )
        opener = FakeOpener([transient_error, FakeResponse([])])
        delays = []

        result = sync_stars.fetch_starred(
            "434308421",
            "test-token",
            opener=opener,
            sleeper=delays.append,
        )

        self.assertEqual([], result)
        self.assertEqual(2, len(opener.requests))
        self.assertEqual([1], delays)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_stable_and_sorted_by_star_time(self):
        entries = [
            api_entry("owner/older", "2026-07-14T00:00:00Z"),
            api_entry("owner/newer", "2026-07-15T00:00:00Z"),
        ]

        snapshot = sync_stars.build_snapshot("434308421", entries)

        self.assertEqual(2, snapshot["count"])
        self.assertEqual("owner/newer", snapshot["stars"][0]["full_name"])
        self.assertNotIn("synced_at", snapshot)
        self.assertNotIn("stargazers_count", snapshot["stars"][0])
        self.assertNotIn("pushed_at", snapshot["stars"][0])

    def test_render_escapes_table_content_and_marks_archived_repository(self):
        entry = api_entry(
            "owner/repo",
            "2026-07-15T00:00:00Z",
            description="A | B",
            archived=True,
        )
        snapshot = sync_stars.build_snapshot("434308421", [entry])

        rendered = sync_stars.render_stars_section(snapshot)

        self.assertIn("A \\| B", rendered)
        self.assertIn("owner/repo（已归档）", rendered)
        self.assertIn("2026-07-15", rendered)


class FileUpdateTests(unittest.TestCase):
    def test_replaces_only_the_generated_readme_section(self):
        original = (
            "# Header\n\n"
            f"{sync_stars.START_MARKER}\nold\n{sync_stars.END_MARKER}\n\nFooter\n"
        )

        updated = sync_stars.replace_generated_section(original, "new")

        self.assertEqual(
            "# Header\n\n"
            f"{sync_stars.START_MARKER}\nnew\n{sync_stars.END_MARKER}\n\nFooter\n",
            updated,
        )

    def test_write_text_if_changed_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.txt"
            self.assertTrue(sync_stars.write_text_if_changed(path, "same"))
            self.assertFalse(sync_stars.write_text_if_changed(path, "same\n"))

    def test_synchronize_replaces_removed_stars_and_updates_both_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stars_path = root / "stars.json"
            readme_path = root / "README.md"
            stars_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "owner": "434308421",
                        "count": 1,
                        "stars": [{"full_name": "owner/removed"}],
                    }
                ),
                encoding="utf-8",
            )
            readme_path.write_text(
                "# Stars\n\n"
                f"{sync_stars.START_MARKER}\nold\n{sync_stars.END_MARKER}\n"
                "\nFooter\n",
                encoding="utf-8",
            )
            current_entries = [
                api_entry("owner/current", "2026-07-15T00:00:00Z")
            ]

            with patch.object(sync_stars, "fetch_starred", return_value=current_entries):
                result = sync_stars.synchronize(
                    "434308421", "test-token", stars_path, readme_path
                )

            snapshot = json.loads(stars_path.read_text(encoding="utf-8"))
            readme = readme_path.read_text(encoding="utf-8")
            repository_names = [star["full_name"] for star in snapshot["stars"]]
            self.assertTrue(result["stars_json_changed"])
            self.assertTrue(result["readme_changed"])
            self.assertEqual(["owner/current"], repository_names)
            self.assertNotIn("owner/removed", readme)
            self.assertIn("owner/current", readme)
            self.assertTrue(readme.endswith("\nFooter\n"))


if __name__ == "__main__":
    unittest.main()
