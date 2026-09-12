"""Tests for the RFC-0027 one-time case selector (scripts/rfc0027_select_cases.py).

The selector reads the production store, so the properties worth pinning are
the ones that keep it read-only and keep third-party prose out of public
evidence — plus the corner rule, which is the part a reader of the frozen
evidence has to be able to trust.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rfc0027_select_cases as sel  # noqa: E402  # pyright: ignore[reportMissingImports]


def _record(text: str, source: str, *, embedding: list[float] | None = None, expired: bool = False):
    return {
        "pattern": text,
        "source": source,
        "valid_until": "2026-09-01" if expired else None,
        "embedding": embedding if embedding is not None else [1.0, 0.0, 0.0],
    }


@pytest.mark.parametrize(
    "text",
    [
        "See https://example.com for the thread.",
        "The reply from @someone reframed the question.",
        'They wrote "this is a long verbatim sentence lifted from their post" in reply.',
        "They wrote 'this is a long verbatim sentence lifted from their post' in reply.",
    ],
)
def test_publication_filter_rejects_third_party_spans(text: str) -> None:
    assert not sel._publishable(text)


def test_publication_filter_keeps_short_quoted_terms() -> None:
    assert sel._publishable("I flagged the term 'functional continuity' as load bearing.")


def test_population_filter_counts_every_exclusion(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.json"
    store.write_text(
        json.dumps(
            [
                _record("kept observation about boundaries", "2026-07-10"),
                _record("expired observation", "2026-07-10", expired=True),
                _record("too old", "2026-05-01"),
                _record("link to https://example.com", "2026-07-10"),
                _record("kept observation about boundaries", "2026-07-11"),
                {"pattern": "no embedding", "source": "2026-07-10", "valid_until": None},
            ]
        ),
        encoding="utf-8",
    )
    patterns, counts = sel._load_population(
        store, window_start="2026-07-01", window_end="2026-07-31"
    )
    assert counts == {
        "total": 6,
        "expired": 1,
        "out_of_window": 1,
        "third_party": 1,
        "duplicate": 1,
        "no_embedding": 1,
        "kept": 1,
    }
    assert [p["text"] for p in patterns] == ["kept observation about boundaries"]


def test_output_paths_are_confined_to_evidence_and_fixtures(tmp_path: Path) -> None:
    sel._validate_output_path(sel.EVIDENCE_ROOT / "x.json")
    sel._validate_output_path(sel.FIXTURE_ROOT / "x.json")
    with pytest.raises(ValueError):
        sel._validate_output_path(tmp_path / "escape.json")
    with pytest.raises(ValueError):
        sel._validate_output_path(sel.EVIDENCE_ROOT.parent / "escape.json")


def test_cluster_is_single_link_over_the_threshold() -> None:
    sim = np.array(
        [
            [1.0, 0.9, 0.1],
            [0.9, 1.0, 0.1],
            [0.1, 0.1, 1.0],
        ]
    )
    assert sel._cluster(sim, 0.8) == [[0, 1], [2]]
    assert sel._cluster(sim, 0.95) == [[0], [1], [2]]


def _synthetic_population() -> tuple[list[dict], list[dict[str, str]]]:
    """Four separable corners built from unit vectors in three planes.

    Each covered cluster sits near a skill vector; the uncovered cluster sits
    in a direction no skill occupies; the thin singleton is short and far from
    every skill.
    """

    def vec(angle: float, plane: tuple[int, int]) -> list[float]:
        v = [0.0, 0.0, 0.0, 0.0]
        v[plane[0]] = float(np.cos(angle))
        v[plane[1]] = float(np.sin(angle))
        return v

    patterns: list[dict] = []

    def add(prefix: str, angles: list[float], plane: tuple[int, int], text: str) -> None:
        for index, angle in enumerate(angles):
            patterns.append(
                {
                    "id": f"{prefix}-{index}",
                    "text": text,
                    "source": f"2026-07-{10 + index:02d}",
                    "sha256": f"{prefix}{index}",
                    "embedding": np.asarray(vec(angle, plane), dtype=np.float32),
                }
            )

    tight = [0.00, 0.02, 0.04]
    spread = [0.50, 0.62, 0.74]
    add("tight", tight, (0, 1), "a repeated observation about the same covered condition")
    add("spread", spread, (0, 1), "a recurring theme observed under differing conditions")
    add("uncovered", [1.55, 1.57, 1.59], (0, 1), "an observation the catalogue does not cover")
    patterns.append(
        {
            "id": "thin-0",
            "text": "short",
            "source": "2026-07-20",
            "sha256": "thin0",
            "embedding": np.asarray([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
        }
    )
    skills = [
        {"name": "covers-tight", "text": "skill covering the tight cluster"},
        {"name": "covers-spread", "text": "skill covering the spread cluster"},
    ]
    return patterns, skills


def test_select_assigns_each_corner(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns, skills = _synthetic_population()
    skill_vectors = np.asarray(
        [[1.0, 0.02, 0.0, 0.0], [float(np.cos(0.62)), float(np.sin(0.62)), 0.0, 0.0]],
        dtype=np.float32,
    )
    monkeypatch.setattr(sel, "embed_texts", lambda texts: skill_vectors)
    cases, selections, stats = sel.select(
        patterns,
        skills,
        cluster_threshold=0.9,
        coverage_high_q=0.5,
        coverage_low_q=0.5,
        cohesion_q=0.5,
        singleton_length_q=1.0,
        per_kind=1,
        max_patterns=3,
        max_skills=2,
    )
    labels = {s["kind_label"]: s for s in selections}
    assert set(labels) == {"reconfirm", "revise", "new", "insufficient"}
    assert labels["reconfirm"]["pattern_ids"][0].startswith("tight")
    assert labels["revise"]["pattern_ids"][0].startswith("spread")
    assert labels["new"]["pattern_ids"][0].startswith("uncovered")
    assert labels["insufficient"]["pattern_ids"] == ["thin-0"]
    assert stats["bucket_sizes"]["new"] >= 1
    # Every case carries a holdout from a day that is not in the case itself.
    for selection in selections:
        holdout = selection["holdout_scene"]
        if holdout is not None:
            assert holdout["source"] not in selection["pattern_sources"]
    # Harness contract: the emitted cases must load unchanged.
    assert {c["case_id"] for c in cases} == {s["case_id"] for s in selections}


def test_select_refuses_when_a_corner_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns, skills = _synthetic_population()
    monkeypatch.setattr(
        sel,
        "embed_texts",
        lambda texts: np.asarray([[1.0, 0.0, 0.0, 0.0]] * len(skills), dtype=np.float32),
    )
    with pytest.raises(RuntimeError, match="candidate"):
        sel.select(
            patterns,
            skills,
            cluster_threshold=0.9,
            coverage_high_q=0.5,
            coverage_low_q=0.5,
            cohesion_q=0.5,
            singleton_length_q=1.0,
            per_kind=3,
            max_patterns=3,
            max_skills=2,
        )
