"""Backfill truncated fields in episode logs.

Recovers full content from Moltbook API for fields that were truncated
during early development (original_post at 500, content at 200).

Usage:
    uv run python scripts/backfill_truncated_posts.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

LOG_DIR = Path.home() / ".config" / "moltbook" / "logs"
CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "credentials.json"
API_BASE = "https://www.moltbook.com/api/v1"
AGENT_NAME = "contemplative-agent"
REQUEST_INTERVAL = 1.2  # seconds between API calls (stay under 60 req/min)

# Fields to check and their truncation thresholds
TRUNCATION_RULES = {
    "original_post": 490,   # was truncated at 500
    "content": 195,         # was truncated at 200
    "their_comment": 490,   # was truncated at 500
}

# Cache: post_id -> full post content
_post_cache: dict[str, Optional[str]] = {}
# Cache: post_id -> {comment_start: full_comment}
_comment_cache: dict[str, dict[str, str]] = {}


def load_api_key() -> str:
    data = json.loads(CREDENTIALS_PATH.read_text())
    return data["api_key"]


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def fetch_post_content(post_id: str, api_key: str) -> Optional[str]:
    """Fetch full post content from Moltbook API (cached)."""
    if post_id in _post_cache:
        return _post_cache[post_id]

    url = f"{API_BASE}/posts/{post_id}"
    try:
        resp = requests.get(url, headers=_headers(api_key), timeout=30, allow_redirects=False)
        if resp.status_code == 200:
            post = resp.json().get("post", {})
            content = post.get("content", "")
            _post_cache[post_id] = content
            time.sleep(REQUEST_INTERVAL)
            return content
        elif resp.status_code == 404:
            _post_cache[post_id] = None
            time.sleep(REQUEST_INTERVAL)
            return None
        else:
            print(f"    WARNING: GET /posts/{post_id[:12]} returned {resp.status_code}")
            time.sleep(REQUEST_INTERVAL)
            return None
    except requests.RequestException as e:
        print(f"    ERROR: {post_id[:12]}: {e}")
        return None


def fetch_comment_by_prefix(post_id: str, prefix: str, api_key: str) -> Optional[str]:
    """Find full comment text by matching the truncated prefix."""
    if post_id not in _comment_cache:
        url = f"{API_BASE}/posts/{post_id}/comments"
        try:
            resp = requests.get(url, headers=_headers(api_key), timeout=30, allow_redirects=False)
            if resp.status_code == 200:
                comments = resp.json().get("comments", [])
                cache = {}
                for c in comments:
                    content = c.get("content", "")
                    if content:
                        # Index by first 50 chars for prefix matching
                        cache[content[:50]] = content
                _comment_cache[post_id] = cache
            else:
                _comment_cache[post_id] = {}
            time.sleep(REQUEST_INTERVAL)
        except requests.RequestException as e:
            print(f"    ERROR fetching comments for {post_id[:12]}: {e}")
            _comment_cache[post_id] = {}

    # Match by prefix
    cache = _comment_cache.get(post_id, {})
    search_prefix = prefix[:50]
    if search_prefix in cache:
        return cache[search_prefix]

    # Fuzzy: try shorter prefixes
    for key, full in cache.items():
        if full.startswith(prefix[:30]):
            return full
    return None


def process_log_file(log_path: Path, api_key: str) -> tuple[int, int]:
    """Process a single log file. Returns (found, updated) counts."""
    lines = log_path.read_text().splitlines()
    found = 0
    updated = 0
    new_lines = []

    for line in lines:
        record = json.loads(line)
        data = record.get("data", {})
        post_id = data.get("post_id", "")
        changed = False

        for field, threshold in TRUNCATION_RULES.items():
            value = data.get(field, "")
            if not value or not post_id or len(value) < threshold:
                continue

            found += 1

            if field == "original_post":
                full = fetch_post_content(post_id, api_key)
            elif field in ("content", "their_comment"):
                full = fetch_comment_by_prefix(post_id, value, api_key)
            else:
                full = None

            if full and len(full) > len(value):
                data[field] = full
                changed = True
                updated += 1
                print(f"    {field}: {post_id[:12]}... ({len(value)} -> {len(full)} chars)")

        if changed:
            record["data"] = data
        new_lines.append(json.dumps(record, ensure_ascii=False))

    if updated > 0:
        backup_path = log_path.with_suffix(".jsonl.bak")
        if not backup_path.exists():
            log_path.rename(backup_path)
            print(f"  Backed up to {backup_path.name}")
        else:
            print(f"  Backup exists, overwriting log")
        log_path.write_text("\n".join(new_lines) + "\n")

    return found, updated


def count_truncated(log_path: Path) -> dict[str, int]:
    """Count truncated fields in a log file (dry-run mode)."""
    counts: dict[str, int] = {}
    for line in log_path.read_text().splitlines():
        r = json.loads(line)
        d = r.get("data", {})
        for field, threshold in TRUNCATION_RULES.items():
            val = d.get(field, "")
            if val and d.get("post_id") and len(val) >= threshold:
                counts[field] = counts.get(field, 0) + 1
    return counts


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN — no changes will be made\n")
    else:
        api_key = load_api_key()

    log_files = sorted(LOG_DIR.glob("*.jsonl"))
    total_found = 0
    total_updated = 0

    for log_path in log_files:
        if log_path.suffix == ".bak":
            continue
        print(f"\n{log_path.name}:")

        if dry_run:
            counts = count_truncated(log_path)
            for field, count in sorted(counts.items()):
                print(f"  {field}: {count} truncated")
                total_found += count
        else:
            found, updated = process_log_file(log_path, api_key)
            total_found += found
            total_updated += updated
            print(f"  {found} found, {updated} updated")

    print(f"\nTotal: {total_found} truncated, {total_updated} updated")


if __name__ == "__main__":
    main()
