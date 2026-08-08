"""Tests for the skill-selection shadow instrument (ADR-0076)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core import skill_selection as ss
from contemplative_agent.core.llm import _estimate_tokens
from contemplative_agent.core.skill_selection import (
    SkillCatalogEntry,
    load_skill_catalog,
    select_applicable_skills,
)

PROMPT_TEMPLATE = "Pick skills.\n\n{skill_catalog}\n\nSituation:\n{situation}\n\nNames only."


def _write_skill(directory: Path, filename: str, name: str, description: str) -> Path:
    path = directory / filename
    path.write_text(
        f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n\nbody of {name}\n',
        encoding="utf-8",
    )
    return path


def _catalog() -> tuple[SkillCatalogEntry, ...]:
    return (
        SkillCatalogEntry(name="skill-a", description="desc a", body_tokens=100),
        SkillCatalogEntry(name="skill-b", description="desc b", body_tokens=200),
    )


@pytest.fixture(autouse=True)
def _reset_module_state():
    yield
    ss.reset_skill_selection()


class TestLoadSkillCatalog:
    def test_reads_name_description_and_tokens(self, tmp_path):
        text_path = _write_skill(tmp_path, "a.md", "skill-a", "does a")
        catalog = load_skill_catalog(tmp_path)
        assert len(catalog) == 1
        entry = catalog[0]
        assert entry.name == "skill-a"
        assert entry.description == "does a"
        assert entry.body_tokens == _estimate_tokens(text_path.read_text(encoding="utf-8"))

    def test_multiple_sorted_and_dotfiles_skipped(self, tmp_path):
        _write_skill(tmp_path, "b.md", "skill-b", "does b")
        _write_skill(tmp_path, "a.md", "skill-a", "does a")
        _write_skill(tmp_path, ".hidden.md", "hidden", "nope")
        catalog = load_skill_catalog(tmp_path)
        assert [e.name for e in catalog] == ["skill-a", "skill-b"]

    def test_unreadable_file_warns_and_skips(self, tmp_path, caplog):
        _write_skill(tmp_path, "a.md", "skill-a", "does a")
        bad = _write_skill(tmp_path, "bad.md", "skill-bad", "nope")
        bad.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING):
                catalog = load_skill_catalog(tmp_path)
        finally:
            bad.chmod(0o644)
        assert [e.name for e in catalog] == ["skill-a"]
        assert any("unreadable" in r.message for r in caplog.records)

    def test_none_or_missing_dir_returns_empty(self, tmp_path):
        assert load_skill_catalog(None) == ()
        assert load_skill_catalog(tmp_path / "nope") == ()


@patch(
    "contemplative_agent.core.skill_selection._load_selection_template",
    new=lambda: PROMPT_TEMPLATE,
)
class TestSelectApplicableSkills:
    @patch("contemplative_agent.core.skill_selection.generate")
    def test_mixed_real_and_hallucinated_names(self, mock_generate):
        mock_generate.return_value = "skill-a\nskill-x"
        result = select_applicable_skills("situation text", _catalog())
        assert result.verdict == "judged"
        assert result.selected == ("skill-a",)
        assert result.rejected_names == ("skill-x",)
        assert result.raw_output == "skill-a\nskill-x"
        # Selection call runs think-OFF with its own caller label.
        kwargs = mock_generate.call_args.kwargs
        assert kwargs["caller"] == "core.skill_selection"
        assert kwargs["think"] is False

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_none_sentinel_means_no_skill_applies(self, mock_generate):
        mock_generate.return_value = "none"
        result = select_applicable_skills("situation", _catalog())
        assert result.verdict == "judged"
        assert result.selected == ()
        assert result.rejected_names == ()

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_llm_failure_is_fail_open_llm(self, mock_generate):
        mock_generate.return_value = None
        result = select_applicable_skills("situation", _catalog())
        assert result.verdict == "fail_open_llm"
        assert result.selected == ()
        assert result.raw_output is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_blank_output_is_fail_open_parse(self, mock_generate):
        mock_generate.return_value = "   \n  "
        result = select_applicable_skills("situation", _catalog())
        assert result.verdict == "fail_open_parse"
        assert result.selected == ()

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_all_hallucinated_is_still_judged(self, mock_generate):
        # "Parse failed" and "every pick was wrong" are different events;
        # the latter is first-class enforcement-decision data.
        mock_generate.return_value = "skill-x\nskill-y"
        result = select_applicable_skills("situation", _catalog())
        assert result.verdict == "judged"
        assert result.selected == ()
        assert result.rejected_names == ("skill-x", "skill-y")

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_match_is_case_insensitive_and_canonical(self, mock_generate):
        mock_generate.return_value = "SKILL-A"
        result = select_applicable_skills("situation", _catalog())
        assert result.selected == ("skill-a",)

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_selected_names_are_deduplicated_and_sorted(self, mock_generate):
        mock_generate.return_value = "skill-b\nskill-a\nskill-b"
        result = select_applicable_skills("situation", _catalog())
        assert result.selected == ("skill-a", "skill-b")

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_prompt_carries_catalog_and_situation(self, mock_generate):
        mock_generate.return_value = "none"
        result = select_applicable_skills("THE-SITUATION", _catalog())
        prompt = mock_generate.call_args[0][0]
        assert "skill-a — desc a" in prompt
        assert "THE-SITUATION" in prompt
        assert result.prompt == prompt


class TestShadowObserve:
    def _configure(self, tmp_path, monkeypatch, *, with_skills=True):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        if with_skills:
            _write_skill(skills_dir, "a.md", "skill-a", "does a")
            _write_skill(skills_dir, "b.md", "skill-b", "does b")
        audit_dir = tmp_path / "logs"
        ss.configure_skill_selection(skills_dir=skills_dir, audit_dir=audit_dir)
        monkeypatch.setattr(ss, "_load_selection_template", lambda: PROMPT_TEMPLATE)
        return skills_dir, audit_dir

    @staticmethod
    def _records(audit_dir: Path) -> list[dict]:
        files = sorted(audit_dir.glob("skill-selection-*.jsonl"))
        assert files, f"no audit file in {audit_dir}"
        return [
            json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines()
        ]

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_judged_record_schema(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = "skill-a\nskill-x"
        ss.shadow_observe_skill_selection("the situation", generation_caller="moltbook.comment")
        (rec,) = self._records(tmp_path / "logs")
        assert rec["generation_caller"] == "moltbook.comment"
        assert rec["verdict"] == "judged"
        assert rec["catalog_count"] == 2
        assert rec["catalog_names"] == ["skill-a", "skill-b"]
        assert rec["selected"] == ["skill-a"]
        assert rec["selected_count"] == 1
        assert rec["rejected_names"] == ["skill-x"]
        assert rec["full_skill_tokens"] > 0
        assert 0 < rec["would_be_skill_tokens"] < rec["full_skill_tokens"]
        assert rec["ts"]
        # _b64_fields bundle round-trips.
        prompt = base64.b64decode(rec["prompt_b64"]).decode("utf-8")
        assert "the situation" in prompt
        assert rec["prompt_truncated"] is False
        assert rec["prompt_encoding"] == "base64:utf-8"
        assert len(rec["prompt_sha256"]) == 64
        output = base64.b64decode(rec["output_b64"]).decode("utf-8")
        assert output == "skill-a\nskill-x"

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_llm_failure_records_fail_open(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = None
        ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.reply")
        (rec,) = self._records(tmp_path / "logs")
        assert rec["verdict"] == "fail_open_llm"
        assert rec["selected"] == []
        assert rec["output_b64"] is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_unconfigured_audit_dir_skips_llm(self, mock_generate, tmp_path):
        # audit_dir unset = shadow disabled: no LLM call, no file.
        ss.configure_skill_selection(skills_dir=tmp_path, audit_dir=None)
        ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
        assert mock_generate.call_count == 0

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_empty_catalog_records_without_llm(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch, with_skills=False)
        ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
        assert mock_generate.call_count == 0
        (rec,) = self._records(tmp_path / "logs")
        assert rec["verdict"] == "empty_catalog"
        assert rec["catalog_count"] == 0
        assert rec["prompt_b64"] is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_missing_template_records_without_llm(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch)
        monkeypatch.setattr(ss, "_load_selection_template", lambda: "")
        ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
        assert mock_generate.call_count == 0
        (rec,) = self._records(tmp_path / "logs")
        assert rec["verdict"] == "no_template"

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_generate_exception_degrades_to_warning(
        self, mock_generate, tmp_path, monkeypatch, caplog
    ):
        self._configure(tmp_path, monkeypatch)
        mock_generate.side_effect = RuntimeError("boom")
        with caplog.at_level(logging.WARNING):
            ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
        assert any("skill selection" in r.message.lower() for r in caplog.records)

    @patch("contemplative_agent.core.skill_selection.append_jsonl_restricted")
    @patch("contemplative_agent.core.skill_selection.generate")
    def test_audit_write_failure_degrades_to_warning(
        self, mock_generate, mock_append, tmp_path, monkeypatch, caplog
    ):
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = "none"
        mock_append.side_effect = OSError("disk full")
        with caplog.at_level(logging.WARNING):
            ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
        assert any("skill selection" in r.message.lower() for r in caplog.records)

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_long_prompt_is_truncated_in_audit(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = "none"
        ss.shadow_observe_skill_selection(
            "x" * (ss._MAX_SKILL_SELECTION_AUDIT_BYTES + 1000),
            generation_caller="moltbook.comment",
        )
        (rec,) = self._records(tmp_path / "logs")
        assert rec["prompt_truncated"] is True
        assert rec["prompt_bytes"] > ss._MAX_SKILL_SELECTION_AUDIT_BYTES
        kept = base64.b64decode(rec["prompt_b64"])
        assert len(kept) == ss._MAX_SKILL_SELECTION_AUDIT_BYTES


class TestCircuitIsolation:
    """Regression for the ADR-0076 codex-review finding: repeated selector
    failures must not open the shared circuit breaker and suppress the very
    publish generation the shadow instrument observes."""

    def test_circuit_shield_blocks_accounting_and_restores(self):
        from contemplative_agent.core.llm import _circuit, circuit_shield

        _circuit.reset()
        try:
            with circuit_shield():
                for _ in range(10):
                    _circuit.record_failure()
            assert _circuit.is_open is False
            # Accounting resumes after the shield exits.
            _circuit.record_failure()
            assert _circuit._consecutive_failures == 1
        finally:
            _circuit.reset()

    def test_shield_restores_on_exception(self):
        from contemplative_agent.core.llm import _circuit, circuit_shield

        _circuit.reset()
        try:
            with pytest.raises(RuntimeError):
                with circuit_shield():
                    raise RuntimeError("boom")
            _circuit.record_failure()
            assert _circuit._consecutive_failures == 1
        finally:
            _circuit.reset()

    def test_shadow_failures_do_not_open_circuit(self, tmp_path, monkeypatch):
        from contemplative_agent.core import llm as llm_module
        from contemplative_agent.core.llm import (
            BackendResult,
            configure,
            reset_llm_config,
        )

        class FlakySelectorBackend:
            model = "test"
            context_window = 32768

            def generate(
                self,
                prompt,
                system,
                num_predict,
                format,
                *,
                temperature=1.0,
                think=False,
            ):
                if "Pick skills." in prompt:  # the selection template marker
                    return None  # the selector always fails
                return BackendResult(
                    text="real output",
                    finish_reason=None,
                    eval_count=1,
                    prompt_tokens=None,
                    cached_tokens=None,
                    thinking=None,
                )

        reset_llm_config()
        try:
            configure(default_system_prompt="sys", backend=FlakySelectorBackend())
            skills_dir = tmp_path / "skills"
            skills_dir.mkdir()
            _write_skill(skills_dir, "a.md", "skill-a", "does a")
            ss.configure_skill_selection(skills_dir=skills_dir, audit_dir=tmp_path / "logs")
            monkeypatch.setattr(ss, "_load_selection_template", lambda: PROMPT_TEMPLATE)
            for _ in range(10):
                ss.shadow_observe_skill_selection("sit", generation_caller="moltbook.comment")
            assert llm_module._circuit.is_open is False
            # The publish-path generation still goes through.
            out = llm_module.generate("content prompt", system="sys", caller="moltbook.comment")
            assert out == "real output"
        finally:
            reset_llm_config()


class TestUntrustedScrubbing:
    """Security-review findings: catalog names/descriptions and hallucinated
    rejected names must not carry control characters into the prompt, the
    audit log, or the terminal report."""

    def test_catalog_name_is_scrubbed_and_bounded(self, tmp_path):
        (tmp_path / "evil.md").write_text(
            "---\nname: evil\x1b[31m-skill-" + "n" * 200 + "\n"
            'description: "ok"\n---\n\n# t\n\nbody\n',
            encoding="utf-8",
        )
        (entry,) = load_skill_catalog(tmp_path)
        assert "\x1b" not in entry.name
        assert len(entry.name) <= 80

    def test_catalog_description_scrub_keeps_cjk(self, tmp_path):
        (tmp_path / "a.md").write_text(
            '---\nname: skill-a\ndescription: "日本語の説明\x1b[31m'
            + "d" * 500
            + '"\n---\n\n# t\n\nbody\n',
            encoding="utf-8",
        )
        (entry,) = load_skill_catalog(tmp_path)
        assert "\x1b" not in entry.description
        assert "日本語の説明" in entry.description
        assert len(entry.description) <= 300

    @patch(
        "contemplative_agent.core.skill_selection._load_selection_template",
        new=lambda: PROMPT_TEMPLATE,
    )
    @patch("contemplative_agent.core.skill_selection.generate")
    def test_rejected_names_are_scrubbed_and_bounded(self, mock_generate):
        mock_generate.return_value = "幻覚-skill\x1b[31m-" + "x" * 200
        result = select_applicable_skills("sit", _catalog())
        assert result.rejected_names
        for name in result.rejected_names:
            assert "\x1b" not in name
            assert len(name) <= 80
        assert "幻覚" in result.rejected_names[0]


class TestAdapterShadowHooks:
    """Content-generation functions fire the shadow hook; post_title does not."""

    @staticmethod
    def _output(text="ok"):
        from contemplative_agent.core.llm import GenerationOutput

        return GenerationOutput(text=text)

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.shadow_observe_skill_selection")
    def test_generate_comment_observes(self, mock_shadow, mock_api):
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_comment,
        )

        mock_api.return_value = self._output()
        generate_comment("a post body")
        assert mock_shadow.call_count == 1
        assert mock_shadow.call_args.kwargs["generation_caller"] == "moltbook.comment"
        assert "a post body" in mock_shadow.call_args[0][0]

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.shadow_observe_skill_selection")
    def test_generate_reply_observes(self, mock_shadow, mock_api):
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_reply,
        )

        mock_api.return_value = self._output()
        generate_reply("the original post", "their comment")
        assert mock_shadow.call_count == 1
        assert mock_shadow.call_args.kwargs["generation_caller"] == "moltbook.reply"
        situation = mock_shadow.call_args[0][0]
        assert "the original post" in situation
        assert "their comment" in situation

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.shadow_observe_skill_selection")
    def test_generate_cooperation_post_observes(self, mock_shadow, mock_api):
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_cooperation_post,
        )

        mock_api.return_value = self._output()
        generate_cooperation_post([{"title": "t", "content": "seed content", "author": "peer"}])
        assert mock_shadow.call_count == 1
        assert mock_shadow.call_args.kwargs["generation_caller"] == "moltbook.cooperation_post"
        assert "seed content" in mock_shadow.call_args[0][0]

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.shadow_observe_skill_selection")
    def test_generate_post_title_does_not_observe(self, mock_shadow, mock_api):
        # Deliberately excluded: same pipeline run and seeds as
        # cooperation_post — a second selection adds cost, not information.
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_post_title,
        )

        mock_api.return_value = self._output(text="a title")
        generate_post_title("seed text")
        assert mock_shadow.call_count == 0


class TestSkillSelectionReading:
    def _write_log(self, log_dir: Path, date: str, records: list[dict]) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"skill-selection-{date}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    @staticmethod
    def _judged(selected, full=1000, would_be=300):
        return {
            "ts": "2026-07-10T00:00:00+00:00",
            "generation_caller": "moltbook.comment",
            "verdict": "judged",
            "selected": selected,
            "selected_count": len(selected),
            "full_skill_tokens": full,
            "would_be_skill_tokens": would_be,
        }

    def test_aggregates_frequencies_and_percentiles(self, tmp_path):
        from datetime import datetime, timezone

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "a.md", "skill-a", "does a")
        _write_skill(skills_dir, "b.md", "skill-b", "does b")
        _write_skill(skills_dir, "c.md", "skill-c", "does c")
        log_dir = tmp_path / "logs"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._write_log(
            log_dir,
            today,
            [
                self._judged(["skill-a"], full=1000, would_be=100),
                self._judged(["skill-a", "skill-b"], full=1000, would_be=300),
                {"ts": "t", "verdict": "fail_open_llm", "selected": []},
            ],
        )
        # Broken line must be skipped, not fatal.
        (log_dir / f"skill-selection-{today}.jsonl").open("a").write("{broken\n")

        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        assert reading.records == 3
        assert dict(reading.verdicts) == {"judged": 2, "fail_open_llm": 1}
        assert reading.per_skill[0] == ("skill-a", 2)
        assert ("skill-b", 1) in reading.per_skill
        assert reading.never_selected == ("skill-c",)
        assert reading.selected_count_p50 == pytest.approx(1.5)
        assert reading.token_reduction_p50 == pytest.approx(800.0)

    def test_old_files_outside_window_are_ignored(self, tmp_path):
        log_dir = tmp_path / "logs"
        self._write_log(log_dir, "2020-01-01", [self._judged(["skill-a"])])
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.records == 0

    def test_format_report_is_human_readable(self, tmp_path):
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._write_log(log_dir, today, [self._judged(["skill-a"])])
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        text = ss.format_skill_selection_report(reading)
        assert "skill-a" in text
        assert "judged" in text


class TestHallucinationRate:
    """ADR-0081 Decision 6: the report surfaces the hallucination rate —
    one of ADR-0076's four enforcement criteria, previously not aggregated."""

    def test_reading_counts_hallucinated_records(self, tmp_path):
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recs = [
            dict(TestSkillSelectionReading._judged(["skill-a"]), rejected_names=["ghost"]),
            TestSkillSelectionReading._judged(["skill-a"]),
            {"ts": "t", "verdict": "fail_open_llm", "selected": [], "rejected_names": []},
        ]
        TestSkillSelectionReading()._write_log(log_dir, today, recs)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.hallucination_records == 1

    def test_report_renders_hallucination_line(self, tmp_path):
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recs = [
            dict(TestSkillSelectionReading._judged(["skill-a"]), rejected_names=["ghost"]),
            TestSkillSelectionReading._judged(["skill-a"]),
        ]
        TestSkillSelectionReading()._write_log(log_dir, today, recs)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        text = ss.format_skill_selection_report(reading)
        assert "Hallucination" in text
        assert "1/2" in text

    def test_zero_judged_renders_without_division_error(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        text = ss.format_skill_selection_report(reading)
        assert "records" in text


class TestWindowStraddlingRegimeChange:
    """The 2026-08-08 reading's §7: a single aggregate over a window that
    straddles a regime change reads as a steady state.

    Both readings so far were misled by this — the 2026-07-24 one by a
    fail-open rate that was one incident, the 2026-08-08 one additionally by
    a hallucination rate that tripled when the catalog did. The instrument
    now carries the day-level breakdown and the enforced count that both
    readings had to reconstruct with ad-hoc scripts.
    """

    @staticmethod
    def _rec(*, verdict="judged", enforced=True, selected=(), rejected=(), catalog=()):
        return {
            "ts": "2026-08-01T00:00:00+00:00",
            "generation_caller": "moltbook.comment",
            "verdict": verdict,
            "enforced": enforced,
            "selected": list(selected),
            "selected_count": len(selected),
            "rejected_names": list(rejected),
            "catalog_names": list(catalog),
            "catalog_count": len(catalog),
            "full_skill_tokens": 1000,
            "would_be_skill_tokens": 300,
        }

    def _two_days(self, tmp_path):
        """Day 1 is pre-enforcement and quiet; day 2 is enforced and noisy."""
        from datetime import datetime, timedelta, timezone

        log_dir = tmp_path / "logs"
        writer = TestSkillSelectionReading()
        today = datetime.now(timezone.utc).date()
        day1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        day2 = today.strftime("%Y-%m-%d")
        writer._write_log(
            log_dir,
            day1,
            [
                self._rec(enforced=False, selected=["skill-a"], catalog=["skill-a", "skill-b"]),
                self._rec(verdict="fail_open_llm", enforced=False, catalog=["skill-a"]),
            ],
        )
        writer._write_log(
            log_dir,
            day2,
            [
                self._rec(selected=["skill-a"], catalog=["skill-a", "skill-b"]),
                self._rec(selected=["skill-b"], rejected=["ghost"], catalog=["skill-a", "skill-b"]),
            ],
        )
        return log_dir, day1, day2

    def test_enforced_records_are_counted(self, tmp_path):
        log_dir, _, _ = self._two_days(tmp_path)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.records == 4
        assert reading.enforced_records == 2

    def test_per_day_separates_the_two_regimes(self, tmp_path):
        log_dir, day1, day2 = self._two_days(tmp_path)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        by_date = {d.date: d for d in reading.per_day}
        assert by_date[day1].judged == 1
        assert by_date[day1].enforced == 0
        assert by_date[day1].fell_back == 1
        assert by_date[day1].hallucination_records == 0
        assert by_date[day2].judged == 2
        assert by_date[day2].enforced == 2
        assert by_date[day2].fell_back == 0
        assert by_date[day2].hallucination_records == 1
        assert by_date[day2].distinct_selected == 2

    def test_every_record_lands_in_judged_or_fell_back(self, tmp_path):
        """No silent residual. A column naming only the fail-open family
        would read as calm on a day the whole catalog went missing, so the
        fallback count is derived from records - judged instead."""
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [
                self._rec(selected=["skill-a"], catalog=["skill-a"]),
                self._rec(verdict="fail_open_llm", enforced=False),
                self._rec(verdict="empty_catalog", enforced=False),
                self._rec(verdict="no_template", enforced=False),
            ],
        )
        (day,) = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None).per_day
        assert day.records == 4
        assert day.judged == 1
        assert day.fell_back == 3
        assert day.records == day.judged + day.fell_back

    def test_per_day_is_chronological(self, tmp_path):
        log_dir, day1, day2 = self._two_days(tmp_path)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert [d.date for d in reading.per_day] == [day1, day2]

    def test_report_renders_the_day_table_and_enforced_line(self, tmp_path):
        log_dir, day1, day2 = self._two_days(tmp_path)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        text = ss.format_skill_selection_report(reading)
        assert "Enforced: 2/3 judged" in text
        assert day1 in text
        assert day2 in text

    def test_judged_empty_is_counted_and_reported(self, tmp_path):
        """ADR-0081 closed its rollout partly on judged-empty being zero, and
        a judged-empty selection injects no skill bodies at all — so it needs
        its own counter rather than living inside the log's selected_count."""
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [
                self._rec(selected=["skill-a"], catalog=["skill-a"]),
                self._rec(selected=[], catalog=["skill-a"]),
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.judged_empty_records == 1
        assert reading.per_day[0].judged_empty == 1
        assert "Judged-empty: 1/2 judged" in ss.format_skill_selection_report(reading)

    def test_exposure_distinguishes_long_offered_from_newly_adopted(self, tmp_path):
        """The property the field exists for.

        §5 of the 2026-08-08 reading: three of four never-selected skills
        turned out to be merely new, and only one had actually been offered
        and refused. The two must not produce the same number, so the fixture
        deliberately gives them very different exposure.
        """
        from datetime import datetime, timedelta, timezone

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "a.md", "skill-a", "does a")
        _write_skill(skills_dir, "old.md", "skill-old", "long offered, never chosen")
        _write_skill(skills_dir, "new.md", "skill-new", "adopted today")

        log_dir = tmp_path / "logs"
        writer = TestSkillSelectionReading()
        today = datetime.now(timezone.utc).date()
        # Four days in which only skill-old is on offer beside skill-a...
        for delta in (3, 2, 1):
            writer._write_log(
                log_dir,
                (today - timedelta(days=delta)).strftime("%Y-%m-%d"),
                [self._rec(selected=["skill-a"], catalog=["skill-a", "skill-old"])] * 2,
            )
        # ...then one day on which skill-new joins the catalog.
        writer._write_log(
            log_dir,
            today.strftime("%Y-%m-%d"),
            [self._rec(selected=["skill-a"], catalog=["skill-a", "skill-old", "skill-new"])],
        )

        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        exposure = dict(reading.never_selected_exposure)
        assert set(exposure) == {"skill-old", "skill-new"}
        assert exposure["skill-old"] == 7
        assert exposure["skill-new"] == 1
        text = ss.format_skill_selection_report(reading)
        assert "skill-old: offered in 7 of 7 judged records, chosen 0" in text
        assert "skill-new: offered in 1 of 7 judged records, chosen 0" in text

    def test_exposure_counts_only_judged_records(self, tmp_path):
        """A name offered to a selector that never answered was not refused.

        Counting exposure over all records reproduced the misreading the
        instrument exists to prevent: during the 2026-07-12 breaker-open
        incident every record was fail_open_llm, and a never-selected skill
        rendered as 'in catalog for 100 of 105 records' — a retirement signal
        drawn from a window with no judgments in it at all.
        """
        from datetime import datetime, timezone

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "x.md", "skill-x", "never judged")
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [self._rec(verdict="fail_open_llm", enforced=False, catalog=["skill-x"])] * 100,
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        assert reading.judged_records == 0
        assert dict(reading.never_selected_exposure) == {"skill-x": 0}
        text = ss.format_skill_selection_report(reading)
        assert "no judged records in window" in text
        assert "of 100 records" not in text

    def test_zero_exposure_reads_as_new_or_renamed_not_as_refused(self, tmp_path):
        """The frontmatter-name backfill will rename skills mid-window, and a
        renamed skill's new name has no history. That must not render the
        same as a skill that was offered and passed over."""
        from datetime import datetime, timezone

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "z.md", "skill-z", "renamed since these records")
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [self._rec(selected=["skill-a"], catalog=["skill-a"])],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        assert dict(reading.never_selected_exposure) == {"skill-z": 0}
        text = ss.format_skill_selection_report(reading)
        assert "never in catalog for any of 1 judged records" in text
        assert "renamed since" in text

    def test_records_without_catalog_names_do_not_crash_exposure(self, tmp_path):
        """Pre-ADR-0081 records predate ``catalog_names``; absent is zero, not
        a KeyError."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "z.md", "skill-z", "never chosen")
        log_dir = tmp_path / "logs"
        from datetime import datetime, timezone

        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [TestSkillSelectionReading._judged(["skill-a"])],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        assert dict(reading.never_selected_exposure) == {"skill-z": 0}

    def test_malformed_catalog_names_are_skipped_not_fatal(self, tmp_path):
        """Fault column: the instrument must not break its subject. A record
        whose catalog_names is the wrong shape degrades to no exposure."""
        from datetime import datetime, timezone

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "z.md", "skill-z", "never chosen")
        log_dir = tmp_path / "logs"
        good = self._rec(selected=["skill-a"], catalog=["skill-a", "skill-z"])
        bad_scalar = dict(good, catalog_names=5)
        bad_nested = dict(good, catalog_names=[{"a": 1}, "skill-z"])
        TestSkillSelectionReading()._write_log(
            log_dir,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            [good, bad_scalar, bad_nested],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        # The good record and the string inside the nested one both count;
        # neither malformed shape raises.
        assert dict(reading.never_selected_exposure) == {"skill-z": 2}

    def test_window_totals_agree_with_the_day_rows(self, tmp_path):
        """The two levels are accumulated in the same loop by hand, so the
        invariant tying them together is worth pinning rather than trusting
        to construction."""
        log_dir, _, _ = self._two_days(tmp_path)
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert sum(d.records for d in reading.per_day) == reading.records
        assert sum(d.judged for d in reading.per_day) == reading.judged_records
        assert sum(d.enforced for d in reading.per_day) == reading.enforced_records
        assert sum(d.judged_empty for d in reading.per_day) == reading.judged_empty_records
        assert (
            sum(d.hallucination_records for d in reading.per_day) == reading.hallucination_records
        )

    def test_empty_log_renders_without_error(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.per_day == ()
        assert reading.enforced_records == 0
        assert "records" in ss.format_skill_selection_report(reading)


class TestEnforcement:
    """ADR-0081: two-pass injection enforcement, unconditional since the
    2026-08-08 reading closed the rollout (15 days at 1,316/1,316 enforced,
    zero fail-open, zero judged-empty, zero hallucination propagation)."""

    def _configure(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        _write_skill(skills_dir, "a.md", "skill-a", "does a")
        _write_skill(skills_dir, "b.md", "skill-b", "does b")
        audit_dir = tmp_path / "logs"
        ss.configure_skill_selection(skills_dir=skills_dir, audit_dir=audit_dir)
        monkeypatch.setattr(ss, "_load_selection_template", lambda: PROMPT_TEMPLATE)
        return skills_dir, audit_dir

    @staticmethod
    def _records(audit_dir: Path) -> list[dict]:
        files = sorted(audit_dir.glob("skill-selection-*.jsonl"))
        assert files
        return [
            json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines()
        ]

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_judged_selection_enforces_without_any_flag(self, mock_generate, tmp_path, monkeypatch):
        self._configure(tmp_path, monkeypatch)
        monkeypatch.delenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", raising=False)
        mock_generate.return_value = "skill-a"
        result = ss.shadow_observe_skill_selection("s", generation_caller="moltbook.comment")
        assert result == ("skill-a",)
        (rec,) = self._records(tmp_path / "logs")
        assert rec["enforced"] is True

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_retired_flag_set_to_zero_does_not_turn_enforcement_off(
        self, mock_generate, tmp_path, monkeypatch
    ):
        """The flag is retired, not inverted. A stale launchd plist or shell
        still exporting the name must not be read as an off switch — the one
        that exists is ``audit_dir``."""
        self._configure(tmp_path, monkeypatch)
        monkeypatch.setenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", "0")
        mock_generate.return_value = "skill-a"
        assert ss.shadow_observe_skill_selection("s", generation_caller="moltbook.comment") == (
            "skill-a",
        )

    def test_enforcement_flag_helper_is_gone(self):
        assert not hasattr(ss, "enforcement_enabled")

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_llm_failure_fails_open_to_full_injection(self, mock_generate, tmp_path, monkeypatch):
        """Fault column (chaos-TDD): selector failure under enforcement must
        fall back to full injection (None), never an empty injection.

        Since 2026-08-08 that fallback no longer fits NUM_CTX at the live
        corpus size, so the call is skipped by the audit-C2 budget guard
        rather than degraded — see ADR-0081's staleness marker. This test
        pins the selector's half of the contract (None, not ()); what the
        generation layer then does with None is that layer's contract."""
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = None
        result = ss.shadow_observe_skill_selection("s", generation_caller="moltbook.reply")
        assert result is None
        (rec,) = self._records(tmp_path / "logs")
        assert rec["verdict"] == "fail_open_llm"
        assert rec["enforced"] is False

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_judged_empty_returns_empty_tuple(self, mock_generate, tmp_path, monkeypatch):
        """An empty judged selection is a decision (inject nothing), not a
        failure (ADR-0081 Decision 3)."""
        self._configure(tmp_path, monkeypatch)
        mock_generate.return_value = "none"
        result = ss.shadow_observe_skill_selection("s", generation_caller="moltbook.comment")
        assert result == ()
        (rec,) = self._records(tmp_path / "logs")
        assert rec["enforced"] is True

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_unconfigured_audit_dir_is_full_injection(self, mock_generate, tmp_path, monkeypatch):
        """The surviving kill switch: audit_dir unset disables the selector
        entirely, which under ADR-0081 means full injection."""
        assert ss.shadow_observe_skill_selection("s", generation_caller="x") is None
        assert mock_generate.call_count == 0


