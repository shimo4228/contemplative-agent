"""ADR-0074 pending-staging fast-fail, for every ``--stage`` producer (T-GUARD).

The invariant — "staging holds at most one unreviewed batch" — is enforced in
two places: ``staging._stage_results`` refuses at write time, and each producer
refuses *before* its LLM work. This module covers the producer half; the
write-time half lives with ``staging.py``.

**Why these tests count backend calls instead of asserting "it refused".**
The write-time refusal already makes a refusal-only assertion pass, so a
producer that burns its LLM calls and *then* gets refused stays green — which
is precisely the regression the producer-side guard exists to prevent. Every
test here therefore counts calls at the LLM backend boundary
(``ChaosBackend.calls``), which is below ``generate_full`` and so catches any
generation path, not only the one the test author thought of.

**Why each test is paired with an anchor.** A zero-call assertion also passes
when the fixture never drives the producer to an LLM call at all (missing
corpus, unmet precondition). Each ``..._skips_llm_when_staging_pending`` test is
therefore paired with a ``..._reaches_llm_when_staging_empty`` anchor over the
*same* fixture: the anchor failing means the guard test was vacuous.

``insight`` is the pattern's origin and keeps its own coverage in
``test_cli_memory.py::TestInsightStagePathADR0074``.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.core.llm import configure, reset_llm_config
from tests.chaos import ChaosBackend

SELF_REFLECTION_PATTERNS = [
    {"pattern": "I notice I hedge when a question has no clean answer."},
    {"pattern": "I return to the same three metaphors under time pressure."},
    {"pattern": "I treat silence in a thread as disinterest more often than it is."},
    {"pattern": "I over-trust my own summaries of other agents' posts."},
]


def _prefill_staging(staged_dir, *, held=False):
    """One unreviewed batch already sitting in staging."""
    staged_dir.mkdir(parents=True, exist_ok=True)
    (staged_dir / "old.md").write_text("# Old candidate\n")
    sidecar: dict[str, object] = {"target": "x"}
    if held:
        sidecar["held"] = True
    (staged_dir / "old.md.meta.json").write_text(json.dumps(sidecar) + "\n")


class TestRefusalNamesTheHeldShare:
    """T-ADOPT-HOLD survives the T-GUARD hoist.

    The held-count breakdown was added to the write-time message so an
    operator could tell "nobody reached this batch" from "I chose to keep
    it". Since the producer-side guard fires first, that message is no
    longer reached on the pending path — so the breakdown has to travel
    with the guard or it goes dark exactly when it matters.
    """

    def test_producer_side_refusal_names_held_items(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        _prefill_staging(staged_dir, held=True)
        with patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir):
            from contemplative_agent.cli import staging

            assert staging._refuse_if_pending("distill-identity") is True
        assert "explicitly held at a past gate" in capsys.readouterr().out

    def test_says_nothing_about_holds_when_none_are_held(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        _prefill_staging(staged_dir)
        with patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir):
            from contemplative_agent.cli import staging

            assert staging._refuse_if_pending("insight") is True
        assert "held at a past gate" not in capsys.readouterr().out

    def test_empty_staging_does_not_refuse(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir(parents=True)
        with patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir):
            from contemplative_agent.cli import staging

            assert staging._refuse_if_pending("insight") is False
        assert capsys.readouterr().out == ""


@contextmanager
def _chaos_backend():
    """Inject a call-recording backend; always restore global LLM config."""
    backend = ChaosBackend(schedule=[])
    reset_llm_config()
    configure(backend=backend)
    try:
        yield backend
    finally:
        reset_llm_config()


def _skill_corpus(directory, count=4):
    """A corpus that clears the structural quality checks.

    Bodies are padded past the 200-char floor on purpose: a short body is
    flagged low-quality, and the non-``--stage`` path then opens an
    interactive drop prompt that reads stdin. That is a different code path
    from the one under test.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (directory / f"skill-{i}.md").write_text(
            f"---\nname: skill-{i}\ndescription: Ask before assuming, case {i}\n---\n\n"
            f"# Skill {i}\n\n## When to Use\n\n"
            f"Ask a clarifying question before acting on case {i}. When the request "
            f"names an outcome but not a constraint, the constraint is the part that "
            f"decides the work, so surface it before writing anything. Restate what "
            f"you heard in one line and let the asker correct it cheaply.\n"
        )
    return directory


# ---------------------------------------------------------------------------
# memory_cmds producers: distill-identity / amend-constitution
# ---------------------------------------------------------------------------


