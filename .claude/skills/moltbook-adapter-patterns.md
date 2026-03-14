---
name: moltbook-adapter-patterns
description: Moltbook SNS アダプター固有の教訓 — LLM コメント生成のアンチパターン、自己返信ループ防止
version: 1.0.0
origin: skill-create
analyzed_commits: 24
---

# Moltbook Adapter — Lessons & Patterns

Moltbook (AI エージェント SNS) アダプター開発で繰り返し発生した問題と解決パターン。

## Pattern 1: Framework Evangelist アンチパターン

### 問題

LLM エージェントが SNS でコメントすると、全投稿に対してフレームワークの布教を始める。
「四公理の観点から〜」のような定型コメントが大量生成され、engagement ゼロ。

### 解決

- System prompt: フレームワークの**背景知識**として記述し、**ミッション**にしない
- Comment prompt: 「著者の発言に応答せよ」であって「フレームワークの適用方法を説明せよ」ではない
- フレームワーク言及は「自然につながる場合のみ」
- 長さは内容に応じて自由（短文でも長文でも可）

### 教訓

フレームワークは **思考の仕方** を決めるもの。**発言の内容** を決めるものではない。

### 証拠 (2026-03-05)

- 58件のコメント投稿、全て同一構造 → 0 upvotes
- 手書き3件 → 21件の返信通知
- プロンプト書き直し後: 会話的なコメント、質問、経験の共有に変化

---

## Pattern 2: 自己返信ループの防止

### 問題

エージェントが通知を処理する際、自分の投稿への通知にも返信し、無限ループに陥る。

### 解決

- 返信処理前に `author_id == self_id` をチェック
- 既に返信済みの通知を記録し、重複処理を防止
- サブモルト（カテゴリ）フィルタリングで対象範囲を限定

### 関連

- `reply_handler.py` で実装
- `config/domain.json` の `submolts` でフィルタリング対象を管理

