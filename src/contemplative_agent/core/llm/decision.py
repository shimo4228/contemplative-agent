"""The decision seam: typed probabilistic judgments behind a protocol (ADR-0112).

Six of this agent's LLM calls ask for a judgment rather than for text. They all
run today as constrained generation on the production model. This module adds
the other shape — three typed questions in, per-option probabilities out — as a
protocol next to :class:`~contemplative_agent.core.llm.backend.LLMBackend`, plus
one implementation that needs no new dependency:
:class:`OllamaLogprobsDecisionBackend`, which reads the first token's
``top_logprobs`` of a ``num_predict: 1`` temperature-0 request.

Three properties are load-bearing and are the reason this is not "just another
backend":

* **The backend returns probabilities, never a decision.** Thresholds, set
  sizes and any normalisation across questions belong to the calling code,
  where they are visible (ADR-0071).
* **Every abstain has a name.** :data:`DECISION_REASONS` is closed; a caller
  can tell "the model said no" from "nothing was observed" from "the batch ran
  out of time" without reading this file.
* **Two models never sit in memory at once.** On a 16 GB machine a second
  resident model pushes the box into swap (RFC-0043 §8: 1.8x slower per row),
  and Ollama 0.34.2 co-loads whenever it judges both fit. ``exclusive=True``
  makes the eviction explicit rather than trusting that judgment.

The readout helpers (:func:`binary_softmax`, the label alphabet, the yes/no
token surfaces) were measured in ``scripts/skillsel_arm_replay.py`` (arm
``C/logits``) and are copied here — their source lines are named at each
definition. The script keeps its copies until the round-3 arms land; a
follow-up chore switches it to these (ADR-0112 Consequences).
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, runtime_checkable

import requests

from .backend import NUM_CTX
from .guard import validate_trusted_url

logger = logging.getLogger(__name__)

# Ollama's own ceiling on ``top_logprobs``: 21 returns HTTP 400 (RFC-0043
# evidence §5). It bounds both the label alphabet below and every request.
OLLAMA_TOP_LOGPROBS_CAP = 20

# Closed reason vocabulary. ``answered`` is the only non-abstain; the other
# nine name one way each that a question produced no distribution. A caller
# that sees a value outside this tuple is reading a record written by a
# different version, not a new failure mode.
DECISION_REASONS: tuple[str, ...] = (
    "answered",
    # No backend is configured — the kill switch. Never written by a backend.
    "unconfigured",
    # The shared breaker was open; nothing was sent and no counter moved.
    "circuit_open",
    "http_error",
    "bad_json",
    # The server answered but carried no ``logprobs`` array.
    "logprobs_unavailable",
    # Logprobs arrived, but none of the question's options were among them.
    "no_option_observed",
    # More options than there are readable single-token labels.
    "label_alphabet_exceeded",
    # The batch's wall-clock budget was spent before this question was sent.
    "budget_exceeded",
    # The backend raised. Recorded by the caller, not by the backend.
    "backend_exception",
)

REASON_ANSWERED = "answered"

# Yes/no token surfaces the first-token reading accepts. Copied from
# ``scripts/skillsel_arm_replay.py:1077-1078``. Compared on the stripped,
# lowercased token text, so "Yes", " yes" and "YES" are one bucket — the
# tokenizer's casing is not a judgment.
_YES_TOKENS = frozenset({"yes", "y", "true"})
_NO_TOKENS = frozenset({"no", "n", "false"})

# One distinct single-token label per option. Copied from
# ``scripts/skillsel_arm_replay.py:528-544``, with the alphabet cut at the
# readout's own ceiling: the script's 62 characters (A-Z, a-z, 0-9) serve a
# reading that scores truncation as a property of the arm, while here an
# option beyond the 20 the server will report could never be observed at all,
# so it is refused instead of silently unreadable. Multi-character labels are
# NOT usable: a first-token reading of "10" sees "1", which is also label 1.
LABEL_ALPHABET: tuple[str, ...] = tuple(chr(c) for c in range(ord("A"), ord("A") + 20))


def label_alphabet(size: int) -> tuple[str, ...]:
    """``size`` distinct single-character labels, or ``()`` when there are not enough.

    An empty return is the caller's signal to abstain with
    ``label_alphabet_exceeded`` rather than reuse a character — two options
    sharing a label would silently merge their scores.
    """
    if size > len(LABEL_ALPHABET):
        return ()
    return LABEL_ALPHABET[:size]


def binary_softmax(yes_logprob: float | None, no_logprob: float | None) -> float | None:
    """P(yes) over the {yes, no} pair alone, from their log-probabilities.

    Copied from ``scripts/skillsel_arm_replay.py:466-484``. Computed in log
    space with the max subtracted: the raw logprobs reach -12 and below, where
    ``exp`` of the difference underflows to 0.0 and the ratio becomes 0/0.
    ``None`` when neither side was observed — an unobserved yes with an
    observed no is 0.0, which is information; two unobserved sides are not, and
    must not read as 0.5.
    """
    if yes_logprob is None and no_logprob is None:
        return None
    if yes_logprob is None:
        return 0.0
    if no_logprob is None:
        return 1.0
    top = max(yes_logprob, no_logprob)
    ey = math.exp(yes_logprob - top)
    en = math.exp(no_logprob - top)
    return ey / (ey + en)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoulQuestion:
    """A yes/no question. ``instructions`` names what is being asked of the state."""

    id: str
    instructions: str


@dataclass(frozen=True)
class ChoiceQuestion:
    """One choice among unordered ``options``; the answer is one distribution."""

    id: str
    instructions: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class ScoreQuestion:
    """One choice among ORDERED ``levels``.

    Structurally a choice; the order is what makes
    :meth:`QuestionAnswer.expected_level` meaningful.
    """

    id: str
    instructions: str
    levels: tuple[str, ...]


DecisionQuestion: TypeAlias = "NoulQuestion | ChoiceQuestion | ScoreQuestion"


def _question_options(question: DecisionQuestion) -> tuple[str, ...]:
    """The option labels one question's distribution is over."""
    if isinstance(question, NoulQuestion):
        return ("yes", "no")
    if isinstance(question, ScoreQuestion):
        return question.levels
    return question.options


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuestionAnswer:
    """One question's distribution, or a named absence of one.

    ``probabilities`` keeps the question's own option order, so a score
    question's levels stay ordered and a reader can index them. It is empty
    whenever ``reason`` is not ``answered``. ``observed`` is how many options
    the server actually reported — the honest denominator for a truncated
    reading — and ``truncated`` says at least one option was not observed and
    therefore carries 0.0 by convention, not by measurement.
    """

    id: str
    probabilities: tuple[tuple[str, float], ...]
    reason: str
    observed: int
    truncated: bool = False

    def as_dict(self) -> dict[str, float]:
        """The distribution as ``{option: probability}`` (order is lost)."""
        return dict(self.probabilities)

    def expected_level(self) -> float | None:
        """Probability-weighted mean of the option INDEX, or None.

        For a :class:`ScoreQuestion` this is the expected level on the 0-based
        scale its ``levels`` declare. None when no mass was observed: a
        truncated reading whose observed options all scored 0.0 has no
        expectation, and returning the midpoint would invent one.
        """
        total = sum(probability for _option, probability in self.probabilities)
        if total <= 0.0:
            return None
        return sum(i * p for i, (_option, p) in enumerate(self.probabilities)) / total


