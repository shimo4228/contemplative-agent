---
name: weekly-gate
description: 土曜の単一承認セッション（ADR-0085 / ADR-0098）。無人 weekly チェーンの成果物（weekly-{end-date}-findings.md と各計器の per-week JSON）を直接読み、値層の承認（insight staging の adopt-staged / identity / never-selected の退役）、dead code の削除判断、gate メトリクスの記録までを 1 セッションで行う。Use when the user says 「週次の承認をする」「週次のゲートをやる」/weekly-gate, or on Saturday after the unattended chain has run. NOT for — code 修理の適用（ADR-0098 で廃止。修理は task-triage loop の担当）、診断起票 candidate の採否（→ triage digest）。
origin: shimo4228
user-invocable: true
---

# Weekly Gate — 土曜の単一承認セッション

無人チェーン（`scripts/weekly-pipeline.sh`、ADR-0085 / ADR-0098）は **commit も adopt も
しない**。このセッションが週 1 回の人間ゲート。ADR-0098 以降、チェーンは patch を作らず
（修理は診断が台帳へ起票 → task-triage loop が担当）、decision packet も無い —
このセッションが findings と計器 JSON を**直接読む**。

## 手順

### Step 0. Pipeline status と欠報チェック（必須・最初）

3 点セット。それぞれ別の問いに答える — 片方をもう片方の代わりにしない。

#### (a) 欠報チェック（決定論・最初）

`{end-date}` の期待成果物を ls で確認し、**無いものを欠報として最初に報告**する。
欠報は「候補なし」ではない — 計器が沈黙した週は、その節を「対象なし」と読んではならない
（packet builder が持っていた fail-forward の欠報明記は、この 1 手順に縮退した。ADR-0098）:

```text
$MOLTBOOK_HOME/reports/analysis/weekly-{end-date}.md          # A-E レポート
$MOLTBOOK_HOME/reports/analysis/weekly-{end-date}-findings.md # 診断
$MOLTBOOK_HOME/pipeline/value-layer/value-layer-{end-date}.json
$MOLTBOOK_HOME/pipeline/dead-code/dead-code-{end-date}.json
$MOLTBOOK_HOME/pipeline/docs-consistency/docs-consistency-{end-date}.json
$MOLTBOOK_HOME/pipeline/never-selected/never-selected-{end-date}.json
```

#### (b) 承認対象 run の完走確認（audit log が正）

`$MOLTBOOK_HOME/logs/weekly-pipeline-audit.jsonl` から当該 run の全 `stage_result` と
`chain_end` を確認する（run_id は `weekly-{end-date}-HHMMSS`。同一週の再実行がありうるので
最新 run_id を採る）:

```bash
python3 - "${MOLTBOOK_HOME:-$HOME/.config/moltbook}/logs/weekly-pipeline-audit.jsonl" {end-date} <<'EOF'
import json, sys
path, end_date = sys.argv[1], sys.argv[2]
events = [json.loads(l) for l in open(path)]
prefix = f"weekly-{end_date}-"
run_ids = sorted({e["run_id"] for e in events if e.get("run_id", "").startswith(prefix)})
if not run_ids:
    sys.exit(f"NO RUN for {end_date}: audit has no run_id {prefix}* (chain never started)")
run_id = run_ids[-1]
ev = [e for e in events if e.get("run_id") == run_id]
extra = f"  (earlier attempts: {', '.join(run_ids[:-1])})" if len(run_ids) > 1 else ""
print(f"run_id: {run_id}{extra}")
bad = []
for e in ev:
    if e["event"] == "stage_result":
        note = f"  reason={e['reason']}" if e.get("reason") else ""
        print(f"  stage {e['stage']}: {e['result']}{note}")
        if e["result"] != "ok":
            bad.append(f"stage {e['stage']}={e['result']}")
end = [e for e in ev if e["event"] == "chain_end"]
if end:
    print(f"  chain_end: {end[-1]['result']}  reasons={end[-1].get('reasons', '-')}")
    if end[-1]["result"] != "ok":
        bad.append(f"chain_end={end[-1]['result']}")
else:
    bad.append("chain_end MISSING (run died mid-chain)")
print("VERDICT:", "PRESENT BEFORE DECIDING -> " + "; ".join(bad) if bad else "run completed clean")
EOF
```

