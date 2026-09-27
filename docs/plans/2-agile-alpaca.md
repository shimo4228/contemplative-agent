# T-RUFF-TYPING + T-VER-RULETABLE

## Context

台帳 `.notes/TASKS.md` の ready 2 件を片付ける。順序は **ruff → parser**（ruff の一括 sweep が `verification_parse.py` も書き換えるため、先に済ませて parser refactor を安定した地面の上でやる。逆順だと差分レビューに typing churn が混ざる）。

### T-RUFF-TYPING — hook と repo で ruff のルールセットが割れている

`hooks/ruff-autofix.sh` は PATH→uvx 解決で **ruff 0.16.0** を使い（`.venv` を意図的に見ない = 2026-07-06 security review の CRITICAL 対応）、repo は lock 経由で **0.15.17**。実測で確認した割れ:

```
uvx (0.16.0)      ruff check src/ tests/  → 844 errors
.venv (0.15.17)   ruff check src/ tests/  → All checks passed!
```

pyproject の `extend-select = ["B","I","T20"]` は両者同じなので、原因は **0.16 の default rule set 拡大**（UP 670 件に加え SIM / RUF / PLC0414 / PLW / TC / DTZ / TRY / FURB / EXE / RUF100 など計 174 件）。つまり編集したファイルだけ hook に近代化され、repo の Verify では検出されない。既に 6 ファイルが二層化済み。

ユーザー判断は **(a) UP 有効化 + 全域一括移行**。ただし単に `extend-select` に `UP` を足すだけでは、pin を 0.16 に上げた瞬間に UP 以外の 174 件も一緒に降ってくる。**default 集合への依存自体をやめて `select` で明示固定**すれば、どのバージョンでも同じ答えになる（実測: `--select E4,E7,E9,F,B,I,T20,UP` は 0.15.17 / 0.16.0 とも **674 errors で完全一致**）。これが (a) の耐久版。

### T-VER-RULETABLE — 検証パーサを宣言的規則表へ

`_resolve` / `_resolve_implicit` の命令的な if/return 連鎖を、順序つき規則表 + 単一ドライバへ。分岐数を減らすのが目的では**ない**（26+27 分岐は 9 回の改正で実誤答から削り出した文法規則そのもの）。次の改正で「どの行に足すか」を自明にするのが目的。検証手段（differential replay + baseline snapshot）が揃っている今が最安。

---

## Part 1 — T-RUFF-TYPING

### 変更

**`pyproject.toml`**

- `[tool.ruff.lint]` の `extend-select` を **`select` に置換**し、default 集合への依存を切る:
  ```toml
  # Pin the rule set explicitly instead of inheriting ruff's defaults: the
  # PostToolUse autofix hook resolves ruff from PATH/uvx (0.16) while this
  # repo locks 0.15.17, and 0.16 widened its defaults — an implicit set
  # silently modernizes only the files you happen to edit.
  select = ["E4", "E7", "E9", "F", "B", "I", "T20", "UP"]
  ```
- dev dependency を `"ruff>=0.16"` へ（floor を上げる。`select` 明示済みなので挙動は同じだが、hook と同じ版で回せるようにする）。`uv lock` で 0.16.x へ更新。
- `per-file-ignores` / `isort.combine-as-imports` は据え置き。

**一括移行**: `uv run ruff check --fix src/ tests/`（594 fixable）→ 残り 80 件（UP035 の `typing.Dict` 系 deprecated-import など `[-]` 表示分）を手動 or `--unsafe-fixes` を個別確認して解消。`uv run ruff format src/ tests/` で整形。対象 55 ファイル（src/ 46 + tests/ 9）。

**`CLAUDE.md`**: 開発環境ブロックに lint コマンドが**書かれていない**（grep で "ruff" ゼロヒット）。Verify の lint 段が常駐文書に無いのがそもそもの遠因なので、`uv run ruff check src/ tests/` を pytest / lint-imports と並べて追記する。

### 注意

- `requires-python = ">=3.10"`、97 ファイルが既に `from __future__ import annotations` を持つので UP045/UP007 の runtime リスクは無し（PEP 604 は 3.10 でネイティブ）。
- CI は存在しない（`.github/` なし）。ゲートはローカルのみ。

### コミット

1. `chore: pin the ruff rule set explicitly and modernize typing across the tree` — pyproject + uv.lock + 55 ファイルの機械的 fix（1 commit。差分は大きいがレビューは機械的）
2. CLAUDE.md の lint コマンド追記は同 commit に含めてよい

### Verify

`uv run ruff check src/ tests/` と `uvx ruff check src/ tests/` が**同じ結果**になること（これが今回の本題）。加えて `uv run pytest tests/ -q`（1546+）、`uv run lint-imports`、`git status`。

---

## Part 2 — T-VER-RULETABLE

対象は `src/contemplative_agent/adapters/moltbook/verification_parse.py` の 3 箇所のみ（`_TailSignals` 847-900 / `_resolve` 902-1018 / `_resolve_implicit` 1020-1110）。外部からこの 3 つを参照するコードもテストも無いので波及はファイル内に閉じる。

### 設計

**規則表にしない部分（正直に据え置く）**: `_resolve` 912-984 の位置分類（ops/marks を head / gap[i] / tail へ畳み込み → collapse → 曖昧性チェック）は決定カスケードでなく**畳み込み**。ここの 4 つの `return None` は分類自体のガード節で、述語にできない（述語が読むべき context をこのループが作っているため）。`_classify_positions(...) -> Optional[_Positions]` としてそのまま抽出し、命令的のまま残すことを docstring に明記する。

