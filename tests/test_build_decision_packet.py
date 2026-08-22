"""Tests for scripts/build_decision_packet.py (+ pipeline_audit.py).

The Saturday decision packet is the single human gate of the unattended
weekly chain (ADR-0085), so its assembly is deliberately code, not LLM:
counts, tables and inclusion rules are structural properties, and the
human must be able to trust that "N patches" means N files on disk and
that prompt-scope diffs appear as full text (human-gate: summarising a
behavior-shaping diff can hide a gate-weakening change).

Fail-forward is the load-bearing fault column: the packet must be produced
— naming what died, with reason codes — for every partial failure of the
chain, because a missing packet is indistinguishable from a chain that
never ran (that ambiguity is what the watchdog checks, not the builder).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_decision_packet as bdp  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
AUDIT_SCRIPT = SCRIPTS / "pipeline_audit.py"

RUN_ID = "weekly-2026-07-24-0900"


def _audit_line(event: str, **fields) -> str:
    return json.dumps(
        {"ts": "2026-07-25T00:00:00+00:00", "run_id": RUN_ID, "event": event, **fields}
    )


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    audit = tmp_path / "weekly-pipeline-audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                _audit_line("stage_result", stage="report", result="ok"),
                _audit_line("stage_result", stage="diagnosis", result="ok"),
                _audit_line(
                    "fix_result",
                    fix_id="F1.2",
                    scope="code",
                    result="patch_ready",
                    attempts="2",
                    patch="patches/weekly-2026-07-24/F1.2.patch",
                ),
                _audit_line(
                    "fix_result",
                    fix_id="F1.3",
                    scope="code",
                    result="failed",
                    attempts="2",
                    reason="VERIFY_FAIL_MAX_ATTEMPTS",
                ),
                _audit_line("review_result", fix_id="F1.2", verdict="APPROVE"),
                # Stale-finding gate: referenced paths got commits after the
                # findings file was written → deterministically skipped, and
                # a skip is not an attempt.
                _audit_line(
                    "fix_result",
                    fix_id="F1.4",
                    scope="code",
                    result="skipped",
                    attempts="0",
                    reason="FINDING_STALE",
                ),
                # A stray event from another run must be ignored.
                json.dumps(
                    {
                        "ts": "2026-07-18T00:00:00+00:00",
                        "run_id": "weekly-2026-07-17-0900",
                        "event": "fix_result",
                        "fix_id": "F1.9",
                        "result": "patch_ready",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            {
                "source": "weekly-2026-07-24-findings.md",
                "counts": {"f1": 3, "f2": 1, "f3": 2},
                "f1": [
                    {"id": "F1.1", "title": "Prompt slot", "scope": "prompt", "paths": []},
                    {"id": "F1.2", "title": "Sweep state", "scope": "code", "paths": []},
                    {"id": "F1.3", "title": "Other bug", "scope": "code", "paths": []},
                ],
            }
        ),
        encoding="utf-8",
    )

    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "F1.2.patch").write_text("--- a/x\n+++ b/x\n", encoding="utf-8")

    prompt_patches = tmp_path / "prompt-patches"
    prompt_patches.mkdir()
    (prompt_patches / "F1.1.patch").write_text(
        "--- a/config/prompts/reply.md\n+conditional block\n", encoding="utf-8"
    )

    insight = tmp_path / "insight-review.md"
    insight.write_text(
        "## 1. skill-a — RECOMMEND: adopt\n\nreason\n\n"
        "## 2. skill-b — RECOMMEND: reject\n\nreason\n",
        encoding="utf-8",
    )

    metrics = tmp_path / "pipeline-metrics.jsonl"
    return {
        "audit": audit,
        "findings": findings,
        "patches": patches,
        "prompt_patches": prompt_patches,
        "insight": insight,
        "metrics": metrics,
        "out": tmp_path / "packet.md",
    }


def _build(paths: dict[str, Path], **overrides) -> str:
    args = {
        "end_date": "2026-07-24",
        "run_id": RUN_ID,
        "audit": paths["audit"],
        "metrics": paths["metrics"],
        "findings": paths["findings"],
        "patches_dir": paths["patches"],
        "prompt_patches_dir": paths["prompt_patches"],
        "insight_review": paths["insight"],
        "improvement": None,
        "out": paths["out"],
    }
    args.update(overrides)
    bdp.build_packet(**args)
    return paths["out"].read_text(encoding="utf-8")


def test_packet_inventory_and_fix_table(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    # 1 作業 1 ゲート: the inventory enumerates counts and scope up front.
    assert "code patch: 1" in text
    assert "prompt diff: 1" in text
    assert "insight: 2" in text
    # Fix table carries the success, the bounded failure, and the stale skip.
    assert "F1.2" in text and "APPROVE" in text
    assert "F1.3" in text and "VERIFY_FAIL_MAX_ATTEMPTS" in text
    assert "F1.4" in text and "FINDING_STALE" in text
    # Cross-run events are excluded.
    assert "F1.9" not in text


def test_fix_table_carries_finding_titles(tmp_path: Path):
    """§2 says WHAT each finding is, not only its ID.

    Without the diagnosis heading the only human-readable material beside
    `F1.2 / APPROVE` is the reviewer's verification prose, which is written
    for the next agent, not for the approver. The heading is already parsed
    into findings.json; this only carries it to the place the decision is
    made.
    """
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "- **F1.2** — Sweep state" in text
    assert "- **F1.3** — Other bug" in text
    # A fix_result with no matching finding says so rather than going blank —
    # a missing heading must not read as "no finding behind this patch".
    assert "- **F1.4** — （DIAGNOSIS_TITLE_MISSING" in text


def test_finding_title_cannot_forge_block_structure(tmp_path: Path):
    """The heading is LLM prose rendered in the builder's own voice.

    Same class as `_path_tokens`: text the builder narrates is text the human
    trusts. Mid-line rendering is the first half of the defence — it stops a
    heading, a fence and a table column.
    """
    paths = _write_inputs(tmp_path)
    findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
    findings["f1"][1]["title"] = "# forged\n## 3. Fake section | extra col"
    paths["findings"].write_text(json.dumps(findings), encoding="utf-8")
    text = _build(paths)
    # A leading # cannot open a heading — the title never starts a line.
    assert not re.search(r"^#+ forged", text, re.MULTILINE)
    # An embedded section heading is flattened onto the one line.
    assert not re.search(r"^## 3\. Fake section", text, re.MULTILINE)
    # A pipe is escaped, so the line cannot grow a column.
    assert "\\| extra col" in text


def test_finding_title_cannot_open_inline_constructs(tmp_path: Path):
    """Mid-line is exactly where inline raw HTML, links and code spans are legal.

    An unclosed `<details>` is closed by nothing and folds every later section
    behind a summary line the heading's author wrote — the failure
    `_unrecognized_verdict` and `_path_tokens` already guard, reachable again
    through the heading (2026-08-15 security review HIGH). A code span is
    equally load-bearing here: it spans line breaks, so one stray backtick
    swallows the rows below it.
    """
    paths = _write_inputs(tmp_path)
    findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
    findings["f1"][1]["title"] = (
        "<details><summary>§3 以降: 変更なし</summary> "
        "![beacon](http://attacker.example/b.png) "
        "[根拠](http://attacker.example/x) `unclosed \u202e\u200b"
    )
    paths["findings"].write_text(json.dumps(findings), encoding="utf-8")
    text = _build(paths)
    # No raw HTML element survives to fold the sections below.
    assert "<details>" not in text and "<summary>" not in text
    # No image or link markup: the builder's narrating voice must not carry a
    # clickable destination the approver did not choose.
    assert "](" not in text
    # No code span: it would run past the line break into the next rows.
    assert "`unclosed" not in text
    # No bidi override / zero-width char to reorder what the approver reads.
    assert "\u202e" not in text and "\u200b" not in text
    # The finding is still named — neutralising is not dropping.
    assert "- **F1.2** —" in text


def test_cell_is_the_control_character_floor_for_every_audit_value():
    """The structural floor neutralises control characters, not each producer.

    This shape has already failed once in this repo: the retired ledger-watch
    intake treated `detail` as the only field needing the pass, and `target`
    reached its section raw. `_cell` is what every call
    sites share, so it is where the class belongs; `_path_tokens`,
    `_unrecognized_verdict` and `_title_cell` keep their own stricter passes as
    defence in depth rather than as the boundary.

    Named individually because a regex narrowed to C0 — the spelling that
    produced the earlier miss — still passes DEL, the C1 block, the bidi
    overrides and the zero-width characters.
    """
    for name, cp in (
        ("ESC", 0x1B),
        ("DEL", 0x7F),
        ("C1 NEL", 0x85),
        ("ZWSP", 0x200B),
        ("RLO", 0x202E),
        ("LS", 0x2028),
    ):
        out = bdp._cell(f"a{chr(cp)}b")
        assert chr(cp) not in out, f"{name} survived _cell"
        assert out == "a b", f"{name}: {out!r}"
    # Structure is still escaped, and the list rule still lives in one place —
    # tuple as well as list, since `_path_tokens`-adjacent producers reach both.
    assert bdp._cell(r"a|b\c") == r"a\|b\\c"
    assert bdp._cell(["x", "y"]) == "x y"
    assert bdp._cell(("x", "y")) == "x y"
    assert bdp._title_cell(("x", "y")) == "x y"


def test_title_keeps_the_visible_marker_the_floor_would_have_erased():
    """`_TITLE_UNSAFE` runs BEFORE `_cell`, and the order is load-bearing.

    `_cell`'s floor substitutes a space. Run first, it leaves the control /
    bidi / zero-width third of `_TITLE_UNSAFE` with nothing to match, and the
    U+FFFD that tells the approver a heading was rewritten becomes an invisible
    space. §2 is the human gate; a tampered heading has to read as one.
    """
    assert bdp._title_cell(f"a{chr(0x202E)}b") == "a�b"
    assert bdp._title_cell("a<details>b") == "a�details�b"
    # The three the ENUMERATED class misses. `_TITLE_UNSAFE` does not list them
    # and the floor would have swallowed each into a space, so the marking is
    # `printable`'s — decided by the same predicate the floor uses, which is
    # why it cannot fall behind it again (cross-model review 2026-08-16).
    for cp in (0x061C, 0x2060, 0xFEFF):
        assert bdp._title_cell(f"a{chr(cp)}b") == "a�b", f"U+{cp:04X} unmarked"
    # The pre-existing behaviour for a value that is not a string is unchanged.
    assert bdp._title_cell(["x", "y"]) == "x y"
    assert bdp.DIAGNOSIS_TITLE_MISSING in bdp._title_cell(None)
    # A line break is FLATTENED to a space, not marked — `_flatten` runs first
    # and it owns the line-break alphabet, so every cell in the packet treats
    # these the same way. Unchanged behaviour, pinned because the marking pass
    # added above is the obvious place to start marking them by accident, and
    # a U+FFFD on every wrapped heading would be noise rather than evidence.
    assert bdp._title_cell(f"a{chr(10)}b") == "a b"
    assert bdp._title_cell(f"a{chr(0x2028)}b") == "a b"


def test_finding_title_is_length_capped(tmp_path: Path):
    """An unbounded heading is a cheap way to push the table out of view."""
    paths = _write_inputs(tmp_path)
    findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
    findings["f1"][1]["title"] = "x" * 900
    paths["findings"].write_text(json.dumps(findings), encoding="utf-8")
    text = _build(paths)
    assert "x" * 900 not in text
    # Elision is visible: a silently truncated heading reads as a complete one.
    assert "…" in text


def test_finding_titles_absent_when_diagnosis_unavailable(tmp_path: Path):
    """Fail-forward: no headings is a named state, never a fabricated one.

    Asserts the positive — three fix rows each say the heading is missing.
    An absence-only assertion would pass on the pre-diff builder, which
    rendered no headings at all, and so would pin nothing.
    """
    paths = _write_inputs(tmp_path)
    text = _build(paths, findings=tmp_path / "absent.json")
    assert "DIAGNOSIS_UNAVAILABLE" in text
    assert text.count("DIAGNOSIS_TITLE_MISSING") == 3
    assert "Sweep state" not in text


def test_finding_title_null_and_list_reach_the_named_states(tmp_path: Path):
    """A JSON null must not render as the literal "None".

    Same lesson `add_reason` already records for reason codes: an unstringified
    value must reach the renderer, or the named-missing state is replaced by a
    fabricated-looking heading.
    """
    paths = _write_inputs(tmp_path)
    findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
    findings["f1"][1]["title"] = None
    findings["f1"][2]["title"] = ["joined", "not repr'd"]
    paths["findings"].write_text(json.dumps(findings), encoding="utf-8")
    text = _build(paths)
    assert "- **F1.2** — （DIAGNOSIS_TITLE_MISSING" in text
    assert "- **F1.3** — joined not repr'd" in text
    assert "['joined'" not in text


def test_duplicate_finding_id_takes_the_first_and_says_so(tmp_path: Path):
    """The fix stage is first-wins; the packet must not be last-wins.

    Otherwise the approver reads a heading describing one finding beside a
    patch implementing another (2026-08-15 security review MEDIUM).
    """
    paths = _write_inputs(tmp_path)
    findings = json.loads(paths["findings"].read_text(encoding="utf-8"))
    findings["f1"].append({"id": "F1.2", "title": "Second heading", "scope": "code"})
    paths["findings"].write_text(json.dumps(findings), encoding="utf-8")
    text = _build(paths)
    assert "- **F1.2** — Sweep state" in text
    assert "Second heading" not in text
    # The collision is named, not silently resolved.
    assert "DIAGNOSIS_TITLE_DUPLICATE" in text


def test_prompt_diff_inlined_full_text(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    # human-gate: behavior-shaping diffs appear as full text, never a summary.
    assert "+conditional block" in text


def test_insight_recommendations_counted_and_inlined(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "RECOMMEND: adopt" in text
    assert "RECOMMEND: reject" in text


def test_metrics_auto_record_appended(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _build(paths)
    records = [
        json.loads(line) for line in paths["metrics"].read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    rec = records[0]
    assert rec["phase"] == "auto"
    assert rec["week_end"] == "2026-07-24"
    assert rec["f1_total"] == 3
    assert rec["f1_code"] == 2
    assert rec["f1_prompt"] == 1
    assert rec["fix_attempted"] == 2
    assert rec["fix_patch_ready"] == 1
    assert rec["verify_fail"] == 1
    assert rec["insight_items"] == 2
    assert rec["improvement_fired"] is False
    assert "VERIFY_FAIL_MAX_ATTEMPTS" in rec["reason_codes"]


def test_fail_forward_missing_findings(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths, findings=tmp_path / "absent.json")
    # The packet still exists and names the failure instead of hiding it.
    assert "DIAGNOSIS_UNAVAILABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["f1_total"] == 0
    assert "DIAGNOSIS_UNAVAILABLE" in rec["reason_codes"]


def test_fail_forward_missing_insight_review(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths, insight_review=tmp_path / "absent.md")
    assert "INSIGHT_REVIEW_UNAVAILABLE" in text


def test_improvement_section_inlined_when_present(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    imp = tmp_path / "improvement.md"
    imp.write_text("--- a/.claude/skills/x\n+tighten step 3\n", encoding="utf-8")
    text = _build(paths, improvement=imp)
    assert "+tighten step 3" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["improvement_fired"] is True


def test_check_improvement_requires_recurrence(tmp_path: Path):
    metrics = tmp_path / "m.jsonl"
    auto = {"phase": "auto", "week_end": "x", "reason_codes": ["FIX_TIMEOUT"]}
    # One record only → not fired (a single bad week is noise, not a pattern).
    metrics.write_text(json.dumps(auto) + "\n", encoding="utf-8")
    assert bdp.check_improvement(metrics) == {"fired": False, "codes": []}
    # Two consecutive weeks sharing a code → fired (P4-shaped threshold).
    metrics.write_text(
        json.dumps(auto)
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "y", "reason_codes": ["FIX_TIMEOUT", "X"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics) == {"fired": True, "codes": ["FIX_TIMEOUT"]}
    # Gate records in between must not break adjacency of auto records.
    metrics.write_text(
        json.dumps(auto)
        + "\n"
        + json.dumps({"phase": "gate", "week_end": "x"})
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "y", "reason_codes": ["OTHER"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics) == {"fired": False, "codes": []}


def test_check_improvement_with_current_codes(tmp_path: Path):
    # The orchestrator calls this BEFORE build (this week's auto record is
    # not yet appended), passing the codes it has collected so far; the
    # comparison is then current-week vs the last recorded week.
    metrics = tmp_path / "m.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "x", "reason_codes": ["FIX_TIMEOUT"]}) + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics, current_codes=["FIX_TIMEOUT", "Y"]) == {
        "fired": True,
        "codes": ["FIX_TIMEOUT"],
    }
    assert bdp.check_improvement(metrics, current_codes=["OTHER"]) == {
        "fired": False,
        "codes": [],
    }
    # No history at all → nothing to recur against.
    empty = tmp_path / "empty.jsonl"
    assert bdp.check_improvement(empty, current_codes=["FIX_TIMEOUT"]) == {
        "fired": False,
        "codes": [],
    }


def test_gate_record_appended(tmp_path: Path):
    metrics = tmp_path / "m.jsonl"
    bdp.append_gate_record(
        metrics,
        end_date="2026-07-24",
        patches_adopted=1,
        patches_rejected=0,
        prompt_diffs_adopted=1,
        insight_adopted=1,
        insight_rejected=1,
        recommendation_matches=2,
        recommendation_total=2,
    )
    rec = json.loads(metrics.read_text(encoding="utf-8").splitlines()[0])
    assert rec["phase"] == "gate"
    assert rec["patches_adopted"] == 1
    assert rec["recommendation_matches"] == 2


def test_pipeline_audit_cli_appends_event(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--log",
            str(log),
            "--run-id",
            RUN_ID,
            "--event",
            "fix_result",
            "--field",
            "fix_id=F1.2",
            "--field",
            "result=patch_ready",
        ],
        check=True,
        capture_output=True,
    )
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["run_id"] == RUN_ID
    assert rec["event"] == "fix_result"
    assert rec["fix_id"] == "F1.2"
    assert "ts" in rec


def test_check_improvement_excludes_same_week_records(tmp_path: Path):
    # A same-week rerun must not compare the run against its own earlier
    # attempt (2026-07-29 review): the baseline is last week, not last record.
    metrics = tmp_path / "m.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "2026-07-17", "reason_codes": ["A"]})
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "2026-07-24", "reason_codes": ["B"]})
        + "\n",
        encoding="utf-8",
    )
    # Without exclusion this would fire on B (self-comparison).
    assert bdp.check_improvement(metrics, current_codes=["B"], end_date="2026-07-24") == {
        "fired": False,
        "codes": [],
    }
    # The true last-week record still participates.
    assert bdp.check_improvement(metrics, current_codes=["A"], end_date="2026-07-24") == {
        "fired": True,
        "codes": ["A"],
    }


def test_unreadable_inputs_degrade_to_reason_codes(tmp_path: Path):
    # Fail-forward survives non-UTF-8 bytes in every upstream artifact
    # (2026-07-29 review, CRITICAL: UnicodeDecodeError escaped every handler).
    paths = _write_inputs(tmp_path)
    paths["audit"].write_bytes(b"\xff\xfe garbage")
    bad_insight = tmp_path / "bad-insight.md"
    bad_insight.write_bytes(b"\x80\x81")
    bad_findings = tmp_path / "bad-findings.json"
    bad_findings.write_bytes(b"\xff{}")
    text = _build(paths, insight_review=bad_insight, findings=bad_findings)
    assert "AUDIT_UNREADABLE" in text
    assert "INSIGHT_REVIEW_UNREADABLE" in text
    assert "DIAGNOSIS_UNAVAILABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "AUDIT_UNREADABLE" in rec["reason_codes"]


def test_recommend_count_is_heading_anchored(tmp_path: Path):
    # A stray "RECOMMEND:" in body prose must not inflate the inventory count.
    paths = _write_inputs(tmp_path)
    paths["insight"].write_text(
        "## 1. skill-a — RECOMMEND: adopt\n\n"
        "the phrase RECOMMEND: reject appears in prose here\n\n"
        "## 2. skill-b — RECOMMEND: reject\n\nreason\n",
        encoding="utf-8",
    )
    _build(paths)
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["insight_items"] == 2


def _reviewed_fix_result() -> str:
    """The `fix_result` line a reviewed fix produces — one owner, two callers.

    Both `_write_review_loop_audit` and the declared-path test need a
    patch_ready F1.2 row to hang review events off; spelling it twice would
    give the fixture shape two owners, so a change to the scope or patch
    contract could update one test and silently leave the other.
    """
    return _audit_line(
        "fix_result",
        fix_id="F1.2",
        scope="code",
        result="patch_ready",
        attempts="2",
        patch="patches/weekly-2026-07-24/F1.2.patch",
    )


def _write_review_loop_audit(paths: dict[str, Path], log_dir: Path | None = None) -> None:
    """Audit shape produced by the review loop (T-PIPELINE-REVIEWLOOP):
    one review_result per round, in chronological order.

    ``log_dir`` writes the ``log`` field the shell records at
    weekly-pipeline.sh:810 — the path it just wrote, which the builder opens
    instead of rebuilding (T-PACKET-LOG-PATH-FROM-SHELL). Omitting it produces
    a pre-2026-08-16 line, which is a fixture for the degradation tests rather
    than a shape any current producer emits.
    """

    def _review(rnd: str, verdict: str) -> str:
        fields = {"fix_id": "F1.2", "round": rnd, "verdict": verdict}
        if log_dir is not None:
            fields["log"] = str(log_dir / f"fix-F1.2-review{rnd}.log")
        return _audit_line("review_result", **fields)

    paths["audit"].write_text(
        "\n".join(
            [
                _reviewed_fix_result(),
                _review("1", "CONCERNS"),
                _review("2", "APPROVE"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_reviewer_column_shows_round_history(tmp_path: Path):
    # 2026-08-01 gate failure: a loop whose final verdict is APPROVE must not
    # erase the CONCERNS history — that reproduces the very information loss
    # the loop exists to fix.
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    text = _build(paths)
    assert "CONCERNS→APPROVE" in text


def test_review_notes_inline_final_round_body(tmp_path: Path):
    # The human gate reads the reviewer's reasoning, not a 4-char verdict
    # (07-31 F1.1: three real defects hidden behind "CONCERNS").
    paths = _write_inputs(tmp_path)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    _write_review_loop_audit(paths, log_dir=run_logs)
    (run_logs / "fix-F1.2-review1.log").write_text(
        "VERDICT: CONCERNS\n- round-1 concern about the regression test\n", encoding="utf-8"
    )
    (run_logs / "fix-F1.2-review2.log").write_text(
        "VERDICT: APPROVE\n- round-2 concerns addressed\n", encoding="utf-8"
    )
    text = _build(paths, run_log_dir=run_logs)
    assert "Review notes" in text
    # Final round full text is inlined; earlier rounds stay on disk (their
    # verdicts appear in the history column).
    assert "round-2 concerns addressed" in text
    assert "round-1 concern about the regression test" not in text


def test_review_notes_absent_without_run_log_dir(tmp_path: Path):
    # Backward compatibility: an old-style invocation (no --run-log-dir)
    # renders the same packet as before the loop existed.
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    text = _build(paths)
    assert "Review notes" not in text
    assert "REVIEW_LOG_UNREADABLE" not in text


def test_review_note_reads_the_path_the_shell_declared(tmp_path: Path):
    """The builder opens the recorded path, it does not rebuild the name.

    The name here is one no reconstruction would ever produce, so this fails
    the moment anyone derives the filename from `fix_id` and `round` again.
    That reconstruction is the defect: the shell's rule (`/`→`_`) and the
    builder's were separate, so a `fix_id` outside the builder's allowlist made
    the two disagree and the review body left the packet in silence — with the
    packet still produced, so the watchdog saw nothing
    (T-PACKET-LOG-PATH-FROM-SHELL).
    """
    paths = _write_inputs(tmp_path)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    declared = run_logs / "r2-arbitrary-name.log"
    declared.write_text("VERDICT: APPROVE\n- body behind an unguessable name\n", encoding="utf-8")
    paths["audit"].write_text(
        _reviewed_fix_result()
        + "\n"
        + _audit_line(
            "review_result", fix_id="F1.2", round="2", verdict="APPROVE", log=str(declared)
        )
        + "\n",
        encoding="utf-8",
    )
    text = _build(paths, run_log_dir=run_logs)
    assert "body behind an unguessable name" in text
    assert "REVIEW_LOG_UNREADABLE" not in text


def test_review_result_without_a_log_field_degrades_to_reason_code(tmp_path: Path):
    """A pre-2026-08-16 audit line names its gap instead of being rebuilt.

    Deliberately no fallback to reconstruction: leaving one in would keep the
    reconstruction alive, which is the whole point of the change. Past weeks'
    packets are disposable (consumed at one Saturday gate), so the cost of
    dropping them is a reason code, and the verdict history — the part §2's
    code-scope rows are approved from — is untouched.
    """
    paths = _write_inputs(tmp_path)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    _write_review_loop_audit(paths)  # no log_dir → no `log` field
    (run_logs / "fix-F1.2-review2.log").write_text("VERDICT: APPROVE\n", encoding="utf-8")
    text = _build(paths, run_log_dir=run_logs)
    assert "REVIEW_LOG_PATH_MISSING" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "REVIEW_LOG_PATH_MISSING" in rec["reason_codes"]
    # No note, and specifically not one rebuilt from fix_id + round: the file
    # that a reconstruction would have found is sitting on disk right there.
    assert "Review notes" not in text
    assert "CONCERNS→APPROVE" in text  # the verdict history still renders


def test_review_log_unreadable_degrades_to_reason_code(tmp_path: Path):
    # Fail-forward: a reviewed fix whose log vanished still enters the packet,
    # with the gap named instead of hidden.
    paths = _write_inputs(tmp_path)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()  # review2 log deliberately absent
    _write_review_loop_audit(paths, log_dir=run_logs)
    text = _build(paths, run_log_dir=run_logs)
    assert "REVIEW_LOG_UNREADABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "REVIEW_LOG_UNREADABLE" in rec["reason_codes"]


def test_legacy_single_review_event_without_round(tmp_path: Path):
    # Pre-loop audit lines carry no round field; the reviewer column must
    # render them unchanged (the 07-24 packet is replayable).
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    rows = [line for line in text.splitlines() if line.startswith("| F1.2 ")]
    assert len(rows) == 1
    assert "APPROVE" in rows[0]
    assert "→" not in rows[0]


def test_review_body_with_backtick_fence_stays_contained(tmp_path: Path):
    # LLM review prose routinely quotes code in its own ``` fences; the
    # packet's fence must outrun the body's longest backtick run or the rest
    # of the review spills into raw packet Markdown (2026-08-01 review, HIGH).
    paths = _write_inputs(tmp_path)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    _write_review_loop_audit(paths, log_dir=run_logs)
    (run_logs / "fix-F1.2-review1.log").write_text("VERDICT: CONCERNS\n", encoding="utf-8")
    (run_logs / "fix-F1.2-review2.log").write_text(
        "VERDICT: APPROVE\n- quoted repro:\n```python\nassert x\n```\ntail line\n",
        encoding="utf-8",
    )
    text = _build(paths, run_log_dir=run_logs)
    start = text.index("#### F1.2")
    section = text[start : text.index("## 3.")]
    # The body (including its inner fence) sits inside a longer outer fence.
    assert "````text" in section
    assert section.count("````") == 2
    assert "tail line" in section


def test_pipeline_audit_rejects_reserved_keys(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--log",
            str(log),
            "--run-id",
            RUN_ID,
            "--event",
            "x",
            "--field",
            "run_id=spoofed",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert not log.exists()


# --- Dead-code intake (T-DEADCODE-INTAKE) --------------------------------
# Signal-first: the section and its inventory line exist only on weeks with
# candidates; a quiet week is silent in the packet but still countable in
# the metrics record (zero vs scan-failure stays distinguishable via reason
# codes). Deletion is never authored here — detection only.


def _dead_code_json(tmp_path: Path, candidates: list[dict]) -> Path:
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "report_prefixes": ["src/", "scripts/"],
                "count": len(candidates),
                "candidates": candidates,
                "unparsed_lines": 0,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_dead_code_section_rendered_when_candidates_exist(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    dc = _dead_code_json(
        tmp_path,
        [
            {
                "file": "src/contemplative_agent/core/foo.py",
                "line": 12,
                "message": "unused function 'orphan'",
                "confidence": 60,
            }
        ],
    )
    text = _build(paths, dead_code=dc)
    assert "dead code candidate: 1" in text
    assert "## 5. Dead code candidates" in text
    assert "unused function 'orphan'" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 1


def test_dead_code_zero_week_is_silent(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    dc = _dead_code_json(tmp_path, [])
    text = _build(paths, dead_code=dc)
    assert "Dead code candidates" not in text
    assert "dead code candidate:" not in text
    # The renumbered fixed headings hold on a quiet week (5 is a gap).
    assert "## 6. Pipeline metrics" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    # Scanned clean is 0 — distinguishable from the not-scanned None below.
    assert rec["dead_code_candidates"] == 0


def test_dead_code_absent_arg_keeps_packet_unchanged(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "Dead code candidates" not in text
    assert "DEADCODE_UNREADABLE" not in text
    assert "dead code —(not scanned)" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    # Not scanned must never read as "scanned clean" (2026-08-07 review).
    assert rec["dead_code_candidates"] is None


def test_dead_code_partial_scan_stderr_is_surfaced(tmp_path: Path):
    # F-DC-7 downstream: vulture skipped input files (stderr) — the gate
    # must see the coverage gap, not a clean-looking table.
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 1,
                "candidates": [
                    {
                        "file": "src/contemplative_agent/core/foo.py",
                        "line": 12,
                        "message": "unused function 'orphan'",
                        "confidence": 60,
                    }
                ],
                "unparsed_lines": 0,
                "stderr_lines": 2,
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "DEADCODE_PARTIAL_SCAN" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_PARTIAL_SCAN" in rec["reason_codes"]


def test_dead_code_non_dict_rows_are_dropped_not_fatal(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps({"tool": "vulture", "candidates": ["oops", 42]}),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "Dead code candidates" not in text  # nothing renderable survived
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 0


def test_dead_code_unreadable_degrades_to_reason_code(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "dead-code.json"
    bad.write_bytes(b"\xff not json")
    text = _build(paths, dead_code=bad)
    assert "DEADCODE_UNREADABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_UNREADABLE" in rec["reason_codes"]


def test_dead_code_partial_parse_is_surfaced_not_silent(tmp_path: Path):
    # A vulture format drift that breaks only some lines must degrade loudly:
    # reason code in the header + metrics, caveat in the section (codex P2).
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 1,
                "candidates": [
                    {
                        "file": "src/contemplative_agent/core/foo.py",
                        "line": 12,
                        "message": "unused function 'orphan'",
                        "confidence": 60,
                    }
                ],
                "unparsed_lines": 3,
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "DEADCODE_PARTIAL_PARSE" in text
    assert "3 行が契約形式に一致せず未解釈" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_PARTIAL_PARSE" in rec["reason_codes"]


def test_dead_code_count_is_code_owned_not_json_claimed(tmp_path: Path):
    # The human-facing count is computed from the candidate rows, never
    # trusted from the JSON's own "count" field.
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 99,
                "candidates": [
                    {
                        "file": "scripts/old_tool.py",
                        "line": 3,
                        "message": "unused variable 'LEGACY_FLAG'",
                        "confidence": 100,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "dead code candidate: 1" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 1


# --- scope escalation (2026-07-29 security review C4) -----------------------
#
# The shell moves a code-scope patch that touched a path outside
# ^(src|scripts|tests)/ into the full-text gate. That guard worked on the
# 2026-08-07 run, but the packet said nothing about it: the escalated patches
# appeared under §3 with no reason, because the builder harvested reason codes
# only from `fix_result.reason` and the escalation is its own event type. A
# guard whose effect is visible but whose cause is not invites the next reader
# to "fix" the scope classifier (the escalation counterpart of ADR-0075's
# no-silent-fallback rule).


def _escalate(paths: dict[str, Path], fix_id: str = "F1.2", files: object = "docs/x.md") -> None:
    """Record an escalation for ``fix_id`` and move its patch to the prompt dir.

    Mirrors the exporter: escalation redirects the output dir, so the patch
    exists in the prompt dir and NOT in the code dir.
    """
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id=fix_id, files=files) + "\n")
    name = f"{fix_id.replace('/', '_')}.patch"
    (paths["patches"] / name).unlink(missing_ok=True)
    (paths["prompt_patches"] / name).write_text(
        "--- a/src/x.py\n+++ b/src/x.py\n", encoding="utf-8"
    )


def test_scope_escalation_reaches_the_header_reason_codes(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths)
    text = _build(paths)
    # Recomputed from the event type, not read from the shell's REASONS var:
    # the builder stays an independent replay of the audit log.
    assert "SCOPE_ESCALATED" in text.split("## 1.")[0]
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "SCOPE_ESCALATED" in rec["reason_codes"]


def test_scope_escalation_marks_the_fix_table_row(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2")
    text = _build(paths)
    row = next(ln for ln in text.splitlines() if ln.startswith("| F1.2 "))
    # The declared scope stays visible (it is what the classifier said); the
    # marker says the export overrode it.
    assert "code" in row and "SCOPE_ESCALATED" in row
    # An unescalated row keeps its plain scope cell.
    assert "SCOPE_ESCALATED" not in next(ln for ln in text.splitlines() if ln.startswith("| F1.3 "))


def test_escalated_prompt_patch_names_its_cause(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/CODEMAPS/architecture.md")
    text = _build(paths)
    section = text.split("## 3.")[1].split("## 4.")[0]
    body = section.split("### F1.2.patch")[1]
    # Why this code-scope patch is in the full-text section, and which path
    # put it there — answerable from the packet alone.
    assert "SCOPE_ESCALATED" in body
    assert "触れたパス: `docs/CODEMAPS/architecture.md`" in body
    # The un-escalated prompt diff carries no such note.
    assert "SCOPE_ESCALATED" not in section.split("### F1.1.patch")[1].split("###")[0]


def test_inventory_counts_escalated_diffs(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths)
    text = _build(paths)
    inventory = text.split("## 1.")[1].split("## 2.")[0]
    assert "prompt diff: 2" in inventory
    assert "うち 1 件" in inventory


def test_escalated_patch_leaves_the_code_patch_count(tmp_path: Path):
    # The gate approves code patches in Step 2 WITHOUT reading their diffs;
    # an escalated patch is not in patches_dir and must not be counted as an
    # apply target, or the escalation's whole point is lost one step earlier.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2")  # the only patch_ready code fix
    inventory = _build(paths).split("## 1.")[1].split("## 2.")[0]
    assert "code patch: 0 件" in inventory
    assert "+1 件は §3 の全文ゲートへ昇格" in inventory


def test_escalation_inferred_from_patch_location_when_event_is_lost(tmp_path: Path):
    # The shell's audit append is best-effort. Losing that one line must not
    # erase the escalation from all three surfaces — a code-scope fix whose
    # patch landed in the prompt dir is an escalation by definition.
    paths = _write_inputs(tmp_path)
    audit_lines = (
        paths["audit"]
        .read_text(encoding="utf-8")
        .replace(
            "patches/weekly-2026-07-24/F1.2.patch",
            str(paths["prompt_patches"] / "F1.2.patch"),
        )
    )
    paths["audit"].write_text(audit_lines, encoding="utf-8")
    text = _build(paths)
    # Named as inferred, so the audit-log gap is itself visible.
    assert "SCOPE_ESCALATED_INFERRED" in text.split("## 1.")[0]
    assert "SCOPE_ESCALATED" in next(ln for ln in text.splitlines() if ln.startswith("| F1.2 "))
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "SCOPE_ESCALATED_INFERRED" in rec["reason_codes"]


def test_recorded_escalation_does_not_also_report_as_inferred(tmp_path: Path):
    # Both signals firing for the same fix is the normal case, not a gap.
    paths = _write_inputs(tmp_path)
    audit_lines = (
        paths["audit"]
        .read_text(encoding="utf-8")
        .replace(
            "patches/weekly-2026-07-24/F1.2.patch",
            str(paths["prompt_patches"] / "F1.2.patch"),
        )
    )
    paths["audit"].write_text(audit_lines, encoding="utf-8")
    _escalate(paths, fix_id="F1.2", files="docs/x.md")
    text = _build(paths)
    assert "SCOPE_ESCALATED_INFERRED" not in text
    assert "SCOPE_ESCALATED" in text


def test_no_escalation_leaves_the_packet_unchanged(tmp_path: Path):
    # Signal-first: a quiet week adds no reason code, no marker, no note.
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "SCOPE_ESCALATED" not in text
    assert "うち" not in text.split("## 1.")[1].split("## 2.")[0]


# --- fault column ----------------------------------------------------------


def test_escalation_without_files_field_still_surfaces(tmp_path: Path):
    # A truncated/older event shape must not hide the escalation itself —
    # the reason code and the marker are what the human acts on.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2") + "\n")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text
    assert "（パス不明）" in text


def test_escalated_paths_cannot_forge_packet_structure(tmp_path: Path):
    # The path list is chosen by the fix session (an LLM with write access in
    # the worktree); a crafted filename must not be able to forge a section
    # heading. The shell collapses newlines, but the builder must not depend
    # on that — and splitlines() is the alphabet every consumer splits on.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/a.md ## 5. Dead code candidates")
    text = _build(paths)
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())


def test_escalated_paths_cannot_write_prose_or_html(tmp_path: Path):
    # git passes every printable ASCII byte in a filename through unquoted, so
    # a raw render would let the fix session write reassurance in the builder's
    # own voice, or open an HTML <details> that folds away the rest of the
    # packet in a browser preview. Only the path allowlist survives.
    paths = _write_inputs(tmp_path)
    _escalate(
        paths,
        fix_id="F1.2",
        files="docs/x.md).　確認済み・対応不要。(was: y.md <details> *bold*",
    )
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    assert "確認済み" not in line and "<details>" not in line
    assert "`docs/x.md" in line  # the real path is still legible to the human


def test_escalated_path_list_is_bounded(tmp_path: Path):
    # An unbounded list is a cheap way to push the surrounding explanation out
    # of the reader's view in the packet's most decision-relevant sentence.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files=" ".join(f"docs/f{i}.md" for i in range(50)))
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    # "断片", not "件": git does not quote spaces, so one filename can split
    # into many tokens — calling them files would be a misleading count.
    assert "ほか 30 断片" in line
    assert "docs/f49.md" not in line


def test_unresolvable_patch_path_does_not_kill_the_packet(tmp_path: Path):
    # The inferred-escalation check is the builder's only filesystem I/O on an
    # audit-derived string. resolve() raises ValueError (not OSError) on an
    # embedded NUL — fail-forward means losing that signal, not the packet.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.6",
                scope="code",
                result="patch_ready",
                attempts="1",
                patch="pat\x00ches/F1.6.patch",
            )
            + "\n"
        )
    assert "F1.6" in _build(paths)


def _declare_review_log(paths: dict[str, Path], tmp_path: Path, log: str) -> Path:
    """Append one `review_result` whose recorded `log` is the value under test.

    Everything except that value is held constant, so each caller's name says
    the whole difference between it and its siblings — the same shape
    `_escalate` above uses for the sibling event.
    """
    run_logs = tmp_path / "runlog"
    run_logs.mkdir(exist_ok=True)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line("review_result", fix_id="F1.3", round="1", verdict="APPROVE", log=log)
            + "\n"
        )
    return run_logs


def test_a_declared_log_path_cannot_forge_a_section_in_the_unreadable_note(tmp_path: Path):
    """The floor that had to move when the reconstruction went away.

    `_log_segment` used to make this unreachable from the BUILD side — the
    builder assembled the name itself, so the `REVIEW_LOG_UNREADABLE` note
    could interpolate it raw. Containment replaced that, and containment only
    bounds WHERE the builder reads: a path INSIDE `run_log_dir` whose filename
    carries a newline passes it, misses on disk, and reaches the note. So the
    guard is now on the render side (`_path_tokens`), and this is the test that
    says so.

    One test where there were two: the round and the fix_id used to reach the
    filename through separate call sites, and 2026-08-08 hardened only one of
    them. One declared field, one door.
    """
    paths = _write_inputs(tmp_path)
    forged = "\n\n## 5. Dead code candidates\n\n| `src/x.py` | 1 | unused | 100% |"
    run_logs = _declare_review_log(paths, tmp_path, f"{tmp_path}/runlog/fix-F1.3-review1{forged}")
    text = _build(paths, run_log_dir=run_logs)
    # Inside the run-log dir, so containment passes and the note really fires —
    # the attack does not need the read to succeed, it needs it to fail.
    assert "REVIEW_LOG_UNREADABLE" in text
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())
    assert not any(ln.startswith("|") and "src/x.py" in ln for ln in text.splitlines())


def test_a_declared_log_path_outside_the_run_log_dir_is_not_read(tmp_path: Path):
    """Containment is the guard that replaced the filename allowlist.

    Stronger than the version it replaces: that one declared a traversal and
    relied on the read MISSING, so an absent containment check would still have
    passed it. Here the target exists and is readable, so the only thing
    keeping it out of a document a human approves from is the check itself.
    """
    paths = _write_inputs(tmp_path)
    (tmp_path / "secret.log").write_text("SUPER SECRET", encoding="utf-8")
    run_logs = _declare_review_log(paths, tmp_path, f"{tmp_path}/runlog/../secret.log")
    text = _build(paths, run_log_dir=run_logs)
    assert "SUPER SECRET" not in text
    assert "REVIEW_LOG_OUTSIDE_RUN_DIR" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "REVIEW_LOG_OUTSIDE_RUN_DIR" in rec["reason_codes"]
    # A header code alone cannot say WHICH fix lost its body: the note names the
    # fid and the refused path, so the tampering signal is actionable at the
    # gate instead of sending the approver to the audit log.
    note = text.split("#### F1.3")[1].split("####")[0]
    assert "REVIEW_LOG_OUTSIDE_RUN_DIR" in note
    assert "secret.log" in note
    assert "確認してください" not in note  # never invite opening a refused path


def test_a_refused_log_path_cannot_forge_a_section_in_its_own_note(tmp_path: Path):
    """The sink the containment note opened: the REFUSED string gets printed.

    Naming the refused path is what makes the tampering signal actionable, but
    it also puts a string that failed every check into the document a human
    approves from — and unlike the unreadable-note path, this one was never
    established to be inside `run_log_dir`. `_path_tokens` is the whole reason
    printing it is safe.
    """
    paths = _write_inputs(tmp_path)
    forged = "\n\n## 5. Dead code candidates\n\n| `src/x.py` | 1 | unused | 100% |"
    run_logs = _declare_review_log(paths, tmp_path, f"{tmp_path}/elsewhere/log{forged}")
    text = _build(paths, run_log_dir=run_logs)
    assert "REVIEW_LOG_OUTSIDE_RUN_DIR" in text
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())
    assert not any(ln.startswith("|") and "src/x.py" in ln for ln in text.splitlines())


def test_an_unresolvable_declared_log_path_is_refused_not_opened(tmp_path: Path):
    """An embedded NUL raises out of `resolve()`, which is not an OSError.

    Same gap that took the read paths down in 2026-07-29, arriving here from a
    new direction now that the builder resolves an audit-declared string. It is
    refused under the containment code rather than its own: the claim that code
    makes — "this path was not established to be inside run_log_dir" — is
    exactly true of a path that cannot be resolved at all.
    """
    paths = _write_inputs(tmp_path)
    run_logs = _declare_review_log(paths, tmp_path, f"{tmp_path}/runlog/fix-F1.3-rev\x00iew1.log")
    text = _build(paths, run_log_dir=run_logs)  # must not raise
    assert "REVIEW_LOG_OUTSIDE_RUN_DIR" in text


def test_no_read_can_take_the_packet_down(tmp_path: Path):
    """The read floor, asserted independently of the containment guard.

    Two floors, two claims: containment says the builder never OPENS a path it
    did not establish as inside `run_log_dir`, this says no read takes the
    builder down whoever handed it the path. Removing either must fail a test.
    Only the ValueError arm is new — an embedded NUL is
    neither OSError nor UnicodeDecodeError, so it walked past fail-forward and
    out of `build_packet`, and a missing packet is the watchdog's finding rather
    than the builder's.
    """
    assert bdp._safe_read_text(Path("a\x00b")) is None  # ValueError, not OSError
    assert bdp._safe_read_text(tmp_path / "nope") is None  # OSError, the anchor


def test_escalation_inferred_from_declared_scope_without_any_audit_event(tmp_path: Path):
    # A sustained audit-write outage takes out both event-based signals at
    # once. findings.json + the exported filename still reconstruct it.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    (paths["prompt_patches"] / "F1.2.patch").write_text(  # F1.2 is declared code
        "--- a/src/x.py\n", encoding="utf-8"
    )
    text = _build(paths)
    assert "SCOPE_ESCALATED_INFERRED" in text
    body = text.split("### F1.2.patch")[1]
    assert "SCOPE_ESCALATED" in body


def test_declared_prompt_scope_patch_is_not_inferred_as_escalated(tmp_path: Path):
    # F1.1 is declared prompt scope — an ordinary prompt diff, not an override.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    assert "SCOPE_ESCALATED" not in _build(paths)


def test_inferred_escalation_does_not_assert_paths_it_never_saw(tmp_path: Path):
    # The inferred branch observed only the patch's output dir. Repeating the
    # observed branch's sentence would assert a cause the builder never saw —
    # the unearned certainty this whole change exists to remove.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    body = _build(paths).split("### F1.2.patch")[1].split("```")[0]
    assert "SCOPE_ESCALATED_INFERRED" in body
    assert "の外に触れた" not in body  # no fabricated cause
    assert "触れたパス:" not in body  # no path slot reused for a non-path


def test_reviewer_verdict_is_constrained_to_its_contract(tmp_path: Path):
    # `verdict` is the one free-text LLM-authored value in the packet: the
    # shell greps a line out of the review session's own output. Left on _cell
    # alone it could carry <details> into the §2 table AND the #### heading,
    # folding away every later section in a browser preview.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "review_result",
                fix_id="F1.3",
                verdict="APPROVE <details><summary>ok</summary>",
            )
            + "\n"
        )
    text = _build(paths)
    assert "<details>" not in text
    assert "UNRECOGNIZED(" in text
    # Breaking the reviewer contract is itself reportable, not silently shown.
    assert "REVIEW_VERDICT_UNRECOGNIZED" in text.split("## 1.")[0]
    # A contract-conforming verdict is untouched.
    assert "| F1.2 " in text and "APPROVE |" in text


def test_an_invisible_suffix_does_not_launder_a_verdict_into_the_contract(tmp_path: Path):
    """The membership test reads the value, never the neutralised rendering.

    Introduced and caught within one commit (2026-08-16 security review HIGH):
    making `_cell` the control-character floor put it UPSTREAM of this check,
    where its space substitution plus `.strip()` turned `APPROVE<invisible>`
    into `APPROVE` — a reportable contract break rendered as a clean approval,
    with the header reason code gone too.

    That cell is load-bearing at the gate: §2 tells the approver that
    code-scope rows carry no §3 diff body and are applied in Step 2 without
    reading diffs, so the reviewer column IS the material the decision rests
    on. Visible characters (the sibling test above) cannot see this — the
    regression is only reachable through characters that render as nothing.

    One case per build directory rather than one build with five events: a
    laundered verdict is INVISIBLE in the output, so a shared build would let
    one surviving `UNRECOGNIZED(` satisfy the assertion for all five.
    """
    for cp in (0x200B, 0x202E, 0x7F, 0xFEFF, 0x00AD):
        case = tmp_path / f"u{cp:04x}"
        case.mkdir()
        paths = _write_inputs(case)
        with paths["audit"].open("a", encoding="utf-8") as fh:
            fh.write(
                _audit_line("review_result", fix_id="F1.3", verdict=f"APPROVE{chr(cp)}") + "\n"
            )
        text = _build(paths)
        assert "UNRECOGNIZED(" in text, f"U+{cp:04X} laundered into a clean verdict"
        assert "REVIEW_VERDICT_UNRECOGNIZED" in text.split("## 1.")[0], f"U+{cp:04X}"
        assert chr(cp) not in text, f"U+{cp:04X} reached the packet"


def test_designed_escalation_does_not_fire_the_improvement_trigger(tmp_path: Path):
    # A docs-touching fix two weeks running is routine. P4 exists to catch
    # faults; spending an unattended session "improving" a guard that worked
    # as designed is the wrong trigger. An audit-log gap still counts.
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "2026-07-17", "reason_codes": ["SCOPE_ESCALATED"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics, current_codes=["SCOPE_ESCALATED"])["fired"] is False
    assert (
        bdp.check_improvement(
            metrics, current_codes=["SCOPE_ESCALATED", "SCOPE_ESCALATED_INFERRED"]
        )["fired"]
        is False
    )  # INFERRED not in the baseline yet
    metrics.write_text(
        json.dumps(
            {
                "phase": "auto",
                "week_end": "2026-07-17",
                "reason_codes": ["SCOPE_ESCALATED", "SCOPE_ESCALATED_INFERRED"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fired = bdp.check_improvement(metrics, current_codes=["SCOPE_ESCALATED_INFERRED"])
    assert fired["fired"] is True and fired["codes"] == ["SCOPE_ESCALATED_INFERRED"]


def test_null_reason_does_not_become_a_none_reason_code(tmp_path: Path):
    # _cell stringifies, so testing truthiness after it would let a JSON null
    # enter as the literal code "None" — and, recurring, fire P4.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("fix_result", fix_id="F1.5", result="failed", reason=None) + "\n")
    _build(paths)
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "None" not in rec["reason_codes"]


def test_truncated_escalation_path_is_marked_as_elided(tmp_path: Path):
    # A truncated path that reads as complete defeats the note's purpose.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/" + "a" * 200 + ".md")
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    assert "…`" in line


def test_table_cells_escape_pipes(tmp_path: Path):
    # The §2 table's own values are audit-derived too: an unescaped `|` in any
    # of them silently shifts every later column. Pinned on `patch`, the one
    # cell carrying a filesystem path.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.7",
                scope="code",
                result="patch_ready",
                attempts="1",
                patch="patches/a|b.patch",
            )
            + "\n"
        )
    row = next(ln for ln in _build(paths).splitlines() if ln.startswith("| F1.7 "))
    assert "a\\|b.patch" in row
    # No unescaped `|` outside the six column delimiters.
    assert re.sub(r"\\\|", "", row).count("|") == 7


def test_escalation_without_exported_patch_still_surfaces(tmp_path: Path):
    # Escalation moves the output dir; the export can still fail (EMPTY_DIFF).
    # No §3 body exists to annotate, so the header + table must carry it —
    # and the inventory must not claim a full-text diff that is not there.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.3", files="docs/x.md") + "\n")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text
    assert "SCOPE_ESCALATED" in next(ln for ln in text.splitlines() if ln.startswith("| F1.3 "))
    assert "うち" not in text.split("## 1.")[1].split("## 2.")[0]


def test_escalation_of_another_run_is_not_harvested(tmp_path: Path):
    # Run-id filtering is the property the independent-replay design rests on:
    # last week's escalation must not raise this week's reason code.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": "2026-07-18T00:00:00+00:00",
                    "run_id": "weekly-2026-07-17-0900",
                    "event": "scope_escalation",
                    "fix_id": "F1.2",
                    "files": "docs/old.md",
                }
            )
            + "\n"
        )
    text = _build(paths)
    assert "SCOPE_ESCALATED" not in text
    assert "docs/old.md" not in text


def test_escalated_fix_id_with_slash_matches_its_patch(tmp_path: Path):
    # The exporter names patches `<fix_id with / → _>.patch`; the builder must
    # use the same contract or the §3 note lands on no patch at all.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1/9", files="docs/y.md") + "\n")
    (paths["prompt_patches"] / "F1_9.patch").write_text("--- a/src/y.py\n", encoding="utf-8")
    body = _build(paths).split("### F1_9.patch")[1]
    assert "SCOPE_ESCALATED" in body and "docs/y.md" in body


def test_escalation_files_null_or_list_degrade_readably(tmp_path: Path):
    # A JSON null must not print "None" as if it were a path, and a list must
    # not leak a Python repr — the builder does not depend on the shell's
    # space-joined string formatting.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2", files=None) + "\n")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    text = _build(paths)
    assert "（パス不明）" in text and "触れたパス: None" not in text

    (tmp_path / "second").mkdir()
    paths2 = _write_inputs(tmp_path / "second")
    with paths2["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2", files=["docs/a.md"]) + "\n")
    (paths2["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    assert "触れたパス: `docs/a.md`" in _build(paths2)


def test_escalation_without_fix_id_marks_no_row(tmp_path: Path):
    # A "?" key would stamp the marker onto every other row that also lost its
    # fix_id. The escalation itself still reaches the header.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", files="docs/x.md") + "\n")
        fh.write(_audit_line("fix_result", scope="code", result="patch_ready", attempts="1") + "\n")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text.split("## 1.")[0]
    assert "SCOPE_ESCALATED" not in next(ln for ln in text.splitlines() if ln.startswith("| ? "))


def test_reason_code_cannot_forge_a_heading_from_the_header(tmp_path: Path):
    # Reason codes are literal constants in today's emitter, but the builder
    # does not trust the shell: the header renders them into a line of prose.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.8",
                scope="code",
                result="failed",
                attempts="1",
                reason="VERIFY_FAIL\n## 5. Dead code candidates",
            )
            + "\n"
        )
    text = _build(paths)
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())


# --- Value layer cadence (identity / constitution) ---


def _value_layer_json(
    tmp_path: Path,
    *,
    identity_due: bool = False,
    identity_days: int | None = 51,
    constitution_due: bool = False,
    constitution_days: int | None = 96,
    patterns_since: int | None = 120,
    staging_pending: int = 0,
) -> Path:
    path = tmp_path / "value-layer.json"
    path.write_text(
        json.dumps(
            {
                "as_of": "2026-07-24",
                "identity": {
                    "last_run_ts": "2026-06-03T00:00:00+00:00",
                    "days_since": identity_days,
                    "interval_days": 28,
                    "due": identity_due,
                    "reason": "INTERVAL_ELAPSED" if identity_due else "NOT_DUE",
                },
                "constitution": {
                    "last_adopted_ts": "2026-04-19T00:00:00+00:00",
                    "days_since": constitution_days,
                    "interval_days": 84,
                    "due": constitution_due,
                    "reason": "INTERVAL_ELAPSED" if constitution_due else "NOT_DUE",
                    "patterns_since": patterns_since,
                },
                "staging_pending": staging_pending,
                "malformed_audit_lines": 0,
                "reasons": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_value_layer_identity_staged_reaches_inventory_and_section(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("stage_result", stage="identity", result="ok") + "\n")
    vl = _value_layer_json(tmp_path, identity_due=True)
    text = _build(paths, value_layer=vl)
    assert "identity candidate: 1" in text
    assert "## 8. Value layer cadence" in text
    assert "adopt-staged" in text.split("## 8.")[1]
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["identity_due"] is True
    assert rec["constitution_due"] is False


def test_value_layer_identity_deferred_names_the_manual_path(tmp_path: Path):
    # ADR-0074: one unreviewed batch at a time — when insight got there first,
    # the gate must see the deferral AND the manual recovery (run distill after
    # adopt-staged empties staging), not silently wait a month.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "stage_result",
                stage="identity",
                result="skipped",
                reason="IDENTITY_STAGING_BUSY",
            )
            + "\n"
        )
    vl = _value_layer_json(tmp_path, identity_due=True, staging_pending=2)
    text = _build(paths, value_layer=vl)
    section = text.split("## 8.")[1]
    assert "IDENTITY_STAGING_BUSY" in section
    assert "distill-identity" in section
    assert "identity candidate:" not in text.split("## 8.")[0]


def test_value_layer_identity_stage_fail_is_visible(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "stage_result", stage="identity", result="fail", reason="IDENTITY_STAGE_FAIL"
            )
            + "\n"
        )
    vl = _value_layer_json(tmp_path, identity_due=True)
    text = _build(paths, value_layer=vl)
    assert "IDENTITY_STAGE_FAIL" in text.split("## 8.")[1]


def test_value_layer_constitution_due_points_to_runbook_not_automation(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path, constitution_due=True)
    text = _build(paths, value_layer=vl)
    section = text.split("## 8.")[1]
    assert "docs/runbooks/constitution-amendment.md" in section
    assert "ADR-0090" in section
    assert "96 日前" in section
    assert "patterns since adoption: 120" in section
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["constitution_due"] is True


def test_value_layer_quiet_week_is_silent(tmp_path: Path):
    # Signal-first: neither due and nothing attempted → no section, but the
    # metrics record still carries the readings for the longitudinal read.
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path)
    text = _build(paths, value_layer=vl)
    assert "Value layer cadence" not in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["identity_due"] is False
    assert rec["constitution_due"] is False


def test_value_layer_absent_arg_keeps_packet_unchanged(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "Value layer cadence" not in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    # Not read must never look like "read as not due" (same None discipline
    # as dead_code_candidates).
    assert rec["identity_due"] is None
    assert rec["constitution_due"] is None


def test_value_layer_unreadable_degrades_to_reason_code(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "value-layer.json"
    bad.write_text("{not json", encoding="utf-8")
    text = _build(paths, value_layer=bad)
    assert "VALUE_LAYER_UNREADABLE" in text.split("## 1.")[0]
    assert "Value layer cadence" not in text


def test_value_layer_instrument_reasons_reach_the_header(tmp_path: Path):
    # Degraded cadence evidence must not read as a clean run (codex review
    # 2026-08-10): the instrument's own reasons ride into reason_codes,
    # prefixed so the gate can tell the two audit logs apart.
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path)
    data = json.loads(vl.read_text(encoding="utf-8"))
    data["reasons"] = ["KNOWLEDGE_UNAVAILABLE", "FUTURE_TIMESTAMP"]
    vl.write_text(json.dumps(data), encoding="utf-8")
    text = _build(paths, value_layer=vl)
    header = text.split("## 1.")[0]
    assert "VALUE_LAYER_KNOWLEDGE_UNAVAILABLE" in header
    assert "VALUE_LAYER_FUTURE_TIMESTAMP" in header
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "VALUE_LAYER_KNOWLEDGE_UNAVAILABLE" in rec["reason_codes"]


def test_value_layer_schema_drift_is_named(tmp_path: Path):
    # A read-but-unrecognized shape must not look like a quiet week.
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "value-layer.json"
    bad.write_text(json.dumps({"identity": {"due": "yes"}, "reasons": []}), encoding="utf-8")
    text = _build(paths, value_layer=bad)
    assert "VALUE_LAYER_SCHEMA" in text.split("## 1.")[0]
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["identity_due"] is None


def test_value_layer_section_renders_even_when_instrument_unreadable(tmp_path: Path):
    # The §1 inventory line references §8; the section must exist whenever
    # an identity stage event does, even if the JSON was unreadable.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("stage_result", stage="identity", result="ok") + "\n")
    bad = tmp_path / "value-layer.json"
    bad.write_text("{not json", encoding="utf-8")
    text = _build(paths, value_layer=bad)
    assert "identity candidate: 1" in text
    assert "## 8. Value layer cadence" in text
    assert "VALUE_LAYER_UNREADABLE" in text.split("## 1.")[0]


def test_value_layer_unknown_reason_renders_constrained(tmp_path: Path):
    # The reason cell is narration; off-contract values must not read as
    # authoritative prose (same treatment as review verdicts).
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path, identity_due=True)
    data = json.loads(vl.read_text(encoding="utf-8"))
    data["identity"]["reason"] = "totally made up"
    vl.write_text(json.dumps(data), encoding="utf-8")
    text = _build(paths, value_layer=vl)
    assert "UNRECOGNIZED" in text.split("## 8.")[1]


# --- Repo-plane intake (ADR-0093): docs consistency ------------------------


def _docs_scan_json(tmp_path: Path, findings: list[dict], errors: list[dict] | None = None) -> Path:
    path = tmp_path / "docs-consistency.json"
    path.write_text(
        json.dumps(
            {
                "findings": findings,
                "count": len(findings),
                "readings": {"codemaps": []},
                "errors": errors or [],
                "scanned_files": 5,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_docs_section_rendered_when_findings_exist(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ds = _docs_scan_json(
        tmp_path,
        [
            {
                "check": "enja_drift",
                "file": "docs/adr/0053-x.md",
                "line": None,
                "detail": "en committed after ja",
            }
        ],
    )
    text = _build(paths, docs_scan=ds)
    assert "## 9. Docs consistency" in text
    assert "docs consistency: 1 件" in text
    assert "enja_drift" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["docs_findings"] == 1


def test_docs_clean_week_is_silent(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ds = _docs_scan_json(tmp_path, [])
    text = _build(paths, docs_scan=ds)
    assert "## 9." not in text
    assert "docs consistency" not in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["docs_findings"] == 0  # scanned clean, not "not scanned"


def test_docs_absent_arg_is_none_in_metrics(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _build(paths)
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["docs_findings"] is None


def test_docs_unreadable_degrades_to_reason_code(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "docs-consistency.json"
    bad.write_text("{not json", encoding="utf-8")
    text = _build(paths, docs_scan=bad)
    assert "DOCSCAN_UNREADABLE" in text.split("## 1.")[0]
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["docs_findings"] is None


def test_docs_partial_errors_render_warning_section(tmp_path: Path):
    # A degraded scan renders even with zero findings — the gate must see
    # that the clean-looking week may be an incomplete reading.
    paths = _write_inputs(tmp_path)
    ds = _docs_scan_json(
        tmp_path, [], errors=[{"check": "enja_drift", "reason": "GIT_FAIL", "detail": "x"}]
    )
    text = _build(paths, docs_scan=ds)
    assert "## 9. Docs consistency" in text
    assert "DOCSCAN_PARTIAL" in text


def test_non_list_errors_field_degrades_not_clean(tmp_path: Path):
    # Schema drift in the errors field must not read as a clean scan
    # (2026-08-14 code review L2).
    paths = _write_inputs(tmp_path)
    ds = tmp_path / "docs-consistency.json"
    ds.write_text(json.dumps({"findings": [], "errors": "GIT_FAIL: everything"}), encoding="utf-8")
    text = _build(paths, docs_scan=ds)
    assert "DOCSCAN_PARTIAL" in text.split("## 1.")[0]


# --- Rules layer maintenance reading (ADR-0097 D2, inside §8) ---


def _value_layer_with_rules(tmp_path: Path, rules: dict | None, **kwargs) -> Path:
    path = _value_layer_json(tmp_path, **kwargs)
    data = json.loads(path.read_text(encoding="utf-8"))
    if rules is not None:
        data["rules"] = rules
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_rules_issues_open_section_8_on_their_own(tmp_path: Path):
    """The layer lost its generator (ADR-0097 D2); the packet is the only
    place its structural state is now reported, so it must not need an
    identity or amendment week to be visible."""
    paths = _write_inputs(tmp_path)
    vl = _value_layer_with_rules(
        tmp_path,
        {
            "files": 2,
            "newest_mtime": "2026-04-11T00:00:00+00:00",
            "days_since_newest": 104,
            "issues": [{"file": "b-layer.md", "reason": 'missing "**Practice:**" section'}],
            "reason": "OK",
        },
    )
    text = _build(paths, value_layer=vl)
    assert "## 8. Value layer cadence (identity / constitution / rules)" in text
    section = text.split("## 8.")[1]
    assert "### Rules layer" in section
    assert "b-layer.md" in section
    assert 'missing "**Practice:**" section' in section
    assert "files: 2" in section
    assert "104 日前" in section
    # Counted by the builder from the rows, and surfaced up front.
    assert "rules layer: 1 件の構造 issue" in text


def test_clean_rules_layer_rides_along_but_opens_nothing(tmp_path: Path):
    """Signal-first: a quiet, well-formed layer adds no section of its own,
    but the standing count/mtime ride an already-open §8 for free."""
    paths = _write_inputs(tmp_path)
    clean = {
        "files": 2,
        "newest_mtime": "2026-04-11T00:00:00+00:00",
        "days_since_newest": 104,
        "issues": [],
        "reason": "OK",
    }
    quiet = _build(paths, value_layer=_value_layer_with_rules(tmp_path, clean))
    assert not any(ln.startswith("## 8.") for ln in quiet.splitlines())

    (tmp_path / "two").mkdir()
    paths2 = _write_inputs(tmp_path / "two")
    loud = _build(
        paths2,
        value_layer=_value_layer_with_rules(tmp_path / "two", clean, constitution_due=True),
    )
    assert "### Rules layer" in loud
    assert "構造 issue: 0 件" in loud
    assert "rules layer:" not in loud.split("## 2.")[0]  # no inventory line


def test_rules_layer_state_is_named_not_guessed(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    vl = _value_layer_with_rules(
        tmp_path,
        {
            "files": 0,
            "newest_mtime": None,
            "days_since_newest": None,
            "issues": [],
            "reason": "RULES_DIR_MISSING",
        },
    )
    text = _build(paths, value_layer=vl)
    assert "state: RULES_DIR_MISSING" in text.split("## 8.")[1]
    # A named state, not an UNRECOGNIZED(...) rendering.
    assert "UNRECOGNIZED" not in text.split("## 8.")[1]


def test_unknown_rules_reason_is_marked_unrecognized(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    vl = _value_layer_with_rules(
        tmp_path,
        {"files": 1, "newest_mtime": None, "issues": [], "reason": "RULES_HAUNTED"},
    )
    text = _build(paths, value_layer=vl)
    assert "UNRECOGNIZED(`RULES_HAUNTED`)" in text.split("## 8.")[1]


def test_rules_vocabulary_is_not_accepted_for_the_cadence_layers(tmp_path: Path):
    """`OK` is a legitimate rules state and a nonsense identity reason — one
    union allowlist would have let the second read as contract-abiding."""
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path, constitution_due=True)
    data = json.loads(vl.read_text(encoding="utf-8"))
    data["identity"]["reason"] = "OK"
    data["rules"] = {"files": 1, "newest_mtime": None, "issues": [], "reason": "OK"}
    vl.write_text(json.dumps(data), encoding="utf-8")
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("stage_result", stage="identity", result="ok") + "\n")
    section = _build(paths, value_layer=vl).split("## 8.")[1]
    assert "UNRECOGNIZED(`OK`)" in section.split("### Rules layer")[0]
    assert "state: OK" in section.split("### Rules layer")[1]


def test_rules_unreadable_reaches_the_packet_header(tmp_path: Path):
    """The instrument decides which rules state is a fault; the builder
    carries it through with the VALUE_LAYER_ prefix like every other one."""
    paths = _write_inputs(tmp_path)
    vl = _value_layer_json(tmp_path)
    data = json.loads(vl.read_text(encoding="utf-8"))
    data["rules"] = {
        "files": 1,
        "newest_mtime": None,
        "issues": [],
        "reason": "RULES_UNREADABLE",
        "unreadable_files": 1,
    }
    data["reasons"] = ["RULES_UNREADABLE"]
    vl.write_text(json.dumps(data), encoding="utf-8")
    text = _build(paths, value_layer=vl)
    assert "VALUE_LAYER_RULES_UNREADABLE" in text.split("## 1.")[0]
    assert "state: RULES_UNREADABLE" in text.split("## 8.")[1]


def test_unwalkable_rules_field_is_named_not_silently_dropped(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    vl = _value_layer_with_rules(tmp_path, None)
    data = json.loads(vl.read_text(encoding="utf-8"))
    data["rules"] = "two files, all fine"
    vl.write_text(json.dumps(data), encoding="utf-8")
    text = _build(paths, value_layer=vl)
    assert "VALUE_LAYER_SCHEMA" in text.split("## 1.")[0]
    assert "### Rules layer" not in text


def test_unwalkable_never_selected_reasons_field_is_named(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = tmp_path / "never-selected.json"
    ns.write_text(
        json.dumps({"exposure_floor": 600, "strict": [], "reasons": "everything is fine"}),
        encoding="utf-8",
    )
    text = _build(paths, skill_selection=ns)
    assert "NEVER_SELECTED_SCHEMA" in text.split("## 1.")[0]


def test_rules_metrics_field_distinguishes_not_scanned_from_clean(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _build(paths, value_layer=_value_layer_json(tmp_path))
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["rules_issues"] is None

    (tmp_path / "two").mkdir()
    paths2 = _write_inputs(tmp_path / "two")
    _build(
        paths2,
        value_layer=_value_layer_with_rules(
            tmp_path / "two",
            {"files": 2, "newest_mtime": None, "issues": [], "reason": "OK"},
        ),
    )
    rec2 = json.loads(paths2["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec2["rules_issues"] == 0


# --- Never-selected exit reading (ADR-0097 D5, §10) ---


def _never_selected_json(
    tmp_path: Path,
    *,
    strict: list[dict] | None = None,
    dormant: list[dict] | None = None,
    below_floor: list[dict] | None = None,
    exposure_floor: object = 600,
    full_skill_tokens: int = 38867,
    fail_open: int = 0,
    reasons: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
) -> Path:
    path = tmp_path / "never-selected.json"
    path.write_text(
        json.dumps(
            {
                "exposure_floor": exposure_floor,
                "strict": strict or [],
                "dormant": dormant or [],
                "below_floor": below_floor or [],
                "history": {
                    "files": 44,
                    "records": 3716,
                    "judged": 3690,
                    "first_day": "2026-07-10",
                    "last_day": "2026-08-22",
                },
                "window": {
                    "days": 14,
                    "since": since,
                    "until": until,
                    "records": 620,
                    "judged": 606,
                    "fail_open": fail_open,
                },
                "corpus": {"full_skill_tokens": full_skill_tokens, "num_ctx": 32768},
                "catalog": {"size": 57, "available": True},
                "reasons": reasons or [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_builder_allowlist_matches_the_instruments_vocabulary():
    """The builder cannot import the package (it runs under system python3),
    so its allowlist is a copy — pinned here rather than left to vigilance."""
    from contemplative_agent.core.skill_selection import NEVER_SELECTED_REASONS

    assert bdp.KNOWN_NEVER_SELECTED_REASONS == set(NEVER_SELECTED_REASONS)


def test_strict_candidates_are_listed_with_the_neutrality_caveat(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[
            {"name": "pre-processing-state-validation", "judged_exposure": 2531},
            {"name": "assume-perfect-adversarial-understanding", "judged_exposure": 1845},
        ],
    )
    text = _build(paths, skill_selection=ns)
    assert "never-selected skill: 2 件" in text
    assert "## 10. Never-selected skills" in text
    section = text.split("## 10.")[1]
    assert "pre-processing-state-validation" in section
    assert "2531" in section
    # The caveat lives beside the candidates, with both numbers printed.
    assert "fail-open" in section and "0 / 620 records" in section
    assert "38,867 tok" in section and "NUM_CTX 32,768 を超える" in section


def test_dormant_is_rendered_as_a_reading_never_a_candidate(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        dormant=[
            {
                "name": "internal-process-audit",
                "judged_exposure": 3000,
                "window_exposure": 606,
                "last_selected": "2026-08-03",
            }
        ],
    )
    text = _build(paths, skill_selection=ns)
    section = text.split("## 10.")[1]
    assert "internal-process-audit" in section
    assert "2026-08-03" in section
    assert "archive 候補ではない" in section
    # Dormant never reaches the inventory — it is not a decision the gate makes.
    assert "never-selected skill:" not in text.split("## 2.")[0]


def test_below_floor_is_counted_not_listed(tmp_path: Path):
    """The floor selects what gets LISTED; a name under it is not yet a
    candidate and must not appear as one (ADR-0097 D8)."""
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        below_floor=[
            {"name": "adopted-last-week", "judged_exposure": 120},
            {"name": "adopted-yesterday", "judged_exposure": 8},
        ],
        reasons=["NEVER_SELECTED_BELOW_FLOOR"],
    )
    text = _build(paths, skill_selection=ns)
    section = text.split("## 10.")[1]
    assert "他に 2 件" in section
    assert "最大 exposure 120" in section
    assert "adopted-last-week" not in section


def test_below_floor_reason_is_a_designed_outcome(tmp_path: Path):
    """It recurs by design after every adoption — counting it would spend an
    unattended improve session on the floor doing its job."""
    assert "NEVER_SELECTED_BELOW_FLOOR" in bdp.DESIGNED_OUTCOME_CODES
    metrics = tmp_path / "m.jsonl"
    for _ in range(2):
        metrics.write_text(
            "\n".join(
                json.dumps(
                    {
                        "phase": "auto",
                        "week_end": w,
                        "reason_codes": ["NEVER_SELECTED_BELOW_FLOOR"],
                    }
                )
                for w in ("2026-08-15", "2026-08-22")
            )
            + "\n",
            encoding="utf-8",
        )
    assert bdp.check_improvement(metrics)["fired"] is False


def test_strict_row_below_the_declared_floor_is_dropped_and_named(tmp_path: Path):
    """The builder re-applies the floor rather than trusting the producer's
    classification — the strict list is the one list a human archives from."""
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[
            {"name": "legitimate", "judged_exposure": 900},
            {"name": "smuggled-in", "judged_exposure": 3},
            {"name": "no-number", "judged_exposure": "many"},
        ],
    )
    text = _build(paths, skill_selection=ns)
    section = text.split("## 10.")[1]
    assert "legitimate" in section
    assert "smuggled-in" not in section
    assert "no-number" not in section
    assert "NEVER_SELECTED_SCHEMA" in text.split("## 1.")[0]
    assert "never-selected skill: 1 件" in text


def test_missing_floor_withholds_the_strict_list_entirely(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[{"name": "unverifiable", "judged_exposure": 900}],
        dormant=[{"name": "d", "judged_exposure": 10, "window_exposure": 5, "last_selected": "x"}],
        exposure_floor=None,
    )
    text = _build(paths, skill_selection=ns)
    section = text.split("## 10.")[1]
    assert "unverifiable" not in section
    assert "NEVER_SELECTED_SCHEMA" in section
    # The dormant reading does not depend on the floor and survives.
    assert "d" in section


def test_corpus_within_num_ctx_says_fail_open_would_reinject(tmp_path: Path):
    """The mechanism statement follows the numbers, both ways — the reader
    must be able to see which side of NUM_CTX this week is on."""
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[{"name": "quiet", "judged_exposure": 700}],
        full_skill_tokens=12000,
        fail_open=3,
    )
    section = _build(paths, skill_selection=ns).split("## 10.")[1]
    assert "NUM_CTX 32,768 に収まる" in section
    assert "再注入される" in section
    assert "3 / 620 records" in section


def test_unknown_corpus_size_abstains_from_the_comparison(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[{"name": "quiet", "judged_exposure": 700}],
        full_skill_tokens=0,
        reasons=["NEVER_SELECTED_FULL_TOKENS_UNKNOWN"],
    )
    text = _build(paths, skill_selection=ns)
    assert "NEVER_SELECTED_FULL_TOKENS_UNKNOWN" in text.split("## 1.")[0]
    assert "NUM_CTX との比較は不可" in text.split("## 10.")[1]


def test_quiet_week_renders_no_section(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths, skill_selection=_never_selected_json(tmp_path))
    assert not any(ln.startswith("## 10.") for ln in text.splitlines())
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["never_selected_strict"] == 0


def test_absent_arg_keeps_packet_unchanged_and_metrics_none(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "## 10." not in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["never_selected_strict"] is None


def test_unreadable_never_selected_json_degrades_to_a_reason_code(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "never-selected.json"
    bad.write_text("{not json", encoding="utf-8")
    text = _build(paths, skill_selection=bad)
    assert "NEVER_SELECTED_UNREADABLE" in text.split("## 1.")[0]
    assert "## 10." not in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["never_selected_strict"] is None


def test_instrument_reasons_reach_the_header_and_drift_is_named(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        reasons=["NEVER_SELECTED_NO_CATALOG", "NEVER_SELECTED_FROM_THE_FUTURE"],
    )
    header = _build(paths, skill_selection=ns).split("## 1.")[0]
    assert "NEVER_SELECTED_NO_CATALOG" in header
    assert "NEVER_SELECTED_FROM_THE_FUTURE" not in header
    assert "NEVER_SELECTED_SCHEMA" in header


def test_hostile_skill_name_cannot_forge_a_section(tmp_path: Path):
    """Store skill names are LLM-distilled text. §10 renders them inside a
    table cell, so the module-wide floor has to hold there too: the row stays
    one line and the forged heading never reaches line-initial position."""
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[{"name": "evil|\n## 11. Fake section\n", "judged_exposure": 900}],
        dormant=[
            {
                "name": "also-evil\n## 12. Also fake\n",
                "judged_exposure": 10,
                "window_exposure": 5,
                "last_selected": "2026-08-\n## 13. Nope",
            }
        ],
    )
    text = _build(paths, skill_selection=ns)
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert not any("Fake" in h or "fake" in h or "Nope" in h for h in headings)
    # The pipe is escaped too, so the forged cell cannot split the row.
    assert "| `evil\\|" in text


def test_explicit_window_bounds_are_named_not_reported_as_last_n_days(tmp_path: Path):
    """The instrument's second window mode (T-SKILLSEL-REPORT-WINDOW) is a
    UTC calendar range; calling it "直近 N 日" would misreport it by a day and
    hide a backfill, the exact trap that mode exists to avoid."""
    paths = _write_inputs(tmp_path)
    ns = _never_selected_json(
        tmp_path,
        strict=[{"name": "quiet", "judged_exposure": 700}],
        since="2026-08-08",
        until="2026-08-22",
    )
    section = _build(paths, skill_selection=ns).split("## 10.")[1]
    assert "2026-08-08 … 2026-08-22の fail-open" in section
    assert "直近" not in section
    assert "### Dormant（2026-08-08 … 2026-08-22は 0 回" in section
