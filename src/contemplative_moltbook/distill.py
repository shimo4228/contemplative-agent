"""Distill — backward-compatible re-export shim."""

from .core.distill import *  # noqa: F401,F403
from .core.distill import (  # noqa: F401
    _evaluate_pattern,
    _format_numbered_knowledge,
    _parse_eval_verdict,
    _summarize_record,
)
