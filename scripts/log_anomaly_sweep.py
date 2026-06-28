#!/usr/bin/env python3
"""Deterministic log-anomaly sweep over self-written logs (read-only).

The cheap, recurring companion to a full multi-agent audit: it intakes signal
that already exists in the runtime logs instead of generating new analysis.
Operational bugs ("気づかなかったバグ") accumulate as repeated warnings /
errors / truncations between runs; this surfaces them ranked by **novelty**
(new since the last sweep) then **frequency delta**, so a freshly-appearing or
spiking anomaly type floats to the top.

Security (load-bearing):
- Reads ONLY ``*.log`` (launchd / cron stderr, self-written) and ``audit.jsonl``
  (approval history, self-written). It MUST NEVER read the episode logs
  ``YYYY-MM-DD.jsonl`` (+ ``.bak``) — those are untrusted external content and a
  prompt-injection vector, and this output may be fed to an LLM.
- Output is normalized signatures (timestamps stripped, digits squashed,
  truncated), not verbatim log bodies, to shrink the injection surface further.

State: a TSV ``count<TAB>signature`` snapshot of the previous sweep, used to
compute the NEW flag and the per-signature delta.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from _md import md_safe

# A line is an anomaly candidate if (a) its log level is WARNING/ERROR/CRITICAL,
# or (b) it matches a level-agnostic critical pattern (these are real problems
# even when logged at INFO/DEBUG). Level keying keeps the verbose DEBUG/INFO
# operational trace (e.g. "circuit breaker open — skipping llm", logged every
# call) out of the sweep; the ranking (novelty + delta) handles the rest.
_LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")
_ATTENTION_LEVELS = {"WARNING", "ERROR", "CRITICAL"}
_CRITICAL_RE = re.compile(
    r"done_reason=length|truncat|num_ctx|\b429\b|backoff", re.IGNORECASE
)


def _is_signal(line: str) -> bool:
    if _CRITICAL_RE.search(line):
        return True
    m = _LEVEL_RE.search(line)
    return bool(m and m.group(1) in _ATTENTION_LEVELS)

# Files we are allowed to read. Episode logs (YYYY-MM-DD.jsonl) are excluded by
# construction: we never glob "*.jsonl".
_LOG_GLOB = "*.log"
_AUDIT_NAME = "audit.jsonl"

_TS_ISO_RE = re.compile(r"^\[?\d{4}-\d\d-\d\d[T ][\d:.\-+Z]*\]?\s*")
_TS_CLOCK_RE = re.compile(r"^\[?\d\d:\d\d:\d\d[.,]?\d*\]?\s*")
_DIGITS_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")

_SIG_MAXLEN = 80
_EXAMPLE_MAXLEN = 160


@dataclass(frozen=True)
class Finding:
    """One normalized anomaly type with its frequency and novelty."""

    signature: str
    count: int
    delta: int
    is_new: bool
    example: str


def normalize(line: str) -> str:
    """Collapse a log line into a stable signature.

    Strips the leading timestamp / clock prefix, lowercases, squashes digit
    runs to ``#`` (so numeric variation — counts, ids, ports — groups), and
    truncates. Agent-name variation is intentionally *not* squashed; minor
    over-splitting is safer than over-merging distinct anomalies.
    """
    s = _TS_ISO_RE.sub("", line)
    s = _TS_CLOCK_RE.sub("", s)
    s = s.strip().lower()
    s = _DIGITS_RE.sub("#", s)
    s = _WS_RE.sub(" ", s).strip()
    return s[:_SIG_MAXLEN]


def analyze(lines: Iterable[str], prev_counts: Dict[str, int]) -> List[Finding]:
    """Rank anomaly signatures by novelty then frequency delta.

    ``prev_counts`` is the previous sweep's ``signature -> count`` snapshot.
    A signature absent from it is NEW; otherwise the delta is the increase
    since last sweep. Sort: NEW first, then largest delta, then largest count.
    """
    counts: Counter[str] = Counter()
    examples: Dict[str, str] = {}
    for line in lines:
        if not _is_signal(line):
            continue
        sig = normalize(line)
        if not sig:
            continue
        counts[sig] += 1
        examples.setdefault(sig, line.strip()[:_EXAMPLE_MAXLEN])

    findings: List[Finding] = []
    for sig, count in counts.items():
        prev = prev_counts.get(sig, 0)
        # is_new conflates "first ever seen" with "seen before but absent from
        # the last snapshot" (state stores only the prior sweep's findings, not
        # full history). After log rotation a known signature can re-appear as
        # NEW — an accepted false-positive of the sparse-state design; the
        # weekly LLM reader can discount a familiar signature flagged new.
        findings.append(
            Finding(
                signature=sig,
                count=count,
                delta=count - prev,
                is_new=(prev == 0),
                example=examples[sig],
            )
        )
    findings.sort(key=lambda f: (not f.is_new, -f.delta, -f.count))
    return findings


def read_state(path: Path) -> Dict[str, int]:
    """Load the previous sweep's ``count<TAB>signature`` TSV; empty if absent."""
    if not path.is_file():
        return {}
    out: Dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        count_str, _, sig = raw.partition("\t")
        if not sig:
            continue
        try:
            out[sig] = int(count_str)
        except ValueError:
            continue
    return out


