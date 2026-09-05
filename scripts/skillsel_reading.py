"""Read-only reading over the skill-selection audit log (RFC-0014 / RFC-0015).

Reproduces, from a single deterministic pass, the aggregates the 2nd and 3rd
readings assembled from throwaway scratchpad scripts (2026-08-08 / 2026-08-22).
Those were session-limited, so each reading re-derived its own numbers and the
longitudinal table could not be replayed. This script is the replayable form
(ADR-0075): same rules, in `scripts/`, so the next window is a re-run and not a
re-derivation.

Instrument, never intervention (skill `read-only-instruments`): nothing here
writes, and no reading feeds the selector.

Reads ONLY the `skill-selection-` logs. Episode logs (`YYYY-MM-DD.jsonl`) and
`agent-launchd.log` in the same directory are prompt-injection carriers and are
unreachable by construction — the enumeration filters on the
`skill-selection-` prefix and never globs the directory. The `prompt_b64` /
`output_b64` payloads are dropped at parse time and never decoded.

That is not the same as "no untrusted-derived text reaches stdout".
`rejected_names` is model output conditioned on the (dropped) situation text,
and one observed form in the 2026-08-23..09-05 window was a fragment of that
text rather than a name. The strings are printed verbatim because the whole
reading is about their spelling; the transcription discipline is on the reader
of this output, not on this script.

Usage:
    python3 scripts/skillsel_reading.py --start 2026-08-23 --end 2026-09-05

Dates are UTC days, matching how `core/skill_selection.py` names the files.
"""

from __future__ import annotations

import argparse
import collections
import difflib
import json
import os
import pathlib
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _stats import wilson_ci  # noqa: E402  (sibling import, see _stats docstring)

LOG_PREFIX = "skill-selection-"
DATE_RE = re.compile(r"^skill-selection-(\d{4}-\d{2}-\d{2})\.jsonl$")

# Payload keys dropped at parse time: untrusted-origin text lives here in b64
# and this reading has no business decoding it.
DROP_KEYS = frozenset(
    {
        "prompt_b64",
        "output_b64",
        "prompt_sha256",
        "output_sha256",
        "prompt_encoding",
        "output_encoding",
    }
)

# §4.2 of the 3rd reading: surface similarity at or above this counts a
# rejected name as a morphological variant of its nearest catalog entry rather
# than a semantic mistake. Pinned to the value the 2nd/3rd readings used so the
# longitudinal series stays one series.
MORPH_SIM = 0.90


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("MOLTBOOK_HOME", os.path.expanduser("~/.config/moltbook")))


def log_files(logs_dir: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    """(utc-day, path) for skill-selection logs only, oldest first."""
    out = []
    for entry in sorted(logs_dir.iterdir()):
        if not entry.is_file() or not entry.name.startswith(LOG_PREFIX):
            continue
        m = DATE_RE.match(entry.name)
        if m:
            out.append((m.group(1), entry))
    return out


def load(logs_dir: pathlib.Path) -> tuple[list[dict], int]:
    records: list[dict] = []
    unparsable = 0
    for day, path in log_files(logs_dir):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                unparsable += 1
                continue
            if not isinstance(rec, dict):
                unparsable += 1
                continue
            rec = {k: v for k, v in rec.items() if k not in DROP_KEYS}
            rec["_day"] = day
            records.append(rec)
    return records, unparsable


def pct(num: int, den: int) -> str:
    return "n/a" if den <= 0 else f"{100.0 * num / den:.2f}%"


def rate(num: int, den: int) -> str:
    """Rate with its 95% Wilson interval — the resolution is part of the reading.

    Several regimes in the longitudinal series rest on tens of records, where a
    bare percentage invites a comparison the denominator cannot support.
    """
    ci = wilson_ci(num, den)
    if ci is None:
        return pct(num, den)
    return f"{pct(num, den)} [{100 * ci[0]:.1f}..{100 * ci[1]:.1f}]"


def quantile(values: list[float], q: float) -> float | None:
    """Nearest-rank order statistic, NOT an interpolating quantile.

    Printed as `p50 (nearest-rank)` rather than `p50` because for even n the
    index lands on a `.5` that `round` resolves by banker's rounding, so which
    of the two middle values wins flips with the parity of n/2. Harmless at
    n=1030; it moves the printed digit on the per-day rows (n = 19..92). The
    corpus figure elsewhere uses `statistics.median` and is labelled median.
    """
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def is_halluc(rec: dict) -> bool:
    return bool(rec.get("rejected_names"))


def catalog_vocab(skills_dir: pathlib.Path) -> tuple[set[str], dict[str, str]]:
    """Tokens the pass-1 prompt is built from, and name -> file stem.

    The prompt carries exactly (frontmatter name, frontmatter description) per
    entry — the `# heading` never appears — which is why the 2026-08-08 reading
    could rule out filename-derived wording as a hallucination source.
    """
    tokens: set[str] = set()
    name_to_stem: dict[str, str] = {}
    if not skills_dir.is_dir():
        return tokens, name_to_stem
    for path in sorted(skills_dir.iterdir()):
        if path.suffix != ".md" or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        name = ""
        for field in ("name", "description"):
            m = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE)
            if not m:
                continue
            value = m.group(1).strip()
            if field == "name":
                name = value
            tokens.update(re.findall(r"[a-z0-9]+", value.lower()))
        if name:
            name_to_stem[name] = path.stem
    return tokens, name_to_stem


