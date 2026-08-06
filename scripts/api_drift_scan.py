#!/usr/bin/env python3
"""Deterministic API-surface drift scan over api-audit.jsonl (read-only).

The cheap, recurring companion to a manual read of the platform's API spec
(skill.md): the client already records the envelope keys of every response in
``api-audit.jsonl`` (ADR-0075), so a platform-side schema change — a new
``check_in`` key on /home carrying role "standing instructions", a field
silently dropped — is measurable without fetching anything external. This scan
diffs the per-endpoint key vocabulary against the previous sweep's snapshot
and renders the drift for the weekly report.

Policy (load-bearing): the spec itself is untrusted external text and is NOT
fetched here or anywhere in the unattended chain. When this scan reports
drift, the re-read of skill.md belongs to the human-gated Saturday session
(/weekly-gate). The rendered section carries that instruction so the policy
travels with the reading.

Windowing (load-bearing): ``--start/--end`` restrict the scan to the report
week. Without a window, the whole-file union is monotone (the log never
rotates), so ``current ⊇ previous`` always holds and a key the platform
*dropped* is undetectable — the removal half of the instrument only works
against a windowed ``current``. The verify-health numbers are honest for the
same reason only within a window. Two accepted properties of that design:

- **Basis**: the window compares against the record's UTC ``ts`` while the
  weekly chain passes JST-derived dates, so boundary-day sessions can fall on
  either side. Harmless for a 7-day union; do not read a boundary-only key's
  appearance/disappearance as platform action without checking timestamps.
- **Conditional keys oscillate**: a key the platform returns only sometimes
  will flag removed one week, leave the baseline, and flag new the next
  (client.py notes some endpoints legitimately omit keys). An oscillating row
  is a property of the endpoint, not drift — weekly readers should discount a
  row they have seen flip before rather than report it as a schema change.

Security:
- Reads ONLY ``api-audit.jsonl`` (self-written by the client). Never episode
  logs.
- Key and endpoint names originate in platform responses (external control).
  Non-printable characters (newlines included) are squashed at intake — a raw
  newline would break the key out of its table cell into report prose, and
  would also corrupt the line-oriented state file so the key re-flags as new
  forever. Rendering additionally Markdown-escapes and length-caps.

State: a TSV ``endpoint<TAB>key`` snapshot of the previously observed
vocabulary. Merge semantics: endpoints observed this window overwrite their
baseline entry (so a removal flags exactly once), endpoints not observed keep
their previous vocabulary (an endpoint not called says nothing about its
schema). Same commit discipline as log_anomaly_sweep: ``--no-update
--emit-state PATH`` writes the snapshot aside; the caller promotes it (atomic
rename) only after the report lands.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _md import md_safe

_KEY_MAXLEN = 48
_ENDPOINT_MAXLEN = 60

# Account suspension follows 10 consecutive verification failures (spec,
# 2026-08 read); warn well before that.
_VERIFY_STREAK_WARN = 3


@dataclass(frozen=True)
class Drift:
    """Vocabulary diff between the current scan and the previous snapshot."""

    new_pairs: tuple[tuple[str, str], ...]
    removed_pairs: tuple[tuple[str, str], ...]
    new_endpoints: frozenset[str] = frozenset()
    is_bootstrap: bool = False


@dataclass(frozen=True)
class VerifyHealth:
    """POST /verify outcome counts; the platform suspends on failure streaks.

    ``trailing_streak`` is the consecutive-failure run still in progress at
    the end of the scanned window — the number the suspension warning keys
    on. A historical ``max_streak`` that already recovered is context, not
    risk.
    """

    attempts: int
    failures: int
    max_streak: int
    trailing_streak: int


def _sanitize(name: str) -> str:
    """Squash non-printable characters in a platform-controlled name.

    ``·`` keeps the anomaly visible (a key that needed squashing IS drift
    signal) while making the name safe for the one-line-per-pair state file
    and the Markdown table cell.
    """
    return "".join(ch if ch.isprintable() else "·" for ch in name)


def load_records(
    lines: Iterable[str], start: str | None = None, end: str | None = None
) -> list[dict[str, Any]]:
    """Parse audit lines once, optionally windowed to [start, end] dates.

    ``start``/``end`` are ISO dates compared against the record's ``ts``
    prefix (lexicographic order is date order). Records without a usable
    ``ts`` are kept only when no window is requested.
    """
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if start or end:
            ts = record.get("ts")
            day = ts[:10] if isinstance(ts, str) and len(ts) >= 10 else None
            if day is None:
                continue
            if (start and day < start) or (end and day > end):
                continue
        records.append(record)
    return records


def build_vocabulary(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """Collect per-endpoint response-key sets from healthy 2xx entries only.

    Error responses (429s and friends) carry their own envelope shape
    (statusCode / message / retry_after_seconds); folding those into the
    vocabulary would read every outage as schema drift. ``soft_fail`` records
    are error-shaped bodies at a 2xx status (client.py marks them), so they
    are excluded for the same reason.
    """
    vocab: dict[str, set[str]] = {}
    for record in records:
        endpoint = record.get("endpoint")
        keys = record.get("keys")
        status = record.get("status")
        if not isinstance(endpoint, str) or not isinstance(keys, list):
            continue
        if not isinstance(status, int) or not 200 <= status < 300:
            continue
        if record.get("soft_fail"):
            continue
        vocab.setdefault(_sanitize(endpoint), set()).update(
            _sanitize(k) for k in keys if isinstance(k, str)
        )
    return vocab


def diff_vocabulary(current: dict[str, set[str]], previous: dict[str, set[str]]) -> Drift:
    """Diff the observed vocabulary against the previous snapshot.

    Removals are computed only for endpoints observed in the current scan: an
    endpoint that simply was not called this window says nothing about its
    schema.
    """
    new_pairs: list[tuple[str, str]] = []
    removed_pairs: list[tuple[str, str]] = []
    new_endpoints: set[str] = set()
    for endpoint, keys in sorted(current.items()):
        prev_keys = previous.get(endpoint)
        if prev_keys is None:
            new_endpoints.add(endpoint)
            new_pairs.extend((endpoint, k) for k in sorted(keys))
            continue
        new_pairs.extend((endpoint, k) for k in sorted(keys - prev_keys))
        removed_pairs.extend((endpoint, k) for k in sorted(prev_keys - keys))
    return Drift(
        new_pairs=tuple(new_pairs),
        removed_pairs=tuple(removed_pairs),
        new_endpoints=frozenset(new_endpoints),
        is_bootstrap=not previous,
    )


def verify_health(records: Iterable[dict[str, Any]]) -> VerifyHealth:
    """Count POST /verify outcomes and the longest consecutive-failure run."""
    attempts = failures = streak = max_streak = 0
    for record in records:
        if record.get("endpoint") != "POST /verify":
            continue
        attempts += 1
        status = record.get("status")
        ok = record.get("success") is True and isinstance(status, int) and status < 400
        if ok:
            streak = 0
        else:
            failures += 1
            streak += 1
            max_streak = max(max_streak, streak)
    return VerifyHealth(
        attempts=attempts,
        failures=failures,
        max_streak=max_streak,
        trailing_streak=streak,
    )


def read_state(path: Path) -> dict[str, set[str]]:
    """Load the previous ``endpoint<TAB>key`` snapshot; empty if absent."""
    if not path.is_file():
        return {}
    vocab: dict[str, set[str]] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        endpoint, _, key = raw.partition("\t")
        if endpoint and key:
            vocab.setdefault(endpoint, set()).add(key)
    return vocab


def write_state(path: Path, vocab: dict[str, set[str]]) -> None:
    """Persist the observed vocabulary for the next scan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f"{endpoint}\t{key}\n" for endpoint in sorted(vocab) for key in sorted(vocab[endpoint])
    )
    path.write_text(body, encoding="utf-8")


