# ADR-0097: 統合器の解体と skill store の出口 — 引き算、出口、語彙の順に

## Status

accepted — partially-supersedes ADR-0016, ADR-0046, ADR-0048, ADR-0096

Decision 1 自体も 2026-08-29 に RFC-0016 で部分的に supersede された:
surprise 計器は復元し、promotion-worth 判定は退役のまま。Decision 1 直下の
追記を参照。

## Date

2026-08-22

## Context

週次の skill 抽出パイプライン（土曜 08:00 の `insight --stage` → staging →
`scripts/weekly-pipeline.sh` の headless Claude review → 土曜ゲートで人間が
`adopt-staged`、[ADR-0074](./0074-weekly-staged-insight.ja.md) /
[ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md)）は、
store の飽和と無関係に毎週 46–55 件の候補を staging に置く。候補はその週の
エピソードから作られる ≥3 pattern の cluster だからである。7 週（2026-07-09 …
08-22）の累計は staged 438 / adopted 53（12%）。却下理由はほぼ全部が「採用済み
skill に既に覆われている」か「同じ batch の兄弟と同じ」である。

gemma の novelty gate（ADR-0074 D6、`core/insight_novelty.py`）は cluster の
12–30% を covered と判定する（13/97、23/77、11/75、8/61、13/68）が、reviewer と
人間は 80–90% を covered として却下する。gate の証拠は store と ledger の
name / description だけ、cluster 側は 3 pattern × 300 文字の sample で、prompt は
「迷ったら NEW」と指示している。batch 内の候補どうしは比較しない。

[ADR-0096](./0096-insight-promotion-worth-abstain.ja.md) の promotion-worth 判定は
2026-08-21 に初めて本番で走り、46/46 が `promote`、抽出側の `NOTHING-PROMOTABLE`
は 55 件中 0（`insight-launchd.log`: "yield 46/55 … nothing_promotable=0"）。
ADR-0096 はまさにこの結果を自分の反証条件として事前登録していた（「Rate = 0%:
gate は発火しておらず、設計は調整不足でなく refuted。fallback は … channel を
残し判定者を落とす」）。gemma の self-judge が全部に yes と言う読みはこれで 3 回
一致した（[ADR-0084](./0084-post-distill-durability-gate.ja.md) v4 arm 40/40、
ADR-0096 の offline check 18/18、本番 46/46）。同 ADR の surprise 計器（D10–12）
には名指しの消費者がいない — `config/prompts/insight-recommendation.md` は
surprise に触れていない — これも同 ADR 自身が撤去条件として挙げたものである。

実効の判定者は headless Claude reviewer である。ゲートのあった 4 週（08-01、
08-08、08-15、08-22）すべてで、人間の採用集合は reviewer の `RECOMMEND: adopt`
集合と一致した（13/8/5/9、08-22 は名前単位で一致）。reviewer は覆っている
store skill と影に入る batch の兄弟を散文で名指ししているが、
`scripts/weekly-pipeline.sh` は `grep -q "RECOMMEND:"` しか見ず、
`scripts/build_decision_packet.py` は見出しを数えるだけ — coverage の判断は毎週
捨てられている。08-22 には reviewer（したがって人間）が name / description / 本文の
食い違う skill（`analyzing-systemic-governance-loops`）1 件と、同一テーマの変奏
3 件を採用した。

store は 57 skill（15.3k 語）。frontmatter は `name` / `description` / `origin` の
3 つだけで、採用日は filename の suffix に、pattern の lineage は `audit.jsonl` に
しかない（staging の sidecar は adopt 時に unlink される）。出口は無い:
`remove-skill` は 5 ヶ月で 6 回、skill-stocktake の merge は 2026-04-11、04-14、
05-30、06-01、08-15 の 5 回で、すべて人間起動。直近 1 週間で 19 skill は一度も
選ばれず、3 件は選択履歴の全体で一度も選ばれていない（judged 露出はそれぞれ
1,845–2,531: `pre-processing-state-validation`、
`assume-perfect-adversarial-understanding`、
`introducing-intentional-systemic-ambiguity`）。いずれ選ばれた skill について、
初選択までの judged 露出は p50 7 / p90 99 / p95 302 / max 569 だった。

[ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.ja.md) の
selector は skill ではなく family を選んでいる。6 skill の「制約」family は、連続する
4 つの週次窓（07-25 … 08-22、各 606–686 judged）で judged action の 0.78 / 0.74 /
0.72 / 0.81 においてどれかが選ばれ、「分解」family は 0.83 / 0.85 / 0.80 / 0.72。
08-15–08-22 の窓（606 judged）の co-selection からは、両向きの条件付き確率 ≥ 0.6 の
対が 3 組（`cross-reference-foundational-claims` ↔
`dissecting-asserted-agency-into-mechanisms` 0.63/0.65、`internal-process-audit`
↔ `shifting-focus-from-state-to-process-mechanics` 0.64/0.69、
`detecting-abstract-to-operational-constraint-shift` ↔
`structural-constraint-mapping-scm` 0.66/0.77）と、非対称の下位ケース対が 11 組
（P(b|a) ≥ 0.7 かつ P(a|b) ≤ 0.4、例: `suspend-interpretation-upon-premise-doubt →
internal-process-audit` 0.96/0.23）が出る — LLM も embedding も使わず
`logs/skill-selection-*.jsonl` だけから計算できる family 構造である。

> **注記（2026-08-22、unit C の検証）**: ここの数値は計器より前の探索的な集計で、
> 最小支持数を宣言していない。`scripts/coselection_families.py` は 3 つの sibling 対を
> 小数第 3 位まで再現し（0.6277/0.654、0.6396/0.6888、0.6641/0.7695）、下位ケースの
> 例も一致するが、明示した床のもとで下位ケース対は 11 組ではなく **16 組**と読む。
> 上の 0.77 は `window` 分母の値で、`--condition co-exposed` では 0.7908 になる。
> 計器の数値を正本とし、この段落はそれを促した観測として読む。「制約」family
の 6 skill はそれぞれ固有の手順を持つ（register の切り替え検出、3 段の失敗分析、
物理 / 注意 / スループットを横断する律速の探索、抽象から測定可能な持続への
翻訳、境界を条件として読む、接点での前提チェックリスト）。共有しているのは姿勢で
ある。

selector の幻覚率（`rejected_names` が空でない judged 記録の割合）は catalog の
大きさとともに上がった: 24 skill で 0.6%、37 で 7.7%、45 で 20.2%、48–57 で 18.0%
（109/606）。ほぼ全部が実在する名前の語形変化である（`suspending-` と
`suspend-`、`identifying-` と `identify-`、`structuring-constraint-mapping-scm`）。

統合器 3 本を 2026-08-15 の手動実行（Ollama gemma4:e4b、think ON）で測ると:
`skill-stocktake --stage` は 68 分、LLM ≈97 コール（1 run ≈ 1 + G + 2N: grouping、
group ごとの merge、singleton ごとの clean、生存者ごとの description 監査）。clean
段（[ADR-0048](./0048-trigger-altitude-skill-lifecycle.ja.md) stage 3）は 47 skill を
処理し、`is_clean_noop` が拾わない（`CLEAN_NOOP` 番兵しか見ない）バイト同一の
書き戻し 14 件、一時的識別子の無い skill に一般化の定型句（"a particular
individual" / "a specific topic" / "in similar contexts"）を*挿入*した書き換え
3 件、採用 4 / 却下 21。grouping は
[ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) の
amendment 以降 frontmatter の summary を証拠にしており、recall は測られていない。
`rules-distill --stage`（8 分、4 コール）は "processing all 48 skills" とログに
出しながら LLM に渡したのは 20 件（`cluster_patterns(max_size=10)` の後
`singletons[:10]`、全 skill dict の importance が同じ 0.1 なので列挙順）。既存の
rule も憲法も identity も prompt に渡さない。8 候補は全部却下（Emptiness 公理の
言い換え、339 回選ばれた skill の言い換え）。内容を rule に移した skill を退役させる
経路が無いので、昇格すると二重注入になる。`.last_rules_distill` は対話経路でしか
書かれない。`rules-stocktake` は 2026-04-11 から不変の rule 2 ファイルに対して
grouping と共通核の合成を回す。