def value_vocab(store: pathlib.Path) -> set[str]:
    """Tokens of the value layer (constitution / identity / rules).

    Rule 2 of the mechanism split needs "this token exists in the value layer
    but not in the catalog" to call a rejected name value-layer bleed.
    """
    tokens: set[str] = set()
    targets: list[pathlib.Path] = []
    identity = store / "identity.md"
    if identity.is_file():
        targets.append(identity)
    for sub in ("constitution", "rules"):
        d = store / sub
        if d.is_dir():
            targets.extend(p for p in sorted(d.iterdir()) if p.suffix == ".md" and p.is_file())
    for path in targets:
        tokens.update(
            re.findall(r"[a-z0-9]+", path.read_text(encoding="utf-8", errors="replace").lower())
        )
    return tokens


def classify(
    name: str, catalog_names: set[str], cat_tokens: set[str], val_tokens: set[str]
) -> tuple[str, str, float]:
    """(mechanism, nearest catalog name, similarity) for one rejected name.

    Rules verbatim from the 3rd reading §4.2, in order:
      1. whitespace or `/` -> prose form -> value-layer bleed
      2. carries a token absent from the catalog but present in the value
         layer -> value-layer bleed
      3. surface similarity to nearest catalog entry >= 0.90 -> morphological
      4. otherwise -> semantic mistake
    """
    nearest, sim = "", 0.0
    # `sorted` is not cosmetic: `catalog_names` is a set, and two entries can
    # tie on similarity. Iterating the set would hand the tie to whichever
    # spelling the hash order happened to visit first, so the grouping table
    # would differ between runs of the same window — the one thing a
    # longitudinal series cannot tolerate.
    for candidate in sorted(catalog_names):
        s = difflib.SequenceMatcher(None, name, candidate).ratio()
        if s > sim:
            nearest, sim = candidate, s
    if " " in name or "/" in name:
        return "value-layer-bleed", nearest, sim
    tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    intruders = tokens - cat_tokens
    if intruders & val_tokens:
        return "value-layer-bleed", nearest, sim
    if sim >= MORPH_SIM:
        return "morphological", nearest, sim
    return "semantic", nearest, sim


def _report_phase0(window: list[dict]) -> list[dict]:
    """Field presence + verdict tally; returns the judged subset."""
    print("\n## phase-0 field presence (window)")
    for field in (
        "verdict",
        "enforced",
        "rejected_names",
        "catalog_count",
        "catalog_names",
        "selected",
    ):
        print(f"  {field}: {sum(1 for r in window if field in r)}/{len(window)}")
    print(f"  verdicts: {dict(collections.Counter(r.get('verdict') for r in window))}")
    return [r for r in window if r.get("verdict") == "judged"]


def _reduction(records: list[dict]) -> list[float]:
    return [
        100.0 * (1 - r["would_be_skill_tokens"] / r["full_skill_tokens"])
        for r in records
        if r.get("full_skill_tokens")
    ]


