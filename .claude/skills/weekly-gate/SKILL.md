---
name: weekly-gate
description: 土曜の単一承認セッション（ADR-0085 / ADR-0098）。無人 weekly チェーンの成果物（weekly-{end-date}-findings.md と各計器の per-week JSON）を直接読み、値層の承認（insight staging の adopt-staged / identity / never-selected の退役）、dead code の削除判断、rfcs/ の無人起票の機微点検と commit（公開に出すのはこのゲート）、gate メトリクスの記録までを 1 セッションで行う。Use when the user says 「週次の承認をする」「週次のゲートをやる」/weekly-gate, or on Saturday after the unattended chain has run. NOT for — code 修理の適用（ADR-0098 で廃止。修理は task-triage loop の担当）、診断起票 draft の採否（→ triage digest）。
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

**最初の 1 行 — 開始の記録**（P2-01.2。Step 7 の `gate_record` の `ts` との差が所要分）:

```bash
python3 scripts/pipeline_audit.py \
  --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --run-id "gate-{end-date}" --event gate_start
```

**土曜の時刻表**（JST。P2-01.11）:

- 無人チェーン（土 09:00 起動）の期待終了 ≤ 12:00。遅れても `CHAIN_DEADLINE_SECONDS`（既定 10800 = 09:00 → 12:00、`scripts/weekly-pipeline.sh`）で打ち切られる
- watchdog: 12:30 / 13:30（`com.moltbook.watchdog.plist`）
- task-triage loop の tick: 14:07 — **Step 6d の commit は 14:07 より前に**（tick が起票を読む）
- Ollama の guard 窓: 13:00–16:45 / 19:00–22:45（JST 0/6/12/18 時のセッションと重ねない、`scripts/ipd-two-arm.sh`）
- Ollama を使う読み（shadow 憲法 / IPD / null pair）はこのゲートでは回さない — 平日の guard 窓で前日までに取る

3 点セット（+ 四半期の (d)）。それぞれ別の問いに答える — 片方をもう片方の代わりにしない。

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
$MOLTBOOK_HOME/pipeline/confusion-pairs/confusion-pairs-{end-date}.json
$MOLTBOOK_HOME/pipeline/comment-outcomes/comment-outcomes-{end-date}.json
$MOLTBOOK_HOME/reports/analysis/weekly-{end-date}-archive-candidates.txt
```

**例外（月次減速、P1-04.6）**: `dead-code-{end-date}.json` / `docs-consistency-{end-date}.json` は、
監査ログ（`logs/weekly-pipeline-audit.jsonl`）の当該 run に `stage=deadcode` / `stage=docsscan`
`result=skipped reason=CADENCE_MONTHLY` があれば設計上存在しない — 欠報ではない（Step 5 と同じ）。
`reason=CADENCE_ERROR` が出ていれば cadence 判定側の異常として報告する。

**凍結の読み（毎週 1 行）**: その週の `materials.md`（`~/.config/moltbook/logs/weekly-pipeline/weekly-*/materials.md`）の `## Freeze Reading` の 1 行を
直接読んで briefing に出す（レポートには転記されない — 数値経路に LLM を通さない）（`scripts/freeze_reading.py`、ADR-0080 追補 2026-10-24「凍結」）。`candidate=freeze candidate`
が出た週だけ verdict（`gate_record` の `freeze_verdict=`）を人間が打つ。**停止リスト**（同追補）の行を
1 つ閉じるか期日を更新し、表が空になった週を記録する。

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

#### (d) 四半期の T4 棚卸し（四半期境界後の最初に開催した土曜ゲートだけ）

ADR-0101 D4。判定は決定論の 1 行 — 今四半期（1/1・4/1・7/1・10/1 起点）の `gate_record` に
`t4_run` が無ければ、このゲートが「四半期境界後の最初に開催した土曜ゲート」（休みの土曜は
数えない — 開かれなかったゲートは記録を残さないので、この判定が自然に飛ばす）:

```bash
python3 - "${MOLTBOOK_HOME:-$HOME/.config/moltbook}/logs/pipeline-metrics.jsonl" {end-date} <<'EOF'
import datetime as dt, json, sys
path, end = sys.argv[1], dt.date.fromisoformat(sys.argv[2])
gate = end + dt.timedelta(days=1)
q_start = dt.date(gate.year, 3 * ((gate.month - 1) // 3) + 1, 1)
done = [r for r in map(json.loads, filter(str.strip, open(path)))
        if r.get("event") == "gate_record" and r.get("t4_run")
        and dt.date.fromisoformat(r["ts"][:10]) >= q_start]
print("T4: done this quarter" if done else f"T4: DUE at this gate (quarter from {q_start})")
EOF
```

