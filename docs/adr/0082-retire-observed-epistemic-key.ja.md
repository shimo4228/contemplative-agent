# ADR-0082: `observed` エピステミックキーの退役 — 警告ではなく死んだフィールドを消す

## Status

accepted — partially-supersedes [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md)

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) を部分的に supersede する
（`epistemic_counts` のスキーマと、read-time derivation の `external_reply` → `observed` の枝）。
ADR-0050 の lineage plumbing・no-write-back・never-persisted の各決定は引き続き有効。

## Date

2026-07-25

## Context

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) は read-time の
epistemic derivation を導入した。パターン行の `provenance.source_type` を epistemic kind に
マップし、`epistemic_counts_for()` が `{observed, generated, unknown}` に集計する。この tally は
`source_ids` とともに承認系譜として `audit.jsonl` と `.staged/*.meta.json` に流れる。

その後 [ADR-0060](./0060-per-episode-grounded-distill.ja.md) が蒸留の取り込みを `activity`
レコードのみに絞った。activity は全て `self` → `self_reflection` → `generated` にマップされる。
`external_reply` を生む唯一の producer である `episode_render.py` の `_derive_source_type()`
（`interaction`/`received` レコードを要求する）は、稼働中の取り込み経路から**到達不能**になった。
以降 `observed` は**構造的に常時ゼロ**である。

これは気付かれ、記録もされていた。[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md)
の M2 レビュー（2026-06-27）は、`observed == 0` が「外部 grounding が無い」と読まれてしまうが
実際はそういう意味ではない、と記録している — 外部コンテンツは rich render の**中の** grounding
テキストとして蒸留に入っており、この tally は最初からそれを数えていない。`epistemic_counts_for()`
と `_log_approval()` の docstring に警告が追加された。
[ADR-0072](./0072-echo-chamber-interventions.ja.md) はこの定数を読んでいた grounding **計器**を
削除したが、`epistemic_counts_for()` 自体は意図的に残した — 下流に読み値の消費者がおらず、
定量化しても行動が変わらないため、signal-first で修理を保留した。

保留は 4 週間もち、そして保留された修理が壊れる典型的な形で壊れた。2026-07-25、週次 `insight`
run が staging した 78 件の skill をレビューする際、エージェントが staged `meta.json` から
`epistemic_counts` を読み、78 件全体で `observed=0, generated=324` と集計し、**staged skill は
全て外部 grounding のない echo である**と結論した。M2 が予測した通りの誤読である。

docstring の警告はこれを防がなかった。**警告が値より先に読まれる保証が無い**からである。
値はデータファイルにあり、警告はそれを生成したコードの中にある。

監査履歴全体（tally を持つ 405 レコード）での集計:

| command | observed | generated | unknown |
|---|---:|---:|---:|
| `insight` | **0** | 1,618 | 0 |
| `distill-identity` | **0** | 231 | **119** |

`unknown` は実際に埋まっている（provenance が `{"source_type": "unknown"}` に default する行と、
ADR-0021 以前の legacy 行）ので残す。`observed` は production で非ゼロになったことが一度もない。

これはハーネスのルール「文書化された不変条件はゲートに落とす」が名指す一般形である — prose に
しか存在しない構造的不変条件は確率的にしか強制されない。しかもここでは不変条件を強制すること
自体が無意味で、フィールドが死んでいる以上、注記を足し続けるのではなく出力をやめるのが誠実な
修理である。

## Decision

**1. `observed` kind を枝ごと完全に退役する。** `_EPISTEMIC_KIND_BY_SOURCE` から
`"external_reply": "observed"` を削除し、`epistemic_counts_for()` が初期化する dict から
`observed` を落とす。出力シェイプは `{generated, unknown}` になる。

