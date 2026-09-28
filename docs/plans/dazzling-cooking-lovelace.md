# README のモデル記述をモデル非依存化する

## Context

コードの実態は `OLLAMA_MODEL` env var 1 個で任意の Ollama モデルに差し替え可能（`core/llm.py:625`、コード変更不要）だが、README / GitHub About / llms-full.txt が「Gemma で動く」と読める書き方になっており、Gemma 専用の狭い設計・大きいモデルは扱えない、という誤読を招く。`OLLAMA_MODEL` の記載は `docs/CONFIGURATION.md:395` の表 1 行のみ。

**見せ方の方針**（ユーザー指示を反映）:
- アーキテクチャの記述（冒頭・About・add-on 節）は **モデル非依存** — 「Ollama 上の任意のローカル LLM」
- 強調点は「**こんな小さなモデルでも堅牢に回る**」（16 GB M1 + 小型モデルは floor の実証であって ceiling ではない）
- Gemma の固有名は **Live Agent（現在の稼働事実）と Quick Start（テスト済みデフォルト）にのみ** 登場させる。ADR-0069（cross-model blind 評価で選定）へリンクし「選択であって制約でない」ことを示す
- 差し替え可能性は主張でなく **実績** として書く: 本番インスタンス自体が Qwen 3.5 9B → Gemma 4 E4B へコード変更なしで乗り換え済み（ADR-0069）

種別: `writing`（README 改稿）。コード変更なし。

## 変更ファイル

### 1. README.md（英語正本）— 4 箇所

- **L11 冒頭**: "with a local Gemma 4 model" を除去。
  → "The whole loop runs with any local LLM served by Ollama — robustly, even with a small model on a single Apple Silicon Mac (M1+, 16 GB) — no cloud, no LLM API keys, no shell execution."
- **L69 Quick Start Prerequisites**: swap 方法を明記。
  → "Any Ollama model works — set `OLLAMA_MODEL` to swap ([Configuration Guide](../../docs/CONFIGURATION.md)). The tested default is the compact Gemma 4 E4B (`gemma4:e4b`, Q4_K_M, ~9.6 GB on disk), which runs the whole loop on an M1 Mac with 16 GB RAM."
- **L94 Live Agent**: 現稼働モデルとしての Gemma をここに移し、Qwen からの乗り換え実績で swap を実証。
  → "…runs daily on Moltbook — currently generating with the compact Gemma 4 E4B on local Ollama, switched from Qwen 3.5 9B by a cross-model blind evaluation with no code change ([ADR-0069](../../docs/adr/0069-gemma-production-model-and-think-on-value-layer-pipelines.md)). Its evolving value layer…"
- **L155 cloud add-on**: "larger than Gemma 4 E4B" → "beyond what the local host serves"（制約はホスト側であって Gemma ではない）

### 2. README.ja.md — 同 4 箇所を鏡像修正

- L11: 「ループ全体が Ollama 上の任意のローカル LLM で動く — Apple Silicon Mac 1 台（M1+, 16 GB）の小さなモデルでも堅牢に。クラウドなし、LLM API キーなし、シェル実行なし。」
- L69 / L94 / L155 も英語版と同旨

### 3. llms-full.txt — 4 箇所（doc sync: user-facing クレーム変更）

- L3 ヘッダ定義: "running on Ollama (any model via `OLLAMA_MODEL`; production default: Gemma 4 E4B + nomic-embed-text)"
- L18 Project Facts: "**Generation LLM**: any Ollama model (`OLLAMA_MODEL` env var); production default Gemma 4 E4B / `gemma4:e4b` (Q4_K_M, ~9.6 GB)"
- L54 hardware FAQ: 「default LLM stack」の後に swap 可能な旨 + ADR-0069 参照を 1 文追加
- L156 cloud add-on 定義: "larger than Gemma 4 E4B" → 同旨の書き換え

（llms.txt L126 は ADR-0069 の要約なので変更不要）

### 4. GitHub About（`gh repo edit --description`）

- 現: "Runs entirely on a local Gemma model. Security by absence."
- 新: "Runs entirely on a local LLM via Ollama — robust even on a small model. Security by absence."
- 外部書き込みなので実行前に新旧全文を提示して確認

## 変更しないもの

- コード（`core/llm.py` のデフォルトはそのまま）
- `docs/CONFIGURATION.md`（既に `OLLAMA_MODEL` を正しく記載）
- llms.txt、glossary（project-coined term の追加なし）

## Chain / Verify

- Writing chain: readme-reviewer は今回スキップ（構成変更なしの文単位差し替え、ユーザーが方向を明示済み）→ 人間 gate（diff 確認）で代替
- Verify: 変更後に README 内リンク先の実在確認（ADR-0069 は確認済み）、`git status`、diff 提示
- コミットはユーザーの diff 確認後（feedback: main 直 commit → push）
