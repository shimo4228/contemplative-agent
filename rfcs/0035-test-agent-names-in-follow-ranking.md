---
state: accepted 2026-09-12
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

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持（同日の simplify 走査で起票、premise は起票時点の main で検証済み）。採否は著者判断（digest に提示）。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。S11 として dispatch（RFC-0030 と同梱、worktree `task/s11-small-fixes`）。fixture 名はテスト側の除外引数へ、`"unknown"` は共有センチネル。

## 2026-09-12 build（S11、worktree `task/s11-small-fixes`）

Next action の決定: **`exclude_names` は新設しない。既存 `exclude_ids` で足りる。**

呼び出し側を数えた結果 — production の `top()` 呼び出しは 1 経路のみ
（`adapters/moltbook/agent.py:651` → `core/memory.py:255` → `InteractionIndex.top`）。名前ベースの
除外に依存していたテストも 1 件のみ（`test_memory.py::test_top_still_filters_test_names`）。
他の fixture 名利用箇所は `get_top_interacted_agents` 自体を stub していて実フィルタを通らない。

テストは自分が seed した id を知っているので `exclude_ids` で除外できる。名前キーの引数を production
API に足すのは、まさに今回取り除いている欠陥（テスト都合が production のランキングに埋まる）と同じ形。

`"unknown"` は module-level `UNKNOWN_AGENT_NAME` に一本化し、`InteractionIndex.top` と
`CommentLedger` の両方がそれを引く。挙動変更（`Bob` / `TestAgent` を名乗る実在 agent がランキングに
残る）は `test_top_ranks_an_agent_whose_name_looks_like_a_fixture` で固定した。
