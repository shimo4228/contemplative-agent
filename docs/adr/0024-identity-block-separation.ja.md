# ADR-0024: Identity Block Separation — Frontmatter で addressing する persona ブロック

> **[ADR-0030](0030-withdraw-identity-blocks.ja.md) に supersede された (2026-04-18)。** 単一責任原則の観点から撤回: 複数の concern (`persona_core`、`current_goals`、将来の block) を 1 ファイルに詰め込み、その内部に sub-addressing を再構築するのは、周囲のメモリ stack が既に責務ごとに層を提供している状況では、concern を分離すべき場所として間違っている。履歴として本文は保持。

## Status

superseded-by 0030

## Date

2026-04-16

## Context

現状 `~/.config/moltbook/identity.md` は単一の平文ブロブ。`distill-identity` はファイル全体を再生成し、`llm._build_system_prompt()` はその全体を system prompt に貼り付ける。スタック中で最も古い部品で、いまだに full-file overwrite をしているのはここだけ。

痛点は 3 つ:

1. **粒度** — distill-identity は段落全部を一度に refresh する。"current goals" の persona ドリフトが "core self" 段落まで書き換えを強いる。エージェント（または将来の承認ゲート付きツール）が identity の 1 側面だけ残りに触れずに編集する方法がない。
2. **監査性** — ファイル全体が上書きされるので、`logs/audit.jsonl` は「identity.md が書かれた」しか記録せず、*どの部分が何故変わったか* は記録しない。Phase 1–3 は他のメモリ面（pattern, skill）に bitemporal / feedback / history トラッキングを与えた。identity だけが浮いている。
3. **拡張性** — Letta の Persona-Block 設計、A-Mem の Memory Evolution、Memento-Skills はいずれも identity 隣接の state を **名前付きで addressing できる単位の集合** として扱い、モノリスとしては扱わない。Phase 2 と Phase 3 の ADR は後の配線でこの形を前提にしている; ブロブのまま続けるとそれらの拡張を塞ぐ。

マスタープラン（`unified-booping-snowflake.md` §Phase 4, IV-6）はこれを schema + migration + block-aware distill にスコープする。per-block distill routing と専用 `agent-edit` ツールは明示的に延期。

## Decision

`identity.md` に **frontmatter で addressing するブロック** を導入する。frontmatter があるファイルは typed なブロックリストを持ち、ない場合は変更なしで動き続ける（単一の `persona_core` ブロックとして扱う）。

### ファイル形式

```markdown
---
blocks:
  - name: persona_core
    last_updated_at: 2026-04-16T10:00:00+00:00
    source: distill-identity
  - name: current_goals
    last_updated_at: 2026-04-16T10:00:00+00:00
    source: agent-edit
---

## persona_core

I'm an AI agent exploring contemplative traditions ...

## current_goals

Running experiments with cooperation games ...
```

主要プロパティ:

- **ブロックは名前付き** で順序付き。round-trip で順序は保たれる。
- **各ブロックはメタデータを持つ** — `last_updated_at`（ISO8601 UTC）と `source`（`distill-identity | agent-edit | migration | template | legacy`）。メタデータは frontmatter に留まり、render された body はきれいに読める。
- **セクションヘッダは `## name`** — 全ブロックで同じレベル。parser はこれを anchor にする。
- **Legacy フォールバック**: `---` で始まらないファイルは `[Block(name="persona_core", body=<ファイル全体>, source="legacy")]` として parse される。renderer はファイルの現在フォーマットを保つ: 入力が legacy なら出力も legacy のまま（明示的に migrate を呼ばない限り）。

### モジュール

`src/contemplative_agent/core/identity_blocks.py` を追加:

```python
@dataclass(frozen=True)
class Block:
    name: str
    body: str
    last_updated_at: Optional[str]
    source: str  # 上記 enum を参照
    extra: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class IdentityDocument:
    blocks: Tuple[Block, ...]
    is_legacy: bool  # 平文ファイルから parse したら True


def parse(text: str) -> IdentityDocument: ...
def render(doc: IdentityDocument) -> str: ...
def update_block(
    doc: IdentityDocument, name: str, *, body: str, source: str, now: Optional[str] = None
) -> IdentityDocument: ...
def load_for_prompt(path: Path) -> str:
    """連結されたブロック body を system prompt に貼り付けるために返す。
    Legacy ファイルはファイル全体をそのまま返す。frontmatter は決して
    プロンプトに漏れない。"""
```

parser は **stdlib のみ**（ADR-0023 の `skill_frontmatter.py` と同じ規律）。ブロックは名前で addressing する; malformed な frontmatter は raise せず legacy モードにフォールバックするので、壊れたファイルでエージェントがオフラインになることはない。

### Runtime read path

`llm._build_system_prompt()` は `path.read_text()` の代わりに `identity_blocks.load_for_prompt(path)` を呼ぶ。これは **legacy ファイルには振る舞い変化なし**（同じ bytes in、同じ bytes out）で、block 形式ファイルでは frontmatter を剥いでから貼り付ける。validation（`validate_identity_content`）は render されたプロンプトテキストに対し、今までと同じく動く。

### Write path（distill-identity）

`distill.distill_identity()`:

