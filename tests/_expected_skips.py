"""The expected-skip table (P1-08.2).

A skipped test is a test that did not run, and a green run hides it. Every skip
in a full run is classified by its reason and compared with the set this
platform is expected to produce; an unclassified skip, a category the platform
should not produce, or a count that moved fails the run (exit status 1) with
the offending skips named. The summary is printed on PASS too.

Keyed by ``(sys.platform, os.geteuid() == 0)``. New darwin-only shell tests
need no edit (``darwin`` is unbounded off macOS and zero on it); a new
*kind* of skip must be added to ``CATEGORIES`` and ``EXPECTED`` here.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from collections.abc import Mapping

# category -> reason pattern (first match wins)
CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("darwin", re.compile(r"macOS|darwin|BSD|launchd", re.IGNORECASE)),
    ("chmod", re.compile(r"does not block root")),
    ("ollama", re.compile(r"Ollama embedding model unavailable")),
    # claude: the CLI is absent, or present but the owner has not opted into the
    # one real-model probe (P1-10.15, CONTEMPLATIVE_RUN_CLAUDE_PROBE=1)
    ("claude", re.compile(r"claude CLI not installed|CONTEMPLATIVE_RUN_CLAUDE_PROBE")),
    ("rsync", re.compile(r"rsync not installed")),
    # tests/test_snapshot_resolve.py reads the sibling contemplative-agent-data checkout:
    # absent on the CI runners, present on the maintainer machine
    ("sibling_repo", re.compile(r"sibling data repo not present")),
    # tests/test_packaging_smoke.py and tests/test_readme_quickstart.py: build / install-route
    # tests run only in the packaging CI job
    ("packaging", re.compile(r"CONTEMPLATIVE_PACKAGING|packaging job only")),
    # an xfail that names a known defect it waits on (e.g. P0-05.3 register printing the key)
    ("known_defect", re.compile(r"drop the marker when fixed")),
)

UNBOUNDED = None

# (platform, is_root) -> category -> exact count (None = any number)
# claude / sibling_repo: absent on the CI runners, present on the maintainer machine -> unbounded
_COMMON = {
    "ollama": 1,
    "claude": UNBOUNDED,
    "sibling_repo": UNBOUNDED,
    "packaging": UNBOUNDED,
    "known_defect": UNBOUNDED,
}
EXPECTED: Mapping[tuple[str, bool], Mapping[str, int | None]] = {
    ("linux", True): {**_COMMON, "darwin": UNBOUNDED, "chmod": 10},
    ("linux", False): {**_COMMON, "darwin": UNBOUNDED},
    ("darwin", True): {**_COMMON, "chmod": 10},
    ("darwin", False): dict(_COMMON),
}


def classify(reason: str) -> str:
    for name, pattern in CATEGORIES:
        if pattern.search(reason):
            return name
    return "unclassified"


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def compare(skips: list[tuple[str, str]], platform: str, root: bool) -> list[str]:
    """Problems between the observed ``(nodeid, reason)`` skips and the table."""
    expected = EXPECTED.get((platform, root))
    if expected is None:
        return [f"no expected-skip row for platform={platform!r} root={root}"]
    seen: Counter[str] = Counter()
    by_cat: dict[str, list[str]] = {}
    for nodeid, reason in skips:
        cat = classify(reason)
        seen[cat] += 1
        by_cat.setdefault(cat, []).append(nodeid)
    problems = []
    for cat, count in sorted(seen.items()):
        if cat not in expected:
            problems.append(f"unexpected skip category {cat!r} x{count}: {by_cat[cat][:3]}")
        elif expected[cat] is not None and expected[cat] != count:
            problems.append(f"skip category {cat!r}: expected {expected[cat]}, saw {count}")
    for cat, count in expected.items():
        if count and seen[cat] == 0:
            problems.append(f"skip category {cat!r}: expected {count}, saw 0")
    return problems


def platform() -> str:
    return sys.platform
