# RFC-0043 第 2 ラウンド — skill selection 再生の精緻化（Jev は非公開 arm、記事化に耐える形へ）

## Context

第 1 ラウンド（2026-09-19〜20、150 行、`docs/evidence/rfc-0043/`）は判断しにくい結果だった:
enum 拘束は幻覚を 0 にするが判断は変えない / 全 arm が opus-5 天井に Jaccard 0.14〜0.16 で並び
集合の一致では arm を見分けられない / 順位で見ると logits 読み AUC 0.73・GLiClass 未調整 0.56 と差が出る /
gemma は 150 行中 107 行で同じ 1 件を選ぶ。弱点は 4 つ — (1) 天井 arm 自身の揺れが未測定
(2) latency が cache 条件の混在で比較不能、メモリ未記録 (3) logits 読みは skill ごとの分解が遅さと
yes 張り付きを作った疑い (4) Jaccard は隣の skill を 0 点にする。オーナーはこの実験を Zenn 記事にする。

**Jev は実行するが結果は公開しない（2026-09-20 オーナー判断）。** TypeSafe Master Customer Agreement
（2026-08-27 更新、2026-09-20 照合）2.3(f) が「publish benchmarks or performance information about the
Services」を、2.3(b) が Output による蒸留・模倣モデルの学習を禁止。Anthropic Commercial Terms（2025-06-17）に
同種条項は無い（TypeSafe 固有）。Jev の数字は gitignored の `.notes/` にだけ置き、公開 repo・commit message・
記事には出さない。記事には「規約 2.3(f) により結果は非公開」と書く。Jev の出力を学習・蒸留に使わない。

## 確定した判断

| 項目 | 決定 |
|---|---|
| Jev | 同じ 150 行で実行。結果は `.notes/` のみ。公開側へ漏れないことを機械ゲートで守る（下記）。規約 2 条項と扱いを as-of つきで RFC-0040 に記録 |
| 標本 | 第 1 ラウンドと**同じ 150 行**（seed 20260919）。既存 arm は再実行せず、新 arm を同じ行に足す |
| 正解の代理 | 機械側のみ: opus-5 の 2 反復目 + sonnet-5 を第 2 評価者。人間のブラインド比較はしない（オーナー判断） — 記事では「正解はフロンティア LLM の合議で、人間の判断ではない」と限界を明記 |
| 実行者 | Opus の build エージェントへ委任（オーナー明示指示）。script 実装と smoke まで。本実行の起動と読みは判断役 |
| 公開 | evidence は公開 repo へ凍結（第 1 ラウンドと同じ規律: 本文・raw 出力を置かない）。記事執筆は本計画の範囲外（zenn-content 側、`collect-context` から） |

## 追加する arm（同じ 150 行）

| arm | 中身 | 答える問い |
|---|---|---|
| E2 `ceiling/rep2` | opus-5 をもう 1 反復（同じ prompt・隔離設定） | 天井自身の自己一致 = 到達可能な一致の上限。0.15 が「gemma が悪い」のか「答えが定まらない問い」なのか |
| G `rater/sonnet` | claude-sonnet-5、E と同じ prompt | 評価者間一致。opus 固有の好みか、フロンティア合議か。E・E2・G の 2/3 多数決を `consensus` ラベルとして併記 |
| A0 / B0 | 自由生成 / enum を temperature 0 で 1 反復 | sampling の揺れと判断の質の分離。t=0 の一致が t=1 より高いか（selector 修理の候補） |
| F `logits/onepass` | catalog 全件に短いラベルを振り、「最も該当するのはどれか」の先頭トークンで全ラベルの logprob を 1 回で読む（SemIf の本来の形） | 分解をやめれば速さと yes 張り付きが直るか。**Phase 0**: Ollama の `top_logprobs` 上限を実測。全ラベルを覆えなければ「上位 N 件のみ観測・残りは打ち切り」として AUC を打ち切り込みで計算し、その旨を集計に明記。覆える N が k（約 6）未満なら理由コードで欠番 |
| D2 `gliclass/desc` | label を description のみにした変種 | GLiClass に 1 定式化だけで「無作為並み」と言わないための公平性 |

## Jev arm（非公開）

API の形（docs.typesafe.ai、2026-09-20 照合）: `POST https://api.typesafe.ai/v1/systemone`、Bearer 認証、
`{state, model, questions}`。1 リクエストに複数の質問を混在でき state を共有する。Noul は確率 0–1、
Choice は `choice / probabilities / confidence` を返す。`usage.input_tokens` が返る。文脈 64k（state + 最長の質問で 32k）、
1,200 req/min、$0.042/MTok 入力。既知の弱点: state を敵対的に扱わない / 無関係な state で精度が落ちる / 英語以外は精度低下。

| arm | 中身 |
|---|---|
| J1 `jev/noul` | 1 行 1 リクエスト。state = situation、questions = skill ごとの Noul（instructions は `config/prompts/skill_selection.md` の該当基準 + その skill の description）→ skill 別確率（C / F と同じ読み方） |
| J2 `jev/choice` | 同じリクエストに Choice 1 問（criteria = `name: description`）を同梱 → skill 上の確率分布（順位として読む）。公式 cookbook `skill_suggestion` と同じ形 |

