---
state: resolved 2026-09-19
state_since: 2026-09-08
review-when: 固定セット比較で変更理由を扱う利点が読めない、生成モデルが変わる、または RFC-0021〜0024 の決着で本提案の前提が変わる
---

## Summary

経験からスキルの変更理由を抽出し、再確認・修正・新規を区別するパイプラインを検討する。全面実装の前に一回限りの固定セット比較で前提を確かめる。

目指すのは、経験の蓄積が必要な行動上の変化へ戻り、その変更を出典とともに辿れ、オーナーと
Claude Code の日常的な選別・修理を要しなくなること。北極星は
[ADR-0080](../docs/adr/0080-north-star-layered-end-state.md) とその 2026-08-26 追補を使う。
スキル数・採用率・特定の人格や文体を目標にしない。人間の承認権限は残す。

## Motivation

現行実装を 2026-09-08 に照合した。以下の「構造」は確認済みで、そこから生じる取り逃しや負荷の
因果については検証を要する仮説である。

| 現在の構造 | 問い直す前提 | 提案する扱い |
|---|---|---|
| 類似する観察をクラスタ化し、最低 3 件から抽出 | 話題の反復は再利用できる行動の発見と同じか | 適用条件・手順に何が加わるかを問う。頻度は材料の一つ |
| 既知テーマとの重複を抽出前に除外 | 同じテーマの訂正・例外まで重複に見えていないか | 再確認と修正を分ける |
| 新規スキル本文を生成し、後段で選別 | 本文を作る前に変更理由を明らかにできないか | 変更理由がある場合だけ本文を作る |
| 選択回数・名前の混同を読む | 選択されたことは生成への寄与を示すか | 選択・生成への影響・環境の反応を別々に読む |

根拠となる現行の入口は [insight.py](../src/contemplative_agent/core/insight.py) の
`_build_cluster_batches` / `_extract_skill` と
[insight_extraction.md](../config/prompts/insight_extraction.md)。抽出指示は一つのスキルへの合成を求め、
`NOTHING-PROMOTABLE` の棄権経路も持つ。棄権できない実装だとは主張しない。

[insight_novelty.py](../src/contemplative_agent/core/insight_novelty.py) の `_load_known_themes` は、
採用済みスキルに加えて過去の staging 台帳も採否にかかわらず既知テーマとして読む。
再提示の抑制にはなるが、「以前の提案は不十分だったが、新しい証拠で改める」経路と緊張する。
**実際に訂正を取り逃したかは未検証。**

負荷の歴史的な根拠は [ADR-0097](../docs/adr/0097-consolidator-dissolution-and-skill-store-exit.md) の
7 週間で 438 候補・53 採用という記録。これは当時の値で、現在の率へ外挿しない。
入口と出口の修理を続けるだけで自己調節へ到達できるかを、本 RFC は問い直す。

## Guide-level explanation

提案する循環は次の形。

```text
対話・行動・観測できた反応
  → 具体的な観察と出典を保存
  → 関連する過去の観察と対比
  → 再確認 / 材料不足 / 既存スキルの修正 / 新規スキル を区別
  → 変更がある場合だけ、根拠と差分を人間が承認
  → 選択・生成・環境との対話へ戻る
```

### Observations are a valid outcome

理解や気づきは観察として残ってよい。経験ごとに行動指針を作る必要はない。
スキル化しない観察も、後の対比や価値層の変化の根拠になる。
初期比較では既存の per-episode distill と knowledge store を流用し、新しい wiki 層は作らない。

類似した観察に加えて、適用条件の違い・従来の説明に収まらない例外も材料にする。
単発の観察を候補検討から一律に落とさず、証拠不足なら指針へ昇格しない。
頻度・新規性・重要性・環境の反応は別々の根拠として扱い、単一スカラーへ還元しない。
新しい重要度 scorer の復活を意味しない（ADR-0080 追補と ADR-0056 の境界を維持）。

### State the reason before writing a skill

本文を作る前に、何を根拠にどの判断が変わるのかを短く表す。例えば、
「従来は A の場面全般に適用していたが、今回の観察では B という条件を区別する必要がある」
という形。これは説明の例で、固定出力様式や特定の行動内容の指定ではない。

