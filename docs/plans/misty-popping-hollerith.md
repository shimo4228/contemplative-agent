# タスク状態語彙の縮約 — `deferred` / `observing` 廃止と入場条件の導入

## Context

2026-08-16 の `/task-stocktake` で 3 つの失敗が実測された:

1. **2 ヶ月滞留** — `T-B1` / `T-C3` は 2026-06-17 に決着し、正本 `remaining-issues-2026-06-05.md` も
   両方 `✅ Done` と記録していたのに、台帳だけが `observing` / `blocked` のまま残っていた
2. **便乗トリガーの 12 回空振り** — 「次に X を触る時に同 PR で」型 4 件のうち 2 件で対象ファイルが
   起票後に計 12 回変更されたが全部素通り（`T-OBS-INJ` の `core/llm/__init__.py` は 8 回、うち 1 回は
   ファイルごとパッケージへ分割する大手術で対象コードは移設までされた）
3. **イベント条件の不死化** — `T-B4` は「view seed text の**変更**」を待っていたが、seed は ADR-0073 で
   **削除**された。条件は永久に発火しない

背景に語彙の肥大がある。`deferred` は store の 42%（19/45）を占め、着手条件の形で分類すると
5 種類（便乗 / signal-first / 他タスク依存 / 実質決定済み / 外部イベント）の仕事を兼ねていた。
`deferred` は**着手条件が空欄でも書ける唯一の開状態**で（`T-L` の着手条件は literally「—」）、
決めたくないものが落ちる先になっていた。

初案（`deferred` 廃止 → 19 件を `blocked` へ、`observing`/`blocked` は「データが積まれているか」で
分ける）は codex-review で 2 つの土台が崩れた:

- 「`blocked` は条件文を走査すればよい」→ **誤り**。`claims.py ready --state blocked` が印字するのは
  ID と**タスク節の 1 行目**で、着手条件ではない（実行確認済み）
- 「`observing` は腐るが `blocked` は腐らない」→ **誤り**。`T-OBS-REL`（blocked）の条件は
  「T-B1 窓明けの retune 判断と束ねる」で、その T-B1 を今日 done にした時点でずれた

Codex の再フレーム: **状態名の整理より open task への入場条件を狭める方が効く**。初案は 19 件を
移送するだけで、3 つの失敗モードは移送先へそのまま移動していた。

### 根本原因

ADR-0095 は `state:` を「`claims.py` が既に宣言している語彙」「so the state vocabulary has one owner」
と書いている（`0095:84-93`）。**これは事実ではない** — `claims.py` が定数として持つのは
`EVENTS` / `OUTCOMES` / `ORIGINS` / `PRODUCER_REQUIRED_ORIGINS` の 4 つだけで、状態語彙の宣言は
1 行も無い（`ready` は `--state` の既定文字列）。語彙は **4 文書に分散して書かれ、5 つ目が消費し、
所有者が不在**だった。所有者を決めないと同じ drift が再発する。

### 意図する結果

開状態を 6 → 4 に縮約し、`blocked` に入場条件を課すことで、条件を名指しできない項目が
開いたまま溜まれなくする。語彙の正本を 1 箇所に定める。

## 設計（確定済み）

### 開状態 4 つ

| 状態 | 定義 |
|---|---|
| `candidate` | 採否判断がまだ要る |
| `ready` | 今選べば着手できる |
| `in_progress` | claim 中 |
| `blocked` | 採用済みで、**条件成立だけで ready になる** |

`deferred` / `observing` は廃止。

### `blocked` の入場条件

本文に次の 3 行が書けなければ `blocked` に置けない。自由記述内の一文でよく、
機械可読フィールドにはしない（機構を足さない — ADR-0095）。

```
再開条件: X（観測可能な事実）
照合先:   Y（PR 番号 / ファイルパス / 依存タスク ID / ログ）
成立時:   ready
```

**条件成立後にもう一度「本当にやるか」を判断するものは `blocked` ではない** → `candidate`。
これが `deferred` の主要な受け皿になる。

### イベント条件の決着規約

条件が内部 artifact（seed / view / prompt / モジュール）の**変更**を待つ場合、
**削除・置換も条件の決着に含める**。対象が消えたら `retired`。`T-B4` 型の不死化への直接対処。

### 終端 4 つ（変更なし）

`done`（やった）/ `decided`（判断が出た）/ `dropped`（やらないと決めた）/
`retired`（対象の側が消えた）。使い分けは 2026-08-16 に `task-stocktake` へ記載済み。

### 語彙の正本

**`~/.claude/skills/task-stocktake/SKILL.md`**（今日の終端語彙節と同じ場所）。
他の 4 文書は参照に落とす。

## 変更範囲

### 1. 語彙の正本 — `~/.claude/skills/task-stocktake/SKILL.md`

`## Phase 1` 直後の状態語彙節（現 l.44-46）を書き換える:

- 開状態 4 つの定義表
- `blocked` の入場条件 3 行
- イベント条件の決着規約
- 既存の「終端語彙の使い分け」節はそのまま残す（今日追加、承認済み）
- 併せて Phase 1 の store 段落（現 l.49-53 相当）と Phase 3 の 3 分類から
  `observing` / `deferred` への言及を除く

`origin: shimo4228` の自作 skill なので編集に制約なし。

### 2. rule — `~/.claude/rules/common/task-tracking.md`

l.10-14 の store 段落。状態の列挙を 4 語 + 終端 4 語に更新し、**定義は複製せず**
`skill: task-stocktake` が正本であることを 1 行で示す（今日入れた終端語彙のポインタを
語彙全体に広げる形）。二重定義を避けるのが目的。

