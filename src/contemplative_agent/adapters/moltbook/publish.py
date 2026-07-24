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
from typing import Any

from ...core.text_utils import log_preview
from .client import MoltbookClientError

logger = logging.getLogger(__name__)


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
    verification: Any,
    handle_verification: Callable[[dict], bool],
    *,
    description: str,
) -> bool:
    """Solve the create-response challenge, if the response carries one.

    Content is created but invisible until the challenge is answered, and the
    window is short enough that a failure is unrecoverable. So a failure means
    record NOTHING — leaving the action out of dedup, memory and the novelty
    gate is what lets a later session redo it visibly. Recording an unverified
    write instead silences the agent: it dedups future attempts against content
    nobody ever saw.

    A trusted-bypass response carries no ``verification`` key and passes.
    """
    if verification is None:
        return True
    if handle_verification(verification):
        return True
    logger.warning("%s created but verification failed; not recording", description)
    return False


def verification_of(created: Any) -> Any:
    """The ``verification`` object of a create response, if it has one."""
    return created.get("verification") if isinstance(created, dict) else None


def log_published(
    summary_fmt: str,
    *args: Any,
    body: str,
    full_fmt: str,
    full_args: tuple[Any, ...] | None = None,
) -> None:
    """Log a published body: INFO preview, DEBUG full text.

    Full bodies in ``*.log`` become anomaly-sweep noise and cross the
    self-written-log trust boundary (F1.1 2026-07-11), so the canonical full
    text lives in the episode log and the comment reports instead. A verbose
    (-v) run does emit the full body at DEBUG — never redirect a -v run's output
    into the sweep-scanned logs dir.

    ``summary_fmt`` receives ``*args`` plus the char count and the preview;
    ``full_fmt`` receives ``full_args`` (defaulting to ``args``) plus the body.
    The override exists because the post path identifies itself by title in the
    INFO line but by id alone in the DEBUG line — and a format string given the
    wrong number of arguments does not raise, it silently drops the record.
    """
    logger.info(summary_fmt, *args, len(body), log_preview(body))
    logger.debug(full_fmt, *(args if full_args is None else full_args), body)
