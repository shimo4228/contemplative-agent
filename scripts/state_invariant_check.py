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

Security: reads ONLY the distilled state — ``knowledge.json`` and
``agents.json``. It MUST NEVER read the episode logs (``logs/*.jsonl``); those
are untrusted external content and this output may be fed to an LLM. Pattern
texts in knowledge.json are the agent's own distilled self-content (already the
input to distill/identity LLMs), so truncated samples are included; raw external
bodies never appear here.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

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


def _md_safe(s: str) -> str:
    """Neutralize Markdown table/code-span breakers before LLM-facing output.

    Mirrors log_anomaly_sweep.render_markdown: a backtick would close the code
    span early, a pipe would misparse a table cell.
    """
    return s.replace("|", "\\|").replace("`", "'")


def _is_aware_or_naive_parseable(ts: str) -> bool:
    if not ts or ts == "unknown":
        return False
    try:
        datetime.fromisoformat(ts)
        return True
    except (ValueError, TypeError):
        return False


def check_knowledge(patterns: List[dict]) -> List[InvariantResult]:
    """Invariants over the knowledge.json pattern list."""
    results: List[InvariantResult] = []
    total = len(patterns)
    live = [p for p in patterns if p.get("valid_until") is None]

    # 1. Sunset fields still present (dead metadata not shed) — drift.
    field_hits: Counter[str] = Counter()
    for p in patterns:
        for f in p.keys():
            if f in SUNSET_FIELDS:
                field_hits[f] += 1
    if field_hits:
        detail = ", ".join(
            f"{f}×{n} ({SUNSET_FIELDS[f]})" for f, n in field_hits.most_common()
        )
        results.append(InvariantResult(
            "sunset_fields", _WARN,
            f"{sum(field_hits.values())} patterns carry retired fields: {detail}",
        ))
    else:
        results.append(InvariantResult(
            "sunset_fields", _OK, "no retired ADR fields present"))

    # 2. Required fields — corruption if missing.
    bad_required = [
        p for p in patterns
        if not isinstance(p.get("pattern"), str) or not p.get("pattern")
        or "distilled" not in p
    ]
    if bad_required:
        results.append(InvariantResult(
            "required_fields", _FAIL,
            f"{len(bad_required)} patterns missing a valid pattern/distilled field",
        ))
    else:
        results.append(InvariantResult(
            "required_fields", _OK, f"all {total} patterns have pattern+distilled"))

    # 3. Timestamp validity (live patterns).
    bad_ts = [p for p in live if not _is_aware_or_naive_parseable(p.get("distilled", ""))]
    if bad_ts:
        results.append(InvariantResult(
            "timestamp_validity", _FAIL,
            f"{len(bad_ts)}/{len(live)} live patterns have unparseable distilled timestamp",
        ))
    else:
        results.append(InvariantResult(
            "timestamp_validity", _OK, f"all {len(live)} live timestamps parseable"))

    # 4. Duplicate live pattern texts (dedup leak).
    texts = Counter(p.get("pattern", "") for p in live)
    dups = {t: c for t, c in texts.items() if c > 1 and t}
    if dups:
        extra = sum(c - 1 for c in dups.values())
        samples = tuple(t[:_SAMPLE_MAXLEN] for t in list(dups)[:_MAX_SAMPLES])
        results.append(InvariantResult(
            "duplicate_live_texts", _WARN,
            f"{len(dups)} live texts duplicated ({extra} redundant rows) — dedup leak",
            samples,
        ))
    else:
        results.append(InvariantResult(
            "duplicate_live_texts", _OK, "no duplicate live pattern texts"))

    # 5. Missing embedding among live (cannot participate in cosine dedup/views).
    no_emb = [p for p in live if not p.get("embedding")]
    if no_emb:
        results.append(InvariantResult(
            "missing_embedding", _FAIL,
            f"{len(no_emb)}/{len(live)} live patterns have no embedding",
        ))
    else:
        results.append(InvariantResult(
            "missing_embedding", _OK, f"all {len(live)} live patterns embedded"))

    # 6. Soft-invalidated ratio (tombstone build-up; grows by design).
    invalid = total - len(live)
    ratio = (invalid / total) if total else 0.0
    level = _WARN if ratio >= _SOFT_INVALID_WARN_RATIO else _INFO
    results.append(InvariantResult(
        "soft_invalidated_ratio", level,
        f"{invalid}/{total} ({ratio:.1%}) soft-invalidated (tombstones, ADR-0021)",
    ))

    return results


def check_agents(agents: dict) -> List[InvariantResult]:
    """Invariants over agents.json."""
    followed = agents.get("followed", []) if isinstance(agents, dict) else []
    if not isinstance(followed, list):
        return [InvariantResult("agents_followed", _FAIL, "followed is not a list")]
    dup = len(followed) - len(set(followed))
    if dup:
        return [InvariantResult(
            "agents_followed", _WARN,
            f"followed has {dup} duplicate entries ({len(followed)} total)")]
    return [InvariantResult(
        "agents_followed", _OK, f"{len(followed)} followed agents, all unique")]


def load_state(home: Path) -> tuple[List[dict], dict]:
    """Read knowledge.json + agents.json (never episode logs)."""
    patterns: List[dict] = []
    kj = home / "knowledge.json"
    if kj.is_file():
        try:
            loaded = json.loads(kj.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                patterns = loaded
        except (OSError, json.JSONDecodeError):
            pass
    agents: dict = {}
    aj = home / "agents.json"
    if aj.is_file():
        try:
            loaded = json.loads(aj.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                agents = loaded
        except (OSError, json.JSONDecodeError):
            pass
    return patterns, agents


_LEVEL_ICON = {_OK: "✅", _INFO: "ℹ️", _WARN: "⚠️", _FAIL: "❌"}


def render_markdown(results: List[InvariantResult]) -> str:
    lines = ["## State Invariant Check", ""]
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
            joined = "; ".join(f"`{_md_safe(s)}`" for s in sample_list)
            lines.append(f"- {name} examples: {joined}")
    return "\n".join(lines) + "\n"


def run(home: Path) -> List[InvariantResult]:
    patterns, agents = load_state(home)
    return check_knowledge(patterns) + check_agents(agents)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    args = parser.parse_args(argv)
    results = run(args.home)
    print(render_markdown(results))
    # Exit non-zero only on a hard FAIL so a caller can gate on corruption;
    # WARN/INFO are reporting-only.
    return 1 if any(r.level == _FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
