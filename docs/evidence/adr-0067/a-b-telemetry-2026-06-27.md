# MLX vs Ollama 本番 A/B telemetry (M1 / 16GB, 2026-06-27)

ADR-0067 の decisive evidence。`~/.config/moltbook/logs/llm-calls-*.jsonl` から再計算した
（ADR-0065 の served-model-id 契約により `model` フィールドが実 model id を記録するため、
backend 別の outcome 内訳が直接集計できる）。

条件: M1 / 16GB / macOS 26.3 / mlx-lm v0.31.3 / `mlx-community/Qwen3.5-9B-4bit`（生成）
+ Ollama `qwen3.5:9b`（生成 baseline）。本番 launchd セッション（agent 0/6/12/18 時、distill 03:30）。

## 主指標 — backend 別 outcome（中央指標）

| backend | calls | ok | circuit_open | error | truncated_dropped | ok 率 |
|---|---|---|---|---|---|---|
| **MLX** (`mlx-community/Qwen3.5-9B-4bit`, 2026-06-27) | **21,224** | **107** | 21,060 | 53 | 4 | **0.50%** |
| **Ollama** (`qwen3.5:9b`, 06-09..06-26 baseline) | ~200–270 / 日 | ≈全数 | ~0 | ~0 | 稀 | **≈100%** |

MLX は **06-27 のみ**稼働（00:49–15:08 UTC）。Ollama は前後 18 日にわたり毎日 ~200–270 コールで
ほぼ 100% ok、circuit breaker をほぼ一度も踏まない（唯一 06-26 が 235 中 7 truncated_dropped＝97%）。

## 時間別プロファイル — 「load して動く → セッション中に崩壊」

MLX (06-27, UTC):

| hour (UTC) | total | ok | circuit_open | error | trunc |
|---|---|---|---|---|---|
| 00 | 23 | 23 | 0 | 0 | 0 |
| 01 | 58 | 58 | 0 | 0 | 0 |
| 03 | 3 | 2 | 0 | 0 | 1 |
| 04 | 477 | 1 | 471 | 5 | 0 |
| 05 | 174 | 11 | 156 | 5 | 2 |
| **09** | **19,520** | **2** | **19,495** | 23 | 0 |
| 10 | 161 | 0 | 156 | 5 | 0 |
| 11 | 5 | 4 | 0 | 1 | 0 |
| 12 | 160 | 0 | 156 | 4 | 0 |
| 14 | 167 | 5 | 156 | 5 | 1 |
| 15 | 476 | 1 | 470 | 5 | 0 |

最初の ~81 コール（00–01 時）は **100% ok** — サーバは load して正常に動く。03 時以降に circuit breaker
が開き始め、**09 時の 1 時間だけで 19,520 回試行して ok は 2 件**（circuit-open + 反応的リトライの空回り）。
以降のセッションは circuit が開いたまま（毎セッション ~156 件の circuit_open）。

これは「最初は動き、メモリ圧の進行とともに OOM 非回復 → circuit カスケード → スピン」という ADR-0067 の
root-cause を裏付ける（prefill cliff の機序は
[prefill-degradation-2026-06-27.md](prefill-degradation-2026-06-27.md) 参照）。

## truncation の再分類（レポートの EOS-runaway 説への反証）

別途 `verify_solve` の truncation を caller 別に集計した A/B では、MLX の truncation は **n=5 のノイズ
レンジ**で、Ollama 側（n≈67 で ~13%）と比べて MLX 固有ではなく **solver 設計の既存性質**と判定された。
よって ADR-0067 は truncation（EOS-runaway）ではなく circuit-breaker カスケードに立脚する。

## 再現方法（live 集計）

```python
import json, glob, os
from collections import defaultdict
agg = defaultdict(lambda: defaultdict(int))
for f in sorted(glob.glob(os.path.expanduser("~/.config/moltbook/logs/llm-calls-*.jsonl"))):
    for line in open(f):
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        m = (r.get("model") or "")
        k = "MLX" if ("mlx" in m.lower() or "Qwen3.5-9B-4bit" in m) else ("Ollama" if "qwen3.5:9b" in m else "other")
        agg[k][r.get("outcome", "?")] += 1
# MLX: total=21224 ok=107 (0.50%) circuit_open=21060 error=53 truncated_dropped=4  (06-27)
```

## 結論

無人連続の本番条件下で、MLX (mlx_lm.server) は同一ハーネスの Ollama に対し **ok 0.50% vs ≈100%** という
decisive な差で劣後した。モデルは load して動いた（21k コール記録）ので故障は runtime 劣化であり、
本番生成は Ollama に固定する（ADR-0067）。

## Caveats

- レポート（[mlx-production-suitability-survey-2026-06.md](mlx-production-suitability-survey-2026-06.md)）の
  「21,143 / 26 ok」「19,520 / 2 ok」等は in-flight の部分スナップショットで、ここでの全期間再計算
  （21,224 / 107 ok）が正。絶対値は本機・本構成固有。
- ADR-0065 契約導入前の早期記録は `model` が class 名 sentinel（`MlxLmBackend`）で 81 件、いずれも ok。
  これらは崩壊前の早期コールで、上記「最初は動く」と整合する（MLX バケットに合算済み）。
