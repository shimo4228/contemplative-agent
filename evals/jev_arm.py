#!/usr/bin/env python3
"""RFC-0043 round 2: the Jev arms (J1 Noul, J2 Choice) — operator-run, private.

Replays the SAME rows the round-1 arms ran on (the ``selection_id`` set frozen
in round 1's ``rows.jsonl``) through TypeSafe's hosted System One endpoint, so
the skill-selection question is asked once more by a model built to answer
typed judgments rather than to generate names.

**Why this file lives in ``evals/`` and not in ``scripts/``.** Every call sends
a past situation off-machine. ``tests/test_cloud_egress_absence.py`` keeps the
shipped package and the scheduled Python (``src/`` and ``scripts/*.py``) free of
hosted-model egress and names ``evals/`` as the one home for an operator-run
one-shot — the same standing ``evals/judging.py::run_claude_raw`` has. Nothing
under ``src/`` or ``scripts/`` imports this module, and
``tests/test_jev_results_stay_private.py`` pins that.

**The numbers stay private.** The TypeSafe Master Customer Agreement (updated
2026-08-27, read 2026-09-20) lists "publish benchmarks or performance
information about the Services" among customer restrictions, 2.3(f), and 2.3(b)
covers distillation and training a model to imitate the output. So: output goes
to ``.notes/`` only (``assert_private_output`` refuses anything else), the arm
labels never enter ``docs/``, and these answers are consumed as a reading — not
as teacher data, few-shot examples or a fine-tuning corpus.

**The API key belongs to the human.** It is read at call time from
``TYPESAFE_API_KEY`` or ``~/.config/typesafe/api_key`` and carried in an opaque
:class:`ApiKey` whose ``repr`` is redacted, so a traceback, a log line or a row
record cannot print it. With no key the run makes zero requests and reports
``jev_key_missing``.

**Rate limits are a policy signal, not a transient error** (rule
``debugging.md``: pushing through one cost the owner an account). TypeSafe's
docs recommend exponential backoff for 429/529; this run does the opposite on
purpose — one wait, one retry, and three rate-limited rows in a row stop the
whole run with ``jev_rate_limited_stop``.

API contract, read from the live docs on 2026-09-20 (``docs.typesafe.ai/api.md``,
``primitives/noul.md``, ``primitives/choice.md``, ``concepts/state.md``,
``models.md``): ``POST https://api.typesafe.ai/v1/systemone``, ``Authorization:
Bearer``, body ``{state, model, questions}`` where ``questions`` is a MAP of
question id to question object. A Noul answers ``{"noul": 0..1}``; a Choice
answers ``{"choice", "probabilities", "confidence"}`` over at most 255 options.
``usage.input_tokens`` comes back per request. Budget: 64k tokens per request,
32k for ``state`` plus the longest single question.

Usage::

    # smoke (3 rows)
    uv run --no-sync python -m evals.jev_arm \\
        --rows .notes/skillsel-arm-replay/full-20260919/rows.jsonl --limit 3

    # the full run the owner launches
    uv run --no-sync python -m evals.jev_arm \\
        --rows .notes/skillsel-arm-replay/full-20260919/rows.jsonl --resume
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, TextIO

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA = "skillsel-arm-replay/1"

# The one destination this module may reach. Named once so the absence guard in
# tests/test_jev_results_stay_private.py has a single string to look for.
API_URL = "https://api.typesafe.ai/v1/systemone"

# Pinned to a version, never an alias: `jev-latest` and `jev-preview` both point
# at 1.13.0 today (models.md, 2026-09-20) and would silently re-point later,
# which would make two halves of one reading two different models.
DEFAULT_MODEL = "jev-1.13.0"

KEY_ENV = "TYPESAFE_API_KEY"
KEY_FILE = Path.home() / ".config" / "typesafe" / "api_key"

# Row-log arm labels. Both start with "J" so a public-side check for the private
# arms has one prefix to look for.
NOUL_LABEL = "J1/jev/noul"
CHOICE_LABEL = "J2/jev/choice"

# Context budget from models.md (2026-09-20). Two separate ceilings: the whole
# request, and `state` plus the LONGEST single question.
REQUEST_TOKEN_CAP = 64_000
STATE_PLUS_QUESTION_TOKEN_CAP = 32_000

# Characters per token used to plan the batches. Deliberately pessimistic: the
# situations carry Japanese, where a token is closer to one character than to
# the ~4 an English-only estimate would assume. Over-estimating only splits a
# request that would have fit; under-estimating gets a 422 mid-run.
CHARS_PER_TOKEN = 2

# The Choice's no-match option. Choice's own page recommends adding one when the
# list may not cover the input, and the selection prompt's verdict space really
# does include "none". A phrase with spaces cannot collide with a catalog name
# (they are kebab-case identifiers); `choice_criteria` asserts it anyway.
NO_MATCH_OPTION = "none of the above"

# Reason codes. Every row that produced no answer carries exactly one, and the
# run prints the tally — a row never disappears silently (ADR-0075).
REASON_KEY_MISSING = "jev_key_missing"
REASON_RATE_LIMITED = "jev_rate_limited"
REASON_RATE_LIMITED_STOP = "jev_rate_limited_stop"
REASON_TIMEOUT = "jev_timeout"
REASON_HTTP = "jev_http_error"
REASON_MALFORMED = "jev_malformed_response"
REASON_STATE_TOO_LARGE = "jev_state_too_large"
REASON_ROW_NOT_FOUND = "jev_row_not_found"
REASON_NO_ANSWERS = "jev_no_answers"

# Statuses that stop the run on sight. A rejected key or a rejected body is a
# property of the request, not of the moment, so retrying 150 times would only
# spend the owner's quota re-learning the same fact.
FATAL_STATUSES = (401, 403, 422)
RATE_LIMIT_STATUSES = (429, 529)

# 429/529 handling. One wait, one retry; `Retry-After` when the server sends a
# plain-seconds value, else this default. The cap stops an odd or hostile header
# from parking the run for hours.
DEFAULT_RETRY_AFTER_S = 10
MAX_RETRY_AFTER_S = 120
MAX_CONSECUTIVE_RATE_LIMITED_ROWS = 3

# `config/prompts/skill_selection.md`'s rule, restated as a CONDITION rather
# than as the instruction it is there ("Select only the names of the skills
# whose trigger conditions are explicitly met by the provided situation. Do not
# select a skill merely because it seems generally useful."). A Noul answers
# whether a condition holds, so an imperative addressed to a generator would be
# the wrong grammar for it — the rule being applied is the same one.
#
# It is repeated inside every question because TypeSafe questions cannot see one
# another and the API has no system-prompt field: the whole judgment has to be
# in the question (concepts/state.md).
_SELECTION_CRITERION = (
    "A skill applies only when its trigger conditions are explicitly met by the "
    "situation. A skill that merely seems generally useful does not apply."
)


class ReplayRow(Protocol):
    """The part of round 1's ``Row`` this arm reads.

    Declared rather than imported: the module it comes from is loaded by path
    (``scripts/`` is not a package), so a Protocol is what gives the fields a
    type here — and it also states, in one place, exactly how much of round 1's
    row this arm depends on.
    """

    selection_id: str
    ts: str
    situation: str
    catalog: tuple[tuple[str, str], ...]
    logged_selected: tuple[str, ...]
    logged_rejected: tuple[str, ...]


# --------------------------------------------------------------------------
# Reuse of the round-1 reconstruction
# --------------------------------------------------------------------------


def _load_replay_module() -> ModuleType:
    """``scripts/skillsel_arm_replay.py`` as a module.

    ``scripts/`` is not a package, so this follows the precedent already set by
    ``tests/test_skillsel_arm_replay.py``: load it by file path under a fixed
    module name, reusing whatever instance is already registered. Round 1's
    ``split_prompt`` / ``parse_catalog`` / ``row_from_record`` are the fidelity
    contract — a copy here would be a second parser to keep in step with the
    prompt template, and the first drift would be invisible.

    The import direction is evals -> scripts, which no gate covers: the egress
    guard scans ``src/`` and ``scripts/`` (not ``evals/``), and its import check
    looks for the reverse direction, ``scripts`` -> ``evals``.
    """
    name = "skillsel_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = REPO_ROOT / "scripts" / "skillsel_arm_replay.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class ApiKey:
    """An API key that cannot print itself.

    ``repr`` and ``str`` are redacted, so the value cannot reach a traceback, a
    log line, an f-string or a row record by accident. The only way out is
    :meth:`auth_header`, which hands it straight to ``requests``.
    """

    _value: str

    def __repr__(self) -> str:
        return "<ApiKey redacted>"

    __str__ = __repr__

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._value}"}


def load_api_key(
    *, env: Mapping[str, str] | None = None, key_file: Path | None = None
) -> ApiKey | None:
    """The key from the environment, else the owner's file, else ``None``.

    ``None`` is a first-class outcome: the caller turns it into
    ``jev_key_missing`` and makes zero requests, rather than sending an
    unauthenticated call and reading the 401 as a finding about Jev.
    """
    source = os.environ if env is None else env
    raw = source.get(KEY_ENV, "")
    if raw.strip():
        return ApiKey(raw.strip())
    path = KEY_FILE if key_file is None else key_file
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return ApiKey(text)
    return None


# --------------------------------------------------------------------------
# Request construction (pure)
# --------------------------------------------------------------------------


def estimate_tokens(value: object) -> int:
    """A pessimistic token count for one JSON-serialisable value.

    Used only to decide how many questions fit in a request. It never has to be
    right, only never optimistic — see :data:`CHARS_PER_TOKEN`.
    """
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def build_state(situation: str) -> dict[str, str]:
    """The request's ``state``.

    A named JSON field rather than a bare string, which ``concepts/state.md``
    recommends whenever the state has a nameable part; it also labels the text
    as the thing being judged instead of as loose prose the model might read as
    addressed to it.
    """
    return {"situation": situation}


def noul_instructions(name: str, description: str) -> str:
    """One skill's yes/no judgment, self-contained.

    Question ids are not sent to the model (``concepts/state.md``), so the skill
    being asked about has to be named in the instructions themselves.
    """
    detail = f"`{name} — {description}`" if description else f"`{name}`"
    return f"{_SELECTION_CRITERION}\n\nDoes the learned skill {detail} apply to `situation`?"


def choice_criteria(catalog: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The Choice's options: every catalog skill, plus a no-match outcome.

    A collision raises rather than asserting: ``assert`` is stripped under
    ``python -O``, and an ``AssertionError`` here would kill the run mid-flight
    past the handler that writes the tally.
    """
    criteria = {name: (description or name) for name, description in catalog}
    if NO_MATCH_OPTION in criteria:
        raise RowUnaskable(f"a catalog name collides with the no-match option {NO_MATCH_OPTION!r}")
    criteria[NO_MATCH_OPTION] = "No skill in the catalog applies to this situation."
    return criteria