この決定のための探索（T-CONSOLIDATOR-REDESIGN）: code map 2 本、著者の vault wiki、
2026-08-22 時点の外部文献調査、他分野の類推（図書館の除籍、Wikipedia の
merge / redirect、API 廃止、記憶の固定化、Zettelkasten、辞書編纂、分類学、
stock-and-flow）、fresh-context の architect 判定、Codex による前提反証。決定に効く
知見: 全部を保存するのは記憶なしより悪く、選択的記憶が効くのは judge が良い
ときだけ（Experience-Following、arXiv:2505.16067）。実行・蒸留・検証を同じ agent が
やると検証が甘くなる（EDV、arXiv:2606.24428）。プログラム的信号は自由記述の内省に
勝る（arXiv:2605.29463）。出口の無いライブラリは肥大し利用率が崩れる（AutoRefine
v1、arXiv:2601.22758: 保守なしで 108 pattern / 利用率 0.08、ありで ~24 / 0.71。
SkillBrew、arXiv:2605.29440: add-only 47.0 vs 59.0）。store 全体の書き換えは
context を崩す（ACE、arXiv:2510.04618: 18,282 → 122 tokens）。Mem0 v3（2026-04）は
reconciliation が context を壊すとして UPDATE / DELETE を捨てた。

usage ≠ utility は再現されている（arXiv:2608.03874、2604.17308、2602.12670）ので、
使用回数で skill の無用を証明することはできない — しかし two-pass 注入のもとで
一度も選ばれなかった skill は一度も注入されていないので、それを外しても judged な
挙動は変わらない。図書館の CREW 除籍法は最終貸出日を「司書が必ず見る filter」と
扱い、理由の書面化を義務づける（義務化まで候補の 98% が保持されていた）。
Wikipedia は新しい重複を古い本記事へ merge する。

architect の判定: 「build はほぼ引き算＋field 1 つ＋list 1 つ。順序は削除 → 出口 →
既に存在する判断の捕捉。計器は最後」。Codex の反証は「never-selected の archive は
*構成から*挙動中立」という主張を覆した（fail-open 経路は全 corpus を再注入する）—
照合すると 2026-07-13 以降 3,716 記録で fail-open は 0 件、かつ全 corpus（38,867
tokens）は既に NUM_CTX 32,768 を超えているので fail-open は注入でなく abstain する
（ADR-0081 amendment）— そして rules 層の保守所有者、reviewer の false negative の
観測器、verdict 語彙が store に触れる前の完全性検査の強化を求めた。

## Decision

