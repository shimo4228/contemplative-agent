"""Shared scan-fault contract for scripts/ deterministic intakes.

Sibling-imported the same way as `_md.py` (the scripts/ dir is not a package;
`python3 scripts/<name>.py` puts it on sys.path). The `reason= detail` message
shape must not fork per intake: it is pinned by each instrument's stderr test
and is what the Saturday gate reads out of the run-log `$RUN_LOG_DIR/<stage>.err`
when a stage abstains. The chain itself branches only on exit status and the
JSON stdout artifact — nothing machine-reads the `*.err` files.
"""

from __future__ import annotations


class ScanError(Exception):
    """A scan-level fault: the reading is unavailable, not zero."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