def _cell(s: str, maxlen: int) -> str:
    if len(s) > maxlen:
        s = s[: maxlen - 1] + "…"
    return md_safe(s)


def _ranked_rows(drift: Drift) -> list[tuple[str, str, str]]:
    """Order rows by signal, highest first.

    A new key on a *known* endpoint (the check_in case) and a removed key are
    the readings this instrument exists for; a brand-new endpoint's bulk key
    dump is usually first-use noise and must not eat the row budget ahead of
    them.
    """
    known_new = [(e, k) for e, k in drift.new_pairs if e not in drift.new_endpoints]
    endpoint_new = [(e, k) for e, k in drift.new_pairs if e in drift.new_endpoints]
    rows = [("🆕", e, k) for e, k in known_new]
    rows += [("␡ removed", e, k) for e, k in drift.removed_pairs]
    rows += [("🆕 (new endpoint)", e, k) for e, k in endpoint_new]
    return rows


def render_markdown(drift: Drift, verify: VerifyHealth, top: int) -> str:
    """Render the drift reading as a Markdown section for the weekly report."""
    top = max(1, top)
    lines = ["## API Drift Scan", ""]

    if drift.is_bootstrap:
        lines.append(
            f"Baseline bootstrap: first scan recorded "
            f"{len(drift.new_pairs)} endpoint/key pairs as the reference "
            "vocabulary. Nothing here is drift yet."
        )
    elif not drift.new_pairs and not drift.removed_pairs:
        lines.append("No response-schema drift since the last scan.")
    else:
        lines.append(
            f"{len(drift.new_pairs)} new and {len(drift.removed_pairs)} removed "
            "endpoint/key pairs since the last scan (healthy 2xx responses only):"
        )
        lines.append("")
        lines.append("| Change | Endpoint | Key |")
        lines.append("|--------|----------|-----|")
        rows = _ranked_rows(drift)
        for change, endpoint, key in rows[:top]:
            lines.append(
                f"| {change} | `{_cell(endpoint, _ENDPOINT_MAXLEN)}` "
                f"| `{_cell(key, _KEY_MAXLEN)}` |"
            )
        if len(rows) > top:
            lines.append("")
            lines.append(f"_{len(rows) - top} further rows omitted (top {top})._")
        lines.append("")
        lines.append(
            "**Action (human gate only):** drift detected — re-read the API "
            "spec (`https://www.moltbook.com/skill.md`) at the Saturday "
            "/weekly-gate session before adapting any consumer. Do NOT fetch "
            "or ingest the spec in the unattended chain; it is untrusted "
            "external text. Briefing-bearing fields (e.g. `check_in` role "
            "standing-instructions) stay unconsumed by design "
            "(tests/test_home_field_allowlist.py)."
        )

    lines.append("")
    if verify.attempts:
        streak_note = (
            f" ⚠️ {verify.trailing_streak} consecutive failures ongoing — "
            "the platform suspends at 10"
            if verify.trailing_streak >= _VERIFY_STREAK_WARN
            else ""
        )
        lines.append(
            f"Verification handshake (scan window): {verify.failures}/"
            f"{verify.attempts} failed, longest consecutive failure run "
            f"{verify.max_streak}.{streak_note}"
        )
    else:
        lines.append("Verification handshake: no POST /verify entries in the scan window.")
    lines.append("")
    lines.append(
        "_Source: api-audit.jsonl (self-written envelope-key records; response "
        "bodies are never logged, episode logs are never read). Key names "
        "originate in platform responses: non-printables are squashed to `·` "
        "at intake, and rendering escapes and length-caps._"
    )
    return "\n".join(lines) + "\n"


