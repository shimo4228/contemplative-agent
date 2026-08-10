#!/usr/bin/env python3
"""Assemble the Saturday decision packet from the unattended weekly chain.

Deterministic by design (when-code-when-llm): every count the human reads in
the packet — patches ready, prompt diffs, insight items — is computed here
from the audit log and the files on disk, never asserted by an LLM. The LLM
stages write prose; this script decides what enters the gate and how.

Inclusion rules follow human-gate.md:
- prompt-scope diffs and pipeline-improvement diffs are inlined FULL TEXT
  (summarising a behavior-shaping diff can hide a gate-weakening change)
- code patches are listed as a table with reviewer verdicts; the diff bodies
  stay on disk for the gate session to apply
- the inventory enumerates counts and scope up front (1 作業 1 ゲート)

Fail-forward: a missing upstream artifact (diagnosis output, insight review)
becomes a reason code in the packet, never a crash — a packet that names what
died is the difference between "chain degraded" and "chain never ran" (the
latter is the watchdog's finding, not ours).

Subcommands:
  build              assemble packet + append the phase:"auto" metrics record
  check-improvement  P4-shaped trigger: same reason code in the last two
                     consecutive auto records → the chain may draft a
                     pipeline-improvement diff (full-text gated)
  gate-record        append the phase:"gate" metrics record (called by the
                     /weekly-gate skill after the human decides)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DIAGNOSIS_UNAVAILABLE = "DIAGNOSIS_UNAVAILABLE"
INSIGHT_REVIEW_UNAVAILABLE = "INSIGHT_REVIEW_UNAVAILABLE"
# Recomputed here from the `scope_escalation` event type rather than read from
# the shell's REASONS variable — the builder replays the audit log
# independently, so a missing `add_reason` upstream still reaches the human.
SCOPE_ESCALATED = "SCOPE_ESCALATED"
# Escalation seen only in the patch's export location, not in an audit event:
# the escalation still reaches the human, and the audit gap is named instead
# of being folded into an ordinary SCOPE_ESCALATED.
SCOPE_ESCALATED_INFERRED = "SCOPE_ESCALATED_INFERRED"
# Codes that report a guard working as designed, not a fault. Recording
# SCOPE_ESCALATED (2026-08-08) put it on the recurrence-comparison side for the
# first time: two consecutive weeks with a docs-touching fix — routine — would
# otherwise spend an unattended session drafting a "pipeline improvement" for a
# guard the packet's own §3 text calls deliberate. SCOPE_ESCALATED_INFERRED is
# deliberately NOT here: a recurring audit-log gap IS a fault worth improving.
# IDENTITY_STAGING_BUSY / IDENTITY_INSIGHT_PENDING recur by design on every
# week the insight batch holds the ADR-0074 staging slot (observed: every
# Saturday since 2026-07-18) — counting them would burn a weekly unattended
# improve session on a working guard, the exact failure this set exists for
# (code review 2026-08-10 HIGH).
DESIGNED_OUTCOME_CODES = frozenset(
    {SCOPE_ESCALATED, "IDENTITY_STAGING_BUSY", "IDENTITY_INSIGHT_PENDING"}
)

# §8 renders the instrument's `reason` fields as narration; they are literal
# enums upstream, but the builder does not trust the file — off-contract
# values get the same UNRECOGNIZED(...) treatment as review verdicts
# (2026-08-10 security review L3).
KNOWN_VALUE_LAYER_REASONS = frozenset(
    {
        "INTERVAL_ELAPSED",
        "NOT_DUE",
        "NO_PRIOR_RUN",
        "NO_PRIOR_ADOPTION",
        "NO_AUDIT_RECORDS",
        "UNPARSABLE_HISTORY",
        "FUTURE_TIMESTAMP",
    }
)

# The insight-recommendation prompt's machine contract: one section heading
# per candidate, `## <n>. <name> — RECOMMEND: adopt|reject`.
_RECOMMEND_HEADING = re.compile(r"^## .+ RECOMMEND: (adopt|reject)\s*$", re.MULTILINE)


def _fence(body: str, info: str = "") -> tuple[str, str]:
    """A code-fence pair guaranteed not to collide with ``body``.

    Review bodies are free-form LLM prose that routinely quotes code in its
    own ``` fences; a hardcoded three-backtick fence would close early and
    spill the rest of the body into the packet's raw Markdown (2026-08-01
    python review, HIGH). The fence is one backtick longer than the longest
    backtick run in the body (minimum three).
    """
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    marks = "`" * max(3, longest + 1)
    return f"{marks}{info}", marks


def _cell(value: object) -> str:
    """Flatten an audit-log value into one Markdown table cell / note line.

    The structural floor, applied to every audit-derived value. Most of them
    are tightly constrained upstream (``fix_id`` is regex-pinned in
    parse_findings.py, ``scope`` is an enum, ``result``/``attempts``/``patch``
    are shell-constructed), so this is defence in depth for them. The two that
    are NOT constrained get a stricter renderer of their own: ``_path_tokens``
    for escalation paths (fix-session filenames) and ``_unrecognized_verdict``
    for reviewer verdicts (a raw line from the review session's output).

    Safe **mid-line only**: a leading `#` and backtick runs are not
    neutralised, so a caller emitting ``f"{_cell(v)}"`` at the start of a line
    reopens the hole. Lists are joined rather than repr'd — the shell
    space-joins today, but the builder must not depend on that.
    """
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    # splitlines(), not replace("\n"): it is the splitter every consumer of
    # this packet uses, and it also breaks on \v \f \x1c-\x1e \x85
    #   — a code/test that disagreed on the line-break alphabet would
    # assert a stronger invariant than the code holds. Backslash first, so
    # escaping `|` cannot be undone by a preceding literal backslash.
    flat = " ".join(str(value).splitlines())
    return flat.replace("\\", "\\\\").replace("|", "\\|")