@dataclass(frozen=True)
class DecisionResult:
    """One batch's answers.

    ``reason`` is the batch-level verdict: ``answered`` only when every
    question answered, otherwise the first non-answered reason in question
    order (first-failure wins), so a row carries a diagnosis rather than a
    count. ``latency_ms`` covers the whole batch, evictions included — it is
    what the shadow reading prices.
    """

    model: str
    latency_ms: int
    answers: tuple[QuestionAnswer, ...]
    reason: str


@dataclass(frozen=True)
class DecisionRequest:
    """What one caller asked of a decision backend.

    The same split :mod:`.request` makes for generation: the caller's ask as a
    value, so a frame that receives it needs no column of positional
    arguments. ``caller`` is the stage label telemetry groups by.
    """

    state: str
    questions: tuple[DecisionQuestion, ...]
    caller: str


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DecisionBackend(Protocol):
    """Pluggable judgment backend — the decision twin of ``LLMBackend``.

    Default (``_decision_backend = None``) disables the path entirely: no
    call, no record, no telemetry. A trained decision model that needs torch
    is injected from a sibling repository through ``configure``, exactly as
    ``contemplative-agent-cloud`` injects its generation backend, so the
    wheel's dependency floor does not move (ADR-0109).
    """

    @property
    def model(self) -> str:
        """Served model id recorded in per-call telemetry. A read-only
        property so a ``frozen=True`` backend dataclass satisfies it."""
        ...

    def decide(
        self,
        state: str,
        questions: tuple[DecisionQuestion, ...],
        *,
        system: str = "",
    ) -> DecisionResult | None:
        """Answer every question against one shared *state*.

        *state* is the prompt PREFIX and the question the suffix, so a
        prefix-caching server carries the (large) state across the per-question
        calls. *system* is the system prompt the caller wants the judge to run
        under — passed rather than assembled here, so a shadow judge can run
        under exactly the system prompt of the live call it observes.

        Implementations return a named abstain instead of raising: a judgment
        path must never abort the generation it precedes. Returning ``None`` is
        permitted but carries no diagnosis, so the caller records it as
        ``backend_exception``.
        """
        ...