def choice_instructions() -> str:
    return (
        f"{_SELECTION_CRITERION}\n\n"
        "Which single learned skill applies best to `situation`? "
        f"Answer `{NO_MATCH_OPTION}` when none of them does."
    )


class RowUnaskable(ValueError):
    """This row cannot be turned into a request at all.

    A named exception rather than a bare ``ValueError``: the caller's handler
    used to be wide enough to also swallow, say, a ``ValueError`` raised while
    reading a malformed number out of a response, and file it under
    ``jev_state_too_large`` — a reason code naming a cause that did not happen.
    """


@dataclass(frozen=True)
class Question:
    """One question plus the catalog name it stands for.

    ``qid`` is synthetic rather than the skill name: ids are code's business
    and are not sent to the model, and a name carrying a character JSON keys
    dislike would otherwise become a request-shaping problem.
    """

    qid: str
    payload: dict[str, Any]
    skill: str | None  # None for the Choice


def build_questions(catalog: Sequence[tuple[str, str]]) -> list[Question]:
    """The Choice first, then one Noul per catalog skill.

    Choice leads so that, when the budget forces a split, the arm that reads a
    distribution over the WHOLE catalog stays in one request. Splitting the
    Nouls is harmless — each is scored on its own against the same state
    (``cookbooks/parallel_questions.md``) — but splitting a Choice would change
    what its probabilities are over.
    """
    questions = [
        Question(
            qid="choice",
            payload={
                "type": "choice",
                "instructions": choice_instructions(),
                "criteria": choice_criteria(catalog),
            },
            skill=None,
        )
    ]
    for index, (name, description) in enumerate(catalog):
        questions.append(
            Question(
                qid=f"n{index:04d}",
                payload={"type": "noul", "instructions": noul_instructions(name, description)},
                skill=name,
            )
        )
    return questions


