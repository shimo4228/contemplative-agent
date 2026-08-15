"""Tests for scripts/ledger_condition_scan.py — the weekly ledger-watch intake.

The seventh deterministic intake (ADR-0093) re-checks the machine-checkable
unblock conditions annotated on blocked rows of `.notes/TASKS.md` (the task
ledger, deliberately local/gitignored — which is exactly why this runs in the
local weekly chain and not in any cloud agent). The knowledge-staleness rule
demands expiry conditions on proposals; this intake is the polling half that
was missing: conditions were written down and then never re-read.

Grammar (one backtick code span per condition, anywhere in a ledger row):

    `watch: gh-pr ollama/ollama#12030`
    `watch: http-post-status http://localhost:11434/api/tokenize 404`
    `watch: file-exists ~/.config/moltbook/cloud.env`

Security contract: response bodies never reach the output. gh-pr state is
mapped onto the closed vocabulary {open, closed, merged}; anything else is a
SCHEMA_DRIFT reason code, never an echoed string. Targets come from the
self-authored ledger (trusted), but the packet builder still _cell-escapes
them at render time.

Fault column (chaos-TDD, ADR-0077 — the seam is the injectable fetcher):

- F-LW-1  network unreachable / timeout → fired=None, reason=UNREACHABLE
- F-LW-2  non-JSON GitHub response → fired=None, reason=PARSE_ERROR
- F-LW-3  unknown `state` value (schema drift) → fired=None,
          reason=SCHEMA_DRIFT — the unknown string is NOT emitted
- F-LW-4  HTTP >= 400 from the API → fired=None, reason=HTTP_ERROR
- F-LW-5  unknown watch type → fired=None, reason=UNKNOWN_WATCH_TYPE
- F-LW-6  ledger file missing → abstain (nonzero exit, LEDGERWATCH_FAIL on
          stderr), never an empty "no watches" success
- F-LW-7  malformed watch expression → fired=None, reason=MALFORMED_WATCH
- F-LW-8  a `watch:` span on a blocked row that `_WATCH_RE` cannot see —
          unterminated, zero-argument, or swallowed by a neighbour's closing
          backtick — is reported as MALFORMED_WATCH under its own kind name,
          never dropped and never misnamed. A span that fails to match is
          otherwise indistinguishable from a row carrying no watch at all
"""

from __future__ import annotations

import http.client
import json
import sys
import time
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger_condition_scan as lcs  # noqa: E402  # pyright: ignore[reportMissingImports]

LEDGER = """\
# TASKS

| ID | 状態 | タスク | 着手条件 | 詳細 |
|----|------|--------|----------|------|
| T-A | blocked | x | `watch: gh-pr ollama/ollama#12030` がマージされたら | y |
| T-B | blocked | x | `watch: file-exists ~/nope.env` | y |
| T-C | ready | 注釈なしの行 | — | y |
"""


def _fetch_json(payload: dict, status: int = 200):
    body = json.dumps(payload).encode()
    return lambda url, method="GET": (status, body)


class TestParseWatches:
    def test_extracts_task_id_type_and_args(self):
        watches, errors = lcs.parse_watches(LEDGER)
        assert errors == []
        assert [(w.task, w.type) for w in watches] == [
            ("T-A", "gh-pr"),
            ("T-B", "file-exists"),
        ]
        assert watches[0].args == ("ollama/ollama#12030",)

    def test_f_lw_7_malformed_expression_surfaces(self):
        watches, errors = lcs.parse_watches("| T-X | blocked | `watch: gh-pr` | — |")
        assert watches == []
        assert [e["reason"] for e in errors] == ["MALFORMED_WATCH"]
        assert errors[0]["task"] == "T-X"

    def test_row_without_task_id_is_malformed(self):
        watches, errors = lcs.parse_watches("`watch: file-exists /tmp/x`")
        assert watches == []
        assert [e["reason"] for e in errors] == ["MALFORMED_WATCH"]

    def test_non_blocked_rows_are_not_polled(self):
        # The contract watches BLOCKED rows: a task moved to done/ready whose
        # historical annotation survives must stop polling — otherwise a
        # resolved task alerts in §10 forever (2026-08-14 codex review P2).
        text = (
            "| T-DONE | done 2026-08-09 | x | `watch: file-exists /tmp/x` | y |\n"
            "| T-LIVE | blocked | x | `watch: file-exists /tmp/y` | y |\n"
        )
        watches, errors = lcs.parse_watches(text)
        assert errors == []
        assert [w.task for w in watches] == ["T-LIVE"]


