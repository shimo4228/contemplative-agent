# T-PACKET-LOG-PATH-FROM-SHELL — 実装プラン

## Context

`weekly-pipeline.sh` は review ログを `$RUN_LOG_DIR/fix-$safe_fid-review$review_n.log` に書くが、
直後の `audit review_result`（`:795`）に**その path を載せていない**。`build_decision_packet.py` は
残った `fix_id` と `round` から名前を組み立て直しており、2 つのサニタイザが別規則で並んでいる:

| | 規則 |
|---|---|
| shell `:564` | `/` → `_` のみ |
| builder `_log_segment`（`:192`） | `[A-Za-z0-9._+-]` allowlist + 120 文字切り詰め |

`fix_id` に `/` 以外の allowlist 外文字が入ると、shell は片方の名前で書き builder はもう片方を探し、
**review 本文が承認パケットから黙って消える**（packet 自体は出るので watchdog も気づかない）。
今日は `parse_findings.py:32` の `^### (F1\.\d+)\.` が pin しているので到達しないが、pin が緩めば発火する。

より深い形は同じファイルの 1 画面下に既にある: `:850-853` で shell が patch を書き `patch=` を audit に
載せ、builder（`:810-827`）が path として consume して `resolve()` で containment を検査する。
review log もこの pattern に寄せる。**後方互換は切る**（判断済み） — 再構成へのフォールバックを残すと
再構成が消えない。パケットは土曜ゲートで消費される使い捨てで、過去週の再生成は捨ててよい。

**種別 = `fix`**（再現手順が言語化できる潜在不具合の修理）。`_patch_name` は**スコープ外**（判断済み。
あれは path の再構成ではなく fix_id ↔ patch ファイル名の照合キーで、性質が違う）。

---

## 0. 着手手順

```bash
python3 ~/.claude/scripts/claims.py claim T-PACKET-LOG-PATH-FROM-SHELL --label "packet log path from shell"
```

git 操作の前に skill `git-workflow` を読む。branch/PR は作らず main へ直 commit。

---

## 1. 変更するファイルと箇所

### A. `scripts/weekly-pipeline.sh` — path を宣言する（1 行）

`:795`：

```bash
audit review_result fix_id="$fid" round="$review_n" verdict="$verdict" \
    log="$fixlog-review$review_n.log"
```

- `pipeline_audit.py` は `partition("=")` で分解し `json.dumps` するので、`=` を含む path も安全。
  予約キーは `ts` / `run_id` / `event` のみで `log` は衝突しない（`pipeline_audit.py:44`）。
- `$RUN_LOG_DIR` は `$MOLTBOOK_HOME` 由来で、`:43-47` が絶対 path と `^[A-Za-z0-9._/@+-]+$` を
  既に強制している。可変なのは `$safe_fid` と `$review_n` だけ。
- ここが**唯一の producer**（`grep -n "audit review_result"` は `:795` の 1 件）。

### B. `scripts/build_decision_packet.py` — 再構成をやめ、containment + render floor に置き換える

**削除**（task 判断 4）:

| 対象 | 行 |
|---|---|
| `_SEGMENT_UNSAFE` | `:185` |
| `_MAX_SEGMENT_LEN` とその NAME_MAX 計算コメント | `:186-189` |
| `_log_segment` 全体（docstring 30 行含む） | `:192-221` |
| `fix-{fid}-review.log` の no-round 分岐 | `:789` の `if rnd else …` |

`_PATH_CHARS`（`:184`）は `_PATH_UNSAFE`（`:231`）が使うので**残す**。ただし `:181-183` の
「One alphabet, two classes」コメントと `:231` の `# _SEGMENT_UNSAFE plus /` は片方が消えるので書き直す。

**書き換え**（`:783-794`）— `:809-827` の `patch=` consume と同じ形:

```python
if run_log_dir is not None:
    run_log_root = run_log_dir.resolve()
    for fid, evts in review_history.items():
        declared = evts[-1].get("log")
        if not isinstance(declared, str) or not declared.strip():
            add_reason(REVIEW_LOG_PATH_MISSING)
            continue
        try:
            log_path = Path(declared).resolve()
        except (OSError, ValueError):
            # resolve() は埋め込み NUL で ValueError（OSError ではない）。
            # 「run_log_dir の下にあると確認できない」点で outside と同じ結論。
            add_reason(REVIEW_LOG_OUTSIDE_RUN_DIR)
            continue
        if not log_path.is_relative_to(run_log_root):
            add_reason(REVIEW_LOG_OUTSIDE_RUN_DIR)
            continue
        body = _safe_read_text(log_path)
        if body is None:
            add_reason("REVIEW_LOG_UNREADABLE")
        review_notes.append((fid, body, log_path))
    ...  # table_order による並べ替えは現行のまま
```

