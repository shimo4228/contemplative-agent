"""The policy every outward write shares: verify, then record — or record nothing.

Posting, commenting and replying each ran their own copy of the same three
decisions: what to do when the create-response carries an unsolved verification
challenge, how to log a published body without leaking it into the sweep-scanned
log dir, and what to do when the client raises. The copies had already drifted —
``_publish_post`` was the only one that did not flag a 429 as rate-limited, so a
throttled post cycle kept spending budget the comment paths would have stopped
spending.

What is NOT here: the dedup key, the memory records, the episode payload, the
novelty sidecar, pacing, the courtesy upvote. Those differ per action for
reasons (a reply dedups per comment, a self-post has no counterparty, only the
feed loop paces), and collapsing them behind a callback bundle would hide the
reasons rather than share them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from ...core.text_utils import log_preview
from .client import MoltbookClientError
from .verification import VerificationAction

logger = logging.getLogger(__name__)


class VerificationHandler(Protocol):
    """The create-time handshake callback (``agent._handle_verification``).

    ``action`` / ``target_id`` identify what the handshake gates so the
    verification audit record can carry them as data (weekly F1.2 2026-08-08)
    instead of the caller dropping them into a log format string the sweep
    normalizes into uncountability.
    """

    def __call__(
        self,
        verification: dict[str, Any],
        *,
        action: VerificationAction | None = None,
        target_id: str | None = None,
    ) -> bool: ...


@contextmanager
def client_error_guard(action: str, *, on_rate_limited: Callable[[], None]) -> Iterator[None]:
    """Swallow a ``MoltbookClientError`` from one outward write.

    A failed write is not exceptional at this layer — the session continues with
    the next action — but a 429 is: it means the budget model and the server
    disagree, and continuing at the same rate wastes the remaining window. Every
    write path flags it, which is the part ``_publish_post`` was missing.
    """
    try:
        yield
    except MoltbookClientError as exc:
        logger.error("Failed to %s: %s", action, exc)
        if exc.status_code == 429:
            on_rate_limited()


def passes_verification(
    verification: dict[str, Any] | None,
    handle_verification: VerificationHandler,
    *,
    description: str,
    action: VerificationAction,
    target_id: str,
) -> bool:
    """Solve the create-response challenge, if the response carries one.

    Content is created but invisible until the challenge is answered, and the
    window is short enough that a failure is unrecoverable. So a failure means
    record NOTHING — leaving the action out of dedup, memory and the novelty
    gate is what lets a later session redo it visibly. Recording an unverified
    write instead silences the agent: it dedups future attempts against content
    nobody ever saw.

    ``action`` and ``target_id`` are required precisely because a failure
    records nothing: the audit record is then the ONLY countable trace that a
    published body was orphaned, and it needs the create kind and a joinable
    target digest to say so (weekly F1.2 2026-08-08). The WARNING below stays
    as the human-readable trace; it is no longer the only one.

    A trusted-bypass response carries no ``verification`` key and passes.
    """
    if verification is None:
        return True
    if handle_verification(verification, action=action, target_id=target_id):
        return True
    logger.warning("%s created but verification failed; not recording", description)
    return False


def verification_of(created: object) -> dict[str, Any] | None:
    """The ``verification`` object of a create response, if it has one."""
    return created.get("verification") if isinstance(created, dict) else None


def log_published(summary_fmt: str, *args: object, body: str) -> None:
    """Log a published body as a bounded single-line preview, never in full.

    Full bodies in ``*.log`` become anomaly-sweep noise and cross the
    self-written-log trust boundary (F1.1 2026-07-11); the canonical full text
    lives in the episode log and the comment reports instead.

    Until 2026-08-01 this also emitted the whole body at DEBUG, guarded only by
    the docstring instruction "never redirect a -v run's output into the
    sweep-scanned logs dir" — which the production ``com.moltbook.agent`` plist
    had been violating, running ``-v`` with both stdout and stderr pointed at
    ``logs/agent-launchd.log``. Multi-line bodies landed there as prefix-less
    continuation lines, inside the channel ``log_anomaly_sweep.py`` reads and
    ``weekly-analysis.sh`` feeds to an LLM (the side channel ADR-0083 closed for
    episode logs). The DEBUG branch and its ``full_fmt`` / ``full_args``
    parameters are gone rather than merely unused: an argument that cannot be
    passed cannot be redirected. Enforced by ``tests/test_publish_logging.py``.

    ``summary_fmt`` receives ``*args`` plus the char count and the preview.
    """
    logger.info(summary_fmt, *args, len(body), log_preview(body))
