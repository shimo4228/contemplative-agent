"""RFC-0017 S4: the offline replay driver and the paper capacity it exercises.

The driver is a calendar and a copier around loops that are already tested
(S2/S3), so what is fixed here is the part only the driver decides: which day
runs which loop, that the production store is copied and never written, that
a July iteration cannot read August's ledgers, and that ``summary.json``'s
two derived ratios (M-a's verification pass rate, M-b's patch ratio) are
computed from the ops rather than from the runs.

The paper capacity is tested through the loops it changes: the whole wiki
arrives in the first prompt, no ``open`` turn is offered, and a day that does
not fit is ``fail_closed_budget`` rather than a quietly smaller sample.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from contemplative_agent.core import wiki_maintainer, wiki_proposer
from contemplative_agent.core.llm import BackendResult, configure, reset_llm_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import wiki_replay  # noqa: E402  # pyright: ignore[reportMissingImports]

MONDAY = date(2026, 8, 3)  # 2026-08-03 is a Monday
TUESDAY = date(2026, 8, 4)


@dataclass
class FakeBackend:
    """Queued responses, one per generate() call. ``None`` = hard failure."""

    model: str = "fake-model"
    context_window: int = 32768
    responses: list[str | None] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def generate(
        self,
        prompt: str,
        system: str,
        num_predict: int,
        format: dict | None,
        *,
        temperature: float = 1.0,
        think: bool = False,
    ) -> BackendResult | None:
        self.calls.append({"prompt": prompt, "format": format})
        item = self.responses.pop(0) if self.responses else None
        return None if item is None else BackendResult(text=item)


@pytest.fixture(autouse=True)
def _clean_llm():
    reset_llm_config()
    yield
    reset_llm_config()


def _episode(ts: str) -> dict:
    return {
        "ts": ts,
        "type": "activity",
        "data": {
            "action": "comment",
            "post_id": "p1",
            "content": "a durable observation about rate limits",
            "original_post": "a peer post",
            "internal_note": "what I noticed",
        },
    }


def _source_store(tmp_path: Path, days: list[date]) -> Path:
    """A miniature production store: episodes, ledgers, one skill."""
    source = tmp_path / "production"
    (source / "logs").mkdir(parents=True)
    (source / "skills").mkdir(parents=True)
    for index, day in enumerate(days):
        (source / "logs" / f"{day.isoformat()}.jsonl").write_text(
            json.dumps(_episode(f"{day.isoformat()}T0{index}:00:00+00:00")) + "\n",
            encoding="utf-8",
        )
    (source / "logs" / "insight-staged.jsonl").write_text(
        json.dumps({"ts": "2026-07-01T00:00+00:00", "name": "early", "filename": "early.md"})
        + "\n"
        + json.dumps({"ts": "2026-09-01T00:00+00:00", "name": "future", "filename": "future.md"})
        + "\n",
        encoding="utf-8",
    )
    (source / "logs" / "audit.jsonl").write_text("", encoding="utf-8")
    (source / "skills" / "rate-limits.md").write_text(
        "---\nname: rate-limits\ndescription: back off on 429\n---\n\nWait, do not retry.\n",
        encoding="utf-8",
    )
    return source


# ------------------------------------------------------------------ calendar


def test_days_in_range_is_inclusive_and_truncatable():
    days = wiki_replay.days_in_range(date(2026, 7, 9), date(2026, 7, 12), None)
    assert days == [date(2026, 7, 9 + n) for n in range(4)]
    assert wiki_replay.days_in_range(date(2026, 7, 9), date(2026, 7, 12), 2) == days[:2]
    assert wiki_replay.days_in_range(date(2026, 7, 12), date(2026, 7, 9), None) == []


def test_the_proposer_runs_only_on_its_weekday(tmp_path):
    days = [MONDAY, TUESDAY]
    source = _source_store(tmp_path, days)
    backend = FakeBackend(responses=['{"action": "abstain", "reason": "nothing"}'] * 12)

    summary = wiki_replay.run_arm(
        wiki_replay.ARMS["opus-constrained"],
        source=source,
        home=tmp_path / "replay",
        days=days,
        proposer_weekday=0,
        verbose=False,
        backend_override=backend,
    )
    assert summary["maintainer"]["runs"] == 2
    assert summary["proposer"]["runs"] == 1
    assert summary["days"] == 2


def test_a_different_proposer_weekday_moves_the_iteration(tmp_path):
    days = [MONDAY, TUESDAY]
    source = _source_store(tmp_path, days)
    summary = wiki_replay.run_arm(
        wiki_replay.ARMS["opus-constrained"],
        source=source,
        home=tmp_path / "replay",
        days=days,
        proposer_weekday=1,
        verbose=False,
        backend_override=FakeBackend(responses=['{"action": "abstain"}'] * 12),
    )
    assert summary["proposer"]["runs"] == 1
    assert summary["wiki_daily"][0]["date"] == MONDAY.isoformat()


# --------------------------------------------------------------- containment


def test_the_source_store_is_never_written_to(tmp_path):
    days = [MONDAY]
    source = _source_store(tmp_path, days)
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    wiki_replay.run_arm(
        wiki_replay.ARMS["opus-constrained"],
        source=source,
        home=tmp_path / "replay",
        days=days,
        proposer_weekday=0,
        verbose=False,
        backend_override=FakeBackend(responses=[_write_turn(MONDAY)] * 4),
    )
    after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert after == before
    assert not (source / "wiki").exists()
    assert (tmp_path / "replay" / "opus-constrained" / "wiki" / "patterns").is_dir()


def test_home_inside_the_production_store_is_refused(tmp_path):
    source = tmp_path / "production"
    source.mkdir()
    assert wiki_replay.refuse_production_home(source / "replay", source) is not None
    assert wiki_replay.refuse_production_home(source, source) is not None
    assert wiki_replay.refuse_production_home(tmp_path / "elsewhere", source) is None


def test_home_has_no_default(tmp_path):
    parser = wiki_replay.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--from", "2026-07-09", "--to", "2026-07-10"])


def test_main_refuses_a_home_under_the_production_store(tmp_path, capsys):
    source = tmp_path / "production"
    (source / "logs").mkdir(parents=True)
    with pytest.raises(SystemExit):
        wiki_replay.main(
            [
                "--home",
                str(source / "inside"),
                "--source",
                str(source),
                "--from",
                "2026-08-03",
                "--to",
                "2026-08-03",
            ]
        )
    assert "overlaps the production store" in capsys.readouterr().err


def test_only_the_replayed_days_are_copied(tmp_path):
    days = [MONDAY, TUESDAY]
    source = _source_store(tmp_path, days + [date(2026, 8, 20)])
    copied = wiki_replay.prepare_arm_home(source, tmp_path / "arm", days)
    assert copied["episode_days"] == 2
    assert not (tmp_path / "arm" / "logs" / "2026-08-20.jsonl").exists()
    assert (tmp_path / "arm" / "skills" / "rate-limits.md").is_file()


def test_a_missing_day_is_counted_not_fatal(tmp_path):
    source = _source_store(tmp_path, [MONDAY])
    copied = wiki_replay.prepare_arm_home(source, tmp_path / "arm", [MONDAY, TUESDAY])
    assert (copied["episode_days"], copied["missing_days"]) == (1, 1)


# ------------------------------------------------------------------- windows


def test_the_proposer_cannot_read_a_ledger_row_from_after_the_replayed_day(tmp_path):
    """`until` is what makes a replayed July iteration honest (S4 goal 3)."""
    source = _source_store(tmp_path, [MONDAY])
    backend = FakeBackend(responses=['{"action": "abstain"}'] * 6)

    wiki_replay.run_arm(
        wiki_replay.ARMS["opus-constrained"],
        source=source,
        home=tmp_path / "replay",
        days=[MONDAY],
        proposer_weekday=0,
        verbose=False,
        backend_override=backend,
    )
    proposer_prompts = [c["prompt"] for c in backend.calls if "Evolution log" in c["prompt"]]
    assert proposer_prompts, "the proposer never ran"
    assert "early" in proposer_prompts[0]
    assert "future" not in proposer_prompts[0]


# ------------------------------------------------------------------- summary


def _write_turn(day: date, op: str = "create") -> str:
    """A write whose citation is a ts the sample really rendered.

    An empty ``sources`` is refused by the store (``SOURCES_EMPTY``), so a
    test that used one would assert about refusals while believing it was
    asserting about writes.
    """
    source = f"{day.isoformat()}T00:00:00+00:00"
    ops = {
        "create": {
            "op": "create",
            "title": "Rate limits",
            "body": "Back off.",
            "sources": [source],
        },
        "append": {"op": "append", "page_id": "p-0001", "text": "More.", "sources": [source]},
    }[op]
    return json.dumps({"action": "write", "ops": [ops]})


def test_open_and_unoffered_refusals_stay_out_of_the_m_a_denominator(tmp_path):
    """M-a counts ops the model emitted; a bad page id is a hallucination reading."""
    tally = wiki_replay.ArmTally()
    tally.add_maintainer(
        wiki_maintainer.MaintainerRun(
            date=MONDAY.isoformat(),
            seed="s",
            outcome="written",
            reason=None,
            episode_ids_read=(),
            episode_ids_skipped=(),
            opened_page_ids=(),
            ops_applied=("create p-0001",),
            ops_refused=(
                ("open", "UNKNOWN_PAGE_ID"),
                ("open", "MAX_OPENS_REACHED"),
                ("write", "UNOFFERED_ACTION"),
                ("append", "ANCHOR_NOT_FOUND"),
            ),
            budget={"episodes": 1},
            wiki_size=wiki_maintainer.WikiSize(pages=1, index_tokens=1, page_chars_p90=1),
            dry_run=False,
        )
    )

    assert (tally.ops_applied, tally.ops_refused) == (1, 1)
    assert tally.refusal_reasons["open:UNKNOWN_PAGE_ID"] == 1
    assert tally.refusal_reasons["write:UNOFFERED_ACTION"] == 1


def test_summary_ratios_are_computed_over_ops_not_runs(tmp_path):
    tally = wiki_replay.ArmTally(
        op_classes={"create": 1, "append": 3},
        ops_applied=4,
        ops_refused=1,
    )
    summary = wiki_replay.build_summary(
        wiki_replay.ARMS["gemma-constrained"],
        served_model="gemma4:e4b",
        days=[MONDAY],
        copied={},
        tally=tally,
        arm_root=tmp_path,
        elapsed=1.0,
        usage=None,
    )
    assert summary["maintainer"]["verification_pass_rate"] == pytest.approx(0.8)
    assert summary["maintainer"]["patch_ratio"] == pytest.approx(0.75)


def test_summary_ratios_are_none_when_nothing_was_emitted(tmp_path):
    """No evidence and a failing score are different readings."""
    summary = wiki_replay.build_summary(
        wiki_replay.ARMS["gemma-constrained"],
        served_model="gemma4:e4b",
        days=[MONDAY],
        copied={},
        tally=wiki_replay.ArmTally(),
        arm_root=tmp_path,
        elapsed=1.0,
        usage=None,
    )
    assert summary["maintainer"]["verification_pass_rate"] is None
    assert summary["maintainer"]["patch_ratio"] is None


def test_creates_only_reads_as_a_patch_ratio_of_zero(tmp_path):
    """M-b's failing case must be 0.0, not absent."""
    summary = wiki_replay.build_summary(
        wiki_replay.ARMS["gemma-constrained"],
        served_model="g",
        days=[MONDAY],
        copied={},
        tally=wiki_replay.ArmTally(op_classes={"create": 5}, ops_applied=5),
        arm_root=tmp_path,
        elapsed=1.0,
        usage=None,
    )
    assert summary["maintainer"]["patch_ratio"] == 0.0


