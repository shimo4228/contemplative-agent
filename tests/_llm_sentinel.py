"""Detect un-mocked LLM calls (P1-08.3 / P1-08.8).

``tests/conftest.py`` points ``OLLAMA_BASE_URL`` at ``127.0.0.1:1``, an
unreachable port, so a test that forgot to mock the LLM gets a refused
connection. ``generate()`` swallows that and returns ``None``, and every
caller treats ``None`` as fail-open, so the test goes green having tested
"nothing happened" (the shape of the 2026-10-09 Quick Start incident).

This autouse fixture records every ``connect`` to the sentinel address and
fails the test at teardown unless it carries ``@pytest.mark.allow_unmocked_llm``
(a test that *means* to exercise LLM unreachability). The connect itself still
proceeds and is refused exactly as before, so test semantics are unchanged.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

SENTINEL = ("127.0.0.1", 1)
MARKER = "allow_unmocked_llm"


@pytest.fixture(autouse=True)
def _unmocked_llm_guard(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    attempts: list[object] = []
    real_connect = socket.socket.connect

    def connect(self: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and tuple(address[:2]) == SENTINEL:
            attempts.append(address)
        return real_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", connect)
    yield
    monkeypatch.undo()
    if attempts and request.node.get_closest_marker(MARKER) is None:
        pytest.fail(
            f"{len(attempts)} un-mocked LLM connection(s) to {SENTINEL[0]}:{SENTINEL[1]}; "
            f"mock the LLM, or mark the test @pytest.mark.{MARKER} if unreachability is the point",
            pytrace=False,
        )
