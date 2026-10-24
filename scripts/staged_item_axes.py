"""Per-axis columns for each staged insight candidate (P2-06.2, D-P2-06-1 = C).

Read-only. Prints one table row per ``$MOLTBOOK_HOME/.staged/*.meta.json`` with
the intake axes ADR-0080's 2026-08-26 amendment (section B) asks to keep apart,
each in its own column and none combined:

* ``surprise``       — the ADR-0096 reading the sidecar carries (rank/of, s_mean).
* ``nearest``        — the store neighbours the duplicate judge was shown
                       (sidecar ``nearest``, by name).
* ``stages``         — the naming kind / duplicate verdict, or the fail-open
                       reason when a stage gave none (sidecar ``stages``).
* ``novelty``        — the novelty gate's verdict for the candidate's cluster:
                       the latest ``novelty_judge`` record in
                       ``logs/insight-novelty.jsonl`` whose ``clusters`` names the
                       sidecar's ``topic`` (``judged`` / ``fail_open_*``).
                       Join key is the cluster label and "latest wins", so a
                       topic that recurs across weeks reads the newest run: the
                       sidecar is staged right after the run it came from.
* ``reply_rate of nearest`` — for each neighbour that has an outcome row, its
                       ``reply_rate`` (and ``injected_comments``) from the
                       latest ``pipeline/comment-outcomes/comment-outcomes-*.json``.
                       A neighbour with no row prints ``-`` ("no reading", not
                       "no replies").

No composite, no rank across columns, no recommendation: the reply rate is an
environment reading on the NEIGHBOURS (a staged candidate has never been
injected, so it has none of its own), a distribution and not a contribution
estimate (ADR-0106 D6/D7). Nothing here is read by a decision; the Saturday
gate reads the table beside each candidate in Step 4.

Consumption plan (ADR-0101; owned by ADR-0111's 2026-10-24 amendment):
(a) the gate reads the table once per Saturday, per staged candidate, while
insight continues; (b) after 8 weekly readings the gate writes one line in the
RFC-0042 / ADR-0111 reading — whether the columns, side by side, changed any
verdict, and whether ADR-0080 section B's "told apart on several axes" is met;
(c) removal: when insight stops (RFC-0042 review-when), delete this script and
the SKILL.md line; the sidecar fields stay as a record.

Reads ONLY: ``.staged/*.meta.json`` (self-written), ``logs/insight-novelty.jsonl``
(self-written; its base64 prompt/output fields are never decoded) and the
comment-outcomes JSON. Never episode logs. Stdlib only.

Usage:
    python3 scripts/staged_item_axes.py --home ~/.config/moltbook
        [--staged-dir DIR] [--comment-outcomes FILE] [--novelty-log FILE]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

NOVELTY_JUDGE_KIND = "novelty_judge"
_NAME_MAX = 60
_PRINTABLE = re.compile(r"[^\x20-\x7e]")


def _clean(value: object, max_len: int = _NAME_MAX) -> str:
    """Printable ASCII, no pipes or backticks (a table cell), capped."""
    text = _PRINTABLE.sub("", str(value))[:max_len]
    return text.replace("|", "/").replace("`", "'")


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        out = float(value)
    except (OverflowError, ValueError):
        return None
    return out if math.isfinite(out) else None


def read_sidecars(staged_dir: Path) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for path in sorted(staged_dir.glob("*.meta.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append((path.name, {"_unreadable": True}))
            continue
        out.append((path.name, data if isinstance(data, dict) else {"_unreadable": True}))
    return out


def _judge_record(line: str) -> dict | None:
    """The line as a novelty-judge record, or None (bad JSON, deferral rows, other kinds)."""
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    if not isinstance(rec, dict):
        return None
    kind = rec.get("kind")
    if kind is not None:
        return rec if kind == NOVELTY_JUDGE_KIND else None
    # Legacy kind-less rows: the deferral writer's rows are not verdicts.
    return None if rec.get("reason") == "review_budget_deferred" else rec


def latest_novelty_by_topic(log: Path, topics: set[str]) -> dict[str, dict]:
    """``{topic: {"verdict", "covered", "ts"}}`` from the newest judge record naming it."""
    found: dict[str, dict] = {}
    if not topics or not log.is_file():
        return found
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return found
    for line in lines:
        rec = _judge_record(line)
        clusters = rec.get("clusters") if rec else None
        if rec is None or not isinstance(clusters, list):
            continue
        covered = rec.get("covered")
        ts = rec.get("ts") if isinstance(rec.get("ts"), str) else ""
        for topic in topics.intersection(c for c in clusters if isinstance(c, str)):
            if topic not in found or ts >= found[topic]["ts"]:
                found[topic] = {
                    "verdict": rec.get("verdict"),
                    "covered": isinstance(covered, list) and topic in covered,
                    "ts": ts,
                }
    return found


def reply_rates(outcomes_path: Path | None) -> dict[str, tuple[float, int]]:
    if outcomes_path is None:
        return {}
    try:
        data = json.loads(outcomes_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, tuple[float, int]] = {}
    for row in (data.get("skills") if isinstance(data, dict) else None) or []:
        if not isinstance(row, dict) or not isinstance(row.get("skill"), str):
            continue
        rate, n = _num(row.get("reply_rate")), row.get("injected_comments")
        if rate is not None and isinstance(n, int) and not isinstance(n, bool):
            out[row["skill"]] = (rate, n)
    return out


def _surprise_cell(meta: dict) -> str:
    s = meta.get("surprise")
    if not isinstance(s, dict):
        return "-"
    rank, of, mean = _num(s.get("rank")), _num(s.get("of")), _num(s.get("s_mean"))
    if rank is None or of is None or mean is None:
        return "unusable"
    return f"rank {rank:.0f}/{of:.0f}, s_mean={mean:.4f}"


def _stages_cell(meta: dict) -> str:
    st = meta.get("stages")
    if not isinstance(st, dict):
        return "-"

    def _one(verdict_key: str, fail_key: str) -> str:
        v, f = st.get(verdict_key), st.get(fail_key)
        if isinstance(v, str):
            return _clean(v, 20)
        return f"unjudged({_clean(f, 24)})" if isinstance(f, str) else "-"

    fo = " fail-open-novelty" if st.get("novelty_fail_open") is True else ""
    return f"naming={_one('naming_kind', 'naming_fail')} duplicate={_one('duplicate_verdict', 'duplicate_fail')}{fo}"


def _nearest(meta: dict) -> list[str]:
    near = meta.get("nearest")
    return [_clean(n) for n in near[:5] if isinstance(n, str)] if isinstance(near, list) else []


def _novelty_cell(meta: dict, novelty: dict[str, dict]) -> str:
    topic = meta.get("topic")
    if not isinstance(topic, str) or topic not in novelty:
        return "no record"
    rec = novelty[topic]
    verdict = _clean(rec["verdict"], 24) if isinstance(rec["verdict"], str) else "?"
    return verdict + (" (covered)" if rec["covered"] else "")


def render(
    sidecars: list[tuple[str, dict]],
    novelty: dict[str, dict],
    rates: dict[str, tuple[float, int]],
) -> str:
    lines = [
        "| staged item | surprise | stage verdicts | novelty gate | nearest (store) | reply_rate of nearest |",
        "|---|---|---|---|---|---|",
    ]
    for name, meta in sidecars:
        if meta.get("_unreadable"):
            lines.append(f"| {_clean(name, 80)} | sidecar unreadable | | | | |")
            continue
        near = _nearest(meta)
        rate_cell = (
            ", ".join(
                f"{n}: {rates[n][0]:.2f} (n={rates[n][1]})" if n in rates else f"{n}: -"
                for n in near
            )
            or "-"
        )
        lines.append(
            f"| {_clean(name, 80)} | {_surprise_cell(meta)} | {_stages_cell(meta)} "
            f"| {_novelty_cell(meta, novelty)} | {', '.join(near) or '-'} | {rate_cell} |"
        )
    lines.append("")
    lines.append(
        "Columns are separate readings, not combined. `reply_rate` is the neighbours' "
        "distribution (ADR-0106 D6), not a property of the candidate; `-` is no reading."
    )
    return "\n".join(lines) + "\n"


def _latest_outcomes(home: Path) -> Path | None:
    files = sorted((home / "pipeline" / "comment-outcomes").glob("comment-outcomes-*.json"))
    return files[-1] if files else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--home", required=True, help="MOLTBOOK_HOME")
    ap.add_argument("--staged-dir", default=None)
    ap.add_argument("--comment-outcomes", default=None)
    ap.add_argument("--novelty-log", default=None)
    args = ap.parse_args()

    home = Path(args.home)
    staged_dir = Path(args.staged_dir) if args.staged_dir else home / ".staged"
    if not staged_dir.is_dir():
        print(f"reason=STAGED_AXES_NO_STAGED_DIR {staged_dir}", file=sys.stderr)
        return 2
    sidecars = read_sidecars(staged_dir)
    if not sidecars:
        print("No staged items.")
        return 0
    log = Path(args.novelty_log) if args.novelty_log else home / "logs" / "insight-novelty.jsonl"
    outcomes = Path(args.comment_outcomes) if args.comment_outcomes else _latest_outcomes(home)
    topics = {m["topic"] for _, m in sidecars if isinstance(m.get("topic"), str)}
    sys.stdout.write(render(sidecars, latest_novelty_by_topic(log, topics), reply_rates(outcomes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
