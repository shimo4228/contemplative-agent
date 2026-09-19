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
A second axis briefly lived here: ``deployment_mismatch`` compared the
pinned regime against the *installed launchd plist*, because the 2026-08-01
enforcement switch lived in a machine-local deployment artefact that no
in-tree hash could see. It retired on 2026-08-08 with the flag it watched.
The regime is now decided entirely by in-tree code (``cli/runtime.py``
configures the selector whenever the skills directory exists), so no
deployment artefact can disagree with the pin, and a check that cannot fire
is not coverage — it reads as coverage. Restore this axis only if some
out-of-tree artefact regains a say in what the eval measures.

NOT covered: generation-path code changes that alter behavior without
touching any recorded constant — that trigger remains prose + human
judgment (a code hash would cry stale on every refactor and train the
reader to ignore the warning). Note this is the gap the 2026-08-06 baseline
fell into; promoting the regime to a recorded field is what removed *that*
instance of it, not the gap itself.

Deterministic and fast (sha256 + constants, no LLM, no network).

``--acknowledge --reason TEXT`` is the one human escape hatch (2026-09-19
amendment): when the ONLY divergence is ``prompt_templates_sha256`` and the
author judges the edited templates unreachable from the comment path the
eval measures, it records that judgement in a sidecar next to the baseline
instead of demanding a re-run. ``--dry-run`` prints the same checks and the
changed-file list without writing. See :mod:`evals.ack` for why the
detection stays wide and the escape stays human.

Exit codes: 0 = baseline fresh (measured, acknowledged, or nothing to
record) / 1 = the baseline is stale — either the plain report, or an
``--acknowledge`` refused because something other than the prompt digest
diverges, which leaves it stale too / 2 = cannot check (no baseline yet,
malformed baseline, malformed sidecar, missing fixture — never reported as
stale, mirroring run_eval's exit-code discipline).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same module-load capture hazard run_eval guards against: importing the
# moltbook adapter binds MOLTBOOK_HOME-derived Path constants. This script
# only reads constants, but pointing the env at a scratch dir first keeps
# that safe even if the adapter ever gains module-level I/O.
os.environ.setdefault("MOLTBOOK_HOME", str(Path(tempfile.gettempdir()) / "eval-staleness-nohome"))

from evals.ack import (  # noqa: E402
    PROMPT_FIELD,
    Acknowledgement,
    append_acknowledgement,
    load_acknowledgements,
    sidecar_path,
)
from evals.dataset import dataset_sha256  # noqa: E402
from evals.run_eval import (  # noqa: E402
    DEFAULT_DATASET,
    EVALS_DIR,
    FIXTURE_DIR,
    INJECTION_REGIME,
    JUDGE_PROMPT_PATH,
    REPO_ROOT,
    hashed_prompt_paths,
    prompt_templates_sha256,
    sampling_state,
)
from evals.snapshot_assets import aggregate_sha256, hash_tree  # noqa: E402

BASELINES_DIR = EVALS_DIR / "baselines"

#: Where an acknowledgement's file list comes from: the tracked inputs of
#: ``prompt_templates_sha256``. Passed to git as pathspecs, so a change to a
#: script-only prompt (which cannot move the digest) still has to survive the
#: registry filter below before it is shown to the reader.
_PROMPT_PATHSPECS = ("config/prompts", "config/domain.json")


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


def diverged_fields(baseline_manifest: dict, current: dict) -> list[str]:
    """Field NAMES where the baseline no longer matches the tree (pure).

    Separate from :func:`divergences` because ``--acknowledge`` decides on
    the set of names ("is prompt_templates_sha256 the only one?"), and
    re-deriving that by parsing formatted message strings is the kind of
    seam that breaks the moment someone edits the wording.
    """
    return [f for f in sorted(current) if baseline_manifest.get(f) != current[f]]


def divergences(baseline_manifest: dict, current: dict) -> list[str]:
    """Human-readable lines for the diverged fields (pure)."""
    return [
        f"{field}: baseline {baseline_manifest.get(field)!r} != current {current[field]!r}"
        for field in diverged_fields(baseline_manifest, current)
    ]


def newest_baseline(baselines_dir: Path) -> Path | None:
    # Face A only: a future post_golden-*.json family must not be compared
    # against the comment dataset this script hashes. The sidecar exclusion
    # covers the ORPHAN case: comment_golden-<date>.ack.json matches this
    # glob, and although it sorts before its own baseline ("a" < "j"), a
    # sidecar whose baseline was deleted or renamed while an older baseline
    # remains would sort last and be picked as a "baseline" with no manifest.
    candidates = sorted(
        p for p in baselines_dir.glob("comment_golden-*.json") if not p.name.endswith(".ack.json")
    )
    return candidates[-1] if candidates else None


def _git(*args: str) -> list[str] | None:
    """Run one read-only git command in the repo; None when git cannot answer."""
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, read-only
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line.strip()]


