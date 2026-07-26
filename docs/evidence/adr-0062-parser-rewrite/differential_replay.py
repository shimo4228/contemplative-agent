#!/usr/bin/env python3
"""Require the old and new parsers to agree on every challenge in the corpus.

``replay_parser.py`` grades the parser against ground truth — server-accepted
answers, server-rejected answers, manual labels — and so can only judge the
~82% of the corpus that carries a label. That is the right gate for a grammar
*change*.

This is the gate for a behaviour-preserving *refactor*, where ground truth is
not what matters: what matters is that the rewrite decides exactly what the old
code decided. Comparing the two implementations needs no labels, so coverage is
the whole corpus — every unique challenge, including the ones nobody ever
graded.

An abstain (``None``) is a result like any other and must match too. The parser
is fail-closed by design, and the dangerous regression is not "wrong answer
becomes different wrong answer" — it is a case that used to stay silent turning
into a confident wrong answer, which the server records as a rejection.

Usage:
    python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py

Exit 0 only when every challenge agrees. The corpus is local
(``~/.config/moltbook/logs/verification-audit.jsonl``) and not committed, so
this runs on the operator's machine; CI sees only the base64 regression
fixtures embedded in ``tests/test_verification.py``.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

EVIDENCE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE_DIR.parents[2]
AUDIT_LOG = Path.home() / ".config" / "moltbook" / "logs" / "verification-audit.jsonl"
BASELINE = EVIDENCE_DIR / "verification_parse_baseline.py"

_PRINTABLE = re.compile(r"[^\x20-\x7E]")


def _safe(text: str) -> str:
    """Strip non-printable bytes before a challenge reaches the terminal.

    Challenge text is server-controlled and untrusted; printing it raw lets it
    smuggle ANSI escapes into the operator's terminal, and this output is the
    kind of thing a coding agent gets asked to read. Same strip the adapter
    applies before logging server-controlled strings.
    """
    return _PRINTABLE.sub("", text)


def _load_baseline() -> Callable[[str], str | None]:
    """Import the frozen pre-refactor parser from the evidence directory."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    spec = importlib.util.spec_from_file_location("verification_parse_baseline", BASELINE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load baseline parser from {BASELINE}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: with ``from __future__ import annotations`` a
    # frozen dataclass resolves its field types lazily through
    # ``sys.modules[cls.__module__]``, which is None for a module loaded by
    # path alone. The baseline has carried dataclasses since the round-9
    # refresh, so without this the loader dies in dataclasses._is_type.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.code_parse_challenge


def _load_current() -> Callable[[str], str | None]:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from contemplative_agent.adapters.moltbook.verification_parse import code_parse_challenge

    return code_parse_challenge


def _unique_challenges() -> Iterator[str]:
    """Every distinct challenge text in the local audit log, oldest first.

    Records store the challenge base64-encoded and bounded; a truncated one is
    still a valid comparison input — both parsers see the same bytes.
    """
    if not AUDIT_LOG.exists():
        raise SystemExit(
            f"No audit corpus at {AUDIT_LOG}.\n"
            "This gate needs the operator's local verification history; there is "
            "nothing to compare against on a fresh clone."
        )
    seen: set[str] = set()
    with AUDIT_LOG.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            encoded = record.get("challenge_b64")
            if not encoded:
                continue
            try:
                text = base64.b64decode(encoded).decode("utf-8", "replace")
            except Exception:
                continue
            if text and text not in seen:
                seen.add(text)
                yield text


def main() -> int:
    baseline = _load_baseline()
    current = _load_current()

    total = 0
    mismatches: list[tuple[str, str | None, str | None]] = []
    abstains = 0
    for challenge in _unique_challenges():
        total += 1
        try:
            old = baseline(challenge)
        except Exception as exc:  # a raising baseline is itself a difference
            old = f"<raised {type(exc).__name__}>"
        try:
            new = current(challenge)
        except Exception as exc:
            new = f"<raised {type(exc).__name__}>"
        if old is None:
            abstains += 1
        if old != new:
            mismatches.append((challenge, old, new))

    print(f"challenges compared : {total}")
    if not total:
        # A gate that passes on zero inputs certifies nothing. The corpus file
        # existing is not enough — truncation, corruption or a schema change to
        # the challenge_b64 field would all leave it readable but empty.
        print(
            f"\nFAIL: no usable challenges in {AUDIT_LOG}. This gate cannot "
            "certify a refactor it never ran."
        )
        return 1
    print(f"baseline abstains   : {abstains} ({abstains / total:.1%})")
    print(f"mismatches          : {len(mismatches)}")

    for challenge, old, new in mismatches[:20]:
        print("\n--- MISMATCH ---")
        print(f"challenge: {_safe(challenge)[:300]!r}")
        print(f"baseline : {old!r}")
        print(f"current  : {new!r}")
    if len(mismatches) > 20:
        print(f"\n... and {len(mismatches) - 20} more")

    if mismatches:
        print(
            "\nFAIL: the refactor changed behaviour. Reduce a mismatch to a "
            "minimal case and fix it — do not accept a difference as an "
            "improvement here; that is what replay_parser.py is for."
        )
        return 1
    print("\nOK: baseline and current agree on every challenge in the corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
