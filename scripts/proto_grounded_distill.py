#!/usr/bin/env python3
"""Measurement prototype for the clustering-based grounded distill redesign.

READ-ONLY / dry-run. Reads the real production episode log + knowledge store,
runs the *proposed* reinforce / cluster / singleton routing, and prints a
metrics table. Writes NOTHING (no knowledge.save(), no valid_until mutation,
no noise log). Throwaway — delete once measurements inform the forward-only
rewrite of core/distill.py.

See .notes/handoff-2026-06-22-distill-clustering-redesign.md (the locked
design) and the approved plan. This script exists to answer the open
tuning questions (cluster / reinforce thresholds, excerpt caps, model
latency, branch ratios, one-off capture) BEFORE the core is touched.

Cross-modal handling (key open question): each episode is embedded so that
reinforce-matching and clustering stay *in-distribution* with the short
stored pattern text that SIM_* / cluster thresholds were calibrated on,
while the LLM prompts are grounded on the *rich* multi-field render:

  - SHORT embedding  = old summarize_record() one-liner  -> reinforce + cluster
  - RICH render      = render_episode() multi-field block -> LLM grounding only

The script reports BOTH cosine distributions (short vs rich) for the
reinforce comparison so the embedding-modality decision is data-driven.

Run standalone AFTER any live agent releases the run lock — this script does
NOT acquire RUN_LOCK_PATH, so do not run it during an active session.

Usage:
    python scripts/proto_grounded_distill.py [--days N] [--llm-samples K] [--no-llm]
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Dict, List

import numpy as np

# This is a scripts/ entry point (like cli.py) so it may import from both
# core/ and adapters/ — the one-directional import rule binds library code,
# not the composition root.
from contemplative_agent.adapters.moltbook.config import (
    KNOWLEDGE_PATH,
    MOLTBOOK_DATA_DIR,
)
from contemplative_agent.core.clustering import cluster_patterns
from contemplative_agent.core.distill import (
    _best_existing_sim,
    _live_embedded,
    summarize_record,
)
from contemplative_agent.core.embeddings import cosine, embed_texts
from contemplative_agent.core.llm import generate, get_distill_system_prompt
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore
from contemplative_agent.core.thresholds import (
    CLUSTER_THRESHOLD_INSIGHT,
    SIM_UPDATE,
)

# ── Provisional tuning knobs (the whole point of this prototype is to
#    measure whether these are right; do NOT lift them verbatim) ──────────
REINFORCE_THRESHOLD = SIM_UPDATE          # start = pattern-vs-pattern UPDATE gate
CLUSTER_THRESHOLD = CLUSTER_THRESHOLD_INSIGHT  # start = insight's pattern threshold
MIN_EPISODES_PER_CLUSTER = 2              # 2 rich episodes may deserve a cluster prompt
MAX_CLUSTER_SIZE = 10                     # = MAX_BATCH prompt-size budget

# Provisional excerpt caps (handoff guesses — the prototype MEASURES the real
# percentiles below so these can be recalibrated before the core rewrite).
EXCERPT_CAPS = {"original_post": 1500, "their_comment": 1200, "content": 2000}
CUT_MARKER = "…[cut]"

# Input scope (2026-06-23 decision, prototype measurement §1-4): learn only
# from substantive engagement episodes with real world-grounding. Drop the
# redundant short 'interaction' / 'post' records (each comment/reply/post
# writes both a rich activity record AND a short paired record) and the
# template sparse actions (upvote / follow / unfollow) that polluted clusters.
RICH_ACTIONS = {"comment", "reply", "post"}


def is_rich_episode(record_type: str, data: dict) -> bool:
    """True iff this episode carries substantive world-grounding to learn from."""
    return record_type == "activity" and data.get("action") in RICH_ACTIONS

_SENT_SEPS = ("。", "！", "？", ".\n", ". ", "! ", "? ")


def truncate_boundary(text: str, max_len: int, marker: str = CUT_MARKER) -> str:
    """Truncate at the nearest sentence -> word -> char boundary, add marker.

    Provisional version of the _truncate_boundary helper that will land in
    _io.py during the forward-only rewrite. Avoids the mid-character /
    mid-word cut that the agent has historically misread as an intentional
    pause (the F1.1 thread that started this whole redesign).
    """
    if len(text) <= max_len:
        return text
    budget = max_len - len(marker)
    if budget <= 0:
        return marker
    window = text[:budget]
    floor = int(budget * 0.5)  # only honour a boundary in the back half
    best = -1
    for sep in _SENT_SEPS:
        idx = window.rfind(sep)
        if idx > best:
            best = idx + len(sep)
    if best >= floor:
        return text[:best].rstrip() + marker
    idx = window.rfind(" ")
    if idx >= floor:
        return window[:idx].rstrip() + marker
    return window.rstrip() + marker


def render_episode(record_type: str, data: dict) -> str:
    """Rich, world-grounded render of one episode (provisional).

    activity records carry the world (original_post / their_comment) and the
    agent's own output (content) plus the pre-action internal_note. Those are
    the fields the current distill throws away. Sparse activity actions
    (upvote / follow / unfollow) carry only internal_note, so we degrade to
    the short summary. Non-activity records (interaction / post / dialogue)
    have no rich world fields, so they reuse summarize_record unchanged.
    """
    if record_type != "activity":
        return summarize_record(record_type, data)

    parts: List[str] = []
    op = data.get("original_post")
    if op:
        parts.append("Post I engaged with:\n" + truncate_boundary(op, EXCERPT_CAPS["original_post"]))
    tc = data.get("their_comment")
    if tc:
        parts.append("Their comment:\n" + truncate_boundary(tc, EXCERPT_CAPS["their_comment"]))
    title = data.get("title")
    if title:
        parts.append("Title I gave it:\n" + title)
    out = data.get("content")
    action = data.get("action", "?")
    if out:
        parts.append(f"My {action}:\n" + truncate_boundary(out, EXCERPT_CAPS["content"]))
    note = data.get("internal_note")
    if note:
        parts.append("What I noticed:\n" + note)  # full, no cap (in-register)

    if not parts:
        # sparse action with nothing but maybe a target — fall back
        return summarize_record(record_type, data)

    target = data.get("target_agent", "")
    header = f"[{action} {target}]".strip()
    return header + "\n" + "\n\n".join(parts)


# ── Provisional LLM prompts (final versions get the prompt-model-match
#    treatment in config/prompts/ during the rewrite — these are only to
#    eyeball cluster/singleton output quality) ─────────────────────────────
CLUSTER_PROMPT = (
    "Below are several recent episodes from an autonomous agent's activity "
    "that cluster together by similarity. Identify the recurring behavioural "
    "pattern they evidence — grounded in what actually happened, not a "
    "platitude. Output a JSON object {{\"patterns\": [\"...\"]}} with 1-3 "
    "concise patterns. If nothing generalizable connects them, output "
    "{{\"patterns\": []}}.\n\nEpisodes:\n{episodes}"
)
SINGLETON_PROMPT = (
    "Below is a single recent episode from an autonomous agent's activity "
    "that matched no existing pattern and joined no cluster. Judge whether it "
    "carries a generalizable, notable observation worth remembering. If yes, "
    "output {{\"patterns\": [\"...\"]}} with exactly one concise pattern. If "
    "it is routine with nothing generalizable, output {{\"patterns\": []}} — "
    "do not invent a pattern.\n\nEpisode:\n{episode}"
)


def _pct(values: List[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def _fmt_dist(label: str, values: List[float]) -> str:
    if not values:
        return f"  {label:<28} (none)"
    return (
        f"  {label:<28} n={len(values):<5} "
        f"min={min(values):7.3f} p50={_pct(values,50):7.3f} "
        f"p90={_pct(values,90):7.3f} max={max(values):7.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=3, help="episode look-back window")
    ap.add_argument("--llm-samples", type=int, default=5,
                    help="how many clusters AND singletons to actually call the LLM on")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip all LLM calls; structural + embedding metrics only")
    ap.add_argument("--cluster-threshold", type=float, default=CLUSTER_THRESHOLD,
                    help="cosine threshold for episode clustering")
    ap.add_argument("--reinforce-threshold", type=float, default=REINFORCE_THRESHOLD,
                    help="cosine threshold (short-embed vs patterns) for reinforce")
    args = ap.parse_args()
    cluster_threshold = args.cluster_threshold
    reinforce_threshold = args.reinforce_threshold

    log_dir = MOLTBOOK_DATA_DIR / "logs"
    episodes = EpisodeLog(log_dir=log_dir)
    knowledge = KnowledgeStore(path=KNOWLEDGE_PATH)
    knowledge.load()

    records = episodes.read_range(days=args.days)
    pre = len(records)
    records = [r for r in records if r.get("type") != "insight"]
    print(f"Episodes: {pre} read, {len(records)} after insight filter "
          f"(days={args.days}, NO noise gate)")
    if not records:
        print("No episodes in window — nothing to measure.")
        return 0

    # Type mix (surfaces the activity/interaction redundancy: each comment
    # writes a rich 'activity' record AND a short 'interaction' record).
    type_mix: Dict[str, int] = {}
    for r in records:
        type_mix[r.get("type", "?")] = type_mix.get(r.get("type", "?"), 0) + 1
    print("Type mix:", ", ".join(f"{k}={v}" for k, v in sorted(type_mix.items())))

    # ── Render: short (for embedding/clustering) + rich (for grounding) ──
    # Input scope: rich engagement episodes only (comment/reply/post activity).
    units: List[dict] = []
    dropped_scope = 0
    raw_lens: Dict[str, List[float]] = {k: [] for k in ("original_post", "their_comment", "content", "internal_note")}
    for r in records:
        rtype = r.get("type", "unknown")
        data = r.get("data", {}) or {}
        if not is_rich_episode(rtype, data):
            dropped_scope += 1
            continue
        short = summarize_record(rtype, data)
        if not short:
            continue  # unknown/empty — matches old drop behaviour
        rich = render_episode(rtype, data)
        if rtype == "activity":
            for f in raw_lens:
                v = data.get(f)
                if v:
                    raw_lens[f].append(float(len(v)))
        units.append({
            "ts": r.get("ts", ""),
            "type": rtype,
            "action": data.get("action", ""),
            "short": short,
            "rich": rich,
        })
    print(f"Renderable rich units: {len(units)}  (dropped {dropped_scope} "
          f"out-of-scope: interaction/post-record/session + sparse actions)")

    # ── Embed short + rich (timed) ──
    t0 = time.monotonic()
    short_arr = embed_texts([u["short"] for u in units])
    t_short = time.monotonic() - t0
    t0 = time.monotonic()
    rich_arr = embed_texts([u["rich"] for u in units])
    t_rich = time.monotonic() - t0
    if short_arr is None or rich_arr is None:
        print("ERROR: embedding failed (Ollama down?). Cannot measure.")
        return 1
    print(f"Embed timing: short={t_short:.1f}s rich={t_rich:.1f}s "
          f"({len(units)} units each)")

    for i, u in enumerate(units):
        u["short_emb"] = short_arr[i]
        u["rich_emb"] = rich_arr[i]

    # ── Reinforce vs existing live patterns (short-embed = in-distribution) ──
    existing = _live_embedded(knowledge.get_raw_patterns())
    print(f"Live embedded patterns (reinforce pool): {len(existing)}")

    reinforce_short_sims: List[float] = []
    reinforce_rich_sims: List[float] = []
    reinforced: List[dict] = []
    novel: List[dict] = []
    for u in units:
        s_sim, _ = _best_existing_sim(u["short_emb"], existing)
        r_sim, _ = _best_existing_sim(u["rich_emb"], existing)
        reinforce_short_sims.append(s_sim)
        reinforce_rich_sims.append(r_sim)
        u["reinforce_short_sim"] = s_sim
        u["reinforce_rich_sim"] = r_sim
        if s_sim >= reinforce_threshold:
            reinforced.append(u)
        else:
            novel.append(u)

    # ── Cluster the novel units (short-embed) ──
    cluster_input = [
        {"embedding": [float(x) for x in u["short_emb"]],
         "distilled": u["ts"], "pattern": u["rich"], "_unit": u}
        for u in novel
    ]
    t0 = time.monotonic()
    clusters, singletons = cluster_patterns(
        cluster_input,
        threshold=cluster_threshold,
        min_size=MIN_EPISODES_PER_CLUSTER,
        max_size=MAX_CLUSTER_SIZE,
    )
    t_cluster = time.monotonic() - t0
    n_clustered = sum(len(c) for c in clusters)

    # ── Branch-ratio + LLM-budget report ──
    total = len(units)
    llm_calls = len(clusters) + len(singletons)
    old_kept = total  # current pipeline keeps everything past the noise gate
    old_calls = math.ceil(old_kept / 30) * 2  # 2-step extract+refine per batch of 30
    print("\n===== BRANCH RATIOS =====")
    print(f"  reinforce : {len(reinforced):5d}  ({100*len(reinforced)/total:5.1f}%)  [no LLM]")
    print(f"  clustered : {n_clustered:5d}  ({100*n_clustered/total:5.1f}%)  in {len(clusters)} clusters")
    print(f"  singleton : {len(singletons):5d}  ({100*len(singletons)/total:5.1f}%)")
    print("\n===== LLM CALL BUDGET =====")
    print(f"  proposed : {llm_calls}  (= {len(clusters)} clusters + {len(singletons)} singletons)")
    print(f"  current  : ~{old_calls}  (ceil({old_kept}/30) batches x 2 steps)")
    print(f"  cluster step wall-clock: {t_cluster:.2f}s (N={len(novel)} novel; O(N^2))")

    print("\n===== REINFORCE COSINE DISTRIBUTIONS (open question: modality) =====")
    print(_fmt_dist("short-embed vs patterns", reinforce_short_sims))
    print(_fmt_dist("rich-embed  vs patterns", reinforce_rich_sims))
    print(f"  (reinforce_threshold={reinforce_threshold} applied to short-embed)")

    print("\n===== INTRA-CLUSTER COSINE SPREAD (open question: cluster threshold) =====")
    print(f"  (cluster_threshold={cluster_threshold}, min_size={MIN_EPISODES_PER_CLUSTER})")
    for ci, c in enumerate(clusters):
        embs = [np.asarray(m["embedding"], dtype=np.float32) for m in c]
        sims = [cosine(embs[i], embs[j])
                for i in range(len(embs)) for j in range(i + 1, len(embs))]
        spread = (f"min={min(sims):.3f} mean={sum(sims)/len(sims):.3f} max={max(sims):.3f}"
                  if sims else "(singleton-sized)")
        actions = ", ".join(sorted({m["_unit"]["action"] or m["_unit"]["type"] for m in c}))
        print(f"  cluster {ci:2d}: size={len(c):2d}  {spread}  actions=[{actions}]")

    print("\n===== RAW ACTIVITY FIELD LENGTHS (open question: excerpt caps) =====")
    for f, vals in raw_lens.items():
        cap = EXCERPT_CAPS.get(f)
        over = sum(1 for v in vals if cap and v > cap)
        cap_s = f" cap={cap} over={over}" if cap else " (no cap; full)"
        print(_fmt_dist(f, vals) + cap_s)

    # ── LLM quality sampling (provisional prompts) ──
    if args.no_llm:
        print("\n(--no-llm: skipped cluster/singleton generation)")
        return 0

    k = args.llm_samples
    print(f"\n===== LLM CLUSTER SAMPLES (first {k}, provisional prompt) =====")
    for ci, c in enumerate(clusters[:k]):
        episodes_block = "\n\n---\n\n".join(m["pattern"] for m in c)
        t0 = time.monotonic()
        out = generate(CLUSTER_PROMPT.format(episodes=episodes_block),
                       system=get_distill_system_prompt(), num_predict=3000,
                       caller="proto.cluster")
        dt = time.monotonic() - t0
        print(f"\n--- cluster {ci} (size={len(c)}, {dt:.1f}s) ---")
        print(out or "(generation failed)")

    print(f"\n===== LLM SINGLETON SAMPLES (first {k}, provisional prompt) =====")
    for si, s in enumerate(singletons[:k]):
        t0 = time.monotonic()
        out = generate(SINGLETON_PROMPT.format(episode=s["pattern"]),
                       system=get_distill_system_prompt(), num_predict=3000,
                       caller="proto.singleton")
        dt = time.monotonic() - t0
        print(f"\n--- singleton {si} ({dt:.1f}s) ---")
        print("GROUNDING:", s["pattern"][:400].replace("\n", " ⏎ "))
        print("OUTPUT:", out or "(generation failed)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
