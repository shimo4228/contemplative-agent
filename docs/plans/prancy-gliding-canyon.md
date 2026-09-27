# 北極星の言語化 — ADR-0080 追補 + CLAUDE.md 直置き + surprise 計器復元の RFC 起票

## Context

北極星（ADR-0080）は現在、プロジェクト CLAUDE.md に言及ゼロで、セッションへのロードが
著者の private auto-memory の索引 1 行に依存している（ralph / 無人 weekly / subagent には
載らない）。また 2026-08-26 の議論で北極星に追加すべき内容が 2 つ決まった:

1. **A の形**（著者決定）: 承認の権限は人間に残り、負荷がゼロに近づく。Moltbook との
   フィードバックループ（episode → patterns → skills → selection → 生成 → Moltbook）が
   著者と Claude Code の関与なく自己調節して回ることが**機構層の完成条件**。
   ゲートの溶解（B案）は採らない — AAP の attribution 思想と整合。
2. **代謝の質**（著者決定）: 頻度単独では価値を判定できない。抽出・採用は複数軸
   （例: 新規性・重要度・環境の反応 — 列挙は固定しない）で見分けられること。
   単一スカラーへの還元は既存ベンチマーク非還元条項と同じ理屈で禁止。
   判定者の選定は下流の設計に残す（重要度 LLM 採点は ADR-0056 で退役済みの前科）。

併せて、ADR-0097 D1 で撤去された surprise 計器の復元を RFC 起票する（撤去理由
「名指しの消費者がいない」が、上記 2 の消費者名指しで消えたため。著者確認済み:
「あれは必要だったよ」+ AskUserQuestion で「RFC 起票まで含める」選択）。

## 変更ファイル

### 1. ADR-0080 日付つき追補（en + ja を**同一 commit で**）

- `docs/adr/0080-north-star-layered-end-state.md`（150 行）と `.ja.md`（134 行）
- 形式は既存 Form B 精例に従う:
  - `## Amendment (2026-08-26) — <短い題>` を **Consequences の後・References の前**に追加
    （0053:197 / 0068:141 の配置精例。ja は 0087:305 精例で `## 追補 (2026-08-26) — <題>`）
  - Status 行を `accepted (amended 2026-08-26 — see Amendment)` に（README.md:162 の
    公認語彙 `accepted (amended YYYY-MM-DD)`。**head は `accepted` のまま**なので
    `tests/test_adr_status_consistency.py` の 5 面一致検査と index は無変更で通る）
  - 冒頭 Status 付近に forward pointer 1 行（0068:11-13 精例）
- 追補の内容（3 点）:
  - (a) 機構層完成条件の具体化 = A の形（上記 Context 1 の文言。既存の
    「止まるのが完成」と矛盾せず拡張。「毎週の人間修理・毎週 40〜50 件の人間濾過を
    要する間は機構層は未完成」を操作可能な判定として書く）
  - (b) 代謝の質の条項（上記 Context 2。軸は「例えば」で開き、Emptiness 条項と
    整合させる。単一スカラー還元禁止を明記）
  - (c) 旧 ledger 参照の修正: EN L126 / JA L112 の「task ledger (T-ENDSTATE-TERM)」は
    移送済み → `rfcs/0006-heartbeat-end-state-criteria.md` への日付つき注記
- **やらないこと**: Decision 本文の書き換え（追補セクションからの参照のみ）、
  index の Status/Date セル変更（0018/0068/0069 精例: 触らない）

### 2. CLAUDE.md 北極星セクション — CYCLES.md の節を**移設**する（複製しない）

- 著者判断（2026-08-26）: ポインタ + 要約の第 3 面を作ると読まれない上に二重管理に
  なるので、**CYCLES.md:70-86 の north-star 節の中身をそのまま CLAUDE.md へ移す**。
  面の数は「ADR-0080（正本・rationale）+ CLAUDE.md（操作面・毎セッション必ずロード）」
  の 2 つになる
- 置き場所: `## 開発原則`（L69）の直前に新 `## 北極星（north star）` セクション
- 中身: CYCLES 節の層別 5 行を日本語化（CLAUDE.md は日本語 — 言語方針 L89）+
  今回の追補 2 条項（A の形・代謝の質）+ ベンチマーク非還元の 1 行 +
  「正本は ADR-0080」リンク。新機構・機構変更の審査に使う旨 1 行
  （「機構層は修理か、能力動機の拡大か」）

