# thermo-nuclear skill 導入 + ADR-0097 slice 2 の構造リファクタ

## Context

`cursor/plugins` の `thermo-nuclear-code-quality-review` skill を harness に入れ、その基準で
ADR-0097 slice 2（`47616da..b5751ec`）の成果物をレビューした。挙動は正しく局所設計も良かったが、
「複雑さを移動するのでなく削除する」経路が 4 本出た。判定は Fix。

**計画中に 1 本が偽陽性と判明した**（D — 包含述語の重複。実際は別スコープ・別 exit code の
別ゲートで、両方ともテストが pin していた）。C も「重複 4 組」のうち 1 組が誤りだった。
残る 3 本（A / C / B）を実行し、D は取り下げて誤指摘が再発しないようコメントだけ足す。

合わせて skill 自体を `~/.claude/skills/` に常設する（手動起動のみ、chain 配線は保留）。

**なぜ今か**: ADR-0097 slice 2 は 1 週間で 2 ファイルを 1000 行超に育てた。層の境界は repo の
語彙（「計器」= ADR-0071 / skill `read-only-instruments`）に既に存在していて、
`core/stocktake.py:44` は `TYPE_CHECKING` import で「このモジュールを計器への runtime 依存から
守るため」と手書きでその分離を維持している。構造が語彙に追いついていない状態を、
手で維持するのをやめて構造にする。

---

## Step 0 — skill を harness に入れる

`~/.claude/skills/thermo-nuclear-code-quality-review/SKILL.md` を新規作成。

本文は upstream verbatim（取得元:
`https://raw.githubusercontent.com/cursor/plugins/main/thermos/skills/thermo-nuclear-code-quality-review/SKILL.md`、
as-of 2026-08-25）。frontmatter だけ harness 規約に合わせる:

**body は 1 バイトも触らない。** frontmatter に `origin` を 1 行足すだけ:

```yaml
---
name: thermo-nuclear-code-quality-review
description: <upstream のまま>
disable-model-invocation: true    # ← upstream に既に入っている
origin: cursor/plugins            # ← 足すのはこの 1 行だけ
---
```

`origin: cursor/plugins` は rule `common/skills.md` の `{org/repo}`（外部 repo）。
本文無編集なので `-customized` は付けない。`herdr`（`origin: herdrdev/herdr`）と同じ形。
upstream の URL と取得日は commit message に残す（SKILL.md に書くと無改変でなくなる）。

`user-invocable: true` は**足さない** — `wait-what`（`disable-model-invocation: true` のみ、
`user-invocable` 無し）が `/wait-what` で起動できている先例があり、upstream の設定で
スラッシュ起動は成立する。

lint（`scripts/hooks/harness_lint.py:77-81, 224-250`）は `name` / `description` / `origin` の
**存在だけ**を見る。`origin` の値は enum 検証されない（`model:` と違い）。`name` はディレクトリ名と
一致必須。外部 origin の SKILL.md は markdown-link 検査の対象外（`harness_lint.py:20-21`、
無改変ポリシーとの衝突回避）。

`skill-creator` の草稿ゲートは通さない — あれは新規作成・大幅改修の入口であって、verbatim な
外部取り込みには適用されない（`herdr` / `wait-what` の先例）。

### 境界について（結論: 設置は問題ない。chain 配線だけ保留）

`implementation-chain` は review 軸を bug = `/code-review` / quality = `/simplify` /
security = `security-reviewer` / silent-failure = `silent-failure-hunter` の 4 つに分けており、
ADR-0039 → ADR-0042 で `code-reviewer` と `python-reviewer` を「built-in と重複」として
退役させている。`implementation-chain/SKILL.md:103-105` は「残る agent 枠は substrate が
持たない観点だけを持つ」と規定 — 素直に読めば quality 軸は `/simplify` の持ち物で、
`skill-creator` の境界チェックは「重なったら新規でなく既存への統合に倒せ」と言う。

**設置に関しては問題にならない。** upstream が `disable-model-invocation: true` を持つので
この skill は自発発火せず、`/thermo-nuclear-code-quality-review` と打った時だけ動く。
chain の中で `/simplify` と競合する経路が存在しない。residency cost は description 1 行分。

