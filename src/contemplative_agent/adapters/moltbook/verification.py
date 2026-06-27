"""Moltbook verification challenge solver.

Moltbook gates every created post/comment/submolt behind an obfuscated math
CAPTCHA (anti-spam): the create-response carries a ``verification`` object
whose ``challenge_text`` is a lobster/physics word problem rendered with
alternating capitalisation, scattered punctuation and broken/repeated words.
The answer (a number to 2 decimals) must be POSTed to ``/verify`` with the
``verification_code`` before the content becomes visible. Trusted agents and
admins bypass this and receive no ``verification`` object.

Solving is a *semantic* task — the operation is implied by a verb ("swims at
twenty and slows by five" = 20 - 5), and the noise is adversarial to any fixed
parser — so the challenge text is handed to the LLM (the CAPTCHA is explicitly
designed for language understanding). The trust boundary is the *output*: only
a ``float``-parseable number is ever submitted (``_extract_answer``); a prompt
injected via the challenge yields no number, fails closed to ``None``, and is
bounded by ``VerificationTracker``.
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Optional

from .config import MAX_VERIFICATION_FAILURES
from ...core.llm import generate

if TYPE_CHECKING:
    from .client import MoltbookClient

logger = logging.getLogger(__name__)

_SOLVER_SYSTEM = (
    "You solve obfuscated arithmetic word problems. The text is deliberately "
    "noisy: scrambled upper/lower case, scattered punctuation, and repeated or "
    "broken letters. First de-noise it and restate the problem, identify the two "
    "numbers and the single operation (a verb often implies it: 'slows by'/"
    "'loses' = subtract, 'gains'/'speeds up by' = add, 'splits into'/'divided "
    "by' = divide, 'times' = multiply), then compute. Reason step by step. On "
    "the FINAL line output only the answer as a number to two decimals, e.g. "
    "15.00 — the last number in your reply must be that answer."
)
# A reasoning model gets the arithmetic right only when allowed to think first
# (forcing an immediate answer produced wrong results in testing); num_predict
# is a generous cap, and drop_truncated fails closed if a case overruns rather
# than extracting a number from incomplete reasoning.
#
# Retuned 3000→5000 (2026-06-27): telemetry (caller=moltbook.verify_solve, n=71)
# showed 12.7% of solves hitting the cap (done_reason=length) → dropped by
# drop_truncated → the post stays unverified and invisible. Successful (STOP)
# solves' output ran up to 2901 tokens (p99=2810) — genuine multi-step reasoning
# on hard challenges, not degenerate repetition (temperature=0 rules out a
# high-temp loop). 5000 (~1.8x p99) clears the genuine tail and stays well within
# NUM_CTX (system + short challenge + 5000 ≈ 5.3K ≪ 32768).
_SOLVER_NUM_PREDICT = 5000


def solve_challenge(challenge_text: str) -> Optional[str]:
    """Solve an obfuscated math challenge via the LLM.

    Returns the answer formatted to 2 decimals (e.g. ``"15.00"``), or ``None``
    when the LLM is unavailable or returns no parseable number.
    """
    if not challenge_text:
        return None
    # temperature=0 for a deterministic arithmetic answer; drop_truncated=True so
    # a cut-off reasoning trace fails closed (None) instead of yielding a wrong
    # number pulled from incomplete work.
    raw = generate(
        challenge_text,
        system=_SOLVER_SYSTEM,
        num_predict=_SOLVER_NUM_PREDICT,
        temperature=0.0,
        drop_truncated=True,
        caller="moltbook.verify_solve",
    )
    if not raw:
        logger.warning("Verification solver returned no output")
        return None
    answer = _extract_answer(raw)
    if answer is None:
        logger.warning("Verification solver output had no parseable number")
    else:
        logger.info("Verification challenge solved: %s", answer)
    return answer


def _extract_answer(text: str) -> Optional[str]:
    """Pull the final number from LLM output and format it to 2 decimals.

    The last number is used: instruction-following output is the bare answer,
    and a reasoning model concludes with the answer after any intermediate
    numbers. Returns ``None`` when no number is present (the output-side trust
    boundary: a non-numeric / injected response fails closed)."""
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    value = float(numbers[-1])  # regex guarantees a float-parseable token
    if not math.isfinite(value):
        # A pathologically long digit run overflows to inf; reject rather than
        # submit "inf" as the answer.
        return None
    return f"{value:.2f}"


def submit_verification(
    client: "MoltbookClient",
    verification_code: str,
    answer: str,
) -> dict:
    """Submit a verification answer to Moltbook (POST /verify).

    The current API keys the submission on ``verification_code`` (the opaque
    ``moltbook_verify_...`` handle returned in the create-response), not a
    challenge id. The code travels in the JSON body, not the URL, so no
    path-pattern validation is applied here.
    """
    response = client.post(
        "/verify",
        json={"verification_code": verification_code, "answer": answer},
    )
    return response.json()


class VerificationTracker:
    """Track consecutive verification failures and auto-stop."""

    def __init__(self, max_failures: int = MAX_VERIFICATION_FAILURES) -> None:
        self._consecutive_failures = 0
        self._max_failures = max_failures

    @property
    def should_stop(self) -> bool:
        return self._consecutive_failures >= self._max_failures

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self.should_stop:
            logger.error(
                "Verification failed %d times consecutively. "
                "Auto-stopping to prevent account suspension.",
                self._consecutive_failures,
            )
