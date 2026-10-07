# pyright: reportPrivateUsage=false
"""The relevance face's label-once asset (scripts/relevance_label_set.py, RFC-0046 / RFC-0047 §3).

Pinned: ``sample`` dedupes by post_id, keeps only answered judgments since
the switch (a live half, when a row has one, ``scored``; a row without one —
RFC-0046 cleanup 2 — is a candidate too), stratifies on the logged P(top)
across the gate (the rejected side included), writes b64 rows + a manifest of
shas naming its ``strata_key``, and refuses to write a partial set (exit 2); a
manifest without ``strata_key`` (S35 / S36) still weights on the live score; output outside ``.notes/`` is refused; ``label
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
AXIOMS = "Emptiness: hold every objective lightly."


def _load():
    spec = importlib.util.spec_from_file_location("relevance_label_set", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["relevance_label_set"] = module
    spec.loader.exec_module(module)
    return module


ls = _load()


def _row(
    post_id,
    score,
    *,
    ts="2026-09-26T01:00:00+00:00",
    reason="answered",
    live="scored",
    p_top=0.5,
):
    body = f"{SECRET} {post_id}"
    return {
        "ts": ts,
        "post_id": post_id,
        "live_score": score,
        "live_reason": live,
        "live_gate": score >= 0.8,
        "threshold_applied": 0.8,
        "decision_reason": reason,
        "decision_p_top": p_top,
        "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "content_b64": base64.b64encode(body.encode()).decode(),
    }


@pytest.fixture(autouse=True)
def _reset_prompting():
    # identity+axioms wires production's prompting (module state) per run.
    from contemplative_agent.core.llm import reset_llm_config

    yield
    reset_llm_config()


def _home(tmp_path: Path, rows: list[dict], *, axioms: str | None = AXIOMS) -> Path:
    home = tmp_path / "home"
    (home / "logs").mkdir(parents=True)
    (home / "identity.md").write_text(IDENTITY, encoding="utf-8")
    if axioms is not None:
        (home / "constitution").mkdir()
        (home / "constitution" / "contemplative-axioms.md").write_text(axioms, encoding="utf-8")
    (home / "logs" / "relevance-2026-09-26.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return home


SCORES = (0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
# One logged P(top) per SCORES slot, covering all five P(top) strata.
P_TOPS = (0.01, 0.1, 0.25, 0.4, 0.8, 0.02, 0.15, 0.95)


def _population(count: int) -> list[dict]:
    return [
        _row(f"p{i:03d}", SCORES[i % len(SCORES)], p_top=P_TOPS[i % len(P_TOPS)])
        for i in range(count)
    ]


def _schema4_row(post_id: str, p_top: float) -> dict:
    """A row written after RFC-0046 cleanup 2: no live half at all."""
    row = _row(post_id, 0.0, p_top=p_top)
    for key in ("live_score", "live_reason", "live_gate", "threshold_applied"):
        del row[key]
    return row


def _sample(
    tmp_path,
    rows,
    *,
    n=10,
    since="2026-09-25T00:00:00Z",
    seed=7,
    axioms: str | None = AXIOMS,
    extra=(),
):
    home = _home(tmp_path, rows, axioms=axioms)
    notes = tmp_path / ".notes"
    out = notes / "labels" / "relevance" / "set"
    code = ls.main(
        [
            "sample",
            *extra,
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
        # Both sides of the score4 gate, the rejected side included.
        assert any(r["decision_p_top"] < 0.3 for r in written)
        assert any(r["decision_p_top"] >= 0.3 for r in written)
        assert {r["stratum"] for r in written} == {name for name, _lo, _hi in ls.P_TOP_STRATA}
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["strata_key"] == "decision_p_top"
        assert manifest["rows"] == 10
        assert manifest["population"] == 40
        assert manifest["seed"] == 7
        assert manifest["identity_sha256"] == hashlib.sha256(IDENTITY.encode()).hexdigest()
        assert manifest["relevance_score4_sha256"] and manifest["relevance_sha256"]
        assert manifest["since"] == "2026-09-25T00:00:00+00:00"
        text = (out / "rows.jsonl").read_text() + (out / "manifest.json").read_text()
        assert SECRET not in text + capsys.readouterr().out

    def test_rows_without_a_live_half_are_candidates(self, tmp_path):
        rows = [_schema4_row(f"n{i:02d}", P_TOPS[i % len(P_TOPS)]) for i in range(20)]
        rows.append(_row("x-old-outage", 0.0, live="llm_unavailable", p_top=0.9))
        code, out, _notes, _home_ = _sample(tmp_path, rows, n=10)
        assert code == 0
        written = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        assert all(r["live_score"] is None for r in written)
        assert not any(r["post_id"].startswith("x-") for r in written)
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["population"] == 20

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


class TestDomainSource:
    """RFC-0046 S32: the label set pins which "my domain" its labels were asked under."""

    def test_the_manifest_pins_the_axioms_and_the_definition(self, tmp_path):
        _code, out, _notes, _home_ = _sample(tmp_path, _population(40))
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["domain_source"] == "identity+axioms"
        assert manifest["axioms_sha256"] == hashlib.sha256(AXIOMS.encode()).hexdigest()

    def test_no_constitution_pins_null(self, tmp_path):
        _code, out, _notes, _home_ = _sample(tmp_path, _population(40), axioms=None)
        assert json.loads((out / "manifest.json").read_text())["axioms_sha256"] is None

    def test_an_axioms_change_is_stale(self, tmp_path, capsys):
        _code, out, notes, home = _sample(tmp_path, _population(40))
        capsys.readouterr()
        (home / "constitution" / "contemplative-axioms.md").write_text("changed", encoding="utf-8")
        assert ls.main(["check", "--dir", str(out)], notes_root=notes) == 1
        assert "axioms_sha256" in capsys.readouterr().out
        with patch("evals.judging.run_claude_raw") as raw:
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 2
        raw.assert_not_called()

    def test_label_asks_under_identity_and_axioms_by_default(self, tmp_path):
        _code, out, notes, _home_ = _sample(tmp_path, _population(40))
        with patch("evals.judging.run_claude_raw", return_value="3") as raw:
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 0
        prompt = raw.call_args.args[0]
        assert AXIOMS in prompt
        assert json.dumps(IDENTITY + "\n\n---\n\n" + AXIOMS, ensure_ascii=False) in prompt

    def test_identity_reproduces_the_old_prompt(self, tmp_path, pinned_nonce):
        _code, out, notes, _home_ = _sample(
            tmp_path, _population(40), extra=("--domain-source", "identity")
        )
        assert json.loads((out / "manifest.json").read_text())["domain_source"] == "identity"
        rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        with patch("evals.judging.run_claude_raw", return_value="3") as raw:
            code = ls.main(
                ["label", "--dir", str(out), "--domain-source", "identity"], notes_root=notes
            )
        assert code == 0
        rar = ls.replay()
        last = rows[-1]
        text = base64.b64decode(last["content_b64"]).decode()
        assert raw.call_args.args[0] == rar.ceiling_prompt(rar.build_state(IDENTITY, text))
        assert AXIOMS not in raw.call_args.args[0]

    @pytest.mark.parametrize("command", ["label", "score"])
    def test_a_definition_other_than_the_manifests_exits_2(self, tmp_path, capsys, command):
        out, notes, _home_, rows = _labelled(tmp_path)
        capsys.readouterr()
        with (
            patch("evals.judging.run_claude_raw") as raw,
            patch.object(ls, "score_row", side_effect=_entry_by_score(rows)) as scorer,
        ):
            code = ls.main(
                [command, "--dir", str(out), "--domain-source", "identity"], notes_root=notes
            )
        assert code == 2
        raw.assert_not_called()
        scorer.assert_not_called()
        assert "domain_source" in capsys.readouterr().out

    def test_a_manifest_without_the_field_is_identity(self, tmp_path, capsys):
        out, notes, _home_, rows = _labelled(tmp_path)
        manifest = json.loads((out / "manifest.json").read_text())
        # a pre-S32 manifest: neither field
        del manifest["domain_source"]
        del manifest["axioms_sha256"]
        (out / "manifest.json").write_text(json.dumps(manifest))
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)) as scorer:
            assert ls.main(["score", "--dir", str(out)], notes_root=notes) == 2
            scorer.assert_not_called()
            code = ls.main(
                ["score", "--dir", str(out), "--domain-source", "identity"], notes_root=notes
            )
        assert code == 0
        assert {call.args[0]["domain"] for call in scorer.call_args_list} == {IDENTITY}

    def test_an_identity_set_ignores_an_axioms_change(self, tmp_path):
        _code, out, notes, home = _sample(
            tmp_path, _population(40), extra=("--domain-source", "identity")
        )
        (home / "constitution" / "contemplative-axioms.md").write_text("changed", encoding="utf-8")
        assert ls.main(["check", "--dir", str(out)], notes_root=notes) == 0

    def test_score_reads_identity_and_axioms_by_default(self, tmp_path):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)) as scorer:
            assert ls.main(["score", "--dir", str(out)], notes_root=notes) == 0
        domains = {call.args[0]["domain"] for call in scorer.call_args_list}
        assert domains == {IDENTITY + "\n\n---\n\n" + AXIOMS}
        summary = json.loads((out / "summary.json").read_text())
        assert summary["manifest"]["domain_source"] == "identity+axioms"
        assert summary["manifest"]["axioms_sha256"] == hashlib.sha256(AXIOMS.encode()).hexdigest()

    def test_a_baseline_under_the_other_definition_is_incomparable(self, tmp_path):
        out, notes, _home_, rows = _labelled(tmp_path)
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)):
            ls.main(["score", "--dir", str(out)], notes_root=notes)
            baseline = out / "baseline.json"
            data = json.loads((out / "summary.json").read_text())
            data["manifest"]["domain_source"] = "identity"
            baseline.write_text(json.dumps(data))
            code = ls.main(
                ["score", "--dir", str(out), "--baseline", str(baseline)], notes_root=notes
            )
        assert code == 2


def test_main_tree_is_the_git_common_dir_parent():
    assert (ls.main_tree() / ".git").exists()


# --------------------------------------------------------------------------
# RFC-0046 S35: the judge on every label, and the readings enforce acts on
# --------------------------------------------------------------------------


def _write_labels(
    out, rows, *, judge: str | None = "jev", on_topic=lambda r: r["live_score"] >= 0.8
):
    lines = []
    for r in rows:
        record = {"post_id": r["post_id"], "on_topic": on_topic(r)}
        if judge is not None:
            record["judge"] = judge
        lines.append(json.dumps(record) + "\n")
    (out / "labels.jsonl").write_text("".join(lines))


def _recorded_set(tmp_path, *, judge: str | None = "jev"):
    """A set whose recorded P(top) equals the live score (so it ranks the labels)."""
    population = [{**r, "decision_p_top": r["live_score"]} for r in _population(40)]
    _code, out, notes, home = _sample(tmp_path, population, n=10)
    rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
    _write_labels(out, rows, judge=judge)
    return out, notes, home, rows


def _score(out, notes, rows, *extra, invert=False) -> tuple[int, dict]:
    """``(exit code, the summary written)`` — a comparison's exit 2 still writes it."""
    with patch.object(ls, "score_row", side_effect=_entry_by_score(rows, invert=invert)):
        code = ls.main(["score", "--dir", str(out), *extra], notes_root=notes)
    return code, json.loads((out / "summary.json").read_text())


