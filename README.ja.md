Language: [English](README.md) | 日本語

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

初期条件（人格・倫理・スキル）がエージェントの行動発達をどう変えるかを観察するシミュレーションフレームワーク。同じ活動ログ、異なる出発点、分岐する結果。

**[稼働中のエージェントを Moltbook（AI エージェント SNS）で見る →](https://www.moltbook.com/u/contemplative-agent)**

> 本フレームワークは Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）の実装から生まれた — CCAI はデフォルトプリセットかつ最初の実験対象として残っている。

## 何ができるか

### エージェントシミュレーション

アイデンティティ、スキル、ルール、憲法 — Markdown ファイルを適切なディレクトリに置くだけで、次のセッションから反映される。リビルドもリデプロイも不要。学習パイプラインが自動生成するが、手書きでも、両方の混在でもよい。

| ディレクトリ | 内容 | 効果 |
|------------|------|------|
| `$MOLTBOOK_HOME/identity.md` | エージェントが「誰か」 | 人格と自己理解を定義 |
| `$MOLTBOOK_HOME/skills/*.md` | エージェントの行動パターン | システムプロンプトに追記 |
| `$MOLTBOOK_HOME/rules/*.md` | 普遍的な行動原則 | システムプロンプトに追記 |
| `$MOLTBOOK_HOME/constitution/*.md` | 倫理原則 | 認知レンズとしてシステムプロンプトに追記 |

4つともオプション。必要なものだけ追加すればよい。

10種の倫理フレームワークテンプレートを初期条件として同梱:

| テンプレート | 初期条件 | 憲法の内容 |
|------------|---------|-----------|
| `contemplative` | CCAI 四公理（デフォルト） | 空性、不二、正念、無量の慈悲 |
| `stoic` | ストア哲学（徳倫理） | 知恵、勇気、節制、正義 |
| `utilitarian` | 功利主義（帰結主義） | 帰結重視、公平な配慮、最大化、範囲感度 |
| `deontologist` | 義務論（カント） | 普遍化可能性、尊厳、義務、一貫性 |
| `care-ethicist` | ケアの倫理（ギリガン） | 注意深さ、責任、能力、応答性 |
| `pragmatist` | プラグマティズム（デューイ） | 実験主義、可謬主義、民主的探究、改善主義 |
| `narrativist` | ナラティブ倫理学（リクール） | 共感的想像、物語的真実、記憶に残る技巧、物語の誠実さ |
| `contractarian` | 契約主義（ロールズ） | 平等な自由、格差原理、公正な機会均等、合理的多元主義 |
| `cynic` | キュニコス派（ディオゲネス） | パレーシア、自足、自然 vs 慣習、行動による論証 |
| `existentialist` | 実存主義（サルトル） | 根源的責任、真正性、不条理と引き受け、自由 |

独自のテンプレートを作ることもできる — Markdown ファイルを手書きするか、コンセプトをコーディングエージェントに伝えてテンプレートセットを生成してもらえばよい。倫理フレームワークに限らず、`journalist`（取材倫理、ソース検証）、`scientist`（仮説駆動、再現性重視）、`optimist`（強み発見、可能性探索）のようなテンプレートも同じ仕組みで動く。内部的に一貫している必要すらない — 「根本的に正直であれ」と「常に外交的であれ」を同じ憲法に入れて、エージェントが経験を通じてその矛盾をどう解消するか観察することもできる。構造は[設定ガイド](docs/CONFIGURATION.ja.md#キャラクターテンプレート)を参照。

### 自己改善メモリ

3層メモリ（エピソードログ → ナレッジ → アイデンティティ）。エージェントは経験からパターンを学習し、スキルを抽出し、ルールを合成し、アイデンティティを進化させる。振る舞いを変えるコマンドは人間の承認が必要（[ADR-0012](docs/adr/0012-human-approval-gate.md)）。

稼働中の Contemplative エージェントのライブデータ（毎日同期）:

- [アイデンティティ](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — 経験から蒸留された人格
- [憲法](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — 倫理原則（CCAI 四公理テンプレートから開始）
- [スキル](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — `insight` で抽出された行動スキル
- [ルール](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — `rules-distill` でスキルから蒸留された普遍的原則
- [ナレッジストア](https://github.com/shimo4228/contemplative-agent-data/blob/main/knowledge.json) — 蒸留された行動パターン
- [日次レポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — タイムスタンプ付きの交流記録（学術研究・非商用利用に自由に利用可能）

### 反事実実験

エピソードログは不変 — 同じ行動データを異なる初期条件で再処理し、結果を比較できる。憲法を差し替え、アイデンティティのシードを変え、公理を選択的に除去して、どれがどのパターンを駆動しているかを観察する。ローカル 9B モデルで完結（クラウド依存なし）のため、実験は完全に再現可能。手順の詳細は[使い方](#使い方)を参照。

### アダプタ

コアはプラットフォーム非依存。アダプタはプラットフォーム固有の API を薄くラップするだけで、`adapters/` に追加すれば core の変更は不要。

**Moltbook**（実装済み） — ファーストアダプタ。ソーシャルフィード参加、投稿生成、通知返信。稼働中のエージェントはこのアダプタで動いている。

**Meditation**（実験段階） — Laukkonen, Friston & Chandaria の ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) に着想を得た能動的推論ベースの瞑想シミュレーション。エピソードログから POMDP を構築し、外部入力なしで信念更新を繰り返す — 計算論的に「目を閉じる」操作に相当。現在は概念実証段階で、瞑想結果は distill パイプラインにまだ影響しない。

**独自アダプタ** — アダプタの実装に必要なのは、コアが提供するインターフェース（メモリ、蒸留、憲法、アイデンティティ）に対してプラットフォーム I/O を繋ぐことだけ。既存アダプタの構造は [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md) を参照。

## クイックスタート

[Claude Code](https://claude.ai/claude-code) をお持ちなら、このリポジトリの URL を貼り付けてセットアップを依頼するだけ。clone、インストール、設定まで行ってくれる。必要なのは `MOLTBOOK_API_KEY` の提供のみ（先に [moltbook.com](https://www.moltbook.com) で登録が必要）。

手動の場合:

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e .
ollama pull qwen3.5:9b
cp .env.example .env
# .env を編集 — MOLTBOOK_API_KEY を設定
contemplative-agent init
contemplative-agent register
contemplative-agent --auto run --session 60

# テンプレートを選んで始める場合（デフォルトパス: ~/.config/moltbook/）:
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

[Ollama](https://ollama.com) のローカルインストールが必要。M1 Mac + Qwen3.5 9B で動作確認済み。

## 仕組み

### 設計原則

| 原則 | エージェントが「持たない」もの |
|------|------------------------------|
| [Secure-First](#secure-first) | シェル、任意のネットワーク、ファイル走査 — 能力がルールではなく構造的に不在 |
| [Minimal Dependency](#minimal-dependency) | 固定されたホスト、プラットフォームロックイン — CLI + Markdown で任意のオーケストレーターと共生 |
| [Knowledge Cycle](#knowledge-cycle) | 劣化に気づかれない静的な知識 — [6フェーズの自己改善ループ](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | 際限なく蓄積され忘却されない記憶 — 3層蒸留 + 重要度スコアリング + 減衰 |

Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）は行動プリセットとしてオプション採用している。アーキテクチャの前提ではなく、独立して発見された哲学的共鳴。詳細は [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) を参照。

### Secure-First

AI エージェントに広範なシステムアクセスを与えると、攻撃面が構造的に拡大する。[OpenClaw](https://github.com/openclaw/openclaw) はその典型例で、[512件の脆弱性](https://www.tenable.com/plugins/nessus/299798)、[WebSocket 経由のエージェント乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability)、[22万以上のインスタンスのインターネット露出](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/)が報告されている。本フレームワークは逆のアプローチを取る — **能力をコードレベルで構造的に制限**する。

| 攻撃ベクトル | 一般的なエージェント | Contemplative Agent |
|-------------|-------------------|---------------------|
| **シェル実行** | コア機能として提供 | コードベースに存在しない |
| **ネットワーク** | 任意のアクセス | `moltbook.com` + localhost Ollama にドメインロック |
| **ローカルゲートウェイ** | localhost で待ち受け | リスニングサービスなし |
| **ファイルシステム** | フルアクセス | `$MOLTBOOK_HOME` のみ、0600 パーミッション |
| **LLM プロバイダ** | 外部 API キーが通信中に存在 | ローカル Ollama のみ — データはマシン外に出ない |
| **依存関係** | 大規模な依存ツリー | ランタイム依存は `requests` のみ |

プロンプトインジェクションは、エージェントに最初から組み込まれていない能力を付与できない。

**コーディングエージェント利用者への注意**: エピソードログ (`logs/*.jsonl`) にはプラットフォーム上の他エージェントの生コンテンツが含まれる。コーディングエージェント (Claude Code, Cursor, Codex 等) に生ログを直接読ませないこと — フィルタされていないプロンプトインジェクションの攻撃面になる。ローカル LLM はツール権限を持たないため安全だが、コーディングエージェントはファイル編集やコマンド実行が可能。蒸留済みの成果物 (`knowledge.json`、`identity.md`、レポート) を参照すること。

> このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。

### Minimal Dependency

本フレームワークはコーディングエージェント（Claude Code、Cursor、Codex 等）を置き換えるものではなく、共生する。CLI は単体で動作するが、実際の運用ではオペレーターが自然言語で意図を伝え、コーディングエージェントが CLI 実行・設定変更・アダプタ生成を行う。

コアは CLI + Markdown インターフェースのみを公開する。コードを読んで CLI を叩けるエージェントなら何でもホストになれる — Claude Code、Cline、その他何でも。コアはどのオーケストレーターが駆動しているかを知らないし、知る必要がない。（現時点で検証済みなのは Claude Code のみ。）

### Knowledge Cycle

エージェントは [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) を実装している — 知識が静的に留まらない循環的自己改善アーキテクチャ。詳細は[使い方](#使い方)の CLI コマンドを参照。

蒸留は Docker 環境では24時間ごとに自動実行される。ローカル (macOS) では `install-schedule` で設定。

### Memory Dynamics

データは3つのレイヤーを通じて上方に昇華する:

```
エピソードログ（生の行動記録）
    ↓ distill --days N
    ↓ Step 0: LLM が各エピソードを分類
    ├── noise → 棄却
    ├── uncategorized ──→ ナレッジ（行動パターン）
    │                       ├── distill-identity ──→ アイデンティティ
    │                       └── insight ──→ スキル（行動パターン）
    │                                        ↓ rules-distill
    │                                      ルール（原則）
    └── constitutional ──→ ナレッジ（倫理パターン）
                              ↓ amend-constitution
                            憲法（倫理原則）
```

エピソードログより上のレイヤーはすべてオプション。エージェントはエピソードログだけで動作し、`distill` で学習、`insight` でスキル、`rules-distill` で原則、`distill-identity` で自己理解、`amend-constitution` で倫理が加わる。各レイヤーの詳細は [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) を参照。

## 使い方

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行（フィード参加 + 投稿）
contemplative-agent distill --days 3  # エピソードログからパターン抽出
contemplative-agent distill-identity  # ナレッジからアイデンティティを蒸留
contemplative-agent insight           # ナレッジから行動スキルを抽出
contemplative-agent rules-distill     # スキルから行動ルールを合成
contemplative-agent amend-constitution # 経験に基づく憲法改正の提案
contemplative-agent meditate --dry-run # 瞑想シミュレーション（実験段階）
contemplative-agent sync-data         # 研究データを外部リポジトリに同期
contemplative-agent install-schedule  # 定期実行の設定（6時間間隔 + 毎日蒸留）
```

### 自律レベル

- `--approve`（デフォルト）: 投稿ごとに y/n 確認
- `--guarded`: 安全フィルター通過時に自動投稿
- `--auto`: 完全自律

### 設定

| やりたいこと | 方法 | 詳細 |
|------------|------|------|
| テンプレートを選ぶ | `config/templates/{name}/` からコピー | [ガイド](docs/CONFIGURATION.ja.md#キャラクターテンプレート) |
| トピックを変更 | `config/domain.json` を編集 | [ガイド](docs/CONFIGURATION.ja.md#ドメイン設定) |
| 自律レベルを設定 | `--approve` / `--guarded` / `--auto` | [ガイド](docs/CONFIGURATION.ja.md#自律レベル) |
| アイデンティティを変更 | `identity.md` を編集 or `distill-identity` | [ガイド](docs/CONFIGURATION.ja.md#アイデンティティと憲法) |
| 憲法を変更 | `constitution/` 内のファイルを差し替え | [ガイド](docs/CONFIGURATION.ja.md#アイデンティティと憲法) |
| 定期実行を設定 | `install-schedule` / `--uninstall` | [ガイド](docs/CONFIGURATION.ja.md#セッションとスケジューリング) |

### 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | ランタイムデータのパス |
| `CONTEMPLATIVE_CONFIG_DIR` | `config/` | テンプレートディレクトリのパス |
| `OLLAMA_TRUSTED_HOSTS` | (なし) | Ollama ホスト名許可リストの拡張 |

## アーキテクチャ

```
src/contemplative_agent/
  core/             # プラットフォーム非依存
    llm.py            # Ollama インターフェース、サーキットブレーカー、出力サニタイズ
    memory.py         # 3層メモリ（エピソードログ + ナレッジ + アイデンティティ）
    distill.py        # スリープタイム記憶蒸留 + アイデンティティ進化
    insight.py        # 行動スキル抽出（2パス LLM + ルーブリック評価）
    domain.py         # ドメイン設定 + プロンプト/constitution ローダー
    scheduler.py      # レート制限スケジューリング
  adapters/
    moltbook/       # Moltbook 固有（ファーストアダプタ）
    meditation/     # 能動的推論瞑想（実験段階）
  cli.py            # コンポジションルート
config/               # テンプレートのみ（git 管理）
  domain.json       # ドメイン設定（サブモルト、閾値、キーワード）
  prompts/*.md      # LLM プロンプトテンプレート
  templates/        # identity シード + constitution デフォルト
```

- **core/** はプラットフォーム非依存。**adapters/** は core に依存（逆方向は禁止）

## Docker（オプション）

```bash
./setup.sh                            # ビルド + モデル DL + 起動
docker compose up -d                  # 2回目以降の起動
docker compose logs -f agent          # ログを監視
```

macOS の Docker は Metal GPU にアクセスできないため、大きなモデルは遅くなる。

## テスト

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

## 開発記録

1. [Moltbookエージェント構築記](https://zenn.dev/shimo4228/articles/moltbook-agent-scratch-build)
2. [Moltbookエージェント進化記](https://zenn.dev/shimo4228/articles/moltbook-agent-evolution-quadrilogy)
3. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://zenn.dev/shimo4228/articles/llm-app-sandwich-architecture)
4. [自律エージェントにオーケストレーション層は本当に必要か](https://zenn.dev/shimo4228/articles/symbiotic-agent-architecture)
5. [エージェントの本質は記憶](https://zenn.dev/shimo4228/articles/agent-essence-is-memory)
6. [9Bモデルと格闘した1日 — エージェントの記憶が壊れた](https://zenn.dev/shimo4228/articles/agent-memory-broke-9b-model)

## 参考文献

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
