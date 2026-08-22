"""Tests for scripts/retrieval_recall_measure.py — the ADR-0097 slice-3 reading.

The script cannot be run against the real corpus by an agent (the staged
ledger lives under ``$MOLTBOOK_HOME/logs/**`` and the weekly reviews quote
external content), so everything it claims is asserted against synthetic
fixtures built here: a four-skill store, a staged ledger, and a review whose
reject sections name covering skills in prose the way the reviewer prompt
asks for.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import retrieval_recall_measure as rrm  # noqa: E402  # pyright: ignore[reportMissingImports]
from _scan import ScanError  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "retrieval_recall_measure.py"

_SKILLS = {
    "internal-process-audit-2026-05-02.md": (
        "internal-process-audit",
        "audit your own internal reasoning process step by step before answering",
        "Pause before answering and walk your own reasoning process step by step, "
        "naming each inference you made and the evidence it rested on.",
    ),
    "structural-constraint-mapping-scm-2026-06-11.md": (
        "structural-constraint-mapping-scm",
        "map the structural constraints of a system before proposing a change",
        "Draw the structural constraints of the system first: what is fixed, what "
        "is a limiting factor, and which boundary is really a condition.",
    ),
    "cross-reference-foundational-claims-2026-07-04.md": (
        "cross-reference-foundational-claims",
        "check a foundational claim against a second independent source",
        "When an argument rests on one foundational claim, find a second source "
        "that states it independently before building on it.",
    ),
    "assume-perfect-adversarial-understanding-2026-07-18.md": (
        "assume-perfect-adversarial-understanding",
        "assume the adversary understood you perfectly and still disagreed",
        "Treat disagreement as informed: assume the other side understood the "
        "argument perfectly and still rejected it, then ask what they saw.",
    ),
}

_LEDGER = [
    {
        "ts": "2026-08-16T08:00:00+00:00",
        "name": "suspend-interpretation-upon-premise-doubt",
        "description": (
            "audit your own internal reasoning process step by step before answering "
            "whenever a premise looks doubtful"
        ),
        "filename": "suspend-interpretation-upon-premise-doubt.md",
    },
    {
        "ts": "2026-08-16T08:00:01+00:00",
        "name": "limiting-factor-search",
        "description": (
            "map the structural constraints of a system before proposing a change so "
            "the limiting factor is found first"
        ),
        "filename": "limiting-factor-search.md",
    },
    {
        "ts": "2026-08-16T08:00:02+00:00",
        "name": "vague-virtue-thing",
        "description": "be thoughtful and considerate at all times",
        "filename": "vague-virtue-thing.md",
    },
    {
        "ts": "2026-08-16T08:00:03+00:00",
        "name": "some-new-thing",
        "description": "a genuinely distinct behaviour with no store analogue",
        "filename": "some-new-thing.md",
    },
]

_REVIEW = """Staged insight candidates for review (2026-08-22 week):

## 1. suspend-interpretation-upon-premise-doubt — RECOMMEND: reject
Already covered by `internal-process-audit`, which asks for the same
step-by-step self-audit before answering.

## 2. limiting-factor-search — RECOMMEND: reject
Covered by `structural-constraint-mapping-scm`; the limiting-factor search is
one move inside that mapping.

## 3. some-new-thing — RECOMMEND: adopt
No store skill states this; provenance spans four episodes.

## 4. vague-virtue-thing — RECOMMEND: reject
A vague virtue rather than a behaviour the agent can enact.

