"""RFC-0017 S1: the wiki store and its four-verb operation vocabulary.

Every refusal here is a *result*, never an exception (ADR-0075 forbids the
silent fallback and the packet forbids the raise): a Maintainer that emits a
bad op must be able to read back why, offline, from
``logs/wiki-ops.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contemplative_agent.core import wiki


@pytest.fixture()
def store(tmp_path: Path) -> wiki.WikiStore:
    return wiki.WikiStore(wiki_dir=tmp_path / "wiki", data_root=tmp_path)


def _ops_log(store: wiki.WikiStore) -> list[dict]:
    path = store.data_root / "logs" / "wiki-ops.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ------------------------------------------------------------------ create


def test_create_allocates_monotonic_ids_and_writes_a_page(store: wiki.WikiStore) -> None:
    first = store.apply(wiki.Create(title="Reply latency", body="Body one.", sources=("e1",)))
    second = store.apply(wiki.Create(title="Upvote shape", body="Body two.", sources=("e2",)))

    assert (first.applied, first.page_id) == (True, "p-0001")
    assert (second.applied, second.page_id) == (True, "p-0002")
    assert first.reason is None

    page = store.wiki_dir / "patterns" / "p-0001.md"
    text = page.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "id: p-0001" in text
    assert "title: Reply latency" in text
    assert "revisions: 1" in text
    assert "  - e1" in text
    assert text.rstrip().endswith("Body one.")


def test_create_ids_continue_after_a_restart(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="a", sources=("e1",)))
    reopened = wiki.WikiStore(wiki_dir=store.wiki_dir, data_root=store.data_root)
    result = reopened.apply(wiki.Create(title="B", body="b", sources=("e2",)))
    assert result.page_id == "p-0002"


def test_read_page_returns_frontmatter_and_body(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="Reply latency", body="Body one.", sources=("e1",)))
    page = store.read_page("p-0001")
    assert page is not None
    assert page.page_id == "p-0001"
    assert page.title == "Reply latency"
    assert page.revisions == 1
    assert page.sources == ("e1",)
    assert page.body.strip() == "Body one."


def test_read_page_of_an_unknown_id_is_none(store: wiki.WikiStore) -> None:
    assert store.read_page("p-9999") is None


# ------------------------------------------------------------------ append


def test_append_extends_the_body_and_accumulates_sources(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="line one", sources=("e1",)))
    result = store.apply(wiki.Append(page_id="p-0001", text="line two", sources=("e2", "e1")))

    assert result.applied
    page = store.read_page("p-0001")
    assert page is not None
    assert page.body.splitlines()[0] == "line one"
    assert "line two" in page.body
    # Existing sources keep their order; new ones are appended once.
    assert page.sources == ("e1", "e2")
    assert page.revisions == 2


# ----------------------------------------------------------------- replace


def test_replace_applies_on_exactly_one_anchor_match(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="alpha beta gamma", sources=("e1",)))
    result = store.apply(wiki.Replace(page_id="p-0001", old="beta", new="BETA", sources=("e2",)))

    assert result.applied
    page = store.read_page("p-0001")
    assert page is not None
    assert page.body.strip() == "alpha BETA gamma"


def test_replace_refuses_when_the_anchor_is_absent(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="alpha", sources=("e1",)))
    result = store.apply(wiki.Replace(page_id="p-0001", old="zeta", new="Z", sources=("e2",)))

    assert result.applied is False
    assert result.reason == "ANCHOR_NOT_FOUND"
    assert store.read_page("p-0001").body.strip() == "alpha"  # type: ignore[union-attr]


def test_replace_refuses_an_ambiguous_anchor(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="beta and beta", sources=("e1",)))
    result = store.apply(wiki.Replace(page_id="p-0001", old="beta", new="B", sources=("e2",)))

    assert result.applied is False
    assert result.reason == "ANCHOR_AMBIGUOUS"
    assert store.read_page("p-0001").body.strip() == "beta and beta"  # type: ignore[union-attr]


# ------------------------------------------------------------ insert_after


def test_insert_after_places_text_below_the_anchor(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="head\nanchor\ntail", sources=("e1",)))
    result = store.apply(
        wiki.InsertAfter(page_id="p-0001", anchor="anchor", text="inserted", sources=("e2",))
    )

    assert result.applied
    page = store.read_page("p-0001")
    assert page is not None
    assert page.body.strip().splitlines() == ["head", "anchor", "inserted", "tail"]


def test_insert_after_refuses_on_zero_and_on_many_matches(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="anchor\nanchor", sources=("e1",)))
    ambiguous = store.apply(
        wiki.InsertAfter(page_id="p-0001", anchor="anchor", text="x", sources=("e2",))
    )
    absent = store.apply(
        wiki.InsertAfter(page_id="p-0001", anchor="nowhere", text="x", sources=("e2",))
    )

    assert (ambiguous.applied, ambiguous.reason) == (False, "ANCHOR_AMBIGUOUS")
    assert (absent.applied, absent.reason) == (False, "ANCHOR_NOT_FOUND")


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    "op",
    [
        wiki.Append(page_id="p-0404", text="x", sources=("e1",)),
        wiki.Replace(page_id="p-0404", old="a", new="b", sources=("e1",)),
        wiki.InsertAfter(page_id="p-0404", anchor="a", text="b", sources=("e1",)),
    ],
)
def test_unknown_page_is_refused(store: wiki.WikiStore, op: wiki.WikiOp) -> None:
    result = store.apply(op)
    assert (result.applied, result.reason) == (False, "PAGE_NOT_FOUND")


@pytest.mark.parametrize(
    "page_id",
    ["../escape", "p-0001/../../etc", "", "not-an-id", "p-0001.md"],
)
def test_a_malformed_page_id_never_leaves_the_store(store: wiki.WikiStore, page_id: str) -> None:
    store.apply(wiki.Create(title="A", body="a", sources=("e1",)))
    result = store.apply(wiki.Append(page_id=page_id, text="x", sources=("e1",)))
    assert (result.applied, result.reason) == (False, "PAGE_NOT_FOUND")


def test_page_path_stays_inside_the_wiki_dir_even_via_a_symlink(
    store: wiki.WikiStore, tmp_path: Path
) -> None:
    store.apply(wiki.Create(title="A", body="a", sources=("e1",)))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "p-0002.md").write_text("---\nid: p-0002\n---\nplanted", encoding="utf-8")
    (store.wiki_dir / "patterns" / "p-0002.md").symlink_to(outside / "p-0002.md")

    result = store.apply(wiki.Append(page_id="p-0002", text="x", sources=("e1",)))

    assert (result.applied, result.reason) == (False, "PATH_ESCAPED")
    assert (outside / "p-0002.md").read_text(encoding="utf-8").endswith("planted")


@pytest.mark.parametrize(
    "op",
    [
        wiki.Create(title="A", body="a", sources=()),
        wiki.Append(page_id="p-0001", text="x", sources=()),
        wiki.Replace(page_id="p-0001", old="a", new="b", sources=()),
        wiki.InsertAfter(page_id="p-0001", anchor="a", text="b", sources=()),
    ],
)
def test_empty_sources_are_refused(store: wiki.WikiStore, op: wiki.WikiOp) -> None:
    store.apply(wiki.Create(title="seed", body="a", sources=("e1",)))
    result = store.apply(op)
    assert (result.applied, result.reason) == (False, "SOURCES_EMPTY")


def test_create_refuses_an_empty_title(store: wiki.WikiStore) -> None:
    result = store.apply(wiki.Create(title="   ", body="a", sources=("e1",)))
    assert (result.applied, result.reason) == (False, "TITLE_EMPTY")


def test_create_refuses_an_empty_body(store: wiki.WikiStore) -> None:
    result = store.apply(wiki.Create(title="A", body="  \n ", sources=("e1",)))
    assert (result.applied, result.reason) == (False, "TEXT_EMPTY")


def test_a_refusal_is_a_result_not_an_exception(store: wiki.WikiStore) -> None:
    # The whole vocabulary, on an empty store, returns rather than raises.
    for op in (
        wiki.Append(page_id="p-0001", text="x", sources=("e1",)),
        wiki.Replace(page_id="p-0001", old="a", new="b", sources=("e1",)),
        wiki.InsertAfter(page_id="p-0001", anchor="a", text="b", sources=("e1",)),
    ):
        assert store.apply(op).applied is False


# ------------------------------------------------------------- atomic write


def test_a_failed_write_leaves_no_partial_page(
    store: wiki.WikiStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.apply(wiki.Create(title="A", body="original", sources=("e1",)))

    def boom(path: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(wiki, "write_restricted", boom)
    with pytest.raises(OSError):
        store.apply(wiki.Append(page_id="p-0001", text="doomed", sources=("e2",)))

    page = store.read_page("p-0001")
    assert page is not None
    assert page.body.strip() == "original"
    assert list((store.wiki_dir / "patterns").glob("*.tmp")) == []


# ------------------------------------------------------------- audit log


def test_every_application_and_refusal_is_logged_without_the_body(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="secret body", sources=("e1",)))
    store.apply(wiki.Replace(page_id="p-0001", old="nope", new="x", sources=("e2",)))

    rows = _ops_log(store)
    assert len(rows) == 2

    created, refused = rows
    assert created["op"] == "create"
    assert created["page_id"] == "p-0001"
    assert created["applied"] is True
    assert created["reason"] is None
    assert created["sources"] == ["e1"]
    assert created["text_sha256"] == hashlib.sha256(b"secret body").hexdigest()
    assert created["ts"]
    assert "secret body" not in json.dumps(created)

    assert (refused["op"], refused["applied"], refused["reason"]) == (
        "replace",
        False,
        "ANCHOR_NOT_FOUND",
    )


def test_the_audit_log_survives_an_unwritable_log_dir(
    store: wiki.WikiStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log failure must not silently drop the op's own outcome."""

    def boom(path: Path, record: dict) -> None:
        raise OSError("read-only fs")

    monkeypatch.setattr(wiki, "append_jsonl_restricted", boom)
    result = store.apply(wiki.Create(title="A", body="a", sources=("e1",)))
    # The page still lands and the caller still learns what happened; the
    # dropped row is warned about, not swallowed into a false refusal.
    assert result.applied is True
    assert store.read_page("p-0001") is not None


