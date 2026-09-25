"""The relevance shadow reading (scripts/relevance_shadow_reading.py, RFC-0046).

Pinned: the window is by the file's UTC day; only answered rows enter the
would-be gate and agreement; the three candidate cuts; latency percentiles;
the ISO-week split; ``content_b64`` never reaches the output; the script is
stdlib-only. Schema 2 adds the ``readiness`` section (RFC-0047 row clock):
rows since the switch, post_id dedupe, the two-rate reach projection for n, and
the enforce fields' split — the v1 aggregates are unchanged.
"""

from __future__ import annotations

import ast
import base64
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "relevance_shadow_reading.py"
SECRET = "a post body that must never be printed"


def _load():
    spec = importlib.util.spec_from_file_location("relevance_shadow_reading", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["relevance_shadow_reading"] = module
    spec.loader.exec_module(module)
    return module


rd = _load()


def _row(gate, reason="answered", p_top=None, latency=None, live_reason="scored"):
    return {
        "ts": "2026-09-28T01:00:00+00:00",
        "live_reason": live_reason,
        "live_gate": gate,
        "live_score": 0.9 if gate else 0.3,
        "decision_reason": reason,
        "decision_p_top": p_top,
        "decision_latency_ms": latency,
        "content_b64": base64.b64encode(SECRET.encode()).decode(),
    }


def _write(home: Path, day: str, rows: list[dict]) -> None:
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"relevance-{day}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    _write(
        home,
        "2026-09-28",
        [
            _row(True, p_top=0.9, latency=1000),  # would gate at every cut, agrees
            _row(True, p_top=0.4, latency=3000),  # would gate at 0.3 only
            _row(False, p_top=0.2, latency=2000),  # gates nowhere, agrees
            _row(False, reason="unconfigured"),  # not answered: out of the cuts
            # An outage 0.0 is an event, not a judgment: out of every rate.
            _row(False, p_top=0.9, latency=5, live_reason="llm_unavailable"),
        ],
    )
    _write(home, "2026-10-05", [_row(False, p_top=0.6, latency=4000)])  # next ISO week
    _write(home, "2026-10-20", [_row(True, p_top=0.9, latency=9)])  # outside the window
    return home


class TestReading:
    def test_totals(self, tmp_path):
        result = rd.reading(_home(tmp_path) / "logs", date(2026, 9, 28), date(2026, 10, 5))
        total = result["total"]
        assert total["rows"] == 6
        assert total["live_scored"] == 5
        assert total["answered"] == 4
        assert total["answered_rate"] == 0.8
        assert total["decision_reasons"] == {"answered": 5, "unconfigured": 1}
        assert total["live_gate_rate"] == 0.4
        assert total["live_gate_rate_answered"] == 0.5

    def test_the_candidate_cuts_read_answered_rows_only(self, tmp_path):
        result = rd.reading(_home(tmp_path) / "logs", date(2026, 9, 28), date(2026, 10, 5))
        cuts = result["total"]["thresholds"]
        assert set(cuts) == {"0.3", "0.5", "0.7"}
        # p_top 0.9 / 0.4 / 0.2 / 0.6 against live True / True / False / False
        assert cuts["0.3"] == {"would_gate_rate": 0.75, "agreement_with_live": 0.75}
        assert cuts["0.5"] == {"would_gate_rate": 0.5, "agreement_with_live": 0.5}
        assert cuts["0.7"] == {"would_gate_rate": 0.25, "agreement_with_live": 0.75}

    def test_latency_percentiles_and_weeks(self, tmp_path):
        result = rd.reading(_home(tmp_path) / "logs", date(2026, 9, 28), date(2026, 10, 5))
        # Latency is the shadow's cost on every row it ran on, outage rows too.
        assert result["total"]["latency_ms_p50"] == 2000
        assert result["total"]["latency_ms_p95"] == 4000
        assert list(result["weeks"]) == ["2026-W40", "2026-W41"]
        assert result["weeks"]["2026-W41"]["rows"] == 1

    def test_an_empty_window_reads_as_nulls_not_zeros(self, tmp_path):
        result = rd.reading(tmp_path / "nothing", date(2026, 9, 1), date(2026, 9, 2))
        assert result["total"]["rows"] == 0
        assert result["total"]["answered_rate"] is None
        assert result["total"]["thresholds"]["0.5"]["would_gate_rate"] is None

    def test_a_broken_line_is_counted_not_fatal(self, tmp_path):
        home = _home(tmp_path)
        with (home / "logs" / "relevance-2026-09-28.jsonl").open("a", encoding="utf-8") as f:
            f.write("{not json\n")
        result = rd.reading(home / "logs", date(2026, 9, 28), date(2026, 9, 28))
        assert result["parse_failures"] == 1


