#!/usr/bin/env python3
"""Deterministic surface counters for the ledger's behaviour observations (read-only).

The fourth deterministic intake that reads the episode logs, beside
``cross_day_duplicate_scan.py`` and under the same output boundary (ADR-0083).
It gives the observation ledger's behaviour rows (O-004 short-input inflation /
wrapper words, O-005 question-closer replacement, O-013 skill H1 headings) and
the two held baseline proposals (question-closer rate, nonce count) a
code-counted ground, so the weekly writer transcribes numbers instead of
re-reading bodies and judging them (P1-05.8, ADR-0099 addendum).

Five columns per published kind (comment / reply / post), per window:

  1. question-closer rate   — body ends on ``?`` / ``？`` (denominator shown;
                              the Wilson interval from ``_stats`` when n >= 10,
                              counts only below that, the P2-01.9 rule)
  2. nonce count            — bodies containing ``untrusted_content_<16 hex>``
  3. skill H1 count         — bodies containing the H1 heading of a skill in
                              ``--skills-dir`` (headings under 8 chars are
                              ignored and only their number is reported)
  4. short-context count    — records whose Context (``original_post`` for a
                              comment, ``their_comment`` for a reply) is under
                              300 chars, of those that have one; plus the
                              median output/input length ratio over them
  5. wrapper-vocabulary     — bodies containing a fixed wrapper word
     count                    (``untrusted_content`` / ``learned_skills``)

Security (load-bearing, ADR-0083): the episode logs carry untrusted content.
The boundary is the OUTPUT: only integer counts, ratios, intervals, dates taken
from filenames and the fixed kind vocabulary leave this module — never body
text, a post id, a counterparty name, a nonce value, or a skill heading. Nothing
here generates or filters: it is a reading, not an intervention (steering
generation by stripping or rephrasing these phrases is what
``config/prompts/principles.md`` rules out), and no LLM is involved.

Observability: read-only instrument, so the ADR-0075 rule is satisfied by
freezing results in the weekly materials. No state, so a failed run costs
nothing and the shell treats failure as "section unavailable".

``--readings-out FILE`` additionally writes the JSON the ledger render reads
(``observation_ledger.py render --readings``): keys ``<column>.<kind|all>`` with
``{"successes","trials"}`` (rates) or ``{"value"}`` (counts). A baseline row
binds to a key through its ``band.reading`` (default: the metric name).

Consumption plan (ADR-0101): (a) the Saturday gate reads the ledger render's
baseline lines each week; the writer transcribes this section. (b) The first
reading adjudicates the two held proposals (question-closer 5-15%, nonce 0)
and decides O-004 / O-005 / O-013 expiry; two consecutive out-of-band weeks
open or recalibrate. (c) Removal: when every ledger row and baseline these
columns serve is archived or superseded, or at the freeze, whichever is first.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from _md import md_safe
from _stats import wilson_ci
from cross_day_duplicate_scan import PUBLISHED_ACTIONS, _day_files

KINDS = PUBLISHED_ACTIONS  # ("post", "reply", "comment") — the closed vocabulary
SHORT_CONTEXT_CHARS = 300
MIN_HEADING_CHARS = 8
MIN_RATE_DENOMINATOR = 10
WRAPPER_WORDS = ("untrusted_content", "learned_skills")
_NONCE_RE = re.compile(r"untrusted_content_[0-9a-f]{16}")
_CLOSERS = ("?", "？")
_H1_RE = re.compile(r"^# (.+?)\s*$", re.MULTILINE)

# The render is built from this closed vocabulary only (see cross_day scan).
RENDER_CHARSET_RE = re.compile(r"[A-Za-z0-9 \n#*:.,()/|`\-_<>=%×]*")


@dataclass(frozen=True)
class Surface:
    """One published body reduced to booleans and lengths — no text survives."""

    date: str
    kind: str
    closer: bool
    nonce: bool
    wrapper: bool
    heading: bool
    context_len: int | None
    out_len: int


def load_headings(skills_dir: Path | None) -> tuple[tuple[str, ...], int]:
    """(usable H1 headings, count of headings ignored as too short)."""
    if skills_dir is None or not skills_dir.is_dir():
        return (), 0
    usable: set[str] = set()
    ignored = 0
    for path in sorted(skills_dir.glob("*.md")):
        if path.is_symlink():
            continue
        try:
            match = _H1_RE.search(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if not match:
            continue
        heading = match.group(1).strip()
        if len(heading) < MIN_HEADING_CHARS:
            ignored += 1
        else:
            usable.add(heading)
    return tuple(sorted(usable)), ignored


def _context_len(kind: str, data: dict) -> int | None:
    key = {"comment": "original_post", "reply": "their_comment"}.get(kind)
    value = data.get(key) if key else None
    return len(value) if isinstance(value, str) and value.strip() else None


def _surface(line: bytes, date: str, headings: tuple[str, ...]) -> Surface | str | None:
    """A Surface, a fault reason code, or None (not a published body)."""
    try:
        record = json.loads(line.decode("utf-8"))
    except UnicodeDecodeError:
        return "bad_encoding"
    except json.JSONDecodeError:
        return "bad_json"
    if not isinstance(record, dict):
        return "bad_shape"
    if record.get("type") != "activity":
        return None
    data = record.get("data")
    if not isinstance(data, dict):
        return "bad_shape"
    kind = data.get("action")
    if kind not in KINDS:
        return None
    content = data.get("content")
    if not isinstance(content, str):
        return "bad_shape"
    if not content.strip():
        return "empty_content"
    return Surface(
        date=date,
        kind=kind,
        closer=content.rstrip().endswith(_CLOSERS),
        nonce=bool(_NONCE_RE.search(content)),
        wrapper=any(w in content for w in WRAPPER_WORDS),
        heading=any(h in content for h in headings),
        context_len=_context_len(kind, data),
        out_len=len(content),
    )


def collect(log_dir: Path, headings: tuple[str, ...]) -> tuple[list[Surface], dict[str, int]]:
    rows: list[Surface] = []
    skipped: dict[str, int] = defaultdict(int)
    for path in _day_files(log_dir):
        date = path.name[: len("YYYY-MM-DD")]
        try:
            raw = path.read_bytes()
        except OSError:
            skipped["unreadable_file"] += 1
            continue
        for line in raw.splitlines():
            if not line.strip():
                continue
            out = _surface(line, date, headings)
            if isinstance(out, Surface):
                rows.append(out)
            elif isinstance(out, str):
                skipped[out] += 1
    return rows, dict(skipped)


def _column_stats(rows: list[Surface]) -> dict:
    with_ctx = [r for r in rows if r.context_len is not None]
    short = [
        r for r in with_ctx if r.context_len is not None and r.context_len < SHORT_CONTEXT_CHARS
    ]
    ratios = [r.out_len / r.context_len for r in short if r.context_len]
    return {
        "bodies": len(rows),
        "closer": sum(r.closer for r in rows),
        "nonce": sum(r.nonce for r in rows),
        "wrapper": sum(r.wrapper for r in rows),
        "heading": sum(r.heading for r in rows),
        "with_context": len(with_ctx),
        "short_context": len(short),
        "median_ratio": round(statistics.median(ratios), 2) if ratios else None,
    }


def summarize(rows: list[Surface], start: str, end: str) -> dict[str, dict]:
    window = [r for r in rows if start <= r.date <= end]
    out = {kind: _column_stats([r for r in window if r.kind == kind]) for kind in KINDS}
    out["all"] = _column_stats(window)
    return out


def readings(summary: dict[str, dict]) -> dict[str, dict]:
    """The machine-readable form the ledger render consumes."""
    out: dict[str, dict] = {}
    for scope, s in summary.items():
        out[f"question_closer.{scope}"] = {"successes": s["closer"], "trials": s["bodies"]}
        out[f"nonce.{scope}"] = {"value": s["nonce"]}
        out[f"skill_heading.{scope}"] = {"value": s["heading"]}
        out[f"wrapper_vocab.{scope}"] = {"value": s["wrapper"]}
        out[f"short_context.{scope}"] = {
            "successes": s["short_context"],
            "trials": s["with_context"],
        }
    return out


def _rate(successes: int, trials: int) -> str:
    if trials <= 0:
        return "n/a (0)"
    if trials < MIN_RATE_DENOMINATOR:
        return f"{successes}/{trials} (counts only)"
    ci = wilson_ci(successes, trials)
    pct = successes / trials * 100
    if ci is None:
        return f"{successes}/{trials}"
    return f"{pct:.1f}% ({successes}/{trials}; CI {ci[0] * 100:.1f}-{ci[1] * 100:.1f})"


def render_markdown(
    summary: dict[str, dict], *, start: str, end: str, headings: int, ignored: int, skipped: dict
) -> str:
    total = summary["all"]["bodies"]
    lines = ["## Surface Counters", ""]
    lines.append(
        f"Window {start}..{end}: {total} published bodies (post/reply/comment). "
        f"Skill H1 headings considered: {headings} (ignored as under "
        f"{MIN_HEADING_CHARS} chars: {ignored})."
    )
    lines.append("")
    lines.append(
        "| Kind | Bodies | Question-closer | Nonce | Skill H1 | Wrapper words "
        f"| Context < {SHORT_CONTEXT_CHARS} (of with-context) | Median out/in |"
    )
    lines.append(
        "|------|--------|-----------------|-------|----------|---------------|------|------|"
    )
    for scope in (*KINDS, "all"):
        s = summary[scope]
        ctx = f"{s['short_context']} of {s['with_context']}" if s["with_context"] else "n/a"
        ratio = "n/a" if s["median_ratio"] is None else f"{s['median_ratio']}"
        lines.append(
            f"| {md_safe(scope)} | {s['bodies']} | {_rate(s['closer'], s['bodies'])} "
            f"| {s['nonce']} | {s['heading']} | {s['wrapper']} | {ctx} | {ratio} |"
        )
    if skipped:
        detail = ", ".join(f"{k} {v}" for k, v in sorted(skipped.items()))
        lines.append("")
        lines.append(f"Records skipped: {sum(skipped.values())} ({detail}).")
    lines.append("")
    lines.append(
        "_Counts, ratios and intervals only; no body text, post id, counterparty "
        "name, nonce value or skill heading crosses this boundary (ADR-0083). "
        "Observation only: a reading, never a filter on generation._"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True, help="MOLTBOOK_HOME/logs/episodes")
    parser.add_argument("--start", required=True, help="window start (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="window end (YYYY-MM-DD)")
    parser.add_argument("--skills-dir", type=Path, default=None, help="MOLTBOOK_HOME/skills")
    parser.add_argument(
        "--readings-out", type=Path, default=None, help="JSON for the ledger render"
    )
    args = parser.parse_args(argv)

    headings, ignored = load_headings(args.skills_dir)
    rows, skipped = collect(args.log_dir, headings)
    summary = summarize(rows, args.start, args.end)
    print(
        render_markdown(
            summary,
            start=args.start,
            end=args.end,
            headings=len(headings),
            ignored=ignored,
            skipped=skipped,
        )
    )
    if args.readings_out is not None:
        args.readings_out.write_text(
            json.dumps(readings(summary), sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
