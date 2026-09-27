# ANN 系ルール導入 + ANN401 drain（LLM-first 軸 4 の充足）+ docs/evidence 根本対策

## Context

verify-bootstrap skill に LLM-first 4 軸の select 方針が加わった（2026-08-31 harness 棚卸し）。
audit 照合の結果、この repo の gap は軸 4「境界の明示型強制」のみ: select に ANN なし、
pyright は明示 mode なし（= **standard**、pyright 1.1.410。`scripts/` は include 外）。

実測（2026-08-31）: ANN001-003+ANN201 は production 側（src/scripts/evals）で違反 **0**（追加 = 現状凍結）。
ANN401 は **24 件 / 9 ファイル**。tests/** は 5,810 件（消費される境界ではない → 除外）。
docs/evidence/** は ANN001×21+ANN201×13 = 34 件が 4 記録に閉じる（凍結逐語記録 — 刈れない）。

ユーザー決定: (1) 全ルール導入、ANN401 は免除ゼロ・inline noqa ゼロ・挙動保存で全件刈る。
(2) docs/evidence は per-file-ignores 積み増しをやめ**検査対象集合から根本除外**。

## 変更 1: pyproject.toml

- `select` に `ANN001,ANN002,ANN003,ANN201,ANN401` 追加。コメント: LLM-first 軸 4（境界の
  明示型は再生成・別セッション編集の凍結端）、ANN202/204-206 は非選択（明示 pin の方針どおり）
- `per-file-ignores`: `"tests/**"` に ANN 系 5 rule を追加（理由コメント付き）
- **docs/evidence 根本対策**: `[tool.ruff]` に `extend-exclude = ["docs/evidence"]` +
  `force-exclude = true`。既存の `"docs/evidence/**" = ["T20", "C901"]` 免除行を**削除**。
  lint / format 両方・staged（tmpdir で `ruff check .` 探索、pyproject は index から複製済みを確認）/
  full 両モードで対象外。force-exclude は PostToolUse autofix hook の明示パス経路も塞ぐ。
  トレードオフ（許容）: F 系も evidence では見なくなる — 凍結記録は編集されない前提

## 変更 2: verify.sh — bandit も evidence を見ない

staged モードの `bandit -q -r .`（107 行目）へ `-x ./docs/evidence` を追加（latent gap:
evidence を stage すると凍結記録が bandit 走査される。full は `-r src evals` で元から対象外）。
**verify.sh 変更 = 人間が diff を読んで `python3 ~/.claude/scripts/hooks/verify_allow.py approve <repo>` で再承認**。

## 変更 3: ANN401 drain 24 件

### 低リスク 17 件（探索で narrowing 済み確認）
- `object` 置換 8 件: `client.py:88/96/112/260/537`、`post_pipeline.py:44`、
  `selection_window.py:49`（TypeGuard で下流不変）、`publish.py:105`（`*args: object`）
- scripts 4 件（pyright 対象外）: `value_layer_approval_join.py:633` → `object`、
  `retrieval_recall_measure.py:959` `**extra` → `object`、`:808` ×2 → `np.ndarray`
  （np は遅延 import — `from __future__ import annotations` を付ける）
- TypeVar 化 2 件: `state_invariant_check.py:206` `_load_typed(expected: type[T], default: T) -> T`
- union 記載 1 件: `memory_cmds.py:215` → `str | IdentityResult | AmendmentResult`
- Generic 化 2 件: `memory_repos.py:129/282` — `InteractionIndex` / `PostHistory` を `Generic[T]`
  （`interaction_cls: type[T]` → `-> T`。facade `memory.py:203/258` の宣言が正解）

### 難所 A: client.py `**kwargs: Any` ×4（436/572/575/578）— 明示 named params 化
全呼び出しサイト実測: 流れる kwargs は `json=`（3 箇所）と `params=`（1 箇所、`dict[str, str]`）のみ。
`timeout` / `allow_redirects` は `_request` 内 `setdefault` 専用で外から渡す箇所ゼロ。

- `_request(..., retries: int = 0, *, json: dict[str, Any] | None = None, params: dict[str, str] | None = None)`。
  `setdefault` 2 行を削除し `session.request(..., json=json, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False)` に直書き（コメント移設）。
  429 再帰（:510）は `retries=retries + 1, json=json, params=params` で伝搬
- `get(path, *, params=None)` / `post(path, *, json=None)` / `delete(path)` に絞る
- 副次効果: `allow_redirects=False`（Bearer リーク防止）が呼び出し側から上書き不能に凍結 — 強化
- 挙動保存根拠: requests は `json=None`/`params=None` を既定値扱い（送信同一）。テストの断言は
  key 単位のみで exact-call なし。Unpack[TypedDict] は typing_extensions 新依存で棄却、
  `**kwargs: object` は stub 不適合で棄却

### 難所 B: publish.py verification ×3（68/100×2）— annotation-only（runtime 1 バイト不変）
handler（`agent.py:497`）は既に `verification: dict` 宣言で `.get`/`.keys()` を呼ぶ = dict 前提。
非 dict truthy の現挙動は AttributeError クラッシュなので、isinstance ガード追加は挙動変更 → しない。

- `passes_verification(verification: dict[str, Any] | None, ...)` — 本文無変更
- `verification_of(created: object) -> dict[str, Any] | None` — 式は無変更（isinstance narrow 済み）
- 整合: Protocol（`publish.py:43`）と `agent.py:499` の `dict` を `dict[str, Any]` に揃える
- pyright 波及確認済み: 呼び出し 3 箇所（post_pipeline.py:457 / feed_manager.py:490 / reply_handler.py:348）適合

### 発見された latent bug（drain のスコープ外 — 起票判断）
非 dict の verification が届くと `_handle_verification` で AttributeError（server-controlled 入力で
production ループがクラッシュしうる）。HIGH 相当なら
`claims.py spawn --origin review --producer src/contemplative_agent/adapters/moltbook/publish.py:100` で
RFC 起票、そうでなければ commit message に 1 行残して捨てる（rule task-tracking 準拠）。

## 変更 4: .claude/verify.md

lint 節に日付つき選定記録: 軸 4 充足・実測 as-of・tests 除外理由・drain 24 件の内訳表・
docs/evidence の根本除外（per-file-ignores → extend-exclude への移行理由）・JSONValue alias を
作らない判断（`object` + narrowing で足りる、`dict[str, Any]` が支配的慣用、core の公開面を増やさない）。

## 実装順序（ゲートを一瞬も赤にしない）

1. Stage 0: `.claude/verify.sh` full green 確認 + ANN401 24 件の baseline 計測
2. Stage 1: 低リスク 17 件 → `uv run pyright` + 関連 pytest（test_memory* 等）
3. Stage 2: 難所 A → pyright + `pytest tests/test_client.py tests/test_auth.py tests/test_submolt_scope.py tests/test_feed_manager.py`
4. Stage 3: 難所 B → pyright + `pytest tests/test_publish_logging.py tests/test_agent.py tests/test_verification.py`
5. Stage 4: pyproject flip（select + tests 免除 + evidence 除外）+ verify.sh の bandit -x
6. 人間: verify.sh diff を読んで `verify_allow.py approve`

注釈変更は select 追加前は不活性なので、この順序ならゲートは常に green。

## Verification

- `uv run ruff check src/ tests/ scripts/ evals/` = 0 件、`uv run ruff check --no-cache .`（staged 面相当）= 0 件
- probe 注入で ANN201 / ANN401 の発火実証（full 相当 + `verify.sh --staged`）→ probe 撤去
- **evidence 除外の実証**: 既存 evidence .py（C901=20 の baseline 等）を一時 stage して
  `verify.sh --staged` PASS → unstage。`ruff check <evidence明示パス>` が excluded になることも確認
- `uv run pyright` / `uv run pytest tests/ -q` 全 PASS（挙動保存）
- `.claude/verify.sh`（引数なし）全 PASS
- commit は push-workflow（main 直 commit）。verify.md 同期を同 commit に含める
