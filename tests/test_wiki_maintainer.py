"""RFC-0017 S2: the Maintainer loop.

The loop is code-owned and bounded; the model only names things the code
already enumerated. These tests fix the properties that makes true: the day is
read whole, in order, one batch of episodes per call, an op cannot reach a page
id the wiki does not hold, ``sources`` cannot reach a page unless the episode
was actually read, and every LLM fault is a distinct fail-closed reason code
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


def _sample(records: list[dict], budget: int) -> wiki_maintainer.EpisodeSample:
    prepared = wiki_maintainer.prepare_day(records)
    sample, _, _ = wiki_maintainer.pack_batch(prepared.episodes, budget)
    return sample


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
    prepared = wiki_maintainer.prepare_day(records)
    assert tuple(e.episode_id for e in prepared.episodes) == ("2026-08-31T01:00:00+00:00",)
    assert set(prepared.skipped_ids) == {
        "2026-08-31T02:00:00+00:00",
        "2026-08-31T03:00:00+00:00",
    }
    assert prepared.skip_reasons["not_rich"] == 2


def test_the_budget_decides_how_many_episodes_one_batch_holds(tmp_path: Path) -> None:
    """What does not fit is the NEXT batch, not a skip (RFC-0022: the day is read whole)."""
    records = [_episode(f"2026-08-31T0{i}:00:00+00:00", content="x" * 4000) for i in range(8)]
    prepared = wiki_maintainer.prepare_day(records)
    big, big_rest, _ = wiki_maintainer.pack_batch(prepared.episodes, 100_000)
    small, small_rest, _ = wiki_maintainer.pack_batch(prepared.episodes, 3_000)

    assert len(small.read_ids) < len(big.read_ids)
    assert small.tokens <= 3_000
    assert big_rest == ()
    assert len(small.read_ids) + len(small_rest) == len(prepared.episodes)
    # chronological, not shuffled: the batches replay the day in order
    assert big.read_ids == tuple(e.episode_id for e in prepared.episodes)


def test_an_episode_larger_than_the_whole_budget_is_stepped_over_not_truncated(
    tmp_path: Path,
) -> None:
    """One fat record must not truncate, and must not block the rest of the day."""
    huge = "2026-08-31T01:00:00+00:00"
    small = "2026-08-31T02:00:00+00:00"
    records = [_episode(huge, content="x" * 200_000), _episode(small)]
    prepared = wiki_maintainer.prepare_day(records)
    sample, rest, oversized = wiki_maintainer.pack_batch(prepared.episodes, 1_000)
    assert oversized == (huge,)
    assert sample.read_ids == (small,)  # the day continues past the fat record
    assert rest == ()


def test_a_record_without_a_ts_is_not_counted_as_over_budget(tmp_path: Path) -> None:
    """over_budget is D8's reading of what the window stopped holding — data faults are not that."""
    broken = _episode("2026-08-31T01:00:00+00:00")
    del broken["ts"]
    records = [broken, _episode("2026-08-31T02:00:00+00:00")]
    prepared = wiki_maintainer.prepare_day(records)

    assert tuple(e.episode_id for e in prepared.episodes) == ("2026-08-31T02:00:00+00:00",)
    assert prepared.skip_reasons["no_ts"] == 1
    assert prepared.skip_reasons["over_budget"] == 0


def test_the_rendered_sample_wraps_the_untrusted_peer_text(tmp_path: Path) -> None:
    records = [_episode("2026-08-31T01:00:00+00:00")]
    sample = _sample(records, 100_000)
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


def test_every_page_body_is_in_the_first_prompt(tmp_path: Path) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="Existing", body="summary line\nMARKER-BODY", sources=("e0",)))

    run, backend = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[
                    {"op": "append", "page_id": "p-0001", "text": "more", "sources": [ts]},
                ],
            ),
        ],
    )

    assert run.outcome == "written"
    assert len(backend.calls) == 1
    assert "MARKER-BODY" in backend.calls[0]["prompt"]


