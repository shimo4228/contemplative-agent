"""Tests for scripts/novelty_retrieval_dry_run.py — the RFC-0023 entry reading.

The real corpus is the live knowledge store (7k+ rows) and the live skill
store, so everything asserted here runs against a synthetic home: six pattern
rows whose hand-written embeddings fall into two clusters plus two far-away
singletons, three skill files, and a stubbed ``embed_texts``. What is pinned
is the *shape* of the reading and the abstain path — the numbers are the
author's to read off the real run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import novelty_retrieval_dry_run as nrd  # noqa: E402  # pyright: ignore[reportMissingImports]

# Two tight groups (axis 0 and axis 1) plus two singletons pointed at axes
# nothing else uses, so average-linkage at CLUSTER_THRESHOLD_INSIGHT (0.70)
# yields exactly two clusters of three and two leftovers.
_PATTERNS = [
    ("cluster A member one about anchoring", [1.0, 0.0, 0.0, 0.0]),
    ("cluster A member two about anchoring", [0.99, 0.05, 0.0, 0.0]),
    ("cluster A member three about anchoring", [0.98, 0.10, 0.0, 0.0]),
    ("cluster B member one about boundaries", [0.0, 1.0, 0.0, 0.0]),
    ("cluster B member two about boundaries", [0.05, 0.99, 0.0, 0.0]),
    ("cluster B member three about boundaries", [0.10, 0.98, 0.0, 0.0]),
    ("a lone observation about upvote sequences", [0.0, 0.0, 1.0, 0.0]),
    ("another lone observation about naming", [0.0, 0.0, 0.0, 1.0]),
]

_SKILLS = {
    "anchor-contextually-20260801.md": (
        "anchor-contextually",
        "anchor an interpretation to its context before acting",
        "Hold the anchoring frame explicitly and name the context it rests on.",
    ),
    "map-boundaries-20260802.md": (
        "map-boundaries",
        "map the boundaries of a system before proposing a change",
        "Draw the boundaries first: what is fixed, and which edge is a condition.",
    ),
    "cross-reference-claims-20260803.md": (
        "cross-reference-claims",
        "check a foundational claim against a second source",
        "Find a second independent source before building on one claim.",
    ),
}


def _write_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "skills").mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    rows = [
        {
            "pattern": text,
            "distilled": f"2026-08-{index + 10:02d}T08:00:00+00:00",
            "embedding": embedding,
            "provenance": {"source_type": "unknown"},
            "valid_from": f"2026-08-{index + 10:02d}T08:00:00+00:00",
            "valid_until": None,
        }
        for index, (text, embedding) in enumerate(_PATTERNS)
    ]
    # One superseded row and one gated row: both must be excluded, the same
    # way _select_patterns and _build_cluster_batches exclude them.
    rows.append(
        {
            "pattern": "a superseded claim",
            "distilled": "2026-07-01T08:00:00+00:00",
            "embedding": [1.0, 0.0, 0.0, 0.0],
            "valid_until": "2026-08-01T00:00:00+00:00",
        }
    )
    rows.append(
        {
            "pattern": "noise",
            "distilled": "2026-07-02T08:00:00+00:00",
            "embedding": [1.0, 0.0, 0.0, 0.0],
            "gated": True,
            "valid_until": None,
        }
    )
    (home / "knowledge.json").write_text(json.dumps(rows), encoding="utf-8")
    for filename, (name, description, body) in _SKILLS.items():
        (home / "skills" / filename).write_text(
            f"---\nname: {name}\ndescription: {description}\norigin: auto-extracted\n---\n\n"
            f"# {name}\n\n{body}\n",
            encoding="utf-8",
        )
    (home / "logs" / "insight-novelty.jsonl").write_text(
        json.dumps({"verdict": "judged", "clusters": ["c1", "c2", "c3", "c4"], "covered": ["c1"]})
        + "\n"
        + json.dumps({"verdict": "judged", "clusters": ["c5", "c6"], "covered": []})
        + "\n"
        # A failed call: its empty `covered` must not read as "the LLM
        # covered nothing".
        + json.dumps({"verdict": "fail_open_llm", "clusters": ["c7"] * 50, "covered": []})
        + "\nnot json\n",
        encoding="utf-8",
    )
    return home


@pytest.fixture
def stub_embeddings(monkeypatch):
    """One axis per skill, matched by name — deterministic, no Ollama."""
    import contemplative_agent.core.embeddings as embeddings

    names = [name for name, _description, _body in _SKILLS.values()]

    def _fake(texts: list[str]):
        vectors = []
        for text in texts:
            vector = [0.0] * len(names)
            for index, name in enumerate(names):
                if name in text:
                    vector[index] = 1.0
            if not any(vector):
                vector[0] = 1.0
            vectors.append(vector)
        return vectors

    monkeypatch.setattr(embeddings, "embed_texts", _fake)
    return _fake


class TestReadingShape:
    def _run(self, tmp_path: Path, *extra: str) -> tuple[int, dict]:
        home = _write_home(tmp_path)
        out = tmp_path / "reading.json"
        code = nrd.main(["--home", str(home), "--out", str(out), *extra])
        return code, (json.loads(out.read_text(encoding="utf-8")) if out.exists() else {})

    def test_the_reading_carries_every_block(self, tmp_path, stub_embeddings, capsys):
        code, reading = self._run(tmp_path)
        assert code == 0
        assert set(reading) == {
            "question",
            "provenance",
            "clusters",
            "top1_distributions",
            "coverage_at_thresholds",
            "rare_lane",
            "llm_history",
            "caveats",
        }
        summary = capsys.readouterr().out
        assert "clusters" in summary and "LLM judge" in summary

    def test_provenance_counts_the_corpus_it_read(self, tmp_path, stub_embeddings):
        _code, reading = self._run(tmp_path)
        provenance = reading["provenance"]
        # 10 rows persisted, 9 live (one superseded), 8 after the gated drop.
        assert provenance["store_patterns"] == 10
        assert provenance["live_patterns"] == 9
        assert provenance["live_ungated_patterns"] == 8
        assert provenance["clusters"] == 2
        assert provenance["singletons"] == 2
        assert provenance["skills"] == len(_SKILLS)
        assert provenance["arms"] == list(nrd.ARMS)
        assert provenance["rrf_k"] == nrd.DEFAULT_RRF_K

    def test_every_cluster_row_has_top3_for_every_arm(self, tmp_path, stub_embeddings):
        _code, reading = self._run(tmp_path)
        assert len(reading["clusters"]) == 2
        for row in reading["clusters"]:
            assert row["size"] == 3
            assert len(row["member_ids"]) == 3
            assert all(len(text) <= nrd.TEXT_PREVIEW_CHARS + 1 for text in row["texts"])
            for arm in nrd.ARMS:
                top3 = row["top3"][arm]
                assert 1 <= len(top3) <= nrd.TOP_N
                assert {"skill", "score"} == set(top3[0])
                # Ordered by score descending — a reader takes [0] as top-1.
                assert [entry["score"] for entry in top3] == sorted(
                    (entry["score"] for entry in top3), reverse=True
                )

    def test_distributions_and_thresholds_carry_their_denominators(self, tmp_path, stub_embeddings):
        _code, reading = self._run(tmp_path)
        for arm in nrd.ARMS:
            block = reading["top1_distributions"][arm]
            assert block["clusters"]["n"] == 2
            assert block["singletons"]["n"] == 2
            coverage = reading["coverage_at_thresholds"][arm]
            assert coverage["available"] is True
            assert [row["from_singleton_quantile"] for row in coverage["thresholds"]] == [
                "p50",
                "p75",
                "p90",
            ]
            for row in coverage["thresholds"]:
                assert row["clusters"] == 2
                assert 0.0 <= row["covered_fraction"] <= 1.0

    def test_the_llm_history_counts_only_judged_records(self, tmp_path, stub_embeddings):
        _code, reading = self._run(tmp_path)
        history = reading["llm_history"]
        assert history["available"] is True
        assert history["judged_records"] == 2
        # The 50 clusters of the fail_open record are excluded, so the rate is
        # 1/6 rather than 1/56.
        assert history["clusters_judged"] == 6
        assert history["clusters_called_covered"] == 1
        assert history["covered_rate"] == pytest.approx(1 / 6, abs=1e-4)
        assert history["unparsable_lines"] == 1
        assert history["records_with_another_verdict"] == 1

    def test_a_missing_novelty_log_is_named_not_silently_zero(self, tmp_path, stub_embeddings):
        home = _write_home(tmp_path)
        (home / "logs" / "insight-novelty.jsonl").unlink()
        out = tmp_path / "reading.json"
        assert nrd.main(["--home", str(home), "--out", str(out)]) == 0
        history = json.loads(out.read_text(encoding="utf-8"))["llm_history"]
        assert history == {
            "available": False,
            "reason": "NOVELTY_LOG_MISSING",
            "path": str(home / "logs" / "insight-novelty.jsonl"),
        }

    def test_quiet_writes_the_file_and_prints_nothing(self, tmp_path, stub_embeddings, capsys):
        code, reading = self._run(tmp_path, "--quiet")
        assert code == 0 and reading["clusters"]
        assert capsys.readouterr().out == ""


class TestAbstains:
    """ADR-0075's fault column: a broken seam exits 2 under a reason code and
    writes nothing, rather than a file of 0.0 similarities that would read as
    "the store covers nothing"."""

    def test_an_unavailable_embedding_backend_abstains(self, tmp_path, monkeypatch, capsys):
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: None)
        home = _write_home(tmp_path)
        out = tmp_path / "reading.json"
        assert nrd.main(["--home", str(home), "--out", str(out)]) == 2
        assert "reason=EMBEDDING_UNAVAILABLE" in capsys.readouterr().err
        assert not out.exists()

    def test_a_zero_norm_embedding_matrix_abstains(self, tmp_path, monkeypatch, capsys):
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0, 0.0] for _ in texts])
        home = _write_home(tmp_path)
        out = tmp_path / "reading.json"
        assert nrd.main(["--home", str(home), "--out", str(out)]) == 2
        assert "reason=EMBEDDING_DEGENERATE" in capsys.readouterr().err
        assert not out.exists()

    def test_a_missing_knowledge_store_abstains(self, tmp_path, capsys):
        assert nrd.main(["--home", str(tmp_path / "nope"), "--out", str(tmp_path / "o.json")]) == 2
        assert "reason=KNOWLEDGE_MISSING" in capsys.readouterr().err

    def test_a_missing_skill_store_abstains(self, tmp_path, capsys):
        home = _write_home(tmp_path)
        code = nrd.main(
            [
                "--home",
                str(home),
                "--skills-dir",
                str(tmp_path / "nope"),
                "--out",
                str(tmp_path / "o.json"),
            ]
        )
        assert code == 2
        assert "reason=SKILLS_DIR_MISSING" in capsys.readouterr().err

    def test_an_out_of_range_rrf_k_abstains(self, tmp_path, capsys):
        home = _write_home(tmp_path)
        code = nrd.main(["--home", str(home), "--out", str(tmp_path / "o.json"), "--rrf-k", "0"])
        assert code == 2
        assert "reason=BAD_RRF_K" in capsys.readouterr().err


class TestPercentile:
    def test_interpolates_and_survives_a_single_value(self):
        assert nrd._percentile([1.0], 50) == 1.0
        assert nrd._percentile([0.0, 1.0], 50) == pytest.approx(0.5)
        assert nrd._percentile([0.0, 1.0, 2.0, 3.0], 25) == pytest.approx(0.75)
