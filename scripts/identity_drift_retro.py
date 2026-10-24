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

from contemplative_agent.core.identity_drift import measure_identity_drift  # noqa: E402


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--snapshots-dir", type=Path)
    ap.add_argument("--current", type=Path)
    ap.add_argument("--extra", type=Path, nargs="*", default=[])
    ap.add_argument("--embed", action="store_true", help="embed via Ollama (needs the server)")
    ap.add_argument("--jsonl", type=Path, help="also write the rows here")
    args = ap.parse_args(argv)

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
