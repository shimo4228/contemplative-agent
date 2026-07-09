"""Deterministic parser for Moltbook's obfuscated arithmetic CAPTCHA.

Rewritten 2026-07-07 (ADR-0062, 5th amendment) from the 601-challenge audit
corpus (docs/evidence/adr-0062-parser-rewrite/). The previous grammar grew by
per-failure patching; this version derives its rules from the corpus-observed
obfuscation layers instead:

- letter doubling (``ttwweennttyy``) — collapsed before lexicon lookup;
- word splitting (``tw en ty th ree``) — whole-atom merges, bounded by the
  longest lexicon word, never by a fragment-count window;
- leet substitution (``f0rce``) — ``0`` maps to ``o`` before scanning;
- homophone misspelling (``fife``, ``twenny``, ``thrirty``) — bounded fuzzy
  matching (edit distance 1 after collapse, minimum lengths, unique result);
  a misspelled number word that stayed invisible made the old parser submit
  a confidently wrong answer, the only deterministic-path wrongs in the
  corpus;
- duplicated number words (``fourteen fourteen``) — adjacent equal values
  collapse to one;
- multi-step phrasing (``gains eight ... increases by seven``) — operands
  and operations must interleave strictly (num op num [op num ...]) and are
  left-folded;
- implicit operations in the question tail (``... what is the total
  force?`` / ``... what is the product?`` / ``twelve newtons less``) —
  resolved only under the connective/unit/adjacency guards below.

Round 7 (2026-07-09, ADR-0062 7th amendment) extends the grammar from the
post-rewrite failure round of the live corpus:

- multiplicative markers (``by a factor of seven`` / ``doubled by two`` /
  ``each detects two``) — a marker word makes the surrounding pair a
  product, and beats a generic change-verb (``increases``/``accelerates``)
  in the same gap; a NON-adjacent trailing marker is scene noise and is
  ignored;
- adjacent ``times`` tail after a change-verb gap (``increases it by three
  times``) — corpus-accepted twins show the server means multiply;
- count multipliers (``and three claws`` / ``has two claws``) — a claw
  count after the second operand multiplies the per-claw magnitude (every
  corpus-accepted example is a product, none an add);
- explicit arithmetic instructions (``what is the sum of these`` /
  ``please add them``) — waive the like-unit guard that otherwise blocks
  an implicit add across unlike units;
- contradiction abstains — ``slows`` against a trailing ``combined`` cue,
  and a bare possessed count (``it has two, whats total``) whose noun was
  mangled away, both abstain instead of guessing;
- number-word fuzzy vs the collapsed canonical spelling (``fowr teen`` ->
  ``fowrten`` -> fourteen) for merged tokens of >= 6 letters, mirroring
  what operation verbs already do.

It stays precision-first: a parsed answer is returned only when the whole
event stream fits the grammar; every ambiguity abstains (``None``) so the
LLM chain still runs. A wrong code parse is worse than ``None``.

Matching is whole-token equality (or distance-1 fuzzy) over merged whole
atoms, never substring matching: ``antenna`` never yields ``ten`` because it
never *equals* (nor is within one edit of) ``ten``.

The challenge text is untrusted. This parser never executes or interprets it
as instructions — it only matches obfuscated number words and arithmetic
cues, is length-bounded against a malicious oversized payload, and fails
closed to ``None``.
"""

from __future__ import annotations

import re
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import NamedTuple, Optional, Union

from .config import MAX_CHALLENGE_INPUT as _MAX_INPUT

# The parser receives the raw, untrusted challenge before the LLM path's
# length guard, so ``_MAX_INPUT`` bounds its own input: anything longer than a
# real CAPTCHA phrase is malicious or unparseable by the finite grammar —
# abstain. The bound is shared via config so the parser and LLM-path limits
# cannot drift.

_ADD = "+"
_SUB = "-"
_MUL = "*"
_DIV = "/"
# Internal variant of _ADD for generic change-verbs ("increases",
# "accelerates"): they mean add on their own (corpus-accepted many times
# over) but are OVERRIDDEN to multiply by an explicit multiplicative marker
# ("by a factor of seven") in the same gap or an adjacent "times" tail.
# Normalised back to _ADD before computing.
_ADD_CHANGE = "+change"


def _normalize_op(op: str) -> str:
    return _ADD if op == _ADD_CHANGE else op


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

