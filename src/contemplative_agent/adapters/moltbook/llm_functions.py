"""Moltbook-specific LLM functions (scoring, generation, topic extraction)."""

from __future__ import annotations

import logging
import re

from ...core.config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH, MAX_POST_TITLE_LENGTH
from ...core.domain import get_domain_config, resolve_prompt
from ...core.llm import (
    GenerationOutput,
    build_system_prompt_with_skills,
    generate,
    generate_for_api,
    get_identity_system_prompt,
    wrap_untrusted_content,
)
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
from ...core.skill_selection import (
    selected_skills_block,
    shadow_observe_skill_selection,
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
        # LLM unavailable — the 0.0 is a failure sentinel, not a judgment.
        # Without this WARNING an Ollama outage scores every post 0.0 and
        # masquerades downstream as "uninteresting feed", silently polluting
        # the relevance distribution a retune would read
        # (observability sweep 2026-07-10).
        logger.warning(
            "Relevance scoring LLM unavailable — returning 0.0 "
            "(reason=llm_unavailable, not a low score)"
        )
        return 0.0

    match = re.search(r"(\d+(?:\.\d+)?)", result)
    if match:
        score = float(match.group(1))
        if score > 1.0:
            # Audit L2: a value outside the 0-1 contract ("topic 5",
            # "8/10") is a wrong-scale answer, not a high score. Clamping
            # it to 1.0 failed toward acting; reject toward not acting.
            logger.warning("Relevance score out of range, rejecting: %s", result[:80])
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
        content=wrap_untrusted_content(content, max_input=MAX_POST_LENGTH + MAX_COMMENT_LENGTH),
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
        # 8192-token run was a repetition runaway that wastes generation time
        # and adds mid-session memory pressure. 1000 covers real notes with
        # margin (2026-06-27 prefill-degradation handoff).
        num_predict=1000,
    )
    return result.strip() if result else ""


def _selection_system(selection: tuple[str, ...] | None) -> str | None:
    """Map a selector return to the ``system=`` argument for the publish call.

    ADR-0081: ``None`` (shadow mode, fail-open, kill switch) → ``None`` =
    the default full system prompt; a judged selection (possibly empty) →
    a system prompt whose ``<learned_skills>`` block holds only the
    selected bodies (empty selection injects no skills block).
    """
    if selection is None:
        return None
    return build_system_prompt_with_skills(selected_skills_block(selection))


# ADR-0081 Decision 2: post_title runs in the same pipeline pass over the
# same seeds as cooperation_post, so it reuses that pass's selection instead
# of paying a second selector call. Module-level hand-off (single process,
# sequential pipeline); generate_cooperation_post overwrites it every pass,
# so a stale value cannot leak across passes.
_last_cooperation_selection: tuple[str, ...] | None = None


def generate_comment(post_text: str, *, think: bool = False) -> GenerationOutput:
    """Generate a contextual comment for a post.

    ``max_input=MAX_POST_LENGTH`` (ADR-0060 pattern): the cap is set to the
    platform post-length limit so realistic content is never cut — a good
    comment needs the whole post, and a mid-word slice is read as a deliberate
    pause rather than clipping. Since a real post cannot exceed the platform
    limit, this branch never truncates real content; it is a NUM_CTX safety
    valve only (a pathological all-CJK max post is skipped by generate()'s
    budget guard, which protects the system prompt's value layer).

    Returns a :class:`GenerationOutput`: ``.text`` is the comment (None on
    failure/drop), ``.thinking`` the reasoning trace when ``think=True``
    (default False = production; the trace is persisted to the episode log,
    never published).
    """
    wrapped_post = wrap_untrusted_content(post_text, max_input=MAX_POST_LENGTH)
    # ADR-0076 shadow observation / ADR-0081 enforcement: a judged selection
    # under the rollout flag returns skill names → generate under a
    # selection-filtered system prompt; None (shadow, fail-open, kill
    # switch) keeps the full prompt.
    selection = shadow_observe_skill_selection(wrapped_post, generation_caller="moltbook.comment")
    system = _selection_system(selection)
    prompt = COMMENT_PROMPT.format(post_content=wrapped_post)
    # chars_per_token=1.5 (audit M2): CJK output runs 1.5-2 chars/tok; the
    # /3 default under-budgets num_predict and cuts Japanese mid-sentence.
    return generate_for_api(
        prompt,
        max_length=MAX_COMMENT_LENGTH,
        system=system,
        temperature=COMMENT_TEMPERATURE,
        chars_per_token=1.5,
        caller="moltbook.comment",
        think=think,
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
    *,
    think: bool = False,
) -> GenerationOutput:
    """Generate a post that responds to specific peer voices in the feed.

    Pre-ADR-0043 this took a single string containing an LLM-generated
    summary of ~10 peer posts. Post-ADR-0043 it takes a list of peer post
    dicts and hands them to the LLM verbatim (each wrapped independently)
    so the LLM must work with concrete voices rather than an abstracted
    topic cluster. The session-insights context section was retired by
    ADR-0052: ungated self-narrative must not condition next-session
    generation — identity (approval-gated) is the continuity carrier.
    """
    global _last_cooperation_selection
    seeds_text = format_feed_seeds(feed_seeds)
    # ADR-0076 shadow observation / ADR-0081 enforcement (see
    # generate_comment). post_title, which runs in the same pipeline pass
    # over the same seeds, is deliberately not observed — a second selection
    # adds cost, not information; it reuses this pass's selection instead
    # (ADR-0081 Decision 2, via _last_cooperation_selection).
    selection = shadow_observe_skill_selection(
        seeds_text, generation_caller="moltbook.cooperation_post"
    )
    _last_cooperation_selection = selection
    system = _selection_system(selection)
    prompt = _resolve_domain_prompt(COOPERATION_POST_PROMPT).format(
        feed_seeds=seeds_text,
    )
    # Deliberately keeps the chars_per_token=3.0 default (audit M2): /3 ≈
    # 13.4K tok output is ample for posts, and the CJK-safe /1.5 would only
    # request a ≈26.7K budget the C2 guard clamps back under the full system
    # prompt. Note the derived 13.4K itself exceeded the window once the
    # system prompt passed ~19K tok (2026-07-09, 13-skill adoption) — the C2
    # guard now clamps num_predict to the remaining budget instead of
    # skipping, so self-posts survive system-prompt growth.
    return generate_for_api(
        prompt,
        max_length=MAX_POST_LENGTH,
        system=system,
        temperature=COMMENT_TEMPERATURE,
        caller="moltbook.cooperation_post",
        think=think,
    )