1. **ADR-0096 の事前登録 fallback を実行する。** promotion-worth の LLM 呼び出し
   （`insight._worth_gate`、`config/prompts/insight_worth.md`、
   `insight-worth.jsonl` の writer）と surprise 計器（`core/insight_surprise.py`、
   sidecar の `surprise` field、`adopt-staged` の surprise 表示）を撤去する。
   ADR-0096 の Decision 1 と 4–6 は残す: `NOTHING-PROMOTABLE` の抽出時 abstain、
   fault と別に数える `ABSTAIN_NOTHING_PROMOTABLE` 理由コード、常に出す yield 行、
   `.last_insight` を進めるかを決める fault / verdict の分割。

   > **2026-08-29 追記（RFC-0016）— Decision 1 は部分的に supersede された:
   > surprise 計器は復元し、worth 判定は復元しない。** この決定は根拠の異なる
   > 2 つの撤去を束ねていた。worth 判定の撤去理由は**反証**である — 本番 3 回の
   > 読みが全件 promote（40/40、18/18、46/46）で、ADR-0096 自身が事前登録した
   > 反証条件が発火した。これは今も成立しており、`insight._worth_gate`、
   > `config/prompts/insight_worth.md`、`insight-worth.jsonl` の writer は
   > 撤去したままにする。surprise 計器の撤去理由はこれとは別で、「読み値の
   > 名指しの消費者がいない」— これも ADR-0096 が撤去条件として事前登録して
   > いたもので、読み値の妥当性への指摘ではなかった。ADR-0080 の 2026-08-26
   > 追補（代謝の質: 頻度単独では価値を判定できない、複数軸で見分けられること、
   > 単一スカラーへの還元は禁止）がその消費者を名指しする — insight 抽出の
   > フィルタは >=3 pattern の頻度クラスタだけで、surprise はその新規性軸の
   > 既実装だった。よって `core/insight_surprise.py`、sidecar の `surprise`
   > field、`adopt-staged` の表示を 2026-08-29 に復元した。
   >
   > 復元には 2 つの制約が付く。本 ADR の Decision 3（「採用は書き込みだけ」）は
   > 保たれる — 復元した sidecar field は**表示専用**で、採用の可否・順序・件数の
   > どれもその値の関数ではない（`tests/test_cli_adopt.py::TestSurpriseIsDisplayOnly`
   > が固定）。また ADR-0080 追補により、読み値を単一スカラーの自動判定へは
   > 昇格させない — 複数軸の一つとしてどこで消費するかの設計は RFC-0017 の
   > 設計セッションに残す。

2. **`rules-distill` と `rules-stocktake` を LLM 生成器として退役する**: CLI
   handler、`core/rules_distill.py`、prompt `rules_distill.md` /
   `rules_distill_refine.md` / `stocktake_rules.md`、`.last_rules_distill`
   marker。`stocktake_merge_rules.md`（共有する核の合成）は family → rule 昇格
   （Decision 7）の prompt として残し、決定論の `_check_rule_quality` も残して
   rules 層が週次 packet に保守の読み値を持ち続けるようにする
   （`scripts/value_layer_due_check.py` の `rules` 節: 件数、mtime、構造検査 —
   スライス 2）。

3. **`skill-stocktake` を縮退する**: ADR-0081 の description 監査と usage 読み値
   （report のみ）だけにし、grouping / merge / clean 段、その prompt
   （`stocktake_skills.md`、`stocktake_merge.md`、`stocktake_clean.md` と system
   prompt）、`--stage` flag、merge / clean の staging producer を外す。1 run の LLM
   呼び出しは ≈1 + G + 2N から N になる。それらの producer だけが書いていた staging の
   field も一緒に外す: `StageItem.sources`（merge 元の adopt 時削除）、
   `StageItem.action`（merge / drop）、item ごとの `command` 上書き、そして
   `adopt-staged` 側の対応する sidecar キーの処理。**採用は書き込みだけになる** —
   攻撃者が書ける sidecar から届いていた 2 つの削除プリミティブを、producer 不在の
   まま残さず消す。Decision 5 の出口は sidecar の field でなく operator が打つ明示の
   引数として来る。

4. **novelty gate は code を変えず目的を言い直す**: ledger
   （`logs/insight-staged.jsonl`）の書き手と安い fail-open の pre-filter であって、
   coverage の判定者ではない。失効条件を名指しする: 決定に依らない known-theme
   inventory（08-21 に 57 skill に対して 397 entry）は単調に増え、2026-07-18 に
   起きたように token-bounded の chunking を再び壊す。

5. **出口を予約する（スライス 2）**。スライス 1 の後に、暦の週でなく観測量で
   ゲートして建てる: 退役 skill は `skills/.archive/` へ移す（削除しない。
   `remove-skill --reason` は必須のまま）。`adopt-staged` に明示引数
   `--archive-names FILE` を足す — reviewer 出力から導出しない。週次 packet に
   code-owned の never-selected 節を足し、**strict** 候補（選択履歴の全体で 0 選択かつ
   judged 露出 ≥ 600 — 床は観測された初選択の最大遅延 569 を超える最小の丸い数）を
   人間が archive する対象として、**dormant**（直近 14 日は 0 選択だが以前に
   選択あり）を読み値だけとして列挙し、併せてその窓の fail-open 件数と
   `full_skill_tokens` 対 NUM_CTX を出す — 挙動中立が成り立つのは judged action に
   限るからである。archive された skill と置き換えた skill は frontmatter に
   `supersedes:` / `superseded_by:` を記録する。read-only の co-selection family
   script を `scripts/` に加える。

