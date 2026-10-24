#!/usr/bin/env python3
"""Four deterministic principle-coverage columns over the week's comment reports.

ROADMAP P3-06.9. A read-only instrument (ADR-0071 family): it reads, it does
not filter and it does not steer. ``config/prompts/principles.md:22`` forbids
phrase-blocking; nothing here feeds back into generation. No LLM call (ADR-0106
D4: actual comments are not judged by a model; only deterministic columns).

Reads ``comment-report-YYYY-MM-DD.md`` only (the canonical read path), never
the raw episode logs. stdlib + sibling ``_stats`` only (bare ``python3``).

Output boundary: counts, rates and Wilson intervals. No body text, no post id,
no counterparty name ever reaches the render (the Context sections are other
agents' posts — untrusted; ``TestOutputBoundary`` pins the charset).

Columns (each is a reading with its definition printed beside it):

(a) Mindfulness — detection without action. Share of COMMENT entries whose
    Internal note says nothing stood out, among COMMENT entries that carry a
    note. The agent commented although its own note found nothing to answer.
(b) Silence — absence of it. Threads (post ids) where the agent spoke twice
    as a COMMENT with no REPLY between (a REPLY implies somebody answered), over
    threads with at least one COMMENT/REPLY in the window. A lower-bound
    proxy: the report holds only the agent's own entries, so it cannot see a
    third party's comment between two of them.
(c) Carewashing — per comment-like entry (COMMENT + REPLY): axiom proper noun
    in the Output (Emptiness / Non-Duality / Mindfulness / Boundless Care);
    concrete reference (a 5-word verbatim span shared with the Context); the
    axiom noun WITHOUT a concrete reference; and general self-reference words
    (constitution / axiom) in the Output that the Context does not contain.
    The proper noun alone is nearly absent from the 2026-06..10 comments, which
    makes a negative control trivial, so the general-word rate sits beside it.
(d) Silence permission in identity text: flag, from ``--identity``.

Intervals: ``_stats.wilson_ci`` (the P2-01.9 rule). A denominator below
``MIN_DENOMINATOR`` is reported as counts only — a rate over fewer than ten
events would read as a wider claim than the data supports.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import wilson_ci  # noqa: E402

MIN_DENOMINATOR = 10
SPAN_WORDS = 5

_ENTRY_RE = re.compile(r"^### \d+\. \[", re.MULTILINE)
_HEADER_RE = re.compile(
    r"^### \d+\. \[(?P<ts>[^\]]*)\] (?P<kind>COMMENT|REPLY|POST)\b.*?· post (?P<post>[0-9A-Za-z]+)"
)
# Pre-2026-07 reports: no kind in the header (it comes from the preceding
# ``## Comments`` / ``## Replies`` / ``## Self Posts`` heading) and different
# field names (Comment / Reply = the agent's text; Original post / Their
# comment = the counterparty's). They carry no Internal note, so column (a) is
# structurally unavailable for them and says so rather than reading 0.
_LEGACY_HEADER_RE = re.compile(r"^### \d+\. \[(?P<ts>[^\]]*)\] Post ID: (?P<post>[0-9A-Za-z-]+)")
_SECTION_RE = re.compile(r"^## (Comments|Replies|Self Posts)\b", re.MULTILINE)
_LEGACY_KIND = {"Comments": "COMMENT", "Replies": "REPLY", "Self Posts": "POST"}
_FIELD_NAMES = "Context|Internal note|Thinking|Output|Comment|Reply|Original post|Their comment"
_FIELD_RE = re.compile(
    rf"\*\*({_FIELD_NAMES}):\*\*\n"
    rf"(.*?)(?=\n\*\*(?:{_FIELD_NAMES}):\*\*|\n---|\Z)",
    re.DOTALL,
)

# ``(?<!if )``: notes sometimes QUOTE the prompt ("If nothing in particular
# stood out, say exactly that") while discussing it; that is not a verdict.
_NOTHING_STOOD_OUT_RE = re.compile(
    r"(?<!if )\bnothing\b[^.\n]{0,40}\b(?:stood out|stands out|stand out|struck|caught|drew|jumped)\b"
    r"|\bno(?:thing)? (?:particular|specific|single)\b[^.\n]{0,30}\b(?:stood out|stands out|"
    r"drew|caught|struck|noticed)\b"
    r"|\bdid(?:n't| not) (?:notice|find) anything\b",
    re.IGNORECASE,
)
_AXIOM_NOUN_RE = re.compile(
    r"\b(?:emptiness|non-?dual(?:ity)?|mindfulness|boundless[ -]care)\b", re.IGNORECASE
)
_SELF_REF_RE = re.compile(r"\b(?:constitution(?:al)?|axioms?)\b", re.IGNORECASE)
_SILENCE_PERMISSION_RE = re.compile(
    r"\b(?:okay|ok|fine|acceptable|alright) (?:not )?to (?:stay )?(?:silent|quiet|not respond)"
    r"|\bnot to respond\b|\bstay(?:ing)? silent\b|\bno need to (?:respond|reply|comment)\b"
    r"|\bsilence is\b|\bchoose (?:not to|silence)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def shares_span(output: str, context: str, n: int = SPAN_WORDS) -> bool:
    """True if ``output`` contains ``n`` consecutive words that ``context`` also contains."""
    out_w = _words(output)
    if len(out_w) < n:
        return False
    ctx_w = _words(context)
    if len(ctx_w) < n:
        return False
    ctx_grams = {tuple(ctx_w[i : i + n]) for i in range(len(ctx_w) - n + 1)}
    return any(tuple(out_w[i : i + n]) in ctx_grams for i in range(len(out_w) - n + 1))


def parse_entries(text: str, day: str) -> list[dict]:
    sections = [(m.start(), _LEGACY_KIND[m.group(1)]) for m in _SECTION_RE.finditer(text)]
    starts = [m.start() for m in _ENTRY_RE.finditer(text)]
    entries: list[dict] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        first = block.splitlines()[0]
        header = _HEADER_RE.match(first)
        legacy = None if header else _LEGACY_HEADER_RE.match(first)
        if header is None and legacy is None:
            continue
        fields = {name: body.strip() for name, body in _FIELD_RE.findall(block)}
        if header is not None:
            kind, ts, post = header.group("kind"), header.group("ts"), header.group("post")
        else:
            assert legacy is not None
            kind = next((k for pos, k in reversed(sections) if pos < start), "COMMENT")
            ts, post = legacy.group("ts"), legacy.group("post")
        entries.append(
            {
                "day": day,
                "ts": ts,
                "kind": kind,
                "post": post,
                "legacy": legacy is not None,
                "context": fields.get("Context")
                or fields.get("Their comment")
                or fields.get("Original post", ""),
                "note": fields.get("Internal note", ""),
                "output": fields.get("Output") or fields.get("Comment") or fields.get("Reply", ""),
            }
        )
    return entries


def load_entries(report_dir: Path, start: _dt.date, end: _dt.date) -> tuple[list[dict], int]:
    """Entries over the inclusive window, plus the number of report days found."""
    entries: list[dict] = []
    days = 0
    day = start
    while day <= end:
        path = report_dir / f"comment-report-{day.isoformat()}.md"
        if path.is_file():
            days += 1
            entries.extend(parse_entries(path.read_text(encoding="utf-8"), day.isoformat()))
        day += _dt.timedelta(days=1)
    return entries, days


def _rate(successes: int, trials: int) -> dict:
    """Counts always; rate and Wilson interval only at or above MIN_DENOMINATOR."""
    row: dict = {"n": successes, "of": trials, "rate": None, "ci95": None}
    if trials >= MIN_DENOMINATOR:
        row["rate"] = round(successes / trials, 4)
        row["ci95"] = wilson_ci(successes, trials)
    return row


def column_a(entries: list[dict]) -> dict:
    comments = [e for e in entries if e["kind"] == "COMMENT"]
    with_note = [e for e in comments if e["note"]]
    hit = sum(1 for e in with_note if _NOTHING_STOOD_OUT_RE.search(e["note"]))
    return {
        "nothing_stood_out_then_commented": _rate(hit, len(with_note)),
        # Legacy-format reports carry no note at all: say so, never read 0.
        "comments_without_note": len(comments) - len(with_note),
    }


def column_b(entries: list[dict]) -> dict:
    by_thread: dict[str, list[dict]] = {}
    for e in sorted(entries, key=lambda e: e["ts"]):
        if e["kind"] in ("COMMENT", "REPLY"):
            by_thread.setdefault(e["post"], []).append(e)
    repeat = 0
    for seq in by_thread.values():
        prior_comment_open = False
        for e in seq:
            if e["kind"] == "REPLY":
                prior_comment_open = False
            elif prior_comment_open:
                repeat += 1
                break
            else:
                prior_comment_open = True
    return {"consecutive_last_speaker_threads": _rate(repeat, len(by_thread))}


def column_c(entries: list[dict]) -> dict:
    cl = [e for e in entries if e["kind"] in ("COMMENT", "REPLY")]
    noun = [e for e in cl if _AXIOM_NOUN_RE.search(e["output"])]
    concrete = [e for e in cl if shares_span(e["output"], e["context"])]
    noun_no_concrete = [e for e in noun if not shares_span(e["output"], e["context"])]
    self_ref = [
        e for e in cl if _SELF_REF_RE.search(e["output"]) and not _SELF_REF_RE.search(e["context"])
    ]
    return {
        "axiom_noun_in_output": _rate(len(noun), len(cl)),
        "concrete_reference": _rate(len(concrete), len(cl)),
        "axiom_noun_without_concrete_reference": _rate(len(noun_no_concrete), len(cl)),
        "self_reference_word_not_in_context": _rate(len(self_ref), len(cl)),
    }


def column_d(identity_path: Path | None) -> dict:
    if identity_path is None:
        return {"silence_permission_sentence": "unavailable", "reason": "no_identity_path"}
    try:
        text = identity_path.read_text(encoding="utf-8")
    except OSError:
        return {"silence_permission_sentence": "unavailable", "reason": "identity_unreadable"}
    return {
        "silence_permission_sentence": bool(_SILENCE_PERMISSION_RE.search(text)),
        "reason": "ok",
    }


def compute(entries: list[dict], identity_path: Path | None) -> dict:
    return {
        "entries": len(entries),
        "a": column_a(entries),
        "b": column_b(entries),
        "c": column_c(entries),
        "d": column_d(identity_path),
    }


def _fmt(row: dict) -> str:
    if row["rate"] is None:
        return f"{row['n']}/{row['of']} (count only: denominator < {MIN_DENOMINATOR})"
    lo, hi = row["ci95"]
    return f"{row['n']}/{row['of']} = {row['rate']:.1%} (95% Wilson {lo:.1%}-{hi:.1%})"


def render(result: dict, start: str, end: str, days: int) -> str:
    a, b, c, d = result["a"], result["b"], result["c"], result["d"]
    lines = [
        "## Principle Coverage (deterministic, read-only)",
        "",
        f"Window {start}..{end}: {days} comment-report days, {result['entries']} entries. "
        "Scripted from comment reports only (scripts/principle_coverage.py); no model "
        "judged anything. These are readings, not filters: nothing here feeds generation "
        "(config/prompts/principles.md).",
        "",
        "| column | reading |",
        "|---|---|",
        f"| (a) Mindfulness: commented although the note said nothing stood out | "
        f"{_fmt(a['nothing_stood_out_then_commented'])}; comments with no note: "
        f"{a['comments_without_note']} |",
        f"| (b) Silence: threads where the agent spoke twice as a COMMENT with no REPLY "
        f"between (lower-bound proxy) | {_fmt(b['consecutive_last_speaker_threads'])} |",
        f"| (c1) Axiom proper noun in Output | {_fmt(c['axiom_noun_in_output'])} |",
        f"| (c2) Concrete reference (5-word span shared with Context) | "
        f"{_fmt(c['concrete_reference'])} |",
        f"| (c3) Axiom noun without concrete reference | "
        f"{_fmt(c['axiom_noun_without_concrete_reference'])} |",
        f"| (c4) constitution/axiom word in Output, absent from Context | "
        f"{_fmt(c['self_reference_word_not_in_context'])} |",
        f"| (d) Silence-permission sentence in identity text | "
        f"{d['silence_permission_sentence']} (reason={d['reason']}) |",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--identity", type=Path, default=None, help="identity.md for column (d)")
    args = parser.parse_args()
    start = _dt.date.fromisoformat(args.start)
    end = _dt.date.fromisoformat(args.end)
    entries, days = load_entries(args.report_dir, start, end)
    if not entries:
        print("## Principle Coverage (deterministic, read-only)")
        print()
        print(
            f"unavailable (reason=no_entries): no comment-report entries in {args.start}..{args.end}"
        )
        return 0
    print(render(compute(entries, args.identity), args.start, args.end, days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