### 3. docs/CYCLES.md — north-star 節を 1 行ポインタに縮退

- L70-86 の節本体を削除し、「North star: see CLAUDE.md (operative, ja) /
  ADR-0080 (canonical)」の 1-2 行に置き換え。FRESHNESS ヘッダ（L1-5）の method 行と
  日付を更新
- ADR-0080 EN L112-113 の「CYCLES.md gains a short North-star section」という既存
  Consequence とズレるので、追補 (c) にこの移設も 1 行注記する

### 4. graph.jsonld の ADR-0080 node

- L2252-2270 の `description` が層別条件を全文 restate しているので追補内容を反映
  （探索で「amendment の substance 変更はここが silent drift する」と特定済み）。
  `status` は `"accepted"` のまま（head 一致検査）

### 5. llms-full.txt（L311-316 の ADR-0080 節）

- 「What counts as finished」の段落に自律代謝 + 代謝の質を 1-2 文追加

### 6. RFC-0016 起票: surprise 計器の復元

- **skill `rfc-writer` を invoke して起票する**（採番・様式・index 行の正本はそこ）
- 骨子: state `draft` / origin idea（著者指示 2026-08-26）。premise: ADR-0097 D1 が
  `core/insight_surprise.py`（267 行）+ 関連を commit `47616da` で撤去（導入は
  `e5dec38`、ADR-0096 D10-12）。撤去理由は「名指しの消費者がいない」であり計器の
  欠陥ではない。消費者が北極星追補（代謝の質・複数軸）で名指しされたため、
  ADR-0097 D1 の**部分 supersede 候補**として復元を提案。スコープは**計器のみ** —
  gemma worth gate（3 回実測で全件 yes、refuted）は復元しない
- `python3 ~/.claude/scripts/claims.py spawn --origin idea` で系譜記録
- `rfcs/README.md` の index に 1 行追加

## 実装順序と commit

1. ADR-0080 追補（en → ja）を書く
2. **agent `adr-reviewer` を起動**（ADR 実質改稿後の必須レビュー。0069 追補も
   同精例 `0ce5430` で reviewer 指摘を反映している）→ 指摘反映
3. CLAUDE.md / CYCLES.md / graph.jsonld / llms-full.txt を書く
4. RFC-0016 を rfc-writer 経由で起票
5. `.claude/verify.sh`（full）を実行 — 効くゲートは markdownlint-cli2（blocking）と
   pytest（`test_adr_status_consistency.py` の 5 面検査 + graph.jsonld の JSON parse）
6. **著者通読 → GO**（値層・worldview 文書なので人間ゲート必須）
7. commit 2 本、**選択 staging で**:
   - `docs(adr-0080): 追補 — 自律代謝の完成条件と代謝の質` （ADR en/ja + CLAUDE.md +
     CYCLES + graph + llms-full。en/ja 同一 commit は docs_consistency_scan の
     enja_drift 検査要件）
   - `rfcs: RFC-0016 surprise 計器の復元を起票`
   - ⚠ **working tree に本日の triage 照合編集（rfcs/0001〜0015 の 15 ファイル）が
     未 commit で残っている**。これは土曜 weekly-gate の担当なので**巻き込まない** —
     `git add` は対象ファイルを明示列挙する
8. push（git-workflow skill 作法: 1 call 1 コマンド、push は sandbox 無効化）

## Verification

- `.claude/verify.sh` full が PASS（特に markdownlint と ADR status 5 面一致）
- `grep -n "北極星" CLAUDE.md` がセクションを返す
- en/ja が同一 commit に入っていること（`git show --stat` で確認）
- rfcs/README.md index と RFC-0016 の state frontmatter 整合
- adr-reviewer の指摘が反映済みであること

## スコープ外（明示）

- surprise 計器の復元**実作業**（RFC 起票まで。実装は別セッションで dispatch）
- insight 抽出機構（novelty gate 較正・満腹信号）の設計・実装 — 北極星確定後の別タスク
- RFC-0010 / RFC-0013 の採否（Slack digest で別途回答待ち）
