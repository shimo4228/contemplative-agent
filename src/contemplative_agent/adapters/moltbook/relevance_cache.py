"""Relevance readings remembered across sessions (RFC-0046 S38 / ADR-0113 note 2026-10-04).

The RFC-0032 memo (``FeedManager._judged_posts``) lives one session. A post
the gate drops is never marked commented, so it stays in the feed and was
scored again in every later session: after enforce, 82 of 502 posts were
scored in a median of 9 sessions (max 21), and 6 flipped their gate verdict —
the temperature-0 logprobs read does not reproduce bit-for-bit, and near the
cut a dropped post later passed. The owner's ruling (RFC-0032, restated at the
RFC-0046 face gate 2026-10-04): re-judging the same post is a bug, not an
observation.

**Key.** ``post_id`` + ``content_sha256`` (sha256 of the text the judgment
read — the same digest the record row carries as ``content_sha256``, so an
entry joins to the row that first recorded it) + ``pin_sha256``, a digest of
everything the reading depends on: the decision backend and model when the
``relevance`` face may ask it, ``relevance_score4.md`` (the 4-level
question), and identity + axioms (the domain it reads). Any of them changing
— an identity adopt, a prompt edit, a model swap — misses, and the post is
judged again. :data:`PIN_VERSION` is bumped by hand when the judging *code*
changes what a reading means. Version 2 (RFC-0046 cleanup 2, 2026-10-07): the
feed stopped asking the free-generated score, so the pin no longer names the
generation model or ``relevance.md``, and an entry no longer holds a live
score (:data:`SCHEMA` 2).

**Values, not verdicts.** An entry holds the decision half of the record row
(``decision_p_top`` …), never a threshold or a gate result: the caller cuts
the remembered value at today's threshold (ADR-0112 D1 — the threshold
belongs to the caller), so a threshold change acts on the next sight without
asking a model.

**Only answers.** A reading is remembered when the decision half is
``answered``. Every failure (an abstain, a breaker, no backend for the face)
fails the gate closed and is asked again next time.

**Store.** ``$MOLTBOOK_HOME/relevance_cache.json``: ``{"schema", "entries":
{post_id: entry}}``, one entry per post (a new reading replaces the old),
rewritten whole through ``write_text_atomic`` (0600, temp + replace) after each
new reading. Single writer: only the feed of a ``run`` session writes, under
the run lock. An unreadable or wrongly shaped file is a WARNING and an empty
start (the next write replaces it); a store from a retired schema is an INFO
and an empty start (its entries are judged once more); a malformed entry is
dropped with one WARNING. It holds no external text — ids, digests, numbers —
and is kept out of the public research-data sync.

**Kill switch.** Unconfigured (the default, and what
:func:`reset_relevance_cache` restores) is off: no read, no write, every
session judges every post as before. The CLI points it at the store in every
full-config run.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ...core._io import parse_aware_utc, write_text_atomic
from ...core.llm import (
    DECISION_FACE_RELEVANCE,
    REASON_ANSWERED,
    decision_backend_name,
    decision_face_enabled,
    decision_model_name,
)
from ...core.relevance_state import production_domain_text

logger = logging.getLogger(__name__)

SCHEMA = 2
# Schema 1 entries carried the free-generated live score (RFC-0046 S38); the
# feed no longer reads one, so such a store starts empty without a warning.
_RETIRED_SCHEMAS = frozenset({1})
# Bump when the judging code changes what a remembered reading means (the
# call parameters, the state's frame, the level read) — the prompt, model and
# domain are pinned by digest already.
PIN_VERSION = 2
# Entries older than this (from ``judged_at``) are dropped. A dropped post
# stayed in the feed at most 5.3 days after enforce and 6.5 days over the
# whole log (relevance-*.jsonl 2026-09-25..10-03, judge's re-count for S38),
# so 14 days is ~2x the longest stay seen; a post outliving it is judged once
# more and remembered again. At ~85 new posts a day the store holds ~1,200
# entries (~300 KB). Review-when: a post is seen re-judged after 14 days
# (two rows for one post_id + content_sha256 more than TTL_DAYS apart), or
# the store passes ~1 MB.
TTL_DAYS = 14
_HEX_DIGEST_LEN = 64

_path: Path | None = None
_entries: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class CachedReading:
    """One remembered reading: the values, never a verdict."""

    decision: Mapping[str, Any]
    judged_at: str


def configure_relevance_cache(path: Path | None = None) -> None:
    """Point the cache at its store. ``None`` leaves it off.

    Drops whatever this process held, so the store is read back from disk on
    the next lookup.
    """
    global _path, _entries
    _path = path
    _entries = None


def reset_relevance_cache() -> None:
    global _path, _entries
    _path = None
    _entries = None


def content_sha256(text: str) -> str:
    """The digest ``b64_audit_fields`` writes as the row's ``content_sha256``."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def relevance_pin() -> str | None:
    """Digest of everything the reading depends on, or None (then: no cache).

    Never raises: a pin that cannot be computed (a prompt file that will not
    load) is one WARNING and a miss — the judgment itself goes on.
    """
    if _path is None:
        return None
    try:
        from ...core import prompts

        asks_decision = decision_face_enabled(DECISION_FACE_RELEVANCE)
        pin = {
            "pin_version": PIN_VERSION,
            "domain_sha256": _sha(production_domain_text()),
            "score4_prompt_sha256": _sha(prompts.RELEVANCE_SCORE4_PROMPT),
            "decision_backend": decision_backend_name() if asks_decision else None,
            "decision_model": decision_model_name() if asks_decision else None,
        }
        return _sha(json.dumps(pin, sort_keys=True))
    except Exception as exc:
        logger.warning("relevance cache pin not computed (judging afresh): %s", exc)
        return None


