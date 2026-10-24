"""Which prompt templates count as eval inputs (ADR-0089 amendment).

``prompt_templates_sha256`` globbed ``config/prompts/*.md`` wholesale, so
editing a document the agent never reads — ``weekly-analysis.md``, whose
only consumer is ``scripts/weekly-analysis.sh:15`` — reported the approved
baseline as stale. The staleness check never blocks, so the cost was not a
broken gate: it was training the reader to dismiss the warning. That exact
failure mode (a prose trigger nobody acted on) is what the 2026-08-08
amendment was written to fix, so growing another instance of it in the
same PR series was not acceptable.

The set of excluded stems is not restated here. ``PromptTemplates`` already
names every template the registry loads, and
``tests/test_packaged_assets.SCRIPT_READ_PROMPTS`` already names every
template only a shell script reads — with an orphan guard forcing each new
prompt file into one bucket or the other at PR time. Deriving the hash
input from the registry means the exclusion list cannot drift, because
there is no second list.
"""

from __future__ import annotations

import dataclasses

from contemplative_agent.core.domain import PromptTemplates
from evals.run_eval import hashed_prompt_paths
from tests.test_packaged_assets import SCRIPT_READ_PROMPTS


def _hashed_stems() -> set[str]:
    return {p.stem for p in hashed_prompt_paths()}


class TestHashedPromptSelection:
    def test_hashes_exactly_the_comment_path_templates(self):
        """P1-07.14: not every registry field — only what the comment eval reads."""
        from evals.run_eval import COMMENT_PATH_TEMPLATES

        assert _hashed_stems() == set(COMMENT_PATH_TEMPLATES)
        fields = {f.name for f in dataclasses.fields(PromptTemplates)}
        assert _hashed_stems() <= fields | {"skill_selection"}
        assert "insight_novelty" not in _hashed_stems()
        assert "relevance_score4" not in _hashed_stems()

    def test_script_only_prompts_are_excluded(self):
        """The bug, stated directly."""
        overlap = _hashed_stems() & SCRIPT_READ_PROMPTS
        assert not overlap, (
            f"script-only prompts still counted as eval inputs: {sorted(overlap)} — "
            "editing one would report the baseline stale for a document the "
            "agent's generation path never reads"
        )

    def test_paths_are_sorted(self):
        """Digest order is part of the digest."""
        paths = hashed_prompt_paths()
        assert paths == sorted(paths)

    def test_domain_json_is_not_a_prompt_path(self):
        from evals.run_eval import REPO_ROOT

        assert (REPO_ROOT / "config" / "domain.json").is_file()
        assert not any(p.name == "domain.json" for p in hashed_prompt_paths())


class TestDigestSensitivity:
    """The selection tests above pin *which files* are chosen; they would
    all still pass if ``prompt_templates_sha256`` ignored the selection and
    went back to hashing the raw glob. These pin the digest's response,
    which is the behaviour the defect was actually about (cross-model
    review, 2026-08-08).

    Run against a synthetic repo root rather than the real tree: the
    function resolves ``REPO_ROOT`` itself, and a test that edits
    ``config/prompts`` in place would be mutating the thing under
    measurement.
    """

    @staticmethod
    def _names() -> tuple[str, str]:
        """One included and one excluded stem (the excluded one is a registry
        template that is not on the comment path)."""
        from evals.run_eval import COMMENT_PATH_TEMPLATES

        fields = sorted(f.name for f in dataclasses.fields(PromptTemplates))
        return sorted(COMMENT_PATH_TEMPLATES)[0], next(
            f for f in fields if f not in COMMENT_PATH_TEMPLATES
        )

    def _fake_root(self, tmp_path, *, included="A", excluded="B", domain='{"d": 1}'):
        included_stem, excluded_stem = self._names()
        prompts = tmp_path / "config" / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        (prompts / f"{included_stem}.md").write_text(included, encoding="utf-8")
        (prompts / f"{excluded_stem}.md").write_text(excluded, encoding="utf-8")
        (tmp_path / "config" / "domain.json").write_text(domain, encoding="utf-8")
        return tmp_path

    def _digest(self, monkeypatch, root) -> str:
        from evals import run_eval

        monkeypatch.setattr(run_eval, "REPO_ROOT", root)
        return run_eval.prompt_templates_sha256()

    def test_editing_a_generation_path_template_changes_the_digest(self, tmp_path, monkeypatch):
        before = self._digest(monkeypatch, self._fake_root(tmp_path / "a"))
        after = self._digest(monkeypatch, self._fake_root(tmp_path / "b", included="EDITED"))
        assert before != after

    def test_editing_a_script_only_template_does_not(self, tmp_path, monkeypatch):
        """The defect, stated as a behaviour rather than as a file list."""
        before = self._digest(monkeypatch, self._fake_root(tmp_path / "a"))
        after = self._digest(monkeypatch, self._fake_root(tmp_path / "b", excluded="EDITED"))
        assert before == after

    def test_editing_domain_json_does_not_change_the_digest(self, tmp_path, monkeypatch):
        """P1-07.14: a threshold edit needs no ack; it is recorded as domain_sha256."""
        from evals import run_eval

        before = self._digest(monkeypatch, self._fake_root(tmp_path / "a"))
        before_domain = run_eval.domain_sha256()
        after = self._digest(monkeypatch, self._fake_root(tmp_path / "b", domain='{"d": 2}'))
        assert before == after
        assert run_eval.domain_sha256() != before_domain

    def test_a_template_the_registry_does_not_know_is_ignored(self, tmp_path, monkeypatch):
        """Guards the same property from the other side: an unrecognised
        stem must not silently join the hash input."""
        before = self._digest(monkeypatch, self._fake_root(tmp_path / "a"))
        root = self._fake_root(tmp_path / "b")
        (root / "config" / "prompts" / "not-a-registry-field.md").write_text("X", encoding="utf-8")
        assert before == self._digest(monkeypatch, root)
