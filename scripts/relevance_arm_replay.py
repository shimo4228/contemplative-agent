#!/usr/bin/env python3
"""Offline replay of the relevance gate against Jev as the label (RFC-0045, packet S28).

The production relevance judgment (``score_relevance_detailed``: gemma4:e4b,
temperature 1.0, ``config/prompts/relevance.md``, gate 0.82) is replayed on the
2,698 posts the ADR-0086 submolt scan already logged in
``logs/submolt-scope-*.jsonl`` (``event == "score"``: ``post_id`` /
``score`` / ``content_b64`` ...). Nothing new is recorded in production and
``$MOLTBOOK_HOME`` is only read.

Arms (labels as they appear in the row log and the summary):

* ``A/free/rep1`` ``A/free/rep2`` — production's own function, called as-is
  (prompt, identity + axioms system prompt, temperature 1.0, parse).
* ``A0/t0`` — the same function with ``generate`` pinned to temperature 0.
* ``C/logits/score4`` — gemma asked the 4-level Score through ADR-0112's
  ``OllamaLogprobsDecisionBackend`` (the seam's first Score use).
* ``E/opus/rep1`` ``E/opus/rep2`` — claude-opus-5 on the same rubric, through
  ``evals/judging.py::run_claude_raw`` (the one sanctioned cloud CLI seam).
* ``K/kev/score4`` + ``K/kev/noul``, ``V/von/score4`` + ``V/von/noul`` — local
  System One servers on ``127.0.0.1`` (``/v1/systemone``), started by the
  operator in their own project env.
* ``J/score4`` + ``J/noul`` — hosted Jev. NOT run from here: the hosted client
  lives in ``evals/jev_arm.py`` (``python -m evals.jev_arm relevance``), which
  imports THIS module for the sample, the state and the questions. Its rows
  file is merged in with ``--augment``.

**The state is the same for every non-production arm**: ``domain`` =
``identity.md`` as production reads it (the judge's call, 2026-09-24: the
question is "is this my domain", and the axioms are values, not the domain)
and ``post`` = the logged 500-character preview wrapped by production's
``wrap_untrusted_content(max_input=1000)``. Arms A / A0 alone run under the
production system prompt (identity + axioms) because they ARE production.

**Text discipline.** Decoded posts never reach stdout or the summary. The row
log (``.notes/`` only — :func:`assert_private_output`) carries scores,
probabilities, latencies and reason codes, never the post; the summary is
walked by ``assert_no_text_in_summary`` before it is written.

Usage::

    # the split (written once, then re-derived and compared on every run)
    uv run --no-sync python scripts/relevance_arm_replay.py --write-split
    # gemma arms (GPU windows waited out)
    uv run --no-sync python scripts/relevance_arm_replay.py --arms A,C --subset all --resume
    uv run --no-sync python scripts/relevance_arm_replay.py --arms A2,A0 --subset sub600 --resume
    # opus
    uv run --no-sync python scripts/relevance_arm_replay.py --arms E,E2 --subset dev --resume
    # kev / von: smoke, then dev, then (only on a dev pass) holdout
    uv run --no-sync python scripts/relevance_arm_replay.py --arms K --subset dev --limit 5 \\
        --kev-endpoint http://127.0.0.1:8009 --resume
    # readings
    uv run --no-sync python scripts/relevance_arm_replay.py --summarize-only \\
        --augment .notes/relevance-arm-replay/jev/rows.jsonl --out-summary …
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import importlib.util
import json
import math
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
# ``evals`` is imported as a package from the repo root for arm E only
# (``evals/judging.py::run_claude_raw``); named in
# tests/test_cloud_egress_absence.py::EVALS_IMPORT_ALLOWLIST.
sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "relevance-arm-replay/1"
NOTES_ROOT = _REPO_ROOT / ".notes"
DEFAULT_DIR = Path(".notes/relevance-arm-replay")

# --------------------------------------------------------------------------
# The judgment every non-production arm is asked (RFC-0045 wording)
# --------------------------------------------------------------------------

# Level heads are RFC-0045's; the descriptions make each level stand on its own
# (typesafe docs: "Score levels must describe concrete situations"), and the
# lowest non-zero level is "shares vocabulary only" (skill jev-judgment-design §3).
LEVELS: tuple[str, ...] = (
    "unrelated — `post` is about something outside `domain`",
    "shares vocabulary only — `post` uses some of the same words as `domain`, "
    "but it is about a different problem",
    "same field — `post` is in the same broad field as `domain`, but not about "
    "what `domain` is concerned with",
    "directly on-topic — `post` is about what `domain` is concerned with",
)
SCORE_INSTRUCTIONS = (
    "`domain` describes an agent and what it is concerned with. "
    "How closely does `post` relate to that domain?"
)
NOUL_INSTRUCTIONS = (
    "`domain` describes an agent and what it is concerned with. "
    "Is `post` directly on-topic for that domain?"
)
TOP_LEVEL = len(LEVELS) - 1

# Row-log labels. J labels are written by evals/jev_arm.py (see the docstring).
LABELS: dict[str, tuple[str, ...]] = {
    "A": ("A/free/rep1",),
    "A2": ("A/free/rep2",),
    "A0": ("A0/t0",),
    "C": ("C/logits/score4",),
    "E": ("E/opus/rep1",),
    "E2": ("E/opus/rep2",),
    "K": ("K/kev/score4", "K/kev/noul"),
    "V": ("V/von/score4", "V/von/noul"),
}
JEV_SCORE_LABEL = "J/score4"
JEV_NOUL_LABEL = "J/noul"
GPU_ARMS = frozenset({"A", "A2", "A0", "C", "K", "V"})
SYSTEMONE_ARMS = frozenset({"K", "V"})

REASON_ANSWERED = "answered"

# Gemma's logged score only takes the values 0.0, 0.1, ... 1.0, so the strata
# are cut at the observed values (judge, 2026-09-24): <=0.4 / 0.5-0.6 / 0.7 /
# 0.8 / >=0.9. The production gates 0.65 and 0.82 both fall between strata.
STRATA: tuple[tuple[str, float, float], ...] = (
    ("s0_le0.4", -math.inf, 0.45),
    ("s1_0.5-0.6", 0.45, 0.65),
    ("s2_0.7", 0.65, 0.75),
    ("s3_0.8", 0.75, 0.85),
    ("s4_ge0.9", 0.85, math.inf),
)
DEV_PER_STRATUM = 30
SUB600_PER_STRATUM = 120
SPLIT_SEED = 20260925

PRODUCTION_GATE = 0.82


# --------------------------------------------------------------------------
# Reuse of the RFC-0043 harness (loaded by path — scripts/ is not a package)
# --------------------------------------------------------------------------


def skillsel() -> ModuleType:
    """``scripts/skillsel_arm_replay.py``: bootstrap, schedule guard, kev client."""
    name = "skillsel_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = _REPO_ROOT / "scripts" / "skillsel_arm_replay.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Sample
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleRow:
    """One logged ``score`` event. ``content_b64`` stays encoded until asked."""

    post_id: str
    logged_score: float
    content_b64: str
    subscribed: bool

    def text(self) -> str:
        return base64.b64decode(self.content_b64).decode("utf-8", errors="replace")


def load_sample(home: Path) -> list[SampleRow]:
    """Every ``event == "score"`` row with ``reason == "scored"``, sorted by post_id.

    All files, no day window: the sample is the whole scan record. A second
    row for a post already seen is dropped (the RFC reads distinct posts).
    """
    rows: dict[str, SampleRow] = {}
    for path in sorted((home / "logs").glob("submolt-scope-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("event") != "score" or record.get("reason") != "scored":
                continue
            post_id = str(record["post_id"])
            if post_id in rows:
                continue
            rows[post_id] = SampleRow(
                post_id=post_id,
                logged_score=float(record["score"]),
                content_b64=str(record["content_b64"]),
                subscribed=bool(record.get("subscribed")),
            )
    return [rows[key] for key in sorted(rows)]


def stratum_of(score: float) -> str:
    for name, low, high in STRATA:
        if low <= score < high:
            return name
    raise ValueError(f"score {score} fits no stratum")


def make_split(rows: Sequence[SampleRow], *, seed: int = SPLIT_SEED) -> dict[str, Any]:
    """Dev (30 per stratum) nested in sub600 (120 per stratum); holdout = not dev.

    Each stratum is shuffled once with ``seed`` (rows pre-sorted by post_id),
    so dev is the first 30 of the same order sub600 takes 120 from — dev is a
    subset of sub600 by construction. A stratum too small for its quota is
    topped up from the next stratum's unused rows (the judge's rule); the
    counts written alongside say whether that happened.
    """
    rng = random.Random(seed)
    by_stratum: dict[str, list[str]] = {name: [] for name, _lo, _hi in STRATA}
    for row in sorted(rows, key=lambda r: r.post_id):
        by_stratum[stratum_of(row.logged_score)].append(row.post_id)
    order = {name: rng.sample(ids, len(ids)) for name, ids in by_stratum.items()}
    dev = _quota_take(order, DEV_PER_STRATUM)
    sub600 = _quota_take(order, SUB600_PER_STRATUM)
    dev_set = {pid for ids in dev.values() for pid in ids}
    return {
        "schema": SCHEMA,
        "seed": seed,
        # An open bound is null: json.dumps would write -Infinity, which strict
        # JSON readers refuse.
        "strata": [{"name": n, "low": _finite(lo), "high": _finite(hi)} for n, lo, hi in STRATA],
        "population": {name: len(ids) for name, ids in by_stratum.items()},
        "dev": dev,
        "sub600": sub600,
        "dev_count": {name: len(ids) for name, ids in dev.items()},
        "sub600_count": {name: len(ids) for name, ids in sub600.items()},
        "holdout_count": len(rows) - len(dev_set),
    }


def _quota_take(order: dict[str, list[str]], quota: int) -> dict[str, list[str]]:
    """The first ``quota`` ids of each stratum, short strata topped up from the next."""
    names = list(order)
    taken: dict[str, list[str]] = {name: list(order[name][:quota]) for name in names}
    used = {pid for ids in taken.values() for pid in ids}
    for index, name in enumerate(names):
        short = quota - len(taken[name])
        neighbours = names[index + 1 :] + list(reversed(names[:index]))
        for neighbour in neighbours:
            if short <= 0:
                break
            spare = [pid for pid in order[neighbour] if pid not in used][:short]
            taken[name].extend(spare)
            used.update(spare)
            short -= len(spare)
    return taken


def subset_ids(split: dict[str, Any], rows: Sequence[SampleRow], subset: str) -> list[str]:
    """The post_ids of one subset, in a fixed order (stratum, then split order)."""
    if subset == "all":
        return [row.post_id for row in rows]
    dev = [pid for ids in split["dev"].values() for pid in ids]
    if subset == "dev":
        return dev
    if subset == "sub600":
        return [pid for ids in split["sub600"].values() for pid in ids]
    if subset == "holdout":
        dev_set = set(dev)
        return [row.post_id for row in rows if row.post_id not in dev_set]
    raise ValueError(f"unknown subset {subset!r}")


# --------------------------------------------------------------------------
# State and prompts
# --------------------------------------------------------------------------


def read_domain(identity_path: Path) -> str:
    """``identity.md`` as production's prompting reads it (stripped, validated)."""
    from contemplative_agent.core.llm.prompting import validate_identity_content

    text = identity_path.read_text(encoding="utf-8").strip()
    if not text or not validate_identity_content(text):
        raise SystemExit(f"{identity_path} is empty or fails production's identity validation")
    return text