def _report_criteria(window: list[dict], judged: list[dict]) -> None:
    enforced = sum(1 for r in judged if r.get("enforced"))
    fail_open = sum(1 for r in window if str(r.get("verdict", "")).startswith("fail_open"))
    jd_empty = sum(1 for r in judged if not r.get("selected"))
    halluc = sum(1 for r in judged if is_halluc(r))
    sel = [len(r.get("selected") or []) for r in judged]
    red = _reduction(judged)
    corpus = [r["full_skill_tokens"] for r in judged if r.get("full_skill_tokens")]
    print("\n## 4 criteria (window, judged)")
    print(f"  judged: {len(judged)}/{len(window)}")
    print(f"  enforced/judged: {enforced}/{len(judged)} = {pct(enforced, len(judged))}")
    print(f"  fail-open: {fail_open}/{len(window)} = {pct(fail_open, len(window))}")
    print(f"  judged-empty: {jd_empty}/{len(judged)} = {pct(jd_empty, len(judged))}")
    print(
        f"  hallucination (rejected_names non-empty): {halluc}/{len(judged)} = {rate(halluc, len(judged))}"
    )
    print(
        f"  selected/action p50={quantile(sel, 0.5)} p90={quantile(sel, 0.9)} max={max(sel) if sel else None}"
    )
    print(
        f"  reduction p10={quantile(red, 0.1):.1f}% p50={quantile(red, 0.5):.1f}% p90={quantile(red, 0.9):.1f}%"
    )
    print(f"  corpus tokens min={min(corpus)} max={max(corpus)}")


def _report_daily(window: list[dict]) -> None:
    print("\n## per day")
    print(
        "  day | rec | judged | enf | fail-open | jd-empty | halluc | halluc% | catalog | sel p50* | red p50*  (*nearest-rank)"
    )
    by_day: dict[str, list[dict]] = collections.defaultdict(list)
    for r in window:
        by_day[r["_day"]].append(r)
    for day in sorted(by_day):
        rows = by_day[day]
        jd = [r for r in rows if r.get("verdict") == "judged"]
        cats: list[int] = []
        for r in rows:
            c = r.get("catalog_count")
            if c is not None and (not cats or cats[-1] != c):
                cats.append(c)
        d_red = _reduction(jd)
        d_hal = sum(1 for r in jd if is_halluc(r))
        red_p50 = f"{quantile(d_red, 0.5):.1f}%" if d_red else "n/a"
        print(
            f"  {day} | {len(rows)} | {len(jd)} | {sum(1 for r in jd if r.get('enforced'))} | "
            f"{sum(1 for r in rows if str(r.get('verdict', '')).startswith('fail_open'))} | "
            f"{sum(1 for r in jd if not r.get('selected'))} | {d_hal} | {pct(d_hal, len(jd))} | "
            f"{'→'.join(str(c) for c in cats)} | {quantile([len(r.get('selected') or []) for r in jd], 0.5)} | "
            f"{red_p50}"
        )


def _report_catalog_conditioning(all_records: list[dict]) -> None:
    """The longitudinal table RFC-0015 reads: rate conditioned on catalog size.

    Kept over ALL history, not the window, because the point of the series is
    that each regime is one row and windows straddle regime changes.
    """
    print("\n## hallucination conditioned on catalog_count (all history)")
    print("  NOTE: a day on which the catalog changed appears in TWO rows, so the day counts")
    print("        below sum to more than the history. `tok` prints a range whenever the")
    print("        regime is not a single store state — §4.2's token ordering is only")
    print("        well-defined for rows where min == max.")
    print("  catalog | judged | halluc | rate | corpus tok | days")
    per_cat: dict[int, list[dict]] = collections.defaultdict(list)
    for r in all_records:
        if r.get("verdict") == "judged" and r.get("catalog_count") is not None:
            per_cat[r["catalog_count"]].append(r)
    for c in sorted(per_cat):
        rows = per_cat[c]
        h = sum(1 for r in rows if is_halluc(r))
        toks = [r["full_skill_tokens"] for r in rows if r.get("full_skill_tokens")]
        days = sorted({r["_day"] for r in rows})
        span = f"{days[0]}..{days[-1]} ({len(days)}d)" if days else "-"
        if not toks:
            tok_s = "n/a"
        elif min(toks) == max(toks):
            tok_s = str(min(toks))
        else:
            tok_s = f"{min(toks)}..{max(toks)} (median {int(statistics.median(toks))}, RANGE)"
        print(f"  {c} | {len(rows)} | {h} | {rate(h, len(rows))} | {tok_s} | {span}")