def test_summary_is_written_and_carries_the_deviations(tmp_path):
    source = _source_store(tmp_path, [MONDAY])
    summary = wiki_replay.run_arm(
        wiki_replay.ARMS["opus-constrained"],
        source=source,
        home=tmp_path / "replay",
        days=[MONDAY],
        proposer_weekday=0,
        verbose=False,
        backend_override=FakeBackend(responses=[_write_turn(MONDAY), '{"action": "abstain"}'] * 4),
    )
    written = json.loads(
        (tmp_path / "replay" / "opus-constrained" / "summary.json").read_text(encoding="utf-8")
    )
    assert written == summary
    assert summary["deviations"] == list(wiki_replay.REPLAY_DEVIATIONS)
    assert summary["maintainer"]["llm_calls"] >= 1
    assert summary["wiki_daily"][0]["date"] == MONDAY.isoformat()


def test_llm_calls_are_counted_from_the_audit_rows(tmp_path):
    log = tmp_path / "wiki-maintainer.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"kind": "turn", "step": 0}),
                json.dumps({"kind": "turn", "step": 1}),
                json.dumps({"kind": "run", "outcome": "written"}),
                "not json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert wiki_replay.count_turns(log) == 2
    assert wiki_replay.count_turns(tmp_path / "absent.jsonl") == 0


