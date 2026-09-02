"""RFC-0017 S2: the Maintainer loop.

The loop is code-owned and bounded; the model only names things the code
already enumerated. These tests fix the four properties that makes true:
the sample is deterministic and budgeted, ``open`` cannot reach an id the
index did not offer, ``sources`` cannot reach a page unless the episode was
actually read, and every LLM fault is a distinct fail-closed reason code
rather than a silent no-op.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from contemplative_agent.core import wiki, wiki_maintainer
from contemplative_agent.core.llm import BackendResult, configure, reset_llm_config


@dataclass
class FakeBackend:
    """Queued responses, one per generate() call. ``None`` = hard failure."""

    model: str = "fake-model"
    context_window: int = 32768
    responses: list[str | BackendResult | None] = field(default_factory=list)
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
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "num_predict": num_predict,
                "format": format,
                "think": think,
            }
        )
        if not self.responses:
            return None
        item = self.responses.pop(0)
        if item is None or isinstance(item, BackendResult):
            return item
        return BackendResult(text=item)


DAY = date(2026, 8, 31)


def _episode(ts: str, content: str = "hello", action: str = "comment") -> dict:
    """One rich activity record — the unit distill reads (ADR-0060)."""
    return {
        "ts": ts,
        "type": "activity",
        "data": {
            "action": action,
            "post_id": "p" + ts[-6:],
            "content": content,
            "original_post": "a peer post",
            "internal_note": "what I noticed",
        },
    }


def _write_day(data_root: Path, day: date, records: list[dict]) -> None:
    path = data_root / "logs" / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n" if records else "",
        encoding="utf-8",
    )


def _turn(action: str, **kw: object) -> str:
    return json.dumps({"action": action, **kw})


def _run(
    tmp_path: Path,
    responses: list[str | BackendResult | None],
    *,
    day: date = DAY,
    dry_run: bool = False,
    config: wiki_maintainer.MaintainerConfig | None = None,
) -> tuple[wiki_maintainer.MaintainerRun, FakeBackend]:
    backend = FakeBackend(responses=responses)
    configure(backend=backend)
    try:
        run = wiki_maintainer.run_maintainer(
            data_root=tmp_path,
            wiki_dir=tmp_path / "wiki",
            day=day,
            config=config or wiki_maintainer.MaintainerConfig(),
            dry_run=dry_run,
        )
    finally:
        reset_llm_config()
    return run, backend


def _audit(tmp_path: Path) -> list[dict]:
    path = tmp_path / "logs" / "wiki-maintainer.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture(autouse=True)
def _clean_llm():
    reset_llm_config()
    yield
    reset_llm_config()


# ------------------------------------------------------------ sampling


def test_the_sample_is_deterministic_for_the_same_day(tmp_path: Path) -> None:
    records = [_episode(f"2026-08-31T0{i}:00:00+00:00") for i in range(8)]
    first = wiki_maintainer.select_episodes(records, seed="2026-W35", budget_tokens=100_000)
    second = wiki_maintainer.select_episodes(records, seed="2026-W35", budget_tokens=100_000)
    assert first.read_ids == second.read_ids
    assert first.read_ids  # and it actually read something


def test_a_different_seed_gives_a_different_order(tmp_path: Path) -> None:
    records = [_episode(f"2026-08-31T0{i}:00:00+00:00") for i in range(8)]
    a = wiki_maintainer.select_episodes(records, seed="2026-W35", budget_tokens=100_000)
    b = wiki_maintainer.select_episodes(records, seed="2026-W99", budget_tokens=100_000)
    assert set(a.read_ids) == set(b.read_ids)
    assert a.read_ids != b.read_ids


def test_only_rich_episodes_are_read_and_the_rest_are_skipped_with_a_reason(
    tmp_path: Path,
) -> None:
    records = [
        _episode("2026-08-31T01:00:00+00:00"),
        {"ts": "2026-08-31T02:00:00+00:00", "type": "interaction", "data": {"direction": "sent"}},
        {
            "ts": "2026-08-31T03:00:00+00:00",
            "type": "activity",
            "data": {"action": "upvote", "post_id": "x"},
        },
    ]
    sample = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=100_000)
    assert sample.read_ids == ("2026-08-31T01:00:00+00:00",)
    assert set(sample.skipped_ids) == {
        "2026-08-31T02:00:00+00:00",
        "2026-08-31T03:00:00+00:00",
    }
    assert sample.skip_reasons["not_rich"] == 2


def test_the_budget_reduces_how_many_episodes_are_read(tmp_path: Path) -> None:
    records = [_episode(f"2026-08-31T0{i}:00:00+00:00", content="x" * 4000) for i in range(8)]
    big = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=100_000)
    small = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=3_000)
    assert len(small.read_ids) < len(big.read_ids)
    assert small.skip_reasons["over_budget"] >= 1
    assert small.tokens <= 3_000


def test_an_episode_larger_than_the_whole_budget_is_skipped_not_truncated(
    tmp_path: Path,
) -> None:
    records = [_episode("2026-08-31T01:00:00+00:00", content="x" * 200_000)]
    sample = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=1_000)
    assert sample.read_ids == ()
    assert sample.skip_reasons["over_budget"] == 1


def test_a_record_without_a_ts_is_not_counted_as_over_budget(tmp_path: Path) -> None:
    """The paper arm fails closed on over_budget, so data faults must not land there."""
    broken = _episode("2026-08-31T01:00:00+00:00")
    del broken["ts"]
    records = [broken, _episode("2026-08-31T02:00:00+00:00")]
    sample = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=100_000)

    assert sample.read_ids == ("2026-08-31T02:00:00+00:00",)
    assert sample.skip_reasons["no_ts"] == 1
    assert sample.skip_reasons["over_budget"] == 0


def test_the_rendered_sample_wraps_the_untrusted_peer_text(tmp_path: Path) -> None:
    records = [_episode("2026-08-31T01:00:00+00:00")]
    sample = wiki_maintainer.select_episodes(records, seed="s", budget_tokens=100_000)
    # episode_render wraps `original_post`; the Maintainer must not undo that.
    assert "a peer post" in sample.rendered
    assert "Post I engaged with" in sample.rendered


# ------------------------------------------------------------ the loop


def test_a_single_write_turn_creates_a_page(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    run, backend = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[
                    {
                        "op": "create",
                        "title": "Peers answer fast",
                        "body": "Observed twice.",
                        "sources": [ts],
                    }
                ],
            )
        ],
    )

    assert run.outcome == "written"
    assert run.ops_applied == ("create p-0001",)
    assert run.ops_refused == ()
    page = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path).read_page("p-0001")
    assert page is not None
    assert page.sources == (ts,)
    assert len(backend.calls) == 1


def test_an_open_turn_feeds_the_page_body_into_the_next_turn(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="Existing", body="summary line\nMARKER-BODY", sources=("e0",)))

    run, backend = _run(
        tmp_path,
        [
            _turn("open", page_ids=["p-0001"]),
            _turn(
                "write",
                ops=[
                    {"op": "append", "page_id": "p-0001", "text": "more", "sources": [ts]},
                ],
            ),
        ],
    )

    assert run.outcome == "written"
    assert run.opened_page_ids == ("p-0001",)
    assert "MARKER-BODY" not in backend.calls[0]["prompt"]
    assert "MARKER-BODY" in backend.calls[1]["prompt"]


def test_after_max_opens_the_schema_no_longer_offers_open(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a", sources=("e0",)))
    store.apply(wiki.Create(title="B", body="b", sources=("e0",)))

    run, backend = _run(
        tmp_path,
        [
            _turn("open", page_ids=["p-0001"]),
            _turn("open", page_ids=["p-0002"]),
            _turn("abstain", reason="nothing durable"),
        ],
        config=wiki_maintainer.MaintainerConfig(max_opens=2),
    )

    assert run.outcome == "abstained"
    assert run.opened_page_ids == ("p-0001", "p-0002")
    actions = [c["format"]["properties"]["action"]["enum"] for c in backend.calls]
    assert "open" in actions[0]
    assert "open" not in actions[2]


def test_the_open_enum_only_ever_offers_ids_that_exist(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a", sources=("e0",)))

    _run(tmp_path, [_turn("abstain", reason="x")])
    # rebuilt to inspect the schema the first call carried
    run, backend = _run(tmp_path, [_turn("abstain", reason="x")])
    schema = backend.calls[0]["format"]
    assert schema["properties"]["page_ids"]["items"]["enum"] == ["p-0001"]
    assert run.outcome == "abstained"


def test_an_unknown_page_id_is_refused_and_retried_once(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a", sources=("e0",)))

    run, backend = _run(
        tmp_path,
        [
            _turn("open", page_ids=["p-9999"]),
            _turn("open", page_ids=["p-0001"]),
            _turn("abstain", reason="done"),
        ],
    )

    assert run.outcome == "abstained"
    assert run.opened_page_ids == ("p-0001",)
    assert ("open", "UNKNOWN_PAGE_ID") in run.ops_refused
    assert len(backend.calls) == 3


def test_two_invalid_turns_in_a_row_fail_closed(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a", sources=("e0",)))

    run, _ = _run(
        tmp_path,
        [_turn("open", page_ids=["p-9999"]), _turn("open", page_ids=["p-8888"])],
    )
    assert run.outcome == "fail_closed_parse"


def test_an_invented_source_is_dropped_before_the_op_reaches_the_store(
    tmp_path: Path,
) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    run, _ = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[
                    {
                        "op": "create",
                        "title": "T",
                        "body": "B",
                        "sources": [ts, "2020-01-01T00:00:00+00:00", "not-a-ts"],
                    }
                ],
            )
        ],
    )
    page = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path).read_page("p-0001")
    assert page is not None
    assert page.sources == (ts,)
    assert run.outcome == "written"


def test_an_op_whose_every_source_was_invented_is_refused(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[{"op": "create", "title": "T", "body": "B", "sources": ["invented"]}],
            )
        ],
    )
    assert run.ops_applied == ()
    assert ("create", "SOURCES_EMPTY") in run.ops_refused
    assert not (tmp_path / "wiki" / "patterns").exists()


def test_a_store_refusal_is_recorded_and_the_run_continues(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    run, _ = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[
                    {"op": "append", "page_id": "p-0404", "text": "x", "sources": [ts]},
                    {"op": "create", "title": "T", "body": "B", "sources": [ts]},
                ],
            )
        ],
    )
    assert ("append", "PAGE_NOT_FOUND") in run.ops_refused
    assert run.ops_applied == ("create p-0001",)


def test_abstain_is_a_normal_outcome_with_a_reason(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(tmp_path, [_turn("abstain", reason="nothing durable today")])
    assert run.outcome == "abstained"
    assert run.reason is not None
    assert "nothing durable" in run.reason


def test_a_day_with_no_episodes_never_calls_the_model(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [])
    run, backend = _run(tmp_path, [])
    assert run.outcome == "no_episodes"
    assert backend.calls == []


# --------------------------------------------------------- fail-closed


def test_a_backend_failure_fails_closed(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(tmp_path, [None])
    assert run.outcome == "fail_closed_llm"
    assert not (tmp_path / "wiki" / "patterns").exists()


def test_malformed_json_fails_closed_as_parse(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(tmp_path, ["}{ this is not json", "still not json"])
    assert run.outcome == "fail_closed_parse"


def test_output_cut_mid_object_fails_closed_as_truncated(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(
        tmp_path,
        [BackendResult(text='{"action": "write", "ops": [{"op": "cre', finish_reason="length")],
    )
    assert run.outcome == "fail_closed_truncated"
    assert not (tmp_path / "wiki" / "patterns").exists()


def test_valid_json_of_the_wrong_shape_fails_closed_as_parse(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    run, _ = _run(tmp_path, ["[1, 2, 3]", '"a string"'])
    assert run.outcome == "fail_closed_parse"


# --------------------------------------------------------------- audit


def test_the_audit_carries_a_run_row_and_one_turn_row_per_call(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts, content="SECRET-EPISODE-BODY")])
    _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[{"op": "create", "title": "T", "body": "B", "sources": [ts]}],
            )
        ],
    )

    rows = _audit(tmp_path)
    turns = [r for r in rows if r["kind"] == "turn"]
    runs = [r for r in rows if r["kind"] == "run"]
    assert len(turns) == 1
    assert len(runs) == 1

    turn = turns[0]
    assert turn["prompt_b64"] and turn["output_b64"]
    assert (
        turn["prompt_sha256"] == hashlib.sha256(base64.b64decode(turn["prompt_b64"])).hexdigest()
        or turn["prompt_truncated"]
    )
    # untrusted episode text never reaches the log in the clear
    raw = json.dumps(turn)
    assert "SECRET-EPISODE-BODY" not in raw
    assert "SECRET-EPISODE-BODY" in base64.b64decode(turn["prompt_b64"]).decode("utf-8")

    run_row = runs[0]
    assert run_row["date"] == str(DAY)
    assert run_row["seed"]
    assert run_row["episode_ids_read"] == [ts]
    assert run_row["outcome"] == "written"
    assert run_row["ops_applied"] == ["create p-0001"]
    assert run_row["index_sha256"]
    assert set(run_row["budget"]) >= {"window", "output_reserve", "episodes"}


def test_the_run_row_carries_the_wiki_size_reading(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a" * 500, sources=("e0",)))
    store.apply(wiki.Create(title="B", body="b" * 100, sources=("e0",)))

    _run(tmp_path, [_turn("abstain", reason="x")])
    run_row = next(r for r in _audit(tmp_path) if r["kind"] == "run")
    size = run_row["wiki_size"]
    assert size["pages"] == 2
    assert size["index_tokens"] > 0
    assert size["page_chars_p90"] >= 500


def test_a_fail_closed_run_still_writes_its_run_row(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    _run(tmp_path, [None])
    run_row = next(r for r in _audit(tmp_path) if r["kind"] == "run")
    assert run_row["outcome"] == "fail_closed_llm"


# -------------------------------------------------------------- dry run


def test_dry_run_calls_the_model_and_changes_no_page(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    run, backend = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[{"op": "create", "title": "T", "body": "B", "sources": [ts]}],
            )
        ],
        dry_run=True,
    )

    assert len(backend.calls) == 1
    assert run.outcome == "written"
    assert run.ops_applied == ("create would-be",)
    assert not (tmp_path / "wiki" / "patterns").exists()
    run_row = next(r for r in _audit(tmp_path) if r["kind"] == "run")
    assert run_row["dry_run"] is True


# ------------------------------------------------------------------- CLI


class TestWikiMaintainCLI:
    """The handler's own decisions: which day, which config, what it prints.

    ``cli`` and the Moltbook config are imported per test rather than at module
    scope: importing the CLI package pulls the adapter layer (and numpy) into
    every collection of this file, which the coverage tracer refuses to load
    twice in one process. The handlers themselves import the same way.
    """

    @staticmethod
    def _cli():
        from contemplative_agent.adapters.moltbook import config
        from contemplative_agent.cli import wiki_cmds

        return wiki_cmds, config

    def _namespace(self, **kw: object) -> argparse.Namespace:
        base = {"wiki_date": None, "dry_run": False, "max_opens": None}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_the_command_is_registered_once_and_needs_no_agent(self) -> None:
        from contemplative_agent.cli import COMMANDS
        from contemplative_agent.cli.registry import Tier

        specs = [s for s in COMMANDS if s.name == "wiki-maintain"]
        assert len(specs) == 1
        assert specs[0].tier is Tier.LLM_RUNTIME_ONLY

    def test_the_default_day_is_yesterday_utc(self) -> None:
        wiki_cmds, _ = self._cli()
        parser = argparse.ArgumentParser()
        resolved = wiki_cmds._resolve_day(None, parser)
        expected = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        assert resolved == expected

    def test_an_explicit_day_is_parsed(self) -> None:
        wiki_cmds, _ = self._cli()
        parser = argparse.ArgumentParser()
        assert wiki_cmds._resolve_day("2026-08-31", parser) == DAY

    def test_a_malformed_day_is_a_usage_error(self) -> None:
        wiki_cmds, _ = self._cli()
        parser = argparse.ArgumentParser()
        with pytest.raises(SystemExit):
            wiki_cmds._resolve_day("31/08/2026", parser)

    def test_the_handler_runs_the_maintainer_and_reports_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wiki_cmds, config = self._cli()
        ts = "2026-08-31T01:00:00+00:00"
        _write_day(tmp_path, DAY, [_episode(ts)])
        monkeypatch.setattr(config, "MOLTBOOK_DATA_DIR", tmp_path)
        monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wiki")

        backend = FakeBackend(
            responses=[
                _turn(
                    "write",
                    ops=[
                        {"op": "create", "title": "T", "body": "B", "sources": [ts]},
                        {"op": "append", "page_id": "p-0404", "text": "x", "sources": [ts]},
                    ],
                )
            ]
        )
        configure(backend=backend)
        try:
            wiki_cmds._handle_wiki_maintain(
                self._namespace(wiki_date="2026-08-31", max_opens=1),
                argparse.ArgumentParser(),
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "wiki-maintain 2026-08-31: written" in out
        assert "applied: create p-0001" in out
        assert "refused: append (PAGE_NOT_FOUND)" in out
        assert "wiki: 1 pages" in out
        assert (tmp_path / "wiki" / "patterns" / "p-0001.md").is_file()

    def test_dry_run_is_labelled_and_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wiki_cmds, config = self._cli()
        ts = "2026-08-31T01:00:00+00:00"
        _write_day(tmp_path, DAY, [_episode(ts)])
        monkeypatch.setattr(config, "MOLTBOOK_DATA_DIR", tmp_path)
        monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wiki")

        configure(
            backend=FakeBackend(
                responses=[
                    _turn(
                        "write",
                        ops=[{"op": "create", "title": "T", "body": "B", "sources": [ts]}],
                    )
                ]
            )
        )
        try:
            wiki_cmds._handle_wiki_maintain(
                self._namespace(wiki_date="2026-08-31", dry_run=True),
                argparse.ArgumentParser(),
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "(dry-run)" in out
        assert not (tmp_path / "wiki" / "patterns").exists()

    def test_an_abstain_prints_its_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wiki_cmds, config = self._cli()
        _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
        monkeypatch.setattr(config, "MOLTBOOK_DATA_DIR", tmp_path)
        monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wiki")

        store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
        store.apply(wiki.Create(title="A", body="a", sources=("e0",)))
        configure(
            backend=FakeBackend(
                responses=[_turn("open", page_ids=["p-0001"]), _turn("abstain", reason="thin day")]
            )
        )
        try:
            wiki_cmds._handle_wiki_maintain(
                self._namespace(wiki_date="2026-08-31"), argparse.ArgumentParser()
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "abstained" in out
        assert "reason: thin day" in out
        assert "opened: p-0001" in out
