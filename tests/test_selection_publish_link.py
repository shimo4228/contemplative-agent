"""RFC-0028: linking a selection record to the comment it became.

The link is a **second** record, not an edit of the first: the selection log
is append-only (ADR-0075), so a comment id that only exists after the publish
call cannot be written back into the record that preceded it. Every selection
record therefore carries a ``selection_id`` and null placeholders, and a
``kind: publish`` record carries the id plus the outcome reason code.

The other half of these tests is backward compatibility: the two instruments
and the reading script over ``skill-selection-*.jsonl`` must not see the new
family at all, so the longitudinal series stays one series.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core import skill_selection as ss
from contemplative_agent.core.never_selected_metrics import read_never_selected
from contemplative_agent.core.selection_metrics import (
    observed_injection_outcomes,
    read_skill_selection_log,
)

PROMPT_TEMPLATE = "{skill_catalog}\n---\n{situation}"


def _write_skill(d: Path, filename: str, name: str, desc: str) -> None:
    (d / filename).write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\nbody of {name}\n", encoding="utf-8"
    )


@pytest.fixture()
def configured(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(skills_dir, "a.md", "skill-a", "does a")
    audit_dir = tmp_path / "logs"
    ss.configure_skill_selection(skills_dir=skills_dir, audit_dir=audit_dir)
    monkeypatch.setattr(ss, "_load_selection_template", lambda: PROMPT_TEMPLATE)
    yield audit_dir
    ss.configure_skill_selection(skills_dir=None, audit_dir=None)


def _records(audit_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for f in sorted(audit_dir.glob("skill-selection-*.jsonl"))
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestSelectionRecordCarriesTheLinkFields:
    @patch("contemplative_agent.core.skill_selection.generate")
    def test_judged_record_has_selection_id_and_null_publish_fields(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.comment")
        (rec,) = _records(configured)
        assert rec["kind"] == "selection"
        assert rec["selection_id"] == obs.selection_id
        assert rec["comment_id"] is None
        assert rec["publish_status"] is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_fail_open_record_also_carries_a_selection_id(self, gen, configured):
        gen.return_value = None
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.reply")
        (rec,) = _records(configured)
        assert rec["verdict"] == "fail_open_llm"
        assert rec["selection_id"] == obs.selection_id
        assert obs.selected is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_legacy_entry_point_still_returns_only_the_selection(self, gen, configured):
        gen.return_value = "skill-a"
        assert ss.shadow_observe_skill_selection("sit", generation_caller="x") == ("skill-a",)


class TestPublishRecord:
    @patch("contemplative_agent.core.skill_selection.generate")
    def test_publish_appends_a_second_record(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.comment")
        ss.record_publish_outcome(
            obs.selection_id, comment_id="c1", publish_status=ss.PUBLISH_PUBLISHED
        )
        selection, publish = _records(configured)
        assert selection["kind"] == "selection"
        assert publish["kind"] == "publish"
        assert publish["selection_id"] == obs.selection_id
        assert publish["comment_id"] == "c1"
        assert publish["publish_status"] == ss.PUBLISH_PUBLISHED
        assert publish["ts"]

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_failed_publish_records_null_comment_id_and_a_reason(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.comment")
        ss.record_publish_outcome(
            obs.selection_id, comment_id=None, publish_status=ss.PUBLISH_FAILED
        )
        publish = _records(configured)[-1]
        assert publish["comment_id"] is None
        assert publish["publish_status"] == ss.PUBLISH_FAILED

    def test_no_selection_id_writes_nothing(self, configured):
        ss.record_publish_outcome(None, comment_id="c1", publish_status=ss.PUBLISH_PUBLISHED)
        assert _records(configured) == []

    def test_kill_switch_writes_nothing(self, tmp_path):
        ss.configure_skill_selection(skills_dir=None, audit_dir=None)
        ss.record_publish_outcome("sel", comment_id="c1", publish_status=ss.PUBLISH_PUBLISHED)
        assert list(tmp_path.glob("*.jsonl")) == []


class TestExistingReadersAreUnaffected:
    """The publish family and any missing key must not move a single number
    the two instruments and the reading script report."""

    def _log(self, logs: Path, day: str, records: list[dict]) -> None:
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"skill-selection-{day}.jsonl").open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def _selection(self, **over) -> dict:
        rec = {
            "kind": "selection",
            "selection_id": "s1",
            "ts": "2026-09-01T00:00:00+00:00",
            "generation_caller": "moltbook.comment",
            "verdict": "judged",
            "enforced": True,
            "selected": ["skill-a"],
            "selected_count": 1,
            "rejected_names": [],
            "catalog_count": 1,
            "catalog_names": ["skill-a"],
            "full_skill_tokens": 100,
            "would_be_skill_tokens": 40,
            "comment_id": None,
            "publish_status": None,
        }
        rec.update(over)
        return rec

    def _publish(self) -> dict:
        return {
            "kind": "publish",
            "selection_id": "s1",
            "ts": "2026-09-01T00:01:00+00:00",
            "comment_id": "c1",
            "publish_status": "published",
        }

    def test_window_reading_counts_only_selection_records(self, tmp_path):
        logs = tmp_path / "logs"
        self._log(logs, "2026-09-01", [self._selection(), self._publish(), self._publish()])
        reading = read_skill_selection_log(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 1), skills_dir=None
        )
        assert reading.records == 1
        assert reading.judged_records == 1
        assert {v for v, _ in reading.verdicts} == {"judged"}

    def test_legacy_records_without_the_new_keys_still_read(self, tmp_path):
        logs = tmp_path / "logs"
        legacy = self._selection()
        for key in ("kind", "selection_id", "comment_id", "publish_status"):
            legacy.pop(key)
        self._log(logs, "2026-09-01", [legacy, self._publish()])
        reading = read_skill_selection_log(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 1), skills_dir=None
        )
        assert reading.records == 1
        assert reading.judged_records == 1

    def test_never_selected_reading_ignores_publish_records(self, tmp_path):
        logs = tmp_path / "logs"
        skills = tmp_path / "skills"
        skills.mkdir()
        _write_skill(skills, "a.md", "skill-a", "does a")
        self._log(logs, "2026-09-01", [self._selection(), self._publish()])
        reading = read_never_selected(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 1), skills_dir=skills
        )
        assert reading.history_records == 1

    def test_reading_script_loader_ignores_publish_records(self, tmp_path):
        logs = tmp_path / "logs"
        self._log(logs, "2026-09-01", [self._selection(), self._publish()])
        spec = importlib.util.spec_from_file_location(
            "skillsel_reading", Path("scripts/skillsel_reading.py")
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        records, unparsable = module.load(logs)
        assert unparsable == 0
        assert len(records) == 1
        assert records[0]["verdict"] == "judged"


class TestRunLevelReaderIgnoresPublishRecords:
    """`observed_injection_outcomes` reads through the shared walk, so the
    `kind` filter is the one in `selection_window` — the second copy it used
    to keep (security review 2026-09-09, the reader that was missed) is gone
    and this pins that the filter still holds from where it now lives."""

    def test_publish_records_do_not_inflate_the_run_counts(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        with (logs / "skill-selection-2026-09-01.jsonl").open("w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "kind": "selection",
                        "selection_id": "s1",
                        "verdict": "judged",
                        "enforced": True,
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "kind": "publish",
                        "selection_id": "s1",
                        "comment_id": "c1",
                        "publish_status": "published",
                    }
                )
                + "\n"
            )
        out = observed_injection_outcomes(logs)
        assert out["records"] == 1
        assert out["enforced"] == 1
        assert out["fell_back"] == 0
        assert out["verdicts"] == {"judged": 1}


class TestPublishFailureReason:
    """RFC-0029: a failed publish says *why* in two machine-classifiable
    columns — the HTTP status and a code-fixed reason — and never in the
    platform's own words (ADR-0083: an untrusted message reaches a readable
    log as a digest at most, and here not at all)."""

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_published_row_carries_both_columns_as_null(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.comment")
        ss.record_publish_outcome(
            obs.selection_id, comment_id="c1", publish_status=ss.PUBLISH_PUBLISHED
        )
        publish = _records(configured)[-1]
        # Present-and-null, not absent: the reading distinguishes "no reason
        # because it worked" from "written before RFC-0029".
        assert publish["http_status"] is None
        assert publish["failure_reason"] is None

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_failed_row_carries_the_status_and_the_reason(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.reply")
        ss.record_publish_outcome(
            obs.selection_id,
            comment_id=None,
            publish_status=ss.PUBLISH_FAILED,
            http_status=400,
            failure_reason=ss.PUBLISH_FAILURE_PARENT_REJECTED,
        )
        publish = _records(configured)[-1]
        assert publish["publish_status"] == ss.PUBLISH_FAILED
        assert publish["http_status"] == 400
        assert publish["failure_reason"] == "parent_rejected"

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_an_off_vocabulary_reason_is_recorded_as_unknown(self, gen, configured):
        """The writer is the vocabulary's gate: a caller that passes anything
        else (a future adapter, a bad refactor) may not widen the column into
        free text — that is how untrusted strings get into a readable log."""
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.reply")
        ss.record_publish_outcome(
            obs.selection_id,
            comment_id=None,
            publish_status=ss.PUBLISH_FAILED,
            http_status="400; injected",  # type: ignore[arg-type]
            failure_reason='{"statuscode":400,"message":"parent comment not found"}',
        )
        publish = _records(configured)[-1]
        assert publish["failure_reason"] == ss.PUBLISH_FAILURE_UNKNOWN
        assert publish["http_status"] is None
        assert "parent comment not found" not in json.dumps(publish)

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_an_out_of_range_status_is_dropped(self, gen, configured):
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.reply")
        ss.record_publish_outcome(
            obs.selection_id,
            comment_id=None,
            publish_status=ss.PUBLISH_FAILED,
            http_status=99999,
            failure_reason=ss.PUBLISH_FAILURE_TRANSPORT,
        )
        publish = _records(configured)[-1]
        assert publish["http_status"] is None
        assert publish["failure_reason"] == "transport"

    @patch("contemplative_agent.core.skill_selection.generate")
    def test_an_unhashable_reason_does_not_raise_into_the_publish_path(self, gen, configured):
        """The vocabulary gate is inside the never-raises contract: ``x in
        frozenset`` raises TypeError for an unhashable value, which would let
        an instrument fail the action it only observes (security review
        2026-09-12)."""
        gen.return_value = "skill-a"
        obs = ss.observe_skill_selection_recorded("sit", generation_caller="moltbook.reply")
        ss.record_publish_outcome(
            obs.selection_id,
            comment_id=None,
            publish_status=ss.PUBLISH_FAILED,
            failure_reason=["parent_rejected"],  # type: ignore[arg-type]
        )
        publish = _records(configured)[-1]
        assert publish["failure_reason"] == ss.PUBLISH_FAILURE_UNKNOWN

    def test_the_vocabulary_is_closed(self):
        assert ss.PUBLISH_FAILURE_REASONS == frozenset(
            {"rate_limited", "parent_rejected", "transport", "unknown"}
        )


class TestLegacyPublishRowsStillRead:
    """RFC-0029 goal 3: the three readers over this log must not notice the
    two new keys are missing from every row written before today."""

    def _log(self, logs: Path, day: str, records: list[dict]) -> None:
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"skill-selection-{day}.jsonl").open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def _rows(self, *, with_new_keys: bool) -> list[dict]:
        selection = {
            "kind": "selection",
            "selection_id": "s1",
            "ts": "2026-09-01T00:00:00+00:00",
            "generation_caller": "moltbook.comment",
            "verdict": "judged",
            "enforced": True,
            "selected": ["skill-a"],
            "selected_count": 1,
            "catalog_count": 1,
            "catalog_names": ["skill-a"],
            "comment_id": None,
            "publish_status": None,
        }
        publish = {
            "kind": "publish",
            "selection_id": "s1",
            "ts": "2026-09-01T00:01:00+00:00",
            "comment_id": None,
            "publish_status": "publish_failed",
        }
        if with_new_keys:
            publish |= {"http_status": 429, "failure_reason": "rate_limited"}
        return [selection, publish]

    def _readings(self, tmp_path: Path, *, with_new_keys: bool) -> tuple:
        from contemplative_agent.core.comment_outcomes import read_comment_outcomes

        logs = tmp_path / ("new" if with_new_keys else "legacy")
        self._log(logs, "2026-09-01", self._rows(with_new_keys=with_new_keys))
        window = read_skill_selection_log(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 1), skills_dir=None
        )
        weekly = read_comment_outcomes(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 1), min_age_days=0
        )
        spec = importlib.util.spec_from_file_location(
            "skillsel_reading", Path("scripts/skillsel_reading.py")
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        records, unparsable = module.load(logs)
        return window, weekly, records, unparsable

    def test_every_reader_reports_the_same_numbers_either_way(self, tmp_path):
        legacy_window, legacy_weekly, legacy_records, legacy_bad = self._readings(
            tmp_path, with_new_keys=False
        )
        new_window, new_weekly, new_records, new_bad = self._readings(tmp_path, with_new_keys=True)
        assert legacy_bad == new_bad == 0
        assert len(legacy_records) == len(new_records) == 1
        assert (legacy_window.records, legacy_window.judged_records) == (
            new_window.records,
            new_window.judged_records,
        )
        for key in ("publish_failures", "joined_publishes", "unjoined_publishes", "malformed_rows"):
            assert legacy_weekly[key] == new_weekly[key], key
        assert legacy_weekly["publish_failures"] == 1

    def test_the_run_level_reader_is_unmoved_too(self, tmp_path):
        logs = tmp_path / "logs"
        self._log(logs, "2026-09-01", self._rows(with_new_keys=True))
        out = observed_injection_outcomes(logs)
        assert out["records"] == 1
        assert out["verdicts"] == {"judged": 1}
