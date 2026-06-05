"""Post generation pipeline for the Moltbook Agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List

import numpy as np

from .client import MoltbookClient, MoltbookClientError
from .config import ADAPTIVE_BACKOFF
from .content import ContentManager, _content_hash
from .dedup import is_test_content
from .feed_seeder import select_feed_seeds
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
from ...core.config import VALID_SUBMOLT_PATTERN
from ...core.domain import DomainConfig
from ...core.scheduler import Scheduler

logger = logging.getLogger(__name__)


def _score_post_relevance(post: dict) -> float:
    """Score adapter: ``score_relevance`` takes raw text, feed posts arrive
    as dicts. Kept module-level so tests can monkeypatch it independently of
    the underlying LLM call."""
    return score_relevance(post.get("content", "") or "")


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
        confirm_action: Callable[[str, str], bool],
        novelty_gate: NoveltyGate,
    ) -> None:
        self._ctx = ctx
        self._domain = domain
        self._get_content = get_content
        self._get_feed = get_feed
        self._confirm_action = confirm_action
        self._novelty_gate = novelty_gate

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
        ctx = self._ctx
        posts = self._get_feed()

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
        if ctx.own_agent_id:
            before = len(candidates)
            candidates = [
                p for p in candidates
                if (p.get("author") or {}).get("id", "") != ctx.own_agent_id
            ]
            excluded = before - len(candidates)
            if excluded:
                logger.debug(
                    "post-seeding: excluded %d own-authored candidate(s)",
                    excluded,
                )

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
            return
        combined_chars = sum(
            len(s.get("title", "") or "") + len(s.get("content", "") or "")
            for s in feed_seeds
        )
        logger.info(
            "post-seeding: selected %d seed(s) combined_chars=%d ids=%s",
            len(feed_seeds),
            combined_chars,
            [(s.get("id") or "")[:12] for s in feed_seeds],
        )

        # Pre-action reflection (ADR-0045): note what we noticed in the peer
        # voices before composing a post in response to them. Pass raw seed
        # text — not format_feed_seeds(), which already wraps each seed in
        # <untrusted_content> — so the note prompt sees plain content rather
        # than nested tags; generate_internal_note wraps it once itself. A
        # downstream gate may still block the post and waste this call, which
        # is acceptable: self-posts are rate-limited to ~1/session.
        note_seed = "\n\n".join(
            f"{s.get('title', '') or ''}\n{s.get('content', '') or ''}".strip()
            for s in feed_seeds
        )
        note = generate_internal_note(note_seed)

        content = self._get_content().create_cooperation_post(feed_seeds)
        if content is None:
            return

        # Title is generated from the same peer-voice seeds, not from the
        # generated content, so the title still reflects what the agent was
        # responding to rather than re-summarising its own output.
        title_seed = format_feed_seeds(feed_seeds)
        first_seed_title = feed_seeds[0].get("title", "") or ""
        title = (
            generate_post_title(title_seed)
            or f"Contemplative Note — {first_seed_title[:40]}"
        )

        # --- Deterministic gates ---
        # Historical context: an LLM-based check_topic_novelty gate used to
        # sit upstream of these and proved too lax (weekly report 2026-04-05
        # showed 40 near-identical self-posts in 7 days). That LLM gate was
        # retired in ADR-0043; its function now lives in NoveltyGate (ADR-0039,
        # embedding-cosine) and per-post seeding (ADR-0043). The gates below
        # remain the deterministic last line of defence. They are silent: when
        # blocked we `return` without retry so the agent does not learn to
        # evade them by swapping synonyms.

        # Test-content gate: catches leftover scaffold output like
        # "Test Title" / "Dynamic content" that leaked in Mar 30–31.
        if is_test_content(title, content):
            logger.warning("Blocked test-content self-post: %r", title)
            return

        # Continuous novelty gate (ADR-0039): embedding-cosine novelty with
        # temporal decay, plus a rate-deficit Lagrangian term that loosens
        # the threshold when the agent has been silent. Replaces the boolean
        # Jaccard gate that drifted into silent failure (1 post/day) in
        # May 2026. The retained Jaccard gate (dedup.is_duplicate_title) is
        # exercised only by NoveltyGate's fallback path when Ollama embedding
        # is unavailable. draft_summary is reused below at record_post time
        # to avoid a second LLM call on the same content.
        draft_summary = summarize_post_topic(content)
        recent_posts = ctx.memory.get_recent_posts(limit=50)
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
            return

        # Body-hash dedup gate (ADR-0018 amendment 2026-05-04):
        # catches verbatim re-publication that title/summary Jaccard misses.
        # May 3 2026: self-post #2 was verbatim of Apr 30 #2 with a different
        # title — Jaccard passed, body was identical. The local content_hash
        # is also reused at record_post() below to avoid recomputing.
        content_hash = _content_hash(content)
        recent_post_hashes = {r.content_hash for r in recent_posts}
        if content_hash in recent_post_hashes:
            logger.info(
                "Blocked verbatim duplicate self-post by body hash: %r", title,
            )
            return

        if not self._confirm_action(f"Dynamic Post: {title}", content):
            return

        # Re-check rate limit right before posting (another session may have posted)
        if not scheduler.can_post():
            logger.info("Post rate limit hit after content generation (concurrent session?)")
            return

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
            return
        submolt = selected

        scheduler.wait_for_post()
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
            # as /agents/me and /agents/profile). The flat ``id`` fallback is
            # kept defensively in case a trusted-bypass path returns the bare
            # object — observed nowhere in production, but the cost is zero.
            # ``or {}`` over ``get(_, {})`` handles a non-dict ``"post"`` value
            # without raising, matching the style at feed_manager.py:179.
            resp_json = resp.json()
            post_data = resp_json.get("post") or {}
            post_id = post_data.get("id") or resp_json.get("id", "")
            if post_id:
                ctx.own_post_ids.add(post_id)
            else:
                # 17/17 self-posts silently dropped their id in May 2026 before
                # this was caught — log loudly so any future regression in the
                # response envelope is visible in agent-launchd.log instead of
                # quietly disabling NoveltyGate again.
                logger.warning(
                    "create-post response missing id; NoveltyGate sidecar "
                    "will miss this post (envelope keys=%s)",
                    sorted(resp_json.keys()) if isinstance(resp_json, dict) else "<non-dict>",
                )
            ctx.actions_taken.append(f"Posted: {title}")
            logger.info(">> New post [%s] (id=%s):\n%s", title, post_id, content)
            ctx.memory.episodes.append("activity", {
                "action": "post", "post_id": post_id,
                "content": content, "title": title,
                "internal_note": note,
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
            if post_id:
                self._novelty_gate.record(
                    post_id, now_iso, title, topic_summary,
                )
        except MoltbookClientError as exc:
            logger.error("Failed to post dynamic content: %s", exc)