def score_question(qid: str, instructions: str, levels: Sequence[str]) -> Question:
    """One Score question over ORDERED ``levels`` (RFC-0045).

    ``criteria`` as a list is the ordered form: the live API answered it with
    a ``legend`` and ``probabilities`` keyed by level index, ``"0"`` first
    (one request on synthetic state, 2026-09-24).
    """
    return Question(
        qid=qid,
        payload={"type": "score", "instructions": instructions, "criteria": list(levels)},
        skill=None,
    )


def plan_batches(
    state: object,
    questions: Sequence[Question],
    *,
    request_cap: int = REQUEST_TOKEN_CAP,
    state_question_cap: int = STATE_PLUS_QUESTION_TOKEN_CAP,
) -> list[list[Question]]:
    """Questions packed into as few requests as the two ceilings allow.

    Raises :class:`RowUnaskable` when ``state`` plus a SINGLE question already
    exceeds the per-question ceiling — that row cannot be asked at all, and the
    caller records ``jev_state_too_large`` rather than truncating the situation
    and reporting the answer as if the model had seen all of it.

    A known incompleteness: one oversized question fails the whole row, even
    when every other question would have fit. Left as a stop rather than a
    partial arm because at this sample's catalog size (54-57 skills, short
    descriptions) the Choice is ~3k estimated tokens against a 32k ceiling, so
    the branch is unreachable here — and a partial-arm path would be a second,
    never-exercised mode in a one-shot whose readings have to be comparable
    across rows. Named in the packet report rather than built.
    """
    state_tokens = estimate_tokens(state)
    batches: list[list[Question]] = []
    current: list[Question] = []
    current_tokens = 0
    for question in questions:
        size = estimate_tokens(question.payload)
        if state_tokens + size > state_question_cap:
            raise RowUnaskable(
                f"state ({state_tokens} est. tokens) plus question {question.qid} "
                f"({size}) exceeds the {state_question_cap}-token ceiling"
            )
        if current and state_tokens + current_tokens + size > request_cap:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(question)
        current_tokens += size
    if current:
        batches.append(current)
    return batches


def build_body(state: object, batch: Sequence[Question], model: str) -> dict[str, Any]:
    """One request body, exactly as ``api.md`` describes it."""
    return {
        "state": state,
        "model": model,
        "questions": {question.qid: question.payload for question in batch},
    }


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


class JevError(RuntimeError):
    """A failed call, carrying a reason code and never a response body."""

    def __init__(self, reason: str, *, status: int | None = None) -> None:
        self.reason = reason
        self.status = status
        super().__init__(reason + (f" (HTTP {status})" if status is not None else ""))


class JevFatal(JevError):
    """A failure that stops the run: a rejected key or a rejected body."""


class JevRateLimited(JevError):
    """429/529 that survived the one permitted retry."""

    def __init__(self, status: int) -> None:
        super().__init__(REASON_RATE_LIMITED, status=status)


def parse_retry_after(value: str | None) -> float:
    """Seconds to wait, from the header — clamped, never trusted blindly.

    A non-numeric value (the RFC also allows an HTTP date) and a negative one
    both fall back to the default rather than being parsed further: this waits
    once and then stops anyway, so precision here buys nothing.
    """
    seconds = float(DEFAULT_RETRY_AFTER_S)
    if value:
        try:
            parsed = float(value.strip())
        except ValueError:
            parsed = seconds
        if parsed >= 0:
            seconds = parsed
    return min(seconds, float(MAX_RETRY_AFTER_S))


