# ADR-0111: insight の入口を段の列にする — 名乗り、コール分割、抽出後の重複判定

## Status

accepted

## Date

2026-09-19

## Context

skill store は 7〜8 月に 19 → 57 件へ育って飽和した。飽和した store では
「ほぼ全件却下」が正しい定常状態で、[ADR-0074](./0074-weekly-staged-insight.ja.md)
が insight の役割を「新しい安定テーマの検出」と定義したときの想定でもある。異常だったのは
歩留まりでなく**人間のゲートに届く量**で、土曜ゲート 4 回で却下 142 件を手で実行していた。

2026-09-19 の insight run（154 クラスタ、窓 09-05〜09-18）を read-only で再生した 2 本の測定
（[docs/evidence/rfc-0041/](../evidence/rfc-0041/README.md) に凍結）が、量をどこが決めているかを示した:

| 読み | 実測 |
|---|---|
| 抽出前 gate は集団を区別しない | どの tie-break arm でも、対照 7 件を却下 68 件と同等以上の率で止める（読み 1） |
| 成果物の**後**に置いた判定は区別する | t=0 で `duplicate`: 却下 68 件の 33、採用済み（leave-one-out）53 件の 12、対照 7 件の 0（読み 3） |
| 個々の verdict が再現するのは t=0 だけ | t=1.0 は verdict 単位で κ 0.00〜0.24（対照 0.00 / leave-one-out 0.04 / 却下群 0.24）。t=0 は 2 反復が全件一致、256 コール・失敗 0（読み 2・3） |
| enum 拘束が書式違反を消す | enum 拘束の 512 コールに enum 外・parse 失敗は 0。RFC-0027 の違反（target 名の日付接尾辞落ち 5/5、evidence id の取り違え 2/12）はどちらも欄が無拘束の `string` だった |
| ラベルのある 75 件で直列に重ねると | 抽出後判定だけで 75 → 42、両方で 75 → **16**（本番が採用した covered 向き gate。退役した `new` 文言での同じ重ね合わせは 25）（読み 3） |

形は [ADR-0084](./0084-post-distill-durability-gate.ja.md) のもの — 成果物の前に置いた judge には
比べる証拠が無い。抽出前 gate が見るのは生の 3 行と 1 行の theme 記述で、抽出後の判定が見るのは
書かれた候補と、同じ投影で並べた名前つきの近傍 5 件である。

別件として、[RFC-0024](../../rfcs/0024-skill-extraction-free-body-split-calls.md) が指摘したとおり、
抽出コールは 1 回の出力で 4 つの仕事（本文・固定様式・1 行 description・name）をしており、
散文を書きながら命名の注意書き 1 段落にも従わされていた。

## Decision

生き残ったクラスタを、次の順の固定した段に通す:

```text
クラスタ
  → 抽出前 gate       batch、temperature 0（ADR-0074 / RFC-0042 項目 1）
  → 名乗り            1 コール: reconfirm / insufficient / revise / new
       reconfirm / insufficient / revise → ここで終わり（記録する）
  → 本文              自由記述、think-ON
  → description / name  短い拘束コール 2 本
  → 抽出後の重複判定  1 コール: duplicate / distinct
       duplicate → ここで終わり（記録する）
  → staging → 土曜ゲート
```

1. **名乗りは最初から enforce する。** クラスタごとに 1 コール、temperature 0。入力はそのクラスタの
   観察（id つき）と、nomic cosine で最も近い store の skill 5 件。`kind` は enum、`target_skill` は
   見せた 5 件の名前の enum（`revise` 以外は null）、`evidence_ids` はそのクラスタの観察 id の enum 配列。
   shadow mode は置かない — insight は停止中で並走させる相手がいない。全コールが監査ログに残るので
   後からの再生はどちらでもできる。

2. **`revise` は記録のみ（案 A）。** `revise` と名乗ったクラスタは本文を書かず、`target_skill` と
   `change_reason` を監査ログに残して終わる。目的はゲートに届く量を絞ることで、置き換え経路は量を
   戻す向きに働く。本文コールの対象を `new` → `new` + `revise` に広げるだけが案 B の全部で、
   ここを壊さずに足せる。

