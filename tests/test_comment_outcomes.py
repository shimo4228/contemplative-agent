"""RFC-0028: the outcome record (write side) and its weekly reading.

The instrument records what the platform returned about our own comments —
replies, their depth, upvotes — and never judges them. These tests pin the
three properties the record layer has to hold for a replay to mean anything:
one record per reaction (dedupe by reply id), untrusted bodies stored as
base64 + sha256 + length only, and a reason code on every path that declines
to write (ADR-0075: no silent fallback).
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from contemplative_agent.core import comment_outcomes as co


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path: Path):
    co.configure_comment_outcomes(audit_dir=tmp_path)
    yield
    co.configure_comment_outcomes(audit_dir=None)


def _records(tmp_path: Path) -> list[dict]:
    path = tmp_path / co.OUTCOME_LOG_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _own(comment_id: str, *, upvotes: int | None = 0, replies=()) -> co.ObservedComment:
    return co.ObservedComment(
        comment_id=comment_id, is_own=True, upvotes=upvotes, body="ours", replies=tuple(replies)
    )


def _theirs(comment_id: str, body: str = "theirs", *, replies=()) -> co.ObservedComment:
    return co.ObservedComment(
        comment_id=comment_id, is_own=False, upvotes=0, body=body, replies=tuple(replies)
    )


class TestRecording:
    def test_records_reply_and_state_for_own_comment(self, tmp_path: Path):
        scan = co.record_comment_outcomes("post1", (_own("c1", replies=[_theirs("r1")]),))
        assert scan.own_comments == 1
        kinds = [r["kind"] for r in _records(tmp_path)]
        assert kinds.count(co.KIND_REPLY) == 1
        assert kinds.count(co.KIND_COMMENT_STATE) == 1

    def test_reply_record_carries_depth_and_post_and_comment_id(self, tmp_path: Path):
        # c1 (ours) → r1 (theirs) → r2 (ours) → r3 (theirs). r3 is a reaction
        # to r2, the nearest comment of ours above it — not to c1 as well.
        nested = _theirs("r1", replies=[_own("r2", replies=[_theirs("r3")])])
        co.record_comment_outcomes("post1", (_own("c1", replies=[nested]),))
        replies = {r["reply_id"]: r for r in _records(tmp_path) if r["kind"] == co.KIND_REPLY}
        assert replies["r1"]["depth"] == 1
        assert replies["r1"]["comment_id"] == "c1"
        assert replies["r1"]["by_self"] is False
        assert replies["r2"]["depth"] == 2
        assert replies["r2"]["comment_id"] == "c1"
        assert replies["r2"]["by_self"] is True
        assert replies["r3"]["depth"] == 1
        assert replies["r3"]["comment_id"] == "r2"
        assert replies["r3"]["post_id"] == "post1"

    def test_state_record_carries_the_columns_separately(self, tmp_path: Path):
        co.record_comment_outcomes(
            "post1", (_own("c1", upvotes=3, replies=[_theirs("r1", replies=[_theirs("r2")])]),)
        )
        state = [r for r in _records(tmp_path) if r["kind"] == co.KIND_COMMENT_STATE][0]
        assert state["upvotes"] == 3
        assert state["reply_count"] == 2
        assert state["max_depth"] == 2
        assert state["has_reply"] is True

    def test_second_scan_writes_nothing_new(self, tmp_path: Path):
        tree = (_own("c1", replies=[_theirs("r1")]),)
        co.record_comment_outcomes("post1", tree)
        before = len(_records(tmp_path))
        scan = co.record_comment_outcomes("post1", tree)
        assert scan.written == 0
        assert scan.duplicates > 0
        assert len(_records(tmp_path)) == before

    def test_new_reply_appends_without_rewriting(self, tmp_path: Path):
        co.record_comment_outcomes("post1", (_own("c1", replies=[_theirs("r1")]),))
        first = _records(tmp_path)
        co.record_comment_outcomes("post1", (_own("c1", replies=[_theirs("r1"), _theirs("r2")]),))
        after = _records(tmp_path)
        assert after[: len(first)] == first
        assert {r["reply_id"] for r in after if r["kind"] == co.KIND_REPLY} == {"r1", "r2"}

    def test_reply_body_is_stored_as_base64_sha256_length_only(self, tmp_path: Path):
        body = "返信の本文 <untrusted>"
        co.record_comment_outcomes("post1", (_own("c1", replies=[_theirs("r1", body)]),))
        rec = [r for r in _records(tmp_path) if r["kind"] == co.KIND_REPLY][0]
        assert rec["reply_body_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert rec["reply_body_bytes"] == len(body.encode("utf-8"))
        assert base64.b64decode(rec["reply_body_b64"]).decode("utf-8") == body
        # The plaintext must not appear anywhere else in the record.
        assert body not in json.dumps({k: v for k, v in rec.items() if k != "reply_body_b64"})

    def test_kill_switch_is_a_reason_code_not_a_silent_skip(self, tmp_path: Path):
        co.configure_comment_outcomes(audit_dir=None)
        scan = co.record_comment_outcomes("post1", (_own("c1", replies=[_theirs("r1")]),))
        assert scan.written == 0
        assert co.REASON_NOT_CONFIGURED in scan.reasons
        assert not (tmp_path / co.OUTCOME_LOG_NAME).exists()

    def test_missing_ids_are_counted_with_a_reason_code(self, tmp_path: Path):
        scan = co.record_comment_outcomes(
            "post1",
            (
                _own("", replies=[_theirs("r1")]),
                _own("c2", replies=[_theirs("")]),
            ),
        )
        assert co.REASON_MISSING_COMMENT_ID in scan.reasons
        assert co.REASON_MISSING_REPLY_ID in scan.reasons
        assert {r["comment_id"] for r in _records(tmp_path)} == {"c2"}

    def test_no_post_id_is_a_reason_code(self, tmp_path: Path):
        scan = co.record_comment_outcomes("", (_own("c1", replies=[_theirs("r1")]),))
        assert scan.written == 0
        assert co.REASON_MISSING_POST_ID in scan.reasons

    def test_comments_that_are_not_ours_are_not_recorded(self, tmp_path: Path):
        scan = co.record_comment_outcomes("post1", (_theirs("x1", replies=[_theirs("x2")]),))
        assert scan.own_comments == 0
        assert _records(tmp_path) == []

    def test_state_record_is_rewritten_only_when_the_state_changes(self, tmp_path: Path):
        co.record_comment_outcomes("post1", (_own("c1", upvotes=0),))
        co.record_comment_outcomes("post1", (_own("c1", upvotes=1),))
        states = [r for r in _records(tmp_path) if r["kind"] == co.KIND_COMMENT_STATE]
        assert [s["upvotes"] for s in states] == [0, 1]


class TestReading:
    """The weekly read: a distribution per skill, joined through the publish
    record. Never a contribution estimate — the note is part of the contract."""

    def _write_selection(self, logs: Path, day: str, sel_id: str, skills: list[str]):
        rec = {
            "kind": "selection",
            "selection_id": sel_id,
            "ts": f"{day}T00:00:00+00:00",
            "verdict": "judged",
            "enforced": True,
            "selected": skills,
            "comment_id": None,
            "publish_status": None,
        }
        with (logs / f"skill-selection-{day}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def _write_publish(self, logs: Path, day: str, sel_id: str, comment_id: str | None):
        rec = {
            "kind": "publish",
            "selection_id": sel_id,
            "ts": f"{day}T00:01:00+00:00",
            "comment_id": comment_id,
            "publish_status": "published" if comment_id else "publish_failed",
        }
        with (logs / f"skill-selection-{day}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def _write_outcome(self, logs: Path, rec: dict):
        with (logs / co.OUTCOME_LOG_NAME).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def test_per_skill_rows_of_injected_replied_and_depth(self, tmp_path: Path):
        logs = tmp_path
        self._write_selection(logs, "2026-09-01", "s1", ["alpha", "beta"])
        self._write_publish(logs, "2026-09-01", "s1", "c1")
        self._write_selection(logs, "2026-09-01", "s2", ["alpha"])
        self._write_publish(logs, "2026-09-01", "s2", "c2")
        self._write_outcome(
            logs,
            {
                "kind": co.KIND_COMMENT_STATE,
                "comment_id": "c1",
                "has_reply": True,
                "reply_count": 2,
                "max_depth": 2,
                "upvotes": 1,
            },
        )
        # c2 was observed and drew nothing — that is a real zero, unlike an
        # unobserved publish (see TestDenominatorIsWhatWasObserved).
        self._write_outcome(
            logs,
            {
                "kind": co.KIND_COMMENT_STATE,
                "comment_id": "c2",
                "has_reply": False,
                "reply_count": 0,
                "max_depth": 0,
                "upvotes": 0,
            },
        )
        reading = co.read_comment_outcomes(
            logs, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        rows = {r["skill"]: r for r in reading["skills"]}
        assert rows["alpha"]["injected_comments"] == 2
        assert rows["alpha"]["comments_with_reply"] == 1
        assert rows["alpha"]["reply_rate"] == pytest.approx(0.5)
        assert rows["alpha"]["mean_thread_depth"] == pytest.approx(1.0)
        assert rows["beta"]["injected_comments"] == 1
        assert rows["beta"]["reply_rate"] == pytest.approx(1.0)

    def test_note_is_fixed_in_the_json(self, tmp_path: Path):
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        assert reading["observation_note"] == co.OBSERVATION_NOTE
        assert "寄与" in reading["observation_note"]
        assert reading["coverage_note"] == co.COVERAGE_NOTE

    def test_comments_younger_than_the_maturity_window_are_excluded(self, tmp_path: Path):
        self._write_selection(tmp_path, "2026-09-07", "s1", ["alpha"])
        self._write_publish(tmp_path, "2026-09-07", "s1", "c1")
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=2
        )
        assert reading["skills"] == []
        assert reading["excluded_immature_publishes"] == 1

    def test_failed_publishes_are_counted_not_dropped(self, tmp_path: Path):
        self._write_selection(tmp_path, "2026-09-01", "s1", ["alpha"])
        self._write_publish(tmp_path, "2026-09-01", "s1", None)
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        assert reading["publish_failures"] == 1
        assert reading["skills"] == []

    def test_publish_without_its_selection_is_named(self, tmp_path: Path):
        self._write_publish(tmp_path, "2026-09-01", "orphan", "c9")
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        assert reading["unjoined_publishes"] == 1

    def test_reading_never_decodes_reply_bodies(self, tmp_path: Path):
        self._write_selection(tmp_path, "2026-09-01", "s1", ["alpha"])
        self._write_publish(tmp_path, "2026-09-01", "s1", "c1")
        self._write_outcome(
            tmp_path,
            {
                "kind": co.KIND_REPLY,
                "comment_id": "c1",
                "reply_id": "r1",
                "depth": 1,
                "by_self": False,
                "reply_body_b64": base64.b64encode("秘密".encode()).decode(),
            },
        )
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        assert "秘密" not in json.dumps(reading, ensure_ascii=False)
        assert "reply_body_b64" not in json.dumps(reading)


class TestIdValidation:
    """Ids come off an untrusted response and become log keys, so they are
    format-checked before they are written (security review 2026-09-09 —
    the publish side already did this via `created_comment_id`)."""

    def test_malformed_ids_are_rejected_with_a_reason_code(self, tmp_path: Path):
        bad = "../../etc/passwd"
        scan = co.record_comment_outcomes(
            "post1", (_own(bad, replies=[_theirs("r1")]), _own("c2", replies=[_theirs(bad)]))
        )
        assert co.REASON_MISSING_COMMENT_ID in scan.reasons
        assert co.REASON_MISSING_REPLY_ID in scan.reasons
        written = json.dumps(_records(tmp_path))
        assert bad not in written

    def test_malformed_post_id_is_rejected(self, tmp_path: Path):
        scan = co.record_comment_outcomes("post 1; rm -rf", (_own("c1"),))
        assert scan.written == 0
        assert co.REASON_MISSING_POST_ID in scan.reasons


class TestNestedOwnComments:
    """A reply under a nested comment of ours belongs to the nearest own
    ancestor only — counting it twice would inflate the reply rate that
    decides whether this instrument survives (security review 2026-09-09)."""

    def test_reply_counts_against_the_nearest_own_ancestor_only(self, tmp_path: Path):
        inner = _own("c2", replies=[_theirs("r1")])
        co.record_comment_outcomes("post1", (_own("c1", replies=[inner]),))
        states = {
            r["comment_id"]: r for r in _records(tmp_path) if r["kind"] == co.KIND_COMMENT_STATE
        }
        assert states["c2"]["reply_count"] == 1
        assert states["c2"]["has_reply"] is True
        assert states["c1"]["reply_count"] == 0
        assert states["c1"]["has_reply"] is False
        replies = {r["reply_id"]: r for r in _records(tmp_path) if r["kind"] == co.KIND_REPLY}
        # c2 is itself a reaction to c1 (we answered ourselves) and is recorded
        # as one — but r1, its reply, is attributed to c2 alone.
        assert replies["c2"]["comment_id"] == "c1"
        assert replies["c2"]["by_self"] is True
        assert replies["r1"]["comment_id"] == "c2"
        assert replies["r1"]["depth"] == 1


class TestDenominatorIsWhatWasObserved:
    """A publish the recorder can never see (a comment on another agent's
    post — the recorder only runs over our own posts) must not enter a skill's
    denominator as a silent zero: that drives every reply rate toward 0 and
    makes ADR-0106's exit criterion unreachable (code review 2026-09-09)."""

    def _seed(self, logs: Path, observed_ids: list[str], unobserved_ids: list[str]):
        recs = []
        for i, cid in enumerate(observed_ids + unobserved_ids):
            sid = f"s{i}"
            recs.append(
                {
                    "kind": "selection",
                    "selection_id": sid,
                    "verdict": "judged",
                    "selected": ["alpha"],
                }
            )
            recs.append(
                {
                    "kind": "publish",
                    "selection_id": sid,
                    "comment_id": cid,
                    "publish_status": "published",
                }
            )
        with (logs / "skill-selection-2026-09-01.jsonl").open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        with (logs / co.OUTCOME_LOG_NAME).open("w", encoding="utf-8") as f:
            for cid in observed_ids:
                f.write(
                    json.dumps(
                        {
                            "kind": co.KIND_COMMENT_STATE,
                            "comment_id": cid,
                            "has_reply": cid == observed_ids[0],
                            "reply_count": 1 if cid == observed_ids[0] else 0,
                            "max_depth": 1 if cid == observed_ids[0] else 0,
                            "upvotes": 0,
                        }
                    )
                    + "\n"
                )

    def test_unobserved_publishes_are_excluded_and_counted(self, tmp_path: Path):
        self._seed(tmp_path, ["c1", "c2"], ["c3", "c4", "c5"])
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        (row,) = reading["skills"]
        assert row["injected_comments"] == 2
        assert row["reply_rate"] == pytest.approx(0.5)
        assert reading["unobserved_publishes"] == 3
        assert reading["observed_publishes"] == 2

    def test_observed_count_is_windowed_not_all_time(self, tmp_path: Path):
        self._seed(tmp_path, ["c1"], [])
        with (tmp_path / co.OUTCOME_LOG_NAME).open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"kind": co.KIND_COMMENT_STATE, "comment_id": "old", "has_reply": True})
                + "\n"
            )
        reading = co.read_comment_outcomes(
            tmp_path, since=date(2026, 9, 1), until=date(2026, 9, 7), min_age_days=0
        )
        assert reading["observed_publishes"] == 1
        assert "observed_comments" not in reading