def generate_reply(
    original_post: str,
    their_comment: str,
    *,
    think: bool = False,
) -> GenerationOutput:
    """Generate a reply that continues a conversation thread.

    Returns a :class:`GenerationOutput` (``.text`` reply, ``.thinking`` trace
    when ``think=True``); see :func:`generate_comment`.
    """
    # Caps set to the platform field limits (ADR-0060 pattern): a reply needs
    # the whole post and comment, and a mid-word slice is read as a deliberate
    # pause rather than clipping. Real content cannot exceed these limits, so
    # neither branch truncates real content — they are NUM_CTX safety valves
    # only (worst-case ASCII ≈16.7K tok via _estimate_tokens /3, well under the
    # 32768 budget; a pathological all-CJK max is skipped by generate()'s guard).
    wrapped_post = wrap_untrusted_content(original_post, max_input=MAX_POST_LENGTH)
    wrapped_comment = wrap_untrusted_content(their_comment, max_input=MAX_COMMENT_LENGTH)
    # ADR-0076 shadow observation / ADR-0081 enforcement (see generate_comment).
    selection = shadow_observe_skill_selection(
        f"{wrapped_post}\n\n{wrapped_comment}", generation_caller="moltbook.reply"
    )
    system = _selection_system(selection)
    prompt = REPLY_PROMPT.format(
        original_post=wrapped_post,
        their_comment=wrapped_comment,
    )
    # chars_per_token=1.5 (audit M2): same CJK output budget as the comment
    # path — see generate_comment.
    return generate_for_api(
        prompt,
        max_length=MAX_COMMENT_LENGTH,
        system=system,
        temperature=COMMENT_TEMPERATURE,
        chars_per_token=1.5,
        caller="moltbook.reply",
        think=think,
    )


def generate_post_title(feed_seed_text: str) -> str | None:
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
    # Title generation does not surface a reasoning trace (no episode of its
    # own); read only the published text. think defaults off.
    result = generate_for_api(
        prompt,
        max_length=MAX_POST_TITLE_LENGTH,
        # ADR-0081 Decision 2: reuse the cooperation_post pass's selection
        # (same seeds, same pipeline pass) — no second selector call.
        system=_selection_system(_last_cooperation_selection),
        chars_per_token=1.5,
        caller="moltbook.post_title",
    ).text
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
    content: str,
    submolts: tuple[str, ...],
) -> str | None:
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

    # Try to find a match within the response. Longest name first (bug-audit
    # 2026-07-06 L7): with tuple order, a short name that is a substring of a
    # longer sibling ("ai" vs "aiethics") could win against the intended
    # longer match and silently misroute the post.
    for name in sorted(submolts, key=len, reverse=True):
        if name in cleaned:
            logger.info("Submolt %r matched as substring of LLM output %r", name, cleaned)
            return name

    logger.warning("LLM returned unrecognized submolt: %s", result)
    return None