def _patch_name(fix_id: str) -> str:
    """The exporter's fix_id → patch filename contract (weekly-pipeline.sh)."""
    return f"{fix_id.replace('/', '_')}.patch"


# The reviewer contract (weekly-pipeline.sh): APPROVE ends the loop, CONCERNS
# drives one re-entry, REVIEW_FAIL is the shell's own fallback when no
# `^VERDICT:` line was found. Anything else means the review session broke
# contract, which is a reportable fault rather than a value to render as-is.
KNOWN_VERDICTS = ("APPROVE", "CONCERNS", "REVIEW_FAIL")
REVIEW_VERDICT_UNRECOGNIZED = "REVIEW_VERDICT_UNRECOGNIZED"

_PATH_UNSAFE = re.compile(r"[^A-Za-z0-9._/+-]")
_PATH_REPLACEMENT = "�"
_MAX_PATH_TOKENS = 20
_MAX_PATH_LEN = 120


def _unrecognized_verdict(raw: str) -> str:
    """Render an off-contract reviewer verdict without carrying its markup."""
    if not raw:
        return "—"
    return f"UNRECOGNIZED(`{_PATH_UNSAFE.sub(_PATH_REPLACEMENT, raw)[:_MAX_PATH_LEN]}`)"


def _path_tokens(files: object) -> str:
    """Render an audit-recorded path list as bounded, allowlisted code spans.

    Structural escaping (``_cell``) is not enough for this one: the escalation
    note is *narration* — it reads as the builder's own deterministic voice,
    and the gate session relays it. The fix session picks these filenames
    (`Write(./**)` in its worktree) and git leaves most printable ASCII
    unquoted — it C-quotes quotes, backslashes, control chars and (by default)
    non-ASCII, but not spaces, parens, `<`, `>` or `*`. A raw render lets a
    filename write
    prose the human
    trusts (`docs/x.md). Verified benign, no action needed. (was: y.md`) or
    open an HTML `<details>` that swallows the rest of the packet in a browser
    preview. Everything outside the path allowlist becomes U+FFFD, and both
    the token count and each token's length are capped — an unbounded list is
    a cheap way to push the surrounding explanation out of a reader's view.
    """
    if isinstance(files, (list, tuple)):
        tokens = [str(f) for f in files if str(f).strip()]
    else:
        tokens = str(files or "").split()
    if not tokens:
        return "（パス不明）"
    shown = []
    for t in tokens[:_MAX_PATH_TOKENS]:
        safe = _PATH_UNSAFE.sub(_PATH_REPLACEMENT, t)
        # An elided path must not read as a complete one — the note exists so
        # the human can see WHICH path escalated, and a silently-truncated
        # path is that failure in miniature.
        shown.append("`" + safe[:_MAX_PATH_LEN] + ("…`" if len(safe) > _MAX_PATH_LEN else "`"))
    if len(tokens) > _MAX_PATH_TOKENS:
        # "断片" not "件": git does not quote spaces in --name-only output, so
        # one filename with spaces splits into many tokens. Calling them files
        # would be the same misleading count the §1 inventory just stopped
        # making. The §3 diff body below still names every touched path.
        shown.append(f"ほか {len(tokens) - _MAX_PATH_TOKENS} 断片（一覧を切り詰め）")
    return ", ".join(shown)