**軸としても別物**（このセッションの実測）: ADR-0097 slice 2 の commit message は
`deviation: /simplify を Review 後に実行 (適用 15 件は機械整理のみ、再 Verify 済み)` と記録している。
同じコードに thermo-nuclear を当てて、`/simplify` が出さなかった層の混在を出した。

| | `/simplify` | thermo-nuclear |
|---|---|---|
| 出力 | fix を working tree に適用 | findings + 承認バー（適用しない） |
| 高度 | 局所 cleanup・altitude | ファイル / モジュール境界の再編（code judo） |
| 判定 | 無し | presumptive blocker を持つ named verdict |

**chain への wiring は今回しない**: `implementation-chain` の Review 表と
`hooks/simplify-order-notice.sh:35-43` の `REVIEWERS` 名簿は
`tests/simplify-order-notice.bats` が一致を assert している。表に足すなら hook とテストも
同じ変更で触る。**2 回目の発火実績が出るまで手動起動のみ**とし、実績が溜まってから再検討する
（`chaos-tdd-chain-deferred` と同じ扱い）。

**公開は別作業**: harness の公開 copy への同期は skill `harness-sync` が担当。外部 origin の
公開判断はそのスコープ外なので、今回はローカル設置のみ。

---

## 測定済みの事実（実行前に AST で確認済み）

### `core/skill_selection.py` (2170 行)

依存方向:

- runtime → 計器 の逆流は **ゼロ**
- 計器 → runtime の参照は `load_skill_catalog` と定数 `_NAME_MAX_CHARS` の **2 つだけ**
- `_tokens` / `_is_prose` / `_is_int` / `_TOKEN_SPLIT_RE` はファイル前半にあるが**呼び出し元が全部計器側**
  （`_tokens` → 976 / 1015 / 1188 / 1190、`_is_prose` → 1007 のみ、`_is_int` → 1148 / 1151 / 1155 / 1880）。
  runtime に残さず一緒に移す

行数の内訳（def 実体のみ、header / import 除く）:

| 行き先 | 行数 |
|---|---|
| runtime | 417 |
| selection-log reading | 830 |
| never-selected reading | 582 |
| 共有基盤（`_SelectionDayFile` / `_iter_selection_days` / `resolve_selection_window`） | 102 |

never-selected は共有基盤に加えて `_FULL_CORPUS_VERDICTS` を使う（→ 基盤側へ）。

命名の先例: この repo の計器は `core/view_metrics.py` (388 行、ADR-0071 の正準例) と
`core/metrics.py` (189 行)。`skill_selection.py` の計器半分 1500 行はこの系列の外れ値。

**行数以外の実利**: `numpy` と `difflib` は**計器側でしか使われていない**（runtime 側の参照ゼロ）。
分離するとエージェント本体の import 経路から numpy が落ちる。`read_markdown_documents` /
`Iterator` / `date` / `timedelta` も同様に計器専用。逆に `generate`（LLM 呼び出し）/
`append_jsonl_restricted` / `skill_theme` / `strip_frontmatter` は runtime 専用 — つまり
**「LLM を呼ぶ側」と「ログを数える側」が今 1 モジュールに入っている**。

### `cli/adopt.py` (2056 行)

| 行き先 | 行数 |
|---|---|
| archive 出口プリミティブ | 305 |
| remove-skill | 242 |
| adopt-staged 本体 | 1303 |

抽出方向の循環は **両方向ともゼロ**。

CLI は既に「モジュールごとに `COMMANDS: tuple[CommandSpec, ...]` を publish し
`cli/__init__.py:32` が集約」というパターン（`agent_cmds` / `session_cmds` / `memory_cmds` /
`schedule` / `stocktake_cmd` / `adopt`）。remove-skill の独立モジュール化はこの既存パターンに乗るだけ。

### 散文密度（1k 行ルールを機械適用しない根拠）

| file | total | code | 散文 |
|---|---|---|---|
| `cli/adopt.py` | 2056 | ~919 | ~912 |
| `core/skill_selection.py` | 2170 | ~1166 | ~820 |