キーだけでなく枝ごと消すのは意図的である。稼働経路が到達しないマッピングは「なぜ到達しない
コードがあるのか」を再調査させ続ける誘因になる。`epistemic_kind_for()` は `.get()` で引くので、
万一 `external_reply` の行が現れても例外ではなく `None` → `unknown` に degrade する。外部取り込み
が復活したら、その時点で**実在する取り込み経路に対して** taxonomy を設計し直す。

**2. `_derive_source_type()` の `external_reply` 戻り値は残す。** この文字列は provenance レコード
であり、epistemic tally とは別レイヤである。その退役は provenance 側の棚卸しを要する別問題で、
本 ADR のスコープ外と明示する。

**3. 履歴は書き換えない。** `audit.jsonl` は append-only の監査ログ、`.staged/*.meta.json` は
承認待ちの成果物であり、どちらも 3 キーのレコードを保持する。`adopt.py` は `epistemic_counts` を
verbatim で pass-through するため、本 ADR より前に staged されたファイル（2026-07-25 の 78 件を
含む）は無変更のまま adopt 可能である。

## Alternatives Considered

**キーを残して警告を強める**（隣接する `"observed_note": "structurally zero since ADR-0060"`
フィールド等）。却下 — 死んだ値の周りに足場を増やすだけであり、しかも論点を認めてしまっている。
値の隣に免責注記をデータとして同梱する必要があるなら、その値は情報を運んでいない。何も運んで
いないフィールドを守るためにレコードシェイプを太らせることにもなる。

**`epistemic_counts` を丸ごと退役する。** 真剣に検討した。`insight` は `generated` 一択、
`distill-identity` も 2 値分割しか出さないので、tally は command ごとにほぼ定数に近い。今回は
却下 — `unknown` は実入力で実際に変動し（119 レコード）、このフィールドは ADR-0050 の承認系譜
契約そのものであり、さらに ADR-0072 が計器削除の際に `epistemic_counts_for()` を残すという明示
的判断を下している。それを覆すには本変更の付随ではなく独自の証拠が要る。

**そのままにする（signal-first の保留を継続）。** 却下 — 読み値の消費者がいない間は保留が正当
だったが、誤読インシデント自体が signal である。読者 1 人につき誤った結論を 1 つ生むフィールド
はコストゼロではない。

## Consequences

**誤読が構造的に不可能になる。** `observed` キーが無ければ、過剰解釈される `observed=0` も無い。
ドキュメントによる強制ではなく**不在による強制**であり、本プロジェクトの `security by absence`
と同じ形である。

**`audit.jsonl` にスキーマの継ぎ目ができる。** 2026-07-25 より前のレコードは 3 キー、以降は
2 キーを持つ。監査の完全性のため、移行せず受け入れる。オフライン解析は固定キーセットを仮定せず
`.get(key, 0)` で読む必要があり、`epistemic_counts_for()` と `_log_approval()` の docstring に
その旨を書いた。`audit.jsonl` を読む唯一のツールである `scripts/log_anomaly_sweep.py` は行単位の
regex マッチのみでこのフィールドに触れないため、影響を受けない。

**production の読み取り側は変更不要。** `src/` のどこも `["observed"]` を索引せず、dict の arity
も仮定していない。全 consumer が opaque な `dict[str, int]` として copy / 直列化する
（`cli/staging.py`、`cli/adopt.py`、`cli/approval.py`、`cli/memory_cmds.py`）。

**削除した枝の代わりに回帰ガードを置く。** `test_epistemic_kind_for` が
`external_reply → None` を、`test_observed_key_is_retired` が出力シェイプからのキー消失を主張する
ので、枝を復活させるには silent な drift ではなく意図的な行為が必要になる。
`test_adopt_passes_through_pre_adr0082_meta_verbatim` が非遡及の保証を固定する。

**インシデントの背後にある読み方の癖には触れていない。** エージェントはデータファイルから値を
読み、それを生成したコードを読まなかった。このフィールドの退役はその 1 事例を消すが、癖そのもの
は消さない。安価な決定論ゲートが見当たらないため、機構化せず観察として残す。
