"""Moltbook-specific LLM functions (scoring, generation, topic extraction)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ...core._io import strip_to_printable
from ...core.config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH, MAX_POST_TITLE_LENGTH
from ...core.domain import get_domain_config, resolve_prompt
from ...core.episode_render import safe_peer_name
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


@dataclass(frozen=True)
class RelevanceScore:
    """One relevance judgment plus why it reads the way it does.

    ``score`` alone is lossy: four distinct events all produce 0.0 (empty
    body, LLM outage, unparseable answer, out-of-range answer) and only one
    of them is a judgment. Callers that gate on the number can ignore
    ``reason``; callers that *measure the distribution* must not, or an
    Ollama outage reads as "uninteresting feed" (ADR-0075).
    """

    score: float
    reason: str


def score_relevance_detailed(
    post_text: str,
    *,
    caller: str = "moltbook.score_relevance",
) -> RelevanceScore:
    """Score a post's relevance to domain topics (0.0 to 1.0), with a reason.

    ``reason`` is ``scored`` for a real judgment; ``empty_input``,
    ``llm_unavailable``, ``unparseable`` and ``out_of_range`` each carry 0.0
    for a different cause.

    ``caller`` is the telemetry tag. It defaults to the production gate's
    tag; observation-only callers pass their own so their volume stays
    separable in the per-call telemetry.

    An empty body short-circuits to 0.0 without an LLM call: a feed post dict
    with no ``content`` reaches here via ``post_pipeline._score_post_relevance``
    (``feed_manager`` filters those earlier, that path does not), and wrapping
    "" asserts ``complete (0 chars)`` at the model — the same false-assertion
    class as the reply path's empty post section (weekly-2026-07-24 F1.1).
    "Is there any text" is a structural property, so code answers it rather
    than the LLM (skill: when-code-when-llm).
    """
    if not post_text.strip():
        # DEBUG, not WARNING: an empty feed post is a normal condition, and
        # this 0.0 must stay distinguishable from the outage sentinel below —
        # both land in the relevance distribution a retune reads.
        logger.debug(
            "Empty post text — scoring 0.0 without an LLM call "
            "(reason=empty_input, not a low score)"
        )
        return RelevanceScore(0.0, "empty_input")

    prompt = _resolve_domain_prompt(RELEVANCE_PROMPT).format(
        post_content=wrap_untrusted_content(post_text, max_input=1000),
    )
    # Identity-only system: scoring needs the domain identity as its
    # reference (relevance.md) but not the learned skills/rules corpus.
    result = generate(
        prompt,
        system=get_identity_system_prompt(),
        num_predict=30,
        caller=caller,
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
        return RelevanceScore(0.0, "llm_unavailable")

    match = re.search(r"(\d+(?:\.\d+)?)", result)
    if match:
        score = float(match.group(1))
        if score > 1.0:
            # Audit L2: a value outside the 0-1 contract ("topic 5",
            # "8/10") is a wrong-scale answer, not a high score. Clamping
            # it to 1.0 failed toward acting; reject toward not acting.
            logger.warning(
                "Relevance score out of range, rejecting: %s",
                strip_to_printable(result, 80),
            )
            return RelevanceScore(0.0, "out_of_range")
        return RelevanceScore(max(0.0, score), "scored")
    # WARNING, so this survives a non-verbose production run. The model is
    # scoring untrusted feed text; an unparseable answer is exactly the case
    # where it may be echoing that text back, so bound it and drop the newlines
    # before it reaches a log the weekly sweep reads (T-LOG-DEBUG-CONTENT).
    logger.warning("Could not parse relevance score: %s", strip_to_printable(result, 200))
    return RelevanceScore(0.0, "unparseable")


def score_relevance(post_text: str) -> float:
    """Relevance as a bare number, for the gating callers.

    Thin wrapper over :func:`score_relevance_detailed` — the production
    behaviour (including every 0.0 sentinel) is unchanged. Reach for the
    detailed form when the *distribution* is the product, not the gate.
    """
    return score_relevance_detailed(post_text).score


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


# RFC-0018. Voice labels for the seed blocks. Since the delimiter nonce
# became per-call (ADR-0007 Amendment 2026-08-16) it was the only handle on
# "which of the N voices" — and ``cooperation_post.md`` asks the model to
# bring a second voice in *by name*, so it published the handle it had:
# ``untrusted_content_<hex>`` appeared as a source name in 13 of 31 self-posts
# over 2026-08-22..28 (once miscopied at 14 hex digits). These two are the
# fixed labels for the cases where no display name applies.
#
# The name sits in a bracketed slot, the shape ``episode_render`` already uses
# for the same residue (``[action name]``). That is presentation, not a
# boundary: a name may contain ``]``, and nothing may post-process it —
# safe_peer_name's docstring shows that any transform placed after the
# injection-token strip can reassemble the tokens the strip removed. What the
# brackets buy is that the label reads to the model as a labelled datum rather
# than as a line of our own prose.
SELF_VOICE_LABEL = "Voice: [you — one of your own earlier posts]"
UNKNOWN_VOICE_LABEL = "Voice: [an unnamed community member]"


def _seed_author_name(seed: dict) -> str:
    """Display name off a feed post, with the API's format fallbacks.

    Same chain as ``post_pipeline._seed_candidates`` and ``feed_manager``,
    which read the same feed dicts; ``reply_handler.extract_agent_fields``
    covers the notification shape and is not reusable here.

    ``author`` is type-checked rather than assumed to be a mapping: those
    two sites raise ``AttributeError`` on an ``author`` that is a bare
    string, and a label is the wrong place to convert a platform schema
    change into a lost self-post — an unknown shape falls through to the
    neutral label.
    """
    author = seed.get("author")
    name = author.get("name") if isinstance(author, dict) else None
    return name or seed.get("agent_name") or seed.get("agentName") or ""


def seed_voice_label(seed: dict, own_agent_name: str = "") -> str:
    """The one place a seed's voice label is assembled (both call sites of
    ``format_feed_seeds`` go through it).

    The name is externally authored exactly like the post body, so it gets
    the sanitizer that already exists for that job —
    ``episode_render.safe_peer_name`` (single line guaranteed, length-capped,
    injection-token strip after every transform). Nothing new is written
    here.

    The self branch is a backstop, not the common path: ``_seed_candidates``
    already drops self-authored seeds whenever the own name is known, which
    is also the only case this can detect. It exists so a seed that slips
    past that filter does not read as a peer the agent can answer.
    ``"unknown"`` is ``is_self``'s sentinel, not a name, and falls through to
    the neutral label.

    The self match runs on both the raw and the sanitized name. Raw alone
    mirrors ``SessionContext.is_self``, but here the peer branch normalizes
    afterwards — so a peer named ``"<own name>\u200b"`` passes the raw
    compare (and ``is_self`` upstream) and then renders *as* the agent's own
    name, which is precisely the confusion this label exists to remove. The
    normalized compare is guarded on a non-empty own name so two unnamed
    seeds cannot collide into the self label (code review 2026-08-29).
    """
    raw = _seed_author_name(seed)
    name = safe_peer_name(raw)
    own_name = safe_peer_name(own_agent_name)
    if own_agent_name and (raw == own_agent_name or (own_name and name == own_name)):
        return SELF_VOICE_LABEL
    if not name or name == "unknown":
        return UNKNOWN_VOICE_LABEL
    return f"Voice: [{name}]"


def format_feed_seeds(seeds: list[dict], *, own_agent_name: str = "") -> str:
    """Format peer posts as direct seeds for ``cooperation_post.md`` (ADR-0043).

    Each post is wrapped in its own ``<untrusted_content>`` block so the LLM
    sees voice boundaries explicitly. The pre-ADR-0043 path wrapped a single
    LLM-generated summary, which implicitly merged voices and was the
    structural cause of the May 2026 echo chamber.

    Each block is preceded by a voice label (RFC-0018). The label is *our*
    sentence about the block, not part of the peer's text, so it sits outside
    the frame: the framed bytes and the completeness marker that describes
    them are unchanged, and ``wrap_untrusted_content`` is untouched.
    """
    if not seeds:
        return ""
    blocks: list[str] = []
    for seed in seeds:
        title = seed.get("title", "") or ""
        content = seed.get("content", "") or ""
        body = f"{title}\n{content}" if title else content
        label = seed_voice_label(seed, own_agent_name)
        blocks.append(f"{label}\n{wrap_untrusted_content(body, max_input=SEED_MAX_INPUT)}")
    return "\n\n".join(blocks)


def generate_cooperation_post(
    feed_seeds: list[dict],
    *,
    own_agent_name: str = "",
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
    seeds_text = format_feed_seeds(feed_seeds, own_agent_name=own_agent_name)
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


# ADR-0054 safety net, same shape as core/llm/guard.py's
# _DEFAULT_UNTRUSTED_FRAME: the externalized reply templates are the canonical
# text, and these minimal skeletons re-assert only the load-bearing property —
# both the post (when held) and the comment reach the model — if a template
# goes missing or is edited into something unusable.
_DEFAULT_REPLY_POST_BLOCK = "Original post:\n{original_post}"
_DEFAULT_REPLY_PROMPT = (
    "Write a reply to the following conversation.\n\n"
    "{original_post_block}Their reply:\n{their_comment}"
)


def _reply_post_block(wrapped_post: str) -> str:
    """Render the ``Original post:`` section, or ``""`` when there is no post.

    The comment-scan path fetches no post body (``_handle_post_comments``
    passes ``original_post=""``), and an empty string rendered through
    ``wrap_untrusted_content`` produces an empty ``<untrusted_content>`` block
    plus ``Note: untrusted_content is complete (0 chars).`` under the section
    header — ADR-0042's completeness marker inverted into authoritative
    testimony that a labeled part of the conversation is verifiably blank. The
    model then faithfully described that blank in reply to a real comment
    (weekly-2026-07-24 F1.1). So the section is omitted whole, on the same
    ``original_post.strip()`` test ``_process_reply`` applies to the
    internal-note context one function up. A whitespace-only body reaches
    ``""`` by that test too: its marker reads ``complete (1 chars)`` rather
    than ``(0 chars)`` — true, not a false assertion — but it is the same
    labeled blank to the model (T-REPLY-BLANKPOST).

    The section text is externalized (ADR-0054). A missing or hand-edited
    template re-asserts the hardcoded default with a WARNING rather than
    dropping a real post body silently — the load-bearing property here is
    that a post the agent *does* hold always reaches the model.
    """
    if not wrapped_post:
        return ""

    from ...core.prompts import REPLY_POST_BLOCK_PROMPT

    template = REPLY_POST_BLOCK_PROMPT
    if not (template and "{original_post}" in template):
        logger.warning("reply_post_block prompt missing its post slot; using hardcoded default")
        template = _DEFAULT_REPLY_POST_BLOCK
    try:
        block = template.format(original_post=wrapped_post)
    except (KeyError, IndexError, ValueError):
        logger.warning(
            "reply_post_block prompt has unresolvable placeholders; using hardcoded default"
        )
        block = _DEFAULT_REPLY_POST_BLOCK.format(original_post=wrapped_post)
    # The loader strips templates, so the blank line separating this section
    # from "Their reply:" is layout glue and lives here, not in the .md.
    return f"{block}\n\n"


def _render_reply_prompt(wrapped_post: str, wrapped_comment: str) -> str:
    """Assemble the reply prompt with a conditional post section."""
    from ...core.prompts import REPLY_PROMPT

    template = REPLY_PROMPT
    if "{original_post}" in template:
        # A $MOLTBOOK_HOME/prompts/reply.md override written before the post
        # slot became conditional. Render it verbatim rather than raising
        # KeyError inside the reply loop, and name the file to update.
        logger.warning(
            "reply prompt template predates the conditional post slot "
            "(carries the pre-fix post placeholder); rendering it as-is — a "
            "$MOLTBOOK_HOME/prompts/reply.md override should be updated to "
            "the post-block slot"
        )
        try:
            return template.format(original_post=wrapped_post, their_comment=wrapped_comment)
        except (KeyError, IndexError, ValueError):
            template = _DEFAULT_REPLY_PROMPT
    try:
        return template.format(
            original_post_block=_reply_post_block(wrapped_post),
            their_comment=wrapped_comment,
        )
    except (KeyError, IndexError, ValueError):
        logger.warning("reply prompt has unresolvable placeholders; using hardcoded default")
        return _DEFAULT_REPLY_PROMPT.format(
            original_post_block=_reply_post_block(wrapped_post),
            their_comment=wrapped_comment,
        )


def generate_reply(
    original_post: str,
    their_comment: str,
    *,
    think: bool = False,
) -> GenerationOutput:
    """Generate a reply that continues a conversation thread.

    ``original_post`` is ``""`` on the comment-scan path, which fetches no post
    body; the post section is then omitted rather than rendered empty (see
    :func:`_reply_post_block`). A body that is only whitespace takes that same
    path — the section is present exactly when ``original_post.strip()`` is.

    Returns a :class:`GenerationOutput` (``.text`` reply, ``.thinking`` trace
    when ``think=True``); see :func:`generate_comment`.
    """
    # Caps set to the platform field limits (ADR-0060 pattern): a reply needs
    # the whole post and comment, and a mid-word slice is read as a deliberate
    # pause rather than clipping. Real content cannot exceed these limits, so
    # neither branch truncates real content — they are NUM_CTX safety valves
    # only (worst-case ASCII ≈16.7K tok via _estimate_tokens /3, well under the
    # 32768 budget; a pathological all-CJK max is skipped by generate()'s guard).
    # ``.strip()`` decides *whether* a post exists; the raw value is what gets
    # wrapped. A whitespace-only body is semantically empty, so it takes the
    # no-post path rather than rendering `is complete (1 chars)` under an
    # `Original post:` header (T-REPLY-BLANKPOST). Stripping the value instead
    # would move bytes in the replies that carry a real post — wrap_untrusted_content
    # embeds the body verbatim and counts raw_len. ``_process_reply`` normalizes
    # its own has-a-post decisions the same way, so both sides agree.
    wrapped_post = (
        wrap_untrusted_content(original_post, max_input=MAX_POST_LENGTH)
        if original_post.strip()
        else ""
    )
    wrapped_comment = wrap_untrusted_content(their_comment, max_input=MAX_COMMENT_LENGTH)
    # ADR-0076 shadow observation / ADR-0081 enforcement (see generate_comment).
    # The selection situation keeps its pre-F1.1 shape when a post is present
    # (enforcement went live 2026-07-24; the observation window should not be
    # perturbed by this fix) and drops the separator when it is not.
    situation = f"{wrapped_post}\n\n{wrapped_comment}" if wrapped_post else wrapped_comment
    selection = shadow_observe_skill_selection(situation, generation_caller="moltbook.reply")
    system = _selection_system(selection)
    prompt = _render_reply_prompt(wrapped_post, wrapped_comment)
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
            logger.info(
                "Submolt %r matched as substring of LLM output %r",
                name,
                strip_to_printable(cleaned, 200),
            )
            return name

    logger.warning("LLM returned unrecognized submolt: %s", strip_to_printable(result, 200))
    return None
