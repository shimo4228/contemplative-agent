"""Layer-1 exit guard and the chain's `--archive-names` call guard (ADR-0122)."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import layer1_exit_guard as g  # noqa: E402  # pyright: ignore[reportMissingImports]


def _row(ts: str, source: str, name: str, decision: str = "approved") -> dict:
    return {"ts": ts, "decision": decision, "source": source, "path": f"/h/skills/.archive/{name}"}


AS_OF = datetime(2026, 12, 1, tzinfo=timezone.utc)


@pytest.mark.unit
def test_counts_split_by_layer_and_ignore_rejected() -> None:
    recs = [
        _row("2026-11-30T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-11-30T05:00:01Z", "stage-archived-names", "b.md"),
        _row("2026-11-30T05:00:02Z", "direct-archive-auto", "c.md"),
        _row("2026-11-30T05:00:03Z", "archive-l1-unattended", "d.md", decision="rejected"),
        _row("2026-11-30T06:00:00Z", "direct-restore", "b.md"),
    ]
    r = g.build_reading(recs, AS_OF)
    assert r["week"] == {"skills_archived_l1": 1, "skills_archived_l2": 2, "restored": 1}
    assert r["halted"] is False


@pytest.mark.unit
def test_two_layer1_restores_within_four_weeks_halt() -> None:
    recs = [
        _row("2026-11-01T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-11-02T05:00:00Z", "archive-l1-unattended", "b-2.md"),
        _row("2026-11-20T05:00:00Z", "direct-restore", "a.md"),
        _row("2026-11-21T05:00:00Z", "direct-restore", "b.md"),
    ]
    r = g.build_reading(recs, AS_OF)
    assert r["halted"] is True and len(r["layer1_restores_in_window"]) == 2


@pytest.mark.unit
def test_restore_after_the_window_or_of_a_human_archive_does_not_count() -> None:
    recs = [
        _row("2026-09-01T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-11-20T05:00:00Z", "direct-restore", "a.md"),  # 80 days later
        _row("2026-11-01T05:00:00Z", "stage-archived-names", "b.md"),  # layer 2
        _row("2026-11-02T05:00:00Z", "direct-restore", "b.md"),
    ]
    assert g.layer1_restores(recs) == []


@pytest.mark.unit
def test_one_restore_cannot_pay_two_archives() -> None:
    recs = [
        _row("2026-11-01T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-11-03T05:00:00Z", "archive-l1-unattended", "a-2.md"),
        _row("2026-11-05T05:00:00Z", "direct-restore", "a.md"),
    ]
    assert len(g.layer1_restores(recs)) == 1


@pytest.mark.unit
def test_require_live_exits_3_when_halted(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    import json

    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                _row("2026-11-01T05:00:00Z", "archive-l1-unattended", "a.md"),
                _row("2026-11-02T05:00:00Z", "archive-l1-unattended", "b.md"),
                _row("2026-11-03T05:00:00Z", "direct-restore", "a.md"),
                _row("2026-11-04T05:00:00Z", "direct-restore", "b.md"),
            ]
        ),
        encoding="utf-8",
    )
    assert g.main(["--audit", str(audit), "--as-of", "2026-12-01", "--require-live"]) == 3
    assert g.main(["--audit", str(audit), "--as-of", "2026-12-01"]) == 0
    assert g.main(["--audit", str(tmp_path / "none"), "--as-of", "2026-12-01"]) == 0


@pytest.mark.unit
def test_the_chain_calls_archive_names_only_with_the_layer1_source() -> None:
    """ADR-0122: a human's `--archive-names` is the gate's; the unattended chain may
    call it only with the layer-1 source flag, and (today) not at all."""
    text = (ROOT / "scripts" / "weekly-pipeline.sh").read_text(encoding="utf-8")
    # Join shell line continuations so a command is one logical line.
    logical = re.sub(r"\\\n\s*", " ", text)
    offenders = [
        ln.strip()
        for ln in logical.splitlines()
        if "--archive-names" in ln
        and not ln.lstrip().startswith("#")
        and "archive-l1-unattended" not in ln.split(" #")[0]
    ]
    assert offenders == []


@pytest.mark.unit
def test_consecutive_weekly_readings_do_not_double_count_the_as_of_day() -> None:
    recs = [_row("2026-12-01T05:00:00Z", "archive-l1-unattended", "a.md")]
    first = g.build_reading(recs, AS_OF)
    second = g.build_reading(recs, datetime(2026, 12, 8, tzinfo=timezone.utc))
    assert first["week"]["skills_archived_l1"] == 1
    assert second["week"]["skills_archived_l1"] == 0


@pytest.mark.unit
def test_reenable_row_clears_halted_but_new_restores_halt_again() -> None:
    recs = [
        _row("2026-11-01T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-11-02T05:00:00Z", "archive-l1-unattended", "b.md"),
        _row("2026-11-20T05:00:00Z", "direct-restore", "a.md"),
        _row("2026-11-21T05:00:00Z", "direct-restore", "b.md"),
    ]
    assert g.build_reading(recs, AS_OF)["halted"] is True
    recs.append(_row("2026-11-25T00:00:00Z", "layer1-reenable", "-"))
    r = g.build_reading(recs, AS_OF)
    assert r["halted"] is False and r["reenabled_at"].startswith("2026-11-25")
    recs += [
        _row("2026-11-26T05:00:00Z", "archive-l1-unattended", "c.md"),
        _row("2026-11-27T05:00:00Z", "archive-l1-unattended", "d.md"),
        _row("2026-11-28T05:00:00Z", "direct-restore", "c.md"),
        _row("2026-11-29T05:00:00Z", "direct-restore", "d.md"),
    ]
    assert g.build_reading(recs, AS_OF)["halted"] is True


@pytest.mark.unit
def test_rows_after_the_as_of_day_are_ignored() -> None:
    recs = [
        _row("2026-11-01T05:00:00Z", "archive-l1-unattended", "a.md"),
        _row("2026-12-05T05:00:00Z", "direct-restore", "a.md"),
    ]
    r = g.build_reading(recs, AS_OF)
    assert r["total"]["restored"] == 0
