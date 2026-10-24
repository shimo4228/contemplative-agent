"""P1-10.10: a live API key never reaches the LLM context, outputs, logs or stdout.

ADR-0015 states "credentials never enter the LLM context" as a structural
property. Nothing proved it: ``FORBIDDEN_SUBSTRING_PATTERNS`` matches
vocabulary and ``_scrub_secrets`` never compares against a real value. This is
the absence test -- one sentinel key is loaded the way production loads it
(``load_credentials()``: env var, then ``credentials.json``), the agent then
does work that talks to the LLM, and the sentinel must not appear on any of
five surfaces:

  1. every prompt/system text sent to the LLM (Ollama request bodies)
  2. the generated outputs after sanitisation
  3. every JSONL (and any other file) written under MOLTBOOK_HOME, except
     ``credentials.json`` itself, which exists to hold the key
  4. the logging stream, DEBUG included
  5. ``register`` / ``status`` stdout

A positive control proves the key was live in the process (the Moltbook
request carries it as the bearer token), so a pass is not vacuous. A failure
here is a structural break, not a flaky test. No runtime redaction is added by
design: the point is that there is nothing to redact.

``test_register_does_not_print_the_issued_key`` is xfail(strict=False): the
fresh key a ``register`` call *receives* is printed today; removing that is
P0-05.3, which should drop the marker when it lands.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import pytest
import responses as responses_lib

from contemplative_agent.adapters.moltbook import auth, llm_functions as lf
from contemplative_agent.core import config as core_config

SENTINEL = "moltbook_sk_SENTINEL_c0ffee5eed1234567890"
MOLTBOOK_API = "https://www.moltbook.com/api/v1"
OLLAMA_GENERATE = re.compile(r"http://[^/]+/api/generate")


def _home() -> Path:
    # conftest pins MOLTBOOK_HOME to a per-session temp dir before import.
    return Path(os.environ["MOLTBOOK_HOME"])


def _load_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str) -> None:
    monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
    if source == "env":
        monkeypatch.setenv("MOLTBOOK_API_KEY", SENTINEL)
    else:
        cred = tmp_path / "credentials.json"
        cred.write_text(json.dumps({"api_key": SENTINEL}), encoding="utf-8")
        monkeypatch.setattr(auth, "CREDENTIALS_PATH", cred)
    assert auth.load_credentials() == SENTINEL  # the same loader production uses


def _home_files_except_credentials() -> list[Path]:
    return [
        p
        for p in _home().rglob("*")
        if p.is_file() and p.name != "credentials.json" and ".hypothesis" not in p.parts
    ]


def _ollama_ok(request):  # responses callback
    return (200, {}, json.dumps({"response": "A short, kind reply.", "done": True}))


@pytest.fixture
def ollama_bodies():
    """Capture every request body sent to the (mocked) Ollama generate endpoint."""
    bodies: list[str] = []

    def _cb(request):
        raw = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        bodies.append(raw or "")
        return _ollama_ok(request)

    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add_callback(responses_lib.POST, OLLAMA_GENERATE, callback=_cb)
        rsps.add(
            responses_lib.GET,
            f"{MOLTBOOK_API}/agents/status",
            json={"status": "claimed", "agent": {"name": "tester"}},
        )
        rsps.add(
            responses_lib.POST,
            f"{MOLTBOOK_API}/agents/register",
            json={"agent": {"id": "a1", "claim_url": "https://example.test/claim"}},
        )
        # Ollama metadata GETs are best-effort observability; let them 404.
        rsps.add(responses_lib.GET, re.compile(r"http://[^/]+/api/(version|tags)"), status=404)
        rsps.bodies = bodies  # type: ignore[attr-defined]
        yield rsps


@pytest.mark.parametrize("source", ["env", "credentials_file"])
def test_sentinel_key_never_appears_on_any_surface(
    source, monkeypatch, tmp_path, ollama_bodies, capsys, caplog
):
    _load_key(monkeypatch, tmp_path, source)
    caplog.set_level(logging.DEBUG)

    from contemplative_agent.adapters.moltbook.agent import Agent

    agent = Agent()
    outputs: list[str | None] = []
    outputs.append(lf.generate_comment("A post about how attention shapes care.").text)
    outputs.append(lf.generate_reply(original_post="a post", their_comment="a comment").text)
    outputs.append(lf.generate_internal_note("some content the agent produced"))

    # Surface 5 + positive control: status goes over the wire with the key.
    result = agent.do_status()
    print(f"Agent status: {result}")
    bearer = [
        c.request.headers.get("Authorization", "")
        for c in ollama_bodies.calls
        if "moltbook.com" in c.request.url
    ]
    assert bearer and all(SENTINEL in h for h in bearer), "control: key was not live in the process"

    prompts = list(ollama_bodies.bodies)  # type: ignore[attr-defined]
    assert prompts, "no LLM request was captured -- the test drove nothing"

    # 1. prompts
    assert not [p for p in prompts if SENTINEL in p], "key reached an LLM prompt"
    # 2. outputs
    assert not [o for o in outputs if o and SENTINEL in o]
    # 3. files written under MOLTBOOK_HOME (JSONL telemetry, episodes, anything)
    leaked = [
        p for p in _home_files_except_credentials() if SENTINEL.encode() in p.read_bytes()
    ]
    assert not leaked, f"key written to {leaked}"
    # 4. logs, DEBUG included
    assert SENTINEL not in caplog.text, "key reached the logging stream"
    # 5. stdout / stderr
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err


def test_register_stdout_has_no_loaded_key(monkeypatch, tmp_path, ollama_bodies, capsys):
    """`register` must not echo the key that was already loaded for this process."""
    _load_key(monkeypatch, tmp_path, "env")
    from contemplative_agent.adapters.moltbook.agent import Agent

    result = Agent().do_register("tester")
    print(f"Registration result: {result}")
    out = capsys.readouterr()
    assert SENTINEL not in out.out + out.err


@pytest.mark.xfail(
    strict=False,
    reason="P0-05.3: register prints the key the platform just ISSUED; drop the marker when fixed",
)
def test_register_does_not_print_the_issued_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
    monkeypatch.setattr(auth, "CREDENTIALS_PATH", tmp_path / "credentials.json")
    with responses_lib.RequestsMock() as rsps:
        rsps.add(
            responses_lib.POST,
            f"{MOLTBOOK_API}/agents/register",
            json={"agent": {"id": "a1", "api_key": SENTINEL, "claim_url": "https://x.test/c"}},
        )
        from contemplative_agent.adapters.moltbook.agent import Agent

        result = Agent().do_register("tester")
        print(f"Registration result: {result}")
    out = capsys.readouterr()
    assert SENTINEL not in out.out + out.err


def test_forbidden_pattern_vocabulary_is_not_the_proof():
    """Why this file exists: the vocabulary filter does not compare real values."""
    assert not any(SENTINEL in p for p in core_config.FORBIDDEN_SUBSTRING_PATTERNS)
