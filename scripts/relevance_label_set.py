#!/usr/bin/env python3
"""Label once, score many: the relevance face's frozen label set (RFC-0046 / RFC-0047 §3).

Four subcommands, one directory per label set
(``<main tree>/.notes/labels/relevance/<YYYY-MM-DD>/``):

1. ``sample`` — read ``logs/relevance-*.jsonl`` under ``--home`` (read-only),
   keep the rows since ``--since`` that are live-``scored`` and ``answered``,
   dedupe by ``post_id`` (earliest row wins), stratify on the live score with
   the RFC-0045 strata (``relevance_arm_replay.STRATA`` — below and above the
   live gate, the rejected side included; skill measurement-discipline §5) and
   draw ``--n`` rows with ``--seed``. Writes ``rows.jsonl`` (``content_b64``
   stays encoded — never plaintext) and ``manifest.json``, which pins every
   input the labels depend on: the ``identity.md`` sha256, the packaged
   ``relevance_score4.md`` / ``relevance.md`` sha256 and any home override's,
   ``DECISION_MODEL``, the served model, the seed, window and counts. Fewer
   than ``--n`` distinct rows: prints "M 行、不足" and exits 2 without writing.
2. ``label`` — claude-opus-5's two-valued label per row (``on_topic`` = the
   top level of the RFC-0045 ceiling rubric, ``ceiling_prompt``), through
   ``evals/judging.py::run_claude_raw`` only (the one cloud seam,
   tests/test_cloud_egress_absence.py). One call per row, resumable, appended to
   ``labels.jsonl``. Refuses (exit 2) when the manifest is stale — a label
   asked under a different identity is a different label. ``--dry-run`` builds
   every prompt and prints the count and the $ range; it calls nothing. The
   real run spends the operator's money and is the operator's to start.
3. ``score`` — re-score ``rows.jsonl`` × ``labels.jsonl`` deterministically
   with the production 4-level Score read (``relevance_arm_replay.run_logits``:
   ``OllamaLogprobsDecisionBackend``, no sampling): AUC of P(directly on-topic)
   and of the expected level against the label, precision / recall / agreement
   at t ∈ {0.3, 0.5, 0.7}, latency p50 / p95 — each its own axis, never a
   composite. ``--baseline`` compares with an earlier summary under the
   ``evals/compare.py`` exit contract: 2 incomparable (any pinned sha differs,
   or an AUC is missing), 1 regression (P(top) AUC down by more than 0.02),
   0 otherwise.
4. ``check`` — the manifest's shas against the tree and ``identity.md`` now
   (the ``evals/check_staleness.py`` shape): lists every stale item, exit 1
   stale / 0 fresh.

Output is refused outside the main tree's ``.notes/`` (a worktree's ``.notes/``
dies with the worktree — RFC-0046 Status); the rows carry other agents' posts,
so they never land in a tracked tree. Decoded post text reaches the model
prompts only — never stdout, a summary or a manifest.

dev-group script: ``uv run --no-sync python scripts/relevance_label_set.py …``.

Usage::

    uv run --no-sync python scripts/relevance_label_set.py sample \\
        --home ~/.config/moltbook --since 2026-09-25T06:20:00Z --n 150 --seed 20260926
    uv run --no-sync python scripts/relevance_label_set.py label --dir <dir> --dry-run
    uv run --no-sync python scripts/relevance_label_set.py score --dir <dir> \\
        [--baseline <old summary.json>] [--out <dir>/summary.json]
    uv run --no-sync python scripts/relevance_label_set.py check --dir <dir>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
# ``evals`` is imported from the repo root for ``label`` only
# (``evals/judging.py::run_claude_raw``); named in
# tests/test_cloud_egress_absence.py::EVALS_IMPORT_ALLOWLIST.
sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "relevance-label-set/1"
DEFAULT_LABEL_MODEL = "claude-opus-5"
DEFAULT_SCORE_MODEL = "gemma4:e4b"
# Per-row opus cost, RFC-0045's 300 calls at API rates ($37.73 → $0.13) up to
# the per-call spread it saw ($0.16).
COST_PER_ROW = (0.13, 0.16)
THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7)
REGRESSION_AUC_DROP = 0.02
ANSWERED = "answered"
SCORED = "scored"
# The shas a label depends on; any change makes the set a different set.
PINNED_KEYS = (
    "identity_sha256",
    "relevance_score4_sha256",
    "relevance_sha256",
    "relevance_score4_home_sha256",
    "relevance_home_sha256",
)
EXIT_OK, EXIT_REGRESSION, EXIT_INCOMPARABLE = 0, 1, 2


def replay() -> ModuleType:
    """``scripts/relevance_arm_replay.py``: strata, ceiling prompt, AUC, arm C."""
    name = "relevance_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = _REPO_ROOT / "scripts" / "relevance_arm_replay.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Paths and pins
# --------------------------------------------------------------------------


def main_tree() -> Path:
    """The main checkout, also from inside a worktree (git's common dir's parent)."""
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(_REPO_ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return _REPO_ROOT
    return Path(out).parent


def default_notes_root() -> Path:
    return main_tree() / ".notes"


def assert_private(path: Path, notes_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    root = notes_root.expanduser().resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"{resolved} is outside {root} — label sets go to .notes/ only")
    return resolved


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def pins(home: Path) -> dict[str, str | None]:
    """The shas of every input a label depends on, as the tree and home stand now."""
    from contemplative_agent.core.domain import DEFAULT_PROMPTS_DIR

    return {
        "identity_sha256": sha256_file(home / "identity.md"),
        "relevance_score4_sha256": sha256_file(DEFAULT_PROMPTS_DIR / "relevance_score4.md"),
        "relevance_sha256": sha256_file(DEFAULT_PROMPTS_DIR / "relevance.md"),
        # A home override changes production's question (core.prompts), not the
        # packaged one this asset asks — pinned so a divergence is visible.
        "relevance_score4_home_sha256": sha256_file(home / "prompts" / "relevance_score4.md"),
        "relevance_home_sha256": sha256_file(home / "prompts" / "relevance.md"),
    }


def stale_items(manifest: dict[str, Any], current: dict[str, str | None]) -> list[str]:
    return [
        f"{key}: {manifest.get(key)} -> {current.get(key)}"
        for key in PINNED_KEYS
        if manifest.get(key) != current.get(key)
    ]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_instant(text: str) -> datetime:
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# sample
# --------------------------------------------------------------------------


def candidate_rows(home: Path, since: datetime) -> list[dict[str, Any]]:
    """Answered, live-scored rows since *since*, one per post (earliest), by post_id."""
    kept: dict[str, dict[str, Any]] = {}
    for path in sorted((home / "logs").glob("relevance-*.jsonl")):
        for record in read_jsonl(path):
            ts = record.get("ts")
            score = record.get("live_score")
            if (
                not isinstance(ts, str)
                or parse_instant(ts) < since
                or record.get("live_reason") != SCORED
                or record.get("decision_reason") != ANSWERED
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not record.get("post_id")
                or not record.get("content_b64")
            ):
                continue
            post_id = str(record["post_id"])
            if post_id in kept and kept[post_id]["ts"] <= ts:
                continue
            kept[post_id] = {
                "post_id": post_id,
                "ts": ts,
                "live_score": float(score),
                "live_gate": record.get("live_gate"),
                "threshold_applied": record.get("threshold_applied"),
                "decision_p_top": record.get("decision_p_top"),
                "content_sha256": record.get("content_sha256"),
                "content_b64": record["content_b64"],
            }
    return [kept[key] for key in sorted(kept)]


def stratified(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """*n* rows spread over the live-score strata (short strata topped up)."""
    rar = replay()
    rng = random.Random(seed)
    by_stratum: dict[str, list[str]] = {name: [] for name, _lo, _hi in rar.STRATA}
    for row in rows:
        by_stratum[rar.stratum_of(row["live_score"])].append(row["post_id"])
    order = {name: rng.sample(ids, len(ids)) for name, ids in by_stratum.items()}
    quota = math.ceil(n / len(order))
    taken = rar._quota_take(order, quota)
    ids = [pid for name in order for pid in taken[name]][:n]
    index = {row["post_id"]: row for row in rows}
    stratum = {pid: name for name, pids in taken.items() for pid in pids}
    return [{**index[pid], "stratum": stratum[pid]} for pid in ids]


def cmd_sample(args: argparse.Namespace, notes_root: Path) -> int:
    since = parse_instant(args.since)
    rows = candidate_rows(args.home, since)
    if len(rows) < args.n:
        print(f"{len(rows)} 行、不足（dedupe 後 answered、--n {args.n}）")
        return EXIT_INCOMPARABLE
    out = assert_private(args.out, notes_root)
    chosen = stratified(rows, args.n, args.seed)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rows.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in chosen), encoding="utf-8"
    )
    from contemplative_agent.core.llm import served_model

    counts: dict[str, int] = {}
    for row in chosen:
        counts[row["stratum"]] = counts.get(row["stratum"], 0) + 1
    manifest = {
        "schema": SCHEMA,
        "home": str(args.home),
        **pins(args.home),
        "decision_model": os.environ.get("DECISION_MODEL"),
        "served_model": served_model(),
        "seed": args.seed,
        "rows": len(chosen),
        "population": len(rows),
        "strata": dict(sorted(counts.items())),
        "since": since.isoformat(),
        "window": {"first": min(r["ts"] for r in chosen), "last": max(r["ts"] for r in chosen)},
        "generated_at": _now(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"sampled {len(chosen)} of {len(rows)} rows into {out} (strata {manifest['strata']})")
    return EXIT_OK


# --------------------------------------------------------------------------
# label
# --------------------------------------------------------------------------


def load_set(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return manifest, read_jsonl(directory / "rows.jsonl")


def row_state(row: dict[str, Any], domain: str) -> dict[str, str]:
    text = base64.b64decode(row["content_b64"]).decode("utf-8", errors="replace")
    return replay().build_state(domain, text)


def cmd_label(args: argparse.Namespace, notes_root: Path) -> int:
    directory = assert_private(args.dir, notes_root)
    manifest, rows = load_set(directory)
    home = Path(manifest["home"])
    stale = stale_items(manifest, pins(home))
    if stale:
        print("stale label set — label refused:\n  " + "\n  ".join(stale))
        return EXIT_INCOMPARABLE
    rar = replay()
    domain = rar.read_domain(home / "identity.md")
    done = {label["post_id"] for label in read_jsonl(directory / "labels.jsonl")}
    todo = [row for row in rows if row["post_id"] not in done]
    prompts = [(row["post_id"], rar.ceiling_prompt(row_state(row, domain))) for row in todo]
    low, high = (len(prompts) * c for c in COST_PER_ROW)
    print(
        f"{len(prompts)} row(s) to label with {args.model} (≈ ${low:.2f}〜${high:.2f}); {len(done)} done"
    )
    if args.dry_run:
        return EXIT_OK
    from evals.judging import JudgeError, run_claude_raw

    scratch = directory / "scratch"
    scratch.mkdir(exist_ok=True)
    failures = 0
    with (directory / "labels.jsonl").open("a", encoding="utf-8") as sink:
        for post_id, prompt in prompts:
            try:
                raw = run_claude_raw(
                    prompt, model=args.model, scratch_dir=scratch, timeout=args.timeout
                )
            except JudgeError as exc:
                failures += 1
                print(f"{post_id[:12]}: {type(exc).__name__}", file=sys.stderr)
                continue
            level = rar.parse_level(raw)
            if level is None:
                failures += 1
                print(f"{post_id[:12]}: unparseable answer", file=sys.stderr)
                continue
            record = {
                "post_id": post_id,
                "on_topic": level == rar.TOP_LEVEL,
                "level": level,
                "raw": raw.strip()[:16],
                "model": args.model,
                "ts": _now(),
            }
            sink.write(json.dumps(record, sort_keys=True) + "\n")
            sink.flush()
    print(f"labelled {len(prompts) - failures}, failed {failures} (re-run resumes)")
    return EXIT_OK if failures == 0 else EXIT_REGRESSION


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def score_row(state: dict[str, str], model: str) -> dict[str, Any]:
    """Arm C's deterministic read (patch point for tests)."""
    return replay().run_logits(state, model)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


