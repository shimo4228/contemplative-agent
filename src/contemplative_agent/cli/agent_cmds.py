"""Commands that need a live ``Agent`` instance.

Previously these four lived as an ``if/elif`` chain inside ``_handle_agent_command``
in ``cli/__init__.py``, reached by falling through both dispatch tables — so an
unregistered command name silently constructed an Agent instead of erroring.
They are ordinary registered commands now; the Agent-tier wiring is what they
share, not a catch-all branch.
"""

from __future__ import annotations

import argparse
import sys

from ..adapters.moltbook import config
from ..adapters.moltbook.agent import Agent, AutonomyLevel
from ..adapters.moltbook.auth import _mask_key
from ..adapters.moltbook.submolt_scope import DEFAULT_SAMPLE_SIZE
from ..core._io import acquire_run_lock
from ..core.domain import DomainConfig, get_domain_config
from ..core.run_context import new_session_id, set_session_id
from . import doctor
from .registry import CommandSpec, Tier
from .runtime import _llm_session_meta


def _build_agent(args: argparse.Namespace, domain_config: DomainConfig | None) -> Agent:
    return Agent(autonomy=args.autonomy, domain_config=domain_config)


# Allowlist, not a denylist: a field the platform adds later (a key, a token)
# stays off the terminal until someone decides it belongs here.
_STATUS_FIELDS = (
    "status",
    "claimed",
    "is_claimed",
    "verified",
    "name",
    "id",
    "agent_id",
    "claim_url",
    "karma",
)


def _project_status(result: object) -> dict:
    if not isinstance(result, dict):
        return {}
    nested = result.get("agent")
    data = {**result, **nested} if isinstance(nested, dict) else result
    return {k: data[k] for k in _STATUS_FIELDS if k in data}


def _handle_register(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    if not args.name.strip():
        parser.error("--name must not be blank")
    result = _build_agent(args, domain_config).do_register(args.name)
    # Project the response instead of echoing it: the registration reply
    # carries the full api_key, which must not land in a terminal scrollback
    # or a pasted bug report. The claim URL was already printed by do_register.
    agent_data = result.get("agent", result) if isinstance(result, dict) else {}
    print(f"Registered agent: {agent_data.get('name') or args.name}")
    api_key = agent_data.get("api_key")
    if api_key:
        print(f"API key saved to {config.CREDENTIALS_PATH} ({_mask_key(str(api_key))})")
    else:
        print("The server returned no API key; nothing was saved.")


def _handle_status(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    result = _build_agent(args, domain_config).do_status()
    print(f"Agent status: {_project_status(result)}")


def _handle_solve(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    _build_agent(args, domain_config).do_solve(args.text)


def _run_lock_busy_message() -> str:
    """What an operator greps for when a scheduled run exits without working."""
    return f"Another run/distill process holds the run lock ({config.RUN_LOCK_PATH}); exiting."


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
            print(_run_lock_busy_message())
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


def _stdin_is_tty() -> bool:
    """Whether a person can answer a prompt. A seam for tests: pytest's stdin is not a TTY."""
    return sys.stdin.isatty()


def _handle_run(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    domain_config: DomainConfig | None,
) -> None:
    if args.session <= 0 or args.session > 1440:
        parser.error("--session must be between 1 and 1440 minutes")
    # Approve mode asks y/n on stdin before every post and every subscription.
    # With no TTY each read hits EOF and counts as "no", so the session used to
    # run to its end, decline everything and exit 0 (one run logged eight
    # "Proceed?" prompts answered by EOF).
    if args.autonomy is AutonomyLevel.APPROVE and not _stdin_is_tty():
        parser.error("no TTY: use --guarded/--auto or run interactively")
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
        **_llm_session_meta(getattr(args, "constitution_dir", None)),
    }
    try:
        doctor.announce_run_startup(
            session_meta,
            on_abort=lambda _reason: agent.record_startup_abort(
                args.session, session_meta, aborted="serving_unready"
            ),
        )
        # Non-blocking lock (audit M5): a second concurrent session would
        # double-spend rate budgets and race knowledge.json — fail fast
        # with a clear message instead of queueing behind it.
        with acquire_run_lock(config.RUN_LOCK_PATH, blocking=False) as acquired:
            if not acquired:
                print(_run_lock_busy_message())
                return
            agent.run_session(duration_minutes=args.session, session_meta=session_meta)
    finally:
        set_session_id(None)


def _add_register_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--name",
        required=True,
        help="Name for the new agent on Moltbook (must not be taken already)",
    )


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--session",
        type=int,
        default=60,
        help="Session duration in minutes, 1..1440 (default: 60)",
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
        add_arguments=_add_register_arguments,
    ),
    CommandSpec(
        name="status",
        help="Check agent status",
        handler=_handle_status,
        tier=Tier.AGENT,
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