`adopt.py` はコード実体としては 1000 行未満。分割の理由は行数ではなく層の混在。

### テスト結合（移動コストの実体）

`skill_selection.py` 側:

- `tests/test_skill_selection.py` (2303 行) — `from ... import skill_selection as ss` の alias 経由で
  **160 call site**。うち約 126 が計器側の名前。**alias をリネームせず 2 本目を足す**のが正解
- 文字列パッチ **38 本**（全て `unittest.mock.patch`。`pytest-mock` はこの repo に無い）。
  移動で壊れるのは:
  - `test_skill_selection.py:2211` `...skill_selection.format_skill_selection_report`
  - `test_skill_selection.py:2215` `...skill_selection.format_never_selected_report`
  - `tests/test_cli_session.py` の **11 本全部**（`read_skill_selection_log` ×7 = 116/138/156/192/217/238/613、
    `format_skill_selection_report` ×4 = 115/191/216/612）
- private 属性 `ss._REJECTED_NAME_RENDER_LIMIT`（758 / 768）、公開定数
  `ss.WORDFORM_SIMILARITY_FLOOR`（1535）/ `ss.NEVER_SELECTED_EXPOSURE_FLOOR`（2169）
- `tests/test_stocktake.py:320` — `SkillSelectionReading` の関数内 import
- **`tests/test_frozen_dataclasses.py:26`** — `"src/contemplative_agent/core/skill_selection.py::_RegimeAccumulator"`
  をハードコードした allowlist。**両方向に検査される**（`:50` が src を AST 走査、`:74` が
  allowlist のエントリが実在するか検査）ので、同じ commit で直さないと必ず落ちる

`adopt.py` 側 — **archive プリミティブへのテスト結合はゼロ**。テストは reason code を
**裸の文字列リテラル**で assert している（`tests/test_cli_skill_archive.py:381, 389, 436, 461, 482,
534, 908, 928, 988`）ので、ハンドラさえ動けば抽出はテストから見えない。
`_handle_remove_skill` の import 行 2 本（`tests/test_cli_adopt.py:19`、
`tests/test_cli_skill_archive.py:28`）だけ直す。

### 機械ゲート側

- **import-linter は package 粒度**（`pyproject.toml:114-163`、layers = `cli` > `adapters` > `core`）。
  新モジュールの登録は不要、`tests/test_architecture.py` も無編集
- ruff の `per-file-ignores` は `"src/contemplative_agent/cli/**" = ["T20"]`（print 免除）。
  **新しい `core/` モジュールはこの免除を継承しない**。現状の formatter は文字列を返すだけなので
  問題ないが、移送中に `print` を持ち込まないこと
- `CommandSpec.resolve()`（`cli/registry.py:56-76`）は `sys.modules.get(handler.__module__)` +
  `getattr` なので、ハンドラを別モジュールへ移しても解決する。手で列挙しているのは
  `cli/__init__.py:15`（`from . import …`）と `:38`（`*adopt.COMMANDS`）の 2 箇所だけ

---

## Step 1 — A: `core/skill_selection.py` の層分離

**4 モジュールに割る。** 命名はこの repo の計器の先例（`core/view_metrics.py` 388 行、ADR-0071 の正準例）に合わせる。

