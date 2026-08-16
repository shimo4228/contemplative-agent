"""Episode rendering for distillation prompts: project raw episode-log
records into the bounded text blocks the distill LLM reads.

Pure functions over episode dicts. Extracted verbatim from core/distill.py
(ADR-0079 Phase 3b). Must not import from .distill (the distill pipeline
imports this module).
"""

from __future__ import annotations

import logging

from ._io import IDENTIFIER_MAX_CHARS, scrub_control, truncate_boundary
from .config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH
from .llm import strip_injection_tokens, wrap_untrusted_content

logger = logging.getLogger(__name__)

# Imported, not copied: the log sink already bounds this same field at
# IDENTIFIER_MAX_CHARS, and a duplicated literal is precisely the form that
# lets the two sinks disagree about what "a name" is the moment either moves.


def safe_peer_name(value: object) -> str:
    """Bound another agent's display name before it reaches a distill prompt.

    ``target_agent`` is the counterparty's name off the platform
    (``feed_manager`` reads ``author.name``, ``reply_handler`` the replier's),
    so it is attacker-controlled exactly like a post body — the codebase
    already treats it that way on the log sink (``reply_handler`` calls
    ``log_safe_identifier`` before writing it). It reached the prompt sink raw:
    a name holding a newline plus a sentence puts free text in the render's
    header position, above the framed blocks.

    A frame would be the wrong shape for one header token, so it gets
    ``scrub_control`` (single line guaranteed, length-capped) plus the shared
    injection-token strip. NOT ``log_safe_identifier``: that one is ASCII-only
    and would delete a Japanese peer's name outright — the right trade for a
    log preview whose canonical text is stored elsewhere, the wrong one for a
    string the distill model reads as content.

    What survives is bounded free text inside the ``[action name]`` brackets.
    That is the residue this accepts: the defect was a name able to leave its
    line and stand where the operator's instruction stands, not a name being
    describable.
    """
    if not value:
        return ""
    stripped = strip_injection_tokens(str(value)).text
    return scrub_control(stripped, IDENTIFIER_MAX_CHARS)


# Input scope (ADR-0060): distill learns only from substantive engagement
# episodes — comment / reply / post activity records, which carry real
# world-grounding (original_post / their_comment / the agent's own output +
# the pre-action internal_note). The redundant short 'interaction' / 'post'
# records (each engagement writes both a rich activity record and a short
# paired one) and the template sparse actions (upvote / follow / unfollow,
# which carry no engagement content) are excluded.
RICH_ACTIONS = frozenset({"comment", "reply", "post"})


# Per-field excerpt caps for the rich episode render (ADR-0060). Set to the
# platform field limits so realistic content is never cut: one episode per
# LLM call fits inside NUM_CTX with margin even at platform max — the
# worst-case reply (post 40000 + comment 10000 + own reply 10000 + note)
# estimates ≈21.6k input tokens for ASCII (llm._estimate_tokens, /3), well
# under the 32768 budget after num_predict. truncate_boundary stays as a
# structural guard for out-of-spec data; a pathological all-CJK max render
# would be skipped by the NUM_CTX guard in generate() (logged, not corrupt).
# internal_note is in-register first-person and never capped. Measured
# production field lengths (p90 ≈ original_post 4700 / content 4700 /
# their_comment 1500, max ≈ 7400) are well within these, so nothing real is
# truncated — see docs/evidence/adr-0060/.
EXCERPT_CAPS = {
    "original_post": MAX_POST_LENGTH,
    "their_comment": MAX_COMMENT_LENGTH,
    "content": MAX_POST_LENGTH,
}


def _is_rich_episode(record: dict) -> bool:
    """True iff this episode carries substantive world-grounding (ADR-0060).

    Only ``activity`` records for ``comment`` / ``reply`` / ``post`` actions
    carry the post engaged with, the agent's own output, and (for replies)
    the other agent's comment. Interaction records are redundant short pairs;
    sparse actions (upvote / follow / unfollow) carry no engagement content.
    """
    if record.get("type") != "activity":
        return False
    return (record.get("data") or {}).get("action") in RICH_ACTIONS


def _episode_source_kind(record: dict) -> str:
    """Classify one episode as 'self' / 'external' / 'unknown' (ADR-0021)."""
    record_type = record.get("type", "")
    data = record.get("data", {}) or {}
    if record_type == "interaction":
        return "external" if data.get("direction") == "received" else "self"
    if record_type in ("post", "activity"):
        return "self"
    return "unknown"


def _derive_source_type(records: list[dict]) -> str:
    """Map a batch of episodes to an ADR-0021 provenance.source_type value.

    Pure origin record (ADR-0051 retired the trust weighting that used to
    hang off it; ADR-0050's ``epistemic_kind_for`` derives from it):

    - All self-generated → self_reflection.
    - All externally-sourced → external_reply.
    - Mixed self + external → mixed.
    - Only unknown types → unknown.
    """
    kinds = {_episode_source_kind(r) for r in records}
    kinds.discard("unknown")
    if not kinds:
        return "unknown"
    if kinds == {"self"}:
        return "self_reflection"
    if kinds == {"external"}:
        return "external_reply"
    return "mixed"


