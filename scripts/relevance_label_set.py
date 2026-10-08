#!/usr/bin/env python3
"""Label once, score many: the relevance face's frozen label set (RFC-0046 / RFC-0047 §3).

Four subcommands, one directory per label set
(``<main tree>/.notes/labels/relevance/<YYYY-MM-DD>/``):

1. ``sample`` — read ``logs/relevance-*.jsonl`` under ``--home`` (read-only),
   keep the rows since ``--since`` that are ``answered`` judgments (a live half,
   when the row has one, ``scored``), dedupe by ``post_id`` (earliest row
   wins), stratify on the logged P(directly on-topic) with :data:`P_TOP_STRATA`
   (below and above the gate's 0.3, the rejected side included and the band
   just under the cut kept apart; skill measurement-discipline §5) and draw
   ``--n`` rows with ``--seed``. The manifest names the key in ``strata_key``.
   Sets sampled before RFC-0046 cleanup 2 (2026-09-28 S35, 2026-10-03 S36)
   were stratified on the live score with the RFC-0045 strata
   (``relevance_arm_replay.STRATA``); their manifest has no ``strata_key``,
   and ``score`` weights them by that key still. Writes ``rows.jsonl`` (``content_b64``
   stays encoded — never plaintext) and ``manifest.json``, which pins every
   input the labels depend on: the ``identity.md`` sha256, the axioms' sha256
   (the constitution text production loads, null when there is none), the
   packaged ``relevance_score4.md`` / ``relevance.md`` sha256 and any home
   override's, the ``domain_source`` the set is labelled under (``--domain-source``,
   default ``identity+axioms`` — RFC-0046's "my domain", production's system
   prompt body), ``DECISION_MODEL``, the served model, the seed, window and counts. Fewer
   than ``--n`` distinct rows: prints "M 行、不足" and exits 2 without writing.
2. ``label`` — claude-opus-5's two-valued label per row (``on_topic`` = the
   top level of the RFC-0045 ceiling rubric, ``ceiling_prompt``), through
   ``evals/judging.py::run_claude_raw`` only (the one cloud seam,
   tests/test_cloud_egress_absence.py). One call per row, resumable, appended to
   ``labels.jsonl`` with ``judge: "opus"``. Jev labels come from
   ``python -m evals.jev_arm relevance-labels`` (RFC-0046 S35 — the cloud call
   stays in ``evals/``); one set holds one judge's labels, and a label without
   the field is opus's. Refuses (exit 2) when the manifest is stale — a label
   asked under a different identity or axioms is a different label — or when
   ``--domain-source`` (default ``identity+axioms``; ``identity`` reproduces
   RFC-0045's state) is not the manifest's (a manifest without the field is
   ``identity``). ``--dry-run`` builds
   every prompt and prints the count and the $ range; it calls nothing. The
   real run spends the operator's money and is the operator's to start.
3. ``score`` — re-score ``rows.jsonl`` × ``labels.jsonl`` deterministically
   with the production 4-level Score read (``relevance_arm_replay.run_logits``:
   ``OllamaLogprobsDecisionBackend``, no sampling): AUC of P(directly on-topic)
   and of the expected level against the label, precision / recall / agreement
   at t ∈ {0.3, 0.5, 0.7}, latency p50 / p95 — each its own axis, never a
   composite. The state's ``domain`` follows ``--domain-source`` under the
   same rule as ``label``. Beside the re-score (the ratchet's baseline — a
   temperature-0 logprobs read does not reproduce bit for bit, RFC-0046 S31)
   the summary reads, on the same labelled rows: ``recorded_cuts`` — the
   ``decision_p_top`` production logged, the very value enforce compares with
   its threshold (``relevance_shadow._resolve``) — and ``live_cut``, the
   row's logged ``live_gate`` (the free-generated gate; only rows from before
   2026-10-07 carry one, so a newer set reads ``n: 0``); ``recorded_vs_rescored`` — |ΔP(top)| mean / p95 and the rows whose
   gate flips per t. Every precision / recall also comes population-weighted
   (``*_weighted`` / ``weighted``): each row counts N_stratum / n_stratum, the
   manifest's ``population_strata`` over its ``strata``, which undoes the
   stratified draw (null for a manifest without the counts). The labels'
   judge is ``label_judge``; mixed judges are refused (exit 2). ``--baseline``
   compares with an earlier summary under the
   ``evals/compare.py`` exit contract: 2 incomparable (any pinned sha, the
   ``domain_source`` or the ``label_judge`` differs, or an AUC is missing),
   1 regression (P(top) AUC down by more than 0.03 — RFC-0046: the run-to-run
   noise floor measured on dev 150 put 0.02 inside it), 0 otherwise.
4. ``check`` — the manifest's shas against the tree, ``identity.md`` and the axioms now
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
REGRESSION_AUC_DROP = 0.03
# Strata on the logged P(directly on-topic) (RFC-0046 cleanup 2). Bounds from
# the post-enforce distribution (835 posts, 2026-09-28..10-06: 402 / 162 / 43 /
# 86 / 142 per band): the bulk far below the cut, the band just under the
# gate's 0.3 on its own, and two above it.
P_TOP_STRATA: tuple[tuple[str, float, float], ...] = (
    ("p0_lt0.05", -math.inf, 0.05),
    ("p1_0.05-0.2", 0.05, 0.2),
    ("p2_0.2-0.3", 0.2, 0.3),
    ("p3_0.3-0.7", 0.3, 0.7),
    ("p4_ge0.7", 0.7, math.inf),
)
STRATA_KEY_P_TOP = "decision_p_top"
# What a manifest without ``strata_key`` was stratified on (every pre-2026-10-07 set).
STRATA_KEY_LIVE = "live_score"
ANSWERED = "answered"
SCORED = "scored"
# The shas a label depends on; any change makes the set a different set.
PINNED_KEYS = (
    "identity_sha256",
    "axioms_sha256",
    "relevance_score4_sha256",
    "relevance_sha256",
    "relevance_score4_home_sha256",
    "relevance_home_sha256",
)
# What a summary carries of its manifest, and what a baseline must match.
COMPARED_KEYS = (*PINNED_KEYS, "domain_source")
EXIT_OK, EXIT_REGRESSION, EXIT_INCOMPARABLE = 0, 1, 2
# The judge a label without the field was asked by (every pre-S35 label).
LEGACY_JUDGE = "opus"


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


def sha256_text(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def axioms_text(home: Path) -> str:
    """The constitution text production appends as axioms ("" when there is none).

    The directory is resolved the way the replay resolves production's prompt
    sources, and read with production's join (``read_constitution``).
    """
    from contemplative_agent.core.domain import read_constitution

    _identity, constitution_dir = replay().skillsel().replay_prompt_sources(home)
    return read_constitution(constitution_dir)[1]


def pins(home: Path) -> dict[str, str | None]:
    """The shas of every input a label depends on, as the tree and home stand now."""
    from contemplative_agent.core.domain import DEFAULT_PROMPTS_DIR

    return {
        "identity_sha256": sha256_file(home / "identity.md"),
        "axioms_sha256": sha256_text(axioms_text(home)),
        "relevance_score4_sha256": sha256_file(DEFAULT_PROMPTS_DIR / "relevance_score4.md"),
        "relevance_sha256": sha256_file(DEFAULT_PROMPTS_DIR / "relevance.md"),
        # A home override changes production's question (core.prompts), not the
        # packaged one this asset asks — pinned so a divergence is visible.
        "relevance_score4_home_sha256": sha256_file(home / "prompts" / "relevance_score4.md"),
        "relevance_home_sha256": sha256_file(home / "prompts" / "relevance.md"),
    }


def stale_items(manifest: dict[str, Any], current: dict[str, str | None]) -> list[str]:
    """Pins that moved. The axioms are skipped for a set labelled under identity
    alone — they never reached its prompts (and a pre-S32 manifest has no pin)."""
    identity_only = manifest_domain_source(manifest) == replay().DOMAIN_SOURCE_IDENTITY
    return [
        f"{key}: {manifest.get(key)} -> {current.get(key)}"
        for key in PINNED_KEYS
        if manifest.get(key) != current.get(key) and not (identity_only and key == "axioms_sha256")
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
    """Answered judgments since *since*, one per post (earliest), by post_id.

    A row's live half, when it has one (rows before 2026-10-07), must be
    ``scored``: a failed live reading was an event, not a judgment. Only feed
    rows: a ``source: "seed"`` row (self-post seed selection asking the same
    gate, from 2026-10-09) is a different draw and stays out of the sample.
    """
    kept: dict[str, dict[str, Any]] = {}
    for path in sorted((home / "logs").glob("relevance-*.jsonl")):
        for record in read_jsonl(path):
            ts = record.get("ts")
            if (
                not isinstance(ts, str)
                or parse_instant(ts) < since
                or record.get("live_reason") not in (None, SCORED)
                or record.get("source", "feed") != "feed"
                or record.get("decision_reason") != ANSWERED
                or _number(record.get("decision_p_top")) is None
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
                "live_score": _number(record.get("live_score")),
                "live_gate": record.get("live_gate"),
                "threshold_applied": record.get("threshold_applied"),
                "decision_p_top": record.get("decision_p_top"),
                "content_sha256": record.get("content_sha256"),
                "content_b64": record["content_b64"],
            }
    return [kept[key] for key in sorted(kept)]


def p_top_stratum_of(p_top: float) -> str:
    for name, low, high in P_TOP_STRATA:
        if low <= p_top < high:
            return name
    raise ValueError(f"P(top) {p_top} fits no stratum")


def manifest_strata_key(manifest: dict[str, Any]) -> str:
    """A manifest from before the field existed was stratified on the live score."""
    return str(manifest.get("strata_key", STRATA_KEY_LIVE))


def stratum_of_row(row: dict[str, Any], strata_key: str) -> str:
    """The stratum *row* falls in under *strata_key*'s bands."""
    if strata_key == STRATA_KEY_P_TOP:
        return p_top_stratum_of(float(row[STRATA_KEY_P_TOP]))
    return replay().stratum_of(row[STRATA_KEY_LIVE])


