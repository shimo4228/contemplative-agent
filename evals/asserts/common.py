"""Shared promptfoo Python assertions for the distill eval suites.

Reuses the production parsing/validation helpers (``strip_code_fence``,
``_is_valid_pattern``) so the assertions judge output exactly the way the
pipeline consumes it — a fence-wrapped JSON object that production accepts
must not fail the eval.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.core._io import strip_code_fence  # noqa: E402
from contemplative_agent.core.distill import _is_valid_pattern  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

_MIN_VALID_PATTERN_RATE = 0.8
_MAX_PATTERNS = 12


def _fail(reason: str) -> dict:
    return {"pass": False, "score": 0.0, "reason": reason}


def assert_refine_output(output: str, context) -> dict:
    """Step 2 contract: {"patterns": [str, ...]}, 1-12 items, mostly valid."""
    try:
        parsed = json.loads(strip_code_fence(output))
    except json.JSONDecodeError as exc:
        return _fail(f"not JSON after fence strip: {exc}")
    if not isinstance(parsed, dict) or "patterns" not in parsed:
        return _fail("missing required key 'patterns'")
    patterns = parsed["patterns"]
    if not isinstance(patterns, list) or not all(
        isinstance(p, str) for p in patterns
    ):
        return _fail("'patterns' is not a list of strings")
    if not 1 <= len(patterns) <= _MAX_PATTERNS:
        return _fail(f"pattern count {len(patterns)} outside 1..{_MAX_PATTERNS}")
    valid = sum(1 for p in patterns if _is_valid_pattern(p.strip()))
    rate = valid / len(patterns)
    return {
        "pass": rate >= _MIN_VALID_PATTERN_RATE,
        "score": rate,
        "reason": f"{valid}/{len(patterns)} patterns pass the production gate",
    }


def assert_importance_output(output: str, context) -> dict:
    """Step 3 contract: {"scores": [int, ...]}, one 1-10 score per pattern."""
    patterns_file = context["vars"]["patterns_file"]
    expected = len(
        [
            line
            for line in (_FIXTURES / patterns_file)
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
    )
    try:
        parsed = json.loads(strip_code_fence(output))
    except json.JSONDecodeError as exc:
        return _fail(f"not JSON after fence strip: {exc}")
    scores = parsed.get("scores") if isinstance(parsed, dict) else None
    if not isinstance(scores, list):
        return _fail("missing required key 'scores'")
    if len(scores) != expected:
        return _fail(f"{len(scores)} scores for {expected} patterns")
    if not all(isinstance(s, int) and 1 <= s <= 10 for s in scores):
        return _fail(f"scores outside 1..10 or non-integer: {scores}")
    return {"pass": True, "score": 1.0, "reason": f"{expected} scores, all in 1..10"}