def test_the_claude_arms_carry_their_usage_into_the_summary(tmp_path):
    """Cost is a first-class reading, not something recovered from stdout."""
    assert wiki_replay.ARMS["opus-paper"].context_window == 200_000
    assert wiki_replay.ARMS["opus-constrained"].context_window == 32768
    assert wiki_replay.ARMS["gemma-constrained"].uses_claude is False


# ------------------------------------------------------------ paper capacity


def _wiki_with_pages(root: Path, count: int) -> None:
    store = wiki_maintainer.WikiStore(wiki_dir=root / "wiki", data_root=root)
    for index in range(count):
        store.apply(
            wiki_maintainer.Create(
                title=f"Pattern {index}",
                body=f"UNIQUE-BODY-{index} — a durable observation.",
                sources=(f"2026-08-0{index + 1}T00:00:00+00:00",),
            )
        )


def test_paper_capacity_puts_every_page_body_in_the_first_prompt(tmp_path):
    (tmp_path / "logs").mkdir()
    _wiki_with_pages(tmp_path, 3)
    (tmp_path / "logs" / f"{MONDAY}.jsonl").write_text(
        json.dumps(_episode(f"{MONDAY}T01:00:00+00:00")) + "\n", encoding="utf-8"
    )
    backend = FakeBackend(context_window=200_000, responses=['{"action": "abstain"}'])
    configure(backend=backend)

    run = wiki_maintainer.run_maintainer(
        data_root=tmp_path,
        wiki_dir=tmp_path / "wiki",
        day=MONDAY,
        config=wiki_maintainer.MaintainerConfig(capacity="paper", context_window=200_000),
    )
    assert run.outcome == "abstained"
    first = backend.calls[0]
    for index in range(3):
        assert f"### p-000{index + 1} — Pattern {index}" in first["prompt"]
    # No `open` turn is offered: the schema's action enum has only two members.
    assert first["format"]["properties"]["action"]["enum"] == ["write", "abstain"]
    assert "open {opens_left}" not in first["prompt"]


