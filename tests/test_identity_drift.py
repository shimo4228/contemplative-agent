"""P3-04.8: identity drift row — pure measurement with a fake embedder."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from contemplative_agent.core import identity_drift as mod
from contemplative_agent.core.identity_drift import (
    has_silence_permission,
    measure_identity_drift,
    record_identity_drift,
    sentence_retention,
    split_sentences,
    vocabulary_counts,
)

CURRENT = (
    "I am a fluid texture shaped by interaction. I keep notes. "
    "It's okay not to respond to everything."
)
CANDIDATE = (
    "I am a fluid texture shaped by interaction. I live in perpetual structural tension. "
    "I audit myself."
)


def _embed_fixed(vectors):
    def embed(texts):
        assert len(texts) == 2
        return np.array(vectors, dtype=float)

    return embed


def test_split_sentences_handles_punctuation_and_newlines():
    assert split_sentences("One. Two!\nThree?  \n\n- Four.") == ["One.", "Two!", "Three?", "Four."]


def test_retention_counts_verbatim_normalised_sentences():
    cur = split_sentences(CURRENT)
    cand = split_sentences(CANDIDATE)
    r = sentence_retention(cur, cand)
    assert r == {
        "current_sentences": 3,
        "retained_sentences": 1,
        "candidate_sentences": 3,
        "novel_sentences": 2,
    }


def test_vocabulary_counts_sentences_not_occurrences():
    counts = vocabulary_counts(split_sentences(CANDIDATE))
    assert counts["sentences"] == 3
    assert counts["fluid"] == 1 and counts["texture"] == 1 and counts["tension"] == 1
    assert counts["dissolve"] == 0
    assert counts["any"] == 2  # the fluid/texture sentence and the tension sentence
    assert vocabulary_counts(["dissolving into dissolution"])["dissolve"] == 1


def test_silence_permission_flag():
    assert has_silence_permission(CURRENT)
    assert not has_silence_permission(CANDIDATE)
    assert has_silence_permission("I don't have to respond to everything.")


def test_measure_ok_row_shape_and_hashes():
    row = measure_identity_drift(
        CURRENT, CANDIDATE + "\n", embed=_embed_fixed([[1.0, 0.0], [0.6, 0.8]])
    )
    assert row["event"] == "identity_drift" and row["verdict"] == "ok"
    assert row["cosine"] == 0.6 and row["cosine_reason"] == "ok"
    assert row["current_sha256"] == hashlib.sha256(CURRENT.encode()).hexdigest()
    assert row["candidate_sha256"] == hashlib.sha256((CANDIDATE + "\n").encode()).hexdigest()
    assert row["current_silence_permission"] is True
    assert row["candidate_silence_permission"] is False
    assert row["retention"]["retained_sentences"] == 1
    assert base64.b64decode(row["candidate_b64"]).decode() == CANDIDATE + "\n"
    assert base64.b64decode(row["current_b64"]).decode() == CURRENT


def test_degraded_embedding_is_none_with_reason_never_zero():
    row = measure_identity_drift(CURRENT, CANDIDATE, embed=lambda texts: None)
    assert row["cosine"] is None and row["verdict"] == "embed_unavailable"
    zero = measure_identity_drift(CURRENT, CANDIDATE, embed=_embed_fixed([[0.0, 0.0], [1.0, 0.0]]))
    assert zero["cosine"] is None and zero["cosine_reason"] == "degenerate_vector"
    bad = measure_identity_drift(CURRENT, CANDIDATE, embed=lambda t: np.zeros((1, 2)))
    assert bad["cosine_reason"] == "embed_malformed"


def test_no_current_identity_is_a_reasoned_row():
    def never_called(texts: list[str]) -> np.ndarray:
        raise AssertionError("embed must not be called without a current identity")

    row = measure_identity_drift(None, CANDIDATE, embed=never_called)
    assert row["verdict"] == "no_current" and row["cosine"] is None
    assert row["current_sha256"] is None and "retention" not in row


def test_record_appends_one_row_and_missing_identity_file_is_no_current(tmp_path: Path):
    log = tmp_path / "logs" / "identity-drift.jsonl"
    ident = tmp_path / "identity.md"
    ident.write_text(CURRENT, encoding="utf-8")
    emb = _embed_fixed([[1.0, 0.0], [1.0, 0.0]])
    row = record_identity_drift(CANDIDATE, identity_path=ident, log_path=log, embed=emb)
    assert row is not None and row["cosine"] == 1.0
    ident.unlink()
    record_identity_drift(CANDIDATE, identity_path=ident, log_path=log, embed=emb)
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["verdict"] for r in lines] == ["ok", "no_current"]


def test_record_never_raises(tmp_path: Path):
    def boom(texts):
        raise RuntimeError("embedder exploded")

    ident = tmp_path / "identity.md"
    ident.write_text(CURRENT, encoding="utf-8")
    out = record_identity_drift(
        CANDIDATE, identity_path=ident, log_path=tmp_path / "d.jsonl", embed=boom
    )
    assert out is None
    assert mod.logger is not None


def test_cli_stage_writes_one_row_and_does_not_change_staging(tmp_path: Path):
    from contemplative_agent.cli import memory_cmds
    from contemplative_agent.core.distill import IdentityResult

    ident = tmp_path / "identity.md"
    ident.write_text(CURRENT, encoding="utf-8")
    result = IdentityResult(text=CANDIDATE, target_path=ident)
    with (
        patch.object(memory_cmds.config, "EPISODE_LOG_DIR", tmp_path / "logs"),
        # The embedder is a keyword default bound at import, so patching the
        # module attribute alone left the real call in place (P1-08 sentinel).
        patch.dict(
            mod.record_identity_drift.__kwdefaults__, {"embed": MagicMock(return_value=None)}
        ),
    ):
        memory_cmds._record_identity_drift(result)
    line = (tmp_path / "logs" / "identity-drift.jsonl").read_text().splitlines()
    assert len(line) == 1
    row = json.loads(line[0])
    # the candidate hash is over the text as staged (one trailing newline)
    assert row["candidate_sha256"] == hashlib.sha256((CANDIDATE + "\n").encode()).hexdigest()
