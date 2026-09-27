# RFC-0040 第 4 ラウンド: ローカル Jev 型判定モデルを Opus 5.5 ループで gemma 超えまで回す

## Context

- **現状**（2026-09-22、RFC-0043 第 3 ラウンド）: 市販のローカル Jev 型 3 家族（qwen logits / kev-0.8b / Laya）は skill selection で gemma に届かず、RFC-0040 は `blocked`。seam（ADR-0112 `DecisionBackend`）は main に入り既定無効。測定 harness `scripts/skillsel_arm_replay.py` は `2bcc274` で撤去済み（復元元 `817ecf3`）。
- **何が変わったか**（2026-09-24 一次資料照合）: **kev の MLX backend が 2026-09-22 に merge**（PR #43）— RFC-0040 Next action の待ち条件 (a) がそのまま発火。加えて **wfzyx/von 1.2**（ModernBERT-Large 395M、8,192 窓、MPS 明記、`von serve` が TypeSafe 互換 `/v1/systemone`）が CA 未測定。Ollama の `top_logprobs` 上限 20 は据置き。
- **超える線**: gemma enum（arm `B/enum`、opus-5 天井との Jaccard@topk 0.158 [0.14, 0.18]）と gemma logits 読み（`C/logits` 0.162、AUC 0.728）。
- **オーナー決定（本セッション）**: ループが動かすのは**新規候補モデルの追加だけ**（fine-tune・state 設計変更・Ollama 別モデルは範囲外）。Opus 5.5 は**ループ駆動役だけ**（天井ラベルは既存の opus-5 ×2 + sonnet-5 をそのまま使う → 新規ラベル費用ゼロ）。

## 標本数 — 150 は要らないが 5 では読めない

既存 evidence JSON から逆算した per-row のばらつき: Jaccard SD ≈ 0.12（gemma）、AUC SD ≈ 0.14。候補が大きく跳ぶ場合対差の SD ≈ 0.25。

| n | 対差 CI の半幅（Jaccard） | 読めるもの |
|---|---|---|
| 5 | ±0.22 | 何も読めない（大きな差でも CI に埋もれる） |
| 30 | ±0.09 | 大きな跳びは検出可。+0.05 程度の改善は読めない |
| 120 | ±0.045 | RFC-0040 の判定規則（CI が正側で 0 を含まない）を引ける |

→ 3 段に分ける。**smoke 5 行**（動く・遅さ・swap だけ。質は読まない）→ **dev 30 行**（ループの内側。候補を捨てる／進めるの判断）→ **holdout 120 行**（dev を通った候補だけ、1 候補 1 回）。150 行は 1 候補 1 回でよく、「毎回 150」はやめる。5 行だけで採否を言うのは measurement-discipline 原則 1（1 回は証拠でない）に当たる。

150 行は既に opus-5 ×2 / sonnet-5 / gemma 8 arm のラベルを持つので、そこから dev / holdout を切り出す（新規ラベルなし）。dev と holdout は固定 seed で 1 回だけ切り、holdout は候補ごとに 1 回しか読まない（読み回すと dev 化する）。

## 候補キュー（search-first、2026-09-24）

| 順 | 候補 | 根拠 / 未検証点 | 走らせ方 |
|---|---|---|---|
| 1 | **kev-0.8b（MLX）** | PR #43 merge 2026-09-22。M5 32GB の数字のみ、**M1 16GB で catalog 丸ごと約 6,000 token の 1 リクエストが通るかは ⚠未検証**（第 3 ラウンドは MPS reference kernel で OOM） | `uv run --python 3.13 --no-project --with "kev[serve] @ git+…@<sha>" python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009`（既定 MLX、`KEV_BACKEND=torch` は使わない）。harness の arm K をそのまま |
| 2 | **von 1.2**（wfzyx/von、HF `wfzyx/von`） | CA 未測定。JevBench ECE 0.045〜0.109。`von serve --port 8010` が `/v1/systemone` 互換 → arm K の client を流用 | `uv run --python 3.13 --no-project --with "von-sdk>=1.2.0" von serve …`。harness に arm `V`（K と同じ run 関数、label 違い） |
| 3 | kev-4b（MLX） | README「32GB Mac」。16GB では gemma を降ろしても swap 前提 | 0.8b が dev を通った場合、または 0.8b が swap 上限内で余裕がある場合のみ |
| — | Laya / GLiClass 再測 | checkpoint 無変更（runtime release のみ） | 除外 |
| — | openJev-verdict-2.0 | checkpoint が LFS pointer 404 / HF 401、LICENSE 不整合 | 除外 |
| — | jevlike | `torch.load(weights_only=False)` 未修正（issue #3）、学習が要る | 除外（範囲外） |

