#!/usr/bin/env python3
"""Read-only reading of the Q2 "compounding" axes (P3-01.3, research-questions ADR).

Q2 asks whether distillation compounds. "Compounding" is read on several axes
that are NEVER collapsed into one number (ADR-0080, 2026-08-26 addendum B).
Every axis here is computed from the public data repo only:

1. ``skill_selection_activity`` — per ``pipeline/never-selected/*.json``: of the
   catalog skills that have ever been selected, the share still chosen inside
   the trailing window (``1 - dormant / ever_selected``).
2. ``corpus_growth`` — from ``knowledge.json``: patterns distilled per ISO week
   (Monday label), the cumulative size before that week, and the weekly
   additions over that prior size. Count-only; the public file is
   embedding-free, so a similarity-based novelty rate is not computable here.
3. ``environment_response`` — per ``pipeline/comment-outcomes/*.json``: the
   skill-injected reply rate as ``sum(comments_with_reply) / sum(injected)``
   over skill rows. A comment injecting k skills is counted k times, so the
   pairs are not independent and the interval is optimistic; the file carries
   no non-injected arm, so the with/without contrast is NOT computable here
   (the confounding caveat of RFC-0028 stays in force).
4. ``source_pattern_age`` — NOT computed here. It needs private inputs
   (skill-selection logs, the audit log's ``source_ids``); its first reading is
   taken on the machine that holds them and frozen under ``docs/evidence/``.
   The output states this instead of omitting the axis.

Rate axes carry a 95% Wilson interval (``scripts/_stats.wilson_ci``); a
denominator below 10 yields counts only and no interval. ``--boundary
YYYY-MM-DD`` (repeatable) labels each row with the regime interval it falls in,
so rows are read per interval; the boundary list itself belongs to the
regime-boundary table (P3-02.1), not to this script.

Manual runs only; not part of CI and not scheduled. Reads
``<data-repo>/knowledge.json`` and ``<data-repo>/pipeline/{never-selected,
comment-outcomes}/*.json`` and nothing else. Abstains with ``reason=CODE``
on stderr and exit 2 when an input is missing or unreadable.

Usage:
    python3 scripts/compounding_axes_reading.py --data-repo ~/contemplative-agent-data \\
        [--boundary 2026-06-28 ...] [--format json|md]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from _stats import wilson_ci

MIN_DENOMINATOR = 10
SCHEMA = 1


class ReadingError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code} {detail}")
        self.code = code
        self.detail = detail


def _rate(successes: int, trials: int) -> dict[str, Any]:
    """Counts always; a rate and interval only from MIN_DENOMINATOR trials."""
    out: dict[str, Any] = {"n": trials, "k": successes}
    if trials >= MIN_DENOMINATOR:
        out["rate"] = round(successes / trials, 4)
        out["ci95"] = wilson_ci(successes, trials)
    else:
        out["rate"] = None
        out["ci95"] = None
    return out


def _interval_index(day: str, boundaries: list[str]) -> int:
    """0 for days before the first boundary, 1 from it, and so on."""
    return sum(1 for b in boundaries if day >= b)


def _load_json(path: Path, code: str) -> Any:  # noqa: ANN401 — json is untyped
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReadingError(f"{code}_MISSING", str(path)) from None
    except (OSError, ValueError) as exc:
        raise ReadingError(f"{code}_UNREADABLE", f"{path}: {exc}") from None


def _dated_files(directory: Path, prefix: str) -> list[tuple[str, Path]]:
    if not directory.is_dir():
        raise ReadingError("INPUT_DIR_MISSING", str(directory))
    found: list[tuple[str, Path]] = []
    for path in sorted(directory.glob(f"{prefix}-*.json")):
        stamp = path.stem[len(prefix) + 1 :]
        try:
            date.fromisoformat(stamp)
        except ValueError:
            continue
        found.append((stamp, path))
    if not found:
        raise ReadingError("NO_READINGS", f"no {prefix}-YYYY-MM-DD.json under {directory}")
    return found


def read_skill_selection_activity(data_repo: Path, boundaries: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stamp, path in _dated_files(data_repo / "pipeline" / "never-selected", "never-selected"):
        doc = _load_json(path, "NEVER_SELECTED")
        catalog = doc.get("catalog") or {}
        if not catalog.get("available"):
            rows.append({"week_end": stamp, "interval": _interval_index(stamp, boundaries), "status": "catalog_unavailable"})
            continue
        size = int(catalog["size"])
        strict = len(doc.get("strict") or [])
        dormant = len(doc.get("dormant") or [])
        below = len(doc.get("below_floor") or [])
        ever = size - strict - below
        row: dict[str, Any] = {
            "week_end": stamp,
            "interval": _interval_index(stamp, boundaries),
            "catalog": size,
            "strict_never_selected": strict,
            "below_floor": below,
            "dormant": dormant,
            "ever_selected": ever,
            "window_active": _rate(ever - dormant, ever),
            "note": "dormant excludes names the window never offered, so the active share is a lower bound",
        }
        rows.append(row)
    return rows


def _week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def read_corpus_growth(data_repo: Path, boundaries: list[str]) -> list[dict[str, Any]]:
    doc = _load_json(data_repo / "knowledge.json", "KNOWLEDGE")
    if not isinstance(doc, list):
        raise ReadingError("KNOWLEDGE_UNREADABLE", "top level is not a list")
    added: dict[date, int] = {}
    live: dict[date, int] = {}
    skipped = 0
    for row in doc:
        stamp = row.get("distilled") if isinstance(row, dict) else None
        try:
            monday = _week_monday(date.fromisoformat(str(stamp)[:10]))
        except ValueError:
            skipped += 1
            continue
        added[monday] = added.get(monday, 0) + 1
        if not row.get("valid_until"):
            live[monday] = live.get(monday, 0) + 1
    if not added:
        raise ReadingError("NO_READINGS", "no row of knowledge.json has a readable 'distilled'")
    rows: list[dict[str, Any]] = []
    cumulative = 0
    monday = min(added)
    last = max(added)
    while monday <= last:
        count = added.get(monday, 0)
        rows.append(
            {
                "week_start": monday.isoformat(),
                "interval": _interval_index(monday.isoformat(), boundaries),
                "added": count,
                "added_still_live": live.get(monday, 0),
                "cumulative_before": cumulative,
                "added_over_cumulative_before": round(count / cumulative, 4) if cumulative else None,
            }
        )
        cumulative += count
        monday += timedelta(days=7)
    if skipped:
        rows.append({"unreadable_distilled_rows": skipped})
    return rows


def read_environment_response(data_repo: Path, boundaries: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stamp, path in _dated_files(data_repo / "pipeline" / "comment-outcomes", "comment-outcomes"):
        doc = _load_json(path, "COMMENT_OUTCOMES")
        skills = doc.get("skills") or []
        injected = sum(int(s.get("injected_comments", 0)) for s in skills)
        replied = sum(int(s.get("comments_with_reply", 0)) for s in skills)
        rows.append(
            {
                "week_end": stamp,
                "interval": _interval_index(stamp, boundaries),
                "observed_publishes": doc.get("observed_publishes"),
                "unobserved_publishes": doc.get("unobserved_publishes"),
                "skill_comment_pairs_reply_rate": _rate(replied, injected),
                "skills_with_at_least_10_pairs": sum(1 for s in skills if int(s.get("injected_comments", 0)) >= MIN_DENOMINATOR),
                "note": "pairs are not independent (one comment injects several skills); no non-injected arm in this file",
            }
        )
    return rows


def build_reading(data_repo: Path, boundaries: list[str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "boundaries": boundaries,
        "axes": {
            "skill_selection_activity": read_skill_selection_activity(data_repo, boundaries),
            "corpus_growth": read_corpus_growth(data_repo, boundaries),
            "environment_response": read_environment_response(data_repo, boundaries),
            "source_pattern_age": {
                "status": "not_computed",
                "reason": "private_inputs",
                "reanalysis": "private-rows",
                "needs": ["skill-selection-*.jsonl", "audit.jsonl adopt entries (source_ids)", "knowledge.json"],
            },
        },
        "single_scalar": None,
    }


def _fmt_rate(r: dict[str, Any]) -> str:
    if r["rate"] is None:
        return f"{r['k']}/{r['n']} (count only)"
    lo, hi = r["ci95"]
    return f"{r['k']}/{r['n']} = {r['rate']:.3f} [{lo:.3f}, {hi:.3f}]"


def render_markdown(reading: dict[str, Any]) -> str:
    axes = reading["axes"]
    out = ["# Q2 compounding axes (read-only; axes are not combined)", ""]
    out += ["## skill_selection_activity", "", "| week end | int | ever selected | window active | dormant | strict never |", "|---|---|---|---|---|---|"]
    for r in axes["skill_selection_activity"]:
        if "status" in r:
            out.append(f"| {r['week_end']} | {r['interval']} | {r['status']} | | | |")
        else:
            out.append(f"| {r['week_end']} | {r['interval']} | {r['ever_selected']} | {_fmt_rate(r['window_active'])} | {r['dormant']} | {r['strict_never_selected']} |")
    out += ["", "## corpus_growth", "", "| week start | int | added | still live | cumulative before | added / before |", "|---|---|---|---|---|---|"]
    for r in axes["corpus_growth"]:
        if "week_start" not in r:
            out.append(f"| unreadable distilled rows: {r['unreadable_distilled_rows']} | | | | | |")
            continue
        ratio = "" if r["added_over_cumulative_before"] is None else f"{r['added_over_cumulative_before']:.3f}"
        out.append(f"| {r['week_start']} | {r['interval']} | {r['added']} | {r['added_still_live']} | {r['cumulative_before']} | {ratio} |")
    out += ["", "## environment_response", "", "| week end | int | observed publishes | skill-comment pairs with reply | skills >= 10 pairs |", "|---|---|---|---|---|"]
    for r in axes["environment_response"]:
        out.append(f"| {r['week_end']} | {r['interval']} | {r['observed_publishes']} | {_fmt_rate(r['skill_comment_pairs_reply_rate'])} | {r['skills_with_at_least_10_pairs']} |")
    out += ["", "## source_pattern_age", "", "Not computed here (`reanalysis: private-rows`); first reading is taken where the private inputs live and frozen under `docs/evidence/`.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--data-repo", required=True, type=Path)
    parser.add_argument("--boundary", action="append", default=[], metavar="YYYY-MM-DD")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    args = parser.parse_args(argv)
    boundaries = sorted(args.boundary)
    for b in boundaries:
        try:
            date.fromisoformat(b)
        except ValueError:
            print(f"reason=BAD_BOUNDARY {b}", file=sys.stderr)
            return 2
    try:
        reading = build_reading(args.data_repo, boundaries)
    except ReadingError as exc:
        print(f"reason={exc.code} {exc.detail}", file=sys.stderr)
        return 2
    if args.format == "md":
        print(render_markdown(reading))
    else:
        print(json.dumps(reading, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