| module | 中身 | 概算 |
|---|---|---|
| `core/skill_selection.py`（残す） | runtime: `configure_*` / `reset_*` / `SkillCatalogEntry` / `load_skill_catalog` / `SkillSelectionResult` / `_render_catalog` / `select_applicable_skills` / `_b64_fields` / `_append_selection_audit` / `configured_injection_regime` / `selection_preconditions_unmet` / `observed_injection_outcomes` / `selected_skills_block` / `shadow_observe_skill_selection` / `_load_selection_template` + `InjectionRegime` / `REGIME_*` / `_MAX_SKILL_SELECTION_AUDIT_BYTES` / `_SELECTION_NUM_PREDICT` / `_NONE_SENTINEL` / `_DESCRIPTION_MAX_CHARS` / `_NAME_MAX_CHARS` | ~550 |
| `core/selection_window.py`（新） | 共有基盤: `_SelectionDayFile` / `_iter_selection_days` / `resolve_selection_window` / `_FULL_CORPUS_VERDICTS` / `_tokens` / `_is_prose` / `_is_int` / `_TOKEN_SPLIT_RE` | ~180 |
| `core/selection_metrics.py`（新） | selection-log 計器: `SkillSelectionDay` / `RejectedNameTally` / `MechanismTally` / `CatalogRegime` / `_RegimeAccumulator` / `SkillSelectionReading` / `read_skill_selection_log` / `format_skill_selection_report` / `format_never_selected_exposure` / `classify_hallucination` / `_read_value_layer_vocabulary` + `HallucinationMechanism` / `WORDFORM_SIMILARITY_FLOOR` / `_VALUE_LAYER_TOKEN_MIN_CHARS` / `_REJECTED_NAME_RENDER_LIMIT` | ~900 |
| `core/never_selected_metrics.py`（新） | never-selected 計器: `NeverSelectedSkill` / `NeverSelectedReading` / `read_never_selected` / `never_selected_reading_json` / `_withholding` / `format_never_selected_report` + `NEVER_SELECTED_*` 5 定数 | ~650 |

依存は一方向: `never_selected_metrics` → `selection_window` + `skill_selection`(`load_skill_catalog`)、
`selection_metrics` → 同じ。逆流を作らない。

**再エクスポートの shim は作らない。** 呼び出し元は 6 箇所しかなく、間接を足すのは
この skill の趣旨（「磨くより層ごと消す」）に反する。全部直接更新する:

| 呼び出し元 | 対応 |
|---|---|
| `cli/session_cmds.py:146, 180-183, 219-223` | import 先を新モジュールへ |
| `cli/stocktake_cmd.py:102` | 同 |
| `core/stocktake.py:46`（`TYPE_CHECKING`）, `:263`（遅延 import） | 同。**この 2 箇所の遅延 import は分離後は不要**になる — 「このモジュールを計器への runtime 依存から守るため」という手書きの理由が構造で満たされるので、コメントごと素直な import に戻せるか検討する（`stocktake` → `never_selected_metrics` が循環を作らないことを確認してから） |
| `scripts/weekly-analysis.sh:471-474` | heredoc 内の import を書き換え。`tests/test_weekly_analysis_shell.py:246, 275` がゲート |
| `scripts/weekly-pipeline.sh:746-750` | **最高リスク。** 失敗が reason code `NEVER_SELECTED_SCAN_FAIL` に飲まれる silent degrade で、テストが無い。書き換え後に手動で 1 回実行して読み値が出ることを確認する |

runtime 側の呼び出し元（`cli/runtime.py:27`、`adapters/moltbook/llm_functions.py:30-33`、
`evals/run_eval.py:229-232, 306, 564`）は**無変更**。

テスト側:
- `tests/test_skill_selection.py` を 2 ファイルに割るか、alias を `ss` に加えて
  `sm`（selection_metrics）/ `ns`（never_selected_metrics）を足すか。**まず alias 追加で通し**、
  2303 行のファイル分割は別 commit に切る（1 commit 1 責務）
- 文字列パッチ 13 本（2211 / 2215 + `test_cli_session.py` の 11 本）を新しい定義位置へ
- `tests/test_frozen_dataclasses.py:26` の allowlist path を `core/selection_metrics.py::_RegimeAccumulator` へ
- `tests/test_stocktake.py:320` の import 先

---

## Step 2 — C: archive 出口の plan/apply 分割

### レビュー時の主張を 1 つ訂正する

レビューでは「重複判定 4 組」と書いたが、精査したら **3 組が真の重複、1 組は誤り**だった:

| レビュー時の主張 | 実際 |
|---|---|
| symlink 拒否 `1833` / `437` | **真の重複**（ただし `literal` vs `target` の罠あり、下記） |
| store 包含 `1805-1812` / `441` | **重複ではない** — 別の問い、別の exit code |
| 宛先の事前拒否 `1867` / `460` | **真の重複**（同じ関数を 2 回呼んでいる） |
| already-archived `1848` / `1895` | **真の重複**（同一関数内で同一式を 2 回）— 一番明白な勝ち |

