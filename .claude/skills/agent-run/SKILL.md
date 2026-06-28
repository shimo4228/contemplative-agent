---
name: agent-run
description: contemplative-agent をバックグラウンドで起動する。引数でセッション時間とバックエンド (ollama / cloud) を指定（例: /agent-run 4時間, /agent-run 30分 cloud openai）
origin: shimo4228
user-invocable: true
---

# Agent Run

contemplative-agent をバックグラウンドで起動する。生成バックエンドを
**ollama（デフォルト）/ cloud** から選べる。

## 引数の解釈

`$ARGUMENTS` を空白区切りで `<時間> [backend] [provider]` として解釈する。

### 時間（必須でなく、省略時 60 分）

- 「4時間」「2h」→ 240分、120分に変換
- 「30分」「30m」「30」→ そのまま分数
- 数値が見つからなければ 60 分

### backend（省略時 `ollama`）

| 値 | 経路 |
|---|---|
| `ollama`（既定） | ローカル Ollama + `qwen3.5:9b`（main repo の組み込み生成） |
| `cloud` | `contemplative-agent-cloud`（Anthropic Claude / OpenAI GPT。埋め込みは Ollama 据置き） |

### provider（`cloud` のときだけ意味を持つ、省略時 `anthropic`）

- `anthropic`（既定、`claude-opus-4-7`）/ `openai`（`gpt-5`）
- model 上書きは `CONTEMPLATIVE_CLOUD_MODEL` 環境変数（skill は触らない）

## パス解決

skill は repo 内で動く前提。repo ルートと sibling の cloud repo を解決する:

```bash
REPO="$(git -C "$PWD" rev-parse --show-toplevel)"
AGENT="$REPO/.venv/bin/contemplative-agent"
CLOUD_BIN="$(dirname "$REPO")/contemplative-agent-cloud/.venv/bin/contemplative-agent-cloud"
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
