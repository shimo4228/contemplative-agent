#!/usr/bin/env python3
"""Deterministic log-anomaly sweep over self-written logs (read-only).

The cheap, recurring companion to a full multi-agent audit: it intakes signal
that already exists in the runtime logs instead of generating new analysis.
Operational bugs ("気づかなかったバグ") accumulate as repeated warnings /
errors / truncations between runs; this surfaces them ranked by **novelty**
(new since the last sweep) then **frequency delta**, so a freshly-appearing or
spiking anomaly type floats to the top.

Security (load-bearing):
- Reads ONLY ``*.log`` (launchd / cron stderr, self-written) and ``audit.jsonl``
  (approval history, self-written). It MUST NEVER read the episode logs
  ``YYYY-MM-DD.jsonl`` (+ ``.bak``) — those are untrusted external content and a
  prompt-injection vector, and this output may be fed to an LLM.
- Output is normalized signatures (timestamps stripped, digits squashed,
  truncated), not verbatim log bodies, to shrink the injection surface further.

State: a TSV ``count<TAB>signature`` snapshot of the previous sweep, used to
compute the NEW flag and the per-signature delta. Committing it is an
irreversible side effect — the Δ / 🆕 columns are defined against it, so a run
that commits the snapshot and then fails to produce anything spends the week's
novelty baseline for nobody. ``--no-update --emit-state PATH`` writes the
snapshot aside; the caller promotes it (atomic rename) only after its own work
has succeeded.

Measurement basis: **there is no time window.** Every line present in each
allowed file at sweep time is counted, so a row's ``Count`` spans that file's
lifetime — and the files rotate on different schedules (``ollama-serve.log``
nightly, ``agent-launchd.log`` weekly, the ``*-launchd.log`` of the one-shot
commands never), which makes two rows of one table not necessarily
commensurable. Rotation also lands inside the sweep's own history: lines leave
the ``*.log`` glob, counts fall, and a known signature re-appears as 🆕. That
cannot be fixed by filtering without discarding signal, so the instrument
instead **states its own basis**: a per-file corpus census (name, lines read,
signal lines) is written to a sidecar beside the state path
(``<state>.corpus.tsv`` — the state TSV itself cannot carry a header, see
``read_state``) and rendered above the table next to the previous sweep's
figures, with an explicit sentence when the corpus shrank.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from _md import md_safe

# A line is an anomaly candidate if (a) its log level is WARNING/ERROR/CRITICAL,
# or (b) it matches a level-agnostic critical pattern (these are real problems
# even when logged at INFO/DEBUG). Level keying keeps the verbose DEBUG/INFO
# operational trace (e.g. "circuit breaker open — skipping llm", logged every
# call) out of the sweep; the ranking (novelty + delta) handles the rest.
_LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")
_ATTENTION_LEVELS = {"WARNING", "ERROR", "CRITICAL"}
_CRITICAL_RE = re.compile(r"done_reason=length|truncat|num_ctx|\b429\b|backoff", re.IGNORECASE)


def _is_signal(line: str) -> bool:
    if _CRITICAL_RE.search(line):
        return True
    m = _LEVEL_RE.search(line)
    return bool(m and m.group(1) in _ATTENTION_LEVELS)


# Files we are allowed to read. Episode logs (YYYY-MM-DD.jsonl) are excluded by
# construction: we never glob "*.jsonl".
_LOG_GLOB = "*.log"
_AUDIT_NAME = "audit.jsonl"

# ``[\d:.,\-+Z]`` (note the comma): ``logging``'s *default* asctime renders
# milliseconds as ``2026-07-25 09:12:33,123``, and without the comma the
# ``,123`` would survive the strip and sit at the head of the signature.
# This runtime does not produce that shape — ``cli/runtime.py`` sets
# ``datefmt="%H:%M:%S"``, so its own lines carry no date and no milliseconds
# and are stripped by ``_TS_CLOCK_RE`` below. The comma is defensive breadth
# for the other producers the sweep globs (launchd / cron stderr, third-party
# libraries configured elsewhere), not a repair of an observed leak.
_TS_ISO_RE = re.compile(r"^\[?\d{4}-\d\d-\d\d[T ][\d:.,\-+Z]*\]?\s*")
_TS_CLOCK_RE = re.compile(r"^\[?\d\d:\d\d:\d\d[.,]?\d*\]?\s*")
_DIGITS_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")

# The runtime's log format (``cli/runtime.py``) is
# ``%(asctime)s [%(levelname)s] %(name)s: %(message)s``; ``%(name)s`` is a
# dotted module path up to ~47 chars. Keying the signature on the *address*
# rather than the predicate pushed the outcome clause past the length cap
# ("... created but verification failed" truncated to "... created" — a
# failure rendered as its own opposite). Match the known format and drop the
# module path; lines that do not match fall back to prefix stripping.
#
# ``name`` requires a dot. The sweep globs every ``*.log`` under the home, not
# only this runtime's, and a bare ``[WARNING] Failed: API error 404`` would
# otherwise parse as name=``Failed`` / message=``API error 404`` — silently
# eating the first word of the predicate on any producer that writes a level
# prefix without a logger name.
_RUNTIME_LINE_RE = re.compile(
    r"^\[(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s+"
    r"(?P<name>[A-Za-z_]\w*(?:\.\w+)+):\s*(?P<message>.*)$"
)

# Hex-shaped ids (uuid fragments, sha digests) vary per item the way digit runs
# do, so they must squash the same way or every item gets its own signature.
# The lookahead requires at least one digit so English words made only of
# ``a-f`` letters ("decade", "facade") are not mistaken for ids.
_HEXID_RE = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{6,}(?:-[0-9a-f]{4,})*\b")

_SIG_MAXLEN = 80


@dataclass(frozen=True)
class Finding:
    """One normalized anomaly type with its frequency and novelty.

    ``origins`` is the set of logger names the signature was observed under.
    It is **display-only**: it never enters the signature, the state file or
    the novelty computation, so a module rename changes this column and not
    the 🆕 / Δ reading. It exists because dropping the name from the key
    merges the same message emitted by different subsystems into one row —
    the reader still needs to see that ``Connection refused`` came from both
    the publish adapter and the embedding client.
    """

    signature: str
    count: int
    delta: int
    is_new: bool
    origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileCensus:
    """What one allowed file contributed to this sweep.

    ``lines_read`` is every line the sweep consumed from the file (the
    denominator); ``signal_lines`` is the subset that passed ``_is_signal``
    (the numerator the table's counts are drawn from).
    """

    name: str
    lines_read: int
    signal_lines: int


@dataclass(frozen=True)
class Corpus:
    """The per-file census of one sweep — its measurement basis.

    The sweep has no time window, so this is the only statement of *what* the
    counts were computed over. Diffing it against the previous sweep's census
    is what distinguishes "53 genuinely new failure classes" from "two inputs
    rotated away", which the counts alone cannot express.
    """

    files: tuple[FileCensus, ...] = ()

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def lines_read(self) -> int:
        return sum(f.lines_read for f in self.files)

    @property
    def signal_lines(self) -> int:
        return sum(f.signal_lines for f in self.files)


def normalize_with_origin(line: str) -> tuple[str, str]:
    """Collapse a log line into ``(signature, origin)``.

    Strips the leading timestamp / clock prefix and — for lines in the
    runtime's own log format — lifts out the dotted ``%(name)s`` module path,
    which is returned separately and never keyed, so the length cap covers
    the predicate ("... created but verification failed") instead of the
    address. Lowercases, squashes digit runs and hex-shaped ids to ``#`` (so
    per-item variation groups), and truncates. Agent-name variation *inside
    the message* is intentionally not squashed; minor over-splitting is safer
    than over-merging distinct anomalies.
    """
    s = _TS_ISO_RE.sub("", line)
    s = _TS_CLOCK_RE.sub("", s)
    s = s.strip()
    origin = ""
    m = _RUNTIME_LINE_RE.match(s)
    if m is not None:
        origin = m.group("name")
        s = f"[{m.group('level')}] {m.group('message')}"
    s = s.lower()
    s = _HEXID_RE.sub("#", s)
    s = _DIGITS_RE.sub("#", s)
    s = _WS_RE.sub(" ", s).strip()
    return s[:_SIG_MAXLEN], origin


def normalize(line: str) -> str:
    """Collapse a log line into a stable signature (logger name excluded)."""
    return normalize_with_origin(line)[0]


def analyze(lines: Iterable[str], prev_counts: dict[str, int]) -> list[Finding]:
    """Rank anomaly signatures by novelty then frequency delta.

    ``prev_counts`` is the previous sweep's ``signature -> count`` snapshot.
    A signature absent from it is NEW; otherwise the delta is the increase
    since last sweep. Sort: NEW first, then largest delta, then largest count.
    """
    counts: Counter[str] = Counter()
    origins: dict[str, list[str]] = {}
    for line in lines:
        if not _is_signal(line):
            continue
        sig, origin = normalize_with_origin(line)
        if not sig:
            continue
        counts[sig] += 1
        seen = origins.setdefault(sig, [])
        if origin and origin not in seen:
            seen.append(origin)

    findings: list[Finding] = []
    for sig, count in counts.items():
        prev = prev_counts.get(sig, 0)
        # is_new conflates "first ever seen" with "seen before but absent from
        # the last snapshot" (state stores only the prior sweep's findings, not
        # full history). After log rotation a known signature can re-appear as
        # NEW — an accepted false-positive of the sparse-state design; the
        # weekly LLM reader can discount a familiar signature flagged new.
        findings.append(
            Finding(
                signature=sig,
                count=count,
                delta=count - prev,
                is_new=(prev == 0),
                origins=tuple(origins.get(sig, ())),
            )
        )
    findings.sort(key=lambda f: (not f.is_new, -f.delta, -f.count))
    return findings


def read_state(path: Path) -> dict[str, int]:
    """Load the previous sweep's ``count<TAB>signature`` TSV; empty if absent."""
    if not path.is_file():
        return {}
    out: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        count_str, _, sig = raw.partition("\t")
        if not sig:
            continue
        try:
            out[sig] = int(count_str)
        except ValueError:
            continue
    return out


