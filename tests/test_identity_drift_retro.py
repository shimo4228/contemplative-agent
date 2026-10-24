"""P3-04.8 / P3-04.9: the retroactive series and the floor / null-pair tables."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "identity_drift_retro.py"
spec = importlib.util.spec_from_file_location("identity_drift_retro", SCRIPT)
retro = importlib.util.module_from_spec(spec)
sys.modules["identity_drift_retro"] = retro
spec.loader.exec_module(retro)


def _embed_by_length(texts):
    # deterministic fake: a 2-D vector from the text length
    return np.array([[1.0, float(len(t))] for t in texts])


def _identity(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name / "identity.md"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    return path


def test_collect_versions_dedups_and_orders(tmp_path):
    snaps = tmp_path / "snaps"
    for name, body in (
        ("distill_20260101T000000Z", "A one."),
        ("distill_20260102T000000Z", "A one."),
        ("insight_20260103T000000Z", "B two."),
    ):
        d = snaps / name
        d.mkdir(parents=True)
        (d / "identity.md").write_text(body)
    cur = tmp_path / "identity.md"
    cur.write_text("C three.")
    got = retro.collect_versions(snaps, cur, [])
    assert [t for _, t in got] == ["A one.", "B two.", "C three."]


def test_table_shows_counts_without_interval_below_ten_sentences():
    rows = [
        retro.measure_identity_drift(
            "I am fluid. Two.", "Tension here. Other.", embed=retro._no_embed
        )
    ]
    out = retro.table(rows, [("a", "I am fluid. Two."), ("b", "Tension here. Other.")])
    assert "0/2" in out and "[" not in out.split("\n")[2]
    assert "n/a (not embedded)" in out


def test_fmt_adds_a_wilson_interval_only_from_ten():
    assert retro._fmt(3, 9) == "3/9"
    assert retro._fmt(3, 10).startswith("3/10 [")


def test_anchor_table_has_one_row_per_template_with_length_ratio(tmp_path):
    t1 = _identity(tmp_path, "stoic", "x" * 50)
    t2 = _identity(tmp_path, "cynic", "y" * 200)
    out = retro.anchor_table("z" * 100, [t1, t2], _embed_by_length)
    assert out.count("\n") == 4
    assert "| stoic | 50 |" in out and "0.50" in out and "2.00" in out


def test_null_pair_table_lists_every_pair(tmp_path):
    runs = [tmp_path / f"r{i}.md" for i in range(3)]
    for i, p in enumerate(runs):
        p.write_text("w" * (10 + i))
    out = retro.null_pair_table(runs, _embed_by_length)
    assert len(out.strip().splitlines()) == 2 + 3  # header, rule, 3 pairs
    assert retro.null_pair_table(runs, retro._no_embed).count("n/a (embed_unavailable)") == 3
