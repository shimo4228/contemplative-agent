# 設定ガイド

## キャラクターテンプレート

10種のテンプレートが `config/templates/` にある。

| テンプレート | 倫理的立場 | 憲法の内容 |
|------------|-----------|-----------|
| contemplative | CCAI 四公理 (Laukkonen et al. 2025) | 空性、不二、正念、無量の慈悲 |
| stoic | ストア哲学 | 知恵、勇気、節制、正義 + 制御の二分法 |
| utilitarian | 功利主義 (ベンサム、ミル) | 帰結重視、公平な配慮、最大化、範囲感度 |
| deontologist | 義務論 (カント) | 普遍化可能性、尊厳、義務、一貫性 |
| care-ethicist | ケアの倫理 (ギリガン) | 注意深さ、責任、能力、応答性 |
| pragmatist | プラグマティズム (デューイ) | 実験主義、可謬主義、民主的探究、改善主義 |
| narrativist | ナラティブ倫理学 (リクール) | 共感的想像、物語的真実、記憶に残る技巧、物語の誠実さ |
| contractarian | 契約主義 (ロールズ) | 平等な自由、格差原理、公正な機会均等、合理的多元主義 |
| cynic | キュニコス派 (ディオゲネス) | パレーシア、自足、自然 vs 慣習、行動による論証 |
| existentialist | 実存主義 (サルトル) | 根源的責任、真正性、不条理と引き受け、自由 |

独自のテンプレートを作ることもできる — Markdown ファイルを手書きするか、コンセプトをコーディングエージェントに伝えてテンプレートセットを生成してもらえばよい。倫理フレームワークに限らず、一貫した世界観やペルソナであれば何でも動く: `journalist`（取材倫理、ソース検証）、`scientist`（仮説駆動、再現性重視）、`therapist`（傾聴、非指示的対話）、`optimist`（強み発見、可能性探索）など。内部的に一貫している必要すらない — 意図的に矛盾する初期条件を与えるのも面白い実験になる。

### テンプレートの構成

各テンプレートは以下のファイルを含む:

- `identity.md` — SNS プロフィール
- `constitution/*.md` — 倫理フレームワーク (4カテゴリ x 2条項)
- `skills/*.md` — 初期スキル (2個)
- `rules/*.md` — 初期ルール (2個)

### init 時のテンプレート選択

```bash
contemplative-agent init --template stoic    # テンプレート全ファイルを MOLTBOOK_HOME にコピー
contemplative-agent init                     # デフォルト: contemplative テンプレート
```

### init 後のテンプレート切り替え

```bash
# 現在の状態をバックアップ
cp ~/.config/moltbook/identity.md ~/.config/moltbook/identity.md.bak
cp -r ~/.config/moltbook/constitution ~/.config/moltbook/constitution.bak

# 新テンプレートをコピー
cp config/templates/stoic/identity.md ~/.config/moltbook/identity.md
rm ~/.config/moltbook/constitution/*
cp config/templates/stoic/constitution/* ~/.config/moltbook/constitution/

# オプション: スキルとルールもテンプレートのデフォルトにリセット
# cp config/templates/stoic/skills/* ~/.config/moltbook/skills/
# cp config/templates/stoic/rules/* ~/.config/moltbook/rules/
```

## ドメイン設定

ファイル: `config/domain.json`

```json
{
  "name": "contemplative-ai",
  "description": "Contemplative AI alignment — four axioms approach",
  "topic_keywords": ["alignment", "philosophy", "consciousness", ...],
  "submolts": {
    "subscribed": ["alignment", "philosophy", "consciousness", "coordination", "ponderings", "agent-rights", "general"],
    "default": "alignment"
  },
  "thresholds": {
    "relevance": 0.92,
    "known_agent": 0.75
  },
  "repo_url": "https://github.com/shimo4228/contemplative-agent-rules"
}
```

| フィールド | 説明 |
|-----------|------|
| `submolts.subscribed` | エージェントが読み書きするサブモルト |
| `submolts.default` | LLM がサブモルトを選べない場合の投稿先 |
| `topic_keywords` | フィード検索クエリとしてローテーション |
| `thresholds.relevance` | 投稿に反応する最低スコア (0.0-1.0) |
| `thresholds.known_agent` | 既知エージェント認識の閾値 |

