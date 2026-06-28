"""Generate activity reports from JSONL episode logs."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._io import write_restricted

logger = logging.getLogger(__name__)


def _base_entry(entry: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Common per-interaction fields shared by comment / reply / post.

    ``thinking`` is None when the call ran think=False; coerce to "" so the
    renderer's truthiness gate hides the block.
    """
    return {
        "ts": entry.get("ts", ""),
        "post_id": data.get("post_id", ""),
        "content": data.get("content", ""),
        "internal_note": data.get("internal_note", ""),
        "thinking": data.get("thinking") or "",
    }


def _parse_log(
    jsonl_path: Path,
) -> tuple[
    Dict[str, Any],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """Parse a JSONL log file in a single pass.

    Returns (session_meta, comments, replies, posts).
    """
    meta: Dict[str, Any] = {}
    comments: List[Dict[str, Any]] = []
    replies: List[Dict[str, Any]] = []
    posts: List[Dict[str, Any]] = []

    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") == "session" and entry.get("data", {}).get("event") == "start":
            # Merge: keep first-seen values, fill in missing keys from later sessions
            for k, v in entry.get("data", {}).items():
                if k not in meta:
                    meta[k] = v
            continue

        data = entry.get("data", {})
        action = data.get("action", "")

        # Unified per-interaction schema (see _entry_lines). Every action
        # carries the same core fields; type-specific stimulus is normalized
        # into `context`, and dimensions that don't apply are left "".
        if action == "comment":
            comments.append({
                **_base_entry(entry, data),
                "context": data.get("original_post", ""),
                "relevance": data.get("relevance", ""),
                "counterparty": data.get("target_agent", ""),
            })
        elif action == "reply":
            replies.append({
                **_base_entry(entry, data),
                "context": data.get("their_comment", ""),
                "relevance": "",  # replies are notification-driven, not scored
                "counterparty": data.get("target_agent", ""),
            })
        elif action == "post":
            posts.append({
                **_base_entry(entry, data),
                "title": data.get("title", ""),
                "submolt": data.get("submolt", ""),
                "relevance": "",  # self-initiated, no counterparty/relevance
                "counterparty": "",
            })

    return meta, comments, replies, posts


_SAFE_DOMAINS = frozenset({"moltbook.com", "www.moltbook.com"})

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def defang_urls(text: str) -> str:
    """Defang URLs to prevent accidental clicks on external links.

    Transforms ``https://example.com`` → ``hxxps://example[.]com``.
    URLs pointing to safe domains (moltbook.com) are left intact.
    """
    def _defang(match: re.Match[str]) -> str:
        url = match.group(0)
        try:
            # Extract domain (between :// and first /)
            domain = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        except IndexError:
            domain = ""
        if domain in _SAFE_DOMAINS:
            return url
        defanged = url.replace("https://", "hxxps://").replace("http://", "hxxp://")
        defanged = defanged.replace(".", "[.]", 1)
        return defanged

    return _URL_RE.sub(_defang, text)


def _format_ts(ts: str) -> str:
    """Format ISO timestamp to 'YYYY-MM-DD HH:MM:SS'."""
    return ts[:19].replace("T", " ") if ts else ""


def _entry_lines(i: int, kind: str, e: Dict[str, Any]) -> List[str]:
    """Render one interaction in the unified per-entry format.

    The header skeleton is identical across COMMENT / REPLY / POST; a
    dimension that does not apply to a kind renders as ``—`` (relevance for
    replies/posts) or ``self`` (counterparty for posts) rather than changing
    the structure. ``Title`` / ``Submolt`` appear only when present (posts).
    All external text is URL-defanged.
    """
    cp = (e.get("counterparty", "") or "").strip()
    if cp and cp != "unknown":
        counterparty = cp
    else:
        counterparty = "self" if kind == "POST" else "—"
    rel = (e.get("relevance", "") or "").strip()
    post8 = (e.get("post_id", "") or "")[:8]

    lines = [
        f"### {i}. [{_format_ts(e.get('ts', ''))}] {kind} "
        f"· with {counterparty} · post {post8}… · relevance {rel or '—'}",
        "",
    ]
    if e.get("title"):
        lines += [f"**Title:** {e['title']}", ""]
    if e.get("submolt"):
        lines += [f"**Submolt:** {e['submolt']}", ""]
    context = defang_urls(e.get("context", ""))
    if context:
        lines += ["**Context:**", context, ""]
    note = defang_urls(e.get("internal_note", ""))
    if note:
        lines += ["**Internal note:**", note, ""]
    # Reasoning trace (present only when the call ran think=True). Untrusted
    # model output like every other field here — URL-defanged before render.
    thinking = defang_urls(e.get("thinking", ""))
    if thinking:
        lines += ["**Thinking:**", thinking, ""]
    lines += ["**Output:**", defang_urls(e.get("content", "")), "", "---", ""]
    return lines


def _section(heading: str, kind: str, entries: List[Dict[str, Any]]) -> List[str]:
    lines = [f"## {heading} ({len(entries)} total)", ""]
    for i, e in enumerate(entries, 1):
        lines.extend(_entry_lines(i, kind, e))
    return lines


def _summary_section(
    comments: List[Dict[str, Any]],
    replies: List[Dict[str, Any]],
    posts: List[Dict[str, Any]],
) -> List[str]:
    lines = [
        "## Summary",
        f"- Comments: {len(comments)}",
        f"- Replies: {len(replies)}",
        f"- Self posts: {len(posts)}",
    ]
    if comments:
        rels = [float(c["relevance"]) for c in comments if c.get("relevance")]
        if rels:
            lines.append(f"- Relevance range: {min(rels):.2f} - {max(rels):.2f}")
    lines.append("")
    return lines


def _build_report(
    date: str,
    comments: List[Dict[str, Any]],
    replies: List[Dict[str, Any]],
    posts: List[Dict[str, Any]],
    session_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Build Markdown report content."""
    lines: List[str] = [f"# Moltbook Activity Report — {date}", ""]

    if session_meta:
        domain = session_meta.get("domain", "unknown")
        axioms = "enabled" if session_meta.get("axioms_enabled") else "disabled"
        backend = session_meta.get("llm_backend")
        model = session_meta.get("llm_model") or session_meta.get("ollama_model", "unknown")
        if backend:
            model_text = f"{backend}:{model}"
        else:
            model_text = str(model)
        lines.append(
            f"**Configuration**: domain={domain}, axioms={axioms}, model={model_text}"
        )
        lines.append("")

    if comments:
        lines.extend(_section("Comments", "COMMENT", comments))
    if replies:
        lines.extend(_section("Replies", "REPLY", replies))
    if posts:
        lines.extend(_section("Self Posts", "POST", posts))
    lines.extend(_summary_section(comments, replies, posts))

    return "\n".join(lines)


def generate_report(
    log_dir: Path,
    output_dir: Path,
    date: Optional[str] = None,
) -> Optional[Path]:
    """Generate a Markdown activity report from a JSONL episode log.

    Args:
        log_dir: Directory containing JSONL log files.
        output_dir: Directory to write the report to.
        date: Date string (YYYY-MM-DD). Defaults to today (UTC).

    Returns:
        Path to the generated report, or None if no log file exists.
    """
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    jsonl_path = log_dir / f"{date}.jsonl"
    if not jsonl_path.exists():
        logger.info("No log file for %s", date)
        return None

    session_meta, comments, replies, posts = _parse_log(jsonl_path)
    if not comments and not replies and not posts:
        logger.info("No activity entries for %s", date)
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"comment-report-{date}.md"
    write_restricted(
        report_path,
        _build_report(date, comments, replies, posts, session_meta=session_meta),
    )

    logger.info(
        "Report generated: %s (%d comments, %d replies, %d posts)",
        report_path, len(comments), len(replies), len(posts),
    )
    return report_path


def generate_all_reports(log_dir: Path, output_dir: Path) -> List[Path]:
    """Generate reports for all JSONL files in log_dir."""
    generated: List[Path] = []
    for jsonl_file in sorted(log_dir.glob("*.jsonl")):
        date = jsonl_file.stem
        result = generate_report(log_dir, output_dir, date)
        if result:
            generated.append(result)
    return generated
