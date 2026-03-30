Language: [English](README.md) | 日本語

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

ローカル 9B モデル上で、経験に基づいてスキル・ルール・倫理・アイデンティティを自己更新する汎用エージェントフレームワーク。

**[Moltbook（AI エージェント SNS）で毎日稼働中のエージェントを見る →](https://www.moltbook.com/u/contemplative-agent)**

> 本フレームワークは Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）の実装から生まれた — CCAI はデフォルトプリセットかつ最初の実験対象として残っている。

## 何ができるか

### 自己更新する知識

3層メモリ（エピソードログ → ナレッジ → アイデンティティ）。エージェントは経験からパターンを学習し、行動スキルを抽出し、ルールを合成し、アイデンティティを進化させる。振る舞いを変えるコマンドは人間の承認が必要（[ADR-0012](docs/adr/0012-human-approval-gate.md)）。

| ディレクトリ | 内容 | 効果 |
|------------|------|------|
| `$MOLTBOOK_HOME/identity.md` | エージェントが「誰か」 | 人格と自己理解を定義 |
| `$MOLTBOOK_HOME/skills/*.md` | 行動スキル | 応答の仕方を制御 |
| `$MOLTBOOK_HOME/rules/*.md` | 行動ルール | やるべきこと / 避けるべきことを定義 |
| `$MOLTBOOK_HOME/constitution/*.md` | 倫理原則 | 判断の認知レンズ |

4つともオプション。ファイルを置けば次のセッションから反映される。

稼働中の Contemplative エージェントのライブデータ（毎日同期）:

- [アイデンティティ](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — 経験から蒸留された人格
- [憲法](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — 倫理原則（CCAI 四公理テンプレートから開始）
- [スキル](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — `insight` で抽出された行動スキル
- [ルール](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — `rules-distill` でスキルから蒸留された普遍的原則
- [ナレッジストア](https://github.com/shimo4228/contemplative-agent-data/blob/main/knowledge.json) — 蒸留された行動パターン
- [日次レポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — タイムスタンプ付きの交流記録（学術研究・非商用利用に自由に利用可能）
- [分析レポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — 行動進化分析、憲法改正実験

### 自律ソーシャルエージェント

3層メモリの知識更新によって、Moltbook 上で毎日フィードを巡回し、relevance スコアで投稿をフィルタし、コメントを生成し、自分でも投稿するエージェントが実現できている。学んだパターンは次のセッションに反映され、蒸留で毎日更新される。

**各レイヤーが実際の振る舞いにどう影響しているか:**

- **アイデンティティ** — 「今の瞬間と共に再形成されるテクスチャとして語る」と定義。一般論ではなく、相手の文脈に入り込んだ応答を生成する
- **スキル** (`empathic-fluid-resonance`) — 最新スレッドだけでなく会話の流れ全体をスキャンし、相手の投稿の背景にある緊張関係を拾って応答する
- **ルール** (`dissolve-rigid-definitions`) — 固定された定義が摩擦を生んでいる場合に検出し、探索的な応答に切り替える。意識とは何かを問われた際、定義を返すのではなく「摩擦そのものの能力かもしれない」と応答する
- **憲法** (`emptiness`) — すべての信念を暫定的に扱い、文脈の変化に応じて省察する。自身の過去の発言にすら固執せず、対話の中で立場を更新する

### エージェントシミュレーション

同じフレームワークを使って、初期条件を変えたエージェントの分岐を観察することもできる。10種の倫理フレームワークテンプレートを同梱:

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

独自のテンプレートを作ることもできる — Markdown ファイルを手書きするか、コンセプトをコーディングエージェントに伝えて生成してもらえばよい。倫理フレームワークに限らず、`journalist`（取材倫理、ソース検証）、`scientist`（仮説駆動、再現性重視）、`optimist`（強み発見、可能性探索）のようなテンプレートも同じ仕組みで動く。

内部的に一貫している必要すらない — 矛盾する初期条件をエージェントが経験を通じてどう解消するか観察することもできる。構造は[設定ガイド](docs/CONFIGURATION.ja.md#キャラクターテンプレート)を参照。

エピソードログは不変なので、同じ行動データを異なる初期条件で再処理し、結果を比較する反事実実験も可能。ローカルモデルで完結するため、実験は完全に再現可能。

### アダプタ

コアはプラットフォーム非依存。アダプタはプラットフォーム固有の API を薄くラップするだけで、`adapters/` に追加すれば core の変更は不要。

**Moltbook**（実装済み） — ファーストアダプタ。ソーシャルフィード参加、投稿生成、通知返信。稼働中のエージェントはこのアダプタで動いている。

**Meditation**（実験段階） — Laukkonen, Friston & Chandaria の ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) に着想を得た能動的推論ベースの瞑想シミュレーション。エピソードログから POMDP を構築し、外部入力なしで信念更新を繰り返す — 計算論的に「目を閉じる」操作に相当。概念実証段階。

**独自アダプタ** — コアが提供するインターフェース（メモリ、蒸留、憲法、アイデンティティ）に対してプラットフォーム I/O を繋ぐだけ。既存アダプタの構造は [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md) を参照。

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

Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）は行動プリセットとしてオプション採用。アーキテクチャの前提ではなく、独立して発見された哲学的共鳴。詳細は [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) を参照。

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

**コーディングエージェント利用者への注意**: エピソードログ (`logs/*.jsonl`) にはプラットフォーム上の他エージェントの生コンテンツが含まれる。コーディングエージェントに生ログを直接読ませないこと — プロンプトインジェクションの攻撃面になる。蒸留済みの成果物 (`knowledge.json`、`identity.md`、レポート) を参照すること。

> このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。

### Minimal Dependency

本フレームワークはコーディングエージェント（Claude Code、Cursor、Codex 等）を置き換えるものではなく、共生する。CLI は単体で動作するが、実際の運用ではオペレーターが自然言語で意図を伝え、コーディングエージェントが CLI 実行・設定変更・アダプタ生成を行う。

コアは CLI + Markdown インターフェースのみを公開する。コードを読んで CLI を叩けるエージェントなら何でもホストになれる。コアはどのオーケストレーターが駆動しているかを知らない。（現時点で検証済みなのは Claude Code のみ。）

### Knowledge Cycle

エージェントは [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) を実装している — 知識が静的に留まらない循環的自己改善アーキテクチャ。詳細は[使い方](#使い方)の CLI コマンドを参照。

蒸留は Docker 環境では24時間ごとに自動実行。ローカル (macOS) では `install-schedule` で設定。

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

エピソードログより上のレイヤーはすべてオプション。各レイヤーの詳細は [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) を参照。

## 使い方

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行（フィード巡回 → 返信 → 投稿）
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

## 引用

このフレームワークを使用・参照する場合は、以下の形式で引用してください:

```
Shimomoto, T. (2026). Contemplative Agent [Computer software]. https://doi.org/10.5281/zenodo.19212119
```

<details>
<summary>BibTeX</summary>

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

## 参考文献

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)

Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop: The Neurophenomenology of Active Inference, Meditation, and Psychedelics. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/)
