"""Shared scan-fault contract for scripts/ deterministic intakes.

Sibling-imported the same way as `_md.py` (the scripts/ dir is not a package;
`python3 scripts/<name>.py` puts it on sys.path). The `reason= detail` message
shape is part of the pipeline's observability contract — the weekly chain
greps it out of each stage's `*.err` file — so it must not fork per intake.
"""

from __future__ import annotations


class ScanError(Exception):
    """A scan-level fault: the reading is unavailable, not zero."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
