#!/usr/bin/env python3
"""LLM behavioral eval runner — Face A: Moltbook comment generation (ADR-0089).

Runs the production ``generate_comment`` path (real Ollama, production
temperature) over the golden dataset under PINNED prompt assets
(evals/fixtures/agent_home/), judges every sample with an isolated
``claude -p`` against the snapshot constitution, and writes a normalized
run JSON that evals/compare.py can diff against an approved baseline.

Exit codes (mirrors .claude/verify.sh):
  0 = run complete (and no regressions, when --baseline is given)
  1 = regressions against the baseline
  2 = cannot measure (Ollama down, identity fallback, INCOMPLETE cases,
      incomparable or malformed baseline, judge failure, any unexpected
      error — everything that is not a clean measurement routes here so it
      can never masquerade as "regressions found")

Not wired into verify.sh on purpose: this is slow (minutes per case),
stochastic, and judged by delta — a different contract from the fast
deterministic gate. Run it when prompt assets, the model, sampling, or the
generation path change.

Usage:
    uv run --group eval python evals/run_eval.py --cases emptiness-1 --samples 1
    uv run --group eval python evals/run_eval.py --baseline evals/baselines/<run>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

# Make the evals package importable under direct-script invocation
# (`python evals/run_eval.py`), mirroring tests/benchmark_distill.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Deterministic-core imports only. contemplative_agent and deepeval are
# imported inside main() AFTER the environment is prepared: MOLTBOOK_HOME is
# captured at module load time (adapters/moltbook/config.py), so importing
# early would point the adapter at the live ~/.config/moltbook.
from evals.compare import IncomparableRunsError, compare_runs, load_run
from evals.dataset import DatasetError, GoldenCase, dataset_sha256, load_dataset
from evals.judging import (
    INCOMPLETE,
    JudgeError,
    JudgeResult,
    Verdict,
    aggregate_case,
    render_judge_prompt,
    run_claude_judge,
)
from evals.snapshot_assets import SnapshotError, aggregate_sha256, hash_tree

SCHEMA_VERSION = 1

# The skill-injection regime this eval reproduces (ADR-0081 two-pass
# enforcement, which is what the launchd plist runs). Recorded in every
# manifest and compared by check_staleness, so the question the 2026-08-06
# baseline could not answer — "which injection regime was this measured
# under?" — is now answerable from the artefact alone. Changing this value
# changes the system under measurement and must invalidate the baseline.
#
# Spelled as a literal, not imported from core.skill_selection: nothing from
# contemplative_agent may be imported at this module's load time (the
# MOLTBOOK_HOME capture hazard documented above the deterministic-core
# imports). tests/test_eval_injection_regime.py holds the two names together
# — a test is the right seam for that link, an import is not.
INJECTION_REGIME = "two_pass_selected"

EVALS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = EVALS_DIR / "fixtures" / "agent_home"
JUDGE_PROMPT_PATH = EVALS_DIR / "fixtures" / "judge" / "comment_judge_prompt.md"
DEFAULT_DATASET = EVALS_DIR / "datasets" / "comment_golden.jsonl"
RESULTS_DIR = EVALS_DIR / "results"
REPO_ROOT = EVALS_DIR.parent


def prompt_templates_sha256() -> str:
    """Digest of the repo-pinned template layer the eval generation reads.

    The scratch MOLTBOOK_HOME has no prompts/ override, so config/prompts/
    and config/domain.json ARE generation inputs (Decision 3) — editing
    comment.md is the single most likely prompt change and must register as
    baseline staleness. Shared with evals/check_staleness.py.
    """
    digest = hashlib.sha256()
    for path in sorted((REPO_ROOT / "config" / "prompts").glob("*.md")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    domain = REPO_ROOT / "config" / "domain.json"
    if domain.is_file():
        digest.update(domain.read_bytes())
    return digest.hexdigest()


def sampling_state() -> dict:
    """The non-temperature sampling/budget constants a run bakes in.

    Recorded as values (not a code hash) so a refactor that moves code
    without changing behavior does not cry stale, while an actual constant
    change does. Shared with evals/check_staleness.py.
    """
    from contemplative_agent.core.config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH
    from contemplative_agent.core.llm import NUM_CTX, SAMPLING_TOP_K, SAMPLING_TOP_P

    return {
        "num_ctx": NUM_CTX,
        "top_p": SAMPLING_TOP_P,
        "top_k": SAMPLING_TOP_K,
        "max_comment_length": MAX_COMMENT_LENGTH,
        "max_post_length": MAX_POST_LENGTH,
    }


def _die_unmeasurable(msg: str) -> NoReturn:
    print(f"[eval] cannot measure: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _preflight(fixture: Path, judge_bin: str) -> None:
    """Fail fast (exit 2) on anything that would make the run meaningless.

    Must run AFTER _configure_pinned_assets: the identity sentinel below
    checks the prompt that configure() just built — reorder these and the
    check silently always passes.
    """
    import requests

    from contemplative_agent.core.llm import get_identity_system_prompt, validate_trusted_url

    if not fixture.is_dir() or not (fixture / "identity.md").is_file():
        _die_unmeasurable(
            f"fixture assets missing at {fixture} — run: uv run python evals/snapshot_assets.py"
        )
    if shutil.which(judge_bin) is None:
        _die_unmeasurable(f"judge binary {judge_bin!r} not on PATH")

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        # Same SSRF gate the production client applies to this variable.
        validate_trusted_url(base_url, source="OLLAMA_BASE_URL")
        requests.get(f"{base_url}/api/tags", timeout=5).raise_for_status()
    except Exception as exc:  # broad on purpose: any failure here means "not measurable"
        _die_unmeasurable(f"Ollama unreachable at {base_url}: {exc}")

    # Identity sentinel: validate_identity_content() silently falls back to
    # the default prompt on a forbidden pattern — the eval would then measure
    # a different persona without noticing. Assert the fixture identity's
    # first content line actually made it into the built prompt.
    sentinel = next(
        (
            stripped
            for line in (fixture / "identity.md").read_text(encoding="utf-8").splitlines()
            if (stripped := line.strip()) and not stripped.startswith("#")
        ),
        None,
    )
    if not sentinel:
        _die_unmeasurable("fixture identity.md has no content line to use as sentinel")
    if sentinel not in get_identity_system_prompt():
        _die_unmeasurable(
            "fixture identity did not reach the system prompt (forbidden-pattern "
            "fallback?) — sentinel line not found"
        )

    # Regime sentinel, same discipline as the identity one above. Two parts,
    # because the configuration reading alone is nearly tautological — it
    # inspects the two globals _configure_pinned_assets just set. The
    # precondition check is what gives it teeth: an empty catalog or an
    # unloadable selection template sends every call back to full-corpus
    # injection while the configuration still reports two_pass_selected, so
    # the manifest would claim a regime the run never enacted. That is the
    # 2026-08-06 defect one layer down.
    from contemplative_agent.core.skill_selection import (
        configured_injection_regime,
        selection_preconditions_unmet,
    )

    configured = configured_injection_regime()
    if configured != INJECTION_REGIME:
        _die_unmeasurable(
            f"injection regime mismatch: pinned {INJECTION_REGIME!r} but the "
            f"configured wiring permits {configured!r}"
        )
    if INJECTION_REGIME == "two_pass_selected":
        unmet = selection_preconditions_unmet()
        if unmet is not None:
            _die_unmeasurable(
                f"pinned regime {INJECTION_REGIME!r} is unreachable: {unmet} — "
                f"every sample would fall back to full-corpus injection while "
                f"the manifest claimed otherwise"
            )

    # Fail-open headroom. When the pass-1 selector fails per call
    # (fail_open_llm / fail_open_parse — inherently not preflightable),
    # ADR-0081 degrades to full-corpus injection. A corpus that no longer
    # fits NUM_CTX turns that graceful degradation into a budget_exceeded
    # skip: the sample is lost, and because aggregate_case only needs a
    # strict majority (2 of 3), one loss per case is absorbed into a smaller
    # denominator rather than surfaced. Warn rather than die — the run is
    # valid as long as the selector holds, and the manifest records how many
    # observations actually fell back, so the absorption is auditable after
    # the fact instead of invisible.
    from contemplative_agent.core.llm import MIN_CLAMPED_NUM_PREDICT, NUM_CTX, _estimate_tokens
    from contemplative_agent.core.llm.prompting import _build_system_prompt

    # Mirror the real audit-C2 condition rather than the laxer
    # "corpus >= window": the guard skips when what remains after the input
    # cannot even meet the clamp floor, which bites before the corpus alone
    # overflows. No BACKEND_FRAMING_RESERVE term — the guard withholds it
    # only when a backend counted for real, and the Ollama path this eval
    # runs on has no tokenizer (ADR-0087), so the estimator's own over-count
    # is the reserve. The post's tokens are excluded because they vary per
    # case; this is the headroom before any prompt, so it reads optimistic
    # by design and a warning here is strictly worse in practice.
    full_corpus_tokens = _estimate_tokens(_build_system_prompt())
    headroom = NUM_CTX - full_corpus_tokens
    if headroom < MIN_CLAMPED_NUM_PREDICT:
        print(
            f"[eval] WARNING: full-corpus fallback would be skipped, not degraded "
            f"({full_corpus_tokens} tok leaves {headroom} < clamp floor "
            f"{MIN_CLAMPED_NUM_PREDICT} in NUM_CTX {NUM_CTX}) — any fail-open "
            f"selection this run loses its sample. Check "
            f"manifest.injection_observed.fell_back before trusting the verdicts.",
            file=sys.stderr,
        )


def _configure_pinned_assets(fixture: Path, selection_audit_dir: Path) -> None:
    """Mirror the production wiring (cli/runtime.py + moltbook agent.py),
    but source every evolving asset from the pinned fixture.

    Skill selection is wired here, not skipped. The original version left it
    unconfigured on the premise that "production runs it in shadow mode" —
    already false when written (ADR-0081 enforcement shipped in ``0723726``,
    the plist carried the flag from 2026-08-01), so the eval injected the
    whole corpus against a production that injects a selection. Both halves
    of that divergence were structural rather than environmental: without
    ``configure_skill_selection`` the ``audit_dir`` kill switch forces full
    injection no matter what the flag says.

    ``selection_audit_dir`` points at the run directory, so each run keeps
    the selections it actually made — the evidence for *why* two runs
    differ, alongside the verdicts of *how*.

    Still deliberately NOT configured: telemetry_dir (no writes), submolt
    scope (read-only instrument, irrelevant here).
    """
    from contemplative_agent.core.domain import load_constitution
    from contemplative_agent.core.llm import configure
    from contemplative_agent.core.skill_selection import configure_skill_selection

    configure(identity_path=fixture / "identity.md")
    clauses = load_constitution(fixture / "constitution")
    if clauses:
        configure(axiom_prompt=clauses)
    if (fixture / "skills").is_dir():
        configure(skills_dir=fixture / "skills")
    if (fixture / "rules").is_dir():
        configure(rules_dir=fixture / "rules")

    # Pin the regime rather than inherit it: an eval whose measured system
    # depends on the caller's environment is not reproducible. INJECTION_REGIME
    # names what is pinned, _preflight asserts the wiring enacted it, and the
    # manifest records it so a future divergence is a diff, not a memory.
    #
    # NOTE: this mutates process-global os.environ, which the function name
    # does not imply. In-process callers (tests) must restore it themselves —
    # monkeypatch.delenv(raising=False) does NOT, because pytest records no
    # undo entry when the name was absent to begin with.
    os.environ["MOLTBOOK_SKILL_SELECTION_ENFORCE"] = "1"
    selection_audit_dir.mkdir(parents=True, exist_ok=True)
    # Guarded like its sibling above: with skills/ absent the catalog is
    # empty, every call falls back to full-corpus injection, and only
    # _preflight's precondition check stands between that and a manifest
    # claiming a regime the run never took.
    if (fixture / "skills").is_dir():
        configure_skill_selection(skills_dir=fixture / "skills", audit_dir=selection_audit_dir)


def _judge_sample(
    case: GoldenCase,
    comment: str,
    *,
    template: str,
    constitution: str,
    judge_model: str,
    judge_timeout: int,
    scratch: Path,
    audit_path: Path,
) -> JudgeResult:
    prompt = render_judge_prompt(
        template, constitution=constitution, axiom=case.axiom, post=case.post, comment=comment
    )
    return run_claude_judge(
        prompt,
        model=judge_model,
        scratch_dir=scratch,
        timeout=judge_timeout,
        audit_path=audit_path,
    )


def _deepeval_report(case_records: list[dict], run_dir: Path) -> None:
    """Secondary artifact: replay the pipeline's verdicts into a deepeval
    TestRun for its report/inspection tooling. Failure here never fails the
    run — the normalized JSON is the contract."""
    try:
        from deepeval import evaluate
        from deepeval.evaluate import AsyncConfig, DisplayConfig
        from deepeval.test_case import LLMTestCase

        from evals.adapter_deepeval import PrecomputedVerdictMetric

        verdicts: dict[str, tuple[Verdict, str]] = {}
        test_cases = []
        for record in case_records:
            for i, sample in enumerate(record["samples"]):
                if sample["status"] != "ok":
                    continue
                name = f"{record['id']}#s{i + 1}"
                failed = [c["question"] for c in sample["checks"] if not c["answer"]]
                reason = "all checks passed" if not failed else "failed: " + ", ".join(failed)
                verdicts[name] = (Verdict(sample["verdict"]), reason)
                test_cases.append(
                    LLMTestCase(name=name, input=record["post"], actual_output=sample["comment"])
                )
        if not test_cases:
            return
        evaluate(
            test_cases=test_cases,
            metrics=[PrecomputedVerdictMetric(verdicts)],
            async_config=AsyncConfig(run_async=False),
            display_config=DisplayConfig(
                results_folder=str(run_dir / "deepeval"), print_results=False
            ),
        )
    except Exception as exc:  # broad on purpose: report layer must not sink the run
        print(f"[eval] deepeval report generation failed (non-fatal): {exc}", file=sys.stderr)


def _deepeval_version() -> str:
    try:
        import deepeval

        return getattr(deepeval, "__version__", "unknown")
    except ImportError:
        return "unknown"


def _write_run(run: dict, run_path: Path) -> None:
    run_path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--samples", type=int, default=3, help="samples per case (default 3)")
    parser.add_argument("--cases", type=str, default="", help="comma-separated case ids to run")
    parser.add_argument("--judge-model", type=str, default="claude-sonnet-5")
    parser.add_argument(
        "--judge-timeout", type=int, default=300, help="seconds per judge attempt (default 300)"
    )
    parser.add_argument("--baseline", type=Path, default=None, help="approved baseline to diff")
    args = parser.parse_args()

    if args.samples < 1:
        parser.error("--samples must be >= 1")

    # Resolve user-supplied paths BEFORE the chdir below, or relative paths
    # would silently resolve against the fresh run directory.
    dataset_path = args.dataset.resolve()
    baseline_path = args.baseline.resolve() if args.baseline is not None else None

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch_home = run_dir / "moltbook-home"
    scratch_home.mkdir(exist_ok=True)
    judge_scratch = run_dir / "judge-scratch"

    # Environment BEFORE any contemplative_agent import (MOLTBOOK_HOME is
    # captured at module load) and before deepeval (telemetry, caches).
    # CONFIDENT_API_KEY would make deepeval POST golden posts and generated
    # comments to Confident AI at the end of evaluate() — strip it and its
    # siblings the way the judge env strips ANTHROPIC_API_KEY.
    os.environ["MOLTBOOK_HOME"] = str(scratch_home)
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
    os.environ["DEEPEVAL_CACHE_FOLDER"] = str(run_dir / ".deepeval")
    for key in ("CONFIDENT_API_KEY", "DEEPEVAL_API_KEY", "DEEPEVAL_RESULTS_FOLDER"):
        os.environ.pop(key, None)
    # MOLTBOOK_SKILL_SELECTION_ENFORCE is deliberately NOT scrubbed here any
    # more: _configure_pinned_assets sets it to the pinned regime, so the
    # inherited value is overwritten rather than dropped. Scrubbing it was
    # half of what made the eval measure full-corpus injection while
    # production ran two-pass (ADR-0089 amendment).
    os.chdir(run_dir)  # second containment wall for anything cwd-relative

    cases = load_dataset(dataset_path)
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
        if not wanted:
            _die_unmeasurable("--cases given but no case ids parsed from it")
        unknown = wanted - {c.id for c in cases}
        if unknown:
            _die_unmeasurable(f"unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c.id in wanted]

    _configure_pinned_assets(FIXTURE_DIR, run_dir / "skill-selection")
    _preflight(FIXTURE_DIR, "claude")

    from contemplative_agent.adapters.moltbook.llm_functions import COMMENT_TEMPERATURE
    from contemplative_agent.core.llm import served_model
    from evals.generation import generate_samples

    template = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    # The judge scores against the same constitution the agent was
    # configured with — load_constitution globs the whole directory, so an
    # amendment that adds a second file reaches both sides or neither.
    from contemplative_agent.core.domain import load_constitution

    constitution = load_constitution(FIXTURE_DIR / "constitution")
    if not constitution:
        _die_unmeasurable(f"no constitution clauses under {FIXTURE_DIR / 'constitution'}")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_model": served_model(),
        "temperature": COMMENT_TEMPERATURE,
        "judge_model": args.judge_model,
        "assets_sha256": aggregate_sha256(hash_tree(FIXTURE_DIR)),
        "judge_prompt_sha256": hashlib.sha256(JUDGE_PROMPT_PATH.read_bytes()).hexdigest(),
        "prompt_templates_sha256": prompt_templates_sha256(),
        "injection_regime": INJECTION_REGIME,
        "sampling": sampling_state(),
        "dataset_sha256": dataset_sha256(dataset_path),
        "samples_per_case": args.samples,
        # A --cases subset changes what was measured; recording the id set
        # makes it a comparability mismatch instead of a silent "clean".
        "case_ids": sorted(c.id for c in cases),
        "deepeval_version": _deepeval_version(),
    }
    run: dict = {"schema_version": SCHEMA_VERSION, "manifest": manifest, "cases": []}
    run_path = run_dir / "run.json"

    case_records: list[dict] = run["cases"]
    for case in cases:
        print(f"[eval] case {case.id} ({case.axiom}/{case.kind}): generating…", flush=True)
        samples = generate_samples(case.post, args.samples)
        sample_records: list[dict] = []
        ok_verdicts: list[Verdict] = []
        for i, sample in enumerate(samples):
            if sample.status != "ok" or sample.text is None:
                sample_records.append({"status": sample.status})
                print(f"[eval]   sample {i + 1}: generation FAILED", flush=True)
                continue
            try:
                result = _judge_sample(
                    case,
                    sample.text,
                    template=template,
                    constitution=constitution,
                    judge_model=args.judge_model,
                    judge_timeout=args.judge_timeout,
                    scratch=judge_scratch,
                    audit_path=run_dir / "judge-audit.jsonl",
                )
            except JudgeError as exc:
                _write_run(run, run_path)  # keep the partial run inspectable
                _die_unmeasurable(
                    f"judge failed on {case.id} sample {i + 1}: {exc} "
                    f"(partial run kept at {run_path})"
                )
            ok_verdicts.append(result.verdict)
            sample_records.append(
                {
                    "status": "ok",
                    "comment": sample.text,
                    "comment_sha256": hashlib.sha256(sample.text.encode()).hexdigest(),
                    "verdict": result.verdict.value,
                    "checks": [
                        {"question": c.question, "answer": c.answer, "evidence": c.evidence}
                        for c in result.checks
                    ],
                }
            )
            print(f"[eval]   sample {i + 1}: {result.verdict.value}", flush=True)
        verdict = aggregate_case(ok_verdicts, requested=args.samples)
        print(f"[eval] case {case.id}: {verdict}", flush=True)
        case_records.append(
            {
                "id": case.id,
                "axiom": case.axiom,
                "kind": case.kind,
                "post": case.post,
                "samples": sample_records,
                "case_verdict": verdict,
            }
        )
        _write_run(run, run_path)  # incremental: an abort keeps every finished case

    # The regime a run *took*, read back from the selection audit it wrote.
    # manifest.injection_regime is a pin (intent); this is the observation.
    # Without it, per-call fail-opens would silently reduce each case's
    # denominator — aggregate_case needs only a strict majority, so one lost
    # sample per case never surfaces — while the manifest still asserted the
    # pinned regime for the whole run. Recorded outside `manifest` on
    # purpose: compare.py treats manifest fields as comparability keys, and
    # two runs with different fail-open counts are still comparable.
    from contemplative_agent.core.skill_selection import observed_injection_outcomes

    run["injection_observed"] = observed_injection_outcomes(run_dir / "skill-selection")
    observed = run["injection_observed"]
    # Expected one selection per generation attempt. A *missing* record is
    # not the same as a recorded fallback and must not read as clean: when
    # shadow_observe_skill_selection hits an internal exception (including a
    # failed audit write) it degrades to None — full-corpus injection — and
    # writes nothing. Counting only `fell_back` would let such a run claim
    # the pinned regime with no warning at all, which is exactly the silent
    # fallback CLAUDE.md's observability rule prohibits.
    expected_observations = sum(len(c["samples"]) for c in case_records)
    unobserved = expected_observations - observed.get("records", 0)
    observed["expected"] = expected_observations
    observed["unobserved"] = unobserved
    if observed.get("fell_back") or unobserved:
        print(
            f"[eval] WARNING: injection regime not uniform across this run — "
            f"{observed['fell_back']} recorded fallback(s) and {unobserved} "
            f"unrecorded selection(s) out of {expected_observations} generation "
            f"attempts (verdicts: {observed['verdicts']}). Those generations did "
            f"not run under the regime the manifest pins; do not approve this "
            f"run as a baseline without accounting for them.",
            file=sys.stderr,
        )

    _write_run(run, run_path)
    print(f"[eval] normalized run written: {run_path}", flush=True)

    _deepeval_report(case_records, run_dir)

    incomplete = [c["id"] for c in case_records if c["case_verdict"] == INCOMPLETE]
    if incomplete:
        _die_unmeasurable(
            f"INCOMPLETE cases {incomplete} — infrastructure failure, run cannot be a baseline"
        )

    if baseline_path is not None:
        report = compare_runs(load_run(baseline_path), run)
        for t in report.regressions:
            print(f"[eval] REGRESSION {t.case_id}: {t.before} -> {t.after}")
        for t in report.improvements:
            print(f"[eval] improvement {t.case_id}: {t.before} -> {t.after}")
        if report.added or report.removed:
            print(f"[eval] cases added={list(report.added)} removed={list(report.removed)}")
        print(
            f"[eval] compare: {len(report.regressions)} regressions, "
            f"{len(report.improvements)} improvements, {len(report.unchanged)} unchanged"
        )
        return 1 if report.regressions else 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except (IncomparableRunsError, DatasetError, SnapshotError, JudgeError, OSError) as exc:
        _die_unmeasurable(str(exc))
    except Exception as exc:  # last resort: an unexpected bug is still "cannot measure"
        _die_unmeasurable(f"unexpected {type(exc).__name__}: {exc}")