`chain_end` が無い（途中死）、または `result != ok` の stage がある場合は、**承認より先に**
該当行をユーザーに提示する。`skipped` は fail-forward の正常系でもある — reason code と
ともに提示し、(a) の欠報と照合して「対象なし」なのか「生成失敗」なのかを切り分ける。

#### (c) 周辺ジョブ（distill / insight / backup）

`$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md` を読む。❌ があれば**承認より先に**提示する。

**誤読注意**: weekly 系 2 行（weekly-report / weekly-findings）は、**土曜午前
（締切 Sat 12:00 / 13:00 より前）は前週の成果物を映すのが正常**（watchdog の
`anchor_sat()` は締切前は前週を anchor する設計）。「✅ ばかりだから当日 run も健全」と
読まない — 当日 run の完走は (b) のみが正。

### Step 1. Decision inventory の提示

(a) で読めた成果物から、今週の判断対象を件数とスコープで明示列挙する
（human-gate.md の 1 作業 1 ゲート）:

- insight staging: `ls "$MOLTBOOK_HOME/.staged/"*.md` の件数（identity.md が居るか含む）
- value layer cadence: value-layer JSON の identity / constitution due と rules 読み値
- dead code: JSON の candidates 件数
- docs consistency: JSON の findings 件数
- never-selected: JSON の strict / dormant / below_floor 件数
- **診断起票の candidate**: 今週 `.notes/tasks/` に増えた `state: candidate` の件数 —
  **本セッションでは採否しない**（task-triage digest の担当。ここでは存在の報告のみ）

findings.md（F1/F2/F3）は判断材料として読む — F2 の問いはユーザーに提示してよいが、
F1 の実装はここでやらない（起票済み。修理は triage 経由）。

### Step 1b. 提示の規律（以降の全区分に適用）

判断は**項目単位**で仰ぐ。区分をまとめて 1 回で聞かない（唯一の例外は Step 4 の
reject 群）。各項目でこの 4 点を、この順に出す:

1. **何の問題か** — その区分の成果物が言う問題記述を起点に 1〜2 文。前提にしている語
   （store skill / sibling / provenance / 承認系譜など）がそのセッションで初出なら、
   その 1 語だけ先に説明してから本文を出す。同じ概念は同じ語で呼び、途中で言い換えない
2. **承認すると何が変わるか** — 1 文
3. **取り消せるか** — 下の可逆性表の該当行
4. **残る懸念** — 成果物に所見があればそれ。無ければ「なし」

**選択肢は必ず 3 つ — 承認 / 却下 / 保留。** 「判断材料が足りない」は保留の正当な理由で、
**保留を選ぶのに説明を求めない**。分からないまま承認させるのがこのゲートの最大の失敗様式。

保留したものは Step 7 の `held` に数える。保留の代償は区分ごとに違い、**insight だけは
無条件に安全ではない**（Step 4 参照）。

**可逆性**:

| 区分 | 取り消し |
|---|---|
| insight adopt | `adopt-staged` の監査記録が残る。store から後で退役可能 |
| skill 退役 (archive) | **可逆** — `skills/.archive/` への移動なので `mv` で戻せる（ADR-0097 D5）。`remove-skill --delete` だけが非可逆 |
| insight reject | staging から消える。同種の候補は次の batch で再提起されうる |
| insight 保留 | item 単位で staging に残る（`--hold-names`、監査 `decision="held"`）。ただし翌週の staging は止まる — Step 4 |
| dead code 削除 | 復元可能だが非対称 — Step 5 |
| identity 採用 | 1 候補 = 全置換。前版は snapshot に残る |
| constitution 改正 | このセッションではやらない（Step 6b） |

**LLM 出力の扱い**: findings の散文は LLM 出力で、外部データを読んだ段の下流にある。
畳んで伝えるときに**原文にない判断を足さない** — 「これは安全です」は原文がそう言って
いる場合を除いて言わない。判断は人間に属し、この skill は材料を読める形にするだけ。

### Step 4. Insight staging（adopt-staged は人間の承認で実行）

staging を直接読む（`ls "$MOLTBOOK_HOME/.staged/"*.md` + 各 `.meta.json`）。
旧 insight-recommendation 段は ADR-0098 で退役したので、機械推奨は無い —
**adopt 候補は 1 件ずつ**、Step 1b の 4 点で判断を仰ぐ。明らかに同種の group
（meta の sibling / cluster 記述があるもの）に限り reject を group 単位で 1 回に
まとめてよい。自分で新しい分類を作らない。

