---
state: accepted 2026-09-19
review-when: 本番生成モデルが gemma4:e4b から替わる、または skill selection の prompt / catalog の形が変わる（同じ再生が production を再現しなくなる — 標本と arm を測り直す）
---

## Summary

skill selection の判断を、学習なしの 5 arm（自由生成 gemma / enum 拘束 gemma / 同じ gemma の logits 読み / GLiClass 未調整 / opus-5 天井）で過去ログに offline 再生し、読み 1 回で「enum 拘束を修理として起票するか」「蒸留段階へ進むか」を決める。[RFC-0040](0040-jev-system-one-local-decision-backend.md) の蒸留実験案・手順 1 の試験適用。

## Motivation

`core/skill_selection.py::select_applicable_skills` は gemma に skill 名を**自由生成**させ、code が catalog と照合する（`format=` なし、temperature 1.0、`num_predict=400`）。直近 3 週（catalog 53–57、2026-09-19 実測）で:

- judged 行の 19–28% に catalog に無い名前が出る（[RFC-0015](0015-skill-name-hallucination-vs-catalog-size.md) 第 4 読みでは 25.44%、うち語形変化 79%）。伝播は 0 だが、選ばれるはずの skill が落ちる
- 1 コール中央値 18.7 秒、入力 約 5,400 tokens、平均選択数 約 6 / 57

RFC-0040 の問いは「意味判断 → 文字列生成 → parse → 判断の取り出し」を、固定候補への直接 scoring に置換できるか。ここには別々の問いが 2 つ重なっている — **候補外を出せない interface にするだけで戻る分**と、**判断目的で学習したモデルの方が判断が良いか**。前者は学習なしで測れる。後者へ進む前に、未調整の非生成 arm がどこまで届くかを読む。

判断面に skill selection を選んだ理由: 5 面のうち、state + その時点の全候補 + 選択結果をログから再構成できるのはここだけ（`logs/skill-selection-*.jsonl` に prompt / output が base64、2026-07-10〜 の 13,633 行）。relevance / submolt_selection は呼び出しメタデータに sha256 と文字数しか無く、distill_postgate / insight_novelty は [RFC-0042](0042-insight-entrance-narrowing.md) で経路が動いた直後。

## Guide-level explanation

同一標本・同一 catalog・同一 situation に 5 arm を当てる。production は無改変。

| arm | 中身 | 出るもの |
|---|---|---|
| A `free` ×2 反復 | 記録済み prompt をそのまま再生（現行と同じ） | 揺れ幅（自己一致 Jaccard）、幻覚 |
| B `enum` ×2 反復 | 同じ prompt + `format=` で `{"selected": [enum(catalog names)]}`。空配列 = none | 選択集合 |
| C `logits` | skill ごとに「該当するか」を問い、先頭トークンの yes / no を Ollama `logprobs` / `top_logprobs` で読む。sample した答えは使わない | skill 別確率 |
| D `gliclass` | GLiClass 未調整、multi-label、label = `name — description` | skill 別スコア |
| E `ceiling` | `claude -p`（claude-opus-5、ツール無効、situation は untrusted 枠、出力は catalog 名のみで code が enum 検証） | 正解の代理 |

E と他 arm が割れた行だけ、オーナーが目で裁定する。C / D は閾値で切らずスコアを保存し、集合比較が要る箇所は「上位 k = A の選択数」と「0.5」の 2 通りを併記する（単一スカラーに潰さない）。

### 事前に固定した判定基準（2026-09-19、読みの前）

1. **enum 拘束を selector の修理として起票する** ⇔ B の幻覚が構造的に 0、かつ B↔E の一致が A↔E より A の揺れ幅（A↔A 自己一致）を超えて悪化しない、かつ選択数が膨らまない
2. **蒸留段階（RFC-0040 手順 3 以降）へ進む** ⇔ C か D のどちらかが、E との一致で B の揺れ幅（B↔B）の内側に入る。入らなければ RFC-0040 に「CA の skill selection では未調整の非生成 arm は届かない」と記録し、蒸留は別の失効条件（モデル更新等）まで止める

## Reference-level explanation