def _tally_rejected(
    judged: list[dict],
    cat_names: set[str],
    cat_tokens: set[str],
    val_tokens: set[str],
) -> tuple[collections.Counter, dict[str, tuple[str, str, float]]]:
    """Occurrence count and (mechanism, nearest, sim) per distinct rejected name."""
    name_counts: collections.Counter = collections.Counter()
    name_info: dict[str, tuple[str, str, float]] = {}
    for r in judged:
        for nm in r.get("rejected_names") or []:
            if not isinstance(nm, str):
                continue
            name_counts[nm] += 1
            if nm not in name_info:
                name_info[nm] = classify(nm, cat_names, cat_tokens, val_tokens)
    return name_counts, name_info


def _report_hallucination(
    window: list[dict],
    judged: list[dict],
    all_records: list[dict],
    cat_tokens: set[str],
    val_tokens: set[str],
) -> None:
    cat_names: set[str] = set()
    for r in window:
        cat_names.update(r.get("catalog_names") or [])
    name_counts, name_info = _tally_rejected(judged, cat_names, cat_tokens, val_tokens)

    mech: collections.Counter = collections.Counter()
    mech_distinct: dict[str, set[str]] = collections.defaultdict(set)
    for nm, cnt in name_counts.items():
        mech[name_info[nm][0]] += cnt
        mech_distinct[name_info[nm][0]].add(nm)
    total = sum(mech.values())
    print("\n## hallucination mechanisms (window)")
    for m in ("morphological", "semantic", "value-layer-bleed"):
        print(f"  {m}: {mech[m]} ({pct(mech[m], total)}) / distinct {len(mech_distinct[m])}")
    print(f"  total emitted rejected names: {total} / distinct {len(name_counts)}")

    print("\n## top rejected names (>=5 occurrences)")
    print("  count | mechanism | sim | rejected -> nearest catalog entry")
    for nm, cnt in name_counts.most_common():
        if cnt < 5:
            break
        m, near, sim = name_info[nm]
        print(f"  {cnt} | {m} | {sim:.2f} | {nm} -> {near}")

    print("\n## rejected names grouped by nearest catalog entry (>=5 total)")
    print("  total | catalog entry <- variants")
    grouped: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for nm, cnt in name_counts.items():
        grouped[name_info[nm][1]].append((nm, cnt))
    for near, variants in sorted(grouped.items(), key=lambda kv: -sum(c for _, c in kv[1])):
        total_near = sum(c for _, c in variants)
        if total_near < 5:
            continue
        forms = ", ".join(f"{nm}({c})" for nm, c in sorted(variants, key=lambda x: -x[1]))
        print(f"  {total_near} | {near} <- {forms}")

    _report_propagation(judged, all_records, cat_names, name_counts)


def _report_propagation(
    judged: list[dict],
    all_records: list[dict],
    cat_names: set[str],
    name_counts: collections.Counter,
) -> None:
    selected_names: set[str] = set()
    for r in judged:
        selected_names.update(x for x in (r.get("selected") or []) if isinstance(x, str))
    # The window's catalog is what the selector filtered against, so a rejected
    # name matching it is impossible by construction and says nothing. The
    # question worth asking is the historical one: is a hallucinated name a
    # FORMER catalog entry — the model reproducing a spelling that a rename or
    # merge removed? Only the all-history union answers that, and the preceding
    # window carried four such key discontinuities (1 merge + 3 renames).
    ever_catalog: set[str] = set()
    for r in all_records:
        ever_catalog.update(x for x in (r.get("catalog_names") or []) if isinstance(x, str))
    print("\n## propagation")
    print(
        f"  distinct rejected names that ever appear in `selected` (window): "
        f"{len(set(name_counts) & selected_names)}"
    )
    print(
        f"  distinct rejected names present in THIS window's catalog: "
        f"{len(set(name_counts) & cat_names)}"
    )
    print(
        f"  distinct rejected names that were EVER a catalog entry (all history): "
        f"{len(set(name_counts) & ever_catalog)}"
    )