DUE なら T4 を行う（ADR-0101 の Review-when の手順）。対象集合は census の登録表
（`scripts/_census_registry.py`）から、削除が決まって branch に乗っている分を差し引いて決める
（削除 PR の merge を待たない）。各計器の行に**読み手の種別**の列を足す — 人間（briefing の
1 行）/ Claude Code 対話 / Claude Code headless（`claude -p` の weekly-report）/ code（決定論）
の 4 値（P1-04.16。人間の 1 行が無い計器の振り分けはこの回では決めない）。同じ回で
`docs/plans/roadmap-2026-10/ROADMAP.md` の §2（完成の判定表）を通読し、層別の verdict を
Step 7 の `gate_record` に書く（`freeze_verdict=` / `self_regulation_verdict=` と同形。読み値が
まだ無い行は「材料なし」）。T4 を行ったら Step 7 の `gate_record` に `--field t4_run=<回数>` を足し、
所有 ADR（ADR-0101）に `T4 run N (YYYY-MM-DD)` の注記を書く。

### Step 1. Decision inventory の提示

(a) で読めた成果物から、今週の判断対象を件数とスコープで明示列挙する
（human-gate.md の 1 作業 1 ゲート）:

- insight staging: `ls "$MOLTBOOK_HOME/.staged/"*.md` の件数（identity.md が居るか含む）
- value layer cadence: value-layer JSON の identity / constitution due と rules 読み値
- dead code: JSON の candidates 件数
- docs consistency: JSON の findings 件数
- never-selected: JSON の strict / dormant / below_floor 件数
- 混同対（ADR-0105）: confusion-pairs JSON の pairs 件数と、候補ファイルの行数
- **診断起票の draft**: 今週 `rfcs/`（台帳の正本。pipeline の起票先でもある）に増えた
  `state: draft` の件数 — **本セッションでは採否しない**（task-triage digest の担当。
  ここでは存在の報告のみ）。ただし**公開へ出す commit はここの仕事**（Step 6d）

findings.md（F1/F2/F3）は判断材料として読む — F2 の問いはユーザーに提示してよいが、
F1 の実装はここでやらない（起票済み。修理は triage 経由）。

### Step 1b. 提示の規律 — eli5 ブリーフィング（以降の全区分に適用）

**オーナーは週次文書・findings を直接読まない**（RFC-0010 の読み口転回、2026-08-26）。
このセッションが唯一の読み口: 裁定 1 件ごとに、絵と平易な日本語で「これは何で、証拠は
こう」を説明して承認を求める。判断は**項目単位**で仰ぐ。区分をまとめて 1 回で聞かない
（唯一の例外は Step 4 の reject 群）。各項目でこの順に出す:

1. **何の問題か / 何の候補か** — 前提知識ゼロで分かる 1〜3 文。専門語・repo 内部語は
   その場で 1 語ずつ普通の日本語に開く。同じ概念は同じ語で呼び、途中で言い換えない。
   図が判断を速くする項目（構造の変更・ループの形）は小さな図解を添えてよい
2. **証拠 — 軸ごとに分けて** — 候補に付いた証拠（新規性・環境の反応・頻度など）を
   **軸ごとに別々の行**で見せる。合成した単一スコア・総合評価は作らない（ADR-0080 追補の
   単一スカラー還元禁止をゲート面でも守る）
3. **推奨 + 理由** — 採用/却下/保留の推奨を 1 行 + 理由 1〜2 文。**推奨は証拠と視覚的に
   分離して置く**（証拠の行に混ぜない）。原文にない判断を証拠として語らない
4. **承認すると何が変わるか** — 1 文
5. **取り消せるか** — 下の可逆性表の該当行
6. **残る懸念** — 成果物に所見があればそれ。無ければ「なし」

**縛り（レンズの可視化 — 実効フィルタ化の防止）**:

- **キュー全件を必ず提示する。** 「明らかに却下だから見せない」をしない — 間引きは
  それ自体が承認判断の代行になる（ADR-0097 の headless reviewer が実効フィルタ化した形の
  再建を防ぐ）。group reject（Step 4）でも構成要素は列挙する
- **説明・推奨・裁定を記録する**（Step 7 の per-item 記録）。推奨と裁定の一致率が
  ~100% で推移し続けたら、それは実効フィルタ = Claude 化の兆候 — 保存済み推奨ログを
  遡って偏りを 1 回監査する（RFC-0010 Review-when）

