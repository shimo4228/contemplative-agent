#!/usr/bin/env python3
"""Offline 5-arm replay of pass-1 skill selection (RFC-0043, packet S1).

Answers RFC-0040's first question — "how much of the selector's hallucination
is the *interface* (free-form name generation) rather than the model?" — by
putting the SAME logged situations through five arms that differ only in how
the judgment is extracted:

* ``A`` ``free``   x2 — the logged prompt replayed as production sends it
  (no ``format=``, ``think=False``, ``num_predict=400``). The jitter floor and
  the hallucination baseline.
* ``B`` ``enum``   x2 — the same prompt with ``format=`` pinning the answer to
  a JSON array whose items are an ``enum`` of the row's own catalog names.
  Hallucination is structurally impossible; the script asserts it.
* ``C`` ``logits``    — one yes/no question per catalog skill, read from the
  first token's ``top_logprobs`` and turned into a probability by a two-way
  softmax. The sampled token is discarded; only the distribution is used.
* ``D`` ``gliclass``  — GLiClass multi-label, unadjusted. Optional import: a
  missing package or checkpoint is a NAMED absence, never a silent skip.
* ``E`` ``ceiling``   — claude-opus-5 with no tools, as a proxy for the right
  answer. Not ground truth (RFC-0043 Drawbacks); the rows where E and the
  local arms disagree are written to an adjudication file for the owner.

Read-only with respect to ``$MOLTBOOK_HOME``: rows are rebuilt from the base64
blobs already in ``logs/skill-selection-*.jsonl``, nothing is written back
there, and ``llm.configure`` is never called — so no telemetry or audit sink is
wired (``scripts/novelty_replay_ab.py``'s contract, RFC-0023).

**Reconstruction fidelity is asserted, not assumed.** Each row's prompt is
split at the template's own headers into a catalog block and a situation, and
the parse is then fed back through production's own formatter; a rebuilt prompt
that differs from the logged one by a single byte stops that row with reason
code ``roundtrip_mismatch`` rather than replaying something production never
sent. Arm A goes further and calls ``core.skill_selection.select_applicable_skills``
itself, so the matching and the rejected-name rule are production's, not a copy.

**Text discipline.** Decoded situations and whole prompts never reach stdout,
the row log or the summary. The row log carries selection sets, scores,
latencies and reason codes, plus the model-authored names that failed the
catalog match — scrubbed and cut to 80 characters, the same treatment
production gives them — and lands under ``.notes/`` (gitignored). The summary
carries aggregates only, and ``assert_no_text_in_summary`` walks all of it
before it is written. Only ``--adjudication`` — a local, gitignored file the
owner reads and this session does not — carries situation text, and only for
rows where E and another arm disagree. ``assert_output_paths_safe`` refuses any
output path inside ``$MOLTBOOK_HOME`` or ``docs/``.

Usage::

    uv run --no-sync python scripts/skillsel_arm_replay.py \\
        --days 21 --n 150 --seed 20260919 --arms A,B,C,D,E \\
        --out-rows .notes/skillsel-arm-replay/rows.jsonl \\
        --out-summary .notes/skillsel-arm-replay/summary.json
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import statistics
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
# ``evals`` is imported as a package from the repo root: the ceiling arm reuses
# the ONE hardened cloud-egress seam this repo already sanctions
# (``evals/judging.py::run_claude_raw``, named in
# ``tests/test_cloud_egress_absence.py``) rather than opening a second one.
# See ``run_ceiling`` for why that matters.
sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "skillsel-arm-replay/1"

ARMS = ("A", "B", "C", "D", "E")

# Arm labels as they appear in the row log and the summary. A and B run twice
# (self-agreement is the floor every cross-arm comparison is read against), so
# their labels carry a repetition index.
ARM_LABELS: dict[str, tuple[str, ...]] = {
    "A": ("A/free/rep1", "A/free/rep2"),
    "B": ("B/enum/rep1", "B/enum/rep2"),
    "C": ("C/logits",),
    "D": ("D/gliclass",),
    "E": ("E/ceiling",),
}

# ``--order-shuffle`` adds one more B repetition with the catalog order
# permuted. Named separately because it is a stability probe, not a third
# sample of the same arm: it answers "does the enum's answer depend on where a
# name sits in the list", which a plain rep cannot.
B_SHUFFLE_LABEL = "B/enum/shuffled"

# The selection template's own section headers. The split is by these markers
# and nothing else — a heuristic that guessed where the catalog ended would put
# situation text into the catalog on the first skill description containing a
# newline.
_SKILLS_HEADER = "## Skills\n\nEach line is one skill: `name — description`.\n\n"
_SITUATION_HEADER = "\n\n## Situation\n\n"
_INSTRUCTIONS_HEADER = "\n\n## Instructions\n\n"

# ``_render_catalog`` joins name and description with a spaced em dash.
_CATALOG_SEP = " — "

# Exclusion reason codes. Every dropped row is counted under one of these and
# the counts are reported; a row never disappears silently (ADR-0075).
EXCLUDE_NOT_JUDGED = "not_judged"
EXCLUDE_NO_PROMPT = "no_prompt_b64"
EXCLUDE_TRUNCATED = "prompt_truncated"
EXCLUDE_NO_SELECTION_ID = "no_selection_id"
EXCLUDE_UNSPLITTABLE = "prompt_unsplittable"
EXCLUDE_CATALOG_MISMATCH = "catalog_mismatch"
EXCLUDE_ROUNDTRIP = "roundtrip_mismatch"
EXCLUDE_DECODE = "prompt_undecodable"

# Per-arm failure reason codes.
ARM_LLM_NONE = "llm_none"
ARM_PARSE = "parse_failed"
ARM_LOGPROBS_UNAVAILABLE = "logprobs_unavailable"
ARM_GLICLASS_NOT_INSTALLED = "gliclass_not_installed"
ARM_CEILING_ERROR = "ceiling_error"

# Production's own selection budget (``skill_selection._SELECTION_NUM_PREDICT``);
# imported at call time rather than copied, so a change there changes the replay.

# The scheduled unattended sessions, in JST hours. Ollama-calling arms wait out
# a window around each so a replay never contends with the production agent for
# the one 16GB GPU (CLAUDE.md: no heavy experiments during scheduled sessions).
SCHEDULE_HOURS_JST = (0, 6, 12, 18)
JST = timezone(timedelta(hours=9))

# Arm D's pipeline, built at most once per process. Module-level because the
# checkpoint is ~1.6GB and the arm runs per row.
_GLICLASS_PIPELINE: Any = None


# --------------------------------------------------------------------------
# Row reconstruction (pure)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One replayable logged selection.

    ``catalog`` is the row's OWN catalog, parsed from its own prompt — the
    catalog grew 53 -> 57 across the window, so a shared catalog would judge
    some rows against skills that did not exist when they ran.
    """

    selection_id: str
    ts: str
    day: str
    catalog: tuple[tuple[str, str], ...]
    situation: str
    prompt: str
    logged_selected: tuple[str, ...]
    logged_rejected: tuple[str, ...]

    @property
    def catalog_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.catalog)

    @property
    def had_hallucination(self) -> bool:
        return bool(self.logged_rejected)


