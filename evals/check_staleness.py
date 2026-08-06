#!/usr/bin/env python3
"""Detect when the approved eval baseline no longer represents the tree.

ADR-0089 defines when to re-run the eval (prompt-asset / model / sampling /
generation-path changes) but a rule that lives only in prose depends on
someone remembering it. This check makes the *trigger* mechanical while the
*decision* to run stays human: it compares the newest approved baseline's
manifest against what a run started right now would measure, and reports
every divergence. verify.sh full mode surfaces the result as a warning —
never a FAIL, because a stale baseline blocks nothing; it only means the
regression gate is silently measuring against the past.

Covered signals: pinned fixture assets, golden dataset, judge prompt,
config/prompts + domain.json templates, sampling/budget constants,
temperature, target model. NOT covered: generation-path code changes that
alter behavior without touching any recorded constant — that trigger
remains prose + human judgment (a code hash would cry stale on every
refactor and train the reader to ignore the warning).

Deterministic and fast (sha256 + constants, no LLM, no network).

Exit codes: 0 = baseline fresh / 1 = stale (divergences listed on stdout) /
2 = cannot check (no baseline yet, malformed baseline, missing fixture —
never reported as stale, mirroring run_eval's exit-code discipline).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same module-load capture hazard run_eval guards against: importing the
# moltbook adapter binds MOLTBOOK_HOME-derived Path constants. This script
# only reads constants, but pointing the env at a scratch dir first keeps
# that safe even if the adapter ever gains module-level I/O.
os.environ.setdefault("MOLTBOOK_HOME", str(Path(tempfile.gettempdir()) / "eval-staleness-nohome"))

from evals.dataset import dataset_sha256  # noqa: E402
from evals.run_eval import (  # noqa: E402
    DEFAULT_DATASET,
    EVALS_DIR,
    FIXTURE_DIR,
    JUDGE_PROMPT_PATH,
    prompt_templates_sha256,
    sampling_state,
)
from evals.snapshot_assets import aggregate_sha256, hash_tree  # noqa: E402

BASELINES_DIR = EVALS_DIR / "baselines"


def current_state() -> dict:
    """What a run started now would record in its manifest (tree-state subset).

    judge_model and samples_per_case are per-invocation CLI choices; their
    defaults live in run_eval.py, whose changes are ordinary code review
    territory — deliberately not staleness signals.
    """
    import hashlib

    from contemplative_agent.adapters.moltbook.llm_functions import COMMENT_TEMPERATURE
    from contemplative_agent.core.llm import served_model

    return {
        "target_model": served_model(),
        "temperature": COMMENT_TEMPERATURE,
        "assets_sha256": aggregate_sha256(hash_tree(FIXTURE_DIR)),
        "judge_prompt_sha256": hashlib.sha256(JUDGE_PROMPT_PATH.read_bytes()).hexdigest(),
        "prompt_templates_sha256": prompt_templates_sha256(),
        "sampling": sampling_state(),
        "dataset_sha256": dataset_sha256(DEFAULT_DATASET),
    }


def divergences(baseline_manifest: dict, current: dict) -> list[str]:
    """Fields where the baseline no longer matches the tree (pure)."""
    return [
        f"{field}: baseline {baseline_manifest.get(field)!r} != current {current[field]!r}"
        for field in sorted(current)
        if baseline_manifest.get(field) != current[field]
    ]


def newest_baseline(baselines_dir: Path) -> Path | None:
    # Face A only: a future post_golden-*.json family must not be compared
    # against the comment dataset this script hashes.
    candidates = sorted(baselines_dir.glob("comment_golden-*.json"))
    return candidates[-1] if candidates else None


def main() -> int:
    baseline_path = newest_baseline(BASELINES_DIR)
    if baseline_path is None:
        print(
            "[eval-staleness] no approved baseline in evals/baselines/ — regression gate inactive"
        )
        return 2
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict) or not isinstance(baseline.get("manifest"), dict):
            print(f"[eval-staleness] cannot check: {baseline_path.name} has no manifest object")
            return 2
        current = current_state()
    except Exception as exc:  # any failure is "cannot check", never "stale"
        print(f"[eval-staleness] cannot check: {type(exc).__name__}: {exc}")
        return 2

    diverged = divergences(baseline["manifest"], current)
    if not diverged:
        return 0
    print(f"[eval-staleness] baseline {baseline_path.name} is STALE — the regression gate")
    print("[eval-staleness] no longer measures the current system (ADR-0089 re-run trigger):")
    for line in diverged:
        print(f"[eval-staleness]   {line}")
    print(
        "[eval-staleness] run: uv run --group eval python evals/run_eval.py "
        f"--baseline evals/baselines/{baseline_path.name}  (then re-approve)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
