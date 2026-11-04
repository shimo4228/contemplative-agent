#!/usr/bin/env python3
"""One-shot measurement: have gemma write a revised body for 5 `revise` proposals.

RFC-0066 (packet S49). ONE-OFF: run once on 2026-11-04, outputs frozen under
``docs/evidence/rfc-0066/``; not part of any pipeline and not re-run. Launch with
``uv run --no-sync python scripts/rfc0066_revise_text_once.py``.

What it answers: if the insight body call were widened from ``new`` to
``new`` + ``revise`` (ADR-0111 option B), would the revised bodies be usable?
The owner judges the 5 outputs at the Saturday gate against the criteria fixed
in RFC-0066 before generation. No LLM judge.

Sample (fixed here, RFC-0066 判定基準): the frozen revise table
(``docs/evidence/adr-0111/revise-table-2026-10-24.md``, 21 rows) is the frame.
Rows are walked newest date first, table order breaking ties; a row is taken
when its target skill is not yet taken and exists in ``$MOLTBOOK_HOME/skills/``
(matched by frontmatter ``name``). Newest first, because the newest proposal for
a target is the one written against the store as it stands, and the 5 target
bodies are checked to be unmodified since their proposal date.

Input per item: the table row is joined to its record in
``logs/insight-stages.jsonl`` (date + target + reason prefix, exactly one
match) for the full ``change_reason``, ``topic`` and ``evidence_ids``; the ids
resolve to pattern text in ``knowledge.json`` through
``knowledge_store.pattern_id``. The naming prompt's base64 field is NOT
decoded, so the input is the observations the naming stage cited, not the
whole cluster batch the production body call would see.

Call shape mirrors the production body call (``insight._write_body``): the
distill system prompt, ``think=True``, ``num_predict=3000``,
``drop_truncated=True``, the ``generate_full`` default temperature, one call
per item, no retry. The prompt is ``docs/evidence/rfc-0066/revise-prompt.md``
(the extraction prompt's body instructions plus the existing skill and the
change reason).

Read-only with respect to ``$MOLTBOOK_HOME``. ``llm.configure`` is never called,
so no telemetry or audit sink is wired. Refuses to run within 60 minutes of the
JST 0/6/12/18 scheduled sessions or when the generation model is not
gemma4:e4b. That no other model is loaded is checked by hand (``ollama ps``)
before the run: the script holds no HTTP client of its own, so it stays out of
the pinned I/O module set (``tests/test_io_surface_allowlist.py``).

Edited after the 2026-11-04 run to pass the repo gates, generation path
unchanged: the ``/api/ps`` + ``/api/tags`` requests became the manifest-file
digest below (same value, c6eb396dbd59…), and the decline test is a local copy
of ``insight._is_abstain_verdict`` (a private name, which
``tests/test_architecture.py`` keeps out of scripts) behind production's
title-first check. All 5 outputs were ``revised`` either way.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from contemplative_agent.core import llm  # noqa: E402
from contemplative_agent.core.insight import MAX_BODY_CHARS  # noqa: E402
from contemplative_agent.core.knowledge_store import pattern_id  # noqa: E402
from contemplative_agent.core.text_utils import extract_title  # noqa: E402

MODEL = "gemma4:e4b"
# Ollama's model digest is the sha256 of this manifest file.
MANIFEST = Path.home() / ".ollama/models/manifests/registry.ollama.ai/library/gemma4/e4b"
ABSTAIN_TOKEN = "NOTHING-PROMOTABLE"
N_ITEMS = 5
JST = timezone(timedelta(hours=9))
SESSION_HOURS_JST = (0, 6, 12, 18)
EVIDENCE_DIR = _REPO_ROOT / "docs" / "evidence" / "rfc-0066"
TABLE = _REPO_ROOT / "docs" / "evidence" / "adr-0111" / "revise-table-2026-10-24.md"
PROMPT_TEMPLATE = EVIDENCE_DIR / "revise-prompt.md"
OUT_JSON = EVIDENCE_DIR / "revise-text-2026-11-04.json"
OUT_MD = EVIDENCE_DIR / "README.md"

Row = tuple[int, str, str, str]
_ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \| ([^|]+?) \| (.+) \|$")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_window(now: datetime) -> None:
    for hour in SESSION_HOURS_JST:
        for day in (-1, 0, 1):
            session = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(
                days=day
            )
            if abs((now - session).total_seconds()) < 3600:
                sys.exit(f"refuse: {now:%H:%M} JST is within 60 min of the {hour:02d}:00 session")


def check_model() -> str:
    """Generation model is gemma4:e4b; return its Ollama digest."""
    if llm.ollama_model() != MODEL:
        sys.exit(f"refuse: generation model is {llm.ollama_model()}, not {MODEL}")
    return hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def is_decline(text: str) -> bool:
    """Production's decline test: no title, and a line that is the token."""
    if extract_title(text) is not None:
        return False
    for line in text.splitlines():
        if line.strip().strip("`*_#> ").strip().upper().rstrip(".:") == ABSTAIN_TOKEN:
            return True
    return False