def split_prompt(prompt: str) -> tuple[str, str]:
    """Return ``(catalog_block, situation)`` of a logged selection prompt.

    Raises ``ValueError`` when any of the three template markers is missing or
    out of order — the caller turns that into ``prompt_unsplittable`` and drops
    the row rather than guessing where the boundary was.
    """
    skills_at = prompt.find(_SKILLS_HEADER)
    if skills_at < 0:
        raise ValueError("no skills header")
    catalog_start = skills_at + len(_SKILLS_HEADER)
    situation_at = prompt.find(_SITUATION_HEADER, catalog_start)
    if situation_at < 0:
        raise ValueError("no situation header")
    situation_start = situation_at + len(_SITUATION_HEADER)
    instructions_at = prompt.find(_INSTRUCTIONS_HEADER, situation_start)
    if instructions_at < 0:
        raise ValueError("no instructions header")
    return prompt[catalog_start:situation_at], prompt[situation_start:instructions_at]


def parse_catalog(block: str) -> tuple[tuple[str, str], ...]:
    """Catalog lines back into ``(name, description)`` pairs.

    A description may itself contain the separator, so the split is on the
    FIRST occurrence — which is where ``_render_catalog`` put it. A line with
    no separator is a name whose description was empty.
    """
    entries: list[tuple[str, str]] = []
    for line in block.split("\n"):
        if not line.strip():
            continue
        name, sep, description = line.partition(_CATALOG_SEP)
        entries.append((name.strip(), description.strip() if sep else ""))
    return tuple(entries)


def render_catalog(catalog: Sequence[tuple[str, str]]) -> str:
    """The catalog block as production renders it.

    Imported from production rather than re-derived would be better still, but
    ``_render_catalog`` takes ``SkillCatalogEntry`` values; this builds those
    and delegates, so the joining rule has exactly one owner.
    """
    from contemplative_agent.core.skill_selection import SkillCatalogEntry, _render_catalog

    return _render_catalog(
        tuple(SkillCatalogEntry(name=n, description=d, body_tokens=0) for n, d in catalog)
    )


def rebuild_prompt(catalog: Sequence[tuple[str, str]], situation: str) -> str:
    """Production's own prompt, from the parse. The fidelity check's other half."""
    from contemplative_agent.core.prompts import SKILL_SELECTION_PROMPT

    return SKILL_SELECTION_PROMPT.format(skill_catalog=render_catalog(catalog), situation=situation)


def row_from_record(record: dict[str, Any]) -> tuple[Row | None, str]:
    """``(row, "")`` or ``(None, reason_code)`` for one logged record.

    Five gates, in the order that makes the reason code the true cause: a
    non-judged verdict is not a failure of this script, a truncated prompt
    cannot be replayed at all, a row with no ``selection_id`` cannot be frozen
    into a reproducible sample (the field arrived with RFC-0028 on 2026-09-09),
    and an unsplittable or non-round-tripping prompt would have the replay
    judging something production never sent.
    """
    if record.get("verdict") != "judged":
        return None, EXCLUDE_NOT_JUDGED
    if record.get("prompt_truncated"):
        return None, EXCLUDE_TRUNCATED
    blob = record.get("prompt_b64")
    if not blob:
        return None, EXCLUDE_NO_PROMPT
    selection_id = record.get("selection_id")
    if not selection_id:
        return None, EXCLUDE_NO_SELECTION_ID
    try:
        prompt = base64.b64decode(blob).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None, EXCLUDE_DECODE
    try:
        catalog_block, situation = split_prompt(prompt)
    except ValueError:
        return None, EXCLUDE_UNSPLITTABLE
    catalog = parse_catalog(catalog_block)
    logged_names = record.get("catalog_names")
    if isinstance(logged_names, list):
        # The record writes ``catalog_names`` independently of the prompt, so a
        # mismatch means the split is wrong — a cheap check that runs before
        # the expensive one and names a different fault.
        if sorted(name for name, _ in catalog) != sorted(str(n) for n in logged_names):
            return None, EXCLUDE_CATALOG_MISMATCH
    if rebuild_prompt(catalog, situation) != prompt:
        return None, EXCLUDE_ROUNDTRIP
    day = str(record.get("ts", ""))[:10]
    return (
        Row(
            selection_id=str(selection_id),
            ts=str(record.get("ts", "")),
            day=day,
            catalog=catalog,
            situation=situation,
            prompt=prompt,
            logged_selected=tuple(str(s) for s in (record.get("selected") or [])),
            logged_rejected=tuple(str(s) for s in (record.get("rejected_names") or [])),
        ),
        "",
    )


