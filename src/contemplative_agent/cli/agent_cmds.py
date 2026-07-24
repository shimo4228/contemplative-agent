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
)
