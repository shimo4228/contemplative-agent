"""core/portable_path.py — the one home-path normaliser (RFC-0050 / RFC-0051).

The path-column cases live in test_snapshot.py (through ``snapshot._portable_path``).
Pinned here: ``redact_home`` matches the home in any letter case, because macOS
file systems are case-insensitive and a writer that lowercases a log line still
names the user (``.anomaly-sweep-state.tsv``, found in the 2026-10-15 review).
"""

from __future__ import annotations

from pathlib import Path

from contemplative_agent.core.portable_path import portable_path, redact_home


def test_redact_home_replaces_every_occurrence_in_any_case(tmp_path, monkeypatch):
    home = tmp_path / "Users" / "SomeUser"
    monkeypatch.setenv("HOME", str(home))
    text = f"a {home}/x b {str(home).lower()}/y c {str(home).upper()}"
    out = redact_home(text)
    assert out == "a ~/x b ~/y c ~"
    assert "someuser" not in out.lower()


def test_redact_home_leaves_text_alone_when_home_is_root(monkeypatch):
    monkeypatch.setenv("HOME", "/")
    assert redact_home("/srv/a") == "/srv/a"


def test_an_alias_in_another_case_is_redacted(tmp_path, monkeypatch):
    home = tmp_path / "Users" / "SomeUser"
    monkeypatch.setenv("HOME", str(home))
    alias = Path("/System/Volumes/Data") / str(home).lower().lstrip("/") / "x"
    out = portable_path(alias, None)
    assert out is not None and "someuser" not in out.lower()
