#!/usr/bin/env python3
"""Offline replay of the wiki loops over past episodes (RFC-0017 S4, D9).

Two arms, same shape and same window, so the only difference between them is
the model:

=================  =================  =============================
arm                model              window
=================  =================  =============================
``gemma``          gemma4:e4b         ``llm.NUM_CTX`` (the shipped loop)
``opus``           ``claude-opus-5``  ``llm.NUM_CTX``
=================  =================  =============================

A **diagnostic instrument, not a gate** (RFC-0022): the live audit log is what
D9's pass lines are read from, and this harness answers "what does a bigger
model do with the same day" — a reference point for reading the live numbers,
not a permission to go live. A one-shot instrument, not a production path (the
ADR-0075 2026-08-29 amendment). Replayability comes free anyway: the S2/S3
loops write their own audit JSONL — every prompt and every raw answer, base64 + sha256 — into the
replay home, so a later parser fix can be re-run against exactly what each
model said without spending a single call again.

**This never writes to the production home.** Each arm gets a fresh directory
under ``--home`` (which has no default and is refused if it is inside the
production store), and the episode logs, skill store and ledgers are *copied*
into it. The wiki, the proposals and the audit rows all accumulate there.

``summary.json`` carries the same material D9's pass lines are read from —
call counts, verification pass rate, the op-class breakdown, what the Proposer
proposed and at what, daily wiki size and batch counts, wall clock and (Claude
arm) token usage and cost. It does NOT judge, and it decides nothing: the
pass lines belong to the live audit log, read at the Saturday gate.

Usage::

    python scripts/wiki_replay.py --home /tmp/replay \\
        --from 2026-07-09 --to 2026-08-29 --arm gemma --arm opus

Add ``--days N`` to truncate the range (smoke runs). The gemma arm occupies
Ollama for hours, so keep the full run outside the JST 0/6/12/18 session
windows (RFC-0017 D9).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contemplative_agent.core import llm  # noqa: E402
from contemplative_agent.core.wiki import render_index  # noqa: E402
from contemplative_agent.core.wiki_maintainer import (  # noqa: E402
    MAINTAINER_LOG_NAME,
    MaintainerConfig,
    MaintainerRun,
    read_wiki_size,
    run_maintainer,
)
from contemplative_agent.core.wiki_proposer import (  # noqa: E402
    PROPOSER_LOG_NAME,
    ProposerConfig,
    ProposerRun,
    run_proposer,
)
from contemplative_agent.testing.claude_cli import ClaudeCliBackend  # noqa: E402

CLAUDE_MODEL = "claude-opus-5"
REPLAY_WINDOW = llm.NUM_CTX

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# What is copied into an arm's home. Directories are copied whole; the dated
# episode logs are copied per replayed day (a 52-day range is all of them, but
# a smoke run should not pay for the rest).
_COPIED_LEDGERS = ("insight-staged.jsonl", "audit.jsonl")
_COPIED_LOG_GLOBS = ("skill-selection-*.jsonl",)

# Deviations from the paper and from live that the reading has to carry with
# it. Written into every summary.json rather than left in a commit message,
# because the summary is what a later reader will have
# (measurement-discipline: a number without its window is not a reading).
# The parenthesis names the RFC-0017 D7 row each one belongs to, or marks it
# as this harness's own.
REPLAY_DEVIATIONS = (
    "skill store is the store as of the replay date's run, not as it stood "
    "on the replayed day (harness-specific: the store's own history is not "
    "reconstructed)",
    "the evolution log's `final decision` and `superseded by` columns come "
    "from the whole ledger; only the staging date is windowed by `until` "
    "(harness-specific)",
    "the Claude arm has no constrained decoding — the per-turn JSON Schema "
    "is an instruction in the prompt, so a schema violation costs the turn as "
    "fail_closed_parse instead of being impossible (harness-specific)",
    "the Claude arm has no output-token cap (`num_predict` has no CLI "
    "counterpart), so it cannot produce fail_closed_truncated "
    "(harness-specific)",
    "the wiki index sits above the full page bodies in every Maintainer "
    "prompt; there is one shape, and the index is its table of contents "
    "rather than a retrieval step (D7 (3))",
    "no fuel: the paper's loop is driven by a verification score against "
    "ground truth, and CA has neither the score nor its inputs — recurrence "
    "across days and the human gate stand in for it (D7 (0))",
    "the Maintainer reads the whole day in batches, not the paper's "
    "stratified sample of at most 8 traces (D7 (5))",
    "the Proposer cannot open a raw episode; the paper's Proposer must read "
    "at least four traces (D7 (7))",
    "Maintainer daily, Proposer run by hand — not the paper's 1:1 pairing "
    "inside one iteration (D7 (4))",
)


@dataclass(frozen=True)
class Arm:
    """One arm's model. Everything else is the shared loop, unchanged."""

    name: str
    model: str
    context_window: int
    uses_claude: bool

    def maintainer_config(self) -> MaintainerConfig:
        return MaintainerConfig(context_window=self.context_window)

    def proposer_config(self) -> ProposerConfig:
        return ProposerConfig(context_window=self.context_window)


