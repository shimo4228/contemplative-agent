---
state: in_progress 2026-09-19
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

in_progress — script と 6 行 smoke まで完了（2026-09-19、`99ad76e` / `18c4ce5`）。本実行と読みは未実施。

smoke で確定したこと（判定には使わない — n=6）:

- arm C は成立: Ollama 0.30.11 は先頭トークンの `top_logprobs` に yes / no を返し、catalog 全件を採点できた
- arm B の幻覚は 2 反復とも 0（enum 拘束の構造どおり）
- **標本の窓は 2026-09-09 以降に縮む**: `selection_id` は RFC-0028 で入った欄で、それ以前の行には無い（21 日窓の 1,664 行中 811 行を理由コード `no_selection_id` で除外、残り 853 行。catalog 54 と 57 が混ざるが、全 arm が同じ行を見る対の設計なので交絡しない）
- system prompt は identity だけでなく憲法も注入して production と同じ長さに再構成した（identity のみだと production の 23% しかなく、再生が production を再現しない）。identity は可変なので、直近の identity 蒸留より前の行は当時と別の system prompt で再生される — 集計の `replay_fidelity` に明記
- arm E は `scripts/` から `claude -p` を直接呼ばず、`evals/judging.py::run_claude_raw`（既存の隔離設定を 1 箇所に保ったまま切り出し）を import する。`tests/test_cloud_egress_absence.py` に「`evals` を import する script は名指しの allowlist のみ」の検査を足した
- arm D の checkpoint は `knowledgator/gliclass-modern-large-v3.0`（学習時の文脈長 8,192、約 1.6 GB）。DeBERTa 系の v3 / instruct は宣言長 512 で、長い入力がエラーにならず学習長の約 10 倍で黙って走るため外した（model card と `config.json` を 2026-09-19 に照合）

### 2026-09-20 — 本実行の読み（150 / 150 行完走、[evidence](../docs/evidence/rfc-0043/README.md)）

arm D の依存は `eval` でなく専用の `[dependency-groups] replay` に置いた（verify の type ゲートが毎回 `eval` を同期するため）。

事前固定の基準への当てはめ（判断役の読み。確定はオーナー）:

1. **enum 修理** — 幻覚 0: 成立（3 反復とも 0%、A は 28.7% / 20.7%）。天井一致が悪化しない: 成立（B 0.158 対 A 0.143、差は A の揺れ幅の中）。選択数が膨らまない: **境界** — 中央値は同じ 6、平均 6.1 → 7.3、最大 16 → 22〜29、自由生成に無かった `parse_failed` が約 1%。A↔B の一致（0.360）は A の自己一致（0.384）とほぼ同じで、enum は判断を変えず候補外の名前だけを消している
2. **蒸留へ進む** — 文面どおりなら C@topk（0.162）が B（0.158）の揺れ幅内に入り成立する。ただし**この成立は空虚**: 全 arm が天井に対し 0.14〜0.16（偶然の床 0.056）に並び、arm 間の差を見分ける力がこの測定に無い。C の確率は 89% が 0.5 以上・中央値 0.995 で yes に張り付き、@topk は同点の中の順位。D（GLiClass 未調整）@topk は 0.058 で偶然の床と同じ

基準の外で出た読み: (a) gemma は 150 行中 107 行で同じ 1 件を選ぶ — 選択の一部は状況でなく癖 (b) 150 行すべてで天井といずれかの arm が割れ、「割れた行だけ裁定」は絞り込みにならなかった (c) 天井 arm の自己一致を測っていないので、低い一致が gemma の判断の質なのか、「どの skill が該当するか」に安定した答えが無いのかを分けられない。

### 2026-09-20 — 読みの訂正と第 2 ラウンド

**訂正**: 上の「測定に識別力が無い」は集合の一致（Jaccard）についてだけ正しい。スコア arm を順位で読むと差が出る —
行ごとの AUC（天井が選んだ skill を選ばなかった skill より上に置けた割合、0.5 が無作為）は logits 読み 0.728、
GLiClass 未調整 0.555。非生成 interface でも同じ gemma なら判断は保たれ、判断目的の別モデルは未調整では届かない。
ただし logits 読みの確率の絶対値は使えない（1 行 54 件中 37 件が 0.99 以上、1 位と k+1 位の差の中央値 0.0003）—
skill を 1 件ずつ単独で問う分解が、遅さ（1 行 約 54 コール）と yes 張り付きの両方を作った疑いがある。

**第 2 ラウンド**（同じ 150 行に arm を足す。既存 arm は再実行しない。判定基準 2 本は動かさない）— 第 1 ラウンドの弱点 4 つに当てる:

| 弱点 | 足すもの |
|---|---|
| 天井 arm 自身の揺れが未測定 | opus-5 の 2 反復目（自己一致 = 到達可能な上限）、claude-sonnet-5 を第 2 評価者、3 票の 2/3 多数決を合議ラベルとして併記。人間ラベルは取らない（正解はフロンティア LLM の合議であって人間の判断ではない、が限界） |
| sampling の揺れと判断の質が混ざる | temperature 0 の自由生成 / enum |
| logits 読みの分解 | catalog 全件にラベルを振り、先頭トークンで全ラベルの logprob を 1 回で読む arm（`top_logprobs` の被覆は実測し、足りなければ打ち切りとして明記） |
| latency が cache 条件の混在で比較不能、資源が未記録 | 全 Ollama コールの prompt 読み / 生成の内訳、arm ごとに行を横断する順の副標本 30 行、`ollama ps`・MPS 確保量・RSS。GPU 使用率は sudo が要るので測らない |
| Jaccard は隣の skill を 0 点にする | 順位指標（AUC、precision@k / recall@k）、埋め込みによる近傍を許す一致、確率の較正（reliability / ECE）、癖の指標（最頻 skill・catalog 内位置）、全平均に bootstrap 95% CI |
| GLiClass を 1 定式化だけで評価した | label を description のみにした変種 |

