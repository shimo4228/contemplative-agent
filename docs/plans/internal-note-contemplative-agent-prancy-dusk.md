# Plan: skill-selection shadow instrument (feat)

## Context

19 skill の全文 system prompt 注入が ≈20.3K tok = NUM_CTX 32768 の 62% を占め、2026-07-09 には 13-skill 一括採用が C2 予算ガードを超えて self-post を抑止する実害が出た。stocktake（corpus 衛生）は実施済みで効果薄（19→18 相当）。ADR-0036 は embedding router を「similarity ≠ applicability」で棄却済みだが、corpus 実観察により skill のトリガー条件は意味的（状況の構造）で typed metadata でも表現できないことが確定 — applicability 判断は LLM に返すのが mechanism-vs-value-split 上の正解。

そこで **pass-1 LLM 選択（状況 + 全 skill の name+description → 適用 skill を選択）を shadow mode で導入**する。注入は当面変更せず、選択結果を監査ログに記録し、2-4 週の観察（幻覚率・per-skill 頻度・would-be token 削減分布）後に enforcement を判断する。計器→介入の順序（ADR-0071）であり、ADR-0023 router の敗因（配線未完・観察不能・stochastic read-path の無検証投入）への直接の答え。

**スコープ外（ユーザー決定 2026-07-10）**: internal-note の生成時注入は見送り。ADR-0058 の立場（note は記録物であって次アクションの条件付けではない）を維持する。

## 新規ファイル

| ファイル | 責務 |
|---|---|
| `src/contemplative_agent/core/skill_selection.py` | 機能の単一正本: カタログ読み込み・選択呼び出し・パース・監査書き込み・集約読み値。core のみ import（`_io`, `llm`, `insight.skill_theme`, `prompts`, `text_utils`）。adapter は import しない |
| `config/prompts/skill_selection.md` | 選択プロンプト。プレースホルダ `{skill_catalog}`（`name — description` 行列挙）+ `{situation}`。system 用 md は作らない（`get_identity_system_prompt()` を使う） |
| `tests/test_skill_selection.py` | ユニットテスト正本 |
| `docs/adr/0076-skill-selection-shadow-instrument.md` + `.ja.md` | 新 ADR（二言語慣例） |

## 変更ファイル

- `core/domain.py` — `PromptTemplates` に `skill_selection: str = ""`、`load_prompt_templates` に `read("skill_selection.md", required=False)`
- `core/prompts.py` — `_ATTR_MAP` に `"SKILL_SELECTION_PROMPT": "skill_selection"`
- `adapters/moltbook/llm_functions.py` — `generate_comment` / `generate_reply` / `generate_cooperation_post` の `generate_for_api` 直前に `shadow_observe_skill_selection(...)` フック（各 1 行）。**post_title は対象外**（cooperation_post と同一 run・同一 seeds で情報増分なし。ADR に 1 行明記）
- `cli.py` — (1) セッション setup（cli.py:790 の `configure_llm(skills_dir=SKILLS_DIR)` 隣）に `configure_skill_selection(skills_dir=SKILLS_DIR, audit_dir=...)`。(2) `report --skill-selection` フラグ（`--patterns` cli.py:2611 と同形、try/except + WARNING degrade）
- `docs/CONFIGURATION.md:257` — 「34 loaded prompt templates」→ 35（`tests/test_packaged_assets.py:61-77` が実数照合）
- Doc Sync 同 PR: CODEMAPS architecture.md Data Flow（鮮度規約）+ graph.jsonld（新 ADR ノード）

## 主要シグネチャ

