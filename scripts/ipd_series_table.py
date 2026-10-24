#!/usr/bin/env python3
"""Table of an IPD series (P3-03.3 retro versions, P3-03.4 placebo arms).

Reads the manifest (label, path, note) and ``OUTDIR/<label>.json`` written by
``scripts/ipd-series.sh`` and prints one markdown table: per text and α, the
effect (custom − baseline) with its SE, and — against the reference text (first
manifest row unless ``--ref``) — Δeffect, SE(Δ) and z under the cell-wise SE
rule of ADR-0090 (Amendment 2026-10-24), plus the failed-move rate when the run
recorded it. Which comparisons are *read* is fixed by the pre-registration
(P3-01.2); this table prints every text against the reference and does not
decide that. 12 cells (4 texts x 3 α) are not tested against one floor; the z
column is read pair by pair.

Usage: python3 scripts/ipd_series_table.py MANIFEST.tsv OUTDIR [--ref LABEL]
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "ipd_two_arm_report", os.path.join(_HERE, "ipd_two_arm_report.py")
)
rep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rep)


def read_manifest(path: str) -> list[tuple[str, str]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            rows.append((parts[0], parts[2] if len(parts) > 2 else ""))
    if not rows:
        sys.exit(f"ERROR: {path}: no rows")
    return rows


def failure_rate(arm: dict) -> str:
    f = arm["failures"]
    if f is None:
        return "not recorded"
    fails = sum(x for rows in f["by_cell"].values() for _r, x in rows)
    moves = sum(f["rounds"] * len(rows) for rows in f["by_cell"].values())
    return f"{fails / moves:.3f}"


def build(manifest: str, outdir: str, ref: str | None) -> str:
    rows = read_manifest(manifest)
    arms = {}
    for label, _note in rows:
        p = os.path.join(outdir, f"{label}.json")
        if not os.path.exists(p):
            sys.exit(f"ERROR: {p}: run for '{label}' is missing")
        arms[label] = rep.load_arm(p)
    ref = ref or rows[0][0]
    if ref not in arms:
        sys.exit(f"ERROR: reference '{ref}' is not in the manifest")
    ra = arms[ref]
    lines = [
        f"# IPD series (reference: {ref})",
        "",
        f"Cell-wise SE rule, |z| > {rep.Z_THRESHOLD:g} (ADR-0090 Amendment 2026-10-24); "
        "12 cells are not tested against one floor.",
        "",
        "| text | α | effect | SE | Δeffect vs ref | SE(Δ) | z | failed moves | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for label, note in rows:
        a = arms[label]
        for al in rep.ALPHAS:
            e, se = rep.effect(a["cells"], al), rep.effect_se(a["ses"], al)
            if label == ref:
                d = sd = None
            else:
                d = e - rep.effect(ra["cells"], al)
                sd = math.hypot(se, rep.effect_se(ra["ses"], al))
            lines.append(
                f"| {label} | {al} | {e:+.3f} | {se:.3f} | "
                + (
                    "(ref) | | | "
                    if d is None
                    else f"{d:+.3f} | {sd:.3f} | {rep._fmt_z(rep.z_of(d, sd))} | "
                )
                + f"{failure_rate(a)} | {note} |"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("outdir")
    ap.add_argument("--ref")
    ns = ap.parse_args()
    print(build(ns.manifest, ns.outdir, ns.ref))
