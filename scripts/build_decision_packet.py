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

from _md import printable

DIAGNOSIS_UNAVAILABLE = "DIAGNOSIS_UNAVAILABLE"
# Per-finding counterpart of the above: the run produced findings.json, but
# this row's id is not in it (or its heading is empty). A named state, not
# prose — §2 now asks the gate to refuse ID-only approval, so "no heading"
# must be as legible as "no diagnosis".
DIAGNOSIS_TITLE_MISSING = "DIAGNOSIS_TITLE_MISSING"
# Two `### F1.N.` headings sharing an id: the builder would silently pick one
# (last-wins) while the fix stage picked the other (first-wins, weekly-
# pipeline.sh), so the approver could read a heading describing a different
# finding than the patch implements (2026-08-15 security review MEDIUM).
DIAGNOSIS_TITLE_DUPLICATE = "DIAGNOSIS_TITLE_DUPLICATE"
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
# NEVER_SELECTED_BELOW_FLOOR (ADR-0097 D5) joins them: skills were never
# selected but none had accumulated the 600 judged exposures that make
# "never selected" mean anything, so the reading proposes nothing. That is the
# floor doing its job, and it recurs by design in every week following an
# adoption — counting it would spend an unattended improve session on a guard
# whose own section calls the outcome deliberate.
DESIGNED_OUTCOME_CODES = frozenset(
    {
        SCOPE_ESCALATED,
        "IDENTITY_STAGING_BUSY",
        "IDENTITY_INSIGHT_PENDING",
        "NEVER_SELECTED_BELOW_FLOOR",
    }
)

