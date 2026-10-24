# ADR-0116: 承認ゲートの記録は「責任の行為」である

## Status

accepted — partially-supersedes ADR-0012（代替案 1 の却下理由、「Claude Code がオーケストレーターの場合」の注意書き、監査行の欄の定義を置き換える。ゲートそのもの、「`--auto` を持たない」、判断表、フローは存続）

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session
decided-by: owner (D-P1-12-1 = A, D-P1-12-2 = B, 2026-10-24)
date: 2026-10-24

## Layer

mechanism

## Context

ADR-0012 は人間の承認ゲートを構造にし、ADR-0080 の 2026-08-26 追補は「ゲートに残る人間の言葉」を帰属の錨とした。ゲートが残す記録にはその言葉が載っていなかった。2026-10 のロードマップ点検（P1-12）は、プロジェクトが言うことと `audit.jsonl` にあるものの間に 5 つの隙間を見つけた。

1. 行は承認・却下が**あった**ことしか言わず、**誰が**・**なぜ**・**どの経路で**を言わない。対話の y/N、`--adopt-names`、`--reject-names`、`--yes` の行は、自由文字列の `source` でしか区別できない。
2. `adopt-staged --yes`（source `stage-adopted-auto`）は「非 TTY の coding-agent ワークフロー用」と文書化されていた。コードは ADR-0012 代替案 1 が却下した経路（「`--auto` … Claude Code は結果を読んで承認を判断できる」）をそのまま符号化し、同 ADR の注意書き（「Claude Code がオーケストレーターの場合、承認フローを検討する必要がある」）は開いたままだった。この経路で憲法改正が 2 件、理由の記録なしに採用された。
3. 却下は staged の本文を `unlink` していた。人間が何に No と言ったかの痕跡は 16 hex のハッシュだけだった（README は却下された skill 提案 547 件を一次データとして数えている）。
4. 採用・却下の経路は監査行の書き込み失敗を無視していた（log-and-continue）。記録が無いまま store に採用が入り、プロセスが exit 0 で終わりうる。
5. `path` は書いたマシンの絶対パスだった。承認されたバイト列を持ったことのないパスを指す行が 2 つあり、staged の行は候補を生成した run の snapshot への鍵を持たず、公開ファイルだけでは決定を run に結べなかった。

本リポジトリを記入例として引く Accountable-AI-practice 側（その ADR-0005 / 0006 / 0008）は、まさにこの ADR が与える記録 — 名前のある人間の承認者と時刻、却下ごとの理由、「交渉不能」な監査記録 — を前提にしている。

## Decision

### D1. `--yes` は TTY 回答の代替であり、人間の理由を運ぶ（D-P1-12-1 = A、owner、2026-10-24）

`adopt-staged --yes` は `--reason TEXT` を要する（無ければ何も触らず exit 2）。打つのは人間が立ち会い、batch を読んだセッションだけで、理由はその人間の言葉である。**Claude Code は説明係・転記者であって承認者ではない**（weekly-gate Step 1b / ADR-0085 / ADR-0098）。`stage-adopted-auto` を coding-agent 経路と記述していた `cli/approval.py` の docstring はそれに合わせて書き換える。ADR-0012 の代替案 1 は、その理由の一部についてのみ却下のまま立つ: 自動スキップは今も提供しない。一括の `--yes` を提供するのは、ゲートが人間の行為であり、記録がそう言うようになったからである。

### D2. 行の欄

`_log_decision`（行形状の唯一の所有者）は、既存の欄に加えて全行に次を書く。

| 欄 | 意味 |
|---|---|
| `reason` | 人間の自由文の理由（`--yes`・`remove-skill`・理由を持つ names-file 行で必須） |
| `reason_code` | enum `duplicate \| off-constitution \| low-quality \| stale \| other` — プロンプトを介さない**すべての却下で必須**（names-file 行のコード、または `--reason-code`）。端末のプロンプトでの却下は理由を尋ねる |
| `channel` | `tty \| names-file \| yes-flag \| headless` — 呼び出し側が上書きしない限り `source` から導出 |
| `session` | 決定が下されたセッション（`CLAUDE_CODE_SESSION_ID` / `MOLTBOOK_GATE_SESSION` / `--session`）。無ければ null |
| `approver` | 決めた人間。D3 |

`path` は対象が `MOLTBOOK_HOME` の中なら相対、外なら絶対で記録する（`snapshot_path` も同様）。行・ファイル・gate 記録を結ぶ鍵は `content_hash` で、`path` は参考にすぎない。`held` は歴史的な decision 値として schema に残る。

