"""P2-06.2: the staged-item axes table is a join with no composite and no write."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "staged_item_axes.py"


def _home(tmp: Path) -> Path:
    home = tmp / "home"
    (home / ".staged").mkdir(parents=True)
    (home / "logs").mkdir()
    meta = {
        "target": "x",
        "command": "insight",
        "seq": 1,
        "topic": "naming the frame",
        "nearest": ["ask-first", "cite-source", "a|b`c"],
        "surprise": {
            "rank": 2,
            "of": 9,
            "s_mean": 0.31234,
            "s_nn": 0.1,
            "ref_k": 5,
            "ref_cos_p50": 0.5,
            "ref_cos_spread": 0.1,
        },
        "stages": {
            "naming_kind": "new",
            "naming_fail": None,
            "duplicate_verdict": None,
            "duplicate_fail": "llm_none",
            "novelty_fail_open": False,
        },
    }
    (home / ".staged" / "cand.md.meta.json").write_text(json.dumps(meta))
    (home / ".staged" / "cand.md").write_text("# cand\n")
    (home / ".staged" / "broken.md.meta.json").write_text("{")
    old = {
        "kind": "novelty_judge",
        "ts": "2026-10-03T00:00:00",
        "verdict": "fail_open_llm",
        "clusters": ["naming the frame"],
        "covered": [],
    }
    new = {
        "kind": "novelty_judge",
        "ts": "2026-10-10T00:00:00",
        "verdict": "judged",
        "clusters": ["naming the frame", "other"],
        "covered": ["other"],
    }
    deferral = {
        "ts": "2026-10-11T00:00:00",
        "reason": "review_budget_deferred",
        "clusters": ["naming the frame"],
    }
    (home / "logs" / "insight-novelty.jsonl").write_text(
        "\n".join(json.dumps(r) for r in (old, new, deferral)) + "\n"
    )
    return home


def _digest(home: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(home.rglob("*")):
        if p.is_file():
            h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()


def test_each_axis_is_its_own_column_and_nothing_is_written(tmp_path):
    home = _home(tmp_path)
    before = _digest(home)
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--home", str(home)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert _digest(home) == before
    rows = [ln for ln in proc.stdout.splitlines() if ln.startswith("| ") and "cand.md" in ln]
    assert len(rows) == 1
    cells = [c.strip() for c in rows[0].strip("|").split("|")]
    assert cells[0] == "cand.md.meta.json"
    assert cells[1] == "rank 2/9, s_mean=0.3123"
    assert cells[2] == "naming=new duplicate=unjudged(llm_none)"
    # latest judge record wins; the deferral row (kind-less) is not a verdict
    assert cells[3] == "judged"
    assert cells[4] == "ask-first, cite-source, a/b'c"
    assert len(cells) == 5  # no reply-rate column (ADR-0106 note 2026-10-31)
    assert "broken.md.meta.json | sidecar unreadable" in proc.stdout


def test_no_composite_vocabulary():
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for word in ("composite_score", "weighted", "total_score"):
        assert word not in text


def test_missing_staged_dir_abstains(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--home", str(tmp_path)], capture_output=True, text=True
    )
    assert proc.returncode == 2
    assert "reason=STAGED_AXES_NO_STAGED_DIR" in proc.stderr


def test_empty_staging_is_a_plain_line(tmp_path):
    (tmp_path / ".staged").mkdir()
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--home", str(tmp_path)], capture_output=True, text=True
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "No staged items."