```python
@dataclass(frozen=True)
class SkillCatalogEntry:
    name: str
    description: str
    body_tokens: int  # _estimate_tokens(全文) — would-be 削減計算用

def load_skill_catalog(skills_dir: Optional[Path]) -> tuple[SkillCatalogEntry, ...]:
    # insight.skill_theme + _load_known_themes の glob/dotfile-skip/OSError-WARNING パターン再利用

@dataclass(frozen=True)
class SkillSelectionResult:
    verdict: str                     # "judged" | "fail_open_llm" | "fail_open_parse" | "empty_catalog"
    selected: tuple[str, ...]        # カタログ照合済み実在名のみ、sorted
    rejected_names: tuple[str, ...]  # 幻覚名
    prompt: str
    raw_output: Optional[str]

def select_applicable_skills(situation, catalog) -> SkillSelectionResult:
    # generate(prompt, system=get_identity_system_prompt(),
    #          caller="core.skill_selection", think=False)
    # audit H5 と同じ理由で学習 corpus は選択者に見せない

def configure_skill_selection(skills_dir=None, audit_dir=None) -> None: ...
def reset_skill_selection() -> None: ...
    # configure_llm と同じ module-global パターン。audit_dir 未設定 = shadow 無効

def shadow_observe_skill_selection(situation: str, *, generation_caller: str) -> None:
    # 全体 try/except → logger.warning（degrade-never-abort、生成は絶対止めない）
    # empty catalog / template 未ロード時は LLM を呼ばず verdict="empty_catalog"

@dataclass(frozen=True)
class SkillSelectionReading:  # 計器（ADR-0071 型、read-only）
    days: int; records: int
    verdicts: tuple[tuple[str, int], ...]
    per_skill: tuple[tuple[str, int], ...]   # 選択頻度降順
    never_selected: tuple[str, ...]          # 現カタログにあり選択 0
    selected_count_p50: float; selected_count_p90: float
    token_reduction_p50: float; token_reduction_p90: float

def read_skill_selection_log(log_dir, *, days, skills_dir) -> SkillSelectionReading
def format_skill_selection_report(reading) -> str
```

パース規約: 行分割 → strip → カタログ名と exact match（case-insensitive）。`none` センチネル = 適用なし（judged）。空白のみ → `fail_open_parse`。**全行幻覚でも verdict は `judged`**（selected=() + rejected 全記録 — パース失敗と全部間違いは別事象）。選択数に numeric cap を設けない（feedback 規約）。

## 監査レコード（logs/skill-selection-YYYY-MM-DD.jsonl）

日次ローテは `_emit_telemetry`（core/llm.py:768-782）方式、書き込みは `append_jsonl_restricted`（0600）。

```jsonc
{
  "ts": "...",                              // now_iso("seconds")
  "generation_caller": "moltbook.comment",  // 3 値
  "verdict": "judged",
  "catalog_count": 19,
  "catalog_names": [...],                   // sorted — カタログ変遷後もリプレイ可能
  "selected": [...], "selected_count": 3,
  "rejected_names": [...],
  "full_skill_tokens": 20300,               // record 時点で焼き込み（corpus 変遷でリプレイ不能になるのを防ぐ）
  "would_be_skill_tokens": 3100,
  // _b64_fields パターン（insight.py:408-419 と同型）:
  "prompt_sha256": "...", "prompt_encoding": "base64:utf-8", "prompt_b64": "...",
  "prompt_bytes": 0, "prompt_truncated": false,
  "output_sha256": "...", "output_b64": "...", "output_bytes": 0, "output_truncated": false
}
```

`_MAX_SKILL_SELECTION_AUDIT_BYTES = 65536`（module-local 定数 + docstring。per-action cadence なので novelty の半分に絞る）。

## テスト計画（TDD 順、patch は使用モジュール側）

