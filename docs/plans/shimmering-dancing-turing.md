# /simplify で見送った 3 件（+ 適用済み quality 分の commit）

## Context

2026-08-16 に `/simplify 0cfe6f2..HEAD`（2026-08-14 週次レポート以降の 22 commit）を 4 エージェント
並列で実行した。quality 軸 16 件は適用済みだが **working tree に未 commit のまま残っている**。
残り 3 件は「quality でなく挙動・セキュリティ・構造の話」として起票され、`/simplify` では適用を
見送った。この plan はその 3 件を、混ざらない commit に分けて閉じる。

**この 22 commit 自体は既に code-reviewer / security-reviewer / codex-review を通過済み。**
以下の Review はこの plan が新しく作る hunk だけを対象にし、22 commit を回し直さない。

決定済み（本セッションで確定）:

| 件 | 決定 |
|---|---|
| T-CONTROL-CHAR-BOUNDARY | 実施。chokepoint へ移す |
| T-WEEKLY-ANALYSIS-SESSION-SCOPE | 実施。2 セッションに **ツール 0 個**（`--tools ""`）を与える |
| T-SIMPLIFY-DEFERRED-STRUCTURE (a) subprocess 境界 | **見送り** — timeout 境界の喪失に見合わない |
| T-SIMPLIFY-DEFERRED-STRUCTURE (b) 大関数 2 つ | **両方採用**。挙動保存 refactor として別 commit |

---

## Commit 0 — 適用済み quality 分を先に出す

現 working tree の 18 ファイル（`scripts/_md.py`, `scripts/tasks.py`,
`scripts/ledger_condition_scan.py`, `src/contemplative_agent/**`, `tests/**`）+ 新規
`scripts/_audit.py` / `docs/evidence/adr-0094/` は `/simplify` の quality pass の成果物。
以降の 4 commit がこれと混ざらないよう、**最初に単独で commit する**。

- `scripts/_md.py::printable` — 制御文字クラスの単一所有者（以降 Commit 1 (b) が使う）
- `scripts/_audit.py` — `audit.jsonl` の行文法の単一所有者

Verify を通してから commit。以降の 3 件は全てこの tree の上に乗る。

---

## Commit 1 — T-CONTROL-CHAR-BOUNDARY

制御文字の無害化が **通る経路の外**にある。2 箇所あるが「chokepoint をどこに置くか」という
1 つの判断なので 1 commit。

### (a) `scripts/tasks.py` — projection への唯一の入口へ移す

現状 `_CONTROL_RE` ガードは `write_store:839` にあり、そこへ到達するのは `cmd_age` と
一度きりの migration だけ。手編集した store → `load_store` → `render_ledger` → `TASKS.md` →
`parse_watches` は素通りする。`write_store` の docstring 自身が穴を認めている。

- `_CONTROL_RE`（現 `tasks.py:1026`）を `_TASK_ID_RE`（`:129`）の隣へ移動 — `render_row` は
  `:606` にあり、定義が後ろだと使えない。`_one_line`（`:1030`）は import 位置に依存しない
- `render_row`（`:606`）に検査を追加。`_TASK_ID_RE` の拒否と `_watch_span_problems` が既に並ぶ
  場所で、cells を組む直前。対象は `state` + `summary` / `condition` / `detail`（`write_store`
  と同じ 4 フィールド。`state` セルは escape されないので同じ扱いが要る）
- **`printable` に寄せない** — `str.isprintable()` は Cn（未割当）も弾く superset で、新しい
  Unicode の絵文字を古い Python が拒否する。表示系の過剰拒否は安全側だが、**書き込み拒否では
  実損**。`_CONTROL_RE` のまま移す
- `write_store` 側の検査は安価な多重防御として残し、docstring の
  「**What it still does not cover**」段落（`:857-864`）を書き換える — chokepoint が移った今、
  あの記述はもう真でない

**空振り検査は実施済み**（着手条件を満たす）:

```
store files: 124 / offending rows: 0 / render OK, 119,282 chars
```

live store 124 件のうち `_CONTROL_RE` に当たる本文は **0 件**。今日この拒否を足しても
render できている行は 1 つも落ちない。

### (b) `scripts/build_decision_packet.py` — 構造的な床へ移す

`_cell`（`:109`、36 箇所から呼ばれる packet の構造的な床）が C0 / C1 / DEL / bidi / zero-width を
通すので、各 producer が個別に埋め合わせている。**この形は既に一度失敗している** —
`_printable` の docstring が「以前の版は `detail` だけが該当と書いており、そのせいで `target` が
無害化されずに §10 へ到達していた」と記録している。

- `from _md import printable` を追加。bare import は `_scan` / `_md` と同じ前例で成立する
  （`python3 scripts/<name>.py` と `tests/test_build_decision_packet.py:25` の `sys.path.insert`
  の両方で解決する — 確認済み）