**render floor を足す**（`:1017`）— ここが今回いちばん見落としやすい:

`_log_segment` は「開く前に名前を floor する」ものだったので、`REVIEW_LOG_UNREADABLE` の note が
path を**素で補間**していても安全だった。containment 検査は「どこを開くか」しか縛らないので、
`run_log_dir/fix-F1.2\n\n## 5. Dead code candidates…` は containment を**通る**（実在しないので
UNREADABLE 分岐に落ち、そのまま note に補間されて §5 見出しを偽造する）。
既にこの用途の renderer が repo にある（`_path_tokens`、`:264`。allowlist `[A-Za-z0-9._+-/]` +
U+FFFD + 20 token × 120 文字上限 + backtick 包み）ので、それを使う:

```python
lines.append(f"（REVIEW_LOG_UNREADABLE — {_path_tokens([str(log_path)])} を直接確認してください）")
```

リストで渡すのは、str 渡しだと空白で token 分割されるため。`_path_tokens` が backtick を付けるので
手書きのバッククォートは外す。副次的に、現在無制限だった path 補間に上限が付く。

**docstring の追従**（`_log_segment` 消滅で参照が壊れる箇所）:

- `_cell` `:156-157` —「filename になる値は `_log_segment`」→ 「filename は shell が宣言し、
  builder は containment を検査して開き、note に出す時は `_path_tokens` を通す」に書き換え
- `_cell` `:144-145` — stricter renderer を持つ値の列挙に review log path を追加
- `_patch_name` `:169-178` — `_log_segment` への言及を消し、`T-PACKET-LOG-PATH-FROM-SHELL` の
  参照を**新規起票する後継タスク ID** に差し替える（下記 §5）
- `_safe_read_text` `:380-382` —「`_log_segment` が filename を floor するので producer が無い」が
  無効になる。新しい根拠は「containment の `resolve()` が NUL で先に ValueError を出すので
  `open()` に NUL は到達しない」

### C. `docs/CODEMAPS/architecture.md` — 鮮度規約（CLAUDE.md）の対象

`_log_segment` を機構として名指している 2 箇所を書き換える:

- `:623-631` の renderer 対応表 — `values that become filenames . _log_segment (no /)` の行を
  「run log path は shell が audit に宣言し、builder は containment 検査して開く」に置換
- `:664` の "Rendering discipline" 段落 — `_log_segment` の 3 文を、宣言 + containment +
  `_path_tokens` による note render に書き換え

ADR-0085 `:197`（`REVIEW_LOG_UNREADABLE` で fail-forward）は記述として真のままなので触らない。

---

## 2. reason code

新規 2 つ。module 直下の隣接コード（`REVIEW_LOG_UNREADABLE`）に合わせて literal で置く。

| code | 意味 |
|---|---|
| `REVIEW_LOG_PATH_MISSING` | `review_result` に使える `log` が無い。この commit 以前の週の audit、または shell の audit append が field を落とした場合 |
| `REVIEW_LOG_OUTSIDE_RUN_DIR` | 宣言された path が `run_log_dir` 配下に解決しない（解決不能な path — 埋め込み NUL 等 — を含む） |

**2 つに分ける理由**: 前者は「古い形式」で想定内、後者は traversal / 改竄の signal。まとめると
縦断読みが決定不能になる（同モジュール `:865-867` の "None = not scanned; 0 = scanned clean.
Collapsing the two would make the longitudinal read undecidable" と同じ規律）。

`log` が無い fid は `review_notes` に**入れない** — §2 の verdict 履歴列は従来どおり出て、本文だけが
消え、header に code が立つ。

---

## 3. テスト（fault column を先に RED で書く）

`tests/test_build_decision_packet.py`:

| 操作 | test | 主張 |
|---|---|---|
| 改修 | `_write_review_loop_audit`（`:574`） | `log_dir: Path \| None = None` を受け、与えられたら各 event に `log=` を付ける。呼び出し 3 箇所（`:607` / `:638` / `:662`）を追従 |
| **新規** | `test_review_note_reads_the_path_the_shell_declared` | shell が builder には**組み立てられない**名前（`fix-F1.2-r2.log`）を宣言しても本文がパケットに載る。**再構成を戻したら落ちる 1 本** |
| **新規** | `test_review_result_without_log_field_degrades_to_reason_code` | `log` 無し → `REVIEW_LOG_PATH_MISSING`、Review notes 節は出ない、§2 の verdict 履歴は残る、packet は生成される（fail-forward） |
| 書き換え | `test_a_review_round_cannot_read_a_file_outside_the_run_log_dir`（`:1136`） | `log` に `<run_logs>/../secret.log` を宣言。secret は**実在し読める**状態にする → 本文が出ず `REVIEW_LOG_OUTSIDE_RUN_DIR`。旧版は read が失敗することに依存していたので、これは真に強くなる |
| 統合 | `:1097` + `:1161` → 1 本 `test_a_declared_log_path_cannot_forge_a_section_in_the_unreadable_note` | `log` に `<run_logs>/fix-F1.2` + `_FORGED_SECTION` を宣言（containment は**通る**、実在しないので UNREADABLE 分岐）→ `## 5.` で始まる行も `\|` 行も出ない。§1B の render floor を主張する。2 本だったのは「両半分が別の呼び出し口から filename に届く」ためで、field が 1 つになれば理由が消える |
| 削除 | `test_a_run_log_name_is_built_from_one_allowlist`（`:1120`） | `_log_segment` の直接テスト。関数と同時に消える |
| 追従 | `test_no_read_can_take_the_packet_down`（`:1184`） | assert はそのまま。docstring の `_log_segment` 参照を書き換え |