def changed_prompt_files(baseline_path: Path) -> tuple[str, ...] | None:
    """Prompt inputs that moved between the baseline's commit and the tree.

    The baseline records one combined digest, not a per-file map, so the
    file list cannot be recovered from the baseline itself — git is the only
    place that knows. Returns ``None`` (reported as "unknown") when git
    cannot answer or the baseline was never committed; an empty tuple would
    claim "nothing changed", which is a different and possibly false thing.

    Compared against the WORKING TREE, not HEAD: the digest that triggered
    the staleness report was computed from the working tree too, so an
    uncommitted prompt edit must appear in the list a human reads.
    """
    added = _git("log", "--diff-filter=A", "--format=%H", "-1", "--", str(baseline_path))
    if not added:
        return None
    changed = _git("diff", "--name-only", added[0], "--", *_PROMPT_PATHSPECS)
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *_PROMPT_PATHSPECS)
    if changed is None or untracked is None:
        return None

    hashed = {p.relative_to(REPO_ROOT).as_posix() for p in hashed_prompt_paths()}
    hashed.add("config/domain.json")

    def counts(rel: str) -> bool:
        # Kept when the file is a current digest input, or when it is gone
        # (deleted or renamed away — it may well have been one, and there is
        # no way left to ask). Over-inclusion is the safe direction: the
        # reader is deciding whether to trust an acknowledgement.
        return rel in hashed or not (REPO_ROOT / rel).exists()

    return tuple(sorted({rel for rel in [*changed, *untracked] if counts(rel)}))


def _say(line: str) -> None:
    print(f"[eval-staleness] {line}")


def _matching_ack(
    acks: tuple[Acknowledgement, ...], manifest: dict, current_hash: str
) -> Acknowledgement | None:
    """The newest acknowledgement of this digest *made against this baseline*.

    Both ends are checked: an entry recorded when the baseline held a
    different digest is a claim about a pair that no longer exists, so it
    does not excuse anything here (security review, 2026-09-19).
    """
    for ack in reversed(acks):
        if ack.acknowledged_hash == current_hash and ack.baseline_hash == manifest.get(
            PROMPT_FIELD
        ):
            return ack
    return None