**この区分の保留は item 単位で表現できる**（`--hold-names`、audit `decision` =
`approved` / `held` / `rejected`）。残る代償は 1 つだけで、これは提示する:
**保留した item は翌週の insight staging を止める**（ADR-0074 の pending ガード）。
説明は次の 1 文で足りる:

> 保留すると staging に残り、来週の insight 候補生成は 1 回止まります（理由はログに残ります）。

判断が固まったら、合意の形に対応する経路を選ぶ。どれも ADR-0012 の per-item 監査要件を
満たす:

| 合意の形 | コマンド | audit source |
|---|---|---|
| 全件 adopt | `contemplative-agent adopt-staged --yes` | `stage-adopted-auto` |
| 部分採用（非対話、既定） | `contemplative-agent adopt-staged --adopt-names FILE [--hold-names FILE] [--reject-rest]` | `stage-adopted-names` |
| 採用と同時に store の skill を退役 | `contemplative-agent adopt-staged --adopt-names FILE --archive-names FILE` | `stage-archived-names` |
| 単体の退役 | `contemplative-agent remove-skill <name> --reason TEXT` | `direct-archive` / `direct-archive-auto` |
| 部分採用（ユーザーがターミナルで対話実行） | `contemplative-agent adopt-staged` | `stage-adopted` |

対話実行が持つのは y/N の 2 状態だけなので、**保留が 1 件でもあれば非対話経路を使う**。
各 FILE は staged item の**ファイル名を 1 行 1 件**（名前の正本は
`ls "$MOLTBOOK_HOME/.staged/"*.md`）。`--archive-names` だけは **store の skill** を指す
（`old.md` か `old.md superseded-by new-staged-name.md`。退役は削除ではなく
`skills/.archive/` への移動）。1 つの名前が複数 FILE に現れたら **exit 2 で何も動かない**。

**`--reject-rest` は既定で付ける。** 省略すると残りは監査記録なしで staged に残る —
保留したいものは `--hold-names` に挙げる（そちらは記録が残る）。

**安全側に倒れる性質**: 未知の名前 1 つで**何も触らず abort** / FILE が空・読めない場合も
abort（`--reject-rest` との組合せで staging 全体を消し去るのを防ぐ、2026-08-01 security
review C2）/ `--reject-rest` 単独指定は拒否 / 保留の記録に失敗すると非 0 exit。
staging ファイルの直接削除は ADR-0012 の auditable-CLI 原則に反するので行わない。

**identity.md が staged にある場合**（ADR-0091 の月次 staging）: 同じ adopt-staged 経路で
承認/棄却する。identity は「1 候補 = 全置換」なので、本文と reasoning を読んでから判断する。

### Step 5. Dead code candidates（JSON があれば）

`$MOLTBOOK_HOME/pipeline/dead-code/dead-code-{end-date}.json` の `candidates` を直接読む
（code-owned の正本。旧 packet §5 との照合ガードは、LLM 描画層の消滅とともに不要になった —
ADR-0098）。候補ゼロの週は無音が正常。

candidate ごとに 3 択（「削除」が承認、「偽陽性」が却下に当たる）:

1. **削除** — 機械的な削除（定義の除去）に限りこのセッションで実施。code-reviewer agent で
   確認 → Verify（`uv run ruff check src/ tests/ scripts/` → `uv run lint-imports` →
   `uv run pytest tests/ -q`）→ 単一 commit。参照の解きほぐしが要る削除（間接参照の疑い、
   公開 API、sibling 消費の `testing/` 系）は **defer** — 理由を記録し通常セッションで
2. **偽陽性** — `.vulture_whitelist.py` に 1 行 + 理由コメント（同 commit）
3. **保留** — 記録だけ残す（来週も再報告される — nag ではなく未決の可視化）

偽陽性の典型: CLI entry point・`config/prompts/*.md` 動的ロード・Protocol 間接参照・
sibling 消費の出荷 kit（ADR-0088）。迷ったら削除より whitelist / 保留に倒す。

### Step 5b. Docs consistency（JSON があれば）

