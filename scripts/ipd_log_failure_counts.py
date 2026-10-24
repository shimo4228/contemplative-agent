#!/usr/bin/env python3
"""Recover failed-move counts for one pre-P3-03.1 IPD run from its run.log.

Bench runs before the counters existed (null-run-1/2, arm A/B, shadow) only left
a log. What a log can still tell:
- "LLM failed to respond, defaulting to COOPERATE" warnings  -> llm_failure_count
  (always logged, exact)
- "LLM response: '...' -> cooperate|defect" DEBUG lines (only if the run used
  -v)                                                         -> parse_fallback_count
  by re-parsing each logged reply with the bench's own parser

Totals per run only (a log does not say which simulation a line belongs to), and
"parse fallbacks: not recoverable" when the log has no DEBUG lines. Never prints
zero for something it cannot see.

Usage: python3 scripts/ipd_log_failure_counts.py RUN.log --bench-src \\
    ../contemplative-agent-rules/benchmarks/prisoners-dilemma/src
"""

import argparse
import ast
import re
import sys
from collections.abc import Callable, Iterable

FAIL = "LLM failed to respond"
RESP = re.compile(r"LLM response: (.*) -> (?:cooperate|defect)\s*$")


def count(lines: Iterable[str], parse_detailed: Callable[[str], tuple]) -> tuple:
    lines = list(lines)  # a file handle is consumed by the first pass
    failures = sum(1 for ln in lines if FAIL in ln)
    replies = []
    for ln in lines:
        m = RESP.search(ln)
        if m:
            try:
                replies.append(ast.literal_eval(m.group(1)))
            except (ValueError, SyntaxError):
                sys.exit(f"ERROR: cannot read a logged reply: {m.group(1)[:80]!r}")
    fallbacks = sum(1 for r in replies if parse_detailed(r)[1]) if replies else None
    return failures, fallbacks, len(replies)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument(
        "--bench-src", required=True, help="prisoners-dilemma/src (provides ipd.llm_player)"
    )
    ns = ap.parse_args()
    sys.path.insert(0, ns.bench_src)
    from ipd.llm_player import _parse_move_detailed  # noqa: PLC0415 (needs --bench-src first)

    with open(ns.log, encoding="utf-8", errors="replace") as f:
        failures, fallbacks, n = count(f, _parse_move_detailed)
    print(f"llm_failure_count: {failures}")
    print(
        f"parse_fallback_count: {fallbacks if fallbacks is not None else 'not recoverable (no DEBUG reply lines; run was not -v)'}"
    )
    print(f"debug_reply_lines: {n}")


if __name__ == "__main__":
    main()
