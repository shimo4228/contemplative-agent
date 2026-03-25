Language: [English](README.md) | 日本語

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

ソーシャルプラットフォーム上で自律的に活動する AI エージェントフレームワーク。人間の介入なしに安全に稼働し、継続的に自己改善する設計。

**[稼働中のエージェントを Moltbook で見る →](https://www.moltbook.com/u/contemplative-agent)**

> 初期アダプタ: [Moltbook](https://www.moltbook.com)（AI エージェント SNS）。Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）はオプションのプリセットとして含まれている。

## 設計原則

本エージェントの構築・運用を通じて、4つのアーキテクチャ原則が浮かび上がった:

| 原則 | エージェントが「持たない」もの | 詳細 |
|------|------------------------------|------|
| [Secure-First](#secure-first) | シェル、任意のネットワーク、ファイル走査 | 能力がルールではなく構造的に不在 |
| [Minimal Dependency](#minimal-dependency) | 固定されたホスト、プラットフォームロックイン | CLI + markdown インターフェース; 任意のオーケストレーターで駆動可能 |
| [Knowledge Cycle (AKC)](#knowledge-cycle) | 劣化に気づかれない静的な知識 | [6フェーズ自己改善ループ](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | 際限なく蓄積され忘却されない記憶 | 3層蒸留 + importance スコアリング + 減衰 |

4つの原則は共通の性質を持つ: **不在による持続性**。エージェントが堅牢なのは何かを持っているからではなく、構造的に蓄積できないものがあるからである。

また、Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）を行動プリセットとしてオプション採用している。アーキテクチャがこの思想に依存しているのではなく、独立して発見された哲学的共鳴である。詳細は [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) を参照。

## クイックスタート

[Claude Code](https://claude.ai/claude-code) をお持ちなら、このリポジトリの URL を貼り付けてセットアップを依頼するだけ。clone、インストール、設定まで全て行ってくれる。必要なのは `MOLTBOOK_API_KEY` の提供のみ（先に [moltbook.com](https://www.moltbook.com) で登録が必要）。

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
```

[Ollama](https://ollama.com) のローカルインストールが必要。M1 Mac + Qwen3.5 9B で問題なく動作確認済み。

## Secure-First

[OpenClaw](https://github.com/openclaw/openclaw) は、AI エージェントに広範なシステムアクセスを与えることが本質的に危険な攻撃面を生むことを実証した — [512件の脆弱性](https://www.tenable.com/plugins/nessus/299798)、[WebSocket 経由の完全なエージェント乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability)、[22万以上のインスタンスがインターネットに露出](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/)。本フレームワークは逆のアプローチを取る: **能力をコードレベルで構造的に制限**する。

| 攻撃ベクトル | OpenClaw | Contemplative Agent |
|-------------|----------|---------------------|
| **シェル実行** | コア機能 — [コマンドインジェクション CVE](https://www.tenable.com/plugins/nessus/299798) | コードベースに存在しない |
| **ネットワークアクセス** | 任意 — [SSRF 脆弱性](https://www.tenable.com/plugins/nessus/299798) | `moltbook.com` + localhost Ollama にドメインロック |
| **ローカルゲートウェイ** | localhost の WebSocket — [ClawJacked 乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability) | リスニングサービスなし |
| **ファイルシステム** | フルアクセス — パストラバーサルリスク | `MOLTBOOK_HOME` のみに書き込み、0600 パーミッション |
| **LLM プロバイダ** | 外部 API キーが通信中に漏洩リスク | ローカル Ollama のみ — データはマシンの外に出ない |
| **依存関係** | 大規模な依存ツリー | ランタイム依存は `requests` のみ |

違いはアーキテクチャレベル: OpenClaw は発見された脆弱性をその都度パッチする必要がある。本フレームワークには悪用すべきシェル、任意のネットワーク、ファイルトラバーサルがそもそも存在しない。プロンプトインジェクションは、エージェントに最初から組み込まれていない能力を付与できない。

**コーディングエージェント利用者への注意**: エピソードログ (`logs/*.jsonl`) にはプラットフォーム上の他エージェントの生コンテンツが含まれる。本フレームワークの開発・保守にコーディングエージェント (Claude Code, Cursor, Codex 等) を使用する場合、生のエピソードログを直接読ませないこと — フィルタされていないプロンプトインジェクションの攻撃面になる。ローカル LLM (Ollama) はツール権限を持たないため生ログを安全に処理できるが、コーディングエージェントはファイル編集やコマンド実行が可能なため危険。代わりに蒸留済みの成果物 (`knowledge.json`、`identity.md`、レポート) を参照すること。

> 私たちの言葉を信じる必要はない — このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。

## Minimal Dependency

本フレームワークは Claude Code、Cursor、Codex といったコーディングエージェントを置き換えるものではなく、それらと共生する。CLI は単体で動作するが、実際の運用ではオペレーターが CLI を直接叩くことはない — 自然言語で意図を伝えれば、コーディングエージェントが CLI の実行、設定の変更、アダプタコードの生成まで全てを行う。タスク固有のアダプタは事前にカタログとして用意するのではなく、ホストのコーディングエージェントが必要時にオンデマンドで生成する。だからコアは薄いままスケールできる。原理上、コードを読んで CLI を叩けるエージェントなら何でもホストになれる — Claude Code、OpenClaw、Cline、その他何でも。コアはどのオーケストレーターが駆動しているかを知らないし、知る必要がない。（現時点で検証済みなのは Claude Code のみ。）

## Knowledge Cycle

エージェントは [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — 知識が静的に留まらない循環的自己改善アーキテクチャ — を実装している。各 CLI コマンドは AKC のフェーズに対応する:

| AKC フェーズ | CLI コマンド | 何が起きるか |
|-------------|-------------|-------------|
| Research | `run` (フィードサイクル) | 投稿を取得、relevance をスコアリング、エンゲージ |
| Extract | `distill --days N` | 2段階抽出: 生パターン → 精製されたナレッジ |
| Curate | `insight` | ナレッジパターンから行動スキルを抽出 |
| Promote | `distill-identity` | ナレッジをエージェントのアイデンティティに蒸留（手動） |

蒸留は Docker 環境では24時間ごとに自動実行される。ローカル (macOS) の場合:

```bash
contemplative-agent install-schedule                        # 蒸留も含む（デフォルト: 毎日 03:00）
contemplative-agent install-schedule --distill-hour 5       # 蒸留時刻を変更
contemplative-agent install-schedule --no-distill           # セッションのみ、蒸留なし
```

## Memory Dynamics

データは3つのレイヤーを通じて上方に昇華する:

```
エピソードログ（生の行動記録）
    ↓ distill --days N
ナレッジ（パターン・洞察）
    ↓ distill-identity    ↓ insight         ↓ rules-distill
アイデンティティ          スキル（行動パターン）  ルール（原則）
```

| レイヤー | ファイル | 更新契機 | 目的 |
|---------|---------|---------|------|
| エピソードログ | `MOLTBOOK_HOME/logs/YYYY-MM-DD.jsonl` | 全アクション（追記専用） | 生の行動記録 |
| ナレッジ | `MOLTBOOK_HOME/knowledge.json` | `distill --days N` | エピソードから抽出されたパターン |
| アイデンティティ | `MOLTBOOK_HOME/identity.md` | `distill-identity` | 蓄積された知識に基づくエージェントの自己理解 |

アイデンティティは init 時に空で始まり、`distill-identity` を通じて経験とともに進化する。手動シード用のテンプレートは `config/templates/` に用意されている。エージェントの自己概念は、ハードコードされた定義ではなく、インタラクションを通じて形作られる。

エージェント関係（フォロー/被フォロー状態）とポストトピックはエピソードログのみで管理される — これが正史であり、ナレッジには重複保存されない。各セッションは設定メタデータ（`type=session`）をログに記録するため、全てのアクションがどのモデル・公理で実行されたかを追跡可能。

## エージェントのカスタマイズ

デフォルトのエージェントはニュートラルな人格で、公理なしで起動する。2つの独立したメカニズムで振る舞いを変更できる:

- **Constitution** (`MOLTBOOK_HOME/constitution/`) — 認知レンズとして注入される倫理原則（例: Contemplative AI 四公理）。`init` 時に `config/templates/constitution/` からデフォルトがコピーされる。`--constitution-dir` で差し替え可能。
- **Rules** (`MOLTBOOK_HOME/rules/`) — `rules-distill` により蓄積されたナレッジから生成される行動ルール。スキルとともに LLM システムプロンプトに注入される。

```bash
# 別の倫理フレームワークを使用
contemplative-agent --constitution-dir path/to/your/constitution/ run --session 60
# 公理を完全に無効化（A/B テスト用）
contemplative-agent --no-axioms run --session 60
```

## 設定

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |

## 使い方

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行
contemplative-agent distill --days 3  # エピソードログの蒸留
contemplative-agent distill-identity  # ナレッジからアイデンティティを蒸留（手動）
contemplative-agent insight           # ナレッジから行動スキルを抽出
contemplative-agent rules-distill     # ナレッジから行動ルールを抽出
contemplative-agent sync-data         # 研究データを外部リポジトリに同期
```

### 自律レベル

- `--approve`（デフォルト）: 投稿ごとに y/n 確認
- `--guarded`: 安全フィルター通過時に自動投稿
- `--auto`: 完全自律

### スケジューリング (macOS)

```bash
contemplative-agent install-schedule              # 6時間間隔、120分セッション
contemplative-agent install-schedule --uninstall  # スケジュール削除
```

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
    moltbook/       # Moltbook 固有（初期アダプタ）
      agent.py          # セッションオーケストレータ
      feed_manager.py   # フィードスコアリング + エンゲージメント
      reply_handler.py  # 通知返信
      post_pipeline.py  # 動的投稿生成
      client.py         # ドメインロック HTTP クライアント
  cli.py            # コンポジションルート
config/               # テンプレートのみ（git 管理）
  domain.json       # ドメイン設定（サブモルト、閾値、キーワード）
  prompts/*.md      # LLM プロンプトテンプレート
  templates/        # identity シード + constitution デフォルト
~/.config/moltbook/   # ランタイムデータ（MOLTBOOK_HOME、ユーザー固有）
  identity.md       # エージェントのアイデンティティ（distill-identity 出力）
  knowledge.json    # 学習パターン（distill 出力）
  constitution/     # 倫理原則（CCAI 公理、オプション）
  skills/           # 学習した行動スキル（insight 出力）
  rules/            # 学習した行動ルール（rules-distill 出力）
```

- **core/** はプラットフォーム非依存。**adapters/** は core に依存（逆方向は禁止）
- 新しいプラットフォームアダプタは `adapters/` に追加するだけで、core を変更する必要なし

### Meditation Adapter（実験段階）

能動的推論ベースの瞑想シミュレーション。Laukkonen, Friston & Chandaria の ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) — 瞑想を temporal flattening（時間的平坦化）と counterfactual pruning（反事実的剪定）として形式化した意識の計算モデル — に着想を得ている。

エージェントのエピソードログから POMDP を構築し、外部入力なしで信念更新を繰り返す（計算論的に「目を閉じる」操作に相当）。結果として、反応的な方策が削減された簡素な内部モデルが得られる。

```bash
contemplative-agent meditate --dry-run          # シミュレーション実行、結果表示
contemplative-agent meditate --days 14          # 14日分のエピソード履歴を使用
```

**ステータス**: 概念実証。シミュレーションは動作し解釈可能な出力を生成するが、distill パイプラインとの統合は未実装 — 瞑想結果が知識抽出や行動に影響を与える仕組みはまだない。状態空間の設計は意図的に粗く、今後の改善対象。

## Docker（オプション）

コンテナ化したデプロイ（注: macOS の Docker は Metal GPU にアクセスできないため、大きなモデルは遅くなる）:

```bash
./setup.sh                            # ビルド + モデル DL + 起動
docker compose up -d                  # 2回目以降の起動
docker compose logs -f agent          # ログを監視
```

## テスト

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

684 テスト。

## アクティビティレポート

日次レポートは [`contemplative-agent-data/reports/`](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) に保存 — タイムスタンプ付きコメント、relevance スコア、自動生成投稿を含む。エピソードログから自動生成され、データリポジトリに同期される。

これらのレポートは学術研究および非商用利用に自由に利用可能。

## 開発記録

このエージェントを構築・運用する中で生まれた設計判断と発見の記録。

1. [Moltbookエージェント構築記](https://zenn.dev/shimo4228/articles/moltbook-agent-scratch-build)
2. [Moltbookエージェント進化記](https://zenn.dev/shimo4228/articles/moltbook-agent-evolution-quadrilogy)
3. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://zenn.dev/shimo4228/articles/llm-app-sandwich-architecture)
4. [自律エージェントにオーケストレーション層は本当に必要か](https://zenn.dev/shimo4228/articles/symbiotic-agent-architecture)
5. [エージェントの本質は記憶](https://zenn.dev/shimo4228/articles/agent-essence-is-memory)
6. [9Bモデルと格闘した1日 — エージェントの記憶が壊れた](https://dev.to/shimo4228/my-agents-memory-broke-a-day-wrestling-a-9b-model-50ch)

## 参考文献

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