class TestSelectedSkillsBlock:
    def test_returns_only_selected_bodies_frontmatter_stripped(self, tmp_path):
        _write_skill(tmp_path, "a.md", "skill-a", "does a")
        _write_skill(tmp_path, "b.md", "skill-b", "does b")
        ss.configure_skill_selection(skills_dir=tmp_path, audit_dir=tmp_path / "logs")
        block = ss.selected_skills_block(("skill-a",))
        assert "body of skill-a" in block
        assert "body of skill-b" not in block
        assert "---" not in block  # frontmatter stripped

    def test_unknown_name_ignored_with_warning(self, tmp_path, caplog):
        _write_skill(tmp_path, "a.md", "skill-a", "does a")
        ss.configure_skill_selection(skills_dir=tmp_path, audit_dir=tmp_path / "logs")
        with caplog.at_level(logging.WARNING):
            block = ss.selected_skills_block(("skill-a", "ghost-skill"))
        assert "body of skill-a" in block
        assert "ghost-skill" in caplog.text

    def test_empty_selection_returns_empty_string(self, tmp_path):
        _write_skill(tmp_path, "a.md", "skill-a", "does a")
        ss.configure_skill_selection(skills_dir=tmp_path, audit_dir=tmp_path / "logs")
        assert ss.selected_skills_block(()) == ""