def cut_reading(scores: list[float], labels: list[bool], t: float) -> dict[str, float | None]:
    flags = [s >= t for s in scores]
    tp = sum(1 for f, y in zip(flags, labels, strict=True) if f and y)
    fp = sum(1 for f, y in zip(flags, labels, strict=True) if f and not y)
    fn = sum(1 for f, y in zip(flags, labels, strict=True) if not f and y)
    agree = sum(1 for f, y in zip(flags, labels, strict=True) if f == y)

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "agreement": ratio(agree, len(flags)),
        "gate_rate": ratio(sum(flags), len(flags)),
    }


def summarize(
    manifest: dict[str, Any], entries: list[tuple[dict[str, Any], bool]], model: str
) -> dict:
    rar = replay()
    answered = [(e, y) for e, y in entries if e.get("reason") == ANSWERED]
    p_top = [float(e["p_top"]) for e, _y in answered]
    expected = [float(e["score"]) for e, _y in answered]
    labels = [y for _e, y in answered]
    auc_top = rar.auc(p_top, labels)
    auc_expected = rar.auc(expected, labels)
    reasons: dict[str, int] = {}
    for e, _y in entries:
        reasons[str(e.get("reason"))] = reasons.get(str(e.get("reason")), 0) + 1
    latencies = [
        float(e["latency_ms"]) for e, _y in entries if isinstance(e.get("latency_ms"), int)
    ]
    return {
        "schema": SCHEMA,
        "manifest": {key: manifest.get(key) for key in PINNED_KEYS},
        "score_model": model,
        "labelled": len(entries),
        "answered": len(answered),
        "on_topic": sum(labels),
        "reasons": dict(sorted(reasons.items())),
        "auc_p_top": round(auc_top, 4) if auc_top is not None else None,
        "auc_expected_level": round(auc_expected, 4) if auc_expected is not None else None,
        "cuts": {f"{t:.1f}": cut_reading(p_top, labels, t) for t in THRESHOLDS},
        "latency_ms_p50": percentile(latencies, 0.5),
        "latency_ms_p95": percentile(latencies, 0.95),
        "generated_at": _now(),
    }


