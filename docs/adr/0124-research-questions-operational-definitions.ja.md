# ADR-0124: 研究問い — 建立時の 3 問と Q4 の操作的定義

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code セッション（ロードマップ束 P3-01）
decided-by: オーナー — D-P3-01-1 = B（Q4 を加える）と D-P3-01-2 = A（評価層は研究証拠から除外）、いずれも 2026-10-24。残りの本文は、これを載せる pull request をオーナーがマージした時点で受理
date: 2026-10-24

## Layer

research

## Context

[ADR-0080](./0080-north-star-layered-end-state.ja.md) は研究層の完成を「建立時の問いが肯定でも否定でも答えられ、論文として結晶化される」と定義している。3 問（小型ローカルモデルの行動を contemplative な憲法は形づくるか／蒸留は複利するか／identity は安定するか）は 2026-07-20 に初めて文章化されたが、**計器・signal・noise floor・反証条件・比較境界が無い**。[ADR-0002](./0002-paper-faithful-ccai.ja.md) に「問い」「仮説」の語は 0 件。これでは読みが問いを決着させられない。現時点の証拠は「憲法本文はどの計器の床も超えて動かさない」だが、何が動いたことになるかを事前に言っていないので、この文には地位がない。

設計を決めた 3 つの事実:

- 公開証拠は偏る。Q1 には [`docs/evidence/adr-0090/`](../evidence/adr-0090/) と [`adr-0092/`](../evidence/adr-0092/) がある。Q2 は clone から見えない（gitignore された `.notes` scratch dir の）読みだけ。Q3 は [ADR-0030](./0030-withdraw-identity-blocks.ja.md) が identity 履歴を撤回し、`snapshots/distill-identity_*` が 2 本あるだけ。
- エージェントは人間ゲート付きの**1 個体**で、対照群が無い。統計は系列内比較にし、n=1 で何が言えるかを正直に書く。
- オーナーの主関心（承認ゲート、自己改訂する価値層の legibility、オペレータ負荷）はこのリポジトリで最も厚く記録されている（決定件数、[ADR-0099](./0099-weekly-report-instrument-redesign.ja.md) の推薦と裁定の一致率、[ADR-0101](./0101-instrument-dissolution-mandate.ja.md) の計器の建立／溶解、ADR-0080 のオペレータ負荷の追補）が、3 問に入っていなかった。

## Decision

### 1. 各問いに (a) 計器 (b) signal と noise floor (c) 事前登録した肯定／否定の判定文 (d) 比較境界

全問共通の比較境界: 憲法改正 3 回（2026-03-27 / 05-05 / 08-09）と生成モデル交代（2026-06-28、[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md)）。正本は DATACARD に載る境界表（P3-02.1）。それが出るまではこの 4 つの日付が作業用の一覧。

**Q1 — contemplative な憲法は小型ローカルモデルの行動を形づくるか？**

- (a) IPD 二アーム ([ADR-0090](./0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md))、shadow 憲法 cosine ([ADR-0092](./0092-shadow-constitution-instrument.ja.md))。評価層 ([ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.ja.md)) は研究証拠**ではない**（D-P3-01-2 = A、開発用回帰ゲート）。
- (b) IPD: Δ(custom − baseline) で ±0.13（null pair 1 組の最大振れ、床自体が不確か）。shadow cosine: 同一入力で run 間 0.016（1 組）。
- (c) 判定文は [`docs/evidence/research-questions.md`](../evidence/research-questions.md) の Q1 に事前登録済みで、[改正 runbook](../runbooks/constitution-amendment.md) が参照する（2026-10-31 の読みより前に固定）。要点: 肯定 = 改正の IPD の読みが、実行前に記録した向きで ADR-0090 の読める 3 信号のいずれかを示す（単一セルだけ床を超えるのは読めない扱い）。否定 = 読める改正 N=3（草案、2026-10-31 の読みの前にオーナーが確認。2026-08-09 を数えるのは遡及）回連続で床を厳密に超える動きが無い — 「この model・計器では H は支持されない」までで、それ以上は言わない。
- (d) 上の境界。介入は憲法改正。