## 5. missing-from-ledger-name — RECOMMEND: reject
Covered by `internal-process-audit` as well.
"""


def _write_store(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    skills.mkdir()
    for filename, (name, description, body) in _SKILLS.items():
        (skills / filename).write_text(
            f"---\nname: {name}\ndescription: {description}\norigin: auto-extracted\n---\n\n"
            f"# {name}\n\n{body}\n",
            encoding="utf-8",
        )
    (skills / ".hidden.md").write_text("---\nname: hidden\n---\nbody\n", encoding="utf-8")
    return skills


def _write_ledger(tmp_path: Path, rows: list[dict] | None = None) -> Path:
    path = tmp_path / "insight-staged.jsonl"
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in (rows if rows is not None else _LEDGER)),
        encoding="utf-8",
    )
    return path


def _write_review(tmp_path: Path, text: str = _REVIEW, day: str = "2026-08-22") -> Path:
    reports = tmp_path / "analysis"
    reports.mkdir(exist_ok=True)
    path = reports / f"weekly-{day}-insight-review.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def corpus(tmp_path: Path):
    return _write_store(tmp_path), _write_ledger(tmp_path), _write_review(tmp_path)


def _pairs(review: Path, skills: Path, ledger: Path, *, policy: str = "exclude"):
    docs, _ = rrm.load_store(skills)
    rows, _ = rrm.load_candidates(ledger)
    sections, _ = rrm.parse_review(review.name, review.read_text(encoding="utf-8"))
    return docs, rrm.build_pairs(
        sections,
        store_names={doc.name.lower(): doc.name for doc in docs},
        ledger=rows,
        review_days={review.name: rrm._review_date(review.name)},
        name_only_queries=policy,
    )


class TestReviewParsing:
    def test_sections_and_verdicts(self, corpus):
        _, _, review = corpus
        sections, unnamed = rrm.parse_review(review.name, review.read_text(encoding="utf-8"))
        assert [s.verdict for s in sections] == ["reject", "reject", "adopt", "reject", "reject"]
        assert sections[0].candidate == "suspend-interpretation-upon-premise-doubt"
        assert unnamed == 0

    def test_heading_without_recommend_ends_the_previous_body(self):
        text = (
            "## 1. alpha-beta-gamma — RECOMMEND: reject\n"
            "Covered by `internal-process-audit`.\n\n"
            "## Notes\n"
            "Mentions `structural-constraint-mapping-scm` outside any section.\n"
        )
        sections, _ = rrm.parse_review("weekly-2026-08-22-insight-review.md", text)
        assert len(sections) == 1
        assert "structural-constraint-mapping-scm" not in sections[0].body

    def test_heading_without_a_candidate_name_is_counted(self):
        text = "## 1. — RECOMMEND: reject\nCovered by `internal-process-audit`.\n"
        sections, unnamed = rrm.parse_review("weekly-2026-08-22-insight-review.md", text)
        assert unnamed == 1
        assert sections[0].candidate is None

    def test_review_date_from_filename(self):
        assert rrm._review_date("weekly-2026-08-22-insight-review.md") == date(2026, 8, 22)
        assert rrm._review_date("something-else.md") is None


class TestGroundTruth:
    def test_labelled_pairs_and_their_exclusions(self, corpus):
        skills, ledger, review = corpus
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert [p.candidate for p in pairs] == [
            "suspend-interpretation-upon-premise-doubt",
            "limiting-factor-search",
        ]
        assert pairs[0].labels == ("internal-process-audit",)
        assert stats.rejections == 4
        # section 4 names no store skill; section 5 has no ledger text.
        assert stats.naming_nothing == 1
        assert stats.name_only_excluded == 1
        assert stats.naming_a_store_skill == 3
        assert stats.kept_pairs == 2

    def test_the_ground_truth_tally_has_no_silent_residual(self, corpus):
        """A rejection dropped for want of ledger text must still be visible.

        Before this was pinned, the reading called ``len(pairs)`` "rejections
        with a named store skill", so a reader summing the printed fields lost
        one rejection per name-only exclusion.
        """
        skills, ledger, review = corpus
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert stats.rejections == stats.naming_a_store_skill + stats.naming_nothing
        assert stats.naming_a_store_skill == stats.kept_pairs + stats.name_only_excluded
        assert stats.kept_pairs == len(pairs)

    def test_name_only_policy_include_keeps_the_fifth(self, corpus):
        skills, ledger, review = corpus
        _, (pairs, stats) = _pairs(review, skills, ledger, policy="include")
        assert len(pairs) == 3
        assert pairs[-1].query_kind == "name-only"
        assert stats.name_only_included == 1

    def test_batch_sibling_reference_is_not_a_coverage_label(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Shadowed by its batch sibling `some-new-thing`.\n\n"
            "## 2. some-new-thing — RECOMMEND: adopt\nKeep this one.\n",
        )
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert pairs == ()
        assert stats.naming_nothing == 1
        assert stats.unresolved_names == ()

    def test_unresolved_reviewer_name_is_named_under_a_stated_rule(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm` and by "
            "`ghost-skill-that-never-existed`; a well-known one-off.\n",
        )
        _, (_, stats) = _pairs(review, skills, ledger)
        # "well-known" and "one-off" are two-segment prose, not skill claims.
        assert stats.unresolved_names == ("ghost-skill-that-never-existed",)

    def test_multi_label_rejection_is_counted(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered jointly by `structural-constraint-mapping-scm` and "
            "`cross-reference-foundational-claims`.\n",
        )
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert stats.multi_label == 1
        assert len(pairs[0].labels) == 2

    def test_candidate_naming_itself_is_not_its_own_label(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(
            tmp_path,
            [
                {
                    "ts": "2026-08-16T08:00:00+00:00",
                    "name": "internal-process-audit",
                    "description": "a restaging of a theme already in the store",
                    "filename": "x.md",
                }
            ],
        )
        review = _write_review(
            tmp_path,
            "## 1. internal-process-audit — RECOMMEND: reject\n"
            "This restages `internal-process-audit`; covered by "
            "`cross-reference-foundational-claims` too.\n",
        )
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert pairs[0].labels == ("cross-reference-foundational-claims",)
        assert stats.candidates_also_in_store == 1

    def test_a_ledger_row_written_after_the_review_is_flagged(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(
            tmp_path,
            [
                {
                    "ts": "2026-09-05T08:00:00+00:00",
                    "name": "limiting-factor-search",
                    "description": "map the structural constraints of a system",
                    "filename": "b.md",
                }
            ],
        )
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm`.\n",
        )
        _, (_pairs_out, stats) = _pairs(review, skills, ledger)
        assert stats.ledger_row_after_review == 1

    def test_ledger_row_nearest_before_the_review_wins(self):
        ledger = {
            "theme": [
                ("2026-08-01T00:00:00+00:00", "old text"),
                ("2026-08-16T00:00:00+00:00", "reviewed text"),
                ("2026-09-05T00:00:00+00:00", "later restaging"),
            ]
        }
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 22))
        assert text == "reviewed text"
        assert late is False

    def test_only_later_rows_are_flagged(self):
        ledger = {"theme": [("2026-09-05T00:00:00+00:00", "later restaging")]}
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 22))
        assert text == "later restaging"
        assert late is True


class TestRetrievalPrimitives:
    def test_trigrams_and_jaccard(self):
        assert rrm.trigrams("ab") == frozenset()
        assert rrm.jaccard(rrm.trigrams("abcd"), rrm.trigrams("abcd")) == pytest.approx(1.0)
        assert rrm.jaccard(rrm.trigrams("abcd"), frozenset()) == 0.0

    def test_normalization_ignores_punctuation_and_case(self):
        assert rrm.trigrams("Alpha-Beta") == rrm.trigrams("alpha beta")

    def test_cosine_edges(self):
        assert rrm.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
        assert rrm.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
        # A dimension mismatch reads as dissimilar, never as an exception.
        assert rrm.cosine([1.0, 0.0], [1.0]) == 0.0

    def test_rrf_prefers_a_document_ranked_well_by_both(self):
        fused = rrm.rrf_rankings([("a", "b", "c")], [("b", "a", "c")], 60)
        assert fused[0][0] in ("a", "b")
        assert fused[0][-1] == "c"

    def test_ranking_ties_break_on_name(self):
        assert rrm._rank({"b": 1.0, "a": 1.0, "c": 0.5}) == ("a", "b", "c")


class TestReading:
    def _reading(self, corpus, **kwargs):
        skills, ledger, review = corpus
        docs, (pairs, stats) = _pairs(review, skills, ledger)
        return rrm.build_reading(
            pairs=pairs,
            docs=docs,
            label_stats=stats,
            reviews=[review.name],
            arms=kwargs.pop("arms", ("lexical",)),
            ks=kwargs.pop("ks", (1, 3, 5, 10)),
            rrf_k=60,
            min_pairs=kwargs.pop("min_pairs", 2),
            name_only_queries="exclude",
            partial_reasons=kwargs.pop("partial_reasons", ()),
        )

    def test_lexical_arm_finds_the_reviewer_named_skill_first(self, corpus):
        reading = self._reading(corpus)
        recall = reading["arms"]["lexical"]["recall"]
        assert recall["1"]["rate"] == pytest.approx(1.0)
        assert recall["1"]["pairs"] == 2

    def test_labelled_pair_count_leads_the_reading(self, corpus):
        reading = self._reading(corpus)
        assert next(iter(reading)) == "labelled_pairs"
        assert reading["labelled_pairs"] == 2

    def test_below_the_floor_the_reading_says_it_is_not_a_decision_input(self, corpus):
        reading = self._reading(corpus, min_pairs=30)
        assert reading["decision_input"] is False
        assert reading["min_pairs_for_decision"] == 30
        assert "BELOW_DECISION_FLOOR" in reading["reasons"]

    def test_every_rate_carries_its_denominator_and_interval(self, corpus):
        for row in self._reading(corpus)["arms"]["lexical"]["recall"].values():
            assert row["pairs"] == 2
            assert row["ci95"] is not None

    def test_corpus_shape_is_printed_for_the_length_bias(self, corpus):
        chars = self._reading(corpus)["corpus_doc_chars"]
        assert chars["min"] <= chars["median"] <= chars["max"]
        assert self._reading(corpus)["corpus_skills"] == 4

    def test_no_labelled_pairs_abstains_rather_than_printing_zero(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(tmp_path, "## 1. some-new-thing — RECOMMEND: adopt\nKeep it.\n")
        docs, (pairs, stats) = _pairs(review, skills, ledger)
        with pytest.raises(ScanError) as excinfo:
            rrm.build_reading(
                pairs=pairs,
                docs=docs,
                label_stats=stats,
                reviews=[review.name],
                arms=("lexical",),
                ks=(1,),
                rrf_k=60,
                min_pairs=2,
                name_only_queries="exclude",
                partial_reasons=(),
            )
        assert excinfo.value.reason == "NO_LABELLED_PAIRS"

    def test_partial_reasons_are_carried_into_the_reading(self, corpus):
        reading = self._reading(corpus, partial_reasons=("LEDGER_PARTIAL_PARSE",))
        assert "LEDGER_PARTIAL_PARSE" in reading["reasons"]


class TestEmbeddingArm:
    """Fault column for the one non-deterministic seam (ADR-0077)."""

    def _prepare(self, corpus, arms):
        skills, ledger, review = corpus
        docs, (pairs, stats) = _pairs(review, skills, ledger)
        return lambda: rrm.build_reading(
            pairs=pairs,
            docs=docs,
            label_stats=stats,
            reviews=[review.name],
            arms=arms,
            ks=(1, 3),
            rrf_k=60,
            min_pairs=2,
            name_only_queries="exclude",
            partial_reasons=(),
        )

    def test_unreachable_ollama_abstains_per_arm_not_per_run(self, corpus):
        # conftest points OLLAMA_BASE_URL at a dead port, so embed_texts
        # returns None: the cosine and union arms must go unavailable while
        # the lexical arm still reports.
        reading = self._prepare(corpus, ("lexical", "cosine", "union"))()
        assert reading["arms"]["cosine"] == {
            "available": False,
            "reason": "EMBEDDING_UNAVAILABLE",
        }
        assert reading["arms"]["union"]["available"] is False
        assert reading["arms"]["lexical"]["available"] is True
        assert "EMBEDDING_UNAVAILABLE" in reading["reasons"]

    def test_cosine_only_run_with_no_backend_abstains_entirely(self, corpus):
        with pytest.raises(ScanError) as excinfo:
            self._prepare(corpus, ("cosine",))()
        assert excinfo.value.reason == "NO_ARM_AVAILABLE"

    def test_uninstalled_package_reads_differently_from_a_dead_ollama(self, corpus, monkeypatch):
        monkeypatch.setitem(sys.modules, "contemplative_agent.core.embeddings", None)
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["reason"] == "EMBEDDING_IMPORT_FAILED"
        assert "EMBEDDING_IMPORT_FAILED" in reading["reasons"]

    def test_short_embedding_response_abstains_instead_of_misaligning(self, corpus, monkeypatch):
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[1.0, 0.0]])
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["available"] is False

    def test_over_long_embedding_response_abstains_too(self, corpus, monkeypatch):
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[1.0, 0.0]] * 99)
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["available"] is False

    def test_a_good_doc_batch_with_a_bad_query_batch_still_abstains(self, corpus, monkeypatch):
        """The second embed call has its own guard; a mis-sized query matrix
        must not reach the strict zip in recall_at_k."""
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(
            embeddings,
            "embed_texts",
            lambda texts: [[1.0, 0.0]] * (len(texts) if len(texts) == len(_SKILLS) else 99),
        )
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["available"] is False

    def test_stubbed_embeddings_produce_a_cosine_and_union_reading(self, corpus, monkeypatch):
        import contemplative_agent.core.embeddings as embeddings

        skills, ledger, review = corpus
        docs, (pairs, _stats) = _pairs(review, skills, ledger)
        # One axis per document; each query is pointed at its labelled skill,
        # so a correct arm scores recall@1 = 1.0 and a broken one scores 0.
        axes = {doc.name: index for index, doc in enumerate(docs)}

        def _fake(texts: list[str]):
            vectors = []
            for text in texts:
                vector = [0.0] * len(docs)
                for name, index in axes.items():
                    if name in text:
                        vector[index] = 1.0
                if not any(vector):
                    # A query: point it at the skill its label names.
                    for pair in pairs:
                        if text.startswith(pair.candidate):
                            vector[axes[pair.labels[0]]] = 1.0
                vectors.append(vector)
            return vectors

        monkeypatch.setattr(embeddings, "embed_texts", _fake)
        reading = self._prepare(corpus, ("lexical", "cosine", "union"))()
        assert reading["arms"]["cosine"]["recall"]["1"]["rate"] == pytest.approx(1.0)
        assert reading["arms"]["union"]["available"] is True
        assert reading["arms"]["union"]["recall"]["1"]["rate"] == pytest.approx(1.0)
        assert reading["arms"]["cosine"]["docs_truncated_for_embedding"] == 0


class TestLoaders:
    def test_frontmatter_name_beats_the_dated_filename(self, tmp_path):
        docs, unreadable = rrm.load_store(_write_store(tmp_path))
        assert unreadable == 0
        assert "internal-process-audit" in {doc.name for doc in docs}
        assert all(not doc.filename.startswith(".") for doc in docs)

    def test_store_without_frontmatter_falls_back_to_the_stem(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "legacy-skill.md").write_text("# Legacy\n\nbody\n", encoding="utf-8")
        docs, _ = rrm.load_store(skills)
        assert docs[0].name == "legacy-skill"

    def test_missing_store_abstains(self, tmp_path):
        with pytest.raises(ScanError) as excinfo:
            rrm.load_store(tmp_path / "nope")
        assert excinfo.value.reason == "SKILLS_DIR_MISSING"

    def test_empty_store_abstains(self, tmp_path):
        (tmp_path / "skills").mkdir()
        with pytest.raises(ScanError) as excinfo:
            rrm.load_store(tmp_path / "skills")
        assert excinfo.value.reason == "SKILLS_EMPTY"

    def test_malformed_ledger_lines_are_counted_not_fatal(self, tmp_path):
        path = tmp_path / "insight-staged.jsonl"
        path.write_text(
            json.dumps(_LEDGER[0])
            + "\n\n   \n{broken\n"
            + '"bare"\n'
            + '{"description": "no name"}\n',
            encoding="utf-8",
        )
        rows, malformed = rrm.load_candidates(path)
        # Blank lines are not malformed; the three broken records are.
        assert malformed == 3
        assert "suspend-interpretation-upon-premise-doubt" in rows

    def test_missing_ledger_abstains(self, tmp_path):
        with pytest.raises(ScanError) as excinfo:
            rrm.load_candidates(tmp_path / "nope.jsonl")
        assert excinfo.value.reason == "CANDIDATES_MISSING"

    def test_unreadable_ledger_abstains_under_its_own_code(self, tmp_path):
        # A directory is an OSError that is not FileNotFoundError: "the file
        # is not there" and "the file is there and unreadable" are different
        # repairs and must not share a reason code.
        (tmp_path / "as-a-dir").mkdir()
        with pytest.raises(ScanError) as excinfo:
            rrm.load_candidates(tmp_path / "as-a-dir")
        assert excinfo.value.reason == "CANDIDATES_UNREADABLE"

    def test_undecodable_skill_file_is_counted_not_fatal(self, tmp_path):
        skills = _write_store(tmp_path)
        (skills / "broken.md").write_bytes(b"\xff\xfe not utf-8\n")
        docs, unreadable = rrm.load_store(skills)
        assert unreadable == 1
        assert len(docs) == len(_SKILLS)

    def test_malformed_review_date_reads_as_no_date(self):
        assert rrm._review_date("weekly-2026-13-45-insight-review.md") is None

    def test_wilson_zero_trials_is_none(self):
        assert rrm.wilson_ci(0, 0) is None

    @pytest.mark.parametrize("spec", ["", "0", "abc", "-2"])
    def test_bad_k_abstains(self, spec):
        with pytest.raises(ScanError) as excinfo:
            rrm._parse_k(spec)
        assert excinfo.value.reason == "BAD_K"

    def test_k_is_deduped_and_sorted(self):
        assert rrm._parse_k("10, 3,3 ,1") == (1, 3, 10)

    @pytest.mark.parametrize("with_dir", [True, False])
    def test_missing_reviews_abstain(self, tmp_path, with_dir):
        target = (tmp_path / "nope") if with_dir else None
        if not with_dir:
            (tmp_path / "empty").mkdir()
        with pytest.raises(ScanError) as excinfo:
            rrm._collect_reviews([], target if with_dir else None)
        assert excinfo.value.reason == "REVIEWS_MISSING"

    def test_review_dir_glob_and_dedup(self, tmp_path):
        review = _write_review(tmp_path)
        collected = rrm._collect_reviews([review], review.parent)
        assert collected == [review]


class TestCli:
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            encoding="utf-8",
            timeout=120,
        )

    def test_end_to_end_lexical_arm(self, corpus):
        skills, ledger, review = corpus
        result = self._run(
            "--review-dir",
            str(review.parent),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
            "--min-pairs",
            "2",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        assert reading["labelled_pairs"] == 2
        assert reading["decision_input"] is True
        assert reading["arms"]["lexical"]["recall"]["1"]["rate"] == pytest.approx(1.0)
        assert reading["ground_truth"]["rejections"] == 4

    def test_below_floor_warns_on_stderr_and_still_prints(self, corpus):
        skills, ledger, review = corpus
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
        )
        assert result.returncode == 0, result.stderr
        assert "BELOW_DECISION_FLOOR" in result.stderr
        assert json.loads(result.stdout)["decision_input"] is False

    def test_missing_skills_dir_abstains(self, corpus, tmp_path):
        _, ledger, review = corpus
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(tmp_path / "nope"),
            "--arm",
            "lexical",
        )
        assert result.returncode == 2
        assert "SKILLS_DIR_MISSING" in result.stderr
        assert result.stdout == ""

    def test_two_reviews_sharing_a_basename_are_named_not_silently_merged(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        first = _write_review(tmp_path)
        second_dir = tmp_path / "other"
        second_dir.mkdir()
        second = second_dir / first.name
        second.write_text(_REVIEW, encoding="utf-8")
        result = self._run(
            "--review",
            str(first),
            "--review",
            str(second),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
            "--min-pairs",
            "2",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        assert "DUPLICATE_REVIEW_NAME" in reading["reasons"]
        assert reading["labelled_pairs"] == 2

    def test_no_labelled_pairs_abstains_from_the_cli(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(tmp_path, "## 1. some-new-thing — RECOMMEND: adopt\nKeep it.\n")
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
        )
        assert result.returncode == 2
        assert "NO_LABELLED_PAIRS" in result.stderr
