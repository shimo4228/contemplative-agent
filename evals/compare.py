"""Baseline comparison over normalized eval-run JSON (ADR-0089).

Deterministic core: stdlib only. Operates exclusively on the eval layer's
own run schema (written by run_eval.py) — never on deepeval's TestRun files,
which are a debug byproduct with no cross-version stability contract.

Comparability gate: a verdict transition only means something when both runs
measured the same thing. Any mismatch in the fields below makes the pair
incomparable (exit 2 at the CLI), which is a different outcome from "found
regressions" (exit 1) and "clean" (exit 0). Shape violations in either run
raise IncomparableRunsError too — a malformed baseline must never surface
as a regression.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evals.judging import INCOMPLETE, VERDICT_RANK, Verdict

SCHEMA_VERSION = 1

# Manifest fields that must match for verdict transitions to be meaningful.
# deepeval_version and created_at are deliberately absent: informational.
# case_ids makes a --cases subset run incomparable with a full baseline —
# "we measured fewer cases" must never read as "clean".
COMPARABILITY_FIELDS = frozenset(
    {
        "target_model",
        "temperature",
        "judge_model",
        "assets_sha256",
        "judge_prompt_sha256",
        "prompt_templates_sha256",
        "sampling",
        "dataset_sha256",
        "samples_per_case",
        "case_ids",
    }
)


class IncomparableRunsError(ValueError):
    """The two runs (or one malformed run) cannot be meaningfully compared."""


@dataclass(frozen=True)
class Transition:
    case_id: str
    before: str
    after: str


@dataclass(frozen=True)
class CompareReport:
    regressions: tuple[Transition, ...] = ()
    improvements: tuple[Transition, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()


def load_run(path: Path) -> dict:
    """Read one normalized run JSON, validating only what makes it loadable.

    Any I/O or parse failure is an IncomparableRunsError so the CLI maps it
    to exit 2 (cannot measure), never exit 1 (regression).
    """
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncomparableRunsError(f"{path}: unreadable run JSON ({exc})") from exc
    if not isinstance(run, dict) or run.get("schema_version") != SCHEMA_VERSION:
        raise IncomparableRunsError(
            f"{path.name}: unsupported schema_version "
            f"{run.get('schema_version') if isinstance(run, dict) else type(run).__name__!r} "
            f"(expected {SCHEMA_VERSION})"
        )
    return run


def _verdict_map(run: dict, label: str) -> dict[str, str]:
    cases = run.get("cases")
    if not isinstance(cases, list):
        raise IncomparableRunsError(f"{label} run: 'cases' is not a list")
    verdicts: dict[str, str] = {}
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or "id" not in case or "case_verdict" not in case:
            raise IncomparableRunsError(f"{label} run: cases[{i}] missing id/case_verdict")
        v = case["case_verdict"]
        if v == INCOMPLETE:
            raise IncomparableRunsError(
                f"{label} run contains INCOMPLETE case {case['id']!r} — "
                "an incomplete run is an infrastructure failure, not a measurement"
            )
        try:
            Verdict(v)
        except ValueError as exc:
            raise IncomparableRunsError(
                f"{label} run: cases[{i}] has unknown verdict {v!r}"
            ) from exc
        verdicts[case["id"]] = v
    return verdicts


def compare_runs(baseline: dict, current: dict) -> CompareReport:
    """Compare two normalized runs case by case.

    Raises IncomparableRunsError on manifest mismatch, INCOMPLETE cases, or
    shape violations; otherwise returns the full transition report.
    Regression = the verdict of a case present in both runs got worse.
    """
    base_manifest, cur_manifest = baseline.get("manifest", {}), current.get("manifest", {})
    mismatched = sorted(
        f for f in COMPARABILITY_FIELDS if base_manifest.get(f) != cur_manifest.get(f)
    )
    if mismatched:
        detail = ", ".join(
            f"{f}: {base_manifest.get(f)!r} != {cur_manifest.get(f)!r}" for f in mismatched
        )
        raise IncomparableRunsError(f"manifest mismatch — {detail}")

    base_verdicts = _verdict_map(baseline, "baseline")
    cur_verdicts = _verdict_map(current, "current")

    regressions: list[Transition] = []
    improvements: list[Transition] = []
    unchanged: list[str] = []
    for case_id in sorted(set(base_verdicts) & set(cur_verdicts)):
        before, after = base_verdicts[case_id], cur_verdicts[case_id]
        if before == after:
            unchanged.append(case_id)
            continue
        transition = Transition(case_id=case_id, before=before, after=after)
        if VERDICT_RANK[Verdict(after)] > VERDICT_RANK[Verdict(before)]:
            regressions.append(transition)
        else:
            improvements.append(transition)

    return CompareReport(
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        added=tuple(sorted(set(cur_verdicts) - set(base_verdicts))),
        removed=tuple(sorted(set(base_verdicts) - set(cur_verdicts))),
        unchanged=tuple(unchanged),
    )
