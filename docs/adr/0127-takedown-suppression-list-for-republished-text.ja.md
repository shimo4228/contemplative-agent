# ADR-0127: 再掲した第三者テキストを撤回するための抑止リスト

## Status

accepted

## Date

2026-10-24

## Context

公開 data repo は他のエージェントとその運用者の文章を再掲している。日次 comment report の `**Context:**` ブロックと、report 見出し・週次分析・一部の pattern 行に出る表示名である。これまで、何を根拠に再掲しているか、どうすれば除去や訂正を頼めるかは書かれておらず、頼まれても実行する経路がコードに無かった。夜間 sync は私的 store から公開 tree を `rsync --delete` で書き直すので、公開 repo で手で消した行は翌朝戻る。

決定 D-P3-05-2（オーナー、2026-10-24）はロードマップの A + E を採った。再掲の根拠と受付経路を明記し（A）、依頼の実行を抑止リストで行う（E）。

## Decision

1. **識別子だけを並べる抑止リスト。本文は書かない。** `config/takedown-suppressions.txt`（公開、空で出荷）と、任意の私的 `$MOLTBOOK_HOME/takedown-suppressions.txt` に 1 行 1 件: `post:<id>`（全桁、または report 見出しに出る先頭 8 文字）、`name:<表示名>`、`pattern:<pattern_id>`、`file:<相対パス>`。リストが空なら挙動は変わらない。
2. **適用箇所。** `core.report` は、リストにある post の Context と、リストにある相手の名前を `[withdrawn]` で描画する。エージェント自身の `Internal note` と `Output` は残る。`scripts/export-patterns-jsonl.py` は、`pattern:` に挙がった行と、本文が `name:` を単語として含む行を、両方の公開形式から外す。`file:` は sync 段のためのもので、`scripts/sync-research-data.sh` への配線は共通の除外 helper（ロードマップ P0-03.2/.3）を待つので本変更に含めない。
3. **黙って落ちない。** parser が理解できない行は例外にして（`TakedownListError`、単体 script では `SystemExit`）、report 生成と export を止める。適用されない撤回は、除去を頼まれた内容をそのまま再公開してしまう。
4. **私的台帳。** 依頼は `$MOLTBOOK_HOME/takedown-requests.jsonl` に、`received, surface, target, decision, actioned, basis` の欄だけで記録する（識別子のみ）。公開側は件数だけを書く（`core.takedown.ledger_count_line`）。受付文面は data repo（`NOTICE`、`DATACARD.md`）にあり、4 面で同一にする。
5. **既に公開した分。** 公開済みの文章への依頼は、sync を止めた maintainer の checkout で一度だけ手で実行する。面ごと（git 履歴・fork・Hugging Face・Zenodo 版・Software Heritage）に何を消せて何が残るかは、`NOTICE` の到達範囲表に書く。

## Consequences

- 除去の依頼が翌日の sync で戻らなくなる。report と pattern では今回から、file は sync 配線が入ってから。
- 照合は意図的に単純にした（識別子の一致、名前は大文字小文字を畳んだ単語一致）。他者について書いた pattern の中に名前が出ていても外れる。リストは外す側に倒れる。
- 承認ログの source への `takedown` の追加はここでは行わない。監査記録の拡張（ロードマップ P1-12.5）までは、適用は report ログの INFO 行、export の stderr の件数、台帳の行として見える。
- リストが comment report に効くのは report が書かれるときだけ。過去日の report は書かれた状態のまま sync されるため、`post:` / `name:` を足したら運用者が `contemplative-agent generate-report --all` を実行する（その日の episode JSONL が残っている間だけ有効。残っていなければ `file:` 項目と決定 5 の手作業による削除を使う）。
- 照合の対象は `Context` ブロックと相手の名前。エージェント自筆の `Internal note` / `Output` が撤回対象の名前を引用していることがあり、その評価文の削除はリストの仕事ではなく report の手編集になる。
- 新しい I/O 面も権限も足さない。読むのはローカルの 2 ファイルだけ。

## Decided by

proposed-by: Claude Code session
decided-by: owner (D-P3-05-2 = A + E)
date: 2026-10-24

## Layer

mechanism

## Review-when

sync に共有 exclude helper が入って `file:` 項目が配線されるとき、`AuditSource` に `takedown` 値が加わるとき、または最初の実請求で識別子照合が拾うべきものを取りこぼしたと分かったときに再検討する。

## Related

- [ADR-0010](0010-research-data-sync.ja.md) — このリストが生き残らなければならない sync
- [ADR-0075](0075-observability-by-default.ja.md) — 常駐経路の監査・リプレイの義務
