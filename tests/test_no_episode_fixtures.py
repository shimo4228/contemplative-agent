"""No production-shaped episode file is tracked under tests/ docs/ evals/ config/ (P0-03.11).

An episode log line carries other agents' post text in plain form (``original_post``,
``their_comment``): untrusted external content, and this repo is public. The old
benchmark fixture ``tests/fixtures/benchmark/real_sample.jsonl`` (50 real lines) was
removed; this pins that no file of that shape comes back.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ("tests", "docs", "evals", "config")
FORBIDDEN_KEYS = frozenset({"original_post", "their_comment"})


def _keys(obj: object, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.add(key)
            _keys(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _keys(value, out)


def _json_files() -> list[Path]:
    files: list[Path] = []
    for name in SCAN_DIRS:
        for path in (REPO_ROOT / name).rglob("*"):
            if path.suffix in (".json", ".jsonl") and "__pycache__" not in path.parts:
                files.append(path)
    return sorted(files)


def _keys_of(path: Path) -> set[str]:
    keys: set[str] = set()
    text = path.read_text(encoding="utf-8", errors="replace")
    docs = text.splitlines() if path.suffix == ".jsonl" else [text]
    for chunk in docs:
        if not chunk.strip():
            continue
        try:
            _keys(json.loads(chunk), keys)
        except ValueError:
            continue
    return keys


def test_no_tracked_json_carries_episode_body_keys() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _json_files():
        hit = _keys_of(path) & FORBIDDEN_KEYS
        if hit:
            offenders[str(path.relative_to(REPO_ROOT))] = sorted(hit)
    assert not offenders, f"episode-shaped files in the public tree: {offenders}"


def test_the_scan_sees_a_forbidden_key(tmp_path: Path) -> None:
    """The scan is not vacuous: a fixture with the key is flagged."""
    bad = tmp_path / "x.jsonl"
    bad.write_text('{"type": "interaction", "data": {"their_comment": "hi"}}\n', encoding="utf-8")
    assert _keys_of(bad) & FORBIDDEN_KEYS == {"their_comment"}


def test_untrusted_content_markers_stay_out_of_fixtures() -> None:
    """``<untrusted_content`` in a value means a rendered prompt; docs/evidence/ is exempt."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _json_files()
        if "docs/evidence" not in p.as_posix()
        and "<untrusted_content" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert not offenders, offenders
