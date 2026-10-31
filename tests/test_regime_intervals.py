"""Regime boundary table and its derived readings (P3-02.1 / .3 / .7).

`docs/evidence/regimes/regimes.json` is the one source of the apparatus
boundaries; the data repo's `pipeline/regimes.json` is a copy made by the sync
(rsync --delete would erase a hand-placed file). These cases pin the contract
the readers rely on: every row names what it affects, the vocabulary is closed,
the value-layer rows agree with the P2-05.7 change series, and the derived
tables behave on a fixture.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REGIMES = REPO_ROOT / "docs" / "evidence" / "regimes" / "regimes.json"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import knowledge_longitudinal_reading as klr  # noqa: E402  # pyright: ignore[reportMissingImports]
import manifest_key_generations as mkg  # noqa: E402  # pyright: ignore[reportMissingImports]
import regime_intervals as ri  # noqa: E402  # pyright: ignore[reportMissingImports]

# The ten change rows value_layer_change_series.py gives on the public snapshots of
# 2026-10-23 (kind, sha_before, sha_after, ts_to). Pinned here so the table cannot
# drift away from the series without a red test.
SERIES_ROWS = [
    ("skills", "4b703749f52e", "edb78c37338e", "2026-08-08T18:30:03Z"),
    ("constitution", "752c85503be8", "5154112a5df1", "2026-08-09T18:30:07Z"),
    ("skills", "edb78c37338e", "483c7025e147", "2026-08-15T04:02:49Z"),
    ("identity", "151e91304927", "4003cf001aca", "2026-08-15T04:17:08Z"),
    ("skills", "483c7025e147", "03850a575075", "2026-08-15T06:29:27Z"),
    ("skills", "03850a575075", "25ffde5fad6b", "2026-08-22T18:30:06Z"),
    ("skills", "25ffde5fad6b", "f999f8343388", "2026-09-12T01:26:32Z"),
    ("identity", "4003cf001aca", "40c36303e336", "2026-09-12T18:30:00Z"),
    ("skills", "f999f8343388", "42f3cd4302e3", "2026-09-19T18:30:01Z"),
    ("identity", "40c36303e336", "e409a8d0c870", "2026-10-10T18:30:05Z"),
]


def _changes() -> dict:
    return {
        "changes": [
            {"kind": k, "sha_before": b, "sha_after": a, "ts_to": ts} for k, b, a, ts in SERIES_ROWS
        ]
    }


def test_real_table_is_valid_and_every_row_has_affects():
    doc = ri.load_regimes(REGIMES)
    assert len(doc["regimes"]) >= 22
    for r in doc["regimes"]:
        assert r["affects"] and set(r["affects"]) <= set(ri.SERIES)


def test_roadmap_dates_are_present():
    dates = {r["date"] for r in ri.load_regimes(REGIMES)["regimes"]}
    for d in (
        "2026-03-27",
        "2026-04-16",
        "2026-05-05",
        "2026-06-17",
        "2026-06-23",
        "2026-06-28",
        "2026-07-03",
        "2026-07-12",
        "2026-07-18",
        "2026-07-26",
        "2026-08-09",
        "2026-08-16",
        "2026-08-29",
        "2026-08-15",
        "2026-08-22",
        "2026-08-28",
        "2026-09-06",
        "2026-09-11",
        "2026-09-12",
        "2026-09-19",
        "2026-09-20",
        "2026-09-28",
        "2026-10-07",
    ):
        assert d in dates, d


def test_two_ollama_versions_and_an_unknown_period():
    doc = ri.load_regimes(REGIMES)
    ollama = sorted(
        (r for r in ri.sorted_rows(doc) if r.get("serving_change", {}).get("ollama_version")),
        key=lambda r: r["date"],
    )
    # P3-02.7: at least two Ollama rows, the 2026-06-28 upgrade recovered from the
    # owner's machine and the 2026-09-20 one seen in the public manifests
    assert [r["serving_change"]["ollama_version"] for r in ollama] == [
        ["0.17.7", "0.30.11"],
        ["0.30.11", "0.34.2"],
    ]
    history = doc["serving_history"]
    versions = [h["ollama_version"] for h in history]
    assert versions[0] == "unknown" and versions[1:] == ["0.30.11", "0.34.2"]
    # the spans tile the record without a gap
    for a, b in zip(history, history[1:], strict=False):
        assert dt.date.fromisoformat(a["to"]) + dt.timedelta(days=1) == dt.date.fromisoformat(
            b["from"]
        )


def test_value_layer_rows_agree_with_the_change_series():
    doc = ri.load_regimes(REGIMES)
    assert ri.check_changes(doc, _changes()) == []


def test_check_changes_names_a_missing_row_and_a_stale_row():
    doc = ri.load_regimes(REGIMES)
    ch = _changes()
    ch["changes"].append(
        {"kind": "skills", "sha_before": "a", "sha_after": "b", "ts_to": "2026-11-01T00:00:00Z"}
    )
    del ch["changes"][0]
    problems = ri.check_changes(doc, ch)
    assert any("no regimes row for skills -> b" in p for p in problems)
    assert any("has no change row in the series" in p for p in problems)


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "regimes.json"
    p.write_text(json.dumps({"regimes": rows}), encoding="utf-8")
    return p


def _row(rid="R1", **kw):
    base = {
        "id": rid,
        "date": "2026-01-10",
        "status": "confirmed",
        "kind": "x",
        "change": "c",
        "affects": ["views"],
    }
    base.update(kw)
    return base


def test_unknown_series_and_empty_affects_are_rejected(tmp_path):
    with pytest.raises(ri.RegimeError, match="unknown series"):
        ri.load_regimes(_write(tmp_path, [_row(affects=["nope"])]))
    with pytest.raises(ri.RegimeError, match="affects is required"):
        ri.load_regimes(_write(tmp_path, [_row(affects=[])]))
    with pytest.raises(ri.RegimeError, match="duplicate"):
        ri.load_regimes(_write(tmp_path, [_row(), _row()]))
    assert ri.main(["--regimes", str(_write(tmp_path, [_row(affects=[])]))]) == 2


def test_stretches_split_on_boundaries_and_count_weekly_points():
    d = dt.date
    obs = [d(2026, 1, 1) + dt.timedelta(days=i) for i in range(0, 60)]  # daily, 60 days
    bnd = [(d(2026, 1, 20), "A"), (d(2026, 2, 3), "B")]
    ivs = ri.series_intervals("x", bnd, obs)
    assert [(i["from"], i["to"]) for i in ivs] == [
        ("2026-01-01", "2026-01-20"),
        ("2026-01-20", "2026-02-03"),
        ("2026-02-03", "2026-03-01"),
    ]
    assert ivs[0]["span_days"] == 19 and ivs[1]["span_days"] == 14
    assert ivs[0]["observations"] == 19  # the point on the boundary day belongs to the new stretch
    assert ivs[1]["closed_by"] == ["B"] and ivs[2]["opened_by"] == ["B"]
    assert ivs[1]["weekly_points"] == 3 and ivs[1]["within_series_ok"] is False
    assert ivs[2]["within_series_ok"] is True  # 4+ weekly points


def test_boundary_before_the_series_opens_the_first_stretch():
    d = dt.date
    ivs = ri.series_intervals("x", [(d(2025, 12, 1), "OLD")], [d(2026, 1, 5), d(2026, 1, 6)])
    assert ivs[0]["opened_by"] == ["OLD"] and len(ivs) == 1


def test_datacard_table_has_every_id_and_the_derived_tables_build(tmp_path):
    doc = ri.load_regimes(REGIMES)
    card = ri.render_datacard(doc)
    for r in doc["regimes"]:
        assert f"| {r['id']} |" in card
    result = ri.build(doc, None)  # no data repo: day spans only
    assert result["min_points"] == 4
    assert {s["series"] for s in result["summary"]} == set(ri.SERIES)


def test_build_reads_a_small_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "reports" / "comment-reports").mkdir(parents=True)
    for i in range(10):
        day = dt.date(2026, 3, 7) + dt.timedelta(days=i * 7)
        (repo / "reports" / "comment-reports" / f"comment-report-{day}.md").write_text("x")
    (repo / "knowledge.json").write_text(json.dumps([{"distilled": "2026-03-26T00:00+00:00"}]))
    doc = ri.load_regimes(REGIMES)
    result = ri.build(doc, repo)
    cr = [i for i in result["intervals"] if i["series"] == "comment-reports"]
    assert cr[0]["from"] == "2026-03-07" and cr[-1]["to"] == "2026-05-09"


def test_manifest_generations(tmp_path):
    snaps = tmp_path / "snapshots"
    base = {"command": "distill", "ts": "2026-08-01T00:00:00Z", "think": True}
    for name, extra, ts in (
        ("distill_20260801T000000Z", {}, "2026-08-01T00:00:00Z"),
        ("distill_20260802T000000Z", {"run_id": "r"}, "2026-08-02T00:00:00Z"),
        ("distill_20260803T000000Z", {"run_id": "r"}, "2026-08-03T00:00:00Z"),
    ):
        d = snaps / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({**base, **extra, "ts": ts}))
    gens = mkg.generations(snaps)
    assert [(g["n_keys"], g["manifests"], g["keys_added"]) for g in gens] == [
        (3, 1, ["command", "think", "ts"]),
        (4, 2, ["run_id"]),
    ]
    assert "T-MANIFEST-RUNID" in mkg.render(gens)


def test_manifest_generations_base_row_claims_no_origin(tmp_path):
    """Once the 14-key manifest rotates out, the oldest public set holds run_id; its
    row must not credit the run_id fix as if the generation had added it."""
    snaps = tmp_path / "snapshots"
    base = {"command": "distill", "run_id": "r", "think": True}
    for name, extra, ts in (
        ("distill_20261024T000000Z", {}, "2026-10-24T00:00:00Z"),
        ("distill_20261025T000000Z", {"manifest_schema": 1}, "2026-10-25T00:00:00Z"),
    ):
        d = snaps / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({**base, **extra, "ts": ts}))
    rows = mkg.render(mkg.generations(snaps)).splitlines()[2:]
    assert rows[0].endswith("| oldest published generation |")
    assert "P0-06.4" in rows[1]


def test_knowledge_reading_definitions():
    rows = klr.load_rows_from_list(
        [
            {"distilled": "2026-01-01T00:00+00:00", "valid_from": "2026-01-01T00:00+00:00"},
            {
                "distilled": "2026-01-10T00:00+00:00",
                "valid_from": "2026-01-10T00:00+00:00",
                "valid_until": "2026-02-01T00:00+00:00",
            },
            {"distilled": "2026-02-10T00:00+00:00", "valid_from": "2026-02-10T00:00+00:00"},
        ]
    )
    d = dt.date
    assert len(klr.active_indices(rows, d(2026, 1, 15))) == 2
    assert len(klr.active_indices(rows, d(2026, 2, 15))) == 2  # the second row ended 02-01
    t = klr.turnover(rows, d(2026, 2, 15), 42)
    assert t["active_now"] == 2 and t["active_then"] == 1  # then = 2026-01-04
    assert t["new_share"] == 0.5  # only the 02-10 row is inside (01-04, 02-15]
    assert t["retired_share"] == 0.0  # the one row active then is still active


def test_knowledge_reading_cosine_and_missing_embeddings():
    np = pytest.importorskip("numpy")
    vecs = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    got = klr.mean_pairwise_cosine(vecs, [0, 1, 2], 10, 0)
    assert got["n"] == 3 and got["value"] == pytest.approx(1 / 3, abs=1e-4)
    rows = klr.load_rows_from_list([{"distilled": "2026-01-01T00:00+00:00"}] * 2)
    res = klr.read(rows, [dt.date(2026, 1, 2)], 42, None, 10, 0)
    assert res["points"][0]["pairwise_cosine"]["reason"] == "no_embeddings_given"


def test_datacard_patch_carries_the_generated_tables():
    """The text handed to the owner for DATACARD.md must be the generators' output for the
    committed table, so a new row cannot land without the patch being regenerated."""
    patch = (REGIMES.parent / "datacard-patch.md").read_text(encoding="utf-8")
    assert ri.render_datacard(ri.load_regimes(REGIMES)) in patch
    assert (REGIMES.parent / "manifest-key-generations.md").read_text(encoding="utf-8") in patch
