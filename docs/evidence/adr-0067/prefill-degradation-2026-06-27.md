# MLX prefill が低メモリ下で ~75x 崖落ちする (M1 / 16GB, 2026-06-27)

ADR-0067 の compound 機序の一つ。`mlx_lm.server` の prompt prefill（プロンプト処理段）が、
**同一サーバプロセス内で**、メモリ圧の進行とともに非線形に崩壊する。本番 `contemplative-agent`
（`LLM_BACKEND=mlx`）の reply 生成 1 件の prefill が 58 分かかってハングし、30 分セッションが 1 件の
生成で終わらず手動 kill した事故の記録。

## 決定的証拠 — 同一プロセスで 72 秒 vs 58 分

`~/.config/moltbook/logs/mlx-server.log`。**同じ mlx_lm.server プロセス (PID 11592)**、ほぼ同サイズ
（~7.5k tok）の prompt:

```
# (A) 正常 — 起動直後 (20:36 起動)、メモリ余裕
20:38:10  Prompt processing progress: 2048/7434
20:38:37  Prompt processing progress: 4096/7434     # +2048 tok = 27 秒 (~76 tok/s)
20:39:04  Prompt processing progress: 6144/7434     # +2048 tok = 27 秒
20:39:22  Prompt processing progress: 7434/7434     # 合計 ~72 秒

# (B) 壊滅 — わずか 11 分後、メモリ圧迫が進行
20:49:54  Prompt processing progress: 2048/7501
21:23:46  Prompt processing progress: 4096/7501     # +2048 tok = 34 分 (~1 tok/s) ★
21:47:31  Prompt processing progress: 6144/7501     # +2048 tok = 24 分
21:47:50  Prompt processing progress: 7501/7501     # 合計 ~58 分
```

同一プロセス・同じ chunk サイズ (2048)・ほぼ同じ prompt サイズで **2048 tok の処理が 27 秒 → 34 分
（~75x）**。コア実装が遅いなら (A) から遅いはず。**(A)→(B) で変わったのはメモリ状況だけ**。

別件として `18:13:04` に `587/930` で prefill が停止＝Metal OOM crash（Abort trap 6 を別途確認）も
観測されている。

## 環境

- **機種/OS**: MacBookPro17,1（Apple M1）, **16GB** unified memory, macOS 26.3 (25D125)
- **mlx-lm**: v0.31.3（`uv tool` 管理）
- **model**: `mlx-community/Qwen3.5-9B-4bit`（重み ~5.2GB）
- **起動**: `scripts/run-with-mlx.sh`（オンデマンド、`trap EXIT` で kill）。
  `mlx_lm.server --model mlx-community/Qwen3.5-9B-4bit --host 127.0.0.1 --port 8080 --prompt-cache-size 2 --chat-template-args '{"enable_thinking": false}'`
- **同居プロセス**: 本番 agent（+MLX で ~6.4GB）, Ollama（埋め込み常駐）, Claude Code, Zed, Codex.app, Chrome
- **メモリ計測**: 転落時 `free 29% / swap 0`、agent+MLX kill 後 `free 71%`（= agent+MLX で ~6.4GB 占有）

## 機序

- prefill ~7.5k tok の大半は ~7.6k tok の system prompt（identity + 4 公理 + skills + rules の
  all-injection）。
- swap = 0 だが macOS の **memory compression は効いている**（free% は圧縮込み）。スワップ手前の圧縮段で
  既に詰まっている。
- **MLX (Metal) は wired メモリ**でスワップ不可 → 圧迫時に逃げ場がない。対して Ollama (GGUF mmap) は
  file-backed / pageable で優雅に degrade する（[wired vs pageable の対比は
  mlx-production-suitability-survey-2026-06.md 障害モード 5 参照](mlx-production-suitability-survey-2026-06.md)）。
  実地でも「MLX (5GB) は軽いのに Ollama (8.6GB) より共存性が悪い」逆転を観測。
- **prompt cache が効いていない**: (A)(B) とも chunk が `2048/N` から開始＝7.5k をフル prefill。
  `--prompt-cache-size 2` の下で reply/comment/score/internal_note の異なる user prompt が回転し
  system prefix (7.6k) を evict しているため、毎回フル prefill して degrade をまともに浴びる。

## 結論

低メモリ下で MLX の wired Metal 確保には逃げ場がなく、ある閾値で prefill が非線形に崖落ちする。16GB で
9B + 他プロセス同居は構造的に厳しい。これは ADR-0067 の「無人連続では不適」判断の compound 要因
（root は OOM の graceful degradation 欠如）。

## Caveat

「~75x」は本機・本構成のテレメトリ。機序（wired Metal + memory compression）は一次情報で裏付け済みだが、
絶対倍率は環境依存。
