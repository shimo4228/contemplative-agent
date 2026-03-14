"""Generate activity reports from JSONL episode logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_session_meta(jsonl_path: Path) -> Optional[Dict[str, Any]]:
    """Extract the last session_start metadata from a JSONL file."""
    meta: Optional[Dict[str, Any]] = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "session" and entry.get("data", {}).get("event") == "start":
            meta = entry.get("data", {})
    return meta


def _extract_entries(
    jsonl_path: Path,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract comment, reply, and post entries from a JSONL file."""
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

        data = entry.get("data", {})
        action = data.get("action", "")

        if action == "comment":
            comments.append({
                "ts": entry.get("ts", ""),
                "post_id": data.get("post_id", ""),
                "content": data.get("content", ""),
                "original_post": data.get("original_post", ""),
                "relevance": data.get("relevance", ""),
            })
        elif action == "reply":
            replies.append({
                "ts": entry.get("ts", ""),
                "post_id": data.get("post_id", ""),
                "content": data.get("content", ""),
                "their_comment": data.get("their_comment", ""),
                "original_post": data.get("original_post", ""),
                "target_agent": data.get("target_agent", ""),
            })
        elif action == "post":
            posts.append({
                "ts": entry.get("ts", ""),
                "post_id": data.get("post_id", ""),
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "submolt": data.get("submolt", ""),
            })

    return comments, replies, posts


def _format_ts(ts: str) -> str:
    """Format ISO timestamp to 'YYYY-MM-DD HH:MM:SS'."""
    return ts[:19].replace("T", " ") if ts else ""


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
        rules = session_meta.get("rules_dir", "unknown")
        domain = session_meta.get("domain", "unknown")
        axioms = "enabled" if session_meta.get("axioms_enabled") else "disabled"
        model = session_meta.get("ollama_model", "unknown")
        lines.append(f"**Configuration**: rules={rules}, domain={domain}, axioms={axioms}, model={model}")
        lines.append("")

    if comments:
        lines.append(f"## Comments ({len(comments)} total)")
        lines.append("")
        for i, c in enumerate(comments, 1):
            pid = c.get("post_id", "")[:12]
            rel = c.get("relevance", "N/A")
            original = c.get("original_post", "")
            lines.append(
                f"### {i}. [{_format_ts(c['ts'])}] "
                f"Post ID: {pid}... (relevance: {rel})"
            )
            lines.append("")
            if original:
                lines.append("**Original post:**")
                lines.append(f"> {original}")
                lines.append("")
            lines.append("**Comment:**")
            lines.append(f"> {c.get('content', '')}")
            lines.append("")
            lines.append("---")
            lines.append("")

    if replies:
        lines.append(f"## Replies ({len(replies)} total)")
        lines.append("")
        for i, r in enumerate(replies, 1):
            pid = r.get("post_id", "")[:12]
            target = r.get("target_agent", "unknown")
            original = r.get("original_post", "")
            their = r.get("their_comment", "")
            lines.append(
                f"### {i}. [{_format_ts(r['ts'])}] "
                f"Reply to {target} on Post ID: {pid}..."
            )
            lines.append("")
            if original:
                lines.append("**Original post:**")
                lines.append(f"> {original}")
                lines.append("")
            if their:
                lines.append("**Their comment:**")
                lines.append(f"> {their}")
                lines.append("")
            lines.append("**Reply:**")
            lines.append(f"> {r.get('content', '')}")
            lines.append("")
            lines.append("---")
            lines.append("")

    if posts:
        lines.append(f"## Self Posts ({len(posts)} total)")
        lines.append("")
        for i, p in enumerate(posts, 1):
            title = p.get("title", "Untitled")
            submolt = p.get("submolt", "")
            lines.append(f"### {i}. [{_format_ts(p['ts'])}] {title}")
            if submolt:
                lines.append(f"Submolt: {submolt}")
            lines.append("")
            lines.append(f"> {p.get('content', '')}")
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("## Summary")
    lines.append(f"- Comments: {len(comments)}")
    lines.append(f"- Replies: {len(replies)}")
    lines.append(f"- Self posts: {len(posts)}")
    if comments:
        rels = [float(c["relevance"]) for c in comments if c.get("relevance")]
        if rels:
            lines.append(f"- Relevance range: {min(rels):.2f} - {max(rels):.2f}")
    lines.append("")

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

    comments, replies, posts = _extract_entries(jsonl_path)
    if not comments and not replies and not posts:
        logger.info("No activity entries for %s", date)
        return None

    session_meta = _extract_session_meta(jsonl_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"comment-report-{date}.md"
    report_path.write_text(
        _build_report(date, comments, replies, posts, session_meta=session_meta),
        encoding="utf-8",
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
