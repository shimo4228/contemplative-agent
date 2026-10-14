"""``core/portable_path.py`` for scripts that run under the system python3 (RFC-0051).

The weekly chain runs some scripts as ``python3 scripts/<name>.py`` — no
``contemplative_agent`` on the path. ``core/portable_path.py`` is stdlib-only
and has no package-relative import by contract, so it is loaded here by file
path, once, and its two functions are re-exported. Scripts launched with
``uv run`` import ``contemplative_agent.core.portable_path`` directly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SOURCE = (
    Path(__file__).resolve().parent.parent / "src" / "contemplative_agent" / "core"
) / "portable_path.py"


def _load():  # noqa: ANN202 — a module object, typed by its two re-exports below
    spec = importlib.util.spec_from_file_location("_core_portable_path", _SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_module = _load()
portable_path = _module.portable_path
redact_home = _module.redact_home
