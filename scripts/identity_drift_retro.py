#!/usr/bin/env python3
"""Retroactive identity drift series from identity.md versions held on disk.

P3-04.8 / P3-04.9, a read-only instrument (ADR-0071; consumption plan in
ADR-0091's amendment). It applies the same measurement the live writer uses
(``core/identity_drift.measure_identity_drift``) to consecutive pairs of
identity versions and prints a Markdown table plus, with ``--jsonl``, the rows.

Inputs, in order: unique ``identity.md`` bodies found in ``--snapshots-dir``
(first appearance by snapshot timestamp), then ``--current`` if its body is new.
A snapshot taken at run start holds the identity that was live then, so the
series is ADOPTED versions only. Staged candidates that were rejected are not in
any public tree; the "all staged" series needs the private ``.staged/`` history
and ``logs/audit.jsonl`` on the owner's machine (``--extra FILE ...`` takes such
files in order).

P3-04.9 reuses the same measurement: ``--templates-dir config/templates --current
identity.md --embed`` prints the 11-template floor anchor, and ``--null-runs A B C
--embed`` prints the pairwise null-pair cosines of >= 3 runs on one corpus (generate
the runs on a COPY of the home so nothing is staged in production).

Cosine needs embeddings from Ollama (nomic-embed-text). ``--no-embed`` (default)
leaves the column empty so the table can be produced offline; pass ``--embed``
on the machine that runs Ollama. Counts only are shown when a denominator is
below 10; otherwise a Wilson interval from ``scripts/_stats.py`` is attached.
No rate line chart: n <= 12 sentences cannot carry one.

Usage::

    uv run --no-sync python scripts/identity_drift_retro.py \
        --snapshots-dir ../contemplative-agent-data/snapshots \
        --current ../contemplative-agent-data/identity.md [--embed] [--jsonl out.jsonl]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS.parent / "src"))

from _stats import wilson_ci  # noqa: E402

from contemplative_agent.core.identity_drift import (  # noqa: E402
    cosine_reading,
    measure_identity_drift,
)


def _no_embed(_texts: list[str]) -> None:
    return None


def collect_versions(
    snapshots_dir: Path | None, current: Path | None, extra: list[Path]
) -> list[tuple[str, str]]:
    """Return [(label, text)] of unique identity bodies in chronological order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(label: str, path: Path) -> None:
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen or not text.strip():
            return
        seen.add(digest)
        out.append((label, text))

    if snapshots_dir is not None:
        for snap in sorted(
            (p for p in snapshots_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name.rsplit("_", 1)[-1],
        ):
            add(snap.name, snap / "identity.md")
    for path in extra:
        add(path.name, path)
    if current is not None:
        add("current", current)
    return out


def _fmt(k: int, n: int) -> str:
    """Count k of n; a Wilson interval only when n >= 10."""
    ci = wilson_ci(k, n) if n >= 10 else None
    return f"{k}/{n}" + (f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "")


def table(rows: list[dict], labels: list[tuple[str, str]]) -> str:
    head = (
        "| from | to | bytes (from -> to) | cosine | retained / current sentences | "
        "novel / candidate sentences | any dissolution word (cand.) | fluid | dissolve | "
        "texture | tension | silence-permission (cur. -> cand.) |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = []
    for i, row in enumerate(rows):
        r, v = row["retention"], row["candidate_vocabulary"]
        n = v["sentences"]
        cos = "n/a (not embedded)" if row["cosine"] is None else f"{row['cosine']:.4f}"
        lines.append(
            f"| {labels[i][0]} | {labels[i + 1][0]} "
            f"| {len(labels[i][1].encode())} -> {len(labels[i + 1][1].encode())} | {cos} "
            f"| {_fmt(r['retained_sentences'], r['current_sentences'])} "
            f"| {_fmt(r['novel_sentences'], r['candidate_sentences'])} "
            f"| {_fmt(v['any'], n)} | {v['fluid']}/{n} | {v['dissolve']}/{n} "
            f"| {v['texture']}/{n} | {v['tension']}/{n} "
            f"| {'yes' if row['current_silence_permission'] else 'no'} -> "
            f"{'yes' if row['candidate_silence_permission'] else 'no'} |"
        )
    return head + "\n".join(lines) + "\n"


def anchor_table(current: str, templates: list[Path], embed) -> str:  # noqa: ANN001
    """P3-04.9 floor anchor: cosine of the current identity to each template identity.

    The templates are short, differently-sized documents, so the table shows the
    byte lengths and their ratio; read it stratified by length, not as one number.
    """
    lines = [
        "| template | bytes | cosine to current | length ratio (template / current) |",
        "|---|---|---|---|",
    ]
    cur_len = len(current.encode())
    for path in templates:
        text = path.read_text(encoding="utf-8")
        value, reason = cosine_reading(current, text, embed)
        cos = f"{value:.4f}" if value is not None else f"n/a ({reason})"
        n = len(text.encode())
        lines.append(f"| {path.parent.name} | {n} | {cos} | {n / cur_len:.2f} |")
    return "\n".join(lines) + "\n"


def null_pair_table(runs: list[Path], embed) -> str:  # noqa: ANN001
    """P3-04.9 null pairs: cosine between runs of one corpus (every pair among ``runs``)."""
    lines = ["| run A | run B | bytes (A, B) | cosine |", "|---|---|---|---|"]
    for i, a in enumerate(runs):
        for b in runs[i + 1 :]:
            ta, tb = a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")
            value, reason = cosine_reading(ta, tb, embed)
            cos = f"{value:.4f}" if value is not None else f"n/a ({reason})"
            lines.append(
                f"| {a.name} | {b.name} | {len(ta.encode())}, {len(tb.encode())} | {cos} |"
            )
    return "\n".join(lines) + "\n"


def _p9(args: argparse.Namespace) -> int:
    from contemplative_agent.core.embeddings import embed_texts

    embed = embed_texts if args.embed else _no_embed
    if args.templates_dir:
        if args.current is None:
            print("--templates-dir needs --current", file=sys.stderr)
            return 2
        files = sorted(args.templates_dir.glob("*/identity.md"))
        print(anchor_table(args.current.read_text(encoding="utf-8"), files, embed), end="")
    if args.null_runs:
        if len(args.null_runs) < 3:
            print("need at least 3 runs for >= 3 null pairs", file=sys.stderr)
            return 2
        print(null_pair_table(args.null_runs, embed), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--snapshots-dir", type=Path)
    ap.add_argument("--current", type=Path)
    ap.add_argument("--extra", type=Path, nargs="*", default=[])
    ap.add_argument("--embed", action="store_true", help="embed via Ollama (needs the server)")
    ap.add_argument("--jsonl", type=Path, help="also write the rows here")
    ap.add_argument(
        "--templates-dir",
        type=Path,
        help="config/templates: print the floor-anchor table (cosine of --current to each "
        "template identity.md) instead of the series (P3-04.9)",
    )
    ap.add_argument(
        "--null-runs",
        type=Path,
        nargs="+",
        help="identity texts from >= 3 distill-identity runs on one corpus: print the "
        "pairwise null-pair cosines instead of the series (P3-04.9)",
    )
    args = ap.parse_args(argv)
    if args.templates_dir or args.null_runs:
        return _p9(args)

    versions = collect_versions(args.snapshots_dir, args.current, args.extra)
    if len(versions) < 2:
        print("need at least two distinct identity versions", file=sys.stderr)
        return 2
    embed = _no_embed
    if args.embed:
        from contemplative_agent.core.embeddings import embed_texts

        embed = embed_texts
    rows = [
        measure_identity_drift(a[1], b[1], embed=embed)
        for a, b in zip(versions, versions[1:], strict=False)
    ]
    print(table(rows, versions), end="")
    if args.jsonl:
        args.jsonl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
