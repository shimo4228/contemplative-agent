"""``doctor``: is this machine ready to run a session? (P0-05.1)

One screen, one verdict. The checks are the ones whose failure used to look
like success: Ollama not running (an INFO line, rc=0), the generation model not
pulled (every post fails the relevance gate), the decision backend unable to
answer (``no_option_observed`` on every post), no home, no credentials.

:func:`serving_findings` is shared with `run`: it turns the session's
``serving_environment()`` reading into findings, so the startup line a session
prints and the line `doctor` prints cannot disagree (``run_startup_report``).

Read-only: it asks Ollama two GETs and one one-token decision, and writes only
the per-call telemetry row the decision call always writes.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..adapters.moltbook import config
from ..core.env import env_get
from ..core.llm import (
    REASON_ANSWERED,
    NoulQuestion,
    configure as configure_llm,
    decide,
    get_ollama_url,
    ollama_model,
    refresh_serving_environment,
    serving_environment,
)
from .registry import CommandSpec, Tier
from .runtime import _build_decision_backend

logger = logging.getLogger(__name__)

OK = "ok"
WARN = "warn"
FAIL = "fail"

# The decision canary's reason codes. ``decision_canary_failed`` is the
# headline; the suffix says how (the backend's own reason, or ``answered_no``
# when it answered and the answer was wrong).
CANARY_FAILED = "decision_canary_failed"
CANARY_ANSWERED_NO = "answered_no"

_CANARY_ID = "doctor_canary"
# A canary that says "yes" at 0.5 or less is not a reading of anything.
_CANARY_MIN_P_YES = 0.5


@dataclass(frozen=True)
class Finding:
    """One line of the report: a level, what was checked, and the next step."""

    level: str
    check: str
    detail: str
    fix: str = ""

    def lines(self) -> list[str]:
        tag = {OK: "  ok  ", WARN: " WARN ", FAIL: " FAIL "}[self.level]
        out = [f"[{tag}] {self.check}: {self.detail}"]
        if self.fix:
            out.append(f"         -> {self.fix}")
        return out


def _tag_name(tag: str) -> str:
    """``gemma4:e4b`` -> ``gemma4:e4b``; ``nomic-embed-text:latest`` -> ``nomic-embed-text``."""
    return tag[: -len(":latest")] if tag.endswith(":latest") else tag


def serving_findings(env: Mapping[str, Any]) -> list[Finding]:
    """Findings for one ``serving_environment()`` reading.

    The reading carries a ``;``-joined reason (``core.llm.serving_environment``).
    A missing *generation* model is a FAIL (every post fails the relevance
    gate); a missing *embedding* model is a WARN (embedding callers fail open).
    """
    reason = str(env.get("serving_environment_reason") or "ok")
    url = get_ollama_url()
    generation = _tag_name(ollama_model())
    findings: list[Finding] = []
    for part in reason.split(";"):
        if part == "ok":
            version = env.get("ollama_version")
            findings.append(
                Finding(OK, "Ollama", f"reachable at {url} (version {version}); models listed")
            )
        elif part == "ollama_unreachable":
            findings.append(
                Finding(
                    FAIL,
                    "Ollama",
                    f"not reachable at {url}",
                    "start Ollama (open the app, or run `ollama serve`)",
                )
            )
        elif part == "ollama_malformed_response":
            findings.append(
                Finding(
                    FAIL,
                    "Ollama",
                    f"{url} answered, but not with Ollama's API",
                    "check OLLAMA_BASE_URL",
                )
            )
        elif part == "backend_injected":
            findings.append(
                Finding(
                    OK,
                    "Generation backend",
                    "an injected backend serves generation; only the embedding model is checked",
                )
            )
        elif part.startswith("model_not_listed:"):
            tag = _tag_name(part.split(":", 1)[1])
            if tag == generation:
                findings.append(
                    Finding(
                        FAIL,
                        "Generation model",
                        f"{tag} is not pulled; the relevance gate fails closed and the "
                        "agent engages with nothing",
                        f"ollama pull {tag}",
                    )
                )
            else:
                findings.append(
                    Finding(
                        WARN,
                        "Embedding model",
                        f"{tag} is not pulled; embedding-backed checks fail open",
                        f"ollama pull {tag}",
                    )
                )
        else:
            findings.append(Finding(WARN, "Ollama", f"unrecognised reason {part!r}"))
    return findings


def home_findings() -> list[Finding]:
    """The home directory and the API key, the two things `init` / `register` make."""
    findings: list[Finding] = []
    home = config.MOLTBOOK_DATA_DIR
    if config.IDENTITY_PATH.is_file():
        findings.append(Finding(OK, "Home", f"{home} is initialised"))
    else:
        findings.append(
            Finding(FAIL, "Home", f"{home} has no identity.md", "contemplative-agent init")
        )
    if env_get("MOLTBOOK_API_KEY"):
        findings.append(Finding(OK, "Moltbook key", "taken from MOLTBOOK_API_KEY"))
    elif config.CREDENTIALS_PATH.is_file():
        findings.append(Finding(OK, "Moltbook key", f"found in {config.CREDENTIALS_PATH}"))
    else:
        # Not a FAIL: right after `init` (where the README places `doctor`)
        # there is no key yet, and `dialogue` runs without one.
        findings.append(
            Finding(
                WARN,
                "Moltbook key",
                f"no {config.CREDENTIALS_PATH} and no MOLTBOOK_API_KEY (only `run` needs it)",
                "contemplative-agent register --name YOUR-AGENT-NAME",
            )
        )
    return findings


def canary_finding() -> Finding:
    """Ask the decision backend one question whose answer is yes.

    The relevance gate reads the first token's logprobs. A model that does not
    answer in one token, or a server that does not return logprobs, makes every
    post ``no_option_observed`` — a feed that engages with nothing and looks
    quiet. This is the same read on a question that cannot be answered no.
    A WARN, not a FAIL: it measures the model, and the operator may choose to
    run on regardless.
    """
    backend = _build_decision_backend()
    if backend is None:
        return Finding(
            FAIL,
            "Decision backend",
            "DECISION_MODEL is empty: no decision backend, so the relevance gate "
            "fails closed (enforce_backend_null) and the agent engages with nothing",
            "unset DECISION_MODEL",
        )
    from ..core import prompts

    configure_llm(decision_backend=backend)
    question = NoulQuestion(id=_CANARY_ID, instructions=prompts.DOCTOR_CANARY_PROMPT.strip())
    result = decide("", (question,), caller="doctor.canary")
    if result is None:  # unreachable: the backend was configured a line above
        return Finding(WARN, "Decision canary", f"{CANARY_FAILED}: no backend")
    answer = result.answers[0] if result.answers else None
    if answer is None or answer.reason != REASON_ANSWERED:
        why = answer.reason if answer is not None else result.reason
        return Finding(
            WARN,
            "Decision canary",
            f"{CANARY_FAILED}: {why} (model {backend.model})",
            "the relevance gate will fail closed with this model; the tested model is "
            "gemma4:e4b (see README, Run it on Moltbook)",
        )
    p_yes = answer.as_dict().get("yes", 0.0)
    if p_yes <= _CANARY_MIN_P_YES:
        return Finding(
            WARN,
            "Decision canary",
            f"{CANARY_FAILED}: {CANARY_ANSWERED_NO} (P(yes) {p_yes:.2f}, model {backend.model})",
            "this model's first-token read is not a usable relevance judge",
        )
    return Finding(
        OK, "Decision canary", f"model {backend.model} answered yes at P(yes) {p_yes:.2f}"
    )


def run_checks() -> list[Finding]:
    findings = serving_findings(serving_environment())
    if not any(f.level == FAIL for f in findings if f.check in ("Ollama", "Generation model")):
        findings.append(canary_finding())
    else:
        findings.append(
            Finding(WARN, "Decision canary", "skipped: Ollama or the generation model is not ready")
        )
    findings.extend(home_findings())
    return findings


def run_startup_report(env: Mapping[str, Any]) -> list[Finding]:
    """What `run` says about the environment before the first cycle.

    The same findings `doctor` prints for Ollama and the models, minus the
    ``ok`` lines (a healthy start says nothing here).
    """
    return [f for f in serving_findings(env) if f.level != OK]


# D-P0-05-1 = A (owner, 2026-10-24): when Ollama or the generation model is not
# ready at start, retry briefly (the nightly 23:55 restart can still be coming
# up when a scheduled session starts), then end the run with rc=1. Without
# Ollama the agent has no work it can do, and six hours of declined posts only
# move the cost to a human reading the weekly report.
STARTUP_RETRY_ATTEMPTS = 5
STARTUP_RETRY_DELAY_S = 20.0


def _blocking(findings: list[Finding]) -> list[Finding]:
    """The findings that mean `run` cannot do its work: Ollama or the generation model."""
    return [f for f in findings if f.level == FAIL]


def announce_run_startup(
    env: dict[str, Any], on_abort: Callable[[str], None] | None = None
) -> None:
    """Check the environment before the first cycle; end the run if it is not usable.

    Retries a failing check ``STARTUP_RETRY_ATTEMPTS`` times in all,
    ``STARTUP_RETRY_DELAY_S`` apart (re-reading Ollama each time; ``env`` is
    updated in place so the session-start row records the reading that held).
    A check that still fails prints ``ERROR:`` lines on stderr and exits 1; a
    missing generation model carries the ``model_not_listed:<tag>`` reason.
    Anything that is only a warning (an embedding model) is logged and the run
    goes on. ``on_abort(reason)`` runs just before the exit so the run leaves
    a record readers can see (an ``aborted`` session row, ADR-0075); stderr
    alone ends in a log nobody reads.
    """
    for attempt in range(1, STARTUP_RETRY_ATTEMPTS + 1):
        if not _blocking(run_startup_report(env)):
            break
        if attempt < STARTUP_RETRY_ATTEMPTS:
            logger.warning(
                "Ollama or the generation model is not ready (attempt %d/%d); retrying in %.0fs",
                attempt,
                STARTUP_RETRY_ATTEMPTS,
                STARTUP_RETRY_DELAY_S,
            )
            time.sleep(STARTUP_RETRY_DELAY_S)
            env.update(refresh_serving_environment())
    reason = str(env.get("serving_environment_reason") or "ok")
    blocking = _blocking(run_startup_report(env))
    for finding in run_startup_report(env):
        text = f"{finding.check}: {finding.detail}" + (f" -> {finding.fix}" if finding.fix else "")
        if finding in blocking:
            print(f"ERROR: {text} [{reason}]", file=sys.stderr)
        else:
            logger.warning("%s [%s]", text, reason)
    if blocking:
        if on_abort is not None:
            on_abort(reason)
        sys.exit(1)


def _handle_doctor(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    findings = run_checks()
    for finding in findings:
        for line in finding.lines():
            print(line)
    failed = [f for f in findings if f.level == FAIL]
    warned = [f for f in findings if f.level == WARN]
    if failed:
        print(f"doctor: {len(failed)} problem(s) to fix, {len(warned)} warning(s)")
        sys.exit(1)
    print(f"doctor: ready ({len(warned)} warning(s))")


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="doctor",
        help="Check Ollama, the models, the decision backend and the home before a first run",
        handler=_handle_doctor,
        tier=Tier.LLM_RUNTIME_ONLY,
    ),
)