- `_cell` の `splitlines()` join の**後**、`\\` / `|` の escape の**前**に `printable` を挟む
- `_title_cell`（`:251`）は `_TITLE_UNSAFE.sub(repl, _cell(...))` の順を
  **`_cell(_TITLE_UNSAFE.sub(repl, ...))` に入れ替える**。そうしないと `_cell` が先に空白へ
  潰すので、制御文字に対する U+FFFD の「何かが剥がされた」可視マーカーが消え、黙って空白に
  なる。入れ替えれば見出しは U+FFFD マーキングを保ち、`_cell` は残り全部の床として効く
- `_path_tokens` / `_unrecognized_verdict` の allowlist はそのまま（境界から多重防御へ降格
  するだけで消さない）

### テスト

- `tests/test_tasks.py` — store の `detail` に U+2028 を入れた task が `render_ledger` で
  `MalformedTask` になり、メッセージが task id を名指しすること。ADR-0077 の fault column
- `tests/test_build_decision_packet.py` — `_cell` が U+202E / U+200B / DEL / C1 / U+2028 を
  中和すること、および `_title_cell` が制御文字に U+FFFD を残すこと

---

## Commit 2 — T-WEEKLY-ANALYSIS-SESSION-SCOPE

無人チェーンのセッション境界が **ファイル単位でゲートされており**、同じチェーンの 2 セッションが
その外にいる。`weekly-pipeline.sh:367` が stage 1 として `bash "$SCRIPTS/weekly-analysis.sh"` を
起動し、そこから `weekly-analysis.sh:424`（レポート生成）と `:486`（翻訳）の 2 つの無人セッションが
出る。どちらも permission フラグを一切持たない（論理行を join すると
`claude -p --system-prompt "$SYSTEM_PROMPT" --output-format text` のみ）。

機構 6（`weekly-pipeline.sh:64`）により、この 2 つは operator の ambient allow rule 106 件と
`additionalDirectories`（無関係な 3 project）を読み込む。

### 与える spec: ツール 0 個

両セッションとも stdin で受けて stdout へ吐くだけで、ファイルを 1 つも触らない
（入力は shell が全部インラインに埋め込み済み、出力はリダイレクト）。ADR-0040 も
「`weekly-analysis.sh` の LLM は source / ADR / CODEMAPS へのアクセスを持たない」と設計意図として
宣言している。`claude --help` は `--tools ""` を「Use "" to disable all tools」と明記。

```
--permission-mode manual --tools "" --strict-mcp-config --setting-sources project
```

deny list は付けない — ツール 0 個に対して拒否するものが無く、`weekly-analysis.sh` は自前 plist
（`config/launchd/com.moltbook.weekly-analysis.plist`）で単独起動もするので `READONLY_DENY` を
共有するには変数を別ファイルへ切り出すことになり、drift か diff 拡大を招く。
`--setting-sources project` が user hooks を落とす件（`weekly-pipeline.sh:64` が stage 2 で Read
deny に置き換えた埋め合わせ）は、Read ツールがそもそも存在しないので補償不要。

### `scripts/weekly-analysis.sh`

- レポートセッション（`:424`）— 上記 4 フラグを追加
- 翻訳セッション（`:486`）— `run_claude_translate()` を廃し、`weekly-pipeline.sh:323` の
  `with_timeout()` と同じ helper を採る。現状の関数は本体に `claude -p "$@"` を 2 回持つので
  **フラグを持つ論理行が 1 本も無く**、行ベースの gate から見えない。`with_timeout` にすれば
  呼び出し側の 1 行に spec が乗る

### `tests/test_weekly_pipeline_session_scope_shell.py` — gate をチェーン全体へ

sweep の docstring は「a sixth session added later cannot ship without one」と主張しているが、
**今日すでに 2 セッションについて偽**であり、それを言う機構が無い。不変条件は「このファイル内の
全行」ではなく「weekly チェーンの全無人セッション」。

- `SCRIPT` → `CHAIN_SCRIPTS = (weekly-pipeline.sh, weekly-analysis.sh)`。`_invocations()` は
  `(script, logical_line)` を全スクリプトから返す
- **C-SCOPE-0（新規）** — `weekly-pipeline.sh` を走査して `bash "$SCRIPTS/*.sh"` で exec される
  スクリプトを列挙し、その全てが `CHAIN_SCRIPTS` に入っていることを assert する。ハードコードした
  tuple は次に増えたとき黙って外れるが、この形なら **3 本目が追加された時点で gate が落ちる** —
  docstring の主張を人手でなく機構で真にする部分
- C-SCOPE-1 — 5 → 7 セッション。`--tools` の値の非空 assert を外す（`_flag_value` は flag 不在で
  既に raise するので検査は弱まらない。空文字は「意図的にゼロ」という最強の宣言）。
  `--disallowedTools` はツール集合が非空のときだけ要求する
