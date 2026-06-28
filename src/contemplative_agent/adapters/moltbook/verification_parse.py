"""Deterministic parser for Moltbook's obfuscated arithmetic CAPTCHA.

ADR-0062 amendment (2026-06-28): the guarded ``EXPR``/``FINAL`` LLM fast path
only proves that the model's expression and its stated answer agree
arithmetically — *not* that the expression faithfully represents the obfuscated
challenge text. A self-consistent but semantically wrong proposal (e.g.
``20 + 12 = 32`` for a "twenty five + twelve" challenge) therefore slips through
the guard. This module owns the arithmetic and number-word reconstruction for
the *finite* CAPTCHA grammar and runs BEFORE any LLM call.

It is precision-first: it returns a parsed answer only when confident, otherwise
``None`` so the existing LLM chain still runs. A wrong code parse is worse than
``None`` (it bypasses the LLM that might have got it right), so every ambiguity
abstains:

- not exactly two operands -> None,
- not exactly one distinct operation -> None,
- no operation positioned *between* the two operands -> None (a trailing or
  question-framing cue such as "how many more ..." must not be read as the
  operator),
- a negative result -> None (the physical-count CAPTCHA domain is non-negative;
  a negative is far likelier a misparse than a real answer).

Matching is whole-token equality over *merged fragments*, never substring
matching. The obfuscator both splits one word across several
whitespace/punctuation-delimited fragments (``tw|enn|ty`` -> twenty) and pads
carrier nouns whose letters happen to contain number words (``antenna`` contains
``ten``). Substring scanning would falsely read ``ten`` out of ``antenna``;
whole-token equality on merged fragments cannot, because ``antenna`` never
*equals* ``ten``.

The challenge text is untrusted. This parser never executes or interprets it as
instructions — it only matches obfuscated number words and arithmetic cues, is
length-bounded against a malicious oversized payload, and fails closed to
``None``.
"""

from __future__ import annotations

from decimal import Decimal, DivisionByZero, InvalidOperation
import re
from typing import NamedTuple, Optional, Union

from .config import MAX_CHALLENGE_INPUT as _MAX_INPUT

# The parser receives the raw, untrusted challenge before the LLM path's length
# guard, so ``_MAX_INPUT`` bounds its own input: anything longer than a real
# CAPTCHA phrase is malicious or unparseable by the finite grammar — abstain.
# The bound is shared via config so the parser and LLM-path limits cannot drift.

# Greedy fragment-merge window. The obfuscator splits one word across several
# fragments ("tw|enn|ty" -> twenty, "t|welv|e" -> twelve), so a single number
# word can span ~3 fragments; 5 leaves margin. A larger window stays safe
# because matching is whole-token equality (never substring) and the accept
# guard abstains on any extra operand a spurious merge might introduce.
_MERGE_WINDOW = 5

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}
_TEENS = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_ADD = "+"
_SUB = "-"
_MUL = "*"
_DIV = "/"

# Operation cues are matched on the verb in the challenge body. ``-``, ``/`` and
# ``x`` are deliberately NOT taken as literal operators: they are pervasive
# obfuscation noise (e.g. ``b-StErS``, ``HoW/``). Only literal ``+`` and ``*``
# are treated as symbol cues — see ``_SYMBOL_OPS`` / ``_ATOM_RE``.
_OP_WORDS = {
    # add
    "plus": _ADD,
    "add": _ADD,
    "adds": _ADD,
    "gain": _ADD,
    "gains": _ADD,
    "more": _ADD,
    "sum": _ADD,
    "combined": _ADD,
    # subtract
    "minus": _SUB,
    "less": _SUB,
    "lose": _SUB,
    "loses": _SUB,
    "fewer": _SUB,
    "drop": _SUB,
    "drops": _SUB,
    "slows": _SUB,
    "decreases": _SUB,
    # multiply
    "times": _MUL,
    "multiplied": _MUL,
    "multiply": _MUL,
    "product": _MUL,
    # divide
    "divided": _DIV,
    "divide": _DIV,
    "splits": _DIV,
    "split": _DIV,
    "quotient": _DIV,
    "shared": _DIV,
}

# Literal operator symbols that are signal rather than noise.
_SYMBOL_OPS = {"+": _ADD, "*": _MUL}

# One atom per scan step: a run of letters OR a single signal-operator symbol,
# in textual order. Other punctuation (the obfuscation noise) is dropped, but
# operator symbols keep their position relative to the number words so the
# accept guard can require an operator *between* the operands.
_ATOM_RE = re.compile(r"[a-z]+|[+*]")


def _collapse_repeats(text: str) -> str:
    """Collapse every run of an identical character to one (``aa`` -> ``a``).

    This neutralises the obfuscator's letter doubling (``twennty`` -> twenty).
    Number/operation lexicons are keyed on collapsed forms so e.g. ``-teen``
    words (``ee`` -> ``e``) and ``adds`` (``dd`` -> ``d``) compare consistently.
    """
    return re.sub(r"(.)\1+", r"\1", text)