def stratified(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """*n* rows spread over the P(top) strata (short strata topped up)."""
    rar = replay()
    rng = random.Random(seed)
    by_stratum: dict[str, list[str]] = {name: [] for name, _lo, _hi in P_TOP_STRATA}
    for row in rows:
        by_stratum[stratum_of_row(row, STRATA_KEY_P_TOP)].append(row["post_id"])
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
    population: dict[str, int] = {}
    for row in rows:
        name = stratum_of_row(row, STRATA_KEY_P_TOP)
        population[name] = population.get(name, 0) + 1
    manifest = {
        "schema": SCHEMA,
        "home": str(args.home),
        **pins(args.home),
        "domain_source": args.domain_source,
        "strata_key": STRATA_KEY_P_TOP,
        "decision_model": os.environ.get("DECISION_MODEL"),
        "served_model": served_model(),
        "seed": args.seed,
        "rows": len(chosen),
        "population": len(rows),
        "strata": dict(sorted(counts.items())),
        # The weights that undo the stratified draw in ``score``.
        "population_strata": dict(sorted(population.items())),
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


def other_judges(records: list[dict[str, Any]], judge: str) -> list[str]:
    """Judges other than *judge* in a ``labels.jsonl`` (a label without the field is opus's)."""
    return sorted({str(r.get("judge", LEGACY_JUDGE)) for r in records} - {judge})


def manifest_domain_source(manifest: dict[str, Any]) -> str:
    """A manifest from before the field existed was labelled under identity alone."""
    return str(manifest.get("domain_source", replay().DOMAIN_SOURCE_IDENTITY))


def refuse(manifest: dict[str, Any], home: Path, source: str, verb: str) -> bool:
    """Print why *verb* is refused (stale pins, another definition); True when refused."""
    stale = stale_items(manifest, pins(home))
    labelled = manifest_domain_source(manifest)
    if labelled != source:
        stale.append(f"domain_source: {labelled} (manifest) != {source} (--domain-source)")
    if stale:
        print(f"stale label set — {verb} refused:\n  " + "\n  ".join(stale))
    return bool(stale)


def row_state(row: dict[str, Any], domain: str) -> dict[str, str]:
    text = base64.b64decode(row["content_b64"]).decode("utf-8", errors="replace")
    return replay().build_state(domain, text)


def cmd_label(args: argparse.Namespace, notes_root: Path) -> int:
    directory = assert_private(args.dir, notes_root)
    manifest, rows = load_set(directory)
    home = Path(manifest["home"])
    if refuse(manifest, home, args.domain_source, "label"):
        return EXIT_INCOMPARABLE
    rar = replay()
    domain = rar.domain_for_source(home, args.domain_source)
    existing = read_jsonl(directory / "labels.jsonl")
    if others := other_judges(existing, LEGACY_JUDGE):
        print(f"labels.jsonl holds labels by {others} — one set, one judge; label refused")
        return EXIT_INCOMPARABLE
    done = {label["post_id"] for label in existing}
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
                "judge": LEGACY_JUDGE,
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


def cut_reading(
    scores: list[float], labels: list[bool], t: float, weights: list[float] | None = None
) -> dict[str, float | None]:
    return flag_reading([s >= t for s in scores], labels, weights)


def flag_reading(
    flags: list[bool], labels: list[bool], weights: list[float] | None = None
) -> dict[str, float | None]:
    """precision / recall / agreement / gate rate of a gate's flags against the labels.

    *weights* (one per row) count each row as that many population rows —
    ``stratum_weights`` — so a stratified sample reads as its population.
    """
    w = weights if weights is not None else [1.0] * len(flags)
    rows = list(zip(flags, labels, w, strict=True))
    tp = sum(x for f, y, x in rows if f and y)
    fp = sum(x for f, y, x in rows if f and not y)
    fn = sum(x for f, y, x in rows if not f and y)
    agree = sum(x for f, y, x in rows if f == y)
    total = sum(w)

    def ratio(a: float, b: float) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "agreement": ratio(agree, total),
        "gate_rate": ratio(sum(x for f, _y, x in rows if f), total),
    }


def stratum_weights(
    rows: list[dict[str, Any]],
    population: dict[str, int] | None,
    *,
    strata_key: str,
) -> list[float] | None:
    """N_stratum / n_stratum per row; None without the manifest's population counts.

    Post-stratified on the stratum the row's *strata_key* value falls in — the
    key ``population_strata`` is counted by (``manifest_strata_key``) — not on
    the ``stratum`` tag: a short stratum is topped up from its neighbours
    (``stratified``), and a borrowed row belongs to, and weighs as, its own
    stratum.
    """
    if not population:
        return None
    names = [stratum_of_row(row, strata_key) for row in rows]
    drawn: dict[str, int] = {}
    for name in names:
        drawn[name] = drawn.get(name, 0) + 1
    return [population[name] / drawn[name] for name in names]


def _cuts(
    scores: list[float], labels: list[bool], weights: list[float] | None
) -> dict[str, dict[str, float | None]]:
    return {f"{t:.1f}": cut_reading(scores, labels, t, weights) for t in THRESHOLDS}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def production_readings(
    manifest: dict[str, Any], labelled: list[tuple[dict[str, Any], dict[str, Any], bool]]
) -> dict[str, Any]:
    """What production logged, read against the same labels (RFC-0046 S35).

    *labelled* is ``(sample row, re-score entry, label)``. ``recorded_cuts`` is
    the sample's ``decision_p_top`` — the value enforce compares with its
    threshold; ``live_cut`` is the row's ``live_gate`` — the free-generated
    gate, carried only by rows from before 2026-10-07. Each is read on the rows
    that carry it, raw and population-weighted.
    """
    rar = replay()
    population = manifest.get("population_strata")
    key = manifest_strata_key(manifest)
    recorded = [
        (row, float(p), y)
        for row, _e, y in labelled
        if (p := _number(row.get("decision_p_top"))) is not None
    ]
    rec_rows = [row for row, _p, _y in recorded]
    rec_scores = [p for _r, p, _y in recorded]
    rec_labels = [y for _r, _p, y in recorded]
    rec_weights = stratum_weights(rec_rows, population, strata_key=key)
    auc_recorded = rar.auc(rec_scores, rec_labels)

    live = [
        (row, row["live_gate"], y)
        for row, _e, y in labelled
        if isinstance(row.get("live_gate"), bool)
    ]
    live_flags = [f for _r, f, _y in live]
    live_labels = [y for _r, _f, y in live]
    live_weights = stratum_weights([row for row, _f, _y in live], population, strata_key=key)

    paired = [
        (float(p), float(entry["p_top"]))
        for row, entry, _y in labelled
        if (p := _number(row.get("decision_p_top"))) is not None
        and entry.get("reason") == ANSWERED
        and _number(entry.get("p_top")) is not None
    ]
    deltas = [abs(a - b) for a, b in paired]
    return {
        "recorded_cuts": {
            "n": len(recorded),
            "auc_p_top": round(auc_recorded, 4) if auc_recorded is not None else None,
            "cuts": _cuts(rec_scores, rec_labels, None),
            "cuts_weighted": _cuts(rec_scores, rec_labels, rec_weights) if rec_weights else None,
        },
        "live_cut": {
            "n": len(live),
            **flag_reading(live_flags, live_labels),
            "weighted": flag_reading(live_flags, live_labels, live_weights)
            if live_weights
            else None,
        },
        "recorded_vs_rescored": {
            "n": len(paired),
            "abs_delta_mean": round(sum(deltas) / len(deltas), 4) if deltas else None,
            "abs_delta_p95": round(p95, 4)
            if (p95 := percentile(deltas, 0.95)) is not None
            else None,
            "gate_flips": {
                f"{t:.1f}": sum(1 for a, b in paired if (a >= t) != (b >= t)) for t in THRESHOLDS
            },
        },
    }


def summarize(
    manifest: dict[str, Any],
    labelled: list[tuple[dict[str, Any], dict[str, Any], bool]],
    model: str,
    judge: str = LEGACY_JUDGE,
) -> dict:
    """*labelled* is ``(sample row, re-score entry, label)`` per labelled row."""
    rar = replay()
    entries = [(e, y) for _row, e, y in labelled]
    answered_rows = [row for row, e, _y in labelled if e.get("reason") == ANSWERED]
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
        "manifest": {
            **{key: manifest.get(key) for key in PINNED_KEYS},
            "domain_source": manifest_domain_source(manifest),
        },
        "score_model": model,
        "label_judge": judge,
        "population_strata": manifest.get("population_strata"),
        "strata_key": manifest_strata_key(manifest),
        "labelled": len(entries),
        "answered": len(answered),
        "on_topic": sum(labels),
        "reasons": dict(sorted(reasons.items())),
        "auc_p_top": round(auc_top, 4) if auc_top is not None else None,
        "auc_expected_level": round(auc_expected, 4) if auc_expected is not None else None,
        "cuts": _cuts(p_top, labels, None),
        "cuts_weighted": (
            _cuts(p_top, labels, weights)
            if (
                weights := stratum_weights(
                    answered_rows,
                    manifest.get("population_strata"),
                    strata_key=manifest_strata_key(manifest),
                )
            )
            else None
        ),
        **production_readings(manifest, labelled),
        "latency_ms_p50": percentile(latencies, 0.5),
        "latency_ms_p95": percentile(latencies, 0.95),
        "generated_at": _now(),
    }


