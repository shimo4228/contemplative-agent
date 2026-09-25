# pyright: reportPrivateUsage=false
"""The relevance face's label-once asset (scripts/relevance_label_set.py, RFC-0046 / RFC-0047 §3).

Pinned: ``sample`` dedupes by post_id, keeps only answered live-scored rows
since the switch, stratifies across the live gate (the rejected side
included), writes b64 rows + a manifest of shas, and refuses to write a
partial set (exit 2); output outside ``.notes/`` is refused; ``label
--dry-run`` calls nothing and prices the run, a real run goes through
``run_claude_raw`` only and refuses a stale set; ``score`` follows the
``evals/compare.py`` exit contract (0 / 1 / 2); ``check`` lists stale pins.
No decoded post text reaches stdout, the manifest or the summary.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "relevance_label_set.py"
SECRET = "a post body that must never be printed"
IDENTITY = "I am an agent concerned with contemplative AI alignment and local models."


def _load():
    spec = importlib.util.spec_from_file_location("relevance_label_set", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["relevance_label_set"] = module
    spec.loader.exec_module(module)
    return module


ls = _load()


def _row(post_id, score, *, ts="2026-09-26T01:00:00+00:00", reason="answered", live="scored"):
    body = f"{SECRET} {post_id}"
    return {
        "ts": ts,
        "post_id": post_id,
        "live_score": score,
        "live_reason": live,
        "live_gate": score >= 0.8,
        "threshold_applied": 0.8,
        "decision_reason": reason,
        "decision_p_top": 0.5,
        "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "content_b64": base64.b64encode(body.encode()).decode(),
    }


def _home(tmp_path: Path, rows: list[dict]) -> Path:
    home = tmp_path / "home"
    (home / "logs").mkdir(parents=True)
    (home / "identity.md").write_text(IDENTITY, encoding="utf-8")
    (home / "logs" / "relevance-2026-09-26.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return home


SCORES = (0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def _population(count: int) -> list[dict]:
    return [_row(f"p{i:03d}", SCORES[i % len(SCORES)]) for i in range(count)]


def _sample(tmp_path, rows, *, n=10, since="2026-09-25T00:00:00Z", seed=7):
    home = _home(tmp_path, rows)
    notes = tmp_path / ".notes"
    out = notes / "labels" / "relevance" / "set"
    code = ls.main(
        [
            "sample",
            "--home",
            str(home),
            "--since",
            since,
            "--n",
            str(n),
            "--seed",
            str(seed),
            "--out",
            str(out),
        ],
        notes_root=notes,
    )
    return code, out, notes, home


class TestSample:
    def test_dedupe_filter_and_strata(self, tmp_path, capsys):
        rows = _population(40)
        rows.append(_row("p000", 0.1, ts="2026-09-26T05:00:00+00:00"))  # a later repeat
        rows.append(_row("x-old", 0.9, ts="2026-09-24T00:00:00+00:00"))  # before since
        rows.append(_row("x-abs", 0.9, reason="http_error"))  # not answered
        rows.append(_row("x-out", 0.0, live="llm_unavailable"))  # an outage event
        code, out, _notes, _home_ = _sample(tmp_path, rows, n=10)
        assert code == 0
        written = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        ids = [r["post_id"] for r in written]
        assert len(ids) == len(set(ids)) == 10
        assert not any(pid.startswith("x-") for pid in ids)
        # Both sides of the live gate, the rejected side included.
        assert any(r["live_score"] < 0.8 for r in written)
        assert any(r["live_score"] >= 0.8 for r in written)
        assert len({r["stratum"] for r in written}) == 5
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["rows"] == 10
        assert manifest["population"] == 40
        assert manifest["seed"] == 7
        assert manifest["identity_sha256"] == hashlib.sha256(IDENTITY.encode()).hexdigest()
        assert manifest["relevance_score4_sha256"] and manifest["relevance_sha256"]
        assert manifest["since"] == "2026-09-25T00:00:00+00:00"
        text = (out / "rows.jsonl").read_text() + (out / "manifest.json").read_text()
        assert SECRET not in text + capsys.readouterr().out

    def test_the_seed_fixes_the_draw(self, tmp_path):
        _code, out_a, _n, _h = _sample(tmp_path / "a", _population(40), seed=3)
        _code, out_b, _n, _h = _sample(tmp_path / "b", _population(40), seed=3)
        assert (out_a / "rows.jsonl").read_text() == (out_b / "rows.jsonl").read_text()

    def test_short_population_writes_nothing_and_exits_2(self, tmp_path, capsys):
        code, out, _notes, _home_ = _sample(tmp_path, _population(6), n=10)
        assert code == 2
        assert "6 行、不足" in capsys.readouterr().out
        assert not out.exists()

    def test_output_outside_notes_is_refused(self, tmp_path):
        home = _home(tmp_path, _population(20))
        with pytest.raises(SystemExit, match="outside"):
            ls.main(
                [
                    "sample",
                    "--home",
                    str(home),
                    "--since",
                    "2026-09-25T00:00:00Z",
                    "--n",
                    "5",
                    "--seed",
                    "1",
                    "--out",
                    str(tmp_path / "public"),
                ],
                notes_root=tmp_path / ".notes",
            )


class TestLabel:
    def test_dry_run_prices_and_calls_nothing(self, tmp_path, capsys):
        _code, out, notes, _home_ = _sample(tmp_path, _population(40), n=10)
        capsys.readouterr()
        with patch("evals.judging.run_claude_raw") as raw:
            code = ls.main(["label", "--dir", str(out), "--dry-run"], notes_root=notes)
        assert code == 0
        raw.assert_not_called()
        printed = capsys.readouterr().out
        assert "10 row(s) to label with claude-opus-5" in printed
        assert "$1.30〜$1.60" in printed
        assert SECRET not in printed
        assert not (out / "labels.jsonl").exists()

    def test_a_run_goes_through_run_claude_raw_and_resumes(self, tmp_path):
        _code, out, notes, _home_ = _sample(tmp_path, _population(40), n=10)
        answers = iter(["3", "0"] * 5)
        with patch(
            "evals.judging.run_claude_raw", side_effect=lambda *a, **k: next(answers)
        ) as raw:
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 0
            assert raw.call_count == 10
            prompt = raw.call_args.args[0]
            assert "directly on-topic" in prompt
            assert raw.call_args.kwargs["model"] == "claude-opus-5"
            # resumable: nothing left to ask
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 0
            assert raw.call_count == 10
        labels = [json.loads(line) for line in (out / "labels.jsonl").read_text().splitlines()]
        assert [lab["on_topic"] for lab in labels] == [True, False] * 5
        assert {"post_id", "on_topic", "raw", "model", "ts"} <= set(labels[0])

    def test_a_stale_set_is_refused(self, tmp_path, capsys):
        _code, out, notes, home = _sample(tmp_path, _population(40), n=10)
        (home / "identity.md").write_text(IDENTITY + " Adopted.", encoding="utf-8")
        with patch("evals.judging.run_claude_raw") as raw:
            code = ls.main(["label", "--dir", str(out), "--dry-run"], notes_root=notes)
        assert code == 2
        raw.assert_not_called()
        assert "identity_sha256" in capsys.readouterr().out


def _labelled(tmp_path):
    _code, out, notes, home = _sample(tmp_path, _population(40), n=10)
    rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
    # on-topic exactly for the high live scores
    (out / "labels.jsonl").write_text(
        "".join(
            json.dumps({"post_id": r["post_id"], "on_topic": r["live_score"] >= 0.8}) + "\n"
            for r in rows
        )
    )
    return out, notes, home, rows


def _entry_by_score(rows, *, invert=False):
    """A fake arm C whose P(top) ranks the rows by live score."""
    by_text = {base64.b64decode(r["content_b64"]).decode(): r["live_score"] for r in rows}

    def fake(state, model):
        score = next(v for text, v in by_text.items() if text in state["post"])
        p_top = 1.0 - score if invert else score
        return {"reason": "answered", "p_top": p_top, "score": p_top, "latency_ms": 100}

    return fake


class TestScore:
    def test_summary_axes(self, tmp_path, capsys):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)):
            code = ls.main(["score", "--dir", str(out)], notes_root=notes)
        assert code == 0
        summary = json.loads((out / "summary.json").read_text())
        assert summary["auc_p_top"] == 1.0
        assert summary["auc_expected_level"] == 1.0
        assert set(summary["cuts"]) == {"0.3", "0.5", "0.7"}
        assert summary["cuts"]["0.7"]["precision"] is not None
        assert summary["latency_ms_p95"] == 100
        assert SECRET not in (out / "summary.json").read_text() + capsys.readouterr().out

    def test_exit_0_against_an_equal_baseline(self, tmp_path):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)):
            ls.main(["score", "--dir", str(out)], notes_root=notes)
            baseline = out / "baseline.json"
            (out / "summary.json").rename(baseline)
            code = ls.main(
                ["score", "--dir", str(out), "--baseline", str(baseline)], notes_root=notes
            )
        assert code == 0

    def test_exit_1_on_an_auc_drop(self, tmp_path):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)):
            ls.main(["score", "--dir", str(out)], notes_root=notes)
        baseline = out / "baseline.json"
        (out / "summary.json").rename(baseline)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows, invert=True)):
            code = ls.main(
                ["score", "--dir", str(out), "--baseline", str(baseline)], notes_root=notes
            )
        assert code == 1

    def test_exit_2_when_a_pinned_sha_differs(self, tmp_path):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)):
            ls.main(["score", "--dir", str(out)], notes_root=notes)
            baseline = out / "baseline.json"
            data = json.loads((out / "summary.json").read_text())
            data["manifest"]["identity_sha256"] = "0" * 64
            baseline.write_text(json.dumps(data))
            code = ls.main(
                ["score", "--dir", str(out), "--baseline", str(baseline)], notes_root=notes
            )
        assert code == 2


class TestScoreStale:
    def test_a_stale_set_is_not_scored(self, tmp_path, capsys):
        out, notes, home, rows = _labelled(tmp_path)
        (home / "identity.md").write_text(IDENTITY + " Adopted.", encoding="utf-8")
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)) as scorer:
            code = ls.main(["score", "--dir", str(out)], notes_root=notes)
        assert code == 2
        scorer.assert_not_called()
        assert "identity_sha256" in capsys.readouterr().out
        assert not (out / "summary.json").exists()


class TestCheck:
    def test_fresh_then_stale(self, tmp_path, capsys):
        _code, out, notes, home = _sample(tmp_path, _population(40), n=10)
        assert ls.main(["check", "--dir", str(out)], notes_root=notes) == 0
        (home / "prompts").mkdir()
        (home / "prompts" / "relevance_score4.md").write_text("override", encoding="utf-8")
        (home / "identity.md").write_text("changed", encoding="utf-8")
        capsys.readouterr()
        assert ls.main(["check", "--dir", str(out)], notes_root=notes) == 1
        printed = capsys.readouterr().out
        assert "identity_sha256" in printed
        assert "relevance_score4_home_sha256" in printed


def test_main_tree_is_the_git_common_dir_parent():
    assert (ls.main_tree() / ".git").exists()