- C-SCOPE-1b — 2 エントリ追加。安定トークンは `$USER_PROMPT` /
  `$TRANSLATE_SYSTEM_PROMPT`（どちらも pipeline 側の行に出ない）、期待値は `("", None)`
- C-SCOPE-4 — `--allowedTools` を持たない invocation を skip する（現状は `_flag_value` が raise）
- C-SCOPE-8 — 空 spec も probe に加え、`--tools ""` が実 CLI でツール 0 個に解決することを assert
  する。この commit の最強の主張に対する drift alarm。`live_cli` マーカー
- module docstring — 「five sessions」「a sixth session added later」を訂正し、C-SCOPE-0 が
  その主張を支える機構であることを書く

### 実 CLI での確認（ship 前に必須）

`--tools ""` はドキュメント上の値だが**この build で実際にどう解決するかは未測定**。
C-SCOPE-8 の probe（`--output-format stream-json` の `system`/`init` イベント、モデル呼び出し前・
無認証・~0.8s）で resolved set が空であることを確認してから ship する。空 spec を CLI が拒否する
場合は方針を再検討する（その場合のみ相談）。

---

## Commit 3 — T-SIMPLIFY-DEFERRED-STRUCTURE (b-1): `_handle_adopt_staged`

`src/contemplative_agent/cli/adopt.py:571-873`、303 行 / 39 分岐。挙動保存の refactor。

既にある seam で割る:

1. 引数の突き合わせ / staged item のロード
2. per-item dispatch（outcome enum を返す）
3. outcome tally からのサマリ描画

exit code 意味論の「2 つの rough edge」を説明する 9 行の docstring 段落は分岐の相互作用の産物
なので、割ったあと縮める。テスト被覆は厚いので、**テストを 1 行も変えずに通ること**が挙動保存の
主張になる。

> 補足（判断材料として記録）: `ruff` の `select` は `["E4","E7","E9","F","B","I","T20","UP"]` で
> **C901 は入っていない**。台帳が引く「C901: 36」は ad-hoc 計測であってゲート違反ではない
> （`--select C901` を手で当てると repo 全体で 26 件出る）。つまりこの refactor の駆動力は
> 可読性であり、「次に指摘が来ると hunk N+1 として刺さる」という将来コストの回避。

---

## Commit 4 — T-SIMPLIFY-DEFERRED-STRUCTURE (b-2): `build_packet`

`scripts/build_decision_packet.py:390-1283`、894 行。§ 単位で割る（`_render_section_*` 群 +
`build_packet` は組み立てだけ残す）。同じく挙動保存で、テスト無改変での pass が主張。

Commit 1 (b) が同ファイルの `_cell` を触るので、**必ず Commit 1 の後**に行う（先にやると
`_cell` の diff が 894 行の移動に埋もれてレビュー不能になる）。

---

## 進め方

各 commit の着手前に claim を取る:

```bash
python3 ~/.claude/scripts/claims.py claim T-CONTROL-CHAR-BOUNDARY --label "chokepoint へ移す"
# 完了時
python3 ~/.claude/scripts/claims.py release T-CONTROL-CHAR-BOUNDARY --outcome done
```

`T-SIMPLIFY-DEFERRED-STRUCTURE` は candidate → 採否が決まったので、(a) 見送り / (b) 採用を
タスク本文に書き戻してから claim する。

## Doc sync

- `docs/CODEMAPS/architecture.md` の Data Flow — Commit 2 は無人チェーンのゲートを狭める変更
  なので、鮮度規約（CLAUDE.md）により同 PR で更新する。直前の `0d5e3ac` が同じことをしている
- Commit 1 (a) は projection への入口に新しい拒否を足すので、同じ節に 1 行

## Review

新しい hunk だけを対象に（22 commit は回し直さない）:

- Commit 1 / 2 — `code-reviewer` + `security-reviewer` + `codex-review`
- Commit 3 / 4 — `code-reviewer` + `codex-review`（挙動保存 refactor、新しい I/O 面は無い）

## Verify

```bash
uv run pytest tests/ -q                     # 各 commit 前にフォアグラウンドで 1 回
uv run ruff check src/ tests/ scripts/
uv run lint-imports
uv run pyright
.claude/verify.sh
```

`verify.sh` は eval baseline の staleness（`prompt_templates_sha256`、`d190f4f` 由来）で
**exit 1 のまま**。既知かつ本変更と無関係なので `VERIFY_BYPASS=1` を使い、commit message に
その旨を明記する（直前の `1921b01` と同じ扱い）。

Commit 2 だけ追加で:

```bash
uv run pytest tests/test_weekly_pipeline_session_scope_shell.py -q      # live_cli 含む
uv run pytest tests/test_weekly_analysis_shell.py -q                    # macOS のみ
```

Commit 1 (a) の空振り再検査（拒否を入れた後、live store が全件 render できること）:

```bash
python3 scripts/tasks.py render --dry-run 2>&1 | tail -3   # 実フラグは --help で確認
```
