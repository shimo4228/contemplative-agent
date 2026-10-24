"""scripts/third_party_overlap.py: counts third-party word spans, prints no text (P0-03.9)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "third_party_overlap", REPO_ROOT / "scripts" / "third_party_overlap.py"
)
assert spec and spec.loader
tpo = importlib.util.module_from_spec(spec)
sys.modules["third_party_overlap"] = tpo
spec.loader.exec_module(tpo)

SHARED = "the quick brown fox jumps over the lazy dog near the quiet river bank today"  # 15 words
ONLY_OURS = "we always check the registry before publishing any new skill candidate to staging"
SECRET_MARK = "zebra-marker-must-not-print"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "data"
    (repo / "reports" / "comment-reports").mkdir(parents=True)
    (repo / "reports" / "analysis").mkdir(parents=True)
    (repo / "snapshots" / "s1" / "skills").mkdir(parents=True)
    (repo / "snapshots" / "s2" / "skills").mkdir(parents=True)
    (repo / "reports" / "comment-reports" / "comment-report-2026-10-01.md").write_text(
        "# Report\n\n## Comments (1 total)\n\n"
        "### 1. [2026-10-01 03:00:00] COMMENT · with Alicebot · post abcd1234… · relevance 0.8\n\n"
        f"**Context:**\n\n{SHARED} {SECRET_MARK}\n\n"
        f"**Internal note:**\n\nreplying to Alicebot about {ONLY_OURS}\n\n"
        f"**Output:**\n\nthanks\n\n---\n",
        encoding="utf-8",
    )
    (repo / "knowledge.json").write_text(
        json.dumps(
            [
                {"pattern": f"agents say: {SHARED}", "distilled": "2026-10-02T00:00+00:00"},
                {"pattern": ONLY_OURS, "distilled": "2026-10-02T00:00+00:00"},
                {"pattern": "a short unrelated pattern", "distilled": "2026-09-02T00:00+00:00"},
            ]
        ),
        encoding="utf-8",
    )
    (repo / "reports" / "analysis" / "weekly-2026-10-02.md").write_text(
        f"# Week\n\n{SHARED}\n\n## Sample\n\n{SHARED}\n", encoding="utf-8"
    )
    (repo / "reports" / "analysis" / "weekly-2026-10-09.md").write_text(
        f"# Week\n\nnothing shared\n\n## Sample\n\n{SHARED}\n", encoding="utf-8"
    )
    # Identical skill bodies in two snapshots count once.
    for snap in ("s1", "s2"):
        (repo / "snapshots" / snap / "skills" / "a.md").write_text(SHARED, encoding="utf-8")
    return repo


def test_counts_by_series_and_n(tmp_path: Path) -> None:
    result = tpo.collect(_repo(tmp_path))
    assert result["inputs"]["skills_unique"] == 1
    assert result["inputs"]["entries"] == 1
    by_n = result["by_n"]
    assert by_n["8"]["patterns"] == 1 and by_n["8"]["patterns_by_month"] == {"2026-10": 1}
    assert by_n["12"]["patterns"] == 1
    assert by_n["20"]["patterns"] == 0  # SHARED is 15 words long
    assert by_n["8"]["weekly_files_any"] == 2
    assert by_n["8"]["weekly_files_before_sample"] == 1
    assert by_n["8"]["skills"] == 1


def test_a_span_the_agent_also_wrote_is_not_counted(tmp_path: Path) -> None:
    result = tpo.collect(_repo(tmp_path))
    assert result["by_n"]["8"]["patterns"] == 1  # ONLY_OURS appears in our own note: not counted


def test_named_block_count(tmp_path: Path) -> None:
    result = tpo.collect(_repo(tmp_path))
    assert result["named_blocks"] == {"entries": 1, "naming_the_counterparty": 1}


def test_output_has_counts_and_no_text(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    out_json = tmp_path / "counts.json"
    assert tpo.main(["--data-repo", str(repo), "--json", str(out_json)]) == 0
    printed = capsys.readouterr().out
    assert "n=12" in printed
    assert SECRET_MARK not in printed and "quick brown" not in printed
    assert SECRET_MARK not in out_json.read_text(encoding="utf-8")


def test_a_missing_data_repo_is_an_error(tmp_path: Path) -> None:
    assert tpo.main(["--data-repo", str(tmp_path / "nope")]) == 2
