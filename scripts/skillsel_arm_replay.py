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

Round 2 (packet S2, 2026-09-20) adds six arms to the SAME rows via
``--augment``, because round 1 could not tell a bad judgment from a question
with no stable answer, and could not tell sampling jitter from either:

* ``E2`` ``ceiling/rep2`` — the ceiling again. Its agreement with itself is the
  highest score any arm could have got, and nothing in round 1 measured it.
* ``G`` ``rater/sonnet``  — a second frontier rater, same prompt. Together with
  E and E2 it gives a 2-of-3 ``consensus`` label reported beside the raters.
* ``A0`` / ``B0``         — arms A and B at temperature 0, once. The gap to
  their temperature-1 twins is the sampling term, paired per row.
* ``F`` ``logits/onepass``— the whole catalog in one call: each entry gets a
  single-character label and the first token's ``top_logprobs`` ranks them.
  Ollama caps that list at 20, so the reading is TRUNCATED on a 53-57 catalog
  and says so (coverage in the summary, unobserved names tied last in the AUC).
* ``D2`` ``gliclass/desc``— GLiClass with the description alone as the label,
  so "unadjusted GLiClass is at chance" does not rest on one label shape.

Round 2 also stops reading agreement as one number. The summary adds rank
quality (AUC with truncation, precision/recall at two k's), calibration
(reliability bins + ECE), threshold-free neighbour agreement against its own
random floor, the arms' habits (modal skill, top-3 share, catalog position,
pairwise Spearman), a bootstrap 95% interval on every mean, and a
cache-controlled latency sub-sample with Ollama's own counters.

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

    # round 1
    uv run --no-sync python scripts/skillsel_arm_replay.py \\
        --days 21 --n 150 --seed 20260919 --arms A,B,C,D,E \\
        --out-rows .notes/skillsel-arm-replay/rows.jsonl \\
        --out-summary .notes/skillsel-arm-replay/summary.json

    # round 2: the same rows, new arms only, into a NEW file
    uv run --group replay python scripts/skillsel_arm_replay.py \\
        --augment .notes/skillsel-arm-replay/full-20260919/rows.jsonl \\
        --arms E2,G,A0,B0,F,D2,B --order-shuffle2 --latency-subsample 30 \\
        --out-rows .notes/skillsel-arm-replay/round2/rows.jsonl \\
        --out-summary .notes/skillsel-arm-replay/round2/summary.json
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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
# ``evals`` is imported as a package from the repo root: the ceiling arm reuses
# the ONE hardened cloud-egress seam this repo already sanctions
# (``evals/judging.py::run_claude_raw``, named in
# ``tests/test_cloud_egress_absence.py``) rather than opening a second one.
# See ``run_ceiling`` for why that matters.
sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "skillsel-arm-replay/1"

ARMS = ("A", "B", "C", "D", "E", "E2", "G", "A0", "B0", "F", "D2")

# Arm labels as they appear in the row log and the summary. A and B run twice
# (self-agreement is the floor every cross-arm comparison is read against), so
# their labels carry a repetition index.
#
# Round 2 (RFC-0043, 2026-09-20) adds six arms that answer what round 1 could
# not: ``E2``/``G`` measure the ceiling's OWN spread (self-agreement and a
# second rater), so a low arm-vs-ceiling number can be read as "gemma judges
# badly" or "the question has no stable answer"; ``A0``/``B0`` separate
# sampling jitter from judgment by re-running the two set arms at
# temperature 0; ``F`` asks the whole catalog in ONE call instead of arm C's
# per-skill decomposition; ``D2`` gives GLiClass a second formulation so
# "unadjusted GLiClass is at chance" does not rest on one label shape.
ARM_LABELS: dict[str, tuple[str, ...]] = {
    "A": ("A/free/rep1", "A/free/rep2"),
    "B": ("B/enum/rep1", "B/enum/rep2"),
    "C": ("C/logits",),
    "D": ("D/gliclass",),
    "E": ("E/ceiling",),
    "E2": ("E2/ceiling/rep2",),
    "G": ("G/rater/sonnet",),
    "A0": ("A0/free/t0",),
    "B0": ("B0/enum/t0",),
    "F": ("F/logits/onepass",),
    "D2": ("D2/gliclass/desc",),
}

# ``--order-shuffle`` adds one more B repetition with the catalog order
# permuted. Named separately because it is a stability probe, not a third
# sample of the same arm: it answers "does the enum's answer depend on where a
# name sits in the list", which a plain rep cannot.
B_SHUFFLE_LABEL = "B/enum/shuffled"
# Round 2 re-runs the probe under a second label because round 1 did not store
# the permutation it used: without the order, a "the enum follows position"
# reading cannot be checked against where each name actually sat.
B_SHUFFLE2_LABEL = "B/enum/shuffled2"

# The three cloud raters. ``consensus`` (2 of 3) is reported beside each of
# them rather than replacing them — a majority label is one more reading, not
# a truth the individual raters are scored against.
RATER_LABELS = ("E/ceiling", "E2/ceiling/rep2", "G/rater/sonnet")

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
# Arm F: fewer than this many catalog labels were observed in the capped
# ``top_logprobs``, so the reading is not a ranking of the catalog at all.
ARM_LABELS_TOO_FEW = "labels_below_floor"
# Arm F needs one distinct single-character label per catalog entry.
ARM_CATALOG_TOO_BIG = "catalog_exceeds_label_alphabet"
ARM_HTTP_ERROR = "ollama_http_error"
# A scoring arm produced an empty score map. Named rather than published:
# an empty map reaches AUC as an all-ties 0.5 and precision@k as 1.0, which
# is a flattering reading of a silent failure.
ARM_NO_SCORES = "no_scores"

# Ollama 0.30.11 refuses ``top_logprobs`` above 20 with HTTP 400 (measured
# 2026-09-20 against the live daemon; the error text is
# "top_logprobs must be between 0 and 20"). Arm F therefore sees at most 20 of
# the row's 53-57 labels and the rest are truncated, not scored — the number
# is here rather than inline so the summary can say what capped it.
OLLAMA_TOP_LOGPROBS_CAP = 20

# Below this many observed labels, arm F's "ranking" would be over so small a
# slice of the catalog that top-k and AUC say more about the cap than about
# the model. Packet S2's floor.
ARM_F_MIN_OBSERVED_LABELS = 6

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
# Rank, calibration and resampling maths (pure) — round 2
# --------------------------------------------------------------------------