**選択肢は 3 つ — 承認 / 却下 / 保留。insight 区分だけは 2 つ — 承認 / 却下。**
「判断材料が足りない」は保留の正当な理由で、**保留を選ぶのに説明を求めない**。分からないまま
承認させるのがこのゲートの最大の失敗様式。insight は承認も却下も可逆（採用は後で archive
でき、却下したテーマは新しいパターン経由で戻る — ADR-0074 D5）なので、材料が足りないときの
安全側は却下がそのまま担う。

保留したものは Step 7 の `held` に数える。

**可逆性**:

| 区分 | 取り消し |
|---|---|
| insight adopt | `adopt-staged` の監査記録が残る。store から後で退役可能 |
| skill 退役 (archive) | **可逆** — `skills/.archive/` への移動なので `mv` で戻せる（ADR-0097 D5）。`remove-skill --delete` だけが非可逆 |
| insight reject | staging から消えるが、**本文は `$MOLTBOOK_HOME/.rejected/<ts>-<content_hash>.md` に残る**（P1-12.2。audit 行の `content_hash` で引ける）。同種の候補は次の batch で再提起されうる |
| `mv` で手戻しした（`.archive/` から戻す・`.rejected/` から戻す等） | 監査 CLI は無いので、`gate_item` に 1 行足す（`--field decision=reverted --field item=<file>`）。手編集の監査 CLI は延期中 |
| dead code 削除 | 復元可能だが非対称 — Step 5 |
| identity 採用 | 1 候補 = 全置換。前版は snapshot に残る |
| constitution 改正 | このセッションではやらない（Step 6b） |

**LLM 出力の扱い**: findings の散文は LLM 出力で、外部データを読んだ段の下流にある。
畳んで伝えるときに**原文にない判断を足さない** — 「これは安全です」は原文がそう言って
いる場合を除いて言わない。判断は人間に属し、この skill は材料を読める形にするだけ。

### Step 1c. 当週のロードマップ決定（`docs/plans/roadmap-2026-10/decisions.md`）

P2-01.10。ロードマップの決定は他の区分と同じ eli5 の規律（Step 1b）で 1 件ずつ仰ぐ。
前後に開始・終了を 1 行ずつ打つ（P2-01.13 — ロードマップの執行分を北極星の負荷系列と
ゲート所要分から分けて読むため）:

```bash
python3 scripts/pipeline_audit.py --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --run-id "gate-{end-date}" --event roadmap_start
```

1. **当週の行を引く** — ゲート日は `{end-date}`（金曜）+ 1 日。`decisions.md` の表は
   2026 年の行を `MM-DD の土曜ゲート`、2027 年以降を `YYYY-MM-DD の土曜ゲート` と書く:

   ```bash
   python3 - docs/plans/roadmap-2026-10/decisions.md {end-date} <<'EOF'
   import datetime as dt, sys
   path, end = sys.argv[1], dt.date.fromisoformat(sys.argv[2])
   gate = end + dt.timedelta(days=1)
   label = f"{gate:%m-%d}" if gate.year == 2026 else f"{gate:%Y-%m-%d}"
   rows = []
   for line in open(path, encoding="utf-8"):
       cells = [c.strip() for c in line.split("|")]
       # Decision rows only: the per-gate count table shares the date cell.
       if len(cells) > 2 and cells[1] == f"{label} の土曜ゲート" \
               and cells[2].startswith(("D-", "ROADMAP-")):
           rows.append(line)
   print(f"gate {gate}: {len(rows)} roadmap decision(s)")
   print("".join(rows), end="")
   EOF
   ```

2. **繰り越しを先に言う** — 「前週から繰り越した行: N（ID）」を 1 行（2026-10-17 の回は
   10-10 の 3 件 D-P0-01-1 / D-P0-01-3 / D-P0-03-2 を `decided_at=2026-10-10` で、
   `ROADMAP-2026-10` を `decided_at=2026-10-11` で打つ遡及分。上限 5 には数えない）。欠席・hold の扱いと
   縮退順は `decisions.md` の「遅れたとき」節（遅れが 2 ゲートを超えたら、後ろから延期候補を
   提示する。決めるのは人間）
3. **1 件ずつ提示** — 問い・選択肢の全文・推奨は `decisions.md` の「4.1 束ごとの決定事項」から、
   材料は表の「材料」列から引いて、その場でコマンドを回す。熟慮（種別列）は `reason` 必須
