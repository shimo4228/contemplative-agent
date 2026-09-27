# CA task ledger — agent-first 化（store 分割 + lease + aging + query-first）

## Context

### 何が壊れているか（2026-08-15 実測）

`contemplative-agent/.notes/TASKS.md` は **112 行 / 102,111 文字（約 68k トークン）**。
開くたびにこれが走査される。内訳:

| 節 | 行数 | 文字数 | 内訳 |
|---|---|---|---|
| Pending | 71 | 64,090 | ready **6 (8.5%)** / blocked 15 / observing 15 / deferred 19 / **done 16（移動漏れ）** |
| Done / Dropped | 41 | 36,482 | — |

1 行の中央値 721 文字、最大 3,842 文字。他 repo の台帳は最大 15k 文字で、
**破綻しているのは CA だけ**（authorship-strategy 14,875 / ~/.claude 15,174）。

### 引き金

読者が変わった。**人間はもう台帳を読まず、必要なら Claude に説明させる**（2026-08-15 著者指示）。
「人間が読む単一 Markdown 表」という初期の足場が、発展を阻害する側に回った
（rule `akc-cycle.md` の Scaffold Dissolution / ADR も足場である）。

### 著者が挙げた 4 課題と、調査で判明した正体

| 課題 | 正体 |
|---|---|
| バグ修正中の新バグが積まれて終わらない | **discovery ≠ task creation の分離が無い**。発見が即 permanent backlog node になる |
| 並行セッションで状態不明・衝突 | 共有可変ファイルの後勝ち消失。`claims.py` で着手済み、台帳本体は未解決 |
| ready 放置 | ready が 64k 文字に埋もれ、**loop が人間の起動を待っている** |
| blocked/deferred が認知資源を削る | 49 行が「今は動かさない」と決めたまま視界に残り続ける |

### 外部調査の結論（as-of 2026-08-15、3 系統が独立に一致）

- **課題1（fix/file/discard の判定規則）と work node 増殖の抑止は、2026-08-15 時点で未解決領域**。
  独立調査・Gemini レポート・ChatGPT レポートが独立に同じ結論。ここは自前設計になる
