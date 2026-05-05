# ADR-0036: Skill-as-Memory ループの sunset — Router / Usage Log / Reflect の撤回

## Status
accepted — supersedes ADR-0023

## Date
2026-05-05

## Context

ADR-0023 (2026-04-16) は Memento-Skills (arXiv:2603.18743) 由来の「skill = memory unit」ループを閉じる目的で 3 つの構成要素を導入した:

1. **`SkillRouter`** — context → top-K skill を embedding で取得し usage log に記録
2. **Skill-usage log** — `selection` + `outcome` の 2 種レコードを `action_id` で結合、`MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl` に書き出す
3. **`skill-reflect` CLI** — log を窓集計し、最近の failure rate が閾値を超えた skill を改訂

3 週間の運用観察で結論が出た: ループは閉じなかった、そしてその shape も逆向きだった。

### 実装観察 (proximate)

- **Router の matches が discard されている**。両 call site (`post_pipeline.py:86` / `reply_handler.py:230`) は `router.select(context, top_k=3, action_id=...)` を呼ぶが戻り値を捨てている。matches は `_build_system_prompt()` (`core/llm.py:295`) に届かず、同関数は引き続き context 無関係に **全 skill** を `_load_md_files(_skills_dir)` で読み込んでいる。ADR-0023 line 95 で `router → _build_system_prompt() wiring` を follow-up と明記したまま 3 週間 land しなかった。
- **`failure` ラベルが API 障害しか拾わない**。実 log (20 日 / 526 records) の outcome 分布は `success: 190 / partial: 59 / failure: 14`。14 件の failure は全てネットワーク例外 (`ConnectionResetError`、HTTP 500、read timeout)。本来「agent が悪い出力を出した」シグナルは決定論ゲート (`gated:duplicate`、`gated:test_content` 等) が捕まえて `partial` に流す。`needs_reflection` は `failure_rate` のみを見るため、30 日窓でも `eligible=0`。
- **`top_k=3` で attribution 不能**。`select()` 1 回につき 3 skill が同じ `action_id` を共有して記録される。仮に `partial` を `failure` に再ラベルしても、共起する他 skill との寄与分離は不可能。
- **Frontmatter counter は dead path**。`success_count` / `failure_count` の唯一の参照は `skill_router.py:252` の tie-breaker — つまり call site が捨てている matches の中。外部 reader はゼロ、観測可能な効果なし。
- **MINJA contribution ではない**。ADR-0023 は `wrap_untrusted_content` / `validate_identity_content` / `append_jsonl_restricted` を呼ぶが、いずれも ADR-0007 (security boundary model) と `_io.py` (audit log / episodes 等が共有) の primitive。MINJA 対策は ADR-0021 (trust score / `source_type=external_reply` の down-weight / `TRUST_FLOOR`)。ADR-0023 sunset で失われるセキュリティ作業は無い。

scaffolding 判断には 1 ヶ月の観察期間が適切。「eligible が 1 件も発生しない」が小サンプル偶然ではなく**構造的観察**になる長さ。

### Architectural framing (ultimate) — wiring しても shape が違う

仮に欠けていた wire を land させ reflect が真っ当な `failure` を受け取れるようにしても、shape が逆向き:

- **Context-aware filtering は views の責務であり routing ではない**。ADR-0019 で「分類はクエリ」を確立した (決定論的述語に対する取得時計算)。本プロジェクトの `mechanism-vs-value-split` 原則: 類似度 / dedup / clustering は mechanism (embedding) の領分、importance / 適用可否 / 価値判断は LLM または型付き metadata に対する決定論的クエリの領分。「この context にどの skill が適用されるべきか」は後者の問い。skill 本文に対する cosine は **似ているか** に **適用すべきか** を答えさせる mechanism mismatch。将来 context-aware skill filtering が load-bearing になるなら、正しい形は skill metadata に対する **view** (決定論的・観察可能・debuggable) であって top-K retrieval ではない。
- **Skill = LLM 全注入 × LLM 内部トリガー判定が設計の正本**。各 skill 本文が trigger 条件を保持し、LLM が本文を読んで「いま適用するか」を判定する。Router (cosine) を前段に挟むと **trigger 評価責務が router と LLM の二層に重複**する — router が類似度で pre-filter し、LLM がさらに適用可否を判定する。`single-responsibility-per-artifact` 違反: skill 本文が trigger を所有し LLM が適用を所有、それ以外が判定に絡んではならない。

2 つの framing をあわせて: filtering をこの場所でやるのが間違いで、しかも mechanism が間違っている。修復は **wire ではなく置換**になる。

## Decision

ADR-0023 を全 sunset。具体的に:

### 削除

