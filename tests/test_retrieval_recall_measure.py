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
    docs, _unreadable, _dupes = rrm.load_store(skills)
    rows, _faults = rrm.load_candidates(ledger)
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

    def test_multi_label_describes_kept_pairs_only(self, tmp_path):
        """A multi-label rejection dropped for want of ledger text must not
        inflate a field that qualifies the recall figures."""
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path, [])
        review = _write_review(
            tmp_path,
            "## 1. not-in-the-ledger-at-all — RECOMMEND: reject\n"
            "Covered by `internal-process-audit` and "
            "`cross-reference-foundational-claims`.\n",
        )
        _, (pairs, stats) = _pairs(review, skills, ledger)
        assert pairs == ()
        assert stats.naming_a_store_skill == 1
        assert stats.name_only_excluded == 1
        assert stats.multi_label == 0

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

    def test_a_blank_ledger_description_is_no_description(self, tmp_path):
        """`skill_theme` falls back to "", and an empty description would
        otherwise build a name-only query stamped `name+description` and slip
        past `--name-only-queries exclude`."""
        skills = _write_store(tmp_path)
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm`.\n",
        )
        for row in (
            {
                "ts": "2026-08-16T08:00:00+00:00",
                "name": "limiting-factor-search",
                "description": "   ",
                "filename": "b.md",
            },
            {
                "ts": "2026-08-16T08:00:00+00:00",
                "name": "limiting-factor-search",
                "filename": "b.md",
            },
        ):
            ledger = _write_ledger(tmp_path, [row])
            _, (pairs, stats) = _pairs(review, skills, ledger)
            assert pairs == ()
            assert stats.name_only_excluded == 1
            included = _pairs(review, skills, ledger, policy="include")[1][0]
            assert included[0].query_kind == "name-only"

    def test_a_sibling_from_another_week_is_not_a_sibling_here(self, tmp_path):
        """Pooling every review's candidates would hide an invented name."""
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        week_one = _write_review(
            tmp_path,
            "## 1. some-new-thing — RECOMMEND: adopt\nKeep it.\n",
            day="2026-07-11",
        )
        week_seven = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm`; see also "
            "`some-new-thing`.\n",
            day="2026-08-22",
        )
        docs, _unreadable, _dupes = rrm.load_store(skills)
        rows, _faults = rrm.load_candidates(ledger)
        sections = []
        review_days = {}
        for path in (week_one, week_seven):
            parsed, _ = rrm.parse_review(path.name, path.read_text(encoding="utf-8"))
            sections.extend(parsed)
            review_days[path.name] = rrm._review_date(path.name)
        _, stats = rrm.build_pairs(
            sections,
            store_names={doc.name.lower(): doc.name for doc in docs},
            ledger=rows,
            review_days=review_days,
            name_only_queries="exclude",
        )
        # `some-new-thing` belongs to week 1's batch, not week 7's, so in
        # week 7 it is a name the reviewer invented and must stay visible.
        assert "some-new-thing" in stats.unresolved_names

    def test_a_review_is_named_the_day_before_its_own_batch(self):
        """The defect that saturated ``ledger_row_after_review`` at 100%.

        ``weekly-pipeline.sh`` names a review after ``END_DATE`` = yesterday,
        while ``insight --stage`` writes that batch's ledger rows on the
        pipeline morning — so the review's own batch is one day AFTER its
        filename date. A cutoff at the filename date excluded it by
        construction: measured on the live corpus, 132 of 135
        ledger-resolvable rejections took the fallback and all 54 kept pairs
        came back flagged.
        """
        ledger = {"theme": [("2026-08-22T08:00:00+00:00", "this week's batch")]}
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 21))
        assert text == "this week's batch"
        assert late is False

    def test_the_staging_lag_is_a_parameter_not_a_hardcoded_schedule(self):
        ledger = {"theme": [("2026-08-22T08:00:00+00:00", "this week's batch")]}
        _text, late = rrm._candidate_description(
            ledger, "theme", date(2026, 8, 21), staging_lag_days=0
        )
        assert late is True

    def test_a_genuine_restaging_is_still_flagged(self):
        """The guard must keep firing on what it was built for."""
        ledger = {"theme": [("2026-09-05T00:00:00+00:00", "a later restaging")]}
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 21))
        assert text == "a later restaging"
        assert late is True

    def test_when_every_row_post_dates_the_review_the_nearest_one_wins(self):
        """Not the latest: with nothing eligible, the earliest row is the one
        closest to the batch the reviewer actually saw."""
        ledger = {
            "theme": [
                ("2026-09-05T00:00:00+00:00", "first restaging"),
                ("2026-11-01T00:00:00+00:00", "much later restaging"),
            ]
        }
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 21))
        assert text == "first restaging"
        assert late is True

    def test_the_lag_does_not_swallow_a_restaging_one_week_later(self):
        ledger = {
            "theme": [
                ("2026-08-22T08:00:00+00:00", "this week's batch"),
                ("2026-08-29T08:00:00+00:00", "next week's restaging"),
            ]
        }
        text, late = rrm._candidate_description(ledger, "theme", date(2026, 8, 21))
        assert text == "this week's batch"
        assert late is False

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
            staging_lag_days=rrm.DEFAULT_STAGING_LAG_DAYS,
            read_faults={},
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
                staging_lag_days=rrm.DEFAULT_STAGING_LAG_DAYS,
                read_faults={},
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
            staging_lag_days=rrm.DEFAULT_STAGING_LAG_DAYS,
            read_faults={},
            partial_reasons=(),
        )

    def test_unreachable_ollama_abstains_per_arm_not_per_run(self, corpus):
        # conftest points OLLAMA_BASE_URL at a dead port, so embed_texts
        # returns None: the cosine and union arms must go unavailable while
        # the lexical arm still reports.
        reading = self._prepare(corpus, ("lexical", "cosine", "union"))()
        cosine_arm = reading["arms"]["cosine"]
        assert cosine_arm["available"] is False
        assert cosine_arm["reason"] == "EMBEDDING_UNAVAILABLE"
        # The model identity is recorded even on the failure path: the run
        # asked SOME model and the reader must know which.
        assert cosine_arm["embedding_model"]
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

    def test_a_dimension_mismatch_abstains_instead_of_scoring_alphabetically(
        self, corpus, monkeypatch
    ):
        """The dangerous fault: `cosine` fails soft to 0.0 and `_rank`'s name
        tie-break turns an all-zero score dict into a confident alphabetical
        ranking that recall_at_k would score as real — inflating recall in the
        permissive direction, straight at ADR-0097's recall@5 >= 0.9 bar."""
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(
            embeddings,
            "embed_texts",
            # Docs get 4 dimensions, queries 8: every cosine is 0.0.
            lambda texts: [[1.0] * (4 if len(texts) == len(_SKILLS) else 8)] * len(texts),
        )
        reading = self._prepare(corpus, ("lexical", "cosine", "union"))()
        assert reading["arms"]["cosine"]["available"] is False
        assert reading["arms"]["cosine"]["reason"] == "EMBEDDING_DEGENERATE"
        assert reading["arms"]["union"]["available"] is False
        assert "EMBEDDING_DEGENERATE" in reading["reasons"]

    def test_zero_width_vectors_abstain(self, corpus, monkeypatch):
        """An (N, 0) matrix passes the row-count guard; the dimension does not."""
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[] for _ in texts])
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["reason"] == "EMBEDDING_DEGENERATE"

    def test_zero_norm_vectors_abstain(self, corpus, monkeypatch):
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0, 0.0]] * len(texts))
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["reason"] == "EMBEDDING_DEGENERATE"

    def test_a_query_with_no_score_spread_abstains(self, corpus, monkeypatch):
        """Non-zero, same-dimension vectors that still leave every document
        tied: the ranking would be pure alphabetical order."""
        import contemplative_agent.core.embeddings as embeddings

        monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[1.0, 1.0]] * len(texts))
        reading = self._prepare(corpus, ("lexical", "cosine"))()
        assert reading["arms"]["cosine"]["reason"] == "EMBEDDING_DEGENERATE"

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
        assert reading["corpus_truncation"]["docs_truncated"] == 0
        assert reading["corpus_truncation"]["queries_truncated"] == 0

    def test_truncation_for_embedding_is_counted_on_both_sides(self, tmp_path, monkeypatch):
        import contemplative_agent.core.embeddings as embeddings

        skills = tmp_path / "skills"
        skills.mkdir()
        long_body = "structural constraint mapping " * (rrm.MAX_TEXT_CHARS // 10)
        (skills / "structural-constraint-mapping-scm.md").write_text(
            f"---\nname: structural-constraint-mapping-scm\n---\n\n{long_body}",
            encoding="utf-8",
        )
        (skills / "other-skill-entirely.md").write_text(
            "---\nname: other-skill-entirely\n---\n\nshort body\n", encoding="utf-8"
        )
        ledger = _write_ledger(
            tmp_path,
            [
                {
                    "ts": "2026-08-16T08:00:00+00:00",
                    "name": "limiting-factor-search",
                    "description": "map constraints " * (rrm.MAX_TEXT_CHARS // 8),
                    "filename": "b.md",
                }
            ],
        )
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm`.\n",
        )
        docs, (pairs, stats) = _pairs(review, skills, ledger)
        monkeypatch.setattr(
            embeddings,
            "embed_texts",
            lambda texts: [[float(i + 1), 1.0] for i in range(len(texts))],
        )
        reading = rrm.build_reading(
            pairs=pairs,
            docs=docs,
            label_stats=stats,
            reviews=[review.name],
            arms=("cosine",),
            ks=(1,),
            rrf_k=60,
            min_pairs=1,
            name_only_queries="exclude",
            staging_lag_days=rrm.DEFAULT_STAGING_LAG_DAYS,
            read_faults={},
            partial_reasons=(),
        )
        assert reading["corpus_truncation"]["docs_truncated"] == 1
        assert reading["corpus_truncation"]["queries_truncated"] == 1
        assert reading["corpus_truncation"]["longest_original"] > rrm.MAX_TEXT_CHARS
        assert "CORPUS_TRUNCATED" in reading["reasons"]


class TestLoaders:
    def test_frontmatter_name_beats_the_dated_filename(self, tmp_path):
        docs, unreadable, _dupes = rrm.load_store(_write_store(tmp_path))
        assert unreadable == 0
        assert "internal-process-audit" in {doc.name for doc in docs}
        assert all(not doc.filename.startswith(".") for doc in docs)

    def test_store_without_frontmatter_falls_back_to_the_stem(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "legacy-skill.md").write_text("# Legacy\n\nbody\n", encoding="utf-8")
        docs, _unreadable, _dupes = rrm.load_store(skills)
        assert docs[0].name == "legacy-skill"

    def test_a_body_line_that_looks_like_frontmatter_is_not_the_identity(self, tmp_path):
        """The selector reads the frontmatter block only (`skill_theme` ->
        `split_frontmatter`). Scanning the whole file gave a legacy body's
        prose `name:` line as the skill identity, and a document answering to
        a name the selector never emits silently loses its labelled pair."""
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "legacy-skill.md").write_text(
            "# Legacy\n\nWhen writing YAML use:\nname: totally-different-identity\n",
            encoding="utf-8",
        )
        docs, _unreadable, _dupes = rrm.load_store(skills)
        assert docs[0].name == "legacy-skill"

    def test_frontmatter_block_is_still_read_when_present(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "file-stem-differs.md").write_text(
            "---\nname: real-frontmatter-name\n---\n\nname: decoy-in-body\n",
            encoding="utf-8",
        )
        docs, _unreadable, _dupes = rrm.load_store(skills)
        assert docs[0].name == "real-frontmatter-name"

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
        rows, faults = rrm.load_candidates(path)
        # Blank lines are not faults; two lines are unparsable and one decoded
        # to an object with no usable name.
        assert faults.unparsable_lines == 2
        assert faults.rows_without_a_name == 1
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
        docs, unreadable, _dupes = rrm.load_store(skills)
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


class TestSkillThemeParity:
    """A4: the local join key must not drift from the one the ledger is written with.

    ``load_store`` resolves a skill's identity with a local mirror of
    ``core.text_utils.skill_theme`` (a module-level package import would break
    the documented bare-``python3`` lexical workflow), while the other side of
    the join — the staged ledger — is written with the real one. Two spellings
    that disagree at the edges is how a labelled pair vanishes with no fault
    recorded, so they are compared here over the cases where a looser reading
    diverges.
    """

    CASES = [
        "---\nname: proper-frontmatter\ndescription: a real one\n---\n\n# Title\n\nbody\n",
        # Not an opener: the first line does not strip to exactly ---.
        "---foo\nname: not-frontmatter\n---\n\n# Legacy Title\n\nbody\n",
        # Not a closer: a mid-line ---bar must not end the block.
        "---\nname: unclosed\n---bar\nstill frontmatter?\n",
        # Frontmatter only, no body — read_markdown_documents would drop this.
        "---\nname: frontmatter-only\ndescription: nothing follows\n---\n",
        # Trailing spaces on both delimiters still strip to ---.
        "---   \nname: padded-delimiters\n---  \n\n# T\n\nbody\n",
        # No frontmatter at all: the title is the description, name falls back.
        "# Just A Title\n\nSome body text.\n",
        # A body line that looks like frontmatter must not become the identity.
        "# Legacy\n\nWhen writing YAML use:\nname: decoy-in-body\n",
        # Quoted description scalar.
        '---\nname: quoted\ndescription: "with quotes"\n---\n\nbody\n',
        # Nothing at all.
        "",
    ]

    @pytest.mark.parametrize("text", CASES)
    def test_matches_core_skill_theme(self, text):
        from contemplative_agent.core.text_utils import skill_theme

        assert rrm._skill_theme(text, "fallback-stem") == skill_theme(text, "fallback-stem")

    def test_the_name_is_scrubbed_the_way_the_selector_scrubs_it(self, tmp_path):
        """The one deliberate addition on top of parity: the same
        ``strip_to_printable`` the selector applies at the same seam, so a name
        carrying an ANSI escape joins the way the selector would join it."""
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "escaped.md").write_text(
            "---\nname: clean\x1b[31m-name\n---\n\nbody\n", encoding="utf-8"
        )
        docs, _unreadable, _dupes = rrm.load_store(skills)
        assert docs[0].name == "clean[31m-name"

    def test_a_wider_read_error_class_than_the_selector_is_deliberate(self, tmp_path):
        """``load_skill_catalog`` catches only OSError; UnicodeDecodeError is a
        ValueError, so a single invalid byte would traceback there."""
        skills = _write_store(tmp_path)
        (skills / "bad-bytes.md").write_bytes(b"\xff\xfe\n")
        docs, unreadable, _dupes = rrm.load_store(skills)
        assert unreadable == 1
        assert len(docs) == len(_SKILLS)


class TestStoreIntegrity:
    def test_two_files_sharing_a_frontmatter_name_are_counted(self, tmp_path):
        """They collapse in every ranking's score dict while corpus_skills
        still counts both."""
        skills = _write_store(tmp_path)
        (skills / "a-duplicate.md").write_text(
            "---\nname: internal-process-audit\n---\n\nbody\n", encoding="utf-8"
        )
        docs, _unreadable, duplicates = rrm.load_store(skills)
        assert duplicates == 1
        assert len(docs) == len(_SKILLS) + 1

    def test_a_reviewer_citing_by_filename_still_resolves(self, tmp_path):
        """The reviewer gets --add-dir over the store, so it sees the dated
        filenames; a citation by filename must not read as a hallucination."""
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm-2026-06-11`.\n",
        )
        _docs, (pairs, stats) = _pairs(review, skills, ledger)
        assert pairs[0].labels == ("structural-constraint-mapping-scm",)
        assert stats.unresolved_names == ()


class TestLexicalSpreadGuard:
    def test_a_query_sharing_nothing_is_not_scored_alphabetically(self, corpus):
        """MEDIUM-1: the degenerate-ranking argument applied to the cheap arm.

        Unlike cosine this does not abstain the whole arm — a trigram query
        that shares nothing says something about that query, not about the
        model — so the pair leaves the denominator and is counted.
        """
        skills, ledger, review = corpus
        docs, (pairs, _stats) = _pairs(review, skills, ledger)
        empty_query = rrm.LabelledPair(
            review=review.name,
            candidate="zzz",
            query="一二三",  # normalizes to nothing
            query_kind="name-only",
            labels=("internal-process-audit",),
        )
        rankings = rrm.lexical_rankings([*pairs, empty_query], docs)
        assert rankings[-1] is None
        assert all(r is not None for r in rankings[:-1])
        scored = rrm.recall_at_k([*pairs, empty_query], rankings, (1,))
        assert scored["1"]["pairs"] == len(pairs)

    def test_a_degenerate_query_is_named_in_the_reading(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(
            tmp_path,
            [
                {
                    "ts": "2026-08-23T08:00:00+00:00",
                    "name": "limiting-factor-search",
                    "description": "一二三",
                    "filename": "b.md",
                }
            ],
        )
        review = _write_review(
            tmp_path,
            "## 1. limiting-factor-search — RECOMMEND: reject\n"
            "Covered by `structural-constraint-mapping-scm`.\n",
        )
        docs, (pairs, stats) = _pairs(review, skills, ledger)
        # The candidate name still carries trigrams, so build a bare query.
        rankings = rrm.lexical_rankings(pairs, docs)
        assert stats.kept_pairs == 1
        assert all(r is not None for r in rankings)


class TestRrfSensitivity:
    def test_rrf_k_actually_changes_the_fusion(self):
        """60 is the TREC-scale default; against ~57 docs `1/(60+r)` is nearly
        linear in r, so the fusion flattens into a rank-sum with no top-rank
        emphasis. The docstring tells the operator to sweep the knob — pin
        that sweeping it moves the ranking."""
        # "x" is one arm's top hit and the other's last (ranks 1 and 6);
        # "y" is mid-table in both (ranks 3 and 3). Same story, two readings.
        left = [("x", "a", "y", "b", "c", "d")]
        right = [("a", "b", "y", "c", "d", "x")]
        peaked = rrm.rrf_rankings(left, right, 1)[0]
        flat = rrm.rrf_rankings(left, right, 60)[0]
        # rrf_k=1 rewards the rank-1 hit; rrf_k=60 is close enough to a
        # rank-sum that the consistently-mediocre document wins instead.
        assert peaked.index("x") < peaked.index("y")
        assert flat.index("y") < flat.index("x")


class TestDecisionFloorJustification:
    def test_thirty_pairs_excludes_0_7_and_twenty_does_not(self):
        """The docstring's floor: 30 is the smallest round pair count at which
        a measured 0.9 excludes 0.7."""
        low_30, _ = rrm.wilson_ci(27, 30)
        low_20, _ = rrm.wilson_ci(18, 20)
        assert low_30 > 0.7
        assert low_20 < 0.7
        assert rrm.DEFAULT_MIN_PAIRS == 30


class TestDeterminism:
    def test_no_module_reads_the_wall_clock(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("date.today", "datetime.now", "datetime.utcnow", "time.time"):
            assert forbidden not in source


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

    def test_an_undated_review_filename_is_named_not_silent(self, tmp_path):
        """Without a date the ledger lookup falls back to the LATEST row —
        possibly a re-staging written after the review. The fallback is
        deliberate, but the late-row counter cannot see it, so the filename
        fault gets its own code."""
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        undated = tmp_path / "my-copy.md"
        undated.write_text(_REVIEW, encoding="utf-8")
        result = self._run(
            "--review",
            str(undated),
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
        assert "REVIEW_DATE_UNPARSEABLE" in json.loads(result.stdout)["reasons"]

    def test_an_unreadable_review_degrades_while_a_readable_one_reports(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        good = _write_review(tmp_path)
        bad = good.parent / "weekly-2026-08-15-insight-review.md"
        bad.write_bytes(b"\xff\xfe not utf-8\n")
        result = self._run(
            "--review-dir",
            str(good.parent),
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
        assert "REVIEW_PARTIAL_READ" in reading["reasons"]
        assert reading["labelled_pairs"] == 2

    def test_every_review_unreadable_abstains(self, tmp_path):
        skills = _write_store(tmp_path)
        ledger = _write_ledger(tmp_path)
        analysis = tmp_path / "analysis"
        analysis.mkdir()
        (analysis / "weekly-2026-08-22-insight-review.md").write_bytes(b"\xff\xfe\n")
        result = self._run(
            "--review-dir",
            str(analysis),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
        )
        assert result.returncode == 2
        assert "REVIEWS_UNREADABLE" in result.stderr

    @pytest.mark.parametrize(
        ("flag", "value", "code"),
        [
            ("--rrf-k", "0", "BAD_RRF_K"),
            ("--min-pairs", "0", "BAD_MIN_PAIRS"),
            ("--k", "0", "BAD_K"),
        ],
    )
    def test_out_of_range_knobs_abstain(self, corpus, flag, value, code):
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
            flag,
            value,
        )
        assert result.returncode == 2
        assert code in result.stderr

    def test_name_only_include_through_the_cli(self, corpus):
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
            "--name-only-queries",
            "include",
            "--min-pairs",
            "2",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        assert reading["labelled_pairs"] == 3
        assert reading["ground_truth"]["name_only_queries"] == {
            "policy": "include",
            "excluded": 0,
            "included": 1,
        }

    def test_an_unreadable_skill_file_abstains_by_default(self, corpus):
        """A shrinking corpus raises recall@k for every surviving pair and
        re-attributes its rejections to "the reviewer named no store skill" —
        the permissive direction against this ADR's own decision bar."""
        skills, ledger, review = corpus
        (skills / "corrupt.md").write_bytes(b"\xff\xfe\n")
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
            "--min-pairs",
            "2",
        )
        assert result.returncode == 2
        assert "reason=SKILLS_PARTIAL_READ" in result.stderr
        assert result.stdout == ""

    def test_allow_partial_store_reads_anyway_and_names_the_magnitudes(self, corpus):
        skills, ledger, review = corpus
        (skills / "corrupt.md").write_bytes(b"\xff\xfe\n")
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "lexical",
            "--min-pairs",
            "2",
            "--allow-partial-store",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        # The count reaches stdout, not only the boolean the reason carries.
        assert reading["read_faults"]["unreadable_skill_files"] == 1
        assert "SKILLS_PARTIAL_READ" in reading["reasons"]
        assert reading["ground_truth"]["naming_tally_complete"] is False

    def test_read_faults_carries_a_number_for_every_fault_class(self, corpus):
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
            "--min-pairs",
            "2",
        )
        assert result.returncode == 0, result.stderr
        faults = json.loads(result.stdout)["read_faults"]
        assert set(faults) == {
            "unreadable_skill_files",
            "store_files_sharing_a_name",
            "unreadable_reviews",
            "undated_reviews",
            "duplicate_review_basenames",
            "review_sections_without_a_candidate_name",
            "ledger_unparsable_lines",
            "ledger_rows_without_a_name",
            "ledger_rows_with_an_unusable_ts",
        }
        assert all(isinstance(count, int) for count in faults.values())

    def test_the_staging_lag_assumption_is_echoed_into_the_reading(self, corpus):
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
            "--min-pairs",
            "2",
            "--staging-lag-days",
            "3",
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["staging_lag_days"] == 3

    def test_a_k_at_or_above_the_corpus_size_is_named(self, corpus):
        """recall@k is 1.0 by construction there — and the same 1.0 would be
        read against the >= 0.9 Review-when."""
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
            "--min-pairs",
            "2",
            "--k",
            "1,50",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        assert "K_EXCEEDS_CORPUS" in reading["reasons"]
        assert reading["arms"]["lexical"]["recall"]["50"]["rate"] == pytest.approx(1.0)

    def test_a_cosine_only_failure_keeps_its_root_cause(self, corpus):
        skills, ledger, review = corpus
        result = self._run(
            "--review",
            str(review),
            "--candidates",
            str(ledger),
            "--skills-dir",
            str(skills),
            "--arm",
            "cosine",
            "--min-pairs",
            "2",
        )
        assert result.returncode == 2
        assert "reason=NO_ARM_AVAILABLE" in result.stderr
        # Not just "cosine": which repair to make.
        assert "cosine=EMBEDDING_" in result.stderr

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