`AuditSource` には `correction`（D6）を足す。予定されている `takedown`（P3-05.14 の抑止リスト適用、approver 付き）は、書く側ができるまで**足さない**。schema の enum はコードの enum と等しく、テストで強制する。

### D3. approver は人間の文字列であり、定数ではない（D-P1-12-2 = B、owner、2026-10-24）

names FILE は先頭に署名行 `# approver: <名前>` を持てる。`--approver NAME` も同じ意味で、両方あれば一致していなければならない（食い違えば exit 2）。環境変数 `MOLTBOOK_OPERATOR` は 2 人目の署名者のための override であり、真実の源ではない。コードは既定の名前を埋めない — 固定の環境値は誰が打っても同じ文字列になるからである。登録名は `docs/GOVERNANCE.md`（*Accountable operator* 行と `Registered approver:` 行）にある。週次の `gate_item` イベントも同じ `content_hash` と `approver` を持つので、1 つの人間の文字列が audit 行と gate 記録の両方に届く。

names-file の書式は `名前<TAB>理由コード<TAB>自由文`、2・3 列目は省略可（`-` か空は「なし」）。列ができる前に書いたファイルもそのまま読める。

### D4. 却下された本文を残す

すべての却下経路（名指し、`--reject-rest` の一括、プロンプトでの却下、staged を介さない直接のプロンプト）は本文を `MOLTBOOK_HOME/.rejected/<UTC ts>-<content_hash>.md`（mode 0600）へ残す。`adopt-staged` の経路は行を書く**前**に残す。staged を介さない直接のプロンプト（`--stage` なしの insight / distill-identity / amend-constitution）は行を先に書き、本文はあとでベストエフォートで残す。ファイル名は監査行の `content_hash` を同じ関数で計算したものなので、行からファイルに辿れる。憲法・identity の候補も同じ経路で扱う。ディレクトリは公開 sync（`sync-research-data.sh`）の除外に入り、private の runtime backup が運ぶ。公開するかどうかは別の決定（P2-05）。

### D5. 記録が無ければ決定もない

`adopt-staged` の採用・却下の経路は `_log_decision` の false を無視しなくなった（staged を介さない直接のプロンプトは行を先に書き、書き込み失敗を無視する。対話用で無人ではない）。行が disk に届かなかった採用は**行われない** — store は無変更、staged の item は残り、run は exit 1。却下は行が失敗したら item を staging に戻し（残した複製も消す）、本文を残せなかった却下は進まない。従来の「unlink を先、記録を後」の順序（まだ staged の item を却下したと言う行を作らない）は保たれる。

### D6. 完全性モデルと訂正

`audit.jsonl` は append-only（`O_APPEND`、umask 0177 → mode 0600）で、rotate せず、週次の private backup（git 履歴）に含まれる。改竄検出の面は `prev` ハッシュ鎖（ADR-0012 の 2026-10-09 注記）である — 編集・削除・並べ替えは後続行のリンクを壊す。検出できないもの（ファイルを持つ者による全書き換え、末尾の切り落とし）はその注記のままで、以前の「git 履歴のみ」という記述はそれに置き換わる。`content_hash` は識別子であって署名ではない。

ログが append-only なので、誤った `path` の訂正は新しい行になる: `command: correction`、`decision: corrected`、`source: correction`、`corrects_ts`・`mv_from`・`mv_to`・`sha_checked`（live ファイルの digest が訂正対象の行の `content_hash` と等しいことを確かめたもの）・訂正した `approver`。`scripts/audit_correction.py` が書く（既定は dry run、hash が合わなければ拒否）ので、他の行と同じく鎖のリンクを持つ。既知の 2 件は 2026-08-09 の憲法と 2026-08-15 の identity の採用（ADR-0090 / ADR-0091）。`scripts/value_layer_approval_join.py` は訂正を判定でなく注記として扱い、訂正された行を approved-but-not-live の検査から外す。

schema は `schemas/audit.schema.json`。`tests/test_audit_schema.py` が実在する全 writer 経路の行を schema に照合するので、schema を更新しない新 source・新 key は CI で落ちる。

### D7. 決定から snapshot に届く

producer の pivot snapshot を staged item の `.meta.json` に `snapshot` として書き、`stage` 行と全採否行の `snapshot_path` に転記する。join の規則は schema（`x-join`）に置く: 採用行 → stage 行は `content_hash`、stage 行 → snapshot は `snapshot_path`、無ければ manifest の `run_id`、無ければ時刻近傍（「推定」と印す）。`scripts/snapshot_resolve.py` が公開ファイルだけでこれを辿り、snapshot が回転で消えた版は `rotated` と表に出す。

