# ADR-0095: タスク台帳機構の退役 — store と claims を残し、パースするものを全部落とす

## Status

accepted — supersedes ADR-0094; partially-supersedes ADR-0093

## Date

2026-08-16

## Context

ADR-0094（2026-08-15）はタスク台帳を 3 層に割った — 1 タスク 1 ファイルの store、追記専用の
claim journal、そして Markdown 表の projection（以下の台帳パスは ADR-0094 と同じく repo の
gitignored な notes ディレクトリからの相対）。projection を生かしたのは、その 1 日前にできた
ADR-0093 の stage 6c（`ledger_condition_scan.py`）が表を読む形だったからである。30 時間後、
その projection の周りの機構は 2,100 行（`scripts/tasks.py` 1,276、`ledger_condition_scan.py` 657、
`migrate_ledger.py` 131、`_md.py` 40）+ テスト 2,400 行になっていた。global の `claims.py` 509 行は別。

2026-08-16 に著者が問うたのは「週次レポート以降、なぜバグ修正が終わらないのか」だった。
`claims.jsonl` の系譜が答えた。`origin: review` で起票されたタスクは 12 件、閉じたのは 7 件、
閉じるたびに平均 1.3 件が新たに起票されていた — fix commit ごとにレビュー連鎖（code-reviewer +
security-reviewer + cross-model。それぞれ 900 行のファイルを全文再読）が隣接コードの既存問題を
閉じるより速く出していた。12 件のうち 7 件が台帳ツール自身の欠陥、2 件が packet builder の
文字列処理で、**エージェント本体のものは 0**。しかも台帳の 7 件は全部 projection 層 —
escape の衝突、pipe、閉じ忘れの `watch:` span、古い projection を健全と読む、制御文字で行が割れる、
restore CLI が無い。store 層（frontmatter + 自由記述）からは 1 件も出ていない。
シリアライズ形式が無いので、間違えようがない。

要件を言い直すと 4 つ: (1) repo ごとに状態付きタスク、(2) 全件読まずに「今着手できるものは」に
答える、(3) 並行セッションが同じタスクを掴まない、(4) blocked の解除条件を週次で照合する。
実態と照らすと、(1)(2) は frontmatter ファイルのディレクトリと `grep` 1 回、(3) は `claims.py`
で既に機能している（この ADR を書いている間も別セッションが 1 件 claim していた）、(4) が
守っていた本物の `watch:` 注釈は **3 件**（+ テスト例 1 件）で、走ったのは 2026-08-14 の 1 回。
要件 4 が機構の重さの半分以上を正当化していた。

大きさとは独立に、形そのものにも 3 つの問題があった:

- projection を残した 3 つの名目 —「消費者が表を読む」「人が開くファイル」「描画物を再パースして
  災害復旧」— はどれも弱かった。消費者は 1 日前にできたもので既に store 直読みに変わっていた。
  人はもう読まない（ADR-0094 の Context 自身がそう書いている）。gitignored な正本を描画物から
  戻すのは向きが逆（store を追跡するか backup に入れる）。
- 脅威モデルが道具に合っていなかった。symlink 拒否、制御文字クラス、path traversal、`\x00` —
  タスクファイルを書くのは著者自身のセッションだけである。`security-reviewer` の「be paranoid」を
  メモ帳に当て続けた結果、メモ帳がパーサ要塞になった。前日に値層について著者が下した判断
  （内容は脅威面ではない）が、ここには適用されていなかった。
- 使う前に計器を付けた。`origin` / `parent` 計測、`seq`、21 日 aging、`candidate` 状態 —
  この repo の「測ってから介入」の習慣（ADR-0071）は、観察対象が生き物である学習ループには
  正しく、観察対象が同じセッションの書いたコードである開発道具には過剰だった。ADR-0094 D6 は
  fix-now / file / discard 規則を「今入れると計測を汚す」として 4 週間保留したが、計測は 2 日で
  答えを出していた。

より深い原因は「スクラッチか外部ツールか」ではない。**スクラッチ + 無人のレビュー連鎖 +
「これは存在すべきか、どの大きさであるべきか」を問う段の欠如**である。`architect` agent は
まさにその問いのために存在するのに、インフラ作業で一度も呼ばれなかった。外部ツールなら連鎖は
止まっていた（reviewer は「そのツールのパーサを直せ」とは言えない）。明示的な上限を持つ
100 行のスクリプトでも同じだった。

## Decision

**1. projection・scan・migration を削除する。** `scripts/tasks.py`、
`scripts/ledger_condition_scan.py`、`scripts/migrate_ledger.py`、そのテストと fixture、
`TASKS.md`、weekly-pipeline の stage 6c、packet builder の `--ledger-watch` 入力と §10、
`ledger_watch_fired` metric。`scripts/_md.py` は残す — packet builder の `_cell` 床が使っている。