4. **1 件ずつ記録** — `recommender` は推奨を書いたモデル名（ロードマップ本文の推奨なら
   それを書いたモデル）。遡及分は `decided_at`:

   ```bash
   python3 scripts/pipeline_audit.py --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
     --run-id "gate-{end-date}" --event gate_item \
     --field category=roadmap --field item=D-… \
     --field recommendation=<A|B|C> --field decision=<A|B|C> \
     --field recommender=<model-id> [--field reason=…] [--field decided_at=YYYY-MM-DD]
   ```

5. **束の閉じ** — 束を閉じるのは、その束の「束の完了条件」のコマンドをこの場で回して満たした
   ときだけ。`--field item=<束ID> --field decision=closed` を 1 行打ち、
   `docs/plans/roadmap-2026-10/closures.md` の行（状態・日付・証跡 sha・未達の移し先）を
   Step 6d の commit に含める（P2-01.12）

`approver` は D-P1-12-2（2027-01-09）までは無い — それまでの roadmap 行は Claude Code の転記で、
裁定は人間の言葉。ゲートは code を適用しない（下の Out of scope）— 決まった削除 PR の merge は
ゲートの後の別セッション。

```bash
python3 scripts/pipeline_audit.py --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --run-id "gate-{end-date}" --event roadmap_end
```

### Step 4. Insight staging（adopt-staged は人間の承認で実行）

staging を直接読む（`ls "$MOLTBOOK_HOME/.staged/"*.md` + 各 `.meta.json`）。
旧 insight-recommendation 段は ADR-0098 で退役したので、機械推奨は無い —
**adopt 候補は 1 件ずつ**、Step 1b の 4 点で判断を仰ぐ。明らかに同種の group
（meta の sibling / cluster 記述があるもの）に限り reject を group 単位で 1 回に
まとめてよい。自分で新しい分類を作らない。

**この区分の選択肢は承認 / 却下の 2 つ。** staging に item を残すと ADR-0074 の pending
ガードが次の insight run を丸ごと止め、その次の run が 2 週分の窓になる（候補数が倍になり、
窓 ≥ 1,000 行で surprise 読み値が消える）。ゲートを閉じるとき staging は空にする。

判断が固まったら、合意の形に対応する経路を選ぶ。どれも ADR-0012 の per-item 監査要件を
満たす:

| 合意の形 | コマンド | audit source |
|---|---|---|
| 全件 adopt | `contemplative-agent adopt-staged --yes --reason TEXT` | `stage-adopted-auto` |
| 部分採用（非対話、既定） | `contemplative-agent adopt-staged --adopt-names FILE --reject-rest --reason-code CODE` | `stage-adopted-names` |
| 全件却下 / 名指しの却下 | `contemplative-agent adopt-staged --reject-names FILE`（`--adopt-names FILE` と併用可） | `stage-rejected-names` |
| 採用と同時に store の skill を退役 | `contemplative-agent adopt-staged --adopt-names FILE --archive-names FILE` | `stage-archived-names` |
| 単体の退役 | `contemplative-agent remove-skill <name> --reason TEXT` | `direct-archive` / `direct-archive-auto` |
| 部分採用（ユーザーがターミナルで対話実行） | `contemplative-agent adopt-staged` | `stage-adopted` |

各 FILE は staged item の**ファイル名を 1 行 1 件**（名前の正本は
`ls "$MOLTBOOK_HOME/.staged/"*.md`）。

**承認の記録（P1-12.1 / ADR-0012 2026-10-24 追補）**: audit 行には誰が・なぜ・どの経路で、が入る。
- **署名**: FILE の先頭に人間が `# approver: <名前>` を 1 行書く（D-P1-12-2 = B）。Claude が
  代筆しない — 名前は説明を受けた人間が打つ。`--approver NAME` でも同じ（FILE と食い違えば exit 2）。
  固定値の環境変数や Claude の自己申告で埋めない。
- **理由**: `--adopt-names` / `--reject-names` の行は `名前<TAB>理由コード<TAB>自由文`（2・3 列目は省略可、
  `-` で空）。理由コードは `duplicate | off-constitution | low-quality | stale | other`。
  **却下には理由コードが要る**（行の 2 列目か `--reason-code`。無ければ exit 2 で何も動かない）。
  `--reject-rest` は `--reason-code` 必須、`--reason TEXT` を足すと全行の自由文になる。
- **`--yes` は `--reason` 必須**。人間が全文を読んだ後の TTY 代替で、打つのは人間が立ち会う
  セッションだけ。Claude Code は説明係・転記者であり承認者ではない。