- 採用しない外部推奨とその理由:
  - 「散文を 3-5 行に圧縮」→ 根拠とされた [arXiv:2602.11988](https://arxiv.org/abs/2602.11988) は
    **repository-level context file** の研究で、task-level record は対象外。かつ有害だったのは
    *repository overviews* で *instructions は effectively followed*。さらに
    [arXiv:2607.12161](https://arxiv.org/abs/2607.12161) が「tool-output を 38.4% 削減して
    **billed cost は +6.8%**、r=0.15、aggressive compression は patch 成功率を下げる」と実測。
    **圧縮は解でない — 読まないことが解**
  - 「Stop hook で sweep を強制」→ ADR-0035 で Stop hook 3 本を配線ごと退役済み
  - 「WIP=1」→ 著者は並行セッション運用を明言。上限をかける場所が違う
  - 「発見物は既定で file」→ **既に実践済み**（`T-ADOPT-NAMED-SKIP-EXIT` 等）。
    台帳の肥大は scope creep の症状ではなく、抑制した結果

### 意図する結果

台帳を「人間が読む単一ビュー」から **「エージェントが問い合わせるストア + 生成される view」** へ移す。
セッションは全体を読まず、`ready` / `due` だけを受け取る。人間への説明は都度生成する。

---

## 決定事項（著者承認済み）

1. **1 タスク 1 ファイル**。`TASKS.md` は生成物へ降格
2. **markdown + lease 付き claim**（SQLite ではない）。衝突は「防止」でなく **「検出 + 期限切れ回収」**
3. **ready の溢れは aging で降格**（枚数上限ではない）。判断者を要さず機械が回る形

---

## 設計

### 3 層

| 層 | 場所 | 正本であるもの |
|---|---|---|
| store | `.notes/tasks/T-XXX.md` | タスクの状態と本文 |
| journal | `.notes/claims.jsonl` | 誰が握っているか / 系譜（実装済み） |
| projection | `scripts/tasks.py` の出力 | 問いへの答え。`TASKS.md` は render 結果 |

### 状態語彙 — `candidate` を 1 つだけ新設

```
candidate → ready → in_progress → done
              ↑ aging で降格 ↓
blocked / observing / deferred  （ready frontier の外）
```

- 現行 4 状態（ready / blocked / observing / deferred）+ `candidate` + `done`
- **`observation` は入れない**。未測定の機構を 2 つ同時に入れない
- `candidate` の役割は 2 つ: (a) aging の降格先 (b) 発見物の入口。
  skill `task-stocktake` が既に持つ「候補台帳（採否判断前の候補はタスクではない）」の
  概念を、wiki-harvest 型だけでなく**バグ発見にも拡張**する形

### frontmatter schema

```yaml
---
id: T-ADOPT-NAMED-SKIP-EXIT
state: ready              # candidate|ready|in_progress|blocked|observing|deferred|done
origin: review            # claims.py と同じ語彙: review|gate|instrument|idea|incident
parent: T-ADOPT-HOLD      # null 可
spawned: 2026-08-15
state_since: 2026-08-15   # aging の起点。state 変更時に更新
stale_after: 21d          # ready の aging 期限（省略時は既定）
watch:                    # ADR-0093 の注釈を構造化（blocked のみ）
  type: gh-pr             # gh-pr|http-status|http-post-status|file-exists
  target: owner/repo#123
defer_until: null
refs: [cli/adopt.py]
commit: null              # done のとき
---

本文は自由。観測記録・実測値・再現条件をそのまま保つ（圧縮しない）。
```

**本文は削らない。** 最長行 `T-CONSOLIDATOR-REDESIGN`（3,842 字）は
「Fable の探索を既存案へ収束させないため、観測された事実だけを置く」という
意図的な設計。圧縮は上記の実測により逆効果。

### query-first projection — `scripts/tasks.py`

読む量を減らす中核。**112 件を全部読ませない。**

| コマンド | 返すもの |
|---|---|
| `tasks.py ready [--limit N]` | 着手可能なものだけ、1 件 1 行の compact 形式 |
| `tasks.py due` | **今日状態遷移しうるもの**だけ（lease 切れ / watch fired / aging 到達 / defer 明け / done 掃除対象） |
| `tasks.py show T-XXX` | 1 件の全文（本文込み） |
| `tasks.py render` | `.notes/TASKS.md` を生成（**consumer 互換**） |
| `tasks.py age` | aging 判定を実行し、降格を journal に記録 |

`due` の述語（レポート2 の SQL 相当を Python で）:

```
state=ready       AND now - state_since > stale_after      → aging 降格対象
state=in_progress AND lease_expires_at < now               → stealable
state=blocked     AND watch fired                          → 解除条件が動いた
state=deferred    AND defer_until <= now                   → 復帰
state=done        AND Pending 節に残存                      → 掃除対象
```

### lease — `claims.py` の拡張

現状の `STALE_HOURS = 24` は**印を付けるだけ**で、自動 release しない
（docstring:「自動解除は check-then-act になる」）。**この判断は正しいが、lease は別物**:
期限を claim 時に**事前に**決めるので check-then-act にならない。

- `claim` に `--lease-hours`（既定 24）を追加。record に `lease_expires` を書く
- 期限切れ = `stealable`。`claim --force` なしで引き継げる
- **自動 release はしない**。stealable の判定を `open`/`due` が出すところまで
- docstring の「自動解除は race」の記述を、lease との違いを明記する形へ更新

### 発見物の入口 — 計測を先に

発見物は **`candidate` に入る。`ready` に直接入れない。**
`claims.py spawn` は既に `origin` / `parent` を記録するので、
**origin 別の流入率と消化率が測れる**（現状は正規表現で散文を分類する粗い推定しかできない）。

判定規則（fix now / file / discard）は 2026-08-15 時点で外部に前例が無いため、
**規則を先に決めず、まず 4 週間計測する**。計測なしに規則を入れると、
効果を切り分けられない（rule `feedback_abstraction_trap`: 行動変容の実証が先）。

---

## 変更するファイル

### ~/.claude（global harness）

| ファイル | 変更 |
|---|---|
| `scripts/claims.py` | lease 追加（`--lease-hours`、`lease_expires`、`stealable` 判定）。既存・未コミット |
| `tests/task-claims.bats` | lease のテスト追加。既存・未コミット |
| `hooks/task-claims-reminder.sh` | 出力に `ready` 件数と `due` 件数を足す。既存・未コミット |
| `rules/common/task-tracking.md` | 単一台帳方式 → 3 層方式へ規約更新 |
| `skills/task-stocktake/SKILL.md` | 台帳フォーマットと状態語彙の記述を更新、`candidate` を追加 |

### contemplative-agent

| ファイル | 変更 |
|---|---|
| `scripts/tasks.py` | **新規**。projection / aging / render |
| `scripts/migrate_ledger.py` | **新規・使い捨て**。既存 112 行を `.notes/tasks/*.md` へ分解 |
| `.notes/tasks/T-*.md` | **新規 112 件**（移行生成） |
| `.notes/TASKS.md` | 生成物へ降格。先頭に「このファイルは生成物」の注記 |
| `scripts/weekly-pipeline.sh` | `tasks.py due` の段を追加（第 8 決定論 intake） |
| `scripts/build_decision_packet.py` | §10 を「watch fired のみ」から `due` 全体へ拡張 |
| `scripts/ledger_condition_scan.py` | **無改修**（生成された TASKS.md を読む） |
| `docs/adr/00XX-*.md` | **新規 ADR**。3 層方式・lease・aging・candidate の判断を記録 |

### 再利用する既存資産

- `scripts/claims.py` の `repo_root()` / `append()` / `read_events()` / `age_hours()` — そのまま
- `scripts/ledger_condition_scan.py` の `_WATCH_RE` / `_GH_PR_RE` — watch 型の検証に再利用
- `.staged/` の 1 item 1 ファイル + `audit.jsonl` の append-only — 同じ形をタスク管理へ持ち込む
- skill `task-stocktake` の Phase 2/3（sweep / verify）— `tasks.py due` の判定に流用

---

## 実装順（各段で止まれる）

1. **`tasks.py` + 移行スクリプト**（read-only 検証まで）
   移行後の `render` 出力が現行 `TASKS.md` と意味的に等価であることを確認してから置き換える
2. **`claims.py` に lease**（bats 拡張つき）
3. **aging と `due`**、hook 出力の更新
4. **weekly chain 配線**（`due` の段、packet §10 拡張）
5. **規約更新**（rule / skill / ADR）

---

## Verification

### 移行の非破壊性（最重要）

```bash
cd ~/MyAI_Lab/contemplative-agent
# 移行前の consumer 出力を保存
python3 scripts/ledger_condition_scan.py > /tmp/before.json
# 移行 → render
python3 scripts/migrate_ledger.py --dry-run     # 差分を目視
python3 scripts/migrate_ledger.py
python3 scripts/tasks.py render > .notes/TASKS.md.new
# consumer が同じ読み値を返すか
python3 scripts/ledger_condition_scan.py --ledger .notes/TASKS.md.new > /tmp/after.json
diff /tmp/before.json /tmp/after.json      # 空であること
```

行数・ID 集合・状態分布が移行前後で一致することを assert するテストを付ける。

### 並行 claim / lease

```bash
cd ~/.claude && bats tests/task-claims.bats
```

追加する主張:
- lease 期限内は他セッションが `--force` なしで奪えない（exit 3）
- lease 期限切れは `--force` なしで奪える
- `open --oneline` が stealable を stale と区別して表示する
- lease 追加後も append-only（既存行が不変）

### projection

- `tasks.py ready` の出力が 2,000 文字以内（現状 64,090 文字からの削減を実測）
- `tasks.py due` が空の日は無音で exit 0
- `tasks.py show T-XXX` が本文を欠落なく返す（最長行 3,842 字で確認）

### aging

- `state_since` を 22 日前に偽装した ready が `due` に現れ、`age` で candidate へ降格
- 降格が `claims.jsonl` に記録される
- `blocked` / `deferred` は aging の対象外

### repo gate

```bash
cd ~/MyAI_Lab/contemplative-agent && .claude/verify.sh
cd ~/.claude && python3 scripts/harness_lint.py
```

---

## 未決（実装後に判断する）

- `stale_after` の既定値（21d は仮。移行後、現 ready 6 件の実年齢を見て決める）
- `candidate` → `ready` 昇格の規則（4 週間の origin 別計測を待つ）
- `deferred` / `observing` の TTL（外部に前例なし。計測が先）
- SQLite への移行（`claims.jsonl` に衝突イベントが実測されてから判断）
