"""Pure parts of the RFC-0041 form A lab arm (P3-03.9). No model is called."""

import importlib.util
import json
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parent.parent / "scripts" / "rfc0041_slot_enum_lab.py"
_SPEC = importlib.util.spec_from_file_location("rfc0041_slot_enum_lab", _P)
lab = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lab)


def test_split_slots_accepts_a_complete_object_and_abstains_otherwise():
    def ok(p, **k):
        return json.dumps({"trigger": " t ", "move": "m", "noticed": "n"})

    assert lab.split_slots("x", ok, "P") == {"trigger": "t", "move": "m", "noticed": "n"}
    assert lab.split_slots("x", lambda p, **k: None, "P") is None
    assert lab.split_slots("x", lambda p, **k: "not json", "P") is None
    assert lab.split_slots("x", lambda p, **k: json.dumps({"trigger": "t"}), "P") is None


def test_split_slots_is_called_constrained_at_temperature_zero():
    seen = {}

    def gen(prompt, **kw):
        seen.update(kw)
        return json.dumps({"trigger": "", "move": "", "noticed": ""})

    lab.split_slots("x", gen, "P")
    assert seen["temperature"] == 0.0 and seen["format"] == lab.SLOT_SCHEMA


def test_ask_relation_rejects_values_outside_the_enum():
    assert lab.ask_relation("c", "n", lambda p, **k: json.dumps({"relation": "revises"}), "P") == "revises"
    assert lab.ask_relation("c", "n", lambda p, **k: json.dumps({"relation": "maybe"}), "P") is None
    assert lab.ask_relation("c", "n", lambda p, **k: "{", "P") is None


def test_separation_counts_pairs_by_theme_and_gap_sign():
    vecs = {"a1": [1, 0], "a2": [0.9, 0.1], "b1": [0, 1], "b2": [0.1, 0.9]}
    theme = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    same, dist = lab.pair_cosines(vecs, theme)
    assert len(same) == 2 and len(dist) == 4
    sep = lab.separation(same, dist)
    assert sep["gap"] > 0.5


def test_compare_arms_clears_only_beyond_two_se():
    raw = {"gap": 0.10, "gap_se": 0.02}
    assert lab.compare_arms(raw, {"gap": 0.20, "gap_se": 0.02})["cleared"] is True
    assert lab.compare_arms(raw, {"gap": 0.13, "gap_se": 0.02})["cleared"] is False


def test_enum_agreement_maps_labels_to_expected_relations_and_counts_abstains():
    rows = [
        ("gate_rejected", "same_as"), ("gate_rejected", "revises"), ("gate_rejected", "none"),
        ("gate_rejected", None), ("adopted_loo", "none"), ("adopted_loo", "same_as"),
    ]
    r = lab.enum_agreement(rows)
    assert r["counts"]["gate_rejected"] == {"hit": 2, "miss": 1, "abstain": 1}
    assert r["counts"]["adopted_loo"] == {"hit": 1, "miss": 1, "abstain": 0}
    assert r["balanced_accuracy"] == pytest.approx((2 / 3 + 1 / 2) / 2)


def test_enum_agreement_unknown_label_exits():
    with pytest.raises(SystemExit):
        lab.enum_agreement([("surprise", "none")])


def test_report_stage_joins_cached_stages_without_text(tmp_path):
    ids = ["a1", "a2", "b1", "b2"]
    vec = {"a1": [1, 0], "a2": [0.9, 0.1], "b1": [0, 1], "b2": [0.1, 0.9]}
    (tmp_path / "vectors.json").write_text(json.dumps({
        "ids": ids, "theme": {"a1": "A", "a2": "A", "b1": "B", "b2": "B"},
        "raw": [vec[i] for i in ids], "concat": [vec[i] for i in ids],
        "per_slot": {s: [vec[i] for i in ids] for s in lab.SLOTS},
        "repeat_cosine": [1.0, 0.999],
    }))
    (tmp_path / "enum.json").write_text(json.dumps([
        {"id": "p1", "label": "gate_rejected", "relation": "same_as"},
        {"id": "p2", "label": "adopted_loo", "relation": "none"},
    ]))
    out = tmp_path / "r.json"
    lab.main(["--stage", "report", "--work", str(tmp_path), "--out", str(out)])
    r = json.loads(out.read_text())
    assert r["separation"]["arms"]["raw"]["gap"] > 0.5
    assert r["enum"]["balanced_accuracy"] == 1.0
