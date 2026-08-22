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
  seam, using that module's own ``cosine``. The import is deferred into the
  arm, so ``--arm lexical`` runs with no model, no numpy and no
  ``contemplative_agent`` on the path.
- ``union`` — reciprocal-rank fusion of the two rankings (``1/(rrf_k+rank)``,
  ``rrf_k`` default 60). Fusion rather than a set union of the two top-k
  lists: a set union at k has a budget of up to 2k documents, so its recall@k
  is not comparable with the single arms' and would read as a free
  improvement. **Read the default against the corpus size**: 60 is the
  TREC-scale constant, chosen for corpora of millions, and against a
  ~57-skill store ``1/(60+r)`` is near-linear over the whole rank range
  (best:worst ~0.52), so the fusion behaves like a rank-sum with little
  top-rank emphasis — the opposite of what a recall@1 reading wants. Sweep
  ``--rrf-k`` (try 5 and 10) beside the default before reading the union arm
  as the better one; ``corpus_skills`` is printed so the ratio is visible.

**One corpus, all arms.** Documents are truncated once at load
(``MAX_TEXT_CHARS``), before any arm sees them, and the truncation is counted
in a top-level ``corpus_truncation`` block. Truncating only inside the
embedding call would have left cosine and union ranking strictly shorter
documents than lexical ranked — and comparing the arms is the entire purpose
of the reading. ``longest_original`` is kept so the Jaccard length-bias
evidence survives the truncation.

Every rate is printed with the number of labelled pairs behind it, and the
reading states whether it is a decision input: below ``--min-pairs`` (default
30) it is not. 30 is the smallest round pair count at which a measured 0.9
excludes 0.7 — 95% Wilson at 30/0.9 is [0.74, 0.97], at 20/0.9 it is
[0.70, 0.97] — and 0.9 is the bar ADR-0097's Review-when reads recall@5
against.

Read-only and deterministic: nothing is written, no gate is fed, no clock is
read (every date comes from a filename or a ledger row). Faults abstain with
a reason code on stderr and a nonzero exit; "no labelled pairs" is an abstain,
never a printed recall of 0.0 (ADR-0075). An unreadable *skill file* abstains
too, unless ``--allow-partial-store``: a shrinking corpus mechanically raises
recall@k for every surviving pair, which is the permissive direction against
this ADR's own decision bar, so a silently smaller store must not be a quiet
reading.

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
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from _audit import parse_records
from _scan import ScanError
from _stats import wilson_ci

DEFAULT_K = (1, 3, 5, 10)
DEFAULT_RRF_K = 60
DEFAULT_MIN_PAIRS = 30
# A review's filename carries the pipeline's END_DATE (yesterday), while the
# batch it reviews is staged on the pipeline morning — so the review is named
# one day before its own ledger rows. See `_candidate_description`.
DEFAULT_STAGING_LAG_DAYS = 1
ARMS = ("lexical", "cosine", "union")

# One bound for every arm, applied once at load. Skill bodies run a few
# thousand characters and the embedding model has its own window; a silent
# truncation there would be an unrecorded change of input (the num_ctx
# lesson), and a truncation applied to only one arm would be an unrecorded
# change of *corpus*.
MAX_TEXT_CHARS = 4000

# A hyphenated token in reviewer prose is only claimed to be a *missing* skill
# name when it has at least this many segments or was written in backticks —
# otherwise "well-known" and "one-off" would read as reviewer hallucinations
# and corrupt the very count that exists to detect them.
ABSENT_NAME_MIN_SEGMENTS = 3

# Cap borrowed from `core/skill_selection.py::_NAME_MAX_CHARS`, applied by the
# same scrub at the same seam (see `_skill_theme`).
NAME_MAX_CHARS = 80