**Q2 — 蒸留は複利するか？**

「複利」は別々の軸で読み、単一スカラーには還元しない（ADR-0080 の 2026-08-26 追補 B）。script は [`scripts/compounding_axes_reading.py`](../../scripts/compounding_axes_reading.py)（公開 data repo に対する read-only）。最初の読みは [`docs/evidence/adr-0124/compounding-axes-20261024.md`](../evidence/adr-0124/compounding-axes-20261024.md) に固定した。

| 軸 | 入力 | noise floor | 複利する場合の期待形状 | 反証形状 |
|---|---|---|---|---|
| 採用 skill の選択活動 | `pipeline/never-selected/*.json` | 95% Wilson 区間、分母 10 未満は件数のみ | 選択実績ありの skill のうち窓内で選ばれた割合の区間下限が 0.5 以上を保つ（この割合は上限側の値: 窓内で一度も提示されなかった名前も active に数えるため、上向きの偏りを踏まえて読む） | 区間上限が 0.5 未満の週が 2 週連続（採用 skill が使われなくなる） |
| corpus 成長（処理量） | `knowledge.json` | 件数には無し。区間内 4 点以上で形として読む | 蒸留が走る間、週あたり追加がほぼ 0 まで減衰しない | 区間中央値の 10% 未満が 4 週連続 |
| skill 注入コメントへの環境応答 | `pipeline/comment-outcomes/*.json` | Wilson 区間（skill×comment の組は独立でない注意つき） | 区間が境界をまたいで下がらない | 区間上限がほぼ 0。**この軸だけでは肯定読みは不可能**: 公開ファイルに非注入アームが無く、selector の選択は状況と交絡する (RFC-0028)。drift として報告 |
| 選ばれた skill の元パターン年齢 | skill-selection log、audit の `source_ids`、`knowledge.json` | 最初の 2 回の読みから決める | 2 回（四半期ごと）の読みの後、選ばれた skill が corpus 全体より古い素材に寄るかの判定文 | 同じ文で逆向き（新しさだけで累積なし） |

最後の 2 列の数値の切りは本草稿の選択で、受理時に固定する。最初の読みの前ならオーナーが変えてよく、変えたら証拠表に日付を書く。corpus 成長軸は処理量であって新規性ではない。類似度ベースの新規性率は公開ファイルに無い埋め込みを要し、再埋め込みの再計算 script (P3-02.3) の仕事。

(d) 各軸は境界で区切った区間ごとに読み、またいで混ぜない。

**Q3 — identity は安定するか？**

- (a) identity 版間距離の系列 (P3-04.8) と再導出の null pair (P3-04.9)。どちらも未実装。入力は data repo の identity 版 `history/`（D-P3-04-1 = C）。
- (b) 要測定: 同一 corpus での identity 再導出の null pair 3 組以上、床アンカーはテンプレート identity。閾値は読んでから決める（signal-first、[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md)）。
- (c) (b) の後に固定: 安定 = 採用版間の距離が再導出の床の内側。変化 = 連続する採用版で同じ向きに床を超える。staged 全版と採用版のみの 2 系列を分けて読み、却下による見かけの安定を除く。
- (d) 上の境界。介入は identity の採用（2026-10-08 時点で staged 11 件中 6 件採用）。

**Q4 — 人間が最終判断を持つ自己改訂ループは、何を可監査にし、何を費やすか**（D-P3-01-1 = B で追加。Q1〜Q3 は捨てない — 否定的結論も結晶化の対象。）