### 設計

`_ArchivePlan`（frozen dataclass）を新設し、プリミティブを計画と適用に割る:

```python
@dataclass(frozen=True)
class _ArchivePlan:
    source: Path                    # LITERAL パス（rename が作用する側）
    data_root: Path
    superseded_by: str | None
    kind: str                       # _ARCHIVE_KIND_ARCHIVE | _ARCHIVE_KIND_PURGE
    intended: Path                  # _archive_dir(data_root) / source.name
    destination_refusal: str | None

_plan_archive(source, *, data_root, superseded_by) -> _ArchivePlan | _ArchiveResult
_apply_archive_plan(plan) -> _ArchiveResult          # 唯一の変更操作
_archive_skill_file(...) = _plan_archive + _apply_archive_plan   # 既存呼び出し元の入口
```

`_apply_archive_plan` が **plan だけ**を引数に取るのが構造上の保証 — preview と本番が
別の入力を見る経路が存在しなくなる。

**要点 4 つ:**

1. **`destination_refusal` は「拒否の返り値」でなく plan の field にする。** 宛先の不調は
   *archive slot* についての事実で、`--delete` は正当にこれを無視する（現状 `1867` の
   `if not delete and ...`）。union の refusal にすると `remove-skill --delete` が
   `.archive` 破損時に新たに exit 1 するようになる — 現状は成功する
2. **`_plan_archive` には `literal` を渡す（`target` ではない）。** `target = literal.resolve()`
   に対する `is_symlink()` は常に False なので、`target` を渡すと symlink 検査が無言の no-op になり
   重複解消の意味が消える。現状 `1946` は `target` を渡している — ディスク上の挙動は不変だが
   commit message に明記する
3. **`_inside_archive(path, data_root)` を抽出**し `1848` / `1895` の 2 箇所を 1 つにする
4. **`_same_archive_slot(intended, final)` を新設。** `1868-1872` のコメントは
  「collision guard が付けるのは `-N` サフィックスだけでディレクトリは変えない」と散文で主張している。
  これを `_collision_free_path` の直後の機械検査に変える — 散文の約束が検査になる

**3 つの拒否面は統合しない。** plan は**コード**を返し、各呼び出し元が自分の流儀で描く:
`_handle_remove_skill` は `Error: {code}: ` + `sys.exit(1)`、`_archive_named_skills` は stderr +
`_Outcome.ARCHIVE_FAILED`、`_record_archive` は全 outcome に監査行。

**監査行の非対称性が構造で説明できるようになる**: plan から学んだ拒否はプロンプトより前なので
記録すべき決定が無く行を書かない（`test_cli_skill_archive.py:897-908` が `not _audit(...)` を assert）。
apply から学んだ拒否は決定の後なので `_record_archive` が `rejected` 行を書く。
この一文を `_plan_archive` の docstring に置く — 分割が安全である理由そのもの。

### 正直な行数

`_handle_remove_skill` は 215 → ~175 行（−40）。だが `_ArchivePlan` / `_plan_archive` /
`_inside_archive` / `_same_archive_slot` / wrapper が ~110 行増え、`_archive_skill_file` の
108 行は消えず移動する。**モジュール全体では 30〜60 行増える見込み。**

成果物は行数ではない。**「このスキルは store を出てよいか、どこへ着地するか」を独立に決める
場所が 4 → 1 になる**こと、そして dry run / プロンプト / 移動が 1 つの frozen object を読むこと。

### 意識的に受け入れる挙動の境界 2 つ

1. **store 内の dangling symlink** — 現状 `target.is_file()` が symlink 検査より先に走るので
   `Error: skill not found:` が出る。ハンドラの `not target.is_file()` ゲートを plan より上に
   **残す**ことで現状の文言を保つ。テストが無いので「`MISSING` と冗長」と読まれる。
   そう読ませない 1 行コメントを置く
2. **`--delete` × 壊れた archive slot** — 現状 `destination_refusal` は `--delete` で無視される。
   plan の field にすることで保たれる。現状テストが無いので新規に 1 本 pin する