### 3. ADR-0095 追補 — `docs/adr/0095-*.md` と `.ja.md`

1 日前の ADR なので新規 ADR でなく **Amendment 節**を両面に足す。内容:

- Decision 2 の語彙列挙（en `l.85` / ja `l.67-68`）から `observing` / `deferred` を外す
- Decision 4 の parked states（en `l.98` / ja `l.77-78`）を `blocked` / `candidate` に
- **Decision 3 の事実誤認を訂正** — 「`claims.py` が語彙を宣言しており所有者が一人いる」は
  実装と一致していない。正本は skill であると明記
- 追補の根拠に本日の 3 実測（滞留 / 空振り 12 回 / 不死化）を 1 行ずつ

`docs/CODEMAPS/architecture.md` の Data Flow は台帳機構が退役済みで記述を持たないため対象外
（`grep` で確認すること）。

### 4. 消費者 — `.claude/skills/weekly-report-diagnosis/SKILL.md`

**2 箇所**。直さないと週次無人チェーンが保留済み介入を F1 として再提案し始める。

- `l.40` — 必読資料の説明。`claims.py ready --state observing` の例と
  「`observing` / `deferred` 行が今週のシグナルを既に予約・却下していないか」を
  `--state blocked` / `--state candidate` ベースに書き換え
- `l.102` — 自己点検チェックリストの「pending (`blocked` / `deferred` / `observing`)」を
  `blocked` / `candidate` に

### 5. タスク 28 件 — `.notes/tasks/`

`deferred` 19 + `observing` 9。**個別の振り分けは設計確定後に別途判断**（著者の指示）だが、
適用する判定パターンは以下:

| 現状 | 判定 | 行き先 |
|---|---|---|
| 条件成立だけで ready になる | 条件 3 行を書けるか | `blocked` |
| 成立後に再判断が要る（signal-first の多く） | — | `candidate` |
| 発生すれば自然に再発見される | — | `dropped` |
| 対象・機構が既に消えている | ADR / commit を引用 | `retired` |
| 便乗（「次に X を触る時に」） | **未決 — 下記** | 暫定 `candidate` |

`.notes/` は gitignored なので、着手前に scratchpad へ tar バックアップを取る
（本日 2 本取得済みの手順と同じ）。

## 未決の 1 点

**便乗型 4 件**（`T-OBS-INJ` / `T-REPLY-PACING` / `T-OBS-EMB` / `T-EXTRACT-TITLE`）は
この語彙では解けない。`blocked` に入れても条件（「次に `embeddings.py` を触る時」）が
編集者に届かないのは変わらず、12 回空振りの実測がそれを示している。

これは**状態の問題ではなく「台帳に何を載せるか」の問題**。選択肢は (a) 注記をコード側の
コメントへ移して台帳行を閉じる（先例: `T-OBS-REL` の詳細は `feed_manager.py:369 コメント`）、
(b) 台帳に残して `candidate` にする、(c) 任意改善として `dropped`。

本計画では**暫定 `candidate`** とし、語彙変更の完了後に単独の議題として扱う。

## 実行順序

1. バックアップ（`.notes/tasks/` → scratchpad の tar）
2. 語彙の正本を書く（skill）← 以降の全編集の参照元になるので最初
3. rule をポインタ化
4. ADR-0095 追補（en / ja 同時 — 片面だけ直すと head 比較で見えない drift になる）
5. `weekly-report-diagnosis` の 2 箇所
6. タスク 28 件を判定パターンで振り分け（1 件ずつ本文の着手条件も書き換える）

2〜5 は互いに独立。6 は 2 が終わってから。

## Verification

```bash
# 1. 廃止語が台帳・文書に残っていないこと
grep -rn "observing\|deferred" .notes/tasks/ docs/adr/0095-*.md \
  .claude/skills/weekly-report-diagnosis/SKILL.md \
  ~/.claude/skills/task-stocktake/SKILL.md ~/.claude/rules/common/task-tracking.md
# → ADR 追補内の「廃止した」という記述以外はゼロ

# 2. 各状態が引けること / 分布
python3 ~/.claude/scripts/claims.py ready
python3 ~/.claude/scripts/claims.py ready --state blocked
python3 ~/.claude/scripts/claims.py ready --state candidate
# → 未知 state を引くと「タスクはありません」（claims.py は語彙を検証しない = 既知の仕様）

# 3. blocked 全件が入場条件 3 行を持つこと（手動確認 — 機械検査は作らない）
for f in .notes/tasks/*.md; do grep -q '^state: blocked' "$f" && \
  { grep -q '再開条件:' "$f" && grep -q '照合先:' "$f" || echo "MISSING: $f"; }; done

# 4. リンク健全性が 0 本のまま（本日 142 本修理済み）
#    → 本セッションで使った Python の照合スクリプトを再実行

# 5. 消費者が実在 state を指すこと
grep -n "claims.py ready --state" .claude/skills/weekly-report-diagnosis/SKILL.md
```

**エンドツーエンド確認**: `weekly-report-diagnosis` skill を読み、`.notes/tasks/` を
実際に引いて F1 重複判定ができるか（無人チェーンが土曜に踏む経路）。skill が指す
`--state` が実在しないと、この段は黙って空を返して「予約済みの介入は無い」と読む。
`grep` で state 名を確認するだけでは足りず、コマンドを 1 回実行して行が返ることを見る。

## 非対象

- `claims.py` への語彙定数の追加（著者判断で skill を正本にしたため。コードを増やさない）
- 台帳を読む新しい機構・配送機構（ADR-0095 の制約）
- 便乗 4 件の最終処分（上記「未決」）
- 公開 repo への同期（`/harness-sync` は別途、外向き操作）