def _tally_field(records: list[dict], field: str) -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    for r in records:
        for nm in r.get(field) or []:
            if isinstance(nm, str):
                counts[nm] += 1
    return counts


def _report_exposure(
    judged: list[dict], share: collections.Counter, name_to_stem: dict[str, str]
) -> None:
    """Never-selected and the low-selection tail, each with its exposure count.

    Exposure is what makes a zero readable: a freshly adopted entry offered in
    a handful of records is not a retirement signal (the 3rd reading had to say
    so about the nine entries adopted on its last day).
    """
    exposure = _tally_field(judged, "catalog_names")
    print("\n## never-selected (offered, chosen 0)")
    for nm in sorted(exposure):
        if share.get(nm, 0) == 0:
            print(
                f"  {nm}: offered {exposure[nm]}/{len(judged)}, chosen 0  (file: {name_to_stem.get(nm, '?')})"
            )
    print("\n## low-selection tail (chosen 1..5)")
    for nm in sorted(exposure):
        if 1 <= share.get(nm, 0) <= 5:
            print(f"  {nm}: {share[nm]}/{exposure[nm]}")


def _report_share(
    judged: list[dict], all_records: list[dict], name_to_stem: dict[str, str]
) -> None:
    print("\n## selection share (window, judged)")
    share = _tally_field(judged, "selected")
    for nm, cnt in share.most_common(10):
        print(f"  {pct(cnt, len(judged))} | {cnt} | {nm}")
    top3 = [c for _, c in share.most_common(3)]
    if top3:
        print(f"  top-3 mean share: {pct(sum(top3), 3 * len(judged))}")

    print("\n## catalog entry arrival (first UTC day the name appears in catalog_names)")
    first_seen: dict[str, str] = {}
    for r in all_records:
        for nm in r.get("catalog_names") or []:
            if isinstance(nm, str):
                first_seen.setdefault(nm, r["_day"])
    for nm, cnt in share.most_common(12):
        print(f"  {first_seen.get(nm, '?')} | {pct(cnt, len(judged))} | {nm}")

    _report_exposure(judged, share, name_to_stem)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--start", required=True, help="window start, UTC day (inclusive)")
    ap.add_argument("--end", required=True, help="window end, UTC day (inclusive)")
    ap.add_argument("--home", default=None, help="store root (default: $MOLTBOOK_HOME)")
    args = ap.parse_args()

    # The window filter compares `YYYY-MM-DD` strings, which is chronological
    # only for that exact spelling. A `2026-8-23` would silently select the
    # wrong window rather than fail, and a reading that quietly covers the
    # wrong days is worse than one that refuses.
    for label, value in (("--start", args.start), ("--end", args.end)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            print(f"ABSTAIN: {label} must be YYYY-MM-DD, got {value!r}", file=sys.stderr)
            return 2
    if args.start > args.end:
        print("ABSTAIN: --start is after --end", file=sys.stderr)
        return 2

    store = pathlib.Path(args.home) if args.home else home()
    logs_dir = store / "logs"
    if not logs_dir.is_dir():
        print(f"ABSTAIN: no logs directory at {logs_dir}", file=sys.stderr)
        return 2

    all_records, unparsable = load(logs_dir)
    window = [r for r in all_records if args.start <= r["_day"] <= args.end]

    print("# skill-selection reading")
    print(f"window: {args.start}..{args.end} (UTC days)")
    print(f"all-history records: {len(all_records)} (unparsable lines: {unparsable})")
    print(f"window records: {len(window)}")
    if not window:
        print("ABSTAIN: window empty")
        return 2

    cat_tokens, name_to_stem = catalog_vocab(store / "skills")
    val_tokens = value_vocab(store)
    print(f"store skills on disk now: {len(name_to_stem)}")

    judged = _report_phase0(window)
    _report_criteria(window, judged)
    _report_daily(window)
    _report_catalog_conditioning(all_records)
    _report_hallucination(window, judged, all_records, cat_tokens, val_tokens)
    _report_share(judged, all_records, name_to_stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
