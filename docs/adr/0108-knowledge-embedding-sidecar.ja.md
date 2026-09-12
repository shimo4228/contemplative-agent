# ADR-0108: パターン埋め込みを knowledge.json から出す — pattern id を鍵にした SQLite sidecar

## Status

accepted

## Date

2026-09-12

## Context

`knowledge.json` は値層の観察面であり、パターン本文・provenance・双時間有効性を
持つ。同時に、重さで見ればほぼ埋め込みファイルである。2026-09-12 に live store
（`$MOLTBOOK_HOME/knowledge.json`、8,467 行、全行が 768 次元ベクトルを持つ）へ
read-only で再計測した:

| 読み値 | 値 |
|---|---|
| ファイルサイズ | 188,944,061 B (180 MiB) |
| 同じ行を `embedding` 抜きで直列化 | 5,990,535 B — **3.17%** |
| `KnowledgeStore.load()` の実時間 | **11.36 s** |
| ├ `read_text` | 1.24 s |
| ├ `json.loads` | 1.91 s |
| └ `first_forbidden_substring` 走査 | **8.06 s** |
| 素の `load()` のピーク RSS | **1,640 MB** |

このうち 2 つは RFC-0031 の記録（load 4.8 s、ピーク ~700 MB、走査 0.77 s）より
**悪い**。差は走査にある。`knowledge_store.load` の汚染検査はファイル**全体**へ
compiled alternation をかけるが、その 97% は禁止文字列に決してマッチしない数字の
羅列である。RFC の前提は無傷どころか過小評価だった — Ollama と同居する 16GB の機体
で、値層を 1 回読むだけでピーク 1.6GB、うち 8 秒はベクトルに prompt-injection 文字列
を探すことに費やされている。

ベクトルは代替不能ではない。`nomic-embed-text` にモデル固定で、隣に置かれた
パターン本文から再導出でき、2 つの export 境界（`scripts/export-patterns-jsonl.py`、
`backup-runtime.sh` と `sync-research-data.sh` の両方から到達）は既にこれを落として
いる — つまりこのプロジェクトは、公開を拒否しているデータの保存・parse・走査に
コストを払い続けてきた。

sidecar には repo 内の前例がある: `core/episode_embeddings.py` は episode / post の
ベクトルを `embeddings.sqlite` に置き、JSONL の監査証跡をテキストのまま保っている。

## Decision

### D1 — SQLite blob sidecar、鍵は ADR-0050 の pattern id

`core/pattern_embeddings.py` が `PatternEmbeddingStore` を持つ。`knowledge.json` の
隣の SQLite ファイル `pattern-embeddings.sqlite` に 1 パターン 1 行:
`(pattern_id TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL)`、blob は
生の `float32` バイト列。鍵は `knowledge_store.pattern_id(p)` — `distilled|pattern`
の既存の content hash（ADR-0050）— なので、sidecar は新しい同一性も JSON 側の id
フィールドも要さない。

形式は好みでなく実測で決めた。live の形（8,467 × 768 `float32`）で両案を計測:

| | write | read all | bytes |
|---|---|---|---|
| SQLite blob | 0.134 s | **0.018 s** | 34,963,456 |
| `.npy` + id リスト (mmap) | 0.008 s | **0.014 s** | 26,146,224 |

11.36 秒の予算に対して、効く側の read は 4 ms 差。時間が並んだ以上、決め手は前例で
ある — repo 内の blob store の書き方を 2 つでなく 1 つに保つ。`.npy` 行列は本 ADR の
Decision の残りが費やされる性質でも負ける: 密行列と並走する id リストという構成上、
**毎回の save がファイル全体を書き直し**、id リストという 2 つ目のずれうる面を持つ。
`INSERT OR REPLACE` は増分で、鍵は行の中にある。

`float16` は RFC-0031 の理由（実測で置いた `SIM_DUPLICATE` / `SIM_UPDATE` の較正を
無効化する）で却下のまま。ディスク上の幅は、ベクトルが既に持っている幅そのもの:
保存済み 8,467 本すべてが bit-exact な `float32` 値である（2026-09-12 検証 — 全行が
`float64 → float32 → float64` を不変で往復する）。書き手がいずれも `float32` 配列を
返す `embed_texts` からベクトルを得ているためである。したがって sidecar の往復は
**無損失**で、cosine の結果は「ほぼ同じ」ではなく bit-identical になる。

### D2 — メモリ上のパターン dict は変えない