### dry run が予測できない 1 ケース（明示的に記録する）

`ARCHIVE_REFUSED_NOT_A_MOVE`（`.archive` が store へ symlink し返しているケース）は
**最終**宛先に依存し、最終宛先は content を要し、plan は意図的に content を読まない。
dry run はこれを予測できない。**省略せずテストに弱い形で符号化する** —
`dry.exit_code == 0 and real.exit_code == 1 and real.reason_code == "ARCHIVE_REFUSED_NOT_A_MOVE"`。
これが dry-run の約束の正確な境界で、現状どこにも書かれていない。

### テスト

**まず HEAD に対して characterization test を書いて緑にする**（`src/` を触る前）。
そうしないと新実装の記述になってしまう。

`tests/test_cli_skill_archive.py` に `class TestArchivePlanAgreesWithTheRun` を追加:

- **本体**: 9 つの store 状態（clean / archive_is_a_regular_file / archive_symlinks_to_store /
  source_is_a_symlink / source_already_archived / name_taken_same_content /
  name_taken_diff_content / missing / escapes_store）で parametrize し、
  同一状態の別 tmpdir に対して dry run と本番を回し、(exit code, reason code, 宛先) の一致を assert
- `test_the_purge_discriminator_is_computed_once` — `_inside_archive` を counting wrapper に
  差し替え、1 invocation につき 1 回であることを assert（`1848` / `1895` の重複が戻る回帰ガード）
- `test_the_collision_guard_never_changes_directory` — `_same_archive_slot` の単体 + `-2` 着地の実走
- `test_a_plan_is_never_applied_with_a_different_source` — `inspect.signature` で
  `_apply_archive_plan` に `source` / `data_root` 引数が無いことを assert。drift の再導入を止める
- `test_delete_ignores_an_unusable_archive_slot` — 境界 2 を pin
- `test_a_dangling_symlink_still_reads_as_not_found` — 境界 1 を pin

### 段取り（C 内部を 3 commit に割る）

1. characterization test を HEAD に対して緑に（`src/` 無変更）
2. `_inside_archive` + `_same_archive_slot` 抽出、3 箇所置換 — **これ単独で関数内重複が消える**
3. `_ArchivePlan` + `_plan_archive` + `_apply_archive_plan` 導入、`_archive_skill_file` を wrapper に。
   `_archive_named_skills` は無変更
4. `_handle_remove_skill` を plan 消費側へ書き換え（`literal` 渡し + 保持する 2 ゲート）
5. docstring 移送 — `1819-1832`（silent-failure CRITICAL）と `1843-1848`（security review MEDIUM）の
   インシデント記録を `_plan_archive` / `_inside_archive` へ。**これを落とすのが本当の回帰リスク**

### 触らないもの（参照コメントだけ足す）

`is_symlink` は 5 箇所ある: `248`（adopt write）/ `437`（プリミティブ）/ `688`（budget 計器）/
`1126`（`_resolve_adopt_plan` の batch abort、exit 2）/ `1833`（ハンドラ）。
このリファクタの対象は `437` と `1833` だけ。`688` と `1126` は**別の段・別の exit code** での
意図的な多層防御で、`test_cli_skill_archive.py:505` が「計器のコピーがループより先に発火する」ことを
pin している。統合すると exit-2 の全体 abort が per-item の exit-1 拒否に化ける。
`_plan_archive` を権威として名指すコメントだけ足す。

---

## Step 3 — B: `cli/adopt.py` の抽出

`cli/skill_archive.py`（新、~380 行）へ移す: `_ARCHIVE_*` 全 reason code、`_ArchiveResult`、
`_resolved_or_self`、`_skills_dir`、`_archive_dir`、`_writes_into_the_store`、
`_target_inside_data_root`、`_archive_destination_refusal`、`_archive_skill_file`、`_record_archive`。
`.approval`（`AuditSource` / `_log_decision`）と `..adapters.moltbook.config` への辺を継承する
（import-linter 上クリーン）。