def write_state(path: Path, findings: Iterable[Finding]) -> None:
    """Persist the current ``count<TAB>signature`` snapshot for next time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{f.count}\t{f.signature}\n" for f in findings)
    path.write_text(body, encoding="utf-8")


def corpus_state_path(state: Path) -> Path:
    """Sidecar path holding the corpus census beside the state snapshot.

    A sidecar rather than a header row in the state file itself: ``read_state``
    silently drops any line whose first field is not an int, so a header would
    vanish without a trace on read and the census would be unrecoverable.
    """
    return state.with_name(state.name + ".corpus.tsv")


def write_corpus(path: Path, corpus: Corpus) -> None:
    """Persist the census as ``lines_read<TAB>signal_lines<TAB>name`` TSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{c.lines_read}\t{c.signal_lines}\t{_tsv_safe(c.name)}\n" for c in corpus.files)
    path.write_text(body, encoding="utf-8")


def read_corpus(path: Path) -> Corpus | None:
    """Load the previous sweep's census; ``None`` when no census exists.

    ``None`` (never recorded — first sweep after this instrument shipped) is
    kept distinct from ``Corpus(())`` (recorded, and the corpus was empty):
    the first cannot support a comparison, the second can.
    """
    if not path.is_file():
        return None
    rows: list[FileCensus] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.split("\t", 2)
        if len(parts) != 3 or not parts[2]:
            continue
        try:
            rows.append(FileCensus(parts[2], int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    return Corpus(tuple(rows))


def _tsv_safe(name: str) -> str:
    """Keep a file name on one TSV field (tabs/newlines are legal in POSIX names)."""
    return name.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def iter_allowed_log_lines(log_dir: Path, census: list[FileCensus] | None = None) -> Iterator[str]:
    """Yield lines from *.log + audit.jsonl only. NEVER episode logs.

    Symlinks are skipped: a ``*.log`` symlink could otherwise redirect into an
    episode log (``2026-06-23.jsonl``) and breach the injection boundary the
    name-glob is meant to enforce. The logs dir is self-written (launchd stderr
    + audit_log), so a legitimate symlink is not expected.

    When ``census`` is given, one ``FileCensus`` per file actually opened is
    appended to it as that file is exhausted — the corpus accounting the
    provenance line reports. Skipped symlinks contribute no row (nothing was
    read from them); a file that fails mid-read contributes the lines that did
    reach the caller, which is what the counts were actually computed over. The
    list is complete only once the generator is fully consumed.
    """
    files = sorted(log_dir.glob(_LOG_GLOB))
    audit = log_dir / _AUDIT_NAME
    if audit.is_file():
        files.append(audit)
    for f in files:
        if f.is_symlink():
            continue
        lines_read = 0
        signal_lines = 0
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    lines_read += 1
                    if _is_signal(line):
                        signal_lines += 1
                    yield line
        except OSError:
            pass
        if census is not None:
            census.append(FileCensus(f.name, lines_read, signal_lines))


# A corpus this much smaller than the previous census is a rotation event, not
# noise: lines left the ``*.log`` glob, so counts fell and known signatures
# re-appear as 🆕. Not a filter — nothing is suppressed at any size; it only
# decides whether the reader is *told* that this week's Δ / 🆕 are incomparable.
_CORPUS_SHRINK_RATIO = 0.9


def corpus_shrank(corpus: Corpus, prev_corpus: Corpus | None) -> bool:
    """True when the corpus lost material ground against the previous census."""
    if prev_corpus is None or prev_corpus.lines_read <= 0:
        return False
    return corpus.lines_read < prev_corpus.lines_read * _CORPUS_SHRINK_RATIO


def _describe(corpus: Corpus) -> str:
    return (
        f"{corpus.file_count} files, {corpus.lines_read} lines read, "
        f"{corpus.signal_lines} signal lines"
    )


def render_provenance(corpus: Corpus, prev_corpus: Corpus | None) -> list[str]:
    """The measurement-basis block rendered above the table.

    States what the counts were computed over, what the previous sweep was
    computed over, and — when those two differ materially — that the novelty
    and delta columns cannot be compared across them.
    """
    if prev_corpus is None:
        tail = (
            "No census was recorded for the previous sweep, so this week's "
            "Δ / 🆕 rest on a snapshot of unstated basis."
        )
    else:
        tail = f"Previous sweep: {_describe(prev_corpus)}."
    out = [f"_Corpus this sweep: {_describe(corpus)}. {tail}_", ""]
    out.append(
        "_Counts have no time window: each is the total over the file's whole "
        "current contents, and those files rotate on different schedules, so "
        "two rows may span very different periods._"
    )
    if corpus_shrank(corpus, prev_corpus):
        assert prev_corpus is not None  # corpus_shrank is False when it is None
        # Floor, not round: 99.96% rounds to "100%", which reads as an empty
        # corpus when four lines are still there. Understate the shrink.
        pct = int((1 - corpus.lines_read / prev_corpus.lines_read) * 100)
        out.append("")
        out.append(
            f"_⚠️ The corpus shrank {pct}% against the previous census — lines "
            "left the `*.log` glob (rotation), so 🆕 and Δ this week are not "
            "comparable to last week's._"
        )
    out.append("")
    return out


def render_markdown(
    findings: list[Finding],
    top: int,
    corpus: Corpus,
    prev_corpus: Corpus | None = None,
) -> str:
    """Render the ranked findings as a Markdown section.

    ``corpus`` is required: the numbers below are uninterpretable without the
    basis they were computed over, so there is no rendering that omits it.
    ``prev_corpus`` is genuinely optional (the first sweep has none) and its
    absence is stated in the output rather than passed over.
    """
    lines = ["## Log Anomaly Sweep", ""]
    lines.extend(render_provenance(corpus, prev_corpus))
    if not findings:
        lines.append("No anomaly-signal lines found in `*.log` / `audit.jsonl`.")
        return "\n".join(lines) + "\n"
    new_count = sum(1 for f in findings if f.is_new)
    lines.append(
        f"{len(findings)} distinct anomaly types "
        f"({new_count} new since last sweep). Top {min(top, len(findings))} "
        f"by novelty then frequency delta:"
    )
    lines.append("")
    lines.append("| New | Count | Δ | Signature (normalized) | Origin |")
    lines.append("|----|------|----|------------------------|--------|")
    for f in findings[:top]:
        flag = "🆕" if f.is_new else ""
        # Neutralize Markdown breakers so a signature cannot break out of its
        # code span in the downstream LLM prompt. The origin column is built
        # from the same untrusted line, so it is escaped the same way.
        sig = md_safe(f.signature)
        origin = md_safe(", ".join(f.origins)) if f.origins else "—"
        lines.append(f"| {flag} | {f.count} | {f.delta:+d} | `{sig}` | {origin} |")
    lines.append("")
    lines.append(
        "_Signatures are normalized (timestamps and module paths stripped, "
        "digits and ids squashed). Origin is display-only — it does not enter "
        "the signature, so a module rename cannot reset the Δ / 🆕 baseline, "
        "and one row may list several subsystems emitting the same message. "
        "Source: self-written logs only; episode logs are never read._"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, required=True, help="MOLTBOOK_HOME/logs")
    parser.add_argument("--state", type=Path, required=True, help="sweep state TSV path")
    parser.add_argument("--top", type=int, default=25, help="rows to render (default 25)")
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="do not write the state file (dry sweep)",
    )
    parser.add_argument(
        "--emit-state",
        type=Path,
        default=None,
        help="write the snapshot to this path instead of committing it; pair "
        "with --no-update so the caller can promote it (atomic rename) "
        "only after the work this sweep fed has actually succeeded. The "
        "corpus census sidecar (PATH.corpus.tsv) is emitted alongside and "
        "must be promoted in lockstep",
    )
    args = parser.parse_args(argv)

    prev = read_state(args.state)
    prev_corpus = read_corpus(corpus_state_path(args.state))
    census: list[FileCensus] = []
    findings = analyze(iter_allowed_log_lines(args.log_dir, census), prev)
    corpus = Corpus(tuple(census))
    print(render_markdown(findings, args.top, corpus, prev_corpus))
    # The census is written *before* its state snapshot in both pairs: the
    # caller treats the snapshot's existence as "the sweep ran to completion"
    # (weekly-analysis.sh promotes on `-e $SWEEP_PENDING`), so the snapshot
    # must stay the last file to appear.
    if not args.no_update:
        write_corpus(corpus_state_path(args.state), corpus)
        write_state(args.state, findings)
    if args.emit_state is not None:
        write_corpus(corpus_state_path(args.emit_state), corpus)
        write_state(args.emit_state, findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