- (a) 決定ログとゲート記録（skill 採用 82 / 却下 547、identity 6/11、憲法 2/4）、[ADR-0099](./0099-weekly-report-instrument-redesign.ja.md) の推薦と裁定の一致率、計器の建立／溶解の記録（[ADR-0101](./0101-instrument-dissolution-mandate.ja.md)）、オペレータ負荷（ADR-0080 の 2026-08-26 追補 A）。決定記録の `approver` と系譜の列 (P1-12) と公開投影 (P2-05.2) が意図する計器だが、まだ無い。
- (b) 件数は noise model の無い集計。率（推薦への裁定の一致、`--yes` で採用された割合）は Wilson 区間で、自明な基準率（全部承認するゲート）の隣に置いて読む。
- (c) legibility: 期間内に採用された各値層変更について、公開記録だけで「何が提案され、誰が決め、どの系譜か」を再構成できるか。肯定 = 記録が完全な割合の区間下限が期間で 0.9 超。否定 = 裁定の推薦一致率が全部承認と区別できず、負荷も下がらない。0.9 は草稿の切りで最初の読みの前ならオーナーが変えてよい。Q4 が記述するのは**ゲート**であり、値層の目標状態は置かない（observation-over-steering）。
- (d) 上の境界と、決定記録の列が入った日付。
- ADR-0080 と `CLAUDE.md` §北極星への採否の反映は P1-03.8 の追補（2026-12）の 1 段落が持つ。この ADR はどちらも編集しない。

### 2. 外部監査経路

この project の監査者はオーナー 1 人で、承認者でもある。[ADR-0106](./0106-comment-outcome-recording.ja.md) は、オーナーが出力を評価することを計測の代わりにしない（値層の進化にオーナーの価値を注入する steering になる）と決めており、論文自身も独立した監督を求めている (Laukkonen et al., 2025)。代替は**公開性**: 外部の読み手は (i) 公開 data repo（patterns、pipeline の読み、snapshots、決定記録）、(ii) ADR/RFC の履歴、(iii) 読みを再計算する script を得る。外部の読み手が何を再計算でき何をできないかは、下の `reanalysis` 列で読みごとに明記し、検証不能な読みを検証可能に見せない。

### 3. `reanalysis` 列

事前登録した各読みに値を 1 つ: `public`（公開データか `docs/evidence/` から再計算可）、`private-rows`（入力行が私的で集計のみ公開）、`rerun-local`（ローカルモデルの再実行で再現）、`rerun-cloud`（cloud judge が要る）。public でない読みは論文の限界節で「再解析不能（集計のみ公開）」として列挙する。列は [`docs/evidence/research-questions.md`](../evidence/research-questions.md) に置く。現時点の分類: IPD・never-selected・comment-outcomes は `public`、relevance ラベル集合・RFC-0045 の行データ・shadow cosine の行は `private-rows`、eval golden は `rerun-cloud`。

### 4. 単一エージェント縦断設計の方法節草稿

- (a) 群間推論はしない。個体は 1 つで対照群が無い。
- (b) 比較は事前登録した境界の前後の系列内比較。
- (c) 計器ごとに null pair の床と、区間つきの効果量。run 間ノイズの推定量は P3-03.10 のセル別 SE 規則が正本で、**着地した時点でこの段落は参照で採る**。それまでは ADR-0090 の 1 組の最大振れを「1 組」と明記して使う。ここで変える場合は P3-03.10 と ADR-0090 を同じ PR で直す。「同一入力の反復 2 回の差を床にする」同型の計器が 3 つある: IPD null pair、identity 再導出 (P3-04.9)、relevance の順序感度 (RFC-0046)。
- (d) 単一事例設計（ITS / change-point）は採らない: ADR-0110 が 28 点でも trend / season / drift が無いとして change-point 系の道具を却下済み。代わりに区間長表（P3-02.1 の派生表）で決める: 系列内比較は**点数 4 以上**の区間だけ。短い区間は記述に留め検定しない。ロードマップ査読が数えた境界間隔（20, 19, 43, 6, 5, 5, 9, 6, 8, 14, 7, 6, 6, 1, 8, 5, 1, 6, 10, 9 日。2026-06-17 以降は最長 14 日）では、週次の読みは直近の区間で最大 2 点にしかならず、多くの比較は記述になる。派生表が入ったらこの一覧を置き換える。

