#!/usr/bin/env python3
"""Offline A/B replay: does the reworked distill prompt restore the abstain path?

Read-only. Runs BOTH prompt versions over the SAME fixed episode set and
reports aggregate readings only — no episode content and no pattern text is
printed, and nothing is written to knowledge.json or any log.

Baseline prompt = the committed version at the given git ref (default HEAD),
candidate prompt = the working-tree version. Same episodes, same model, same
decoding parameters; only the instruction text differs.

Measured (per arm):
  - judged-abstain rate  (the 0.1% production reading is the thing under test)
  - patterns-per-episode distribution and median (is the yield still pinned
    to the old example's arity of 2?)
  - fault counts, kept apart from the verdict (a flaky backend must not read
    as a quiet week)
  - surviving-pattern length and first-person share, as a coarse guard against
    ADR-0060/0072 flattening — a drop in candidate count is NOT evidence of
    improvement on its own.

Evidence for ADR-0084's Measurement section. Run from the repo root:
    python3 docs/evidence/adr-0084/replay-distill-abstain-20260726.py \
        [--episodes N] [--ref GITREF]

Preserved as it ran on 2026-07-26; only the paths were adjusted when it moved
here from `.notes/`. One consequence worth knowing before re-running it: the
baseline arm is the prompt at `--ref` and the candidate arm is the working-tree
prompt, and `load_prompts` exits when the two are identical — before
`--candidate-file` is applied. The adopted v5 arm leaves `distill_episode.md`
unchanged, so replaying it from a clean checkout needs the candidate prompt
edited into the working tree first. Run outputs go to the gitignored `.notes/`,
never beside this file.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # docs/evidence/adr-0084/ -> repo root
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.adapters.moltbook import config as mb_config  # noqa: E402
from contemplative_agent.core import episode_render, llm  # noqa: E402
from contemplative_agent.core._io import strip_code_fence  # noqa: E402
from contemplative_agent.core.distill import (  # noqa: E402
    _PATTERNS_SCHEMA,
    _is_valid_pattern,
    _parse_patterns,
)
from contemplative_agent.core.memory import EpisodeLog  # noqa: E402

PROMPT_REL = "config/prompts/distill_episode.md"

# Run outputs are derived from the production episode log, so they must never
# land beside this script: it lives in the tracked docs/ tree since being
# promoted here as ADR-0084 evidence. `.notes/` is gitignored (.gitignore:48),
# which is where these writes went when the script itself lived there.
SCRATCH = REPO / ".notes"


def load_prompts(ref: str) -> tuple[str, str]:
    baseline = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{ref}:{PROMPT_REL}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidate = (REPO / PROMPT_REL).read_text(encoding="utf-8")
    if baseline.strip() == candidate.strip():
        sys.exit(f"baseline ({ref}) and working tree are identical — nothing to compare")
    return baseline, candidate


def pick_episodes(n: int) -> list[dict]:
    """Deterministic, evenly-spread sample of recent distillable episodes."""
    # Same log dir the CLI passes in (the EpisodeLog default is not the
    # production home), and the same richness filter distill itself applies.
    log = EpisodeLog(log_dir=mb_config.MOLTBOOK_DATA_DIR / "logs")
    records = [r for r in log.read_range(days=7) if r.get("type") != "insight"]
    rich = [r for r in records if episode_render._is_rich_episode(r)]
    rich.sort(key=lambda r: r.get("ts", ""))
    if len(rich) <= n:
        return rich
    step = len(rich) / n
    return [rich[int(i * step)] for i in range(n)]


_GATE_SCHEMA = {
    "type": "object",
    "properties": {"durable": {"type": "boolean"}, "moment": {"type": "string"}},
    "required": ["durable"],
}


def _gate(template: str, rendered: str) -> tuple[bool, str]:
    """Separate durability judgment. Fails OPEN: any failure distills anyway.

    Splitting the verdict out of the distill call is what makes the causality
    readable — the distill prompt stays byte-identical to the baseline, so a
    register change cannot be an artifact of rewording it. Measured today:
    one line of the merged prompt swung the abstain rate 2.5% <-> 15%, which
    is itself the evidence that a generation frame biases the judgment.
    """
    out = llm.generate(
        template.format(episode=rendered),
        system=llm.get_distill_system_prompt(),
        num_predict=300,
        format=_GATE_SCHEMA,
        caller="replay.distill_gate",
        drop_truncated=True,
    )
    if out is None:
        return True, "gate_fault"
    try:
        data = json.loads(strip_code_fence(out))
    except json.JSONDecodeError:
        return True, "gate_parse"
    if not isinstance(data, dict) or not isinstance(data.get("durable"), bool):
        return True, "gate_shape"
    return data["durable"], str(data.get("moment") or "")


_POSTGATE_SCHEMA = {
    "type": "object",
    "properties": {"keep": {"type": "array", "items": {"type": "integer"}}},
    "required": ["keep"],
}


def _postgate(template: str, rendered: str, patterns: list[str]) -> tuple[list[str], bool]:
    """Judge the PRODUCED patterns, not the episode. Fails OPEN (keeps all).

    v4 put the durability question before distillation and it never said no
    (0/40): naming a worthwhile moment costs nothing when you never have to
    write it. Producing the pattern is the evidence requirement — so the
    verdict belongs after production, with the artifact in hand. Per-pattern,
    so a two-pattern episode where only one is real keeps one.
    """
    numbered = "\n\n".join(f"{i}. {p}" for i, p in enumerate(patterns, 1))
    out = llm.generate(
        template.format(episode=rendered, patterns=numbered),
        system=llm.get_distill_system_prompt(),
        num_predict=300,
        format=_POSTGATE_SCHEMA,
        caller="replay.distill_postgate",
        drop_truncated=True,
    )
    if out is None:
        return patterns, True
    try:
        data = json.loads(strip_code_fence(out))
    except json.JSONDecodeError:
        return patterns, True
    keep = data.get("keep") if isinstance(data, dict) else None
    if not isinstance(keep, list):
        return patterns, True
    idx = {k for k in keep if isinstance(k, int) and 1 <= k <= len(patterns)}
    return [p for i, p in enumerate(patterns, 1) if i in idx], False


def run_arm(
    label: str,
    template: str,
    episodes: list[dict],
    gate_template: str | None = None,
    postgate_template: str | None = None,
) -> dict:
    yields: list[int] = []
    faults: Counter[str] = Counter()
    abstains = 0
    gate_faults = 0
    lengths: list[int] = []
    surviving: list[str] = []
    first_person = 0
    total_patterns = 0

    for i, record in enumerate(episodes, 1):
        rendered = episode_render.render_episode(
            record.get("type", "unknown"), record.get("data") or {}
        )
        if gate_template is not None:
            durable, why = _gate(gate_template, rendered)
            if why.startswith("gate_"):
                gate_faults += 1
            if not durable:
                abstains += 1
                yields.append(0)
                print(f"  [{label}] {i}/{len(episodes)} n=0 gate=abstain", flush=True)
                continue
        out = llm.generate(
            template.format(episode=rendered),
            system=llm.get_distill_system_prompt(),
            num_predict=3000,
            format=_PATTERNS_SCHEMA,
            caller="replay.distill",
            drop_truncated=True,
        )
        if out is None:
            faults["llm_none"] += 1
            print(f"  [{label}] {i}/{len(episodes)} fault=llm_none", flush=True)
            continue
        raw, mode = _parse_patterns(out)
        if mode == "shape_violation":
            faults["shape_violation"] += 1
            print(f"  [{label}] {i}/{len(episodes)} fault=shape_violation", flush=True)
            continue
        kept = [p for p in raw if _is_valid_pattern(p)]
        if postgate_template is not None and kept:
            before = len(kept)
            kept, failed = _postgate(postgate_template, rendered, kept)
            if failed:
                gate_faults += 1
            if before != len(kept):
                print(f"  [{label}] {i}/{len(episodes)} postgate {before}->{len(kept)}", flush=True)
        if not kept:
            abstains += 1
        yields.append(len(kept))
        total_patterns += len(kept)
        for p in kept:
            lengths.append(len(p))
            surviving.append(p)
            low = p.lower()
            if low.startswith("i ") or " i " in low[:80] or "my " in low[:80]:
                first_person += 1
        print(f"  [{label}] {i}/{len(episodes)} n={len(kept)} parse={mode}", flush=True)

    # The register proxies below are crude; ADR-0072 register conformance is a
    # value-layer judgment. Dump the surviving patterns so the operator can
    # read them directly instead of trusting the proxy. Local-only (SCRATCH is
    # gitignored) and self-authored — no episode content is written here.
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dump = SCRATCH / f"replay-patterns-{label}.txt"
    dump.write_text(
        "\n\n".join(f"[{n:03d}] {p}" for n, p in enumerate(surviving, 1)), encoding="utf-8"
    )
    print(f"  [{label}] wrote {len(surviving)} surviving patterns to {dump.name}", flush=True)

    judged = len(yields)
    return {
        "arm": label,
        "episodes": len(episodes),
        "judged": judged,
        "faults": dict(faults),
        "gate_faults": gate_faults,
        "abstain_rate": (abstains / judged) if judged else 0.0,
        "abstains": abstains,
        "yield_dist": dict(sorted(Counter(yields).items())),
        "yield_median": statistics.median(yields) if yields else 0,
        "yield_mean": (total_patterns / judged) if judged else 0.0,
        "patterns_total": total_patterns,
        "pattern_len_median": statistics.median(lengths) if lengths else 0,
        "first_person_share": (first_person / total_patterns) if total_patterns else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--only", choices=("both", "candidate"), default="both")
    ap.add_argument("--label", default="candidate", help="name for the candidate arm")
    ap.add_argument("--postgate-file", help="judge produced patterns after distilling")
    ap.add_argument("--gate-file", help="run a separate durability gate call before distilling")
    ap.add_argument(
        "--candidate-file",
        help="read the candidate prompt from this path instead of the working tree "
        "(lets an earlier arm be re-measured without clobbering the live prompt)",
    )
    args = ap.parse_args()

    baseline, candidate = load_prompts(args.ref)
    if args.candidate_file:
        candidate = Path(args.candidate_file).read_text(encoding="utf-8")
    # Same deterministic episode set as any earlier run at the same --episodes,
    # so a re-run of the candidate arm alone stays comparable to the stored
    # baseline instead of silently changing the control.
    episodes = pick_episodes(args.episodes)
    print(f"episode set: {len(episodes)} (deterministic spread over the last 7 days)\n", flush=True)

    results = []
    if args.only == "both":
        results.append(run_arm("baseline", baseline, episodes))
    gate = Path(args.gate_file).read_text(encoding="utf-8") if args.gate_file else None
    post = Path(args.postgate_file).read_text(encoding="utf-8") if args.postgate_file else None
    results.append(
        run_arm(args.label, candidate, episodes, gate_template=gate, postgate_template=post)
    )

    print("\n" + json.dumps(results, indent=2, ensure_ascii=False))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out = SCRATCH / f"replay-distill-{args.label}.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
