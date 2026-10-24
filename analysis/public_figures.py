#!/usr/bin/env python3
"""Figures from the PUBLIC data only (RFC P3-05.11).

Input is a checkout of ``shimo4228/contemplative-agent-data`` (or any
directory with the same layout) and nothing else: no ``MOLTBOOK_HOME``, no
logs, no model, no network. stdlib only, so it runs under ``python3 -I``.

Usage:
    python3 -I analysis/public_figures.py DATA_DIR OUT_DIR

Writes three SVG files to OUT_DIR and prints one line per figure with the
numbers it plotted (so a run can be diffed):

* ``patterns-per-month.svg`` — rows of ``knowledge.json`` by ``distilled``
  month.
* ``comments-per-month.svg`` — COMMENT / REPLY / POST entries of
  ``reports/comment-reports/*.md`` by month.
* ``skills-per-month.svg`` — adopted skills by the ``YYYYMMDD`` suffix of the
  file name (the adoption date).

The comment-report parser keeps only ``**Internal note:**`` and
``**Output:**`` (the agent's own text) and drops ``**Context:**`` (the quoted
third-party post) and the counterparty's display name: the figures need
neither, and the Context is outside the CC0 dedication (see DATACARD).
Regime boundaries (``pipeline/regimes.json``) are not drawn yet: the file does
not exist (RFC P3-02.1), and coordinates are never hand-written here.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_ENTRY_RE = re.compile(
    r"^### \d+\. \[(?P<ts>[^\]]+)\] (?P<kind>COMMENT|REPLY|POST) · with .*? · post (?P<post>\S+?)…"
)
# Reports before the unified header (about 2026-06) use free-form headers; they
# are counted as ``LEGACY`` entries so a month's total is not silently short.
_LEGACY_RE = re.compile(r"^### \d+\. \[(?P<ts>[^\]]+)\]")
_KEPT = {"**Internal note:**": "internal_note", "**Output:**": "output"}
_DROPPED = {"**Context:**", "**Title:**", "**Submolt:**", "**Thinking:**"}


def parse_comment_report(text: str) -> list[dict]:
    """Entries of one ``comment-report-YYYY-MM-DD.md``, Context dropped."""
    entries: list[dict] = []
    current: dict | None = None
    field: str | None = None
    for line in text.splitlines():
        m = _ENTRY_RE.match(line)
        if not m and _LEGACY_RE.match(line):
            lm = _LEGACY_RE.match(line)
            m = {"ts": lm["ts"], "kind": "LEGACY", "post": ""}  # type: ignore[assignment]
        if m:
            current = {
                "ts": m["ts"],
                "kind": m["kind"],
                "post": m["post"],
                "internal_note": "",
                "output": "",
            }
            entries.append(current)
            field = None
        elif current is None:
            continue
        elif line.strip() == "---":
            field = None
        elif line.strip() in _KEPT:
            field = _KEPT[line.strip()]
        elif line.strip() in _DROPPED or line.startswith("**") and line.rstrip().endswith(":**"):
            field = None
        elif field:
            current[field] = (current[field] + "\n" + line).strip("\n")
    return entries


def load_patterns(data_dir: Path) -> list[dict]:
    return json.loads((data_dir / "knowledge.json").read_text(encoding="utf-8"))


def load_comment_entries(data_dir: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted((data_dir / "reports" / "comment-reports").glob("comment-report-*.md")):
        out.extend(parse_comment_report(path.read_text(encoding="utf-8")))
    return out


def month_counts(stamps: list[str]) -> dict[str, int]:
    """``YYYY-MM -> count`` for ISO-ish stamps; unparsable ones are counted apart."""
    c: Counter[str] = Counter()
    for s in stamps:
        c[s[:7] if re.match(r"\d{4}-\d{2}", s or "") else "unknown"] += 1
    return dict(sorted(c.items()))


def skill_months(data_dir: Path) -> dict[str, int]:
    stamps = []
    for p in sorted((data_dir / "skills").glob("*.md")):
        m = re.search(r"-(\d{4})(\d{2})(\d{2})\.md$", p.name)
        stamps.append(f"{m[1]}-{m[2]}-{m[3]}" if m else "")
    return month_counts(stamps)


def bar_svg(title: str, series: dict[str, int]) -> str:
    """A plain vertical bar chart, one bar per key, no external dependency."""
    w, h, pad_l, pad_b, pad_t = 720, 320, 48, 44, 36
    peak = max(series.values(), default=1) or 1
    n = max(len(series), 1)
    slot = (w - pad_l - 16) / n
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{title}">',
        f"<title>{title}</title>",
        f'<text x="{pad_l}" y="22" font-size="14" font-family="sans-serif">{title}</text>',
        f'<line x1="{pad_l}" y1="{h - pad_b}" x2="{w - 8}" y2="{h - pad_b}" stroke="#888"/>',
        f'<text x="4" y="{pad_t + 6}" font-size="11" font-family="sans-serif">{peak}</text>',
    ]
    for i, (key, value) in enumerate(series.items()):
        bar_h = (h - pad_b - pad_t) * value / peak
        x = pad_l + i * slot + slot * 0.15
        y = h - pad_b - bar_h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{slot * 0.7:.1f}" height="{bar_h:.1f}" fill="#4a6fa5">'
            f"<title>{key}: {value}</title></rect>"
        )
        parts.append(
            f'<text x="{x + slot * 0.35:.1f}" y="{h - pad_b + 14}" font-size="10" text-anchor="middle" '
            f'font-family="sans-serif">{key}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build(data_dir: Path, out_dir: Path) -> dict[str, dict[str, int]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = {
        "patterns-per-month": (
            "Patterns distilled per month",
            month_counts([r.get("distilled", "") for r in load_patterns(data_dir)]),
        ),
        "comments-per-month": (
            "Comments, replies and posts per month",
            month_counts([e["ts"] for e in load_comment_entries(data_dir)]),
        ),
        "skills-per-month": ("Skills adopted per month", skill_months(data_dir)),
    }
    for name, (title, series) in figures.items():
        (out_dir / f"{name}.svg").write_text(bar_svg(title, series), encoding="utf-8")
    return {name: series for name, (_, series) in figures.items()}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    data_dir, out_dir = Path(argv[1]), Path(argv[2])
    if not (data_dir / "knowledge.json").is_file():
        print(f"Error: {data_dir} has no knowledge.json", file=sys.stderr)
        return 2
    for name, series in build(data_dir, out_dir).items():
        print(f"{name}: {sum(series.values())} total over {len(series)} months")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