_REVIEW_GLOB = "weekly-*-insight-review.md"
_REVIEW_DATE_RE = re.compile(r"weekly-(\d{4}-\d{2}-\d{2})-insight-review")
_HEADING_RE = re.compile(r"^##[ \t]+(?P<head>.+?)[ \t]*$", re.MULTILINE)
_VERDICT_RE = re.compile(r"RECOMMEND:[ \t]*(adopt|reject)\b", re.IGNORECASE)
_KEBAB_RE = re.compile(r"(?<![\w-])[a-z0-9]+(?:-[a-z0-9]+)+(?![\w-])")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Mirrors of `core/text_utils.py` and `core/_io.py`; see `_skill_theme`.
_FM_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_FM_DESCRIPTION_RE = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.MULTILINE)
_PRINTABLE_RE = re.compile(r"[^\x20-\x7E]")
# Store filenames carry an adoption-date suffix, and the reviewer can see
# them (`weekly-pipeline.sh` grants --add-dir over the skill store), so a
# citation by filename must resolve to the skill rather than be filed as a
# hallucination-shaped unresolved name.
_TRAILING_ISO_DATE_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class StoreSkill:
    """One adopted skill as a retrieval document."""

    name: str
    filename: str
    text: str
    original_chars: int


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


# ---------------------------------------------------------------- primitives


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


def _rank(scores: dict[str, float]) -> tuple[str, ...]:
    """Names ordered by score desc, ties broken by name so runs are identical."""
    return tuple(name for name, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])))


def _no_spread(scores: dict[str, float]) -> bool:
    """True when every document scored the same, so the order is the tie-break.

    ``_rank``'s name tie-break exists for determinism, and it turns an
    all-equal score dict into a confident-looking *alphabetical* ranking that
    ``recall_at_k`` would score as real. One document cannot be degenerate.
    """
    return len(scores) > 1 and max(scores.values()) == min(scores.values())


# -------------------------------------------------------------------- loaders


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Mirror of ``core.text_utils.split_frontmatter`` — pinned by a parity test.

    Line-exact, like the original: the first line must *strip* to ``---`` and
    the block ends at the next line that strips to ``---``. A ``startswith``
    plus ``find("\\n---")`` reading accepted ``---foo`` as an opener and a
    mid-line ``\\n---bar`` as a closer, which is precisely how the two spellings
    of one join key drift apart.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[: index + 1]), "\n".join(lines[index + 1 :]).lstrip("\n")
    return "", text


