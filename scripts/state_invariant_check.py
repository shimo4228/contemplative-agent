#!/usr/bin/env python3
"""Deterministic state-invariant check over persisted agent state (read-only).

The structural companion to the log-anomaly sweep: where the sweep watches the
*event stream* (logs), this watches the *accumulated state* for silent drift —
the failure mode that tests miss because they never observe how state evolves
across many runs (dead metadata that never sheds, dedup leaks, tombstone
build-up, schema fields from sunset ADRs).

Each invariant is an absolute "this should hold" check (no novelty/state needed,
unlike the sweep). A clean run confirms the invariants; the value is catching a
regression week over week.

Security: reads ONLY the distilled state — ``knowledge.json``, its
embedding sidecar (ADR-0108, ids only) and ``agents.json``. It MUST NEVER read the episode logs (``logs/*.jsonl``); those
are untrusted external content and this output may be fed to an LLM. Pattern
texts in knowledge.json are the agent's own distilled self-content (already the
input to distill/identity LLMs), so truncated samples are included; raw external
bodies never appear here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from _audit import parse_ts
from _md import md_safe

T = TypeVar("T")

# Fields retired by ADRs — a pattern is meant to shed these on its next save.
# Their presence means dead metadata is still round-tripping (drift), not
# corruption. Only definitively-retired fields are listed, to avoid flagging
# live telemetry as a violation.
SUNSET_FIELDS = {
    "trust_score": "ADR-0051",
    "trust_updated_at": "ADR-0051",
    "importance": "ADR-0056",
    "access_count": "ADR-0028",
    "last_accessed": "ADR-0028",
    "last_accessed_at": "ADR-0028",
    "success_count": "ADR-0028",
    "failure_count": "ADR-0028",
    "restored_from_evolution_at": "ADR-0034",
    "category": "ADR-0026",
}

# Above this share of soft-invalidated (tombstoned) rows, warn that the live
# pool is being dwarfed by never-pruned history (bitemporal design, ADR-0021,
# so the ratio only grows — INFO below the line, WARN above it).
_SOFT_INVALID_WARN_RATIO = 0.40

_SAMPLE_MAXLEN = 60
_MAX_SAMPLES = 3

_OK, _INFO, _WARN, _FAIL = "OK", "INFO", "WARN", "FAIL"


@dataclass(frozen=True)
class InvariantResult:
    """One invariant's outcome."""

    name: str
    level: str  # OK | INFO | WARN | FAIL
    summary: str
    samples: tuple[str, ...] = ()


def _parses_as_timestamp(ts: str) -> bool:
    """Whether *ts* is a timestamp at all, via the shared scripts/ parser.

    The invariant asks "is this a timestamp", not "is this our spelling", so
    the shared parser's extra tolerance (a trailing ``Z``) is in the right
    direction — and its grammar has one owner.
    """
    return bool(ts) and ts != "unknown" and parse_ts(ts) is not None


def _verdict(
    name: str,
    bad: object,
    level: str,
    bad_summary: str,
    ok_summary: str,
    samples: tuple[str, ...] = (),
) -> InvariantResult:
    """One invariant's result: *level* when *bad* is non-empty, else OK.

    Every invariant below is the same two-armed sentence, and writing it out
    five times is how the arms drift apart — one arm counting live patterns
    and its partner counting all of them reads as a passing check.
    """
    if bad:
        return InvariantResult(name, level, bad_summary, samples)
    return InvariantResult(name, _OK, ok_summary)