ARMS: dict[str, Arm] = {
    "gemma": Arm(
        name="gemma",
        model="",  # whatever OLLAMA_MODEL serves; recorded from llm.served_model()
        context_window=REPLAY_WINDOW,
        uses_claude=False,
    ),
    "opus": Arm(
        name="opus",
        model=CLAUDE_MODEL,
        context_window=REPLAY_WINDOW,
        uses_claude=True,
    ),
}


# ------------------------------------------------------------------- the home


def default_source() -> Path:
    """The production store the replay copies FROM. Never written to."""
    import os

    return Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))


def days_in_range(start: date, end: date, limit: int | None) -> list[date]:
    """Every day from *start* to *end* inclusive, truncated to *limit*."""
    if end < start:
        return []
    span = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return span[:limit] if limit is not None else span


def prepare_arm_home(source: Path, arm_root: Path, days: list[date]) -> dict[str, int]:
    """Copy what the loops read into a fresh arm directory.

    Copied, never symlinked: the Maintainer's store writes into ``wiki/`` next
    to these files, and a link would put an arm one bug away from the
    production home. Missing inputs are counted, not fatal — a replay over a
    day whose log is absent is a shorter replay, and the count says so.
    """
    logs = arm_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (arm_root / "wiki").mkdir(parents=True, exist_ok=True)

    copied = {"episode_days": 0, "missing_days": 0, "ledgers": 0, "selection_logs": 0}
    for day in days:
        name = f"{day.isoformat()}.jsonl"
        src = source / "logs" / name
        if not src.is_file():
            copied["missing_days"] += 1
            continue
        shutil.copy2(src, logs / name)
        copied["episode_days"] += 1
    for name in _COPIED_LEDGERS:
        src = source / "logs" / name
        if src.is_file():
            shutil.copy2(src, logs / name)
            copied["ledgers"] += 1
    for pattern in _COPIED_LOG_GLOBS:
        for src in sorted((source / "logs").glob(pattern)):
            shutil.copy2(src, logs / src.name)
            copied["selection_logs"] += 1

    skills_src = source / "skills"
    if skills_src.is_dir():
        shutil.copytree(skills_src, arm_root / "skills", dirs_exist_ok=True)
    else:
        (arm_root / "skills").mkdir(parents=True, exist_ok=True)
    return copied


def refuse_production_home(home: Path, source: Path) -> str | None:
    """The reason *home* must not be used, or ``None``.

    A replay that writes into the production store would contaminate the very
    logs the experiment reads, and it would do it silently. Checked on
    resolved paths, not spellings.
    """
    home = home.resolve()
    source = source.resolve()
    if home == source or source in home.parents or home in source.parents:
        return f"--home {home} overlaps the production store {source}"
    return None


# ------------------------------------------------------------------ the arms


def configure_arm(arm: Arm, arm_root: Path, *, backend_override: object = None) -> object:
    """Point ``core.llm`` at this arm's model. Returns the backend, if any.

    ``backend_override`` exists so a test can drive a whole arm without
    spawning anything. It is a parameter rather than an env var because the
    default must be the real thing: a harness that reaches the network only
    when a variable is unset is one forgotten export away from a silent
    no-op run, and this arm's whole output is what the model said.
    """
    llm.reset_llm_config()
    backend = backend_override
    if backend is None and arm.uses_claude:
        backend = ClaudeCliBackend(
            model=arm.model,
            scratch_dir=arm_root / "scratch",
            context_window=arm.context_window,
            audit_path=arm_root / "logs" / "claude-cli-audit.jsonl",
        )
    llm.configure(backend=backend, telemetry_dir=arm_root / "logs")  # type: ignore[arg-type]
    return backend


