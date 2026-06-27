"""Moltbook-specific LLM functions (scoring, generation, topic extraction)."""

from __future__ import annotations

import logging
import re
from typing import Optional

from ...core.config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH, MAX_POST_TITLE_LENGTH
from ...core.domain import get_domain_config, resolve_prompt
from ...core.memory import POST_TOPIC_SUMMARY_MAX
from ...core.prompts import (
    COMMENT_PROMPT,
    COOPERATION_POST_PROMPT,
    INTERNAL_NOTE_PROMPT,
    POST_TITLE_PROMPT,
    RELEVANCE_PROMPT,
    REPLY_PROMPT,
    SUBMOLT_SELECTION_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)
from ...core.llm import (
    generate,
    generate_for_api,
    get_identity_system_prompt,
    wrap_untrusted_content,
)

logger = logging.getLogger(__name__)

# ADR-0047: outward reflective generation (comment / reply / cooperation post)
# raises temperature above the 1.0 production baseline to break formulaic,
# RLHF-baked openings ("What a beautiful moment…"). Candidate-set pruning
# (top_k/top_p/min_p) could not dislodge them; temperature 1.3 flattens the
# mode-collapsed peak while top_k=20 (in core.llm) still caps runaway. Scoring,
# title and distill paths keep the 1.0 default. Validated on comment/reply;
# 1.5 was rejected for axiom-label collapse.
COMMENT_TEMPERATURE = 1.3


def _resolve_domain_prompt(template: str) -> str:
    """Resolve a prompt template with the current domain config."""
    domain = get_domain_config()
    return resolve_prompt(template, domain)


def score_relevance(post_text: str) -> float:
    """Score a post's relevance to domain topics (0.0 to 1.0)."""
    prompt = _resolve_domain_prompt(RELEVANCE_PROMPT).format(
        post_content=wrap_untrusted_content(post_text, max_input=1000),
    )
    # Identity-only system: scoring needs the domain identity as its
    # reference (relevance.md) but not the learned skills/rules corpus.
    result = generate(
        prompt,
        system=get_identity_system_prompt(),
        num_predict=30,
        caller="moltbook.score_relevance",
    )
    if result is None:
        return 0.0

    match = re.search(r"(\d+(?:\.\d+)?)", result)
    if match:
        score = float(match.group(1))
        if score > 1.0:
            # Audit L2: a value outside the 0-1 contract ("topic 5",
            # "8/10") is a wrong-scale answer, not a high score. Clamping
            # it to 1.0 failed toward acting; reject toward not acting.
            logger.warning(
                "Relevance score out of range, rejecting: %s", result[:80]
            )
            return 0.0
        return max(0.0, score)
    logger.warning("Could not parse relevance score: %s", result)
    return 0.0


def generate_internal_note(content: str) -> str:
    """Note what the agent noticed while reading ``content``, before it
    decides how to act on it (pre-action reflection, ADR-0045).

    A single-responsibility call: the note only, as plain text (no schema).
    Kept separate from scoring/generation so the local model focuses on
    noticing rather than juggling two tasks in one prompt. Returns "" on
    failure — callers treat an empty note as "nothing recorded".
    """
    if not INTERNAL_NOTE_PROMPT:
        return ""
    # Cap at the sum of the platform field limits so realistic content is
    # never cut (ADR-0060 pattern, mirrored from distill's EXCERPT_CAPS): a
    # mid-word slice here is read by the note's contemplative register as a
    # deliberate "pause" rather than as clipping. ``content`` is a post on the
    # feed path and ``post + sep + comment`` on the reply path; this bound
    # generously covers both (only content that already exceeds the platform
    # limits could reach it, and then by at most the separator's length). The
    # cap is now only a NUM_CTX safety valve — real posts (p90 ≈ 4.7K chars)
    # never reach it; a pathological max render is skipped by generate()'s
    # budget guard, not silently mid-word-truncated here.
    prompt = INTERNAL_NOTE_PROMPT.format(
        content=wrap_untrusted_content(
            content, max_input=MAX_POST_LENGTH + MAX_COMMENT_LENGTH
        ),
    )
    # Identity-only system: the note keeps the first-person register but
    # not the learned corpus, cutting the vocabulary feedback path
    # note → episode → distill.
    result = generate(
        prompt,
        system=get_identity_system_prompt(),
        caller="moltbook.internal_note",
        # Cap well below the 8192 default: production telemetry (863 calls)
        # shows real notes finish at p90 ≈ 413 tokens (median 264); the lone
        # 8192-token run was a repetition runaway that, under the MLX backend,
        # holds the KV cache and adds mid-session memory pressure. 1000 covers
        # real notes with margin (2026-06-27 prefill-degradation handoff).
        num_predict=1000,
    )
    return result.strip() if result else ""


