#!/usr/bin/env python3
"""Synchronize a GitHub user's public starred repositories."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
START_MARKER = "<!-- stars:start -->"
END_MARKER = "<!-- stars:end -->"
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


class SyncError(RuntimeError):
    """Raised when synchronization cannot safely continue."""


def _next_link(link_header: str | None) -> str | None:
    """Return the URL marked rel=next in an RFC 8288 Link header."""
    if not link_header:
        return None

    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"', part)
        if match and "next" in match.group(2).split():
            return match.group(1)
    return None


def _request_json(
    url: str,
    token: str | None,
    *,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    attempts: int = 3,
) -> tuple[Any, Any]:
    headers = {
        "Accept": "application/vnd.github.star+json",
        "User-Agent": "github-stars-sync/1.0",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload, response.headers
        except HTTPError as exc:
            last_error = exc
            if exc.code not in TRANSIENT_HTTP_CODES or attempt == attempts - 1:
                raise SyncError(
                    f"GitHub API request failed with HTTP {exc.code}."
                ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise SyncError(f"GitHub API request failed: {exc}") from exc

        sleeper(2**attempt)

    raise SyncError(f"GitHub API request failed: {last_error}")


def fetch_starred(
    username: str,
    token: str | None = None,
    *,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Fetch every page of starred repositories for a public GitHub user."""
    encoded_username = quote(username, safe="")
    next_url: str | None = (
        f"{API_BASE_URL}/users/{encoded_username}/starred?per_page=100&page=1"
    )
    seen_urls: set[str] = set()
    entries: list[dict[str, Any]] = []

    while next_url:
        if next_url in seen_urls:
            raise SyncError("GitHub API returned a pagination loop.")
        seen_urls.add(next_url)

        payload, headers = _request_json(
            next_url,
            token,
            opener=opener,
            sleeper=sleeper,
        )
        if not isinstance(payload, list):
            raise SyncError("GitHub API returned an unexpected response shape.")
        if not all(isinstance(entry, dict) for entry in payload):
            raise SyncError("GitHub API returned an invalid repository entry.")

        entries.extend(payload)
        next_url = _next_link(headers.get("Link"))

    return entries


def _license_identifier(repo: dict[str, Any]) -> str | None:
    license_info = repo.get("license")
    if not isinstance(license_info, dict):
        return None

    spdx_id = license_info.get("spdx_id")
    if spdx_id and spdx_id != "NOASSERTION":
        return str(spdx_id)
    name = license_info.get("name")
    return str(name) if name else None


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Reduce an API entry to stable fields used by this repository."""
    repo = entry.get("repo", entry)
    if not isinstance(repo, dict) or not repo.get("full_name"):
        raise SyncError("A starred repository is missing its full_name.")

    topics = repo.get("topics")
    normalized_topics = (
        sorted((str(topic) for topic in topics), key=str.casefold)
        if isinstance(topics, list)
        else []
    )

    return {
        "repository_id": repo.get("id"),
        "full_name": str(repo["full_name"]),
        "html_url": str(
            repo.get("html_url") or f"https://github.com/{repo['full_name']}"
        ),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "topics": normalized_topics,
        "license": _license_identifier(repo),
        "archived": bool(repo.get("archived", False)),
        "fork": bool(repo.get("fork", False)),
        "starred_at": entry.get("starred_at"),
        "pushed_at": repo.get("pushed_at"),
    }


def build_snapshot(username: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    stars = [normalize_entry(entry) for entry in entries]
    stars.sort(key=lambda item: item["full_name"].casefold())
    stars.sort(key=lambda item: item.get("starred_at") or "", reverse=True)
    return {
        "schema_version": 1,
        "owner": username,
        "count": len(stars),
        "stars": stars,
    }


def _markdown_text(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    text = " ".join(str(value).replace("\r", "\n").splitlines())
    return html.escape(text, quote=False).replace("|", "\\|")


def render_stars_section(snapshot: dict[str, Any]) -> str:
    stars = snapshot["stars"]
    lines = [
        f"当前收录 **{len(stars)}** 个公开 Star 仓库，按 Star 时间倒序排列。",
        "",
        "> 本区域由 GitHub Actions 自动生成，请勿手动编辑。",
    ]

    if not stars:
        lines.extend(["", "尚未同步到 Star 数据。"])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "| Star 日期 | 仓库 | 简介 | 语言 | Topics | License |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for star in stars:
        starred_at = star.get("starred_at") or ""
        starred_date = starred_at[:10] if starred_at else "—"
        name = _markdown_text(star["full_name"])
        if star.get("archived"):
            name += "（已归档）"
        repository = f"[{name}]({star['html_url']})"
        topics = ", ".join(
            f"`{_markdown_text(topic)}`" for topic in star.get("topics", [])
        ) or "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    starred_date,
                    repository,
                    _markdown_text(star.get("description")),
                    _markdown_text(star.get("language")),
                    topics,
                    _markdown_text(star.get("license")),
                ]
            )
            + " |"
        )

    return "\n".join(lines)


def replace_generated_section(readme: str, generated: str) -> str:
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise SyncError("README markers are missing or duplicated.")

    start_index = readme.index(START_MARKER) + len(START_MARKER)
    end_index = readme.index(END_MARKER)
    if start_index >= end_index:
        raise SyncError("README markers are in the wrong order.")

    return (
        readme[:start_index]
        + "\n"
        + generated.rstrip()
        + "\n"
        + readme[end_index:]
    )


def write_text_if_changed(path: Path, content: str) -> bool:
    normalized = content.rstrip() + "\n"
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == normalized:
        return False
    path.write_text(normalized, encoding="utf-8", newline="\n")
    return True


def synchronize(
    username: str,
    token: str | None,
    stars_path: Path,
    readme_path: Path,
) -> dict[str, Any]:
    entries = fetch_starred(username, token)
    snapshot = build_snapshot(username, entries)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"

    readme = readme_path.read_text(encoding="utf-8")
    rendered_readme = replace_generated_section(
        readme, render_stars_section(snapshot)
    )

    stars_changed = write_text_if_changed(stars_path, snapshot_text)
    readme_changed = write_text_if_changed(readme_path, rendered_readme)
    return {
        "owner": username,
        "count": snapshot["count"],
        "stars_json_changed": stars_changed,
        "readme_changed": readme_changed,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize public GitHub stars into JSON and Markdown."
    )
    parser.add_argument("--username", required=True, help="GitHub username")
    parser.add_argument(
        "--stars-file", type=Path, default=Path("stars.json"), help="JSON output"
    )
    parser.add_argument(
        "--readme", type=Path, default=Path("README.md"), help="README path"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = synchronize(
            username=args.username,
            token=os.environ.get("GITHUB_TOKEN"),
            stars_path=args.stars_file,
            readme_path=args.readme,
        )
    except (OSError, SyncError) as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