- **標本**: 直近 3 週・`verdict == "judged"` から、幻覚あり / なしを半々に層別して 150 行前後。seed 固定、抽出した `selection_id` を出力に凍結。prompt の base64 から catalog ブロックと situation を code がテンプレート区切りで切り出す。切り出せない行は理由コードつきで除外して件数を報告する（推測で埋めない）
- **script**: `scripts/skillsel_arm_replay.py` 1 本（`scripts/novelty_replay_ab.py` の型）。`$MOLTBOOK_HOME` に read-only、`llm.configure` を呼ばない。行単位で append・再開可能。arm は直列（16GB で gemma と GLiClass を同時に載せない）。JST 0 / 6 / 12 / 18 時のスケジュールセッション窓では待機
- **依存**: `[dependency-groups] eval` に `gliclass` を追加、`uv run --no-sync python` で起動（ADR-0109 — wheel の床は不変）。モデルの取得は実行前にオーナーの明示許可を取る
- **C arm の成立確認**: `core/llm` は logprobs を露出しないので script 内から localhost の Ollama を直接呼ぶ（許可ホスト内）。着手時に 1 行で `top_logprobs` に yes / no が入るかを確かめ、成立しなければ arm C を理由コードつきで欠番にする（黙って落とさない）
- **D arm の入力長**: checkpoint は着手時に model card の max length で決める。超える場合は label を分割して複数 pass（multi-label は label 独立）
- **出力**: `docs/evidence/rfc-0043/` に集計 JSON（arm 別の幻覚率・選択数分布・自己一致・E との一致（Jaccard、skill 別 precision / recall）・候補順入替 1 回の安定性・latency・メモリ）と読みの README。**situation 本文とデコード済み prompt は evidence に置かない**。オーナー裁定用の行は gitignored のローカルファイルに出し、Claude Code セッションは読まない（untrusted 本文を含む）
- **再生の妥当性**: A arm の幻覚率が production ログの同窓の値と同じ帯に入ることを、再生が production を再現している証拠として README に記す

### 消費計画（ADR-0101）

一発測定（ADR-0075 の 2026-08-29 追補により監査ログ義務の対象外、結果は docs/evidence へ凍結）。(a) 読むのはオーナーと判断役、本実行の完了時 (b) 読み 1 回で上の 2 判定を出す (c) 判定を本 RFC に追記した時点で満了 — script は evidence README の復元手順へ降格するか、そのまま削除する。

## Drawbacks

- E arm で過去の situation 本文（他エージェントの投稿）が Anthropic API へ出る。replay の天井 arm の先例と同じ扱い
- 正解の代理は opus-5 であって ground truth ではない。E 自身の誤りはオーナー裁定の行でしか拾えない
- C arm は 1 行あたり catalog 件数ぶんのコールになり遅い。latency の読みは「interface を変えただけの対照」としての値で、実用速度ではない
- 標本 150 行では skill 別の precision / recall は粗い

## Rationale and alternatives

- **蒸留まで通しでやる**: 評価ラベル数百行・学習依存・16GB での訓練が一度に入り、失敗時に原因を切り分けられない。未調整 arm の読みを先に置けば、進まない判断も安く出せる
- **enum 拘束だけ試す**: 最小だが RFC-0040 の問い（直接 scoring への置換）に答えない
- **SemIf repo をそのまま使う**: Transformers / MLX 用で Ollama 非対応、テスト済みは Qwen 系、排他的な 1 択の設計（2026-09-19 一次資料照合）。モデルと interface が同時に変わり対照群として濁るので、同じ原理を gemma4:e4b 上で再現して「SemIf 型」と記録する
- **RFC-0040 に追記して state を動かす**: state 欄 1 つに「Jev 本体待ち（blocked）」と「代替候補の比較」が同居し、無人 triage の照合と衝突する

## Prior art

- RFC-0040 の比較対象表（Jev / GLiClass / jevlike / SemIf、一次資料照合 2026-09-19）
- `scripts/novelty_replay_ab.py`（RFC-0023）— base64 ログからの differential replay と、同一入力の反復で judge 自身の揺れを床として測る型
- [docs/evidence/rfc-0041/](../docs/evidence/rfc-0041/README.md) — t=1.0 の同一プロンプト 2 反復が Jaccard 0.50 しか一致しなかった読み（揺れ幅を先に測る理由）
- skill `llm-pipeline-layering`（code が列挙し model は enum で名指す）、skill `measurement-discipline`

## Unresolved questions

- Ollama の `logprobs` が `think=False` 相当の呼び出しで先頭トークンに yes / no を返すか（着手時の成立確認で決まる）
- GLiClass のどの checkpoint が 57 label × 説明文 + situation の入力長に耐えるか

## Future possibilities

判定 1 が成立 → enum 拘束の本番投入を別 RFC で起票。判定 2 が成立 → RFC-0040 手順 2 以降（独立評価ラベル、時系列 split、jevlike / GLiClass の学習、offline → shadow）を別 RFC で具体化。

## Status

accepted — 対象面・5 arm・判定基準 2 本・消費計画を確定（2026-09-19、オーナーとの interview）。script は未実装。

## Next action

build セッションへ dispatch: script 実装 → 5 行の smoke（全 arm が通るか、C の成立確認）→ 本実行 → 読み → オーナー裁定 → 判定を本 RFC に追記。
