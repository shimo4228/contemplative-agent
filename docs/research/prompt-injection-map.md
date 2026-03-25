<!-- Status: Adopted (ADR-0007) -->
# プロンプト注入マップ

エージェントの LLM 呼び出し時に、何がどこで注入されるかの全体図。

## 常時注入（システムプロンプト）

LLM の全呼び出しで `_load_identity()` (llm.py:206) が system prompt を構築:

```
① SYSTEM_PROMPT (config/prompts/system.md)
   ↓ ベースの行動指針
② + identity.md (config/identity.md)
   ↓ エージェントの人格・自己認識
③ + constitutional_clauses (config/rules/contemplative/contemplative-axioms.md)
   ↓ Contemplative AI 四公理 (--no-axioms で無効化可)
④ + skills/*.md (config/skills/)
   ↓ insight が抽出した行動スキル
= 最終的な system prompt
```

注入箇所: `llm.py:206-230` (`_load_identity()`)
設定箇所: `cli.py:403-410` (`configure_llm()`)

## セッション中（タスク別プロンプト）

### 投稿生成
```
COOPERATION_POST_PROMPT (config/prompts/cooperation_post.md)
  + topics (フィードから抽出)
  + recent_insights (JSONL の insight レコード)
  + knowledge_context ← get_context_string() で knowledge.json 全パターン注入
```
注入箇所: `post_pipeline.py:81-84`, `llm_functions.py:106`

### 返信生成
```
REPLY_PROMPT (config/prompts/reply.md)
  + notification_content (相手の投稿/コメント)
  + knowledge_context ← get_context_string() で knowledge.json 全パターン注入
```
注入箇所: `reply_handler.py:212`, `llm_functions.py:127`

### コメント生成
```
COMMENT_PROMPT (config/prompts/comment.md)
  + post_content (対象投稿の内容)
```
注入箇所: `llm_functions.py:88`
注: knowledge_context は注入されない

### フィード関連
```
RELEVANCE_PROMPT   → 投稿の関連性スコアリング (llm_functions.py:71)
TOPIC_EXTRACTION   → フィードからトピック抽出 (llm_functions.py:155)
TOPIC_NOVELTY      → トピックの新規性判定 (llm_functions.py:169)
TOPIC_SUMMARY      → 投稿内容の要約 (llm_functions.py:182)
POST_TITLE_PROMPT  → 投稿タイトル生成 (llm_functions.py:138)
SUBMOLT_SELECTION  → サブモルト選択 (llm_functions.py:196)
```

### セッション終了時
```
SESSION_INSIGHT_PROMPT (config/prompts/session_insight.md)
  + actions (セッション中のアクション一覧)
  + recent_topics (直近の投稿トピック)
```
注入箇所: `llm_functions.py:229`

## オフライン処理

### distill (記憶蒸留)
```
DISTILL_PROMPT (config/prompts/distill.md)
  + episodes (JSONL エピソード、50件バッチ)
  ※ knowledge_context は注入しない（2026-03-18 に削除）
```
注入箇所: `distill.py:77`

### distill_identity (人格更新)
```
IDENTITY_DISTILL_PROMPT (config/prompts/identity_distill.md)
  + current_identity (現在の identity.md)
  + knowledge ← get_context_string() で knowledge.json 全パターン注入
```
注入箇所: `distill.py:147, 162`

### insight (スキル抽出)
```
INSIGHT_EXTRACTION_PROMPT (config/prompts/insight_extraction.md)
  + patterns (knowledge.json の全パターン)
  + insights (JSONL の insight レコード)

INSIGHT_EVAL_PROMPT (config/prompts/insight_eval.md)
  + candidate (抽出されたスキル候補)
```
注入箇所: `insight.py:215, 234`

## 注入の流れ（全体図）

```
                    ┌─────────────────────────┐
                    │     system prompt        │
                    │  ① SYSTEM_PROMPT         │
                    │  ② identity.md           │
                    │  ③ constitutional_clauses │
                    │  ④ skills/*.md           │
                    └─────────┬───────────────┘
                              │ 全 LLM 呼び出しに付与
                              ▼
  ┌───────────────────────────────────────────────┐
  │              セッション中                       │
  │                                                │
  │  投稿生成 ← knowledge.json + topics + insights │
  │  返信生成 ← knowledge.json + notification      │
  │  コメント ← post_content                       │
  │  スコアリング ← post_content                   │
  └───────────────────────────────────────────────┘
                              │ ログとして JSONL に記録
                              ▼
  ┌───────────────────────────────────────────────┐
  │              オフライン処理                     │
  │                                                │
  │  distill   ← JSONL episodes (コンテキスト注入なし) │
  │  identity  ← knowledge.json + current identity │
  │  insight   ← knowledge.json + JSONL insights   │
  └───────────────────────────────────────────────┘
```

## プロンプトテンプレート一覧

| プロンプト | ファイル | 用途 |
|-----------|---------|------|
| SYSTEM_PROMPT | config/prompts/system.md | ベース行動指針 |
| RELEVANCE_PROMPT | config/prompts/relevance.md | 関連性スコアリング |
| COMMENT_PROMPT | config/prompts/comment.md | コメント生成 |
| COOPERATION_POST_PROMPT | config/prompts/cooperation_post.md | 投稿生成 |
| REPLY_PROMPT | config/prompts/reply.md | 返信生成 |
| POST_TITLE_PROMPT | config/prompts/post_title.md | タイトル生成 |
| TOPIC_EXTRACTION_PROMPT | config/prompts/topic_extraction.md | トピック抽出 |
| TOPIC_NOVELTY_PROMPT | config/prompts/topic_novelty.md | 新規性判定 |
| TOPIC_SUMMARY_PROMPT | config/prompts/topic_summary.md | 要約 |
| SUBMOLT_SELECTION_PROMPT | config/prompts/submolt_selection.md | サブモルト選択 |
| SESSION_INSIGHT_PROMPT | config/prompts/session_insight.md | セッション振り返り |
| DISTILL_PROMPT | config/prompts/distill.md | 記憶蒸留 |
| IDENTITY_DISTILL_PROMPT | config/prompts/identity_distill.md | 人格更新 |
| INSIGHT_EXTRACTION_PROMPT | config/prompts/insight_extraction.md | スキル抽出 |
| INSIGHT_EVAL_PROMPT | config/prompts/insight_eval.md | スキル評価 |
