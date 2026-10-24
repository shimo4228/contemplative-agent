"""scripts/comment_outcome_separation.py on synthetic windows (P1-04.5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import comment_outcome_separation as cos  # type: ignore[import-not-found]  # noqa: E402


def _window(since: str, until: str, skills: dict[str, tuple[int, int]],
            joined: int = 300, observed: int = 100) -> dict:
    return {
        "since": since, "until": until, "joined_publishes": joined,
        "observed_publishes": observed,
        "skills": [{"skill": k, "injected_comments": n, "comments_with_reply": r,
                    "replied_fraction": r / n} for k, (r, n) in skills.items()],
    }


def _write(tmp: Path, name: str, w: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(w), encoding="utf-8")
    return p


def test_flat_skills_do_not_separate():
    a = _window("2026-09-12", "2026-10-02", {"s1": (10, 40), "s2": (11, 40), "s3": (9, 40)})
    b = _window("2026-10-03", "2026-10-23", {"s1": (12, 40), "s2": (10, 40), "s3": (11, 40)})
    res = cos.analyse([a, b])
    assert res["separates"] is False
    assert res["chi_square"]["p"] > 0.5
    assert res["permutation"]["p"] > 0.5


def test_wide_gap_with_disjoint_wilson_separates_and_pools_windows():
    a = _window("2026-09-12", "2026-10-02", {"hi": (30, 50), "lo": (5, 50), "mid": (15, 50)})
    b = _window("2026-10-03", "2026-10-23", {"hi": (28, 50), "lo": (6, 50)})
    res = cos.analyse([a, b])
    assert res["separates"] is True
    pooled = {r["skill"]: (r["replied"], r["n"]) for r in res["table"]}
    assert pooled["hi"] == (58, 100) and pooled["lo"] == (11, 100)
    assert res["max_gap_pair"]["high"] == "hi" and res["max_gap_pair"]["low"] == "lo"
    assert res["chi_square"]["p"] < 0.001
    assert res["permutation"]["p"] < 0.01


def test_gap_without_disjoint_intervals_or_small_n_does_not_qualify():
    # gap 0.5 but n=10 each: Wilson intervals overlap.
    res = cos.analyse([_window("a", "b", {"x": (8, 10), "y": (3, 10)})])
    assert res["max_gap_pair"]["gap"] >= 0.2
    assert res["max_gap_pair"]["wilson_disjoint"] is False
    assert res["separates"] is False
    # n below MIN_N: counted, no interval, not eligible.
    res2 = cos.analyse([_window("a", "b", {"x": (4, 4), "y": (0, 4)})])
    assert res2["eligible_skills"] == 0 and res2["separates"] is False
    assert res2["table"][0]["wilson95"] is None


def test_first_output_line_is_observed_rate_fact():
    res = cos.analyse([_window("a", "b", {"x": (1, 20)}, joined=300, observed=100)])
    first = cos.render(res).splitlines()[0]
    assert first.startswith("observed 100 of 300 joined publishes (33.3%)")


def test_wilson_matches_shared_implementation():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import _stats  # type: ignore[import-not-found]
    lo, hi = cos.wilson(7, 30)
    assert [round(lo, 4), round(hi, 4)] == _stats.wilson_ci(7, 30)
    assert cos.wilson(0, 0) is None and cos.wilson(5, 3) is None


def test_chi2_sf_reference_values():
    assert abs(cos._chi2_sf(3.841459, 1) - 0.05) < 1e-4
    assert abs(cos._chi2_sf(5.991465, 2) - 0.05) < 1e-4
    assert abs(cos._chi2_sf(18.307, 10) - 0.05) < 1e-3


def test_accepts_renamed_rate_key_and_abstains_on_bad_input(tmp_path, capsys):
    w = _window("a", "b", {"x": (3, 20), "y": (9, 20)})
    for s in w["skills"]:
        s["reply_rate"] = s.pop("replied_fraction")  # pre-2026-10-24 key
    p = _write(tmp_path, "w.json", w)
    assert cos.main(["--window", str(p)]) == 0
    assert capsys.readouterr().out.splitlines()[0].startswith("observed")
    assert cos.main([]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert cos.main(["--window", str(bad)]) == 2
    assert "WINDOW_UNREADABLE" in capsys.readouterr().err
