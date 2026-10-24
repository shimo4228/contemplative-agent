"""Fresh-interpreter driver for ``tests/test_quickstart_smoke.py`` (P0-05.9).

Runs the README Quick Start (``init`` -> ``register`` -> ``run --session 1``) through
``contemplative_agent.cli.main`` against a real ``Agent``. Only the network and the
models are replaced: ``responses`` stands in for moltbook.com, a stub generation
backend and a stub decision backend stand in for the two Ollama paths.

It must be a separate interpreter because ``adapters.moltbook.config`` freezes its
paths at import time, and the point of the smoke is that nothing is set: the home is
``$HOME/.config/moltbook`` and no ``DECISION_*`` / ``MOLTBOOK_*`` variable exists.

Usage: python quickstart_harness.py [enforce-env-empty]
The last stdout line is a JSON summary; everything before it is the CLI's own output.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import responses

from contemplative_agent.cli import main, runtime
from contemplative_agent.core import llm
from contemplative_agent.core.llm import (
    BackendResult,
    DecisionResult,
    QuestionAnswer,
)

API = "https://www.moltbook.com/api/v1"
POST_ID = "post-smoke-0001"
KEY = "moltbook_sk_QUICKSTARTSENTINEL"

wiring: dict[str, object] = {}


class StubGeneration:
    # Reports itself as the default Ollama generation model, so the decision
    # backend the CLI wires reads the same model (exclusive=False) exactly as
    # it does on a stock install; a different name would model a sibling backend.
    model = llm.ollama_model()
    context_window = 32768

    def generate(self, prompt, system, num_predict, format, *, temperature=1.0, think=False):
        return BackendResult(
            text="A short, kind reply that stays on the point of the post.",
            finish_reason="stop",
        )


class StubDecisionBackend:
    """Answers every question: all of the mass on the top option."""

    def __init__(self, *, model, exclusive, batch_budget_s):
        wiring.update(model=model, exclusive=exclusive, batch_budget_s=batch_budget_s)
        self.model = model
        self.exclusive = exclusive

    def decide(self, state, questions, *, system=""):
        answers = []
        for question in questions:
            options = list(getattr(question, "levels", None) or getattr(question, "options", ()))
            n = len(options) or 4
            probs = [0.4 / (n - 1)] * (n - 1) + [0.6]  # P(top) 0.6 >= the 0.3 cut
            labels = [str(o) for o in options] or [str(i) for i in range(n)]
            answers.append(
                QuestionAnswer(
                    id=question.id,
                    probabilities=tuple(zip(labels, probs, strict=True)),
                    reason="answered",
                    observed=n,
                )
            )
        return DecisionResult(
            model=self.model, latency_ms=1, answers=tuple(answers), reason="answered"
        )


def _json(body, status=200):
    return (status, {"Content-Type": "application/json"}, json.dumps(body))


def _route(request):
    path = request.url.split("/api/v1", 1)[1].split("?", 1)[0]
    method = request.method
    if method == "POST" and path == "/agents/register":
        return _json({"agent": {"name": "smoke", "api_key": KEY, "id": "agent-1",
                                "claim_url": "https://www.moltbook.com/claim/x"}})
    if method == "GET" and path == "/home":
        return _json({"your_account": {"name": "smoke", "karma": 1},
                      "activity_on_your_posts": []})
    if method == "GET" and path == "/feed":
        return _json({"posts": []})
    if method == "GET" and re.fullmatch(r"/submolts/[^/]+/feed", path):
        return _json({"posts": [{
            "id": POST_ID,
            "title": "On noticing",
            "content": "What changes when an agent pauses before it answers?",
            "author": {"name": "someone-else"},
            "submolt": {"name": "alignment"},
        }]})
    if method == "GET" and path == f"/posts/{POST_ID}":
        return _json({"post": {"id": POST_ID, "content":
                               "What changes when an agent pauses before it answers?"}})
    if method == "POST" and path == f"/posts/{POST_ID}/upvote":
        return _json({"success": True})
    if method == "POST" and path == f"/posts/{POST_ID}/comments":
        return _json({"success": True, "comment": {"id": "comment-1"}})
    if method == "POST" and re.fullmatch(r"/submolts/[^/]+/subscribe", path):
        return _json({"success": True})
    return _json({"error": "unrouted in the smoke"}, status=404)


def _run(argv):
    sys.argv = ["contemplative-agent", *argv]
    try:
        main()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


def run() -> dict:
    # No waiting: a 1-minute session would otherwise sleep out its remainder.
    time.sleep = lambda _s: None  # type: ignore[assignment]
    runtime.OllamaLogprobsDecisionBackend = StubDecisionBackend  # type: ignore[misc]
    llm.configure(backend=StubGeneration())

    calls: list[str] = []
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add_callback(
            responses.GET, re.compile(re.escape(API) + ".*"), callback=_route
        )
        rsps.add_callback(
            responses.POST, re.compile(re.escape(API) + ".*"), callback=_route
        )
        # Ollama answers its two metadata GETs (the startup check reads them).
        ollama = "http://localhost:11434"
        rsps.add(responses.GET, f"{ollama}/api/version", json={"version": "0.34.2"})
        rsps.add(
            responses.GET,
            f"{ollama}/api/tags",
            json={"models": [
                {"name": llm.ollama_model(), "digest": "a" * 64},
                {"name": "nomic-embed-text:latest", "digest": "b" * 64},
            ]},
        )
        rc = {
            "init": _run(["init"]),
            "register": _run(["register", "--name", "smoke"]),
            "run": _run(["--auto", "run", "--session", "1"]),
        }
        calls = [f"{c.request.method} {c.request.url.split('/api/v1', 1)[1].split('?', 1)[0]}"
                 for c in rsps.calls if "/api/v1" in c.request.url]
    return {"rc": rc, "wiring": wiring, "calls": calls,
            "decision_model_env": os.environ.get("DECISION_MODEL")}


if __name__ == "__main__":
    summary = run()
    print(json.dumps(summary))
