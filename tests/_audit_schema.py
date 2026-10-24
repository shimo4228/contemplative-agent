"""A stdlib reader for the subset of JSON Schema ``schemas/audit.schema.json`` uses.

The schema is deliberately plain (type / enum / required / properties /
additionalProperties / pattern), so the check that real writer output matches
it needs no ``jsonschema`` dependency. If the schema ever grows past this
subset the validator must refuse it loudly rather than pass what it cannot
read - see ``_SUPPORTED_KEYWORDS``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "audit.schema.json"

_TYPES: dict[str, Any] = {
    "string": str,
    "object": dict,
    "array": list,
    "null": type(None),
    "integer": int,
    "boolean": bool,
}

# Annotation keywords are ignored by design; anything else must be handled.
_SUPPORTED_KEYWORDS = {
    "type",
    "enum",
    "required",
    "properties",
    "additionalProperties",
    "pattern",
    "items",
}
_ANNOTATIONS = {"$schema", "$id", "title", "description"}


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _type_ok(value: Any, wanted: str | list[str]) -> bool:
    names = wanted if isinstance(wanted, list) else [wanted]
    return any(
        isinstance(value, _TYPES[n]) and not (n == "integer" and isinstance(value, bool))
        for n in names
    )


def _check_object(
    value: dict[str, Any], schema: dict[str, Any], where: str, errors: list[str]
) -> None:
    for name in schema.get("required", []):
        if name not in value:
            errors.append(f"{where}: missing required key {name!r}")
    props = schema.get("properties", {})
    for name, sub in value.items():
        if name in props:
            _check(sub, props[name], f"{where}.{name}", errors)
        elif schema.get("additionalProperties") is False:
            errors.append(f"{where}: unexpected key {name!r}")


def _check(value: Any, schema: dict[str, Any], where: str, errors: list[str]) -> None:
    for key in schema:
        if key in _ANNOTATIONS or key.startswith("x-") or key in _SUPPORTED_KEYWORDS:
            continue
        raise NotImplementedError(
            f"schema keyword {key!r} at {where} is outside the checked subset"
        )
    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append(f"{where}: {value!r} is not of type {schema['type']}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        errors.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, dict):
        _check_object(value, schema, where, errors)
    if isinstance(value, list) and "items" in schema:
        for i, sub in enumerate(value):
            _check(sub, schema["items"], f"{where}[{i}]", errors)


def validate_row(row: dict[str, Any], *, current: bool = True) -> list[str]:
    """Errors for one audit row; empty when it conforms.

    ``current=True`` additionally requires every key in ``x-writer-keys`` -
    what rows written today must carry. Legacy rows pass ``current=False``.
    """
    schema = load_schema()
    errors: list[str] = []
    _check(row, schema, "row", errors)
    if current:
        errors.extend(
            f"row: missing writer key {key!r}" for key in schema["x-writer-keys"] if key not in row
        )
    return errors
