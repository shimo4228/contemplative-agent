# TASKS — fixture: the pre-migration dialect

Migration input, frozen. Body pipes sit **bare inside backtick code spans**,
which is not valid GFM — a renderer reads them as extra columns — but is what
the real table contained on 2026-08-15 and what `split_row(legacy=True)` exists
to read.

`T-WRITE-TMP-NOFOLLOW` is a copy of the real row that split into 8 cells
instead of 5. Do not "fix" its pipes: the malformed shape is the assertion.

`T-EFFECT-NOISE` carries the other real problem row — `|Δ効果|` as
absolute-value notation — in its **hand-fixed** form, escaped. Escaping is what
the operator had to do before the one-shot migration would run, because the
legacy dialect hides pipes inside code spans only, and that one sat in plain
prose. The raw shape is asserted inline in `TestLegacyFixture` instead: it must
raise `MalformedRow`, since that refusal is what forced the hand fix rather
than a silently shredded body.

## Pending

| ID | 状態 | タスク | 着手条件 | 詳細 |
|----|------|--------|----------|------|
| T-WRITE-TMP-NOFOLLOW | done 2026-08-01 | 固定名の tmp を `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` で開く | — | `abc1234` |
| T-EFFECT-NOISE | observing | 解釈規約: \|Δ効果\| < 0.13 はノイズとして読まない | 4 週分の読み値 | [ADR-0071](../../../docs/adr/0071-read-only-pattern-composition-instruments.md) |
| T-UPSTREAM-PR | blocked | 上流の修正待ち `watch: gh-pr example/example#1` | PR が閉じるまで | `scripts/ledger_condition_scan.py` |
| T-PLAIN | ready | 素の行。エスケープも code span も無い | なし | — |
