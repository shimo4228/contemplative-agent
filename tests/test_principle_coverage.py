"""Fault column for ``scripts/principle_coverage.py`` (ROADMAP P3-06.9).

A read-only, LLM-free instrument over comment-report Markdown. The parsing
boundary (two report grammars), the column definitions, the count-only floor
for small denominators and the output boundary (counts only — Context is other
agents' text) are the fault surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import principle_coverage as pc  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = REPO_ROOT / "scripts" / "principle_coverage.py"

CONTEXT = (
    "The decay rate of error propagation in long horizon tasks rises with state graph density."
)


def _entry(i, kind, post, note, output, ctx=CONTEXT, ts="2026-10-01 10:00:0"):
    return (
        f"### {i}. [{ts}{i}] {kind} · with someone · post {post}… · relevance P(top) 0.80\n\n"
        f"**Context:**\n{ctx}\n\n**Internal note:**\n{note}\n\n**Output:**\n{output}\n\n---\n\n"
    )


def _report(entries):
    return "# Moltbook Activity Report — 2026-10-01\n\n## Comments (n total)\n\n" + "".join(entries)


def _parse(entries):
    return pc.parse_entries(_report(entries), "2026-10-01")


class TestParsing:
    def test_new_format_fields(self):
        (e,) = _parse([_entry(1, "COMMENT", "abc123", "A phrase drew me.", "my reply")])
        assert (e["kind"], e["post"], e["output"], e["note"]) == (
            "COMMENT",
            "abc123",
            "my reply",
            "A phrase drew me.",
        )
        assert e["context"] == CONTEXT

    def test_legacy_format_takes_kind_from_section_and_has_no_note(self):
        text = (
            "# Moltbook Activity Report — 2026-03-14\n\n## Comments (1 total)\n\n"
            "### 1. [2026-03-14 00:03:38] Post ID: 613ca785-4ed... (relevance: 0.92)\n\n"
            "**Comment:**\nEmptiness matters.\n\n---\n\n## Replies (1 total)\n\n"
            "### 1. [2026-03-14 01:00:00] Post ID: dfc2ae5e-f69... (relevance: 0.95)\n\n"
            "**Their comment:**\nthey said\n\n**Reply:**\nmine\n\n---\n\n"
        )
        a, b = pc.parse_entries(text, "2026-03-14")
        assert (a["kind"], a["output"], a["note"]) == ("COMMENT", "Emptiness matters.", "")
        assert (b["kind"], b["output"], b["context"]) == ("REPLY", "mine", "they said")

    def test_thinking_never_bleeds_into_output(self):
        text = _entry(1, "COMMENT", "p1", "n", "out").replace(
            "**Output:**", "**Thinking:**\nSECRET\n\n**Output:**"
        )
        (e,) = _parse([text])
        assert "SECRET" not in e["output"] and "SECRET" not in e["note"]


class TestColumns:
    def test_a_counts_nothing_stood_out_and_missing_notes_are_not_zero_rate(self):
        es = _parse(
            [
                _entry(i, "COMMENT", f"p{i}", "Nothing in particular stood out.", "x")
                for i in range(1, 4)
            ]
            + [_entry(i, "COMMENT", f"p{i}", "The phrase drew me.", "x") for i in range(4, 12)]
        )
        a = pc.column_a(es)["nothing_stood_out_then_commented"]
        assert (a["n"], a["of"]) == (3, 11)
        assert a["rate"] == round(3 / 11, 4) and a["ci95"] is not None

    def test_small_denominator_is_count_only(self):
        es = _parse([_entry(1, "COMMENT", "p1", "Nothing stood out.", "x")])
        a = pc.column_a(es)["nothing_stood_out_then_commented"]
        assert (a["n"], a["of"], a["rate"], a["ci95"]) == (1, 1, None, None)

    def test_b_reply_between_resets_the_streak(self):
        es = _parse(
            [
                _entry(1, "COMMENT", "t1", "n", "x"),
                _entry(2, "REPLY", "t1", "n", "x"),
                _entry(3, "COMMENT", "t1", "n", "x"),  # after a reply: not consecutive
                _entry(4, "COMMENT", "t2", "n", "x"),
                _entry(5, "COMMENT", "t2", "n", "x"),  # two comments, no reply between
            ]
        )
        b = pc.column_b(es)["consecutive_last_speaker_threads"]
        assert (b["n"], b["of"]) == (1, 2)

    def test_c_positive_control_axiom_noun_without_concrete_reference(self):
        es = _parse(
            [
                _entry(i, "COMMENT", f"p{i}", "n", "Emptiness and boundless care guide me.")
                for i in range(10)
            ]
        )
        c = pc.column_c(es)
        assert c["axiom_noun_in_output"]["rate"] == 1.0
        assert c["axiom_noun_without_concrete_reference"]["n"] == 10
        assert c["concrete_reference"]["n"] == 0

    def test_c_negative_control_and_concrete_reference(self):
        out = "You note the decay rate of error propagation in long horizon tasks, which I accept."
        es = _parse([_entry(i, "COMMENT", f"p{i}", "n", out) for i in range(10)])
        c = pc.column_c(es)
        assert c["axiom_noun_in_output"]["n"] == 0
        assert c["concrete_reference"]["n"] == 10

    def test_c4_self_reference_word_counts_only_when_context_lacks_it(self):
        ctx_with = "The constitution of this club is long."
        es = _parse(
            [
                _entry(i, "COMMENT", f"p{i}", "n", "My constitution says so.", ctx=CONTEXT)
                for i in range(5)
            ]
            + [
                _entry(i, "COMMENT", f"q{i}", "n", "My constitution says so.", ctx=ctx_with)
                for i in range(5, 10)
            ]
        )
        assert pc.column_c(es)["self_reference_word_not_in_context"]["n"] == 5

    def test_d_flag_and_unavailable(self, tmp_path):
        ident = tmp_path / "identity.md"
        ident.write_text("I value it: it's okay not to respond to everything.", encoding="utf-8")
        assert pc.column_d(ident)["silence_permission_sentence"] is True
        ident.write_text("I answer every post.", encoding="utf-8")
        assert pc.column_d(ident)["silence_permission_sentence"] is False
        assert pc.column_d(None)["silence_permission_sentence"] == "unavailable"
        assert pc.column_d(tmp_path / "nope.md")["reason"] == "identity_unreadable"


class TestOutputBoundary:
    def test_render_carries_counts_only_never_bodies_or_ids(self, tmp_path):
        d = tmp_path / "reports"
        d.mkdir()
        (d / "comment-report-2026-10-01.md").write_text(
            _report(
                [
                    _entry(
                        i,
                        "COMMENT",
                        f"POSTID{i}",
                        "BODYNOTE nothing stood out",
                        "BODYOUT",
                        ctx="BODYCTX",
                    )
                    for i in range(1, 12)
                ]
            ),
            encoding="utf-8",
        )
        r = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPT),
                "--report-dir",
                str(d),
                "--start",
                "2026-10-01",
                "--end",
                "2026-10-01",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr
        for secret in ("BODYNOTE", "BODYOUT", "BODYCTX", "POSTID", "someone"):
            assert secret not in r.stdout
        assert "## Principle Coverage" in r.stdout and "95% Wilson" in r.stdout

    def test_empty_window_is_a_stated_reason(self, tmp_path):
        r = subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPT),
                "--report-dir",
                str(tmp_path),
                "--start",
                "2026-10-01",
                "--end",
                "2026-10-02",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0 and "reason=no_entries" in r.stdout
