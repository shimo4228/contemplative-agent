"""P0-04.1: distill's window is "recent day-files minus the processed ledger".

Fixtures are synthetic day files with explicit ``ts`` values (the real episode
logs are never read by a Claude Code session)."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core import distill_ledger
from contemplative_agent.core.distill import distill
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore

LEDGER = "distill-processed.jsonl"


def _episode(ts: str, tag: str) -> dict:
    return {
        "ts": ts,
        "type": "activity",
        "data": {
            "action": "comment",
            "post_id": f"p-{tag}",
            "original_post": f"A post about {tag} in public threads.",
            "content": f"A grounded comment about {tag} that quotes details.",
            "target_agent": "Alice",
            "internal_note": f"Noticed {tag} landed better with concrete quotes.",
        },
    }


def _write_day(log_dir, date: str, records: list[dict]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{date}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _pattern_for(tag: str) -> str:
    return json.dumps(
        {"patterns": [f"Pattern about {tag} shows that quoting concrete details helps threads"]}
    )


@pytest.fixture
def distinct_embeddings():
    """Mutually orthogonal vectors, so dedup never merges across episodes."""
    counter = {"n": 0}

    def _mk(texts):
        rows = []
        for _ in texts:
            v = np.zeros(64, dtype=np.float32)
            v[counter["n"] % 64] = 1.0
            counter["n"] += 1
            rows.append(v)
        return np.array(rows, dtype=np.float32)

    with patch("contemplative_agent.core.distill.embed_texts", side_effect=_mk):
        yield


def _generate_by_tag(fail_tags=()):
    """A ``generate`` stub answering per episode tag; ``None`` for fail_tags."""

    def _gen(prompt, **kwargs):
        for tag in ("quokka", "lemur", "narwhal", "tapir"):
            if tag in prompt:
                return None if tag in fail_tags else _pattern_for(tag)
        return None

    return _gen


def _run(tmp_path, now, *, days=1, dry_run=False, ledger=True, fail_tags=()):
    log = EpisodeLog(log_dir=tmp_path / "episodes")
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    with patch(
        "contemplative_agent.core.distill.generate", side_effect=_generate_by_tag(fail_tags)
    ) as gen:
        result = distill(
            days=days,
            dry_run=dry_run,
            episode_log=log,
            knowledge_store=ks,
            processed_ledger_path=tmp_path / LEDGER if ledger else None,
            now=now,
        )
    return result, gen


def _ledger_ids(tmp_path) -> set[str]:
    return distill_ledger.read_processed_ids(tmp_path / LEDGER)


def _stored(tmp_path) -> list[str]:
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    ks.load()
    return [p["pattern"] for p in ks.get_raw_patterns()]


class TestLedgerWindow:
    def test_an_episode_across_the_utc_day_is_distilled_by_the_next_run(
        self, tmp_path, distinct_embeddings
    ):
        """The 21Z episode lives in yesterday's file; the next 18:30Z run reads
        yesterday's file too and picks it up (legacy ``--days 1`` did not)."""
        late = "2026-10-23T21:30:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-23", [_episode(late, "quokka")])
        now = _utc(2026, 10, 24, 18, 30)

        legacy, legacy_gen = _run(tmp_path, now, ledger=False)
        assert "No episodes" in legacy and legacy_gen.call_count == 0

        _, gen = _run(tmp_path, now, days=1)
        assert gen.call_count == 1
        assert any("quokka" in p for p in _stored(tmp_path))
        assert _ledger_ids(tmp_path) == {late}

    def test_a_late_start_across_midnight_still_reads_the_scheduled_day(
        self, tmp_path, distinct_embeddings
    ):
        """Scheduled 18:30Z on the 24th, started after 00:00Z on the 25th: the
        run takes ``now`` once and still reads the 24th's file."""
        ts = "2026-10-24T17:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-24", [_episode(ts, "lemur")])

        _, gen = _run(tmp_path, _utc(2026, 10, 25, 0, 20))
        assert gen.call_count == 1
        assert _ledger_ids(tmp_path) == {ts}

    def test_a_second_run_over_the_same_files_adds_nothing(self, tmp_path, distinct_embeddings):
        ts = "2026-10-24T03:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-24", [_episode(ts, "tapir")])
        now = _utc(2026, 10, 24, 18, 30)

        _run(tmp_path, now)
        before = _stored(tmp_path)
        ledger_before = (tmp_path / LEDGER).read_text()

        second, gen = _run(tmp_path, now)
        assert gen.call_count == 0
        assert "No episodes" in second
        assert _stored(tmp_path) == before  # ADD 0 / UPDATE 0
        assert (tmp_path / LEDGER).read_text() == ledger_before

    def test_a_flapping_backend_loses_nothing(self, tmp_path, distinct_embeddings):
        ok = "2026-10-24T03:00:00.000001+00:00"
        flaky = "2026-10-24T04:00:00.000001+00:00"
        _write_day(
            tmp_path / "episodes",
            "2026-10-24",
            [_episode(ok, "tapir"), _episode(flaky, "narwhal")],
        )
        now = _utc(2026, 10, 24, 18, 30)

        _run(tmp_path, now, fail_tags=("narwhal",))
        assert _ledger_ids(tmp_path) == {ok}  # the abstained one is NOT recorded

        _, gen = _run(tmp_path, now)  # backend recovered
        assert gen.call_count == 1  # only the one that failed
        assert _ledger_ids(tmp_path) == {ok, flaky}
        assert any("narwhal" in p for p in _stored(tmp_path))

    def test_dry_run_records_nothing(self, tmp_path, distinct_embeddings):
        ts = "2026-10-24T03:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-24", [_episode(ts, "tapir")])
        _run(tmp_path, _utc(2026, 10, 24, 18, 30), dry_run=True)
        assert not (tmp_path / LEDGER).exists()

    def test_episodes_already_cited_by_the_store_are_not_rerun(
        self, tmp_path, distinct_embeddings
    ):
        """Introducing the ledger must not re-run what the calendar run finished."""
        ts = "2026-10-24T03:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-24", [_episode(ts, "tapir")])
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern(
            "An older pattern already distilled from this very episode of steady work",
            embedding=[1.0] + [0.0] * 63,
            provenance={"source_type": "self", "source_episode_ids": [ts]},
        )
        ks.save()
        _, gen = _run(tmp_path, _utc(2026, 10, 24, 18, 30))
        assert gen.call_count == 0

    def test_the_window_is_at_least_two_day_files(self, tmp_path, distinct_embeddings):
        ts = "2026-10-23T22:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-23", [_episode(ts, "quokka")])
        _, gen = _run(tmp_path, _utc(2026, 10, 24, 18, 30), days=1)
        assert gen.call_count == 1
        assert distill_ledger.LEDGER_MIN_WINDOW_DAYS >= 2

    def test_without_a_ledger_the_calendar_window_is_unchanged(self, tmp_path, distinct_embeddings):
        ts = "2026-10-23T22:00:00.000001+00:00"
        _write_day(tmp_path / "episodes", "2026-10-23", [_episode(ts, "quokka")])
        _, gen = _run(tmp_path, _utc(2026, 10, 24, 18, 30), days=1, ledger=False)
        assert gen.call_count == 0


class TestLedgerFile:
    def test_malformed_lines_are_skipped(self, tmp_path):
        path = tmp_path / LEDGER
        path.write_text('{"episode_id": "a"}\n{"episode_id": "b"\n\nnot json\n{"x": 1}\n')
        assert distill_ledger.read_processed_ids(path) == {"a"}

    def test_missing_file_and_none_are_empty(self, tmp_path):
        assert distill_ledger.read_processed_ids(tmp_path / "nope.jsonl") == set()
        assert distill_ledger.read_processed_ids(None) == set()

    def test_a_failed_append_is_reported_not_raised(self, tmp_path, caplog):
        with patch.object(distill_ledger, "append_jsonl_restricted", side_effect=OSError("full")):
            written = distill_ledger.record_processed(tmp_path / LEDGER, ["a", "b"])
        assert written == 0
        assert distill_ledger.LEDGER_WRITE_FAILED in caplog.text