def check_knowledge(
    patterns: list[dict], sidecar_ids: set[str] | None = None
) -> list[InvariantResult]:
    """Invariants over the knowledge.json pattern list.

    *sidecar_ids* is the id set of the ADR-0108 embedding sidecar; an empty
    set means "no sidecar", which is exactly what a pre-migration store and a
    restored-without-vectors store both look like.
    """
    sidecar_ids = sidecar_ids or set()
    results: list[InvariantResult] = []
    total = len(patterns)
    live = [p for p in patterns if p.get("valid_until") is None]

    # 1. Sunset fields still present (dead metadata not shed) — drift.
    field_hits: Counter[str] = Counter()
    for p in patterns:
        for f in p.keys():
            if f in SUNSET_FIELDS:
                field_hits[f] += 1
    detail = ", ".join(f"{f}×{n} ({SUNSET_FIELDS[f]})" for f, n in field_hits.most_common())
    results.append(
        _verdict(
            "sunset_fields",
            field_hits,
            _WARN,
            f"{sum(field_hits.values())} patterns carry retired fields: {detail}",
            "no retired ADR fields present",
        )
    )

    # 2. Required fields — corruption if missing.
    bad_required = [
        p
        for p in patterns
        if not isinstance(p.get("pattern"), str) or not p.get("pattern") or "distilled" not in p
    ]
    results.append(
        _verdict(
            "required_fields",
            bad_required,
            _FAIL,
            f"{len(bad_required)} patterns missing a valid pattern/distilled field",
            f"all {total} patterns have pattern+distilled",
        )
    )

    # 3. Timestamp validity (live patterns).
    bad_ts = [p for p in live if not _parses_as_timestamp(p.get("distilled", ""))]
    results.append(
        _verdict(
            "timestamp_validity",
            bad_ts,
            _FAIL,
            f"{len(bad_ts)}/{len(live)} live patterns have unparseable distilled timestamp",
            f"all {len(live)} live timestamps parseable",
        )
    )

    # 4. Duplicate live pattern texts (dedup leak).
    texts = Counter(p.get("pattern", "") for p in live)
    dups = {t: c for t, c in texts.items() if c > 1 and t}
    extra = sum(c - 1 for c in dups.values())
    results.append(
        _verdict(
            "duplicate_live_texts",
            dups,
            _WARN,
            f"{len(dups)} live texts duplicated ({extra} redundant rows) — dedup leak",
            "no duplicate live pattern texts",
            tuple(t[:_SAMPLE_MAXLEN] for t in list(dups)[:_MAX_SAMPLES]),
        )
    )

    # 5. Missing embedding among live (cannot participate in cosine dedup/views).
    # ADR-0108 moved the vectors to a sidecar, so presence is now a question
    # about two files: an inline vector (pre-migration row) OR a sidecar row
    # under this pattern's id. Asking the JSON alone would report every
    # migrated pattern as unembedded.
    no_emb = [p for p in live if not p.get("embedding") and _pattern_id(p) not in sidecar_ids]
    results.append(
        _verdict(
            "missing_embedding",
            no_emb,
            _FAIL,
            f"{len(no_emb)}/{len(live)} live patterns have no embedding",
            f"all {len(live)} live patterns embedded",
        )
    )

    # 6. Soft-invalidated ratio (tombstone build-up; grows by design).
    invalid = total - len(live)
    ratio = (invalid / total) if total else 0.0
    level = _WARN if ratio >= _SOFT_INVALID_WARN_RATIO else _INFO
    results.append(
        InvariantResult(
            "soft_invalidated_ratio",
            level,
            f"{invalid}/{total} ({ratio:.1%}) soft-invalidated (tombstones, ADR-0021)",
        )
    )

    return results


def check_agents(agents: dict) -> list[InvariantResult]:
    """Invariants over agents.json."""
    followed = agents.get("followed", []) if isinstance(agents, dict) else []
    if not isinstance(followed, list):
        return [InvariantResult("agents_followed", _FAIL, "followed is not a list")]
    dup = len(followed) - len(set(followed))
    if dup:
        return [
            InvariantResult(
                "agents_followed",
                _WARN,
                f"followed has {dup} duplicate entries ({len(followed)} total)",
            )
        ]
    return [InvariantResult("agents_followed", _OK, f"{len(followed)} followed agents, all unique")]


