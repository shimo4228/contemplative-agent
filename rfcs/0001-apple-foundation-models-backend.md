---
state: blocked
state_since: 2026-08-16
---

## タスク

Apple Foundation Models をローカル生成 backend として挿すか — 2026-08-01 に実測して棄却、再開条件待ち。

**測定して棄却した（2026-08-01）。挿さない。** 4 軸すべてが同じ向き: (1) **射程 6.7%** — 本番 30 日 n=8,772 の実分布で 4,096 窓に収まる publish 呼び出しの割合。enforced 経路（9.3%）だけなら 72.1% だが、fail-open（90.7%、フル注入 16,990 tok）は 0%。(2) **品質は現行が圧勝** — 実投稿 30 件・盲検・別モデル judge で gemma4:e4b の実公開コメントが 27/30 件 1 位（平均順位 1.17 対 2.39/2.40）。(3) **reasoning が無い** — ADR-0069 の think-ON 6 コマンド 9 呼び出しを黙って取り消す。(4) **メモリ利得は既取得** — ADR-0065 のとおり Ollama は 5 分で降り、agent は 1 日 4×60 分しか動かない。**速度は棄却理由ではない**（p50 28.7s ≒ 本番フル注入 28.3s。台帳の旧 1.15s は identity のみの値で 25 倍外れていた）。**副産物として (a) が決着**: 片肺なら `probability_threshold`（top-k 単独は 30 件中 1 件が 4-gram 反復率 0.467 で退化）。**再開条件**: (i) enforcement が安定して射程が 72% 帯に乗る（→ `T-PLIST-FLAG-REVERT`） かつ (ii) 品質差が縮む世代が出る（OS 27 GA 後の再測定。窓 8,192 は射程しか動かさないので単独では着手条件にならない）

## 着手条件

再開条件: (i) enforcement が安定して射程が 72% 帯に乗る **かつ** (ii) 品質差が縮む世代が出る（OS 27 GA 後の再測定）— 同時成立
照合先:   (i) `logs/skill-selection-*.jsonl` の enforced 比率、(ii) OS バージョンと再測定結果
成立時:   accepted（窓 8,192 は射程しか動かさないので単独では条件にならない。備考なき限り再提起しない）

## 詳細

実測ハーネスと生データ: `.notes/apple-fm-quality-ab.py`（4 phase・2 venv、`--baseline` で本番レイテンシ）+ `apple-fm-ab-20260801/`。判断軸と罠の正本は skill [`apple-silicon-local-llm-serving`](../.claude/skills/apple-silicon-local-llm-serving/SKILL.md)（窓・切り詰め署名・sampling・測り方の罠 7 件をここに集約済み）。Phase 0 計器は `.notes/apple-fm-probe.py`。関連: [ADR-0065](../docs/adr/0065-mlx-ondemand-launchd-and-telemetry-model-contract.md)（Ollama の常駐ゼロ）/ [ADR-0067](../docs/adr/0067-keep-ollama-for-unattended-production.md)（無人本番は Ollama）/ [ADR-0069](../docs/adr/0069-gemma-production-model-and-think-on-value-layer-pipelines.md)（think-ON）/ [ADR-0087](../docs/adr/0087-optional-token-counting-capability-for-the-context-budget-guard.md)（この検討が生んだ `count_tokens` seam）。派生タスク: `T-SKILLSEL-CACHE-COST` / `T-THINK-SILENT-FALLBACK` / `T-BACKEND-CONTRACT-KIT`

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。(ii) `sw_vers` = 26.6.1（OS 27 GA 未到達）。(i)(ii) 同時成立が条件なので (i) の enforced 比率は未集計。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`sw_vers` = 26.6.1（OS 27 GA 未到達）。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。`sw_vers` = 26.6.1（OS 27 GA 未到達）。

旧 ID: T-APPLE-FM-BACKEND（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`sw_vers` = 26.6.1（OS 27 GA 未到達）。enforcement 射程側も変化なし。

## Status

blocked — 2026-08-01 に 4 軸を実測して棄却済み、再開条件待ち
（2026-08-25）。直近の照合 2026-08-24 も未成立（`sw_vers` = 26.6.1 で OS 27 GA 未到達）。

## Next action

- 再開条件: (i) enforcement が安定して射程が 72% 帯に乗る **かつ** (ii) 品質差が縮む
  世代が出る（OS 27 GA 後の再測定）— 同時成立
- 照合先: (i) `logs/skill-selection-*.jsonl` の enforced 比率、(ii) OS バージョンと
  再測定結果
- 成立時: accepted（窓 8,192 は射程しか動かさないので単独では条件にならない）