def test_the_page_id_enum_only_ever_offers_ids_that_exist(tmp_path: Path) -> None:
    _write_day(tmp_path, DAY, [_episode("2026-08-31T01:00:00+00:00")])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(wiki.Create(title="A", body="a", sources=("e0",)))

    run, backend = _run(tmp_path, [_turn("abstain", reason="x")])
    schema = backend.calls[0]["format"]
    assert schema["properties"]["action"]["enum"] == ["write", "abstain"]
    assert "page_ids" not in schema["properties"]
    ops = schema["properties"]["ops"]["items"]["properties"]
    assert ops["page_id"]["enum"] == ["p-0001"]
    assert run.outcome == "abstained"


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
    assert run_row["batches"] == 1
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
        base = {"wiki_date": None, "dry_run": False, "catch_up_days": 0}
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

    def test_catch_up_days_resolve_oldest_first(self) -> None:
        wiki_cmds, _ = self._cli()
        parser = argparse.ArgumentParser()
        days = wiki_cmds._resolve_days(self._namespace(wiki_date=None, catch_up_days=2), parser)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        assert days == [yesterday - timedelta(days=2), yesterday - timedelta(days=1), yesterday]

    def test_a_date_with_catch_up_is_a_usage_error(self) -> None:
        wiki_cmds, _ = self._cli()
        parser = argparse.ArgumentParser()
        with pytest.raises(SystemExit):
            wiki_cmds._resolve_days(
                self._namespace(wiki_date="2026-08-31", catch_up_days=2), parser
            )

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
        # never the production lock: the handler takes it BLOCKING, so a test
        # that used the real path would queue behind a live agent session
        monkeypatch.setattr(config, "RUN_LOCK_PATH", tmp_path / ".run.lock")

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
                self._namespace(wiki_date="2026-08-31"),
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
        # never the production lock: the handler takes it BLOCKING, so a test
        # that used the real path would queue behind a live agent session
        monkeypatch.setattr(config, "RUN_LOCK_PATH", tmp_path / ".run.lock")

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
        # never the production lock: the handler takes it BLOCKING, so a test
        # that used the real path would queue behind a live agent session
        monkeypatch.setattr(config, "RUN_LOCK_PATH", tmp_path / ".run.lock")

        store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
        store.apply(wiki.Create(title="A", body="a", sources=("e0",)))
        configure(backend=FakeBackend(responses=[_turn("abstain", reason="thin day")]))
        try:
            wiki_cmds._handle_wiki_maintain(
                self._namespace(wiki_date="2026-08-31"), argparse.ArgumentParser()
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "abstained" in out
        assert "reason: thin day" in out
        assert "batches: 1" in out


# ------------------------------------------------------------- batching


def _big_episode(ts: str) -> dict:
    """One rich episode large enough that two of them need two batches."""
    return _episode(ts, content="x" * 4000)


def _small_window() -> wiki_maintainer.MaintainerConfig:
    """A window that holds the wiki, the shell and exactly one big episode."""
    return wiki_maintainer.MaintainerConfig(context_window=6000)


def test_a_day_that_does_not_fit_one_call_is_split_into_batches(tmp_path: Path) -> None:
    first_ts = "2026-08-31T01:00:00+00:00"
    second_ts = "2026-08-31T02:00:00+00:00"
    _write_day(tmp_path, DAY, [_big_episode(first_ts), _big_episode(second_ts)])

    run, backend = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[
                    {
                        "op": "create",
                        "title": "Peers answer fast",
                        "body": "MARKER-FROM-BATCH-ONE",
                        "sources": [first_ts],
                    }
                ],
            ),
            _turn("abstain", reason="already recorded"),
        ],
        config=_small_window(),
    )

    assert run.outcome == "written"  # the day rolls up: one batch wrote
    assert len(run.batches) == 2
    assert run.batches[0].episode_ids_read == (first_ts,)
    assert run.batches[1].episode_ids_read == (second_ts,)
    assert run.episode_ids_read == (first_ts, second_ts)
    # the second batch reads the wiki again, so it sees what the first wrote
    assert "MARKER-FROM-BATCH-ONE" not in backend.calls[0]["prompt"]
    assert "MARKER-FROM-BATCH-ONE" in backend.calls[1]["prompt"]


def test_a_day_the_wiki_alone_fills_fails_closed_and_names_what_it_did_not_read(
    tmp_path: Path,
) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    # A page this long can only be built by a store without the length rule —
    # which is the point of the rule: with it, filling the window takes many
    # pages (D8's remaining growth axis), not one runaway page.
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path, page_max_chars=100_000)
    store.apply(wiki.Create(title="Huge", body="y" * 20_000, sources=("e0",)))

    run, backend = _run(tmp_path, [], config=wiki_maintainer.MaintainerConfig(context_window=6000))

    assert run.outcome == "fail_closed_budget"
    assert backend.calls == []
    assert run.episode_ids_skipped == (ts,)
    assert run.skip_reasons["over_budget"] == 1


