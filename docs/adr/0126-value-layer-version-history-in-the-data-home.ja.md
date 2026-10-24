# ADR-0126: 価値層の版履歴は data home に置く

## Status

accepted — ADR-0030 を部分的に supersede

## Date

2026-10-24

## Decided by

proposed-by: Claude Code セッション（roadmap 前倒し束 P3-04）
decided-by: オーナー（D-P3-04-1 = C）
date: 2026-10-24

## Layer

mechanism

## Context

`identity.md` と憲法は採用時にその場で置き換わる。本 ADR の前は、過去の版の写しは
pivot snapshot（ADR-0020）の run 開始時コピーだけで、その窓（100 枠）は日次の
`distill` に押し出されていた（今回 ADR-0020 の追補で種類別に直した）。もう 1 つの
手がかりである私有の `audit.jsonl` は hash を持つが本文を持たない。公開 data 木には
採用された版を時系列に並べたものが無かった。採用された identity 6 版のうち公開
snapshot に残るのは 3 版（694 / 894 / 954 B。4 つ目の 971 B は現行ファイル）、
憲法の第 2 版（2026-03-27）は report の引用以外に木のどこにも無い。

ADR-0030 は ADR-0025 の per-block history 配線を撤回し、理由の 1 つに「pivot snapshot
と `audit.jsonl` で identity の全文 replay は既に足りる」（Context 3）を挙げた。
その議論は `identity.md` の*内部*の block 粒度の履歴についてのもので、ファイルの
外にある公開の版ごとの記録には及ばない。しかも snapshot の半分は上の理由で
成り立たなくなっていた。ADR-0010 は `history/identity/*` を同期対象に挙げていたが、
それを作る処理は無かった。

## Decision

1. **採用時に、採用された版の逐語コピーを `$MOLTBOOK_HOME` の下に書く。** identity は
   `history/identity/<UTC ts>-<sha12>.md`、憲法は
   `constitution/history/<UTC date>-<sha12>.md`。中身は採用されたバイト列そのままで
   何も足さないので、`sha256(file)[:12]` は名前の末尾と、その時点の live ファイルの
   hash に一致する。書き手は `core/value_history.py` で、書き込み経路 2 つ
   （`adopt-staged` と `_handle_single_result` の直接承認）から、正規ファイルを
   置き換えた書き込みのときだけ呼ばれる。
2. **data repo だけでなく data home に置く。** `sync-data` は home を `--delete` 付きで
   rsync するので、repo にだけ置いたファイルは次の実行で消える。憲法ローダーと
   snapshot のコピーはどちらも `constitution/*.md` を平坦に読むので、サブフォルダは
   注入文にも snapshot の中身にも影響しない。
3. **best-effort で、止めない。** コピーを作る時点で採用の書き込みと audit は済んで
   いる。失敗は warning に記録し、採用を巻き戻さない。同名（同じ日・同じバイト列）の
   ファイルが既にあれば触らない。
4. **それ以前の版は 1 回だけ種まきする。** writer より前の版は
   `docs/evidence/value-history/seed/` にあり、`cp -Rn`（上書きなし）で home に
   適用する。遡及ファイルの名前にはその本文を持つ最初の snapshot の時刻が入り、
   これは採用時刻の上限である。2026-03-27 の憲法は amendment report の引用からの
   再構成で、先頭にそう明記し、hash は不明。公開 snapshot に無い identity の版と
   採用版の全数は、私有の audit log とオーナーの端末が要る。
5. **憲法の各版にセクション → technique の写像を添える。**
   `constitution/history/lineage.json` は版ごとに、セクション名で決めた
   `technique_key`（名前がどれにも合わなければ `null`）つきでセクションを記録する。
   per-axiom の系列が `Emptiness` -> `Emptiness & Flow` を追え、対応の無い
   セクションを外せるようにするため。同じ呼び出しで書かれ、憲法本文に対しては
   read-only（`core/constitution_lineage.py`）。`graph.jsonld` の 4 つの axiom node には
   論文の `version` とそのファイルへの `productionVariant` リンクが付く。
6. **ADR-0030 に対する範囲。** 本 ADR が supersede するのは、ADR-0030 の「snapshot と
   audit があるので版ごとの identity 記録は不要」という議論と「履歴なし」の終状態
   だけ。ADR-0024 / ADR-0025 の撤回は全体として有効のまま: block スキームも
   `identity.md` 内の sub-addressing も無く、1 ファイル 1 関心。履歴ファイルは
   自分のディレクトリに置く全文コピーで、独自の記録を要する関心は独自の場所に
   置く、という ADR-0030 が示した形に当たる。

## Review-when

3 つ目の価値層ファイルが採用時にその場置換されるようになったとき、公開木が home の
同期でなくなったとき、または履歴が保持規則を欲しがる大きさ（identity で 1 採用
約 1 KB）になったとき。

## Consequences

### Positive

- 公開 data repo の clone だけで、採用された憲法・identity の全版が時系列に並び、
  それぞれ ADR-0090 の provenance と live ファイルの hash で確かめられる。
- `constitution/history/CHANGELOG.md` と lineage 表は、shallow clone では辿れない commit
  の発掘でなく、ファイルを指せる。

### Negative

- 各版の写しが 2 つになる。採用ごとに数 KB。
- 履歴は来歴（誰が・どの経路で）を持たない。それは私有の audit log に残り、読める
  台帳は CHANGELOG である。

## References

- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — 部分的に supersede（Context 3 の議論のみ）
- [ADR-0020](0020-pivot-snapshots-for-replayability.ja.md) — run 開始時コピーと、種類別保持の追補
- [ADR-0010](0010-research-data-sync.ja.md) — `history/identity/*` を挙げた同期
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md) — 履歴を照合する hash