**三値の結果型（本件の肝）**: 各規則は fire（答えを返す）/ abstain（None を返して**停止**）/ fall through（次の規則へ）の 3 状態が要る。素朴な `Callable[..., str | None]` では abstain と非適用が潰れ、黙って挙動が変わる。

```python
class _Decision(NamedTuple):
    stop: bool
    answer: Optional[str]

_NEXT = _Decision(stop=False, answer=None)      # 適用外 — 次の行へ
_ABSTAIN = _Decision(stop=True, answer=None)    # 発火して沈黙
def _answer(value): return _Decision(True, value)   # _compute_chain の None も「発火」
```

`_compute_chain` は域外（負の中間値・ゼロ除算）で `None` を返す。これは非適用ではなく**発火して答えなし**なので `_answer()` で包んで必ず停止させる。

**規則行**: `cli/registry.py` の `CommandSpec` に倣い frozen dataclass + module-level `tuple[_Rule, ...]` + 汎用ドライバ。

```python
@dataclass(frozen=True)
class _Rule(Generic[_Ctx]):
    name: str
    when: Callable[[_Ctx], bool]
    then: Callable[[_Ctx], _Decision]

def _resolve_operation(rules, ctx) -> Optional[str]:
    for rule in rules:
        if not rule.when(ctx):
            continue
        decision = rule.then(ctx)
        if decision.stop:
            return decision.answer
    raise AssertionError("rule table is not total")  # 各表は無条件の終端行で閉じる
```

**表は 2 つ**（1 つに融合すると explicit 側の全述語が `ctx.chain is not None` で始まり、順序の主張が埋もれる）:

- `_EXPLICIT_TAIL_RULES`（`_resolve` 986-1011 由来、4 行）: `adjacent_multiplicative_tail_overrides_change_verb` / `tail_operation_contradicts_chain` / `subtraction_chain_against_combined_cue` / `explicit_chain`
- `_IMPLICIT_RULES`（`_resolve_implicit` 1047-1109 由来、14 行 = 元の `return` 1 つにつき 1 行）: 乗法 3 行 → 減法 4 行 → 加法質問枠 1 行 → count multiplier 1 行 → implicit add 5 行

context は frozen dataclass（`_ExplicitCtx` / `_ImplicitCtx`）で、入れ子 `if` の外側条件を**名前つきフィールドに昇格**して各行が verbatim に再利用する（`has_mult_signal = bool(mult_tail or adjacent_marks)` など）。これが flatten 時の述語漏れ対策の本体。派生値は factory で**eager 計算**（関与するヘルパーは全て純粋で `_Abstain` を投げない — raise は 571/578/800 の上流のみ）。

`_TailSignals` は変更しない。既に正しい形（一箇所で導出して両分岐へ渡す = 10th amendment の成果）で、規則 context の核になる。

`_resolve` 1013-1016 のルーティング（`len(operands) != 2 or any(filled)`）は文法規則でなくディスパッチなので `_resolve` に 2 行のまま残す。

### 唯一の非自明な等価性

explicit 行 1 の override。現行コードは `chain = [_MUL]` に書き換えてから sub/"combined" ガードへ**落ちる**が、`_normalize_op(_MUL) != _SUB` なのでそのガードは override 後は必ず不活性 → 行 1 が直接答えを返すのは厳密に等価。commit message に明記する（差分リプレイが証明）。

### コミット（各段で個別にゲート通過）

1. `refactor: name the position classification _resolve does before it decides` — 912-984 を `_classify_positions` へ抽出（純粋な移動）
2. `refactor: the implicit two-operand rules become an ordered table` — `_Decision` / `_Rule` / `_resolve_operation` / `_ImplicitCtx` / `_IMPLICIT_RULES`
3. `refactor: the explicit-chain tail rules join the same table` — `_ExplicitCtx` / `_EXPLICIT_TAIL_RULES`
4. `docs: record the rule-table representation` — ADR-0062 に amendment note（三値である理由・前段を命令的に残した理由）+ 台帳 T-VER-RULETABLE を Done へ（実測の行数/行数比つき）

`verification_parse_baseline.py` は**絶対に触らない**。

### Verify（各コミットごと）

1. `python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py` → mismatch 0 / 比較件数が全件（≥2149。エージェントが監査ログを書き続けるので N は増えうる。着手時点の N を記録し「その N の 100%」を要求する。可能ならリファクタ中はスケジュール実行を止める）
2. `uv run pytest tests/test_verification.py -q`（67 test）
3. 最終のみ `uv run pytest tests/ -q` 全件 + `uv run lint-imports`
4. `replay_parser.py` は**合否ゲートにしない**（既存で wrong=7 = T-VER-GRAMMAR-11）。回すなら wrong が厳密に 7、abstain が 382 のままであること = リファクタが何も動かしていないことの確認としてのみ

### Review チェーン

実装後、`python-reviewer` + `security-reviewer` + `codex-review` を diff に対して並列起動（refactor 種別だが、パーサは untrusted 入力の境界なので security は Y、公開 API でなくとも過去 9 改正が codex/python reviewer 指摘由来なので cross-model も Y）。

---

## Parallel Group / Sequential

```
Sequential: Part 1 (ruff) → Verify → Part 2 (parser, 4 commits) → Review → Verify
Parallel Group (Part 2 実装後): [python-reviewer, security-reviewer, codex-review]
```

Part 1 と Part 2 は同一ファイルを触るので並列化しない。