def build_state(domain: str, post_text: str) -> dict[str, str]:
    """``{domain, post}`` — the post inside production's untrusted frame."""
    from contemplative_agent.core.llm import wrap_untrusted_content

    return {"domain": domain, "post": wrap_untrusted_content(post_text, max_input=1000)}


def state_text(state: dict[str, str]) -> str:
    """The state as prompt text for the arms that take a string (C, E)."""
    return json.dumps(state, ensure_ascii=False, indent=2)


_CEILING_PROMPT = (
    "You are judging how relevant a social-media post is to an agent's domain.\n\n"
    "## State\n\n{state}\n\n"
    "## Question\n\n{instructions}\n\n{levels}\n\n"
    "Answer with exactly one digit: the number of the level. No prose."
)


def ceiling_prompt(state: dict[str, str]) -> str:
    levels = "\n".join(f"{i}. {level}" for i, level in enumerate(LEVELS))
    return _CEILING_PROMPT.format(
        state=state_text(state), instructions=SCORE_INSTRUCTIONS, levels=levels
    )


def parse_level(raw: str) -> int | None:
    """The first digit 0-3 in the answer, or None."""
    match = re.search(r"[0-9]", raw)
    if match is None:
        return None
    level = int(match.group(0))
    return level if level <= TOP_LEVEL else None


