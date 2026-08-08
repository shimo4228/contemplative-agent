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
temperature, target model, and the skill-injection regime the eval pins
(``injection_regime``, added 2026-08-08 — see the ADR-0089 amendment).
Plus one signal on a different axis: ``deployment_mismatch`` compares the
pinned regime against the *installed launchd plist*, because the 2026-08-01
enforcement switch lived in a machine-local deployment artefact that no
in-tree hash can see.

NOT covered: generation-path code changes that alter behavior without
touching any recorded constant — that trigger remains prose + human
judgment (a code hash would cry stale on every refactor and train the
reader to ignore the warning). Note this is the gap the 2026-08-06 baseline
fell into; promoting the regime to a recorded field is what removed *that*
instance of it, not the gap itself. Also not covered: whether the plist is
actually loaded (`launchctl`), and any plist other than the session agent.

Deterministic and fast (sha256 + constants, no LLM, no network).

Exit codes: 0 = baseline fresh / 1 = stale (baseline-vs-tree divergences
listed on stdout, and/or a tree-vs-deployment regime mismatch, which can
report 1 with no divergences listed) / 2 = cannot check (no baseline yet,
malformed baseline, missing fixture — never reported as stale, mirroring
run_eval's exit-code discipline).
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same module-load capture hazard run_eval guards against: importing the
# moltbook adapter binds MOLTBOOK_HOME-derived Path constants. This script
# only reads constants, but pointing the env at a scratch dir first keeps
# that safe even if the adapter ever gains module-level I/O.
os.environ.setdefault("MOLTBOOK_HOME", str(Path(tempfile.gettempdir()) / "eval-staleness-nohome"))

from contemplative_agent.cli.schedule import LAUNCHD_PLIST_PATH  # noqa: E402

# Imported, not re-spelled: a third hand-typed copy of these literals would be
# unlinked to the core constants, and renaming a REGIME_* value would turn this
# detector into a permanent false mismatch with the whole suite green. The
# module-load hazard that forces run_eval.py to use a literal does not apply
# here — this module already imports contemplative_agent above, after the
# MOLTBOOK_HOME setdefault.
from contemplative_agent.core.skill_selection import (  # noqa: E402
    REGIME_FULL_CORPUS_SHADOW,
    REGIME_TWO_PASS_SELECTED,
)
from evals.dataset import dataset_sha256  # noqa: E402
from evals.run_eval import (  # noqa: E402
    DEFAULT_DATASET,
    EVALS_DIR,
    FIXTURE_DIR,
    INJECTION_REGIME,
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
        # Read from run_eval's pin, not from live module state: nothing here
        # calls _configure_pinned_assets, so an observed regime would report
        # the unconfigured default and cry stale on every run. The pin is what
        # a run would enact, and _preflight refuses to run if it does not.
        "injection_regime": INJECTION_REGIME,
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


def deployment_mismatch(plist_path: Path, pinned_regime: str) -> str | None:
    """Whether the installed schedule runs a different injection regime than
    the eval pins. ``None`` = agrees, or nothing to compare against.

    The signal the 2026-08-06 drift needed and did not have. Every other
    check here compares the baseline against the *tree*; this one compares
    the tree against the *deployment*, because that is where the divergence
    actually lived — ADR-0081 enforcement was switched on in a launchd plist
    on 2026-08-01, an artefact no in-tree hash can see.

    Machine-local and best-effort by construction: a missing plist (fresh
    clone, CI, non-macOS, schedule not installed) is silence, never a
    complaint. There is no tree-side substitute — the flag is read from the
    environment at call time, so no repo state can stand in for it.

    Parsed with ``plistlib`` (stdlib) rather than by string proximity. The
    first version scanned a 64-character window after the key for
    ``<string>1</string>``, which misread in the *silent* direction — a
    commented-out block, or the flag set to 0 followed by any short key with
    value 1, both read as enforced and returned "agrees". A detector that
    goes quiet on the shapes it exists to catch is worse than no detector.
    ``plistlib`` also handles the binary format launchd accepts, which the
    text read raised ``UnicodeDecodeError`` on — outside ``main()``'s guard,
    so it escaped as a traceback and exit 1, i.e. "stale", violating this
    module's cannot-check-is-never-stale rule.
    """
    try:
        if not plist_path.is_file():
            return None
        with plist_path.open("rb") as handle:
            parsed = plistlib.load(handle)
        env = parsed.get("EnvironmentVariables") or {}
        # Exact "1", matching enforcement_enabled()'s semantics rather than
        # truthiness.
        enforced = env.get("MOLTBOOK_SKILL_SELECTION_ENFORCE") == "1"
    except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
        # Unreadable, malformed, or an unexpected shape: silence, never a
        # complaint and never a crash.
        return None
    deployed = REGIME_TWO_PASS_SELECTED if enforced else REGIME_FULL_CORPUS_SHADOW
    if deployed == pinned_regime:
        return None
    return (
        f"injection regime: eval pins {pinned_regime!r} but the installed "
        f"schedule ({plist_path.name}) runs {deployed!r}"
    )


def newest_baseline(baselines_dir: Path) -> Path | None:
    # Face A only: a future post_golden-*.json family must not be compared
    # against the comment dataset this script hashes.
    candidates = sorted(baselines_dir.glob("comment_golden-*.json"))
    return candidates[-1] if candidates else None


def main() -> int:
    # Reported before anything baseline-related and on every exit path: an
    # eval that no longer reproduces the deployed system is worth saying out
    # loud whether or not a baseline exists to be stale against.
    mismatch = deployment_mismatch(LAUNCHD_PLIST_PATH, INJECTION_REGIME)
    if mismatch is not None:
        print("[eval-staleness] the eval no longer reproduces the deployed system:")
        print(f"[eval-staleness]   {mismatch}")
        print(
            "[eval-staleness] establish which side moved. If production changed "
            "deliberately, follow it: fix the pin (evals/run_eval.py "
            "INJECTION_REGIME), re-run, re-approve. If the deployment drifted "
            "(e.g. a reinstalled plist dropped the flag), fix the deployment. "
            "The instrument follows production — never the reverse."
        )

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
        # A deployment mismatch is a re-run trigger in its own right: the
        # baseline matches the tree, but the tree measures the wrong system.
        return 1 if mismatch is not None else 0
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