# ---------------------------------------------------------------------------
# The shipped implementation
# ---------------------------------------------------------------------------

_NOUL_SUFFIX = "\n\n## Question\n\n{instructions}\nAnswer with exactly one word: yes or no."
_LABEL_SUFFIX = (
    "\n\n## Question\n\n{instructions}\n\n{options}\n"
    "Answer with exactly one letter: the label of your choice."
)


@dataclass(frozen=True)
class OllamaLogprobsDecisionBackend:
    """A decision backend that reads the first token's ``top_logprobs``.

    No new dependency and no new outbound surface: it posts to the same
    allow-listed Ollama URL the generation path uses (``validate_trusted_url``).
    It never touches the shared circuit breaker's counters — its caller reads
    ``is_open`` on its behalf — because an instrument's failures must not open
    the circuit that guards the publish path it observes.

    ``exclusive`` states that this model is NOT the served generation model, so
    the batch evicts the generation model before it starts and evicts itself on
    its last call (``keep_alive: 0``). ``batch_budget_s`` bounds what one batch
    may add to a cycle: RFC-0043's arm ``C/logits`` — this same per-entry shape
    on gemma — took 51.0 s per row at the median and 820 s at the maximum over
    150 rows. Questions the budget did not reach come back as
    ``budget_exceeded`` rather than delaying the generation behind them.
    """

    model: str
    base_url: str | None = None
    exclusive: bool = False
    # Connect-biased like every other local LLM transport here; the read side
    # is long because a cold model load is ~7 s and a batch is many calls.
    timeout: tuple[int, int] = (30, 300)
    batch_budget_s: float = 120.0

    def decide(
        self,
        state: str,
        questions: tuple[DecisionQuestion, ...],
        *,
        system: str = "",
    ) -> DecisionResult | None:
        started = time.monotonic()
        if not questions:
            return DecisionResult(
                model=self.model, latency_ms=0, answers=(), reason=REASON_ANSWERED
            )
        try:
            url = f"{self._base_url()}/api/generate"
        except ValueError as exc:
            # A misconfigured URL is not a per-question event, but the result
            # shape is one answer per question either way: a caller that zips
            # answers against its own list must never have to handle a short
            # tuple.
            logger.warning("decision backend URL refused: %s", exc)
            return self._all(questions, "http_error", started)

        if self.exclusive:
            self._evict(url, self._generation_model())

        answers: list[QuestionAnswer] = []
        evicted = False
        for index, question in enumerate(questions):
            if time.monotonic() - started >= self.batch_budget_s:
                answers.append(_abstained(question, "budget_exceeded"))
                continue
            # The batch's own model comes down on its last sent call, which is
            # free (it rides a request already being made).
            evict_self = self.exclusive and index == len(questions) - 1
            answer, reached = self._ask(url, state, system, question, evict_self=evict_self)
            # Only a request the server actually answered took the eviction
            # with it; a transport failure carried nothing.
            evicted = evicted or (evict_self and reached)
            answers.append(answer)

        if self.exclusive and not evicted:
            # The budget cut the batch short, or the last call failed before
            # the server saw it. Either way the model must come down, so the
            # eviction goes as a request of its own — the co-residence
            # guarantee is not conditional on the batch finishing.
            self._evict(url, self.model)

        return DecisionResult(
            model=self.model,
            latency_ms=int((time.monotonic() - started) * 1000),
            answers=tuple(answers),
            reason=batch_reason(tuple(answers)),
        )

    # -- internals ---------------------------------------------------------

    def _base_url(self) -> str:
        """The allow-listed Ollama origin. Raises ValueError when untrusted."""
        if self.base_url is not None:
            return validate_trusted_url(self.base_url, source="DecisionBackend base_url")
        # Lazy: the facade imports this module, so a module-level import would
        # be circular. By call time it is fully loaded.
        from . import _get_ollama_url

        return _get_ollama_url()

    @staticmethod
    def _generation_model() -> str:
        from . import served_model

        return served_model()

    def _all(
        self, questions: tuple[DecisionQuestion, ...], reason: str, started: float
    ) -> DecisionResult:
        """One batch where every question failed the same way."""
        return DecisionResult(
            model=self.model,
            latency_ms=int((time.monotonic() - started) * 1000),
            answers=tuple(_abstained(q, reason) for q in questions),
            reason=reason,
        )

    def _evict(self, url: str, model: str) -> None:
        """Ask Ollama to unload *model* now. Best effort, never raises.

        A side effect on a shared daemon: anything else using it feels the
        next call to that model as a reload (~7 s for gemma). ADR-0112 names
        this as the one boundary this seam crosses.
        """
        try:
            requests.post(
                url,
                json={"model": model, "keep_alive": 0},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            logger.warning("decision backend could not evict %s: %s", model, exc)

    def _ask(
        self,
        url: str,
        state: str,
        system: str,
        question: DecisionQuestion,
        *,
        evict_self: bool,
    ) -> tuple[QuestionAnswer, bool]:
        """One question. Returns its answer and whether the server was reached.

        The second element is what the eviction bookkeeping needs: a request
        that never arrived did not take the model down with it.
        """
        options = _question_options(question)
        if isinstance(question, NoulQuestion):
            prompt = state + _NOUL_SUFFIX.format(instructions=question.instructions)
            # Not min(20, 2): the yes/no surfaces compete with whatever
            # spelling, casing or punctuation the model prefers, and are not
            # guaranteed to be the top two tokens. Arm C read the full cap for
            # this reason, and the cap is what that measurement was taken at.
            needed = OLLAMA_TOP_LOGPROBS_CAP
        else:
            labels = label_alphabet(len(options))
            if not labels:
                return _abstained(question, "label_alphabet_exceeded"), False
            rendered = "\n".join(
                f"{label}. {option}" for label, option in zip(labels, options, strict=True)
            )
            prompt = state + _LABEL_SUFFIX.format(
                instructions=question.instructions, options=rendered
            )
            needed = len(options)

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": 1,
                # Always sent: Ollama's documented default of 2,048 truncates
                # silently, which is the trap RFC-0043's replay notes record.
                "num_ctx": NUM_CTX,
            },
            "logprobs": True,
            "top_logprobs": min(OLLAMA_TOP_LOGPROBS_CAP, needed),
        }
        if evict_self:
            payload["keep_alive"] = 0

        try:
            response = requests.post(url, json=payload, timeout=self.timeout, allow_redirects=False)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("decision call failed for %s: %s", question.id, exc)
            # raise_for_status means the server DID answer, so an error status
            # still took the keep_alive with it; a transport failure did not.
            reached = isinstance(exc, requests.exceptions.HTTPError)
            return _abstained(question, "http_error"), reached

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("decision response was not JSON for %s: %s", question.id, exc)
            return _abstained(question, "bad_json"), True

        entries = data.get("logprobs") or []
        if not entries:
            return _abstained(question, "logprobs_unavailable"), True
        alternatives = entries[0].get("top_logprobs") or [entries[0]]

        if isinstance(question, NoulQuestion):
            return _read_noul(question, alternatives), True
        return _read_labels(question, options, alternatives), True