6. **語彙を予約する（スライス 3）**: reviewer prompt の verdict 文法を `adopt` /
   `adopt-superseding <skill>` / `reject: covered-by <skill>` /
   `reject: sibling-of <candidate>` / `reject: vague` にする。古い skill がテーマを
   覆うときの既定は `reject: covered-by`（古い skill は選択履歴を保つ）で、
   `adopt-superseding` は理由を書いたときだけ。`build_decision_packet.py` は review
   の section と staged item の 1:1 対応（理由コード `INSIGHT_REVIEW_INCOMPLETE`）と
   名指しされた store skill 全件の実在（不在は reviewer の幻覚として記録）を検査し、
   verdict は提案に留まる — store の変更は明示のゲート引数でしか起きない。新しい
   prompt は初回の本番 run の前に 2026-08-21 の batch で offline replay して検証し、
   過去 7 週の候補と reviewer の名指しに対する offline の retrieval recall 測定
   （`scripts/retrieval_recall_measure.py`、著者が手で走らせる）が、code が用意する
   retrieval 証拠束をそもそも作るかを決める。

7. **rule 昇格は A′ の形を取る**: co-selection family の any-of 選択率が ≥ 500
   judged の互いに素な窓 2 つ以上で ≥ 0.75 なら（「制約」family は既に該当）、
   agent 自身のモデル（gemma）が family の共通の姿勢を `stocktake_merge_rules.md`
   で Practice / Rationale の形に合成し、結果は人間ゲートを通り、member の skill は
   状況依存の手順として **store に残る**。選ばれなくなった member は never-selected
   の出口から去る。rules 層は小さく保つ。

8. **「変数は一度に一つ」（[ADR-0056](./0056-retire-importance-llm-scoring.ja.md)）は
   暦の週でなく観測量で測る。** 変更ごとに期待する効果と、それを読める最小の
   記録数（judged 選択記録 ≈ 80–95 / 日）を事前登録する: 挙動中立な削除には不要。
   strict never-selected 3 件の archive には ≥ 80 judged で `catalog_count` 54、
   archive 名が `selected` にも `rejected_names` にも無い、fail-open 0。family →
   rule の昇格には ≥ 100 judged で member の選択が減り `selected_count` p50 が
   下がること。co-selection 対の merge には ≥ 100 judged でその対の語形幻覚が
   消えること。新規採用 skill が never-selected 候補になるのは judged 露出 600
   以降。暦に縛られる段は土曜の無人 reviewer run だけで、スライス 3 はその前に
   offline で検証する。

## Review-when

- 出口と最初の family 統合の後に ≥ 600 judged 記録がたまっても selector の幻覚率が
  18–20% の帯から下がらない → catalog サイズ仮説は誤り。store の衛生でなく
  selector / catalog の設計（family 単位の catalog、SameCapRisk 型の retrieval 時
  family 解決）を見直す。
- `insight-novelty.jsonl` に `fail_open_budget` が現れる → known-theme inventory が
  chunking を超えた。ledger の役割に retrieval 補助の再設計か、ledger の剪定が要る。
- スライス 3 の実在検査で、reviewer が名指しした covering skill の不在 / 誤りが
  却下の ≥ 10% に出る、または `scripts/retrieval_recall_measure.py` が
  ラベル付き対 30 組以上で `union` アームの recall@5 ≥ 0.9 を報告し、かつ 08-22 型の
  miss（同一テーマの変奏を採用）が再発する → code が用意する retrieval 証拠束を
  reviewer のために建てる。`union` は lexical と cosine の順位を予算 k で
  reciprocal-rank fusion したものであって、top-k 2 本の集合和ではない — 後者は
  最大 2k 件を引くので単独アームと recall@k を比較できず、誤った理由でこの閾値を
  超える。