@dataclass
class JevClient:
    """One POST, with the whole retry policy in one place.

    ``session`` carries the run's one connection (``main`` passes it; ~150
    requests to one host). ``sleep`` is injected so a test can drive the retry
    policy without waiting in real time.
    """

    key: ApiKey
    url: str = API_URL
    timeout: int = 60
    session: requests.Session | None = None
    sleep: Callable[[float], None] = time.sleep
    # RFC-0045's policy is stricter than the per-request one below: ONE
    # Retry-After wait per run, and the next 429/529 anywhere in the run raises
    # without waiting (packet S28, rule debugging.md). ``None`` keeps the
    # original per-request policy for the skill-selection run.
    max_rate_limit_waits: int | None = None
    rate_limit_waits_used: int = 0

    def _post(self, body: dict[str, Any]) -> requests.Response:
        poster = requests.post if self.session is None else self.session.post
        return poster(
            self.url,
            json=body,
            headers={**self.key.auth_header(), "Content-Type": "application/json"},
            timeout=self.timeout,
            allow_redirects=False,
        )

    def _send(self, body: dict[str, Any]) -> tuple[requests.Response, int]:
        started = time.monotonic()
        try:
            response = self._post(body)
        except requests.Timeout:
            raise JevError(REASON_TIMEOUT) from None
        except requests.RequestException:
            # `from None`: the transport exception's text can name the URL and
            # its `request` attribute holds the Authorization header. Only the
            # reason code travels onward, so neither can reach a traceback.
            raise JevError(REASON_HTTP) from None
        return response, int((time.monotonic() - started) * 1000)

    def ask(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """``(response payload, latency_ms)``.

        One retry, and only for a rate limit. A timeout is not retried: the
        request is large, and a second one doubles the tokens spent on a call
        that already did not come back.
        """
        for attempt in (1, 2):
            response, latency_ms = self._send(body)
            status = int(response.status_code)
            if status in FATAL_STATUSES:
                raise JevFatal(REASON_HTTP, status=status)
            if status not in RATE_LIMIT_STATUSES:
                return _payload_of(response, status), latency_ms
            if attempt == 2 or self._wait_budget_spent():
                raise JevRateLimited(status)
            self.rate_limit_waits_used += 1
            wait = parse_retry_after(response.headers.get("Retry-After"))
            print(f"  [rate limit] HTTP {status} — waiting {wait:.0f}s, one retry", flush=True)
            self.sleep(wait)
        raise JevRateLimited(RATE_LIMIT_STATUSES[0])  # pragma: no cover - loop returns first

    def _wait_budget_spent(self) -> bool:
        return (
            self.max_rate_limit_waits is not None
            and self.rate_limit_waits_used >= self.max_rate_limit_waits
        )


def _payload_of(response: requests.Response, status: int) -> dict[str, Any]:
    """The response body as the API contract describes it, or a reason code."""
    if status >= 400:
        raise JevError(REASON_HTTP, status=status)
    try:
        payload = response.json()
    except ValueError:
        raise JevError(REASON_MALFORMED) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise JevError(REASON_MALFORMED)
    return payload


# --------------------------------------------------------------------------
# Answer reading (pure)
# --------------------------------------------------------------------------


@dataclass
class RowAnswers:
    """What one row's requests produced, before it becomes a record."""

    noul: dict[str, float] = field(default_factory=dict)
    choice: str | None = None
    choice_probabilities: dict[str, float] = field(default_factory=dict)
    choice_confidence: float | None = None
    # Names the response used that are not in this row's catalog, scrubbed and
    # cut the way production treats arm A's rejected names. A first-class
    # column, not a dropped value: "which names did the model invent" is one of
    # the readings RFC-0043 exists for.
    rejected: list[str] = field(default_factory=list)
    # Numbers that came back non-finite or unreadable. Counted rather than
    # coerced — a NaN silently read as 0.0 would be a judgment the model did
    # not make (ADR-0075: no silent fallback).
    unreadable_numbers: int = 0
    requests: int = 0
    latency_ms: int = 0
    usage_input_tokens: int = 0


def _number(value: object) -> float | None:
    """``value`` as a FINITE float, or ``None``.

    ``True`` is not 1.0 here, and neither NaN nor an infinity is a probability.
    Letting one through would reach ``int()`` in the usage path (``OverflowError``
    on an infinity, ``ValueError`` on a NaN) and crash the run mid-way, or —
    worse — be caught by a broad handler upstream and recorded under some
    unrelated reason code.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _catalog_index(catalog: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Lower-cased name -> the catalog's own spelling.

    The same canonicalisation round 1's ceiling arm applies to model-authored
    names (``skillsel_arm_replay.run_ceiling``), so the two arms' name columns
    mean the same thing.
    """
    return {name.lower(): name for name, _description in catalog}


def _canonical(raw: object, by_lower: Mapping[str, str], into: RowAnswers) -> str | None:
    """A response-supplied name as the catalog spells it, or ``None``.

    Anything the catalog does not hold is recorded in ``rejected`` — scrubbed of
    control characters and cut to 80 characters, production's own treatment
    (``core/skill_selection.py``) — and never becomes a key in ``scores`` or an
    entry in ``selected``. The Choice's option names come back from a hosted
    model that was shown untrusted post text, so an unconstrained string from
    there must not land in the row log as if it were a skill.
    """
    from contemplative_agent.core._io import scrub_control

    text = str(raw)
    if text == NO_MATCH_OPTION:
        return NO_MATCH_OPTION
    canonical = by_lower.get(text.strip().lower())
    if canonical is None:
        into.rejected.append(scrub_control(text, 80))
    return canonical


def _read_choice(answer: Mapping[str, Any], into: RowAnswers, by_lower: Mapping[str, str]) -> None:
    choice = answer.get("choice")
    if choice is not None:
        into.choice = _canonical(choice, by_lower, into)
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, dict):
        canonical: dict[str, float] = {}
        for key, value in probabilities.items():
            number = _number(value)
            if number is None:
                into.unreadable_numbers += 1
                continue
            name = _canonical(key, by_lower, into)
            if name is not None:
                canonical[name] = number
        into.choice_probabilities = canonical
    into.choice_confidence = _number(answer.get("confidence"))