# Lexicons keyed on collapsed forms (see _collapse_repeats). Scan tokens are
# collapsed before lookup so both clean and letter-doubled spellings match.
_NUMBER_WORDS = {
    _collapse_repeats(word): value
    for word, value in {**_UNITS, **_TEENS, **_TENS}.items()
}
_TENS_COLLAPSED = {_collapse_repeats(word) for word in _TENS}
_OP_TOKENS = {_collapse_repeats(word): op for word, op in _OP_WORDS.items()}


class _NumEvent(NamedTuple):
    value: int
    is_tens: bool


class _OpEvent(NamedTuple):
    op: str


_Event = Union[_NumEvent, _OpEvent]


class _Operand(NamedTuple):
    value: int
    first_index: int  # event index of the operand's first token
    last_index: int  # event index of the operand's last token


def code_parse_challenge(challenge_text: str) -> Optional[str]:
    """Parse the finite CAPTCHA grammar deterministically.

    Returns the answer formatted to two decimals (e.g. ``"44.00"``) only when
    exactly two operands and exactly one operation — positioned between them —
    are recovered with high confidence; otherwise ``None`` so the LLM solver
    chain runs.
    """
    if not challenge_text or len(challenge_text) > _MAX_INPUT:
        return None
    return _resolve(_scan(challenge_text))


def _scan(challenge_text: str) -> list[_Event]:
    """Tokenise into ordered number / operation events.

    Number words are reconstructed by greedy whole-token merging of consecutive
    letter atoms (never crossing an operator symbol); operator symbols and verb
    cues become op events in textual order.
    """
    atoms = _ATOM_RE.findall(challenge_text.lower())
    events: list[_Event] = []
    i = 0
    total = len(atoms)
    while i < total:
        atom = atoms[i]
        symbol_op = _SYMBOL_OPS.get(atom)
        if symbol_op is not None:
            events.append(_OpEvent(symbol_op))
            i += 1
            continue

        # Greedy whole-token merge over the run of letter atoms starting at i,
        # bounded by the next operator symbol (merging must not cross it).
        run_end = i
        while run_end < total and atoms[run_end] not in _SYMBOL_OPS:
            run_end += 1
        max_length = min(_MERGE_WINDOW, run_end - i)
        matched = False
        for length in range(max_length, 0, -1):
            token = _collapse_repeats("".join(atoms[i : i + length]))
            if token in _NUMBER_WORDS:
                events.append(_NumEvent(_NUMBER_WORDS[token], token in _TENS_COLLAPSED))
                i += length
                matched = True
                break
            if token in _OP_TOKENS:
                events.append(_OpEvent(_OP_TOKENS[token]))
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return events


def _resolve(events: list[_Event]) -> Optional[str]:
    """Fold events into operands + operations and apply the precision guards."""
    operands: list[_Operand] = []
    op_positions: list[tuple[int, str]] = []
    pending_tens: Optional[int] = None
    pending_index: Optional[int] = None
    op_since_tens = False

    def flush_pending_tens() -> None:
        nonlocal pending_tens, pending_index, op_since_tens
        if pending_tens is not None and pending_index is not None:
            operands.append(_Operand(pending_tens, pending_index, pending_index))
        pending_tens = None
        pending_index = None
        op_since_tens = False

    for index, event in enumerate(events):
        if isinstance(event, _OpEvent):
            op_positions.append((index, event.op))
            if pending_tens is not None:
                op_since_tens = True
            continue
        # _NumEvent: merge a unit (1-9) onto a directly-preceding tens word, but
        # only when no operation cue intervened ("thirty six" -> 36, while
        # "thirty plus five" stays 30 and 5).
        if event.is_tens:
            flush_pending_tens()
            pending_tens = event.value
            pending_index = index
        elif (
            pending_tens is not None
            and pending_index is not None
            and 1 <= event.value <= 9
            and not op_since_tens
        ):
            operands.append(_Operand(pending_tens + event.value, pending_index, index))
            pending_tens = None
            pending_index = None
            op_since_tens = False
        else:
            flush_pending_tens()
            operands.append(_Operand(event.value, index, index))
    flush_pending_tens()

    if len(operands) != 2:
        return None
    operations = {op for _, op in op_positions}
    if len(operations) != 1:
        return None
    operation = next(iter(operations))
    between = any(
        operands[0].last_index < position < operands[1].first_index
        for position, _ in op_positions
    )
    if not between:
        return None
    return _compute(operands[0].value, operation, operands[1].value)


def _compute(lhs: int, op: str, rhs: int) -> Optional[str]:
    """Compute ``lhs op rhs`` with Decimal precision, formatted to two decimals.

    Abstains (``None``) on division by zero and on a negative result — the
    CAPTCHA domain is non-negative, so a negative is a misparse signal.
    """
    left, right = Decimal(lhs), Decimal(rhs)
    try:
        if op == _ADD:
            result = left + right
        elif op == _SUB:
            result = left - right
        elif op == _MUL:
            result = left * right
        elif op == _DIV:
            result = left / right
        else:
            return None
    except (DivisionByZero, InvalidOperation):
        return None
    if not result.is_finite() or result < 0:
        return None
    return f"{result:.2f}"