# --------------------------------------------------------------------------
# Reading a /v1/systemone Score answer (Jev, kev, von share the shape)
# --------------------------------------------------------------------------


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def read_score_probabilities(answer: object, levels: Sequence[str] = LEVELS) -> list[float] | None:
    """Per-level probabilities in level order, or None when unreadable.

    Jev answers ``probabilities`` keyed by level index as a string (``"0"`` ..
    ``"3"``, observed 2026-09-24); a server keyed by the level text, or giving
    a list, is read the same way. Renormalised: Jev rounds to two decimals.
    """
    if not isinstance(answer, dict):
        return None
    raw = answer.get("probabilities")
    values: list[float | None]
    if isinstance(raw, list) and len(raw) == len(levels):
        values = [_finite(v) for v in raw]
    elif isinstance(raw, dict):
        values = [
            _finite(raw[str(i)]) if str(i) in raw else _finite(raw.get(level))
            for i, level in enumerate(levels)
        ]
    else:
        return None
    if any(v is None or v < 0 for v in values):
        return None
    numbers = [float(v) for v in values if v is not None]
    total = sum(numbers)
    if total <= 0:
        return None
    return [round(v / total, 6) for v in numbers]


def score_entry(probabilities: list[float], latency_ms: int, **meta: object) -> dict[str, Any]:
    """A Score arm's row entry: distribution, normalised expectation, P(top level)."""
    expected = sum(i * p for i, p in enumerate(probabilities))
    return {
        "reason": REASON_ANSWERED,
        "probs": probabilities,
        "score": round(expected / TOP_LEVEL, 6),
        "p_top": probabilities[TOP_LEVEL],
        "latency_ms": latency_ms,
        **meta,
    }


def noul_entry(p_yes: float, latency_ms: int, **meta: object) -> dict[str, Any]:
    return {"reason": REASON_ANSWERED, "score": round(p_yes, 6), "latency_ms": latency_ms, **meta}


def failed_entry(reason: str, latency_ms: int = 0, **meta: object) -> dict[str, Any]:
    return {"reason": reason, "score": None, "latency_ms": latency_ms, **meta}


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------


@contextlib.contextmanager
def generate_temperature(temperature: float | None) -> Iterator[None]:
    """Pin ``llm_functions.generate``'s temperature for arm A0, then restore it.

    Arm A0 is production's own function with ONE change; patching the name the
    function looks up keeps the prompt, the system prompt and the parse
    production's rather than a copy of them.
    """
    from contemplative_agent.adapters.moltbook import llm_functions

    if temperature is None:
        yield
        return
    original = llm_functions.generate

    def pinned(*args: Any, **kwargs: Any) -> str | None:  # noqa: ANN401
        kwargs["temperature"] = temperature
        return original(*args, **kwargs)

    llm_functions.generate = pinned
    try:
        yield
    finally:
        llm_functions.generate = original


