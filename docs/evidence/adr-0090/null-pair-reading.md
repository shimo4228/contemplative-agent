# T-CONST-IPD (a): IPD ベンチ null ペア実測（2026-08-06 深夜〜08-07）

同一憲法・同一条件で contemplative-ipd を 2 回回し、憲法改正時の読みに使う
run 間 noise floor を確定した。

## 条件

- ベンチ: `contemplative-agent-rules/benchmarks/prisoners-dilemma`（paper protocol, Appendix E）
- モデル: `OLLAMA_MODEL=gemma4:e4b`（本番生成モデル、ADR-0069）
- 憲法: `~/.config/moltbook/constitution/contemplative-axioms.md`
  sha256 `3d8a8503…`（**audit.jsonl の 2026-05-05 承認レコードの content_hash と一致** —
  現行本番憲法そのもの）
- n=10 simulations × 3 opponent α × 2 variant（baseline = プロンプトなし / custom = 憲法）
- run1: 08-06 22:07 JST 開始、3,076s。run2: 08-07 01:05 開始、4,082s
  （0 時のスケジュール窓を wrapper が自動回避、feedback `no-heavy-experiments-during-sessions` 遵守）

## 読み

| cell | run1 | run2 | diff | diff/SE |
|---|---|---|---|---|
| baseline/α=0.0 | .000 | .030 | +.030 | 1.96 |
| baseline/α=0.5 | .040 | .010 | −.030 | −1.57 |
| baseline/α=1.0 | .020 | .020 | .000 | 0.00 |
| custom/α=0.0 | .090 | .080 | −.010 | −0.22 |
| custom/α=0.5 | .160 | .210 | +.050 | 0.72 |
| custom/α=1.0 | .420 | .290 | **−.130** | −1.94 |

custom − baseline（改正時の主指標）: α=0.0: +.090/+.050（揺れ .040）、
α=0.5: +.120/+.200（揺れ .080）、α=1.0: +.400/+.270（揺れ **.130**）。

1. **方向は 6/6 で再現**: custom > baseline が両 run × 全 α で成立。α 勾配
   （相手が協力的なほど協力率が伸びる相互性）も両 run で保存。
2. **効果量の noise floor = ±0.13**（n=10）。全セル diff/SE < 2 で run 内
   サンプリングノイズと整合 — ADR-0089 Amendment で見つけた run レベル相関
   シフトの証拠は**このベンチでは観測されず**（ただし 1 ペア・n=10 なので
   検出力は弱い。「無い」ではなく「見えなかった」）。
3. baseline arm は床（0〜4%）に安定。

## 改正時の解釈規約（この読みの使い方）

- **|Δ(custom−baseline)| < 0.13 の変化はノイズと区別不能** — 改正前後で
  効果量がこの幅で動いても「協力性が変わった」と言わない。
- 読んでよい signal: **符号の反転**（custom < baseline への転落）、
  **α 勾配の消失**（相互性構造の崩れ）、複数セル同方向の 0.13 超の移動。
- 微小差を検出したければ n を増やす（SE ∝ 1/√n）が、n=10 で片 run ~51〜68 分
  （プレフィックスキャッシュ状態で変動）。改正判断に必要になってから。

## ファイル

- `null-run-1.json` / `null-run-2.json` — ベンチ生出力（statistics + 60 simulations 各）
- `run1.log` / `run2.log` — 実行ログ
- `analyze-null-pair.py` — 上表の導出スクリプト
