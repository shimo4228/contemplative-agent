"""run_id / session_id stamping on audit records (ADR-0078 follow-up).

Every audit record written through ``append_jsonl_restricted`` must carry a
process-wide ``run_id``; records written while an agent session is active must
also carry ``session_id``. Stamping lives in the writer so no log producer can
forget it.
"""

import json

import pytest

from contemplative_agent.core import run_context
from contemplative_agent.core._io import append_jsonl_restricted


@pytest.fixture(autouse=True)
def _reset_session_id():
    run_context.set_session_id(None)
    yield
    run_context.set_session_id(None)


def test_run_id_is_stable_hex_within_process() -> None:
    assert isinstance(run_context.RUN_ID, str)
    assert len(run_context.RUN_ID) == 32
    int(run_context.RUN_ID, 16)  # raises if not hex
    assert run_context.RUN_ID == run_context.RUN_ID


def test_session_id_defaults_to_none_and_is_settable() -> None:
    assert run_context.current_session_id() is None
    sid = run_context.new_session_id()
    run_context.set_session_id(sid)
    assert run_context.current_session_id() == sid
    run_context.set_session_id(None)
    assert run_context.current_session_id() is None


def _read_single_record(path):
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_append_stamps_run_id_always(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    append_jsonl_restricted(path, {"ts": "2026-01-01T00:00:00+00:00"})
    record = _read_single_record(path)
    assert record["run_id"] == run_context.RUN_ID
    assert "session_id" not in record  # omitted when no session is active


def test_append_stamps_session_id_when_session_active(tmp_path) -> None:
    sid = run_context.new_session_id()
    run_context.set_session_id(sid)
    path = tmp_path / "audit.jsonl"
    append_jsonl_restricted(path, {"ts": "2026-01-01T00:00:00+00:00"})
    record = _read_single_record(path)
    assert record["run_id"] == run_context.RUN_ID
    assert record["session_id"] == sid


def test_append_does_not_override_caller_supplied_ids(tmp_path) -> None:
    run_context.set_session_id("live-session")
    path = tmp_path / "audit.jsonl"
    append_jsonl_restricted(
        path, {"ts": "t", "run_id": "explicit-run", "session_id": "explicit-session"}
    )
    record = _read_single_record(path)
    assert record["run_id"] == "explicit-run"
    assert record["session_id"] == "explicit-session"


def test_append_does_not_mutate_caller_record(tmp_path) -> None:
    original = {"ts": "t"}
    append_jsonl_restricted(tmp_path / "audit.jsonl", original)
    assert original == {"ts": "t"}
