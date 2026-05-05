"""Centralized retrieval / classification thresholds (ADR-0035 PR2).

Each constant carries the ADR / calibration date / unit so that future
edits can trace the value back to its evidence rather than re-deriving
it. Move thresholds here when introducing a new one — ``core/snapshot.py``
reads from this module so a new value automatically appears in pivot
snapshots without a separate registration step.

Thresholds that remain module-local (intentional):
- ``views._DEFAULT_THRESHOLD`` — per-view override slot (configured
  per-view via the registry, not a global cap).

Why a single file rather than per-domain modules: the registry is the
ADR-0020 lens. Splitting it duplicates the late-import pattern that
``snapshot.collect_thresholds`` was already routing around.
"""

from __future__ import annotations

# --- Distill / dedup (core/distill.py callers) -----------------------------

NOISE_THRESHOLD: float = 0.55
"""Episode noise gate (ADR-0026, ADR-0027 Phase 1).

Embedding cosine to the ``noise`` view centroid; episodes at or above
this threshold are gated out of distillation but still retained in the
episode log as ``bīja`` (ADR-0027). Calibrated against the ``noise``
seed text, not against patterns.
"""

SIM_DUPLICATE: float = 0.90
"""Pattern-pair near-duplicate threshold (ADR-0019 dedup, calibrated 2026-04-17).

At or above ``SIM_DUPLICATE`` the new pattern is dropped (SKIP). Was
0.92; lowered to 0.90 after observing max cosine 0.8980 across 97
patterns in the production store (`docs/evidence/adr-0019/...`).
"""

SIM_UPDATE: float = 0.80
"""Pattern-pair similarity-boost threshold (ADR-0019 dedup).

In ``[SIM_UPDATE, SIM_DUPLICATE)`` the existing pattern is
soft-invalidated (ADR-0021 bitemporal) and a revised row is appended.
Below ``SIM_UPDATE`` the new pattern is added unconditionally (ADD).
"""

DEDUP_IMPORTANCE_FLOOR: float = 0.05
"""Patterns below this effective importance are excluded from dedup
comparisons (ADR-0019). Keeps a heavily-decayed legacy row from
blocking a fresh, more important arrival via residual cosine
similarity.
"""

# --- Insight / rules-distill clustering ------------------------------------

CLUSTER_THRESHOLD_INSIGHT: float = 0.70
"""Cosine threshold for grouping patterns into one ``insight`` skill batch.

Calibration: ``docs/evidence/adr-0009/threshold-calibration-20260417.md``.
Pattern text is short; cosine sits higher than skill-text side, so this
runs above ``CLUSTER_THRESHOLD_RULES``.
"""

CLUSTER_THRESHOLD_RULES: float = 0.65
"""Cosine threshold for grouping skills into one ``rules-distill`` batch.

Skill text is longer than pattern text, so the cosine distribution sits
lower than the pattern side. Tune via dry run if rules-distill batches
become too narrow / too wide.
"""

MAX_BATCH: int = 10
"""Maximum patterns/skills passed to one LLM extract call.

Used by both ``insight`` (``BATCH_SIZE``) and ``rules-distill``
(``MAX_RULES_BATCH``); kept identical so the two callers share a single
prompt-size budget.
"""

# --- Stocktake clustering --------------------------------------------------

SIM_CLUSTER_THRESHOLD: float = 0.80
"""Pair similarity above which two skills are eligible to merge in
``skill-stocktake`` (ADR-0016 broad consolidator role).

Higher than ``CLUSTER_THRESHOLD_RULES`` because stocktake is a final
audit; we want only confidently-redundant pairs to surface as merge
candidates.
"""