class TestUnterminatedWatchSpan:
    """F-LW-8 — the failure that reads as success.

    `_WATCH_RE` requires a closing backtick **and** at least one argument
    character, so an annotation missing either produces no match — and *no
    match* is exactly what a row with no annotation produces. Left alone, the
    task waits in §10 at `fired 0` for as long as it stays blocked (2026-08-15
    code review LOW).

    The kinds are named separately because they share no true sentence. A first
    version called all of them "unterminated", which was false for the one that
    closes and false for the one whose closer was taken — a guard against
    silent failure that misnamed the failure (2026-08-15 code review HIGH).
    """

    @pytest.mark.parametrize(
        ("cell", "kind"),
        [
            ("上流待ち `watch: gh-pr a/b#1", lcs.WATCH_UNTERMINATED),
            ("解除条件 `watch:` は後で書く", lcs.WATCH_NO_ARGUMENT),
        ],
        ids=["unterminated", "no-argument"],
    )
    def test_each_invisible_kind_is_reported_under_its_own_name(self, cell, kind):
        watches, errors = lcs.parse_watches(f"| T-X | blocked | {cell} | — | y |")
        assert watches == []
        assert [(e["task"], e["reason"]) for e in errors] == [("T-X", "MALFORMED_WATCH")]
        assert f"({kind})" in errors[0]["detail"]

    def test_a_span_swallowed_by_a_neighbour_is_named_not_merely_counted(self):
        """Three annotations, the middle one eaten by its neighbour's backtick.

        `/a`'s span runs to the backtick that was meant to *open* `/b`, so `/b`
        disappears and `/c` parses normally: two openers matched, three
        present. Which one is reported has to come from the offsets — pairing
        the leftover openers by *count* names `/c`, the one that is fine, and
        says nothing about `/b`, the one that vanished. A diagnosis pointing at
        the wrong annotation is worse than none, so the excerpt is asserted.
        """
        watches, errors = lcs.parse_watches(
            "| T-X | blocked | `watch: file-exists /a "
            "`watch: file-exists /b` `watch: file-exists /c` | — | y |"
        )
        assert [(w.task, w.args) for w in watches] == [("T-X", ("/a",)), ("T-X", ("/c",))]
        assert [e["reason"] for e in errors] == ["MALFORMED_WATCH"]
        # The excerpt must *begin* at the offender. Asserting mere containment
        # would pass on the count-paired version too, since an 80-char window
        # opened at `/c` still reaches `/b`'s text on a row this dense.
        assert errors[0]["detail"].endswith(
            f"({lcs.WATCH_SWALLOWED}): `watch: file-exists /b` `watch: file-exists /c` | — | y |"
        )

    def test_a_well_formed_row_reports_nothing(self):
        """The negative half: the guard must not fire on the shape it allows."""
        watches, errors = lcs.parse_watches("| T-X | blocked | `watch: file-exists /a` | — | y |")
        assert errors == []
        assert [w.args for w in watches] == [("/a",)]

    def test_the_ledger_header_documenting_the_grammar_is_not_a_fault(self):
        """`_HEADER` explains the annotation with a bare `` `watch:` ``, which
        opens and closes with empty args — no `_WATCH_RE` match, and on a line
        that is not a task row at all. Reporting it would put a permanent
        phantom entry in §10, which is the same "noise that trains you to
        ignore the section" failure the scoping exists to avoid."""
        header = (
            "> **watch 注釈（ADR-0093）**: 解除条件は `watch:` で始まる backtick スパンで注釈する。"
        )
        assert lcs.parse_watches(header) == ([], [])

    def test_the_excerpt_cannot_carry_terminal_control_into_the_artifact(self):
        """`detail` is the one field that echoes ledger text verbatim, and
        `json.dumps` escapes only C0 — DEL, the 8-bit C1 controls, the bidi
        overrides and ZWSP all survive it literally. Bodies are self-authored
        but routinely quote outside text (pasted logs, upstream titles), and
        the sinks are a retained JSON artifact and a terminal (2026-08-15
        security review LOW). Both details are covered, not just the new one.
        """
        poison = "\x7f‮​"
        # Placed INSIDE each excerpt window. The invisible-span excerpt starts
        # at the opener, so poison written before it is never echoed — a first
        # version put it there and passed with the sanitiser deleted, which the
        # mutation sweep caught.
        rows = [
            f"| T-X | blocked | 待ち `watch: gh-pr{poison} a/b#1 | — | y |",  # invisible-span
            f"| T-Y | blocked | `watch: gh-pr{poison}` | — | y |",  # arity detail
        ]
        for row in rows:
            _, errors = lcs.parse_watches(row)
            assert errors, row
            blob = json.dumps(errors, ensure_ascii=False)
            assert not any(ch in blob for ch in poison), errors

    def test_a_whitespace_run_after_an_opener_does_not_backtrack(self):
        """`\\s*` and `[^`]+` overlap, so an opener trailed by whitespace with
        no closing backtick was quadratic — 811ms at 16k spaces, 4x per
        doubling, and `render_row` now runs the pattern three times per blocked
        task with no timeout above it (2026-08-15 security review LOW).

        The bound is generous by ~1000x: measured 3.3s unbounded vs ~2ms with
        `\\s{0,8}` at this size.
        """
        start = time.perf_counter()
        lcs.parse_watches("| T-X | blocked | `watch:" + " " * 32000 + "| — | y |")
        assert time.perf_counter() - start < 1.0

    def test_the_whitespace_bound_does_not_change_what_is_parsed(self):
        """The deterministic half of the finding above: past the eighth space
        the run falls into `[^`]+` and is discarded by `.split()`, so a
        generously-indented annotation still parses to the same watch."""
        wide = "| T-X | blocked | `watch:" + " " * 20 + "gh-pr a/b#1` | — | y |"
        watches, errors = lcs.parse_watches(wide)
        assert errors == []
        assert [(w.type, w.args) for w in watches] == [("gh-pr", ("a/b#1",))]

    def test_a_non_blocked_row_is_outside_the_contract_entirely(self):
        """The scan's scope is the watch contract's scope — blocked rows — for
        every kind, including the invisible ones. The *render* is stricter for
        the two kinds that are broken markup in any state; this end stays at
        the contract, because a row out of contract has nothing to report."""
        row = "| T-DONE | done 2026-08-10 | 本文が `watch: gh-pr a/b#1 でも通る | なし | — |"
        assert lcs.parse_watches(row) == ([], [])