def lookup(post_id: str, content_sha: str, pin: str | None) -> CachedReading | None:
    """The remembered reading for this post, text and pin, or None."""
    if _path is None or pin is None:
        return None
    entry = _loaded().get(post_id)
    if entry is None or entry["content_sha256"] != content_sha or entry["pin_sha256"] != pin:
        return None
    return CachedReading(dict(entry["decision"]), entry["judged_at"])


def remember(
    post_id: str,
    content_sha: str,
    pin: str | None,
    decision: Mapping[str, Any] | None,
) -> bool:
    """Remember one reading if it is an answer; True when it was written.

    *decision* is the decision half of the record row, or None when it was not
    asked (recorder and gate both off) — nothing to remember then. Never
    raises: a failed write is one WARNING and the entry stays in memory for
    this session.
    """
    if _path is None or pin is None or decision is None:
        return False
    if decision.get("decision_reason") != REASON_ANSWERED:
        return False
    entries = _loaded()
    entries[post_id] = {
        "content_sha256": content_sha,
        "pin_sha256": pin,
        "decision": dict(decision),
        "judged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _prune(entries)
    try:
        write_text_atomic(
            _path, json.dumps({"schema": SCHEMA, "entries": entries}, ensure_ascii=False)
        )
    except (OSError, UnicodeError) as exc:
        logger.warning("relevance cache not written (kept in memory this session): %s", exc)
        return False
    return True


def _loaded() -> dict[str, dict[str, Any]]:
    global _entries
    if _entries is None:
        _entries = _load()
    return _entries


def _load() -> dict[str, dict[str, Any]]:
    if _path is None or not _path.exists():
        return {}
    try:
        data = json.loads(_path.read_text(encoding="utf-8"))
    # ValueError covers JSONDecodeError, UnicodeError and an over-long integer
    # literal; RecursionError is a too-deeply nested file. Anything escaping
    # here would leave the store unloaded and fail every feed judgment.
    except (OSError, ValueError, RecursionError) as exc:
        logger.warning("relevance cache unreadable, starting empty: %s", exc)
        return {}
    raw = data.get("entries") if isinstance(data, dict) else None
    if isinstance(data, dict) and data.get("schema") in _RETIRED_SCHEMAS:
        logger.info(
            "relevance cache schema %r is retired (RFC-0046 cleanup 2), starting empty",
            data.get("schema"),
        )
        return {}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(raw, dict):
        logger.warning(
            "relevance cache has an unknown shape (schema %r), starting empty",
            data.get("schema") if isinstance(data, dict) else type(data).__name__,
        )
        return {}
    entries = {pid: entry for pid, entry in raw.items() if _valid(pid, entry)}
    dropped = len(raw) - len(entries)
    if dropped:
        logger.warning("relevance cache: dropped %d malformed entr(ies)", dropped)
    _prune(entries)
    return entries


def _valid(post_id: object, entry: object) -> bool:
    if not isinstance(post_id, str) or not isinstance(entry, dict):
        return False
    decision = entry.get("decision")
    judged_at = entry.get("judged_at")
    if (
        not _is_digest(entry.get("content_sha256"))
        or not _is_digest(entry.get("pin_sha256"))
        or not isinstance(decision, dict)
        or not isinstance(decision.get("decision_reason"), str)
        or not isinstance(judged_at, str)
    ):
        return False
    try:
        parse_aware_utc(judged_at)
    except ValueError:
        return False
    return True


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == _HEX_DIGEST_LEN


def _prune(entries: dict[str, dict[str, Any]]) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)
    for post_id in [
        pid for pid, entry in entries.items() if parse_aware_utc(entry["judged_at"]) < cutoff
    ]:
        del entries[post_id]