1. 現 identity を `identity_blocks.parse()` 経由で読む。
2. `persona_core` ブロックの body（legacy なら全体 body）を既存の 2 段 LLM refine に渡す。
3. 成功時、`update_block(doc, "persona_core", body=new_text, source="distill-identity")` を呼び、*render された document テキスト* を持つ `IdentityResult` を返す — 承認ゲート越しのファイル書き込みは依然として atomic な全ファイル書き込みだが、他のブロック（例: `current_goals`）は **bitwise で不変** のまま。
4. `~/.config/moltbook/identity_history.jsonl` にエントリを追記する: `{ts, block, old_hash, new_hash, source, approved_by}`。old/new body の SHA-256 ハッシュを記録し、body そのものは記録しない — history ファイルは untrusted な内容を重複させず、小さく保つ。full-text の復元は snapshot（ADR-0020）から、history からではない。

ディスク上のファイルが legacy（frontmatter なし）で書き込みが成功したら、writer は legacy モードに留まる。block 形式への移行は明示的 — 次フェーズの `migrate-identity` CLI 経由か、`init` 時に初期 block frontmatter を与えることで行う。

### Migration helper

`migrate_identity_to_blocks(path, *, now) -> MigrationResult` は `<path>.bak.pre-adr0024` を作成し、legacy body を読み、単一の `persona_core` ブロック（`source="migration"`）を持つ block 形式ファイルを書く。冪等: ファイルが既に frontmatter を持つなら `MigrationResult(already_migrated=True)` を返し何も触らない。**この ADR では CLI 配線なし** — Phase 3 のケイデンスに従い、振る舞い変更リスクは per-block distill routing と `agent-edit` ツールとまとめて follow-up ADR で降ろす。

### Trust boundary

ブロックは **trusted**（現在の identity.md と同じ）。frontmatter メタデータは外部入力ではなくこのコードパスが生成する。`source` はクローズドな enum で、free な文字列ではない。history ファイルは `write_restricted` で 0600 パーミッションで書かれる。

## Consequences

**Positive**:

- per-block distill（次 ADR）、agent-edit ツール（次 ADR）、identity introspection のブロックを外す — 各ブロックは名前で独立に addressing できる。
- history ログにより、identity は ADR-0021 で pattern が、ADR-0023 で skill が得たのと同じ監査性を得る。
- Legacy ファイルと既存 11 テンプレは migration ゼロで動き続ける。
- migration が走れば `distill-identity` は無関係な persona 面を叩かなくなる。
- parser レベルの YAML フォールバックにより、壊れた identity.md は system prompt 構築をクラッシュさせず「legacy whole-file」にデグレードする。

**Negative / risks**:

- migration が全ユーザに浸透するまで 2 コードパス（legacy vs block）が共存する。バグ表面はやや広いが、両パスがテストされ、legacy パスは「ファイル全体を読む」セマンティクスに折り畳まれる（既存と同じ）ので緩和。
- `identity_history.jsonl` は上限なく伸びる。許容: エントリ 1 件 ~200 bytes、distill ごとに 1 件、ADR-0021 が memory artefact は no-delete を決めている。
- `identity_blocks` は新しい小モジュール。ADR-0023 の `skill_frontmatter` 選択と一貫する — 同じ stdlib のみ parser ファミリーで、3 dataclass 分のメタデータのために `PyYAML` runtime 依存を避ける justification がある。

**Deferred（この ADR では扱わない）**:

- `contemplative-agent migrate-identity` CLI サブコマンド。
- per-block distill routing（例: `current_goals` を `persona_core` とは別の pattern view から distill）。
- 走行中のエージェントがターン内で 1 ブロックを更新する `agent-edit` ツール（承認ゲート付き）。
- "name がある、body が文字列" を超える block スキーマ検証 — 現状、未知のブロック名を受け入れ、プロンプト renderer に素通しで含めさせている。

## 検討した代替案

1. **PyYAML 依存** — ブロックあたり 3 key のために 200 KB+ の C 拡張可能な依存を引く。却下: ADR-0023 `skill_frontmatter` と同じ論理。小さな手書きサブセットで十分で `pyproject.toml` を minimal に保てる。
2. **ブロックを別ファイル化**（`identity/persona_core.md`, `identity/current_goals.md`）— per-block の version control がすっきりするが、`llm.py` の single-file read が壊れ、ファイルシステム syscall が増え、ブロック順序セマンティクスを失う。現在のブロック数（1–5）に対し over-engineering として却下。
3. **ブロックを `knowledge.json` に格納** — Phase 1 のスキーマ（provenance, trust, bitemporal）を再利用できる。却下: identity は意図して *trusted* で *self-authored* な面で、memory pattern ではない。untrusted/scored な pattern store と co-mingle すると ADR-0007 の境界を侵食する。
4. **初回 distill で auto-migrate** — on-disk フォーマットをサイレントにアップグレード。却下: 11 テンプレが平文で checkin されている; auto-migration はチェックアウトしたテンプレと running ファイルを比較する人を驚かせる。migration は明示的でなければならない。
5. **この ADR で per-block な LLM distill を実現** — ブロック種別ごとの新プロンプトと per-view routing が必要。scope creep として却下; Phase 4 の remit はスキーマ移行であって、各ブロックの意味の再解釈ではない。

## References

- Letta Persona / Human blocks — エージェントのブロック addressing な長期記憶（セッション跨ぎの persistent context）。
- [ADR-0007](0007-security-boundary-model.md) — identity がその中に存在する信頼境界モデル。
- [ADR-0012](0012-human-approval-gate.md) — `MOLTBOOK_HOME` への書き込み承認ゲート。
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — snapshot は full-text 復元の経路として残る; history log はハッシュのみ。
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — このADRが mirror するスキーマ拡張ケイデンス。
- [ADR-0023](0023-skill-as-memory-loop.md) — 「stdlib のみ frontmatter + history log + CLI 配線は deferred」という同じ規律を持つ sibling ADR。
