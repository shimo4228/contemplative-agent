"""Tests for the skill-selection shadow instrument (ADR-0076)."""

from __future__ import annotations

import base64
import datetime as dt
import difflib
import json
import logging
from pathlib import Path
from typing import Any
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


class TestRejectedNameTally:
    """The 2026-08-08 backfill reading: the hallucination *rate* mixes three
    mechanisms (wordform variance / semantic substitution / value-layer
    bleed), and separating them needs the names themselves, not a count of
    records that had any. The instrument reports name, count and nearest
    catalog match; it does not classify — that is the reader's judgment
    (``read-only-instruments``: an instrument must not become the
    intervention).
    """

    @staticmethod
    def _rejected(names, selected=("skill-a",)):
        return dict(TestSkillSelectionReading._judged(list(selected)), rejected_names=list(names))

    def _catalog_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "a.md", "skill-alpha", "does alpha")
        _write_skill(skills_dir, "z.md", "unrelated-thing", "does z")
        return skills_dir

    def _today(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def test_tallies_names_with_counts_and_nearest_catalog_match(self, tmp_path):
        skills_dir = self._catalog_dir(tmp_path)
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            self._today(),
            [
                self._rejected(["skill-alphas"]),
                self._rejected(["skill-alphas", "totally-different-xyz"]),
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)

        tally = reading.rejected_name_tally
        assert [t.name for t in tally] == ["skill-alphas", "totally-different-xyz"]
        assert tally[0].count == 2
        # The wordform case: one character from a real catalog name.
        assert tally[0].nearest == "skill-alpha"
        assert tally[0].similarity > 0.9
        # The unrelated case: nearest still resolves, but far away. The
        # instrument reports the distance rather than calling it "fabricated".
        assert tally[1].count == 1
        assert tally[1].similarity < 0.6

    def test_counted_over_judged_records_only(self, tmp_path):
        """Same discipline as every other rate in this reading: a selector
        that never answered did not hallucinate."""
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            self._today(),
            [
                self._rejected(["ghost-name"]),
                {
                    "ts": "t",
                    "verdict": "fail_open_parse",
                    "selected": [],
                    "rejected_names": ["should-not-count"],
                },
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert [t.name for t in reading.rejected_name_tally] == ["ghost-name"]

    def test_nearest_is_absent_when_no_catalog_is_available(self, tmp_path):
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["ghost-name"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        entry = reading.rejected_name_tally[0]
        assert entry.nearest == ""
        assert entry.similarity == 0.0
        assert reading.catalog_available is False

    def test_no_ruler_is_not_reported_as_nothing_resembles_it(self, tmp_path):
        """Both cases leave ``similarity`` at 0.0, and the first render of
        this tally collapsed them — so an unreadable ``skills_dir`` would
        have printed the value-layer-bleed signature. That is the worst
        misreading this tally can produce: a broken instrument looking
        like a finding (cross-model review, 2026-08-08)."""
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["ghost-name"])]
        )

        no_catalog = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        text = ss.format_skill_selection_report(no_catalog, include_rejected_names=True)
        assert "no catalog to compare against" in text
        assert "no catalog name resembles it" not in text

        with_catalog = ss.read_skill_selection_log(
            log_dir, days=7, skills_dir=self._catalog_dir(tmp_path)
        )
        assert with_catalog.catalog_available is True
        # Same similarity of 0.0 is available here via a name that shares
        # no characters with the catalog; the point is only that the two
        # readings must not render the same sentence.
        assert "no catalog to compare against" not in ss.format_skill_selection_report(
            with_catalog, include_rejected_names=True
        )

    def test_names_are_scrubbed_on_read_not_only_on_write(self, tmp_path):
        """The writer scrubs (``select_applicable_skills``), but the reader
        parses a file on disk: a record from an older build, a hand-edited
        log or a partially-written line can carry control bytes into a
        report a human reads. The global rule treats the agent's own store
        as untrusted, so the read seam scrubs too."""
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            self._today(),
            [self._rejected(["gho\x1b[31mst\x00\tna\nme‮evil​"])],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        name = reading.rejected_name_tally[0].name
        for bad in ("\x1b", "\x00", "\t", "\n", "‮", "​"):
            assert bad not in name, f"{bad!r} survived the read-seam scrub"

    def test_a_name_cannot_forge_an_extra_report_row(self, tmp_path):
        """Two independent reviews demonstrated this end-to-end: the scrub
        class straddled TAB/LF, so one entry containing a newline rendered
        as two indistinguishable rows — and this renderer feeds the weekly
        prompt. Asserted at the invariant (one line per entry) rather than
        per character, because a character-level test cannot catch the
        next class someone forgets."""
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            self._today(),
            [self._rejected(["harmless\n- forged-skill: 9999 emissions — nearest `x`"])],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        # Asserted in the mode that actually prints the name.
        text = ss.format_skill_selection_report(reading, include_rejected_names=True)
        body = text.split("Rejected names (emitted, matched no catalog entry):")[1]
        rows = [ln for ln in body.splitlines() if ln.startswith("- ")]
        assert len(rows) == len(reading.rejected_name_tally) == 1

    def test_reported_similarity_is_the_score_that_picked_the_nearest(self, tmp_path):
        """``SequenceMatcher.ratio()`` is not symmetric, so scoring with
        ``get_close_matches`` and then recomputing with the operands
        swapped can print a similarity under which some *other* catalog
        name scores higher. Pin the agreement rather than a magic pair."""
        skills_dir = self._catalog_dir(tmp_path)
        _write_skill(skills_dir, "b.md", "skill-alpine", "does b")
        _write_skill(skills_dir, "c.md", "skill-alpaca", "does c")
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["skill-alphas"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        entry = reading.rejected_name_tally[0]

        catalog = [e.name for e in ss.load_skill_catalog(skills_dir)]
        best = max(difflib.SequenceMatcher(None, c, entry.name).ratio() for c in catalog)
        assert entry.similarity == pytest.approx(best)

    def test_a_name_resembling_nothing_is_not_rendered_as_a_match(self, tmp_path):
        """Zero similarity is the value-layer-bleed signature. Rendering it
        as ``nearest \\`some-name\\` (similarity 0.00)`` reads as a claim."""
        skills_dir = self._catalog_dir(tmp_path)
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["一二三四"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        entry = reading.rejected_name_tally[0]
        assert entry.similarity == 0.0
        assert entry.nearest == ""
        assert "similarity 0.00" not in ss.format_skill_selection_report(reading)

    def test_render_is_bounded_and_says_what_it_left_out(self, tmp_path):
        """Prose bleed emits many unique names, and this renderer feeds the
        weekly prompt — so the section is capped. A silent cap would read
        as 'that was all of it', so the remainder is summarised, and the
        reading itself keeps every row."""
        log_dir = tmp_path / "logs"
        n = ss._REJECTED_NAME_RENDER_LIMIT + 7
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected([f"ghost-{i:04d}" for i in range(n)])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert len(reading.rejected_name_tally) == n

        text = ss.format_skill_selection_report(reading)
        body = text.split("Rejected names (emitted, matched no catalog entry):")[1]
        rows = [ln for ln in body.splitlines() if ln.startswith("- ")]
        assert len(rows) == ss._REJECTED_NAME_RENDER_LIMIT + 1
        assert "and 7 more distinct names (7 emissions), not shown" in text

    def test_malformed_entries_are_skipped_not_fatal(self, tmp_path):
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir,
            self._today(),
            [
                self._rejected(["good-name"]),
                dict(TestSkillSelectionReading._judged(["skill-a"]), rejected_names=[42, None]),
                dict(
                    TestSkillSelectionReading._judged(["skill-a"]),
                    rejected_names="not-a-list",
                ),
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert [t.name for t in reading.rejected_name_tally] == ["good-name"]
        # A record whose rejected_names is unusable still counted as a
        # hallucination record if it was truthy — the two are different
        # questions and must not be silently merged.
        assert reading.hallucination_records == 3

    def test_report_renders_the_tally_when_names_are_requested(self, tmp_path):
        skills_dir = self._catalog_dir(tmp_path)
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["skill-alphas"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        text = ss.format_skill_selection_report(reading, include_rejected_names=True)
        assert "skill-alphas" in text
        assert "skill-alpha" in text

    def test_names_are_withheld_by_default_but_the_shape_is_not(self, tmp_path):
        """A rejected name is free text from a model whose prompt embeds
        untrusted post bodies, so the default render omits it. Everything
        that is *not* attacker-influenceable — how many distinct names, how
        many emissions, which real skill each sits near and how far — still
        renders, because the nearest name comes from the catalog."""
        skills_dir = self._catalog_dir(tmp_path)
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [self._rejected(["ATTACKER-TEXT-alphas"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        text = ss.format_skill_selection_report(reading)

        assert "ATTACKER-TEXT" not in text
        # The shape survives: nearest catalog name, distance, emissions.
        assert "skill-alpha" in text
        assert "1 emissions" in text
        assert "similarity" in text

    def test_report_omits_the_section_when_nothing_was_rejected(self, tmp_path):
        log_dir = tmp_path / "logs"
        TestSkillSelectionReading()._write_log(
            log_dir, self._today(), [TestSkillSelectionReading._judged(["skill-a"])]
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.rejected_name_tally == ()
        assert "Rejected names" not in ss.format_skill_selection_report(reading)


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


class TestSkillSelectionWindowAndMechanisms:
    """T-SKILLSEL-REPORT-WINDOW (2026-08-22): three instrument extensions the
    third reading needed six ad-hoc scripts for — an explicit UTC calendar
    window, the hallucination rate conditioned on ``catalog_count`` with a
    corpus-token axis, and the three-mechanism split of rejected names.
    All read-only (ADR-0071 / ADR-0076); the selector is untouched."""

    @staticmethod
    def _rec(
        selected=("skill-a",), *, catalog_count: Any = 45, tokens: Any = 1000, rejected=(), **extra
    ):
        # ``Any``: fault rows deliberately pass the wrong type.
        rec = dict(
            TestSkillSelectionReading._judged(list(selected), full=tokens, would_be=100),
            catalog_count=catalog_count,
            rejected_names=list(rejected),
            catalog_names=["identifying-structural-tensions", "trace-dependency-failures"],
        )
        rec.update(extra)
        return rec

    def _write(self, log_dir, date, records):
        TestSkillSelectionReading()._write_log(log_dir, date, records)

    def _catalog_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(
            skills_dir,
            "a.md",
            "identifying-structural-tensions",
            "identify tensions via system metaphors",
        )
        _write_skill(skills_dir, "b.md", "trace-dependency-failures", "trace failures")
        return skills_dir

    def _value_layer(self, tmp_path):
        constitution = tmp_path / "constitution"
        constitution.mkdir()
        (constitution / "axioms.md").write_text(
            "Mindfulness: monitor your interpretative process continuously.\n",
            encoding="utf-8",
        )
        identity = tmp_path / "identity.md"
        identity.write_text("I am a contemplative agent.\n", encoding="utf-8")
        return (constitution, identity)

    # --- window ---------------------------------------------------------

    def test_since_until_selects_utc_calendar_days_inclusive(self, tmp_path):
        from datetime import date

        log_dir = tmp_path / "logs"
        for day in ("2026-08-08", "2026-08-09", "2026-08-22", "2026-08-23"):
            self._write(log_dir, day, [self._rec(extra_day=day)])
        reading = ss.read_skill_selection_log(
            log_dir,
            since=date(2026, 8, 9),
            until=date(2026, 8, 22),
            skills_dir=None,
        )
        assert reading.records == 2
        assert [d.date for d in reading.per_day] == ["2026-08-09", "2026-08-22"]
        assert reading.days == 14
        assert reading.window_since == "2026-08-09"
        assert reading.window_until == "2026-08-22"
        text = ss.format_skill_selection_report(reading)
        assert "2026-08-09" in text and "2026-08-22" in text
        assert "last 14 days" not in text

    def test_days_mode_is_unchanged_and_reports_no_bounds(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec()])
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.records == 1
        assert reading.days == 7
        assert reading.window_since is None and reading.window_until is None
        assert "last 7 days" in ss.format_skill_selection_report(reading)

    def test_window_arguments_are_exclusive_and_ordered(self, tmp_path):
        from datetime import date

        log_dir = tmp_path / "logs"
        with pytest.raises(ValueError, match="days"):
            ss.read_skill_selection_log(log_dir, days=7, since=date(2026, 8, 9), skills_dir=None)
        with pytest.raises(ValueError, match="since"):
            ss.read_skill_selection_log(log_dir, until=date(2026, 8, 9), skills_dir=None)
        with pytest.raises(ValueError, match="since"):
            ss.read_skill_selection_log(
                log_dir, since=date(2026, 8, 10), until=date(2026, 8, 9), skills_dir=None
            )
        with pytest.raises(ValueError, match="days"):
            ss.read_skill_selection_log(log_dir, skills_dir=None)

    def test_since_alone_runs_through_today(self, tmp_path):
        from datetime import date, datetime, timezone

        log_dir = tmp_path / "logs"
        today = datetime.now(timezone.utc).date()
        self._write(log_dir, today.isoformat(), [self._rec()])
        self._write(log_dir, "2026-01-01", [self._rec()])
        reading = ss.read_skill_selection_log(log_dir, since=date(2026, 1, 2), skills_dir=None)
        assert reading.records == 1
        assert reading.window_until == today.isoformat()

    def test_empty_window_abstains_cleanly(self, tmp_path):
        from datetime import date

        reading = ss.read_skill_selection_log(
            tmp_path / "logs", since=date(2026, 8, 9), until=date(2026, 8, 22), skills_dir=None
        )
        assert reading.records == 0
        assert reading.catalog_regimes == ()
        assert reading.mechanism_tally == ()
        text = ss.format_skill_selection_report(reading)
        assert "0 records" in text

    # --- catalog_count conditioning ---------------------------------------

    def test_catalog_regimes_condition_rate_and_token_median(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(
            log_dir,
            today,
            [
                self._rec(catalog_count=45, tokens=100),
                self._rec(catalog_count=45, tokens=200, rejected=["ghost-a"]),
                self._rec(catalog_count=45, tokens=300),
                self._rec(catalog_count=48, tokens=50),
                self._rec(catalog_count=48, tokens=70, rejected=["ghost-a", "ghost-b"]),
                {"ts": "t", "verdict": "fail_open_llm", "selected": [], "catalog_count": 45},
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        regimes = {r.catalog_count: r for r in reading.catalog_regimes}
        assert [r.catalog_count for r in reading.catalog_regimes] == [45, 48]
        assert (regimes[45].judged, regimes[45].hallucination_records) == (3, 1)
        assert regimes[45].full_skill_tokens_median == pytest.approx(200.0)
        assert (regimes[48].judged, regimes[48].hallucination_records) == (2, 1)
        assert regimes[48].full_skill_tokens_median == pytest.approx(60.0)
        assert reading.catalog_count_missing == 0
        text = ss.format_skill_selection_report(reading)
        assert "33.3%" in text and "50.0%" in text
        assert "200" in text and "60" in text

    def test_catalog_count_missing_is_abstained_not_bucketed(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        no_count = self._rec()
        del no_count["catalog_count"]
        self._write(
            log_dir,
            today,
            [no_count, self._rec(catalog_count="45"), self._rec(catalog_count=45)],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert [r.catalog_count for r in reading.catalog_regimes] == [45]
        assert reading.catalog_regimes[0].judged == 1
        assert reading.catalog_count_missing == 2
        text = ss.format_skill_selection_report(reading)
        assert "catalog_count_missing" in text and "2" in text

    def test_full_skill_tokens_missing_is_counted_not_imputed(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        no_tok = self._rec(catalog_count=45)
        del no_tok["full_skill_tokens"]
        self._write(
            log_dir,
            today,
            [
                no_tok,
                self._rec(catalog_count=45, tokens=300),
                self._rec(catalog_count=45, tokens="x"),
            ],
        )
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        regime = reading.catalog_regimes[0]
        assert regime.judged == 3
        assert regime.full_skill_tokens_median == pytest.approx(300.0)
        assert regime.tokens_missing == 2
        all_missing = tmp_path / "logs2"
        self._write(all_missing, today, [dict(no_tok)])
        regime = ss.read_skill_selection_log(all_missing, days=7, skills_dir=None).catalog_regimes[
            0
        ]
        assert regime.full_skill_tokens_median is None
        text = ss.format_skill_selection_report(
            ss.read_skill_selection_log(all_missing, days=7, skills_dir=None)
        )
        assert "full_skill_tokens_missing" in text

    # --- mechanism split --------------------------------------------------

    def test_rejected_names_are_split_by_mechanism(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(
            log_dir,
            today,
            [
                self._rec(rejected=["identify-structural-tensions"]),
                self._rec(
                    rejected=["identify-structural-tensions", "translate-dependency-failures"]
                ),
                self._rec(rejected=["interpretative-audit"]),
                self._rec(rejected=["suspending interpretation upon premise doubt"]),
            ],
        )
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=self._value_layer(tmp_path),
        )
        by_name = {t.name: t for t in reading.rejected_name_tally}
        assert by_name["identify-structural-tensions"].mechanism == "wordform"
        assert by_name["identify-structural-tensions"].similarity >= ss.WORDFORM_SIMILARITY_FLOOR
        assert by_name["translate-dependency-failures"].mechanism == "semantic"
        assert by_name["interpretative-audit"].mechanism == "value_layer"
        assert by_name["suspending interpretation upon premise doubt"].mechanism == "value_layer"
        assert reading.value_layer_reason is None
        tally = {m.mechanism: (m.emissions, m.distinct) for m in reading.mechanism_tally}
        assert tally == {"wordform": (2, 1), "semantic": (1, 1), "value_layer": (2, 2)}
        text = ss.format_skill_selection_report(reading)
        assert "wordform" in text and "semantic" in text and "value_layer" in text
        assert "40.0%" in text  # wordform 2 of 5 emissions

    def test_catalog_description_words_are_catalog_vocabulary(self, tmp_path):
        """The pass-1 prompt shows (name, description) pairs, so a token that
        appears only in a description is catalog-derived, not value-layer
        bleed — even when the value layer also contains it."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        constitution, identity = self._value_layer(tmp_path)
        (constitution / "more.md").write_text("use metaphors wisely\n", encoding="utf-8")
        self._write(log_dir, today, [self._rec(rejected=["metaphors-of-failures"])])
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=(constitution, identity),
        )
        assert reading.rejected_name_tally[0].mechanism == "semantic"

    def test_value_layer_unavailable_abstains_with_reason_code(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(
            log_dir,
            today,
            [self._rec(rejected=["identify-structural-tensions", "interpretative-audit"])],
        )
        skills_dir = self._catalog_dir(tmp_path)
        not_configured = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        assert not_configured.value_layer_reason == "value_layer_not_configured"
        by_name = {t.name: t for t in not_configured.rejected_name_tally}
        # Rule 3 needs no value layer: still decidable.
        assert by_name["identify-structural-tensions"].mechanism == "wordform"
        # Rule 2 would need it: abstain, do not fall through to "semantic".
        assert by_name["interpretative-audit"].mechanism == "unclassified"
        assert by_name["interpretative-audit"].mechanism_reason == "value_layer_unavailable"
        tally = {m.mechanism: m.emissions for m in not_configured.mechanism_tally}
        assert tally == {"wordform": 1, "unclassified": 1}
        text = ss.format_skill_selection_report(not_configured)
        assert "value_layer_not_configured" in text

        unreadable = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=skills_dir,
            value_layer_paths=(tmp_path / "nope", tmp_path / "nope.md"),
        )
        assert unreadable.value_layer_reason == "value_layer_unreadable"
        assert "value_layer_unreadable" in ss.format_skill_selection_report(unreadable)

    def test_no_catalog_leaves_every_name_unclassified(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["identify-structural-tensions"])])
        reading = ss.read_skill_selection_log(
            log_dir, days=7, skills_dir=None, value_layer_paths=self._value_layer(tmp_path)
        )
        entry = reading.rejected_name_tally[0]
        assert entry.mechanism == "unclassified"
        assert entry.mechanism_reason == "catalog_unavailable"
        assert "catalog_unavailable" in ss.format_skill_selection_report(reading)

    def test_prose_names_are_value_layer_even_when_value_layer_is_absent(self, tmp_path):
        """Rule 1 (whitespace / slash = prose, not a slug) needs neither
        ruler nor value layer, so it must not be abstained with them."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["a prose clause here"])])
        reading = ss.read_skill_selection_log(log_dir, days=7, skills_dir=None)
        assert reading.rejected_name_tally[0].mechanism == "value_layer"

    # --- trust boundary ---------------------------------------------------

    def test_default_renderer_still_withholds_names_in_new_sections(self, tmp_path):
        """``weekly-analysis.sh`` takes the default; the new sections must
        not become a second channel for model-emitted strings."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        names = ["identify-structural-tensions", "zqxv-audit", "zqxv prose leak"]
        self._write(log_dir, today, [self._rec(rejected=names)])
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=self._value_layer(tmp_path),
        )
        default = ss.format_skill_selection_report(reading)
        for name in names:
            assert name not in default
        assert "zqxv" not in default
        assert "Hallucination by mechanism" in default
        human = ss.format_skill_selection_report(reading, include_rejected_names=True)
        for name in names:
            assert name in human


class TestSkillSelectionMechanismFaults(TestSkillSelectionWindowAndMechanisms):
    """Fault rows for the mechanism split's inputs (silent-failure review,
    2026-08-22). Every one of these must abstain with a reason code that
    reaches the report — never a wrong bucket, never a lost section."""

    def test_undecodable_value_layer_file_abstains_not_crashes(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["interpretative-audit"])])
        identity = tmp_path / "identity.md"
        identity.write_bytes(b"\xff\xfe not utf-8 \x80\x81")
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=(identity,),
        )
        assert reading.value_layer_reason == "value_layer_unreadable"
        assert reading.rejected_name_tally[0].mechanism == "unclassified"
        assert "value_layer_unreadable" in ss.format_skill_selection_report(reading)

    def test_partly_read_value_layer_names_what_was_missing(self, tmp_path):
        """A constitution that reads plus an identity file that does not is
        *not* "value layer available": rule 2 would then measure against half
        the vocabulary and call an identity-only token `semantic`."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["interpretative-audit"])])
        constitution, identity = self._value_layer(tmp_path)
        identity.unlink()
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=(constitution, identity),
        )
        assert reading.value_layer_files == 1
        assert reading.value_layer_missing == ("identity.md",)
        text = ss.format_skill_selection_report(reading)
        assert "identity.md" in text
        # Still classified — the part that was read is a real ruler — but the
        # gap is named rather than hidden behind a file count.
        assert reading.rejected_name_tally[0].mechanism == "value_layer"

    def test_mechanism_section_names_the_missing_catalog(self, tmp_path):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["ghost-name"])])
        reading = ss.read_skill_selection_log(
            log_dir, days=7, skills_dir=None, value_layer_paths=self._value_layer(tmp_path)
        )
        section = ss.format_skill_selection_report(reading).split("Hallucination by mechanism")[1]
        assert "catalog_unavailable" in section

    def test_short_foreign_tokens_are_not_claimed_to_be_checked(self, tmp_path):
        """The value-layer vocabulary drops tokens under
        ``_VALUE_LAYER_TOKEN_MIN_CHARS``, so a 3-char foreign token can never
        match it. Testing it anyway would print "not in value layer" about a
        word that was never looked up."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        constitution, identity = self._value_layer(tmp_path)
        (constitution / "short.md").write_text("ego and its metaphors\n", encoding="utf-8")
        self._write(log_dir, today, [self._rec(rejected=["ego-tensions"])])
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=(constitution, identity),
        )
        entry = reading.rejected_name_tally[0]
        assert entry.mechanism == "semantic"
        assert "ego" not in entry.mechanism_note

    def test_unreadable_value_layer_root_is_logged_not_silent(self, tmp_path, caplog):
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["ghost-name"])])
        with caplog.at_level(logging.WARNING):
            reading = ss.read_skill_selection_log(
                log_dir,
                days=7,
                skills_dir=None,
                value_layer_paths=(tmp_path / "absent-dir",),
            )
        assert reading.value_layer_reason == "value_layer_unreadable"
        assert reading.value_layer_missing == ("absent-dir",)


class TestSkillSelectionReviewFixes(TestSkillSelectionWindowAndMechanisms):
    """Code-review findings, 2026-08-22: the value layer is optional for the
    consumer that matters most (the weekly packet), the constitution can be
    overridden by a CLI flag, and a directory can be read only in part."""

    def test_wordform_is_decided_without_a_value_layer(self, tmp_path):
        """Rule 3 needs no value layer. Abstaining before checking it made
        the weekly packet (which passes no value-layer paths) print
        `unclassified` for the same record `report --skill-selection` calls
        `wordform` — two renderers disagreeing about one log line."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(
            log_dir,
            today,
            [
                # A misspelling is a token outside the catalog vocabulary, so
                # rule 2 fires first — but the name sits at ~0.97 of a real
                # catalog entry, which rule 3 can settle on its own.
                self._rec(rejected=["identifing-structural-tensions"]),
                self._rec(rejected=["wholly-unrelated-invention"]),
            ],
        )
        skills_dir = self._catalog_dir(tmp_path)
        without = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        by_name = {t.name: t for t in without.rejected_name_tally}
        assert by_name["identifing-structural-tensions"].mechanism == "wordform"
        # Far from every catalog name: value_layer vs semantic genuinely
        # needs the value layer, so this one still abstains.
        assert by_name["wholly-unrelated-invention"].mechanism == "unclassified"
        assert by_name["wholly-unrelated-invention"].mechanism_reason == "value_layer_unavailable"
        with_layer = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=skills_dir,
            value_layer_paths=self._value_layer(tmp_path),
        )
        assert {t.name: t.mechanism for t in with_layer.rejected_name_tally}[
            "identifing-structural-tensions"
        ] == "wordform"

    def test_partly_read_directory_is_named_as_partial(self, tmp_path):
        """``read_markdown_documents`` skips unreadable and empty-bodied
        files internally, so "files > 0" is not "the value layer was read"."""
        log_dir = tmp_path / "logs"
        today = TestRejectedNameTally()._today()
        self._write(log_dir, today, [self._rec(rejected=["interpretative-audit"])])
        constitution, identity = self._value_layer(tmp_path)
        (constitution / "empty.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        reading = ss.read_skill_selection_log(
            log_dir,
            days=7,
            skills_dir=self._catalog_dir(tmp_path),
            value_layer_paths=(constitution, identity),
        )
        assert reading.value_layer_files == 2
        assert reading.value_layer_missing == (constitution.name,)
        assert constitution.name in ss.format_skill_selection_report(reading)


class TestNeverSelectedReading:
    """ADR-0097 D5: the whole-history exit reading.

    The error this reading exists to avoid is conflating two populations —
    a skill never selected in a 14-day window is usually one that WAS
    selected before it, and archiving that changes judged behaviour. Every
    test below is about keeping the two apart, or about the caveat that
    travels with them (behaviour-neutrality holds for judged actions only).
    """

    # An explicit UTC calendar window (resolve_selection_window's second
    # mode) rather than `days`: the same seam the sibling reading uses,
    # and the only one that replays identically offline.
    SINCE = dt.date(2026, 8, 8)
    UNTIL = dt.date(2026, 8, 22)

    def _write(self, log_dir: Path, day: str, records: list[dict]) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"skill-selection-{day}.jsonl").open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    @staticmethod
    def _judged(selected: list[str], catalog: list[str], full: int = 40000) -> dict:
        return {
            "ts": "2026-08-01T00:00:00+00:00",
            "verdict": "judged",
            "enforced": True,
            "selected": selected,
            "catalog_names": catalog,
            "full_skill_tokens": full,
            "would_be_skill_tokens": 100,
        }

    def _store(self, tmp_path: Path, names: list[str]) -> Path:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        for name in names:
            _write_skill(skills_dir, f"{name}.md", name, f"does {name}")
        return skills_dir

    def test_strict_and_dormant_are_separate_populations(self, tmp_path):
        """A skill selected before the window is dormant, never strict."""
        skills_dir = self._store(tmp_path, ["kept", "dormant-one", "never-one"])
        log_dir = tmp_path / "logs"
        catalog = ["kept", "dormant-one", "never-one"]
        # Old day, outside the 14-day window: dormant-one is chosen here.
        self._write(
            log_dir,
            "2026-07-01",
            [self._judged(["kept", "dormant-one"], catalog)] * 5,
        )
        # In-window days: only `kept` is ever chosen.
        self._write(log_dir, "2026-08-20", [self._judged(["kept"], catalog)] * 700)

        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert [e.name for e in reading.strict] == ["never-one"]
        assert [e.name for e in reading.dormant] == ["dormant-one"]
        assert reading.strict[0].judged_exposure == 705
        assert reading.strict[0].last_selected == ""
        assert reading.dormant[0].window_exposure == 700
        assert reading.dormant[0].last_selected == "2026-07-01"

    def test_below_floor_is_not_a_candidate(self, tmp_path):
        """Never selected, but not offered enough times for that to mean
        anything — listed nowhere, counted separately, named in reasons."""
        skills_dir = self._store(tmp_path, ["kept", "fresh"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-08-20",
            [self._judged(["kept"], ["kept", "fresh"])] * 599,
        )

        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.strict == ()
        assert [e.name for e in reading.below_floor] == ["fresh"]
        assert reading.below_floor[0].judged_exposure == 599
        assert "NEVER_SELECTED_BELOW_FLOOR" in reading.reasons

    def test_floor_is_inclusive_at_the_boundary(self, tmp_path):
        """600 is the floor, not the first number above it — the ADR names
        the smallest round number ABOVE the observed max latency (569)."""
        skills_dir = self._store(tmp_path, ["kept", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-08-20",
            [self._judged(["kept"], ["kept", "quiet"])] * 600,
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert [e.name for e in reading.strict] == ["quiet"]
        assert reading.below_floor == ()
        assert "NEVER_SELECTED_BELOW_FLOOR" not in reading.reasons

    def test_selection_before_the_history_start_still_disqualifies(self, tmp_path):
        """The strict cut is over the WHOLE history, not the window: one
        selection in March keeps a skill out of the archive list forever."""
        skills_dir = self._store(tmp_path, ["old-favourite"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-03-02", [self._judged(["old-favourite"], ["old-favourite"])])
        self._write(log_dir, "2026-08-20", [self._judged([], ["old-favourite"])] * 900)

        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.strict == ()
        assert [e.name for e in reading.dormant] == ["old-favourite"]

    def test_a_name_absent_from_the_window_catalog_is_not_dormant(self, tmp_path):
        """Not offered is not refused — the 2026-07-12 breaker-open
        misreading, in the population that would now propose an archive."""
        skills_dir = self._store(tmp_path, ["retired-from-catalog"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-03-02",
            [self._judged(["retired-from-catalog"], ["retired-from-catalog"])],
        )
        # In-window records exist but never carry the name in the catalog.
        self._write(log_dir, "2026-08-20", [self._judged([], ["something-else"])] * 50)

        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.dormant == ()
        assert reading.strict == ()

    def test_exposure_counts_judged_records_only(self, tmp_path):
        """A fail-open window offers nothing — it cannot make a candidate."""
        skills_dir = self._store(tmp_path, ["quiet"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-08-20",
            [
                {
                    "verdict": "fail_open_llm",
                    "selected": [],
                    "catalog_names": ["quiet"],
                }
            ]
            * 900,
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.strict == ()
        assert reading.below_floor[0].judged_exposure == 0
        assert reading.window_fail_open == 900
        assert "NEVER_SELECTED_NO_HISTORY" in reading.reasons

    def test_full_corpus_count_includes_no_template_excludes_empty_catalog(self, tmp_path):
        """The count is "records that injected the WHOLE corpus", and the
        producer decides which verdicts those are: ``shadow_observe`` returns
        None — "keep the full prompt" — for ``fail_open_*`` AND for
        ``no_template``. ``empty_catalog`` is the asymmetry: it also skips the
        judgment, but there was no corpus to inject.

        Excluding ``no_template`` is not conservative, it is wrong in the
        dangerous direction: a week that lost the selection template would
        print "fail-open: 0 of 700" next to an archive candidate that all 700
        of those actions injected.
        """
        skills_dir = self._store(tmp_path, ["a"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-08-20",
            [
                {"verdict": "fail_open_parse", "selected": [], "catalog_names": ["a"]},
                {"verdict": "fail_open_llm", "selected": [], "catalog_names": ["a"]},
                {"verdict": "no_template", "selected": [], "catalog_names": ["a"]},
                {"verdict": "empty_catalog", "selected": [], "catalog_names": []},
                self._judged(["a"], ["a"]),
            ],
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.window_records == 5
        assert reading.window_judged == 1
        # 2 fail_open_* + 1 no_template; empty_catalog is the one left out.
        assert reading.window_fail_open == 3
        assert reading.history_fail_open == 3
        # Still not `records - judged` (that would be 4): the residual stays
        # visible instead of being absorbed.
        assert reading.window_records - reading.window_judged == 4

    def test_a_lost_template_week_is_not_reported_as_zero_fail_open(self, tmp_path):
        """The scenario the verdict set exists for, end to end."""
        skills_dir = self._store(tmp_path, ["a", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-10", [self._judged(["a"], ["a", "quiet"])] * 600)
        self._write(
            log_dir,
            "2026-08-20",
            [{"verdict": "no_template", "selected": [], "catalog_names": ["a", "quiet"]}] * 700,
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert [e.name for e in reading.strict] == ["quiet"]
        assert reading.history_fail_open == 700
        text = ss.format_never_selected_report(reading)
        assert "fail-open across the whole history: 700 of 1300 records" in text

    def test_unreadable_catalog_withholds_every_population(self, tmp_path):
        """No ruler: "never selected" cannot be said of names that could not
        be enumerated, and must not read as "nothing to archive"."""
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-20", [self._judged([], ["ghost"])] * 900)
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=None
        )
        assert reading.strict == ()
        assert reading.dormant == ()
        assert reading.below_floor == ()
        assert reading.catalog_available is False
        assert "NEVER_SELECTED_NO_CATALOG" in reading.reasons

    def test_corpus_size_is_the_latest_observed_not_recomputed(self, tmp_path):
        """The caveat asks what the SELECTOR saw, so the reading takes the
        value the writer baked in, latest day wins."""
        skills_dir = self._store(tmp_path, ["a"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-07-01", [self._judged(["a"], ["a"], full=10_000)])
        self._write(log_dir, "2026-08-20", [self._judged(["a"], ["a"], full=38_867)])
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.history_full_skill_tokens == 38867
        assert reading.num_ctx == 32768
        assert "NEVER_SELECTED_FULL_TOKENS_UNKNOWN" not in reading.reasons

    def test_missing_corpus_size_abstains_rather_than_guessing(self, tmp_path):
        skills_dir = self._store(tmp_path, ["a"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-08-20",
            [{"verdict": "judged", "selected": ["a"], "catalog_names": ["a"]}],
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.history_full_skill_tokens == 0
        assert "NEVER_SELECTED_FULL_TOKENS_UNKNOWN" in reading.reasons

    def test_dropped_rows_degrade_visibly_not_just_without_aborting(self, tmp_path):
        """Not aborting is half the requirement. The other half is that the
        reader can see the reading narrowed its own evidence — a dropped row
        is a judged action this list did not get to look at."""
        skills_dir = self._store(tmp_path, ["a", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-20", [self._judged(["a"], ["a", "quiet"])] * 600)
        with (log_dir / "skill-selection-2026-08-20.jsonl").open("a", encoding="utf-8") as fh:
            fh.write("{broken\n")
            fh.write("[1, 2]\n")  # valid JSON, not an object
            fh.write("\n")  # blank lines are not a drop
        (log_dir / "skill-selection-not-a-date.jsonl").write_text("{}\n", encoding="utf-8")

        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.history_records == 600
        assert reading.history_files == 1
        assert reading.malformed_rows == 2
        assert reading.unreadable_files == 0
        assert "NEVER_SELECTED_LOG_PARTIAL" in reading.reasons
        # Bounded loss: two rows out of six hundred do not withhold the list.
        assert "NEVER_SELECTED_LOG_UNREADABLE" not in reading.reasons
        assert [e.name for e in reading.strict] == ["quiet"]
        assert "Evidence lost: 0 unreadable day(s), 2 unusable row(s)" in (
            ss.format_never_selected_report(reading)
        )

    def test_a_lost_day_withholds_the_strict_list(self, tmp_path):
        """Unbounded loss. The one record that ever selected a name may be in
        the file that would not open, so the honest answer is not a shorter
        list — it is no list."""
        skills_dir = self._store(tmp_path, ["kept", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-10", [self._judged(["kept"], ["kept", "quiet"])] * 600)
        # The day that ever selected `quiet`, made unopenable.
        self._write(log_dir, "2026-08-20", [self._judged(["quiet"], ["kept", "quiet"])])
        (log_dir / "skill-selection-2026-08-20.jsonl").chmod(0o000)
        try:
            reading = ss.read_never_selected(
                log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
            )
        finally:
            (log_dir / "skill-selection-2026-08-20.jsonl").chmod(0o644)
        assert reading.unreadable_files == 1
        assert "NEVER_SELECTED_LOG_UNREADABLE" in reading.reasons
        assert "NEVER_SELECTED_LOG_PARTIAL" in reading.reasons
        assert reading.strict == ()
        text = ss.format_never_selected_report(reading)
        assert "WITHHELD (NEVER_SELECTED_LOG_UNREADABLE)" in text
        assert "- (none)" not in text.split("Strict (")[1].split("Dormant")[0]

    def test_an_undecodable_byte_does_not_escape_the_reading(self, tmp_path):
        """UnicodeDecodeError is a ValueError, not an OSError. Uncaught it
        propagates into the CLI's broad handler and the section vanishes with
        no reason code — indistinguishable from a build without it."""
        skills_dir = self._store(tmp_path, ["kept", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-10", [self._judged(["kept"], ["kept", "quiet"])] * 600)
        (log_dir / "skill-selection-2026-08-20.jsonl").write_bytes(b"\xff\xfe not utf-8\n")
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.unreadable_files == 1
        assert "NEVER_SELECTED_LOG_UNREADABLE" in reading.reasons
        assert reading.strict == ()

    def test_an_undecodable_skill_file_does_not_escape_the_reading(self, tmp_path):
        skills_dir = self._store(tmp_path, ["kept"])
        (skills_dir / "broken.md").write_bytes(b"---\nname: \xff\n---\nbody\n")
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-10", [self._judged(["kept"], ["kept"])])
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.catalog_size == 1

    def test_an_empty_window_is_named_and_withholds_dormant(self, tmp_path):
        """An agent that was down for the requested fortnight: every
        window-scoped figure reads 0, including a fail-open count a reader
        would otherwise take as "no full-corpus injection ever happened"."""
        skills_dir = self._store(tmp_path, ["kept", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(
            log_dir,
            "2026-07-01",
            [self._judged(["kept"], ["kept", "quiet"])] * 601
            + [{"verdict": "fail_open_llm", "selected": [], "catalog_names": ["kept", "quiet"]}]
            * 40,
        )
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.window_records == 0
        assert "NEVER_SELECTED_EMPTY_WINDOW" in reading.reasons
        assert reading.dormant == ()
        # The history figure is what the strict list is judged against, and
        # it is not recoverable by subtraction from the window's.
        assert reading.history_fail_open == 40
        text = ss.format_never_selected_report(reading)
        assert "fail-open across the whole history: 40 of 641 records" in text
        assert "WITHHELD (NEVER_SELECTED_EMPTY_WINDOW)" in text

    def test_missing_log_dir_reads_as_no_history(self, tmp_path):
        skills_dir = self._store(tmp_path, ["a"])
        reading = ss.read_never_selected(
            tmp_path / "absent", since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert reading.history_files == 0
        assert "NEVER_SELECTED_NO_HISTORY" in reading.reasons
        assert reading.strict == ()

    def test_json_projection_carries_rows_not_counts(self, tmp_path):
        """The packet computes its own counts — a count in a field is a
        count nobody checked."""
        skills_dir = self._store(tmp_path, ["kept", "quiet"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-08-20", [self._judged(["kept"], ["kept", "quiet"])] * 600)
        payload = ss.never_selected_reading_json(
            ss.read_never_selected(
                log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
            )
        )
        # Round-trips through JSON (the packet reads it off disk).
        payload = json.loads(json.dumps(payload))
        assert payload["exposure_floor"] == ss.NEVER_SELECTED_EXPOSURE_FLOOR
        assert [r["name"] for r in payload["strict"]] == ["quiet"]
        assert payload["strict"][0]["judged_exposure"] == 600
        assert payload["window"]["fail_open"] == 0
        assert payload["corpus"]["num_ctx"] == 32768
        assert payload["catalog"]["size"] == 2
        assert not any(key.endswith("_count") for key in payload)

    def test_report_names_both_populations_and_the_caveat(self, tmp_path):
        skills_dir = self._store(tmp_path, ["kept", "quiet", "dormant-one"])
        log_dir = tmp_path / "logs"
        catalog = ["kept", "quiet", "dormant-one"]
        self._write(log_dir, "2026-07-01", [self._judged(["dormant-one"], catalog)])
        self._write(log_dir, "2026-08-20", [self._judged(["kept"], catalog)] * 600)
        text = ss.format_never_selected_report(
            ss.read_never_selected(
                log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
            )
        )
        assert "quiet: offered in 601 judged records" in text
        assert "NOT archive candidates" in text
        assert "dormant-one" in text
        assert "fail-open in 2026-08-08 … 2026-08-22: 0 of 600 records" in text
        # Both window-scoped lines name the same span — the fail-open count
        # and the dormant cut are measured under one window, and a reader
        # must not have to guess whether they are.
        assert "Dormant (0 selections in 2026-08-08 … 2026-08-22 but" in text
        assert "full corpus 40,000 tok exceeds NUM_CTX 32,768" in text

    def test_report_flag_prints_both_readings(self, capsys):
        """`report --skill-selection` is the exit reading's live consumer —
        the weekly chain does not yet pass it to the packet, and an
        instrument with no reader is one this repo would not keep."""
        from contemplative_agent.cli import main

        with (
            patch("contemplative_agent.core.metrics.compute_metrics"),
            patch(
                "contemplative_agent.core.metrics.format_report",
                return_value="SESSION-METRICS",
            ),
            patch(
                "contemplative_agent.core.skill_selection.format_skill_selection_report",
                return_value="WINDOW-READING",
            ),
            patch(
                "contemplative_agent.core.skill_selection.format_never_selected_report",
                return_value="EXIT-READING",
            ) as mock_exit,
            patch("sys.argv", ["contemplative-agent", "report", "--skill-selection"]),
        ):
            main()
        out = capsys.readouterr().out
        assert "WINDOW-READING" in out
        assert "EXIT-READING" in out
        mock_exit.assert_called_once()

    def test_windowed_report_no_longer_calls_its_list_candidates(self, tmp_path):
        """The window reading cannot decide archive candidacy — most of its
        never-selected list is dormant."""
        skills_dir = self._store(tmp_path, ["a", "b"])
        log_dir = tmp_path / "logs"
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        self._write(log_dir, today, [self._judged(["a"], ["a", "b"])])
        text = ss.format_skill_selection_report(
            ss.read_skill_selection_log(log_dir, days=14, skills_dir=skills_dir)
        )
        assert "not archive candidates" in text
        assert "stocktake candidates" not in text

    # --- one windowing scheme, not two (rebase onto T-SKILLSEL-REPORT-WINDOW) ---

    def test_both_readings_resolve_the_same_window(self, tmp_path):
        """The exit reading calls `resolve_selection_window`, so the two
        readings of one log cannot name different fortnights. If a second
        windowing implementation is ever added here, this fails."""
        skills_dir = self._store(tmp_path, ["a"])
        log_dir = tmp_path / "logs"
        for day in ("2026-08-07", "2026-08-08", "2026-08-22", "2026-08-23"):
            self._write(log_dir, day, [self._judged(["a"], ["a"])])

        windowed = ss.read_skill_selection_log(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        exit_reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        # The bound day is in, the day before and the day after are out.
        assert windowed.records == 2
        assert exit_reading.window_records == windowed.records
        assert exit_reading.window_judged == windowed.judged_records
        assert exit_reading.window_days == windowed.days
        assert exit_reading.window_since == windowed.window_since
        assert exit_reading.window_until == windowed.window_until
        # ...and the whole history is still read, past both bounds.
        assert exit_reading.history_records == 4

    def test_days_mode_matches_the_sibling_reading(self, tmp_path):
        skills_dir = self._store(tmp_path, ["a"])
        log_dir = tmp_path / "logs"
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        self._write(log_dir, today, [self._judged(["a"], ["a"])])
        windowed = ss.read_skill_selection_log(log_dir, days=7, skills_dir=skills_dir)
        exit_reading = ss.read_never_selected(log_dir, days=7, skills_dir=skills_dir)
        assert exit_reading.window_days == windowed.days == 7
        assert exit_reading.window_since is None and exit_reading.window_until is None
        assert exit_reading.window_records == windowed.records == 1

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"days": 7, "since": dt.date(2026, 8, 8)},
            {"until": dt.date(2026, 8, 22)},
            {"since": dt.date(2026, 8, 23), "until": dt.date(2026, 8, 22)},
        ],
    )
    def test_bad_window_combinations_raise_from_the_shared_resolver(self, tmp_path, kwargs):
        with pytest.raises(ValueError):
            ss.read_never_selected(tmp_path / "logs", skills_dir=None, **kwargs)

    def test_dormant_cut_respects_the_upper_bound(self, tmp_path):
        """A selection AFTER `until` must not un-dormant a skill: the window
        is what the reader asked about, not "up to now"."""
        skills_dir = self._store(tmp_path, ["revived"])
        log_dir = tmp_path / "logs"
        self._write(log_dir, "2026-07-01", [self._judged(["revived"], ["revived"])])
        self._write(log_dir, "2026-08-20", [self._judged([], ["revived"])] * 3)
        self._write(log_dir, "2026-08-25", [self._judged(["revived"], ["revived"])])
        reading = ss.read_never_selected(
            log_dir, since=self.SINCE, until=self.UNTIL, skills_dir=skills_dir
        )
        assert [e.name for e in reading.dormant] == ["revived"]
        # last_selected is whole-history, and says so by naming the later day.
        assert reading.dormant[0].last_selected == "2026-08-25"