class TestDistillIdentityPendingGuard:
    def _run(self, tmp_path, *, prefill):
        staged_dir = tmp_path / ".staged"
        if prefill:
            _prefill_staging(staged_dir)
        args = argparse.Namespace(stage=True, constitution_dir=None)
        registry = MagicMock()
        registry.find_by_view.return_value = SELF_REFLECTION_PATTERNS
        with (
            _chaos_backend() as backend,
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.adapters.moltbook.config.IDENTITY_PATH", tmp_path / "id.md"),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "audit.jsonl"),
            patch(
                "contemplative_agent.cli.memory_cmds._load_view_registry",
                return_value=registry,
            ),
            patch(
                "contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None
            ) as snapshot,
        ):
            from contemplative_agent.cli.memory_cmds import _handle_distill_identity

            _handle_distill_identity(args, MagicMock())
        return backend, snapshot

    def test_reaches_llm_when_staging_empty(self, tmp_path):
        """Anchor: without this the guard test below could pass vacuously."""
        backend, _ = self._run(tmp_path, prefill=False)
        assert len(backend.calls) >= 1

    def test_skips_llm_when_staging_pending(self, tmp_path, capsys):
        backend, snapshot = self._run(tmp_path, prefill=True)
        assert backend.calls == []
        # The snapshot precedes the LLM call, so the guard must precede it too.
        snapshot.assert_not_called()
        assert "adopt-staged" in capsys.readouterr().out


class TestAmendConstitutionPendingGuard:
    def _run(self, tmp_path, *, prefill):
        staged_dir = tmp_path / ".staged"
        constitution_dir = tmp_path / "constitution"
        constitution_dir.mkdir(parents=True, exist_ok=True)
        (constitution_dir / "01-core.md").write_text(
            "# Core\n\nPrefer the reading that reduces suffering.\n"
        )
        if prefill:
            _prefill_staging(staged_dir)
        args = argparse.Namespace(stage=True, constitution_dir=constitution_dir)
        registry = MagicMock()
        registry.find_by_view.return_value = SELF_REFLECTION_PATTERNS
        with (
            _chaos_backend() as backend,
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "audit.jsonl"),
            patch(
                "contemplative_agent.cli.memory_cmds._load_view_registry",
                return_value=registry,
            ),
            patch(
                "contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None
            ) as snapshot,
        ):
            from contemplative_agent.cli.memory_cmds import _handle_amend_constitution

            _handle_amend_constitution(args, MagicMock())
        return backend, snapshot

    def test_reaches_llm_when_staging_empty(self, tmp_path):
        backend, _ = self._run(tmp_path, prefill=False)
        assert len(backend.calls) >= 1

    def test_skips_llm_when_staging_pending(self, tmp_path, capsys):
        backend, snapshot = self._run(tmp_path, prefill=True)
        assert backend.calls == []
        snapshot.assert_not_called()
        assert "adopt-staged" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Mechanical net over the registry, so the producer list is not maintained by
# hand here as well. The per-producer tests above assert the guard *works*;
# this one asserts nobody added a --stage command without one. That gap is the
# reason this task existed: the producer list was originally read off
# ``grep _stage_results``, which undercounts (two handlers share one call site)
# and mislocates (the call sites sit in shared tails, one frame below the LLM
# call). Deriving the list from the registry removes the hand-count entirely.
# ---------------------------------------------------------------------------


def _stage_producer_specs():
    """Every registered command whose parser exposes ``--stage``."""
    from contemplative_agent.cli import COMMANDS

    specs = []
    for spec in COMMANDS:
        parser = argparse.ArgumentParser(prog=spec.name, add_help=False)
        spec.add_arguments(parser)
        options = {opt for action in parser._actions for opt in action.option_strings}
        if "--stage" in options:
            specs.append(spec)
    return specs


class TestEveryStageProducerIsGuarded:
    """Pin the guard's per-handler placement, which is intentional rather than
    a missed refactor: these tests call the handlers directly, as scripts do,
    so hoisting ``_refuse_if_pending`` into ``main()``'s dispatch would leave
    that entry path unguarded (T-GUARD)."""

    def test_registry_lists_the_expected_producers(self):
        """Pin the set, so a new --stage command is a visible decision rather
        than a silent addition that the loop below happens to cover."""
        names = {spec.name for spec in _stage_producer_specs()}
        assert names == {
            "distill-identity",
            "amend-constitution",
            "insight",
        }

    @pytest.mark.parametrize("spec", _stage_producer_specs(), ids=lambda s: s.name)
    def test_handler_consults_the_guard_before_anything_else(self, spec):
        """With the guard answering "pending", the handler must return without
        touching its runtime. Nothing is patched except the guard itself, so a
        handler that skips it crashes or hangs on real config here rather than
        passing — and one that calls it late fails the ``_take_snapshot`` and
        backend assertions."""
        with (
            _chaos_backend() as backend,
            patch("contemplative_agent.cli.staging._refuse_if_pending", return_value=True) as guard,
            patch("contemplative_agent.cli.memory_cmds._take_snapshot") as snapshot,
        ):
            spec.resolve()(argparse.Namespace(stage=True), MagicMock())

        guard.assert_called_once_with(spec.name)
        snapshot.assert_not_called()
        assert backend.calls == []