def compare(summary: dict[str, Any], baseline: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """``evals/compare.py``'s contract: 2 incomparable, 1 regression, 0 clean."""
    diff = [
        key
        for key in PINNED_KEYS
        if summary["manifest"].get(key) != baseline.get("manifest", {}).get(key)
    ]
    now, then = summary.get("auc_p_top"), baseline.get("auc_p_top")
    report: dict[str, Any] = {"sha_differs": diff, "auc_p_top": {"baseline": then, "now": now}}
    if diff or now is None or then is None:
        return EXIT_INCOMPARABLE, report
    report["auc_p_top"]["delta"] = round(now - then, 4)
    if then - now > REGRESSION_AUC_DROP:
        return EXIT_REGRESSION, report
    return EXIT_OK, report


def cmd_score(args: argparse.Namespace, notes_root: Path) -> int:
    directory = assert_private(args.dir, notes_root)
    manifest, rows = load_set(directory)
    labels = {
        label["post_id"]: bool(label["on_topic"])
        for label in read_jsonl(directory / "labels.jsonl")
    }
    home = Path(manifest["home"])
    stale = stale_items(manifest, pins(home))
    if stale:
        # The prompts would be rebuilt under inputs the labels were not asked
        # under; a comparison with any baseline would then be meaningless.
        print("stale label set — score refused (incomparable):\n  " + "\n  ".join(stale))
        return EXIT_INCOMPARABLE
    rar = replay()
    domain = rar.read_domain(home / "identity.md")
    model = args.model or manifest.get("decision_model") or DEFAULT_SCORE_MODEL
    entries = [
        (score_row(row_state(row, domain), model), labels[row["post_id"]])
        for row in rows
        if row["post_id"] in labels
    ]
    summary = summarize(manifest, entries, model)
    code = EXIT_OK
    if args.baseline is not None:
        code, summary["comparison"] = compare(summary, json.loads(args.baseline.read_text()))
    out = assert_private(args.out or directory / "summary.json", notes_root)
    out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"scored {summary['answered']}/{summary['labelled']} labelled rows: "
        f"AUC P(top) {summary['auc_p_top']} / expected level {summary['auc_expected_level']}; "
        f"p95 {summary['latency_ms_p95']} ms → {out}"
    )
    if "comparison" in summary:
        print(f"against baseline: {summary['comparison']} → exit {code}")
    return code


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace, notes_root: Path) -> int:
    directory = assert_private(args.dir, notes_root)
    manifest, _rows = load_set(directory)
    home = args.home or Path(manifest["home"])
    stale = stale_items(manifest, pins(home))
    if stale:
        print("stale:\n  " + "\n  ".join(stale))
        return EXIT_REGRESSION
    print(f"fresh: {directory}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="The relevance face's frozen label set.")
    sub = parser.add_subparsers(dest="command", required=True)
    today = datetime.now(timezone.utc).date().isoformat()

    sample = sub.add_parser("sample", help="stratified rows + manifest from the relevance log")
    sample.add_argument("--home", type=Path, required=True)
    sample.add_argument("--since", required=True, help="UTC instant (the switch)")
    sample.add_argument("--n", type=int, default=150)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--out", type=Path, default=None)
    sample.set_defaults(today=today)

    label = sub.add_parser("label", help="opus labels through evals/judging.py::run_claude_raw")
    label.add_argument("--dir", type=Path, required=True)
    label.add_argument("--model", default=DEFAULT_LABEL_MODEL)
    label.add_argument("--timeout", type=int, default=300)
    label.add_argument("--dry-run", action="store_true")

    score = sub.add_parser("score", help="deterministic logprobs re-score and AUC")
    score.add_argument("--dir", type=Path, required=True)
    score.add_argument("--model", default=None)
    score.add_argument("--baseline", type=Path, default=None)
    score.add_argument("--out", type=Path, default=None)

    check = sub.add_parser("check", help="manifest shas against the tree and identity.md")
    check.add_argument("--dir", type=Path, required=True)
    check.add_argument("--home", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None, *, notes_root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = notes_root or default_notes_root()
    if args.command == "sample":
        if args.out is None:
            args.out = root / "labels" / "relevance" / args.today
        return cmd_sample(args, root)
    return {"label": cmd_label, "score": cmd_score, "check": cmd_check}[args.command](args, root)


if __name__ == "__main__":
    sys.exit(main())
