"""README Quick Start, end to end, with nothing set (P0-05.9).

``init -> register -> run --session 1`` goes through ``cli.main`` and a real
``Agent`` in a fresh interpreter whose only environment is ``HOME`` (so the home
is the default ``$HOME/.config/moltbook`` and no ``DECISION_*`` / ``MOLTBOOK_*``
variable exists). ``tests/quickstart_harness.py`` replaces the network
(``responses`` for moltbook.com) and the two model paths (a stub generation
backend, a stub decision backend that answers ``answered`` with P(top) = 0.6).
It looks at CLI wiring only, never at what the model wrote.

The run uses ``--auto``: the default ``--approve`` prompts on stdin, which a
test (like a cron job) does not have.

Why a subprocess: ``adapters.moltbook.config`` freezes its paths at import time,
so an in-process test could only reach the unset-env wiring through a patched
home — which is not the thing under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from contemplative_agent.core.llm import ollama_model

HARNESS = Path(__file__).with_name("quickstart_harness.py")


def _quickstart(home: Path, **extra_env: str) -> tuple[dict, str]:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), **extra_env}
    proc = subprocess.run(
        [sys.executable, str(HARNESS)],
        env=env,
        cwd=home,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), proc.stderr


def _engaged(summary: dict) -> list[str]:
    return [c for c in summary["calls"] if c.endswith("/upvote") or c.endswith("/comments")]


def test_quickstart_runs_one_engage_with_no_environment(tmp_path):
    summary, _stderr = _quickstart(tmp_path)

    assert summary["rc"] == {"init": 0, "register": 0, "run": 0}
    # The env-less default wiring: the decision backend exists, reads the
    # Ollama generation model, and swaps no model (not exclusive).
    assert summary["wiring"]["model"] == ollama_model()
    assert summary["wiring"]["exclusive"] is False
    assert summary["decision_model_env"] is None
    # One engage: the gate passed the post, so the agent upvoted and commented.
    assert any(c.endswith("/upvote") for c in _engaged(summary))
    assert any(c.endswith("/comments") for c in _engaged(summary))
    # README says init writes into ~/.config/moltbook/ and register saves the key there.
    home = tmp_path / ".config" / "moltbook"
    assert (home / "identity.md").is_file()
    assert (home / "credentials.json").is_file()


def test_quickstart_with_an_empty_decision_model_engages_with_nothing(tmp_path):
    """The pair case: ``DECISION_MODEL=`` leaves no backend and the gate fails closed."""
    summary, stderr = _quickstart(tmp_path, DECISION_MODEL="")

    assert summary["rc"]["run"] == 0
    assert summary["wiring"] == {}  # no decision backend was constructed
    assert _engaged(summary) == []
    assert "fails" in stderr and "closed" in stderr
