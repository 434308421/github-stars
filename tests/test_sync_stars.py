from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


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
        return next(self.responses)


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


if __name__ == "__main__":
    unittest.main()