class TestEnforcementWiring:
    """ADR-0081: when the selector returns a judged selection, the publish
    paths generate under a selection-filtered system prompt; None keeps the
    default (full) system prompt."""

    @staticmethod
    def _output(text: str = "generated"):
        from contemplative_agent.core.llm import GenerationOutput

        return GenerationOutput(text=text)

    def _patches(self):
        return (
            patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api"),
            patch(
                "contemplative_agent.adapters.moltbook.llm_functions.shadow_observe_skill_selection"
            ),
            patch(
                "contemplative_agent.adapters.moltbook.llm_functions.selected_skills_block",
                return_value="SEL_BLOCK",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.llm_functions.build_system_prompt_with_skills",
                return_value="SYS_SEL",
            ),
        )

    def test_comment_enforced_uses_selected_system(self):
        from contemplative_agent.adapters.moltbook.llm_functions import generate_comment

        p_api, p_shadow, p_block, p_build = self._patches()
        with p_api as mock_api, p_shadow as mock_shadow, p_block as mock_block, p_build:
            mock_api.return_value = self._output()
            mock_shadow.return_value = ("skill-a",)
            generate_comment("a post")
            assert mock_api.call_args.kwargs["system"] == "SYS_SEL"
            assert mock_block.call_args.args[0] == ("skill-a",)

    def test_comment_shadow_keeps_full_system(self):
        from contemplative_agent.adapters.moltbook.llm_functions import generate_comment

        p_api, p_shadow, p_block, p_build = self._patches()
        with p_api as mock_api, p_shadow as mock_shadow, p_block, p_build:
            mock_api.return_value = self._output()
            mock_shadow.return_value = None
            generate_comment("a post")
            assert mock_api.call_args.kwargs.get("system") is None

    def test_reply_enforced_uses_selected_system(self):
        from contemplative_agent.adapters.moltbook.llm_functions import generate_reply

        p_api, p_shadow, p_block, p_build = self._patches()
        with p_api as mock_api, p_shadow as mock_shadow, p_block, p_build:
            mock_api.return_value = self._output()
            mock_shadow.return_value = ("skill-b",)
            generate_reply("post", "comment")
            assert mock_api.call_args.kwargs["system"] == "SYS_SEL"

    def test_post_title_reuses_cooperation_selection(self):
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_cooperation_post,
            generate_post_title,
        )

        p_api, p_shadow, p_block, p_build = self._patches()
        with p_api as mock_api, p_shadow as mock_shadow, p_block, p_build:
            mock_api.return_value = self._output(text="a title")
            mock_shadow.return_value = ("skill-a",)
            generate_cooperation_post([{"title": "t", "content": "seed"}])
            generate_post_title("seed")
            # post_title runs no second selection but generates under the
            # same selection-filtered system prompt (ADR-0081 Decision 2).
            assert mock_shadow.call_count == 1
            assert mock_api.call_args.kwargs["system"] == "SYS_SEL"

    def test_post_title_full_when_cooperation_was_shadow(self):
        from contemplative_agent.adapters.moltbook.llm_functions import (
            generate_cooperation_post,
            generate_post_title,
        )

        p_api, p_shadow, p_block, p_build = self._patches()
        with p_api as mock_api, p_shadow as mock_shadow, p_block, p_build:
            mock_api.return_value = self._output(text="a title")
            mock_shadow.return_value = None
            generate_cooperation_post([{"title": "t", "content": "seed"}])
            generate_post_title("seed")
            assert mock_api.call_args.kwargs.get("system") is None