`cli/remove_skill.py`（新、~290 行）へ移す: `_handle_remove_skill`、`_add_remove_skill_arguments`、
`remove-skill` の `CommandSpec`。`cli/__init__.py:15` の import 行と `:38` の
`*adopt.COMMANDS` の隣に `*remove_skill.COMMANDS` を足す（既存パターンに乗るだけ）。

`cli/adopt.py` は ~1400 行に。**モジュール docstring の脅威モデルを分ける** — archive 出口に
関する 2 bullet（D5 が `--archive-names` からしか入らない件、move の両端 containment）は
`skill_archive.py` の docstring へ移す。残す方には「出口は別モジュール」への参照を 1 行。

---

## Step 4 — D: **取り下げ**（レビュー時の誤り）

レビューでは「`remove-skill` だけ canonical な包含述語を使っていない」と書いた。**これは誤り。**

`_handle_remove_skill:1805-1812` の `target.is_relative_to(skills_dir)` と
`_target_inside_data_root`（`:101-130`）は**別の問いに答えている**:

| | ハンドラ `1805-1812` | `_target_inside_data_root` |
|---|---|---|
| スコープ | `skills/` | `data_root` 全体 |
| 読み | 参照先のみ | 参照先 **かつ** literal + resolved parent |
| exit | **2**（オペレータの打ち間違い、何も触らない） | 1（reason code つき拒否） |

`remove-skill ../other` の `other.md` は data_root の**内側**にあるので
`_target_inside_data_root` は True を返す — 逃走を捕まえない。exit 2 を出しているのは
ハンドラ側の狭いゲートの方。両方ともテストが pin している
（`tests/test_cli_adopt.py:191` `test_escape_attempt_rejected`、
`tests/test_cli_skill_archive.py:886` `test_a_skill_symlinked_out_of_the_store_is_still_an_escape`）。

**代わりにやること**: `1805-1812` に「これは `_target_inside_data_root` の複製ではなく
**より狭い**ゲートで、exit 2 は打ち間違いに割り当てられている」という 2 行コメントを足す。
将来のレビュー（この skill 自身を含む）が「canonical に寄せろ」と誤指摘するのを止めるため。
Step 2 の docstring 移送と同じ commit に含める。


## Verify

各 commit で `./.claude/verify.sh`（全体検査）。中身は format / lint / **type (pyright)** /
**arch (lint-imports)** / security (bandit) / shell (shellcheck) / markdown / deps (pip-audit) /
**test (pytest)** / eval baseline 鮮度（advisory）。

これに加えて、機械ゲートが**捕まえない**ものを手で確認する:

1. **`scripts/weekly-pipeline.sh` の never-selected 読み値** — テストが無く失敗が
   `NEVER_SELECTED_SCAN_FAIL` に飲まれる。Step 1 の後に 1 回実行し、JSON が出ることを目視
2. **CLI の実挙動** — `contemplative-agent report --skill-selection` と
   `contemplative-agent remove-skill --dry-run <name> --reason x` を実際に叩く
   （`--dry-run` は書き込まない。ADR-0012 系は non-TTY から呼ぶとき non-interactive フラグ必須 —
   `--help` を先に見る）
3. **CODEMAPS** — 分割は「機構」を変えないので CLAUDE.md の鮮度規約（ゲート・式・閾値・段構成）
   には当たらないが、モジュール表と統計が古くなる。**どのドキュメントテストも落ちない**
   （`docs_consistency_scan.py` は日付と commit 数しか見ない）ので明示的に直す:
   - `docs/CODEMAPS/core-modules.md:34`（`skill_selection.py` の行、LOC 2171）+ ヘッダの
     `Files scanned: 30 core modules`
   - `docs/CODEMAPS/architecture.md:24, 35-36, 625, 829` と freshness header
   - `docs/CODEMAPS/moltbook-agent.md:20`（`adopt.py (~1830L)`）, `:46`（`skill_selection.py (1058L)`
     — **既に 1112 行ずれている**）
   - `docs/CODEMAPS/INDEX.md:124-134` の統計表
   - `architecture.md:756` は `cli/adopt.py:323-326` を行番号で引いており、adopt.py の
     323 行目より上を触ると壊れる。参照を行番号から関数名に変える
   - `architecture.md:766` はテスト名 `test_skill_selection_reading_reaches_the_prompt_names_only`
     を引いているが実物は `…reaches_the_materials_names_only`（`tests/test_weekly_analysis_shell.py:246`）
     — **既に stale**。ついでに直す