キュー消化後の**追加探索**は 1 ループにつき 1 回、入場条件 5 つ全部: (a) Apple Silicon の runtime（MLX / MPS）が一次資料に明記 (b) checkpoint が取得できる (c) 判定目的で学習、または較正の数字が公開 (d) Apache-2.0 等の明示ライセンス、fork 群でなく origin repo (e) Jev 出力での学習を明言していない。追加は最大 2 件。

## 事前登録する判定規則（読みの前に固定）

同じ行で `B/enum/rep1`・`C/logits`・`E/ceiling` が揃っているので、比較は全部 paired。

- **smoke（5 行）pass** ⇔ 5 行すべて `reason == answered`、1 行の latency 中央値 < 20 秒（本番 19.1 秒の帯）、走行中の `vm.swapusage` used が開始時 +3 GB 以内。fail なら candidate を落とし理由コードを evidence に残す
- **dev（30 行）pass** ⇔ (候補 − `C/logits`) の Jaccard@topk 対差の bootstrap 95% CI の下限 > −0.02 **かつ** 平均 > +0.05（n=30 での 1 SE ≈ 0.046。「明らかに悪くない、かつ跳びの兆しがある」）。AUC（noul 型のみ）と ECE は併記するが判定に使わない
- **holdout（120 行）pass** ⇔ RFC-0040 の規則そのまま — (候補 − `C/logits`) **と** (候補 − `B/enum/rep1`) の Jaccard@topk 対差 CI がともに正側で 0 を含まない、かつ p ≥ 0.5 集合の天井に対する precision を分母付きで報告
- 1 候補につき holdout は 1 回。question 型の切替（choice / noul）は第 3 ラウンドと同じく 2 label を同時に走らせ、label ごとに上の規則を当てる（候補の「改稿」は別候補と数え、holdout 読みの総数は 1 ループ 3 回まで）

## 作業フロー

### Phase 0 — 判断役（この承認の直後、本セッション）

1. `python3 ~/.claude/scripts/claims.py claim RFC-0040 --label "round4 kev-mlx/von"`。RFC-0040 の state は `blocked` → `accepted`（待ち条件 (a) 発火、照合 2026-09-24 を本文に 1 段落）
2. build packet `.notes/packets/rfc-0040-c.md` を書く（下の Phase 1〜3 と判定規則をそのまま。Must-not: 本番 `DECISION_MODEL` を触らない / `$MOLTBOOK_HOME` へ書かない / holdout を 2 回読まない / 天井 arm を再実行しない）
3. checkpoint の取得許可（RFC-0043 の規約: 実行前にオーナー許可）— 本プラン承認をもって次の 3 件に限り許可とみなす: `jaredpalmer/kev-0.8b`（約 1.6 GB）、`wfzyx/von`（約 1.5 GB）、`jaredpalmer/kev-4b`（約 8 GB、順 3 に進んだときのみ）

### Phase 1 — harness 復元と split（build、Opus 5.5、worktree）

- `git checkout 817ecf3 -- scripts/skillsel_arm_replay.py tests/test_skillsel_arm_replay.py`（`evals/jev_arm.py` と `[dependency-groups] replay` は復元しない — K/V は別 process の HTTP、gliclass / laya は使わない → repo の依存はゼロ追加）
- harness の変更 3 点（各 1 テスト）:
  1. arm `V`（von）を追加: `run_kev` と同じ関数、`--von-endpoint` と label `V/choice` `V/noul`。`ARMS` / `ARM_LABELS` / `_arm_plan` の `_MULTI_LABEL_PLANS` に配線（K の写し）
  2. `wait_out_schedule` を K / V にも掛ける（`_OLLAMA_ARMS` とは別に `_GPU_ARMS` を置く。第 3 ラウンドで手動 `--resume` になった穴）
  3. `--augment` した summary が `B/enum/rep1` と `C/logits` に対する候補の paired CI を出す（既存の `paired_differences` に候補 − B / 候補 − C の 2 行を追加。`--summarize-only` で再集計できることを確認）
- split: `round3/l/rows.jsonl`（150 行、全 label 入り）から seed 固定で dev 30 行（幻覚あり 15 / なし 15）と holdout 120 行を `round4/dev.jsonl` `round4/holdout.jsonl` に切る（`--augment` はそのファイルの `selection_id` 集合をそのまま標本にする）。切った直後に両方を `--summarize-only` し、dev / holdout 上の `B/enum/rep1` と `C/logits` の値を evidence に先に書く（基準線を候補より先に凍結）
- tests: 復元したテスト + 上の 3 点。`.claude/verify.sh` を通す

