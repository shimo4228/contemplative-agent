# T-SKILLSEL-CACHE-COST — プレフィックスキャッシュ仮説の統制 A/B（2026-08-05）

## 目的

2026-08-01 の観察データ層別（enforced p50 56.1s vs フル注入 p50 28.3s、`caller=moltbook.comment`）が
**プレフィックスキャッシュの破壊**で説明できるかを統制実験で確認する。
T-SKILLSEL の enforcement 判断（読み窓 08-07〜）への入力。

## 方法

- ハーネス: [`skillsel-cache-ab-20260805.py`](skillsel-cache-ab-20260805.py)、生データ: [`skillsel-cache-ab-20260805.jsonl`](skillsel-cache-ab-20260805.jsonl)
- モデル/経路: Ollama `/api/generate`、`gemma4:e4b`、`num_ctx=32768` 明示、`num_predict=32`（生成を最小化し prefill を主指標に）、`temperature=0`
- system prompt: 実データで構成 — base 部（`~/.config/moltbook/` の identity + constitution + rules、全コール固定）+ skills 部（実 skill store から 14 ファイル ≈ 25-30K chars）。合計 ~30K chars = 実運用サイズ帯
- user prompt: 全コール同一（コメント返信の代表的なタスク）
- 系列（モデルロードは warmup で吸収、keep_alive 既定 5 分内に連続実行）:
  1. `warmup` — system 空、計測外
  2. `arm1-prime` ×1 — アーム 1 の初回（コールドプレフィル基準）
  3. `arm1-cached` ×5 — **バイト同一** system の反復 = キャッシュヒット期待
  4. `arm2-varied` ×5 — コールごとに skills 部の構成ファイルを 3 つずつずらして入れ替え（base 部は共通プレフィックスのまま、サイズ帯は同一）= skills 部のコールドプレフィル期待
  5. `arm1-revisit` ×1 — アーム 1 の system を再訪（arm2 5 コール後のキャッシュ残存/eviction 確認）
- 主指標: `prompt_eval_duration`（prefill 時間）と `prompt_eval_count`（prefill されたトークン数）。副指標: `total_duration`
- 環境統制: 実施 2026-08-05 10:59〜 JST（launchd 窓 12:00 の前に完了）、開始時 `ollama ps` で他ジョブ不在を確認、production 状態は不変更（読み取りもハーネス素材の value 層ファイルのみ）

## 生データ

実施 2026-08-05 10:59〜11:09 JST 頃（launchd 12:00 窓の前に完了、13 コール全て `done_reason` 正常）。
全行は [`skillsel-cache-ab-20260805.jsonl`](skillsel-cache-ab-20260805.jsonl)。

| コール | system chars | prompt_eval (tok) | **prompt_eval 時間** | total | コールド prefill 速度 |
|---|---|---|---|---|---|
| arm1-prime #0（初回コールド） | 32,380 | 6,202 | **38.85s** | 41.42s | 6.27 ms/tok |
| arm1-cached #1〜#5（バイト同一 ×5） | 32,380 | 6,202 | **0.061〜0.064s** | 2.47〜2.49s | —（キャッシュヒット） |
| arm2-varied #1（skills 部入替） | 56,615 | 10,734 | **75.96s** | 78.68s | 7.08 ms/tok |
| arm2-varied #2 | 47,367 | 9,018 | **61.73s** | 64.43s | 6.85 ms/tok |
| arm2-varied #3 | 33,782 | 6,474 | **41.93s** | 44.36s | 6.48 ms/tok |
| arm2-varied #4 | 30,785 | 5,956 | **37.96s** | 40.57s | 6.37 ms/tok |
| arm2-varied #5 | 29,103 | 5,652 | **35.55s** | 38.12s | 6.29 ms/tok |
| arm1-revisit #99（arm2 5 コール後に再訪） | 32,380 | 6,202 | **3.95s** | 6.61s | —（部分再利用） |

設計からの逸脱 1 点: arm2 のサイズ帯は 29〜57K chars とばらけた（skill store のファイルサイズ差を
ローテーションが拾った）。ただし per-token 正規化（右端列）で全コールドコールが 6.3〜7.1 ms/tok に
一貫しており、arm1 と同サイズ帯の #3〜#5 だけを見ても結論は変わらない。

## 読み

**キャッシュ起因と言い切れる。** 直接証拠は prompt_eval_duration の 3 桁差:

1. **バイト同一 system の反復は prefill をほぼ全再利用する** — 6,202 トークンの prefill が
   38.85s（コールド）→ 0.06s（2 回目以降、5/5 で再現）。**約 600 倍**。壁時計 total でも
   41.4s → 2.5s の **約 16 倍**。
2. **skills 部を入れ替えると毎回フルコールドプレフィルに落ちる** — base 部（identity +
   constitution + rules）が共通プレフィックスでも、arm2 の 5/5 コールが 6.3〜7.1 ms/tok の
   コールド速度（arm1-prime と同一帯）。共通 base による部分再利用は観測されない
   （base が先頭 ~2K chars と小さいためノイズに埋没）。
3. **キャッシュは直近プロンプトで上書きされ、再訪時は部分再利用に劣化する** — arm1-revisit は
   3.95s（即時ヒットの 60 倍遅、コールドの 10 倍速）。セッション内でも異なる system が挟まると
   ヒットは保証されない。

**本番観察（enforced p50 56.1s vs フル注入 28.3s）との整合**: フル注入はバイト同一なので
2 コール目以降 prefill ≈ 0 となり残りは生成時間が支配。enforced は選別で組合せが毎回変わるので
毎コール ~6-10K tok のコールドプレフィル（実測換算 40〜70s）を払う。観察された 2 倍差は
この機序で十分説明でき、むしろ生成時間が両アームに共通に乗る分だけ**比が圧縮された控えめな現れ**。

**T-SKILLSEL enforcement 判断への含意**: ADR-0081 の「83% トークン削減」は API 課金モデルの
利得軸であり、ローカル llama.cpp では**壁時計の損失**になる。選別後プロンプト（~6K tok）の
コールドプレフィル ~39s > フル注入（~17K tok）のキャッシュヒット ~0.06s。トークン削減を
壁時計利得に変えるには、選別結果が呼び出し間でバイト安定（固定順序・固定集合、または
セッション内固定）である必要がある。

**副産物の注意（telemetry）**: 本走行では `prompt_eval_count` がキャッシュヒット時も全数
（6,202）を報告した — 0.06s で 6,202 tok の実評価は物理的に不可能なので、これは「プロンプトの
トークン数」であって「実際に prefill したトークン数」ではない。**キャッシュヒットの検出は
`prompt_eval_duration` でしか見えない**。`cached_tokens` が Ollama 経路で None のままでも、
duration ベースでヒット率の計器化は可能。

**限界**: n=5/アーム（コールド側は prime + 5 で実質 6 点）、単一マシン・単一時点、
生成は num_predict=32 に固定（生成時間の寄与は本番より小さく見える）。ただし主張は
prefill 機序の有無であり、3 桁差 + 5/5 再現で結論には十分。