# ---------------------------------------------------------------- index


def test_render_index_of_an_empty_store_is_a_deterministic_heading(
    store: wiki.WikiStore,
) -> None:
    out = wiki.render_index(store.wiki_dir)
    assert out.strip()
    assert "0" in out
    assert out == wiki.render_index(store.wiki_dir)


def test_render_index_lists_id_title_and_first_line_in_id_order(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="Zulu", body="first zulu line\nsecond", sources=("e1",)))
    store.apply(wiki.Create(title="Alpha", body="first alpha line", sources=("e2",)))

    out = wiki.render_index(store.wiki_dir)
    lines = [line for line in out.splitlines() if line.startswith("p-")]
    assert lines[0].startswith("p-0001")
    assert "Zulu" in lines[0]
    assert "first zulu line" in lines[0]
    assert lines[1].startswith("p-0002")
    assert "Alpha" in lines[1]


def test_render_index_skips_an_unreadable_page_and_counts_it(store: wiki.WikiStore) -> None:
    store.apply(wiki.Create(title="A", body="a", sources=("e1",)))
    (store.wiki_dir / "patterns" / "p-0002.md").write_text("no frontmatter here", encoding="utf-8")

    out = wiki.render_index(store.wiki_dir)
    assert "p-0001" in out
    assert "p-0002" not in out
    assert "1" in out