def write_state(path: Path, findings: Iterable[Finding]) -> None:
    """Persist the current ``count<TAB>signature`` snapshot for next time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{f.count}\t{f.signature}\n" for f in findings)
    path.write_text(body, encoding="utf-8")


def iter_allowed_log_lines(log_dir: Path) -> Iterable[str]:
    """Yield lines from *.log + audit.jsonl only. NEVER episode logs.

    Symlinks are skipped: a ``*.log`` symlink could otherwise redirect into an
    episode log (``2026-06-23.jsonl``) and breach the injection boundary the
    name-glob is meant to enforce. The logs dir is self-written (launchd stderr
    + audit_log), so a legitimate symlink is not expected.
    """
    files = sorted(log_dir.glob(_LOG_GLOB))
    audit = log_dir / _AUDIT_NAME
    if audit.is_file():
        files.append(audit)
    for f in files:
        if f.is_symlink():
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                yield from fh
        except OSError:
            continue


def render_markdown(findings: List[Finding], top: int) -> str:
    """Render the ranked findings as a Markdown section."""
    lines = ["## Log Anomaly Sweep", ""]
    if not findings:
        lines.append("No anomaly-signal lines found in `*.log` / `audit.jsonl`.")
        return "\n".join(lines) + "\n"
    new_count = sum(1 for f in findings if f.is_new)
    lines.append(
        f"{len(findings)} distinct anomaly types "
        f"({new_count} new since last sweep). Top {min(top, len(findings))} "
        f"by novelty then frequency delta:"
    )
    lines.append("")
    lines.append("| New | Count | Δ | Signature (normalized) |")
    lines.append("|----|------|----|------------------------|")
    for f in findings[:top]:
        flag = "🆕" if f.is_new else ""
        # Neutralize Markdown breakers so a signature cannot break out of its
        # code span in the downstream LLM prompt.
        sig = md_safe(f.signature)
        lines.append(f"| {flag} | {f.count} | {f.delta:+d} | `{sig}` |")
    lines.append("")
    lines.append(
        "_Signatures are normalized (timestamps stripped, digits squashed). "
        "Source: self-written logs only; episode logs are never read._"
    )
    return "\n".join(lines) + "\n"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True, help="MOLTBOOK_HOME/logs")
    parser.add_argument("--state", type=Path, required=True, help="sweep state TSV path")
    parser.add_argument("--top", type=int, default=25, help="rows to render (default 25)")
    parser.add_argument(
        "--no-update", action="store_true",
        help="do not write the state file (dry sweep)",
    )
    args = parser.parse_args(argv)

    prev = read_state(args.state)
    findings = analyze(iter_allowed_log_lines(args.log_dir), prev)
    print(render_markdown(findings, args.top))
    if not args.no_update:
        write_state(args.state, findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