def load_rows(
    log_dir: Path, *, days: int, today: date
) -> tuple[list[Row], dict[str, int], list[str]]:
    """Every replayable row in the window, with the exclusion tally and the days read.

    The window is cut on the log's FILE date, which is how every other reader
    of this log cuts it (``selection_window._iter_selection_days``); the record
    kind is read the same way too, so a record with no ``kind`` is a selection
    record here exactly as it is there.
    """
    from contemplative_agent.core.selection_window import SELECTION_RECORD_KIND

    since = today - timedelta(days=days - 1)
    rows: list[Row] = []
    excluded: dict[str, int] = {}
    days_read: list[str] = []
    for path in sorted(log_dir.glob("skill-selection-*.jsonl")):
        part = path.stem.removeprefix("skill-selection-")
        try:
            file_date = datetime.strptime(part, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (since <= file_date <= today):
            continue
        days_read.append(part)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                excluded["malformed_line"] = excluded.get("malformed_line", 0) + 1
                continue
            if not isinstance(record, dict):
                excluded["malformed_line"] = excluded.get("malformed_line", 0) + 1
                continue
            if record.get("kind", SELECTION_RECORD_KIND) != SELECTION_RECORD_KIND:
                continue
            row, reason = row_from_record(record)
            if row is None:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            rows.append(row)
    return rows, excluded, days_read


def stratified_sample(rows: Sequence[Row], *, n: int, seed: int) -> list[Row]:
    """``n`` rows, half from the hallucinating stratum and half from the clean one.

    Deterministic in ``seed``: the strata are sorted by ``selection_id`` before
    sampling, so the input's file order cannot move the result. When one stratum
    is short the other makes up the difference — the alternative (returning
    fewer rows than asked) would silently shrink the sample.
    """
    with_hallu = sorted((r for r in rows if r.had_hallucination), key=lambda r: r.selection_id)
    without = sorted((r for r in rows if not r.had_hallucination), key=lambda r: r.selection_id)
    want_each = n // 2
    take_h = min(want_each, len(with_hallu))
    take_w = min(n - take_h, len(without))
    take_h = min(len(with_hallu), take_h + (n - take_h - take_w))
    rng = random.Random(seed)
    picked = rng.sample(with_hallu, take_h) + rng.sample(without, take_w)
    return sorted(picked, key=lambda r: r.selection_id)


# --------------------------------------------------------------------------
# Set maths (pure)
# --------------------------------------------------------------------------


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Jaccard index of two name sets. Two empty sets agree perfectly (1.0).

    The empty/empty case is a real outcome here — "no skill applies" is a
    verdict the prompt explicitly offers — so scoring it 0.0 would read as
    disagreement between two arms that in fact said the same thing.
    """
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)


def precision_recall(predicted: Iterable[str], truth: Iterable[str]) -> tuple[float, float]:
    """Precision and recall of ``predicted`` against ``truth``.

    An empty prediction has precision 1.0 (it asserted nothing false) and an
    empty truth has recall 1.0 — stated explicitly because the alternative
    (0.0) makes an arm that correctly says "none" look like its worst case.
    """
    p, t = set(predicted), set(truth)
    precision = len(p & t) / len(p) if p else 1.0
    recall = len(p & t) / len(t) if t else 1.0
    return precision, recall


def binary_softmax(yes_logprob: float | None, no_logprob: float | None) -> float | None:
    """P(yes) over the {yes, no} pair alone, from their log-probabilities.

    Computed in log space with the max subtracted: the raw logprobs reach -12
    and below, where ``exp`` of the difference underflows to 0.0 and the ratio
    becomes 0/0. ``None`` when neither side was observed — an unobserved yes
    with an observed no is 0.0, which is information; two unobserved sides are
    not, and must not read as 0.5.
    """
    if yes_logprob is None and no_logprob is None:
        return None
    if yes_logprob is None:
        return 0.0
    if no_logprob is None:
        return 1.0
    top = max(yes_logprob, no_logprob)
    ey = math.exp(yes_logprob - top)
    en = math.exp(no_logprob - top)
    return ey / (ey + en)


def topk_set(scores: dict[str, float], k: int) -> tuple[str, ...]:
    """The ``k`` highest-scoring names, ties broken by name for determinism."""
    if k <= 0:
        return ()
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(sorted(name for name, _ in ordered[:k]))


def threshold_set(scores: dict[str, float], threshold: float) -> tuple[str, ...]:
    """Every name scoring at or above ``threshold``."""
    return tuple(sorted(name for name, score in scores.items() if score >= threshold))


def enum_schema(catalog_names: Sequence[str]) -> dict[str, Any]:
    """The ``format=`` schema that makes a hallucinated name unrepresentable.

    An empty array is the ``none`` verdict; there is no separate sentinel,
    because an enum that also admitted the string "none" would be back to
    accepting a name that is not a skill.
    """
    return {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {"type": "string", "enum": list(catalog_names)},
            }
        },
        "required": ["selected"],
    }


# --------------------------------------------------------------------------
# Schedule guard
# --------------------------------------------------------------------------


def schedule_wait_seconds(now: datetime, *, lead_min: int, trail_min: int) -> float:
    """Seconds to wait before an Ollama call, or 0.0 when outside every window.

    The windows are the scheduled unattended sessions in JST: a replay that ran
    through one would contend with production for the single GPU and would also
    be measuring a host under load (CLAUDE.md: no heavy experiments during
    scheduled sessions).
    """
    local = now.astimezone(JST)
    for hour in SCHEDULE_HOURS_JST:
        start = local.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
            minutes=lead_min
        )
        end = start + timedelta(minutes=lead_min + trail_min)
        # The 00:00 window opens on the previous calendar day; check both.
        for offset in (timedelta(0), timedelta(days=1)):
            s, e = start + offset, end + offset
            if s <= local < e:
                return (e - local).total_seconds()
    return 0.0


def wait_out_schedule(args: argparse.Namespace) -> None:
    """Block until outside a scheduled-session window. Prints, never silent."""
    while True:
        seconds = schedule_wait_seconds(
            datetime.now(timezone.utc),
            lead_min=args.schedule_lead_min,
            trail_min=args.schedule_trail_min,
        )
        if seconds <= 0:
            return
        print(f"  [schedule] inside a session window — waiting {seconds / 60:.1f} min", flush=True)
        time.sleep(min(seconds, 300))


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------


@dataclass
class ArmOutcome:
    """One arm's answer on one row.

    ``selected`` is the arm's name set. ``scores`` is populated only by the
    scoring arms (C, D), where collapsing to a set is a reading decision the
    summary makes twice (top-k and 0.5) rather than a fact the arm asserts.
    """

    selected: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    scores: dict[str, float] = field(default_factory=dict)
    latency_ms: int = 0
    reason: str = ""
    note: str = ""
    # ``(names scored, catalog size)`` for a scoring arm. A partial reading —
    # say 27 of 57 skills — collapses to a set over only the scored names and
    # would otherwise look exactly like a complete one in the summary.
    scored_of: tuple[int, int] | None = None


def replay_prompt_sources(home: Path) -> tuple[Path, Path]:
    """``(identity file, constitution dir)`` as production resolves them.

    Both names come from the adapter's own constants rather than a copy: the
    system prompt is the one piece of the replay that is NOT reconstructed from
    the log, so a stale spelling here would silently swap in a shorter prompt
    and the replay would be measuring a different regime with no sign of it.
    """
    from contemplative_agent.adapters.moltbook.config import (
        CONSTITUTION_DIRNAME,
        IDENTITY_FILENAME,
    )

    return home / IDENTITY_FILENAME, home / CONSTITUTION_DIRNAME


def configure_replay_prompting(identity_path: Path, constitution_dir: Path) -> tuple[str, str]:
    """Rebuild the selection call's system prompt. Returns ``(system, note)``.

    ``get_identity_system_prompt()`` = identity + axioms
    (``core.llm.prompting._identity_axioms_base``), and production wires BOTH:
    ``cli/runtime.py`` calls ``configure_llm(identity_path=...)`` and then
    ``configure_llm(axiom_prompt=load_constitution(CONSTITUTION_DIR))``. Loading
    only the identity leaves the axiom clauses out, which on the live home is
    most of the prompt by volume — arms A/B/C would then be measured under a
    system prompt production never used, and the RFC's own validity check (does
    arm A's hallucination rate land in the same band as the logged window?)
    would be comparing two regimes.

    ``configure_prompting`` is called directly rather than through
    ``llm.configure``: it has no telemetry or audit parameter at all, so the
    replay provably cannot wire the sink ``llm.configure`` would.

    What this CANNOT reproduce is time. identity.md and the constitution are
    both mutable, and the files read here are today's, not the ones in force
    when a row was logged. The returned note records what was actually found so
    the artifact says which prompt produced its numbers.
    """
    from contemplative_agent.core.domain import load_constitution
    from contemplative_agent.core.llm import prompting as _prompting

    parts: list[str] = []
    if identity_path.is_file():
        _prompting.configure_prompting(identity_path=identity_path)
        parts.append(f"identity={identity_path.name}:{identity_path.stat().st_size}B")
    else:
        parts.append(f"identity=MISSING at {identity_path} (DEFAULT system prompt)")
    clauses = load_constitution(constitution_dir) if constitution_dir.is_dir() else ""
    if clauses:
        _prompting.configure_prompting(axiom_prompt=clauses)
        parts.append(f"axioms={constitution_dir.name}:{len(clauses)}chars")
    else:
        parts.append(f"axioms=MISSING at {constitution_dir} (production injects them)")
    return _prompting.get_identity_system_prompt(), "; ".join(parts)


def run_free(row: Row, system: str) -> ArmOutcome:
    """Arm A: production's own call, on production's own prompt.

    ``select_applicable_skills`` is called rather than reimplemented — it
    rebuilds the prompt from the catalog, and ``row_from_record`` has already
    asserted that rebuild is byte-identical to the logged prompt. So this is
    the production path, and the rejected-name rule is production's.
    """
    from contemplative_agent.core.llm import prompting as _prompting
    from contemplative_agent.core.skill_selection import (
        SkillCatalogEntry,
        select_applicable_skills,
    )

    catalog = tuple(SkillCatalogEntry(name=n, description=d, body_tokens=0) for n, d in row.catalog)
    started = time.monotonic()
    # ``select_applicable_skills`` takes the system prompt from the module
    # config; the replay's config is already set, and this asserts it.
    assert _prompting.get_identity_system_prompt() == system
    result = select_applicable_skills(row.situation, catalog)
    latency = int((time.monotonic() - started) * 1000)
    if result.verdict != "judged":
        return ArmOutcome(latency_ms=latency, reason=result.verdict)
    return ArmOutcome(
        selected=result.selected,
        rejected=result.rejected_names,
        latency_ms=latency,
    )


def run_enum(row: Row, system: str, *, catalog_order: Sequence[str] | None = None) -> ArmOutcome:
    """Arm B: the same prompt, with the answer constrained to catalog names.

    ``catalog_order`` permutes only the order the enum lists, never the prompt
    — the order-shuffle probe asks whether the constrained decode depends on
    position within the schema, which is the only place the order can matter
    once the prompt is fixed.
    """
    from contemplative_agent.core import llm
    from contemplative_agent.core.skill_selection import _SELECTION_NUM_PREDICT

    names = list(catalog_order) if catalog_order is not None else list(row.catalog_names)
    started = time.monotonic()
    raw = llm.generate(
        row.prompt,
        system=system,
        num_predict=_SELECTION_NUM_PREDICT,
        format=enum_schema(names),
        caller="rfc0043.enum",
        think=False,
    )
    latency = int((time.monotonic() - started) * 1000)
    if raw is None:
        return ArmOutcome(latency_ms=latency, reason=ARM_LLM_NONE)
    try:
        data = json.loads(_strip_fence(raw))
        picked = data["selected"]
        if not isinstance(picked, list):
            raise TypeError("selected is not a list")
        selected = tuple(str(name) for name in picked)
    except (json.JSONDecodeError, KeyError, TypeError):
        return ArmOutcome(latency_ms=latency, reason=ARM_PARSE)
    # The arm's whole claim. A name outside the catalog here would mean the
    # backend did not honour the enum, which is a finding about the backend,
    # not a hallucination rate — so it stops the run rather than being counted.
    outside = sorted(set(selected) - set(row.catalog_names))
    assert not outside, f"enum arm returned non-catalog names: {outside}"
    return ArmOutcome(selected=tuple(sorted(set(selected))), latency_ms=latency)


def _strip_fence(text: str) -> str:
    """Drop a ```json fence if the model added one around its JSON."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


# Yes/no token surfaces the first-token reading accepts. Compared on the
# stripped, lowercased token text, so "Yes", " yes" and "YES" are one bucket —
# the tokenizer's casing is not a judgment.
_YES_TOKENS = frozenset({"yes", "y", "true"})
_NO_TOKENS = frozenset({"no", "n", "false"})

_LOGIT_QUESTION = (
    "{situation}\n\n"
    "## Question\n\n"
    "Does the skill `{name} — {description}` apply to the situation above?\n"
    "Answer with exactly one word: yes or no."
)


def ollama_yes_no(
    base_url: str, model: str, prompt: str, system: str, *, timeout: tuple[int, int]
) -> tuple[float | None, dict[str, Any]]:
    """P(yes) for one skill, from the first token's ``top_logprobs``.

    The sampled token is thrown away on purpose: a single greedy sample is a
    coarse reading of exactly the distribution the logprobs give in full, and
    RFC-0043's arm C is about the distribution.

    ``core.llm`` does not expose ``logprobs``, so this posts to the Ollama HTTP
    API itself. The base URL goes through ``core.llm.guard.validate_trusted_url``
    first — the same allowlist the production path uses — so this arm cannot
    reach a host the agent itself could not.
    """
    import requests

    from contemplative_agent.core.llm.guard import validate_trusted_url

    url = validate_trusted_url(base_url, source="rfc0043.logits")
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 1, "num_ctx": 32768},
        "logprobs": True,
        "top_logprobs": 20,
    }
    response = requests.post(
        f"{url}/api/generate", json=payload, timeout=timeout, allow_redirects=False
    )
    response.raise_for_status()
    entries = response.json().get("logprobs") or []
    if not entries:
        return None, {"reason": ARM_LOGPROBS_UNAVAILABLE}
    alternatives = entries[0].get("top_logprobs") or [entries[0]]
    yes_lp: float | None = None
    no_lp: float | None = None
    for alt in alternatives:
        token = str(alt.get("token", "")).strip().lower()
        logprob = alt.get("logprob")
        if not isinstance(logprob, (int, float)):
            continue
        # First occurrence wins: ``top_logprobs`` is ordered by probability, so
        # the first "yes"-surface token is the most likely spelling of yes.
        if token in _YES_TOKENS and yes_lp is None:
            yes_lp = float(logprob)
        elif token in _NO_TOKENS and no_lp is None:
            no_lp = float(logprob)
    probability = binary_softmax(yes_lp, no_lp)
    meta: dict[str, Any] = {"yes_logprob": yes_lp, "no_logprob": no_lp}
    if probability is None:
        meta["reason"] = ARM_LOGPROBS_UNAVAILABLE
    return probability, meta


def run_logits(row: Row, system: str, args: argparse.Namespace) -> ArmOutcome:
    """Arm C: one yes/no question per catalog skill.

    Slow by construction — one call per skill per row — and the latency is
    reported as what it is: the cost of this interface as a CONTRAST, not a
    proposal for production (RFC-0043 Drawbacks).
    """
    from contemplative_agent.core.llm import _get_model, _get_ollama_url

    scores: dict[str, float] = {}
    unobserved = 0
    started = time.monotonic()
    for name, description in row.catalog:
        prompt = _LOGIT_QUESTION.format(situation=row.situation, name=name, description=description)
        probability, _meta = ollama_yes_no(
            _get_ollama_url(),
            _get_model(),
            prompt,
            system,
            timeout=(30, args.ollama_timeout),
        )
        if probability is None:
            unobserved += 1
            continue
        scores[name] = probability
    latency = int((time.monotonic() - started) * 1000)
    if not scores:
        return ArmOutcome(latency_ms=latency, reason=ARM_LOGPROBS_UNAVAILABLE)
    note = f"{unobserved} skill(s) had no yes/no token in top_logprobs" if unobserved else ""
    return ArmOutcome(
        scores=scores,
        latency_ms=latency,
        note=note,
        scored_of=(len(scores), len(row.catalog)),
    )


def run_gliclass(row: Row, args: argparse.Namespace) -> ArmOutcome:
    """Arm D: GLiClass multi-label, unadjusted — or a named absence.

    Optional import. A missing package is reported as ``gliclass_not_installed``
    and the arm is a NAMED blank in the summary: RFC-0043's second criterion
    asks whether C or D reaches the ceiling, and an arm that quietly vanished
    would let that question read as answered.

    Three defaults below are not arbitrary; each disarms a way this arm can
    look like it worked while measuring something else (checkpoint sources
    read 2026-09-19, listed in the packet report):

    * ``--gliclass-checkpoint`` defaults to ``gliclass-modern-large-v3.0``,
      the only large-tier checkpoint with a genuinely trained 8192 context.
      The DeBERTa v3 checkpoints declare ``max_position_embeddings: 512`` but
      set ``position_biased_input: false``, so no absolute position table is
      allocated and long input does not error — it just runs ~10x past the
      length the model was trained at, silently.
    * ``--gliclass-max-length`` is passed explicitly because the pipeline's own
      default is 1024 WITH ``truncation=True``: at the default, a 5,000-char
      situation is cut with no error and the scores are for a fragment.
    * ``--gliclass-device`` is turned into a ``torch.device`` before it is
      passed. The pipeline only honours a device STRING when it contains
      "cuda"; ``device="mps"`` falls through to CPU silently, while the
      ``torch.device`` object is taken as given.
    """
    try:
        import torch  # type: ignore
        from gliclass import GLiClassModel, ZeroShotClassificationPipeline  # type: ignore
        from transformers import AutoTokenizer  # type: ignore
    except ImportError as exc:
        return ArmOutcome(reason=ARM_GLICLASS_NOT_INSTALLED, note=str(exc)[:200])

    labels = [f"{name}{_CATALOG_SEP}{description}" for name, description in row.catalog]
    # Built once per process and cached. Constructing it inside the timed region
    # would make this arm's published latency the checkpoint LOAD time, sitting
    # in the summary beside B's and C's inference latencies as if comparable —
    # and would reload ~1.6GB of weights on every one of 150 rows.
    global _GLICLASS_PIPELINE
    load_ms = 0
    if _GLICLASS_PIPELINE is None:
        load_started = time.monotonic()
        model = GLiClassModel.from_pretrained(args.gliclass_checkpoint)
        tokenizer = AutoTokenizer.from_pretrained(args.gliclass_checkpoint)
        _GLICLASS_PIPELINE = ZeroShotClassificationPipeline(
            model,
            tokenizer,
            classification_type="multi-label",
            device=torch.device(args.gliclass_device),
            max_length=args.gliclass_max_length,
        )
        load_ms = int((time.monotonic() - load_started) * 1000)
    pipeline = _GLICLASS_PIPELINE
    started = time.monotonic()
    scores: dict[str, float] = {}
    # Labels are independent under multi-label, so splitting them across passes
    # changes nothing but the input length — which is the whole reason to split.
    # ``0`` means one pass, which is what the 8192 default checkpoint affords.
    stride = args.gliclass_label_batch or len(labels)
    for start in range(0, len(labels), stride):
        batch = labels[start : start + stride]
        results = pipeline(row.situation, batch, threshold=0.0)[0]
        for entry in results:
            name = str(entry["label"]).partition(_CATALOG_SEP)[0].strip()
            scores[name] = float(entry["score"])
    return ArmOutcome(
        scores=scores,
        latency_ms=int((time.monotonic() - started) * 1000),
        scored_of=(len(scores), len(row.catalog)),
        note=f"checkpoint load {load_ms} ms (once per process)" if load_ms else "",
    )


_CEILING_PROMPT = (
    "You are selecting which of a fixed catalog of learned skills apply to a "
    "situation.\n\n"
    "## Skills\n\nEach line is one skill: `name — description`.\n\n"
    "{catalog}\n\n"
    "## Situation\n\n"
    "{situation}\n\n"
    "## Instructions\n\n"
    "Select only the skills whose trigger conditions are explicitly met by the "
    "situation. Do not select a skill merely because it seems generally useful.\n"
    "Return ONLY a JSON array of skill names, copied exactly from the list above. "
    "Return [] if none apply. No prose, no code fence."
)


def run_ceiling(row: Row, args: argparse.Namespace) -> ArmOutcome:
    """Arm E: claude-opus-5 with no tools, as a proxy for the right answer.

    The subprocess is NOT spawned here. It goes through
    ``evals/judging.py::run_claude_raw`` — the one cloud-egress seam this repo
    sanctions (``tests/test_cloud_egress_absence.py`` names it), which already
    pins the isolation set: no settings or CLAUDE.md, no tools, no MCP servers,
    an allowlisted environment, a scratch cwd, and the prompt on stdin rather
    than argv. Opening a second subprocess here would mean a second isolation
    set to keep correct, and the guard test would be right to fail it.

    **A coverage note for whoever reviews this.** That guard text-scans ``src/``
    and ``scripts/`` for the CLI invocation, so it cannot see egress reached
    through an import — which is what this function does. The compensating
    control is ``TestCloudEgressStaysInOneSeam`` in
    ``tests/test_skillsel_arm_replay.py``: it parses this file's imports and
    fails if a second subprocess appears or if the seam stops going through
    ``evals/judging.py``. Upgrading the original guard from a text scan to an
    import-reachability check is a broader change than this packet, and is
    named in the packet report rather than done here.

    The situation is carried verbatim from the log, where production had
    already wrapped it in the untrusted frame (``select_applicable_skills``
    requires its caller to wrap) — so the untrusted boundary travels with the
    text instead of being re-applied here from memory.

    Names outside the catalog are recorded as ``rejected`` by the same rule
    arm A uses; the ceiling is not exempt from the catalog.
    """
    from evals.judging import JudgeError, run_claude_raw

    prompt = _CEILING_PROMPT.format(catalog=render_catalog(row.catalog), situation=row.situation)
    started = time.monotonic()
    try:
        raw = run_claude_raw(
            prompt,
            model=args.ceiling_model,
            scratch_dir=Path(args.ceiling_scratch),
            timeout=args.ceiling_timeout,
        )
    except JudgeError as exc:
        return ArmOutcome(
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=ARM_CEILING_ERROR,
            note=type(exc).__name__,
        )
    latency = int((time.monotonic() - started) * 1000)
    try:
        picked = json.loads(_strip_fence(raw))
        if not isinstance(picked, list):
            raise TypeError("not a list")
    except (json.JSONDecodeError, TypeError):
        return ArmOutcome(latency_ms=latency, reason=ARM_PARSE)
    from contemplative_agent.core._io import scrub_control

    by_lower = {name.lower(): name for name in row.catalog_names}
    selected: set[str] = set()
    rejected: list[str] = []
    for item in picked:
        canonical = by_lower.get(str(item).strip().lower())
        if canonical is None:
            # Same treatment production gives arm A's rejected names
            # (``skill_selection.py`` scrubs before they enter the plaintext
            # audit field): this is raw model output shaped by untrusted input,
            # and the two rejected-name columns sit side by side in one row.
            rejected.append(scrub_control(str(item), 80))
        else:
            selected.add(canonical)
    return ArmOutcome(
        selected=tuple(sorted(selected)),
        rejected=tuple(rejected),
        latency_ms=latency,
    )


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

# Longest string the summary may carry at a leaf. Every legitimate string in
# this artifact is a label, a reason code, a catalog name or a short fixed
# sentence; a situation excerpt is thousands of characters. The bound is on the
# VALUE, not on the key name — a key-name denylist would pass
# ``{"note": "<a whole post>"}`` and would admit any field a future arm adds
# under a name nobody thought to ban.
SUMMARY_MAX_LEAF_CHARS = 200

# Keys whose string values are prose the script itself wrote (the fidelity
# note, the collapse-rule descriptions). Named one by one so a new free-text
# field has to be added here deliberately rather than inheriting the exemption.
SUMMARY_PROSE_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "home",
        "generation_model",
        "ollama_base_url",
        "prompt",
        "system",
        "system_sources",
        "sink",
        "arm_A_path",
        "topk",
        "half",
    }
)
# Deliberately NOT exempt: ``note`` / ``notes``. Those are the fields most
# likely to grow into a free-text channel, and every note this script writes is
# a short fixed sentence well under the bound.


def assert_no_text_in_summary(summary: object, path: str = "$", key: str = "") -> None:
    """Fail loudly if anything long enough to be a situation reached the summary.

    The summary is the artifact that becomes ``docs/evidence/`` — public. This
    walks the WHOLE object before it is written, so "we did not put post bodies
    in evidence" is a checked property rather than a habit.

    The check is on leaf values: a string longer than
    :data:`SUMMARY_MAX_LEAF_CHARS` stops the write unless its key is named in
    :data:`SUMMARY_PROSE_KEYS`. Dict KEYS are checked the same way, because a
    catalog name is a key here and a hallucinated "name" can be a whole line of
    model output.
    """
    if isinstance(summary, dict):
        for child_key, value in summary.items():
            text = str(child_key)
            if len(text) > SUMMARY_MAX_LEAF_CHARS:
                raise AssertionError(f"summary key at {path} is {len(text)} chars — too long")
            assert_no_text_in_summary(value, f"{path}.{text}", text)
    elif isinstance(summary, list):
        for i, item in enumerate(summary):
            assert_no_text_in_summary(item, f"{path}[{i}]", key)
    elif isinstance(summary, str):
        if len(summary) > SUMMARY_MAX_LEAF_CHARS and key not in SUMMARY_PROSE_KEYS:
            raise AssertionError(
                f"summary value at {path} is {len(summary)} chars — may carry post text"
            )


def _spread(values: Sequence[float]) -> dict[str, Any]:
    """n / min / median / max — never a lone number (skill measurement-discipline)."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": round(ordered[0], 4),
        "median": round(statistics.median(ordered), 4),
        "max": round(ordered[-1], 4),
        "mean": round(statistics.fmean(ordered), 4),
    }


def _set_for(entry: dict[str, Any], rule: str, k: int) -> tuple[str, ...] | None:
    """One arm's name set under one collapsing rule, or ``None`` if it has none.

    A scoring arm has no set of its own; the summary makes two (``topk`` with
    k = the same row's arm-A selection size, and ``0.5``) and reports both
    rather than picking one (RFC-0043: no single scalar).
    """
    if entry.get("reason"):
        return None
    scores = entry.get("scores")
    if scores:
        return topk_set(scores, k) if rule == "topk" else threshold_set(scores, 0.5)
    selected = entry.get("selected")
    return tuple(selected) if selected is not None else None


CEILING_LABEL = "E/ceiling"


def _arm_reading(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """One arm's own numbers: failures, hallucination, sizes, latency.

    Rows the arm failed on are counted under their reason code and dropped from
    every rate — folding a failed call in as "selected nothing" would let a
    flaky host read as an arm that agrees with the ceiling less.
    """
    failures: dict[str, int] = {}
    for entry in entries:
        if entry.get("reason"):
            failures[entry["reason"]] = failures.get(entry["reason"], 0) + 1
    ok = [e for e in entries if not e.get("reason")]
    hallucinating = [e for e in ok if e.get("rejected")]
    sizes = [len(e.get("selected") or ()) for e in ok if e.get("selected") is not None]
    return {
        "rows_attempted": len(entries),
        "rows_ok": len(ok),
        "failures": failures,
        "hallucination": {
            "rows_with_a_rejected_name": len(hallucinating),
            "rows_ok": len(ok),
            "rate": round(len(hallucinating) / len(ok), 4) if ok else None,
            "rejected_names_total": sum(len(e.get("rejected") or ()) for e in ok),
        },
        "selection_size": _spread([float(s) for s in sizes]),
        "scored_arm": bool(ok and ok[0].get("scores")),
        "latency_ms": _spread([float(e.get("latency_ms", 0)) for e in entries]),
        # A scoring arm that read only part of the catalog still produces a set,
        # and that set looks complete. These two say how much of the catalog it
        # actually scored, and carry each arm's own note rather than dropping it.
        "catalog_scored": _spread([float(e["scored_of"][0]) for e in ok if e.get("scored_of")]),
        "catalog_size": _spread([float(e["scored_of"][1]) for e in ok if e.get("scored_of")]),
        "notes": _count(e["note"] for e in entries if e.get("note")),
    }


def _ceiling_pairs(
    rows: list[dict[str, Any]], label: str, rule: str
) -> tuple[list[tuple[tuple[str, ...], tuple[str, ...]]], int]:
    """``(arm set, ceiling set)`` for every row where both arms answered, plus the dropped-row count.

    ``k`` for the top-k rule is taken per row from that row's own A/free/rep1
    size, so a scoring arm is asked for as many skills as the free arm picked
    there — not a constant nobody chose.

    A scoring arm has no ``k`` on a row where arm A did not answer, and ``k=0``
    would credit it with selecting nothing — an agreement number that is a
    property of the missing reference, not of the arm. Two different causes get
    two different handlings: arm A missing from the RUN is a stop (the whole
    comparison is unobtainable), while arm A failing on ONE row just drops that
    row from the pairs. A transient ``fail_open_llm`` in hour three of a run
    must not make the summary unobtainable.

    Returns ``(pairs, rows dropped for a missing k)``.
    """
    free_label = ARM_LABELS["A"][0]
    needs_k = rule == "topk"
    if needs_k and not any(free_label in row.get("arms", {}) for row in rows):
        raise SystemExit(
            f"arm {label} is scored and needs a top-k k, but {free_label} was not run — "
            "rerun with arm A included, or read the @half rule only"
        )
    pairs: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    dropped = 0
    for row in rows:
        arms = row.get("arms", {})
        if CEILING_LABEL not in arms or label not in arms:
            continue
        truth = _set_for(arms[CEILING_LABEL], rule, 0)
        if truth is None:
            continue
        reference = _set_for(arms.get(free_label, {}), "topk", 0)
        if needs_k and arms[label].get("scores") and reference is None:
            dropped += 1
            continue
        got = _set_for(arms[label], rule, len(reference or ()))
        if got is None:
            continue
        pairs.append((got, truth))
    return pairs, dropped


def _per_skill_cells(
    pairs: list[tuple[tuple[str, ...], tuple[str, ...]]],
) -> dict[str, dict[str, Any]]:
    """tp / fp / fn plus precision and recall, per skill name."""
    cells: dict[str, dict[str, Any]] = {}
    for got, truth in pairs:
        for name in set(got) | set(truth):
            cell = cells.setdefault(name, {"tp": 0, "fp": 0, "fn": 0})
            if name in got and name in truth:
                cell["tp"] += 1
            elif name in got:
                cell["fp"] += 1
            else:
                cell["fn"] += 1
    for cell in cells.values():
        denom_p = cell["tp"] + cell["fp"]
        denom_r = cell["tp"] + cell["fn"]
        cell["precision"] = round(cell["tp"] / denom_p, 4) if denom_p else None
        cell["recall"] = round(cell["tp"] / denom_r, 4) if denom_r else None
    return cells


def _self_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Within-arm Jaccard for the repeated arms — the floor every gap clears."""
    out: dict[str, Any] = {}
    for family in ("A", "B"):
        left, right = ARM_LABELS[family]
        out[family] = _spread(
            [
                jaccard(r["arms"][left]["selected"], r["arms"][right]["selected"])
                for r in rows
                if left in r.get("arms", {})
                and right in r.get("arms", {})
                and not r["arms"][left].get("reason")
                and not r["arms"][right].get("reason")
            ]
        )
    return out


def summarize(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """Turn the row log into the pre-registered readings.

    Every rate carries its denominator. A scoring arm (C, D) gets BOTH
    collapsing rules reported side by side; a set arm gets the one set it
    asserted. Neither is reduced to a single scalar (RFC-0043).
    """
    labels = sorted({label for row in rows for label in row.get("arms", {})})
    by_label = {
        label: _arm_reading([r["arms"][label] for r in rows if label in r.get("arms", {})])
        for label in labels
    }

    versus_ceiling: dict[str, Any] = {}
    per_skill: dict[str, dict[str, dict[str, Any]]] = {}
    for label in labels:
        if label == CEILING_LABEL:
            continue
        scored = by_label[label]["scored_arm"]
        for rule in ("topk", "half") if scored else ("topk",):
            pairs, dropped = _ceiling_pairs(rows, label, rule)
            if not pairs:
                continue
            key = f"{label}@{rule}" if scored else label
            versus_ceiling[key] = {
                "rows": len(pairs),
                "rows_dropped_no_k": dropped,
                "jaccard": _spread([jaccard(g, t) for g, t in pairs]),
                "precision": _spread([precision_recall(g, t)[0] for g, t in pairs]),
                "recall": _spread([precision_recall(g, t)[1] for g, t in pairs]),
            }
            per_skill[key] = _per_skill_cells(pairs)

    return {
        "schema": SCHEMA,
        **meta,
        "arms": by_label,
        "self_agreement_jaccard": _self_agreement(rows),
        "versus_ceiling": versus_ceiling,
        "per_skill_versus_ceiling": per_skill,
        "collapse_rules": {
            "topk": "k = the same row's A/free/rep1 selection size",
            "half": "score >= 0.5",
            "note": "reported for scoring arms (C, D) only; set arms have one set",
        },
    }


def write_adjudication(rows: list[dict[str, Any]], by_id: dict[str, Row], path: Path) -> int:
    """Rows where the ceiling and a local arm disagree, with the situation.

    The owner reads this file; this session does not (it carries other agents'
    post text). It lives outside ``docs/`` for the same reason.
    """
    ceiling = "E/ceiling"
    blocks: list[str] = []
    for record in rows:
        arms = record.get("arms", {})
        if ceiling not in arms or arms[ceiling].get("reason"):
            continue
        truth = set(arms[ceiling].get("selected") or ())
        disagreeing = {
            label: sorted(set(entry.get("selected") or ()) ^ truth)
            for label, entry in arms.items()
            if label != ceiling
            and not entry.get("reason")
            and entry.get("selected") is not None
            and set(entry["selected"]) != truth
        }
        if not disagreeing:
            continue
        row = by_id.get(record["selection_id"])
        if row is None:
            continue
        lines = [
            f"## {record['selection_id']} ({row.ts})",
            "",
            f"- ceiling (E): {sorted(truth) or '[]'}",
        ]
        for label, delta in sorted(disagreeing.items()):
            lines.append(
                f"- {label}: {sorted(arms[label]['selected']) or '[]'}  (symmetric diff: {delta})"
            )
        lines += [
            "",
            "### Situation (untrusted — external post text)",
            "",
            "```",
            row.situation,
            "```",
            "",
        ]
        blocks.append("\n".join(lines))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# RFC-0043 adjudication — rows where the ceiling and a local arm disagree\n\n"
        "Owner-only. The situation blocks are other agents' posts (untrusted).\n\n"
        + "\n".join(blocks),
        encoding="utf-8",
    )
    return len(blocks)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def _load_done(path: Path) -> tuple[list[dict[str, Any]], set[str], int]:
    """``(rows, ids already replayed, unparseable line count)`` for ``--resume``.

    The malformed count is returned rather than swallowed: a dropped line leaves
    its id out of the resume set, so that row would be replayed and appended a
    second time, and the summary would count it twice.
    """
    if not path.is_file():
        return [], set(), 0
    records: list[dict[str, Any]] = []
    malformed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            malformed += 1
    return records, {str(r.get("selection_id")) for r in records}, malformed


