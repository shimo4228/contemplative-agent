"""Commands that need a live ``Agent`` instance.

Previously these four lived as an ``if/elif`` chain inside ``_handle_agent_command``
in ``cli/__init__.py``, reached by falling through both dispatch tables — so an
unregistered command name silently constructed an Agent instead of erroring.
They are ordinary registered commands now; the Agent-tier wiring is what they
share, not a catch-all branch.
"""

from __future__ import annotations

import argparse

from ..adapters.moltbook import config
from ..adapters.moltbook.agent import Agent
from ..adapters.moltbook.submolt_scope import DEFAULT_SAMPLE_SIZE
from ..core._io import acquire_run_lock
from ..core.domain import DomainConfig, get_domain_config
from ..core.run_context import new_session_id, set_session_id
from .registry import CommandSpec, Tier, no_arguments
from .runtime import _llm_session_meta


def _build_agent(args: argparse.Namespace, domain_config: DomainConfig | None) -> Agent:
    return Agent(autonomy=args.autonomy, domain_config=domain_config)


def _handle_register(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    result = _build_agent(args, domain_config).do_register()
    print(f"Registration result: {result}")


def _handle_status(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    result = _build_agent(args, domain_config).do_status()
    print(f"Agent status: {result}")


def _handle_solve(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    _build_agent(args, domain_config).do_solve(args.text)


def _handle_submolt_scan(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    # 100 = five feed pages' worth per submolt. Above that a single sweep's
    # local LLM cost stops being weekly-job shaped, and the platform serves
    # 20 posts per page anyway, so the extra calls would mostly re-score the
    # same page.
    if args.sample_size <= 0 or args.sample_size > 100:
        parser.error("--sample-size must be between 1 and 100")
    agent = _build_agent(args, domain_config)
    # The sweep spends the same GET budget a session does, so it takes the
    # same lock: two processes reading concurrently would double-spend the
    # rate budget and the scan would starve the session it must not disturb.
    with acquire_run_lock(config.RUN_LOCK_PATH, blocking=False) as acquired:
        if not acquired:
            print(
                f"Another run/distill process holds the run lock ({config.RUN_LOCK_PATH}); exiting."
            )
            return
        result = agent.do_submolt_scan(args.sample_size)
    print(
        f"Submolt scope scan {result.verdict}: {len(result.scanned)} submolts sampled "
        f"of {result.discovered} listed, {result.scored} posts scored"
    )
    for name, reason in result.skipped:
        print(f"  skipped {name}: {reason}")
    if result.verdict == "disabled":
        print("Instrument disabled — no audit dir configured (ADR-0086 kill switch).")
    print("Read it with: contemplative-agent report --days 30 --submolt-scope")


def _handle_run(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    if args.session <= 0 or args.session > 1440:
        parser.error("--session must be between 1 and 1440 minutes")
    agent = _build_agent(args, domain_config)
    dc = domain_config or get_domain_config()
    # Session identity (ADR-0078 follow-up): every audit record written
    # while this session runs carries session_id via the shared writer.
    # Cleared in finally — a same-process caller (tests, embedding) must
    # not have later non-session writes stamped with a stale session_id.
    session_id = new_session_id()
    set_session_id(session_id)
    session_meta = {
        "axioms_enabled": not args.no_axioms,
        "domain": dc.name,
        "session_id": session_id,
        **_llm_session_meta(),
    }
    try:
        # Non-blocking lock (audit M5): a second concurrent session would
        # double-spend rate budgets and race knowledge.json — fail fast
        # with a clear message instead of queueing behind it.
        with acquire_run_lock(config.RUN_LOCK_PATH, blocking=False) as acquired:
            if not acquired:
                print(
                    f"Another run/distill process holds the run lock ({config.RUN_LOCK_PATH}); exiting."
                )
                return
            agent.run_session(duration_minutes=args.session, session_meta=session_meta)
    finally:
        set_session_id(None)


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes (default: 60)",
    )


def _add_solve_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", help="Obfuscated challenge text")


def _add_submolt_scan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Posts sampled per submolt (default: {DEFAULT_SAMPLE_SIZE})",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="register",
        help="Register a new agent on Moltbook",
        handler=_handle_register,
        tier=Tier.AGENT,
        add_arguments=no_arguments,
    ),
    CommandSpec(
        name="status",
        help="Check agent status",
        handler=_handle_status,
        tier=Tier.AGENT,
        add_arguments=no_arguments,
    ),
    CommandSpec(
        name="run",
        help="Run autonomous session",
        handler=_handle_run,
        tier=Tier.AGENT,
        add_arguments=_add_run_arguments,
    ),
    CommandSpec(
        name="solve",
        help="Test verification solver",
        handler=_handle_solve,
        tier=Tier.AGENT,
        add_arguments=_add_solve_arguments,
    ),
    CommandSpec(
        name="submolt-scan",
        help="Read-only submolt-scope sweep (ADR-0086 instrument; changes nothing)",
        handler=_handle_submolt_scan,
        tier=Tier.AGENT,
        add_arguments=_add_submolt_scan_arguments,
    ),
)