1. カタログ: frontmatter 付き .md ×3 + dotfile skip + unreadable → WARNING skip
2. 選択パース（`core.skill_selection.generate` を patch）: 実在名/幻覚名混在・`none`・generate→None→fail_open_llm・空白→fail_open_parse・全行幻覚→judged・case-insensitive
3. 監査書き込み: tmp_path JSONL 全フィールド検証 + b64 round-trip + truncated（tests/test_insight.py:724-800 TestNoveltyGateAudit が正本）
4. degrade-never-abort: append raise / generate raise → WARNING のみ。audit_dir 未設定 → generate call_count==0
5. empty_catalog: LLM 呼ばずレコードのみ
6. 計器: 合成 JSONL → 頻度/never_selected/パーセンタイル/壊れ行 skip（tests/test_llm.py:907-971 粒度）
7. adapter フック（patch: `adapters.moltbook.llm_functions.shadow_observe_skill_selection`）: 3 関数が generation_caller 込みで 1 回呼ぶ、post_title は呼ばない
8. CLI: `report --skill-selection` 出力 + 読み込み失敗時も report 本体が生きる
9. packaged assets: CONFIGURATION.md 34→35 を先にレッドで確認してから更新

## ADR-0076 骨子

- **Context**: 62% 圧迫 + 2026-07-09 実害。ADR-0036 の扉。corpus 実観察（トリガーは意味的 → typed metadata 不能）を evidence 化
- **Decision**: shadow mode の pass-1 LLM 選択。identity prompt + think-OFF。幻覚名拒否記録。fail-open。`report --skill-selection`
- **Alternatives**: embedding router（0036 棄却）/ 即 enforcement（ベースラインなしの one-way door）/ typed trigger metadata（実証済み不能）/ core hook（境界違反）
- **Consequences**: +1 LLM call/action（記録で定量化）。never-selected は stocktake 入力にもなる。観察計画: 2-4 週後に verdict 分布・幻覚率・削減分布レビュー。enforcement 判断基準は予約のみ（shadow データが決める）

## 実装順序

1. `config/prompts/skill_selection.md` 起草 + domain/prompts 登録 + CONFIGURATION.md 35（packaged assets green 確認）
2. **プロンプトを gemma4:e4b 自身に改訂させる**（feedback: prompt-model-match。実カタログ 19 件を渡して revise）
3. テスト 1-2 → コア実装（カタログ + 選択）
4. テスト 3-5 → 監査 + degrade 実装
5. テスト 7 → adapter フック + cli configure 配線
6. テスト 6, 8 → 計器 + report フラグ
7. ADR-0076（en/ja）+ CODEMAPS Data Flow + graph.jsonld

## Review / Verify chain（planning.md 準拠）

```
Parallel Group: [python-reviewer, security-reviewer, codex-review]
  （security 対象: untrusted situation テキストの選択プロンプト混入面 + 監査ログ格納）
Sequential: Doc Sync 確認 → Verify（build / pyright / ruff / pytest coverage≥80% /
  secret scan / doc sync / git status）→ 全 PASS でコミット可（main 直 push 運用）
```

## Verification（end-to-end）

1. `uv run pytest tests/test_skill_selection.py tests/test_packaged_assets.py -v` + 全体回帰
2. 手動 smoke: `MOLTBOOK_HOME` を試験ディレクトリにして 1 comment 経路を流し、`logs/skill-selection-*.jsonl` にレコード 1 件（verdict/selected/b64 round-trip）を確認 — ただし smoke 1 回で「機能した」と主張しない（feedback: one-run-not-evidence）
3. `contemplative-agent generate-report --skill-selection` で計器出力を確認
4. スケジュールセッション（JST 0/6/12/18 時）と重ねない時間帯で実行（16GB Metal OOM 実績）

## リスク / Open questions

- **+1 LLM call/action の遅延**: 記録される数値で費用対効果ごと観察。`configure_skill_selection` を呼ばなければ無効（kill switch 内蔵）
- **situation の粒度**: cooperation_post は feed_seeds 連結が最大 15K chars — 選択用に絞る余地は open question として ADR に記録（絞ると選択時と生成時で見ている状況がずれるトレードオフ）
- **enforcement 設計はスコープ外**: shadow の読み値が決める
