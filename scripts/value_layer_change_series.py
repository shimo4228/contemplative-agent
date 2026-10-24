#!/usr/bin/env python3
"""Value-layer change series from the public ``snapshots/`` digests (P2-05.7).

stdlib only; run as ``python3 -I scripts/value_layer_change_series.py``. Read-only:
the one input is a ``snapshots/`` directory (the public copy in the data repo is
enough), the outputs are two JSON files the caller names.

What it answers: *at which snapshot did a value-layer kind (identity /
constitution / rules / skills) change, and what changed?* Each snapshot dir
holds ``identity.md`` and ``constitution/ rules/ skills/*.md`` copies. A kind's
digest is the first 12 hex of sha256 (``identity.md``: of the file; a directory:
of the sorted ``name<TAB>file-sha256`` lines). Walking the snapshots in
manifest-``ts`` order, a row is emitted at every point where the digest differs
from the previous snapshot that has the kind:

    {kind, from_snapshot, to_snapshot, ts_from, ts_to,
     sha_before, sha_after, files_added, files_removed}

This is *not* ``unchanged_since`` of ``value_layer_approval_join.py`` (that is
the stillness of a hand-edit detector's unmatched set, not of the value layer).
A boundary lost to snapshot rotation (MAX_SNAPSHOTS) is not recoverable here;
the row's ``from_snapshot`` is simply the oldest snapshot still present, which
is why ``coverage`` (first / last snapshot ts, count) is part of the output.

Second output, ``--candidates-out``: serving-environment change *candidates* —
the points where a snapshot manifest's ``ollama_version`` /
``generation_model_digest`` / ``embedding_model_digest`` differ from the
previous snapshot that recorded the same key (a key absent or null on either
side is not a change). The script never touches ``pipeline/regimes.json``;
confirming a candidate into the boundary table is a human act (P3-02.7).

Consumption plan (ADR-0101): (a) the Saturday gate's materials carry one line
(did any kind change in the latest week) and the P4-01 consideration event B and
the P2-01.5 self-regulation statement read the series; (b) four consecutive
weeks with no change make event B a candidate, and one reading writes
"stationary" or "drifting" into the gate record; (c) retire when the run
sessions stop (layer 5) — the series is frozen then, and the script stops with
the snapshots.

Usage:
    value_layer_change_series.py SNAPSHOTS_DIR --out changes.json
        [--candidates-out regime-candidates.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

KINDS = ("identity", "constitution", "rules", "skills")
SERVING_KEYS = ("ollama_version", "generation_model_digest", "embedding_model_digest")
SHA_LEN = 12

_TS_FROM_NAME = re.compile(r"_(\d{8}T\d{6})\d*Z$")


def _sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:SHA_LEN]


def _dir_files(path: Path) -> dict[str, str]:
    """``{file name: full sha256}`` for the ``*.md`` files directly in ``path``."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.glob("*.md"))
        if p.is_file()
    }


def kind_state(snap: Path, kind: str) -> tuple[str, dict[str, str]] | None:
    """``(digest, files)`` of one kind in one snapshot; None when it has none."""
    if kind == "identity":
        f = snap / "identity.md"
        if not f.is_file():
            return None
        data = f.read_bytes()
        return _sha12(data), {"identity.md": hashlib.sha256(data).hexdigest()}
    d = snap / kind
    if not d.is_dir():
        return None
    files = _dir_files(d)
    body = "".join(f"{n}\t{h}\n" for n, h in sorted(files.items()))
    return _sha12(body.encode()), files


def _manifest(snap: Path) -> dict[str, Any]:
    try:
        data = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _snap_ts(snap: Path, manifest: dict[str, Any]) -> str:
    ts = manifest.get("ts")
    if isinstance(ts, str) and ts:
        return ts
    m = _TS_FROM_NAME.search(snap.name)
    if m:
        t = m.group(1)
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[9:11]}:{t[11:13]}:{t[13:15]}Z"
    return ""


def load_snapshots(root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    """Snapshot dirs with a manifest (a dir without one is incomplete), oldest first."""
    rows = []
    for snap in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = _manifest(snap)
        if not manifest:
            continue
        rows.append((_snap_ts(snap, manifest), snap, manifest))
    rows.sort(key=lambda r: (r[0], r[1].name))
    return rows


def change_series(snaps: list[tuple[str, Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind in KINDS:
        prev: tuple[str, Path, str, dict[str, str]] | None = None
        for ts, snap, _m in snaps:
            state = kind_state(snap, kind)
            if state is None:
                continue
            sha, files = state
            if prev is not None and prev[2] != sha:
                out.append(
                    {
                        "kind": kind,
                        "from_snapshot": prev[1].name,
                        "to_snapshot": snap.name,
                        "ts_from": prev[0],
                        "ts_to": ts,
                        "sha_before": prev[2],
                        "sha_after": sha,
                        "files_added": sorted(set(files) - set(prev[3])),
                        "files_removed": sorted(set(prev[3]) - set(files)),
                    }
                )
            prev = (ts, snap, sha, files)
    out.sort(key=lambda r: (r["ts_to"], r["kind"]))
    return out


def serving_candidates(snaps: list[tuple[str, Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    last: dict[str, tuple[str, str, Any]] = {}  # key -> (snapshot name, ts, value)
    out: list[dict[str, Any]] = []
    for ts, snap, manifest in snaps:
        changed: dict[str, list[Any]] = {}
        frm = ""
        frm_ts = ""
        for key in SERVING_KEYS:
            value = manifest.get(key)
            if value is None:
                continue
            if key in last and last[key][2] != value:
                changed[key] = [last[key][2], value]
                frm, frm_ts = last[key][0], last[key][1]
            last[key] = (snap.name, ts, value)
        if changed:
            out.append(
                {
                    "kind": "serving_env",
                    "status": "candidate",
                    "from_snapshot": frm,
                    "to_snapshot": snap.name,
                    "ts_from": frm_ts,
                    "ts_to": ts,
                    "changed": changed,
                }
            )
    return out


def build(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snaps = load_snapshots(root)
    coverage = {
        "snapshots": len(snaps),
        "first_ts": snaps[0][0] if snaps else None,
        "last_ts": snaps[-1][0] if snaps else None,
    }
    doc = {"coverage": coverage, "changes": change_series(snaps)}
    return doc, serving_candidates(snaps)


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("snapshots", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidates-out", type=Path)
    args = ap.parse_args(argv)
    if not args.snapshots.is_dir():
        print(f"ERROR: snapshots dir not found: {args.snapshots}", file=sys.stderr)
        return 1
    doc, candidates = build(args.snapshots)
    _write(args.out, doc)
    if args.candidates_out:
        _write(args.candidates_out, candidates)
    cov = doc["coverage"]
    print(
        f"value-layer-change-series: {cov['snapshots']} snapshots, "
        f"{len(doc['changes'])} changes, {len(candidates)} serving_env candidates"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