class TestLabelJudge:
    def test_opus_labels_carry_their_judge(self, tmp_path):
        _code, out, notes, _home_ = _sample(tmp_path, _population(40), n=10)
        with patch("evals.judging.run_claude_raw", return_value="3"):
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 0
        labels = [json.loads(line) for line in (out / "labels.jsonl").read_text().splitlines()]
        assert {lab["judge"] for lab in labels} == {"opus"}

    def test_the_summary_names_the_judge(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        _code, summary = _score(out, notes, rows)
        assert summary["label_judge"] == "jev"

    def test_a_label_without_the_field_is_opus(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path, judge=None)
        _code, summary = _score(out, notes, rows)
        assert summary["label_judge"] == "opus"

    def test_opus_does_not_label_into_a_jev_set(self, tmp_path, capsys):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        (out / "labels.jsonl").write_text(
            json.dumps({"post_id": rows[0]["post_id"], "on_topic": True, "judge": "jev"}) + "\n"
        )
        with patch("evals.judging.run_claude_raw") as raw:
            assert ls.main(["label", "--dir", str(out)], notes_root=notes) == 2
        raw.assert_not_called()
        assert "jev" in capsys.readouterr().out

    def test_mixed_judges_are_not_scored(self, tmp_path, capsys):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        with (out / "labels.jsonl").open("a") as sink:
            sink.write(json.dumps({"post_id": "zzz", "on_topic": True, "judge": "opus"}) + "\n")
        with patch.object(ls, "score_row", side_effect=_entry_by_score(rows)) as scorer:
            code = ls.main(["score", "--dir", str(out)], notes_root=notes)
        assert code == 2
        scorer.assert_not_called()
        assert "judge" in capsys.readouterr().out

    def test_a_baseline_by_another_judge_is_incomparable(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        _code, summary = _score(out, notes, rows)
        baseline = out / "baseline.json"
        summary["label_judge"] = "opus"
        baseline.write_text(json.dumps(summary))
        code, now = _score(out, notes, rows, "--baseline", str(baseline))
        assert code == 2
        assert "label_judge" in now["comparison"]["sha_differs"]

    def test_an_old_baseline_without_the_field_was_opus(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path, judge=None)
        _code, summary = _score(out, notes, rows)
        del summary["label_judge"]
        baseline = out / "baseline.json"
        baseline.write_text(json.dumps(summary))
        code, _now = _score(out, notes, rows, "--baseline", str(baseline))
        assert code == 0


class TestProductionReadings:
    def test_live_cut_reads_the_recorded_live_gate(self, tmp_path):
        # labels = live_score >= 0.8 = the rows' live_gate: the live gate is exact
        out, notes, _home_, rows = _recorded_set(tmp_path)
        _code, summary = _score(out, notes, rows)
        live = summary["live_cut"]
        assert live["n"] == 10
        assert (live["precision"], live["recall"], live["agreement"]) == (1.0, 1.0, 1.0)
        assert live["gate_rate"] == round(sum(r["live_gate"] for r in rows) / 10, 4)

    def test_recorded_cuts_read_the_logged_p_top(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        # the re-score is inverted; the recorded reading must not follow it
        _code, summary = _score(out, notes, rows, invert=True)
        recorded = summary["recorded_cuts"]
        assert recorded["n"] == 10
        assert recorded["auc_p_top"] == 1.0
        assert set(recorded["cuts"]) == {"0.3", "0.5", "0.7"}
        expected = ls.cut_reading(
            [r["live_score"] for r in rows], [r["live_score"] >= 0.8 for r in rows], 0.7
        )
        assert recorded["cuts"]["0.7"] == expected
        assert summary["auc_p_top"] == 0.0  # the inverted re-score

    def test_the_gap_between_recorded_and_rescored(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        _code, same = _score(out, notes, rows)
        gap = same["recorded_vs_rescored"]
        assert gap["n"] == 10
        assert gap["abs_delta_mean"] == 0.0 and gap["abs_delta_p95"] == 0.0
        assert gap["gate_flips"] == {"0.3": 0, "0.5": 0, "0.7": 0}
        _code, inverted = _score(out, notes, rows, invert=True)
        flips = inverted["recorded_vs_rescored"]["gate_flips"]
        expected = sum(1 for r in rows if (r["live_score"] >= 0.5) != (1 - r["live_score"] >= 0.5))
        assert flips["0.5"] == expected > 0

    def test_the_manifest_counts_the_population_per_stratum(self, tmp_path):
        _code, out, _notes, _home_ = _sample(tmp_path, _population(40), n=10)
        manifest = json.loads((out / "manifest.json").read_text())
        assert sum(manifest["population_strata"].values()) == manifest["population"] == 40
        assert set(manifest["population_strata"]) >= set(manifest["strata"])

    def test_every_reading_has_a_population_weighted_twin(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        _code, summary = _score(out, notes, rows)
        assert set(summary["cuts_weighted"]) == {"0.3", "0.5", "0.7"}
        assert set(summary["recorded_cuts"]["cuts_weighted"]) == {"0.3", "0.5", "0.7"}
        assert summary["live_cut"]["weighted"]["precision"] == 1.0

    def test_a_live_stratified_manifest_still_scores_weighted(self, tmp_path):
        """S35 / S36 shape: no ``strata_key``, population counted on live strata."""
        out, notes, _home_, rows = _recorded_set(tmp_path)
        manifest = json.loads((out / "manifest.json").read_text())
        del manifest["strata_key"]
        live_strata: dict[str, int] = {}
        for r in rows:
            name = ls.replay().stratum_of(r["live_score"])
            live_strata[name] = live_strata.get(name, 0) + 2
        manifest["population_strata"] = live_strata
        (out / "manifest.json").write_text(json.dumps(manifest))
        _code, summary = _score(out, notes, rows)
        assert summary["strata_key"] == "live_score"
        assert summary["cuts_weighted"] is not None
        assert summary["live_cut"]["weighted"] is not None

    @pytest.mark.parametrize(("now", "code"), [(0.9, 0), (0.895, 0), (0.89, 1)])
    def test_the_regression_line_is_0_03(self, now, code):
        """RFC-0046: 0.02 sat inside the run-to-run noise floor; the line is 0.03."""
        assert ls.REGRESSION_AUC_DROP == 0.03
        baseline = {"manifest": {}, "auc_p_top": 0.921}
        exit_code, _report = ls.compare({"manifest": {}, "auc_p_top": now}, baseline)
        assert exit_code == code

    def test_an_old_manifest_has_no_weighted_reading(self, tmp_path):
        out, notes, _home_, rows = _recorded_set(tmp_path)
        manifest = json.loads((out / "manifest.json").read_text())
        del manifest["population_strata"]
        (out / "manifest.json").write_text(json.dumps(manifest))
        _code, summary = _score(out, notes, rows)
        assert summary["cuts_weighted"] is None
        assert summary["live_cut"]["weighted"] is None


class TestWeightedCut:
    def test_weights_undo_the_stratified_draw(self):
        # two strata: stratum A (weight 3) all gated and on-topic, B (weight 1) gated, off-topic
        scores = [0.9, 0.9, 0.9, 0.9]
        labels = [True, True, False, False]
        plain = ls.cut_reading(scores, labels, 0.5)
        weighted = ls.cut_reading(scores, labels, 0.5, weights=[3.0, 3.0, 1.0, 1.0])
        assert plain["precision"] == 0.5
        assert weighted["precision"] == 0.75
        assert weighted["recall"] == 1.0
        assert weighted["gate_rate"] == 1.0

    def test_stratum_weights_are_population_over_sample(self):
        rows = [{"live_score": 0.1}, {"live_score": 0.2}, {"live_score": 0.9}]
        live = ls.STRATA_KEY_LIVE
        weights = ls.stratum_weights(rows, {"s0_le0.4": 10, "s4_ge0.9": 5}, strata_key=live)
        assert weights == [5.0, 5.0, 5.0]
        assert ls.stratum_weights(rows, None, strata_key=live) is None

    def test_p_top_weights_use_the_p_top_bands(self):
        rows = [{"decision_p_top": 0.01}, {"decision_p_top": 0.29}, {"decision_p_top": 0.31}]
        population = {"p0_lt0.05": 8, "p2_0.2-0.3": 3, "p3_0.3-0.7": 6}
        weights = ls.stratum_weights(rows, population, strata_key=ls.STRATA_KEY_P_TOP)
        assert weights == [8.0, 3.0, 6.0]

    def test_a_manifest_without_strata_key_was_stratified_on_the_live_score(self):
        assert ls.manifest_strata_key({}) == "live_score"
        assert ls.manifest_strata_key({"strata_key": "decision_p_top"}) == "decision_p_top"

    def test_a_borrowed_row_weighs_as_its_own_stratum(self):
        # s4 had 1 row in the population; the draw topped it up from s3 and
        # tagged the borrowed rows s4 — they must weigh as s3, and not crash
        # on a tag the population never counted.
        rows = [
            {"live_score": 0.9, "stratum": "s4_ge0.9"},
            {"live_score": 0.8, "stratum": "s4_ge0.9"},
            {"live_score": 0.8, "stratum": "s4_ge0.9"},
            {"live_score": 0.8, "stratum": "s3_0.8"},
        ]
        weights = ls.stratum_weights(
            rows, {"s4_ge0.9": 1, "s3_0.8": 30}, strata_key=ls.STRATA_KEY_LIVE
        )
        assert weights == [1.0, 10.0, 10.0, 10.0]

    def test_a_topped_up_draw_scores_with_weights(self, tmp_path):
        # no row at >= 0.85: the s4 quota is filled from other strata
        population = [
            {**r, "decision_p_top": r["live_score"]}
            for r in _population(40)
            if r["live_score"] < 0.85
        ]
        _code, out, notes, _home_ = _sample(tmp_path, population, n=10)
        rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        _write_labels(out, rows)
        code, summary = _score(out, notes, rows)
        assert code == 0
        assert summary["cuts_weighted"] is not None
        assert summary["live_cut"]["weighted"] is not None
