"""Session subcommands: init / report / meditate / dialogue / sync-data.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import json as json_mod
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..core.domain import (
    DEFAULT_CONFIG_DIR,
)
from . import memory_cmds, runtime
from .registry import CommandSpec, Tier, no_arguments

logger = logging.getLogger(__name__)


def _run_sync() -> None:
    """Run research data sync script (best-effort)."""
    script = runtime._repo_root() / "scripts" / "sync-research-data.sh"
    if not script.exists():
        return
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        if result.stdout.strip():
            print(result.stdout.strip())
    else:
        print(f"Warning: sync failed: {result.stderr.strip()}", file=sys.stderr)


def _list_templates() -> list[str]:
    """Return sorted list of available template names."""
    templates_dir = DEFAULT_CONFIG_DIR / "templates"
    if not templates_dir.is_dir():
        return []
    return sorted(
        d.name for d in templates_dir.iterdir() if d.is_dir() and (d / "identity.md").exists()
    )


def _do_init(template_name: str = "contemplative") -> None:
    """Initialize runtime data files in MOLTBOOK_HOME."""
    import shutil

    def copy_or_create_dir(src: Path, dst: Path, label: str, provenance: str = "") -> None:
        if dst.exists():
            print(f"{label} already exists: {dst}")
        elif src.is_dir():
            shutil.copytree(src, dst)
            print(f"Copied {label.lower()}: {dst}{provenance}")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            print(f"Created empty {label.lower()} dir: {dst}")

    templates_dir = DEFAULT_CONFIG_DIR / "templates"
    template_dir = templates_dir / template_name
    if not template_dir.is_dir():
        available = ", ".join(_list_templates())
        print(f"Unknown template: {template_name}", file=sys.stderr)
        print(f"Available templates: {available}", file=sys.stderr)
        sys.exit(1)

    config.MOLTBOOK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Identity
    src_identity = template_dir / "identity.md"
    if config.IDENTITY_PATH.exists():
        print(f"Identity file already exists: {config.IDENTITY_PATH}")
    elif src_identity.exists():
        config.IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_identity, config.IDENTITY_PATH)
        os.chmod(config.IDENTITY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created identity file: {config.IDENTITY_PATH} (from {template_name})")

    # Knowledge (always empty, not template-specific)
    if config.KNOWLEDGE_PATH.exists():
        print(f"Knowledge file already exists: {config.KNOWLEDGE_PATH}")
    else:
        config.KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.KNOWLEDGE_PATH.write_text(
            json_mod.dumps([], ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.chmod(config.KNOWLEDGE_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created knowledge file: {config.KNOWLEDGE_PATH}")

    # Copy directories from template (constitution, skills, rules)
    template_suffix = f" (from {template_name})"
    for src_dir, dst_dir, label in [
        (template_dir / "constitution", config.CONSTITUTION_DIR, "Constitution"),
        (template_dir / "skills", config.SKILLS_DIR, "Skills"),
        (template_dir / "rules", config.RULES_DIR, "Rules"),
    ]:
        copy_or_create_dir(src_dir, dst_dir, label, template_suffix)

    # Copy shared runtime dirs (not template-specific) so the user owns
    # every Markdown file the agent consults at runtime. Edits here
    # surface via git-diff against config/ and are captured in pivot
    # snapshots for replayability.
    for src_dir, dst_dir, label in [
        (DEFAULT_CONFIG_DIR / "prompts", config.PROMPTS_DIR, "Prompts"),
        (DEFAULT_CONFIG_DIR / "views", config.VIEWS_DIR, "Views"),
    ]:
        copy_or_create_dir(src_dir, dst_dir, label)


def _handle_sync_data(_args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    _run_sync()


def _handle_init(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    _do_init(template_name=args.template)


def _handle_report(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.memory import EpisodeLog
    from ..core.metrics import compute_metrics, format_report

    log_dir = config.MOLTBOOK_DATA_DIR / "logs"
    episode_log = EpisodeLog(log_dir=log_dir)
    report = compute_metrics(episode_log, days=args.days)
    print(format_report(report, fmt=args.format))

    # --patterns: read-only pattern-composition instruments (view_metrics).
    # Costs two seed embeddings via Ollama; everything else reads stored
    # pattern embeddings. Observability only — never wired into gates.
    if getattr(args, "patterns", False):
        from ..core.memory import KnowledgeStore
        from ..core.view_metrics import format_pattern_report

        knowledge_store = KnowledgeStore(path=config.KNOWLEDGE_PATH)
        knowledge_store.load()
        view_registry = memory_cmds._load_view_registry(args)
        print()
        print(
            format_pattern_report(
                knowledge_store.get_live_patterns(),
                view_registry,
            )
        )

    # --skill-selection: read-only shadow-selection reading (ADR-0076).
    # Aggregates logs/skill-selection-*.jsonl; observability only — a broken
    # instrument degrades to a WARNING and never breaks the report.
    if getattr(args, "skill_selection", False):
        try:
            from ..core.skill_selection import (
                format_skill_selection_report,
                read_skill_selection_log,
            )

            reading = read_skill_selection_log(
                log_dir,
                days=args.days,
                skills_dir=config.SKILLS_DIR if config.SKILLS_DIR.is_dir() else None,
            )
            print()
            print(format_skill_selection_report(reading))
        except Exception as exc:
            logger.warning("Skill-selection reading failed (report unaffected): %s", exc)

    # --submolt-scope: read-only scope reading (ADR-0086). Aggregates
    # logs/submolt-scope-*.jsonl written by `submolt-scan`; observability
    # only — wired to no gate, and a broken reading never breaks the report.
    if getattr(args, "submolt_scope", False):
        try:
            from ..adapters.moltbook.submolt_scope import (
                format_submolt_scope_report,
                read_submolt_scope_log,
            )
            from ..core.domain import get_domain_config

            domain = get_domain_config()
            # Group by the CURRENT subscribed set, not the label each record
            # carried when its scan ran: the operator is deciding about the
            # scope as it stands today (codex review 2026-08-01).
            reading = read_submolt_scope_log(
                log_dir,
                days=args.days,
                threshold=domain.relevance_threshold,
                subscribed=domain.subscribed_submolts,
            )
            print()
            print(format_submolt_scope_report(reading))
        except Exception as exc:
            logger.warning("Submolt-scope reading failed (report unaffected): %s", exc)


def _handle_generate_report(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..core.report import generate_all_reports, generate_report

    log_dir = config.MOLTBOOK_DATA_DIR / "logs"
    output_dir = config.REPORTS_DIR

    if args.all_dates:
        results = generate_all_reports(log_dir, output_dir)
        print(f"Generated {len(results)} reports in {output_dir}")
    else:
        result = generate_report(log_dir, output_dir, date=args.date)
        if result:
            print(f"Report generated: {result}")
        else:
            print("No log data found for the specified date.")


def _handle_meditate(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from ..adapters.meditation.config import MeditationConfig
    from ..adapters.meditation.meditate import meditate as run_meditate
    from ..adapters.meditation.pomdp import build_matrices
    from ..adapters.meditation.report import interpret_and_save
    from ..core.memory import EpisodeLog

    log_dir = config.MOLTBOOK_DATA_DIR / "logs"
    episode_log = EpisodeLog(log_dir=log_dir)
    results_path = config.MEDITATION_DIR / "results.json"

    meditation_config = MeditationConfig(meditation_cycles=args.cycles)
    matrices = build_matrices(episode_log, days=args.days, config=meditation_config)
    result = run_meditate(matrices, config=meditation_config)
    output = interpret_and_save(
        result,
        results_path,
        dry_run=args.dry_run,
    )
    print(output)


_PRODUCTION_HOME = config.DEFAULT_MOLTBOOK_HOME.resolve()


_SHUTDOWN_GRACE_SECONDS = 5


def _spawn_dialogue_peer(
    *,
    home: Path,
    turns: int,
    stdin_fd: int,
    stdout_fd: int,
    seed: str | None = None,
) -> subprocess.Popen:
    # CONTEMPLATIVE_DIALOGUE_PEER_MODULE lets an outer wrapper (e.g. a
    # managed-LLM shim) route peers through its own entry module so the
    # wrapper's setup (like a configured LLM backend) runs in each peer
    # process too. Default keeps the built-in path unchanged.
    peer_module = os.environ.get(
        "CONTEMPLATIVE_DIALOGUE_PEER_MODULE",
        "contemplative_agent.cli",
    )
    cmd = [
        sys.executable,
        "-u",
        "-m",
        peer_module,
        "dialogue-peer",
        "--turns",
        str(turns),
        "--label",
        home.name,
    ]
    if seed is not None:
        cmd += ["--seed", seed]
    env = {**os.environ, "MOLTBOOK_HOME": str(home)}
    return subprocess.Popen(
        cmd,
        stdin=stdin_fd,
        stdout=stdout_fd,
        env=env,
        close_fds=True,
    )


def _stop_peer(proc: subprocess.Popen) -> int:
    """Terminate a peer gracefully; escalate to SIGKILL if it ignores SIGTERM."""
    proc.terminate()
    try:
        return proc.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait()


def _handle_dialogue(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Spawn two peer subprocesses with bidirectional pipes and wait for them.

    Each peer inherits a distinct MOLTBOOK_HOME so their episode logs stay
    separate — production (~/.config/moltbook) is never touched.
    """
    if args.turns < 1:
        runtime._exit_with("--turns must be >= 1")
    if not args.seed.strip():
        runtime._exit_with("--seed must be a non-empty string")

    home_a = args.home_a.expanduser().resolve()
    home_b = args.home_b.expanduser().resolve()
    for home, label in [(home_a, "HOME_A"), (home_b, "HOME_B")]:
        if home == _PRODUCTION_HOME or _PRODUCTION_HOME in home.parents:
            runtime._exit_with(
                f"{label} ({home}) overlaps with production (~/.config/moltbook); "
                "pick a different MOLTBOOK_HOME for the dialogue sandbox."
            )
        if not home.is_dir():
            runtime._exit_with(
                f"{label} ({home}) does not exist — initialise first with "
                f"'MOLTBOOK_HOME={home} contemplative-agent init'"
            )
        if not (home / "identity.md").is_file():
            runtime._exit_with(
                f"{label} ({home}) has no identity.md — initialise with "
                f"'MOLTBOOK_HOME={home} contemplative-agent init'"
            )

    a_to_b_r, a_to_b_w = os.pipe()
    b_to_a_r, b_to_a_w = os.pipe()

    proc_a = _spawn_dialogue_peer(
        home=home_a,
        turns=args.turns,
        stdin_fd=b_to_a_r,
        stdout_fd=a_to_b_w,
        seed=args.seed,
    )
    proc_b = _spawn_dialogue_peer(
        home=home_b,
        turns=args.turns,
        stdin_fd=a_to_b_r,
        stdout_fd=b_to_a_w,
        seed=None,
    )
    # Parent releases its pipe ends so EOF propagates when a peer exits.
    for fd in (a_to_b_r, a_to_b_w, b_to_a_r, b_to_a_w):
        os.close(fd)

    try:
        rc_a = proc_a.wait()
        rc_b = proc_b.wait()
    except KeyboardInterrupt:
        rc_a = _stop_peer(proc_a)
        rc_b = _stop_peer(proc_b)

    if rc_a != 0 or rc_b != 0:
        logger.warning("dialogue peers exited with codes a=%d b=%d", rc_a, rc_b)
        sys.exit(1)