_WRITE_VERBS = frozenset({"create", "append", "replace", "insert_after"})


@dataclass
class ArmTally:
    """Everything ``summary.json`` reports, accumulated as the arm runs."""

    maintainer_outcomes: dict[str, int] = field(default_factory=dict)
    proposer_outcomes: dict[str, int] = field(default_factory=dict)
    op_classes: dict[str, int] = field(default_factory=dict)
    ops_applied: int = 0
    ops_refused: int = 0
    refusal_reasons: dict[str, int] = field(default_factory=dict)
    proposal_targets: list[str] = field(default_factory=list)
    proposal_kinds: dict[str, int] = field(default_factory=dict)
    wiki_daily: list[dict[str, Any]] = field(default_factory=list)

    def add_maintainer(self, run: MaintainerRun) -> None:
        _bump(self.maintainer_outcomes, run.outcome)
        for entry in run.ops_applied:
            self.ops_applied += 1
            _bump(self.op_classes, entry.split(" ", 1)[0])
        for op_name, reason in run.ops_refused:
            # Every refusal keeps its own breakdown line, but only the write
            # verbs count toward M-a: an open the model aimed at a page id
            # that does not exist, or an action the turn never offered, is a
            # hallucination reading — not an op the store declined to apply.
            _bump(self.refusal_reasons, f"{op_name}:{reason}")
            if op_name in _WRITE_VERBS:
                self.ops_refused += 1
        self.wiki_daily.append(
            {
                "date": run.date,
                "outcome": run.outcome,
                "batches": len(run.batches),
                "episodes_read": len(run.episode_ids_read),
                "pages": run.wiki_size.pages,
                "index_tokens": run.wiki_size.index_tokens,
                "page_chars_p90": run.wiki_size.page_chars_p90,
                "episode_budget": run.budget.get("episodes"),
            }
        )

    def add_proposer(self, run: ProposerRun) -> None:
        _bump(self.proposer_outcomes, run.outcome)
        if run.proposal is not None:
            _bump(self.proposal_kinds, run.proposal.kind)
            self.proposal_targets.append(run.proposal.target or run.proposal.name)


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def count_turns(path: Path) -> int:
    """LLM calls, counted from the audit rows the loop itself wrote.

    Derived from the replay artefact rather than from a counter in this
    script, so the number in the summary and the rows a reader can inspect
    cannot disagree.
    """
    if not path.is_file():
        return 0
    turns = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("kind") == "turn":
            turns += 1
    return turns


