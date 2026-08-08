"""The eval must measure production's skill-injection regime (ADR-0089 amendment).

The 2026-08-06 eval layer skipped ``configure_skill_selection`` on the
stated premise that "production runs it in shadow mode". That premise was
already false when written: ADR-0081 two-pass enforcement shipped in
``0723726`` (2026-07-24) and the launchd plist has carried
``MOLTBOOK_SKILL_SELECTION_ENFORCE=1`` since 2026-08-01. The eval therefore
injected the whole skill corpus while production injected a selection —
measuring a system that does not exist.

Two properties are pinned here, and the split matters:

* ``INJECTION_REGIME`` names what the eval pins. It is a manifest field and
  a staleness signal, so a future divergence surfaces mechanically instead
  of relying on a prose "revisit when …" trigger (the trigger that failed).
* ``_configure_pinned_assets`` must *enact* that name. Without this half the
  constant could drift from the wiring and lie in the manifest — the same
  class of defect one layer up.
"""

from __future__ import annotations

import os

import pytest

from contemplative_agent.core import skill_selection
from contemplative_agent.core.llm import NUM_CTX, configure, reset_llm_config
from evals.run_eval import FIXTURE_DIR, INJECTION_REGIME, _configure_pinned_assets


@pytest.fixture
def clean_config(monkeypatch, tmp_path):
    """Isolate both halves of the regime state.

    ``setenv``, not ``delenv(raising=False)``: ``_configure_pinned_assets``
    assigns the enforcement flag into the real ``os.environ``, and pytest's
    ``delenv`` registers no undo entry when the name was absent, so the
    assignment would survive teardown and leave enforcement globally ON for
    every later test in the process. ``setenv`` does register an undo.
    """
    reset_llm_config()
    skill_selection.reset_skill_selection()
    monkeypatch.setenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", "")
    yield tmp_path / "audit"
    reset_llm_config()
    skill_selection.reset_skill_selection()


class TestPinnedRegime:
    def test_eval_pins_the_two_pass_selected_regime(self):
        """The regime production runs under ADR-0081 enforcement.

        Also the only thing binding ``run_eval``'s literal to the core
        constant — the literal exists because nothing from
        ``contemplative_agent`` may be imported at that module's load time.
        """
        assert INJECTION_REGIME == skill_selection.REGIME_TWO_PASS_SELECTED

    def test_configuration_permits_the_pinned_regime(self, clean_config):
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert skill_selection.configured_injection_regime() == INJECTION_REGIME

    def test_configuring_does_not_leak_the_flag_past_teardown(self, clean_config):
        """Guard on the fixture itself.

        ``_configure_pinned_assets`` writes the enforcement flag into the
        real environment. If that escaped the test, every later test in the
        process would silently run with ADR-0081 enforcement ON and
        "default off" would stop being a testable property of the suite.
        """
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert os.environ["MOLTBOOK_SKILL_SELECTION_ENFORCE"] == "1"
        # The assertion that matters is in the fixture's monkeypatch undo;
        # this test exists so a fixture regression has somewhere to fail.

    def test_unconfigured_selection_reports_full_corpus(self, clean_config):
        """The pre-fix state, named — the kill switch alone forces full injection
        regardless of the enforcement flag."""
        assert skill_selection.configured_injection_regime() == skill_selection.REGIME_FULL_CORPUS

    def test_shadow_mode_still_injects_the_full_corpus(self, clean_config, monkeypatch):
        """Shadow observation is not a third injection behaviour: the selector
        runs and is recorded, but ``_selection_system(None)`` still yields the
        full corpus. Named separately so a manifest can distinguish
        'never observed' from 'observed, not enforced'."""
        monkeypatch.setenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", "")
        skill_selection.configure_skill_selection(
            skills_dir=FIXTURE_DIR / "skills", audit_dir=clean_config
        )
        regime = skill_selection.configured_injection_regime()
        assert regime == skill_selection.REGIME_FULL_CORPUS_SHADOW