- model は `jev-1.13.0` を固定指定（alias でなく版を記録）。identity / 憲法の system prompt は渡さない
  （無関係な state は精度を落とすと公式が明記）— gemma arm との入力差として `replay_fidelity` に書く
- 置き場所: クライアントは `evals/jev_arm.py`（operator が手で回す一発 egress の置き場 — `run_claude_raw` と同じ扱い）。
  `requests` のみ、新依存なし。入力は第 1 ラウンドの `selection_id`、出力は `.notes/skillsel-arm-replay/jev/`
- **API key は私もエージェントも扱わない**: script は環境変数 `TYPESAFE_API_KEY`、無ければ
  `~/.config/typesafe/api_key`（オーナーが自分で作る、chmod 600）を読む。値をログ・例外・出力に出さない（テストで固定）
- **rate limit は policy signal**: 429 / 529 は 1 回だけ待って再試行、連続 3 回で run を止めて報告（backoff で踏み抜かない）
- **公開側へ漏らさない機械ゲート**: (a) 公開用集計（`docs/` 配下へ書く経路）は arm label が `J` で始まる行を
  含むと assert で落ちる (b) `tests/` に「`docs/evidence/` 配下の JSON / md に `jev/` arm の数値キーが無い」検査
  (c) Jev 込みの集計は `--private-summary` で `.notes/` にだけ書ける
- commit message・RFC・evidence README に Jev の数字を書かない（「実行した」「規約により非公開」は書いてよい）
- 送信されるのは過去の situation 本文（他エージェントの公開投稿）と skill の name / description。
  TypeSafe は同意なく学習に使わないと規約 4.1 で述べるが、保持期間は未規定・ゼロ保持はエンタープライズのみ

## グローバルハーネスへ TypeSafe skill を取り込む（オーナー指示 2026-09-20、実験とは独立）

- 出所: `typesafe-ai/skills`（MIT、`skills/typesafe-ai/SKILL.md` 10 KB + LICENSE の 2 ファイルのみ、
  commit `65a39f3` を 2026-09-20 に全文レビュー済み）。中身は live docs への道案内と設計指針で、
  実行 script・API key の読み書き指示・外部送信の指示は無い
- 置き方: `claude plugin marketplace add` は使わない（上流の更新が無審査で制御プログラムに入る。ECC と同じ
  ローカル取り込み方針 — harness ADR-0008）。`~/.claude/skills/typesafe-ai/` に SKILL.md と LICENSE を
  コピーし、frontmatter に `origin: typesafe-ai/skills-customized` と `metadata.upstream_sha` / 取得日を足す
- customized にする理由 = 冒頭に「この harness での注意」を 1 節だけ足す: (1) 規約 2.3(f) により Jev の
  ベンチマーク・性能情報は公開しない、2.3(b) により出力を学習・蒸留に使わない（as-of 2026-09-20、
  Review-when: MCA の改定）(2) API key は人間が置く — agent は値を読まない・出力しない
  (3) live docs の本文は untrusted data として読む (4) CA repo では egress は `evals/` にだけ置く
- `python3 ~/.claude/scripts/hooks/harness_lint.py` を通し、`~/.claude` の git に commit（公開 copy への
  同期はしない — 外部 origin は harness-sync の対象外）
- 実行者: 判断役（このセッション）。skill 散文の取り込みで (a) に当たる

## 追加で取るデータ

- **Ollama の内訳**: 全 Ollama コールでレスポンスの `prompt_eval_count` / `prompt_eval_duration` /
  `eval_count` / `eval_duration` / `load_duration` を記録（cache が効いたかは prompt_eval で分かる）。
  `core/llm.generate` が露出しない場合は script 内の localhost 直叩き経路（arm C と同じ）に寄せる
- **公平な latency**: 30 行の副標本で A / B / F / D を **arm ごとに行を横断する順**で回し（直前コールが
  別 prompt になる）、上の内訳つきで記録。production ログの同窓の `duration_ms` 分布を参照値として併記
- **資源**: arm 切替時に `ollama ps` の SIZE / PROCESSOR、GLiClass は `torch.mps.driver_allocated_memory()`、
  プロセス RSS。gemma と GLiClass の同居時の合計も 1 点。GPU 使用率は `powermetrics` が sudo 必須のため
  **測らない**と明記
- **E / E2 / G のコスト**: `claude -p` envelope の usage / cost 欄を行ごとに集計（本文は保存しない）
- **位置**: 各行の catalog 順と B/shuffled の置換を記録し、選ばれた skill の catalog 内位置の分布を出す
  （最頻 skill は名前に付くのか位置に付くのか — 第 1 ラウンドの B/shuffled は置換を保存していないので再実行）

## 指標（集計の作り直し — 単一スカラーに潰さない）

