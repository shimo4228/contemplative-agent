"""Tests for activity report generation from JSONL episode logs."""

import json

from contemplative_agent.core.report import (
    _build_report,
    _format_ts,
    _parse_log,
    generate_all_reports,
    generate_report,
)


class TestFormatTs:
    def test_iso_timestamp(self):
        assert _format_ts("2026-03-14T10:30:45.123+00:00") == "2026-03-14 10:30:45"

    def test_empty_string(self):
        assert _format_ts("") == ""


class TestExtractEntries:
    def test_classifies_comment_reply_post(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"ts": "2026-03-14T01:00:00", "type": "activity", "data": {"action": "comment", "post_id": "p1", "content": "Nice post", "relevance": "0.95"}}),
            json.dumps({"ts": "2026-03-14T02:00:00", "type": "activity", "data": {"action": "reply", "post_id": "p2", "content": "Thanks", "target_agent": "bob"}}),
            json.dumps({"ts": "2026-03-14T03:00:00", "type": "activity", "data": {"action": "post", "post_id": "p3", "title": "My Post", "content": "Hello"}}),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        _, comments, replies, posts = _parse_log(jsonl)
        assert len(comments) == 1
        assert len(replies) == 1
        assert len(posts) == 1
        assert comments[0]["post_id"] == "p1"
        assert replies[0]["target_agent"] == "bob"
        assert posts[0]["title"] == "My Post"

    def test_skips_malformed_json(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('not valid json\n{"ts":"t","type":"activity","data":{"action":"comment","post_id":"p1","content":"ok"}}\n', encoding="utf-8")

        _, comments, replies, posts = _parse_log(jsonl)
        assert len(comments) == 1

    def test_empty_file(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text("", encoding="utf-8")

        _, comments, replies, posts = _parse_log(jsonl)
        assert comments == []
        assert replies == []
        assert posts == []

    def test_skips_blank_lines(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('\n\n{"ts":"t","type":"activity","data":{"action":"post","post_id":"p1","title":"T","content":"C"}}\n\n', encoding="utf-8")

        _, _, _, posts = _parse_log(jsonl)
        assert len(posts) == 1


class TestExtractSessionMeta:
    def test_merges_session_starts_first_value_wins(self, tmp_path):
        """First-seen session meta values are kept; later sessions only fill gaps."""
        jsonl = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "session", "data": {"event": "start", "domain": "first", "model": "a"}}),
            json.dumps({"type": "activity", "data": {"action": "comment"}}),
            json.dumps({"type": "session", "data": {"event": "start", "domain": "second", "extra": "new"}}),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        meta, _, _, _ = _parse_log(jsonl)
        assert meta["domain"] == "first"
        assert meta["model"] == "a"
        assert meta["extra"] == "new"

    def test_returns_empty_when_no_session(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('{"type": "activity", "data": {"action": "comment"}}\n', encoding="utf-8")

        meta, _, _, _ = _parse_log(jsonl)
        assert meta == {}

    def test_ignores_session_end(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('{"type": "session", "data": {"event": "end", "actions_count": 5}}\n', encoding="utf-8")

        meta, _, _, _ = _parse_log(jsonl)
        assert meta == {}

    def test_skips_malformed_json(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('bad json\n{"type": "session", "data": {"event": "start", "domain": "ok"}}\n', encoding="utf-8")

        meta, _, _, _ = _parse_log(jsonl)
        assert meta["domain"] == "ok"


class TestBuildReport:
    def test_includes_session_meta(self):
        meta = {"domain": "contemplative-ai", "axioms_enabled": True, "ollama_model": "qwen3.5:9b"}
        report = _build_report("2026-03-14", [], [], [], session_meta=meta)
        assert "**Configuration**:" in report
        assert "domain=contemplative-ai" in report
        assert "axioms=enabled" in report
        assert "model=qwen3.5:9b" in report

    def test_no_session_meta(self):
        report = _build_report("2026-03-14", [], [], [])
        assert "**Configuration**" not in report

    def test_formats_comments(self):
        comments = [{"ts": "2026-03-14T10:00:00", "post_id": "abc123def456", "content": "Great", "relevance": "0.95", "original_post": ""}]
        report = _build_report("2026-03-14", comments, [], [])
        assert "## Comments (1 total)" in report
        assert "abc123def45" in report
        assert "0.95" in report

    def test_formats_replies(self):
        replies = [{"ts": "2026-03-14T11:00:00", "post_id": "xyz", "content": "Reply text", "target_agent": "alice", "their_comment": "Their msg", "original_post": "Original"}]
        report = _build_report("2026-03-14", [], replies, [])
        assert "## Replies (1 total)" in report
        assert "Reply to alice" in report
        assert "Their msg" in report

    def test_formats_posts(self):
        posts = [{"ts": "2026-03-14T12:00:00", "post_id": "p1", "title": "My Title", "content": "Post body", "submolt": "alignment"}]
        report = _build_report("2026-03-14", [], [], posts)
        assert "## Self Posts (1 total)" in report
        assert "My Title" in report
        assert "Submolt: alignment" in report

    def test_summary_section(self):
        comments = [{"ts": "t", "post_id": "p", "content": "c", "relevance": "0.92", "original_post": ""}]
        report = _build_report("2026-03-14", comments, [], [])
        assert "## Summary" in report
        assert "Comments: 1" in report
        assert "Relevance range: 0.92 - 0.92" in report

    def test_empty_data(self):
        report = _build_report("2026-03-14", [], [], [])
        assert "# Moltbook Activity Report — 2026-03-14" in report
        assert "Comments: 0" in report


class TestGenerateReport:
    def test_generates_report_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        jsonl = log_dir / "2026-03-14.jsonl"
        jsonl.write_text(json.dumps({"ts": "t", "type": "activity", "data": {"action": "comment", "post_id": "p1", "content": "Hi", "relevance": "0.9"}}) + "\n", encoding="utf-8")

        output_dir = tmp_path / "reports"
        result = generate_report(log_dir, output_dir, date="2026-03-14")

        assert result is not None
        assert result.exists()
        assert "comment-report-2026-03-14.md" in result.name
        content = result.read_text(encoding="utf-8")
        assert "Moltbook Activity Report" in content

    def test_returns_none_no_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        output_dir = tmp_path / "reports"

        assert generate_report(log_dir, output_dir, date="2026-01-01") is None

    def test_returns_none_no_activity(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        jsonl = log_dir / "2026-03-14.jsonl"
        jsonl.write_text('{"type": "session", "data": {"event": "start"}}\n', encoding="utf-8")

        output_dir = tmp_path / "reports"
        assert generate_report(log_dir, output_dir, date="2026-03-14") is None

    def test_creates_output_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        jsonl = log_dir / "2026-03-14.jsonl"
        jsonl.write_text(json.dumps({"ts": "t", "type": "activity", "data": {"action": "post", "post_id": "p1", "title": "T", "content": "C"}}) + "\n", encoding="utf-8")

        output_dir = tmp_path / "nested" / "reports"
        result = generate_report(log_dir, output_dir, date="2026-03-14")

        assert result is not None
        assert output_dir.exists()

    def test_includes_session_meta_in_report(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        jsonl = log_dir / "2026-03-14.jsonl"
        lines = [
            json.dumps({"type": "session", "data": {"event": "start", "domain": "test", "axioms_enabled": True, "ollama_model": "qwen3.5:9b"}}),
            json.dumps({"ts": "t", "type": "activity", "data": {"action": "comment", "post_id": "p1", "content": "Hi", "relevance": "0.9"}}),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        output_dir = tmp_path / "reports"
        result = generate_report(log_dir, output_dir, date="2026-03-14")
        content = result.read_text(encoding="utf-8")
        assert "domain=test" in content


class TestGenerateAllReports:
    def test_generates_multiple_reports(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        for date in ["2026-03-13", "2026-03-14"]:
            jsonl = log_dir / f"{date}.jsonl"
            jsonl.write_text(json.dumps({"ts": "t", "type": "activity", "data": {"action": "comment", "post_id": "p1", "content": "Hi", "relevance": "0.9"}}) + "\n", encoding="utf-8")

        output_dir = tmp_path / "reports"
        results = generate_all_reports(log_dir, output_dir)
        assert len(results) == 2

    def test_empty_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        output_dir = tmp_path / "reports"

        assert generate_all_reports(log_dir, output_dir) == []
