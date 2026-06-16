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
    """Metrics collected from a single benchmark run."""

    # Input
    dataset: str
    episode_count: int
    category_distribution: Dict[str, int]

    # Pipeline
    batch_count: int
    parse_success_count: int
    parse_fallback_count: int
    parse_failure_count: int
    llm_call_count: int
    llm_timeout_count: int
    elapsed_seconds: float

    # Output
    patterns_extracted: int
    patterns_rejected: int
    patterns_added: int
    patterns_updated: int
    patterns_skipped: int
    uncertain_count: int
    pattern_lengths: List[int] = field(default_factory=list)


def _collect_metrics_from_logs(
    log_records: List[logging.LogRecord],
    dataset: str,
    episode_count: int,
    elapsed: float,
) -> DistillBenchmarkReport:
    """Parse log records emitted by distill() into a DistillBenchmarkReport."""
    category_dist: Dict[str, int] = {}
    batch_count = 0
    total_extracted = 0
    total_rejected = 0
    total_added = 0
    total_updated = 0
    total_skipped = 0
    uncertain_count = 0
    llm_call_count = 0
    llm_timeout_count = 0
    parse_success = 0
    parse_fallback = 0
    parse_failure = 0
    pattern_lengths: List[int] = []

    for rec in log_records:
        msg = rec.getMessage()

        # Step 0 classification
        m = re.search(r"Step 0: (\d+) constitutional, (\d+) uncategorized, (\d+) noise", msg)
        if m:
            category_dist = {
                "constitutional": int(m.group(1)),
                "uncategorized": int(m.group(2)),
                "noise": int(m.group(3)),
            }

        # Batch results (ADR-0056: the 2-step pipeline log carries no importance)
        m = re.search(r"Batch (\d+)/(\d+): \d+ episodes \(prompt \d+ chars\) → (\d+) patterns \((\d+) rejected\)", msg)
        if m:
            batch_count = max(batch_count, int(m.group(2)))
            extracted = int(m.group(3))
            rejected = int(m.group(4))
            total_extracted += extracted
            total_rejected += rejected

        # Added patterns
        m = re.search(r"Added pattern \(source=[^)]+\): (.+)", msg)
        if m:
            total_added += 1
            pattern_lengths.append(len(m.group(1)))

        # Dedup updates
        if "Dedup:" in msg and "update" in msg:
            m = re.search(r"(\d+) update", msg)
            if m:
                total_updated += int(m.group(1))

        # LLM quality gate
        m = re.search(r"LLM quality gate: (\d+) uncertain", msg)
        if m:
            uncertain_count += int(m.group(1))

        # Distill complete
        m = re.search(r"Distill complete: (\d+) added, (\d+) updated", msg)
        if m:
            # Use authoritative final counts
            total_added = int(m.group(1))
            total_updated = int(m.group(2))

        # Ollama calls
        if "Ollama request failed" in msg:
            llm_timeout_count += 1
        if "/api/generate" in msg or "Ollama" in msg:
            pass  # counted via batch/classify

        # Parse outcomes
        if "Failed to parse dedup decisions" in msg:
            parse_failure += 1
        if "Dedup decision count mismatch" in msg:
            parse_fallback += 1

    # Estimate LLM calls: classify(N) + extract(batches) + refine(batches) + dedup(uncertain>0)
    # ADR-0056: the importance call per batch was retired (3 → 2 per batch).
    llm_call_count = episode_count + batch_count * 2 + (1 if uncertain_count > 0 else 0)

    # Parse success = extract/refine batches + dedup calls - failures - fallbacks
    parse_total = batch_count + (1 if uncertain_count > 0 else 0)
    parse_success = max(0, parse_total - parse_failure - parse_fallback)

    return DistillBenchmarkReport(
        dataset=dataset,
        episode_count=episode_count,
        category_distribution=category_dist,
        batch_count=batch_count,
        parse_success_count=parse_success,
        parse_fallback_count=parse_fallback,
        parse_failure_count=parse_failure,
        llm_call_count=llm_call_count,
        llm_timeout_count=llm_timeout_count,
        elapsed_seconds=round(elapsed, 2),
        patterns_extracted=total_extracted,
        patterns_rejected=total_rejected,
        patterns_added=total_added,
        patterns_updated=total_updated,
        patterns_skipped=total_skipped,
        uncertain_count=uncertain_count,
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
    if report.category_distribution:
        for cat, count in sorted(report.category_distribution.items()):
            print(f"    {cat}: {count}")

    print(f"\n  Batches:      {report.batch_count}")
    print(f"  LLM calls:   {report.llm_call_count}")
    print(f"  Timeouts:    {report.llm_timeout_count}")
    print(f"  Elapsed:     {report.elapsed_seconds:.1f}s")

    print(f"\n  Parse success:  {report.parse_success_count}")
    print(f"  Parse fallback: {report.parse_fallback_count}")
    print(f"  Parse failure:  {report.parse_failure_count}")

    print(f"\n  Extracted:    {report.patterns_extracted}")
    print(f"  Rejected:     {report.patterns_rejected}")
    print(f"  Added:        {report.patterns_added}")
    print(f"  Updated:      {report.patterns_updated}")
    print(f"  Uncertain:    {report.uncertain_count}")

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
        ("Batches", "batch_count"),
        ("LLM calls", "llm_call_count"),
        ("Timeouts", "llm_timeout_count"),
        ("Elapsed (s)", "elapsed_seconds"),
        ("Parse success", "parse_success_count"),
        ("Parse fallback", "parse_fallback_count"),
        ("Parse failure", "parse_failure_count"),
        ("Extracted", "patterns_extracted"),
        ("Rejected", "patterns_rejected"),
        ("Added", "patterns_added"),
        ("Updated", "patterns_updated"),
        ("Uncertain", "uncertain_count"),
    ]

    print(f"\n  {'Metric':<20} {'Before':>10} {'After':>10} {'Delta':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10}")

    for label, key in fields:
        va = a.get(key, 0)
        vb = b.get(key, 0)
        delta = vb - va
        sign = "+" if delta > 0 else ""
        print(f"  {label:<20} {va:>10} {vb:>10} {sign}{delta:>9}")

    # Parse reliability = success / (success + fallback + failure)
    for data, name in [(a, "Before"), (b, "After")]:
        total = data.get("parse_success_count", 0) + data.get("parse_fallback_count", 0) + data.get("parse_failure_count", 0)
        if total > 0:
            rate = data.get("parse_success_count", 0) / total * 100
            print(f"  Parse reliability ({name}): {rate:.1f}%")

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