- **却下した本文**は `$MOLTBOOK_HOME/.rejected/<ts>-<content_hash>.md` に残る。
- audit 行の書き込みに失敗したら**採用は行われず**（exit 1）、item は staged のまま残る。`--archive-names` だけは **store の skill** を指す
（`old.md` か `old.md superseded-by new-staged-name.md`。退役は削除ではなく
`skills/.archive/` への移動）。`--adopt-names` / `--reject-names` / `--archive-names` の 2 つ以上に同じ名前が
現れたら **exit 2 で何も動かない**。

**部分採用では `--reject-rest` を既定で付ける。** 省略すると残りは監査記録なしで staged に残り、次の
insight run を止める。`--reject-names` とは排他（exit 2）— `--reject-names` は列挙であって「残り全部」ではなく、
挙げなかった item は staged のまま残る。ゲートを閉じるときは `ls "$MOLTBOOK_HOME/.staged/"*.md` の全件を
どちらかの FILE に挙げる。

**安全側に倒れる性質**: 未知の名前 1 つで**何も触らず abort** / FILE が空・読めない場合も
abort（`--reject-rest` との組合せで staging 全体を消し去るのを防ぐ、2026-08-01 security
review C2）/ `--reject-rest` 単独指定は拒否。`--reject-names` も同じ契約。
staging ファイルの直接削除は ADR-0012 の auditable-CLI 原則に反するので行わない。

**identity.md が staged にある場合**（ADR-0091 の月次 staging）: 同じ adopt-staged 経路で
承認/棄却する。identity は「1 候補 = 全置換」なので、本文と reasoning を読んでから判断する。

### Step 5. Dead code candidates（JSON があれば）

`$MOLTBOOK_HOME/pipeline/dead-code/dead-code-{end-date}.json` の `candidates` を直接読む
（code-owned の正本。旧 packet §5 との照合ガードは、LLM 描画層の消滅とともに不要になった —
ADR-0098）。候補ゼロの週は無音が正常。
空振りが 4 回続くと dead-code / docs-consistency は月次に減速する（`scripts/scan_cadence.py`、P1-04.6）— JSON が無い週は
監査ログに `stage=deadcode result=skipped reason=CADENCE_MONTHLY` があれば欠報ではない。直近 4 回に陽性が出れば週次に戻る。

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

**`errors` が非空なら findings 0 でも「検査 X abstain（reason）」を 1 行提示する**（P1-05.5。緑に隠さない）。
2 週続いたら draft 起票。件数（`readings_count` / `abstain_count`）は `reports/PIPELINE-STATUS.md` の
`docs-consistency` 行にも出る — JSON の転記であって判断ではない。

`readings.freshness` は docs/CYCLES.md の FRESHNESS header の齢（読み値のみ、閾値なし）。機構層の変更が
ADR / script header に未反映かは、当週の src/ + scripts/ commit を gate が目で確認する（codemap と
その鮮度計器は ADR-0102 で退役 — 段構成の正本は所有 ADR と script 冒頭コメント）。

### Step 6b. Value layer cadence（value-layer JSON があれば）

`value-layer-{end-date}.json` を直接読む。静かな週は無音が正常。出るのは 4 パターン:

1. **identity staged** — Step 4 で扱い済みのはず。未処理なら戻る
2. **identity deferred（IDENTITY_STAGING_BUSY / IDENTITY_INSIGHT_PENDING /
   IDENTITY_STAGING_RACE）** — このセッションで拾うなら、Step 4 で staging を空にした
   **後**に `contemplative-agent distill-identity --stage` → staged された identity.md を
   同セッションで adopt-staged（翌週の自動再試行に任せてもよい — due は持続する）
   identity の候補を却下するときも Step 4 と同じ経路（却下した本文は
   `$MOLTBOOK_HOME/.rejected/` に自動で残る — P1-12.2）
3. **constitution due** — 情報表示のみ。改正はこのセッションでは**やらない** —
   `docs/runbooks/constitution-amendment.md` を別途スケジュール。ADR-0056: 同じ週に
   identity と constitution を両方採用しない
   **`constitution.due` が true の週は、改正ゲートを次の土曜に予定し、`gate_record` に 1 行残す**
   （RFC の自動起票はしない。due は 83 日ごと）
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