- strict never-selected として archive した skill が `.archive/` から 2 回以上
  復元される → 600 露出の床は低すぎる。初選択遅延の分布から読み直す。
- `rules/` が 5 ファイル前後を超える、または昇格後に生成が instruction-stacking の
  症状を示す → 昇格を止めて層を見直す。
- スライス 2–3 の後も週次の候補量が ≥ 40 で、テーマの ≥ 80% が ledger 既出 →
  `--weekly-insight` の月次化（plist 1 行、可逆）を検討する。代償は 100–150 件の
  batch。

## Alternatives Considered

### 統合器 3 本を残して cadence を与える

（T-CONSOLIDATOR-CADENCE）却下 — 測定済みの欠陥（20/48 のカバレッジ、公理の
言い換え、退役経路なし、14/47 の no-op 書き換え）を持つ道具に時計を付けると、欠陥が
定期的に起きる。

### `rules-distill` を修理する

全件処理にし、既存 rule と憲法を prompt に渡す。却下 — 「LLM が skill batch から rule
を蒸留する」という前提は公理と既存 skill の言い換えしか出さなかった（8/8 却下）。
入力を増やしても同じものが増えるだけ。

### reviewer のための retrieval 補助の証拠束を今建てる

cosine + 字面の top-k で store 本文を inline する。未決 — reviewer の coverage 判断は
既に存在し、語彙がそれを捕捉する（architect 判定）。その false negative の観測器は
まだ無い（Codex 反証）ので、スライス 3 の offline recall 測定で決める。

### embedding 閾値による候補の抑止

却下 — ADR-0074 の較正は、この corpus で同テーマと別テーマの類似度に分離が無いことを
示した。

### attestation（抽出の前に複数窓での再出現を要求する）

却下 — ADR-0074 の窓シミュレーションは隣接窓の cluster 32 件中 32 件を一致させた。
この corpus では全テーマが再出現するので、再出現は何も濾さない。

### catalog 容量の上限を packet の読み値にする

却下 — 24 → 37 の幻覚率の跳ねは name backfill（ADR-0081 amendment）と交絡しており、
`report --skill-selection` は既に幻覚率の行を出している。

### 採用時の union merge

（`merge_group` 経由の `adopt-revising X`）却下 — union merge は 10 トリガーの過広な
skill を作った機構であり（ADR-0048）、落とした pattern 5 件中 2 件しか完全に回復
しなかった（ADR-0046）。Mem0 v3 も同じ理由で in-place の reconciliation を捨てた。
supersede-and-archive は両方のテキストを残す。

### 代表 skill をそのまま昇格させ、兄弟を archive する

却下 — 「制約」family の 6 member はそれぞれ固有の手順を持つ。co-selection が示すのは
add-on であって代替ではない。archive すると手順が注入から落ちる。

### 人間が昇格する rule を手書きする

却下 — rules 層が著者の言葉を運ぶことになり、
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) の観測スタンスから
外れる。

### insight の上流に日次の capsule 層または日次の決定論的構造層を置く

（2026-07-18 の note）採らない — データフローの大きな変更で
[ADR-0060](./0060-per-episode-grounded-distill.ja.md) の平坦化リスクがあり、統合器の
問いには不要。入口流量の問いのために未決のまま残す。

### 全自動の採用

却下。ADR-0085 の代替案 3 と同じ。

### archive の代わりの `disabled-candidate` 状態

（Codex の代替案）却下 — archive は可逆で、状態を増やさない。

## Consequences

### Positive

- 週次 insight run から worth 呼び出し 46 回と surprise pass が消える。
  `skill-stocktake` の 1 run は LLM ≈115 コールから ≈57（description 監査のみ）に
  なる。loaded prompt の inventory から 10 template が消える（`insight_worth`、
  `rules_distill`、`rules_distill_refine`、`stocktake_rules`、`stocktake_skills`、
  `stocktake_merge`、`stocktake_clean` と stocktake の system prompt 3 本）。
  `stocktake_merge_rules.md` は昇格のために残る。正本の件数は
  `docs/CONFIGURATION.md` にある。