## Review-when

- この変更後の最初の土曜ゲートで、人間の立ち会いのない `--yes` 採用、または登録名にない `approver` が出た: コードでなく運用が D1/D3 に反している。
- 4 週連続で approver の欠落・登録外が無く、`gate_item` が全件解決する: approver 行を毎週読むのをやめる（下記）。
- 2 人目の approver が任命される（P4-03.2）: D3 の登録表と署名行に引き継ぎ行が要り、`--yes` の「人間が立ち会う」も見直す。
- data repo に決定の投影が入る（P2-05.2）: `snapshot_resolve.py` がそれを直接読み、schema の join 規則を照合し直す。

### Consumption plan

追加した読み値は 3 つ。それぞれのヘッダに消費計画がある（ADR-0101）。

- **approver 行**（`value_layer_approval_join.py`）— 週次レポートが週 1 回読む。4 週連続でクリーンならレポートから外し、schema/テストの検査に任せる。欄の撤去とともに撤去。
- **`scripts/gate_item_audit_join.py`** — ゲートセッションが土曜に Step 7 の後で 1 回走らせる。4 週クリーンで手動実行をやめる。`gate_item` が `content_hash` を持たなくなったら撤去。
- **`scripts/snapshot_resolve.py`** — 再現ガイドや RCA が決定の適用版を名指す必要があるときに読む。`rotated` の版数で snapshot 保持の変更（P3-04.1）を決める。8 週新たな `rotated` が出なければ週次の経路から外し、release gate としてだけ残す。

## Alternatives Considered

1. **`--yes` を `--adopt-names` 全件列挙の糖衣にする**（D-P1-12-1 案 B）。却下: 憲法 runbook の step 4 と「batch 全部を採用する」週のすべてに、staging の中身を写すだけのリストが要る。
2. **`--yes` を「監督された coding-agent セッションの TTY 代替」のまま、例外を accountability practice に書き戻す**（案 C）。却下: practice が承認者でないと言うエージェントを、承認者として記録してしまう。
3. **環境変数の固定値を `approver` にする**（D-P1-12-2 案 C）。却下: 誰が打っても同じ文字列になる。行為でなく設定の記録になる。
4. **人間がすべてのゲートコマンドを自分で打つ**（案 A）。必須にしない: 署名行が、batch を読み終えた人間にタイプを移さずに、同じ「人間由来の文字列」を与える。
5. **行が失敗したら採用をロールバックする。** 却下: 監査済みの書き込みを巻き戻すこと自体が監査されない変更になる。行を先に書いてから書き込む。
6. **`.rejected/` を今すぐ公開 sync に入れる。** P2-05 へ延期: 人間が断った本文の公開は、それ自体が開示の決定である。

## Consequences

### Positive

- 行が行為として読める: 名前のある人間、その人の言葉の理由、通った経路、転記したセッション。
- 却下は復元でき、`content_hash` で引ける。547 件の却下データが本文を失わなくなる。
- 記録の無い採用は起きない。exit code がそう言う。
- schema は writer が実際に出すものに CI で照合される。

### Negative

- ゲートが少し多くを求める: `--yes` の理由、プロンプトを介さない却下のコード。これ以前に書いた裸の `--reject-names` ファイルは、コードを足すまで exit 2 で落ちる。
- `approver` は人間の申告であり、暗号的なものではない。ハッシュ鎖は編集を検出するが、誰が打ったかは検出しない。
- 2026-10-24 より前の行は絶対パスのままで、新しい欄を持たない。読み手はそれを許容し続ける必要がある。

### Reversal cost

D2–D5 は低い（欄は追加で、無視する読み手もそのまま動く）。D1 は CLI の契約で、`--reason` を戻すと `--yes` はまた無言になる。

## References

- `ADR-0012`（`0012-human-approval-gate.md`）— 本 ADR により部分的に supersede される。
- `ADR-0080`（`0080-north-star-layered-end-state.md`）— 2026-08-26 追補がゲートの人間の言葉を帰属の錨とする。
- `ADR-0085`、`ADR-0098` — 土曜ゲート。説明係としての Claude Code。
- `ADR-0090`、`ADR-0091` — D6 が記録する、手で直した 2 件の採用。
- `ADR-0097`（D5）— D4 が可逆性を写す archive の出口。
- `ADR-0101` — 上の読み値の消費計画。
- `ADR-0020` — pivot snapshot（D7）。
- `docs/GOVERNANCE.md` — 役割、登録された承認者、各記録の所在。