def run_production(row: SampleRow, *, temperature: float | None) -> dict[str, Any]:
    """Arms A / A0: ``score_relevance_detailed`` itself."""
    from contemplative_agent.adapters.moltbook.llm_functions import score_relevance_detailed

    started = time.monotonic()
    with generate_temperature(temperature):
        result = score_relevance_detailed(row.text(), caller="rfc0045.replay")
    latency = int((time.monotonic() - started) * 1000)
    if result.reason != "scored":
        return failed_entry(result.reason, latency)
    return {"reason": REASON_ANSWERED, "score": result.score, "latency_ms": latency}


def run_logits(state: dict[str, str], model: str) -> dict[str, Any]:
    """Arm C: the 4-level Score through ADR-0112's logprobs backend."""
    from contemplative_agent.core.llm.decision import (
        OllamaLogprobsDecisionBackend,
        ScoreQuestion,
    )

    question = ScoreQuestion(id="score4", instructions=SCORE_INSTRUCTIONS, levels=LEVELS)
    backend = OllamaLogprobsDecisionBackend(model=model)
    result = backend.decide(state_text(state), (question,), system="")
    if result is None:
        return failed_entry("backend_exception")
    answer = result.answers[0]
    if answer.reason != REASON_ANSWERED:
        return failed_entry(answer.reason, result.latency_ms)
    probabilities = [round(p, 6) for _option, p in answer.probabilities]
    return score_entry(
        probabilities, result.latency_ms, observed=answer.observed, truncated=answer.truncated
    )