**2. store が台帳であり、文法は frontmatter だけ。** `tasks/T-XXX.md`。frontmatter に
`state:`（`claims.py` が既に宣言している語彙 — `ready` / `in_progress` / `blocked` / `observing` /
`deferred` / `candidate`、終端 `done` / `dropped` / `decided` / `retired`、日付を続けてよい）、
本文は自由記述。セクション名も列も escape も無い。

**3. 台帳を読むのは global harness の 1 コマンド。** `~/.claude/scripts/claims.py ready [--state S]`
がある状態のタスクを 1 行ずつ列挙し、claim 中のものに印を付ける。`claim` / `release` / `spawn`
の隣に置くので、状態語彙の所有者は 1 つになる。harness にも repo にも、これ以外に台帳を
プログラムで読むものは無い。

**4. 肥大は archive で解く。機構では解かない。** 終端状態のタスク（`done` / `decided` /
`dropped` / `retired`）は `archive/tasks/` へ移す。駐車中（`blocked` / `observing` /
`deferred`）は生きているディレクトリに残す — `ready` は状態で既に除外しているし、週次診断が
再提案を避けるために読む。ADR-0094 の aging（D3）と `candidate` intake（D4）が「queue が
減らない」への答えだったのを、これで置き換える。

**5. レビュー指摘の閉鎖規則。今日から。** diff の外の指摘は HIGH 以上だけ起票し、それ未満は
commit message に 1 行残して捨てる。起票するもののうち所有者の判断が要るものは
`state: candidate`。ADR-0094 D6 の計測期間はこれで早期に閉じる — 特徴づけようとしたループの
再生産数は 2 日で 1 を超えており、4 週間待っても尾が溜まるだけだった。

**6. 要件 4 は土曜ゲートに戻す。** blocked の条件 3 件は、人が週 1 回 `gh pr view` を打って
確かめる。機械照合可能な条件の数が人が 1 分で見られる量を超えたら、それが再考の signal —
まず外部ツールから。

## Alternatives Considered

**store 層を残して projection だけ消す。** `tasks.py` の約 600 行（aging、`due`、`seq`、
`render_task_file`）と、repo と global harness で二重定義された STATES 語彙が残る。要件 1〜3 を
満たすのに生き残る行は `claims.py` に足した約 70 行（うち列挙ループが約 20 行）である。

**`tasks.py` を丸ごと `~/.claude/scripts/` へ移す。** 著者は 2026-08-15 朝に「台帳の並行性は
global harness 側で扱う」と決め、同日夕方の ADR-0094 は 1 日前の scan が表を読むという理由で
repo 局所に建てた。ファイルを移せばパーサとそのバグが global 化するだけ。global 化するのは
要件であってコードではない。

**Backlog.md / HZL / tkr / GitHub Issues を採用。** 選択肢としては開いたままで、要件が増えたら
最初に評価するもの（`search-first`、その日の as-of で）。今日採用しないのは、生き残った要件が
ディレクトリ列挙 + `claims.py` で満たされており、残コード 0 行を消すために依存を足すのは取引に
ならないから。GitHub Issues はさらに「意図的にローカル」という配置を覆すので所有者の判断。

**stage 6c を残して入力形式だけ直す。** 3 件の注釈は、ネットワークに触る週次 stage、閉じた
status 語彙、4 つの fault code、packet の 1 節を正当化しない。ゲートで 3 行読む方が速い。

**削除でなく、レビュー連鎖に「存在すべきか」ゲートを足す。** 両方要る。この ADR は削除を行う。
ゲート側は global harness の変更（rule `task-tracking.md` が本日付で閉鎖規則を持つ。インフラ
作業の大きさ/存在の問いは記録したが、まだ配線していない）。

## Consequences

**Positive:**

- 約 4,600 行の削除（コード 2,100、テスト 2,400、fixture）に対し `claims.py` への追加 ~70 行。
  open だった review 起票 5 件のうち 3 件は存在しなくなるコードの件で dropped として閉じる。
- weekly chain から唯一のネットワーク egress を持つ決定論 stage が消える。
- 台帳を持つ 9 repo で状態語彙 1 つ、reader 1 つ、書き方の規約 1 つ。rule `task-tracking.md` は
  単一表と store の両形式を 1 段落で記述する。
- 閉鎖規則が構造的に review 起票の再生産数を 1 未満に抑える — 隣接コードの LOW 指摘の尾が
  台帳に入らなくなる。

**Negative / accepted:**

- blocked 条件の機械照合は無い。3 件、ゲートで手で見る。
- aging は無い。誰も始めない `ready` は stocktake が動かすまで `ready` のまま。
  `task-stocktake` が引き続き掃除役。
- `TASKS.md` は消える。`docs/evidence/adr-0094/` の evidence 文書と ADR-0093/0094 の本文は
  歴史としてそのまま。
- `claims.jsonl` の `origin` / `parent` 系譜は `spawn` が引き続き記録する（コストは無く、
  ここへ至る問いに答えたのはこれ）。それを集めていた 4 週間の計測は本決定で閉じる。

