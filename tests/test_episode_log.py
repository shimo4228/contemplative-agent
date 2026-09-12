"""Tests for core/episode_log — Layer 1 append-only daily JSONL storage."""

import json
import logging
from datetime import datetime, timedelta, timezone

from contemplative_agent.core import episode_log as episode_log_module
from contemplative_agent.core.episode_log import EpisodeLog


def _date_str(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestAppend:
    def test_appends_to_today_utc_file(self, tmp_path):
        log = EpisodeLog(tmp_path)
        log.append("post", {"content": "hello"})
        path = tmp_path / f"{_date_str()}.jsonl"
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        # run_id は共有 writer (_io.append_jsonl_restricted) が全 JSONL に
        # スタンプする実行識別子（ADR-0078 follow-up）。session 中は
        # session_id も付くが、テストプロセスでは非 session なので付かない。
        assert set(record) == {"ts", "type", "data", "run_id"}
        assert record["type"] == "post"
        assert record["data"] == {"content": "hello"}

    def test_ts_is_utc_iso(self, tmp_path):
        log = EpisodeLog(tmp_path)
        log.append("activity", {})
        record = json.loads((tmp_path / f"{_date_str()}.jsonl").read_text(encoding="utf-8"))
        assert record["ts"].endswith("+00:00")

    def test_none_log_dir_is_noop(self, tmp_path):
        log = EpisodeLog(None)
        log.append("post", {"content": "x"})
        assert list(tmp_path.iterdir()) == []

    def test_write_oserror_warns_without_raising(self, tmp_path, monkeypatch, caplog):
        def _raise(_path, _record):
            raise OSError("disk full")

        monkeypatch.setattr(episode_log_module, "append_jsonl_restricted", _raise)
        log = EpisodeLog(tmp_path)
        with caplog.at_level(logging.WARNING):
            log.append("post", {"content": "x"})
        assert "Failed to write episode log" in caplog.text


class TestReadFile:
    def test_missing_file_returns_empty(self, tmp_path):
        assert EpisodeLog.read_file(tmp_path / "absent.jsonl") == []

    def test_blank_lines_skipped(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")
        assert EpisodeLog.read_file(path) == [{"a": 1}, {"a": 2}]

    def test_malformed_line_skipped_with_warning(self, tmp_path, caplog):
        path = tmp_path / "log.jsonl"
        path.write_text('{"a": 1}\nnot json{\n{"a": 2}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            records = EpisodeLog.read_file(path)
        assert records == [{"a": 1}, {"a": 2}]
        assert "Skipping malformed log line" in caplog.text

    def test_reads_multiple_valid_lines(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text("\n".join(json.dumps({"i": i}) for i in range(5)) + "\n", encoding="utf-8")
        assert len(EpisodeLog.read_file(path)) == 5


class TestReadRange:
    @staticmethod
    def _write_day(tmp_path, days_ago, records):
        path = tmp_path / f"{_date_str(days_ago)}.jsonl"
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )

    def test_days_1_reads_today_only(self, tmp_path):
        self._write_day(tmp_path, 0, [{"type": "post", "data": {"d": "today"}}])
        self._write_day(tmp_path, 1, [{"type": "post", "data": {"d": "yesterday"}}])
        records = EpisodeLog(tmp_path).read_range(days=1)
        assert [r["data"]["d"] for r in records] == ["today"]

    def test_days_2_includes_yesterday(self, tmp_path):
        self._write_day(tmp_path, 0, [{"type": "post", "data": {"d": "today"}}])
        self._write_day(tmp_path, 1, [{"type": "post", "data": {"d": "yesterday"}}])
        records = EpisodeLog(tmp_path).read_range(days=2)
        assert {r["data"]["d"] for r in records} == {"today", "yesterday"}

    def test_record_type_filter(self, tmp_path):
        self._write_day(
            tmp_path,
            0,
            [
                {"type": "post", "data": {}},
                {"type": "interaction", "data": {}},
                {"type": "post", "data": {}},
            ],
        )
        records = EpisodeLog(tmp_path).read_range(days=1, record_type="post")
        assert len(records) == 2
        assert all(r["type"] == "post" for r in records)

    def test_missing_day_files_silently_skipped(self, tmp_path):
        self._write_day(tmp_path, 0, [{"type": "post", "data": {}}])
        records = EpisodeLog(tmp_path).read_range(days=7)
        assert len(records) == 1

    def test_none_log_dir_returns_empty(self):
        assert EpisodeLog(None).read_range(days=3) == []

    def test_repeated_reads_parse_each_file_once(self, tmp_path, monkeypatch):
        """The feed gate calls read_range once per candidate post; the days it
        re-reads are append-only, so the parse is memoized per (mtime, size)."""
        self._write_day(tmp_path, 0, [{"type": "post", "data": {"d": "a"}}])
        self._write_day(tmp_path, 1, [{"type": "post", "data": {"d": "b"}}])
        log = EpisodeLog(tmp_path)
        parsed: list[str] = []
        real = EpisodeLog.read_file

        def counting(path):
            parsed.append(path.name)
            return real(path)

        monkeypatch.setattr(EpisodeLog, "read_file", staticmethod(counting))
        first = log.read_range(days=2)
        second = log.read_range(days=2)
        assert [r["data"]["d"] for r in first] == [r["data"]["d"] for r in second]
        assert len(parsed) == 2

    def test_appending_to_a_day_invalidates_the_memo(self, tmp_path):
        """Today's file grows during a session — a stale read must not be
        reachable."""
        self._write_day(tmp_path, 0, [{"type": "post", "data": {"d": "a"}}])
        log = EpisodeLog(tmp_path)
        assert [r["data"]["d"] for r in log.read_range(days=1)] == ["a"]
        self._write_day(
            tmp_path,
            0,
            [{"type": "post", "data": {"d": "a"}}, {"type": "post", "data": {"d": "b"}}],
        )
        assert [r["data"]["d"] for r in log.read_range(days=1)] == ["a", "b"]

    def test_returned_list_is_not_the_memo(self, tmp_path):
        """A caller that mutates the list it got back cannot corrupt later reads."""
        self._write_day(tmp_path, 0, [{"type": "post", "data": {"d": "a"}}])
        log = EpisodeLog(tmp_path)
        got = log.read_range(days=1)
        got.clear()
        assert len(log.read_range(days=1)) == 1