消費計画は据え置き: 読み 1 回で 2 判定を確定し、満了で script と `replay` group を撤去する。この測定は記事の証拠台帳にもなる。
ホスト型 Jev の扱いは [RFC-0040](0040-jev-system-one-local-decision-backend.md) の「利用規約の制約」— 公開側に数字を置かない。

### 2026-09-20 — 第 2 ラウンドの読み（150 / 150 行完走、[evidence](../docs/evidence/rfc-0043/README.md)「第 2 ラウンド」）

**第 1 ラウンドで分けられなかった問いに答えが出た**: opus-5 は自分自身と Jaccard 0.678 で一致し、sonnet-5 とも 0.436〜0.475。
gemma のどの arm も opus-5 とは 0.143〜0.162（無作為 0.056）。一致の低さは「どの skill が該当するかに安定した答えが無い」
せいではなく、gemma の判断の質。interface（temperature・enum 拘束・logits 読み）を変えても、この値は 95% CI の幅でしか動かない。

事前固定の基準への最終の当てはめ（判断役の読み。確定はオーナー）:

1. **enum 修理** — 成立。幻覚 0（5 反復すべて）、天井一致は自由生成より悪化しない（自由生成 − enum = −0.015、95% CI [−0.032, +0.001]）。
   選択数は平均 6.1 → 7.1〜7.4（temperature 0 では 8.1）、`parse_failed` が約 1%（temperature 0 でも出る — enum は出力 tokens が
   約 2 倍になり `num_predict=400` に当たる）。ただし**代価が 2 つ見つかった**: cache をそろえた副標本で enum は自由生成より遅い
   （13.0 秒 対 9.8 秒）、そして**より安い修理がある** — 自由生成のまま temperature を 0 にするだけで幻覚は 28.7% / 20.7% → 7.3% に減り、
   天井一致は変わらず（差 −0.008、CI [−0.023, +0.007]）、速度も選択数も変わらない。RFC-0042 が insight の判定コールに入れたのと同じ手
2. **蒸留へ進む** — 基準の文面（非生成 arm が enum の揺れ幅内）は logits 読みで満たすが、**進まないことを推奨する**。
   この測定が示したのは「interface を非生成にしても gemma の判断は良くも悪くもならない」であって、蒸留の教師に値する判断が
   gemma の側に無い: gemma は 150 行中 71〜82% で同じ 1 件を選び（候補順を入れ替えても変わらない — 癖は位置でなく名前に付く）、
   その decision trace を小型モデルへ写せば癖ごと写る。GLiClass 未調整は label の書き方で AUC 0.555 → 0.627 に動くが、
   gemma の logits 読み（0.728）に届かない。教師をフロンティア LLM の合議に替える道は別の問い（規約と費用の確認が先）で、本 RFC の範囲外

基準の外で出た読み: (a) 1 回読みの logits は較正が桁違いに良い（ECE 0.116 対 分解版 0.766）が、Ollama の `top_logprobs` 上限 20 のため
catalog の 37% しか観測できず AUC は 0.642 に留まる。全ラベルを読むには Ollama を通さない経路が要る (b) 判断コールの時間は
prompt を読む約 4〜5 秒 + 出力 tokens ÷ 15（M1 のメモリ帯域幅で頭打ち）。本番の 19 秒は単独コールの約 2 倍で、差は未測定
(c) arm を行ごとに回したため gemma と GLiClass が同居し、16 GB の機体で swap が 17 GB まで膨らんだ — 計画は「arm は直列」だった。
検収で見落とした（CLAUDE.md の開発環境に運用則として記録済み）。

### 2026-09-20 — オーナーの確定

1. **selector の修理**: 成立。temperature 0 を先に入れ、enum 拘束はその上で受入条件つきで判断する → [RFC-0044](0044-skill-selector-temperature-zero.md)
2. **蒸留**: 進まない。gemma の decision trace は教師に値しない（71〜82% の行で同じ skill を選ぶ癖ごと写る）。RFC-0040 に戻した

読みは 1 回で 2 判定を出し、消費計画の (b) は満了。

### 2026-09-22 — 第 3 ラウンド: arm 実装済み、実測待ち

[RFC-0040](0040-jev-system-one-local-decision-backend.md) が accepted になり、同じ 150 行の harness に
ローカル判断モデルの 3 家族 7 label（H 判定モデルの logits 読み / K kev / L Laya）を足した。
arm と test と実行手順まで（`--help` に新 flag が出る）。**実測はまだ走っていない** — 読みの枠は
[evidence](../docs/evidence/rfc-0043/README.md)「第 3 ラウンド」に空欄で置いてある。
下の「後始末」はこの読みが終わるまで待つ。

## Next action

第 3 ラウンドの実測（H → K → L を直列に、JST 0 / 6 / 12 / 18 の窓を避けて）と evidence への凍結が先。
そのあと後始末: この測定を記事の証拠台帳にまとめ終えたら、`scripts/skillsel_arm_replay.py`・`evals/jev_arm.py`・それぞれのテスト・`[dependency-groups] replay` を撤去し、evidence README に復元手順（commit SHA）を残す（RFC-0041 の測定 script と同じ扱い）。公開ツリーに非公開 arm の label が入らないことの検査は、script の撤去後も残す。
