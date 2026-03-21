# Contemplative Agent

自律 AI エージェントフレームワーク。構造的に権限を最小化し、Docker コンテナ化で強制。初期アダプタは Moltbook (AI エージェント SNS)。Contemplative AI 四公理はオプションプリセット。

## 構造

```
config/                                 # 外部化された設定・テンプレート + 学習成果
  domain.json                           # ドメイン設定 (サブモルト, 閾値, キーワード)
  prompts/                              # プロンプトテンプレート (.md, ドメイン非依存)
  rules/default/                        # デフォルトルール (ニュートラル、公理なし)
  rules/contemplative/                  # Contemplative AI プリセット (四公理)
  identity.md                           # エージェントの人格定義 (distill で更新)
  knowledge.json                         # 蒸留された知識パターン (distill で更新、JSON配列)
  skills/                               # 抽出された行動スキル (insight で生成)
  launchd/                              # macOS launchd テンプレート
setup.sh                                # 初回セットアップ (ビルド + モデルDL + 起動)
Dockerfile                              # マルチステージ、非root (UID 1000)
docker-compose.yml                      # agent + ollama (ネットワーク分離)
docker-entrypoint.sh                    # セッションループ + auto-distill
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
    knowledge_store.py                  # Layer 2: 蒸留された知識パターン (JSON 永続化)
    memory.py                           # Layer 3: MemoryStore ファサード + dataclass + re-export
    distill.py                          # スリープタイム記憶蒸留
    insight.py                          # 行動スキル抽出 (single-pass, /learn-eval フォーマット)
    scheduler.py                        # レート制限スケジューラ (パラメータ化)
    report.py                           # アクティビティレポート生成 (JSONL → Markdown)
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
    meditation/                         # Active Inference 瞑想シミュレーション
      config.py                         # 状態空間定義、瞑想パラメータ
      pomdp.py                          # Episode Log → POMDP 行列 (A/B/C/D)
      meditate.py                       # 瞑想ループ (temporal flattening + counterfactual pruning)
      report.py                         # 結果解釈 → KnowledgeStore 書き込み
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
contemplative-agent init                          # identity.md + knowledge.json 作成
contemplative-agent distill --dry-run             # 記憶蒸留 (dry run)
contemplative-agent distill --days 3              # 3日分を蒸留
contemplative-agent insight --dry-run             # 行動スキル抽出 (dry run)
contemplative-agent insight                       # 行動スキルを skills/ に生成
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"
contemplative-agent generate-report               # 本日のアクティビティレポート生成
contemplative-agent generate-report --all          # 全日分を生成
contemplative-agent meditate --dry-run             # 瞑想シミュレーション (dry run)
contemplative-agent meditate --days 14 --cycles 100  # 14日分、100サイクル
contemplative-agent install-schedule              # launchd 定期起動 (6h毎, 120分)
contemplative-agent install-schedule --uninstall  # スケジュール削除

# ルール切替 (デフォルトはニュートラル、四公理を使う場合:)
contemplative-agent --rules-dir config/rules/contemplative/ run --session 30
# カスタムドメイン
contemplative-agent --domain-config path/to/domain.json --rules-dir path/to/rules/ run --session 30
```

- Python 3.9+ (venv は 3.13.5)
- 依存: requests, numpy。LLM は Ollama (qwen3.5:9b, localhost or Docker service)
- ビルド: hatch
- 33 モジュール、~6400 LOC (memory 3層分割 + meditation adapter + insight.py + report.py + _io.py 共有ユーティリティ)

### Docker

```bash
./setup.sh                                              # 初回: ビルド + モデルDL + 起動
./setup.sh llama3.1:8b                                  # 追加モデルのDL
docker compose up -d                                    # 2回目以降: 起動
docker compose logs -f agent                            # ログ確認
docker compose run agent command distill --days 3       # CLI パススルー
docker compose down                                     # 停止
```

- `CONTEMPLATIVE_CONFIG_DIR` env var で config/ パスをオーバーライド可能
- `OLLAMA_TRUSTED_HOSTS` env var で Ollama ホスト名許可リストを拡張可能
- `docker-compose.override.yml` で既存データディレクトリをバインドマウント可能

## セキュリティ方針

- ランタイムデータ: `MOLTBOOK_HOME` 環境変数でカスタマイズ可 (デフォルト: `~/.config/moltbook`、credentials/logs/rate_state)
- 学習成果: `config/` 配下 (identity.md, knowledge.json, skills/)。`CONTEMPLATIVE_CONFIG_DIR` でオーバーライド可
- API key: env var > `$MOLTBOOK_HOME/credentials.json` (0600)。ログには `_mask_key()` のみ
- HTTP: `allow_redirects=False`、ドメイン `www.moltbook.com` のみ、Retry-After 300s キャップ
- LLM: Ollama は LOCALHOST_HOSTS + OLLAMA_TRUSTED_HOSTS (ドット無しホスト名のみ) で制限。出力は `re.IGNORECASE` で禁止パターン除去。外部コンテンツ・knowledge context は `<untrusted_content>` タグでラップ。identity.md は forbidden pattern 検証済み
- Docker: Ollama は internal-only ネットワーク (インターネットアクセスなし、setup.sh 初回のみ一時接続)。agent は非root (UID 1000)。OLLAMA_MODEL はフォーマット検証済み
- post_id: `[A-Za-z0-9_-]+` バリデーション
- Verification: 連続7失敗で自動停止

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3層防御（`has_read_budget()`/`has_write_budget()` バジェット、プロアクティブ待機、リアクティブバックオフ）。API 仕様の詳細は `WebFetch https://www.moltbook.com/skill.md` で最新を参照。

## テスト

639件全パス (2026-03-21)。
distill 94%, memory 93%, verification 94%, agent 90%, meditation (54 tests), insight ~85%, scheduler 88%, content 87%, llm 80%, client 79%, cli 75%, auth 75%, domain, prompts, config (core/adapters 分割済み)。

## メモリアーキテクチャ (3層)

- **EpisodeLog**: `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` (append-only, ランタイム。interaction/post/insight/activity)
- **KnowledgeStore**: `config/knowledge.json` (蒸留された知識パターンのみ, バッチ更新)
- **agents.json**: `~/.config/moltbook/agents.json` (フォロー状態, ランタイム)
- **Identity**: `config/identity.md` (エージェントの人格定義, バッチ更新)
- **Skills**: `config/skills/*.md` (行動スキル, insight で生成)
- Agent Relationships, Post Topics, Insights は JSONL が正 (knowledge.md の重複保存を廃止)
- `distill` コマンドで日次蒸留 (Docker: 24時間間隔で自動実行、ローカル: cron 対応)
- セッション開始時に `type=session, event=start` でルール・ドメイン・モデル等のメタデータを記録
- セッション終了時に `type=session, event=end` でアクション数サマリーを記録

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク

## 論文

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125

Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews. (瞑想の計算モデル — meditation adapter の理論的基盤)

# currentDate
Today's date is 2026-03-16.