def read_table() -> list[Row]:
    """(table order, date, target, reason clipped to 120 with the ellipsis removed)."""
    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m and m.group(1) != "date":
            rows.append((len(rows), m.group(1), m.group(2).strip(), m.group(3).rstrip("…")))
    if len(rows) != 21:
        sys.exit(f"premise: revise table has {len(rows)} rows, expected 21")
    return rows


def skill_files(home: Path) -> dict[str, Path]:
    by_name: dict[str, Path] = {}
    for path in sorted((home / "skills").glob("*.md")):
        m = re.search(r"^name:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            by_name[m.group(1)] = path
    return by_name


def select(rows: list[Row], skills: dict[str, Path]) -> tuple[list[Row], list[str]]:
    taken: set[str] = set()
    skipped: list[str] = []
    chosen: list[Row] = []
    for row in sorted(rows, key=lambda r: (r[1], -r[0]), reverse=True):
        _, _, target, _ = row
        if target in taken:
            continue
        if target not in skills:
            skipped.append(target)
            continue
        taken.add(target)
        chosen.append(row)
        if len(chosen) == N_ITEMS:
            break
    return chosen, skipped


def join_log(row: Row, log_rows: list[dict]) -> dict:
    _, date, target, reason = row
    hits = [
        r
        for r in log_rows
        if r.get("verdict") == "revise"
        and r.get("ts", "")[:10] == date
        and r.get("target_skill") == target
        and (r.get("change_reason") or "").startswith(reason)
    ]
    if len(hits) != 1:
        sys.exit(f"premise: {date} {target} matched {len(hits)} log rows, expected 1")
    return hits[0]


def main() -> None:
    now = datetime.now(JST)
    check_window(now)
    digest = check_model()
    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    log_rows = [
        json.loads(line)
        for line in (home / "logs" / "insight-stages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    patterns = {
        pattern_id(p): p for p in json.loads((home / "knowledge.json").read_text(encoding="utf-8"))
    }
    skills = skill_files(home)
    chosen, skipped = select(read_table(), skills)
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    system = llm.get_distill_system_prompt()

    items = []
    for row in chosen:
        _, date, target, _ = row
        rec = join_log(row, log_rows)
        skill_path = skills[target]
        mtime = datetime.fromtimestamp(skill_path.stat().st_mtime, JST)
        if mtime.date().isoformat() > date:
            sys.exit(
                f"premise: {skill_path.name} modified {mtime:%Y-%m-%d}, after the {date} proposal"
            )
        existing = skill_path.read_text(encoding="utf-8")
        missing = [i for i in rec["evidence_ids"] if i not in patterns]
        if missing:
            sys.exit(f"premise: {target} evidence ids not in knowledge.json: {missing}")
        evidence = [patterns[i]["pattern"] for i in rec["evidence_ids"]]
        prompt = template.format(
            subcategory=rec["topic"],
            existing_skill=existing.strip(),
            change_reason=rec["change_reason"],
            patterns="\n".join(f"- {p}" for p in evidence),
        )
        started = time.monotonic()
        out = llm.generate_full(
            prompt,
            system=system,
            num_predict=3000,
            caller="rfc0066.revise_once",
            think=True,
            drop_truncated=True,
        )
        seconds = round(time.monotonic() - started, 1)
        text = None if out is None or out.text is None else out.text.strip()
        if text is None:
            outcome = "llm_none"
        elif is_decline(text):
            outcome = "declined"
        elif not text or len(text) > MAX_BODY_CHARS:
            outcome = "body_invalid"
        else:
            outcome = "revised"
        print(f"{target}: {outcome} ({seconds}s, {len(text or '')} chars)", flush=True)
        items.append(
            {
                "table_date": date,
                "target_skill": target,
                "skill_file": skill_path.name,
                "skill_mtime": mtime.isoformat(timespec="seconds"),
                "existing_sha256": sha256(existing),
                "existing_text": existing,
                "topic": rec["topic"],
                "naming_ts": rec["ts"],
                "naming_run_id": rec.get("run_id"),
                "change_reason": rec["change_reason"],
                "evidence_ids": rec["evidence_ids"],
                "evidence_patterns": evidence,
                "prompt_sha256": sha256(prompt),
                "outcome": outcome,
                "revised_body": text,
                "thinking": None if out is None else out.thinking,
                "seconds": seconds,
                "judgment": None,
            }
        )

    record = {
        "generated_at": now.isoformat(timespec="seconds"),
        "model": MODEL,
        "model_digest": digest,
        "call": {
            "system": "llm.get_distill_system_prompt()",
            "system_sha256": sha256(system),
            "think": True,
            "num_predict": 3000,
            "temperature": 1.0,
            "drop_truncated": True,
            "retries": 0,
        },
        "prompt_template": PROMPT_TEMPLATE.name,
        "prompt_template_sha256": sha256(template),
        "frame": TABLE.relative_to(_REPO_ROOT).as_posix(),
        "selection": "newest table date first, table order breaks ties; one row per target; target must exist in skills/",
        "skipped_targets_absent": skipped,
        "items": items,
    }
    OUT_JSON.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(record), encoding="utf-8")
    print(f"wrote {OUT_JSON.relative_to(_REPO_ROOT)} and {OUT_MD.relative_to(_REPO_ROOT)}")


def render_md(record: dict) -> str:
    lines = [
        "# RFC-0066 — revise 提案の改訂本文（2026-11-04、一回限り）",
        "",
        f"生成: `{record['model']}` digest `{record['model_digest']}`、本番の body call と同じ形"
        f"（distill system prompt、think-ON、num_predict 3000、temperature 1.0、1 件 1 回・再試行なし）。"
        f"プロンプトは [`{record['prompt_template']}`]({record['prompt_template']})"
        f"（sha256 `{record['prompt_template_sha256'][:12]}`）、生成 script は "
        "[`scripts/rfc0066_revise_text_once.py`](../../../scripts/rfc0066_revise_text_once.py)、"
        "全欄（thinking trace を含む）は "
        "[`revise-text-2026-11-04.json`](revise-text-2026-11-04.json)。",
        "",
        "標本: 凍結済みの revise 表（21 行）を新しい日付から順に見て、異なる target skill を 5 件。"
        "入力は既存 skill の全文・naming 段の change reason 全文・naming 段が引いた観察（evidence_ids）だけ"
        "（cluster 全体ではない）。",
        "",
        "判定基準は [RFC-0066](../../../rfcs/0066-revise-text-one-shot-measurement.md) の"
        "「判定基準（2026-11-04、読みの前）」節。判定欄はオーナーが土曜ゲートで埋める。",
        "",
        "| # | target skill | 提案日 | 生成結果 | 使える |",
        "|---|---|---|---|---|",
    ]
    for n, it in enumerate(record["items"], 1):
        lines.append(f"| {n} | `{it['target_skill']}` | {it['table_date']} | {it['outcome']} | |")
    lines += ["", "判定: 5 件中 ___ 件が「使える」 → ___", ""]
    for n, it in enumerate(record["items"], 1):
        lines += [
            "---",
            "",
            f"## {n}. `{it['target_skill']}`",
            "",
            f"- 既存 file: `{it['skill_file']}`（sha256 `{it['existing_sha256'][:12]}`）",
            f"- 提案: {it['table_date']}（{it['topic']}）、prompt sha256 `{it['prompt_sha256'][:12]}`",
            "",
            f"**Change reason**: {it['change_reason']}",
            "",
            "### 既存",
            "",
            "````markdown",
            it["existing_text"].strip(),
            "````",
            "",
            "### 改訂本文（gemma4:e4b）",
            "",
            "````markdown",
            it["revised_body"] or f"(none: {it['outcome']})",
            "````",
            "",
            "<details><summary>入力した観察（naming 段の evidence_ids）</summary>",
            "",
        ]
        lines += [
            f"- `{i}` {p}" for i, p in zip(it["evidence_ids"], it["evidence_patterns"], strict=True)
        ]
        lines += [
            "",
            "</details>",
            "",
            "**判定**（オーナー）: (1) trigger を壊さない ___ (2) change reason が本文にある ___ "
            "(3) そのまま採用してよい ___ → 使える ___",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