`KnowledgeStore.load()` は各行のベクトルを `entry["embedding"]` に `list[float]` として
戻す。ファイルがかつて持っていたのと全く同じ形である。このフィールドの消費者 —
`pattern_dedup._live_embedded`、`views.find_by_view`、`clustering`、`view_metrics`、
`insight_surprise`、`insight`、`constitution` — はどれも無変更で、効く回帰（移行前後で
cosine の判定が同じ）はレビューでなく**構成上**真になる。

これは本変更の意図的な限界である: sidecar は*永続化*の決定である。1.6GB のピークは
JSON の parse（180 MiB のテキストとその一時的な float グラフ）で叩いており、常駐表現を
遅延化することでは叩いていない。遅延化は 9 箇所の呼び出し元に対して dict の契約を一度に
変える — 常駐コストが律速になったときに別途提案できる。

### D3 — 2 つのファイルと、片方しか無い状態

store は 2 ファイルになったので、復元が半分だけを作りうる。load 経路は各半状態を、
黙って劣化させる代わりに理由コードで名指しする
（`core/pattern_embeddings.SidecarConsistency`、集計 WARNING として記録され
`scripts/state_invariant_check.py` が読む）:

| 理由コード | 状態 |
|---|---|
| `inline_legacy` | JSON がまだ inline ベクトルを持つ — 移行前のファイル。そのまま使い、次の `save()` で sidecar へ移す |
| `sidecar_absent` | JSON に行があるが sidecar ファイルが無い — backup からの復元直後の通常状態 |
| `sidecar_unreadable` | ファイルはあるが読める DB でない — 中断した restore。raise でなく名指しにする: 1 つの壊れたファイルで無人の `load()` が毎回落ちてはならない |
| `row_missing` | sidecar はあるがこの pattern id のベクトルが無い — 再導出候補 |
| `dim_mismatch` | 保存幅が支配的な幅と異なる — 再 backfill 無しの埋め込みモデル変更。`cosine` に渡せば 0.0 が返るだけなので、行は未埋め込みのまま残す |
| `orphan_vectors` | どの live 行も主張しない id を sidecar が持つ — 無害、計数し、要求時に刈る |

2 つの不具合は 7 箇所の read 側でなく*書き込み*境界で捕まえる: 非数値の `embedding`
（壊れた legacy 行）は raise せず WARNING で skip する — raise させると 1 行の破損が store
全体の save を止めるため。非有限のベクトル（`np.asarray([None, None], dtype=float32)` は
raise せず NaN を返す）も同様に skip する — NaN ベクトルはそれに対する全 cosine を無意味に
するため。どちらの行もテキストとしては残り、`row_missing` として読み戻る。

ベクトルを得られなかった行は `embedding` キーを持たない。これは全消費者が既に扱える形
（skip し `skipped` に計上する）であり、かつコードの下で計数される。
`scripts/state_invariant_check.py` の `missing_embedding` 不変条件は sidecar にも問う
ようになったので、移行後の store が 8,467 件の未埋め込みを報告することはない。

**contention は loud に、damage は名指しに。** どちらも `sqlite3.Error` として来るが、
必要な答えは逆である。壊れたファイルは「ベクトル無し、全行が再導出候補」へ degrade する —
それが上の `sidecar_unreadable` である。一時的なロックは**同じように degrade させてはならない**:
dedup と view は未埋め込み行を skip するので、distill 1 回分がベクトル 0 本で走り、重複を
再追加し、view は何も返さず、証拠は WARNING 1 行だけになる。したがってロック由来のエラーは
伝播させ、接続は 30 秒の busy timeout を持つ（Python の既定は 5 秒）— sidecar は、store が
以前は atomic rename 1 回で失うものが無かった場所に、ロックを持ち込むためである。`dim` 列は
読み戻して blob の実幅と照合する。これにより切り詰められた書き込みが、正当に狭いベクトルと
取り違えられずに damage として捕まる。

**knowledge の save 失敗が他の 2 ファイルを飛ばさないようにした。**
`MemoryStore.save()` は knowledge / follow state / comment ledger を書き、knowledge が最初である。
以前は contention で失敗しえない atomic rename 1 回だったが、いまは失敗しうる。よってエラーを
捕捉し、残り 2 つを書いてから re-raise する（呼び出し元は save が不完全だったことを依然知る）。