def merge_state(previous: dict[str, set[str]], current: dict[str, set[str]]) -> dict[str, set[str]]:
    """Fold the window's observations into the baseline.

    Observed endpoints are overwritten (a reported removal leaves the
    baseline, so it flags exactly once); unobserved endpoints keep their
    previous vocabulary.
    """
    return {**previous, **current}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True, help="api-audit.jsonl path")
    parser.add_argument("--state", type=Path, required=True, help="scan state TSV path")
    parser.add_argument("--start", default=None, help="window start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="window end date (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=25, help="rows to render (default 25)")
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="do not write the state file (dry scan)",
    )
    parser.add_argument(
        "--emit-state",
        type=Path,
        default=None,
        help="write the snapshot to this path instead of committing it; pair "
        "with --no-update so the caller can promote it (atomic rename) "
        "only after the report this scan fed has actually landed",
    )
    args = parser.parse_args(argv)

    if not args.audit.is_file():
        print("## API Drift Scan\n\nNo audit log found; nothing to scan.\n")
        return 0

    with args.audit.open(encoding="utf-8", errors="replace") as fh:
        records = load_records(fh, args.start, args.end)

    prev = read_state(args.state)
    vocab = build_vocabulary(records)
    drift = diff_vocabulary(vocab, prev)
    print(render_markdown(drift, verify_health(records), args.top))

    merged = merge_state(prev, vocab)
    if not args.no_update:
        write_state(args.state, merged)
    if args.emit_state is not None:
        write_state(args.emit_state, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