3. **抽出コールを 3 本に割る。** 本文は自由記述 — 固定様式と命名の注意書きはプロンプトから外す
   （RFC-0024）。`description`（what + when の 1 文）と `name` は、既に存在する本文について問う別コール。
   **frontmatter は code が組み立て、様式違反は保存時に code が拒否する** — 空・過大な本文、
   20〜300 字の外か引用符を含む description、slug にならない name。違反は理由コードつきの fault であって
   切り詰めではない（切り詰めた description は書かれたものと見分けがつかない）。これは
   [ADR-0096](./0096-insight-promotion-worth-abstain.ja.md) の理由コード語彙を狭める —
   fault が 3 つ増え、`no_title` が外れる（code が組む title は欠けようがない）。
   ADR-0096 に日付つきの注記を置いた。

4. **抽出後の重複判定。** 書かれた候補ごとに 1 コール、temperature 0。同じ近傍 5 件を同じ投影
   （name / description / 「何をするか」「いつか」の先頭 230 字）で並べる。`verdict` と `nearest` は
   見せたものの enum。`distinct` だけが staging へ進む。プロンプトは
   `scripts/post_extraction_judge_replay.py` の測定した文言をそのまま `config/prompts/` へ移す —
   証拠はその文言についての証拠である。ただし**候補側の投影は測定した形ではない**: 再生は両側から
   `## Solution` / `## When to Use` を読んでおり、Decision 3 がその様式を新しい本文から外すので、
   候補は 230 字の散文 head として投影される。本文コールがもう求めない様式を残すより、
   承知のうえで受け入れる。Consequences で再掲する。

5. **両方の段は fail-open。** 向きは現行 gate と同じ: 名乗りが判定できなかったクラスタは本文コールへ、
   抽出後判定が判定できなかった候補は staging へ通す。fail-open はそれぞれ理由コードを持つ
   （`llm_none` / `unparseable` / `off_enum` / `no_store` / `retrieval_unavailable`）。

6. **両方の段は全コールを** `$MOLTBOOK_HOME/logs/insight-stages.jsonl` に append-only で残す。プロンプトと生出力は
   base64 + sha256 で上限つき、verdict・理由コード・temperature・見せた store 名は平文
   （[ADR-0075](./0075-observability-by-default.ja.md)）。`insight-novelty.jsonl` とは別ファイルにする —
   あの log の読み手は kind の無い旧行を構造で判別しており（`is_novelty_judge_record`）、その規則は
   あのファイルが想定した 2 族だけを持つ間しか成り立たない。

7. **専用の週次計器は作らない**（[ADR-0101](./0101-instrument-dissolution-mandate.ja.md)）。
   判定による 4 つの終わり方（`reconfirm` / `insufficient` / `revise` / `duplicate`）は run 自身の
   yield 行と `insight` の summary で理由別に数えるだけ。読み script・率・傾向・ゲートの metric 列は
   作らない。`scripts/_census_registry.py` の行だけは足す —
   [ADR-0107](./0107-instrument-census-and-episode-log-folder.ja.md) が自己書き込みログ全件に
   要求しており、無いと `UNKNOWN` が出るため。あの行は既存のセンサスに合流するだけで新しい計器ではない。
   消費計画は Review-when に置く。

8. **判定コール 2 本は think-OFF。** 根拠となった再生がその条件で走っているので、think-ON は
   未測定の条件になる。[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md)
   の think-ON は生成のある場所（本文コール）に残す。

### ADR-0097 が退役させた judge との違い

[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) Decision 1 が退役させた
抽出後 judge は、事前登録の反証条件が発火したものだった — 問いは**昇格の価値**
（「この候補は昇格に値するか」）で、対象は候補**単体**、本番初回が 46/46 promote。比較対象の無い問いには
量るべき証拠が無く、これは ADR-0084 が名指した欠陥と同じ形である。

今回の判定は比較対象を供給した別の問いを立てる — 「これはこの 5 件の名前つき skill のどれかと同じ
behavior か」。2026-09-19 の再生では率が集団で分かれた（却下 33/68、採用済み 12/53、対照 0/7）。
退役した judge が出せなかったのがまさにこの読みである。

## Review-when