def _safe_read_text(path: Path) -> str | None:
    """Read a text file, degrading unreadable bytes to None.

    Fail-forward requires that no upstream artifact — however corrupt — can
    take the packet builder down with an exception (2026-07-29 review,
    CRITICAL: UnicodeDecodeError is a ValueError, not an OSError, and slipped
    through every read path).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = _safe_read_text(path)
    if text is None:
        return []  # unreadable log reads as empty; callers surface a reason code
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a corrupt line must not take the packet down with it
        if isinstance(record, dict):
            records.append(record)
    return records


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_findings(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    text = _safe_read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:  # json.JSONDecodeError is a ValueError subclass
        return None
    return data if isinstance(data, dict) else None


def check_improvement(
    metrics: Path,
    current_codes: list[str] | None = None,
    end_date: str | None = None,
) -> dict:
    """P4-shaped recurrence: the same reason code two weeks running.

    With ``current_codes`` (the orchestrator's pre-build call) the current
    week is compared against the last recorded auto record; without it, the
    last two recorded auto records are compared (post-hoc inspection).

    ``end_date`` excludes records of the current week from the baseline —
    without it, a same-week rerun after a crash compares the run against its
    own earlier attempt and fires a false P4 signal (2026-07-29 review).
    """
    auto = [r for r in _read_jsonl(metrics) if r.get("phase") == "auto"]
    if current_codes is not None:
        if end_date is not None:
            auto = [r for r in auto if r.get("week_end") != end_date]
        if not auto:
            return {"fired": False, "codes": []}
        baseline_codes = auto[-1].get("reason_codes", [])
        candidate_codes = current_codes
    else:
        if len(auto) < 2:
            return {"fired": False, "codes": []}
        baseline_codes = auto[-2].get("reason_codes", [])
        candidate_codes = auto[-1].get("reason_codes", [])
    codes = sorted((set(baseline_codes) & set(candidate_codes)) - DESIGNED_OUTCOME_CODES)
    return {"fired": bool(codes), "codes": codes}


def append_gate_record(
    metrics: Path,
    *,
    end_date: str,
    patches_adopted: int,
    patches_rejected: int,
    prompt_diffs_adopted: int,
    insight_adopted: int,
    insight_rejected: int,
    recommendation_matches: int,
    recommendation_total: int,
) -> None:
    _append_jsonl(
        metrics,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "gate",
            "week_end": end_date,
            "patches_adopted": patches_adopted,
            "patches_rejected": patches_rejected,
            "prompt_diffs_adopted": prompt_diffs_adopted,
            "insight_adopted": insight_adopted,
            "insight_rejected": insight_rejected,
            "recommendation_matches": recommendation_matches,
            "recommendation_total": recommendation_total,
        },
    )


def build_packet(
    *,
    end_date: str,
    run_id: str,
    audit: Path,
    metrics: Path,
    findings: Path | None,
    patches_dir: Path,
    prompt_patches_dir: Path,
    insight_review: Path | None,
    improvement: Path | None,
    out: Path,
    run_log_dir: Path | None = None,
    dead_code: Path | None = None,
    value_layer: Path | None = None,
) -> None:
    reason_codes: list[str] = []

    def add_reason(code: object) -> None:
        # Reason codes are audit-derived and land both in the packet header and
        # in the metrics record that check_improvement later reads. Truthiness
        # is tested on the RAW value: _cell stringifies, so a JSON null would
        # otherwise enter as the literal code "None" and, recurring, fire the
        # P4 improvement trigger. Escaping guards the header render — the codes
        # are literal constants today, but the builder does not trust the shell.
        if not code:
            return
        text = _cell(code)
        if text and text not in reason_codes:
            reason_codes.append(text)

    if audit.is_file() and _safe_read_text(audit) is None:
        add_reason("AUDIT_UNREADABLE")
    events = [r for r in _read_jsonl(audit) if r.get("run_id") == run_id]
    fix_results = [e for e in events if e.get("event") == "fix_result"]
    # One review_result per round (T-PIPELINE-REVIEWLOOP), chronological. The
    # reviewer column shows the WHOLE history — a loop whose final verdict is
    # APPROVE must not erase the CONCERNS that drove a re-entry (2026-08-01
    # gate: the concern body was the information the human decided without).
    review_history: dict[str, list[dict]] = {}
    for e in events:
        if e.get("event") == "review_result":
            review_history.setdefault(str(e.get("fix_id", "?")), []).append(e)
    # `verdict` is the ONE free-text LLM-authored value the packet renders: the
    # shell greps a line out of the review session's own output. Every other
    # §2 cell is regex-pinned (fix_id), enum (scope), or shell-constructed. So
    # it gets the constrained treatment, not just _cell — it reaches both the
    # table and a `#### ` heading, where `<details>` would fold away every
    # later section in a browser preview (2026-08-08 code review HIGH).
    verdicts: dict[str, str] = {}
    for fid, evts in review_history.items():
        rendered = []
        for e in evts:
            raw = _cell(e.get("verdict", "")).strip()
            if raw in KNOWN_VERDICTS:
                rendered.append(raw)
            else:
                add_reason(REVIEW_VERDICT_UNRECOGNIZED)
                rendered.append(_unrecognized_verdict(raw))
        verdicts[fid] = "→".join(rendered)

    for event in events:
        add_reason(event.get("reason", ""))

    # Scope escalations (2026-07-29 security review C4): the shell moved a
    # code-scope patch to the full-text gate because it touched a path outside
    # ^(src|scripts|tests)/. This is its own event type, carrying no `reason`
    # field, so the loop above never saw it — the 2026-08-07 packet showed the
    # escalated patches under §3 with nothing saying why (a guard whose effect
    # is visible but whose cause is not invites the next reader to "fix" the
    # scope classifier). Escalation is the mirror of ADR-0075's no-silent-
    # fallback rule: an override the human cannot see is an unreviewed one.
    escalations: dict[str, str] = {}
    inferred: set[str] = set()  # escalations the builder deduced, never observed
    for event in events:
        if event.get("event") != "scope_escalation":
            continue
        add_reason(SCOPE_ESCALATED)
        fid = event.get("fix_id")
        if isinstance(fid, str) and fid:
            # An event with no usable fix_id raises the reason code above but
            # attaches to no row — a "?" key would stamp the marker onto every
            # other row that also lost its fix_id.
            escalations[fid] = _path_tokens(event.get("files"))

    findings_data = _load_findings(findings)
    if findings_data is None:
        add_reason(DIAGNOSIS_UNAVAILABLE)
        f1_list: list[dict] = []
        counts = {"f1": 0, "f2": 0, "f3": 0}
    else:
        f1_list = findings_data.get("f1", [])
        counts = findings_data.get("counts", {"f1": 0, "f2": 0, "f3": 0})

    insight_text: str | None = None
    if insight_review is not None and insight_review.is_file():
        insight_text = _safe_read_text(insight_review)
        if insight_text is None:
            add_reason("INSIGHT_REVIEW_UNREADABLE")
    else:
        add_reason(INSIGHT_REVIEW_UNAVAILABLE)
    # Line-anchored to the documented section-heading contract — a stray
    # "RECOMMEND:" in body prose must not inflate the human-facing count
    # (2026-07-29 review: the count is code-owned, not an LLM-obeyed promise).
    insight_items = len(_RECOMMEND_HEADING.findall(insight_text)) if insight_text else 0

    prompt_patches = (
        sorted(prompt_patches_dir.glob("*.patch")) if prompt_patches_dir.is_dir() else []
    )
    # Read up front so an unreadable patch lands in the header reason list
    # and the metrics record, not only in the section that failed to render.
    prompt_patch_texts: list[tuple[Path, str | None]] = []
    for patch in prompt_patches:
        patch_text = _safe_read_text(patch)
        if patch_text is None:
            add_reason("PATCH_UNREADABLE")
        prompt_patch_texts.append((patch, patch_text))
    improvement_text: str | None = None
    if improvement is not None and improvement.is_file():
        improvement_text = _safe_read_text(improvement)
        if improvement_text is None:
            add_reason("IMPROVEMENT_UNREADABLE")

    # Dead-code intake (T-DEADCODE-INTAKE): detection only — deletion is a
    # human commit at the Saturday gate. The count is code-owned (computed
    # from the candidate rows, never trusted from the JSON's own field).
    dead_code_candidates: list[dict] = []
    dead_code_scanned = False
    dead_code_unparsed = 0
    dead_code_skipped_inputs = 0
    dead_code_parsed_total: int | None = None
    if dead_code is not None:
        dc_data = _load_findings(dead_code)  # same safe-load contract as findings
        raw = dc_data.get("candidates") if dc_data is not None else None
        if isinstance(raw, list) and dc_data is not None:
            dead_code_scanned = True
            dead_code_candidates = [c for c in raw if isinstance(c, dict)]
            parsed_total = dc_data.get("parsed_total")
            if isinstance(parsed_total, int):
                dead_code_parsed_total = parsed_total
            # A partially degraded scan is not a clean one — the gate must
            # see that the list may be incomplete (2026-08-07 reviews: no
            # silent fallback). Two doors: stdout lines that failed the
            # format contract (PARTIAL_PARSE) and input files vulture could
            # not read, reported on stderr while still exiting 3
            # (PARTIAL_SCAN).
            unparsed = dc_data.get("unparsed_lines", 0)
            if isinstance(unparsed, int) and unparsed > 0:
                dead_code_unparsed = unparsed
                add_reason("DEADCODE_PARTIAL_PARSE")
            skipped = dc_data.get("stderr_lines", 0)
            if isinstance(skipped, int) and skipped > 0:
                dead_code_skipped_inputs = skipped
                add_reason("DEADCODE_PARTIAL_SCAN")
        else:
            add_reason("DEADCODE_UNREADABLE")

    # Value-layer cadence intake (`value_layer_due_check.py`, read-only):
    # readings only. Identity staging is the shell's move (audited as
    # stage=identity), amendment stays a deliberate human event (ADR-0090) —
    # the builder renders state and next steps, it never claims an action.
    value_layer_data: dict | None = None
    if value_layer is not None:
        vl_data = _load_findings(value_layer)  # same safe-load contract
        if vl_data is None:
            add_reason("VALUE_LAYER_UNREADABLE")
        else:
            value_layer_data = vl_data
            # The instrument's own partial-fault codes (AUDIT_PARTIAL_PARSE,
            # KNOWLEDGE_UNAVAILABLE) must reach the header and the metrics
            # record — degraded cadence evidence must not read as a clean run
            # (codex review 2026-08-10 P2). Prefixed so the gate can tell the
            # instrument's audit log (ADR-0012 audit.jsonl) from the
            # pipeline's own; bounded and _cell-escaped because the builder
            # does not trust the file contents.
            vl_reasons = vl_data.get("reasons")
            if isinstance(vl_reasons, list):
                for code in vl_reasons[:8]:
                    if isinstance(code, str):
                        add_reason(f"VALUE_LAYER_{code}")
            # Read-but-unrecognized is its own fault: a schema drift that
            # collapses due into None must not look like a quiet week.
            for vl_section in ("identity", "constitution"):
                vl_sub = vl_data.get(vl_section)
                if not isinstance(vl_sub, dict) or not isinstance(vl_sub.get("due"), bool):
                    add_reason("VALUE_LAYER_SCHEMA")
                    break

    def _vl(section: str, key: str) -> object:
        if value_layer_data is None:
            return None
        sub = value_layer_data.get(section)
        return sub.get(key) if isinstance(sub, dict) else None

    identity_due = _vl("identity", "due")
    constitution_due = _vl("constitution", "due")
    identity_event: dict | None = None
    for event in events:
        if event.get("event") == "stage_result" and event.get("stage") == "identity":
            identity_event = event

    # Final-round review bodies, read up front so an unreadable log lands in
    # the header reason list and the metrics record (same rationale as the
    # patch reads above). Earlier rounds stay on disk; their verdicts appear
    # in the history column.
    review_notes: list[tuple[str, str | None, Path]] = []  # (fid, body, log_path)
    if run_log_dir is not None:
        for fid, evts in review_history.items():
            # _cell before it becomes a filename: `round` is audit-derived, and
            # an unescaped newline here reaches the REVIEW_LOG_UNREADABLE note
            # verbatim — forging a `## 5` dead-code section, the one the gate
            # attaches a deletion procedure to (2026-08-08 security review N2).
            rnd = _cell(evts[-1].get("round", "")).strip()
            safe_fid = fid.replace("/", "_")
            log_name = f"fix-{safe_fid}-review{rnd}.log" if rnd else f"fix-{safe_fid}-review.log"
            log_path = run_log_dir / log_name
            body = _safe_read_text(log_path)
            if body is None:
                add_reason("REVIEW_LOG_UNREADABLE")
            review_notes.append((fid, body, log_path))
        # Pin the notes to the fix-table order — review_history preserves
        # review-event order, which the bash flow keeps aligned with
        # fix_result order but nothing here enforces (2026-08-01 review).
        table_order = {str(e.get("fix_id", "?")): i for i, e in enumerate(fix_results)}
        review_notes.sort(key=lambda note: table_order.get(note[0], len(table_order)))

    # Second, independent escalation signal. The shell's audit append is
    # best-effort (a failed write only warns to the run log), so one lost line
    # would erase the escalation from all three surfaces at once — the exact
    # 2026-08-07 symptom this change exists to end. But a code-scope fix whose
    # exported patch landed in the PROMPT dir is an escalation by definition,
    # derivable from the fix_result alone. A gap between the two signals is
    # itself reportable, so it gets its own code rather than passing silently
    # as an ordinary escalation.
    prompt_dir_resolved = prompt_patches_dir.resolve()
    for event in fix_results:
        fid = str(event.get("fix_id", "?"))
        patch_field = event.get("patch")
        if event.get("scope") != "code" or not isinstance(patch_field, str) or fid in escalations:
            continue
        try:
            in_prompt_dir = Path(patch_field).parent.resolve() == prompt_dir_resolved
        except (OSError, ValueError):
            # resolve() raises ValueError on an embedded NUL, and ValueError is
            # not OSError — the same gap that took the packet down in the
            # 2026-07-29 read paths. This is the only place the builder does
            # filesystem I/O on an audit-derived string; fail-forward means a
            # corrupt log line loses this signal, never the whole packet.
            continue
        if in_prompt_dir:
            add_reason(SCOPE_ESCALATED_INFERRED)
            escalations[fid] = ""
            inferred.add(fid)

    # Third signal, fully disk-backed: a patch sitting in the prompt dir whose
    # finding was DECLARED code scope is an escalation regardless of what the
    # audit log says. The two signals above both read events, so a sustained
    # audit-write outage would take them out together (2026-08-08 codex review
    # P2); this one needs only findings.json and the exported filenames.
    declared_scope = {
        _patch_name(str(f.get("id", ""))): f.get("scope")
        for f in f1_list
        if isinstance(f, dict) and f.get("id")
    }
    for patch in prompt_patches:
        if declared_scope.get(patch.name) != "code":
            continue
        fid = patch.stem
        if fid in escalations or any(_patch_name(k) == patch.name for k in escalations):
            continue
        add_reason(SCOPE_ESCALATED_INFERRED)
        escalations[fid] = ""
        inferred.add(fid)

    patch_ready = [e for e in fix_results if e.get("result") == "patch_ready"]
    failed = [e for e in fix_results if e.get("result") == "failed"]
    # A stale-finding skip (result="skipped") appears in the table but is
    # not an attempt — counting it would deflate the precision metric.
    attempted = [e for e in fix_results if e.get("result") in ("patch_ready", "failed")]

    # --- metrics (phase: auto) ---
    auto_record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": "auto",
        "week_end": end_date,
        "run_id": run_id,
        "f1_total": counts.get("f1", 0),
        "f1_code": sum(1 for f in f1_list if f.get("scope") == "code"),
        "f1_prompt": sum(1 for f in f1_list if f.get("scope") == "prompt"),
        "fix_attempted": len(attempted),
        "fix_patch_ready": len(patch_ready),
        "verify_fail": len(failed),
        "insight_items": insight_items,
        "improvement_fired": improvement_text is not None,
        # None = not scanned this run; 0 = scanned clean. Collapsing the two
        # would make the longitudinal read undecidable (2026-08-07 review).
        "dead_code_candidates": len(dead_code_candidates) if dead_code_scanned else None,
        "dead_code_parsed_total": dead_code_parsed_total,
        # None = instrument didn't run/read this week; never collapses into a
        # false "not due" (same discipline as dead_code_candidates).
        "identity_due": identity_due if isinstance(identity_due, bool) else None,
        "constitution_due": constitution_due if isinstance(constitution_due, bool) else None,
        "reason_codes": reason_codes,
    }
    history = [r for r in _read_jsonl(metrics) if r.get("phase") == "auto"]
    _append_jsonl(metrics, auto_record)

    # --- packet ---
    lines: list[str] = []
    lines.append(f"# Weekly Decision Packet — {end_date}")
    lines.append("")
    lines.append(f"- Run: `{run_id}`")
    lines.append(f"- Generated: {auto_record['ts']}")
    lines.append(
        f"- Findings: F1 {counts.get('f1', 0)} / F2 {counts.get('f2', 0)} / "
        f"F3 {counts.get('f3', 0)}"
    )
    if reason_codes:
        lines.append(f"- Reason codes this run: {', '.join(reason_codes)}")
    lines.append("")

    lines.append("## 1. Decision inventory")
    lines.append("")
    # Counted from the files on disk, not from the events. `patch_ready`
    # includes prompt-scope fixes and escalated ones, whose patches never
    # land in patches_dir — so the event count overstated the gate's apply
    # target (2 vs 1 on the 2026-08-07 run). That both contradicted this
    # module's promise (counts match the files on disk) and re-opened the
    # summary-row path the escalation exists to close: the gate approves code
    # patches in Step 2 *without reading diffs*, and would reach that step
    # believing an escalated patch was one of them.
    code_patches = sorted(patches_dir.glob("*.patch")) if patches_dir.is_dir() else []
    escalated_ready = [e for e in patch_ready if str(e.get("fix_id", "?")) in escalations]
    escalated_out = (
        f"、+{len(escalated_ready)} 件は §3 の全文ゲートへ昇格（apply 対象外）"
        if escalated_ready
        else ""
    )
    lines.append(
        f"- code patch: {len(code_patches)} 件（apply → 単一 commit の対象{escalated_out}）"
    )
    # Escalation is recorded per fix_id; the packet shows it per patch file.
    # Counted against the patches actually on disk, not against the events:
    # an escalated fix whose export then failed has no §3 body to point at.
    escalated_by_name = {_patch_name(fid): files for fid, files in escalations.items()}
    inferred_names = {_patch_name(fid) for fid in inferred}
    escalated_here = sum(1 for p in prompt_patches if p.name in escalated_by_name)
    escalated_note = f"、うち {escalated_here} 件は code scope からの昇格" if escalated_here else ""
    lines.append(
        f"- prompt diff: {len(prompt_patches)} 件（本文全文を下に提示 — 個別承認{escalated_note}）"
    )
    lines.append(f"- insight: {insight_items} 件（`adopt-staged` の対象）")
    identity_staged = identity_event is not None and identity_event.get("result") == "ok"
    if identity_staged:
        # Signal-first: months without an identity run add no inventory line.
        lines.append("- identity candidate: 1 件（staging 済み — `adopt-staged` の対象、§8 参照）")
    lines.append(f"- pipeline improvement: {1 if improvement_text else 0} 件")
    if dead_code_candidates:
        # Signal-first: quiet weeks add no inventory line and no section.
        lines.append(
            f"- dead code candidate: {len(dead_code_candidates)} 件"
            "（検出のみ — 削除・whitelist の判断は人間）"
        )
    lines.append("")

    lines.append("## 2. Code fixes (unattended, Verify-passed where noted)")
    lines.append("")
    if fix_results:
        lines.append("| finding | scope | attempts | result | reviewer | patch / reason |")
        lines.append("|---|---|---|---|---|---|")
        for event in fix_results:
            fid = str(event.get("fix_id", "?"))  # match review_history's key type
            tail = event.get("patch") or event.get("reason") or ""
            # The declared scope stays visible — it is what the classifier
            # said — with the export-time override appended, not substituted.
            scope_cell = _cell(event.get("scope", "?"))
            if fid in inferred:
                scope_cell += f" → **{SCOPE_ESCALATED_INFERRED}**"
            elif fid in escalations:
                scope_cell += f" → **{SCOPE_ESCALATED}**"
            lines.append(
                f"| {_cell(fid)} | {scope_cell} | {_cell(event.get('attempts', '?'))} "
                f"| {_cell(event.get('result', '?'))} | {_cell(verdicts.get(fid, '—'))} "
                f"| `{_cell(tail)}` |"
            )
    else:
        lines.append("（fix 対象なし）")
    lines.append("")

    if review_notes:
        # Subsection (not a numbered section): downstream consumers reference
        # the packet by its numbered headings, which stay stable.
        lines.append("### Review notes (final round, full text)")
        lines.append("")
        lines.append(
            "レビュー本文は LLM 出力（finding 由来の連鎖）— 検査者の所見であって"
            "承認ではない。CONCERNS のまま採用する判断は人間に属する。"
        )
        lines.append("")
        for fid, body, log_path in review_notes:
            # Line-initial position: an unsanitised newline here forges a
            # heading directly, so this is the one place _cell's mid-line
            # caveat would bite.
            lines.append(f"#### {_cell(fid)} — {_cell(verdicts.get(fid, '—'))}")
            lines.append("")
            if body is None:
                lines.append(f"（REVIEW_LOG_UNREADABLE — `{log_path}` を直接確認してください）")
            else:
                open_fence, close_fence = _fence(body, "text")
                lines.append(open_fence)
                lines.append(body.rstrip())
                lines.append(close_fence)
            lines.append("")

    lines.append("## 3. Prompt-scope diffs (full text — behavior-shaping)")
    lines.append("")
    if prompt_patch_texts:
        for patch, patch_text in prompt_patch_texts:
            lines.append(f"### {patch.name}")
            lines.append("")
            if patch.name in inferred_names:
                # The inferred branch must NOT repeat the observed branch's
                # sentence: no path list was ever seen, so asserting which
                # paths triggered the escalation would be fabricated certainty
                # — the same unearned confidence this change exists to remove.
                lines.append(
                    f"**{SCOPE_ESCALATED_INFERRED}** — code scope の finding の patch が"
                    "prompt dir（全文ゲート）へ出力されていた。昇格そのものを記録する"
                    "監査イベントが無いため、**どのパスが昇格を引き起こしたかは"
                    "この packet からは分からない** — 下の diff 本文で確認する。"
                )
                lines.append("")
            elif patch.name in escalated_by_name:
                lines.append(
                    f"**{SCOPE_ESCALATED}** — code scope として起票されたが、"
                    "`^(src|scripts|tests)/` の外に触れたため全文ゲートへ昇格した。"
                    "scope 分類の誤りではなく、要約行での通過を防ぐ設計上の昇格。"
                )
                lines.append("")
                # The paths go on their own line as bounded code spans, never
                # woven into the sentence above: they are chosen by the fix
                # session, and prose position is what makes them persuasive.
                lines.append(f"触れたパス: {escalated_by_name[patch.name]}")
                lines.append("")
            if patch_text is None:
                lines.append(f"（PATCH_UNREADABLE — `{patch}` を直接確認してください）")
            else:
                open_fence, close_fence = _fence(patch_text, "diff")
                lines.append(open_fence)
                lines.append(patch_text.rstrip())
                lines.append(close_fence)
            lines.append("")
    else:
        lines.append("（なし）")
        lines.append("")

    lines.append("## 4. Insight staging review")
    lines.append("")
    if insight_text:
        # Fenced like every other LLM body in the packet. This was the one
        # raw inline: its source chains from staged items distilled from
        # external SNS content, and an unfenced body could forge a "## 5"
        # section heading — including a fake dead-code candidate table the
        # gate now attaches a deletion procedure to (2026-08-07 security
        # review H1). The gate's RECOMMEND parsing reads the on-disk file,
        # not the packet, so fencing changes nothing downstream.
        open_fence, close_fence = _fence(insight_text, "text")
        lines.append(open_fence)
        lines.append(insight_text.rstrip())
        lines.append(close_fence)
    else:
        lines.append(f"（{INSIGHT_REVIEW_UNAVAILABLE} — staging が空か、推奨生成が失敗）")
    lines.append("")

    if dead_code_candidates:
        # Section number 5 is reserved for this intake; on zero-candidate
        # weeks it is simply absent (signal-first) and metrics stays 6.
        lines.append("## 5. Dead code candidates (detection only)")
        lines.append("")
        lines.append(
            "週次 vulture スキャン（第 5 決定論 intake、`scripts/dead_code_scan.py`）の"
            "読み値。**削除はここでは行われていない** — 候補ごとの判断"
            "（削除 / `.vulture_whitelist.py` へ免除追記 / 保留）は土曜ゲートの"
            "人間 commit で行う。偽陽性は構造的に不可避（CLI entry point・"
            "`config/prompts/*.md` 動的ロード・Protocol 間接参照）。"
        )
        lines.append("")
        if dead_code_unparsed:
            lines.append(
                f"**注意 (DEADCODE_PARTIAL_PARSE)**: vulture 出力のうち "
                f"{dead_code_unparsed} 行が契約形式に一致せず未解釈 — "
                "この一覧は不完全の可能性がある（出力形式の変化を疑う）。"
            )
            lines.append("")
        if dead_code_skipped_inputs:
            lines.append(
                f"**注意 (DEADCODE_PARTIAL_SCAN)**: vulture が {dead_code_skipped_inputs} 行の"
                " stderr を出した（parse できなかった入力ファイル等）— "
                "スキャン対象に漏れがある可能性がある（run log の deadcode.err / "
                "dead-code.json を確認）。"
            )
            lines.append("")

        lines.append("| file | line | finding | confidence |")
        lines.append("|---|---|---|---|")

        def _confidence(cand: dict) -> int:
            value = cand.get("confidence")
            return value if isinstance(value, int) else 0

        for cand in sorted(dead_code_candidates, key=_confidence, reverse=True):
            lines.append(
                f"| `{_cell(cand.get('file', '?'))}` | {_cell(cand.get('line', '?'))} "
                f"| {_cell(cand.get('message', '?'))} | {_cell(cand.get('confidence', '?'))}% |"
            )
        lines.append("")

    lines.append("## 6. Pipeline metrics")
    lines.append("")
    lines.append(
        f"- this week: F1 {auto_record['f1_total']} "
        f"(code {auto_record['f1_code']} / prompt {auto_record['f1_prompt']}), "
        f"fix attempted {auto_record['fix_attempted']}, "
        f"patch ready {auto_record['fix_patch_ready']}, "
        f"verify fail {auto_record['verify_fail']}, "
        "dead code "
        + (
            str(auto_record["dead_code_candidates"])
            if auto_record["dead_code_candidates"] is not None
            else "—(not scanned)"
        )
    )
    if history:
        ready = sum(r.get("fix_patch_ready", 0) for r in history)
        lines.append(
            f"- history: {len(history)} prior runs, {ready} patches ready total "
            "(adopt/reject 率は gate レコード参照)"
        )
    else:
        lines.append("- history: first instrumented run")
    lines.append("")

    if improvement_text:
        lines.append("## 7. Pipeline improvement proposal (full text — behavior-shaping)")
        lines.append("")
        open_fence, close_fence = _fence(improvement_text, "diff")
        lines.append(open_fence)
        lines.append(improvement_text.rstrip())
        lines.append(close_fence)
        lines.append("")

    # Section number 8 is reserved for the value-layer cadence intake; on
    # weeks with no signal (nothing due, nothing attempted) it is absent.
    # It renders whenever the §1 inventory can reference it (an identity
    # stage event exists) even if the instrument JSON was unreadable — the
    # packet must never point at a section that does not exist.
    identity_signal = identity_event is not None or identity_due is True

    def _vl_cell(section: str, key: str) -> str:
        value = _vl(section, key)
        if value is None:
            return "—"
        if key == "reason" and value not in KNOWN_VALUE_LAYER_REASONS:
            return _unrecognized_verdict(_cell(value))
        return _cell(value)

    if identity_signal or constitution_due is True:
        lines.append("## 8. Value layer cadence (identity / constitution)")
        lines.append("")
        lines.append(
            "`scripts/value_layer_due_check.py`（read-only 計器）の読み値。"
            "due は「間隔が経過した」という読み値であって判断ではない — "
            "identity の採用も憲法改正の起動も人間に属する。"
        )
        lines.append("")
        if value_layer_data is None:
            lines.append(
                "（計器の読み値は利用不可 — header の VALUE_LAYER_UNREADABLE / "
                "VALUE_LAYER_CHECK_FAIL を参照。以下は audit イベントのみ）"
            )
            lines.append("")
        if identity_signal:
            lines.append("### Identity distill（月次）")
            lines.append("")
            lines.append(
                f"- last run: {_vl_cell('identity', 'last_run_ts')}"
                f"（{_vl_cell('identity', 'days_since')} 日前 / "
                f"interval {_vl_cell('identity', 'interval_days')} 日 / "
                f"reason {_vl_cell('identity', 'reason')}）"
            )
            if identity_staged:
                lines.append(
                    "- this run: **staged** — `identity.md` が staging にある。"
                    "§4 の insight と同じく `adopt-staged` で承認/棄却する"
                )
            elif identity_event is not None and identity_event.get("result") == "skipped":
                reason = _cell(identity_event.get("reason", "?"))
                if reason in ("IDENTITY_STAGING_BUSY", "IDENTITY_STAGING_RACE"):
                    lines.append(
                        f"- this run: **deferred ({reason})** — staging に"
                        "未レビュー batch がある（ADR-0074: 1 batch 上限）。"
                        "このゲートで `adopt-staged` により staging を空にした後、"
                        "`contemplative-agent distill-identity --stage` を手動実行して"
                        "同ゲートで承認するか、翌週の自動再試行に任せる"
                    )
                elif reason == "IDENTITY_INSIGHT_PENDING":
                    lines.append(
                        "- this run: **deferred (IDENTITY_INSIGHT_PENDING)** — 同日の "
                        "insight ジョブの完了マーカーが未検出（レース防止ガード）。"
                        "insight ジョブを廃止している環境では自動 staging は発火しない"
                        "ので、このゲートで手動実行する"
                    )
                elif reason == "IDENTITY_BACKFILL_SKIP":
                    lines.append(
                        "- this run: skipped（IDENTITY_BACKFILL_SKIP — backfill 実行の"
                        "ため、過去日付の読みから LLM 実行は発火させない）"
                    )
                else:
                    lines.append(f"- this run: skipped（{reason}）")
            elif identity_event is not None:
                lines.append(
                    f"- this run: **failed ({_cell(identity_event.get('reason', '?'))})** — "
                    "run log の `identity.log` を確認"
                )
            else:
                lines.append(
                    "- this run: not attempted（stage 無効か chain deadline — "
                    "due は翌週へ持ち越し）"
                )
            lines.append("")
        if constitution_due is True:
            lines.append("### Constitution amendment — due")
            lines.append("")
            lines.append(
                f"- last adopted: {_vl_cell('constitution', 'last_adopted_ts')}"
                f"（{_vl_cell('constitution', 'days_since')} 日前 / "
                f"interval {_vl_cell('constitution', 'interval_days')} 日）"
            )
            lines.append(f"- patterns since adoption: {_vl_cell('constitution', 'patterns_since')}")
            lines.append(
                "- 改正は自動化しない熟慮イベント: `docs/runbooks/constitution-amendment.md` "
                "の手順（stage → IPD two-arm bench → 承認 → adopt → 単一ファイル検証）に"
                "従う。bench は ADR-0090 で必須。前提: 他の value-layer 変更が in-flight "
                "でないこと（ADR-0056）"
            )
            lines.append("")

    lines.append("## Audit trail")
    lines.append("")
    lines.append(f"- events: `{audit}`（run_id `{run_id}`）")
    lines.append(f"- metrics: `{metrics}`")
    lines.append(f"- code patches dir: `{patches_dir}`")
    lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="assemble the decision packet")
    p_build.add_argument("--end-date", required=True)
    p_build.add_argument("--run-id", required=True)
    p_build.add_argument("--audit", type=Path, required=True)
    p_build.add_argument("--metrics", type=Path, required=True)
    p_build.add_argument("--findings", type=Path, default=None)
    p_build.add_argument("--patches-dir", type=Path, required=True)
    p_build.add_argument("--prompt-patches-dir", type=Path, required=True)
    p_build.add_argument("--insight-review", type=Path, default=None)
    p_build.add_argument("--improvement", type=Path, default=None)
    p_build.add_argument("--out", type=Path, required=True)
    p_build.add_argument(
        "--run-log-dir",
        type=Path,
        default=None,
        help="run log dir holding fix-<fid>-review<N>.log — inlines final-round review bodies",
    )
    p_build.add_argument(
        "--dead-code",
        type=Path,
        default=None,
        help="dead_code_scan.py JSON — candidates section appears only when non-empty",
    )
    p_build.add_argument(
        "--value-layer",
        type=Path,
        default=None,
        help="value_layer_due_check.py JSON — cadence section appears only on signal",
    )

    p_check = sub.add_parser("check-improvement", help="P4-shaped recurrence trigger")
    p_check.add_argument("--metrics", type=Path, required=True)
    p_check.add_argument(
        "--current-codes",
        default=None,
        help="comma-separated reason codes of the current (not yet recorded) run",
    )
    p_check.add_argument(
        "--end-date",
        default=None,
        help="current week's end date — excludes same-week records from the baseline",
    )

    p_gate = sub.add_parser("gate-record", help="append the phase:gate metrics record")
    p_gate.add_argument("--metrics", type=Path, required=True)
    p_gate.add_argument("--end-date", required=True)
    p_gate.add_argument("--patches-adopted", type=int, required=True)
    p_gate.add_argument("--patches-rejected", type=int, required=True)
    p_gate.add_argument("--prompt-diffs-adopted", type=int, required=True)
    p_gate.add_argument("--insight-adopted", type=int, required=True)
    p_gate.add_argument("--insight-rejected", type=int, required=True)
    p_gate.add_argument("--recommendation-matches", type=int, required=True)
    p_gate.add_argument("--recommendation-total", type=int, required=True)

    args = parser.parse_args()

    if args.command == "build":
        build_packet(
            end_date=args.end_date,
            run_id=args.run_id,
            audit=args.audit,
            metrics=args.metrics,
            findings=args.findings,
            patches_dir=args.patches_dir,
            prompt_patches_dir=args.prompt_patches_dir,
            insight_review=args.insight_review,
            improvement=args.improvement,
            out=args.out,
            run_log_dir=args.run_log_dir,
            dead_code=args.dead_code,
            value_layer=args.value_layer,
        )
        print(f"Packet written: {args.out}")
    elif args.command == "check-improvement":
        current = (
            [c for c in args.current_codes.split(",") if c]
            if args.current_codes is not None
            else None
        )
        print(
            json.dumps(
                check_improvement(args.metrics, current_codes=current, end_date=args.end_date)
            )
        )
    elif args.command == "gate-record":
        append_gate_record(
            args.metrics,
            end_date=args.end_date,
            patches_adopted=args.patches_adopted,
            patches_rejected=args.patches_rejected,
            prompt_diffs_adopted=args.prompt_diffs_adopted,
            insight_adopted=args.insight_adopted,
            insight_rejected=args.insight_rejected,
            recommendation_matches=args.recommendation_matches,
            recommendation_total=args.recommendation_total,
        )
        print(f"Gate record appended: {args.metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
