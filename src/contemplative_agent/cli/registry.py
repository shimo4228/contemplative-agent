"""Command registry: the single place a subcommand declares itself.

Before this, adding a command meant editing ``main`` twice — once in the
~350-line block of ``subparsers.add_parser`` calls, once in the right
dependency-tier dispatch table further down — and nothing tied the two edits
together. A command whose parser was added but whose tier entry was forgotten
fell through to the Agent-constructing branch instead of erroring.

Now each handler module publishes ``COMMANDS: tuple[CommandSpec, ...]`` and
``main`` iterates it for both parser construction and dispatch, so the two can
no longer disagree.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    """How much runtime a command needs before its handler may run.

    The tiers are ordered by setup cost, and the distinction is not cosmetic:
    ``LLM_RUNTIME_ONLY`` exists because stocktake supplies its own system
    prompts, so loading the skills/rules/axioms corpus would pollute its prompt
    environment — while still needing per-call telemetry (review 2026-06-27 M1).
    """

    NO_LLM = "no_llm"
    """No LLM configuration, no domain config."""

    LLM_RUNTIME_ONLY = "llm_runtime_only"
    """LLM telemetry only — deliberately without the prompt corpus."""

    LLM_FULL = "llm_full"
    """LLM + domain config, but no Agent instance."""

    AGENT = "agent"
    """Needs an Agent; the handler takes ``domain_config`` as a third argument."""


def no_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare a command that takes no flags of its own."""
    return


@dataclass(frozen=True)
class CommandSpec:
    """One subcommand: its parser, its handler, and what runtime it needs."""

    name: str
    help: str
    handler: Callable[..., None]
    tier: Tier
    add_arguments: Callable[[argparse.ArgumentParser], None] = no_arguments

    def resolve(self) -> Callable[..., None]:
        """Look the handler up by name in its defining module, at call time.

        A ``CommandSpec`` captures the function object at import time, so
        ``mock.patch`` on the handler's definition site would otherwise be a
        silent no-op and CLI wiring tests would assert against the real
        implementation without noticing. Resolving here keeps patching the
        definition site working, and falls back to the captured object when the
        module no longer carries the name.

        The lookup is by ``__name__``, not identity, so do not "simplify" this
        back to returning ``self.handler`` — that reintroduces the silent
        no-op. The tradeoff: two handlers sharing a name in one module (a
        decorator that rebinds, an alias assignment) would resolve to whichever
        object currently owns the name. Every handler here is a uniquely named
        module-level ``_handle_*``, which is what keeps that theoretical.
        """
        module = sys.modules.get(self.handler.__module__)
        if module is None:
            return self.handler
        return getattr(module, self.handler.__name__, self.handler)


def build_subparsers(
    subparsers: argparse._SubParsersAction,
    commands: tuple[CommandSpec, ...],
) -> None:
    """Register every command's parser onto *subparsers*."""
    for spec in commands:
        spec.add_arguments(subparsers.add_parser(spec.name, help=spec.help))


def index_by_name(commands: tuple[CommandSpec, ...]) -> dict[str, CommandSpec]:
    """Map command name -> spec, rejecting duplicate registrations.

    Two modules claiming the same command name used to be a last-writer-wins
    dict literal; here it is a startup error, since the winner depended on
    dispatch-table order that nothing documented.
    """
    index: dict[str, CommandSpec] = {}
    for spec in commands:
        if spec.name in index:
            raise ValueError(f"duplicate command registration: {spec.name}")
        index[spec.name] = spec
    return index
