#!/usr/bin/env python3
"""``skills/INDEX.md`` and ``pipeline/skills-index.json`` for the public data repo (P2-05.8).

stdlib only; run as ``python3 -I scripts/skills_index.py`` from the sync export
stage (``sync-research-data.sh``), after the rsync. ``skills/`` and ``pipeline/``
are rsync ``--delete`` mirrors of ``MOLTBOOK_HOME``, so the two files are
regenerated on every sync rather than placed by hand.

One row per live skill (``skills/*.md`` in the public copy) and one per retired
skill (``MOLTBOOK_HOME/skills/.archive/*.md``, private). Columns for a live row:
stem, ``name:``, origin (frontmatter), adopted_at and source (the earliest
adopting row of ``logs/audit.jsonl`` for that file name: ``direct`` or
``stage-adopted*``; null with ``adopted_at_reason: no_audit_row`` when there is
none), status ``live``. A retired row carries only the name, the date of the
archiving audit row (null when unknown) and ``superseded_by`` — the retired text
itself stays private (ADR-0097 D5). Audit rows are read for ``ts``, ``source``
and the file's basename only; ``reason`` and every other body-like field is never
read into a row.

Not yet filled (stubs, ``null`` in the JSON, absent in the Markdown): the
selection-count column (waits for the .3 projection) and ``generated_by``. The
stem <-> ``name:`` map of P3-05.9 is the (stem, name) pair of every row here.

Self-check: the row count must equal ``skills/*.md`` + retired files; a mismatch
prints ERROR and exits 1. The line printed on success is the one-line log of the
export stage.

Consumption plan (ADR-0101): (a) the public reader, and the owner drawing the
monthly ledger; (b) one judgement — can a skill's provenance and record be read
off one line; the 2027-Q1 review only adds or drops columns; (c) retire at the
final sync of P4-02, or when the store stops accepting entries (RFC-0042
review-when / D-P0-01-1 B).

Usage:
    skills_index.py --skills DIR --out-md INDEX.md --out-json skills-index.json
        [--archive DIR] [--audit audit.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ADOPT_SOURCES_PREFIX = ("stage-adopted",)
_ADOPT_SOURCES_EXACT = ("direct",)
_RETIRE_SOURCES_PREFIX = ("direct-archive", "direct-remove", "direct-purge", "stage-archived")


def frontmatter(text: str) -> dict[str, str]:
    """Top-level ``key: value`` lines of a leading ``---`` block; values unquoted."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line[:1] in (" ", "\t", "-"):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _skill_files(skills: Path) -> list[Path]:
    """``*.md`` of the live dir, minus the index this script writes into it."""
    return [f for f in sorted(skills.glob("*.md")) if f.name != "INDEX.md"]


def _audit_rows(path: Path | None) -> list[dict[str, str]]:
    """``{base, ts, source}`` for approved rows — nothing else is kept."""
    if path is None or not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("decision") != "approved":
                continue
            p, ts, src = rec.get("path"), rec.get("ts"), rec.get("source")
            if isinstance(p, str) and isinstance(ts, str) and isinstance(src, str):
                rows.append({"base": p.replace("\\", "/").rsplit("/", 1)[-1], "ts": ts, "source": src})
    return rows


def _is_adoption(source: str) -> bool:
    return source in _ADOPT_SOURCES_EXACT or source.startswith(_ADOPT_SOURCES_PREFIX)


def _is_retirement(source: str) -> bool:
    return source.startswith(_RETIRE_SOURCES_PREFIX)


def build(
    skills: Path, archive: Path | None, audit: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    audit_rows = _audit_rows(audit)
    live: list[dict[str, Any]] = []
    for f in _skill_files(skills):
        fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        mine = sorted(
            (r for r in audit_rows if r["base"] == f.name and _is_adoption(r["source"])),
            key=lambda r: r["ts"],
        )
        row: dict[str, Any] = {
            "stem": f.stem,
            "name": fm.get("name"),
            "origin": fm.get("origin"),
            "adopted_at": mine[0]["ts"] if mine else None,
            "source": mine[0]["source"] if mine else None,
            "generated_by": None,
            "selected_90d": None,
            "status": "live",
        }
        if not mine:
            row["adopted_at_reason"] = "no_audit_row"
        live.append(row)
    retired: list[dict[str, Any]] = []
    if archive is not None and archive.is_dir():
        for f in sorted(archive.glob("*.md")):
            fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            mine = sorted(
                (r for r in audit_rows if r["base"] == f.name and _is_retirement(r["source"])),
                key=lambda r: r["ts"],
            )
            retired.append(
                {
                    "stem": f.stem,
                    "name": fm.get("name"),
                    "status": "archived",
                    "retired_at": mine[-1]["ts"] if mine else None,
                    "superseded_by": fm.get("superseded_by"),
                }
            )
    return live, retired


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(live: list[dict[str, Any]], retired: list[dict[str, Any]]) -> str:
    out = [
        "# Skills index",
        "",
        "Generated by `scripts/skills_index.py` on every sync; do not edit. "
        "One row per live skill, then one per retired skill (name and date only; "
        "the retired text is not published). Empty cell = not recorded.",
        "",
        f"## Live ({len(live)})",
        "",
        "| stem | name | origin | adopted_at | source | status |",
        "|---|---|---|---|---|---|",
    ]
    for r in live:
        out.append(
            "| "
            + " | ".join(_cell(r[k]) for k in ("stem", "name", "origin", "adopted_at", "source", "status"))
            + " |"
        )
    out += [
        "",
        f"## Retired ({len(retired)})",
        "",
        "| stem | name | retired_at | superseded_by |",
        "|---|---|---|---|",
    ]
    for r in retired:
        out.append(
            "| " + " | ".join(_cell(r[k]) for k in ("stem", "name", "retired_at", "superseded_by")) + " |"
        )
    return "\n".join(out) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skills", type=Path, required=True)
    ap.add_argument("--archive", type=Path)
    ap.add_argument("--audit", type=Path)
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    args = ap.parse_args(argv)
    if not args.skills.is_dir():
        print(f"ERROR: skills dir not found: {args.skills}", file=sys.stderr)
        return 1
    live, retired = build(args.skills, args.archive, args.audit)
    n_files = len(_skill_files(args.skills))
    n_retired = len(list(args.archive.glob("*.md"))) if args.archive and args.archive.is_dir() else 0
    rows = len(live) + len(retired)
    if rows != n_files + n_retired:
        print(f"ERROR: skills-index rows {rows} != skills/*.md {n_files} + retired {n_retired}", file=sys.stderr)
        return 1
    _write(args.out_md, render_markdown(live, retired))
    _write(args.out_json, json.dumps({"live": live, "retired": retired}, ensure_ascii=False, indent=1) + "\n")
    print(f"skills-index: live={len(live)} retired={len(retired)} rows={rows} skills/*.md={n_files}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