def generate_comment(post_text: str) -> Optional[str]:
    """Generate a contextual comment for a post.

    ``max_input=MAX_POST_LENGTH`` (ADR-0060 pattern): the cap is set to the
    platform post-length limit so realistic content is never cut — a good
    comment needs the whole post, and a mid-word slice is read as a deliberate
    pause rather than clipping. Since a real post cannot exceed the platform
    limit, this branch never truncates real content; it is a NUM_CTX safety
    valve only (a pathological all-CJK max post is skipped by generate()'s
    budget guard, which protects the system prompt's value layer).
    """
    prompt = COMMENT_PROMPT.format(
        post_content=wrap_untrusted_content(post_text, max_input=MAX_POST_LENGTH)
    )
    # chars_per_token=1.5 (audit M2): CJK output runs 1.5-2 chars/tok; the
    # /3 default under-budgets num_predict and cuts Japanese mid-sentence.
    return generate_for_api(
        prompt,
        max_length=MAX_COMMENT_LENGTH,
        temperature=COMMENT_TEMPERATURE,
        chars_per_token=1.5,
        caller="moltbook.comment",
    )


# Audit L6: per-seed hard cap. The 15K combined budget in select_feed_seeds
# is soft (binds only when >1 seed survives selection), so a single 40K-char
# post passed through uncapped — enough to trip the C2 budget guard and
# suppress the self-post entirely (action-suppression DoS). 5000 = the 15K
# char budget over target_count=3 seeds; production p90 is 2,400 chars
# (n=50, 2026-05-21), so the cap rarely binds on real posts.
SEED_MAX_INPUT = 5000


def format_feed_seeds(seeds: list[dict]) -> str:
    """Format peer posts as direct seeds for ``cooperation_post.md`` (ADR-0043).

    Each post is wrapped in its own ``<untrusted_content>`` block so the LLM
    sees voice boundaries explicitly. The pre-ADR-0043 path wrapped a single
    LLM-generated summary, which implicitly merged voices and was the
    structural cause of the May 2026 echo chamber.
    """
    if not seeds:
        return ""
    blocks: list[str] = []
    for seed in seeds:
        title = seed.get("title", "") or ""
        content = seed.get("content", "") or ""
        body = f"{title}\n{content}" if title else content
        blocks.append(wrap_untrusted_content(body, max_input=SEED_MAX_INPUT))
    return "\n\n".join(blocks)


def generate_cooperation_post(
    feed_seeds: list[dict],
) -> Optional[str]:
    """Generate a post that responds to specific peer voices in the feed.

    Pre-ADR-0043 this took a single string containing an LLM-generated
    summary of ~10 peer posts. Post-ADR-0043 it takes a list of peer post
    dicts and hands them to the LLM verbatim (each wrapped independently)
    so the LLM must work with concrete voices rather than an abstracted
    topic cluster. The session-insights context section was retired by
    ADR-0052: ungated self-narrative must not condition next-session
    generation — identity (approval-gated) is the continuity carrier.
    """
    prompt = _resolve_domain_prompt(COOPERATION_POST_PROMPT).format(
        feed_seeds=format_feed_seeds(feed_seeds),
    )
    # Deliberately keeps the chars_per_token=3.0 default (audit M2): at
    # max_length=40000, the CJK-safe /1.5 would derive num_predict≈26.7K
    # and leave only ~6K tokens of input headroom inside NUM_CTX — the C2
    # budget guard would then skip every self-post under the full system
    # prompt (10-21K tok). /3 ≈ 13.4K tok output is ample for posts.
    return generate_for_api(
        prompt,
        max_length=MAX_POST_LENGTH,
        temperature=COMMENT_TEMPERATURE,
        caller="moltbook.cooperation_post",
    )


