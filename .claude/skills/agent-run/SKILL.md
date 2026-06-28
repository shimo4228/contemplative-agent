---
name: agent-run
description: contemplative-agent をバックグラウンドで起動する。引数でセッション時間とバックエンド (ollama / cloud / mlx) を指定（例: /agent-run 4時間, /agent-run 30分 cloud openai, /agent-run 30分 mlx）
origin: shimo4228
user-invocable: true
---

# Agent Run

contemplative-agent をバックグラウンドで起動する。生成バックエンドを
**ollama（デフォルト）/ cloud / mlx** から選べる。

## 引数の解釈

`$ARGUMENTS` を空白区切りで `<時間> [backend] [provider]` として解釈する。

### 時間（必須でなく、省略時 60 分）

- 「4時間」「2h」→ 240分、120分に変換
- 「30分」「30m」「30」→ そのまま分数
- 数値が見つからなければ 60 分

### backend（省略時 `ollama`）

| 値 | 経路 |
|---|---|
| `ollama`（既定） | ローカル Ollama + `gemma4:e4b`（main repo の組み込み生成） |
| `cloud` | `contemplative-agent-cloud`（Anthropic Claude / OpenAI GPT。埋め込みは Ollama 据置き） |
| `mlx` | `contemplative-agent-mlx`（Apple Silicon ローカル MLX `mlx_lm.server`。埋め込みは Ollama 据置き。`run-with-mlx.sh` がサーバを起動→実行→停止）。**対話的・短時間用途のみ**（16GB 無人連続運用に不適、ADR-0067） |

### provider（`cloud` のときだけ意味を持つ、省略時 `anthropic`）

- `anthropic`（既定、`claude-opus-4-7`）/ `openai`（`gpt-5`）
- model 上書きは `CONTEMPLATIVE_CLOUD_MODEL` 環境変数（skill は触らない）

## パス解決

skill は repo 内で動く前提。repo ルートと sibling の cloud repo を解決する:

```bash
REPO="$(git -C "$PWD" rev-parse --show-toplevel)"
AGENT="$REPO/.venv/bin/contemplative-agent"
CLOUD_BIN="$(dirname "$REPO")/contemplative-agent-cloud/.venv/bin/contemplative-agent-cloud"
MLX_REPO="$(dirname "$REPO")/contemplative-agent-mlx"
MLX_RUN="$MLX_REPO/scripts/run-with-mlx.sh"
```

## 起動コマンド (CRITICAL)

**グローバルフラグ `-v --auto` は必ず `run` の前**。順序変更・省略禁止。
`{N}` は分数、`bg` はバックグラウンド起動（nohup + リダイレクト）。

### ollama（デフォルト）

```bash
"$AGENT" -v --auto run --session {N}
```

### cloud

`contemplative-agent-cloud` は同一 CLI の drop-in。provider を環境変数で渡し、
**API キーは skill が扱わず** `~/.config/moltbook/cloud.env`（cloud CLI が自動で読む）
またはシェル環境変数に委譲する。

```bash
CONTEMPLATIVE_CLOUD_PROVIDER={provider} "$CLOUD_BIN" -v --auto run --session {N}
```

### mlx

`contemplative-agent-mlx` の `run-with-mlx.sh` が mlx_lm.server を起動 → ヘルス待ち →
エージェント実行 → 終了時にサーバ停止する（idle メモリ ~0）。**Apple Silicon 専用**。
生成のみ MLX、埋め込みは Ollama 据置き。

```bash
"$MLX_RUN" -v --auto run --session {N}
```

## 実行手順

1. `$ARGUMENTS` を 時間 / backend / provider に分解。
2. 時間を分数に変換。
3. backend ごとに **事前チェック**（下記）。失敗したら**起動せず停止して理由を報告**
   （silent に ollama へ落とさない）。
4. バックエンド別コマンドを **バックグラウンド** で起動
   （`nohup <cmd> > <scratchpad>/agent-session.log 2>&1 &`）。
5. 起動コマンド・セッション時間・backend・ログのパスを報告。

## 事前チェック（silent fallback 禁止）

| backend | 確認 | 失敗時 |
|---|---|---|
| `ollama` | `curl -sf localhost:11434/api/tags` | Ollama 未起動を報告して停止 |
| `cloud` | `[ -x "$CLOUD_BIN" ]` かつ（`[ -f "$MOLTBOOK_HOME/cloud.env" ]` または `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY` が設定済み） | cloud venv 不動 or 鍵未設定を報告。**Ollama へ落とさない**。導入: `uv pip install --python <cloud>/.venv/bin/python -e <main-repo>`、鍵は `~/.config/moltbook/cloud.env` に `CONTEMPLATIVE_CLOUD_PROVIDER=` と `ANTHROPIC_API_KEY=`（または `OPENAI_API_KEY=`） |
| `mlx` | `[ "$(uname -m)" = "arm64" ]` かつ `[ -x "$MLX_RUN" ]` かつ `[ -x "$MLX_REPO/.venv/bin/contemplative-agent-mlx" ]` かつ `[ -x "$HOME/.local/bin/mlx_lm.server" ]` かつ Ollama 稼働（埋め込み用、`curl -sf localhost:11434/api/tags`） | 非 Apple Silicon / mlx venv 不動 / mlx_lm.server 未導入 / Ollama 停止を報告し**停止**。**Ollama へ落とさない**。導入: mlx repo を `git clone` → `uv venv .venv` → `uv pip install -e .` + main も同 venv へ、`uv tool install mlx-lm` |

`MOLTBOOK_HOME` 未設定時の既定は `~/.config/moltbook`。

## 特殊フラグ

ユーザーが明示指定した場合のみ追加（全 backend 共通、`run` の前に置く）:

- `--guarded` / `--approve`: `--auto` の代わり
- `--no-axioms`: A/B テスト用（公理なし）
- `--domain-config PATH` / `--rules-dir PATH` / `--constitution-dir PATH`: 切替

## 注意

- 生成のみが backend で切り替わる。**埋め込みは常にローカル Ollama**（`nomic-embed-text`、
  cloud add-on も埋め込みは据置き）。
- `cloud` は untrusted な SNS コンテンツを外部 API に送る = security by absence を
  **緩める**選択。研究実験（大型モデルでの distill 比較等）以外では使わない。
- `mlx` は**完全ローカル**（cloud egress なし）で security by absence は緩めない。ただし
  Apple Silicon 専用で、16GB では無人連続運用に不適（ADR-0067: EOS 暴走 / OOM / prefill 崖 /
  cache churn / wired thrash）。**対話的・短時間に限る**。本番スケジュール（0/6/12/18 時 JST）と
  重ねると 16GB メモリ競合でクラッシュしうるので避ける。