def compare(summary: dict[str, Any], baseline: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """``evals/compare.py``'s contract: 2 incomparable, 1 regression, 0 clean."""
    diff = [
        key
        for key in COMPARED_KEYS
        if summary["manifest"].get(key) != baseline.get("manifest", {}).get(key)
    ]
    if summary.get("label_judge", LEGACY_JUDGE) != baseline.get("label_judge", LEGACY_JUDGE):
        diff.append("label_judge")
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
    records = read_jsonl(directory / "labels.jsonl")
    labels = {label["post_id"]: bool(label["on_topic"]) for label in records}
    judges = sorted({str(label.get("judge", LEGACY_JUDGE)) for label in records})
    if len(judges) > 1:
        print(f"labels by more than one judge {judges} — score refused (one set, one judge)")
        return EXIT_INCOMPARABLE
    home = Path(manifest["home"])
    # The prompts would be rebuilt under inputs the labels were not asked
    # under; a comparison with any baseline would then be meaningless.
    if refuse(manifest, home, args.domain_source, "score (incomparable)"):
        return EXIT_INCOMPARABLE
    domain = replay().domain_for_source(home, args.domain_source)
    model = args.model or manifest.get("decision_model") or DEFAULT_SCORE_MODEL
    labelled = [
        (row, score_row(row_state(row, domain), model), labels[row["post_id"]])
        for row in rows
        if row["post_id"] in labels
    ]
    summary = summarize(manifest, labelled, model, judges[0] if judges else LEGACY_JUDGE)
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


def _domain_source_flag(parser: argparse.ArgumentParser) -> None:
    rar = replay()
    parser.add_argument(
        "--domain-source",
        choices=rar.DOMAIN_SOURCES,
        default=rar.DOMAIN_SOURCE_PRODUCTION,
        help="the state's domain: identity + axioms (production) or identity.md alone",
    )


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
    _domain_source_flag(sample)
    sample.set_defaults(today=today)

    label = sub.add_parser("label", help="opus labels through evals/judging.py::run_claude_raw")
    label.add_argument("--dir", type=Path, required=True)
    label.add_argument("--model", default=DEFAULT_LABEL_MODEL)
    label.add_argument("--timeout", type=int, default=300)
    label.add_argument("--dry-run", action="store_true")
    _domain_source_flag(label)

    score = sub.add_parser("score", help="deterministic logprobs re-score and AUC")
    score.add_argument("--dir", type=Path, required=True)
    score.add_argument("--model", default=None)
    score.add_argument("--baseline", type=Path, default=None)
    score.add_argument("--out", type=Path, default=None)
    _domain_source_flag(score)

    check = sub.add_parser("check", help="manifest shas against the tree, identity and axioms")
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
