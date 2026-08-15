# D3 — Per-Block Distill Routing 引き継ぎ (2026-04-18)

次セッションで cold start できるように作成。内部 issue tracker `.notes/remaining-issues-2026-04-18.md` §1 (D3) の実装着手用（※ADR-0030 で D3/D4 は撤回済み、本 handoff は退役参照）。

## What is D3

`distill-identity` CLI が `persona_core` block しか refresh できない現状を解消し、`current_goals` などの追加 block も「自身のビュー + 自身のプロンプト」で refresh できるようにする。

ADR-0024/0025 で identity_blocks の multi-block parse/render と per-block history は実装済み。**残ったのは `distill_identity()` 内の dispatch 層**。

## 現状 (2026-04-18 verified)

### 既に動くもの

- `identity_blocks.py` (parse / render / `update_block` / per-block history `append_history`) — multi-block 対応済み
- ADR-0025 per-block ハッシュ記録 — `identity_history.jsonl` で block 単位の差分追跡
- `~/.config/moltbook/views/` に 7 view が配置済み (`self_reflection`, `constitutional`, `communication`, `noise`, `reasoning`, `technical`, `social`)

### 動かないもの (今回スコープ)

- `distill_identity()` (`distill.py:187-302`) は内部で `persona_core` ハードコード:
  - L226: 常に `"self_reflection"` view でパターンマッチング
  - L248: `current_doc.get(identity_blocks.PERSONA_CORE_BLOCK)` で persona_core 限定取得
  - L290-295: `update_block(..., "persona_core", ...)` ハードコード
- prompts は `config/prompts/identity_distill.md` + `identity_refine.md` の 2 本のみ (persona_core 用)
- block ↔ view ↔ prompt のマッピングを保持する config が存在しない
- `~/.config/moltbook/identity.md` 自体がまだ legacy 形式 (frontmatter なし、4 段落のみ。block 分割なし)。migration 必要

## 実装方針 (予備案、要レビュー)

### 案 A: Config-driven dispatch (推奨)

```python
# distill.py 冒頭
@dataclass(frozen=True)
class BlockDistillConfig:
    block_name: str
    view_name: str       # ViewRegistry に存在する view
    prompt_key: str      # prompts.py ATTR_MAP のキー
    refine_prompt_key: str
    enabled: bool

_BLOCK_CONFIG: Dict[str, BlockDistillConfig] = {
    "persona_core": BlockDistillConfig(
        "persona_core", "self_reflection",
        "IDENTITY_DISTILL_PROMPT", "IDENTITY_REFINE_PROMPT",
        enabled=True,
    ),
    "current_goals": BlockDistillConfig(
        "current_goals", "goal_reflection",
        "IDENTITY_GOALS_DISTILL_PROMPT", "IDENTITY_GOALS_REFINE_PROMPT",
        enabled=False,  # view + prompt が揃ったら true
    ),
}

def distill_identity(..., block_name: str = "persona_core"):
    cfg = _BLOCK_CONFIG[block_name]
    if not cfg.enabled:
        raise ValueError(f"block {block_name} not enabled")
    # 既存ロジックを cfg.view_name / cfg.prompt_key で parametrize
```

**利点**: 新 block 追加は config 1 行 + view + prompt 2 本でスケール。dispatch は dict lookup のみで明快。

**代替**:
- 案 B: YAML 外出し (`config/templates/contemplative/identity_blocks_distill.yaml`) — 将来の柔軟性は高いが I/O 増、stocktake 範囲に入りにくい
- 案 C: ハードコード if/elif — 1-2 block ならアリだが先細り

### prompt の出処 (重要)

feedback memory `prompt-model-match` により **per-block prompt は qwen3.5:9b 自身に書かせる**必要。手順:

1. 新 block (例 `current_goals`) を実装する**前に**、qwen3.5:9b に block の目的と入力形式を渡して prompt 草稿を生成させる
2. 草稿を `config/prompts/identity_distill_current_goals.md` に置く (命名規則: `identity_{distill,refine}_{block_name}.md`)
3. `prompts.py` の ATTR_MAP に lazy-load エントリ追加
4. config の `prompt_key` を新エントリに向ける

prompt を Claude / 人手で書くと、生成時に思考空間の不一致で品質劣化するリスクあり (memory `prompt-model-match`)。

## Open Decisions

着手時に決めること:

1. **identity.md migration**: legacy 4 段落 → multi-block 形式への migration script を先に作るか、distill 側で auto-migrate するか
2. **enabled flag の運用**: `current_goals` を最初から enabled にして empty body から育てるか、view + prompt が揃ってから ON にするか
3. **新 view の名称**: `goal_reflection` で良いか、別命名 (`self_goals` など) にするか — ViewRegistry の既存 7 view と命名一貫性を確認
4. **CLI 形態**: `distill-identity --block current_goals` フラグ追加か、全 enabled block を順に refresh するデフォルト挙動か

## Critical Files (cold start 順)

| # | File | 何を見るか |
|---|---|---|
| 1 | `src/contemplative_agent/core/distill.py:187-302` | `distill_identity()` 本体、ハードコード箇所 (L226, L248, L290-295) |
| 2 | `src/contemplative_agent/core/identity_blocks.py` | 既存 multi-block API (parse, render, update_block, append_history) |
| 3 | `src/contemplative_agent/cli.py:1396-1443` | `_handle_distill_identity` CLI 入口、history 書き込み箇所 |
| 4 | `src/contemplative_agent/core/views.py:199-261` | ViewRegistry (per-block view 解決の基盤) |
| 5 | `tests/test_identity_blocks.py` | multi-block テスト例 (`current_goals` 例あり) |

## Test 戦略

- `test_distill.py:390-545` の `distill_identity` テスト群を block_name parametrize 化 (各 enabled block に対して同じ shape のテストを回す)
- `test_identity_blocks.py` は既に multi-block を扱うので追加変更小
- 新規: per-block dispatch の unit test (`_BLOCK_CONFIG` lookup、unknown block で ValueError)
- 新規: enabled=False block を distill しようとした際の behavior

## 関連 ADR

- ADR-0024: identity_blocks 導入 (multi-block parse/render)。L123-126 で D3 を `next ADR territory` として deferred
- ADR-0025: per-block hash 記録 (`identity_history.jsonl`)。L101-105 で D3 + D4 を deferred
- 新規 ADR が必要かは設計レビュー後判断。現状 ADR-0024/0025 の延長線上で済むなら不要、CLI 仕様が大きく変わるなら ADR-0030 として起票

## Out of Scope (次々セッション以降)

- D4 (`agent-edit` runtime tool): セッション中に individual block を更新する CLI/tool。ADR-0013 (authorship-problem) + ADR-0017 (manas frame) との接続が必要で独立 ADR が要る
- Issue 1 / Issue 7 (Rare-important pattern 救済): `RARE_IMPORTANT_FLOOR` 値 decision が別途必要

## Reproduction (動作確認用)

```bash
cd <repo root>  # このドキュメント作成時のディレクトリ名は contemplative-moltbook

# 現状の distill-identity 動作確認 (persona_core のみ refresh される)
contemplative-agent distill-identity --stage

# identity history の現状を見る
contemplative-agent inspect-identity-history --tail 5
```