def test_more_batches_than_the_cap_fails_closed_as_batches(tmp_path: Path) -> None:
    first_ts = "2026-08-31T01:00:00+00:00"
    second_ts = "2026-08-31T02:00:00+00:00"
    _write_day(tmp_path, DAY, [_big_episode(first_ts), _big_episode(second_ts)])

    run, backend = _run(
        tmp_path,
        [_turn("abstain", reason="thin")],
        config=wiki_maintainer.MaintainerConfig(context_window=6000, max_batches=1),
    )

    assert run.outcome == "fail_closed_batches"
    assert len(backend.calls) == 1
    assert run.episode_ids_read == (first_ts,)
    assert run.episode_ids_skipped == (second_ts,)


def test_a_re_run_of_the_same_day_does_not_read_the_same_episodes_again(
    tmp_path: Path,
) -> None:
    first_ts = "2026-08-31T01:00:00+00:00"
    second_ts = "2026-08-31T02:00:00+00:00"
    _write_day(tmp_path, DAY, [_big_episode(first_ts), _big_episode(second_ts)])

    # A dry run reads nothing for real: its batch rows must not count as read.
    _run(tmp_path, [_turn("abstain", reason="dry")] * 2, config=_small_window(), dry_run=True)
    first, _ = _run(
        tmp_path,
        [_turn("abstain", reason="a")],
        config=wiki_maintainer.MaintainerConfig(context_window=6000, max_batches=1),
    )
    assert first.episode_ids_read == (first_ts,)

    second, backend = _run(tmp_path, [_turn("abstain", reason="b")], config=_small_window())
    assert second.episode_ids_read == (second_ts,)
    assert len(backend.calls) == 1

    third, backend = _run(tmp_path, [], config=_small_window())
    assert third.outcome == "already_done"
    assert backend.calls == []


def test_a_batch_fault_stops_the_day_and_keeps_what_earlier_batches_wrote(
    tmp_path: Path,
) -> None:
    first_ts = "2026-08-31T01:00:00+00:00"
    second_ts = "2026-08-31T02:00:00+00:00"
    _write_day(tmp_path, DAY, [_big_episode(first_ts), _big_episode(second_ts)])

    run, backend = _run(
        tmp_path,
        [
            _turn(
                "write",
                ops=[{"op": "create", "title": "T", "body": "B", "sources": [first_ts]}],
            ),
            "this is not json",
        ],
        config=_small_window(),
    )

    assert run.outcome == "fail_closed_parse"
    assert len(backend.calls) == 2
    # the faulted batch's episode is NOT read: the next run gets it back
    assert run.episode_ids_read == (first_ts,)
    assert second_ts in run.episode_ids_skipped
    assert run.ops_applied == ("create p-0001",)
    assert (tmp_path / "wiki" / "patterns" / "p-0001.md").is_file()
    assert run.batches[0].outcome == "written"
    assert run.batches[1].outcome == "fail_closed_parse"


def test_one_fat_episode_does_not_block_the_rest_of_the_day(tmp_path: Path) -> None:
    """The old sampler stepped over an oversized episode; batching must too.

    ``render_episode`` caps every excerpt (ADR-0060), so this needs a small
    window to reach — but the branch is what keeps one long record from
    ending a day AND inflating D8's over_budget reading.
    """
    huge = "2026-08-31T01:00:00+00:00"
    small = "2026-08-31T02:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(huge, content="x" * 4000), _episode(small)])

    run, backend = _run(
        tmp_path,
        [_turn("abstain", reason="thin")],
        config=wiki_maintainer.MaintainerConfig(context_window=5000),
    )

    assert run.outcome == "abstained"
    assert run.episode_ids_read == (small,)
    assert run.episode_ids_skipped == (huge,)
    assert run.skip_reasons["over_budget"] == 1
    assert len(backend.calls) == 1


def test_a_lost_batch_audit_row_is_not_swallowed(tmp_path: Path) -> None:
    """The batch row IS the resume state, so its loss must not read as a clean run."""
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    # A directory where the audit file belongs: every append raises OSError.
    (tmp_path / "logs" / "wiki-maintainer.jsonl").mkdir()

    with pytest.raises(OSError):
        _run(
            tmp_path,
            [_turn("write", ops=[{"op": "create", "title": "T", "body": "B", "sources": [ts]}])],
        )


# --------------------------------------------------------------- catch-up