def _handle_dialogue_peer(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Run one peer's dialogue loop against stdin/stdout.

    LLM and domain are already configured by ``_configure_llm_and_domain``
    (tier-2 dispatch). This handler only has to wire an EpisodeLog rooted at
    the current MOLTBOOK_HOME and drive the loop.
    """
    from ..adapters.dialogue.peer import run_peer_loop
    from ..core.episode_log import EpisodeLog

    episode_log = EpisodeLog(log_dir=config.EPISODE_LOG_DIR)
    replies = run_peer_loop(
        episode_log=episode_log,
        peer_in=sys.stdin,
        peer_out=sys.stdout,
        max_turns=args.turns,
        seed=args.seed,
        label=args.label,
    )
    # Bug-audit 2026-07-06 M10: a dialogue cut short (peer EOF / broken pipe
    # after fewer than the requested turns) previously exited 0, so the
    # parent's rc gate reported a truncated dialogue as a clean full run.
    # Exit nonzero on shortfall; _handle_dialogue already fails on rc != 0.
    if replies < args.turns:
        logger.warning(
            "dialogue peer %s generated %d of %d requested replies (dialogue truncated)",
            args.label,
            replies,
            args.turns,
        )
        sys.exit(2)


def _add_init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--template",
        type=str,
        default="contemplative",
        help="Character template to use (default: contemplative)",
    )


def _add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument(
        "--format",
        choices=["text", "md"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--patterns",
        action="store_true",
        help="Append read-only knowledge-pattern composition instruments "
        "(consumed-view supply / diversity)",
    )
    parser.add_argument(
        "--skill-selection",
        action="store_true",
        help="Append the read-only skill-selection shadow reading "
        "(per-skill frequency, never-selected, would-be token reduction; "
        "ADR-0076)",
    )
    parser.add_argument(
        "--submolt-scope",
        action="store_true",
        help="Append the read-only submolt-scope reading — subscribed vs "
        "unsubscribed hit rates from `submolt-scan` sweeps (ADR-0086)",
    )


def _add_generate_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to generate report for (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_dates",
        help="Generate reports for all available log dates",
    )


def _add_meditate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days of episodes to build POMDP from (default: 7)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=50,
        help="Number of meditation cycles (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show results without writing to knowledge store",
    )


def _add_dialogue_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "home_a",
        type=Path,
        help="MOLTBOOK_HOME for agent A (initiator). Must be pre-initialised.",
    )
    parser.add_argument(
        "home_b",
        type=Path,
        help="MOLTBOOK_HOME for agent B (responder). Must be pre-initialised.",
    )
    parser.add_argument(
        "--seed",
        type=str,
        required=True,
        help="Opening message from agent A that starts the dialogue",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Max reply turns per side (hard cap, default: 5)",
    )


def _add_dialogue_peer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--turns",
        type=int,
        required=True,
        help="Max reply turns this peer will generate",
    )
    parser.add_argument(
        "--seed",
        type=str,
        default=None,
        help="Opening message if this peer is the initiator",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="peer",
        help="Short label for stderr traces",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="init",
        help="Initialize identity and knowledge files",
        handler=_handle_init,
        tier=Tier.LLM_FULL,
        add_arguments=_add_init_arguments,
    ),
    CommandSpec(
        name="report",
        help="Show self-improvement metrics from episode logs",
        handler=_handle_report,
        tier=Tier.LLM_FULL,
        add_arguments=_add_report_arguments,
    ),
    CommandSpec(
        name="generate-report",
        help="Generate activity report from episode logs",
        handler=_handle_generate_report,
        tier=Tier.LLM_FULL,
        add_arguments=_add_generate_report_arguments,
    ),
    CommandSpec(
        name="meditate",
        help="Run active inference meditation on episode history",
        handler=_handle_meditate,
        tier=Tier.LLM_FULL,
        add_arguments=_add_meditate_arguments,
    ),
    CommandSpec(
        name="sync-data",
        help="Sync research data to external git repository",
        handler=_handle_sync_data,
        tier=Tier.NO_LLM,
        add_arguments=no_arguments,
    ),
    # dialogue spawns two peer agents (each rooted at a different
    # MOLTBOOK_HOME) and pipes them together; it needs no LLM of its own.
    CommandSpec(
        name="dialogue",
        help="Run a local dialogue between two agent instances (two MOLTBOOK_HOMEs)",
        handler=_handle_dialogue,
        tier=Tier.NO_LLM,
        add_arguments=_add_dialogue_arguments,
    ),
    # Internal entry for each peer subprocess: reads JSON line messages from
    # stdin, writes replies to stdout. Spawned by `dialogue`, not by users —
    # hence a different tier from `dialogue` despite the shared module.
    CommandSpec(
        name="dialogue-peer",
        help="(internal) one side of a dialogue — spawned by 'dialogue'",
        handler=_handle_dialogue_peer,
        tier=Tier.LLM_FULL,
        add_arguments=_add_dialogue_peer_arguments,
    ),
)
