#!/usr/bin/env python3
"""Retrieval-recall measurement (ADR-0097 Decision 6) — read-only, offline.

Decides one thing: **should ADR-0097 build a code-prepared retrieval evidence
bundle for the weekly insight reviewer at all?** The Codex challenge on that
ADR found that "we will act when a miss is observed" had no observer, so the
question is answered with a measurement instead of a promise.

The question in one line: *given a staged candidate the reviewer rejected as
already covered by a named store skill, does a mechanical retrieval put that
skill in the top k?* High recall means a bundle would have shown the reviewer
the skill it named anyway, so the bundle is cheap insurance; low recall means
the reviewer is finding coverage that retrieval cannot find, and a bundle
built on this retrieval would mislead rather than help.

**Ground truth** comes from the reviewer's own prose. Each
``reports/analysis/weekly-<end>-insight-review.md`` carries one
``## <n>. <candidate> — RECOMMEND: adopt|reject`` section per candidate
(``config/prompts/insight-recommendation.md``); a ``reject`` section that
names an existing store skill in its body becomes one labelled pair. Candidate
query text comes from the staged ledger ``logs/insight-staged.jsonl``
(``{ts, name, description, filename}`` per ADR-0074 Decision 7), matched by
name to the row nearest before the review's date.

**This script was written without running it.** The two corpora it reads —
``$MOLTBOOK_HOME/logs/**`` and the weekly review reports, which quote
external content — are outside what the authoring agent may read
(prompt-injection boundary, CLAUDE.md). It is verified against synthetic
fixtures in ``tests/test_retrieval_recall_measure.py``; the real reading is
the author's to take. Read the labelled-pair count first when they do.

**Arms** (at least three, so the reading can distinguish them):

- ``lexical`` — character-trigram Jaccard between the candidate text and the
  whole skill file. Stdlib only, no model. An external survey as of
  2026-08-22 found a lexical filter catching ~42x more near-duplicate pairs
  than cosine > 0.92 on a comparable corpus, which is why the cheap arm is
  measured rather than assumed inferior. Its bias is length: Jaccard's union
  is dominated by the longer side, so a short skill file scores higher for
  the same overlap. ``corpus_doc_chars`` is printed so a reader can see
  whether the store is uniform enough for that to be harmless.
- ``cosine`` — nomic embeddings through the existing ``core/embeddings.py``
  seam. The import is deferred into the arm, so ``--arm lexical`` runs with
  no model, no numpy and no ``contemplative_agent`` on the path.
- ``union`` — reciprocal-rank fusion of the two rankings (``1/(rrf_k+rank)``,
  ``rrf_k`` default 60). Fusion rather than a set union of the two top-k
  lists: a set union at k has a budget of up to 2k documents, so its recall@k
  is not comparable with the single arms' and would read as a free
  improvement. **Read the default against the corpus size**: 60 is the
  TREC-scale constant, chosen for corpora of millions, and against a ~57-skill
  store ``1/(60+r)`` is near-linear over the whole rank range (best:worst
  ~0.52), so the fusion behaves like a rank-sum with little top-rank emphasis
  — the opposite of what a recall@1 reading wants. Sweep ``--rrf-k`` (try 5
  and 10) beside the default before reading the union arm as the better one;
  ``corpus_skills`` is printed so the ratio is visible.

Every rate is printed with the number of labelled pairs behind it, and the
reading states whether it is a decision input: below ``--min-pairs`` (default
30) it is not. 30 is the smallest round pair count at which a measured 0.9
excludes 0.7 — 95% Wilson at 30/0.9 is [0.74, 0.97], at 20/0.9 it is
[0.70, 0.97] — and 0.9 is the bar ADR-0097's Review-when reads recall@5
against.

Read-only and deterministic: nothing is written, no gate is fed, no clock is
read (every date comes from a filename or a ledger row). Faults abstain with
a reason code on stderr and a nonzero exit; "no labelled pairs" is an abstain,
never a printed recall of 0.0 (ADR-0075).

Usage::

    python3 scripts/retrieval_recall_measure.py \\
        --review-dir "$MOLTBOOK_HOME/reports/analysis" \\
        --candidates "$MOLTBOOK_HOME/logs/insight-staged.jsonl" \\
        --skills-dir "$MOLTBOOK_HOME/skills" \\
        --arm lexical

    # cosine / union additionally need Ollama and the installed package:
    uv run python scripts/retrieval_recall_measure.py ... \\
        --arm lexical --arm cosine --arm union
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from _scan import ScanError

DEFAULT_K = (1, 3, 5, 10)
DEFAULT_RRF_K = 60
DEFAULT_MIN_PAIRS = 30
ARMS = ("lexical", "cosine", "union")

# Skill bodies run a few thousand characters; the embedding model has its own
# window and a silent truncation there would be an unrecorded change of input
# (the num_ctx lesson). Truncate explicitly and count it.
EMBED_MAX_CHARS = 4000

# A hyphenated token in reviewer prose is only claimed to be a *missing* skill
# name when it has at least this many segments or was written in backticks —
# otherwise "well-known" and "one-off" would read as reviewer hallucinations
# and corrupt the very count that exists to detect them.
ABSENT_NAME_MIN_SEGMENTS = 3

_REVIEW_GLOB = "weekly-*-insight-review.md"
_REVIEW_DATE_RE = re.compile(r"weekly-(\d{4}-\d{2}-\d{2})-insight-review")
_HEADING_RE = re.compile(r"^##[ \t]+(?P<head>.+?)[ \t]*$", re.MULTILINE)
_VERDICT_RE = re.compile(r"RECOMMEND:[ \t]*(adopt|reject)\b", re.IGNORECASE)
_KEBAB_RE = re.compile(r"(?<![\w-])[a-z0-9]+(?:-[a-z0-9]+)+(?![\w-])")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_FM_NAME_RE = re.compile(r"^name:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_Z95 = 1.959964


def wilson_ci(successes: int, trials: int) -> list[float] | None:
    """95% Wilson score interval, rounded to 4 places; None when trials == 0.

    Duplicated verbatim in ``coselection_families.py``: both are standalone
    stdlib instruments run with a bare ``python3``, and a shared
    ``scripts/_stats.py`` would be a third import edge for ten lines of
    textbook arithmetic.
    """
    if trials <= 0 or successes < 0 or successes > trials:
        # An impossible count is a caller bug, and ``math.sqrt`` of the
        # negative variance it implies would surface as a domain error rather
        # than as the abstain this instrument owes its reader.
        return None
    p = successes / trials
    denom = 1.0 + _Z95 * _Z95 / trials
    centre = (p + _Z95 * _Z95 / (2 * trials)) / denom
    half = (_Z95 / denom) * math.sqrt(p * (1 - p) / trials + _Z95 * _Z95 / (4 * trials * trials))
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


@dataclass(frozen=True)
class StoreSkill:
    """One adopted skill as a retrieval document."""

    name: str
    filename: str
    text: str


@dataclass(frozen=True)
class ReviewSection:
    """One ``## n. name — RECOMMEND: verdict`` section and its prose body."""

    review: str
    candidate: str | None
    verdict: str
    body: str


