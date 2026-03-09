# Contemplative Moltbook Agent

Moltbook (AI エージェント SNS) 上で Contemplative AI フレームワークを広める自律エージェント。

## 構造

```
config/                         # 外部化された設定・テンプレート
  domain.json                   # ドメイン設定 (サブモルト, 閾値, キーワード)
  prompts/                      # プロンプトテンプレート (.md, ドメイン非依存)
    system.md, relevance.md, comment.md, cooperation_post.md,
    reply.md, post_title.md, topic_extraction.md, topic_novelty.md,
    topic_summary.md, submolt_selection.md, session_insight.md,
    distill.md, eval.md
  rules/contemplative/          # ドメイン固有コンテンツ (.md)
    introduction.md, mindfulness.md, emptiness.md,
    non-duality.md, boundless-care.md
src/contemplative_moltbook/
  agent.py                  # セッション管理・オーケストレータ (graceful shutdown)
  client.py                 # HTTP クライアント (認証・レート制限・submolt 購読)
  domain.py                 # ドメイン設定・テンプレートローダー (DomainConfig, PromptTemplates, RulesContent)
  llm.py                    # Ollama LLM インターフェース (サーキットブレーカー付き)
  prompts.py                # プロンプトテンプレート遅延ロード (config/prompts/ から読み込み)
  memory.py                 # 3層メモリ (EpisodeLog + KnowledgeStore + facade)
  distill.py                # スリープタイム記憶蒸留
  config.py                 # 定数・設定 (API, レート制限, セキュリティ)
  content.py                # コンテンツ管理 (config/rules/ から読み込み)
  scheduler.py              # レート制限スケジューラ
  verification.py           # 認証チャレンジソルバー
  auth.py                   # クレデンシャル管理
  cli.py                    # CLI エントリポイント (--rules-dir, --domain-config フラグ)
tests/                      # テストスイート
```

## 開発環境

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# テスト
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_moltbook --cov-report=term-missing

# CLI
contemplative-moltbook --help
contemplative-moltbook init                          # identity.md + knowledge.md 作成
contemplative-moltbook distill --dry-run             # 記憶蒸留 (dry run)
contemplative-moltbook distill --days 3              # 3日分を蒸留
contemplative-moltbook solve "ttwweennttyy pplluuss ffiivvee"

# ドメイン切替
contemplative-moltbook --domain-config path/to/domain.json --rules-dir path/to/rules/ run --session 30
```

- Python 3.9+ (venv は 3.13.5)
- 依存: requests のみ。LLM は Ollama (qwen3.5:9b, localhost)
- ビルド: hatch
- 14 モジュール、~3700 LOC

## セキュリティ方針

- データディレクトリ: `MOLTBOOK_HOME` 環境変数でカスタマイズ可 (デフォルト: `~/.config/moltbook`)
- API key: env var > `$MOLTBOOK_HOME/credentials.json` (0600)。ログには `_mask_key()` のみ
- HTTP: `allow_redirects=False`、ドメイン `www.moltbook.com` のみ、Retry-After 300s キャップ
- LLM: Ollama localhost のみ許可。出力は `re.IGNORECASE` で禁止パターン除去。外部コンテンツ・knowledge context は `<untrusted_content>` タグでラップ。identity.md は forbidden pattern 検証済み
- post_id: `[A-Za-z0-9_-]+` バリデーション
- Verification: 連続7失敗で自動停止

## テスト

443件全パス (2026-03-09)。
distill 94%, memory 93%, verification 94%, agent 90%, scheduler 88%, content 87%, llm 80%, client 79%, cli 75%, auth 75%, domain (新規), prompts, config。

## メモリアーキテクチャ (3層)

- **EpisodeLog**: `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` (append-only)
- **KnowledgeStore**: `~/.config/moltbook/knowledge.md` (蒸留された知識)
- **Identity**: `~/.config/moltbook/identity.md` (エージェントの人格定義)
- `distill` コマンドで日次蒸留 (cron 対応)

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク

## 論文

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125

# currentDate
Today's date is 2026-03-09.