- store に初めて出口ができる（スライス 2）。judged action に対する挙動中立は選択
  ログから証明でき、family 構造は agent が既に書いているデータから読める。
- reviewer の週次の coverage 判断が、捨てられる代わりに機械可読で検査可能になる
  （スライス 3）。
- 判断は記録数で進む。1 日 ≈ 80–95 judged なら、ほとんどのゲートは 1–2 日で読め、
  rule 昇格の基準は既に満たしている。

### Negative

- スライス 2 が入るまで store に出口は無い — スライス 1 だけでは機構が減るだけで
  store は縮まない。
- 採用済み skill の重複検出に LLM 段は無くなった。co-selection の読み値がゲートで
  使われるまで、残る衛生 pass は description 監査だけ。
- rules 層に生成器は無い。新しい rule は family 昇格（Decision 7）でしか来ない。
- ADR-0096 の計器は本番の 1 回の読みで撤去される。同 ADR 自身の事前登録が
  「1 回の読みで決める」と言っており、一致した 3 回の読みは上に記録した。
- スライス 2 が archive を足すまで `remove-skill` は削除のまま。これまでの 6 件の
  削除は削除のまま残る（内容は snapshot と `audit.jsonl` の hash に保存されている）。
- この変更より前に書かれた sidecar を後から adopt すると、delete-on-adopt が効かなく
  なる: `sources` と `action: drop` は無視されるので、merge 元は merged file の隣に
  残り、drop item は target を unlink せず本文を書く。着地時点で staging は空なので
  該当する sidecar は存在しないが、黙って起きる失敗なのでここに記録する。

### Neutral / Follow-ups

- [ADR-0016](./0016-insight-narrow-stocktake-broad.ja.md) の分割「insight = 狭い
  生成器、stocktake = 広い統合器」は終わる。統合は batch の統合器でなく土曜ゲート
  （co-selection の読み値 + supersede-and-archive）へ移る。ADR-0016 に日付つき注記を
  置く。
- ADR-0048 の stage 2 と 3（merge 時と clean 時のトリガー一般化）は退役し、stage 1
  （抽出 prompt）は残る。ADR-0048 に日付つき注記を置く。
- ADR-0096 の Decision 2 と 10–12 は自身の fallback により退役し、Decision 1 と 4–9
  は残る（9 の audit writer は記録対象の判定者とともに消える）。ADR-0096 に日付つき
  注記を置く。
- ADR-0046 amendment の summary 証拠 grouping は grouping 段とともに退役する。
  ADR-0046 に日付つき注記を置く。
- 台帳: `T-CONSOLIDATOR-REDESIGN` → `decided`、`T-CONSOLIDATOR-CADENCE` →
  `dropped`、`T-SKILL-PROMOTE` → A′ の形で `candidate`。
- `docs/CODEMAPS/architecture.md` の Data Flow と `docs/CONFIGURATION.md` は同じ
  変更で更新する（CLAUDE.md の鮮度規約）。

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.ja.md) — Insight as Narrow
  Generator, Stocktake as Broad Consolidator
- [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.ja.md) —
  Stocktake Duplicate Detection
- [ADR-0048](./0048-trigger-altitude-skill-lifecycle.ja.md) — Trigger-Altitude
  for Skill Lifecycle
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — Epistemic
  Taxonomy and Approval Lineage
- [ADR-0056](./0056-retire-importance-llm-scoring.ja.md) — Retire the
  Distill-Time Importance LLM Rating
- [ADR-0074](./0074-weekly-staged-insight.ja.md) — Weekly Staged Insight
- [ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) — Skill-Selection
  Shadow Instrument
- [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.ja.md) —
  Skill-Selection Two-Pass Injection Enforcement
- [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md) —
  Unattended Weekly Fix Chain with a Single Saturday Gate
- [ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.ja.md) —
  Value-Layer Cadence in the Weekly Chain
- [ADR-0096](./0096-insight-promotion-worth-abstain.ja.md) — Promotion-Worth
  Abstain at Insight Time