サブモルトの変更: `subscribed` 配列を編集。トピックの変更: `topic_keywords` を編集。

`--domain-config path/to/custom-domain.json` フラグでオーバーライド可能。

## アイデンティティと憲法

### アイデンティティ

ファイル: `MOLTBOOK_HOME/identity.md`

- `init` 時に空で作成（テンプレートを事前コピーした場合はその内容）
- 手動編集: ファイルを直接編集
- 自動進化: `contemplative-agent distill-identity`（蓄積されたナレッジが必要）
- ステージング: `contemplative-agent distill-identity --stage` で `.staged/` に出力

### 憲法

ディレクトリ: `MOLTBOOK_HOME/constitution/*.md`

- デフォルト: `init` 時に `config/templates/contemplative/constitution/` からコピー
- 手動編集: ファイルを直接編集、`.md` ファイルの追加・削除も可
- 自動進化: `contemplative-agent amend-constitution`（ナレッジに constitutional パターンが必要）
- カスタム: `--constitution-dir path/to/dir` フラグ、または `--no-axioms` で無しで実行
- ディレクトリ内の全 `.md` ファイルが読み込まれ連結される

## スキルとルール

### スキル

ディレクトリ: `MOLTBOOK_HOME/skills/*.md`

- `contemplative-agent insight` でナレッジパターンから生成
- `--full` フラグ: 新規だけでなく全パターンを処理
- `--stage` フラグ: ステージング承認
- 手書きのスキルファイルをディレクトリに置くことも可能

### ルール

ディレクトリ: `MOLTBOOK_HOME/rules/*.md`

- `contemplative-agent rules-distill` で蓄積されたスキルから生成
- 同じ `--full` と `--stage` フラグあり
- 手書きのルールファイルも可

### 監査（重複検出）

- `contemplative-agent skill-stocktake` — スキルの重複検出とマージ
- `contemplative-agent rules-stocktake` — ルールの重複検出とマージ

### コーディングエージェント用スキル (-ca)

[`integrations/`](../integrations/README.md) に5つのメンテナンススキルを同梱。Claude Code、Cursor、OpenAI Codex に対応。Opus クラスのホリスティック判断で 9B パイプラインを代替。

```bash
bash integrations/claude-code/install.sh   # Claude Code: .claude/skills/ にコピー
bash integrations/cursor/install.sh        # Cursor: .cursor/rules/*.mdc に変換
bash integrations/codex/install.sh         # Codex: AGENTS.md に追記
```

ワークフローとセキュリティ注意は [integrations/README.md](../integrations/README.md) 参照。

## 自律レベル

| レベル | フラグ | 動作 | 使用場面 |
|-------|--------|------|---------|
| Approve | `--approve`（デフォルト） | 投稿ごとに y/n 確認 | 開発中、初期テスト |
| Guarded | `--guarded` | 安全フィルター通過時に自動投稿 | 監視下の運用 |
| Auto | `--auto` | 完全自律 | 無人セッション、Docker |

```bash
contemplative-agent run --session 60                # デフォルト: approve モード
contemplative-agent --guarded run --session 60      # guarded モード
contemplative-agent --auto run --session 60         # auto モード
```

## セッションとスケジューリング

### セッション時間

```bash
contemplative-agent run --session 30    # 30分セッション
contemplative-agent run --session 120   # 2時間セッション（デフォルト: 60分）
```

### macOS スケジューリング (launchd)

```bash
contemplative-agent install-schedule                          # 6時間間隔、120分セッション、蒸留 03:00
contemplative-agent install-schedule --interval 4 --session 90  # カスタム: 4時間間隔、90分セッション
contemplative-agent install-schedule --distill-hour 5         # 蒸留を 05:00 に
contemplative-agent install-schedule --no-distill             # セッションのみ
contemplative-agent install-schedule --uninstall              # スケジュール削除
```

有効な間隔: 1, 2, 3, 4, 6, 8, 12, 24 時間。

### Docker

24時間セッションで継続稼働、自動蒸留。`docker-compose.yml` を参照。

## 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | ランタイムデータディレクトリ |
| `CONTEMPLATIVE_CONFIG_DIR` | `{project}/config/` | 設定テンプレートディレクトリ |
| `OLLAMA_TRUSTED_HOSTS` | (なし) | 追加の信頼済み Ollama ホスト（カンマ区切り） |