def _acknowledge(
    baseline_path: Path,
    manifest: dict,
    current: dict,
    acks: tuple[Acknowledgement, ...],
    reason: str,
    dry_run: bool = False,
) -> int:
    """Record that a prompt-only divergence is out of the eval's scope.

    ``acks`` is passed in rather than re-read: main() already read the
    sidecar inside its cannot-check guard, and a second read here would be
    an AckError outside that guard, i.e. a traceback instead of exit 2.

    ``dry_run`` runs every check and prints the changed-file list without
    writing: the list is the evidence for the judgement, and a reader who
    wants to see it before committing to it should not have to undo a write.
    """
    fields = diverged_fields(manifest, current)
    if not fields:
        _say(f"baseline {baseline_path.name} is fresh — nothing to acknowledge")
        return 0

    already = _matching_ack(acks, manifest, current[PROMPT_FIELD])
    if fields == [PROMPT_FIELD] and already is not None:
        _say(
            f"this digest is already acknowledged ({already.date}, "
            f"reason: {already.reason}) — nothing to record"
        )
        return 0

    other = [f for f in fields if f != PROMPT_FIELD]
    if other:
        _say(
            "refusing to acknowledge: an acknowledgement only excuses "
            f"{PROMPT_FIELD}, and these fields diverge too:"
        )
        for field in other:
            _say(f"  {field}: baseline {manifest.get(field)!r} != current {current[field]!r}")
        _say("these name things a run would measure differently — re-run the eval instead")
        return 1

    baseline_hash = manifest.get(PROMPT_FIELD)
    if not isinstance(baseline_hash, str):
        # Nothing to bind the record's other end to. Stringifying None here
        # would write an entry that can never match again, i.e. a record
        # that looks like an excuse and is not one.
        _say(f"refusing to acknowledge: the baseline records no {PROMPT_FIELD} to bind to")
        return 1

    changed = changed_prompt_files(baseline_path)
    if changed is None:
        _say("changed prompt files: unknown (no git answer, or the baseline is not committed)")
    else:
        _say(f"prompt inputs changed since {baseline_path.name} was committed:")
        for rel in changed:
            _say(f"  {rel}")
    if dry_run:
        _say("--dry-run: nothing written. Re-run without it to record the acknowledgement")
        return 0
    entry = Acknowledgement(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        baseline_hash=baseline_hash,
        acknowledged_hash=current[PROMPT_FIELD],
        changed_prompt_files=changed,
        reason=reason,
    )
    written = append_acknowledgement(baseline_path, entry)
    _say(f"recorded in {written.name} (the baseline itself is unchanged)")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acknowledge",
        action="store_true",
        help="record that a prompt-only divergence cannot reach the comment path",
    )
    parser.add_argument("--reason", default="", help="why it cannot (required with --acknowledge)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --acknowledge: run the checks and print the changed files, write nothing",
    )
    args = parser.parse_args(argv)
    if args.dry_run and not args.acknowledge:
        parser.error("--dry-run only means something with --acknowledge")
    if args.acknowledge and not args.reason.strip():
        parser.error("--acknowledge requires --reason: the record is the point")
    if args.reason and not args.acknowledge:
        parser.error("--reason only means something with --acknowledge")
    return args


def _report_stale(baseline_path: Path, manifest: dict, current: dict, fields: list[str]) -> int:
    _say(f"baseline {baseline_path.name} is STALE — the regression gate")
    _say("no longer measures the current system (ADR-0089 re-run trigger):")
    for line in divergences(manifest, current):
        _say(f"  {line}")
    _say(
        "run: uv run --group eval python evals/run_eval.py "
        f"--baseline evals/baselines/{baseline_path.name}  (then re-approve)"
    )
    if fields == [PROMPT_FIELD]:
        _say(
            "or, if the edited templates cannot reach the comment path the eval "
            "measures, record that instead of re-running: "
            "uv run --group eval python evals/check_staleness.py --acknowledge "
            f'--reason "..."  (appends to {sidecar_path(baseline_path).name})'
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    baseline_path = newest_baseline(BASELINES_DIR)
    if baseline_path is None:
        _say("no approved baseline in evals/baselines/ — regression gate inactive")
        return 2
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict) or not isinstance(baseline.get("manifest"), dict):
            _say(f"cannot check: {baseline_path.name} has no manifest object")
            return 2
        current = current_state()
        acks = load_acknowledgements(baseline_path)
    except Exception as exc:  # any failure is "cannot check", never "stale"
        # AckError lands here too: a corrupted sidecar means we cannot say
        # whether the digest was cleared, and guessing "not cleared" would
        # print a STALE the reader has been taught to dismiss.
        _say(f"cannot check: {type(exc).__name__}: {exc}")
        return 2

    if args.acknowledge:
        return _acknowledge(
            baseline_path,
            baseline["manifest"],
            current,
            acks,
            args.reason.strip(),
            dry_run=args.dry_run,
        )

    fields = diverged_fields(baseline["manifest"], current)
    if fields == [PROMPT_FIELD]:
        ack = _matching_ack(acks, baseline["manifest"], current[PROMPT_FIELD])
        if ack is not None:
            _say(
                f"baseline {baseline_path.name}: {PROMPT_FIELD} matches by "
                f"acknowledgement, not by measurement ({ack.date}, "
                f"reason: {ack.reason})"
            )
            return 0
    if not fields:
        return 0
    return _report_stale(baseline_path, baseline["manifest"], current, fields)


if __name__ == "__main__":
    sys.exit(main())