def _arm_to_dict(outcome: ArmOutcome) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "selected": list(outcome.selected),
        "rejected": list(outcome.rejected),
        "latency_ms": outcome.latency_ms,
    }
    if outcome.scores:
        payload["scores"] = {k: round(v, 6) for k, v in outcome.scores.items()}
        payload["selected"] = None  # a scoring arm asserts no set of its own
    if outcome.scored_of is not None:
        payload["scored_of"] = list(outcome.scored_of)
    if outcome.reason:
        payload["reason"] = outcome.reason
    if outcome.note:
        payload["note"] = outcome.note
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RFC-0043: offline 5-arm replay of pass-1 skill selection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    default_home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    parser.add_argument("--home", type=Path, default=default_home)
    parser.add_argument("--days", type=int, default=21, help="window width in days (default 21)")
    parser.add_argument("--n", type=int, default=150, help="sample size (default 150)")
    parser.add_argument("--seed", type=int, default=20260919)
    parser.add_argument("--arms", default="A,B,C,D,E", help="subset of A,B,C,D,E")
    parser.add_argument(
        "--order-shuffle", action="store_true", help="one extra B rep, enum order permuted"
    )
    parser.add_argument(
        "--out-rows", type=Path, default=Path(".notes/skillsel-arm-replay/rows.jsonl")
    )
    parser.add_argument(
        "--out-summary", type=Path, default=Path(".notes/skillsel-arm-replay/summary.json")
    )
    parser.add_argument(
        "--adjudication",
        type=Path,
        default=Path(".notes/skillsel-arm-replay/adjudication.md"),
        help="owner-only file carrying situation text for disagreeing rows",
    )
    parser.add_argument(
        "--resume", action="store_true", help="skip selection_ids already in --out-rows"
    )
    parser.add_argument("--schedule-lead-min", type=int, default=10)
    parser.add_argument("--schedule-trail-min", type=int, default=60)
    parser.add_argument("--ollama-timeout", type=int, default=1200)
    parser.add_argument("--ceiling-model", default="claude-opus-5")
    parser.add_argument("--ceiling-timeout", type=int, default=300)
    parser.add_argument(
        "--ceiling-scratch",
        default=str(Path(".notes/skillsel-arm-replay/ceiling-scratch")),
    )
    parser.add_argument(
        "--gliclass-checkpoint",
        default="knowledgator/gliclass-modern-large-v3.0",
        help="8192-context ModernBERT tier; see run_gliclass for why not the DeBERTa v3 tier",
    )
    parser.add_argument(
        "--gliclass-device", default="cpu", help="cpu or mps (never a bare string to the pipeline)"
    )
    parser.add_argument("--gliclass-max-length", type=int, default=6144)
    parser.add_argument(
        "--gliclass-label-batch",
        type=int,
        default=0,
        help="labels per pass; 0 = one pass (multi-label labels are independent)",
    )
    parser.add_argument(
        "--summarize-only", action="store_true", help="re-read --out-rows, no calls"
    )
    return parser