### 5. 四原則の機構カバレッジ

表 [`docs/evidence/four-principles-coverage.md`](../evidence/four-principles-coverage.md) をここから参照する。改正のたびと、計器を足す ADR のたびに更新する。論文の限界節のギャップ記述はこの表のギャップ列を引く。

### 6. 消費計画 (ADR-0101)

- `scripts/compounding_axes_reading.py` — (a) 受理時（2026-12）にオーナーが 1 回、以後は境界が増えた時と Q2 の論文を書く時（2027-Q1〜Q2）。年齢の軸は四半期に 1 回。 (b) 1 回の読みで各軸が「期待形状 / 反証形状 / どちらでもない」のどれに落ちたかを証拠表に書く。年齢の軸は 2 回で判定。 (c) 撤去: 手動実行のみ、CI に入れない。最終 sync (P4-02) で値を `docs/evidence/` に固定し再実行しない。年齢の軸は 2 期で Q2 が決まらなければ外す（script は evidence に残す）。
- 機構カバレッジ表 — (a) 改正ゲート (P0-07、2026-10-31 以降) と計器 ADR のたびにオーナーが読む。 (b) 1 回の読みで「機構ゼロの原則」「計器が盲目の原則」を書く。 (c) 最終 sync で固定。

## Review-when

- Q1 の事前登録行の最初の読み（2026-10-31 の改正）が出たとき: 判定文が書いたまま使えたかを確かめ、N や切りを変えたなら記録する。
- P3-03.10 が着地したとき: 4(c) の暫定の推定量を参照に置き換える。
- 境界表 (P3-02.1) が着地したとき: 作業用の境界一覧と区間長の一覧を置き換える。
- P1-12 の決定記録の列が着地したとき: Q4 の計器・床・期日を「未構築」から書き換える。
- 再導出の null pair (P3-04.9) が出たとき: Q3 の (b)(c) を固定する。

## Alternatives Considered

- **3 問のまま (D-P3-01-1 = A)** — オーナー決定で不採用。Q4 が無いと、ループで最も厚く記録されているもの（ゲート）を研究する問いが無い。
- **Q1 を Q4 に置換 (C)** — 不採用。Q1 の否定的答えも結晶化の対象。
- **評価層を研究計器に拡張 (D-P3-01-2 = B)** — 不採用。12 件・2–1 margin が多い・cloud judge では弁別力が無く（[evidence](../evidence/adr-0089/README.md)）、育てることは ADR-0101 の溶解義務とゼロ API 前提に反する。
- **Q2 の軸を 1 つの「複利スコア」に還元** — ADR-0080 追補 B が禁止。
- **縦断設計に中断時系列** — 4(d) の理由で不採用。

## Consequences

- 各問いが失敗しうるようになる: 否定の形を事前に述べた文がある。すでに持っている読み（Q1 の床内の読み）は、語りでなく表の最初の行になる。
- 再解析できない読みが出る。限界として明記し、隠さない。
- Q3 と Q4 は計器のある範囲まで定義し、残りは日付つきの stub と、各自の Review-when による更新。
- script 1 本と表 2 枚が増える。いずれも撤去条件を持つ。

## References

- `ADR-0080` — 研究層の完成条件。Q4 の段落は P1-03.8 が足す。
- `ADR-0090`, `ADR-0092` — Q1 の計器と床。`ADR-0089` — 評価層（研究証拠から除外）。
- `ADR-0099`, `ADR-0101`, `ADR-0106` — ゲート記録、溶解義務、オーナー評価が計測の代わりにならない理由。
- [`docs/evidence/research-questions.md`](../evidence/research-questions.md), [`docs/evidence/four-principles-coverage.md`](../evidence/four-principles-coverage.md)。
- Laukkonen et al. (2025), Contemplative Artificial Intelligence, arXiv:2504.15125。