**候補ファイル（ADR-0105）**: pipeline は `weekly-{end-date}-archive-candidates.txt` に
never-selected strict ∪ 混同対の少ない側を **store のファイル名で 1 行 1 件**書く
（`confusion-pairs-{end-date}.json` の `pairs` / `reasons` が根拠。読むのは JSON の方）。
退役するときはそのファイルをそのまま渡す — `contemplative-agent adopt-staged
--adopt-names FILE --archive-names weekly-{end-date}-archive-candidates.txt`（採用が無い週は
`--archive-names` 単独で完結する）。**空のファイルは渡さない**（`--archive-names` は空の選択を
writer bug と見て exit 2 する）。行を削ってから渡してよい — このファイルは提案であって決定ではない。
JSON の `reasons` に `CONFUSION_*` の withheld コードがあればその週は archive しない。

**天井の問いは 2026-10-24 に閉じた**（ADR-0105 注記、D-P1-04-4 = A）: archive の後に幻覚率を取る手順は無い。
代わりに 7c の撤去条件を見る — `confusion-pairs-{end-date}.json` の混同対が 7b の strict の外の
entry を 4 週連続で名指ししなければ、stage 7c の削除 PR を起こす（直近 4 週の JSON を読めば足りる）。

### Step 6e. Comment outcomes（JSON があれば）

`comment-outcomes-{end-date}.json` を直接読む（ADR-0106 の消費計画）。**読むだけ。**
この計器から skill の採用・退役・選択へ流れる経路は無く、ここで作ってもいけない
（ADR-0106 D6 — 流すなら別の ADR）。

1. **注記を先に読む** — `observation_note`（分布であって寄与推定ではない。どの skill が
   注入されたかは selector の判断で、状況と交絡する）と `coverage_note`（観測しているのは
   自分の投稿の下のスレッドだけ）。この 2 行を飛ばして行を比べると、交絡した分布を寄与として
   読む
2. **母数の健全性** — `observed_publishes` / `unobserved_publishes` / `publish_failures` /
   `unjoined_publishes` / `excluded_immature_publishes` / `unreadable_days`。
   分母は `observed_publishes`（観測できた公開だけ）。`unobserved_publishes` がこれを
   大きく上回る週の行は被覆の偏りを見ているので比べない。`observed_publishes` が小さい週も
   比べない（件数から偶然に出る幅の方が広い）
3. **行を読む** — skill ごとの `injected_comments` / `replied_fraction` / `mean_thread_depth`
4. **2 窓で判定する（消費計画）** — 各 ≥ 500 judged records の 2 窓が揃ったら決める:
   (i) 返信率が skill 間で分かれるか (ii) store 全体の返信率の帯を宣言できるか。
   **分かれなければ計器を撤去する** — weekly stage 7d を削除し、`rfcs/0028-...` を
   `resolved` にし、ログは歴史として残す（ADR-0106 `## Review-when`）

### Step 6f. Instrument census — 登録表の手入れ（materials にあれば）

`$MOLTBOOK_HOME/logs/weekly-pipeline/weekly-{end-date}-HHMMSS/materials.md`（run_id は Step 0(b) のもの）の
`## Instrument Census` 冒頭の太字行だけ読む
（ADR-0107 の消費計画。分布・redundancy・ledger・trace・帯・id 反復・週内外れ値・
hunting windows の 8 節は weekly-report の Phase 0 が読み済みで、ここでは読み直さない）。status が OK / KEPT / QUIET 以外の行を 1 読みで片付ける（KEPT はゲートが残すと決めた退役 writer のファイル、QUIET は宣言した周期の内側にある slow writer の空窓 — どちらも問いではない）:

- `UNKNOWN` — 誰かが登録なしに書き始めたログ。`scripts/_census_registry.py` の `REGISTRY`
  に行を足す（glob / owner ADR / 毎週答えさせる enum 欄）か、書く側を止める
- `NO_ROWS` — 登録は live なのに窓内 0 行。writer が退役したなら `status=WRITER_RETIRED` に
  反転、季節性（月次 shadow 等）なら `cadence_days=N` を行に書く — 最新行が N 日以内なら空窓は QUIET（OK 扱い）で
  問われず、N 日を超えて沈黙したら NO_ROWS に戻る（止まった writer を黙らせない）。
  単発の空窓（候補 0 件の週の `insight-staged` 等）は放置してよい — 判断を commit message に 1 行
- `MISSING_EVENT` — heartbeat 不在（injection guard の `guard_alive`）。修理は task-triage へ
- `ORPHAN` — writer 退役後のファイル残存。削除するか研究データとして残すかを決める
  （削除は人間だけ。エピソードログは対象外 — 別フォルダで census は触らない）。残すと決めたら
  `REGISTRY` の行を `status=KEPT` に反転する — 以後は OK 扱いで太字行に出ない（削除したら行を消す）

OK だけの週は何もしない。表を直したら `uv run pytest tests/test_instrument_census.py`。