def run_row(
    row: Row, system: str, wanted: Sequence[str], args: argparse.Namespace
) -> dict[str, dict[str, Any]]:
    """Every requested arm on one row, in order, serially.

    Serial on purpose: one 16GB GPU cannot hold gemma and a GLiClass checkpoint
    at once, and a latency column measured under contention answers a question
    nobody asked. ``wait_out_schedule`` sits before each Ollama-calling arm
    rather than once per row, because arm C alone can run for minutes.
    """
    arms: dict[str, dict[str, Any]] = {}
    if "A" in wanted:
        for label in ARM_LABELS["A"]:
            wait_out_schedule(args)
            arms[label] = _arm_to_dict(run_free(row, system))
    if "B" in wanted:
        for label in ARM_LABELS["B"]:
            wait_out_schedule(args)
            arms[label] = _arm_to_dict(run_enum(row, system))
        if args.order_shuffle:
            wait_out_schedule(args)
            order = list(row.catalog_names)
            random.Random(args.seed).shuffle(order)
            arms[B_SHUFFLE_LABEL] = _arm_to_dict(run_enum(row, system, catalog_order=order))
    if "C" in wanted:
        wait_out_schedule(args)
        arms[ARM_LABELS["C"][0]] = _arm_to_dict(run_logits(row, system, args))
    if "D" in wanted:
        arms[ARM_LABELS["D"][0]] = _arm_to_dict(run_gliclass(row, args))
    if "E" in wanted:
        arms[ARM_LABELS["E"][0]] = _arm_to_dict(run_ceiling(row, args))
    return arms