- **事前登録の反証条件。** 再開後、抽出後判定が**累計 30 件以上**の候補に答えた時点で（週をまたいで
  累計し、土曜ゲートで読む）、その `duplicate` 率が 0% か 100% なら設計は refuted — 段は**撤去**する
  （調整しない）。どちらかの端に張りつく率は ADR-0097 の失敗の再来で、成果物に関わらず同じことを
  答える judge である。件数の床を置くのは、目標が週 1 桁だからで、0/3 は判定でなく静かな週である。
  期間中プロンプトは凍結する。store は凍結しないので、読みは毎週の store 件数を記録し、1/3 を超えて
  変わったら計数をやり直す（近傍が比較対象であり、入れ替われば問いが入れ替わる）。
- [RFC-0042](../../rfcs/0042-insight-entrance-narrowing.md) の量の読み: 再開後 3 回の土曜ゲートで
  ゲートに届く件数が停止前の水準（週 ~35 件、4 回のゲートで 142 件）に戻っているなら、
  絞りは本番で再現しなかった —
  store を凍結して insight を退役させるか、再設計する。
- 本番生成モデルが gemma4:e4b でなくなる。温度・拘束・コール分割の挙動はこのモデルで測っている。
  大型化すれば分割が要らないかもしれず、RFC-0017 の平坦化もモデル起因だった。
- `revise` の提案が数週ぶん溜まって読まれる。使えるなら案 B（ゲートへの置き換え経路）をそこで決める —
  本 ADR は案 B に反対を先取りしない。
- store が飽和でなくなる（40 件台を継続的に割る）。「ほぼ全件却下が定常状態」という前提が崩れ、
  候補の半分を止めるゲートは抑制になる。

### Consumption plan

`insight-stages.jsonl` の census 行は、週次センサス（ADR-0107/0110）が enum 別件数と fail-open の
エラー数として読み、土曜ゲートが上記の 1 行の件数として読む。消費する判断はちょうど 2 つ —
反証条件の読み（30 件）と RFC-0042 の量の読み（3 回のゲート）。両方に答えが出た後、行は writer が
生きている間だけ残す。段を撤去するときは行とログも一緒に撤去する。

## Alternatives Considered

- **RFC-0041（knowledge のスキーマからの根本再設計）**: withdrawn。動機だった「入口が何も通さない」は
  故障でなく飽和で、スキーマ変更は消費者が多い。この問題に対して過大。
- **抽出前 gate の変更だけ**（temperature 0 + covered 向き tie-break、RFC-0042 項目 1 として出荷済み）:
  ラベルのある集合で 75 → 25（読み 3 の `covered` arm）と件数は動くが、読み 1 のとおり却下と対照を
  同率以上で止める。名乗りの回数を抑える安い前絞りとして残し、区別する段にはしない。
- **名乗りを先に shadow mode で走らせる**（[ADR-0076](./0076-skill-selection-shadow-instrument.ja.md)
  の型）: 不採用。insight が停止中で shadow する live の判断が無い。監査ログが同じオフライン再生を
  2 つの regime 無しに与える。
- **案 B — `revise` が置き換え候補を書き**、`--archive-names "old superseded-by new"` でゲートに出す:
  却下でなく保留（再訪条件は上記）。量を戻す向きで、改訂本文の質をまだ誰も読んでいない。
- **抽出後判定を store の退役判定に使う**（leave-one-out の対は毎週無料で出る）: しない。
  [ADR-0105](./0105-skill-store-exit-confusion-pairs.ja.md) が gemma を退役の判定者にする案を
  不採択にした理由は生きている。対は後で土曜ゲートに**列挙**してよい — 列挙は判定ではない。

## Consequences

### Positive

- 人間のゲートに届く候補が、再生した 2 週の窓で 75 → 16 になる — 週あたり約 8 件で、
  土曜ゲート 4 回で実際に却下した週 35 件（142 / 4）に対する値。
- 何も生まなかったクラスタが、どの段が決めたかを言う。判定による 4 つの理由は fault の 6 つと
  分けて数えるので、静かな週と壊れた backend が同じに読めない。
- ゲートするコールはすべて `insight-stages.jsonl` からオフラインで再生できる。
- 本文プロンプトが 1 つのことだけを問い、identity のブロックは code が組む。frontmatter が欠ける・
  壊れることが構造的に無くなり、`no_title` は到達不能になったので削除した。

### Negative

