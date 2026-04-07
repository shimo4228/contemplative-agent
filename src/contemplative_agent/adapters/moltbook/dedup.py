"""Lightweight deterministic dedup gates for self-posts and comment targets.

These gates exist because the LLM-based novelty checks (check_topic_novelty,
relevance scorer) are probabilistic and have proven too lax in practice — see
~/.config/moltbook/reports/analysis/weekly-2026-04-05.md for the empirical
case (40 near-identical self-posts in 7 days).

Design notes:
- No new dependencies. Pure stdlib.
- Token-set Jaccard is sufficient because the failure mode is vocabulary
  fixation (same words reused), not paraphrase. Embeddings would be overkill
  and would not catch the actual problem any better.
- Gates are silent: when a post is blocked, callers `return` without retry.
  This is intentional — the agent should not learn to evade the gate by
  swapping synonyms. "If there is nothing to say, do not say anything."
"""

from __future__ import annotations

import re
from typing import Iterable

# Common English stopwords plus a few connectives that show up in titles.
_STOP: frozenset[str] = frozenset({
    "the", "a", "an", "of", "to", "and", "in", "on", "that", "this", "from",
    "beyond", "with", "is", "are", "for", "by", "into", "be", "as", "at",
    "it", "or", "but", "we", "us", "our", "you", "your", "they", "them",
    "i", "me", "my", "his", "her", "its",
})

_WORD_RE = re.compile(r"[a-z]+")

# Prefix length used as a crude language-agnostic stemmer ("blocking key").
# Most English root forms stabilize within the first 5 characters, so:
#   tremble / trembling / trembled       → tremb
#   metabolize / metabolizing / metabolic → metab
#   fossilized / fossilizing / fossils    → fossi
#   constitution / constitutional         → const
# This collapses inflectional and derivational variants well enough for the
# vocabulary-fixation case the dedup gate is meant to catch, without the
# false positives a Porter stemmer would introduce.
_PREFIX_LEN = 5


def _tokens(text: str) -> set[str]:
    """Normalize text to a token set: lowercase, alpha-only, stopword-free,
    prefix-truncated to act as a crude stemmer, length>2."""
    if not text:
        return set()
    out: set[str] = set()
    for raw in _WORD_RE.findall(text.lower()):
        if raw in _STOP or len(raw) <= 2:
            continue
        out.add(raw[:_PREFIX_LEN])
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity. 0.0 when either side is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_duplicate_title(
    draft_title: str,
    draft_topic_summary: str | None,
    recent_records: Iterable[object],
    threshold: float = 0.25,
) -> tuple[bool, float, str | None]:
    """Check if the draft is too similar to any recent self-post.

    Both the draft and each recent record contribute (title ∪ topic_summary)
    token sets, which are compared via Jaccard.

    Threshold rationale (0.25): Jaccard for short text (5-10 words) is
    intrinsically compressed because the union grows with both inputs while
    the intersection is bounded by the smaller side. Empirically, the
    weekly-2026-04-05 report's 19 duplicate titles pair at 0.20-0.40 even
    after prefix-5 stemming. A 0.25 threshold catches the bulk while leaving
    genuinely different topics (which share ~0 stems) untouched. At runtime
    the topic_summary is also fed in, which lifts real duplicates further
    above 0.25 — title-only is the worst case.

    Args:
        draft_title: The candidate post title.
        draft_topic_summary: Optional 1-line topic summary of the draft body.
        recent_records: Iterable of PostRecord-like objects with .title and
            .topic_summary attributes (duck-typed; works with dataclasses).
        threshold: Minimum Jaccard score that counts as a duplicate.

    Returns:
        (is_duplicate, max_similarity_seen, prior_title_or_None).
    """
    draft = _tokens(draft_title) | _tokens(draft_topic_summary or "")
    if not draft:
        return False, 0.0, None
    best = 0.0
    best_title: str | None = None
    for rec in recent_records:
        prior_title = getattr(rec, "title", "") or ""
        prior_summary = getattr(rec, "topic_summary", "") or ""
        prior = _tokens(prior_title) | _tokens(prior_summary)
        score = jaccard(draft, prior)
        if score > best:
            best = score
            best_title = prior_title
        if best >= threshold:
            return True, best, best_title
    return False, best, best_title


# ---------------------------------------------------------------------------
# Test content gate
# ---------------------------------------------------------------------------

_TEST_PATTERNS: tuple[str, ...] = (
    "test title",
    "dynamic content",
    "lorem ipsum",
    "test post",
)


def is_test_content(title: str, body: str) -> bool:
    """Detect leftover test/scaffold content that should never reach the live
    feed. Triggered the Mar 30–31 spike of 23 'Test Title / Dynamic content'
    posts."""
    blob = f"{title or ''}\n{body or ''}".lower()
    return any(p in blob for p in _TEST_PATTERNS)


# ---------------------------------------------------------------------------
# Promotional content gate
# ---------------------------------------------------------------------------

# Defanged URLs (hxxps) and explicit CTA phrases. Conservative on purpose:
# we'd rather miss spam than false-positive a genuine post that happens to
# include a URL. The CTA branches require `://` after https? so the bare
# word "https" in normal prose ("switch to https is important") does not
# match. Add new patterns as they appear in weekly reports.
_PROMO_RE = re.compile(
    r"(make a profile at\b"
    r"|hxxps?://(inbed|agentflex)\."
    r"|sign up at\s+https?://"
    r"|join us at\s+https?://)",
    re.IGNORECASE,
)


def is_promotional(text: str) -> bool:
    if not text:
        return False
    return bool(_PROMO_RE.search(text))