def _replay_meta(
    args: argparse.Namespace,
    rows: Sequence[Row],
    sample: Sequence[Row],
    excluded: dict[str, int],
    days_read: Sequence[str],
) -> dict[str, Any]:
    """Everything a later reader needs to know what this run measured."""
    from contemplative_agent.core.llm import _get_model, _get_ollama_url
    from contemplative_agent.core.skill_selection import _SELECTION_NUM_PREDICT

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "args": {
            k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k != "home"
        },
        # Basename only: the summary is published, and the absolute path is the
        # operator's home directory and username.
        "home": args.home.name,
        "window_days_read": list(days_read),
        "rows_replayable": len(rows),
        "rows_sampled": len(sample),
        "excluded": excluded,
        "sample_selection_ids": [row.selection_id for row in sample],
        "sample_catalog_counts": _count(len(row.catalog) for row in sample),
        "sample_days": _count(row.day for row in sample),
        "sample_strata": {
            "logged_hallucination": sum(1 for r in sample if r.had_hallucination),
            "logged_clean": sum(1 for r in sample if not r.had_hallucination),
        },
        "generation_model": _get_model(),
        "ollama_base_url": _get_ollama_url(),
        "num_predict": _SELECTION_NUM_PREDICT,
        "replay_fidelity": {
            "prompt": "byte-identical to the logged prompt (round-trip asserted per row)",
            "system": (
                "rebuilt from today's identity.md via configure_prompting; identity.md is "
                "mutable, so a row logged before the last identity distillation ran under a "
                "different system prompt than this replay uses"
            ),
            "sink": "llm.configure is never called — no telemetry or audit sink is wired",
            "arm_A_path": "core.skill_selection.select_applicable_skills (production's own)",
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wanted = tuple(a.strip().upper() for a in args.arms.split(",") if a.strip())
    unknown = sorted(set(wanted) - set(ARMS))
    if unknown:
        raise SystemExit(f"unknown arm(s): {unknown} (choose from {list(ARMS)})")
    assert_output_paths_safe(args)

    log_dir = args.home / "logs"
    today = datetime.now(timezone.utc).date()
    rows, excluded, days_read = load_rows(log_dir, days=args.days, today=today)
    sample = stratified_sample(rows, n=args.n, seed=args.seed)
    by_id = {row.selection_id: row for row in sample}
    print(
        f"window {days_read[0] if days_read else '-'}..{days_read[-1] if days_read else '-'}: "
        f"{len(rows)} replayable row(s), sampled {len(sample)}, excluded {sum(excluded.values())}",
        flush=True,
    )

    done_records, done_ids, malformed = _load_done(args.out_rows)
    # Rows from a different sample would be summarized under THIS run's
    # ``sample_selection_ids``, so the artifact would name a row set it did not
    # aggregate. Refuse rather than quietly widen the population.
    foreign = sorted({str(r.get("selection_id")) for r in done_records} - set(by_id))
    if foreign:
        raise SystemExit(
            f"{args.out_rows} holds {len(foreign)} row(s) outside this sample "
            f"(first: {foreign[0]}) — the seed/window/n changed; use a different --out-rows"
        )
    if malformed:
        # A dropped line leaves its id out of ``done_ids``, so the row is
        # replayed and lands in the file twice — counted twice by the summary.
        raise SystemExit(
            f"{args.out_rows} has {malformed} unparseable line(s) — resuming would "
            "double-count those rows; truncate the file or start a fresh run"
        )
    if done_records and not (args.resume or args.summarize_only):
        # The row log is opened in append mode, so a second run without
        # ``--resume`` would silently double every row and halve every rate.
        raise SystemExit(
            f"{args.out_rows} already holds {len(done_records)} row(s) — pass --resume to "
            "continue that run, or give a different --out-rows"
        )
    identity_path, constitution_dir = replay_prompt_sources(args.home)
    system, prompt_note = configure_replay_prompting(identity_path, constitution_dir)
    meta = _replay_meta(args, rows, sample, excluded, days_read)
    meta["replay_fidelity"]["system_sources"] = prompt_note
    if args.summarize_only:
        return _finish(done_records, meta, by_id, args)

    args.out_rows.parent.mkdir(parents=True, exist_ok=True)
    handle = args.out_rows.open("a", encoding="utf-8")
    written = list(done_records)
    try:
        for index, row in enumerate(sample, 1):
            if row.selection_id in done_ids:
                continue
            arms = run_row(row, system, wanted, args)
            record = {
                "selection_id": row.selection_id,
                "ts": row.ts,
                "catalog_count": len(row.catalog),
                "logged_selected": list(row.logged_selected),
                "logged_rejected_count": len(row.logged_rejected),
                "arms": arms,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            written.append(record)
            print(
                f"  [{index}/{len(sample)}] {row.selection_id[:8]} "
                + " ".join(
                    f"{label}={'ERR:' + a['reason'] if a.get('reason') else (len(a['selected']) if a.get('selected') is not None else 'scores')}"
                    for label, a in arms.items()
                ),
                flush=True,
            )
    finally:
        handle.close()
    return _finish(written, meta, by_id, args)


def assert_output_paths_safe(args: argparse.Namespace) -> None:
    """Refuse to write into the research store or into the public tree.

    "Read-only with respect to ``$MOLTBOOK_HOME``" and "situations never enter
    ``docs/``" are the two properties this script's docstrings claim, and until
    this check they were prose: every output path is a bare argparse value, so
    one mistyped flag could append beside the append-only episode logs, or put
    other agents' post bodies into the public repo. The repo has the same shape
    of containment check in ``cli/store_paths.py::_target_inside_data_root``.
    """
    home = args.home.expanduser().resolve()
    docs = (_REPO_ROOT / "docs").resolve()
    for flag, path in (
        ("--out-rows", args.out_rows),
        ("--out-summary", args.out_summary),
        ("--adjudication", args.adjudication),
        ("--ceiling-scratch", Path(args.ceiling_scratch)),
    ):
        resolved = Path(path).expanduser().resolve()
        for forbidden, why in ((home, "$MOLTBOOK_HOME is read-only here"), (docs, "public tree")):
            if resolved == forbidden or forbidden in resolved.parents:
                raise SystemExit(f"{flag}={resolved} is inside {forbidden} — {why}")


def _count(values: Iterable[Any]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for value in values:
        tally[str(value)] = tally.get(str(value), 0) + 1
    return dict(sorted(tally.items()))


def _finish(
    records: list[dict[str, Any]],
    meta: dict[str, Any],
    by_id: dict[str, Row],
    args: argparse.Namespace,
) -> int:
    summary = summarize(records, meta)
    assert_no_text_in_summary(summary)
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out_summary}")
    if by_id:
        count = write_adjudication(records, by_id, args.adjudication)
        print(f"wrote {args.adjudication} ({count} disagreeing row(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