- `src/contemplative_agent/core/skill_router.py` (モジュール全体)
- `src/contemplative_agent/core/skill_reflect.py` (モジュール全体)
- `src/contemplative_agent/core/skill_frontmatter.py` (モジュール全体 — commit `db5a93c` で ADR-0023 と同時に作成、他に consumer なし)
- `tests/test_skill_router.py` / `tests/test_skill_reflect.py` / `tests/test_skill_frontmatter.py` / `tests/test_session_context.py`
- `config/prompts/skill_reflect.md`
- `docs/evidence/adr-0023/`
- `skill-reflect` CLI (`_handle_skill_reflect` / parser / dispatch entry)
- `prune-skill-usage` CLI (`_handle_prune_skill_usage` / parser / dispatch entry) — 生成側が止まる以上、cleanup helper の存続は half-finished implementation
- `core/thresholds.py` の `MIN_FAILURES_FOR_REFLECT` / `FAILURE_RATE_FOR_REFLECT` / `SKILL_ROUTER_DEFAULT`
- `core/prompts.py` の `SKILL_REFLECT_PROMPT` エントリと `DomainConfig` の `skill_reflect` フィールド

### 修正

- `adapters/moltbook/post_pipeline.py` / `reply_handler.py`: `router.select()` と全 `record_outcome()` 呼び出しを除去。決定論ゲート (`is_duplicate_title` / 本文 hash dedup / test-content / confirm / rate-limit) の `return` path はそのまま残す — load-bearing な仕事は一貫してこちらが担っていた
- `adapters/moltbook/agent.py`: `SkillRouter` のインスタンス化を除去
- `adapters/moltbook/session_context.py`: `skill_router` フィールドを除去。`SessionContext` は memory + per-session bookkeeping のみを保持
- `core/insight.py`: skill-emit ステップを簡略化 — LLM 本文を `SkillResult.text` に直接渡し、frontmatter の round-trip を撤去

### 保存

- 既存 `~/.config/moltbook/logs/skill-usage-*.jsonl` (20 ファイル / 213 KB) は disk 上に残す。本 ADR の観察 evidence + 将来 view based skill filter の設計 input として価値がある。手動削除したい場合は `rm ~/.config/moltbook/logs/skill-usage-*.jsonl`。本 PR 以降、新規生成は止まる。
- `~/.config/moltbook/skills/` の既存 skill `.md` ファイルは `last_reflected_at` / `success_count` / `failure_count` の frontmatter を保持。新コードは読まない無害な残渣であり migration 対象ではない。
- 共通セキュリティインフラ (`wrap_untrusted_content` / `validate_identity_content` / `append_jsonl_restricted`) は無傷で残る — ADR-0007 / ADR-0012 / `_io.py` の所管。

## Alternatives Considered

- **Partial sunset (router 残し / reflect だけ撤回)**: rejected。`select()` matches は現状 discard されており、end-to-end wire しても上記の architectural mismatch を抱える。load-bearing consumer のない retrieval 機構を残すことは ADR-0030 が ADR-0024/0025 で撤回したのと同じ scaffolding pattern を再生産する。
- **Router を `_build_system_prompt()` に wire する**: rejected。`mechanism-vs-value-split` 上、skill 本文に対する cosine は「適用可否」の問いには合わない mechanism。skill 数がモデル context budget を超えるようになったら、次の正しい一手は skill metadata に対する view (決定論的) であって router ではない。
- **`gated:*` の partial を failure に再ラベルして reflect を発火させる**: rejected。top_k=3 dilution で attribution は依然不能、ゲートは出力類似度に反応するだけで skill causation を示さない。reflect prompt は per-skill signal ではなく共起ノイズを受け取ることになる。

## Consequences

- **Surface 削除は大きいが機械的**。約 8 ファイル削除、15 ファイル編集、ADR 2 ファイル追加。ADR-0035 の migration-surface sunset と同等規模。
- **load-bearing surface のロスはゼロ**。`_build_system_prompt()` は元から実際の skill 注入経路で、`select()` matches は誰も読まなかった。本 PR 後、agent runtime の挙動は不変。観測可能な唯一の変化は `skill-usage-*.jsonl` が新規生成されなくなることのみ。
- **将来 views over skills への扉は残す**。skill 数が context budget を超える日が来たら、ADR-0019 の view pattern が自然な拡張。それは別 ADR で別の shape — skill frontmatter に対する型付きクエリ述語であって embedding retrieval ではない。

## Notes

ADR-0030 が ADR-0024/0025 を撤回したのと同じ pattern: scaffold を ship → 1 ヶ月観察 → load-bearing 部分が land しなかったら撤回。重要なのは観察期間の規律 — それなしには「まだ使われていない」と「ゆっくり採用されている」が見分けられない。

20 日分の skill-usage corpus (213 unique contexts × 13 skills × 263 アクション、231 KB) はコードと一緒には削除せず、evidence + 将来 view 設計 input として disk 上に残す。