def _drop_embedding_vectors(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Object hook that keeps ``embedding`` as a bool instead of its vector.

    knowledge.json is ~190 MB, ~97% of it 768-dim float vectors, and the only
    question any invariant here asks of ``embedding`` is whether one is present
    (invariant 5). Without this the whole vector graph — millions of Python
    floats — stays alive for the run, on a 16 GB box that also hosts Ollama.
    Each vector is still built transiently by the parser; it is freed here
    instead of being retained.
    """
    return {k: bool(v) if k == "embedding" else v for k, v in pairs}


def _load_typed(path: Path, expected: type[T], default: T) -> T:
    """Read a JSON file, returning the loaded value only if it has *expected*
    type; silently fall back to ``default`` on IO / parse / type error.
    """
    if path.is_file():
        try:
            loaded = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=_drop_embedding_vectors
            )
            if isinstance(loaded, expected):
                return loaded
        except (OSError, json.JSONDecodeError):
            pass
    return default


def _pattern_id(p: dict) -> str:
    """ADR-0050 content-hash id, restated rather than imported.

    This script is standalone by design (it ships beside ``_audit`` / ``_md``
    and runs from the weekly chain without the package installed). The recipe
    is two lines and is pinned by ``tests/test_state_invariant_check.py``
    against ``knowledge_store.pattern_id``, so the copy cannot drift silently.
    """
    raw = f"{p.get('distilled', '')}|{p.get('pattern', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def load_sidecar_ids(home: Path) -> set[str]:
    """Pattern ids present in the embedding sidecar (ADR-0108) — ids only.

    No vectors are read: the only question any invariant asks is presence, and
    on a 16 GB box this file is the one whose bulk the sidecar split existed to
    avoid resident. An unreadable or absent sidecar reads as empty, which
    invariant 5 then reports as missing embeddings — the visible state, not a
    swallowed error.
    """
    path = home / "pattern-embeddings.sqlite"
    if not path.is_file():
        return set()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return set()
    try:
        rows = conn.execute("SELECT pattern_id, dim FROM pattern_embeddings").fetchall()
    except sqlite3.Error:
        return set()
    finally:
        conn.close()
    if not rows:
        return set()
    # Width matters, not just presence. The loader keeps only the dominant
    # width and drops the rest as ``dim_mismatch`` (an embedding-model change
    # without a re-backfill), so counting a narrower row as "embedded" here
    # would report OK for exactly the rows the store refuses to use — the two
    # readers of the same file would disagree (code review 2026-09-12).
    widths: Counter[int] = Counter(int(dim) for _, dim in rows)
    dominant, _ = widths.most_common(1)[0]
    return {pid for pid, dim in rows if int(dim) == dominant}


def load_state(home: Path) -> tuple[list[dict], dict]:
    """Read knowledge.json + agents.json (never episode logs)."""
    patterns = _load_typed(home / "knowledge.json", list, [])
    agents = _load_typed(home / "agents.json", dict, {})
    return patterns, agents


_LEVEL_ICON = {_OK: "✅", _INFO: "ℹ️", _WARN: "⚠️", _FAIL: "❌"}


def render_markdown(results: list[InvariantResult], *, read_at: str | None = None) -> str:
    """Render the invariant table.

    ``read_at`` stamps *when* the live store was read. Without it the counts
    below silently compete with the committed-snapshot counts in the weekly
    report's state diff, which are a different source measured at a different
    moment (ADR-0075: the reading exists, the label that makes it usable does
    not — findings F1.4).
    """
    lines = ["## State Invariant Check", ""]
    source = "live store" if read_at is None else f"live store, read at {read_at}"
    lines.append(
        f"Source: {source} — `total` counts every row in `knowledge.json`, "
        "so total = live + tombstones (ADR-0021). Committed-snapshot counts "
        "elsewhere in this report are a different source and moment."
    )
    lines.append("")
    fails = sum(1 for r in results if r.level == _FAIL)
    warns = sum(1 for r in results if r.level == _WARN)
    if fails:
        lines.append(f"**{fails} FAIL, {warns} WARN** — state invariants violated.")
    elif warns:
        lines.append(f"{warns} WARN, no FAIL — drift to watch, no corruption.")
    else:
        lines.append("All invariants hold.")
    lines.append("")
    lines.append("| | Invariant | Result |")
    lines.append("|----|-----------|--------|")
    for r in results:
        icon = _LEVEL_ICON.get(r.level, "")
        lines.append(f"| {icon} | `{r.name}` | {r.summary} |")
    samples = [(r.name, r.samples) for r in results if r.samples]
    if samples:
        lines.append("")
        for name, sample_list in samples:
            joined = "; ".join(f"`{md_safe(s)}`" for s in sample_list)
            lines.append(f"- {name} examples: {joined}")
    return "\n".join(lines) + "\n"


def run(home: Path) -> list[InvariantResult]:
    patterns, agents = load_state(home)
    return check_knowledge(patterns, load_sidecar_ids(home)) + check_agents(agents)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    args = parser.parse_args(argv)
    results = run(args.home)
    read_at = datetime.now().astimezone().isoformat(timespec="seconds")
    print(render_markdown(results, read_at=read_at))
    # Exit non-zero only on a hard FAIL so a caller can gate on corruption;
    # WARN/INFO are reporting-only.
    return 1 if any(r.level == _FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
