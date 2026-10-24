"""P3-05.19: the takedown suppression list through the report writer and the export."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from contemplative_agent.core import report, takedown
from contemplative_agent.core.knowledge_store import pattern_id

ROOT = Path(__file__).resolve().parent.parent


def _export_module():
    spec = importlib.util.spec_from_file_location(
        "export_patterns_jsonl", ROOT / "scripts" / "export-patterns-jsonl.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shipped_list_is_empty_and_parses() -> None:
    sup = takedown.parse(
        (ROOT / "config" / "takedown-suppressions.txt").read_text(encoding="utf-8")
    )
    assert not sup


def test_parse_kinds_and_matching() -> None:
    sup = takedown.parse(
        "# c\npost:abcdef12\nname:Some Agent\npattern:0123456789ab\nfile:reports/x.md\n"
    )
    assert sup.post_withdrawn("abcdef12-0000-aaaa")  # full id starts with the listed prefix
    assert not sup.post_withdrawn("zzzzzzzz")
    assert sup.name_withdrawn("some agent")
    assert sup.text_names_withdrawn("a note about Some Agent here")
    assert not sup.text_names_withdrawn("a note about Some Agentic thing")
    assert sup.pattern_withdrawn("0123456789ab") and sup.file_withdrawn("reports/x.md")


@pytest.mark.parametrize("bad", ["nonsense", "unknown:value", "post:", "post:short", "name:   "])
def test_malformed_line_stops_loudly(bad: str) -> None:
    with pytest.raises(takedown.TakedownListError):
        takedown.parse(bad)


def test_load_merges_public_and_private_lists_and_missing_is_empty(tmp_path: Path) -> None:
    cfg, home = tmp_path / "cfg", tmp_path / "home"
    cfg.mkdir()
    home.mkdir()
    assert not takedown.load_suppressions(cfg, home)
    (cfg / takedown.LIST_NAME).write_text("pattern:aaaaaaaaaaaa\n", encoding="utf-8")
    (home / takedown.LIST_NAME).write_text("name:Someone\n", encoding="utf-8")
    sup = takedown.load_suppressions(cfg, home)
    assert sup.pattern_withdrawn("aaaaaaaaaaaa") and sup.name_withdrawn("someone")


ENTRY = {
    "ts": "2026-10-20T03:03:26+00:00",
    "counterparty": "Some Agent",
    "post_id": "abcdef1234567890",
    "context": "THIRD-PARTY TEXT",
    "internal_note": "my note",
    "content": "my reply",
}


def test_report_entry_is_unchanged_without_a_list() -> None:
    text = "\n".join(report._entry_lines(1, "COMMENT", ENTRY))
    assert "THIRD-PARTY TEXT" in text and "Some Agent" in text
    assert text == "\n".join(report._entry_lines(1, "COMMENT", ENTRY, takedown.Suppressions()))


def test_report_renders_withdrawn_post_as_placeholder() -> None:
    sup = takedown.parse("post:abcdef12\n")
    text = "\n".join(report._entry_lines(1, "COMMENT", ENTRY, sup))
    assert "THIRD-PARTY TEXT" not in text and "Some Agent" not in text
    assert takedown.WITHDRAWN in text
    assert "my note" in text and "my reply" in text  # the agent's own text stays


def test_post_matching_handles_short_stored_ids_and_rejects_too_short() -> None:
    full_listed = takedown.parse("post:abcdef1234567890\n")
    assert full_listed.post_withdrawn("abcdef12")  # stored 8-char id, listed full id
    assert full_listed.post_withdrawn("abcdef1234567890")
    assert not full_listed.post_withdrawn("abcdef1")  # under 8 characters never matches
    assert not full_listed.post_withdrawn("")
    assert not full_listed.post_withdrawn("abcdef13")
    prefix_listed = takedown.parse("post:abcdef12\n")
    assert prefix_listed.post_withdrawn("abcdef1234567890")


def test_name_withdrawal_survives_sanitization_of_the_stored_name() -> None:
    sup = takedown.parse("name:Some Agent\n")
    for stored in ("Some\nAgent", "Some Agent\x00", "SOME AGENT"):
        entry = dict(ENTRY, counterparty=stored, post_id="ffffffff00000000")
        text = "\n".join(report._entry_lines(1, "COMMENT", entry, sup))
        assert "THIRD-PARTY TEXT" not in text, stored
        assert takedown.WITHDRAWN in text, stored


def test_generate_all_reports_honours_the_list(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / takedown.LIST_NAME).write_text("post:abcdef12\n", encoding="utf-8")
    monkeypatch.setenv("MOLTBOOK_HOME", str(home))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for day in ("2026-10-20", "2026-10-21"):
        rec = {
            "ts": f"{day}T03:03:26+00:00",
            "type": "activity",
            "data": {
                "action": "comment",
                "content": "my reply",
                "target_agent": "Some Agent",
                "post_id": "abcdef1234567890",
                "original_post": "THIRD-PARTY TEXT",
            },
        }
        (log_dir / f"{day}.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    outs = report.generate_all_reports(log_dir, tmp_path / "out")
    assert len(outs) == 2
    for out in outs:
        assert "THIRD-PARTY TEXT" not in out.read_text(encoding="utf-8")


def test_report_renders_withdrawn_name_as_placeholder() -> None:
    sup = takedown.parse("name:some agent\n")
    other = dict(ENTRY, post_id="ffffffff00000000")
    text = "\n".join(report._entry_lines(1, "COMMENT", other, sup))
    assert "THIRD-PARTY TEXT" not in text and "Some Agent" not in text


def test_generate_report_applies_the_list_end_to_end(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / takedown.LIST_NAME).write_text("post:abcdef12\n", encoding="utf-8")
    monkeypatch.setenv("MOLTBOOK_HOME", str(home))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    rec = {
        "ts": "2026-10-20T03:03:26+00:00",
        "type": "activity",
        "data": {
            "action": "comment",
            "content": "my reply",
            "target_agent": "Some Agent",
            "post_id": "abcdef1234567890",
            "original_post": "THIRD-PARTY TEXT",
            "internal_note": "my note",
        },
    }
    (log_dir / "2026-10-20.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    out = report.generate_report(log_dir, tmp_path / "out", date="2026-10-20")
    assert out is not None
    body = out.read_text(encoding="utf-8")
    assert "THIRD-PARTY TEXT" not in body and "Some Agent" not in body
    assert takedown.WITHDRAWN in body and "my reply" in body


def test_export_withholds_listed_patterns_and_names_and_mirrors_core_rules(tmp_path: Path) -> None:
    mod = _export_module()
    rows = [
        {"pattern": "keep this", "distilled": "2026-10-01T00:00+00:00"},
        {"pattern": "drop by id", "distilled": "2026-10-02T00:00+00:00"},
        {"pattern": "about Some Agent today", "distilled": "2026-10-03T00:00+00:00"},
        {"pattern": "about Some Agentic things", "distilled": "2026-10-04T00:00+00:00"},
    ]
    src = tmp_path / "knowledge.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    lst = tmp_path / "list.txt"
    lst.write_text(
        f"pattern:{pattern_id(rows[1])}\nname:some agent\npost:abcdef12\n", encoding="utf-8"
    )
    out = tmp_path / "out.jsonl"
    n = mod.export(src, out, suppression_files=[lst])
    kept = [json.loads(line)["pattern"] for line in out.read_text().splitlines()]
    assert kept == ["keep this", "about Some Agentic things"] and n == 2
    # the stdlib mirror and the core rules agree row by row
    sup = takedown.parse(lst.read_text(encoding="utf-8"))
    core_kept = [
        r["pattern"]
        for r in rows
        if not (sup.pattern_withdrawn(pattern_id(r)) or sup.text_names_withdrawn(r["pattern"]))
    ]
    assert core_kept == kept


def test_export_without_lists_is_unchanged(tmp_path: Path) -> None:
    mod = _export_module()
    rows = [{"pattern": "a", "distilled": "d"}]
    src = tmp_path / "k.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    out = tmp_path / "o.jsonl"
    assert mod.export(src, out) == 1


def test_export_refuses_a_malformed_list(tmp_path: Path) -> None:
    mod = _export_module()
    src = tmp_path / "k.json"
    src.write_text("[]", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.export(src, tmp_path / "o.jsonl", suppression_files=[bad])


def test_ledger_row_shape_and_public_count_line() -> None:
    good = {
        "received": "2026-11-21",
        "surface": "git history",
        "target": "post:abcdef12",
        "decision": "withdrawn",
        "actioned": "2026-11-22",
        "basis": "author request",
    }
    pending = dict(good, decision="pending", actioned=None)
    takedown.validate_ledger_row(good)
    assert takedown.ledger_count_line([good, pending], "2026-11-23") == (
        "requests received 2 / actioned 1 as of 2026-11-23"
    )
    assert (
        takedown.ledger_count_line([], "2026-10-24")
        == "requests received 0 / actioned 0 as of 2026-10-24"
    )
    for bad in (
        dict(good, decision="maybe"),
        dict(good, received="yesterday"),
        {"received": "2026-11-21"},
    ):
        with pytest.raises(takedown.TakedownListError):
            takedown.validate_ledger_row(bad)
