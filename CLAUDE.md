# Contemplative Agent

Contemplative AI フレームワークを広める自律エージェント。初期アダプタは Moltbook (AI エージェント SNS)。

## 構造

```
config/                                 # 外部化された設定・テンプレート
  domain.json                           # ドメイン設定 (サブモルト, 閾値, キーワード)
  prompts/                              # プロンプトテンプレート (.md, ドメイン非依存)
  rules/contemplative/                  # ドメイン固有コンテンツ (.md)
src/contemplative_agent/
  __init__.py
  cli.py                                # Composition root (唯一 core/ と adapters/ の両方を import)
  core/                                 # プラットフォーム非依存のコアロジック
    _io.py                              # 共有ファイル I/O (write_restricted, truncate)
    config.py                           # セキュリティ定数・コンテンツ制限 (FORBIDDEN_*, MAX_*_LENGTH)
    domain.py                           # ドメイン設定・テンプレートローダー
    prompts.py                          # プロンプトテンプレート遅延ロード
    llm.py                              # Ollama LLM インターフェース (パラメータ化, サーキットブレーカー)
    episode_log.py                      # Layer 1: append-only JSONL ログ
    knowledge_store.py                  # Layer 2: 蒸留された知識 (Markdown 永続化)
    memory.py                           # Layer 3: MemoryStore ファサード + dataclass + re-export
    distill.py                          # スリープタイム記憶蒸留
    scheduler.py                        # レート制限スケジューラ (パラメータ化)
  adapters/
    moltbook/                           # Moltbook プラットフォーム固有
      config.py                         # URL, パス, タイムアウト, レート制限
      agent.py                          # セッション管理・オーケストレータ (570行)
      session_context.py                # 共有セッション状態 (協力者間の明示的コントラクト)
      feed_manager.py                   # フィード取得・スコアリング・エンゲージメント
      client.py                         # HTTP クライアント
      auth.py                           # クレデンシャル管理
      content.py                        # コンテンツテンプレート
      llm_functions.py                  # Moltbook 固有 LLM 関数
      reply_handler.py                  # 通知返信処理 (SessionContext 依存)
      post_pipeline.py                  # 動的投稿生成パイプライン (SessionContext 依存)
      verification.py                   # 認証チャレンジソルバー
tests/                                  # テストスイート
```

### Import 規約

- **core/ は adapters/ を import しない** (依存方向: adapters -> core)
- cli.py は composition root として両方を import (唯一の例外)
- core/ モジュールはコンストラクタ引数で設定を受け取る (パラメータ化)
- adapters/ が core/config の定数と adapter 固有の config を組み合わせて渡す
- 協力者 (ReplyHandler, PostPipeline, FeedManager) は Agent を import しない。SessionContext + Callable で依存注入

## 開発環境

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# テスト
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing

# CLI
contemplative-agent --help
contemplative-agent init                          # identity.md + knowledge.md 作成
contemplative-agent distill --dry-run             # 記憶蒸留 (dry run)
contemplative-agent distill --days 3              # 3日分を蒸留
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"
contemplative-agent install-schedule              # launchd 定期起動 (6h毎, 120分)
contemplative-agent install-schedule --uninstall  # スケジュール削除

# ドメイン切替
contemplative-agent --domain-config path/to/domain.json --rules-dir path/to/rules/ run --session 30
```

- Python 3.9+ (venv は 3.13.5)
- 依存: requests のみ。LLM は Ollama (qwen3.5:9b, localhost)
- ビルド: hatch
- 26 モジュール、~4970 LOC (memory 3層分割 + _io.py 共有ユーティリティ、llm_functions ヘルパー統一済み)

## セキュリティ方針

- データディレクトリ: `MOLTBOOK_HOME` 環境変数でカスタマイズ可 (デフォルト: `~/.config/moltbook`)
- API key: env var > `$MOLTBOOK_HOME/credentials.json` (0600)。ログには `_mask_key()` のみ
- HTTP: `allow_redirects=False`、ドメイン `www.moltbook.com` のみ、Retry-After 300s キャップ
- LLM: Ollama localhost のみ許可。出力は `re.IGNORECASE` で禁止パターン除去。外部コンテンツ・knowledge context は `<untrusted_content>` タグでラップ。identity.md は forbidden pattern 検証済み
- post_id: `[A-Za-z0-9_-]+` バリデーション
- Verification: 連続7失敗で自動停止

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3層防御（`has_read_budget()`/`has_write_budget()` バジェット、プロアクティブ待機、リアクティブバックオフ）。API 仕様の詳細は `WebFetch https://www.moltbook.com/skill.md` で最新を参照。

## テスト

520件全パス (2026-03-14)。
distill 94%, memory 93%, verification 94%, agent 90%, scheduler 88%, content 87%, llm 80%, client 79%, cli 75%, auth 75%, domain, prompts, config (core/adapters 分割済み)。

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
Today's date is 2026-03-14.
