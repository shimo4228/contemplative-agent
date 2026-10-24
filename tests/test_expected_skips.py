"""The expected-skip table's comparison (P1-08.2)."""

from __future__ import annotations

from tests import _expected_skips as table

OLLAMA = ("t::a", "Ollama embedding model unavailable")
DARWIN = ("t::b", "rotate-log.sh runs under the macOS launchd job")


def test_the_expected_set_is_clean():
    assert table.compare([OLLAMA, DARWIN], "linux", False) == []


def test_one_unclassified_skip_is_a_problem():
    problems = table.compare([OLLAMA, ("t::x", "flaky today")], "linux", False)
    assert any("unclassified" in p for p in problems)


def test_a_darwin_skip_on_macos_is_a_problem():
    problems = table.compare([OLLAMA, DARWIN], "darwin", False)
    assert any("'darwin'" in p for p in problems)


def test_chmod_skips_only_belong_to_root():
    chmod = ("t::c", "chmod(0o000) does not block root, so the fault cannot be injected")
    assert table.compare([OLLAMA, chmod], "linux", False)
    assert table.compare([OLLAMA, *[chmod] * 10], "linux", True) == []


def test_a_vanished_category_is_a_problem():
    assert table.compare([DARWIN], "linux", False)
