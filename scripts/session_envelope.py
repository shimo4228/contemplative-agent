#!/usr/bin/env python3
"""Read the exit state of the weekly `claude -p` session from its JSON envelope (P2-02.8).

The session runs with `--output-format json`; the envelope's `result` text is
NOT what this reads (the report itself is the file under reports/.private/).
Only numbers and flags are printed, as `key=value` lines:

  is_error, denials, models, plus the numeric fields evals/judging.py records
  (duration_ms, duration_api_ms, num_turns, total_cost_usd, usage_*)

`denials` is the length of the envelope's `permission_denials` list; when the
CLI does not carry that key it prints `denials=unknown` (never 0 — an absent
key must not read as "nothing was refused"). `models` is the comma list of
`modelUsage` keys, i.e. the model(s) that actually answered.

The numeric key set is a copy of `evals/judging.py::_envelope_numbers`;
tests/test_session_envelope.py asserts the two stay identical (the shared
import path waits on D-P1-06-1).

Exit 0 = parsed, 2 = stdin was not a JSON object. Read-only, stdlib only.
"""

from __future__ import annotations

import json
import re
import sys

NUMBER_KEYS = ("duration_ms", "duration_api_ms", "num_turns", "total_cost_usd")
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def envelope_numbers(envelope: dict) -> dict[str, object]:
    out: dict[str, object] = {k: envelope[k] for k in NUMBER_KEYS if _is_number(envelope.get(k))}
    usage = envelope.get("usage")
    if isinstance(usage, dict):
        for key in USAGE_KEYS:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                out[f"usage_{key}"] = value
    return out


def summarize(envelope: dict) -> dict[str, object]:
    out: dict[str, object] = {"is_error": "true" if envelope.get("is_error") else "false"}
    denials = envelope.get("permission_denials")
    out["denials"] = len(denials) if isinstance(denials, list) else "unknown"
    usage = envelope.get("modelUsage")
    names = sorted(k for k in usage if isinstance(k, str)) if isinstance(usage, dict) else []
    # Model ids go into an audit field read by a shell: keep a conservative alphabet.
    out["models"] = ",".join(re.sub(r"[^A-Za-z0-9._:/\[\]-]", "_", n) for n in names) or "unknown"
    out.update(envelope_numbers(envelope))
    return out


def main() -> int:
    try:
        envelope = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return 2
    if not isinstance(envelope, dict):
        return 2
    for key, value in summarize(envelope).items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
