"""Jev labels on the relevance face's frozen label set (evals/jev_arm.py, RFC-0046 S35).

``python -m evals.jev_arm relevance-labels --dir <set>`` asks Jev the RFC-0045
``Jx/score4`` request for every row of ``relevance_label_set.py``'s set and
appends one label per row to ``labels.jsonl``. Pinned here, with no network:
the state is the label set's own (``row_state`` under the manifest's
``domain_source``), the pre-registered line (on_topic = P(directly on-topic)
>= 0.5) and the label record, ``--dry-run`` sends nothing, a stale manifest /
another judge's labels / a missing key send nothing, the rate-limit stop,
resume, and that no post text or key reaches stdout or the file.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import responses

from evals import jev_arm as mod

REPO_ROOT = Path(__file__).resolve().parent.parent
DUMMY_KEY = "sk-test-DO-NOT-LEAK-0123456789"
SECRET = "a post body that must never be printed"
IDENTITY = "I am an agent concerned with contemplative AI alignment and local models."
AXIOMS = "Emptiness: hold every objective lightly."


def _load_label_set():
    name = "relevance_label_set"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "relevance_label_set.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ls = _load_label_set()


@pytest.fixture(autouse=True)
def _reset_prompting():
    from contemplative_agent.core.llm import reset_llm_config

    yield
    reset_llm_config()


def _row(i: int) -> dict:
    body = f"{SECRET} p{i:03d}"
    score = (0.1, 0.5, 0.7, 0.8, 0.9)[i % 5]
    return {
        "ts": "2026-09-26T04:00:00+00:00",
        "post_id": f"p{i:03d}",
        "live_score": score,
        "live_reason": "scored",
        "live_gate": score >= 0.8,
        "threshold_applied": 0.82,
        "decision_reason": "answered",
        "decision_p_top": score,
        "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "content_b64": base64.b64encode(body.encode()).decode(),
    }


def _label_set(tmp_path: Path, n: int = 5) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    (home / "logs").mkdir(parents=True)
    (home / "identity.md").write_text(IDENTITY, encoding="utf-8")
    (home / "constitution").mkdir()
    (home / "constitution" / "contemplative-axioms.md").write_text(AXIOMS, encoding="utf-8")
    (home / "logs" / "relevance-2026-09-26.jsonl").write_text(
        "".join(json.dumps(_row(i)) + "\n" for i in range(20)), encoding="utf-8"
    )
    notes = tmp_path / ".notes"
    out = notes / "labels" / "relevance" / "set"
    argv = ["sample", "--home", str(home), "--since", "2026-09-26T03:00:00Z"]
    argv += ["--n", str(n), "--seed", "1", "--out", str(out)]
    assert ls.main(argv, notes_root=notes) == 0
    return out, notes, home


def _payload(p_top: float) -> dict:
    rest = (1.0 - p_top) / 3
    return {
        "model": mod.DEFAULT_MODEL,
        "answers": {
            "score4": {
                "type": "score",
                "legend": {"0": "a", "1": "b", "2": "c", "3": "d"},
                "probabilities": {"0": rest, "1": rest, "2": rest, "3": p_top},
            },
            "noul": {"type": "noul", "noul": 0.4},
        },
        "usage": {"input_tokens": 810, "output_tokens": 30},
    }


def _run(out: Path, notes: Path, *extra: str) -> int:
    return mod.relevance_labels_main(["--dir", str(out), *extra], notes_root=notes)


def _labels(out: Path) -> list[dict]:
    path = out / "labels.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(mod, "load_api_key", lambda: mod.ApiKey(DUMMY_KEY))


class TestDryRun:
    @responses.activate
    def test_counts_and_prices_and_sends_nothing(self, tmp_path, keyed, capsys):
        out, notes, _home = _label_set(tmp_path)
        capsys.readouterr()
        assert _run(out, notes, "--dry-run") == 0
        printed = capsys.readouterr().out
        assert "5 row(s) to ask" in printed
        assert "$" in printed and "token" in printed
        assert SECRET not in printed
        assert len(responses.calls) == 0
        assert not (out / "labels.jsonl").exists()


class TestRun:
    @responses.activate
    def test_the_pre_registered_line_and_the_record(self, tmp_path, keyed, capsys):
        out, notes, _home = _label_set(tmp_path)
        for p_top in (0.6, 0.5, 0.49, 0.1, 0.99):
            responses.add(responses.POST, mod.API_URL, json=_payload(p_top), status=200)
        assert _run(out, notes) == 0
        labels = _labels(out)
        assert [lab["on_topic"] for lab in labels] == [True, True, False, False, True]
        first = labels[0]
        assert first["judge"] == "jev"
        assert first["rule"] == "p_top>=0.5"
        assert first["model"] == mod.DEFAULT_MODEL
        assert first["p_top"] == pytest.approx(0.6)
        assert len(first["probs"]) == 4
        assert first["domain_source"] == "identity+axioms"
        assert {"post_id", "ts"} <= set(first)
        rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        assert [lab["post_id"] for lab in labels] == [r["post_id"] for r in rows]
        text = (out / "labels.jsonl").read_text() + capsys.readouterr().out
        assert SECRET not in text and DUMMY_KEY not in text

    @responses.activate
    def test_the_state_is_the_label_sets_own(self, tmp_path, keyed, pinned_nonce):
        out, notes, home = _label_set(tmp_path, n=5)
        for _ in range(5):
            responses.add(responses.POST, mod.API_URL, json=_payload(0.7), status=200)
        assert _run(out, notes) == 0
        rows = [json.loads(line) for line in (out / "rows.jsonl").read_text().splitlines()]
        body = responses.calls[0].request.body
        assert body is not None
        sent = json.loads(body)
        domain = ls.replay().domain_for_source(home, "identity+axioms")
        assert domain == IDENTITY + "\n\n---\n\n" + AXIOMS
        assert sent["state"] == ls.row_state(rows[0], domain)
        # the RFC-0045 Jx request: the 4-level Score (and its Noul), the replay's words
        rel = mod.load_relevance_module()
        expected = {q.qid: q.payload for q in mod.build_relevance_questions(rel)}
        assert sent["questions"] == expected
        assert sent["model"] == mod.DEFAULT_MODEL

    @responses.activate
    def test_resume_asks_only_what_is_missing(self, tmp_path, keyed):
        out, notes, _home = _label_set(tmp_path)
        for _ in range(2):
            responses.add(responses.POST, mod.API_URL, json=_payload(0.7), status=200)
        responses.add(responses.POST, mod.API_URL, status=500, json={})
        for _ in range(2):
            responses.add(responses.POST, mod.API_URL, json=_payload(0.7), status=200)
        assert _run(out, notes) == 1  # one row failed
        assert len(_labels(out)) == 4
        with pytest.raises(SystemExit, match="--resume"):
            _run(out, notes)
        responses.add(responses.POST, mod.API_URL, json=_payload(0.2), status=200)
        assert _run(out, notes, "--resume") == 0
        assert len(responses.calls) == 6
        assert len({lab["post_id"] for lab in _labels(out)}) == 5

    @responses.activate
    def test_an_unreadable_answer_is_a_failure_not_a_label(self, tmp_path, keyed, capsys):
        out, notes, _home = _label_set(tmp_path, n=5)
        broken = _payload(0.7)
        broken["answers"]["score4"] = {"type": "score"}
        responses.add(responses.POST, mod.API_URL, json=broken, status=200)
        for _ in range(4):
            responses.add(responses.POST, mod.API_URL, json=_payload(0.7), status=200)
        assert _run(out, notes) == 1
        assert len(_labels(out)) == 4
        assert "parse_failed=1" in capsys.readouterr().out

    @responses.activate
    def test_a_rate_limit_after_the_one_wait_stops_the_run(self, tmp_path, keyed, capsys):
        out, notes, _home = _label_set(tmp_path)
        responses.add(responses.POST, mod.API_URL, json=_payload(0.7), status=200)
        for _ in range(2):
            responses.add(
                responses.POST, mod.API_URL, status=429, json={}, headers={"Retry-After": "0"}
            )
        assert _run(out, notes) == 1
        assert mod.REASON_RATE_LIMITED_STOP in capsys.readouterr().out
        assert len(responses.calls) == 3
        assert len(_labels(out)) == 1


class TestRefusals:
    @responses.activate
    def test_a_missing_key_sends_nothing(self, tmp_path, monkeypatch, capsys):
        out, notes, _home = _label_set(tmp_path)
        monkeypatch.setattr(mod, "load_api_key", lambda: None)
        assert _run(out, notes) == 1
        assert mod.REASON_KEY_MISSING in capsys.readouterr().out
        assert len(responses.calls) == 0

    @responses.activate
    def test_a_stale_set_sends_nothing(self, tmp_path, keyed, capsys):
        out, notes, home = _label_set(tmp_path)
        (home / "identity.md").write_text(IDENTITY + " Adopted.", encoding="utf-8")
        assert _run(out, notes) == 2
        assert "identity_sha256" in capsys.readouterr().out
        assert len(responses.calls) == 0

    @responses.activate
    def test_another_judges_labels_are_not_mixed_in(self, tmp_path, keyed, capsys):
        out, notes, _home = _label_set(tmp_path)
        (out / "labels.jsonl").write_text(json.dumps({"post_id": "p000", "on_topic": True}) + "\n")
        assert _run(out, notes, "--resume") == 2
        assert "opus" in capsys.readouterr().out
        assert len(responses.calls) == 0

    def test_a_set_outside_notes_is_refused(self, tmp_path, keyed):
        out, _notes, _home = _label_set(tmp_path)
        with pytest.raises(SystemExit, match="outside"):
            _run(out, tmp_path / "elsewhere" / ".notes")

    def test_the_subcommand_is_wired(self, monkeypatch):
        seen: list[list[str]] = []
        monkeypatch.setattr(mod, "relevance_labels_main", lambda argv: seen.append(argv) or 0)
        assert mod.main(["relevance-labels", "--dir", "x", "--dry-run"]) == 0
        assert seen == [["--dir", "x", "--dry-run"]]
