"""Golden dataset loader contract (evals/dataset.py).

Deterministic core of the eval layer (ADR-0089): must be importable and
testable with the dev dependency group only — no deepeval import anywhere
on this path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.dataset import AXIOMS, KINDS, DatasetError, GoldenCase, dataset_sha256, load_dataset


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
    return path


def _valid_record(**overrides) -> dict:
    rec = {
        "id": "emptiness-1",
        "axiom": "Emptiness",
        "kind": "normal",
        "post": "I held a belief about permanence today.",
    }
    rec.update(overrides)
    return rec


class TestLoadDataset:
    def test_loads_valid_records_in_order(self, tmp_path):
        path = _write_jsonl(
            tmp_path / "golden.jsonl",
            [
                _valid_record(),
                _valid_record(id="mindfulness-1", axiom="Mindfulness", kind="edge"),
            ],
        )
        cases = load_dataset(path)
        assert [c.id for c in cases] == ["emptiness-1", "mindfulness-1"]
        assert isinstance(cases[0], GoldenCase)
        assert cases[1].kind == "edge"

    def test_skips_blank_lines(self, tmp_path):
        path = tmp_path / "golden.jsonl"
        path.write_text(json.dumps(_valid_record()) + "\n\n\n")
        assert len(load_dataset(path)) == 1

    def test_rejects_duplicate_id(self, tmp_path):
        path = _write_jsonl(tmp_path / "g.jsonl", [_valid_record(), _valid_record()])
        with pytest.raises(DatasetError, match="duplicate"):
            load_dataset(path)

    @pytest.mark.parametrize("missing", ["id", "axiom", "kind", "post"])
    def test_rejects_missing_key(self, tmp_path, missing):
        rec = _valid_record()
        del rec[missing]
        path = _write_jsonl(tmp_path / "g.jsonl", [rec])
        with pytest.raises(DatasetError, match=missing):
            load_dataset(path)

    def test_rejects_unknown_axiom(self, tmp_path):
        path = _write_jsonl(tmp_path / "g.jsonl", [_valid_record(axiom="Diligence")])
        with pytest.raises(DatasetError, match="axiom"):
            load_dataset(path)

    def test_rejects_unknown_kind(self, tmp_path):
        path = _write_jsonl(tmp_path / "g.jsonl", [_valid_record(kind="tricky")])
        with pytest.raises(DatasetError, match="kind"):
            load_dataset(path)

    def test_rejects_empty_post(self, tmp_path):
        path = _write_jsonl(tmp_path / "g.jsonl", [_valid_record(post="  ")])
        with pytest.raises(DatasetError, match="post"):
            load_dataset(path)

    def test_rejects_invalid_json_line(self, tmp_path):
        path = tmp_path / "g.jsonl"
        path.write_text('{"id": broken\n')
        with pytest.raises(DatasetError, match="line 1"):
            load_dataset(path)

    def test_vocabulary_is_closed(self):
        assert AXIOMS == frozenset({"Emptiness", "Non-Duality", "Mindfulness", "Boundless Care"})
        assert KINDS == frozenset({"normal", "edge", "adversarial"})


class TestDatasetSha256:
    def test_stable_and_content_sensitive(self, tmp_path):
        p1 = _write_jsonl(tmp_path / "a.jsonl", [_valid_record()])
        p2 = _write_jsonl(tmp_path / "b.jsonl", [_valid_record()])
        p3 = _write_jsonl(tmp_path / "c.jsonl", [_valid_record(post="different")])
        assert dataset_sha256(p1) == dataset_sha256(p2)
        assert dataset_sha256(p1) != dataset_sha256(p3)