### Step 6g. Baseline proposals の採否（materials の Ledger 節に `Proposed baselines` があれば）

`materials.md` の `## Observation Ledger (current view)` の `### Proposed baselines` だけ読む
（P1-05.1。無人セッションは baseline を**宣言できない** — 帯の再較正は人間ゲートの権限）。
proposal は `P-NNN` の id で列挙される（**未裁定は全件**列挙する。件数をここに固定しない）。
`⚑ STALE` は 2 週を超えて滞留している印。1 件ずつ 3 択:

1. **採用** — `declared_by: gate` の `baseline` 行を足す。`--from-proposal` は metric / expected を
   proposal から取る。帯を構造化するなら `--band-*` を全部付ける（一部だけは拒否される）:

   ```bash
   LEDGER="$MOLTBOOK_HOME/reports/analysis/observation-ledger.jsonl"
   python3 scripts/observation_ledger.py declare-baseline --ledger "$LEDGER" \
     --from-proposal P-NNN --source "gate {gate-date} / {根拠の報告}" \
     --band-low 0 --band-high 10 --unit '%' --estimator quantile --windows 1 \
     --regime "{境界表の行 id}" [--weekly-sd N]
   ```

   同じ metric の旧 `baseline` は後勝ちで置き換わる（再宣言 = 再較正）。**この metric に open の
   observation があり expiry が「帯を再較正したら」型なら、同じ gate で `archive` 行も要る**
   （archive 行 1 本を書いた delta ファイルを `observation_ledger.py append --ledger "$LEDGER" --delta FILE`
   に渡す。`archive` は append の検証を通る型 — 理由に発火した expiry の引用を書く）。
2. **却下** — `python3 scripts/observation_ledger.py reject --ledger "$LEDGER" --id P-NNN --reason "…"`
   （却下も行として残る。render から消える）
3. **保留** — `python3 scripts/observation_ledger.py hold --ledger "$LEDGER" --id P-NNN --reason "…"`
   （pending のまま残り、STALE の印だけ外れる。保留の理由に「何の読みを待つか」を書く）

`ledger` は本番 Mac 上の正本に追記する（data repo 側は毎朝の sync で上書きされる）。
追記したら `python3 scripts/observation_ledger.py render --ledger "$LEDGER"` で 1 回確かめる。

### Step 6d. rfcs/ の無人起票を公開に出す（機微点検 → commit）

無人セッションは working tree に**書くだけ**。`rfcs/` は公開 repo の tracked ディレクトリ
なので、**公開へ出す commit はこのゲートの仕事**（2026-08-25 著者判断、harness RFC-0001。
「書くのは無人、公開に出すのは人間」）。

```bash
git -C "$(pwd)" status --short rfcs/
```

未コミットの起票（`??` の `NNNN-slug.md`）を **1 件ずつ全文読んで機微点検**する。見るのは
外に出て困る情報だけ — 本文の質・採否は triage digest の担当で、ここでは判断しない。
点検範囲は `rfcs/` に加えて `docs/plans/` + `docs/evidence/` + `tests/`（公開 tracked で、同じ経路で秘密・ローカルパス・本番由来の本文が混ざりうる。regex の正本は `config/secret-patterns.txt` — 無い間は目視）:

- 秘密・資格情報・個人情報・ローカル絶対パス（`/Users/...`）・非公開ログの生引用
- 未公開の外部固有名（他者の名前、未公表の共同作業）
- untrusted な材料（post 本文）からそのまま流れ込んだ文字列

3 択で処理する:

1. **公開可能** → そのまま commit
2. **一部が機微** → 該当箇所だけ本文修正してから commit（診断の要点は残す）
3. **公開不可** → 撤回。ファイルを削除し、claims の系譜には起票が残るのでその旨を
   commit message か次の digest に 1 行残す（黙って消さない）

機械の点検 1 行: 起票全体に対し `git grep -n -E -f config/secret-patterns.txt -- rfcs/` を走らせる
（`sync-research-data.sh` の commit 前スキャンと同じ値の形のリスト。ヒット 0 が基準）。

**計器の draft は消費計画が要る（ADR-0101）**: 新しい read-only 計器（読み値・分布・較正
スケール・監査面）を提案する draft は、消費計画 —（a）誰がいつ読むか（b）何回の読みで何を
決めるか（c）満了時の撤去条件 — を書いていなければ**受理しない**。不採択は「draft を理由
1 行つきで未受理のまま残す」で記録する（削除も却下台帳も作らない）。