# Operation cues are matched on the verb in the challenge body. ``-``, ``/``
# and ``x`` are deliberately NOT taken as literal operators: they are
# pervasive obfuscation noise (``b-StErS``, ``HoW/``). Only literal ``+`` and
# ``*`` are treated as symbol cues, and only when positioned between operands
# (a stray trailing ``what is+ total force?`` is noise — see _resolve).
#
# Quantity-introducing verbs (``exerts``, ``applies``, ``pushes``, ``has``)
# are deliberately absent: they attach a magnitude to a subject, they do not
# combine two magnitudes ("one claw exerts X and the other exerts Y" is an
# implicit ADD resolved by the question tail, not by "exerts").
_OP_WORDS = {
    # add
    "plus": _ADD,
    "add": _ADD,
    "adds": _ADD,
    "added": _ADD,
    "gain": _ADD,
    "gains": _ADD,
    "gained": _ADD,
    "give": _ADD,
    "gives": _ADD,
    "more": _ADD,
    "increases": _ADD_CHANGE,
    "increased": _ADD_CHANGE,
    "accelerates": _ADD_CHANGE,
    "accelerate": _ADD_CHANGE,
    "acquires": _ADD,
    "acquire": _ADD,
    "speeds": _ADD_CHANGE,
    # subtract
    "minus": _SUB,
    "less": _SUB,
    "lose": _SUB,
    "loses": _SUB,
    "lost": _SUB,
    "fewer": _SUB,
    "drop": _SUB,
    "drops": _SUB,
    "slows": _SUB,
    "decreases": _SUB,
    "decreased": _SUB,
    "reduces": _SUB,
    "reduce": _SUB,
    "subtracts": _SUB,
    "subtract": _SUB,
    # multiply
    "times": _MUL,
    "multiplied": _MUL,
    "multiply": _MUL,
    "multiplies": _MUL,
    "product": _MUL,
    # divide — the 601-challenge corpus contains ZERO division challenges;
    # only unambiguous explicit words are kept (for the grammar's symmetry),
    # while the prose-ambiguous "splits"/"split"/"shared" of the previous
    # lexicon are dropped: the corpus uses them as scene prose ("a claw
    # struggle splits on territory", "shares claw"), where reading them as
    # division turned a correct implicit add into 30/14.
    "divided": _DIV,
    "divide": _DIV,
    "divides": _DIV,
    "quotient": _DIV,
}

# Literal operator symbols that are signal (when between operands).
_SYMBOL_OPS = {"+": _ADD, "*": _MUL}

# Multiplicative marker words (round 7). A marker between two operands makes
# the pair a product — filling an empty gap ("the force is doubled by two")
# or beating a generic change-verb in the same gap ("increases velocity by a
# factor seven"; twin-confirmed: "times a molting growth factor is seven" =
# 161.00 accepted). A marker AFTER the last operand is scene noise
# ("...dominance fights lobster velocity um physicx factors" = 47.00
# accepted as a plain add) and is ignored in the explicit-chain path.
# "times" itself stays an _OP_WORDS entry: unlike these nouns it IS the
# operator when it sits between operands, and its adjacent-tail behaviour is
# handled by the change-verb override in _resolve.
_MUL_MARKER_WORDS = {
    "factor",
    "factors",
    "doubled",
    "doubles",
    "double",
    "each",
}

# Possession/usage verbs in the SAME-SUBJECT form "it has/uses" directly
# before a BARE second operand ("...and it has twoo, whats total force?"):
# corpus "has" is additive when another entity holds the quantity ("the
# weaker claw has fourteen" = add) but multiplicative when the same subject
# possesses a count of claws ("it has two claws" = 50.00 accepted for
# 25x2). With the count noun mangled away, the same-subject bare form is
# ambiguous — abstain. The "<noun> has N" form stays an implicit add.
_POSSESSION_VERBS = {"has", "uses"}
_SAME_SUBJECT_WORDS = {"it"}

# Imperative additive tail words ("please add them"): an explicit
# instruction, unlike question framing ("how many more?"), so it resolves
# the implicit add and waives the like-unit guard.
_IMPERATIVE_ADD_WORDS = {"add", "added"}

# Count-noun after the second operand that turns it into a multiplier
# ("three claws strike together" / "has two claws"): every corpus-accepted
# example is a product. Matched on the collapsed atom directly after the
# operand, or on two merged atoms (the obfuscator splits it into "cla ws").
_COUNT_NOUN = "claws"