def test_a_day_already_read_to_the_end_is_already_done_without_a_call(
    tmp_path: Path,
) -> None:
    ts = "2026-08-31T01:00:00+00:00"
    _write_day(tmp_path, DAY, [_episode(ts)])
    first, _ = _run(tmp_path, [_turn("abstain", reason="thin")])
    assert first.outcome == "abstained"

    second, backend = _run(tmp_path, [])

    assert second.outcome == "already_done"
    assert backend.calls == []
    rows = [r for r in _audit(tmp_path) if r["kind"] == "run"]
    assert rows[-1]["outcome"] == "already_done"
    assert not [r for r in _audit(tmp_path) if r["kind"] == "batch" and r["batch"] > 0]


def test_catch_up_runs_oldest_first_and_keeps_going_past_a_faulted_day(
    tmp_path: Path,
) -> None:
    days = [date(2026, 8, 29), date(2026, 8, 30), DAY]
    for day in days:
        _write_day(tmp_path, day, [_episode(f"{day.isoformat()}T01:00:00+00:00")])

    backend = FakeBackend(
        responses=[
            _turn("abstain", reason="first"),
            "not json at all",  # day two faults
            _turn("abstain", reason="third"),
        ]
    )
    configure(backend=backend)
    try:
        runs = wiki_maintainer.run_days(data_root=tmp_path, wiki_dir=tmp_path / "wiki", days=days)
    finally:
        reset_llm_config()

    assert [r.date for r in runs] == [d.isoformat() for d in days]
    assert [r.outcome for r in runs] == ["abstained", "fail_closed_parse", "abstained"]
    assert len(backend.calls) == 3


def test_catch_up_stops_after_a_budget_failure_and_names_the_rest(tmp_path: Path) -> None:
    """A window the wiki alone fills is structural: the later days would all fail the same way."""
    days = [date(2026, 8, 30), DAY]
    for day in days:
        _write_day(tmp_path, day, [_episode(f"{day.isoformat()}T01:00:00+00:00")])
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path, page_max_chars=100_000)
    store.apply(wiki.Create(title="Huge", body="y" * 20_000, sources=("e0",)))

    backend = FakeBackend(responses=[])
    configure(backend=backend)
    try:
        runs = wiki_maintainer.run_days(
            data_root=tmp_path,
            wiki_dir=tmp_path / "wiki",
            days=days,
            config=wiki_maintainer.MaintainerConfig(context_window=6000),
        )
    finally:
        reset_llm_config()

    assert [r.outcome for r in runs] == ["fail_closed_budget", "skipped_after_budget"]
    assert backend.calls == []
    rows = [r for r in _audit(tmp_path) if r["kind"] == "run"]
    assert rows[-1]["outcome"] == "skipped_after_budget"


def test_catch_up_stops_at_its_time_budget(tmp_path: Path) -> None:
    """The caller holds the run lock across the walk, so it must not run all night."""
    days = [date(2026, 8, 29), date(2026, 8, 30), DAY]
    for day in days:
        _write_day(tmp_path, day, [_episode(f"{day.isoformat()}T01:00:00+00:00")])

    ticks = iter([0.0, 0.0, 100.0, 200.0])  # start, day one, then past the budget
    backend = FakeBackend(responses=[_turn("abstain", reason="first")])
    configure(backend=backend)
    try:
        runs = wiki_maintainer.run_days(
            data_root=tmp_path,
            wiki_dir=tmp_path / "wiki",
            days=days,
            seconds=60,
            clock=lambda: next(ticks),
        )
    finally:
        reset_llm_config()

    assert [r.outcome for r in runs] == [
        "abstained",
        "skipped_after_deadline",
        "skipped_after_deadline",
    ]
    assert len(backend.calls) == 1
    assert runs[1].reason == "the catch-up ran out of its time budget"


def test_a_day_whose_every_episode_is_oversized_is_a_window_failure(tmp_path: Path) -> None:
    """Not `no_episodes`: the day HAD episodes, the window could not hold one."""
    _write_day(
        tmp_path,
        DAY,
        [_episode(f"2026-08-31T0{n}:00:00+00:00", content="x" * 4000) for n in range(2)],
    )

    run, backend = _run(tmp_path, [], config=wiki_maintainer.MaintainerConfig(context_window=5000))

    assert run.outcome == "fail_closed_budget"
    assert backend.calls == []
    assert run.skip_reasons["over_budget"] == 2
