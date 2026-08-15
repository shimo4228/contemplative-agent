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
- F-LW-9  the ledger is a *projection* of `.notes/tasks/` (ADR-0094) and
          nothing on this path re-derives it, so a failed `tasks.py render`
          leaves the previous table in place: parsing it yields a well-formed
          `fired 0` over rows the store no longer has. The table is therefore
          rendered from the store on every run and the file is not the input —
          a store that will not render abstains (LEDGER_UNRENDERABLE, carrying
          render's own message), and the two ways the subprocess itself fails
          get RENDER_TIMEOUT / RENDER_UNAVAILABLE. Drift in the on-disk file is
          reported (PROJECTION_DRIFT) and never fatal
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
import tasks as tasks_mod  # noqa: E402  # pyright: ignore[reportMissingImports]

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

    def test_the_watch_target_is_sanitised_too_not_only_the_error_detail(self):
        """`target` is the *other* field carrying ledger text verbatim, and it
        goes further than `detail`: it reaches packet §10, which a human reads
        at the Saturday gate. The first version of `_printable`'s docstring
        claimed `detail` was the only such field, and `target` was unsanitised
        because of it (2026-08-15 security review).

        Since 2026-08-16 `build_decision_packet._cell` also neutralises this
        class, so §10 has two layers. This assertion is still the load-bearing
        one for `detail`, which reaches a terminal directly and passes through
        no packet code at all."""
        # Only the non-printable characters are the hazard; `[31m` is inert
        # text and must survive, so asserting over the whole escape sequence
        # would fail on the half that is supposed to pass through.
        control = "\x1b\x7f‮​"
        watch = lcs.Watch(task="T-X", type="file-exists", args=(f"/tmp/{control}[31mx",))
        result = lcs.run_watch(watch, lambda *_a, **_k: (200, b""))
        assert not any(ch in result["target"] for ch in control)
        assert result["target"].startswith("/tmp/") and result["target"].endswith("[31mx")

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
            "projection_drift": None,
            "source": "file",
        }

    def test_f_lw_6_missing_ledger_abstains(self, tmp_path: Path, capsys):
        """Through `main`, which now renders — so what is missing is the store
        the derived root points at, and the abstain names that. The contract
        F-LW-6 exists for is unchanged: nonzero, never an empty 'no watches'
        success."""
        notes = tmp_path / ".notes"
        notes.mkdir()
        rc = lcs.main(["--ledger", str(notes / "TASKS.md")])
        assert rc != 0
        assert "LEDGERWATCH_FAIL" in capsys.readouterr().err

    def test_a_ledger_outside_the_expected_layout_is_refused_not_guessed(
        self, tmp_path: Path, capsys
    ):
        """The root is derived from the ledger, so an unexpected layout silently
        bound the reading to a store the caller never named: `--ledger
        <repo>/backup/TASKS.md` produced a full reading of `<repo>/.notes/tasks`
        labelled `source: store` (2026-08-15 code review LOW)."""
        stray = tmp_path / "backup"
        stray.mkdir()
        assert lcs.main(["--ledger", str(stray / "TASKS.md")]) == 2
        assert "--root" in capsys.readouterr().err

    def test_main_emits_json(self, tmp_path: Path, capsys):
        ledger, _ = _store(tmp_path, [PLAIN_READY])
        rc = lcs.main(["--ledger", str(ledger)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["watch_count"] == 0


TASK_FILE = """---
id: {tid}
state: {state}
seq: {seq}
---

## タスク

{summary}

## 着手条件

{condition}

## 詳細

—
"""


def _store(root: Path, tasks: list[dict], *, render: bool = True) -> tuple[Path, Path]:
    """A real `.notes/` layout: a store of task files, and its projection.

    Task *files*, not a hand-written table, because the scan now renders the
    table itself — a fixture that faked the projection would exercise none of
    the path under test.
    """
    notes = root / ".notes"
    (notes / "tasks").mkdir(parents=True)
    for seq, task in enumerate(tasks, start=1):
        (notes / "tasks" / f"{task['tid']}.md").write_text(
            TASK_FILE.format(seq=seq, condition="なし", **task), encoding="utf-8"
        )
    ledger = notes / "TASKS.md"
    if render:
        ledger.write_text(
            tasks_mod.render_ledger(tasks_mod.load_store(notes / "tasks")), encoding="utf-8"
        )
    return ledger, root


BLOCKED_ON_PR = {
    "tid": "T-A",
    "state": "blocked",
    "summary": "待ち `watch: gh-pr ollama/ollama#12030`",
}
BLOCKED_ON_FILE = {
    "tid": "T-B",
    "state": "blocked",
    "summary": "待ち `watch: file-exists ~/nope.env`",
}
PLAIN_READY = {"tid": "T-C", "state": "ready", "summary": "注釈なしの行"}


class TestRenderFromStore:
    """F-LW-9 — the table is re-derived, never read from a cache.

    `.notes/TASKS.md` is a projection of `.notes/tasks/` (ADR-0094) and nothing
    on the weekly path re-renders it, so a week whose `tasks.py render` failed
    handed this intake the *previous* table: well-formed, parseable, describing
    a store that had moved. The old rows polled clean and the new blocked rows
    were simply absent, so "the render is broken" reached the gate as
    `result=ok watches=N fired=0` — ADR-0077's forbidden shape one layer up
    (2026-08-15 code review HIGH). Reading the store directly removes the cache
    rather than testing its age.
    """

    def test_the_reading_comes_from_the_store(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [BLOCKED_ON_PR, BLOCKED_ON_FILE, PLAIN_READY])
        result = lcs.scan(ledger, fetch=_fetch_json({"state": "closed", "merged": True}), root=root)
        assert result["source"] == "store"
        assert result["watch_count"] == 2
        assert result["fired_count"] == 1  # gh-pr merged fired; ~/nope.env absent
        assert result["errors"] == []

    def test_a_task_filed_since_the_last_render_is_already_polled(self, tmp_path: Path):
        """The whole point of reading the source. Under the old design this row
        was invisible until a human re-rendered, and its absence was
        indistinguishable from a condition that had not fired."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / "T-NEW.md").write_text(
            TASK_FILE.format(
                tid="T-NEW",
                state="blocked",
                seq=9,
                condition="なし",
                summary="待ち `watch: file-exists /nonexistent-probe`",
            ),
            encoding="utf-8",
        )
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert [w["task"] for w in result["watches"]] == ["T-NEW"]

    def test_an_unrenderable_store_abstains_and_names_the_row(self, tmp_path: Path):
        """The reachable trigger: `render_row` refuses an annotation the
        scanner cannot see, so one typo'd blocked row stops the render. The
        abstain must carry render's own message — it already names the task and
        the cell, and replacing it would send the operator back to running the
        render by hand to find out which row."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / "T-BAD.md").write_text(
            TASK_FILE.format(
                tid="T-BAD",
                state="blocked",
                seq=9,
                condition="なし",
                summary="待ち `watch: gh-pr a/b#1",
            ),  # never closes
            encoding="utf-8",
        )
        with pytest.raises(lcs.ScanError) as exc:
            lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert exc.value.reason == "LEDGER_UNRENDERABLE"
        assert "T-BAD" in exc.value.detail

    def test_this_module_consults_no_timestamp(self):
        """Structural, because behavioural is not available: the case that
        ruled out comparing timestamps — a render that breaks with **no store
        edit**, which `c16642c` and `8265e3c` each caused — cannot be
        distinguished from any other refused render by observing this module,
        precisely because it no longer looks at mtimes.

        A first version dressed it up as behaviour by stamping the store older
        than the projection and asserting the abstain. The stamps were inert:
        no mutation of the current code could make them load-bearing, so the
        assertion held for reasons unrelated to its name — the same class as
        the defect under repair (2026-08-15 code review LOW). What is actually
        worth pinning is that no timestamp comes back."""
        source = Path(str(lcs.__file__)).read_text(encoding="utf-8")
        for forbidden in ("st_mtime", "getmtime", "time.time"):
            assert forbidden not in source, (
                f"{forbidden} is back: a freshness *comparison* calls a week fresh "
                "whenever the render side tightens without the store changing"
            )

    def test_the_subprocess_never_asks_render_to_write(self, tmp_path: Path, monkeypatch):
        """The design rests on `render` without `--output` only printing, and
        this job runs unattended weekly. `--output` would make it edit the
        operator's ledger and silence PROJECTION_DRIFT forever (the file would
        then always match); `--allow-empty` would turn a vanished store into a
        clean zero. Neither is visible in the reading, so the argv is pinned
        directly (2026-08-15 code review LOW)."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        before = ledger.read_bytes()
        seen = {}
        real = lcs.subprocess.run

        def spy(argv, **kw):
            seen["argv"], seen["kw"] = argv, kw
            return real(argv, **kw)

        monkeypatch.setattr(lcs.subprocess, "run", spy)
        lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert "--output" not in seen["argv"]
        assert "--allow-empty" not in seen["argv"]
        assert ledger.read_bytes() == before
        # Pinned here because it is unobservable on macOS, which reports UTF-8
        # even under LC_ALL=C: the contract is what protects the Linux case.
        assert seen["kw"]["encoding"] == "utf-8"
        assert seen["kw"]["env"]["PYTHONUTF8"] == "1"
        assert seen["kw"]["stdin"] is lcs.subprocess.DEVNULL

    def test_an_empty_store_abstains_rather_than_reporting_a_clean_zero(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / "T-C.md").unlink()
        with pytest.raises(lcs.ScanError) as exc:
            lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert exc.value.reason == "LEDGER_UNRENDERABLE"
        # The code is shared with the typo case by design (splitting inside
        # exit 2 would mean pattern-matching render's prose), so the detail is
        # what has to carry the distinction — and this one is the catastrophic
        # reading: the store is gitignored with no history to restore from.
        assert "タスクがありません" in exc.value.detail

    def test_a_missing_store_abstains(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / "T-C.md").unlink()
        (root / ".notes" / "tasks").rmdir()
        with pytest.raises(lcs.ScanError) as exc:
            lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert exc.value.reason == "LEDGER_UNRENDERABLE"
        assert "タスクがありません" in exc.value.detail

    def test_a_hung_render_is_named_separately_from_a_refused_one(self, tmp_path: Path):
        """Different repair: a hang is not a task to go fix. Collapsing the two
        would point the operator at a row that is not the problem."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        with pytest.raises(lcs.ScanError) as exc:
            lcs.render_from_store(root, timeout=0.001)
        assert exc.value.reason == "RENDER_TIMEOUT"

    def test_a_renderer_that_crashes_is_not_reported_as_a_bad_store(
        self, tmp_path: Path, monkeypatch
    ):
        """`cmd_render` exits 2 for "I refuse this store"; anything else is the
        renderer or its environment falling over. Collapsing them sent the
        operator hunting for a bad task file when the real cause was e.g. a
        locale the child cannot encode the Japanese table into — measured under
        LC_ALL=en_US.ISO8859-1 (2026-08-15 code review MEDIUM)."""
        crasher = tmp_path / "crash.py"
        crasher.write_text("import sys; sys.stderr.write('boom'); sys.exit(1)", encoding="utf-8")
        monkeypatch.setattr(lcs, "_TASKS_PY", crasher)
        with pytest.raises(lcs.ScanError) as exc:
            lcs.render_from_store(tmp_path)
        assert exc.value.reason == "RENDER_FAILED"

    @pytest.mark.parametrize("missing", ["script", "interpreter"])
    def test_a_missing_renderer_is_named_rather_than_crashing(
        self, tmp_path: Path, monkeypatch, missing: str
    ):
        """One at a time: patching both at once meant neither was shown to
        produce the code on its own (2026-08-15 code review LOW)."""
        if missing == "script":
            monkeypatch.setattr(lcs, "_TASKS_PY", tmp_path / "not-here.py")
        else:
            monkeypatch.setattr(lcs.sys, "executable", str(tmp_path / "no-python"))
        with pytest.raises(lcs.ScanError) as exc:
            lcs.render_from_store(tmp_path)
        assert exc.value.reason == "RENDER_UNAVAILABLE"


class TestProjectionDrift:
    """A stale `.notes/TASKS.md` is reported, never fatal, and under its own name.

    The reading is over the store, so a drifted file cannot corrupt it — but it
    is the file a human opens, and letting it drift in silence is how the
    operator's view and the gate's view come apart. Fatal would be worse than
    useless: the store routinely runs ahead of the projection between hand
    renders (`claims.py` unions both for exactly that reason), so abstaining on
    drift would fail most weeks until the alarm meant nothing — the original
    failure returning through the alarm-fatigue door (2026-08-15 code review
    MEDIUM).
    """

    def test_a_fresh_projection_reports_no_drift(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [PLAIN_READY])
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert result["projection_drift"] is None
        assert result["errors"] == []

    def test_a_drifted_projection_is_reported_without_losing_the_reading(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [BLOCKED_ON_FILE])
        ledger.write_text("| T-GONE | blocked | 古い表 | — | — |\n", encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        # The reading still happened, and it is the store's, not the file's.
        assert [w["task"] for w in result["watches"]] == ["T-B"]
        assert result["projection_drift"]["reason"] == "PROJECTION_DRIFT"
        # How far apart, not just that they disagree: the deleted LEDGER_STALE
        # named the witness and both timestamps, and "they differ" alone is the
        # weaker statement (2026-08-15 code review LOW).
        assert "file 1 行" in result["projection_drift"]["detail"]

    def test_an_absent_projection_is_drift_not_a_fault(self, tmp_path: Path):
        ledger, root = _store(tmp_path, [BLOCKED_ON_FILE], render=False)
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert result["watch_count"] == 1
        assert result["projection_drift"]["reason"] == "PROJECTION_DRIFT"

    def test_drift_does_not_ride_in_the_watch_error_channel(self, tmp_path: Path):
        """`errors` means "a watch annotation could not be parsed" — the packet
        counts its entries and prints "N 件の watch 注釈が解釈不能 — 注釈構文を
        確認", discarding reason and detail. Routing drift through it delivered
        a true signal under a false name, with advice that does not apply
        (2026-08-15 cross-model review P2)."""
        ledger, root = _store(
            tmp_path, [{"tid": "T-A", "state": "blocked", "summary": "`watch: gh-pr`"}]
        )
        ledger.write_text("drifted\n", encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert [e["reason"] for e in result["errors"]] == ["MALFORMED_WATCH"]
        assert result["projection_drift"]["reason"] == "PROJECTION_DRIFT"

    def test_the_repair_command_names_the_root_it_was_read_from(self, tmp_path: Path):
        """Without `--root`, `tasks.py` renders its *default* store — so for a
        ledger outside this repo the suggested command would overwrite that
        ledger with this repo's tasks (2026-08-15 cross-model review P2)."""
        ledger, root = _store(tmp_path, [PLAIN_READY], render=False)
        detail = lcs.scan(ledger, fetch=_fetch_json({}), root=root)["projection_drift"]["detail"]
        assert f"--root {root} render --output {ledger}" in detail

    def test_an_undecodable_projection_is_drift_not_a_traceback(self, tmp_path: Path):
        """`read_text` raises UnicodeDecodeError — a ValueError, not an
        OSError — so a corrupt projection escaped `main`'s ScanError handler as
        a traceback with no reason code, losing the `LEDGERWATCH_FAIL reason=`
        line the weekly chain greps out of the stage's err file (2026-08-15
        cross-model review P2)."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        ledger.write_bytes(b"\xff\xfe not utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({}), root=root)
        assert result["projection_drift"]["reason"] == "PROJECTION_DRIFT"

    @pytest.mark.parametrize("hostile", ["\x1b[31m", "\u202e", "\x9b", "\u200b"])
    def test_the_drift_detail_cannot_carry_terminal_control(self, tmp_path: Path, hostile: str):
        """This detail lands in the retained JSON as well as on stderr, and
        `main`'s sink sanitiser only covers the abstain line — so the ledger
        path, which is operator-supplied and unconstrained, needs sanitising
        where it is composed (2026-08-15 cross-model review P3)."""
        _, root = _store(tmp_path, [PLAIN_READY], render=False)
        ledger = root / ".notes" / f"TASKS{hostile}.md"
        detail = lcs.scan(ledger, fetch=_fetch_json({}), root=root)["projection_drift"]["detail"]
        assert hostile not in detail


class TestUnrenderedSource:
    """`root=None` — read the file, and say so."""

    def test_reading_a_file_is_labelled_as_such(self, tmp_path: Path):
        ledger = tmp_path / "TASKS.md"
        ledger.write_text(LEDGER, encoding="utf-8")
        result = lcs.scan(ledger, fetch=_fetch_json({"state": "open"}), root=None)
        assert result["source"] == "file"
        assert result["watch_count"] == 2

    def test_the_cli_derives_the_root_from_the_ledger(self, tmp_path: Path, capsys):
        """The production path: the pipeline passes `--ledger` and never
        `--root`, so this derivation is the whole of it."""
        ledger, _ = _store(tmp_path, [BLOCKED_ON_FILE])
        assert lcs.main(["--ledger", str(ledger)]) == 0
        assert json.loads(capsys.readouterr().out)["source"] == "store"

    def test_the_cli_abstains_when_the_derived_store_cannot_render(self, tmp_path: Path, capsys):
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / "T-C.md").unlink()
        assert lcs.main(["--ledger", str(ledger)]) != 0
        assert "reason=LEDGER_UNRENDERABLE" in capsys.readouterr().err

    def test_an_explicit_root_overrides_the_derivation(self, tmp_path: Path, capsys):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        _store(elsewhere, [PLAIN_READY])
        (elsewhere / ".notes" / "tasks" / "T-C.md").unlink()
        stray = tmp_path / "TASKS.md"
        stray.write_text(LEDGER, encoding="utf-8")
        assert lcs.main(["--ledger", str(stray), "--root", str(elsewhere)]) != 0
        assert "reason=LEDGER_UNRENDERABLE" in capsys.readouterr().err

    @pytest.mark.parametrize("hostile", ["\x1b[31m", "\u202e", "\x9b", "\u200b"])
    def test_the_abstain_line_cannot_carry_terminal_control(
        self, tmp_path: Path, capsys, hostile: str
    ):
        """Asserted through `main`, because stderr is the sink: the line is
        printed raw to a terminal and retained in `ledgerwatch.err`. The detail
        carries `tasks.py render`'s stderr, so the sanitiser has to sit at the
        sink rather than at each raise site, where one raw field would keep
        slipping past (2026-08-15 security review LOW).

        **The hostile bytes go in the store *filename*, not a task body.** A
        first version put them in the summary and passed with the sink
        sanitiser deleted: `render_row` formats cells with `!r`, and `repr`
        escapes on `str.isprintable()`, so the characters never reached the
        detail raw and the assertion was about `repr` rather than about this
        module. `load_store` interpolates `path.name` bare — measured — which
        is the path that actually reaches stderr unescaped.

        Four classes, not just ESC: `_printable`'s argument for using
        `str.isprintable()` is that it covers Cc/Cf/Cs/Co/Cn/Zl/Zp, and a test
        exercising ESC alone would pass against a bare C0 filter."""
        ledger, root = _store(tmp_path, [PLAIN_READY])
        (root / ".notes" / "tasks" / f"T-{hostile}BAD.md").write_text("x", encoding="utf-8")
        assert lcs.main(["--ledger", str(ledger)]) != 0
        err = capsys.readouterr().err
        assert hostile not in err
        assert "BAD.md" in err