# Question-tail cue words that imply an operation over the two operands when
# no explicit operation sits between them. "sum"/"combined" live here rather
# than in _OP_WORDS: all nine corpus occurrences are trailing question cues
# ("what is the combined force?"), never between-operand operators — and as
# operators they aborted challenges where a split "swims um" merged into a
# spurious leading "sum". "product"/"times"/"multiplied" stay _OP_WORDS and
# are reclassified by position in _resolve.
_ADDITIVE_CUES = {"total", "sum", "combined"}

# Safe continuation material directly after the second operand of an implicit
# add: the question itself may follow instead of a unit word.
_QUESTION_WORDS = {"what", "whats", "how", "total", "sum", "combined"}

# Fuzzy matching floors: a number word may be recovered at edit distance 1
# from its CANONICAL spelling only when the merged token is >= 4 letters
# ("trwo" -> two, "fife" -> five, but never a 3-letter prose token like
# "for" -> four), an operation verb only when token and word are >= 6
# letters. Targets are the canonical (uncollapsed) spellings: comparing
# against collapsed lexicon keys would grant double-lettered words a free
# extra edit ("there" is one edit from collapsed "thre" but two from
# "three").
_FUZZY_MIN_TOKEN = 4
_FUZZY_MIN_OP = 6
# Round 7: a LONG merged token (>= 6 letters) may additionally be recovered
# at edit distance 1 from the COLLAPSED canonical spelling — the corpus
# combines misspelling with letter doubling inside a split word ("fowr teen"
# merges to "fowrten": two edits from "fourteen" but one from its collapsed
# form "fourten"). Operation verbs already compare against their collapsed
# form; this extends the same treatment to number words, with a higher floor
# than _FUZZY_MIN_TOKEN because the collapsed target is one edit "cheaper".
_FUZZY_MIN_NUM_COLLAPSED = 6

# How many atoms past the second operand a postfix operator may sit and still
# bind to it ("twelve <unit> less", "three times <that>") — one intervening
# unit/filler atom, no more. A farther trailing operation word is question
# framing ("... how many less?"), which must not be read as the operator.
_POSTFIX_ADJACENCY = 2

# Common prose words that sit one edit from a number word and would
# otherwise be misread as operands ("then" -> ten, "once"/"ones"/"none" ->
# one, "fight"/"right" and the rest of the -ight family -> eight; the corpus
# says "dominance fight" in 40 of 601 challenges and "right claw" in 5).
# Corpus-checked via the replay harness.
_FUZZY_STOPWORDS = {
    "then",
    "once",
    "ones",
    "none",
    "there",
    "fight",
    "fights",
    "right",
    "light",
    "might",
    "night",
    "sight",
    "tight",
    "weight",
}

# One atom per scan step: a run of letters OR a single signal-operator
# symbol, in textual order. Other punctuation (obfuscation noise) is dropped,
# but operator symbols keep their position relative to the number words.
_ATOM_RE = re.compile(r"[a-z]+|[+*]")


def _collapse_repeats(text: str) -> str:
    """Collapse every run of an identical character to one (``aa`` -> ``a``).

    This neutralises the obfuscator's letter doubling (``twennty`` ->
    twenty). Number/operation lexicons are keyed on collapsed forms so both
    clean and letter-doubled spellings compare consistently.
    """
    return re.sub(r"(.)\1+", r"\1", text)


_CANONICAL_NUMBERS = {**_UNITS, **_TEENS, **_TENS}
_NUMBER_WORDS = {_collapse_repeats(word): value for word, value in _CANONICAL_NUMBERS.items()}
_TENS_VALUES = frozenset(_TENS.values())
_OP_TOKENS = {_collapse_repeats(word): op for word, op in _OP_WORDS.items()}
# Collapsed token -> canonical word, for the few rules keyed on the exact
# verb ("add" imperative vs "more" framing). Collapsed keys are unique
# across _OP_WORDS ("add" -> "ad", "adds" -> "ads").
_OP_TOKEN_WORDS = {_collapse_repeats(word): word for word in _OP_WORDS}
_AND_COLLAPSED = _collapse_repeats("and")
_CUE_TOKEN_WORDS = {_collapse_repeats(word): word for word in _ADDITIVE_CUES}
_MARKER_TOKENS = {_collapse_repeats(word) for word in _MUL_MARKER_WORDS}
_POSSESSED_COUNT_SUFFIXES = tuple(
    _collapse_repeats(subject + verb)
    for subject in _SAME_SUBJECT_WORDS
    for verb in _POSSESSION_VERBS
)
_QUESTION_TOKENS = {_collapse_repeats(word) for word in _QUESTION_WORDS}

