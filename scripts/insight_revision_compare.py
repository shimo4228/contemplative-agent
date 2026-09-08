#!/usr/bin/env python3
"""Run the one-time, read-only RFC-0027 extraction comparison.

This harness is intentionally separate from ``core.insight``. It reads one
explicit JSON case file, uses packaged prompt assets (never a home override),
calls the configured LLM, and writes one explicit JSON result. It never opens
the runtime store, skills directory, staging ledger, or a production marker.
The result is an observation artifact; it contains no adoption or quality
verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from contemplative_agent.core import llm
from contemplative_agent.core.domain import PromptTemplates, load_prompt_templates

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "config" / "prompts"
INPUT_SCHEMA_VERSION = 1
OUTPUT_SCHEMA_VERSION = 1
REASON_KINDS = frozenset({"reconfirm", "insufficient", "revise", "new"})

REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "target_skill", "change_reason", "evidence_ids"],
    "properties": {
        "kind": {"type": "string", "enum": sorted(REASON_KINDS)},
        "target_skill": {"type": ["string", "null"]},
        "change_reason": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
}


def _fail(message: str) -> ValueError:
    return ValueError(f"invalid RFC-0027 cases: {message}")


def _validate_patterns(case_id: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise _fail(f"case {case_id} patterns must be a non-empty array")
    pattern_ids: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, pattern in enumerate(value):
        if not isinstance(pattern, dict) or set(pattern) != {"id", "text"}:
            raise _fail(f"case {case_id} pattern {index} must have id and text")
        pattern_id = pattern.get("id")
        text = pattern.get("text")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            raise _fail(f"case {case_id} has an empty pattern id")
        if pattern_id in pattern_ids:
            raise _fail(f"case {case_id} has duplicate pattern id: {pattern_id}")
        if not isinstance(text, str) or not text.strip():
            raise _fail(f"case {case_id} pattern {pattern_id} has empty text")
        pattern_ids.add(pattern_id)
        normalized.append({"id": pattern_id, "text": text})
    return normalized


def _validate_skills(case_id: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise _fail(f"case {case_id} existing_skills must be an array")
    skill_names: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, skill in enumerate(value):
        if not isinstance(skill, dict) or set(skill) != {"name", "text"}:
            raise _fail(f"case {case_id} skill {index} must have name and text")
        name = skill.get("name")
        text = skill.get("text")
        if not isinstance(name, str) or not name.strip():
            raise _fail(f"case {case_id} has an empty skill name")
        if name in skill_names:
            raise _fail(f"case {case_id} has duplicate skill name: {name}")
        if not isinstance(text, str) or not text.strip():
            raise _fail(f"case {case_id} skill {name} has empty text")
        skill_names.add(name)
        normalized.append({"name": name, "text": text})
    return normalized


def _validate_case(raw_case: object, index: int) -> dict[str, Any]:
    if not isinstance(raw_case, dict):
        raise _fail(f"case {index} must be an object")
    if set(raw_case) != {"case_id", "patterns", "existing_skills"}:
        raise _fail(f"case {index} keys must be case_id, patterns, existing_skills")
    case_id = raw_case.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise _fail(f"case {index} has an empty case_id")
    return {
        "case_id": case_id,
        "patterns": _validate_patterns(case_id, raw_case.get("patterns")),
        "existing_skills": _validate_skills(case_id, raw_case.get("existing_skills")),
    }


def _validate_cases(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise _fail("top level must be an object")
    if value.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise _fail(f"schema_version must be {INPUT_SCHEMA_VERSION}")
    if set(value) != {"schema_version", "cases"}:
        raise _fail("top level keys must be schema_version and cases")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise _fail("cases must be a non-empty array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        normalized_case = _validate_case(raw_case, index)
        case_id = normalized_case["case_id"]
        if case_id in seen:
            raise _fail(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        normalized.append(normalized_case)
    return normalized


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load and validate the caller-supplied immutable case snapshot."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {path}: {exc}") from exc
    return _validate_cases(raw)


def _repo_prompts() -> PromptTemplates:
    """Load only packaged prompts, bypassing ``MOLTBOOK_HOME`` overrides."""
    return load_prompt_templates(PROMPTS_DIR)


def _observations(case: dict[str, Any]) -> str:
    return "\n".join(f"- [{p['id']}] {p['text']}" for p in case["patterns"])


def _existing_skills(case: dict[str, Any]) -> str:
    skills = case["existing_skills"]
    if not skills:
        return "(none supplied)"
    return "\n\n".join(f"### {s['name']}\n{s['text']}" for s in skills)


def _call_current(case: dict[str, Any], prompts: PromptTemplates) -> dict[str, Any]:
    prompt = prompts.insight_extraction.format(
        subcategory=case["case_id"],
        patterns="\n".join(f"- {p['text']}" for p in case["patterns"]),
    )
    output = llm.generate_full(
        prompt,
        system=prompts.system,
        num_predict=3000,
        caller="rfc0027.current.extract",
        think=True,
        drop_truncated=True,
    )
    return _generation_record(output)


def _generation_record(output: llm.GenerationOutput | None) -> dict[str, Any]:
    if output is None or output.text is None:
        return {"status": "llm_none", "text": None, "thinking": None}
    return {"status": "generated", "text": output.text, "thinking": output.thinking}


def _parse_reason(raw: str | None, case: dict[str, Any]) -> dict[str, Any]:
    if raw is None:
        return {"status": "llm_none", "raw_text": None}
    base = {"status": "parse_error", "raw_text": raw}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return base
    if not isinstance(parsed, dict):
        return {**base, "status": "invalid"}
    expected = {"kind", "target_skill", "change_reason", "evidence_ids"}
    if set(parsed) != expected:
        return {**base, "status": "invalid"}
    kind = parsed["kind"]
    target = parsed["target_skill"]
    reason = parsed["change_reason"]
    evidence_ids = parsed["evidence_ids"]
    pattern_ids = {p["id"] for p in case["patterns"]}
    skill_names = {s["name"] for s in case["existing_skills"]}
    valid = (
        isinstance(kind, str)
        and kind in REASON_KINDS
        and (target is None or isinstance(target, str))
        and isinstance(reason, str)
        and bool(reason.strip())
        and isinstance(evidence_ids, list)
        and bool(evidence_ids)
        and all(
            isinstance(evidence_id, str) and evidence_id in pattern_ids
            for evidence_id in evidence_ids
        )
        and len(set(evidence_ids)) == len(evidence_ids)
        and ((kind == "revise" and target in skill_names) or (kind != "revise" and target is None))
    )
    if not valid:
        return {**base, "status": "invalid"}
    return {
        "status": "parsed",
        "raw_text": raw,
        "kind": kind,
        "target_skill": target,
        "change_reason": reason,
        "evidence_ids": evidence_ids,
    }


def _call_proposed(case: dict[str, Any], prompts: PromptTemplates) -> dict[str, Any]:
    reason_prompt = prompts.insight_revision_reason.format(
        observations=_observations(case),
        existing_skills=_existing_skills(case),
    )
    reason_output = llm.generate_full(
        reason_prompt,
        system=prompts.system,
        num_predict=600,
        format=REASON_SCHEMA,
        caller="rfc0027.proposed.reason",
        think=False,
        drop_truncated=True,
    )
    raw_reason = None if reason_output is None else reason_output.text
    reason = _parse_reason(raw_reason, case)
    row: dict[str, Any] = {"reason": reason, "candidate": None}
    if reason["status"] != "parsed" or reason["kind"] not in {"revise", "new"}:
        return row

    candidate_prompt = prompts.insight_revision_generation.format(
        kind=reason["kind"],
        target_skill=reason["target_skill"] or "(none)",
        change_reason=reason["change_reason"],
        observations=_observations(case),
        existing_skills=_existing_skills(case),
    )
    candidate = llm.generate_full(
        candidate_prompt,
        system=prompts.system,
        num_predict=3000,
        caller="rfc0027.proposed.generate",
        think=True,
        drop_truncated=True,
    )
    row["candidate"] = _generation_record(candidate)
    return row


def compare_cases(
    cases: list[dict[str, Any]],
    *,
    arm: Literal["current", "proposed", "both"] = "both",
) -> dict[str, Any]:
    """Run selected arms over already validated cases.

    No result is interpreted here. In particular, the harness does not score,
    pick a winner, write staging, or call adoption code.
    """
    normalized = _validate_cases({"schema_version": INPUT_SCHEMA_VERSION, "cases": cases})
    prompts = _repo_prompts()
    arms: dict[str, list[dict[str, Any]]] = {}
    if arm in {"current", "both"}:
        arms["current"] = [
            {"case_id": case["case_id"], "result": _call_current(case, prompts)}
            for case in normalized
        ]
    if arm in {"proposed", "both"}:
        arms["proposed"] = [
            {"case_id": case["case_id"], **_call_proposed(case, prompts)} for case in normalized
        ]
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "experiment": "RFC-0027",
        "interpretation": "observation_only",
        "arms": arms,
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prompt_hashes(prompts: PromptTemplates, arm: str) -> dict[str, str]:
    names = ["system", "insight_extraction"]
    if arm in {"proposed", "both"}:
        names.extend(["insight_revision_reason", "insight_revision_generation"])
    return {name: _sha256(getattr(prompts, name).encode("utf-8")) for name in names}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="explicit RFC-0027 case JSON")
    parser.add_argument("--out", type=Path, required=True, help="explicit JSON output path")
    parser.add_argument("--arm", choices=("current", "proposed", "both"), default="both")
    args = parser.parse_args(argv)

    raw = args.cases.read_bytes()
    cases = load_cases(args.cases)
    prompts = _repo_prompts()
    result = compare_cases(cases, arm=args.arm)
    result["input_sha256"] = _sha256(raw)
    result["prompt_sha256"] = _prompt_hashes(prompts, args.arm)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
