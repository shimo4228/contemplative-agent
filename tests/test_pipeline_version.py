"""P3-05.17: ``provenance.pipeline_version`` is computed, never a literal."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import tomllib

from contemplative_agent.core import distill
from contemplative_agent.core.prompts import DISTILL_EPISODE_PROMPT

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_pipeline_version_is_package_version_plus_prompt_digest() -> None:
    digest = hashlib.sha256(DISTILL_EPISODE_PROMPT.encode("utf-8")).hexdigest()[:12]
    assert distill.pipeline_version() == f"distill@{_pyproject_version()}+{digest}"


def test_pipeline_version_changes_with_the_prompt(monkeypatch) -> None:
    before = distill.pipeline_version()
    from contemplative_agent.core import prompts

    # distill imports the prompt lazily (prompts resolves names on first access),
    # so the module attribute is the seam.
    monkeypatch.setattr(prompts, "DISTILL_EPISODE_PROMPT", DISTILL_EPISODE_PROMPT + "\nx")
    assert distill.pipeline_version() != before


def test_pipeline_version_falls_back_to_unknown_without_an_install(monkeypatch, caplog) -> None:
    import importlib.metadata as md

    def _missing(name: str) -> str:
        raise md.PackageNotFoundError(name)

    distill._package_version.cache_clear()
    monkeypatch.setattr(md, "version", _missing)
    try:
        with caplog.at_level("WARNING"):
            value = distill.pipeline_version()
            distill.pipeline_version()  # cached: one warning only
        digest = hashlib.sha256(DISTILL_EPISODE_PROMPT.encode("utf-8")).hexdigest()[:12]
        assert value == f"distill@unknown+{digest}"
        assert sum("not installed" in r.message for r in caplog.records) == 1
    finally:
        monkeypatch.undo()
        distill._package_version.cache_clear()


def test_no_literal_pipeline_version_in_src() -> None:
    pattern = re.compile(r"""["']distill@\d""")
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "src").rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def add_learned_pattern(self, pattern, **kw) -> None:
        self.calls.append({"pattern": pattern, **kw})


def test_stored_rows_carry_the_computed_value() -> None:
    rec = _Recorder()
    prov = [distill._PatternProvenance(text="p", source_type="self_reflection", episode_ids=("e",))]
    distill._store_new_patterns(rec, "2026-10-24", [0], [np.zeros(2)], prov)  # type: ignore[arg-type]
    assert rec.calls[0]["provenance"]["pipeline_version"] == distill.pipeline_version()