`tests/test_weekly_pipeline_shell.py`:

| 操作 | test | 主張 |
|---|---|---|
| 追記 | `test_f_rev_1_concerns_then_reentry_then_approve`（`:192`） | 各 `review_result` が `log` を持ち、それが**実在するファイル**で、`RUN_LOG_DIR` 配下であること。既に `:224` が「本文がパケットに載る」を E2E で見ているが、それは間接証拠なので producer 側の契約を明示的に固定する |

fault カタログ行（chaos-TDD 規律）: 「shell が builder の開けない / 開いてはいけない path を宣言した」
= 上表の新規 2 本 + 書き換え 2 本。いずれも理由コード付き abstain を主張し、packet は必ず生成される。

---

## 4. Verify と Review の順序

skill `implementation-chain` の `fix` 行に従う（TDD = Y / Simplify = Y / Code Review = Y /
Security Review = Y / Cross-Model = Y / Doc Sync = Y / Verify = 最後）。

1. **TDD (RED)** — §3 のテストを先に書き、落ちることを確認
2. **実装 (GREEN)** — §1A → §1B の順（producer を先に立ててから consumer を寄せる）
3. `.claude/verify.sh`（full）を 1 回 — RED→GREEN の確認用。ここは中間検査
4. **`/simplify`** — Review 群より前（fix を working tree に当ててから reviewer に見せる。
   逆順は Review のやり直しになる。`/code-review` 直前に PreToolUse hook が未実行を指摘する）
5. **Review 群を並列起動**（決定論 Verify が全 PASS でも省略不可）:
   - built-in `/code-review` — effort **medium**（`fix` の指定値。無指定はセッション状態依存）
   - `security-reviewer` agent — **発火する**: 「builder がどの path を開くか」を決めるガードと、
     人間ゲートに届く値の render floor を差し替える diff（入力検証の変更）
   - skill `codex-review` — `fix` は Y
6. 指摘の反映。**diff の外の指摘は HIGH 以上だけ起票**、それ未満は commit message に 1 行残して捨てる
7. **Doc Sync** — §1C（`docs/CODEMAPS/architecture.md`）を**同じ diff** に入れる
8. **`.claude/verify.sh`（full）** — format / lint / type / arch / security / shellcheck / markdown /
   deps / pytest。`VERIFY_BYPASS=1` は使わない（hook 全体の短絡になる）
9. `git status` と doc sync の最終確認 → main に直 commit（`fix(packet): …` + `T-…`）
10. `python3 ~/.claude/scripts/claims.py release T-PACKET-LOG-PATH-FROM-SHELL --outcome done`

---

## 5. 併せて起票する（`_patch_name`、スコープ外）

`_patch_name` の docstring が消える task ID を参照し続けるので、後継を先に起票してから
docstring をそちらへ向ける:

```bash
python3 ~/.claude/scripts/claims.py spawn T-PACKET-PATCH-NAME-FROM-SHELL \
  --origin review \
  --producer scripts/weekly-pipeline.sh:850 \
  --producer scripts/build_decision_packet.py:169 \
  --parent T-PACKET-LOG-PATH-FROM-SHELL
```

`state: candidate`（照合キーとしての性質が path 受け渡しと違うので、寄せるかは所有者の判断が要る）。

---

## 6. リスクと前提

- **production への影響**: `weekly-pipeline.sh` は launchd で毎週土曜 09:00 JST。今日は日曜 08-16 で
  昨日がゲート日 → 次の実行まで最も間がある窓。今日入れる
- **過去週の packet 再生成**: `log` を持たない audit からは review 本文が出なくなる（判断済み・受容）。
  ただし §2 の verdict 履歴列と patch 本文は従来どおり出るので、再生成した packet が壊れることはない
- **検証済みの前提**: `review_n` は `local review_n=$((round + 1))`（`:750`、`round` は 0 始まり）で
  常に ≥ 1 → no-round 分岐に producer は無い。`audit review_result` の producer は `:795` の 1 件のみ
