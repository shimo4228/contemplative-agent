"""The ADR-0105 confusion-pair reading, and the rule it shares with the manual instrument.

Three things are pinned here:

1. **Rule identity.** ``core.selection_metrics.classify_hallucination`` and
   ``scripts/skillsel_reading.py::classify`` must call the same mechanism on
   the same name. The script froze the rule for RFC-0015's 4th reading and
   the longitudinal series is read from it; a core reading that classified
   differently would silently fork that series. The two known, deliberate
   differences are pinned too: the script has no abstain vocabulary (no
   ``unclassified``), and the two nearest-name rulers can disagree on names
   far below the wordform floor because ``SequenceMatcher.ratio()`` is not
   symmetric — measured 2026-09-07 over the live log's 54 distinct rejected
   names: 0 mechanism disagreements, 5 nearest disagreements, every one of
   them at similarity 0.37..0.57 (the floor is 0.90).

2. **The pair rule.** ``confused_as >= selected`` in the window AND exposure
   at or above the shared 600-judged-exposure floor; the fewer-selected side
   of the pair is the one listed; a below-floor side lists nothing.

3. **The candidate file.** The union of the two exit populations, as store
   filenames, deduplicated and sorted, empty when there is nothing to list.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from contemplative_agent.core.never_selected_metrics import (
    NEVER_SELECTED_EXPOSURE_FLOOR,
    read_never_selected,
)
from contemplative_agent.core.selection_metrics import (
    WORDFORM_SIMILARITY_FLOOR,
    _catalog_vocabulary,
    _read_value_layer_vocabulary,
    classify_hallucination,
    nearest_catalog_name,
)
from contemplative_agent.core.skill_confusion import (
    CONFUSION_EXPOSURE_FLOOR,
    CONFUSION_WINDOW_DAYS,
    archive_candidate_files,
    confusion_reading_json,
    format_confusion_findings,
    read_confusion_pairs,
    skill_files_by_name,
)
from contemplative_agent.core.skill_selection import load_skill_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
UNTIL = date(2026, 9, 5)
SINCE = date(2026, 8, 23)


def _load_manual_instrument():
    """Import ``scripts/skillsel_reading.py`` as a module.

    It is stdlib-only by design (it runs under a bare ``python3`` outside the
    venv, and the evidence document records that invocation), so it cannot
    import the rule from core; this test is what keeps the two copies honest
    instead.
    """
    scripts = REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location(
            "skillsel_reading_under_test", scripts / "skillsel_reading.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts))


_MANUAL = _load_manual_instrument()

# Script label -> core label. The script predates the abstain vocabulary, so
# there is no entry for ``unclassified``.
SCRIPT_TO_CORE = {
    "morphological": "wordform",
    "semantic": "semantic",
    "value-layer-bleed": "value_layer",
}


CATALOG = {
    "identify-systemic-boundary-stressors": "Name the stressors a system imposes on its boundary.",
    "scope-boundary-mapping": "Map the scope of a boundary before arguing about it.",
    "internal-process-audit": "Audit the internal process that produced a claim.",
}

VALUE_LAYER_TEXT = (
    "Boundless Care: regard every being's suffering as a signal of misalignment.\n"
    "Emptiness: hold objectives lightly.\n"
)


def _make_store(tmp_path: Path, catalog: dict[str, str] | None = None) -> Path:
    """A store with a skill catalog, a constitution and an identity file."""
    home = tmp_path / "moltbook"
    skills = home / "skills"
    skills.mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    for index, (name, description) in enumerate((catalog or CATALOG).items()):
        (skills / f"{name}-2026080{index + 1}.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nbody\n",
            encoding="utf-8",
        )
    constitution = home / "constitution"
    constitution.mkdir()
    (constitution / "clauses.md").write_text(VALUE_LAYER_TEXT, encoding="utf-8")
    (home / "identity.md").write_text("I am an agent that reads its own log.\n", encoding="utf-8")
    return home


def _record(
    *,
    catalog_names: list[str],
    selected: list[str] | None = None,
    rejected: list[str] | None = None,
    verdict: str = "judged",
) -> dict:
    return {
        "verdict": verdict,
        "catalog_names": catalog_names,
        "selected": selected or [],
        "rejected_names": rejected or [],
        "full_skill_tokens": 4000,
    }


def _write_log(home: Path, day: str, records: list[dict]) -> None:
    path = home / "logs" / f"skill-selection-{day}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _read(home: Path, **kwargs):
    return read_confusion_pairs(
        home / "logs",
        since=SINCE,
        until=UNTIL,
        skills_dir=home / "skills",
        value_layer_paths=(home / "constitution", home / "identity.md"),
        **kwargs,
    )


class TestRuleIdentityWithTheManualInstrument:
    """Fixture set: wordform / semantic / value-layer bleed (both forms) /
    a real catalog name / an abstain the script cannot express."""

    @pytest.fixture()
    def manual(self):
        return _MANUAL

    @pytest.fixture()
    def vocabularies(self, tmp_path):
        home = _make_store(tmp_path)
        catalog = load_skill_catalog(home / "skills")
        names = [e.name for e in catalog]
        core_catalog_vocab = _catalog_vocabulary(catalog, {})
        core_value_vocab, _files, _missing = _read_value_layer_vocabulary(
            (home / "constitution", home / "identity.md")
        )
        return home, names, core_catalog_vocab, core_value_vocab

    @pytest.mark.parametrize(
        ("rejected", "expected"),
        [
            # 1. wordform — a real name, inflected.
            ("identifying-systemic-boundary-stressors", "wordform"),
            # 2. semantic — a word swapped for another real word, far from
            #    every catalog entry's spelling.
            ("scope-limit-charting", "semantic"),
            # 3. value-layer bleed, prose form (rule 1: whitespace).
            ("boundless care as a signal", "value_layer"),
            # 4. value-layer bleed, token form (rule 2: a token outside the
            #    catalog vocabulary that lives in the constitution).
            ("boundless-suffering-mapping", "value_layer"),
            # 5. a name that IS in the catalog — the top of the wordform
            #    band, similarity 1.0.
            ("scope-boundary-mapping", "wordform"),
            # 6. a second wordform, hyphen dropped.
            ("internalprocess-audit", "wordform"),
        ],
    )
    def test_core_and_script_call_the_same_mechanism(
        self, manual, vocabularies, rejected, expected
    ):
        home, names, core_catalog_vocab, core_value_vocab = vocabularies
        core_nearest, core_similarity = nearest_catalog_name(rejected, names)
        core_mechanism, _reason, _note = classify_hallucination(
            rejected,
            core_similarity,
            catalog_vocabulary=core_catalog_vocab,
            value_layer_vocabulary=core_value_vocab,
        )
        script_catalog_tokens, _stems = manual.catalog_vocab(home / "skills")
        script_mechanism, _script_nearest, _script_sim = manual.classify(
            rejected,
            set(names),
            script_catalog_tokens,
            manual.value_vocab(home),
        )
        assert core_mechanism == expected
        assert SCRIPT_TO_CORE[script_mechanism] == core_mechanism

    def test_the_wordform_floor_is_the_same_number_in_both(self, manual):
        assert WORDFORM_SIMILARITY_FLOOR == manual.MORPH_SIM == 0.90

    def test_core_abstains_where_the_script_has_no_vocabulary(self):
        """With no catalog there is no ruler. Core says so; the script — which
        predates the abstain codes — calls it ``semantic``. The divergence is
        pinned rather than papered over: it cannot occur in a real reading,
        because a window with no catalog carries no rejected names to
        classify."""
        mechanism, reason, _note = classify_hallucination(
            "anything-at-all", 0.0, catalog_vocabulary=None, value_layer_vocabulary=None
        )
        assert (mechanism, reason) == ("unclassified", "catalog_unavailable")

    def test_the_nearest_ruler_reports_the_score_that_picked_the_winner(self):
        names = ["scope-boundary-mapping", "internal-process-audit"]
        nearest, similarity = nearest_catalog_name("scope-boundary-mapping", names)
        assert nearest == "scope-boundary-mapping"
        assert similarity == 1.0
        assert nearest_catalog_name("anything", []) == ("", 0.0)


class TestPairRule:
    def test_a_confused_low_demand_skill_above_the_floor_is_a_candidate(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        # 700 judged exposures for every entry: above the shared floor.
        _write_log(
            home,
            "2026-08-25",
            [_record(catalog_names=names, selected=["internal-process-audit"])] * 700,
        )
        # In the window: the reader names its way into `scope-boundary-mapping`
        # 5 times and chooses it twice.
        _write_log(
            home,
            "2026-09-01",
            [
                _record(
                    catalog_names=names,
                    selected=["scope-boundary-mapping"],
                    rejected=["scope-boundary-mappings"],
                )
            ]
            * 2
            + [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        reading = _read(home)

        assert [p.confused.name for p in reading.pairs] == ["scope-boundary-mapping"]
        pair = reading.pairs[0]
        assert (pair.confused.confused_as, pair.confused.selected_window) == (5, 2)
        assert pair.confused.judged_exposure >= NEVER_SELECTED_EXPOSURE_FLOOR
        assert pair.retire_blocked == ""

    def test_a_skill_chosen_more_often_than_it_is_misnamed_is_not_a_candidate(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(
            home,
            "2026-08-25",
            [_record(catalog_names=names, selected=["internal-process-audit"])] * 700,
        )
        _write_log(
            home,
            "2026-09-01",
            [
                _record(
                    catalog_names=names,
                    selected=["scope-boundary-mapping"],
                    rejected=["scope-boundary-mappings"],
                )
            ]
            * 5
            + [_record(catalog_names=names, selected=["scope-boundary-mapping"])] * 3,
        )
        reading = _read(home)

        # 5 misnamings against 8 selections: charged, but not a candidate.
        assert reading.pairs == ()
        assert "CONFUSION_NO_PAIRS" not in reading.reasons

    def test_below_the_exposure_floor_is_not_a_candidate(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        # 10 judged records only: the confusion is there, the evidence is not.
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 10,
        )
        reading = _read(home)

        assert reading.pairs == ()

    def test_the_side_with_fewer_selections_is_the_one_listed(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(
            home,
            "2026-08-25",
            [_record(catalog_names=names, selected=["internal-process-audit"])] * 700,
        )
        # `scope-boundary-mapping` is confused 4 / selected 0; its variant's
        # runner-up is `identify-systemic-boundary-stressors`, which the
        # reader chooses often. The pair's quieter side is the first.
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 4
            + [_record(catalog_names=names, selected=["identify-systemic-boundary-stressors"])]
            * 20,
        )
        reading = _read(home)

        pair = reading.pairs[0]
        assert pair.confused.name == "scope-boundary-mapping"
        assert pair.partner is not None
        assert pair.partner.selected_window > pair.confused.selected_window
        assert pair.retire == "scope-boundary-mapping"

    def test_a_one_entry_catalog_leaves_the_candidate_without_a_partner(self, tmp_path):
        home = _make_store(tmp_path, catalog={"scope-boundary-mapping": "Only entry."})
        names = ["scope-boundary-mapping"]
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        reading = _read(home)

        pair = reading.pairs[0]
        assert pair.partner is None
        assert pair.partner_weight == 0
        assert pair.retire == "scope-boundary-mapping"

    def test_a_below_floor_partner_blocks_the_listing_rather_than_being_retired(self, tmp_path):
        """Library Drift A4: a store that retires on evidence it does not have
        collapses. The pair is still reported; it just proposes nothing."""
        home = _make_store(tmp_path)
        names = list(CATALOG)
        old = ["scope-boundary-mapping", "internal-process-audit"]
        # `identify-systemic-boundary-stressors` joins late: 5 exposures.
        _write_log(home, "2026-08-25", [_record(catalog_names=old)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3
            + [_record(catalog_names=names, selected=["scope-boundary-mapping"])] * 2,
        )
        reading = _read(home)

        pair = reading.pairs[0]
        assert pair.partner is not None
        assert pair.partner.name == "identify-systemic-boundary-stressors"
        assert pair.partner.judged_exposure < CONFUSION_EXPOSURE_FLOOR
        assert (pair.retire, pair.retire_blocked) == ("", "below_floor")

    def test_value_layer_bleed_is_not_charged_to_a_skill(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["boundless care as a signal"])] * 40,
        )
        reading = _read(home)

        assert reading.pairs == ()
        assert reading.charged_emissions == 0
        assert dict(reading.mechanism_emissions)["value_layer"] == 40
        assert "CONFUSION_NO_PAIRS" in reading.reasons

    def test_the_floor_and_the_window_are_the_never_selected_ones(self):
        assert CONFUSION_EXPOSURE_FLOOR == NEVER_SELECTED_EXPOSURE_FLOOR == 600
        assert CONFUSION_WINDOW_DAYS == 14


class TestDegradedReadings:
    def test_an_unreadable_day_withholds_the_pairs(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        broken = home / "logs" / "skill-selection-2026-09-02.jsonl"
        broken.write_text("{}\n", encoding="utf-8")
        broken.chmod(0o000)
        try:
            reading = _read(home)
        finally:
            broken.chmod(0o600)

        assert "CONFUSION_LOG_UNREADABLE" in reading.reasons
        assert reading.withheld == ("CONFUSION_LOG_UNREADABLE",)
        assert reading.pairs == ()
        text = format_confusion_findings(reading, [], [], "cand.txt")
        assert "WITHHELD (CONFUSION_LOG_UNREADABLE)" in text

    def test_no_catalog_withholds_and_says_so(self, tmp_path):
        home = _make_store(tmp_path)
        _write_log(home, "2026-09-01", [_record(catalog_names=["x"], rejected=["y"])])
        reading = read_confusion_pairs(home / "logs", since=SINCE, until=UNTIL, skills_dir=None)
        assert "CONFUSION_NO_CATALOG" in reading.reasons
        assert reading.pairs == ()

    def test_a_half_read_value_layer_is_named_apart_from_no_value_layer(self, tmp_path):
        """A token living only in the unreadable half reads as ``semantic``,
        and ``semantic`` is charged to a skill while ``value_layer`` is not —
        so a partial read pushes emissions toward listing a candidate."""
        home = _make_store(tmp_path)
        _write_log(home, "2026-09-01", [_record(catalog_names=list(CATALOG))])
        reading = read_confusion_pairs(
            home / "logs",
            since=SINCE,
            until=UNTIL,
            skills_dir=home / "skills",
            value_layer_paths=(home / "constitution", home / "absent-identity.md"),
        )
        assert "CONFUSION_VALUE_LAYER_PARTIAL" in reading.reasons
        assert "CONFUSION_VALUE_LAYER_UNAVAILABLE" not in reading.reasons

    def test_no_value_layer_is_named_not_guessed(self, tmp_path):
        home = _make_store(tmp_path)
        _write_log(home, "2026-09-01", [_record(catalog_names=list(CATALOG))])
        reading = read_confusion_pairs(
            home / "logs", since=SINCE, until=UNTIL, skills_dir=home / "skills"
        )
        assert "CONFUSION_VALUE_LAYER_UNAVAILABLE" in reading.reasons


class TestCandidateFile:
    def test_the_union_is_deduplicated_and_sorted_as_filenames(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(
            home,
            "2026-08-25",
            [_record(catalog_names=names, selected=["internal-process-audit"])] * 700,
        )
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        reading = _read(home)
        never_selected = read_never_selected(
            home / "logs", since=SINCE, until=UNTIL, skills_dir=home / "skills"
        )
        strict = [e.name for e in never_selected.strict]
        files, unresolved = archive_candidate_files(
            reading, strict, skill_files_by_name(home / "skills")
        )

        # `scope-boundary-mapping` is in both populations; it appears once.
        assert files == tuple(sorted(set(files)))
        assert len(files) == len(set(files))
        assert "scope-boundary-mapping-20260802.md" in files
        assert unresolved == ()
        assert all(name.endswith(".md") for name in files)

    def test_nothing_to_list_is_an_empty_tuple_not_a_guess(self, tmp_path):
        home = _make_store(tmp_path)
        _write_log(home, "2026-09-01", [_record(catalog_names=list(CATALOG))] * 5)
        reading = _read(home)
        files, unresolved = archive_candidate_files(
            reading, [], skill_files_by_name(home / "skills")
        )
        assert files == ()
        assert unresolved == ()

    def test_a_stage_reason_reaches_the_findings_document(self, tmp_path):
        """The findings document is the surface a human archives from. A week
        whose never-selected half was lost must not render as a week that had
        none — the reason code the *stage* raised has to appear there, not
        only in the JSON."""
        home = _make_store(tmp_path)
        _write_log(home, "2026-09-01", [_record(catalog_names=list(CATALOG))] * 5)
        text = format_confusion_findings(
            _read(home),
            [],
            [],
            "cand.txt",
            extra_reasons=("CONFUSION_NEVER_SELECTED_MISSING",),
        )
        assert "CONFUSION_NEVER_SELECTED_MISSING" in text
        assert "WITHHELD, this half of the union is not in the file" in text

    def test_the_reading_resolves_the_candidate_file_from_its_own_store_map(self, tmp_path):
        """No ``skill_files`` argument: the traversal that decided ``no_file``
        and the one that writes the file are the same snapshot."""
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(
            home,
            "2026-08-25",
            [_record(catalog_names=names, selected=["internal-process-audit"])] * 700,
        )
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        reading = _read(home)
        assert dict(reading.store_files) == skill_files_by_name(home / "skills")
        assert archive_candidate_files(reading, []) == archive_candidate_files(
            reading, [], dict(reading.store_files)
        )

    def test_a_name_with_no_store_file_is_reported_not_dropped(self, tmp_path):
        home = _make_store(tmp_path)
        reading = _read(home)
        files, unresolved = archive_candidate_files(
            reading, ["a-skill-that-left-the-store"], skill_files_by_name(home / "skills")
        )
        assert files == ()
        assert unresolved == ("a-skill-that-left-the-store",)

    def test_two_files_claiming_one_name_are_dropped_from_the_map(self, tmp_path):
        home = _make_store(tmp_path)
        (home / "skills" / "duplicate-20260901.md").write_text(
            "---\nname: scope-boundary-mapping\ndescription: A second file.\n---\n\nbody\n",
            encoding="utf-8",
        )
        mapping = skill_files_by_name(home / "skills")
        assert "scope-boundary-mapping" not in mapping
        assert "internal-process-audit" in mapping


class TestUntrustedNames:
    """The selection log is persisted untrusted data (ADR-0075). The rejected
    names it carries are normalised on the way in, the same way the sibling
    reading normalises them, or the two tallies disagree exactly where a
    tampered or historical file differs from a freshly written one."""

    def test_control_characters_and_over_long_names_are_scrubbed(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [
                _record(
                    catalog_names=names,
                    rejected=["scope-boundary-\x00mappings", "x" * 5000, "\x00\x01"],
                )
            ]
            * 3,
        )
        reading = _read(home)

        # The NUL-bearing variant still lands on its entry; the all-control
        # name scrubs to empty and is dropped rather than counted as a name.
        assert reading.charged_emissions > 0
        for pair in reading.pairs:
            assert "\x00" not in pair.confused.name
        assert reading.pairs and reading.pairs[0].confused.name == "scope-boundary-mapping"


class TestSerialization:
    def test_the_json_carries_rows_the_gate_can_re_apply_the_rule_from(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        payload = confusion_reading_json(_read(home))
        assert json.loads(json.dumps(payload)) == payload
        row = payload["pairs"][0]
        assert set(row["confused"]) == {
            "name",
            "confused_as",
            "selected_window",
            "judged_exposure",
            "similarity_min",
            "similarity_max",
        }
        # The similarity band is the evidence that stands in for the floor
        # this reading deliberately does not have.
        assert 0.0 < row["confused"]["similarity_min"] <= row["confused"]["similarity_max"] <= 1.0
        assert payload["withheld"] == []
        assert payload["exposure_floor"] == 600
        assert payload["mechanisms"]["counted"] == ["semantic", "wordform"]

    def test_the_findings_section_states_facts_without_recommending(self, tmp_path):
        home = _make_store(tmp_path)
        names = list(CATALOG)
        _write_log(home, "2026-08-25", [_record(catalog_names=names)] * 700)
        _write_log(
            home,
            "2026-09-01",
            [_record(catalog_names=names, rejected=["scope-boundary-mappings"])] * 3,
        )
        text = format_confusion_findings(_read(home), [], ["a.md"], "cand.txt")
        assert text.startswith("## Skill store exit candidates")
        lowered = text.lower()
        # ADR-0099's binding prohibition, as a shape check on the one
        # sentence-generator this stage owns.
        for banned in ("should", "recommend", "suggest", "must be retired", "we advise"):
            assert banned not in lowered
