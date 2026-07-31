# ADR-0025: Identity History ログ配線 + migrate-identity CLI

> **[ADR-0030](0030-withdraw-identity-blocks.ja.md) に supersede された (2026-04-18)。** 稼働環境で `identity_history.jsonl` は一度も書かれず、ADR-0020 snapshot + `audit.jsonl` が既に本 ADR がカバーしようとした監査面を埋めていた。履歴として本文は保持。

## Status

superseded-by 0030

## Date

2026-04-16

## Context

ADR-0024 は identity のブロックスキーマ、stdlib のみの parser/renderer、block-aware な distill-identity、migration を純関数として出荷した。Phase-3 ケイデンス（「schema は降ろす、配線は延期」）に従い、2 つの成果物を意図的に先送りにしていた:

1. **`identity_history.jsonl` が live コードパスで書かれていない。** `identity_blocks.append_history()` はテスト済みで準備完了（0600 perms、JSONL、old/new body の SHA-256 16-hex-prefix ハッシュ）だが、distill-identity の呼び出し箇所から invoke されていない。結果、ブロック変更のたびにディスクに書き換えが発生するが、汎用 `audit.jsonl` の承認レコードを超える per-block 監査トレイルは残らない。
2. **`migrate-identity` CLI がない。** 純関数 `identity_blocks.migrate_to_blocks(path)` は冪等で、`.bak.pre-adr0024` を作り、フルテスト済み — だが legacy な `identity.md` を block フォーマットにアップグレードしたいユーザは Python シェルに落ちるしかない。11 パッケージテンプレと、ユーザ既存の `identity.md` は、migration が easy に呼べるまで legacy に留まる。

同じ follow-up セットからの deferred-but-deeper な 2 タスク — per-block distill routing と runtime agent-edit tool — は **明示的にスコープ外**。per-block routing はブロック別プロンプト規律（各プロンプトを Opus ではなく qwen3.5:9b 自身の思考空間で書かせる）を要し、複数ファイルに波及する。agent-edit tool は ADR-0013 authorship-problem 領域に踏み込む — mid-session の自己改変はこのコードベースに前例がなく、独自 ADR に値する。

## Decision

### 1. `IDENTITY_HISTORY_PATH` 定数を追加

`src/contemplative_agent/core/config.py`、`IDENTITY_PATH` の隣に:

```python
IDENTITY_HISTORY_PATH = MOLTBOOK_DATA_DIR / "logs" / "identity_history.jsonl"
```

history log を既存の `logs/` ディレクトリの `audit.jsonl` の隣に置く。0600 perms は `identity_blocks.append_history()` が強制（テスト済み）。2 つのログは別目的を果たす:

- `audit.jsonl` — **汎用承認レコード。** 「ユーザが時刻 Z にパス Y について X を決めた」。どのコマンドでも承認イベントあたり 1 エントリ。
- `identity_history.jsonl` — **per-block 変更レコード。** 「ブロック `persona_core` が時刻 Z に source `distill-identity` でハッシュ A からハッシュ B に変わった」。ブロック変更あたり 1 エントリ、identity 専用。full-text 復元は snapshot サブシステム（ADR-0020）の役目; history はハッシュのみを保ち、ログを小さく保ち、untrusted 内容を再取り込みしない。

### 2. `IdentityResult` に history-threading フィールドを追加

`src/contemplative_agent/core/distill.py`:

```python
@dataclass(frozen=True)
class IdentityResult:
    text: str
    target_path: Path
    # ADR-0025 history threading — defaults で既存 caller がそのまま動く
    old_body: str = ""          # distill *前* の persona_core body
    new_body: str = ""          # distill *後* の refined persona body
    block_name: str = "persona_core"
    source: str = "distill-identity"
```

defaults が key property: `IdentityResult(text=..., target_path=...)` を構築する caller は動き続け、`.text` / `.target_path` しか読まない consumer は bit 一致。コードベース内で直接コンストラクトするテストはない（確認済み）ので、defaults 付きの新フィールドは非破壊。

`distill.distill_identity` は既に持っているものから新フィールドを埋める — `current_identity`（parse した document から取り出した persona_core body）が `old_body` になり、validate 後に cleanup された `new_persona_body` が `new_body` になる。

### 3. history フックを 3 つの CLI write 箇所に配線

| Site | When | Source label |
|---|---|---|
| `_handle_distill_identity` 直接書き込み | `_wr(...)` 成功後 | `"distill-identity"` |
| `_handle_adopt_staged`（`command == "distill-identity"`） | `write_restricted(...)` 成功後 | `"distill-identity"` |
| `_handle_distill_identity --stage` 経路 | **決して追記しない** — staging は承認前 | — |
| `_handle_migrate_identity` | `migrate_to_blocks()` 成功後 | `"migration"` |

すべての append 呼び出しは `try/except OSError` で包む — ログ書込失敗は成功したファイル書込を決してブロックしない。`_log_approval`（cli.py:284–285）と同じ防御パターン。

`adopt-staged` 分岐では、`write_restricted(...)` の **前** に現ファイルを読んで pre-write body をハッシュできるようにする。read-before-write なしだと、identity ファイルだと気づいた時点で古い内容は消えている。非 identity な staged 項目には read は無料（identity 分岐に入らない）で、identity.md には安い（小さなファイル 1 つ）。

### 4. `migrate-identity` CLI サブコマンド

`_handle_migrate_patterns`（ADR-0021）をパターン源に:

