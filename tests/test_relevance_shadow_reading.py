"""The relevance shadow reading (scripts/relevance_shadow_reading.py, RFC-0046).

Pinned: the window is by the file's UTC day; only answered rows enter the
would-be gate and agreement; the three candidate cuts; latency percentiles;
the ISO-week split; ``content_b64`` never reaches the output; the script is
stdlib-only.
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
    def test_six_summary_lines_then_json_and_no_body(self, tmp_path, capsys):
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
        assert json.loads("\n".join(lines[6:])) == json.loads(out_json.read_text())
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