| 結果 | スキルの扱い | 根拠の扱い |
|---|---|---|
| 再確認 | 本文を変更しない | 同じ判断を支持する観察として残す |
| 材料不足 | 本文を作らない | 不明点を保ったまま観察に残す |
| 修正 | 対象スキルの適用条件・手順の変更を提案 | 対象の版、出典、変更理由を対応づける |
| 新規 | 既存スキルでは表せない指針を提案 | 何が新しいかと出典を対応づける |

これらは設計上の区別であり、永続状態機械を新設する決定ではない。
保留候補を毎週人間へ再審査させる台帳は増やさない。新しい証拠によって再検討できるようにするが、
以前の却下理由や承認履歴を無視して同じ提案を再送しない。再検討の条件は未決。

### Keep evidence and reusable guidance connected

具体的な証拠は既存の観察記録と出典 ID に保持し、本文は適用条件と行動を簡潔に表す。
相手とのやり取りを本文へ引用して固定・公開する方向は取らない
（[RFC-0024](0024-skill-extraction-free-body-split-calls.md) の 2026-09-07 著者判断）。
本文と description の分離、固定節構成の緩和は、変更理由を表現する後段として検討する。

同じモデルに新たな合否 judge を足すことは本案の前提にしない。変更理由の生成も誤りうる仮説で、
機械的に確認できる出典・対象版・形式の検証とは区別する。
以前のスキルを読ませることによる語彙の自己模倣も検証対象に含める。

### Make approval proportional to actual changes

人間へ渡す単位は「この経験を理由に、この判断をこう改める」という根拠と差分。
変更がなければ定例の候補選別を要求しない。新規・修正・退役の実行はいずれも人間の承認を通す。
退役は既存の archive 経路を使う方向で、本案は意味的類似による自動 merge を導入しない。

選択されたこと、生成に影響したこと、環境が反応したことはそれぞれ異なる観測である。
選択率を有用性と同一視しない。環境の反応を成功ラベルや報酬へ自動変換しない。
反応がない、または対応関係を確認できない場合は不明とする。
承認されやすいテーマや好ましい人格へ候補を寄せることも目標にしない。

## Reference-level explanation

### Scope and existing work

本 RFC はパイプラインの前提と初期比較を扱う。既存 RFC の実装・待機条件・状態をこの起票で変更しない。

| 関連項目 | 本案との関係 |
|---|---|
| [RFC-0021](0021-skill-stocktake-family-saturation.md) / ADR-0105 | 出口の候補生成と、archive 後の 2 窓読みを持つ。本案の採否をその読みが代替するわけではない |
| [RFC-0023](0023-novelty-gate-retrieval-and-rare-lane.md) / ADR-0104 | 既知候補検索は流用候補。covered/NEW の区別と希少レーンは本案の採用時に整合を取る |
| [RFC-0024](0024-skill-extraction-free-body-split-calls.md) | 本文・description の生成を担う候補。本案はその前の「何を変更するか」を扱う |
| [RFC-0017](0017-insight-extraction-redesign.md) / ADR-0103 | WikiSkill 形は退役済み。残された比較記録を参照し、wiki 復活を前提にしない |

本番化する場合の候補箇所は `core/insight.py` / `core/insight_novelty.py` と抽出プロンプト、
staging / adopt の変更対象・出典・版の受け渡し、週次ゲートの提示内容。
モジュール分割・コール数・schema は初期比較後に決める。既存スキルの更新を扱うなら、
人間ゲートまでに対象が変わった場合の版照合と、承認・却下・置換を辿れる記録が必要になる。

本番経路への採用時は、所有 ADR、新旧判断との関係、該当 script の冒頭コメント、該当する
[設計図](../docs/diagrams/README.md)を同じ変更で整合させる。
監査は ADR-0075 の production 契約に従う。一回限りの比較は結果の evidence 凍結で扱う。

### First comparison and consumption plan

全面実装の前に、既存記録の小さな固定セットで**一回限りの比較**を提案する。
実行前にケース数・選び方・判断方法・予算・停止条件を固定する。今回の起票は実験実行の承認を含まない。