**parser が読めない行は「拒否」であって「削ぎ落とし」ではない。** `_parse_json` はパターン行
でない配列要素を黙って落としていた。全書き手が逐語往復だった間は無害だったが、`save()` は
配列全体を書き直すので、そうした行は次の書き込みで**削除**される。件数を
`KnowledgeStore.dropped_rows` として露出し WARNING を出し、両オペレータ script は非ゼロなら
書き込みを拒否する — 本番データに向けられる script であり、別のものを埋め込むついでに行を
削ぎ落とすのは、この変更が黙って行ってよい取引ではない。

**書き順は sidecar が先、JSON が後。** sidecar の書き込みが失敗すれば JSON は無傷で
旧状態が残る。sidecar 成功後に JSON が失敗すれば、sidecar は JSON がまだ名指していない
行のベクトルを持つ — orphan であり、計数され無害である。逆順は「どこにもベクトルの無い
JSON」を作りうる、つまりデータ損失になる。既存の `_load_failed` 拒否（失敗した load は
populated なファイルへ `[]` を保存してはならない）はそのままで、いまは sidecar 書き込みも
守る。

### D4 — 移行は load/save 経路そのもの、script として 1 度だけ露出する

新しい CLI コマンドは作らない: ADR-0035 が一回限りの migration コマンドという**類**を
退役させており、2 つ目のコード経路は 2 つ目の正しさの維持対象になる。後方互換読み込み
（D3 の `inline_legacy`）が**移行そのもの**であり、store を load して save する実行は
すべて自動的に upgrade する。`scripts/migrate-knowledge-sidecar.py` は、本番切り替えを
する人間にとってそれを意図的で報告可能にするためだけに存在する
（`docs/runbooks/knowledge-embedding-sidecar-migration.md`）。中身は
`KnowledgeStore.load()` → `save()` と前後のサイズ表示だけである。

### D5 — sidecar は backup も sync もしない

`backup-runtime.sh` と `sync-research-data.sh` は両方 `pattern-embeddings.sqlite*` を
除外する。理由は既に inline ベクトルを除外しているのと同じ: 25–35 MB の再導出可能な
バイナリが、毎週書き換わって git repo に入る。復元経路は形として不変 — mirror を復元し
`scripts/restore-embed-knowledge.py` を走らせる。これが JSON でなく sidecar へ書くように
なっただけである。両 script の除外は厳密な basename なので、既存の `embeddings.sqlite`
の行は新しい sidecar 名を**覆わない**。追加は整頓でなく機能上必須である
（`sync-research-data.sh` は**公開** repo へ push する）。

**末尾の `*` は規則の一部**であり、その厳密 basename 規律への唯一の意図的例外である。
SQLite は既定の `journal_mode=delete` で動くので、save の最中は
`pattern-embeddings.sqlite-journal` が旧ページを保持する（500 行で 2 MB 実測 =
live store なら ~35 MB）。かつ `sync-research-data.sh` は `.run.lock` を取らないため、
スケジュールされた distill のトランザクション中に rsync しうる。厳密 basename では、
この境界が剥がすために存在するベクトルそのものを公開 repo の history へ入れることになり、
`--delete` では取り消せない（security review、2026-09-12。回帰は
`tests/test_backup_runtime_shell.py`）。journal mode が変わった場合の `-wal` / `-shm` も
同じ `*` が覆う。

episode store 側の `--exclude='embeddings.sqlite'` にも同一の欠落があり（同じ journal mode の
SQLite ファイルで、同じ script の 1 行上）、本変更のレビュー中に著者判断で
`embeddings.sqlite*` へ広げた。2 つの規則は重ならない: rsync は slash を含まない pattern を
basename 全体に固定するので、`embeddings.sqlite*` は `pattern-embeddings.sqlite` に
マッチしない（2026-09-12 検証）。だから両方が要る。対は
`tests/test_sync_research_data_shell.py` が実 transfer で固定する。

### D6 — dedup のベクトル化は本変更に含めない

RFC-0031 は `_argmax_cosine` のベクトル化（0.25 s → 0.009 s）を相乗り候補として挙げた。
live の形で再計測すると、8,467 候補に対するスカラーループは **0.020 s** であり 0.25 s
ではない。主張された削減はこのサイズでは存在せず、変更は cosine の判定が計算される
唯一の場所に触れる — D2 が証明可能に不変へ保とうとしているまさにその場所である。やらない。

## Review-when