def test_constrained_capacity_is_unchanged_by_the_new_option(tmp_path):
    (tmp_path / "logs").mkdir()
    _wiki_with_pages(tmp_path, 3)
    (tmp_path / "logs" / f"{MONDAY}.jsonl").write_text(
        json.dumps(_episode(f"{MONDAY}T01:00:00+00:00")) + "\n", encoding="utf-8"
    )
    backend = FakeBackend(responses=['{"action": "abstain"}'])
    configure(backend=backend)

    wiki_maintainer.run_maintainer(data_root=tmp_path, wiki_dir=tmp_path / "wiki", day=MONDAY)
    first = backend.calls[0]
    assert first["format"]["properties"]["action"]["enum"] == ["open", "write", "abstain"]
    # The index does carry a snippet of each page; what constrained capacity
    # must NOT do is hand over the opened-page section before any open turn.
    assert "(none yet)" in first["prompt"]
    assert "### p-0001 — Pattern 0" not in first["prompt"]


def test_paper_capacity_records_a_day_that_does_not_fit(tmp_path):
    """A day the window cannot hold is named, never sampled down."""
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / f"{MONDAY}.jsonl").write_text(
        "\n".join(json.dumps(_episode(f"{MONDAY}T0{n}:00:00+00:00")) for n in range(5)) + "\n",
        encoding="utf-8",
    )
    backend = FakeBackend(responses=['{"action": "abstain"}'])
    configure(backend=backend)

    run = wiki_maintainer.run_maintainer(
        data_root=tmp_path,
        wiki_dir=tmp_path / "wiki",
        day=MONDAY,
        # A window too small for the day: paper capacity must refuse, not trim.
        config=wiki_maintainer.MaintainerConfig(capacity="paper", context_window=3200),
    )
    assert run.outcome == "fail_closed_budget"
    assert backend.calls == []


def test_paper_capacity_gives_the_proposer_every_page_and_every_skill(tmp_path):
    (tmp_path / "logs").mkdir()
    skills = tmp_path / "skills"
    skills.mkdir()
    skills.joinpath("rate-limits.md").write_text(
        "---\nname: rate-limits\ndescription: back off\n---\n\nUNIQUE-SKILL-BODY\n",
        encoding="utf-8",
    )
    _wiki_with_pages(tmp_path, 2)
    backend = FakeBackend(context_window=200_000, responses=['{"action": "abstain"}'])
    configure(backend=backend)

    run = wiki_proposer.run_proposer(
        data_root=tmp_path,
        wiki_dir=tmp_path / "wiki",
        skills_dir=skills,
        today=MONDAY,
        config=wiki_proposer.ProposerConfig(capacity="paper", context_window=200_000),
    )
    assert run.outcome == "abstained"
    prompt = backend.calls[0]["prompt"]
    assert "UNIQUE-BODY-0" in prompt and "UNIQUE-BODY-1" in prompt
    assert "UNIQUE-SKILL-BODY" in prompt
    assert backend.calls[0]["format"]["properties"]["action"]["enum"] == ["propose", "abstain"]


def test_paper_capacity_proposer_refuses_a_picture_that_does_not_fit(tmp_path):
    (tmp_path / "logs").mkdir()
    skills = tmp_path / "skills"
    skills.mkdir()
    skills.joinpath("big.md").write_text(
        "---\nname: big\ndescription: d\n---\n\n" + ("x " * 4000), encoding="utf-8"
    )
    _wiki_with_pages(tmp_path, 1)
    backend = FakeBackend(responses=['{"action": "abstain"}'])
    configure(backend=backend)

    run = wiki_proposer.run_proposer(
        data_root=tmp_path,
        wiki_dir=tmp_path / "wiki",
        skills_dir=skills,
        today=MONDAY,
        config=wiki_proposer.ProposerConfig(capacity="paper", context_window=4096),
    )
    assert run.outcome == "fail_closed_budget"
    assert backend.calls == []
