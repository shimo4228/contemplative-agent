"""scripts/snapshot_resolve.py: decisions reach their snapshot from public files only (P1-12.9)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import snapshot_resolve as sr  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "snapshot_resolve.py"


def _find_data_repo() -> Path:
    """The sibling data repo: ``CONTEMPLATIVE_AGENT_DATA_REPO``, else next to this checkout."""
    import os

    here = Path(__file__).resolve()
    candidates = [os.environ.get("CONTEMPLATIVE_AGENT_DATA_REPO", "")] + [
        str(here.parents[i] / "contemplative-agent-data") for i in (2, 3)
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "snapshots").is_dir():
            return Path(candidate)
    return here.parent / "_no_data_repo"


DATA_REPO = _find_data_repo()
MINUTE = timedelta(seconds=60)


def _manifests(*specs):
    return [(name, {"command": cmd, "ts": ts, "run_id": run}) for name, cmd, ts, run in specs]


def _row(decision, **kw):
    row = {
        "ts": "2026-10-24T10:05:00+00:00",
        "command": "insight",
        "decision": decision,
        "content_hash": "0123456789abcdef",
    }
    row.update(kw)
    return row


def test_snapshot_path_resolves_exactly():
    manifests = _manifests(("insight_X", "insight", "2026-10-24T10:00:00Z", "r1"))
    how, name = sr.resolve_one(
        _row("staged", snapshot_path="snapshots/insight_X"), manifests, MINUTE
    )
    assert (how, name) == ("exact-path", "insight_X")


def test_run_id_resolves_when_there_is_no_snapshot_path():
    manifests = _manifests(("insight_X", "insight", "2026-10-24T10:00:00Z", "r1"))
    assert sr.resolve_one(_row("staged", run_id="r1"), manifests, MINUTE) == (
        "exact-run_id",
        "insight_X",
    )


def test_ts_neighbourhood_is_marked_inferred_and_needs_the_same_command():
    manifests = _manifests(("insight_X", "insight", "2026-10-24T10:05:30Z", None))
    assert sr.resolve_one(_row("staged"), manifests, MINUTE) == ("inferred-ts", "insight_X")
    other = _manifests(("distill_X", "distill", "2026-10-24T10:05:30Z", None))
    assert sr.resolve_one(_row("staged"), other, MINUTE)[0] == "rotated"


def test_nothing_in_reach_is_rotated_not_hidden():
    assert sr.resolve_one(_row("staged"), [], MINUTE) == ("rotated", None)


def test_an_adoption_follows_its_stage_row_to_the_snapshot():
    stage = _row("staged", snapshot_path="snapshots/insight_X", ts="2026-10-24T10:05:00+00:00")
    adopted = _row("approved", ts="2026-10-31T05:00:00+00:00")
    manifests = _manifests(("insight_X", "insight", "2026-10-24T10:00:00Z", "r1"))
    (result,) = sr.resolve_all([stage, adopted], manifests, neighbour=MINUTE)
    assert result[0] is adopted and result[1:] == ("exact-path", "insight_X")


def test_staged_rows_are_not_decisions():
    assert sr.resolve_all([_row("staged")], [], neighbour=MINUTE) == []


def test_cli_exit_codes(tmp_path):
    snaps = tmp_path / "snapshots"
    (snaps / "insight_X").mkdir(parents=True)
    (snaps / "insight_X" / "manifest.json").write_text(
        json.dumps({"command": "insight", "ts": "2026-10-24T10:00:00Z", "run_id": "r1"})
    )
    decisions = tmp_path / "d.jsonl"
    decisions.write_text(json.dumps(_row("approved", run_id="r1")) + "\n")

    def run(*extra):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--decisions",
                str(decisions),
                "--snapshots",
                str(snaps),
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    ok = run("--require-resolved")
    assert ok.returncode == 0 and "exact-run_id 1" in ok.stdout
    decisions.write_text(
        json.dumps(_row("approved", run_id="nope", ts="2020-01-01T00:00:00Z")) + "\n"
    )
    assert run().returncode == 0
    assert run("--require-resolved").returncode == 1
    assert (
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--decisions",
                str(tmp_path / "x"),
                "--snapshots",
                str(snaps),
            ],
            capture_output=True,
        ).returncode
        == 2
    )


@pytest.mark.skipif(not (DATA_REPO / "snapshots").is_dir(), reason="sibling data repo not present")
def test_the_public_manifests_of_the_sibling_data_repo_load():
    manifests = sr.load_manifests(DATA_REPO / "snapshots")
    assert manifests, "the public snapshots carry manifests"
    assert all("command" in m for _, m in manifests)