class TestGhPr:
    def test_open_pr_not_fired(self):
        result = lcs.check_gh_pr(
            "ollama/ollama#12030", _fetch_json({"state": "open", "merged": False})
        )
        assert result == {"status": "open", "fired": False, "reason": None}

    def test_merged_pr_fires(self):
        result = lcs.check_gh_pr(
            "ollama/ollama#12030", _fetch_json({"state": "closed", "merged": True})
        )
        assert result == {"status": "merged", "fired": True, "reason": None}

    def test_closed_unmerged_fires(self):
        result = lcs.check_gh_pr("o/r#1", _fetch_json({"state": "closed", "merged": False}))
        assert result["status"] == "closed" and result["fired"] is True

    def test_f_lw_1_unreachable(self):
        def fetch(url, method="GET"):
            raise OSError("connection refused")

        result = lcs.check_gh_pr("o/r#1", fetch)
        assert result == {"status": None, "fired": None, "reason": "UNREACHABLE"}

    def test_f_lw_2_non_json(self):
        result = lcs.check_gh_pr("o/r#1", lambda url, method="GET": (200, b"<html>"))
        assert result["reason"] == "PARSE_ERROR" and result["fired"] is None

    def test_f_lw_3_unknown_state_not_echoed(self):
        payload = {"state": "<script>evil</script>", "merged": False}
        result = lcs.check_gh_pr("o/r#1", _fetch_json(payload))
        assert result == {"status": None, "fired": None, "reason": "SCHEMA_DRIFT"}

    def test_f_lw_4_http_error(self):
        result = lcs.check_gh_pr("o/r#1", _fetch_json({}, status=404))
        assert result == {"status": "http_404", "fired": None, "reason": "HTTP_ERROR"}

    def test_bad_target_is_malformed(self):
        result = lcs.check_gh_pr("not-a-target", _fetch_json({}))
        assert result["reason"] == "MALFORMED_WATCH"