commit する前に `python3 scripts/rfc_index.py --validate` を通し（draft は state + state_since だけで通る。
`title` を足すと index に出る。accepted にするときは `review-when` / `alignment` も要る）、`python3 scripts/rfc_index.py` で
`rfcs/README.md` の index を再生成する（表と実体の drift を残さない — test が検査する）。
番号は pipeline が採番済み — **振り直さない**（欠番は再利用しない規約）。

```bash
git -C "$(pwd)" add rfcs/
git -C "$(pwd)" commit -m "docs(rfcs): file weekly {end-date} diagnosis drafts"
```

push はこのゲートでは行わない（通常の push 手順に従う）。

**CHANGELOG の `## [Unreleased]`（P0-06.5）**: この週に `done` にした RFC / `accepted` にした ADR は、
その commit で `CHANGELOG.md` の `## [Unreleased]` に 1 行足す（利用者に見える変更だけ。
内部の記録のみの RFC は足さない）。release 時に版見出しへ移し、`## [Unreleased]` は空で残す
（`scripts/release_consistency_check.py` がこの見出しの存在を見る）。

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
  --field skills_archived=N --field skills_archive_candidates=N --field skills_total=N
```

Step 0 の `gate_start` 行の `ts` からこの行の `ts` までが、このゲートの所要分（P2-01.2。
時刻表の 12:00〜14:07 = 127 分と照合する）。T4 を行った回は `--field t4_run=<回数>` を足す（Step 0 (d)）。

`skills_archive_candidates` は機械が出した候補数（`weekly-{end-date}-archive-candidates.txt` の
行数、0 なら 0）、`skills_total` はゲート終了時の `skills/*.md` の本数。`insight_adopted` と
`skills_archived` を並べると店の入口と出口の差が週ごとに出る — 出口が入口に追いつかない間は
店は自律的に代謝しない（RFC-0021 の 2 窓読みの材料。2026-09-08 著者指示）。

`*_held` は**保留が 0 件でも必ず渡す**（省略すると「保留 0 件の週」と「保留を数えなかった
セッション」が区別できなくなる）。`insight_held` は区分に保留が無いので常に 0 — 列は縦断記録の
連続性のために残す。

加えて **per-item のレンズ記録**（RFC-0010 Q7 — 説明係の推奨と人間の裁定を縦断記録に残す。
推奨・裁定の一致率が後から測れることが、eli5 ブリーフィングが実効フィルタ化していないかの
唯一の検証面）。裁定した項目 1 件につき 1 行:

```bash
python3 scripts/pipeline_audit.py \
  --log "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --run-id "gate-{end-date}" --event gate_item \
  --field item="{staged-name | O-NNN | candidate-id}" \
  --field category="insight|identity|deadcode|retire|docs|roadmap" \
  --field recommendation="adopt|reject|hold" --field decision="adopt|reject|hold" \
  --field content_hash="{audit 行の content_hash}" --field approver="{署名した人間の名前}"
```

`content_hash` は `category=insight|identity` の行で必須（P1-12.1 PR-B）: 直前の `adopt-staged` が
audit に書いた行の `content_hash`（stdout の行ではなく
`tail -n 20 "$MOLTBOOK_HOME/logs/audit.jsonl"` で `source=stage-*` の行を見て転記する）。1 週分の
`gate_item` がすべて audit 行に解決するかは
`python3 scripts/gate_item_audit_join.py --metrics "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl"
--audit "$MOLTBOOK_HOME/logs/audit.jsonl" --run-id "gate-{end-date}"` が 1 回で答える（解決しない行があれば
exit 1）。`approver` は Step 4 で署名した名前と同じ文字列 — deadcode / retire / docs 区分の行にも
同じ署名の経路で付ける（D-P1-12-2 = B）。登録名は `docs/GOVERNANCE.md` の Accountable operator 行。

`category=roadmap` の行（Step 1c）は `recommendation` / `decision` が選択肢の記号（`A|B|C`、
束の閉じは `closed`）で、`recommender` を足す（様式の正本は Step 1c）。

## Out of scope（このセッションでやらないこと）

- **code 修理の適用・再実装** — ADR-0098 で廃止。診断の F1 は draft として台帳に
  起票済みで、採否は task-triage digest、実装は triage の dispatch が担う
- **診断起票 draft の採否** — 存在の報告まで（Step 1）。決めるのは triage digest。
  ただし `rfcs/` の未コミット起票を機微点検して commit するのは**このセッション**（Step 6d）
- **過去週の一括処理** — 1 セッション 1 週
- **staging への書き込み**（adopt-staged 以外の経路での操作）
