"""Regenerate the environment-variable docs from the registry (P1-06.4).

``src/contemplative_agent/core/env.py::ENV_KEYS`` is the source of truth. This
script rewrites the two generated artifacts in place:

* the table between the ``env-table`` markers in ``docs/CONFIGURATION.md``;
* the whole of ``.env.example``.

``tests/test_configuration_doc.py`` asserts both are byte-equal to what the
registry renders, so a registry edit without a re-run is a red test.

Run it with the project environment (it imports the package; it is not a bare
``python3`` script)::

    uv run --no-sync python scripts/render_env_docs.py          # write
    uv run --no-sync python scripts/render_env_docs.py --check  # exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contemplative_agent.core.env import (
    TABLE_BEGIN,
    TABLE_END,
    render_config_table,
    render_env_example,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DOC = ROOT / "docs" / "CONFIGURATION.md"
ENV_EXAMPLE = ROOT / ".env.example"


def render_config_doc(current: str) -> str:
    """*current* with the text between the markers replaced by the table."""
    head, sep, rest = current.partition(TABLE_BEGIN)
    if not sep:
        raise SystemExit(f"{CONFIG_DOC}: marker {TABLE_BEGIN!r} not found")
    _old, sep, tail = rest.partition(TABLE_END)
    if not sep:
        raise SystemExit(f"{CONFIG_DOC}: marker {TABLE_END!r} not found")
    return f"{head}{TABLE_BEGIN}\n{render_config_table()}{TABLE_END}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if either file is stale")
    args = parser.parse_args(argv)

    wanted = {
        CONFIG_DOC: render_config_doc(CONFIG_DOC.read_text(encoding="utf-8")),
        ENV_EXAMPLE: render_env_example(),
    }
    stale = [p for p, text in wanted.items() if p.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    for path in stale:
        path.write_text(wanted[path], encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