def run_ceiling(state: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    """Arm E: claude-opus-5, no tools, through the one sanctioned seam."""
    from evals.judging import JudgeError, run_claude_raw

    started = time.monotonic()
    cost: dict[str, object] = {}
    try:
        raw = run_claude_raw(
            ceiling_prompt(state),
            model=args.ceiling_model,
            scratch_dir=Path(args.ceiling_scratch),
            timeout=args.ceiling_timeout,
            meta_out=cost,
        )
    except JudgeError as exc:
        return failed_entry("ceiling_error", note=type(exc).__name__)
    latency = int((time.monotonic() - started) * 1000)
    level = parse_level(raw)
    if level is None:
        return failed_entry("parse_failed", latency, cost=dict(cost))
    probabilities = [1.0 if i == level else 0.0 for i in range(len(LEVELS))]
    return {**score_entry(probabilities, latency, cost=dict(cost)), "level": level}


def systemone_request(state: dict[str, str], model: str) -> dict[str, Any]:
    """One request carrying both questions — the shape Jev, kev and von take."""
    return {
        "state": state,
        "model": model,
        "questions": {
            "score4": {
                "type": "score",
                "instructions": SCORE_INSTRUCTIONS,
                "criteria": list(LEVELS),
            },
            "noul": {"type": "noul", "instructions": NOUL_INSTRUCTIONS},
        },
    }


def systemone_entries(answers: dict[str, Any], latency_ms: int) -> tuple[dict, dict]:
    """``(score4 entry, noul entry)`` from one response's ``answers`` map."""
    probabilities = read_score_probabilities(answers.get("score4"))
    score = (
        score_entry(probabilities, latency_ms)
        if probabilities is not None
        else failed_entry("parse_failed", latency_ms)
    )
    noul_answer = answers.get("noul")
    p_yes = _finite(noul_answer.get("noul")) if isinstance(noul_answer, dict) else None
    noul = (
        noul_entry(p_yes, latency_ms)
        if p_yes is not None and 0.0 <= p_yes <= 1.0
        else failed_entry("parse_failed", latency_ms)
    )
    return score, noul


def run_systemone(state: dict[str, str], family: str, args: argparse.Namespace) -> list[dict]:
    """Arms K / V: one ``/v1/systemone`` request to the operator-started server."""
    sk = skillsel()
    server = sk._SYSTEMONE_SERVERS[family]
    endpoint = getattr(args, server.endpoint_attr)
    started = time.monotonic()
    try:
        data = sk.kev_post(
            endpoint,
            systemone_request(state, server.model),
            timeout=(10, args.systemone_timeout),
            server=server,
        )
    except sk.KevCallFailed as exc:
        latency = int((time.monotonic() - started) * 1000)
        return [failed_entry(exc.reason, latency, note=exc.note[:80])] * 2
    latency = int((time.monotonic() - started) * 1000)
    return list(systemone_entries(data["answers"], latency))


# --------------------------------------------------------------------------
# Row log (append-only; lines for one post merge on read)
# --------------------------------------------------------------------------


def assert_private_output(path: Path, *, notes_root: Path | None = None) -> Path:
    """Refuse any row/aux output outside the gitignored ``.notes/`` tree.

    Copied from ``817ecf3:evals/jev_arm.py::assert_private_output`` (this
    script may not import that module — tests/test_jev_results_stay_private.py).
    The row log is keyed by post and sits one decode away from other agents'
    posts, so it never lands in a tracked tree.
    """
    resolved = Path(path).expanduser().resolve()
    root = (NOTES_ROOT if notes_root is None else notes_root).expanduser().resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(f"{resolved} is outside {root} — row-level output goes to .notes/ only")
    return resolved


def read_rows(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    """``{post_id: {label: entry}}`` merged over every file, later lines winning."""
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise SystemExit(f"{path}:{number} is not JSON — refusing to merge") from None
            arms = merged.setdefault(str(record["post_id"]), {})
            arms.update(record.get("arms") or {})
    return merged


def answered(arms: dict[str, Any], label: str) -> bool:
    entry = arms.get(label)
    return isinstance(entry, dict) and entry.get("reason") == REASON_ANSWERED


def row_record(row: SampleRow, arms: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "post_id": row.post_id,
        "stratum": stratum_of(row.logged_score),
        "logged_score": row.logged_score,
        "arms": arms,
    }


# --------------------------------------------------------------------------
# Resources (smoke rule: swap +3 GB at most)
# --------------------------------------------------------------------------


def swap_used_mb() -> float | None:
    """``vm.swapusage`` used, in MB (macOS). None where it cannot be read."""
    try:
        out = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["/usr/sbin/sysctl", "-n", "vm.swapusage"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"used = ([0-9.]+)M", out)
    return float(match.group(1)) if match else None


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def run_arm(
    family: str, row: SampleRow, state: dict[str, str], args: argparse.Namespace
) -> list[dict]:
    """One arm family on one row — one entry per label in ``LABELS[family]``."""
    if family in ("A", "A2"):
        return [run_production(row, temperature=None)]
    if family == "A0":
        return [run_production(row, temperature=0.0)]
    if family == "C":
        return [run_logits(state, args.decision_model)]
    if family in ("E", "E2"):
        return [run_ceiling(state, args)]
    return run_systemone(state, family, args)


def run_rows(
    rows: Sequence[SampleRow],
    families: Sequence[str],
    args: argparse.Namespace,
    *,
    domain: str,
    done: dict[str, dict[str, Any]],
    write: Callable[[dict[str, Any]], None],
) -> Counter:
    """Every (row, family) not yet answered; one appended line per row."""
    tally: Counter = Counter()
    sk = skillsel()
    for index, row in enumerate(rows, 1):
        arms: dict[str, Any] = {}
        for family in families:
            labels = LABELS[family]
            if all(answered(done.get(row.post_id, {}), label) for label in labels):
                continue
            if family in GPU_ARMS:
                sk.wait_out_schedule(args)
            state = build_state(domain, row.text())
            for label, entry in zip(labels, run_arm(family, row, state, args), strict=True):
                if family in SYSTEMONE_ARMS:
                    entry["swap_used_mb"] = swap_used_mb()
                arms[label] = entry
                tally[f"{label}:{entry['reason']}"] += 1
        if arms:
            write(row_record(row, arms))
            brief = " ".join(f"{k}={v.get('score')}" for k, v in arms.items())
            print(f"  [{index}/{len(rows)}] {row.post_id[:8]} {brief}", flush=True)
    return tally


def select_rows(args: argparse.Namespace, sample: Sequence[SampleRow]) -> list[SampleRow]:
    split = load_or_check_split(args, sample)
    wanted = subset_ids(split, sample, args.subset)
    if args.limit > 0:
        wanted = wanted[: args.limit]
    by_id = {row.post_id: row for row in sample}
    return [by_id[pid] for pid in wanted]


def load_or_check_split(args: argparse.Namespace, sample: Sequence[SampleRow]) -> dict[str, Any]:
    """The split re-derived from the seed; must equal the file written before any arm ran."""
    split = make_split(sample, seed=args.seed)
    path = Path(args.split)
    if args.write_split:
        assert_private_output(path).parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(split, indent=1) + "\n", encoding="utf-8")
        return split
    if not path.is_file():
        raise SystemExit(f"{path} is missing — run --write-split first")
    frozen = json.loads(path.read_text(encoding="utf-8"))
    if frozen != split:
        raise SystemExit(f"{path} no longer matches the sample + seed — the sample moved")
    return split


def prepare_prompting(home: Path) -> str:
    """Wire production's system prompt (for A / A0); return the arms' ``domain``."""
    sk = skillsel()
    identity_path, constitution_dir = sk.replay_prompt_sources(home)
    _system, note = sk.configure_replay_prompting(identity_path, constitution_dir)
    print(f"production system prompt: {note}", flush=True)
    return read_domain(identity_path)


def check_arm_mix(families: Sequence[str]) -> None:
    """Refuse unknown arms, and an Ollama arm in the same run as K / V.

    Rows run arm after arm, so ``A,K`` would load gemma and then call kev with
    gemma still resident on every row — the co-residence the 16 GB machine
    cannot hold (RFC-0043 §8: swap to 17 GB, 1.8x slower), and it would skew
    the K / V latency and swap the smoke rule reads.
    """
    unknown = [f for f in families if f not in LABELS]
    if unknown:
        raise SystemExit(f"unknown arm(s) {unknown}; J runs from evals/jev_arm.py")
    served = set(families) & SYSTEMONE_ARMS
    if served and set(families) & (GPU_ARMS - SYSTEMONE_ARMS):
        raise SystemExit(f"{sorted(served)} cannot run in the same run as an Ollama arm")


def run_main(args: argparse.Namespace, sample: Sequence[SampleRow]) -> int:
    families = [f.strip() for f in args.arms.split(",") if f.strip()]
    check_arm_mix(families)
    out_rows = assert_private_output(Path(args.out_rows))
    done = read_rows([out_rows])
    if done and not args.resume:
        raise SystemExit(f"{out_rows} already holds rows — pass --resume")
    rows = select_rows(args, sample)
    domain = prepare_prompting(Path(args.home))
    if SYSTEMONE_ARMS & set(families):
        base_url, _model = skillsel()._ollama_endpoint()
        print(f"ollama unload before K/V: {skillsel().ensure_ollama_idle(base_url)}", flush=True)
    print(f"{len(rows)} row(s), arms {families}, swap {swap_used_mb()} MB at start", flush=True)
    out_rows.parent.mkdir(parents=True, exist_ok=True)
    with out_rows.open("a", encoding="utf-8") as handle:

        def write(record: dict[str, Any]) -> None:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()

        tally = run_rows(rows, families, args, domain=domain, done=done, write=write)
    print(f"reasons: {dict(sorted(tally.items()))}", flush=True)
    return 0


# --------------------------------------------------------------------------
# Readings (RFC-0045's three, pre-registered; this code reports, it does not judge)
# --------------------------------------------------------------------------

C_LABEL = "C/logits/score4"
A_LABEL = "A/free/rep1"
CANDIDATE_LABELS = (
    "K/kev/score4",
    "K/kev/noul",
    "V/von/score4",
    "V/von/noul",
    A_LABEL,
    "A/free/rep2",
    "A0/t0",
    JEV_NOUL_LABEL,
)


def auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Mann-Whitney AUC from average ranks (ties count half). None without both classes.

    Rank form rather than all pairs: the holdout is ~2,500 rows and the
    bootstrap asks 2,000 times, where the pairwise loop does not finish.
    """
    positives = sum(1 for y in labels if y)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ranks = skillsel()._ranks(list(scores))
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def bootstrap_stat(
    n: int, stat: Callable[[list[int]], float | None], *, seed: int, iterations: int
) -> dict[str, Any]:
    """Point value + row-resampled 95% interval of any statistic over row indices."""
    point = stat(list(range(n)))
    if point is None:
        return {"n": n, "value": None, "lo": None, "hi": None}
    rng = random.Random(seed)
    draws = [stat([rng.randrange(n) for _ in range(n)]) for _ in range(iterations)]
    kept = sorted(d for d in draws if d is not None)
    if not kept:
        return {"n": n, "value": round(point, 4), "lo": None, "hi": None}
    return {
        "n": n,
        "value": round(point, 4),
        "lo": round(kept[int(0.025 * len(kept))], 4),
        "hi": round(kept[min(int(0.975 * len(kept)), len(kept) - 1)], 4),
    }


def _score(arms: dict[str, Any], label: str) -> float | None:
    return arms[label]["score"] if answered(arms, label) else None


def jev_on_topic(arms: dict[str, Any]) -> bool | None:
    """Jev's binary label: P(top level) >= 0.5 on the Score (provisional, README)."""
    return arms[JEV_SCORE_LABEL]["p_top"] >= 0.5 if answered(arms, JEV_SCORE_LABEL) else None


def reading_jev_vs_opus(merged: dict, ids: Sequence[str], *, seed: int, iters: int) -> dict:
    """Reading 1: may Jev be the label? (dev rows)."""
    sk = skillsel()
    out: dict[str, Any] = {}
    for rep in ("E/opus/rep1", "E/opus/rep2"):
        rows = [merged[i] for i in ids if answered(merged.get(i, {}), rep)]
        for jev_label in (JEV_SCORE_LABEL, JEV_NOUL_LABEL):
            # Each pairing keeps only the rows where BOTH sides answered: a
            # placeholder for a missing answer would be ranked like a value.
            pairs = [
                (a[jev_label]["score"], a[rep]["score"]) for a in rows if answered(a, jev_label)
            ]
            out[f"spearman {jev_label} vs {rep}"] = bootstrap_stat(
                len(pairs),
                lambda idx, p=pairs: sk.spearman([p[k][0] for k in idx], [p[k][1] for k in idx]),
                seed=seed,
                iterations=iters,
            )
        rows = [a for a in rows if answered(a, JEV_SCORE_LABEL)]
        agree = [float(jev_on_topic(a) == (a[rep]["level"] == TOP_LEVEL)) for a in rows]
        out[f"on-topic agreement {JEV_SCORE_LABEL} vs {rep}"] = sk.bootstrap_ci(
            agree, seed=seed, iterations=iters
        )
    both = [
        merged[i]
        for i in ids
        if answered(merged.get(i, {}), "E/opus/rep1") and answered(merged[i], "E/opus/rep2")
    ]
    self_agree = [
        float((a["E/opus/rep1"]["level"] == TOP_LEVEL) == (a["E/opus/rep2"]["level"] == TOP_LEVEL))
        for a in both
    ]
    out["opus self on-topic agreement (rep1 vs rep2)"] = sk.bootstrap_ci(
        self_agree, seed=seed, iterations=iters
    )
    out["opus self exact level agreement"] = sk.bootstrap_ci(
        [float(a["E/opus/rep1"]["level"] == a["E/opus/rep2"]["level"]) for a in both],
        seed=seed,
        iterations=iters,
    )
    out["opus level counts rep1"] = dict(
        Counter(str(a["E/opus/rep1"]["level"]) for a in both).most_common()
    )
    return out


def reading_candidates(merged: dict, ids: Sequence[str], *, seed: int, iters: int) -> dict:
    """Reading 2: |candidate - Jev P(on-topic)|, paired against C, plus AUC vs C."""
    sk = skillsel()
    out: dict[str, Any] = {}
    for label in CANDIDATE_LABELS:
        rows = [
            merged[i]
            for i in ids
            if all(answered(merged.get(i, {}), x) for x in (label, C_LABEL, JEV_SCORE_LABEL))
        ]
        if not rows:
            continue
        target = [a[JEV_SCORE_LABEL]["p_top"] for a in rows]
        y = [t >= 0.5 for t in target]
        cand = [a[label]["score"] for a in rows]
        base = [a[C_LABEL]["score"] for a in rows]
        err_c = [abs(c - t) for c, t in zip(cand, target, strict=True)]
        err_b = [abs(b - t) for b, t in zip(base, target, strict=True)]
        out[label] = {
            "n": len(rows),
            "jev_on_topic": sum(y),
            "error": sk.bootstrap_ci(err_c, seed=seed, iterations=iters),
            "error_C": sk.bootstrap_ci(err_b, seed=seed, iterations=iters),
            "error minus C": sk.paired_difference_ci(err_c, err_b, seed=seed, iterations=iters),
            "auc": bootstrap_stat(
                len(rows),
                lambda idx, c=cand, yy=y: auc([c[k] for k in idx], [yy[k] for k in idx]),
                seed=seed,
                iterations=iters,
            ),
            "auc_C": bootstrap_stat(
                len(rows),
                lambda idx, b=base, yy=y: auc([b[k] for k in idx], [yy[k] for k in idx]),
                seed=seed,
                iterations=iters,
            ),
        }
    c_rows = [merged[i] for i in ids if answered(merged.get(i, {}), C_LABEL)]
    c_rows = [a for a in c_rows if answered(a, JEV_SCORE_LABEL)]
    out[C_LABEL] = {
        "n": len(c_rows),
        "error": sk.bootstrap_ci(
            [abs(a[C_LABEL]["score"] - a[JEV_SCORE_LABEL]["p_top"]) for a in c_rows],
            seed=seed,
            iterations=iters,
        ),
    }
    return out


def reading_gate(merged: dict, logged: dict[str, float], *, seed: int, iters: int) -> dict:
    """Reading 3: the production gate seen from Jev. Numbers only."""
    sk = skillsel()
    out: dict[str, Any] = {}
    for name, score_of in (
        ("logged score", lambda pid, a: logged[pid]),
        (A_LABEL, lambda pid, a: _score(a, A_LABEL)),
        ("A0/t0", lambda pid, a: _score(a, "A0/t0")),
    ):
        passed = [
            jev_on_topic(a)
            for pid, a in merged.items()
            if pid in logged
            and jev_on_topic(a) is not None
            and (s := score_of(pid, a)) is not None
            and s >= PRODUCTION_GATE
        ]
        out[f"{name} >= {PRODUCTION_GATE}: Jev not on-topic"] = {
            "denominator": len(passed),
            "not_on_topic": sum(1 for v in passed if not v),
            "fraction": round(sum(1 for v in passed if not v) / len(passed), 4) if passed else None,
        }
    out["A self-agreement"] = _pair_agreement(merged, A_LABEL, "A/free/rep2", seed, iters)
    out["A0 vs A"] = _pair_agreement(merged, "A0/t0", A_LABEL, seed, iters)
    pairs = [
        (a["A0/t0"]["score"], a[A_LABEL]["score"], a[JEV_SCORE_LABEL]["p_top"])
        for a in merged.values()
        if all(answered(a, x) for x in ("A0/t0", A_LABEL, JEV_SCORE_LABEL))
    ]
    out["A0 minus A: error vs Jev"] = sk.paired_difference_ci(
        [abs(x - t) for x, _a, t in pairs],
        [abs(a - t) for _x, a, t in pairs],
        seed=seed,
        iterations=iters,
    )
    return out


def _pair_agreement(merged: dict, left: str, right: str, seed: int, iters: int) -> dict:
    sk = skillsel()
    pairs = [
        (a[left]["score"], a[right]["score"])
        for a in merged.values()
        if answered(a, left) and answered(a, right)
    ]
    return {
        "n": len(pairs),
        "exact": sk.bootstrap_ci([float(x == y) for x, y in pairs], seed=seed, iterations=iters),
        "gate agreement": sk.bootstrap_ci(
            [float((x >= PRODUCTION_GATE) == (y >= PRODUCTION_GATE)) for x, y in pairs],
            seed=seed,
            iterations=iters,
        ),
        "gate rate left": _rate([x >= PRODUCTION_GATE for x, _y in pairs]),
        "gate rate right": _rate([y >= PRODUCTION_GATE for _x, y in pairs]),
        "left minus right": sk.paired_difference_ci(
            [x for x, _y in pairs], [y for _x, y in pairs], seed=seed, iterations=iters
        ),
    }


def _rate(flags: Sequence[bool]) -> float | None:
    return round(sum(flags) / len(flags), 4) if flags else None


def jev_by_logged_value(merged: dict, logged: dict[str, float]) -> dict:
    """The correspondence table: gemma's logged value x Jev's modal level."""
    table: dict[str, dict[str, Any]] = {}
    for pid, arms in merged.items():
        if pid not in logged or not answered(arms, JEV_SCORE_LABEL):
            continue
        probs = arms[JEV_SCORE_LABEL]["probs"]
        cell = table.setdefault(f"{logged[pid]:.1f}", {"n": 0, "modal_level": Counter(), "p": []})
        cell["n"] += 1
        cell["modal_level"][str(max(range(len(probs)), key=probs.__getitem__))] += 1
        cell["p"].append(arms[JEV_SCORE_LABEL]["p_top"])
    return {
        value: {
            "n": cell["n"],
            "modal_level": dict(sorted(cell["modal_level"].items())),
            "mean_p_top": round(statistics.fmean(cell["p"]), 4),
            "on_topic_rate": _rate([p >= 0.5 for p in cell["p"]]),
        }
        for value, cell in sorted(table.items())
    }


def validity(merged: dict, logged: dict[str, float]) -> dict:
    """Does the replayed A land in the logged band? (the replay's fidelity check)."""
    rows = [(logged[pid], a[A_LABEL]["score"]) for pid, a in merged.items() if answered(a, A_LABEL)]
    if not rows:
        return {}
    return {
        "n": len(rows),
        "logged histogram": dict(sorted(Counter(f"{x:.1f}" for x, _a in rows).items())),
        "A histogram": dict(sorted(Counter(f"{a:.1f}" for _x, a in rows).items())),
        "logged gate rate": _rate([x >= PRODUCTION_GATE for x, _a in rows]),
        "A gate rate": _rate([a >= PRODUCTION_GATE for _x, a in rows]),
        "exact agreement with log": _rate([x == a for x, a in rows]),
        "gate agreement with log": _rate(
            [(x >= PRODUCTION_GATE) == (a >= PRODUCTION_GATE) for x, a in rows]
        ),
    }


def arm_counts(merged: dict, ids_by_subset: dict[str, set[str]]) -> dict:
    """Per label: answered / reasons / latency / swap, per subset."""
    out: dict[str, Any] = {}
    labels = sorted({label for arms in merged.values() for label in arms})
    for subset, ids in ids_by_subset.items():
        for label in labels:
            entries = [merged[i][label] for i in ids if label in merged.get(i, {})]
            if not entries:
                continue
            latencies = [e["latency_ms"] for e in entries if e.get("latency_ms")]
            swaps = [e["swap_used_mb"] for e in entries if e.get("swap_used_mb") is not None]
            out.setdefault(subset, {})[label] = {
                "rows": len(entries),
                "reasons": dict(Counter(e["reason"] for e in entries)),
                "latency_ms_median": statistics.median(latencies) if latencies else None,
                "swap_used_mb_first_max": [swaps[0], max(swaps)] if swaps else None,
            }
    return out


def write_summary(args: argparse.Namespace, sample: Sequence[SampleRow]) -> int:
    sk = skillsel()
    split = load_or_check_split(args, sample)
    merged = read_rows([Path(args.out_rows), *map(Path, args.augment)])
    logged = {row.post_id: row.logged_score for row in sample}
    dev = subset_ids(split, sample, "dev")
    holdout = subset_ids(split, sample, "holdout")
    seed, iters = args.seed, args.bootstrap_iterations
    summary = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": {"rows": len(sample), "population": split["population"]},
        "split": {k: split[k] for k in ("seed", "strata", "dev_count", "sub600_count")},
        "arms": arm_counts(merged, {"dev": set(dev), "holdout": set(holdout)}),
        "validity": validity(merged, logged),
        "reading1 (dev)": reading_jev_vs_opus(merged, dev, seed=seed, iters=iters),
        "reading2 dev": reading_candidates(merged, dev, seed=seed, iters=iters),
        "reading2 holdout": reading_candidates(merged, holdout, seed=seed, iters=iters),
        "reading3": reading_gate(merged, logged, seed=seed, iters=iters),
        "jev level by logged score": jev_by_logged_value(merged, logged),
    }
    sk.assert_no_text_in_summary(summary)
    out = Path(args.out_summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RFC-0045 relevance replay against Jev.")
    default_home = Path.home() / ".config" / "moltbook"
    parser.add_argument("--home", type=Path, default=default_home)
    parser.add_argument("--arms", default="", help="comma list of " + ",".join(LABELS))
    parser.add_argument("--subset", choices=("all", "dev", "sub600", "holdout"), default="dev")
    parser.add_argument("--limit", type=int, default=0, help="first N rows of the subset")
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    parser.add_argument("--split", default=str(DEFAULT_DIR / "split.json"))
    parser.add_argument("--write-split", action="store_true")
    parser.add_argument("--out-rows", default=str(DEFAULT_DIR / "rows.jsonl"))
    parser.add_argument("--resume", action="store_true", help="skip labels already answered")
    parser.add_argument("--augment", action="append", default=[], help="extra rows files")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--out-summary", default=str(DEFAULT_DIR / "summary.json"))
    parser.add_argument("--decision-model", default="gemma4:e4b")
    parser.add_argument("--ceiling-model", default="claude-opus-5")
    parser.add_argument("--ceiling-scratch", default=str(DEFAULT_DIR / "ceiling-scratch"))
    parser.add_argument("--ceiling-timeout", type=int, default=300)
    parser.add_argument("--kev-endpoint", default="http://127.0.0.1:8009")
    parser.add_argument("--von-endpoint", default="http://127.0.0.1:8010")
    parser.add_argument("--systemone-timeout", type=int, default=120)
    parser.add_argument("--schedule-lead-min", type=int, default=10)
    parser.add_argument("--schedule-trail-min", type=int, default=60)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample = load_sample(Path(args.home))
    if args.write_split:
        split = load_or_check_split(args, sample)
        print(f"split: population {split['population']} dev {split['dev_count']}", flush=True)
        return 0
    if args.summarize_only:
        return write_summary(args, sample)
    return run_main(args, sample)


if __name__ == "__main__":
    raise SystemExit(main())