def read_answers(
    payload: Mapping[str, Any],
    batch: Sequence[Question],
    into: RowAnswers,
    *,
    catalog: Sequence[tuple[str, str]],
) -> None:
    """Fold one response into the row's answers.

    An answer that is missing or the wrong shape is left out rather than
    defaulted: a Noul recorded as 0.0 because the field was absent would read as
    "Jev said no", which is a different claim from "Jev did not answer".
    ``scored_of`` in the record is what keeps that difference visible.

    Every name that ends up in the record passes :func:`_canonical` — including
    the Noul side, where the name comes from this module's own question map and
    so always matches. Routing both through one gate is what makes "no
    response-supplied string is written as a skill name" a checkable property
    rather than an argument about which side the name came from.
    """
    by_lower = _catalog_index(catalog)
    answers = payload.get("answers") or {}
    by_id = {question.qid: question for question in batch}
    for qid, answer in answers.items():
        question = by_id.get(str(qid))
        if question is None or not isinstance(answer, dict):
            continue
        if question.skill is None:
            _read_choice(answer, into, by_lower)
            continue
        value = _number(answer.get("noul"))
        if value is None:
            into.unreadable_numbers += 1 if answer.get("noul") is not None else 0
            continue
        name = _canonical(question.skill, by_lower, into)
        if name is not None and name != NO_MATCH_OPTION:
            into.noul[name] = value
    usage = payload.get("usage")
    tokens = _number(usage.get("input_tokens")) if isinstance(usage, dict) else None
    if tokens is not None:
        into.usage_input_tokens += int(tokens)


# The two arms share every request, so neither one's latency or token count is
# its own. Said in the record rather than in a README nobody reads beside it.
_SHARED_NOTE = "J1 and J2 share the same request(s); latency and usage are row totals, not per-arm"


def arms_record(answers: RowAnswers, catalog_size: int) -> dict[str, dict[str, Any]]:
    """The row's two arm entries, in round 1's own row shape.

    **Both arms write ``selected: None`` beside ``scores``**, which is exactly
    how round 1 writes a scoring arm (``skillsel_arm_replay._arm_to_dict``), and
    round 1's ``_set_for`` reads ``scores`` FIRST. An entry carrying both would
    therefore have its ``selected`` silently ignored by every summary rule while
    ``write_adjudication`` still read it — one arm reporting two different sets.
    J2's winner keeps its own key, ``choice``, where nothing can mistake it for
    a collapsed set; the reading RFC-0043 wants from J2 is the rank anyway, and
    the argmax is recoverable from ``scores``.

    A row where nothing came back gets a reason code rather than empty
    ``scores``: ``_set_for`` would fall through empty scores to a ``None``
    ``selected`` and drop the row from ``_ceiling_pairs`` with no counter, which
    is the silent gap this module says it does not have.
    """
    choice_scores = {
        name: value
        for name, value in answers.choice_probabilities.items()
        if name != NO_MATCH_OPTION
    }
    if not answers.noul and not choice_scores:
        return failed_arms_record(REASON_NO_ANSWERS)
    shared: dict[str, Any] = {
        "latency_ms": answers.latency_ms,
        "usage_input_tokens": answers.usage_input_tokens,
        "requests": answers.requests,
        "unreadable_numbers": answers.unreadable_numbers,
        "note": _SHARED_NOTE,
    }
    # Non-catalog names the response used. They belong to the Choice — a Noul's
    # name comes from this module's own question map — so J1's list is empty by
    # construction, not because nobody looked.
    rejected = sorted(set(answers.rejected))
    return {
        NOUL_LABEL: {
            "selected": None,
            "rejected": [],
            "scores": {name: round(value, 6) for name, value in sorted(answers.noul.items())},
            "scored_of": [len(answers.noul), catalog_size],
            **shared,
        },
        CHOICE_LABEL: {
            "selected": None,
            "rejected": rejected,
            "scores": {name: round(value, 6) for name, value in sorted(choice_scores.items())},
            "scored_of": [len(choice_scores), catalog_size],
            "choice": answers.choice,
            "confidence": answers.choice_confidence,
            "no_match_probability": answers.choice_probabilities.get(NO_MATCH_OPTION),
            **shared,
        },
    }


def failed_arms_record(reason: str, *, status: int | None = None) -> dict[str, dict[str, Any]]:
    """Both arms as a named failure. Never a silent gap."""
    entry: dict[str, Any] = {"selected": None, "rejected": [], "reason": reason}
    if status is not None:
        entry["note"] = f"HTTP {status}"
    return {NOUL_LABEL: dict(entry), CHOICE_LABEL: dict(entry)}


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def read_selection_ids(rows_path: Path) -> list[str]:
    """Round 1's ``selection_id`` set, in round 1's own file order.

    The order is part of the sample: reading it here rather than re-deriving it
    from the seed means this arm cannot land on a different 150 rows if the
    window, the log or the sampler ever moves.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{rows_path} has an unparseable line: {exc}") from None
        selection_id = record.get("selection_id") if isinstance(record, dict) else None
        if not selection_id:
            raise SystemExit(f"{rows_path} has a line with no selection_id")
        if str(selection_id) not in seen:
            seen.add(str(selection_id))
            ids.append(str(selection_id))
    if not ids:
        raise SystemExit(f"{rows_path} holds no rows")
    return ids


def _selection_records(log_dir: Path) -> list[dict[str, Any]]:
    """Every selection record in the log directory, oldest file first.

    Every file is read rather than a day window: the sample is defined by ids,
    and a window that no longer reached the oldest of them would drop rows while
    looking like it had asked for all of them.
    """
    from contemplative_agent.core.selection_window import SELECTION_RECORD_KIND

    out: list[dict[str, Any]] = []
    for path in sorted(log_dir.glob("skill-selection-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and (
                record.get("kind", SELECTION_RECORD_KIND) == SELECTION_RECORD_KIND
            ):
                out.append(record)
    return out


def load_rows_by_id(
    log_dir: Path, wanted: Sequence[str], replay: ModuleType
) -> dict[str, ReplayRow]:
    """The wanted rows, rebuilt by round 1's own reconstruction."""
    want = set(wanted)
    found: dict[str, ReplayRow] = {}
    for record in _selection_records(log_dir):
        selection_id = str(record.get("selection_id") or "")
        if selection_id not in want or selection_id in found:
            continue
        row, _reason = replay.row_from_record(record)
        if row is not None:
            found[selection_id] = row
    return found


