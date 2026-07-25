#!/usr/bin/env python3
"""Deterministic cross-day duplicate scan over published bodies (read-only).

The third deterministic intake of the weekly report, after the log-anomaly sweep
(event stream) and the state-invariant check (accumulated state). This one covers
*identity between published records*: whether the same body text was published on
more than one day.

Why it exists: the weekly report has now twice asserted a cross-entry fact that
was not in the artifacts (2026-06-15, a "6-day consecutive re-reply" that was six
distinct interlocutors; 2026-07-25, "the first cross-day byte-identical outputs in
the record", which pairs four real entries with an invented occurrence). Every
other claim in the report is single-entry and verifiable by construction against
its source daily report. Only the duplication claim requires comparing entries
across days — and whether two strings are identical is a structural property, so
it belongs to code, not to recall.

Security (load-bearing, ADR-0083): this is the ONLY intake that reads the episode
logs ``YYYY-MM-DD.jsonl``, which carry untrusted external content and are a
prompt-injection vector into the weekly LLM call. The boundary is the *output*,
not the input: nothing leaves this module except

  - SHA-256 digests truncated to 12 hex characters,
  - integer counts,
  - dates taken from the *filenames* (self-controlled), and
  - action names from a fixed vocabulary {post, reply, comment}.

Body text, post ids, counterparty names, internal notes and thinking never appear
in the render. ``tests/test_cross_day_duplicate_scan.py::TestOutputBoundary``
gates this; ``RENDER_CHARSET_RE`` states it as a closed character vocabulary.

Observation only. Hash-equality dedup as an *intervention* is a rejected mechanism
(``config/prompts/principles.md`` appendix) — this scan reports what is there and
never suppresses generation. It holds no state, so unlike the sweep it has no
baseline to spend: every run is an absolute measurement, and a failed weekly run
costs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from _md import md_safe

# Episode-log day files only. `*.bak` never matches (`.jsonl.bak`), and neither
# do the sibling `audit.jsonl` / `skill-usage-*.jsonl`. Explicit [0-9] rather
# than \d: on a str pattern \d is Unicode-aware and admits fullwidth or
# Arabic-Indic digits, which would then be copied from the filename into the
# render. The dates are called self-controlled, so the pattern should enforce
# that structurally instead of relying on who happens to write the directory.
_DAY_FILE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl$")

# The agent's own published output. follow / unfollow / upvote carry no body.
PUBLISHED_ACTIONS = ("post", "reply", "comment")

DIGEST_LEN = 12

# The closed vocabulary the render is built from: ASCII letters and digits, the
# punctuation of the template itself, and the multiplication sign used in the
# action tallies. Nothing derived from body text can widen it — a violation means
# untrusted content found a path into the prompt. (The single footer line, which
# starts with `_`, carries prose punctuation and is excluded when checking.)
RENDER_CHARSET_RE = re.compile(r"[A-Za-z0-9 \n#*:.,()/|`\-_×]*")


@dataclass(frozen=True)
class Published:
    """One published body, reduced to what may cross the boundary."""

    date: str  # from the filename
    action: str  # one of PUBLISHED_ACTIONS
    digest: str  # sha256(content)[:DIGEST_LEN]


@dataclass(frozen=True)
class DuplicateGroup:
    """Bodies sharing a digest, with where and how they were published."""

    digest: str
    count: int
    dates: tuple[str, ...]
    actions: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ScanResult:
    # Day counts are days that carried published output, not day files present:
    # a file with no post/reply/comment contributes nothing to identity, and the
    # denominator of a duplicate reading should be what was actually compared.
    total_bodies: int
    total_days: int
    window_bodies: int
    window_days: int
    cross_day_lifetime: tuple[DuplicateGroup, ...]
    cross_day_window: tuple[DuplicateGroup, ...]
    intra_day_window: tuple[DuplicateGroup, ...]
    skipped: dict[str, int]


def _day_files(log_dir: Path) -> list[Path]:
    """Day files only, symlinks skipped.

    A symlink is refused for the same reason the sweep refuses one: a name that
    matches the allowed pattern could otherwise redirect the reader anywhere.
    Here it would not breach the injection boundary (the output is digests
    either way), but it would silently corrupt the date attribution, which is
    what the whole scan asserts.
    """
    try:
        entries = sorted(log_dir.iterdir())
    except OSError:
        return []
    return [p for p in entries if _DAY_FILE_RE.match(p.name) and not p.is_symlink() and p.is_file()]


def collect(log_dir: Path) -> tuple[list[Published], dict[str, int]]:
    """Read every day file into digests, counting faults by reason.

    Returns ``(bodies, skipped)`` where *skipped* maps a reason code to a count.
    Episode logs are append-only and share a host with launchd kills, so a torn
    final line is an ordinary occurrence, not corruption; it is skipped and
    counted rather than raised, and the count is rendered so the skip is never
    silent.
    """
    bodies: list[Published] = []
    skipped: Counter[str] = Counter()

    for path in _day_files(log_dir):
        date = path.name[: len("YYYY-MM-DD")]
        try:
            raw = path.read_bytes()
        except OSError:
            skipped["unreadable_file"] += 1
            continue

        for raw_line in raw.splitlines():
            if not raw_line.strip():
                continue
            try:
                # Strict, not errors="replace": lossy decoding maps distinct
                # invalid byte sequences onto the same U+FFFD string, which
                # would let two different bodies collide into an invented
                # duplicate. A scan whose purpose is to refuse unsupported
                # identity claims must not manufacture one.
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                skipped["bad_encoding"] += 1
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad_json"] += 1
                continue
            if not isinstance(record, dict):
                skipped["bad_shape"] += 1
                continue
            if record.get("type") != "activity":
                continue  # insight / post-type records are not published bodies
            data = record.get("data")
            if not isinstance(data, dict):
                skipped["bad_shape"] += 1
                continue
            action = data.get("action")
            if action not in PUBLISHED_ACTIONS:
                continue
            content = data.get("content")
            if not isinstance(content, str):
                skipped["bad_shape"] += 1
                continue
            if not content.strip():
                skipped["empty_content"] += 1
                continue
            try:
                encoded = content.encode("utf-8")
            except UnicodeEncodeError:
                # A lone UTF-16 surrogate survives json.loads (the file bytes
                # are plain ASCII escape syntax) and only fails here. Left
                # uncaught it would abort the whole scan on one poisoned
                # record — and since episode logs are never deleted, the scan
                # would stay dead every week after, invisibly: the shell
                # discards stderr and falls back to "not available". Skip and
                # count, like every other fault.
                skipped["bad_unicode"] += 1
                continue
            digest = hashlib.sha256(encoded).hexdigest()[:DIGEST_LEN]
            bodies.append(Published(date=date, action=action, digest=digest))

    return bodies, dict(skipped)


def _group(bodies: list[Published]) -> dict[str, list[Published]]:
    grouped: dict[str, list[Published]] = defaultdict(list)
    for b in bodies:
        grouped[b.digest].append(b)
    return grouped


def _make_group(digest: str, members: list[Published]) -> DuplicateGroup:
    return DuplicateGroup(
        digest=digest,
        count=len(members),
        dates=tuple(sorted({m.date for m in members})),
        actions=tuple(sorted(Counter(m.action for m in members).items())),
    )


def _sorted_groups(groups: list[DuplicateGroup]) -> tuple[DuplicateGroup, ...]:
    # Digest breaks ties so the render is byte-identical across runs.
    return tuple(sorted(groups, key=lambda g: (-g.count, g.digest)))


def scan(bodies: list[Published], skipped: dict[str, int], *, start: str, end: str) -> ScanResult:
    """Derive window and lifetime readings from a single pass.

    ISO dates compare lexicographically, so the window bounds are plain string
    comparisons and are inclusive at both ends.
    """
    window = [b for b in bodies if start <= b.date <= end]

    cross_lifetime = [
        _make_group(digest, members)
        for digest, members in _group(bodies).items()
        if len({m.date for m in members}) > 1
    ]
    cross_window = [
        _make_group(digest, members)
        for digest, members in _group(window).items()
        if len({m.date for m in members}) > 1
    ]

    intra_window: list[DuplicateGroup] = []
    for digest, members in _group(window).items():
        per_date = Counter(m.date for m in members)
        repeated = {d for d, n in per_date.items() if n > 1}
        if repeated:
            intra_window.append(_make_group(digest, [m for m in members if m.date in repeated]))

    return ScanResult(
        total_bodies=len(bodies),
        total_days=len({b.date for b in bodies}),
        window_bodies=len(window),
        window_days=len({b.date for b in window}),
        cross_day_lifetime=_sorted_groups(cross_lifetime),
        cross_day_window=_sorted_groups(cross_window),
        intra_day_window=_sorted_groups(intra_window),
        skipped=skipped,
    )


_FOOTER = (
    "_Exact SHA-256 of the published body, no normalization: near-identical "
    "wording is a semantic reading and stays with the report. Digests, counts "
    "and dates only, and dates come from filenames - no body text, post id or "
    "counterparty name crosses this boundary (ADR-0083). Observation only: "
    "hash-equality dedup as an intervention is a rejected mechanism "
    "(principles.md appendix), and this table is not a case for it._"
)


def _rows(scope: str, groups: tuple[DuplicateGroup, ...], top: int) -> list[str]:
    rows = []
    for g in groups[:top]:
        actions = ", ".join(f"{a}×{n}" if n > 1 else a for a, n in g.actions)
        # md_safe is a no-op on hex, but every LLM-facing scripts/ render goes
        # through the same neutralizer rather than trusting its own charset.
        rows.append(
            f"| {scope} | `{md_safe(g.digest)}` | {g.count} | {', '.join(g.dates)} | {actions} |"
        )
    return rows


def render_markdown(result: ScanResult, *, start: str, end: str, top: int) -> str:
    lines = ["## Cross-Day Duplicate Scan", ""]
    lines.append(
        f"Window {start}..{end}: {result.window_bodies} published bodies "
        f"(post/reply/comment) across {result.window_days} days with output."
    )
    lines.append(f"**Cross-day exact duplicates in window: {len(result.cross_day_window)}.**")
    lifetime = len(result.cross_day_lifetime)
    lines.append(
        f"Lifetime ({result.total_days} days with published output, "
        f"{result.total_bodies} bodies): **cross-day exact duplicates: {lifetime}.**"
    )
    if lifetime == 0:
        # Stated as a sentence, not as a zero. The report's failure was not
        # misreading a count; it was leading with a cross-day claim while
        # calling the check undeterminable. A claim of that shape is now
        # contradicted by a line that can be quoted back at it.
        #
        # But the sentence is only as absolute as the coverage. Skipped records
        # could hold the missing occurrence, and this scan exists to refuse
        # claims wider than their evidence — including its own.
        if result.skipped:
            lines.append(
                "No body was published on more than one day among the bodies "
                "read, but records were skipped (see below), so this is not a "
                "claim about the full record."
            )
        else:
            lines.append(
                "No body has ever been published on more than one day, so any "
                "claim of a cross-day identical output is false and must be "
                "withdrawn."
            )
    intra_bodies = sum(g.count for g in result.intra_day_window)
    lines.append(
        f"Intra-day exact repeats in window: {len(result.intra_day_window)} groups "
        f"({intra_bodies} bodies)."
    )
    if result.skipped:
        detail = ", ".join(f"{k} {v}" for k, v in sorted(result.skipped.items()))
        lines.append(f"Records skipped: {sum(result.skipped.values())} ({detail}).")

    rows = _rows("cross-day (lifetime)", result.cross_day_lifetime, top)
    rows += _rows("intra-day (window)", result.intra_day_window, top)
    if rows:
        shown = min(top, len(result.cross_day_lifetime)) + min(top, len(result.intra_day_window))
        total = len(result.cross_day_lifetime) + len(result.intra_day_window)
        lines.append("")
        if shown < total:
            lines.append(f"Showing {shown} of {total} groups, largest first:")
            lines.append("")
        lines.append("| Scope | Digest | Bodies | Dates | Actions |")
        lines.append("|-------|--------|--------|-------|---------|")
        lines.extend(rows)

    lines.append("")
    lines.append(_FOOTER)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True, help="MOLTBOOK_HOME/logs")
    parser.add_argument("--start", required=True, help="window start (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="window end (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=25, help="rows per scope (default 25)")
    args = parser.parse_args(argv)

    bodies, skipped = collect(args.log_dir)
    result = scan(bodies, skipped, start=args.start, end=args.end)
    print(render_markdown(result, start=args.start, end=args.end, top=args.top))
    # Always 0. Unlike the state-invariant check, a finding here is not
    # corruption — a duplicate is a fact about published output, and the caller
    # gates on nothing.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
