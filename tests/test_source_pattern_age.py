"""Tests for scripts/source_pattern_age.py — source-pattern age of selected skills (RFC-0071 P3-01.3).

Three properties are pinned on a synthetic MOLTBOOK_HOME: the age arithmetic
(selection time minus the median creation time of the adoption row's source
patterns), the reason code of every way a trace can fail (no row is dropped
silently), and the output boundary (ADR-0083: no ``reason``, pattern text,
prompt text or pattern id leaves the script).
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import source_pattern_age as spa  # noqa: E402  # pyright: ignore[reportMissingImports]

from contemplative_agent.core.knowledge_store import pattern_id as core_pattern_id

BODY_PATTERN = "BODY-PATTERN-TEXT"
BODY_REASON = "BODY-REASON-TEXT"
BODY_PROMPT = "BODY-PROMPT-TEXT"


def _pattern(distilled: str, n: int) -> dict:
    return {"pattern": f"{BODY_PATTERN} {n}", "distilled": distilled, "gated": False}


def _pid(p: dict) -> str:
    return hashlib.sha256(f"{p['distilled']}|{p['pattern']}".encode()).hexdigest()[:12]


def _skill(d: Path, slug: str, name: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(f"---\nname: {name}\n---\n# Title\nbody\n", encoding="utf-8")


def _approved(slug: str, ts: str, command: str = "insight", source_ids=None) -> dict:
    row = {
        "ts": ts,
        "command": command,
        "path": f"/home/x/skills/{slug}.md",
        "decision": "approved",
        "source": "stage-adopted",
        "content_hash": "0" * 16,
        "reason": BODY_REASON,
    }
    if source_ids is not None:
        row["source_ids"] = source_ids
    return row


def _selection(ts: str, selected: list[str], catalog: list[str], verdict: str = "judged") -> dict:
    return {
        "kind": "selection",
        "ts": ts,
        "verdict": verdict,
        "enforced": True,
        "selected": selected,
        "catalog_names": catalog,
        "prompt_b64": base64.b64encode(BODY_PROMPT.encode()).decode(),
    }


def _home(tmp_path: Path) -> tuple[Path, list[str]]:
    home = tmp_path / "home"
    logs = home / "logs"
    logs.mkdir(parents=True)
    # alpha's three source patterns: median creation 2026-08-27 -> 5.0 weeks
    # before the 2026-10-01 selection.
    alpha_patterns = [
        _pattern("2026-08-25T00:00+00:00", 1),
        _pattern("2026-08-27T00:00+00:00", 2),
        _pattern("2026-09-10T00:00+00:00", 3),
    ]
    alpha_ids = [_pid(p) for p in alpha_patterns]
    (home / "knowledge.json").write_text(json.dumps(alpha_patterns), encoding="utf-8")

    live = home / "skills"
    _skill(live, "alpha-20260901", "alpha")  # name differs from the slug
    _skill(live, "gamma-20260415", "gamma")  # adopted before source_ids existed
    _skill(live, "eps-20260901", "eps")  # source ids absent from knowledge
    _skill(live, "zeta-20261005", "zeta")  # adopted after the selection
    _skill(live / ".archive", "theta-20260801", "theta")  # retired, no audit row at all
    _skill(home / "snapshots" / "insight_20260901" / "skills", "delta-20260601", "delta")
    _skill(live, "dup-a", "dup")
    _skill(home / "snapshots" / "insight_20260901" / "skills", "dup-b", "dup")

    audit = [
        _approved("alpha-20260901", "2026-09-01T00:00:00+00:00", source_ids=alpha_ids),
        _approved("gamma-20260415", "2026-04-15T00:00:00+00:00"),
        _approved("eps-20260901", "2026-09-01T00:00:00+00:00", source_ids=["ffffffffffff"]),
        _approved("zeta-20261005", "2026-10-05T00:00:00+00:00", source_ids=alpha_ids),
        _approved("delta-20260601", "2026-06-01T00:00:00+00:00", command="skill-stocktake"),
        {**_approved("alpha-20260901", "2026-09-01T00:00:00+00:00"), "decision": "rejected"},
    ]
    (logs / "audit.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in audit), encoding="utf-8"
    )

    names = ["alpha", "beta", "gamma", "delta", "eps", "zeta", "theta", "dup"]
    records = [
        _selection("2026-10-01T00:00:00+00:00", [*names, "alpha"], names),
        _selection("2026-10-01T06:00:00+00:00", [], names, verdict="fail_open_llm"),
        _selection("2026-09-01T00:00:00+00:00", ["alpha"], names),  # outside the window
        {"kind": "publish", "ts": "2026-10-01T00:00:00+00:00", "selected": ["alpha"]},
    ]
    (logs / "skill-selection-2026-10-01.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    return home, alpha_ids


def _render(home: Path) -> str:
    return spa.render(spa.load_inputs(home), date(2026, 9, 15), date(2026, 10, 31))


def test_pattern_id_mirrors_the_store() -> None:
    p = _pattern("2026-08-25T00:00+00:00", 1)
    assert spa.pattern_id(p) == core_pattern_id(p)


def test_age_is_selection_minus_median_source_creation(tmp_path: Path) -> None:
    home, _ = _home(tmp_path)
    inp = spa.load_inputs(home)
    t = spa.trace("alpha", datetime(2026, 10, 1, tzinfo=UTC), inp)
    assert t.reason is None
    assert t.age_weeks == 5.0
    assert t.source_week == "2026-W35"
    assert t.spread_weeks is not None and round(t.spread_weeks, 2) == round(16 / 7, 2)


def test_every_untraced_name_gets_its_reason_code(tmp_path: Path) -> None:
    home, _ = _home(tmp_path)
    inp = spa.load_inputs(home)
    at = datetime(2026, 10, 1, tzinfo=UTC)
    reasons = {
        n: spa.trace(n, at, inp).reason
        for n in ("beta", "gamma", "delta", "eps", "zeta", "theta", "dup")
    }
    assert reasons == {
        "beta": spa.NAME_UNMAPPED,
        "gamma": spa.ADOPTION_ROW_WITHOUT_SOURCE_IDS,
        "delta": spa.ADOPTED_WITHOUT_INSIGHT_ROW,
        "eps": spa.SOURCE_PATTERN_MISSING,
        "zeta": spa.ADOPTION_AFTER_SELECTION,
        "theta": spa.NO_ADOPTION_ROW,
        "dup": spa.NAME_AMBIGUOUS,
    }


def test_window_dedup_and_counts(tmp_path: Path) -> None:
    home, _ = _home(tmp_path)
    inp = spa.load_inputs(home)
    calls = [c for c in inp.calls if spa.in_window(c.ts, date(2026, 9, 15), date(2026, 10, 31))]
    assert len(calls) == 1  # the 09-01 record is outside, publish rows are not selections
    sel = spa.distribution([(n, c.ts) for c in calls for n in c.selected], inp)
    assert sel.total == 8  # "alpha" twice in one record counts once
    assert sel.ages == (5.0,)
    assert sum(sel.reasons.values()) == 7
    assert sel.missing_ids == 1  # eps's one absent source id
    out = _render(home)
    assert "| selected | 8 | 1/8 | 7 |" in out
    assert "fail-open records in window (select nothing): 1" in out


def test_corpus_ages_only_patterns_created_by_the_reference_time(tmp_path: Path) -> None:
    home, _ = _home(tmp_path)
    inp = spa.load_inputs(home)
    # 2026-09-01: the 08-25 and 08-27 patterns exist (1.0 and 5/7 weeks old), 09-10 does not.
    ages = spa.corpus_ages(inp, datetime(2026, 9, 1, tzinfo=UTC))
    assert sorted(round(a, 4) for a in ages) == [round(5 / 7, 4), 1.0]
    assert spa.corpus_ages(inp, None) == ()


def test_output_carries_no_body_reason_or_id(tmp_path: Path) -> None:
    home, alpha_ids = _home(tmp_path)
    out = _render(home)
    for body in (BODY_PATTERN, BODY_REASON, BODY_PROMPT, *alpha_ids, "ffffffffffff"):
        assert body not in out
    assert base64.b64encode(BODY_PROMPT.encode()).decode() not in out


def test_unsafe_name_characters_are_masked() -> None:
    assert spa.safe_name("ok-name_1.2") == "ok-name_1.2"
    assert spa.safe_name("bad|name\nx") == "bad?name?x"


def test_main_reads_only_and_exits_zero(tmp_path: Path, capsys) -> None:
    home, _ = _home(tmp_path)
    before = sorted(p.relative_to(home) for p in home.rglob("*"))
    assert spa.main(["--home", str(home), "--start", "2026-09-15", "--end", "2026-10-31"]) == 0
    assert "Source-pattern age" in capsys.readouterr().out
    assert sorted(p.relative_to(home) for p in home.rglob("*")) == before
