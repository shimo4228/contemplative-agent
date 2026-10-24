"""P1-10.7: the dialogue peer subprocess gets an allowlisted env, not os.environ."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from contemplative_agent.cli import session_cmds


def _spawn(tmp_path: Path) -> dict[str, str]:
    with patch.object(session_cmds.subprocess, "Popen") as popen:
        session_cmds._spawn_dialogue_peer(
            home=tmp_path / "home-a", turns=2, stdin_fd=0, stdout_fd=1
        )
    return popen.call_args.kwargs["env"]


def test_no_api_key_reaches_peer(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLTBOOK_API_KEY", "sentinel-moltbook")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sentinel-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-openai")
    monkeypatch.setenv("HF_TOKEN", "sentinel-hf")
    env = _spawn(tmp_path)
    assert not [k for k in env if "_API_KEY" in k]
    assert "HF_TOKEN" not in env
    assert "sentinel" not in "".join(env.values())


def test_allowlisted_names_pass_and_home_is_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "m")
    monkeypatch.setenv("CONTEMPLATIVE_DIALOGUE_PEER_MODULE", "x.y")
    monkeypatch.setenv("MOLTBOOK_HOME", "/somewhere/else")
    env = _spawn(tmp_path)
    assert env["OLLAMA_MODEL"] == "m"
    assert env["CONTEMPLATIVE_DIALOGUE_PEER_MODULE"] == "x.y"
    assert "PATH" in env
    assert env["MOLTBOOK_HOME"] == str(tmp_path / "home-a")
