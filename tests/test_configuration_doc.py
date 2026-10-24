"""The env-key registry is the single source for env reads and env docs (P1-06.4).

Three directions are closed here:

* the generated artifacts (the table in ``docs/CONFIGURATION.md`` and the whole
  of ``.env.example``) are byte-equal to what ``core/env.py`` renders;
* ``src/`` reads the environment only through the registry, and every key it
  reads that way is registered (and vice versa: a registered key names the file
  that reads it);
* the script-side knobs (``${NAME:-default}`` in ``scripts/*.sh``) are all
  registered, and each registered script key appears in the file it names.

Thresholds are not here — their table is P1-04.8's.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

from contemplative_agent.core import env as env_registry
from contemplative_agent.core.env import ENV_KEYS, TABLE_BEGIN, TABLE_END, env_get, env_is_set

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "contemplative_agent"
ENV_MODULE = SRC / "core" / "env.py"
CONFIG_DOC = ROOT / "docs" / "CONFIGURATION.md"
ENV_EXAMPLE = ROOT / ".env.example"

# Shell locals that happen to use the ``${NAME:-x}`` form; they are not env keys.
# Shell-internal names (set and read inside one script) and the system TMPDIR.
_SHELL_LOCALS = {"REASONS", "CENSUS_REASON", "RSYNC_VERSION_LINE", "FREEZE_REASON", "TMPDIR"}
# Loop variables passed to env_is_set in src (the retired-name warning loop).
_DYNAMIC_ALLOWED = {("cli/runtime.py", "retired")}

sys.path.insert(0, str(ROOT / "scripts"))
import render_env_docs  # noqa: E402  # pyright: ignore[reportMissingImports]


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if p != ENV_MODULE)


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            out[node.targets[0].id] = node.value.value
    return out


def _registry_reads() -> dict[str, set[str]]:
    """repo-relative src path -> registry keys read through env_get / env_is_set."""
    reads: dict[str, set[str]] = {}
    for path in _src_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_string_constants(tree)
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"env_get", "env_is_set"}
            ):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                name = arg.value
            elif isinstance(arg, ast.Name) and arg.id in constants:
                name = constants[arg.id]
            elif isinstance(arg, ast.Name) and (rel, arg.id) in _DYNAMIC_ALLOWED:
                continue
            else:
                pytest.fail(f"{rel}:{node.lineno}: env key is not a literal or module constant")
            reads.setdefault(rel, set()).add(name)
    return reads


class TestGeneratedArtifactsMatchTheRegistry:
    def test_config_table_is_byte_equal(self) -> None:
        doc = CONFIG_DOC.read_text(encoding="utf-8")
        assert TABLE_BEGIN in doc and TABLE_END in doc
        between = doc.split(TABLE_BEGIN + "\n", 1)[1].split(TABLE_END, 1)[0]
        assert between == env_registry.render_config_table(), (
            "docs/CONFIGURATION.md env table is stale: "
            "run `uv run --no-sync python scripts/render_env_docs.py`"
        )

    def test_env_example_is_byte_equal(self) -> None:
        assert ENV_EXAMPLE.read_text(encoding="utf-8") == env_registry.render_env_example(), (
            ".env.example is stale: run `uv run --no-sync python scripts/render_env_docs.py`"
        )

    def test_the_renderer_script_agrees(self) -> None:
        assert render_env_docs.main(["--check"]) == 0

    def test_a_link_to_env_example_precedes_the_table(self) -> None:
        doc = CONFIG_DOC.read_text(encoding="utf-8")
        before = doc.split(TABLE_BEGIN, 1)[0]
        assert "(../.env.example)" in before.split("## Environment Variables", 1)[1]

    def test_every_non_retired_key_appears_in_env_example(self) -> None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        for key in ENV_KEYS:
            if key.retired:
                assert key.name not in text
            else:
                assert re.search(rf"^# {key.name}=", text, re.M), key.name


class TestRegistryShape:
    def test_names_are_unique(self) -> None:
        names = [n for key in ENV_KEYS for n in key.names]
        assert len(names) == len(set(names))

    def test_table_cells_cannot_break_the_row(self) -> None:
        for key in ENV_KEYS:
            for cell in (key.default, key.description, key.owner, key.empty_means):
                assert "|" not in cell and "\n" not in cell, key.name

    def test_owner_adr_exists(self) -> None:
        for key in ENV_KEYS:
            if key.owner == "(none)":
                continue
            match = re.fullmatch(r"ADR-(\d{4})", key.owner)
            assert match, f"{key.name}: owner {key.owner!r}"
            assert list((ROOT / "docs" / "adr").glob(f"{match.group(1)}-*.md")), key.name

    def test_unregistered_names_are_refused(self) -> None:
        with pytest.raises(KeyError, match="not a registered environment key"):
            env_get("NOT_A_REGISTERED_KEY")
        with pytest.raises(KeyError):
            env_is_set("NOT_A_REGISTERED_KEY")

    def test_get_and_is_set_follow_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_TRUSTED_HOSTS", raising=False)
        assert env_get("OLLAMA_TRUSTED_HOSTS") is None
        assert env_get("OLLAMA_TRUSTED_HOSTS", "x") == "x"
        assert not env_is_set("OLLAMA_TRUSTED_HOSTS")
        monkeypatch.setenv("OLLAMA_TRUSTED_HOSTS", "")
        assert env_get("OLLAMA_TRUSTED_HOSTS", "x") == ""
        assert env_is_set("OLLAMA_TRUSTED_HOSTS")


class TestSrcReadsTheEnvironmentOnlyThroughTheRegistry:
    def test_no_os_environ_or_getenv_outside_the_registry(self) -> None:
        offenders: list[str] = []
        for path in _src_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(SRC).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                    if isinstance(node.value, ast.Name) and node.value.id == "os":
                        offenders.append(f"{rel}:{node.lineno}")
                if isinstance(node, ast.ImportFrom) and node.module == "os":
                    if any(a.name in {"environ", "getenv"} for a in node.names):
                        offenders.append(f"{rel}:{node.lineno}")
        assert not offenders, f"read the environment through core/env.py: {offenders}"

    def test_every_key_read_in_src_is_registered(self) -> None:
        registered = {n for key in ENV_KEYS for n in key.names}
        for rel, names in _registry_reads().items():
            assert names <= registered, f"{rel}: {sorted(names - registered)}"

    def test_registered_python_readers_are_real(self) -> None:
        reads = _registry_reads()
        for key in ENV_KEYS:
            if key.retired:
                continue
            py_readers = [p for p in key.read_by if p.startswith("src/")]
            for path in py_readers:
                rel = path.removeprefix("src/contemplative_agent/")
                assert key.name in reads.get(rel, set()), f"{key.name} is not read in {path}"
            actual = {rel for rel, names in reads.items() if key.name in names}
            declared = {p.removeprefix("src/contemplative_agent/") for p in py_readers}
            assert actual <= declared, (
                f"{key.name} is read in undeclared {sorted(actual - declared)}"
            )


class TestScriptKnobsAreRegistered:
    @staticmethod
    def _script_files() -> list[Path]:
        return sorted((ROOT / "scripts").glob("*.sh")) + [ROOT / ".claude" / "verify.sh"]

    def test_every_default_form_expansion_names_a_registered_key(self) -> None:
        registered = {n for key in ENV_KEYS for n in key.names}
        unknown: dict[str, set[str]] = {}
        for path in self._script_files():
            for name in re.findall(r"\$\{([A-Z][A-Z0-9_]*):?-", path.read_text(encoding="utf-8")):
                if name not in registered and name not in _SHELL_LOCALS:
                    unknown.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
        assert not unknown, f"script env knobs missing from core/env.py: {unknown}"

    def test_registered_script_readers_contain_the_name(self) -> None:
        for key in ENV_KEYS:
            for rel in key.read_by:
                if rel.startswith("src/"):
                    continue
                text = (ROOT / rel).read_text(encoding="utf-8")
                assert re.search(rf"\$\{{{key.name}:?-", text), f"{key.name} not read in {rel}"
