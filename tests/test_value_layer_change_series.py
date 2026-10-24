"""Tests for scripts/value_layer_change_series.py (P2-05.7).

Fixture: three snapshots. Between the first two the identity and one skill
change; between the second and third a skill file is added and one removed and
the serving environment moves. The script must put the boundaries exactly there.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import value_layer_change_series as vl  # noqa: E402  # pyright: ignore[reportMissingImports]


def _snap(
    root: Path,
    name: str,
    ts: str,
    *,
    identity: str,
    skills: dict[str, str],
    constitution: str = "c",
    serving: dict | None = None,
) -> Path:
    d = root / name
    (d / "constitution").mkdir(parents=True)
    (d / "rules").mkdir()
    (d / "skills").mkdir()
    (d / "identity.md").write_text(identity)
    (d / "constitution" / "a.md").write_text(constitution)
    (d / "rules" / "r.md").write_text("rule")
    for stem, body in skills.items():
        (d / "skills" / f"{stem}.md").write_text(body)
    manifest = {"command": "distill", "ts": ts, **(serving or {})}
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def _fixture(root: Path) -> None:
    env = {
        "ollama_version": "0.30.11",
        "generation_model_digest": "g1",
        "embedding_model_digest": "e1",
    }
    _snap(
        root,
        "distill_20260801T000000000000Z",
        "2026-08-01T00:00:00Z",
        identity="id1",
        skills={"a": "A", "b": "B"},
        serving=env,
    )
    _snap(
        root,
        "distill_20260802T000000000000Z",
        "2026-08-02T00:00:00Z",
        identity="id2",
        skills={"a": "A", "b": "B2"},
        serving=env,
    )
    _snap(
        root,
        "distill_20260803T000000000000Z",
        "2026-08-03T00:00:00Z",
        identity="id2",
        skills={"a": "A", "c": "C"},
        serving={**env, "ollama_version": "0.34.2"},
    )


def test_boundaries_match_fixture(tmp_path: Path) -> None:
    _fixture(tmp_path)
    doc, candidates = vl.build(tmp_path)
    rows = {(r["kind"], r["to_snapshot"].split("_")[1][:9]): r for r in doc["changes"]}
    assert set(rows) == {
        ("identity", "20260802T"),
        ("skills", "20260802T"),
        ("skills", "20260803T"),
    }
    ident = rows[("identity", "20260802T")]
    assert ident["sha_before"] != ident["sha_after"]
    assert len(ident["sha_before"]) == 12
    assert ident["files_added"] == [] and ident["files_removed"] == []
    last = rows[("skills", "20260803T")]
    assert last["files_added"] == ["c.md"]
    assert last["files_removed"] == ["b.md"]
    assert doc["coverage"] == {
        "snapshots": 3,
        "first_ts": "2026-08-01T00:00:00Z",
        "last_ts": "2026-08-03T00:00:00Z",
    }
    # constitution and rules never changed: no row
    assert not [r for r in doc["changes"] if r["kind"] in ("constitution", "rules")]


def test_serving_env_change_yields_one_candidate(tmp_path: Path) -> None:
    _fixture(tmp_path)
    _doc, candidates = vl.build(tmp_path)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["kind"] == "serving_env" and c["status"] == "candidate"
    assert c["changed"] == {"ollama_version": ["0.30.11", "0.34.2"]}
    assert c["to_snapshot"].startswith("distill_20260803")


def test_absent_serving_keys_are_not_a_change(tmp_path: Path) -> None:
    _snap(
        tmp_path, "distill_20260801T000000000000Z", "2026-08-01T00:00:00Z", identity="i", skills={}
    )
    _snap(
        tmp_path,
        "distill_20260802T000000000000Z",
        "2026-08-02T00:00:00Z",
        identity="i",
        skills={},
        serving={"ollama_version": "0.34.2"},
    )
    _doc, candidates = vl.build(tmp_path)
    assert candidates == []


def test_dir_without_manifest_is_skipped(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "distill_20260804T000000000000Z").mkdir()
    doc, _ = vl.build(tmp_path)
    assert doc["coverage"]["snapshots"] == 3


def test_cli_writes_outputs_and_never_regimes(tmp_path: Path) -> None:
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    _fixture(snaps)
    out = tmp_path / "pipeline" / "value-layer" / "changes.json"
    cand = tmp_path / "pipeline" / "value-layer" / "regime-candidates.json"
    res = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "value_layer_change_series.py"),
            str(snaps),
            "--out",
            str(out),
            "--candidates-out",
            str(cand),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert len(json.loads(out.read_text())["changes"]) == 3
    assert len(json.loads(cand.read_text())) == 1
    assert not (tmp_path / "pipeline" / "regimes.json").exists()


def test_missing_dir_is_an_error(tmp_path: Path) -> None:
    res = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "value_layer_change_series.py"),
            str(tmp_path / "nope"),
            "--out",
            str(tmp_path / "o.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1 and "ERROR" in res.stderr