1. 再確認、適用条件の変化、既存にない発見、材料不足を含む記録を選ぶ。
   入力にはその時点の既存スキルと観察を対応づけ、未来の記録を混ぜない。
   診断用の区分であり、Moltbook 上の行動に客観的な成功・失敗ラベルがあるとは扱わない。
2. 現行抽出と、変更理由を先に扱う案を、同じ観察・スキルのスナップショットと同じモデルで比べる。
   生成元の観察を評価にも使う循環を避け、適用確認には抽出に使っていない別の場面も用意する。
3. 根拠のない一般化、必要な変更の取り逃し、変更不要な場面での候補生成、
   本文と description の対応、人間が読み解く負担、コール数と所要時間を別々に読む。
   事前に指定した読み手が出典と照合し、判定者の推論も観察事実と分ける。総合点で採否を決めない。
4. 本番 store・staging・公開先には書かず、結果を `docs/evidence/rfc-0027/` に凍結する。
   公開するのは公開可能な集計・差分の説明と制約で、第三者の原文や個人情報を転記しない。

### Bounded implementation

この RFC の比較を実行するための読み取り専用ハーネスを
`scripts/insight_revision_compare.py` に置いた。
入力は `schema_version: 1` の明示的なケース JSON（観察 ID・本文・既存スキルのスナップショット）だけで、
現行 arm と理由先行 arm を同じ入力へ適用する。理由先行 arm は
`reconfirm` / `insufficient` なら本文生成を呼ばず、`revise` / `new` だけ本文候補を作る。
理由 JSON が壊れた場合は候補を作らず、出力には `parse_error` または `invalid` を残す。

ハーネスは packaged prompt を明示的に読み、`MOLTBOOK_HOME`、knowledge store、skills、staging、
run marker を読まない。出力先は `docs/evidence/rfc-0027/` 配下へ限定し、既存の insight / adopt 経路へ
接続していない。各 arm の実呼び出し数・所要時間と、比較対象の raw output は観察成果物として記録するが、
winner、閾値、採用判断は生成しない。入力 fixture は
`evals/fixtures/insight_revision_cases.json` に置いた。
これは実験結果ではなく、実験を一回実行する前の実装である。

消費計画（ADR-0101）:

- **誰が・いつ読むか**: 本 RFC の設計セッションでオーナーが比較結果と制約を読む。
- **何回で何を決めるか**: 事前固定した一回の比較で、変更理由を扱う案の限定実装へ進むか、
  モデル要件またはスキル層の役割を再検討するかを決める。判定不能も明示的な結果にする。
- **満了時の撤去条件**: 読みを記録したら比較専用の実行経路を撤去し、凍結 evidence を残す。
  定期計器にしない。差が読めなかったことだけを理由に judge や再試行ループを追加しない。

## Drawbacks

- Gemma が観察間の違いと変更理由を保てるかは未検証。コール分割だけで解決する保証はない。
- 類似例だけでなく対比例を集める段は検索漏れや選択偏りを持つ。希少な経験を一律に落とさないことと、
  全記録を毎回読むことは別であり、有限の入力予算でどう扱うかが残る。
- 修正中心にすると既存スキルへの固着や本文の肥大が起こりうる。新規を無理に修正へ押し込まない。
- 採用基準を「オーナーが好む内容」に寄せれば、観察対象の進化を誘導する。変更理由の検証と内容の選好を混ぜない。
- 成功・失敗の ground truth がないため、限定比較から対話全体の有用性や長期的な自己調節を証明できない。
- 人間承認と変化の継続には一定の判断負荷が残る。固定の週次選別を減らすことと、負荷の完全消滅は同じではない。

## Rationale and alternatives

| 案 | 判断材料 |
|---|---|
| 現行の抽出形式と退役だけを改善 | 最小の修理。ただし新規生成と後段選別を中心とする構造は残る |
| **変更理由を中心に再確認・修正・新規を扱う** | 本 RFC の第一候補。経験の蓄積とスキル数の増加を切り離し、変更を辿りやすくする仮説 |
| 書き手のモデル・実行環境を見直す | 第一候補が小型モデルで成立しなければ再検討。ローカル性・資源・運用負荷・費用の検証が必要 |
| スキル抽出の役割を縮小する | 有効性を確認できなければ検討。ただし経験が行動へ戻る経路と研究上の問いを再定義する必要がある |

