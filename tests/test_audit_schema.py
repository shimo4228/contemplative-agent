"""``schemas/audit.schema.json`` is checked against what the writers emit (P1-12.4).

A schema nobody runs rots: this is the CI step that keeps it equal to the
executed row shape. Rows come from the real writer for every ``source`` the
code can produce, so adding a source (or a key) without touching the schema
fails here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args
from unittest.mock import patch

import pytest

from contemplative_agent.cli import approval
from contemplative_agent.cli.approval import CHANNELS, REASON_CODES, AuditSource, Decision

from ._audit_schema import load_schema, validate_row


@pytest.fixture
def written(tmp_path):
    """Rows from the real writer, one per AuditSource, plus a correction."""
    log = tmp_path / "logs" / "audit.jsonl"
    with (
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", log),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
    ):
        for source in get_args(AuditSource):
            if source == "correction":
                continue
            approval._log_approval(
                "insight",
                tmp_path / "skills" / "a.md",
                None if source == "stage" else True,
                f"text for {source}",
                source=source,  # type: ignore[arg-type]
                snapshot_path=tmp_path / "snapshots" / "insight_20261024T000000Z",
                source_ids=["abc"],
                epistemic_counts={"generated": 1},
            )
        approval._log_approval(
            "insight", tmp_path / "skills" / "b.md", False, "rejected", reason_code="stale"
        )
        approval.log_correction(
            corrects_ts="2026-08-09T04:02:11+00:00",
            content_hash_of_corrected="0123456789abcdef",
            mv_from="constitution/axioms-2.md",
            mv_to="constitution/axioms.md",
            sha_checked="0123456789abcdef",
            approver="Test Human",
            reason="moved by hand",
        )
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_every_written_row_validates(written):
    assert len(written) == len(get_args(AuditSource)) + 1
    for row in written:
        assert validate_row(row) == [], row


def test_the_enums_equal_the_code(written):
    schema = load_schema()["properties"]
    assert set(schema["source"]["enum"]) == set(get_args(AuditSource))
    assert set(schema["reason_code"]["enum"]) - {None} == set(REASON_CODES)
    assert set(schema["channel"]["enum"]) - {None} == set(CHANNELS)
    # ``held`` is historical: in the schema, not in the writer's vocabulary.
    assert set(schema["decision"]["enum"]) == set(get_args(Decision)) | {"held"}


def test_writer_keys_are_all_declared_properties():
    schema = load_schema()
    assert set(schema["x-writer-keys"]) <= set(schema["properties"])


def test_a_legacy_row_validates_without_the_new_keys():
    legacy = {
        "ts": "2026-08-15T04:02:00+00:00",
        "command": "amend-constitution",
        "path": "/Users/x/.config/moltbook/constitution/contemplative-axioms-2.md",
        "decision": "approved",
        "source": "stage-adopted-auto",
        "content_hash": "0123456789abcdef",
        "snapshot_path": None,
        "reason": None,
        "source_ids": None,
        "epistemic_counts": None,
    }
    assert validate_row(legacy, current=False) == []
    assert validate_row(legacy, current=True) != [], "today's writer keys are required of new rows"


def test_an_unknown_key_or_value_is_refused(written):
    row = dict(written[0])
    assert validate_row({**row, "mystery": 1}) != []
    assert validate_row({**row, "channel": "carrier-pigeon"}) != []
    assert validate_row({**row, "content_hash": "short"}) != []


def test_the_real_log_shape_matches_the_documented_path_rule(written):
    inside = [r for r in written if r["command"] == "insight"]
    assert all(not Path(r["path"]).is_absolute() for r in inside)
