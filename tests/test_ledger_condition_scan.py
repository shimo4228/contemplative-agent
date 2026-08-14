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
"""

from __future__ import annotations

import http.client
import json
import sys
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
