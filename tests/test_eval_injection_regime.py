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

The flag itself retired on 2026-08-08, which is why nothing here sets or
isolates it any more: the regime now follows from the wiring alone, so the
pin and the enacted regime cannot be separated by an environment.
"""

from __future__ import annotations

import os

import pytest

from contemplative_agent.core import skill_selection
from contemplative_agent.core.llm import NUM_CTX, configure, reset_llm_config
from evals.run_eval import FIXTURE_DIR, INJECTION_REGIME, _configure_pinned_assets


@pytest.fixture
def clean_config(tmp_path):
    reset_llm_config()
    skill_selection.reset_skill_selection()
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

    def test_configuring_mutates_no_process_global_environment(self, clean_config):
        """``_configure_pinned_assets`` used to assign the enforcement flag
        into the real ``os.environ``, which leaked past teardown unless the
        fixture pre-seeded the name — a hazard worth keeping pinned now that
        no fixture guards against it. Snapshot comparison rather than a
        single-name check: any process-global write from a function named
        "configure pinned assets" is the defect."""
        before = dict(os.environ)
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert dict(os.environ) == before

    def test_stale_export_cannot_move_the_regime(self, clean_config, monkeypatch):
        """The retired name is inert: the pin is enacted by wiring alone."""
        monkeypatch.setenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", "0")
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert skill_selection.configured_injection_regime() == INJECTION_REGIME

    def test_unconfigured_selection_reports_full_corpus(self, clean_config):
        """The surviving kill switch: with ``audit_dir`` unset the selector is
        off entirely, which under ADR-0081 means full injection."""
        assert skill_selection.configured_injection_regime() == skill_selection.REGIME_FULL_CORPUS

    def test_shadow_regime_literal_survives_for_historical_manifests(self):
        """``full_corpus_shadow_observed`` is unreachable since the flag
        retired, but baselines approved before 2026-08-08 record it. The
        literal has to stay resolvable so the compare layer can tell
        'incomparable' from 'unrecognised'."""
        assert skill_selection.REGIME_FULL_CORPUS_SHADOW == "full_corpus_shadow_observed"


class TestConfiguredRegimeIsACeilingNotAnOutcome:
    """The distinction the first version of this change got wrong.

    ``configured_injection_regime()`` reads one global; four further
    conditions can still route an individual call back to full-corpus
    injection. Two of them are deterministic and belong in a preflight.
    """

    def test_empty_catalog_is_reported_as_an_unmet_precondition(self, clean_config, tmp_path):
        empty = tmp_path / "no-skills"
        empty.mkdir()
        skill_selection.configure_skill_selection(skills_dir=empty, audit_dir=clean_config)
        assert (
            skill_selection.configured_injection_regime()
            == skill_selection.REGIME_TWO_PASS_SELECTED
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


class TestSkillsOffArm:
    """RFC-0017 の一時アーム: skill を一切注入しない run を、on と同じ fixture から立てる。

    読み終えたら撤去する（RFC-0017 消費計画）。on の pin (``INJECTION_REGIME``) は
    不変で、off は manifest に ``no_skills`` を書く — 配線の読み値 ``full_corpus``
    は「全 skill 注入」の意味なので記録しない。fixture の ``skills/`` はディスクに
    残るので assets_sha256 は on と同一、regime だけが違い ``--baseline`` 比較は
    exit 2 のまま（fail-closed 維持）。
    """

    def test_arm_table_maps_off_to_full_corpus_and_on_to_the_pin(self):
        from evals.run_eval import ARM_REGIMES

        assert ARM_REGIMES["skills-on"] == INJECTION_REGIME
        assert ARM_REGIMES["skills-off"] == "no_skills"
        assert ARM_REGIMES["skills-off"] != skill_selection.REGIME_FULL_CORPUS
        assert set(ARM_REGIMES) == {"skills-on", "skills-off"}

    def test_off_arm_leaves_the_selector_unwired(self, clean_config):
        _configure_pinned_assets(FIXTURE_DIR, clean_config, skills=False)
        assert skill_selection.configured_injection_regime() == skill_selection.REGIME_FULL_CORPUS
        assert not clean_config.exists(), "off arm must not create a selection audit dir"

    def test_off_arm_system_prompt_carries_no_skills_but_keeps_identity(self, clean_config):
        from contemplative_agent.core.llm import get_identity_system_prompt, prompting

        _configure_pinned_assets(FIXTURE_DIR, clean_config, skills=False)
        prompt = prompting._build_system_prompt()
        assert "<learned_skills>" not in prompt
        sentinel = next(
            line.strip()
            for line in (FIXTURE_DIR / "identity.md").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        assert sentinel in get_identity_system_prompt()

    def test_on_arm_is_the_default_and_unchanged(self, clean_config):
        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        assert skill_selection.configured_injection_regime() == INJECTION_REGIME
        assert skill_selection.selection_preconditions_unmet() is None

    def test_regime_sentinel_accepts_only_the_enacted_regime(self, clean_config):
        from evals.run_eval import _assert_regime_enacted

        _configure_pinned_assets(FIXTURE_DIR, clean_config, skills=False)
        _assert_regime_enacted("no_skills")
        with pytest.raises(SystemExit) as exc:
            _assert_regime_enacted(INJECTION_REGIME)
        assert exc.value.code == 2

    def test_regime_sentinel_rejects_off_regime_when_selector_is_wired(self, clean_config):
        from evals.run_eval import _assert_regime_enacted

        _configure_pinned_assets(FIXTURE_DIR, clean_config)
        _assert_regime_enacted(INJECTION_REGIME)
        with pytest.raises(SystemExit) as exc:
            _assert_regime_enacted("no_skills")
        assert exc.value.code == 2

    def test_off_arm_generation_makes_one_call_with_no_skill_body(self, clean_config):
        """End-to-end through the production function the eval calls — the
        seam the unit test above cannot see (``generate_comment`` never calls
        ``_build_system_prompt`` directly; ``system=None`` reaches it inside
        ``core.llm``). One backend call proves no pass-1 selector ran; no
        catalog body in the system prompt proves no corpus was wired."""
        from contemplative_agent.adapters.moltbook.llm_functions import generate_comment
        from tests.test_llm_backend import FakeBackend

        _configure_pinned_assets(FIXTURE_DIR, clean_config, skills=False)
        backend = FakeBackend(responses=["A grounded reply."])
        configure(backend=backend)
        generate_comment("What persists when a belief dissolves?")

        assert len(backend.calls) == 1, "a second call means the pass-1 selector ran"
        system = backend.calls[-1]["system"] or ""
        assert "<learned_skills>" not in system
        assert "<learned_rules>" in system, (
            "rules must still reach the prompt (single-variable contrast)"
        )
        # Bodies are read from the fixture files directly: on this arm the
        # selector is unwired, so selected_skills_block() has no catalog to
        # render from and would return "" for every name (a vacuous check).
        skill_files = sorted((FIXTURE_DIR / "skills").glob("*.md"))
        assert len(skill_files) > 1
        for path in skill_files:
            text = path.read_text(encoding="utf-8")
            body = text.split("---", 2)[2] if text.startswith("---") else text
            line = next(ln.strip() for ln in body.splitlines() if len(ln.strip()) >= 20)
            assert line not in system, f"skill {path.name!r} reached the off-arm prompt"
