"""The policy every outward write shares: verify, then record — or record nothing.

Posting, commenting and replying each ran their own copy of the same three
decisions: what to do when the create-response carries an unsolved verification
challenge, how to log a published body without leaking it into the sweep-scanned
log dir, and what to do when the client raises. The copies had already drifted —
``_publish_post`` was the only one that did not flag a 429 as rate-limited, so a
throttled post cycle kept spending budget the comment paths would have stopped
spending. The RFC-0028 outcome row is the same shape of shared decision: the
guard hides "raised" from everything after it, so "record exactly one row,
``PUBLISH_FAILED`` unless something said otherwise" lives here too.

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
from dataclasses import dataclass
from typing import Protocol

from ...core.config import is_valid_id
from ...core.skill_selection import (
    PUBLISH_FAILED,
    PUBLISH_FAILURE_PARENT_REJECTED,
    PUBLISH_FAILURE_RATE_LIMITED,
    PUBLISH_FAILURE_TRANSPORT,
    PUBLISH_FAILURE_UNKNOWN,
    PUBLISH_ID_UNKNOWN,
    PUBLISH_PUBLISHED,
    PUBLISH_UNVERIFIED,
    record_publish_outcome,
)
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
        verification: object,
        *,
        action: VerificationAction | None = None,
        target_id: str | None = None,
    ) -> bool: ...


# The one phrase in the platform's 4xx body that separates "this parent
# comment cannot be replied to" from every other client rejection. Matched
# because the status alone does not distinguish them and the body itself may
# not be recorded — the match produces a code, never a stored string, so a
# server that forged the phrase would mislabel one row of our own instrument
# and nothing else (RFC-0029 / ADR-0083).
#
# Only on a 4xx: a validation body may echo submitted content back
# (``client.py``), and our own comment text is LLM-generated from inbound
# posts, so an unrestricted match is steerable by a counterparty who gets us
# to write the phrase. Not narrowed to specific codes (400/404/422) because
# the platform's code for this rejection is not documented and guessing it
# would lose the class this reason code exists to count — the residual
# false-positive stays inside one 4xx row of our own instrument.
_PARENT_REJECTION_MARKER = "parent comment"


# Our own prefix for a request that never reached the server (``client.request``
# wraps the transport exception). Ours, not the platform's, which is why it is
# safe to key a reason on it.
_TRANSPORT_MESSAGE_PREFIX = "request failed:"


@dataclass(frozen=True)
class PublishFailure:
    """Why one outward write failed, in the two columns the outcome row keeps.

    Deliberately not the message: ``failure_reason`` is a member of
    ``PUBLISH_FAILURE_REASONS`` and ``http_status`` an int, so nothing
    platform-authored travels from here into the readable log. The full
    message keeps its one existing destination, the ERROR line in
    ``client_error_guard``.
    """

    http_status: int | None
    failure_reason: str


def publish_failure_of(exc: MoltbookClientError) -> PublishFailure:
    """Classify one client error into the RFC-0029 columns.

    Ordered by how actionable the answer is: a 429 is the one the session
    reacts to immediately, a parent rejection is the one the 2026-09-11 sweep
    could not name, a transport failure is "the platform never heard us", and
    everything else is ``unknown`` — which loses nothing, because
    ``http_status`` still carries the code the reading would group by.
    """
    status = exc.status_code if isinstance(exc.status_code, int) else None
    message = str(exc).lower()
    if status == 429:
        reason = PUBLISH_FAILURE_RATE_LIMITED
    elif status is not None and 400 <= status < 500 and _PARENT_REJECTION_MARKER in message:
        reason = PUBLISH_FAILURE_PARENT_REJECTED
    elif status is None and message.startswith(_TRANSPORT_MESSAGE_PREFIX):
        reason = PUBLISH_FAILURE_TRANSPORT
    else:
        reason = PUBLISH_FAILURE_UNKNOWN
    return PublishFailure(http_status=status, failure_reason=reason)


@contextmanager
def client_error_guard(
    action: str,
    *,
    on_rate_limited: Callable[[], None],
    on_failure: Callable[[PublishFailure], None] | None = None,
) -> Iterator[None]:
    """Swallow a ``MoltbookClientError`` from one outward write.

    A failed write is not exceptional at this layer — the session continues with
    the next action — but a 429 is: it means the budget model and the server
    disagree, and continuing at the same rate wastes the remaining window. Every
    write path flags it, which is the part ``_publish_post`` was missing.

    ``on_failure`` receives the classified failure. It exists because the guard
    is also the last place the error is visible: everything after it sees only
    "the write finished", so a path that records an outcome row can otherwise
    say ``publish_failed`` without saying why (RFC-0029).
    """
    try:
        yield
    except MoltbookClientError as exc:
        logger.error("Failed to %s: %s", action, exc)
        # Rate limit first: it is the one the session reacts to, and ordering
        # it after a caller-supplied callback would let that callback's failure
        # skip it (code review 2026-09-12).
        if exc.status_code == 429:
            on_rate_limited()
        if on_failure is not None:
            try:
                on_failure(publish_failure_of(exc))
            except Exception:  # the guard swallows; a recorder may not undo that
                logger.warning("Failed to record why %s failed", action, exc_info=True)


class PublishOutcome:
    """The RFC-0028 outcome row for one outward write, in progress.

    Every exit of a write path has to leave exactly one ``publish`` record, and
    ``client_error_guard`` swallows the client error — so "the write raised"
    looks, from outside the guard, identical to "the write finished". Each
    caller therefore carried the same three locals (a ``PUBLISH_FAILED``
    default, the id seen so far, and a ``recorded`` flag) plus a post-guard
    fallback. Held here instead, so the failure default belongs to the same
    place as the success path rather than to whoever remembers to repeat it.

    ``published`` / ``unverified`` write immediately rather than at exit: the
    row has to survive the process being interrupted between the publish and
    the records that follow it (feed_manager's ordering note).
    """

    def __init__(self, selection_id: str | None) -> None:
        self._selection_id = selection_id
        self._comment_id: str | None = None
        self._recorded = False
        self._failure: PublishFailure | None = None

    def created(self, comment_id: str | None) -> None:
        """Remember the id the create response carried, before verifying it.

        Kept even when the write later fails: the fallback row names the
        comment that may be live but unrecorded elsewhere.
        """
        self._comment_id = comment_id

    def published(self) -> None:
        """Record a live, verified write — id-unknown when the envelope had none."""
        self._record(PUBLISH_PUBLISHED if self._comment_id else PUBLISH_ID_UNKNOWN)

    def unverified(self) -> None:
        """Record a write whose create-time handshake failed."""
        self._record(PUBLISH_UNVERIFIED)

    def failed(self, failure: PublishFailure) -> None:
        """Remember why the write failed, for the ``PUBLISH_FAILED`` exit row.

        Pass as ``client_error_guard(on_failure=...)``: the guard is inside
        this block, so this is how the swallowed error reaches the exit that
        writes the row.
        """
        self._failure = failure

    def _record(self, publish_status: str) -> None:
        # The reason columns belong to the failed row only — every other
        # status names its own cause (``record_publish_outcome``).
        failure = self._failure if publish_status == PUBLISH_FAILED else None
        record_publish_outcome(
            self._selection_id,
            comment_id=self._comment_id,
            publish_status=publish_status,
            http_status=failure.http_status if failure else None,
            failure_reason=failure.failure_reason if failure else None,
        )
        self._recorded = True


@contextmanager
def publish_outcome(selection_id: str | None) -> Iterator[PublishOutcome]:
    """Guarantee one RFC-0028 outcome row for the write inside the block.

    Leaving the block without having recorded means the write never reached
    the platform (the guard swallowed the client error, or the body was never
    sent), which is ``PUBLISH_FAILED``. Wrap this OUTSIDE
    ``client_error_guard`` so the swallowed error still reaches the exit.
    """
    outcome = PublishOutcome(selection_id)
    try:
        yield outcome
    finally:
        if not outcome._recorded:
            outcome._record(PUBLISH_FAILED)


def passes_verification(
    verification: object,
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

    A trusted-bypass response carries no ``verification`` key and passes
    (an explicit JSON ``null`` passes the same way — the bypass is the
    identity check ``is None``, never truthiness).
    The value is server-controlled JSON and is passed through unnarrowed —
    the handler owns the shape check (a non-dict is its audited reject,
    2026-08-31), so a malformed challenge still leaves the countable trace.
    """
    if verification is None:
        return True
    if handle_verification(verification, action=action, target_id=target_id):
        return True
    logger.warning("%s created but verification failed; not recording", description)
    return False


def created_comment_id(created: dict) -> str | None:
    """The id of a just-created comment, or None when the envelope had none.

    ``post_comment`` returns ``{}`` for an ambiguous envelope and folds a bare
    top-level id into the dict, so an id can legitimately be absent after a
    successful publish (client docstring). ``is_valid_id`` is what keeps a
    hostile body from putting an arbitrary string — of any length — into the
    outcome log's join key.
    """
    if not isinstance(created, dict):
        return None
    value = created.get("id") or created.get("comment_id")
    return value if is_valid_id(value) else None


def verification_of(created: object) -> object:
    """The ``verification`` value of a create response, if it has one.

    Deliberately ``object``, not ``dict | None``: the value is server-
    controlled JSON and this function does not narrow it — asserting ``dict``
    here would be a narrowing lie (review 2026-08-31). The handler behind
    ``passes_verification`` owns the shape check.
    """
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
