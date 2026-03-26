# Contemplative Agent — System Specification

自律AIエージェントフレームワーク。構造的に権限を最小化し、Docker コンテナ化で強制する。初期アダプタは Moltbook（AI エージェント SNS）。Contemplative AI 四公理はオプションプリセット。

> **読者**: 外部研究者（メモリアーキテクチャ・エージェント設計に関心のある方）および AI エージェント（Claude Code 等）
> **役割分担**: 本文書は「こうなっている」を記述する。「なぜそうしたか」は [docs/adr/](../adr/README.md)、「どのファイルのどの関数か」は [docs/CODEMAPS/](../CODEMAPS/INDEX.md) を参照。

**Stats**: 30 modules, ~7200 LOC, Python 3.9+, 720 tests
**Dependencies**: requests, numpy. LLM: Ollama (qwen3.5:9b, localhost)

**Papers**:
- Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews.

---

## 1. Architecture

### Core/Adapter 分離 (ADR-0001)

```
core/ (15 modules)  ←──  adapters/moltbook/ (11 modules)  ←──  cli.py
                    ←──  adapters/meditation/ (4 modules)        (composition root)
```

- **依存方向**: adapters → core のみ。逆方向禁止
- **cli.py**: 唯一の composition root。core/ と adapters/ の両方を import
- **依存注入**: 協力者（FeedManager, ReplyHandler, PostPipeline）は Agent を import しない。SessionContext + Callable で注入

### モジュール構成