**記録しておく教訓（この repo でなく harness 向け）:** 読者が agent だけになった道具は、agent が
自分のために自分の基準で拡張し続ける。人間の「そこまで要らない」は、人間が読むのをやめた時点で
ループの外に出た。自律運用の本当のコストはタスクあたりの token ではなく、所有者の予算で agent の
ために建つインフラである。それに効く計器は、最後のレビューでなく、インフラ作業の最初に置く
「大きさ/存在」の問いである。

## Amendment (2026-08-16): 状態語彙に所有者がいなかった — 開状態 4 つ、名前でなく入場条件で締める

本 ADR が着地した当日の棚卸しで、上の決定が防がない失敗が 3 つ実測された。いずれも
機構ではなく語彙の側にあった。

**1. Decision 3 の前提が実装と一致していない。** Decision 3 は `state:` の語彙を
「`claims.py` が既に宣言している語彙」とし、`claims.py` が `claim` / `release` / `spawn` の
兄弟であることをもって「状態語彙には所有者が一人いる」と書いている。実際に `claims.py` が
宣言しているのは `EVENTS` / `OUTCOMES` / `ORIGINS` / `PRODUCER_REQUIRED_ORIGINS` の 4 つで、
**状態語彙の宣言は 1 行も無い**。`ready` は `--state` の既定文字列にすぎず、state は
不透明なトークンとして読まれる。語彙は実際には 4 文書（本 ADR の en/ja、skill
`task-stocktake`、rule `task-tracking.md`）に書かれ、5 つ目（skill
`weekly-report-diagnosis`）が消費し、誰も所有していなかった。**正本は skill
`task-stocktake` に定める**。他の文書は参照に落とし、定義を複製しない。

**2. `deferred` と `observing` を退役させる。** `deferred` は store の 42%（45 件中 19 件）を
占め、5 つの仕事を同時に担っていた — 便乗（「次に X を触る時に」）、signal-first
（「浪費が実際に起きたら」）、他タスク依存、実質決定済み、外部イベント待ち。加えて
**着手条件が空欄でも書ける唯一の開状態**であり（`T-L` の着手条件は「—」）、決めたくない
ものが全部そこへ落ちた。`observing` の退役理由は逆で、`blocked` との運用上の差が検討に
耐えなかった。初案は「`observing` は腐るが `blocked` は腐らない」を根拠にしたが、これは
誤りである — `T-OBS-REL`（blocked）の条件は「T-B1 窓明けの retune 判断と束ねる」で、
`T-B1` が閉じた瞬間に前提がずれた。

開状態は `candidate` / `ready` / `in_progress` / `blocked` の 4 つになる。終端は変更なし。

**3. 効くレバーは名前でなく入場条件だった。** 初案は 19 件を全部 `blocked` へ移すもので、
失敗モードを移送先へそのまま運ぶだけだった。`blocked` に置けるのは**条件成立だけで
`ready` へ移せるタスク**に限る — 成立後に「本当にやるか」の判断が残るものは `candidate`、
発生すればそれ自体で再発見されるリスクは将来の自分への予告として保持せず `dropped` に
する。条件は「何を待つか・どこで照合するか・成立時どうなるか」を書けなければならない。
文法上は名指しているが照合できない条件（「必要になったら」「保守コストが顕在化したら」）は
資格を満たさない。

**4. イベント条件は削除を決着に含める。** 条件が内部 artifact の**変更**を待つ場合、その
削除・置換もその条件を決着させる（→ `retired`）。`T-B4` は「view seed text の変更」を
待っていたが、ADR-0073 がその seed を削除したので trigger は永久に発火せず、1 ヶ月半
生き残った。時間窓は経過で必ず判定できるが、イベント条件は「発火した」と「発火源が消えた」を
区別しない限り判定できない。

**5. 便乗項目は台帳に置かない。** 条件が「次にこのファイルを触る時」なら、注記はコードの側へ
置く。計測窓では、そうしたタスク 2 件で対象ファイルが計 12 回変更され、1 回も拾われなかった —
`T-OBS-INJ` の `core/llm/__init__.py` は 8 回変更され、うち 1 回は当該ファイルを
`core/llm/` パッケージへ分割する変更で、タスクが対象としていたコードそのものを移設したが、
要求されていた audit ログは付かないままだった。台帳には「そのファイルを編集する人」への
経路が無く、Decision 3 の「これ以外に台帳をプログラムから読むものは無い」がまさにその理由で
ある。配送機構を足して解く問題ではない。

Decision 2 の語彙列挙と Decision 4 の駐車状態リストを上記に合わせて改める。Decision 3 の
読み取りコマンドは変更なく、変わるのは所有者に関する主張だけ。消費者も同じ変更で更新した:
skill `weekly-report-diagnosis` は `--state observing` を引き、駐車済みの介入を再提案しない
ために `blocked` / `deferred` / `observing` 行を照合していた — 存在しない state を指すと、
この段は何も返さず「駐車中の介入は無い」と読める。
