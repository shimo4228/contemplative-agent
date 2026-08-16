"""Per-post seeding for self-post generation (ADR-0043).

Replaces the pre-ADR-0043 ``extract_topics`` LLM-summary step with direct
sampling of peer posts. The summariser was implicitly merging individual
voices into the agent's own vocabulary cluster (Karuna Manifesto /
Topological Compassion canon, 2026-05-21), defeating the engagement-gradient
repair in ADR-0041.

Design:
- Pure function. No I/O. ``score_relevance`` is injected so unit tests stay
  Ollama-free and the same selector can be reused across call sites. The
  ``should_continue`` pacing predicate is injected for the same reason: the
  scan has to be stoppable from outside without the selector learning what
  a circuit breaker is (T-FEED-PACING).
- RNG is injected (``numpy.random.Generator``) so the production loop gets a
  fresh draw per cycle while tests can pin a seed for determinism.
- Combined-length budget is a *soft* fallback: the selector drops trailing
  posts until the sum fits, but never drops below one. Hard per-post
  truncation lives in ``format_feed_seeds`` (``SEED_MAX_INPUT`` via
  ``wrap_untrusted_content``, audit L6) — the explicit truncation contract
  for the entire pipeline (ADR-0042).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import numpy as np

logger = logging.getLogger(__name__)


def _always_continue() -> bool:
    return True


def select_feed_seeds(
    posts: Sequence[dict],
    *,
    rng: np.random.Generator,
    score_relevance: Callable[[dict], float],
    target_count: int = 3,
    relevance_floor: float = 0.4,
    char_budget: int = 15000,
    should_continue: Callable[[], bool] = _always_continue,
) -> list[dict]:
    """Pick up to ``target_count`` peer posts as direct seeds.

    Shuffle ``posts``, walk in shuffled order, accept the first ones whose
    ``score_relevance`` meets ``relevance_floor`` until ``target_count`` are
    collected. Then drop trailing posts (newest-rejected-first) until the
    combined ``title + content`` length fits ``char_budget`` — but never
    drop below one.

    The 15,000-char default budget is derived from qwen3.5:9b's 32K-token
    context window minus the prompt skeleton and output budget (≈ 8K tokens
    reserved for non-feed content; 15K chars ≈ 4K tokens in English — the
    session-insights footer was retired by ADR-0052, which only widens the
    margin). API spec allows 40,000-char posts, but the production
    distribution (n=50 sample on 2026-05-21) shows p90 = 2,400 chars and
    max = 3,857 chars — so in practice the budget rarely binds. This budget
    is soft (binds only when >1 seed survives); the hard per-seed cap is
    ``SEED_MAX_INPUT`` in ``format_feed_seeds`` (audit L6).

    ``should_continue`` is consulted before each candidate is scored and ends
    the walk when it answers False, keeping whatever was accepted so far. The
    walk's only other exit is ``target_count`` accepts, so a scorer that has
    stopped judging (an LLM outage returns 0.0 for everything) would otherwise
    take it through the entire candidate list at full speed — the shape of the
    2026-07-12 incident (T-FEED-PACING). The caller decides what "keep going"
    means; production passes the circuit breaker's reading.
    """
    if not posts:
        return []
    indices = list(range(len(posts)))
    rng.shuffle(indices)
    accepted: list[dict] = []
    for idx in indices:
        if not should_continue():
            logger.info(
                "Seed selection stopped after %d candidate(s): caller asked to stop",
                len(accepted),
            )
            break
        post = posts[idx]
        try:
            score = score_relevance(post)
        except Exception:  # noqa: BLE001 — relevance is best-effort, never block selection
            logger.debug(
                "score_relevance raised for post %s, treating as 0.0",
                (post.get("id") or "?")[:12],
            )
            score = 0.0
        if score < relevance_floor:
            continue
        accepted.append(post)
        if len(accepted) >= target_count:
            break
    while len(accepted) > 1 and _combined_length(accepted) > char_budget:
        accepted = accepted[:-1]
    return accepted


def _combined_length(seeds: Sequence[dict]) -> int:
    return sum(len(s.get("title", "") or "") + len(s.get("content", "") or "") for s in seeds)