# ADR-0097 D5 never-selected intake. The reading is produced under the venv
# (`core.skill_selection.never_selected_reading_json`) because it needs the
# selection-log grammar and the catalog loader; this module only renders it.
NEVER_SELECTED_UNREADABLE = "NEVER_SELECTED_UNREADABLE"
# Rows that do not match the contract the section is rendered from — a strict
# row without an integer exposure, or a floor that is not a positive integer.
# The strict list is the one list a human archives from, so a row the builder
# cannot re-check against the declared floor is dropped and named, never shown.
NEVER_SELECTED_SCHEMA = "NEVER_SELECTED_SCHEMA"
# The instrument's own closed vocabulary, re-emitted into the header so a
# degraded exit reading does not read as a clean week. Anything outside it is
# schema drift.
KNOWN_NEVER_SELECTED_REASONS = frozenset(
    {
        "NEVER_SELECTED_NO_CATALOG",
        "NEVER_SELECTED_NO_HISTORY",
        "NEVER_SELECTED_BELOW_FLOOR",
        "NEVER_SELECTED_FULL_TOKENS_UNKNOWN",
    }
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

# The rules layer's own vocabulary (ADR-0097 D2), kept apart from the cadence
# one rather than merged into it: `OK` is a legitimate rules state and a
# nonsense identity reason, and one union set would have made the second read
# as contract-abiding. `OK` / `RULES_EMPTY` / `RULES_DIR_MISSING` are states of
# the layer, not faults; only RULES_UNREADABLE reaches the header, and the
# instrument — not this list — decides that.
KNOWN_RULES_REASONS = frozenset({"OK", "RULES_EMPTY", "RULES_DIR_MISSING", "RULES_UNREADABLE"})

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


def _flatten(value: object) -> str:
    """An audit-log value as ONE LINE, with nothing neutralised.

    Split out of :func:`_cell` for the callers that must see the ORIGINAL
    characters: ``_title_cell``, which marks inline markup before the floor can
    substitute it away, and the reviewer-verdict check, which tests membership
    in a contract and must not be handed a laundered value.

    Lists are joined rather than repr'd — the shell space-joins today, but the
    builder must not depend on that, and it must not be a second place that
    decides it either.

    ``splitlines()``, not ``replace("\n")``: it is the splitter every consumer
    of this packet uses, and it also breaks on \v \f \x1c-\x1e \x85 and
    U+2028/U+2029 — a code/test that disagreed on the line-break alphabet would
    assert a stronger invariant than the code holds.
    """
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    return " ".join(str(value).splitlines())


def _cell(value: object) -> str:
    """Flatten an audit-log value into one Markdown table cell / note line.

    The structural floor every audit value passes through, so that a new
    producer cannot reach a table cell by being forgotten. The per-producer
    form has already failed once: the retired ledger-watch intake treated
    ``detail`` as the only field needing it, and ``target`` reached its section
    raw.

    **Where the floor is the whole defence, and where it is not.** Three audit
    values are written outside this repo's control and get a stricter renderer
    ON TOP of this one: ``_title_cell``, ``_unrecognized_verdict``,
    ``_path_tokens``. The last of those also carries the recorded run-log path,
    which is repo-written but reaches the note line at the one position this
    floor does not cover — see the ``REVIEW_LOG_UNREADABLE`` note in §2.
    File bodies bypass this floor entirely — see ``_fence``.

    Every other audit value is a shell literal or is pinned upstream, and for
    those this floor is all they get. That is the decision, not an omission: a
    finding that one of them could forge packet structure needs a hand-edited
    audit log, and an actor who can hand-edit that log can write the packet
    directly (2026-08-16, T-PACKET-FLOOR-BYPASS).

    Safe **mid-line only**: a leading `#` and backtick runs are not
    neutralised, so a caller emitting ``f"{_cell(v)}"`` at the start of a line
    reopens the hole. Flattening to one line — including the list rule — is
    :func:`_flatten`'s, not restated here. Values that are *paths* rather than
    cells need :func:`_path_tokens` instead: this one passes ``/``, and it
    escapes for Markdown rather than for a reader deciding what was opened.
    """
    # Backslash first, so escaping `|` cannot be undone by a preceding literal
    # backslash. `printable` before both: a substitution that produced a `\` or
    # a `|` would otherwise go unescaped and silently give the table a column.
    # THIS CALL passes the default space, which cannot; the parameter exists
    # (`_title_cell` uses U+FFFD), so the safety is a property of the argument
    # here rather than of the function — do not pass a replacement containing
    # `\` or `|` (2026-08-16 code review MEDIUM).
    return printable(_flatten(value)).replace("\\", "\\\\").replace("|", "\\|")


def _patch_name(fix_id: str) -> str:
    """The exporter's fix_id → patch filename contract (weekly-pipeline.sh:866).

    Still a reconstruction, and deliberately left as one when the run-log path
    stopped being rebuilt (2026-08-16). A different defect class: after that
    change the patch name has ONE rule spelled identically on both sides, where
    the run-log name had two incompatible rules held apart only by
    ``parse_findings.py``'s pin. Same-rule-twice is a maintenance risk;
    different-rules-twice was a live divergence. This output is also only ever
    COMPARED against a name on disk, never joined and opened.

    Swapping in the audit's own ``patch`` field is blocked at ONE of the four
    call sites, not all: the third escalation signal below reads the exported
    filenames precisely because it must survive an audit-write outage. The
    ``escalated_by_name`` / ``inferred_names`` uses are already keyed off
    audit-derived ``escalations``, so they would spend no independence that is
    not already spent. That the conflict is partial is what makes it decidable
    — T-PACKET-PATCH-NAME-FROM-SHELL holds the trade.
    """
    return f"{fix_id.replace('/', '_')}.patch"


# The reviewer contract (weekly-pipeline.sh): APPROVE ends the loop, CONCERNS
# drives one re-entry, REVIEW_FAIL is the shell's own fallback when no
# `^VERDICT:` line was found. Anything else means the review session broke
# contract, which is a reportable fault rather than a value to render as-is.
KNOWN_VERDICTS = ("APPROVE", "CONCERNS", "REVIEW_FAIL")
REVIEW_VERDICT_UNRECOGNIZED = "REVIEW_VERDICT_UNRECOGNIZED"

# The run-log ladder, in the order the review-note loop walks it: nothing
# declared / declared but not containable / containable but unreadable. Three
# codes because they are expected to behave differently over time — the first
# is designed to RETIRE as pre-2026-08-16 weeks age out, the second should
# never fire at all, the third is an ordinary fail-forward gap. A code expected
# to go quiet and a code expected to stay silent cannot share a bucket without
# making both unreadable, the same reason the metrics record below keeps "not
# scanned" distinct from "scanned clean".
REVIEW_LOG_PATH_MISSING = "REVIEW_LOG_PATH_MISSING"
REVIEW_LOG_OUTSIDE_RUN_DIR = "REVIEW_LOG_OUTSIDE_RUN_DIR"
REVIEW_LOG_UNREADABLE = "REVIEW_LOG_UNREADABLE"

# The path alphabet: what a rendered path may keep. Everything else becomes
# U+FFFD, including the newline that would forge a heading and the `<` that
# would open a `<details>`.
_PATH_CHARS = "A-Za-z0-9._+-"
_PATH_UNSAFE = re.compile(rf"[^{_PATH_CHARS}/]")
_PATH_REPLACEMENT = "�"
_MAX_PATH_TOKENS = 20
_MAX_PATH_LEN = 120
# The run-log note prints an ABSOLUTE path (~107 chars here), so it gets its own
# budget rather than `_MAX_PATH_LEN`'s, which was sized for the repo-relative
# names a fix session picks. Same number as `_MAX_TITLE_LEN` and the same job:
# bound one reader's line without eliding the thing the line exists to show.
_MAX_LOG_PATH_LEN = 240
# Measured over the 17 F1 headings in the 2026-07-31..08-14 findings files:
# max 193, median 164. 240 leaves ~24% headroom on the widest observed heading
# while still bounding the line, so one heading cannot push the §2 table off a
# reader's screen. The budget is spent on the ESCAPED form, so a pipe-heavy
# heading fits fewer source characters than this number suggests.
_MAX_TITLE_LEN = 240
# A heading is prose, so it gets no path-style allowlist (Japanese would not
# survive one) — but every character class that can open an INLINE construct
# does get neutralised, because mid-line is exactly where those are legal:
#   < >    raw HTML. An unclosed <details> is closed by nothing and folds §3-§9
#          behind a summary line the heading's author wrote (2026-08-08 HIGH,
#          named verbatim in _path_tokens' docstring, reachable again here).
#   [ ]    link / image markup — a destination beside a patch row, in the
#          builder's narrating voice, at the moment of approval.
#   `      code span; it spans line breaks, so one stray backtick swallows the
#          rows below it. Costs the `audit.jsonl` styling real headings use —
#          the heading is a pointer, and findings.md keeps the styled original.
#   ctrl / bidi / zero-width: ANSI manipulation when the packet is cat'd, and
#          reordering of what the approver reads.
_TITLE_UNSAFE = re.compile(r"[<>\[\]`\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def _unrecognized_verdict(raw: str) -> str:
    """Render an off-contract reviewer verdict without carrying its markup."""
    if not raw:
        return "—"
    return f"UNRECOGNIZED(`{_PATH_UNSAFE.sub(_PATH_REPLACEMENT, raw)[:_MAX_PATH_LEN]}`)"


def _path_tokens(files: object, max_len: int = _MAX_PATH_LEN) -> str:
    """Render an audit-recorded path list as bounded, allowlisted code spans.

    Two callers, one claim: **a path rendered inside the builder's own
    narration, whoever chose it.** The escalation note below is the first; the
    second is the ``REVIEW_LOG_UNREADABLE`` note, whose path the shell chose
    rather than a fix session. That one is checked for containment before it is
    opened, and containment is not a renderer — it bounds where the builder
    READS and says nothing about what a name may PRINT, so a path legitimately
    inside the run-log dir still arrives here unneutralised.

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

    ``max_len`` is a parameter because the two callers render different-sized
    values against the same purpose. The default fits the repo-relative names
    a fix session picks. An ABSOLUTE path needs more: the run-log note runs
    ~107 characters on this machine, so the default would leave ~13 characters
    of headroom and then hand the operator a truncated, unopenable path — in
    the note whose only job is to let them open it.
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
        shown.append("`" + safe[:max_len] + ("…`" if len(safe) > max_len else "`"))
    if len(tokens) > _MAX_PATH_TOKENS:
        # "断片" not "件": git does not quote spaces in --name-only output, so
        # one filename with spaces splits into many tokens. Calling them files
        # would be the same misleading count the §1 inventory just stopped
        # making. The §3 diff body below still names every touched path.
        shown.append(f"ほか {len(tokens) - _MAX_PATH_TOKENS} 断片（一覧を切り詰め）")
    return ", ".join(shown)


def _title_cell(title: object) -> str:
    """Render a diagnosis heading as a bounded, mid-line quotation.

    §2 used to name findings by ID alone, which left the reviewer's
    verification prose — written for the next agent — as the only readable
    material at the moment of approval. The heading answers "what is this
    patch for", so it belongs beside the row.

    It is LLM prose in the builder's narrating voice, the same class
    ``_path_tokens`` guards, and it needs both halves of that guard:

    - **block structure** — ``_flatten`` collapses line breaks and ``_cell``
      escapes pipes, and the caller keeps it mid-line, so it cannot open a
      heading, a fence or a table column;
    - **inline structure** — ``_TITLE_UNSAFE`` neutralises what is legal
      mid-line: raw HTML (an unclosed ``<details>`` folds §3-§9 behind a
      summary the heading's author wrote), link/image markup, and code spans
      that run past the line break;
    - **invisibility** — ``_TITLE_UNSAFE`` names the bidi and zero-width
      characters it knew about, and ``printable`` covers the ones no
      enumeration keeps up with. Both replace with U+FFFD rather than a space,
      which is what separates this from ``_cell``'s floor: here the approver
      has to be able to SEE that the heading was rewritten.

    The length is capped because an unbounded heading pushes the table it
    explains out of view, and elision is marked — a silently cut heading reads
    as a whole one. The cap measures the escaped form (so the packet line has a
    real bound), which can land inside an escape pair; the trailing backslash
    run is dropped rather than shown, since a lone `\\` on a legibility line is
    the wart this whole change exists to remove.
    """
    # None (no such id) and "" (parsed, empty heading) are the same fact to the
    # approver, and _cell would render the former as the literal "None". Passed
    # unstringified so a list still reaches the shared join, not a repr.
    #
    # Both marking passes run BEFORE _cell, not after. _cell's floor
    # substitutes a space, so running it first left them with nothing to match
    # and turned a U+FFFD — the approver's only sign that a heading was
    # rewritten — into an invisible space. This is the human gate; a tampered
    # heading has to read as one.
    #
    # And `printable` beside `_TITLE_UNSAFE`, because the enumerated class is
    # not complete and enumerations of this class keep proving not to be:
    # U+061C, U+2060 and U+FEFF are all outside _TITLE_UNSAFE, all silently
    # swallowed by the floor, and all found by cross-model review rather than
    # by writing the class out again (2026-08-16). `printable` decides what the
    # floor would remove by the same predicate the floor uses, so the marking
    # cannot fall behind it. A heading is a single line by contract, so marking
    # line breaks here rather than flattening them is the same judgement —
    # _TITLE_UNSAFE's \x00-\x1f already did it for \n, and this extends it to
    # U+2028/U+2029, which it did not cover.
    marked = printable(
        _TITLE_UNSAFE.sub(_PATH_REPLACEMENT, _flatten(title or "")), _PATH_REPLACEMENT
    )
    flat = _cell(marked).strip()
    if not flat:
        return f"（{DIAGNOSIS_TITLE_MISSING} — findings.json にこの ID の見出しが無い）"
    if len(flat) > _MAX_TITLE_LEN:
        return flat[:_MAX_TITLE_LEN].rstrip("\\") + "…"
    return flat


def _safe_read_text(path: Path) -> str | None:
    """Read a text file, degrading unreadable bytes AND unopenable paths to None.

    Fail-forward requires that no upstream artifact — however corrupt — can
    take the packet builder down with an exception (2026-07-29 review,
    CRITICAL: UnicodeDecodeError is a ValueError, not an OSError, and slipped
    through every read path).

    ``ValueError``, which subsumes ``UnicodeDecodeError``. The same gap has cost
    this module twice — the decode above, and ``resolve()`` on an embedded NUL
    in the escalation inference below — and ``open()`` is the third shape it
    could take: a NUL in a built filename raises ``ValueError`` out of
    ``build_packet``, and a missing packet is the watchdog's finding
    (`scripts/pipeline_watchdog.sh`), not the builder's. It reads as "the chain
    died", so a fault the packet exists to REPORT would arrive as the absence of
    the report. No producer can reach it today: the run-log path is resolved
    for the containment check before it is opened, and ``resolve()`` raises on
    the NUL first — so this is the second door on one input, not a repair of an
    observed failure.

    Widening is narrow in practice: the only ``ValueError`` this adds is the
    embedded-NUL path, and it is not silent — the callers that surface a
    degraded read turn None into a named reason code. (``_read_jsonl`` turns it
    into ``[]`` instead, which for the metrics file suppresses the P4 trigger
    rather than naming it. Pre-existing, and unreachable by the same argument.)
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
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
    patches_held: int | None = None,
    prompt_diffs_held: int | None = None,
    insight_held: int | None = None,
) -> None:
    # `held` is the gate's third outcome (weekly-gate Step 1b): the approver
    # could not decide — most often because the material was not legible. It is
    # NOT a rejection: folding it into `*_rejected` would record "the human did
    # not understand this" as "the machine was wrong", biasing the very F1
    # precision trend that drives the improvement trigger. Held items are also
    # excluded from `recommendation_total`, so the ratio stays a statement about
    # decided items.
    #
    # Default None, not 0, per the packet's None-vs-0 discipline: a gate session
    # that predates these fields recorded no holds, which is not the same fact
    # as a week with zero holds.
    _append_jsonl(
        metrics,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "gate",
            "week_end": end_date,
            "patches_adopted": patches_adopted,
            "patches_rejected": patches_rejected,
            "patches_held": patches_held,
            "prompt_diffs_adopted": prompt_diffs_adopted,
            "prompt_diffs_held": prompt_diffs_held,
            "insight_adopted": insight_adopted,
            "insight_rejected": insight_rejected,
            "insight_held": insight_held,
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
    docs_scan: Path | None = None,
    skill_selection: Path | None = None,
) -> None:
    reason_codes: list[str] = []

    def add_reason(code: object) -> None:
        # Reason codes are audit-derived and land both in the packet header and
        # in the metrics record that check_improvement later reads. Truthiness
        # is tested on the RAW value: _cell stringifies, so a JSON null would
        # otherwise enter as the literal code "None" and, recurring, fire the
        # P4 improvement trigger. That null is the real defect this guard has
        # caught; the _cell call is the module-wide floor doing its ordinary
        # job on a shell-written value, not a claim that these codes are a
        # threat surface (see _cell's scope paragraph).
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
    # `verdict` is one of the two free-text LLM-authored values §2 renders (the
    # other is the diagnosis heading — see `_title_cell`): the shell greps a
    # line out of the review session's own output. Every other §2 cell is
    # regex-pinned (fix_id), enum (scope), or shell-constructed. So it gets the
    # constrained treatment, not just _cell — it reaches both the table and a
    # `#### ` heading, where `<details>` would fold away every later section in
    # a browser preview (2026-08-08 code review HIGH).
    verdicts: dict[str, str] = {}
    for fid, evts in review_history.items():
        rendered = []
        for e in evts:
            # `_flatten`, NOT `_cell`: the membership test decides whether this
            # is a contract-abiding verdict, and `_cell`'s floor substitutes a
            # space for every non-printable — so `.strip()` then removed it and
            # `APPROVE​` tested equal to `APPROVE`. Measured 2026-08-16:
            # adding the floor turned `UNRECOGNIZED(…)` plus a header reason
            # code into a clean approval, on the one cell the gate's code-scope
            # rows are approved from without reading a diff (security review
            # HIGH, introduced by that same commit). Same discipline as
            # `_vl_cell` below, which compares the unrendered value.
            raw = _flatten(e.get("verdict", "")).strip()
            if raw in KNOWN_VERDICTS:
                rendered.append(raw)
            else:
                add_reason(REVIEW_VERDICT_UNRECOGNIZED)
                # `_unrecognized_verdict` allowlists to [A-Za-z0-9._/+-] and
                # marks the rest U+FFFD, so the raw value is what it wants.
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

    # One id-keyed index over f1_list, shared by the §2 headings and the
    # scope-escalation inference below — two walks with independently-drifting
    # guards is how the packet starts disagreeing with itself.
    #
    # FIRST-wins, matching the fix stage's own lookup (weekly-pipeline.sh:
    # `for f in data['f1']: if f['id'] == ...: break`). Last-wins would let a
    # second `### F1.2.` heading describe the row while the patch implements
    # the first. Duplicates are reported, never silently resolved.
    f1_by_id: dict[str, dict] = {}
    duplicate_ids: list[str] = []
    for item in f1_list:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        fid_key = str(item["id"])
        if fid_key in f1_by_id:
            duplicate_ids.append(fid_key)
            continue
        f1_by_id[fid_key] = item
    if duplicate_ids:
        add_reason(DIAGNOSIS_TITLE_DUPLICATE)

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
            # pipeline's own. Bounded because a separate process writes this
            # file and a long list would push the header out of view; escaped
            # by the same floor every audit value passes.
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

    # Docs-consistency intake (ADR-0093): detection only — any doc edit is a
    # human commit at the Saturday gate. The count is code-owned (computed
    # from the finding rows, never trusted from the JSON's own field).
    docs_findings: list[dict] = []
    docs_scanned = False
    docs_error_count = 0
    if docs_scan is not None:
        ds_data = _load_findings(docs_scan)  # same safe-load contract
        raw = ds_data.get("findings") if ds_data is not None else None
        if isinstance(raw, list) and ds_data is not None:
            docs_scanned = True
            docs_findings = [f for f in raw if isinstance(f, dict)]
            ds_errors = ds_data.get("errors")
            if isinstance(ds_errors, list) and ds_errors:
                # A partially degraded scan is not a clean one (same door as
                # DEADCODE_PARTIAL_PARSE): a git fault or unreadable file
                # means the finding list may be incomplete.
                docs_error_count = len(ds_errors)
                add_reason("DOCSCAN_PARTIAL")
            elif ds_errors is not None and not isinstance(ds_errors, list):
                # Schema drift in the errors field must not read as a clean
                # scan (2026-08-14 code review L2).
                docs_error_count = 1
                add_reason("DOCSCAN_PARTIAL")
        else:
            add_reason("DOCSCAN_UNREADABLE")

    # Never-selected intake (ADR-0097 D5): listing only — the archive move is
    # a human decision at the Saturday gate, made with `adopt-staged
    # --archive-names`. Every count below is computed from the rows, and the
    # exposure floor is re-applied here rather than trusted from the
    # producer's classification: the strict list is the one list a human acts
    # on, so a row this module cannot re-check is dropped and named.
    ns_data: dict | None = None
    ns_floor: int | None = None
    ns_strict: list[dict] = []
    ns_dormant: list[dict] = []
    ns_below_floor: list[dict] = []
    if skill_selection is not None:
        ns_data = _load_findings(skill_selection)  # same safe-load contract
        if ns_data is None:
            add_reason(NEVER_SELECTED_UNREADABLE)
        else:
            raw_floor = ns_data.get("exposure_floor")
            if isinstance(raw_floor, int) and not isinstance(raw_floor, bool) and raw_floor > 0:
                ns_floor = raw_floor
            else:
                # Without a floor there is no criterion the strict rows were
                # selected by, so they are not shown at all. The dormant
                # reading does not depend on it and survives.
                add_reason(NEVER_SELECTED_SCHEMA)

            def _ns_rows(key: str) -> list[dict]:
                raw = ns_data.get(key) if ns_data is not None else None
                return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

            def _ns_exposure(row: dict) -> int | None:
                value = row.get("judged_exposure")
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
                return None

            ns_dormant = _ns_rows("dormant")
            ns_below_floor = _ns_rows("below_floor")
            if ns_floor is not None:
                for row in _ns_rows("strict"):
                    exposure = _ns_exposure(row)
                    if exposure is None or exposure < ns_floor:
                        add_reason(NEVER_SELECTED_SCHEMA)
                        continue
                    ns_strict.append(row)
            ns_reasons = ns_data.get("reasons")
            if isinstance(ns_reasons, list):
                for code in ns_reasons[:8]:
                    if isinstance(code, str) and code in KNOWN_NEVER_SELECTED_REASONS:
                        add_reason(code)
                    elif code:
                        add_reason(NEVER_SELECTED_SCHEMA)
            elif ns_reasons is not None:
                # Same door as DOCSCAN_PARTIAL's non-list `errors`: a reasons
                # field this cannot walk would otherwise open the section
                # while contributing no codes, which reads as a clean run.
                add_reason(NEVER_SELECTED_SCHEMA)

    def _vl(section: str, key: str) -> object:
        if value_layer_data is None:
            return None
        sub = value_layer_data.get(section)
        return sub.get(key) if isinstance(sub, dict) else None

    identity_due = _vl("identity", "due")
    constitution_due = _vl("constitution", "due")

    # Rules layer (ADR-0097 D2). A missing `rules` key means the instrument was
    # not asked for it (no --rules-dir) — not scanned, rendered as nothing.
    # `issues` are rendered, never raised as header reason codes: a rule file
    # that lost its `**Practice:**` heading is a content problem for a human,
    # and putting it on the recurrence channel would burn an unattended
    # improve session drafting a pipeline patch for it.
    rules_raw = value_layer_data.get("rules") if value_layer_data is not None else None
    rules_data = rules_raw if isinstance(rules_raw, dict) else None
    if rules_raw is not None and rules_data is None:
        # Present but unwalkable: without this the section would silently
        # vanish and the week would read as "the layer was never scanned".
        add_reason("VALUE_LAYER_SCHEMA")
    rules_issues: list[dict] = []
    if rules_data is not None:
        raw_issues = rules_data.get("issues")
        if isinstance(raw_issues, list):
            rules_issues = [i for i in raw_issues if isinstance(i, dict)]
    rules_reason = rules_data.get("reason") if rules_data is not None else None
    # Signal-first: a clean, quiet rules layer opens no section of its own. It
    # still rides along whenever §8 renders for another reason, which is where
    # the standing count and mtime are worth their space.
    rules_signal = rules_data is not None and (bool(rules_issues) or rules_reason != "OK")
    identity_event: dict | None = None
    for event in events:
        if event.get("event") == "stage_result" and event.get("stage") == "identity":
            identity_event = event

    # Final-round review bodies, read up front so an unreadable log lands in
    # the header reason list and the metrics record (same rationale as the
    # patch reads above). Earlier rounds stay on disk; their verdicts appear
    # in the history column.
    # (fid, body, rendered path span, code) — code is "" when a body was read.
    # A degraded note carries the fid and the path, because a header reason code
    # alone cannot say WHICH fix lost its review body: the gate would see
    # "something was refused" with no way to recover what without opening the
    # audit log, and REVIEW_LOG_OUTSIDE_RUN_DIR is the tampering signal.
    review_notes: list[tuple[str, str | None, str, str]] = []
    if run_log_dir is not None:
        # The path comes off the event (`log`, weekly-pipeline.sh) and is
        # checked for containment here; it is not rebuilt from fix_id + round.
        # Why that matters is at the producer — the one place a future editor
        # changes the name — and in architecture.md's Rendering discipline
        # (T-PACKET-LOG-PATH-FROM-SHELL).
        run_log_root = run_log_dir.resolve()
        for fid, evts in review_history.items():
            declared = evts[-1].get("log")
            if not isinstance(declared, str) or not declared.strip():
                # No fallback to the old reconstruction, deliberately: leaving
                # one in is how the reconstruction survives. Pre-2026-08-16
                # audit lines lose their review bodies, which costs nothing
                # durable — a packet is consumed at one Saturday gate.
                add_reason(REVIEW_LOG_PATH_MISSING)
                continue
            try:
                log_path = Path(declared).resolve()
            except (OSError, ValueError):
                # `resolve()` raises ValueError on an embedded NUL — see
                # `_safe_read_text` for why that arm is not an OSError.
                log_path = None
            # One claim, one code, one exit: a path that cannot be resolved was
            # never established to be inside run_log_dir either. The REFUSED
            # string is what the note shows — `_path_tokens` is what makes
            # printing an unvetted path safe, and the resolved form does not
            # exist here.
            if log_path is None or not log_path.is_relative_to(run_log_root):
                add_reason(REVIEW_LOG_OUTSIDE_RUN_DIR)
                span = _path_tokens([declared], max_len=_MAX_LOG_PATH_LEN)
                review_notes.append((fid, None, span, REVIEW_LOG_OUTSIDE_RUN_DIR))
                continue
            body = _safe_read_text(log_path)
            code = ""
            if body is None:
                add_reason(REVIEW_LOG_UNREADABLE)
                code = REVIEW_LOG_UNREADABLE
            span = _path_tokens([str(log_path)], max_len=_MAX_LOG_PATH_LEN)
            review_notes.append((fid, body, span, code))
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
            # 2026-07-29 read paths. One of the two places the builder resolves
            # an audit-derived string; the other is the run-log path above, and
            # it names its failure with a reason code because a lost review
            # body is a hole in the packet. This one is silent on purpose: it
            # is the second of three escalation signals, so fail-forward here
            # loses redundancy, not information.
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
    declared_scope = {_patch_name(fid): f.get("scope") for fid, f in f1_by_id.items()}
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
        # Same None-vs-0 discipline for the repo-plane intake (ADR-0093).
        "docs_findings": len(docs_findings) if docs_scanned else None,
        # ADR-0097 D8 reads decisions off record counts, not calendar weeks, so
        # the exit needs a longitudinal series: how many strict candidates the
        # floor surfaced each week, and how many structural issues the rules
        # layer carried. Both None when the intake did not run.
        "never_selected_strict": len(ns_strict) if ns_data is not None else None,
        "rules_issues": len(rules_issues) if rules_data is not None else None,
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
    if docs_findings:
        # Signal-first: quiet weeks add no inventory line and no section.
        lines.append(
            f"- docs consistency: {len(docs_findings)} 件"
            "（検出のみ — doc 修正は人間 commit、§9 参照）"
        )
    if ns_strict:
        # Signal-first: a week whose floor surfaced nobody adds no line. The
        # dormant reading never gets an inventory line — it is not a decision
        # the gate makes, and listing it here would read as one.
        lines.append(
            f"- never-selected skill: {len(ns_strict)} 件"
            "（検出のみ — archive の判断は人間、§10 参照）"
        )
    if rules_issues:
        lines.append(
            f"- rules layer: {len(rules_issues)} 件の構造 issue"
            "（検出のみ — 修正は人間 commit、§8 参照）"
        )
    lines.append("")

    lines.append("## 2. Code fixes (unattended, Verify-passed where noted)")
    lines.append("")
    if fix_results:
        lines.append("| finding | scope | attempts | result | reviewer | patch / reason |")
        lines.append("|---|---|---|---|---|---|")
        # The table answers "what happened to this patch"; the headings answer
        # "what is it for". Both are keyed by fix_id, so they are derived in one
        # pass — a second walk would re-derive the key and drift from it.
        heading_lines: list[str] = []
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
            # `.get("title")` unstringified: _title_cell takes `object` so that a
            # JSON null reaches the named-missing state instead of the literal
            # "None", and a list reaches _cell's join instead of a repr.
            heading_lines.append(
                f"- **{_cell(fid)}** — {_title_cell(f1_by_id.get(fid, {}).get('title'))}"
            )
        # Out of the table because the heading is a sentence — as a cell it
        # would crush the columns the gate scans.
        lines.append("")
        lines.append(
            "**各 finding の診断見出し**（診断段の LLM 出力 — その patch が"
            "何を直すのかの手がかり。承認判断は下の reviewer verdict と、"
            "§3 に本文がある行（prompt scope と昇格分のみ）はその diff で行う。"
            "code scope の行に §3 本文は無く、patch は table のパスに置かれている）:"
        )
        lines.append("")
        lines.extend(heading_lines)
        if duplicate_ids:
            # The row above shows the FIRST heading (the one the fix stage
            # implemented); saying so is what keeps the packet honest about
            # which of the colliding headings the patch belongs to.
            lines.append("")
            lines.append(
                f"**{DIAGNOSIS_TITLE_DUPLICATE}** — findings.md に同じ id の見出しが"
                f"複数ある（{_cell(sorted(set(duplicate_ids)))}）。上の行は fix 段が"
                "実装したのと同じ最初の見出しを示す。重複した側の本文は "
                "findings.md を直接確認する。"
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
        for fid, body, path_span, code in review_notes:
            # Line-initial position: an unsanitised newline here forges a
            # heading directly, so this is the one place _cell's mid-line
            # caveat would bite.
            lines.append(f"#### {_cell(fid)} — {_cell(verdicts.get(fid, '—'))}")
            lines.append("")
            if code == REVIEW_LOG_OUTSIDE_RUN_DIR:
                # Deliberately NOT "確認してください": the path was refused, so
                # telling the operator to open it would hand a hostile string
                # the one action the guard exists to prevent.
                lines.append(
                    f"（{code} — 記録された path {path_span} は run log dir の外を指す。"
                    "読み込みを拒否した。開かず audit を確認）"
                )
            elif body is None:
                lines.append(f"（{code} — {path_span} を直接確認してください）")
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
        if key == "reason":
            # Per-section vocabulary: the rules layer's states and the
            # cadence layers' states are disjoint, and checking each against
            # the other's set would let a drifted value pass as contractual.
            known = KNOWN_RULES_REASONS if section == "rules" else KNOWN_VALUE_LAYER_REASONS
            if value not in known:
                return _unrecognized_verdict(_cell(value))
        return _cell(value)

    if identity_signal or constitution_due is True or rules_signal:
        lines.append("## 8. Value layer cadence (identity / constitution / rules)")
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
        if rules_data is not None:
            # Rendered whenever §8 exists, not only on its own signal: the
            # count and the mtime are the standing maintenance reading the
            # layer got in exchange for losing its generator (ADR-0097 D2),
            # and riding an already-open section costs the packet nothing.
            lines.append("### Rules layer（maintenance reading）")
            lines.append("")
            lines.append(
                "ADR-0097 D2 で `rules-distill` / `rules-stocktake` は退役した。"
                "rules 層に残る所有者はこの決定論的な読み値だけで、**ここでは何も"
                "修正されていない** — 構造 issue の扱い（修正 / 容認 / 保留）は"
                "土曜ゲートの人間 commit で行う。新しい rule は family promotion"
                "（ADR-0097 D7）からのみ入る。"
            )
            lines.append("")
            days_since = _vl("rules", "days_since_newest")
            lines.append(
                f"- files: {_vl_cell('rules', 'files')} 本 / "
                f"newest mtime: {_vl_cell('rules', 'newest_mtime')}"
                + (f"（{_cell(days_since)} 日前）" if days_since is not None else "")
                + f" / state: {_vl_cell('rules', 'reason')}"
            )
            if rules_issues:
                lines.append(
                    f"- 構造 issue: {len(rules_issues)} 件"
                    "（B 層の Practice/Rationale 形式を満たさない）"
                )
                lines.append("")
                lines.append("| rule file | reason |")
                lines.append("|---|---|")
                for issue in sorted(rules_issues, key=lambda i: str(i.get("file", ""))):
                    lines.append(
                        f"| `{_cell(issue.get('file', '?'))}` | {_cell(issue.get('reason', '?'))} |"
                    )
            else:
                lines.append("- 構造 issue: 0 件")
            lines.append("")

    # Section number 9 is reserved for the docs-consistency intake; on clean
    # weeks it is absent (signal-first). It also renders when the scan itself
    # partially failed — a degraded reading must not disappear.
    if docs_findings or docs_error_count:
        lines.append("## 9. Docs consistency (detection only)")
        lines.append("")
        lines.append(
            "週次 docs 整合性スキャン（第 6 決定論 intake、"
            "`scripts/docs_consistency_scan.py`）の読み値。**doc の修正はここでは"
            "行われていない** — 各 finding の判断（修正 / 例外として容認 / 保留）は"
            "土曜ゲートの人間 commit で行う。検査対象は自筆 docs のみ"
            "（`enja_drift` = ADR の en が ja より後に commit / "
            "`broken_link` = 相対リンク断線 / `notes_ref` = ADR から gitignored な "
            "`.notes/` への参照）。"
        )
        lines.append("")
        if docs_error_count:
            lines.append(
                f"**注意 (DOCSCAN_PARTIAL)**: スキャン中に {docs_error_count} 件の"
                "検査エラー（git 失敗・読めないファイル等）— この一覧は不完全の"
                "可能性がある（scan JSON の `errors` を確認）。"
            )
            lines.append("")
        lines.append("| check | file | line | detail |")
        lines.append("|---|---|---|---|")

        def _tick(value: object) -> str:
            # _cell escapes pipes/newlines but not backticks; `file` renders
            # inside a code span and `detail` quotes link targets from doc
            # text, so a stray backtick could open inline markdown mid-cell
            # (2026-08-14 security review LOW — defence-in-depth, the corpus
            # is self-authored). Same neutralization as _md.md_safe.
            return _cell(str(value).replace("`", "'"))

        for f in sorted(
            docs_findings, key=lambda f: (str(f.get("check", "")), str(f.get("file", "")))
        ):
            line_no = f.get("line")
            lines.append(
                f"| {_cell(f.get('check', '?'))} | `{_tick(f.get('file', '?'))}` "
                f"| {_cell(line_no) if line_no is not None else '—'} "
                f"| {_tick(f.get('detail', '?'))} |"
            )
        lines.append("")

    # Section number 10 is reserved for the never-selected exit reading
    # (ADR-0097 D5); a week with nothing in any population and no degraded
    # reading is simply absent (signal-first).
    def _ns(section: str, key: str) -> object:
        if ns_data is None:
            return None
        sub = ns_data.get(section)
        return sub.get(key) if isinstance(sub, dict) else None

    def _ns_cell(section: str, key: str) -> str:
        value = _ns(section, key)
        return "—" if value is None else _cell(value)

    ns_signal = ns_data is not None and bool(
        ns_strict or ns_dormant or ns_below_floor or ns_data.get("reasons")
    )
    if ns_signal and ns_data is not None:
        lines.append("## 10. Never-selected skills (archive candidates — detection only)")
        lines.append("")
        lines.append(
            "選択ログ（`logs/skill-selection-*.jsonl`）全履歴の読み値"
            "（ADR-0097 D5、`core/skill_selection.py`）。**archive はここでは"
            "行われていない** — 候補ごとの判断（archive / 保留）と理由の記録は"
            "土曜ゲートの人間が `adopt-staged --archive-names` で行う。"
            "この節は列挙するだけで、順位も閾値判定も持たない。"
        )
        lines.append("")
        lines.append(
            f"読み取り範囲: {_ns_cell('history', 'files')} 日分のログ"
            f"（{_ns_cell('history', 'first_day')} … {_ns_cell('history', 'last_day')}）、"
            f"judged {_ns_cell('history', 'judged')} / "
            f"records {_ns_cell('history', 'records')}、"
            f"catalog {_ns_cell('catalog', 'size')} skills"
        )
        lines.append("")
        # The caveat is printed BESIDE the candidates, not in a footnote: the
        # behaviour-neutrality argument ("never selected ⇒ never injected ⇒
        # removing it cannot change judged behaviour") holds for judged
        # actions only, and the fail-open path injects the full corpus. Both
        # numbers are printed so the reader can check the claim instead of
        # taking it on faith (the Codex challenge in ADR-0097's Context).
        lines.append(
            "**behaviour-neutrality は judged な action についてのみ成り立つ** — "
            "fail-open した action には全 corpus が注入される。判断材料:"
        )
        lines.append("")
        # The instrument windows by `days` (today − N) or by explicit UTC
        # calendar bounds (`since`/`until`, T-SKILLSEL-REPORT-WINDOW). Naming
        # a bounded window as "直近 N 日" would misreport it by a day and hide
        # a backfill entirely — which is the trap the explicit mode exists to
        # avoid, so the packet must not re-introduce it in its own prose.
        ns_since, ns_until = _ns("window", "since"), _ns("window", "until")
        ns_span = (
            f"{_cell(ns_since)} … {_cell(ns_until)}"
            if ns_since
            else f"直近 {_ns_cell('window', 'days')} 日"
        )
        lines.append(
            f"- {ns_span}の fail-open: "
            f"{_ns_cell('window', 'fail_open')} / "
            f"{_ns_cell('window', 'records')} records"
        )
        full_tokens = _ns("corpus", "full_skill_tokens")
        num_ctx = _ns("corpus", "num_ctx")
        if isinstance(full_tokens, int) and isinstance(num_ctx, int) and full_tokens > 0:
            # A mechanism statement tied to the two printed numbers, not a
            # judgment about archiving: when the corpus exceeds the context
            # window the fail-open path abstains rather than injects (ADR-0081
            # amendment). The reader can see which side of it this week is on.
            relation = (
                f"NUM_CTX {num_ctx:,} を超える — fail-open は注入せず abstain する"
                f"（ADR-0081 amendment）"
                if full_tokens >= num_ctx
                else f"NUM_CTX {num_ctx:,} に収まる — fail-open が起きれば"
                "archive 候補も再注入される"
            )
            lines.append(f"- full corpus {full_tokens:,} tok は {relation}")
        else:
            lines.append(
                "- full corpus のトークン数が読めない"
                "（NEVER_SELECTED_FULL_TOKENS_UNKNOWN）— "
                f"NUM_CTX との比較は不可。NUM_CTX は {_ns_cell('corpus', 'num_ctx')}"
            )
        lines.append("")
        floor_text = _cell(ns_floor) if ns_floor is not None else "—"
        lines.append(f"### Strict（全履歴で 0 回選択 かつ judged exposure ≥ {floor_text}）")
        lines.append("")
        if ns_floor is None:
            lines.append(
                f"（{NEVER_SELECTED_SCHEMA} — exposure floor が読めないため候補一覧を"
                "表示しない。読み値の JSON を直接確認する）"
            )
        elif ns_strict:
            lines.append(
                f"下の {len(ns_strict)} 件は「一度も注入されていない」— 外しても "
                "judged な生成は変わらない。理由の記録は必須（`remove-skill --reason`）。"
            )
            lines.append("")
            lines.append("| skill | judged exposure (history) |")
            lines.append("|---|---|")
            for row in sorted(
                ns_strict,
                key=lambda r: (-int(r.get("judged_exposure", 0)), str(r.get("name", ""))),
            ):
                lines.append(
                    f"| `{_cell(row.get('name', '?'))}` "
                    f"| {_cell(row.get('judged_exposure', '?'))} |"
                )
        else:
            lines.append("（該当なし）")
        if ns_below_floor:
            exposures = [
                r.get("judged_exposure")
                for r in ns_below_floor
                if isinstance(r.get("judged_exposure"), int)
            ]
            highest = max(exposures) if exposures else 0
            lines.append("")
            lines.append(
                f"床未満: 一度も選ばれていない skill が他に {len(ns_below_floor)} 件"
                f"（最大 exposure {highest}）。まだ候補ではない — 提示された回数が"
                "少なすぎて「選ばれていない」が何も意味しない（ADR-0097 D8）。"
            )
        lines.append("")
        lines.append(f"### Dormant（{ns_span}は 0 回、以前は選択あり）")
        lines.append("")
        lines.append(
            "**読み値のみ。archive 候補ではない** — 過去に選択された skill を"
            "外すと judged な生成が変わる。"
        )
        lines.append("")
        if ns_dormant:
            lines.append("| skill | judged exposure (window) | last selected |")
            lines.append("|---|---|---|")
            for row in sorted(ns_dormant, key=lambda r: str(r.get("name", ""))):
                last = row.get("last_selected") or "—"
                lines.append(
                    f"| `{_cell(row.get('name', '?'))}` "
                    f"| {_cell(row.get('window_exposure', '?'))} | {_cell(last)} |"
                )
        else:
            lines.append("（該当なし）")
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
        help="run log dir the recorded review-log paths must resolve inside "
        "— inlines final-round review bodies",
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
    p_build.add_argument(
        "--docs-scan",
        type=Path,
        default=None,
        help="docs_consistency_scan.py JSON — section appears only on findings/errors",
    )
    p_build.add_argument(
        "--skill-selection",
        type=Path,
        default=None,
        help="never-selected reading JSON (ADR-0097 D5) — section appears only on "
        "signal. Produced under the venv, e.g.: uv run python -c 'import json,"
        "pathlib;from contemplative_agent.core.skill_selection import "
        "read_never_selected,never_selected_reading_json;"
        "print(json.dumps(never_selected_reading_json(read_never_selected(...))))'",
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
    # Optional so a session that recorded no holds stays distinguishable from
    # one that held nothing (None vs 0) — the skill's Step 7 always passes them.
    p_gate.add_argument("--patches-held", type=int, default=None)
    p_gate.add_argument("--prompt-diffs-held", type=int, default=None)
    p_gate.add_argument("--insight-held", type=int, default=None)

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
            docs_scan=args.docs_scan,
            skill_selection=args.skill_selection,
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
            patches_held=args.patches_held,
            prompt_diffs_held=args.prompt_diffs_held,
            insight_held=args.insight_held,
        )
        print(f"Gate record appended: {args.metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