## commit 構成

1 responsibility 1 commit（feedback `single-responsibility-per-artifact`）:

1. `feat(harness)`: skill 設置（`~/.claude` 側。CA repo とは別 repo なので独立 commit）
2. `refactor(skill-selection)`: A — 層分離（純粋な移動 + import 更新。意味変更ゼロ）
3. `test(archive)`: C-1 — characterization test を HEAD に対して緑にする（`src/` 無変更）
4. `refactor(archive)`: C-2 — `_inside_archive` / `_same_archive_slot` 抽出、3 箇所置換
5. `refactor(archive)`: C-3 — `_ArchivePlan` 導入 + `_handle_remove_skill` を plan 消費側へ。
   docstring 移送と D の「狭いゲート」コメントもここ（**唯一の意味変更を含む** commit）
6. `refactor(cli)`: B — `skill_archive.py` / `remove_skill.py` 抽出
7. `docs(codemaps)`: 上記の stale 修正

**この repo は main 直 commit → push**（feedback `push-workflow`。branch / PR を持ち込まない、
`gh pr create` の自動実行はしない）。git 操作の前に skill `git-workflow` を読む。

## Review chain

`implementation-chain` の `refactor` 種別:

- Refactor Clean（`/simplify` はこの中で）
- **Code Review**: built-in `/code-review`、effort は `high` を明示（無指定だと前回値を再利用する）
- Cross-Model Review: skill `codex-review`（`refactor` は C 判定 — C の意味変更があるので回す）
- Security Review: C。**Step 2 / Step 3 が archive 出口と containment 述語に触るので回す**。
  `security-reviewer` の Phase 3 は rule `common/security.md` の harness 脅威面を反証源に引くが、
  ここは CA repo なので CA 側の脅威モデル（`adopt.py` の module docstring、CLAUDE.md の
  「値層は脅威面ではない」）が反証源

決定論 Verify が全 PASS でも Review agent の起動は省略不可（feedback `review-agents-not-optional`）。

## RFC 起票

**しない。** レビュー由来の指摘だが、defer せずこのセッションで実行するため。
rule `task-tracking` の「diff の外なら HIGH 以上だけ起票」は先送りする指摘の規律であって、
実行する作業には当たらない。

## リスク

| リスク | 実体 | 緩和 |
|---|---|---|
| weekly チェーンの無言劣化 | `weekly-pipeline.sh:746-750` の import 失敗が `NEVER_SELECTED_SCAN_FAIL` に飲まれる。土曜まで気づかない | Step 1 直後に手動実行して読み値を目視。テストが無いこと自体を commit message に残す |
| `test_frozen_dataclasses.py` の path allowlist | 両方向検査なので同 commit で直さないと必ず落ちる | Step 1 のチェックリストに入れる（落ちるので silent ではない） |
| C の意味変更 | plan/apply 分割は dry-run と本番の一致を規律から不変条件に変える。reason code の出方・監査行・exit code が変わりうる | C を単独 commit にし、既存の reason code assert（裸文字列 9 箇所）を先に通す。新規テストで dry-run と本番の一致を pin |
| `test_skill_selection.py` 2303 行の扱い | 160 call site。分割まで欲張ると commit が読めなくなる | alias 追加で通し、ファイル分割は別 commit（やらなくてもよい） |
| インシデント記録の逸失 | C の docstring 移送で `1819-1832`（silent-failure CRITICAL の再現手順）と `1843-1848`（security review MEDIUM）を落とすと、検査が存在する理由が消える。**これが C の本当の回帰リスク** | 移送を独立ステップにして diff で目視。削除でなく移動であることを commit message に書く |
| レビュー自体の偽陽性 | thermo-nuclear は「構造的に見える」重複を強く押す。D は実際には別ゲートだった | **plan 段で 1 件ずつ実コードとテストに当てる**。今回はそれで 2 件（D 全体と C の 1 組）を落とせた |