# Longest candidate a merge can produce: the longest canonical word plus the
# one extra character fuzzy matching tolerates. Compared against the
# COLLAPSED merged token (letter doubling can make the raw run arbitrarily
# longer, so a raw-length bound would blind the scanner to doubled words).
_MAX_TOKEN_LEN = (
    max(len(word) for word in (*_CANONICAL_NUMBERS, *_OP_WORDS, *_MUL_MARKER_WORDS)) + 1
)
# Fragment-count cap for one merge: the corpus splits a word across at most
# ~6 fragments; 12 leaves margin while bounding scan cost on adversarial
# many-atom input.
_MAX_MERGE_ATOMS = 12


class _Abstain(Exception):
    """Internal signal: the challenge is ambiguous — fail closed to None."""


def _within_one_edit(a: str, b: str) -> bool:
    """True when Levenshtein distance between ``a`` and ``b`` is exactly 1."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1 or a == b:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    # ``b`` is one longer: skip exactly one character of ``b``.
    i = 0
    while i < la and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :]


class _NumEvent(NamedTuple):
    value: int
    is_tens: bool
    atom_start: int
    atom_end: int


class _OpEvent(NamedTuple):
    op: str
    atom_index: int
    is_symbol: bool
    # Canonical lexicon word that produced this event (None for symbol ops
    # and fuzzy matches). Only exact-match words drive word-keyed rules
    # (the "add" imperative), so fuzzy recovery does not need to carry one.
    word: Optional[str] = None


class _AndEvent(NamedTuple):
    atom_index: int


class _CueEvent(NamedTuple):
    atom_index: int
    word: str


class _MulMarkerEvent(NamedTuple):
    atom_index: int


_Event = Union[_NumEvent, _OpEvent, _AndEvent, _CueEvent, _MulMarkerEvent]


class _Operand(NamedTuple):
    value: int
    atom_start: int
    atom_end: int


def code_parse_challenge(challenge_text: str) -> Optional[str]:
    """Parse the finite CAPTCHA grammar deterministically.

    Returns the answer formatted to two decimals (e.g. ``"44.00"``) only when
    the operands and operations recovered from the challenge interleave into
    exactly one unambiguous computation; otherwise ``None`` so the LLM solver
    chain runs.
    """
    if not challenge_text or len(challenge_text) > _MAX_INPUT:
        return None
    normalized = challenge_text.lower().replace("0", "o")
    atoms = _ATOM_RE.findall(normalized)
    try:
        events = _dedup_numbers(_scan(atoms))
        operands = _compose_operands(events)
        return _resolve(operands, events, atoms)
    except _Abstain:
        return None


class _Lexeme(NamedTuple):
    kind: str
    value: Union[int, str, None] = None
    # Canonical lexicon word behind the match, where a rule needs it
    # (op imperatives, cue "sum"); None for fuzzy ops and non-word kinds.
    word: Optional[str] = None


def _match_exact(token: str) -> Optional[_Lexeme]:
    """Look up a collapsed merged token in the exact lexicons."""
    if token in _NUMBER_WORDS:
        return _Lexeme("num", _NUMBER_WORDS[token])
    if token in _OP_TOKENS:
        return _Lexeme("op", _OP_TOKENS[token], _OP_TOKEN_WORDS[token])
    if token == _AND_COLLAPSED:
        return _Lexeme("and")
    if token in _CUE_TOKEN_WORDS:
        return _Lexeme("cue", None, _CUE_TOKEN_WORDS[token])
    if token in _MARKER_TOKENS:
        return _Lexeme("mark")
    return None


def _match_fuzzy(token: str) -> Optional[_Lexeme]:
    """Recover a homophone-misspelled number word or operation verb.

    Edit distance exactly 1 after collapse, with per-kind length floors.
    All candidates must agree on one result (value or operator); two
    different plausible readings poison the whole parse (raises _Abstain)
    rather than letting either reading win — the corpus shows a silently
    dropped number word produces a confident wrong answer.
    """
    if token in _FUZZY_STOPWORDS:
        return None
    results: set[tuple[str, Union[int, str]]] = set()
    if len(token) >= _FUZZY_MIN_TOKEN:
        for word, value in _CANONICAL_NUMBERS.items():
            if _within_one_edit(token, word):
                results.add(("num", value))
    if len(token) >= _FUZZY_MIN_NUM_COLLAPSED:
        # Misspelling combined with letter doubling ("fowr teen" ->
        # "fowrten"): one edit from the collapsed canonical spelling
        # (_NUMBER_WORDS is already keyed on collapsed forms). The higher
        # floor keeps short prose tokens out (the collapsed target is one
        # edit "cheaper" than the canonical one).
        for collapsed_word, value in _NUMBER_WORDS.items():
            if _within_one_edit(token, collapsed_word):
                results.add(("num", value))
    if len(token) >= _FUZZY_MIN_OP:
        # Ops also compare against their collapsed form: a doubled AND
        # misspelled verb ("accellarates" -> "acelarates") is two edits from
        # the canonical spelling but one from the collapsed one. Numbers get
        # the same treatment only above _FUZZY_MIN_NUM_COLLAPSED — they
        # become operands, where a false positive is a wrong submitted
        # answer, not just a wrong verb reading.
        for word, op in _OP_WORDS.items():
            if len(word) < _FUZZY_MIN_OP:
                continue
            if _within_one_edit(token, word) or _within_one_edit(token, _collapse_repeats(word)):
                results.add(("op", op))
    if not results:
        return None
    if len(results) > 1:
        # Deliberate: ambiguity at the longest merge length abandons the
        # whole parse instead of backing off to a shorter merge — a shorter
        # reading that "works" around a poisoned token is exactly the
        # silent-drop failure mode this rule exists to prevent.
        raise _Abstain
    kind, matched = next(iter(results))
    return _Lexeme(kind, matched)


def _scan(atoms: list[str]) -> list[_Event]:
    """Tokenise into ordered number / operation / connective / cue events.

    Lexicon words are reconstructed by greedy whole-token merging of
    consecutive letter atoms (longest merge first, never crossing an operator
    symbol, bounded by the longest lexicon word). Exact matches win; fuzzy
    recovery runs only where no exact merge matched.
    """
    events: list[_Event] = []
    i = 0
    total = len(atoms)
    while i < total:
        atom = atoms[i]
        symbol_op = _SYMBOL_OPS.get(atom)
        if symbol_op is not None:
            events.append(_OpEvent(symbol_op, i, True))
            i += 1
            continue

        # Candidate tokens per merge length: collapsed concatenations of
        # whole consecutive atoms, never crossing an operator symbol, capped
        # by fragment count and by collapsed length (raw length is
        # meaningless under letter doubling).
        run_tokens: list[str] = []
        merged_raw = ""
        run_end = i
        while (
            run_end < total
            and atoms[run_end] not in _SYMBOL_OPS
            and len(run_tokens) < _MAX_MERGE_ATOMS
        ):
            merged_raw += atoms[run_end]
            token = _collapse_repeats(merged_raw)
            if len(token) > _MAX_TOKEN_LEN:
                break
            run_tokens.append(token)
            run_end += 1

        matched = False
        for matcher in (_match_exact, _match_fuzzy):
            for length in range(len(run_tokens), 0, -1):
                token = run_tokens[length - 1]
                result = matcher(token)
                if result is None:
                    continue
                last = i + length - 1
                if result.kind == "num" and isinstance(result.value, int):
                    events.append(_NumEvent(result.value, result.value in _TENS_VALUES, i, last))
                elif result.kind == "op" and isinstance(result.value, str):
                    events.append(_OpEvent(result.value, i, False, result.word))
                elif result.kind == "and":
                    events.append(_AndEvent(i))
                elif result.kind == "mark":
                    events.append(_MulMarkerEvent(i))
                else:
                    events.append(_CueEvent(i, result.word or ""))
                i += length
                matched = True
                break
            if matched:
                break
        if not matched:
            i += 1
    return events


def _dedup_numbers(events: list[_Event]) -> list[_Event]:
    """Drop a number event that immediately repeats the previous one.

    The obfuscator writes a number word twice (a split form followed by a
    clean repeat: ``tw ellv e twelve``, ``thirty two two``). Only *directly*
    consecutive equal values collapse — any intervening operation, "and", or
    cue event keeps both (``forty + seven ... seven`` stays a chain).
    """
    deduped: list[_Event] = []
    for event in events:
        previous = deduped[-1] if deduped else None
        if (
            isinstance(event, _NumEvent)
            and isinstance(previous, _NumEvent)
            and previous.value == event.value
            and previous.is_tens == event.is_tens
        ):
            # Keep one event spanning both occurrences, so downstream
            # atom-adjacency guards look past the duplicate.
            deduped[-1] = previous._replace(atom_end=event.atom_end)
            continue
        deduped.append(event)
    return deduped


def _compose_operands(events: list[_Event]) -> list[_Operand]:
    """Fold number events into operands, compounding tens + unit.

    A unit word (1-9) merges onto a directly preceding tens word only when no
    other event intervened ("thirty six" -> 36, while "thirty plus five" and
    "thirty and five" stay separate operands). Unmatched prose atoms carry no
    event and therefore never interrupt the compound (``forty antenna plus
    two`` still reads forty).
    """
    operands: list[_Operand] = []
    pending: Optional[_NumEvent] = None
    interrupted = False

    def flush() -> None:
        nonlocal pending, interrupted
        if pending is not None:
            operands.append(_Operand(pending.value, pending.atom_start, pending.atom_end))
        pending = None
        interrupted = False

    for event in events:
        if not isinstance(event, _NumEvent):
            if pending is not None:
                interrupted = True
            continue
        if event.is_tens:
            flush()
            pending = event
        elif pending is not None and 1 <= event.value <= 9 and not interrupted:
            operands.append(
                _Operand(pending.value + event.value, pending.atom_start, event.atom_end)
            )
            pending = None
            interrupted = False
        else:
            flush()
            operands.append(_Operand(event.value, event.atom_start, event.atom_end))
    flush()
    return operands


def _resolve(operands: list[_Operand], events: list[_Event], atoms: list[str]) -> Optional[str]:
    """Fit ops/cues around the operands and compute, or abstain.

    Grammar: operands and explicit operations must interleave strictly —
    every gap between consecutive operands carries exactly one agreed
    operation, and anything after the last operand must be consistent with
    it. A two-operand challenge with an empty gap may still resolve through
    the guarded implicit rules (question-tail add/multiply, adjacent postfix
    operator).
    """
    if len(operands) < 2:
        return None

    ops = [e for e in events if isinstance(e, _OpEvent)]
    ands = [e for e in events if isinstance(e, _AndEvent)]
    cues = [e for e in events if isinstance(e, _CueEvent)]
    marks = [e for e in events if isinstance(e, _MulMarkerEvent)]
    last = operands[-1]

    # Position classification (atom indices). Head/tail symbols are noise;
    # a head word-operation is question framing ("how many more ...") and
    # poisons the read.
    gap_ops: list[list[str]] = [[] for _ in range(len(operands) - 1)]
    tail_word_ops: list[_OpEvent] = []
    for op in ops:
        if op.atom_index < operands[0].atom_start:
            if not op.is_symbol:
                return None
            continue
        if op.atom_index > last.atom_end:
            if not op.is_symbol:
                tail_word_ops.append(op)
            continue
        for gap, (left, right) in enumerate(zip(operands, operands[1:])):
            if left.atom_end < op.atom_index < right.atom_start:
                gap_ops[gap].append(op.op)
                break
        else:
            # Inside an operand's own atom range — impossible by construction.
            return None

    # Multiplicative markers by position: a marker between two operands
    # makes that gap a product ("the force is doubled by two"), beating a
    # generic change-verb in the same gap ("increases ... by a factor
    # seven"); any other op word alongside a marker is a real conflict and
    # abstains through the len(f) > 1 check. A marker BEFORE the first
    # operand poisons the read like a head op word does (zero corpus
    # occurrences — an unmodeled phrasing, so abstain rather than let the
    # additive path silently override a multiplicative cue). Markers after
    # the last operand feed the tail rules below; a non-adjacent trailing
    # marker is scene noise ("...physicx factors").
    tail_marks: list[_MulMarkerEvent] = []
    for mark in marks:
        if mark.atom_index < operands[0].atom_start:
            return None
        if mark.atom_index > last.atom_end:
            tail_marks.append(mark)
            continue
        for gap, (left, right) in enumerate(zip(operands, operands[1:])):
            if left.atom_end < mark.atom_index < right.atom_start:
                if not gap_ops[gap] or set(gap_ops[gap]) == {_ADD_CHANGE}:
                    gap_ops[gap] = [_MUL]
                else:
                    gap_ops[gap].append(_MUL)
                break

    # A change-verb alongside a plain add in the same gap ("...collide and+
    # increases by seven") is agreement, not conflict: both mean add, and
    # the explicit "+" removes the change-verb's marker-override
    # eligibility. Collapse before the ambiguity check.
    filled = [
        {_ADD if op == _ADD_CHANGE else op for op in g} if set(g) >= {_ADD, _ADD_CHANGE} else set(g)
        for g in gap_ops
    ]
    if any(len(f) > 1 for f in filled):
        return None

    tail_cues = [c for c in cues if c.atom_index > last.atom_end]

    if all(filled):
        chain = [next(iter(f)) for f in filled]
        # Tail operations must restate the last step ("gains eight more") or
        # be a multiplicative/divisive contradiction — then abstain. One
        # exception (round 7, twin-confirmed): an ADJACENT multiplicative
        # tail after a single change-verb gap ("increases it by three
        # times") overrides the change-verb to multiply.
        contradicting = [
            op for op in tail_word_ops if _normalize_op(op.op) != _normalize_op(chain[-1])
        ]
        if contradicting:
            override = (
                chain == [_ADD_CHANGE]
                and all(op.op == _MUL for op in contradicting)
                and any(op.atom_index - last.atom_end <= _POSTFIX_ADJACENCY for op in contradicting)
            )
            if not override:
                return None
            chain = [_MUL]
        # A subtraction chain against a trailing "combined" cue ("another
        # lobster slows by fifteen ... what's the combined velocity?") is
        # contradictory: every corpus-accepted "combined" is additive, and
        # the subtract reading was server-rejected — abstain, never guess.
        if any(_normalize_op(op) == _SUB for op in chain) and any(
            c.word == "combined" for c in tail_cues
        ):
            return None
        return _compute_chain(operands, [_normalize_op(op) for op in chain])

    if len(operands) != 2 or any(filled):
        # Chains (3+) never resolve implicitly; a half-filled two-operand
        # read is contradictory.
        return None
    return _resolve_implicit(operands, tail_word_ops, tail_marks, ands, tail_cues, atoms)


def _resolve_implicit(
    operands: list[_Operand],
    tail_word_ops: list[_OpEvent],
    tail_marks: list[_MulMarkerEvent],
    ands: list[_AndEvent],
    tail_cues: list[_CueEvent],
    atoms: list[str],
) -> Optional[str]:
    """Resolve two operands with no explicit operation between them.

    Priority: a multiplicative signal (specific) beats the additive question
    cue (generic); a postfix subtraction requires immediate adjacency; the
    implicit add requires the connective, the cue, and the unit guard —
    unless an explicit arithmetic instruction ("sum" / "add them") waives
    the unit guard.
    """
    first, second = operands
    and_between = any(first.atom_end < a.atom_index < second.atom_start for a in ands)
    cue_after = bool(tail_cues)

    mult_tail = [op for op in tail_word_ops if op.op == _MUL]
    sub_tail = [op for op in tail_word_ops if op.op == _SUB]
    other_tail = [op for op in tail_word_ops if op.op not in (_MUL, _SUB)]

    # A trailing multiplicative marker counts as evidence only when ADJACENT
    # to the second operand — unlike a trailing multiplicative VERB, whose
    # non-adjacent "what is the product?" question form is corpus-attested,
    # a distant marker is scene noise ("...physicx factors what is total
    # force?" is an implicit add) exactly as in the explicit-chain path
    # (found by codex-review: the noise rule was applied to one path only).
    # A between-operand marker was already folded into the gap by _resolve
    # and never reaches here.
    adjacent_marks = [m for m in tail_marks if m.atom_index - second.atom_end <= _POSTFIX_ADJACENCY]
    if mult_tail or adjacent_marks:
        if sub_tail:
            return None
        adjacent = bool(adjacent_marks) or any(
            op.atom_index - second.atom_end <= _POSTFIX_ADJACENCY for op in mult_tail
        )
        if and_between or adjacent:
            return _compute_chain(operands, [_MUL])
        return None
    if sub_tail:
        if other_tail:
            return None
        # The same subtract-vs-"combined" contradiction the explicit-chain
        # path abstains on (found by python-reviewer: the guard covered one
        # path only).
        if any(c.word == "combined" for c in tail_cues):
            return None
        if all(op.atom_index - second.atom_end <= _POSTFIX_ADJACENCY for op in sub_tail):
            return _compute_chain(operands, [_SUB])
        return None
    # A bare trailing additive verb ("... how many more?") is question
    # framing, not an operator — except the imperative "please add them",
    # an explicit instruction which resolves the add below.
    imperative_add = bool(other_tail) and all(op.word in _IMPERATIVE_ADD_WORDS for op in other_tail)
    if other_tail and not imperative_add:
        return None

    # Count multiplier: "twenty five newtons and three claws" — a claw
    # count directly after the second operand multiplies the per-claw
    # magnitude (every corpus-accepted example is a product).
    if and_between and cue_after and _count_noun_after(atoms, second.atom_end):
        return _compute_chain(operands, [_MUL])

    # Implicit add: "X <unit> and Y <unit>, what is the total?"
    if not (and_between and (cue_after or imperative_add)):
        return None
    unit_first = _adjacent_atom(atoms, first.atom_end)
    unit_second = _adjacent_atom(atoms, second.atom_end)
    if unit_first is None or unit_second is None:
        return None
    # A same-subject bare possessed count ("...and it has twoo, whats total
    # force?") is ambiguous: corpus "has" adds when another entity holds the
    # quantity ("the weaker claw has fourteen") but multiplies when the same
    # subject possesses a count of claws, and here the count noun was
    # mangled away — abstain rather than guess either way. The lookback is
    # merge-aware ("i t ha s two" still reads as "it has"; found by
    # codex-review: a raw single-atom check missed the split form).
    if unit_second in _QUESTION_TOKENS and _possessed_bare_count(atoms, second):
        return None
    # An explicit arithmetic instruction ("what is the sum of these" /
    # "please add them") waives the like-unit guard: the corpus pairs
    # unlike quantities (velocity + force) under an explicit sum, and the
    # multiplicative reading was server-rejected.
    explicit_add = imperative_add or any(c.word == "sum" for c in tail_cues)
    # Fuzzy unit pairing needs the same length floor as every other fuzzy
    # comparison in this module: two short noise fragments ("me"/"ne") sit
    # one edit apart far too easily. Exact equality has no floor (the corpus
    # abbreviates units down to "cm", and equal short units are real signal).
    like_units = unit_first == unit_second or (
        len(unit_first) >= _FUZZY_MIN_TOKEN
        and len(unit_second) >= _FUZZY_MIN_TOKEN
        and _within_one_edit(unit_first, unit_second)
    )
    if not (like_units or unit_second in _QUESTION_TOKENS or explicit_add):
        return None
    return _compute_chain(operands, [_ADD])


def _adjacent_atom(atoms: list[str], atom_end: int) -> Optional[str]:
    """Collapsed form of the atom immediately after ``atom_end``, if any."""
    if atom_end + 1 >= len(atoms):
        return None
    return _collapse_repeats(atoms[atom_end + 1])


# How many atoms before an operand boundary the possession lookback joins:
# "it has" splits into at most ~4 fragments in the corpus ("i t ha s").
_POSSESSION_LOOKBACK_ATOMS = 4


def _possessed_bare_count(atoms: list[str], operand: _Operand) -> bool:
    """True for the same-subject possession form "it has/uses" directly
    before ``operand``.

    Atom-boundary-free: the fuzzy number merge can absorb a leading fragment
    of the verb into the operand itself ("ha s two" scans as "ha" + a num
    event spanning "s two"), so instead of walking atoms backwards this
    joins the few atoms before EITHER operand boundary and checks the
    collapsed suffix. A false positive here only abstains (coverage loss,
    never a wrong answer).
    """
    for boundary in {operand.atom_start, operand.atom_end}:
        window = "".join(atoms[max(0, boundary - _POSSESSION_LOOKBACK_ATOMS) : boundary])
        if _collapse_repeats(window).endswith(_POSSESSED_COUNT_SUFFIXES):
            return True
    return False


def _count_noun_after(atoms: list[str], atom_end: int) -> bool:
    """True when the atom(s) right after ``atom_end`` spell the count noun.

    The obfuscator may split the noun across two atoms ("cla ws"), so a
    two-atom merge is also accepted.
    """
    nxt = _adjacent_atom(atoms, atom_end)
    if nxt == _COUNT_NOUN:
        return True
    if nxt is None or atom_end + 2 >= len(atoms):
        return False
    return _collapse_repeats(atoms[atom_end + 1] + atoms[atom_end + 2]) == _COUNT_NOUN


def _compute_chain(operands: list[_Operand], chain: list[str]) -> Optional[str]:
    """Left-fold the operand values, abstaining on any out-of-domain step.

    The physical-count CAPTCHA domain is non-negative: a negative
    intermediate or final value, a division by zero, or a non-finite result
    signals a misparse, not a real answer.
    """
    result = Decimal(operands[0].value)
    try:
        for op, operand in zip(chain, operands[1:]):
            right = Decimal(operand.value)
            if op == _ADD:
                result += right
            elif op == _SUB:
                result -= right
            elif op == _MUL:
                result *= right
            elif op == _DIV:
                result /= right
            else:
                return None
            if not result.is_finite() or result < 0:
                return None
    except (DivisionByZero, InvalidOperation):
        return None
    return f"{result:.2f}"
