"""Shared Markdown-neutralizer for scripts/ LLM-facing reports."""
from __future__ import annotations


def md_safe(s: str) -> str:
    """Neutralize Markdown table/code-span breakers before LLM-facing output.

    A backtick would close a code span early; a pipe would misparse a table
    cell. Shared by state_invariant_check and log_anomaly_sweep, whose reports
    are both fed to an LLM downstream.
    """
    return s.replace("|", "\\|").replace("`", "'")
