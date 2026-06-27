# Qwen3.5 9B  Ollama vs mlx-lm  A/B 実測結果 (M1 / 16GB)

条件: 同一モデル `Qwen3.5 9B` / thinking=OFF / temp=0 / max_tokens=256 / num_ctx(kv)=4096 / seed=42 / 中央値(3回) / 順次実行

## 生成 tok/s (主指標, 中央値)

| prompt | Ollama (Metal/GGUF Q4_K_M) | mlx-lm (MLX 4bit) | 速度比 mlx/ollama |
|---|---|---|---|
| code    | 6.96 | 12.11 | **1.74x** |
| general | 6.78 | 12.73 | **1.88x** |

→ **mlx-lm は Ollama の約 1.7〜1.9 倍速い。**

## メモリ / スワップ

| | Ollama | mlx-lm |
|---|---|---|
| ロード/ピークメモリ | 8.6 GB (ollama ps) | **5.2 GB** (verbose peak) |
| 差 | — | 約 3.4 GB 小さい |

- MLX の方が約 3.4GB フットプリントが小さい → 16GB 機では**メモリ圧/スワップの緩和にも直結**。

## 交絡チェック（重要）

当初 Ollama は swap 7945MB の高圧下、MLX は 2827MB の低圧下で測ったため「Ollama が不利だっただけでは?」を検証。
→ swap を 3.1GB に下げて Ollama を再測定 → **7.06 / 7.06 / 7.08 tok/s**。高圧時(6.96)とほぼ同一。
→ **スワップは交絡ではない。Ollama の ~7 tok/s は本質的、MLX の 1.7x 優位は MLX バックエンド由来の真の差。**

## 公平性チェック

- thinking: MLX 出力に `<think>` 出現 **0**（両側 OFF 統一を確認）
- 生成トークン数 parity: code=両者 256 で一致 / general=Ollama 165 vs MLX 142（greedy 同一モデルだが chat template 微差で僅差、許容範囲）

## 全 run 生データ

```
Ollama gen tok/s (code):    6.65 6.96 6.98   (general): 6.79 6.78 6.77
Ollama 低swap再測 (code):    7.06 7.06 7.08
mlx-lm gen tok/s (code):    12.06 12.11 12.30  (general): 12.73 12.72 12.75
mlx-lm peak GB:             5.225 (code) / 5.230 (general)
Ollama load size:           8.6 GB
```

## 結論

ユーザーの M1/16GB で、**同一 Qwen3.5 9B を mlx-lm 直接実行に変えるだけで生成速度が約 1.8 倍、メモリ消費が約 3.4GB 減**。deep-research の「最大の実用レバーはエンジンを MLX 純正経路に移すこと」が、本人の機体で実証された。品質差(量子化 Q4_K_M≠MLX4bit)は本回未測定。