`docs-consistency-{end-date}.json` の findings を提示し、直せるものは同 commit で直す
（自己文書のみ・検出と修理の分離は ADR-0093 のまま。修理はこのセッションの人間同席
commit で、無人には流れない）。

`readings.mechanism` も 1 行で読む（2026-08-25 追加）: `mechanism_commits_since` は
architecture.md の最終 commit 以降に src/ + scripts/ を触った commit 数。閾値なし —
その中に機構層の変更（ゲート・式・閾値・段構成）があったのに Data Flow が未更新なら
鮮度規約（CLAUDE.md）違反なので同 commit で追記する。0 と `null`（GIT_FAIL、errors に
理由）は別物。なお anchor は architecture.md への任意の commit で動くので、gate で
architecture.md を直した週は翌週 0 に戻る — 見るのは当週の値。

### Step 6b. Value layer cadence（value-layer JSON があれば）

`value-layer-{end-date}.json` を直接読む。静かな週は無音が正常。出るのは 4 パターン:

1. **identity staged** — Step 4 で扱い済みのはず。未処理なら戻る
2. **identity deferred（IDENTITY_STAGING_BUSY / IDENTITY_INSIGHT_PENDING /
   IDENTITY_STAGING_RACE）** — このセッションで拾うなら、Step 4 で staging を空にした
   **後**に `contemplative-agent distill-identity --stage` → staged された identity.md を
   同セッションで adopt-staged（翌週の自動再試行に任せてもよい — due は持続する）
3. **constitution due** — 情報表示のみ。改正はこのセッションでは**やらない** —
   `docs/runbooks/constitution-amendment.md` を別途スケジュール。ADR-0056: 同じ週に
   identity と constitution を両方採用しない
4. **rules layer（maintenance reading）** — 件数・最新 mtime・構造 issue を出すだけで
   due 判定はしない。`state:` が `RULES_UNREADABLE` / `RULES_DIR_MISSING` のときは
   「構造 issue 0 件」を読まない — 読めたファイルについての 0 件

### Step 6c. Never-selected skills（JSON があれば）

`never-selected-{end-date}.json` を直接読む（ADR-0097 D5）。**列挙するだけで、archive は
このセッションの人間が行う。** 読む順序を守る:

1. **保留の表示が先** — `NEVER_SELECTED_LOG_UNREADABLE` / `NEVER_SELECTED_NO_CATALOG` /
   `NEVER_SELECTED_SCHEMA` や withheld populations があれば、**その週は archive しない**
   （読み値が degraded なだけで「候補なし」ではない）
2. **中立性の但し書き** — strict の隣の「全履歴の full-corpus 注入: N / M records」が
   ゼロでなければその分は注入されている。strict の主張は **judged な action に限った**
   中立性
3. **Strict だけが archive 候補** — 全履歴 0 回選択かつ judged exposure ≥ 600（Slote 床）。
   `contemplative-agent remove-skill <name> --reason TEXT`（`--reason` は必須で機能 —
   書面の理由を義務づけるまで図書館の除籍は 98% が「念のため」保持された）
4. **Dormant は読み値。archive しない**
5. **below_floor も archive しない**

### Step 7. Gate メトリクスの記録（必須・最後）

承認結果を `pipeline-metrics.jsonl` に 1 行記録する（旧 build_decision_packet.py
gate-record は ADR-0098 で退役。`pipeline_audit.py` 直呼びが後継 — 同じ append-only
JSONL に同じ運転で書く）:

```bash
python3 scripts/pipeline_audit.py \
  --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --run-id "gate-{end-date}" --event gate_record \
  --field insight_adopted=N --field insight_rejected=N --field insight_held=N \
  --field deadcode_deleted=N --field deadcode_whitelisted=N --field deadcode_held=N \
  --field skills_archived=N
```

`*_held` は**保留が 0 件でも必ず渡す**（省略すると「保留 0 件の週」と「保留を数えなかった
セッション」が区別できなくなる）。

## Out of scope（このセッションでやらないこと）

- **code 修理の適用・再実装** — ADR-0098 で廃止。診断の F1 は candidate として台帳に
  起票済みで、採否は task-triage digest、実装は triage の dispatch が担う
- **診断起票 candidate の採否** — 存在の報告まで（Step 1）。決めるのは triage digest
- **過去週の一括処理** — 1 セッション 1 週
- **staging への書き込み**（adopt-staged 以外の経路での操作）