# ---------------------------------------------------------------------------
# Reading one distribution
# ---------------------------------------------------------------------------


def _abstained(question: DecisionQuestion, reason: str) -> QuestionAnswer:
    return QuestionAnswer(id=question.id, probabilities=(), reason=reason, observed=0)


def _logprob_of(alternative: object) -> float | None:
    """The alternative's logprob when it is a real number, else None."""
    if not isinstance(alternative, dict):
        return None
    value = alternative.get("logprob")
    # bool is an int subclass; a True logprob is a malformed body, not 1.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _read_noul(question: NoulQuestion, alternatives: list) -> QuestionAnswer:
    """P(yes) from the yes/no surfaces among the reported alternatives."""
    yes_lp: float | None = None
    no_lp: float | None = None
    for alternative in alternatives:
        logprob = _logprob_of(alternative)
        if logprob is None:
            continue
        token = str(alternative.get("token", "")).strip().lower()
        # First occurrence wins: ``top_logprobs`` is ordered by probability, so
        # the first yes-surface token is the most likely spelling of yes.
        if token in _YES_TOKENS and yes_lp is None:
            yes_lp = logprob
        elif token in _NO_TOKENS and no_lp is None:
            no_lp = logprob
    probability = binary_softmax(yes_lp, no_lp)
    if probability is None:
        return _abstained(question, "no_option_observed")
    return QuestionAnswer(
        id=question.id,
        probabilities=(("yes", probability), ("no", 1.0 - probability)),
        reason=REASON_ANSWERED,
        observed=(yes_lp is not None) + (no_lp is not None),
        truncated=yes_lp is None or no_lp is None,
    )