class TestOutput:
    def test_seven_summary_lines_then_json_and_no_body(self, tmp_path, capsys):
        home = _home(tmp_path)
        out_json = tmp_path / "reading.json"
        code = rd.main(
            [
                "--home",
                str(home),
                "--start",
                "2026-09-28",
                "--end",
                "2026-10-05",
                "--json-out",
                str(out_json),
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        assert json.loads("\n".join(lines[7:])) == json.loads(out_json.read_text())
        assert lines[6].startswith("n=300 到達: ")
        assert lines[0].startswith("relevance shadow 2026-09-28..2026-10-05")
        assert SECRET not in out
        assert base64.b64encode(SECRET.encode()).decode() not in out

    def test_the_script_is_stdlib_only(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= set(sys.stdlib_module_names)


def _paired(
    ts,
    post_id,
    *,
    gate_source="score4",
    enforce_gate: bool | None = True,
    live_gate=True,
    reason="enforced",
    p_top=0.9,
):
    return {
        "ts": ts,
        "post_id": post_id,
        "live_reason": "scored",
        "live_gate": live_gate,
        "decision_reason": "answered",
        "decision_p_top": p_top,
        "decision_latency_ms": 100,
        "gate_source": gate_source,
        "enforce_gate": enforce_gate,
        "enforce_reason": reason,
        "content_b64": base64.b64encode(SECRET.encode()).decode(),
    }


def _readiness_home(tmp_path: Path) -> Path:
    home = tmp_path / "rhome"
    _write(
        home,
        "2026-09-25",
        [
            _paired(
                "2026-09-25T00:00:00+00:00",
                "old",
                gate_source="live",
                enforce_gate=None,
                reason="enforce_unconfigured",
            ),  # before the switch
            _paired("2026-09-25T12:00:00+00:00", "a"),
            _paired("2026-09-25T18:00:00+00:00", "a", enforce_gate=False),  # same post again
        ],
    )
    _write(
        home,
        "2026-09-26",
        [
            _paired("2026-09-26T06:00:00+00:00", "b", enforce_gate=False, live_gate=False),
            _paired(
                "2026-09-26T09:00:00+00:00",
                "c",
                gate_source="live",
                enforce_gate=None,
                reason="enforce_backend_null",
            ),
            _paired("2026-09-26T12:00:00+00:00", "d"),
        ],
    )
    return home


class TestReadiness:
    def _read(self, tmp_path, n=10):
        return rd.reading(
            _readiness_home(tmp_path) / "logs",
            date(2026, 9, 25),
            date(2026, 9, 26),
            since=rd.parse_since("2026-09-25T12:00:00Z"),
            n=n,
        )

    def test_schema_is_2_and_v1_totals_stand(self, tmp_path):
        result = self._read(tmp_path)
        assert result["schema"] == "relevance-shadow-reading/2"
        # the whole window, the switch notwithstanding
        assert result["total"]["rows"] == 6

    def test_rows_since_the_switch_and_dedupe(self, tmp_path):
        r = self._read(tmp_path)["readiness"]
        assert r["since"] == "2026-09-25T12:00:00+00:00"
        assert r["n"] == 10
        assert r["answered_rows"] == 5
        assert r["answered_dedupe"] == 4

    def test_two_rates_and_the_projection(self, tmp_path):
        r = self._read(tmp_path)["readiness"]
        # 5 rows over the 1.0 day from the switch to the last row
        assert r["rate_per_day_all"] == 5.0
        # last 24h ending at the last row: rows after 2026-09-25T12:00 exclusive = 4
        assert r["rate_per_day_last_day"] == 4.0
        # 5 more rows at 4..5 rows/day from 2026-09-26T12:00
        assert r["reach_dates"] == ["2026-09-27", "2026-09-27"]
        assert r["reached"] is False

    def test_projection_width_orders_the_dates(self, tmp_path):
        r = self._read(tmp_path, n=25)["readiness"]
        # 20 more: 20/5 = 4 days -> 09-30, 20/4 = 5 days -> 10-01
        assert r["reach_dates"] == ["2026-09-30", "2026-10-01"]

    def test_reached(self, tmp_path):
        r = self._read(tmp_path, n=5)["readiness"]
        assert r["reached"] is True

    def test_the_enforce_split(self, tmp_path):
        r = self._read(tmp_path)["readiness"]
        assert r["gate_source"] == {"live": 1, "score4": 4}
        # enforce_gate vs live_gate over the 4 enforced rows: a T/T, a F/T, b F/F, d T/T
        assert r["enforce_live_agreement"] == 0.75
        assert r["enforce_reasons"] == {"enforce_backend_null": 1, "enforced": 4}

    def test_no_rows_since_reads_as_nulls(self, tmp_path):
        r = rd.reading(tmp_path / "none", date(2026, 9, 25), date(2026, 9, 26), since=None, n=300)[
            "readiness"
        ]
        assert r["answered_rows"] == 0
        assert r["reach_dates"] is None
        assert r["rate_per_day_all"] is None

    def test_the_since_default_is_the_window_start(self, tmp_path):
        result = rd.reading(
            _readiness_home(tmp_path) / "logs", date(2026, 9, 25), date(2026, 9, 26)
        )
        assert result["readiness"]["since"] == "2026-09-25T00:00:00+00:00"
        assert result["readiness"]["n"] == 300
        assert result["readiness"]["answered_rows"] == 6

    def test_summary_line_names_the_reach(self, tmp_path):
        result = self._read(tmp_path)
        line = rd.summary_lines(result)[6]
        assert line == "n=10 到達: 2026-09-27〜2026-09-27 見込み（4.0〜5.0 行/日、dedupe 後 4 行）"