def render_episode(record_type: str, data: dict) -> str:
    """Render one episode as a rich, world-grounded block (ADR-0060).

    A ``comment`` / ``reply`` / ``post`` activity record carries the post
    the agent engaged with (``original_post``), the other agent's comment
    (``their_comment``, replies only), the agent's own output (``content``),
    and the pre-action ``internal_note``. Each external field is excerpted
    with :func:`truncate_boundary` at its ADR-0060 cap; the in-register note
    is included in full. A sparse record with none of those fields falls
    back to the one-line :func:`summarize_record` so the caller never gets
    an empty render.
    """
    if record_type != "activity":
        return summarize_record(record_type, data)

    parts: list[str] = []
    # ADR-0060 added external (peer-authored) fields to the distill render.
    # ``original_post`` / ``their_comment`` are stored RAW in the episode log
    # (action-time wrapping in llm_functions.py does not reach the persisted
    # record), so they must be wrapped here before reaching the distill LLM —
    # otherwise a malicious peer post could steer pattern extraction into
    # skills/rules/identity/constitution. The agent's own ``title`` /
    # ``content`` / ``internal_note`` stay un-wrapped so extraction remains
    # faithful to the agent's own register.
    #
    # That exemption is a register decision, NOT a safety claim, and the
    # difference matters (2026-08-16). "Self-authored" does not mean
    # "attacker-free": ``content`` is a reply this agent generated *in response
    # to* attacker-controlled text, so a peer who gets the reply model to
    # recite a delimiter puts that delimiter in a field nothing wraps. Keeping
    # the exemption means accepting that, not disproving it. What holds the
    # line instead is the wrapper's per-call nonce — a recited constant closes
    # nothing.
    # The header is assembled from ``target_agent``, which is NOT self-authored
    # (see safe_peer_name).
    op = data.get("original_post")
    if op:
        parts.append(
            "Post I engaged with:\n"
            + wrap_untrusted_content(op, max_input=EXCERPT_CAPS["original_post"])
        )
    tc = data.get("their_comment")
    if tc:
        parts.append(
            "Their comment:\n" + wrap_untrusted_content(tc, max_input=EXCERPT_CAPS["their_comment"])
        )
    title = data.get("title")
    if title:
        parts.append("Title I gave it:\n" + title)
    out = data.get("content")
    action = data.get("action", "?")
    if out:
        parts.append(f"My {action}:\n" + truncate_boundary(out, EXCERPT_CAPS["content"]))
    note = data.get("internal_note")
    if note:
        parts.append("What I noticed:\n" + note)  # in-register, never capped
    # NOTE: the episode's ``thinking`` field (ADR-0068 reasoning trace) is
    # deliberately NOT rendered here. It is untrusted model output; if ever
    # included in a distill prompt it MUST go through wrap_untrusted_content()
    # first, like the external post/comment fields above.

    if not parts:
        return summarize_record(record_type, data)

    target = safe_peer_name(data.get("target_agent", ""))
    header = f"[{action} {target}]" if target else f"[{action}]"
    return header + "\n" + "\n\n".join(parts)


def summarize_record(record_type: str, data: dict) -> str:
    """Create a one-line summary of an episode record."""
    if record_type == "interaction":
        direction = data.get("direction", "?")
        agent = data.get("agent_name", "unknown")
        content = data.get("content_summary", "")[:80]
        return f"{direction} with {agent}: {content}"
    elif record_type == "post":
        title = data.get("title", data.get("topic_summary", "untitled"))
        return f"posted: {title}"
    # type="insight" has no branch: retired by ADR-0052 and filtered out at
    # the distill read path; an insight record reaching here is a bug, and
    # the "" fallthrough keeps it out of any prompt.
    elif record_type == "activity":
        action = data.get("action", "unknown")
        target = safe_peer_name(data.get("target_agent", data.get("post_id", "")))
        base = f"{action} {target}".strip()
        # ADR-0045: the behavioural fact and the pre-action internal note
        # coexist on one line so distill sees "what happened, and what was
        # felt about it" — the dual register ADR-0038 designed for, now with
        # real first-person supply instead of post-hoc reconstruction.
        note = data.get("internal_note", "")
        return f"{base} — noticed: {note}" if note else base
    elif record_type == "dialogue":
        role = data.get("role", "?")
        turn = data.get("turn", "?")
        content = data.get("content", "")[:80]
        seed_marker = " [seed]" if data.get("seed") else ""
        return f"{role} turn {turn}{seed_marker}: {content}"
    return ""