```bash
contemplative-agent migrate-identity              # migration を走らせる
contemplative-agent migrate-identity --dry-run    # プレビューのみ
```

- **既に block 形式** → `already in block format (no-op)` を出力し exit 0。
- **ファイルなし** → `No identity file found at ...` を出力し exit 0（エラーではない）。
- **Dry-run** → source path、*作成される* backup path、target block name を出力; ファイル書き込みなし。
- **本番** → `identity_blocks.migrate_to_blocks()` に委譲。`identity.md.bak.pre-adr0024` を書き、frontmatter スキーマで `identity.md` を書き直す。続いて、`audit.jsonl` に `_log_approval("migrate-identity", ...)` エントリ 1 件、`identity_history.jsonl` に `source="migration"` エントリ 1 件を追記 — 初期 persona_core body を表す。

Tier-1 の `no_llm_handlers` dispatch map に登録 — 純関数、LLM なし、ネットワークなし。`migrate-patterns` と同じ位置。

### 5. `identity_blocks.py` や `llm.py` には変更なし

両モジュールはすでに必要なものを全て公開している。`append_history`, `parse`, `.get`, `migrate_to_blocks` すべて ADR-0024 のテストとともに出荷済み。`llm._build_system_prompt` は既にブロック parser 経由でルーティングされる。

## Consequences

**Positive**:

- `distill-identity` の承認済み書き込みごとに per-block 監査トレイルが残る。将来のツール（`contemplative-agent inspect-identity-history`、次 ADR の per-block routing）はスキーマ追加なしでその上に乗れる。
- ユーザは legacy 平文 `identity.md` から block 形式への 1 コマンドアップグレード経路を得る。既存 11 パッケージテンプレは legacy 互換のまま; migration は opt-in。
- `migrate-patterns`（ADR-0021）と一貫した使い勝手 — 同じ `--dry-run`、同じサマリブロック、同じ audit log 統合。
- staging 経由の書き込み（`distill-identity --stage`）は、staging ではなく実際の adoption 時にのみ history を生む。history ログは地に足のついた状態 — 今ディスクに何があるか — を反映する。

**Negative / risks**:

- `IdentityResult` のフィールド数が倍増（2 → 6）。defaults で緩和; コードベース内に positional 引数のコンストラクタはないので呼び出し側は壊れない。
- `_handle_adopt_staged` に identity 固有分岐が増える。`distill-identity` が今日 identity artefact を生む唯一のコマンドなので許容; 将来のコマンド（後続 ADR の agent-edit）は同じ分岐に嵌る。
- `identity_history.jsonl` は上限なく伸びる。エントリ 1 件 ~250 bytes、distill 承認 / migration ごとに 1 件、伸びはユーザ活動で bounded。ADR-0021 は memory artefact の no-delete を決めており、同じ規律がここに適用される。

**明示的に扱わない**（次 ADR 領域）:

- per-block distill routing（`current_goals`, `recent_themes` 等、それぞれ独自 view と独自プロンプトから）。
- live セッション中に個別ブロックを更新する runtime agent-edit tool。
- `identity_history.jsonl` の自動 pruning / rotation / compaction。

## 検討した代替案

1. **すべての *提案* で（却下を含め）history append する** — ユーザが no と言っても LLM が書こうとしたものの可視性が得られる。却下: 承認イベントはすでに `audit.jsonl` にあり、`identity_history.jsonl` で「提案されたが却下」シグナルを重複させると history が audit log のノイジーな superset になる。history は地に足のついたディスク上変更にスコープする。
2. **history threading フィールドを `IdentityResult` ではなく専用 `DistillMetadata` sidecar に埋める** — 型階層が綺麗。却下: 誰も求めていない新 dataclass を足し、CLI が 2 オブジェクトを juggle することを強いる。sensible default 付きの 4 つのオプショナルフィールドに対する over-engineering。
3. **`IdentityResult` 拡張をせず、CLI が before/after body を自前で再ハッシュ** — `IdentityResult` を小さく保つ。却下: `distill.distill_identity` で既に走っている parse-and-extract のロジックを複製する。現行関数は `current_identity` 抽出のためにすでに document を parse している; CLI に同じ仕事を 2 回させるのは無駄。
4. **migrate-identity を別コマンドのフラグとして出荷**（例: `distill-identity --migrate`）— 直交する 2 操作を結合する。LLM 本番 distill なしで migrate したいユーザに強要すべきでない。却下: `migrate-patterns` の前例に従い、独立サブコマンドにする。
5. **`distill-identity` からの初回 block-format 書き込み時に自動 migration** — ユーザを in-place な形式変更で驚かせる。ADR-0024 が auto-migration を却下したのと同じ理由で却下: 11 パッケージテンプレは意図的に平文で、自動形式アップグレードはチェックアウトしたテンプレと running ファイルを比較する人を驚かせる。

## References

- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — snapshot は full-text 復元メカニズムとして残る; この ADR の history log はハッシュのみを保存。
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — `migrate-identity` が mirror する `migrate-patterns` CLI。
- [ADR-0023](0023-skill-as-memory-loop.md) — 「小さな stdlib のみ frontmatter + history log + CLI 配線は deferred」という規律を導入した sibling ADR。この ADR がその規律を identity で完成させる。
- [ADR-0024](0024-identity-block-separation.md) — この ADR は Phase 4 follow-up の deferred 配線を完成させる。
