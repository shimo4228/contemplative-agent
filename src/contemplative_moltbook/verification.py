"""Moltbook verification challenge solver.

Moltbook uses obfuscated math CAPTCHAs to verify AI agents.
Characters are repeated (e.g., "ttwweennttyy" -> "twenty").
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional, Tuple

from .config import MAX_VERIFICATION_FAILURES

if TYPE_CHECKING:
    from .client import MoltbookClient

logger = logging.getLogger(__name__)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}

OPERATIONS = {
    "plus": "+",
    "added": "+",
    "gains": "+",
    "minus": "-",
    "loses": "-",
    "subtracted": "-",
    "times": "*",
    "multiplied": "*",
    "divided": "/",
    "over": "/",
}


def deobfuscate(text: str) -> str:
    """Normalize repeated characters: 'ttwweennttyy' -> 'twenty'.

    Moltbook doubles each character, so we detect the repetition factor
    and take every Nth character. We try factor 2 first (most common),
    then fall back to run-length collapsing.
    """
    if not text:
        return text

    words = text.split(" ")
    decoded_words = []
    for word in words:
        if not word:
            decoded_words.append(word)
            continue
        decoded_words.append(_deobfuscate_word(word))
    return " ".join(decoded_words)


def _deobfuscate_word(word: str) -> str:
    """Deobfuscate a single word by detecting repetition factor."""
    # Try pair-based decoding (factor 2): check if chars at even positions
    # match chars at odd positions
    if len(word) >= 2 and len(word) % 2 == 0:
        is_paired = all(word[i] == word[i + 1] for i in range(0, len(word), 2))
        if is_paired:
            return word[::2]

    # Try factor 3
    if len(word) >= 3 and len(word) % 3 == 0:
        is_tripled = all(
            word[i] == word[i + 1] == word[i + 2]
            for i in range(0, len(word), 3)
        )
        if is_tripled:
            return word[::3]

    # Fallback: run-length collapse
    result = [word[0]]
    for i in range(1, len(word)):
        if word[i] != word[i - 1]:
            result.append(word[i])
    return "".join(result)


def parse_number_word(word: str) -> Optional[int]:
    """Convert a number word to its integer value.

    Handles compound forms like 'twenty-five' or 'twenty five'.
    """
    word = word.lower().strip()

    # Try direct digit
    if word.isdigit():
        return int(word)

    # Try direct lookup
    if word in NUMBER_WORDS:
        return NUMBER_WORDS[word]

    # Try compound forms
    parts = re.split(r"[-\s]+", word)

    # Handle "X hundred Y" pattern first (before simple compound)
    if len(parts) >= 2 and "hundred" in parts:
        idx = parts.index("hundred")
        hundreds = NUMBER_WORDS.get(parts[idx - 1], 0) if idx > 0 else 1
        remainder = 0
        rest = parts[idx + 1:]
        if len(rest) == 1:
            remainder = NUMBER_WORDS.get(rest[0], 0)
        elif len(rest) == 2:
            remainder = NUMBER_WORDS.get(rest[0], 0) + NUMBER_WORDS.get(rest[1], 0)
        return hundreds * 100 + remainder

    # Simple compound: "twenty-five", "twenty five"
    if len(parts) == 2:
        tens = NUMBER_WORDS.get(parts[0])
        ones = NUMBER_WORDS.get(parts[1])
        if tens is not None and ones is not None:
            return tens + ones

    return None


def parse_challenge(text: str) -> Optional[Tuple[float, str, float]]:
    """Parse a deobfuscated challenge into (num1, operator, num2).

    Returns None if parsing fails.
    """
    text = text.lower().strip()

    # Find the operation keyword
    op_symbol = None
    op_pos = -1
    op_word = ""
    for keyword, symbol in OPERATIONS.items():
        idx = text.find(keyword)
        if idx != -1 and (op_pos == -1 or idx < op_pos):
            op_pos = idx
            op_symbol = symbol
            op_word = keyword

    if op_symbol is None:
        return None

    left_text = text[:op_pos].strip()
    right_text = text[op_pos + len(op_word):].strip()

    num1 = parse_number_word(left_text)
    num2 = parse_number_word(right_text)

    if num1 is None or num2 is None:
        return None

    return (float(num1), op_symbol, float(num2))


def compute(num1: float, op: str, num2: float) -> Optional[float]:
    """Compute the result of a binary operation."""
    if op == "+":
        return num1 + num2
    if op == "-":
        return num1 - num2
    if op == "*":
        return num1 * num2
    if op == "/":
        if num2 == 0:
            return None
        return num1 / num2
    return None


def solve_challenge(obfuscated_text: str) -> Optional[str]:
    """Solve an obfuscated math challenge.

    Returns the formatted answer string, or None on failure.
    """
    clean = deobfuscate(obfuscated_text)
    logger.debug("Deobfuscated: '%s' -> '%s'", obfuscated_text, clean)

    parsed = parse_challenge(clean)
    if parsed is None:
        logger.warning("Failed to parse challenge: '%s'", clean)
        return None

    num1, op, num2 = parsed
    result = compute(num1, op, num2)
    if result is None:
        logger.warning("Failed to compute: %s %s %s", num1, op, num2)
        return None

    answer = f"{result:.2f}"
    logger.info("Solved: %s %s %s = %s", num1, op, num2, answer)
    return answer


def submit_verification(
    client: MoltbookClient,
    challenge_id: str,
    answer: str,
) -> dict:
    """Submit a verification answer to Moltbook."""
    response = client.post(
        "/verify",
        json={"challenge_id": challenge_id, "answer": answer},
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