class TestConfiguredRegimeIsACeilingNotAnOutcome:
    """The distinction the first version of this change got wrong.

    ``configured_injection_regime()`` reads two globals; four further
    conditions can still route an individual call back to full-corpus
    injection. Two of them are deterministic and belong in a preflight.
    """

    def test_empty_catalog_is_reported_as_an_unmet_precondition(self, clean_config, tmp_path):
        empty = tmp_path / "no-skills"
        empty.mkdir()
        skill_selection.configure_skill_selection(skills_dir=empty, audit_dir=clean_config)
        assert skill_selection.configured_injection_regime() in (
            skill_selection.REGIME_TWO_PASS_SELECTED,
            skill_selection.REGIME_FULL_CORPUS_SHADOW,
        )
        unmet = skill_selection.selection_preconditions_unmet()
        assert unmet is not None and "empty skill catalog" in unmet

    def test_populated_catalog_has_no_unmet_preconditions(self, clean_config):
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert skill_selection.selection_preconditions_unmet() is None


class TestObservedOutcomes:
    """The manifest's regime is a pin; this is the observation beside it."""

    def test_absent_audit_dir_is_reported_not_raised(self, tmp_path):
        out = skill_selection.observed_injection_outcomes(tmp_path / "never-written")
        assert out["records"] == 0 and "unavailable" in out

    def test_enforced_and_fallback_records_are_counted_separately(self, tmp_path):
        audit = tmp_path / "sel"
        audit.mkdir()
        (audit / "skill-selection-2026-08-08.jsonl").write_text(
            '{"verdict": "judged", "enforced": true}\n'
            '{"verdict": "fail_open_llm", "enforced": false}\n'
            '{"verdict": "judged", "enforced": true}\n',
            encoding="utf-8",
        )
        out = skill_selection.observed_injection_outcomes(audit)
        assert out["records"] == 3
        assert out["enforced"] == 2
        assert out["fell_back"] == 1
        assert out["verdicts"]["fail_open_llm"] == 1

    def test_unparseable_line_is_counted_never_fatal(self, tmp_path):
        audit = tmp_path / "sel"
        audit.mkdir()
        (audit / "skill-selection-2026-08-08.jsonl").write_text("{not json}\n", encoding="utf-8")
        out = skill_selection.observed_injection_outcomes(audit)
        assert out["verdicts"]["UNPARSEABLE_RECORD"] == 1


class TestRegimeIsNotCosmetic:
    """Why the divergence mattered, pinned as arithmetic rather than prose."""

    def test_full_corpus_leaves_almost_no_context_budget(self, clean_config):
        from contemplative_agent.core.llm import _estimate_tokens, prompting

        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        full = _estimate_tokens(prompting._build_system_prompt())
        selected = _estimate_tokens(prompting.build_system_prompt_with_skills(""))
        # The full corpus consumes most of the window on its own, so
        # num_predict is clamped (llm/__init__ audit-C2 guard) before a single
        # post is added; a selection-filtered prompt is not.
        assert full > NUM_CTX * 0.8
        assert selected < NUM_CTX * 0.2


class TestGenerationTakesTheTwoPassPath:
    def test_comment_generation_injects_only_selected_skills(self, clean_config):
        """End-to-end through the production function the eval calls.

        Pass 1 returns one catalog name; pass 2 must then inject that skill's
        body alone. Asserted on the system prompt the backend actually
        received — the artefact the model conditions on.
        """
        from contemplative_agent.adapters.moltbook.llm_functions import generate_comment
        from contemplative_agent.core.llm.prompting import _build_system_prompt
        from tests.test_llm_backend import FakeBackend

        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        catalog = skill_selection.load_skill_catalog(FIXTURE_DIR / "skills")
        assert len(catalog) > 1, "fixture needs several skills for this to mean anything"
        chosen = catalog[0].name

        backend = FakeBackend(responses=[chosen, "A grounded reply."])
        configure(backend=backend)
        generate_comment("What persists when a belief dissolves?")

        publish_system = backend.calls[-1]["system"]
        # Bind against BODIES, not catalog names. Both injection paths strip
        # frontmatter, and the catalog name lives only in the frontmatter, so
        # asserting `name not in prompt` is true even under full-corpus
        # injection — the first version of this test proved nothing.
        selected_body = skill_selection.selected_skills_block((chosen,))
        assert selected_body, "the chosen skill must contribute a body"
        assert selected_body in publish_system, "the selected skill's body was not injected"

        full_corpus = _build_system_prompt()
        assert len(publish_system) < len(full_corpus), (
            "publish prompt is not smaller than full-corpus injection — "
            f"{len(publish_system)} vs {len(full_corpus)} chars"
        )
        # And a specific unselected body really is absent.
        other = skill_selection.selected_skills_block((catalog[1].name,))
        assert other and other not in publish_system, (
            f"unselected skill {catalog[1].name!r} reached the publish system prompt"
        )
