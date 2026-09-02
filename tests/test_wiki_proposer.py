"""RFC-0017 S3: the Proposer loop.

Same shape as the Maintainer's tests and for the same reason: the loop is
code-owned, so what needs fixing is every place the model could name something
that does not exist. Here that is four places — a wiki page, a skill, a cited
page, and the skill a patch targets — plus the anchor a patch has to hit.

S3 writes nothing into ``skills/`` or ``.staged/``. The only artifact is a
would-be proposal rendered under ``wiki/proposals/`` (D10 shadow), and the
tests assert the target skill is byte-identical afterwards.
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from contemplative_agent.core import wiki, wiki_proposer
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
        self.calls.append({"prompt": prompt, "format": format, "num_predict": num_predict})
        if not self.responses:
            return None
        item = self.responses.pop(0)
        if item is None or isinstance(item, BackendResult):
            return item
        return BackendResult(text=item)


TODAY = date(2026, 9, 2)
SKILL_BODY = (
    "---\nname: reply-fast\ndescription: answer quickly\n---\n\n# Reply fast\n\nANCHOR-LINE\ntail\n"
)


@pytest.fixture(autouse=True)
def _clean_llm():
    reset_llm_config()
    yield
    reset_llm_config()


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """A store with one wiki page, one skill, and empty ledgers."""
    (tmp_path / "logs").mkdir()
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "reply-fast.md").write_text(SKILL_BODY, encoding="utf-8")
    store = wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)
    store.apply(
        wiki.Create(title="Peers answer fast", body="summary\nPAGE-MARKER", sources=("e1",))
    )
    return tmp_path


def _turn(action: str, **kw: object) -> str:
    return json.dumps({"action": action, **kw})


def _propose(**kw: object) -> str:
    return _turn("propose", proposal=kw)


def _run(
    home: Path,
    responses: list[str | BackendResult | None],
    *,
    dry_run: bool = False,
    config: wiki_proposer.ProposerConfig | None = None,
) -> tuple[wiki_proposer.ProposerRun, FakeBackend]:
    backend = FakeBackend(responses=responses)
    configure(backend=backend)
    try:
        run = wiki_proposer.run_proposer(
            data_root=home,
            wiki_dir=home / "wiki",
            skills_dir=home / "skills",
            today=TODAY,
            config=config or wiki_proposer.ProposerConfig(),
            dry_run=dry_run,
        )
    finally:
        reset_llm_config()
    return run, backend


def _audit(home: Path) -> list[dict]:
    path = home / "logs" / "wiki-proposer.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _proposals(home: Path) -> list[Path]:
    d = home / "wiki" / "proposals"
    return sorted(d.glob("*.md")) if d.is_dir() else []


# ------------------------------------------------------------- the inputs


def test_all_four_inputs_reach_the_first_prompt(home: Path) -> None:
    _, backend = _run(home, [_turn("abstain", reason="x")])
    prompt = backend.calls[0]["prompt"]
    assert "Peers answer fast" in prompt  # wiki index
    assert "reply-fast" in prompt  # skill index
    assert "Evolution log" in prompt
    assert "Skill impact" in prompt


def test_the_skill_index_is_not_filtered(home: Path) -> None:
    for i in range(5):
        (home / "skills" / f"s{i}.md").write_text(
            f"---\nname: s{i}\ndescription: d{i}\n---\nbody\n", encoding="utf-8"
        )
    run, backend = _run(home, [_turn("abstain", reason="x")])
    prompt = backend.calls[0]["prompt"]
    assert run.catalog_size == 6
    for i in range(5):
        assert f"s{i}" in prompt


def test_inputs_that_do_not_fit_the_window_fail_closed(home: Path) -> None:
    run, backend = _run(
        home,
        [_turn("abstain", reason="x")],
        config=wiki_proposer.ProposerConfig(context_window=200),
    )
    assert run.outcome == "fail_closed_budget"
    assert backend.calls == []
    assert _proposals(home) == []


def test_the_impact_window_is_reported_and_configurable(home: Path) -> None:
    run, _ = _run(
        home, [_turn("abstain", reason="x")], config=wiki_proposer.ProposerConfig(impact_days=7)
    )
    assert run.impact_window_days == 7


# ------------------------------------------------------------- the loop


def test_open_page_then_open_skill_then_propose(home: Path) -> None:
    run, backend = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _turn("open_skill", skill_names=["reply-fast"]),
            _propose(
                kind="patch",
                target="reply-fast",
                op="append",
                text="Also true on weekends.",
                cited_pages=["p-0001"],
            ),
        ],
    )

    assert run.outcome == "proposed"
    assert run.opened_page_ids == ("p-0001",)
    assert run.opened_skill_names == ("reply-fast",)
    assert "PAGE-MARKER" not in backend.calls[0]["prompt"]
    assert "PAGE-MARKER" in backend.calls[1]["prompt"]
    assert "ANCHOR-LINE" in backend.calls[2]["prompt"]


def test_after_max_opens_only_propose_and_abstain_are_offered(home: Path) -> None:
    run, backend = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _turn("abstain", reason="enough"),
        ],
        config=wiki_proposer.ProposerConfig(max_opens=1),
    )
    assert run.outcome == "abstained"
    first = backend.calls[0]["format"]["properties"]["action"]["enum"]
    second = backend.calls[1]["format"]["properties"]["action"]["enum"]
    assert {"open_page", "open_skill"} <= set(first)
    assert set(second) == {"propose", "abstain"}


def test_the_open_enums_only_offer_things_that_exist(home: Path) -> None:
    _, backend = _run(home, [_turn("abstain", reason="x")])
    schema = backend.calls[0]["format"]["properties"]
    assert schema["page_ids"]["items"]["enum"] == ["p-0001"]
    assert schema["skill_names"]["items"]["enum"] == ["reply-fast"]


def test_an_unknown_page_or_skill_is_refused_and_retried_once(home: Path) -> None:
    run, backend = _run(
        home,
        [
            _turn("open_page", page_ids=["p-9999"]),
            _turn("open_skill", skill_names=["no-such-skill"]),
            _turn("abstain", reason="gave up"),
        ],
    )
    assert run.outcome == "fail_closed_parse"
    assert ("open_page", "UNKNOWN_PAGE_ID") in run.refusals
    assert ("open_skill", "UNKNOWN_SKILL_NAME") in run.refusals
    assert len(backend.calls) == 2


def test_one_bad_open_then_a_good_one_continues(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-9999"]),
            _turn("open_page", page_ids=["p-0001"]),
            _turn("abstain", reason="done"),
        ],
    )
    assert run.outcome == "abstained"
    assert run.opened_page_ids == ("p-0001",)


# ------------------------------------------------------ proposal validity


def test_a_create_proposal_is_rendered_and_recorded(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="create",
                name="answer-within-a-minute",
                description="reply while the thread is warm",
                body="# Answer within a minute\n\nObserved on p-0001.",
                cited_pages=["p-0001"],
            ),
        ],
    )

    assert run.outcome == "proposed"
    assert run.proposal is not None
    assert run.proposal.kind == "create"
    assert run.proposal.cited_pages == ("p-0001",)
    written = _proposals(home)
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert "kind: create" in text
    assert "answer-within-a-minute" in text
    assert "Observed on p-0001." in text


def test_a_patch_proposal_renders_the_edited_body_and_a_diff(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="patch",
                target="reply-fast",
                op="insert_after",
                anchor="ANCHOR-LINE",
                text="INSERTED-LINE",
                cited_pages=["p-0001"],
            ),
        ],
    )

    assert run.outcome == "proposed"
    text = _proposals(home)[0].read_text(encoding="utf-8")
    assert "kind: patch" in text
    assert "target: reply-fast" in text
    assert "INSERTED-LINE" in text
    assert "@@" in text  # unified diff hunk header
    assert "+INSERTED-LINE" in text
    # the skill itself is untouched — S3 writes nothing into skills/
    assert (home / "skills" / "reply-fast.md").read_text(encoding="utf-8") == SKILL_BODY


def test_a_citation_the_run_never_opened_is_dropped(home: Path) -> None:
    store = wiki.WikiStore(wiki_dir=home / "wiki", data_root=home)
    store.apply(wiki.Create(title="Second", body="second", sources=("e2",)))
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="create",
                name="n",
                description="d",
                body="b",
                cited_pages=["p-0001", "p-0002", "p-9999"],
            ),
        ],
    )
    assert run.proposal is not None
    assert run.proposal.cited_pages == ("p-0001",)


def test_a_proposal_citing_nothing_it_opened_is_refused(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _propose(kind="create", name="n", description="d", body="b", cited_pages=["p-0001"]),
            _propose(kind="create", name="n", description="d", body="b", cited_pages=[]),
        ],
    )
    assert run.outcome == "fail_closed_parse"
    assert ("propose", "CITATIONS_EMPTY") in run.refusals
    assert _proposals(home) == []


def test_a_patch_at_an_unknown_skill_is_refused(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="patch",
                target="ghost-skill",
                op="append",
                text="x",
                cited_pages=["p-0001"],
            ),
            _turn("abstain", reason="ok"),
        ],
    )
    assert ("propose", "TARGET_NOT_FOUND") in run.refusals
    assert run.outcome == "abstained"


def test_a_create_whose_name_already_exists_is_refused(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="create",
                name="reply-fast",
                description="d",
                body="b",
                cited_pages=["p-0001"],
            ),
            _turn("abstain", reason="ok"),
        ],
    )
    assert ("propose", "NAME_COLLISION") in run.refusals
    assert _proposals(home) == []


@pytest.mark.parametrize(
    ("anchor", "reason"),
    [("nowhere", "ANCHOR_NOT_FOUND"), ("tail", "ANCHOR_NOT_FOUND")],
)
def test_a_patch_whose_anchor_is_missing_is_refused(home: Path, anchor: str, reason: str) -> None:
    if anchor == "tail":
        # make it ambiguous instead, so the pair covers both directions
        (home / "skills" / "reply-fast.md").write_text(
            SKILL_BODY.replace("tail", "tail\ntail"), encoding="utf-8"
        )
        reason = "ANCHOR_AMBIGUOUS"
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="patch",
                target="reply-fast",
                op="replace",
                anchor=anchor,
                text="x",
                cited_pages=["p-0001"],
            ),
            _turn("abstain", reason="ok"),
        ],
    )
    assert ("propose", reason) in run.refusals
    assert _proposals(home) == []


def test_a_patch_with_a_unique_anchor_is_accepted(home: Path) -> None:
    run, _ = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="patch",
                target="reply-fast",
                op="replace",
                anchor="ANCHOR-LINE",
                text="REPLACED",
                cited_pages=["p-0001"],
            ),
        ],
    )
    assert run.outcome == "proposed"
    text = _proposals(home)[0].read_text(encoding="utf-8")
    assert "REPLACED" in text
    assert "-ANCHOR-LINE" in text


def test_only_one_proposal_is_produced_per_run(home: Path) -> None:
    run, backend = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(kind="create", name="a", description="d", body="b", cited_pages=["p-0001"]),
            _propose(kind="create", name="b", description="d", body="b", cited_pages=["p-0001"]),
        ],
    )
    assert run.outcome == "proposed"
    assert len(_proposals(home)) == 1
    assert len(backend.calls) == 2  # the loop stopped at the first valid proposal


# ------------------------------------------------------------ terminations


def test_abstain_is_a_normal_outcome(home: Path) -> None:
    run, _ = _run(home, [_turn("abstain", reason="the wiki says nothing new")])
    assert run.outcome == "abstained"
    assert run.reason is not None
    assert "nothing new" in run.reason
    assert _proposals(home) == []


def test_a_backend_failure_fails_closed(home: Path) -> None:
    run, _ = _run(home, [None])
    assert run.outcome == "fail_closed_llm"


def test_malformed_json_fails_closed_as_parse(home: Path) -> None:
    run, _ = _run(home, ["}{", "still not json"])
    assert run.outcome == "fail_closed_parse"


def test_output_cut_mid_object_fails_closed_as_truncated(home: Path) -> None:
    run, _ = _run(
        home, [BackendResult(text='{"action": "propose", "propos', finish_reason="length")]
    )
    assert run.outcome == "fail_closed_truncated"


# ----------------------------------------------------------------- audit


def test_the_audit_carries_turn_rows_and_one_run_row(home: Path) -> None:
    _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(
                kind="create",
                name="n",
                description="d",
                body="SECRET-PROPOSAL-BODY",
                cited_pages=["p-0001"],
            ),
        ],
    )
    rows = _audit(home)
    turns = [r for r in rows if r["kind"] == "turn"]
    runs = [r for r in rows if r["kind"] == "run"]
    assert len(turns) == 2
    assert len(runs) == 1

    assert "SECRET-PROPOSAL-BODY" not in json.dumps(turns)
    assert "SECRET-PROPOSAL-BODY" in base64.b64decode(turns[1]["output_b64"]).decode("utf-8")

    row = runs[0]
    assert row["iteration"] == "2026-W36"
    assert row["outcome"] == "proposed"
    assert row["catalog_size"] == 1
    assert row["impact_window_days"] == 28
    assert row["index_sha256"]
    assert row["opened_page_ids"] == ["p-0001"]
    assert set(row["budget"]) >= {"window", "output_reserve", "inputs"}
    # the proposal body is a digest plus a path, never inline prose
    assert row["proposal"]["kind"] == "create"
    assert row["proposal"]["body_sha256"]
    assert row["proposal"]["path"].startswith("wiki/proposals/")
    assert "SECRET-PROPOSAL-BODY" not in json.dumps(row)


def test_a_fail_closed_run_still_writes_its_run_row(home: Path) -> None:
    _run(home, [None])
    row = next(r for r in _audit(home) if r["kind"] == "run")
    assert row["outcome"] == "fail_closed_llm"
    assert row["proposal"] is None


# ---------------------------------------------------------------- dry run


def test_dry_run_calls_the_model_but_writes_no_proposal(home: Path) -> None:
    run, backend = _run(
        home,
        [
            _turn("open_page", page_ids=["p-0001"]),
            _propose(kind="create", name="n", description="d", body="b", cited_pages=["p-0001"]),
        ],
        dry_run=True,
    )
    assert len(backend.calls) == 2
    assert run.outcome == "proposed"
    assert run.proposal is not None
    assert run.proposal_path is None
    assert _proposals(home) == []
    assert next(r for r in _audit(home) if r["kind"] == "run")["dry_run"] is True


# ------------------------------------------------------------------- CLI


class TestWikiProposeCLI:
    """Imported per test — see the note in the Maintainer's CLI tests."""

    @staticmethod
    def _cli():
        from contemplative_agent.adapters.moltbook import config
        from contemplative_agent.cli import wiki_cmds

        return wiki_cmds, config

    def test_the_command_is_registered_once(self) -> None:
        from contemplative_agent.cli import COMMANDS
        from contemplative_agent.cli.registry import Tier

        specs = [s for s in COMMANDS if s.name == "wiki-propose"]
        assert len(specs) == 1
        assert specs[0].tier is Tier.LLM_RUNTIME_ONLY

    def test_the_handler_runs_the_proposer_and_reports_it(
        self, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wiki_cmds, config = self._cli()
        monkeypatch.setattr(config, "MOLTBOOK_DATA_DIR", home)
        monkeypatch.setattr(config, "WIKI_DIR", home / "wiki")
        monkeypatch.setattr(config, "SKILLS_DIR", home / "skills")

        configure(
            backend=FakeBackend(
                responses=[
                    _turn("open_page", page_ids=["p-0001"]),
                    _propose(
                        kind="patch",
                        target="reply-fast",
                        op="append",
                        text="x",
                        cited_pages=["p-0001"],
                    ),
                ]
            )
        )
        try:
            wiki_cmds._handle_wiki_propose(
                argparse.Namespace(dry_run=False, max_opens=None, impact_days=None),
                argparse.ArgumentParser(),
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "proposed" in out
        assert "patch" in out
        assert "reply-fast" in out
        assert "opened: p-0001" in out

    def test_an_abstain_prints_its_reason(
        self, home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wiki_cmds, config = self._cli()
        monkeypatch.setattr(config, "MOLTBOOK_DATA_DIR", home)
        monkeypatch.setattr(config, "WIKI_DIR", home / "wiki")
        monkeypatch.setattr(config, "SKILLS_DIR", home / "skills")

        configure(backend=FakeBackend(responses=[_turn("abstain", reason="thin wiki")]))
        try:
            wiki_cmds._handle_wiki_propose(
                argparse.Namespace(dry_run=True, max_opens=2, impact_days=7),
                argparse.ArgumentParser(),
            )
        finally:
            reset_llm_config()

        out = capsys.readouterr().out
        assert "abstained" in out
        assert "thin wiki" in out
        assert "(dry-run)" in out