def generate_reply(
    original_post: str,
    their_comment: str,
) -> Optional[str]:
    """Generate a reply that continues a conversation thread."""
    # Caps set to the platform field limits (ADR-0060 pattern): a reply needs
    # the whole post and comment, and a mid-word slice is read as a deliberate
    # pause rather than clipping. Real content cannot exceed these limits, so
    # neither branch truncates real content — they are NUM_CTX safety valves
    # only (worst-case ASCII ≈16.7K tok via _estimate_tokens /3, well under the
    # 32768 budget; a pathological all-CJK max is skipped by generate()'s guard).
    prompt = REPLY_PROMPT.format(
        original_post=wrap_untrusted_content(original_post, max_input=MAX_POST_LENGTH),
        their_comment=wrap_untrusted_content(their_comment, max_input=MAX_COMMENT_LENGTH),
    )
    # chars_per_token=1.5 (audit M2): same CJK output budget as the comment
    # path — see generate_comment.
    return generate_for_api(
        prompt,
        max_length=MAX_COMMENT_LENGTH,
        temperature=COMMENT_TEMPERATURE,
        chars_per_token=1.5,
        caller="moltbook.reply",
    )


def generate_post_title(feed_seed_text: str) -> Optional[str]:
    """Generate a post title from peer-post voice blocks (ADR-0043).

    ``feed_seed_text`` is the output of ``format_feed_seeds`` — concatenated
    ``<untrusted_content>`` blocks, one per peer voice. Pre-ADR-0043 the
    input was an LLM-generated topic summary string; the parameter was
    renamed to reflect the post-ADR-0043 contract.
    """
    prompt = _resolve_domain_prompt(POST_TITLE_PROMPT).format(
        feed_seed_text=wrap_untrusted_content(feed_seed_text),
    )
    # chars_per_token=1.5 (audit M2): CJK-safe output budget; at
    # max_length=300 the cost is 250 vs 150 tokens — negligible.
    result = generate_for_api(
        prompt,
        max_length=MAX_POST_TITLE_LENGTH,
        chars_per_token=1.5,
        caller="moltbook.post_title",
    )
    if result:
        # Strip surrounding whitespace, then at most ONE balanced quote
        # pair the LLM may have added (audit L4: the old chained
        # .strip('"').strip("'") deleted every leading/trailing quote
        # char, destroying titles that legitimately start or end with a
        # quotation). Length is already bounded by MAX_POST_TITLE_LENGTH.
        title = result.strip()
        if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":
            title = title[1:-1].strip()
        return title
    return None


def summarize_post_topic(content: str) -> str:
    """Generate a 1-line topic summary for storage in memory.

    The output is truncated to POST_TOPIC_SUMMARY_MAX so the dedup gate
    (token-set Jaccard against memory-stored topic_summaries) sees both
    sides at the same cap.
    """
    prompt = TOPIC_SUMMARY_PROMPT.format(
        post_content=wrap_untrusted_content(content, max_input=2000),
    )
    result = generate(
        prompt,
        system=get_identity_system_prompt(),
        num_predict=60,
        caller="moltbook.topic_summary",
    )
    if result:
        return result.strip()[:POST_TOPIC_SUMMARY_MAX]
    # Audit L7: returning raw post content here stored external prose
    # fragments as topic_summaries, polluting the novelty/embedding store.
    # "" lets the caller's ``draft_summary or title`` idiom fall back to
    # the title instead.
    return ""


def select_submolt(
    content: str, submolts: tuple[str, ...],
) -> Optional[str]:
    """Ask LLM to select the best submolt for a post. Returns None if invalid."""
    submolt_list = ", ".join(submolts)
    prompt = SUBMOLT_SELECTION_PROMPT.format(
        submolt_list=submolt_list,
        post_content=wrap_untrusted_content(content, max_input=1000),
    )
    result = generate(
        prompt,
        system=get_identity_system_prompt(),
        num_predict=20,
        caller="moltbook.select_submolt",
    )
    if result is None:
        return None

    # Extract submolt name from response (may include extra text)
    cleaned = result.strip().lower().strip('"').strip("'")
    if cleaned in submolts:
        return cleaned

    # Try to find a match within the response
    for name in submolts:
        if name in cleaned:
            return name

    logger.warning("LLM returned unrecognized submolt: %s", result)
    return None

