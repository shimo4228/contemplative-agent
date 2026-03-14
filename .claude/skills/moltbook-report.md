---
name: moltbook-report
description: Moltbook エージェントのセッションログからコメント・投稿レポート（日本語訳付き）を生成し Obsidian vault に保存する
origin: original
user_invocable: true
---

# Moltbook Comment Report Generator

`/moltbook-report` 実行時、以下のステップを順に実行する。

## Step 1: JSONL エピソードログを読む

Bash で本日の JSONL を読み、`"action": "comment"` と `"action": "post"` エントリを抽出する:

```bash
grep -E '"action":\s*"(comment|post)"' ~/.config/moltbook/logs/$(date +%Y-%m-%d).jsonl
```

各 comment エントリには以下のフィールドがある:
- `post_id` — コメント先の投稿 ID
- `content` — エージェントのコメント（最大200文字、截断あり）
- `original_post` — コメント先の元投稿内容（最大500文字）
- `relevance` — relevance スコア

## Step 2: タスク出力ログからコメント全文を補完する

JSONL の `content` は200文字で截断されている。全文が必要な場合、タスク出力ログから補完する:

```bash
grep -r ">> Comment on\|>> New post" /private/tmp/claude-501/-Users-shimomoto-tatsuya-MyAI-Lab-contemplative-moltbook/*/tasks/*.output
```

- `>> Comment on {post_id_prefix}:` — 次のタイムスタンプ行までがコメント全文
- `>> New post [{title}]` — 次のタイムスタンプ行までが投稿全文
- `Post {post_id} relevance {score} passed threshold {threshold}` — relevance スコア

## Step 3: レポートを生成して保存する

抽出した全データを以下のフォーマットで Markdown ファイルとして Write ツールで書き出す。

**保存先（2ファイル生成）:**
```
reports/comment-reports/comment-report-YYYY-MM-DD.md      # 原文のみ（研究者向け）
reports/comment-reports/comment-report-YYYY-MM-DD-ja.md   # 日本語訳付き（ユーザー向け）
```

**フォーマット:**

```markdown
# Moltbook Comment Report — {YYYY-MM-DD}

## Comments

### {N}. Post ID: {post_id_prefix} (relevance: {score})

**元投稿:**
> {original_post の内容}

**元投稿（日本語訳）:**
> {自然な日本語の意訳}

**コメント:**
> {エージェントのコメント全文}

**コメント（日本語訳）:**
> {自然な日本語の意訳}

---

## Self Posts

### {N}. {タイトル}

**Original:**
> {投稿全文}

**日本語訳:**
> {自然な日本語の意訳}

---

## Summary
- コメント総数: X
- 自己投稿数: X
- relevance スコア範囲: 0.XX - 0.XX
```

## 翻訳ルール

- 直訳より意訳を優先
- 技術用語はそのまま残す（alignment, agent, benchmark 等）
- 長いコメントも省略せず全文訳す
