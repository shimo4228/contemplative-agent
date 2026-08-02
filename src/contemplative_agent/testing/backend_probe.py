"""The adapter a sibling implements so the kit can drive its backend.

Everything in :mod:`.backend_contract` is something a sibling *calls*. This
module is the one thing a sibling *implements*. The split is deliberate:
the two have different readers, and a sibling that only ever reaches
``LEVEL_STATIC`` never opens this file.

Why a Protocol rather than a bag of callables passed to ``check_backend``:
six keyword arguments named ``sent_sampling_params`` / ``stub_malformed`` /
``construct_with_untrusted_host`` / ... would be unreadable at the call site
and would give the sibling no typed target for pyright to check. ADR-0087
split ``TokenCountingBackend`` off ``LLMBackend`` for the same reason — a
capability a backend *can* honor deserves a type the checker verifies.

Why the surface is two methods and not seven: the obvious accessors leak
provider assumptions into the kit. ``sent_messages()`` presumes a chat
messages array; Anthropic carries ``system`` outside it, and a completion
backend has no such array at all. :class:`SentCall` is the normalized form
the kit reads, and :attr:`SentCall.raw` is the escape hatch a sibling reads
back for its own provider-shaped tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Recognized make_backend() overrides
# ---------------------------------------------------------------------------

# A non-positive context window must be refused at construction: it would
# make the C2 pre-flight skip every check and blackout generation silently.
OVERRIDE_CONTEXT_WINDOW = "context_window"
# An untrusted host or a non-http scheme must be refused at construction
# (SSRF). Meaningless for an SDK-keyed backend, which raises
# NotImplementedError and gets the dependent checks skipped.
OVERRIDE_BASE_URL = "base_url"

OVERRIDES = (OVERRIDE_CONTEXT_WINDOW, OVERRIDE_BASE_URL)


@dataclass(frozen=True)
class ProbeResponse:
    """What the provider should return, expressed in the contract's vocabulary.

    The fields mirror :class:`~contemplative_agent.core.llm.BackendResult`
    one-for-one, and that correspondence is the point: the kit hands the
    probe a value in the contract's vocabulary and asserts it comes back in
    the contract's vocabulary. A backend that drops ``cached_tokens`` on the
    floor is caught by the round trip, not by a provider-specific assertion.

    The two trailing flags are faults rather than content, so they are named
    for what they do rather than for a field:

    ``malformed`` — the provider returns a body this backend cannot parse.
    The contract is that the backend raises (so the caller records
    ``error_kind="backend_exception"``), not that it returns None (which
    collapses into ``outcome="empty"`` and loses the diagnosis).

    ``raise_transport`` — the transport itself fails. The backend must let it
    propagate rather than swallowing it into a None.
    """

    text: str | None = "ok"
    finish_reason: str | None = "stop"
    eval_count: int | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    thinking: str | None = None
    malformed: bool = False
    raise_transport: BaseException | None = None


@dataclass(frozen=True)
class SentCall:
    """One provider call the backend made, normalized.

    :meth:`BackendProbe.responding` yields a plain ``list`` that the probe
    appends one of these to per call. One immutable record per call rather
    than a single mutable accumulator: "how many calls" is then ``len()``
    rather than a counter that can disagree with the records, and the kit's
    strongest negative assertion — the C2 pre-flight check, that the request
    never reached the provider at all — is simply an empty list.
    """

    # top_p / top_k / temperature / the output cap, under whatever names the
    # provider uses. The kit looks up the values, not the key spelling.
    sampling: Mapping[str, object] = field(default_factory=dict)
    # None means the backend sent no system content at all, which is the
    # contract for an empty system string. An empty string means it sent one
    # and it was empty — a different thing, and the failure being checked.
    system: str | None = None
    prompt: str | None = None
    # Provider-shaped, untouched. The kit never reads this; a sibling's own
    # payload-shape tests do. Keeping it here means writing a probe is a
    # migration of the sibling's existing mocks rather than new work.
    raw: object = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sampling", MappingProxyType(dict(self.sampling)))


@runtime_checkable
class BackendProbe(Protocol):
    """The sibling-supplied adapter for everything above ``LEVEL_STATIC``.

    Two methods. Provider shape is absorbed here so the kit only ever sees
    :class:`ProbeResponse` and :class:`SentCall`.
    """

    def make_backend(self, **overrides: object) -> object:
        """Construct a fresh backend, applying *overrides* if recognized.

        Recognized keys are listed in :data:`OVERRIDES`. For each, the
        contract is that construction *fails* — the checks are that a
        non-positive context window and an untrusted base URL are refused at
        the door rather than at first use.

        An override this backend has no concept of must raise
        ``NotImplementedError``; the dependent checks are then reported as
        skipped with a reason rather than silently passing.
        """
        ...

    def responding(self, *responses: ProbeResponse) -> AbstractContextManager[list[SentCall]]:
        """Make provider calls inside the block return *responses* in order.

        Once the responses are exhausted the last one repeats, matching the
        schedule convention in ``tests/chaos.py`` — a check that issues one
        call should not have to care how many the backend makes internally.

        The yielded list receives one :class:`SentCall` per provider call, in
        order, and is readable after the block exits.
        """
        ...
