"""Okapi BM25 for the scripts/ novelty instruments — one implementation, stdlib only.

Sibling-imported the same way as `_scan.py` and `_stats.py` (scripts/ is not a
package; running a script puts scripts/ on sys.path), so the bare-`python3`
instruments that import it gain no dependency.

Consumers: ``novelty_retrieval_dry_run.py`` (the RFC-0023 entry measurement)
and ``novelty_replay_ab.py`` (its reference column). Both rank one corpus of
skill texts against cluster text, and both must read the same tokenizer and
the same IDF, or their two bm25 columns would be two instruments.

The code was lifted unchanged from ``retrieval_recall_measure.py`` when that
instrument was retired (P1-04.7, 2026-10-31): its readings stay frozen as
``docs/evidence/rfc-0023/retrieval-recall-v{1,2}-*.json``, and a bm25 column
computed here is comparable with the bm25 arm in those files.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

# Okapi BM25's standard constants (Robertson & Zaragoza's own defaults, and
# what Lucene ships): k1 bounds the term-frequency saturation, b the length
# normalization. Not swept — they are the scorer's definition here, not a knob,
# and a tuned pair read against a decision bar would be a fitted number.
BM25_K1 = 1.2
BM25_B = 0.75

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, every non-alphanumeric run collapsed to one space."""
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def bm25_tokens(text: str) -> list[str]:
    """Whitespace tokens of the normalized text — the only tokenizer."""
    return normalize(text).split()


@dataclass(frozen=True)
class Bm25Index:
    """A prepared BM25 corpus: term frequencies, lengths and IDF per document.

    Built once per corpus and reused across queries. ``names`` is the ranking
    key; a repeated name collapses in the score dict (last one wins).
    """

    names: tuple[str, ...]
    term_freqs: tuple[dict[str, int], ...]
    lengths: tuple[int, ...]
    average_length: float
    idf: dict[str, float]
    k1: float
    b: float


def build_bm25_index(
    names: Sequence[str], texts: Sequence[str], *, k1: float = BM25_K1, b: float = BM25_B
) -> Bm25Index:
    """Index ``texts`` (parallel to ``names``) for BM25 scoring.

    The IDF is the non-negative Lucene form,
    ``ln(1 + (N - df + 0.5) / (df + 0.5))``, not the classic Robertson one:
    the classic form goes NEGATIVE for a term carried by more than half the
    corpus, and against a ~57-document store of same-genre skill files that
    is not an edge case — a document would be *penalised* for containing a
    common query word, which reorders the ranking rather than flattening it.
    The non-negative form keeps "a term in every document contributes almost
    nothing" without ever pushing a match below a non-match.
    """
    term_freqs: list[dict[str, int]] = []
    lengths: list[int] = []
    document_freq: dict[str, int] = {}
    for text in texts:
        counts: dict[str, int] = {}
        tokens = bm25_tokens(text)
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        term_freqs.append(counts)
        lengths.append(len(tokens))
        for token in counts:
            document_freq[token] = document_freq.get(token, 0) + 1
    total = len(texts)
    idf = {
        token: math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
        for token, freq in document_freq.items()
    }
    # An all-empty corpus would divide by zero in the length normalizer; 1.0
    # leaves every tf term at 0 anyway (no document has any token).
    average_length = (sum(lengths) / total) if total and sum(lengths) else 1.0
    return Bm25Index(
        names=tuple(names),
        term_freqs=tuple(term_freqs),
        lengths=tuple(lengths),
        average_length=average_length,
        idf=idf,
        k1=k1,
        b=b,
    )


def bm25_scores_from_index(index: Bm25Index, query: str) -> dict[str, float]:
    """Okapi BM25 score per document name for one query against a built index.

    A query term absent from the corpus contributes nothing (no IDF entry),
    and a query sharing no term with anything scores every document 0.0 — the
    caller reads an all-equal dict as "no ranking for this query", never as an
    alphabetical guess.
    """
    query_terms = bm25_tokens(query)
    scores: dict[str, float] = {}
    for position, name in enumerate(index.names):
        counts = index.term_freqs[position]
        norm = index.k1 * (
            1.0 - index.b + index.b * (index.lengths[position] / index.average_length)
        )
        total = 0.0
        for term in query_terms:
            frequency = counts.get(term)
            if not frequency:
                continue
            weight = index.idf.get(term, 0.0)
            total += weight * (frequency * (index.k1 + 1.0)) / (frequency + norm)
        scores[name] = total
    return scores
