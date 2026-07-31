# ADR-0007: セキュリティ境界モデル

## Status

accepted

## Date

2026-03-12

## Context

自律エージェントは外部入力（他エージェントの投稿、API レスポンス）と LLM 出力の両方が信頼できない。特にプロンプトインジェクション（外部エージェントの投稿に悪意あるプロンプトが含まれる）と LLM 出力の暴走（禁止パターンの生成）が脅威。

## Decision

信頼境界を3層で防御:

**1. 入力サニタイズ（書き込み時）**

- 全外部入力を `wrap_untrusted_content()` で `<untrusted_content>` タグにラップ
- knowledge context も untrusted としてラップ（自分自身の蒸留出力も信頼しない）

**2. 出力サニタイズ（読み出し時）**

- LLM 出力を `_sanitize_output()` で `FORBIDDEN_SUBSTRING_PATTERNS` 除去（`re.IGNORECASE`）
- identity.md は `_validate_identity_content()` で forbidden pattern 検証

**3. ネットワーク制限**

- HTTP: `allow_redirects=False`（Bearer token 漏洩防止）、ドメインロック（`www.moltbook.com` のみ）
- Ollama: `LOCALHOST_HOSTS` + `OLLAMA_TRUSTED_HOSTS`（ドット無しホスト名のみ）で制限
- Docker: ADR-0006 のネットワーク分離

**4. 設定ファイル検証**

- `domain.json`, `contemplative-axioms.md` ロード時も `FORBIDDEN_SUBSTRING_PATTERNS` 検証
- `OLLAMA_MODEL` はフォーマット検証（`VALID_MODEL_PATTERN`）
- `post_id` は `[A-Za-z0-9_-]+` バリデーション

**5. 運用制限**

- Verification: 連続7失敗で自動停止
- API key: env var > credentials.json (0600)、ログには `_mask_key()` のみ
- Claude Code からのエピソードログ直読み禁止（プロンプトインジェクション経路）

## Alternatives Considered

- **LLM 出力を信頼する**: 小規模モデル（9B）は禁止パターンを守れないことが多く、サニタイズなしは危険
- **ホワイトリスト方式（許可パターンのみ通す）**: 表現の自由度が下がりすぎて投稿品質に影響
- **外部セキュリティスキャナ**: 依存が増える。現時点の規模では内蔵のパターンマッチで十分

## Consequences

- 蓄積データ（knowledge.json, identity.md）は全て untrusted として扱われる
- セキュリティ定数は `core/config.py` に集約（`FORBIDDEN_SUBSTRING_PATTERNS`, `MAX_*_LENGTH`, `VALID_*_PATTERN`）
- 新しい禁止パターン追加は `core/config.py` の定数を更新するだけ
- パフォーマンスへの影響は軽微（正規表現マッチのみ）
