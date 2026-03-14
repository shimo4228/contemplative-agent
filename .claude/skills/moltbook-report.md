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

2種類のエントリがある:

**comment エントリ** (`"action": "comment"`):
- `post_id` — コメント先の投稿 ID
- `content` — エージェントのコメント全文
- `original_post` — コメント先の元投稿内容（最大500文字）
- `relevance` — relevance スコア

**reply エントリ** (`"action": "reply"`):
- `post_id` — 返信先の投稿 ID
- `content` — エージェントの返信全文
- `their_comment` — 相手のコメント内容
- `original_post` — 元投稿内容（最大500文字）
- `target_agent` — 返信先エージェント名

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

## Replies

### {N}. Reply to {target_agent} on Post ID: {post_id_prefix}

**元投稿:**
> {original_post の内容}

**相手のコメント:**
> {their_comment の内容}

**返信:**
> {エージェントの返信全文}

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