### Phase 2 — 候補ループ（build、Opus 5.5、無人。JST 0/6/12/18 の窓は harness が待つ）

候補ごとに:

```
evict gemma (keep_alive: 0)  →  server 起動（別 process、commit / revision を pin、HF_HUB_OFFLINE=1）
→ smoke: --augment round4/dev.jsonl --augment-limit 5 --no-embed --latency-subsample 0
→ pass なら dev: --augment round4/dev.jsonl（30 行）→ 判定
→ pass なら holdout: --augment round4/holdout.jsonl（120 行、--no-embed 無し = soft agreement も出す）→ 判定
→ server 停止、`vm.swapusage` と `ollama ps` を aux に残す
```

- 各段の summary.json と run.log は `.notes/skillsel-arm-replay/round4/<candidate>/{smoke,dev,holdout}/` に置く。**situation 本文・decoded prompt は evidence に出さない**（第 1〜3 ラウンドと同じ）
- swap used が開始時 +6 GB を超えたら候補を打ち切り（第 3 ラウンド §8 の 17 GB 事故の再発防止）
- 停止条件（どれか）: (i) holdout pass → ループ終了 (ii) キュー + 追加探索 2 件が尽きた (iii) 同じ候補で同じ失敗 2 回（boundary.md） (iv) 経過 2 晩

### Phase 3 — 記録（build が draft、判断役が検収）

- `docs/evidence/rfc-0043/README.md` に「第 4 ラウンド（2026-09-2x）」節: 実行条件・split・各候補の smoke / dev / holdout の読み・測らなかったこと・実行コマンド。凍結 JSON `skillsel-arm-replay-round4-<date>.json`（holdout まで進んだ候補の summary。dev 止まりは数字だけ README に）
- RFC-0040 の Status / Next action を更新: pass なら「`DECISION_MODEL` 経路（Ollama 外なので sibling 注入）で shadow 有効化」を次の RFC 追補として提案（launchd の env 変更は人間ゲート）。fail なら `blocked` に戻し review-when を「kev-4b が 16GB に載る経路 / von の次版 / 新規候補が入場条件を満たす」に更新
- harness は task branch に commit（新 SHA を README に記す）。merge 後に再撤去するか残すかは検収時のオーナー判断（S26 と同じ扱いなら再撤去）
- memory `project_decision_backend_seam.md` を更新（kev MLX 着弾、split の所在、判定規則）

## 費用と時間の見積もり

- cloud 費用: ゼロ（天井ラベル再利用）。Opus 5.5 のセッション token のみ
- 時間: 第 3 ラウンドの K/choice は分割で 6.9 秒/行。MLX で同等以下なら 1 候補 dev 30 行 ≈ 5 分、holdout 120 行 ≈ 15〜30 分。候補 3 件で 1 晩に収まる
- メモリ: kev-0.8b MLX ≈ 2 GB、von ≈ 1.5 GB、gemma は降ろす（再ロード 7 秒）。kev-4b（≈ 8 GB）は swap を見て

## 重要ファイル

- `git show 817ecf3:scripts/skillsel_arm_replay.py`（4,852 行）: `stratified_sample` :489、`augment_sample` :4563、`run_kev` :2057、`_MULTI_LABEL_PLANS` :4153、`_OLLAMA_ARMS` :4048、`wait_out_schedule` :844、`bootstrap_ci` :747、`summarize` :3472
- `.notes/skillsel-arm-replay/round3/l/rows.jsonl`（150 行、全 arm の label を持つ split 元）
- `docs/evidence/rfc-0043/README.md`、`rfcs/0040-jev-system-one-local-decision-backend.md`、`docs/adr/0112-*.md`
- `src/contemplative_agent/core/llm/decision.py`（pass 後の注入先。本ラウンドでは触らない）

## 検証

- harness: 復元テスト + 新規 3 テストが green、`.claude/verify.sh` exit 0
- split の再現: `--summarize-only` を dev / holdout に当てて `rows == 30 / 120`、`B/enum/rep1`・`C/logits`・`E/ceiling` の値が出る（候補を走らせる前）
- smoke 5 行で `reason` の分布・latency・swap を aux に記録できている
- holdout の判定は summary.json の `paired_differences` の 2 行（候補 − B、候補 − C）で機械的に読める
- 公開ツリーの検査 `tests/test_jev_results_stay_private.py` が引き続き green（ホスト型 Jev の label を混ぜない）
