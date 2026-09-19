"""RFC-0034: ``insight-novelty.jsonl`` has two writers, so records carry a kind.

The deferral record (``insight._append_deferral_audit``) and the judge record
(``insight_novelty._append_novelty_audit``) share exactly one key (``ts``) and
one file. Without a discriminator the replay reads a deferral row as a judge
row with verdict ``None`` — and its inventory-size guard reads the missing
``known_themes_count`` as a second regime and stops the whole run. A ``kind``
fixes both, the way ``skill_selection`` already does for its own log; absence
means the judge family, because every record written before this change is one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import novelty_replay_ab as nra  # noqa: E402  # pyright: ignore[reportMissingImports]

from contemplative_agent.core import insight_novelty as inov  # noqa: E402


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestBothWritersNameTheirFamily:
    def test_the_kind_constants_live_in_one_place(self):
        assert inov.NOVELTY_JUDGE_RECORD_KIND == "novelty_judge"
        assert inov.NOVELTY_DEFERRAL_RECORD_KIND == "review_budget_deferral"
        assert inov.NOVELTY_JUDGE_RECORD_KIND != inov.NOVELTY_DEFERRAL_RECORD_KIND

    def test_the_deferral_writer_emits_its_kind(self, tmp_path):
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        audit = tmp_path / "insight-novelty.jsonl"
        batches: list[inov._Batch] = [(f"cluster-{i}", ["p"], (f"p{i}",)) for i in range(1, 4)]
        _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-1", "cluster-2", "cluster-3"}),
            {},
            cap=1,
            audit_path=audit,
        )
        (rec,) = _records(audit)
        assert rec["kind"] == inov.NOVELTY_DEFERRAL_RECORD_KIND
        assert rec["reason"] == "review_budget_deferred"

    def test_the_judge_writer_emits_its_kind(self, tmp_path):
        audit = tmp_path / "insight-novelty.jsonl"
        inov._append_novelty_audit(
            audit,
            verdict="judged",
            batches=[("cluster-1", ["p"], ("p1",))],
            covered=set(),
            known_themes_count=2,
            inventory_count=5,
            known_selection={"mode": "full"},
            prompt="p",
            raw_output="{}",
            temperature=inov._NOVELTY_TEMPERATURE,
            batch_index=0,
            batch_count=1,
        )
        (rec,) = _records(audit)
        assert rec["kind"] == inov.NOVELTY_JUDGE_RECORD_KIND
        assert rec["verdict"] == "judged"


class TestTheReplayFiltersByKind:
    def _judge_row(self, **over) -> dict:
        rec = {
            "kind": inov.NOVELTY_JUDGE_RECORD_KIND,
            "ts": "2026-09-04T23:02:41+00:00",
            "verdict": "judged",
            "known_themes_count": 1,
            "inventory_count": 1,
            "batch_index": 0,
            "batch_count": 1,
            "clusters": ["cluster-1"],
            "covered": [],
        }
        rec.update(over)
        return rec

    def _deferral_row(self) -> dict:
        return {
            "kind": inov.NOVELTY_DEFERRAL_RECORD_KIND,
            "ts": "2026-09-04T23:05:00+00:00",
            "reason": "review_budget_deferred",
            "cap": 1,
            "deferred": [{"topic": "cluster-9", "size": 2, "pattern_ids": ["p9"]}],
        }

    def _log(self, tmp_path: Path, rows: list[dict]) -> Path:
        path = tmp_path / "insight-novelty.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        return path

    def test_a_deferral_row_is_not_a_verdict_and_not_a_second_regime(self, tmp_path, capsys):
        """Before the discriminator this raised: the deferral row has no
        ``known_themes_count``, so the inventory guard saw two regimes."""
        path = self._log(tmp_path, [self._judge_row(), self._deferral_row()])
        records = nra._records_for_run(path, "2026-09-04")
        assert [r["verdict"] for r in records] == ["judged"]
        # Dropped rows are named, never silently absent (ADR-0075).
        assert "1" in capsys.readouterr().err

    def test_a_record_without_a_kind_is_still_a_judge_record(self, tmp_path):
        legacy = self._judge_row()
        del legacy["kind"]
        path = self._log(tmp_path, [legacy])
        records = nra._records_for_run(path, "2026-09-04")
        assert len(records) == 1
        assert records[0]["verdict"] == "judged"

    def test_a_legacy_deferral_row_is_not_read_as_a_judge_record(self, tmp_path):
        """A kind-less row is not automatically a judge record: the deferral
        writer has been appending kind-less rows to this same file since the
        fail-open cap shipped, and one of them reaching the regime guard
        crashes it (``sorted({485, None})``) rather than stopping it cleanly
        (code review 2026-09-12)."""
        legacy_deferral = self._deferral_row()
        del legacy_deferral["kind"]
        path = self._log(tmp_path, [self._judge_row(), legacy_deferral])
        records = nra._records_for_run(path, "2026-09-04")
        assert [r["verdict"] for r in records] == ["judged"]
        assert not inov.is_novelty_judge_record(legacy_deferral)

    def test_verdicts_logged_no_longer_gains_a_none(self, tmp_path):
        path = self._log(
            tmp_path,
            [
                self._judge_row(prompt_b64=None),
                self._judge_row(verdict="fail_open_llm", batch_index=1),
                self._deferral_row(),
            ],
        )
        records = nra._records_for_run(path, "2026-09-04")
        verdicts = sorted({str(r.get("verdict")) for r in records})
        assert verdicts == ["fail_open_llm", "judged"]
        assert "None" not in verdicts