def _extract_title(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _strip_to_printable(value: str, max_len: int) -> str:
    """Mirror of ``core._io.strip_to_printable`` (no ``keep_newline`` caller)."""
    return _PRINTABLE_RE.sub("", value[:max_len])


def _skill_theme(text: str, fallback_name: str) -> tuple[str, str]:
    """``(name, description)`` for a skill document — the store's join key.

    A local mirror of ``core.text_utils.skill_theme`` rather than an import:
    the documented lexical-arm workflow is a bare ``python3`` invocation, and
    a module-level package import would break it entirely. The drift risk that
    buys is real and load-bearing — the *other* side of this join, the staged
    ledger, is written with the real ``skill_theme`` — so
    ``tests/test_retrieval_recall_measure.py`` runs both over a corpus of edge
    cases and asserts identical output. Two spellings that disagree at the
    edges is exactly how a labelled pair vanishes with no fault recorded.

    The ``_strip_to_printable`` scrub is the one ``core/skill_selection.py``
    applies at the same seam, so a name carrying an ANSI escape or a homoglyph
    joins the way the selector would join it.
    """
    frontmatter, body = _split_frontmatter(text)
    name = None
    description = None
    if frontmatter:
        match = _FM_NAME_RE.search(frontmatter)
        name = match.group(1).strip() if match else None
        match = _FM_DESCRIPTION_RE.search(frontmatter)
        description = match.group(1).strip() if match else None
    title = _extract_title(body or text)
    return (name or fallback_name, description or title or "")


def load_store(
    skills_dir: Path, *, max_chars: int = MAX_TEXT_CHARS
) -> tuple[tuple[StoreSkill, ...], int, int]:
    """Read ``skills_dir/*.md`` into documents; returns (docs, unreadable, duplicate_names).

    Same traversal contract as ``core.skill_selection.load_skill_catalog``
    (sorted glob, dotfiles skipped, unreadable files skipped) and the same
    identity rule: the frontmatter ``name:`` wins over the filename, because
    the filename carries an adoption-date suffix while the selector, the
    ledger and the reviewer all speak the frontmatter name. On the live store
    all 57 files carry a ``name:`` and all 57 differ from their filename stem,
    so falling back to the stem would void every labelled pair.

    The local traversal is kept rather than calling ``load_skill_catalog``
    because that function does not retain body text (this is a retrieval
    corpus) and ``read_markdown_documents`` drops frontmatter-only files,
    which would silently shrink the corpus. The one deliberate divergence is
    wider: ``UnicodeDecodeError`` is a ``ValueError``, not an ``OSError``, so
    catching only ``OSError`` (as ``load_skill_catalog`` does) lets a single
    invalid byte traceback out of a read this instrument must survive.
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
        name, _description = _skill_theme(text, fallback_name=path.stem)
        docs.append(
            StoreSkill(
                name=_strip_to_printable(name, NAME_MAX_CHARS),
                filename=path.name,
                text=text[:max_chars],
                original_chars=len(text),
            )
        )
    if not docs:
        raise ScanError("SKILLS_EMPTY", str(skills_dir))
    # Every ranking is a dict keyed by name, so two files declaring the same
    # frontmatter `name:` collapse into one entry — one document silently
    # leaves the ranking while `corpus_skills` still counts both. Latent today
    # (all 57 live skills declare distinct names), so it is counted rather
    # than made an abstain.
    duplicate_names = len(docs) - len({doc.name for doc in docs})
    return tuple(docs), unreadable, duplicate_names


@dataclass(frozen=True)
class LedgerFaults:
    unparsable_lines: int
    rows_without_a_name: int
    rows_with_an_unusable_ts: int


def load_candidates(path: Path) -> tuple[dict[str, list[tuple[str, str]]], LedgerFaults]:
    """Staged-ledger rows as ``name.lower() -> [(ts, description)]`` + faults.

    Line splitting is ``_audit.parse_records``, the shared grammar the weekly
    packet's other readers use; only the field policy is local. ``UnicodeDecodeError``
    is a ``ValueError``, not an ``OSError`` — caught explicitly so a single
    invalid byte abstains under a code instead of tracebacking.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScanError("CANDIDATES_MISSING", str(path)) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ScanError("CANDIDATES_UNREADABLE", f"{path}: {exc}") from exc
    records, unparsable = parse_records(text)
    rows: dict[str, list[tuple[str, str]]] = {}
    without_name = 0
    unusable_ts = 0
    for record in records:
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            without_name += 1
            continue
        timestamp = record.get("ts")
        if not isinstance(timestamp, str):
            # An empty ts sorts to the front and reads as "before every
            # review", so a row that lost its timestamp must be visible
            # rather than quietly become the oldest staging of its theme.
            unusable_ts += 1
            timestamp = ""
        description = record.get("description")
        rows.setdefault(name.strip().lower(), []).append(
            (timestamp, description if isinstance(description, str) else "")
        )
    return rows, LedgerFaults(unparsable, without_name, unusable_ts)


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


@dataclass(frozen=True)
class ReviewCorpus:
    """Every review's sections, plus the faults reading them produced."""

    sections: tuple[ReviewSection, ...]
    review_days: dict[str, date | None]
    names: tuple[str, ...]
    unreadable: int
    undated: int
    duplicate_names: int
    unnamed_sections: int


def load_reviews(paths: Sequence[Path]) -> ReviewCorpus:
    """Read and parse every review file, naming each fault it hits.

    Extracted from ``main`` so the two guards below are reachable from a unit
    test: both carry comments claiming they are load-bearing, and neither was
    testable while the stage existed only inside the CLI entry point.
    """
    sections: list[ReviewSection] = []
    review_days: dict[str, date | None] = {}
    names: list[str] = []
    unreadable = 0
    undated = 0
    duplicate_names = 0
    unnamed_sections = 0
    for path in paths:
        if path.name in review_days:
            # Sections are keyed by basename, so a second file with the same
            # name would take the first one's review date and its candidates
            # would be matched against the wrong ledger rows.
            duplicate_names += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        # UnicodeDecodeError is a ValueError, not an OSError — the same gap
        # guarded at the other two read sites in this module.
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        parsed, unnamed = parse_review(path.name, text)
        sections.extend(parsed)
        unnamed_sections += unnamed
        review_day = _review_date(path.name)
        if review_day is None:
            # Without a date, _candidate_description falls back to the LATEST
            # ledger row for a name — possibly a re-staging written after this
            # review, which the reviewer never saw. The fallback is deliberate
            # (a query is better than no pair) but it must not be silent, and
            # the late-row counter cannot see it because "later than an
            # unknown date" is undecidable.
            undated += 1
        review_days[path.name] = review_day
        names.append(path.name)
    if not names:
        raise ScanError("REVIEWS_UNREADABLE", f"{unreadable} files unreadable")
    return ReviewCorpus(
        sections=tuple(sections),
        review_days=review_days,
        names=tuple(names),
        unreadable=unreadable,
        undated=undated,
        duplicate_names=duplicate_names,
        unnamed_sections=unnamed_sections,
    )


def _candidate_description(
    ledger: dict[str, list[tuple[str, str]]],
    candidate: str,
    review_day: date | None,
    *,
    staging_lag_days: int = DEFAULT_STAGING_LAG_DAYS,
) -> tuple[str | None, bool]:
    """Description for a candidate + whether the chosen row post-dates the review.

    Themes recur, so one name can carry several ledger rows. The row that
    batch reviewed is the newest one at or before the review's cutoff; a row
    after it describes a re-staging the reviewer never saw.

    **The cutoff is the review's filename date plus a staging lag, not the
    filename date itself.** A review's name carries the pipeline's
    ``END_DATE``, which ``scripts/weekly-pipeline.sh`` sets to *yesterday*,
    while ``insight --stage`` writes that same batch's ledger rows on the
    pipeline morning — so a review is always named one day BEFORE the rows it
    reviewed, and a cutoff at the filename date excludes the review's own
    batch by construction. It did: on the live corpus 132 of 135
    ledger-resolvable rejections took the fallback branch and every kept pair
    came back flagged ``ledger_row_after_review``. A guard saturated at 100%
    is worse than no guard — it is the only field standing between a query
    built from the wrong week's text and a number read against ADR-0097's
    ``recall@5 >= 0.9`` Review-when, and it cannot flag the three names that
    really do carry two rows with different descriptions.

    The lag is a parameter (``--staging-lag-days``) rather than a hardcoded
    schedule, and it is echoed into the reading so a reader can see which
    assumption produced the pairing. When nothing is eligible even with the
    lag the theme was only ever staged *after* this review, and the fallback
    takes the EARLIEST row — nearest to the review — rather than the latest.

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
        cutoff = (review_day + timedelta(days=staging_lag_days)).isoformat()
        eligible = [row for row in ordered if row[0][:10] <= cutoff]
        if eligible:
            chosen = eligible[-1]
    late = chosen is None and review_day is not None
    if chosen is None:
        # Undated review: nothing to compare against, so the latest row is
        # the only defensible pick and REVIEW_DATE_UNPARSEABLE names the
        # doubt. Dated review with nothing eligible: every row post-dates the
        # batch, so the nearest one is the earliest.
        chosen = ordered[0] if review_day is not None else ordered[-1]
    description = chosen[1].strip()
    return (description or None), late


@dataclass(frozen=True)
class LabelStats:
    """Where every rejection went, in counts that add up.

    Two identities hold and are asserted by the tests, because a ground-truth
    tally with a silent residual is the same failure as a rate without its
    denominator — a reader who sums the printed fields must not come up short:

        rejections           == naming_a_store_skill + naming_nothing
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
    queries_truncated: int
    unresolved_names: tuple[str, ...]
    candidates_also_in_store: int


def build_pairs(
    sections: Sequence[ReviewSection],
    *,
    store_names: dict[str, str],
    ledger: dict[str, list[tuple[str, str]]],
    review_days: dict[str, date | None],
    name_only_queries: str,
    max_chars: int = MAX_TEXT_CHARS,
    staging_lag_days: int = DEFAULT_STAGING_LAG_DAYS,
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
    queries_truncated = 0
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
            canonical = store_names.get(token) or store_names.get(
                _TRAILING_ISO_DATE_RE.sub("", token)
            )
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
            ledger,
            section.candidate,
            review_days.get(section.review),
            staging_lag_days=staging_lag_days,
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
        if len(query) > max_chars:
            queries_truncated += 1
            query = query[:max_chars]
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
        queries_truncated=queries_truncated,
        unresolved_names=tuple(sorted(unresolved)),
        candidates_also_in_store=candidates_also_in_store,
    )
    return tuple(pairs), stats


# ----------------------------------------------------------------------- arms
#
# An arm returns one ranking per pair, ``None`` where it has no usable ranking
# for that pair. ``recall_at_k`` scores only the non-None entries and reports
# the reduced denominator, so a degenerate query lowers the visible exposure
# instead of contributing an alphabetical guess.


def lexical_rankings(
    pairs: Sequence[LabelledPair], docs: Sequence[StoreSkill]
) -> list[tuple[str, ...] | None]:
    """Trigram-Jaccard rankings; None for a query that shares nothing.

    Unlike the cosine arm, a no-spread query here does NOT abstain the whole
    arm. The causes differ: for embeddings, every document scoring the same
    means the model is broken, which invalidates every ranking it produced;
    for trigrams it means this particular short query shares no character
    trigram with any skill file, which says nothing about the other queries.
    """
    doc_grams = [(doc.name, trigrams(doc.text)) for doc in docs]
    rankings: list[tuple[str, ...] | None] = []
    for pair in pairs:
        query_grams = trigrams(pair.query)
        scores = {name: jaccard(query_grams, grams) for name, grams in doc_grams}
        rankings.append(None if _no_spread(scores) else _rank(scores))
    return rankings


def cosine_rankings(
    pairs: Sequence[LabelledPair], docs: Sequence[StoreSkill]
) -> tuple[list[tuple[str, ...] | None] | None, str | None, str]:
    """Embedding rankings, or (None, reason, model) when the seam is unusable.

    The import is deferred so the lexical arm runs with a bare ``python3`` and
    no installed package (the weekly scripts are invoked that way), and it
    brings ``core.embeddings.cosine`` rather than a local reimplementation —
    numpy is already loaded by then, so the only thing a private copy bought
    was a second definition to keep in sync.

    Every failure mode gets its own code, because a *degenerate* ranking is
    the dangerous one: ``cosine`` answers 0.0 for a dimension mismatch or a
    zero-norm vector, and ``_rank``'s name tie-break then turns an all-zero
    score dict into a confident-looking alphabetical ranking that
    ``recall_at_k`` would happily score. That inflates recall in the
    permissive direction — straight at ADR-0097's "build the bundle when
    recall@5 >= 0.9" Review-when. NaN and Inf are checked explicitly: NaN is
    truthy so ``any()`` passes it, every NaN comparison is False so
    ``max == min`` passes it, and ``norm == 0.0`` is False for NaN, so all
    three of the other guards let it through to score as an alphabetical
    ranking. Python's ``json`` accepts bare ``NaN`` / ``Infinity`` tokens, so
    a numerically failing local model reaches here intact.
    """
    try:
        import numpy as np

        from contemplative_agent.core.embeddings import (
            _get_embedding_model,
            cosine,
            embed_texts,
        )
    # Not just ImportError: a broken native extension raises OSError or
    # RuntimeError, and a traceback here would exit 1 with no reason code.
    except Exception as exc:  # noqa: BLE001 - any import failure is one reason
        return None, f"EMBEDDING_IMPORT_FAILED: {type(exc).__name__}: {exc}", "unknown"

    model = _get_embedding_model()
    doc_matrix = embed_texts([doc.text for doc in docs])
    # Row count is compared for equality, not just for shortfall: a response
    # with MORE rows than inputs is as unusable as one with fewer, and would
    # otherwise reach the strict zip in recall_at_k as a traceback instead of
    # a reason code (ADR-0077 fault column).
    if doc_matrix is None or len(doc_matrix) != len(docs):
        return None, "EMBEDDING_UNAVAILABLE", model
    query_matrix = embed_texts([pair.query for pair in pairs])
    if query_matrix is None or len(query_matrix) != len(pairs):
        return None, "EMBEDDING_UNAVAILABLE", model

    try:
        doc_array = np.asarray(doc_matrix, dtype=np.float64)
        query_array = np.asarray(query_matrix, dtype=np.float64)
    except (TypeError, ValueError):
        # Ragged rows: numpy refuses, and so does this reading.
        return None, "EMBEDDING_DEGENERATE", model
    if doc_array.ndim != 2 or query_array.ndim != 2:
        return None, "EMBEDDING_DEGENERATE", model
    if doc_array.shape[1] == 0 or doc_array.shape[1] != query_array.shape[1]:
        return None, "EMBEDDING_DEGENERATE", model
    for array in (doc_array, query_array):
        if not np.isfinite(array).all():
            return None, "EMBEDDING_DEGENERATE", model
        if not array.any(axis=1).all():
            return None, "EMBEDDING_DEGENERATE", model

    # Dimensions are equal by the check above, so core's shape-mismatch
    # WARNING branch is unreachable from here.
    rankings: list[tuple[str, ...] | None] = []
    for query_vector in query_array:
        scores = {
            docs[index].name: cosine(query_vector, doc_vector)
            for index, doc_vector in enumerate(doc_array)
        }
        if _no_spread(scores):
            return None, "EMBEDDING_DEGENERATE", model
        rankings.append(_rank(scores))
    return rankings, None, model


def rrf_rankings(
    left: Sequence[tuple[str, ...] | None],
    right: Sequence[tuple[str, ...] | None],
    rrf_k: int,
) -> list[tuple[str, ...] | None]:
    """Reciprocal-rank fusion; None wherever either arm had no ranking."""
    fused: list[tuple[str, ...] | None] = []
    for left_ranking, right_ranking in zip(left, right, strict=True):
        if left_ranking is None or right_ranking is None:
            fused.append(None)
            continue
        scores: dict[str, float] = {}
        for ranking in (left_ranking, right_ranking):
            for position, name in enumerate(ranking, start=1):
                scores[name] = scores.get(name, 0.0) + 1.0 / (rrf_k + position)
        fused.append(_rank(scores))
    return fused


def recall_at_k(
    pairs: Sequence[LabelledPair],
    rankings: Sequence[tuple[str, ...] | None],
    ks: Sequence[int],
) -> dict[str, Any]:
    """Share of scored candidates with at least one named skill in the top k.

    "At least one" rather than "all": a rejection that names two covering
    skills is one coverage judgment the bundle would have to surface, not two
    independent retrieval targets. ``multi_label_pairs`` in the reading says
    how many pairs the distinction applies to.
    """
    scored = [
        (pair, ranking)
        for pair, ranking in zip(pairs, rankings, strict=True)
        if ranking is not None
    ]
    out: dict[str, Any] = {}
    for k in ks:
        hits = sum(
            1 for pair, ranking in scored if any(label in ranking[:k] for label in pair.labels)
        )
        out[str(k)] = {
            "hits": hits,
            "pairs": len(scored),
            "rate": round(hits / len(scored), 4) if scored else None,
            "ci95": wilson_ci(hits, len(scored)),
        }
    return out


def _arm_block(
    pairs: Sequence[LabelledPair],
    rankings: Sequence[tuple[str, ...] | None],
    ks: Sequence[int],
    metric: str,
    **extra: Any,
) -> dict[str, Any]:
    degenerate = sum(1 for ranking in rankings if ranking is None)
    return {
        "available": True,
        "metric": metric,
        "queries_with_no_score_spread": degenerate,
        "recall": recall_at_k(pairs, rankings, ks),
        **extra,
    }


# -------------------------------------------------------------------- reading


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
    staging_lag_days: int,
    read_faults: dict[str, int],
    partial_reasons: Sequence[str],
) -> dict[str, Any]:
    """Assemble the reading from already-loaded inputs (pure; unit-testable)."""
    # Scalar validation lives here, not in main: build_reading is the pure,
    # independently-callable entry point the tests use directly, and rrf_k < 1
    # divides by zero inside rrf_rankings.
    if rrf_k < 1:
        raise ScanError("BAD_RRF_K", str(rrf_k))
    if min_pairs < 1:
        raise ScanError("BAD_MIN_PAIRS", str(min_pairs))
    if not pairs:
        raise ScanError(
            "NO_LABELLED_PAIRS",
            f"{label_stats.rejections} rejections read, "
            f"{label_stats.naming_nothing} named no store skill, "
            f"{label_stats.name_only_excluded} had no ledger text",
        )

    reasons = list(partial_reasons)
    arm_readings: dict[str, Any] = {}
    lexical: list[tuple[str, ...] | None] | None = None
    cosine_ranks: list[tuple[str, ...] | None] | None = None
    cosine_code = "EMBEDDING_UNAVAILABLE"
    cosine_detail: str | None = None
    embedding_model = "unknown"

    if "lexical" in arms or "union" in arms:
        lexical = lexical_rankings(pairs, docs)
    if "cosine" in arms or "union" in arms:
        cosine_ranks, cosine_reason, embedding_model = cosine_rankings(pairs, docs)
        if cosine_reason is not None:
            cosine_code, _, cosine_detail = cosine_reason.partition(": ")
            reasons.append(cosine_code)

    if "lexical" in arms and lexical is not None:
        arm_readings["lexical"] = _arm_block(
            pairs, lexical, ks, "character-trigram Jaccard over the whole skill file"
        )
    if "cosine" in arms:
        if cosine_ranks is None:
            arm_readings["cosine"] = {
                "available": False,
                "reason": cosine_code,
                # The detail separates "the package is not installed" from
                # "a native extension is broken" — different repairs.
                "detail": cosine_detail or None,
                "embedding_model": embedding_model,
            }
        else:
            arm_readings["cosine"] = _arm_block(
                pairs,
                cosine_ranks,
                ks,
                "embedding cosine (core/embeddings.py)",
                # The model that actually served this run, not the pinned
                # default: OLLAMA_EMBEDDING_MODEL overrides it, and a
                # same-dimension swap passes every shape check above.
                embedding_model=embedding_model,
            )
    if "union" in arms:
        if lexical is None or cosine_ranks is None:
            arm_readings["union"] = {"available": False, "reason": "UNION_ARM_INCOMPLETE"}
        else:
            arm_readings["union"] = _arm_block(
                pairs,
                rrf_rankings(lexical, cosine_ranks, rrf_k),
                ks,
                f"reciprocal-rank fusion of lexical and cosine (rrf_k={rrf_k})",
            )

    if not any(arm.get("available") for arm in arm_readings.values()):
        # Carry each arm's own reason into the detail: a cosine-only run that
        # fails otherwise discards the root cause the mixed-arm path prints,
        # and "cosine" alone does not say whether to install a package, start
        # Ollama, or distrust the model.
        why = "; ".join(
            f"{name}={block.get('reason', 'unavailable')}"
            for name, block in sorted(arm_readings.items())
        )
        raise ScanError("NO_ARM_AVAILABLE", why or ", ".join(sorted(arms)))
    if any(arm.get("queries_with_no_score_spread") for arm in arm_readings.values()):
        reasons.append("DEGENERATE_QUERY_RANKING")

    # With labels drawn from the store and a ranking that covers all of it,
    # any k at or above the corpus size scores 1.0 by construction. Never
    # fires at 57 skills with the default k, but the same 1.0 would be read
    # against the >= 0.9 Review-when.
    if any(k >= len(docs) for k in ks):
        reasons.append("K_EXCEEDS_CORPUS")

    doc_chars = sorted(len(doc.text) for doc in docs)
    docs_truncated = sum(1 for doc in docs if doc.original_chars > len(doc.text))
    if docs_truncated or label_stats.queries_truncated:
        reasons.append("CORPUS_TRUNCATED")
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
        "staging_lag_days": staging_lag_days,
        "reviews": list(reviews),
        "corpus_skills": len(docs),
        "corpus_doc_chars": {
            "min": doc_chars[0],
            "median": int(statistics.median(doc_chars)),
            "max": doc_chars[-1],
        },
        "corpus_truncation": {
            "limit": MAX_TEXT_CHARS,
            "docs_truncated": docs_truncated,
            "queries_truncated": label_stats.queries_truncated,
            "longest_original": max(doc.original_chars for doc in docs),
            "applies_to": "every arm (truncated once at load, before any ranking)",
        },
        # Magnitudes, not just the boolean the reason code carries. A
        # corrupt skill file shrinks the corpus, which mechanically RAISES
        # recall@k for every surviving pair and re-attributes its rejections
        # to "the reviewer named no store skill" — so the counts have to
        # reach the reader, not only the fact that something went wrong.
        "read_faults": read_faults,
        "ground_truth": {
            # rejections == naming_a_store_skill + naming_no_store_skill, and
            # naming_a_store_skill == labelled_pairs_kept + the name-only
            # exclusions below. Both identities close by construction so a
            # reader summing these fields never comes up short.
            "rejections": label_stats.rejections,
            "rejections_naming_a_store_skill": label_stats.naming_a_store_skill,
            "rejections_naming_no_store_skill": label_stats.naming_nothing,
            "labelled_pairs_kept": label_stats.kept_pairs,
            "naming_tally_complete": not read_faults.get("unreadable_skill_files", 0),
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
            "Labels are an unfiltered scan for store names in the reject "
            "body, so a negated mention ('this is NOT covered by foo-bar') "
            "yields foo-bar as a POSITIVE label. Nothing here detects "
            "negation; spot-check the reject prose before treating a low "
            "recall as a retrieval failure.",
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
    parser.add_argument(
        "--staging-lag-days",
        type=int,
        default=DEFAULT_STAGING_LAG_DAYS,
        help="days between a review's filename date and its own batch's ledger rows "
        "(the pipeline names a review after yesterday; see _candidate_description)",
    )
    parser.add_argument(
        "--allow-partial-store",
        action="store_true",
        help="proceed when a skill file is unreadable (default: abstain — a smaller "
        "corpus raises recall@k for every surviving pair)",
    )
    args = parser.parse_args(argv)

    try:
        arms = tuple(dict.fromkeys(args.arm)) if args.arm else ARMS
        ks = _parse_k(args.k)
        review_paths = _collect_reviews(args.review, args.review_dir)
        docs, unreadable_skills, duplicate_store_names = load_store(args.skills_dir)
        if unreadable_skills and not args.allow_partial_store:
            raise ScanError(
                "SKILLS_PARTIAL_READ",
                f"{unreadable_skills} skill file(s) unreadable — a smaller corpus raises "
                "recall@k and re-attributes rejections to the reviewer; pass "
                "--allow-partial-store to read anyway",
            )
        ledger, ledger_faults = load_candidates(args.candidates)
        reviews = load_reviews(review_paths)

        pairs, label_stats = build_pairs(
            reviews.sections,
            store_names={doc.name.lower(): doc.name for doc in docs},
            ledger=ledger,
            review_days=reviews.review_days,
            name_only_queries=args.name_only_queries,
            staging_lag_days=args.staging_lag_days,
        )

        read_faults = {
            "unreadable_skill_files": unreadable_skills,
            "store_files_sharing_a_name": duplicate_store_names,
            "unreadable_reviews": reviews.unreadable,
            "undated_reviews": reviews.undated,
            "duplicate_review_basenames": reviews.duplicate_names,
            "review_sections_without_a_candidate_name": reviews.unnamed_sections,
            "ledger_unparsable_lines": ledger_faults.unparsable_lines,
            "ledger_rows_without_a_name": ledger_faults.rows_without_a_name,
            "ledger_rows_with_an_unusable_ts": ledger_faults.rows_with_an_unusable_ts,
        }
        # One list, so a new counter cannot be added without its code.
        fault_codes = (
            ("unreadable_skill_files", "SKILLS_PARTIAL_READ"),
            ("store_files_sharing_a_name", "STORE_NAME_COLLISION"),
            ("unreadable_reviews", "REVIEW_PARTIAL_READ"),
            ("undated_reviews", "REVIEW_DATE_UNPARSEABLE"),
            ("duplicate_review_basenames", "DUPLICATE_REVIEW_NAME"),
            ("review_sections_without_a_candidate_name", "REVIEW_SECTION_WITHOUT_CANDIDATE_NAME"),
            ("ledger_unparsable_lines", "LEDGER_PARTIAL_PARSE"),
            ("ledger_rows_without_a_name", "LEDGER_PARTIAL_PARSE"),
            ("ledger_rows_with_an_unusable_ts", "LEDGER_ROW_WITHOUT_A_TIMESTAMP"),
        )
        partial = [code for key, code in fault_codes if read_faults[key]]

        reading = build_reading(
            pairs=pairs,
            docs=docs,
            label_stats=label_stats,
            reviews=reviews.names,
            arms=arms,
            ks=ks,
            rrf_k=args.rrf_k,
            min_pairs=args.min_pairs,
            name_only_queries=args.name_only_queries,
            staging_lag_days=args.staging_lag_days,
            read_faults=read_faults,
            partial_reasons=partial,
        )
    except ScanError as exc:
        # `reason=` token per the scripts/_scan.py contract (the weekly chain
        # greps it out of a stage's .err file); exit 2 matches every other
        # instrument's "the reading is unavailable".
        print(f"retrieval_recall_measure: reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 2

    if not reading["decision_input"]:
        print(
            f"retrieval_recall_measure: reason=BELOW_DECISION_FLOOR "
            f"{reading['labelled_pairs']} labelled pairs < "
            f"{reading['min_pairs_for_decision']} — read as context, not as a decision input",
            file=sys.stderr,
        )
    print(json.dumps(reading, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