# --------------------------------------------------------------------------
# Output containment
# --------------------------------------------------------------------------


def assert_private_output(path: Path, *, notes_root: Path) -> Path:
    """Refuse any output path outside the gitignored ``.notes/`` tree.

    This is the mechanical half of "the Jev numbers stay private" (MCA 2.3(f)).
    Prose in a docstring would not survive one mistyped flag, and the mistake it
    prevents — an arm's numbers landing under ``docs/`` — is a publication, not
    a typo that can be reverted before anyone sees it.
    """
    resolved = Path(path).expanduser().resolve()
    root = notes_root.expanduser().resolve()
    if resolved == root or root not in resolved.parents:
        raise SystemExit(
            f"--out-rows={resolved} is outside {root} — the Jev arm writes only into "
            ".notes/ (TypeSafe MCA 2.3(f): the numbers are not published)"
        )
    return resolved


def load_done(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    """``(records, ids already answered)`` for ``--resume``."""
    if not path.is_file():
        return [], set()
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise SystemExit(
                f"{path} has an unparseable line — resuming would replay and double a row; "
                "truncate the file or give a fresh --out-rows"
            ) from None
        if not isinstance(record, dict):
            # Round 1 counts this malformed and refuses for the same reason a
            # broken line is refused: the row's id is absent from the resume
            # set, so it gets asked and appended a second time.
            raise SystemExit(
                f"{path} has a non-object line — resuming would replay and double a row; "
                "truncate the file or give a fresh --out-rows"
            )
        records.append(record)
    return records, {str(r.get("selection_id")) for r in records}


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def plan_row(row: ReplayRow) -> tuple[dict[str, str], list[list[Question]]]:
    """``(state, batches)`` for one row. Raises :class:`RowUnaskable`."""
    state = build_state(row.situation)
    return state, plan_batches(state, build_questions(row.catalog))


def run_batches(
    state: dict[str, str],
    batches: Sequence[Sequence[Question]],
    row: ReplayRow,
    client: JevClient,
    model: str,
) -> RowAnswers:
    """Every request this row needs, in order. Raises on a failed call."""
    answers = RowAnswers()
    for batch in batches:
        payload, latency_ms = client.ask(build_body(state, batch, model))
        answers.requests += 1
        answers.latency_ms += latency_ms
        read_answers(payload, batch, answers, catalog=row.catalog)
    return answers


def answer_row(row: ReplayRow, client: JevClient, model: str) -> dict[str, dict[str, Any]]:
    """One row's arms, with every non-fatal failure turned into a reason code.

    The planning and the sending are in SEPARATE handlers on purpose: one
    ``except ValueError`` around both would file a malformed number in a
    response under ``jev_state_too_large``, a reason code naming a cause that
    did not happen.

    :class:`JevFatal` is deliberately not caught: a rejected key or body is a
    property of the request, so the caller stops the run instead of writing 150
    identical failures.
    """
    try:
        state, batches = plan_row(row)
    except RowUnaskable:
        return failed_arms_record(REASON_STATE_TOO_LARGE)
    try:
        answers = run_batches(state, batches, row, client, model)
    except JevFatal:
        raise
    except JevError as exc:
        return failed_arms_record(exc.reason, status=exc.status)
    return arms_record(answers, len(row.catalog))


def record_for(
    selection_id: str, row: ReplayRow | None, arms: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """One row of the log, field for field as round 1 writes one.

    **"Merge" here means a per-``selection_id`` union of the ``arms`` dicts, not
    a concatenation of the two files.** Round 1's ``_ceiling_pairs`` needs the
    ceiling arm and the arm under test in the SAME row's ``arms``, so appending
    these records to round 1's rows.jsonl would leave J1 and J2 with no
    ceiling reading at all — and ``summarize`` skips an empty pair list without
    a word. The reader joins on ``selection_id`` first.

    ``schema`` is the one key round 1 does not write; the rest are its own
    fields with its own names, so a joined row is indistinguishable from one
    round 1 produced.
    """
    return {
        "schema": SCHEMA,
        "selection_id": selection_id,
        "ts": row.ts if row is not None else "",
        "catalog_count": len(row.catalog) if row is not None else 0,
        "logged_selected": list(row.logged_selected) if row is not None else [],
        "logged_rejected_count": len(row.logged_rejected) if row is not None else 0,
        "arms": arms,
    }


def _progress(arms: Mapping[str, Mapping[str, Any]]) -> str:
    """One short line per row. Never the situation, never a skill description."""
    parts: list[str] = []
    for label, entry in arms.items():
        reason = entry.get("reason")
        if reason:
            parts.append(f"{label}=ERR:{reason}")
        elif entry.get("selected") is not None:
            parts.append(f"{label}={len(entry['selected'] or [])}")
        else:
            parts.append(f"{label}=scores:{len(entry.get('scores') or {})}")
    return " ".join(parts)


@dataclass
class RunState:
    """What the loop carries between rows: the tally and the stop conditions."""

    tally: dict[str, int] = field(default_factory=dict)
    consecutive_rate_limited: int = 0
    stopped: str = ""

    def observe(self, arms: Mapping[str, Mapping[str, Any]]) -> None:
        """Count the row, and move the rate-limit streak — but only for rows
        that actually reached the network.

        A row that was never in the log made no request, so it is neither a
        rate-limited row nor evidence that the limit has lifted. Letting it
        reset the streak would let three refusals in a row go unnoticed as long
        as a missing row happened to sit between two of them.
        """
        reason = str(arms[NOUL_LABEL].get("reason") or "")
        if reason:
            self.tally[reason] = self.tally.get(reason, 0) + 1
        if reason == REASON_ROW_NOT_FOUND:
            return
        if reason == REASON_RATE_LIMITED:
            self.consecutive_rate_limited += 1
        else:
            self.consecutive_rate_limited = 0

    @property
    def must_stop(self) -> bool:
        return self.consecutive_rate_limited >= MAX_CONSECUTIVE_RATE_LIMITED_ROWS


def send_rows(
    ids: Sequence[str],
    rows: Mapping[str, ReplayRow],
    client: JevClient,
    handle: TextIO,
    *,
    model: str,
    done_ids: set[str],
) -> RunState:
    """The row loop. Writes as it goes so a stop keeps everything already paid for."""
    state = RunState()
    for index, selection_id in enumerate(ids, 1):
        if selection_id in done_ids:
            continue
        row = rows.get(selection_id)
        try:
            arms = (
                answer_row(row, client, model)
                if row is not None
                else failed_arms_record(REASON_ROW_NOT_FOUND)
            )
        except JevFatal as exc:
            print(
                f"stopping: HTTP {exc.status} — the key or the request body is rejected, "
                "so every remaining row would be too",
                flush=True,
            )
            state.stopped = f"{REASON_HTTP} (HTTP {exc.status})"
            break
        state.observe(arms)
        handle.write(json.dumps(record_for(selection_id, row, arms), ensure_ascii=False) + "\n")
        handle.flush()
        print(f"  [{index}/{len(ids)}] {selection_id[:8]} {_progress(arms)}", flush=True)
        if state.must_stop:
            print(
                f"{REASON_RATE_LIMITED_STOP}: {state.consecutive_rate_limited} rows in a row hit "
                "the limit — that is a policy signal, not a transient error, so the run stops "
                "here (rule debugging.md). Those rows are WRITTEN as failures, so --resume will "
                "skip them; re-ask them with a fresh --out-rows once the limit is understood",
                flush=True,
            )
            state.stopped = REASON_RATE_LIMITED_STOP
            break
    return state


def dry_run(ids: Sequence[str], rows: Mapping[str, ReplayRow]) -> int:
    """Report the request plan per row and send nothing."""
    for selection_id in ids:
        row = rows.get(selection_id)
        if row is None:
            continue
        state = build_state(row.situation)
        try:
            batches = plan_batches(state, build_questions(row.catalog))
        except ValueError as exc:
            print(f"  {selection_id[:8]} {REASON_STATE_TOO_LARGE}: {exc}", flush=True)
            continue
        print(
            f"  {selection_id[:8]} catalog={len(row.catalog)} "
            f"state~{estimate_tokens(state)}tok requests={len(batches)}",
            flush=True,
        )
    print("dry run — no request was sent", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RFC-0043 round 2: the private Jev arms (J1 Noul, J2 Choice).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    default_home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    parser.add_argument(
        "--rows",
        type=Path,
        required=True,
        help="round-1 rows.jsonl — the selection_id set and its order (read-only)",
    )
    parser.add_argument("--home", type=Path, default=default_home)
    parser.add_argument("--limit", type=int, default=0, help="first N rows only (0 = all)")
    parser.add_argument(
        "--out-rows", type=Path, default=Path(".notes/skillsel-arm-replay/jev/rows.jsonl")
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--resume", action="store_true", help="skip ids already in --out-rows")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan the requests and report the batch counts; send nothing",
    )
    return parser


# --------------------------------------------------------------------------
# RFC-0045: the relevance run (``python -m evals.jev_arm relevance``)
# --------------------------------------------------------------------------

# Labels in the relevance row log. They do not reuse the skill-selection
# labels: a different surface, a different question.
RELEVANCE_SCORE_LABEL = "J/score4"
RELEVANCE_NOUL_LABEL = "J/noul"
RELEVANCE_OUT_ROWS = Path(".notes/relevance-arm-replay/jev/rows.jsonl")


def load_relevance_module() -> ModuleType:
    """``scripts/relevance_arm_replay.py`` — the sample, the state, the questions.

    Loaded by path for the reason :func:`_load_replay_module` gives: one owner
    for the question text, so Jev is asked exactly what gemma, kev and von are.
    The direction is evals -> scripts; scripts/ never imports this module
    (tests/test_jev_results_stay_private.py).
    """
    name = "relevance_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = REPO_ROOT / "scripts" / "relevance_arm_replay.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_relevance_questions(rel: ModuleType) -> list[Question]:
    """The 4-level Score and the on-topic Noul, in the replay's own words."""
    return [
        score_question("score4", rel.SCORE_INSTRUCTIONS, rel.LEVELS),
        Question(
            qid="noul",
            payload={"type": "noul", "instructions": rel.NOUL_INSTRUCTIONS},
            skill=None,
        ),
    ]


def relevance_row(
    state: dict[str, str], client: JevClient, model: str, rel: ModuleType
) -> dict[str, dict[str, Any]]:
    """One post's two entries. Raises :class:`JevError` on a failed call."""
    payload, latency_ms = client.ask(build_body(state, build_relevance_questions(rel), model))
    score, noul = rel.systemone_entries(payload.get("answers") or {}, latency_ms)
    usage = payload.get("usage")
    tokens = _number(usage.get("input_tokens")) if isinstance(usage, dict) else None
    if tokens is not None:
        score["usage_input_tokens"] = int(tokens)
    return {RELEVANCE_SCORE_LABEL: score, RELEVANCE_NOUL_LABEL: noul}


def _relevance_failed(reason: str, status: int | None) -> dict[str, dict[str, Any]]:
    note = {"note": f"HTTP {status}"} if status is not None else {}
    return {label: {"reason": reason, "score": None, **note} for label in _RELEVANCE_LABELS}


_RELEVANCE_LABELS = (RELEVANCE_SCORE_LABEL, RELEVANCE_NOUL_LABEL)


def send_relevance_rows(
    rows: Sequence[Any],
    client: JevClient,
    handle: TextIO,
    *,
    model: str,
    domain: str,
    rel: ModuleType,
) -> str:
    """The row loop. Returns ``""`` or the reason the run stopped early."""
    for index, row in enumerate(rows, 1):
        state = rel.build_state(domain, row.text())
        try:
            arms = relevance_row(state, client, model, rel)
        except JevRateLimited as exc:
            print(
                f"{REASON_RATE_LIMITED_STOP}: HTTP {exc.status} after the run's one wait — "
                "a policy signal, not a transient error (rule debugging.md); stopping",
                flush=True,
            )
            return REASON_RATE_LIMITED_STOP
        except JevFatal as exc:
            print(f"stopping: HTTP {exc.status} — key or body rejected", flush=True)
            return f"{REASON_HTTP} (HTTP {exc.status})"
        except JevError as exc:
            arms = _relevance_failed(exc.reason, exc.status)
        handle.write(json.dumps(rel.row_record(row, arms), ensure_ascii=False) + "\n")
        handle.flush()
        brief = " ".join(f"{k}={v.get('score')}" for k, v in arms.items())
        print(f"  [{index}/{len(rows)}] {row.post_id[:8]} {brief}", flush=True)
    return ""


def build_relevance_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RFC-0045: the Jev label on the relevance replay.")
    parser.add_argument("--home", type=Path, default=Path.home() / ".config" / "moltbook")
    parser.add_argument("--subset", choices=("all", "dev", "sub600", "holdout"), default="all")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--split", default=".notes/relevance-arm-replay/split.json")
    parser.add_argument("--out-rows", type=Path, default=RELEVANCE_OUT_ROWS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--resume", action="store_true", help="skip posts already answered")
    parser.add_argument("--dry-run", action="store_true", help="count the rows; send nothing")
    return parser


def relevance_main(argv: list[str]) -> int:
    args = build_relevance_parser().parse_args(argv)
    args.write_split = False
    out_rows = assert_private_output(args.out_rows, notes_root=REPO_ROOT / ".notes")
    rel = load_relevance_module()
    sample = rel.load_sample(args.home)
    done = rel.read_rows([out_rows])
    if done and not args.resume:
        raise SystemExit(f"{out_rows} already holds rows — pass --resume")
    rows = [
        row
        for row in rel.select_rows(args, sample)
        if not all(rel.answered(done.get(row.post_id, {}), x) for x in _RELEVANCE_LABELS)
    ]
    print(f"{len(rows)} row(s) to ask ({len(done)} already in {out_rows.name})", flush=True)
    if args.dry_run:
        print("dry run — no request was sent", flush=True)
        return 0
    key = load_api_key()
    if key is None:
        print(f"{REASON_KEY_MISSING}: 0 requests sent", flush=True)
        return 1
    identity_path, _constitution = rel.skillsel().replay_prompt_sources(args.home)
    domain = rel.read_domain(identity_path)
    out_rows.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session, out_rows.open("a", encoding="utf-8") as handle:
        client = JevClient(key=key, timeout=args.timeout, session=session, max_rate_limit_waits=1)
        stopped = send_relevance_rows(
            rows, client, handle, model=args.model, domain=domain, rel=rel
        )
    print(f"wrote {out_rows}", flush=True)
    return 1 if stopped else 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["relevance"]:
        return relevance_main(argv[1:])
    args = build_parser().parse_args(argv)
    out_rows = assert_private_output(args.out_rows, notes_root=REPO_ROOT / ".notes")

    every_id = read_selection_ids(args.rows)
    ids = every_id[: args.limit] if args.limit > 0 else every_id
    rows = load_rows_by_id(args.home / "logs", ids, _load_replay_module())
    print(
        f"{len(ids)} target row(s) from {args.rows.name}: {len(rows)} rebuilt, "
        f"{len(ids) - len(rows)} {REASON_ROW_NOT_FOUND}",
        flush=True,
    )

    done_records, done_ids = load_done(out_rows)
    if done_records and not args.resume:
        raise SystemExit(
            f"{out_rows} already holds {len(done_records)} row(s) — pass --resume to continue "
            "that run, or give a different --out-rows"
        )
    # Round 1's guard, for its reason: a file holding rows outside THIS target
    # set would be read as this run's population, so the artifact would name a
    # row set it did not ask (skillsel_arm_replay.main).
    foreign = sorted(done_ids - set(ids))
    if foreign:
        raise SystemExit(
            f"{out_rows} holds {len(foreign)} row(s) outside this target set "
            f"(first: {foreign[0]}) — --rows or --limit changed; use a different --out-rows"
        )
    if args.dry_run:
        return dry_run(ids, rows)

    key = load_api_key()
    if key is None:
        print(
            f"{REASON_KEY_MISSING}: neither {KEY_ENV} nor {KEY_FILE} holds a key — 0 requests "
            "sent. The owner places it; this run never reads its value.",
            flush=True,
        )
        return 1

    out_rows.parent.mkdir(parents=True, exist_ok=True)
    # One session for the whole run: ~150 requests to one host, each carrying a
    # multi-kilobyte body, so the TLS handshake is worth paying once.
    with requests.Session() as session, out_rows.open("a", encoding="utf-8") as handle:
        state = send_rows(
            ids,
            rows,
            JevClient(key=key, timeout=args.timeout, session=session),
            handle,
            model=args.model,
            done_ids=done_ids,
        )
    print(f"wrote {out_rows}", flush=True)
    if state.tally:
        tally = ", ".join(f"{k}={v}" for k, v in sorted(state.tally.items()))
        print(f"reason codes: {tally}", flush=True)
    if state.stopped:
        print(f"run stopped early: {state.stopped}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