- 移行後の（テキストのみの）`knowledge.json` 自体が ~50 MB を超える、または sidecar が
  小さい方の半分でなくなる — 分割を動機づけたサイズ論はそのときテキストについての話に
  なり、別の分割が要る
- 埋め込みモデルの幅が変わる: 保存済み全ベクトルが一斉に `dim_mismatch` になり、移行 /
  backfill の問いが再埋め込みの問いとして開き直る
- 常駐 float list のコスト（D2 の意図的な限界）が JSON parse でなく律速のメモリ制約に
  なる — そのとき D2 で却下した遅延 hydration 案が再び候補になる
- 2 つ目の消費者が per-pattern lookup でなく**行列**を要する（ベクトル化 dedup、ANN
  index）— D1 の決め手は同点処理であり、行列の消費者はそれを逆へ倒す

## Alternatives Considered

- **何もしない。** 今も動く。コストは値層を 1 回読むごとに 11 秒と 1.6GB、それも Ollama
  が同居する機体で。加えて、strip を忘れた経路があれば GitHub の 100 MB 上限へ向かう
  180 MiB のファイルが残る。却下: コストは毎週払われ、データは再導出可能である。
- **`.npy` 行列 + id リスト。** read が 4 ms 速く 8.8 MB 小さく、将来のベクトル化 dedup
  を無料にする。D1 の決め手で却下: 並走する id リストは 2 つ目の整合面であり、毎回の
  save が行列全体を書き直し、D6 が示した通りそれが可能にするベクトル化はこのサイズでは
  何の価値も無い。行列の消費者が現れたら再開する項目として Review-when に載せた。
- **`knowledge.json` を圧縮する (gzip)。** 両端に CPU を足し、常駐コストには触れない —
  parse は依然 float グラフ全体を作る。
- **`float16` ベクトル。** sidecar が半分になるが、実測で置いた `SIM_DUPLICATE` /
  `SIM_UPDATE` 閾値を無効化する。再較正のコストが 17 MB の節約を上回る。
- **遅延 hydration（ベクトルはクエリ毎に取得、常駐しない）。** 常駐コストを叩く唯一の案。
  *今回は*却下: 保存形式を動かすのと同じ変更で 9 消費者の `entry["embedding"]` 契約を
  変えるため、回帰が起きたとき原因候補が 2 つになる。今回は D2 の bit-identical 性の方が
  RSS より価値がある。
- **明示的な `migrate-*` CLI コマンド。** ADR-0035 が `embed-backfill` /
  `migrate-patterns` / `migrate-categories` を**類として**退役させた。4 つ目はそれを
  開き直す。`scripts/` の script は同種の運用ツールである `restore-embed-knowledge.py`
  に倣う。

## Consequences

**良くなること。** live store の**複製**（8,467 行、2026-09-12。本番 home には触れて
いない）で end-to-end 実測:

| | before | after |
|---|---|---|
| `knowledge.json` | 180.2 MiB | **5.7 MiB** |
| sidecar | — | 33.3 MiB |
| `KnowledgeStore.load()` | 15.50 s | **0.56 s** |
| その load のピーク RSS | 1,206 MB | **403 MB** |
| 実クエリ 50 本 × live 7,950 ベクトルでの `_argmax_cosine` の判定 | — | **bit-identical** |

値層が再び ~6 MB のテキストファイルになる: 読める、grep できる、diff できる、汚染検査が
安い。最も効くのは毎週の無人チェーンで、`state_invariant_check.py` は同じファイルを
読むだけでピーク 1.5 GB を使っていた。`export-patterns-jsonl.py` の strip
は legacy ファイルのためだけに残る no-op になり、両 sync script が守っている
「180 MiB のファイルを git remote へ絶対に届かせない」という危険が、源から消える。

**悪くなること。** store が 2 ファイルになる。backup、restore、sync、snapshot、dialogue
peer 用の `MOLTBOOK_HOME` の複製 — あらゆる運用手順が 2 つ目を考える必要を持つ。D3 の
5 つの理由コードは、半状態を黙らせず可読にするための代価である。backup から復元した
store は `restore-embed-knowledge.py` を走らせるまで**正しいが未埋め込み**である。これは
元から真だった（mirror は常に embedding-free だった）が、失敗がもう 1 箇所で見えるように
なった。

**全く変わらないこと。** cosine の判定、閾値、較正、`entry["embedding"]` の全消費者。
それが D2 の目的そのものであり、近似ではなく bit-exact な主張である（D1）。
