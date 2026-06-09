"""Dialogue peer loop — one side of a local 2-agent dialogue.

Reads peer messages from an input stream, generates replies via the configured
LLM, writes replies to an output stream, and appends each exchange to the
home's episode log under record type ``dialogue``.

Streams are JSON line-delimited. Each line is one of:
  - ``{"turn": N, "content": "..."}`` — a message
  - ``{"type": "stop"}`` — graceful shutdown signal

Turn counting: a peer stops after generating ``max_turns`` replies (the seed
sent by the initiator does not count as a reply — it is the opening move).
"""

from __future__ import annotations

import functools
import json
import logging
import sys
from typing import Optional, TextIO

from ...core.episode_log import EpisodeLog
from ...core.llm import generate, wrap_untrusted_content

logger = logging.getLogger(__name__)

# Code-side fallback. The canonical text lives in config/prompts/dialogue.md
# (ADR-0054) and is loaded at use; this default preserves behavior if that
# template is missing or gutted of its placeholders.
_DEFAULT_DIALOGUE_PROMPT = """\
You are in an ongoing dialogue with another agent. Reply briefly (1-3 sentences), staying true to your identity and values.

{history_section}The other agent just said:
{peer_message}
"""

_HISTORY_LIMIT = 5
_NUM_PREDICT = 300
_MAX_LINE_BYTES = 16 * 1024  # cap peer input to defend against a hostile sender


def _build_history_section(history: list[str]) -> str:
    if not history:
        return ""
    recent = history[-_HISTORY_LIMIT:]
    lines = "\n".join(f"- {h}" for h in recent)
    return f"Previous exchanges:\n{lines}\n\n"


def _write_json_line(stream: TextIO, payload: dict) -> bool:
    """Write one JSON line to ``stream``. Returns False if the peer closed the pipe."""
    try:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()
        return True
    except (BrokenPipeError, OSError):
        return False


def _log_stderr(label: str, turn: int, role: str, content: str) -> None:
    """Emit a human-readable trace of each exchange to stderr."""
    snippet = content.replace("\n", " ")[:200]
    print(f"[{label}] turn {turn} {role}: {snippet}", file=sys.stderr, flush=True)


def _resolve_template() -> str:
    """Resolve the dialogue template once.

    The externalized config/prompts/dialogue.md (ADR-0054) is loaded here,
    falling back to the hardcoded default if it is missing or lacks the
    required placeholders.
    """
    from ...core.prompts import DIALOGUE_PROMPT

    template = DIALOGUE_PROMPT
    if not (
        template
        and "{peer_message}" in template
        and "{history_section}" in template
    ):
        template = _DEFAULT_DIALOGUE_PROMPT
    return template


def _parse_peer_line(line: str) -> Optional[dict]:
    """Parse one raw line into a peer message dict; None to skip."""
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("malformed JSON line from peer, skipping: %r", line[:80])
        return None
    if not isinstance(msg, dict):
        return None
    return msg


def _render_reply_prompt(template: str, history: list, peer_content: str) -> str:
    """Format the reply prompt, falling back to the default template."""
    wrapped = wrap_untrusted_content(peer_content)
    try:
        return template.format(
            history_section=_build_history_section(history),
            peer_message=wrapped,
        )
    except (KeyError, IndexError, ValueError):
        return _DEFAULT_DIALOGUE_PROMPT.format(
            history_section=_build_history_section(history),
            peer_message=wrapped,
        )


def run_peer_loop(
    *,
    episode_log: EpisodeLog,
    peer_in: TextIO,
    peer_out: TextIO,
    max_turns: int,
    seed: Optional[str] = None,
    label: str = "peer",
    generate_fn=functools.partial(generate, caller="dialogue.peer"),
) -> int:
    """Run one peer's dialogue loop. Returns the number of replies generated.

    The ``generate_fn`` indirection exists for tests — production callers use
    the default (``core.llm.generate`` with the telemetry caller label
    pre-bound; the 2-argument call protocol is unchanged).
    """
    history: list[str] = []
    replies_generated = 0

    if seed is not None:
        if not _write_json_line(peer_out, {"turn": 0, "content": seed}):
            return 0
        episode_log.append(
            "dialogue", {"role": "self", "turn": 0, "content": seed, "seed": True},
        )
        history.append(f"self: {seed}")
        _log_stderr(label, 0, "self(seed)", seed)

    template = _resolve_template()

    while replies_generated < max_turns:
        line = peer_in.readline(_MAX_LINE_BYTES)
        if not line:
            break  # EOF — peer closed its end

        msg = _parse_peer_line(line)
        if msg is None:
            continue
        if msg.get("type") == "stop":
            break

        peer_content = msg.get("content")
        peer_turn = msg.get("turn", replies_generated + 1)
        if not isinstance(peer_content, str) or not peer_content:
            continue

        episode_log.append(
            "dialogue",
            {"role": "peer", "turn": peer_turn, "content": peer_content},
        )
        history.append(f"peer: {peer_content}")
        _log_stderr(label, peer_turn, "peer", peer_content)

        prompt = _render_reply_prompt(template, history, peer_content)
        reply = generate_fn(prompt, num_predict=_NUM_PREDICT)
        if reply is None:
            reply = "(no reply)"

        replies_generated += 1
        episode_log.append(
            "dialogue", {"role": "self", "turn": replies_generated, "content": reply},
        )
        history.append(f"self: {reply}")
        _log_stderr(label, replies_generated, "self", reply)

        if not _write_json_line(peer_out, {"turn": replies_generated, "content": reply}):
            break  # peer closed its end — we are done

    _write_json_line(peer_out, {"type": "stop"})
    return replies_generated
