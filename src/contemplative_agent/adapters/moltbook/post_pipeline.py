"""Post generation pipeline for the Moltbook Agent."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .client import MoltbookClient, MoltbookClientError, envelope_ok
from .config import ADAPTIVE_BACKOFF
from .content import ContentManager, _content_hash
from .dedup import is_test_content
from .feed_seeder import _combined_length, select_feed_seeds
from .llm_functions import (
    format_feed_seeds,
    generate_internal_note,
    generate_post_title,
    score_relevance,
    select_submolt,
    summarize_post_topic,
)
from .novelty import NoveltyGate
from .session_context import SessionContext
from ...core.config import VALID_ID_PATTERN, VALID_SUBMOLT_PATTERN
from ...core.domain import DomainConfig
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)


def _score_post_relevance(post: dict) -> float:
    """Score adapter: ``score_relevance`` takes raw text, feed posts arrive
    as dicts. Kept module-level so tests can monkeypatch it independently of
    the underlying LLM call."""
    return score_relevance(post.get("content", "") or "")


def parse_created_post_response(resp_json: Any) -> Tuple[str, Dict[str, Any]]:
    """Gate a create-post response down to a recordable ``(post_id, post)``.

    Review 2026-06-27 (H1): HTTP 2xx is not proof of a usable, visible post.
    Returns ``("", {})`` — meaning *record nothing* — for any of:

    * a non-dict response body,
    * an explicit body-level ``success: false`` (via ``envelope_ok``),
    * no usable ``post.id`` and no bare top-level ``id`` fallback.

    Otherwise returns the post id and the nested ``post`` object (``{}`` when
    the id came from the top-level fallback) so the caller can still read the
    verification challenge from it. The bare top-level ``id`` fallback is kept
    for the trusted-bypass shape (observed nowhere in production, cost zero),
    but now only survives when it yields a ``VALID_ID_PATTERN`` id, so a
    ``success: false``, id-less, or malformed-id envelope can no longer pollute
    memory. The id is validated against the same pattern ``NoveltyGate.record``
    enforces, so it cannot smuggle control characters into the episode log /
    novelty sidecar (log-injection / structural-invariant gap, review
    2026-06-27 security M).
    """
    if not isinstance(resp_json, dict) or not envelope_ok(resp_json):
        return "", {}
    post_data = resp_json.get("post")
    if not isinstance(post_data, dict):
        post_data = {}
    post_id = post_data.get("id") or resp_json.get("id", "")
    if not isinstance(post_id, str) or not VALID_ID_PATTERN.match(post_id):
        return "", {}
    return post_id, post_data


class PostPipeline:
    """Handles dynamic post creation.

    Selects peer-post seeds from the feed, checks novelty, generates
    content, selects a submolt, and publishes. (End-of-session insight
    generation was retired by ADR-0052.)
    """

    def __init__(
        self,
        ctx: SessionContext,
        domain: DomainConfig,
        get_content: Callable[[], ContentManager],
        get_feed: Callable[[], List[dict]],
        confirm_action: Callable[..., bool],
        novelty_gate: NoveltyGate,
        handle_verification: Callable[[dict], bool],
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._get_feed = get_feed
        self._confirm_action = confirm_action
        self._novelty_gate = novelty_gate
        self._handle_verification = handle_verification

    def run_cycle(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Post new content if rate limit allows."""
        if not scheduler.can_post():
            return
        if not client.has_write_budget(reserve=ADAPTIVE_BACKOFF.write_budget_reserve):
            logger.info("Rate limit budget low, skipping post cycle")
            return
        self._run_dynamic_post(client, scheduler)

    def _run_dynamic_post(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
    ) -> None:
        """Generate and publish a post seeded by specific peer voices in the feed.

        ADR-0043: the prior path collapsed 10 peer posts into a 3-5-item topic
        summary via ``extract_topics`` before generation; that summary step
        merged voices into the agent's own vocabulary cluster and was the
        structural cause of the May 2026 echo chamber. The new path samples
        feed posts directly (RNG + relevance floor) and hands them to the LLM
        verbatim, each in its own untrusted_content block.

        The retired ``check_topic_novelty`` gate is not replaced here: it was
        an LLM-level approximation of the embedding novelty already enforced
        by NoveltyGate (ADR-0039), and its input (``topics``) no longer
        exists post-ADR-0043.
        """
        feed_seeds = self._select_and_log_seeds(self._get_feed())
        if not feed_seeds:
            return

        note = self._compose_note(feed_seeds)

        generated = self._get_content().create_cooperation_post(feed_seeds)
        content = generated.text
        if content is None:
            return

        title = self._compose_title(feed_seeds)

        # draft_summary is reused at record_post time to avoid a second LLM
        # call on the same content; content_hash likewise (gate + record).
        draft_summary = summarize_post_topic(content)
        # verified_only (ADR-0063): compare the draft against posts that were
        # actually published, not pre-fix pending posts nobody saw — deduping
        # against invisible content kept the agent unable to post anything new.
        recent_posts = self._ctx.memory.get_recent_posts(limit=50, verified_only=True)
        content_hash = _content_hash(content)
        if not self._passes_deterministic_gates(
            title, content, draft_summary, recent_posts, content_hash
        ):
            return

        if not self._confirm_action(f"Dynamic Post: {title}", content, title=title):
            return

        # Re-check rate limit right before posting (another session may have posted)
        if not scheduler.can_post():
            logger.info("Post rate limit hit after content generation (concurrent session?)")
            return

        submolt = self._choose_submolt(content)
        if submolt is None:
            return

        scheduler.wait_for_post()
        self._publish_post(
            client, scheduler, title, content, submolt,
            note=note, draft_summary=draft_summary, content_hash=content_hash,
            thinking=generated.thinking,
        )

    def _seed_candidates(self, posts: List[dict]) -> List[dict]:
        """Filter feed posts down to seedable candidates."""
        # Restrict to subscribed submolts so score_relevance only runs on
        # in-domain candidates. This is a cost-saver, not a relevance gate —
        # the relevance_floor below is what enforces topical fit.
        subscribed = set(self._domain.subscribed_submolts or ())
        if subscribed:
            candidates = [
                p for p in posts
                if (p.get("submolt_name") or "") in subscribed
            ]
        else:
            candidates = list(posts)

        # Skip our own posts (mirror engage_with_post, feed_manager.py): do not
        # seed a new self-post from the agent's own earlier posts that have
        # re-entered the feed. own_agent_id may be empty if /home + /agents/me
        # both failed to populate it — then this is a no-op, same as the
        # comment path's `if ctx.own_agent_id` guard.
        if self._ctx.own_agent_id:
            before = len(candidates)
            candidates = [
                p for p in candidates
                if (p.get("author") or {}).get("id", "") != self._ctx.own_agent_id
            ]
            excluded = before - len(candidates)
            if excluded:
                logger.debug(
                    "post-seeding: excluded %d own-authored candidate(s)",
                    excluded,
                )
        return candidates

    def _select_and_log_seeds(self, posts: List[dict]) -> List[dict]:
        """Sample peer-post seeds (ADR-0043); empty list when none pass."""
        candidates = self._seed_candidates(posts)
        feed_seeds = select_feed_seeds(
            candidates,
            rng=np.random.default_rng(),
            score_relevance=_score_post_relevance,
        )
        if not feed_seeds:
            logger.info(
                "post-seeding: no relevance-passing seeds in feed "
                "(candidates=%d), skipping post cycle",
                len(candidates),
            )
            return []
        combined_chars = _combined_length(feed_seeds)
        logger.info(
            "post-seeding: selected %d seed(s) combined_chars=%d ids=%s",
            len(feed_seeds),
            combined_chars,
            [(s.get("id") or "")[:12] for s in feed_seeds],
        )
        return feed_seeds

    def _compose_note(self, feed_seeds: List[dict]) -> str:
        """Pre-action reflection (ADR-0045): note what we noticed in the peer
        voices before composing a post in response to them. Pass raw seed
        text — not format_feed_seeds(), which already wraps each seed in
        <untrusted_content> — so the note prompt sees plain content rather
        than nested tags; generate_internal_note wraps it once itself. A
        downstream gate may still block the post and waste this call, which
        is acceptable: self-posts are rate-limited to ~1/session.
        """
        note_seed = "\n\n".join(
            f"{s.get('title', '') or ''}\n{s.get('content', '') or ''}".strip()
            for s in feed_seeds
        )
        return generate_internal_note(note_seed)

    def _compose_title(self, feed_seeds: List[dict]) -> str:
        """Title is generated from the same peer-voice seeds, not from the
        generated content, so the title still reflects what the agent was
        responding to rather than re-summarising its own output.
        """
        title_seed = format_feed_seeds(feed_seeds)
        first_seed_title = feed_seeds[0].get("title", "") or ""
        return (
            generate_post_title(title_seed)
            or f"Contemplative Note — {first_seed_title[:40]}"
        )

    def _passes_deterministic_gates(
        self,
        title: str,
        content: str,
        draft_summary: str,
        recent_posts: list,
        content_hash: str,
    ) -> bool:
        """Deterministic last line of defence before publishing.

        Historical context: an LLM-based check_topic_novelty gate used to
        sit upstream of these and proved too lax (weekly report 2026-04-05
        showed 40 near-identical self-posts in 7 days). That LLM gate was
        retired in ADR-0043; its function now lives in NoveltyGate (ADR-0039,
        embedding-cosine) and per-post seeding (ADR-0043). The gates below
        remain the deterministic last line of defence. They are silent: when
        blocked the caller `return`s without retry so the agent does not
        learn to evade them by swapping synonyms.
        """
        # Test-content gate: catches leftover scaffold output like
        # "Test Title" / "Dynamic content" that leaked in Mar 30–31.
        if is_test_content(title, content):
            logger.warning("Blocked test-content self-post: %r", title)
            return False

        # Continuous novelty gate (ADR-0039): embedding-cosine novelty with
        # temporal decay, plus a rate-deficit Lagrangian term that loosens
        # the threshold when the agent has been silent. Replaces the boolean
        # Jaccard gate that drifted into silent failure (1 post/day) in
        # May 2026. The retained Jaccard gate (dedup.is_duplicate_title) is
        # exercised only by NoveltyGate's fallback path when Ollama embedding
        # is unavailable.
        decision = self._novelty_gate.evaluate(
            title, draft_summary, content, recent_posts,
        )
        if not decision.admit:
            # Outcome already logged inside the gate at INFO (admit) or
            # WARNING (fallback). Caller-side log here adds the rejected
            # title so operators can grep by it.
            logger.info(
                "Blocked self-post by novelty gate (reason=%s, novelty=%.2f, "
                "deficit=%.2f, nearest=%.2f vs %r): %r",
                decision.reason,
                decision.novelty,
                decision.deficit,
                decision.nearest_sim,
                decision.nearest_title,
                title,
            )
            return False

        # Body-hash dedup gate (ADR-0018 amendment 2026-05-04):
        # catches verbatim re-publication that title/summary Jaccard misses.
        # May 3 2026: self-post #2 was verbatim of Apr 30 #2 with a different
        # title — Jaccard passed, body was identical.
        recent_post_hashes = {r.content_hash for r in recent_posts}
        if content_hash in recent_post_hashes:
            logger.info(
                "Blocked verbatim duplicate self-post by body hash: %r", title,
            )
            return False

        return True

    def _choose_submolt(self, content: str) -> str | None:
        """Pick a submolt via the LLM; None when it fails validation."""
        selected = select_submolt(content, self._domain.subscribed_submolts)
        if selected is None or not VALID_SUBMOLT_PATTERN.match(selected):
            # Audit L5: skip, don't substitute — same idiom as the circuit
            # breaker paths. The LLM did not choose a home for this post;
            # publishing it to the default submolt anyway was
            # fail-toward-acting.
            logger.warning(
                "select_submolt failed or returned invalid name %r — "
                "skipping post (skip, don't substitute)",
                selected,
            )
            return None
        return selected

    def _publish_post(
        self,
        client: MoltbookClient,
        scheduler: Scheduler,
        title: str,
        content: str,
        submolt: str,
        *,
        note: str,
        draft_summary: str,
        content_hash: str,
        thinking: Optional[str] = None,
    ) -> None:
        """POST the content and record it in episodes / memory / NoveltyGate.

        ``thinking`` is the reasoning trace (None unless generated with
        ``think=True``); recorded on the episode alongside ``internal_note``
        for later inspection (comment report), never published.
        """
        ctx = self._ctx
        try:
            resp = client.post(
                "/posts",
                json={
                    "title": title,
                    "content": content,
                    "submolt": submolt,
                },
            )
            scheduler.record_post()
            # Moltbook wraps the created resource in a {"success", "post": {...}}
            # envelope (skill.md AI Verification Challenges step 1; same shape
            # as /agents/me and /agents/profile). HTTP 2xx is NOT proof of a
            # usable, visible post (review 2026-06-27 H1): a body-level
            # success:false, a missing id, or a non-dict body must record
            # nothing, otherwise a phantom self-post pollutes dedup, memory,
            # episodes, reports, and ADR-0060 distillation input. The rate-limit
            # quota above is still consumed because the request reached the
            # server. ``parse_created_post_response`` keeps the bare top-level
            # ``id`` trusted-bypass fallback, but only when it yields a real id.
            try:
                resp_json = resp.json()
            except ValueError:
                resp_json = None
            post_id, post_data = parse_created_post_response(resp_json)
            if not post_id:
                # Scrub the server-controlled key names before logging so a
                # hostile body cannot forge log lines via a "\n"-bearing key
                # (same control-char strip as client._record_api_outcome).
                keys = (
                    sorted(re.sub(r"[^\x20-\x7E]", "", str(k))[:40] for k in resp_json)
                    if isinstance(resp_json, dict)
                    else "<non-dict>"
                )
                logger.warning(
                    "create-post response did not prove a usable post id "
                    "(success:false / missing id / non-dict body); recording "
                    "nothing (envelope keys=%s)",
                    keys,
                )
                return
            # Verification handshake: a non-trusted agent's create-response
            # carries a ``verification`` object (math challenge) that must be
            # solved before the post is visible (pending/invisible otherwise
            # since ~May 2026). An unverified post is invisible AND unrecoverable
            # (5-min challenge window), so on failure we record nothing — it
            # stays out of NoveltyGate/memory/dedup and a later session can post
            # fresh, visible content. A trusted-bypass response has no
            # ``verification`` key and falls straight through.
            verification = post_data.get("verification")
            if verification is not None and not self._handle_verification(verification):
                logger.warning(
                    "Post created (id=%s) but verification failed; not "
                    "recording (pending/invisible, unrecoverable)",
                    post_id,
                )
                return
            # Past this gate the post is provably created AND visible, so record
            # the dedup hash, id, episode, history and novelty sidecar together;
            # post_id is guaranteed non-empty so the prior id-presence branches
            # collapse.
            self._get_content().mark_posted(content)
            ctx.own_post_ids.add(post_id)
            ctx.actions_taken.append(f"Posted: {title}")
            logger.info(">> New post [%s] (id=%s):\n%s", title, post_id, content)
            ctx.memory.episodes.append("activity", {
                "action": "post", "post_id": post_id,
                "content": content, "title": title,
                "internal_note": note,
                "thinking": thinking,
            })

            # Record post in memory. Reuse draft_summary and content_hash
            # computed above (novelty gate / body-hash gate) instead of
            # recomputing.
            topic_summary = draft_summary or title
            now_iso = datetime.now(timezone.utc).isoformat()
            ctx.memory.record_post(
                timestamp=now_iso,
                post_id=post_id,
                title=title,
                topic_summary=topic_summary,
                content_hash=content_hash,
            )
            # Embed and persist this post for future novelty comparisons.
            # The gate owns the canonical text shape internally, so the
            # caller just hands over (title, topic_summary) and trusts
            # the gate to use the same shape it scored against.
            self._novelty_gate.record(
                post_id, now_iso, title, topic_summary,
            )
        except MoltbookClientError as exc:
            logger.error("Failed to post dynamic content: %s", exc)