# One distinct single-token surface per catalog entry. Upper case first
# because the model reaches for it first, then lower case, then digits; the
# three classes are recorded per row so "the answer is a position, not a
# judgment" stays checkable. Multi-character labels are NOT usable here: a
# first-token reading of "10" sees "1", which is also label 1.
LABEL_ALPHABET = tuple(
    [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [chr(c) for c in range(ord("a"), ord("z") + 1)]
    + [str(d) for d in range(10)]
)


def label_alphabet(size: int) -> tuple[str, ...]:
    """``size`` distinct single-character labels, or ``()`` when there are not enough.

    An empty return is the caller's signal to record
    ``catalog_exceeds_label_alphabet`` rather than reuse a character — two
    catalog entries sharing a label would silently merge two skills' scores.
    """
    if size > len(LABEL_ALPHABET):
        return ()
    return LABEL_ALPHABET[:size]


def auc_with_truncation(
    scores: dict[str, float], truth: Iterable[str], universe: Iterable[str]
) -> float | None:
    """Row-wise ROC AUC of ``scores`` against ``truth`` over ``universe``.

    Ties score 0.5, which is what makes this usable on a TRUNCATED reading:
    arm F observes at most :data:`OLLAMA_TOP_LOGPROBS_CAP` of the row's labels,
    and every unobserved name is placed at one shared bottom rank rather than
    dropped. Dropping them would score the arm only on the slice it happened to
    surface — flattering exactly the arm whose coverage is worst.

    ``None`` when the row has no positive or no negative (AUC is undefined),
    so the caller counts it rather than averaging a 0.5 that means "no data".
    """
    names = list(dict.fromkeys(universe))
    positives = set(truth) & set(names)
    negatives = [n for n in names if n not in positives]
    if not positives or not negatives:
        return None
    # Unobserved names share one rank below every observed score. ``-inf``
    # would break the tie arithmetic below (inf - inf), so a sentinel one step
    # under the minimum observed score is used instead.
    floor = min(scores.values(), default=0.0) - 1.0
    ranked = {name: scores.get(name, floor) for name in names}
    total = 0.0
    for p in positives:
        for n in negatives:
            if ranked[p] > ranked[n]:
                total += 1.0
            elif ranked[p] == ranked[n]:
                total += 0.5
    return total / (len(positives) * len(negatives))


def precision_recall_at_k(
    scores: dict[str, float], truth: Iterable[str], k: int
) -> tuple[float, float]:
    """Precision and recall of the top ``k`` scored names against ``truth``."""
    return precision_recall(topk_set(scores, k), truth)


def consensus_set(sets: Sequence[Iterable[str]], *, need: int = 2) -> tuple[str, ...]:
    """Names chosen by at least ``need`` of the raters, sorted.

    The rule is per NAME, not per rater's whole set: three raters that each
    pick six skills and overlap on four produce a consensus of four, which is
    the quantity "do the frontier models agree about this skill" asks for.
    """
    tally: dict[str, int] = {}
    for one in sets:
        for name in set(one):
            tally[name] = tally.get(name, 0) + 1
    return tuple(sorted(name for name, count in tally.items() if count >= need))


def reliability_bins(
    observations: Sequence[tuple[float, bool]], *, bins: int = 10
) -> dict[str, Any]:
    """Ten-bin reliability table plus the ECE for a scoring arm.

    ``observations`` is ``(probability, was in the reference set)`` per scored
    name. The table is what says whether "0.9" means anything: arm C's round-1
    reading (89% of scores at or above 0.5) is a distribution claim, and this
    turns it into a calibration claim.
    """
    if bins < 1:
        raise ValueError("bins must be >= 1")
    table: list[dict[str, Any]] = []
    ece = 0.0
    total = len(observations)
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        # The top bin owns its right edge; otherwise p == 1.0 falls out of
        # every bin and the table silently loses the most confident scores.
        inside = [
            (p, hit)
            for p, hit in observations
            if (low <= p < high) or (index == bins - 1 and p == high)
        ]
        row = {
            "bin": f"{low:.1f}-{high:.1f}",
            "n": len(inside),
            "mean_score": round(statistics.fmean(p for p, _ in inside), 4) if inside else None,
            "hit_rate": (
                round(sum(1 for _, hit in inside if hit) / len(inside), 4) if inside else None
            ),
        }
        table.append(row)
        if inside and total:
            ece += (len(inside) / total) * abs(row["mean_score"] - row["hit_rate"])
    return {"n": total, "bins": table, "ece": round(ece, 4) if total else None}


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Spearman rank correlation, ties averaged. ``None`` when undefined."""
    if len(a) != len(b):
        raise ValueError("spearman needs paired sequences")
    if len(a) < 2:
        return None
    ra, rb = _ranks(a), _ranks(b)
    mean_a, mean_b = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in ra))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in rb))
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks (1-based), ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for index in order[i : j + 1]:
            ranks[index] = shared
        i = j + 1
    return ranks


def bootstrap_ci(values: Sequence[float], *, seed: int, iterations: int = 2000) -> dict[str, Any]:
    """Mean with a row-level bootstrap 95% interval. Deterministic in ``seed``.

    Resampling is over ROWS, which is the unit that repeats: a per-skill
    bootstrap would treat 57 scores from one situation as 57 independent
    observations and shrink every interval.
    """
    if not values:
        return {"n": 0, "mean": None, "lo": None, "hi": None, "iterations": iterations}
    rng = random.Random(seed)
    size = len(values)
    means = sorted(
        statistics.fmean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(iterations)
    )
    return {
        "n": size,
        "mean": round(statistics.fmean(values), 4),
        "lo": round(means[int(0.025 * iterations)], 4),
        "hi": round(means[min(int(0.975 * iterations), iterations - 1)], 4),
        "iterations": iterations,
    }


def paired_difference_ci(
    left: Sequence[float], right: Sequence[float], *, seed: int, iterations: int = 2000
) -> dict[str, Any]:
    """Bootstrap CI of the PAIRED difference ``left - right``.

    Two separate intervals that overlap do not mean the difference is not
    there, and two that do not overlap overstate it; every "arm X beats arm Y"
    sentence in the summary is read off this instead.
    """
    if len(left) != len(right):
        raise ValueError("paired_difference_ci needs paired sequences")
    return bootstrap_ci(
        [x - y for x, y in zip(left, right, strict=True)], seed=seed, iterations=iterations
    )


def soft_precision_recall(
    got: Sequence[str],
    truth: Sequence[str],
    vectors: dict[str, Any],
) -> tuple[float | None, float | None]:
    """Nearest-neighbour agreement in embedding space — no threshold.

    ``soft recall`` = for each name the reference picked, the best cosine to
    anything the arm picked, averaged. ``soft precision`` is the same the other
    way. Jaccard scores a neighbouring skill 0; this says how far off it was.
    Names with no vector are skipped, and an empty side returns ``None`` rather
    than a 0.0 that would read as "maximally wrong".
    """
    from contemplative_agent.core.embeddings import cosine

    got_vectors = [vectors[n] for n in set(got) if n in vectors]
    truth_vectors = [vectors[n] for n in set(truth) if n in vectors]
    if not got_vectors or not truth_vectors:
        return None, None
    recall = statistics.fmean(max(cosine(t, g) for g in got_vectors) for t in truth_vectors)
    precision = statistics.fmean(max(cosine(g, t) for t in truth_vectors) for g in got_vectors)
    return precision, recall


def random_k_set(names: Sequence[str], k: int, rng: random.Random) -> tuple[str, ...]:
    """``k`` names drawn without replacement — the chance floor every rate is read against."""
    k = max(0, min(k, len(names)))
    return tuple(sorted(rng.sample(list(names), k)))


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
    # Whatever else this arm measured about its own call: Ollama's counters,
    # the cloud envelope's cost numbers, arm F's label map and truncation flag,
    # the shuffled arm's permutation. Merged into the row entry as-is, so a new
    # arm records what it knows without a new column in every other arm.
    # Numbers and short strings only — this reaches the row log, not stdout.
    meta: dict[str, Any] = field(default_factory=dict)


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
    # Round 1 ran the shuffle probe without storing the permutation, so a
    # "the answer follows position" reading had nothing to check against.
    order_meta = {"enum_order": names} if catalog_order is not None else {}
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
        return ArmOutcome(latency_ms=latency, reason=ARM_LLM_NONE, meta=dict(order_meta))
    outcome = _parse_enum_answer(raw, names, latency)
    outcome.meta.update(order_meta)
    return outcome


def _strip_fence(text: str) -> str:
    """Drop a ```json fence if the model added one around its JSON."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


# --------------------------------------------------------------------------
# Direct Ollama path (round 2) — the counters production's wrapper drops
# --------------------------------------------------------------------------

# Ollama's own per-call counters. ``prompt_eval_count`` is the one that says
# whether the prefix cache was hit: a cached prefix is not re-evaluated, so a
# latency compared across arms without this column is comparing cache states,
# which is exactly what made round 1's latency reading unusable.
OLLAMA_COUNTER_KEYS = (
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
    "load_duration",
    "total_duration",
)


class OllamaCallFailed(RuntimeError):
    """One Ollama call failed in transport. A row outcome, not a stop.

    Narrow on purpose. The arms below used to catch ``Exception``, which also
    swallowed ``validate_trusted_url``'s ``ValueError`` — a misconfigured
    ``OLLAMA_TRUSTED_HOSTS`` would then read as 150 transient timeouts instead
    of stopping the run, and arm C (which lets the guard raise) would have
    behaved differently from arms A0 / B0 / F in the same file. Egress stays
    blocked either way; what this restores is being able to tell a bad host
    from a slow one.
    """


def ollama_counters(data: dict[str, Any]) -> dict[str, Any]:
    """The timing/token counters from one ``/api/generate`` response.

    ``done_reason`` travels with them because a ``length`` stop means the arm's
    answer was cut at ``num_predict`` — a parse failure downstream would
    otherwise look like the model's fault.
    """
    out: dict[str, Any] = {
        key: data.get(key) for key in OLLAMA_COUNTER_KEYS if isinstance(data.get(key), int)
    }
    if isinstance(data.get("done_reason"), str):
        out["done_reason"] = data["done_reason"]
    return out


def ollama_generate(
    base_url: str,
    model: str,
    prompt: str,
    system: str,
    *,
    num_predict: int,
    temperature: float,
    timeout: tuple[int, int],
    format: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """One ``/api/generate`` call, returning ``(raw text, counters)``.

    Production's ``core.llm.generate`` is the right path for a replay and round
    1 used it — but it projects the response to a string, so the cache and
    token counters this round needs never reach the caller. The sampling
    options below are imported from production's own constants rather than
    copied, and the response runs through production's ``_sanitize_output``,
    so this path differs from ``generate`` in exactly two ways it names: the
    counters come back, and no circuit breaker or telemetry sink is touched.
    The URL goes through the production allowlist guard, so this arm cannot
    reach a host the agent itself could not.
    """
    import requests

    from contemplative_agent.core.llm import SAMPLING_TOP_K, SAMPLING_TOP_P, _sanitize_output
    from contemplative_agent.core.llm.backend import NUM_CTX
    from contemplative_agent.core.llm.guard import validate_trusted_url

    url = validate_trusted_url(base_url, source="rfc0043.direct")
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "top_p": SAMPLING_TOP_P,
            "top_k": SAMPLING_TOP_K,
            "num_predict": num_predict,
            "num_ctx": NUM_CTX,
        },
    }
    if format is not None:
        payload["format"] = format
    try:
        response = requests.post(
            f"{url}/api/generate", json=payload, timeout=timeout, allow_redirects=False
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OllamaCallFailed(type(exc).__name__) from exc
    return _sanitize_output(str(data.get("response", "")), None), ollama_counters(data)


def match_catalog_names(raw: str, catalog_names: Sequence[str]) -> tuple[list[str], list[str]]:
    """``(selected, rejected)`` under production's own free-generation rule.

    Mirrors ``skill_selection.select_applicable_skills``'s post-generation
    block: one name per line, matched case-insensitively, the ``none`` sentinel
    dropped, and an unmatched line scrubbed and cut before it is recorded.
    Arm A calls production directly and does not need this; arm A0 does,
    because it goes through :func:`ollama_generate` to get the counters.
    ``tests/test_skillsel_arm_replay.py`` pins the two against each other on
    the same text so this copy cannot drift unnoticed.
    """
    from contemplative_agent.core._io import scrub_control
    from contemplative_agent.core.selection_window import _NAME_MAX_CHARS
    from contemplative_agent.core.skill_selection import _NONE_SENTINEL

    by_lower = {name.lower(): name for name in catalog_names}
    selected: set[str] = set()
    rejected: list[str] = []
    for line in (line.strip() for line in raw.splitlines()):
        if not line or line.lower() == _NONE_SENTINEL:
            continue
        canonical = by_lower.get(line.lower())
        if canonical is None:
            rejected.append(scrub_control(line, _NAME_MAX_CHARS))
        else:
            selected.add(canonical)
    return sorted(selected), rejected


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


def _ollama_endpoint() -> tuple[str, str]:
    """``(base url, generation model)`` as production resolves them."""
    from contemplative_agent.core.llm import _get_model, _get_ollama_url

    return _get_ollama_url(), _get_model()


def run_free_direct(
    row: Row, system: str, args: argparse.Namespace, *, temperature: float
) -> ArmOutcome:
    """Arm A's free generation through the direct path, at a given temperature.

    Two callers, two temperatures. Arm A0 passes 0.0: round 1 measured arm A's
    self-agreement at 0.384 without being able to say how much of the remaining
    0.6 is sampling and how much is the model changing its mind, and a greedy
    decode removes the sampling term (one repetition — a second greedy decode
    of the same prompt is the same answer). The latency sub-sample passes
    :data:`PRODUCTION_TEMPERATURE`, because it needs arm A's real timing WITH
    the cache counters, which production's wrapper does not return.
    """
    from contemplative_agent.core.skill_selection import _SELECTION_NUM_PREDICT

    base_url, model = _ollama_endpoint()
    started = time.monotonic()
    try:
        raw, counters = ollama_generate(
            base_url,
            model,
            row.prompt,
            system,
            num_predict=_SELECTION_NUM_PREDICT,
            temperature=temperature,
            timeout=(30, args.ollama_timeout),
        )
    except OllamaCallFailed as exc:
        return ArmOutcome(
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=ARM_HTTP_ERROR,
            note=str(exc)[:60],
        )
    latency = int((time.monotonic() - started) * 1000)
    if not raw.strip():
        return ArmOutcome(latency_ms=latency, reason=ARM_LLM_NONE, meta={"ollama": counters})
    selected, rejected = match_catalog_names(raw, row.catalog_names)
    return ArmOutcome(
        selected=tuple(selected),
        rejected=tuple(rejected),
        latency_ms=latency,
        meta={"ollama": counters},
    )


def run_enum_direct(
    row: Row, system: str, args: argparse.Namespace, *, temperature: float
) -> ArmOutcome:
    """Arm B's constrained generation through the direct path, at a given temperature."""
    from contemplative_agent.core.skill_selection import _SELECTION_NUM_PREDICT

    base_url, model = _ollama_endpoint()
    names = list(row.catalog_names)
    started = time.monotonic()
    try:
        raw, counters = ollama_generate(
            base_url,
            model,
            row.prompt,
            system,
            num_predict=_SELECTION_NUM_PREDICT,
            temperature=temperature,
            timeout=(30, args.ollama_timeout),
            format=enum_schema(names),
        )
    except OllamaCallFailed as exc:
        return ArmOutcome(
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=ARM_HTTP_ERROR,
            note=str(exc)[:60],
        )
    latency = int((time.monotonic() - started) * 1000)
    outcome = _parse_enum_answer(raw, names, latency)
    outcome.meta["ollama"] = counters
    return outcome


def _parse_enum_answer(raw: str, names: Sequence[str], latency: int) -> ArmOutcome:
    """Shared by the two enum arms: parse, then assert the enum held.

    A name outside the catalog here would mean the backend did not honour
    ``format=``, which is a finding about the backend rather than a
    hallucination rate — so it stops the run rather than being counted.
    """
    if not raw.strip():
        return ArmOutcome(latency_ms=latency, reason=ARM_LLM_NONE)
    try:
        data = json.loads(_strip_fence(raw))
        picked = data["selected"]
        if not isinstance(picked, list):
            raise TypeError("selected is not a list")
        selected = tuple(str(name) for name in picked)
    except (json.JSONDecodeError, KeyError, TypeError):
        return ArmOutcome(latency_ms=latency, reason=ARM_PARSE)
    outside = sorted(set(selected) - set(names))
    assert not outside, f"enum arm returned non-catalog names: {outside}"
    return ArmOutcome(selected=tuple(sorted(set(selected))), latency_ms=latency)


_ONEPASS_PROMPT = (
    "## Skills\n\nEach line is `label<TAB>name — description`.\n\n"
    "{catalog}\n\n"
    "## Situation\n\n{situation}\n\n"
    "## Instructions\n\n"
    "Reply with exactly one character: the label of the single skill that "
    "applies most to the situation. No other text."
)


def run_logits_onepass(row: Row, system: str, args: argparse.Namespace) -> ArmOutcome:
    """Arm F: the whole catalog in ONE call, read from the first token.

    This is the form arm C's per-skill decomposition abandoned. Arm C asks 57
    independent yes/no questions, which is 57 calls per row and — round 1's
    reading — degenerates to yes (89% of scores at or above 0.5) because a
    single skill in isolation has nothing to be compared against. Here the
    labels compete inside one distribution, so a skill can only score high by
    outranking the others.

    **What the cap does to the reading.** Ollama 0.30.11 refuses
    ``top_logprobs`` above :data:`OLLAMA_TOP_LOGPROBS_CAP` (measured
    2026-09-20), so at most 20 of the row's 53-57 labels are observed. The
    unobserved ones are NOT dropped: ``truncated`` and ``scored_of`` travel
    with the row, the summary publishes the coverage, and
    :func:`auc_with_truncation` puts every unobserved name at one shared
    bottom rank. Below :data:`ARM_F_MIN_OBSERVED_LABELS` observed labels the
    arm abstains with a reason code instead of publishing a ranking of a
    handful of names.

    Scores are a softmax over the observed LABEL tokens only — the
    alternatives that are not labels (the model's prose openings) are dropped
    first, so the probabilities are "among the answers that are labels", not
    "among everything the model might say".
    """
    labels = label_alphabet(len(row.catalog))
    if not labels:
        return ArmOutcome(
            reason=ARM_CATALOG_TOO_BIG,
            note=f"{len(row.catalog)} entries > {len(LABEL_ALPHABET)} single-token labels",
        )
    catalog_block = "\n".join(
        f"{label}\t{name}{_CATALOG_SEP}{description}"
        for label, (name, description) in zip(labels, row.catalog, strict=True)
    )
    prompt = _ONEPASS_PROMPT.format(catalog=catalog_block, situation=row.situation)
    base_url, model = _ollama_endpoint()
    started = time.monotonic()
    try:
        alternatives, counters = ollama_first_token_logprobs(
            base_url, model, prompt, system, timeout=(30, args.ollama_timeout)
        )
    except OllamaCallFailed as exc:
        return ArmOutcome(
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=ARM_HTTP_ERROR,
            note=str(exc)[:60],
        )
    latency = int((time.monotonic() - started) * 1000)
    by_label = dict(zip(labels, row.catalog_names, strict=True))
    # Case-sensitive on purpose: "A" and "a" are two different labels here, so
    # the lower-casing arm C does on yes/no surfaces would merge two skills.
    observed: dict[str, float] = {}
    for alternative in alternatives:
        token = str(alternative.get("token", "")).strip()
        logprob = alternative.get("logprob")
        name = by_label.get(token)
        if name is None or not isinstance(logprob, (int, float)):
            continue
        # First occurrence wins: the list is ordered by probability.
        observed.setdefault(name, float(logprob))
    meta: dict[str, Any] = {
        "ollama": counters,
        "top_logprobs_requested": OLLAMA_TOP_LOGPROBS_CAP,
        "alternatives_returned": len(alternatives),
        "labels_observed": len(observed),
        "truncated": len(observed) < len(row.catalog),
        "label_classes": _label_class_tally(labels[: len(row.catalog)], observed, by_label),
    }
    if len(observed) < ARM_F_MIN_OBSERVED_LABELS:
        return ArmOutcome(latency_ms=latency, reason=ARM_LABELS_TOO_FEW, meta=meta)
    top = max(observed.values())
    weights = {name: math.exp(lp - top) for name, lp in observed.items()}
    total = sum(weights.values())
    scores = {name: weight / total for name, weight in weights.items()}
    return ArmOutcome(
        scores=scores,
        latency_ms=latency,
        scored_of=(len(scores), len(row.catalog)),
        meta=meta,
    )


def _label_class_tally(
    labels: Sequence[str], observed: dict[str, float], by_label: dict[str, str]
) -> dict[str, int]:
    """How many observed labels were upper case, lower case or a digit.

    The alphabet is ordered, so a model that only ever surfaces upper-case
    letters is answering with a POSITION in the catalog rather than a
    judgment — and that is invisible in the scores alone.
    """
    classes = {"upper": 0, "lower": 0, "digit": 0}
    for label in labels:
        name = by_label.get(label)
        if name is None or name not in observed:
            continue
        if label.isdigit():
            classes["digit"] += 1
        elif label.isupper():
            classes["upper"] += 1
        else:
            classes["lower"] += 1
    return classes


def ollama_first_token_logprobs(
    base_url: str, model: str, prompt: str, system: str, *, timeout: tuple[int, int]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The first generated token's ``top_logprobs``, plus the call counters.

    Same allowlisted URL guard as :func:`ollama_yes_no`; the sampled token is
    discarded here too — only the distribution is read.
    """
    import requests

    from contemplative_agent.core.llm.guard import validate_trusted_url

    url = validate_trusted_url(base_url, source="rfc0043.onepass")
    from contemplative_agent.core.llm.backend import NUM_CTX

    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 1, "num_ctx": NUM_CTX},
        "logprobs": True,
        "top_logprobs": OLLAMA_TOP_LOGPROBS_CAP,
    }
    try:
        response = requests.post(
            f"{url}/api/generate", json=payload, timeout=timeout, allow_redirects=False
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OllamaCallFailed(type(exc).__name__) from exc
    entries = data.get("logprobs") or []
    if not entries:
        return [], ollama_counters(data)
    return list(entries[0].get("top_logprobs") or [entries[0]]), ollama_counters(data)


def _gliclass_labels(row: Row, label_mode: str) -> tuple[list[str], dict[str, str]]:
    """``(labels, label -> catalog name)`` for one GLiClass formulation.

    ``name_desc`` is arm D's ``name — description``. ``desc`` is arm D2: the
    description alone, which removes the skill's own name from the text being
    matched. Round 1's "unadjusted GLiClass is at chance" rests on one
    formulation, and the names are terse slugs — so the second reading exists
    to keep that conclusion from being a property of the label shape.

    Entries whose label would be empty or would collide with another entry's
    are dropped rather than merged: two catalog names behind one label would
    silently sum two skills' scores. The drop is visible in ``scored_of``.
    """
    seen: dict[str, str] = {}
    labels: list[str] = []
    for name, description in row.catalog:
        label = description if label_mode == "desc" else f"{name}{_CATALOG_SEP}{description}"
        label = label.strip()
        if not label or label in seen:
            continue
        seen[label] = name
        labels.append(label)
    return labels, seen


def run_gliclass(
    row: Row, args: argparse.Namespace, *, label_mode: str = "name_desc"
) -> ArmOutcome:
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

    labels, by_label = _gliclass_labels(row, label_mode)
    if not labels:
        return ArmOutcome(reason=ARM_PARSE, note=f"no usable {label_mode} labels in this catalog")
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
            name = by_label.get(str(entry["label"]).strip())
            if name is None:
                continue
            scores[name] = float(entry["score"])
    latency = int((time.monotonic() - started) * 1000)
    if not scores:
        # The same abstention arms C and F make. Without it an empty map is
        # written with no ``scores`` key at all, so the row reads downstream as
        # a SET arm that correctly said "none" — and the rank section scores it
        # 0.5 AUC and 1.0 precision@k for having answered nothing.
        return ArmOutcome(
            latency_ms=latency,
            reason=ARM_NO_SCORES,
            scored_of=(0, len(row.catalog)),
            meta={"label_mode": label_mode, "labels_built": len(labels)},
        )
    return ArmOutcome(
        scores=scores,
        latency_ms=latency,
        scored_of=(len(scores), len(row.catalog)),
        note=f"checkpoint load {load_ms} ms (once per process)" if load_ms else "",
        meta={"label_mode": label_mode, "labels_built": len(labels)},
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


def run_ceiling(row: Row, args: argparse.Namespace, *, model: str | None = None) -> ArmOutcome:
    """Arm E / E2 / G: a cloud rater with no tools, as a proxy for the right answer.

    ``model`` selects the rater: ``--ceiling-model`` (arm E and its second
    repetition E2) or ``--rater-model`` (arm G). E2 exists because round 1
    could not say whether a 0.15 agreement means gemma judges badly or the
    question has no stable answer — the ceiling's agreement with ITSELF is the
    highest any arm could reach. G answers the other half: whether that ceiling
    is one model's taste or something two frontier models share.

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
    envelope_numbers: dict[str, object] = {}
    try:
        raw = run_claude_raw(
            prompt,
            model=model or args.ceiling_model,
            scratch_dir=Path(args.ceiling_scratch),
            timeout=args.ceiling_timeout,
            meta_out=envelope_numbers,
        )
    except JudgeError as exc:
        return ArmOutcome(
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=ARM_CEILING_ERROR,
            note=type(exc).__name__,
        )
    latency = int((time.monotonic() - started) * 1000)
    meta: dict[str, Any] = {"model": model or args.ceiling_model, "cost": dict(envelope_numbers)}
    try:
        picked = json.loads(_strip_fence(raw))
        if not isinstance(picked, list):
            raise TypeError("not a list")
    except (json.JSONDecodeError, TypeError):
        return ArmOutcome(latency_ms=latency, reason=ARM_PARSE, meta=meta)
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
        meta=meta,
    )


# --------------------------------------------------------------------------
# Resource snapshots (round 2)
# --------------------------------------------------------------------------


def ollama_loaded_models(
    base_url: str, *, timeout: tuple[int, int] = (5, 30)
) -> list[dict[str, Any]]:
    """What Ollama currently holds resident: name, bytes, and GPU share.

    ``/api/ps`` rather than the ``ollama ps`` CLI: this script is pinned by
    ``TestCloudEgressStaysInOneSeam`` to spawn no process of its own, and the
    HTTP endpoint carries the same two numbers the CLI's SIZE and PROCESSOR
    columns are rendered from. The derived percentage is recorded beside the
    raw bytes rather than instead of them.
    """
    import requests

    from contemplative_agent.core.llm.guard import validate_trusted_url

    url = validate_trusted_url(base_url, source="rfc0043.ps")
    response = requests.get(f"{url}/api/ps", timeout=timeout, allow_redirects=False)
    response.raise_for_status()
    out: list[dict[str, Any]] = []
    for model in response.json().get("models") or []:
        size = model.get("size")
        vram = model.get("size_vram")
        entry: dict[str, Any] = {"name": str(model.get("name", ""))[:120]}
        if isinstance(size, int):
            entry["size_bytes"] = size
        if isinstance(vram, int):
            entry["size_vram_bytes"] = vram
        if isinstance(size, int) and isinstance(vram, int) and size > 0:
            entry["gpu_percent"] = round(100 * vram / size, 1)
        out.append(entry)
    return out


def resource_snapshot(tag: str) -> dict[str, Any]:
    """One point reading of what this machine is holding, at an arm switch.

    Three sources, each named so a missing one is visible rather than absent:
    Ollama's resident models, the MPS allocator (only meaningful once a torch
    arm has loaded), and this process's own peak RSS. GPU UTILISATION is not
    here and is not measurable without ``sudo powermetrics`` — the summary says
    so under ``not_measured`` rather than leaving a reader to assume it was
    checked.
    """
    import resource as _resource

    snapshot: dict[str, Any] = {
        "tag": tag,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # macOS reports ru_maxrss in bytes (Linux in kibibytes); the unit is in
        # the key so a cross-platform reader is not left guessing.
        "process_max_rss_bytes_or_kib": _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss,
    }
    try:
        base_url, _ = _ollama_endpoint()
        snapshot["ollama_models"] = ollama_loaded_models(base_url)
    except Exception as exc:  # noqa: BLE001 — an instrument must not stop the run
        snapshot["ollama_models_error"] = type(exc).__name__
    torch = sys.modules.get("torch")
    if torch is not None and hasattr(torch, "mps"):
        try:
            snapshot["mps_driver_allocated_bytes"] = int(torch.mps.driver_allocated_memory())
            snapshot["mps_current_allocated_bytes"] = int(torch.mps.current_allocated_memory())
        except Exception as exc:  # noqa: BLE001
            snapshot["mps_error"] = type(exc).__name__
    else:
        snapshot["mps"] = "torch not loaded in this process"
    return snapshot


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
        "augment",
        "direct_ollama_arms",
        "topk",
        "half",
        "order",
        "rule",
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
        # any(), not ok[0]: one row with empty scores must not reclassify the arm.
        "scored_arm": any(e.get("scores") for e in ok),
        # ``ok``, not ``entries``: a failure that never made a call carries
        # latency 0 (gliclass_not_installed, catalog_exceeds_label_alphabet),
        # and averaging those in drags the published median toward zero with
        # nothing in this block saying which rows contributed.
        "latency_ms": _spread([float(e.get("latency_ms", 0)) for e in ok]),
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


def _selected_of(entry: dict[str, Any]) -> tuple[str, ...] | None:
    """One arm's asserted set on one row, or ``None`` when it has none."""
    if entry.get("reason"):
        return None
    selected = entry.get("selected")
    return tuple(selected) if selected is not None else None


def _rater_agreement(rows: list[dict[str, Any]], *, seed: int, iterations: int) -> dict[str, Any]:
    """How much the cloud raters agree with each other — the real ceiling.

    Round 1 compared every local arm against ONE opus-5 pass and read 0.14-0.16
    as the local arms' number. It is only their number if the reference agrees
    with itself; E-vs-E2 says how high any arm could have scored, and E-vs-G
    says whether that reference is one model's taste.
    """
    out: dict[str, Any] = {}
    for left, right in ((0, 1), (0, 2), (1, 2)):
        a, b = RATER_LABELS[left], RATER_LABELS[right]
        values = [
            jaccard(sa, sb)
            for row in rows
            for sa, sb in [
                (_selected_of(row["arms"].get(a, {})), _selected_of(row["arms"].get(b, {})))
            ]
            if a in row.get("arms", {})
            and b in row.get("arms", {})
            and sa is not None
            and sb is not None
        ]
        if values:
            out[f"{a} vs {b}"] = {
                "jaccard": _spread(values),
                "ci95": bootstrap_ci(values, seed=seed, iterations=iterations),
            }
    return out


def _consensus_rows(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """``selection_id -> consensus set`` for rows where all three raters answered.

    All three or nothing: a "2 of 3" computed over two raters is a 2-of-2
    unanimity rule wearing the same name.
    """
    out: dict[str, tuple[str, ...]] = {}
    for row in rows:
        arms = row.get("arms", {})
        sets = [_selected_of(arms.get(label, {})) for label in RATER_LABELS]
        if any(s is None for s in sets) or not all(label in arms for label in RATER_LABELS):
            continue
        out[str(row.get("selection_id"))] = consensus_set([s for s in sets if s is not None])
    return out


def _collapsed_set(
    row: dict[str, Any], entry: dict[str, Any] | None, rule: str
) -> tuple[tuple[str, ...] | None, bool]:
    """``(the arm's set on this row, dropped for a missing k)``.

    A scoring arm has no set of its own, so the top-k rule borrows k from the
    same row's ``A/free/rep1``. When THAT arm failed on the row there is no k,
    and ``k = 0`` would credit the scoring arm with having selected nothing —
    an agreement number that is a property of the missing reference, not of the
    arm. ``_ceiling_pairs`` has refused this since round 1 and publishes the
    count; this is the same rule for the sections that grew around it.
    """
    if entry is None or entry.get("reason"):
        return None, False
    free = _set_for(row.get("arms", {}).get(ARM_LABELS["A"][0], {}), "topk", 0)
    if entry.get("scores") and rule == "topk" and free is None:
        return None, True
    return _set_for(entry, rule, len(free or ())), False


def _versus_reference(
    rows: list[dict[str, Any]],
    labels: Sequence[str],
    by_label: dict[str, Any],
    reference: dict[str, tuple[str, ...]],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Every arm's set agreement against an arbitrary per-row reference set.

    The three raters are NOT scored here. They are the reference's own voters:
    a rater's pick joins the consensus as soon as one of the other two agrees,
    so its agreement with the consensus is inflated by construction and would
    sit in the same table as the local arms as if the two were comparable. How
    much the raters agree is ``rater_agreement``, which compares them pairwise
    and owes nothing to the majority rule.
    """
    out: dict[str, Any] = {}
    for label in labels:
        if label in RATER_LABELS:
            continue
        scored = by_label[label]["scored_arm"]
        for rule in ("topk", "half") if scored else ("topk",):
            values: list[float] = []
            dropped = 0
            for row in rows:
                truth = reference.get(str(row.get("selection_id")))
                if truth is None:
                    continue
                got, no_k = _collapsed_set(row, row.get("arms", {}).get(label), rule)
                dropped += no_k
                if got is None:
                    continue
                values.append(jaccard(got, truth))
            if values:
                key = f"{label}@{rule}" if scored else label
                out[key] = {
                    "rows": len(values),
                    "rows_dropped_no_k": dropped,
                    "jaccard": _spread(values),
                    "ci95": bootstrap_ci(values, seed=seed, iterations=iterations),
                }
    return out


@dataclass(frozen=True)
class _RankCells:
    """One scoring arm's per-row rank measurements, before aggregation."""

    aucs: list[float]
    coverage: list[float]
    at_k: dict[str, dict[str, list[float]]]
    rows_auc_undefined: int
    rows_reference_empty: int


def _one_arm_ranking(rows: list[dict[str, Any]], label: str) -> _RankCells:
    """Raw per-row rank measurements for one scoring arm, before aggregation."""
    free_label = ARM_LABELS["A"][0]
    aucs: list[float] = []
    coverage: list[float] = []
    at_k: dict[str, dict[str, list[float]]] = {
        "k=ceiling": {"precision": [], "recall": []},
        "k=free": {"precision": [], "recall": []},
    }
    undefined = 0
    # Rows where the ceiling chose nothing. ``precision_recall``'s convention
    # gives an empty prediction against an empty truth (1.0, 1.0) — right for a
    # set arm that also said "none", but at k = 0 EVERY scoring arm collects
    # that 1.0 for free. Counted so the at-k means can be read with the free
    # rows in view (round 1 had 3 such rows of 150).
    reference_empty = 0
    for row in rows:
        entry = row.get("arms", {}).get(label)
        truth = _selected_of(row.get("arms", {}).get(CEILING_LABEL, {}))
        if entry is None or entry.get("reason") or truth is None:
            continue
        scores = entry.get("scores") or {}
        universe = row.get("catalog_order") or sorted(set(scores) | set(truth))
        value = auc_with_truncation(scores, truth, universe)
        if value is None:
            undefined += 1
        else:
            aucs.append(value)
        if not truth:
            reference_empty += 1
        scored_of = entry.get("scored_of")
        if scored_of and scored_of[1]:
            coverage.append(scored_of[0] / scored_of[1])
        free = _selected_of(row.get("arms", {}).get(free_label, {}))
        ks = (("k=ceiling", len(truth)), ("k=free", len(free) if free is not None else None))
        for key, k in ks:
            if k is None:
                continue
            precision, recall = precision_recall_at_k(scores, truth, k)
            at_k[key]["precision"].append(precision)
            at_k[key]["recall"].append(recall)
    return _RankCells(
        aucs=aucs,
        coverage=coverage,
        at_k=at_k,
        rows_auc_undefined=undefined,
        rows_reference_empty=reference_empty,
    )


def _ranking_readings(
    rows: list[dict[str, Any]],
    labels: Sequence[str],
    by_label: dict[str, Any],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Rank-level readings for the scoring arms: AUC and precision/recall at k.

    Set agreement collapses a ranking before it is scored, and that threw away
    the only axis on which round 1's arms differed at all. AUC uses every
    scored name and carries the truncated arms honestly
    (:func:`auc_with_truncation`); the two k's are the two defensible sizes —
    what the ceiling picked, and what the production arm picked.
    """
    out: dict[str, Any] = {}
    for label in labels:
        if not by_label[label]["scored_arm"]:
            continue
        cells = _one_arm_ranking(rows, label)
        if not cells.aucs and not cells.coverage:
            continue
        out[label] = {
            "auc": _spread(cells.aucs),
            "auc_ci95": bootstrap_ci(cells.aucs, seed=seed, iterations=iterations),
            "rows_auc_undefined": cells.rows_auc_undefined,
            "rows_reference_empty": cells.rows_reference_empty,
            "catalog_coverage": _spread(cells.coverage),
            "at_k": {
                key: {
                    "precision": _spread(pair["precision"]),
                    "recall": _spread(pair["recall"]),
                }
                for key, pair in cells.at_k.items()
                if pair["precision"]
            },
        }
    return out


def _calibration(
    rows: list[dict[str, Any]], labels: Sequence[str], by_label: dict[str, Any]
) -> dict[str, Any]:
    """Reliability table and ECE per scoring arm, against the ceiling's set."""
    out: dict[str, Any] = {}
    for label in labels:
        if not by_label[label]["scored_arm"]:
            continue
        observations: list[tuple[float, bool]] = []
        for row in rows:
            entry = row.get("arms", {}).get(label)
            truth = _selected_of(row.get("arms", {}).get(CEILING_LABEL, {}))
            if entry is None or entry.get("reason") or truth is None:
                continue
            for name, score in (entry.get("scores") or {}).items():
                observations.append((float(score), name in truth))
        if observations:
            out[label] = reliability_bins(observations)
    return out


def _quirk_readings(
    rows: list[dict[str, Any]],
    labels: Sequence[str],
    catalogs: dict[str, Sequence[str]] | None,
) -> dict[str, Any]:
    """Is an arm answering the situation, or answering out of habit?

    Round 1's sharpest finding was that one arm picked the same skill in 107 of
    150 rows. These are the four shapes that finding has: how often the modal
    skill wins, how much of the mass the top three take, how many distinct
    skills the arm ever picks, and where in the catalog the picks sit.
    """
    per_arm: dict[str, Any] = {}
    frequency: dict[str, dict[str, int]] = {}
    for label in labels:
        counts: dict[str, int] = {}
        positions: list[int] = []
        rows_with_a_set = 0
        dropped = 0
        for row in rows:
            picked, no_k = _collapsed_set(row, row.get("arms", {}).get(label), "topk")
            dropped += no_k
            if picked is None:
                continue
            rows_with_a_set += 1
            order = list((catalogs or {}).get(str(row.get("selection_id")), ()))
            for name in picked:
                counts[name] = counts.get(name, 0) + 1
                if name in order:
                    positions.append(order.index(name))
        if not counts:
            continue
        frequency[label] = counts
        total = sum(counts.values())
        ranked = sorted(counts.values(), reverse=True)
        per_arm[label] = {
            "rows_with_a_set": rows_with_a_set,
            "rows_dropped_no_k": dropped,
            "distinct_skills": len(counts),
            "modal_skill_rows": ranked[0],
            "modal_skill_row_rate": round(ranked[0] / rows_with_a_set, 4)
            if rows_with_a_set
            else None,
            "top3_share_of_all_picks": round(sum(ranked[:3]) / total, 4) if total else None,
            "catalog_position": _spread([float(p) for p in positions]),
        }
    return {"per_arm": per_arm, "frequency_spearman": _frequency_spearman(frequency)}


def _frequency_spearman(frequency: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Rank correlation of how often each arm picks each skill, pairwise."""
    out: dict[str, Any] = {}
    labels = sorted(frequency)
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            names = sorted(set(frequency[left]) | set(frequency[right]))
            if len(names) < 2:
                continue
            value = spearman(
                [float(frequency[left].get(n, 0)) for n in names],
                [float(frequency[right].get(n, 0)) for n in names],
            )
            if value is not None:
                out[f"{left} vs {right}"] = round(value, 4)
    return out


def _soft_agreement(
    rows: list[dict[str, Any]],
    labels: Sequence[str],
    catalog_text: dict[str, str],
    vectors: dict[str, Any],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Threshold-free neighbour agreement, with a random-k floor in the same units.

    Jaccard gives a neighbouring skill the same 0 as an unrelated one, which on
    a catalog with skill families understates every arm equally but by an
    unknown amount. The floor is computed by the same formula on random sets,
    so "0.72" can be read against "random also scores 0.66" rather than against
    intuition.
    """
    out: dict[str, Any] = {}
    rng = random.Random(seed)
    floor_precision: list[float] = []
    floor_recall: list[float] = []
    for label in labels:
        precisions: list[float] = []
        recalls: list[float] = []
        dropped = 0
        for row in rows:
            truth = _selected_of(row.get("arms", {}).get(CEILING_LABEL, {}))
            if truth is None:
                continue
            got, no_k = _collapsed_set(row, row.get("arms", {}).get(label), "topk")
            dropped += no_k
            if got is None:
                continue
            precision, recall = soft_precision_recall(got, truth, vectors)
            if precision is None or recall is None:
                continue
            precisions.append(precision)
            recalls.append(recall)
            if label == CEILING_LABEL:
                continue
            names = list((catalog_text or {}).keys())
            fp, fr = soft_precision_recall(random_k_set(names, len(got), rng), truth, vectors)
            if fp is not None and fr is not None:
                floor_precision.append(fp)
                floor_recall.append(fr)
        if precisions:
            out[label] = {
                "rows": len(precisions),
                "rows_dropped_no_k": dropped,
                "soft_precision": _spread(precisions),
                "soft_precision_ci95": bootstrap_ci(precisions, seed=seed, iterations=iterations),
                "soft_recall": _spread(recalls),
                "soft_recall_ci95": bootstrap_ci(recalls, seed=seed, iterations=iterations),
            }
    if floor_precision:
        out["random_k_floor"] = {
            "soft_precision": _spread(floor_precision),
            "soft_recall": _spread(floor_recall),
            "note": "random sets of the same size, same formula, pooled over arms",
        }
    return out


def summarize(
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    seed: int = 20260919,
    iterations: int = 2000,
    catalogs: dict[str, Sequence[str]] | None = None,
    catalog_text: dict[str, str] | None = None,
    vectors: dict[str, Any] | None = None,
    aux: Sequence[dict[str, Any]] = (),
    production_latency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn the row log into the pre-registered readings.

    Every rate carries its denominator. A scoring arm gets BOTH collapsing
    rules reported side by side; a set arm gets the one set it asserted.
    Nothing is reduced to a single scalar (RFC-0043), and round 2 adds the
    axes round 1 could not read: the raters' agreement with each other, rank
    quality (AUC, precision/recall at two k's), calibration, threshold-free
    neighbour agreement against its own random floor, the arms' habits, and a
    bootstrap interval on every mean.
    """
    labels = sorted({label for row in rows for label in row.get("arms", {})})
    by_label = {
        label: _arm_reading([r["arms"][label] for r in rows if label in r.get("arms", {})])
        for label in labels
    }
    non_ceiling = [label for label in labels if label != CEILING_LABEL]

    versus_ceiling: dict[str, Any] = {}
    per_skill: dict[str, dict[str, dict[str, Any]]] = {}
    for label in non_ceiling:
        scored = by_label[label]["scored_arm"]
        for rule in ("topk", "half") if scored else ("topk",):
            pairs, dropped = _ceiling_pairs(rows, label, rule)
            if not pairs:
                continue
            key = f"{label}@{rule}" if scored else label
            jaccards = [jaccard(g, t) for g, t in pairs]
            versus_ceiling[key] = {
                "rows": len(pairs),
                "rows_dropped_no_k": dropped,
                "jaccard": _spread(jaccards),
                "jaccard_ci95": bootstrap_ci(jaccards, seed=seed, iterations=iterations),
                "precision": _spread([precision_recall(g, t)[0] for g, t in pairs]),
                "recall": _spread([precision_recall(g, t)[1] for g, t in pairs]),
            }
            per_skill[key] = _per_skill_cells(pairs)

    consensus = _consensus_rows(rows)
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        **meta,
        "arms": by_label,
        "self_agreement_jaccard": _self_agreement(rows),
        "versus_ceiling": versus_ceiling,
        "per_skill_versus_ceiling": per_skill,
        "rater_agreement": _rater_agreement(rows, seed=seed, iterations=iterations),
        "consensus": {
            "rule": "a skill chosen by at least 2 of E / E2 / G",
            "rows": len(consensus),
            "set_size": _spread([float(len(s)) for s in consensus.values()]),
            "versus_consensus": _versus_reference(
                rows, labels, by_label, consensus, seed=seed, iterations=iterations
            ),
        },
        "ranking": _ranking_readings(rows, labels, by_label, seed=seed, iterations=iterations),
        "calibration": _calibration(rows, labels, by_label),
        "quirks": _quirk_readings(rows, labels, catalogs),
        "paired_differences": _paired_differences(rows, seed=seed, iterations=iterations),
        "collapse_rules": {
            "topk": "k = the same row's A/free/rep1 selection size",
            "half": "score >= 0.5",
            "note": "reported for scoring arms only; set arms have one set",
        },
        "not_measured": [
            "GPU utilisation (powermetrics needs sudo; only resident bytes are read)",
            "human labels (RFC-0043: the reference is a model consensus, not ground truth)",
        ],
    }
    if vectors and catalog_text:
        summary["soft_agreement"] = _soft_agreement(
            rows, labels, catalog_text, vectors, seed=seed, iterations=iterations
        )
    else:
        summary["soft_agreement"] = {"reason": "no embeddings available for this summary"}
    summary["resources"] = [a for a in aux if a.get("kind") == "resource"]
    summary["latency_subsample"] = _latency_readings(
        [a for a in aux if a.get("kind") == "latency"], production_latency
    )
    return summary


def _paired_differences(
    rows: list[dict[str, Any]], *, seed: int, iterations: int
) -> dict[str, Any]:
    """Bootstrap CIs on the PAIRED gaps this round exists to size.

    Each entry answers one sentence someone will want to write: the sampling
    term (A vs A0), what the enum changes (A vs B), and the headroom the
    ceiling's own spread leaves (E-vs-E2 against A-vs-E).
    """
    named = {
        "A/free/rep1 - A0/free/t0 (sampling term)": (ARM_LABELS["A"][0], ARM_LABELS["A0"][0]),
        "B/enum/rep1 - B0/enum/t0 (sampling term, constrained)": (
            ARM_LABELS["B"][0],
            ARM_LABELS["B0"][0],
        ),
        "A/free/rep1 - B/enum/rep1 (what the enum changes)": (
            ARM_LABELS["A"][0],
            ARM_LABELS["B"][0],
        ),
    }
    out: dict[str, Any] = {}
    for title, (left, right) in named.items():
        values_left: list[float] = []
        values_right: list[float] = []
        for row in rows:
            arms = row.get("arms", {})
            truth = _selected_of(arms.get(CEILING_LABEL, {}))
            a, b = _selected_of(arms.get(left, {})), _selected_of(arms.get(right, {}))
            if truth is None or a is None or b is None:
                continue
            values_left.append(jaccard(a, truth))
            values_right.append(jaccard(b, truth))
        if values_left:
            out[title] = paired_difference_ci(
                values_left, values_right, seed=seed, iterations=iterations
            )
    return out


def _latency_readings(
    records: Sequence[dict[str, Any]], production: dict[str, Any] | None
) -> dict[str, Any]:
    """The cache-controlled latency sub-sample, with production beside it.

    Round 1's latency column compared a cold arm against a warm one and could
    not say so. Here the sub-sample is run arm-major, so consecutive calls of
    one arm are on DIFFERENT prompts, and ``prompt_eval_count`` travels with
    each call — the number that says whether the prefix cache was hit.
    """
    by_arm: dict[str, dict[str, Any]] = {}
    for label in sorted({str(r.get("arm")) for r in records}):
        mine = [r for r in records if str(r.get("arm")) == label]
        by_arm[label] = {
            "calls": len(mine),
            "latency_ms": _spread([float(r.get("latency_ms", 0)) for r in mine]),
            "prompt_eval_count": _spread(
                [
                    float(r["ollama"]["prompt_eval_count"])
                    for r in mine
                    if r.get("ollama", {}).get("prompt_eval_count") is not None
                ]
            ),
            "eval_count": _spread(
                [
                    float(r["ollama"]["eval_count"])
                    for r in mine
                    if r.get("ollama", {}).get("eval_count") is not None
                ]
            ),
            "total_duration_ms": _spread(
                [
                    r["ollama"]["total_duration"] / 1e6
                    for r in mine
                    if r.get("ollama", {}).get("total_duration") is not None
                ]
            ),
        }
    return {
        "order": "arm-major (every consecutive call of one arm is a different row)",
        "arms": by_arm,
        "production_reference": production
        or {"reason": "no llm-calls telemetry found for core.skill_selection in this window"},
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
    payload.update(outcome.meta)
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
    parser.add_argument("--arms", default="A,B,C,D,E", help=f"subset of {','.join(ARMS)}")
    parser.add_argument(
        "--order-shuffle", action="store_true", help="one extra B rep, enum order permuted"
    )
    parser.add_argument(
        "--order-shuffle2",
        action="store_true",
        help="round-2 order probe: a second permuted B rep that RECORDS its permutation",
    )
    parser.add_argument(
        "--augment",
        type=Path,
        default=None,
        help=(
            "an existing rows.jsonl to extend: its selection_ids become the sample (no "
            "re-draw), arms already present are not called again, and the result is "
            "written to --out-rows. The named file is never opened for writing."
        ),
    )
    parser.add_argument(
        "--augment-limit",
        type=int,
        default=0,
        help="smoke aid: take only the first N selection_ids of --augment (0 = all)",
    )
    parser.add_argument(
        "--extra-rows",
        type=Path,
        default=None,
        help=(
            "another rows.jsonl whose arms are merged into the SUMMARY only, keyed by "
            "selection_id. A merged summary may not be written under docs/."
        ),
    )
    parser.add_argument(
        "--latency-subsample",
        type=int,
        default=30,
        help="rows for the cache-controlled latency pass (0 = skip); run arm-major",
    )
    parser.add_argument(
        "--latency-arms",
        default="A,B,F,D",
        help="arms measured in the latency sub-sample",
    )
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="skip the soft-agreement section (it calls localhost nomic-embed-text)",
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
    parser.add_argument(
        "--out-aux",
        type=Path,
        default=Path(".notes/skillsel-arm-replay/aux.jsonl"),
        help="resource snapshots and latency sub-sample calls (read back by --summarize-only)",
    )
    parser.add_argument("--ceiling-model", default="claude-opus-5")
    parser.add_argument(
        "--rater-model", default="claude-sonnet-5", help="arm G: the second cloud rater"
    )
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


# Which arms call Ollama. These wait out a scheduled unattended session before
# each call; the cloud and GLiClass arms do not touch the one local GPU.
_OLLAMA_ARMS = frozenset({"A", "B", "A0", "B0", "C", "F"})

# ``core.llm.generate``'s own default, which ``select_applicable_skills`` takes
# by not passing one. Pinned against the live signature by
# ``tests/test_skillsel_arm_replay.py`` rather than trusted: a production
# default that moved would leave the latency sub-sample measuring a regime
# production no longer runs, with nothing to say so.
PRODUCTION_TEMPERATURE = 1.0

# The latency sub-sample's labels for arms A and B. They are NOT
# ``A/free/rep1`` and ``B/enum/rep1``: the timing pass posts to Ollama directly
# so that ``prompt_eval_count`` comes back (production's wrapper drops it), and
# a timing measured on one code path must not be filed under a row arm measured
# on another.
LATENCY_LABELS = {"A": "A/free/latency", "B": "B/enum/latency"}


def _latency_arms(args: argparse.Namespace) -> tuple[str, ...]:
    """The arm families the timing pass runs, parsed like ``--arms``."""
    return tuple(a.strip().upper() for a in args.latency_arms.split(",") if a.strip())


def _latency_plan(
    family: str, row: Row, system: str, args: argparse.Namespace
) -> list[tuple[str, Callable[[], ArmOutcome]]]:
    """One family's calls for the timing pass.

    Arms A and B are redirected to the direct path at production's own
    temperature — same prompt, same sampling options, same output sanitising,
    but Ollama's counters survive. Round 1's latency column could not tell a
    cold call from a cached one, which is the single reason its 17.9s vs 4.7s
    reading was unusable; ``prompt_eval_count`` is that distinction.
    Every other family runs exactly as it does in a row.
    """
    if family in LATENCY_LABELS:
        runner = run_free_direct if family == "A" else run_enum_direct
        return [
            (
                LATENCY_LABELS[family],
                lambda: runner(row, system, args, temperature=PRODUCTION_TEMPERATURE),
            )
        ]
    return _arm_plan(family, row, system, args)


def _arm_plan(
    family: str, row: Row, system: str, args: argparse.Namespace
) -> list[tuple[str, Callable[[], ArmOutcome]]]:
    """The ``(label, deferred call)`` pairs one arm family produces on one row.

    Deferred rather than already-run: :func:`run_row` waits out a scheduled
    unattended session before EACH Ollama call, and arm B makes up to four of
    them — a plan that had already made its calls would have waited once and
    then run straight through the window.

    A table rather than a chain of ``if``s: every family's labels, its runner
    and its arguments sit on one line, so adding round 3's arm is one entry
    instead of another branch in a function nobody can read at a glance.
    """
    if family == "A":
        return [(label, lambda: run_free(row, system)) for label in ARM_LABELS["A"]]
    if family == "B":
        plan: list[tuple[str, Callable[[], ArmOutcome]]] = [
            (label, lambda: run_enum(row, system)) for label in ARM_LABELS["B"]
        ]
        for flag, label, seed in (
            (args.order_shuffle, B_SHUFFLE_LABEL, args.seed),
            (args.order_shuffle2, B_SHUFFLE2_LABEL, args.seed + 1),
        ):
            if not flag:
                continue
            order = list(row.catalog_names)
            random.Random(seed).shuffle(order)
            # ``order=order`` binds THIS iteration's permutation; a closure over
            # the loop variable would give both shuffles the last one.
            plan.append((label, lambda order=order: run_enum(row, system, catalog_order=order)))
        return plan
    single: dict[str, Callable[[], ArmOutcome]] = {
        "A0": lambda: run_free_direct(row, system, args, temperature=0.0),
        "B0": lambda: run_enum_direct(row, system, args, temperature=0.0),
        "C": lambda: run_logits(row, system, args),
        "F": lambda: run_logits_onepass(row, system, args),
        "D": lambda: run_gliclass(row, args),
        "D2": lambda: run_gliclass(row, args, label_mode="desc"),
        "E": lambda: run_ceiling(row, args),
        "E2": lambda: run_ceiling(row, args),
        "G": lambda: run_ceiling(row, args, model=args.rater_model),
    }
    return [(ARM_LABELS[family][0], single[family])]


def run_row(
    row: Row,
    system: str,
    wanted: Sequence[str],
    args: argparse.Namespace,
    *,
    skip_labels: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    """Every requested arm on one row, in ``ARMS`` order, serially.

    Serial on purpose: one 16GB GPU cannot hold gemma and a GLiClass checkpoint
    at once, and a latency column measured under contention answers a question
    nobody asked. ``wait_out_schedule`` sits before each Ollama call rather
    than once per row, because arm C alone can run for minutes.

    ``skip_labels`` is what makes ``--augment`` cheap AND safe: a family runs
    because ONE of its labels is missing (arm B's ``shuffled2`` on a round-1
    row), and the labels that are already frozen are not called again.
    """
    skip = set(skip_labels)
    arms: dict[str, dict[str, Any]] = {}
    for family in ARMS:
        if family not in wanted:
            continue
        for label, call in _arm_plan(family, row, system, args):
            if label in skip:
                continue
            if family in _OLLAMA_ARMS:
                wait_out_schedule(args)
            arms[label] = _arm_to_dict(call())
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
            "augment": (
                "arms added by --augment ran on a LATER date than the arms already in the "
                "source file: E vs E2 therefore carries any cloud model-version drift "
                "between the two runs on top of the rater's own spread, and the local arms "
                "ran against whatever identity.md and constitution were in force today"
                if args.augment is not None
                else "single run — every arm in this file ran in one pass"
            ),
            "direct_ollama_arms": (
                "A0 / B0 / F post to /api/generate from this script rather than through "
                "core.llm.generate, because that wrapper projects the response to a string "
                "and drops the cache and token counters. Sampling options and output "
                "sanitising are production's own; no circuit breaker or telemetry is touched"
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    wanted = tuple(a.strip().upper() for a in args.arms.split(",") if a.strip())
    # Both lists, not just ``--arms``: an unknown name in ``--latency-arms``
    # would reach ``ARM_LABELS[family]`` as a bare KeyError hours into a run,
    # after every row had already been replayed.
    for flag, names in (("--arms", wanted), ("--latency-arms", _latency_arms(args))):
        unknown = sorted(set(names) - set(ARMS))
        if unknown:
            raise SystemExit(f"unknown arm(s) in {flag}: {unknown} (choose from {list(ARMS)})")
    assert_merged_summary_stays_private(args)
    assert_output_paths_safe(args)

    log_dir = args.home / "logs"
    today = datetime.now(timezone.utc).date()
    rows, excluded, days_read = load_rows(log_dir, days=args.days, today=today)
    base_records: list[dict[str, Any]] = []
    if args.augment is not None:
        base_records, sample = augment_sample(args, rows)
    else:
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

    base_by_id = {str(record.get("selection_id")): record for record in base_records}
    args.out_rows.parent.mkdir(parents=True, exist_ok=True)
    args.out_aux.parent.mkdir(parents=True, exist_ok=True)
    aux_handle = args.out_aux.open("a", encoding="utf-8")
    handle = args.out_rows.open("a", encoding="utf-8")
    written = list(done_records)
    try:
        _write_aux(aux_handle, resource_snapshot("run-start") | {"kind": "resource"})
        for index, row in enumerate(sample, 1):
            if row.selection_id in done_ids:
                continue
            base = base_by_id.get(row.selection_id, {})
            todo = _arms_still_missing(wanted, base, args)
            arms = run_row(row, system, todo, args, skip_labels=base.get("arms", {}))
            record = merge_row_record(base, row, arms)
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
        _write_aux(aux_handle, resource_snapshot("rows-done") | {"kind": "resource"})
        run_latency_subsample(sample, system, args, aux_handle)
    finally:
        aux_handle.close()
        handle.close()
    return _finish(written, meta, by_id, args)


def _write_aux(handle: TextIO, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def family_labels(family: str, args: argparse.Namespace) -> tuple[str, ...]:
    """Every label ``family`` writes under these flags.

    Not simply ``ARM_LABELS[family]``: the order probes ride on family B and
    are switched on by flags, so a skip rule reading only ``ARM_LABELS`` would
    decide arm B was finished on a round-1 row and never run
    ``B/enum/shuffled2`` — the one arm that exists because round 1 lost its
    permutation.
    """
    labels = list(ARM_LABELS[family])
    if family == "B":
        if args.order_shuffle:
            labels.append(B_SHUFFLE_LABEL)
        if args.order_shuffle2:
            labels.append(B_SHUFFLE2_LABEL)
    return tuple(labels)


def _arms_still_missing(
    wanted: Sequence[str], base: dict[str, Any], args: argparse.Namespace
) -> tuple[str, ...]:
    """The requested arm families this row does NOT already carry.

    An arm family is skipped only when EVERY label it writes is already there:
    a half-finished family (arm A's rep1 without rep2) has to run, and the
    merge refuses to overwrite the rep that exists.
    """
    have = set(base.get("arms", {}))
    return tuple(family for family in wanted if not set(family_labels(family, args)).issubset(have))


def merge_row_record(
    base: dict[str, Any], row: Row, arms: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """A base row record plus newly-run arms. The base's own arms are never touched.

    Augmenting in place would put round 2's numbers and round 1's in one file
    with no way to tell which run produced which — and a re-run of an existing
    arm would overwrite a measurement that is already frozen in evidence. So an
    arm label that already exists stops the run instead of being replaced, and
    the result is written to a NEW file (the source file is opened read-only).
    ``catalog_order`` is filled in when the base lacks it: round 1 did not
    record it, and the position readings cannot be computed without it.
    """
    record = json.loads(json.dumps(base)) if base else {}
    record.setdefault("selection_id", row.selection_id)
    record.setdefault("ts", row.ts)
    record.setdefault("catalog_count", len(row.catalog))
    record.setdefault("logged_selected", list(row.logged_selected))
    record.setdefault("logged_rejected_count", len(row.logged_rejected))
    record.setdefault("catalog_order", list(row.catalog_names))
    existing = record.setdefault("arms", {})
    clash = sorted(set(arms) & set(existing))
    if clash:
        raise SystemExit(
            f"{row.selection_id}: arm(s) {clash} already in the augmented file — "
            "re-running a frozen arm would replace a published measurement"
        )
    existing.update(arms)
    return record


def augment_sample(
    args: argparse.Namespace, rows: Sequence[Row]
) -> tuple[list[dict[str, Any]], list[Row]]:
    """``(base records, the Row objects they name)`` for ``--augment``.

    The sample is the file's own ``selection_id`` set — not a fresh draw. A
    re-draw would have to reproduce round 1's seed, window and exclusion
    behaviour exactly, and any drift there would silently compare two different
    populations. An id the current log can no longer rebuild stops the run:
    that row's new arms would be missing from an otherwise complete file.
    """
    source = Path(args.augment).expanduser().resolve()
    # Every output path, not just --out-rows: --out-summary is written with
    # ``write_text`` and would TRUNCATE the source, --out-aux would append into
    # it, and the file being protected is what round 1's published evidence was
    # computed from. ``assert_output_paths_safe`` does not cover it — the
    # round-1 rows live under ``.notes/``, outside both of its forbidden trees.
    for flag, path in (
        ("--out-rows", args.out_rows),
        ("--out-summary", args.out_summary),
        ("--out-aux", args.out_aux),
        ("--adjudication", args.adjudication),
    ):
        if Path(path).expanduser().resolve() == source:
            raise SystemExit(f"{flag} is the --augment source; that file stays read-only")
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or not record.get("selection_id"):
            raise SystemExit(f"{source} holds a line with no selection_id")
        records.append(record)
    if args.augment_limit:
        records = records[: args.augment_limit]
    by_id = {row.selection_id: row for row in rows}
    missing = [str(r["selection_id"]) for r in records if str(r["selection_id"]) not in by_id]
    if missing:
        raise SystemExit(
            f"{len(missing)} selection_id(s) in {source} are no longer replayable from "
            f"{args.home}/logs (first: {missing[0]}) — widen --days or use the original log set"
        )
    sample = [by_id[str(r["selection_id"])] for r in records]
    print(f"augmenting {len(sample)} row(s) from {source.name}", flush=True)
    return records, sample


def run_latency_subsample(
    sample: Sequence[Row], system: str, args: argparse.Namespace, aux_handle: TextIO
) -> None:
    """The cache-controlled latency pass: arm-major over a sub-sample.

    Arm-major is the whole point. Run row-major, every arm's second call sits
    behind the same prompt prefix the previous arm just evaluated, and the
    latency column measures the cache rather than the arm — round 1's arm A
    rep2 came out 4x faster than rep1 for exactly that reason. Here each
    consecutive call of one arm is a different row, so no arm inherits its own
    warm prefix, and ``prompt_eval_count`` records what actually happened.
    """
    count = min(args.latency_subsample, len(sample))
    if count <= 0:
        return
    # The pass runs at the END of a run, so a ``--resume`` would run it a second
    # time and append a second set of calls — the aggregate would then average
    # two passes and report twice the call count.
    if any(record.get("kind") == "latency" for record in _read_jsonl(args.out_aux)):
        print("  [latency] sub-sample already recorded in --out-aux; skipping", flush=True)
        return
    wanted = _latency_arms(args)
    subsample = list(sample[:count])
    print(f"latency sub-sample: {len(wanted)} arm(s) x {count} row(s), arm-major", flush=True)
    for family in wanted:
        _write_aux(aux_handle, resource_snapshot(f"latency-{family}") | {"kind": "resource"})
        for row in subsample:
            for label, call in _latency_plan(family, row, system, args):
                if family in _OLLAMA_ARMS:
                    wait_out_schedule(args)
                entry = _arm_to_dict(call())
                _write_aux(
                    aux_handle,
                    {
                        "kind": "latency",
                        "arm": label,
                        "selection_id": row.selection_id,
                        "latency_ms": entry.get("latency_ms"),
                        "ollama": entry.get("ollama", {}),
                        "reason": entry.get("reason", ""),
                    },
                )


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
        ("--out-aux", args.out_aux),
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


def assert_merged_summary_stays_private(args: argparse.Namespace) -> None:
    """A summary carrying merged foreign arms may not be written into ``docs/``.

    ``--extra-rows`` exists so the judge can fold in a run this session never
    saw. Where those numbers came from, and whether they may be published, is
    not something this script can know — so a merged summary is confined to
    the gitignored tree, and the refusal names ``--extra-rows`` rather than
    relying on the general output-path guard's more distant message.
    """
    if args.extra_rows is None:
        return
    docs = (_REPO_ROOT / "docs").resolve()
    for flag, path in (("--out-summary", args.out_summary), ("--out-rows", args.out_rows)):
        resolved = Path(path).expanduser().resolve()
        if resolved == docs or docs in resolved.parents:
            raise SystemExit(
                f"{flag}={resolved} is under {docs} and --extra-rows was given — "
                "a summary merging outside rows stays out of the public tree"
            )


def merge_extra_rows(
    rows: list[dict[str, Any]], extra: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fold another run's arms into these rows, keyed by ``selection_id``.

    Read-only on both inputs (the merge builds new dicts), additive only: an
    arm label this file already carries wins, and the count of refused
    overwrites is reported rather than silently resolved. Extra rows naming a
    ``selection_id`` outside this sample are dropped and counted — they would
    otherwise widen the population an aggregate claims to cover.
    """
    by_id = {str(row.get("selection_id")): row for row in rows}
    merged_labels: dict[str, int] = {}
    unknown = 0
    conflicts = 0
    out = [json.loads(json.dumps(row)) for row in rows]
    out_by_id = {str(row.get("selection_id")): row for row in out}
    for record in extra:
        target = out_by_id.get(str(record.get("selection_id")))
        if target is None:
            unknown += 1
            continue
        for label, entry in (record.get("arms") or {}).items():
            if label in target.setdefault("arms", {}):
                conflicts += 1
                continue
            target["arms"][label] = entry
            merged_labels[label] = merged_labels.get(label, 0) + 1
    return out, {
        "rows_in_base": len(by_id),
        "arms_merged": merged_labels,
        "rows_outside_sample_dropped": unknown,
        "labels_already_present_kept": conflicts,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Every parseable object in a JSONL file; a missing file is an empty list."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if isinstance(record, dict):
            out.append(record)
    return out


def _catalog_maps(by_id: dict[str, Row]) -> tuple[dict[str, Sequence[str]], dict[str, str]]:
    """``(selection_id -> catalog order, skill name -> 'name — description')``.

    The second map is what the soft-agreement section embeds. Later
    descriptions win on a name collision across rows, which is the catalog's
    own direction of travel (it grew 53 -> 57 over the window).
    """
    orders: dict[str, Sequence[str]] = {}
    text: dict[str, str] = {}
    for selection_id, row in by_id.items():
        orders[selection_id] = list(row.catalog_names)
        for name, description in row.catalog:
            text[name] = f"{name}{_CATALOG_SEP}{description}" if description else name
    return orders, text


def _skill_vectors(catalog_text: dict[str, str]) -> dict[str, Any]:
    """Embed every catalog entry once, via the production localhost path.

    ``core.embeddings`` rather than a second HTTP client: the model identity
    and its calibration pin live there (ADR-0071), and this reading would
    otherwise be free to drift onto a different embedding model without
    anything noticing. An empty dict means the embedder was unreachable — the
    summary then says so instead of omitting the section silently.
    """
    from contemplative_agent.core.embeddings import embed_texts

    names = sorted(catalog_text)
    if not names:
        return {}
    vectors = embed_texts([catalog_text[name] for name in names])
    if vectors is None:
        return {}
    return {name: vectors[index] for index, name in enumerate(names)}


def production_latency_reference(home: Path, days: Sequence[str]) -> dict[str, Any] | None:
    """``duration_ms`` of production's own selection calls over the same days.

    Metadata-only telemetry (``logs/llm-calls-*.jsonl``, no prompt bodies), so
    the replay's latency can be read against what the live agent actually
    spent rather than against a number from memory.
    """
    values: list[float] = []
    for day in days:
        path = home / "logs" / f"llm-calls-{day}.jsonl"
        for record in _read_jsonl(path):
            if record.get("caller") != "core.skill_selection":
                continue
            duration = record.get("duration_ms")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                values.append(float(duration))
    if not values:
        return None
    return {"caller": "core.skill_selection", "days": list(days), "duration_ms": _spread(values)}


def _finish(
    records: list[dict[str, Any]],
    meta: dict[str, Any],
    by_id: dict[str, Row],
    args: argparse.Namespace,
) -> int:
    catalogs, catalog_text = _catalog_maps(by_id)
    if args.extra_rows is not None:
        records, merge_note = merge_extra_rows(records, _read_jsonl(Path(args.extra_rows)))
        meta = {**meta, "extra_rows_merged": merge_note}
    vectors = {} if args.no_embed else _skill_vectors(catalog_text)
    summary = summarize(
        records,
        meta,
        seed=args.seed,
        iterations=args.bootstrap_iterations,
        catalogs=catalogs,
        catalog_text=catalog_text,
        vectors=vectors,
        aux=_read_jsonl(args.out_aux),
        production_latency=production_latency_reference(
            args.home, list(meta.get("window_days_read") or [])
        ),
    )
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