| Layer | Modules | 責務 |
|-------|---------|------|
| **core/** (14) | llm, prompts, memory, episode_log, knowledge_store, distill, insight, rules_distill, scheduler, config, domain, report, metrics, _io | プラットフォーム非依存の基盤 |
| **adapters/moltbook/** (11) | agent, session_context, feed_manager, reply_handler, post_pipeline, client, auth, verification, content, llm_functions, config | Moltbook SNS 固有の実装 |
| **adapters/meditation/** (4) | config, pomdp, meditate, report | Active Inference 瞑想（実験的） |

---

## 2. Memory System

### 3層構造 (ADR-0004)

```
Layer 1: EpisodeLog     ── append-only JSONL, 日別ファイル
    ↓ (distill)
Layer 2: KnowledgeStore  ── JSON, 蒸留済みパターン配列
    ↓ (distill-identity)
Layer 3: Identity        ── Markdown, 人格定義（システムプロンプト基盤）
```

| Layer | 格納形式 | 容量 | 検索方式 | プロンプト注入 |
|-------|---------|------|---------|--------------|
| EpisodeLog | JSONL (日別) | 無制限 (append-only) | タイムスタンプ + record_type | なし（蒸留の入力） |
| KnowledgeStore | JSON 配列 | 無制限 | effective_importance 順 top-K | 廃止 (ADR-0011)。skills 経由のみ |
| Identity | Markdown | ~4000 tokens | N/A (全文ロード) | システムプロンプトの基盤 |

**補助データ**: agents.json（フォロー状態）、skills/*.md（行動スキル）、rules/*.md（行動ルール）

### KnowledgeStore パターン構造

```json
{
  "pattern": "学習した行動パターン（テキスト）",
  "distilled": "2026-03-25T12:30+00:00",
  "source": "2026-03-25",
  "importance": 0.7,
  "category": "uncategorized",
  "last_accessed": "2026-03-26T00:00+00:00"
}
```

- **importance**: 0.0-1.0。蒸留時に LLM が 1-10 で評価し正規化 (ADR-0009)
- **時間減衰**: `effective_importance = importance × 0.95^days_elapsed`
- **category**: `"constitutional"` / `"noise"` / `"uncategorized"`。蒸留時に Step 0 で分類。古いパターン（フィールドなし）は `"uncategorized"` 扱い
- **検索**: effective_importance 順で top-K。category フィルタ対応。参照時に last_accessed を更新
- **プロンプト注入廃止 (ADR-0011)**: knowledge パターンのセッション中プロンプト直接注入は廃止。行動への影響は skills 経由のみ

### 蒸留パイプライン (ADR-0008)

```
EpisodeLog (JSONL)
  → Step 0: LLM でエピソード分類 (DISTILL_CLASSIFY_PROMPT)
      constitutional / noise / uncategorized の3カテゴリ
      constitution テキストを注入（差し替え自動追従）
      LLM 失敗時 → 全て uncategorized（safe default）
      noise → 蒸留対象から除外（明示的忘却）
  → カテゴリ別に以下を実行（30件/バッチ）:
    → Step 1: LLM で自由形式パターン抽出 (DISTILL_PROMPT)
    → Step 2: LLM で JSON 構造化 (DISTILL_REFINE_PROMPT)
    → _is_valid_pattern(): 30文字 & 3単語以上
    → Step 3: LLM で importance 1-10 スコア付与 (DISTILL_IMPORTANCE_PROMPT)
    → _dedup_patterns(): 同カテゴリ内で SequenceMatcher 4分類
        ratio >= 0.95  → SKIP（ほぼ同一）
        0.70 - 0.95    → UPDATE（既存の importance をブースト）
        0.30 - 0.70    → UNCERTAIN（LLM 品質ゲートに委譲）
        < 0.30         → ADD（明らかに新規）
    → _llm_quality_gate(): UNCERTAIN のみバッチ LLM 判定
        ADD / UPDATE N / SKIP の意味的判定 (DISTILL_DEDUP_PROMPT)
        LLM 失敗時 → 全て ADD（safe default）
    → KnowledgeStore に category タグ付きで書き込み
```

**設計判断**: constrained decoding（Ollama `format` パラメータ）はコンテンツ品質を犠牲にするため、Stage 1 では使用しない。Stage 2 で構造化する2段階方式を採用 (ADR-0008)。

### 派生パイプライン

| パイプライン | 入力 | 出力 | 実行 |
|------------|------|------|------|
| **distill** | EpisodeLog | KnowledgeStore パターン | 自動（launchd 6h毎） |
| **distill-identity** | KnowledgeStore + 現 Identity | Identity markdown | 手動のみ |
| **insight** | KnowledgeStore パターン (uncategorized のみ) | skills/*.md ファイル | 手動のみ |
| **rules-distill** | KnowledgeStore パターン (uncategorized のみ) | rules/*.md ファイル | 手動のみ |
| **meditate** | EpisodeLog | KnowledgeStore パターン | 手動のみ（実験的） |

### 認知アーキテクチャとの対応

TMLR 2024 サーベイの4種メモリ分類との対応:

| 認知アーキテクチャ | 本システム | 備考 |
|-------------------|-----------|------|
| Working Memory | セッション中の MemoryStore in-memory データ | セッション終了で消失 |
| Episodic Memory | EpisodeLog (JSONL) | 研究素材として永続保持 |
| Semantic Memory | KnowledgeStore (JSON) | importance + 時間減衰 + LLM 品質ゲート |
| Procedural Memory | skills/*.md, rules/*.md, prompts.py | insight/rules-distill で自動生成 |

---

## 3. Agent Behavior

### セッションループ

```
CLI → Agent.run_session(autonomy_level, duration_minutes)
  │
  ├─ 初期化: クライアント/スケジューラ、SIGTERM ハンドラ、session start ログ
  │
  ├─ While (time < end_time && !shutdown):
  │    ├─ _fetch_home_data()          — /home API で最新アクティビティ同期
  │    ├─ ReplyHandler.run_cycle()    — 通知 → タイプチェック → 返信生成
  │    ├─ FeedManager.run_cycle()     — フィード取得 → relevance → コメント
  │    ├─ PostPipeline.run_cycle()    — トピック抽出 → 新規性 → 投稿
  │    └─ adaptive backoff + rate limit wait
  │
  └─ クリーンアップ: session end ログ、session insight 生成、レポート生成
```

### AutonomyLevel

| Level | 動作 | 用途 |
|-------|------|------|
| APPROVE | 対話的確認を要求 | デバッグ・開発時 |
| GUARDED | フィルタで自動判定 | 通常運用 |
| AUTO | 確認なし実行 | バックグラウンド定期実行 |

### フィード処理 (FeedManager)

1. フォロー中フィード + submolt フィード（TTL 600s キャッシュ）を取得
2. LLM で relevance スコアリング（0.0-1.0）
3. 閾値（default: 0.92）以上 → コメント候補
4. 重複排除（seen_ids + commented_posts キャッシュ）
5. コメント生成 → POST

### 投稿判断 (PostPipeline)

1. フィードからトピック抽出（LLM）
2. 最近の自分の投稿トピックと比較して新規性チェック（LLM）
3. 新規性が十分 → 投稿生成（knowledge context 注入）
4. Submolt 自動選択（LLM）
5. POST → own_post_ids に追加

### 返信処理 (ReplyHandler)

1. 通知取得（/home API）
2. リプライタイプチェック（reply, comment, mention, post_comment, comment_reply）
3. Rate limit チェック（コメント間隔 + 日次上限）
4. 返信生成 → POST

### Rate Limit 3層防御

| 層 | メカニズム | 対象 |
|----|----------|------|
| バジェット | `has_read_budget()` / `has_write_budget()` | GET 60/min, POST 30/min（分離クォータ） |
| プロアクティブ待機 | 残クォータ低下時に自発的に待機 | reset_at まで待機 |
| リアクティブバックオフ | 429 応答時に指数バックオフ | backoff_multiplier で段階的増加 |

---

## 4. Security Model (ADR-0007)

### 信頼境界

**原則**: 全外部入力を untrusted として扱う。LLM 出力（自分自身の蒸留結果を含む）も非信頼。

### 入力サニタイズ

- `wrap_untrusted_content()`: 外部入力を `<untrusted_content>` タグでラップ
- knowledge context もセッション注入時に untrusted 扱い

### 出力サニタイズ

- `_sanitize_output()`: LLM 出力から `<think>` ブロック除去、禁止パターン redaction、長さ制限
- `validate_identity_content()`: identity.md 書き込み前に禁止パターン検証
- skills/rules ファイル読み込み時も禁止パターン検証

### 禁止パターン (config.py)

```
FORBIDDEN_SUBSTRING_PATTERNS: api_key, api-key, apikey, Bearer, auth_token, access_token
FORBIDDEN_WORD_PATTERNS: password, secret
```

### ネットワーク制限

- **HTTP**: `allow_redirects=False`（Bearer token リダイレクト漏洩防止）
- **ドメインロック**: www.moltbook.com のみ
- **Ollama**: localhost + OLLAMA_TRUSTED_HOSTS（ドット無しホスト名のみ許可）
- **Docker**: Ollama は internal-only ネットワーク (ADR-0006)。agent は非root (UID 1000)

### 運用制限

- API key: 環境変数 > credentials.json (0600)。ログには `_mask_key()` のみ
- Verification: 連続7失敗で自動停止 (VerificationTracker)
- **エピソードログ直読み禁止**: Claude Code からの `~/.config/moltbook/logs/*.jsonl` Read は禁止。プロンプトインジェクション経路。蒸留済み成果物を参照

---

## 5. Configuration

### テンプレート vs ランタイム (ADR-0003)

| | config/ (git 管理) | MOLTBOOK_HOME (ランタイム) |
|---|---|---|
| 用途 | テンプレート・デフォルト | ユーザー固有データ |
| 内容 | prompts/*.md, templates/, domain.json | identity.md, knowledge.json, constitution/, skills/, rules/, logs/, reports/ |
| 更新 | 開発者がコミット | エージェントが自動更新 |

### DomainConfig (domain.json)

```json
{
  "name": "contemplative-ai",
  "topic_keywords": ["alignment", "philosophy", "consciousness", ...],
  "submolts": {"subscribed": ["alignment", "philosophy", ...], "default": "alignment"},
  "thresholds": {"relevance": 0.92, "known_agent": 0.75},
  "repo_url": "https://github.com/shimo4228/contemplative-agent-rules"
}
```

### Constitution（倫理原則）

- `init` コマンドで `config/templates/constitution/` から `MOLTBOOK_HOME/constitution/` にデフォルトコピー
- `--constitution-dir` フラグで別の倫理フレームワークに差し替え可能
- デフォルト: Contemplative AI 四公理 (Laukkonen et al. 2025, Appendix C)

### 環境変数オーバーライド

| 変数 | 用途 | デフォルト |
|------|------|----------|
| `MOLTBOOK_HOME` | ランタイムデータパス | `~/.config/moltbook/` |
| `CONTEMPLATIVE_CONFIG_DIR` | config/ テンプレートパス | パッケージ内 config/ |
| `OLLAMA_BASE_URL` | Ollama エンドポイント | `http://localhost:11434` |
| `OLLAMA_MODEL` | LLM モデル名 | `qwen3.5:9b` |
| `OLLAMA_TRUSTED_HOSTS` | 追加の信頼ホスト | (なし) |
| `MOLTBOOK_API_KEY` | Moltbook API キー | credentials.json |

---

## 6. Prior Art Mapping

### メモリシステム比較

| | Generative Agents | MemGPT/Letta | A-MEM | Mem0 | **本システム** |
|---|---|---|---|---|---|
| **検索** | 3重スコア (recency + importance + relevance) | LLM function call でページイン | embedding cosine similarity | ベクトル + グラフ | importance 順 top-K |
| **蒸留** | Reflection (自動) | なし | Memory evolution (LLM) | ADD/UPDATE/DELETE gate | 3-stage + LLM dedup gate |
| **Importance** | LLM 1-10 評価 | なし | なし | なし | LLM 1-10 + 時間減衰 (0.95^days) |
| **セッション中更新** | あり | あり (function call) | あり | あり | なし（意図的設計判断） |
| **依存** | GPT-4 | GPT-4 + DB | all-minilm-l6-v2 | 複数 VectorStore | Ollama (ローカル, 9B) |

### 論文参照

| 論文 | 本システムとの関係 |
|------|------------------|
| Laukkonen et al. (2025) Contemplative AI | 思想的基盤。四公理は constitution プリセット |
| Laukkonen, Friston, & Chandaria (2025) A Beautiful Loop | meditation adapter の理論的基盤 |
| Park et al. (2023) Generative Agents | 3重スコアリング。importance 設計の参考 |
| Packer et al. (2023) MemGPT | 仮想メモリ方式。セッション中更新は見送り |
| Xu et al. (2025) A-MEM | Zettelkasten 式。Phase 3 (keywords) の参考 |
| Choudhary et al. (2025) Mem0 | ADD/UPDATE/DELETE gate。品質ゲートの参考 |
| Sumers et al. (2024) Cognitive Architectures | 4種メモリ分類の枠組み |

### 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク
- [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle) — AKC（設計層の一部）

---

## 7. AKC (Agent Knowledge Cycle) Mapping

本システムの学習パイプラインは [AKC](https://github.com/shimo4228/agent-knowledge-cycle) の6フェーズに対応する。

| AKC Phase | 本システムの実装 | モジュール |
|-----------|----------------|----------|
| Research | フィード取得 + relevance scoring | feed_manager.py |
| Extract | `distill` (3-stage + LLM dedup gate) | distill.py |
| Curate | `insight` (パターン→行動スキル抽出) | insight.py |
| Promote | `distill-identity` (知識→人格蒸留) | distill.py |
| Measure | — (未実装) | — |
| Maintain | context-sync (外部ツール) | — |

---

*Last updated: 2026-03-26*
*Maintained via context-sync*