class TestHttpStatus:
    def test_expected_status_not_fired(self):
        result = lcs.check_http_status(
            "http://localhost:11434/api/tokenize",
            "404",
            lambda url, method="GET": (404, b""),
            method="POST",
        )
        assert result == {"status": "http_404", "fired": False, "reason": None}

    def test_unexpected_status_fires(self):
        result = lcs.check_http_status(
            "http://localhost:11434/api/tokenize",
            "404",
            lambda url, method="GET": (400, b""),
            method="POST",
        )
        assert result == {"status": "http_400", "fired": True, "reason": None}

    def test_f_lw_1_unreachable(self):
        def fetch(url, method="GET"):
            raise OSError("refused")

        result = lcs.check_http_status("http://x", "404", fetch)
        assert result == {"status": None, "fired": None, "reason": "UNREACHABLE"}

    def test_non_http_scheme_is_malformed(self):
        result = lcs.check_http_status(
            "file:///etc/passwd", "404", lambda u, method="GET": (0, b"")
        )
        assert result["reason"] == "MALFORMED_WATCH"

    def test_unicode_digit_expect_is_malformed_not_a_crash(self):
        # '\u00b2'.isdigit() is True but int('\u00b2') raises — the row must
        # degrade, not kill the remaining watches (2026-08-14 code review L1).
        result = lcs.check_http_status(
            "http://localhost/x", "\u00b2", lambda u, method="GET": (200, b"")
        )
        assert result == {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}

    def test_post_to_non_loopback_host_is_malformed(self):
        # Unattended empty-body POSTs are state-changing on lazy services;
        # the only legitimate POST target is the local Ollama probe
        # (2026-08-14 security review MEDIUM).
        result = lcs.check_http_status(
            "http://evil.example/api", "404", lambda u, method="GET": (404, b""), method="POST"
        )
        assert result == {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}

    def test_post_to_loopback_is_allowed(self):
        result = lcs.check_http_status(
            "http://localhost:11434/api/tokenize",
            "404",
            lambda u, method="GET": (404, b""),
            method="POST",
        )
        assert result["reason"] is None


class TestDefaultFetch:
    def test_f_lw_8_garbage_status_line_degrades_to_oserror(self, monkeypatch):
        # http.client.BadStatusLine is NOT an OSError, and its message embeds
        # the server's raw response line — it must be converted to a
        # code-owned OSError before it can escape into ledgerwatch.err
        # (2026-08-14 security review MEDIUM).
        def exploding_urlopen(request, timeout=None):
            raise http.client.BadStatusLine("<attacker bytes>")

        monkeypatch.setattr(lcs.urllib.request, "urlopen", exploding_urlopen)
        with pytest.raises(OSError) as excinfo:
            lcs.default_fetch("http://localhost:1/x")
        assert "attacker" not in str(excinfo.value)


class TestFileExists:
    def test_existing_file_fires(self, tmp_path: Path):
        target = tmp_path / "cloud.env"
        target.write_text("", encoding="utf-8")
        result = lcs.check_file_exists(str(target))
        assert result == {"status": "exists", "fired": True, "reason": None}

    def test_missing_file_not_fired(self, tmp_path: Path):
        result = lcs.check_file_exists(str(tmp_path / "nope.env"))
        assert result == {"status": "absent", "fired": False, "reason": None}


class TestScan:
    def test_scan_renders_contract(self, tmp_path: Path):
        ledger = tmp_path / "TASKS.md"
        ledger.write_text(LEDGER, encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({"state": "closed", "merged": True}))
        assert result["watch_count"] == 2
        assert result["fired_count"] == 1  # gh-pr merged fired; ~/nope.env absent
        by_task = {w["task"]: w for w in result["watches"]}
        assert by_task["T-A"]["status"] == "merged"
        assert by_task["T-B"]["fired"] is False

    def test_f_lw_5_unknown_type_carried_per_watch(self, tmp_path: Path):
        ledger = tmp_path / "TASKS.md"
        ledger.write_text("| T-Z | blocked | `watch: carrier-pigeon x` | — |", encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({}))
        assert result["watches"][0]["reason"] == "UNKNOWN_WATCH_TYPE"
        assert result["watches"][0]["fired"] is None

    def test_no_watches_is_a_clean_zero(self, tmp_path: Path):
        ledger = tmp_path / "TASKS.md"
        ledger.write_text("| T-C | ready | x | — |", encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({}))
        assert result == {
            "watches": [],
            "watch_count": 0,
            "fired_count": 0,
            "errors": [],
        }

    def test_f_lw_6_missing_ledger_abstains(self, tmp_path: Path, capsys):
        rc = lcs.main(["--ledger", str(tmp_path / "missing.md")])
        assert rc != 0
        assert "LEDGERWATCH_FAIL" in capsys.readouterr().err

    def test_main_emits_json(self, tmp_path: Path, capsys):
        ledger = tmp_path / "TASKS.md"
        ledger.write_text("| T-C | ready | x | — |", encoding="utf-8")
        rc = lcs.main(["--ledger", str(ledger)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["watch_count"] == 0