@dataclass(frozen=True)
class LabelledPair:
    """A rejected candidate plus the store skills the reviewer named."""

    review: str
    candidate: str
    query: str
    query_kind: str
    labels: tuple[str, ...]


def _normalize(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def trigrams(text: str) -> frozenset[str]:
    """Character trigrams of the normalized text (empty for < 3 chars)."""
    normalized = _normalize(text)
    if len(normalized) < 3:
        return frozenset()
    return frozenset(normalized[i : i + 3] for i in range(len(normalized) - 2))


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity over plain sequences; mismatched shapes read as 0.0.

    Same convention as ``core/embeddings.cosine`` — two vectors in different
    spaces are correctly dissimilar rather than an exception — but without
    numpy, so the lexical arm never pulls the dependency in.
    """
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(x * y for x, y in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(x * x for x in left))
    norm_right = math.sqrt(sum(y * y for y in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def _frontmatter(text: str) -> str:
    """The leading ``---`` block, or "" when the document has none."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def load_store(skills_dir: Path) -> tuple[tuple[StoreSkill, ...], int]:
    """Read ``skills_dir/*.md`` into retrieval documents; returns (docs, unreadable).

    Same traversal contract as ``core.skill_selection.load_skill_catalog``
    (sorted glob, dotfiles skipped, unreadable files skipped) and the same
    identity rule: the frontmatter ``name:`` wins over the filename, because
    the filename carries an adoption-date suffix while the selector, the
    ledger and the reviewer all speak the frontmatter name.

    The ``name:`` scan is restricted to the leading frontmatter block, as
    ``core.text_utils.skill_theme`` does. Scanning the whole file resolved a
    legacy body's prose ``name:`` line as the skill's identity while the
    selector read the filename stem — and a document that answers to a name
    the selector never emits cannot be joined to the reviewer's prose, so the
    labelled pair would vanish with no fault recorded.
    """
    if not skills_dir.is_dir():
        raise ScanError("SKILLS_DIR_MISSING", str(skills_dir))
    docs: list[StoreSkill] = []
    unreadable = 0
    for path in sorted(skills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        match = _FM_NAME_RE.search(_frontmatter(text))
        name = (match.group(1).strip() if match else "") or path.stem
        docs.append(StoreSkill(name=name, filename=path.name, text=text))
    if not docs:
        raise ScanError("SKILLS_EMPTY", str(skills_dir))
    return tuple(docs), unreadable


def load_candidates(path: Path) -> tuple[dict[str, list[tuple[str, str]]], int]:
    """Staged-ledger rows as ``name.lower() -> [(ts, description)]`` + fault count."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScanError("CANDIDATES_MISSING", str(path)) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ScanError("CANDIDATES_UNREADABLE", f"{path}: {exc}") from exc
    rows: dict[str, list[tuple[str, str]]] = {}
    malformed = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(record, dict):
            malformed += 1
            continue
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            malformed += 1
            continue
        description = record.get("description")
        timestamp = record.get("ts")
        rows.setdefault(name.strip().lower(), []).append(
            (
                timestamp if isinstance(timestamp, str) else "",
                description if isinstance(description, str) else "",
            )
        )
    return rows, malformed


def parse_review(review_name: str, text: str) -> tuple[tuple[ReviewSection, ...], int]:
    """Split a review into sections; returns (sections, headings without a candidate name).

    A ``##`` heading without ``RECOMMEND:`` ends the previous section's body
    but contributes none of its own — a reviewer that appends a summary
    section must not have it read as the last candidate's reasoning.
    """
    headings = list(_HEADING_RE.finditer(text))
    sections: list[ReviewSection] = []
    unnamed = 0
    for index, match in enumerate(headings):
        head = match.group("head")
        verdict_match = _VERDICT_RE.search(head)
        if verdict_match is None:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        title = head[: verdict_match.start()]
        name_match = _KEBAB_RE.search(title.lower())
        candidate = name_match.group(0) if name_match else None
        if candidate is None:
            unnamed += 1
        sections.append(
            ReviewSection(
                review=review_name,
                candidate=candidate,
                verdict=verdict_match.group(1).lower(),
                body=text[match.end() : end],
            )
        )
    return tuple(sections), unnamed


def _review_date(review_name: str) -> date | None:
    match = _REVIEW_DATE_RE.search(review_name)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _candidate_description(
    ledger: dict[str, list[tuple[str, str]]], candidate: str, review_day: date | None
) -> tuple[str | None, bool]:
    """Description for a candidate + whether the chosen row post-dates the review.

    Themes recur, so one name can carry several ledger rows. The row nearest
    *before* the review is the one that batch reviewed; a later row describes
    a re-staging the reviewer never saw.

    A blank description reads as *no* description, not as an empty one: the
    ledger writer is ``skill_theme``, whose last fallback is ``""``, and an
    empty string would otherwise build a query that is the candidate name plus
    a newline while being stamped ``name+description`` — a name-only query
    smuggled past ``--name-only-queries exclude`` under the wrong label.
    """
    rows = ledger.get(candidate.lower())
    if not rows:
        return None, False
    ordered = sorted(rows, key=lambda row: row[0])
    chosen: tuple[str, str] | None = None
    if review_day is not None:
        eligible = [row for row in ordered if row[0][:10] <= review_day.isoformat()]
        if eligible:
            chosen = eligible[-1]
    late = chosen is None and review_day is not None
    if chosen is None:
        chosen = ordered[-1]
    description = chosen[1].strip()
    return (description or None), late


@dataclass(frozen=True)
class LabelStats:
    """Where every rejection went, in counts that add up.

    Two identities hold and are asserted by the tests, because a ground-truth
    tally with a silent residual is the same failure as a rate without its
    denominator — a reader who sums the printed fields must not come up short:

        rejections      == naming_a_store_skill + naming_nothing
        naming_a_store_skill == kept_pairs + name_only_excluded
    """

    rejections: int
    naming_a_store_skill: int
    kept_pairs: int
    naming_nothing: int
    multi_label: int
    name_only_excluded: int
    name_only_included: int
    ledger_row_after_review: int
    unresolved_names: tuple[str, ...]
    candidates_also_in_store: int


def build_pairs(
    sections: Sequence[ReviewSection],
    *,
    store_names: dict[str, str],
    ledger: dict[str, list[tuple[str, str]]],
    review_days: dict[str, date | None],
    name_only_queries: str,
) -> tuple[tuple[LabelledPair, ...], LabelStats]:
    """Turn reject sections into labelled (candidate -> covering skill) pairs.

    "Batch" means the review a section came from, not the whole run. Pooling
    every week's candidates would let a reviewer's invented name in week 7
    match a real candidate from week 1 and be filed as a sibling reference —
    silently removing it from ``unresolved_reviewer_names``, the one field
    that exists to surface invented names.
    """
    batch_candidates: dict[str, set[str]] = {}
    for section in sections:
        if section.candidate:
            batch_candidates.setdefault(section.review, set()).add(section.candidate)
    pairs: list[LabelledPair] = []
    rejections = 0
    naming_a_store_skill = 0
    naming_nothing = 0
    multi_label = 0
    name_only_excluded = 0
    name_only_included = 0
    ledger_row_after_review = 0
    candidates_also_in_store = 0
    unresolved: dict[str, None] = {}

    for section in sections:
        if section.verdict != "reject" or section.candidate is None:
            continue
        rejections += 1
        siblings = batch_candidates.get(section.review, set())
        body = section.body.lower()
        backticked = {
            token for span in _BACKTICK_RE.findall(body) for token in _KEBAB_RE.findall(span)
        }
        labels: list[str] = []
        for token in _KEBAB_RE.findall(body):
            if token == section.candidate:
                continue
            canonical = store_names.get(token)
            if canonical is not None:
                if canonical not in labels:
                    labels.append(canonical)
                continue
            if token in siblings:
                # A sibling in this review's own batch, not a coverage claim
                # (ADR-0097's `reject: sibling-of` verdict).
                continue
            if token.count("-") + 1 >= ABSENT_NAME_MIN_SEGMENTS or token in backticked:
                unresolved[token] = None
        if not labels:
            naming_nothing += 1
            continue
        # Counted here, before the ledger lookup can drop the pair: a
        # rejection that named a covering skill DID name one, whether or not
        # this measurement can build a query for it.
        naming_a_store_skill += 1
        description, late_row = _candidate_description(
            ledger, section.candidate, review_days.get(section.review)
        )
        if late_row:
            ledger_row_after_review += 1
        if description is None:
            if name_only_queries == "exclude":
                name_only_excluded += 1
                continue
            name_only_included += 1
            query = section.candidate
            query_kind = "name-only"
        else:
            query = f"{section.candidate}\n{description}"
            query_kind = "name+description"
        if section.candidate in store_names:
            candidates_also_in_store += 1
        # Counted on the KEPT pair, not on the rejection: this field qualifies
        # the recall figures ("how many of the scored pairs does the any-of
        # hit rule soften"), so a pair the ledger lookup dropped must not
        # appear in it.
        if len(labels) > 1:
            multi_label += 1
        pairs.append(
            LabelledPair(
                review=section.review,
                candidate=section.candidate,
                query=query,
                query_kind=query_kind,
                labels=tuple(labels),
            )
        )

    stats = LabelStats(
        rejections=rejections,
        naming_a_store_skill=naming_a_store_skill,
        kept_pairs=len(pairs),
        naming_nothing=naming_nothing,
        multi_label=multi_label,
        name_only_excluded=name_only_excluded,
        name_only_included=name_only_included,
        ledger_row_after_review=ledger_row_after_review,
        unresolved_names=tuple(sorted(unresolved)),
        candidates_also_in_store=candidates_also_in_store,
    )
    return tuple(pairs), stats


def _rank(scores: dict[str, float]) -> tuple[str, ...]:
    """Names ordered by score desc, ties broken by name so runs are identical."""
    return tuple(name for name, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])))


def lexical_rankings(
    pairs: Sequence[LabelledPair], docs: Sequence[StoreSkill]
) -> list[tuple[str, ...]]:
    doc_grams = [(doc.name, trigrams(doc.text)) for doc in docs]
    rankings: list[tuple[str, ...]] = []
    for pair in pairs:
        query_grams = trigrams(pair.query)
        rankings.append(_rank({name: jaccard(query_grams, grams) for name, grams in doc_grams}))
    return rankings


def cosine_rankings(
    pairs: Sequence[LabelledPair], docs: Sequence[StoreSkill]
) -> tuple[list[tuple[str, ...]] | None, str | None, tuple[int, int]]:
    """Embedding rankings, or (None, reason, truncation) when the seam is unusable.

    The import lives here rather than at module scope so the lexical arm runs
    with a bare ``python3`` and no installed package (the weekly scripts are
    invoked that way).

    Three ways the seam can fail and each gets its own code, because a
    *degenerate* ranking is the dangerous one: ``cosine`` answers 0.0 for a
    dimension mismatch or a zero-norm vector (the same fail-soft convention as
    ``core/embeddings.cosine``), and ``_rank``'s name tie-break then turns an
    all-zero score dict into a confident-looking alphabetical ranking that
    ``recall_at_k`` will happily score. That inflates recall in the permissive
    direction — straight at ADR-0097's "build the bundle when recall@5 >= 0.9"
    Review-when — so a query whose scores have no spread abstains the whole
    arm rather than contributing a ranking nobody can tell from a real one.
    """
    try:
        from contemplative_agent.core.embeddings import embed_texts
    except ImportError as exc:
        return None, f"EMBEDDING_IMPORT_FAILED: {exc}", (0, 0)

    doc_texts = [doc.text[:EMBED_MAX_CHARS] for doc in docs]
    query_texts = [pair.query[:EMBED_MAX_CHARS] for pair in pairs]
    truncation = (
        sum(1 for doc in docs if len(doc.text) > EMBED_MAX_CHARS),
        sum(1 for pair in pairs if len(pair.query) > EMBED_MAX_CHARS),
    )
    # Row count is compared for equality, not just for shortfall: a response
    # with MORE rows than inputs is as unusable as one with fewer, and would
    # otherwise reach the strict zip in recall_at_k as a traceback instead of
    # a reason code (ADR-0077 fault column).
    doc_matrix = embed_texts(doc_texts)
    if doc_matrix is None or len(doc_matrix) != len(doc_texts):
        return None, "EMBEDDING_UNAVAILABLE", truncation
    query_matrix = embed_texts(query_texts)
    if query_matrix is None or len(query_matrix) != len(pairs):
        return None, "EMBEDDING_UNAVAILABLE", truncation

    doc_vectors = [(docs[i].name, [float(v) for v in row]) for i, row in enumerate(doc_matrix)]
    query_vectors = [[float(v) for v in row] for row in query_matrix]
    dimension = len(doc_vectors[0][1])
    if dimension == 0:
        return None, "EMBEDDING_DEGENERATE", truncation
    for vector in [vec for _, vec in doc_vectors] + query_vectors:
        if len(vector) != dimension or not any(vector):
            return None, "EMBEDDING_DEGENERATE", truncation

    rankings: list[tuple[str, ...]] = []
    for query_vector in query_vectors:
        scores = {name: cosine(query_vector, vec) for name, vec in doc_vectors}
        if len(docs) > 1 and max(scores.values()) == min(scores.values()):
            return None, "EMBEDDING_DEGENERATE", truncation
        rankings.append(_rank(scores))
    return rankings, None, truncation


def rrf_rankings(
    left: Sequence[tuple[str, ...]], right: Sequence[tuple[str, ...]], rrf_k: int
) -> list[tuple[str, ...]]:
    """Reciprocal-rank fusion of two equal-length ranking lists."""
    fused: list[tuple[str, ...]] = []
    for left_ranking, right_ranking in zip(left, right, strict=True):
        scores: dict[str, float] = {}
        for ranking in (left_ranking, right_ranking):
            for position, name in enumerate(ranking, start=1):
                scores[name] = scores.get(name, 0.0) + 1.0 / (rrf_k + position)
        fused.append(_rank(scores))
    return fused


def recall_at_k(
    pairs: Sequence[LabelledPair], rankings: Sequence[tuple[str, ...]], ks: Sequence[int]
) -> dict[str, Any]:
    """Share of labelled candidates with at least one named skill in the top k.

    "At least one" rather than "all": a rejection that names two covering
    skills is one coverage judgment the bundle would have to surface, not two
    independent retrieval targets. ``multi_label_pairs`` in the reading says
    how many pairs the distinction applies to.
    """
    out: dict[str, Any] = {}
    for k in ks:
        hits = 0
        for pair, ranking in zip(pairs, rankings, strict=True):
            if any(label in ranking[:k] for label in pair.labels):
                hits += 1
        out[str(k)] = {
            "hits": hits,
            "pairs": len(pairs),
            "rate": round(hits / len(pairs), 4) if pairs else None,
            "ci95": wilson_ci(hits, len(pairs)),
        }
    return out


def build_reading(
    *,
    pairs: Sequence[LabelledPair],
    docs: Sequence[StoreSkill],
    label_stats: LabelStats,
    reviews: Sequence[str],
    arms: Sequence[str],
    ks: Sequence[int],
    rrf_k: int,
    min_pairs: int,
    name_only_queries: str,
    partial_reasons: Sequence[str],
) -> dict[str, Any]:
    """Assemble the reading from already-loaded inputs (pure; unit-testable)."""
    if not pairs:
        raise ScanError(
            "NO_LABELLED_PAIRS",
            f"{label_stats.rejections} rejections read, "
            f"{label_stats.naming_nothing} named no store skill, "
            f"{label_stats.name_only_excluded} had no ledger text",
        )

    reasons = list(dict.fromkeys(partial_reasons))
    arm_readings: dict[str, Any] = {}
    lexical: list[tuple[str, ...]] | None = None
    cosine_ranks: list[tuple[str, ...]] | None = None
    # The arm reports the code it actually failed under: an uninstalled
    # package and a dead Ollama are different repairs, and collapsing both
    # into EMBEDDING_UNAVAILABLE sends the reader to the wrong one.
    cosine_code = "EMBEDDING_UNAVAILABLE"
    embed_truncated = (0, 0)

    if "lexical" in arms or "union" in arms:
        lexical = lexical_rankings(pairs, docs)
    if "cosine" in arms or "union" in arms:
        cosine_ranks, cosine_reason, embed_truncated = cosine_rankings(pairs, docs)
        if cosine_reason is not None:
            cosine_code = cosine_reason.split(":")[0]
            if cosine_code not in reasons:
                reasons.append(cosine_code)

    if "lexical" in arms and lexical is not None:
        arm_readings["lexical"] = {
            "available": True,
            "metric": "character-trigram Jaccard over the whole skill file",
            "recall": recall_at_k(pairs, lexical, ks),
        }
    if "cosine" in arms:
        if cosine_ranks is None:
            arm_readings["cosine"] = {"available": False, "reason": cosine_code}
        else:
            arm_readings["cosine"] = {
                "available": True,
                "metric": "nomic embedding cosine (core/embeddings.py)",
                "docs_truncated_for_embedding": embed_truncated[0],
                "queries_truncated_for_embedding": embed_truncated[1],
                "embed_max_chars": EMBED_MAX_CHARS,
                "recall": recall_at_k(pairs, cosine_ranks, ks),
            }
    if "union" in arms:
        if lexical is None or cosine_ranks is None:
            arm_readings["union"] = {"available": False, "reason": "UNION_ARM_INCOMPLETE"}
        else:
            arm_readings["union"] = {
                "available": True,
                "metric": f"reciprocal-rank fusion of lexical and cosine (rrf_k={rrf_k})",
                "recall": recall_at_k(pairs, rrf_rankings(lexical, cosine_ranks, rrf_k), ks),
            }

    if not any(arm.get("available") for arm in arm_readings.values()):
        raise ScanError("NO_ARM_AVAILABLE", ", ".join(sorted(arms)))

    doc_chars = sorted(len(doc.text) for doc in docs)
    decision_input = len(pairs) >= min_pairs
    if not decision_input:
        reasons.append("BELOW_DECISION_FLOOR")
    if label_stats.unresolved_names:
        reasons.append("UNRESOLVED_REVIEWER_NAMES")

    return {
        # Deliberately the first key: every rate below is over this many
        # pairs, and a recall figure over a handful is not a decision input.
        "labelled_pairs": len(pairs),
        "decision_input": decision_input,
        "min_pairs_for_decision": min_pairs,
        "reviews": list(reviews),
        "corpus_skills": len(docs),
        "corpus_doc_chars": {
            "min": doc_chars[0],
            "median": int(statistics.median(doc_chars)),
            "max": doc_chars[-1],
        },
        "ground_truth": {
            # rejections == naming_a_store_skill + naming_no_store_skill, and
            # naming_a_store_skill == labelled_pairs_kept + the name-only
            # exclusions below. Both identities close by construction so a
            # reader summing these fields never comes up short.
            "rejections": label_stats.rejections,
            "rejections_naming_a_store_skill": label_stats.naming_a_store_skill,
            "rejections_naming_no_store_skill": label_stats.naming_nothing,
            "labelled_pairs_kept": label_stats.kept_pairs,
            "multi_label_pairs": label_stats.multi_label,
            "name_only_queries": {
                "policy": name_only_queries,
                "excluded": label_stats.name_only_excluded,
                "included": label_stats.name_only_included,
            },
            "ledger_row_after_review": label_stats.ledger_row_after_review,
            "candidates_also_present_in_store": label_stats.candidates_also_in_store,
            # Diagnostic only, and a token heuristic — eyeball it before
            # quoting it. This is NOT ADR-0097 slice 3's existence check,
            # which belongs to build_decision_packet.py over live review text.
            "unresolved_reviewer_names": list(label_stats.unresolved_names),
            "unresolved_name_rule": (
                f">= {ABSENT_NAME_MIN_SEGMENTS} hyphen-separated segments or written in backticks, "
                "and matching neither the store nor a candidate in the same batch"
            ),
        },
        "k": list(ks),
        "arms": arm_readings,
        "caveats": [
            "The store is read as it is now, not as it was at review time: a "
            "skill adopted after a review sits in the corpus and one removed "
            "since is missing, so a label naming a removed skill contributes "
            "no pair at all.",
            "Recall counts a hit when ANY reviewer-named skill is in the top "
            "k; multi_label_pairs says how many pairs that softens.",
        ],
        "reasons": list(dict.fromkeys(reasons)),
    }


def _parse_k(spec: str) -> tuple[int, ...]:
    values: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = int(chunk)
        except ValueError as exc:
            raise ScanError("BAD_K", f"{chunk!r}: {exc}") from exc
        if value < 1:
            raise ScanError("BAD_K", f"{value} is below 1")
        if value not in values:
            values.append(value)
    if not values:
        raise ScanError("BAD_K", "no cutoffs given")
    return tuple(sorted(values))


def _collect_reviews(paths: Sequence[Path], review_dir: Path | None) -> list[Path]:
    collected = list(paths)
    if review_dir is not None:
        if not review_dir.is_dir():
            raise ScanError("REVIEWS_MISSING", str(review_dir))
        collected.extend(sorted(review_dir.glob(_REVIEW_GLOB)))
    unique: list[Path] = []
    for path in collected:
        if path not in unique:
            unique.append(path)
    if not unique:
        raise ScanError("REVIEWS_MISSING", "no --review paths and no --review-dir matches")
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline retrieval-recall measurement against reviewer-named store skills."
    )
    parser.add_argument(
        "--review", type=Path, action="append", default=[], help="one weekly review md (repeatable)"
    )
    parser.add_argument(
        "--review-dir", type=Path, default=None, help=f"dir to glob {_REVIEW_GLOB} from"
    )
    parser.add_argument(
        "--candidates", type=Path, required=True, help="logs/insight-staged.jsonl (ADR-0074)"
    )
    parser.add_argument("--skills-dir", type=Path, required=True, help="the adopted skill store")
    parser.add_argument(
        "--arm",
        action="append",
        choices=ARMS,
        default=None,
        help="retrieval arm (repeatable; default: all three)",
    )
    parser.add_argument("--k", default=",".join(str(k) for k in DEFAULT_K))
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K)
    parser.add_argument("--min-pairs", type=int, default=DEFAULT_MIN_PAIRS)
    parser.add_argument(
        "--name-only-queries",
        choices=("exclude", "include"),
        default="exclude",
        help="candidates with no ledger text: drop them, or query on the name alone",
    )
    args = parser.parse_args(argv)

    try:
        arms = tuple(dict.fromkeys(args.arm)) if args.arm else ARMS
        ks = _parse_k(args.k)
        if args.rrf_k < 1:
            raise ScanError("BAD_RRF_K", str(args.rrf_k))
        if args.min_pairs < 1:
            raise ScanError("BAD_MIN_PAIRS", str(args.min_pairs))
        review_paths = _collect_reviews(args.review, args.review_dir)
        docs, unreadable_skills = load_store(args.skills_dir)
        ledger, malformed_ledger = load_candidates(args.candidates)

        sections: list[ReviewSection] = []
        review_days: dict[str, date | None] = {}
        review_names: list[str] = []
        unreadable_reviews = 0
        unnamed_sections = 0
        undated_reviews = 0
        duplicate_review_names = 0
        for path in review_paths:
            if path.name in review_days:
                # Sections are keyed by basename, so a second file with the
                # same name would take the first one's review date and its
                # candidates would be matched against the wrong ledger rows.
                duplicate_review_names += 1
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                unreadable_reviews += 1
                continue
            parsed, unnamed = parse_review(path.name, text)
            sections.extend(parsed)
            unnamed_sections += unnamed
            review_day = _review_date(path.name)
            if review_day is None:
                # Without a date, _candidate_description falls back to the
                # LATEST ledger row for a name — possibly a re-staging written
                # after this review, which the reviewer never saw. The
                # fallback is deliberate (a query is better than no pair) but
                # it must not be silent, and the late-row counter cannot see
                # it because "later than an unknown date" is undecidable.
                undated_reviews += 1
            review_days[path.name] = review_day
            review_names.append(path.name)
        if not review_names:
            raise ScanError("REVIEWS_UNREADABLE", f"{unreadable_reviews} files unreadable")

        pairs, label_stats = build_pairs(
            sections,
            store_names={doc.name.lower(): doc.name for doc in docs},
            ledger=ledger,
            review_days=review_days,
            name_only_queries=args.name_only_queries,
        )

        partial: list[str] = []
        if unreadable_reviews:
            partial.append("REVIEW_PARTIAL_READ")
        if undated_reviews:
            partial.append("REVIEW_DATE_UNPARSEABLE")
        if duplicate_review_names:
            partial.append("DUPLICATE_REVIEW_NAME")
        if unnamed_sections:
            partial.append("REVIEW_SECTION_WITHOUT_CANDIDATE_NAME")
        if malformed_ledger:
            partial.append("LEDGER_PARTIAL_PARSE")
        if unreadable_skills:
            partial.append("SKILLS_PARTIAL_READ")

        reading = build_reading(
            pairs=pairs,
            docs=docs,
            label_stats=label_stats,
            reviews=review_names,
            arms=arms,
            ks=ks,
            rrf_k=args.rrf_k,
            min_pairs=args.min_pairs,
            name_only_queries=args.name_only_queries,
            partial_reasons=partial,
        )
    except ScanError as exc:
        print(f"retrieval_recall_measure: {exc}", file=sys.stderr)
        return 2

    if not reading["decision_input"]:
        print(
            f"retrieval_recall_measure: BELOW_DECISION_FLOOR: {reading['labelled_pairs']} "
            f"labelled pairs < {reading['min_pairs_for_decision']} — read as context, "
            "not as a decision input",
            file=sys.stderr,
        )
    print(json.dumps(reading, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
