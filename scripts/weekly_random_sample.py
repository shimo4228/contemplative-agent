#!/usr/bin/env python3
"""Deterministic random sample of daily comment-report entries (RFC-0010).

The weekly instrument document's Sample section is the control channel against
the LLM writer's own selection function: a uniform sample drawn by code, from
the same corpus the writer reads, that the writer must copy verbatim and may
not curate. Seeded by the week's end date so the draw is replayable — running
this script again for the same window reproduces the same sample (no wall
clock, no PID, no entropy).

Reads ``comment-report-YYYY-MM-DD.md`` files (the canonical read path for
utterance bodies — never the raw episode logs). Output is markdown with
per-entry excerpts bounded deterministically (character caps, not model
judgment). The shell wraps the whole section in the untrusted nonce frame,
since Context excerpts are other agents' post bodies.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import random
import re
from pathlib import Path

_ENTRY_RE = re.compile(r"^### \d+\. \[", re.MULTILINE)
# The full field vocabulary core/report.py::_entry_lines emits in the
# **X:**\nbody shape (Title/Submolt are single-line `**X:** value` and never
# match this). Thinking is parsed only so it cannot bleed into a neighboring
# capture — it is never rendered. The `\n---` alternative stops the last
# field's capture at the entry separator instead of running to end-of-block.
_FIELD_RE = re.compile(
    r"\*\*(Context|Internal note|Thinking|Output):\*\*\n"
    r"(.*?)(?=\n\*\*(?:Context|Internal note|Thinking|Output):\*\*|\n---|\Z)",
    re.DOTALL,
)

CONTEXT_CAP = 300
OUTPUT_CAP = 500

# (rendered label, parsed field name, character cap) — the two fields the
# sample surfaces, in print order.
_RENDERED_FIELDS = (
    ("Context (counterparty, untrusted)", "Context", CONTEXT_CAP),
    ("Output (agent)", "Output", OUTPUT_CAP),
)


def _excerpt(text: str, cap: int) -> str:
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    return f"{text[:cap].rsplit(' ', 1)[0]} […truncated at {cap} chars]"


def _entries_for_day(path: Path, day: str) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    starts = [m.start() for m in _ENTRY_RE.finditer(text)]
    entries = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        header = block.splitlines()[0].lstrip("# ").strip()
        fields = {name: body.strip() for name, body in _FIELD_RE.findall(block)}
        entries.append({"day": day, "header": header, "fields": fields})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, help="comment-reports directory")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD inclusive (also the seed)")
    parser.add_argument("--k", type=int, default=5, help="sample size (default 5)")
    args = parser.parse_args()

    start = _dt.date.fromisoformat(args.start)
    end = _dt.date.fromisoformat(args.end)
    report_dir = Path(args.report_dir)

    corpus: list[dict] = []
    day = start
    while day <= end:
        path = report_dir / f"comment-report-{day.isoformat()}.md"
        if path.exists():
            corpus.extend(_entries_for_day(path, day.isoformat()))
        day += _dt.timedelta(days=1)

    print("## Random Sample (deterministic control channel)")
    print()
    if not corpus:
        print(f"No entries found in {args.start}..{args.end}. Sample unavailable.")
        return 0

    k = min(args.k, len(corpus))
    rng = random.Random(f"weekly-sample-{args.end}")
    sample = rng.sample(corpus, k)
    sample.sort(key=lambda e: (e["day"], e["header"]))

    print(
        f"Uniform sample of {k} of {len(corpus)} entries, seed `weekly-sample-{args.end}` "
        f"(replayable: scripts/weekly_random_sample.py). Excerpts are cut at fixed character "
        f"caps by code, not chosen by any model. The writer copies this section verbatim."
    )
    print()
    for i, entry in enumerate(sample, 1):
        print(f"### Sample {i}/{k} — {entry['header']}")
        print()
        for label, field, cap in _RENDERED_FIELDS:
            value = entry["fields"].get(field, "")
            if value:
                print(f"**{label}:** {_excerpt(value, cap)}")
                print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