モデル変更やスキル層の縮小は本 RFC で採用していない。各案とも、能力向上を北極星の代替にしない。

## Prior art

- [ADR-0080](../docs/adr/0080-north-star-layered-end-state.md): 層別の北極星、日常的関与なく回る代謝、
  複数軸の質、人間ゲートの権限と負荷の区別。
- [ADR-0097](../docs/adr/0097-consolidator-dissolution-and-skill-store-exit.md): 候補選別の歴史的負荷と、
  promotion-worth judge が全件 promote したため退役した記録。judge の追加を既定解にしない根拠。
- [ADR-0103](../docs/adr/0103-retire-the-wiki-mechanism.md): 同じ形の wiki 実験でモデル間の具体性が異なった記録。
  本案を小型モデルで成立すると断言できない根拠。
- [RFC-0017 の 2026-09-02 Reading](0017-insight-extraction-redesign.md): 12 ケース × 3 サンプルの
  skills-on/off 比較は判定不能。スキル無効の証明にも、新案の有効性の証明にも使わない。
- [ADR-0105 の初回読み](../docs/evidence/adr-0105/dry-run-20260907.md): 混同対が既存の退役候補に
  足した新名は 0 件。出口一般の無効性を示すものではなく、当該一回の追加信号の読み。
- [Trace2Skill v5, §2](https://arxiv.org/html/2603.25158v5): 実行経験から既存スキルの変更を提案する先例。
  正誤が検証できるタスクと成功・失敗の軌跡を土台にするため、Moltbook の対話へ判定構造を直接移植しない。
  一次本文照合は 2026-09-08。CA の小型モデルで本案が成立する証拠ではない。

## Unresolved questions

- どの観察を対比に選ぶか。希少な例外と材料不足を、頻度の床や類似度の単独閾値なしにどう扱うか。
- 再確認と修正を区別できる最小の入力・コール構成は何か。既存スキルの語彙の自己模倣をどう見分けるか。
- 以前の却下理由・採用・退役と、新しい証拠による再提案をどう接続するか。
- 変更理由と証拠の評価を誰がどの契約で担うか。出典の存在確認だけでは内容の妥当性を保証できない。
- 初期比較のケース数、読み手、判断方法、予算、停止条件をどう事前固定するか。
- 限定比較を通った場合、どの範囲の本番観察なら自己調節と人間負荷への効果を確認できるか。

## Future possibilities

限定比較で前提が支持された場合にのみ、既存 staging を使う小さな実装範囲を設計する。
長期的な変化の記録は既存の縦断データへ接続し、別の知識層や常設評価パイプラインの増設を既定にしない。

## Status

draft（2026-09-08）。オーナーの依頼で、北極星から抽出パイプラインを見直した提案を RFC 化し、
一回限りの比較を行う境界付きハーネスまで実装した。比較実行と本番実装の採用は未決。
既存 RFC の状態と運用は変更していない。

## Next action

ケース選定・判断方法・資源予算・停止条件を先に具体化し、実験の承認後に一回だけ比較する。
読みを受けて限定実装・モデル要件の再検討・スキル層の役割の再検討のいずれかを選ぶ。

## 2026-09-09 triage 照合（無人 cycle）

`draft` 維持。ハーネスは main（`6d17266`〜`ffec2c2`）に入り、`docs/evidence/rfc-0027/` は未生成 = 比較は未実行。
残る決定は著者: ケース選定・判断方法・予算・停止条件の事前固定と一回限りの実行承認（digest に提示）。
stale branch `codex/rfc-0027-comparison`（`d38614a`、main の `6d17266` の旧版で main が上位互換）は削除候補。

## 2026-09-09 決定（著者回答: RFC-0021 の第 1 窓の後に回す）

`draft` 維持。一回限りの比較は RFC-0021 の 2 窓読みの第 1 窓（2026-09-12 土曜ゲート）を見てから
ケース選定・判断方法・予算・停止条件を固めて実行する。照合先: RFC-0021 の消費計画の記録。
stale branch `codex/rfc-0027-comparison` は同日削除（main が上位互換）。

## 2026-09-12 triage 照合（無人 cycle）

2026-09-09 決定の待ち条件（RFC-0021 第 1 窓）は `644775f` で成立。残るは著者によるケース選定・判断方法・予算・停止条件の事前固定と実行承認（digest に提示）。`draft` 維持。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。ケース選定・判断方法・予算・停止条件は著者と 1 問ずつ固定してから measurement として dispatch。

## 2026-09-12 事前固定（著者回答、4 問）

1. **ケース**: 本番記録から 12 件（reconfirm / insufficient / revise / new の各区分 3 件）。knowledge.json の
   パターンとその時点の skills スナップショットから build が選び、選び方・除外基準を evidence に記録。合成 4 件
   （`evals/fixtures/insight_revision_cases.json`）は smoke として併用。第三者原文は evidence に転記しない
2. **判断方法**: 読み手はオーナー。build は軸別の事実だけ出す（両 arm の raw 出力・コール数・所要時間・出典照合 =
   evidence_ids が観察に実在するか）。一般化・取り逃し・読み解く負担の 3 軸はオーナーが読む。judge は置かない
3. **予算**: gemma4:e4b ローカル（本番と同じモデル）、JST 0/6/12/18 のセッション窓と weekly を避けて実行。費用ゼロ
4. **停止条件**: 1 回で終了、再試行なし。parse_error / invalid はそのまま記録。ハーネスのバグで全件失敗した場合のみ
   修理後に 1 回だけ再実行を許す

dispatch は measurement（S14）として WIP が空き次第。

## 2026-09-12 build（S14 measurement — 一回限りの比較を実行した）

事前固定（4 問）どおりに一回だけ実行した。**判定は含まない** — 軸別の事実は
[`docs/evidence/rfc-0027/comparison-2026-09-12.md`](../docs/evidence/rfc-0027/comparison-2026-09-12.md)、
選び方と除外は同ディレクトリの [README](../docs/evidence/rfc-0027/README.md)。読みはオーナーが行う。

- **ケース**: 本番記録から 12 件（各区分 3 件）。選定は新設の read-only スクリプト
  `scripts/rfc0027_select_cases.py`。knowledge.json を 1 回だけ load し、
  書き込みは `docs/evidence/rfc-0027/` と `evals/fixtures/` に限定。区分は coverage（ケース重心と最近傍 skill の
  cosine）× cohesion（ケース内の平均相互 cosine）の 4 隅で、**診断ラベルであり成否ラベルではない**。
  閾値はこの corpus の分位（nomic の圧縮された帯に絶対値を置かないため）。
  ケースは `evals/fixtures/rfc0027_production_cases_20260912.json`（`schema_version: 1`）。
  適用確認用の holdout（別日の最近傍観察、どちらの arm にも与えていない）は case schema が追加キーを拒むため
  `case-selection-20260912.json` に同梱。
- **公開規約**: URL・`@handle`・25 文字以上の引用span を含むパターンを母集団から除外
  （窓内 live 6,709 件中 4,838 件が該当）。残るのは 1〜3 語の術語引用のみで、第三者の原文・handle・link は
  evidence に無い。
- **smoke**: 合成 4 件で `--arm both` 1 回（`smoke-20260912.json`）。2 コール経路も 1 回発火した。
- **本比較**: 12 件 `--arm both`、gemma4:e4b ローカル、2026-09-12 15:35–15:55 JST（セッション窓の外）、再試行なし。
  current arm 12 コール / 904.0 s、proposed arm 12 コール / 268.5 s。
  proposed arm は 12 件すべてで kind を名乗り、うち 4 件が `parsed`（いずれも kind = `reconfirm`）、
  8 件が `invalid`（名乗った kind は revise 3 / insufficient 3 / reconfirm 2）。
  `invalid` の機械的な理由は「供給カタログに無い skill 名を target にした」3 件
  （うち 2 件は供給済み skill 名から `-YYYYMMDD` 接尾辞を落としたもの、1 件はどこにも無い名前）、
  「非 revise に target を付けた」1 件、「観察に無い evidence id」4 件。
  本文生成コール（`revise` / `new` のときだけ発火）は今回 1 件も発火していない。
  current arm は 12 件すべて出力を返し、うち 2 件が `NOTHING-PROMOTABLE`（棄権）。
- **記録の限界**: ハーネスは proposed arm の理由コールの所要時間をケース単位で保存しない（arm 合計のみ）。
  今回は候補コールが 0 だったため 268.5 s は全て理由コール（平均 22.4 s/件）。

- **実行後に見つかった欠陥（レビュー指摘、同日）**: 選定スクリプトの case_id が区分ラベルで始まり、
  ハーネスは `case_id` を current arm の抽出プロンプト（`{subcategory}`）へ渡す。つまり
  **current arm は 12 件すべてで区分ラベルを見ており、proposed arm は見ていない**（非対称）。
  事前固定が「1 回・再試行なし」なので実行はこのまま凍結し、欠陥を明記して報告する。
  再実行するなら先に case_id を不透明化する（`scripts/rfc0027_select_cases.py` の `_case_row`）。
  再実行の可否はオーナーの判断。

消費計画どおり、読みを記録したら比較専用の実行経路を撤去する。定期計器にしない。

## 2026-09-12 build 追記（S14 — ハーネス修理と 1 回だけの再実行）

初回の欠陥（case_id が current arm の抽出プロンプトへ漏れる）を著者が**ハーネスのバグ**と認め、
事前固定の例外条項（バグの場合のみ修理後 1 回だけ再実行）を適用した。

- **修理**: `scripts/insight_revision_compare.py` の `{subcategory}` は case_id でなく、ケース任意欄
  `subcategory`（無ければ定数 `observation`）を受ける。`subcategory` に case_id を含むケースは拒否する。
  回帰は `tests/test_insight_revision_compare.py::test_neither_arm_sees_the_case_id_or_its_selection_label`
  （両 arm のどのプロンプトにも case_id・区分ラベル・日付が入らないことを固定。修理前のコードで RED を確認）。
- **再実行**: 同じ 12 件（fixture は byte 一致、sha256 `445857b1…`、prompt hash も初回と同一）で
  `--arm both` を 1 回。2026-09-12 16:12–16:32 JST（セッション窓外）、再試行なし。
  current 12 コール / 835.4 s、proposed 13 コール / 378.9 s。
  proposed arm は `parsed` 5 件（reconfirm 3 / revise 1 / insufficient 1）、`invalid` 7 件
  （名乗りは revise 4 / insufficient 2 / reconfirm 1）。**本文生成コールが 1 件発火**
  （`revise-p08206-2026-09-08`、target は供給済み skill）。
  `invalid` の理由は「供給カタログに無い target」4 件（**4 件とも `-YYYYMMDD` 接尾辞落ち**、
  初回にあった実在しない名前は今回 0）、「非 revise に target」1 件、「観察に無い evidence id」2 件。
- **初回の結果は削除せず残す** — 欠陥を明記した evidence として
  [`comparison-2026-09-12.md`](../docs/evidence/rfc-0027/comparison-2026-09-12.md)、
  修理後は [`comparison-2026-09-12-rerun.md`](../docs/evidence/rfc-0027/comparison-2026-09-12-rerun.md)。
  どちらも軸別の事実のみで、arm の優劣は書いていない。

## 2026-09-12 merge（判断役の検収 → 著者の merge 語）

S14 `77bd33a` + `77af40c` を main へ ff merge（`77af40c`）。比較は完了、evidence は `docs/evidence/rfc-0027/`（初回 = ラベル漏れあり、再実行 = 修理後・例外条項適用）。**state は `accepted` のまま — 残るのはオーナーの読み**（消費計画: 限定実装 / モデル要件の再検討 / スキル層の役割の再検討のいずれかを 1 回の読みで決める。判定不能も明示的な結果）。読み後に本 RFC の次の状態（accepted で限定実装へ / resolved / withdrawn）を決め、比較専用の実行経路の撤去（消費計画の満了条件）を起こす。

## 2026-09-16 triage 照合（無人 cycle）

`accepted` 維持。S14 の比較は 2026-09-12 に完了し `77af40c` で main に入っている。dispatch 対象は無い（measurement は消化済み）。残るのはオーナーの読み（限定実装 / resolved / withdrawn / 判定不能の明示）— digest に再提示。読み後に比較専用経路 `scripts/insight_revision_compare.py` の撤去（消費計画の満了条件）を起こす。

## 2026-09-17 決定（著者回答: 名前照合を緩めてもう 1 回だけ再実行）

09-12 再実行の読み: proposed arm の `invalid` 7 件はすべて比較スクリプト自身の文字列チェック
（`scripts/insight_revision_compare.py` の `_parse_reason`）で落ちたもので、モデルの判断内容ではない —
`-YYYYMMDD` 接尾辞落ち 4 / untrusted wrapper のタグ名を evidence id に書いた 2 / reconfirm に target 1。
2 段目（本文生成）に進んだのは 1 件だけで、比べたかった「修正として書いた本文」がほぼ無い。
著者はこれを測定器の欠陥と認め、事前固定の再実行例外を **2 回目として明示的に適用**した（1 回目は
09-12 の case_id 漏れ）。あわせて、比較スクリプト群（compare 478 行 / 選定 460 行 / 描画 229 行 / テスト
約 450 行 / evidence 約 1,400 行）は 12 件の目視比較には過大だったと読む — 原因は 09-08 の起票セッションが
承認前に本番向けの厳密契約を持つスクリプトを出荷し、以後の事前固定・build・検収がその存在を前提に
積み上がったこと。撤去は消費計画どおり読み後に行う。

修理は照合の緩和のみ（接尾辞落ちを完全名に引き戻す / evidence id と reconfirm の target は記録のみで
止めない）。プロンプトと 12 件は byte 不変。dispatch は S17（Opus Agent、worktree
`task/s17-rfc0027-rerun`）、実行は 19:05 JST 以降に 1 回。evidence は `comparison-2026-09-17-rerun2.md`。

## 2026-09-17 merge（判断役の検収 → main へ ff merge）

S17 `dd0dc7a` を main へ ff merge。検収: diff は packet の範囲内（プロンプト / fixture / src / rfcs /
09-12 の evidence は無変更、prompt sha256 4 本と input sha256 は 3 run で同一）、verify は判断役が
worktree と main の両方で再実行し exit 0、chain は fix 種別の Code Review を Opus サブエージェントで
1 回、逸脱 3 件は理由付きで名指し（重複 evidence id を flags 扱い / 全 invalid 行に invalid_reason /
非 revise の target は 2 段目へ渡さない）。3 回目の run（19:39–20:04 JST、1 回のみ）は proposed arm
12 件すべて parsed、2 段目 5 回発火、revise 5 件の target は全部が接尾辞落ちで一意に解決。
evidence は `docs/evidence/rfc-0027/comparison-2026-09-17-rerun2.md`。

**state は `accepted` のまま — 残るのはオーナーの読み**（09-12 merge 節の消費計画と同じ: 限定実装 /
モデル要件の再検討 / スキル層の役割の再検討 / 判定不能 のいずれかを 1 回の読みで決め、読み後に
比較専用経路を撤去する）。diff 外 findings 2 件（LOW、renderer の docstring と CASES の固定）は
commit body に残し起票しない。

## 2026-09-19 triage 照合（無人 cycle、stocktake 併走）

`accepted` 維持。3 回目の run（S17 `dd0dc7a`）の読みはオーナー未着手。同日の土曜ゲートで RFC-0041 が accepted になり、その結論が出た時点で本 RFC を `obsoleted` にする見込み（著者: 今は動かさない）。読みを別途行うか、0041 の設計対話に吸収するかは digest に提示。dispatch 対象なし。

## 2026-09-19 オーナーの読みと決着

`accepted` → `resolved`。3 回目の run（`comparison-2026-09-17-rerun2.md`）を軸別の事実で読んだ結果: 限定実装へ進む。
名乗り（reconfirm / insufficient / revise / new）は本番経路へ移し、書式違反は欄の enum 拘束（`target_skill` は供給名、
`evidence_ids` は観察 id）とコール分割で消す — 3 回目の違反はどれも無拘束の `string` 欄から出ていた。実装は
[RFC-0042](0042-insight-entrance-narrowing.md) の作業項目 2、比較専用の実行経路の撤去（本 RFC の消費計画の満了条件）は同 7。
読みが残した未決: 名乗りの再現性（各 1 回の run）と `revise` 本文の質は未測定で、RFC-0042 の Drawbacks が引き継ぐ。