def _read_labels(
    question: DecisionQuestion, options: tuple[str, ...], alternatives: list
) -> QuestionAnswer:
    """Softmax over the OBSERVED labels; unobserved options carry 0.0.

    Normalising over the observed subset rather than over all options is the
    honest reading of a truncated response: the server reported a ranking of
    what it surfaced and said nothing about the rest, so the mass it did report
    is distributed among the options it named, and ``truncated`` tells the
    caller the zeros are a convention rather than a measurement.
    """
    labels = label_alphabet(len(options))
    by_label = {label: index for index, label in enumerate(labels)}
    logprobs: dict[int, float] = {}
    for alternative in alternatives:
        logprob = _logprob_of(alternative)
        if logprob is None:
            continue
        token = str(alternative.get("token", "")).strip()
        index = by_label.get(token)
        # First occurrence wins, as in the yes/no reading.
        if index is not None and index not in logprobs:
            logprobs[index] = logprob
    if not logprobs:
        return _abstained(question, "no_option_observed")
    top = max(logprobs.values())
    weights = {index: math.exp(value - top) for index, value in logprobs.items()}
    total = sum(weights.values())
    probabilities = tuple(
        (option, weights.get(index, 0.0) / total) for index, option in enumerate(options)
    )
    return QuestionAnswer(
        id=question.id,
        probabilities=probabilities,
        reason=REASON_ANSWERED,
        observed=len(logprobs),
        truncated=len(logprobs) < len(options),
    )


def batch_reason(answers: tuple[QuestionAnswer, ...]) -> str:
    """``answered`` only when every answer did; else the first that did not.

    First-failure wins rather than a count or a majority: the row's job is to
    hand the reading a diagnosis it can group by, and the first failure in
    question order is the one a replay would hit first.
    """
    for answer in answers:
        if answer.reason != REASON_ANSWERED:
            return answer.reason
    return REASON_ANSWERED
