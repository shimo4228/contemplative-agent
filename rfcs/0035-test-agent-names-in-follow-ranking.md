---
state: draft 2026-09-12
review-when: テスト側が exclude 引数で fixture 名を渡す形に移れば、この定数は消えて本 RFC も終わる
---

## Summary

`InteractionIndex._TEST_AGENT_NAMES`（`Agent0..Agent4`, `Bob`, `TestAgent`,
`Agent1 Updated`）が production の follow 候補ランキングの中で除外に使われている。

## Motivation

除外リストの中身はテスト fixture の名前で、`top()` —— 実際の follow 候補ランカー —— が
それを読んでいる。同じメソッドの 1 行上には `exclude_ids` という汎用の除外口があり、
self 除外に使われている。

さらにこの集合は 2 つの異なる規則を 1 つに混ぜている:
`"unknown"` は production のセンチネル（`CommentLedger` が同じリテラルで guard している）、
残りはテストのノイズ。

## Guide-level explanation

fixture 名はテスト側から渡す。production の定数には `"unknown"` センチネルだけを残し、
それも `CommentLedger` と同じ共有定数を引く。

## Reference-level explanation

- `_TEST_AGENT_NAMES` から fixture 名を削除
- テストは既存の `exclude_ids`（または新設の `exclude_names`）で渡す
- `"unknown"` のドロップは `top()` に残すが、リテラルではなく共有センチネルを参照する

## Drawbacks

挙動が変わる: 実在のエージェントが `Bob` や `TestAgent` を名乗っていた場合、これまで
ランキングから落ちていたのが落ちなくなる（本来の意図はそちらのはず）。

## Status

draft — 2026-09-12 の simplify 走査（core memory 群の altitude レビュー）で同定。
挙動変更を伴うため simplify の範囲からは外して起票した。

## Next action

fixture 名を渡す口（`exclude_ids` 流用か `exclude_names` 新設か）の決定。
