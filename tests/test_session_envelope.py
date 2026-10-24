"""session_envelope.py (P2-02.8): numbers and flags from the weekly session's JSON envelope."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import session_envelope as se  # noqa: E402

from evals import judging  # noqa: E402


def test_the_numeric_key_set_is_the_one_evals_records():
    """Copy-plus-parity until D-P1-06-1 settles a shared import path."""
    assert se.NUMBER_KEYS == judging._ENVELOPE_NUMBER_KEYS
    assert se.USAGE_KEYS == judging._ENVELOPE_USAGE_KEYS
    sample = {
        "duration_ms": 5, "duration_api_ms": 4, "num_turns": 2, "total_cost_usd": 0.1,
        "result": "text", "usage": {"input_tokens": 1, "output_tokens": 2, "other": 9},
    }
    assert se.envelope_numbers(sample) == judging._envelope_numbers(sample)


def test_summary_never_carries_the_result_text_and_unknown_is_not_zero():
    out = se.summarize({"is_error": False, "result": "SECRET", "num_turns": 3})
    assert "SECRET" not in repr(out)
    assert out["denials"] == "unknown" and out["models"] == "unknown" and out["is_error"] == "false"
    assert se.summarize({"permission_denials": [1, 2]})["denials"] == 2
