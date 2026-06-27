"""Tests for scripts/state_invariant_check.py — deterministic state drift check."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import state_invariant_check as sic  # type: ignore[import-not-found]  # noqa: E402


def _live(text: str, **extra) -> dict:
    p = {
        "pattern": text,
        "distilled": "2026-06-20T10:00:00+00:00",
        "embedding": [0.1, 0.2],
        "valid_from": "2026-06-20T10:00:00+00:00",
        "valid_until": None,
    }
    p.update(extra)
    return p


def _result(results, name):
    return next(r for r in results if r.name == name)


class TestSunsetFields:
    def test_clean_when_no_retired_fields(self):
        r = _result(sic.check_knowledge([_live("a clean pattern")]), "sunset_fields")
        assert r.level == sic._OK

    def test_flags_retired_fields_with_adr(self):
        patterns = [
            _live("p1", trust_score=0.9),
            _live("p2", importance=0.5, restored_from_evolution_at="2026-04-01"),
        ]
        r = _result(sic.check_knowledge(patterns), "sunset_fields")
        assert r.level == sic._WARN
        assert "trust_score" in r.summary
        assert "ADR-0056" in r.summary  # importance


class TestRequiredAndTimestamp:
    def test_missing_pattern_field_is_fail(self):
        bad = {"distilled": "2026-06-20T10:00:00+00:00", "valid_until": None}
        r = _result(sic.check_knowledge([bad]), "required_fields")
        assert r.level == sic._FAIL

    def test_unparseable_timestamp_is_fail(self):
        r = _result(sic.check_knowledge([_live("p", distilled="not-a-date")]),
                    "timestamp_validity")
        assert r.level == sic._FAIL

    def test_unknown_timestamp_is_fail(self):
        r = _result(sic.check_knowledge([_live("p", distilled="unknown")]),
                    "timestamp_validity")
        assert r.level == sic._FAIL

    def test_clean_timestamps_ok(self):
        r = _result(sic.check_knowledge([_live("p")]), "timestamp_validity")
        assert r.level == sic._OK


class TestDuplicatesAndEmbedding:
    def test_duplicate_live_texts_flagged(self):
        patterns = [_live("same text"), _live("same text"), _live("other")]
        r = _result(sic.check_knowledge(patterns), "duplicate_live_texts")
        assert r.level == sic._WARN
        assert "1 live texts duplicated" in r.summary
        assert r.samples and r.samples[0].startswith("same text")

    def test_invalidated_duplicates_not_counted(self):
        # Only LIVE rows count; a tombstoned duplicate is expected (bitemporal).
        patterns = [
            _live("kept"),
            {**_live("kept"), "valid_until": "2026-06-21T00:00:00+00:00"},
        ]
        r = _result(sic.check_knowledge(patterns), "duplicate_live_texts")
        assert r.level == sic._OK

    def test_missing_embedding_is_fail(self):
        p = _live("p")
        del p["embedding"]
        r = _result(sic.check_knowledge([p]), "missing_embedding")
        assert r.level == sic._FAIL


class TestSoftInvalidatedRatio:
    def test_low_ratio_is_info(self):
        patterns = [_live(f"p{i}") for i in range(9)] + [
            {**_live("old"), "valid_until": "2026-06-21T00:00:00+00:00"}
        ]
        r = _result(sic.check_knowledge(patterns), "soft_invalidated_ratio")
        assert r.level == sic._INFO
        assert "10.0%" in r.summary

    def test_high_ratio_is_warn(self):
        patterns = [_live("live")] + [
            {**_live(f"old{i}"), "valid_until": "2026-06-21T00:00:00+00:00"}
            for i in range(4)
        ]  # 4/5 = 80% tombstoned
        r = _result(sic.check_knowledge(patterns), "soft_invalidated_ratio")
        assert r.level == sic._WARN


class TestAgents:
    def test_unique_followed_ok(self):
        r = sic.check_agents({"followed": ["a", "b", "c"]})[0]
        assert r.level == sic._OK

    def test_duplicate_followed_warn(self):
        r = sic.check_agents({"followed": ["a", "b", "a"]})[0]
        assert r.level == sic._WARN
        assert "1 duplicate" in r.summary

    def test_followed_not_a_list_is_fail(self):
        r = sic.check_agents({"followed": "accidental-string"})[0]
        assert r.level == sic._FAIL


class TestLoadAndRender:
    def test_load_reads_only_state_files_not_episodes(self, tmp_path):
        (tmp_path / "knowledge.json").write_text(
            json.dumps([_live("persisted pattern")]), encoding="utf-8"
        )
        (tmp_path / "agents.json").write_text(
            json.dumps({"followed": ["x"]}), encoding="utf-8"
        )
        # An episode log present in the same tree must be ignored.
        (tmp_path / "2026-06-23.jsonl").write_text(
            json.dumps({"data": {"pattern": "injection bait"}}), encoding="utf-8"
        )
        patterns, agents = sic.load_state(tmp_path)
        assert len(patterns) == 1
        assert agents == {"followed": ["x"]}

    def test_render_all_ok(self):
        out = sic.render_markdown(sic.check_knowledge([_live("p")]))
        assert "State Invariant Check" in out
        assert "All invariants hold" in out

    def test_render_reports_fail(self):
        bad = {"distilled": "x", "valid_until": None}  # missing pattern
        out = sic.render_markdown(sic.check_knowledge([bad]))
        assert "FAIL" in out

    def test_render_escapes_backtick_and_pipe_in_samples(self):
        # Duplicate live texts reach the LLM as code-span samples; a backtick
        # or pipe must be neutralized so it cannot break the span/table.
        text = "use `with` blocks | always"
        out = sic.render_markdown(sic.check_knowledge([_live(text), _live(text)]))
        assert "examples:" in out
        # The raw backtick from the sample must not survive (only the wrapping
        # code-span backticks remain); the pipe is escaped.
        assert "`with`" not in out
        assert "\\|" in out

    def test_run_endtoend_on_missing_home_is_clean(self, tmp_path):
        # No state files → empty pattern list → no corruption, no crash.
        results = sic.run(tmp_path / "nonexistent")
        assert all(r.level != sic._FAIL for r in results)