def run_arm(
    arm: Arm,
    *,
    source: Path,
    home: Path,
    days: list[date],
    proposer_weekday: int,
    verbose: bool = True,
    backend_override: object = None,
) -> dict[str, Any]:
    """Replay every day for one arm and return its summary block."""
    arm_root = home / arm.name
    copied = prepare_arm_home(source, arm_root, days)
    backend = configure_arm(arm, arm_root, backend_override=backend_override)
    served = arm.model or llm.served_model()

    tally = ArmTally()
    started = time.monotonic()
    for day in days:
        maintainer = run_maintainer(
            data_root=arm_root,
            wiki_dir=arm_root / "wiki",
            day=day,
            config=arm.maintainer_config(),
        )
        tally.add_maintainer(maintainer)
        if verbose:
            print(f"[{arm.name}] {day} maintainer: {maintainer.outcome}", flush=True)
        if day.weekday() != proposer_weekday:
            continue
        proposer = run_proposer(
            data_root=arm_root,
            wiki_dir=arm_root / "wiki",
            skills_dir=arm_root / "skills",
            today=day,
            config=arm.proposer_config(),
        )
        tally.add_proposer(proposer)
        if verbose:
            print(f"[{arm.name}] {day} proposer:   {proposer.outcome}", flush=True)

    elapsed = time.monotonic() - started
    summary = build_summary(
        arm,
        served_model=served,
        days=days,
        copied=copied,
        tally=tally,
        arm_root=arm_root,
        elapsed=elapsed,
        usage=backend.usage.as_dict() if isinstance(backend, ClaudeCliBackend) else None,
    )
    (arm_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    llm.reset_llm_config()
    return summary


def build_summary(
    arm: Arm,
    *,
    served_model: str,
    days: list[date],
    copied: dict[str, int],
    tally: ArmTally,
    arm_root: Path,
    elapsed: float,
    usage: dict[str, Any] | None,
) -> dict[str, Any]:
    """The D9 material, computed but never judged.

    Two ratios are pre-computed because both are trivially mis-derived by
    hand: ``verification_pass_rate`` is M-a's denominator (every op the model
    emitted, applied or refused — NOT the runs), and ``patch_ratio`` is M-b's
    (the three editing verbs over all four, so "creates only" reads as 0.0).
    Both are ``None`` when nothing was emitted, never 0.0: no evidence and a
    failing score are different readings, and 0.0 would collapse them.
    """
    ops_total = tally.ops_applied + tally.ops_refused
    patches = sum(tally.op_classes.get(name, 0) for name in ("append", "replace", "insert_after"))
    creates = tally.op_classes.get("create", 0)
    wiki_dir = arm_root / "wiki"
    final_size = read_wiki_size(wiki_dir, render_index(wiki_dir))
    return {
        "arm": arm.name,
        "model": served_model,
        "context_window": arm.context_window,
        "from": days[0].isoformat() if days else None,
        "to": days[-1].isoformat() if days else None,
        "days": len(days),
        "inputs_copied": copied,
        "elapsed_seconds": round(elapsed, 1),
        "usage": usage,
        "maintainer": {
            "runs": sum(tally.maintainer_outcomes.values()),
            "llm_calls": count_turns(arm_root / "logs" / MAINTAINER_LOG_NAME),
            "outcomes": dict(sorted(tally.maintainer_outcomes.items())),
            "ops_total": ops_total,
            "ops_applied": tally.ops_applied,
            "ops_refused": tally.ops_refused,
            # M-a
            "verification_pass_rate": (
                round(tally.ops_applied / ops_total, 4) if ops_total else None
            ),
            "op_classes": dict(sorted(tally.op_classes.items())),
            # M-b
            "patch_ratio": (
                round(patches / (patches + creates), 4) if (patches + creates) else None
            ),
            "refusal_reasons": dict(sorted(tally.refusal_reasons.items())),
        },
        "proposer": {
            "runs": sum(tally.proposer_outcomes.values()),
            "llm_calls": count_turns(arm_root / "logs" / PROPOSER_LOG_NAME),
            "outcomes": dict(sorted(tally.proposer_outcomes.items())),
            "kinds": dict(sorted(tally.proposal_kinds.items())),
            # P-a is `kinds["patch"] >= 1`; P-b is read by a person from these.
            "targets": list(tally.proposal_targets),
        },
        "wiki_daily": tally.wiki_daily,
        "wiki_final": {
            "pages": final_size.pages,
            "index_tokens": final_size.index_tokens,
            "page_chars_p90": final_size.page_chars_p90,
        },
        "deviations": list(REPLAY_DEVIATIONS),
    }


# -------------------------------------------------------------------- the CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--home",
        required=True,
        type=Path,
        help="Replay root. Required, no default: each arm gets <home>/<arm>/.",
    )
    parser.add_argument("--source", type=Path, default=None, help="Store to copy from (read-only)")
    parser.add_argument("--from", dest="start", required=True, help="First day (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", required=True, help="Last day, inclusive")
    parser.add_argument(
        "--arm",
        action="append",
        dest="arms",
        choices=sorted(ARMS),
        help="Repeatable. Default: both.",
    )
    parser.add_argument("--days", type=int, default=None, help="Truncate the range (smoke runs)")
    parser.add_argument(
        "--proposer-weekday", choices=WEEKDAYS, default="monday", help="Default monday"
    )
    parser.add_argument("--quiet", action="store_true", help="No per-day progress lines")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source = args.source or default_source()
    refusal = refuse_production_home(args.home, source)
    if refusal is not None:
        parser.error(refusal)

    try:
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    except ValueError as exc:
        parser.error(f"bad date: {exc}")
    days = days_in_range(start, end, args.days)
    if not days:
        parser.error("empty date range")

    args.home.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name in args.arms or sorted(ARMS):
        summaries.append(
            run_arm(
                ARMS[name],
                source=source,
                home=args.home,
                days=days,
                proposer_weekday=WEEKDAYS.index(args.proposer_weekday),
                verbose=not args.quiet,
            )
        )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
