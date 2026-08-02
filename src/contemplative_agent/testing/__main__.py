"""CLI runner: check a backend without writing a test file.

The measured failure this addresses is not "the sibling had no conformance
test" — ``contemplative-agent-cloud`` had one. It is that nobody ran it for
three months. A kit whose value depends on the sibling first writing and
then maintaining test scaffolding inherits exactly that failure mode, so the
kit ships an entry point the explicit human release gate can call directly::

    python -m contemplative_agent.testing --backend my_pkg.backends:MyBackend

Exit status is the verdict: 0 conforming, 1 non-conforming, 2 the target
could not be loaded or constructed (a distinct outcome — "your backend is
wrong" and "I never saw your backend" must not share a code).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from urllib.parse import urlsplit

from .backend_contract import (
    CAPABILITIES,
    DEFAULT_REQUIRE,
    LEVELS,
    check_backend,
)

EXIT_OK = 0
EXIT_NONCONFORMING = 1
EXIT_UNUSABLE_TARGET = 2

_ALLOWED_KWARG_NAMES = frozenset({"base_url", "model"})


class _TargetSpecError(ValueError):
    """The user-provided import target is syntactically unusable."""


def _validate_cli_kwarg(name: str, value: str) -> None:
    """Keep argv constructor values deliberately narrow and credential-free."""
    if name != "base_url":
        return
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path in {"", "/"}
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "base_url must be a credential-free HTTP(S) origin; use a local factory "
            "for URLs with paths or any other components"
        )


def _load_target(target: str) -> object:
    """Resolve ``package.module:attribute`` to the attribute itself."""
    if ":" not in target:
        raise _TargetSpecError(
            f"expected 'package.module:attribute', got {target!r} "
            "(the colon separates the module from the name inside it)"
        )
    module_path, _, attribute = target.partition(":")
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attribute)
    except AttributeError as exc:
        raise _TargetSpecError(f"{module_path!r} has no attribute {attribute!r}") from exc


def _parse_kwargs(pairs: Sequence[str]) -> dict[str, str]:
    """Parse ``name=value`` constructor arguments.

    Values stay strings. Anything needing real types (a client object, a
    numeric window) is beyond what a command line should be constructing —
    write a factory function and point ``--backend`` at that instead.
    """
    kwargs: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise ValueError("expected name=value")
        if name not in _ALLOWED_KWARG_NAMES:
            raise ValueError(
                f"constructor kwarg {name!r} is not accepted; only base_url and model "
                "may be passed in argv, so use a local factory for all other values"
            )
        _validate_cli_kwarg(name, value)
        kwargs[name] = value
    return kwargs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m contemplative_agent.testing",
        description="Check an LLMBackend implementation against the contract.",
    )
    parser.add_argument(
        "--backend",
        required=True,
        metavar="pkg.mod:Name",
        help=(
            "Import path to a backend class, or to a zero-argument factory "
            "returning an instance. An already-constructed instance works too."
        ),
    )
    parser.add_argument(
        "--kwarg",
        action="append",
        default=[],
        metavar="name=value",
        help=(
            "Allowlisted constructor argument: base_url or model (repeatable). Values are "
            "passed as strings; use a local factory for every other constructor value."
        ),
    )
    parser.add_argument(
        "--require",
        default=DEFAULT_REQUIRE,
        choices=LEVELS,
        help=(
            "Coverage level to claim. Levels above 'static' need a probe, "
            "which the CLI cannot supply — use a test file for those."
        ),
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        choices=CAPABILITIES,
        help="Capability the backend claims to have (repeatable).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="CHECK_ID",
        help="Check id to skip (repeatable).",
    )
    args = parser.parse_args(argv)

    try:
        kwargs = _parse_kwargs(args.kwarg)
    except ValueError as exc:
        print(f"cannot parse --kwarg: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE_TARGET

    try:
        target = _load_target(args.backend)
    except _TargetSpecError as exc:
        print(f"cannot load {args.backend!r}: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE_TARGET
    except Exception as exc:
        print(
            f"cannot load {args.backend!r}: {type(exc).__name__} (exception detail suppressed)",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE_TARGET

    backend = target
    if callable(target):
        try:
            backend = target(**kwargs)
        except Exception as exc:
            print(
                f"cannot construct {args.backend!r}: {type(exc).__name__} "
                "(exception detail suppressed)\n"
                "Pass constructor arguments with --kwarg name=value, or point "
                "--backend at a zero-argument factory.",
                file=sys.stderr,
            )
            return EXIT_UNUSABLE_TARGET
    elif kwargs:
        print(f"--kwarg given but {args.backend!r} is not callable", file=sys.stderr)
        return EXIT_UNUSABLE_TARGET

    report = check_backend(
        backend,
        capabilities=args.capability,
        require=args.require,
        exclude=args.exclude,
    )
    print(repr(report))
    return EXIT_OK if report.ok else EXIT_NONCONFORMING


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess
    raise SystemExit(main())