- クラスタあたりのコール数が 1 → 最大 5（名乗り + 本文 + description + name + 判定）。名乗りで止まる
  クラスタは短い 1 コールで終わり、多数はそこで止まる。
- 抽出後判定は採用済み skill の ~2 割を `duplicate` と言う（読み 3）。誤判定か store の実重複かは
  未分離で、本当に新しいテーマも同じ率で落ちうる。止まったクラスタは台帳に書かれないので、
  再発性に頼る。
- 重複判定の候補側の投影は、再生が測定した形ではない — 再生が 2 つの見出し節を読んだ場所に、
  230 字の散文 head が入る。store 側は本 ADR 以降の最初の採用まで節を保つが、その後は両側とも散文に
  なり、どちらも測定した形ではなくなる。文言と切り詰め幅は不変で、変わったのは入力である。
- 根拠は 1 つの窓の 1 run。ここからプロンプトを詰めると過適合になる — 文言は凍結し、次の読みは
  本番の実数にする。
- 名乗りの再現性は未測定（RFC-0027 の 12 問は各 1 回、temperature 1.0 相当）。`revise` 本文は
  まだ誰も読んでいない。

### 戻すときの費用

重複判定の撤去は呼び出し 1 箇所とプロンプト 2 本。名乗りの撤去はそれに加えて判定 4 語の理由コードと、
それを報告する `VERDICT_ABSTAIN_REASONS` の行。高いのはコール分割の巻き戻しで、プロンプト 3 本・
code が組む frontmatter・保存時の fault 3 語が 1 本のプロンプトへ畳み戻り、その間に採用された store は
2 つの本文様式を抱えることになる。本 ADR は store を 1 件も書き換えないので、巻き戻しても採用済みの
skill は失われない。

### Neutral

- `config/prompts/` が 6 ファイル増え、`insight_extraction.md` は本文コールだけに狭まる。
- eval baseline `comment_golden` が prompt hash の検査で STALE になる
  （[ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.ja.md)、advisory）。再実行と再承認は
  RFC-0042 の残りとまとめて 1 回行う。
- 段の順序は 5 箇所に書かれることになる（本 ADR、RFC-0042、
  `src/contemplative_agent/core/insight.py` の module docstring、
  図の JSON、`CLAUDE.md` の CLI 行）。ゲート・段構成の変更は所有 ADR・script 冒頭コメント・図を
  同じ PR で更新するという CLAUDE.md の鮮度規約が drift を止める。所有者は本 ADR。

## References

- [RFC-0042](../../rfcs/0042-insight-entrance-narrowing.md) — 実装元の提案（項目 2〜4）。
  項目 1 は ADR-0074 の追補として別に出荷済み
- [docs/evidence/rfc-0041/](../evidence/rfc-0041/README.md) — ここの数字すべての出所である凍結済みの
  再生と、それを作った script（`scripts/novelty_tiebreak_replay.py` /
  `scripts/post_extraction_judge_replay.py`）
- [ADR-0074](./0074-weekly-staged-insight.ja.md) — 本段が挟む抽出前 novelty gate。日付つき注記あり
- [ADR-0084](./0084-post-distill-durability-gate.ja.md) — 先例: 成果物の前に置いた judge には
  比べるものが無い
- [ADR-0096](./0096-insight-promotion-worth-abstain.ja.md) — 本 ADR が狭める abstain 理由語彙
  （`no_title` 削除、保存時 3 語追加）。日付つき注記あり
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) — promotion-worth judge を
  退役させた ADR。これがそれと別物である理由を日付つき注記で残した
- [ADR-0075](./0075-observability-by-default.ja.md) /
  [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 監査ログと、それが負う消費計画
- [RFC-0024](../../rfcs/0024-skill-extraction-free-body-split-calls.md) — コール分割と自由記述の本文。
  RFC-0042 に吸収済み
- 実装: `src/contemplative_agent/core/insight_stages.py`、
  `src/contemplative_agent/core/skill_projection.py`、
  `src/contemplative_agent/core/insight.py`、
  `config/prompts/insight_{naming,naming_system,description,name,duplicate,duplicate_system}.md`、
  `scripts/_census_registry.py`、`tests/test_insight_stages.py`、
  `docs/diagrams/pipeline-02-insight-selection.workflow.json`
