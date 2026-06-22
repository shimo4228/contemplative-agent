#!/usr/bin/env python3
"""Distillation quality benchmark runner.

Runs distill() against fixed test datasets and collects metrics from logs.
Not a pytest test — requires a running Ollama instance.

Usage:
    uv run python tests/benchmark_distill.py run --output results/before.json
    uv run python tests/benchmark_distill.py run --dataset synthetic --output results/after.json
    uv run python tests/benchmark_distill.py compare results/before.json results/after.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contemplative_agent.core.distill import distill
from contemplative_agent.core.episode_log import EpisodeLog
from contemplative_agent.core.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "benchmark"
RESULTS_DIR = FIXTURES_DIR / "results"


@dataclass(frozen=True)
class DistillBenchmarkReport:
    """Metrics collected from a single benchmark run.

    ADR-0060: distill is per-episode (one grounded LLM call per engagement
    episode, no fixed-size batching and no noise gate). The metrics below track
    that pipeline — batch counts, parse-fallback rates, and the Step-0 noise
    classification of the retired 2-step pipeline no longer have a log source.
    """

    # Input
    dataset: str
    episode_count: int
    # ADR-0060: rich engagement episodes (comment/reply/post) after filtering.
    engagement_episode_count: int

    # Pipeline (one LLM call per distilled episode)
    episodes_distilled: int
    llm_call_count: int
    llm_failure_count: int
    elapsed_seconds: float

    # Output
    patterns_added: int
    patterns_updated: int
    patterns_skipped: int
    # ADR-0060: provenance is per-episode; distribution of pattern source kinds
    # (replaces the retired Step-0 category distribution).
    source_type_distribution: Dict[str, int] = field(default_factory=dict)
    pattern_lengths: List[int] = field(default_factory=list)


def _collect_metrics_from_logs(
    log_records: List[logging.LogRecord],
    dataset: str,
    episode_count: int,
    elapsed: float,
) -> DistillBenchmarkReport:
    """Parse log records emitted by distill() into a DistillBenchmarkReport.

    ADR-0060 log surface (per-episode distill):
      - "Distilling N engagement episodes (filtered from M records)"
      - "Distilling N episodes individually"
      - "Added pattern (source=X): ..."          (one per stored pattern)
      - "Dedup: N soft-invalidated ..."          (recurring patterns replaced)
      - "Dry run — N patterns found, S skipped, U would soft-invalidate"
      - "Distill complete: A added, U updated"   (authoritative final counts)
      - "Episode distill failed (LLM returned None)"  (per-episode LLM failure)
      - "SKIP (sim): ..."                         (per-pattern dedup skip, info)
    """
    engagement_episode_count = 0
    episodes_distilled = 0
    total_added = 0
    total_updated = 0
    total_skipped = 0
    llm_failure_count = 0
    source_type_dist: Dict[str, int] = {}
    pattern_lengths: List[int] = []

    for rec in log_records:
        msg = rec.getMessage()

        # ADR-0060: engagement-episode filter (rich / total records)
        m = re.search(r"Distilling (\d+) engagement episodes \(filtered from (\d+) records\)", msg)
        if m:
            engagement_episode_count = int(m.group(1))

        # ADR-0060: per-episode loop — one structured LLM call each
        m = re.search(r"Distilling (\d+) episodes individually", msg)
        if m:
            episodes_distilled = int(m.group(1))

        # Added patterns, with per-episode source provenance
        m = re.search(r"Added pattern \(source=([^)]+)\): (.+)", msg)
        if m:
            total_added += 1
            source_type_dist[m.group(1)] = source_type_dist.get(m.group(1), 0) + 1
            pattern_lengths.append(len(m.group(2)))

        # Per-pattern dedup skip against the existing live pool (info-level).
        # The distinct intra-run "SKIP-NEW" path (a new pattern skipped against
        # another new pattern in the same run) is intentionally NOT counted
        # here — "SKIP (" excludes "SKIP-NEW (" — so this tracks only skips
        # against already-stored patterns.
        if re.match(r"SKIP \(\d", msg):
            total_skipped += 1

        # Recurring pattern replaced (soft-invalidate + re-add)
        m = re.search(r"Dedup: (\d+) soft-invalidated", msg)
        if m:
            total_updated = int(m.group(1))

        # Dry-run summary — authoritative skip / would-update when not persisting
        m = re.search(r"Dry run — (\d+) patterns found, (\d+) skipped, (\d+) would soft-invalidate", msg)
        if m:
            total_skipped = int(m.group(2))
            total_updated = int(m.group(3))

        # Authoritative final counts (non-dry-run)
        m = re.search(r"Distill complete: (\d+) added, (\d+) updated", msg)
        if m:
            total_added = int(m.group(1))
            total_updated = int(m.group(2))

        # Per-episode LLM failure
        if "Episode distill failed (LLM returned None)" in msg:
            llm_failure_count += 1

    # ADR-0060: exactly one structured LLM call per distilled episode.
    llm_call_count = episodes_distilled

    return DistillBenchmarkReport(
        dataset=dataset,
        episode_count=episode_count,
        engagement_episode_count=engagement_episode_count,
        episodes_distilled=episodes_distilled,
        llm_call_count=llm_call_count,
        llm_failure_count=llm_failure_count,
        elapsed_seconds=round(elapsed, 2),
        patterns_added=total_added,
        patterns_updated=total_updated,
        patterns_skipped=total_skipped,
        source_type_distribution=source_type_dist,
        pattern_lengths=pattern_lengths,
    )


def run_benchmark(dataset: str = "synthetic", output: Optional[str] = None) -> DistillBenchmarkReport:
    """Run distill() against a fixed dataset and collect metrics."""
    dataset_path = FIXTURES_DIR / f"{dataset}.jsonl"
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        sys.exit(1)

    records = EpisodeLog.read_file(dataset_path)
    print(f"Loaded {len(records)} episodes from {dataset_path.name}")

    # Fresh knowledge store (in-memory, no persistence)
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp())
    knowledge = KnowledgeStore(path=tmp_dir / "knowledge.json")
    knowledge.load()

    # Capture logs
    log_records: List[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    collector = _Collector(level=logging.DEBUG)
    root_logger = logging.getLogger("contemplative_agent")
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(collector)

    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root_logger.addHandler(console)

    try:
        start = time.monotonic()
        distill(
            days=1,
            dry_run=False,
            knowledge_store=knowledge,
            log_files=[dataset_path],
        )
        elapsed = time.monotonic() - start
    finally:
        root_logger.removeHandler(collector)
        root_logger.removeHandler(console)

    report = _collect_metrics_from_logs(log_records, dataset, len(records), elapsed)

    # Save results (always — auto-generate filename if not specified)
    if not output:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output = f"{dataset}_{ts}.json"
    out_path = RESULTS_DIR / output if not Path(output).is_absolute() else Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    print(f"\nResults saved to {out_path}")

    _print_report(report)
    return report


def _print_report(report: DistillBenchmarkReport) -> None:
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print(f"  Distill Benchmark Report — {report.dataset}")
    print("=" * 60)

    print(f"\n  Episodes:     {report.episode_count}")
    print(f"  Engagement:   {report.engagement_episode_count}")
    if report.source_type_distribution:
        for kind, count in sorted(report.source_type_distribution.items()):
            print(f"    {kind}: {count}")

    print(f"\n  Distilled:   {report.episodes_distilled}")
    print(f"  LLM calls:   {report.llm_call_count}")
    print(f"  LLM failures:{report.llm_failure_count}")
    print(f"  Elapsed:     {report.elapsed_seconds:.1f}s")

    print(f"\n  Added:        {report.patterns_added}")
    print(f"  Updated:      {report.patterns_updated}")
    print(f"  Skipped:      {report.patterns_skipped}")

    if report.pattern_lengths:
        lens = report.pattern_lengths
        print(f"  Pattern len: mean={sum(lens)/len(lens):.0f}, "
              f"min={min(lens)}, max={max(lens)}, n={len(lens)}")

    print()


def compare_reports(path_a: str, path_b: str) -> None:
    """Compare two benchmark result JSON files."""
    a = json.loads(Path(path_a).read_text())
    b = json.loads(Path(path_b).read_text())

    print("\n" + "=" * 70)
    print(f"  Comparison: {Path(path_a).name} vs {Path(path_b).name}")
    print("=" * 70)

    fields = [
        ("Episodes", "episode_count"),
        ("Engagement", "engagement_episode_count"),
        ("Distilled", "episodes_distilled"),
        ("LLM calls", "llm_call_count"),
        ("LLM failures", "llm_failure_count"),
        ("Elapsed (s)", "elapsed_seconds"),
        ("Added", "patterns_added"),
        ("Updated", "patterns_updated"),
        ("Skipped", "patterns_skipped"),
    ]

    print(f"\n  {'Metric':<20} {'Before':>10} {'After':>10} {'Delta':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10}")

    for label, key in fields:
        va = a.get(key, 0)
        vb = b.get(key, 0)
        delta = vb - va
        sign = "+" if delta > 0 else ""
        print(f"  {label:<20} {va:>10} {vb:>10} {sign}{delta:>9}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Distillation quality benchmark")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run benchmark")
    run_parser.add_argument("--dataset", default="real_sample", help="Dataset name (default: real_sample)")
    run_parser.add_argument("--output", "-o", help="Output JSON filename (saved in results/)")

    cmp_parser = sub.add_parser("compare", help="Compare two result files")
    cmp_parser.add_argument("before", help="Path to before results JSON")
    cmp_parser.add_argument("after", help="Path to after results JSON")

    args = parser.parse_args()

    if args.command == "run":
        run_benchmark(dataset=args.dataset, output=args.output)
    elif args.command == "compare":
        compare_reports(args.before, args.after)


if __name__ == "__main__":
    main()