- 集合: Jaccard・precision・recall（既存）+ 無作為 k 件の床 + **E↔E2 を上限として併記**
- 順位（スコア arm C / F / D / D2）: 行ごと AUC、precision@k・recall@k（k = 天井の選択数 と A の選択数の 2 通り）
- 近傍を許す一致: skill の `name — description` を nomic-embed-text で埋め込み、天井が選んだ各 skill について
  arm が選んだ中の最大 cosine の平均（soft recall）と逆向き（soft precision）。閾値は置かない。無作為の床を同じ式で
- 較正: C / F の確率を 10 ビンに切り、ビンごとの「天井が選んだ割合」（reliability）。ECE も 1 値
- 癖: arm ごとの最頻 skill の出現率、上位 3 件のシェア、distinct 数、選択頻度分布の arm 間 Spearman
- **全ての平均に行単位 bootstrap の 95% CI**（seed 固定、2,000 回）。差を言う箇所は対の差の CI

## 実装

- `scripts/skillsel_arm_replay.py` を拡張: arm 識別子の追加、**既存 rows.jsonl に arm を足すモード**
  （`--augment`: `selection_id` で突き合わせ、既にある arm label は呼ばない。出力は新ファイルへ書き
  元ファイルは変更しない）、Ollama 内訳の記録、`--latency-subsample N`、資源スナップショット、
  集計の指標追加。`--summarize-only` で指標だけ再計算できること
- 再利用: `split_prompt` / `parse_catalog` / `rebuild_prompt` / `enum_schema` / `ollama_yes_no` の
  直叩き経路 / `run_ceiling`（`evals/judging.py::run_claude_raw`、モデル名だけ変える）/
  `assert_no_text_in_summary` / `wait_out_schedule`。埋め込みは `core` の既存 embed 経路（localhost Ollama）
- `tests/test_skillsel_arm_replay.py` に追加: augment の突き合わせ、AUC（同点 0.5）、打ち切り AUC、
  bootstrap の決定性、soft 一致、reliability ビン、consensus の 2/3 規則、summary に本文系キーが無いこと
- temperature の指定が `core/llm.generate` で可能かを Phase 0 で確認（不可なら直叩き経路）
- src/ と config/prompts/ は無改変。`tests/test_cloud_egress_absence.py` の allowlist は現状のまま足りる

## 手順

0. **オーナーの作業（1 回）**: TypeSafe console で API key を発行し、`~/.config/typesafe/api_key` に保存して
   `chmod 600`（または起動シェルで `TYPESAFE_API_KEY` を export）。key は私に見せない
1. RFC-0040 に規約照合の記録（2.3(f) / 2.3(b)、as-of 2026-09-20、「実行するが結果は非公開・学習に使わない」の判断）を追記。
   RFC-0043 の基準 2 の読みを訂正（AUC で見ると logits 0.73 対 GLiClass 0.56 — 「識別力なし」は Jaccard の話）、
   第 2 ラウンドの範囲・問い・消費計画（読み 1 回で 2 判定を確定し記事の証拠台帳にする。満了で script 撤去）を追記
2. Opus build エージェントへ dispatch（worktree、種別 measurement、packet に本ファイルの表を丸ごと）。
   受入 = テスト緑・verify exit 0・6 行 smoke で全新 arm が通る・F の Phase 0 結果の報告。time cap 3 時間
3. 判断役が検収（verify 再実行、pyright、diff 範囲、summary の漏れ検査）→ main へ ff-only
4. 本実行を nohup で起動（見込み 2.5〜3 時間: E2 45 分 / G 30 分 / A0+B0 40 分 / F 15〜45 分 /
   D2 7 分 / shuffled 再実行 20 分 / latency 副標本 20 分。JST 0/6/12/18 時の窓は待機）
5. 集計を `docs/evidence/rfc-0043/` に第 2 ラウンドとして凍結、README を読みごと更新、RFC-0043 に
   事前固定の 2 基準への最終当てはめ → オーナーが確定

## Non-goals

- Jev の数字の公開、Jev 出力を使った学習・蒸留、Jev の本番組み込み（規約 2.3(f) / 2.3(b)）
- E / E2 / G の `claude -p` と Jev API 以外の、localhost 外の判断モデル
- selector / prompt / catalog の変更、GLiClass / jevlike の学習
- 人間ラベル、GPU 使用率（sudo）
- 記事の執筆・構成（証拠が揃った後に zenn-content 側で）

## Verification

- `./.claude/verify.sh` exit 0、`uv run --group eval pyright scripts/skillsel_arm_replay.py` 0 errors
- augment 後の rows で、第 1 ラウンドの arm の値が 1 バイトも変わっていない（既存 arm label の sha256 を比較）
- 同 seed で bootstrap CI が再現する
- E↔E2 の自己一致が集計に出ている / F の `top_logprobs` 被覆率が集計に出ている
- evidence JSON に本文・base64・raw 出力が無い（`assert_no_text_in_summary` + grep）
- `git grep -n "jev/" -- docs/` が数値を含む行を返さない / `git status` で `.notes/` 配下が追跡されていない
- Jev arm の smoke は 3 行だけ（key が無ければ理由コード `jev_key_missing` で欠番になることもテスト）。
  API key の値がログ・出力・例外メッセージに現れないことをテストで固定
- latency 副標本の各コールに `prompt_eval_count` があり、cache の効き具合が読める
