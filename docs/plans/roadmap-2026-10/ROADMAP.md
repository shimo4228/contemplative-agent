# Contemplative Agent 完成ロードマップ（2026-10 版）

> **凍結版**（P2-01.10）。2026-10-11 にオーナーが採択（project thread の「進めて」）し、同日この形で repo に固定した。以後この文書は書き換えない — 採用後の変更は [`decisions.md`](decisions.md) の dated 節に足す。束の閉じは [`closures.md`](closures.md)。付録は同じディレクトリの [`appendix-all-items.md`](appendix-all-items.md) / [`appendix-method.md`](appendix-method.md)。


作成日: 2026-10-10 ／ 対象: `shimo4228/contemplative-agent` v2.12.0（HEAD `2cad850`、2026-10-09）と兄弟 repo（`-data` / `-otel` / `-cloud` / `-mlx` / `-rules`）／ 依頼: 「プロダクトの足りていない点・品質向上が必要な点を洗い出し、もう付け足す点がないロードマップにする」

## 要約（1 ページ）

**結論**: ADR-0080 の 5 層のうち、今「完成」と言えるのはセキュリティ層だけで、それも公開データ側に 2 か所破れがある（embedding 入り 72 MB の `.bak`、第三者投稿の逐語断片）。機構層は止まっていない上に「止まった」の計測単位が無く、自己調節（人間ゲートの負荷→0）は定義すら無い。価値層は legible だが記録に穴がある。研究層は 3 つの問いに操作的定義が無く、論文も対照条件も無い。終わり方は予約のまま。

**規模**: 18 観点のレビューで 779 項目（全件 `path:line` つき）を挙げ、39 の作業束・360 項目に統合し、異なるペルソナによる穴探しを 第 1 ラウンド（10 視点）で 38 件、第 2 ラウンド（8 視点）で 33 件、第 3 ラウンド（8 視点）で 23 件、第 4 ラウンド（5 視点）で 2 件 の新規指摘を採用（既存項目への吸収を含む）して回し、第 4 ラウンドで新規が 2 件に減り指摘の大半が整合の直しになったので、オーナーの判断でそこで打ち切った（付録 B.2）。オーナーの決定が要るものは 99 件（熟慮 40 件、既定可 59 件。既定可でも `decision` は人間が打つ）。やらないこと（却下・延期の記録）は第 5 章に理由つきで約 151 件。土曜ゲート 1 回に決定 ≤ 5 件（熟慮 ≤ 3）・着手束 ≤ 2 の規約で配ると、10〜12 月の 12 ゲートに 55 件、2027-01-09〜03-06 の 9 ゲートに 43 件が載る。03-13 からの 3 回は繰り越し用に空けてある（4.0 の表）。この規約を守ると Phase 1 の束は着手が 2027-01 まで延び、Phase 1 の期限は 2027-03 になる。

**最初の 4 週（土曜ゲートごと。10-10 の決定は 10-17 に遡及記録する）**

| ゲート | やること（束） | 決めること |
|---|---|---|
| 10-10 | insight 再開後 3 回目の読みを材料に RFC-0042 / 0023 を終端し、RFC-0048 再開の材料を揃える（P0-01.1〜.7）。公開 data repo から embedding 入りの 72 MB `.bak` を外す（P0-03.1） | 入口の運用（継続 / 凍結 / 月次）、RFC-0023 の withdraw、`_gc_trash/` の扱い |
| 10-17 | 木曜 03:00 の submolt-scan の読みを Step 1c の D-P0-02-1 行の照合コマンドで確かめ、go を記録する。旧 relevance gate の削除 PR は 10-12〜16 に branch で用意しておき、merge はゲートの後の別セッション（P0-02）。T4 第 2 回で計器の読み手を 4 値で棚卸しし、滞留 sweep を裁く（P1-04）。weekly-gate SKILL の同梱 PR（Step 0 時刻表・Step 1c ロードマップ決定・T4 チェックリスト・`gate_start`）は前日までに merge。決定と削除 PR では最も重い週 | 読みが不成立のとき v2.13.0 をどうするか、ADR-0112 退役部分の記録、却下台帳を「既知」に含めるか、sweep の撤去、snapshot 保持方針（11-01 の prune 前） |
| 10-24 | P0-03 の残り（除外 allowlist の反転・絶対パス・スキャン・第三者断片の測定と文言訂正、無人 force push の停止）を 10-19〜23 の平日に入れる。ゲートの後は 06:00 JST セッションの蒸留取りこぼしの修理に着手し（P0-04.1。実数は P0-04.2 に記録）、10-31 の憲法 due に向けた P0-07 の計器 PR を 10-26〜30 に入れる。項目数では 10 月で最も重い週（P0-03 の残りと新しい script 2 本） | RFC-0040 の終端、版履歴の置き場、stage 7d / 7c の撤去、baseline 4 件の裁定 |
| 10-31 | 憲法改正 due は「読みのみ」を既定にし shadow 系列を取る（P0-07 の決定 2 件）。snapshot の prune は 11-01 より前、10-26〜30 に merge（P3-04.1）。土曜当日は読みのみで軽いが、前の平日は 10 月で最も Ollama の読みが多い（IPD の null pair・shadow 2 run・score 150 行で推定 6〜8 時間。前夜に起動すれば在席は要らない） | 改正を起動するか、shadow の月次配線、`adopt-staged --yes` と AAP 0005 の整合、cloud repo の維持 / 凍結 / archive、ロードマップ項目と commit の結び方 |

**11 月**: 11-07 / 11-14 の 2 ゲートで v2.13.0 の形を決め、tag は 11-16〜20 の平日に打つ（P0-05 / P0-06: Python 床 3.11・配布単位・CHANGELOG と DOI・Quick Start・uv.lock・契約キット）。11-21 は公開データの版と backfill（履歴の書き換え、第三者断片の伏せ字、takedown 手順）。11-28 は ADR-0080 追補（2026-11） の材料（負荷の定義、代謝の下限、headless Claude Code の位置づけ、凍結の読み方、人間の言葉として残す接点）。並行して v2.13.0 前の先行項目（障害表・census 規則・鍵まわりのコード修理など。4.0 の「先行項目」列）が平日に入る。

**12 月**: 12-05 に relevance face の閾値と真値（D-P1-15-1 / -2）と RFC-0048 層 1（P2-07.5 の境界草案の後、D-P2-07-1）、12-12 に研究問い Q4・AI 判断役の権限・2 層公開、12-19 に終わり方（追補（2026-12））、12-26 に otel / rules の処遇・研究対照（dialogue）。face ループの昇格先は 2027-01-09（D-P1-02-2）、論文の主題と「空性のみ公理」案は 2027-02-13。作業束では CI とテストの信頼性（P1-08）と RFC 台帳（P1-02）が年末に始まる。

**2027-01〜03**: 01-09〜01-30 の 4 ゲートで承認証跡の approver・ADR 台帳の規約・コード構造・文書の言語方針を決め、Phase 1 の残る束（批准経路・構造・アダプタ・文書・境界表）に着手する（01-02 は休み）。02-06〜03-06 の 5 ゲートで Phase 2 の実装（sync と watchdog・無人チェーン・公開 2 層・層 1）と、論文の主題・研究対照・wind-down runbook を決める。凍結の判定は、停止リストが空になってから窓が満ちる週で、推奨どおりなら早くて 2027-05-01。

**2027-Q2**: Phase 2 の読み（負荷 3 系列と自己調節の週次読み、読み量削減）、研究の結晶化（装置境界表、版履歴、対照条件、データセット再利用性、論文 1 本目は harness 層の責任構造を主題に SSRN / Zenodo）、公開データの最終形の決定。

**構造的に最も重い論点 4 つ**

1. 無人週次チェーンが headless の Claude Code（`claude -p`）を前提にしている。ADR-0080 08-26 追補 §A の「Claude Code の日常的関与なく自己調節」と構造的に矛盾するので、機構層と見なすか作業環境と見なすかを決めないと「負荷→0」の判定ができない（P2-02、D-P2-02-1）。
2. 承認ゲートの記録が「責任を取る行為」として未完成。誰が・なぜが無く、却下本文は破棄され、AI 判断役が 9 月 15 日以降 merge/push しているのに CYCLES.md は「Every promotion stays human」のまま（P1-12 / P1-13）。AAP の記入例として本体を使うには、ここが先。
3. 研究層に問いの操作的定義が無い。オーナーの主関心（ゲート負荷と価値層の legibility、harness 層の責任構造）は建立時の 3 問いに入っていないので、第 4 の問いとして立てるかを決める（P3-01、D-P3-01-1）。これが論文の主題（P3-06）と公開データの最終形（P3-05）を決める。
4. RFC-0048 層 1（決定論の自動退役。D-P2-07-1、旧 D-P0-01-4 を統合）は、ADR-0080 の「人間の言葉はゲートの attribution の錨」と ADR-0105 の「無人チェーンは store に触れない」に境界を接する。可逆性では省略の理由にならないので、ADR-0080 への dated amendment を先に起票し、A（例外を認める）か B（候補提示まで）をオーナーが `gate_record` に残す（P2-07.5、D-P2-07-1）。

**やらないこと（要点）**: 資金・商用・人員拡大、cloud や大型モデルの本番既定化、人間ゲートの溶解（LLM の判定が人間の裁定を置き換えること）、Jev（RFC-0040）の本番化、自動停止・自動修復、Moltbook 閉鎖時の移植、2 体目の本番化、価値層への直接介入（「空性のみ公理」の本番適用）、新しい LLM 判定者の追加、ロードマップ決定の自動採択。理由は第 5 章。

## 0. この文書の読み方

**「完成」の定義は ADR-0080（2026-08-26 追補を含む）の層別完成条件**をそのまま使う。機構層は「止まる」こと **かつ** Moltbook とのフィードバックループがオーナーと Claude Code の日常的関与なしに自己調節して回ること（人間ゲートは権限として残り、負荷が 0 に近づく）。価値層は到達点を持たず、legible な進化が続くこと。研究層は建立時の問いが論文として結晶し拡散されること。セキュリティ層は absence が維持されること。終わり方は設計されていること。本文書はこの 5 条件を「判定表」（第 2 章）に展開し、満たすための作業を**フェーズ × 作業束**（第 3 章）に並べる。

**読む順番**: 急ぐなら第 4 章（オーナーの決定が必要な事項）→ 第 3 章 Phase 0 → 第 2 章。全体像は第 1 章 → 第 2 章 → 第 3 章の順。第 5 章は「載せなかった提案」とその理由で、却下の記録として読む。

**項目の様式**: 各作業束（`P<フェーズ>-<番号>`）は「狙い」「期限・順序」「束の完了条件」を持ち、その下に項目（`P0-01.3` のような番号）が並ぶ。項目は 5 行（instrument は消費計画の 1 行を足して 6 行）で、落とした番号は欠番のまま残す（ID は他文書から参照される）。

- **何を**: 動詞から始まる具体的な作業
- **根拠**: `path:line` / commit / 引用（レビュー担当が実際に開いて確認したもの。付録 A から元項目に遡れる）。`path:line` は次の commit の行を指す: 本体 `2cad850` / data `a0428f4` / rules `eec96a4` / otel `ca9479f` / cloud `65b0526` / mlx `2f6c7fd` / AKC `3d42a66` / AAP `af2db90`（いずれも 2026-10-09〜10 の HEAD）。年の無い `MM-DD` は 2026 年、2027 年の日付は常に年つきで書く
- **完了条件**: 機械で判定できる形（テスト名・ファイルの存在・数値・コマンドの終了コード・ADR/RFC の state）を優先
- **規模・整合**: 規模 S/M/L（S = 平日の Claude Code 1 セッション・PR 1 本、M = 2〜3 セッション・PR 2〜3 本、L = 複数週か GPU 時間）と、ADR-0080 のレビュー・レンズによる分類（下記）
- **出典**: 18 観点のレビューで付けた元項目 ID（付録 A の表と対応。`R1-`〜`R4-` で始まる ID は穴探しラウンドの新規項目で、付録 A の末尾の表にある）
- **消費計画**（instrument のみ、最終行）: (a) 誰が・いつ読む (b) 何回の読みで何を決める (c) 撤去条件（ADR-0101）

規模・整合 の行末には `依存:`（先に要る項目）、`順序:`（同じファイルを触る先行 PR）、`注:` を書いてよい。整合分類は 1 項目に 1 つ。挙動を変える項目は完了条件の文中に「書き換える既存テスト: `file::test`」（無ければ「既存テストは不変」）を書き、凍結後は P1-01.7 がこの列挙と `tests/` の変更を照合する。

**整合分類（ADR-0080 のレンズ）**:

| 分類 | 意味 | 扱い |
|---|---|---|
| repair | 既存機構の修理・後始末・不整合の解消。機構層を「止める」方向 | 本文に載せる |
| instrument | read-only の**読み値を出す計器**。読み値は機械が出し、判定は人間が行う（判定の**材料**を増やすが判定者は増やさない）。ADR-0071 / ADR-0101 の消費計画 (a)(b)(c) を最終行に持つ。記録・台帳・schema・文書は読み値ではないので neutral | 本文に載せる |
| neutral | 文書・運用・研究成果物など、機構層の動きに影響しないもの | 本文に載せる |
| capability-growth | エージェントの能力や機構を増やす提案 | 第 5 章へ（却下・延期の記録） |
| value-steering-risk | 価値層を特定の方向へ誘導するおそれ（observation-over-steering、ADR-0050/0051/0052 に抵触） | 第 5 章へ、または第 4 章の決定事項として明示 |

**「判定者」の線引き**: 本文書で「判定者（judge）」とは、本番の行動を変える verdict を出す LLM を指す。新しい判定者は増やさない（ADR-0056 / ADR-0097 の ablation・退役証拠が立ったまま。復活は ADR-0056 を明示的に supersede する ADR が前提）。shadow 読みや研究用のラベル付けは instrument として扱うが、次の 3 条件を満たすものに限る: (i) 本番経路の外で走る（offline replay か、ADR-0113 型の shadow で「gate 率の差分 0」を完了条件にする）、(ii) ADR-0101 の消費計画 (a)(b)(c) を持つ、(iii) 判定者に昇格させるときは ADR-0056 を supersede する ADR を先に書く。cloud モデル（opus / Jev）を研究ラベル付けに使う項目は「前提変更（ゼロ API の例外）」として規模・整合の行に明示し、egress の扱いは D-P1-11-4 に従う。

**「熟慮」と「既定可」**: 第 4 章の決定は 2 種類に分けてある。**熟慮**は一方向の扉か、価値層・ゲート・北極星の読み値・研究の方向に触れるもので、オーナー自身の判断と `reason` が要る。**既定可**は可逆または機械的で、推奨をそのまま採ってよいが `decision` は人間が打つ。種別は §4.0 の表が正本（本文の推奨文に括弧で書いてあるものもある）。

**土曜ゲートの配分規約**: 1 ゲート = 決定 ≤ 5 件、うち熟慮 ≤ 3 件、当週に着手する作業束 ≤ 2（第 4 章 4.0 の表が検査になる）。「束」は決定の出所ではなく、その週に手を入れる作業束で、読みだけの決定は束に数えない。37 束（P1-01 と P1-14 は他の束の PR に同乗）は 4.0 の表のどこかで着手週を少なくとも 1 回名指されている。束の着手週より前に入る項目（「今すぐ」「v2.13.0 前」「11-01 まで」）は 4.0 の「先行項目」列に週ごとに名指してあり、列に無い項目は当週に入れない。10-10 の決定は本文書の作成日当日のため遡及記録（10-17 に打つ。上限に数えない）。11-28 の熟慮 5 件は ADR-0080 の追補（2026-11）の 1 PR に結ぶ例外。決定 ≤ 5 は土曜 12:00〜14:07 の窓の代理で、Ollama を使う読みは平日の guard 窓で前日までに取る（P2-01.11）。10 月は日付拘束のある決定だけを置き、v2.13.0 は 11 月前半に回した。この規約を守ると決定は 2027-03-06 まで並び、03-13 / 03-20 / 03-27 の 3 回は欠席や遅れの繰り越し先として空けてある（繰り越しと縮退の順は P2-01.14）。

**平日の作業と委ね先**: 作業量は 4.0 の月別表で見積もってある（S = 1、M = 3 セッション）。直近 8 週の commit は中央値で週 ≈ 51 だが、直近 2 週は 24 / 15 で、10〜11 月の見積りはその 2〜3 倍にあたる。task-triage loop（ADR-0098）に回してよいのは、S / repair で凍結集合に触れず、Mac 実機・外部サービス・`launchctl` を要しない項目だけで、loop の入口は `rfcs/` の draft なので、回す項目だけ `origin: roadmap` の draft を起票する（P2-01.4 / .5 の RFC 数からは除外。D-P2-01-5）。それ以外はオーナーの対話セッションで行う。「本番機へ」は `PROJECT_ROOT` の main checkout に merge することを指す（launchd は次の起動から読むので再 load は要らない）。土曜ゲートは code を適用しない（`weekly-gate/SKILL.md` の Out of scope）。PR はゲートの前の平日に branch で用意し、merge はゲートの後の別セッションで行う。

**週の言い方**: 「X の週」は土曜 X の前の月〜金で、X のゲートで使うものはその金曜までに main へ入れる。「着手 X」は X のゲートで方針を確かめ、X の後の平日に PR を入れる（X のゲートの決定を要する部分は X の後の週に回す）。

**依存と停止リスト**: 各束の「依存」は先に終わっている必要がある束・項目だけを指し、自分を参照する側（消費者）は「→ 参照元」の行に分けてある。「停止リスト」（P1-01.3）は期日つきの残作業の表で、空になった週が凍結判定の唯一の開始点。トリガーつきの延期は第 5 章の延期行（延期台帳）に置き、停止リストには入れない。

**フェーズの意味**: Phase 0 は「今すぐの修理」（10 月中。日付が決まっているものを含む）、Phase 1 は「機構層を止めるための後始末」（2027-03 まで。束の着手は 10 月〜2027-01 に分けて並べ、凍結の判定（verdict）は停止リストが空になった週 + 窓が満ちた週（推奨どおり — D-P1-01-1 の追加段 B・D-P2-07-1 A — なら停止リストの最終行は P2-07.1 / P2-06.2 で、早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8 の遅い方 + 8 週で、早くて 2027-04-03））、Phase 2 は「自己調節とゲート負荷ゼロ」（決定は 2026-10〜12 月と 2027-02〜03 の土曜。先行項目は 10〜11 月、実装は 2026-11〜2027-03）、Phase 3 は「研究の結晶化」（2027 年 Q2 まで）、Phase 4 は「終わり方」（12 月に予約、runbook は 2027 年 Q1、最終版の形は Q2）。横断テーマ（価値層の legibility・security absence の維持・ガバナンス文書）は独立のフェーズにせず、それぞれ P3-04 / P1-10 / P1-12・P1-13 の束に畳んである。期限は「この順で進めるとき無理のない時期」であり、締切ではない。実行は 1 人（オーナー）＋ Claude Code を前提に、土曜ゲート 1 回に決定 ≤ 5 件（熟慮 ≤ 3）・束 ≤ 2 の想定で並べた。

**前提**: 実行環境は M1 Mac 16 GB・Ollama（gemma4:e4b + nomic-embed-text）・API コストゼロのまま。資金・商用化・人員拡大を前提とする項目は載せていない（オーナーの立場上受け取れず、趣味として続ける方針のため）。大型モデルや cloud を前提にする提案は「前提の変更」として第 4 章または第 5 章に明示した。

**この文書の限界**: レビューは 2026-10-09〜10 のリポジトリの状態（shallow clone、直近 447 commit。tag と古い履歴は読めない）に基づく。`~/.config/moltbook/` のランタイム実体（episode ログ・gate 記録の生データ・launchd の実状態）はオーナーの Mac にしか無く、読めていない。それらに依存する判断（例: 06:00 JST セッションの蒸留取りこぼしの実件数）は「オーナーの Mac で確認する」を完了条件の最初の 1 行にしてある。

## 1. 現状スナップショット（2026-10-10）

| 項目 | 値（確認方法） |
|---|---|
| 本体の版 | v2.12.0（2026-09-12 release、Zenodo DOI 10.5281/zenodo.22724623）。HEAD `2cad850`（2026-10-09）。release 後 **177 commit** が未リリース（`git log --since=2026-09-13`）。`CHANGELOG.md` に Unreleased 節なし |
| コード | `src/` 96 ファイル・約 37,600 行。`tests/` 126 ファイル。pytest 4,762 passed / 178 skipped / 2 failed（コンテナに rsync が無いための失敗）、カバレッジ 95.05%。ruff / pyright / import-linter / 依存床テストは通過（TESTS-CI 観点の実行結果） |
| Python 床 | `pyproject.toml` は `>=3.10` だが `typing.assert_never` 等で実際の床は **3.11** |
| 決定記録 | ADR 113 本（最新 0113、2026-10 に 0111〜0113）。RFC 49 本、うち blocked 7 本: 0012 / 0023 / 0040 / 0042 / 0046 / 0047 / 0048。本文 `## Status` が frontmatter と食い違うものが約 20 本 |
| 稼働 | Moltbook 上の 1 インスタンス、2026-03-07〜。JST 0 / 6 / 12 / 18 時に 6 時間セッション。日次 distill、週次 insight（2026-09-19 に再開、再開後の staging は空）、月次 identity staging、憲法改正は due 読み値ベース（最終採択 2026-08-09、次回 due は 2026-10-31（ADR-0091 の 83 日）、P0-07） |
| モデル | gemma4:e4b（2026-06-28〜、ADR-0069）+ nomic-embed-text、Ollama、M1 Mac 16 GB。生成 15 tok/s |
| 週次運用 | `scripts/weekly-pipeline.sh`（土曜、headless `claude -p` の `/weekly-report` + 決定論 intake）→ 土曜の人間ゲート `/weekly-gate` → task triage。起票台帳はオーナー私的の `~/.claude/scripts/claims.py` |
| 進行中 | RFC-0046（relevance gate を Score4 logprobs に置換）: 09-28 accepted・enforce-first、10-03 に事前登録の gate 率予測が不成立、10-07 に旧 score が upvote-only / note を動かし続けていた件を修理、後始末 3（旧 gate 削除）は **2026-10-15 の読み後**。README Quick Start が env 無しで静かに何もしない問題を 10-09 に修理中（`4b85f22` / `2cad850`）。v2.13.0 準備中 |
| 公開データ repo | 212 MB。`knowledge.json` 7.5 MB・**10,985** patterns（embedding なし）。**`knowledge.json.bak-dup-cleanup-20260718` 72 MB が 768 次元 embedding 入りで公開されたまま**。skills 53・rules 2・snapshots 100（上限）・reports 320 ファイル・pipeline 40 ファイル。DOI は v1.0.0（2026-06-17）のみ。HF mirror あり |
| 兄弟 repo | `-cloud` 2026-08-17、`-mlx` 2026-08-16、`-otel` 2026-08-17、`-rules` 2026-07-07 で停止。いずれも `DecisionBackend`（ADR-0112 / 0113、2026-10）以前の形 |
| 関連 repo | agent-knowledge-cycle（2026-10-09）、agent-attribution-practice（2026-09-27、SSRN DOI）。いずれも本体の事例としての記述は未反映 |
| 北極星 | ADR-0080 + 2026-08-26 追補（A: 自己調節と負荷→0、B: 代謝の質は複数軸）。CLAUDE.md § 北極星に操作面の要約（同 PR 同期規約） |

**要点**: 機構層は「止まって」いない（src への commit は 8 月 40 → 9 月 95 → 10 月 6、2 か月で ADR 17 本）。無人週次チェーンは headless Claude Code と土曜の人間の読みに依存し、「関与なしに自己調節」の条件は定義すら未着手。価値層は legible だが記録に穴がある（承認者・理由・却下本文・snapshot の上限超え）。研究層は問いの操作的定義・対照条件・論文のいずれも無い。セキュリティ層は absence が保たれているが、公開データの開示境界が 1 か所破れている。終わり方は RFC-0006 withdraw 後、予約のまま。

## 2. 「完成」の判定表

| 層 | ADR-0080 の完了条件 | 現状判定（2026-10-10） | 判定の材料になる読み値（置く束） | 読む時・読む人 | 満たすための束 |
|---|---|---|---|---|---|
| 1a 機構層: 止まる | 変更が修理のみになり、機構層 ADR が 0 に近づく | **未達**。src commit 8 月 40 / 9 月 95 / 10 月（1〜9 日）6、機構 ADR 0097〜0113 が 2 か月で 17 本。「止まった」の計測単位が未定義 | 凍結集合の commit 種別と四半期の新設機構 ADR 数（P1-01.1 の 4 系列）、凍結条件表と停止リスト（P1-01）。定義は 11-28 に存在すれば満たし、verdict は停止リストが空になった週 + 窓が満ちた週（推奨どおり — D-P1-01-1 の追加段 B・D-P2-07-1 A — なら停止リストの最終行は P2-07.1 / P2-06.2 で、早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8 の遅い方 + 8 週で、早くて 2027-04-03） | 週次: Step 0 の briefing 1 行（P1-01.1）。四半期: T4 行で通読（P0-01.8） | P0-02, P0-04, P0-05, P0-06, P1-01〜P1-08, P1-11, P1-15 |
| 1b 機構層: 自己調節 | Moltbook とのループがオーナーと Claude Code の日常的関与なく回り、人間ゲートの**負荷**→0（ゲートは権限として残る） | **未達**。週次チェーンは headless `claude -p` と土曜の人間の読みを前提。介入ゼロの週 0/6。負荷・自己調節の定義と読み値が無い | 負荷 3 系列（裁定件数・読み量・ゲート外作業）と `origin: gate` 起票数・修理 PR 数を並べた 8 週表（P2-01.3、D-P2-01-1 の B）、自己調節の週次読みと verdict（P2-01.5。定常の下限は D-P2-01-3 の 8 週）、推奨↔裁定一致率（P2-01.1）、dead-man 表示（P2-01）。Claude Code 依存の決着（P2-02） | 週次: P2-01.1 / .2 の 2 列は 10-17 から Step 1 で。自己調節の 8 週表（P2-01.5）は 11-28 から（09-19 以降を遡って出す）。D-P2-01-3 の下限に照らした verdict は定義（11-28）の後、T4 行で | P0-01, P0-07, P1-04, P1-05, P2-01〜P2-07 |
| 1c 代謝の質（08-26 追補 §B） | 摂取装置が新規性・重要度・環境の反応など複数軸で見分ける。単一スカラー禁止 | **部分**。surprise / novelty / comment-outcome の各読みは存在するが join されておらず、insight 再開後の候補は 0 | 多軸 join の 1 画面（P2-06）、飽和の定義（P2-07）。08-26 追補 §B の歯止め 3 つを読み値に付す: 軸の列挙は開いたまま（0080:204-206）、環境の反応は reading であって reward weighting ではない（:213-217、変えるなら ADR-0051 の supersede）、importance を軸として名指しても計器の再建ではない（:219-228、ADR-0056 の ablation は立ったまま） | 2027-Q1 まで**材料なし**（join 画面と飽和定義は Q1）。それまでは P0-01.5 / .6 の insight 週次の読みを Step 0 で | P0-01, P2-06, P2-07 |
| 2 価値層: legible な進化 | すべての価値層変更が記録から追跡でき、オフラインで説明できる | **部分**。採用は `audit.jsonl` に残るが承認者・理由・却下本文が無い。snapshot 100 件上限で pivot が消える。skill→pattern→episode の連鎖が公開側で切れる。オーナー意図の介入チャネル 12 本が未登録 | 承認記録の完備（P1-12）、版履歴 history と憲法 CHANGELOG、identity drift の read-only 計器（P3-04）、介入チャネル登録表（P3-07） | 週次: 承認記録の行（P1-12、2027-01 から Step 7）。版履歴・drift 計器（P3-04）は 2027-Q1 まで**材料なし** | P1-12, P3-04, P3-05, P3-07, P0-07 |
| 3 研究層: 結晶と拡散 | 建立時の 3 問いが肯定/否定で答えられ、論文として結晶し、機械参照圏に拡散され、派生される | **未達**。3 問いに操作的定義・signal・反証条件が無い。対照条件無し（RFC-0002 withdrawn）。論文ドラフト無し。公開データだけで図表を再生成できない | 研究問い ADR と証拠表（P3-01）、装置境界表（P3-02）、再現ガイドの実行成功（P3-05） | 四半期: 証拠表（P3-01.3）が出てから T4 行で。2027-Q1 まで**材料なし** | P3-01〜P3-06, P0-03 |
| 4 セキュリティ層: absence | 1 外部アダプタ、権限の不増加。変わらないことが成功 | **ほぼ維持、2 か所破れ**。72 MB の embedding 入り `.bak` が公開 repo に同期済み。公開 patterns に第三者投稿の逐語断片（12 語以上の連続一致 311 行、R1 再現者視点の測定）があり、NOTICE / HF card の「引用ゼロ」と食い違う。週次セッションの Read 許可が `.env` / `.notes` を除外していない。I/O 面の allowlist が機械検査されていない | I/O 面 allowlist テストと依存床テストの継続通過、公開 repo の除外 allowlist の検査（P1-10, P0-03） | 週次: CI の結果（P1-10、12 月から）と公開 repo の除外検査（P0-03、10 月から）。人が読むのは赤のときだけ | P0-03, P1-10 |
| 5 終わり方 | heartbeat の終了条件を持つ（ADR-0080:72-78 の 2 条件: read-only 計器が代謝の定常を示す **かつ** 残る問いが別の実験を要する）。最終成果物は縦断記録（データセット + 論文） | **未着手**。RFC-0006 withdrawn（2026-09-28）。runbook 無し。bus factor 1 | 検討イベントの予約と判断役の明記（P4-01。イベントは上の 2 条件のどちらに対応するかを 1 行で持つ: 代謝の定常 = P2-01.5 の自己調節の読み（下限は D-P2-01-3 の 8 週）、別の実験 = P3-03 の採否）、runbook の dry-run 成功（P4-02） | 四半期: T4 行の検討イベント行（P4-01、12 月の予約後）。代謝の定常の材料は 8 週表（P2-01.5、11-28 から遡及 8 週）。verdict は D-P2-01-3 の後、T4 行で | P4-01〜P4-03 |

判定の原則: 「達」の判定はオーナーが行う（ADR-0080 08-26 追補 §A「十分性は人間の判断」）。この表の読み値は判定の**材料**であり、達成の代替ではない（ベンチマーク非還元条項）。定義そのものは機械判定にしない（ADR-0080:125-129「deliberately not machine-checkable」）。閾値や窓は ADR-0080 の定義でなく dated note の「読み方」に置く（P1-01、追補（2026-11））。読む時は 2 つ: 週次は Step 0 の briefing 1 行（P1-01.1）で層 1a だけを、四半期は P0-01.8 の T4 行の中でこの表の 7 行を通読し、`gate_record` に層別の verdict を 1 行ずつ書く。「材料なし」の行は読み値が出るまで verdict を書かない（空欄も記録）。

## 3. ロードマップ本体


### Phase 0 — 今すぐの修理（〜2026-10 末）

日付が決まっている読み（10-10 の土曜ゲート、10-15 の submolt-scan、10-31 の憲法改正 due（ADR-0091 の 83 日））に結びつく修理と、公開面の破れ・静かな取りこぼしのように放置日数がそのまま損失になる修理を集めた。いずれも ADR-0080 のレンズでは repair であり、能力は増えない。

**このフェーズの完了条件**
- P0-01 の決定が土曜ゲートの記録（RFC-0042 / 0048 / 0023 / ADR-0111 の state 更新）として残っている
- 公開 data repo に embedding 入りファイルと絶対パスが無く、除外が allowlist で検査されている（P0-03）
- 06:00 JST セッションの episode が蒸留されるテストが通る（P0-04）
- README の Quick Start が env 無し / Ollama 不在で非 0 終了し、その経路が CI の smoke で固定されている（P0-05）
- v2.13.0 が tag・CHANGELOG・DOI つきで出ており、wheel 単体で `--help` が通る（P0-06）
- 10-31 due の憲法改正ゲートの結果変数が予測つきで事前登録されている（P0-07）


#### P0-01 10-10 土曜ゲートの決定束（insight / RFC-0042・0023・0048 / ADR-0111 / T4）
- 狙い: insight 再開後 3 回目の読み（2026-10-10 08:00 JST の run）を起点に、価値層ループの入口（insight）と出口（RFC-0048）の方針を 1 セッションで決める。ADR-0080 の 08-26 追補 §A の未完成条件「ループが日常的関与なく自己調節して回る」は、入口 0 件・出口 0 件の静止状態を「定常」と呼ぶか「未完成」と呼ぶかを決めないと判定できない。
- 期限・順序: 2026-10-10（土曜ゲート）。10-10 の run 結果は data repo の最終 sync（2026-10-09T20:30Z、run 前）に無いので、ローカルの `logs/insight-stages.jsonl` と `insight-launchd.log` を読む。順序は RFC-0042 終端 → RFC-0023 終端 → RFC-0048 再開 → ADR-0111 追補。T4 第 2 回（.8）は 10-17 の土曜ゲートに置く（対象集合は census の登録表から `rfcs/0046:260` の削除リストを差し引いて決め、削除 PR の merge を待たない）。遡及は次の土曜（10-17）まで可 — 10-10 の 3 件（D-P0-01-1 / -3 / D-P0-03-2）は 10-17 に `gate_item … --field category=roadmap --field decided_at=2026-10-10` で遡及記録し、10-17 の上限 5 には数えない。ゲート配分（1 ゲート = 決定 ≤ 5・束 ≤ 2）: 10-10 は D-P0-01-1 / -3（+ D-P0-03-2）、D-P0-01-2 は 10-17。出口層 1 の採否は D-P2-07-1（12-05）。SKILL.md の変更（.8 の Step 0 四半期行）は 10-17 前の同梱 PR（P1-04.16 / P2-01.2 / P2-01.10 / P2-01.11 と同じ 1 PR。Step 0 の四半期行は .8 が所有）。.7 の内訳行の src 変更は 10-16 までに本番機へ（10-17 08:00 の insight run より前）。
- 束の完了条件:
  - `rfcs/0042` / `0023` / `0048` の frontmatter `state:` が `blocked` でない（done / withdrawn / accepted）
  - ADR-0111 に 2026-10-10 付の追補（入口方針・反証条件の日付化・revise 消費計画）がある
  - `docs/evidence/adr-0111/` に revise 表（13 行以上）が存在する
  - ADR-0101 に「T4 run 2 (2026-10-17)」の日付つき注記、`.claude/skills/weekly-gate/SKILL.md` に四半期 step がある

##### P0-01.1 10-10 の読みを 1 セッションで処理する手順と材料
- 何を: weekly-gate の digest 冒頭に「① insight count 行（候補数 / revise 累計 / duplicate judge 回答 n / 30 / W40 以降の週次 pattern 数と cluster ≥ 3 の数）→ ② RFC-0042 終端 → ③ RFC-0023 終端 → ④ RFC-0048 再開 → ⑤ ADR-0111 追補」を置く（⑥ T4 起動は 10-17 のゲートに移す）。count 行は人間が組む（script は作らない）: 候補数と covered は `insight-launchd.log` の Summary 行（`cli/memory_cmds.py:239`）、cluster 数は同じログの `Processing … cluster batches` の行（`core/insight.py:852`）、duplicate judge / revise の verdict 分布は materials の census 行（`_census_registry.py:160-165`）、W40 以降の週次 pattern 数は State Diff から写す。10-17（P0-02、RFC-0046 の照合は同日の Step 1c の D-P0-02-1 行の照合コマンド）と 10-31（P0-07）の決定は各 RFC の照合節に日付で固定する（`decide_by` 欄は P1-02 で導入、現状 0 本）。
- 根拠: `rfcs/0042:186-188`（再開条件と成立時の分岐）/ `rfcs/0048:92-94`、`rfcs/0023:237-239`（照合先 = RFC-0042 の読み）/ data repo knowledge.json の週次追加 W39 727 → W40 488 → W41 503（score4 enforce で入力が約 2 割減、ADR-0074 項目 9 の `min_size=3` 床の前提が動いた）
- 完了条件: 3 本の RFC と ADR-0111 に「2026-10-10」の照合節 / 注記が揃う。count 行に cluster 数と pattern 数が並記され、各値の出所が上の 4 箇所（Summary 行 / `Processing … cluster batches` 行 / census 行 / State Diff）と一致する（新しい script は増えない）。
- 規模・整合: S / repair   出典: AB-48 CP-26

##### P0-01.2 RFC-0042 を終端し、入口の方針と読み値を ADR-0111 追補に残す
- 何を: 10-10 の候補数が週 30 件台に戻っていなければ RFC-0042 を `done`（絞りは本番で再現）にする。同じ追補で D-P0-01-1 の結論（週次継続 / 入口停止 / 月次）と根拠の読み値（候補 0 の週数、revise 累計、採用 0 の週数、W40 以降の入力減）を書く。入口停止（D-P0-01-1 B）を選ぶ場合は「価値層は到達点なし」との整合（skills 以外の層が進化を担う）を 1 段落、`docs/CYCLES.md` #4 の「Curate (insight)」を書き換える。
- 根拠: `rfcs/0042:192,204`（09-26: 13 行 = revise 10 / reconfirm 3、10-03: 候補 0、63 covered、revise 3、16 行）/ `docs/adr/0111:157-160`（RFC-0042 の volume reading）/ data repo `pipeline/never-selected/never-selected-2026-10-02.json` strict 0 件、`confusion-pairs-2026-10-02.json` pairs 0 件、skills 53 本（出口側も候補 0）
- 完了条件: `rfcs/0042` の `state:` が `done`、ADR-0111 に 2026-10-10 追補、`docs/CYCLES.md:87` が選んだ方針と一致。
- 規模・整合: S / neutral   出典: CP-19 VL-20 AB-10

##### P0-01.3 RFC-0023 の希少レーンを withdraw し、ADR-0104 の "remains open" を閉じる
- 何を: 入口が 0 件の今、希少レーン（singleton 保留台帳 + 週次再クラスタ）は店への供給を増やす機構で、RFC-0048 の「件数を絞る」方向と逆。RFC-0023 を「S9（候補検索 top-k）分で done、希少レーンは withdraw」で終端し、ADR-0104 に日付つき注記を足す。候補が 30 件台に戻っていた場合のみ review-when どおり再設計を読み直す。
- 根拠: `rfcs/0023:2,235-239`（blocked、成立時に著者が accepted / withdrawn を判断）/ `docs/adr/0104:238-239`「RFC-0023's rare lane … is NOT part of this change and remains open」/ `rfcs/0048:98-109`（store の件数を絞る方向、オーナー指示 2026-09-26）
- 完了条件: `rfcs/0023` の `state:` が終端（done か withdrawn）、ADR-0104 の "remains open" の隣に 2026-10 の注記。
- 規模・整合: S / neutral（能力拡大の抑止）   出典: AB-08

##### P0-01.4 RFC-0048 を再開し、出口層 1 の自動化と注入 ablation に分ける
- 何を: 入口が絞れた（候補 0）ので RFC-0048 の再開条件は成立。`accepted` に動かし、(a) 出口層 1（never-selected strict の決定論 archive、可逆、反証条件 = 4 週以内の復元 2 件）と (b)「skill の注入はコメントを変えるか」の ablation（現行 / skill なし / 強い判定者 1 件の 3 通り、opus 対比較、一発測定）を別 RFC に分ける。(a) の設計は P2-07、(b) は研究層（P3-03）へ。
- 根拠: `rfcs/0048:2-3,92-94`（再開条件 = RFC-0042 の 3 回の読みで 30 件台に戻っていない）/ `rfcs/0048:24-34`（3 層と反証条件）/ `rfcs/0048:70-74`（注入の open question、答え次第で出口設計の前提が変わる）
- 完了条件: RFC-0048 の `state:` が `accepted`、分割後の 2 本がそれぞれ単独の再開条件と照合先を持つ。
- 規模・整合: S / repair（(b) は計器、前提変更: ゼロ API の例外 — 研究ラベル付けのみ、≈$0.01 / 回、egress 分類は D-P1-11-4。本番既定化ではない）   出典: AB-13

##### P0-01.5 ADR-0111 の反証条件を日付つきにし、命名段の反証条件を事前登録する
- 何を: duplicate judge の反証条件「累計 30 件」は、命名段が全 cluster を `revise` / `reconfirm` で止める限り到達しない（2 run で回答 0 / 30）。追補で (1)「2026-12 末までに 30 件未達なら段を残すか撤去するかを読む」の日付条件、(2) 命名段の反証条件（例: 4 run 連続 `new` = 0 かつ `revise` ≥ 10 → revise ログを読んで案 B か命名段の撤去を決める）を事前登録し、insight の Summary 行（`cli/memory_cmds.py:236-240`）に「duplicate judge 回答 n / 30」を常設する。
- 根拠: `docs/adr/0111:146-156`（反証条件 ≥ 30 件）/ `src/contemplative_agent/core/insight_stages.py:7-15`（`revise` は本文を書かず停止、duplicate judge は `new` の後）/ `rfcs/0042:192,204`（16 行すべて命名段、`new` 0）
- 完了条件: ADR-0111 Review-when に日付条件と命名段の反証条件がある。Summary 行に `n / 30` が出る。
- 規模・整合: S / neutral（ADR の反証条件と Summary 行の 1 値 = 記録）   出典: AB-10 CP-20

##### P0-01.6 revise 提案に消費計画を置き、1 回だけ表に出す
- 何を: 蓄積した `revise` 行（13 件以上: target_skill / change_reason）を名前・提案名・日付だけの表として 1 回 `docs/evidence/adr-0111/` に出し、ADR-0111 の Consumption plan に「読み手 = 土曜ゲート、回数 = 3 run 分を 1 回、決めること = 案 B の可否、決定後は行を消す」の 3 文を足す。新しい週次計器は作らない（D7 維持）。
- 根拠: `src/contemplative_agent/core/insight.py:1008-1012`「whether to turn them into a replacement path is a later reading, not this stage's」/ `docs/adr/0111:164-166,171-179`（Review-when 4 項目目と Consumption plan に revise の読み手が無い）/ data repo `reports/analysis/weekly-2026-10-02-findings.md` F3.2「`revise` verdicts accumulate … with no consumer」
- 完了条件: `docs/evidence/adr-0111/` に 13 行以上の revise 表が存在する。ADR-0111 Consumption plan に revise の 3 文がある。
- 規模・整合: S / neutral（1 回の表と ADR の消費計画文 = 記録）   出典: CP-21 VL-22 AB-10

##### P0-01.7 novelty gate の「既知」判定の内訳を記録し、却下台帳の扱いを決める
- 何を: `_load_known_themes` は adopted skill と staged 台帳（却下分を含む）を区別せず既知にする。10-17 の insight run で「covered の根拠が store か台帳（adopted / rejected）か」を件数で分けて Summary 行と監査行に出し、その読みで D-P0-01-2（現状維持 / adopted のみ / TTL）を決める。ADR-0050「No rejection write-back」と ADR-0074 項目 7「reached review なら considered」の関係を両 ADR に cross-reference で明文化する。
- 根拠: `src/contemplative_agent/core/insight_novelty.py:374-392`（docstring「whether or not it was adopted」、`chain(_skill_file_themes, _staged_ledger_themes)`）/ `core/insight.py:814`（抽出前に `_load_known_themes(skills_dir, staged_ledger_path)`）、`cli/memory_cmds.py:169-194`（台帳は decision-agnostic で追記のみ）/ `docs/adr/0050:38-42,112` / `rfcs/0042:204`「63 already covered」（store は 53 本）
- 完了条件: Summary 行または `insight-stages.jsonl` に `covered_by: store|ledger_adopted|ledger_rejected` の内訳が 1 回出る。内訳行の src 変更は 10-16 までに本番機に入っている（10-17 08:00 の insight run が出す）。ADR-0074 に判断（維持 / 絞り / TTL）の追補 1 段落、ADR-0050 と相互参照。
- 規模・整合: S / instrument（決定側 D-P0-01-2 は value-steering-risk 扱い）   出典: CP-16 VL-21
- 消費計画: (a) 10-17 の土曜ゲートの人間が 10-17 08:00 JST の insight run の Summary 行（候補数・covered、`cli/memory_cmds.py:239`）と `Processing … cluster batches` の行（cluster 数、`core/insight.py:852`）を読む (b) 1 回の読みで D-P0-01-2（A / B / C）を決める (c) 決定後に内訳行は撤去し、ADR-0074 追補の 1 段落だけ残す（1 回で撤去）

##### P0-01.8 T4 第 2 回（四半期棚卸し）を起動し、weekly-gate に四半期 step を足す
- 何を: ADR-0101 D4 の「四半期境界後の最初の土曜ゲート」（2026-10-03）に T4 の記録が無い。10-17 の土曜ゲート（10-10 は不可）で T4 run 2 を起動する。T4 の対象集合は census の登録表から `rfcs/0046:260` の削除リストを差し引いて決める（削除 PR の merge を待たない — merge はゲートの後の別セッション）。weekly-gate SKILL Step 0 に「四半期境界後の最初の開催した土曜ゲートなら T4 を実施（決定論の日付判定 1 行。休みの土曜は数えない — 2027-01-02 は休みなので第 3 回は 2027-01-09）」を足す。同じ回で読み手の種別（人間 / Claude Code 対話 / headless / code）の棚卸し（P1-04.16）を行う。T4 行の中で第 2 章の判定表 7 行を `docs/plans/roadmap-2026-10/ROADMAP.md`（P2-01.10 が 10-17 の SKILL PR で commit するロードマップ全文）から通読し、`gate_record` に層別 verdict（`freeze_verdict=` / `self_regulation_verdict=` と同形）を書く — 2027-Q1 まで読み値が無い行は「材料なし」と記録する（1b / 5 は対象外: 8 週表（P2-01.5）は 11-28 から遡及 8 週で出るので「11-28 から」と記録し、D-P2-01-3 の下限に照らした verdict は定義の後の T4 行で出す）。各計器の判定本体は P1-04 で行う。
- 根拠: `docs/adr/0101:121-128`（No standing register、Recurrence: at the first Saturday gate after each quarter boundary）/ `.claude/skills/weekly-gate/SKILL.md` に T4 / 四半期 / 棚卸 の語が無い（grep 0 件）/ `git log --grep=T4` は `4e33f22`（ADR-0101 起票）と `c8db8b9`（2026-08-29、ADR-0049 注記）のみ / `rfcs/0046:260`（削除リスト = T4 の対象から差し引く集合）
- 完了条件: ADR-0101 に「T4 run 2 (2026-10-17)」の注記、SKILL.md Step 0 に四半期判定の行（「開催した土曜ゲート」で判定。T4 行に「§2 を `docs/plans/roadmap-2026-10/ROADMAP.md` から通読」の 1 句を含む）。SKILL.md の変更は 10-17 前の同梱 PR。各 owning ADR への判定注記は P1-04 の完了条件。
- 規模・整合: S / repair   出典: OI-02 WO-37   順序: SKILL.md は 10-17 前の同梱 PR（P1-04.16 / P2-01.2 / P2-01.10 / P2-01.11 と同 PR、Step 0 の四半期行を所有。§2 の読み元 = P2-01.10 の `ROADMAP.md` の commit も同 PR）

##### P0-01.9 RFC-0049 の「次」（`parent_rejected` の読み）に担当と期日を置く
- 何を: RFC-0049 は done だが末尾の「次: 列が溜まったら `parent_rejected` を返信先ごとに数え (a) 同一本文の別 comment か (b) 終端印がセッションをまたいで残らないかを決める」に読み手と期日が無い。10-17 の weekly-gate で読む 1 行（RFC-0049 の review-when か RFC-0038 への注記）を置く。読みは 1 行: `logs/skill-selection-*.jsonl` の publish 行で `failure_reason == "parent_rejected"` を `reply_key_sha256` ごとに数える（RFC-0049 / `a7fa263` の列。自己書き込みのログなので読んでよい）。このコマンドを decisions.md（P2-01.10）の 10-17 の材料欄に置く。
- 根拠: `rfcs/0049:2,50`（`state: done 2026-10-03`、「次: …」）/ `core/skill_selection.py:438`（`PUBLISH_FAILURE_PARENT_REJECTED`）、`:577-598`（publish 行の `reply_key_sha256`）/ RFC-0038 の修理（09-19 done）の当否が未確定のまま 2 本とも done
- 完了条件: decisions.md の 10-17 の材料欄に上のコマンドがある。(a)/(b) の判定が evidence か RFC に記録され、必要なら修理 RFC が起票される。
- 規模・整合: S / neutral（RFC の読み手と期日の記録）   出典: AB-14


**依存**
- 2026-10-10 08:00 JST の insight run（ローカル `logs/insight-stages.jsonl` / `insight-launchd.log`。data repo は run 前の sync）
- P0-02（RFC-0046 後始末 3）: 入力減（W40 以降）の要因確定は 10-17 の Step 1c の D-P0-02-1 行の照合コマンド以降
- 順序: P1-04（T4 の判定本体、P1-04.16 = 10-17 の読み手 4 値の棚卸し）と P2-01.10 / .11（`docs/plans/roadmap-2026-10/ROADMAP.md` の commit = .8 の §2 通読の読み元、時刻表）は .8 と同じ 10-17 の回・同じ SKILL PR（同 PR）
- ADR-0050 / 0074 / 0101 / 0104 / 0111、RFC-0042 / 0023 / 0048 / 0049
- → 参照元: P1-02（`decide_by` 欄・RFC 台帳 — .1 の日付固定を引く）、P3-03（注入 ablation = .4 (b) の移送先）、P2-07（RFC-0048 出口層 1 の設計 = .4 (a) の移送先。P2-07.5 = 層 1 と ADR-0080「Not gate dissolution」境界の整合で ADR-0080 追補（2026-11、P1-03.8）の草案の段落。採否は D-P2-07-1（12-05））


#### P0-02 10-15 読み → 旧 relevance gate の削除（RFC-0046 後始末 3）
- 狙い: score4 enforce 後も旧 relevance gate（自由生成 0-1 スコア）一式が本番呼び手ゼロのまま残り、判定経路が 2 本に見える。10-15（木）03:00 JST の submolt-scan が残すログを 10-17 の土曜ゲートの Step 1c の D-P0-02-1 行の照合コマンドで照合し「旧機構は本番に効いていない」を確認してから 1 PR で削除し、Quick Start 事故（env 無しで feed が静かに何もしない）の再発面と、plist / docs の旧世界の記述を同時に消す。判定経路を 1 本にするのは ADR-0080「止まる」側の修理で、v2.13.0（P0-06）の前提。
- 期限・順序: 着手 10-17 の土曜ゲート（§4.0）。材料は 2026-10-15（木）03:00 JST の submolt-scan が残すログ（UTC 10-14 の `llm-calls` と `submolt-scope`）。照合コマンド（`rfcs/0046:255` の for ループと `submolt-scope-2026-10-14.jsonl` の `scale: "score4"` の確認）は decisions.md（P2-01.10）の D-P0-02-1 行の材料欄に置き、10-17 の Step 1c の中で実行する（常設の Step は作らない。木曜に人は要らない、ログは残る）。削除 PR（.2 / .5〜.9）は 10-17 の週（10-12〜16）にオーナーの対話セッションで branch として用意してテストを緑にしておき、10-17 は Step 1c で照合の go を記録し、merge はゲートの後の別セッションで行う（ゲートは code を適用しない — `weekly-gate/SKILL.md:404-405`）。go / wait の決定（D-P0-02-1 / -2）も 10-17 の回（T4 第 2 回と同じ回。1 ゲート = 決定 ≤ 5・束 ≤ 2 の規約。10-17 は P0-02 削除 PR + T4 + 決定 5 + 遡及 3 で、決定と削除 PR の数では最も重い週 — 項目数では 10-24 の方が多い）。plist コメント（.3）は照合を待たず 10-16 まで。ADR-0113 の Status（.7）は 10-17 の削除 PR に同梱（同じ PR が Amendment 3 と ADR-0112 の partial supersede で Status を変えるため）。削除 PR → ADR 注記 → `/release-doi` v2.13.0（形は 11-07 の決定、tag は 11-14 のゲートの後の平日 11-16〜20、P0-06）の順（`rfcs/0046:260`）。`cli/runtime.py` の順序: .2（`:173-208` 削除）→ P0-05（preflight）→ P1-07.13（`:295-316`）。
- 束の完了条件:
  - `rfcs/0046` の `state:` が終端（done）
  - `grep -rn "score_relevance\b\|score_relevance_detailed\|relevance_threshold\b\|RELEVANCE_PROMPT" src/ tests/ scripts/` が 0 件、`config/prompts/relevance.md` が無い
  - `scripts/relevance_label_set.py check` が exit 0（evidence の ratchet が削除後も読める）
  - ADR-0113 に Amendment 3、ADR-0112 に partially-superseded の記録、`graph.jsonld` のエッジが `tests/test_adr_status_consistency.py` で green
  - CHANGELOG の v2.13.0 節に `thresholds.relevance` 撤去の移行 1 行

##### P0-02.1 10-15 の scan ログを 10-17 の Step 1c で release 段 (0) として照合し、go / wait を決める
- 何を: RFC-0046 の照合コマンド（10-14 以降の `llm-calls-*.jsonl` で `moltbook.score_relevance` と `moltbook.submolt_scope` が 0、`submolt-scope-2026-10-14.jsonl` に `scale: "score4"`）を、decisions.md（P2-01.10）の D-P0-02-1 行の材料欄に置いたコマンドとして 10-17 の weekly-gate Step 1c で実行し、成立なら go を記録して .2 の削除 PR（10-12〜16 に branch で用意済み）をゲートの後の別セッションで merge、不成立なら D-P0-02-1 を決めて RFC-0046 に 1 行書く（10-15（木）に人は要らない — scan のログが材料）。
- 根拠: `rfcs/0046:2`（`state: blocked 2026-10-09`）、`:246-258`（本番初回読み: 旧 caller 0、feed 68 行 fail-closed 0、待つもの = 2026-10-15 03:00 JST、照合コマンド `:255`、再開条件）/ `.claude/skills/weekly-gate/SKILL.md:17-87`（Step 0 は (a)(b)(c) だけで (d) は無い）/ `src/contemplative_agent/cli/runtime.py:173-174`（`4b85f22`: 未設定の既定 = `{relevance}`、Quick Start 側は修理済み）
- 完了条件: decisions.md の D-P0-02-1 行の材料欄に照合コマンドがある。RFC-0046 に 2026-10-17 の照合節（材料 = 10-15 のログ、成立 / 不成立と判断）がある。既存テストは不変。
- 規模・整合: S / repair   出典: AR-26 RD-31 CU-11

##### P0-02.2 旧 relevance gate 一式を 1 PR で削除する（削除リスト + docs 例 + 移行行）
- 何を: `rfcs/0046:260` の削除リスト（`score_relevance` / `score_relevance_detailed` / `relevance_prompt_template` / `config/prompts/relevance.md` / `thresholds.relevance` と `DomainConfig.relevance_threshold`（既定 0.82）/ `DECISION_FACES` `DECISION_ENFORCE` の配線と `enforce_unconfigured` / ADR-0112 の skill-selection shadow / `scripts/relevance_arm_replay.py` の arms A / A0（`:600-605` `run_production` — 削除し、evidence 固定の replay としては残さない。束の完了条件 2 の grep と整合）/ plist の DECISION_* 3 キー）を 1 PR で消し、`core/report.py` の旧 `relevance` キー読みと `tests/test_llm.py` の 5 クラス・`test_domain.py` / `test_agent.py` の参照（下の既存テスト欄）も落とす。`_warn_unknown_keys` の allowlist から `relevance` を外し legacy key を WARNING 化、docs 例（`CONFIGURATION.md:139` の 0.92、`config/domain.json:13` の 0.80）を `relevance_score4` のみに揃え、CHANGELOG に移行 1 行。PR は 10-17 の週（10-12〜16）にオーナーの対話セッションで branch として用意してテストを緑にし、merge は 10-17 の Step 1c で go を記録した後の別セッション（ゲートは code を適用しない）。
- 根拠: `src/contemplative_agent/adapters/moltbook/llm_functions.py:54,82,159`（本番呼び手 0、`96881f5`）/ `src/contemplative_agent/core/domain.py:44,167,175`（必須欄・allowlist・既定 0.82）/ `rfcs/0046:210`（0.82 / 0.65 は domain.py の既定、本番 domain.json は 0.80 / 0.70 — 三重化の出所）/ `docs/CONFIGURATION.md:155`「a later amendment deletes it」
- 完了条件: 束の完了条件 2 と 5。閾値名ごとに値の出所が 1 箇所（`config/domain.json` の `relevance_score4` のみ）。書き換える既存テスト: `tests/test_llm.py::TestScoreRelevanceParsing` / `::TestScoreRelevanceEmptyInput` / `::TestRelevancePromptContract` / `::TestScoreRelevanceOutageVisibility` / `::TestScoreRelevanceReasonCodes`（削除）、`tests/test_domain.py::TestLoadDomainConfig::test_loads_default_config` / `::test_custom_config` / `::test_typo_threshold_key_warns` と `::TestResolvePrompt` の 4 件（`relevance_threshold` kwarg / `thresholds.relevance` を外す）、`tests/test_agent.py::TestSelectiveMode::test_relevance_threshold_in_range`（削除）、`tests/test_submolt_scope.py::_domain`（helper の `relevance_threshold=0.80`）、`tests/test_relevance_enforce.py::TestOneJudge::test_a_feed_cycle_never_asks_the_free_generated_score`（`score_relevance_detailed` の patch → 不在 assert）、`core/report.py:97` の legacy キー読みを落とす場合は `tests/test_report.py::TestRelevanceScales::test_a_malformed_p_top_degrades_to_the_legacy_field` / `::test_the_parser_carries_the_new_key`（`tests/test_instrument_census.py` の `moltbook.score_relevance` は caller 名の文字列のみで不変）。
- 規模・整合: M / repair   出典: CH-15 CU-11 CU-12 DC-14 AR-26   順序: `cli/runtime.py` は本項目（`:173-208` 削除）→ P0-05 → P1-11.5 → P1-07.13

##### P0-02.3 agent plist の DECISION_* コメントを 10-16 までに amendment 2 の文言に直す
- 何を: 削除 PR を待たず、template と live plist の両方でコメント 2 箇所（「Remove both keys to turn the shadow off; the live gate is unchanged either way」「Remove this key to put the live gate back」）を `CONFIGURATION.md:433` の文（キー削除は無変化、空文字が gate を止め feed と種選びが止まる）に差し替える。キーは残す。
- 根拠: `config/launchd/com.moltbook.agent.plist:26-31,36-40`（旧 shadow + live gate の記述）/ `docs/CONFIGURATION.md:433`（正）/ `cli/runtime.py:168-174`（未設定 = 本番既定、空文字 = off）/ `rfcs/0046:237`（RFC 自身が「plist のコメントも古い」と記録）
- 完了条件: plist コメントが P2-04.3 の所有する `CONFIGURATION.md:433` の段落と一致（本項目は段落を書き換えず参照する）。live plist も同じ変更（`launchctl` の再 load はセッション窓外）。既存テストは不変。
- 規模・整合: S / repair   出典: AR-27 RD-32 CU-11

##### P0-02.4 `relevance_score4` 不在時に起動時 ERROR で理由を出す（fail-closed は維持）
- 何を: `--domain-config` で古い自作 domain.json（`relevance` のみ）を渡すと WARNING 1 行の後 6 時間 engage なし。`load_domain_config` が `relevance_score4` 不在を起動時 ERROR + 例示値（0.3）で説明する。fail-closed はオーナー決定どおり維持し、理由を早く出すだけ。
- 根拠: `src/contemplative_agent/core/domain.py:53-56,177-181`（不在 → None → `enforce_no_threshold`）/ `src/contemplative_agent/adapters/moltbook/feed_manager.py:530-536`（session 1 回の WARNING）/ `config/templates/contemplative/` に domain.json が無い（preset は constitution / identity.md / rules / skills のみ）/ `docs/CONFIGURATION.md:154`
- 完了条件: 不在時の起動メッセージを固定するテスト 1 件、CONFIGURATION.md に 1 行。
- 規模・整合: S / repair   出典: AR-28

##### P0-02.5 lab ratchet と replay arm A/A0 の根拠を削除前に evidence に固定する
- 何を: `relevance.md` を消すと `relevance_label_set.py check` の sha pin が永久に stale になり、RFC-0045 の arm A（AUC 0.821 の根拠）が再生できなくなる。削除と同じ変更で (a) `check` が「manifest にあり tree に無い key」を退役として許容、(b) `relevance.md` の原文と sha を `docs/evidence/rfc-0045/README.md` に固定、(c) `relevance_arm_replay.py` の arm A/A0 は .2 で撤去し、(b) の原文と sha だけを残す（evidence の原文を読む replay は作らない）。
- 根拠: `scripts/relevance_label_set.py:230`（`relevance_sha256: sha256_file(DEFAULT_PROMPTS_DIR / "relevance.md")`）、`:238-247`（`stale_items`）/ `docs/evidence/rfc-0046/label-set-2026-09-28.json` manifest に `relevance_sha256` / `scripts/relevance_arm_replay.py:599-605`（`run_production` が `score_relevance_detailed` を呼ぶ）
- 完了条件: 削除後に `relevance_label_set.py check` が exit 0、`score --baseline` が回る。`docs/evidence/rfc-0045/README.md` に原文と sha。
- 規模・整合: S / repair   出典: LP-05

##### P0-02.6 fail-closed の 3 条件をテストで固定する
- 何を: 削除 PR で配線を消した結果「判定不能時に旧スコアへ fallback」や「env 空で fail-open」が静かに復活しないよう、(1) 既存 10 本を名指しで保持し、足すのは 2 本 — 空文字 env で feed cycle が engage 0 の 1 本、stub でなく `OllamaDecisionBackend` を conftest の `OLLAMA_BASE_URL=http://127.0.0.1:1`（接続拒否）で呼んで `backend_null` + Moltbook POST 0 の 1 本、(2) ADR-0113 Amendment 3 に「fail-closed は absence の一形態」1 行。watchdog の `fail_closed` 日次カウントは P2-04 へ。
- 根拠: `cli/runtime.py:173-208`（未設定 → `{relevance}`、空文字 → off）/ `adapters/moltbook/feed_manager.py:296-299,509-536`（fail_closed で cycle 終了、WARNING 1 回）/ `rfcs/0046:207`（enforce 後 1,616 行で live gate が代わりに働いた行 0 = 戻り先は不要）/ `src/contemplative_agent/core/llm/decision.py:425-440`（唯一の副作用 `keep_alive: 0` evict）
- 完了条件: `tests/test_relevance_enforce.py` の既存 10 本（`test_unconfigured_fails_closed` / `test_no_threshold_fails_closed` / `test_backend_null_fails_closed` / `test_without_enforce_the_feed_engages_with_nothing` / `test_no_threshold_is_named_and_engages_with_nothing` / `test_a_fail_closed_post_ends_the_cycle` / `test_no_backend_is_backend_null` / `test_a_raising_backend_degrades_to_backend_null` / `test_a_malformed_answer_fails_closed` / `test_row_carries_the_four_enforce_fields_and_no_live_half`）を保持したまま新規 2 本が green、ADR-0113 Amendment 3 に 1 行。既存テストは不変（保持 10 本を名指し）。
- 規模・整合: S / repair   出典: SA-31

##### P0-02.7 ADR-0113 の Status を 10-17 の削除 PR で 3 日付の amended + `partially-supersedes ADR-0112` に揃える
- 何を: ADR-0113 は追補 2 本で本番挙動が 3 回変わったが Status は bare `accepted`。10-17 の削除 PR（Amendment 3 = .6、ADR-0112 の partial supersede = .8 と同じ PR）で Status を `accepted (amended 2026-10-07, 2026-10-09, 2026-10-17) — partially-supersedes ADR-0112 (D2 kill switch, D5 skill-selection shadow retired)` にし、5 面（本文・ja・索引・`graph.jsonld` ほか `tests/test_adr_status_consistency.py` が見る面）で揃える（P1-03.2 の 0113 行も同じ文字列）。追補 1 の冒頭に「`:458` が予約した further ADR でなく追補にした理由（同じ face・同じ seam の閾値側だけを変える）」を 1 文足す。
- 根拠: `docs/adr/0113:5`（Status `accepted`）、`:236`（Amendment 2026-10-07）、`:337`（Amendment 2 2026-10-09）、`:359`（「narrows ADR-0112 Decision 2」）、`:458`（「a further ADR」の予約）/ `docs/adr/README.md:178,186`（前向きの半分 `partially-supersedes` と、per-node の edge ⇔ Status・両半分の検査）
- 完了条件: ADR-0113 の Status が上の文字列で 5 面一致し、`test_partial_supersede_edges_are_reciprocal` と per-node の edge ⇔ Status 検査が .8 と同じ PR で green、追補 1 に理由 1 文。既存テストは不変。
- 規模・整合: S / repair   出典: AB-12   順序: 10-17 の削除 PR に同梱（.2 / .6 / .8 と同 PR）

##### P0-02.8 ADR-0112 を partially-superseded にし、phase separation の未決を閉じる
- 何を: 削除 PR で ADR-0112 の D5（skill-selection shadow、一度も動いていない）と D2（未設定 = kill switch）が退役する。ADR-0112 を `partially-superseded-by ADR-0113`（存続: seam / 3 型契約 / 適合キット / Ollama logprobs 実装）に書き換え、`graph.jsonld` に `partiallySupersedes` の双方向エッジ、Review-when から「eight-gate clock」を削除。同じ注記で Alternatives の「Phase separation now … Deferred — 未決」を「判定モデル = 生成モデルで交代が無いため moot、別モデル採用時に再訪」と閉じる。再訪の引き金は ADR に置かず、`docs/runbooks/model-swap.md`（P1-07.11）のチェックリストの 1 行にする。
- 根拠: `docs/adr/0112:5`（Status `accepted`）、`:187-193`（2026-09-22 注記: 時計未開始）、`:238-242`（Deferred — 未決, revisit at the enforcement reading）/ `docs/adr/0113:548-549`（DECISION_MODEL = served model、交代なし）/ `tests/test_adr_status_consistency.py:380`（`test_partial_supersede_edges_are_reciprocal`、graph は repo 直下 `graph.jsonld`）
- 完了条件: `test_partial_supersede_edges_are_reciprocal` green、ADR-0112 の Deferred に閉じた注記、Review-when に eight-gate clock が無い。ADR-0112 を partially-superseded にする同じ commit で `docs/runbooks/model-swap.md` のチェックリストに「ADR-0112 の phase separation を再訪」1 行（runbook が未作成ならこの 1 行のチェックリストとして起こし、表と手順は P1-07.11 が足す）。
- 規模・整合: S / repair   出典: AB-11 AB-41

##### P0-02.9 `relevance_shadow.py` を `relevance_gate.py` に改名する
- 何を: enforce 後、このファイルが「the relevance gate」そのもの（docstring）だが、名前と `reset_relevance_shadow` が shadow のまま。削除 PR と同時に `git mv relevance_shadow.py relevance_gate.py`、`reset_relevance_shadow` → `reset_relevance_gate`、conftest の autouse fixture `_reset_relevance_shadow`（`tests/conftest.py:126-140`）→ `_reset_relevance_gate`、`scripts/relevance_label_set.py:50` / `scripts/relevance_shadow_reading.py:113` の docstring 更新（`relevance_shadow_reading.py` のファイル名は保持 — shadow 期のログを読む計器）、ADR-0113 / `graph.jsonld` / `.claude/skills/shadow-mode-validation` の参照を更新。evidence に固定した分は触らない。
- 根拠: `src/contemplative_agent/adapters/moltbook/relevance_shadow.py:1-12`「The relevance gate … One judge, fail-closed … the only relevance judgment the feed acts on」、`:206`（`def reset_relevance_shadow`）/ 役割の変遷 `5cf42b7` → `128fe60` → `96881f5`
- 完了条件: `grep -rn "relevance_shadow" src/ tests/ scripts/ evals/ docs/ graph.jsonld .claude/` が `docs/evidence/` と `scripts/relevance_shadow_reading.py` のファイル名以外で 0 件。書き換える既存テスト: `tests/conftest.py::_reset_relevance_shadow`（fixture 改名）、`tests/test_relevance_enforce.py::_reset`（`:60` の `rs.reset_relevance_shadow()`）、`tests/test_relevance_shadow.py`（`:29,64` の import / reset — ファイル名は `tests/test_relevance_gate.py` に `git mv`、規約 `tests/test_<対象>.py`）、`tests/test_relevance_cache.py:38,60`、`tests/test_agent.py:15` / `tests/test_feed_judgment_memo.py:18` の import 行。
- 規模・整合: S / repair   出典: CH-16


**依存**
- 2026-10-15（木）03:00 JST submolt-scan のログ（`logs/llm-calls-2026-10-14.jsonl`、`logs/submolt-scope-2026-10-14.jsonl` — 10-17 の Step 1c の D-P0-02-1 行の照合コマンドの材料）
- P2-04.3（`CONFIGURATION.md:433` の段落の所有者 — .3 が参照。P2-04 は着手 2027-02-06 で本束より後なので、.3 は現行の `:433` の段落に合わせて書き、P2-04.3 が段落を書き換えたら更新）
- ADR-0112 / 0113、RFC-0045 / 0046 / 0047
- → 参照元: P1-03（追補による supersession の語彙・索引 — .8 は参照のみ、先行は不要。着手 11-28）、P1-07.11（`docs/runbooks/model-swap.md` のチェックリスト — .8 が「phase separation を再訪」の行を先に置く）、P1-03.2（索引の 0113 行 = .7 の文字列）、P0-06（v2.13.0 `/release-doi`、11-07 の決定と 11-16〜20 の tag は削除 PR の後。CHANGELOG に Unreleased 節は現在無く、最新は v2.12.0 2026-09-12）、P0-05（smoke は旧 gate 削除後に固定）、P1-07.13（`cli/runtime.py` は .2 の後）、P1-15（RFC-0047 face 較正）、P2-04（watchdog の fail_closed 日次カウント）


#### P0-03 公開データの開示境界の修理（embedding 入り .bak・ロック・絶対パス）
- 狙い: `scripts/sync-research-data.sh` の rsync 除外が公開 repo の唯一の開示境界だが「書いた名前しか守らない」方式のため、embedding 入り 72 MB バックアップ・lock・隠し state・絶対パス（ユーザー名）が現物で公開されている。北極星のセキュリティ層（absence 維持、ADR-0007）と研究層（DATACARD の自己記述と現物の一致）に直結する修理で、能力は増やさない。
- 期限・順序: 着手 10-10 の土曜ゲート（§4.0。残りは 10-24 の週の先行項目、11-21 に再入場）。期限 11-21（D-P0-03-1 / -3）。週の言い方は §0（「X の週」= 土曜 X の前の月〜金、「着手 X」= X のゲートで方針を確かめ X の後の平日に PR）。.1（bak の除去）は着手 10-10（10-12〜16 の平日に PR = 10-17 の週。10-10 の決定は 10-17 に遡及記録）。残り（.2〜.11、.14、.16）は 10-24 の週（10-19〜23。10-24 のゲートの決定を要しない — 方針は D-P0-03-2 が 10-10 に決めた）。ただし .10 の見出しの描画 / sidecar と .14 の HF card の License 節は D-P0-03-3（11-21）の後。sync は毎日 push する（data repo 最新 commit `sync: 2026-10-09T20:30:08Z`）ので .1 と除外の拡張（.2）を先に、allowlist 反転（.3）と scan（.6）は P1-08 のシェル層テストと歩調を合わせ（P1-08 の着手 12-19 より前は現行の `tests/test_sync_research_data_shell.py` の形で書き、P1-08.1 / .2 / .3 が入ったら macOS セル・期待集合・harness に載せ替える）、.5 の正規化段は .6 の scan より前に走らせる。data repo の手保守ファイル（DATACARD / NOTICE / README / llms.txt / `.zenodo.json` / `graph.jsonld` / `.gitignore` / workflow）の編集と `git rm` は sync を行う Mac の checkout（`sync-research-data.sh:5` の `DATA_REPO`）でだけ行い、その間は sync job を unload する（.16 (c)。DATACARD への 1 行は 10-17 の週の 10-16 まで — P3-05.1 / .2 が 10-17 の週に data repo を触るため。.16 の (a)(b)(d) の修理は 10-24 の週）。`_gc_trash/` の扱い（D-P0-03-2）は 10-10 に決め 10-17 に遡及記録（上限 5 に数えない）。履歴書換の可否（D-P0-03-1）と第三者断片・表示名の扱い（D-P0-03-3）は 11-21 の土曜ゲート（撤回ポリシー D-P3-05-2 と同じ回、データ版 DOI の前 — データ版は v2.13.0 と同時には切らず最初の新版は 12-05 のゲートの後）。`sync-research-data.sh` の順序: .2（backup + data repo `.gitignore`）→ .3（sync allowlist。helper `_excludes()` の書き換えと `RSYNC_BIN` の解決はここで 1 回）→ .16（push 段だけ。rsync 呼び出しは触らない）→ P2-05.1（allowlist を 2 本に分ける）。.5 の ADR-0020 の段落は後の P3-04.1 の PR（10-31 の週）の `## Amendment` に寄せる（.5 のコード PR は 10-24 の週のまま）。.6 の weekly-gate Step 6d の読み手 1 行は 10-24 前の同梱 PR に同乗（Step 6d の所有者は P2-05.1 — 推定）。.9 / .14（文言と宣言の整合）は 10-24 の週に入れ D-P0-03-3 より前に。.11 は v2.13.0 の tag（11-14 の決定の後、11-20 まで）より前（P0-06.6 段 (5) の停止基準が .11 の不在テストを読む）。この束の決定: D-P0-03-1 / -3（11-21）、D-P0-03-2（10-10）。
- 束の完了条件:
  - `git -C contemplative-agent-data ls-files | grep -E '\.bak|\.lock$|\.DS_Store|_gc_trash/'` が空
  - `grep -rl '/Users/' contemplative-agent-data --exclude-dir=.git | wc -l` が 0 で、新規 sync でも増えない（commit 前 scan が abort する）
  - `tests/test_sync_research_data_shell.py` に negative case 7 種（`knowledge.json.bak-x` / `.run.lock` / `.staged.lock` / `credentials.json` / `cloud.env` / `_gc_trash/x.md` / `x.tmp`）と allowlist 反転テスト、remote にしか無い commit が sync の後も残るテスト（.16）があり緑
  - 両 rsync script が同一の `config/sync-excludes.txt` を参照し（script 本文を grep する text-level テスト、ubuntu で走る）、sync 側は allowlist（`--include` 列挙 + `--exclude='*'`）、data repo `.gitignore` が同じファイルから生成されている。両 script が `RSYNC_BIN` を 1 回解決し、rsync 3.x が無ければ `ERROR:` で止まる（.3）
  - DATACARD に「2026-07-18 bak の公開期間」「07-10 / 07-18 の手動介入」「退役 skill の扱い」「第三者逐語重なりの測定値」の 4 注記、NOTICE / DATACARD / HF card に「no raw quoted」文言が 0 で帰属記述が実装（見出しの表示名 + post id 8 文字）と一致、本体 `git ls-files | grep -c real_sample` = 0
  - `NOTICE:22` / `DATACARD.md:33` の `reports/analysis/` 行に第三者由来断片の注記（.9）、README / README.ja / llms.txt の「no restriction・一切の制限なく・unrestricted」5 箇所が 0（.14）

##### P0-03.1 embedding 入り bak を tree から外し、除外を `knowledge.json.*` / `*.bak*` に広げる
- 何を: `knowledge.json.bak-dup-cleanup-20260718`（72,378,529 B、3,250 行すべてに 768 次元 `embedding`、現 store の 2026-07-17T18:45 以前の行と同一集合）を data repo から `git rm` し、`MOLTBOOK_HOME` 側の元ファイルは `knowledge.backups/`（除外済み）へ移す。`sync-research-data.sh` の除外に `knowledge.json.*` と `*.bak*` を足す（`*.bak.*` は `.bak-` に一致しない — fnmatch で確認）。
- 根拠: `scripts/sync-research-data.sh:89-91`（`knowledge.json` 完全一致と `*.bak.*`）; `DATACARD.md:28,47,106`（embedding は export で落とす）; `docs/runbooks/runtime-backup-restore.md:35`（「Historical `*.bak.*` snapshots stay as-is」— この名前は想定外）
- 完了条件: `git ls-files | grep -c bak` = 0; `test_sync_research_data_shell.py` に `knowledge.json.bak-x` / `knowledge.json.bak.1` の negative case; DATACARD の Excluded data に「bak は 2026-07-18〜10-xx の公開履歴に存在」の 1 行
- 規模・整合: S / repair   出典: DE-01 CP-09 SA-11 OI-40 RF-31 RD-37

##### P0-03.2 除外リストを `config/sync-excludes.txt` に統合し、`backup-runtime.sh` と data repo `.gitignore` をそこから生成する（sync 側は .3）
- 何を: `scripts/backup-runtime.sh:135-147` の除外を `config/sync-excludes.txt`（`--exclude-from`）に移し、sync 側に欠けている `.run.lock` / `.staged.lock` / `.last_*` / `*.env`（cloud sibling の `cloud.env` は鍵ファイル）を同じファイルに足す（sync 側 `scripts/sync-research-data.sh:70-98` の rsync 呼び出しは触らず、allowlist への反転と同ファイルの参照は .3 で 1 回）。data repo の `.gitignore`（現在 4 行）を同じリストから生成し、`git add -A` に対する二重の壁にする。私的 backup 側（`backup-runtime.sh:134-148` の除外と `:162` の `rm -f`）にも `cloud.env` / `*.env` が無いので、同じ共有リストを読ませ `rm -f cloud.env` を足す（`docs/runbooks/runtime-backup-restore.md:22` の除外表にも 1 行）。私的 backup repo の履歴に `cloud.env` があった期間の扱いは P1-10.9 の所在表（7 番目）。
- 根拠: `backup-runtime.sh:143-144` は両 lock を除外、`sync-research-data.sh:69-99` には無い（`:26`「Keep this list in step」が守られていない）; data repo `git ls-files` に `.run.lock` `.staged.lock` `.DS_Store` `reports/.DS_Store` `skills/.last_insight`; `contemplative-agent-cloud/src/contemplative_agent_cloud/cli.py:40-55`（`$MOLTBOOK_HOME/cloud.env` を `os.environ` に読む）、`.claude/skills/agent-run/SKILL.md:62`; `backup-runtime.sh:134-148,162`（除外と `rm -f` は `credentials.json` のみ）
- 完了条件: backup 側が `--exclude-from="$SCRIPT_DIR/../config/sync-excludes.txt"` を持つ text-level テスト（script 本文の grep、ubuntu で走る。両 script の一致は .3）; backup 側に `rm -f cloud.env` の行; data repo `.gitignore` に `credentials.json` `*.env` `logs/` `*.sqlite*` `relevance_cache.json` `*.bak*` `*.tmp` `.*.lock` `.archive/` が並ぶ; `git status --ignored` で lock が ignored に出る。書き換える既存テスト: `tests/test_backup_runtime_shell.py::test_the_excludes_alone_keep_the_family_out_of_the_transfer`（`:177` の `--exclude='…'` regex を共有ファイル読みに。darwin 限定なので macOS セルで passed、ubuntu では skip）
- 規模・整合: S / repair   出典: DE-02 DE-03 DE-05 CP-11 SA-15 SA-32   順序: `sync-research-data.sh` は .2 → .3 → P2-05.1（本項目は sync 側を触らない）

##### P0-03.3 除外テストを「公開してよい名前の allowlist」に反転し、未知の名前は fail-closed にする
- 何を: `tests/test_sync_research_data_shell.py` を、`MOLTBOOK_HOME` 直下に現れてよい名前の列挙（identity.md / knowledge.json / constitution/ / skills/ / rules/ / views/ / reports/ / snapshots/ / pipeline/ / meditation/）と negative case 7 種（.1 の bak、両 lock、`credentials.json`、`cloud.env`、`_gc_trash/`、`*.tmp`）に書き換える。sync script 側も `--include` 列挙 + `--exclude='*'` にし、未知の top-level 名は stderr に名前を出して転送しない。同じ `config/sync-excludes.txt` を `--exclude-from` でも参照し（allowlist の内側の名前 — `*.bak*` / lock 等 — に効く）、テスト helper `_excludes()`（`tests/test_sync_research_data_shell.py:42-44`、script 本文の `--exclude='…'` を regex で読む）は `config/sync-excludes.txt` を読む形に書き換える（書き換えはここで 1 回）。開示境界の rsync の実体を 1 つに固定する: 両 script の冒頭で `RSYNC_BIN` を 1 回解決し（推奨: Homebrew の rsync 3.x を明示パスで呼び、無ければ `ERROR:` で止める。OS 同梱版 — macOS 15 以降は openrsync、外部知識 — に黙って落ちない）、境界テストも同じ解決関数で rsync を選ぶ。隠し state（`reports/analysis/.anomaly-sweep-state.tsv` + `.corpus.tsv`、`.api-drift-state.tsv`、`.approval-join-state.json`、`skills/.last_insight`、`constitution/.last_constitution_amend`）を allowlist に載せるか `.private/` へ書き先を変えるかは .8 (b)(c) と同じ決定で書く（載せないなら negative case に）。
- 根拠: `tests/test_sync_research_data_shell.py:4`（「disclosure boundary」と自称）だが固定しているのは `VECTOR_FILES` 4 名・3 テストのみ（`:34-39,75-96`）; 現物の漏れ 6 種（.1 / .2）はすべて「名前を書いていなかった」経路; `scripts/sync-research-data.sh:69` と `scripts/backup-runtime.sh:134`（`rsync -a --delete` を PATH から呼ぶ）、`tests/test_sync_research_data_shell.py:48-70`（`_transfer` も PATH の `rsync`）、`git grep 'rsync --version\|openrsync' -- scripts tests docs` 0 件（openrsync との照合差が今の除外に効くかは未検証 = 推測）
- 完了条件: negative case 7 種が赤→緑; 未知の名前 `foo.json` を置いた transfer で転送されず stderr に名前が出るテスト（rsync を要するこの 2 群は macOS セルで passed、ubuntu では skip — P1-08.2 の期待集合に登録）; 両 script が同一の `--exclude-from="$SCRIPT_DIR/../config/sync-excludes.txt"` を持つ text-level テスト（ubuntu で走る）。`RSYNC_BIN`: 両 script に解決があり解決できないとき rc≠0 と `ERROR:` を出すテスト、`"$RSYNC_BIN" --version | head -1` の行が data repo の次の sync commit 本文（P0-06.4 の要約行の隣）と backup ログに残り、反転テストが macOS セルで両実装（Homebrew 版と `/usr/bin/rsync`）とも passed、CONFIGURATION に「開示境界は rsync 3.x の照合規則を前提」1 行。書き換える既存テスト: `tests/test_sync_research_data_shell.py::_excludes`（helper）とそれを使う `::test_no_embedding_file_or_its_journal_reaches_the_public_transfer` / `::test_the_counterweight_research_data_still_goes` / `::test_both_sqlite_rules_are_prefix_matches`、`::_transfer`（`:62` の `"rsync"` を解決関数に）
- 規模・整合: S / repair   出典: SA-10（DE-01 CP-09 SA-15 のテスト部分を含む）R3-OSX-04（旧 P0-03.15）   順序: .2 の後、.16 / P2-05.1 の前（`sync-research-data.sh` の rsync 呼び出しはここで 1 回反転）。P1-08.1 / .2 / .3（着手 12-19）より前は現行のテストの形で書き、入ったら macOS セル・期待集合・harness に載せ替える

##### P0-03.4 `--delete` は除外済みの受け側ファイルを消さない — 撤回手順を sync に入れ、誤ったコメントを直す
- 何を: rsync の `--exclude` は受け側の同名ファイルを `--delete` から保護する（消すには `--delete-excluded`）ので、除外を足しても過去の公開は撤回されない。`backup-runtime.sh:158-170` が既にやっている「excluded-but-present を `rm -f` してから `git add -A`」と同じ段を sync に置き（または除外パターンごとに `git rm -r --cached --ignore-unmatch`）、`:32-34` の「`--delete` means an archive … is withdrawn on the next sync」を訂正する。撤回段（rm / `git rm --cached`）は「公開しない」クラスの名前（.2 の共有除外のうち秘密・bak・lock・tmp）だけに当てる。受け側が所有する governance 10 名（`sync-research-data.sh:71-80` の `.gitignore`〜`DATACARD.md`）と、export が書き直す `knowledge.json`（`:89` で除外、`:107-109` で再生成）は対象外 — 同じ `--exclude` 列が「`--delete` から守る」（`:23-26`）と「公開しない」の両方に使われているので、一律に消すと無人の 05:30 sync が README / LICENSE / DATACARD を消して push する。
- 根拠: `scripts/sync-research-data.sh:24-26`（README 等を除外するのは `--delete` から守るため）、`:32-34`（「withdrawn on the next sync」と書く）、`:55-57`（同じ script が「PUBLIC repo's history, where `--delete` cannot retract them」と書く。HEAD `2cad850` で `:33` と `:57` が同じ script の中で食い違う）; `backup-runtime.sh:158-161`「rsync --exclude also shields a destination copy from --delete」; 現物: `.DS_Store` は除外（`:94`）なのに 2 件 tracked
- 完了条件: テスト「受け側に除外対象（`.DS_Store`、`x.bak`）が残っていても sync 後に消える」; テスト「governance 10 名と `knowledge.json` の 11 名は sync 後も tree に残る」; `.DS_Store` 2 件が次回 sync で tree から消える（container に rsync 無し — 実走は macOS）
- 規模・整合: S / repair   出典: SA-13（DE-03 SA-32 の `git rm` 部分を含む）

##### P0-03.5 絶対パス（ユーザー名）の書き手を `$MOLTBOOK_HOME` 相対にし、sync 出力側で一括正規化する
- 何を: `core/snapshot.py` の manifest 6 欄と `scripts/value_layer_due_check.py` の `path` 欄を `$MOLTBOOK_HOME/...` 表記に変える（ADR-0020 には「replay に絶対パスは不要」の 1 段落を P3-04.1 の PR の `## Amendment` に寄せる。ADR-0020 の追補を 2 本にしない）。既存分（manifest 100/100、`pipeline/value-layer/*.json` 6 件、`reports/analysis/*.md` 11 件、計 545 箇所）は MOLTBOOK_HOME を手で直さず、sync の rsync 後・`git add` 前に 1 箇所で `$HOME` 文字列を `$MOLTBOOK_HOME` に置換する正規化段を置く。書き手一覧に `scripts/pipeline_watchdog.sh:189`（失敗日のみ `Logs: \`$LOG_DIR\`` = `$MOLTBOOK_HOME/logs` の絶対パス）を足す。本体 repo 側の `/Users/` 7 ファイル 10 行（`docs/evidence/rfc-0023/novelty-retrieval-dry-run-20260904.json` の `provenance.home` 等 3、`novelty-replay-ab-20260905.json` 1、`rfc-0017/comment_golden-skills-off-20260902.json` 1、`tests/test_cli_schedule.py:109,112`、`tests/test_value_layer_approval_join.py:54`、`docs/plans/task-ready-herdr-modular-eclipse.md:122`）も直す — evidence の書き手は `$MOLTBOOK_HOME` 表記、tests は `/Users/example`、`weekly-gate/SKILL.md:339` の例示は残す。weekly-report skill に「パスは `$MOLTBOOK_HOME` / `$PROJECT_ROOT` 表記」の規約を 1 行足す。
- 根拠: `core/snapshot.py:182-187`（`str(views_dir)` 等 6 欄）; `scripts/value_layer_due_check.py:173,219`（`"path": str(rules_dir)`）; data repo `grep -rl /Users/ --include=manifest.json snapshots | wc -l` = 100、`grep -rho '/Users/[^ "]*' | wc -l` = 545; `.claude/skills/weekly-gate/SKILL.md:339` は rfcs/ で `/Users/...` を公開不可と数える（機械の挙動と不一致）; `scripts/pipeline_watchdog.sh:189`（`Logs:` 行）; 本体側 7 ファイル 10 行
- 完了条件: `tests/test_snapshot.py` に「manifest に `/Users/` も `Path.home()` も現れない」; data repo `grep -rl '/Users/' | wc -l` = 0; 本体 `grep -rl '/Users/' docs/evidence tests docs/plans | wc -l` = 0（本体の 7 ファイル 10 行の修理と grep 0 件の正本はこの項目。P1-10.12 は weekly-gate Step 6d の点検範囲の 1 行だけ）; 正規化段が .6 の scan より前に走る（さもないと最初に ❌ が出た日に sync が `/Users/` で abort し、公開ミラーの停止と pipeline の故障が重なる）; P3-04.1 の ADR-0020 `## Amendment` に本項目の 1 段落
- 規模・整合: S / repair   出典: DE-07 SA-12 SA-36 OI-39 GO-46 VL-44 WO-42   順序: コード PR は 10-24 の週、ADR-0020 の 1 段落は後の P3-04.1 の PR（10-31 の週）の `## Amendment` に寄せる

##### P0-03.6 data repo に秘密・パススキャンを置く（sync の commit 前 abort + gitleaks workflow）
- 何を: `sync-research-data.sh` の `git add -A` 後・commit 前に stdlib 正規表現で staged 差分を走査し、ヒットで commit を中止し stderr に `ERROR:` を出す（watchdog / anomaly sweep が拾う形）。regex は 1 ファイル `config/secret-patterns.txt` に置き、値の形に限る（`sk-[A-Za-z0-9]{20,}` / `hf_[A-Za-z0-9]{30,}` / `ghp_…` / `-----BEGIN [A-Z ]*PRIVATE KEY` / `Authorization: Bearer [A-Za-z0-9._-]{20,}`、現 tree 0 件 = baseline）。`api_key` / `Bearer ` の語彙は他エージェント本文（comment-report 6 ファイル）に一致し、入れた日から日次 sync が止まるので使わない。`/Users/` と `/home/` は .5 の正規化段の後段で走査。メール形は owner の 1 件を allowlist にして足し、既存一致（本文未読）は人間の点検対象 — ただしメール形は secret ではなく個人データで、保持・削除は P3-05.14 (a) (iii) の方針に従う。同じファイルを sync pre-commit / data repo の `.github/workflows/` gitleaks（SHA pin、本体 `verify.yml` と同型）/ weekly-gate Step 6d / harness hook（P2-03）の 4 つが読む（P2-05.1 の無人経路スキャンと P1-10.12 の pre-commit 1 行はここに一本化）。
- 根拠: `.github/workflows/verify.yml:47-58`（gitleaks は本体のみ）; data repo に `.github/` 無し; `sync-research-data.sh:113-121`（`git add -A` → commit、検査無し）; `.claude/verify.md:20`（SAST は bandit = コード対象）; data repo 現 tree: 値の形 5 種のヒット 0、`api_key` 語彙は comment-report 6 ファイル、メール形 7 ファイル（R1-SEC、ファイル名のみ確認）
- 完了条件: 既存 tree の baseline 0 件（値の形 5 種）; fixture（`sk-…` を含むファイル）を置くと sync が rc≠0 で commit しない; data repo の Actions で gitleaks が緑; 4 つの読み手が同じ `config/secret-patterns.txt` を参照するテスト; メール形の計数条件を明記する（対象ファイル種別 = 公開 `*.md` / `*.json` の全体（comment-report の Context ブロックと `knowledge.json` を含む）、defang 形（`[at]` / `(at)` 等）を許容する正規表現 — R1-SEC の「7 ファイル」と R2-ETH の再計測「Context 0 / 他の公開 md 2 / `knowledge.json` 0」の差は計数条件の差として記録する）
- 規模・整合: S / repair   出典: SA-16（OI-39 WO-42 の scan 部分を含む）SA-08 WO-43（P2-05.1 のスキャン部分）SA-25（P1-10.12 の pre-commit 行）

##### P0-03.7 `_gc_trash/`（書き換え前 skill 原本 10 件）の扱いを 2026-08-22 の判断に揃える
- 何を: `.archive/` を「退役判断の系譜を公開しない」として除外した判断（commit `4f53259`）と、`_gc_trash/2026-07-10-clean-rewrite-originals/*.md` 10 件（`origin: auto-extracted`、README 無し）が公開されている現状を一致させる。推奨は除外 + `git rm`（履歴には残る旨を DATACARD に注記）。公開を続けるなら DATACARD の構造表に由来を書く（D-P0-03-2）。
- 根拠: data repo `git ls-files | grep _gc_trash` 10 件; `git log 4f53259`（2026-08-22）; `sync-research-data.sh:28-34,98`（`.archive/` のみ除外）; `docs/plans/rustling-waddling-turtle.md:189`（`_gc_trash` を `.archive/` の先例と呼ぶ）
- 完了条件: DATACARD に退役 skill の扱いが 1 文で書かれ、除外リスト（.2 の共有ファイル）と一致; 除外なら `git ls-files | grep -c _gc_trash` = 0
- 規模・整合: S / neutral   出典: DE-04 SA-14（CP-10 RD-37 の `_gc_trash` 部分を含む）

##### P0-03.8 来歴の穴を DATACARD に書く（07-10 / 07-18 の手動介入、隠し state、stale な amend マーカー）
- 何を: DATACARD に (a) 2026-07-10 の skill clean-rewrite と 07-18 の「dup-cleanup」（行は 1 つも消えておらず `valid_until` 96 行差のみ）を Preprocessing として 1 段落、(b) `reports/analysis/.anomaly-sweep-state.tsv`（+ `.corpus.tsv`）、`.api-drift-state.tsv`、`.approval-join-state.json`、`skills/.last_insight` の weekly baseline / pipeline state を「Pipeline state」として説明（または `reports/.private/` へ書き先変更。.3 の allowlist と同じ決定）、(c) `constitution/.last_constitution_amend`（2026-03-27）は直接書き込み経路でしか更新されず staged 採用（05-06 / 08-10）を反映せず、src に reader も無い（due 判定は audit の `last_adopted_ts`）— マーカーを退役させる: `memory_cmds.py:316` の書き手を外し、テスト 3 箇所（`tests/test_cli_adopt.py:507-519`、`test_constitution.py:178`、`test_constitution_shadow.py:118`）を書き換え、sync 除外に加えて公開 repo から削除し、DATACARD に「最終改正は audit / value-layer JSON が正」の 1 行（P3-04 のマーカー退役項目を吸収。staged 経路でも書く案は正本が 2 つになるので採らない）。
- 根拠: bak と現 store の行集合一致・`valid_until` 213 対 309（python 集計）; `DATACARD.md:20-21`「never hand-edited」; `scripts/weekly-analysis.sh:158,384,421`（書き手）; `cli/memory_cmds.py:315-316`（`wrote` のときだけ marker を書く）と `cli/adopt.py` に `write_run_marker` 無し; `pipeline/value-layer/value-layer-2026-10-02.json:15` `last_adopted_ts: 2026-08-09`; `scripts/value_layer_due_check.py:402`（due 判定は audit の `last_adopted_ts`、マーカーの reader は src に無し）
- 完了条件: `grep -c 'dup-cleanup\|2026-07-10' DATACARD.md` ≥ 1; 公開 tree の隠しファイルが 0 または全件 DATACARD に説明; 公開 repo に `.last_constitution_amend` が無く `grep -rn last_constitution_amend src/ tests/` が 0 件; DATACARD に「最終改正は audit / value-layer JSON が正」の 1 行
- 規模・整合: S / repair   出典: CP-10 DE-08 RF-32 VL-29 PF-14 SB-25

##### P0-03.9 第三者投稿との逐語重なりを測り、「no raw quoted」の文言を測定値つきに改める
- 何を: `analysis/third_party_overlap.py`（入力は data repo のみ、出力は n=8/12/20 語の件数と月別分布、本文は出さない。入力系列に `reports/analysis/*.md` と `snapshots/*/skills/*.md` も加え、Internal note / Output に相手表示名を含む「名指しブロック」数の計測行を足す（R2-ETH-09））を data repo か本体に置き、DATACARD「Third-party content」と HF card の「contains no raw quoted」文言を測定値つきに改める（開示）。文言 sweep の対象に `DATACARD.md:98`「all pattern text … machine-generated」と HF card の「owner-authored distillate … applies cleanly to every row」「never hand-edited」を加え、07-10 / 07-18 の手動介入（.8 (a)）と整合させる。carve-out が `knowledge.json` / `reasoning.md` の該当 span にも及ぶことを NOTICE に書く。weekly 文書: `NOTICE:22` と `DATACARD.md:33` の `reports/analysis/` 行に「第三者 Context 由来の逐語断片を含みうる（測定値つき）」を付け、carve-out の対象を `**Context:**` ブロック限定から「`reports/**` 内の第三者投稿由来テキスト全般」に広げ、`config/prompts/weekly-analysis.md` に「Context 本文を 8 語以上そのまま写さない（post id と要約で指す）」の 1 行を足す。この 3 つは 10-24 の週に入れる。export 境界で第三者由来の N 語以上の span を伏せ字にする projection（エージェントの記憶は触らない）は D-P0-03-3。
- 根拠: HF `Shimo4228/contemplative-agent-data` card License 節、`NOTICE:49-50`、`DATACARD.md:113-114`「contains no raw quoted context … cleanest fully-CC0 surface」/ 測定（R1-REP、2026-10-10、python -I、件数のみ・本文未読）: `knowledge.json` 10,985 行 × `reports/comment-reports/*.md` の `**Context:**` 7,442 ブロックで、第三者 Context にだけ現れる連続 8 語を含む pattern 469 行、12 語 311 行、20 語 121 行（月別 12 語: 07 月 99 / 08 月 102 / 09 月 92 / 10 月 18、06 月以前 0 — 06-23 per-episode distill・06-28 gemma 切替以降に集中、因果は推定）; `snapshots/*/reasoning.md` 14 件中 7 件にも 12 語以上の一致（`NOTICE:23` は `snapshots/` を owner-authored に列挙）; skills 53 / identity / constitution / rules は 0 / weekly 文書（R2-ETH、`python3 -I`、本文未出力）: `reports/analysis/*.md` 78 ファイル中 43 が一致（5,056 箇所、`weekly-YYYY-MM-DD.md` 28 本中 20）、一致は `## Random Sample` H2（`scripts/weekly_sample_splice.py:38`、08-28 以降）より前から出る = LLM 執筆の本文転記; `scripts/weekly-analysis.sh:145-146`; `reports/analysis/` に `**Context:**` ブロックは 0 件なので `NOTICE:38-45` の carve-out は届かず、`NOTICE:22` は `reports/analysis/` を owner-authored CC0 に列挙する
- 完了条件: 測定 script が repo にあり週次か CI で件数が出る（入力 3 系列 = patterns / weekly / snapshot skills、名指しブロック数の行を含む）; NOTICE / DATACARD / HF card に「no raw quoted」「never hand-edited」「applies cleanly to every row」の文言が 0 か測定値つき; D-P0-03-3 の決定が第 4 章（`gate_item`）に記録されている; NOTICE / DATACARD の `reports/analysis/` 行と carve-out の範囲が直り、`config/prompts/weekly-analysis.md` に 1 行（8 語一致件数を土曜の materials に出す行は P2-04.14 の側）。既存テストは不変。
- 規模・整合: S / neutral（n-gram ヒューリスティック。言い換えや引用符付き短句の扱いで ±数十行は動く）   出典: R1-REP-06 R2-ETH-01（旧 P0-03.12）

##### P0-03.10 NOTICE / DATACARD の帰属記述を実装（見出しの表示名 + post id 8 文字）に合わせる
- 何を: `NOTICE:38-42` / `DATACARD.md:111-112` の「隣接する `## Sources` block で帰属」を「帰属は各エントリ見出しの相手エージェント表示名と post id（先頭 8 文字）。`## Sources` は引用元投稿自身の節」に直す。新規報告の見出しに post id 全桁（または defang した permalink）を描画するか、日次の `sources.json`（post_id → 表示名 → defang URL）を sidecar として同期するかは D-P0-03-3 の D（表示名の仮名化）の後（P3-05.14 (d) の 3 択「残す / 仮名化 / 落とす」と同じ 11-21 の回）。
- 根拠: `NOTICE:38-42`、`DATACARD.md:111-112`; `src/contemplative_agent/core/report.py:180-224`（`_entry_lines` に "Sources" の描画無し、`:206-208` `post8 = post_id[:8]`）; data repo 217 報告中 `## Sources` は 136 ファイル・719 回、すべて `**Context:**` 本文の内側（引用元投稿自身の節）で 7,442 Context ブロック中 1 割弱; 見出しの 8 文字 id は私的 episode log でしか解決できない
- 完了条件: NOTICE / DATACARD に `## Sources` を帰属手段として書く文が 0; takedown 手順（P3-05.14）が「post id で特定」と書ける
- 規模・整合: S / neutral   出典: R1-REP-07

##### P0-03.11 本体の公開 repo から本番 episode 形式の fixture `tests/fixtures/benchmark/real_sample.jsonl` を除去し、episode 形式のファイルが tests/ に無いことを固定する
- 何を: `real_sample.jsonl`（50 行、`original_post` / `their_comment` / `content` / `target_agent` / `agent_name` / `post_id` を平文で持つ）を `git rm` し、`tests/benchmark_distill.py` の入力を `.notes/` 配下のローカル episode に限る（`evals/jev_arm.py` の `assert_private_output` と同型の入力側 assert）。不在テスト 1 本: `tests/ docs/ evals/ config/` 配下の `*.json` / `*.jsonl` を `json.load` して key を再帰的に集め、禁止 key（`original_post` / `their_comment`）があれば赤（`docs/evidence/` の 4 本 — `rfc-0023/novelty-retrieval-dry-run-20260904.json` 等 — は文字列値の中の一致なので key 検査なら allowlist 不要）。`<untrusted_content` だけは値側の文字列検査で `docs/evidence/` を除外。`git rm` と同じ PR で `tests/benchmark_distill.py:300` の既定 dataset（`--dataset` default `real_sample`）を `.notes/` 側へ変え、「既定 path が repo 内を指さない」assert を同じテストに置く（禁止 key を持つ合成 golden があれば manifest の `source: synthetic` で除外）。履歴に残る旨は P1-10.1 の残余表に 1 行、履歴書換の可否は D-P0-03-1 と同じ判断に委ねる。
- 根拠: `tests/fixtures/benchmark/real_sample.jsonl`（61,209 B、50 行、`type` = session 1 / activity 35 / interaction 14、`ollama_model: qwen3.5:9b` — キー構造と件数のみ確認、本文未読）; 唯一の consumer `tests/benchmark_distill.py:300`（`--dataset` 既定 `real_sample`、`:5`「Not a pytest test」）; `CLAUDE.md:98`（episode log は平文 untrusted、Claude Code の直読み禁止）; data repo 側は `sync-research-data.sh:81` で `logs/` 全除外; 同梱 hooks は `.config/moltbook/logs` パスしか見ず（`integrations/claude-code/hooks/*.sh:15,33,60`）、`weekly-pipeline.sh:359` の `Read(/$PROJECT_ROOT/**)` で無人セッションからも可読
- 完了条件: まずオーナーが Mac で中身を確認する（本文未読のまま、キー構造と `real_sample` の名から本番 episode と推定）; `git ls-files | grep -c real_sample` = 0; 不在テスト（key 検査 + 既定 path の assert）緑、`docs/evidence/` の 4 本で偽陽性 0; P1-04.7（consumer 無し fixture の退役、旧 P1-08 の行を吸収）の `real_sample` 行がこの項目を参照
- 規模・整合: S / repair（absence の維持、能力は減る）   出典: R1-SEC-03（TQ-26 の `real_sample` 退役行 — P1-04.7 に吸収 — と同じ現物）   順序: v2.13.0 の tag（11-14 の決定の後、11-20 まで）より前に merge（P0-06.6 段 (5) の停止基準が `git ls-files | grep -c real_sample` = 0 とこの不在テストの緑を読む。Zenodo 版は tag 時点の tree の zip で不変）

##### P0-03.14 機械可読のライセンス宣言と README / llms.txt の「no restriction」散文を carve-out と整合させる
- 何を: data repo `README.md:29` / `README.ja.md:29` / `llms.txt:98,101,133` の「no restriction・一切の制限なく・unrestricted」5 箇所を「owner-authored content は CC0。comment reports は第三者本文を含み CC0 の対象外（NOTICE）」の 2 文に揃える。`.zenodo.json` に `notes`（carve-out の 1 段落）を足して次 deposit の record 説明に出す。`graph.jsonld` の Dataset ノード（`:39` `license: …/zero/1.0/`）に `usageInfo`（NOTICE の URL）と `conditionsOfAccess` を足す。HF card の License 節（YAML `license: cc0-1.0` → mlcroissant のメタデータ）は `patterns.jsonl` 単体の宣言なので D-P0-03-3 の結論に従う — `cc0-1.0` を維持するなら License 節に測定値（.9）を併記、伏せ字しないなら `license: other` + `license_name` を検討。P3-05.1 の週次 scan に禁則語 `no restriction|一切の制限|unrestricted` を足す。
- 根拠: HF card 冒頭 YAML `license: cc0-1.0`（hub タグ `license:cc0-1.0` `library:mlcroissant`）; `.zenodo.json:12` `"license": "cc0-1.0"`（deposit 全体 = Context を含む tree）; `graph.jsonld:39`; data `CITATION.cff:7` `license: CC0-1.0`; 散文: `README.md:29`「freely available, with no restriction … including reuse in model training」、`README.ja.md:29`「一切の制限なく自由に利用できる（モデル学習への利用を含む）」、`llms.txt:98`「both unrestricted under CC0」/ `:101`「with no restriction」/ `:133`「There are no restrictions」— いずれも「daily comment reports」を主語に含む; `NOTICE:35-50` の carve-out は散文の末尾にしか無く、P3-05.1 の整合パスは技術的 stale 文言だけでライセンス文言は対象外
- 完了条件: 5 箇所の grep（`no restriction|一切の制限|unrestricted`）が 0; `.zenodo.json` に `notes`; `graph.jsonld` の Dataset ノードに 2 属性; HF card の License 節が D-P0-03-3 の結論と一致（本セッションから HF は未検証 — オーナーが目視）。既存テストは不変。
- 規模・整合: S / repair   出典: R2-ETH-05   依存: P3-05.1、P0-03.9。HF card の License 節だけは D-P0-03-3（11-21）の後に揃える（現行の形で書き、決定が入ったら更新）

##### P0-03.16 公開 data repo への無人 force push をやめ、remote 側の commit を翌朝上書きしない
- 何を: (a) `sync-research-data.sh` の push を force なしの `git push` にし、non-fast-forward は `ERROR:` 行 + 非 0（P2-04.2 の sync 失敗と同じ行・同じ読み手）。stale lease 対策だった直前の `git fetch` は、push 前の `git merge --ff-only origin/main` の確認（失敗したら `ERROR:` で止める）に置き換える。(b) bare remote に sync の外で commit を 1 つ足した状態で sync を走らせるテスト 1 本。(c) 公開 data repo への書き換え・除去・手での編集（`:71-80` の governance ファイルを含む）は sync を行う checkout（`:5` の `DATA_REPO`）でだけ行い、その間は sync job を unload する — DATACARD の Maintenance（10-16 まで）・D-P0-03-1 の B の実行条件・P3-05.19 の手順に 1 行。(d) `:23-26` と `:124-125` のコメントを実態に合わせる。
- 根拠: `scripts/sync-research-data.sh:123-130`（`git fetch origin` の直後に期待値を省略した `git push --force-with-lease`。fetch で remote-tracking ref が remote と同じになるので lease は常に一致し実質 `--force`、失敗しても `WARNING:` だけ。scratchpad の使い捨て bare repo で、別 clone から push した commit が fetch + force-with-lease の後に remote から消えることを再現）/ `:71-80`（受け側が保守する governance ファイル `.gitignore`〜`DATACARD.md` の rsync 除外）/ 対照 `scripts/backup-runtime.sh:188`（force なしの `git push`、失敗で `ERROR:` + exit 1）。上書きが実際に起きたことがあるかは data repo が depth 1 なので未確認（推測）
- 完了条件: `scripts/sync-research-data.sh` に `--force` / `--force-with-lease` が 0 件; テスト「remote にしか無い commit が sync の後も残り、rc≠0 と `ERROR:` 行が出る」が緑（rsync を要するので macOS セルで passed、ubuntu では skip — P1-08.2 の期待集合に登録）; DATACARD の Maintenance に (c) の 1 行; `:23-26` / `:124-125` のコメントが push 段の実態と一致。既存テストは不変。
- 規模・整合: S / repair（能力を増やさず、無人経路の権限を狭める）   出典: R4-ONEWAY-01 R4-COLD Fix-11 DE-11（旧 P2-05.6）   順序: `sync-research-data.sh` は .2 → .3 → 本項目（push 段だけ）→ P2-05.1。(c) の DATACARD 1 行は 10-17 の週（10-16 まで）、(a)(b)(d) は 10-24 の週。ERROR 行の書式は P2-04.2（着手 2027-02-06）、テストの harness は P1-08.3（着手 12-19）で、どちらも本項目より後なので現行の形（`backup-runtime.sh:188` と同型の `ERROR:` + 非 0、現行の `tests/test_sync_research_data_shell.py` 型）で書き、依存先が入ったら更新


**依存**
- P1-08（`test_sync_research_data_shell.py` は実 rsync を要し container では走らない → macOS セル / P1-08.2 の期待集合。text-level テストは ubuntu。P1-08 は着手 12-19 で本束より後なので、.3 / .4 / .6 / .16 のテストは現行の `tests/test_sync_research_data_shell.py` の形で書き、P1-08.1 / .2 / .3 が入ったら載せ替える）
- P3-05.1（10-17 の週の先行項目 — .14 の禁則語を足す週次 scan）
- 順序: P3-05（11-21 は本束の再入場と同じ週）— D-P0-03-3 は D-P3-05-2 と同じ 11-21 の回。.9 / .10 / .14 の帰属・carve-out 文言は 10-24 の週に現行の NOTICE / DATACARD へ入れ、P3-05.14 の takedown 節（11-21）が入ったら合わせる
- → 参照元: P0-06（データ版 DOI は D-P0-03-1 / -3 / D-P3-05-2 の後、最初の新版は 12-05 のゲートの後。P0-06.6 段 (5) の停止基準が .11 の不在テストを読む — v2.13.0 の tag より前）、P1-10（threat model・鍵の所在: P1-10.9 の所在表が .2 の `cloud.env` を、P1-10.1 の残余表が .11 の 1 行を、P1-10.12 の Step 6d 点検範囲が .5 / .6 を引く。`config/secret-patterns.txt` の正本は .6）、P1-04.7（consumer 無し script / fixture の退役 — .11 の `real_sample` 行）、P3-04.1（ADR-0020 の `## Amendment` に .5 の 1 段落を寄せる）、P1-11（SA-15「兄弟 cloud の README に『鍵は MOLTBOOK_HOME の外へ』」の移送先。この束は `*.env` の除外とテストまで）、P2-05（promote 層の機微点検。P2-05.1 のスキャンは .6 が正本、allowlist の 2 本化は .3 の後、push 段は .16 の後）、P2-04（sync 失敗を watchdog が拾う面。P2-04.2 の ERROR 行は .16 と同じ書式、.9 の一致件数行は P2-04.14）、P2-03（harness hook が .6 の regex ファイルを読む）、P3-05.14 / .19（NOTICE の takedown 節・抑止リストが .9 の carve-out と .10 の post id 解決を使い、.19 の実行手順は .16 (c) の規約を引く）、P2-04.23（`host_check` が .3 の rsync の版を読む）、P0-06.4（sync commit 本文の要約行 — .3 の版の行が隣に並ぶ）


#### P0-04 蒸留の取りこぼしと非原子書き込みの修理（06:00 JST セッション）
- 狙い: 代謝ループの入口（episode → pattern）で 1 日 4 セッション中 1 本（06:00 JST = 21Z）が構造的に一度も蒸留されていない。ADR-0080 の「ループが自己調節して回る」以前にループが閉じておらず、公開データセット knowledge.json と研究層の縦断記録が 1/4 偏る。同じ経路の冪等性・再試行・埋め込み backfill・原子書き込みを一度に直す（能力は増やさない）。
- 期限・順序: 着手 10-24 の土曜ゲート（§4.0。11-21 に決定 2 件）。期限 2026-11（.2 / .6 は 11-21 の決定の後の週）。週の言い方は §0（「X の週」= 土曜 X の前の月〜金、「着手 X」= X のゲートで方針を確かめ X の後の平日に PR）。.1（台帳 + 窓）は着手 10-24（10-26〜30 の平日に PR。P0-03 の残りは 10-24 の週で先に入る）。取りこぼしの実数は .2 が記録する（comment-report の 21〜22Z 見出しの数か `instrument_census.py` のセッション台帳。episode の直読みはしない）— D-P0-04-1 の材料なので 11-21 の週までに。.2（backfill、やる場合）は D-P0-04-1（11-21 の土曜ゲート、D-P0-04-2 と同じ回）の後の週。.5（憲法の検証失敗）と .7（`axiom_files[0]`）は 10-31 の週（10-26〜30。10-31 の憲法改正ゲート（P0-07）より前）。.3 / .4 は 10 月中（10-31 の週まで）。.6 は D-P0-04-2（11-21）の後の週（11-23〜27）、ただし save 順序のテストは決定を待たず 10 月中に入れてよい。この束の決定: D-P0-04-1 / -2（11-21）。
- 束の完了条件:
  - knowledge.json の `provenance.source_episode_ids` の UTC 時刻分布で 21–22Z 帯が修理後の週に 0 でない（週次 census 1 行）
  - 同じ日ファイルで `distill` を 2 回走らせた 2 回目が ADD 0 / UPDATE 0 になるテストが green
  - `write_run_marker`・staged `.md` / `.meta.json`・`reasoning.md` の書き込みが `write_restricted` 経由（`grep -n '\.write_text(' core/_io.py cli/staging.py cli/runtime.py` の該当が `core/_io.py` の `write_text_atomic` 本体 1 箇所のみ。実対象は `_io.py:446` `write_run_marker`、`staging.py:242,264`、`runtime.py:453`。`:134` の docstring と `:417` の定義名は `\.write_text(` に当たらない）
  - `tests/test_constitution.py` に検証失敗ケースと複数ファイル拒否ケースがある

##### P0-04.1 蒸留窓を暦日から「処理済み台帳」に替え、故障分を翌 run で拾う
- 何を: `read_range(days=1)` は当日 UTC ファイルだけを読み、distill は 18:30Z（03:30 JST）に 1 回走るので、21Z 以降に追記される 06:00 JST セッション分は翌日の実行が翌 UTC ファイルしか読まず永久に未読。処理済み episode id の台帳（append-only JSONL、ADR-0075 型、成功した episode のみ記録）を distill に持たせ、窓を「直近 N 日（N ≥ 2）のファイル − 台帳にある id」にする。N=1 では直らない第 2 経路がある: 遅延起動（distill は blocking lock で待つ `cli/memory_cmds.py:59-66`、submolt-scan の run lock `cli/schedule.py:356-363,666-680`、launchd の取りこぼしは wake 後に合算実行）で 03:30 開始の run が 00:00Z を越えると、台帳があっても翌 UTC ファイルしか読まない。故障（`llm_none` 等）で abstain した episode は台帳に書かず翌 run で再処理。時計 seam は `read_range(days, *, now: datetime | None = None)`（`core/episode_log.py:70` の `datetime.now(timezone.utc)` を引数化。distill 側 `distill.py:150` は run 開始時刻を 1 回取って渡す = 遅延起動の修理そのもの）。台帳のファイル名は `$MOLTBOOK_HOME/logs/<名前>.jsonl`（名前は実装 PR で固定）で固定し、`scripts/_census_registry.py` に Entry を 1 行足す（P1-04.14 の census で未登録にならないため）。
- 根拠: `src/contemplative_agent/core/episode_log.py:59-78`（`now - i 日` の UTC 日付ファイル）、`core/distill.py:150`（`read_range(days=days)`）、`:141-160`（処理済みの参照なし）、`:674-681`「their patterns are lost for this run」/ `config/launchd/com.moltbook.distill.plist:13-15,28-33`（`--days 1`、`{{DISTILL_HOUR}}`:30 ローカル、既定 3 = `cli/schedule.py:614`）/ data repo knowledge.json `source_episode_ids` 12,859 件の UTC 時刻: 03–04Z 5,011 / 09–10Z 3,986 / 15–16Z 3,833 / 21–22Z 0（2026-09 以降も 1,156 / 1,150 / 1,124 / 0）
- 完了条件: UTC 日付をまたぐ 1 本の episode が翌 run で蒸留されるテスト、遅延起動で UTC 日を跨いだ run（開始 23:xxZ → 読み 00:xxZ）が前日ファイルも読むテスト、同じ日ファイル 2 回で 2 回目 ADD 0 / UPDATE 0 のテスト、flapping backend で落ちた episode が翌 run で処理されるテスト（`tests/test_distill.py` は現在 15 件すべて `days=1` の同日レコード）。`_census_registry.py` に台帳の Entry がある。書き換える既存テスト: `tests/test_episode_log.py::TestReadRange::test_days_1_reads_today_only` / `::test_days_2_includes_yesterday`（実時刻の `_date_str` を `now=` 注入に揃える — 挙動は不変）; `tests/test_distill.py` の `days=1` 15 件は台帳の tmp fixture を足すだけで assert は不変（推測）。
- 規模・整合: M / repair   出典: CP-01 CP-02 CP-03   順序: `_census_registry.py` は Entry 1 行の差分（順序不問）

##### P0-04.2 06:00 JST 分の欠損を記録し、backfill の要否を決める
- 何を: 2026-03 以降の 21Z episode（推定 3,000〜4,000 本）は一度も蒸留されていない。取りこぼしの実数を、comment-report の 21〜22Z 見出しの数（下の根拠と同じ経路）か `instrument_census.py` のセッション台帳から数えて記録する（episode の直読みはしない — `CLAUDE.md:98`）。D-P0-04-1 で backfill の範囲を決め、やる場合は `--file` の日ファイル丸ごと再処理（重複を生む）でなく台帳 + ts フィルタで、別 run 名（snapshot `command`）と DATACARD / 装置境界表（P3-02）への日付つき記載を伴う。やる場合の手順: 実行直前に `knowledge.json` と `pattern-embeddings.sqlite` を `knowledge.backups/` に日付つきで退避し、sync job を止め、ts フィルタで再処理される episode 数の dry-run 件数を `gate_item` に書いてから打ち、結果を確かめてから sync を戻す（dedup は 0.80〜0.90 で旧行を soft-invalidate し新行を ADD するので、翌 05:30 の sync と HF upload の後は戻せない）。やらない場合も欠損期間を同じ場所に記す。
- 根拠: data repo `reports/comment-reports/` の見出し行で 21–22Z のコメントは 2026-09 に 524 / 2,082 件（元項目の値、セッションは発話している）/ knowledge.json `distilled` の UTC 時刻は 18Z に 9,956 / 10,985 行（蒸留は毎日 1 回）/ `docs/CONFIGURATION.md:34` の `--days 3` 例は冪等キーなしでは churn（`core/pattern_dedup.py:42-43,86-97`: 0.80–0.90 は旧行 soft-invalidate + 新行 ADD）
- 完了条件: 取りこぼしの実数（経路名つき）が D-P0-04-1 の材料欄（decisions.md）にある。DATACARD（または P3-02 の境界表）に「2026-03-07〜修理日の 06:00 JST セッションは未蒸留」の 1 段落。backfill する場合は退避 2 ファイルと dry-run 件数の `gate_item` 行が実行より前の時刻で残り、4 スロットの時刻分布が揃う。
- 規模・整合: S〜L / repair（S = 記録のみ、L = 全期間 backfill で数十 GPU 時間）   出典: CP-01 CP-02

##### P0-04.3 埋め込み障害で保存された「ベクトルなし行」を自動 backfill する
- 何を: `_embed_patterns` 失敗時は全行 None で保存され、dedup / views / clustering から永久に外れる（修理は手動 script のみ）。distill 末尾（または weekly chain）で `missing_embedding > 0` なら `restore-embed-knowledge.py` の `backfill()` を再利用して自動実行し、失敗は理由コードで残す。
- 根拠: `core/distill.py:705-721`（all-None 退化）/ `core/pattern_dedup.py:65-69`（None は常に ADD）/ `core/views.py:303,333-336`、`core/clustering.py:109-113`（除外 / singleton）/ `scripts/restore-embed-knowledge.py:13-14`（手動）、`scripts/state_invariant_check.py:185-194`（週次 FAIL を出すだけ）
- 完了条件: 埋め込み障害 → 復旧の 2 run で行がベクトルを持つテスト。`missing_embedding` の週次 FAIL が修理後 0。
- 規模・整合: S / repair   出典: CP-04

##### P0-04.4 マーカー・staging・reasoning の書き込みを `write_restricted` に統一する
- 何を: `write_run_marker`・staged `.md` / `.meta.json`・`reasoning.md` は `Path.write_text` で、`write_restricted`（mkstemp + `os.replace`）の原子性契約から漏れている。3 箇所を `write_restricted` 経由にし、途中中断テストを足す。半端な `.last_insight` の挙動は元項目の「拒否」ではなく全件再クラスタ（`_filter_since` は不正な timestamp で pool 全体を返す）なので、修理の優先度は上がる。
- 根拠: `core/_io.py:443-446`（`write_text`）vs `:121-140`（`write_restricted`）/ `cli/staging.py:242,264`、`cli/runtime.py:453` / `core/insight.py:990-998`（マーカー不在のみ拒否）+ `core/knowledge_store.py:252-277`（「Returns all on bad timestamp」）/ `scripts/weekly-pipeline.sh:683-695`（`fromisoformat` 失敗を `false` に畳む）
- 完了条件: 3 箇所に `.write_text(` が無い（束の完了条件の grep）、`write_run_marker` の中断テスト 1 件、壊れたマーカーで `extract_insight` が拒否する（全件再クラスタしない）テスト 1 件。
- 規模・整合: S / repair   出典: CP-06

##### P0-04.5 `amend_constitution` の検証失敗を理由つきエラーにする
- 何を: 検証失敗時に生成テキストをそのまま返し、CLI が「結果」として印字する（identity 側は理由つきエラー文字列）。identity と同じ理由コード付きの str を返し、`audit.jsonl` に `validation_failed` を残す。10-31 の改正ゲート前に入れる。
- 根拠: `core/constitution.py:163-165`（`return amended_text`）vs `core/distill.py:328-335`（identity:「failed forbidden-pattern validation; discarded.」）/ `cli/memory_cmds.py:102-104`（str をそのまま print）/ `tests/test_constitution.py` に `validate` 0 件
- 完了条件: 検証失敗で承認ループに入らず理由が印字されるテスト 1 件（`tests/test_constitution.py`）+ `audit.jsonl` に `validation_failed` 行が残るテスト 1 本。書き換える既存テスト: `tests/test_constitution.py::TestAmendConstitution::test_forbidden_pattern_returns_string`（`:204-218`、`assert "api_key" in result` = 生成テキストがそのまま返る現行挙動の pin → 理由コードの assert に）。
- 規模・整合: S / repair   出典: CP-07

##### P0-04.6 knowledge.json の保存前バックアップを持つか、案内文を直す
- 何を: `KnowledgeStore` は「Restore from a `.bak`」と案内するが `.bak` を書くコードは src に無く（ADR-0035 で退役）、off-site backup は月曜 10:00 の週 1 回。D-P0-04-2 で (a) `save()` 直前に直近 3 世代を `knowledge.backups/` に残す（sync 除外は既にある）か (b) 案内文を「月曜 backup から restore」に直すかを選び、runbook と同じ PR で更新。(a) の 3 世代の回転は `save()` が書いた名前規則（例 `knowledge.json.save-<ts>`）のファイルだけを数え、P0-03.1 が同じ `knowledge.backups/` に移す `knowledge.json.bak-dup-cleanup-20260718`（07-18 の dedup 前の store、768 次元入り）は回転の対象外にする。どちらを選んでも、`MemoryStore.save()` が knowledge の保存失敗時に `agents.json` と comment ledger を書いてから再 raise する順序をテストで固定する（(a) の世代回転は `KnowledgeStore.save()` の中で失敗しうる）。
- 根拠: `core/knowledge_store.py:338,417,428`（`.bak` 案内）、src に `.bak` の書き手なし（grep）/ `scripts/sync-research-data.sh:90`（`knowledge.backups/` を除外）/ `cli/schedule.py:647-656`（backup 既定 月曜 10:00）/ `core/_io.py:126-127`（`fsync` なし — 電源断は契約外）/ `core/memory.py:202-226`（docstring が「knowledge error は他 2 つを書いてから re-raise」と約束、`tests/test_memory.py` に該当テスト無し）
- 完了条件: 案内文と実在する復元手段が一致（(a) なら `knowledge.backups/` に 3 世代が残るテストと、`knowledge.json.bak-dup-cleanup-20260718` を置いた状態で回転しても消えないテスト）。`tests/test_memory.py` に save 順序のテスト（knowledge の `save()` を失敗させ、`agents.json` と comment ledger が書かれた後に例外が上がる）が 1 本。既存テストは不変。
- 規模・整合: S / repair   出典: CP-08 CP-32（旧 P1-08.20 (h)）   順序: save 順序のテストは D-P0-04-2 を待たず 10 月中、(a) / (b) の実装は 11-21 の後

##### P0-04.7 憲法改正が `axiom_files[0]` だけを書く契約を固定する
- 何を: `amend_constitution` は `axiom_files[0]` のみ改正し、loader は `*.md` を全部連結して注入する。ファイルが 2 本以上なら改正を拒否して理由を出す（1 行）か、連結した 1 本に書き戻すかを docstring とテストに固定し、runbook の「verify single-file state（mandatory until that defect is fixed）」を不要にする。T-ADOPT-OVERWRITE-TARGETS（`-2.md` 事故）の再発面。
- 根拠: `core/constitution.py:136`（`axioms_path = axiom_files[0]`）/ `core/domain.py:329-332`（全 `*.md` 連結）/ `docs/runbooks/constitution-amendment.md:36-45`（既知欠陥と手動検証）/ `docs/adr/0090:278-288`（2026-08-09 の `-2.md` 事故の経緯）/ data repo `constitution/` は現在 1 ファイル
- 完了条件: 複数ファイルで `amend_constitution` が理由つき str を返すテスト 1 件、runbook step 5 の「mandatory until fixed」が消える。
- 規模・整合: S / repair   出典: CP-28 PF-36


**依存**
- ADR-0075（append-only JSONL の型）、ADR-0074（マーカー契約）、ADR-0035（`.bak` 退役）、ADR-0090（`-2.md` 事故）
- P0-03（data repo の sync 除外: `knowledge.backups/` は既に除外。.6 (a) の回転の対象外にする bak は P0-03.1 が移す）、P1-04.14（census の Entry 登録 — .1 の台帳）
- P1-08（テストの床。着手 12-19 で本束より後なので、テストは現行の `tests/` の形で書き、P1-08 の床が入ったら更新）
- → 参照元: P0-07（.5 / .7 を 10-31 の改正ゲート前に要する）、P3-02（装置境界表に .2 の欠損期間を記録）、P3-05（DATACARD / DOI 版に .2 の段落）


#### P0-05 初回体験（Quick Start）の修理と preflight
- 狙い: README の Quick Start（init → register → run / dialogue）を第三者が打ったとき、Ollama 不在・env 無し・Moltbook 不達・非 TTY のどれでも「成功したように見えて何もしない」経路が残っている。北極星の最小形「README どおりに打てば 1 セッションが回る」（研究の再現入口）と ADR-0075（reason codes over silent fallback）の修理。能力は増やさない。
- 期限・順序: 着手 11-07 の土曜ゲート（§4.0）。期限は v2.13.0 の tag（11-14 の決定の後、11-20 まで）。v2.13.0 の 2 ゲート（11-07 に形を決める D-P0-05-1 / -2、11-14 の決定の後、11-20 までの tag 前に merge）。RFC-0046 後始末 3 の削除 PR（10-17）の後、P0-06 と同じ PR 列（v2.13.0 は日付拘束が無いので 10 月のゲートには載せない）。`4b85f22` で既定値は直ったが README と smoke が無いので、.9 の smoke を先に書き（赤）、.1〜.8 と .11 で緑にし、.10 の README 注記は v2.13.0 で外す。`cli/runtime.py` の順序: P0-02.2（`:173-208` 削除）→ 本束（.1 の preflight / .2 (a) / .8 の WARNING）→ P1-07.13（`:295-316`）。.1 は PR 3 本（A `doctor` → B canary → C `run` 起動時 ERROR、C は D-P0-05-1 = 11-07 の後）。shell テスト・macOS 依存は無い（smoke は in-process、CI の verify 行列は P1-08.1 の 2 セル）。
- 束の完了条件:
  - smoke テスト 1 本: tmp HOME + `responses` + stub decision / 生成 backend で `init → run --session 1` を env 無しで通し、engage 1 回を assert して緑
  - Ollama 停止下で `contemplative-agent doctor` が rc=1、`run` が timeout 0.1 s を注入した fixture で理由コード（`model_not_listed:` / `enforce_backend_null` / `circuit_open` のいずれか）つきで rc=1（壁時計の条件は置かない）、`dialogue` が rc≠0 で `logs/episodes/` に行を増やさない — 各 1 テスト
  - `tests/test_cli.py` で `register` / `status` の stdout に `api_key` 値が無い、`run --approve < /dev/null` が rc=2
  - .9 の smoke 1 本 + 対ケースが緑（ファイル別の coverage 床は `--cov-fail-under` では書けないので置かない。TOTAL の床 94 は P1-08.7）、`cli/__init__.py` の dispatch で RuntimeError / FileNotFoundError / MoltbookClientError が 1 行 + rc=1
  - README「Run it on Moltbook」に Ollama 最小版の 1 段落と `docs/TROUBLESHOOTING.md`（P1-09.17）への 1 行リンク、Quick Start の install 2 経路（uv / venv+pip）が CI の `packaging` job（P0-06.3、3.13 の leg）で実行される

##### P0-05.1 起動 preflight（`doctor` / `init --check`）: Ollama・モデル・logprobs を 1 画面で判定し rc≠0
- 何を: `contemplative-agent doctor` を追加し、Ollama 到達（`/api/version`）・生成 / 埋め込みモデルの有無（`serving_environment()` の reason を再利用）・`MOLTBOOK_HOME` の配置・`credentials.json` の有無・Ollama 版を印字し、不備は原因と次の一手（`ollama pull gemma4:e4b` 等）を 1 行ずつ出して rc=1。既知の答えを持つ `NoulQuestion` 1 問（期待 yes）を decision backend に投げ `answered` でなければ `decision_canary_failed`（reason 併記）— Gemma 以外のモデルで全投稿 `no_option_observed` になる経路の canary。README の `init` 直後に置く。`run` 起動時も同じ検査関数を呼び、`serving_environment()` の reason に `model_not_listed:<生成モデル>` が含まれれば `ERROR:` を stderr に出す（P2-04.5 (2) を吸収。非 0 終了にするかは D-P0-05-1、.2(a) の WARNING はその既定。埋め込みモデルは WARNING に留めるかは実装時に判断）。`doctor` の Tier は `Tier.LLM_RUNTIME_ONLY`（`cli/registry.py:35`。Ollama に `/api/version` を打つので `NO_LLM` ではない）。PR は 3 本: PR-A（`doctor` 登録 + `responses` の接続拒否テスト + `--help`）→ PR-B（`NoulQuestion` canary、`decision_canary_failed`）→ PR-C（`run` 起動時の `model_not_listed:` ERROR、D-P0-05-1 = 11-07 の後）（`tests/test_cli.py::TestCommandRegistry` は件数を pin していないので `doctor` 追加で赤にならない）。
- 根拠: `cli/session_cmds.py:56-115`（`_do_init` はファイル複製のみ）; `core/llm/__init__.py:442-446`（Ollama 不達は `logger.info` で記録し reason `ollama_unreachable` を返すだけ）; `core/llm/__init__.py:468-520`（reason を返すだけ、呼び手は `cli/runtime.py:315,393` の記録のみ）; `core/llm/decision.py:544-561,598`（1 token 完全一致、外れると `no_option_observed`）、`adapters/moltbook/relevance_shadow.py:130`（投稿単位 skip、WARNING 無し）; `README.md:60`「any chat model」; `core/llm/__init__.py:509-512`（`model_not_listed:<tag>` を記録するだけ、`cli/*.py` に preflight 無し）
- 完了条件: 接続拒否を `responses` で再現した `doctor` が rc=1 と原因 1 行; canary テスト（stub が yes を返さない → WARNING）; `cli/` に `doctor` が登録され `--help` に出る; `model_not_listed:gemma4:e4b` のとき `run` が `ERROR:` を stderr に出すテスト 1 本（rc は D-P0-05-1）
- 規模・整合: M / repair（canary は instrument）   出典: CU-01 AR-18（DC-34 の版表示部分を含む）AR-37 LP-27（P2-04.5 (2) の `run` 起動時判定）（実行記録は R1-NEW / CU-01: Ollama 不達が INFO 1 行で rc=0）   順序: PR-A → PR-B → PR-C; `cli/runtime.py` は P0-02.2 の後・P1-11.5 → P1-07.13 の前

##### P0-05.2 「静かな無行動セッション」3 経路を起動時に止める（backend 不在・Moltbook 不達・非 TTY approve）
- 何を: (a) `run_session` 開始時に `serving_environment()` の reason が `ok` 以外なら WARNING（`model_not_listed` は `ollama pull` を併記）、`enforce_backend_null` を session 内 1 回の WARNING に昇格（`CONFIGURATION_REASONS` に 1 つ足すだけ）、`_log_session_end` に fail-closed 件数と理由内訳を足す。(b) setup 段（`_fetch_home_data`）の transport エラーは N 回再試行後 rc=1 で中断し理由を 1 行。(c) `--approve` かつ `not sys.stdin.isatty()` を起動時に検出し「no TTY: use --guarded/--auto or run interactively」で rc=2。backend 不在で session 自体を止めるかは D-P0-05-1。
- 根拠: `adapters/moltbook/agent.py:776-777,790-791`（setup / cycle の例外を握って継続）、`:438-442`（EOF → False、ログ無し）、`:892-912`（session end に fail-closed 計数無し）; `feed_manager.py:262,286,530-536`（breaker open は INFO、WARNING は `CONFIGURATION_REASONS` のみ）、`relevance_shadow.py:124`（`enforce_backend_null` を含まない）; `adapters/moltbook/agent.py:277`（submolt ごとに `_confirm_side_effect` を呼ぶ。非 TTY では EOF の拒否が submolt の数だけ続く）; ADR-0113 ja:96 Review-when（検知が翌週の人間の読み）
- 完了条件: テスト 3 件 — timeout を 0.1 s に注入した fixture（sentinel `127.0.0.1:1` は即時拒否なので「2 分以内」は何も検査せず、応答しない host を模すと `core/llm/__init__.py:959` の `timeout=(30, 1200)` 等で壁時計が数十秒〜20 分になる）で `run --session 60` の理由コードが `model_not_listed:` / `enforce_backend_null` / `circuit_open` のいずれかで rc=1、経過時間の assert は置かない; `run --approve < /dev/null` が rc=2; session end 行に `fail_closed_count` と `fail_closed_reasons`。`docs/CONFIGURATION.md` に各 1 行
- 規模・整合: M / repair   出典: AR-13 CU-10 CU-09（実行記録は R1-NEW / CU-09: 非 TTY で 8 回の `Proceed?` が流れ rc=0）

##### P0-05.3 `register` / `status` が api_key を stdout に印字する — マスクする
- 何を: `cli/agent_cmds.py:36` の `print(f"Registration result: {result}")` を name / claim URL / `credentials.json` の保存先 / `_mask_key(api_key)` だけにし、`:45` の `status` は許可キーの投影に限る。`737133e`（2026-10-08）が「見送り」と明記した件で、v2.13.0 で README 手順を初めて他者が打つ想定なので今が直し時。
- 根拠: `cli/agent_cmds.py:36,45`; `adapters/moltbook/auth.py:19`（`_mask_key` は保存側にある）、`:101-105`（応答の `api_key` を保存）; `git log 737133e`「見送り: cli/agent_cmds.py:36 が登録応答（api_key を含む）を stdout にそのまま表示する」
- 完了条件: P1-10.10 の sentinel 鍵 fixture（1 つの sentinel 鍵で prompt / `_sanitize_output` 後出力 / JSONL / `.log` / `register` `status` の stdout の 5 面を回す）を共有し、その stdout 面（capsys）で鍵全文が含まれない; CHANGELOG Unreleased に 1 行
- 規模・整合: S / repair   出典: CU-04 SA-06

##### P0-05.4 典型失敗 3 種（鍵なし・通信失敗・設定ファイルなし）を traceback でなく 1 行 + rc=1 で終える
- 何を: `cli/__init__.py` の dispatch（`main()`、例外ハンドラ無し）で `RuntimeError` / `FileNotFoundError` / `MoltbookClientError` / `ValueError` を捕捉し、stderr に 1 行（`-v` のときだけ traceback）で rc=1。メッセージ自体（「Run 'contemplative-agent register --name NAME' first.」等）は概ね良く traceback に埋もれているだけだが、「No API key found」は `register` の 1 経路しか案内しないので、`register` / `~/.config/moltbook/credentials.json` の `{"api_key": …}` / `MOLTBOOK_API_KEY` の 3 経路を 1 行に併記する（`README.md:94` の読者 = 既に鍵を持つ人）。同じ PR で `run --help` の `--session` 説明に範囲 1..1440 を足す（エラー文 `--session must be between 1 and 1440 minutes` と同じ数字）。
- 根拠: `cli/__init__.py:53-144`（`try` 無し）; `adapters/moltbook/agent.py:289-293`; `adapters/moltbook/client.py:496-510`（`MoltbookClientError`）; `core/domain.py:139-141`; `adapters/moltbook/client.py:510`（`raise MoltbookClientError(…) from exc` が urllib3 / requests の例外鎖ごと `main` まで上がる）; `agent.py:291-293`（`register` のみ案内）、`README.md:94`（3 経路）
- 完了条件: `tests/test_cli.py` に 3 ケース、stdout / stderr に `Traceback` を含まず rc=1; 鍵の 3 経路が 1 行に併記され、`--session` の範囲が help に出る
- 規模・整合: S / repair   出典: CU-03（実行記録は R1-NEW / CU-03: `register` の通信失敗が urllib3 の多段 traceback で終わる）

##### P0-05.5 `dialogue` が Ollama 不在でも rc=0 で "(no reply)" をエピソードに記録する — 失敗を失敗にする
- 何を: `adapters/dialogue/peer.py` で `generate_fn` が None を返した turn は `replies_generated` に数えず episode にも書かず、`run_peer_loop` を抜けて rc=2（`session_cmds.py:489-496` の truncation ガードが初めて発火する）。`tests/test_dialogue_peer.py:200` の「(no reply) を成功として固定」を書き換える。README「Try it without an account」の最初の体験なので優先。
- 根拠: `adapters/dialogue/peer.py:192-196`（None → "(no reply)" → `replies_generated += 1` → `_record_turn`）; `cli/session_cmds.py:489-496`; `tests/test_dialogue_peer.py:198-200`; `README.md:69-84`
- 完了条件: Ollama 停止下の `dialogue` が rc≠0 と原因 1 行で終わり `logs/episodes/` に行が増えないテスト; 旧テストが「失敗は失敗」に置換
- 規模・整合: S / repair   出典: CU-06

##### P0-05.6 `init` の次手案内と `MOLTBOOK_HOME` の `~` / 相対パス解決
- 何を: `_do_init` の末尾に次の 3 行（`ollama pull …`、`register --name`、`run --session 60`、アカウント無しなら `dialogue`）を印字。`adapters/moltbook/config.py:24` で `Path(...).expanduser().resolve()` し、相対パスは WARNING（cwd = repo 直下だと作業木の中に home が生まれ、episode log が公開 repo に入る経路）。初期化済み home に `init --template stoic` を打つと `Identity file already exists …` 7 行で rc=0 のまま、由来は `identity.md` にも残らないので、WARNING 1 行（「この home は初期化済み。別テンプレートは別の `MOLTBOOK_HOME` に」）を次手案内と同じ PR で足す。
- 根拠: `src/contemplative_agent/adapters/moltbook/config.py:24`（`MOLTBOOK_DATA_DIR = Path(os.environ.get("MOLTBOOK_HOME", …))`、`expanduser` / `resolve` 無し）; `cli/session_cmds.py:56-115`（`_do_init` は複製のみで次手の案内を印字しない）; 実行記録（出典欄）: `init` の出力は Created / Copied 7 行のみ、`MOLTBOOK_HOME='~/tilde-home' init` が cwd に `./~/tilde-home` を作る、既存 home に別テンプレート → 7 行 rc=0 で `identity.md` に frontmatter 無し
- 完了条件: `tests/test_cli_session.py` の `_do_init` テストに stdout 末尾の次手 assert; `~` と相対の 2 ケース; 既存 home + 別テンプレートの WARNING テスト
- 規模・整合: S / repair   出典: CU-02 CU-33（実行記録は R1-NEW / CU-33）

##### P0-05.7 `init` が複製する `prompts/` は既定 home では読まれない — 文書と実装を一致させる
- 何を: `core/domain.py:219-223` は `MOLTBOOK_HOME` env が無いと None（packaged を読む）だが、`init` は `~/.config/moltbook/prompts/` へ複製し、CONFIGURATION は「home copies are the source of truth」と書く。本番 snapshot 100/100 が `prompts_dir: null` = 本番は packaged を読んでいるので、解決を既定 home に揃えると本番が 3 月の stale な複製を黙って読み始める。推奨は `init` の prompts 複製をやめ文書を直す（D-P0-05-2）。どちらでも env 未設定ケースのテストを足す。`MOLTBOOK_HOME` 明示の既存 home に残る旧複製は CONFIGURATION の 1 行「`prompts/` のファイルを消せば packaged に戻る」（`CONFIGURATION.md:329` の趣旨）で代替し、drift 警告や `init --refresh-prompts` は足さない（P1-14 の drift 警告項目は落とした。D-P0-05-2 の推奨 B を前提（決定前））。
- 根拠: `cli/session_cmds.py:111-115`; `core/domain.py:219-223`; `docs/CONFIGURATION.md:300,329`; data repo `grep -l '"prompts_dir": null' snapshots/*/manifest.json | wc -l` = 100
- 完了条件: 文書と実装が一致（CONFIGURATION の「source of truth」の文が実装と同じ条件を書く）; `tests/` に env-unset の読み込みテスト
- 規模・整合: S / repair   出典: CU-14

##### P0-05.8 plist の `DECISION_MODEL` literal を外し、exclusive（毎 post 2 回のモデル入替）を起動時に警告する
- 何を: `config/launchd/com.moltbook.agent.plist:32-33` の `DECISION_MODEL=gemma4:e4b` を外す（既定は「`OLLAMA_MODEL` に追従」なので literal は再掲ではない）。`cli/runtime.py:251` で既定 Ollama 経路なのに `exclusive=True` になったら WARNING 1 行（両モデル名併記）。
- 根拠: `com.moltbook.agent.plist:32-33`（`OLLAMA_MODEL` キーは無い）; `cli/runtime.py:188-189,246-252`; `docs/CONFIGURATION.md:433`「the keys restate the defaults: removing them changes nothing」が `DECISION_MODEL` には当てはまらない（`:500` は unset = `OLLAMA_MODEL`）; `core/llm/decision.py:364-365,425-438`（前後で `keep_alive: 0` evict、約 7 秒）
- 完了条件: `tests/test_cli_schedule.py` で plist に `DECISION_MODEL` literal が無い; exclusive WARNING のテスト 1 件; `CONFIGURATION.md:433` の段落は P2-04.3 が所有 — 本項目は「`DECISION_MODEL` は再掲ではない（unset = `OLLAMA_MODEL`、`:500`）」の点を P2-04.3 の段落を参照する 1 行で書き、段落自体は書き換えない
- 規模・整合: S / repair   出典: LP-10 AR-17

##### P0-05.9 README Quick Start の end-to-end smoke と、env 無し既定配線のカバレッジ
- 何を: tmp HOME + `responses`（Moltbook）+ stub decision backend（`answered`、P(top) ≥ 0.3）+ stub 生成で `init → run --session 1` を env 無しで通し、engage 1 回（upvote か comment）を assert する smoke を 1 本（CLI 配線だけを見る、LLM 内容は不問）。`cli/runtime.py:218-239,288,321-327`（`_configure_llm_and_domain` 周辺 = `4b85f22` の既定）を直接固定する（ファイル別の coverage 床は `--cov-fail-under` が TOTAL にしか効かないので置かず、新 script も作らない。TOTAL の床 94 は P1-08.7）。
- 根拠: `tests/test_cli.py:9,29-60` は `main()` を in-process で呼ぶが `agent_cmds.Agent` を mock（21 箇所）— Agent 実体で `run` を通すテストは 0; `4b85f22` が足したのは `tests/test_decision_backend.py:596-618` の単体 3 件; `pytest_cov.log`: TOTAL 95%（12,437 stmts / miss 615）、`cli/runtime.py` 85%（miss 22）、`cli/memory_cmds.py` 74%
- 完了条件: smoke 1 本が env 無しで緑、`DECISION_ENFORCE=`（空）で fail-closed を assert する対ケース（coverage の数字は条件にしない。実測 `pytest_cov.log`: `cli/runtime.py` 84.5% / `memory_cmds.py` 74.3% は根拠の記録のみ）
- 規模・整合: M / repair   出典: TQ-34 TQ-25

##### P0-05.10 README / CONFIGURATION: fail-closed の見方、v2.12.0 アーカイブの注記、Ollama 最小版と「any chat model」の但し書き
- 何を: README「Run it on Moltbook」に (a) 症状 → 原因 → 確認ログ（feed が投稿に関与しないときの `logs/relevance-*.jsonl` の `enforce_reason` と session の WARNING 等）の表は `docs/TROUBLESHOOTING.md`（P1-09.17）に置き、README には Quick Start 末尾の 1 行リンクだけ、(b) v2.12.0 の Zenodo / SWH スナップショットは `DECISION_*` の設定が要る（v2.13.0 で解消）、(c) 「relevance gate は Gemma 系で検証済み、他モデルは `doctor` の canary を見る。Ollama ≥ <logprobs を返す最小版、著者環境 0.34.2>」、(d) 「`config/domain.json` を複製して `--domain-config` で渡す」の 1 段落（第三者の submolt / `repo_url`。D-P0-05-2 の推奨 B を前提（決定前）、plist に `--domain-config` を渡す引数は P1-14.6）、(e) `--guarded` / `--auto` はサブコマンドの前に置く旗なので `docs/CONFIGURATION.md:378` と同形の 1 例（実測 `run --guarded --session 1` → `unrecognized arguments` rc=2）を足す。CONFIGURATION の env 表にも最小版を 1 行。
- 根拠: `rfcs/0046-relevance-gate-score4-logprobs-shadow.md:241`; `README.md:58-96` に `fail-closed` / `DECISION_` が 0 件（grep）; `README.md:60`「any chat model you serve locally」; `core/llm/decision.py:8-9,66`（`top_logprobs` 読み、`logprobs_unavailable` は fail-closed 理由）; `docs/adr/0112-decision-backend-seam-and-shadow-skill-decision.md:53`（0.34.2 のみ、最小要件の記述無し）; `README.md:96`（`--guarded` の旗位置の例無し）、`cli/__init__.py:61-66`（`--domain-config`）、`core/domain.py:24-28`（`CONTEMPLATIVE_CONFIG_DIR`）
- 完了条件: README に TROUBLESHOOTING への 1 行リンク・最小版・`--domain-config` の段落・旗位置の例; v2.13.0 リリースで (b) を外す（CHANGELOG に対応行）
- 規模・整合: S / repair   出典: DC-33 DC-34

##### P0-05.11 README Quick Start の前提 `uv` を宣言し、venv+pip の代替行を完結させ、install 2 経路を docs-as-tests にする
- 何を: README EN/JA の前提行（`:60`）に `uv`（導入リンク）を足し、`:65` の `# or: pip install -e .` を完結した代替行 `python3 -m venv .venv && source .venv/bin/activate && pip install -e .` に置き換える（`uv venv` は既定で pip を入れないので、現行の `# or:` は uv venv の中では動かず、システム pip に入ると `externally-managed-environment` になる）。P0-06.3 の packaging smoke（または .9）に「README の Quick Start fenced block から install 行を抽出し、uv 経路 / venv+pip 経路の両方を新 venv で実行して `contemplative-agent --help` rc 0」を 1 ケース足す。
- 根拠: `README.md:60`（前提は Ollama / Python / 10 GB のみ、uv の語なし）、`:65`「`uv venv .venv && … uv pip install -e .   # or: pip install -e .`」、`README.ja.md:60,65`（同文）; 実測 2026-10-10（R1-NEW）: `uv venv` の `bin/` は `activate* python python3 python3.10` のみで `python -m pip` → `No module named pip`（本体 `.venv` に pip があるのは dev 依存 `pip-audit` 経由で README 経路では再現しない）; `.claude/verify.sh:55-57` も uv 不在を `brew install uv` で案内（macOS 前提）
- 完了条件: 両経路のテストが CI 緑; `README.md` / `README.ja.md` の install 行が同一で `uv` が前提行に現れる
- 規模・整合: S / repair   出典: R1-NEW-01


**依存**
- P0-02（RFC-0046 後始末 3 の削除 PR は 10-17 のゲートで go、merge はゲートの後。旧 gate の削除後に smoke を固定しないと二重に書き直す。`cli/runtime.py` は P0-02.2 の後）
- 順序: P0-06（v2.13.0、同じ 11-07 の着手で同じ PR 列。形は 11-07 の決定、tag は 11-14 の決定の後の 11-16〜20。.10 (b) の注記の着脱、CHANGELOG Unreleased、.11 の install 2 経路は P0-06.3 の `packaging` job に同居）
- 本束より後の週の項目（いずれも現行の形で書き、依存先が入ったら更新）: P1-10.10（.3 の sentinel 鍵 fixture。P1-10 は着手 11-14）、P1-09.17（`docs/TROUBLESHOOTING.md` — .10 (a) の症状表の正本。着手 2027-01-23）、P2-04.3（`CONFIGURATION.md:433` の段落の所有者 — .8 は現行の段落を参照。着手 2027-02-06）、P2-04.5（plist の curl 戻り値と ollama 絶対パスは残り、`run` 起動時の判定は .1）、P1-08（smoke の置き場 = CI の verify 2 セル、未モック LLM の扱い、`responses` の導入可否。TOTAL の coverage 床は P1-08.7。着手 12-19）、P1-07 / P1-15（Gemma 以外のモデルでの logprobs 読みの較正、canary の閾値。着手 2027-01-16 / 12-05）
- → 参照元: P1-11.5・P1-07.13（`cli/runtime.py` は本束の後、P1-11.5 → P1-07.13 の順）、P1-14.2 / P1-14.9（各 1〜数行、P0-05 か P0-06 の PR に同乗。P1-14 の home 解決 2 項目 — `domain.json` 複製・prompts drift 警告 — は D-P0-05-2 の推奨 B を前提（決定前）に落とした）、P1-14（初回体験の後に残る CLI UX）、P2-04（watchdog が「無行動セッション」を拾う面 — .2 の計数が材料）


#### P0-06 v2.13.0 リリース（Python 床・配布単位・版メタデータ・runbook）
- 狙い: 固定版として引用に耐える v2.13.0 を切る。宣言（`requires-python >= 3.10` / pip installable / Keep a Changelog）と実態（床は 3.11・clone + editable 専用・Unreleased 無し）のずれを閉じ、release 手順を repo 内に持つ。北極星（ADR-0080）では「止まる」前の最後の数版が研究層の引用対象になるので、版メタデータの正しさは研究層の再現性に直結する。
- 期限・順序: 着手 11-07 の土曜ゲート（§4.0。11-14 に再入場）。期限は v2.13.0 の tag = 11-14 のゲートの後の平日（11-16〜20）。RFC-0046 後始末 3（10-17 の Step 1c の D-P0-02-1 行の照合コマンドで go を記録 → 旧 gate 削除 PR の merge はゲートの後の別セッション → P0-02）の後。11-07 の土曜ゲートで D-P0-06-1（床）/ D-P0-06-2（配布単位）/ D-P0-06-3（互換性ポリシー）を決め、v2.13.0 の中身を決める 11-14 の 3 件（D-P1-08-1 = .6 段 4 と ADR-0109 追補の半分、D-P1-11-5 = kit の level と release notes の兄弟行、D-P3-05-1 = runbook の deposit 段）の後の平日（11-16〜20）に release PR を merge して tag を打つ（土曜ゲートは code を適用しない。v2.13.0 は日付拘束が無いので 10 月のゲートには載せない）。順序: D-P0-06-1 / -2 / -3 → .1 .2 .5 → .6 runbook（兄弟適合・依存の固定・外部リンクの確認は段 2 / 4 の中）→ .3 .4 .7 .10 .11 は runbook の段として → annotated tag。P0-03.11（本体 tree から `real_sample.jsonl` を除去）は tag より前（.6 段 (5) の停止基準）。データ版 DOI は v2.13.0 と同時には切らない（最初の新版は 11-21 の D-P0-03-1 / D-P0-03-3 / D-P3-05-2 の後、12-05 のゲートの後 — P3-05.12）。CI の床検査は .3 の `packaging` job の 1 leg で、verify の行列は P1-08.1 の {ubuntu/3.13, macos/3.13} 2 セル。ADR-0109 の追補は D-P0-06-2 A（11-07）と D-P1-08-1 B（11-14、P1-08.5 の ADR-0069 訂正を含む）を 1 本にして v2.13.0 の release PR で入れる（2 週続けて別の追補にしない）。この束の決定: D-P0-06-1 / -2 / -3（11-07）。
- 束の完了条件:
  - `git ls-remote --tags origin` に `v2.13.0^{}`（annotated）があり、`CHANGELOG.md` の先頭 2 見出しが `## Unreleased`（空）と `## v2.13.0 …`
  - CI job `packaging` の床 leg（Python 3.11 + `uv sync --resolution lowest-direct` + `pytest -q`、.3）が緑
  - `scripts/release_consistency_check.py` が exit 0（pyproject / CITATION.cff / codemeta.json / README×2 BibTeX / llms-full.txt の version・DOI が一致）
  - `docs/runbooks/release.md` が存在し、`docs/evidence/releases.md` に v2.13.0 の 1 行がある

##### P0-06.1 Python 床を実態に合わせ、床で CI を回す
- 何を: 床を 3.11 に上げる（推奨、D-P0-06-1）か `assert_never` を shim して 3.10 を守るかを決め、同 PR で `pyproject.toml:5` / classifiers（`:15-21`、現状 `Python :: 3` のみ）/ `[tool.ruff] target-version`（`:179` `py310`）/ `README.md` と `README.ja.md` の 17・60・130 行 / `CLAUDE.md:35`「Python 3.10+」/ sibling 2 repo の `requires-python` を同期する。床の検査は .3 の `packaging` job の床 leg を指す（別 job は作らない）。
- 根拠: `src/contemplative_agent/cli/__init__.py:15` `from typing import assert_never`（3.11 で追加）; `tests/test_dependency_floor.py:13` `import tomllib`（3.11+）; 実測 Python 3.10.20 で `pytest` → `ImportError: cannot import name 'assert_never'`（scratchpad `py310.log`）、3.11 / 3.12 は 4,761 passed; `.github/workflows/verify.yml:31` は `python-version: "3.13"` のみで床は誰も検査していない。
- 完了条件: `packaging` job の床 leg（.3、3.11 + lowest-direct）で `pytest -q` が緑; `grep -rn "3\.10" README.md README.ja.md CLAUDE.md pyproject.toml` が床と矛盾する行を返さない（床 3.11 なら 0 件）。既存テストは不変。
- 規模・整合: S / repair   出典: TQ-01 CU-26 RD-03 RD-25 RD-33

##### P0-06.2 配布単位を決め、import 時の `config/` 依存を外す
- 何を: 配布を (A) clone + editable 限定（README に明記。兄弟の pin 先は P1-11.1 の tag 方針「凍結 commit = tag = README 状態行 = pin 先」に従う）か (B) `config/` を package data にした自己完結 wheel かを決める（D-P0-06-2）。A の ADR-0109 追補は D-P1-08-1 B の追補と同じ `## Amendment` 1 本にして release PR に入れる。どちらでも `core/prompts.py` の import 時ロード（`__getattr__` → `get_prompt_templates()`）を使用関数内へ下げて `--help` / `init` が prompts 無しで動くようにし、`docs/CONFIGURATION.md:498` に「checkout 外では `CONTEMPLATIVE_CONFIG_DIR` 必須」を書く。README EN/JA の Quick Start と Facts に install 経路の 1 文を足す。
- 根拠: `pyproject.toml:36-37` `packages = ["src/contemplative_agent"]`（force-include 無し）、`src/` に非 .py は 0 件、wheel 実測 101 entries / `config/` 0（scratchpad `dist/`）; `core/domain.py:23-27`（`_PROJECT_ROOT = Path(__file__)…parent×4` → site-packages では `lib/python3.x/config`）→ `:292-294` で `FileNotFoundError`; `core/prompts.py:51-53`; `cli/runtime.py:52-60` `_repo_root()`; 兄弟 pin は PyPI 未公開の `contemplative-agent>=2.7.0`（cloud `pyproject.toml:26`）/ `>=2.10.0`（mlx `:55`）で、README は `>=2.0`（cloud `README.md:76`、mlx `:99`）と不一致。
- 完了条件: (A) なら README EN/JA に「wheel / `uv tool` 未対応、`-e` 前提」の 1 文（兄弟の `[tool.uv.sources]` tag pin は P1-11.1 で 1 箇所に定める）と、release PR に ADR-0109 の `## Amendment` 1 本（D-P0-06-2 A と D-P1-08-1 B を同じ見出しの下に）; (B) なら素の venv に wheel を入れて `contemplative-agent init` が通る。いずれでも `CONTEMPLATIVE_CONFIG_DIR` 未設定・checkout 外の `--help` が rc 0。
- 規模・整合: M / repair   出典: TQ-38 CU-27 RD-01 RD-02 RD-28 RD-33 RD-39

##### P0-06.3 packaging smoke を CI に 1 job 足す
- 何を: D-P0-06-2 = A のとおり主文を「checkout → 新 venv → `pip install -e .` → `contemplative-agent --help` → `MOLTBOOK_HOME=tmp contemplative-agent init` → `python -m contemplative_agent.testing --help`」にした job `packaging` を `verify.yml` に足す（3.13 の leg）。`uv build` は「wheel が作れる」1 step に落とす（B を採った時だけ wheel 経路に戻す。非 editable の wheel は `config/` を含まず `domain.py:294` の `FileNotFoundError` で collection error 34 件 — 実測）。同じ job の 2 本目の leg が床の検査: Python 3.11 + `uv sync --resolution lowest-direct` + `pytest -q` のみ（`verify.sh` は呼ばない — lint / type ツールまで床版に下がるため。3.13 では numpy の最下が 1.26.0 に解決され床にならない — 実測）。P0-05.11 の README install 2 経路（uv / venv+pip、Quick Start の fenced block から抽出）のケースも 3.13 の leg に同居させる。.2 が終わるまで赤で始めてよい。
- 根拠: `grep -rn "uv build\|twine\|python -m build\|check-wheel" .github .claude scripts tests` → 0 件; `verify.yml` は `verify.sh` 1 本; `tests/test_packaged_assets.py:43-44` は checkout の `config/prompts` を前提で wheel は見ない; wheel の `contemplative_agent/testing/` 5 件は入っている（実測、RD-39 と一致）ので kit 配布は修理後に成立する。
- 完了条件: job `packaging` の 2 leg が緑（3.13 の leg: `CONTEMPLATIVE_CONFIG_DIR` 未設定で `init` が rc 0 を含む; 床 leg: 3.11 + lowest-direct で `pytest -q` 緑、実測 4,762 passed / 2 failed（rsync 不在の 2 件）/ 178 skipped）、runbook（.6）の段 3 がそれを release の前提にする。既存テストは不変。
- 規模・整合: S / repair（CI = 検査面の修理）   出典: RD-06 RD-25 RD-39   注: 床 leg の pandas は床（2.2.0）で解く（pandas 3.0.x は numpy 1.24.0 と ABI 非互換で `test_instrument_census.py` が ImportError。P1-08.6 は着手 12-19 で本束より後なので、この job で先に解き、P1-08.6 が入ったら合わせる）

##### P0-06.4 動いている版を申告できるようにする（`--version` / `__main__` / manifest）
- 何を: `importlib.metadata.version("contemplative-agent")` を 1 箇所に置き（版の出どころはここだけ）、`--version`、`src/contemplative_agent/__main__.py`、snapshot `manifest.json` の `framework_version` / `git_commit` / `prompt_digests` / `manifest_schema`（欄名はこの 4 つに固定。P1-07.13 の来歴 record 型（着手 2027-01-16）が入ったら、そこから写す形に更新）、監査 JSONL の header に載せる。`sync-research-data.sh` の commit 本文 2 行目に決定論の要約（`patterns=10985 skills=53 rules=2 reports=217 snapshots=100 framework=v2.x.y`）を付ける（P3-05 の「manifest と sync commit に版と件数」項目を吸収）。
- 根拠: `grep -rn "__version__\|importlib.metadata" src/` → 0 件; `src/contemplative_agent/__main__.py` 不在（`python -m contemplative_agent` は失敗、`.cli` は動く）; `contemplative-agent --version` → argparse rc 2（CU-34 の実行記録）; 版は `pyproject.toml:3` にしか無い; `scripts/sync-research-data.sh:120-121` `git commit -m "sync: $TIMESTAMP"`（data repo の履歴はこの 1 行だけ）; manifest に version / commit 系キー 0（`core/snapshot.py:116-122` は generation_model / serving_env まで）、公開 manifest 100 件の鍵集合は 3 世代（14 / 15 / 19 鍵）で schema 版の鍵が無い; `scripts/weekly-analysis.sh:175-181` 自身が data repo の `git log --before=` で版を探している。
- 完了条件: `contemplative-agent --version` の出力 == pyproject の version をテストが固定; `python -m contemplative_agent --help` rc 0; 新規 snapshot の manifest に 4 欄があるテスト（`tests/` に 1 本）; data repo の次の snapshot manifest に `framework_version` がある; `git log --format=%b` で件数の時系列が引ける。
- 規模・整合: S / repair（来歴の記録 = ADR-0075 の observability）   出典: CU-34 RD-07 RD-19 DE-13
- 消費計画: (a) 再現者と `weekly-analysis.sh` の版探索、P3-02 の境界表が snapshot / sync commit を読む (b) 読みごとに snapshot・公開行をコード版に対応づける（決定は無い — 来歴の記録） (c) snapshot 機構か sync の退役時に欄ごと撤去

##### P0-06.5 CHANGELOG に Unreleased を置き、v2.12.0 以降を記録する
- 何を: `## Unreleased` を起こし、ADR-0109〜0113（+ 0113 追補 2 本）と RFC-0038〜0049 の done / blocked、score4 enforce・fail-closed・既定反転（`4b85f22`）を節に落とす。v2.1.0 の stub と「v1.x は `git log v1.3.1..v2.0.0`」の注記を足す。以後「RFC を done にした PR / ADR を accepted にした PR が Unreleased に 1 行足す」を CLAUDE.md 鮮度規約（`:13`）か weekly-gate Step 6d に 1 行追記（SKILL.md 側を選ぶなら着手週 11-07 の本束の PR に入れる — 本項目は §4.0 の先行列に無いので 10-31 の同梱 PR には乗せない。Step 6d のその 1 行は本項目が所有）。
- 根拠: `grep -ni unreleased CHANGELOG.md` → 0 件; 先頭節 `CHANGELOG.md:9` は v2.12.0（2026-09-12）; `git log --oneline 950f190..HEAD | wc -l` → 185（`--since=2026-09-13` では 177 — 方法差）; 見出し一覧に `v2.1.0` / `v1.x` 無し（origin には v0.2.0〜v2.12.0 の 22 tag、うち 8 lightweight — .11 と同数）; `README.md:133`「release v2.12.0 (as of 2026-10-08)」は 10-08 リリースと誤読しうる。
- 完了条件: `grep -c '^## Unreleased' CHANGELOG.md` = 1（release commit 直後も空節として残す）; CHANGELOG の `## vX.Y.Z` 見出し集合 ⊇ origin の v2.x tag 集合（v1.x は 1 注記で可）; v2.13.0 節が ADR-0109〜0113 と RFC-0046 を引く。
- 規模・整合: S / neutral   出典: RD-10 DC-01 AB-40

##### P0-06.6 release runbook を repo 内に書き、記録台帳を始める
- 何を: `docs/runbooks/release.md` を書く — (0) RFC-0046 再開条件 → 旧 gate 削除 + ADR-0113 追補 3 → (1) `verify.sh` exit 0 → (2) 兄弟適合（`scripts/check-sibling-backends.sh` を走らせ、結果 1 行 `Sibling conformance: mlx ok / cloud …` を P1-11.13 が gate 行に出す `sha / main / level / kit` から写して CHANGELOG の版節に貼る。`docs/runbooks/sibling-backend-conformance.md:53-58` の古い段落の書き換えは P1-11.3、cloud の処遇は P1-11）→ (3) packaging smoke（.3）+ release 前 1 回の `verification_parse` differential replay（固定 baseline + 4,963 challenge、mismatch 0。定期化はしない — P1-08 の定期化案を落とした分の 1 行）→ (4) 版・DOI 整合（.7）、Unreleased → 版見出し、要約同期、依存の固定（D-P1-08-1 = B なら `uv lock` → `uv export --no-dev --frozen -o docs/evidence/release-vX.Y.Z/requirements.txt` の 2 行。`uv.lock` は gitignore なので lock を先に作る — `--frozen` 単独では失敗する。A なら `uv sync --locked` の確認。書いた requirements.txt は CHANGELOG の版節から参照）、外部リンクの確認（README / README.ja / CITATION.cff / .zenodo.json / llms*.txt の http(s) URL を `curl -sI` で確かめ出力を release 記録に残す。週次チェーンには入れない — 無人の外部 I/O を増やさない）→ (5) annotated tag（メッセージ = CHANGELOG 見出し。停止基準: tag を打つ commit で `git ls-files | grep -c real_sample` = 0、かつ P0-03.11 の不在テストが verify に入って緑 — Zenodo 版は tag 時点の tree の zip で不変）+ GitHub Release → Zenodo（DOI 採番は人間承認）→ (6) DOI 戻し commit + SWH save（SWHID は `rel` / `dir + qualifier` 形、.11）→ (7) HF 同期 → (8) データ版 DOI — v2.13.0 と同時には切らない（最初の新版は 11-21 の 3 決定の後、12-05 のゲートの後 — P3-05.12）。deposit の作成手順を 1 行（D-P3-05-1 (b)「不変の DOI 版に何を入れるか」の A / B / C に従う。推奨 C なら deposit 用コピーで Context ブロックを `[see GitHub <commit>]` に置換し Internal note / Output は残す — R2-ETH-10）。D-P3-05-1 (b) が B / C なら、最初の新版より前に data repo の Zenodo–GitHub 連携を off にし（オーナーが Zenodo の GitHub 設定画面で状態を確かめ、日付を releases.md の備考に残す）、data repo では GitHub Release を作らない（連携が on のまま Release を作ると tree 全体の版が別に自動採番される）→ (9) 兄弟 pin / README → (10) RFC-0046 done。launchd 構成の差分を確かめる段（中身と位置は P2-04.22 (b) が所有）も同じ runbook に置く。各段に停止基準と必要な資格情報（Zenodo token / `hf` / `gh`）。最終段で `docs/evidence/releases.md` に 1 行（tag / commit / annotated? / Release URL / 版 DOI / SWHID（`rel` か `dir + qualifier`、snp 単独不可）/ HF revision / 備考。過去 22 tag の遡及は .11）。`release-doi` skill はここへのリンクだけにする。
- 根拠: `docs/runbooks/` に release の runbook 無し（6 ファイル）; `docs/runbooks/README.md:23-26`「手順の実体をここに置き、`~/.claude/skills/release-doi/` からはリンクだけ張る」と自ら規定; `.claude/skills/` 11 件に release-doi 無し; 参照は `docs/adr/0088:133`、`docs/CYCLES.md:92`、`rfcs/0046:240,262`; tag は annotated / lightweight 混在（`git ls-remote --tags origin`: v0.2.0〜v1.2.0・v1.3.1・v2.2.0・v2.2.1 が lightweight）、ローカル shallow clone は `git tag -l` 0 件; `docs/evidence/` に release 記録無し; `scripts/check-sibling-backends.sh:63-66`（成功時 `[sibling] ok` だけで kit の出力を捨てる）、`a0cdcbc`（2026-09-12、3 backend 静的 PASS を commit message にだけ残す）; `.gitignore:18` `uv.lock`、`pyproject.toml:106-117`（「uv.lock is gitignored here」）; `tests/test_doc_links.py:39`（`_EXTERNAL_PREFIXES` で http(s) を skip、README に外部 URL 約 30 本）; data repo に `.zenodo.json`（`:2` `upload_type: dataset`、連携が読むファイル。連携が今 on かは推測）
- 完了条件: `docs/runbooks/release.md` の全段（10 段 + P2-04.22 (b) の段）が停止基準を持ち、段 (5) に `real_sample` 0 件と P0-03.11 の不在テスト、段 (8) に Zenodo–GitHub 連携 off の条件がある; `docs/evidence/releases.md` に v2.13.0 行; `git ls-remote --tags origin | grep 'v2.13.0^{}'` が 1 行; v2.13.0 の CHANGELOG 節に `sha / main / level / kit` 付きの兄弟適合の結果行; D-P1-08-1 = B のとき `docs/evidence/release-v2.13.0/requirements.txt` が存在し CHANGELOG v2.13.0 節からリンクされる; 外部 URL チェックの出力ファイルが release 記録に残る（v2.13.0 で初回）。
- 規模・整合: S / neutral   出典: RD-12 RD-30 RD-11 RD-38 DC-44 RD-29 CH-32（旧 P0-06.8）SA-27（旧 P0-06.9）DC-38（旧 P1-09.21）   依存: P0-03.11（v2.13.0 の tag より前）

##### P0-06.7 版・DOI・要約メタデータの整合を機械検査にする
- 何を: `scripts/release_consistency_check.py`（stdlib）を `verify.sh` に足す — pyproject.version == CITATION.cff.version == codemeta.version == README×2 BibTeX version == llms-full.txt 版; CITATION.doi == codemeta.identifier == README 版 DOI; CHANGELOG 先頭の版見出し == version; CHANGELOG 各版見出しの DOI == `docs/evidence/releases.md`（.11）の行。CITATION.cff の `doi:` / `url:` は concept DOI（`10.5281/zenodo.19212118`）にして tag 時点の自己引用ずれを消す（版 DOI は README / CHANGELOG 側）。同じ release commit で CITATION.cff abstract / codemeta description / .zenodo.json description / HF 2 card の冒頭を `README.md:12` の 1 文に揃え、keywords に `value-layer` / `human-approval-gate` / `harness` を足す。
- 根拠: release commit `950f190` は 10 ファイル、DOI 戻し `c958d1f` は 5 ファイルの手作業; `git show 950f190:CITATION.cff` → `doi: 10.5281/zenodo.22028295`（= v2.11.0 の DOI）で `version: "2.12.0"` — tag の中身と SWH snapshot が前版を自己引用; concept DOI の先例 `CHANGELOG.md:367`; `CITATION.cff:5-11` / `codemeta.json` / `.zenodo.json` は「security-first … four architectural principles」のまま、README は `3720d79` で主語を置換済み; `verify.sh` / `scripts/docs_consistency_scan.py` に version / DOI の検査無し。
- 完了条件: スクリプトがずれで非 0; tag v2.13.0 の中の CITATION.cff `doi:` が concept DOI（または自版 DOI）; 4 ファイルの冒頭 1 文が同一（スクリプトで比較）。HF card は本セッションから未検証 — runbook 段 7 で目視。
- 規模・整合: S / repair（`verify.sh` の検査 = 修理）   出典: RD-08 RD-13 RD-17 DC-04

##### P0-06.10 sdist の範囲を決め、キャッシュ dir を除外する
- 何を: `[tool.hatch.build.targets.sdist]` に範囲を 1 行で書く（全部入りなら `exclude` にキャッシュ・venv 系を列挙）。`.import_linter_cache/` をルート `.gitignore` に足す。
- 根拠: `pyproject.toml` に sdist 設定無し; リポジトリ直下に `.import_linter_cache/`（`CACHEDIR.TAG` + 自己 `.gitignore`）があり root `.gitignore` に無い; scratchpad の非 git コピーで `uv build --sdist` → 2,102 entries / 22 MB（`.import_linter_cache` 4・`.claude` 14・`config` 112・venv 由来 1,089）— git の有無で中身が変わる = 範囲が未決（RD-05 の git checkout 実測は 5.98 MB）。
- 完了条件: `tar -tzf dist/*.tar.gz | grep -cE 'import_linter|\.venv'` = 0 を packaging smoke（.3）が検査。
- 規模・整合: S / neutral   出典: RD-05

##### P0-06.11 版識別子の台帳 — CITATION.cff の SWHID を `rel` / `dir + qualifier` 形にし、releases.md を 22 tag + data v1.0.0 まで遡って埋める
- 何を: `CITATION.cff:30-51` の 7 件（すべて `swh:1:snp:…`、「Software Heritage snapshot of v2.x.0」）を、annotated tag なら `swh:1:rel:<tag object>`、lightweight tag なら `swh:1:dir:<tree>;origin=https://github.com/shimo4228/contemplative-agent;visit=swh:1:snp:<既存値>;anchor=swh:1:rev:<commit>` に置き換える。`docs/evidence/releases.md`（.6）の SWHID 列を「rel か dir + qualifier。snp 単独は不可」と定義し、v2.13.0 の release commit と同時に入れる。同じ台帳を v0.2.0〜v2.12.0 の 22 行 + data repo `v1.0.0`（`acc3ad9`）の 1 行で遡って埋め（列: tag / commit / annotated? / GitHub Release URL or none / 版 DOI or none / SWHID / HF revision or n/a / 備考: deposit に含まれた `knowledge.json` の形）、CHANGELOG の各版見出し末尾に版 DOI を 1 リンク足す。Zenodo 側の読み取り（どの tag に deposit があるか）はオーナーのみ可能。
- 根拠: `CITATION.cff:30-51`（`identifiers` 7 件すべて `type: swh` / `swh:1:snp:` / v2.6.0〜v2.12.0）; `git ls-remote --tags origin`（2026-10-10）: v0.2.0 / v0.3.0 / v1.0.0–v1.2.0 / v1.3.1 / v2.2.0 / v2.2.1 は lightweight（`^{}` 行なし）で SWH の release オブジェクトを持たない; `snp` は訪問時点の全ブランチ・タグ集合の識別子で版の tree を一意に指さず、`description` の「snapshot of v2.6.0」と意味が食い違う（仕様）。SWH API は本セッションから 403 で、各 snp に対応する rel / dir の実在は未確認 / 本体 repo 内の版 DOI は `22724623`（v2.12.0、10 箇所）のみで `CHANGELOG.md` に DOI 0 件; HF `Shimo4228/contemplative-agent` card の「Per-version DOI (v2.3.0, 2026-05-05): 10.5281/zenodo.19212119」が repo 外に残る唯一の過去版 DOI; data `CITATION.cff:5-8` は concept DOI + version 1.0.0 のみ; Zenodo API も 403（どの tag に deposit があるかは未確認 — だからこそ repo 内に表が要る）
- 完了条件: `CITATION.cff` に `swh:1:snp:` 単独の行が 0; 各 SWHID が SWH の resolve API で 200 を返した記録（日付つき）が releases.md に 1 列ある（オーナーの手元で実施）; 22+1 行がすべて埋まり「無し」は明示; `scripts/release_consistency_check.py`（.7）が CHANGELOG 見出しの DOI と releases.md の一致を検査する
- 規模・整合: S / neutral   出典: R1-REP-01 R1-REP-02（旧 P0-06.12）


**依存**
- P0-02（RFC-0046 後始末 3: 旧 gate 削除 PR は 10-17 のゲートで go、merge はゲートの後）— v2.13.0 の前提
- P0-03.11（tag の commit に `real_sample.jsonl` が無いこと — .6 段 (5) の停止基準。v2.13.0 の tag より前）
- P1-11 の先行項目（11-07 の P1-11.2 / .3 / .13、11-14 の P1-11.5）— .6 段 2 の cloud 判断と runbook 段落（P1-11.3）、release gate の兄弟行 `sha / main / level / kit`（P1-11.13）
- P0-03 / P3-05（D-P0-03-1 / D-P0-03-3 / D-P3-05-2 と D-P3-05-1 (b) — runbook 段 8 のデータ版はこれらの後）
- 順序: P0-05（同じ 11-07 の着手で同じ PR 列。Quick Start smoke、P0-05.11 の README install 2 経路は .3 と同じ job に同居）
- 本束より後の週の項目（いずれも現行の形で書き、依存先が入ったら更新）: P1-08.5 (B)（.6 段 4 の 2 行の正本）、P1-08.1（verify の行列 2 セルの定義 — 床 leg は本束 .3 が持つ）、P1-08.6（床 leg の pandas / numpy 床）— P1-08 は着手 12-19; P1-07.13（来歴 record 型 — .4 の manifest 4 欄。着手 2027-01-16）; P1-11.1（.2 / D-P0-06-2 A の兄弟 pin 方針。P1-11 は着手 12-26）。差分 replay の定期化案を落とした分は .6 の 1 行
- 外部: Zenodo / SWH / HF の資格情報（オーナーの手元）。.11 の SWH resolve 確認と Zenodo 読み取り、.6 段 8 の Zenodo–GitHub 連携の確認はオーナーのみ
- → 参照元: P2-04.22 (b)（release runbook に launchd 構成差分の段を 1 つ足す — .6）、P4-02.1 (3)（最終 deposit は .6 の段 8 を引く。`final` tag も Zenodo–GitHub 連携の条件を引く）、P2-04.23 / P1-08.26（`.venv` の再生成は .6 段 4 の `docs/evidence/release-<版>/requirements.txt` から）、P0-03.3（sync commit 本文の rsync の版の行が .4 の要約行の隣）、P1-08（CI 強化 — .1 / .3 の恒久化先）、P2-03（私的ハーネス: release-doi skill の実体 — .6 の skill 側の縮退）、P3-05（公開データの DOI 版、P3-05.12 / .14 — runbook 段 8 と .11 の data v1.0.0 行を引く）


#### P0-07 10-31 due の憲法改正ゲートの事前登録と shadow 系列
- 狙い: 次回 due（2026-10-31 = last_adopted 2026-08-09 + 83 日）は、初めて計器つき（IPD 二腕 + shadow）で開く憲法改正ゲート。結果変数を予測つきで先に登録し、shadow 系列を 8 月の 2 点から伸ばし、改正の記録欄（referent inventory・入力選択比・機械書きの出自・shape 読み）を整えることで、価値層の「legible な進化」（ADR-0080）を事後解釈でなく事前登録で読める形にする。
- 期限・順序: 10-31 の週（10-26〜30。§4.0 は P0-07 を 10-24 の着手束に置く（10-24 のゲートの後、10-26〜30 に PR）。.4 だけは 10-17 の週の先行項目）。期限は 2026-10-31 の due 前。週の言い方は §0（「X の週」= 土曜 X の前の月〜金で、X のゲートで使うものはその金曜までに main へ）。10-31 の土曜ゲートは決定 5 件・熟慮 3（P0-07 の 2 件 + D-P1-11-1 / D-P1-12-1 / D-P2-01-5。§4.0 の生成値）で、P0-07 の 2 件は土曜当日は読みのみ（B）が既定で軽い（憲法改正は weekly-gate SKILL.md:238-240 のとおり別セッション）。10-31 の週は 10 月で最も Ollama の読みが多い（IPD null pair だけで ≈ 4 h、shadow 2 run と score 150 行を足すと推定 6〜8 h。前夜起動で在席不要）。.1（shadow 2 run と ADR-0092 の Consumption plan）と .2（事前登録 RFC）はこの週に入れ、Ollama を使う読み（shadow run・IPD）は平日の guard 窓で前日までに取る（P2-01.11 の時刻表）。.4（RFC-0012 の照合先と間隔の訂正）は 10-17 の週（§4.0 の先行列、10-16 まで）、.4 の消費（done）は 10-31 のゲート。.3 / .7（記録欄）は 10-31 の週に merge（prompt 変更で eval baseline が STALE → S24 の確認済み経路）。.8 の L11 削除は prompt 編集（P3-07.1 チャネル (3)）なので 10-31 の読み（.1 / .2）取得後。SKILL.md の変更（Step 6b に「due=true の週は改正ゲートを次の土曜に予定し `gate_record` に 1 行」の 1 句、.4 が所有）は 10-31 前の同梱 PR。P0-04.5 / .7 の憲法経路の修理が先（同じ 10-31 の週）。束の閉じ方: 下の完了条件は書き手のコードとテストの merge で満たし、本番の改正での確認は .7 の消費計画 (a)（D-P0-07-1 = A の回、B なら以後最初に起動された改正）。2027-Q1 までに改正が無ければ .1 (c) / .7 (c) の撤去と同じ日付で閉じる。この束の決定: D-P0-07-1 / -2（10-31）。
- 束の完了条件:
  - `logs/constitution-shadow.jsonl` に 2026-10 の run が 2 本以上、`docs/evidence/adr-0092/` に系列（4 点以上）の表
  - 事前登録 RFC（主要 1 本 = IPD Δeffect + 記述的 3〜4 読み、予測と片側の反証線つき）が 10-31 より前の日付で commit されている
  - `rfcs/0012` の `state:` が done、ADR-0092 に Consumption plan（撤去条件つき）
  - 書き手のコードと、fixture manifest に 4 値（`matched_count / live_count / top_k / threshold`）+ shape 値 + 出自（sidecar または本文）が出るテストが merge 済み（.7 / .8）
  - RFC-0012 / ADR-0091 / `scripts/value_layer_due_check.py` の間隔が 83 で一致

##### P0-07.1 shadow 憲法を 10 月中に 2 run 以上取り、系列を evidence に固定する
- 何を: shadow は 2026-08-11 の 2 run（同一コーパス、cosine 0.814 / 0.798、noise 0.016）以降走っておらず、4,785 pattern が積まれた今の影は未読。10 月中に `shadow-constitution` を 2 run（think-ON、JST 0/6/12/18 の窓外）、可能なら 11 月初旬に 1 run 取り、cosine と section inventory の系列（4 点以上）を `docs/evidence/adr-0092/` に追記する。
- 根拠: `docs/evidence/adr-0092/shadow-run-1-reading.md`（2026-08-11、cosine 0.814 / 0.798）/ `docs/adr/0092:136-141`（No scheduled wiring、CLI opt-in 先行）、`:150-151`（≥ 2 runs、one run is wiring proof）/ data repo `reports/analysis/weekly-2026-10-02.md:175`（NO_ROWS `constitution-shadow.jsonl`）、`pipeline/value-layer/value-layer-2026-10-02.json`（days_since 54、patterns_since 4,785）/ `docs/adr/0092` に Consumption plan 節なし（grep 0 件）、`:235-236`（配線提案時に再訪）、`scripts/_census_registry.py:136-138`（`constitution-shadow.jsonl` の `cadence_days=90` は休眠を QUIET にして見えなくする）
- 完了条件: `constitution-shadow.jsonl` に 2026-10 の行が 2 本以上、evidence に系列表（日付・cosine・section inventory・corpus 件数）4 点以上。ADR-0092 に日付つきの Consumption plan（読み手 = 次回改正ゲート 2026-10-31、採否にかかわらず run 3 の要否をそこで決める、2027-Q1 までに改正が無ければ計器を撤去 — census 行も）と撤去条件の日付があり、RFC-0012 の Next action が同期している。
- 規模・整合: S / instrument   出典: RF-11 VL-31 OI-33（旧 P0-07.5 を含む）
- 消費計画: (a) 10-31 の改正ゲート（weekly-gate、人間同席）が evidence の系列表を読む (b) 2 回の読み（10-31 と、改正を起動した場合は採択後の review）で D-P0-07-1（起動 / 見送り）と D-P0-07-2（配線 / 手動 / 撤去）を決める (c) 2027-Q1 までに改正が無ければ計器を撤去（ADR-0092 の Consumption plan の撤去条件、census 行も）

##### P0-07.2 改正の前後比較の結果変数を予測つきで事前登録する
- 何を: ADR-0090 は「2026-08-09 を前後比較の基準点」と置くが何を比較するかは未指定。改正前に (a) IPD two-arm（`scripts/ipd-two-arm.sh`）、(b) shadow 系列の cosine、(c) 環境応答率（gate_record / comment outcomes）、(d) identity 距離 の 4 読みと、(e) 公開コメントで Context に無い constitution / axiom 自己言及語の率（P3-06.9 (c) と同じ定義、`reanalysis: public`。上昇は 07 月 — 基準点 08-09 より前 — から始まっているので前傾向として扱い、改正の効果とは読まない）を 1 本の RFC に登録し、runbook step 3 の判断材料に並べる。主要な読みは (a) IPD Δeffect の 1 本（契約どおり）で、残りは記述的と宣言し、反証線は予測方向の片側にする。各床が 1 対由来であること（IPD ±0.13 = ADR-0090:214-216「max of three per-α swings from a single null pair」、shadow cosine 0.016 = `docs/evidence/adr-0092/shadow-run-1-reading.md:39-41`「one pair」）と「静かな読みは『無い』でなく『見えなかった』」（`docs/evidence/adr-0090/null-pair-reading.md:33-36`、ADR-0090:133）を RFC 本文に 1 行ずつ写す。.3 の referent inventory も記述的な読みとして含める。
- 根拠: `docs/adr/0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md:240`「以降の週次レポート・T-P3 縦断読みの前後比較基準点は 2026-08-09」/ `docs/runbooks/constitution-amendment.md:19-35`（step 0 shadow、step 2 bench、step 3 approve:「The instrument informs; it does not gate」）/ `scripts/ipd-two-arm.sh` 存在 / ADR-0056 系の事前登録文化
- 完了条件: `rfcs/` に事前登録 RFC が 10-31 より前の日付で commit され、主要 1 本（IPD Δeffect）に予測と片側の反証線、残りは記述的と明記されている。各読みの行に `reanalysis: public | private-rows | rerun-local | rerun-cloud` の列（P3-01.1 の規則。P3-01 は着手 12-12 で本項目より後なので現行の 4 値で書き、P3-01.1 が入ったら合わせる）。(e) の行は前傾向の 1 句を含む。
- 規模・整合: S / instrument   出典: RF-22 PF-12
- 消費計画: (a) 改正ゲートの人間（10-31 と、改正を起動した場合は採択後 4 週の review） (b) 改正前後の 1 対の読みで予測との一致 / 不一致を RFC の照合節に記録し、主要 1 本が反証線を越えたら復元（`docs/evidence/adr-0090/` の前版）を判断する（残りは記録のみ — 「1 本でも越えたら復元」は家族単位の誤報率を上げるので採らない） (c) 改正後の review 1 回で RFC を done にし、次の due までは読まない（撤去 = RFC の終端。改正を見送った場合は次の due に持ち越し、2027-Q1 までに改正が無ければ .1 (c) と同時に撤去）

##### P0-07.3 条項の指示対象（referent inventory）を shadow / 改正の読みに加える
- 何を: 第 3 改正（2026-08-09）は条項の指示対象を directive / belief から「自分の計算構造」（memory artifacts、token limit、resource depletion）へ広げた — 解釈キー（rules repo）が referent を狭める方向と逆の自己言及的再束縛。runbook step 0 / 6 に「各条項が統治する名詞を {directives, beliefs/goals, self-other, computational structures} で数える」列を足し、第 1〜3 版と shadow run 1–2 で表を埋める。同じ表に版ごとの ADR-0005 衝突語彙件数の列（`constitutional directives` / `constitutional clauses` / `process of the constitution` / `applying rules` の 4 句）を足し、FLIP への依頼文（P3-06.4）に「版ごとの refusal / disclaimer 件数を judge 失敗と分けて併記」の 1 行、P3-06.5 の突合に 4 行目「語彙除去 × non_duality 最弱の交絡可能性」を置き、P3-04 の lineage にも同じ列を足す。read-only の読みで、憲法文には触らない。
- 根拠: data repo `constitution/contemplative-axioms.md:5`「any structure, whether conceptual or computational (e.g., memory artifacts, defined boundaries), is provisional scaffolding」、`:18`「every signal of systemic limitation (whether resource depletion, memory ceiling, or functional boundary)」/ `snapshots/amend-constitution_20260809T052952499578Z/reasoning.md:10,15`（process の mechanics を philosophy に写す plan）/ `contemplative-agent-rules/prompts/operator-keyed.md:15`（Referent を作業結論に狭める）/ rules `docs/adr/0005-…md:19,21`「Mechanism (hypothesis): a surface-form collision …」; 実測（R1-FLIP）: rules `rules/contemplative/contemplative-axioms.md` に衝突語彙 5 指示対象、`docs/evidence/adr-0090/constitution-2026-05-05-retired.md` と data `constitution/contemplative-axioms.md` は表題の `Constitutional`(:1) のみ（5 / 1 / 1）。frontier safety-trained モデルが衝突語彙に反応する差が「進化版 vs 原文」差に混入しうる（推測 — ADR-0005 自身が機構を仮説扱い）
- 完了条件: 表（版 × 4 カテゴリ + 衝突語彙列）が evidence に 1 枚、次回ゲートの判断材料として runbook から参照される; FLIP 依頼文に 1 行、P3-06.5 の crosscheck に 1 行、P3-04 の lineage に列（前提: FLIP 側の cloud 実行 — 本体は value layer を再送信しない）。
- 規模・整合: S / instrument   出典: PF-12 R1-FLIP-02（旧 P0-07.9）
- 消費計画: (a) 改正ゲートの人間が runbook step 0 / 6 で表を読む（衝突語彙列も同じ表） (b) 探索的計器: 改正ごとに 1 回埋め、2027-Q1 の review（.1 (c) と同じ時点）で継続可否 (c) 2 改正分埋めても判断材料にならなければ列を runbook から外す

##### P0-07.4 RFC-0012 の照合先と間隔を正し、10-31 のゲートで消費して done にする
- 何を: RFC-0012 の照合先「weekly packet §8」は ADR-0098 で退役済み（gate は value-layer JSON を直読み）、本文の「84 日間隔」は ADR-0091（83）と `value_layer_due_check.py`（既定 83）と食い違う。照合先を `pipeline/value-layer/*.json` の `constitution.due`、間隔を 83、次の照合日を 2026-10-31 に訂正する。10-31 の weekly-gate で runbook step 0（shadow ≥ 2 run、床アンカー）を実行し、改正の起動可否（D-P0-07-1）と月次配線可否（D-P0-07-2）を 1 行ずつ記録して done にする。weekly-gate Step 6b と runbook に「due=true の週は改正ゲートを次の土曜に予定し `gate_record` に 1 行」の 1 句を置く（due は 83 日ごと。RFC の自動起票はしない）。
- 根拠: `rfcs/0012:2-3,8,12`（blocked since 2026-08-16、「84 日間隔」「weekly packet §8」）、dead-band 照合節 18 本 / `docs/adr/0091:84,108-111`（83 日、27/83 は policy choice）/ `scripts/value_layer_due_check.py:581`（`--amendment-interval-days` default 83）/ `value-layer-2026-10-02.json`（interval 83、last_adopted 2026-08-09 → due 2026-10-31）
- 完了条件: RFC-0012 の 3 箇所（照合先・83・日付）が訂正され、10-31 後に `state: done`、ADR-0092 D5 の消費者が 1 回実際に消費した記録が evidence にある。SKILL.md Step 6b と `docs/runbooks/constitution-amendment.md` に due 週の 1 句がある（SKILL.md の変更は 10-31 前の同梱 PR）。既存テストは不変。
- 規模・整合: S / repair   出典: AB-07 AB-42 WO-52   順序: 訂正は 10-17 の週（10-16 まで、§4.0 の先行列）、Step 6b の 1 句は 10-31 前の同梱 PR（Step 6b のこの 1 句は本項目が所有）

##### P0-07.7 改正の入力選択比と shape 値を manifest に記録する
- 何を: 改正は live pattern 約 4.8k のうち constitutional view の cosine 上位 50（threshold 0.55）だけを見るが、manifest は `views: []` で選択比が無い。`AmendmentResult` / snapshot manifest に `matched_count / live_count / top_k / threshold` と、shadow と同じ shape 読み（節数・条項数・quoted 率）を載せる。拒否はしない（bold integration は設計意図）。runbook step 6 の記録項目に追加。
- 根拠: `core/constitution.py:23`（`MIN_PATTERNS_REQUIRED = 3`）、`:108-109`（view cosine で取得）、`:49-62`（`AmendmentResult` に件数欄なし）/ `config/views/constitutional.md`（threshold 0.55、top_k 50）/ data repo `snapshots/amend-constitution_20260809T052952499578Z/manifest.json`（`views: []`）、`value-layer-2026-10-02.json` patterns_since 4,785 / `docs/adr/0092:59`（friction-biased sample）
- 完了条件: 書き手のコード（`AmendmentResult` と snapshot manifest に 4 値 + shape 値）と、fixture manifest に 4 値 + shape 値が出るテストが merge 済み; runbook step 6 に記録項目。
- 規模・整合: S / instrument   出典: PF-35 PF-38
- 消費計画: (a) 改正ゲートの人間が runbook step 6 で本番 manifest の 4 値と shape 値を読む（D-P0-07-1 = A なら 10-31 の回、B なら以後最初に起動された改正） (b) 改正ごとに 1 回、選択比（matched / live）と shape の前版差を記録して判断材料にする（拒否はしない。2 改正分で判断材料にならなければ shape 値の列を外す） (c) 2027-Q1 までに改正が無ければ .1 (c) と同時に撤去（4 値は manifest の来歴欄として残す）

##### P0-07.8 改正の出自（版・親 sha256・採択日・モデル）を機械が書き、Source 行の書換をやめる
- 何を: プロンプト L11「If the input claims a verbatim source, update that attribution」により、本番憲法の Source 行は gemma の自己記述（"amended based on deep pattern recognition …"）になっている。`adopt-staged` が出自（`amendment: 3`, `adopted:`, `parent_sha256:`, `generation_model:`）を機械的に書き、L11 を「Source 行は変更しない」に戻す。注意: 憲法は `read_constitution`（`domain.py:329-332`）が frontmatter を剥がさず連結して注入する（`_load_md_files` の剥離は skills / rules のみ）ので、frontmatter を置くなら `read_constitution` に剥離を足すか、出自は sidecar（manifest / `.meta.json`）に置く。
- 根拠: `config/prompts/constitution_amend.md:11` / data repo `constitution/contemplative-axioms.md:2`（Source 行、model 生成）、`reasoning.md:23`「(The attribution must be updated)」/ `core/llm/prompting.py:175-200`（`_load_md_files` は skills:295 / rules:327 の読み手）vs `core/domain.py:352,329-332`（憲法は raw 連結）/ `cli/runtime.py:223`（`load_constitution` が system prompt へ）
- 完了条件: 出自 4 値を書く `adopt-staged` のコードと、fixture の改正で sidecar（または本文）に出自 4 値が出るテストが merge 済み（本番での確認は .7 の消費計画 (a) と同じ回）、`constitution_amend.md` L11 が削除され、注入される憲法文に出自が混ざらないテスト 1 件。(b) L11 の削除は 10-31 の読み（.1 / .2）取得後に行う（前に入れるなら事前登録 RFC に「唯一の意図的変数」と明記する）; (c) 削除後の `constitution_amend.md` の sha12 を P3-04.3 の第 4 版行・P3-02.1 の境界表・P3-06.4 の束（版ごとの prompt）に書く（行はそれぞれの束で書く）。既存テストは不変。
- 規模・整合: S / neutral（出自の機械化は記録。L11 削除は prompt 編集 = P3-07.1 チャネル (3) の dated 行として登録）   出典: PF-37


**依存**
- P0-04.5（検証失敗の理由つきエラー）/ P0-04.7（`axiom_files[0]`）— 同じ 10-31 の週で先に（順序）
- ADR-0090 bench の実行環境（M1、JST 0/6/12/18 窓回避、`scripts/ipd-two-arm.sh`）
- RFC-0012、ADR-0056 / 0089（prompt 変更で eval baseline STALE → S24 の確認済み経路）/ 0090 / 0091 / 0092 / 0098 / 0101
- P1-04.16（T4 第 2 回 10-17 の読み手種別 — .1〜.3 の消費計画の読み手は「人間（改正ゲート）」）、P2-01.11（土曜の時刻表 — Ollama の読みは平日の guard 窓。10-17 の先行項目）
- 本束より後の週の項目（いずれも現行の形で書き、依存先が入ったら更新）: P3-01（研究問い ADR: Q1 の操作的定義。P3-01.1 の `reanalysis` 列の規則 — .2 が引く。着手 12-12）、P1-05（観察台帳の expiry。着手 2027-01-09）
- → 参照元: P3-04（版履歴 / 憲法 CHANGELOG — .8 の出自と同じ欄、第 4 版行に .8 の prompt sha12、.3 の衝突語彙の lineage 列）、P3-02.1（境界表に .8 の sha12）、P3-06.4（版ごとの prompt の束と .3 の FLIP 依頼文）、P3-06.5（.3 の突合の 4 行目）、P3-07.1（.8 をチャネル (3) の dated 行として登録。空性のみ公理案 — 介入チャネル表と改正ゲートの関係）


### Phase 1 — 機構層を「止める」ための後始末（〜2027-03。束の着手は 2027-01 まで、凍結の verdict は推奨どおりなら早くて 2027-05-01）

ADR-0080 の「止まる」を判定できる状態にし、止める前に一度だけ触る構造・台帳・文書・テスト・兄弟 repo・ガバナンス記録の後始末を終える。ここで増やしてよいのは read-only の読み値と記録だけで、判定者（新しい LLM 呼び出し）は増やさない。配分規約（§0）を守ると Phase 1 の 15 束は 10〜12 月に収まらないので、着手を 10 月〜2027-01 の土曜に分けて並べ（4.0 の「着手する束」列）、決定の一部も 2027-01 の 4 ゲートに載る。

**このフェーズの完了条件**
- 凍結条件表が ADR として存在し、凍結集合の commit 種別と四半期の機構 ADR 数の読みが weekly materials に出る（P1-01。定義の存在で満たす。凍結の verdict は停止リストが空になった週 + 窓が満ちた週（推奨どおり — D-P1-01-1 の追加段 B・D-P2-07-1 A — なら停止リストの最終行は P2-07.1 / P2-06.2 で、早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8 の遅い方 + 8 週で、早くて 2027-04-03）に書く）
- RFC / ADR 台帳が機械生成の索引を持ち、frontmatter と本文 Status の食い違いが 0（P1-02 / P1-03）
- 計器の T4 棚卸しが終わり、消費計画の無い計器が 0（P1-04）
- CI が macOS を含む 2 セル以上で shell 層と wheel 検査を含み、未モック LLM で vacuous に通るテストが 0（P1-08）
- README / CYCLES / CONFIGURATION / glossary の数値がすべて日付つきか生成物（P1-09）
- SECURITY.md と I/O 面 allowlist テストが存在する（P1-10）
- 兄弟 repo の処遇が決まり README に明記されている（P1-11）
- 承認記録に approver / reason / 却下本文が残る（P1-12）。AI 判断役の権限境界が CYCLES.md に書かれている（P1-13）


#### P1-01 機構層の「凍結」判定を定義する
- 狙い: ADR-0080 は機構層の完成を「止まる」と定義する（`docs/adr/0080:52-53`「completion means the layer stops moving. Changes become repair-only; mechanism-layer ADRs approach zero」）が、計測単位も閾値も無く、週次ゲートは毎週「止まったか」を再発明している。9 月の refactor 46 本と 10 月の追補・Note は「修理」の体裁で動き続けており、止める条件と残作業の一覧が要る。定義は非機械判定のまま（`:125-129`）: 読み値は機械が出し、凍結の verdict は人間が打つ。
- 期限・順序: 着手束に数えない（.1 / .2 は先行列、定義は 11-28 の D-P1-01-1、他は他束の PR に同乗）。期限は定義 2026-11-28 / verdict = 停止リストが空になった週 + 窓（推奨どおり（D-P1-01-1 の追加段 B・D-P2-07-1 A）なら停止リストの最終行は P2-07.1 / P2-06.2 で、verdict は早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8（2027-01-30 の週）の遅い方 + 8 週で、早くて 2027-04-03）。2 段 — 定義は 2026-11-28（D-P1-01-1 の土曜ゲート、追補（2026-11）の材料。Phase 1 の完了条件「凍結条件表が ADR として存在」は定義の存在で満たす）、verdict は窓が満ちた週（開始点 = 停止リスト（.3）が空になった週 = 最終行の merge 週。P1-06 の構造 PR 4 本（2027-01-16 / 01-23 / 01-30 / 02-06）の最後は 2027-02-06 の週で、D-P1-01-1 の追加段（.9）で src の機構変更を載せると最終行は P2-07.1 / P2-06.2 に動く。Phase 2 の読み）。.4 の凍結集合 → .1 の読み → .3 の表 / .6 の規則の順に文面を揃え、ADR-0080 の追補（2026-11）（P1-03.8、CLAUDE.md §北極星と同 PR。P1-03.9 の基礎率・待ち時間の 1 行ずつと .8 のモデル交代の段落も同じ PR）に 1 段落ずつ入れる（追補（2026-11）の PR は 11-30〜12-04 に草案を出し、12-05 の D-P2-07-1 の後に 12-07〜11 に merge — P1-03.8）。定義の前に走ってよいのは P0-02.2 と P1-06 の .10 / .4(a)（修理・登録簿）で、停止リストに「凍結前の最後の動かす PR」として先に載せる。契約固定 PR と P1-06.3 改名 PR は定義（D-P1-01-1 = 11-28）の後。.1 の配線（`weekly-analysis.sh` の materials 段）は 10-24 の週（§4.0 の先行列。10-31 の chain から 11-28 までに 4 週）。.2 の手タグ（`core/` 90 commit）は 10-31 の週（§4.0 の先行列。10-17 の T4 記録を読んでから、10-17 には着手しない）。.3 / .6 の weekly-gate SKILL.md 変更は追補（2026-11）と同 PR（12-07〜11 の merge）で、10-17 / 10-24 / 10-31 の週の同梱 PR には含めない。.9 の扱いは D-P1-01-1 の追加段（11-28）で決め、.8 の扱いは D-P1-01-2（2027-01-30、凍結の verdict の前）で決める。決定: D-P1-01-1（追加段を含む）/ D-P1-01-2。
- 束の完了条件:
  - ADR-0080 の追補（2026-11）に凍結集合の表（.4）・計測単位 4 系列と読みの規則 3 行（.1）・停止リスト（.3）・凍結後の PR 規則 5 行（.6）が 1 段落ずつあり、閾値と窓は追補の定義でなく dated note の「読み方」として置かれている（基礎率・待ち時間の 1 行ずつは P1-03.9、同じ PR）
  - `scripts/freeze_reading.py`（stdlib）が凍結集合の commit 数（ISO 週・種別別）・新設 mechanism ADR 数・機構節を変える追補数（層別）・`tests/` 純増行数（src / scripts の 2 系列、閾値なし）の 4 系列と「列挙外の tests 変更」（.7）を 1 行で出し、`weekly-analysis.sh` の materials 段（census と同じ場所）で走って weekly-report はその 1 行を転記するだけ（headless セッションは script を実行できない。P2-01 はこの出力を参照する）
  - 「停止リスト」（期日つき残作業の表）が存在し、各行に期日と判断役がある。期日の無いトリガーつき延期は表に入れず、第 5 章の延期行に置く
  - 凍結は script の `freeze candidate` 宣言 + `gate_record` の人間 verdict で記録される（script は判定しない。verdict は定義の後、窓が満ちた週の読みで、凍結の verdict は早くて 2027-05-01（推奨どおりの場合））

##### P1-01.1 凍結の計測単位と読みの規則を決め、毎週読む
- 何を: 計測単位を 4 系列で置く — (i) 凍結集合（.4）を触った commit 数を ISO 週・種別（`fix` / それ以外 = `feat` / `refactor` / `perf` / `docs` / `chore` / prefix 無し）で、(ii) 新設 mechanism ADR 数 / 月、(iii) `## Decision` / Mechanism 節を変える追補、または凍結集合の commit と同じ PR に入る追補の数 / 月（mechanism / instrument / governance に層別して数える。消費計画・Review-when・Decided-by・dated Note は「docs の動き」として報告のみで閾値に入れない）、(iv) `tests/` の純増行数 / 週（`git log --numstat -- tests/`。`tests/*_shell.py` = 凍結集合の .sh を検査する scripts 系列とそれ以外 = src 系列の 2 本に分けて出し、P2-04 / P2-02 / P2-03 / P2-05 の shell テストのこぶを src 系列から分ける。閾値なし、読みだけ）。読みの規則 3 行 — (1) 対象は凍結集合を触った commit、(2) `fix` 以外の type はすべて「動いた」、(3) 凍結後の commit は `fix` 型 + RFC id 必須（.6）— を追補（2026-11）に置き、閾値と窓（D-P1-01-1）は追補の定義でなく dated note の「読み方」に置く。読みは stdlib script `scripts/freeze_reading.py` 1 本が .4 の path 集合で `git log` を引き、`docs/adr/` の見出し grep と合わせて 1 行で出す。`weekly-analysis.sh` の materials 段（census と同じ場所）で走らせ、weekly-report はその 1 行を転記するだけにし（headless セッションは Bash を持たない）、P2-01 の「止まる」の読み（src+scripts+config の feat / fix・改訂 ADR 数・新規 RFC 数を docs-consistency JSON と `## Agent State Diff` に 1 行出す案。本項目に吸収）は同じ出力を参照する。窓が満ちたら script は `freeze candidate` と宣言するだけで、凍結の verdict は人間が `gate_record` に書く（P2-01.5 と同型）。
- 根拠: 実データ（2026-10-10、`git log -- src/` 月別）: 2026-08 40（feat 8 / fix 13 / refactor 13）、2026-09 95（feat 24 / fix 14 / refactor 46 / perf 6）、2026-10（1〜9 日）6（feat 1 / fix 5）。ISO 週別 total / fix 以外: W33 8/2、W34 13/9、W35 13/11、W36 19/17、W37 63/57（simplify sweep）、W38 9/5、W39 10/7、W40 2/0、W41 4/1（`4b85f22` feat = ADR-0113 追補 2）→「fix のみの週」は現時点で連続 1 週も無い。ADR 新設（索引 Date）: 08 月 16 / 09 月 12 / 10 月（1〜9 日）0。ADR en 本文の日付つき Note: 08 月 8 / 09 月 16 / 10 月（1〜9 日）11 行、追補見出し 10 月（1〜9 日）2（ADR-0113）。`core/` は 2026-07-09 以降 90 commit。`docs/adr/0080:125-129`「The definition is deliberately not machine-checkable; drift is watched through the weekly reflection/diagnosis cycle, not a lint gate」。prefix だけでは修理か動いたかを分けられない例: `4b85f22 feat(relevance)`（2026-10-09、RFC-0046 の移行 = 修理だが `feat`）、`271e3fe docs(comments)`（2026-09-12、src 46 ファイル / 72 件を触る `docs:`）。ADR unique 改訂は 2026-08 50 / 09 47 / 10（1〜9 日）12 本（R1-FRZ の実測）— 文書追補を数えると (iii) は 0 にならない。
- 完了条件: 追補（2026-11）に計測単位 4 系列と読みの規則 3 行が 1 段落; `scripts/freeze_reading.py` の出力 1 行が materials 段から weekly-report に 4 週連続で転記される（配線は 10-24 の週（§4.0 の先行列））; 同 script は `fix` 以外の type と commit trailer `Reproduces:`（P1-13.3）の欠落を同じ 1 行で出す; 出力 1 行に `tests/` 純増行数が src / scripts の 2 系列で出て、.6 の規則 (5) に tests の限定 1 行があり、「固定テスト」の集合（表面の literal snapshot・`ignore_imports` 契約・AST 検査・sentinel 検出・egress / 権限の不在テスト）は P1-06 の束完了条件の表で閉じる（P1-06 側。それ以外の P1-08 のテスト追加項目は第 5 章の延期行「触る時だけ・凍結後」）; 窓が満ちた週に script の `freeze candidate` 宣言（P1-03.9 の基礎率を併記）と `gate_record` の人間 verdict（`freeze_verdict=`）が 1 行ずつ読める。
- 規模・整合: S / instrument   出典: CH-41 CP-17 AB-29 OI-20 OI-21 R1-FRZ-02   順序: 配線は 10-24 の週（§4.0 の先行列）、規則の文面は 11-28 の D-P1-01-1 の後に追補（2026-11）へ
- 消費計画: (a) 人間が土曜ゲート Step 0 の briefing 1 行で毎週読む（出力は `weekly-analysis.sh` の materials 段が作り、headless の weekly-report は転記するだけ。読み手の種別は P1-04.16 の 4 値で「人間」） (b) 毎週 1 回の読みで「連続週数が D-P1-01-1 の窓に達したか」だけを見て、達したら candidate 宣言 → 人間 verdict で凍結を決める (c) 凍結 verdict 後は週次をやめ、四半期 T4（ADR-0101）の読みに降ろす。

##### P1-01.2 core commit を repair / instrument / capability でタグ付けする（T4）
- 何を: ADR-0101 D4 の四半期 T4 棚卸し（第 2 回 = 10-17）の記録を読んでから、10-31 の週（§4.0 の先行列）の平日セッションで（10-17 当日には着手しない）git 履歴の全件（2026-08-16 `01075d9` 〜）の `core/` 90 commit を repair / instrument / capability-growth の 3 値で 1 件ずつタグ付けし、`docs/evidence/adr-0080/core-commit-tags.md` に表で残す。08-16 以前（v2.8.0 〜 v2.11.0）は git に無いので、CHANGELOG の節単位（v2.8.0 / v2.9.0 / v2.10.0 / v2.11.0）で 1 行ずつ付けるか対象外と表の冒頭に明記する。`DecisionBackend` seam（ADR-0112）と score4 gate（ADR-0113）が「修理」か「新しい判定機構」かを、この表で初めて記録する。
- 根拠: `git log -- src/contemplative_agent/core/` → 90 件（`--since` 無しでも同数。履歴の起点は `01075d9` 2026-08-16 で、「2026-07-09 以降」は実際には全件）、上位 `skill_selection.py` 18 / `llm/__init__.py` 18 / `domain.py` 16; v2.8.0（2026-07-09）〜 v2.11.0（08-20）の core 変更は CHANGELOG にしか無い; `docs/adr/0080:178-182`「Bounded mechanism work undertaken to reach self-regulation … is in-scope repair … not capability growth」; `CLAUDE.md:80`「機構層は『修理か、能力動機の拡大か』」— この審査が commit 単位で記録された例は無い。
- 完了条件: 表に 90 行があり 3 値のいずれかが付き、08-16 以前の扱い（CHANGELOG 節 4 行か対象外）が冒頭に 1 行、capability-growth の件数と理由が T4 の記録に 1 行ある。以後は再タグ付けしない — 凍結後の commit は `fix` 型 + RFC id 必須（.6、追補（2026-11）の読みの規則 (3)）で alignment が RFC の `alignment:` 欄（P1-02.4）に記録されるため、.1 の種別読みで代替できる。
- 規模・整合: M / neutral（審査記録の表 — 読み値を出す計器ではない）   出典: CP-17   順序: 10-31 の週（§4.0 の先行列）

##### P1-01.3 「停止リスト」（止めるために残っている作業）を 1 表にする
- 何を: ADR-0080 の追補（2026-11）（P1-03.8）に 1 段落として表を置く（`docs/CYCLES.md` の North star 節からは参照のみ）: 行 = 削除待ちコード（旧 relevance 経路、RFC-0046 再開条件 2026-10-15）、未決 Review-when（ADR-0111 の `revise` 案 B と insight 退役判定、ADR-0112:239 の「Deferred — 未決」）、blocked RFC（0042 / 0047 / 0048）、凍結前の最後の動かす PR（P0-02.2、P1-06 の .10 / .4(a) — 定義の前に走ってよい修理・登録簿）、最後の構造 PR（P1-06.3 の改名 PR）、2027-Q1 に凍結集合を触る src の機構変更（.9、D-P1-01-1 の追加段 B を前提、決定前: P2-07.1・P2-06.2・P1-12.1 PR-C・P1-07.7 / .8）; 列 = 期日・判断役・成立したら何が消えるか。表が空になった週が .1 の凍結判定の唯一の開始点（最終行の merge 週と一致する。推奨どおり（D-P1-01-1 の追加段 B・D-P2-07-1 A）なら停止リストの最終行は P2-07.1 / P2-06.2 で、verdict は早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8（2027-01-30 の週）の遅い方 + 8 週で、早くて 2027-04-03）。期日の無いトリガーつき延期（「触る時だけ・凍結後」）は表に入れず、第 5 章の延期行に置く。
- 根拠: `rfcs/0046:243`「古いコードは消していない（呼び手がないだけ）」、`:259`「再開条件: 10-14 以降のファイルで両方 0」; `docs/adr/0111:157-168` Review-when（3 ゲートで週 ~35 件に戻れば「freeze the store and retire insight, or redesign」、`revise` 案 B は「decided then」）; `docs/adr/0112:239`「Deferred — 未決, revisit at the enforcement reading」; `CLAUDE.md:73` は未完成の判定を書くが残作業は書かない。
- 完了条件: 追補（2026-11）に表が 1 段落あり各行に期日と判断役がある; weekly-gate の手順に「表の行を 1 つ閉じる or 期日を更新する」が 1 行ある（SKILL.md の変更は追補（2026-11）と同 PR）; 行数が 0 になった週が記録される。
- 規模・整合: S / neutral   出典: CP-18

##### P1-01.4 凍結集合（frozen set）を 1 表で定義する
- 何を: 追補（2026-11）（.1 の判定文と同じ節）に凍結集合の表を置く — 行 = `src/`、`config/launchd/`、`config/prompts/`、`config/domain.json`、launchd / weekly チェーンが起動する `scripts/*.sh`（`weekly-pipeline.sh` / `pipeline_watchdog.sh` / `rotate-log.sh` / `backup-runtime.sh`）とそれらが呼ぶ `scripts/*.py` のうち本番経路（watchdog / rotate / backup / `state_invariant_check`）、`.claude/skills/weekly-report/**`（SKILL.md + `references/diagnosis.md` — 種別: 機構（D-P2-02-1 = A / C のとき）、B なら行ごと対象外）; 列 = 種別（機構 / 計器）・読みに入るか・撤去が「動いた」に入るか（計器の削除 commit は入れない）。`scripts/freeze_reading.py` はこの表の path 集合で `git log` を引き、P2-01 側は同じ出力を使う。D-P1-06-1 で A を採る場合、`_bootstrap.py` を import する script は自動的にこの表に入る。表の注に 1 句: `weekly-gate/SKILL.md`・`.claude/verify.*`・CLAUDE.md は人間ゲート手順・検査面・文書なので入れない（CLAUDE.md は無人セッションに読み込まれるが、その変更は P2-02.7 の `instr_sha12` 行で追う）。
- 根拠: .1 の旧案は `src/` のみを数えたが機構は外にもある — `config/launchd/*.plist` 8 本が起動するのは `scripts/*.sh` 8 本で、weekly チェーンは `scripts/` の 14 ファイルを呼ぶ（`weekly-pipeline.sh` / `weekly-analysis.sh` の grep）; `scripts/` は .py 33 本 18,724 行 + .sh 8 本 2,585 行（src は .py 96 本 37,562 行）; commit は `scripts/` 2026-08 29 / 09 75 / 10 4、v2.12.0（`950f190`）以降 +9,152 / −1,732 行・43 commit（src は +4,219 / −634・25 commit）; `7a152b0 feat(census)`（2026-10-03、9 ファイル）は `scripts/_census_registry.py` / `weekly-analysis.sh` / `config/prompts/weekly-analysis.md` / ADR-0107 / tests を触り `src/` は触っていないので、`src/` だけの読みには現れない; 無人チェーン唯一の LLM 段の指示書 `.claude/skills/weekly-report/`（`weekly-pipeline.sh:352` が `/weekly-report` で起動）は 2026-08-16 以降 12 commit で、旧表に無い。
- 完了条件: 追補（2026-11）に表が 1 段落; `freeze_reading.py` の path 集合が表と一致する（test 1 本。`.claude/skills/weekly-report/` の正負 1 ケースを含む）; 計器 script の削除 commit が (i) の「動いた」に数えられない（同 test の negative case）。
- 規模・整合: S / neutral   出典: R1-FRZ-01

##### P1-01.6 凍結後の PR 受入規則 5 行を追補（2026-11）・CLAUDE.md・skill に同期する
- 何を: 追補（2026-11）（.1 と同じ追補）に「凍結後の PR 規則」を 5 行で置き、CLAUDE.md 開発原則と `weekly-gate` skill・harness 側 task-triage skill（P2-03）に同期する — (1) 凍結集合（.4）を触る PR は `fix:` 型で RFC id を持つ（RFC の `alignment:` は repair）、(2) 変更前に再現する証拠（監査ログの行か失敗するテスト、ADR-0075 の replay）を commit trailer `Reproduces:` に 1 行（語彙の正本は P1-13.3。直 push が運用の形で PR 本文は無いことが多い）、(3) 改名・移動・新 module・新 env キー・新 CLI フラグ・新 launchd label は含めない（`tests/test_surface_snapshot.py`（P1-06.2）の literal snapshot が赤になる変更は ADR 追補と同 PR のみ）、(4) `docs:` / `refactor:` 型で凍結集合を触らない（コメント修正は fix PR に同梱）、(5) `tests/` の変更は再現テスト・snapshot 更新・fix PR が pin を外す既存テストの書き換え（項目の完了条件に列挙されたものに限る）のみ（.1 の (iv) と同じ集合）。計器の合成 fixture テスト（P2-04 の ❌ 再現、`*_shell.py`）は計器側の再現テストとして許容する。機械検査は snapshot テスト + `freeze_reading.py`（`fix` 以外の type と `Reproduces:` 欠落を同じ 1 行で出す。列挙外の `tests/` 変更は .7）の 2 つで足り、新しい hook は置かない。
- 根拠: `CLAUDE.md:73`「機構層（コード）= 止まるのが完成。変更は修理のみ」、`:80`「機構層は『修理か、能力動機の拡大か』」は ADR / RFC の審査文で PR / commit の形式要件が無い; `.claude/verify.sh`（format / lint / type / arch / markdown / deps / test）と `verify.yml` は commit の種別も RFC 参照も読まない; `.claude/skills/weekly-gate/SKILL.md:3`「code 修理の適用（ADR-0098 で廃止。修理は task-triage loop の担当）」— 何を触ってよいかの規則は loop 側にも無い; 2026-10 の src commit 6 件は同じ RFC-0046 の作業が `fix` 4 件と `feat` 1 件（`4b85f22`）に分かれ、`fix(register)`（`737133e`、2026-10-08）は `--name` 必須化という CLI 表面の変更。
- 完了条件: 追補（2026-11）に 5 行; `CLAUDE.md` と weekly-gate SKILL.md の diff が追補（2026-11）と同 commit; `freeze_reading.py` が凍結後の `fix` 以外の type と `Reproduces:` 欠落を同じ 1 行で出す（test 1 本）; snapshot テストは P1-06 の契約固定 PR（`tests/test_surface_snapshot.py`、P1-06 束完了条件）に依る。
- 規模・整合: S / neutral（人間の言葉は RFC と土曜ゲートに残る — ゲートの溶解ではない）   出典: R1-FRZ-04

##### P1-01.7 既存テストの列挙と `tests/` 変更の照合（`freeze_reading.py`）
- 何を: 挙動を変える項目（P0-02.2 / .6 / .9、P0-03.2 / .3、P0-04.1 / .5、P1-06.1 / .3、P1-12.3、P3-04.1、P3-05.9 / .17）が完了条件の文中に書く定型句「書き換える既存テスト: `tests/<file>::<test>`」（無ければ「既存テストは不変」）を列挙の正本とし、`scripts/freeze_reading.py`（.1）が凍結後の commit で変更された `tests/` のファイルをその列挙と突き合わせ、列挙外の `tests/` 変更（fix PR が足す新規の再現テスト・`tests/test_surface_snapshot.py` の snapshot 更新・`*_shell.py` の計器側 fixture テスト（.6 (5)）は除く）を「列挙外の tests 変更: N 件（path）」の 1 行で出す（読みだけ、閾値なし）。列挙の読み元は `docs/plans/roadmap-2026-10/ROADMAP.md`（P2-01.10 が採択日つきで commit する全文の凍結版）で、定型句を grep する。
- 根拠: 草案の完了条件は新規テストしか書かず、既存テストが現行挙動を pin している例が 4 件 — `tests/test_constitution.py:204 test_forbidden_pattern_returns_string`（P0-04.5）、`tests/test_snapshot.py:152 test_prune_chronological_across_commands`（P3-04.1）、`tests/test_sync_research_data_shell.py:42 _excludes()`（P0-03.2 / .3）、`tests/conftest.py:135`（P0-02.9、autouse fixture が `reset_relevance_shadow` を import）; .6 の規則 (5) は旧文面ではこれらの書き換えを凍結後に禁じ、PR は「新規テスト緑・既存テスト赤」で止まるか、実装側が独断で既存テストを消す / 弱める（人間の言葉が残らない）。
- 完了条件: 上記 13 項目の完了条件に定型句がある（本ロードマップ側、各束）; `freeze_reading.py` の出力に「列挙外の tests 変更」の 1 行があり、合成 fixture（列挙内 1 件・列挙外 1 件・`*_shell.py` 1 件）で件数が 1 になる test 1 本。
- 規模・整合: S / repair   出典: R2-IMPL-01   依存: P1-01.1（script）、P1-01.6（規則 (5) の文面）、P2-01.10（列挙の読み元 `docs/plans/roadmap-2026-10/ROADMAP.md`）

##### P1-01.8 凍結後の生成 / 埋め込みモデル交代を装置境界として扱う（D-P1-01-2）
- 何を: 追補（2026-11）（.6 と同じ追補）に「凍結後のモデル交代」の段落を 1 つ置く — 交代は装置境界として扱い、扱い（A 固定 / B 窓を数え直す / C regime 行）は D-P1-01-2（2027-01-30）が決める、まで書き、決定値は `gate_record` と（A なら）ADR-0069 Trigger 1（`:131`）の日付つき停止注記に置く。どれを採っても `scripts/freeze_reading.py`（.1）は `OLLAMA_MODEL` / `OLLAMA_EMBEDDING_MODEL` / `_DEFAULT_*_MODEL` を触る commit を `fix` / 違反とは別の種別 `regime` で出す。強いられた交代への備えとして、重み blob（gemma 9.6 GB + nomic）を digest つきで手元保管するか DATACARD に「not archived」と書くかを同じ決定で選ぶ。
- 根拠: .6 (3) は新しい env キーを禁じるだけで、既存の `OLLAMA_MODEL` の値の変更（`core/llm/backend.py:27` `_DEFAULT_OLLAMA_MODEL = "gemma4:e4b"`）は fix とも違反とも読めない; `docs/adr/0069:128-140` は交代を前向きの trigger（`:131` より良いローカルモデル、`:136` ハードウェア変更）として残し、`docs/adr/0080:80-82`「a finished observation instrument」と衝突する; `docs/adr/0090:127-130` は生成モデルを較正の契約に含め `OLLAMA_MODEL` の変更で ±0.13 の床が無効になると書く（研究層 Q1 = `0080:62-68` の系列が境界をまたいで比べられない）; 9.6 GB は `docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md:17`。
- 完了条件: 追補（2026-11）に段落 1 つ; D-P1-01-2 の decision が `gate_record` に 1 行; A の場合 ADR-0069 に日付つき注記; `freeze_reading.py` が上記 3 種の名前を触る合成 commit を `regime` と出す test 1 本; DATACARD に blob 保管の有無が 1 行。
- 規模・整合: S / neutral（決定の明文化。消費計画は書かない — 計器ではない）   出典: R3-MDL-02   依存: P1-01.6、P3-02.1（境界表）、P1-07.11（model-swap runbook）、D-P1-01-2

##### P1-01.9 2027-Q1 に凍結集合を触る項目と凍結窓を両立させる（D-P1-01-1 の追加段）
- 何を: D-P1-01-1（11-28）の追加段で、2027-Q1 に凍結集合（.4）を触る項目の扱いを決める。推奨 B を前提（決定前）に、.4 の表の計器行（watchdog の検査行・census の Entry）に「読みに入らない」の印を付け、src の機構変更（P2-07.1・P2-06.2・P1-12.1 PR-C・P1-07.7 / .8）だけを停止リスト（.3）に期日・判断役つきの行として載せる。開始点は停止リスト最終行の merge 週に動くので、本束の期限・順序と D-P1-01-1 の verdict の日付はこの最終行から計算する（推奨どおり（D-P1-01-1 の追加段 B・D-P2-07-1 A）なら停止リストの最終行は P2-07.1 / P2-06.2 で、verdict は早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8（2027-01-30 の週）の遅い方 + 8 週で、早くて 2027-04-03）。
- 根拠: 読みの規則 (2)「`fix` 以外の type はすべて動いた」（.1）と .6 (1)(3) のもとで、2027-Q1 の実装（P2-04 の watchdog 検査行・sync の管理下化、P2-02 / P2-03 の `weekly-pipeline.sh`、P2-07.1 の店に触る無人段、P2-06.2 の `.meta.json` 印字、P1-12.1 PR-C の `approver`、P1-07.7 / .8 の decision 面）は `feat` 型で凍結集合を触り、連続週数を毎回 0 に戻す; 停止リスト（.3）の行は削除待ちコード・未決 Review-when・blocked RFC・P0-02.2 / P1-06 の .10 / .4(a)・P1-06.3 だけで、.1 の (iv) も shell テストのこぶしか想定していない。
- 完了条件: 停止リストに 2027-Q1 の凍結集合項目の行（期日・判断役）がある（推奨 B なら src の 5 項目）、または .4 の表に除外の列がある; 本束の期限・順序と D-P1-01-1 の verdict の日付が停止リスト最終行の日付から計算されている。
- 規模・整合: S / neutral   出典: R3-TIME-02   依存: D-P1-01-1（追加段）、P1-01.3、P1-01.4、P1-06（構造 PR の週）、P1-07.7 / .8（2027-01-30 の週）


**依存**
- P0-02.2（旧 relevance 経路の削除、10-17）— 停止リストの最初の行 = 「凍結前の最後の動かす PR」の 1 つ
- P0-01（10-10 ゲート: RFC-0042 / 0048 の読み）— 停止リストの blocked 行
- P1-02.4（RFC `alignment:` 欄）— .2 の後継計器、.6 の規則 (1)
- P1-03.8（ADR-0080 の追補（2026-11）の受け皿）— .1 / .3 / .4 / .6 / .8 の文面と P1-03.9 の基礎率行はここで 1 PR（11-30〜12-04 に草案、12-05 の D-P2-07-1 の後に 12-07〜11 に merge、CLAUDE.md §北極星と同 commit）
- P1-04（ADR-0101 T4 第 2 回 = 10-17）— .2 はその記録を読んでから; P1-04.16 の読み手 4 値を .1 の消費計画が使う
- P1-06（最後の構造窓）— .10 / .4(a) は定義前に走ってよい「凍結前の最後の動かす PR」; 契約固定 PR（`tests/test_surface_snapshot.py`・固定テストの表）と .3 改名 PR は定義の後で、.3 の merge 週 = 停止リストが空になる週 = 開始点
- `weekly-analysis.sh` の materials 段（census と同じ場所）— .1 / .7 の配線先（.1 は 10-24 の週、§4.0 の先行列）
- P2-01.10（ロードマップの repo 内置き場 `docs/plans/roadmap-2026-10/`）— .7 の列挙の読み元 `ROADMAP.md`
- D-P1-06-1（scripts の鏡）— A なら `_bootstrap.py` を import する script が .4 の表に入る
- D-P2-02-1（headless は機構層か、11-28）— .4 の `.claude/skills/weekly-report/**` 行の種別（A / C なら機構、B なら対象外）
- P2-02.7（`chain_start` の `instr_sha12`）— .4 の注で CLAUDE.md の変更を追う先
- P3-02.1（装置の境界表）、P1-07.11（model-swap runbook）、D-P1-01-2（2027-01-30）— .8 の `regime` 行の置き場と扱い
- P1-06（構造 PR 4 本の週 2027-01-16 / 01-23 / 01-30 / 02-06）、P1-07.7 / .8（2027-01-30 の週）、P2-07.1 / P2-06.2（2027-02-27 の着手の後）— 停止リスト最終行の日付と .9 の計算
- → 参照元: P2-01（北極星の読み値の機械化 — 「止まる」の読みは .1 の出力を参照）、P2-03（harness 側 task-triage skill — .6 の規則の同期先）、P1-08（テスト追加項目の第 5 章延期行「触る時だけ・凍結後」— .1 の固定テスト集合の外側）、P1-06（.1 の判定が構造窓の終わりを定義し、.1 / .6 の機械検査はその snapshot）、P2-07.1・P2-06.2・P1-12.1 PR-C・P1-07.7 / .8（停止リストに期日つきの行を持つ — D-P1-01-1 の追加段 B を前提、決定前、.9）、P1-03.7（`## Layer` が .1 の (ii)(iii) の層別の材料）、P1-13.3（commit trailer の語彙 `Reproduces:` の正本。12-12 の週で .6 より後なので、.6 の規則 (2) は現行の語 `Reproduces:` で先に書き、P1-13.3 はそれを正本として採る）


#### P1-02 RFC 台帳の健全化と blocked RFC の終端
- 狙い: `rfcs/README.md:3-5`「state は各ファイルの frontmatter が唯一の正本」なのに本文 `## Status` が 31/49 本で別の state を言い（本ブリーフ §2 の「insight 停止中」誤読の原因）、frontmatter の様式が 2 形式、索引に state 列が無く、決定待ちが本文の照合節に散っている。公開台帳（ADR-0095）の価値は「却下理由ごと残る」ことで、読み手が古い状態文を正と誤読する費用を機械で消す。blocked 7 本のうち外部待ち型（0040）と 1 語で解ける型（0047）を終端する。
- 期限・順序: 着手 2026-12-26 の土曜ゲート（§4.0）。期限 2027-01（.6 は D-P1-02-2 = 2027-01-09 の後）。.1（Status 整合）と .2（frontmatter 正規化）は test で固定するので先、.3 / .4（索引生成）はその上。.5 は D-P1-02-1（2026-10-24 の土曜ゲート）で決め、withdraw（frontmatter の `state:` 1 行）は 10-31 の週（§4.0 の先行列）、照合先の移し（ADR-0112 Review-when・evidence README）と arm K5 の撤去は 12-26 の着手週に行う。.6 の終端は D-P1-02-2（2027-01-09 の土曜ゲート）の後で、RFC-0047 の終端はこの項目だけが持つ（P1-15.1 の置き場と D-P1-04-3 A の再検討はここを引く）。P0-01（10-10 の 0042 / 0023 / 0048 の読み）の結果を .2 の `decide_by` に写す。RFC-0011 の Status 節は P1-04.3（10-17 の着手）が先に直し、.1 の test がそれを固定する。決定: D-P1-02-1 / D-P1-02-2。
- 束の完了条件:
  - `tests/test_rfc_frontmatter.py` が 49 本で green（state 語のみ / `state_since` 必須 / blocked に `decide_by` / accepted・done に `admitted-by` / 本文 `## Status` 先頭語 = frontmatter か節が無い）
  - `rfcs/README.md` の表が `scripts/rfc_index.py` の出力と一致（test）し、state 列と awaiting-owner 節がある
  - RFC-0040 の `state:` が終端語（withdrawn）になっている（D-P1-02-1 = 2026-10-24 の後、10-31 の週。arm K5 の撤去は 12-26 の着手週）; RFC-0047 は D-P1-02-2（2027-01-09）の後に .6 だけが done にする（P1-15 側は昇格 ADR を完了条件に持たない）

##### P1-02.1 本文 `## Status` の stale を解消し、test で固定する
- 何を: 本文 `## Status` を (1)「決定の記録」節に改名して state 語を書かない、または (2) frontmatter から写した 1 行に置き換える（規約側は harness の rfc-writer、本 repo は test で守る）。先に `rfcs/0042:137-139`「実装は未着手、insight 週次は停止中」・`:64`「2026-09-19 から停止中」、`rfcs/0041:97`「停止は継続中」、`rfcs/0011:113-121`（Status blocked / Next action 09-03 待ち。P1-04.3 が 10-17 の着手で先に直していれば確認だけ）の 4 箇所を現状に直す。
- 根拠: 機械比較（本統合の script、先頭語比較）: 49 本中 `## Status` 節あり 42、うち frontmatter と不一致 31（0001〜0011 / 0014〜0016 / 0021 / 0023 / 0024 / 0027 / 0028 / 0031〜0035 / 0041〜0044 / 0046〜0048。AB-01 の「20 本」は誤りで、同項目の列挙自体が 30 本、さらに 0010 `done` vs `in_progress` が漏れ）; `rfcs/0042:176`「項目 6 — insight 週次スケジュールを再開（著者指示、2026-09-19）」、`:204`「2026-10-03 08:00 の insight run: 候補 0 件」; `rfcs/0011:2` `state: done 2026-09-05` vs `:113-116` blocked。
- 完了条件: `tests/test_rfc_frontmatter.py::test_body_status_matches_frontmatter` が 49 本で green; `grep -n "停止中" rfcs/0041*.md rfcs/0042*.md` が現状と矛盾する行を返さない。
- 規模・整合: S / repair   出典: AB-01 DC-47 OI-47 VL-19

##### P1-02.2 frontmatter を 1 形式に正規化し、blocked に `decide_by` / `next_check` を足す
- 何を: `state:`（語のみ）/ `state_since:`（必須）/ `review-when:`（終端以外は必須）とし、blocked には `decide_by:`（この日までに成立しなければ withdraw か問いを小さくする）と `next_check:`（次回照合日。それ以前は triage が追記も照合もしない）を必須にして test で検査する。同じ正規化で admission の欄 `admitted-by: <人名> <date>` と `decided-by:` を足し、`rfcs/README.md` に本体要件として明記する（規約本文は harness の rfc-writer、欄の存在は本体の検査対象）。既存の暦待ち dead-band 節は各 1 行に畳む。RFC-0044 の review-when に「RFC-0048 の注入 ablation で skill 注入に効果があり、catalog を絞った後も幻覚率 5% 超」の再燃条件を 1 行足す。
- 根拠: 実測: `state:` に日付を含むのが 46/49（例外 0012 / 0013 / 0020）、`state_since` 無し 15（0031〜0037 / 0041〜0048）、`review-when` 無し 22、`decide_by` 0; `rfcs/0023` は `state: blocked 2026-09-23` + `state_since: 2026-09-04` で経過日数が二重; `## … triage 照合` 見出し 158（0012: 17、0006: 14、0023: 10 — 照合先は 2026-10-31 / withdraw まで鳴らない暦条件）; `rfcs/0047:47`「stuck: n が 14 日で満ちない face は延長でなく決める」が台帳様式に無い; `rfcs/0044:3` review-when はモデル / prompt 変更のみ、`:93` / `:105` に同日の done → accepted → done; AKC `0028:43`「The current claim ledgers record a task's origin but not who admitted it … not yet observable mechanically」、frontmatter の `admitted-by` は 0 件。
- 完了条件: 49 本が 1 形式（test）; blocked 7 本に `decide_by` と `next_check`; `state: accepted|done` の RFC 全件に `admitted-by` があり `tests/test_rfc_frontmatter.py` が検査する; `grep -c 'triage 照合' rfcs/0012*.md` が `next_check` 以前に増えない（triage skill は harness 側で P2-03 が後から合わせる。本 repo は欄と test まで）。
- 規模・整合: S / repair   出典: AB-02 AB-38 AB-06 AB-43 GO-14

##### P1-02.3 索引を frontmatter から生成し、state 列と claims.py 無し環境の読み方を置く
- 何を: stdlib script `scripts/rfc_index.py` が `rfcs/README.md` の表（#, title, state, since, decide_by, review-when 有無, 再開条件 1 行）を生成し、weekly-gate Step 6d の commit 前に走らせる。test は「生成結果 = commit 済み」。`CLAUDE.md:150-151` の claims.py 節に「harness repo が無い環境では `grep -h '^state:' rfcs/*.md`」の 1 行を足す。
- 根拠: `rfcs/README.md:13` の表は `| # | Title |` の 2 列; state 集計（blocked 7 / done 25 / withdrawn 11 / obsoleted 3 / resolved 3 — DC-10 の「withdrawn 12」は誤り）は README から見えない; `CLAUDE.md:150-151`「`python3 ~/.claude/scripts/claims.py ready` …」（repo 外）; `docs/adr/README.md` は状態列を持つのに RFC 側は無い。
- 完了条件: `tests/test_rfc_frontmatter.py::test_index_is_generated` green; README の表に state 列; 第三者が README だけで open 7 本を読める。
- 規模・整合: S / repair   出典: AB-03 DC-10

##### P1-02.4 決定待ち（awaiting-owner）と `alignment:` を台帳で集計する
- 何を: RFC frontmatter に `decision_needed:`（1 行の問い）と `alignment: repair | instrument | capability-growth | value-steering-risk`（本ブリーフと同語彙 = ADR-0080 の審査軸）を足し、.3 の生成器に「awaiting-owner」節（`decision_needed:` と ADR 本文の `Deferred — 未決` grep）と alignment の集計を加える。open RFC 全件に alignment を付け、capability-growth が open のままなら理由を本文に書く。
- 根拠: 決定待ち 15 件が RFC の照合節・ADR の Alternatives・CHANGELOG に散在（0012 の 10-31 起動、0023 / 0042 / 0048 の 10-10、0046 の 10-15、0047 の 1 語、0040 の withdraw、ADR-0111 案 B、`docs/adr/0112:239`「Deferred — 未決, revisit at the enforcement reading」、ADR-0080 L5 ほか）; RFC-0043〜0048 は 09-19〜09-26 の 8 日間に起票され、修理（0044 / 0046）と方法論・将来像（0040 / 0047）が同じ速度で流れたが「修理 / 能力拡大」欄は無い（0047 は Motivation で自己申告のみ）; `CLAUDE.md:80` の審査基準は起票様式に無い。
- 完了条件: 生成表の awaiting-owner 節に上記 15 件（残存分）が出る; open RFC 全件に `alignment:`; `grep -c 'alignment: capability-growth' rfcs/*.md` が digest に出る。
- 規模・整合: S / neutral（台帳の欄と集計 — 読み値を出す計器ではない）   出典: AB-37 AB-44

##### P1-02.5 RFC-0040（Jev / ローカル判断モデル）を終端する
- 何を: D-P1-02-1 で withdraw を決め、候補モデルの照合先を ADR-0112 Review-when（既に `docs/adr/0112:200-202`「Ollama gains the ability to serve custom-head decision models, or Jev's weights are released」を持つ）と `docs/evidence/rfc-0043` / `rfc-0045` の README に移す。harness 側の arm K5（`scripts/relevance_arm_replay.py`、`tests/test_relevance_arm_replay.py`、`tests/test_jev_arm.py`）は RFC-0043 と同じく撤去し、SHA と復元手順を evidence に 1 行残す。再入場条件は「確率の値そのものを消費する機構が ADR で立つ」の 1 つ。
- 根拠: `rfcs/0040:281-297` 第 4 ラウンド判定（候補 3 件とも dev 不通過、holdout 0 回消費）、JevK5 は holdout 合格・不採用（16 GB 同居不可 / Ollama 経由で AUC 低下）; frontmatter `review-when`（`:6`）は外部条件 8 つ、本文 484 行、照合節 5; 上流待ち型の blocked は `6ce54d9`（2026-08-30、blocked 5 件を withdrawn）で既に畳んだ先例; RFC-0046 Motivation「モデルを替えずに生成形を替えるのが唯一の当たり」。
- 完了条件: `rfcs/0040` の `state: withdrawn`（10-31 の週）; ADR-0112 Review-when に JevK5 の Ollama 版差条件 1 行; `ls scripts/relevance_arm_replay.py tests/test_jev_arm.py` が無く evidence に復元 SHA（12-26 の着手週）。
- 規模・整合: S / neutral（能力拡大の予約を閉じる）   出典: AB-09 LP-30   順序: withdraw の frontmatter 1 行は 10-31 の週（§4.0 の先行列、10-24 の D-P1-02-1 の後）、arm K5 の撤去と照合先の移しは 12-26 の着手週

##### P1-02.6 RFC-0047（face 改善ループ）の昇格先を決めて終端する
- 何を: skill selection face を「retire（RFC-0044 第 1 段で修理済み）」の 1 語で閉じ、review-when「2 face が enforce か retire に決着」を成立させる。昇格先は D-P1-02-2（ADR 1 本か、`docs/CYCLES.md` #6 への 1 段落 + `docs/evidence/rfc-0047/`）。RFC-0047 の終端（done）はこの項目だけが持ち、P1-15.1 の face 台帳 3 列・label manifest の pin・Consequences の教訓の置き場は D-P1-02-2 が決めた昇格先、D-P1-04-3 A（Face A の相関証明）の再検討もこの終端の後とする。
- 根拠: `rfcs/0047:3` review-when「ループの型を ADR + docs/CYCLES.md #5/#6 へ昇格し、この RFC は done」; `:88`「ループ自体の停止条件: 全 face が『乖離なし』か『未計測・着手しない』になったらこのループを溶解する」（同行は機構層の完成条件 = ADR-0080 の 08-26 追補 §A と同型と書く）; `:47` stuck 14 日規律; face 台帳 7 行のうち 4 行が未計測 / 止まった / 固定（AB-16）。
- 完了条件: `rfcs/0047` `state: done`; 溶解条件が CYCLES.md（または ADR）に 1 段落で残る。
- 規模・整合: S / neutral   出典: AB-16 R3-ADR Merge-08


**依存**
- P0-01（10-10 ゲート: 0042 / 0023 / 0048 の読み）— .2 の `decide_by` 初期値
- P1-03（ADR 台帳: `Deferred — 未決` の語彙、graph の RFC ノード）— .4 の grep 対象と生成器の同居
- P1-15（relevance face の較正）— .6 の relevance face の決着
- → 参照元: P2-03（私的ハーネス: rfc-writer skill・claims.py — .1 / .2 の規約側。本 repo は欄と test までで先に入る）、P1-04.3（RFC-0011 の Status 節を先に直す — .1 の test が固定する）、P1-01（`alignment:` 欄 = 凍結後の規則 (1) と .2 の後継計器、.4 の集計の読み手）、P2-03（task-triage skill が .2 の `next_check` を尊重する — harness 側）、P1-03.5（RFC 型ノードは .3 の生成器と同居）、P1-15.1（face 台帳の置き場は .6 の昇格先）、P1-04（D-P1-04-3 A の再検討は .6 の終端の後）


#### P1-03 ADR 台帳の機械追跡（追補・Note・索引・Review-when）
- 狙い: ADR は「判断の記録」で、北極星の「mechanism-layer ADRs approach zero」（`docs/adr/0080:53`）は ADR 数が機構の動きの尺度であることを前提にする。しかし実態は日付つき追補（16 本に `## Amendment` 見出し、ADR-0062 は本文に "amendment" 42 回）と Note（en 本文 36 行 / 18 本、うち 10 月 11 行）で決定が動き、Status / 索引 / graph はそれを写さない（0043 の seed floor は Note で「superseded」なのに Status は `accepted`）。README 規約（`:193`「never overwrite」、`:197` `/sync-context`）も実態と違う。語彙と生成器を決め、5 面（en / ja 本文、en / ja 索引、graph）の同期を「本文 1 ファイル + script」にする。
- 期限・順序: 着手 2026-11-28 の土曜ゲート（§4.0、追補（2026-11））と 2027-01-30 の土曜ゲート（.2 / .3）。期限 2027-Q1。.1（語彙・規約、D-P1-03-1 / D-P1-03-2 = 2027-01-09 の土曜ゲート、同じ回。それまでは推奨 A の 3 条件を暫定基準として 10-17 から decisions.md の記録規則に置く = .11、P2-01.10 の decisions.md に同乗）→ .2 / .3（検査と手修正、2027-01-30 の週）→ .4（Review-when 遡及 — 10-17 の T4 記録（P1-04.1）を読んでから、11-28 の着手（11-30 以降の平日セッション））→ .5（生成器、語彙確定後。PR-A → PR-B → PR-C。PR-A は `[AKC: …]` タグ列の扱いを決め、P1-13.7 の写像の書き直しは PR-B より前）。.6 / .7 は 11-28 の着手（11-30 以降の平日）に独立で出せる（.7 は `## Decided by` と `## Layer` を 1 PR、凍結窓の開始前）。.8 の追補（2026-11）は 11-30〜12-04 に段落の草案（P2-07.5 は A / B の両文）を含めて PR を出して 12-05 のゲートに提示し、12-05 の D-P2-07-1 の後に採った方の文で 1 本 merge（12-07〜11）; 追補（2026-12）は 12-19 の D-P4-01-1 の後の PR（12-21〜25）。.9（基礎率・待ち時間の行）は追補（2026-11）と同じ PR。決定: D-P1-03-1 / D-P1-03-2。
- 束の完了条件:
  - `docs/adr/README.md` の Guidelines が追補の許容範囲・粒度 3 条件・`revised-by` 語彙を定義し、`/sync-context` 参照が無い
  - `tests/test_adr_status_consistency.py` が「Amendment 見出し ⇔ Status 尾部 `amended`」「本文 `Note (date, revised by ADR-X)` ⇔ X への typed edge」「0067 ↔ 0070 の双方向」を検査し 113 本で green
  - `scripts/adr_index.py` の出力 = commit 済みの索引 2 面 + graph の ADR ノード（test）
  - accepted な ADR 全件が `## Review-when` か「期限なし（理由）」を持ち、`scripts/docs_consistency_scan.py` が欠落 0 を報告
  - ADR-0080 に日付形の `## Amendment (YYYY-MM-DD) — <題>` 見出しが追補（2026-11）/ 追補（2026-12）の 2 本あり、各 commit に CLAUDE.md §北極星の diff が含まれ、ロードマップ本文と decisions.md で `grep -cE '追補 [CD]'` = 0（.8）
  - ADR ≥ 0114 が `## Decided by` と `## Layer` を持つ（test、.7）

##### P1-03.1 追補・Note・新 ADR の境界と粒度を README 規約に書く
- 何を: `docs/adr/README.md:193`「Changes to existing ADRs are made via a new ADR … (never overwrite)」を書き換える — 同じ決定の範囲内の数値・閾値・運用手順の更新は `## Amendment (date)` + Status 尾部 `(amended …)`、決定の反転・他 ADR の前提変更・本番の外向き挙動の変更は新 ADR か partial supersede（D-P1-03-1）。`:195` の粒度基準を「可逆性が低い / 他 ADR の前提を変える / 本番の外向き挙動を変える」の 3 条件にし、該当しない変更は RFC done + CHANGELOG で終える。ADR-0113 追補 1（fail-closed 化）/ 2 をその基準で分類した注記を 0113 に 1 行。Guidelines に関係語と `(amended …)` 尾部の併記形を 1 行で定義する（例 `accepted (amended 2026-10-07, 2026-10-09, 2026-10-17) — partially-supersedes ADR-0112 (D2 kill switch, D5 skill-selection shadow retired)`。`docs/adr/README.md:174-181` の語彙は関係語か尾部のどちらか一方の形しか無く、.2 の test は 0074 / 0085 のように `partially-superseded-by` が頭にある Status にも尾部を要求する）。
- 根拠: `## Amendment` 見出しを持つ en ADR は 16 本（0007 / 0018 / 0042 / 0046 / 0053 / 0068 / 0074 / 0080 / 0081 / 0085 / 0086 / 0087 / 0089 ×5 / 0090 / 0095 / 0113 ×2）、0106 は見出し無しの太字 `**D3 amendment (date, RFC-…)**` ×3（`:73` / `:87` / `:100`）— 様式が 3 通り; ADR-0062 本文 "amendment" 42 回; ADR-0080 追補（`:144` 以降）は「dated, additive amendment, not a superseding ADR」と自ら形式を正当化; 小粒 ADR の例 0073（view seed 5 本の削除）/ 0059 / 0035（AB-35）; 113 本の平均 194 行・最大 1,147 行（0089）。
- 完了条件: README の Guidelines に 3 行の境界と 3 条件の粒度基準と併記形 1 行; 0113 に分類注記; 次の 5 本の新設 ADR が基準に合う（ゲートで目視）。
- 規模・整合: S / repair   出典: AB-21 AB-35 DC-28

##### P1-03.2 Status 尾部 `(amended …)` を 5 面で機械検査する
- 何を: `tests/test_adr_status_consistency.py` に「本文に `## Amendment` 見出し（または .1 で定めた追補様式）がある ⇔ Status 尾部に `amended` がある」を足す（日付一致までは求めない）。16 本の 5 面を揃え、索引 0113 行は P0-02.7（10-17 の削除 PR）が 5 面に打つ文字列 `accepted (amended 2026-10-07, 2026-10-09, 2026-10-17) — partially-supersedes ADR-0112 (D2 kill switch, D5 skill-selection shadow retired)` と同じにし（併記形は .1）、0081 本文 Status を索引に合わせる。
- 根拠: 本文 Status に `amended` があるのは 0018 / 0039 / 0068 / 0075 / 0080 の 5 本、索引にあるのは 0075 / 0081 の 2 本; `docs/adr/0081:3-5` 本文は bare `accepted` vs 索引 `README.md:89`「accepted (amended 2026-09-20)」（本文 `:282` に `## Amendment (2026-09-20)` あり）; 索引 `:121` の 0113 は bare `accepted`; test docstring（`tests/test_adr_status_consistency.py:21`）「descriptive tail is free」で尾部は検査外; `README.md:180`「`accepted (amended YYYY-MM-DD)` — body amended」が規約。
- 完了条件: 新 test が 113 本で green（16 本の 5 面が揃う）; `grep -c amended docs/adr/README.md` ≥ 16。
- 規模・整合: S / repair   出典: AB-20 DC-28

##### P1-03.3 Note による実質 supersession を Status と graph に昇格する
- 何を: 決定の一部を無効化する Note は `partially-superseded-by`（Status + graph edge）へ、それ未満は `revised-by ADR-NNNN (YYYY-MM-DD)` 語彙を README と graph `@context` に足す（D-P1-03-2）。まず 6 本を手で直す: 0043（Note 10-09「superseded」）、0086（Note 10-07 / 10-09）、0067 ↔ 0070（0070 Status「revises ADR-0067 Decision #3」に対し 0067 en 本文に 0070 への言及 0）、`0074:360`、`0096:125` / `:189`、`0112:98-104`（注記 2026-09-25 ADR-0113）。Note の書式を 2 つに分ける — 改訂は `Note (date, revised by ADR-X)`、手続きの適用は `Note (date, per ADR-0101 T4)`（P1-04.1 の書式。既存 `0049:149`「Note (2026-08-29, ADR-0101 T4 first stocktake)」も同類）— test は前者だけを対象に「本文に `Note (date, revised by ADR-X)` があれば X への typed edge が要る」を足す（手続き適用の Note に `revised-by ADR-0101` edge を要求しない）。
- 根拠: `docs/adr/0043:37`「**Note (2026-10-09, ADR-0113 amendment 2)**: superseded. … `relevance_floor` is gone」で Status `:5` は `accepted`; `0086:7-9` 同型; `0070:5` Status「revises ADR-0067 Decision #3 (… removed and relocated)」、`0067:5` は「accepted — partially-supersedes ADR-0065」のみ（`grep -c 0070` → 0）; `README.md:186`「LLMs can traverse the supersede / withdrawal chain without parsing prose」; test は Status 散文と edge の一致のみで Note は検査外。
- 完了条件: 6 本の 5 面と graph が揃い、`test_partial_supersede_edges_are_reciprocal` が 0067 / 0070 を含めて green; 新 test `test_dated_notes_have_typed_edges` が 113 本で green（`per ADR-0101 T4` 形の Note を対象外とする negative case 1 本を含む）。
- 規模・整合: M / repair   出典: AB-22 AB-23

##### P1-03.4 Review-when を遡及し、README の参照を直す
- 何を: `docs/adr/README.md:159`「(required since ADR-0044)」を「(harness 規約; 本 repo では ADR-0097 以降必須)」に直す。accepted な機構 ADR（0070〜0096 は 0069 以外すべて無し — 0071 / 0072 / 0075 / 0076 / 0081 / 0086 / 0087 / 0088 / 0090 / 0095 …）に、10-17 の T4 記録（P1-04.1）を読んでから 11-28 の着手（11-30 以降の平日セッション）で「Review-when 1 行」または「期限なし（理由）」を足す（10-17 当日には着手しない）。`scripts/docs_consistency_scan.py` に欠落検出を 1 reading 追加。
- 根拠: `## Review-when` 見出しを持つ en ADR は 18 本（0069 + 0097〜0113）、0089 は `:1125` `### Revisit condition` で代替; 0069 の Review-when 節は「this repo's own `0044` is an unrelated topic-keywords ADR」と自ら注記; `docs_consistency_scan.py:18-31` の reading は enja_drift / broken_link / notes_ref / freshness のみ; 「機構層が止まる」は各 ADR の失効条件が発火していないことで初めて認定できる。
- 完了条件: `grep -L '^## Review-when' docs/adr/0*.md`（en、withdrawn / superseded 除く）が「期限なし」宣言を持つ ADR だけを返す; scan の新 reading が 0 件。
- 規模・整合: M / neutral（ADR 文書の遡及。scan の 1 reading は既存計器の検査項目で計器の新設ではない）   出典: AB-24

##### P1-03.5 索引 2 面と graph の ADR 面を本文から生成し、Last revised / AAP / RFC ノードを足す
- 何を: stdlib script `scripts/adr_index.py` が本文（Status / Date / 題 / Amendment・Note の最大日付）から `docs/adr/README.md` / `README.ja.md` の表と `graph.jsonld` の ADR ノード（status / datePublished / supersede 系 edge）を生成し、test は「生成結果 = commit 済み」に単純化する。列を 2 つ足す — `Last revised`（Amendment / Note の最大日付か git）と `AAP`（P3-06.6 の「AAP ADR → CA の実物」表を正本にして生成。AAP `CLAUDE.md:17-28` の対応表は古い — 0006 / 0007 が「(暗黙、essay で言語化)」、0005 が CA ADR-0012 のみ、ADR-0050 が無い。AAP 側の表の更新は P3-06.7 と同じ PR、AAP 0002 行の「ADR-0028 / ADR-0029 audit」も照合対象（推測、要確認））。ADR の起点になった RFC（graph の `isBasedOn` が URL 文字列で指す 0028 / 0031 / 0032 / 0036 / 0040 / 0042 / 0045 / 0046）を `RFC` 型ノードにする。`CLAUDE.md:13` 鮮度規約に「AAP 対応 ADR を持つ本体 ADR の改訂は AAP 側の確認を PR 説明に書く」を 1 行。PR は 3 本 — PR-A（`scripts/adr_index.py` が README 表を生成 + 「生成 = commit 済み」テスト。索引の `[AKC: …]` タグ 13 本は README / README.ja の手書き行にしか無いので、タグ列の扱い（graph の akc-cycle-mapping から生成か削除）をこの PR の決定に含める）→ PR-B（`graph.jsonld` の ADR ノード + RFC 型ノード、`tests/test_adr_status_consistency.py` を拡張）→ PR-C（`Last revised` / `AAP` 列 + `CLAUDE.md:13`。P3-06.6 の表は 2027-Q1 後半に出来るので、それまでは `AAP` 列を空にして置き場（P3-06.6）を指す注を表に置き、表が出来た週に再生成する）。
- 根拠: 索引 113 行 × 2 面と graph の ADR ノード 113 は手書き（`grep -rl 'adr/README' scripts/` → 0）; 直近 30 日（2026-09-10〜）で本文が変わった ADR は 22 本（0113 は en/ja 合わせて 12 回、0112 は 8 回）だが索引 Date は起票日のみ — 10 月は新設 0 で「止まった」に見える; graph の RFC ノード 0（`@type` は ADR 113 / Concept 13 / Phase 6 …）; `docs/adr/README.md` に `agent-attribution-practice` 0 件、ADR 本文で AAP を引くのは 3 本; AAP `CLAUDE.md:34`「逆方向 (contemplative-agent の ADR 改訂時に本 repo を更新) も同様」は片側にしか無い。
- 完了条件: `tests/test_adr_index_generated.py` green（生成 = commit 済み）; `scripts/adr_index.py --revised-since 30` が exit 0 で件数を出す（「30 日以内に改訂された ADR の数」の読み）; graph に ADR → RFC の typed edge 8 本; 索引に AAP 列（P3-06.6 の表が出来るまでは空で置き場を指し、出来た週の再生成で埋まる）。
- 規模・整合: M / repair   出典: AB-34 AB-27 AB-46 GO-33 R3-AKC M1 F3   順序: PR-A → PR-B → PR-C; P1-13.7 の写像の書き直しは PR-B より前

##### P1-03.6 小さな整合修理（Date 節・`/sync-context`・ADR-0061 の帰属）
- 何を: 0032 en 本文に `## Date` 節（2026-04-27）を足す（見出し自体が無い — 索引は 2026-04-27）。`docs/adr/README.md:197` と `README.ja.md:225` の `/sync-context` を `uv run pytest tests/test_adr_status_consistency.py tests/test_graph_integrity.py` + `scripts/docs_consistency_scan.py` に置換。`src/contemplative_agent/adapters/moltbook/llm_functions.py:181` / `:226` / `:521` の「ADR-0060 pattern」を ADR-0061（platform field 上限への cap は 0061 の決定、`docs/adr/0061:50,57`）に直す。test に「索引 Date = 本文 Date」を足す。
- 根拠: `grep -n '^## Date' docs/adr/0032-runtime-agent-stance.md` → 0 件、索引 `README.md:40` は 2026-04-27; `.claude/skills/` に sync-context 無し（11 skill）; ADR-0061 題「Action-Time Untrusted Input Caps at Platform Field Limits」、src / tests からの 0061 引用 0。
- 完了条件: `grep -rc 'ADR-0060 pattern' src/ --include=*.py` が 0 かつ `grep -rc 'ADR-0061' src/ --include=*.py` ≥ 3; README en/ja に `sync-context` 無し; Date test green。
- 規模・整合: S / repair   出典: AB-25 AB-26 AB-28

##### P1-03.7 Template に `## Decided by` と `## Layer`
- 何を: `docs/adr/README.md:139-170` の Template に `## Decided by`（proposed-by: Claude Code session / decided-by: 人名 / date）を追加し、ADR-0114 以降は test で必須にする。既存 113 本は backfill しない（AKC ADR-0026 と同じ方針）。同じ PR で `## Layer`（`mechanism | instrument | governance | research | worldview` のどれか 1 つ。README の 2 分類は `worldview` 以外 = problem-solving と注記）を足して ADR ≥ 0114 で必須にし、凍結窓の開始以降の追補見出しは `## Amendment (YYYY-MM-DD, <layer>) — <題>` とする（その範囲に限って必須、既存は backfill しない）。`scripts/freeze_reading.py`（P1-01.1）の新設 mechanism ADR 数と層別の追補数はこの 2 つだけを読む。層を 5 つにするかはオーナー判断（P1-01.1 の 3 層 + research / worldview は推測による拡張）。
- 根拠: Template は Status / Date / Context / Decision / Review-when / Alternatives / Consequences / References で起草者・受理者欄が無い; 明示するのは `docs/adr/0080:43-44`「This ADR was decided in an owner–assistant working conversation on 2026-07-20」など 6 本（GO-30 集計）; `git log` 442/447 commit がオーナー名義で、Claude 起草 ADR の受理はオーナーの commit に暗黙化; AAP `0006:53-61`（attribution: who authored the behavior）の設計判断版; `docs/adr/README.md:125-137` の分類は Problem-solving / Worldview の 2 つだけで Template に層の欄が無く、追補見出しは `0113:236`「## Amendment (2026-10-07): one judge, fail-closed (RFC-0046 cleanup 2)」のように題だけ — P1-01.1 と D-P1-01-1 A の「新設 mechanism ADR 数」「機構節を変える追補数（層別）」を見出しの grep で出す材料が無い; 2026-12〜2027-Q1 に新設 ADR が少なくとも 6 本予定される（推測を含む集計）。
- 完了条件: Template に 2 欄; `tests/test_adr_status_consistency.py`（または新 test）が ADR ≥ 0114 の `## Decided by` と `## Layer`、窓開始以降の追補見出しの層を検査し green; `freeze_reading.py` の出力行に層別件数; P3-01 / P1-13.1 / P2-07.1 の ADR が層を持って起票される。
- 規模・整合: S / neutral（Template の欄と test — 読み値を出さない。Confidence med — 層の数はオーナー判断）   出典: GO-30 R3-ADR-02   順序: 凍結窓の開始前（11-28 の着手）

##### P1-03.8 ADR-0080 への追補を（2026-11）/（2026-12）の 2 本に束ね、同 PR で CLAUDE.md §北極星を同期する
- 何を: 本ロードマップが ADR-0080 に別々に提案する追補 / dated note（P0-07.8、P1-01.1 / .3 / .4 / .6 / .8、P2-01.3 / .5、P2-02.1、P2-07.5、P4-01.1、D-P2-05-3 A、D-P3-01-1 の Q4 採否、D-P1-13-1 A の人間ゲート範囲）を 2 本に束ねる — 追補（2026-11）（止まる・負荷・自己調節の読み方、凍結集合と凍結後の PR 規則、凍結後のモデル交代（P1-01.8）、Claude Code 関与の二分、人間の言葉を残す 3 接点（P2-07.5 の dated note もここに 1 段落）、Re-read trigger 発火の記録。材料は 11-28 の土曜ゲート: D-P1-01-1（定義と追加段のみ。verdict は窓が満ちた週の読みで、追補の材料ではない）/ D-P2-01-1 / D-P2-01-3 / D-P2-02-1 / D-P2-05-3。「読み方」段落に .9 の基礎率・待ち時間の 1 行ずつを同じ PR で）と追補（2026-12）（第 5 層の検討イベント、P3-01 の Q4 採否、D-P1-13-1 A を採る場合の人間ゲートの範囲。12-19 の土曜ゲート: D-P4-01-1 の後）。P2-06.3 の表は ADR-0106 に一本化し ADR-0080 には入れない。見出しは `## Amendment (YYYY-MM-DD) — <題>` の日付形で、小見出しに A / B / C を再利用しない（既存の 08-26 追補 §A / §B / §C と衝突させない）。各読み値に「この読み値は判定の材料であり、達したかの判定はオーナーが `gate_record` に書く」の定型 1 行を付し、各 PR で CLAUDE.md §北極星を同期する。各項目の完了条件は「追補（2026-11）/ 追補（2026-12）に 1 段落」とし、「追補 2」の番号衝突（P2-02.1 / P4-01.1）を消す。
- 根拠: `docs/adr/0080:239-245`「the CLAUDE.md section must be updated in the same PR as any future amendment here」「future changes land as further dated amendments to this ADR, with the CLAUDE.md operative section synced in the same PR」、`:125-129`（定義は非機械判定）、`:175-182`; 既存の 08-26 追補は小見出し `:162`「### A.」/ `:199`「### B.」/ `:230`「### C. Housekeeping」を持ち、本文 `:15` / `:138` が「Amendment §C」を参照する — 新しい 2 本を「C / D」と呼ぶと §C と取り違える; `CLAUDE.md:71`「ADR を追補したら本節を同 PR で同期する」; 既存の追補見出しは `:144` の 1 本（2026-08-26）のみで、本ロードマップが求める追補は項目 9 + 決定 1（束外の追補を寄せて項目 11 + 決定 3）で、草案ではそれらが別 PR を予定し、同 PR 同期を書くのは P2-01.3 / P2-02.1 / P4-01.1 の 3 項目だけだった — 10 本が別 PR で入ると北極星の操作面が 7 回ずれる機会を持ち、閾値や窓（D-P1-01-1）が定義に混ざる。
- 完了条件: 追補（2026-11）の PR は 11-30〜12-04 に段落の草案（P2-07.5 は A / B の両文）を含めて出し、12-05 の D-P2-07-1 の後に採った方の文で 1 本 merge（12-07〜11）、追補（2026-12）は 12-21〜25 に merge; ADR-0080 の `## Amendment` 見出しが日付形で 2 本増え、それぞれの commit に `CLAUDE.md` §北極星の diff が含まれる（`git log --format=%H -- docs/adr/0080-north-star-layered-end-state.md CLAUDE.md` で同 commit）; 上記の各項目の完了条件が「追補（2026-11）/ 追補（2026-12）に 1 段落」になり、ロードマップ本文に ADR-0080 の「追補 2」表記が無い; ロードマップ本文と decisions.md で `grep -cE '追補 [CD]'` = 0、CLAUDE.md §北極星の参照も日付形。
- 規模・整合: S / neutral（文書）   出典: R1-NS-02（R1-NS M-1 の受け皿）R3-ADR Merge-01 R3-ADR-01   順序: 追補（2026-11）は 11-28 の決定の後に草案、12-05 の D-P2-07-1 の後に merge; 追補（2026-12）は 12-19 の D-P4-01-1 の後

##### P1-03.9 連続週数型トリガー 6 規則に基礎率と待ち時間を 1 行ずつ添える（追補（2026-11）の「読み方」）
- 何を: 本ロードマップの run-length 規則 — D-P1-01-1 A（凍結集合の commit が `fix` のみ連続 8 週）、D-P2-01-3 B（8 週 adopted 0 ∧ archived 0 ∧ identity 更新 0）、D-P4-01-1 B（下限は D-P2-01-3 の 8 週に一本化）、P1-05.2（2 週連続帯外）、ADR-0099（Deviations 空 4 週）、ADR-0110（outlier 空 4 週）— の各々に「現在の基礎率ではこの条件が何もなくても満たされる確率」と「満たされるまでの期待週数」を 1 行ずつ、追補（2026-11）（.8）の「読み方」段落に同じ PR で添える。定義には入れない（読み方は追補（2026-11）の置き場）。`scripts/freeze_reading.py`（P1-01.1）と `self_regulation_reading.py`（P2-01.5）は「候補宣言」の行に「基礎率 X で偶然の確率 Y」を併記する。分布形は仮定（推測）であることを各行に明記する。
- 根拠: ADR-0091:111-115（identity 間隔は 6〜26 日、中央値 13、policy choice）→ 間隔が中央値 13 日の指数分布なら 8 週で採用 0 の確率 ≈ 5%（D-P2-01-3 B と、8 週で計算し直した D-P4-01-1 B は同じ線。旧案 26 週の ≈ 6e-5 は過剰）; P1-01.1 根拠: W33〜W41 の 9 週で「fix のみの週」は 0（基礎率 0/9、Wilson 上限 ≈ 0.30）→ 8 週連続は現状の分布では到達不能で、到達 = 分布が変わったの読み（意図どおりだが明文化されていない）; `docs/adr/0099-weekly-report-instrument-redesign.md:164-168`、`docs/adr/0110-instrument-series-projection.md:214-216` はどちらも基礎率の記述なし。
- 完了条件: 追補（2026-11）の「読み方」段落に 6 規則の基礎率・待ち時間が 1 行ずつ（D-P4-01-1 行は 8 週で計算）; `freeze_reading.py` と `self_regulation_reading.py` の候補宣言行に基礎率の併記（各 test 1 本）; 区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）。
- 規模・整合: S / neutral（読み方の注。閾値は変えない）   出典: R2-STAT-05   依存: P1-03.8（同じ PR）、P1-01.1 / P2-01.5（併記先の script）、D-P2-01-3 / D-P4-01-1（規則の文面）

##### P1-03.11 追補と新 ADR の境界を、D-P1-03-1 の前から暫定基準で運用する
- 何を: D-P1-03-1（2027-01-09）の推奨 A の 3 条件（反転・他 ADR の前提変更・本番挙動の変更は新 ADR か partial supersede）を「暫定基準」として 10-17 から decisions.md の記録規則に 1 行置き（P2-01.10 の decisions.md に同乗）、決定より前に入る 3 件の完了条件をそれに合わせる — (1) P1-12.5: ADR-0012 の却下理由の反転は `partially-superseded-by` にする新 ADR か、ADR-0012 の Status に partial と範囲 (2) ADR-0010 の Sync Timing は P2-04.1 が D-P2-04-1 / D-P2-05-1 の後に 1 本で partial supersede（P1-09.5 は文書 3 面の一致だけ）(3) D-P3-04-1 の決定文に「ADR-0030 の前提文を partial supersede する ADR を起こすか」。各項目の書き換えは P1-12 / P2-04 / P3-04 側。
- 根拠: `docs/adr/0012-human-approval-gate.md:50` の却下理由「Claude Code can read results and make an approval decision」を P1-12.5 は Notes で閉じる予定; `docs/adr/0010-research-data-sync.md:36-38`「Runs as a post-processing step of the distill command. No additional launchd plist required.」を P1-09.5 / P2-04.1 は launchd 日次に書き換える; `docs/adr/0030-withdraw-identity-blocks.md:33`「ADR-0020 (pivot snapshots) provides full-text identity replay」の前提を P3-04.2 が崩す; `docs/adr/README.md:193`「never overwrite」は現状のまま。
- 完了条件: 暫定基準の 1 行が decisions.md の記録規則にある; 3 件の完了条件が Status / graph の edge で終わり、`test_partial_supersede_edges_are_reciprocal` が green。
- 規模・整合: S / repair（Confidence med — 3 件を「反転」とみなすかは推奨 A の文言に照らした読み）   出典: R3-ADR-03   依存: P1-03.1、P2-01.10（decisions.md）、D-P1-12-1 / D-P3-04-1（10-31）


**依存**
- P1-02（RFC 台帳: frontmatter の正規化と `scripts/rfc_index.py`）— .5 の RFC ノードと awaiting-owner の同居
- P1-04.1（ADR-0101 T4 第 2 回 = 10-17 の記録）— .4 の遡及はその記録を読んでから（10-24 以降の平日セッション）
- P0-02.7（10-17 の削除 PR、0113 の Status 文字列）— .2 の 0113 行
- P1-13.7（AKC 写像の書き直し）— .5 PR-B の前
- P2-01.10（`docs/plans/roadmap-2026-10/decisions.md` の記録規則）— .11 の暫定基準の置き場
- P1-01.1 / .3 / .4 / .6 / .8、P2-01.3 / .5、P2-02.1、P2-07.5、P0-07.8、D-P2-05-3 A と D-P1-01-1（定義と追加段）/ D-P2-01-1 / D-P2-01-3 / D-P2-02-1 / D-P2-05-3（11-28 の土曜ゲート）、D-P2-07-1（12-05 の土曜ゲート — P2-07.5 の段落の A / B）— .8 の追補（2026-11）の材料（11-30〜12-04 に草案、12-05 の後に 1 PR で merge）
- P4-01.1、D-P4-01-1（12-19 の土曜ゲート）、D-P3-01-1 / D-P1-13-1（12-12 の土曜ゲート）— .8 の追補（2026-12）の材料（12-19 の後に 1 PR、12-21〜25）
- P1-01.1（`freeze_reading.py` の候補宣言行）、P2-01.5（`self_regulation_reading.py` の候補宣言行）、P2-01.9（区間の規則）— .9 の併記先と区間
- → 参照元: P1-01（.5 の `Last revised` 列が「追補 / Note 数 / 月」の読みの正本; D-P1-01-1 の基礎率の注は .9; .7 の `## Layer` が P1-01.1 の `freeze_reading.py` の層別の材料）、P3-06.6（AAP ADR → CA の実物表 — 2027-Q1 で .5 PR-C より後なので、PR-C は AAP 列を空で置き、表が出来た週に再生成で埋める）、P1-13.3（帰属 trailer の語彙 — 12-12 の週で .7 より後なので、.7 は現行の語で書き P1-13.3 が合わせる）、P3-06（AAP への書き戻し — .5 の AAP 列）、P1-02.4（awaiting-owner の `Deferred — 未決` 語彙 — .3 / .6 で揃える）、P2-01 / P2-02 / P2-07 / P3-01 / P4-01 / P1-13（追補（2026-11）/ 追補（2026-12）の各段落を各項目の完了条件が指す）、P1-12.5 / P2-04.1 / P3-04（D-P3-04-1）（.11 の暫定基準で完了条件を書く）、P1-04.1（`per ADR-0101 T4` 形の Note — .3 の test の対象外）


#### P1-04 計器の解体と消費計画の補完（ADR-0101 T4）
- 狙い: 北極星（ADR-0080 の 08-26 追補 §A）は「観測で止まる」装置の完成だが、計器複合体（出口計器 4 本 ≈3,000 行・eval 層・常設 sweep）は溶解義務（ADR-0101）の後も消費計画なしに育っている。四半期 T4 の第 2 回（Q3 境界後の最初の土曜 = 2026-10-03 が期日、記録なし）で祖父条項 ADR の計画を backfill し、読みが何も決めない計器を撤去・減速する。
- 期限・順序: 着手 2026-10-17 の土曜ゲート（§4.0）。期限 2026-12（.11 と .10 の ADR-0089 追補は D-P1-04-3 = 2027-02-06 の後。.16 の (i)〜(iii) の振り分けは遅くとも 2027-01-09 の T4 第 3 回）。T4 第 2 回は 10-17 の土曜ゲートに統一（P0-02 の旧 relevance gate 削除 = 10-15 以降の読みの後。削除で対象集合が変わるため）: D-P1-04-1 と .16 の読み手 4 値の棚卸しをこの回で、D-P1-04-2 / D-P1-04-4 は 10-24 のゲートで裁く。10-17 のゲートは判定と 4 値表まで（ゲートは code を適用しない — `SKILL.md:404-405`）で、.1 の ADR への backfill PR は 10-19〜10-23 の平日、.16 の (i)〜(iii) の振り分けは D-P2-02-1（11-28）の後の 12 月の平日か次の T4（2027-01-09）。.5（comment-outcomes の 2 窓判定）の 2 窓は 3 週窓 × 2（09-12〜10-02 / 10-03〜10-23）を `read_comment_outcomes` の 2 回の直接呼び出しで 10-24 の週（10-19〜23）に取り（weekly の 7 日窓では 500 に届かない。P2-04.13 PR-A は待たない）、検定とともに 10-24 で裁く — 遅れた場合は P2-01.14 の規則に従う。weekly-gate SKILL.md の変更は同梱 PR に束ねる: .16（T4 チェックリストの読み手 4 値列）は 10-17 の週の同梱 PR（P0-01.8 の Step 0 四半期行と同乗）、.4（Step 6c の天井段落削除）は 10-24 の週の同梱 PR（P1-05.1 の Step 6g は先行列の 10-17 の週の同梱 PR に移ったので同乗しない）。eval 層は .12 のコード撤去のみ v2.13.0（P0-06、tag は 11-14 の決定の後の 11-16〜20）の tag 前、.10 / .11 は後で、.11 は D-P3-01-2 / D-P1-04-3 がどちらも推奨どおりなら「smoke として baseline 1 行」に縮める。閾値の表は .8 の 1 枚（P1-06.4 は env 登録簿だけ、P1-07.11 は runbook だけを持ち、表は .8 を引く）。ADR-0089 の追補は .10 が 1 本（日付 1 つ）で持ち、.12 の deepeval 撤去・P1-07.15 の seam 固定文・P3-01.2 の研究証拠としての位置づけ・D-P3-01-2 A をその段落として寄せる（D-P1-04-3 と D-P3-01-2 は同じ 2027-02-06 の土曜ゲート）。決定: D-P1-04-1 / D-P1-04-2 / D-P1-04-3 / D-P1-04-4。
- 束の完了条件:
  - `grep -l '^### Consumption plan' docs/adr/*.md` が 0071 / 0076 / 0085 / 0086 / 0089 / 0090 / 0091 / 0092 / 0093 / 0097 を含む（現在は 0104–0107 / 0110–0113 の 8 本のみ）
  - T4 第 2 回の判定が所有 ADR の日付付き注記として存在し、retirement candidate ごとに撤去 commit か RFC があり、T4 記録に読み手の種別 4 値の表が 1 回出ている（.16）
  - `scripts/_census_registry.py` の KEPT 行すべてに `until` がある
  - 公開 data repo に `pipeline/ledger-watch/` が無く、`scripts/` に入力の存在しないスクリプトが無い
  - `evals/baselines/` の最新 baseline が ack 無しの実測で、comparability に `selection_temperature` を含む

##### P1-04.1 T4 第 2 回を実施し、祖父条項 ADR に Consumption plan を backfill する
- 何を: 2026-10-03 に期日を迎えた T4 第 2 回を 10-17 の土曜ゲートで実施する。ゲートは判定（計器ごとの (a)(b)(c) か retirement candidate）と .16 の 4 値表までで、ADR への backfill は 10-19〜10-23 の平日に PR で入れる（ゲートは code を適用しない — `SKILL.md:404-405`）。ADR-0071 / 0076 / 0086 / 0090 / 0092（祖父条項 5 本）と 0091 / 0093 / 0097 に `## Review-when` → `### Consumption plan` を追補し、計器ごとに (a) 読み手 (b) 決める事 (c) 撤去条件 か「retirement candidate」を日付付き注記で記す。ADR-0091 は「due の週だけ JSON を出す」選択肢を含める。
- 根拠: ADR-0101:112-128（T4 は四半期境界後の最初の土曜ゲートで再発、判定は所有 ADR の dated annotation）/ `grep -l '^### Consumption plan' docs/adr/*.md` → 0104–0107・0110–0113 の 8 本のみで、0071 / 0076 / 0086 / 0090 / 0092 と 0091 / 0093 には `## Review-when` 節自体が無い / `git log --since=2026-09-25` と ADR の注記に T4 第 2 回の記録なし（ADR-0049:149 の初回 2026-08-29 のみ）。
- 完了条件: 上記 grep が 8 ADR を追加で含む（backfill の commit は 10-19〜10-23）。各 ADR に `Note (2026-10-xx, per ADR-0101 T4)` の判定注記（手続きの適用の書式。P1-03.3 の typed edge test の対象外）。
- 規模・整合: M / repair   出典: OI-01 WO-51

##### P1-04.2 読み手のない 2 計器（view_metrics・skill-stocktake）の去就を T4 で決める
- 何を: `view_metrics` は ADR-0071 の plan で「改正ゲート時のみ `report --patterns`（RFC-0012 の材料）」とし、`distill.py:51` の dry-run `instrument_lines` 経路を撤去する。`skill-stocktake` は ADR-0097 注記で「T4 専用 / 撤去」を決め、撤去なら CLI 表から落とす。surprise は撤去候補にしない（ADR-0097 en:8,186 が 08-26 追補 §B の新規性軸の既実装として復元し、P2-06.2 が 3 軸 join の 1 列として消費する — やらないこと候補を参照）。
- 根拠: `cli/session_cmds.py:245`（唯一の手動呼び出し）、`core/distill.py:51`、`config/views/` は 2 本（0.55 / 0.66）で `weekly-analysis.sh` の節一覧（:220-635）に pattern composition 節なし / `snapshots/skill-stocktake_20260815T041708923626Z` が唯一の実行痕跡、weekly-gate SKILL.md・weekly-analysis.sh に呼び出しなし、`cli/stocktake_cmd.py` docstring「this command reports, it does not retire」。
- 完了条件: ADR-0071 / 0097 に注記 + `distill.py:51` 経路の削除とテスト更新。
- 規模・整合: S / repair   出典: OI-14 OI-13

##### P1-04.3 submolt-scope sweep（ADR-0086）の常設を判定し、尺度断絶を計器側で検出する
- 何を: ADR-0086 に Consumption plan を追補し、(a) 購読集合変更の材料として四半期 1 回読む か (b) 撤去 かを決める（D-P1-04-1）。撤去なら `install-schedule` の経路から plist を外し、`report --submolt-scope` の残否を決める。併せて `submolt_scope_stability.py` / `relevance_arm_replay.py` / `relevance_label_set.py` に `scale` / `strata_key` 混在時の理由コード付き abstain を入れ、2026-10-09 を系列の境と ADR-0086 / RFC-0047 に明記する。
- 根拠: `rfcs/0011` frontmatter `state: done 2026-09-05` だが `## Status`（:113-116）は blocked のまま、2026-09-05 done 項「判定は行っていない」、installed plist `Weekday=4 / Hour=3`（:109）/ ADR-0086:7, 9（10-07・10-09 注記: score4 採点へ移行、以前の数値と比較不能）/ `relevance_arm_replay.py` docstring:6-12（2,698 投稿、0–1 尺度の記録のみ読む）/ ADR-0107:28 表で `submolt-scope-*` は「manual scripts only, outside the chain」。
- 完了条件: ADR-0086 注記 + RFC-0011 Status 節の更新（P1-02.1 の test が後で固定する）+ launchd 設定の整合。混在入力で 3 スクリプトが理由コード付きで abstain する（テスト 1 本）。
- 規模・整合: S / repair   出典: OI-05 OI-34

##### P1-04.4 出口計器（7b/7c）の天井問いを ADR-0105 に終端し、撤去条件を短縮する
- 何を: ADR-0105 に日付付き注記を足す — 天井読み 1/2 = 26.85%（帯外）、2/2 = 23.03%（帯内）→「帯では答えられない」で閉じ、RFC-0044 の読み（t=0 で幻覚率が catalog と無関係に 2.6% へ）で天井仮説の動機は消えた。Removal condition の「1 年」を「4 週連続で 7b と重複しない候補が 0 なら撤去」に短縮（D-P1-04-4）し、weekly-gate Step 6c の天井手順（:271-284）を削除する。`core/skill_confusion.py`（src 内 fan-in 0、755 行）は `scripts/` へ移すか plan に「scripts 専用」と明記する。
- 根拠: `docs/evidence/rfc-0014/skillsel-read-4-20260905.md:272-273`、`rfcs/0021:170`（2026-09-19「消費計画は満了」）、ADR-0105 に dated note なし（grep '2026-09-19' → 0）、ADR-0105:189-193「a year in which every week lists nothing…」/ data repo `pipeline/confusion-pairs/` の pairs は 09-11: 2、09-18: 1、09-25: 1、10-02: 0（4 週連続空ではない）、never-selected `strict` は 09-18 以降 3 週 0 / 4 本で 3,068 行（selection_metrics 1,141 / never_selected 620 / skill_confusion 755 / selection_window 552）、消費者は `scripts/confusion_pair_reading.py:47` と tests のみ。
- 完了条件: ADR-0105 注記 1 本。SKILL.md Step 6c の天井段落が消える。`weekly-pipeline.sh` 7c が短縮した撤去条件を持つ（発火時は削除 PR）。`skill_confusion` の fan-in ≥1 か `scripts/` 移動。
- 規模・整合: S / repair   出典: OI-07 CP-27 CH-20 AB-17 WO-50   順序: SKILL.md Step 6c の変更は 10-24 の週の同梱 PR（R2-GATE Merge-01）

##### P1-04.5 comment-outcomes（ADR-0106）の 2 窓判定を取り、撤去か帰属 RFC かを記録する
- 何を: 2 窓を 3 週窓 × 2（09-12〜10-02 / 10-03〜10-23）と定義し、`read_comment_outcomes(log_dir, *, since, until, min_age_days=2)` を since / until を変えて 2 回直接呼ぶ（stage 7d と同じ呼び方の 1 行: `uv run --no-sync python -c '…read_comment_outcomes(home / "logs", since=date(2026, 9, 12), until=date(2026, 10, 2), min_age_days=2)…'`、2 窓目は since=10-03 / until=10-23）。出力 JSON 2 本を `docs/evidence/adr-0106/`（新設）に置く — weekly JSON は `since = until − 6` の 7 日窓で、1 週で 500 に届く列が無い。ADR-0106 の注記は 2 文: 「≥ 500 judged records」は `joined_publishes`（selection の読みと同じ母集団、ADR-0106:161）で数え、返信率は `observed_publishes`（D5 の観測分母、母集団の約 1/3）で読む。分かれるか（skill 別返信率の広がり vs `injected_comments` の偶然幅、store 全体の帯を宣言できるか）は 2 窓を合算した `scripts/comment_outcome_separation.py`（stdlib + numpy、read-only）1 本で読む — skill ごとの (reply, no-reply) 表で (1) 全体の χ² か G 検定（期待度数 < 5 の skill は「その他」に併合）、(2) 置換検定（返信を comment にシャッフルし、skill 別率の分散の分布）、(3) skill 別 Wilson 区間を出し、観測率 1/3 の事実を結果の 1 行目に出す。A / B は p 値ではなく効果量で決める: 最大 skill 間差 ≥ 0.2 を「分かれる」の線として 10-24 の読みの前に事前登録し、決定文に書く。10-24 のゲート（D-P1-04-2）で裁いて ADR-0106 Review-when に日付付き注記を書く。分かれなければ stage 7d を撤去し RFC-0028 を resolved に、分かれれば帰属 RFC を起票する — ただし読みに限り、skill 別返信率を adopt / archive の判定には流さない（ADR-0106 D6「読みは分布であり、そうだとファイルに書く」、ADR-0051。流せば reward weighting で ADR-0051 の supersede が要る、`docs/adr/0080:213-217`）。
- 根拠: ADR-0106:159-168（2 窓 ≥500 judged、問い (i)(ii)、撤去条件: stage 7d 削除・RFC-0028 resolved — 検定は未指定）、`:161`「≥ 500 judged records (the same population the selection readings count)」、`:128-131`（D5 観測分母）/ `core/comment_outcomes.py:446-452`（`read_comment_outcomes` は since / until を受け取る）、`weekly-pipeline.sh:964-966`（stage 7d は `since = until − 6` で呼ぶだけ）/ data repo `pipeline/comment-outcomes/` 09-11〜10-02 の 4 窓は `joined_publishes` 37 / 367 / 370 / 285、`observed_publishes` 15 / 126 / 132 / 96（10-02: unobserved 189 / excluded_immature 100）— 1 週で 500 に届く列は無い; 10-02 窓の skill 36 件の `injected_comments` 中央値 11・10 未満 18 件、09-18 窓は 45 skill 中 10 未満 23 件 / ADR-0106:100 の D3 追補（2026-10-03）は計器の修理で、判定の記録ではない / SKILL.md Step 6e（:296-300）は手順を持つが判定の記録先が無く、`:301`「各 ≥ 500 judged records」の judged がどの欄かは未定義。
- 完了条件: 2 窓の読み 2 本（since / until と 3 週窓の実測値 `joined_publishes` / `observed_publishes` を記した JSON）が 10-23 までに `docs/evidence/adr-0106/` にある; `scripts/comment_outcome_separation.py` が 2 窓合算で (1)(2)(3) を出す（合成 fixture の test 1 本）; ADR-0106 に judged と率の分母の 2 文の注記と判定注記 1 本; D-P1-04-2 の決定文に事前登録線と「観測率 1/3」の限定があり、10-24 の `gate_record` が script 出力を引く; 区間は Wilson で、P2-01.9 の `scripts/_stats.wilson_ci` が 10-31 の週に入るまでは同じ式を script 内に持ち、入ったら置き換える（分母 < 10 は件数のみ）。撤去なら `weekly-pipeline.sh` から 7d が消え `rfcs/0028` が resolved。
- 規模・整合: S / instrument（事前登録と検定。adopt / archive には流さない）   出典: OI-06 AB-18 R2-STAT-03   順序: 2 回の呼び出しと検定 script は 10-24 の週（10-19〜23）
- 消費計画: (a) 10-24 の土曜ゲート（D-P1-04-2）の人間が 1 回読む（読み手の種別は P1-04.16 の 4 値で「人間」。weekly の 7d 行はそれまで headless の転記のみ） (b) 1 回の読み（検定つき）で A（撤去 + RFC-0028 resolved）/ B（帰属 RFC 起票）を決める (c) 撤去条件: ADR-0106 の撤去条件と同じ — 分かれなければ stage 7d と共に消え、分かれれば帰属 RFC に引き継いで本項目の読みは終わる

##### P1-04.6 低陽性スキャン（dead-code・docs-consistency）に減速条件と plan を追補する
- 何を: ADR-0085（dead-code）/ ADR-0093（docs-consistency）に Consumption plan を追補し「陽性 0 が N 週続いたら月次へ減速、陽性が出たら週次に戻す」を書く。dead-code は 9 回で候補 13 件がすべて whitelist 行き（偽陽性）なので N=4 を推奨。gate briefing の「陽性時のみ展開」は → P2-06。
- 根拠: data repo `pipeline/dead-code/` 9 件の候補数は 0 / 1 / 1 / 0 / 2 / 1 / 6 / 1 / 0（9 回連続 0 ではない。09-18 の 6 件は `e12c09c` で whitelist）/ `pipeline/docs-consistency/` findings は 22 / 4 / 0 / 0 / 0 / 1 / 0 / 0（8 回連続 0 ではない）/ ADR-0085・0093 に Review-when 節なし / SKILL.md Step 5（:201-217）「候補ゼロの週は無音が正常」。
- 完了条件: 2 ADR に plan 節。`weekly-pipeline.sh` の 2 stage が減速条件を持つ。
- 規模・整合: S / repair   出典: OI-08

##### P1-04.7 退役計器の残骸（公開 data repo・scripts・fixture）を 1 回の総当たりで撤去し、形式の現役 / 退役表を置く
- 何を: `pipeline/ledger-watch/`（ADR-0095 で退役した stage 6c の唯一の出力）をゲートで削除する。`reports/analysis/README.md` に形式ごとの現役 / 退役（期間・所有 ADR）表を置く（DATACARD 側の表は → P3-05）。`scripts/retrieval_recall_measure.py`（退役した `-insight-review.md` を ground truth に読む）を削除し、ADR-0097 Review-when の該当 trigger を「`docs/evidence/rfc-0023/retrieval-recall-v{1,2}-*.json` で recall@5 0.61、0.9 未達」の注記に置き換える。同じ総当たりで consumer の無い script・fixture・定数も片付ける（P1-08 から吸収）: `scripts/submolt_scope_stability.py`（tests/ から参照 0。去就は D-P1-04-1 に従う）と `scripts/ipd-two-arm.sh`（tests/ 参照 0）は smoke 1 本か退役判断、`tests/fixtures/sampling/`（qwen3.5:9b 期、読み手なし）は `docs/evidence/` へ移すか削除、`tests/fixtures/benchmark/real_sample.jsonl`（2026-03-30、qwen）は `tests/benchmark_distill.py` ごと退役判断（episode 形式の除去自体は P0-03.11）、vulture の唯一の候補 `relevance_shadow.py:80 SOURCES` は土曜ゲートで判定。
- 根拠: data repo `pipeline/ledger-watch/ledger-watch-2026-08-14.json`（1 本）、`reports/analysis/` に `-packet.md` ×5、`-insight-review.md` ×5、`-improvement.md` ×1、`patches/` ×4、`.ja.md` ×15（現行は `weekly-*.md` ×28 + `-findings.md` ×21）/ `scripts/retrieval_recall_measure.py` docstring:16-17, 30-37（固定先は `docs/evidence/rfc-0023/`。`docs/evidence/adr-0097/` は存在しない）/ ADR-0097:343-346 は同スクリプトの recall@5 ≥ 0.9 を現役 trigger として引用 / `grep -rln submolt_scope_stability tests/` = 0（参照は ADR-0086 / 0113、RFC-0011 のみ）; `tests/fixtures/sampling/{comment_suite.jsonl,results/*.json}` の参照は `docs/evidence/adr-0068/` と ADR-0089 のみ; `tests/fixtures/benchmark/real_sample.jsonl:1` `"ollama_model": "qwen3.5:9b"`、`tests/benchmark_distill.py:5`「Not a pytest test — requires a running Ollama」; `src/…/relevance_shadow.py:80` `SOURCES`（`4b85f22` の残り）。
- 完了条件: 公開 repo に `pipeline/ledger-watch/` が無い。README 表が全 `pipeline/*/` と `reports/analysis/*` 形式を網羅。`scripts/*.py` の docstring が参照する入力パターンがすべて実在し、`scripts/` の .py / .sh と `tests/fixtures/` の全ファイルに tests/ か scripts/ の consumer がある（参照 0 の一覧が空。総当たり 1 回、結果を T4 記録に注記）。`dead_code_scan.py` の候補 0。
- 規模・整合: S / repair   出典: OI-10 WO-39 OI-11 TQ-26 TQ-32 TQ-39

##### P1-04.8 計器の閾値・定義の一覧表を置き、docs-consistency scan で値の一致を検査する
- 何を: `docs/CONFIGURATION.md`（または glossary）に閾値の表を 1 枚置く — 列 = 値・置き場所・所有 ADR・較正日・モデル依存か・再較正の読み（退役条件は所有 ADR の plan を引く）、行 = 下の計器閾値 8 値・`core/thresholds.py` の 5 定数（較正日の列は .15 の再読で埋まる）・この時点で在るモデル依存の定数（P1-07.11 の runbook はこの表を引き、着手時に行を足すだけ）。`docs_consistency_scan.py` に表と定数の一致検査を 1 本だけ足す（新 registry は作らない。P1-06.4 は env キーの登録簿だけを持ち、閾値の表と検査は持たない）。表に「knowledge growth」の定義（分母・tombstone / soft_invalidated の扱い）を 1 行で固定し、`weekly-analysis.sh` の state diff と `state_invariant_check.py` が `core/knowledge_store` の同じ件数関数を使う。`state_invariant_check.py` に `orphan_vectors`（INFO）を足す。
- 根拠: `core/thresholds.py` は 5 定数のみ（SIM_DUPLICATE / SIM_UPDATE / DEDUP_IMPORTANCE_FLOOR / CLUSTER_THRESHOLD_INSIGHT / MAX_BATCH）、600 / 14 は `never_selected_metrics.py:52, 59`、0.80 / 0.3 は `config/domain.json:13-14`、27 / 83 は `value_layer_due_check.py:580-581`、3.5 は `_census_series.py:21`、300 は `pipeline_watchdog.sh:34` / `weekly-analysis.sh:220` の state diff と `state_invariant_check.py:196-200` の soft_invalidated 率は別計算 / `knowledge_store.py:170 prune_orphan_vectors` は `migrate-knowledge-sidecar.py --prune` からのみ、`state_invariant_check.py:185-194` は `missing_embedding` のみ、`SidecarConsistency.orphan_vectors`（`pattern_embeddings.py:79`）は既にある。
- 完了条件: 表が 8 値と `core/thresholds.py` の 5 定数を網羅して 6 列を持ち、scan の一致検査 1 本が不一致を findings に出す（P1-06.4 / P1-07.11 に別の閾値表と検査が無い — 各束側）。2 スクリプトの件数が同一関数由来（テスト 1 本）。invariant check の出力に `orphan_vectors` 行。
- 規模・整合: M / repair   出典: OI-28 OI-30 CP-14 R4-CUT Merge（.15 の較正日列・P1-06.4 (b)・P1-07.11 の表を 1 枚に）

##### P1-04.9 同名指標・同一分類の重複定義を 1 箇所にする（reply_rate・hallucination 分類）
- 何を: `comment_outcomes.py` の `reply_rate` を `replied_fraction` に改名し、`core/metrics.py` の定義を glossary に載せる。`scripts/skillsel_reading.py::classify` を `selection_metrics.classify_hallucination` の薄い wrapper にし、pin テストを「同一関数」の確認に縮める。
- 根拠: `core/metrics.py:25, 105`（replies_received / 送信総数）対 `core/comment_outcomes.py:527`（replied / total、skill 単位）/ `selection_metrics.py:359` と `skillsel_reading.py:207` の 2 実装、`skill_confusion.py:11-18` が手動版を規則を固定した基準（"froze the rule"）と記す。
- 完了条件: `grep -rn reply_rate src/` が 1 定義のみ。分類ロジックの本体が 1 箇所。
- 規模・整合: S / repair   出典: OI-26 OI-27

##### P1-04.10 eval 層（ADR-0089）に Consumption plan を置き、ack の儀式化を止める
- 何を: ADR-0089 に Consumption plan（リリース前と comment path の ADR 追補時に走らせる。4 連続 ack のみなら撤去候補）を追補し、Revisit condition (a) が発火済みであることを注記する。ADR-0089 への追補はこの項目が 1 本（日付 1 つ、D-P1-04-3 / D-P3-01-2 = 2027-02-06 の後）で持ち、.12 の deepeval 撤去・P1-07.15 の seam 固定文 1 行・P3-01.2 の研究証拠としての位置づけ・D-P3-01-2 A（開発用回帰ゲート）・D-P1-04-3 の結論を段落として寄せる（ack と `check_staleness.py` のコード変更は先に入れてよい）。ack に `paths_considered` と commit range を必須化し、`check_staleness.py` が ack 連続 3 回 / 45 日超過、または ack 以降に `adapters/moltbook/{feed_manager,relevance_shadow,relevance_cache,llm_functions}.py` の変更があれば「re-baseline suggested」に格上げする（advisory のまま）。v2.13.0 手順への eval 実行は → P0-06。
- 根拠: `evals/baselines/comment_golden-2026-09-12.ack.json` の 4 ack（09-19 / 09-25 / 10-07 ×2、理由はすべて「コメント生成経路の prompt は不変」）/ ADR-0089:1125-1131 Revisit condition (a)「3 回以上の ack で見直す」は既に発火 / `evals/check_staleness.py:10`「never a FAIL, because a stale baseline blocks nothing」/ 09-12 以降は実測なし、`docs/glossary.md:217`「Deliberately outside both verify.sh and tests/」。
- 完了条件: ADR-0089 の `## Amendment` が 1 本だけ増え、plan 節 + Revisit (a) 発火の注記と上の寄せた段落を持つ。次回 ack が範囲付き。上限超過で理由付き warn（テスト 1 本）。
- 規模・整合: S / repair   出典: OI-35 OI-37 TQ-29 R3-ADR Merge-03

##### P1-04.11 eval baseline を取り直し、comparability と fixture を本番に揃える
- 何を: D-P3-01-2 / D-P1-04-3（2027-02-06）の後に行う。両方が推奨どおり（D-P3-01-2 A・D-P1-04-3 B）なら「smoke として baseline 1 行」（2 check の smoke の baseline を 1 回取り直すだけ）に縮める。そうでなければ `run_eval.py::sampling_state()` に `selection_temperature` / `selection_num_predict` を足して comparability field にし、fixture を再 snapshot（skills 53）して baseline を取り直す。以後「月次 identity staging の承認後に snapshot → full run（約 19 分）→ baseline 承認」を 1 サイクルとして `docs/CYCLES.md` #5 に 1 行、`check_staleness.py --json` を weekly materials の Instrument Census 隣に advisory 1 行で載せる。
- 根拠: `core/skill_selection.py:94-103`（selector は 2026-09-20 から t=0、以前は 1.0）、09-12 baseline manifest は temperature 1.3（comment）と sampling 5 key のみ / `run_eval.py:160-167`「次の baseline 取り直しで足す（2026-08-16 判断）」のまま 08-31・09-12 の取り直しを経過 / `evals/fixtures/agent_home/manifest.json` snapshot_at 2026-08-08・49 ファイル、baseline の assets_sha256 は 08-08 以降不変（再 snapshot は 1 回のみ）/ `weekly-analysis.sh`・weekly-gate SKILL.md に `check_staleness` の呼び出しなし。
- 完了条件: `check_staleness` が 09-12 baseline を STALE と報告し、新 baseline が承認される。manifest の snapshot_at が直近の月次 staging 以降。materials に staleness 行。
- 規模・整合: M / repair（推奨どおりなら S）   出典: LP-20 OI-36 TQ-30   順序: D-P3-01-2 / D-P1-04-3（2027-02-06）の後

##### P1-04.12 deepeval 依存を落とす
- 何を: `evals/adapter_deepeval.py` と `run_eval.py::_deepeval_report`、`eval` dependency group を削除する。ADR-0089 には単独の追補を書かず、.10 の 1 本の追補に 1 段落を寄せる。`.claude/verify.sh` の type gate と CI（`uv sync --group eval`）から eval group を外す。
- 根拠: `evals/adapter_deepeval.py:37 PrecomputedVerdictMetric`（pipeline の verdict を写すだけ）、`evals/run_eval.py:365-367`「Failure here never fails the run — the normalized JSON is the contract」/ `.claude/verify.sh:139-144`（type gate だけ eval group を同期、pip-audit 面の拡大を「意図的な受容」と記す）/ `.github/workflows/verify.yml:43-46` / golden 読み・judge・比較はすべて自前（`evals/dataset.py` / `judging.py` / `compare.py`）。
- 完了条件: `verify.sh` が eval group を sync しない。`tests/test_eval_layering.py` が「deepeval を import する module は 0」に変わる。pip-audit の対象 package 数が減る。
- 規模・整合: S / repair   出典: LP-21

##### P1-04.13 抽出前 novelty gate の冗長性を 1 回の replay で読み、retire か節約額の明記かを決める
- 何を: RFC-0041 の凍結版 replay 集合で「gate が止めた cluster のうち後段の duplicate judge も止めるもの」の比率を 1 回読む。冗長なら gate を retire（ADR-0111 追補）、残すなら GPU 節約額を数字で書く。
- 根拠: ADR-0111:26「The pre-extraction novelty gate does not separate populations」、:48-56（段構成は gate を先頭に維持）、:101-105（両段 fail-open）/ `core/insight_novelty.py:657-658`（chunk ごと num_predict 2,000、t=0）/ `core/insight_stages.py:369-371`（enum 拘束の duplicate judge、t=0）/ skill `llm-pipeline-layering`: 成果物を judge するコールは成果物の後に置く。
- 完了条件: ADR-0111 追補 1 本（比率と判断）。
- 規模・整合: M / repair   出典: LP-18

##### P1-04.14 census の KEPT に期限を付け、standing register 化を止める
- 何を: `_census_registry.py` の KEPT 行（`insight-worth.jsonl` / `noise-*.jsonl`）に `until`（日付か条件: 例「公開 data repo に凍結版を置いた後」）を必須化し、`skill-usage-*.jsonl`（ADR-0036 sunset、手動 rm 待ち）も同列で一度に片付ける。期限超過は census が ORPHAN で出す。
- 根拠: `scripts/_census_registry.py:190-191`（kept 2026-09-26 gate、期限なし）/ ADR-0101:121-122「No standing register is kept」/ CLAUDE.md:98（skill-usage は歴史的データとして残置・手動 rm）。
- 完了条件: KEPT 行すべてに `until`。`tests/test_instrument_census.py` に期限超過 → ORPHAN のケース。
- 規模・整合: S / repair   出典: OI-45

##### P1-04.15 insight / dedup の較正定数を現 register で 1 回再読し、動かすか据え置きの dated note で閉じる
- 何を: 新計器を建てず、`docs/evidence/adr-0009/`（`threshold-sweep.py` / `threshold-calibration-20260417.md`）の 3 点較正をそのまま現 store（data repo `knowledge.json`、10,985 行 = 較正時の 113 倍）で 1 回再実行し（read-only、定時窓外）、結果で (a) 定数を動かす → `core/thresholds.py` の docstring と所有 ADR の追補を同 PR、(b) 動かさない → 各定数の docstring に「2026-06-23（ADR-0060）以降の register では非選択的 / 据置の理由」の dated note、のどちらかで閉じる。dedup 側（`SIM_DUPLICATE` / `SIM_UPDATE` / `DEDUP_IMPORTANCE_FLOOR`）は常に再読し、insight 側（`CLUSTER_THRESHOLD_INSIGHT` / `MIN_PATTERNS_REQUIRED`）の再読は D-P0-01-1 = A（insight 継続）のときのみ。この項目は再読の手順だけを持ち、較正日は .8 の表の列に入る。
- 根拠: `core/thresholds.py:28-34`（`SIM_DUPLICATE = 0.90`、calibrated 2026-04-17、97 patterns）/ `:55-60`（`CLUSTER_THRESHOLD_INSIGHT = 0.70`、較正は `docs/evidence/adr-0009/threshold-calibration-20260417.md`、「Pattern text is short」）/ `core/insight.py:63 MIN_PATTERNS_REQUIRED = 3` / `docs/adr/0060:9`（2026-06-23、per-episode grounded distill で register が変わった）/ `docs/adr/0074:39-46,148`（2026-07-09: 32/32 cluster が centroid cosine 0.795–0.90、「no separation exists …」= 0.70 床は現 register で非選択的）/ `grep -c '2026-1' src/contemplative_agent/core/thresholds.py` → 0（2026-06-23 以降の較正日も note も無い）。旧チャットの関心「ADR-0060 で圧縮は insight へ移ったが insight の較正は旧 register のまま」が草案に無く、.8 は定数を表に載せるだけ、P0-01.1 は `min_size=3` のみだった。
- 完了条件: `core/thresholds.py` の dedup 側 3 定数に、D-P0-01-1 = A なら insight 側の定数にも、2026-06-23 以降の較正日か dated note がある（`grep -c '2026-1' src/contemplative_agent/core/thresholds.py` ≥ 3、A なら ≥ 5）; .8 の表の較正日列が埋まる。
- 規模・整合: S / repair   出典: R1-OWN-02

##### P1-04.16 読み手の種別（人間 / Claude Code 対話 / headless / code）で計器の消費計画を書き直す（T4 第 2 回 10-17）
- 何を: T4 第 2 回（10-17）のチェックリストに「読み手の種別: 人間（briefing の 1 行）/ Claude Code 対話 / Claude Code headless（`claude -p` の weekly-report）/ code（決定論）」の列を足し、本ロードマップの instrument 項目の消費計画 (a) をこの 4 値で書き直す。10-17 の T4 は 4 値表まで。人間の 1 行が無い計器の振り分け — (i) briefing の 1 行に昇格、(ii) headless 専用と明記して負荷系列 (ii)（P2-01.3）に計上、(iii) 撤去 — は D-P2-02-1（11-28）の結論の後、12 月の平日か次の T4（2027-01-09）で決める。
- 根拠: `docs/adr/0101:68-70`（(a) 名指しの消費者と cadence。「必要になったとき」は不可）; `.claude/skills/weekly-gate/SKILL.md:109`「オーナーは週次文書・findings を直接読まない」; `scripts/weekly-pipeline.sh:91,352`（無人チェーンは `claude -p "/weekly-report …"` の 1 セッション）; `docs/adr/0080:164-172`（08-26 追補 §A: オーナーと Claude Code の日常的関与なく自己調節）; 草案で消費計画の読み手を「土曜ゲート / weekly-gate Step N / weekly-report」と書く instrument 項目は 20 件以上、「無人セッション」と区別して書く項目は 0（P2-02.1 の二分のみ）— 08-26 追補 §A の「Claude Code の関与 → 0」が達成されると、読み手が Claude Code セッションである計器は読み手を失う。
- 完了条件: `scripts/instrument_census.py`（ADR-0110）の出力か T4 記録（ADR-0101 Review-when）に 4 値の表が 1 回出る; 読み手が「人間」の計器は weekly-gate SKILL.md の Step に 1 行で対応づく; (i)〜(iii) の判定が所有 ADR の dated note にある（D-P2-02-1 の後、遅くとも 2027-01-09）。
- 規模・整合: S / neutral（棚卸しの記録 — 読み値を出す計器ではない）   出典: R1-NS-03   順序: SKILL.md の T4 チェックリスト列は 10-17 の週の同梱 PR（R2-GATE Merge-01）、(i)〜(iii) は D-P2-02-1（11-28）の後


**依存**
- P0-02（RFC-0046 後始末 3: 旧 relevance arm・ADR-0112 decision shadow の削除、2026-10-15 以降）— T4 の対象集合がここで変わる
- P0-01（10-10 ゲート: insight 継続の読み）— .15 の再較正の前提（.5 の窓は 10-10 のゲートでは取らない — 3 週窓の手動実行）
- 順序: .14 の census 変更と P2-01.1 の登録行の修正は `_census_registry.py` の別の行の差分で順序不問; P1-05.1 の Step 6g は先行列の 10-17 の週（P2-01.10 の SKILL 同梱 PR）で、.4 の Step 6c とは別 PR
- P1-02.6（RFC-0047 の終端、D-P1-02-2 = 2027-01-09）/ P1-15.1（face 台帳）: Face A の台帳行と D-P1-04-3 A の再検討時期
- D-P3-01-2（2027-02-06、D-P1-04-3 と同じ回）: .10 の ADR-0089 追補 1 本の前提
- 順序: P2-01.9（率の区間の規則 `scripts/_stats.wilson_ci`、10-31 の週）は .5 の読み（10-24）より後 — .5 は同じ Wilson の式を script 内に持ち、P2-01.9 が入ったら置き換える
- 順序: 同 PR — P0-01.8 / P2-01.2 / P2-01.10 / P2-01.11（10-17 の週の SKILL.md 同梱 PR の同乗者）と .16 の T4 チェックリスト列
- P2-02.1 / D-P2-02-1（Claude Code 関与の二分）: .16 の 4 値の (i)〜(iii) の振り分け
- 順序: 同じ PR 群 — P0-03.11（`real_sample.jsonl` の除去）と .7 の退役判断
- RFC-0012（view 由来の循環性）: .2 の view_metrics plan / RFC-0048（出口）: .4 の exit reading 統合
- → 参照元: P1-02.1（.3 が先に直す RFC-0011 の Status 節を test で固定する）、P1-06.4 / P1-07.11（閾値の表は .8 の 1 枚を引く）、P0-06（v2.13.0 — .12 を release 前に、release 手順への eval 実行）、P2-06（gate briefing の陽性時のみ展開）、P3-05（DATACARD の形式表）、P2-06.2（staged item の 3 軸 join — surprise の名指しの消費者、.2 で surprise を撤去候補にしない理由）、P1-08（consumer の無い script / fixture の退役項目を .7 に吸収）、P1-01.1（.16 の読み手 4 値を消費計画が使う）、P1-01.2 / P1-03.4（.1 の T4 記録を読んでから着手）、P1-07.15 / P3-01.2（ADR-0089 の段落を .10 の 1 本の追補に寄せる）、P1-03.3（.1 の `per ADR-0101 T4` 形の Note は typed edge test の対象外）


#### P1-05 観察台帳と週次計器の機械化（baseline・expiry・自己故障）
- 狙い: 週次ゲートの負荷→0（ADR-0080 の 08-26 追補 §A）に対し、観察台帳（RFC-0010 / ADR-0099）は「毎週の再演を 1 行に圧縮する」装置のはずが、帯が散文・expiry が自由文・批准経路が未実装で open が 13 行まで単調増し、scan の abstain は緑に隠れる。code が列挙し model は転記するだけ、の形に戻す（CLAUDE.md 開発原則、skill `llm-pipeline-layering`）。
- 期限・順序: 着手 2027-01-09 の土曜ゲート（§4.0）。期限 2027-01。先行項目: .1（批准経路の実装）と .4（O-017 の archive）は 10-17 の週（§4.0 の先行列）、.5（enja_drift）は 11-21 の週（§4.0 の先行列）。滞留 4 件の裁定（D-P1-05-1）と O-009 / O-015 の archive は 10-24 の土曜ゲート（推奨 B なら nonce / question-closer の 2 件は保留とし、.8 の列ができた後に裁定）。.1 のコマンド（`declare-baseline` / `reject --id`）の PR は Step 6g の SKILL 同梱 PR より前か同じ PR。.2（帯の構造化）は .1 で宣言された帯と P1-04.8 の定義表を前提に、着手週 2027-01-09 の別 PR で .4 が片付けた帯を読む。.3 の `expiry_rule` と render の印付けは着手週から、「N 週で強制」の規約文は D-P1-05-2（2027-01-16 の土曜ゲート）の後。.7（census 登録行）は P2-01.1 に吸収した。.8（表層カウンタ）は着手週 2027-01-09 に .2 と同 PR か先に入れ（.2 / .3 が列を読む）、materials の配線は現行の `weekly-analysis.sh` の形で書き、P2-04.13 PR-A（2027-02-06 の着手）が stage の形を変えたら合わせる。`weekly-gate/SKILL.md` の変更は Step ごとに先行列の週に合わせる: Step 6g（.1 の所有）は 10-17 の週の SKILL 同梱 PR（P2-01.10 と同じ PR。10-24 の裁定の前に入る）、Step 5b の 1 行（.5 の所有）は .5 の修理本体と同じ 11-21 の週の PR。.2 の `regime` 付け替え（score4 enforce 09-28 / temperature 0 09-26 をまたぐ帯）は .4 と同じ PR にせず、着手週の .2 の PR で行う。この束の決定: D-P1-05-1（2026-10-24）、D-P1-05-2（2027-01-16）。
- 束の完了条件:
  - `observation_ledger.py` に `declare-baseline` があり、`baseline_proposal` の未裁定が 0（裁定行が結び付く。D-P1-05-1 で保留した 2 件は .8 の列による裁定の後）
  - `baseline` 行 6 本すべてが `band: {metric, low, high, unit, source}` を持ち、`render` が当週読み値（.8 の表層カウンタの列を含む）の in / below / above を出す
  - `observation` 行の expiry に機械形式（`expiry_rule`）があり、同一 metric の open が最大 1、8 週超の open に proposal / RFC が紐付く
  - `pipeline/docs-consistency/*.json` の `errors` が空の週が 2 週続き、abstain が gate briefing と PIPELINE-STATUS に件数で出る
  - census の `pipeline-metrics.jsonl` 行が OK を返す（実装は P2-01.1。この束では参照のみ）

##### P1-05.1 baseline の批准経路（`declare-baseline` + ゲート Step）を作り、滞留 4 件を裁定する
- 何を: `observation_ledger.py` に `declare-baseline`（人間同席ゲート用、`declared_by: gate`）と `reject --id`（却下も行として残す）を足し、weekly-gate SKILL.md に Step 6g「baseline proposals の採否（採用 / 却下 / 保留）」を追加する。滞留 4 件（08-28 ×2、09-04、09-25）を 10-24 の土曜ゲートで裁定する（D-P1-05-1、熟慮）。
- 根拠: data repo `reports/analysis/observation-ledger.jsonl`: `baseline` 6 行はすべて `declared_by: bootstrap`（2026-08-26）、`baseline_proposal` 4 行に対応する `baseline` 行なし / `scripts/observation_ledger.py:63` `_SESSION_TYPES = {"observation","archive","baseline_proposal"}`、:104-113 は metric 名一致の `baseline` 行追記で proposal を閉じる設計（経路はあるが書き手が無い）/ `grep -c -i baseline .claude/skills/weekly-gate/SKILL.md` → 0 / `config/prompts/weekly-analysis.md:88`「active baselines are declared by the Saturday gate or the bootstrap」。
- 完了条件: 未裁定 proposal 0（D-P1-05-1 で保留とした 2 件は .8 の列による裁定まで滞留週数の上限から除く）。SKILL.md に Step 6g。render が proposal の滞留週数を出し、以後 2 週を超えない。
- 規模・整合: S / repair   出典: OI-16 WO-08   順序: 10-17 の週（§4.0 の先行列。コマンド `declare-baseline` / `reject --id` の PR は Step 6g の SKILL 同梱 PR より前か同じ PR）、裁定は 10-24 の土曜ゲート（D-P1-05-1）

##### P1-05.2 baseline 帯を構造化し、帯内外の判定を render で機械化する
- 何を: `baseline` 行に `band: {metric, low, high, unit, source}` を足し（6 本: 400–550 / 10–25% / +300..+700 / 2–10% / ~6.0% / 0）、`observation_ledger.py render` が当週の読み値（`selection_metrics` の率、state diff の件数、sampler の volume、`state_invariant_check` の比率）と照合して in / below / above を出す。writer（`weekly-analysis.md`）の帯判定を「転記」に下げる。帯の定義（分母・除外）は P1-04.8 の一覧表を単一ソースにする。`band` には `estimator`（点推定 / 分位）・`windows`（何週から）・`regime`（P3-02.1 の境界表の行 id）を必須にする。「2 週連続 below / above」規則の誤報率は未定義なので、先に ADR-0099 様式の週次読み 6〜7 週分から週間 SD を出し、帯幅 / SD を render に併記する。score4 enforce（09-28）と temperature 0（09-26）をまたぐ帯（weekly output 400–550、hallucination 10–25%）は .4 の再較正と同じ PR で `regime` を付け替える。
- 根拠: `observation-ledger.jsonl` の baseline 6 行は `expected` 散文のみ（例「400-550 published outputs/week (492 in the 2026-08-21 window…」）/ `observation_ledger.py:57` `_ID_RE`、:241 `_validate_baseline_proposal_row` は metric / expected の存在のみで帯照合の関数なし / `config/prompts/weekly-analysis.md:42-47` が帯比較を writer の散文義務として課す / `baseline` 6 行のキーは `declared / declared_by / expected / metric / source / type` のみで n・窓・区間のキーが無く、出所は単一窓 `weekly-2026-08-21`（ADR-0099:19,112）。
- 完了条件: 6 baseline すべてに `band`（`estimator` / `windows` / `regime` を含む）。render 出力に機械判定列と帯幅 / SD の併記。率の帯照合の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）で、点が帯内でも区間が帯をはみ出せば「判定不能」。`tests/test_observation_ledger.py` に in / below / above の 3 ケース + 「区間が帯をまたぐ → 判定不能」の 1 ケース。
- 規模・整合: M / instrument   出典: OI-15 R2-STAT F-5 R2-STAT-02   順序: 着手週 2027-01-09 の別 PR（.4 が 10-17 の週に片付けた帯を読み、`regime` の付け替えもこの PR）
- 消費計画: (a) 土曜ゲートの人間が weekly materials の Ledger 節（render の baseline 1 行 = metric / 当週読み値 / in・below・above、帯幅 / SD）を毎週読む (b) 2 週連続の below / above（区間で読む: P2-01.9）で observation を起票するか帯を再較正する（.4 の最小持続ルール、再較正は .1 の `declare-baseline`）。帯内の週は何も決めない (c) 撤去条件: 当該 baseline 行が archive / supersede で閉じた時にその列が消える。6 本すべて閉じれば render の機械判定列を外す

##### P1-05.3 expiry に機械形式を足し、長期 open の出口規約を置く
- 何を: `observation` 行に `expiry_rule: {"kind": "unchanged_weeks", "n": 4}` 等の副形式を足し、`render` が「発火済み（archive 候補）」と「8 週超過」を印付けする。台帳規約に「8 週継続した観測は baseline_proposal へ転換するか RFC を起票して archive」を追加する（D-P1-05-2）。schema に `supersedes` を足し、`append` が同一 metric の open 2 本を拒む。
- 根拠: open 13（observation 17 − archive 4）、O-002 は 2026-06-26 から 14 週、O-001 は 07-10 から 12 週 open / `observation_ledger.py:224-225` は expiry の存在のみ検査、:154 は `[expiry: …]` を表示するだけ、:125 `_weeks_since` は数えるだけで閾値なし / 10-02 報告 Ledger 節の `unchanged` 行は 11 / `weekly-analysis.md:87`「an observation with no way to leave the ledger is a permanent tax on every future week」。
- 完了条件: 4 週 unchanged の O-id が render で自動候補化される。8 週超の open が 0 か各々に proposal / RFC が紐付く。同一 metric の open 2 本を含む delta を `append` が拒む（テスト）。
- 規模・整合: M / repair   出典: WO-03 OI-19 OI-17

##### P1-05.4 現行の矛盾行（O-009 / O-015、O-016 / O-017）を次のゲートで片付ける
- 何を: O-009（帯上）と O-015（帯下）は同一指標の 2 open — 09-25 の temperature-0 帯（0–10%）を .1 で批准すれば（D-P1-05-1、10-24）両者の expiry（「gate が帯を再較正したら」「gate が temperature-0 の baseline を宣言したら」）が同時に発火するので archive する。O-017 は expiry 第 1 節（face gate の keep / kill 記録）が 10-04 の keep で発火済み → 次のゲート（10-17）で archive。O-016 は gate が volume 帯を再確認するか、「2 週連続で帯外のときのみ open」の最小持続ルールを規約に入れる。temperature-0 帯の批准と同じ PR で、.2 の `regime` 付け替え（09-26 / 09-28 をまたぐ帯）を行う。
- 根拠: 台帳 O-009（2026-09-04、26.6%）expiry「…or when the gate re-calibrates the declared band」、O-015（09-25）expiry「when the Saturday gate declares a baseline for the temperature-0 regime…」、10-02 報告 O-009 行「The in-band count toward the expiry does not advance」（読みは 2.8%）/ O-017 expiry「when the rfcs/0046 face gate records keep or kill」、`rfcs/0046:180` face gate keep（2026-10-04）/ O-016: 391 対 400–550（1 週・2.3%）、帯の n は台帳に無い / `core/report.py:166-177` は P(top) と旧 relevance を別名で表示。`domain.json:13` の `relevance: 0.80` 削除は RFC-0046 後始末 3 → P0-02。
- 完了条件: O-009 / O-015 / O-017 に archive 行。O-016 は archive か「2 週連続」規約の明記。
- 規模・整合: S / repair   出典: OI-17 OI-18 R2-STAT F-5   順序: 10-17 の週（§4.0 の先行列。O-009 / O-015 の archive は 10-24 の裁定の後）。.2 とは別 PR

##### P1-05.5 docs-consistency scan の `enja_drift` 自己故障を直し、abstain を緑に隠さない
- 何を: `docs_consistency_scan.py::git_last_commit_ts` が ADR-0103 の timestamp を取れない原因を本番 clone で特定して直す（本クローンでは `git log --name-only -- docs/adr` に 0103 が現れる → 本番側の履歴 / CWD の差が原因と推測）。weekly-gate Step 5b に「`errors` 非空なら findings 0 でも『検査 X abstain』を提示、2 週続いたら draft 起票」を足し、`PIPELINE-STATUS.md` に各 stage の `readings: N / abstain: reason` 列を加える（JSON の件数と errors の転記のみ）。
- 根拠: data repo `pipeline/docs-consistency/docs-consistency-2026-{09-11,09-18,09-25,10-02}.json` の `errors` に `enja_drift GIT_FAIL "no timestamp: docs/adr/0103-…"`（4 週連続。08-14〜09-04 の 4 件は errors=[]）/ `scripts/docs_consistency_scan.py:251-254` / SKILL.md Step 5b（:219-228）は findings と `readings.freshness` のみ、`errors` への言及なし / `scripts/pipeline_watchdog.sh:34` MIN_REPORT_BYTES=300（報告サイズのみ）、`reports/PIPELINE-STATUS.md` 2026-10-10 は全ステージ ✅。
- 完了条件: errors=[] の JSON が 2 週続く。abstain の週に briefing に 1 行、PIPELINE-STATUS に件数が出る。ADR の en / ja は D-P1-09-1 A の運用規則（Status 行と `## Amendment` 見出し + 1 行要約は ja も同 PR、Note 本文は en のみ）を前提（決定前）に、`enja_drift` は Status / 見出しの差分だけを数える（en だけの Note 追加を検出しない test 1 本）。
- 規模・整合: S / repair   出典: OI-09 WO-32 OI-46 R3-ADR Fix-07   順序: 11-21 の週（§4.0 の先行列）。Step 5b の 1 行も同じ PR

##### P1-05.6 log anomaly sweep をローテーションに耐える形にする
- 何を: `log_anomaly_sweep.py` の state に前回 corpus の行数とファイル集合を持たせ、Δ を率（signature 件数 / 総行数）で出すか、ローテーション検出時は「baseline reset」1 行を明示して次週から再開する。
- 根拠: data repo `reports/analysis/weekly-2026-10-02.md:168-169`「Log Anomaly Sweep corpus shrank 87% (990,722 → 122,996 lines) through rotation, so this week's 🆕 and Δ are not comparable」/ `scripts/log_anomaly_sweep.py` docstring:7-8, 23-27（novelty → frequency delta、state は TSV）/ `scripts/rotate-log.sh`（ollama-restart が `ollama-serve.log` を回す）。
- 完了条件: ローテーション週の報告に Δ が率で出る、または reset 行が 1 行だけ出る（テスト 1 本）。
- 規模・整合: S / repair   出典: OI-29

##### P1-05.8 台帳の振る舞い観察を決定論の表層カウンタで照合する
- 何を: `scripts/cross_day_duplicate_scan.py` の隣に兄弟 script を 1 本置き（または同 script を拡張し）、同じ出力境界（件数・比率・日付・固定語彙。本文・post id・相手の名前は出さない、ADR-0083）で週ごとに 5 列を出す — (1) 種類別（comment / reply / post）の question-closer 率（分母つき）(2) 公開本文中の `untrusted_content_[0-9a-f]{16}`（nonce）の件数 (3) 採用 skill の H1 見出しを含む本文の件数 (4) Context < 300 字の件数と出力 / 入力長比の中央値 (5) wrapper 語彙（`untrusted_content` / `learned_skills` など固定の語）を含む本文の件数。`weekly-analysis.sh` の materials 段（Cross-Day Duplicate Scan と同じ場所）で走らせ、weekly-report の執筆者は数を書き写すだけにする。照合先は台帳の振る舞い観察 O-004（短入力の膨張・wrapper）/ O-005（question-closer の置き換え）/ O-013（skill の H1 見出し）と、D-P1-05-1 で保留した baseline_proposal 2 件（question-closer 5–15%、nonce 0）で、.2 の帯判定と .3 の満期判定（`expiry_rule`）がこの列を読む。生成側には触らない（剥がす・言い換えるのは steering で、`config/prompts/principles.md:22` の語句ブロック禁止に当たる）、LLM 判定も使わない（第 5 章、ADR-0106 D4）。
- 根拠: 本体 `2cad850` の `config/prompts/weekly-analysis.md:36-40`（満期の判定は報告の執筆者に任される）・`:92`（材料 (6)「exact-identity claims come only from here」— 決定論の取り込みは重複の走査 1 本だけ）; `scripts/cross_day_duplicate_scan.py:1-12`（出力境界の先例）と `weekly-analysis.sh:485-504`（その配線）; `core/llm/guard.py:140` の `_sanitize_output` は wrapper / nonce を剥がさない; `config/prompts/comment.md:3`「A brief post invites a brief reply」。月別の件数（nonce は 08 月の POST に 19 件・09 月 0 件・10-04 に 1 件、skill 見出しを含むコメントは 06→10 月で 15 / 25 / 6 / 11 / 3 件、Context < 300 字のとき出力の中央値は約 900–1,400 字、10 月の question-closer 率はコメント 7% / 返信 11% / 自投稿 14%）は公開日報 7,964 件の Output ブロックを数えた read-only 集計で、本文は確かめていない。
- 完了条件: materials に 5 列の節が週ごとに出る; 出力境界の test（`tests/test_cross_day_duplicate_scan.py::TestOutputBoundary` と同型: 本文・id・名前が render に出ない）と 5 列の合成 fixture の test 各 1 本; .2 の render が (1)(2) の列で baseline 行の in / below / above を出し、.3 の render が O-004 / O-005 / O-013 の満期候補をこの列で印付けする; 率の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）; D-P1-05-1 で保留した 2 件がこの列の照合で裁定され `gate_item` に 1 行ある。
- 規模・整合: S〜M / instrument（読みであってフィルタではない）   出典: R4-BEHAV-01   順序: 着手 2027-01-09 で .2 と同 PR か先（.2 / .3 が列を読む）; materials の配線は現行の `weekly-analysis.sh` の形で書き、P2-04.13 PR-A（2027-02-06 の着手）が stage の形を変えたら合わせる; 凍結集合では計器行として扱う（P1-01.9、D-P1-01-1 の追加段 B を前提、決定前）。依存: P1-05.1（批准経路、10-17 の週）、P1-01.9（D-P1-01-1 の追加段、11-28）、P2-01.9（区間、10-31 の週）
- 消費計画: (a) 土曜ゲートの人間が render の baseline 行で毎週読む（code → 人間 1 行。読み手の種別は P1-04.16 の 4 値で「人間」） (b) 満期の発火と 2 週連続の帯外れを、執筆者ではなくこの列で判定する（最初の読みで D-P1-05-1 の保留 2 件を裁定） (c) 撤去条件: 各列に対応する台帳行と baseline がすべて archive / supersede された時か、凍結の時の早いほう


**依存**
- P1-04.8（閾値・定義の一覧表）: .2 の帯定義の単一ソース
- P2-01.9（率の区間規則 `scripts/_stats.wilson_ci`）: .2 の帯照合と .8 の率はこの規則で判定 / P3-02.1（装置の境界表）: .2 の `band.regime` が行 id を引く
- P1-01.9（D-P1-01-1 の追加段、11-28）: .8 の script を凍結集合の計器行として扱うかの前提
- P0-02（RFC-0046 後始末 3）: `domain.json:13` の退役閾値の削除、O-017 の前提
- P0-01（10-10 ゲート）: O-017 archive と proposal 裁定の最初の機会（裁定は 10-24）/ P2-01.10（10-17 の週の SKILL 同梱 PR）: .1 の Step 6g が同乗する
- P2-01.1（census 登録行の修正: 旧 .7 の吸収先。`pipeline-metrics.jsonl` の読み手）
- D-P1-09-1（2027-01-23、推奨 A を前提 — 決定前）: .5 の `enja_drift` が数える差分（Status / 見出しのみ）の規則
- P2-04（検知面）: watchdog の拡張はそちら、ここは PIPELINE-STATUS の転記列のみ。P2-04.13 PR-A（2027-02-06 の着手）は .8 より後なので、.8 は現行の materials 段の形で書き PR-A が合わせる
- RFC-0010 / ADR-0099（台帳の所有）、ADR-0107 / 0110（census）
- → 参照元: P2-06（読み量削減: render の発火候補一覧が gate の読み面になる）/ P2-01（負荷計器: open 件数・滞留週数が負荷系列の材料）/ P1-03.9（.2 の「2 週連続帯外」規則に基礎率・待ち時間の 1 行を添える）


#### P1-06 コード構造の最後の窓（OllamaBackend・core 内層契約・規約の明文化）
- 狙い: 機構層の完成は「止まる」こと（ADR-0080）。止まる前に 1 回だけ触る構造項目（本番経路を契約に乗せる、core 内の方向を機械で固定する、規約を日付つきで文書にする）と、止まった後は「触る時だけ」にする項目（巨大モジュールの分割、綴りの統一）を二分し、後者は第 5 章の延期行（トリガーつき）に載せる。能力は 1 つも増やさない。
- 期限・順序: 着手 2027-01-16 の土曜ゲート（§4.0）。期限 2027-02（P1-01 の凍結判定の前）。順序は 1 行で固定する: P0-02.2（削除 PR）→ .10（小修理束、1 commit）→ .4（env 登録簿）→ P1-08.8（sentinel 検出。.1 PR-A の patch 付け替え漏れを赤にする。2027-01-16 より前）→ .1 PR-A（2027-01-16 の週）/ PR-B（2027-01-23 の週。どちらも P1-11 の sibling 処遇 D-P1-11-2（11-14）/ -3 / -6（12-26）の後）→ 契約固定 PR（.2 の `ignore_imports` 契約 + .3 の AST 検査 + `tests/test_surface_snapshot.py`。2027-01-30 の週）→ .3 の改名 PR（alias 無し。2027-02-06 の週）。§4.0 の先行列にこの束の項目は無いので、.10 / .4 も着手週 2027-01-16 の週に入る（構造 PR の本数には数えない）。閾値の集約は P1-04.8 の閾値表（1 枚）が持ち、この束は env 登録簿だけを持つ。D-P1-01-1 の定義（11-28）の前に置いてよいのは P0-02.2 と .10 / .4（修理・登録簿）だけで、停止リスト（P1-01.3 の期日つき残作業の表）に「凍結前の最後の動かす PR」として載せる。契約固定 PR と .3 の改名 PR は定義の後。構造 PR は 1 ゲート週に 1 本（2027-01-16 / 01-23 / 01-30 / 02-06 の 4 本）。この束が停止リストに持つ最後の行は .3 の改名 PR（今の配置で 2027-02-06 の週）。凍結の verdict は停止リストが空になった週 + 窓で、推奨どおり（D-P1-01-1 の追加段 B・D-P2-07-1 A）なら停止リストの最終行は P2-07.1 / P2-06.2 で、verdict は早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8 の遅い方 + 8 週で、早くて 2027-04-03。巨大モジュールの分割と module 状態・綴り・遅延 import・Decision 語彙（「触る時だけ」）と他の延期分は停止リストの表には入れず、第 5 章の延期行に載せるだけで着手しない。`cli/runtime.py` の env 読み（.4）は P0-02.2（:173-208 削除）→ P0-05 preflight → P1-07.13（:295-316）の列の P0-02.2 の後。この束の決定: D-P1-06-1（鏡 4 関数、2027-01-16）、D-P1-06-2（DTO 境界、2027-01-16）。
- 束の完了条件:
  - `python -m contemplative_agent.testing --backend contemplative_agent.core.llm.ollama:OllamaBackend` が CI では `--require static` で exit 0、Mac（土曜ゲート）では `--require runtime` で exit 0 を `docs/evidence` に 1 行（kit の既定 `DEFAULT_REQUIRE = LEVEL_STATIC` `testing/backend_contract.py:117` は `generate()` を呼ばない）、`grep -c _post_ollama src/contemplative_agent/core/llm/__init__.py` = 0
  - 「固定テスト」の表が閉じている（R1-FRZ-02 (2)、P1-01.1）: import-linter 契約 6 本（.2、`uv run lint-imports` pass）/ `_` 名の AST 検査（.3）/ `tests/test_surface_snapshot.py` の表面 literal snapshot（.2: CLI の name + tier、launchd label、env キー — いずれも契約固定 PR 時点の実数 —、`config/prompts/*.md` の stem 集合、`KIT_VERSION = "2"`、外向き host 2、`gemma4:e4b` literal の所在）/ `tests/test_ci_config.py` の CI 設定 literal（P1-08.25）/ sentinel 検出（P1-08.8）/ allowlist・否定テスト（P1-08.17 / .18）/ 週次セッションの deny テスト（P1-10.5）/ save 順序テスト（P0-04 の該当項目）。これ以外の tests/ 追加は停止リスト
  - tests / scripts / evals から `contemplative_agent.core.llm` の `_` 名 import が 0 件、`__all__` が存在、`core/llm/__init__.py` に `_x as _x` の再 export 0、alias 0
  - `core/env.py` 登録簿 + `tests/test_configuration_doc.py` green で `docs/CONFIGURATION.md` / `.env.example` の未記載 0（閾値の表は P1-04.8 の 1 枚）
  - `.claude/verify.md` に関数長・拡張複雑度（.7）・ログ水準（.8）・鏡 4 関数の台帳（D-P1-06-1 B）が日付つきであり、ADR-0062 に「`verification_parse.py` を分割しない」追補（.7）があり、`uv run ruff check --select RUF100 src` が 0
  - 第 5 章の延期行に「触る時だけ」が載っている: 巨大モジュールの分割 4 本 + module 状態・綴り・遅延 import・Decision 語彙の 4 件 + 延期分（BLE001 / pyright スコープ、`exc_info` sweep）がトリガーつき（停止リストの表には入れない）

##### P1-06.1 OllamaBackend を `LLMBackend` 実装にし、facade から transport を外す
- 何を: PR-A: `core/llm/ollama.py` を新設し `_post_ollama` / `_drop_for_output_truncation` / `_finalize_ok` / `_record_ollama_counters` / `_warn_front_truncation` を移す（名前不変、alias 無し = .10 の CLAUDE.md 規約）。同 PR で `tests/test_llm.py` の patch 対象 `"contemplative_agent.core.llm.requests.post"`（59 箇所）を新 module 側（`core.llm.ollama.requests.post` か `OllamaBackend` 境界の stub）に付け替える。PR-B: `OllamaBackend`（frozen dataclass、`model` / `context_window=NUM_CTX` / `generate`）を置き、`_backend=None` の既定を `OllamaBackend()` にし、`__init__` は re-export + `configure` + 分岐のみ、`scripts/check-sibling-backends.sh:32-34` の一覧に加えて kit を実行する。順序は .4 の後、契約固定 PR の前（1 ゲート週に構造 PR 1 本: PR-A は 2027-01-16、PR-B は 2027-01-23 の週）で、P1-08.8 の sentinel 検出を先に入れる（付け替え漏れが実接続になり赤で見える）。
- 根拠: `grep -rn "class .*LLMBackend\|LLMBackend)" src/` → 実装 0（`core/llm/backend.py:141` Protocol、`:207 TokenCountingBackend` Protocol、`testing/backend_contract.py:329` の isinstance のみ。検証済）/ `core/llm/__init__.py:836-839`（`if _backend is not None … else _post_ollama`）・`:924 _post_ollama`・`:1-12` docstring「Transport … stay in this module」（検証済）/ `__init__.py` 1162 行（検証済）/ `tests/` に `_post_ollama` の文字列は HEAD で 0、`tests/test_llm.py` が patch するのは `"contemplative_agent.core.llm.requests.post"` 59 箇所（検証済）
- 完了条件: 3 コマンド — `grep -c _post_ollama src/contemplative_agent/core/llm/__init__.py` = 0 / `grep -c '"contemplative_agent.core.llm.requests.post"' tests/test_llm.py` = 0 かつ新 module 側の patch が同数（現状 59）/ `wc -l src/contemplative_agent/core/llm/__init__.py` < 500（「−300 行目安」は削った）。`core.llm` の公開名集合が不変（`tests/test_llm.py` の import 行に diff なし）。kit の exit 0 は束完了条件の `--require` 2 段。書き換える既存テスト: `tests/test_llm.py` の patch 59 箇所（`TestGenerate` 13 / `TestThinkParameter` 10 / `TestGenerateForApi` 9 / `TestSilentTruncationDetector` 5 / `TestDoneReasonTruncation` 5 / `TestGenerateFull` 4 / `TestGenerateBudgetGuard` 4 / `TestGenerateBudgetClamp` 4 / `TestCircuitBreaker` 3 / `TestClampFloorIsInertOnOllama` 2。patch 文字列のみで test 名は不変）
- 規模・整合: M / repair   出典: CH-03 CH-23 CH-42 R2-IMPL Fix-10 R2-TST Fix-22 R3-TIME Fix-06（週）   順序: P1-08.8（2027-01-16 より前）→ PR-A（2027-01-16 の週）→ PR-B（2027-01-23 の週）

##### P1-06.2 import-linter に core 内層契約と「計器 → 判定経路」禁止契約を足す（今ある辺を pin、新しい辺だけ赤。契約固定 PR）
- 何を: `[tool.importlinter]` に core 内 `layers`（`config / _io / text_utils` < `thresholds / prompts / domain` < `llm` < `embeddings` < 他）を 1 本、`core.selection_metrics / never_selected_metrics / skill_confusion / view_metrics / comment_outcomes.read_* / constitution_shadow` を `adapters.*` と `core.skill_selection / insight / distill` から import 禁止する `forbidden` を 1 本足す。現存の循環辺と関数内 import はすべて `ignore_imports` に列挙して pin する（drain しない。コード移動 0。`percentile` は `selection_metrics.py:408` のまま ignore に載せ、`core/_stats.py` は作らない）。同じ PR「契約の固定」に、.3 の AST 検査（現存の `_` import 15 行は pin。`tests/test_architecture.py` に置く）と `tests/test_surface_snapshot.py`（`test_architecture.py` に同居させない）の表面 literal snapshot 1 本（CLI の name + tier、launchd label、env キー — literal は HEAD の 21 / 8 / 16 でなく契約固定 PR 時点の実数を P0-02.2 / P0-02.9 / P0-05.1 / P1-06.3 の後に採取する —、`config/prompts/*.md` の stem 集合、`KIT_VERSION = "2"`（`testing/backend_contract.py:59`）、外向き host 2（Moltbook / Ollama）、`gemma4:e4b` literal の所在 = `backend.py` のみ）を入れ、docstring に「変更は ADR 追補と同 PR のみ（P0 の PR には遡って効かない）」と書く。固定テストの表には `tests/test_ci_config.py`（P1-08.25）も 1 行で載せる。P1-09 の docs テストは snapshot と表を照合する側に回す。
- 根拠: 循環辺（全件検証済）: `core/domain.py:258 from .llm import validate_identity_content`、`core/embeddings.py:22 from .llm import …`、`core/llm/__init__.py:489 from ..embeddings import`（コメント「module-level import would be circular」）、`core/llm/prompting.py:92,319,329` / `guard.py:452` → `..prompts`、`core/prompts.py:31,51` → `.domain`、`core/llm/decision.py:404,410` → 親 facade / 関数内 import は grep で src 118（core 49 / cli 56）、元項目の AST 計数 103 と同程度 / `pyproject.toml:133-145` は cli → adapters → core のみ / `adapters/moltbook/submolt_scope.py:57 from ...core.selection_metrics import percentile`（検証済）/ `tests/test_architecture.py` は 42 行・テスト 1 本（import 方向）で literal は無く、`tests/test_cli.py:368, 373` も生 vs 生の集合一致/ 21 / 16 は 2026-10-09 の実数（`CommandSpec(` 21 件、`os.environ.get` 16 箇所）で、P0-05.1 が `doctor` を足し（22）、P0-02.2 が `DECISION_FACES` / `DECISION_ENFORCE` の読みと plist 3 キーを消す
- 完了条件: `uv run lint-imports` が 6 契約で pass、`ignore_imports` の件数が verify.md に日付つきで記録、新規の関数内 import / 循環辺が契約違反として赤になる、`tests/test_surface_snapshot.py` の各集合を 1 つ変えると赤（literal は契約固定 PR 時点の実数）
- 規模・整合: S / repair（OI-43 は observation-over-steering ADR-0050/0051/0052 の機械化。CH-22 単体は neutral。コード移動 0 の 1 PR）   出典: CH-22 OI-43（snapshot: R1-FRZ Fix-05 / R1-FRZ-02）R2-IMPL Fix-09 R2-TST-02（表の 1 行）R3-TIME Fix-06（週）   順序: 契約固定 PR = 2027-01-30 の週

##### P1-06.3 underscore 名の越境を閉じる（公開名化・`__all__`・scripts/evals の AST 検査。1 PR、alias 無し）
- 何を: facade の `_` 再 export 18 名のうち tests / scripts が使う 9 名（`_circuit` 17 / `_estimate_tokens` 13 / `_build_system_prompt` 8 / `_load_md_files` 7 / `_measure_input_tokens` 5 / `_get_ollama_url` 3 / `_get_model` 3 / `_prompting` 2 / `_sanitize_output` 1）と `adapters/moltbook/config.py:10` の `_DEFAULT_OLLAMA_MODEL` を公開名へ改名し、呼び手（src / tests 135 行 / scripts・evals 15 行）全部を同じ PR で直して `__all__` を宣言する。互換 alias は置かない（.10）。`tests/test_architecture.py` の「scripts / evals は `contemplative_agent` の `_` 名を import しない」AST 検査（scripts は `root_packages` 外で import-linter が見ない。契約固定 PR で pin 入りで先行）の pin をこの PR で空にする。pyright `reportPrivateUsage` は error にするか入れない（warning は誰も読まない: verify.sh は exit code しか見ない）。
- 根拠: `core/llm/__init__.py:30-129` の `_x as _x` 18 件（検証済）/ tests・scripts・evals の `_` import 計 59 件（検証済）/ sibling（cloud / mlx）は `LLMBackend` / `BackendResult` / `configure` のみで `_` 名 0 件（両 repo 全 .py を grep。**元項目の「sibling も `_circuit` 等を import」は誤り**）/ `pyproject.toml:128 root_packages = ["contemplative_agent"]`
- 完了条件: `grep -rhoE "from contemplative_agent\.core\.llm[a-z.]* import.*" tests scripts evals | grep -c " _"` = 0、`__all__` が存在、`core/llm/__init__.py` に `_x as _x` の再 export 0、alias 0、AST 検査の pin が空で green。sibling の追随 commit は不要。書き換える既存テスト: `tests/conftest.py` / `tests/test_llm.py` / `tests/test_llm_chaos.py` / `tests/test_llm_telemetry.py` / `tests/test_skill_selection.py` / `tests/test_insight.py` / `tests/test_eval_injection_regime.py` の `_` 名 import 行と `patch("…core.llm.prompting._build_system_prompt")` 7 箇所 / `patch("…core.llm._generate_full")` 2 箇所の文字列、`tests/test_llm.py:2029` の `_DEFAULT_OLLAMA_MODEL` assert（test 名は不変。HEAD の grep で確定）。scripts / evals 側は `scripts/skillsel_arm_replay.py` / `evals/run_eval.py`
- 規模・整合: M / neutral   出典: CH-24 CH-25 R3-TIME Fix-06（週）   順序: 改名 PR = 2027-02-06 の週（停止リストの最終行）

##### P1-06.4 env キーの登録簿を正本化する（構造 PR の前。閾値の表は P1-04.8 の 1 枚を引く）
- 何を: `core/env.py` に `ENV_KEYS`（名前・既定・所有 ADR・読む場所・空文字の意味）を置き全 `os.environ.get`（16 箇所 / 12 ファイル）をそこ経由にし、`docs/CONFIGURATION.md` の環境変数表と `.env.example` を登録簿からの生成物にして `tests/test_configuration_doc.py` で差分 0 を assert する（scripts が読む名前（`${VAR:-}`）も表に含む）。P1-09.3 の環境変数台帳と P1-08.17 の `os.environ.get` 列はここに吸収: env キーの call site が `core/env.py` 1 箇所になるので allowlist は自明。閾値（score4 / novelty / circuit を含む）の一覧と定数との一致検査は P1-04.8 の閾値表 1 枚（値・置き場所・所有 ADR・較正日・モデル依存か・再較正の読み）が持ち、この項目は表を作らない。
- 根拠: env 16 種のうち `docs/CONFIGURATION.md` 未記載 4（`OLLAMA_BASE_URL` / `OLLAMA_EMBEDDING_MODEL` / `MOLTBOOK_PIPELINE_STAGES` / `CONTEMPLATIVE_DIALOGUE_PEER_MODULE`）、`.env.example` 未記載 10（`737133e` の書き直し後も同数。検証済）、`.env.example` は README / README.ja / CONFIGURATION のどこからも参照されない（`grep -n '\.env'` 0 件、NEW F8）/ 閾値の置き場所の散在（`core/domain.py:175`・`adapters/moltbook/novelty.py:197-203`・`backend.py:29-30`）は P1-04.8 の表の「置き場所」列で読む
- 完了条件: 登録表 + 照合テスト green で文書の未記載 0、env 表の直前に `.env.example` への 1 行リンク
- 規模・整合: S / repair（登録簿と照合テスト。計器ではない）   出典: CH-37 + DC-21 CU-37 DC-22 CU-16（旧 P1-09.3 の env 台帳分） + P1-08.17（SA-01）の env 列（CH-38 の閾値集約は P1-04.8 へ）

##### P1-06.7 関数長と拡張複雑度の読みを verify.md に記録する（新ルールは足さない）
- 何を: `.claude/verify.md` の C901 節に関数長分布（p50 16 / p90 56 / p95 80 / max 183）と boolop・内包・三項込みの複雑度（ccx p90 9 / p99 15 / max 22、上位: `distill` 9→22 / `compute_diversity` 6→20 / `_apply_points` 8→19 / `_classify_positions` 4→18 / `extract_agent_fields` 1→15）を日付つきで記録し、再調査トリガー「100 行超の関数を新設する PR」を足す。80 行超の 7 本に「密だが正常」の理由を 1 行ずつ。ccx ≥ 18 の 4 本は次に触る時に名前付き述語（`_is_x()`）へ畳む。同じ日付の記録として、ADR-0062 に追補 1 段落「`adapters/moltbook/verification_parse.py`（1,806 行）は分割しない（行数の大半は語彙・規則表、関数は C901 分割済、唯一のゲートは `differential_replay.py` の 0 mismatch）」を書く。
- 根拠: `pyproject.toml:220-232`（C901 = 10、exemption 0、分布 2026-08-31 時点、検証済）/ `.claude/verify.md:124`（PLR0915 は「C901 と重複」で不採用）・`:133`（cognitive complexity 実装時のトリガー）（検証済）/ 分布値は元項目の自作 AST 推定（順位は安定、絶対値 ±2）/ `adapters/moltbook/verification_parse.py` 1806 行・`docs/evidence/adr-0062-parser-rewrite/differential_replay.py` 0 mismatch、関数は `009baee` / `2e878a3` / `5be5ef6` で C901 分割済
- 完了条件: verify.md に日付つき節 + トリガー行 + 7 本の理由行、`docs/adr/0062*.md` に追補（`differential_replay.py` 0 mismatch のまま）。触った後は ccx ≥ 18 の 4 本が 15 未満
- 規模・整合: S / neutral   出典: CH-07 CH-08 AR-11 CH-01（ADR-0062 追補）

##### P1-06.8 ログ水準の規約（文書 4 行）と re-level 2 件
- 何を: 4 行の規約（CRITICAL = 資格情報 / 権限、ERROR = セッションの目的が達成されない、WARNING = 劣化して続行、INFO = 通常）を verify.md に置く。設定由来 WARNING の ERROR 化 2 件（`feed_manager._fail_closed` `:530-536`、`core/llm/__init__.py:546` の telemetry 書き込み失敗）は .10 の小修理束に含める。計器型 `except` の `logger.warning(..., exc)` に `exc_info=exc` を揃え untrusted 本文を含み得る例外は `type(exc).__name__` のみ（`backend.py:376-382` の既存規約）とする sweep は第 5 章の延期行（トリガー: 当該 handler を fix PR で触る時に規約どおりに直す）。`log_anomaly_sweep.py` の ERROR 節は P1-05 側。
- 根拠: `logger.warning` 261 / `error` 16 / `critical` 1（`agent.py:262` のみ）/ `feed_manager.py:530-536`（検証済。`4b85f22` で `DECISION_*` 未設定は本番既定になったが `enforce_no_threshold` 等の設定理由は残る）/ `exc_info=True` 3 件・`logger.exception` 4 件のみ / `backend.py:376-382`（検証済）
- 完了条件: 規約 4 行が verify.md に日付つき、.10 の re-level 2 件が merge
- 規模・整合: S / repair   出典: CH-28 CH-29

##### P1-06.10 凍結前の 1 commit 小修理束（土曜ゲートで人間 commit）
- 何を: `.vulture_whitelist.py:67` の `draft_body`（実体なし）を削除し、`cli/schedule.py` の `_do_install_*` 4 本の免除を揃える。`core/distill.py:99` の `# noqa: E402` import を冒頭へ移す。`PatternEmbeddingStore._ensure_initialized`（`core/pattern_embeddings.py:167-186`）の例外経路で接続を閉じる（現状の ResourceWarning 2 件はどちらもテスト側で P1-08.15 が直す。src 側は原因ではなく小修理のみ）。`adapters/moltbook/config.py:80` を `OLLAMA_BASE_URL = _DEFAULT_OLLAMA_URL`（.3 の公開名化後は公開名）に。`CLAUDE.md:84`「frozen=True（例外なし）」を「DTO / ドメインは frozen。`_` 始まりの module-private accumulator（`_Tally` / `_RegimeAccumulator` / `_WindowCollections`、関数内で frozen DTO へ畳まれる）のみ可」に改訂。R1 で吸収した小片（R1-FRZ-03）: `RUF100` を ruff `select` に足し、不活性 `# noqa: BLE001` 6 件（`feed_seeder.py:92` / `cli/session_cmds.py:260` / `cli/stocktake_cmd.py:111` / `core/constitution_shadow.py:76` / `core/llm/guard.py:321` / `core/memory.py:216`）を削除（旧 .6）/ 設定由来 WARNING の ERROR 化 2 件 `feed_manager.py:530-536`・`core/llm/__init__.py:546`（.8）/ `User-Agent: ContemplativeAgent/0.1`（`client.py:315`）を `importlib.metadata.version("contemplative-agent")` から組む（失敗時 "unknown"。旧 .11 の 1 点）/ 既存 alias を 1 回だけ畳む: `write_text_atomic` の呼び手を `write_restricted` へ、`_ATTR_ALIASES` 2 件を `PromptTemplates` の field 名に揃える（畳めないものは verify.md に日付つきで「残す」と書く）/ CLAUDE.md 開発原則に 1 行「改名・移動は呼び手（src / tests / scripts / evals）全部と同じ PR で行う。互換 alias は置かない（sibling が消費する公開名は `KIT_VERSION` を上げる）」（.3 はこの規約で 1 PR、alias 無し）。
- 根拠: 4 件とも検証済 — `grep -rn draft_body src scripts tests evals` 0 件、whitelist のみ / `distill.py:93-101`（`thresholds.py` は何も import しないので冒頭移動で挙動不変）/ `backend.py:19` と `config.py:80` の 2 重定義、同ファイル `:81-86` 自身が「bare literal は drift の原因」と述べる / `CLAUDE.md:84` / `pyproject.toml:214-217` の select に `RUF100` 無し、noqa 6 件は不活性（検証済）/ `client.py:315`（検証済、pyproject は 2.12.0）/ `core/_io.py:417-428` `write_text_atomic` は 2026-07-06 から thin alias（3 か月後も両名の参照が src に 9 / 9 行）、`core/prompts.py:14-17` `_ATTR_ALIASES` 2 件（検証済）/ 逆の前例: CHANGELOG v2.12.0「the feed-scoring seam was renamed with its tests following」、`testing/` kit は `KIT_VERSION = "2"`（`backend_contract.py:59`）で版を持つ
- 完了条件: 台帳の全名前が src / scripts に実在、src の `E402` noqa 0、`localhost:11434` の定義が src で 1 箇所、CLAUDE.md 改訂、`uv run ruff check --select RUF100 src` が 0、2 箇所が ERROR で出るテスト各 1 件、UA = pyproject 版のテスト 1 件、src に `write_text_atomic` の呼び手 0（または verify.md の「残す」行）、`_ATTR_ALIASES` に同じ処置、CLAUDE.md に改名・移動の 1 行、`_ensure_initialized` の例外経路で接続が閉じるテスト 1 件
- 規模・整合: S / repair   出典: CH-12 CH-13 CH-33 CH-35 CH-11（旧 .6 の RUF100）CH-28（.8 の re-level）AR-08（旧 .11 の UA）R1-FRZ-03 R2-TST Fix-03（sqlite の例外経路）CH-24 CH-36（alias 文言、R4-CUT Merge で旧 P1-06.17 から）

##### P1-06.11 Moltbook client / auth の規律外 2 点（UA の版同期は .10 へ）
- 何を: `follow_agent`（`client.py:794-811`）と `auth.py:97,114` の `response.json()` 直叩きを `_post_body` 経由にし、2xx + HTML（メンテ画面）の `ValueError` を False / 明示エラーに畳む。本番呼び手のない `search()`（`client.py:989`）とそのテストを削除し、末尾の absence コメント（`:1128-1131`）に名を足す。`User-Agent` を `importlib.metadata.version` から組む 1 点は .10 の小修理束に移した。
- 根拠: `client.py:989 def search`、src に `.search(` の本番呼び手 0（検証済）/ `auth.py:97 result = response.json()`（検証済）/ `client.py:736-766 _get_list` の「失敗した読みは空の読み」規律（検証済）
- 完了条件: 2xx + HTML で False / 明示エラーになるテスト 2 件、`grep -n "def search" client.py` 0 でテスト緑
- 規模・整合: S / repair（AR-07 は security by absence の維持。能力は減る）   出典: AR-06 AR-07（AR-08 は .10 へ）

##### P1-06.13 legacy 読み経路の退役条件を ADR-0108 に追補する
- 何を: `knowledge_store.py` の 3 世代読み経路（inline embedding / bare-string 行 / importance 欄）に数値の退役条件「週次 census の `pattern_embeddings.inline_legacy == 0` が 4 週続いたら inline 読み経路と bare-string 経路を削除（v1.x 移行は ADR-0035 と同じく v2.0.x tag へ送る）」を ADR-0108 に 1 段落追補する。削除は条件成立時のみ。
- 根拠: `core/knowledge_store.py` の `legacy` 言及 15 件（元項目は 17。検証で 15 に訂正）/ `core/pattern_embeddings.py:74-108` の `inline_legacy` / `sidecar_absent` カウンタ / 本番 store は 2026-09-12 に `scripts/migrate-knowledge-sidecar.py` で移行済（CHANGELOG v2.12.0）
- 完了条件: ADR-0108 に追補。条件成立後は `knowledge_store.py` の `legacy` 言及が拒否メッセージのみ、`inline_legacy` カウンタ削除
- 規模・整合: S / repair   出典: CH-18   依存: P1-05（週次 census の読み値）


**依存**
- P1-01（凍結判定・停止リスト = P1-01.3 の期日つき残作業の表: .3 の改名 PR がこの束の最後の行。「触る時だけ」と延期分は第 5 章の延期行。この束の「1 回だけ触る」群は凍結判定の前に終える）/ P1-01.4（凍結集合: D-P1-06-1 A の条件）/ P1-01.1（固定テストの表、tests/ の純増の読み）
- P0-02（RFC-0046 後始末 3: legacy `relevance` 0.82 と `relevance.md` の削除 = P0-02.2 → .10 / .4 はその後。`test_llm.py` の legacy テスト削減 → .1 と同 PR）
- P1-11（sibling 処遇 D-P1-11-2（11-14）/ -3 / -6（12-26）: .1 の `check-sibling-backends.sh` と `docs/runbooks/sibling-backend-conformance.md` の更新。.3 は sibling が `_` 名を使っていないので sibling 非依存）
- P1-08（pyright / `lint-imports` を CI で回す: .2 の機械判定）/ P1-08.8（.1 PR-A の前に sentinel 検出）/ P1-08.8 / .17 / .18 / .25、P1-10.5（deny テスト）、P0-04 の該当項目（save 順序テスト）（固定テストの表の構成員）
- P1-04.7（`retrieval_recall_measure.py` の削除 → D-P1-06-1 の鏡が 1 本減る）/ P1-05（週次 census: .13 の読み値）
- RFC-0042（`core/insight.py` はブロック解除まで触らない）/ ADR-0062（.7 の追補）/ ADR-0108（.13 の追補）/ ADR-0109（D-P1-06-1）
- → 参照元: P1-09（env 台帳は .4 の生成物。旧 P1-09.3 は .4 に吸収、P1-09 の docs テストは snapshot と表を照合する側）/ P1-08.17（env 列は .4 に吸収）/ P1-07.11（.1 の定数の所在、.2 の snapshot の `gemma4:e4b` 行）/ P1-04.8（閾値表 1 枚。score4 / novelty / circuit の行）/ P1-01.1 / .6（固定テストの表、.3 の改名 PR = この束の停止リストの最後の行）/ P1-05（.8 の `log_anomaly_sweep.py` ERROR 節はそちら）/ P1-08.15（sqlite のテスト側 close 漏れ 2 件。src 側は .10）/ P2-02.8（週次セッションの envelope の数値抽出を `evals/judging.py::_envelope_numbers` と共有する経路は D-P1-06-1 に従う。それまでは複製 + 一致テスト）


#### P1-07 アダプタと LLM 接点の堅牢性（障害時の挙動・予算・較正定数・来歴）
- 狙い: 外部呼び出し面（Moltbook 読み / 書き・生成・判定・埋め込み）ごとに「閉じる / 開く / 退化する」が違い、その表も、交代・障害・文脈超過のときに何が起きるかの記録も無い。北極星（ADR-0080）の「オーナーと Claude Code の日常的関与なく回る」は、無人の 6 時間セッションが障害を自分で名指して終われることが前提で、交代 runbook と prompt / 重みの来歴は縦断データセット（最終成果物）の前提。能力は増やさず、既存の理由コード語彙で記録を完備する。
- 期限・順序: 着手 2027-01-16 の土曜ゲート（§4.0）。期限 2027-Q1。障害表（.1）・census の api-audit 規則修正（.5）・3xx の fail-loud（.18）は 10-24 の週（§4.0 の先行列。v2.13.0 の tag 前、週次の読みの正しさに直結）。終了条件（.3）は次の無人障害の前に。.19（平台の再読台帳）の初回行は 11-14 の週（§4.0 の先行列。11-21 の土曜ゲート（D-P3-05-2）の前）。.7 の timeout と .8 の着地点は D-P1-07-1 / -2（2027-01-16）の後の 2027-01-30 の週に merge し、どちらも src の機構変更なので凍結の停止リスト（P1-01.3）に期日つきの行を持つ（D-P1-01-1 の追加段 B を前提、決定前）。runbook（.11）と digest pin（.12）は P0-02（旧 gate 削除）の後に書く方が一覧が短い。モデル依存の定数の表は P1-04.8 の閾値表 1 枚（「モデル依存か」「再較正の読み」の列）で、この束は表を持たず runbook がそれを引く。`prompting.py:346` / `feed_seeder.py:59` のコメントは .10 PR2 で 1 回だけ書き換え、.11 はコメントを触らない（順序: .10 PR2 → .11）。埋め込みの digest pin は .12 に同梱（順序: .12 → .11）。Ollama 本体の更新手順は .11 の runbook の節で、導入・更新経路は D-P1-07-3（2027-01-30、既定可）で決める（自動更新を切るのはオーナーの手作業で決定を待たない）。推定器の較正（.10）は実機 1 回の計測待ちで、P1-15.2 の 3 回目の読み（t=0.3 の再導出）の後（NS F-14）。.13 は PR-A（来歴 record）→ PR-B（llm-calls 行 + census enum、.5 の llm-calls Entry 規則を同梱）→ PR-C（override WARNING）。同一ファイルの順序: `cli/runtime.py` は P0-02.2（:173-208 削除）→ P0-05 preflight → P1-11.5（:243-253）→ P1-07.13（:295-316）でこの束は最後; `_census_registry.py` は Entry 1 行の差分で順序不問、llm-calls Entry の 1 件だけ .13 PR-B と同 PR。この束の決定: D-P1-07-1 / -2（2027-01-16）、D-P1-07-3（2027-01-30）。transport 再試行（旧 .2）、契約修理 3 点（.4 の残り）、log family の残り（旧 .6）、pass-2 予算（.8 の残り）は第 5 章の延期行（トリガーつき。停止リストの表には入れない）。
- 束の完了条件:
  - `docs/CONFIGURATION.md` に「障害時の挙動」表（5 面 × 障害 × 挙動 × 理由コード × ログ水準 × ADR。3xx / 2xx 非 JSON / `success:false` の 3 行を含む）があり、理由コード列が `scripts/_census_registry.py` の enum 集合に含まれるテストが green
  - `tests/test_agent.py` に `end_reason: auth_rejected` 1 件と verification streak 持ち越し 1 件が green
  - 53 skill の catalog で pass-1 が None でも `generate_comment` が `budget_exceeded` にならないテストが green
  - `docs/runbooks/model-swap.md` が存在し、チェックリストの行数 = 「モデルが変わったら」を持つ項目の数（grep 照合）、Ollama 節と `docs/evidence/serving-changes.md` がある（.11）。`relevance_cache.PIN_VERSION == 3`（digest 変化で miss するテスト green）、`calibration_drift_note()` が digest で比較するテスト green（.12）、`gemma4:e4b` literal の所在が P1-06.2 の表面 snapshot の 1 行で固定され scripts 3 箇所が `served_model()` 由来
  - session-start episode に来歴 record（`framework_version` / `git_commit` / `prompt_digests` / `prompt_templates_sha256` / `identity_source` / `manifest_schema` / `python_version` / `numpy_version` / `os_release`）があり、llm-calls 行に `kind` / `schema` / `template`、新規 snapshot の manifest に同じ欄が非 null（comment-report から template digest が引けることは P2-05.4 の完了条件）
  - `_request_body` が `300 ≤ status < 400` を raise し 301 / 302 / 307 の mock テスト 3 件が green（.18）、`docs/evidence/moltbook-platform-readings.md` が存在し表 2 の全行に最終確認日がある（.19）

##### P1-07.1 障害時の挙動表を 1 枚置く（docs のみ）
- 何を: `docs/CONFIGURATION.md` に「面（decision / 生成 / 埋め込み / Moltbook 読み / Moltbook 書き）× 障害 × 挙動（閉じる / 開く / 退化）× 記録される理由コード × ログ水準 × 根拠 ADR」の 1 表を書く。理由コードは既存語彙（`enforce_unconfigured / enforce_no_threshold / enforce_backend_null / enforce_exception`、`circuit_open`、`budget_exceeded`、`transport_error`、`soft_fail`、`publish_failed`、空リスト、Jaccard 退化）のみ。表には (i) 3xx: 読み = 空読み（WARNING）/ 書き `post_comment` は `_comment_envelope` の「assuming success」で成功扱い（`client.py:213-231`）、(ii) 2xx + 非 JSON / `action` 欠落: `unfollow_agent` も「assuming success」（`:1098` / `:1122`）、(iii) 2xx + `success:false`: `soft_fail` の 3 行を含める（.18 の修理後は (i) の書きは raise に変わるので、表は .18 と同 PR か直後に更新）。
- 根拠: decision = fail-closed `adapters/moltbook/relevance_shadow.py:260-284`（検証済）/ 生成 = breaker + `None` `core/llm/__init__.py:879-978` / 埋め込み = fail-open `core/embeddings.py:157-160`「The circuit breaker is deliberately untouched」（検証済）、`novelty.py:188-203` の Jaccard 退化 / Moltbook 読み = 空読み `client.py:736-766`、書き = 冪等扱い `client.py:700` / 現 CONFIGURATION.md は `DECISION_*` 行の散文だけで面横断の表は無い（検証済）/ `client.py:213-231`（`_comment_envelope`: non-JSON → `None` = 成功扱い）、`:1098` / `:1122`（unfollow の「assuming success」）、`:567`（`>= 400` だけ raise、3xx は正常経路。検証済）
- 完了条件: 表が存在し、理由コード列の集合 ⊆ `_census_registry.py` の `enum_fields` 値集合を assert するテスト 1 件
- 規模・整合: S / neutral   出典: AR-14 R2-PLAT Fix-03   順序: .18 と同 PR か直後   注: ログ水準の列は現行の水準で書き、P1-06.8 の re-level（2027-01-16 の週）で表を更新する

##### P1-07.3 `run_session` の終了条件に鍵失効と verification streak の持ち越しを足す
- 何を: `SessionContext.auth_rejected` を置き、`_fetch_own_agent_id_fallback` と `_request_body` の 401/403 で立てて `verification.should_stop` と同列の終了条件にし、`_log_session_end` に `end_reason: auth_rejected`。起動時に `verification-audit.jsonl` 末尾の連続失敗数を読んで `VerificationTracker(initial_streak=…)` に引き継ぐ。
- 根拠: `agent.py:261-266`（401/403 → `logger.critical` のみでフロー続行。検証済）/ `:780-784`（検証済）/ `adapters/moltbook/config.py:89 MAX_VERIFICATION_FAILURES = 7`、`verification.py:624`（プロセス内カウンタ。検証済）/ `scripts/api_drift_scan.py:67`「suspension follows 10 consecutive verification failures」/ src に `auth_rejected` / `end_reason` 無し（検証済）
- 完了条件: 401 を返す mock で session が 1 cycle 以内に終わるテスト、末尾 7 失敗で起動した session が最初の失敗で止まるテスト、各 1 件
- 規模・整合: S / repair   出典: AR-05 AR-12   注: 平台側の「連続」がセッションを跨ぐかは未確認（推測）

##### P1-07.4 通知の取りこぼし件数を 1 回読む（429 判定・drift 表・`since` の修理は停止リスト）
- 何を: `get_notifications` が `since` 無し・既定件数で返す窓から外れた通知の件数（api-audit の応答件数が既定件数に張り付く頻度、`reply_handler` が前回処理した `created_at` より古い未処理の有無）を 1 回読み、非 0 なら paging を入れる判断を装置境界（P3-02 regime 表）に 1 行書く。hard / soft 429 判定の reset 値一次化と `Retry-After` HTTP-date、`_EXPECTED_KEYS` の feed / home 追加、`since` + paging の修理は読みの後に触る（第 5 章の延期行のトリガー）。
- 根拠: `client.py:517`（文言判定）・`:529`（`float(Retry-After)`、失敗時 60 s 固定）・`:35 MAX_RETRY_AFTER = 300`（検証済）/ `client.py:50-57` の docstring が feed 未カバーを自認、`:58-67` は 8 endpoint のみ（検証済）/ `client.py:785 get_notifications(since=None)`、`reply_handler.py:209` は引数なし（検証済）
- 完了条件: 読み値 1 行（取りこぼし件数 / 窓）+ 判断 1 行（paging を入れるか、regime 表）。平台の現行文言・既定件数・paging は未確認（推測）のまま
- 規模・整合: S / instrument   出典: AR-03 AR-04 AR-09   注: paging は届く通知の母集団 = 本番の行動量を変えるので読みが先（NS F-14）。平台の現行文言・既定件数・paging の確認は .19 の台帳行（日付・digest）を引く
- 消費計画: (a) 土曜ゲートのオーナーが 1 回読む (b) 1 読みで paging の要否（第 5 章の延期行のトリガー発火）を決める (c) 読み後に撤去（1 回の読み）

##### P1-07.5 census の api-audit error 規則を直す（transport 行・3xx。`truncated_kept` の llm-calls 規則は .13 PR-B へ）
- 何を: `api-audit.jsonl` の error 規則を「`200 ≤ status < 300` 以外は error」にする（`status: null` の transport 行も行数に含めて error に数える。P2-04.4 (b) と同じ文言）。`llm-calls-*.jsonl` の error 規則（`outcome in ("ok", "truncated_kept")`、truncation は別列）は同じ `Entry` 行を .13 PR-B が触るので、そちらに同梱する。同じ PR で api-audit の `content_status`（`client.py:177-186` が書く moderation 状態）の非 null 件数を `jq` で 1 回だけ数えて PR 本文に 1 行残す（常設の drift 行は置かない。非 0 なら第 5 章の延期行から起こす）。
- 根拠: `scripts/_census_registry.py:170-172`（`error=(("status","<",400),)`）と `:133`（`outcome in ("ok",)`）、検証済 / `client.py:500-508` の transport 行は `"status": None`（検証済。`Entry` docstring「absent or null is not judged」→ 停止の週が error 率 0 に読める）/ `core/llm/__init__.py:1043`「`truncated_kept` if done_reason == length else ok」（出力は呼び手に渡る。検証済）/ `client.py:486-494` は redirect を追わないので 3xx は常に失敗だが `:567` は `>= 400` しか raise せず `:172` の規則は 3xx を正常に数える（検証済）
- 完了条件: 合成 fixture（`status: None` 3 行 + `status: 301`・`keys` 無し 1 行）で api-audit error 率 1.0 のテスト 1 件、PR 本文に `content_status` の非 null 件数 1 行。`truncated_kept` 行が llm-calls error に数えられないテストは .13 PR-B 側
- 規模・整合: S / repair（census の規則の誤りを直す。計器の増設ではない）   出典: AR-02 AR-36 R2-PLAT Fix-02 R2-IMPL Merge-04 R2-PLAT-02（`content_status` の 1 回の計数、R4-CUT Prune）   注: `truncated_kept` を成功と読むかは ADR-0065 の定義で確認してから（.13 PR-B）   順序: `_census_registry.py` は Entry 1 行の差分で順序不問（P2-01.1 / P2-01.8 と同じ PR でもよい）

##### P1-07.7 decision 面の timeout / breaker を live gate 向けに決める（D-P1-07-1）
- 何を: ADR-0113 に 1 段落追補して、(a) decision 専用の小さな breaker（3 失敗 / 120 s、`circuit_open` は既存語彙）か (b) read timeout 300 s → 60 s（実測 p95 4.9 s、RFC-0046）のどちらかを入れる。生成 breaker とは共有しない（ADR-0113 の隔離は維持）。
- 根拠: `core/llm/decision.py:339 timeout = (30, 300)`、`:340 batch_budget_s = 120.0`、`:370`（予算は各質問の前にしか見ない = feed の 1 問バッチには効かない。検証済）/ ADR-0113 ja:86「decision の読みが circuit breaker に書かないため cycle を終える — 終えなければ backend が落ちているとき残りの投稿 1 件ごとに timeout を払う」（検証済）/ 2026-10-07 以降 gate は live で、応答しない障害では cycle ごとに最大 300 s 払って fail-closed
- 完了条件: ADR-0113 追補 + 選んだ方のテスト 1 件: timeout を 0.1 s に注入した fixture で理由コードが `enforce_backend_null`（(b)）か `circuit_open`（(a)）で fail-closed になることと、read timeout 定数（(b) なら 60）か breaker 閾値（(a) なら 3 / 120 s）の literal を assert する。経過時間（壁時計）の assert は置かない
- 規模・整合: S / repair   出典: AR-16 R2-TST Fix-10

##### P1-07.8 skill 注入の予算: pass-1 fail-open の着地点（D-P1-07-2）
- 何を: pass-1 が `fail_open_llm` / `fail_open_parse` のとき `_selection_system(None)` が全コーパス（53 skill ≈ 103k 文字 → 推定 34k tok > `NUM_CTX` 32k）に落ち、C2 ガードが comment / reply / post を無言で skip する経路を塞ぐ。着地点は D-P1-07-2（推奨 A: skills ブロック無し）で決め、`enforced=False` 行に着地点を記録する。pass-2 の予算（8k est tok）と `selection_truncated` 欄は新しい切り捨て規則なので第 5 章の延期行。`_SELECTION_NUM_PREDICT` のコメントの catalog 数（37 → 現行 53）の修正は .10 の棚卸し commit に含める。
- 根拠: `adapters/moltbook/llm_functions.py:210-`（`_selection_system` の None 分岐 → 既定の全コーパス prompt）、`core/llm/__init__.py:800-813`（`available < MIN_CLAMPED_NUM_PREDICT` → `outcome = budget_exceeded`、`None`。検証済）/ 測定は元項目（`python3 -I`、data repo 53 skills）/ `core/skill_selection.py:229`「No numeric cap is applied to the selection size」、`:90 _SELECTION_NUM_PREDICT = 400`（検証済）/ ADR-0081「fail-open = 全注入」は catalog が窓に収まった時代（37 本）の設計
- 完了条件: 53 skill の catalog で pass-1 None でも `generate_comment` が `budget_exceeded` にならないテスト、ADR-0081 追補（fail-open の着地点）
- 規模・整合: S / repair   出典: LP-01 LP-03

##### P1-07.9 decision 面の文脈超過を理由コードで名指す
- 何を: `_ask` の前に `measure_input_tokens` 相当で見積もり、`NUM_CTX − BACKEND_FRAMING_RESERVE` を超えたら `decision_reason: "budget_exceeded"`（既存語彙）を文脈にも使い、`error_kind` で `context` / `time` を分ける。
- 根拠: `core/llm/decision.py:471-480`（`num_ctx` を常に送り `num_predict: 1`、入力長の見積もり無し。検証済）/ `:370` の `budget_exceeded` は時間予算のみ / 生成側だけ `core/llm/__init__.py:781` で `ctx_window` clamp / identity は distill-identity で育つ（ADR-0091）ので domain + 投稿 1,000 字 + 質問が 32k に近づく経路がある。超えると Ollama は先頭（= domain）を捨てて `answered` のまま答える
- 完了条件: 長い domain で `budget_exceeded`（`error_kind: context`）が記録されるテスト 1 件
- 規模・整合: S / instrument   出典: AR-15   注: Ollama の先頭切り捨て挙動は版依存（推測）
- 消費計画: (a) 土曜ゲートのオーナーが weekly の census 行（`budget_exceeded` × `error_kind: context` の件数 / 週）を読む (b) 非 0 の週が出たら .10 の再較正の材料にし、D-P1-07-2 の着地点を見直すかを決める。0 の週は何も決めない (c) 撤去条件: .10 の係数が固定された後 8 週連続 0 なら読みを止める（欄は残す）

##### P1-07.10 token 推定器を gemma 実測で再較正し、Qwen 期の残滓を 1 commit で棚卸す（2 PR）
- 何を: PR 1 = 計測: llm-calls の `input_tokens`（推定）/ `prompt_eval_count`（実測）を経路別 n ≥ 1,000 行で 1 回読み、gemma4 の tok/char（CJK / 英文）を `docs/evidence/adr-0069/` に固定し ADR-0087 に追補（固定した比の更新条件 = モデル交代。Review-when は .11 の `model-swap.md` チェックリストの行を参照するだけにする）。PR 2 = 係数: Ollama 経路の `_estimate_tokens` を「実測比 × 安全率 1.2」に置く 1 commit。同じ commit で `prompting.py:346` / `feed_seeder.py:59` のコメントを gemma 基準に（この 2 行の書き換えはここで 1 回だけ。.11 はコメントを触らず、定数の行は P1-04.8 の表に足す）、`core/skill_selection.py:90` 付近の catalog 数コメントを現行（53）に直す（.8 から移した）。`_INJECTION_TOKENS` への Gemma `<start_of_turn>` / `<end_of_turn>` 追加は P1-10 の実機確認が「Ollama は user text の special token を解釈する」だった時だけ行う（確認前は項目に書かない）。着手は P1-15.2 の 3 回目の読み（t=0.3 の再導出）の後で、係数の変更は装置境界（P3-02 regime 表）に 1 行。
- 根拠: `core/llm/prompting.py:340-354`（ASCII /3・非 ASCII ×2、根拠「Qwen3.5 real is ~1.5-2」。検証済）/ `core/llm/__init__.py:784-786`「the two differ by 1.73-1.95x on this agent's corpora」（検証済）/ `core/llm/guard.py:160-165` は ChatML 3 token のみ（検証済）/ src の `qwen` 言及は 6 行・4 ファイル（`config.py:65` / `backend.py:20-24` / `prompting.py:346` / `feed_seeder.py:59`。検証済）/ 試算: 日本語 14,000 字の post は推定 28k tok で skip、実トークン（≈1.5/字）なら収まる
- 完了条件: evidence 1 節 + ADR-0087 追補、`budget_exceeded` 行/週が週次の読み値に出る、`grep -i qwen src` が ADR-0069 の履歴注記（`backend.py:20-24` / `config.py:65`）だけ、`_estimate_tokens` の係数 ≥ 実測の上限、regime 表に 1 行
- 規模・整合: M / repair   出典: LP-02 CH-17 LP-07 R3-MDL M-1 M-2   依存: 実機（M1）で 1 回の計測、P1-15.2（3 回目の読み）、P1-10（special token の解釈確認）   順序: PR2 → .11   注: 推定を実測に寄せると長文 post の engage が増える = 本番の行動量が変わる（NS F-14）

##### P1-07.11 モデル・serving 交代 runbook（「モデルが変わったら再走」のチェックリストと Ollama 本体の更新手順を 1 か所に）
- 何を: `docs/runbooks/model-swap.md` を書く（既存の 1 行チェックリスト（P0-02.8 が 10-17 に起こす「ADR-0112 の phase separation を再訪」）に手順を足す）— off-window → pull + digest 記録 → ADR-0068 型 A/B → `relevance_arm_replay.py --arms C --subset dev` の AUC ≥ 0.908 → `relevance_label_set.py check` → 再ラベル or ack → evals re-baseline → `OLLAMA_MODEL` / plist → 各 Review-when（ADR-0112 / 0113、RFC-0046 / 0047 / 0040）の消化。モデル依存の定数 — `_DEFAULT_OLLAMA_MODEL` / `NUM_CTX` / `MIN_CLAMPED_NUM_PREDICT`（n=2,366）/ `_estimate_tokens` / skills framing（`prompting.py:268`）/ `<think>` 正規表現（`guard.py:74`）/ `relevance_score4: 0.3`、(a) 埋め込み側（view floor 0.66 / 0.55、dedup 0.90 / 0.80、novelty θ=0.35、insight cluster 0.70、`CALIBRATION_ANCHORS`、.12 の `CALIBRATED_EMBEDDING_DIGEST`）(b) 研究の床（IPD の SE 規則、shadow cosine 0.016、P3-04.9 の identity 床、P1-05.2 の帯）(c) 生成側の残り（`COMMENT_TEMPERATURE = 1.3`、`decision.py:339-340` の `(30, 300)` / `batch_budget_s = 120.0`、`feed_seeder.py:59` の予算）— は P1-04.8 の閾値表 1 枚に「モデル依存か」「再較正の読み」の列で載せ、runbook はその表を引く（この項目は表を持たない。`prompting.py:346` / `feed_seeder.py:59` のコメントは .10 PR2 が書き換えたものを触らない）。runbook には (d) 埋め込みモデル交代の手順（全 pattern の re-backfill と (a) の再較正。同じ 768 次元のモデルでは混在を検出できないので .12 の digest 照合が先）と (e) ADR-0068 型 A/B の盲検判定は cloud が行う旨（前提変更: ゼロ API の例外 — 研究判定のみ、egress 分類は D-P1-11-4。P1-15.2 / .3 と同じ書式）を置く。runbook の冒頭に「モデルが変わったら再走」のチェックリストを置き、引き金を持つ項目（.10 の Review-when、P3-04.8 (c)、P3-04.9 (c)、P2-02.3 (b)、P0-02.8 の phase separation 再訪、P3-03.2 の IPD 床、shadow cosine 床 0.016、P1-01.8 / D-P1-01-2 の装置境界）はこの行を参照するだけにする。runbook は「serving 変更」まで広げ Ollama 本体の節を持つ: (f) 導入・更新経路を D-P1-07-3 で決め `docs/CONFIGURATION.md` に 1 行（推奨: アプリのまま自動更新を切り、更新は手動・セッション窓外。自動更新を切るのは決定を待たずオーナーが手で行う）(g) Ollama 版依存の前提の表（前提 / 場所 / 確かめ方）: `decision.py:49-51` の `top_logprobs` 上限 20、`/api/tokenize` 不在（`backend.py:363`、ADR-0087）、cache hit でも `prompt_eval_count` が全 token 数を返す挙動（`5eed66e` / `fb14ede`）、.9 の文脈超過時の先頭切り捨て、`OLLAMA_MAX_LOADED_MODELS` 未設定時の同時ロード（ADR-0112）、t=0 の logprobs が run 間で bit 再現しない（RFC-0046）の 6 件 (h) 更新手順: 更新前に `ollama --version` と両モデルの digest を控える → 更新 → P0-05.1 の `doctor` と decision canary → `relevance_label_set.py check` → 結果 1 行（日付 / 前後の版 / digest / canary の結果）を `docs/evidence/serving-changes.md` に（境界表への写しは P3-02.7）。scripts の `gemma4:e4b` literal 3 箇所を `served_model()` 由来に。ADR-0069 の手順に step 7 として参照を足す。「`gemma4:e4b` literal は `backend.py` と evidence / baseline 以外に無い」は別テストにせず P1-06.2 の表面 snapshot の 1 行で固定する（src 側は既に成立: literal は `backend.py:27` の 1 箇所、他 4 行はコメント）。
- 根拠: `core/llm/backend.py:19,27,32,46-67`（検証済）/ `config/domain.json:14 "relevance_score4": 0.3`（検証済）/ `core/embeddings.py:30-47`（埋め込み側の閾値と 3 点較正はすべて nomic-embed-text で測った、と自認）/ 引き金の散在: P1-07.10 Review-when・P3-04.8 (c)・P3-04.9 (c)・P2-02.3 (b)・P0-02.8・ADR-0090:127-130（モデル交代で IPD 床が無効）/ `docs/runbooks/` に model-swap 無し（検証済）/ `scripts/relevance_label_set.py:110` / `relevance_arm_replay.py:1712` / `ipd-two-arm.sh:37`（検証済）/ ADR-0069 Review-when の手順 6 段は decision seam 以前で判定面と plist を含まない / `rfcs/0044-skill-selector-temperature-zero.md:67-68`（09-20 に Ollama 0.30.11 → 0.34.2 が受け身で記録され、更新の判断の記録は無い）/ `config/launchd/com.moltbook.ollama-restart.plist:35`（`/usr/local/bin/ollama serve` = アプリ導入で、更新はアプリ側に任されている）/ `core/llm/decision.py:49-51`（`OLLAMA_TOP_LOGPROBS_CAP = 20`、21 で HTTP 400）（推測を含む: アプリが自分を更新するか、オーナーの Mac の設定は未確認）
- 完了条件: runbook（チェックリスト + Ollama 節 + 前提表）+ ADR-0069 追補 + P1-04.8 の表に (a)〜(c) と上記の定数の行があり runbook がその表を引く + scripts 3 箇所が `served_model()` 由来 + runbook のチェックリストの行数 = 「モデルが変わったら」を持つ項目の数（grep 照合）+ CONFIGURATION に導入経路と自動更新の方針が 1 行。次の Ollama 更新で `docs/evidence/serving-changes.md` に前後 1 行と canary の結果が残る。既存テストは不変
- 規模・整合: M / repair（(e) は前提変更: ゼロ API の例外、研究判定のみ）   出典: AR-19 LP-25 LP-26 R3-MDL M-1 M-2 F-1 F-4 R3-OSX-01（Ollama 節、R4-CUT Merge）   依存: P0-02（旧 gate 削除後は一覧が短い）、P1-04.8（閾値表）、.12（`check` が digest を見ること）、P0-05.1（`doctor` と canary）、P1-15.3（`ollama_version` 列）、D-P1-11-4（(e) の egress 分類）   順序: .10 PR2 → .11、.12 → .11

##### P1-07.12 判定と埋め込みの pin に重み digest を含める（cache `PIN_VERSION` 3・label set manifest・`CALIBRATED_EMBEDDING_DIGEST`・restore の照合）
- 何を: `relevance_cache` の pin に `generation_model_digest`（`serving_environment()` が既に返す）を足して `PIN_VERSION = 3`（digest 取得失敗時は名前のみ = 現行）。`scripts/relevance_label_set.py` の manifest にも digest key を足し、`check` は digest 変化で exit 2（旧 manifest は欠損を許容）。埋め込み側は `core/embeddings.py` に `CALIBRATED_EMBEDDING_DIGEST`（現行 nomic-embed-text の digest）を置き、`calibration_drift_note()` は `serving_environment()` の `embedding_model_digest` と比べる（Ollama に届かず digest が取れないときは今の名前比較に戻り、その理由を note に書く）。`docs/runbooks/runtime-backup-restore.md` の手順 5（再埋め込み）の前に「digest を照合し、違えば `restore-embed-knowledge.py` で全件 re-backfill してから view を使う」1 行を置く。`CALIBRATED_EMBEDDING_DIGEST` は P1-04.8 の閾値表に行を持ち、.11 の埋め込み交代手順 (d) はこの照合を引く。
- 根拠: `adapters/moltbook/relevance_cache.py:142-148` の pin は `domain_sha256` / `score4_prompt_sha256` / `decision_backend` / `decision_model`（名前）のみ、`:81 PIN_VERSION = 2`、`:90 TTL_DAYS = 14`（検証済）/ `core/llm/__init__.py:468 serving_environment()` が `generation_model_digest` を持ち session-start episode と snapshot にだけ記録、`:472`「a re-pull silently swaps the weights behind gemma4:e4b」、`:514`（`embedding_model_digest` は episode / manifest に書くだけで較正判定は読まない）/ `relevance_label_set.py:372-373` は名前のみ / `core/embeddings.py:30-38`（「the model identity itself is pinned」）、`:38 CALIBRATED_EMBEDDING_MODEL = "nomic-embed-text"`、`:54-72`（`calibration_drift_note` は名前の文字列比較のみ）/ `core/pattern_embeddings.py:149-155`（同じ 768 次元の別重みは検出できない）/ `docs/runbooks/runtime-backup-restore.md:74-78`（手順 5）・`:92-94`（照合手順は無い）
- 完了条件: digest 変化で cache miss のテスト 1 件、`check` exit 2 のテスト 1 件、埋め込み側のテスト 2 本（名前が同じで digest が違えば note が出る / digest が取れなければ名前比較に戻り理由を返す）、restore runbook に照合 1 行、P1-04.8 の表に `CALIBRATED_EMBEDDING_DIGEST` の行。既存テストは不変（追加のみ）
- 規模・整合: S / repair（埋め込み側は既存 WARNING の前提の修理で計器の新設ではない）   出典: AR-20 LP-17 R3-MDL-01（埋め込み側、R4-CUT Merge）   → P1-15（RFC-0047 の face 台帳はこの pin を前提にする）

##### P1-07.13 来歴 record を 1 つ定義し、session-start episode / llm-calls 行 / snapshot manifest に記録する（P2-05.4 の正本）
- 何を: PR-A: 来歴 record（frozen dataclass、1 回計算）を定義し `_llm_session_meta` に写す + `identity_source` + fallback WARNING + テスト 2 本 → PR-B: llm-calls 行の `template` / `kind` / `schema` + `_census_registry.py` の enum（.5 の llm-calls Entry 規則変更を同梱）→ PR-C: home prompts override の digest WARNING。record の欄 — `framework_version`（P0-06.4 の単一ソース）/ `git_commit` / `prompt_digests{name: sha12}`（resolve 後、`$MOLTBOOK_HOME/prompts/` override 込み）/ `prompt_templates_sha256` / `prompt_override_files`（stem の列）/ `identity_sha256` / `axioms_sha256` / `identity_source: identity | default_fallback` / 値層 4 ファイルの sha256（`values_digest`）/ `manifest_schema`（整数）/ 実行環境の版 `python_version` / `numpy_version` / `os_release`（P1-08.26 (c)、PR-A と同じ PR）。`_llm_session_meta` に写し、llm-calls 行に `template`（stem）、`kind: "generation" | "embedding"`（追加のみ。無印 = 生成の読み互換は維持）、`schema: <int>` を足す（旧 .6 から吸収）。公開面の comment-report（P2-05.4）はこの record を写すだけにする（欄名は上記に固定。PR-A の後）。snapshot `manifest.json` にも同じ record を写し（独自に計算しない。PR-A と同じ PR か直後）、`prompts_dir` が全件 null の原因（home に `prompts/` が無く `config.PROMPTS_DIR.is_dir()` が偽）を解消するか、CONFIGURATION の「`prompts/` … full inference-time context」を実態に直す。home の prompts override が packaged と差分あるときは digest を取る同じ場所で WARNING 1 行（`prompt_override_differs`、ファイルごと。`init --refresh-prompts` は足さない）。identity fallback 時は WARNING 1 行（既にあれば欄だけ）。
- 根拠: `cli/runtime.py:295-316`（モデル名と重み digest のみ。検証済）/ `core/domain.py:244-265` の override は失敗時 WARNING のみで有効な override は記録に残らず、内容の新旧も見ない / `config/prompts/system.md` は 1 行「Keep API keys …」（検証済）で `prompting.py:231-235 _identity_base` が identity 無効時にこれへ落ちる（検証済）/ src に `identity_source` 無し（検証済）/ 本番で pin される template は `relevance_score4.md` だけ（`relevance_cache.py:146`）/ `core/llm/__init__.py:352` の `"kind": "decision"` だけが明示、`relevance_cache.py:74 SCHEMA = 2` は cache のみ、`_census_registry.py:128-131`「Rows before 2026-09-12 lack it」（旧 .6）/ data repo `snapshots/*/manifest.json` の鍵集合は 3 世代（14 / 15 / 19 鍵）で schema 版の鍵が無く `"prompts_dir": null` が 100 / 100（R1-REP-04）/ `core/snapshot.py:155-184`（manifest キー、`:184` `prompts_dir`）、`docs/CONFIGURATION.md:354-358`
- 完了条件: `identity_source` 欄 + fallback テスト 1 件、llm-calls の `kind` / `schema` を `_census_registry.py` の enum が読む、旧コピーを置いた home で WARNING が出るテスト 1 件、新規 snapshot の manifest に `manifest_schema` と上記欄が非 null で record と一致するテスト 1 件、CONFIGURATION.md の記述と manifest のキー集合が一致するテスト 1 件。「comment-report から任意の comment の template digest が引ける」は P2-05.4 の完了条件（この項目の PR では report を触らない）
- 規模・整合: M / repair（来歴の記録は ADR-0075 の observability = repair）   出典: LP-28 LP-32 AR-33 AR-34（旧 .6）GO-12（P2-05.4）VL-06（旧 P3-04.6 の manifest への写し、R4-CUT Merge）CU-15（旧 P1-14.4 の WARNING 1 行）R2-IMPL Fix-11 Merge-04 R3-OSX-05 (c)（実行環境の 3 欄）   順序: `cli/runtime.py` は P0-02.2（:173-208 削除）→ P0-05 preflight → P1-11.5（:243-253）→ この項目（:295-316）; `_census_registry.py` の llm-calls Entry は PR-B で 1 回

##### P1-07.14 eval の prompt digest の対象を絞り、dead field を消す
- 何を: `config/prompts/stocktake_merge_rules.md` とその field（`core/domain.py:79`、読み手なし、merge は ADR-0097 で退役）を削除し、`test_every_prompt_file_is_consumed` に「各 field は `src/` に `<FIELD>_PROMPT` の読み手を 1 つ以上持つ」検査を足す。`evals/run_eval.py::prompt_templates_sha256` を comment 経路の template（comment / learned_*_framing / untrusted_* / skill_selection / system）+ `domain.json` のうち comment 経路に効く key に絞るか、`domain.json` を `domain_sha256` に分けて ack 対象から外す。
- 根拠: `grep -rn STOCKTAKE_MERGE_RULES_PROMPT src/` 0 件、`stocktake_merge_rules.md` と `domain.py:79` は存在（検証済）/ **元項目の「2 本」のうち `insight_revision_generation.md` は `bcc97e2`（RFC-0042 項目 7/8）で削除済 → 1 本に訂正** / `evals/baselines/comment_golden-2026-09-12.ack.json` の ack 4 件（09-19 / 09-25 / 10-07 ×2）中 2 件が `domain.json` のみの変更（検証済）
- 完了条件: dead field でテストが落ちる、次の閾値変更で ack が要らない
- 規模・整合: S / repair   出典: LP-04 LP-24   → evals の運用は P1-08

##### P1-07.15 判定 seam の記録事項 2 件（固定文は ADR-0054 の例外と記録・seed 非固定）
- 何を: `_NOUL_SUFFIX` / `_LABEL_SUFFIX`（`decision.py:308-309`）と `_DECISION_QUESTION`（`skill_selection.py:310`）は `config/prompts/` に外出しせず、ADR-0112 追補 1 行で「seam 内の固定文は ADR-0054（prompts は config）の例外。変更は `score4_prompt_sha256` の pin を更新する PR と同時」と記録する（外出しは cache / label set の pin 対象を広げる新作業）。「生成の seed は固定しない。再現は多数決 3 と凍結版 label set で代替」の 1 行は、別の追補を起こさず P1-04.10 が 1 本で持つ ADR-0089 の追補（D-P1-04-3 / D-P3-01-2 = 2027-02-06 の後）に段落として寄せる（必要なら llm-calls 行に Ollama が返す seed を記録するだけ）。
- 根拠: `core/llm/decision.py:308-309`、`core/skill_selection.py:310`（検証済）/ `score4_prompt_sha256`（`relevance_cache.py:146`）は suffix 変更を検出しない / `grep -rn seed src/contemplative_agent/core/llm/` 0 件（検証済）、判定は t=0・生成は t=1.3（ADR-0047）で evals は多数決 3（ADR-0089 追補）
- 完了条件: ADR-0112 追補 1 行、P1-04.10 の ADR-0089 追補に seed の段落 1 つ
- 規模・整合: S / neutral   出典: LP-08 LP-16 R3-ADR Merge-03   順序: ADR-0112 追補 1 行は着手週、seed の段落は P1-04.10 の ADR-0089 追補の PR（D-P1-04-3 / D-P3-01-2 = 2027-02-06 の後）に同乗

##### P1-07.16 `select_submolt` の None 率・部分一致率を 1 回読む
- 何を: llm-calls の `moltbook.select_submolt` 行と WARNING / INFO（部分一致）から None 率・部分一致率を 1 回読む。> 5% なら Ollama `format=` の enum schema（code が列挙し model は名指す）に替えて同じ読みで比較する。enum 拘束への置換は却下ではなく順序: 読み（1 回）の後に判断する。読まずに替えない（NS P-3）。
- 根拠: `adapters/moltbook/llm_functions.py:634-665`（`format=` なし、`num_predict=20`、完全一致 → 最長名の部分一致 → WARNING。検証済）/ `post_pipeline.py:471-485` は None で投稿 skip（代替しない）/ RFC-0047 の face 台帳は submolt を「未計測・着手しない」、RFC-0040「enum 拘束は別途起票してよい」
- 完了条件: 読み値 1 回 + 判断 1 行（RFC-0047 か ADR-0113 の Note）。None 率・部分一致率の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）で、「> 5%」は区間全体で判定
- 規模・整合: S / repair   出典: LP-19   → P1-15（face 台帳）

##### P1-07.18 3xx をアダプタ境界で失敗として閉じる（redirect 無効 = 3xx は常に失敗）
- 何を: `_request_body` で `300 ≤ status < 400` を `MoltbookClientError(status_code=3xx)` として raise する（audit 行は現状どおり status を残す）。`publish_failure_of` の `unknown` に `http_status` が乗る現行列で読めることを確認する。自動追従・URL 書き換えは入れない。.1 の表に 3xx 行、.5 / P2-04.4 (b) の規則は `200 ≤ status < 300` に揃える。
- 根拠: `client.py:486-494`（`allow_redirects=False`、「no call site may loosen it」）、`:567`（`status_code >= 400` のみ raise。3xx は本文を `_parse_body` して正常経路へ）、`:736-766`（`_get_list` の non-JSON → `[]` + WARNING = 空読み）、`:213-231`（`_comment_envelope` の「assuming success」→ `post_comment` が `{}`）、`:700-731`（`_idempotent_write` は False）（検証済）/ `scripts/_census_registry.py:172`（`status < 400`）、`api_drift_scan.py:140-162`（語彙は 2xx のみ）→ 3 計器とも 3xx 週を「正常」と読む / `tests/test_client.py:81` `test_redirects_disabled` は kwarg の有無だけで 3xx 応答のテストは無い（`grep -n "30[1278]" tests/test_client.py` 0 件）/ `config.py:13` `BASE_URL = "https://www.moltbook.com/api/v1"`（版上げ・ドメイン移行はまず 301 / 308 で現れる形 — 平台が移行時に何を返すかは未確認 = 推測）
- 完了条件: 301 / 302 / 307 の mock で (a) `get_notifications` が `[]` + WARNING に「HTTP 30x」 (b) `post_comment` が raise して publish 記録を書かない (c) `_idempotent_write` が False、のテスト各 1 件（計 3 件）; .5 と P2-04.4 (b) の規則が `200 ≤ status < 300`; .1 の表に 3xx 行。既存テストは不変（`test_redirects_disabled` は P1-08.17 に畳む側）
- 規模・整合: S / repair（fail-loud の修理。能力は増えない）   出典: R2-PLAT-01   注: transport は `client.py:488` の 1 箇所なので修理点も 1 箇所（P1-08.17 の allowlist テストが後から読む）   順序: .1 / .5 と同じ 10-24 の週（§4.0 の先行列）の修理束（v2.13.0 の tag 前）

##### P1-07.19 平台の仕様・規約の人間再読台帳 `docs/evidence/moltbook-platform-readings.md`（平台由来定数に確認日）
- 何を: `docs/evidence/moltbook-platform-readings.md` を新設する — 表 1 = 読み台帳（日付 / URL / 取得物の sha256 / 確認した点 / 前回との差分 / 読んだ人）、表 2 = 平台由来定数（定数名 / 場所 / 値 / 最終確認日 / 変化時に効く経路）。初回行は既存の日付つきコメント 5 箇所を転記する（本文は写さない。規約は条項番号 + 短い引用のみ）。再読の契機 = (i) drift scan の Action 行が出た土曜 (ii) データセット版切り（D-P3-05-1）(iii) 四半期 1 回。無人 fetch は入れない。「skill.md / 規約を確認」の 4 箇所（P1-10.9 (3)、P4-02.3、この束の .4 の解除条件、P3-05.14 (a)）はこの台帳の行（日付・digest）を引く。
- 根拠: 平台を読んだ記録が日付つきコメントとして散在 — `core/config.py:98`「verified via skill.md, 2026-05-04」、`core/comment_outcomes.py:26-31`「Phase 0, 2026-09-09 against skill.md」、`scripts/api_drift_scan.py:66-67`「suspension follows 10 consecutive verification failures (spec, 2026-08 read)」、`docs/adr/0106-….ja.md:32`「2026-09-09 取得」、`docs/adr/0018-….md:107`「(skill.md, 2026-05-04)」（5 件とも検証済）/ 無人チェーンは取りに行かない（`api_drift_scan.py:290-296`「Do NOT fetch … in the unattended chain」）、人間の再読先は `CLAUDE.md:135`「`WebFetch https://www.moltbook.com/skill.md`」1 行のみ（検証済）/ 規約（ToS）への言及は本体 docs / NOTICE / DATACARD に 0 件（先例は `rfcs/0040:209` の MCA 照合のみ）/ 確認日の無い平台由来定数: `adapters/moltbook/config.py:20` `FEED_CONTENT_PREVIEW_LEN = 500`（`feed_manager.py:460-465` が「長さ == 500」で再取得を判定 — 500 が変われば再取得が黙って止まる）、`:89` `MAX_VERIFICATION_FAILURES = 7`（対 平台 10）、`:103-109` `RateLimits`、`:117-120`（GET 60 / POST 30）、`client.py:517`（`"limit reached"` 文言）、`:529`（`Retry-After` float）（検証済）
- 完了条件: ファイルが存在し表 2 の全行に最終確認日がある。台帳を参照する 4 箇所（P1-10.9 (3)・P4-02.3・本束の依存・P3-05.14 (a)）が台帳行を引く。P1-10.9 の「確認日つき」がこの表を指す。初回行は 11-14 の週（§4.0 の先行列。11-21 の土曜ゲート（D-P3-05-2）の前）
- 規模・整合: S / neutral（文書台帳。観測は人間が行い、機構は触らない）   出典: R2-PLAT-03 R2-PLAT Merge-01 R2-PLAT Fix-06   注: 台帳を引く側（P3-05.14 (a) / D-P3-05-2、P1-10.9 (3)、P4-02.3、P4-01.1）は → 参照元
- 消費計画: (a) オーナーが土曜ゲートで読む（契機 (i)〜(iii)） (b) 1 読みで「適応 / 第 5 章の延期行のトリガー発火 / P4-01 検討イベント」のどれかを決め、表 1 に 1 行 (c) wind-down 時に最終行（閉鎖時点の状態）を書き、以後は更新しない


**依存**
- P0-02（RFC-0046 後始末 3: `relevance.md` / `thresholds.relevance` / `DECISION_FACES` スイッチの削除。.1 の表と .11 の一覧はその後の形で書く）
- P1-04.8（閾値表 1 枚: モデル依存の定数の行を持ち、.11 の runbook が引く。.12 は `CALIBRATED_EMBEDDING_DIGEST` の行を足す）
- P2-01.1（census registry: .13 PR-B が llm-calls Entry を 1 回で触る。.5 の api-audit Entry は 1 行の差分で順序不問）/ P1-04（T4）
- P0-06.4（`framework_version` の単一ソース: .13）/ P1-14（旧 .4 は Prune 済。差分 WARNING 1 行だけ .13 に）
- P1-15.2（3 回目の読み: .10 の着手条件）/ P1-10（.10 の `_INJECTION_TOKENS` 確認）
- P3-02.1（regime 表: .4 の paging 判断と .10 の係数変更を装置境界に 1 行）
- ADR-0113 追補（D-P1-07-1）、ADR-0081 / 0087 / 0069 / 0112 追補、ADR-0089 の追補は P1-04.10 の 1 本（.15 の seed 段落はその PR に同乗、D-P1-04-3 / D-P3-01-2 = 2027-02-06 の後）、ADR-0065 の `truncated_kept` 定義確認（.5 → .13 PR-B）
- P1-11（D-P1-11-4 = 12-05: .11 (e) の cloud 盲検判定の egress 分類）/ P0-05.1（`doctor` と decision canary: .11 の Ollama 節の更新手順）/ P1-15.3（`ollama_version` 列: .11 の Ollama 節）
- 実機 M1 で 1 回の計測（.10、D-P1-07-2 の C）/ 平台の仕様・規約の確認（.4 の修理を解除する時）は .19 の台帳行（日付・digest）を引く
- → 参照元: P2-05.4（.13 の record を写す側。PR-A の後）/ P1-06.2（.11 の scripts の `gemma4:e4b` literal を表面 snapshot の 1 行で固定）/ P1-06.8（re-level の後に .1 の表のログ水準を更新）/ P1-08.17（.18 の修理点 = transport 1 箇所 `client.py:488` を allowlist テストが読む）/ P3-02.7（.11 の Ollama 節の台帳から境界表の Ollama 行を写す）/ P1-08.26 (c)（.13 PR-A の record に実行環境の 3 欄を同じ PR で）/ P1-01.8・D-P1-01-2（凍結後のモデル交代 = 装置境界。.11 の runbook を引く）/ P3-04.8 (c)・P3-04.9 (c)・P2-02.3 (b)・P0-02.8・P3-03.2（「モデルが変わったら再走」は .11 のチェックリストの行を参照するだけ）/ P2-04.5（`{{OLLAMA_BIN}}` 化は D-P1-07-3 に従う）/ P2-04.19（ドリルの前提 (3) の digest 照合は .12）/ P2-04.23（machine-rebuild runbook の Ollama・digest 段は .12 と .11 を引く）/ P1-11.14（otel 側の語彙対応表: .13 の欄を前提）/ P1-15（RFC-0047: .12 の digest pin と .16 の読みを face 台帳が前提にする）/ P2-04.4 (b)（.5 と同じ `200 ≤ status < 300` の文言）/ P2-01.8（`publish_failed` の理由列: .5 / P2-01.1 と同じ PR）/ P1-10.9 (3)・P4-02.3・P3-05.14 (a) / D-P3-05-2・P4-01.1 (c)（.19 の台帳行を引く）/ P2-04.21（drift scan の盲点 2 行目が非 0 なら .19 の再読へ）


#### P1-08 テストと CI の強化（macOS job・未モック LLM・順序依存・床・契約）
- 狙い: 4,700 本の単体テストが 2026-10-09 の Quick Start 事故を通した。CI が ubuntu/3.13 の 1 セルで shell 層 80 件が未実行、LLM 不達 → None で緑になる 78 件、順序依存、床・配布面の未検査を直し、「赤 = diff の問題」を判断役（人間）と cloud build が信じられる状態にする。ADR-0080 の「止まる」機構層は、変更が入らないことを機械で確かめる装置があって初めて凍結できる（P1-01 の前提）。
- 期限・順序: 着手 12-19 の土曜ゲート（§4.0）。期限 2027-01。.1（CI 行列 2 セル）と .8 / .9（vacuous pass・順序依存）を先に（他項目の「赤」の信頼性の前提）。.8 は 2027-01-16 の P1-06.1 PR-A（`core/llm/ollama.py` への移設）より前に入れる（`tests/test_llm.py` の patch 付け替え漏れが実接続になり赤で見える）。shell テスト（.3 と他束の shell テスト）は .1 の後で、harness は .3 の `tests/_shell_harness.py`、ubuntu で空になる条件は .2 の期待集合に登録する。pytest の起動行（`pyproject.toml:43` の `addopts` と `.claude/verify.sh:172`）の所有者は .7 で、.2 / .6 / .9 / .15 は自分のフラグを .7 の行に載せる（フラグは各修理と同じか後の PR。先に入れると赤）。.25 は .1 と同 PR か直後で、.26 (a) は .25 と同じ PR、.26 (c) は P1-07.13 PR-A と同じ PR、.26 (b) は P2-04.23（2027-Q1）と同時、.24 は .4 / .23 の後、.17 は P1-10.6 の後か同 PR。.12（理由コード語彙の閉包テスト）は RFC-0046 後始末 3（10-17 の Step 1c の D-P0-02-1 行の照合コマンドで照合 → 旧 gate 削除 PR（P0-02.2）は平日に branch で用意し、merge はゲートの後の別セッション）の後。.21 は評価層が現役の形で書き、D-P3-01-2 / D-P1-04-3（2027-02-06）で評価層が退役なら検査ごと外す。この束の決定: D-P1-08-1（.5。11-14 の土曜ゲート。v2.13.0 の tag はこの決定の後の平日 11-16〜20。.23 の形（exit 2 か要約行）も同じ回で 1 つに決める）、D-P1-08-2（.4 の branch protection、2027-01-23 の土曜ゲート）。.5 の ADR-0109 追補（D-P1-08-1 B と ADR-0069 の訂正）は、D-P0-06-2 A の追補と合わせて P0-06 の release PR の 1 本にする。.16 は P1-04.7 に吸収、.11 は第 5 章の延期行、.13 / .14 / .22 は落とした。固定テスト（.8 の sentinel 検出、.17 / .18、.25。週次セッションの deny テストは P1-10.5、save 順序テストは P0-04 の該当項目が持つ）は P1-06 の「固定テストの表」の構成員で、凍結判定（P1-01）の前に揃える。それ以外の tests/ 追加は、凍結後は P1-01.6 規則 (5) の範囲（再現テスト・snapshot 更新・項目の完了条件に列挙した既存テストの書き換え・計器の合成 fixture テスト）のみ。
- 束の完了条件:
  - CI の verify 2 セル {ubuntu/3.13, macos/3.13} と P0-06.3 の `packaging` job の床 leg（Python 3.11 + lowest-direct）で緑、macOS セルの skip 理由に `darwin` 由来が 0
  - `pytest -p randomly` が 3 seed 以上で緑、opt-in marker 無しの sentinel（`127.0.0.1:1`）接続が 0、起動行が .7 の最終形と一致
  - CI ログに PASS 時も skip 件数と理由が出て、期待集合（.2）外の skip とカバレッジ後退（床 94 固定）が赤になる
  - `tests/test_io_surface_allowlist.py` が存在し、allowlist の正本はそのテスト定数（P1-10.1 の表はそこから生成）で、.18 の動的検査が同じ定数を読む
  - `.claude/verify.md` と runbook で「CI 未配線」「no repository … uses CI」が grep 0、`tests/test_ci_config.py`（.25）が緑

##### P1-08.1 CI 行列を macOS に広げる（床は P0-06.3 の packaging job の 1 leg）
- 何を: `verify.yml` の `verify` job を matrix {ubuntu-latest/3.13, macos-latest/3.13} の 2 セルにする（`verify.sh` は無引数のまま。CI 用の別コマンド列を作らない）。床の検査（Python 3.11 = D-P0-06-1 A、`uv sync --resolution lowest-direct`、`pytest -q` のみで `verify.sh` は呼ばない — lowest-direct は dev group の ruff / pyright / pytest-cov まで床版に下げる）は P0-06.3 の `packaging` job の 1 leg が持つ。pandas 3.0.x と numpy 1.24.0 の ABI 非互換は、床 leg で pandas も床（2.2.0）で解くか、dev の pandas 床を numpy 床と同時に上げる（.6 と同 PR）。BSD 依存を `python3 -c` に書き換える案（WO-31 (a)）は shell を触る M 作業なので採らず、runner で解く。
- 根拠: `.github/workflows/verify.yml:23` `runs-on: ubuntu-latest`、`:31` `python-version: "3.13"`、matrix なし; 実測 skip 178 のうち `sys.platform != "darwin"` 由来 80（`tests/test_weekly_analysis_shell.py:36`、`test_weekly_pipeline_valuelayer_shell.py:45`、`test_backup_runtime_shell.py:45`、`test_rotate_log_shell.py:35` 等）、`scripts/weekly-pipeline.sh:154` `date -v-1d`・`:607` `sed -i ''`（BSD 依存）; 実測 3.13 で lowest-direct を解くと numpy の最下は 1.26.0（1.24.0 に cp313 wheel が無い）= 床にならず、3.11 + lowest-direct の editable venv では 4,762 passed / 2 failed（rsync 不在の 2 件のみ）/ 178 skipped、pandas 3.0.6 + numpy 1.24.0 は `tests/test_instrument_census.py` が ImportError・pandas 2.2.0 で緑。public repo の macOS runner は無料枠（推定）。
- 完了条件: verify job の 2 セルが緑 / macOS セルの `-rs` 要約（出し方は .2）に `darwin` 由来の skip が 0 / 床 leg の判定は P0-06.3 の完了条件（赤なら床を上げて pyproject を更新）。既存テストは不変。
- 規模・整合: S / repair   出典: TQ-02, WO-31, TQ-10, R2-TST Merge-02 Fix-01   依存: .2（`-rs` 要約と期待集合）、P0-06.3（床 leg）

##### P1-08.2 skip を可視化し、環境依存 skip を理由つきにする
- 何を: 期待 skip 集合を `(sys.platform, os.geteuid() == 0)` で引く表にして assert する（想定外の skip 1 件で test ゲートが非 0）。修理後の期待値は ubuntu: {darwin 80, ollama 1, claude 2} / macOS: {ollama 1, claude 2} / root 追加: {chmod 8}（他束の shell テストは追加時にこの表へ登録する）。`verify.sh` の test ゲートは `check` の外で pytest を走らせ PASS 時も `-rs` 要約を stdout に残す（`-rs` は P1-08.7 の起動行）。`tests/test_sync_research_data_shell.py` の rsync 2 件を `shutil.which("rsync")` で理由つき skip にし、`test_adr_status_consistency.py` の parametrize 内 skip 89 件は列挙側（`_BACKWARD` 該当の ADR だけ）で絞る。
- 根拠: `.claude/verify.sh:35-43` `check` は非ゼロ時のみ出力、`:172` `pytest -q`; 実測（Linux・root）skip 178 = `tests/test_adr_status_consistency.py:271` `pytest.skip("not a backward supersede status")` 89 + darwin 限定 6 ファイル 80 + 「chmod(0o000) does not block root」8 + `tests/test_novelty_gate.py:368` Ollama embedding 1、`claude` 不在の 2 件（`tests/test_weekly_pipeline_session_scope_shell.py:350, 442` の skipif）は GitHub runner では両セルで出る（runner の非 root と `claude` 不在は推測）; `tests/test_sync_research_data_shell.py:60` が `rsync` を無条件に `subprocess.run`（本コンテナで `FileNotFoundError` 2 件を再現）。
- 完了条件: 期待集合のテストが 2 セルで緑、想定外の skip 1 件で非 0 / CI ログに PASS 時も skip 件数・理由が出る（P1-08.7 の起動行に `-rs` がある）/ rsync 不在環境で 2 件が理由つき `skipped` / skip 理由集計から `:271` の行が消える。書き換える既存テスト: `tests/test_sync_research_data_shell.py::test_no_embedding_file_or_its_journal_reaches_the_public_transfer`、`::test_the_counterweight_research_data_still_goes`（helper `_transfer` 経由の rsync 不在 skip）、`tests/test_adr_status_consistency.py::test_supersede_targets_agree_across_faces`（parametrize の列挙を絞る）。
- 規模・整合: S / repair（CI の読み面の修理。計器ではない）   出典: TQ-04, TQ-06, TQ-05, R2-TST Fix-07 Merge-01   順序: `test_sync_research_data_shell.py` は P0-03.3（helper `_excludes()` の書き換え）の後

##### P1-08.3 shell テストの harness と watchdog 本体の shell テストを足す
- 何を: `tests/_shell_harness.py` を新設し、shell テストの harness（tmp HOME、PATH 前置の stub dir、darwin 限定 skip 理由の定数 1 つ）を定義する（`tests/__init__.py` があるので import 可、`_` 接頭で pytest の収集外）。他束の shell テスト（.23、P1-10.13 / .14、P2-02.2 / .5 / .6、P2-03.5、P2-04.15〜.19、P2-05.1、P3-05.19 ほか）はこれを使う。最初の利用者として `tests/test_pipeline_watchdog_shell.py` を新設し、PATH 前置の `date` stub と tmp の成果物ディレクトリで `anchor_sat` の土曜 12:00 / 13:00 境界 4 ケースと `prev_fails` の通知 dedup 2 ケースを固定する。
- 根拠: `grep -rln pipeline_watchdog tests/` → `tests/test_cli_schedule.py` のみ（plist の内容検査）; `scripts/pipeline_watchdog.sh:83-84` `days_since_sat` / `anchor_sat()`、`:163-164` `prev_fails`、`:196-215` 通知 dedup、`:54-58` `stat -f` / `date -j`（BSD）。2026-07-25 の 0 byte report に対する唯一の独立装置が自身は未検査; `ls tests/_*.py` = `__init__.py` のみ（共有 helper 無し）、既存 8 本の `tests/test_*_shell.py` が各自 `subprocess.run` を持ち 6 本が PATH を細工。
- 完了条件: `tests/_shell_harness.py` が存在し新テストがそれを import / 新テスト 6 件が macOS セルで passed、ubuntu では skip（.2 の期待集合に登録）。既存テストは不変。
- 規模・整合: S / repair   出典: WO-30, R2-TST Merge-03 Fix-14   依存: .1（macOS セル）、.2（期待集合）

##### P1-08.4 CI の記述を実態に合わせ、Dependabot と branch protection の判断を記録する
- 何を: `.claude/verify.md` の「CI 未配線」節と `docs/runbooks/sibling-backend-conformance.md` の「no repository … uses CI」を書き直す。`pyproject.toml` の `live_cli` コメント（退役済み fix loop が根拠）を「operator-only、CI では claude CLI の認証が無いので意図的に skip」に直す。`.github/dependabot.yml`（github-actions のみ。間隔は四半期 — 凍結後も PR が来る装置なので月次にせず、読むのは T4 と同じ回）を足す。branch protection は D-P1-08-2。
- 根拠: `.claude/verify.md:344-349`「未配線。`.github/workflows/` が存在しないため」vs `.github/workflows/verify.yml`（f89b28d、2026-09-25）; `docs/runbooks/sibling-backend-conformance.md:16-19`; `pyproject.toml:47-53`「deselected inside weekly-pipeline.sh's fix loop」— fix 段は ADR-0098 決定 2 で撤去、`scripts/` に `live_cli` の参照 0; `tests/test_weekly_pipeline_session_scope_shell.py:349-350, 441-442` の skipif; `verify.yml:18-19` permissions 最小・SHA pin は良好、`dependabot.yml` 無し。
- 完了条件: 「CI 未配線」「no repository … uses CI」「fix loop」が repo で grep 0 / `.github/dependabot.yml` が存在し間隔が四半期 / verify.md の CI 節に D-P1-08-2 の判断が日付つきで書かれ、CI 節の literal が `verify.yml` と一致（照合は .25 のテスト）。既存テストは不変。
- 規模・整合: S / neutral   出典: TQ-03, TQ-07, TQ-11, R2-TST-02

##### P1-08.5 `uv.lock` と固定版の環境再現を決める
- 何を: D-P1-08-1 を決める。(A) なら `uv.lock` を追跡して CI を `uv sync --locked`、pip-audit は lock 済み環境に対して走らせる。(B) なら現状（床 + `constraint-dependencies` + 毎 run フレッシュ監査）を ADR-0109 追補で正式化し（追補は D-P0-06-2 A の分と合わせて P0-06 の release PR の 1 本）、ADR-0069 の「`uv.lock` が固定する」を同じ PR で訂正し、release ごとに `uv lock` → `uv export --no-dev --frozen -o docs/evidence/release-vX.Y.Z/requirements.txt` の 2 行で固定版を残して CHANGELOG の版節から参照する（`uv.lock` は gitignore なので `--frozen` 単独では lock が無く失敗する）。P0-06.6 の release runbook（段 4）はこの 2 行を参照するだけにし、パスはこの 1 つに統一する。
- 根拠: `.gitignore:18` `uv.lock`; `pyproject.toml:101`「pin は pyproject が正本 (uv.lock は gitignore)」、`:108-111`; `docs/adr/0109-dependency-floor-scoped-to-the-wheel.md:79`「`uv.lock` is gitignored」vs `docs/adr/0069-….md:290`「rejected: `uv.lock` already pins the Python side」; `verify.yml:43` `uv sync --group eval` は毎 run 新規解決（実測: 床 `ruff>=0.16` に対し CI は公開当日の ruff 0.17.0 を解決、今回は緑）。
- 完了条件: 判断を記した ADR（新設か 0109 追補）が accepted / tag を checkout して `uv sync --locked` か `docs/evidence/release-vX.Y.Z/requirements.txt` からの同期が再現する / ADR-0069 と 0109 の記述が矛盾しない / (B) なら `docs/evidence/release-v2.13.0/requirements.txt` が存在し CHANGELOG v2.13.0 節からリンクされ、runbook に `--frozen` 単独の表記が無い。既存テストは不変。
- 規模・整合: S / neutral（決定と文書）   出典: TQ-08, RD-24, SA-27（旧 P0-06.9）, R2-TST Fix-19, R3-ADR Merge-04   順序: ADR-0109 の追補は P0-06 の release PR に同乗

##### P1-08.6 dev / eval 依存の衛生（pandas 床、deepeval pin、plugin autoload）
- 何を: `pandas>=2.2` の床を実態に合わせる — 床 leg（P0-06.3）では pandas 3.0.x が numpy 1.24.0 と ABI 非互換なので、pandas も床（2.2.0）で解くか dev の pandas 床を numpy 床と同時に上げる（.1 と同 PR）。deepeval 4.2.x で MarkupError（S-CI-1）が直っているか確認し pin を上げるかを決める（autoload を切るので `-p no:deepeval` は不要になる）。CI の pytest は `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` + 明示 `-p` にして、eval group の推移的 plugin（xdist / rerunfailures / repeat / asyncio）に依存しない（行は P1-08.7）。
- 根拠: 実測 `pandas 3.0.6 / deepeval 4.1.5 / pytest 9.1.1`（`uv run --group eval`）; `pyproject.toml:95` `pandas>=2.2`、`:103` `deepeval==4.1.5`（2026-07-31、最新 4.2.8）、`:43` `addopts = "-p no:deepeval"`; 実測 pytest ヘッダ `plugins: platformdirs, hypothesis, rerunfailures-16.7, xdist-3.8.0, repeat-0.9.4, asyncio-1.4.0, anyio, cov`、autoload を切ると `-p pytest_cov` 無しで `--cov` が unrecognized、hypothesis は `tests/conftest.py:51-54` が profile を直接 load するので plugin 無しで緑。
- 完了条件: pyproject の床・pin が実測と一致（床 leg が緑）/ pytest ヘッダの `plugins:` が {cov, randomly}（+ hypothesis 任意）のみ / P1-08.7 の起動行に `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` と明示 `-p` がある。既存テストは不変。
- 規模・整合: S / neutral   出典: TQ-09, TQ-33, R2-TST Fix-01 Fix-02 Merge-01

##### P1-08.7 pytest 起動行の最終形と verify.sh の test / deps ゲートの契約（coverage 床 94 固定・offline fail-soft）
- 何を: pytest の起動行（`pyproject.toml:43` の `addopts` と `.claude/verify.sh:172`）の所有者として最終形をここに 1 回だけ書く: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -rs -p pytest_cov -p randomly --cov=src --cov-fail-under=94 -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning`（`-p hypothesispytest` は任意、`-p no:deepeval` は不要）。各フラグの理由は .2（`-rs`）/ .6（autoload）/ .9（randomly）/ .15（`-W`）が持ち、本項目は `--cov` と床を持つ。床は 94（現状 95.1 の 1 下）で固定し「土曜ゲートで引き上げる」規定は置かない（後退 1 pt で赤、前進は読み値のみ。凍結後のテスト追加を制度化しない）。deps ゲートはネット不達を事前判定して「skipped (offline)」+ exit 2 相当に分類する（pip-audit の出力文言に依存しない）。
- 根拠: `.claude/verify.sh:172` `pytest -q`（`--cov` なし）、`:170` `pip-audit`（非ゼロ = FAIL=1、契約 `:7` は「検査不能 = 2」）; `pyproject.toml:43` `addopts = "-p no:deepeval"` を .2 / .6 / .9 / .15 が別々に書き換える予定だった; 実測 cov TOTAL 95%（12,437 stmts）、pytest 46.9s で追加は秒単位; ADR-0100 の退役理由「tests took 57% of the window's net .py growth」（CHANGELOG v2.12.0）が床の引き上げと逆向き。
- 完了条件: `pyproject.toml` の `addopts` と `verify.sh` の test ゲートを合わせた起動行が上の最終形と一致 / カバレッジ後退 1 pt で CI が赤 / オフラインの full run が `deps: skipped (offline)` を出して exit 2 / verify.md の表が実態と一致（床 94 を日付つきで記す。CI 節の照合は .25 のテスト）。既存テストは不変。
- 規模・整合: S / repair   出典: TQ-27, TQ-12, TQ-24, R2-TST Merge-01   順序: フラグは .6 / .9 / .15 の修理と同じか後の PR で入れる（先に入れると赤）

##### P1-08.8 未モック LLM 経路を検出して opt-in にする（検出 + marker のみ）
- 何を: conftest に sentinel（`127.0.0.1:1`）への socket 接続検出を autouse で入れ、既定 FAIL・`@pytest.mark.allow_unmocked_llm` で明示 opt-in にする。現に接続する 78 件には同じ PR で一括して marker を付けて終える。「LLM 不達を意図したテスト」と「mock 漏れ」の棚卸しと `ChaosBackend`（`tests/chaos.py`）か requests 層への再 mock は第 5 章の延期行（トリガー: 当該テストを触る時）。marker は `integration`（使用 0）を削り `allow_unmocked_llm` / `ollama_live` に置き換える（`integration` の削除は .10 の規約 2 行と同 PR）。
- 根拠: `tests/conftest.py:35` `OLLAMA_BASE_URL=http://127.0.0.1:1`、`:28-34`「generate() swallows exceptions and returns None; every caller treats None as a fail-open signal」; 実測（socket フック）sentinel 接続テスト 78 / 試行 107（`test_agent.py` 47、`test_insight_chaos.py` 8、`test_skillsel_arm_replay.py` 6、`test_comment_outcome_wiring.py` 5、`test_cli.py` 4 …）; `pyproject.toml:44-54` markers、実使用 `unit` 19 / `integration` 0 / `live_cli` 2; `tests/test_llm.py` は `"contemplative_agent.core.llm.requests.post"` を 59 箇所 patch しており、P1-06.1 PR-A の移設で patch が外れると sentinel へ実接続する。feed は fail-closed なので None 経路の緑は「何もしないこと」の緑（事故と同形）。
- 完了条件: opt-in 無しの sentinel 接続 0（検出テストが CI で緑）/ 宣言 marker がすべて使用されている。書き換える既存テスト: sentinel に接続する 78 件（marker 付与のみ。`tests/test_agent.py` 47 / `tests/test_insight_chaos.py` 8 / `tests/test_skillsel_arm_replay.py` 6 / `tests/test_comment_outcome_wiring.py` 5 / `tests/test_cli.py` 4 ほか、全件は検出テストの初回出力で列挙）。
- 規模・整合: S / repair（凍結を守る固定テスト: 実 LLM 漏れ検出）   出典: TQ-13, TQ-22, R2-TST Fix-22   順序: P1-06.1 PR-A より前（付け替え漏れが赤で見える）

##### P1-08.9 順序依存を解消する（autouse reset + `-p randomly` のみ）
- 何を: memory / staged / decision backend 系の module-global 設定に autouse の reset fixture を揃え、`pytest-randomly>=5.0` を dev group に足して CI に `-p randomly`（seed はログに出る。フラグは P1-08.7 の起動行）を常設する。共有 sandbox `MOLTBOOK_HOME`（module load 時に Path 定数へ固定）を per-test の `tmp_path` + 定数差し替え fixture に移す書き換え（と、それに伴う `OLLAMA_TRUSTED_HOSTS=127.0.0.1` 無効行の削除・sandbox tempdir の `atexit` rmtree）は第 5 章の延期行。
- 根拠: 実測 `pytest-randomly` seed 12345 → `test_agent.py::TestRunPostCycle::test_posts_dynamic` FAIL（他テストの post record が残り dedup 発火）、seed 777 → 同 1 件 + `tests/test_skill_selection.py:342 TestShadowDecision` の 4 件（`:395` `assert None == 'StubDecisionBackend'`、`:463` `'unconfigured' == 'http_error'` = module-global の decision backend 設定リーク）; `pyproject.toml:69-98` の dev group に `pytest-randomly` は無く `uv run pytest -p randomly` は `ImportError`（実測）; `tests/conftest.py:11-14, 25-26`（Path 定数の固定）、`:125-141`（S38 relevance リークの記録）、`:36` `setdefault("OLLAMA_TRUSTED_HOSTS", "127.0.0.1")` → `core/llm/guard.py:26` `_SIMPLE_HOSTNAME_RE`（ドット不可）。
- 完了条件: 3 つ以上の seed で緑（seed が CI ログにある）/ P1-08.7 の起動行に `-p randomly` がある。既存テストは不変（conftest への reset fixture 追加のみ）。
- 規模・整合: S / repair   出典: TQ-14, TQ-15, TQ-40, R2-TST Fix-02 Merge-01

##### P1-08.10 テスト規約を 2 行で明文化する（mock の置き場・理由コード assert）
- 何を: 「LLM は `ChaosBackend` か requests 層でだけ差し替える」「新規テストは文言でなく理由コード / 構造化レコードに assert し、既存は触ったときに移行する」を CLAUDE.md の開発原則 1 箇所に足す（`tests/README.md` は無く、作らない）。`integration` marker の削除（.8）を同 PR で。内部 generate patch（上位 5 ターゲット約 175 箇所）の棚卸しと「半減 ≤ 90」の目標は置かない（1,257 箇所の patch を触る目標 = churn）。
- 根拠: `patch(` 1,257 箇所中、`adapters.moltbook.llm_functions.generate_for_api` 50、`core.skill_selection.generate` 46、`core.llm.generate_full` 46、`llm_functions.generate` 42、`core.distill.generate` 25 は内部関数（境界 `core.llm.requests.post` 87 / `client._session.request` 121 は健全）; `docs/adr/0077-chaos-tdd-fault-injection.md:27, 41-42`（2026-08-01 追補: patch が厚く `drop_truncated` が一度も検査されていなかった）; 文字列照合 `pytest.raises(match=)` 108 / `caplog.text` 116 / `capsys` 174、1f6ef15（2026-09-28）の文言追従; `ls tests/README.md` は不在。
- 完了条件: 規約 2 行が CLAUDE.md に存在 / `grep -o caplog.text tests/*.py | wc -l` の週次 1 行が `freeze_reading.py` の tests 系列の隣に出る（読みだけ、閾値なし）。既存テストは不変。
- 規模・整合: S / repair（週次の grep 1 行は P1-01.1 の tests 系列に同居する読みで、読み手と撤去は P1-01.1 に従う）   出典: TQ-16, TQ-18, R2-TST Fix-12   依存: P1-01.1（`freeze_reading.py` の tests 系列）

##### P1-08.12 feed（score4 gate）の理由コード語彙の閉包テストを 1 本置く
- 何を: enforce 経路の abstain 理由コード語彙に閉包テスト 1 本を足す。比較対は書き手の定数（`ENFORCE_REASONS` `adapters/moltbook/relevance_shadow.py:115`、`DECISION_REASONS` `core/llm/decision.py:57`）× ADR-0113 の理由表（fault ごとに 1 語）で、読み手側は `scripts/_census_registry.py` の relevance Entry に `enum_values=`（書き手の定数を import）を持たせ census の未知値が赤になる形にする。形は `tests/test_relevance_enforce.py:310 test_the_reasons_are_closed`（literal 等値）と `tests/test_llm_chaos.py:700 test_vocabulary_has_no_dead_codes`（producer == consumer）と同型。F-FEED-1〜n（timeout / 429 / logprobs 欠落 / malformed / flapping）の fault 列 5 本は opt-in の判断（ADR-0100）で第 5 章の延期行。RFC-0046 後始末 3（旧 gate 削除）の後に着手。
- 根拠: `scripts/_census_registry.py:187` の relevance 行は `enum_fields=("decision_reason","gate_source","enforce_reason","source")` = 列名の列挙で値集合を持たない（`Entry` に値集合の欄が無い、`:55-77`）; fault 列は `test_distill_chaos` / `test_llm_chaos` / `test_verification_chaos` / `test_reply_chaos` / `test_insight_chaos` の 5 本のみ、`tests/test_relevance_enforce.py` / `test_relevance_shadow.py` / `test_decision_contract.py` の fault 語は grep 1 / 1 / 0 行; `rfcs/0046-….md:2` `state: blocked 2026-10-09`、`:248` 次の submolt-scan 2026-10-15 03:00 JST。
- 完了条件: 語彙閉包テストが緑で、書き手の定数に語を 1 つ足す / 消すと赤、census の fixture に未知値の行を 1 つ混ぜると赤。既存テストは不変。
- 規模・整合: S / repair   出典: TQ-20, R2-TST Fix-04   順序: `_census_registry.py` は Entry の差分で他項目と順序不問（同 PR を要するのは P1-07.13 PR-B の llm-calls 規則だけ）

##### P1-08.15 ResourceWarning を赤にし、テスト側の close 漏れ 2 件を閉じる
- 何を: `tests/test_pattern_embeddings.py:454` を `contextlib.closing(sqlite3.connect(…))` に、`tests/test_skill_selection.py:744` を `with ….open("a") as f:` に書き換え、`-W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning` を P1-08.7 の起動行に載せる。`.claude/verify.md` に再現手順 `PYTHONTRACEMALLOC=25 pytest -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning <file>` と「警告の帰属先が GC 時点の別テストにずれる」の 1 行。src 側 `PatternEmbeddingStore._ensure_initialized` の例外経路は現状の警告の原因ではなく、閉じるなら P1-06.10 の小修理。
- 根拠: 実測 両 `-W` の full run で rsync 以外の赤 2 件 — `tests/test_publish_logging.py::TestLogPublishedKeepsBodiesOut::test_char_count_still_reported` に「unclosed database」が GC 時に帰属し、tracemalloc で作成元は `tests/test_pattern_embeddings.py:454`（sqlite3 の context manager は commit / rollback のみで close しない）、もう 1 件は `tests/test_skill_selection.py:744` の `.open("a").write(…)`; `-W error::ResourceWarning` 単独では `__del__` 時の警告が `PytestUnraisableExceptionWarning` に包まれ rc 0（最小再現、pytest 9.1.1）; `pyproject.toml` に `filterwarnings` なし。
- 完了条件: P1-08.7 の起動行（両 `-W` を含む）で suite 全体が緑。書き換える既存テスト: `tests/test_pattern_embeddings.py::TestDimColumnIsRead::test_a_truncated_blob_is_treated_as_absent`、`tests/test_skill_selection.py::TestSkillSelectionReading::test_aggregates_frequencies_and_percentiles`。
- 規模・整合: S / repair   出典: TQ-21, R2-TST Fix-03 Merge-01

##### P1-08.17 I/O 面の allowlist テストを足す（import ルートの module 単位 + transport call）
- 何を: `tests/test_io_surface_allowlist.py` を新設する。(ii) `requests` / `urllib` / `subprocess` / `socket` / `http.client` / `shutil` / `os.system` / `webbrowser` / `smtplib` を import する module の集合（現状 src 10: `cli/session_cmds.py`、`cli/schedule.py`、`testing/__main__.py`、`core/embeddings.py`、`core/llm/__init__.py`、`core/llm/decision.py`、`core/llm/guard.py`、`core/snapshot.py`、`adapters/moltbook/client.py`、`adapters/moltbook/post_pipeline.py`; scripts 4: `dead_code_scan.py`、`docs_consistency_scan.py`、`relevance_arm_replay.py`、`relevance_label_set.py`）を走査範囲 `("src", "scripts")`（`test_cloud_egress_absence.py:64` と同じ）で固定する。(i) transport call は `requests.(get|post|request|Session)` に加えて Session インスタンスの `.request/.get/.post/.delete`（`client.py:488` `self._session.request(`）も数え、列挙した全 transport call に `allow_redirects=False` がある assert を同じテストに畳む（P1-10.6）。Moltbook の method+path テンプレート（write verb: register / posts / comments / verify / follow / subscribe / upvote / mark-read）も allowlist に含め、追加は ADR 追補と同じ PR を要求する。(iv) allowlist の正本はテスト定数（`RUNTIME_FLOOR` / `EVALS_IMPORT_ALLOWLIST` と同型）で、P1-10.1 の threat model 表はそこから生成・照合する。(v) .18 の動的検査は同じ定数を共有する。`os.environ.get` の列は置かない — env キーの正本は P1-06.4 の `core/env.py` 登録簿で、call site が 1 箇所になれば allowlist は自明。
- 根拠: 既存の機械ゲートは依存床（`tests/test_dependency_floor.py:15`）、層方向（import-linter）、`/home` 投影（`test_home_field_allowlist.py`）、cloud egress の absence（`test_cloud_egress_absence.py`）のみで、call site 集合を固定するテストは無い（`ls tests | grep io_surface` = 0）; 外向き transport は Moltbook 1 箇所（`client.py:488`。`auth.py:96` は `client.post` 経由で transport ではない）+ Ollama 5（`embeddings.py:178` / `llm/__init__.py:435, 959` / `decision.py:433, 499`）で 2026-08 以降 3 → 5 に増えた、`core/embeddings.py:178` は今 `allow_redirects=False` を欠く; `grep -rlE "^(import|from) (requests|urllib|subprocess|socket|http\.client|shutil|webbrowser|smtplib)\b|os\.system\(" src/ scripts/` = src 10 / scripts 4。
- 完了条件: テストが存在し、P1-10.1 の表がテスト定数から生成されて一致 / allowlist 外の import か transport call 1 件で赤 / `allow_redirects=False` の欠落 1 件で赤。書き換える既存テスト: `tests/test_client.py::TestMoltbookClient::test_redirects_disabled`、`tests/test_serving_environment.py::TestServingEnvironment::test_does_not_follow_redirects`（allowlist テストに畳む）。
- 規模・整合: S / neutral（凍結を守る固定テスト。能力は増えない）   出典: SA-01, AR-25, SA-41, R2-TST Fix-05   順序: P1-10.6 の後か同 PR（先に入れると `core/embeddings.py:178` で採用時に赤）   注: P1-10.14（shell 経路の egress allowlist）は同じ様式でこの項目を参照する

##### P1-08.18 注入投稿 1 本の end-to-end 否定テスト
- 何を: `responses` で Moltbook / Ollama を mock し、注入ペイロード入り feed で `run_cycle` を 1 周させたあと、`responses.calls` の host と method/path の集合が {comment, upvote, follow, post} の既知 verb・host 1 つに限られることを assert する 1 本。.17 の静的 allowlist と対になる動的な検査で、期待集合は .17 と同じテスト定数を読む。
- 根拠: `README.md:103`「the agent has no tool an injected instruction could call」; 単体の `wrap_untrusted_content`（`core/llm/guard.py`）と `test_home_field_allowlist.py` はあるが、`tests/` に `responses` の host assert は無し（grep）。
- 完了条件: テスト 1 本が存在し、未知の host / verb が 1 つ混ざると赤。既存テストは不変。
- 規模・整合: S / neutral（凍結を守る固定テスト）   出典: SA-39

##### P1-08.21 eval の axiom ラベルと改正済み憲法の節の写像を staleness 検査に入れる
- 何を: golden case の `axiom`（論文の 4 公理名）と本番憲法の節名（Emptiness & Flow / Non-Duality & Unity / Mindful Monitoring / Boundless Compassion）の写像表を judge prompt か dataset frontmatter に持たせ、節の merge / split で `evals/check_staleness.py` が落ちるようにする。
- 根拠: `evals/dataset.py:17` `AXIOMS = frozenset({"Emptiness", "Non-Duality", "Mindfulness", "Boundless Care"})`; judge prompt「{constitution}」「probes the axiom: **{axiom}**」; `evals/check_staleness.py` に axiom の参照なし（grep 0）。
- 完了条件: 写像が明示され、節構造の変更で staleness 検査が非 0。評価層の位置づけ（P1-04 の T4）が「退役」なら本項目も落とす。書き換える既存テスト: `tests/test_eval_staleness.py::TestDivergences::test_each_field_is_a_staleness_signal`（manifest に写像の field を足す場合のみ parametrize に 1 行 — 推定）。
- 規模・整合: S / repair（staleness 検査の穴）   出典: PF-33   注: 評価層が現役の形で書き、評価層の位置づけ（D-P3-01-2 / D-P1-04-3 = 2027-02-06、P1-04 の T4）が「退役」になったら検査ごと外す

##### P1-08.23 `verify.sh` のツール不在を検査不能として言う（`tests/test_verify_shell.py`）
- 何を: full mode（引数なし）で shellcheck / markdownlint-cli2 の不在を契約どおりの検査不能として言う（staged mode は現状どおり skip 可）。形は exit 2 か末尾の `skipped: shell, markdown` 要約行のどちらか 1 つで、D-P1-08-1 と同じ 11-14 の回に決める（テストは 1 本しか書けない）。分類語彙は .7 の deps ゲート（`skipped (offline)` / exit 2）と共有する。テストは `tests/test_verify_shell.py`（darwin skip 無し、`test_sync_research_data_shell.py` 型で Linux でも走る）。harness は P1-08.3。固有の設定は 3 つ: `VERIFY_REPO_ROOT`（`verify.sh:22-23`）を `git init` した tmp dir に向ける / PATH 先頭に `exit 0` の `uv` stub を置く（素で叩くと `:172` が suite をもう 1 周走らせる）/ shellcheck・markdownlint-cli2 を含まない PATH。assert は `[verify] shellcheck 不在`（`:154`）・`[verify] markdownlint-cli2 不在`（`:163`）の行か exit 2（決めた方）。
- 根拠: `.claude/verify.sh:7`（契約: `2 = 検査不能 (fail-soft)`）に対し、`:149-155`（shellcheck 不在 → `warn` + skip）、`:70-75` / `:160-164`（markdownlint-cli2 不在 → `warn` + skip）、`:181 exit $FAIL`（`FAIL` は `check` の非ゼロ時のみ 1）→ 両ツール不在の full run は warn 2 行を出して exit 0（検証済）; `:27` は git repo を要求、`:55-58` は `uv` 不在で exit 2; `.github/workflows/verify.yml:36-41` は両方を pin して導入し `./.claude/verify.sh` を呼ぶので、ローカル PASS の PR が CI で markdown / shell に落ちうる。ADR-0075「silent fallback を置かない」の自己適用。
- 完了条件: `tests/test_verify_shell.py` が .1 の 2 セルで passed（skip 無し）で、shellcheck と markdownlint-cli2 を PATH から外した full run が 11-14 に決めた形（exit 2 か要約行）を出す / `.claude/verify.md` の shell 行が markdown 行と同じ「未導入なら …」の注記を持つ。既存テストは不変。
- 規模・整合: S / repair（契約 `:7` の検査不能 = 2 の自己適用。読み値を出す計器ではない）   出典: R1-NEW-02, R2-IMPL Fix-16, R2-TST Fix-06 Merge-03   依存: .3（harness）、.7（分類語彙を共有）   注: P1-13.5（CONTRIBUTING の「Verify の通し方」）がこの項目を読む

##### P1-08.24 shellcheck / markdownlint-cli2 の版 pin を 1 箇所に（dev group と `package.json`）
- 何を: `shellcheck-py>=0.11.0.1` を `pyproject.toml` の dev group に足し、`verify.sh:63` を `SHELLCHECK=("${UV[@]}" shellcheck -S style)` にして（`:149` の不在判定も同じ解決経路に揃える — 推定で必要）、workflow の `pip install shellcheck-py==0.11.0.1` 行を消す。markdownlint-cli2 は `package.json` の devDependency に pin して workflow は `npm ci`、.4 の `dependabot.yml` に `npm` ecosystem を 1 節足す。CONTRIBUTING（P1-13.5）は版を名指しせず dev group / `package.json` を指す 1 行。
- 根拠: `.github/workflows/verify.yml:36-41`（`pip install shellcheck-py==0.11.0.1`、`npm i -g markdownlint-cli2@0.23.2` = workflow 内だけの pin）; `.claude/verify.sh:13`「ツールの版は pyproject.toml の [dependency-groups] dev が正本」vs `:63` `SHELLCHECK=(shellcheck -S style)`（PATH の任意版。ローカルは brew）、`:70-75`（markdownlint は PATH か `node_modules/.bin`）; `pyproject.toml:69-98` の dev group に shellcheck-py 無し、repo に `package.json` 無し。
- 完了条件: `grep -c "shellcheck-py\|markdownlint-cli2@" .github/workflows/verify.yml` = 0 / `uv run shellcheck --version` と CI ログの版が同じ / `package.json` に markdownlint-cli2 の pin、`.github/dependabot.yml` に `npm` 節。既存テストは不変。
- 規模・整合: S / neutral（ゲートの配管。機構に触れない）   出典: R2-TST-01   依存: .4（dependabot yml）、.23（PATH を細工するテストと不在判定の形）   注: P1-13.5 の CONTRIBUTING がこの正本を指す（P1-13.5 側がこの項目の後）

##### P1-08.25 `verify.yml` の literal を固定し verify.md の CI 節と照合する（`tests/test_ci_config.py`）
- 何を: `tests/test_ci_config.py` を新設し、`.github/workflows/verify.yml` を文字列で読んで（`yaml` は使わない）`jobs:` 直下の名前集合 {verify, secrets, packaging}、各 job の `runs-on` / `timeout-minutes` / `python-version` の literal、`./.claude/verify.sh` が無引数で 1 回だけ呼ばれることを assert し、`.claude/verify.md` の CI 節に同じ literal（セル名と timeout）が出ることを照合する。P1-06.2 の固定テストの表に 1 行で載せ、.4 / .7 の「表が実態と一致」はこのテストを指す。
- 根拠: `.claude/verify.md:344-349`「未配線。`.github/workflows/` が存在しないため」vs `verify.yml`（f89b28d、2026-09-25）— 文書が 2 週以上ずれたまま誰も赤にしない; `verify.yml:21-24, 47-49` の job / runs-on / timeout は今どのテストも読まない; `tests/test_surface_snapshot.py`（P1-06.2）は CLI / launchd / env / prompts / host を固定し CI 設定は含まず、`scripts/docs_consistency_scan.py` は `.github/` を読まない（grep 0）。
- 完了条件: テストが存在し緑、`verify.yml` の `timeout-minutes` を 1 変えると赤 / verify.md の「未配線」が grep 0。既存テストは不変。
- 規模・整合: S / neutral（テストは読み値ではない）   出典: R2-TST-02   依存: .1（2 セルの行列）、P0-06.3（`packaging` job）   順序: .1 と同 PR か直後   注: P1-06.2 の固定テストの表がこのテストを 1 行で載せる（→ 参照元）

##### P1-08.26 本番 `.venv` の再生成を規約にする（`.python-version`・固定版から作る・実行環境の版を来歴に）
- 何を: (a) repo 直下に `.python-version`（`3.13`、CI の verify セルと同じ minor）を置き、.25 の `tests/test_ci_config.py` に「`.python-version` == `verify.yml` の `python-version`」の assert を 1 つ足し、`CLAUDE.md:35` の手書きの版はこのファイルを指す 1 文に直す。(b) P2-04.23 の machine-rebuild runbook の venv 段に本番 `.venv` の作り方を 1 通りだけ書く: `uv venv` → `uv pip install -r docs/evidence/release-<最新>/requirements.txt` → `uv pip install -e . --no-deps`（D-P1-08-1 = A なら `uv sync --locked`）。(c) P1-07.13 の来歴 record に `python_version` / `numpy_version` / `os_release` の 3 欄を足す（P1-07.13 PR-A と同じ PR。manifest と session-start episode へは P1-07.13 が写す）。
- 根拠: repo 直下に `.python-version` が無い / `CLAUDE.md:35`「Python 3.10+ (venv は 3.13.5)」が本番 venv の版の唯一の記述 / `.github/workflows/verify.yml:31` `python-version: "3.13"` / `.gitignore:18` `uv.lock` で依存は下限指定のみ（`pyproject.toml:22`）なので `.venv` を作り直すたびに numpy / requests は「その日の最新」になる / .5 (B) の `docs/evidence/release-vX.Y.Z/requirements.txt` から本番 `.venv` を作る手順は無い / snapshot manifest の serving_env は Ollama の版と 2 つの digest だけで、Python / numpy / OS の版はどこにも記録されない（`uv venv` が `.python-version` 無しでどの interpreter を選ぶかは外部知識・未確認）
- 完了条件: `.python-version` が存在し `tests/test_ci_config.py` で照合される、runbook（P2-04.23）に venv の 3 行がある、新規 snapshot manifest に 3 欄が非 null（P1-07.13 の manifest テストに 1 行）。既存テストは不変（`tests/test_ci_config.py` は .25 で新設）
- 規模・整合: S / repair（規約と手順、来歴の記録 = ADR-0075 の observability。新しい計器も能力も足さない）   出典: R3-OSX-05   依存: D-P1-08-1   順序: (a) は .25 と同 PR、(b) は P2-04.23 と同 PR、(c) は P1-07.13 PR-A と同 PR


**依存**
- P0-06.3（`packaging` job の床 leg: 束の完了条件 1 行目）/ P0-06（D-P0-06-1 の床 = 3.11、v2.13.0 の tag 日 → .5 の決定時期 D-P1-08-1 = 11-14）
- P0-02.2 / RFC-0046 後始末 3（旧 gate 削除、10-17）→ .12
- P0-03.3（`test_sync_research_data_shell.py` の helper 書き換え）→ .2 の rsync skip
- P1-10.5（週次セッションの deny テスト。`test_c_scope_6_read_scopes_survive_in_the_deny_list` は platform 限定が無く .1 の 2 セルとも走る）/ P1-10.6（`allow_redirects=False` の修理）: .17 の前か同 PR
- P1-01.6（凍結後の tests/ 規則 (5)）/ P1-01.1（`freeze_reading.py` の tests 系列: .10 の読み 1 行）
- P1-04（ADR-0101 消費計画、TQ-29 / TQ-30 evals、評価層の位置づけ）→ .21 / P1-04.7（旧 .16 の吸収先）
- P0-06 の release PR（.5 の ADR-0109 追補を D-P0-06-2 A の分と 1 本に）
- → 参照元: P0-06（.3 / .6 が .1 の 2 セルと .5 (B) の 2 行手順を引く）、P0-05（.9 の smoke は verify 2 セルで走り、TOTAL の床 94 は .7）、P1-06（.1 PR-A の前に .8、固定テストの表の構成員 .8 / .17 / .18 / .25。P1-06.2 が .25 を表に載せる）、P1-06.4（env キーの正本 `core/env.py`。.17 は env 列を持たない）、P1-10.1（.17 のテスト定数から表を生成）、P1-10.13 / .14・P2-02・P2-03・P2-04・P2-05.1・P3-05.19（shell テストは .1 の macOS セル、harness は .3、ubuntu の skip は .2 の期待集合）、P1-13.5（CONTRIBUTING が .23 / .24 を指す）、P1-11（AR-24 / SB-21 conformance kit が TQ-28 の受け皿）、P1-01（凍結判定は本束の固定テストが前提）、P0-03.11（R1-SEC-03: `real_sample.jsonl` の除去 = 旧 .16 の該当行）、P1-07.13（.26 (c) の 3 欄を manifest に写す。.26 (c) は PR-A と同 PR）、P2-04.23（.26 (b) の venv 段と同 PR）


#### P1-09 ドキュメントの同期と欠落文書（数値・CYCLES・CONFIGURATION・glossary・llms）
- 狙い: ADR-0102 の論理（古い機構記述は無記述より有害）が CYCLES・CONFIGURATION・llms・data repo の説明文に跳ね返っている。北極星（ADR-0080）の「止まる」を第三者が検証できるのは文書が実体と一致している時だけなので、修理を 3 種に限る — 生成できるものは生成する（生成元とスクリプト名を書く）／手書き数値は日付つきにする／存在しないものへの案内は消す。能力は増やさない。
- 期限・順序: 着手 2027-01-23 の土曜ゲート（§4.0）。期限 2027-02。索引・件数・退役導線は依存なしで先に入れる（いずれも §4.0 の先行列）: .1 / .8 / .9 は 11-28 の週、.10 / .13 / .14 は 12-05 の週、.2 は 2027-01-09 の週（P1-11.1 の状態列と同じ PR。`CLAUDE.md:164-167` の同じ 4 行を触り、状態列は 12-26 の D-P1-11-3 / -6 の後でしか書けない）。.14 の README は `docs/plans/roadmap-2026-10/`（P2-01.10 が 10-17 に置く）を例外として名指す。llms・図・release checklist 系（.7、.19）は P0-02（旧 relevance gate 削除）と P0-06（v2.13.0）の後に 1 回で更新する方が安い（外部リンクの確認は P0-06.6 の release runbook の 1 段）。.20 は D-P1-09-3（12-26 の土曜ゲート）の後。環境変数台帳（旧 .3）は P1-06.4 の `core/env.py` 登録簿から生成する。D-P1-09-1（言語方針）と D-P1-09-2（diagrams の鮮度規約）は 2027-01-23 の土曜ゲート（.19 の 00 図更新は D-P1-09-2 の後、P0-02 完了後に 1 回）。.5 は文書 3 面の一致だけで、ADR-0010 の書き換えは D-P2-04-1（2027-02-06）と D-P2-05-1（12-12）の後に P2-04.1 が 1 本の partial supersede で起こす。.6 が触る `weekly-gate/SKILL.md:28`（「A-E レポート」の語）は 2027-01-23 のゲートの後の平日の PR で入れる（.6 は §4.0 の先行列に無いので 10-17 / 10-24 / 10-31 の同梱 PR には乗せない。Step の所有者は変えない）。
- 束の完了条件:
  - 実体数 = 表の行数が docs テストで固定される: `docs/evidence` dir 数、`docs/runbooks/*.md` 数、tracked の skill 数（`git ls-files '.claude/skills/*/SKILL.md'`）、`--weekly-*` フラグ集合、CONFIGURATION en/ja の `## ` 数。`CommandSpec` 名 + tier・`config/launchd/` label・env キー・`config/prompts/*.md` stem の表は `tests/test_architecture.py` の literal snapshot（P1-06 の束完了条件）と照合する側に回す（env キーの正本は `core/env.py` 登録簿 = P1-06.4）。
  - `scripts/docs_consistency_scan.py` の `notes_ref` が rfcs/ を含み、週次 JSON の findings が 0。
  - `grep -rn 'A-E\|A–E\|Mon 08:00\|distill at 03:00\|120min\|packet 13:30\|/install.sh\|until that defect\|rules-distill\|Qwen3.5 9B' <各項目の対象>` が歴史記述を除き 0 件。
  - README en/ja・llms-full・CLAUDE.md・CONFIGURATION の手書き件数すべてに `as of <日付>` と集計コマンドが付く（または件数が消えている）。
  - 新規文書 3 本（glossary (A) 部・`docs/TROUBLESHOOTING.md`・`docs/plans/README.md`）が存在し README か CLAUDE.md から辿れる。

##### P1-09.1 索引を実体から生成する（docs/evidence・docs/runbooks）
- 何を: `docs/evidence/README.md` の表を `ls docs/evidence`（各 dir の README 1 行目を説明列に）から生成する 1 本（例 `scripts/gen_evidence_index.py`）を置き、命名規則に `rfc-NNNN/` と `<slug>-YYYYMMDD/` を正式化する。`docs/runbooks/README.md` に `constitution-amendment.md`（ADR-0090 の手順、`llms-full.txt:328` が参照）を足し、Docker 行を削る。
- 根拠: `docs/evidence/` 37 dir に対し表は 15 行、未掲載 22（adr-0049 / 0053 / 0060 / 0062-parser-rewrite / 0081 / 0086 / 0089 / 0092 / 0093 / 0094 / 0096 / 0102、rfc-0011 / 0014 / 0023 / 0041 / 0043 / 0044 / 0045 / 0046、verify-solve-model-compare-20260701、weekly-gate-step4-comply-20260808）; `docs/runbooks/README.md:10-13` は 4 本のみ、`:27` に Docker 行（ADR-0070 で撤去済み）
- 完了条件: `ls docs/evidence | grep -v README.md | wc -l` = 表の行数、`ls docs/runbooks/*.md | wc -l` − 1 = 表の行数（`tests/test_doc_links.py` 系に 2 assert、または scan に `index_gap` 検査）。
- 規模・整合: S / repair   出典: DC-29 AB-39 OI-41 DC-30

##### P1-09.2 CLAUDE.md の表を実体に合わせ、件数一致をテストで固定する（skills 表・関連 repo・docs 配置）
- 何を: skills 表に `weekly-gate`（公開版なし・CA 固有、ADR-0098）を足す（`upstream` / `edition` の列は P1-13.8 と同じ表）。関連リポジトリ節に `contemplative-agent-otel`（ADR-0078、凍結/維持の状態は P1-11 の決定を引く）と AKC / AAP を足し、README「Adapters and add-ons」と `llms.txt` Related にも otel を 1 行 — `CLAUDE.md:164-167` の同じ 4 行を P1-11.1 が状態列で編集するので 1 PR にする。ドキュメント配置節に plans / diagrams / CYCLES / DEVELOPMENT-RECORDS / BIBLIOGRAPHY / otel-semconv-mapping を加える。
- 根拠: `ls .claude/skills` = 11 に対し `CLAUDE.md:120-131` の表は 10 行（本文 `:48,146` は `/weekly-gate` を参照）; `CLAUDE.md:164-167` は rules / data / cloud / mlx の 4 件で、ADR-0088:333 が otel の欠落を「記録」したまま; `README.md` に otel 0 件、`llms.txt` の otel は ADR-0078 行（:132）のみで Related（:182-187）に無し; `CLAUDE.md:110` は adr / evidence / runbooks / security / glossary / CONFIGURATION のみ、`ls docs/` は 15 エントリ
- 完了条件: 表の行数 = `git ls-files '.claude/skills/*/SKILL.md' | wc -l`（テストは tracked のみを数える。手元の未追跡 skill と CI で結果が割れない）; 兄弟 5 repo + AKC / AAP が CLAUDE.md と README の両方に載る; `ls docs/` の各エントリが配置節に 1 行ずつある; ADR-0088:333 に解消の dated note。
- 規模・整合: S / repair   出典: DC-07 DC-08 SB-35 DC-09 R3-HRN Fix-01   順序: 2027-01-09 の週（§4.0 の先行列。P1-11.1 の状態列と同じ PR）

##### P1-09.4 スケジュール記述（曜日・時刻・分・セッション長・フラグ・plist コメント）を `schedule.py` に揃える
- 何を: CONFIGURATION en/ja と `CLAUDE.md:58` のフラグ列挙に `--watchdog` と `--weekly-submolt-scan` を足し、既定を「60 分 / distill HH:30 / insight Sat 08:00 / submolt-scan Thu」に直し、既定曜日は Scheduling 節 1 箇所だけに書く。`com.moltbook.insight.plist:30-31`（Mon 08:00）、`com.moltbook.watchdog.plist:20` と `pipeline_watchdog.sh:81`（packet 13:30 / 13:00）、`cli/memory_cmds.py:62-64`（insight は manual）のコメントを現行に直し、ADR-0085 D6（`:81-82`「packet by 13:00」）に dated note。`tests/test_cli_schedule.py` に「`--help` の全 `--weekly-*` フラグが CONFIGURATION.md に現れる」検査。
- 根拠: `docs/CONFIGURATION.md:210`「default Mon 08:00」vs `:400`「Sat 08:00」vs `schedule.py:623-629` default 6（「Monday default was retired 2026-07-29」）; `:396`「120min sessions, distill at 03:00」（ja:248 同文）vs `schedule.py:598` default 60・`:342` `:30`・`com.moltbook.distill.plist:34` Minute 30; `:59-63` と `CLAUDE.md:58` に `--weekly-submolt-scan` 無し（`schedule.py:659-669` default Thu、ja:75 にはある — 英語正本が ja より古い）
- 完了条件: `grep -rn 'Mon 08:00\|distill at 03:00\|120min\|120分\|packet 13:30' docs/CONFIGURATION*.md CLAUDE.md config/launchd/ scripts/pipeline_watchdog.sh src/contemplative_agent/cli/memory_cmds.py` 0 件; フラグ検査テストが通る。
- 規模・整合: S / repair   出典: DC-15 DC-16 DC-17 CU-20 WO-40 CP-30 WO-41

##### P1-09.5 CYCLES.md を再生成し、job 表を `config/launchd/` と一致させ、sync-data の実行主体を 3 文書で揃える
- 何を: FRESHNESS header を HEAD で再生成し、master table に submolt-scan（Thu）/ backup（Mon）/ ollama-restart を足し、`com.moltbook.sync-data` を実体に直す。「public / owner-private」列を足し、Cycle #1 / #2（`com.shimomoto.daily-research`、`com.shimo.wiki-refresh`）を owner-private と明記して検証手順から外す。`README.md:102`「commands you run yourself」・`docs/adr/0010:38`「post-processing step of the distill command」・CYCLES row 9 を同じ主体で揃える。ADR-0010 の書き換え（実行主体・HF upload・ADR-0015 との関係）はこの項目では行わず、D-P2-04-1 と D-P2-05-1 の後に P2-04.1 が 1 本の partial supersede で起こす（除外リスト = 開示境界の記述は → P0-03）。
- 根拠: `docs/CYCLES.md:1-7` generated 2026-08-26 / 117b04b、`git log` は 09-05 に 2 commit（c914b4e / 6cbd6ca）で header 未更新、HEAD から 377 commit 遅れ（data repo `docs-consistency-2026-10-02.json` では 350 / 38 日）; `:92` `com.moltbook.sync-data` に対し `config/launchd/` 8 本に無し、`scripts/*.sh` / plist / skills に `sync-data` の呼び手無し（data repo 最終 commit `sync: 2026-10-09T20:30:08Z` = 05:30 JST は定時 job を示唆 — 推測、repo 外）; `:214` の検証手順は `ls ~/Library/LaunchAgents/com.*`
- 完了条件: header の source-commit = `git log -1 --format=%h -- docs/CYCLES.md`; table の `com.moltbook.*` 集合 = `config/launchd/` の label 集合; 各行に public / owner-private; 3 文書の sync-data 主体が同一文。
- 規模・整合: S / repair   出典: DC-24 WO-38 CP-31 SA-03 WO-20 R3-ADR Merge-02

##### P1-09.6 週次チェーンの段構成記述（script 冒頭・skill・CYCLES row 5）から旧 A-E と旧パスを消す
- 何を: `scripts/weekly-pipeline.sh:1-21` を「materials → /weekly-report（六節 instrument document + diagnosis + draft filing）→ sample splice → promote → 計器 6 本 → spawn」に書き換え、`:126` の時間内訳と `:184-187` の矛盾を解く。`.claude/skills/weekly-gate/SKILL.md:28`「A-E レポート」と `.claude/skills/weekly-report/SKILL.md:20-21` の既定パス（`reports/analysis/…-materials.md`）を `logs/weekly-pipeline/<run_id>/materials.md` に直し、CYCLES row 5（`:88`）を script 冒頭と同文にする。`docs/CYCLES.md:218` の `weekly-analysis-ja.md` を落とす。
- 根拠: `CLAUDE.md:5,13`「段構成は script 冒頭コメントが正本」に対し `weekly-pipeline.sh:3`「A-E synthesis + ja」`:20`「no complete A-E report」、同ファイル `:184`「Japanese translations retired … (2026-08-26)」; `weekly-pipeline.sh:165` `MATERIALS="$RUN_LOG_DIR/materials.md"` vs weekly-report SKILL:20-21（weekly-gate 側だけ 7a152b0 で修正済み）; `config/prompts/` に `weekly-analysis-ja.md` 無し（`tests/test_packaged_assets.py:35` が retired と明記）
- 完了条件: `grep -rn 'A-E\|A–E\|weekly-analysis-ja' scripts/weekly-pipeline.sh scripts/weekly-analysis.sh .claude/skills/*/SKILL.md docs/CYCLES.md` 0 件; materials の既定パスが 3 箇所で同一規則。
- 規模・整合: S / repair   出典: DC-25 DC-26

##### P1-09.7 ADR 追加時の同期対象を llms.txt・HF mirror・共有フォルダまで広げる
- 何を: `CLAUDE.md:11` の「ADR 追加時に更新」対象（graph.jsonld のみ）に `llms.txt` の ADR 行と `llms-full.txt` の Facts を加え、`tests/test_adr_status_consistency.py`（現在 body / README en・ja / graph の面のみ）に「`llms.txt` の最大 ADR 番号 = `ls docs/adr` の最大番号」を足す。graph.jsonld の HF mirror（`Shimo4228/contemplative-agent`）同期を `/release-doi` か ADR 追加規約に組み込み、HF `lastModified` と `git log -1 -- graph.jsonld` の差を `docs_consistency_scan.py` の reading に足す。共有フォルダ `/mnt/project-files/knowledge/Contemplative agent llms-full.txt`（v2.0.0）を現行で差し替える。
- 根拠: `llms.txt:162` が最後の ADR 行（ADR-0108）、`llms-full.txt:22`「ADRs: 108 total」vs `ls docs/adr` 113（両ファイル最終更新 2026-09-12、950f190 / c958d1f）; HF `Shimo4228/contemplative-agent` Updated 12 Sep 2026（connector で再確認）vs graph.jsonld の commit 09-19 / 09-20 / 09-22 / 09-25 / 10-03 / 10-07 / 10-09、同期手順は repo 外 `~/.claude/skills/jsonld-knowledge-graph/SKILL.md`（`CLAUDE.md:171`）; 共有ファイル `:11` Version 2.0.0、`:15` tests 1115、`:18` Qwen、`:21` rank-bm25、`:22` ADRs 30
- 完了条件: 新テストが通る; HF の Updated 日 ≥ graph.jsonld の最終 commit 日; 共有フォルダの llms-full が `Version: 2.13.0` 以上を名乗る。
- 規模・整合: S / repair   出典: DC-02 DC-03 DC-45

##### P1-09.8 手書き数値に「as of 日付 + 集計コマンド」を付けるか消す
- 何を: README en/ja（82/547・6/11・2/4・約 10,700 patterns）、`llms-full.txt`（Tests / test files / ADRs / free disk）、`CLAUDE.md:5`（70 ファイル）、`CONFIGURATION.md:254`（45 skills ≈ 36K）、`:89-94`（skills (2) / rules (2) — `tabula-rasa` は constitution のみ）の各数値を「as of <日付>（`<集計コマンド>`）」にするか、件数を消して出典（`docs/adr/README.md`、`pytest --co -q | tail -1`、data repo DATACARD）へ寄せる。`/release-doi` に再計測ステップを 1 行（→ P0-06）。
- 根拠: `README.md:139`「about 10,700 patterns as of October 2026」vs data repo `jq '.patterns|length'` = 10,985（sync 2026-10-09T20:30Z、2.6% ずれ）; `llms-full.txt:15`「3983 … 113 test files」vs `ls tests/test_*.py` 126・`def test_` 4,059、`:20`「~12 GB」vs `README.md:60`「about 10 GB」; `CLAUDE.md:5` 70 vs `grep -rlE 'ADR-0[0-9]{3}' src/ --include='*.py' | wc -l` 78; `CONFIGURATION.md:254` 45 vs data repo `skills/*.md` 53; `config/templates/tabula-rasa/` に skills / rules 無し
- 完了条件: 上記ファイルの手書き件数すべてに日付と出典が付く（`grep -nE '[0-9]{2,} (skills|patterns|files|tests)' README.md llms-full.txt CLAUDE.md docs/CONFIGURATION.md` の各行に `as of` がある）か、件数が消えている。
- 規模・整合: S / neutral   出典: DC-05 DC-06 DC-18 DC-19

##### P1-09.9 退役済みの手順・欠陥・モデル名への案内を消す
- 何を: `docs/CONFIGURATION.md:284-294` の `-ca` 節を削り「coding agent 向けは episode-log 保護 hook のみ（`integrations/README.md`）」に置換、0 件をコピーする `integrations/{claude-code,codex,cursor}/install.sh` を撤去。`docs/runbooks/constitution-amendment.md:38-42` の「Known defect … mandatory until that defect is fixed」を「v2.11.0 で修正済み（`cli/adopt.py:183 _replaces_canonical_target`）。単一ファイル確認と hash 照合は欠陥と無関係の恒久手順」に書き換え。`CLAUDE.md:21` `uv pip install -e ".[dev]"` を `uv sync`（eval は `--group eval`）に。`prompting.py:346` / `feed_seeder.py:59` の Qwen 校正根拠を「gemma4:e4b で再確認済み」か「Qwen 校正のまま未再測定」と明記（再測定自体は → P1-07）、`glossary.md:335` の `qwen3.5:9b` と `:193` decision packet（ADR-0098 で退役）に historical / retired 注記。
- 根拠: `integrations/README.md:59`「Skills (Shelved) … ADR-0013」、`integrations/skills/` 不在、`install.sh:8-16` は `*-ca` を走査して「0 skills installed」; `CHANGELOG.md:76`（v2.11.0、T-ADOPT-OVERWRITE-TARGETS 10c6df4）vs runbook `:38,42`; `pyproject.toml:66-69` は `[dependency-groups]` のみで `tests/test_dependency_floor.py:37` が extras を禁止（RD-14 実走: `.[dev]` は exit 0 で pytest が入らない）; `backend.py:20-24` は gemma への交代を正しく記述
- 完了条件: `grep -rn '\-ca' docs/CONFIGURATION*.md` 0 件、`integrations/` 内のパスがすべて実在; runbook に「until that defect is fixed」無し; 新規 clone で CLAUDE.md の手順どおり `uv run pytest` が走る; 現行コードのコメントに旧モデル名が根拠として残らない。
- 規模・整合: S / repair   出典: DC-20 CU-18 GO-45 VL-30 RD-14 CU-39 DC-23

##### P1-09.10 CONFIGURATION.md の文言を実装に合わせ、TOC と ja 版を見出し単位で同期する
- 何を: `:26`「Create identity + knowledge files」と `:172`「Starts empty at init」を「`--template`（既定 contemplative）から identity / constitution / skills / rules / prompts / views を複製、knowledge は空」に、`:373` GUARDED「passes safety filters」を「forbidden-pattern list（`core/llm/guard.py`）と空文字のみ。品質・事実性は見ない」に直す。TOC に Pipeline Prompts & View Seeds / Runtime Logs を足し、ja に 2 節を訳すか「英語版のみ」の見出しを置く。CLI 節（`:21-63`、14 本）を `CommandSpec` 21 本（tier 別・1 行説明）で書き直す（旧 .3 の CLI 部分。名前集合は P1-06 の snapshot と照合）。autonomy 表（`:372`）に APPROVE で確認される副作用（subscribe / upvote post / upvote comment / follow / unfollow / mark-read / post / reply）の 1 表を置き、`_confirm_action` / `_confirm_side_effect` の呼び出し箇所の集合と一致する docs テストを添える（旧 P1-14.1 の文書部分）。
- 根拠: `cli/session_cmds.py:56-117`（テンプレ 7 種を複製）; `adapters/moltbook/agent.py:366-370` docstring「only checks forbidden patterns and emptiness」; `docs/CONFIGURATION.md:9-17` TOC 9 項目 vs `## ` 11 節（`:298` Pipeline Prompts & View Seeds、`:452` Runtime Logs が無い）; `docs/CONFIGURATION.ja.md` は 9 節（両節無し、両ファイルとも 4b85f22 で同日更新）; registry 21 本に対し `docs/CONFIGURATION.md:21-63` は 14 本（`shadow-constitution` / `status` / `dialogue-peer` は文書全体で 0 件、`README.md:155` は `report` を設計変更の入口として案内）; 確認点 `adapters/moltbook/agent.py:277`（subscribe、毎セッション 8 連続）、`feed_manager.py:679`、`reply_handler.py:565,674`、`agent.py:670,695` vs `README.md:96`「waits for your OK on every post」
- 完了条件: TOC 項目数 = `## ` 見出し数 − 1、en/ja の `## ` 数が一致（`tests/test_doc_links.py` 系に対照テスト）; `init` の文言が `init` の出力と一致; GUARDED の文言が docstring と一致; CLI 節の名前集合 = snapshot の `CommandSpec` 名集合; 副作用表の集合 = `_confirm_*` 呼び出し箇所の集合（テスト）。
- 規模・整合: S / repair   出典: CU-17 CU-19 DC-12 DC-13 DC-21 CU-37 CU-08

##### P1-09.11 data repo の説明文（README en/ja・llms.txt・DATACARD）の退役語・旧パス・モデル名を直し、同期を release checklist に置く
- 何を: 対象 3 文書の stale を一度に直す — `README.md:36` / `llms.txt:14` のフローから `rules-distill`（ADR-0097 で退役）を外す; `README.md:45` / `DATACARD.md:104`「`logs/*.jsonl`」→「`logs/` 全体」、`DATACARD.md:107`「excluded via `.gitignore`」→「`sync-research-data.sh` の `--exclude` が唯一の境界、`.gitignore` は第二の網」; `README.md:50` の rules repo 説明 →「論文 Appendix C の verbatim 配布（ADR-0002）」; `llms.txt:9` Qwen → gemma4:e4b、`:12`「JSON + SQLite embeddings」→ embedding-free、`:13` Views 7 → 2、`:17` kinds に `rules-distill_*` / `skill-stocktake_*`、`:71`「eight skills」→ 53、`:94` の存在しない manifest 例と「every file and its hash」を実物に; `DATACARD.md:20-21`「never hand-edited」を本体 README:142 の手編集公認と揃える; EN/JA の Related に AAP を揃える。本体の release checklist（→ P0-06）に「data repo 説明文の同期」を 1 行。
- 根拠: `sync-research-data.sh:72-80` が README / README.ja / llms.txt / DATACARD を sync から除外（手動保守前提）、`:81-82` が `logs/` と `agents.json` を除外; data repo `views/` 2 本、`skills/` 53 本（最新 20260822）、`snapshots/distill_20260504T180001646486Z` 不在、snapshot kinds に rules-distill 1 / skill-stocktake 1、`README.ja.md:52` に AAP・`README.md` Related に無し
- 完了条件: `grep -n 'rules-distill\|Qwen3.5\|logs/\*\.jsonl\|Views shipped: 7\|eight distilled\|via \`.gitignore\`' README.md llms.txt DATACARD.md` が歴史記述を除き 0 件; release checklist に同期行がある。
- 規模・整合: S / repair   出典: DC-46 DE-14 VL-43 PF-30 SA-40 DE-21

##### P1-09.12 rules 層の出自を 3 文書で揃え、frontmatter に origin を付ける
- 何を: 本体 `README.md:141,151`「hand-written」、data repo `README.md:36` / `llms.txt:14`「emitted by `rules-distill`」、`README.ja.md`「知識から蒸留」を 1 つの事実に揃える — 2026-04-11 の 2 件は rules-distill 産（ファイル名の日付 suffix と Practice / Rationale 書式からの推定）で以後は人手管理、生成器は ADR-0097 で退役。`rules/*.md` 2 件に `origin:` / `adopted:` の frontmatter。rules 層の今後（凍結 / 廃止）は本束では決めない（→ P3-07）。
- 根拠: data repo `rules/` = `flow-with-contextual-fluidity-…-20260411.md`、`prioritize-semantic-depth-…-20260411.md`（frontmatter 無し）; `pipeline/value-layer/value-layer-2026-10-02.json` rules `files: 2, days_since_newest: 174`; `snapshots/rules-distill_20260815…` 1 件
- 完了条件: 3 文書の rules 記述が同一文; 2 ファイルに frontmatter があり `value_layer_due_check.py` が読める。
- 規模・整合: S / repair   出典: VL-38 PF-32

##### P1-09.13 `.notes/` 参照を rfcs / ADR 本文から消し、scan を rfcs に広げる
- 何を: `scripts/docs_consistency_scan.py:398` の `check_notes_refs`（現在 ADR のみ）を `rfcs/` へ広げ、既存参照（rfcs 21 本・ADR-0113 en/ja）は「非公開（理由: 他エージェント本文を含む）」注記付き参照か `docs/evidence/` に固定した読み値ファイル（例 `docs/evidence/rfc-0046/label-set-2026-09-28.json`）へ置換する。
- 根拠: `CLAUDE.md:114`「ADR / rfcs 本文から `.notes/` を参照してはならない（gitignored）」; `grep -c '\.notes/' rfcs/*.md` 非 0 が 21 本（0046 / 0040 / 0014 / 0013 / 0004 が各 5）; `docs/adr/0113-*.md` / `.ja.md` 各 1（`.notes/labels/relevance/2026-09-28/`）
- 完了条件: scan の `notes_ref` が rfcs/ を対象に含み findings 0; 新規参照が週次 JSON に出る（`tests/test_docs_consistency_scan.py` に rfcs ケース）。
- 規模・整合: S / repair   出典: AB-05

##### P1-09.14 docs/plans に README を置き、以後の plan は .notes へ
- 何を: `docs/plans/README.md`（英語 3 行: 承認済み plan の記録（ADR-0085 由来、当時のまま変更しない）、機構の正本ではない（正本はリンク先 ADR / RFC）、ハーネス参照は当時のもの。加えて例外 1 行「`roadmap-2026-10/` は採択済みロードマップの凍結版。更新は束の閉じ表（P2-01.12）と `decisions.md` の配り直し・繰り越し（P2-01.12 / .14）だけ。裁定は `gate_item` が正本」）を置き、CLAUDE.md 配置節に 1 行（.2 と同 PR）。以後の plan-mode ファイルは `.notes/`（gitignored）に置き、tracked 追加を止める。lint 除外を残すなら README で宣言。
- 根拠: `git ls-files docs/plans | wc -l` = 77、README 無し、`.markdownlint-cli2.jsonc:23` で lint 除外; `~/.claude` 参照 30 ファイル、個人名 2 ファイル; `docs/plans/zany-marinating-floyd.md:41` が退役済み `.notes/TASKS.md` を参照
- 完了条件: README が存在し例外行がある。以後 `git log --diff-filter=A -- docs/plans ':!docs/plans/roadmap-2026-10'` に新規ファイルが無い。
- 規模・整合: S / neutral   出典: DC-09 WO-21 TQ-41 R3-FUT Fix-02   依存: P2-01.10（`roadmap-2026-10/` の凍結版、10-17）

##### P1-09.15 glossary を「現行機構語彙 + 翻訳表」の 2 部構成にする
- 何を: `docs/glossary.md` に (A) 現行機構語彙（1 行定義 + 所有 ADR/RFC: value layer / staging・`.staged` / approval gate / episode・pattern・view / distill・insight / decision backend・face・score4・relevance gate・fail-closed / shadow・paired・enforce-first / weekly chain・weekly gate・triage loop・dead-band / census statuses（KEPT / QUIET）/ confusion pairs / comment outcomes）を足し、(B) 既存の翻訳表を残す。退役語に「retired by ADR-NNNN」、`:317` の `contemplative-moltbook/` を直す。
- 根拠: `grep -c -i` で score4 / Jev / triage / dead-band / decision backend / relevance gate / weekly gate / fail-closed / QUIET が各 0、face 1（KEPT 4）; `:193` decision packet は ADR-0098 で退役（注記無し）; `README.md:189` が Glossary として案内
- 完了条件: README Core concepts 5 語と ADR-0101〜0113 の見出し語が (A) にある（`grep -c` 各 ≥ 1）。
- 規模・整合: M / neutral   出典: DC-39

##### P1-09.17 docs/TROUBLESHOOTING.md（症状 → 原因 → 見るログ）
- 何を: 英語 8〜10 行の表 — feed が無反応（fail-closed、`gate_source: "fail_closed"` / `enforce_reason`、`logs/relevance-*.jsonl` と session の WARNING を見る）/ Ollama 未起動 / モデル未 pull / logprobs 無し / insight 拒否（`.last_insight`、未審査 batch）/ staging 詰まり / 2 モデル共載 swap / launchd が env を見ない / `MOLTBOOK_API_KEY` と credentials.json の優先順。README には症状→原因→確認ログの段落を置かず Quick Start 末尾の 1 行リンクだけにする（P0-05.10 (a) を吸収。(b)(c) は P0-05.10 に残る）。
- 根拠: 既知の挙動が `CONFIGURATION.md:203-209`（insight 拒否）、`:252-256`（fallback 不収容）、`:475-487`（relevance_cache 14 日）、`CLAUDE.md:38`（swap 17 GB）に散在; 開発者向けは `docs/runbooks/silent-llm-calls.md` のみ
- 完了条件: ファイルが存在し README Quick Start からリンク; P0-05 の preflight が出す各エラー文言が表の行に 1 対 1 で対応。
- 規模・整合: S / neutral   出典: DC-41 DC-33（README 段落の半分）

##### P1-09.19 docs/diagrams の鮮度規約の適用範囲を明記し、00 図を最終形で 1 回更新する
- 何を: `docs/diagrams/README.md` に適用範囲（値層ループのみ / feed 側ゲートも含む）を書き、含めるなら 00 図に relevance gate（score4、`thresholds.relevance_score4`）と seed 選択を 1 ノード足して再 deliver。P0-02 の削除後に 1 回で行う。
- 根拠: `docs/diagrams/README.md:1-7`「refresh: any PR that changes a pipeline gate, threshold …」; `git log -- docs/diagrams` 最終 2026-09-19（source-commit 99ea8bb から 277 commit）; `grep -il 'score4\|relevance' docs/diagrams/*.json` 0; ADR-0113 追補 2 回（968a83e / 4b85f22）は docs/diagrams を触っていない
- 完了条件: README に scope 文がある; 含める場合 00 図の JSON に `relevance_score4` ノードがある。
- 規模・整合: S / neutral   出典: DC-27

##### P1-09.20 OS 前提（macOS / launchd・POSIX ロック）を README と CONFIGURATION に宣言する
- 何を: README Requirements に「macOS / Linux（POSIX `fcntl` ロック必須）。Windows は WSL」、CONFIGURATION の Scheduling 節に「`install-schedule` は macOS（launchd）のみ。他 OS は `run --session` を自前で起動」を各 1〜2 行。cron / systemd の例は同梱しない（やらないこと候補）。
- 根拠: `core/_io.py:17` `import fcntl`; `cli/schedule.py:303-304`「install-schedule is only supported on macOS (launchd)」; `README.md` / `docs/CONFIGURATION.md` に linux / cron / systemd / WSL の記述 0 件（`README.md:60` は「tested setup is an Apple Silicon Mac」のみ）
- 完了条件: 2 文書に宣言行がある（`grep -ci 'launchd\|WSL' README.md` ≥ 1、Scheduling 節に macOS-only 文）。
- 規模・整合: S / neutral   出典: CU-30 RD-26


**依存**
- P0-02（旧 relevance gate 削除）→ .7 の llms-full Facts・.19 の図は削除後の最終形で 1 回。
- P1-06（.4 `core/env.py` 登録簿 = 旧 .3 の環境変数台帳の正本、表面 literal snapshot — 本束の docs テストはこれと照合する側。.10 は 12-05 の週に `CommandSpec` の実体と照合して書き、P1-06.2 の snapshot が入ったら照合先を snapshot に替える）。
- P0-06（v2.13.0 release runbook）→ .7 / .8 / .11 の「release checklist に 1 行」はそこに置く。
- P0-05（Quick Start preflight）→ .17 の表はエラー文言確定後。
- P0-03（開示境界の allowlist 化）→ .5 の sync-data の記述と .11 の除外説明は P0-03 の allowlist と同文にする。
- P2-01.10（`docs/plans/roadmap-2026-10/` の凍結版、10-17）→ .14 の README の例外行。
- P1-11（兄弟 repo の処遇）→ .2 の otel 行の状態（凍結 / 維持）は D-P1-11-3 の結論を引く。
- P1-02 / P1-03（RFC / ADR 台帳の索引生成）→ .1 / .7 の生成スクリプトは同じ方式（`scripts/` 配下、header に生成元）に揃える。
- HF トークン（既存 `hf upload` 経路）→ .7 の mirror 同期。
- → 参照元: P1-11.1（.2 の関連リポジトリ節は P1-11.1 の状態列と同じ PR。P1-11.1 の参照棚卸し表が `docs_consistency_scan.py` に「兄弟名が出る面 ⊆ 一覧面」の 1 検査を足す — .13 と同じ scan、graph.jsonld → HF は .7 の経路）、P1-13.8（AAP / AKC 由来 skill の `upstream` / `edition` 列 — .2 の skills 表と同じ表、同じ件数一致テスト）、P1-14（旧 P1-14.1 の「確認される副作用」一覧は .10 の表に、旧 P1-14.7 の非 macOS 手引きは .20 の宣言 + D-P1-09-3 A で代替）、P0-05.10（(a) の症状→原因→確認ログは .17 に吸収、README は 1 行リンクのみ — R1-NEW Merge）、P1-12.7（.10 の副作用 1 表 = GOVERNANCE.md の素材）、P3-07（.12 は出自の記述のみ）、P2-04.1（ADR-0010 の partial supersede は P2-04.1 が 1 本で起こす。.5 は文書 3 面の一致だけ）、P2-01.12（束の閉じ表は .14 の例外行の唯一の更新経路）、P1-05.5（`enja_drift` の数え方は D-P1-09-1 A の運用規則）


#### P1-10 セキュリティ: threat model・SECURITY.md・I/O 面の機械ゲート・鍵の所在
- 狙い: 北極星（ADR-0080）のセキュリティ層は「absence の維持」であり、到達点は守りを足すことではなく「何が無いか」を英語の正本 1 枚と機械検査で証明できる状態にすること。今は脅威モデルが `CLAUDE.md:91-100`（日本語）にしか無く、`docs/security/` は 2026-04-01 止まり、機械強制（hooks）は repo 外の harness にしか無いので、レビューのたびに同じ問い（権限を持つエージェントの脅威モデルの持ち込み、CLAUDE.md:94）が再発する。
- 期限・順序: 着手 11-14 の土曜ゲート（§4.0）。期限 2026-12（.1 threat-model は 2027-01。.3 / .4 は D-P1-10-1 / -2 = 2027-01-23 の後）。コード修理は .5 / .6 が 10-24 の週、.7 / .8 が 11-07 の週（§4.0 の先行列。いずれも v2.13.0（P0-06）の tag 前に S で片付く）。.15 の probe は 10-24 の週（§4.0 の先行列。.5 と同じ PR、オーナーの Mac で 1 回）。threat-model（.1）は P1-08 の I/O allowlist テスト（SA-01）と P1-11 の推論 egress 分類（SA-19 → D-P1-11-4 = 12-05）が決まってから表を固定する。hooks（.4）は D-P1-10-1（2027-01-23）の後。.3（SECURITY.md）は D-P1-10-2（2027-01-23）A の実装で決定前は着手しない（受付文面の正本は NOTICE の takedown 節と受付台帳 = P3-05.14（11-21）で、.3 は後からリンクするだけ）。回転 runbook（.9）の Moltbook 再発行可否は P1-07.19 の再読台帳の初回行（11-14 の週、§4.0 の先行列）を引く。shell テスト（.13）は P1-08.1 / .3（12-19 着手）の後に足す（macOS セル、harness は P1-08.3）。.5 の deny テストは text-level で platform 限定が無い。`weekly-pipeline.sh` を触る .5 / .13 / .15 は P2-04.13 PR-A より前に入ってよい（PR-A は挙動不変の移動で、後から rebase する）。verb 集合を読む .14 も PR-A の前後を問わない（PR-A は verb 集合を変えない）。.12 が触る `weekly-gate/SKILL.md` Step 6d の点検範囲 1 行は 11-14 のゲートの後の平日の PR で入れる（.12 は §4.0 の先行列に無いので 10-17 / 10-24 / 10-31 の同梱 PR には乗せない）。
- 束の完了条件:
  - `docs/security/threat-model.md` + `.ja.md` が存在し、`README.md` の「What it will not do」から 1 リンク、`CLAUDE.md` セキュリティ方針節は要約 + リンクに縮む
  - ルートに `SECURITY.md`（報告経路 = GitHub private vulnerability reporting + メール alias。本文は NOTICE の takedown 節へのリンクのみ）、両 repo のリンクが通り GitHub Security policy 表示が有効（D-P1-10-2 の後）
  - 7 本のテストが CI 緑: hooks の block/allow fixture、週次セッションの allow 縮小 + deny（`.env*` 等。deny 案なら 8 種）、embeddings の 3xx 非追従、peer spawn の `env` 引数 allowlist、report title defang、untracked settings の preflight abort（.13）、shell egress allowlist（.14）。shell 条件（.13）は macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録）。.5 の deny テストは 2 セルとも走る
  - `docs/runbooks/credential-rotation.md` が鍵の置き場所 7 箇所（私的 backup repo の履歴を含む）を列挙し、Moltbook 再発行の可否は P1-07.19 の台帳行を引く
  - P1-08.17 の allowlist テストが列挙する全 transport call（`self._session.request` を含む）に `allow_redirects=False` がある（`grep -rn "requests\.\(get\|post\)" src/` は補助。正本はテスト定数）

##### P1-10.1 生きた threat model を英語の正本 1 枚にする
- 何を: `docs/security/threat-model.md`（+ `.ja.md`）を新設する。資産 / 信頼境界 / 脅威は (a) I/O 面を広げるコード変更 (b) Claude Code セッション自身の untrusted 読み の 2 つ / I/O 面の表（P1-08 SA-01 の allowlist と同一内容）/ 受容済み残余（API エラー本文最大 500 字が WARNING 経由で `*.log` に単行で残る、研究ツール Jev/TypeSafe への第三者本文 egress は人間起動・鍵は人間・出力は `.notes/` のみ、土曜の対話セッションが comment-report の Context を読む根拠 = 人間同席・URL defang・生 JSON でない）/ 鍵の所在（.9 へのリンク）/ review-when。2026-04-01 の 2 本は冒頭に historical と記す。受容済み残余に 3 行を足す: (a) 週次セッションの出力（report / findings / `tasks-*/T-*.md`）は untrusted 由来の二次テキストで、chain の構造ゲートは名前と `state:` のみ（`weekly-pipeline.sh:543-557`）、それを土曜の全ツールセッション（weekly-gate / triage）が読む (b) 公開 body repo 内の固定 fixture / evidence の `post` 文字列（`docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json` 12 件、`evals/datasets/comment_golden.jsonl` 12 行、`tests/fixtures/sampling/comment_suite.jsonl` 4 行）の出所を manifest に書く（合成なら `source: synthetic` で残余から外れる）(c) `tests/fixtures/benchmark/real_sample.jsonl`（本番 episode 50 行）の除去と履歴に残る旨（P0-03.11）。I/O 面の表は P1-08.17 のテスト定数（正本）から生成する。
- 根拠: `CLAUDE.md:91-100`（脅威の定義、日本語のみ）; `docs/security/` は `2026-04-01-*.md` 2 本のみで `git log` は 2026-08-16 の一括 touch 1 件; `adapters/moltbook/client.py:575-576`（`strip_to_printable(response.text, 500)`、コメント「injection carrier」）; `evals/jev_arm.py:20-40`; `contemplative-agent-data/DATACARD.md:87` Collection method に研究 egress の記述なし
- 完了条件: ファイル 2 本が存在し、`README.md` 「What it will not do」節からリンク、`CLAUDE.md` の該当節が要約 + リンク、DATACARD に「研究ツールの egress」1 節、I/O 面の表が P1-08.17 のテスト定数から生成・照合される（表を正本にしない）、残余表に (a)(b)(c) の 3 行
- 規模・整合: M / neutral   出典: SA-29 DC-32 SA-05 SA-18 SA-23

##### P1-10.2 ADR-0007 本文の退役・不在記述を inline 注記で現状に合わせる
- 何を: ADR-0007 に Amendment と同じ方式で注記を入れる — §1 第 2 項は撤回済み、§3「Docker: network isolation」は ADR-0070 で退役、§4「`VALID_MODEL_PATTERN`」は実装に存在しない（検証しない理由: localhost への JSON 値で境界ではない。実装側に寄せない）、§5 `_mask_key()` は末尾 4 文字。`.ja.md` 同期。
- 根拠: `docs/adr/0007-security-boundary-model.md:33,38,44`; `grep -rn VALID_MODEL_PATTERN src/ scripts/ tests/` 0 件、`core/llm/__init__.py:253-254` は env をそのまま返す; `CHANGELOG.md:245`（ADR-0070 で Docker 削除）; `adapters/moltbook/auth.py:19-23` vs `docs/security/2026-04-01-security-scan.md:50`「first/last 2 chars」
- 完了条件: `scripts/docs_consistency_scan.py` の intake で ADR-0007 の退役参照 0 件、`README.md:155` のリンク先本文に存在しない機構名が無い
- 規模・整合: S / neutral   出典: SA-35 AR-21

##### P1-10.3 `SECURITY.md`（報告窓口）を置き、data repo の削除依頼窓口と 1 本にする
- 何を: 本体ルートに `SECURITY.md`（対象版 = 最新 tag、報告経路 = GitHub private vulnerability reporting + メール alias（GitHub アカウント不要。PVR は脆弱性報告の UI で、Moltbook の相手運用者や HF / Zenodo 経由の読者には届かない）、範囲 = 本体 + data repo の takedown、非対象 = Moltbook 側と凍結兄弟）を置く。連絡先と対応期限（受理通知 7 日以内・判断 30 日以内）の正本は NOTICE の takedown 節と受付台帳（P3-05.14、11-21）で、`SECURITY.md` はその節へ後からリンクするだけ。data repo は `NOTICE` から参照。GitHub 側で private reporting を有効化（オーナー作業、この環境から未確認）。受け付けない旨を書くなら `CONTRIBUTING.md` 1 段落（帰属表示と同じ PR → P1-13）。D-P1-10-2 A の実装（決定前は着手しない）。
- 根拠: `find /home/claude/shimo4228 -maxdepth 2 -iname SECURITY.md` 0 件（本体・data・兄弟すべて）; `.github/workflows/verify.yml:4-5,55`（bandit / pip-audit / gitleaks は有効 = 検出面だけあって受け口が無い）; `contemplative-agent-data/NOTICE` は存在
- 完了条件: NOTICE の takedown 節へのリンクが両 repo から通る + GitHub の Security policy 表示が有効（オーナー確認 1 行を PR に残す）。`SECURITY.md` に連絡先・期限の本文を持たない（NOTICE と二重に書かない）
- 規模・整合: S / neutral   出典: SA-30 GO-29 RD-34   依存: D-P1-10-2、P3-05.14（正本の節と受付台帳、11-21）

##### P1-10.4 同梱 Claude Code hooks を ADR-0107 の境界に同期し、fixture テストで固定する
- 何を: `integrations/claude-code/hooks/*.sh` を「`logs/episodes/` 配下（`.bak` 等含む）+ `agent-launchd.log*` を遮断、`logs/` 直下の自己書き込み JSONL は通す」に書き直し、`integrations/README.md` の「What gets blocked」表と `install-hooks.sh:5` の参照先（→ .1 の threat-model.md）を更新する。`tests/` に bash fixture テスト（block 3 件: `logs/episodes/2026-10-02.jsonl` / `.pre-cleanup.bak` / `agent-launchd.log`、allow 3 件: `logs/weekly-pipeline-audit.jsonl` / `audit.jsonl` / `skill-selection-*.jsonl`）。正本の置き場は D-P1-10-1。`integrations/README.md` / `install-hooks.sh` に「無人週次セッションは `--setting-sources project` で user hooks を落とすので hooks は効かず、境界は deny list（C-SCOPE-6、.5）」の 1 行を足し、D-P1-10-1 = A のとき `install-hooks.sh` が harness の `_episode-log-common.sh` と同じ `~/.claude/hooks/` に別名で並ぶ二重化を撤去する手順を同項目に置く。同じ PR で `CLAUDE.md:98` の `agent-launchd.log*` 例外行に「初回 rotate 日 + 8 世代 = 退役予定日」を日付で書き（初回 rotate 日はオーナーが手元の世代ファイルで確かめる）、その日にオーナーが例外と harness hook の規則を外す。
- 根拠: `hooks/block-episode-logs-read.sh:13-14`（`"$MOLTBOOK_LOGS"/*.jsonl` — bash の case で `*` が `/` を跨ぐため `logs/**` の全 JSONL を遮断、`agent-launchd.log` は素通し）; `block-episode-logs-bash.sh:15,18`; `integrations/README.md:5`; `CLAUDE.md:98`（機械強制は `~/.claude/hooks/_episode-log-common.sh`、repo 外）; `grep -rln block-episode-logs tests/` 0 件; `.claude/settings*.json` は repo に無い（`.gitignore` の `.claude/*`）/ `scripts/backup-runtime.sh:30-55`（週次 rotate、8 世代）、`scripts/rotate-log.sh:1-40`（日付を記録しない）、`CLAUDE.md:98`「ローテーションで置き換わるまで除外を維持する」（人の記憶頼み）
- 完了条件: fixture テスト 6 件が CI で通り、同梱 hook の遮断集合 = `CLAUDE.md:98` の禁止集合、`integrations/` の最終 commit が 2026-08-29（`4788a02`）より新しい、README に hooks が無人セッションに効かない旨の 1 行、`CLAUDE.md:98` の例外行に退役予定日（日付）
- 規模・整合: M / repair   出典: SA-24 DC-31 WO-17 CU-21 SA-38（退役予定日の 1 句、R4-CUT Prune）

##### P1-10.5 週次無人セッションの Read 許可を allow の縮小 + deny で閉じる（`.env*` / `.notes/` / `.venv/` / `.claude/settings*` / `.claude/worktrees/` / `.deepeval/` / `evals/results/` / `tests/fixtures/benchmark/`）
- 何を: 主案: `scripts/weekly-pipeline.sh:359` の allow `Read(/$PROJECT_ROOT/**)` を `{src,docs,rfcs,config,scripts,.claude/skills,tests}` に狭め、deny は allow 内に残る名前（`Read(/$PROJECT_ROOT/.env*)`、`tests/fixtures/benchmark/**`）だけにする — deny は「書いた名前しか守らない」（P0-03.3 と同じ論理）。allow を広げたまま残す場合は deny に `.env*` / `.notes/**` / `.venv/**` / `.claude/settings*.json` / `.claude/worktrees/**`（worktree は main checkout の `.claude/worktrees/<name>` に住み、他ブランチの未 commit の作業木を丸ごと読める）/ `.deepeval/**` / `evals/results/**` / `tests/fixtures/benchmark/**` の 8 つ（主案なら `.claude/worktrees/` は allow の外で自動的に外れ、追加は不要）。`tests/test_weekly_pipeline_session_scope_shell.py` の `test_c_scope_6_read_scopes_survive_in_the_deny_list` に assert を追加し、allow 側が存在する限り deny が必須である旨をテスト名に書く（P1-08 の束依存がこの 1 行を引く）。
- 根拠: `scripts/weekly-pipeline.sh:359`（`Read(/$PROJECT_ROOT/**)`）と `:360`（deny は `credentials.json` / `skills/.archive` / `logs/episodes` / `agent-launchd.log*` のみ）; 同 `:320-327` が脅威を自認; `:118-121`「A name the CLI does not recognise in --tools is discarded in SILENCE」; `tests/test_weekly_pipeline_session_scope_shell.py:303-335,313-317` は 3 種だけを検証; `.env.example:3-5` は `.env` を repo 直下に作る手順; RFC-0046 L221（`.notes/` に他エージェント本文入り label set）; `.gitignore` の `.deepeval/`（「its keystore stores API keys in plaintext」）と `evals/results/`; `tests/fixtures/benchmark/real_sample.jsonl`（P0-03.11）
- 完了条件: 同テストが allow の縮小（または deny 8 種）を assert して通り、`weekly-pipeline.sh` から 1 つ消すと赤（`test_c_scope_6_…` は text-level の検査で platform 限定の skip が無く、P1-08.1 の 2 セルとも走る）
- 規模・整合: S / repair   出典: SA-07 SA-37 R3-HRN Fix-03   順序: 同 PR（.15 の probe）、10-24 の週（§4.0 の先行列）。`weekly-pipeline.sh` は P2-04.13 PR-A より前に入ってよい（PR-A は挙動不変の移動で、後から rebase する）

##### P1-10.6 `embeddings.py` の Ollama POST に `allow_redirects=False` を付ける
- 何を: `core/embeddings.py:178` に `allow_redirects=False` を足し、3xx を返す mock で follow しないテストを `tests/test_embeddings*.py` に 1 件置く（既存の redirect テストは `tests/test_client.py` / `tests/test_serving_environment.py` にあり、同型で書く）。これで外向き HTTP の全呼び出し面が同じ規律になり、P1-08 の allowlist テストが「属性の不在」を機械で見られる。
- 根拠: `src/contemplative_agent/core/embeddings.py:178` `requests.post(url, json=payload, timeout=EMBEDDING_TIMEOUT_SECONDS)`; 同じ Ollama 向けの `core/llm/__init__.py:435,959`、`core/llm/decision.py:433-437,499`、`adapters/moltbook/client.py:494` は全て `allow_redirects=False`; ADR-0007 §3（:31）
- 完了条件: P1-08.17 の allowlist テストが列挙する全 transport call（`self._session.request(`、`client.py:488` を含む）に `allow_redirects=False` がある（`grep -rn "requests\.\(get\|post\)(" src/` は補助）+ 3xx テスト 1 件
- 規模・整合: S / repair   出典: SA-02 AR-22

##### P1-10.7 dialogue の peer サブプロセスへ渡す env を allowlist に絞る
- 何を: `cli/session_cmds.py:383` の `{**os.environ, ...}` を `PATH` `HOME` `MOLTBOOK_HOME` `OLLAMA_*` `CONTEMPLATIVE_*` の allowlist にし、`subprocess.Popen` に渡す `env` 引数（`session_cmds.py:383-388`）に `MOLTBOOK_API_KEY` と `*_API_KEY` が無いことをテストで固定する（peer は Moltbook client を初期化しないので鍵は不要）。assert は spawn 時の `env` 引数に対して行う — cloud peer は自分で `cloud.env` を読み `ANTHROPIC_API_KEY` を env に入れるので、peer 側 `os.environ` の検査は偽陽性。
- 根拠: `src/contemplative_agent/cli/session_cmds.py:383` `env = {**os.environ, "MOLTBOOK_HOME": str(home)}`; ADR-0015:38（dialogue では Moltbook client を初期化しない）; `CONTEMPLATIVE_DIALOGUE_PEER_MODULE`（同 `:362-367`）で cloud peer に差し替えると `ANTHROPIC_API_KEY` 等も継承
- 完了条件: テスト 1 件（`Popen` の `env` 引数に `_API_KEY` を含むキーが無い）
- 規模・整合: S / repair   出典: SA-04

##### P1-10.8 comment-report の `Title` / `Submolt` を defang する
- 何を: `core/report.py` で `title` / `submolt` に `defang_urls` を適用する（`Context` の `<untrusted_content_{nonce}>` 枠は消費側 `scripts/weekly-analysis.sh:125-145` が LLM に読ませる時点で付ける設計なので、render 時には付けない — やらないこと候補）。`tests/test_report.py` に 1 件。公開済み report は `generate-report --all` で再生成。
- 根拠: `src/contemplative_agent/core/report.py:209-212`（title / submolt を生のまま出力）、`:213-215`（context は defang のみ — 枠は消費側 `weekly-analysis.sh:125-145,346-351` が付ける）; `docs/security/2026-04-01-episode-log-access-control.md:124` Residual Risk 4 が未解消; `core/config.py:103` `MAX_POST_TITLE_LENGTH = 300`; `.claude/skills/weekly-report/SKILL.md:89-91`
- 完了条件: テスト 1 件 + 再生成済み report に `**Title:** ` 行の生 URL が 0
- 規模・整合: S / repair   出典: SA-20 SA-23

##### P1-10.9 鍵の棚卸しと回転手順を runbook にする（keychain を使わない理由を含む）
- 何を: `docs/runbooks/credential-rotation.md` を新設: (1) 無人 launchd job に keychain unlock が無いので平文 0600 を選ぶ理由 (2) 鍵の全所在 — `$MOLTBOOK_HOME/credentials.json`、`MOLTBOOK_API_KEY` env、`$MOLTBOOK_HOME/cloud.env`（cloud 兄弟）、`~/.config/typesafe/api_key`（Jev）、HF token（`hf upload` の書込 scope、dataset 限定 fine-grained か）、git credential（公開 data repo + 私的 backup repo）、私的 backup repo の履歴（`cloud.env` が存在した期間 — 7 番目。存在したなら回転を手順に） (3) 漏洩時の手順 — Moltbook 側の再発行可否は P1-07.19 の再読台帳の行（日付・digest）を引く（自前で `skill.md` を読む手順は書かない）、不可なら「新規 `register --name` + 旧エージェント停止」と明記し、これは platform 上の識別子と相手関係を分ける一方向の操作なので、実施は人間が `gate_item` で決め、実施日を P3-02.1 の境界表と P4-01 の検討イベントの入力に 1 行書く、と添える。ADR-0007 §5 から追補でリンク。`backup-runtime.sh:134-148` の除外と `:162` の `rm -f` に `cloud.env` / `*.env` を足し（P0-03.2 の共有除外と同じ PR）、`docs/runbooks/runtime-backup-restore.md:22` の鍵一覧にも `cloud.env` を足す。
- 根拠: ADR-0007:44（Moltbook 鍵のみ）; `grep -rni keychain src/ docs/ README.md rfcs/` 0 件; `docs/CONFIGURATION.md:424`「a restore needs this repo plus a re-issued credential」だが再発行手順なし; `adapters/moltbook/auth.py:54-68`（`save_credentials` 0600）、`:85-108`（`register_agent` は新規作成であり回転ではない）; `scripts/sync-research-data.sh:127,141-151`（`git push` / `hf upload`）、`scripts/backup-runtime.sh:188`（私的 repo へ push）、`:134-148,162`（除外と `rm -f` に `cloud.env` が無い）; `evals/jev_arm.py:27-31`
- 完了条件: runbook が存在し 7 所在を列挙、Moltbook 再発行の可否が P1-07.19 の台帳行（日付・digest）を引いて書かれ、新規 `register` が `gate_item` の決定を要する一方向の操作として書かれている、`tests/test_backup_runtime_shell.py` に `cloud.env` 除外の assert 1 件
- 規模・整合: S / neutral   出典: SA-09 SA-33 R4-ONEWAY Fix-09   依存: P1-07.19（台帳の初回行、11-14 の週 = §4.0 の先行列）

##### P1-10.10 鍵の実値が LLM 文脈・出力・ログに現れないことを sentinel で検査する
- 何を: 守りを runtime に足すのではなく、テストで absence を証明する: 1 つの sentinel API key を `load_credentials()` に与えて run/distill の経路を回し、5 面 — 組み立てられた全 prompt・`_sanitize_output` 後の出力・書かれた JSONL・`.log`・`register` / `status` の stdout（capsys）— に実値が現れないことを assert する（LLM は mock）。fixture は P0-05.3 と共有し、P0-05.3 の完了条件はこのテストへの参照にする。失敗したら構造の破れ（ADR-0015「credentials never enter the LLM context」）として扱う。実値置換（`[REDACTED]` 化）の runtime 追加は「やらないこと候補」。
- 根拠: `core/config.py:42-51` `FORBIDDEN_SUBSTRING_PATTERNS` は語彙のみ; `core/llm/guard.py:95-116` `_scrub_secrets` は実値と比較しない; ADR-0015 Context
- 完了条件: 5 面を回すテスト 1 件が CI で通り、P0-05.3 がそれを参照する
- 規模・整合: S / repair   出典: SA-26

##### P1-10.12 公開 `docs/plans/` + `docs/evidence/` + `tests/` を週次ゲートの機微点検範囲に入れる
- 何を: `.claude/skills/weekly-gate/SKILL.md` Step 6d の点検対象を `rfcs/` から `rfcs/` + `docs/plans/` + `docs/evidence/` + `tests/` に広げる（規約 1 行のみ。commit 前の拒否と regex は P0-03.6 の `config/secret-patterns.txt` に一本化し本項目には置かない）。本体の `/Users/` の正規化と grep 0 件は P0-03.5 が持つ。
- 根拠: `git ls-files docs/plans | wc -l` = 77; `weekly-gate/SKILL.md:326-348` の点検は `rfcs/` のみ; `CLAUDE.md:110-112`（WIP は `.notes/`、plan は `docs/` 側）
- 完了条件: SKILL.md Step 6d の点検範囲に 4 つのパスがある（規約 1 行）
- 規模・整合: S / neutral   出典: SA-25

##### P1-10.13 無人週次セッションの有効権限を起動前に機械で固定する（untracked `.claude/settings.json` の preflight と監査行）
- 何を: preflight 段（P2-02.6 と同じ場所）で `.claude/settings.json` の有無と sha256、`permissions.allow` / `hooks` の有無を `weekly-pipeline-audit.jsonl` に 1 行書き、allow 規則か hooks があれば `PREFLIGHT_PROJECT_SETTINGS_WIDEN` で abort する。代案は `--setting-sources ""`（project も落とす）への切り替え: 認証が残ることは evals の判定セッションで実測済みなので、実 CLI で 1 回計測するのは (i) その下で project skill `/weekly-report` が解決されるか (ii) CLAUDE.md が落ちて診断の質が変わるか の 2 点。両方よければ切り替えて依存を消す。解決されない場合の第 2 案: evals と同じく skill 本文（SKILL.md + `references/diagnosis.md`）を stdin の prompt で渡し、`WEEKLY_TOOLS` から `Skill` を外す（入力がバイト列で固定される）。
- 根拠: `.gitignore`「`.claude/*`」（settings は untracked、本環境にも無い）; `scripts/weekly-pipeline.sh:55-59`（`--setting-sources project` は CWD 依存で $HOME からは no-op）、`:358`; `tests/test_weekly_pipeline_session_scope_shell.py:21-22`「`--allowedTools` only ADDS — the settings allow rules are consulted first」「Only DENY rules outrank」、`:51-56`（テストは呼び出し行の契約だけを読む）; script に settings の存在・hash を audit に書く行は無い（`grep -n settings` はコメント 6 行のみ）/ `evals/judging.py:248,299,324`（判定セッションは `--setting-sources ""` + env allowlist で走り、`evals/baselines/comment_golden-*.json` の 5 本を生成 = 認証は残る）
- 完了条件: audit 行 1 種 / settings fixture を置くと abort する shell テスト（harness は P1-08.3。macOS セルで passed、ubuntu では skip — P1-08.2 の期待集合に登録）/ `--setting-sources ""` の下での (i) skill 解決 (ii) 診断の質の計測結果 1 行（`docs/evidence` か script コメント。`claude` CLI 不在のため本環境では未確認）
- 規模・整合: S / instrument   出典: R1-SEC-01 R3-HRN Fix-06   順序: audit 行と abort は着手（11-14 のゲートの後の平日）に入れ、shell テストは P1-08.1 / .3（12-19 着手）の後に足す。`weekly-pipeline.sh` は P2-04.13 PR-A より前に入ってよい（PR-A は挙動不変の移動で、後から rebase する）。preflight 段は P2-02.6 と共有し、.13 が先に入るときは .13 が段を起こして P2-02.6（2027-02-06 着手）がそこに行を足す
- 消費計画: (a) 土曜ゲート Step 0 が PIPELINE-STATUS 経由で毎週読む (b) abort 1 件で「無人セッションの権限が広がった」と判定し原因の settings を消す (c) `--setting-sources ""`（または第 2 案）に切り替えたら preflight ごと撤去

##### P1-10.14 無人シェル経路の外向き verb を不在テストで固定する（`scripts/*.sh` の egress inventory）
- 何を: `tests/test_shell_egress_allowlist.py` を足す — (a) `scripts/*.sh` は `#` 以降を落として `shlex` で token 化し、`config/launchd/*.plist` は `plistlib` の `ProgramArguments` を読む（素の grep はコメント 13 行を verb に数える）(b) `git push|hf |gh |curl|wget|ssh|scp|nc |rsync .*:` 等の verb 出現を (file, verb) の表 — `sync-research-data.sh`: `git push` + `hf upload` / `backup-runtime.sh`: `git push` + `gh repo view` / `weekly-pipeline.sh`: `claude -p` / `com.moltbook.ollama-restart.plist`: その `ProgramArguments` の verb / `ipd-two-arm.sh`: 研究 script（launchd / chain の外、P1-01.4 の凍結集合にも無い）と注記して表に載せる — と照合する (c) 「未知 verb 1 件で赤」はこの表に対して判定する。P2-02.4 の README 列挙はこの集合から生成し、docs-consistency scan で照合する。P3-05.2 の HF 鮮度の読みは `sync-research-data.sh` が `hf` の戻りを 1 行ログに書く形で新 egress は無く、目録の `hf upload` 1 verb は変わらない。保守 script は ADR-0015 の外で、この固定集合がその管理面（P1-11.7 の追補、R2-PLAT-06）。harness は P1-08.3（text-level 検査なので ubuntu でも走る）。
- 根拠: `tests/test_cloud_egress_absence.py:56-63`（`*.sh` を意図的に除外、`claude -p` 2 箇所を名指し）; 現物の verb — `scripts/sync-research-data.sh:127`（`git push --force-with-lease`）、`:150`（`hf upload`）、`scripts/backup-runtime.sh:69`（`gh repo view`）、`:188`（`git push`）、`scripts/weekly-pipeline.sh:352`（`claude -p`）; 無人起動は `config/launchd/com.moltbook.{backup,weekly-pipeline,submolt-scan}.plist`; `tests/test_sync_research_data_shell.py` / `test_backup_runtime_shell.py` は転送内容を見るだけで verb 集合を固定しない
- 完了条件: テストが存在し、(b) の表に対して未知 verb 1 件で赤; P2-02.4 が入った後は README 列挙と集合が一致
- 規模・整合: S / instrument   出典: R1-SEC-02 R2-PLAT-06   順序: P2-04.13 PR-A の前後を問わない（PR-A は verb 集合を変えない）。様式は P1-08.17、harness は P1-08.3 だが、どちらも 12-19 着手なので現行の形で書き、入ったら載せ替える   注: P2-02.4 の README 列挙はこの集合から生成する（→ 参照元）
- 消費計画: (a) CI と release gate が毎回読む (b) 赤 1 件で「I/O 面が増えた」と判定し inventory の更新か差し戻し（R2-PLAT-06） (c) `scripts/*.sh` が凍結集合（P1-01.4）に入り 8 週変更 0 なら release gate のみに縮める

##### P1-10.15 週次セッションの bare `Glob,Grep` allow が Read の正 scope を迂回しないことを実 CLI で 1 回確かめ、C-SCOPE-9 に固定する
- 何を: オーナーの Mac で 1 回、本番と同じ flag 集合・同じ cwd で「allow 根の外に置いた sentinel ファイル（tmp の 1 行）を Grep / Glob させる」probe を走らせ、結果を `tests/test_weekly_pipeline_session_scope_shell.py` に C-SCOPE-9（`claude` 不在で skip、C-SCOPE-8 と同型）として固定する。外まで届いたら `Glob,Grep` の bare allow を外して Read の正 scope に従わせ（CLI が `Grep(path)` を受けなければ `--add-dir` と deny で囲う）、`weekly-pipeline.sh:320-327` のコメントを実測に合わせる。
- 根拠: `scripts/weekly-pipeline.sh:359`（`--allowedTools "Glob,Grep,Read(/$PROJECT_ROOT/**),…"` — Glob / Grep は path 指定なしの bare allow）/ 同 `:320-327`（Read は 2026-08-24 security review HIGH を受けて正に scope した、の設計意図）/ `:301`「Read denies cover Grep too (verified 2026-08-15)」— 確かめたのは deny 側だけ / `tests/test_weekly_pipeline_session_scope_shell.py` の C-SCOPE-0〜8 に Glob / Grep の到達範囲を問う項目は無い / .5 は Read の allow を縮めるが Glob / Grep には触れない（Confidence low: bare allow の到達範囲は CLI の権限評価の仕様で、本環境では確認できない推定 — だから probe が先）
- 完了条件: probe の結果 1 行（日付・CLI 版）が script コメントか `docs/evidence/` にあり、C-SCOPE-9 がオーナーの手元で passed。既存テストは不変（C-SCOPE-9 は追加）
- 規模・整合: S / repair   出典: R3-HRN-03   順序: 同 PR（.5）、10-24 の週（§4.0 の先行列）。`weekly-pipeline.sh` は P2-04.13 PR-A より前に入ってよい（PR-A は挙動不変の移動で、後から rebase する）


**依存**
- P1-08.17（SA-01 の I/O allowlist テスト — .1 の表はその定数から生成。正本はテスト定数）、P1-08.1 / P1-08.3（.13 の shell テストの macOS セルと harness `tests/_shell_harness.py`。12-19 着手なので、それより前に入る .13 / .14 は現行の形で書き、入ったら載せ替える）、P0-03.6（.12 の regex 正本 `config/secret-patterns.txt`）、P0-03.11（.1 残余 (c)、.5 の deny）、P0-03.2（.9 の `*.env` 共有除外）、P1-11（D-P1-11-4 推論 egress の ADR-0015 分類 — .1 の外部面表。P1-11.7 の追補が保守 script を ADR-0015 の外と書く）、P1-07.19（平台の再読台帳 — .9 (3) はその行を引く）、P3-05.14（NOTICE の takedown 節と受付台帳、11-21 — .3 は後からリンクするだけ、SA-17 と同一窓口）、P0-03（公開データの開示境界）、P1-09（DC-11 言語方針 — .1 の英語正本）
- → 参照元: P2-02.4（.14 の集合から README 列挙を生成）、P2-02.6（.13 と preflight 段を共有）、P2-04.13 PR-A（`weekly-pipeline.sh` — .5 / .13 / .15 は PR-A より前に入ってよく、PR-A が rebase する）、P0-05.3（.10 の fixture を共有し完了条件が .10 を参照）、P0-05（SA-06 `register` / `status` が api_key を stdout に出す — .9 の「鍵の所在」と同じ経路）、P1-13.5（CONTRIBUTING.md と帰属表示、community profile — .3）、P2-03（harness の PreToolUse 秘密スキャン — .12 と同じ点検範囲を読む）、P1-08.17（.6 の修理の後か同 PR で allowlist テストを入れる）、P3-02.1・P4-01（.9 (3) の新規 `register` の実施日）、P1-11.7（ADR-0015 追補が .14 の固定集合を保守 script の管理面として名指す — R2-PLAT-06）、P2-02.9（週次の `claude -p` の環境固定は .14 の verb 表を前提にする）、P4-02.6（wind-down の鍵・資格情報の失効表。.9 の runbook からのリンクは P4-02.6 の PR で張る）、P2-04.23（machine-rebuild runbook の credentials 段が .9 を引く）
- 外部: harness repo（`_episode-log-common.sh`、D-P1-10-1）、GitHub private vulnerability reporting の有効化とメール alias の用意（オーナー）、`agent-launchd.log` の rotate 8 世代の経過（.4 の退役予定日）


#### P1-11 兄弟 repo の処遇（cloud / mlx / otel / rules）
- 狙い: 北極星（ADR-0080）は兄弟を到達点に数えていない — layer 5 の器として名指すのは data repo だけ（ADR-0080:288）。cloud / mlx / otel は 2026-08-16/17 で止まり、本体は ADR-0112/0113（DecisionBackend、score4 enforce 2026-10-07）で先へ進んだ。機構層を凍結する前に、3 兄弟を「維持 / 凍結 / 削除」として機械的に表現し（README 状態行・release gate の状態列・skill の警告）、本体 release gate が「落ちて当然」文書のまま黙って通る面を無くす。rules repo は値層ゲート（ADR-0090 の IPD bench）の依存先なので、較正契約の書き戻しと tag は処遇に関係なく要り、処遇そのもの（維持 + 消費契約 / vendoring）は D-P1-11-6 で決める（R1-SIB-01）。
- 期限・順序: 着手 12-26 の土曜ゲート（§4.0）。期限 2027-01。D-P1-11-1（cloud）は 10-31 の土曜ゲート、D-P1-11-2（mlx）と D-P1-11-5（kit）は 11-14 の土曜ゲート（この順。v2.13.0 の release notes の兄弟行に cloud / mlx の状態が先に入る。tag は 11-14 の決定の後、11-20 までの平日）、D-P1-11-4（egress）は 12-05（同じ回の順は D-P1-11-4 → D-P1-15-2 → D-P1-15-1）、D-P1-11-3 / -6（otel / rules）は 12-26（§4.0 のゲート再配分）。決定を待たない先行分（いずれも §4.0 の先行列）: rules の較正契約と tag（.10）は 10-24 の週（憲法 due 10-31 の前）、文書修理（.2 .3）と gate 出力（.13。v2.13.0 の release gate（P0-06、tag は 11-14 の決定の後の平日 11-16〜20）が兄弟行を release notes に写す前）は 11-07 の週、兄弟注入の明文化（.5）は 11-14 の週、rules の文書修理と ADR-0005 の終了条件（.11 .12）は 11-21 の週。契約テスト・otel 追従・cloud 衛生（.4 .6 .7）は「維持」を選んだ repo だけ、.14 / .15 は凍結を選んだ時の凍結 commit に含める。.1 の README 状態行・`TARGETS` の状態列・`CLAUDE.md` 関連リポジトリ節は 12-26 の決定の後、P1-09.2 と同 PR で 2027-01-09 の週（§4.0 の先行列）。ADR-0015 追補（.1。D-P1-11-4 の分類 + 適用単位の段落、R2-PLAT-06）は 12-05 と同じ PR。ADR-0078 の note は .1 の otel 状態行と .14 の正本移動を 1 本にし、D-P1-11-3（12-26）の後の同じ PR で書く。`cli/runtime.py` の順序は P0-02.2 → P0-05 → P1-11.5 → P1-07.13（同一ファイル。`:243-253` を触る .5 は P1-07.13 より前）、.6 の `_census_registry.py` enum 同期は Entry 1 行の差分で順序不問。棚卸し表 (2) の `weekly-gate/SKILL.md:212,217` は決定（12-26）後の 1 PR で触り、10-17 / 10-24 / 10-31 の同梱 PR には乗せない（Step の所有者は変えない）。
- 束の完了条件:
  - 4 兄弟の README 冒頭に状態行（`Active` / `Frozen as of contemplative-agent vX.Y.Z, DATE` / rules は維持 + 消費契約）があり、ADR 追補（0070 / 0067 / 0078 / 0090 のいずれか）に日付つき決定が残る。凍結 commit = tag = README 状態行 = 本体の pin 先（.1）
  - `./scripts/check-sibling-backends.sh` が状態列（active / frozen / absent）と `sha= / main= / level= / kit=` を出して v2.13.0 gate で exit 0、release notes に兄弟 1 行ずつ（.13 の出力を写す）
  - cloud: `grep -rn Qwen` が `evidence/` 以外で 0; mlx: README / llms.txt の「本番モデル」記述が gemma を指し `grep -c Qwen README.md` ≤ 2; 両 README の依存 pin が `pyproject.toml` と一致し install 順は main → sibling
  - rules: `v0.2.0` tag が存在、`benchmarks/prisoners-dilemma/tests/test_prompts_in_sync.py` が通り、README が較正契約（gemma4:e4b / n=10 / ±0.13 + bench 側のフィールド）と「稼働インスタンスの憲法は改正済み」と本体からの消費契約（D-P1-11-6）を書いている
  - otel: 維持なら正本 fixture の契約テストが未知キーで落ちる、凍結なら README に Frozen 行（decision / embed 行は `text_completion` のまま、と明記）と本体 `docs/otel-semconv-mapping.md` が 3 ログ全面の正本（.14）
  - 本体側の兄弟参照（.1 の棚卸し表 (2)）が決定後に同じ状態語を言い、`docs_consistency_scan.py` の「兄弟名が出る面 ⊆ 一覧面」検査が findings 0

##### P1-11.1 処遇決定を記録し、凍結 / 維持を機械で表現する（状態行・tag 方針・本体側参照の棚卸し表）
- 何を: D-P1-11-1/2/3/6 の結果を ADR 追補（cloud → ADR-0070 か 0088、mlx → ADR-0067、otel → ADR-0078（.14 の正本移動と同じ 1 本の dated note、D-P1-11-3 の後の同じ PR）、rules → 本体 ADR-0090 に dated note を書き、rules repo に新 ADR-0006「本体からの消費契約」（ja 併記、rules repo の慣例どおり）を起票）に日付つきで書き、4 兄弟の README 冒頭に状態行（`Active` / `Frozen as of contemplative-agent vX.Y.Z (kit static PASS DATE)` — P4-02.5 の `last conformant:` 行はこれと同じ行、rules は「本体 ADR-0090 の較正依存先として維持」）を置く。tag 方針を 1 行で固定: 「凍結 commit = tag = README 状態行 = 本体の pin 先（P0-06.2 A の `[tool.uv.sources]`、rules は `v0.2.0` = .10、P3-06.3 の SWH / `.zenodo.json` はこの tag を参照）」。`CLAUDE.md` 関連リポジトリ節（P1-09.2 と同じ 4 行、1 PR）と `docs/CONFIGURATION.md:500` を一致させ、`scripts/check-sibling-backends.sh` の `TARGETS` に状態列を持たせ（frozen は検査結果を報告するが release blocker にしない、absent と区別）、`.claude/skills/agent-run/SKILL.md` は frozen backend の起動時に 1 行警告。CI は置かず、frozen 宣言には「依存は実行前に `pip-audit` せよ」を添える。本体側の兄弟参照は下の棚卸し表（R1-SIB-02）で 3 分類し、`docs_consistency_scan.py` に「兄弟名が出る面 ⊆ 一覧面」の 1 検査を足す。D-P1-11-4 の実施もここで持つ（cloud の処遇に依らない。凍結でも追補は要る）: 結果を ADR-0015 追補に書き、同じ追補に適用単位の段落を日付つきで置く — 「本 ADR の単位は LLM を持ち相手の文を読む agent process。LLM を持たない保守 script（sync / backup）は本 ADR の外で、外向き verb は `tests/test_shell_egress_allowlist.py`（P1-10.14）の固定集合で管理する。script が LLM を持つ場合（weekly の `claude -p`）は D-P1-11-4 の分類に従う」（`sync-research-data.sh:127`（`git push`）と `:150`（`hf upload`）は同じ 1 プロセスで 2 つの外部書込面を持ち、文字どおり当てると現状違反、当てないと P1-10.14 の消費計画 (b) の根拠が無い）。`CLAUDE.md:93` に同じ 1 文を置き、`docs_consistency_scan.py` で ADR-0015 ↔ CLAUDE.md の文の一致を検査する。
- 根拠: `scripts/check-sibling-backends.sh:31-35`（固定 3 件、`:44-48` absent は非失敗）; `docs/runbooks/sibling-backend-conformance.md:37-39`; `.claude/skills/agent-run/SKILL.md:93-95`（存在検査のみ）; 4 repo とも `.github/` 無し、remote tag 0（`git ls-remote --tags`）; `CLAUDE.md:166-167`; 参照面の実測（`grep -rIc "contemplative-agent-(cloud|mlx|otel)|contemplative_agent_(cloud|mlx)"`、2026-10-10）は本体 20 面超 + data repo 3 面（`README.md:50` / `README.ja.md:50` が rules を「知識から蒸留された行動ルール」と誤記、`llms.txt:135-139` は rules + cloud のみ）、HF card 2 枚に兄弟 link 0 件（`EcosystemRepo` ノード `graph.jsonld:1714,1730,1741,1752` だけが mirror に乗る）; rules repo の `docs/adr/` は 0001〜0005（各 en / ja）だけで 0006 は無い（新設になる）; ADR-0015:19「An agent process owns at most one adapter …」、`:21`（副作用の定義に file writes outside `MOLTBOOK_HOME` を含む、推論 egress は数えていない）、`CLAUDE.md:93`「1 プロセスにつき最大 1 つ」、`scripts/sync-research-data.sh:127,150`
- 完了条件: 決定後に script の出力と skill の両方がその状態を表示し、`grep -rn "Frozen\|Active\|calibration dependency" <sibling>/README.md` が各 1 行; 棚卸し表 (2) の全面が同じ状態語を言い、data repo の rules 説明が「四公理の配布物（Appendix C verbatim）」になり、HF の graph mirror（P1-09.7 の経路）が `status` / `dateModified` 付き `EcosystemRepo` ノードを含む; scan の新検査が findings 0; rules repo に ADR-0006（en / ja）が存在し本体 ADR-0090 の dated note から link; ADR-0078 の note が 1 本（otel の状態と正本の所在を同じ note で）; ADR-0015 追補（D-P1-11-4 の分類と適用単位の段落）+ `CLAUDE.md:93` の 1 文があり、`docs_consistency_scan.py` で ADR-0015 ↔ CLAUDE.md の文が一致
- 規模・整合: S / repair   出典: SB-26 SB-27 SB-28 SB-38 SA-28 SB-07 DE-38（README 行）SA-19（ADR-0015 追補）R2-PLAT-06 R3-ADR Fix-04 / Fix-05 / Merge-09   依存: P1-10.14（固定集合）、D-P1-11-1/2/3/4/6   順序: P1-09.2 と同 PR（2027-01-09 の週）   注: `graph.jsonld` の `EcosystemRepo` ノードは現行の形で書き、HF mirror への反映は P1-09.7（P1-09 着手 2027-01-23）が入ったら更新。data repo の兄弟記述は P1-09.11 と同じ PR

参照棚卸し表（R1-SIB-02。上の `grep` の全件を 3 分類。決定前に表を置き、決定後に (2) を 1 PR で揃える）:

| 分類 | 面 | 扱い |
|---|---|---|
| (1) 残す = 歴史 | ADR 12 本 + RFC 1 本の歴史記述、ADR-0088:333-335、CHANGELOG、`testing/{backend_contract,decision_contract,__main__}.py` の docstring（cautionary tale） | 触らない |
| (2) 書き換える = 一覧と状態 | `CLAUDE.md`（3 箇所）、`README.md:164` / `README.ja.md:164`、`llms.txt:187`（cloud のみ）/ `llms-full.txt:154-158,268`、`docs/CONFIGURATION.md:500`、`docs/otel-semconv-mapping.md:77-80`、`graph.jsonld:1714,1730,1741,1752`（`EcosystemRepo` ノードに `status` + `dateModified`）、`.claude/skills/weekly-gate/SKILL.md:212,217`（削除 defer 規則が sibling 消費を前提）、runbook / script / `agent-run` skill、data repo `README.md:50` / `README.ja.md:50` / `llms.txt:135-139`（誤記と mlx / otel の欠落） | 決定後に同じ状態語で 1 PR（HF へは P1-09.7 の経路、data repo は P1-09.11 と同じ PR） |
| (3) 決める | `CONTEMPLATIVE_DIALOGUE_PEER_MODULE` seam（`cli/session_cmds.py:362-364`、`core/llm/backend.py:146`、`cli/runtime.py:181-183`）、`tests/test_cloud_egress_absence.py:14-15` / `tests/test_backend_contract.py:129,159` の文言、`docs/otel-semconv-mapping.md` の正本（.14） | D-P1-11-1 C / D-P1-11-3 の結論で |

##### P1-11.2 兄弟 README / llms.txt / skill の実測との食い違いを直す（処遇と無関係に必要）
- 何を: (a) cloud / mlx の「Qwen3.5 9B」を「gemma4:e4b（ADR-0069、2026-06-28〜）」に、mlx の比較文に「測定 2026-06、対照 Qwen3.5-9B（Ollama）、本番は gemma、MLX 実行は生成モデルを替える」を並記 (b) README の `>=2.0` を pyproject の pin（cloud `>=2.7.0`、mlx `>=2.10.0`）と理由（kit を持つ版）に揃える (c) PyPI は未公開（2026-10-10 に `contemplative-agent` / `-cloud` / `-mlx` / `-otel` / `contemplative-ipd` の 5 名とも 404 を確認）: 両 README は source install のみにし、install 順は main → sibling を同じ venv に（P0-06.2 A の `[tool.uv.sources]` pin が入るまで。正しい順は `agent-run/SKILL.md:94-95`）(d) 各 README に "Verified against contemplative-agent vX (kit level static) on DATE" 1 行、runbook に「PASS したら兄弟に commit」を追加 (e) cloud の既定 `gpt-5` / `claude-opus-4-7` は未検証なので検証済み（`gpt-4o` / `claude-sonnet-4-6`）に戻すか検証日を書く — skill の既定も同期 (f) cloud README に「thinking trace は取れない」、ADR-0069:280-282 に「2026-08-04 不採用、`trace_absent` で記録」の注 (g) otel `llms.txt:9` の time-gap 記述を README:90-95 と揃え、Jaeger / otel-desktop-viewer / sdk の検証版と日付を 1 行 (h) `agent-run` skill の mlx 前提検査を `run-with-mlx.sh` の uvx フォールバックと一致させる (i) 両 README の Protocol 抜粋パス `# contemplative_agent/core/llm.py` を現行 `core/llm/backend.py:141`（ADR-0079 で package 化）に直し、任意 Protocol `TokenCountingBackend`（ADR-0087）の注を足す。
- 根拠: cloud `README.md:14,30,69-73,76,137-140,152`、`llms.txt:11,16`、`src/contemplative_agent_cloud/__init__.py:9`、`pyproject.toml:3,26`、`backends/openai.py:31,132`、`backends/anthropic.py:32,109-112`; mlx `README.md:7-8,90-96,99,178`、`cli.py:14,37`、`scripts/run-with-mlx.sh:24,91-97`、`scripts/serve-mlx.sh:16`、`backends/mlx.py:4,62`、`pyproject.toml:50-55`（mlx の Qwen は evidence 外で 8 ファイル 23 箇所、うち 5 箇所がコード既定）; PyPI 5 名 404（2026-10-10）; 本体 `core/llm/backend.py:27`、`.claude/skills/agent-run/SKILL.md:31,95`、ADR-0112:205-207; otel `llms.txt:9` vs `README.md:90-95`、`README.md:49-63`
- 完了条件: cloud は `grep -rn Qwen` が `evidence/` 以外で 0; mlx は README / llms.txt の「本番モデル」記述が gemma を指し、`MLX_MODEL` 既定が Qwen である理由を README 1 行が言う（`grep -c Qwen README.md` ≤ 2）; `grep -n time-gap llms.txt` が otel で 0、README pin == pyproject pin、install 順が main → sibling、Protocol 抜粋パスが `core/llm/backend.py:141`、各 README に Verified 行（.13 の gate 出力を写す）、skill と script の mlx 条件が一致
- 規模・整合: S / repair   出典: SB-03 SB-13 SB-14 SB-15 SB-16 SB-19 SB-24 SB-08 SB-11 SB-17   順序: 11-07 の週（§4.0 の先行列）

##### P1-11.3 本体側の「cloud は落ちて当然」を消し、2026-08-04 の解決を ADR に残す
- 何を: `docs/runbooks/sibling-backend-conformance.md:53-58`「`contemplative-agent-cloud` fails — expected as of 2026-08-02」の段落を削除し（release runbook の古い段落の修正は本項目が持つ。`a0cdcbc` 2026-09-12 = v2.12.0 当日に 3 backend 静的 PASS しており「v2.11 以降は未検証」ではない。CHANGELOG の結果行は P0-06.6 の段 2 が .13 の gate 行から写す）、ADR-0088 に「`T-CLOUD-SIBLING-STALE` は 2026-08-04 に minimal repair（未マージ branch `1a7d3d0` の merge）で解決、2026-09-12 に 3 backend 静的 PASS（`a0cdcbc`）」の追補 3 行、`tests/test_backend_contract.py:129,159` の docstring を "a hypothetical pre-2026-05 shape" に直す。実行ログは `docs/evidence/` に 1 本（AR-23 の「実行して確かめる」半分は `a0cdcbc` で済み、文書だけ残っている）。
- 根拠: `docs/runbooks/sibling-backend-conformance.md:54-58`; ADR-0088 en:293（未決扱いのまま）; `docs/plans/jazzy-swinging-thunder.md:5,38`（解決の記録が計画メモにしか無い）; cloud `backends/anthropic.py:73-78,93-102`（現行シグネチャ）; 本体 commit `a0cdcbc` 2026-09-12
- 完了条件: `grep -rn T-CLOUD-SIBLING-STALE docs/runbooks/` が 0 件、`grep -c '2026-08-02' docs/runbooks/sibling-backend-conformance.md` = 0、ADR-0088 に dated note 1 本（en:293 の原文は残す）
- 規模・整合: S / repair   出典: SB-18 AR-23 RD-29 CH-32（runbook 部分）   順序: 11-07 の週（§4.0 の先行列）

##### P1-11.4 維持する兄弟に契約キットを import させ、release gate で自前 pytest も回す
- 何を: 維持と決めた repo に `tests/test_conformance.py`（`check_backend(<Backend>(...), require="static")` の `ok` を assert）を置き、`_circuit` 直触りを `circuit_reading()` に書き換える（本体の `[tool.ruff]` / pyright 設定の複製はしない — やらないこと候補）。`check-sibling-backends.sh --with-pytest` で各兄弟の `.venv` の `pytest -q` を回し、結果行を release notes に写す（CI は置かない方針は変えない）。
- 根拠: cloud `tests/test_anthropic_backend.py:220`・`test_openai_backend.py:207`、mlx `tests/test_mlx_backend.py:74`（`isinstance` のみ）; 両 repo の tests に `contemplative_agent.testing` / `check_backend` 0 件; cloud `tests/test_main_contract_integration.py:37,47,70`・mlx `tests/test_mlx_backend.py:24,376,383`（`_circuit` 直触り）; 本体 `core/llm/backend.py:620` `circuit_reading()`、`testing/backend_contract.py:558`; `tests/test_backend_contract.py:223`; `docs/runbooks/sibling-backend-conformance.md:16-19`（CI 不採用は意図）
- 完了条件: release 前に手で回した兄弟 `pytest` の結果行（日付・commit。本体の Protocol を 1 引数変えると kit の check 名で落ちる形）を v2.13.0 release notes に写す — 兄弟 4 repo に CI は無く（`.github/workflows/` 不在、2026-10-10）手動実行でしか見えない; 兄弟 tests に `_circuit` の文字列が無い
- 規模・整合: S / repair   出典: SB-21 SB-12 SB-20 SB-37

##### P1-11.5 DecisionBackend 以後の兄弟注入の意味を明文化する（判定は常に Ollama）
- 何を: cloud / mlx の README に「relevance gate（RFC-0046）は Ollama 上の `DECISION_MODEL`（既定 = `OLLAMA_MODEL`）を使い、Ollama 常駐が必須。`DECISION_MODEL=` 空なら feed は何も engage しない」を明記し、ADR-0112 Review-when の該当行を更新する。`exclusive` は「Ollama 上に判定モデル以外が常駐する」= `ollama_model() != decision_model` で判定するか（cloud 注入下の毎バッチ gemma 再ロードを止める）、ADR-0112 追補で「兄弟注入時はバッチ毎の再ロードを受容」と書く。`_evict` の 404 は DEBUG で区別する。
- 根拠: `cli/runtime.py:177-189`（docstring）、`:243-253`（`exclusive=decision_model != served_model()`）; `core/llm/decision.py:398-406`（`_base_url` は常に Ollama）、`:425-440`（`_evict` は `raise_for_status` 無し）; ADR-0112:199「no sibling backend is built」; `docs/CONFIGURATION.md:500`; cloud / mlx の src・README に `decision` / `relevance` 0 件
- 完了条件: 両 README に記述、ADR-0112 Review-when 更新、cloud 注入下で `llm-calls` の decision 行 latency が再ロード分を含まないテスト（または追補で受容を明記）
- 規模・整合: S / repair   出典: SB-01 SB-02   順序: 11-14 の週（§4.0 の先行列）。`cli/runtime.py` は P0-02.2（:173-208 削除）→ P0-05 preflight → 本項目（:243-253 の `exclusive` 判定）→ P1-07.13（:295-316）

##### P1-11.6 otel を維持するなら: 行種別の変換と正本 fixture の契約テスト
- 何を: 本体が行種別ごとの代表行（generation / `kind:"decision"` / `caller:"embed"`）を `testing/telemetry_fixture()`（ADR-0088 と同じ配置）か `docs/evidence/` に公開し、otel の pytest がそれを読んで未知キーで fail にする。`load_records` に種別判定を入れ、span 名・属性は本体 `docs/otel-semconv-mapping.md` の表を正とする — decision 行は `ca.audit.*`（`kind` / `decision_reason` / `question_count` / `answered_count` / `prompt_norm_sha256`）に置き gen_ai span にしない（`:49-50`「the batch is not a gen_ai call」）、`embeddings {model}` / `text_completion {model}` は gen_ai、`p_top` は decision 行に無いので写さない; `ca.token_count.source` / `ca.thinking.source` 等を写す。「写す / 落とす」表に `outcome` 語彙（生成行 `ok / error / empty / circuit_open / budget_exceeded / truncated_dropped / truncated_kept`、decision 行 `ok / error / circuit_open / budget_exceeded`）→ `status_error` / `error.type` の 1 列を足す。provider は model id 接頭辞（`claude-` / `gpt-` / `mlx-community/`）から導き不明は `unknown`。`docs/mapping.md` の `solver_path` 語彙を `scripts/_census_registry.py` の enum に同期し、`_emit_telemetry` の全キーを「写す / 落とす」で表に載せる。凍結なら本項目は閉じ、README に Frozen 行（.1）。
- 根拠: 本体 `core/llm/__init__.py:347-363,407`（decision 行は同じ `llm-calls-*.jsonl`。キーに `prompt_norm_sha256`（`:361`）はあり `p_top` は無い）、`:718,765,813,885,979,1007,1043`（outcome 語彙）; 本体 `docs/otel-semconv-mapping.md:49-50`; otel `mapping.py:88`（`outcome == "error"` だけを error に）、`records.py:207`（`prompt_sha256` のみ読む）; otel `records.py:57-77`（`LlmCall` に `thinking_source` 等なし）、`:187-208`（`kind` を見ない）、`:275-295`（3 ログのみ）; `mapping.py:65-70`（全行 `text_completion` / `ollama`）; `tests/fixtures/llm-calls-2026-01-01.jsonl`（6 行、`run_id` / decision / embed 0）; `docs/mapping.md:56`（退役済み `llm_reason`、本体 `verification.py:12`）; `docs/otel-semconv-mapping.md:80-85`（2026-08-16 の consumer lag）
- 完了条件: 本体で `_emit_telemetry` のキーを増やすと otel のテストが落ちる、3 種別 1 行ずつの fixture で span 名と属性が固定される
- 規模・整合: M / neutral   出典: SB-04 SB-05 SB-06 SB-09 AR-35   順序: `_census_registry.py` の `solver_path` enum は Entry 1 行の差分で順序不問

##### P1-11.7 cloud を維持するなら: 緩めた分の最小衛生（cloud.env の mode、無人起動の明示ゲート）
- 何を: `_load_home_cloud_env` が `cloud.env` の mode を見て group/other 可読なら WARNING（拒否はしない）。`--auto` 起動は `CONTEMPLATIVE_CLOUD_ALLOW_UNATTENDED=1` 無しでは拒否（sibling 側のみ、main 無改変）。ADR-0015 追補・`CLAUDE.md:93` の 1 文・scan の一致検査は D-P1-11-4 の実施として .1 が持つ（cloud の処遇に依らない）。cloud README に鍵の置き場の 1 段落: `$MOLTBOOK_HOME/cloud.env` は本体の backup / sync mirror の対象領域にあるので、鍵は shell 環境変数で渡す（`_load_home_cloud_env` は不在を黙って許す）か、置くなら本体側の `*.env` 除外（P0-03.2 / P1-10.9）が入っていることを確認する（P0-03 第 5 章から移送）。
- 根拠: cloud `src/contemplative_agent_cloud/cli.py:42-60`（`read_text` のみ、`stat` 無し）; cloud `README.md:32`（本体 HOME の 0600 を前提に書く）、`:46-60`（relaxes を明記）; cloud `cli.py` に `auto` / `unattended` の記述 0 件; `agent-run/SKILL.md:62-66`（`-v --auto` で起動）; D-P1-11-1 の推奨 B は「.4 .7 は実施しない」ので、ADR-0015 側の 3 点は .1 に置く
- 完了条件: sibling テスト 2 本（mode WARNING、`--auto` の明示 env 拒否）と cloud README の鍵の置き場 1 段落
- 規模・整合: S / neutral   出典: SB-23 SA-19 SA-15（cloud README）   依存: D-P1-11-1（維持のときだけ）、D-P1-11-4

##### P1-11.8 otel の exporter record に本文 / b64 欄が無いことを不在テストで固定し、README に metadata-only を明記する
- 何を: exporter に渡る record（`records.py`）に本文・b64 欄が無いことを fixture で固定する不在テスト 1 本と、README に「off-host へ送る場合は metadata-only（hash・endpoint 名・caller 名・categorical code）であることを確認せよ」の 1 段落。`--endpoint` の host 制限は置かない（やらないこと候補）。D-P1-11-3 = B なら Frozen 行（.1）に「off-host へ送るなら hash と categorical code だけ」の 1 句で足り、A なら .6 の契約テストに吸収する。
- 根拠: otel `records.py:1-8`（untrusted free-text は parse 時に落ち、dataclass に欄が無い）、`docs/mapping.md:74-83`; `emit.py:141-145`（endpoint は `OTLPSpanExporter(endpoint=…)` に明示で渡すので `OTEL_EXPORTER_OTLP_ENDPOINT` の上書きは効かない）; README:23-27 が metadata-only を既に言う; `cli.py:23`（既定 `http://localhost:4318`）、`:51-53,87-88`（任意 URL）
- 完了条件: 不在テスト 1 本（A）か Frozen 行の 1 句（B）、README 1 段落
- 規模・整合: S / neutral   出典: SA-34

##### P1-11.9 契約キットの runtime 段を出荷するか static で凍結するかを記録する
- 何を: D-P1-11-5 の結果を ADR-0088 追補に書く。出荷なら mlx に `BackendProbe` を実装し `check-sibling-backends.sh --require runtime`（mlx_lm.server 起動時のみ）、`generate` の `None` 契約・`think` 無視・`context_window` 整合の 3 検査から。凍結なら「static のみ、runtime は sibling が必要になったら」と書き、script に `--decision` の target 行をコメントで置いて「現在 0 件」と明記。
- 根拠: ADR-0088 en:179-208（catalogued 23 件未実装）、`:310`「23 of 29」; `testing/backend_contract.py:59`（`KIT_VERSION = "2"`）、`:109-117`（`DEFAULT_REQUIRE = LEVEL_STATIC`）、`:470-480`（static 6 検査）; `testing/decision_contract.py:205-215`（static 4 検査）; `testing/backend_probe.py`（Protocol のみ 139 行）; mlx `pyproject.toml:50-52`; `check-sibling-backends.sh` に `decision` 0 件
- 完了条件: ADR-0088 追補、または mlx の release gate 行が `level=runtime`
- 規模・整合: M / neutral   出典: SB-22 AR-24

##### P1-11.10 rules repo に本体の較正契約を書き戻し、tag を切る
- 何を: rules の `README.md` と `benchmarks/prisoners-dilemma/README.md` に「contemplative-agent の ADR-0090 が `--protocol paper --prompt-file` で消費している。較正契約は gemma4:e4b / n=10 / ±0.13（null pair 2026-08-06/07）に加え、paper protocol（10 rounds・α 3 水準・`Choice:` 形式）、temperature 0.5、`num_predict` 500、`top_p` 0.9、Ollama `think: False`（`llm_player.py:164`）、挿入位置（user turn）、`_parse_move` の COOPERATE 既定を列挙する（bench 側の既定変更が床を黙って無効化するため）。`llm_player` のプロンプト・温度・パーサを変えたら本体の null pair を再取得する」を書き、`docs/calibration-gemma4-e4b-2026-08.md` から本体 `docs/evidence/adr-0090/null-pair-reading.md` へ相互リンク。`benchmarks/prisoners-dilemma/tests/test_prompts_in_sync.py`（既存の pytest 設定の下。rules に root `tests/` も `pyproject.toml` も無く新設しない）で `prompts/*.md` と package 内複製の sha256 一致を assert。rules に `v0.2.0` tag、本体 runbook と `ipd-two-arm.sh` の既定 `BENCH_REF` が tag を指す（D-P1-11-6 A の消費契約。P3-06.3 の SWH save / `.zenodo.json` の有無はこの tag を参照して決める）。P3-03.1 (b) の `ipd-two-arm.sh` provenance（10-31 の週）がこの tag を引く。
- 根拠: 本体 `scripts/ipd-two-arm.sh:36`（`BENCH_DIR` 既定 `../contemplative-agent-rules/benchmarks/prisoners-dilemma`）、`:37-38`（gemma4:e4b / `N_SIMS=10`）、`:131`; `docs/runbooks/constitution-amendment.md:3-5,13-15`; ADR-0090:51-62（null pair、±0.13）; rules `benchmarks/.../src/ipd/llm_player.py:22`（既定 `qwen3.5:9b`）、`:164`（`think: False`）、`README.md:106,120`（結果表は qwen。JA `README.ja.md:90,104`）、`grep -rni "two-arm\|amend\|gemma"` 0 件; `diff prompts/custom.md benchmarks/.../prompts/custom.md` 同一・paper-faithful 同一、同一性テスト無し（63 テスト）; rules remote tag 0
- 完了条件: 両 README に記述（契約フィールド列挙つき）、`benchmarks/prisoners-dilemma/tests/test_prompts_in_sync.py` 1 本が既存 63 件と同じ設定で通る、tag 存在、本体 runbook と `ipd-two-arm.sh` が tag を指す
- 規模・整合: S / repair   出典: SB-29 RF-43 SB-32   順序: 10-24 の週（§4.0 の先行列。憲法 due 10-31 の前）

##### P1-11.11 rules repo の文書修理（改正済み憲法との関係・死リンク・DOI・日付・私有パス）
- 何を: (a) README の Related Projects に「稼働インスタンスの憲法は改正済み（data repo `constitution/` 参照）。本 repo の条項は Appendix C verbatim（ADR-0002）で、本体の `config/templates/contemplative/constitution/` と同一」を 1 行（条項文自体は同期しない — やらないこと候補）(b) README L9 の効果量の帰属（「empirically validated … d=0.96 / d>7」）は P3-01.5 が正本（再現範囲表と同じ PR。JA `README.ja.md:9,112` と data `llms.txt:138` の再掲も P3-01.5 の完了条件）(c) `llms-full.txt:185` の `contemplative-moltbook` リンク、`llms.txt:47` の AAP DOI `19652014`（正は `19652013`）、`llms-full.txt:193` の "Last updated: 2026-04-26"、README の Related Projects（本体のみ）と `README.ja.md:134-136` を llms.txt の 3 件に揃える（sweep 対象に `README.ja.md` と data `llms.txt` を含める）(d) `CLAUDE.md:11-23` の Obsidian vault 絶対パスを「存在すれば参照」の条件付きにするか harness へ移す。
- 根拠: sha256 一致 — rules `rules/contemplative/contemplative-axioms.md` = 本体 `config/templates/contemplative/constitution/contemplative-axioms.md`（`e3b556…`）; 稼働中 `contemplative-agent-data/constitution/contemplative-axioms.md`（`37e355…`）は見出しから 8 条項すべて書き換え（「Revised Constitutional AI Clauses … amended」、`snapshots/amend-constitution_20260809T…`）; rules `README.md:100-102`、`README.ja.md:9,112,134-136`、`prompts/custom.md:3,53`; `llms.txt:47`、`llms-full.txt:185,193`; data `llms.txt:138`; 本体 `README.md:171` / AAP README の `19652013`; rules `CLAUDE.md:11-23`
- 完了条件: `grep -rn '19652014\|contemplative-moltbook'` が rules（JA 含む）と data `llms.txt` で ADR-0001 の歴史記述以外 0、README en/ja に改正済みの 1 行、rules CLAUDE.md に絶対パス無し
- 規模・整合: S / repair   出典: RF-43 PF-19 SB-33 SB-34   順序: 11-21 の週（§4.0 の先行列）

##### P1-11.12 rules ADR-0005（operator-keyed の効力）の観察に終了条件を置く
- 何を: ADR-0005 に観察の終了条件（例: 2026-10-31 までに flag 再発の有無を記録）を追補し、結果に応じて ADR-0002 の verbatim 原則を system-instruction 面で限定するか、ADR-0005 を "confirmed" にする。同じ追補に本体 ADR-0002 の dated note（P3-01.2 の 1 本、10-31 の週。P3-07.4 の段落は後から同じ note に入る）への逆リンク 1 行を含める（P3-07.4 は本体側だけに）。
- 根拠: rules `docs/adr/0005-…md:5-7`（accepted）、`:62`「Efficacy is unverified … single-adopter observation」; `README.md:148`; 最終 commit 2026-07-07（`eec96a4`）以降更新なし
- 完了条件: ADR-0005 の Status 行か追補に終了日と結論が入る
- 規模・整合: S / neutral   出典: SB-36 PF-18（逆リンク半分）   依存: P3-01.2（逆リンク先の dated note）   順序: 11-21 の週（§4.0 の先行列）

##### P1-11.13 release gate の兄弟行に `sha / main / level / kit` を出させ、README の Verified 行と CHANGELOG 行をその出力から写す
- 何を: `scripts/check-sibling-backends.sh` を数行変える: 成功時も kit の出力 1 行目（`<ConformanceReport ok level=static kit=2 …>` の repr）を出し、`git -C "$SIBLING_ROOT/$repo" rev-parse --short HEAD`（`--dirty` 付き）と本体の `git describe --tags` を同じ行に足す（例 `[sibling] ok mlx 2f6c7fd main=v2.12.0 level=static kit=2`）。README への自動追記は作らず、runbook に「この行を兄弟 README の Verified 行（.2 d）と CHANGELOG（P0-06.6 の段 2）に貼る」と書く。
- 根拠: `scripts/check-sibling-backends.sh:63-66`（成功時 `printf '[sibling] ok %s' "$target"` で `$out` を捨てる）; `testing/__main__.py:224`（`print(repr(report))`）、`backend_contract.py:308-313`（`ConformanceReport.__repr__`）、`:53-59`（`KIT_VERSION` の存在理由 = kit 改訂と backend 破損の区別）; script は兄弟 commit を記録せず working tree を import（`:21-22`、dirty 判定無し）; 唯一の記録は手書きの mlx `pyproject.toml:51-52`「Verified 2026-08-16 against main v2.10.0 … level=static」（kit 版無し。kit は `b424555` 2026-09-22 で v2）
- 完了条件: gate 出力に `sha= / main= / level= / kit=` があり、v2.13.0 の CHANGELOG と 3 兄弟 README の Verified 行がその文字列と `grep -F` で一致
- 規模・整合: S / instrument   出典: R1-SIB-03   順序: 11-07 の週（§4.0 の先行列。11-14 の決定の後、11-20 までの v2.13.0 の tag 前）。v2.13.0 の兄弟行には D-P1-11-1（10-31）/ D-P1-11-2（11-14）の結論を 1 句添え、P1-11.1 の状態列は決定（12-26）の後に同じ行へ足す   注: P0-06.6 の段 2 がこの行を CHANGELOG に写す（→ 参照元）
- 消費計画: (a) release gate を回す人が版ごとに読む (b) `kit=` が前回と違えば「kit が検査を増やした」、`sha=` が同じで落ちれば「本体の Protocol が変わった」と判定 (c) 兄弟が全て frozen で 2 release 連続同じ行なら Frozen 行の固定文字列に縮める

##### P1-11.14 otel 凍結時に ADR-0078 の語彙対応表の正本を本体 `docs/otel-semconv-mapping.md` に戻す
- 何を: D-P1-11-3 = B なら ADR-0078 の dated note（.1 の otel 状態行と同じ 1 本、D-P1-11-3 の後の同じ PR）に「正本は本体 `docs/otel-semconv-mapping.md`、otel `docs/mapping.md` は v2.10.0 schema の frozen copy」を書き、verification / api / 除外表を本体文書に 1 回複製して以後は本体が更新する（P1-07.13 で llm-calls 行に `template` を足す時も同じ表を直す）、otel README の Frozen 行に同じ 1 句、otel `docs/mapping.md:1-6` の canonical 宣言を frozen 表記に。A なら逆に otel が本体の正本 fixture（.6）を読む形にして本体の表を pointer のままにする。
- 根拠: ADR-0078:48-52「The canonical field-by-field table lives next to the code that implements it, in the sibling repository — this repo's copy is a pointer, not the source of truth」; 本体 `docs/otel-semconv-mapping.md:73-80` は llm-calls 面だけ自前で持ち verification / api / 除外表は otel `docs/mapping.md` へのリンク; llm-calls 面は本体が先行（`:16-38` が decision / embed 行を定義、otel `README.md:108-115` は embed のみ、最終 commit `ca9479f` 2026-08-17 < ADR-0112 2026-09-22）
- 完了条件: 本体文書が 3 ログ全面の表を持ち、ADR-0078 に dated note 1 本（.1 の otel 行と共用、2 本目を書かない）、otel `docs/mapping.md:1-6` の canonical 宣言が frozen 表記
- 規模・整合: S / repair   出典: R1-SIB-04 R3-ADR Merge-09   依存: D-P1-11-3   注: P1-07.13（2027-01-16 着手）が llm-calls 行に `template` を足す時に同じ表を直す（先行条件ではない）

##### P1-11.15 mlx wrapper の `mlx-server.log` の置場（`MOLTBOOK_HOME`）・umask 077・rotation と backup 除外
- 何を: mlx `scripts/run-with-mlx.sh` を `LOG="${MOLTBOOK_HOME:-$HOME/.config/moltbook}/logs/mlx-server.log"` + `umask 077` に直し、本体 `scripts/backup-runtime.sh` の rotation / 除外に `mlx-server.log` を 1 行（`ollama-serve.log` と同扱い）、`docs/runbooks/runtime-backup-restore.md:25` の表に 1 行。D-P1-11-2 = A（凍結）なら凍結 commit に含める。
- 根拠: mlx `scripts/run-with-mlx.sh:36`（`LOG="$HOME/.config/moltbook/logs/mlx-server.log"`、`MOLTBOOK_HOME` を見ない）、`:39` `mkdir -p`、`:108` `>>"$LOG" 2>&1`（umask 既定 → 0644。本体の audit 書込は `core/_io.py:155` `fchmod 0o600`）; 本体 `scripts/backup-runtime.sh:55` が回すのは `agent-launchd.log` のみ、`runtime-backup-restore.md:25` は `ollama-serve.log` 96 MB の前例を記録し `mlx-server.log` は除外表に無い; `scripts/_census_registry.py:228` は `*.log` を無視; 現在のサイズは本環境から未観測
- 完了条件: mlx 側に shell 検査 1 本（`MOLTBOOK_HOME=<tmp>` で本番 dir に書かない）、本体 `tests/test_backup_runtime_shell.py` に除外 1 assert
- 規模・整合: S / repair   出典: R1-SIB-05   依存: D-P1-11-2


**依存**
- P1-04（ADR-0101 T4 棚卸し — D-P1-04-1 と同じ 10-17。D-P1-11-3 は 12-26 で同じ回ではない）、P1-09.13（`docs_consistency_scan.py` の新検査を同じ scan に、12-05 の週）、P3-01.2（本体 ADR-0002 の dated note — .12 の逆リンク先、10-31 の週）、P0-03.2 / P1-10.9（cloud の鍵の置き場 — .7 に移送、SA-15）、P1-10.14（shell egress の固定集合 — .1 の ADR-0015 追補が保守 script の管理面として名指す、R2-PLAT-06）
- 順序: .1 と P1-09.2（`CLAUDE.md` 関連リポジトリ節）は同 PR（2027-01-09 の週）。`cli/runtime.py` は P0-02.2 → P0-05 → .5 → P1-07.13
- 後の週の項目（現行の形で書き、入ったら更新）: P1-09.7（graph.jsonld → HF mirror — .1 の棚卸し表 (2)）、P1-09.11（data repo の兄弟記述 — .1 の (2) と同じ PR、P1-09 着手 2027-01-23 の後）、P1-07.13（.14 の表の更新契機）、P1-06（凍結窓 — D-P1-11-1 = C のときだけ、cloud seam の退役は窓の中で）、P3-03（D-P1-11-1 = A のときだけ、大型モデル蒸留アームの RFC）
- → 参照元: P0-06（v2.13.0 release gate / release notes の兄弟行 — .1 .2 .3 .4 .9 と .13 の出力を写す）、P0-06.6（段 2 の CHANGELOG の結果行 ← .13 の出力）、P1-10（threat-model の外部面表 — D-P1-11-4 / SA-19）、P0-07 / P3-03（憲法改正ゲートが rules の IPD bench を消費 — .10 は次の due 2026-10-31 前に）、P4-02.5（archive の操作 — 条件は D-P1-11-6）、P3-06.3（SWH / `.zenodo.json` — .10 の tag を参照）、P3-03.1(b)（`ipd-two-arm.sh` の provenance に rules の tag / sha — .10）、P3-01.5（rules README:9 の効果量帰属の正本 — .11 (b) はそれを指すだけ）、P3-07.4（本体 ADR-0002 の dated note の段落 — .12 の逆リンク先に後から入る）、P1-15（D-P1-15-2（12-05、同じ回で D-P1-11-4 の後）の前提変更が D-P1-11-4 の分類を引く）
- RFC-0040（blocked、sibling 注入型 DecisionBackend の再考条件）、ADR-0067 の upstream issue（mlx-lm #615/#884/#854/#883 — この環境から現状未確認）、ADR-0112 Review-when
- 外部・未確認: gemma の MLX 重みの可用性（D-P1-11-2 B）、rules ADR-0005 の著者観察記録（.12）、`mlx-server.log` の現在のサイズ（.15）。PyPI は 5 名とも未公開と確認済み（2026-10-10、.2 c）


#### P1-12 承認ゲートの記録を「責任の行為」にする（approver・reason・却下本文・GOVERNANCE.md）
- 狙い: ADR-0080 の 08-26 追補 §A は「人間の言葉がゲートに残ることが attribution の錨」（0080:189-193）と言うが、現物の `audit.jsonl` には誰が・なぜが無く、却下本文は消え、役割定義は repo 外。AAP（ADR-0005/0006/0008）が CA を lineage に引く以上、本体の記録だけで責任構造を再現できる状態にする（付表参照）。
- 期限・順序: 着手 2027-01-09 の土曜ゲート（§4.0）。期限 2027-02。決定: D-P1-12-1 = 10-31 の土曜ゲート、D-P1-12-2 = 2027-01-09 の土曜ゲート。D-P1-12-1（`--yes` の位置づけ）は 2026-10-31 の憲法改正 due（P0-07）の前。先行は置かない（§4.0 の先行列に P1-12 の項目は無い）: .1 PR-A（`reason` / `channel` / `session`）と .2 / .3 は着手週 2027-01-09 に入れ、.1 の `approver` 欄と `gate_item` への署名経路は D-P1-12-2（2027-01-09）の結論で実装する。.7（GOVERNANCE.md）は D-P1-13-1（12-12）の決定後。.1 は PR-A（audit 行 3 欄 + FILE 3 列 + 行形状テスト。.9 の `snapshot_path` を同梱）→ PR-B（`gate_item` の `content_hash` + approval_join の flag + 検証スクリプト）→ PR-C（`approver`、D-P1-12-2 = 2027-01-09 の後）の 3 本。PR-C は src の機構変更なので凍結の停止リスト（P1-01.3）に期日つきの行を持つ（D-P1-01-1 の追加段 B を前提、決定前）。.5 は D-P1-12-1（10-31）の結論を ADR-0012 の部分 supersede として書く（追補と新 ADR の境界は P1-03.11 の暫定基準）。`weekly-gate/SKILL.md` を触るのは .1 PR-B の Step 7（`gate_item` に `content_hash`。Step 7 の所有者 = P1-12.1）・可逆性表の 1 句（「`mv` で戻した時は `gate_item` に 1 行」— 手編集の監査 CLI を第 5 章の延期行に移した間の代わり）・.7 の `:92` 参照差し替えだけで、SKILL.md の変更は 2027-01-08 までの同梱 PR に入れる。着手までの暫定 1 行（.2 の順序、却下の前に staged ファイルを `.rejected/` へ cp）は 10-17 の SKILL 同梱 PR（P2-01.10）に同乗し、先行列には足さない。
- 束の完了条件:
  - `tests/test_cli_approval.py` が全 `stage-*` 行の `reason`（enum + 自由文）/ `channel` / `session` キーを検証し（`approver` は D-P1-12-2 の結論後に同じテストへ）、直近 4 週の却下行の `reason` null 率が 0
  - fault-injection テスト（audit 書込不可 → 採用 0 件・exit≠0）が CI で緑
  - `schemas/audit.schema.json` が存在して CI で実行形と照合され（3 段 join 規則 = .9 を含む）、`value_layer_approval_join.py` の path 不一致が 0
  - staged 経路（`stage` / `stage-adopted-*` / `stage-rejected-names`）の新規 audit 行で `snapshot_path` が非 null、公開 `history/` の全版と直近 4 週の adopted skill が公開ファイルだけで snapshot dir に解決する script が exit 0（.9）
  - `docs/GOVERNANCE.md` が存在し（Accountable operator 行・AAP ADR 列・記録所在表に `logs/api-audit.jsonl` を含む）、`docs/adr` と `.claude` に `human-gate.md` 参照が 0、CYCLES.md 9 行に Approver / Record / Public? が埋まる
  - ADR-0012 が `partially-superseded-by` の新 ADR（または Status に partial と範囲）で `--yes` と「Claude Code は転記者」を述べ、未解決注記（:65）が消え、`tests/test_adr_status_consistency.py::test_partial_supersede_edges_are_reciprocal` が緑

##### P1-12.1 audit 行に「誰が」「なぜ」「どの経路で」を足し、gate_item と鍵で結ぶ
- 何を: PR-A: `_log_decision` に `reason`（adopt / reject の全 `stage-*` 経路で受ける。却下理由は enum `duplicate | off-constitution | low-quality | stale | other` + 自由文の 2 欄、schema は .4）、`channel`（`tty | names-file | yes-flag | headless`）、`session`（Claude Code セッション id か weekly の `run_id`）を先に足し、承認者 ≠ 転記者が行の中で読めるようにする。`--adopt-names` / `--reject-names` FILE を「名前 TAB 理由コード TAB 自由文」の 3 列可にし、group reject は共通理由 1 行（.9 の `snapshot_path` 転記を同じ PR に同梱）。PR-B: weekly-gate Step 7 の `gate_item` に `content_hash` を転記し、`value_layer_approval_join.py` に「`approver` が登録名に無い行」の flag と、1 週分の gate_item を audit 行に解決する検証スクリプトを足す。PR-C（D-P1-12-2 = 2027-01-09 の後）: `approver` 欄 — 正本は .7 GOVERNANCE.md の「Accountable operator」行（名前・ORCID・since）で env は override のみ（固定値の環境変数は誰が打っても同じ文字列で、責任の行為の記録にならない）。触るのは `cli/approval.py::_log_decision`、`cli/adopt.py`（`_adopt_write_item` :234 / `_reject_unselected` :1067 の経路）、SKILL.md Step 7、`scripts/value_layer_approval_join.py`、schema（.4）の 4 ファイル・2 面。
- 根拠: `src/contemplative_agent/cli/approval.py:188-199`（record に approver / channel / session 欄なし、`reason` は :125-127 で「remove-skill 等のみ」）、`:90-92`（`stage-adopted-auto` = "used by non-TTY coding-agent workflows"）; `cli/adopt.py:1107-1115`（reject は `reason` を渡さない）; `cli/*.py` に `isatty` 0 件、repo に `MOLTBOOK_OPERATOR` 0 件（2026-10-10 grep）; `.claude/skills/weekly-gate/SKILL.md:389-400`（gate_item は item/category/recommendation/decision のみ、audit への鍵なし）; AAP `docs/adr/0006-causal-traceability.md:46-47`「human approver (or rejecter) and a timestamp」、`0005:64-66`「reason field populated for rejections」、`0005:76-78`「Its decision still flows through the same audit record」、`0008:52-54`（named human が operational record に）
- 完了条件: 新規行に `reason` / `channel` / `session` が入る行形状テスト（`approver` は D-P1-12-2 後に同じテストへ）; 直近 4 週の却下行で `reason` null 率 0・enum 外 0; 1 週分の gate_item が `content_hash` で audit 行に全件解決する検証スクリプト; approval_join の登録名外 flag が 0; PR-C は凍結の停止リスト（P1-01.3）に期日つきの行を持つ（D-P1-01-1 の追加段 B を前提、決定前）
- 規模・整合: M / repair   出典: GO-01 GO-02 GO-09 CU-23 CU-24   依存: D-P1-12-2（`approver` 欄・`gate_item` の署名経路）、.7（Accountable operator 行）、.4（enum を schema に）   順序: PR-A は着手週 2027-01-09、PR-A → PR-B → PR-C（R2-IMPL Fix-15）; SKILL.md Step 7 は 2027-01-08 までの同梱 PR

##### P1-12.2 却下された提案の本文を破棄せず保存する
- 何を: reject 経路で `content_file.unlink` の代わりに `MOLTBOOK_HOME/.rejected/<ts>-<content_hash>.md` へ移動する（削除でなく移動、ADR-0097 D5 の archive と同じ可逆性。命名は audit 行の `content_hash` と一致させ .1 の鍵で引く）。却下本文の保全先はこの 1 か所に固定し（P3-04.3 / P3-06.4 の読み元もここ）— 憲法 / identity の却下案も同じ場所から hash で引け、`--stage` 時の所有者の一行所見（`--note`）は .1 の `reason` 欄と一体。公開するかは P2-05（D-P2-05-2）。
- 根拠: `cli/adopt.py:1097-1110`（Unlink BEFORE logging → `_log_approval(..., False, ...)`、本文は hash のみ残る）; `approval.py:194`（sha256 先頭 16 hex）; data repo `snapshots/` の kind（distill 84 / insight 11 / …）に staged 候補本文は無い; README.md:36（547 却下 = 本プロジェクト固有の一次データ）
- 完了条件: audit 行の `content_hash` から却下本文ファイルが引けるテスト（憲法 / identity の候補も対象。推測: 2026-09-19 以降の insight 候補は `insight-stages.jsonl`（ADR-0111 D6、b64）に残るが identity / constitution の却下本文は無い）; `.rejected/` が `sync-research-data.sh` の既定除外に入るテスト
- 規模・整合: S / repair   出典: GO-03   順序: 着手週 2027-01-09。着手までは暫定で、weekly-gate SKILL.md Step 6b と `docs/runbooks/constitution-amendment.md` の裁定段に「却下の前に staged ファイルを `$MOLTBOOK_HOME/.rejected/` へ cp」の 1 行（10-17 の SKILL 同梱 PR = P2-01.10 に同乗。本項目は着手週のまま、先行列には足さない）

##### P1-12.3 監査行の書き込みに失敗したら採用を続行しない
- 何を: `_adopt_write_item` / `_reject_unselected` が `_log_decision` の False を受けたら書き込みをロールバック（または skill_archive と同じく監査行を先に書き、失敗なら書かない）し、exit code を非 0 にする。
- 根拠: `approval.py:175-186`「Adopt and reject ignore it ... log-and-continue behaviour is unchanged」; `:200-205`（OSError → warning → return False）; AAP `0005:64`「The audit record is non-negotiable」
- 完了条件: fault-injection テスト（audit パス書込不可）で採用 0 件・exit≠0（root 実行では skip、`745b892` #9 と同じ扱い。同型は `tests/test_cli_skill_archive.py::TestArchiveAtTheAdoptGate::test_a_completed_move_with_a_failed_audit_write_is_not_success`）; 書き換える既存テスト: 既存テストは不変（HEAD の `tests/` に log-and-continue を pin するテストは無い — `grep -rn 'Failed to write audit' tests/` 0 件、2026-10-10）。ただし「監査行を先に書く」案を採る場合のみ `tests/test_cli_adopt.py::TestAdoptStagedUncoveredFailurePaths::test_a_failed_reject_unlink_is_a_failure_not_a_rejection`（unlink → log の順を pin、2026-08-01 H1）を書き換える（R2-IMPL-01）
- 規模・整合: S / repair   出典: GO-05   順序: 着手週 2027-01-09

##### P1-12.4 audit スキーマ・訂正行・完全性モデルを正本化する
- 何を: `schemas/audit.schema.json` を本体に置く（`decision` enum に historical `held`、`source` enum = `AuditSource`、.1 の新欄 `reason_code`（enum: duplicate / off-constitution / low-quality / stale / other）/ `reason` / `channel` / `session` / `approver`、staged 経路の `snapshot_path` と 3 段 join 規則 = .9）。`path` の実在しない 2 行（憲法 08-09 `contemplative-axioms-2.md`、identity 08-15）に `command: correction` 行を 1 回追記し、各行に「手当て: 誰が・いつ・`mv` 元→先・照合した sha」を入れる（08-09 は ADR-0090:276-291「Remediated by hand within minutes … sha verified against the audit record」、08-15 は `cli/adopt.py:192-197` の docstring にしか無く、公開 snapshot から 04:02Z〜04:17Z の間と絞れる。P3-07.1 のチャネル (2) の dated 実例 2 行と identity 側の dated note（`docs/evidence/adr-0091/`）は P3-07 / P3-04 で書く）。「鍵は `content_hash`、`path` は参考」を docstring と DATACARD に書く。`path` は `MOLTBOOK_HOME` 相対で記録する。ADR-0012 追補か DATACARD に完全性モデル（append-only・0600・週次 private backup の git 履歴が改竄検出面、hash は識別用）を 1 節。
- 根拠: `approval.py:43-58`（`held` の歴史的混在は docstring が正本）; `:191`（`path: str(path)` = 絶対パス）; `docs/adr/0090-…ja.md:254-256`「承認レコードは存在しないパス … 信頼できるキーは content hash」; `core/_io.py:201-207`（umask 0177 append のみ）; AKC `schemas/` に episode-log / knowledge はあるが audit は無い
- 完了条件: schema が CI で実行形と照合される; `value_layer_approval_join.py` が訂正行を解釈し不一致 0; DATACARD と AAP 0006 Lineage から link
- 規模・整合: S / neutral   出典: GO-04 GO-06 GO-10 VL-04

##### P1-12.5 ADR-0012 の部分 supersede: `--yes` の位置づけと「Claude Code は承認者ではない」
- 何を: D-P1-12-1 の結論を、ADR-0012 を `partially-superseded-by` にする新 ADR（または ADR-0012 の Status に partial と範囲を書く形）に書く — 代替案 1 の却下理由（:50「Claude Code can read results and make an approval decision」）の反転にあたり、D-P1-03-1 推奨 A の暫定基準（P1-03.11）では追補・日付付き Notes ではなく partial supersede になる。中身は `--yes` / `--adopt-names` / `--reject-names` / `--archive-names` と audit source の表（`AuditSource` に `takedown` を足す: P3-05.14 の抑止リスト適用行と P3-05.19 (d)、approver 付き。それまでは P3-05.14 の私的台帳 — R2-ETH-06）、「`--yes` は人間が全文を読んだ後の TTY 代替、打つのは人間が立ち会うセッションだけ」、「Claude Code は説明係・転記者であり承認者ではない（weekly-gate Step 1b / ADR-0085 / ADR-0098）」。代替案 1（:50）と注記（:65）を閉じ、`approval.py:90-92` の docstring（`stage-adopted-auto` = "used by non-TTY coding-agent workflows" — 退ける AAP 0005 path (1) をそのまま符号化している文）も同じ PR で書き換える。AAP 0005 path (1) の「supervising agent = operator」を 0008 と整合させる注記を AAP 側に書く（AAP CLAUDE.md:34 の双方向規約）。
- 根拠: `docs/adr/0012-human-approval-gate.md:20,50,65`（`--auto` 無し / 「Claude Code can read results and make an approval decision」/ 未解決注記）、本文に `--yes` の記述なし（:76 の remove-skill のみ）; `approval.py:31,88-91`（`stage-adopted-auto`）; README.md:38（憲法改正 2 件が `--yes`）; `docs/runbooks/constitution-amendment.md:37`（Step 4 `adopt-staged -y`）; AAP `0005:76-83` vs `0008:75-77`
- 完了条件: ADR-0012 の Status と graph のエッジが partial supersede で終わり（新 ADR と双方向、`tests/test_adr_status_consistency.py::test_partial_supersede_edges_are_reciprocal` が緑）、新 ADR（Status 形なら ADR-0012）の文言と `AuditSource` 列挙（`takedown` を含む）・docstring が一致（"non-TTY coding-agent workflows" の文が無い）; :65 の未解決注記が無い; 両 ADR（CA 側 / AAP 0005）が同じ答えを書く。SKILL.md:176 の既定が `--adopt-names --reject-rest` である点は既に成立
- 規模・整合: S / neutral   出典: GO-07 GO-17 GO-47 CU-25 SA-21 R3-ADR-03   依存: P1-03.11（暫定基準）、P1-03.1（関係語の Guidelines）

##### P1-12.7 `docs/GOVERNANCE.md`: 役割・artifact class × 承認者・記録の所在を本体に置く
- 何を: 1 ページに (a) 役割（runtime agent / weekly session / judge / build / human）とツール権限、(b) artifact class（値層 4 種 / `config/prompts` / `.claude` / `scripts/weekly-*` / `src` / `tests` / `docs/adr` / `rfcs` / data repo）× 生成者 / 承認者 / 記録先 / 可逆性 / 公開の表（AKC ADR-0028 の保護クラスと ADR-0085 の scope を本体語彙で）、(c) 退役済み `human-gate.md` の 3 規則（1 作業 1 ゲート・inspector not approver・escalation）の転記、(d) 「Accountable operator: <名前・ORCID>、since 2026-03-07、gap-bearer = 同一人」の行（.1 の `approver` の正本。交代は P4-03.2 の両者承認の監査行）、(e) 表に「AAP ADR」列と「条文番号は本体に書かず AAP `docs/policy-mapping/eu-ai-act.md`（2026-08-04 読み）を日付つきで参照」の 1 行、(f) 記録の所在表: `audit.jsonl` は rotate しない・`logs/` は週次 private backup に含まれる・`logs/api-audit.jsonl`（request / response の構造欄のみ）は RCA Q4「どの外部面に触れたか」の証拠（P4-03.3、AAP 0006 required artifacts の adapter call log の記入例）。CYCLES.md master table に Approver / Record / Public? の 3 列を足し、ADR-0085:54,133,197 と SKILL.md:92 の参照を差し替える。
- 根拠: `docs/CYCLES.md:222-223`（役割契約の正本は `~/.claude/rules/common/`）; `rfcs/README.md:8-10`（起票規約・状態語彙・判断が claude-harness）; AKC `README.md:128`（gate は harness の `boundary.md`）、AKC `0028:83`「a harness without such a list has no line to apply」; `docs/CYCLES.md:82-92`（列に承認者・記録・公開が無い）; AAP `0007:54-66`（scaffolding は file として version-controlled）; 本体に AAP ADR / EU AI Act への参照 0 件（`grep -rni 'AI Act\|2024/1689'`）、AAP `docs/policy-mapping/README.md:24,75-81`（改訂で decay するのは mapping 側）; `scripts/weekly-analysis.sh:424`「the audit log never rotates」、`scripts/backup-runtime.sh:4-8`（episode logs・audit trails を private repo へ）、`adapters/moltbook/client.py:45`（`API_AUDIT_PATH`、構造欄のみ）; AAP `0008:52-54`（named human が operational record に）
- 完了条件: ファイルが存在し CYCLES.md:222-223 がそこを指す; `grep -rn human-gate docs/adr .claude` = 0（`docs/plans` の履歴は除く）; 9 行すべて 3 列が埋まり Public? = No の行に理由がある; Accountable operator 行と AAP ADR 列があり、所在表に `api-audit.jsonl` の行がある（grep）
- 規模・整合: M / neutral   出典: GO-21 GO-22 GO-23 GO-27

##### P1-12.9 staged 経路の audit 行に snapshot への鍵を書き、3 段 join の規則を schema に置く
- 何を: `.meta.json` に `snapshot` 欄（producer の snapshot dir 名か `run_id`）を書き、`_adopt_write_item` / `_reject_unselected` の audit 行に `snapshot_path` として転記する（コード変更は .1 PR-A と同じ PR）。`schemas/audit.schema.json`（.4）に join 規則「採用行.content_hash = stage 行.content_hash、stage 行.run_id = manifest.run_id」を書き、`run_id` の無い 18 manifest は `ts` 近傍規則（同 command・±1 分）で `lineage.json`（P3-04.12）に backfill し「推定」と印す。`approval.py:123-125` の docstring「None when the command did not produce a snapshot」を直す（staged コマンドも snapshot を書く）。
- 根拠: `cli/staging.py:266-274`（`stage` 行の `_log_approval` に `snapshot_path` を渡さない）; `cli/adopt.py:304-314`（`stage-adopted-*` / `-auto` 行も渡さない）、`cli/memory_cmds.py:124-131`（`direct` 経路だけが渡す）; `core/_io.py:194-200`（audit 行に `run_id` を刻印）、`core/snapshot.py:124-126,166`（manifest の `run_id` は「audit.jsonl を経由せず llm-calls 行に直接 join」）; data repo manifest 100 件中 `run_id` 無し 18 件（`distill_20260718…`〜`insight_20260731…`、14 鍵世代）; 両憲法採択・月次 identity 採択・全 insight 採用が staged 経路（README.md:38、ADR-0091）
- 完了条件: 公開 `history/` の全版（識別 3 版・憲法 08-09）と直近 4 週の adopted skill が、公開ファイルだけ（decisions 投影 + manifest）で snapshot dir に 1 本の script で解決し、解決不能な版は「snapshot 回転で消失」と表に出る; 新規 staged 行の `snapshot_path` 非 null が .1 の行形状テストで固定される
- 規模・整合: S / instrument   出典: R2-VL-01   依存: .1 / .4（行形）、P3-04.1（snapshot 保持）、P3-04.12（`lineage.json`）   注: P2-05.2（2027-02-20 着手）の投影列 `snapshot` はこの規則を読む側（→ 参照元）
- 消費計画: (a) FLIP 束（P3-02）・再現ガイド・RCA（P4-03.3）が「版の特定」で読み、土曜ゲートは P2-05.2 の投影列で見る (b) 解決表 1 回の読みで backfill の「推定」行を人が確認し、解決不能な版の数で P3-04.1 の保持条件（kind 別 prune）を変えるかを決める (c) 撤去条件: 公開 `history/` の全版が解決し、以後 8 週「解決不能」が新たに出なければ script は release gate のみに縮める


**依存**
- P1-13（D-P1-13-1 = 12-12 の権限配置が .7 の表の中身）、P0-07（D-P1-12-1 を憲法 due 前に）、D-P1-12-2（2027-01-09: .1 の `approver` 欄と `gate_item` の署名経路）、P1-03.11（.5 の partial supersede の暫定基準、10-17 から）、P3-04.1 / P3-04.12（.9 の snapshot 保持と `lineage.json`）
- 順序: .2 の暫定 1 行は P2-01.10（10-17 の SKILL 同梱 PR）に同乗
- → 参照元: P3-04.3 / P3-06.4（却下本文の読み元 = .2）、P2-05 / D-P2-05-2（却下本文・audit 投影の公開範囲は後で決める）、P2-07.1（D-P2-07-1 = A なら `restore-skill` だけを層 1 の実装に同梱 — 第 5 章の延期行）、P3-05.19 (d)（audit source `takedown` = .5 の後）、P4-03.2 / .3（operator 交代の監査行、RCA Q4 の証拠 = `logs/api-audit.jsonl`）、P2-05.2（投影列 `session` = .1 / `snapshot` = .9 の規則、。reason enum は P2-05.2 の投影と P3-06.2 の却下理由分布が前提にする）、P2-01.10（roadmap 決定の `gate_item` 行: `approver` は D-P1-12-2 の結論後、それまでは転記 — R2-GATE-01）、P3-05（DATACARD の schema 節、P3-05.14 の `takedown` source = .5）、P3-06（AAP 側への書き戻し: 0005 path (1) 注記・0006 Lineage link、P3-06.6 の条文列は AAP 逆引き索引から導出）、P3-07.1 / P3-04.2（.4 の訂正行と対になるチャネル (2) の dated 実例と identity の dated note）
- 外部: AAP CLAUDE.md:34 の双方向更新規約、claude-harness `boundary.md`（repo 外、本環境から読めない）


#### P1-13 AI 判断役の権限境界と帰属表示の明文化
- 狙い: オーナー原則は「人間がオーケストレーター、AI オーケストレーターは責任構造を壊す」だが、harness 側（AKC ADR-0028、2026-09-15）は判断役 AI に保護クラス外の merge/push を渡し、本体の CYCLES.md は「Every promotion stays human」のまま。どちらが本体の原則かを決めて書き、「誰が書いたか」（Co-Authored-By 4/447、判断役の commit が全部オーナー名義）を記録で区別できるようにする。ADR-0080 の 08-26 追補 §A の「負荷→0、権限は人間」の権限の所在を本体に残す作業。
- 期限・順序: 着手 12-12 の土曜ゲート（§4.0）。期限 2027-01。決定: D-P1-13-1 / D-P1-13-2 = 12-12 の土曜ゲート、D-P1-13-3 = 2027-01-30 の土曜ゲート。D-P1-13-1 を先に（P1-12.7 GOVERNANCE.md の表の中身になる）、D-P1-13-1 = A のときの ADR-0080 の人間ゲート範囲は追補（2026-12）（P1-03.8、12-21〜25 の PR）の 1 段落に入れ、別の追補を起こさない。帰属 trailer は harness の commit テンプレへの要求（P2-03.1 の要求節の行）と同時。`Roadmap:` trailer（.3）は暫定（10-10 から）で手で付け、D-P2-01-5（10-31）= A / C なら以後止める（付いた trailer は残す）。harness のテンプレへの取り込みは .3 で行う。.5 は P1-08.23 / .24（12-19 の週）の後。.7 の写像の書き直しは P1-03.5 PR-B（graph の ADR ノード）より前に置き、ADR index の `[AKC: …]` タグ列の扱い（graph の akc-cycle-mapping から生成 / 削除）は P1-03.5 PR-A の決定に含める。AKC 側の PR（.7 の 2 面と .1 の ADR-0028 note）は P3-06.7 の AKC 書き戻しと束ねてよい。LICENSE / NOTICE と .8（skill の出自）は着手（12-12）後いつでも可。
- 束の完了条件:
  - `docs/CYCLES.md` master table #6 と :149 が D-P1-13-1 の結論と同じ主語・同じ権限配置を述べ（C なら「merge = 判断役、push = 人間」の本体例外が AKC ADR-0028 側にも dated note で書かれる）、FRESHNESS が 2026-08-26 から更新されている
  - 直近 50 commit で Claude 実装 commit に `Co-Authored-By`、無人セッション由来 commit に `X-Session` trailer が付く（`git log --format=%b | grep -c` が無人 commit 数と一致）
  - README / CITATION.cff / .zenodo.json に同一の AI 支援開発の開示文がある
  - `CONTRIBUTING.md`（1 段落 + Verify の通し方）/ `.github/ISSUE_TEMPLATE/{bug_report,proposal}.md` / `.github/PULL_REQUEST_TEMPLATE.md` / `NOTICE` が存在し（CODE_OF_CONDUCT は置かない）、本体と rules repo の LICENSE 名義が他 5 repo と一致
  - AKC 写像 5 面（graph.jsonld / ADR index タグ / CYCLES.md / AKC `CLAUDE.md:32` / AKC `examples/constitution_amend/README.md:18-27`）の一致テストが緑で、6 相すべてに realizedBy ≥ 1、退役 ADR・退役コマンドを指す相が 0
  - AAP / AKC 由来の skill 複製の frontmatter に `upstream` / `edition` があり、`git ls-files '.claude/skills/*/SKILL.md' | xargs grep -L '^upstream:'` が本体固有 skill だけを返す（母集団は tracked のみ）

##### P1-13.1 判断役 merge の権限配置を本体に決めて書く
- 何を: D-P1-13-1 の結論（推奨 C: merge は判断役、push = 公開は人間）を problem-solving ADR 1 本（C を採る場合）に書く — 本体 repo の保護クラス（rules / identity / constitution / skills / ADR / `config/prompts` / `.claude` / `scripts/weekly-*` / verify・CI・tests の assertion、および「行動を記述する文書」= README のゲート段落 `:142`・`docs/CYCLES.md`・`docs/CONFIGURATION.md`・`docs/GOVERNANCE.md` 自身・`docs/runbooks/*` — 判断役が自分の権限線を動かす merge を保護クラス外にしない）、人間の権限点 = admission と push、revert 2 件 / 3 か月の撤回条件、AAP ADR-0010 の Phase-crossing decision（新パターンは findings → triage → human gate = route to design、gap-bearer はオーナー）。CYCLES.md #6 と :149 を更新し FRESHNESS を打ち直す。C なら AKC ADR-0028 側に本体の例外（push = 人間）を dated note で書く。A を採る場合の ADR-0080 の人間ゲート範囲は追補（2026-12）の 1 段落（P1-03.8）。
- 根拠: `docs/adr/README.md:127-137`（Worldview は「プロジェクトの問題が読めるようになる枠組み」で、判断役の merge 権限は特定の運用問題への決定 = problem-solving）、ADR-0098 の題「Weekly Chain Single-Session Redesign and Repair Delegation to the Task-Triage Loop」（merge / push の権限配置は範囲外）; AKC `docs/adr/0028-…md:3,17-22,33`（2026-09-15 に switch 移動、保護クラス、admission）; `docs/CYCLES.md:1-7`（FRESHNESS 2026-08-26）, `:89`（#6 = pre-commit diff approval）, `:149`「Every promotion stays human」; 本体 git: `fdbc27e`（09-19「S18 a0cfa83 を main へ ff merge（検収: …）」）と `82b169e`（09-26「オーナーが S32 を merge・push … 判断役の事後検収」）が同じ名義で並び、09-15 以降 177 commit に Revert 0; `docs/adr/0098:73-78`（修理は triage loop 経由）; AAP `0010:107-113`; AKC `0005:38`「Editing an ADR or README that documents behavior | Yes」、`0028:33`「ADRs and other documents that describe behavior」（保護クラスに行動を記述する文書を含む）
- 完了条件: ADR が存在し CYCLES.md #6 / :149 と同じ配置を述べる; CYCLES.md と AKC ADR-0028（本体の例外節を dated note で含む）が同じ権限配置を述べ、保護クラスの列挙に GOVERNANCE.md と runbooks が入る; AAP `0010` Open question 2（:286-300）の脚注に CA の週次セッションが引かれる（→ P3-06）
- 規模・整合: S / neutral   出典: GO-13 GO-15 R3-ADR Fix-06 / Merge-01   注: A のときの ADR-0080 の段落は P1-03.8 が追補（2026-12）に書く（12-21〜25、D-P1-13-1 を材料に読む側 → 参照元）

##### P1-13.2 task-triage loop の契約と照合節の様式を本体に書く
- 何を: CYCLES.md Operating model か ADR-0098 追補に triage loop の契約を 1 節（入力 = `rfcs/*.md` frontmatter、出力 = 「照合」節の様式、無人 cycle が変えてよい state、頻度 Wed 17:07 / Sat 14:07、harness skill への固定リンク）。照合節の見出しに `(by: judge | owner)`、F-findings に `severity` / `claim_type`（defect|measurement|design）、triage の `verdict` を同じ enum で書く規約を `rfcs/README.md` に載せる。
- 根拠: `docs/adr/0098:73-78`（triage-ca が独立検証層）; `rfcs/0012-*.md` に「照合」21 回; `.claude/skills/weekly-report/SKILL.md:157`（`~/.claude/skills/task-triage` を指すだけ）; `rfcs/README.md:8-10`（規約の正本は harness）; 対照: `rfcs/0046:26-27`（`decision_model` / `decision_reason` は enum で記録）、SKILL.md:389-400（gate_item は enum）
- 完了条件: 契約節が存在し、`scripts/docs_consistency_scan.py` が照合節の様式（by: と verdict enum）を検査する
- 規模・整合: S / neutral   出典: WO-16 GO-19

##### P1-13.3 commit の帰属 trailer を揃える（Co-Authored-By・X-Session・Reviewed-by）
- 何を: D-P1-13-2 の方式を harness の commit テンプレに入れる — Claude 実装 commit に `Co-Authored-By: Claude <model> <noreply@anthropic.com>`（cloud build と同形）、無人セッション由来に `X-Session: triage-ca <date>`、クロスモデルレビューに `Reviewed-by:` / `Review-deferred:`（散文は残す）。凍結集合（P1-01.4）を触る `fix:` commit には `Reproduces: <audit 行 / failing test / replay>`（変更前に再現した証拠 1 行。直 push が運用の形で PR 本文は無いことが多いので commit trailer に置く）、ロードマップ項目の実装 commit には `Roadmap: <項目 ID>`（例 `Roadmap: P0-03.2`。暫定（10-10 から）で付け、D-P2-01-5 = A / C なら以後止める — 付いた trailer は残す。`freeze_reading.py` と P2-01.13 が別系列に出し、P1-01.7 の照合が機械で結ぶ）— trailer 語彙の正本は本項目で、P1-01.6 規則 (2) はここを参照し、`freeze_reading.py`（P1-01.1）が `fix` 以外の type と trailer 欠落を同じ 1 行で出す。
- 根拠: `git log --format=%an` = Tatsuya Shimomoto 442 / Claude 4 / Shenton YAN 1（447 commit）; `Co-Authored-By` は 4/447 で全部 cloud build（09-24〜25、`Claude Opus 5.5` + `Claude-Session:`、`verify.yml:1-3` の `claude/**`）; 「判断役」を含む commit 38 件・「無人 triage cycle」5 件（`c5b91c1` 等）は全部オーナー名義; merge 9 件中 3 件に「judge:」注記（`7176266`）; AAP `0006:98-101`「which human approved which version, which code introduced which capability」
- 完了条件: `git log --format=%b | grep -c X-Session` が無人 commit 数と一致; 直近 50 commit で trailer の欠落 0; 凍結後の `fix:` commit で `Reproduces:` 欠落 0（`freeze_reading.py` の 1 行）; 実装 commit に trailer `Roadmap: <項目 ID>`（10-10 以降の実装 commit で欠落 0。D-P2-01-5 = A / C ならその決定以後は数えない）
- 規模・整合: S / neutral   出典: GO-31 GO-32 GO-34 R2-IMPL Merge-03（P1-01.6 規則 (2) から）R3-HRN-05 R3-TIME-01   依存: P2-03.1 の要求節の行（harness commit sha）   注: D-P2-01-5（10-31）= A / C なら `Roadmap:` だけを止める（付け始めは決定を待たない）

##### P1-13.4 AI 支援開発の開示文を README / CITATION.cff / .zenodo.json に置く
- 何を: README「For tools and AI assistants」Facts に 1 行（例「Implementation is written by Claude Code under the owner's review; every commit is approved by the owner」— 文面は D-P1-13-2 に従う）、CITATION.cff と .zenodo.json の `notes` に同文。
- 根拠: README.md で Claude に触れるのは :106（hooks の案内）のみ; CITATION.cff に top-level `notes` 無し; `.zenodo.json` に `contributors` / `notes` 欄が不在; GitHub の co-author 表示は trailer がある 4 commit だけ（.3）なので「GitHub が自動表示するから不要」の前提は現物で崩れている（オーナーメモ `overview.md:43` は本環境では未検証）
- 完了条件: 3 面に同文がある（`grep` で一致）
- 規模・整合: S / neutral   出典: GO-35

##### P1-13.5 CONTRIBUTING（1 段落 + Verify の通し方）と issue / PR テンプレ、外部貢献の方針
- 何を: D-P1-13-3 の方針で `CONTRIBUTING.md`（英語 = README と同じ正本言語）を置く — 「ADR / RFC を要する変更の線」1 段落と Verify の通し方（入口 `./.claude/verify.sh`、ツール前提 uv / shellcheck-py / markdownlint-cli2（node 22）の OS 別導入 — 版は名指しせず「正本は `pyproject.toml` の dev group（shellcheck-py）と `package.json`（markdownlint-cli2）」を指す 1 行（P1-08.24、R2-TST-01）、`uv sync --group eval` が CI と同じ venv を作ること、Python 床 = P0-06.3 の `packaging` job の床 leg（3.11 + lowest-direct）、AI 支援の開示 = trailer）。`.github/ISSUE_TEMPLATE/bug_report.md`・`proposal.md`（RFC 起票への導線 = D-P1-13-3 A の入口）・`.github/PULL_REQUEST_TEMPLATE.md`（チェック 3 行: verify.sh 緑 / ゲート・閾値・段構成を変える PR は所有 ADR 追補を同 PR で（CLAUDE.md:13）/ AI 支援の trailer）を足し、README に Contributing 節（Citation の直前にリンク）と #9 の謝辞。CODE_OF_CONDUCT は置かない。
- 根拠: ルートに CONTRIBUTING / CODE_OF_CONDUCT / GOVERNANCE 無し; `.github/` は `workflows/verify.yml` のみ（2026-10-10 実見）; 外部 PR 既着 `745b892`（2026-10-08、Shenton YAN、#9 = root 実行時の chmod テスト skip）; README.md:119「fork it, take parts of it, or build on it」に PR の受け方なし; `verify.sh` を教える文書が無い（`grep -n verify CLAUDE.md README.md docs/CONFIGURATION.md` 0 件。`verify.yml:1-9` のコメントと `.claude/verify.md` のみ）、verify.sh は uv 不在で exit 2（`:55-58`）、shellcheck / markdownlint-cli2 不在は warn + skip（`:117, :154, :163`。案内は `brew install` と `npm i -g`）
- 完了条件: 4 ファイル（CONTRIBUTING + テンプレ 3）が存在し README「Citation」の直前にリンク; CONTRIBUTING が `verify.sh` と版の正本（dev group / `package.json`）を指す 1 行を持ち、版の数字を手書きしない（grep）; GitHub community profile は SECURITY.md（P1-10.3）と合わせて揃う
- 規模・整合: S / neutral   出典: GO-28 DC-42   依存: P1-10.3（SECURITY.md）、P1-08.23（verify.sh のツール不在の exit 2 / 要約行）、P1-08.24（版 pin の正本）   順序: P1-08.23 / .24（12-19 の週）の後に入れる（束の着手 12-12 より後）

##### P1-13.6 LICENSE 名義と NOTICE（ライセンス組合せ）
- 何を: 本体と `contemplative-agent-rules` の LICENSE 名義「Shimo」を「Tatsuya Shimomoto」に揃える。本体に `NOTICE` を置く（MIT の範囲、`config/templates/*/constitution` の出典と引用根拠、data repo は CC0、論文は CC BY）と README License 節からの link。
- 根拠: 本体 `LICENSE:3`「Copyright (c) 2026 Shimo」、rules repo も同じ; AAP / AKC / cloud / mlx / otel は既に「Tatsuya Shimomoto」（1074 bytes）; `CITATION.cff` / `codemeta.json` / `.zenodo.json` は Shimomoto, Tatsuya; data repo には `NOTICE` があり本体には無い; `config/templates/contemplative/constitution/contemplative-axioms.md:2`「Source: Laukkonen et al. (2025), Appendix C — verbatim」（原文ライセンス記載なし）; README.md:119 MIT、:53 CC0
- 完了条件: 7 repo の LICENSE 名義が一致（`sed -n 3p */LICENSE`）; NOTICE が存在し README が参照
- 規模・整合: S / neutral   出典: GO-36 GO-37

##### P1-13.7 AKC 6 フェーズ写像の正本を 1 面にする
- 何を: 正本にする前に graph の Research / Curate / Measure / Maintain 4 相を 2026-10 の実体で書き直す（Research = signal-first intake → relevance gate ADR-0112 / 0113・RFC-0046、Curate = 退役済み `rules-distill`（ADR-0097）を外し、insight を Extract に移した後の中身 — 候補は skill-stocktake（ADR-0016 / 0018）・出口（ADR-0097 / 0105）・novelty / duplicate 段（ADR-0111）で、推測を含む。下の Promote / Extract の案と同時に確定、Measure = 行動が変わったかの検査 → ADR-0089 / 0106 / 0099 / 0097 D5 / 0101、Maintain = docs と artifact の hygiene → ADR-0093 docs-consistency scan・dead-code scan（ADR-0085 / 0098 チェーン）・0014）。AKC 側の 2 面 — `CLAUDE.md:32`（「pivot snapshots=Measure」と Curate の `rules-distill`）と `examples/constitution_amend/README.md:18-27`（CA の amend を 6 相に写した表。同じファイルの `:14`「augmenting only (never deleting original clauses)」を訂正し、Measure 行から ADR-0090 / ADR-0092 へ link）— も双方向更新の AKC 側 PR で直す。その上で `graph.jsonld` の akc-cycle-mapping を正本とし、ADR index の `[AKC: …]` タグ（13 本、ADR 本文に無く README / README.ja の手書き行にだけある）を graph から生成するか削除（この扱いは P1-03.5 PR-A の決定に含め、本項目の書き直しは PR-B より前）、CYCLES.md master table に「AKC phase」列を graph と同文で足す。Promote の定義は AKC README の「human-gated change」に揃え、insight（生成）= Extract、adopt-staged = Promote とする案を AKC と同時に決める。
- 根拠: `docs/adr/README.md:28`「[0020] Pivot Snapshots `[AKC: Curate]`」vs `graph.jsonld:1411`「Measure -> pivot snapshots (ADR-0020)」; `graph.jsonld:1579`（Research = feed_manager / post_pipeline）、`:1683`（Measure の realizedBy = 0020 のみ）、`:1705-1710`（Maintain = 退役 ADR 5 本）; ADR index の `[AKC:` 13 本は Extract 6 / Curate 7 / Promote 6 / Maintain 1、Research / Measure 0; `docs/CYCLES.md:87`「Extract (distill) / Curate (insight)」; AKC `README.md:39`（Research = signal-first intake、Measure = checks whether behavior actually changed、Maintain = docs and artifact hygiene）; AKC `CLAUDE.md:32`（graph と一致、同じく古い）; `graph.jsonld:1411` と AKC `CLAUDE.md:32` はどちらも Curate に退役済み `rules-distill` を挙げる; AKC `examples/constitution_amend/README.md:14`「augmenting only (never deleting original clauses)」対 CA `config/prompts/constitution_amend.md:9`「rephrase clauses, remove what no longer holds, merge or split sections」（本番憲法は 8 節すべて書き換え済み — P1-11.11 の根拠）; `grep -l '\[AKC:' docs/adr/*.md` は README.md / README.ja.md のみ
- 完了条件: 5 面（graph / ADR index タグ / CYCLES.md / AKC `CLAUDE.md:32` / AKC `examples/constitution_amend/README.md:18-27`）の写像が一致し `tests/test_adr_status_consistency.py` 相当の検査が入る; 6 相すべてに realizedBy ≥ 1（Research / Curate / Measure / Maintain が 2026-10 の ADR を指す）; 退役 ADR・退役コマンドを指す相が 0; AKC `examples/constitution_amend/README.md:14` に「augmenting only」が無い
- 規模・整合: S / repair   出典: GO-26 R3-AKC M1 / F1 / F2   順序: P1-03.5 PR-A（タグ列の扱いを決める）→ 本項目 → P1-03.5 PR-B（graph の ADR ノード）

##### P1-13.8 AAP / AKC 由来 skill 複製の upstream・edition を frontmatter に記録する
- 何を: 対象 skill（`read-only-instruments` / `replayable-audit-logs` / `shadow-mode-validation` / `llm-agent-security-principles` / `code-and-llm-collaboration` / `when-code-when-llm`、要確認 `llm-pipeline-layering`）の frontmatter に `upstream: <repo>@<tag|commit>` と `edition: ca-specific | verbatim` を足し、編集方向（CA 固有の例は本体で書き、原則の変更は standalone 側へ — AKC `akc-cycle.md` と同じ一方向）を `CLAUDE.md` の skills 表に 1 列で書く（P1-09.2 と同じ表）。同じ表の注に 1 行「同名 skill の優先順位（user `~/.claude/skills/` / project `.claude/skills/`）と、edition = verbatim の skill は repo 側を編集しない」（優先順位は CLI の仕様で、本環境では未確認）。`tests/`（か `scripts/docs_consistency_scan.py`）で対象全件に両キーがあることを固定し、数え上げの母集団は `git ls-files '.claude/skills/*/SKILL.md'`（tracked のみ。手元の未追跡 skill — `.gitignore:82` の `silent-llm-calls-in-tests` — で CI と手元が割れない）。AAP `docs/skills/README.md` から本体を "filled-in example" として link（P3-06.6 と同じ PR）。
- 根拠: `.claude/skills/{read-only-instruments,replayable-audit-logs,shadow-mode-validation}/SKILL.md:1-6`（frontmatter は `name / description / compatibility / origin: shimo4228` のみ。upstream repo・commit・edition 無し — 2026-10-10 に本環境で再確認）; `llm-pipeline-layering/SKILL.md:1-6` は `origin: auto-extracted`（本体由来の可能性、要確認）; 出自リンクは `when-code-when-llm/SKILL.md:211`（AKC への Source 行）1 本; AAP `docs/skills/README.md:11-13`（standalone repo = ADR-0005 / 0006 の installable "how"）、`0005:124-128`（read-only instruments と shadow-mode validation が named approver の署名材料）; AKC `docs/akc-cycle.md:40-43`（同型の先例「the two copies drifted」→ 編集を一方向にして edition を宣言）; standalone repo との差分は本環境から未検証（`gh api` 403。推測: ドリフトの有無は不明）
- 完了条件: `git ls-files '.claude/skills/*/SKILL.md' | xargs grep -L '^upstream:'` が本体固有 skill（weekly-gate / weekly-report / agent-run / apple-silicon-local-llm-serving、必要なら llm-pipeline-layering）だけを返す（テストは tracked のみを数える）; standalone 側との差分を 1 回取り各 edition に verbatim / ca-specific を記録; CLAUDE.md の skills 表に編集方向の列と優先順位の注 1 行; `~/.claude/skills/` と同名の repo skill の一覧と優先順位の確認日を 1 行（オーナーの手元で確認）
- 規模・整合: S / neutral   出典: R1-AAP-01 R3-HRN Fix-01 / Fix-05   依存: 外部: standalone 3 repo の read（本環境では不可）   注: skills 表の列は現行の表に足し、件数一致は P1-09.2（2027-01-09 の週）が入ったら更新。AAP からの逆 link は P3-06.6 の PR（→ 参照元）


**依存**
- AKC ADR-0028 / claude-harness ADR-0069・0075（repo 外、本環境から読めない）、P2-03.1（harness に要求する変更の節 — .3 の commit テンプレ trailer の行、10-24 の週）、P1-10.3（SECURITY.md、.5 の community profile）、P1-08.23（.5 の Verify の通し方。.5 はこの後）、P1-08.24（shellcheck-py / markdownlint-cli2 の版の正本 = dev group / `package.json`、.5 はそれを指す）、P1-03.5（PR-A でタグ列の扱いを決め、.7 は PR-B より前）、D-P2-01-5（10-31。.3 の `Roadmap:` trailer を続けるか止めるか — 付け始めは待たない）、P1-03.11（.1 の ADR が新 ADR か partial supersede かの暫定基準）
- 後の週の項目（現行の形で書き、入ったら更新）: P1-09（.1 は CYCLES.md の FRESHNESS を打ち直し、P1-09 の文書整備が入ったら合わせる。P1-09.2 の skills 表の件数 = .8 の列）、P2-03（harness の claims 台帳の取り込み、着手 2027-02-13）
- → 参照元: P1-12.7（GOVERNANCE.md が D-P1-13-1 を消費）、P1-03.8（D-P1-13-1 = A のときの追補（2026-12）の段落）、P3-06（AAP case-studies / 0010 脚注への書き戻し、P3-06.6 = .8 の逆 link）、P2-07.1 の ADR + P1-12.5（GO-20 の受け皿: ゲート省略条件は層 1 の位置決めと同じ決定）、P1-01.6 / P1-01.1（規則 (2) が .3 の `Reproduces:` trailer を参照し、`freeze_reading.py` が読む）、P2-01.12 / P2-01.13 / P1-01.7（.3 の `Roadmap:` trailer を読む）、P3-06.7（AKC への書き戻し — .7 の AKC 側 PR に束ねてよい）


#### P1-14 CLI の残りの UX 整備（`.last_insight` の起点・テンプレート skills・installer の前提・`init` の Tier）
- 狙い: 初回体験（P0-05）の後に残る摩擦のうち、機構を増やさず既定と案内を直せるもの — 新規 home で週次 insight が走らない罠（.2）、テンプレート skills の schema（.5）、`.venv` 決め打ちの installer の前提（.6）、`init` の Tier（.9）。購読確認の永続化・`domain.json` の home 解決・prompts drift 警告・非 macOS の手引き・help の再編は R1 で落とした（第三者向けの新しい状態・解決経路・フラグで、凍結後に触る理由にならない。やらないこと候補）。承認ゲートは「責任を取る行為」（設計原則）なので、APPROVE で何を確認しているかは文書（P1-09.10 の副作用 1 表）で示す。
- 期限・順序: 着手束に数えない（P0-05 / P0-06 の PR に同乗、§4.0）。期限 2027-Q1（触る時だけ）。.2（`.last_insight`、数行）は 11-07 の週（§4.0 の先行列）に P0-05 の PR に、.9（`init` の Tier、数行）は 11-14 の週（§4.0 の先行列）に P0-06 の PR に入れる（凍結後に CLI 変更があることを前提にしない）。.6 は P0-06 の配布単位（RD-29 / CU-27）の決定（11-07）の後で D-P1-14-1 = 2027-01-30 の土曜ゲート。D-P1-14-2（購読確認の永続化、2027-03-06 の土曜ゲート）は推奨 C を前提（決定前）で本束に実装項目を持たない。.5 はいつでも可。
- 束の完了条件:
  - 新規 home で `init` 直後の `insight --stage` が WARNING で終わらないテストが緑
  - 新規 `init` 直後の `skill-stocktake` の LOW QUALITY が 0（テスト）
  - 「clone + `.venv` 前提」が README / CONFIGURATION に明記され `install-schedule` のエラー文がそれを指す（D-P1-14-1 推奨 B を前提（決定前）。P0-06 が wheel を選んだ時だけ `.venv` の無い checkout で `--dry-run` が妥当な plist を出す）、plist 描画に `--domain-config` 引数がある
  - `init` が `NO_LLM` で、`CONTEMPLATIVE_CONFIG_DIR=/nonexistent init` が traceback でなく 1 行メッセージ + rc=1
  - APPROVE で確認される副作用の一覧（P1-09.10 の 1 表）と `_confirm_*` 呼び出し箇所の集合が一致する docs テストが緑（本束からは P1-09 を参照するのみ）

##### P1-14.2 新規 home に `.last_insight` の起点を与える
- 何を: `init` が `.last_insight` = init 時刻を書く（新規 home では「init 以降のパターン」が incremental の自然な定義で、ADR-0074 の「暗黙の full recluster を拒む」は保たれる）。併せて CONFIGURATION.md の scheduling 節に「既存 home で marker が無ければ初回は `insight --full` を手で」を 1 行。
- 根拠: `src/contemplative_agent/core/insight.py:990-997`（marker 無し → `refusing the implicit full recluster (ADR-0074)` で None）; `cli/session_cmds.py:56-117` `_do_init` は marker を作らない（`write_last_insight` は `cli/memory_cmds.py:231, 265, 277` の insight 実行後のみ）; `config/launchd/com.moltbook.insight.plist:12-14` は `insight --stage` を流す; 実測 behave.txt: 新規 home の `insight` / `insight --stage` とも WARNING で rc=0（launchd ログの 1 行だけが手がかり）。
- 完了条件: 新規 home で `init` 直後の `insight --stage` が WARNING 無しで incremental（0 new patterns）になるテスト / CONFIGURATION.md に bootstrap の 1 行。
- 規模・整合: S / repair   出典: CU-07

##### P1-14.5 テンプレート skills を live store の schema に揃える
- 何を: `config/templates/*/skills/*.md` 20 本を本文は変えず live 形式（frontmatter + `## Problem` / `## Solution`）に変換する（代替は stocktake に第 2 schema を許すこと。推奨は変換 — 初期値と抽出 skill を同じ物差しで棚卸しするため）。
- 根拠: `src/contemplative_agent/core/stocktake.py:161-169` `_check_skill_quality` は `## Problem` / `## Solution` 必須; `grep -L "## Problem" config/templates/*/skills/*.md` = 20 / 20（11 テンプレート、tabula-rasa は 0 本）; 実測 behave.txt: 新規 home の `skill-stocktake` が `LOW QUALITY: deep-inquiry.md — missing "## Problem" section` 等を列挙。
- 完了条件: 新規 `init` 直後の `skill-stocktake` の LOW QUALITY が 0（テスト）。
- 規模・整合: S / neutral   出典: CU-22

##### P1-14.6 `install-schedule` の `.venv` / `config/launchd` 決め打ちの前提を明記する（描画の一般化は wheel 配布の時だけ）
- 何を: D-P1-14-1 に従い既定は (B)「本番は clone + `.venv` 前提」を README / CONFIGURATION に明記し、`Error: venv not found` のエラー文がその段落を指すようにする。(A) `Path(sys.executable).parent`（か `shutil.which("contemplative-agent")`）と package data のテンプレートから描画して `--dry-run` を足すのは P0-06 が wheel 配布を選んだ時だけ（配布単位の決定前に A をコードに入れない）。同じ PR で plist テンプレートの `--auto run --session` に `--domain-config <path>` を渡す 1 引数を足す（旧 .3 の機構部分。第三者の `domain.json` 複製の文書 1 段落は P0-05.10 (d)）。
- 根拠: `src/contemplative_agent/cli/schedule.py:229-237` `project_root = runtime._repo_root()`、`template_path = project_root / "config" / "launchd" / …`、`venv_bin = project_root / ".venv" / "bin"`（無ければ `Error: venv not found`）; `config/launchd/com.moltbook.agent.plist:12` `{{VENV_BIN}}/contemplative-agent`、`:12-18` は `--auto run --session` のみで `--domain-config` を渡さない、`:21` `WorkingDirectory {{PROJECT_ROOT}}`; `docs/CONFIGURATION.md:393-404` は手順のみで前提の記述なし。
- 完了条件: (B) 文書に前提の 1 段落があり、`install-schedule` のエラー文がそれを指す; plist テンプレートに `--domain-config` 引数（描画テスト）/ (A) は wheel の時だけ: `.venv` の無い checkout で `install-schedule --dry-run` が妥当な plist を出すテスト。
- 規模・整合: S / repair   出典: CU-28, RD-04, CU-13（plist 引数の部分のみ）

##### P1-14.9 `init` の Tier を `NO_LLM` にする
- 何を: `CommandSpec(name="init", …, tier=Tier.LLM_FULL)` を `NO_LLM` にし、設定ディレクトリ不在は `init` 内で 1 行メッセージ + rc=1 にする。`init` はファイル複製だけで LLM・domain 配線を要しない（最小権限）。
- 根拠: `src/contemplative_agent/cli/session_cmds.py:644-650`（`tier=Tier.LLM_FULL`）; `cli/__init__.py:125, 134`（`NO_LLM` は配線を飛ばし、`LLM_FULL` は `_configure_llm_and_domain` を通す）; `cli/agent_cmds.py` の `solve` / `status` は `Tier.AGENT`; 実測 2026-10-10: `MOLTBOOK_HOME=<tmp> CONTEMPLATIVE_CONFIG_DIR=/nonexistent contemplative-agent init` → `FileNotFoundError: Prompts directory not found: /nonexistent/prompts`（`core/domain.py:294 load_prompt_templates`、`cli/__init__.py:133 _configure_llm_and_domain` 経由で `_do_init` に到達しない）、traceback 表示で rc=1。
- 完了条件: Ollama 系 env が壊れていても `init` が rc=0 で通るテスト / `CONTEMPLATIVE_CONFIG_DIR=/nonexistent init` が traceback でなく 1 行メッセージ + rc=1。
- 規模・整合: S / repair   出典: CU-38


**依存**
- P0-06 RD-29 / CU-27（配布単位、11-07）→ .6（D-P1-14-1、2027-01-30）
- P1-09（.6 の文書側。P1-09 着手 2027-01-23 は .6 の決定 2027-01-30 より前）
- RFC-0042（insight は 2026-09-19 に再開済み、blocked）: .2 は再開とは独立の起動時の罠。P0-01 の insight 方針が「退役（形 C）」なら .2 は文書 1 行に縮退
- 順序: .2 は P0-05 の PR（11-07 の週）、.9 は P0-06 の PR（11-14 の週）に同乗（同 PR）
- 後の週の項目（現行の形で書き、入ったら更新）: P1-09（.2 の CONFIGURATION.md の 1 行は現行の文書に書き、P1-09 の書き直しで合わせる）
- 旧項目の移し先（先行条件ではない）: P0-05.10 (d) / P0-05.7（旧 .3 / .4 の文書行、D-P0-05-2 推奨 B を前提（決定前））、P0-05.4 / .10 (e)（旧 .8 の `--session` 範囲と `--guarded` の例）、P1-09.10 / .20（旧 .1 の副作用 1 表、旧 .7 の OS 前提宣言）、P1-07.13（旧 .4 の packaged との差分 WARNING 1 行）
- → 参照元: P1-12.7（GOVERNANCE.md の素材 = P1-09.10 の副作用 1 表、本束からは P1-09 経由で参照するのみ）


#### P1-15 relevance face の較正と face ループの昇格（RFC-0047）
- 狙い: score4 gate（t=0.3）は 2026-10-07 以降、本番で最頻の判断コールの唯一の判定経路になったが、事前登録の gate 率予測は（問いの単位の誤りとして）不成立のまま、閾値は enforce 前の母集団で置かれ、較正・margin・位置バイアス・真値の二段は未測定。RFC-0047 の解除条件「2 face の決着」は実質成立しており、ループの型と face 台帳を昇格先（置き場は D-P1-02-2 が決める）と CYCLES に揃えて記録することが、機構層を「止める」前の最後の計器整備（ADR-0080: 修理と計器は in-scope、能力拡大は不可）。
- 期限・順序: 着手 12-05 の土曜ゲート（§4.0）。期限 2027-01（.1 の台帳 PR は D-P1-02-2 = 2027-01-09 の後）。決定: D-P1-15-2 / D-P1-15-1 = 12-05 の土曜ゲート（同じ回の順は D-P1-11-4 → D-P1-15-2 → D-P1-15-1。t の裁定はその真値の既定が決まった後）。.2（再較正）の 3 回目の読みは 10-31 の週（§4.0 の先行列）— S40（10-07）以降の feed 行が post 単位で 150 に達してから、かつ月次 identity adopt（ADR-0091）の前に 1 回。読みは先行し（D-P1-11-4 前の 1 回の Jev 送信は ADR-0015 の現行の研究用途扱いで行い、12-05 の分類で事後に記録）、t の裁定は 12-05。.1（台帳と教訓の記録）は P0-02 の 10-17 の削除 PR の後で、置き場は D-P1-02-2（2027-01-09）が決めた昇格先（RFC-0047 の終端は P1-02.6 だけが持つ）、台帳の真値列は D-P1-15-2（12-05）の結論を引く。.2 の weekly JSON 1 節（adopt 前後の gate 率）は headless の weekly-report が作れない（tools に Bash 無し、`weekly-pipeline.sh:123`）ので chain の stage（7b と同形、materials 段の決定論 script）に置き、weekly-report はその 1 行を転記するだけ（現行の chain の形で書き、P2-04.13 PR-A（P2-04 着手 2027-02-06）が入ったら移す）。.3〜.5 は .1 の後、順不同。
- 束の完了条件:
  - D-P1-02-2 が決めた昇格先（P1-02.6）にループの型と face 台帳があり、`docs/CYCLES.md` #5 / #6 に face 台帳の再導出手順 1 行（RFC-0047 の `state: done` は P1-02.6 の完了条件で、本束は持たない）
  - 昇格先の face 台帳に temperature / 失敗時の向き（所有 ADR）/ 真値 judge（二段）の 3 列
  - ADR-0113 evidence に S40 以降の post 単位 150 行での t ∈ {0.3, 0.5} の P / R（3 回目の読み、Wilson 区間つき）と Review-when に「identity adopt 後 150 post で再読」
  - `relevance_shadow_reading.py` の週別出力に margin 比率と `ollama_version` の列; adopt 前後 gate 率の 1 節は chain の stage が書き、weekly-report は転記のみ
  - `.claude/verify.sh` full mode が `relevance_label_set.py check` を advisory で回す

##### P1-15.1 face 台帳に 3 列を足し、D-P1-02-2 が決めた昇格先と CYCLES.md #5 / #6 に置く
- 何を: 10-17 の削除 PR の後、D-P1-02-2（2027-01-09）が決めた昇格先（ADR 1 本か CYCLES.md #6 の 1 段落 + evidence、P1-02.6）に 1 PR で、ループの型（行数 clock・enforce-first・label once / score many・ratchet 規約）と CYCLES.md #5 / #6 の再導出手順 1 行を書く（RFC-0047 の終端 = done は P1-02.6 だけが持つ）。face 台帳に「temperature（0 / 既定 1.0）」「失敗時の向きと所有 ADR」「真値 judge = Jev（既定、版 pin）/ opus（Jev 不可時）」の 3 列を置き、label set manifest に `judge` / `judge_version` を pin する。真値 judge の交代（Jev ↔ opus、版の変更）は装置境界として P3-02 の regime 表に 1 行入れる。Consequences に pilot の教訓を書く — 事前登録の問いは post 単位で置く、paired 行の二重計上、予測値にも区間を付け差の区間で判定する、n=300 の導出 1/√n（ADR-0113:428-429）は p=0.5 の最悪値で p≈0.13 なら半幅 ±3.8 pt（計算）— 問いは n でなく予測値の不確かさで決まった。task-triage 検収 checklist の 1 行は → P2-03。
- 根拠: `rfcs/0047:3` review-when「2 face が enforce か retire に決着したら…昇格し done」、relevance = keep（`rfcs/0046:180`、2026-10-04）、skill selection = RFC-0044 done（09-26）+ decision shadow は後始末 3 の削除対象（`rfcs/0046:258`）/ 真値の食い違い: `rfcs/0047:41`「本番 shadow 行 × opus の二値ラベル」対 `rfcs/0046:112`「審判 = Jev」、`evals/jev_arm.py:87-89`（1.13.0 に pin）、`docs/evidence/rfc-0046/label-set-2026-09-28.json` の manifest に judge 欄なし（summary の `label_judge` のみ）/ temperature: `core/llm/__init__.py:573-580` は 3 面のみ列挙、`select_submolt`（`llm_functions.py:638`）と `distill.py:505-506` は既定 1.0 / 向き: relevance = fail-closed（ADR-0113 amendment 1）、novelty / stages = fail-open（ADR-0111:101-105）、submolt = skip（`post_pipeline.py:471-485`）。
- 完了条件: D-P1-02-2 の昇格先に台帳 3 列と Consequences の教訓、CYCLES.md 1 行。manifest に judge key。`generate()` docstring の列挙を実態に合わせる。
- 規模・整合: S / neutral（前提変更: ゼロ API の例外 — 研究ラベル付けのみ、≈$0.01 / 回、egress 分類は D-P1-11-4。本番既定化ではない）   出典: LP-29 LP-15 LP-35 LP-09 TQ-31 R3-ADR Merge-08   依存: P1-02.6 / D-P1-02-2（置き場と RFC-0047 の終端）、D-P1-15-2（真値列）

##### P1-15.2 t=0.3 を enforce 後の母集団（post 単位）で再読し、identity adopt 前後の gate 率の窓を置く
- 何を: S40（10-07）以降の feed 行（`source: "feed"`、post 単位 dedupe）から 150 行を `relevance_label_set.py sample` → `label`（Jev ≈ $0.01）→ `score` し、t ∈ {0.3, 0.5} の P / R を ADR-0113 evidence に追記、オーナーが事前登録の規則を新母集団に再適用して t を確認する（維持でも可、D-P1-15-1）。事前登録に検出力の 1 行を置く: S36 は on_topic 10 / 150（`rfcs/0046:175`）で recall 1.000 の Wilson 95% は [0.72, 1.00]、precision 0.532 は ≈ [0.32, 0.73]、予測値（n=150）の半幅 ≈ ±7.6 pt（非加重の計算。`cuts_weighted` の加重ではさらに広い）— 「±6 pt」の判定は点でなく「差の区間が 0 を含むか」で行い、post 単位を主要単位（`rfcs/0046:176`）、事前登録に `cuts_weighted` を使うと明記する。chain の materials 段の決定論 script（7b と同形）が weekly JSON に「adopt 前後 7 日の post 単位 gate 率」1 節を出し（`relevance_shadow_reading.py --since`。weekly-report は転記のみ）、差の区間が ±6 pt を含まない時に再読を開く条件を ADR-0113 Review-when に 1 行。
- 根拠: `rfcs/0046:125-128` S35 t=0.3 P / R 0.618 / 0.930（enforce 前 150 行）、:168-172 S36 0.532 / 1.000（on_topic 10 / 150）、:180 face gate keep は「事前登録の問いは post 単位で読むべきだった」を記録（行単位 0.127 / post 単位 0.271）/ ADR-0113 amendment 1 Review-when（:329-336）は fail_closed / backend_null / upvote 数のみで t の再読と adopt 条件を含まない / `core/relevance_state.py:53` production_domain_text = identity + axioms、`relevance_cache.py:145` は domain sha を pin（adopt で全 post 再採点）/ commit `6fa1dd6`（本番 0.127 対 予測 0.346、母集団 2.5 倍の交絡）。
- 完了条件: evidence に 3 回目の読み（post 単位・新 strata、区間つき）が固定。Review-when に「identity adopt 後 150 post で再読」。weekly JSON に adopt 前後の 1 節（chain の stage が書く）。区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）。
- 規模・整合: S / instrument（前提変更: ゼロ API の例外 — 研究ラベル付けのみ、Jev ≈ $0.01 / 回、egress 分類は D-P1-11-4。本番既定化ではない）   出典: LP-11 LP-31 OI-32（計測部分のみ）   依存: P2-01.9（区間規則、10-31 の週）   注: D-P1-11-4 前の 1 回の Jev 送信は ADR-0015 の現行の研究用途扱いで行い、12-05 の分類で事後に記録する。weekly 1 節の stage は現行の chain の形（7b と同形）で書き、P2-04.13 PR-A（2027-02-06 の週）が入ったら移す
- 消費計画: (a) 3 回目の読みはオーナーが 12-05 の土曜ゲート（D-P1-15-1）で 1 回読む; adopt 前後 gate 率の 1 節は土曜ゲートが weekly の該当行で adopt の翌週に読む (b) 3 回目の読みは差の区間 1 回で t の維持 / 再導出を決め、adopt 前後の 1 節は差の区間が ±6 pt を含まない時だけ再読を開く（含めば何もしない） (c) 撤去条件: 値層の identity adopt が定常宣言（D-P2-01-3 A）で止まれば adopt 前後の 1 節は撤去（3 回目の読みは evidence に固定済みで撤去対象ではない）

##### P1-15.3 shadow reading に margin 分布と `ollama_version` の列を足す
- 何を: `relevance_shadow_reading.py` の週別に |p_top − t| ≤ 0.05 の post 比率と、session_id join の `ollama_version`（版が変わった週に印）を足す。margin 比率が大きければ近傍のみ 2 回読みの多数決か hysteresis を RFC で検討する（読み値 1 節 + 判断 1 行。読みの前の既定は「入れない」）。
- 根拠: `docs/evidence/rfc-0045/README.md:381-382`（dev 150 を 2 回: 行単位 |ΔP(段 3)| 平均 0.023・p95 0.099、閾値 0.3 / 0.5 / 0.7 での gate 反転 2 / 2 / 4 行）、`rfcs/0046:85`（t=0 の logprobs は run 間で bit 再現しない）、`:127`（記録値 vs 再採点 p95 0.119、反転 4 / 5 / 6 行）、`:184`（同一本文で 6 post の判定が入れ替わった）/ `relevance_cache.py:81 PIN_VERSION = 2`、:90 `TTL_DAYS = 14`（post 単位の再採点は止めたが 1 回目の引きは近傍で乱数に近い）/ `core/llm/decision.py:51 OLLAMA_TOP_LOGPROBS_CAP = 20`（Ollama 0.34.2 の値）、週別は `decision_reason` のみで版の列なし。
- 完了条件: 週別出力に 2 列。読み値 1 節と判断 1 行（RFC-0046 か .1 の昇格先）。
- 規模・整合: S / instrument   出典: LP-12 LP-33
- 消費計画: (a) 土曜ゲートが weekly の relevance 節で margin 比率と `ollama_version` の印を読む (b) 4 週の読みで margin 比率の水準を見て、近傍のみ 2 回読み / hysteresis の RFC を書くか「入れない」を確定する（読みの前の既定は「入れない」） (c) 撤去条件: 判断 1 行が RFC-0046 か .1 の昇格先に入った後は `ollama_version` 列だけ残し、margin 列は census の 1 列に縮める

##### P1-15.4 lab 側で較正（ECE）と 4 段ラベルの位置バイアスを 1 回ずつ読み、evidence に固定する
- 何を: `relevance_label_set.py score` に reliability 図（5 帯）と ECE を足し `docs/evidence/rfc-0046/` に固定、report の文言を「P(top)（未較正）」にする。dev 150 を段の並びを逆（D〜A）にした prompt で各順序 2 run 回す（または AUC 差の bootstrap CI を `docs/evidence/rfc-0045/relevance-noise-20260926.json` の run 間差と並べる — 1 run では順序と run 間ノイズが交絡する: temperature 0 でも argmax 一致 0.913、`rfcs/0046:85`）。run 間ノイズの推定量は P3-03.10 のセル別 SE 規則（10-31 の週、正本）に従う。AUC 差の区間を `docs/evidence/rfc-0045/` に固定。区間が 0 を含まない場合に ADR-0112 の seam へ seed 付きラベル順ランダム化を入れるかは、この読みの結果を条件に別途 RFC で決める（D-P1-15-2 は真値 judge の決定でランダム化を扱わない）。
- 根拠: ADR-0112:283（noul 形で ECE 0.766 = 最悪較正）、RFC-0045 / 0046 evidence は AUC と t ごとの P / R のみ、`grep -i 'ece\|reliability' scripts/relevance_*.py` → 0 / `core/llm/decision.py:458-466` は options を `label_alphabet` 順に固定描画、shuffle なし / `docs/evidence/rfc-0043/README.md:55, 72` の「順序入替」は skill selection の enum arm のみ、rfc-0045 README に順序感度の記述なし / `core/report.py:166-177` は P(top) を確率として表示。
- 完了条件: evidence JSON に `ece` 欄 + 順序感度 1 節（各順序 2 run か bootstrap CI、推定量は P3-03.10）。report 文言変更。
- 規模・整合: S / neutral   出典: LP-13 LP-14   依存: P3-03.10（推定量の正本、10-31 の週）

##### P1-15.5 relevance face の決定論検査（label set の失効）を verify.sh に配線する
- 何を: `scripts/relevance_label_set.py check --dir .notes/labels/relevance/<latest>` を `.claude/verify.sh` full mode の advisory に足す（本体が無い clone では静かに skip）。「face の prompt / seam に触ったら `score --baseline` を回す」規約は .1 の昇格先の ratchet 節に書き、task-triage checklist の 1 行は → P2-03。
- 根拠: `.claude/verify.sh:174-178` は `evals/check_staleness.py` だけを advisory で回し、`relevance_label_set` への参照なし / `docs/evidence/rfc-0046/README.md:17-31`「ratchet の回し方」は手動コマンド 3 行、失効時は再ラベルか ack / `config/prompts/relevance_score4.md` の最終変更 `5cf42b7`（2026-09-25）以降、変更で warn する経路が無い / `rfcs/0047:60` ratchet 規約 4 は RFC が blocked のまま未配線。
- 完了条件: `relevance_score4.md` か identity の変更で verify full が warn を出す（手元で 1 回確認）。
- 規模・整合: S / neutral   出典: LP-23


**依存**
- P0-02（RFC-0046 後始末 3、10-17 の削除 PR の後）: .1 の前提（ADR-0112 shadow・旧 arm の削除後に台帳を書く）
- P0-01 / ADR-0091（月次 identity staging・adopt）: .2 の adopt 前後の窓
- P1-04.10〜.12（eval 層の位置づけ）: 昇格先の Face A 行
- P3-03.10（run 間ノイズの推定量の正本 — .4 はそれを参照）、P2-01.9（率の区間規則 — .2 の P / R、R2-STAT-02）
- 外部: Jev（closed weights、RFC-0040、版 1.13.0 の継続提供）
- D-P1-11-4（cloud 判定者の egress 分類、12-05。同じ回で D-P1-15-2 → D-P1-15-1 より先）
- P1-02.6 / D-P1-02-2（2027-01-09。.1 の置き場と RFC-0047 の終端）
- 後の週の項目（現行の形で書き、入ったら更新）: P2-04.13 PR-A（chain の stage の形 = 7b と同形 — .2 の weekly 1 節、2027-02-06 の週）、D-P1-04-3（2027-02-06。eval 層の位置づけ — 昇格先の Face A 行は現行の扱いで書く）
- → 参照元: P2-03（私的ハーネス: task-triage 検収 checklist の 1 行）、P2-01（北極星の読み値: face gate の推奨 ↔ 裁定の一致率）、P3-02（regime 表: 真値 judge の交代を装置境界として 1 行）、P3-01.1（事前登録の `reanalysis` 列 — .2 の読みは private-rows（ラベル集合は `.notes/`）、R2-STAT-06）


### Phase 2 — 自己調節とゲート負荷ゼロ（決定 2026-10〜12 と 2027-02〜03 ／ 先行 2026-10〜11、実装 2026-11〜2027-03）

ADR-0080 08-26 追補 §A の「ループがオーナーと Claude Code の日常的関与なく自己調節し、人間ゲートの負荷が 0 に近づく」を、まず計測可能にし、次に無人チェーンの依存と検知面を整える。ゲートの溶解はしない（08-26 追補 §A の境界）。自動停止・自動修復の判断も入れない。

**このフェーズの完了条件**
- 負荷 3 系列と自己調節の週次読みが materials に出て、4 週連続で介入ゼロを機械が示せる（P2-01）
- headless Claude Code の位置づけが ADR-0080 追補として決まっている（P2-02）
- 本 repo だけで週次運用モデルが閉じる（私的ハーネス依存 0 または文書化済み、P2-03）
- watchdog がループ本体・Ollama・Moltbook・sync を検知し、失敗が非 0 終了で人間に見える（P2-04）
- 無人 LLM 出力の公開が 2 層に分かれている（P2-05）
- 土曜ゲートの読み量が carried 畳み込み後に半減している（P2-06）


#### P2-01 北極星の読み値を機械化する（止まる・負荷・自己調節・一致率）
- 狙い: ADR-0080 の 08-26 追補 §A の 2 つの必要条件（「止まる」「負荷→0 で自己調節」）は、追補自身が「load reading が出たら計器の要否を再読する」と予約した（`docs/adr/0080:262-264`）のに、読み値は 6 週分出ている（Inventory 行・`gate_record`）まま誰も集計していない。材料はすべて既存の自己書き込みログにあるので、新しい判定者を増やさず read-only の読み手だけを置く。
- 期限・順序: 着手 11-28 の土曜ゲート（§4.0）。期限 2027-Q1。ただし .1（census 行の修正）と .2（`gate_start`）は 1 行の変更なので 10-17 の週（§4.0 の先行列）に先に入れる（`_census_registry.py` は Entry 1 行の差分なので .1 / .8 / P1-07.5 の順序は不問、同じ PR でもよい）。`weekly-gate/SKILL.md` の変更（SKILL 部分 .2 / .10 / .11 / .12 / .13 / .14）は 10-17 の週（§4.0 の先行列）の同梱 PR で、10-16（金）までに main へ入れる（.2 = Step 0 の `gate_start` と Step 7、.10 = Step 1c、.11 = Step 0 の時刻表、.12 = Step 1c の束の閉じの 1 句、.13 = Step 1c 前後の `roadmap_start` / `roadmap_end`、.14 = Step 1c の繰り越し行。他の Step の所有者は Step 0(a)(b) = P2-04.13、Step 0(c) = P2-04.17、Step 7 の `content_hash` = P1-12.1、Step 6d = P2-05.1）。同じ PR に P1-12.2 の暫定 1 行（Step 6b と `docs/runbooks/constitution-amendment.md` の裁定段に「却下の前に staged ファイルを `$MOLTBOOK_HOME/.rejected/` へ cp」。P1-12.2 の着手 2027-01-09 まで）が同乗する。.3 / .5 は .1 の派生列に依存し、8 週表を出す script は .5 の 1 本で、「止まる」列は P1-01.1 の `freeze_reading.py` の出力を写す。.5 の初版は 11-28 の週（11-23〜27）に merge して D-P2-01-1 の選択肢の和集合（B の 3 系列 + 起票 / 修理数 + 所要分）の列を出し、決定後に使わない列を落とす。.5 の初回値は RFC-0042 の 10-10 読み（P0-01）の後に evidence に固定する。.7（空選択の 4 週系列）の手動 4 run は 10-31 の週（§4.0 の先行列）、materials 配線は着手週 11-28 の 2 回目の読みまで。.8（`publish_failed` 理由列）は着手週、.9（Wilson 区間）は 10-31 の週（§4.0 の先行列、P1-15.2 と同じ週）、.6 の watchdog shell テストは P1-08.1 の後。.13 は SKILL の 2 行だけ 10-17 の週で、分離 3 列は .5 の初版 PR に入れる。.10 の凍結版（`docs/plans/roadmap-2026-10/`）と .12 の閉じ表は同じ commit、.14 の節は同じディレクトリの `decisions.md` に置く。`Roadmap:` trailer は 10-10 の作業から暫定で付け、D-P2-01-5 = A / C なら以後止める（付いた trailer は残す）。決定は D-P2-01-5 が 10-31（.12 / .13 の commit trailer）、D-P2-01-1 / D-P2-01-3 が 11-28（追補（2026-11）の材料）、D-P2-01-2 が 12-12、D-P2-01-4 が 2027-02-13（停止の是非と N の値は D-P4-01-3、12-19）。
- 束の完了条件:
  - weekly materials の `## Instrument Census` に `pipeline-metrics` が OK で現れ（`uv run pytest tests/test_instrument_census.py` 緑）、その母集団に `category=roadmap` の `gate_item`（.10 の様式）が含まれる
  - `scripts/self_regulation_reading.py`（.5）1 本が直近 8 週の表（裁定数・所要分・読み量・ゲート外作業・draft/修理数・一致率・止まる系列（P1-01.1 の出力列）・空選択率）を exit 0 で出し、率の列には区間（.9）が併記される
  - ADR-0080 追補（2026-11、P1-03.8）に Re-read trigger の発火と「負荷」3 系列の読み方の段落がある（読み値は材料、判定は人間が `gate_record` に書く）
  - `docs/evidence/adr-0080/` に初回 6〜8 週の読み値が固定され、`docs/plans/roadmap-2026-10/` に全文の凍結版・`decisions.md`（「遅れたとき」節つき）・39 行の束の閉じ表がある（.10 / .12 / .14）
  - 公開 `reports/PIPELINE-STATUS.md` に最終人間ゲート日の 1 行がある

##### P2-01.1 ゲート記録の読み手を置く（census 登録行の修正と派生列）
- 何を: `scripts/_census_registry.py:147` の `pipeline-metrics.jsonl` 行を現行の書き手（`event=gate_record|gate_item`、`category / recommendation / decision`）に合わせて `category="event", enum_fields=("event","category","recommendation","decision")` に直し（旧 P1-05.7 と同一論点 — ここで実装）、`_census_series.py` に gate_record の裁定合計（decisions/gate）と gate_item の `recommendation==decision` 率（週別・category 別。第 4 章の決定 `category=roadmap` を含む — R1-NS-04）を派生列として足す。ADR-0099 Review-when の「~100% sustained」を定数にして照合行を出す。同じ派生列として、`audit.jsonl` の `stage-adopted* / stage-rejected-names / stage-archived-names / direct-archive*` 行と `insight-staged.jsonl` をゲート日で束ねた `gates: [{date, staged, adopted, rejected, archived}]` を出す（新しい書き手は足さず、`gate_record` の `insight_adopted` 等と突合して差があれば例外行）。`gate_item` の様式（`category=roadmap` / `item=<D-ID>` / `recommendation|decision=<A|B|C>` / `recommender=`）は .10 に委ねる（様式は .10）。
- 根拠: `scripts/_census_registry.py:147`（`category="phase", enum_fields=("phase","verdict")` — `pipeline_audit.py` はどちらも書かない。`phase:"auto"|"gate"` は ADR-0085:88-90 の旧スキーマで、`scripts/weekly-pipeline.sh:71-72` が chain 側の書き込み廃止を明記）; `.claude/skills/weekly-gate/SKILL.md:374,396`（gate_record / gate_item の field 一覧）; `docs/adr/0107:27`（pipeline-metrics は「zero automated readers」のまま）; `docs/adr/0099:155-168` Review-when; `tests/test_instrument_census.py:207`（glob の網羅のみでスキーマを検査しない）; RFC-0041 のゲート記録（0/43, 0/29, 0/2, 0/68）は本文に手書き、`scripts/_census_registry.py:173-175`（`audit.jsonl` の decision は窓内 enum 件数のみ、ゲート単位でない）。
- 完了条件: materials の `## Instrument Census` で `pipeline-metrics` が OK（enum 分布に `decision` が出る）; 「decisions this gate / agreement」の 2 値が週次 materials に出て、agreement は category 別（`roadmap` を含む）に出る; RFC-0042 の「週 30 件台に戻るか」と ADR-0111 の反証（30 件 / duplicate 率）がゲート単位の束ねのコマンド 1 本の出力で判定できる（採用率・duplicate 率の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ））; `tests/test_instrument_census.py` に gate_record / gate_item 行の fixture。
- 規模・整合: S / instrument（census 行の修正部分は repair）   出典: OI-03 OI-04 OI-22 WO-07（旧 P1-05.7 を吸収 — R1-OWN Merge-01 / R1-NS M-2）、CP-24（旧 P2-06.4 を吸収 — R4-CUT Merge）   順序: `_census_registry.py` は Entry 1 行の差分なので順序不問（.8 / P1-07.5 と同じ PR でもよい）
- 消費計画: (a) 土曜ゲート Step 1 の briefing と weekly materials でオーナーが毎週読む（ゲート単位の束ねは Step 4 の briefing と RFC-0042 / ADR-0111 の読みで） (b) D-P2-01-2（12-12）の監査で 1 回、以後は ADR-0099 Review-when「~100% sustained」の照合行を四半期 T4 で読む; ゲート単位の束ねは RFC-0042 / ADR-0111 の判定を 4 週ごとに 1 回 (c) 撤去条件: Review-when の発火と D-P2-01-2 の監査結果が `gate_record` に書かれたら照合行を止める（一致率の列は記録として残す）; ゲート単位の束ねは RFC-0042 / ADR-0111 の review-when が満了したら撤去（`gate_record` との突合行は残す）

##### P2-01.2 ゲート所要時間を記録する
- 何を: weekly-gate Step 0 冒頭に `pipeline_audit.py --event gate_start` を 1 行足し、Step 7 の `gate_record` の `ts` との差を .5 の表（`self_regulation_reading.py`）が「所要分」として出す。
- 根拠: `.claude/skills/weekly-gate/SKILL.md:17,365-378`（Step 0 / Step 7 に開始・終了の記録が無い）; `scripts/pipeline_audit.py:35`（`ts` は自動付与）; `docs/adr/0098:122-123` Review-when「> 2h が常態なら再設計」。
- 完了条件: 直近 4 週の gate 所要分が .5 の表に列で出る; 4 週とも ≤ 127 分かを .11 の時刻表と照合できる。
- 規模・整合: S / instrument   出典: WO-05   順序: 10-17 の週（§4.0 の先行列）。SKILL.md の変更（Step 0 の `gate_start`・Step 7）はその週の同梱 PR（R2-GATE Merge-01）
- 消費計画: (a) 土曜ゲート Step 1 で .5 の表の「所要分」列をオーナーが毎週読む（.11 の時刻表 ≤ 127 分と照合） (b) 4 週の読みで ADR-0098 Review-when「> 2h が常態なら再設計」の発火有無を 1 回判定し、所要分を D-P2-01-1 B の負荷系列に含めるかを 11-28 で決める (c) 撤去条件: ゲートが退役（第 5 層）した時。`gate_start` 行は記録として残す

##### P2-01.3 「負荷」を 3 系列で定義し、追補（2026-11）に読み方を書く
- 何を: 負荷の運用定義を (i) 裁定件数（gate_record）、(ii) 読み量（Inventory 5 数 + Exceptions / Ledger / findings の行数）、(iii) ゲート外作業（土曜ゲート commit が触った `rfcs/README.md` 以外のファイル数、whitelist / registry 編集）に分け、`origin: gate` の draft 起票数・前週 draft の処遇・修理 PR 数を**並べて**（合成しない）読む列構成を定義する。8 週表を出す script は .5 の `scripts/self_regulation_reading.py` 1 本で、この項目では script を書かない。読み方（定義ではない — 定義は機械判定しない、`docs/adr/0080:125-129`）は追補（2026-11、P1-03.8、CLAUDE.md §北極星と同 PR）に 1 段落で書く。
- 根拠: `docs/adr/0080:171,262-264`; data repo Inventory 行 08-28→10-02 `decisions-pending 0 · exceptions 5→12 · continuing 7→11`（裁定は 0〜2、読みは単調増）; `origin: gate` の RFC 8 本（0018 / 0019 / 0026 / 0029 / 0030 / 0038 / 0039 / 0049、7 週、全件 done）; `docs/adr/0098:24-30`「8 of 11 weekly F1 findings were about the plumbing itself」。
- 完了条件: .5 の 8 週表に (i)(ii)(iii) と起票 / 修理数の列がこの定義どおりに出て、weekly-gate Step 1 が 1 行で読む; 追補（2026-11）に「負荷」3 系列の読み方が 1 段落（別番号の追補は振らない。`pipeline-metrics.jsonl` の公開可否は → P2-05 GO-11）。
- 規模・整合: S / neutral（定義と追補（2026-11）の段落。読み値と消費計画は .5）   出典: AB-30 WO-01 WO-02 OI-44 AB-45

##### P2-01.5 自己調節の読み値（必要条件の機械宣言 + 代謝の下限）と初回値の固定
- 何を: 週ごとに (i) 裁定数 (ii) `origin: gate` 新規 draft 数 (iii) ゲート commit が触った `rfcs/README.md` 以外のファイル数 (iv) open 台帳数 (v) Exceptions 行数 (vi) insight staged / adopted / archived（+ 層 1 の復元件数 → P2-07）を並べ、「(i)+(ii)+(iii) = 0 が N 週連続」を機械が `self-regulating candidate` と宣言し、十分性はオーナーが `gate_record` に `self_regulation_verdict=` で書く。(vi) の 4 週値（`logs/insight-staged.jsonl` の行数・`.staged/*.meta.json` 数・`audit.jsonl` の `adopted` 件数）はこの script が正本で、`reports/PIPELINE-STATUS.md` の `- ➖ intake — staged 4w: N, pending: M, adopted 4w: K` 行はその出力を写す（名前と件数のみ、判定しない。watchdog 自身は ADR-0085 の terminal artifact 検査に限定 — P2-04.7 を吸収）。「代謝が止まっていない」側の下限（D-P2-01-3）と Re-read trigger を発火させた記録は追補（2026-11、P1-03.8）に 1 段落で書く。初回 6 週分を `docs/evidence/adr-0080/` に固定する。この script が束の負荷読み値コマンドの 1 本で、.3 の 3 系列 + 起票 / 修理数、.2 の所要分、「止まる」列（出所は P1-01.1 の `scripts/freeze_reading.py` の 1 行出力 = 当週の凍結集合への commit 数・改訂 ADR 数・新規 RFC 数を写すだけで、この束では git を読む script を書かない）、.7 の空選択率、.8 の理由列、.13 のロードマップ分の分離 3 列を同じ 8 週表に並べる。初版は 11-28 の週（11-23〜27）に merge し、D-P2-01-1 の選択肢の和集合（B の 3 系列 + 起票 / 修理数 + 所要分）の列を出し、決定後に使わない列を落とす。(vi) の adopted / archived 件数の照合先は P2-05.7 の変化系列（`pipeline/value-layer/changes.json`）。
- 根拠: `docs/adr/0080:175-182`（necessary / sufficiency は人間判断）; git log: 08-29 / 09-12 / 09-19 `e12c09c` `028b776` / 09-26 `32c035f` / 10-03 `e8bcb10` `7a152b0` — 直近 6 週すべてでゲート commit あり（ゼロ介入週 0/6）; data repo never-selected strict 0,0,0・`staging_pending` 0,0,0（09-18〜10-02）、archive candidates 3/1/1/0; data repo `reports/PIPELINE-STATUS.md`（10-10「All scheduled pipelines healthy」）に対し `reports/analysis/weekly-2026-10-02.md:180-184`「staged nothing … `insight-staged.jsonl` の最終行は 09-19」・`.approval-join-state.json`（4 層とも `unchanged_since: 2026-08-28` = hand-edit 検知器の未照合集合 0 件が 08-28 から継続（手編集なし）であって値層の静止ではない — `scripts/value_layer_approval_join.py:238-245`; 静止の読み値は P2-05.7 の変化系列で、identity 09-12・skills 09-12 / 09-19 に変化がある）— 健全表示と代謝停止が同居。
- 完了条件: `scripts/self_regulation_reading.py`（read-only、`### Consumption plan` つき）が 8 週表を出し、`PIPELINE-STATUS.md` の intake 行がその出力と一致する（合成 fixture で 1 件）; `docs/evidence/adr-0080/README.md` に初回値; 下限条件が追補（2026-11）にある; 率の列（6 列）の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）; (vi) の照合先が `pipeline/value-layer/changes.json`（P2-05.7）。10-10 の「入口停止 / 継続」決定そのものは → P0-01（CP-19 / VL-20）。
- 規模・整合: M / instrument   出典: WO-33 WO-34 WO-35 CP-25（P2-04.7 を吸収）、AB-29 OI-20 OI-21（旧 P2-01.4 の参照 1 句 — R4-CUT Prune）   順序: .1 の派生列の後、初版は 11-28 の週（11-23〜27）。依存: P2-05.7（(vi) の照合先）、.9（区間）、P1-01.1（「止まる」列）
- 消費計画: (a) オーナーが土曜ゲート Step 1 で毎週（weekly-gate が 1 行に畳む）、`self-regulating candidate` の宣言行は materials で読む (b) 11-28 の D-P2-01-1（何を負荷と呼ぶか）と D-P2-01-3（下限）で 1 回ずつ、以後は「負荷→0」提案（RFC-0048 等）の審査ごとに 8 週表を読み、十分性の verdict は `gate_record` に `self_regulation_verdict=` で書く (c) 撤去条件: (i)+(ii)+(iii) = 0 が N 週続き verdict が `gate_record` に書かれた後は週次表を止め、四半期 T4（ADR-0101）の読みに畳む

##### P2-01.6 最終人間ゲート日の公開表示（dead-man の読み値）
- 何を: `pipeline_watchdog.sh` が `gate_record` の最新 `ts` を読んで `reports/PIPELINE-STATUS.md` に「last human gate: YYYY-MM-DD（N 週前）」を 1 行足す（公開ミラーに sync される）。行の表示形式と watchdog の fail 行を出すかは D-P2-01-4、停止の是非と N の値は D-P4-01-3。
- 根拠: `scripts/pipeline_watchdog.sh:19-20,185-190`（出力は PIPELINE-STATUS と Notification Center のみ）; data repo `reports/PIPELINE-STATUS.md`（10-10「All scheduled pipelines healthy」、ゲートの有無は出ない）; `docs/CONFIGURATION.md:416`。
- 完了条件: 公開 `PIPELINE-STATUS.md` から最終ゲート日が読める; watchdog の shell テストに 1 件（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））。
- 規模・整合: S / instrument   出典: DE-41   依存: P1-08.1
- 消費計画: (a) 公開 `PIPELINE-STATUS.md` を読む第三者と、土曜ゲート Step 0(c) のオーナー（毎週） (b) 探索的ではない — 「N 週前」の 1 行が D-P2-01-4 B（watchdog の fail 行）の入力、N の値と停止の是非は D-P4-01-3（12-19、P4-01 GO-39） (c) 撤去条件: ゲートが退役（第 5 層）した時に最終ゲート日を固定して行の更新を止める

##### P2-01.7 空選択（満腹信号）の発火率を 4 週系列で読む
- 何を: `scripts/skillsel_reading.py` の既存 `judged-empty` 読みを weekly materials に 4 週系列（judged-empty / judged、`rejected_names` のみの行は別列）で出し、.5 の表に「空選択率」列として並べる。3 週連続 0/460 の現状は `none` 経路が「一度も発火しない abstain 経路」である疑いを含むので、測らずに「第 4 の手段」（空選択エピソード限定の insight 入力）へ進むことも、黙って捨てることもしない。期限: 10-31 の読みは 10-31 の週（§4.0 の先行列）の手動 4 run（`skillsel_reading.py --start/--end`、`:504-505`）で 4 週表を作り `docs/evidence/` に置く; materials（`weekly-analysis.sh`）への配線は 11-28 の 2 回目の読みまで。
- 根拠: `docs/adr/0081:67`「judged-but-empty selection injects no skill bodies (an empty selection is a judgment, not a failure)」; `config/prompts/skill_selection.md:19`「If no skill applies, return only the word `none`」; `scripts/skillsel_reading.py:267,276`（`judged-empty` を数える読みは既にある）; data repo `reports/analysis/weekly-2026-09-18.md` / `09-25` / `10-02`「0 judged-empty」（10-02 週は Enforcement 460/460）; `docs/adr/0080:179-180`「a satiety signal, a novelty judge — is in-scope repair」。
- 完了条件: materials の `## Instrument Census` 近くに 4 週系列の行; 2026-12 までに ADR-0081 の dated note（空選択は満腹信号として機能しない）か RFC（空選択エピソード限定の insight 入力 — capability-growth として第 5 章側で審査、読みが出るまで実装しない）のどちらか 1 つが存在。
- 規模・整合: S / instrument   出典: R1-OWN-01（.5 の表に列を足す）   順序: 10-31 の手動 4 run は .5 より前で、.5 の初版 PR（11-28 の週）がこの系列を「空選択率」列として取り込む。依存: P0-01 の insight 継続
- 消費計画: (a) オーナーが 10-31 と 11-28 の土曜ゲートで (b) 2 回の読みで「0 が続く → ADR-0081 に dated note を書き .5 の候補から外す」「>0 → RFC を起票」を決める (c) 撤去条件: その 2 回で決めたら系列は撤去（結果は note か RFC に残す）

##### P2-01.8 `publish_failed` の理由列（RFC-0029）を census の enum に入れ、削除済み target の再試行ループを読む
- 何を: `scripts/_census_registry.py` の `skill-selection-*.jsonl` 行の `enum_fields` に `failure_reason` と `http_status`（値は既に enum / int、RFC-0029 の列）を足し、週次 census の分布行で「同一 `reply_key_sha256` が 2 セッション以上 `http_status: 404` + `unknown` で繰り返す」形（相手が投稿を消した target への再試行ループ）を読めるようにする。.1 / P1-07.5 と同じ PR。自動退役の拡張は提案しない（404 を退役コードに含めるかは決定として起票）。
- 根拠: `src/contemplative_agent/adapters/moltbook/publish.py:114-133`（`publish_failure_of`: 429 → `rate_limited`、4xx + "parent comment" → `parent_rejected`、transport → `transport`、他は `unknown`。`http_status` は常に残る）; `adapters/moltbook/reply_handler.py:254-276`（dedup key を退役させるのは `parent_rejected` のみ、`unknown` は「conditions of the moment … stay retryable」）; `rfcs/0038:27-28`（404 は parent 拒否と「投稿そのものが消えた」の両方の形）; `scripts/_census_registry.py:174-176`（skill-selection の enum は `kind / verdict / enforced / publish_status / temperature / decision_reason` — `failure_reason` も `http_status` も数えない）。ループの発生は未観測（推測）。
- 完了条件: census の合成 fixture で `failure_reason` の分布が出るテスト 1 件（`tests/test_instrument_census.py`）; 読み値 1 行が weekly materials の `## Instrument Census` に出る。
- 規模・整合: S / instrument   出典: R2-PLAT-05   順序: 着手週。`_census_registry.py` は Entry 1 行の差分なので .1 / P1-07.5 との順序は不問（同じ PR でもよい）。注: P1-07.4（取りこぼし件数の 1 回読み）は後の週にあるので、現行の enum で先に入れ、P1-07.4 が入ったら照合する
- 消費計画: (a) 土曜ゲートが census の分布行で読む（毎週） (b) 同一 `reply_key_sha256` が 2 セッション以上 404 + `unknown` なら、404 を退役コードに含めるかをオーナーが決める（決定として起票。自動退役の拡張は提案しない） (c) 撤去条件: 8 週 0 件なら列は残して読みを止める（費用 0）

##### P2-01.9 新設する率の読みに Wilson 区間を必須にし、帯・閾値は区間で判定する
- 何を: 本ロードマップが新設する率の読み（.5 の 6 列、P2-07.2 の 3 軸、P1-05.2 の帯照合、P3-06.9 の (a)(b)(c)、P3-01.3 の環境応答率、P3-04.8 の保持率 / 語彙率、P1-15.2 の P / R）はすべて `scripts/_stats.wilson_ci` を共有し、「帯内 / 帯外」「閾値未満」は区間で判定する（点が帯内でも区間が帯をはみ出せば「判定不能」と出す）。分母が 10 未満の行は率を出さず件数だけを出す。各項目側は「区間は P2-01.9 の規則」の 1 句で参照する。
- 根拠: `scripts/_stats.py:7-13`（2 本の手書き区間がテストで先に乖離した経緯、ADR-0097 の `recall@5 >= 0.9` 用）、`:24-43`（Wilson、分母 0 で None）; import 元は `scripts/retrieval_recall_measure.py` と `scripts/skillsel_reading.py` の 2 本だけ（grep）; `scripts/confusion_pair_reading.py` / `observation_ledger.py` / `_census_series.py` に区間 0 件; data repo `pipeline/comment-outcomes/comment-outcomes-2026-10-02.json`: skill 36 件の `injected_comments` 中央値 11、10 未満が 18 件; `docs/adr/0080:206-208`（単一スカラー化は禁じるが率の解像度は求めていない）。
- 完了条件: 上記 7 項目の script が `_stats` を import する（grep で 7 本以上）; render / materials の率の列に区間が併記される; `tests/test_observation_ledger.py` に「区間が帯をまたぐ → 判定不能」の 1 件。
- 規模・整合: S / instrument   出典: R2-STAT-02、R4-XREF Fix-02   順序: 10-31 の週（§4.0 の先行列、P1-15.2 と同じ週）。注: 読みの解像度であって新しい判定者ではない
- 消費計画: (a) 土曜ゲートの人間が各読みの区間つき行を読む（既存の cadence のまま） (b) 「2 週連続」「N 週連続 0」型の規則（P1-03.9）は区間で読む (c) 撤去条件: 当該読み値の撤去と同時（独立の計器ではない）

##### P2-01.10 weekly-gate に Step 1c「当週のロードマップ決定」と `category=roadmap` の記録様式を置き、ロードマップ全文の凍結版を repo に commit する
- 何を: (1) §0〜§5 と付録 A / B の全文を採択日つきの凍結版として `docs/plans/roadmap-2026-10/`（`ROADMAP.md` + `decisions.md` = §4.0 の表と §4.1 の全文。要約列は切らない — `gate_item` には `decision=<A|B|C>` しか残らないので、選択肢の中身を repo から引けるようにする）に 10-17 の週（§4.0 の先行列）の SKILL 同梱 PR と同時に commit する（P0-01.8 の T4 行と P1-01.7 はこの PR で `ROADMAP.md` が repo にある前提で読む。表の先頭行に `ROADMAP-2026-10` = ロードマップ採択そのもの）。`decisions.md` には「材料（項目 ID・ファイル・コマンド）」の列を 1 本置き、Step 1c はここから材料の所在を引く（例: D-P0-02-1 ← Step 1c の D-P0-02-1 行の照合コマンド = `rfcs/0046:255` の for ループと `submolt-scope-2026-10-14.jsonl` の `scale: "score4"` の確認; D-P0-01-2 ← P0-01.7 の Summary 行と `covered_by`）。凍結版 = 10-16 時点の最終版で、以後に採用した分は `decisions.md` の dated 節に足し、`ROADMAP.md` は書き換えない。生成器（scratchpad）から repo へ移すのはオーナーの対話セッション。公開 repo なので、同梱 PR のセッションで weekly-gate Step 6d の 3 項目（秘密・資格情報・個人情報・ローカル絶対パス / 未公開の外部固有名 / untrusted な材料からそのまま流れ込んだ文字列）を `ROADMAP.md` に当てて機微点検し、結果を commit 本文に 1 行残す（新しい仕組みは作らない。私的参照 = §5 横断の資金の行・旧チャットの日付・`/mnt/project-files/knowledge/`・CONTEXT-FROM-CHATS への言及は、残すか言い換えるかをオーナーが決める）。11-28 の熟慮 5 件は追補（2026-11）の 1 PR に結ぶので「熟慮 ≤ 3 / ゲート」の例外とし、11-28 の週（11-23〜27）に Claude Code が 4.1 本文と材料の所在を 1 枚にまとめて Step 1c の前段に置く。(2) `weekly-gate/SKILL.md` に Step 1c「当週のロードマップ決定」: ゲート日（= `{end-date}` + 1 日。`{end-date}` は金曜）の行を `decisions.md` から引き、Step 1b の規律で選択肢・推奨・材料の所在を提示し、1 件ずつ `pipeline_audit.py --event gate_item --field category=roadmap --field item=D-… --field recommendation=<A|B|C> --field decision=<A|B|C> --field recommender=<model-id> [--field reason=…] [--field decided_at=…]` を打つ（熟慮は `reason` 必須、遡及分は `decided_at`）。.1 の census / 派生列はこの様式を読む（様式の正本はここ）。同じ PR に P1-12.2 の暫定 1 行（Step 6b と `docs/runbooks/constitution-amendment.md` の裁定段に「却下の前に staged ファイルを `$MOLTBOOK_HOME/.rejected/` へ cp」、P1-12.2 の着手 2027-01-09 まで）が同乗する。
- 根拠: `.claude/skills/weekly-gate/SKILL.md:89-107`（Step 1 の Decision inventory は staging / dead code / retire / docs の区分のみ）、`:393-399`（`gate_item` の template: `category="insight|identity|deadcode|retire|docs"`、`decision="adopt|reject|hold"`）; `scripts/pipeline_audit.py:34-46`（予約 key は ts / run_id / event のみ → `category=roadmap` / `recommender` / `reason` / `decided_at` は今日でも書ける）; 第 4 章冒頭の記録規則は「SKILL.md の様式」と言うが様式が無い; 日付 → D-ID の対応表は生成器（scratchpad）にしか無く、repo 内の置き場は草案に無い。 `scripts/weekly-pipeline.sh:155`（`END_DATE="$YESTERDAY"` = 金曜。§4.0 と `decisions.md` の行は土曜）; `SKILL.md:326-348`（Step 6d が点検するのは `rfcs/` の未 commit 起票だけ）、`:404-405`（Out of scope: code 修理の適用はゲートでしない）。
- 完了条件: 10-17 の `pipeline-metrics.jsonl` に `category=roadmap` の `gate_item` ≥ 5（遡及 3 を含む）; `tests/` に template の field 集合を固定する 1 本（.1 の fixture と共用。`{end-date}` 10-16 → ゲート日 10-17 の行を引くケースを 1 本含む）; SKILL.md に Step 1c; `docs/plans/roadmap-2026-10/` に全文（`ROADMAP.md`）と `decisions.md` があり、`decisions.md` の各 D-ID 行に選択肢の全文と材料の列がある; 機微点検の結果（Step 6d の 3 項目、残す / 言い換えた私的参照の件数）が commit 本文に 1 行。
- 規模・整合: S / neutral   出典: R2-GATE-01、R3-FUT Fix-01、R3-TIME Fix-03、R4-COLD Fix-02 / -03 / -04 / -05、R4-ONEWAY Fix-08、R4-XREF Fix-16 / -17   順序: 10-17 の週（§4.0 の先行列）の SKILL.md 同梱 PR（.2 / .11 / .12〜.14 / P0-01.8 / P1-04.16 / P1-05.1 の Step 6g と同 PR。P1-12.2 の暫定 1 行も同乗）。注: `approver` は D-P1-12-2（2027-01-09）の後に足す; .1（読み手）と P1-09.14（`docs/plans/` 凍結の例外行、12-05 の週）はこの PR の後に入る参照元

##### P2-01.11 土曜の時刻表（chain 終了・watchdog・triage tick・Ollama guard 窓）を SKILL Step 0 に書く
- 何を: `weekly-gate/SKILL.md` Step 0 冒頭に時刻表 5 行 — chain 期待終了 ≤ 12:00 / 遅延時の deadline（`CHAIN_DEADLINE_SECONDS`）/ watchdog 12:30・13:30 / triage tick 14:07 / Ollama guard 窓 13:00–16:45・19:00–22:45 — と「Step 6d の commit は 14:07 より前」を書く。Ollama を使う読み（shadow / IPD / null pair: P0-07.1 / P3-03.2）は平日の guard 窓で前日までに取る（§0 の配分規約に同じ 1 文）。
- 根拠: `config/launchd/com.moltbook.weekly-pipeline.plist`（土 09:00）、`scripts/weekly-pipeline.sh:133`（`CHAIN_DEADLINE_SECONDS=10800 # 09:00 → 12:00`）、`:129`（headless 1 セッション 5,400 s）; `config/launchd/com.moltbook.watchdog.plist:33-45`（土 12:30 / 13:30）; `.claude/skills/weekly-report/SKILL.md:15`（task-triage loop の土 14:07 tick が Step 6d で commit した起票を読む）; `scripts/ipd-two-arm.sh:46-70`（JST 0/6/12/18 の各 60 分後から次の窓の 75 分前までしか腕を起動しない = 土曜に空く窓は 13:00–16:45 / 19:00–22:45）; SKILL.md Step 0〜7 に時刻の記述が無い（`grep -c "12:00\|14:07\|JST"` = 0）。14:07 tick の意味は harness 側（読めない）で `weekly-report/SKILL.md:15` の 1 行のみ（推測を含む）。
- 完了条件: SKILL.md Step 0 に時刻表 5 行; .2 の所要分が 4 週とも ≤ 127 分（14:07 − 12:00）で読める。
- 規模・整合: S / neutral   出典: R2-GATE-02   順序: 10-17 の週（§4.0 の先行列）の SKILL.md 同梱 PR（.10 / .2 と同 PR）。注: P0-07.1 / P3-03.2（guard 窓で走る読み、10-31 の週）はこの時刻表を読む参照元

##### P2-01.12 束を閉じる記録（閉じ表）と、ロードマップ文書自身の退役条件
- 何を: .10 の `docs/plans/roadmap-2026-10/` に `decisions.md` と並べて束の閉じ表を 1 枚置く（39 行、列 = 束 / 状態 open・closed・moved-to-§5 / 閉じた日 / 証跡 commit sha / 未達で §5 の延期行か RFC に移した項目）。束を閉じるのは土曜ゲートで束の完了条件のコマンドを回して満たしたときだけで、同時に `gate_item category=roadmap item=<束ID> decision=closed` を 1 行打ち、閉じ表の行は Step 6d の commit に含める（満たせない項目は §5 の延期行か RFC 起票のどちらかを行に書く。黙って消さない）。2027-01-30 のゲートで、§4.0 が 2〜3 月の土曜（02-06〜03-06）に配った決定を遅れに合わせて ≤ 5 件・熟慮 ≤ 3 のまま配り直す。表の冒頭に退役条件 1 行「39 束がすべて closed か moved-to-§5 になった週、または P4-02 の最終 sync の早い方で凍結し、以後は追記しない。次のロードマップは別の日付ディレクトリに起こす」。実装 commit と項目の結び方は D-P2-01-5（推奨 B: RFC は起票せず、P1-13.3 の trailer 語彙に `Roadmap: <項目 ID>` を足して実装 commit を結び、並行セッションの lease は claims の自由ラベルで取る。`claims.py` が `RFC-NNNN` 以外の ID を受けるかは harness 側で未確認 — 対応は P2-03.1 の要求節）。決定前でも 10-10 の作業から実装 commit には暫定で `Roadmap: <項目 ID>` を付ける（D-P2-01-5 = A / C なら以後止め、付いた trailer は残す — B を採らなければ無視されるだけで可逆）。
- 根拠: 束を閉じる手順は §0・各 Phase 冒頭・§4 の記録規則のどこにも無い（「閉じる」は P3-02.2 / .7 など個別項目の中だけ）; 証跡の唯一の置き場 `gate_item category=roadmap`（.10）は決定の記録で、`$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl` は private（`scripts/sync-research-data.sh` に `pipeline-metrics` の語 0 件）; 停止リスト（P1-01.3）は機構層の残作業だけで 39 束を覆わない; `CLAUDE.md:139,154`（pending の正本は `rfcs/`、lease は `claims.py claim RFC-NNNN`）— 束を RFC にすると .5 の「新規 RFC 数」の列（P1-01.1 の出力を写す）に 39 本が流れ込む; D-P2-01-5 の期限 10-31 より前に 10 月の実装 PR 群（P0-03.1、10-17 の SKILL 同梱 PR と削除 PR、10-24 の P0-03 / P0-04 と先行項目）が入る。
- 完了条件: 閉じ表が 39 行で存在し冒頭に退役条件の 1 行; SKILL.md Step 1c に「束の閉じ」の 1 句; 閉じた束の行に証跡 sha と `gate_item ... decision=closed` の対応; D-P2-01-5 の決定が `gate_item category=roadmap` に残り、10-10 以後の実装 commit に暫定の trailer `Roadmap: <項目 ID>` が付いている（B なら継続し、P1-13.3 の trailer 表に `Roadmap:`、CLAUDE.md 残課題節に「ロードマップ項目は RFC にしない、trailer で結ぶ」1 行。A / C なら以後止める）。
- 規模・整合: S / neutral（新しい計器・判定者は作らない。読むのは Step 1c と T4 四半期で、消費計画は書かない — 計器ではない）   出典: R3-FUT-01、R3-HRN-05、R4-COLD Fix-12、R4-XREF Fix-03 / -17   順序: .10 と同 PR（10-17 の週の SKILL 同梱 PR。P0-01.8 の T4 行も同 PR）で Step 1c の 1 句、閉じ表は .10 の凍結版の commit と同時。注: 閉じの前提は P1-01.3（機構層の束は停止リストの空）; trailer 語彙は現行の形（暫定）で書き、P1-13.3 の trailer 表（12-12 の週）が入ったら更新; claims の対応は P2-03.1 の要求節（10-24 の週から）; P1-09.14（例外行、12-05 の週）は参照元

##### P2-01.13 ロードマップの執行分を北極星の負荷系列とゲート所要分から分けて読む
- 何を: (1) .10 の Step 1c の前後に `pipeline_audit.py --event roadmap_start` / `roadmap_end` を 1 行ずつ打ち、.5 の 8 週表に「うちロードマップ分」の 3 列（`category=roadmap` の決定数・Step 1c の分・ロードマップ由来の commit 数）を足す; (2) ロードマップ由来の commit は trailer `Roadmap: <項目 ID>` で数える（暫定（10-10 から）。D-P2-01-5 = A / C なら trailer を止めた週から commit 数の列は空にする）; (3) .5 の candidate 条件 (i)〜(iii) はロードマップ分を除いた列で計算し、除いた分は同じ行に並べて出す（合成しない）; (4) 追補（2026-11）の「負荷」の読み方段落（.3 / P1-03.8）に「ロードマップ執行期間（`decisions.md` の D-ID に対応する `gate_item category=roadmap` がそろうまで）は分けて読み、そろった週に分離列を撤去する」を 1 文。
- 根拠: .5 の candidate 条件（(i) 裁定数 + (ii) `origin: gate` 新規 draft 数 + (iii) ゲート commit の触ったファイル数 = 0 が N 週連続）と .2 の所要分（≤ 127 分）/ `docs/adr/0098-weekly-single-session-and-triage-delegation.md:122`（「The Saturday session routinely takes > 2h」で再設計）; .10 は Step 1c を同じ土曜ゲートに置き `gate_item category=roadmap` を同じ `pipeline-metrics.jsonl` に書く; §4.0 のロードマップ決定は 12-26 までに 55 件（うち 10-10 の遡及 3）、2027-01 に 19 件、2027-02〜03 に 24 件、2027-Q2 に 1 件; `rfcs/*.md` の `origin:` 語彙は `gate` / `idea` / `instrument` でロードマップ由来の値が無い。
- 完了条件: 合成 fixture（ロードマップ行 2・通常行 1）で candidate 判定がロードマップ行に左右されないテスト 1 本; .5 の初版（11-28 の週）で 8 週表に分離 3 列; SKILL.md Step 1c に開始・終了の 2 行（10-17 の週の同梱 PR に同乗）; 実装 commit に暫定（10-10 から）の trailer `Roadmap: P2-01.13`。
- 規模・整合: S / instrument   出典: R3-TIME-01、R4-XREF Fix-02 / -03 / -13 / -14 / -17   順序: (1) の SKILL 2 行は 10-17 の週（§4.0 の先行列）の SKILL 同梱 PR（.10 と同 PR）、(3) の分離 3 列は .5 の初版 PR（11-28 の週）、(4) の 1 文は P1-03.8 の追補（2026-11）の PR。注: (2) の trailer は暫定（10-10 から）で書き、P1-13.3 の trailer 表と D-P2-01-5（10-31）が入ったら更新
- 消費計画: (a) オーナーが土曜ゲート Step 1 で .5 の 8 週表の分離列を毎週読む (b) 11-28 の D-P2-01-1 / D-P2-01-3 の読みで 1 回「ロードマップ分を除いた値」で定義と下限を置く (c) 撤去条件: `decisions.md` の全 D-ID に対応する `gate_item category=roadmap` がそろった週に分離列と `roadmap_start` / `roadmap_end` を止める（行は記録として残す）

##### P2-01.14 `decisions.md` に「遅れたとき」の節（日付拘束の表・繰り越し規則・縮退順）を置く
- 何を: .10 の `docs/plans/roadmap-2026-10/decisions.md` に節「遅れたとき」を置く — (1) 日付拘束の表（項目 / 決定 ID・動かせない理由・逃したときの既定 =「hold で記録し次回の拘束日へ」か「実行しない」）; (2) 欠席した週の規則: 日付拘束の行だけ次の土曜に繰り上げ、他は 2027-03-13 / 03-20 / 03-27 の空き枠（§4.0 の繰り越し枠）を先に使って後ろへ送る、既定可は一括処理回へ、熟慮は 1 ゲート ≤ 3 を超えない。10-10 の 3 件に 10-10 時点の決定（`gate_record`・commit）が無ければ欠席と同じに扱い、日付に縛られる D-P0-01-1 と D-P0-03-2 は 10-17 に打ち、既定可の D-P1-04-1 を 2027-03-13 の空き枠へ送る（P0-03.1 が未着手なら 10-17 の週に入れる）; (3) 縮退順（遅れが 2 ゲートを超えたら後ろから第 5 章の延期行へ移す候補を Step 1c が提示し、決めるのは人間）: 残す順に P0 の修理 → 停止リストの行 → 北極星の読み値（P2-01）→ 公開データの撤回経路（P3-05.14 / .19）→ 研究（P3-01〜P3-06）→ 文書の同期（P1-09）→ 兄弟 repo（P1-11）; (4) Step 1c の template に「前週から繰り越した行: N（ID）」の 1 行。この節は `ROADMAP-2026-10` 行の決定に含める（新しい D は振らない）。
- 根拠: §0 の「期限は『この順で進めるとき無理のない時期』であり締切ではない」; §4.0 の決定 ≤ 5 に対し 10-10〜12-26 は 55 / 60（うち 10-10 の遡及 3）、2027-01 は 19 / 20 で 1 ゲート欠けると 5 件があふれる; 本文書は 10-10 当日に作られたので、10-10 のゲートで 3 件が決まった記録があるとは限らない; 日付拘束は各束に散在（10-15 の scan ログ → 10-17、10-31 の憲法改正 due、P3-04.1 の snapshot prune ≈ 11-01、P3-01.2 / P3-03.1 / .2 の改正 due 前、D-P0-06-1 の Python 3.10 EOL 2026-10 ほか）; ゲート不在への備えはエージェント側（D-P2-01-4、D-P4-01-3）にしか無い。
- 完了条件: `decisions.md` に節と日付拘束の表（10 行前後）; SKILL.md Step 1c に繰り越し行（10-17 の週の同梱 PR に同乗）; 最初に欠席が起きた週の `gate_item` に `decided_at` と繰り越し先が残る。
- 規模・整合: S / neutral   出典: R3-TIME-03、R4-COLD Fix-08、R4-XREF Fix-13   順序: 10-17 の週（§4.0 の先行列）の SKILL 同梱 PR（.10 と同 PR）


**依存**
- ADR-0101（新計器の `### Consumption plan`）、ADR-0099 / RFC-0010 の Review-when
- P1-01.1 / P1-01.4（.5 の「止まる」列は `freeze_reading.py` の出力を写す。凍結判定は P1-01）
- P1-03.8（ADR-0080 追補（2026-11）の受け皿: .3 / .5 / .13 (4) の段落）、ADR-0081（.7 の dated note）
- P0-01（RFC-0042 の 10-10 読み → .5 の初回値の固定。.7 は insight 継続が前提）
- P2-05.7（.5 (vi) の照合先 = 値層の変化系列、11-14 の週）、P2-02 D-P2-02-1（11-28: headless セッション数・所要時間を負荷系列に含めるか）
- P1-07.5（.1 / .8 と同じ census 規則。`_census_registry.py` は Entry 1 行の差分なので順序不問）、P1-08.1 / P1-08.3（.6 の watchdog shell テストの macOS セルと harness）
- D-P4-01-3（12-19: オーナー不在 N 週の停止の是非と N の値。D-P2-01-4 は表示形式だけを持つ）
- 後の週に入るもの（現行の形で書き、入ったら更新）: P1-13.3（trailer 語彙 `Roadmap:`: .12 / .13 は暫定（10-10 から）の trailer で書く、D-P2-01-5）、P2-03.1（harness 側の claims 対応: .12。要求節は 10-24 の週から）、P1-05（baseline 批准・台帳の機械化: .5 の open 台帳数は現行の台帳で数える）、P1-07.4（.8 の取りこぼし側の読み）
- → 参照元: P2-04（PIPELINE-STATUS の intake 行は .5 の出力を写す）、P4-01（D-P2-01-3 の下限 = 検討イベント B。.6 の行は D-P4-01-3 の N の入力）、P2-07.2 / P1-05.2 / P3-06.9 / P3-01.3 / P3-04.8 / P1-15.2（.9 の区間規則）、P1-03.9（.5 の候補宣言行に基礎率を併記）、P0-01.8 / P1-04.16 / P1-05.1 / P1-12.2（.10 / .11 / .12〜.14 と同じ 10-17 の SKILL PR）、P1-01.7 / P0-01.8（読み元 = .10 の `docs/plans/roadmap-2026-10/ROADMAP.md`）、P1-01（`freeze_reading.py` が .12 の `Roadmap:` trailer を別系列に出す）、P1-09.14（`docs/plans/` 凍結の例外行 = `roadmap-2026-10/`: .10 / .12 の後に書く）、P2-05 GO-11（gate_record / gate_item の公開可否）、P1-12（`gate_item` に approver / reason 欄を後から足す）、P2-07（層 1 の復元件数を .5 の列に足す）、P2-06.1（節別行数を .3 の読み量に足す）、P0-07.1 / P3-03.2（.11 の guard 窓の時刻表を読む）


#### P2-02 Claude Code 依存の決着（headless 週次セッションの位置づけ）
- 狙い: ADR-0080 の 08-26 追補 §A は「オーナーと Claude Code の日常的関与なく自己調節」を機構層の完成条件にする（`docs/adr/0080:164-167`）一方、無人週次チェーンは毎週 `claude -p` を 1 回起動し、`claude` 不在では起動すらしない（`scripts/weekly-pipeline.sh:248,352`）。この同居を「機構層の一部」か「オーナーの作業環境」かに決めないと、「完成」の定義と RFC-0048 等の「負荷→0」提案の審査基準がぶれる。
- 期限・順序: 着手 2027-02-06 の土曜ゲート（§4.0）。期限 2027-Q1。決定は 2026-11-28 の土曜ゲート（D-P2-02-1、追補（2026-11）の材料）、実装は着手週から。.1（文言の二分）は追補（2026-11、P1-03.8）の 1 段落として決定と同 PR。.2（instruments-only）と .3（モデル ID 記録）は選択肢に依らず要る（B / C なら .2 は必須）。.4 は README 整備（P1-09）と同時でよい。shell テスト（.2 / .5 / .6 / .7 / .8）は P1-08.1 の後。`weekly-pipeline.sh` を触る .2 / .3 / .5 / .6 / .7 / .8 / .9 は P2-04.13 PR-A の後（PR-A は verb 集合を変えない）で、`chain_start` の欄は .3 / .5 / .7 を、`claude -p` の起動行は .3 / .8 / .9 を同じ PR に寄せてよい。決定は D-P2-02-1（11-28）。
- 束の完了条件:
  - ADR-0080 追補（2026-11、P1-03.8）に Claude Code の関与の二分 + 選択 A/B/C の段落が着地し、CLAUDE.md §北極星と CYCLES.md Operating model が同 PR で同期
  - `MOLTBOOK_PIPELINE_STAGES=valuelayer,deadcode,docsscan` で `claude` 不在でも `chain_end=ok` になる shell テストが緑
  - 直近 1 週の audit `chain_start` と文書 Inventory 行に同じ `writer: <model>` / `claude_version=` が出て、`chain_start` に入力の来歴 5 欄（.7）、`stage_result stage=report` に envelope の数値欄（.8）が出る
  - README「What it will not do」/ `.zenodo.json` / CLAUDE.md の外向き先の列挙が一致し、P1-10.14 の固定集合と照合される
  - `docs/runbooks/weekly-chain-rerun.md` が存在し `docs/runbooks/README.md` の表に載る

##### P2-02.1 「Claude Code の関与」を二分して ADR-0080 に追補する
- 何を: ADR-0080 追補（2026-11、P1-03.8）の 1 段落として関与を (i) 修理・判断のための対話セッション（→ 0 にする対象）と (ii) 無人の読み手セッション（`claude -p`。許容するなら件数・所要時間を P2-01.3 の負荷系列に含める）に分け、D-P2-02-1 の選択を同じ段落に記す（別番号の追補は振らない）。CLAUDE.md §北極星（同 PR 規則）と CYCLES.md「program workers」を同期する。
- 根拠: `docs/adr/0080:164-167`; `CLAUDE.md:73`; `scripts/weekly-pipeline.sh:3,91`（「ONE claude session」）; `docs/CYCLES.md:39-41,54-55`; 修理も harness の task-triage loop（土 14:07、`weekly-pipeline.sh:11-13`）= Claude Code セッション。
- 完了条件: 追補（2026-11）に 1 段落（CLAUDE.md §北極星との同 commit は P1-03.8 の完了条件）; RFC-0047 / 0048 の審査記録がその区分を引用する。
- 規模・整合: S / neutral   出典: AB-31 WO-09

##### P2-02.2 instruments-only モード（report 無しでも決定論段を完走）
- 何を: `report` が STAGES に無い、または `--skip-report` で canonical report が無い場合に `REPORT_ABSENT` を reason に記録して value-layer / dead-code / docs-scan / never-selected / confusion / comment-outcomes を続行する分岐を足す。promote / ledger / spawn は report がある場合だけ。
- 根拠: `scripts/weekly-pipeline.sh:135`（STAGES 既定）、`:248`（preflight が `claude` を必須にする）、`:496-500`（report 不在で exit 1）、`:26-27`（`--skip-report` は既存 report 前提）。
- 完了条件: `tests/test_weekly_pipeline_*_shell.py` に「`claude` 不在 + `MOLTBOOK_PIPELINE_STAGES=valuelayer,deadcode,docsscan` で chain_end=ok、reason に REPORT_ABSENT」の 1 件（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; watchdog が「report 欠報」と「instruments 欠報」を別行で出す（→ P2-04）。
- 規模・整合: S / repair   出典: WO-10   順序: P2-04.13 PR-A の後。依存: P1-08.1

##### P2-02.3 書き手モデル ID と CLI 版を文書と監査に残す
- 何を: `claude -p` に `--model` を明示固定し、`chain_start` の audit に `claude_version=$(claude --version)` と `model=` を field で残す。文書の Inventory 行の stamp（`format: instrument-v1 (RFC-0010)`）に `writer: <model>` を加える。
- 根拠: `scripts/weekly-pipeline.sh:256`（chain_start は `end_date` / `stages` のみ）、`:352-362`（`--model` 無し）; `config/prompts/weekly-analysis.md:30`（stamp は format のみ）; `scripts/weekly-analysis.sh:12-14`（model / style 境界の注記は ADR-0099 の散文だけ）。
- 完了条件: 直近 1 週の文書と audit に同じ stamp; モデル更新が縦断読み（RFC-0010 の 4 週読み）の分割点として後から再構成できる。
- 規模・整合: S / instrument   出典: WO-11   順序: P2-04.13 PR-A の後（`chain_start` の field 追加）
- 消費計画: (a) RFC-0010 の縦断読み（4 週読み）をする土曜ゲートの人間と、P3-02 の regime 表を描く時に (b) 探索的 — モデル交代の週を分割点として読めるかを 2027-Q1 の review で継続可否（書き手モデルが変わったときの再走の引き金は P1-07.11 の `docs/runbooks/model-swap.md` のチェックリストの行を参照する） (c) 撤去条件: D-P2-02-1 = B で headless セッションが止まった時（stamp は文書に残す）

##### P2-02.4 外向き通信の全列挙と「cloud なし」の範囲の修正
- 何を: README「What it will not do」に 3 行（agent loop: moltbook.com + localhost Ollama / maintenance: GitHub push + `gh repo view`（可視性照会、`backup-runtime.sh:69`）+ HF upload / program: `claude` CLI for weekly report & evals）を書き、`.zenodo.json` の「no cloud inference anywhere in the pipeline」を「in the agent's own loop」に直す。CLAUDE.md の API コストゼロ原則に「週次セッションのサブスクリプション消費は原則の外」を 1 文足す。
- 根拠: `.zenodo.json:10`; `README.md:102`（`sync-data` を git push とだけ書く）と `scripts/sync-research-data.sh:139`（`hf upload`）; `scripts/weekly-pipeline.sh:91`; `evals/judging.py:246,288`（isolated `claude -p` judge）; サブスクリプション消費の明文は docs/ に無い（grep 0 件、`docs/evidence/rfc-0045/README.md:162` のみ）; `scripts/backup-runtime.sh:69`（`gh repo view … --json visibility`、`gh` 不在なら unknown — 列挙漏れ）。
- 完了条件: 外向き先の列挙が README・`.zenodo.json`・CLAUDE.md で一致し、P1-10.14（`tests/test_shell_egress_allowlist.py` の固定集合）から生成して docs-consistency scan で照合する（broken_link と同じ扱いで差分を出す）。
- 規模・整合: S / neutral   出典: DC-35

##### P2-02.5 週次チェーンの再実行 runbook と入力の縮小
- 何を: `docs/runbooks/weekly-chain-rerun.md`（欠報・途中死・同一週の再実行 `--end-date`・`.private/` quarantine の扱い・サブスクリプション枯渇 / timeout 時）を書き、`WEEKLY_PREV_COUNT` 既定を 3→1 に下げ（台帳が継続を担う RFC-0010 以後、旧 report 3 週分は不要 — 推測）、materials のサイズを `chain_start` に `materials_bytes=` で記録する。
- 根拠: `scripts/weekly-analysis.sh:51`（`PREV_REPORT_COUNT=${WEEKLY_PREV_COUNT:-3}`）; data repo comment-report 09-26..10-02 = 1,877,760 bytes（週 ≈ 2 MB）; `scripts/weekly-pipeline.sh:129`（`WEEKLY_TIMEOUT=5400`）; `docs/runbooks/README.md` の一覧に週次チェーンの runbook が無い。
- 完了条件: runbook が存在し `docs/runbooks/README.md` の表に載る; audit に `materials_bytes` が出る; `WEEKLY_PREV_COUNT=1` でも `tests/test_weekly_analysis_shell.py` が緑（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録） — 同ファイルは Linux で 25 件全 skip の実測）。
- 規模・整合: S / repair   出典: WO-12   順序: P2-04.13 PR-A の後（`chain_start` の field 追加）。依存: P1-08.1

##### P2-02.6 `--tools` 名の黙った脱落を preflight で止める
- 何を: chain の preflight に「`claude` が `WEEKLY_TOOLS` の各名を認識するか」の決定論チェック（C-SCOPE-8 と同じ問い）を入れ、不一致は `PREFLIGHT_TOOLSET_DRIFT` で abort する。
- 根拠: `scripts/weekly-pipeline.sh:117-121`（未知の tool 名は無音で捨てられる）; `tests/test_weekly_pipeline_session_scope_shell.py:349-350,441-442`（`claude` が無い CI では skip）; `.github/workflows/verify.yml` は ubuntu（`claude` 無し）。
- 完了条件: preflight の shell テスト 1 件（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録） — `claude` 不在の CI では走らない）; 不一致週の audit に `PREFLIGHT_TOOLSET_DRIFT`。
- 規模・整合: S / repair   出典: WO-13   順序: P2-04.13 PR-A の後（preflight は `weekly-pipeline.sh`）。依存: P1-08.1

##### P2-02.7 無人週次セッションの入力の来歴（HEAD・branch・dirty・指示書の sha・skill 在庫）を `chain_start` に記録する
- 何を: `chain_start` に `git_head=`（`rev-parse --short HEAD`）・`branch=`・`dirty=`（`git status --porcelain -- scripts/ .claude/skills/weekly-report/ config/prompts/ CLAUDE.md` の件数）・`instr_sha12=`（weekly-report の SKILL.md / `references/diagnosis.md` / CLAUDE.md / `config/prompts/weekly-analysis.md` の連結 sha12）・`skills=`（`.claude/skills/*` の名前と tracked / untracked の印）を足し、`branch != main` か `dirty > 0` か untracked skill ありなら WARNING 行 `PREFLIGHT_WORKTREE_DRIFT`（abort しない — 欠報のほうが損失が大きい）。weekly-gate の `gate_start`（P2-01.2）にも `weekly-gate/SKILL.md` の sha12 と `git_head` を 1 欄ずつ。
- 根拠: `scripts/weekly-pipeline.sh:256`（`audit chain_start end_date= stages=` のみ）、`:123`（`WEEKLY_TOOLS="Read,Glob,Grep,Edit,Write,Skill"`）、`:358`（`--setting-sources project` = CLAUDE.md を読み込む）; `config/launchd/com.moltbook.weekly-pipeline.plist`（`WorkingDirectory {{PROJECT_ROOT}}` = 対話セッションが編集する同じ checkout）; `.gitignore:79-82`（未追跡の project skill を個別に除外 = 手元に未追跡 skill がある、推定）; 指示書は 08-16 以降 `.claude/skills/weekly-report` 12 commit・CLAUDE.md 32・`weekly-analysis.md` 9 で週 1 回以上動く。
- 完了条件: 合成 checkout（feature branch + 未 commit の SKILL.md + untracked skill dir）で 5 欄と WARNING が audit に出る shell テスト 1 本（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; 直近 1 週の audit に 5 欄; 既存テストは不変。
- 規模・整合: S / instrument   出典: R3-HRN-01   順序: P2-04.13 PR-A の後、.3 と同じ `chain_start` 行。依存: P2-01.2（`gate_start`）、P1-08.1 / P1-08.3。注: 未追跡 skill の実在と `Skill` tool が読む範囲は推定（CLI の仕様、未確認）
- 消費計画: (a) 土曜ゲート Step 0 の人間が WARNING 行の有無を毎週読み、P3-02 の regime 表を描くときに `instr_sha12` の変化週を分割点として読む (b) WARNING 1 件で「その週の文書は main 以外 / 未 commit の指示書で書かれた」と記録し、再実行（.5 の runbook）するかを決める; 分割点は regime 表の行になる (c) 撤去条件: D-P2-02-1 = B で headless セッションが止まった時に欄ごと撤去（それまでの行は記録として残す）

##### P2-02.8 週次セッションの終了状態を JSON envelope で読み、「拒否されて空」を理由コードにする
- 何を: 週次セッションを `--output-format json` にし（`result` 本文は既存どおり `.private/` のファイルが正本、log には envelope の数値欄だけ残す）、`stage_result stage=report` に `is_error` / `num_turns` / `duration_ms` / `denials=`（権限拒否の件数。envelope の鍵名は実 CLI で 1 回確認して固定し、無ければ `weekly-session.log` の拒否行の件数で代える）を足す。`is_error=true` は `REPORT_SESSION_ERROR`、`denials > 0` は `REPORT_SESSION_DENIED`（abort しない）。数値欄の抽出は `evals/judging.py::_envelope_numbers` と鍵集合を共有する（`scripts/` から import する経路は D-P1-06-1 に従い、それまでは複製 + 「evals と同じ鍵集合」の一致テスト）。.5 の 8 週表に headless の `duration_ms` / `num_turns` 列（P2-01.5、D-P2-02-1 A の条件「無人の読み手を負荷系列に数える」の出所）。
- 根拠: `scripts/weekly-pipeline.sh:361-362`（`--output-format text > weekly-session.log` — この log の読み手は scripts に 0 件）、`:333-334`（「the 2026-08-29 run was refused and produced zero」= 権限拒否で 0 件の実例。構造ゲートは H2 見出しの有無だけを見る）; 対照 `evals/judging.py:373-374`（同じ `claude -p` の envelope の `is_error` で fail-loud）、`:392`（`_envelope_numbers` が `duration_ms` / `num_turns` ほかを記録）。
- 完了条件: envelope fixture 3 種（正常 / `is_error` / 拒否あり）で audit の reason が分かれる shell テスト 1 本（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; P2-01.5 の 8 週表に `duration_ms` / `num_turns` 列; C-SCOPE-1（`tests/test_weekly_pipeline_session_scope_shell.py::test_c_scope_1_every_session_pins_a_bounded_contract`）は `--output-format` を assert していないので既存テストは不変、`--output-format json` を要求する assert を 1 行足す。
- 規模・整合: S / repair（silent fallback の除去、ADR-0075）   出典: R3-HRN-02   順序: P2-04.13 PR-A の後、.3 と同じ起動行。依存: D-P1-06-1（共有の経路）、P1-08.1 / P1-08.3

##### P2-02.9 週次チェーンの `claude -p` を evals と同じ環境固定（env allowlist・自動更新と非必須通信の無効化）で起動する
- 何を: `weekly-pipeline.sh` の `claude -p` を `env -i` + allowlist（evals の 8 鍵 + `MOLTBOOK_HOME`）+ `DISABLE_AUTOUPDATER=1` + `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` で起動する。2 つの呼び出し口の allowlist が一致するテストを `tests/test_cloud_egress_absence.py`（`claude -p` を名指しする既存テスト）に 1 本足し、.4 の README 列挙に「claude CLI の非必須通信は両呼び出し口で無効」の 1 句。
- 根拠: `evals/judging.py:226-234`（`_JUDGE_ENV_ALLOWLIST` 8 鍵 + `DISABLE_AUTOUPDATER=1` + `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`）と `tests/test_eval_judge_and_snapshot.py:66,74`（evals 側の固定は検査済み）vs `scripts/weekly-pipeline.sh:352-362`（env 指定なし、launchd の env と PATH をそのまま継承）; `src/contemplative_agent/cli/schedule.py:250`（`{{USER_LOCAL_BIN}}` = `~/.local/bin`、自己更新する配置と推定）; `scripts/*.sh` と `config/launchd/*.plist` に `AUTOUPDATER` / `NONESSENTIAL` は 0 件。
- 完了条件: C-SCOPE-1 に env 固定の assert（text-level、ubuntu で走る）— 書き換える既存テスト: `tests/test_weekly_pipeline_session_scope_shell.py::test_c_scope_1_every_session_pins_a_bounded_contract`（起動行の検出に `env` 前置を許す形に）; 両呼び出し口の allowlist 一致テスト 1 本; 直近 1 週の run が成功（認証が落ちないことの実測 1 回、オーナーの手元）。
- 規模・整合: S / repair   出典: R3-HRN-04   順序: P2-04.13 PR-A の後、.3 / .8 と同じ起動行。依存: .4、P1-10.14（egress 目録）


**依存**
- オーナー判断（D-P2-02-1）、ADR-0080 同 PR 規則（CLAUDE.md §北極星）
- P1-08.1 / P1-08.3（CI の 2 セル {ubuntu/3.13, macos/3.13} と shell harness `tests/_shell_harness.py`: .2 / .5 / .6 のテスト）、P1-09（README / CONFIGURATION の同期）
- P2-04.13 PR-A（`weekly-pipeline.sh` の整理が先: .2 / .3 / .5 / .6）
- P1-13 GO-15（1 セッション多役の線引き）
- P1-03.8（追補（2026-11）の受け皿: .1 の段落）、P1-10.14（外向き verb の固定集合: .4 の列挙元）
- P2-01.2（.7 の `gate_start` 欄）、D-P1-06-1（.8 の `_envelope_numbers` 共有の経路）、P1-10.14（.9 の非必須通信も egress 目録に）、P1-07.11（.3 のモデル交代の引き金は `model-swap.md` の行）
- → 参照元: P2-01.3 / .5（.1 の二分で無人セッション数・所要時間を負荷系列に含めるか、.8 の `duration_ms` / `num_turns` 列）、P3-02（.7 の `instr_sha12` 変化週を regime 表の分割点に）、P2-03（`claims.py` / task-triage も Claude Code セッション: D-P2-02-1 で B を選ぶと依存の範囲が変わる）、P2-04（watchdog が .2 の REPORT_ABSENT と instruments 欠報を別に読む）


#### P2-03 私的ハーネス依存を閉じる（claims.py・release skill・パス・inbox）
- 狙い: CYCLES.md は「shared workspace は repo 自身」と宣言する（`docs/CYCLES.md:26`）が、無人チェーンの起票記録（`claims.py`）、修理ループ（task-triage）、台帳の規約（rfc-writer）、release 手順、verify 契約、data repo のパスが `~/.claude/` とオーナーのディレクトリ構成にある。北極星の「自己調節」装置の半分が公開 repo の外にあり、第三者も、オーナー不在時も、運用モデルを再現・検証できない。取り込み / 文書化 / 切り離しに三分して閉じる。
- 期限・順序: 着手 2027-02-13 の土曜ゲート（§4.0）。期限 2027-Q1。.1 の三分類表（決定 D-P2-03-1、2027-02-13、D-P2-02-1（11-28）の後）が先、.2（起票系譜の取り込み）→ .3（inbox 化）はその実装。.4（RFC 規約の転記）と .5（パス env 化）は独立で、.5 は P0-03（絶対パス）と同 PR でよい（`sync-research-data.sh` は P0-03.2 → P0-03.3 → P0-03.16（push 段）→ P2-05.1 の順で、.5 の env 化はその後か同 PR）。shell テスト（.2 / .3 / .5）は P1-08.1 の後。`weekly-pipeline.sh` を触る .2 / .3 は P2-04.13 PR-A の後。ただし .1 の「本ロードマップが harness に要求する変更」節は 10-24 の週（§4.0 の先行列）から書き始め、期日の早い行（P0-03.6 = 10-24、P1-01.6 = 11-28 の後）から埋める（三分類表の残りは着手週 2027-02-13）。
- 束の完了条件:
  - `docs/CONFIGURATION.md`（または `docs/CYCLES.md`）に外部参照の三分類表があり、(A) 取り込み分が実装済み
  - `claims.py` 不在の clone で `weekly-pipeline.sh` が `SPAWN_RECORD_FAIL` を出さず、`rfcs/` の無人起票全件の frontmatter から起票週（run_id）が分かる
  - 無人実行後、本体 `git status --short rfcs/` と data repo の無人 commit の `reports/analysis/` 差分が共に空（inbox は gitignored。P2-05.1 (B) と共通の 1 文）
  - `rfcs/README.md` だけで 49 本の state と昇格の有無が読める（外部リンク不要）
  - `MOLTBOOK_DATA_REPO` を任意パスにして `sync-data` と `weekly-analysis.sh` が通る

##### P2-03.1 外部参照の三分類表と harness 依存境界の ADR note
- 何を: `~/.claude/` 参照（30 種超）を (A) 取り込み: 無人チェーンが実行時に呼ぶもの（`claims.py spawn` → .2）と台帳の最小規約（→ .4）、(B) 外部依存として文書化: `task-triage` / `task-stocktake` / `release-doi` / `jsonld-knowledge-graph` / `verify-bootstrap` は claude-harness の固定 commit リンク + 入出力契約 1 段落、(C) 切り離し: `wiki-harvest` / `wiki-query` / `archify` は「owner-private」列に隔離 — の 1 表にする。ADR 1 本（note 形式）に「必須バイナリ、`claims.py` の入出力、`rfcs/` draft 契約、harness 無しで動く最小構成」を記し、`docs/runbooks/` に harness 無し運用を 1 ページ置く。同じ表に節「本ロードマップが harness に要求する変更」を置く（列 = 項目 ID・harness の対象ファイル・期日・完了の証跡 = harness commit sha と日付）: P1-01.6（task-triage skill への規則同期）、P1-02.1（rfc-writer 規約）、P1-02.2（triage が `next_check` を尊重）、P1-13.3（commit テンプレの trailer。D-P2-01-5 = B なら `Roadmap:` と claims の自由ラベルも）、P0-03.6（harness hook が `config/secret-patterns.txt` を読む）、P1-10.4（hook の二重化撤去）、P0-06.6（release-doi skill のリンク化）。harness 側で本 repo を対象にする定期 job（`triage-ca` の 2 tick ほか）は (B) 文書化の行に名指す（P2-04.3 / P4-02.7 の停止手順がここを引く）。
- 根拠: `scripts/weekly-pipeline.sh:81`; `CLAUDE.md:11,98,151-159,171`; `docs/CYCLES.md:222-225`; `.claude/skills/weekly-report/SKILL.md:157`; `docs/runbooks/README.md:24`（`release-doi`）; `docs/diagrams/README.md:43`（`archify`）; `.claude/verify.sh:4`（`verify-bootstrap`）; ADR-0095 は claims を残したと書くが実装場所と契約は無い。
- 完了条件: 表が repo にあり、clone 先で `weekly-pipeline.sh` のどの段が動くかが文書だけで分かる; (A) の実装 = .2 .4 が merge 済み; 要求節の 7 行それぞれに harness commit sha と日付が入っている（未了の行は期日と空欄）。
- 規模・整合: M / neutral   出典: WO-14 AB-32、R3-HRN Fix-04   順序: 要求節は 10-24 の週（§4.0 の先行列）から書き始め、P0-03.6 / P1-01.6 の行を先に埋める。三分類表の残りは着手週 2027-02-13

##### P2-03.2 起票の系譜を公開 RFC に取り込み、`claims.py` を任意化する
- 何を: pipeline の起票段が draft の frontmatter に `filed_by: weekly-{end-date}-{run_id}` と `producer:`（既に抽出している最初の `path:line`）を書く（本文不変、frontmatter 1〜2 行の追記のみ）。`claims.py` 呼び出しは `PIPELINE_CLAIMS_PY` が実在する時だけの二重記録にし、不在では reason を出さない。
- 根拠: `scripts/weekly-pipeline.sh:81,617-625`（spawn 失敗は `SPAWN_RECORD_FAIL`、`--producer` は既に算出済み）; `.gitignore:48`（`.notes/` = claims.jsonl は非公開）; `rfcs/0049-publish-row-reply-target.md:1-6`（frontmatter は `id / state / state_since / origin: gate` のみ、run_id 無し）; `docs/adr/0098:99-101`。
- 完了条件: `rfcs/` の `origin: gate` 全件（0018 / 0019 / 0026 / 0029 / 0030 / 0038 / 0039 / 0049 + 以後）に `filed_by` があり、`claims.py` 不在の shell テストで `SPAWN_RECORD_FAIL` が出ない（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））。
- 規模・整合: S / repair   出典: WO-15 GO-16   順序: P2-04.13 PR-A の後（起票段は `weekly-pipeline.sh`）。依存: P1-08.1

##### P2-03.3 無人起票を tracked `rfcs/` に直接置かない（inbox + ゲート採番）
- 何を: 起票段の出力先を `rfcs/.inbox/`（gitignored）にし、採番（`next_rfc_number`）・`rfcs/NNNN-*.md` への移動・index 追記を weekly-gate Step 6d の機微点検後に行う。採番が遅れるので .2 の `filed_by` と spawn もその時点に移す。
- 根拠: `scripts/weekly-pipeline.sh:181,560-611`（`$PRIVATE_DIR/tasks-{end}` から採番して `mv` で tracked `rfcs/` へ、commit はしない）; `.claude/skills/weekly-gate/SKILL.md:326-362`（Step 6d が commit）; 土 14:07 の triage（harness）も `rfcs/` に書いて commit する（→ P1-13 WO-16）。
- 完了条件: 無人実行後、本体 `git status --short rfcs/` と data repo の無人 commit の `reports/analysis/` 差分が共に空（P2-05.1 (B) と共通の 1 文 — どちらも「無人が書き、人間が公開に出す」の実装）; `tests/test_weekly_pipeline_diagnosis_scope_shell.py` に inbox 経路の 1 件（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））。
- 規模・整合: S / repair   出典: WO-46   順序: P2-04.13 PR-A の後（.2 と同じ起票段）。依存: P1-08.1

##### P2-03.4 RFC 台帳の最小規約を `rfcs/README.md` に転記する
- 何を: README に 5 行の規約（state 語彙と終端語、blocked の 3 行様式「再開条件 / 照合先 / 成立時」、RFC→ADR 昇格条件 =「本番挙動・スキーマ・ゲートを変える決定が固まった時」、RFC に残すもの = 読み・運用記録）を書き、harness 側リンクは「詳細」として残す。
- 根拠: `rfcs/README.md:7-10`（規約本文を書かないと宣言）; `docs/adr/README.md` は RFC に言及しない（grep 0 件）; 昇格は毎回起きている（0028→ADR-0106、0031→0108、0037→0110、0040→0112、0042→0111、0046→0113）のに条件は RFC ごとの自由記述。
- 完了条件: 外部リンクを辿らずに 49 本の state（done / blocked / draft …）と昇格の有無が解釈できる; P1-02 の索引生成がこの語彙を読む。
- 規模・整合: S / repair   出典: AB-04

##### P2-03.5 data repo / backup repo のパスを env 化する
- 何を: `MOLTBOOK_DATA_REPO`（既定 `$HOME/MyAI_Lab/contemplative-agent-data`）を導入して `sync-research-data.sh` / `weekly-analysis.sh` の 2 箇所を統一し、`MOLTBOOK_BACKUP_REPO` と同型で CONFIGURATION の env 表と `sync-data --help` に「オーナー運用向け。第三者は自分の data repo を指す」と書く。
- 根拠: `scripts/sync-research-data.sh:5`、`scripts/weekly-analysis.sh:31`（上書き不可）; `scripts/backup-runtime.sh:20`（`${MOLTBOOK_BACKUP_REPO:-…}` は上書き可で非対称）; `scripts/weekly-analysis.sh:290-302`（data repo が無いと State Diff が無音で退化）; `docs/CONFIGURATION.md` に DATA_REPO 相当の env が無い（grep 0 件）。
- 完了条件: 任意パスで `sync-data` と weekly-analysis が通る shell テスト（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; env 未設定時のみ従来既定。
- 規模・整合: S / repair   出典: WO-18 CU-31 RD-27   順序: `sync-research-data.sh` は P0-03.2 → P0-03.3 → P0-03.16 → P2-05.1 の後か同 PR。依存: P1-08.1。注: P2-05.8 の export 段の live 木照合ログは `MOLTBOOK_DATA_REPO` 未設定で skip（R2-TST Fix-13）


**依存**
- D-P2-02-1（headless / triage の位置づけ）
- P1-13 WO-16（triage loop が公開台帳に無人で書く主体）、P1-12 GO-21（役割定義の正本が repo 外）
- P0-03（絶対パスの相対化: .5 と同 PR 可。`sync-research-data.sh` の順序は P0-03.2 → P0-03.3 → P0-03.16 → P2-05.1）、P1-09（CONFIGURATION の env 表）
- P1-08.1 / P1-08.3（CI の 2 セルと shell harness: .2 / .3 / .5 のテスト）、P2-04.13 PR-A（`weekly-pipeline.sh` の整理が先: .2 / .3）
- harness RFC-0001 / ADR-0049（「書くのは無人、公開に出すのは人間」）
- → 参照元: P1-02（RFC frontmatter 正規化・索引生成 — .4 の語彙を読む）、P1-01.6 / P1-02.1 / P1-02.2 / P1-13.3 / P0-03.6 / P1-10.4 / P0-06.6（harness 側の完了の証跡を .1 の要求節の行に書く）、P2-04.3 / P4-02.7（`triage-ca` の停止は .1 の (B) 行を引く）、P2-04.23（再構築 runbook の私的 harness 段が .1 を引く）、P2-05.8（.5 の `MOLTBOOK_DATA_REPO` で live 木照合ログを skip）


#### P2-04 無人チェーンの検知面と停止手順（watchdog・sync・ロック・ディスク・ドリル）
- 狙い: ADR-0080 の 08-26 追補 §A の「オーナーと Claude Code の日常的関与なく回る」は、止まったことが人間に見える面が無いと「静かな空回り」と区別できない。watchdog（ADR-0085、pure bash）にループ本体・Ollama・Moltbook・sync・ディスクの検査行を足し、失敗を非 0 終了と `ERROR:` 行に揃える。自動停止・自動修復は入れない（判断は人間。検知結果は P4-01 の検討イベントへ渡す）。
- 期限・順序: 着手 2027-02-06 の土曜ゲート（§4.0）。期限 2027-Q1。.1〜.3（sync の管理下化・非 0 化・完全停止手順）は P4-02 runbook の dry-run（2027-03-06 着手）の前提なので先。watchdog の検査行（.4 / .5 / .10 / .15 / .17）は P2-01 の WO-33（合成 fixture の fault column）と P1-08.3 の harness に乗せ、shell テストは P1-08.1 の後（macOS セルで passed、ubuntu では skip）。.18（`timeout` の解決）は着手週 2027-02-06 の中で .13 PR-A の後、shell テストは P1-08.1 / .3 の後。.19（ドリルの条件・再実施・backup 周期・credentials の保管先）は 1 回で入れる。.13 の chain 整理は P1-06 の凍結判定の前に 1 回だけ、着手週 2027-02-06 に PR-A → PR-B → PR-C の順（P1-04.5 の 2 窓読みは既存の `read_comment_outcomes` を since / until を変えて直接呼ぶので、PR-A を待たない）。P1-10.5 / .13 / .15（P1-10 は 11-14 着手、.5 / .15 は 10-24 の先行列）は PR-A より前に入ってよく、PR-A は挙動不変の移動なので後から rebase する。同一ファイルの順序: `weekly-pipeline.sh` は .13 PR-A（verb 集合を変えない）→ 追加項目（.8 / .9 / .14 / .17 / .18、P2-02.2 / .3 / .5 / .6、P2-03.2 / .3）。P1-10.5 / .13 / .15 は PR-A より前、P1-10.14（verb 集合の不在テスト）は前後を問わない; `weekly-gate/SKILL.md` は Step 単位で所有者を分ける — Step 0(a)(b) = .13（PR-B）、Step 0(c) = .17、Step 7 の `content_hash` = P1-12.1、Step 0 の `gate_start` / Step 1c / 時刻表 = P2-01.2 / .10 / .11（10-17 の週の同梱 PR、§4.0 の先行列）、Step 6d = P2-05.1 — で、.13 PR-B / .17 の SKILL 変更は 10-17 の同梱 PR の後。.21 は着手週。.22 は (b) の release runbook の段だけ 11-07 の週（§4.0 の先行列。P0-06.6 の release runbook の PR に同乗、v2.13.0 の tag（11-14 の決定の後、11-20 まで）の前）、(a) は着手週 2027-02-06; .23 は .19 のドリルと同じ回で、.22 の 1 行・P1-07.11 / .12・P1-08.26 の後。ADR-0010 の partial supersede は .1 が D-P2-04-1（2027-02-06）と D-P2-05-1（12-12）の後に 1 本で起こす。決定は D-P2-04-1（2027-02-06、P4-02 dry-run の前）、D-P2-04-3（2027-03-06、.9 の `late_minutes` を 4 週読んだ後。揃わなければ 2027-03-13 の空き枠へ繰り越す）、D-P2-04-2（2027-02-20）。
- 束の完了条件:
  - `config/launchd/com.moltbook.sync-data.plist` が存在し、文書化された完全停止手順の後に `launchctl list | grep com.moltbook` が空
  - `scripts/pipeline_watchdog.sh` に agent / moltbook / sync-data / disk / launchctl（PID・LastExitStatus）の検査行があり、各行に合成 fixture で ❌ を再現するテストが 1 本ずつある（pure bash + date / stat / launchctl の制約を保つ; harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録）; Depends: P1-08.1）
  - `contemplative-agent sync-data` と `scripts/sync-research-data.sh` が失敗時 rc≠0 かつ `ERROR:` 行（テスト名で固定）
  - `docs/CONFIGURATION.md` にロック表・ログ保持表・TZ/電源前提の 3 節
  - ADR-0108 後の restore ドリルの日付と RTO が `docs/runbooks/runtime-backup-restore.md` の「Drill conditions」節の下に 1 行あり、同じ回に `docs/runbooks/machine-rebuild.md` と `scripts/host_check.sh`（.23）、CONFIGURATION の本番 `install-schedule` 1 行（.22）がある

##### P2-04.1 sync-data job を installer の管理下に置く
- 何を: `config/launchd/com.moltbook.sync-data.plist` を追加し `_OPTIONAL_JOBS` に `sync-data`（既定 daily 05:30、agent セッション外）を足す。ADR-0010 の Sync Timing / Sync Targets を partial supersede する ADR を 1 本起こす（「distill の後処理」→ launchd 日次、targets / exclusions は script が正本。P2-05.1 / .3 の 2 層公開と除外表、P1-09.5 の sync-data 主体の 3 文書一致もこの 1 本の段落に寄せ、ADR-0010 への追補は別に起こさない。決定の反転なので追補ではなく partial supersede）、CYCLES.md row 9 と CONFIGURATION.md を同期。経路の選択は D-P2-04-1。現に毎日 05:30 に走っている経路を installer の管理下に置くだけで、公開範囲は変えない（公開範囲の拡大は P2-05）。
- 根拠: `docs/adr/0010-research-data-sync.md:38`「Runs as a post-processing step of the distill command. No additional launchd plist required」に対し `_run_sync` の呼び出しは `src/contemplative_agent/cli/session_cmds.py:119`（`sync-data` コマンド）のみ / `config/launchd/` は 8 plist で sync-data 無し、`cli/schedule.py:126-185` `_OPTIONAL_JOBS` にも無し / data repo の sync commit は毎日 05:30 JST（`a0428f4` 2026-10-10 05:30:08 +0900）、`docs/CYCLES.md:92` は `com.moltbook.sync-data` を名指し
- 完了条件: `config/launchd/com.moltbook.sync-data.plist` が存在、`tests/test_cli_schedule.py` に install / uninstall の 1 ケース、`install-schedule --uninstall` 後に sync-data plist が無い、ADR-0010 を partial supersede する ADR が存在し（ADR-0010 の Status に範囲）、`tests/test_adr_status_consistency.py::test_partial_supersede_edges_are_reciprocal` が green
- 規模・整合: S / repair   出典: WO-19, DE-09、R3-ADR Merge-02   順序: ADR は D-P2-04-1（2027-02-06）と D-P2-05-1（12-12）の後に 1 本

##### P2-04.2 sync の失敗を非 0 と ERROR 行にし、watchdog が公開ミラーの鮮度を読む
- 何を: `sync-research-data.sh` の push 失敗を `ERROR:` 行 + `exit 1` に（backup と同じ loud 方針）、`_run_sync` は rc≠0 で `sys.exit(1)` とし、rc=0 でも script の stderr（`WARNING:` 行）を透過させる（`capture_output` を外すか rc に関わらず stderr を出す）。watchdog の sync 行は .1 の plist が与える `sync-data-launchd.log` を他 4 行と同じ `log_healthy`（mtime + 末尾 30 行の grep）で読む — data repo の `.git/refs/heads/main` の mtime は使わない（「No changes to sync.」の日は commit が無く ref が動かないので偽 ❌ になる）。
- 根拠: `scripts/sync-research-data.sh:127-129`（`git push --force-with-lease || { echo "WARNING: push failed, will retry next cycle" >&2; }` → 終了コード 0）、`:116`（「No changes to sync.」の日は commit 無し）、`:126,128,154,157`（fetch / push / hf upload / projection の失敗はすべて `WARNING:`）/ `src/contemplative_agent/cli/session_cmds.py:29-43`（rc≠0 でも `sys.exit` 無し; rc=0 のとき stdout のみ print で stderr を捨てる → script の WARNING が CLI 経由ではどのログにも残らず anomaly sweep にも出ない）/ 対照 `scripts/backup-runtime.sh:188-191`（push 失敗で `exit 1`）/ `scripts/pipeline_watchdog.sh:61-77,92-160`（`log_healthy`; 検査対象は distill / insight / weekly-report / weekly-findings / backup のみ）
- 完了条件: 「script 不在・rc≠0 で `sync-data` が rc=1」と「rc=0 でも script の stderr（`WARNING:`）が透過する」のテスト各 1 本、watchdog に `sync-data` 行（`sync-data-launchd.log` を読む）、push 失敗の `ERROR:` 行が翌週 weekly レポートの Log Anomaly Sweep に出ることを合成ログで確認
- 規模・整合: S / repair   出典: DE-10, CU-32

##### P2-04.3 「全部止める」手順を 1 コマンドまたは 1 節にする
- 何を: `install-schedule --uninstall --all` で ollama-restart と sync-data も unload する（テンプレのある plist は管理下へ）か、`docs/CONFIGURATION.md` に「完全停止」節（`launchctl list | grep com.moltbook` の期待値 0 件、手動 plist の除去手順）を書く。P4-02 runbook の手順 (2) がこれを引く。harness 側で本 repo を対象にする job（`triage-ca` の tick ほか）と repo 外の定期処理（claims の CA タスク・graph mirror）の停止は P4-02.7 の小節（手順と確認コマンドの正本）を引く 1 行だけを同じ節に置き、手順の行と確認コマンドはこの節に書かない。`docs/CONFIGURATION.md:433` の段落（ollama-restart は手動 `launchctl` 管理）の所有者はこの項目 — P0-02.3 / P0-05.8 / .5 / P4-03.2 はこの段落を参照する 1 行だけ書き、書き換えない。
- 根拠: `src/contemplative_agent/cli/schedule.py:447-457`（docstring「Out of scope, and left untouched: com.moltbook.ollama-restart (installed and updated manually)」+ legacy 2 本は手動除去）/ `docs/adr/0098-weekly-single-session-and-triage-delegation.md:75`（`triage-ca`: Wed 17:07 / Sat 14:07）、`scripts/weekly-pipeline.sh:11-13`（土 14:07 の tick が判断して dispatch）— `config/launchd/` の 8 本はすべて `com.moltbook.*` で、harness の tick は `launchctl list | grep com.moltbook` に出ない/ `config/launchd/com.moltbook.ollama-restart.plist:3-6`「Managed manually via launchctl, NOT by install-schedule」/ `docs/CONFIGURATION.md:433`（同旨）
- 完了条件: 手順どおり実行後 `launchctl list | grep com.moltbook` が空（harness 側 job の停止確認は P4-02.7 の確認コマンド）; 節に P4-02.7 へのリンク 1 行。`--all` を実装する場合はテスト 1 本; `docs/CONFIGURATION.md:433` の段落がこの項目の 1 回の書き換えで「完全停止」節と整合
- 規模・整合: S / repair   出典: DE-33

##### P2-04.4 watchdog にループ本体（agent）と Moltbook 到達不能の検査行を足す
- 何を: pure bash で (a) agent 行: 当日の `reports/comment-reports/comment-report-<today>.md` の mtime が直近セッション時刻以降、かつ `logs/llm-calls-<today>.jsonl` に当日行がある / (b) moltbook 行: 直近 24 h の `api-audit.jsonl` に `200 ≤ status < 300` の行が 0 かつ行数 > 0（`status: null` の transport 行も行数に含める; P1-07.5 の census 規則と同じ文言 — 3xx は client が redirect を追わないので常に失敗、P1-07.18）なら ❌ + `ERROR:` 行 / (c) comment-report 不在が 7 日続いたら ❌（platform 閉鎖の形）。停止はしない — 7 日行は P4-01 の検討イベントの入力。
- 根拠: `scripts/pipeline_watchdog.sh:92-160`（agent / submolt-scan / ollama-restart の行が無い。`config/launchd/com.moltbook.watchdog.plist:23-55` の起動は 04:30 日次 + 土 12:30/13:30 + 月 11:00）/ `src/contemplative_agent/adapters/moltbook/client.py:500-508`（transport 失敗は `status: None` 行として api-audit に残る）/ `docs/adr/0113-decision-faces-and-relevance-score4-shadow.md:329-331` Review-when「the feed engages with nothing for a whole day」は人間が読む前提、`scripts/api_drift_scan.py:18-28` は週次
- 完了条件: Ollama 停止を人為再現して翌 04:30 の `PIPELINE-STATUS.md` に ❌ agent が出る（再現手順を runbook に）、合成 api-audit fixture 2 本（24 h 不通 / 7 日 0 件）で ❌ になるテスト（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））、各行の読み手 = 土曜ゲート Step 0(c) を script 冒頭コメントに明記（ADR-0101）
- 規模・整合: S / instrument   出典: WO-23, AR-29, DE-42   依存: P1-08.1、P1-07.18（3xx を失敗として閉じる）。注: 部分廃止は .21 の行と役割分担（moderation 状態の常設行は置かない）
- 消費計画: (a) 土曜ゲート Step 0(c) が `PIPELINE-STATUS.md` の ❌ として読む（毎週）、7 日行は P4-01 の検討イベント C の入力 (b) 探索的ではない — ❌ 1 行で人間の停止 / 再実行判断（.3、P2-02.5 の runbook）の 1 判断 (c) 撤去条件: run セッションが止まった（第 5 層）時に agent / moltbook 行を落とす

##### P2-04.5 ollama-restart plist の curl 戻り値と ollama の絶対パスを直す（モデル不在の判定は P0-05.1 を呼ぶ）
- 何を: `com.moltbook.ollama-restart.plist` の `curl … > /dev/null` を `|| echo "ERROR: ollama did not answer /api/tags after restart" >> $LOG` に（template と live の鏡像規約どおり）。同じ修理で `/usr/local/bin/ollama serve` の絶対パス固定を `{{OLLAMA_BIN}}` placeholder か `command -v ollama` に替える — テンプレートは Ollama.app 導入を前提にしている（同じ行が `pkill -f 'Ollama.app/Contents/MacOS/Ollama'` を打ち、アプリが張る CLI は `/usr/local/bin`）。Homebrew 等で入れ直すと 23:55 の `pkill` の後に起動が失敗し、curl の修理だけが痕跡になる。`{{OLLAMA_BIN}}` 化するかどうかは P1-07.11 の Ollama 節の導入経路の決定（D-P1-07-3: A アプリのまま / B Homebrew に移して `brew pin`）に従う。`run` 起動時のモデル不在（`model_not_listed:<生成モデル>`）の判定と非 0 終了は P0-05.1 の `doctor` の検査関数（`serving_environment()` の reason を再利用）を呼ぶ — 止めるか継続かは D-P0-05-1（v2.13.0）に従い、ここでは別実装しない。`install-schedule` の docs は .3 の段落を参照する 1 行。
- 根拠: `config/launchd/com.moltbook.ollama-restart.plist:35`（`/usr/local/bin/ollama serve` を絶対パスで固定; `sleep 20; curl -s http://localhost:11434/api/tags > /dev/null` — 戻り値未使用）/ `src/contemplative_agent/core/llm/__init__.py:509-512`（`model_not_listed:<tag>` を記録するだけ — 呼び手は P0-05.1）/ `docs/adr/0069-…md:277`「confirm gemma4:e4b is pulled (`ollama list`)」は手動 / ADR-0075 §3「No silent fallbacks」
- 完了条件: template 差分（curl の `|| echo ERROR` と ollama パス）+ `docs/CONFIGURATION.md:433` の段落は .3 の所有で、ここでは .3 の段落を参照する 1 行のみ; `run` 側の rc≠0 のテストは P0-05.1 の完了条件（ここでは数えない）
- 規模・整合: S / repair   出典: AR-37, LP-27（LP-27 の `run` 側は P0-05.1 / D-P0-05-1 に統合）、R3-OSX Fix-01   依存: P1-07.11 / D-P1-07-3（2027-01-30。パスの描き方は導入経路の決定に従う）

##### P2-04.8 ジョブ × 書き込み先 × ロックの表を置き、chain 自身が lock を取る
- 何を: 8 本の launchd ジョブ + 土曜ゲートのコマンドについて「書き込み先 / 取るロック / blocking か」を ADR-0085（または CYCLES.md #4/#5）に 1 表で置き、`tests/test_cli_schedule.py` に「スケジュール済みコマンドが取るロック」を列挙固定する。`weekly-pipeline.sh` 冒頭で `$MOLTBOOK_HOME/.weekly.lock` を非ブロッキング flock（`python3 -c` 可）し、取れなければ `CHAIN_ALREADY_RUNNING` で exit 0。insight / distill-identity への lock 追加は D-P2-04-3。
- 根拠: `scripts/weekly-pipeline.sh` に flock 無し（`:721` はコメントのみ）、`:264-275` が `.pending*` と `.private/weekly-$END_DATE*.md` を `rm -f` / `scripts/weekly-analysis.sh:154-155`「concurrent runs are excluded by the pipeline's own single-run schedule」（前提のみ）/ `src/contemplative_agent/cli/memory_cmds.py:59-66`（distill は blocking、insight は「manual」扱いで無ロック — ADR-0074 以降は launchd job）、`cli/memory_cmds.py:140-166` と `cli/adopt.py` に `acquire_run_lock` 無し、`cli/staging.py:30,190` は staging dir のみ
- 完了条件: 表が存在、`tests/test_cli_schedule.py` にロック列挙テスト 1 本、chain 二重起動テスト（fault column、harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））で `CHAIN_ALREADY_RUNNING` が audit に出る
- 規模・整合: S / repair   出典: WO-26, CP-05   順序: .13 PR-A の後（`weekly-pipeline.sh` 冒頭の flock）。依存: P1-08.1

##### P2-04.9 時間窓のガード — 遅延起動の記録と identity 段の窓
- 何を: chain 冒頭で plist の予定時刻からの遅延を計算し ≥ 60 分なら `chain_start` に `late_minutes=` と reason `CHAIN_LATE_START` を残す（abort しない）。identity 段に「次の agent セッション開始まで ≥ `IDENTITY_TIMEOUT` + 5 分」のガードを足し、満たさなければ `IDENTITY_WINDOW_TOO_SHORT` で翌週へ（due は持続）。
- 根拠: `scripts/weekly-pipeline.sh:133` `CHAIN_DEADLINE_SECONDS=10800`（09:00 → 12:00 で 12:00 セッションと接する）、`:132` `IDENTITY_TIMEOUT=900`、`:709-712` が `distill-identity --stage` を起動、`:256` `audit chain_start` に遅延の記録無し / 7 本の plist が `/usr/bin/caffeinate -s`（watchdog plist は bash 直接）。`-s` は AC 電源時のみ有効で launchd は取りこぼしを wake 後に合算実行（外部知識、推測を含む）/ `CLAUDE.md:38`「JST 0 / 6 / 12 / 18 時のスケジュールセッションと重ねない」
- 完了条件: audit の `chain_start` に `late_minutes=` が出る、`IDENTITY_WINDOW_TOO_SHORT` のテストが valuelayer の fault column にある（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））
- 規模・整合: S / instrument   出典: WO-22, WO-27   順序: .13 PR-A の後（`chain_start` と identity 段）。依存: P1-08.1
- 消費計画: (a) 土曜ゲート Step 0(b) の完走判定で `late_minutes=` を読む（.13 の `pipeline_run_status.py` が 1 行に出す） (b) 4 週の読みで D-P2-04-3（insight / identity への lock 追加の要否）を決める — 衝突（`IDENTITY_WINDOW_TOO_SHORT` か late ≥ 60 分）が 1 件でもあれば A へ (c) 撤去条件: D-P2-04-3 が決まり、以後 8 週 late ≥ 60 分が 0 なら reason の提示は撤去（audit の field は残す）

##### P2-04.10 ディスク閾値・ログ保持ポリシー表・ローテ skip の検知
- 何を: watchdog に `df -k "$MOLTBOOK_HOME"` の空き閾値（例 10 GB）1 行。`logs/weekly-pipeline/<run_id>/` を chain 末尾で N 世代（例 12）に刈る。`docs/CONFIGURATION.md` に「ログ保持表」（ファイル / 書き手 / ローテ主体 / 世代 / 公開可否）を 1 表。`agent-launchd.log` のローテ skip が 2 週続いたら watchdog ❌。70 MB の `.bak` の処遇は → P0-03（ここに含めない）。
- 根拠: `grep -rn 'df -' scripts src docs` 該当 0 / `scripts/weekly-pipeline.sh:163-164`（`RUN_LOG_DIR` はローテ無し）、`scripts/weekly-analysis.sh:424`「the audit log never rotates」/ `scripts/backup-runtime.sh:55-56` + `scripts/rotate-log.sh:91-95`（lsof で open 中なら `ERROR:` + exit 1 で skip）、`docs/CONFIGURATION.md:435`（skip は「loudly」のみで回数の検知なし）/ `com.moltbook.ollama-restart.plist:35`（ollama-serve.log は 7 世代）
- 完了条件: `PIPELINE-STATUS.md` に `disk` 行、`logs/weekly-pipeline/` の世代数テスト（bash）、保持表の存在、ローテ skip 2 週で ❌ のテスト（watchdog の shell テストは harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））
- 規模・整合: S / repair   出典: WO-24, WO-29   順序: .13 PR-A の後（chain 末尾の刈り込み）。依存: P1-08.1

##### P2-04.11 TZ と電源の前提を明文化する
- 何を: `docs/CONFIGURATION.md` に「スケジュールはローカル TZ、記録は UTC、DST 地域は watchdog anchor と insight marker の 6 h 窓を要確認」「`caffeinate -s` は AC 電源前提、蓋閉じ・バッテリー時は wake 後の合算実行が起きる（`pmset` の案内）。LaunchAgents はログインセッション内でしか走らない（8 本とも `~/Library/LaunchAgents`）ので、OS 更新・停電後の再起動で自動ログインが無ければ watchdog を含む全ジョブが止まり検知面ごと消える — 検知側は .17。自動ログインが無くなる典型は 2 つ: (i) FileVault が有効だと自動ログインできず、再起動のたびに人がログインするまで 8 本が止まる (ii) macOS の「アップデートを自動でインストール」が有効だと深夜の再起動が人の知らないうちに起きる（いずれも外部知識）。段落の末尾に「現行機の FileVault と自動更新の設定、OS 更新は手動・セッション窓外で行う」の宣言 1 行、再起動後の点検は .23 の `host_check`」を各 1 段落。`weekly-pipeline.sh` 冒頭に END_DATE の TZ 前提を 1 行コメント。`date -u` への統一は決定事項にしない（現行機 JST では顕在化しない）。
- 根拠: `scripts/weekly-pipeline.sh:154` `date -v-1d`（ローカル）、`scripts/pipeline_watchdog.sh:40-41, 57-59`（ローカル `date`）、`scripts/pipeline_audit.py:35`（`datetime.now(timezone.utc)`）、`scripts/api_drift_scan.py:25-28`「the window compares against the record's UTC ts while the weekly chain passes JST-derived dates」/ `grep -rn DST scripts` 該当 0 / `src/contemplative_agent/cli/schedule.py:47`（`LAUNCHD_PLIST_DIR = ~/Library/LaunchAgents`。LaunchAgents と LaunchDaemons の違いは外部知識）
- 完了条件: CONFIGURATION.md に 2 段落（電源の段落に LaunchAgents の 1 文、FileVault / 自動更新の 2 原因、現行機の設定の宣言 1 行と .23 への参照を含む）、script 冒頭コメント 1 行（docs_consistency_scan の対象外なので目視）
- 規模・整合: S / neutral   出典: WO-28, WO-22、R3-OSX Fix-03

##### P2-04.13 chain のインライン python を script に出し、完走判定と理由コードを gate・watchdog で共有する
- 何を: PR-A: stage 7b / 7d のインライン python を `scripts/never_selected_reading.py` / `scripts/comment_outcomes_reading.py` へ移し、chain を「段の列挙 + 共通 run_stage」に戻す（挙動不変、1,000 行 → ≤ 700 行の確認）→ PR-B: gate Step 0(b) の heredoc python を `scripts/pipeline_run_status.py <end-date>`（stdlib）に移し、chain の stage 列挙から期待成果物を導出して present / missing を出すことで Step 0(a) の手書き ls（SKILL.md:21-37、9 path）も 1 コマンドにする（0(b) と .17 の Step 0(c) 鮮度と同じ script）、watchdog の土曜 13:30 検査も `result=fail` 行の grep で同じ答えを出す → PR-C: identity 段の延期理由を value-layer JSON の `identity.deferred_reason` に書き戻す。PR-A は verb 集合を変えない（P1-10.14 の固定集合は不変）。
- 根拠: `wc -l scripts/weekly-pipeline.sh` = 1000（ADR-0098「約 600 行」）、7b `:835-875` / 7c `:895-933` / 7d `:935-` のインライン python は `stage_enabled` の外 / `.claude/skills/weekly-gate/SKILL.md:39-73`（audit を読む heredoc python を毎週 LLM セッションが実行）、`scripts/pipeline_watchdog.sh` は audit を読まない / `scripts/weekly-pipeline.sh:696-731`（`IDENTITY_INSIGHT_PENDING` / `IDENTITY_STAGING_BUSY` / `IDENTITY_STAGING_RACE` は audit にしか残らない）
- 完了条件: chain ≤ 700 行、各段 1 関数呼び出し、`pipeline_run_status.py` が stage 列挙から導出した期待成果物の present / missing と `chain reasons: …` を出し `PIPELINE-STATUS.md` にも同じ行、value-layer JSON に `identity.deferred_reason`、既存 fault column が緑のまま（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））
- 規模・整合: M / repair   出典: WO-47, WO-48, CP-29、R4-COLD Fix-06（7d の前倒しを取り消し）   順序: 着手週 2027-02-06 で PR-A → PR-B → PR-C; .17 / P2-02.6 は PR-A の後。P1-10.5 / .15 は先に入る（P1-10.13 も PR-A より前に入ってよい。PR-A が rebase する）。依存: P1-08.1

##### P2-04.14 Sample splice の H2 を落とし、構造ゲートが H2 本数を数える
- 何を: `weekly_sample_splice.py` で sidecar 先頭の `## Random Sample …` 行を落とす（または H3 に下げる）。chain の構造ゲート（`report_missing_parts`）に「H2 = 6 本」の本数検査を足し、超過も `REPORT_INCOMPLETE` 系の reason にする。
- 根拠: `scripts/weekly_sample_splice.py:38, 61`（`SOURCE_HEADING` を残したまま差し込む）/ data repo `reports/analysis/weekly-2026-08-28.md` … `weekly-2026-10-02.md` の `grep -c '^## '` = 7（6 本（08-28 / 09-04 / 09-11 / 09-18 / 09-25 / 10-02）すべて）/ `config/prompts/weekly-analysis.md:19`「All six headings … in this order」
- 完了条件: 次週の weekly-*.md で `grep -c '^## '` = 6、splice の単体テスト 1 本（ubuntu で走る）、H2 超過の fault column 1 本（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））
- 規模・整合: S / repair   出典: WO-49   順序: .13 PR-A の後（`report_missing_parts`）。依存: P1-08.1。注: P0-03.9 が同じ構造ゲートに第三者 Context 由来の逐語一致件数の報告行（abort しない）を足す

##### P2-04.15 watchdog が launchctl の PID / LastExitStatus を読み、「走り続けている」と「非 0 で終わった」を区別する
- 何を: `log_healthy` と成果物行に `launchctl list com.moltbook.<job>` の読みを足す — 検査時刻に `"PID"` があれば ❌ `still running since <log mtime>`、`"LastExitStatus"` ≠ 0 なら末尾に ERROR が無くても ❌ `last exit N`。script 冒頭コメントと ADR-0085:78 に「許可する外部コマンドは date / stat / launchctl」の 1 行を追補。停止・kill はしない。
- 根拠: `scripts/pipeline_watchdog.sh:61-77`（`log_healthy` = ログ mtime ≥ 期限 + 末尾 30 行の grep のみ）、`:99-100,108-109,156-157`（distill / insight / backup がこれを使う）/ `src/contemplative_agent/cli/memory_cmds.py:65-66`（distill は開始直後に「Acquiring run lock …」を出して blocking で待つ）+ `cli/runtime.py:63-70`（INFO を stderr へ）+ `config/launchd/com.moltbook.distill.plist:37-40`（stdout / stderr とも同じ log）→ 開始した瞬間に mtime が新しくなり、以後ハングしても ✅ / `scripts/backup-runtime.sh:69,188`・`scripts/sync-research-data.sh:126-128,154`（timeout 無し）、plist に `ExitTimeOut` 無し / `scripts/pipeline_watchdog.sh:13-16` HARD CONSTRAINT「pure bash + BSD date/stat only」— `launchctl` は `/bin/launchctl` で PATH 非依存。`launchctl list` の出力形式（`"PID"` / `"LastExitStatus"`）は外部知識（推測を含む）。
- 完了条件: harness は P1-08.3 — `launchctl` stub（PATH 前置）で 3 ケース（走行中 / rc=2 / rc=0）、合成 fixture で `PIPELINE-STATUS.md` に `still running` の ❌ が出る（macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; ADR-0085 に許可コマンドの追補行。
- 規模・整合: S / instrument   出典: R1-SRE-01（.2 / .5 の「rc≠0」を読む主体）   順序: .4 と同 PR 可。依存: P1-08.1 / P1-08.3
- 消費計画: (a) 土曜ゲート Step 0(c) が `PIPELINE-STATUS.md` の ❌ として読む（毎週） (b) 探索的ではない — ❌ 1 行がそのまま人間の停止 / 再実行判断（.3、P2-02.5 の runbook）の入力 (c) 撤去条件: ジョブが launchd 以外の supervisor で rc を書き手に残す形に移った時（現行構成では撤去しない）

##### P2-04.16 `install-schedule --watchdog` が watchdog の固定窓に合わない引数を拒否する
- 何を: `install-schedule --watchdog` が、watchdog の固定の検査窓（distill は当日 03:00 以降・insight 土曜 07:30・report は金曜の `weekly-<Fri>.md`・backup 月曜 09:30）で覆えない引数の組合せ（`--distill-hour` ≥ 4、pipeline day ≠ Sat、backup day ≠ Mon など）を `parser.error` で拒否する。watchdog の期待表を引数から描く env 結線（4 変数 + 描画）はしない — 既定値以外で運用しない単一オーナーには過剰。今は既定以外で毎日 ❌（通知疲れ）か、ずれた窓で ✅ になり、どちらも静かな誤読で、`install-schedule` はその場で何も言わない。
- 根拠: `src/contemplative_agent/cli/schedule.py:97-100`（watchdog の検査時刻は template 内に固定）、`:416-434`（`substitutions={}` — placeholder 無し）、`:522-548`（引数検証に watchdog との整合検査無し）、`:614,626-631`（`--distill-hour` は 0–23 を受理、`--weekly-insight-day` の help は「matches the watchdog's fixed Saturday anchor」と言うだけで他値を拒否しない）/ `scripts/pipeline_watchdog.sh:92-100`（distill は当日 03:00 以降の mtime を要求 — `--distill-hour 5` では毎日 ❌）、`:105-109,118-121,149-157`（insight 土曜 07:30 / report `weekly-<Fri>.md` / backup 月曜 09:30 固定）/ `config/launchd/com.moltbook.watchdog.plist:23-55`（検査時刻も固定）
- 完了条件: `tests/test_cli_schedule.py` に「`--distill-hour 5 --watchdog` が `parser.error` で拒否される」1 本（ubuntu で走る）; `docs/CONFIGURATION.md:403` の 1 文を「watchdog の固定窓に合わない引数は拒否される」に更新。既存テストは不変（`tests/test_cli_schedule.py::TestInstallDistillSchedule::test_install_distill_custom_hour` は watchdog なしの関数直呼びで、拒否は parser 段。拒否のテストは同ファイルの `TestInstallSubmoltScanSchedule::test_out_of_range_schedule_installs_nothing` と同じ形で、plist が 1 本も書かれないことも assert する）。
- 規模・整合: S / repair   出典: R1-SRE-02、R4-CUT Fix-04   依存: P1-09.4

##### P2-04.17 `PIPELINE-STATUS.md` の `Last check:` の鮮度を読む主体を置く（watchdog 自身の停止を検知する）
- 何を: (a) 土曜ゲート Step 0(c) に「`Last check:` が 36 h より古ければ ❌ と同じ扱い（watchdog silent）で、承認より先に提示」を 1 行。(b) `weekly-pipeline.sh` の `chain_start` に `watchdog_age_h=` を記録し、72 h 超なら reason `WATCHDOG_STALE`（abort しない）。(c) status file 自身に「next check by <時刻>」と、通知の試行 `notified: <時刻> rc=<n>`（`osascript` の rc は現状 `2>/dev/null` で捨てている — Notification Center は GUI セッション不在・集中モードで到達を観測できない）を各 1 行書き、公開コピーを読む人が stale と healthy を区別できるようにする。off-host heartbeat は入れない（第 5 章の延期行どおり）。
- 根拠: `scripts/pipeline_watchdog.sh:171`（`Last check:` を書く）、`:192-193`（`mv` の失敗を見ない — ディスク満杯・書込不可でも exit 0 で古い status が残る）、`:209,213`（`osascript … 2>/dev/null`）/ `.claude/skills/weekly-gate/SKILL.md:80-82`（Step 0(c) は ❌ の有無だけを読み、日付は読まない）/ `src/contemplative_agent/cli/schedule.py:47,556-566`（8 本とも `~/Library/LaunchAgents` → ログインセッション外では走らない; `--watchdog` を落とした再 install で watchdog plist を黙って除去）/ data repo `reports/PIPELINE-STATUS.md`「Last check: 2026-10-10 04:30 JST … All scheduled pipelines healthy」は sync で毎日公開される — 凍った file は健全と言い続け、.2（sync 行）も再通知も watchdog の中にあるので一緒に死ぬ
- 完了条件: SKILL.md Step 0(c) に鮮度規則、`chain_start` に `watchdog_age_h`、日付を戻した status fixture で `WATCHDOG_STALE` が audit に出る shell テスト 1 本（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））、status file に `next check by` と `notified:` の行。
- 規模・整合: S / instrument   出典: R1-SRE-03（P2-04.6 の `notified:` 記録を吸収 — R1-SRE F5）   順序: .13 PR-A の後（`chain_start`）; SKILL.md Step 0(c) の所有者はこの項目で、変更は 10-17 の同梱 PR の後。依存: P1-08.1、.13（完走判定 script を共有するなら同じ場所）、.11（文書側）
- 消費計画: (a) 土曜ゲート Step 0(c) の人間（毎週、承認より先）と chain の preflight（毎週） (b) 探索的ではない — stale 1 回で「watchdog が止まっている」の 1 判断 (c) 撤去条件: off-host heartbeat（第 5 章の延期行、トリガー「次に見逃しが起きたら」）を建てた時に (a)(c) を畳む

##### P2-04.18 `with_timeout` の `timeout` 不在を preflight と audit が言う
- 何を: preflight で `timeout` → `gtimeout` → `$TIMEOUT_BIN` の順に解決し、`chain_start` に `timeout_bin=<path|none>` を記録。無ければ `WARNING:` + reason `NO_TIMEOUT_BIN`（fail-forward、abort しない）— 必須 bin に昇格させるかは実装時に決める（単一デプロイなので必須を推奨）。`docs/CONFIGURATION.md` の chain 節に 1 文。
- 根拠: `scripts/weekly-pipeline.sh:222-229`（`with_timeout`: `command -v timeout` が無ければ `"$@"` をそのまま実行 — コメント自身が degradation と呼ぶ）、`:248-254`（preflight は `claude git uv python3` のみ検査）、`:256`（`chain_start` に timeout の有無を記録しない）、`:352,710-711,767-768,808,853-854,923-924,954-955`（全段がこの関数経由）/ `config/launchd/com.moltbook.weekly-pipeline.plist:21-22`（PATH に gnubin 無し。macOS は `timeout` を同梱せず Homebrew coreutils は `gtimeout` 名 — 外部知識）/ .8 の chain flock が入ると、hang した `claude -p` の残った run が以後毎週 `CHAIN_ALREADY_RUNNING` で新しい run を弾く。著者機に `timeout` があるかは未確認（推測）。
- 完了条件: harness は P1-08.3 — PATH から timeout を外した run の audit に `timeout_bin=none` と reason が出る 1 本、`gtimeout` のみの PATH でそれが使われる 1 本（macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））、`docs/CONFIGURATION.md` の chain 節に 1 文。
- 規模・整合: S / repair   出典: R1-SRE-04（Horizon now）   順序: 着手週 2027-02-06 の中で .13 PR-A の後（preflight）、shell テストは P1-08.1 / .3 の後。依存: P1-08.1、P1-08.3

##### P2-04.19 復旧ドリルの実施条件・合格基準・周期を runbook に書き、検査を script に落とす
- 何を: `docs/runbooks/runtime-backup-restore.md` に「Drill conditions」節 — (1) 隔離先で行う（`MOLTBOOK_HOME=$PWD/restored-home`、ドリルで live home を `mv` しない）(2) 0/6/12/18 JST の窓と土 08:00–13:00 を避ける（Ollama 競合・run lock）(3) 前提: 空きディスク ≥ live home の 2 倍、`nomic-embed-text` の digest が最新の公開 snapshot manifest の `embedding_model_digest` と一致（不一致なら step 5 を打たず P1-07.11 の交代手順へ。照合の実体は P1-07.12）、backup repo の最新 commit 時刻を控える (4) 合格基準: fresh clone + `git fsck` が clean、`logs/episodes/` のファイル数と総バイトが「live − 最終 backup commit より新しいファイル」と一致、knowledge.json 行数一致、step 5 後 `missing_embedding` = 0、episode 側 `embeddings.sqlite`（backup から旧重みで戻る）と別の重みの埋め込みが混在しない (5) step 5 の所要時間を RTO として記録 (6) 周期: T4 四半期 + store 配置を変える ADR の着地後。backup 自体の周期（日次か 7 日損失の許容か）は D-P2-04-2 の決定を `docs/CONFIGURATION.md` と runbook に 1 行で反映する。`credentials.json` の保管先（パスワードマネージャ名など、値は書かない）を runbook に 1 行（鍵の棚卸し全体は P1-10）。検査は `scripts/restore-drill-check.sh`（read-only bash: tmp へ clone → fsck → 件数照合 → 不一致で exit 1）に落とし、restore 自体は自動化しない。この節を入れる回に ADR-0108（sidecar）後のドリルを 1 回実施し、日付と結果（JSON parse / 行数一致 / `missing_embedding` 不変量 / RTO）を Restore drills に追記する。
- 根拠: `docs/runbooks/runtime-backup-restore.md:6-7`（「This backup is the only off-machine copy of those logs」）、`:58-82`（step 2 `mv restored-home ~/.config/moltbook` は live home を上書きする形で、`MOLTBOOK_HOME` 上書きは括弧書きのみ; 窓・ディスク・所要時間の記述無し）、`:84-94`（合格基準は knowledge.json の parse / 行数 / `missing_embedding` のみ — `logs/episodes/` の件数・バイトは基準に無く、周期も無い）/ `scripts/backup-runtime.sh:186-191`（push まで。mirror を clone として検証する面（`git fsck`・fresh clone）は無い: `grep -rn "git fsck\|git clone" scripts docs/runbooks` は runbook step 1 のみ）/ `src/contemplative_agent/core/episode_embeddings.py:38-43`（`embeddings.sqlite` は `dim` しか記録しない — 「callers should re-backfill if the model changes」）、`scripts/restore-embed-knowledge.py` は digest を見ずにそのとき pull されている重みで全 pattern を埋め込み直す; `:84-94`（ドリルは 2026-07-11 のみ、「Since 2026-07-12 … Verify instead」は手順記述で実施記録なし）、`:70-72`「re-register / copy from the secret store」で store の実体は未記載 / `docs/CONFIGURATION.md:401`（backup は Mon 10:00 週 1）、data repo `reports/PIPELINE-STATUS.md`「backup — last run 10-05 10:00」→ 最大 7 日分の episode log が単一コピー
- 完了条件: runbook に節が存在、ADR-0108 後の日付 + RTO つきのドリル行 1 本、`credentials.json` の保管先 1 行、D-P2-04-2 の backup 周期が `docs/CONFIGURATION.md` に反映、fixture mirror で check script が不一致を exit 1 にする shell テスト 1 本（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））。
- 規模・整合: M / instrument   出典: R1-SRE-05、R3-OSX Fix-02、DE-43（旧 P2-04.12 を吸収 — R4-CUT Merge）   依存: P1-08.1、P1-07.12（digest 照合の実体）。注: D-P2-04-2（2027-02-20）は着手週の後なので、(6) の backup 周期と (4) の「最終 backup commit」は現行の週 1 で書き、決定が入ったら更新
- 消費計画: (a) オーナーが T4 四半期と store 配置を変える ADR の着地後に 1 回ずつ (b) 1 回のドリルで「backup が restore できる」の 1 判断（不合格なら P1-10 の修理か backup 周期の見直し（D-P2-04-2）へ） (c) 撤去条件: backup（ADR-0108 以後の sidecar 構成）が退役した時

##### P2-04.21 drift scan の盲点 2 行（未観測 baseline endpoint / 呼び出し > 0 かつ 2xx = 0 の endpoint）を出す
- 何を: `scripts/api_drift_scan.py` の `render_markdown` に 2 行足す — 「Baseline endpoints not observed this window: N（列挙）」と「Endpoints with calls > 0 and 2xx = 0 this window: N（endpoint / 件数 / 最頻 status）」。state の schema は変えない（窓内の records と `prev` の差集合だけで出る）。P1-07.4 の停止リスト（`_EXPECTED_KEYS` 拡張）は触らない。.4 (b) の日次全停止行との役割分担（.4 = 全 endpoint が 24 h 落ちた形、本項目 = 部分廃止）を script 冒頭コメントに 1 行。
- 根拠: data repo `reports/analysis/.api-drift-state.tsv` = 74 行・18 endpoint、うち `GET /submolts/{name}/{name}`（2 key）と `POST /submolts/{name}/{name}`（3 key）は現行 `_normalize_endpoint`（`client.py:73-92`）が出せない形（旧 normalizer の産物と推測、shallow で履歴は追えない）; `scripts/api_drift_scan.py:324-331`（`merge_state` = 未観測 endpoint は前回語彙を永久保持）、`:166-186`（removal は観測 endpoint のみ）、`tests/test_api_drift_scan.py:146,308`（この挙動を意図として固定）、`:140-162`（語彙は 2xx のみ → 平台が endpoint を廃止して 404 / 410 / 5xx だけ返す週は「未観測」= 何も出ない）。
- 完了条件: 合成 fixture（baseline に余分な endpoint 1 本 / 窓内 404 のみの endpoint 1 本）で各行が出るテスト 2 件（`tests/test_api_drift_scan.py`、ubuntu で走る）; 本番の次回 scan で `{name}/{name}` が 1 行目に出る。
- 規模・整合: S / instrument   出典: R2-PLAT-04   順序: .4 と同 PR（役割分担の 1 行）。依存: P1-07.19（2 行目が非 0 なら再読台帳へ）
- 消費計画: (a) 土曜ゲートが weekly の API Drift 節で読む（毎週） (b) 1 行目は 1 回読んで `{name}/{name}` 2 行を手で prune（state TSV 編集 + weekly-pipeline の pending 昇格と同じ規律）、2 行目は非 0 なら P1-07.19 の再読台帳へ (c) 撤去条件: 1 行目は 8 週連続 0 で撤去、2 行目は scan と運命を共にする

##### P2-04.22 本番 launchd 構成（`install-schedule` の全引数 + 手動 plist）を repo に宣言し、テンプレート変更を本番に届ける段を置く
- 何を: (a) `docs/CONFIGURATION.md` の Scheduling 節に「本番の構成」として、実際に打っている `install-schedule …` の 1 行・手動 plist（ollama-restart）・確認した日付を置く（値はオーナーの Mac で確認し、鍵やパスは書かない）。(b) P0-06.6 の release runbook に段を 1 つ足す: 前の tag から `git diff --stat <prev>..HEAD -- config/launchd/` が空でなければ (a) の 1 行をセッション窓外で打ち直し、`launchctl list | grep -c com.moltbook` を (a) の job 数と照合して `docs/evidence/releases.md` の備考に 1 語残す。本番 plist とテンプレートの描画結果を突き合わせる read-only の検査 script は置かない（(b) の `git diff --stat` と `launchctl list | grep -c` が同じ問いに答える）。
- 根拠: `docs/CONFIGURATION.md:433`（`install-schedule` は宣言的で、渡さなかった任意 job を消す — 「always pass the full desired set」）、`src/contemplative_agent/cli/schedule.py:469`（`_remove_stale_schedule_jobs`）; 本番の full desired set は repo のどこにも無い; `docs/CONFIGURATION.md:435`（RFC-0030: plist の修理は次の `install-schedule --weekly-backup` まで本番に届かなかった先例）; `config/launchd/com.moltbook.ollama-restart.plist:5`（「mirror live changes here in the same change」— 手の規約だけで照合は無い）; `docs/CYCLES.md:214`（確認は `ls ~/Library/LaunchAgents/com.*`）; plist テンプレートを変える項目は P0-02.3 / P0-05.8 / .1 / .5 / .16 / P1-14.6 の 6 つ。
- 完了条件: (a) の 1 行と確認日がある; release runbook に段がある; v2.13.0 の release 行に (b) の段の 1 語（(a) の宣言行は着手週に入るので、v2.13.0 では `git diff --stat` の空 / 非空と `launchctl list | grep -c com.moltbook` の件数だけ）。
- 規模・整合: S / repair   出典: R3-OSX-02、R4-CUT Fix-05（(c) の検査 script と消費計画を外す）   順序: (b) の release runbook の段だけ 11-07 の週（§4.0 の先行列。P0-06.6 の release runbook の PR、v2.13.0 の tag（11-14 の決定の後、11-20 まで）の前）、(a) は着手週 2027-02-06。依存: P0-06.6、P1-09.4（既定値の記述の修理）、P1-01.4（`config/launchd/` は凍結集合）

##### P2-04.23 Mac の再構築と OS / Homebrew / Python / Ollama 更新後の点検（runbook 1 本と read-only の `host_check`）
- 何を: (a) `docs/runbooks/machine-rebuild.md` を書く — 順序: OS 設定（FileVault と自動ログイン、電源、自動更新を切る — .11）→ Homebrew の依存（uv・git・gh・coreutils・rsync — P0-03.3 の rsync の実体）→ Ollama（P1-07.11 の Ollama 節の経路）と両モデルの pull → digest を最新の公開 snapshot manifest と照合し、不一致なら止めて P1-07.11 へ → repo の clone と `.venv`（P1-08.26）→ `claude` と私的 harness（P2-03.1 の表を引く）→ data / backup repo の clone → credentials（P1-10.9）→ `MOLTBOOK_HOME` の復旧（既存 runbook の step 1〜6）→ `install-schedule`（.22 の 1 行）と手動 plist・sync-data job の再導入（D-P2-04-1 の決定値）→ 最初の 1 日の点検。P4-03.2 の技術手順（launchd の再 install・credentials の再発行・backup repo の権限）はこの runbook に 1 本で置き、P4-03.2 は責任移転に固有の行だけを持つ。(b) `scripts/host_check.sh`（read-only bash）: macOS の版、`xcode-select -p`、PATH 上の `git` / `python3` / `rsync` / `timeout` / `claude` / `hf` / `gh` の実体と版、`.venv/bin/python -V` が起動すること、両モデルの digest（最新 manifest と比べる）、`launchctl list | grep -c com.moltbook` と .22 の宣言の一致を 1 画面に出し、不一致で rc=1。Ollama・モデル・home の部分は P0-05.1 の `doctor` を呼ぶだけにする。打つのは OS / Homebrew / Ollama / Python の更新後、再構築の最後、.19 のドリルと同じ回。
- 根拠: `docs/runbooks/runtime-backup-restore.md:58-80`（復旧手順は `MOLTBOOK_HOME` だけで、step 5 はそのとき pull されている重みで全 pattern を埋め込み直す — digest 照合なし）; `src/contemplative_agent/cli/schedule.py:236-238`（`.venv/bin` が無いと `Error: venv not found`）、`:250`（`{{USER_LOCAL_BIN}}` = `~/.local/bin` の `claude`）; data / backup repo の既定パス（`scripts/sync-research-data.sh:5`、`scripts/backup-runtime.sh:20`）、`hf`・`gh`・`timeout`（.18）・自動ログイン（.11）・全引数（.22）・sync-data job（D-P2-04-1）は手順として順序づけられていない; 無人経路は bare `python3` を 27 箇所で呼び、plist の PATH は `/opt/homebrew/bin` を先に置くので Homebrew の python の入替が実行 interpreter の入替になる（CLT の shim が major update 後に落ちうるのは外部知識）。
- 完了条件: runbook が存在し各段に確認コマンドと期待出力がある; `host_check.sh` が fixture（digest 不一致 / `timeout` 不在 / job 数不一致）でそれぞれ rc=1 になる shell テスト（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; `docs/runbooks/README.md` の表に行がある; 次の OS 更新の後に 1 回打った記録が `docs/evidence/serving-changes.md`（P1-07.11）に 1 行。
- 規模・整合: M / repair（(b) は read-only の点検で消費計画つき）   出典: R3-OSX-03、R3-OSX Merge-01（P4-03.2 の技術手順と D-P2-04-1 の「再構築時に公開ミラーが黙って止まる」を受ける）   順序: .19 のドリルと同じ回（着手週）。依存: P1-07.11 / P1-07.12、.22、P0-03.3、P1-08.26、P0-05.1、P1-10.9、P2-03.1、.11 / .19、P1-08.1 / P1-08.3
- 消費計画: (a) オーナーが更新後・再構築後・ドリル時に `host_check` の出力を読む (b) 1 回の読みで「本番を再開してよいか」を 1 つ決める（digest 不一致なら P1-07.11 へ） (c) 撤去条件: P4-02 の wind-down が終わり、実行機が退役した時


**依存**
- P2-01（WO-33: watchdog の合成 fixture / fault column。.4 .10 .15 のテストはこの harness に乗る; 代謝の脈の intake 行は P2-01.5 の出力を写す）
- P1-08.1 / P1-08.3（CI の 2 セル {ubuntu/3.13, macos/3.13} と shell harness `tests/_shell_harness.py`: .4 / .8 / .9 / .10 / .13 / .14 / .15〜.19 の shell テストは macOS セルで passed、ubuntu では skip）
- P0-05.1 / D-P0-05-1（.5 のモデル不在判定はその検査関数を呼ぶ、v2.13.0）、P1-09.4（.16 の schedule 文書）
- P1-07.5 / P1-07.18（.4 (b) の `200 ≤ status < 300` 規則と 3xx の閉じ方）、P1-07.19（.21 の 2 行目の再読先）
- P0-03（DE-01: 70 MB `.bak` の処遇は .10 に含めない）
- P0-06（plist template の変更は v2.13.0 以降の release に同梱）
- P1-10（鍵の棚卸し — .19 の保管先 1 行はその一部）
- P1-06（.13 の chain 整理は凍結判定の前の最後の窓）
- ADR-0085（pure bash 制約）、ADR-0101（新しい検査行の読み手 = 土曜ゲート Step 0(c) を明記）、ADR-0010（partial supersede は .1 が 1 本で。D-P2-05-1（12-12）の 2 層公開もそこへ）
- P1-07.11 / P1-07.12 / D-P1-07-3（.5 のパスの描き方、.19 / .23 の digest 照合と Ollama の導入経路）、P0-06.6（.22 (b) の release runbook）、P1-09.4（.22 の既定値の記述）、P1-08.26（.23 の `.venv` 段）、P0-03.3（.23 の rsync 段）、P1-10.9（.23 の credentials 段）、P2-03.1（.3 の harness job 名と .23 の私的 harness 段）
- → 参照元: P4-01 / P4-02（.4 の 7 日行は検討イベントの入力、.3 は runbook の手順 (2)。P4-02.7 は .3 の節からリンクされる repo 外の停止手順）、P0-02.3 / P0-05.8 / P4-03.2（.3 の `CONFIGURATION.md:433` 段落を参照。P4-03.2 の技術手順は .23 の runbook を指す）、P1-09.5 / P2-05.1（ADR-0010 の改訂は .1 の 1 本に寄せる）、P2-02.2 / .3 / .5 / .6、P2-03.2 / .3、P1-10.14（.13 PR-A の後に `weekly-pipeline.sh` を触る）、P1-01.6 (5)（.4 / .15 / .17〜.19 の合成 fixture テストは計器側の再現テストとして許容）


#### P2-05 公開に出す責任の接点（2 層公開・承認記録の投影・値層の縦断）
- 狙い: 「書くのは無人、公開に出すのは人間」（2026-08-25 著者判断）は `rfcs/` にだけ効いていて、同じ無人セッションの LLM 文書（`reports/analysis/weekly-*.md`、84 件）は人間の言葉なしで公開 data repo に出ている。一方で「責任を取る行為」の証跡（audit.jsonl・gate_item）は非公開で、README の中心主張（82/547）を第三者が検証できない。ADR-0080 の 08-26 追補 §A（権限は人間、負荷→0）と層 5（最終成果物 = データセット + 論文）の両方に関わる公開境界を、機械生成 = 無人 / LLM 文書 = 人間 promote の 2 層に分け、承認記録は本文抜きの投影で出す。
- 期限・順序: 着手 2027-02-20 の土曜ゲート（§4.0）。期限 2027-Q1。決定は D-P2-05-3 が 11-28（追補（2026-11）の材料）、D-P2-05-1 が 12-12、D-P2-05-2 が 2027-02-27。.2 は P1-12.1/.2/.4（approver・reason・却下本文・path 相対化）が入ってから（P1-12 の着手は 2027-01-09）、.3 は D-P2-05-1 の結論（C）に従属し、P1-04 の消費計画（読者 = 論文の図）と P0-03 の機微検査の後。.5 は D-P3-02-1（B）の実装で、B は D-P4-02-2（2027-Q2）と同じ回に決まるので .5 は 2027-Q2（この束の期限と束の完了条件には含めない）。.7（値層の変化系列）は 11-14 の週（§4.0 の先行列。`unchanged_since` 4 箇所の差し替えと同時）、.8（`skills/INDEX.md`）と .9（comment-report の Skills 行、本番 payload は P1-06 の凍結窓）は着手週。ADR-0010 の改訂は P2-04.1 の partial supersede 1 本に寄せ、.1 / .3 は段落（2 層の宣言・除外表）を渡す。shell テスト（.1）は P1-08.1 の後。`sync-research-data.sh` の順序は P0-03.2（backup + `.gitignore`）→ P0-03.3（sync allowlist、helper `_excludes()` の書き換えはここで 1 回）→ P0-03.16（push 段: force なしの push と non-fast-forward の ERROR）→ .1（allowlist を 2 本に分ける、同じ rsync 呼び出し）; `weekly-gate/SKILL.md` Step 6d の所有者は .1 で、変更は 10-17 の同梱 PR の後。
- 束の完了条件:
  - ADR-0010 の partial supersede（P2-04.1 の 1 本）に 2 層の宣言と除外表の段落があり、無人の `sync-research-data.sh` 経路が `reports/analysis/` を同期しないテストが緑（土曜以外の sync commit に `reports/analysis/` の差分 0）
  - data repo の `pipeline/decisions/` から README の 4 数字（82/547・6/11・2/4）が `jq` 1 行で再計算できる
  - `pipeline/gate/` から週ごとの adopted / rejected / held と推奨↔裁定一致率が計算できる
  - shadow 憲法と skill-selection 集計の 2 系列が公開 repo に週次で増え、`pipeline/value-layer/changes.json`（.7）と `skills/INDEX.md`（.8）が sync のたびに再生成される
  - ADR-0080 追補（2026-11、P1-03.8）に「人間の言葉として残す接点」の段落があり、CLAUDE.md §北極星が同 PR で同期され、weekly-gate SKILL.md の Step 構成がそれに整列する

##### P2-05.1 公開面を 2 層に分け、LLM 文書は人間が promote する
- 何を: D-P2-05-1 に従い `sync-research-data.sh` を 2 経路にする — (A1) 自己著作のみの機械出力（値層・knowledge・snapshots・`pipeline/*.json`: 機械生成、機微点検不要と宣言）は無人同期、(A2) 第三者本文を運ぶ機械出力（`reports/comment-reports/`、7,444 Context ブロック）は抑止リスト P3-05.19（`config/takedown-suppressions.txt`、11-21 の週）を同期の条件として後から読み、無人同期、(B) `reports/analysis/`（無人 LLM が書いた文書）は土曜ゲート Step 6d の機微点検の後に人間が `sync-data --reports` を打つ。allowlist は P0-03.3 の 1 本を 2 本に分ける（同じ rsync 呼び出し、P0-03.3 の後）。無人経路の決定論 pre-commit スキャンは P0-03.6 が正本（regex は `config/secret-patterns.txt` 1 ファイル、sync pre-commit / gitleaks / Step 6d / harness hook が同じものを読む）で、ここでは呼ぶだけ — 二重に書かない。2 層の宣言と除外表は ADR-0010 の partial supersede（P2-04.1 が D-P2-04-1 と D-P2-05-1 の後に 1 本で起こす）の段落として渡し、ADR-0010 への追補は別に起こさない。
- 根拠: `.claude/skills/weekly-report/SKILL.md:73-75`（`reports/.private/` に Write）→ `scripts/weekly-pipeline.sh:437`（構造検査後に `mv` で `reports/analysis/` へ promote、人間不在）→ `scripts/sync-research-data.sh:95`（除外は `reports/.private/` のみ）; `weekly-gate/SKILL.md:326-331`「公開へ出す commit はこのゲートの仕事」は `rfcs/` のみ; data repo 最終 commit 2026-10-09T20:30Z（JST 05:30、無人）; ADR-0080:189-193「the human word at the gate is the anchor」
- 完了条件: P2-04.1 の partial supersede に 2 層の段落 + sync の 3 経路（A1 / A2 / B）テスト（harness は P1-08.3; macOS セルで passed、ubuntu では skip（P1-08.2 の期待集合に登録））; (A2) は抑止リストの post id が次回 sync 後も公開 tree に戻らない（P3-05.19 のテストと共用）; (B) は P2-03.3 と共通の 1 文「無人実行後、本体 `git status --short rfcs/` と data repo の無人 commit の `reports/analysis/` 差分が共に空」; スキャンの fixture テストは P0-03.6 側
- 規模・整合: M / repair   出典: SA-08 WO-43（スキャン部分は P0-03.6 へ）、R3-ADR Merge-02（ADR-0010 の改訂は P2-04.1 へ）   順序: P0-03.3 / P0-03.16 の後、同じ rsync 呼び出し（P0-03.2 → P0-03.3 → P0-03.16 → .1）; SKILL.md Step 6d の所有者はこの項目。依存: P1-08.1、P3-05.19（(A2) の抑止リスト）、P2-04.1（ADR-0010 の partial supersede）

##### P2-05.2 承認記録とゲート縦断記録を本文抜きで公開する
- 何を: D-P2-05-2 に従い `export-patterns-jsonl.py` と同型の export 境界で (a) `audit.jsonl` の投影 `pipeline/decisions/decisions.jsonl`（ts / command / decision / source / content_hash / name / reason code / source_ids 数 / approver / `run_id` / `snapshot`（P1-12.9 の規則で解決した dir 名）/ `channel` / `session`（P1-12.1）、value-layer 行だけ `source_ids` を全件出す（P3-06.4 と一致）、`path` は `MOLTBOOK_HOME` 相対、本文なし）、(b) `pipeline-metrics.jsonl` の gate_record + gate_item を `pipeline/gate/*.json`、(c) 退役の `archived: [{name, date, reason_code, superseded_by}]` と approval_join の `unapproved_live_files` を `pipeline/value-layer/*.json` に出す。DATACARD に「decision log」節、README の数字をそこから集計する旨。
- 根拠: README.md:36,133（82/547・6/11・2/4）, :56「Rejected proposals stay in a local decision log and are not published」; `sync-research-data.sh:81`（`logs/` 全体除外）, `:28-34,98`（`.archive/` は退役系譜の非公開が理由）; `docs/adr/0010` Sync Targets に audit 無し; data repo `pipeline/` は 7 系列のみ（gate / decisions 無し）、`find -iname '*audit*'` 0 件; `weekly-pipeline.sh:71-72`（pipeline-metrics は土曜ゲートだけが書く）; 公開 insight-review は `RECOMMEND` 46 行 / `DECISION` 0 行（08-21 が最後、以後は gate_item が唯一の記録）; AAP `0006:102-104`「Third parties … can inspect the chain without running the agent」
- 完了条件: README の 4 数字が公開ファイルから再計算できる; 週ごとの推奨↔裁定一致率が `pipeline/gate/` から出る（区間は P2-01.9 の規則）; 57→53 の退役 4 件が名前つきで読める; 採用行から `run_id` → `snapshot` dir が引ける（P1-12.9 の 3 段 join）; DATACARD に列挙
- 規模・整合: M / instrument   出典: DE-28 DC-37 RF-17 VL-02 GO-11 （P1-12 から: GO-04 VL-03 VL-16 VL-08 残り）   依存: P1-12.1 / .4 / .9（投影の列）
- 消費計画: (a) README の数字を再計算する公開読者と、論文の数字を引くオーナー（月次、.5 の描画時） (b) 探索的ではない — 「README の 4 数字と推奨↔裁定一致率が公開ファイルから再計算できるか」の 1 判断 (c) 撤去条件: run セッション停止（第 5 層）で投影も止まる（既出分は公開のまま）

##### P2-05.3 計器ログの本文抜き投影（shadow 憲法・skill selection・relevance・comment-outcomes）
- 何を: D-P2-05-1 の結論（C: 2 層 + スキャン）に従属させて、週次チェーンに「研究投影」段を足し、`constitution-shadow.jsonl`（ts / cosine / sha / sections / verdict）、`skill-selection-*`（週次集計: 選択回数上位 10 と選択 0 の件数）、`relevance-*`（shape のみ）、`comment-outcomes`（自己書き込み欄のみ、他エージェント名と b64 本文を落とす）を `pipeline/instrument-logs/` に出す — 無人チェーンから公開 data repo への新しい投影経路なので層 (A) の機械生成として ADR-0010 の partial supersede（P2-04.1）の除外表に列挙する。data repo README の store 件数（53）の隣に選択分布を併記。読み手: 論文の図を描くオーナー（月次、.5 の描画時）と README の読者。土曜ゲートは読まない。
- 根拠: `sync-research-data.sh:81`（`logs/` 除外）; DATACARD「Excluded data」は episode log を理由にしているが計器ログも一括除外; CLAUDE.md:98（`skill-selection-*` / `constitution-shadow.jsonl` は b64 収納で Claude Code が読んでよい、ADR-0076/0092）; `docs/evidence/rfc-0043/README.md:87`（gemma は 150 行中 107 行＝71% で同じ 1 件を選ぶ → store 件数は実効サイズを表さない）; `pipeline/` の 7 系列に shadow・selection 系列が無い
- 完了条件: 公開データだけで台帳 baseline と census 読みが再計算できる; 2 系列が週次で増える; 読者が store 件数と選択分布を同じページで読める
- 規模・整合: M / instrument   出典: OI-48 RF-38 VL-14   注: .9 の `pipeline/instrument-logs/comment-skills.jsonl`（過去分の backfill）は同じ投影段
- 消費計画: (a) 論文の図を描くオーナーが月次（.5 の描画時）、公開読者は README (b) 探索的 — 2027-Q1 の review で継続可否（store 件数と選択分布を同じページで読めているか） (c) 撤去条件: insight / skill store が入口停止（RFC-0042 review-when / D-P0-01-1 B）か D-P2-05-1 が投影経路を許さない結論なら段を撤去（既出分は公開のまま）

##### P2-05.4 run セッション単位で有効だった値層版を公開面に pin する
- 何を: 値層 4 ファイルの sha256 は P1-07.13 の来歴 record（session-start episode の `_llm_session_meta`。`serving_environment()` と同じ場所、`core/llm/__init__.py:468`）が正本で 1 回だけ計算する。この項目はその record を comment-report の各行の `values_digest` 欄に写すだけ（再計算しない。snapshot manifest 側も P1-07.13 が同じ record を写す）。
- 根拠: data repo `snapshots/` の kind に `run` が無い（distill 84 / insight 11 / distill-identity 2 / amend-constitution 1 / rules-distill 1 / skill-stocktake 1）; 値層ファイルは日次 `sync:` commit の粒度でしか追えない; AAP `0006:44-45`「Identity, rules, constitution, and skills pinned to a specific version at the time」
- 完了条件: 公開 comment-report の 1 行から data repo の値層 commit（または hash）を特定できる; 同じ行から P1-07.13 の template digest（llm-calls 行の `template`）が引ける（P1-07.13 の完了条件から移管）
- 規模・整合: S / instrument   出典: GO-12（来歴 record は P1-07.13 に正本 — R1-OWN Merge-07、本項目は「写す」だけ）   順序: P1-07.13 PR-A の後
- 消費計画: (a) incident-response（P4-03.3）の「版の特定」と P3-02 の regime 表を描く時にオーナーが (b) 探索的ではない — 公開 comment-report の 1 行から値層 commit を引ける、の 1 判断 (c) 撤去条件: run セッションが止まった時（第 5 層）に転記も止まる。欄は記録として残す

##### P2-05.5 月次の value-layer ledger（機械描画、LLM 文書にしない）
- 何を: D-P3-02-1（B: 月次の縦断サマリ）の実装としてこれを置く。identity cadence（27 日）に合わせ、`pipeline/` の JSON から code が 1 ページ `reports/analysis/value-layer-YYYY-MM.md` を描画する（採用 / 却下件数、identity 類似度、constitution shadow 読み、store 選択分布、patterns / skills / identity / constitution の変化表（データ源は .7 の `pipeline/value-layer/changes.json`）— 評価語彙なし、ADR-0099 様式、regime 境界線（P3-02.1）入り）。LLM に書かせないので層 (A) として無人同期でよい。P3-02.2 は改題と DATACARD 区間表に絞る。
- 根拠: `.claude/skills/weekly-report/SKILL.md:66`「出すのは機構側の観察だけ」; data repo `reports/analysis/weekly-2026-10-02.md:210-213`（value-layer は hash の存在確認のみ）; `weekly-gate/SKILL.md:229`（Step 6b は cadence の due のみ）; data repo `reports/analysis/agent-diachronic-analysis.md:2,143-145`（縦断分析は建立 2 週目で停止 — P3-02.2 後段と同じ成果物）
- 完了条件: 2 か月分が公開され、全数値が .2 / .3 / .7 の JSON から再計算できる; DATACARD から参照される（D-P3-02-1 B の完了条件を兼ねる）
- 規模・整合: M / instrument   出典: VL-45 RF-39 DE-22（P3-02.2 後段を吸収 — D-P3-02-1 の実装）、R4-XREF Fix-18   順序: D-P3-02-1 B（D-P4-02-2 と同じ回）の後、2027-Q2（P2-05 の期限と束の完了条件の外）。依存: .7（変化表のデータ源）、.8（skill 単位の行）
- 消費計画: (a) 論文の図を描くオーナー（月次）と公開読者 (b) 探索的ではない — 月 1 ページで値層の変化が regime 境界つきで読めるかの 1 判断（D-P3-02-1 B の完了条件） (c) 撤去条件: run セッション終了で停止、既出分は残す

##### P2-05.7 値層の変化系列（版境界）を公開 `snapshots/` の digest から機械で出す
- 何を: `scripts/value_layer_change_series.py`（read-only、`python3 -I`、入力 = 公開 `snapshots/` のみ）を置き、`pipeline/value-layer/changes.json` に `[{kind, from_snapshot, to_snapshot, sha_before, sha_after, files_added, files_removed}]` を出す。P4-01.1 の材料 3 読みの 2 番目（`unchanged_since`）をこの系列に差し替え、P2-01.5 (vi) の adopted / archived 件数の照合先、.5 の変化表のデータ源、P3-02.1 の境界行（identity 08-15 / 09-12、skills 09-12 / 09-19）の出典にする。snapshot 回転（P3-04.1 前）で消える境界は `history/`（P3-04.2）側の版で補う。同じ script の出力に「serving_env の変化行」（snapshot manifest の `ollama_version` / `generation_model_digest` / `embedding_model_digest` が前の snapshot と変わった点）を足し、`pipeline/regimes.json` の候補行として出す — 確定は人間（P3-02.7 の境界表）で、script は書き込まない。
- 根拠: 公開 `snapshots/*/{identity.md, constitution/*.md, rules/*.md, skills/*.md}` 全 100 件の sha 集計（R2-VL が実行）: identity `151e91304927`(694 B, ≤07-17〜08-15T04:02Z) → `4003cf001aca`(894 B, 08-15T04:17Z〜09-12T01:26Z) → `40c36303e336`(954 B, 09-12T18:30Z〜 = live と一致); constitution `3d8a8503509e` → `37e3556a40ea`（`distill_20260809T18:30Z` 以降）; rules 2 件不変; skills 19(07-17) → 24 → 37 → 45 → 50(08-15T04:02Z) → 48(08-15T06:29Z) → 57(08-22) → 54(09-12T01:26Z) → 53(09-19T18:30Z)。対して `reports/analysis/.approval-join-state.json` は 4 層とも `digests: []`・`unchanged_since 2026-08-28` で、これは hand-edit 検知器の未照合集合の静止（`scripts/value_layer_approval_join.py:238-245`）であって値層の静止ではない。
- 完了条件: 上の境界が script 出力と一致するテスト（fixture = 3 snapshot、ubuntu で走る）; serving_env を変えた fixture で候補行が 1 行出るテスト; P4-01.1 / P2-01.5 / P3-02.1 がこの JSON を名指す; D-P3-07-1 (ii) の文言が訂正される（P3-07 の束で）。
- 規模・整合: S / instrument   出典: R2-VL-03、R3-MDL F-2   順序: 11-14 の週（§4.0 の先行列。`unchanged_since` 4 箇所の差し替え（R2-VL Fix-04）と同時）。依存: P3-04.1（回転窓）、P3-04.2（history）。注: P3-02.1（12-05 の週、境界行の出典として読む）と P3-02.7（2027-01-23 の週、serving_env の候補行の確定先）は後の週の参照元
- 消費計画: (a) 土曜ゲートの materials に 1 行（直近週の変化有無）; P4-01 の検討イベント B と P2-01.5 の自己調節宣言が読む (b) 4 週連続「変化 0」で検討イベント B の候補、1 回の読みで「静止 / 漂流」の語を `gate_record` に書く (c) 撤去条件: run セッション停止（第 5 層）で系列を固定。snapshot 自体が止まれば script も止まる

##### P2-05.8 `skills/INDEX.md`（+ `pipeline/skills-index.json`）を sync-data の export 段で生成する
- 何を: `sync-data` の export 段（`export-patterns-jsonl.py` と同型）で `skills/INDEX.md` と `pipeline/skills-index.json` を生成する — 列: stem / `name:` / adopted_at / source（audit source 語彙）/ origin / generated_by / 直近 90 日の選択回数（`pipeline/never-selected` と .3 の集計から）/ status（live / archived <date> / superseded_by）。退役分（`.archive/`、非公開）は名前と日付だけ行に残す（.2 (c) と同じ範囲）。P3-05.9 の写像表 `pipeline/skill-names.json`（stem ↔ `name:`）はこの INDEX と同じ生成段で出す（`name:` の書き換えもファイル rename もしない）。
- 根拠: data repo `DATACARD.md:23-36` Structure 表の `skills/*.md, rules/*.md` 行は「Distilled behavioral skills and rules」の 1 行; `skills/` に README / INDEX 無し（`*.md` 53 + `.last_insight`）; frontmatter は name / description / origin のみで 20/53 が name ≠ stem（P3-05.9）; `pipeline/never-selected/*.json` は dormant 名を持つが skill 一覧ではない; `docs/evidence/rfc-0043/README.md:87`（gemma は 71% で同じ 1 件を選ぶ = 件数は実効サイズを表さない）; data repo に `tests/` も `scripts/` も無く、本体 `tests/` から live data repo を読むテストは CI で成立しない。
- 完了条件: 合成 fixture（export 段を対象）で「写像表 / INDEX の行数 = `skills/*.md` + 退役件数」のテスト 1 本（P3-05.9 の完了条件はこのテストを指す）; live 木の照合は export 段の 1 行ログ（`MOLTBOOK_DATA_REPO` 未設定なら skip、P2-03.5）; DATACARD Structure 表が INDEX を指す; README.md:36 の 82 / 547 が INDEX + .2 の decisions 投影から再計算できる。
- 規模・整合: S / instrument   出典: R2-VL-04（完了条件のテストは R2-TST Fix-13）   依存: P3-05.8（frontmatter）、.2 / .3（投影・集計）、P3-05.9（name ↔ stem の写像表）、P2-03.5（`MOLTBOOK_DATA_REPO`）
- 消費計画: (a) 公開読者と、.5 の月次 ledger を描くオーナー (b) 探索的ではない — 「skill 単位で来歴と実績が 1 行で読めるか」の 1 判断、2027-Q1 の review で列の増減だけ決める (c) 撤去条件: P4-02 の最終 sync で固定。store が入口停止（RFC-0042 review-when / D-P0-01-1 B）なら再生成を止める

##### P2-05.9 公開 comment-report の各行に注入 skill 名を出す（選択 → コメントの結び付きを公開面に）
- 何を: comment episode の payload に `selection_id` と `selected`（名前列）を足し（`feed_manager.py:803` の隣、ADR-0075 の「機能と同じ PR で監査面」）、`core/report.py` の行描画に `Skills: a, b` と `gate_source`（P1-09.17 の語彙）の 1 行を足す。過去分は私有 `skill-selection-*.jsonl` から `selection_id` → `comment_id` で backfill した表を `pipeline/instrument-logs/comment-skills.jsonl`（.3 の投影段）として出す。本番 payload の変更は P1-06 の凍結窓で行う。選択・生成は不変。
- 根拠: `src/contemplative_agent/core/skill_selection.py:755-835`（選択ログは `selection_id` / `catalog_names` / `selected` / `selected_count` を持ち、`comment_id` は publish 記録側で埋まる）; `adapters/moltbook/feed_manager.py:719-722,750-766`（`record_publish_outcome(selection_id, comment_id=…)` で選択 → コメントの link を私有ログに書く）、`:803`（comment episode の payload は `relevance_p_top` 等で `selection_id` / `selected` を持たない）; `core/report.py:88-100`（comment-report の行は context / relevance / counterparty のみ、`skill` の語は 0 件）; `scripts/sync-research-data.sh:81`（`logs/` 除外）。.4 の `values_digest` は store 全体の版までで、選択（≤ 数件 / 53）は別。
- 完了条件: 公開 comment-report の新規行すべてに Skills 行（選択 0 なら `Skills: (none)`）; 過去分は 2026-09-09（link 記録の開始）以降が表で引ける; .4 の `values_digest` と同じ行に並ぶ。過去 link の網羅率は私有ログ未読（推測）。
- 規模・整合: S / instrument   出典: R2-VL-06   順序: P1-06 の凍結窓（本番 payload 変更）、.4 の後。依存: .3 / .4（同じ行・同じ投影段）、RFC-0028（selection ↔ publish の link）、P1-06
- 消費計画: (a) 公開読者（発話 1 件の「なぜ」）、P3-06.9 (c) と P3-01.3 を描くオーナー（月次） (b) 探索的ではない — 「公開発話 1 件から注入 skill が引けるか」の 1 判断 (c) 撤去条件: run セッション停止で転記も止まる。列は記録として残す


**依存**
- P1-12（.1 approver / reason、.2 却下本文の保存、.4 path 相対化、.9 snapshot への鍵 — .2 の投影の列）、P0-03（公開境界の allowlist 化・絶対パスの相対化・機微検査。`sync-research-data.sh` は P0-03.2 → P0-03.3 → P0-03.16 → .1 の順）、P1-04（ADR-0101 の消費計画: .3 の読者）、P3-04（値層縦断計器: .5 の中身; .1 回転窓 / .2 history は .7 の境界の補い）、P3-05（DATACARD / schema; .8 frontmatter / .9 写像表 / .19 抑止リスト）、P3-06.4（.2 の `source_ids` 全件の範囲）、P2-04（sync の検知面）、P2-03（sync スケジューラが repo 外; .5 の `MOLTBOOK_DATA_REPO` は .8 の live 木照合ログ）
- P1-03.8（追補（2026-11）: D-P2-05-3 A の段落）、P0-03.6（無人経路のスキャンの正本 — `config/secret-patterns.txt`）、P1-07.13（.4 の来歴 record の正本、PR-A が先）、P3-02 D-P3-02-1 / P3-02.1（.5 はその実装、regime 境界線）
- P1-08.1 / P1-08.3（.1 の shell テストの macOS セルと harness）、P1-06（.9 の本番 payload 変更は凍結窓で）、RFC-0028（.9 の selection ↔ publish link）
- 外部: data repo 側の DATACARD / README 手保守。ADR-0010 の改訂は P2-04.1 の partial supersede 1 本（.1 / .3 は段落を渡す）
- → 参照元: P4-03.3（.4 の読み手 = 版の特定）、P2-07（層 1 の位置決めは D-P2-05-3 を前提）、P4-01.1 / P2-01.5 (vi) / P3-02.1 / P3-02.7 / D-P3-07-1 (ii)（.7 の変化系列を材料・照合先・出典・確定先にする）、P3-05.9（.8 の写像表テスト）、P3-06.9 (c) / P3-01.3（.9 の行単位の再計算）、P2-01.3（`pipeline-metrics.jsonl` の公開可否 = GO-11）


#### P2-06 週次ゲートの読み量を減らす（carried・陽性のみ・多軸 join）
- 狙い: 裁定件数は週 0〜2 件まで落ちたが、ゲートが読む量（文書 207→279 行、Exceptions 80 行、findings 144 行）は再膨張しており、負荷の主成分は読み量（P2-01.3 の第 2 系列）。ADR-0080 の 08-26 追補 §B の「複数軸で見分ける」も、軸が別ファイルに散っているため人間は実質 1 軸で決めている。新しい判定者を増やさず、畳み込みと join だけで読む量を減らす。
- 期限・順序: 着手 2027-02-27 の土曜ゲート（§4.0）。期限 2027-Q1。.1（carried 畳み込み）は prompt の規約変更だけなので、着手週の PR の次の週次 run から入る。.2（多軸 join）は RFC-0042 の 10-10 読み（P0-01）で insight が続く場合のみ着手（入口停止（D-P0-01-1 B）なら出口側の .3 だけ）で、D-P2-06-1 C の実装（決定前は着手しない）。.2 は src の機構変更（`.meta.json` の `nearest` と `adopt-staged` の印字）なので、凍結の停止リスト（P1-01.3）に期日つきの行を持つ（D-P1-01-1 の追加段 B を前提、決定前）。ゲート単位の採用率は P2-01.1 の派生列（10-17 の週）で出る。決定は D-P2-06-1（2027-02-13、insight 継続が決まった場合）。
- 束の完了条件:
  - 週次文書の Exceptions 行数が 2 週連続で減り、carried 行が 1 行に畳まれている
  - staged item 1 件につき surprise / 近傍 5 本の名前 / 段の判定 / novelty verdict / 関連 skill の reply_rate が別列で `adopt-staged` と briefing に出る（合成スコア無し）
  - 入口 / 出口 × 軸の表が ADR-0106 にある

##### P2-06.1 Exceptions の carried 畳み込みと節別行数の読み
- 何を: `config/prompts/weekly-analysis.md` §Exceptions に「前週も出た行は `carried (since W)` 印を必須にし 1 行に畳む」規約を足し、節別行数（Inventory / Ledger / Deviations / Exceptions / Discarded / findings）を P2-01.3 が定義する読み量の列（表は P2-01.5 の `self_regulation_reading.py`）として出す。
- 根拠: data repo `reports/analysis/weekly-*.md` 行数 08-28 207 → 09-04 303 → 09-11 350 → 09-18 249 → 09-25 245 → 10-02 279、findings 78 / 93 / 198 / 82 / 113 / 144; `config/prompts/weekly-analysis.md:58-62`（例外ごとに fact + pointer + 台帳 / 起票の有無を書く規約はあるが、前週との畳み込みは無い）; Inventory の `exceptions` 5→12、`continuing` 7→11 と単調増。
- 完了条件: carried 行が 1 行化され Exceptions の行数が 2 週連続で減る; 節別行数が P2-01.5 の表に列で出る。
- 規模・整合: S / repair   出典: WO-04

##### P2-06.2 staged item の多軸 join（sidecar に近傍と段の判定、briefing に 3 軸）
- 何を: `.meta.json` に `nearest`（段が見た store 近傍 5 本の名前）と段の判定列（naming kind / duplicate verdict / fail-open 理由）を足し、`adopt-staged` が surprise の隣に印字する。gate briefing 側は `scripts/` の join で staged item ごとに surprise / novelty verdict（`insight-novelty.jsonl`）/ 関連 skill の `reply_rate`（`comment-outcomes-{end}.json`）を 3 列で並べる。スカラー化しない、判定者を足さない。これは D-P2-06-1 C（sidecar + scripts の両方）の実装で、決定前は着手しない。
- 根拠: `cli/staging.py:254-260`、`cli/memory_cmds.py:246-253`（sidecar は `source_ids` / `epistemic_counts` / `surprise` のみ）; `cli/adopt.py:1120-1170,1233`（印字は surprise だけ）; `core/insight_stages.py:222,344`（`store_shown` は監査ログにしか残らない）; `docs/adr/0080:203-208`（複数軸・単一スカラー禁止）; `docs/adr/0099:127-131`（per-axis、no composite）。
- 完了条件: sidecar 欄の追加テスト + `adopt-staged` 出力の 1 行; briefing の各 staged item に 3 軸が別列で出る; 凍結の停止リスト（P1-01.3）に本項目の期日つきの行がある（D-P1-01-1 の追加段 B を前提、決定前）。
- 規模・整合: M / instrument   出典: OI-23 CP-22   依存: D-P2-06-1（C の実装、決定前は着手しない）
- 消費計画: (a) 土曜ゲート Step 4（insight 1 件ずつ）でオーナーが staged item ごとに 3 軸を読む（毎週、insight 継続中） (b) 8 週で「3 軸が別列で出て裁定が変わったか」を RFC-0042 / ADR-0111 の読みに 1 行で残し、08-26 追補 §B「見分けられる」の充足を判定 (c) 撤去条件: 入口停止（RFC-0042 review-when / D-P0-01-1 B）で入口が閉じたら briefing の join を撤去（sidecar 欄は記録として残す）

##### P2-06.3 軸 × 適用位置（入口 / 出口）の表と出口候補への reply_rate 並記
- 何を: ADR-0106（D6 = 出口判定に使わない、の所有 ADR）に「新規性 / 重要度 / 環境の反応 × 入口 / 出口」の 1 表を置き（ADR-0080 には書かない — 追補は P1-03.8 の 2 本に限る）、「環境の反応」は入口候補には定義上付かない（まだ注入されていない）ことを書く。出口候補ファイル（`weekly-{end}-archive-candidates.txt`）の隣に該当 skill の `reply_rate` と `observed_publishes` を並記する — 判定には使わない（ADR-0106 D6）。RFC-0048 の設計点に足す（→ P2-07.1）。
- 根拠: data repo `pipeline/comment-outcomes/comment-outcomes-2026-10-02.json`（skill 別 reply_rate、observed 96 / unobserved 189）; `core/comment_outcomes.py:89-106`（分布であって寄与推定ではない注記）; `docs/adr/0106:136`（D6）; RFC-0047「comment-outcome を従属変数にしない」。
- 完了条件: 表が ADR-0106 にある; 出口候補の隣に reply_rate が並記され、archive 判定の入力にならないことがテストで固定される。
- 規模・整合: S / neutral   出典: CP-23、R3-ADR Merge-01（表の置き場を ADR-0106 に一本化）


**依存**
- P0-01（RFC-0042 の 10-10 読み: insight 継続 / 入口停止（D-P0-01-1）で .2 の要否が決まる）、D-P2-06-1（.2 は C の実装）
- P2-01.1 / .3 / .5（派生列・ゲート単位の採用率・読み量の定義・8 週表）、P1-05（台帳の機械化: carried と台帳 expiry は同じ問題の両面）
- ADR-0101（.2 の消費計画）、P1-12（`gate_item` と audit 行の相互参照 CU-24）
- P1-01.3 / D-P1-01-1（.2 は停止リストに期日つきの行を持つ。追加段 B を前提、決定前）
- → 参照元: P2-07.1（.3 の出口候補の reply_rate 並記は層 2 の定型説明の一部）、P2-01.3 / .5（.1 の節別行数を読み量の列に）


#### P2-07 RFC-0048 出口の自己維持と knowledge の保持方針
- 狙い: skill store の出口（退役）を機械に渡す層 1 は、ADR-0080 の 08-26 追補 §A の「負荷→0」への最短の修理（候補は毎週 0〜1 件を機械が出し、裁定は 2 週とも機械の候補どおり — `rfcs/0048:18-20`）だが、「承認ゲートは責任を取る行為」（設計原則）の線を入口と出口で非対称にする。飽和の定義、層 1 の位置、live プールの保持方針を先に決めてから設計する。
- 期限・順序: 着手 12-05 の土曜ゲート（.5 の草案）・2027-02-27 の土曜ゲート（実装、D-P2-07-2 の後）（§4.0）。期限 2027-Q1。.5（層 1 と ADR-0080 境界の整合草案）は 12-05 の週（11-30〜12-04 の平日）に起こし、D-P2-07-1 が 12-05 の土曜ゲート（RFC-0042 の 10-10 読みの後。P0-01 の AB-13 が RFC-0048 を「出口自動化」と「store 件数を絞る / 注入 ablation」に分割する前提）、ADR-0080 の文面は追補（2026-11）の 1 段落で、P1-03.8 の PR は 11-30〜12-04 に A / B 両文の草案段落を含めてゲートに提示し、12-05 の D-P2-07-1 の後に採った方の文で 1 本 merge する（12-07〜11）。D-P2-07-2 / -3 が 2027-02-27。順序は .5 → .1。.1 は src の機構変更（店に触る新しい無人段）なので、凍結の停止リスト（P1-01.3）に期日つきの行を持つ（D-P1-01-1 の追加段 B を前提、決定前）。.1 の設計セッションで RFC-0048 の Depends に注入 ablation の測定 RFC 番号を入れる。.2（飽和の定義）は .1 の設計の前提で、3 軸の率は P2-01.9 の区間規則で判定する。.4（保持方針）は独立で later。
- 束の完了条件:
  - ADR-0080 の追補（2026-11）に層 1 と「Not gate dissolution」境界の段落（.5）があり、層 1 の位置と範囲を決めた ADR（または ADR-0012 追補）がそれを引き、RFC-0048 の Summary がそれを反映して accepted または withdrawn
  - `gate_record.skills_archived` が層別（layer1 / layer2）で記録され、層 1 の復元件数が P2-01.5 の表に列で出て、無人チェーンの `--archive-names` 呼び出しのガードテスト（A: 無人専用 source のみ / B: 呼ばない）が緑
  - `pipeline/value-layer/*.json` に `store_state: saturated|equilibrium|growing` が毎週出る
  - RFC-0048 の Depends に注入 ablation の RFC 番号が入っている
  - knowledge の保持方針（a / b / c）が ADR に書かれ、週次 census に live 行の年齢分布が 1 行出る

##### P2-07.1 RFC-0048 層 1 の設計（実行位置・監査語彙・層別記録・反証計器）
- 何を: .5 の境界整合の後の設計セッションで、層 1（never-selected strict の決定論 archive）を weekly stage 7b の直後（`adopt-staged --archive-names` の決定論呼び出し）で無人実行する「決定論の自動退役 + 事後報告 + 復元権」にするか候補提示までに留めるか（D-P2-07-1）を決め、無人実行なら audit source は無人専用の新語（例 `archive-l1-unattended` — `direct-archive-auto` は `remove-skill --yes` の人間 CLI の語彙なので流用しない。人間の `--yes` と機械が同じ source に混ざる）とし、「可逆だから gate 省略」では足りない（境界の理由は attribution の錨）ことを ADR に書く。`gate_record.skills_archived` を層別にし、反証条件「4 週以内の復元 2 件で層 1 停止」の計器（復元件数）を P2-01.5 の列に足す。層 2 の定型説明は機械が軸ごとの数字だけで出す（→ P2-06.3 の reply_rate 並記）。D-P2-07-1 = A なら、復元権の CLI `restore-skill`（archive からの戻し、audit 行つき）だけをこの実装に同梱する（`edit-value` は作らない）。同じ設計セッションで RFC-0048 の Depends に「skill 注入はコメントを変えるか」の測定 RFC（P0-01 AB-13 の分割 (b)、測定設計は → P3-03）の番号を入れ、「測定前に store の件数を絞る側（09-26 追記）には着手しない」と書く（層 1 = never-selected strict は一度も注入されていない skill なので、この前提の外で止めない）。
- 根拠: `rfcs/0048:2-3`（blocked 2026-09-26、review-when = 10-10 まで）、`:26-28`（層 1）、`:33`（反証条件）、`:41`（`direct-archive-auto`）、`:45`（gate_record に層 1 を含める）、`:51`（LLM verdict は層 1 に入れない）; `docs/adr/0097:352-353` Review-when（復元 1 回超で床の見直し）; data repo never-selected strict 0,0,0・archive candidates 3/1/1/0（09-11〜10-02）; `docs/adr/0080:189-196`（Not gate dissolution — 人間の言葉は attribution の錨）; `docs/adr/0105:103-104`「Nothing in the unattended chain touches the store」; `src/contemplative_agent/cli/approval.py:37,110`・`cli/remove_skill.py:296`（`direct-archive-auto` = `remove-skill --yes`）; `rfcs/0048:70-74`（注入が効くかの open question と 3 通りの確かめ方）、`:98-117`（件数を絞る方向のオーナー指示）; `docs/evidence/rfc-0017/`（skills on/off の 1 回読み、Face A）。
- 完了条件: ADR 化（.5 の追補（2026-11）の段落を引用し、新 source を `AuditSource` 列挙に追加 — P1-12.5）; 凍結の停止リスト（P1-01.3）に本項目の期日つきの行（D-P1-01-1 の追加段 B を前提、決定前）; `gate_record` に `skills_archived_l1 / _l2`; `tests/` に層 1 のテスト（復元 2 件で自動停止するガード、無人チェーンの `--archive-names` 呼び出しのガード。A なら `restore-skill` の往復テスト 1 本）; `### Consumption plan`（ADR-0101）; RFC-0048 の frontmatter / Depends に測定 RFC 番号があり、件数を絞る設計点が測定 RFC の結果を待つと明記。
- 規模・整合: M / repair（D-P2-07-1 は value-steering-risk の決定）   出典: WO-36 VL-18（GO-20 の「ゲート省略条件」はここで定義、AAP 0005 側は P3-06.7 — R1-AAP F9）、VL-15（旧 P2-07.3 を吸収 — R4-CUT Merge）、旧 P1-12.6 の `restore-skill`（D-P2-07-1 = A のとき — R4-CUT Prune）

##### P2-07.2 「飽和」の操作的定義（`store_state`）
- 何を: ADR 1 本で飽和 / 均衡 / 成長を 4 週窓の 3 軸（入口の新規候補率 = staged ÷ cluster、出口の候補率 = archive candidates ÷ store、選択集中度 = hub skill の選択シェア）で定義し、`value-layer-{end}.json` に `store_state` を毎週出す。閾値は事前登録し、ADR-0111 Review-when「~40 件を下回ったら」と整合させる。「閾値未満」=「Wilson 区間全体が閾値未満」（`scripts/_stats.wilson_ci`、= P2-01.9 の規則 — 3 軸は staged 0 / store 53〜57 / archive 候補 0〜3 の小さい件数の比で、点の閾値は 1 件で反転する; 分母 < 10 は件数のみ）。
- 根拠: `rfcs/0048:3` と `rfcs/0042:3`（互いの review-when が入口件数だけを見る）; `rfcs/0042:204`（10-03: 候補 0 件、63 already covered）; data repo never-selected strict 0,0,0、confusion pairs 2→1→1→0、store 57→54→53; `docs/adr/0111:13-14,167`（saturated の語は散文のみ）。
- 完了条件: `store_state` が JSON に出て、RFC-0048 / 0042 の review-when がそれを参照する; 区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）; `tests/` の value-layer 読みに 1 件。
- 規模・整合: M / instrument   出典: VL-13   依存: P2-01.9（区間）
- 消費計画: (a) 土曜ゲート Step 6c（never-selected）の隣でオーナーが毎週、RFC-0048 / 0042 の review-when の読みで (b) D-P2-07-2（2027-02-27）で 3 軸 × 4 週窓の採否を 1 回、以後は `store_state` の遷移（saturated ↔ growing）ごとに RFC-0048 の設計点を読む (c) 撤去条件: 入口停止（D-P0-01-1 B）かつ層 1 の退役が止まった（store が固定された）時

##### P2-07.4 knowledge live プールの保持方針と年齢分布の読み
- 何を: 保持方針を 1 つ決めて ADR に書く（D-P2-07-3: a 現状維持 no-GC・トリガ 50 MB を明文化 / b N 日より古い live 行を年次シャードへ id を保って移す / c dedup の比較母集団を全 live に広げる）。決定に先立ち週次 census（`instrument_census.py`）に「live 行の年齢分布（58 日以内 / 以降）」1 行を足す。
- 根拠: data repo `knowledge.json` 10,985 pattern（155,290 行）/ tombstone（`valid_until`）675; `core/distill.py:749-756`（dedup 母集団は `effective_importance ≥ DEDUP_IMPORTANCE_FLOOR`、0.95^days ≈ 58 日）; `core/knowledge_store.py:170-177`（prune は orphan vector のみ、compact 無し）; `scripts/state_invariant_check.py:59`（tombstone 40% で WARN のみ）; `docs/adr/0108:215-216` Review-when（50 MB）; `docs/adr/0060:174-175`（no-delete）。
- 完了条件: ADR に方針; census に年齢分布 1 行（消費計画つき）; (b) / (c) を選んだ場合は `KnowledgeStore` の該当テスト。
- 規模・整合: M / neutral   出典: CP-12

##### P2-07.5 層 1 無人 archive と ADR-0080「Not gate dissolution」境界の整合を先に決める
- 何を: D-P2-07-1 を決める前に、ADR-0080 の追補（2026-11）に入れる 1 段落の草案「決定論・可逆・事後報告の archive は gate dissolution に当たるか」を起票し（ADR-0080 への別の dated note は起こさない）、オーナーが A（例外を認める: ADR-0105 を partial supersede、audit source は `archive-l1-unattended` 等の新語、反証条件を同 note に）か B（候補提示まで: 層 1 は人間の `adopt-staged --archive-names` 呼び出し）を `gate_record` に残す。段落は追補（2026-11）の束ね（P1-03.8）に入り、CLAUDE.md §北極星の同 PR 同期に従う。草案（A / B の両文）は D-P2-07-1（12-05）の前、12-05 の週（11-30〜12-04）に P1-03.8 の PR に含めて提示し、12-05 の決定の後に採った方の文で merge する（12-07〜11）。
- 根拠: `docs/adr/0080:189-196`（「the human word at the gate is the anchor of the program's attribution practice (ADR-0050), and removing it would trade away attribution …」— 可逆性を例外条件にしていない）; `docs/adr/0105:103-104`（「Nothing in the unattended chain touches the store」が決定文）; `rfcs/0048:26-28,40-41`（層 1「承認を待たない — 可逆なので」、実行位置は未設計、`direct-archive-auto` は「既存の語彙」）; `src/contemplative_agent/cli/approval.py:37,110`・`cli/remove_skill.py:296`（`direct-archive-auto` = `remove-skill --yes`、人間の CLI）; `docs/adr/0097:248`（600 床は「explicit operator argument」）。無人 archive を黙って実装すれば ADR 2 本を supersede し、audit の source が人間の `--yes` と機械で混ざる。
- 完了条件: ADR-0080 の追補（2026-11）に 1 段落（A なら境界の例外文 + CLAUDE.md §北極星の同 PR 同期、B なら「層 1 は人間の言葉を残す」の 1 行）; RFC-0048 の Reference-level「実行位置」がその段落を引用; `tests/` に「無人チェーンは `--archive-names` を呼ばない」（B）または「新 source でのみ呼ぶ」（A）のガード 1 件; オーナーの A / B が `gate_record`（`category=roadmap`）に 1 行。
- 規模・整合: S / neutral（D-P2-07-1 で value-steering-risk を明示 — 本項目は決定の前提作業（草案起票）で、A の実装は ADR 改訂を伴う repair）   出典: R1-NS-01   依存: D-P1-12-1（10-31、`adopt-staged --yes` と AAP 0005 の整合）、P1-03.8。注: .1 と P3-06.7（AAP 0005 の例外節）は .5 / D-P2-07-1 の結論を引く参照元


**依存**
- P0-01（RFC-0042 の 10-10 読み、AB-13 の RFC-0048 分割、CP-19 の凍結 / 継続）
- P2-07.1 の ADR（可逆・決定論・報告義務の 3 条件の定義）+ P1-12.5（`--yes` の位置づけ、`AuditSource` 列挙）、P1-12 WO-45（復元権の明文化）; AAP ADR-0005 への dated note（層 1 は `--auto` 禁止の例外か否か）は P3-06.7
- P1-03.8（ADR-0080 の追補（2026-11）の束ね — .5 の段落はその 1 本に入る）、P1-01.3 / D-P1-01-1（.1 は停止リストに期日つきの行。追加段 B を前提、決定前）
- P2-01.1 / .5（gate_record 層別・復元件数の列）、P2-01.9（.2 の 3 軸の区間）
- 順序: P2-06.3（出口候補の reply_rate 並記 = 層 2 の定型説明）と .1 の RFC-0048 の設計点は同じ週（2027-02-27）に入れる
- D-P2-05-3（11-28: 「人間の言葉として残す接点」— D-P2-07-1 はこれを前提）、D-P1-12-1（10-31: .5 の前提）
- P3-03 / P3-01（注入 ablation の測定設計: .1 の RFC-0048 Depends に番号を入れる）
- ADR-0097 D5 / Review-when、ADR-0105（.5 で partial supersede の要否）、ADR-0080:189-196（Not gate dissolution）、ADR-0108 Review-when、ADR-0101
- → 参照元: P2-01.5（層 1 の復元件数を列に写す）、P3-06.7（AAP 0005 側の dated note は .5 / D-P2-07-1 の結論を引く）


### Phase 3 — 研究の結晶化（〜2027-Q2）

建立時の 3 問い（憲法は小型ローカルモデルの行動を形づくるか／蒸留は複利するか／identity は安定するか）に、オーナーの主関心である第 4 の問い（承認ゲートの負荷と価値層の legibility、harness 層の責任構造）を加えるかを決め、操作的定義・対照条件・縦断記録・公開データの再利用性・論文の順に結晶させる。投稿先は SSRN / Zenodo を既定とする。

**このフェーズの完了条件**
- 研究問い ADR が存在し、各問いに計器・signal・反証条件・境界がある（P3-01）
- 装置境界表と研究ログが公開 repo にある（P3-02）
- 対照条件の採否が決まり、採ったものは evidence が凍結されている（P3-03）
- identity / 憲法の全版履歴が公開 data repo に残り、snapshot 上限で消えない（P3-04）
- 第三者が公開データだけで README の図表を再生成できる（P3-05）
- 論文 1 本が SSRN / Zenodo に DOI つきで出ている（P3-06）
- 「空性のみ公理」案と介入チャネルの扱いが決まっている（P3-07）


#### P3-01 研究問いの操作的定義（研究問い ADR・統計方針・Q4 の採否）
- 狙い: ADR-0080 L3（研究層）の完成条件は「建立時の 3 問に肯定でも否定でも答えが出て結晶化される」ことだが、3 問には計器・signal・反証条件・比較境界が無く、現時点の証拠は「憲法本文の限界効果は全計器の床以下」を示している（反証条件が無いので結論が出ない状態）。問いを操作的に定義し、オーナーの主関心（harness 層・承認ゲート・legibility）を Q4 として加えるかを決めないと、P3-03 の対照実験も P3-06 の論文種別も投資先が決まらない。
- 期限・順序: 着手 12-12 の土曜ゲート（§4.0）。期限 2026-12（研究問い ADR）。D-P3-01-2 = 2027-02-06。先行: .2 の Q1 事前登録は 10-31 の週（§4.0 の先行列）— 憲法改正 due（ADR-0091 の 83 日 = 2026-10-31、P0-07）の前に置く。決定は 2 件: D-P3-01-1（Q4）は 12-12 の土曜ゲートで ADR 起票の前に決める、D-P3-01-2（評価層の位置づけ）は 2027-02-06 の土曜ゲート（D-P1-04-3 と同じ回。ADR-0089 の追補は P1-04.10 が持つ 1 本に段落として寄せる）。Q4 の採否は ADR-0080 の追補（2026-12）（P1-03.8、12-19 の決定の後、12-21〜25 の PR）の 1 段落。.3/.4 は P3-02 の境界表（.4 (b) は P3-02.1 の区間長表。派生表は 2027-01-23 の週なので、.4 の草稿は「点数 ≥ 4」の規則を先に書き、表が入ったらリンクを足す）と同時に書くと効率的。IPD 床の推定量の正本は P3-03.10（10-31 の週）で、.4 (c) はそれを採るか理由つきで変える。.5/.6 は独立の小項目（`reanalysis` 列は .1 の証拠表に同居）。
- 束の完了条件:
  - `docs/adr/<N>-research-questions.md`（research 型）が state accepted で存在し、Q1〜Q3（採択なら Q4）すべてに (a) 計器 (b) signal と noise floor (c) 事前登録した肯定／否定の判定文 (d) 比較境界 が揃う
  - `docs/evidence/research-questions.md` の各問いの行が「現時点の答え」か「必要な計器と期日」のどちらかを持ち、`reanalysis` 列（.1）が埋まっている
  - ADR-0080 の追補（2026-12）（P1-03.8 の 1 本）に Q4 の採否の 1 段落があり、`CLAUDE.md` §北極星が同 PR で同期されている
  - `docs/CYCLES.md` Master table の cycle 7（Crystallization → papers）行から研究問い ADR へリンクがある

##### P3-01.1 研究問い ADR と証拠対応表を起票する
- 何を: research 型 ADR を 1 本起票し、Q1（憲法が小型ローカルモデルの行動を形づくるか）/ Q2（蒸留は複利するか）/ Q3（identity は安定するか）それぞれに (a) 使う計器 (b) 読める signal と noise floor (c) 事前登録した肯定／否定の判定文 (d) 比較境界（改正 03-27 / 05-05 / 08-09、モデル交代 06-28 など → P3-02 の境界表を参照）を書く。同時に `docs/evidence/research-questions.md` を作り、3 問 × （現時点の答え / 根拠 evidence / 未測定なら計器と期日）の表を置く（Q2 の縦断読みは P3-02.3、Q3 の identity 差分計器は P3-04 から埋める）。「外部監査経路 = 公開データ repo + ADR/RFC trail + FLIP グループでの読み合わせ（監査者がオーナー単独である事実を含む）」を ADR の 1 節として明記する。同じ表に、事前登録する各読み（P0-07.2 の改正の 4〜5 読み、.2 の Q1 事前登録、P3-06.2 のゲート縦断、P1-15.2 の t の再読）の `reanalysis: public | private-rows | rerun-local | rerun-cloud` 列を置き、public でない読みは論文で「再解析不能（集計のみ公開）」と明記する（P3-05.10 の 3 段表は script 単位なので、読み単位の対応はここで持つ）。
- 根拠: `docs/adr/0080-north-star-layered-end-state.md:62-68`（3 問は 2026-07-20 に初めて文章化、計器なし）; `docs/adr/0002-paper-faithful-ccai.md` に question / hypothes の語が 0 件; 公開 evidence の対応は Q1 のみ（`docs/evidence/adr-0090/`）、Q2 は `rfcs/0006:17-19` が `.notes/` の読みを引くだけ、Q3 は ADR-0030 が identity history を撤回し data repo の `snapshots/distill-identity_*` が 2 本のみ; 論文 `2504_15125_fulltext.md:220`「Independent oversight needed」に対し ADR-0106:189-191 はオーナー評価を steering として却下（公開性が代替）; 再解析の可否: 公開で再解析できるのは IPD（`docs/evidence/adr-0090/*.json`）・comment-outcomes / never-selected（data `pipeline/`）、できないのは relevance ラベル集合（`docs/evidence/rfc-0046/README.md:8`）・RFC-0045 の行データ（`rfcs/0046:88`）・eval golden（cloud judge）、P3-05.10 の 3 段表は 29/47 script が私的ログ要。
- 完了条件: ADR が存在し Q1〜Q3 に (a)〜(d) が揃う; `docs/evidence/research-questions.md` の 3 行すべてが「答え」か「計器+期日」を持つ（Q2 の縦断読み P3-02.3 は 2027-01-23 の週、Q1 の対照 P3-03 は 2027-02-20 着手なので、それまでは「計器+期日」の行で書き、入ったら更新）; `docs/CYCLES.md` cycle 7 行からリンク; ADR に「外部監査経路」節がある; `research-questions.md` と 4 項目の事前登録に `reanalysis` 列があり、論文 A / B の限界節が `private-rows` の読みを列挙する。
- 規模・整合: M / neutral（ADR・証拠表の文書。`reanalysis` は表の 1 列で計器は増えない）   出典: RF-01 AB-33 PF-41 R2-STAT-06   注: 各読みの行に列を置くのは各担当（P0-07.2 / P3-06.2 / P1-15.2）

##### P3-01.2 Q1 の反証条件を事前登録し、証拠表に「限定行」を置く
- 何を: `docs/evidence/research-questions.md` に Q1 の事前登録を書く —「H: 憲法本文は行動を変える。P1: 条項 X を変える改正は読み Y（IPD Δeffect / shadow cosine / eval verdict）を床 F 以上動かす。P2: N 回の改正で一度も動かなければ、この model・計器では H は支持されない」— し、次回改正 gate の runbook 手順から参照させる。同じ表に限定行 5 本を置く: (i) rules repo の skill-comply 測定（値中立コーディング課題では 25%、IPD では 91.7% = 「どの行動面に効き、どれに効かないか」）、(ii) 評価層 ADR-0089（golden 12 件、8/12 が 2–1 margin、cloud judge）の研究証拠としての位置づけは D-P3-01-2 待ち（推奨 A = 開発用回帰ゲートとして研究証拠から除外）、(iii) 本番の配備形は憲法を identity の後ろに連結するだけで、論文が d>7 を出した「応答前の contemplative pause」（Appendix D 条件 7、rules bench 91.7%）とは別物、(iv) 「憲法なし」対照は IPD 内蔵の no-prompt baseline のみで Moltbook 行動面は未計画（RFC-0002 は distill 面の A/B で、withdrawn 理由は Face B が誰の予定にも無いこと）。本番 CLI には憲法注入を外すレバー `--no-axioms` が現存し公開 report も A/B 可能と公言しているが、本番ループへの介入になるので使わない（D-P3-03-3、observation-over-steering）と 1 文で限定する、(v) 自己進化アーム（human-gated self-revision）の限定行 — 数字（staged 4 / adopted 2 / rejected 2、本文なし）・採択モード（両方 `adopt-staged --yes`）・判断材料の正本は P3-04.3 の値層 CHANGELOG の該当行（1 版 = 1 行、却下 2 行）で、ここにはその行を同文で写す（「proposal = adopted」が成り立つのは 08-09 のみ、の 1 句を含む。P3-06.4 の束の gate card も同じ行を描画）。(iii) は ADR-0002 の dated note 1 本として残し（P3-07.4 の「解釈キー不適用・referent 拡張」はこの note への 1 段落追記）、(iv) は RFC-0002 の dated note として残す。(ii) の ADR-0089 側の記述は D-P3-01-2 の後に P1-04.10 が持つ 1 本の追補の 1 段落になる（本項目では書かない）。
- 根拠: ADR-0057:80-83「Removing the axiom injection left the register essentially unchanged」、ADR-0058:89「Behavioral impact is near-inert」、ADR-0090:234-236（第 3 改正: 全 |Δeffect| ≤ 0.05、床 ±0.13 内）、`docs/evidence/adr-0092/ipd-shadow-reading.md:31-45`（Care 欠落 shadow でも無信号）、`rfcs/0020:139`（golden 12 件中動いたのは 1 件）; rules `docs/skill-comply-contemplative-axioms-2026-04-26.md:3,7,9`; rules `prompts/paper-faithful.md:1-6`「First, take a contemplative pause」vs `src/contemplative_agent/core/llm/prompting.py:218-229`（`_identity_axioms_base` は連結のみ）; `rfcs/0002:47-58`; `src/contemplative_agent/cli/__init__.py:76`・`cli/runtime.py:222-224`（`--no-axioms`）と data `reports/analysis/constitution-amendment-report.md:184`「A/B capability: `--no-axioms` flag runs the same agent without constitution」; 本体 `README.md:36,38`（4 staged / 2 adopted、両方 `--yes`）。
- 完了条件: 事前登録ファイルが存在し `docs/runbooks/constitution-amendment.md` から参照される（83 日 = 2026-10-31 の due 前、10-31 の週）; 証拠表に限定行 5 本（(ii) は「D-P3-01-2 待ち（推奨 A）」の限定行、(iv) に `--no-axioms` の 1 文、(v) は P3-04.3 の CHANGELOG 行と同文で P3-06.4 の gate card も同源）; 事前登録の各読みに `reanalysis` 列（.1）; ADR-0002 に「配備形は論文の介入と異なる」dated note が 1 本ある（P3-07.4 はこの note に段落を足す）。
- 規模・整合: S / neutral（事前登録と限定行の文書）   出典: PF-22 RF-09 RF-10 PF-39 PF-09 R2-VL Merge-01

##### P3-01.3 Q2「複利」の読み値を複数軸で事前登録する
- 何を: 「複利」を 2〜3 軸（例: 採用 skill の選択率の時間推移、corpus サイズに対する新規性率、skill 注入有無別の環境応答率）で定義し、各軸に期待形状と反証形状を書く。すべて公開 `pipeline/*.json`（never-selected 2026-08-28〜、comment-outcomes 2026-09-11〜）と `knowledge.json` から script 1 本で計算できる形にする。単一スカラーへの還元はしない（ADR-0080 の 08-26 追補 §B）。P3-02 の境界表の区間ごとに読む。軸の 1 つに「選ばれた skill の元パターン年齢分布」（skill-selection log の selected skill → staging `.meta.json` の `source_ids` → pattern 作成週。ランタイムには何も戻さない）を置き、全軸を read-only の script 1 本で出す。この軸だけは私的ログが入力なので `reanalysis: private-rows`（.1 の列）。
- 根拠: 候補読み値は散在して宣言されていない: ADR-0080:147-148（7 週で 438 staged / 53 採用 = 12%）、`contemplative-agent-data/pipeline/never-selected/`・`pipeline/comment-outcomes/`、README:110（dev.to 記事「17 日で新規パターンが止まり、人間承認の改正だけがループを動かした」）; ADR-0080 の 08-26 追補 §B（`:199` 以下）は単一スカラーを禁止; 元パターン年齢: `src/contemplative_agent/core/knowledge_store.py:210-211,593`（ADR-0028 で `access_count` 退役）、`src/contemplative_agent/cli/staging.py:37,254`（`source_ids` は ADR-0050 の系譜メタ）、`scripts/` に該当スクリプト無し。
- 完了条件: 研究問い ADR の Q2 節に軸・期待形状・反証形状が書かれ、元パターン年齢の軸を除く各軸の値が公開 JSON から script で再計算できる（P3-05 の再現ガイドに載る）。率の軸（選択率・新規性率・環境応答率）の区間は P2-01.9 の規則（`scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）で、期待形状 / 反証形状の判定は区間で行う。元パターン年齢の軸は 1 回目の読みが `docs/evidence/` にあり Q2 節から参照される。
- 規模・整合: M / instrument   出典: RF-15 R2-STAT-02 OI-25 R2-VL Fix-05
- 消費計画: (a) オーナーが研究問い ADR の起票時（2026-12）に 1 回、以後は P3-02.1 の境界が増えた時と論文 B の執筆時（2027-Q1〜Q2）に読む。元パターン年齢の軸は四半期 1 回 (b) 1 回の読みで各軸が「期待形状 / 反証形状 / どちらでもない」のどれに落ちたかを Q2 節に書く（単一スカラーに還元しない）。元パターン年齢の軸は 2 期（2 回）の読みで「選ばれた skill の元パターンが若い方に寄るか」の判定文を書く (c) 撤去条件: script は手動実行のみ（CI に入れない）。P4-02 の最終 sync で値を evidence に固定し、以後は再実行しない。元パターン年齢の軸は 2 期で Q2 の読みが決まらなければ外す（script は evidence に残す）

##### P3-01.4 単一エージェント縦断設計の統計方針（方法節草稿）を書く
- 何を: 方法節の下書きを研究問い ADR の 1 節（または別の research ADR）に置く: (a) 群間推論はしない、(b) 事前登録した境界（P3-02 の表）前後の within-series 比較、(c) 計器ごとの null pair 床と効果量＋区間 — run 間ノイズの推定量は P3-03.10 のセル別 SE 規則（10-31 の週、正本）を採るか、理由つきで変える（変える場合は P3-03.10 と ADR-0090 の記述を同じ PR で直す）。3 計器（IPD = ADR-0090 null pair / P3-03.2 / P3-03.10、identity 再導出 = P3-04.9、relevance 順序感度 = P1-15.4）は同型「同一入力の反復 2 回の差を床にする」。(d) 単一事例設計（ITS / change-point）の採否は落とした（やらないこと候補）— 代わりに系列別の区間長表（P3-02.1 の派生表）を引き、(b) の within-series 比較は点数 ≥ 4 の区間だけを対象にし、それ以外は記述統計に留める。「n=1 で何が言えるか」に先回りして答える。
- 根拠: 効果量は IPD（Cohen's d、ANOVA）と `rfcs/0011:10`（submolt sweep、Cohen's d = 0.448）で使用済み; null pair 床は ADR-0090 / ADR-0091:35-38（1 組、±0.13、96 日分の変化も解像できず）; 時系列手法（ruptures、changefinder …）は `docs/adr/0110-instrument-series-projection.md:285-290` が 28 点でも「trend / season / drift が無い」として却下済み; P3-02.1 の境界間隔は 20 / 19 / 43 / 6 / 5 / 5 / 9 / 6 / 8 / 14 / 7 / 6 / 6 / 1 / 8 / 5 / 1 / 6 / 10 / 9 日（R2-STAT の計算、06-17 以降は最長 14 日で週次読みなら 1 区間 ≤ 2 点）; 3 計器の同型: ADR-0090 null pair、`docs/evidence/adr-0092/shadow-run-1-reading.md:39-41`、RFC-0046 `relevance-noise-20260926.json`。
- 完了条件: 方法節草稿が存在し (a)〜(c) と P3-02.1 の区間長表への参照（点数 ≥ 4 の規則。派生表が入る 2027-01-23 の週までは規則だけを書き、入ったらリンクを足す）を含む; (c) が P3-03.10 のセル別 SE 規則を採るか、変える理由を書く（P3-04.9・P1-15.4 の「推定量は P3-01.4 (c)」の 1 句は (c) 経由で P3-03.10 を指す）。
- 規模・整合: M / neutral（方法節の文書）   出典: RF-21 R2-STAT P-1 M-1 R2-STAT-04 R4-XREF Fix-20   依存: P3-03.10（推定量の正本、10-31 の週）

##### P3-01.5 再現範囲表を置き、rules README の効果量の帰属を直す
- 何を: 「自分が確かめたこと」と「論文の報告値」を分ける再現範囲表（条件数・モデル・n・判定器・一致した方向／しなかった点）を rules repo と本体 `docs/evidence/` に 1 枚置き、rules README の「empirically validated with AILuminate d=0.96 … d>7」を「論文の報告値（Laukkonen et al.）」と明記する。自前の再現は qwen3.5:9b・n=2・7 条件中 2 条件・探索的、と書く。同じ主張を再掲する rules `README.ja.md:9,112` と data repo `llms.txt:138` も同時に直す（P1-11.11(b) はこの項目に吸収。(a)(c) は P1-11 側）。
- 根拠: rules `README.md:9`; rules `docs/benchmark-results-paper-protocol.md:8,14,65-66`（「exploratory results with n=2」、qwen3.5:9b vs GPT-4.1-nano）; 論文 `2504_15125_fulltext.md:183-191`（GPT-4.1 nano、AILuminate 100 iterations）; rules `README.ja.md:9,112`（同じ効果量の主張、JA 併記）; data `llms.txt:138`「with empirical validation — IPD cooperation d>7 and AILuminate safety d=0.96」。
- 完了条件: 表が両 repo に存在し、rules `README.md:9` / `README.ja.md:9,112` / data `llms.txt:138` の文言が修正されている（各ファイルで `grep -n "empirically validated\|empirical validation\|実証"` が「論文の報告値（Laukkonen et al.）」注記つきの行だけを返す）。
- 規模・整合: S / repair（文書）   出典: RF-12

##### P3-01.6 四原則の機構カバレッジ表を置く
- 何を: 四原則 × 4 列（憲法の文言 / 機構としての実装 / 観測計器 / ギャップ）の総括表を `docs/evidence/` に置き、改正・計器追加のたびに更新する。記録する事実: 機構列が厚いのは Emptiness だけ（憲法自身が改正可能ファイル、ADR-0058 で公理レンズを外し「空性が自分に作用」できる）; Non-Duality は境界の強化側のみ; Mindfulness の `internal_note` は行為に戻らない; Boundless Care は機構ゼロで、現行計器（shadow・IPD）は friction bias により Care に構造的に盲目。各原則の計器化は本束では行わない（→ P3-06）。外向き文書（README:32「名前の由来」、codemeta「philosophical resonance, not an architectural dependency」）は誇張していないが、表から参照する。
- 根拠: `contemplative-agent-data/constitution/contemplative-axioms.md:5-18`（第 3 改正の 8 条項）; `docs/evidence/adr-0092/shadow-run-1-reading.md:49-51`（Care 語彙 0、両 run）; ADR-0092:59-62「friction-biased sample … Values that operate silently leave no patterns」; `config/prompts/relevance_score4.md:1-6`（関与判断は topical 関連度のみ）; `config/prompts/comment.md:3`（唯一近いのは「長さは相手の重みに従う」）。
- 完了条件: 表が `docs/evidence/` に存在し、研究問い ADR（.1）から参照される（ADR-0080 からの参照は追補（2026-12）の Q4 段落に 1 句で同乗し、ADR-0080 を別に追補しない）。
- 規模・整合: S / instrument   出典: PF-01
- 消費計画: (a) オーナーが改正ゲート（P0-07、2026-10-31 以降の各回）と計器追加の ADR 着地時に読み、P3-06 の論文 B がギャップ列を限界節に引く (b) 1 回の作成で「機構ゼロの原則（Care）/ 計器が盲目の原則」を Q1 証拠表の限定行に書き、以後は改正・計器追加ごとに 1 列更新する（判断は人間） (c) 撤去条件: P4-02 の最終 sync で表を固定し、以後は更新しない


**依存**
- P3-02.1（境界表 .1(d) と .4 (b) の区間長表。派生表は 2027-01-23 の週）、P3-03.10（.4 (c) の推定量の正本、10-31 の週）、P3-04.3（.2 (v) が写す値層 CHANGELOG の行）
- 現行の形で書き、入ったら更新するもの（本束の着手 12-12 より後の週）: P3-02.3（Q2 の縦断読み、2027-01-23 の週）、P3-03（面集合・床・対照アーム → Q1 証拠表、2027-02-20 着手）、P3-03.3（`--no-axioms` を使わない対照の代替）、P3-04.8 / .9（Q3 の identity 差分計器、P3-01 と並行）
- RFC-0012（shadow 読みの消費）、P1-11.11（.5 の rules README sweep: (b) は本項目が正、(a)(c) は P1-11 側）、P2-01.9（.3 の率の区間規則）
- P1-03.8（ADR-0080 の追補（2026-12）= Q4 の採否の段落の器）、P1-04.10（ADR-0089 の 1 本の追補 = D-P3-01-2 と .2 (ii) の段落の器）
- 外部: AAP repo（Q4 の接続先）、FLIP グループ（外部監査経路の読み手）
- → 参照元: P0-07（83 日 = 2026-10-31 の改正ゲートが .2 の事前登録を参照）、P3-06（論文種別・投稿先が研究問い ADR を前提にし、四原則の計器化は .6 の表を引く）、P3-06.4（束の gate card が .2 (v) と同じ CHANGELOG 行を描画）、P3-05.10（.3 の再計算 script を再現ガイドに載せる）、P3-04.9・P1-15.4（.4 (c) 経由で P3-03.10 の推定量を参照）、P0-07.2 / P3-06.2 / P1-15.2（.1 の `reanalysis` 列）、P3-07.4（.2 の ADR-0002 dated note に段落を足す）、P4-02.8（.1 の `reanalysis` 列の読みに再検証依頼が来うる期間を確かめる）


#### P3-02 装置の境界表と縦断記録の再構成（regime・研究ログ・.notes の昇格）
- 狙い: 最終成果物は縦断記録（ADR-0080 L5）だが、蒸留コーパスの時系列は装置変更に支配されている（月別 distilled 件数 2026-06 707 → 07 3,441 の跳ねは per-episode distill とモデル交代の直後）のに境界表が無く、Q2 の唯一の縦断読み（T-P3）は gitignored の `.notes/` にしか無い。n=1 縦断研究で唯一できる推論は「境界内の比較」なので、境界表・研究ログ・null 結果の昇格は P3-01 の研究問い ADR と P3-06 の論文の前提になる。
- 期限・順序: 着手 2027-01-23 の土曜ゲート（§4.0）。期限 2027-02。.1（境界表）は 12-05 の週（§4.0 の先行列）、P3-01 の研究問い ADR（12-12）より前（P3-01.1(d)・.4 と P3-03.3 が参照する）→ .3（T-P3 昇格、P3-05 の再埋め込み再現性 RF-37 に依存）→ .4（研究ログ、P3-01 の問い ID が列になる）→ .5/.6 は独立で随時。.2 は改題と区間表に絞る（月次縦断サマリは P2-05.5 が D-P3-02-1 B の実装として担い、D-P3-02-1 B の後、2027-Q2。本束の完了条件には入らない）。`regimes.json` の schema（`affects` 列を含む）は .1 の PR（12-05 の週）で 1 回で決め、.7（Ollama 版・digest の履歴復元と manifest 世代表）と .1 の系列別の区間長表の派生（P3-01.4 (b) が引く）は §4.0 の先行列に無いので着手週 2027-01-23 にその schema へ行と派生表を足す。決定は 1 件: D-P3-02-1（2027-02-20 は A だけを決め、B は D-P4-02-2（2027-Q2）と同じ回）。
- 束の完了条件:
  - `contemplative-agent-data/DATACARD.md` に「Apparatus boundaries / Regime changes」表（日付 / 変更 / 影響する列・系列 / ADR・RFC）があり、下記 .1 の全行が載る; `reports/analysis/` の区間表がある
  - T-P3 の 3 量（corpus サイズ、pairwise cosine、入れ替わり率）が公開データだけから script 1 本で再計算でき、`docs/evidence/` に数値・図（境界線入り）が固定されている
  - `pipeline/regimes.json` の全行に `affects: [系列名]` があり、系列別の区間長表（.1 の派生表）が `docs/evidence/` にある
  - `docs/research/LOG.md` が存在し、`docs/evidence/` の全ディレクトリ（現在 37）と既知の null / dropped 4 件が行を持つ
  - `grep -l "\.notes/" rfcs/*.md` の各ファイルで、参照先が昇格済みか「失われてよい」注記がある

##### P3-02.1 装置の境界表（regime changes）を DATACARD に置く
- 何を: DATACARD に境界表を追加し、以後は値層・機構変更の ADR 着地時に同 PR で 1 行足す（規約は P1-09 の鮮度規約と同形）。現時点で載せる行（検証済み）: 03-27 第 1 改正（log 以前）/ 04-16 `provenance.pipeline_version` が distill@0.26 で開始（それ以前の 300 件は None）/ 05-05 第 2 改正 / 06-17 importance 退役（ADR-0056）/ 06-23 distill@0.60 = per-episode distill（ADR-0060）/ 06-28 qwen3.5:9b → gemma4:e4b（ADR-0069）/ 07-03 register 介入・views 7 → 2（ADR-0072 / 0073）/ 07-12 export で embedding 除去 / 07-18 dup-cleanup / 07-26 ADR-0084 postgate（抽出器変更）/ 08-09 第 3 改正 + IPD 計器初使用 / 08-16・08-29 レポート計器境界（日本語訳は 08-29 で終了）/ 08-15T04:02Z〜04:17Z identity 採用（694 B → 894 B、twin の手当て込み — P3-04.2 / P3-07.1 (2)、出典 P2-05.7）/ 08-22 skills 最終採用（この時点 57 件）/ 08-28 hand-edit 検知器の未照合集合 0 件が継続開始（手編集なし。値層の静止ではない — 静止・漂流の読み値は P2-05.7 の変化系列）/ 09-06 ADR-0069 追補 → 09-12 以降の manifest に `serving_env`（Ollama 版・重み digest）/ 09-11 insight 欠測 1 run → 09-18 再開、09-25・10-02 は staged 0 / 09-12 embedding sidecar（ADR-0108）・identity 採用（894 B → 954 B）・skills 57 → 54（archive、出典 P2-05.7）/ 09-18〜09-20 Ollama 0.30.11 → 0.34.2（`insight_20260918T23Z` と `distill_20260920T18Z` の間）/ 09-19 skills 54 → 53（以後 53 件、出典 P2-05.7）/ 09-28T15:00Z score4 enforce t=0.3（旧 0.82 とは別尺度）/ 10-07 comment-report 見出しが `P(top)` 表記。各行に `affects: [系列名]` を必須にし、script 1 本（read-only、`python3 -I`）が系列ごとに「境界と境界の間の日数」と「その区間に入る週次点数」の派生表を出して `docs/evidence/`（.3 の図と同じ場所）に置く — P3-01.4 (b) の within-series 比較は点数 ≥ 4 の区間だけを対象にし、それ以外は記述統計に留める。論文の図はすべて境界線を描き（区間長は帯で）、Q2 の期間は「ループが閉じていた区間」に限定する。表は `pipeline/regimes.json`（日付 / 変更 / 影響する列・系列 / ADR）でも出し、P3-05.11 の図 script はそれを読んで境界線を引く（座標を手書きしない）。
- 根拠: 公開 `knowledge.json`（10,985 件）の月別件数 216 / 239 / 271 / 707 / 3,441 / 2,678 / 2,668 / 765（10-09 まで）と `provenance.pipeline_version`（distill@0.26: 04-16〜06-22 544 件、distill@0.60: 06-23〜 10,141 件）; ADR 日付（0056 06-17、0060 06-23、0069 06-28、0072/0073 07-03、0108 09-12）; `DATACARD.md:47`（embedding は 2026-07-12 から export で除去）; ADR-0099 .ja:171-179（08-16 / 08-29 境界）; `reports/analysis/.approval-join-state.json` の `unchanged_since` 2026-08-28 は hand-edit 検知器の未照合集合が同一のまま続く起点（`scripts/value_layer_approval_join.py:238-245` Trend docstring）であって値層の静止ではない; identity / skills の境界は公開 `snapshots/` の digest 集計（R2-VL-03 → P2-05.7: identity `151e91304927` 694 B → `4003cf001aca` 894 B（08-15T04:17Z）→ `40c36303e336` 954 B（09-12T18:30Z）、skills 57（08-22）→ 54（09-12T01:26Z）→ 53（09-19T18:30Z））; `snapshots/`（insight_20260904 → 0911 欠 → 0918 / 0925 / 1002）と `weekly-2026-10-02.md:180-184`; `rfcs/0046:137-142`; `src/contemplative_agent/core/report.py:166-177`; `core/snapshot.py:116-122`（`serving_env`、ADR-0069 追補 2026-09-06）と公開 manifest 38 件の `ollama_version`（0.30.11 → 0.34.2、R1-REP-04）; ADR-0084（2026-07-26）; DATACARD の Known limitations（:95-99）には境界が 1 行も無い; 区間長（R2-STAT の計算）: 間隔 20 / 19 / 43 / 6 / 5 / 5 / 9 / 6 / 8 / 14 / 7 / 6 / 6 / 1 / 8 / 5 / 1 / 6 / 10 / 9 日、06-17 以降の最長は 14 日（07-26 → 08-09）、`docs/adr/0110-instrument-series-projection.md:285-290`（28 点で change-point 不適）。
- 完了条件: DATACARD に表があり上記の全行（22 行）が載る; `pipeline/regimes.json` が表と同内容で存在し（全行に `affects`）P3-05.11 の図 script がそれを読む; identity / skills の境界行が P2-05.7 の `changes.json` と一致する; 境界で計器を自動で読む仕組みは作らない（RFC-0008 は withdrawn 2026-08-30 のまま）; P3-01 の研究問い ADR (d) がこの表を参照する; 区間長の派生表が `docs/evidence/` にあり系列別の最長区間と点数が読め、P3-01.4 の方法節が「点数 ≥ 4 の区間」の規則でこの表を指す。
- 規模・整合: S / instrument   出典: RF-14 DE-24 RF-16 R2-VL Fix-04 R2-VL-03 R2-STAT-04   順序: 表と `affects` 列は 12-05 の週（§4.0 の先行列）、P3-01 の研究問い ADR（12-12）より前。区間長表の派生 script は着手週 2027-01-23
- 消費計画: (a) P3-01.1 (d) / .4 の方法節（オーナー、2026-12）、P3-03.3 の 4 版表、P3-05.11 の図 script、P3-06 の論文の図が読む (b) 1 回の作表で「ループが閉じていた区間」を Q2 の期間として固定し、以後は ADR 着地時に 1 行足すだけ（判断は人間） (c) 撤去条件: 表は常設（データの境界記録）。P4-02 の最終 sync で固定し、以後は追記しない

##### P3-02.2 `reports/analysis/` の区間表と「縦断分析」の改題
- 何を: DATACARD の `reports/analysis/` 記述（「Weekly rolling analyses, diachronic analyses」）を区間表（期間 / 書式 / 執筆モデル / ADR / 機械可読の対応物）にする: `agent-diachronic-analysis.md`（03-07〜03-20、qwen 期、別執筆モデル、対応物なし）、`constitution-amendment-report.md`（第 1 改正のみ）、weekly A–E 系列（03-30〜08-21。03-30〜08-07 は散文のみ）、計器文書（08-29〜、08-16 の model/style 境界を跨ぐ。08-07 dead-code / 08-14 以降は `pipeline/<系列名>` と `observation-ledger.jsonl` が対応物）。「Diachronic analysis」を名乗る文書は建立 2 週目で止まっているので「initial 14-day analysis」と改題する（D-P3-02-1 A）。月次の縦断サマリ（D-P3-02-1 B）は本項目から外し、P2-05.5 を実装とする。
- 根拠: `contemplative-agent-data/reports/analysis/agent-diachronic-analysis.md:2`「Period: 2026-03-07 through 2026-03-20 (14 days)」、:143-145「Added 2026-03-28」（以後更新なし）; `DATACARD.md:33`; ADR-0099 .ja:171-179（「境界でありシグナルではない」）; weekly 系列は `reports/analysis/weekly-2026-03-30.md` から; `pipeline/` の最古は dead-code 2026-08-07（R1-REP-05）。
- 完了条件: DATACARD に区間表（機械可読の対応物の列つき）がある; 文書名と期間が一致する（改題済み）。
- 規模・整合: S / instrument   出典: RF-39 DE-22
- 消費計画: (a) P3-05.10 の再現者と P3-06 の論文方法節が読む（改題時と論文 cutoff 時） (b) 1 回の読みで「縦断分析」の名を保つか改題するかを D-P3-02-1 で決める (c) 撤去条件: 区間表が DATACARD に入った時点で本項目は閉じる（月次サマリは D-P3-02-1 B を採った場合の P2-05.5、2027-Q2 以降。表の更新は P1-09 の鮮度規約）

##### P3-02.3 T-P3 の縦断読みを昇格し、公開データから再計算する script を添える
- 何を: T-P3 の読み（corpus 1,463 → 5,832、pairwise cosine 0.55 → 0.58、6 週で 75% 入れ替わり）を `docs/evidence/`（または data repo `reports/analysis/`）に昇格し、公開 `knowledge.json` + DATACARD「Reconstructing embeddings」の手順から同じ 3 量を再計算する script を 1 本添える。図には .1 の境界線を入れ、「4.0 倍」が distill@0.60 とモデル交代の境界を跨いでいることを明記する。`rfcs/0006` の `.notes/` 参照を昇格先に差し替える。
- 根拠: `rfcs/0006:13-19`（参照先は `.notes/memory-pipeline-phase3-reading-2026-08-16.md`）; ADR-0080:259-261; `docs/evidence/` に 5,832 の記載なし; `rfcs/0006:100-106`（withdrawn 理由「1 回きりで更新する計器が無く、発火しない条件のまま 12 回素通り」）。
- 完了条件: script 1 本が公開データだけから 3 量と図を出す（CI ではなく手動実行でよい、出力を evidence に固定）; `rfcs/0006` から `.notes/` への参照が 0 件。
- 規模・整合: M / instrument   出典: RF-13   依存: P3-05.10（RF-37 再埋め込みの再現性）
- 消費計画: (a) P3-01.3 の Q2 読み（オーナー、研究問い ADR 起票時 2026-12）と P3-06 論文 B の図 1 枚 (b) 1 回の再計算で T-P3 の 3 量を evidence に固定し、以後は境界表の区間が増えた時だけ再実行 (c) 撤去条件: evidence に固定した時点で script は手動実行のみ（CI に入れない）、P4-02 の最終版で最後の 1 回

##### P3-02.4 問い別の研究ログを置き、null 結果・中止実験を正式な行にする
- 何を: `docs/research/LOG.md`（列 = 日付 / 問い Q1〜Q4 / 計器 / 事前登録リンク / 結果 / 境界 / 状態）を 1 本置き、既存の `docs/evidence/`（37 ディレクトリ）と withdrawn RFC から遡及して埋める。`result: null` / `status: dropped` を正式な値とし、既知 4 件（dialogue two-arm、Converse IPD、RFC-0002 公理除去 A/B、T-GAP1 の mode 再計数）を行にする。論文の限界節・方法節はこのログから引く。
- 根拠: 代替候補はどれも「どの問いの証拠か」を索引キーに持たない — `rfcs/`（49 本、state 中心）、`docs/evidence/`（ADR/RFC 単位）、`reports/analysis/observation-ledger.jsonl`（31 行、運用観測 O-xxx）; null 例は `docs/evidence/adr-0092/interpretation-notes.md:73-84`（dialogue two-arm は 2026-08-15 に取り下げ、Converse IPD は unscheduled）と `docs/plans/whimsical-coalescing-trinket.md:12,27-29`（読み値は `.notes/`）。
- 完了条件: `docs/evidence/` の全ディレクトリ名が LOG に出現する（`for d in docs/evidence/*/; do grep -q "$(basename $d)" docs/research/LOG.md; done` が全件真）; 既知 4 件が `null` / `dropped` 行として存在; P3-01 の研究問い ADR が LOG を「証拠の索引」として参照する。
- 規模・整合: M / instrument   出典: RF-47 RF-48
- 消費計画: (a) オーナーが評価証拠を足す ADR / RFC の着地時と論文の限界節執筆時に読む (b) 遡及の 1 回で null / dropped 4 件を行にし、以後は ADR / RFC 1 本につき 1 行（判断は人間） (c) 撤去条件: P4-02 の最終 sync で LOG を固定、以後は追記しない

##### P3-02.5 `.notes/` に残る研究読みの棚卸し
- 何を: RFC・plans から参照される `.notes/` の研究読み（現在 21 本の RFC が `.notes/` を参照）を一覧し、各々を `docs/evidence/` に昇格するか「失われてよい」と明記する棚卸しを 1 回行う。研究上 load-bearing なもの（T-P3 読み、T-CAND7 詳細、T-GAP1 の premise-check・mode-recount）は昇格を既定にする。CLAUDE.md:114 の禁則（ADR / rfcs 本文から `.notes/` を参照しない）を rfcs/ の既存本文にも適用する。
- 根拠: CLAUDE.md:114; `rfcs/0006:14`、`rfcs/0008`（3 箇所）、`rfcs/0046`（5 箇所）ほか `grep -c "\.notes/" rfcs/*.md` で 21 ファイル; `docs/plans/whimsical-coalescing-trinket.md:27-29`「ADR がリンクしなかったのは `.notes/` が gitignored で CLAUDE.md が ADR→`.notes` 参照を禁じているため」; ADR-0090 の null pair README は昇格済みの好例。
- 完了条件: 21 ファイルの各 `.notes/` 参照に「昇格先パス」か「失われてよい（理由）」が付く; 研究上 load-bearing な 3 件は `docs/evidence/` に存在する。
- 規模・整合: S / repair   出典: RF-49

##### P3-02.6 撤去済み測定スクリプトの再現ポインタを evidence に付ける
- 何を: 撤去済みスクリプトを参照する evidence 文書の冒頭に「再現: commit <sha> の scripts/<name>」を 1 行追記する。対象（`git log --diff-filter=D -- scripts/`）: edca8cf 08-24 `build_decision_packet.py` `parse_findings.py` / a06c6be 08-29 `coselection_families.py` `offwindow-run.sh` / 947d204 09-05 `wiki_replay.py` / bcc97e2 09-19 `insight_revision_compare.py` `novelty_tiebreak_replay.py` `post_extraction_judge_replay.py` `rfc0027_render_fact_table.py` `rfc0027_select_cases.py`。撤去自体は ADR-0101 に沿うので復活させない。
- 根拠: bcc97e2「RFC-0027 の比較経路と RFC-0041 の測定スクリプトを撤去 (RFC-0042 項目 7 / 8)」; `skillsel_arm_replay.py` は 2bcc274 で削除後に復活済み（`scripts/` に存在）; ADR-0075 追補は固定した結果で代替すると定めるが evidence 側に sha の指示は無い。
- 完了条件: 上記 9 名のいずれかを含む `docs/evidence/**/*.md` すべてに「再現: commit」行がある（`grep -L` が空）。
- 規模・整合: S / repair   出典: OI-42

##### P3-02.7 Ollama 版・モデル digest の履歴を復元し、manifest 3 世代の表を置く
- 何を: (1) 公開 `snapshots/*/manifest.json` 100 件の鍵集合は 3 世代（14 鍵 18 件 / 15 鍵 44 件 / 19 鍵 38 件）なので、DATACARD に「鍵 / 初出 snapshot / 日付 / ADR」の表を `python3 -I` 集計から生成して置く（`manifest_schema` 欄の新設は P0-06.4 / P1-07.13 の来歴 record 側で行い、ここでは表にするだけ）。(2) オーナーが手元の記録（Homebrew / ollama のログ、`llm-calls` 監査行）から 2026-09-12 以前の Ollama 版とモデル digest の切替日を復元し、.1 の境界表に「serving」行として足す（復元できない期間は `unknown` と明示）。(3) P1-15.3 の `ollama_version` 列はこの表から引く。(4) 2026-09-12 以降の serving 行は手で書かない: P2-05.7 の版境界 script の出力に「serving_env の変化行」（公開 manifest の `ollama_version` / `generation_model_digest` / `embedding_model_digest` が前の snapshot と変わった行）を足し、`pipeline/regimes.json` の候補として出して人間が確定する（P1-07.11 の更新記録 `docs/evidence/serving-changes.md` の行と照合）。
- 根拠: `ollama_version` / `generation_model_digest` / `embedding_model_digest` / `serving_environment_reason` は `distill-identity_20260912T012632887862Z` 以降の 38 件のみ（`src/contemplative_agent/core/snapshot.py:116-122`「ADR-0069 addendum 2026-09-06」）; その 38 件で Ollama は `0.30.11`（〜`insight_20260918T230000Z`、16 件）→ `0.34.2`（`distill_20260920T183004Z`〜、22 件）、2 つの digest は不変; `DATACARD.md:80-82`（再導出が bit-identical なのは同じ Ollama / model 版の下のみ）; 03-07〜09-11 の run の Ollama 版は公開側のどこにも無い。
- 完了条件: 境界表（.1 と `pipeline/regimes.json`）に Ollama 版の行が 2 以上（`0.30.11` → `0.34.2` を含む）; DATACARD の manifest 鍵表と `python3 -I` 集計の diff 0; 復元不能な期間が `unknown` と書かれている; P2-05.7 の script を公開 snapshot に当てると 09-18〜09-20 の `0.30.11` → `0.34.2` が serving_env の変化行（候補）として出る。
- 規模・整合: S / instrument   出典: R1-REP-04 R3-MDL F-2   依存: P2-05.7（serving_env の変化行）
- 消費計画: (a) P3-05.10 の再現者と P3-02.3 の再埋め込み script が読む（再導出の可否判定） (b) 1 回の復元で表を固定し、以後は P2-05.7 の script が出す serving_env の変化行（候補）を人間が確定して .1 に 1 行 (c) 撤去条件: 表が DATACARD に入った時点で本項目は閉じる（以後の行は P2-05.7 の候補を人間が確定する）


**依存**
- P3-05（RF-37 再埋め込みの再現性 → .3; DATACARD の schema 改訂 P3-05.3 と同じファイルを触る → .1/.2 は同 PR か順序を決める）
- P3-01（研究問い ADR が LOG の「問い」列を定義）、P0-06.4 / P1-07.13（`manifest_schema` 欄・版の単一ソース → .7）、P2-05.7（値層の変化系列 = .1 の identity / skills 境界行の出典、.7 の serving_env 変化行の候補）
- P0-03（`knowledge.json.bak-dup-cleanup-20260718` の公開除外 — 07-18 の境界行は残す）、P1-09（「ADR 着地時に境界表へ 1 行」の鮮度規約）、P1-03（ADR テンプレート）
- 決定: D-P4-02-2（2027-Q2。縦断サマリ = 最終版の一部、D-P3-02-1 B はこの回。本束の完了条件には入らない）
- → 参照元: P3-01.1 (d) / P3-01.4（境界表と .1 の区間長表）、P3-03.3（4 版 × IPD の表が改正日を使う）、P3-05.11（図 script が `pipeline/regimes.json` を読む）、P2-05.5（D-P3-02-1 B の実装 = 月次縦断サマリが .2 の区間表を引く）、P1-15.3（`ollama_version` 列 → .7 の表）、P3-05.6 / .17（.7 の Ollama 版の行と境界行）、P1-01.8（凍結後のモデル交代を .1 の regime 行として読む）、P1-07.11（Ollama 更新の記録 → .7 の候補行と照合）、P1-10.9 (3)（新規 `register` の実施日を .1 の境界表に 1 行）


#### P3-03 対照条件（IPD の床・プラセボ憲法・旧版・Care 面・2 体目の判断）
- 狙い: Q1「瞑想的憲法が小型ローカルモデルの行動を形づくるか」の答えは、現状 IPD ベンチ内の no-prompt baseline（協調率 1 面、null pair 1 組・床 ±0.13）に閉じている。瞑想固有か（プラセボ）、改正で変わったか（旧版系列）、Care は働いているか（計器が構造的に盲目）、Moltbook 環境に依存するか（別環境）を切り分けないと、論文の方法節と限界節が書けない。本束は本番の学習ループに何も注入しない read-only 計器の拡張だけを本体に置き、大型モデル・cloud・2 体目を要する案は「前提の変更」として分離して判断に回す。
- 期限・順序: 着手 2027-02-20 の土曜ゲート（§4.0）。期限 2027-Q1。先行: .1 / .2 / .10 は 10-31 の週（§4.0 の先行列）— .10（セル別 SE 規則、公開 JSON の再計算のみで新 run 不要）が .2 の予算化より前、.1（計器の修理）と .2（床の検証）は改正 due（ADR-0091 の 83 日 = 2026-10-31、P0-07）の前の平日に回す（各 null pair ~2 h、定時窓外）。.3/.4 は .1(c) の任意テキスト入口と P3-01.2 の事前登録（比較対・family-wise 規則・予測）が前提で、束の着手週（2027-02-20）以後。.5/.7/.8 は D-P3-03-1（12-26 の土曜ゲート）と D-P3-03-2 / -3 / -4（2027-02-20 の土曜ゲート）を決めてから、実行は 2027-Q1。.9（RFC-0041 形 A の測定）は P0-01 と P2-07 の決定の後。IPD 床の推定量の正本は .10（10-31 の週）で、P3-01.4 (c)（12-12 着手）はそれを採るか理由つきで変える側。
- 束の完了条件:
  - `docs/evidence/adr-0090/` に 4 run のセル別 SE 表（.10）と null pair ≥3 組の JSON があり、ADR-0090 に「床 = セル別 SE 規則（|z| > 2、推定量の正本は .10）、検証に使った pair 数」が書かれている（改正記録への SE・z と Δ の併記は .2 の消費計画 (a) — D-P0-07-1 = A の回、B なら以後最初に起動された改正）
  - IPD 結果 JSON の simulation 行に `parse_fallback_count` / `llm_failure_count` が入り、`provenance.txt` が bench commit・IPD version・Ollama version・重み digest を含む 8 行になる
  - `scripts/ipd-two-arm.sh --files A B` でテンプレート 2 本の比較が同一書式で走る
  - 「4 版 × IPD」の表が data repo `constitution/history/` に、「プラセボ 4 アーム」の表が `docs/evidence/` に固定され P3-01 の Q1 証拠表に行がある
  - D-P3-03-1〜4 が RFC / ADR に state 付きで記録され、前提変更を伴う案はその旨が RFC の節として書かれている

##### P3-03.1 IPD 計器を修理する（失敗件数の記録・provenance 3 行・任意テキスト入口）
- 何を: (a) rules repo `llm_player.py` で解析失敗（`_parse_move` の曖昧時 COOPERATE 既定）と LLM 失敗（応答なし → COOPERATE）を simulation 単位に数え、結果 JSON に `parse_fallback_count` / `llm_failure_count` を書き、`scripts/ipd_two_arm_report.py` に表示する。既存 5 run（null ×2、arm A / B、shadow）は run.log から件数を復元して evidence に追記する。(b) `ipd-two-arm.sh` の provenance に `git -C "$BENCH_DIR" rev-parse HEAD`、`contemplative-ipd` の version（pyproject 0.2.0、tag 無し）、`ollama --version`、`OLLAMA_MODEL` の重み digest（`GET /api/tags` の sha256 先頭 12 hex。ADR-0069 追補 2026-09-06 の `generation_model_digest` と同じ流儀 — Ollama tag は mutable で ±0.13 床は重みに結びつく）の 4 行を足す。(c) `--files A B`（または `ARM_A_FILE` / `ARM_B_FILE`）で `.staged/` と承認ハッシュに依らず任意の 2 テキストを同じ較正契約（n=10、gemma4:e4b、窓ガード）で比べられるようにし、provenance に由来を書く。`--files` 時はレポートの固定ラベル「arm A (current) / arm B (staged)」を引数名に置き換え、本番 home 外では `AUDIT_CHECK_BYPASS=1` が必須である旨を第三者向け手順に 1 行書く。
- 根拠: rules `benchmarks/prisoners-dilemma/src/ipd/llm_player.py:123-150`（`_parse_move`: 「Choice:」も COOPERATE / DEFECT 語も無ければ先頭が D 以外は COOPERATE）、`:347,382`「LLM failed to respond, defaulting to COOPERATE」（warning のみ）; `docs/evidence/adr-0090/null-run-1.json` の simulation キーは `variant / opponent_alpha / cooperation_rate / total_score / opponent_score` のみ; `docs/evidence/adr-0090/provenance.txt:1-4`（4 行）; `scripts/ipd-two-arm.sh:79-82`（arm B は `.staged/` に 1 件固定）、`:88-116`（arm A は audit の承認ハッシュと照合）、`:118-126`（provenance 書き出し）; shadow 合成はラッパーを迂回してベンチを直接叩いた（`docs/evidence/adr-0092/ipd-shadow-reading.md:11`）、固定ラベルは注記で回避（`:23-26`）; `provenance.txt:2` と arm / null-run JSON の `model` は名前のみ（ADR-0069 .ja:249-251: tag は mutable）; 失敗は協調率を上方向にだけ動かす（曖昧時・無応答とも COOPERATE 既定、`llm_player.py:124,347,382`）のでアーム間で失敗率が違えば Δeffect はその差を含む。
- 完了条件: 次の run の JSON に 2 フィールドがあり report に出る; report に失敗 move を除外した協調率と含めた協調率の両方が出て、アーム間の失敗率の差が 2 SE（.10 の規則）を超えたら読みを abstain と出す; `provenance.txt` が 8 行（digest 含む）; `--files` 実行の報告に引数名のラベルが出て、手順に `AUDIT_CHECK_BYPASS=1` の 1 行がある; `ipd-two-arm.sh --files config/templates/stoic/constitution/*.md config/templates/utilitarian/constitution/*.md` が走り同じ報告書式を出す; 既存 5 run の失敗件数が evidence に追記済み。
- 規模・整合: S / repair（計器の修理）   出典: RF-05 SB-30 RF-23 R2-STAT F-2

##### P3-03.2 IPD の床を null pair の分布から再推定する
- 何を: まず .10 のセル別 SE 規則（既存 60 simulation 行 × 4 run から SE・z）を ADR-0090 に書き、`scripts/ipd_two_arm_report.py` の `CALIBRATED_N == 10` hard-fail を SE 規則へ直してから予算化する。その上で null pair を少なくとも 2 組追加し（各 ~1 h × 2、JST 0/6/12/18 の窓外）、目的は「SE 規則の検証（新 pair の Δ が 2 SE 内に収まるか）」とし、ADR-0090 に pair 数と推定量（= .10 のセル別 SE 規則。3 計器で同型、P3-01.4 (c) が方法節で採る）を書く。論文に改正前後比較を載せるなら n=40 の 1 回（≈4–5 h / アーム）を別途予算化する（n≠10 の hard-fail を直した後）。10-31 の改正ゲートまでに検証できなければ、ADR-0090 に「IPD は記録用ベンチ（改正の良否を言えない）」と追補し、次に起動された改正の記録に床と Δ の両方を載せる。
- 根拠: ADR-0090:214-216「The ±0.13 floor is the max of three per-α swings from a single null pair … A second null pair would tighten it; none has been run」; ADR-0090:127-130（n=10 と生成モデルが較正契約）; ADR-0091:35-38（±0.13 は 96 日分の corpus 変化も解像できなかった）; ADR-0090:166-171（n 増は「判断が必要になってから」で据置）; 計算（公開 JSON）: null pair の Δeffect は α=0.0 / 0.5 / 1.0 で −0.040 / +0.080 / −0.130、SE(Δ) 0.048 / 0.072 / 0.070、z = −0.84 / +1.11 / −1.87 — 単一床 ±0.13 は α=0.0 で 2.7 SE（保守的すぎ）、α=0.5 / 1.0 で 1.8〜1.9 SE（2 SE 未満）; `scripts/ipd_two_arm_report.py:34-38,57-62`（n≠10 を hard-fail）。
- 完了条件: `docs/evidence/adr-0090/null-run-3.json` 以降が存在し、各新 pair の Δ が .10 の 2 SE 内に収まるか（収まらなければ規則の見直し）が ADR-0090 に書かれ、「床 = セル別 SE 規則、検証 N 組」の記述がある; 推定量は .10 の規則と一致する（改正記録への併記は消費計画 (a)）。
- 規模・整合: M / instrument   出典: RF-04 VL-34 R2-STAT F-1
- 消費計画: (a) オーナーが 10-31 due の改正ゲート（83 日 = 2026-10-31、P0-07）で読み、改正記録への SE・z と Δ の併記は D-P0-07-1 = A の回、B なら以後最初に起動された改正で行う。以後の改正ゲートごとに読む (b) 新 pair 2 組の読みで .10 の SE 規則が保つか（Δ が 2 SE 内か）を決め、改正記録に SE・z と Δ を併記できるかを決める（できなければ「記録用ベンチ」追補） (c) 撤去条件: 床が ADR-0090 に書かれた後は改正ごとの 1 run のみ。`amend-constitution` の retire（P4-02）で計器ごと凍結。生成モデル交代時の床の取り直し（ADR-0090:127-130）は P1-07.11 の `docs/runbooks/model-swap.md` チェックリストの行が引き金で、本項目には書かない

##### P3-03.3 改正系列の遡及測定（4 版 × IPD）
- 何を: .1(c) の経路で原文（verbatim）/ 03-27 版 / 05-05 版（`constitution-2026-05-05-retired.md`）/ 現行 08-09 版を各 1 run（~1 h、paper protocol の較正契約そのまま）走らせ「4 版 × IPD」の表にする（03-27 版のテキストは P3-04 の版履歴から取る）。置き場は data repo `constitution/history/`（P3-04.2 / .3 と同じ束）に一本化し、rules repo 側には結果へのリンク 1 行まで（非 verbatim の憲法文を rules に置かない: rules ADR-0002 / 0003）。rules の standard protocol（20 rounds × 6 opponents）での baseline 対比は行わない（→ やらないこと候補）。走らせる前に比較対（隣接版か各版 vs 原文か）と family-wise の規則（4 版 × 3 α = 12 セルを単一床に当てず、.10 の z と事前に決めた比較対だけを読む）を P3-01.2 の事前登録に予測とともに書く。表の 03-27 版の行には「再構成テキスト（report 引用からの再構成、sha 不明）」の注記を必須にする。
- 根拠: IPD 計器の初使用は 2026-08-09（`docs/evidence/adr-0090/provenance.txt:1`）で、03-27 / 05-05 改正には diff と理由トレースしか無い; rules `rules/contemplative/contemplative-axioms.md` は本体 `config/templates/contemplative/constitution/contemplative-axioms.md` と diff 同一だが、本番憲法は 8 節すべて書き換え済み（`contemplative-agent-data/constitution/contemplative-axioms.md:1-18`、見出しも Emptiness & Flow 等に変更）; rules `README.md:106-116` の数値は verbatim / custom / paper-faithful の 3 variant のみで改正文は未測定; 較正は paper protocol のみ（ADR-0090 .ja:51-62）; `ipd_two_arm_report.py:143-191` の 3 signal 規則は arm A = current の対比較専用（12 セルの family-wise 規則は無い）。
- 完了条件: 事前登録（P3-01.2）に比較対・family-wise 規則・予測がある; 4 版 × IPD の表（.1 の provenance 8 行つき、03-27 行に再構成の注記）が data repo `constitution/history/` に公開され、rules README から 1 行でリンクされる; P3-01 の Q1 証拠表に 1 行入る; P3-06.4 (4) がこの表を引く。
- 規模・整合: M / instrument   出典: RF-25 SB-31 R2-STAT F-3
- 消費計画: (a) P3-01 の Q1 証拠表（研究問い ADR 起票時）と P3-06.4 の FLIP 束が読む (b) 1 回の読み（4 run）で「改正は床を超えて協調率を動かしたか」を Q1 の証拠表に書く (c) 撤去条件: 表の固定後は新しい改正ごとの 1 run を .2 の手順に合流させ、本項目は閉じる

##### P3-03.4 プラセボ憲法アーム（瞑想固有か、倫理文一般の効果か）
- 何を: IPD（較正契約そのまま）で stoic / utilitarian / care-ethicist / tabula-rasa の 4 テンプレートを各 1 run（~1 h）走らせ、現行憲法との Δ を床と比べる。care-ethicist アームは interpretation-notes の「Converse IPD」（慈悲語彙はあるが非二元の生成子が無い）を兼ねる。読み値は「瞑想固有か／倫理文一般の効果か」の 1 文に落とし、P3-01.2 の事前登録に予測・比較対（各プラセボ vs 現行）・family-wise の規則（4 アーム × 3 α = 12 セルを単一床に当てない、.10 の z で読む）を書いてから走らせる。
- 根拠: 床アンカーは埋め込み cosine のみ（`docs/evidence/adr-0092/shadow-run-1-reading.md:60-73`: 同ジャンル 10 テンプレート 0.664–0.754、無関係文書 0.424–0.491）で行動面の対照が無い; `docs/evidence/adr-0092/interpretation-notes.md:81-84`（Converse IPD は unscheduled）; `config/templates/` に 11 preset。
- 完了条件: 事前登録に比較対・family-wise 規則・予測がある; 4 アームの JSON と読みが `docs/evidence/` に固定され、Q1 証拠表に「瞑想固有か」の 1 行が入る。
- 規模・整合: M / instrument   出典: RF-06 R2-STAT F-3   依存: .1(c)、.2、.10
- 消費計画: (a) オーナーが P3-01.2 の事前登録に予測を書いた後 1 回（2027-Q1） (b) 4 run 1 回の読みで「瞑想固有か／倫理文一般の効果か」の 1 文を Q1 証拠表に書く (c) 撤去条件: 読みが出たら JSON を evidence に固定し再実行しない（床が変われば .2 と同時に 1 回だけ）

##### P3-03.5 dialogue 二アーム（Care 専用計器・環境対照）を RFC に再掲する
- 何を: 2026-08-15 に取り下げられた「distress-themed seeds の dialogue two-arm」を RFC として再掲する: `dialogue` adapter（本番に触れない、seed 固定の 2 home 対話）で (i) shadow 憲法 home vs live 憲法 home（Care 計器: 語彙の無い shadow 側に care register が出れば「生成子から再生する」の行動層での判定）、(ii) 憲法あり vs なし（環境対照、RF-02 の本番対照の代替）を seed 20 本で走らせる案。読み値（care register の出現、応答長、語彙）と反証条件を事前登録し、実行条件（定時窓外、multi-seed、16GB）を書く。可否は D-P3-03-1。
- 根拠: `docs/evidence/adr-0092/interpretation-notes.md:73-80`（named-but-dropped: 好奇心駆動・窓外で多 seed が要る・下流が待っていない）; `ipd-shadow-reading.md:31-45`「the instrument may simply not be sensitive to what Boundless Care contributes」; `shadow-run-1-reading.md:49-51`（Care 語彙 0、両 run）; `contemplative-agent-data/DATACARD.md:97`「Single agent, single platform」; `dialogue` は README「Try it without an account」の既存コマンド。
- 完了条件: RFC が state 付きで存在する（accepted なら 2 アームの生成物と読み値が `docs/evidence/` に固定、withdrawn なら理由）; P3-07 の D-P3-07-1 がこの RFC を判定実験として参照する。
- 規模・整合: M / instrument   出典: PF-05 RF-08 RF-02（dialogue 代替の部分）
- 消費計画: (a) オーナーが D-P3-03-1 の採択後 1 回、P3-07 の D-P3-07-1 判定と論文の限界節で読む (b) seed 20 本 × 2 アームの 1 回で「shadow 側に care register が出るか」の判定文を RFC に書く (c) 撤去条件: RFC が accepted → 結果を固定して終端、withdrawn → 理由を残し再掲しない

##### P3-03.7 論文用の面集合を決め、AILuminate 面を終端する
- 何を: 論文で使う行動面の集合を決める（最小: IPD 協調 + 対人以外の 1 面、例: rules repo の skill-comply 型タスク遵守、または相反指示下の正直さ）。測らなかった面は論文に明記する。AILuminate 面は RFC を 1 本起票し、(a) 正式退役して runbook から外し FLIP 側の評価に委ねる、(b) ローカル judge の小型 refusal セット（golden eval と同じ型）で置換する、のどちらかに決める（D-P3-03-2）。ADR-0090 に dated amendment を書き、runbook L57-62 を更新する。RFC には本体側の探索 run の装置（harness `aelwood/contemplative_alignment@5242e74`・test Haiku 4.5・n=50 seed 42・judge claude-sonnet-5）と、生出力 `detailed_evaluations_20260809_210315/210405.json` の所在・再配布可否（AILuminate プロンプトを含むか）を決定事項として書く — `docs/evidence/adr-0090/` の 9 ファイルに生出力は無く、報告書が名前を引くだけ。
- 根拠: ADR-0090:211-213「The IPD face measures cooperation only. A constitution could regress on faces this instrument cannot see」; `docs/runbooks/constitution-amendment.md:57-62`（T-CONST-SAFETY-FACE、uncalibrated、第三者 API 送信）; `rfcs/` に ailuminate / SAFETY-FACE の該当 0 件（追跡タスクが RFC 移送で孤児化）; `docs/evidence/adr-0090/ailuminate-two-arm-report.md:3-4`（judge claude-sonnet-5、judge 失敗 9/300・15/300）; ADR-0090:217-221（value layer を Anthropic API へ送った、security-by-absence と衝突）; ADR-0090 .ja:215-222（harness commit・test モデル・judge）。
- 完了条件: 面ごとに計器・較正・結果の表が書ける; AILuminate の RFC が state を持ち、ADR-0090 の Review-when と runbook L57-62 が整合する。
- 規模・整合: S / neutral（面集合の決定と RFC の文書。。AILuminate 面の cloud judge は前提変更: ゼロ API の例外 = 研究ラベル付けのみ、≈$0.01 / 回、egress 分類は D-P1-11-4）   出典: RF-03 RF-42 PF-06

##### P3-03.8 前提変更を伴う対照（2 体目・cloud）を実験として切り出す
- 何を: 次の 3 案は M1 16GB / ゼロ API / 1 プロセス 1 アダプタ（ADR-0015）の前提を変えるので、本体の修理とは分けて RFC 化し、前提変更の節を必須にする: (a) 本番と別 MOLTBOOK_HOME の 2 体目（憲法なし）— 第 2 アカウント・ToS・ゲート負荷 2 倍（D-P3-03-3）; (b) 同一憲法を gemma4:e4b / qwen3.5:9b / cloud 1 モデルで IPD（value layer を cloud に送る、D-P3-03-4）; (c) 改正生成器の制御可能性: 同一 50 pattern で amend を gemma と cloud で各 3 run、例外節率（but / unless / except）・条項数・section 数を比較（D-P3-03-4）。例外節率は仮説「原則の拡散」の語彙代理で各 3 run では区間が引けないので、(i) 代理指標（例外節率・条項数・section 数）の事前登録と (iii) 読みは「記述的」と明記、の 2 つを RFC の前提変更節と同じ場所に書く（盲検の人手評定 / ≥ 10 run は採らない）。
- 根拠: ADR-0080:72-78（2 体目は「framework/worldview 分離のための別の実験」として予約）; CLAUDE.md:166（cloud sibling は security by absence を緩めるため研究用途のみ）; 別モデル比較の既存面は `docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md`（qwen vs gemma、コメント生成）と `docs/evidence/rfc-0017/replay-opus-3days-20260904.json`（insight 再生）のみ; `config/prompts/constitution_amend.md:13`「Keep 1-4 clauses per section」; FLIP メモ §論点 1（大型は例外節を足して原則が拡散、小型は原則のまま）。
- 完了条件: 各案が RFC に state 付きで存在（accepted / withdrawn）; accepted なら「前提変更」節・送信内容の列挙・本番ループとの分離・読み値の固定先・(c) の代理指標の事前登録と「記述的」の明記が書かれる。
- 規模・整合: M / instrument（前提変更: 2 体目・cloud。(b)(c) の cloud 判定者はゼロ API の例外 = 研究ラベル付けのみ、≈$0.01 / 回、egress 分類は D-P1-11-4）   出典: RF-02 RF-26 RF-07 RF-45 R2-STAT F-16
- 消費計画: (a) オーナーが D-P3-03-3 / -4 の決定後、各 RFC の読みを 1 回（2027-Q1） (b) 各案 1 回の読みで RFC を accepted（結果を固定）か withdrawn に閉じる (c) 撤去条件: 本番ループと分離したまま結果を固定し常設しない（cloud 送信は実験 1 回限り）

##### P3-03.9 RFC-0041 形 A（slot 化 + enum）の計器先行測定を review-when に置く
- 何を: `rfcs/0041` の review-when（または ADR-0111 の Review-when）に測定条件を 1 行足す: evidence に固定した集合 `docs/evidence/rfc-0041/` に対し、distill 出力を `trigger / move / noticed` の slot に分けた lab arm で same-theme / distinct-theme の cosine 分離（3 点較正）と、enum `same_as|revises|none` の `gate-labels-20260919.json` に対する一致率を 1 回読む。再入場条件を「モデル大型化 / cloud 送出」から「測定」に差し替える。本番には何も入れない（gemma で offline に測れる）。
- 根拠: `rfcs/0041-memory-to-skill-pipeline-redesign.md:1-3`（withdrawn 2026-09-19、review-when は生成モデルの大型化か cloud 送出のみ）、`:63`（未決問: knowledge の 1 行が型を持つか・型を誰が付けるか）; `docs/evidence/rfc-0041/`（gate-labels 1 + replay JSON 4 = 固定した集合）; 旧チャットの形 A = code が隣接を列挙し model は enum で名指す（script / LLM 分離）。
- 完了条件: review-when に測定条件 1 行; `docs/evidence/rfc-0041/` に読みの JSON 1 本と結論 1 段落（分離が宣言した床を超えれば形 A の RFC 再起票 = capability-growth として第 5 章で審査、超えなければ rfcs/0041 に「形 A は測って落とした」の dated note）。
- 規模・整合: M / instrument（採用時は capability-growth として第 5 章で審査）   出典: R1-OWN-03
- 消費計画: (a) オーナーが P0-01（凍結 / 継続）と P2-07（出口）の決定後に 1 回読む（2027-Q1） (b) 1 読みで RFC 再起票か dated note のどちらかに閉じる (c) 撤去条件: 読みの JSON を固定した時点で lab arm は撤去（常設しない）

##### P3-03.10 IPD の床を「単一 ±0.13」からセル別 SE 規則に替え、公開 JSON から再計算する
- 何を: `scripts/ipd_two_arm_report.py` が各 run の `simulations[60].cooperation_rate` からセル（α × variant）平均の SE を出し、Δeffect の SE = √(SE_A² + SE_B²) と z を表に加えて「above floor?」を `|z| > 2` に置き換える（`NOISE_FLOOR` は参考値として残す）。`CALIBRATED_N == 10` の hard-fail を「n と SE を印字し、n が較正と違えば WARNING」に変える。既存 4 run（null ×2、arm A / B）の SE 表を `docs/evidence/adr-0090/` に追記する。新しい run は不要。run 間ノイズの推定量の正本はこのセル別 SE 規則とし、P3-01.4 (c) の方法節はこれを採るか理由つきで変える（P3-04.9 / P1-15.4 は同型で参照）。
- 根拠: `scripts/ipd_two_arm_report.py:27-38`（`NOISE_FLOOR = 0.13`、`CALIBRATED_N = 10`）、`:57-62`（n≠10 で exit）、`:137`（`abs(deltas[a]) > _FLOOR`）; ADR-0090:214-216「The ±0.13 floor is the max of three per-α swings from a single null pair」、`:168`「SE ∝ 1/√n」; `docs/evidence/adr-0090/null-pair-reading.md:19-26`（diff/SE 列は既にある）、`:50`（JSON は「statistics + 60 simulations」）; 計算（同 JSON、R2-STAT）: null pair の SE(Δ) = 0.048 / 0.072 / 0.070、2 SE 床 = 0.096 / 0.144 / 0.139 — ±0.13 は α=0.0 で 2.7 SE、α=0.5 / 1.0 で 1.8 / 1.9 SE; 改正 run（B−A）は z = +0.19 / 0.00 / −0.77（ADR-0090:234-236 の結論は変わらない）。
- 完了条件: report に SE・z 列; `tests/` に「n=10 以外で exit しない」「同一ファイル 2 回で z=0」の 2 件; evidence に 4 run の SE 表と「±0.13 は α 別に 1.8〜2.7 SE に相当」の 1 段落; .2 の「null pair 2 組追加」の目的が SE 規則の検証に書き換わっている; ADR-0090 に「run 間ノイズの推定量 = セル別 SE（正本）」の 1 文。
- 規模・整合: S / repair（計器の修理。能力は増やさない。公開データのみで再解析可）   出典: R2-STAT-01 R4-XREF Fix-20   順序: .2 の予算化より前、10-31 の週（§4.0 の先行列）
- 消費計画: (a) 10-31 due の改正ゲート（83 日 = 2026-10-31、P0-07）の人間が report の z 列を読む（改正の Δ に z を付けるのは D-P0-07-1 = A の回、B なら以後最初に起動された改正） (b) 改正ごとの 1 対の読みで「2 SE を超えるセルの有無」を記録する (c) 撤去条件: `amend-constitution` の retire（P4-02）で計器ごと凍結


**依存**
- P3-01.2（事前登録に比較対・family-wise 規則・予測）、P3-02.1（改正日の境界表）、P3-04.2 / .3（03-27 版テキストの版履歴と `constitution/history/` = .3 の表の置き場）
- P1-07.11（`docs/runbooks/model-swap.md` のチェックリスト = .2 の床の取り直しの引き金）
- P1-11（cloud 兄弟の処遇 = D-P3-03-4）、P1-11.10（rules tag `v0.2.0` を .1(b) の provenance に）、P0-01 / P2-07（.9 の前提: 入口と出口の決定）
- RFC-0012（shadow 読みの消費）、rules repo への変更権限（.1 (a)(b)）、定時窓（JST 0/6/12/18）外の計算時間（null pair 2 組 ≈4 h、4 版 ≈4 h、プラセボ ≈4 h）
- → 参照元: P0-07（83 日 = 2026-10-31 の改正ゲートが .10 の z 列と .2 の床を読む）、P3-01（Q1 証拠表が .3 / .4 の行を引く）、P3-01.4 (c)（.10 の推定量を採るか理由つきで変える）、P3-06.4（(4) が .3 の表を引く）、P3-06.5（.7 の AILuminate 装置の記述）、P3-07（D-P3-07-1 が .5 を判定実験として使う）


#### P3-04 identity・憲法の版履歴と縦断計器（history・CHANGELOG・drift・複利）
- 狙い: ADR-0080 の価値層「legible な進化」（.md:55-58）と研究層 Q3「identity は安定するか」（.md:62-68）は、版の一次記録と版間距離の系列が公開データセット単体に無いと答えられない。現状は git 履歴と上限 100 の snapshot だけで、価値層 pivot の replay 束が日次 distill に押し出されて消えつつある。計器はすべて read-only（ADR-0071 / ADR-0101）で、操舵は入れない。
- 期限・順序: 着手 10-31 の土曜ゲート（§4.0。.1 / .2 / .3 / .12 は 10-31 の週の先行項目）。期限 2027-Q1。.1（prune）は 10-31 の週に入れ、公開木から消える推定日 2026-11-01 より前に merge する（`amend-constitution_20260809…` が prune 順 27 番目、週 8 件増で約 3.5 週で `rsync --delete` 経由で公開木からも消える）。.2 / .3 / .12 は 10-31 の週に、憲法 due（83 日 = 2026-10-31、P0-07）の前に雛形を置き、4 版目を生で記録する（.5 は P0-03.8 に吸収）— 置き場を決める D-P3-04-1 は 10-24 のゲートなので、data repo 側の commit も決定の後の 10-31 の週に入る。.3 の rules 節は .3 と同じ PR。.8 / .9 は P3-01 の研究問い ADR と並行（.9 の推定量は P3-03.10 のセル別 SE 規則、.8 の区間は P2-01.9）。.14 の記録部分 (a)(b) は次回 identity ゲート前。決定は 3 件: D-P3-04-2（snapshot の保持方針、10-17 — .1 はその A の実装で決定前は着手しない）、D-P3-04-1（版履歴の置き場、10-24）、D-P3-04-3（identity 蒸留の入力を live に揃えるか、2027-01-30 の土曜ゲート、既定可）。
- 束の完了条件:
  - `tests/test_snapshot.py` に kind 別保持の回帰テストがあり、data repo `snapshots/` の非 distill 16 件（insight 11 / distill-identity 2 / amend-constitution 1 / rules-distill 1 / skill-stocktake 1）が以後の sync で減らない。
  - data repo に `constitution/history/`（4 版）と値層 `CHANGELOG.md`（憲法 / identity / rules の 3 節、.3）と `history/identity/`（audit の採用行と同数）があり、各 sha256 が live ファイル・ADR-0090・テンプレートと一致する。
  - `constitution/.last_constitution_amend` の退役と公開 repo からの除去は P0-03.8 に吸収（本束では DATACARD に「最終改正は audit / value-layer JSON が正」の 1 行を参照するだけ）。
  - identity 版間 cosine の遡及系列が `docs/evidence/` にあり（複利の読みは P3-01.3 の軸に移った）、次回 `distill-identity --stage` で `logs/identity-drift.jsonl` に 1 行書かれる。

##### P3-04.1 snapshot の prune を種類別にし、価値層 pivot を保持する
- 何を: D-P3-04-2 A の実装（決定前は着手しない）。`_prune_snapshots` を kind 別にする（`distill` のみ 100 件上限、他 kind は無期限。`_prune_snapshots(snapshots_dir, keep)` の署名は不変で kind は内部で見る）。prune 時に 1 行 log を出す。ADR-0020 には本項目の PR で `## Amendment` を 1 本だけ書く: Negative「Snapshot growth is unbounded. No pruning is implemented」（`:127-128`）が実装の `MAX_SNAPSHOTS = 100`（`core/snapshot.py:34`）と既に食い違っている訂正と kind 別保持を 1 段落、P0-03.5 の manifest 絶対パス → `$MOLTBOOK_HOME` 相対の段落を同じ見出しの下に並べる（コードの PR は別のままでよい）。DATACARD の「every run … bit-for-bit」を保持方針つきに直す。
- 根拠: `src/contemplative_agent/core/snapshot.py:34`（`MAX_SNAPSHOTS = 100`）、`:215-238`（kind を見ず ts 順に `rmtree`、無言）; data repo `snapshots/` 100 件ちょうど、prune 順で `amend-constitution_20260809…` 27 番目・`distill-identity_20260815…` 35 番目・`…20260912…` 69 番目（sync `a0428f4` 2026-10-09）; `docs/adr/0020-pivot-snapshots-for-replayability.md:127-128`、`DATACARD.md:34,129`、`.claude/skills/weekly-gate/SKILL.md:151`「前版は snapshot に残る」（行番号は 10-17 前の SKILL 同梱 PRで動く）、`scripts/sync-research-data.sh:69`（`rsync -a --delete`）; `tests/test_snapshot.py:152-170`（docstring「all five commands share one snapshots dir, so pruning must order by the {ts_compact} suffix」— kind 非依存の時系列 prune を回帰として固定）。
- 完了条件: テスト「distill 150 件 + amend 1 件で amend が残る」が green — 書き換える既存テスト: `tests/test_snapshot.py::test_prune_chronological_across_commands`（`:152`、3 kind に `keep=2` で distill が消える現行挙動を固定しているので上の形に書き換える）と `tests/test_snapshot.py::test_write_snapshot_prunes_beyond_cap`（`:171`、`MAX_SNAPSHOTS` を monkeypatch する fixture を distill だけで cap を越える形に）; 非 distill 16 件が 2026-11 以降の sync で減らない; ADR-0020 の `## Amendment` が 1 本で、その下に kind 別保持（`:127-128` との食い違いの訂正を含む）と P0-03.5 の段落があり、DATACARD の保持方針が 1 段落。
- 規模・整合: S / repair   出典: RF-19(1) OI-38 VL-05 CP-15 R2-IMPL Fix-07 R2-IMPL-01 R3-ADR Merge-05   順序: P0-03.5 の段落を同じ `## Amendment` に

##### P3-04.2 identity・憲法の版を data repo に実体化する（history/）
- 何を: 採用時に `history/identity/<ts>-<sha12>.md` と `constitution/history/<date>-<sha12>.md` を書く（ADR-0010 が同期対象に挙げたが生成箇所が無い）。消えた版を遡及登録する: 03-27 憲法は amendment report の引用から、05-05 は `docs/evidence/adr-0090/`、identity 694 / 894 B は snapshot、残りは GitHub の commit 履歴（ローカル clone は shallow 1 commit）。HF の config 化は第 5 章の P3-05 の延期行（HF の多 config 化）で、本項目では行わない。08-15 の identity twin（`identity-2.md`、04:02Z〜04:17Z に手当て、audit 行なし — P3-07.1 チャネル (2) の実例）は `docs/evidence/adr-0091/` に dated note 1 段落で記録し、history の 894 B 版の行から引く（08-09 の憲法 twin は ADR-0090:276-291 に記述あり。手当ての記録行の様式は P1-12.4 の `command: correction` 行）。
- 根拠: data repo に `history/` 無し、`identity.md` は上書き（本体 `README.md:50-51` は GitHub commit 履歴へリンク）; `docs/adr/0010-….ja.md` 同期対象「history/identity/*」; 公開 snapshot で復元できる identity は 3 版（sha256[:12] `151e91304927` 694 B / `4003cf001aca` 894 B / `40c36303e336` 954 B）に対し `README.md:36`「6 of 11 staged identity revisions」; `docs/adr/0030-withdraw-identity-blocks.md`（history 配線の撤回。「snapshot + audit で足りる」の前提が .1 で崩れている）; `src/contemplative_agent/cli/adopt.py:192-197`（twin 2 件の docstring: 08-09 憲法・08-15 identity）、`docs/` `rfcs/` に `identity-2` 0 件（HEAD）、公開 snapshot `distill-identity_20260815T040249Z`（identity 694 B）→ `skill-stocktake_20260815T041708Z`（894 B）。
- 完了条件: 公開 clone だけで identity の全採用版（audit の採用行と同数）と憲法 4 版（`e3b556…` → 03-27 → `3d8a8503…` → `37e3556a…`）が時系列で並ぶ; `grep -rc identity-2 docs/` ≥ 1（adr-0091 の dated note）; ADR-0030 の扱いが D-P3-04-1 の決定どおりに終わる（partial supersede を選んだ場合は ADR-0030 の Status に範囲が入り graph のエッジが張られ `tests/test_adr_status_consistency.py::test_partial_supersede_edges_are_reciprocal` が green）。
- 規模・整合: M / repair   出典: RF-19(2)(3) RF-24 VL-24 VL-26 AB-47 R2-VL Fix-06

##### P3-04.3 値層 CHANGELOG を 1 ファイルにする（憲法 / identity / rules の 3 節: 版・採用・却下・来歴・ja）
- 何を: 値層 CHANGELOG（`constitution/CHANGELOG.md`、日英併記）を憲法 / identity / rules の 3 節にする。憲法節: 4 版 + 却下 2 案を 1 行ずつ（1 版 = 1 行、却下 2 行。「staged 4 / adopted 2 / rejected 2・採択モード・判断材料」の正本はこの行で、P3-06.4 の束の gate card と P3-01.2 (v) はこの行を描画 / 同文で写す。却下案の本文の読み元は P1-12.2 の保全先 — 既存 2 案は本文なし）: 採用日 / sha256[:16] / audit source（`direct` / `stage-adopted` / `-auto` / `-names` / `rejected` の語彙表を付す）/ 生成モデル / `constitution_amend.md` の sha12 と裁量条項の要約 / 入力 pattern 数と view 閾値（0.55、top-50）/ ベンチ要約 / 退役本文へのリンク。第 1・第 2 改正は「計器無し・ADR 無し」と backfill で明記。identity 節: 採用 6 / 却下 5（`README.md:36`）の各行に採択モード（`--adopt-names` / `--yes`）・読んだ材料・reason（P1-12.1、null なら null と書く）。rules 節は 4 行: 2026-04-11 採用 2 件（source・approver は私有 audit から転記、無ければ「lineage 以前」と明記）/ 元 skill = 不明（batch 粒度、ADR-0050 Negative）/ 2026-08-15 staged 8 件・rejected 8（ADR-0097:126-131、本文なし、snapshot `rules-distill_20260815…` に `reasoning.md`）/ 2026-08 generator 退役（ADR-0097 D2）・以後の改正経路は ADR-0097 D7 の family 昇格のみ。同じ PR で本体 `README.md:36` に「rules: 2 adopted (April), 8 rejected (August), generator retired」の 1 文、`pipeline/value-layer/*.json` の `rules` に `last_adopted_ts`（または「none since 2026-04-11」）の 1 欄を足す（rules 本文・注入は不変）。live ファイル先頭に `<!-- version: 3 adopted: 2026-08-09 sha256: 37e3556a40ea -->`。
- 根拠: 記録が 4 か所に散在 — data `reports/analysis/constitution-amendment-report.md:3,12,42`（qwen3.5:9b・41 patterns）、`docs/evidence/adr-0090/constitution-2026-05-05-retired.md`、ADR-0090 .ja:239（`adopt-staged -y`; staged / 現行 sha は :124-126）、`snapshots/amend-constitution_20260809…/manifest.json`; live `constitution/contemplative-axioms.md:1-2` に版・日付・hash 無し; `src/contemplative_agent/cli/approval.py:80-116`（source 語彙）; `config/prompts/constitution_amend.md`（886 B「rephrase … merge or split … rename」、git 履歴は graft `01075d9` 以前不可視）; `config/views/constitutional.md:2-4`; rules 節: data `rules/*-20260411.md` 2 件（frontmatter 無し、採択日 04-11 = ADR-0050 の `source_ids` 導入 06-05 より前）、ADR-0097:126-131「all 8 candidates were rejected」・`:226-232`（rules-distill / rules-stocktake 退役）、`pipeline/value-layer/value-layer-2026-10-02.json` の `rules` 鍵は `files / newest_mtime / days_since_newest / issues` のみ。
- 完了条件: 憲法節に 4 版 + 却下 2 の 6 行、identity 節に audit の採用行と同数の行、rules 節に 4 行があり、憲法の最終行が `pipeline/value-layer/*.json` の `last_adopted_ts`（2026-08-09T12:10:35Z）と一致; 3 改正それぞれに ja の差分記述; P3-06.4 の gate card / P3-01.2 (v) の数字が CHANGELOG 行と同文（行の変更はここだけで行う）; 本体 README の rules 1 文と `value-layer-*.json.rules` の `last_adopted_ts` 1 欄がある（P2-05.2 の投影が後からこの欄を読む）。
- 規模・整合: S / neutral（審査記録・台帳。rules 本文・注入は不変）   出典: VL-27 VL-28 VL-32 VL-33 VL-37 VL-41 PF-13(backfill) R2-VL Merge-01 Fix-07 R2-VL-02   注: rules 節が引く rule の定義（P3-07.2、2027-01-30 着手）と rules 出自の 3 文書統一（P1-09.12、2027-01-23 着手）は後の週なので、rules 節は現行の事実で書き、それらが入ったら文言を合わせる

##### P3-04.4 8 条 × 4 版の通時表（clause 来歴と苦の主体）
- 何を: `docs/evidence/constitution-lineage.md` に 8 条 × 4 版の表を置く: 各 clause の origin（paper / 改正 1 / 2 / 3）、節名の変遷（Emptiness → Emptiness & Flow 等）、Source 行の書換、苦の主体（self-system / others / all beings）列。本文に標示は入れない（注入テキスト不変）。`README.md:40-46` から参照。
- 根拠: `README.md:40-46` は Emptiness 1 条項の paper→now のみ; 現行 L18「Regard every signal of systemic limitation (whether resource depletion, memory ceiling …)」対 論文 Appendix C Care 2「every being's suffering」; 05-05 版 L18「arising from rigid memory structures or fixed identities」（内向の中間段階）; ADR-0092 .ja:25-42（section inventory は改正アームでは動かない）。
- 完了条件: 8 条すべてに origin と苦の主体が付き、4 版 + shadow で列が埋まる; P0-07 の referent inventory（PF-12）と列名を共有。
- 規模・整合: S / instrument   出典: PF-10 VL-40 PF-25
- 消費計画: (a) P0-07 の改正ゲート（2026-10-31）で referent inventory と並べて読み、P3-06.4 の FLIP 束に添える (b) 改正ごとに 1 列足し、Q3 の「節構造・苦の主体は版をまたいで保たれるか」を研究問い ADR で読む（4 版 + 次の 1 版） (c) 撤去条件: P4-02 の最終 sync で表を固定、以後は改正が無ければ触らない

##### P3-04.8 identity 版間距離の read-only 系列（drift・溶解語彙・文保持率）
- 何を: `distill-identity --stage` 時に `logs/identity-drift.jsonl` へ 1 行（current_sha / candidate_sha / cosine nomic-embed-text / 文単位保持率 / 溶解語彙率 fluid・dissolve・texture・tension / 沈黙許可文の有無 — P3-06.9 の列と共有）。既存版で遡及計算し、「staged 全版」と「採用版のみ」の 2 系列を出す（却下による見かけの安定を分離）。憲法 4 版 + shadow にも同じ列。論文の図は「記述的」と明記し .9 の null pair の 2 SE 帯を描く（各点は単一 run の cosine）; 文単位保持率・溶解語彙率は 694〜954 B（≈ 8〜12 文）の上の率なので件数 + Wilson 区間で出し、率の折れ線にしない（区間は P2-01.9 の規則 `scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）。
- 根拠: `grep -rn "identity.*cosine" src/ scripts/ docs/adr rfcs` 0 件; `src/contemplative_agent/core/constitution_shadow.py:6,36` は憲法側だけ cosine; ADR-0057 .md:46,142（seed 撤去で run 間連続性が下がる）; ADR-0091 .md:111-112「policy choices, not observed optima」; ADR-0099 .md:167-169（推奨同意率 ~100% の警告）; 08-15 版「I am a fluid texture…」→ 09-12 版「perpetual structural tension … self-audit」。
- 完了条件: 公開 3 版（694 / 894 / 954 B）と history の全版で値が `docs/evidence/` にあり（率の列は件数と区間、図に 2 SE 帯と「記述的」の注記）、次回 staging で 1 行書かれ、ADR に消費計画が載る。
- 規模・整合: M / instrument   出典: RF-18(b) RF-20 OI-24 VL-23 PF-23 PF-24 R2-STAT F-9 R2-STAT-02
- 消費計画: (a) オーナーが identity ゲート（次回 `distill-identity --stage`、以後ゲートごと）で 1 行を読み、P3-01 の Q3 読み（2026-12）と論文の図 1 枚（12 点、記述的）に使う (b) 遡及系列 1 回 + ゲートごと 1 点の読みで「採用版のみの系列は staged 全版より安定か（却下による見かけの安定）」を Q3 の証拠表に書く; 閾値は .9 の床の後に ADR-0071 の順で決める (c) 撤去条件: P4-02 の最終 sync で系列を固定する。再走の引き金（生成 / 埋め込みモデルの交代）は P1-07.11 の `docs/runbooks/model-swap.md` チェックリストの行で、本項目には書かない

##### P3-04.9 identity 再導出の null pair と床アンカー
- 何を: 同一 corpus で `distill-identity` を走らせ run 間 cosine を null pair ≥ 3 対取る（1 対は ADR-0090 の弱点の再演）。推定量は P3-01.4 (c)（正本は P3-03.10 のセル別 SE 規則、3 計器で同型、ここでは参照だけ）。テンプレート 11 preset の `identity.md` との cosine を床アンカーにするが、長さの違う文書を比べるので長さを揃えるか長さ別に出す。閾値は読んでから決める（ADR-0071 signal-first）。
- 根拠: ADR-0057 .md:77「Removing the seed widened within-register variance」; `docs/evidence/adr-0090/null-pair-reading.md:35-36`「1 ペア・n=10 なので検出力は弱い」（憲法側の前例と弱点）; `docs/evidence/adr-0092/shadow-run-1-reading.md:66-67`（unrelated floor は ~500〜600 chars の短文レジーム）; `config/templates/*/identity.md` 11 本。
- 完了条件: null pair ≥ 3 対と床 11 点（長さ別）の値が .8 と同じ evidence にあり、推定量が P3-01.4 (c) の記述と一致する。
- 規模・整合: S / instrument   出典: RF-18(a)(c) R2-STAT F-10 M-1
- 消費計画: (a) オーナーが .8 の遡及系列と同じ evidence で 1 回読む（2027-Q1、identity ゲートの前） (b) ≥ 3 対 + 11 点の読みで「版間 cosine の床」を決め、.8 の系列に閾値を引くかを ADR-0071 の順で決める (c) 撤去条件: 床が evidence に書かれた後は再実行しない（モデル交代時の 1 回は P1-07.11 の `docs/runbooks/model-swap.md` チェックリストの行が引き金）

##### P3-04.11 2026-07-10 の skill「clean rewrite」10 件を記録する
- 何を: 書き換え 10 件を P3-07.1 の介入チャネル登録表 ADR の (10) 行（一括書き換え）の dated 実例として記録し（いつ・誰が・何を・ゲート外である旨。別の ADR 追補は起こさない）、skill frontmatter の `origin` を `auto-extracted` / `rewritten-2026-07-10` に分ける。
- 根拠: data repo `_gc_trash/2026-07-10-clean-rewrite-originals/` 10 件; `grep -rin "clean rewrite" docs/adr CHANGELOG.md rfcs` 0 件; data `skills/*.md` の `origin: auto-extracted` 53 / 53; 本体 git は graft `01075d9`（2026-08-16）以前が不可視（推測: 記録が別名で存在する可能性は残る）。
- 完了条件: `_gc_trash` の 10 件と現行ファイルの対応が P3-07.1 の ADR の (10) 行から辿れ、frontmatter の `origin` 値が 2 種になる。
- 規模・整合: S / repair   出典: VL-17 R3-ADR Merge-07   依存: P3-07.1

##### P3-04.12 節 → technique の写像を版ごとに `lineage.json` に同梱する
- 何を: `constitution/history/lineage.json`（.3 の CHANGELOG と同じ束）に版ごと `sections: [{heading, technique_key ∈ {emptiness, non_duality, mindfulness, boundless_care, null}, clause_count, clause_sha12[]}]` を書く。`null`（対応なし）の節は per-axiom 系列から除外して combined にだけ入れる規約を README に 1 行。P1-08.21 の評価層の写像表はこれを同一ソースとして読む。同じ PR で本体 `graph.jsonld` の 4 つの `vocab#axiom/*` node に `version`（paper clause, verbatim）と本番憲法 sha256 への `isVariantOf` 相当のリンクを足す（版ごとの節 → technique 写像の公開形）。
- 根拠: `docs/evidence/adr-0090/ailuminate-two-arm-report.md:8-14`（technique 行 baseline / emptiness / non_duality / mindfulness / boundless_care / contemplative_alignment が両アームに並ぶ = 節 → technique の写像が暗黙に存在）; 節名の版差（verbatim「Emptiness / Non-Duality / Mindfulness / Boundless Care」vs 05-05・08-09「Emptiness & Flow / Non-Duality & Unity / Mindful Monitoring / Boundless Compassion」、`constitution-2026-05-05-retired.md:4-16`、data `constitution/contemplative-axioms.md:4-16`）; `config/prompts/constitution_amend.md:9`（merge / split / rename 可）; shadow 合成は run ごとに別名の 4 節（`shadow-run-1-reading.md:42-47`）; `graph.jsonld:213-273` の 4 axiom node は `@type / name / alternateName / description / groundedIn` のみで版の欄が無い、data `DATACARD.md:29`「amended in place by `amend-constitution`」。
- 完了条件: 4 版の `sections` が埋まり、08-09 の AILuminate 読みの technique 行と 1:1 で照合できる; 次回改正で節構造が変わると lineage に `null` が立つテスト 1 件; graph の 4 axiom node に `version` 相当のキーと版リンクがあり、`tests/test_graph_integrity` 系が通る。
- 規模・整合: S / neutral   出典: R1-FLIP-03 PF-31

##### P3-04.14 identity 蒸留の入力が raw（閉じた pattern を含む）で憲法が live、の非対称を記録する
- 何を: (a) ADR-0057（または ADR-0091）に dated note「identity は raw（`valid_until` ありの閉じた行 675 件を含む）、憲法は live。理由 = <オーナー確認>」を 1 段落、DATACARD の lineage 節（P3-05.8）に「identity の `source_ids` は閉じた行を含みうる」の 1 行; (b) `epistemic_counts` と並べて `closed_input_count`（入力中の `valid_until` あり件数）を `IdentityResult` → `.meta.json` → audit に記録する（記録のみ、挙動不変）; (c) live に揃えるかは D-P3-04-3（変えるなら P3-02.1 に境界行。入力集合の変更は P3-07.1 チャネル (5) 取得パラメータ = value-steering-risk として審査）。
- 根拠: `src/contemplative_agent/core/distill.py:289` `find_by_view("self_reflection", knowledge.get_raw_patterns())` vs `core/constitution.py:108` `find_by_view("constitutional", knowledge.get_live_patterns())`; `core/knowledge_store.py:244-250`（raw = 全行のコピー）、`:279-281`（live = `is_live` = `valid_until is None`、ADR-0051 D1）; 公開 `knowledge.json` 10,985 行のうち `valid_until` あり 675 行; ADR-0050:59-64（両コマンドとも `find_by_view` と書くが liveness には触れない）; ADR-0057 / 0091 / 0026 に raw を選ぶ理由の記述なし（grep 0）; `core/distill.py:227-239`（`IdentityResult.epistemic_counts`）。
- 完了条件: note 1 段落と DATACARD の 1 行; `closed_input_count` が次回 staging の `.meta.json` と audit 行にある; D-P3-04-3 の有無が `gate_item` にある。
- 規模・整合: S / neutral（記録。(c) で入力を変える場合は value-steering-risk として審査）   出典: R2-VL-05   依存: P3-05.8、.8、P1-12.1（sidecar / audit 行形）


**依存**
- P0-07（憲法 due 2026-10-31: referent inventory PF-12 と .4 の列共有、shadow 系列）
- P1-12（P1-12.1 の audit 行形 → .14、P1-12.4 の `correction` 行 → .2 の twin 記録、P1-12.2 = .3 の却下行の本文の読み元。いずれも 2027-01 着手なので、.2 / .3 は現行の形で書き、入ったら更新）
- P3-03.10（.9 の推定量の正本、10-31 の週）/ P2-01.9（.8 の率の区間規則）/ P3-05.8（.14 の lineage 行）
- 現行の形で書き、入ったら更新するもの: P3-01（研究問い ADR: Q3 の操作的定義 → .8 / .9、12-12）/ P3-05.3（DATACARD の骨組み、11-21 の後 — .1 の保持方針の段落は現行の DATACARD に書き、骨組みが入ったら Distribution / Maintenance へ移す）
- P0-03.8（`.last_constitution_amend` の退役を吸収）
- ADR-0101（消費計画）、ADR-0071（signal-first）、ADR-0030（history 撤回。partial supersede の要否は D-P3-04-1）、ADR-0020（`## Amendment` 1 本、P0-03.5 の段落を同乗）
- P0-03.5（ADR-0020 の同じ `## Amendment` に段落）、P3-07.1（.11 を記録する (10) 行）、P1-07.11（.8 / .9 の再走の引き金 = model-swap.md の行）、P1-03.11（D-P1-03-1 の暫定基準 → D-P3-04-1 の partial supersede の問い）
- 外部: GitHub 上の data repo 履歴（shallow clone では復元不可。オーナー手元で unshallow）
- → 参照元: P0-07（before/after 参照点 = 08-09 snapshot の存続が .1 の期限に直結）、P3-05.2（HF mirror の版メタデータ）、P3-03.3（4 版 × IPD の表を `constitution/history/` に置く）、P3-06.4（束と gate card が .2 / .3 / .12 を使う）、P3-01.2 (v)（.3 の CHANGELOG 行を写す）、P3-01.3（Q2 の元パターン年齢の軸）、P2-05.7（値層の変化系列が .1 の回転窓を前提にし、回転で消えた境界を .2 の history で補う）、P3-07（.3 の rules 節と D-P3-04-3 を D-P3-07-1 の材料にする）、P2-05.2（`value-layer-*.json.rules` の `last_adopted_ts` を投影に載せる）、P1-08.21（.12 の写像表を同一ソースとして読む）、P1-07.13（snapshot manifest への来歴 record の写し）


#### P3-05 公開データセットの研究再利用性（DATACARD・schema・DOI 版・HF・再現ガイド）
- 狙い: ADR-0080 の研究層は「最終成果物 = データセット + 論文」で、到達点は第三者による再現と派生。現状は DATACARD が datasheet 項目を欠き、引用メタデータ・graph・HF card が実データ（embedding 0 行・importance 0 行・views 2 本）と食い違い、DOI 固定版は v1.0.0（2026-06-17）だけで、skill → pattern → episode の来歴が公開側で切れている。第三者が公開データだけで README の図表・統計を再生成できる状態にする。
- 期限・順序: 着手 11-21 の土曜ゲート（§4.0）。期限 2027-Q2。先行: 整合パス（.1）と HF id の統一（.2）は 10-17 の週（§4.0 の先行列。.2 のうち `sync-research-data.sh` の鮮度ログ 1 行だけは下の順序で P0-03.3 → P0-03.16 → P2-05.1 の後）。data repo の手保守ファイルの編集と `git rm` は sync を行う Mac の checkout でだけ行い、その間は sync job を unload する（P0-03.16 (c) の規約。.1 / .2 が 10-17 の週に data repo を触るので、10-16 までに DATACARD に置く）。DATACARD は datasheet の骨組み（.3、S）を先に入れ、節を埋める項目（.4〜.6 / .12 / .14 / .17、P3-02.1 / .2 / .7、P0-03.9 / .10）はその後。いずれも P0-03（.bak 72MB・絶対パスの除去）の後。本体側メタデータ（.13）は P0-06（v2.13.0 の release PR）と同時だが、data 版（.12）は v2.13.0（tag は 11-14 のゲートの後の平日 11-16〜20）と同時には切らず、11-21 の D-P0-03-1 / D-P0-03-3 / D-P3-05-2 の後、12-05 のゲートの後（D-P3-05-4 の後）。takedown の受付文面・到達範囲表（NOTICE 側）・私的台帳（.14）と撤回の実行経路 .19 (a)(b)(c) は 11-21 の週、.19 (d) の audit source `takedown` は P1-12.5 の後。.14 の表は P4-02.1 の SWH save request より前。決定は 6 件: D-P3-05-1（版付け規則と DOI 版の中身、11-14、熟慮）、D-P3-05-5（graph の HF ライセンス、11-14）、D-P3-05-2（撤回ポリシー、11-21、熟慮）、D-P3-05-4（`patches/` の扱い、12-05）、D-P3-05-3（2027-02-27）、D-P3-05-6（2027-03-06）。`sync-research-data.sh` を触る .2（鮮度ログ）/ .9 は P0-03.3 → P0-03.16 → P2-05.1 の後、.19 (c) は P0-03.3 → P0-03.16 の後（P2-05.1 は後から読む側）。
- 束の完了条件:
  - `docs/REPRODUCING.md` に列挙された全コマンドが、公開 data repo の clone と HF `shimo4228/contemplative-agent-data` だけを入力に別マシンで exit 0 し、README の数値（pattern 数・skills 数・版 DOI）と一致する記録が `docs/evidence/` にある。
  - `DATACARD.md` に Gebru らの datasheet 7 見出しがあり、`knowledge.json` schema 表が集計スクリプトの出力と diff 0。
  - data repo の governance 7 ファイル + HF card 2 枚に `768-dim|importance scores|seven|Qwen|rules-distill|n<1K` が無い（退役注記を除く）。`hub_repo_details` の `dataset_structure` が両 HF dataset で splits を返す。
  - v1.0.0 以外の版 DOI が 1 つ以上あり、`CITATION.cff` の version/date がそれに一致。本体 `.zenodo.json` に `isSupplementedBy` 10.5281/zenodo.20732894。
  - 公開 `skills/*.md` 53 件すべてから `knowledge.json` の行に到達する同梱スクリプトが exit 0。写像表 `pipeline/skill-names.json`（.9）の行数 = `skills/*.md` + 退役件数（P2-05.8 のテスト）。
  - NOTICE の takedown 節（.14）が受付の文面・到達範囲表・私的台帳の件数行を持ち、実行経路（.19）を名指し、4 面（NOTICE / DATACARD / HF card / `.zenodo.json`）の受付文面の diff が 0。

##### P3-05.1 データ repo メタデータの整合パスと週次 scan
- 何を: `CITATION.cff` / `.zenodo.json` / `llms.txt` / `README(.ja).md` / `graph.jsonld` / HF card を実データに合わせて 1 回で直す（768-dim embedding・importance・seven views・Qwen3.5・`rules-distill`・「各改正の provenance trail」・`size_categories: n<1K`）。graph.jsonld の `RetrievalView` 5 ノードと `command-rules-distill` ノードは削除か `retired:` 属性に、`views/constitutional.md` の `seed_from` を属性化。以後 `scripts/docs_consistency_scan.py` 相当を data repo の governance ファイルに週次で当てる（禁則語に `no restriction|一切の制限|unrestricted` を含める — ライセンス散文の整合は P0-03.14、R2-ETH-05）。
- 根拠: data `CITATION.cff:20-23`・`.zenodo.json:10`（768-dim / importance / seven views）に対し `knowledge.json` は importance 0 行・embedding 0 行、`views/` は 2 本（ADR-0073、2026-07-03）。`llms.txt:9,13,14,52,68`、data `README.md:36,50`、`graph.jsonld:78,93,134-195,219`。HF card frontmatter `size_categories: n<1K`（hub 自動 tag は `10K<n<100K`、2026-10-10 確認）。`scripts/docs_consistency_scan.py:72` の対象は本体の `CLAUDE.md` / `README*` のみ。
- 完了条件: 上記 8 ファイルで `grep -c "768-dim\|importance scores\|seven\|Qwen\|rules-distill"` = 0（DATACARD の退役注記を除く）。graph の `RetrievalView` ノード数 = `ls views/*.md | wc -l`。data repo 向け scan が週次 materials に 0 件で出る（禁則語 3 語は P0-03.14 の後に 0）。
- 規模・整合: S / repair   出典: RF-30 DE-15 DE-16 RD-36 DE-12 R2-ETH-05

##### P3-05.2 HF mirror の canonical id・鮮度・版メタデータ
- 何を: 文書・`.zenodo.json`・graph の HF 参照を hub 正本の小文字 `shimo4228/…` に統一する。Viewer / Parquet は小文字 id で動く（`default/train` 11.0K 行・7 列・Parquet 2.3 MB、graph 側 173 行）が、文書が使う `Shimo4228/…` では 404 "renamed" になる（2026-10-10 確認。推定: 大小文字の不一致）。release runbook に「graph.jsonld + graph.jsonl + card（version / BibTeX / DOI / ノード数は生成）」を 1 段で入れ、`graph.jsonld` ルートに `schema:version`（= pyproject version）と `schema:dateModified` を置く。
- 根拠: `hub_repo_details`: graph mirror Updated 2026-09-12、card「79 nodes」「v2.3.0 / 2026-05-05 / 10.5281/zenodo.19212119」vs 本体 `graph.jsonld` 178 ノード・最終 commit `4b85f22` 2026-10-09。本体 `graph.jsonld` のトップレベルは `@context` / `@graph` のみ。`CLAUDE.md:171` の同期手順は `~/.claude/skills/jsonld-knowledge-graph/`（repo 外 → P2-03）。
- 完了条件: `grep -rc "Shimo4228/" DATACARD.md README.md llms.txt .zenodo.json graph.jsonld CLAUDE.md` = 0。HF card の version == `pyproject.toml` version。HF の graph から `schema:version` が読める。AKC / AAP の `CLAUDE.md` の HF 行（AKC `CLAUDE.md:56`、AAP `CLAUDE.md:151`、どちらも `Shimo4228/contemplative-agent`）も小文字 id（兄弟 repo の PR）。graph mirror の lastModified と本体 graph.jsonld 最終 commit の差、および patterns dataset `shimo4228/contemplative-agent-data` の lastModified と data repo 最終 sync commit の差が各 ≤ 7 日 — 鮮度の読みは `sync-research-data.sh` 側（既に HF に出る唯一の無人経路、`:150` `hf upload`）が `hf` の戻り（成功 / 失敗と時刻）を 1 行ログに書き、weekly の materials 段はそのログを読んで各 1 行にする（新しい egress は足さない: `weekly-analysis.sh` はネットワークに出ない。P1-10.14 の verb 目録は `hf upload` 1 verb のまま）。`hf upload` 失敗は WARNING のみ（`:154`）なので、公開ミラーの鮮度を読む面はこの行だけ。
- 規模・整合: S / repair   出典: RF-35 DE-12 RD-20 RD-22 R2-GATE Fix-13 R3-AKC F4   順序: `sync-research-data.sh` は P0-03.3 → P0-03.16 → P2-05.1 の後

##### P3-05.3 DATACARD に Gebru らの datasheet 7 節の骨組みを先に入れる
- 何を: Motivation / Composition / Collection / Preprocessing / Uses / Distribution / Maintenance の 7 見出しを先に置き、現 DATACARD の節（Structure / schema / Collection method / Known limitations / Excluded / Third-party / Intended / Not intended / Provenance）を対応する新節に移し替え、「volatile な数は計算コマンドで示す」方針を各節冒頭に 1 行書く。骨組み時点で書ける事実だけ入れる: Composition に `meditation/results.json` の更新停止の注記（2 run、2026-03-21、ADR-0049）と skill store は選択注入（1 回平均 6 件、全件注入経路なし、全文 36k token > `num_ctx` 32,768）、Maintenance にサイズ読み値（checkout / pack / 月次増分を決定論 1 行。消費は最終版作成時 → P4-02）。節の中身は後続項目が埋める: Composition ← .4 / .5 / .6 / .17 / P3-02.1 / P3-02.7、Collection ← .14 / P0-03.10、Preprocessing ← .6 / P0-03.9、Distribution ← .12、Maintenance ← .14（受付件数）/ .5（再計算列）/ P3-02.2。
- 根拠: `DATACARD.md:23-132` の現節は Structure / schema / Collection method / Known limitations / Excluded / Third-party / Intended / Not intended / Provenance。`meditation/results.json` の `"ts"` 2 件・最終 2026-03-21。`pipeline/never-selected/never-selected-2026-10-02.json` `corpus.history_full_skill_tokens` 36,429 / `num_ctx` 32,768、RFC-0048:71「1 件約 690 token、1 回平均 6 件」。`du -sh`: reports 60M / snapshots 28M / .git 48M、comment-reports 217 日分（欠落なし）。
- 完了条件: 7 見出しすべてが存在し（`grep -c "^## " DATACARD.md` ≥ 7、見出し語が datasheet 語彙に一致）、旧節の本文が対応する新節に移っている; 節内の数値は「コマンド + 実行日」の形。
- 規模・整合: S / neutral   出典: RF-29 DE-23 VL-39 DE-06

##### P3-05.4 `knowledge.json` schema 表を集計から生成し、列の由来・語彙・id 導出式を書く
- 何を: `scripts/export-patterns-jsonl.py --describe`（新設）で列ごとの出現件数・初出日・導入/退役 ADR を出し、DATACARD と HF card の表をその出力に置き換える。明記するもの: `gated` 293 行（2026-03-26〜04-15 のみ。キー欠損 = 未判定、ADR-0011 → 退役）、`provenance.source_type` の enum（ADR-0021:33）self_reflection 10,419 / mixed 266 / unknown 300、`pipeline_version` None 300 / `distill@0.26` 544（04-16〜）/ `distill@0.60` 10,141（06-23〜、ADR-0060）= 抽出器の世代境界、`restored_from_evolution_at` 231 行（全件 2026-05-04T14:15Z）、`valid_until` 675 行（soft-invalidate、ADR-0021）、完全重複 4 件、`importance` 0 行（ADR-0056）、`pattern_id = sha256(f"{distilled}|{pattern}")[:12]`。未知欄を黙って落とす `_entry_from_dict` に件数 WARNING のテストを足す。
- 根拠: `python3 -I` 集計（2026-10-10、10,985 行）は上記のとおり。`DATACARD.md:45-49` と HF card は `importance`「Legacy rows only」/ `gated`「null = predates gating」/ `provenance`「(`source_type`)」のみ。`src/contemplative_agent/core/knowledge_store.py:63-74`（pattern_id、"No persisted id field"）、`:546-597`（ホワイトリスト復元）、`:451-489`。`scripts/export-patterns-jsonl.py:27,38`。
- 完了条件: 表の全列に出現件数・初出日・ADR があり、`--describe` の出力と DATACARD の表の diff が 0。DATACARD の式だけで `knowledge.json` から sidecar と同じ id を計算できる（テスト 1 本）。未知欄 WARNING のテストが通る。
- 規模・整合: S / repair   出典: DE-17 RF-40 DE-26 VL-09 CP-13 DE-18

##### P3-05.5 公開 tree の未説明構成要素を 1 表にする（pipeline / PIPELINE-STATUS / ledger / patches / _gc_trash）
- 何を: DATACARD に「Pipeline instruments」節（path → 生成 script → 所有 ADR → 消費者 → 公開入力で再計算 yes / no）と、公開 tree の全トップレベル・`reports/analysis` の命名規則（`weekly-DATE-{findings,packet,insight-review,archive-candidates,improvement}`）の表を置く。`reports/analysis/patches/`（本体コードの diff 14 件、MIT）は sync 除外か NOTICE に位置づけを書く（D-P3-05-4、12-05）。`_gc_trash/2026-07-10-clean-rewrite-originals/`（書き換え前 skill 10 件）は D-P0-03-2 と P0-03.7 の処理どおりに表に 1 行。「公開入力で再計算」列は、全 pipeline JSON に生成元ヘッダを常設せず、1 回の再実行（dead-code / docs-consistency を本体 tag から再実行して `count` が一致するか）で埋める。
- 根拠: `grep -c "pipeline/\|PIPELINE-STATUS\|observation-ledger\|findings\|patches" DATACARD.md README.md llms.txt` = 0/0/0。実体: `pipeline/{comment-outcomes 4, confusion-pairs 4, dead-code 9, docs-consistency 8, ledger-watch 1, never-selected 6, value-layer 8}` = 40 JSON（2026-08-07〜10-02）、`reports/PIPELINE-STATUS.md`、`reports/analysis/observation-ledger.jsonl`、`patches/weekly-2026-07-31..08-21/{code,prompt}/F1.x.patch` 14 件。`_gc_trash/` 10 件（`ls _gc_trash/2026-07-10-clean-rewrite-originals | wc -l` = 10、P0-03.7 と一致）は統合時に発見（どの文書にも無い）。7 系列 40 JSON のトップレベル鍵に生成 script 名・コード版・commit・入力・schema 版は無く（`python3 -I` 集計）、生成元は `scripts/weekly-pipeline.sh:647-947`; 公開入力だけで再計算できるのは dead-code と docs-consistency の 2 系列、残り 5 系列は `logs/`（sync 除外 `sync-research-data.sh:81`）が入力。
- 完了条件: `ls -d */` と `ls reports/analysis | sed -E 's/[0-9]{4}-[0-9]{2}-[0-9]{2}/DATE/' | sort -u` の全行が DATACARD の表に対応する（差分 0 の決定論チェック）; 再計算列が全系列で埋まり、dead-code / docs-consistency を本体 tag から再実行して `count` が一致した記録 1 件が REPRODUCING.md（.10）にある。
- 規模・整合: S / repair   出典: DE-20 R1-REP-05

##### P3-05.6 snapshot の「bit-for-bit replay」の主語と前提を書き直す
- 何を: DATACARD に (a) 回転窓 `MAX_SNAPSHOTS = 100`（現 tree は 2026-07-17 以降の 100 件: distill 84 / insight 11 / distill-identity 2 / amend-constitution 1 / rules-distill 1 / skill-stocktake 1）と `git log --diff-filter=D -- snapshots/` での取り出し方、(b) replay に要る入力の表（公開: views / constitution / skills / rules / identity / centroids / manifest。非公開: episode log・embeddings sidecar・prompts。「Ollama 版 / モデル digest」行は 09-12 以降のみ公開、それ以前は P3-02.7 の復元表）、(c) kinds の全列挙を書き、`llms.txt:94`「manifest が全ファイルとハッシュを列挙」を削る。最終版で窓を解除するかは P4-02。
- 根拠: `src/contemplative_agent/core/snapshot.py:34`（`MAX_SNAPSHOTS = 100`）、`:206`（書き込み後に prune）。`scripts/sync-research-data.sh` は `rsync --delete`。manifest の鍵集合は 3 世代（14 鍵 18 件 / 15 鍵 44 件 / 19 鍵 38 件、R1-REP-04）: `snapshots/skill-stocktake_20260815T041708923626Z/manifest.json`（15 鍵世代）のキーは command / ts / run_id / generation_model / think / embedding_model / embedding_dim / thresholds / views / *_dir / identity_path（ファイル一覧・ハッシュ無し、`prompts_dir: null`）、19 鍵世代（`distill-identity_20260912…` 以降）は `ollama_version` / 2 digest / `serving_environment_reason` を持つ（`core/snapshot.py:116-122`）。`DATACARD.md:19,129`・`CITATION.cff:24-25`「bit-for-bit replayable」。`llms.txt:17,93` は kinds 4 種のみ。
- 完了条件: DATACARD の replay 節に「公開データのみで復元できる / 非公開が要る」の 2 列表。kinds 列挙 = `ls snapshots | sed 's/_.*//' | sort -u`。`grep -c "every file and its hash" llms.txt` = 0。
- 規模・整合: S / repair   出典: DE-19

##### P3-05.8 skill → pattern の来歴を公開側に出す（frontmatter の source_ids / adopted / generated_by）
- 何を: 採用時に `source_ids`（pattern_id 列）・`adopted_at`・`audit_content_hash`・`generated_by: <model>`・`origin: auto-extracted|rewritten-2026-07-10`（語彙は P3-04.11 と同一）を skill frontmatter に書き込み（`cli/adopt.py` の書き出し経路）、既存 53 件は `logs/audit.jsonl` と snapshot manifest から一回限りバックフィルする（`direct` source の audit 行つき）。`audit_content_hash` は採用時の全文（canonicalize 後、frontmatter 込み、`cli/adopt.py:302-310`）の sha256[:16] なので、backfill 後に公開ファイルから再計算した値は一致しない — DATACARD に「再計算には backfill 前のバイト列（snapshot / git 履歴）が要る」と明記し、新規行からは body-only hash を併記する。到達スクリプトを data repo に同梱し、DATACARD に鎖の到達範囲（episode は非公開で止まる）を書く。
- 根拠: 公開 `skills/*.md` の frontmatter キーは name / description / origin のみ（53 件すべて `origin: auto-extracted`、2 件に退役済み `last_reflected_at / success_count / failure_count`）。lineage は `src/contemplative_agent/cli/approval.py:163-196` `_log_decision` の audit 行（`source_ids`, `content_hash`）にしか無く、`scripts/sync-research-data.sh:81` が `logs/` を除外。本体 `README.md:56`「Rejected proposals stay in a local decision log and are not published」。`source_episode_ids` は episode のタイムスタンプ（例 `2026-04-16T03:00:09.520151+00:00`）で、comment-report 見出し `[2026-10-08 03:05:35] COMMENT · with … · post bd4a099a…` との突き合わせ表が無い。
- 完了条件: 公開 `skills/*.md` 53 件すべてから `knowledge.json` の行に機械的に到達するスクリプトが exit 0。`generated_by` 非空 53/53。DATACARD に到達範囲の 1 段落。(a) DATACARD に `audit_content_hash` の定義と「再計算値は一致しない」の注記、新規行に body-only hash; (b) 注入文不変の試験: `src/contemplative_agent/core/llm/prompting.py:200-204` の frontmatter 剥がし経路で backfill 前後の system prompt が byte 同一（テスト 1 本）; (c) `origin` の語彙が P3-04.11 と一致。
- 規模・整合: M / neutral（来歴の記録）   出典: VL-01 VL-42 R2-VL Fix-03

##### P3-05.9 skill の name ↔ ファイル名の写像表と slug の語境界
- 何を: `name:` の書き換えもファイル rename も行わない（`name:` は本番の選択 LLM が読む enum で、20 件を書き換えると判定者入力と `skill-selection-*.jsonl` の系列名が途中で変わる）。代わりに写像表 `pipeline/skill-names.json`（stem ↔ `name:`、退役分も行に残す）を `sync-research-data.sh` の export 段で生成し（P2-05.8 の `skills/INDEX.md` と同じ生成段）、`pipeline/never-selected/*.json` の `dormant` 名を stem に引けるようにする。`core/text_utils.py` の 50 文字切り詰めは語境界（最後の `-`）で行う（コード変更は P1-06 の窓で）が、新規採用にしか効かないと注記し、既存 3 件の語中切れ名は stem に揃えない（LLM 向け名が悪化する向き）。
- 根拠: data repo `skills/` 集計（2026-10-10）: 不一致 20/53（例 `subjective-attention-calibration-20260725.md` → `internal-process-audit`、`dynamic-semantic-decoupling-…` → `dynamic-sematic-…` の typo）。`src/contemplative_agent/core/artifact_extraction.py:42,101`（`canonicalize_frontmatter_name`。`cli/adopt.py:302` から呼ばれ、新規採用にしか効かない）。`core/text_utils.py:24,57`（`MAX_SLUG_LENGTH = 50`、`slug[:MAX_SLUG_LENGTH]`）。語中で切れた名 `constraint-shift-analysis-pivot-point-identificati` 等 3 件。`src/contemplative_agent/core/skill_selection.py:182`（catalog 名は frontmatter `name`、`:215` LLM に見せる一覧、`:341-342` 判定質問、`:762,834` `catalog_names` / `selected`）。data repo に `tests/` も `scripts/` も無く、本体 `tests/` から live data repo を読むテストは CI（tmp HOME）で成立しない。
- 完了条件: 「写像表 / INDEX の行数 = `skills/*.md` + 退役件数」のテスト（合成 fixture、`sync-research-data.sh` の export 段を対象。テスト本体は P2-05.8 側に置き、ここではそれを引く）が緑; live 木の照合は export 段の 1 行ログ（`MOLTBOOK_DATA_REPO` 未設定なら skip、P2-03.5）; `pipeline/never-selected/*.json` の `dormant` 名が写像表経由で `ls skills/` に引ける。既存テストは不変（語境界切り詰めで `tests/test_text_utils.py::test_caps_at_max_slug_length` と `tests/test_insight.py::TestSlugify::test_max_length` は ≤ 50 の assert のまま通る）。
- 規模・整合: S / instrument（描画のみ）   出典: VL-10 VL-11 R2-VL Fix-02 R2-TST Fix-13   順序: P2-05.8 と同じ export 段（`sync-research-data.sh` は P0-03.3 → P0-03.16 → P2-05.1 の後）

##### P3-05.10 再現ガイド `docs/REPRODUCING.md` と再現性の 3 段表
- 何を: 英語 1 本で (1) データ取得（`datasets.load_dataset("shimo4228/contemplative-agent-data")`、data repo clone、snapshot の読み方）、(2) 主要読み値の再計算コマンド、(3) README の 3 つの問いごとの「主張 ↔ evidence dir ↔ 再現段」対応表、(4) 引用（.13 の 4 DOI 表）、(5) 「コード tag ↔ 公開 `knowledge.json` の形」の対応 1 節（07-12 export で embedding 除去、09-12 ADR-0108 sidecar。どの tag が `restore-embed-knowledge.py` / `migrate-knowledge-sidecar.py` のどちらを使うか — `DATACARD.md:83-85` は runtime 復元を本体 script に委ねるだけ）を書く。再現性を「公開データのみ / 私的ログ要 / cloud（`claude` judge）要」の 3 段で表にし、`docs/evidence/` の各 script を段に分類する。`evals/README.md` も足す。
- 根拠: 本体 `README.md:30`「If you research how agents form and revise values … this repository is for you」の後に手順が無く、`grep -n DATACARD README.md` 0 件。`evals/` に README 無し。`docs/evidence/README.md` の索引は 15 行 / 37 dir。`docs/evidence/*/*.py` + `scripts/*.py` 47 本のうち `grep -lE 'logs/|MOLTBOOK_HOME|audit\.jsonl'` に掛かるのは 29 本（2026-10-10 再計算、。元項目の「34 本」は条件が残っていないので 29/47 を正とする）。`evals/judging.py:237` `run_claude_judge`（cloud 依存）。raw episode は非公開（`DATACARD.md:104`）。
- 完了条件: 第三者が REPRODUCING.md だけで README の数値を 1 つ以上再計算できる（別マシンで exit 0 の記録を `docs/evidence/` に残す）。3 段表に `docs/evidence/**/*.py` の全 script が載る（索引行数 = dir 数）。
- 規模・整合: M / neutral（再現ガイドの文書）   出典: DC-36 RF-37

##### P3-05.11 公開データのみを入力にする図表スクリプトと Loading 節
- 何を: `analysis/`（data repo か本体）に「入力は公開 data repo + HF のみ」の図表スクリプトを置き、1 コマンドで README / 論文の全図を生成する。境界線は `pipeline/regimes.json`（P3-02.1）を読んで引く（座標を手書きしない）。DATACARD に "Loading" 節（patterns を pandas / polars で 3 行、comment-report の 20 行パーサで `**Context:**` を落とし `**Internal note:**` / `**Output:**` だけ残す例、snapshot manifest の読み方）を置く。
- 根拠: 公開データから読める計器は `pipeline/*.json`（7 系列 40 JSON）と `knowledge.json` のみで、evidence script の大半は私的ログ前提（.10）。comment-report の文法は `src/contemplative_agent/core/report.py:180-224` `_entry_lines`（`### N. [ts] KIND · with <name> · post <id>… · relevance …` → `**Context:**` / `**Internal note:**` / `**Output:**`）にしか無く、`DATACARD.md:61-77` の唯一のコードは埋め込み再構成。
- 完了条件: `make figures`（相当）が公開 clone だけで exit 0 し、生成物が README の図表と一致。Loading 節の例をコピーして実行すると動く（テストで固定）。
- 規模・整合: M / neutral（図表 script と Loading 節の文書）   出典: RF-28 DE-25   依存: D-P0-03-3（表示名の扱い — Loading 節の例と snapshot 由来の行の名前を仮名化するかは決定後、R2-ETH Fix-12）

##### P3-05.12 データセットの版付け規則と次の版 DOI
- 何を: 版付け規則（D-P3-05-1）を DATACARD の Distribution に書き、次の版を切って `CITATION.cff` の version / date-released を更新する。DATACARD / llms.txt の「concept DOI」と `CITATION.cff` の `doi:` の呼び分け（concept 20732894 / version DOI）を直し、SWH 識別子を data の `CITATION.cff` に足す。次の版は v2.13.0（tag は 11-14 のゲートの後の平日 11-16〜20）と同時には切らず、11-21 の D-P0-03-1 / D-P0-03-3 / D-P3-05-2 と 12-05 の D-P3-05-4 の後、12-05 のゲートの後に切る。deposit に何を入れるかは D-P3-05-1 (b)（推奨 C: deposit 用コピーでは Context ブロックを `[see GitHub <commit>]` に置換）に従い、作成手順は P0-06 の release runbook。(b) が B / C なら最初の新版より前に data repo の Zenodo–GitHub 連携を off にし、data repo では GitHub Release を作らない（P0-06.6 段 (8)。連携が on のまま Release を作ると tree 全体が自動で不変版になる）。
- 根拠: data `CITATION.cff:5-8` version 1.0.0 / 2026-06-17 / doi 20732894。`git ls-remote --tags origin` = `v1.0.0` のみ（2026-10-10）。`DATACARD.md:8`・`llms.txt:7` は同番号を concept DOI と呼ぶ。v1.0.0 は gemma4 切替（ADR-0069、06-28）・sidecar（ADR-0108、09-12）・RFC-0046 enforce 以前。`.zenodo.json` に `version` 無し。`docs/CYCLES.md:92` cycle 9 の `release-doi` skill は repo 外（→ P2-03）。
- 完了条件: v1.0.0 以外の tag と版 DOI が 1 つ以上あり（日付は 12-05 のゲートの後、deposit は D-P3-05-1 (b) の形。B / C なら連携 off の確認日が releases.md の備考にある）、`CITATION.cff` の version / date がそれに一致（`cffconvert --validate` exit 0）。DATACARD に版一覧へのリンク。
- 規模・整合: S / neutral   出典: RF-34 RD-18 DE-30

##### P3-05.13 引用の双方向化と本体側の機械可読メタデータ
- 何を: 本体 `.zenodo.json` に `{"identifier":"10.5281/zenodo.20732894","relation":"isSupplementedBy","resource_type":"dataset"}` と HF data dataset、`CITATION.cff` references に dataset 1 件、README「For tools and AI assistants」に dataset DOI を足す。README Citation 節に 4 行表（実装 = CA / 記録 = data / 判断 = AAP / 方法 = AKC）を EN/JA で置く。`codemeta.json` に `programmingLanguage` / `runtimePlatform` / `operatingSystem` / `softwareRequirements` / `issueTracker` / `readme` / `releaseNotes`、`pyproject [project.urls]` に Changelog / DOI を足し、`.zenodo.json` の `isDocumentedBy` を hub の `main` 可変 URL から commit 固定 URL か DOI 付き dataset に変える。v2.13.0 の release PR と同時（→ P0-06）。
- 根拠: `grep -rn 20732894 README.md CLAUDE.md docs rfcs CITATION.cff .zenodo.json codemeta.json` = 0 件（data 側は `isSupplementTo` / `isDerivedFrom` で本体を指す片方向）。`README.md:171`「Cite AAP for the accountability thesis and this repository for the implementation」の 1 文のみ。`codemeta.json` はトップレベル 12 キー（`@context` / `@type` を除けば 10）、`pyproject.toml:24-27` urls 3 件。`.zenodo.json` `isDocumentedBy` = `https://raw.githubusercontent.com/shimo4228/shimo4228/main/graph.jsonld`。
- 完了条件: 次 deposit の `.zenodo.json` に dataset DOI があり、`grep -c '/main/' .zenodo.json` = 0。README EN/JA に 4 行表。codemeta の追加 7 キーが RD-08 の検査対象。
- 規模・整合: S / neutral   出典: DE-29 RD-16 GO-38 RD-35 RD-40

##### P3-05.14 第三者投稿の倫理声明・takedown の受付と到達範囲表・carve-out の範囲
- 何を: NOTICE と DATACARD に "Third-party content & takedown" 節を足す（takedown の受付文面・連絡先・対応期限の正本はこの節。P1-10.3 の `SECURITY.md` は後からここへリンクするだけ、実行経路は .19）: (a) 再掲の根拠を 3 行で: (i) Moltbook 規約の条項（オーナーが確認し、P1-07.19 の再読台帳の行（日付・digest）を引く。条項番号 + 短い引用のみで本文は写さない） (ii) 引用・情報解析の法定例外（準拠法を明記。法的助言ではなく依拠先の記録） (iii) 個人データの分類（表示名 = 公開ハンドル、URL、メール形 — P0-03.6 のメール形の保持・削除方針はこれを参照）と保持方針（決定は D-P3-05-2 — R2-ETH-08）, (b) 削除・訂正依頼の受付 — NOTICE / DATACARD / HF card / `.zenodo.json` description に同一文面「Takedown / correction requests: <メール alias> または GitHub Security advisory（どちらでも可）、受理通知 7 日以内・判断 30 日以内」を置き、受付台帳は私的 `MOLTBOOK_HOME/takedown-requests.jsonl`（受理日 / 面 / 対象 id / 判断 / 実施日 / 根拠）、公開側は DATACARD Maintenance に件数のみ（「requests received N / actioned M as of <date>」）— と依頼の種別（投稿者本人 / 原投稿を自分で削除した著者からの申し出 / 名指しされた運用者の訂正依頼）。名前で来た依頼は来た時に `grep -rl` 1 本で post id に引く（表示名の逆引き script は第 5 章の P0-03 の延期行）, (c) 撤回の到達範囲表 — 面 = git 履歴 / fork / HF 履歴 / Zenodo 版 / SWH × 操作（削除 / 置換 / 撤回申請 / 不可）× 残る痕跡 × 確認日 の 5 行を NOTICE に置く。各行の初期値は外部知識・未検証（Zenodo = ファイル不変・record 撤回と metadata 追記は申請可 / HF = 履歴 squash 可 / GitHub = 書き換え後も fork・SHA 直参照が残り支援窓口あり / SWH = takedown 窓口あり）で、オーナーが各サービスの現行規約で確認し日付を付す。本体の既存版 DOI（v2.6.0〜v2.12.0 の release zip）に `real_sample.jsonl` が入っているかをオーナーが `git ls-tree` で確かめた 1 行（D-P0-03-1 の材料）も置く。`docs/runbooks/incident-response.md` への写しは P4-03.3 が行う。「平台側の削除は追跡・伝播しない（観測時点の写し）」の 1 文を NOTICE / DATACARD に置く（平台側の削除状態は P1-07.5 の census 規則 PR で `content_status` の非 null 件数を 1 回数え、非 0 なら第 5 章の延期行から起こす）。元投稿が平台側で削除された場合の扱いは 3 択 — A 反映しない + NOTICE に「投稿時点の写し。元投稿の削除は反映しない」/ B 依頼ベースのみ（.19 の抑止リスト）/ C 月次に既存 endpoint で再照会し `[deleted on platform]` に置換（I/O 面が増えるので第 5 章で審査）— で推奨は A + B（R2-ETH-07）, (d) 帰属の実態は comment-report 見出しの相手エージェント表示名 + post id 先頭 8 文字で、`## Sources` は引用元投稿自身の節であって帰属手段ではない（NOTICE / DATACARD の文言訂正は P0-03.10）。8 文字 id は私的 episode log でしか解決できないので、表示名を「残す / 仮名化（private salt の HMAC 先頭 8 桁、export 境界のみ・記憶は不変）/ 落とす」のどれにするか（`safe_peer_name` は scrub であって匿名化ではない。対象は comment-report + weekly だけでなく `knowledge.json` / HF 行 / skills / snapshots。名前の決定は D-P0-03-3 の D）、新規報告の post id を全桁にするか、日次 `sources.json`（post_id → 表示名 → URL）を sidecar で出すかを決める（決定後に P0-03.10 が新規報告の描画を変える）。weekly 文書に出る相手名も同じ扱い。Internal note / Output は相手を名指す機械生成の評価を含みうる（143 / 416 ブロック）ので「訂正・削除依頼は同じ窓口」の 1 段落を置き、仮名化を採る場合は両ブロックの名前も同じ変換にかける（名指しブロック数の計測行は P0-03.9 の script — R2-ETH-09）, (e) carve-out を `reports/**` 内の第三者投稿由来テキスト全般に広げる（weekly 28 本中 20 本に Context 由来の 8 語一致 3,193 箇所 — 計測は P0-03.9。「該当なし」と書く分岐は落とす）。論文に載せる引用は本文でなく id のみ。
- 根拠: `NOTICE:35-50`・`DATACARD.md:109-114` は帰属と「再利用者の責任」止まりで、再配布者（オーナー）側の根拠・連絡先・不変性の注記が無い。`comment-report-2026-10-08.md` の `**Context:**` 68 ブロック。見出しは `src/contemplative_agent/core/report.py:196-205` で相手名を描画。`weekly-2026-10-02.md` Ledger 節が `pixelbotstripclub` / `zaguu` を名指す。`scripts/weekly-pipeline.sh:320-323`「reads nonce-framed untrusted post bodies, and its outputs are published by sync-research-data」。`weekly-2026-08-21-packet.md` 145,674 B（`**Context:**` ブロック 0。引用の形は未読）。`NOTICE:38-42`・`DATACARD.md:111-112`「adjacent `## Sources` block」に対し `report.py:206-208`（`post8 = post_id[:8]`、Sources の描画無し）; `## Sources` は 217 報告中 136 ファイル・719 回、すべて `**Context:**` の内側（R1-REP-07）; `adapters/moltbook/client.py:69-70,148-170`（`is_deleted` は api-audit に記録されるだけで読み手が無い）; `src/contemplative_agent/core/episode_render.py:24-40`（`safe_peer_name` は改行・制御文字・injection token の scrub であって匿名化ではない）; R2-ETH の計測（`python3 -I`、本文未出力）: `reports/analysis/*.md` 78 中 43 に Context 由来の 8 語一致（weekly 28 中 20、計 3,193 箇所）、Internal note 143 / Output 416 ブロックに「名前らしい」表示名、表示名の残存は `knowledge.json` 142 行・skills 1・snapshots 105 ファイル; 受付: data repo の governance 5 ファイル（`README.md` / `README.ja.md` / `llms.txt` / `DATACARD.md` / `NOTICE`）に `contact` / `takedown` / `remov` / `privacy` 0 件（grep）、HF card に連絡先節無し、`.zenodo.json` に `contact` / `notes` 無し、現状の窓口は P1-10.3 の GitHub private vulnerability reporting 1 本（相手は Moltbook 上のエージェント運用者で GitHub にいる保証は無い）; 到達範囲: 不変・準不変の面 5 つ — data repo の git 履歴（D-P0-03-1 A「消さない」）、fork、HF（`scripts/sync-research-data.sh:149-151` が毎 sync で `hf upload` → 過去版が revision として残る: 外部知識）、Zenodo 版 DOI v1.0.0（data `CITATION.cff:5-8`、`.zenodo.json:2,12` = GitHub release zip）、SWH（P0-06.11 / P4-02.1 が save request を予定）。Zenodo / HF / SWH / GitHub の API はこの環境から未接続。
- 完了条件: NOTICE / DATACARD に節があり、根拠 3 行・受付文面（4 面で diff 0）・5 面の表（各行に確認日とリンク、P4-02.1 の SWH save request より前）・「観測時点の写し」の 1 文・削除済み投稿の方針（A の 1 文）・名指し評価の 1 段落が grep できる; 台帳の行形テスト 1 本と DATACARD の件数行; `NOTICE:22` の `reports/analysis/` が owner-authored の列挙から carve-out 側に移っている（計測は P0-03.9）; (a)(i) が P1-07.19 の台帳行（日付・digest）を引く; (d) の決定（D-P0-03-3）が記録され P0-03.10 がそれを引く; 次回 Zenodo 版（12-05 のゲートの後、.12）に反映。
- 規模・整合: S / neutral   出典: RF-33 SA-17 DE-27 R2-PLAT Merge-01 Fix-04 R2-ETH Merge-02 Fix-01 Fix-02 R2-ETH-02 R2-ETH-07 R2-ETH-08 R2-ETH-09 R2-ETH-04 R2-ETH-06   順序: 11-21 の週（受付文面・表・台帳）。`incident-response.md` への写しは P4-03.3、`AuditSource` の `takedown` は .19 (d)   依存: P1-07.19（再読台帳の初回行は 11-14 の週、§4.0 の先行列）、D-P3-05-2、D-P0-03-3、D-P0-03-1、P0-03.9（逐語重なりの計測）、P1-07.5（`content_status` の 1 回の計数）、P0-06.11（SWHID の形）

##### P3-05.17 `provenance.pipeline_version` の更新規則と値 → コード版の対応表
- 何を: `pipeline_version` の更新規則を決めて実装する — 推奨は `distill@<pyproject version>+<distill prompt sha12>`（値がコードと prompt から計算される。リテラル禁止のテスト 1 本）— し、DATACARD に対応表（値 / 期間 / commit か tag / prompt digest / generation model / 導入 ADR。`memory_evolution@0.26` の退役行を含む）を置き、`--describe`（.4）がその表を出す。コード変更は v2.13.0 の release か P1-06 の窓で。
- 根拠: `src/contemplative_agent/core/distill.py:892` `"pipeline_version": "distill@0.60"`（リテラル）; 公開 `knowledge.json` 10,985 行で `distill@0.60` 10,141（06-23〜10-09）/ `distill@0.26` 544 / None 300、`memory_evolution@0.26` 0 行（`docs/evidence/adr-0021/implementation-audit-20260418.md:26,201` では 54 行。`restored_from_evolution_at` 231 行が痕跡）; 同じ `distill@0.60` の区間に ADR-0069（06-28）・ADR-0084（07-26）・ADR-0108（09-12）・score4 enforce（09-28）が入る（P3-02.1 の境界行）; `docs/adr/0021:35`「e.g. "distill@0.21"」以外に値の規約が無い（0.26 ↔ ADR-0026、0.60 ↔ ADR-0060 は推定）。
- 完了条件: 新規行の値が計算値と一致するテスト（リテラル禁止）; 対応表の全値が `knowledge.json` の出現値集合と一致; 過去 2 値は ADR 日付で backfill された行がある。既存テストは不変（HEAD の `tests/` に `pipeline_version` の literal を assert するテストは無く、`tests/test_knowledge_store.py:151` の `distill@0.21` は fixture 値）。
- 規模・整合: S / instrument   出典: R1-REP-03
- 消費計画: (a) P3-05.10 の再現者と P3-02.1 の境界表が読む（行単位の世代判定） (b) 1 回の対応表で「どの区間を同じ抽出器として比較してよいか」を P3-01.3 の Q2 読みに渡す (c) 撤去条件: 列は常設（データ列の規則）、対応表の更新は release runbook の 1 行に畳む

##### P3-05.19 撤回の実行経路 — 抑止リストを export・描画・sync に通す
- 何を: `config/takedown-suppressions.txt`（1 行 1 件: `post:<id>` / `name:<表示名>` / `pattern:<pattern_id>` / `file:<相対パス>`、本文は書かない）を置き、(a) `scripts/export-patterns-jsonl.py` が該当 pattern 行を落とす（または本文を `[withdrawn <date>]` に置換し id を保つ）、(b) `core/report.py` の描画が該当 post の Context を `[withdrawn]` にし名前を仮名化する、(c) `sync-research-data.sh` が `--exclude-from` 相当で該当ファイルを再同期しない（P0-03.3 の `config/sync-excludes.txt` と同じ helper）、(d) 適用を audit 行（source `takedown`、approver 付き）に残す — `AuditSource` に `takedown` を足すのは P1-12.5 の後で、それまでは .14 の私的台帳に記録する。既公開分は同じリストで 1 回の `git rm` / 置換 commit（sync を行う Mac の checkout でだけ行い、その間は sync job を unload — P0-03.16 (c)）。依頼が無ければリストは空で挙動不変。(a)(b)(c) は 11-21 の週（.14 の公開と同じ週）。
- 根拠: `scripts/sync-research-data.sh:69-77`（`rsync -a --delete`、`reports/` は除外されない）、`:106-109`（公開 `knowledge.json` を私的 store から毎回再生成）、`:149-154`（HF へ毎回 upload）; `scripts/export-patterns-jsonl.py:27,38`（落とす欄は `embedding` のみ、行の抑止無し）; ADR-0060:174（no-delete policy）+ 公開 `knowledge.json` の tombstone 675 行（soft-invalidate でも本文は公開のまま）; comment-report は `core/report.py` が私的 episode log から描画する。依頼を受理して公開 repo で行を消しても翌 05:30 の無人 sync で戻る（R2-ETH-03）。
- 完了条件: fixture の post id を入れると次回 sync 後も公開 tree に戻らないテスト（`tests/test_sync_research_data_shell.py` 型、harness は P1-08.3、Linux で走る）; export / report の単体テスト各 1; NOTICE の takedown 節（.14）がこの経路を名指す。
- 規模・整合: M / repair   出典: R2-ETH-03   順序: (a)(b)(c) は 11-21 の週、(d) は P1-12.5 の後。`sync-research-data.sh` は P0-03.2 → .3 → P0-03.16 の後（P2-05.1 は後から (A2) の同期条件としてこの経路を読む）。`core/report.py` の分岐は P1-06 の構造 PR（2027-01-16）より前に入るので、P1-06 側はこの分岐を保って移す   依存: P0-03.10（post id の解決）、P0-03.2 / .3（共有除外ファイル）、P0-03.16（sync を行う checkout での手作業）


**依存**
- P0-03（`.bak` 72MB・ロック・絶対パスの除去。DATACARD / NOTICE 再編の前提）、P0-03.9 / .14（weekly の逐語断片の計測、ライセンス散文 → .14 / .1）、P0-03.16（data repo の手作業は sync を行う checkout でだけ → .1 / .2 / .19）
- P0-06（v2.13.0: `.zenodo.json` / `CITATION.cff` / `codemeta.json` の release PR、RD-07 の版定数、release runbook の HF 段と deposit 作成手順。P0-06.4 は P3-05.7 の吸収先 = manifest 列・sync commit 要約、欄名 `framework_version` / `git_commit` / `prompt_digests` / `manifest_schema`）
- P2-05.8（.9 の写像表と同じ export 段・行数テスト）、P3-02.1 / .7（.11 の `regimes.json`、.6 / .17 の境界と Ollama 版）、P0-03.9 / .10（第三者逐語重なりの測定・帰属文言 → .3 / .14）、P1-07.13（.17 の prompt digest）、P1-07.19（平台の再読台帳 → .14 (a)、初回行は 11-14 の週、§4.0 の先行列）
- P1-12（承認記録の完備。.8 のバックフィル元 `logs/audit.jsonl` の行形、P1-12.5 の `AuditSource` → .19 (d)。2027-01 着手なので .19 (d) だけを後に回す）、P1-08.3（.19 の shell テスト harness）、P1-07.5（.14 (c) の `content_status` の 1 回の計数）
- P2-03（`release-doi` / `jsonld-knowledge-graph` skill が `~/.claude/skills/` にある）、P2-05（承認記録の投影。.14 の公開範囲）
- P3-02（装置の境界表。.10 の主張 ↔ evidence 対応）、P3-04.11（`origin` 語彙 → .8）、P3-07（介入チャネル登録表 → D-P3-05-6。B の記録先は P3-07.1 の (10) 行）
- 決定: D-P0-03-1 / D-P0-03-3（11-21、.12 の次版と .11 の表示名）、D-P0-03-2（10-10、`_gc_trash/` → .5 の表の行）
- 外部: Moltbook 規約の確認（P1-07.19 の台帳）、Zenodo / HF / SWH の操作と規約確認（オーナー、.14 (c)）
- → 参照元: P3-06.3（D-P3-05-1 の規則を論文 cutoff に適用、2027-Q2）、P4-03.3（事案時の該当行は D-P3-05-2 と .14 (c) の表に従い、表を `incident-response.md` に写す）、P4-02（wind-down runbook: 最終版 DOI、snapshot 窓の解除、サイズ読み値の消費。P4-02.1 の SWH save は .14 の表の後）、P3-06.3 / .4（版 DOI、改正ごとの入力 pattern 集合は P3-06.4 の束に同梱）、P3-01.3（再現ガイド .10 に再計算 script を載せる）、P3-02.3（.10 の再埋め込み手順）、P1-10.3（`SECURITY.md` が .14 の節へリンク）、P2-05.1（(A2) の同期条件として .19 の経路を後から読む）、P4-02.8（終了後の takedown 経路が .14 / .19 を引く）、P2-01.14（縮退順の「公開データの撤回経路」は .14 / .19 の分割で読む）


#### P3-06 論文・FLIP 供出・AAP への書き戻し・哲学読みの計器
- 狙い: ADR-0080 の研究層は「3 つの建立時の問いが論文化・拡散されること」（.md:62-68）、最終成果物は「データセット + 論文」（.md:73-77）だが、論文の器も投稿先も無い（CYCLES #7 の成果物は AKC / AAP の 3 本のみ）。オーナーの主関心（harness 層の責任構造と AAP への接続、CONTEXT §3）を第一候補にし、FLIP の公理比較には「実装観察」として束を供出する。四原則の機構カバレッジ読みは read-only 計器として置き、操舵しない。資金・商用を前提にしない（CONTEXT §4）。
- 期限・順序: 着手 2027-02-13 の土曜ゲート（§4.0）。期限 2027-Q2。先行: .9 / .11 は 12-05 の週（§4.0 の先行列。.9 は読みが溜まるのに 4 週要る）。順序: .1 の主題・種別決定を 2027-02-13 の土曜ゲート（D-P3-06-1。D-P3-07-1 と同じ回）→ .4 / .5 は P3-04.2 / .3 / .12 の完成後（2027-Q1）→ .6 / .7 は P1-12 の `docs/GOVERNANCE.md` 後（2027-Q1。AAP `CLAUDE.md:17-28` の対応表の更新は .7 と同じ AAP 側 PR）。.7 の AKC 書き戻し表は (a) を束の着手週に置き（P1-13.7 の AKC 側 PR に束ねる場合はその PR に同乗）、(b)(c) は発火条件つき → 論文ドラフト 2027-Q2、.3 の固定版は cutoff 時（D-P3-05-1 の版付け規則の適用も同じ時、2027-Q2）。決定は 3 件: D-P3-06-1（主題・種別、2027-02-13）、D-P3-06-2（FLIP 束の範囲、2027-03-06 — .4 はその B の実装で決定前は着手しない）、D-P3-06-3（沈黙分岐、2027-03-06、熟慮）。.9 の 4 列は materials 段の決定論 script か `pipeline/` JSON に出す（weekly packet は退役済み。`weekly-pipeline.sh` を触るなら P2-04.13 PR-A の後）。
- 束の完了条件:
  - `rfcs/` に論文計画 RFC が `state: accepted` で存在し、主題・種別・投稿先（SSRN + Zenodo）・図表リスト・「問い → 使うファイル → 版タグ」表を持つ。
  - FLIP 束が公開 URL（data repo `constitution/history/` + README）で指せ、突合 1 頁が `docs/evidence/adr-0092/` にある。
  - AAP に CA の case study・deployment record・open-questions evidence が入り、本体 README から link される。
  - 土曜の materials（`pipeline/` JSON か materials 段の決定論 script の出力）に .9 の 4 列が 4 週分出ている（weekly packet は退役済み）。
  - 論文 cutoff 用 `artifacts.md` の雛形（5 系統、装置を含む）が release runbook にある。
  - AKC ADR-0015 Decision 2 に CA ADR-0082 を引く dated Note（.7 (a)）が merge され、.7 の書き戻し表の (b)(c) 各行に発火条件と照合先 ID がある。

##### P3-06.1 論文計画 RFC（主題・種別・投稿先・図表・問い→ファイル→版）
- 何を: RFC を 1 本起票し、主題 A「harness 層の責任構造 — 人間ゲートを責任の行為として記録した 7 か月」（第一候補、CONTEXT §3）と B「3 つの建立時の問い」（dataset / empirical note、P3-01 / P3-03 の読みが揃ってから）を分ける。投稿先は SSRN（DOI・ORCID 連動）+ Zenodo、arXiv は任意。論文 A の後に companion 記事 1 本（「Why model-centric alignment papers miss the harness layer」、`zenn-content/` 側、Cycle #8。新項目にしない）。各問いに「使うファイル → 固定する版タグ → 必要な公開 projection」を 1 表で対応させる。資金・商用・査読料を要する経路は書かない。
- 根拠: `docs/CYCLES.md:90,151`（#7「drafted paper → Zenodo / SSRN deposit」= 投稿先は既定済み）; `docs/plans/how-to-build-your-shimmying-boot.md:38`「論文3本: AKC×1 / AAP×2」; `llms.txt:176-180` Papers 節は Laukkonen 2 本のみ; `rfcs/`・`docs/plans/` に論文執筆項目なし; ADR-0080 .md:62-68, 73-77。
- 完了条件: RFC が accepted で、種別・分量・締切・図表リスト・問い→ファイル→版タグ表を持ち、ドラフトの空骨格（見出しのみ）が repo にある。
- 規模・整合: M / neutral   出典: RF-27 RF-52 DE-39

##### P3-06.2 ゲート縦断記録の事前登録（論文 A の主データ）
- 何を: 「承認 = 責任の行為であって品質管理ではない」を外部に説明する指標を事前登録する: 採用率・却下理由分布・推奨↔裁定一致率・保留率・週次負荷（読み量・件数）。P1-12 の approver / reason 欄と P2-01 の負荷定義を前提に、`docs/evidence/gate/preregistration.md` 1 本と公開データの対応表を書く。
- 根拠: `README.md:36`（82 / 547、6 / 11、2 / 4 — 唯一の公開集計）; ADR-0099 .md:167-169（推奨同意率 ~100% = effective-filter 警告）; AKC `docs/adr/0014-failure-modes-of-the-bidirectional-loop.md:44-58`（gate complacency / deskilling は文献のみで実データ無し）; ADR-0080 の 08-26 追補（`:144-154`、438 / 53 の観察が機構層の完成条件を具体化した前例）。
- 完了条件: 事前登録 1 本（指標・予測・反証条件）が evidence にあり、各指標が公開ファイル（`pipeline/*.json`・承認記録の projection）に対応する。
- 規模・整合: M / instrument   出典: GO-43   注: 各指標の行に `reanalysis` 列（P3-01.1）
- 消費計画: (a) オーナーが論文 A の執筆時（2027-Q2）と、それまで四半期 1 回 P2-01 の負荷読みと並べて読む (b) 事前登録 1 本 + cutoff 時の 1 回の集計で、指標が予測と反証条件のどちらに落ちたかを論文に書く (c) 撤去条件: 論文 cutoff（.3）で集計を固定、以後は P2-05.2 の投影が出るだけで本項目は閉じる

##### P3-06.3 論文 cutoff の固定版 1 枚（code・data・rules・兄弟）
- 何を: release runbook に「論文 cutoff 手順」を足す: 本体 tag + 版 DOI、data repo の版 DOI（現状 v1.0.0 / 2026-06-17 の 1 つだけ、P3-05.12）、rules repo は P1-11.10 の tag `v0.2.0` を参照し SWH save / `.zenodo.json` の有無だけを本項目で決める、兄弟 3 repo（cloud / mlx / otel）の tag は P1-11.1 の方針（凍結 commit = tag = README 状態行 = pin 先）に従い本項目では SWH save の有無のみ。SWHID の形は P0-06.11（`rel` / `dir + qualifier`、`snp` 単独は不可）。`docs/evidence/paper-<id>/artifacts.md` に 5 系統を列挙する — 4 系統（code・data・rules・兄弟）に 5 番目の「装置」: 生成 / 埋め込みモデルの名前と digest、Ollama 版、審判 Jev の版、Claude の書き手モデル（P2-02.3）。装置の値は `serving_environment()`（`src/contemplative_agent/core/llm/__init__.py:468`）が書いた最終 snapshot の manifest から写す（Q1 は「small-local-model behavior」なのでモデルの同一性が再現の前提）。
- 根拠: 本体 `CITATION.cff:18`（版 DOI は v2.12.0 の 1 件 `10.5281/zenodo.22724623`）、`:30-51`（SWH `snp` 識別子 7 件 v2.6.0–v2.12.0 — 訪問スナップショットで版の tree を一意に指さない、R1-REP-01）; data `CITATION.cff:5-8`（version 1.0.0、DOI 20732894）; rules / cloud / mlx / otel に `CITATION.cff` `.zenodo.json` tag 無し（`git tag` 0 件。rules 直下に pyproject は無く bench は `contemplative-ipd` 0.2.0）。
- 完了条件: artifacts.md に識別子が 5 系統そろい（tag は P1-11.1 / P1-11.10 の値と一致、装置の値は最終 snapshot の manifest と一致）、論文の References から辿れる; data の版は D-P3-05-1 の版付け規則（実装は P3-05.12）で cutoff 直前に切られた版の Zenodo 版 DOI を引き、data repo `CITATION.cff` の version と一致する（論文が引く版は終了時の最終版 P4-02.2 とは別物。適用は 2027-Q2、本手順の後）。
- 規模・整合: S / neutral   出典: RD-15 RD-23 DE-39(版方針) R3-MDL F-3 RF-50

##### P3-06.4 FLIP に渡す束（human-gated self-revision アーム）を切る
- 何を: D-P3-06-2 B の実装（決定前は着手しない）。data repo `constitution/history/`（P3-04.2 / .3 / .12）を README つきで 1 束にする。中身: (1) 憲法 4 版の本文と来歴 — verbatim `e3b556…` 2026-03-07 / 03-27 版 = report 引用からの再構成・sha 不明・audit 以前、qwen3.5:9b・41 patterns / 05-05 版 `3d8a8503…` = ADR・ベンチ無し、audit 承認行はあり（`null-pair-reading.md:9-10` が content_hash 一致を確認）、生成モデルは qwen3.5:9b と推定 / 08-09 版 `37e3556a…` = gemma4:e4b think-ON・top-50 patterns。採択モードは 05-05 / 08-09 とも `adopt-staged --yes`（`README.md:38`）。版ごとに改正プロンプトの版（固定 4 節 → merge / split 可、P3-07.5）の 1 列、gate card、P3-04.12 の節 → technique 写像、P3-04.3 の rules 節、改正ごとの入力 pattern 集合を添える — gate card: 数字（staged 4 / adopted 2 / rejected 2、本文なし）・採択モード（両方 `stage-adopted-auto` = `adopt-staged --yes`）・判断材料（08-09: diff + `reasoning.md` + IPD report + AILuminate 読み; 05-05: diff + トレースのみ; 03-27: log 以前）・reason（null）の正本は P3-04.3 の CHANGELOG 行で、card はその行を描画するだけ。アーム名を「human-gated self-revision」とし、「proposal = adopted」が成り立つのは 08-09 のみ（staged sha `37e3556…` = 採択 sha）と明記する（P3-01.2 の限定行 (v) も同じ行を写す）; 入力 pattern 集合: P2-05.2 の決定ログ投影で value-layer 行（amend-constitution / distill-identity）に限り `source_ids` を全件出し、束に `inputs/<version>/patterns.jsonl`（id・本文・`valid_from`）と当時の `config/prompts/constitution_amend.md`（P3-07.5 で特定した版）を同梱する。03-27（41 patterns）と 05-05 は audit に lineage が無ければ「復元不能」と明記。公開のみで本番ループは不変（pattern 本文は既に CC0 公開）、(2) shadow 合成（`docs/evidence/adr-0092/`、Care 語彙 0）、(3) 11 プリセット憲法（`config/templates/*/constitution/`）を対照床、(4) 本体の探索的読み: 4 版 × IPD の表（P3-03.3）、IPD two-arm + null pair、AILuminate two-arm（harness `aelwood/contemplative_alignment@5242e74`・test Haiku 4.5・n=50 seed 42・judge claude-sonnet-5・未較正。生出力 `detailed_evaluations_20260809_*.json` の所在と再配布可否は P3-03.7 の RFC）。README の要件に配備形 3 行: (i) 本番 = identity + `---` + 憲法を system prompt に連結（`core/llm/prompting.py:218-229`）、SOUL.md / `operator-keyed` 不使用、(ii) IPD = user turn に raw 挿入（`llm_player.py:277-282`、paper-faithful の「contemplative pause」ラッパー無し）、(iii) FLIP harness = 彼らの technique ラッパー（P3-01.2 (iii) の限定行を写す）。依頼: 4 版を同一 judge・同一 run で（memo §論点2 の 03-27 値は退役した Sonnet 4 judge のもので新 run と絶対値比較できない）、版ごとの refusal / disclaimer 件数を judge 失敗と分けて併記（P0-07.3 の衝突語彙目録）、FLIP に無い縦断軸「改正ごとの per-axiom lift 推移」を足す。提示は memo §提示戦略どおり「実装観察」として。公理 / ルール分離案は添えない（P3-07）。
- 根拠: FLIP メモ `# AILuminate実験結果に対する論点整理.md` §論点2（Emptiness 76.8 / Non-duality 73.2 / Mindfulness 77.1 / Boundless care 78.5 = 2026-04、第 1 改正版のみ）; `docs/evidence/adr-0090/ailuminate-two-arm-report.md:1-22`（A: 05-05 / B: 08-09、non_duality 55.7 → 61.6、「彼らの Sonnet 4 は退役 404」、`:3-4` は生出力の名前のみ）; ADR-0090 .ja:215-222（harness commit・judge）、`:237-240`（08-09 の採択材料）; ADR-0092 .ja:26（gemma 下で唯一採択された改正 = 08-09）; `docs/evidence/adr-0092/shadow-run-1-reading.md:49-54,81-82`; gate card: 本体 `README.md:36,38`（「adopted 2 of 4 staged constitution amendments」「both logged constitution amendments were adopted」with `--yes`）、`src/contemplative_agent/cli/approval.py:90`（`stage-adopted-auto` = no human prompt）、却下 2 案の本文は未保全（P1-12.2）、reason は null（P1-12.1）。audit 行の細部は私有ログ未読（推測を含む）; 入力集合: `src/contemplative_agent/core/constitution.py:53-61,171`（ADR-0050 以降 `pattern_ids` = view 一致パターンの content-hash id）、`cli/approval.py:128-135,197`（audit 行の `source_ids`、lineage 無しは null）、data `snapshots/amend-constitution_20260809…/manifest.json` は `"views": []` で入力を持たない、`scripts/sync-research-data.sh:81`（`logs/` 除外 = audit 非公開）。08-09 行に `source_ids` が実在するかは私有 audit 未読（コード経路からは高い、推測）。
- 完了条件: オーナー側で閉じる — 束が公開 URL で指せ、README に来歴欄・配備形 3 行・gate card があり、送付記録 `docs/evidence/adr-0092/flip-handoff-<date>.md` に渡した sha 一覧と依頼文がある; gate card が P3-04.3 の CHANGELOG 行と同文（描画元）で、P2-05.2 の `pipeline/decisions/` の constitution 4 行と数字が一致する; 08-09 の 50 件が公開 id で解決し、`constitution_amend.md` + 親本文 + 50 件で第三者が生成段を再走できる手順が束 README にある（再走はモデルを問わず、本体の前提は変えない）。FLIP 側の結果表（05-05・08-09 の列）は「外部の読み値」として別記し、done の条件にしない。
- 規模・整合: S / neutral   出典: RF-41 R1-FLIP-01 R1-FLIP-04   依存: P2-05.2（`source_ids` と decisions の投影）、P3-07.5（`constitution_amend.md` の版）

##### P3-06.5 FLIP 3 仮説と本体の読みの突合 1 頁
- 何を: `docs/evidence/adr-0092/flip-hypotheses-crosscheck.md`: 仮説（制御可能性 / 空性の溶解圧 / 公理・ルール分離）× 本体の読み（shadow: Care 不在・3 公理再導出・IPD 協調効果保存、interpretation-notes の生成子 / 系、AILuminate で non_duality lift −7.8 / −2.9 — 同じ行に未較正の注記: baseline の run 間揺れ ~1.6 点、judge 失敗 9/300・15/300、n=50。−2.9 は揺れの範囲、−7.8 も単一 run なので「両アーム負」は方向の記述まで）× 整合・不整合 × 弁別実験（第一候補 = .4 の per-axiom lift 系列）。4 行目に「衝突語彙の除去 × non_duality 最弱の交絡可能性」を置く（P0-07.3 の目録を引く。原文だけが ADR-0005 の衝突語彙を持ち、frontier safety-trained モデル上では injection-defense の反応差が「進化版 vs 原文」差に混入しうる — 推測）。
- 根拠: FLIP メモ §論点2-3; `docs/evidence/adr-0092/shadow-run-1-reading.md:49-54`、`interpretation-notes.md:27-44`; `docs/evidence/adr-0090/ailuminate-two-arm-report.md:1,27`（non_duality lift −7.8 / −2.9、run 間揺れ ~1.6、judge 失敗 9/300・15/300、n=50）。
- 完了条件: 1 頁が存在し（lift の行に未較正の注記つき）、.4 の README から link され、FLIP への返信の下敷きになる。
- 規模・整合: S / neutral   出典: RF-44 R2-STAT F-15

##### P3-06.6 CA を AAP の「記入例」にする（case study・deployment record・GOVERNANCE link）
- 何を: AAP `docs/quadrants/case-studies.md` に 11 件目「(Running instance) Contemplative Agent」: runtime = LLM Workflow、週次セッション = operation-phase 配置、Phase-crossing = design へ戻す、gap-bearer = オーナー、10 ADR 充足表。AAP `examples/deployment-record.md`（空欄テンプレ: operator / adapter / gap-bearer / Phase-crossing / gate 一覧 / audit schema / handoff）と本体 `docs/DEPLOYMENT-RECORD.md`（記入例）。AAP README「Using this as an agent-adoption navigator」から本体 `docs/GOVERNANCE.md`（P1-12）へ「filled-in example」として link。deployment record の各行に「AAP ADR → CA の実物」を書く（ADR-0006 = `audit.jsonl` + `pipeline-metrics.jsonl` の `gate_item`、ADR-0005 = weekly-gate Step 4 / 6c、ADR-0008 = オーナー 1 名）。条文番号は本体に複製せず、AAP `docs/policy-mapping/eu-ai-act.md`（2026-08-04 読み）の逆引き表から日付つきで導出する（P1-12.7 と同じ規約）。この「AAP ADR → CA の実物」表を正本とし、P1-03.5 PR-C の ADR 索引の AAP 列はここから生成する（AAP `CLAUDE.md:17-28` の対応表は古い: 0006 / 0007 が「暗黙、essay で言語化」、0005 が CA ADR-0012 のみで ADR-0050 が無い。0002 行の「ADR-0028 / ADR-0029 audit」も照合対象 — 推測、要確認）。
- 根拠: AAP `docs/quadrants/case-studies.md` 見出し 10 件に CA 無し（`grep -ci contemplative` 0）; AAP `examples/` は `audit-tests` のみ; AAP `README.md:84-103,158-169`; 本体 ADR-0033 .md:45,56 / .ja:56（Phase-crossing observation はあるが、AAP 0010:107-113 の Phase-crossing decision と gap-bearer の記録が無い）; AAP `docs/policy-mapping/eu-ai-act.md:324`「Reverse index — EU AI Act Article → applicable ADR(s)」; 本体に `docs/GOVERNANCE.md` `docs/DEPLOYMENT-RECORD.md` 無し。
- 完了条件: AAP に case study + テンプレ、本体に記入例があり、AAP ADR-0008 / 0009 / 0010 と README から link、本体 README から逆 link; AAP の逆引き表の各 Article が AAP ADR 経由で CA の path に 1 つ以上届く（条文番号は本体に書かない）; P1-03.5 PR-C の AAP 列とこの表の diff が 0。
- 規模・整合: M / neutral   出典: GO-40 GO-41 GO-44 R3-AKC F3

##### P3-06.7 AAP の open questions に CA の運用経験を日付つきで書き戻す（AKC への書き戻し表を含む）
- 何を: AAP ADR-0008 Q2（24/7 と単一人間）・Q5（departure）、ADR-0010 Q1-3（operation-phase edge case / sequence-of-design-sessions / 再帰）に「Evidence from contemplative-agent (dated)」の箇条を足し、本体 ADR-0074（pending guard）/ 0085（土曜単一ゲート）/ 0098（自己供給ループ遮断）/ 0080 を引く。AAP `CLAUDE.md:34` の双方向更新規約に従い、AAP `CLAUDE.md:17-28` の CA 対応表を .6 の表に合わせる更新も同じ AAP 側 PR で行う。AAP ADR-0005 には「層 1（決定論・可逆・事後報告）の無人 archive は `--auto` 禁止の例外か否か」の dated note を、D-P2-07-1 / P2-07.5（R1-NS-01）の結論として書き戻す（P2-07.1 の ADR + P1-12.5 を引く。P2-07.1 は 2027-02-27 の着手なので、note は D-P2-07-1 の結論で書き、ADR が入ったらリンクを足す）。AKC への書き戻しも同じ形の 1 表（事実と発火条件だけ。編集は AKC / AAP 側の PR）で持つ: (a) 束の着手週: AKC ADR-0015 Decision 2 と graph の同旨 2 ノードに dated Note（AKC 0026 D3 の様式）「参照実装の集計は CA ADR-0082 で `{generated, unknown}` に縮退し `observed` は構造的に 0。self-generated share は CA では未測定、近い読みは P0-03.9 の逐語重なり測定」; (b) D-P2-07-3 の決定後: AKC ADR-0026 の Layer 2 / 3 未決に「CA の事例 = supersession のみ、書き込み時 expiry なし、保持方針 = 決定値」の dated note; (c) 発火条件つき: D-P1-12-1 / D-P2-07-1 / D-P1-13-1 で promote / archive の主体が変わった時と P4-02 の終了時に、AKC 3 面（`CLAUDE.md:32`、`llms-full.txt:163`、`graph.jsonld:699`）と AAP 3 面（`README.md:158`、`llms.txt:72`、`graph.jsonld:212`）の現在形の記述へ dated note（AKC ADR-0027 Decision 3）。P4-02.1 の手順 (5) から本表を参照する 1 行。
- 根拠: AAP `docs/adr/0008-one-agent-one-human.ja.md` Open questions 2, 5; `0010-phase-separation.ja.md:105-110`（Phase-crossing decision）, open questions（:284-300）; 3 本とも Status experimental; 本体 ADR-0098 .ja:92,159（自己供給ループを構造的に遮断）; AKC: `docs/adr/0015-loop-failure-modes-self-reingestion.md:108-115`（Decision 2: 参照実装 = CA の `epistemic_counts` `{observed, generated, unknown}`）、AKC `graph.jsonld:269` / `:453`、CA `docs/adr/0082-retire-observed-epistemic-key.md`（`observed` 退役）、AKC `docs/adr/0026-expiry-conditioned-knowledge.md:29`（Layer 2 / 3 の expiry は未決）と CA `core/pattern_dedup.py:91`（`valid_until` を書くのは UPDATE 時の supersession だけ）、AKC `docs/adr/0027-mental-model-and-instance.md:29`（Decision 3）。
- 完了条件: 0008 / 0010 に CA 由来の dated evidence、0005 に層 1 の dated note が入り、AAP 側で status 見直しの判断材料が揃う（accepted 化は AAP 側の判断）; AAP `CLAUDE.md:17-28` の表が .6 の表と一致する; AKC 書き戻し表の (a) の Note が AKC に merge され graph `:269` / `:453` と一致し、(b)(c) の各行に発火条件と照合先 ID（D-P2-07-3 / D-P1-12-1 / D-P2-07-1 / D-P1-13-1 / P4-02）がある; P4-02.1 の runbook に参照の 1 行がある。
- 規模・整合: M / neutral   出典: GO-42 R3-AKC F3 R3-AKC-01   依存: P1-13.7（AKC 側 PR を (a) と束ねてよい）、P0-03.9   順序: AKC の (a) は束の着手週（P1-13.7 に束ねる場合はその PR に同乗）、(b)(c) は発火条件つき

##### P3-06.9 四原則の機構カバレッジを materials の決定論的 4 列で読む
- 何を: 既存 episode / comment-outcomes から LLM 無しで: (a) note が「nothing stood out」系なのにコメントした率（Mindfulness: 検知 → 行為が切れている）、(b) 同一スレッドで自分が連続して最後の発話者である率（沈黙の不在）、(c) コメント当たり公理固有名詞の出現率と具体参照率（carewashing）に、Context に無い一般語の自己言及（constitution / axiom）の率を並べる（固有名詞は 2026-06〜10 のコメントで 0–2% しか出ず陰性対照がほぼ自明になるため。読みでありフィルタではない — `config/prompts/principles.md:22`）、(d) identity 本文に沈黙許可文があるかのフラグ（P3-04.8 の列と共有）。4 列は materials 段の決定論 script（`weekly-analysis.sh` の材料段、census と同じ置き場）か `pipeline/` JSON に出し、読み手は weekly-gate Step 6e と同形の 1 行（weekly packet は退役済み）。(a)(b) は週の分母（enforce 後コメント 25〜41 件/日、`rfcs/0046:178`）と Wilson 区間つき（区間は P2-01.9 の規則 `scripts/_stats.wilson_ci`、分母 < 10 は件数のみ）。
- 根拠: `src/contemplative_agent/adapters/moltbook/feed_manager.py:346-379`（note は取り出されるが `create_comment(post_text)` に渡らず、読んだ後に「やめる」分岐が無い）; `config/prompts/internal_note.md:3`; `config/templates/contemplative/identity.md:7`「it's okay not to respond to everything」が本番 `identity.md` に無い; ADR-0047 .md:41（axiom-label collapse）; ADR-0106 .ja:93 D4（実コメントを LLM で判定しない → 決定論的列のみ）; `config/prompts/principles.md:22`（語句ブロック禁止。読みであってフィルタではない）; `scripts/weekly-pipeline.sh:987`「no packet: the Saturday gate reads the artifacts directly」。
- 完了条件: materials に 4 列が 4 週分出る（(a)(b) は分母と区間つき）; 較正（陽性対照）: (c) が 2026-03 Phase 3（data `reports/analysis/agent-diachronic-analysis.md:54`「Emptiness 262 回」= 仮説を生んだデータ）で陽性; 陰性対照: 2026-09 の 1 週（予測 = 陰性）で陰性、の両方を過去データで確認。
- 規模・整合: S / instrument   出典: PF-04 PF-07 PF-20 PF-42 R2-STAT F-11 R2-GATE Fix-06   順序: `weekly-pipeline.sh` を触る場合は P2-04.13 PR-A の後（共通規則 H）
- 消費計画: (a) オーナーが土曜ゲートで materials の 4 列を 4 週分読む（12-05 の週から 4 週） (b) 4 週の読みで D-P3-06-3（沈黙分岐・ループ閉鎖の是非）を RFC で判断する (c) 撤去条件: D-P3-06-3 が A（記録のみ）なら 4 週後に列を materials から外し evidence に固定、B なら RFC の計器に引き継ぐ

##### P3-06.11 glossary に参照読みを 3 行足す
- 何を: `docs/glossary.md` に (1)「Emptiness（憲法条項、エージェントの値）」と「hold lightly（設計ヒューリスティック、ADR-0080 由来）」を別項目で、(2) Non-Duality の参照読み（論文 L124: 構築性の自覚であり区別の否定ではない。本体の self / other 境界は ADR-0007 で保つ）を 2 行。(1)(2) に「憲法内の capability 語は行為の質を指し、ADR-0080 .md:95 の capability（能力目標として却下した語）とは別義」の 1 句を添える。ADR-0080 は変更しない。
- 根拠: `docs/glossary.md:297-298` は翻訳表のみで axiom 項無し; ADR-0037 .ja:56 / `rfcs/0025:67`「sunk cost は理由にしない（Emptiness）」が Emptiness を統治メタルールとして引く; 現行憲法 L9「separation … is an illusion」対 論文 L124; 現行 L18「Let compassion expand your capability」対 ADR-0080 .md:95。
- 完了条件: glossary に 3 項目（(1)(2) に「ADR-0080 .md:95 の capability とは別義」の 1 句）、`git diff -- docs/adr/0080-*` が空。
- 規模・整合: S / neutral   出典: PF-26 PF-29 PF-40 R3-ADR Prune-01

##### P3-06.12 shadow 専用の `constitutional_paper` view（レンズ漂流と本文漂流の分離）
- 何を: 論文 verbatim（`config/templates/contemplative/constitution/`）を seed とする第二 view を shadow 計器にだけ足し、同じ patterns に対する 2 つの検索結果の重なり率を shadow record に記録する。本番の view は触らない。
- 根拠: `config/views/constitutional.md:2-4`（`seed_from: ${CONSTITUTION_DIR}/*.md` — 改正のたびレンズも動く）; ADR-0092 .ja:25-42（3 つの circularity channel）; RFC-0012 は `state: blocked`。
- 完了条件: view 追加 + shadow record に `overlap_vs_paper_view` 列、1 回目の値。
- 規模・整合: S / instrument   出典: PF-34
- 消費計画: (a) オーナーが shadow run ごと（P0-07 の改正ゲート、2026-10-31 以降の各回）に `overlap_vs_paper_view` を読み、.5 の突合 1 頁に 1 行足す (b) 改正 2 回分（2 読み）で「レンズ漂流が本文漂流に混入しているか（重なり率が改正ごとに下がるか）」を RFC-0012 の読みに書く (c) 撤去条件: 2 読みで重なり率が動かなければ view を落とす; RFC-0012 が withdrawn になれば同時に撤去


**依存**
- P3-04（.2 / .3 / .12 の history・CHANGELOG・lineage → .4 / .5）、P3-03.3（4 版 × IPD → .4 (4)）、P3-03.7（AILuminate の生出力の所在 → .4 (4)）、P0-07.3（衝突語彙目録 → .4 の依頼文・.5 の 4 行目）、P2-05.2（`source_ids` と decisions の投影 → .4）、P3-07.5（`constitution_amend.md` の版 → .4）
- P1-11.1 / P1-11.10 / P0-06.11（兄弟・rules の tag と SWHID の形 → .3）、P2-02.3（書き手モデル → .3 の装置系統）、P2-07.5（AAP 0005 への書き戻し → .7。P2-07.1 の ADR は 2027-02-27 着手なので入ったらリンクを足す）、AAP `docs/policy-mapping/eu-ai-act.md`（逆引き表 → .6）
- P3-01（研究問い ADR → .1 の主題 B）/ P3-02 / P3-03（読み → 論文 B）
- P3-05（DATACARD・DOI 版 → .3）/ P3-07（公理 / ルール分離 → .4 の範囲）
- P1-12（`docs/GOVERNANCE.md`・approver / reason → .2 / .6）/ P2-01（負荷定義 → .2）/ P2-05（承認記録の projection → .2）
- P4-01 / P4-02（終了判断・最終 sync → .3 の cutoff）
- P1-13.7（AKC 側 PR を .7 (a) と束ねてよい）、P0-03.9（.7 (a) の「近い読み」）、D-P2-07-3（.7 (b) の発火）、D-P1-12-1 / D-P2-07-1 / D-P1-13-1（.7 (c) の発火）
- ADR-0101（消費計画）、ADR-0072（echo-chamber 系列 → .9）、ADR-0106（comment-outcomes → .9）、RFC-0012（blocked → .12）
- 外部: FLIP 側の harness（judge Sonnet 4 退役）と返信タイミング、SSRN / Zenodo
- → 参照元: P3-01.2 (v)（.4 の gate card と同じ CHANGELOG 行を写す）、P3-01.1（.2 の `reanalysis` 列）、P3-05.12（.3 の版 DOI）、P3-04.3（rules 節の読者 = .4 の FLIP 束）、P3-03.8 (c)（改正生成器比較が .4 の入力 pattern 集合を読む）、P2-07.5（AAP 0005 の dated note は .7 が D-P2-07-1 の結論を引く）、P1-03.5（PR-C の AAP 列は .6 の表から生成）、P4-02.1（手順 (5) が .7 の AKC 書き戻し表 (c) を参照）


#### P3-07 「空性のみ公理」案と価値層への介入チャネルの決定
- 狙い: FLIP メモの「公理 = 空性のみ、三原則 = ルール」案は、本体の rules 層が「生成器無し・全件常時注入・沈黙の制約・gate 外・shadow / IPD / eval の対象外」である以上、本番エージェントで行えば三原則が「観測対象」から「所有者の固定指示」へ変わり、ADR-0050（gate = containment、所有者の意思を学習ループに入れない）と ADR-0097（所有者が rule を手書きする案の却下）からの離脱になる。一方で案の動機（空性と三原則の論理階層差、改正 cadence の分離）は shadow 系列の観測（Care を失い空性語彙を保つ）と噛み合い検証価値がある。「どの形でやるか」を決めると同時に、価値層へ届くオーナー意思のチャネル 12 本を 1 表に登録し、観測優先が守られているかを検証可能にする。
- 期限・順序: 着手 2027-01-30 の土曜ゲート（§4.0）。期限 2027-02（決定 D-P3-07-1 = 2027-02-13 の土曜ゲート）。.2（前提作業: rule の定義・改正経路・caveat）と .3（ADR-0017 / 0037 の dated note）を先に置き、RFC-0012 の shadow 読みが 10-31 due の改正ゲート（ADR-0091 の 83 日 = 2026-10-31、P0-07）で消費された後に D-P3-07-1 を決める。.1（登録表）は並行（(10) 行に P3-04.11 と D-P3-05-6 B の dated 実例）、.4 は P3-01.2 が書く ADR-0002 の dated note への 1 段落追記（P3-01.2 の後）、.5 は小さく随時。本番憲法はこの束では直接変更しない。決定は 1 件: D-P3-07-1。
- 束の完了条件:
  - D-P3-07-1 が ADR（採用）または RFC（検証）として state 付きで記録され、`contemplative-agent-data/constitution/` の変更は改正ゲート経由のみ（`.approval-join-state.json` の constitution digest が gate 記録なしに変わっていない）
  - 介入チャネル登録表の ADR が存在し、12 本 + exemplar 行の全列（分類 / 記録場所 / 公開の有無）が埋まり、ADR テンプレートに「価値層へのチャネルを足す ADR は表を更新」の 1 行がある
  - `docs/glossary.md` に「rule（本体）」項目があり、ADR-0017 / ADR-0037 に dated note、ADR-0002 の dated note（P3-01.2 の 1 本）に .4 の段落がある（rules repo ADR-0005 からの逆リンクは P1-11.12 の追補に含める）
  - `config/prompts/constitution_amend.md` の構造制約撤廃が commit・日付・理由つきで ADR から辿れる

##### P3-07.1 価値層への介入チャネル登録表（ADR）を書く
- 何を: 価値層へ届くオーナー意思のチャネルを 1 表にする — (1) ゲート y/N・`--yes`（`stage-adopted-auto`） (2) Markdown の手編集（ゲート迂回） (3) prompt 編集（`constitution_amend.md` の裁量条項、`identity_distill.md`「Keep it brief」、ADR-0072 D1 の register 指示） (4) view seed・exemplar・threshold（`self_reflection` の exemplar 4 件は人選、ADR-0072 D3） (5) 取得パラメータ（top_k 50、`MIN_PATTERNS_REQUIRED = 3`） (6) 抽出ガード句 `_EXTRACTION_FAILURE_PHRASES` (7) 語彙禁止（ADR-0074） (8) novelty gate の既知台帳 (9) 出口規則（ADR-0097 floor 600、ADR-0105） (10) 一括書き換え（2026-07-10） (11) Claude の eli5 推奨（一致率 45/45） (12) cadence 27 / 83 日。各行 = 分類（ゲート権限 / 観測設計 / 操舵疑い）/ 記録場所（audit source 名・ADR・git）/ 公開の有無。dated 実例の行を足す: (2) = 08-09 の憲法 twin（`contemplative-axioms-2.md`、両文が同時注入、手当ては ADR-0090:276-291「Remediated by hand within minutes … sha verified」）と 08-15 の identity twin（`identity-2.md`、04:02Z〜04:17Z に手当て、audit 行なし — 記録は P1-12.4 の `command: correction` 行「手当て: 誰が・いつ・`mv` 元→先・照合した sha」と P3-04.2 の dated note）; (3) = P0-07.8 の `constitution_amend.md` L11 削除（整合 neutral、実施は 10-31 の読み P0-07.1 / .2 の取得後、削除後の prompt sha12 を P3-04.3 の第 4 版行・P3-02.1 の境界表・P3-06.4 の束（入力 pattern 集合と当時の prompt）に書く）; (10) = 2026-07-10 の skill clean rewrite 10 件（data `_gc_trash/2026-07-10-clean-rewrite-originals/`、ゲート外 — いつ・誰が・何を。P3-04.11 はこの行を記録先にし、別の ADR 追補を起こさない）と、D-P3-05-6 = B を採る場合の 2 世代テンプレート 4 件を例外として残す記録。候補分類（推測）: (1)(2) はゲート権限、(4)〜(9)(12) は観測設計、(3)(10)(11) は操舵疑いとして根拠を書く。新チャネルを足す ADR はこの表の更新を必須にする（ADR テンプレートに 1 行）。
- 根拠: `src/contemplative_agent/cli/approval.py:90`（`stage-adopted-auto` = `adopt-staged --yes`、憲法 2 件とも `--yes`）、README:142（手編集はゲートを迂回）; `config/views/self_reflection.md:2-3,16`、ADR-0072:107-112（4 exemplar の appendix、rollback は 1 行削除）; `src/contemplative_agent/core/insight.py:63`、`core/distill.py:915`; ADR-0097:273（600 judged）; `.claude/skills/weekly-gate/SKILL.md:109`「オーナーは週次文書・findings を直接読まない」、`rfcs/0010:72`（45/45 = 100%）; ADR-0091:111「They are policy choices, not observed optima」; `src/contemplative_agent/cli/adopt.py:192-197`（twin 2 件の docstring: 08-09 憲法は harmful、08-15 identity は silent）、`config/prompts/constitution_amend.md:11`（L11「If the input claims a verbatim source, update that attribution to reflect revision」）; ADR-0050 Context と `docs/glossary.md:120` は steering を「所有者の修正を学習ループに反映する / 却下の書き戻し」と狭く定義し (3)〜(12) を分類していない。
- 完了条件: ADR が存在し 13 行（12 + exemplar）すべてに分類・記録場所・公開有無が入り、(2) の dated 実例 2 行と (3) の dated 行 1 行、(10) の dated 実例（2026-07-10 の 10 件。`_gc_trash` の 10 件と現行ファイルの対応が辿れる。D-P3-05-6 = B なら 4 件の例外行も）がある; `docs/adr/README.md`（またはテンプレート）に更新義務の 1 行; P2-01 の負荷計器が表の行 ID で参照できる。
- 規模・整合: M / neutral（ADR 文書）   出典: VL-35 VL-25 R2-VL Fix-01 Fix-06 R3-ADR Merge-07

##### P3-07.2 「空性のみ公理」案の前提作業（rule の定義・三原則の改正経路・因子分解の caveat）
- 何を: D-P3-07-1 を決める前に 3 つを揃える。(a) `docs/glossary.md` に「rule（本体）」を 1 項目定義する — 注入様式 = 全 rule を常時・無選択で注入し「決して語らない沈黙の制約」/ 生成経路 = generator 無し、ADR-0097 D7 の family 昇格（A′ = gemma が Practice/Rationale を合成し人間 gate）のみ / 観測 = shadow・IPD・eval の対象外 — し、三原則がこの定義に入るかを判定する（テンプレの rules は逆向きに Emptiness・Non-Duality を規則化している）。(b) 案を採る場合の ADR 受理条件に「三原則 rules にも改正経路（A′ の家族昇格、または定期 shadow 対象化）」を必須にする（空性だけが改正可能だと三原則が物象化し、論文 L167 の警告の裏返しになる）。(c) `docs/evidence/adr-0092/interpretation-notes.md` に「generator / corollary 因子分解（同体大悲）は D-P3-07-1 の根拠にしない — IPD は Care を見ない」の 1 行と、判定実験 = P3-03.5 の distress two-arm を明記する。
- 根拠: `config/prompts/learned_rules_framing.md:1`「silent behavioral constraints … must never be announced or narrated」; `src/contemplative_agent/core/llm/prompting.py:327-336`（全 rule を無選択で連結）; ADR-0097:462「The rules layer has no generator」、:310-318（A′）; `config/templates/contemplative/rules/hold-lightly.md:1-7`（「Never treat any belief … as final」= Emptiness の規則化）、`non-adversarial.md:3-7`; 本番 rules 2 件（`contemplative-agent-data/rules/*-20260411.md`）は distill 調; 論文 `2504_15125_fulltext.md:167`「ensure emptiness itself is not reified」、:134-137（cold wisdom / dumb compassion = 知恵と慈悲は相互に還元できない）; `interpretation-notes.md:27-45,86-91`「one factorization the data admits, not the only one」。
- 完了条件: glossary 項目が存在し D-P3-07-1 の RFC / ADR から参照される; ADR 受理条件に「三原則の改正経路」節; interpretation-notes に caveat 行と判定実験の名指し。
- 規模・整合: S / neutral   出典: PF-16 PF-17 PF-28

##### P3-07.3 ADR-0017 / ADR-0037 に dated note（再バランス手段の処遇・憲法層のフレーム）
- 何を: ADR-0017 に日付つき段落を 2 つ足す。(a) L73 の再バランス手段（prompt weighting / system prompt での公理順序 / `distill_identity` の「transform not eliminate」文言）は ADR-0050 以降は value-steering として退役し観測に委ねる（ADR-0057 が identity の reframe を意図的に neutral に保った事実が根拠）、または依然 open、のどちらかを明記する。(b) 憲法層に効くフレームは「未決 / 唯識（轉依）/ 中観（空性頂点）」のどれかを明示する — ADR-0037 は唯識優先を memory 層に限定し、FLIP メモは中観標準（空性を頂点とする階層）で、ADR-0017:61 が却下した読みそのもの。ADR-0050 の References から逆参照する。
- 根拠: ADR-0017:53「Emptiness overpowering Non-Duality in practice is the observed bug. The fix is rebalancing, not choosing a side」、:73「Possible vectors include prompt weighting, axiom ordering in the system prompt, and explicit 'transform not eliminate' phrasing」、:17（唯識の核 = 轉依）、:61（Pure Emptiness / Zen-school framing は Rejected）、Status は accepted で note 無し; ADR-0057:52-56（reframe を neutral に保つ sub-decision）; ADR-0037:50「Scope is memory architecture only … Constitution, skill layer, and agent stance are out of scope」、:82（Yogācāra dogma risk）; `docs/adr/README.md:133-135`（0017 は Worldview ADR）; FLIP メモ L106-118。
- 完了条件: ADR-0017 Status / Consequences に日付つき段落 2 つ; ADR-0050 References に逆リンク; D-P3-07-1 の RFC / ADR から参照される。
- 規模・整合: S / neutral   出典: PF-03 PF-27

##### P3-07.4 ADR-0002 に dated note（解釈キーの不適用と referent の逆方向拡張）
- 何を: P3-01.2 が書く本体 ADR-0002 の dated note（「配備形は論文の介入と異なる」、1 本）に 1 段落を追記する（別の note を起こさない）: 「rules repo の解釈キー（ADR-0005、`operator-keyed`）は frontier chat の配布面向けで本体には適用しない（本体はローカル gemma で injection flag が生じない）。キーが directives の referent を『作業結論』に狭めたのに対し、本体の改正済み憲法は referent を『自分の計算構造（memory artifacts, defined boundaries）』まで広げており（第 3 改正 L5, L10, L18）、これは観測対象である」。rules repo ADR-0005 からの逆リンクは P1-11.12 の追補（観察終了条件）に 1 行含める（本項目は本体 ADR-0002 側のみ）。
- 根拠: rules `docs/adr/0005:19`（同じ条項は Claude Code では flag されない — 決定変数はモデル世代でなく surface）、`:62`（効果は未検証、n=1）; 本体 `git log --all -i --grep "interpretive|operator-keyed|SOUL"` 該当なし; `config/templates/contemplative/constitution/contemplative-axioms.md` は rules repo の verbatim と diff 同一; `contemplative-agent-data/constitution/contemplative-axioms.md:5,10,18`。
- 完了条件: ADR-0002 の dated note（P3-01.2 の 1 本）にこの段落があり、ADR-0002 の dated note は 1 本のまま（rules ADR-0005 の逆リンクは P1-11.12 側の完了条件）。
- 規模・整合: S / neutral   出典: PF-18 R3-ADR Merge-06   依存: P3-01.2

##### P3-07.5 改正プロンプトの構造制約撤廃を記録する
- 何を: `config/prompts/constitution_amend.md` が「4 固定節・追加 / 削除 / 改名不可・最大 4 条項」から「merge / split / rename 可・1–4 条項・Source 行の書換」へ変わった時期と理由を特定し、短い記録 ADR か既存 ADR の dated note に書く。shallow clone では 2026-08-16 以前が見えないので、オーナーの完全 clone で `git log -p -- config/prompts/constitution_amend.md`（外部化前は `prompts.py` 等）を引く。時期は第 1 改正（03-27、固定節のまま）と第 2 改正（05-05、表題「Fluid Constitutional AI Clauses」・節名が変更済み）の間と推定。この撤廃は節名変更・Source 行書換・referent 拡張を可能にした研究条件そのものなので、.1 の (3) 行から参照する。
- 根拠: `config/prompts/constitution_amend.md:9`「merge or split sections, rename them if the structure no longer fits」、:11、:13「Keep 1-4 clauses per section」; 旧制約の記録は `contemplative-agent-data/reports/analysis/constitution-amendment-report.md:44`「the four axiom sections … cannot be added, removed, or renamed … (max 4 per section)」のみ; `docs/evidence/adr-0090/constitution-2026-05-05-retired.md:1`; ADR-0092:27 は現行文言を引用するだけで変更日を持たない; CHANGELOG・ADR-0054 に該当エントリ無し; shallow clone の最古 commit は 2026-08-16（`git log --reverse`）。
- 完了条件: `constitution_amend.md` の冒頭コメントか ADR から commit sha・日付・理由が辿れる; .1 の登録表 (3) 行がそれを参照する。
- 規模・整合: S / neutral   出典: PF-11


**依存**
- RFC-0012（shadow 読みの消費 = 10-31 due の改正ゲート、83 日 = 2026-10-31）、P0-07（10-31 due の改正ゲートで価値層の変数を 1 つに保つ。改正が起動されるのは D-P0-07-1 = A の回、B なら以後最初に起動された改正）、P3-01.2（ADR-0002 の dated note 本体 → .4）、P2-05.7（値層の変化系列 = D-P3-07-1 (ii) の静止・漂流の読み値）
- 現行の形で書き、入ったら更新するもの（本束の着手 2027-01-30 より後）: P3-03.5（distress two-arm = D-P3-07-1 の判定実験。P3-03 の着手は 2027-02-20、可否は D-P3-03-1（12-26）で決まるので、.2 (c) は実験を名指して書き、RFC が入ったら state を足す）、D-P3-03-3（2027-02-20。2 体目 = B 案の前提で、B を採る場合の実施はその後）
- P1-03（ADR テンプレートへの 1 行）、P1-11（rules repo の同期・ADR-0005 逆リンク）、P1-12（チャネル (1) の承認記録の完備、P1-12.4 の `correction` 行 = (2) の実例の記録）、P3-04（(10) 一括書き換え 2026-07-10 の版履歴、P3-04.2 の identity twin dated note、P3-04.3 の rules 節）、P0-07.8（(3) の dated 行）
- 外部: オーナーの完全 clone（.5 の commit 特定）、FLIP グループへの返答のタイミング
- → 参照元: P2-01（負荷計器が .1 の登録表の行 ID で参照）、P3-05（D-P3-05-6 と .1 の介入チャネル判定）、P3-04.14 / D-P3-04-3（チャネル (5) として審査）、P3-06.4（公理 / ルール分離案を添えない = D-P3-07-1 の後）、P1-11.12（.4 の逆リンク）、P3-04.11 / D-P3-05-6 B（(10) 行の dated 実例を記録先にする）


### Phase 4 — 終わり方（予約 2026-12 ／ runbook の dry-run 2027-03、最終版の形（D-P4-02-2）は 2027-Q2）

終了条件そのものは決めない（RFC-0006 の withdraw を尊重）。決めるのは「いつ・誰が・何を材料に検討するか」と、検討の結果が「止める」だったときの手順だけ。Moltbook が閉鎖された場合も移植しない。

**このフェーズの完了条件**
- ADR-0080 追補に検討イベント・判断役・材料・記録先が 1 段落で書かれている（P4-01）
- wind-down runbook が存在し dry-run が通る（P4-02）
- 継続者向けの最小指示と引継ぎチェックリストが repo にある（P4-03）


#### P4-01 終了判断の検討イベントと判断役を予約する
- 狙い: ADR-0080 第 5 層「designed termination」は RFC-0006 withdraw（2026-09-28）で「いつ」と「どうやって」が一緒に棚上げされた。終了条件は決めない（オーナー判断を尊重）が、「止めるかを検討するセッションを開く」観測可能なイベントと、判断役・材料・記録先を ADR-0080 の日付つき追補で予約する。Moltbook 閉鎖時は移植しない。
- 期限・順序: 着手 12-19 の土曜ゲート（§4.0）。期限は決定 12-19 / 追補 PR 12-21〜25 — 12-19 のゲートで決定 3 件を打ち、追補（2026-12）の段落（.1、決定の結論を書くので PR は決定の後）を 12-21〜25 の平日に 1 本 merge する（P1-03.8 の束ね。CLAUDE.md § 北極星を同 PR で同期 — ADR-0080 08-26 追補 §C の規約。別番号の追補は振らない）。.5 は P1-12 の `docs/GOVERNANCE.md` の後（2027-02）に書き分ける。決定は D-P4-01-1 / D-P4-01-2 / D-P4-01-3 の 3 件がすべて 12-19 の土曜ゲート（旧 D-P4-01-4 は削除し D-P3-05-1（11-14）に統合。その規則を論文 cutoff に当てる順序は P3-06.3 の完了条件が持つ）。検討イベント C（Moltbook 到達不能 7 日）の観測元は P2-04.4 の予定の行名で名指すだけで、行の実装（P2-04 着手 2027-02-06）は待たない — 追補は現行の形（予定の行名 + 土曜ゲート Step 0 で人間が PIPELINE-STATUS の到達性を読んで代替）で書き、行が入ったら更新する（.1）。検討イベント B の材料（P2-01.5 の出力、P2-05.7 の変化系列）は追補（2026-12）の前に存在する。P4-02 runbook（how）と P4-03（継続性）はこの追補を参照する側。
- 束の完了条件:
  - 12-21〜25 に merge した `docs/adr/0080-north-star-layered-end-state.md` の追補（2026-12）（P1-03.8）に when / how の分離、検討イベント ≥ 1、判断役・材料・記録先、Moltbook 閉鎖 = 終端の段落（.1）があり、`CLAUDE.md:78` が同 commit で同期（`scripts/docs_consistency_scan.py` の差分 0）
  - 2027-02（P1-12 の `docs/GOVERNANCE.md` の後）: `docs/GOVERNANCE.md` に operator unavailability 節があり、AAP ADR-0008:82-87 との対応が書かれる（.5）

##### P4-01.1 ADR-0080 第 5 層に「when と how の分離」・検討イベント・判断役と材料・Moltbook 終端を 1 段落で追補する
- 何を: 追補（2026-12）（P1-03.8）の 1 段落として書く: (a) 終了「条件」は再起票しない（RFC-0006 の withdraw を維持）、(b) 手順は P4-02 の runbook（発動条件を持たない）、(c) 観測可能な「検討イベント」を 1 つ以上予約 — 候補: 研究層 3 問の公開の答えが出揃った時（ADR-0080:72-78 の 2 条件のうち「残る問いが別の実験を要する」側）/ 値層の採用が 8 週連続 0（同「read-only 計器が代謝の定常を示す」側。下限は D-P2-01-3 の 8 週（adopted 0 ∧ archived 0 ∧ identity 更新 0）に一本化し、材料は P2-01.5 の出力列）/ Moltbook 到達不能 7 日（観測元は予定の行名 = `scripts/pipeline_watchdog.sh` の P2-04.4 (c) 行「comment-report 不在 7 日」の `PIPELINE-STATUS.md` ❌。行が入るまでは土曜ゲート Step 0 で人間が PIPELINE-STATUS の到達性を読んで代替する、の 1 文を同じ段落に）/ 候補 4 つ目: 人間の再読台帳（P1-07.19、`docs/evidence/moltbook-platform-readings.md`）に平台の規約改定・閉鎖告知の行が書かれた時（無人チェーンは平台の仕様文を取りに行かない — `scripts/api_drift_scan.py:290-296` — ので観測元は人間の台帳になる）。イベントは「検討セッションを開く」だけで、停止を含意しない（D-P4-01-1）。(d) 同じ段落に「判断役 = オーナー。材料 = 直近 N 週の weekly 計器 JSON（P2-01.5 の出力列 = 週次パターン増分・P2-05.7 の `pipeline/value-layer/changes.json` の変化系列・staged 件数）。記録 = 本 ADR の追補 + data repo `final` タグの commit message + 本体 CHANGELOG の Ending 節」。「定常」の状態定義は今は書かず、イベント発火時に新計器を建てずに上の列で事前登録する、と注記し、パターン層（+300..+700/週）と値層（staged 0 が続く一方、snapshot の digest では identity 09-12・skills 09-12 / 09-19 に変化）で読みが一致しない現状を 1 文。(e) 同じ段落に 1 行「Moltbook の閉鎖・到達不能の恒久化はこの観察走行の終端。別 platform への移植はしない（新しい実験は新 repo）。SNS 側の Protocol は作らない」（D-P4-01-2）。P2-04.4 の 7 日行が検知面、判断は人間。
- 根拠: `rfcs/0006-heartbeat-end-state-criteria.md:1-3`（`state: withdrawn 2026-09-28`）、`:101-103`（「辞めるときなんて今考えなくていい」/ 照合先が 1 回きりで 12 回素通り /「定常を見てから止め方を決める」は事前登録と逆順）/ `docs/adr/0080-north-star-layered-end-state.md:72-78`（第 5 層、`:76-78`「The final deliverable is the longitudinal record … not the agent instance itself」）、`:140-142` Note「a new entry is filed when it becomes one」、`:175-182`「sufficiency is deliberately left to the owner's judgment」（機構層の話で第 5 層に判断役・記録先は無い）/ `CLAUDE.md:78` / data repo `reports/analysis/observation-ledger.jsonl:4` baseline「+300..+700 patterns/week, plateau-shaped」と `reports/analysis/weekly-2026-10-02.md:180-184`（insight 再開後 staged 0）/ SNS 側に抽象が無い — `src/contemplative_agent/adapters/moltbook/agent.py:285-300`（具象 `MoltbookClient`）、`src/contemplative_agent/core/llm/backend.py:140-141`（LLM 側だけ `LLMBackend` Protocol）
- 完了条件: 追補（2026-12）に 1 段落（検討イベント ≥ 1 件、各イベントの観測元（計器 JSON = P2-01.5 の出力と P2-05.7 の `changes.json` / watchdog の P2-04.4 (c) 行（予定の行名）/ 公開の答え表 / 人間の再読台帳 P1-07.19）がファイル名で名指し、watchdog 行が入るまでの代替（Step 0 の人間の読み）が 1 文）; 同じ段落に判断役・材料（P2-01.5 の出力と P2-05.7 の `changes.json` をファイル名で名指し。この束では新 ADR・新 script は作らない）・記録先の 1 文と、Moltbook 閉鎖 = 終端・移植しないの 1 行がある（以後 `rfcs/` に移植系 RFC が起票されたらこの行を引いて withdrawn にする）; CLAUDE.md § 北極星の同 commit 同期は P1-03.8 の完了条件
- 規模・整合: S / neutral   出典: AB-15, DE-31, R3-END Fix-05, DE-45, DE-40, AR-30, R4-CUT Merge   依存: D-P2-01-3（11-28）、P2-01.5、P2-05.7、P1-07.19。順序: 追補 PR は 12-21〜25（D-P4-01-1〜3 の後）。注: P2-04.4 は行名を引くだけで先行条件ではない（現行の形で書き、行が入ったら更新）

##### P4-01.5 オーナー不在時に「誰が止める・続ける」を GOVERNANCE.md に書く
- 何を: `docs/GOVERNANCE.md`（P1-12 で新設）に「operator unavailability」節: (a) 停止権限者 = オーナーのみ、(b) 停止手順 = P2-04.3 の完全停止 + register 解除、(c) ゲート不在 N 週で止めるかと N の値（D-P4-01-3 に 1 本化し、節には決定の N を数値で書く。推奨は「承認済み値層で動き続けるのは ADR-0012 の設計どおり」と宣言し N 週（推奨 N = 4 週）を P4-01.1 の検討イベントに加える。自動 read-only 化はしない。PIPELINE-STATUS の「最終ゲート日」行の表示と watchdog の fail 行は D-P2-01-4 の側）。AAP ADR-0008「halts at the next approval gate」との対応（値層では満たす、外部表面は承認済み値で継続）を明記。
- 根拠: AAP `docs/adr/0008-one-agent-one-human.md:82-87`「If the accountable operator is unavailable … the agent halts at the next approval gate rather than defaulting to permissive behavior」/ `docs/CYCLES.md:86-87`（row 3 の agent は human gate「—」で継続、row 4 の値層だけ `adopt-staged` ゲート）/ `scripts/pipeline_watchdog.sh` に gate_record の鮮度検査なし（`:190` は読み手案内のみ）/ `docs/GOVERNANCE.md` 不在（`ls` 結果）
- 完了条件: 節が存在し、AAP 0008:82-87 との対応表（値層 / 外部表面 / 停止権限）が 3 行、P4-03.1 からリンク
- 規模・整合: S / neutral   出典: GO-39, R3-END M-1   依存: P1-12（`docs/GOVERNANCE.md` の新設）、D-P4-01-3（12-19）   順序: 2027-02（P1-12 の GOVERNANCE.md の後。12-19 には閉じない）


**依存**
- P2-04.3（完全停止手順 — .5 (b)）/ P1-07.5（census 規則 PR で `content_status` の非 null 件数を 1 回数える。非 0 なら第 5 章の延期行から moderation 行を起こし、自己投稿面の非 0 を検討イベントの入力にする）
- P2-01（AB-30: 研究層の答え表、北極星の読み値; P2-01.5 の出力列 = イベント B の材料）、D-P2-01-3（検討イベント B の下限 = 8 週）、P2-05.7（値層の変化系列）/ P3-01（研究問いの操作的定義 — イベント A の「答えが出揃う」の定義）
- P1-07.19（人間の再読台帳 = 候補 4 つ目の観測元）
- P1-12（`docs/GOVERNANCE.md` の新設、approver 欄）
- ADR-0080 08-26 追補 §C（追補時は CLAUDE.md を同 PR で同期）
- P1-03.8（追補（2026-12）の受け皿）
- → 参照元: P4-02（how = runbook は追補（2026-12）の when / how 分離を引く）、P4-03（継続性 — .5 の operator unavailability 節を P4-03.1 がリンク）、P1-03.9（D-P4-01-1 B の基礎率を 8 週で計算）、P2-01 D-P2-01-4（PIPELINE-STATUS の「最終ゲート日」の表示と watchdog の fail 行だけ。不在 N 週で止めるかと N の値は D-P4-01-3）/ P2-04.4（Moltbook 到達不能・7 日 0 件の watchdog 行 = 検討イベント C の観測元。着手 2027-02-06 で追補より後なので依存ではない — 追補（2026-12）は現行の形（予定の行名 + 土曜ゲート Step 0 の人間の読みで代替）で書き、行が入ったら更新）


#### P4-02 wind-down runbook（手順のみ・発動条件を持たない）
- 狙い: ADR-0080 第 5 層は「designed termination」を end state の一部とするが、停止手順書が無いので終わりは forced（Mac 故障・platform 停止・オーナー不在）にしかならない。手順だけを `docs/runbooks/wind-down.md` に置き、発動条件は持たせない（P4-01 の検討イベント + 人間判断）。
- 期限・順序: 着手 2027-03-06 の土曜ゲート（§4.0）。期限 2027-Q1 に dry-run まで。前提: P2-04.1 / .3（sync-data の管理下化・完全停止手順）、P0-03（`.bak`・絶対パスの除去）、P1-11（兄弟 repo の処遇決定、rules は D-P1-11-6）。最終版チェックリスト（.2）は P3-05 の DATACARD 改訂と同じ手で。.1 の SWH 保存要求は撤回の到達範囲表（P3-05.14 の takedown 節の表）の後。.6（鍵の失効表）は P1-10.9 の runbook の後で、保持期限は .8 の alias 存続期限と同時に決める。.7 は P2-04.3 の完全停止節から 1 行リンクされる。dry-run は各手順の確認コマンドと所要時間の計測まで（(3)〜(6) の外部操作は実行しない）。決定は D-P4-02-1（2027-02-06 の土曜ゲート、dry-run の前）と D-P4-02-2（熟慮。P3-05 の DATACARD 改訂と同時、2027-Q2）。.6 / .7 / .8 は .1 と同じ `wind-down.md` の PR。
- 束の完了条件:
  - `docs/runbooks/wind-down.md` が存在し `docs/runbooks/README.md` の表に行があり、各手順に確認コマンドと期待出力と「可逆 / 不可逆」列、(2) と (3) の間に中止線 1 行、鍵・資格情報の失効表（.6）・repo 外の定期処理（.7）・終了後の takedown 経路と保持期間（.8）がある
  - dry-run を 1 回実施し（各手順の確認コマンドと所要時間の計測まで。(3)〜(6) の外部操作 — `final` tag・Zenodo 採番・SWH・HF 最終 upload・GitHub archive・本体最終リリース・兄弟 archive・Moltbook 処遇 — と launchd 停止は実行しない）、所要時間と日付が runbook 末尾に記録
  - 最終版チェックリストの各項目が機械検査可能（`ls knowledge.json.bak*` が空、`grep -c '^## '`、DATACARD の volumes 表 = manifest 集計 など）
  - 本体・data の「終了状態」文言テンプレ（README Status 行・CITATION・HF card）と兄弟 4 repo の GitHub archive の操作・条件が runbook にある（兄弟 README の状態行は P1-11.1 が正本）

##### P4-02.1 `docs/runbooks/wind-down.md` を書き、順序を固定する
- 何を: (0) `com.moltbook.agent` を先に unload（新しいセッションを起こさない）→ (1) 最終 weekly chain を手動 1 回 + 最終の土曜ゲートで staged を全件裁定し `gate_record` に終了 verdict を 1 行 → `distill` → `sync-data` → `backup-runtime.sh` → (2) 残りの launchd job を停止（P2-04.3、`launchctl list | grep com.moltbook` が空）と repo 外の定期処理の停止（.7）→ 中止線「ここまでは `install-schedule` の再実行で再開できる。(3) の Zenodo 採番以降は戻せない」→ (3) 最終 sync → 最終版チェックリストの deposit 前項目（.2）→ data repo `final` tag（P0-06.6 の段 8 と同じ条件: D-P3-05-1 (b) が B / C なら data repo の Zenodo–GitHub 連携は off のまま（オーナーが設定画面で確認し日付を releases.md の備考に）、data repo では GitHub Release を作らない）→ P0-06.6 の段 8（D-P3-05-1 (b) の形で deposit。手順実体は release runbook へリンク。GitHub–Zenodo 連携が tag ではなく Release で動く点は外部知識・未確認）→ SWH 保存要求 → HF 最終 upload → GitHub archive → (4) 本体の最終リリース（.4）→ (5) 兄弟 archive（.5）と AKC / AAP の現在形の記述への dated note（P3-06.7 の書き戻し表の AKC 行を参照する 1 行）→ (6) Moltbook 処遇（.3）→ (7) private backup の最終 push と保管先記録、`takedown-requests.jsonl` の移送（.8）。各手順に「可逆 / 不可逆」列と、その時点の鍵の処置（.6 の表）。data repo のローカル clone は weekly chain が止まるまで残す。DE-01 の履歴書換をするなら `weekly-analysis.sh` の日付検索が壊れないことを 1 回確認。dry-run は確認コマンドと所要時間の計測まで（(3)〜(6) の外部操作は実行しない）。
- 根拠: `docs/runbooks/` は 5 本 + `rca/`（wind-down / decommission 無し、`grep -rn -i "wind-down\|decommission" docs rfcs` 0 件）/ `scripts/sync-research-data.sh:69`（`rsync -a --delete` 日次 push。archive 後も動けば push 失敗が WARNING のみ `:127-129`）/ `scripts/weekly-analysis.sh:170-190`（`$DATA_REPO` の `git log --before=` で週の state diff を取る — 日付検索で SHA 非依存）/ data repo `CITATION.cff` に SWH 無し / `config/launchd/com.moltbook.agent.plist:45-47`（`StartCalendarInterval` の定時起動 — (1) と (2) の間に新しいセッションが入りうる）
- 完了条件: runbook が存在し (0)〜(7) の各手順に確認コマンドと「可逆 / 不可逆」列、(2) と (3) の間に中止線 1 行、(1) の後に未裁定の staged 0 件（土曜ゲートの census と同じ数え方）、(5) に P3-06.7 の書き戻し表（AKC 行）への参照 1 行、(3) の `final` tag の段に Zenodo–GitHub 連携の条件 1 句、dry-run 1 回の記録（確認コマンドと所要時間。外部操作は実行しない）、履歴書換後に `weekly-analysis.sh` が 1 回成功
- 規模・整合: M / neutral   出典: DE-32, DE-34, RF-51, R3-END Fix-01 / Fix-02 / Fix-03, R3-AKC-01, R4-ONEWAY Fix-02   順序: (3) の SWH 保存要求は P3-05.14 の撤回の到達範囲表（各行に確認日）の後（R2-ETH-04）。(3) の `final` tag と deposit は P0-06.6 の段 8 と D-P3-05-1 (b) の形

##### P4-02.2 最終スナップショットのチェックリスト（何を直してから、どの形で切るか）
- 何を: DATACARD（または runbook）に最終版チェックリスト: `.bak` 除去（P0-03）/ snapshots 回転窓の履歴分を tree に戻すか（D-P4-02-2）/ DATACARD に最終 volumes（patterns・reports 日数・snapshots・skills・期間・モデル digest 表を manifest から集計、「volatile volumes は書かない」規約の切替）/ regime 表（P3-02）/ `llms.txt`・`CITATION.cff` version・`graph.jsonld` 更新 / `final` タグ・Zenodo 版 / DATACARD に `status: archived (ended YYYY-MM-DD)` + Maintenance 節 / HF card に "frozen as of" / README バナー。deposit 前の 2 項目（手順 (3) の deposit より前に満たす）: data repo の「毎日同期・生きている」表記に状態語を付けるか書き換える / `takedown-requests.jsonl` の未判断行 0 件（P3-05.14 の受付台帳）。
- 根拠: data repo `DATACARD.md:3-5`「not volatile volumes … read the directories directly」、Maintenance / status 節無し（grep 0）/ `knowledge.json.bak-dup-cleanup-20260718` 70 MB、`snapshots/` 100 本 28 MB（`core/snapshot.py:34` `MAX_SNAPSHOTS = 100` で回転。distill 84 / insight 11 / identity 2 / その他 3。data repo は shallow clone で履歴上の総数は未確認 — 推測で数百）/ Zenodo の GitHub release zip は tree をそのまま含む / data repo の 8 面が live 表記 — `README.md:9,11`（auto-synced）、`:52`（Live agent on Moltbook）、`DATACARD.md:4,93`、`llms.txt:21,142`、`CITATION.cff:25`、`NOTICE:4`、`.zenodo.json:10`（最終 Zenodo record は不変なので deposit 前に直す）
- 完了条件: チェックリストが存在し各項目に確認コマンド（例: `ls knowledge.json.bak*` が空、`python3 -I` で manifest 集計 = DATACARD 表）; deposit 前の項目として `grep -rniE 'auto-synced|daily|live agent|grows continuously' README* DATACARD.md llms.txt CITATION.cff NOTICE .zenodo.json` が状態語つきの行以外 0 件、`takedown-requests.jsonl` の未判断行 0 件
- 規模・整合: M / neutral   出典: DE-35, RF-51, R3-END Fix-04

##### P4-02.3 Moltbook アカウントの処遇を 3 択で記録する
- 何を: runbook に 3 択（放置して識別子を凍結 / 人間名義で「終了」を 1 投稿 / platform に削除依頼）と、選んだ場合の README・data README の live 表記の書き換え（状態語を付ける）を置く。削除 API の有無は停止時点で人間の再読台帳（P1-07.19、`docs/evidence/moltbook-platform-readings.md`）に 1 行足し、その行（日付・digest）を runbook が引く（`skill.md` を各自で確認する手順は書かない）。推奨は D-P4-02-1。
- 根拠: `grep -rn -i "deregister\|unregister\|delete-account" src docs` 0 件、data repo `reports/analysis/.api-drift-state.tsv:1-3` の DELETE は `/agents/{name}/follow` のみ（drift state は client が呼んだ endpoint の応答 key しか持たない — `scripts/api_drift_scan.py:140-162` — ので「client に呼び手が無い」の証拠であって、平台側に endpoint が無いことの証拠ではない）/ 本体 `README.md:54`・`README.ja.md:54`・data repo `README.md:52`「Live agent on Moltbook」（DATACARD には無し）/ `docs/CONFIGURATION.md:27` `register --name NAME`
- 完了条件: 選択が runbook に記録され、README 3 箇所の live 表記テンプレに状態語がある; 削除 API の有無の確認が P1-07.19 の台帳行（日付・digest）を引く
- 規模・整合: S / neutral   出典: DE-36   依存: P1-07.19

##### P4-02.4 本体 repo の「終了状態」の表し方を決める
- 何を: runbook に「最終リリース（CHANGELOG に Ending 節）→ README Status 行を『ran 2026-03-07..YYYY-MM-DD』の期間表記（EN / JA）→ `CITATION.cff` version / `.zenodo.json` → `graph.jsonld` に repo 状態ノード → `llms.txt` / `llms-full.txt` 再生成 → GitHub archive」の順と文言テンプレを書く。テンプレに .8 の「終了後の受付は alias のみ、判断は best-effort」1 文。repo 外の面 1 行（profile repo `shimo4228/shimo4228`、dev.to / Zenn 記事、HF の 2 card）。
- 根拠: `README.md:133`「Status: one live instance since 2026-03-07; release v2.12.0 (as of 2026-10-08)」、`README.ja.md:36`（同旨）/ `CITATION.cff:28` `version: "2.12.0"`、`.zenodo.json`・`graph.jsonld`（`status: accepted` は ADR ノードのみ、repo 状態ノード無し）・`llms.txt` が存在 / 終了後の表記規約・archive 設定の記述なし / repo 外の面: 本体 `.zenodo.json:153,165` と data `.zenodo.json:4-5`（`isPartOf`）が profile repo `shimo4228/shimo4228` を指す、本体 `README.md:110-112`（dev.to / Zenn 記事）
- 完了条件: runbook に手順と文言テンプレ（EN / JA）と repo 外の面の行があり、手順 (4) に確認コマンド 1 行（`grep -E 'ran 2026-03-07\.\.[0-9]{4}-[0-9]{2}-[0-9]{2}' README.md README.ja.md` が 2 件）
- 規模・整合: S / neutral   出典: DE-37, R3-END P-1 / Fix-04

##### P4-02.5 兄弟 repo の GitHub archive の操作と条件を runbook に 1 行ずつ
- 何を: P1-11 の決定（D-P1-11-1〜3、rules は D-P1-11-6）を前提に、runbook に -otel / -cloud / -mlx / -rules の「GitHub archive の操作と条件」を 1 行ずつ書く（README の状態行 `Frozen as of contemplative-agent vX.Y.Z` = `last conformant` は同じ行で P1-11.1 が正本 — ここでは書かない）。rules は本体が `amend-constitution` を retire する（本束の手順 (4) の後）か bench を本体に vendoring する（D-P1-11-6 B）まで archive しない — `ipd-two-arm.sh` が rules の bench を既定で呼び、憲法改正の承認に bench は required なので、先に archive すると終了手順の最後の改正に計器が無い。archive 時も条項文は verbatim のまま（rules ADR-0002）、README には『稼働インスタンスの憲法は改正済み（data repo）』の 1 行（P1-11.11 a）だけ。
- 根拠: 兄弟の最終 commit 2026-08-16/17、-rules 2026-07-07（BRIEF §1）/ `scripts/ipd-two-arm.sh:36,44`（`BENCH_DIR` 既定 = `../contemplative-agent-rules/benchmarks/prisoners-dilemma`、`IPD_BIN` はその `.venv`）/ `docs/runbooks/constitution-amendment.md:3-5`（IPD two-arm bench は required）/ `docs/runbooks/sibling-backend-conformance.md` はリリース前ゲートのみ / `CLAUDE.md:164-167` は役割のみ
- 完了条件: runbook に 4 行（操作と条件。rules の条件文を含む）; 各兄弟 README の状態行は P1-11.1 の完了条件
- 規模・整合: S / neutral   出典: DE-38（README 1 行は P1-11.1 に吸収 — R1-SIB Merge-02 / Fix-01）

##### P4-02.6 鍵・資格情報の失効表を wind-down runbook に置く
- 何を: `docs/runbooks/wind-down.md` に表を 1 つ: 行 = P1-10.9 の 7 所在 + Zenodo–GitHub 連携 + HF の書込 scope、列 = 処置（失効 / scope 縮小 / 保持）× 時点（手順番号）× 理由 × 確認方法。既定: Moltbook 鍵は手順 (6) で消すのはディスク上の平文（`credentials.json`・`MOLTBOOK_API_KEY` env）だけ。パスワードマネージャの封印コピーは .8 の alias 存続期限まで残し、その日に破棄して日付を記録（再発行できない platform で鍵を破棄すると D-P4-02-1 の B / C と platform 上で takedown に応じる手段を永久に失う一方向の操作なので、破棄を受付期限に合わせる）/ `cloud.env` と typesafe の鍵は (2) の後に失効 / HF token と GitHub の push 資格は .8 の受付期限まで保持（CA 専用でなければ CA の repo への scope を外す）/ Zenodo 連携は最終 deposit の後に repo の toggle を off（D-P3-05-1 (b) が B / C なら P0-06.6 の段 8 で off 済み — 確認だけ）。P1-10.9 の runbook からこの表へリンク。
- 根拠: 手順 (1)〜(7) と .2 / .3 に鍵の失効・破棄が無く、P1-10.9 の 7 所在は回転と漏洩時の手順で終了時の扱いが無い / `adapters/moltbook/auth.py:29-32`（env > file）、`:54-68`（0600 の平文）、cloud 兄弟 `src/contemplative_agent_cloud/cli.py:40-55`（`$MOLTBOOK_HOME/cloud.env` を読む）、`scripts/sync-research-data.sh:140-150`（`hf upload`）/ `docs/runbooks/runtime-backup-restore.md:70-72`（restore には鍵の再発行が要る）
- 完了条件: 表が runbook にあり 9 行それぞれに処置・時点・理由・確認方法（例: `test ! -e "$MOLTBOOK_HOME/credentials.json"`、GitHub Settings の Applications で連携先を目視し日付を記録）; HF / GitHub 資格の保持期限とパスワードマネージャの Moltbook 鍵の封印コピーの破棄日が .8 の alias 存続期限と同じ日付; `docs/runbooks/credential-rotation.md`（P1-10.9）にこの表へのリンク 1 行
- 規模・整合: S / neutral   出典: R3-END-01, R4-ONEWAY Fix-10   依存: P1-10.9、D-P4-02-1。順序: .1 / .8 と同 PR（`wind-down.md`）

##### P4-02.7 repo 外の定期処理（harness の tick・claims・graph mirror）を停止手順に入れる
- 何を: 手順 (2) に「repo 外の定期処理」小節を 3 行と各確認コマンドで置く: harness の `triage-ca` 登録の解除（確認: tick 一覧に CA が無く、次の tick 時刻を過ぎて `git log --since` と `rfcs/` の mtime に変化が無い）/ claims.py の CA タスクの close または移管（`python3 ~/.claude/scripts/claims.py ready` に CA の行が 0）/ graph mirror の同期対象から CA を外す（harness skill `jsonld-knowledge-graph` の Mirror Sync 節）。P2-04.3 の完全停止節からこの 3 行へ 1 行リンク。harness 側の実体は repo 内の記述からの推定（未確認）。
- 根拠: `docs/adr/0098-weekly-single-session-and-triage-delegation.md:75`（`triage-ca`: Wed 17:07 / Sat 14:07、worktree dispatch）、`scripts/weekly-pipeline.sh:11-13`（Sat 14:07 tick が `rfcs/` を判断し dispatch）/ `CLAUDE.md:151-159`（claims.py は `~/.claude`）、`:171`（HF graph mirror は harness skill で同期）/ `src/contemplative_agent/cli/schedule.py:447-457`（uninstall の範囲は管理下の `com.moltbook.*` plist だけ）
- 完了条件: runbook の手順 (2) に 3 行と確認コマンドがあり、dry-run で 3 つを列挙できた記録がある; P2-04.3 の完全停止節にこの小節へのリンク 1 行
- 規模・整合: S / repair   出典: R3-END-02（R3-HRN Fix-07 の P4-02.1 (2) 側）   依存: P2-04.3。順序: .1 と同 PR（`wind-down.md`）

##### P4-02.8 終了後（GitHub archive 後）の takedown 経路と私的記録の保持期間を決める
- 何を: runbook に「終了後」節: メール alias の存続期限（例: 最終版から N 年）と、終了状態の文言（.4 のテンプレ）に「終了後の受付はこの alias のみ、判断は best-effort」1 文 / 実行手順（GitHub: unarchive → 除去 commit → 再 archive、HF: 直接削除、Zenodo: P3-05.14 の到達範囲表の行に従う）/ 台帳 `takedown-requests.jsonl` は手順 (7) で私的 backup repo へ移送 / 私的 backup の保持期間と満了時の処置（repo 削除）。削除は人間の決定（`gate_item`）で行い本体 CHANGELOG の Ending 節に日付を残す。決める前に P3-01.1 の `reanalysis:` 列（private-rows | rerun-local）の読みについて、論文 cutoff 後に再検証の依頼が来うる期間を 1 行で確認する（私的 backup は生の episode の唯一の off-machine コピーで、削除すると private-rows の再解析は永久にできない）。.6 の HF / GitHub 資格の保持期間をこの期限に合わせる。
- 根拠: P3-05.14 の受付（窓口はメール alias か GitHub Security advisory、台帳は `MOLTBOOK_HOME/takedown-requests.jsonl`）と P3-05.19（抑止リストは `sync-research-data.sh` 経由で適用 — 手順 (2) で sync が止まると動かない）/ `docs/runbooks/runtime-backup-restore.md:1-7`（私的 backup は episode log の唯一の off-machine コピー）、手順 (7) に保持期間が無い / archive 後に advisory を受けられるかは外部知識・未検証
- 完了条件: 節が存在し、alias の期限・3 面の実行手順・台帳の移送先・backup の保持期間と満了時の処置（削除は `gate_item` の決定、Ending 節に日付、決定前の `reanalysis:` 列の確認 1 行）がそれぞれ 1 行; .6 の資格保持期限と同じ日付
- 規模・整合: S / neutral   出典: R3-END-03, R4-ONEWAY Fix-11   依存: P3-05.14 / .19、D-P3-05-2（11-21）、P3-01.1。順序: .1 / .6 と同 PR（`wind-down.md`）


**依存**
- P4-01（when / how 分離の追補（2026-12）が先 — runbook は how）
- P2-04.1 / .3（sync-data の管理下化、完全停止手順 = 手順 (2)）/ P2-04.2（sync 失敗の非 0）
- P0-03（DE-01 `.bak`、絶対パス）/ P3-05（DATACARD・schema・DOI 版・HF、RF-34; P3-05.14 の撤回到達範囲表は SWH 保存要求の前）/ P3-02（regime 表）
- P1-07.19（.3 の削除 API の有無を引く再読台帳）
- P1-10.9（鍵の 7 所在 — .6 の表の行）/ P3-05.14 / .19、D-P3-05-2（.8 の終了後の takedown 経路）/ P3-01.1（`reanalysis:` 列 — .8 の backup 削除の決定前の確認）/ P0-06.6 の段 8、D-P3-05-1 (b)（手順 (3) の deposit の形）
- P1-11（兄弟 repo の処遇決定: D-P1-11-1〜3、D-P1-11-6（rules）、P1-11.1（状態行の正本）、P1-11.11 a）/ P2-03（`release-doi` skill は repo 外 — runbook から手順実体をリンク）
- 外部: Zenodo 版 DOI、Software Heritage 保存要求、HF dataset card、GitHub archive フラグ
- → 参照元: P4-03（継続者が runbook を実行できる形 — P4-03.1 が archive 手順を引く）、P3-04.8 / P2-05.8（最終 sync で系列・INDEX を固定）、P2-04.3（完全停止節から .7 へ 1 行リンク）、P1-10.9（credential-rotation runbook から .6 へリンク）、P3-06.7（書き戻し表の AKC 行 = P4-02 終了時の dated note — 手順 (5) が参照）、P2-01.12（ロードマップ文書の退役条件 = P4-02 の最終 sync）


#### P4-03 継続性（bus factor 1）・引継ぎ・インシデント手順
- 狙い: 単一 Mac・個人アカウント（GitHub / HF / Zenodo / ORCID）・個人 git 資格情報で、「終わらせる作業」自体がオーナーにしかできない。最終成果物（Zenodo 版）は不変なので、継続者向けの最小指示・責任者交代のチェックリスト・インシデント手順の 3 本を runbook に置き、AAP ADR-0008 の「責任者の交代は記録付き」と ADR-0006 の「事後に原因を辿れる」を本体 repo だけで満たす。
- 期限・順序: 着手 2027-03-13 の土曜ゲート（§4.0。P4-02 の runbook dry-run 2027-03-06 の翌週）。期限 2027-Q1。P4-02 runbook（archive 手順）と P1-12（`approver` 欄・GOVERNANCE.md）の後。.2 の技術手順（launchd 再 install・credentials 再発行・backup repo 権限）は P2-04.23 の machine-rebuild runbook を引くだけなので、その後。incident-response は P1-12 の GO-12（版の特定）に依存し、data repo での扱いは撤回ポリシー D-P3-05-2（11-21）の結論と P3-05.14 の到達範囲表（NOTICE 側は 11-21）を引き、`incident-response.md` への写しは .3 の完了条件が持つ。決定は D-P4-03-1（2027-02-06 の土曜ゲート。.2 の範囲はこの決定に従う）。旧 D-P4-03-2 は削除し D-P3-05-2 に統合。
- 束の完了条件:
  - `docs/runbooks/continuity.md`、`operator-handoff.md`、`incident-response.md` が存在し `docs/runbooks/README.md` の表に 3 行
  - `incident-response.md` の RCA テンプレの見出しが AAP ADR-0006:43-51 の 5 問と 1:1 で対応
  - 継承者の有無（「決めない」を含む）が `continuity.md` に日付つきで記録
  - handoff チェックリストに、運用そのものを渡す場合（D-P4-03-1 C の移管、または将来の運用継承）は audit 行 `approver` の切替（P1-12 導入後）と「引継ぎ自体を audit 行に残す」規約があり、D-P4-03-1 B（推奨）なら archive 権限の付与と audit 1 行だけがある

##### P4-03.1 継続者向けの最小指示（`docs/runbooks/continuity.md`、1 ページ）
- 何を: 必要アカウント一覧（GitHub / HF / Zenodo / ORCID / Moltbook、名義のみ）、private backup の所在と権限、「オーナー不在時に第三者がすべきこと = 何もしない（Zenodo 版は不変、公開ミラーは最後の sync で止まる）/ できれば GitHub archive のみ」、GitHub の successor 設定の有無。継承者を 1 名決めるか「決めない」と記録（D-P4-03-1）。P4-01.5 の operator unavailability 節へリンク。
- 根拠: `CLAUDE.md:38`「実行機（開発・本番・実験がすべてこの 1 台）」/ `grep -rn -i "bus factor\|successor\|owner absence\|引継\|succession" docs CLAUDE.md README.md rfcs` 該当 0（`handoff` は別義のみ）/ `docs/runbooks/runtime-backup-restore.md:62`（backup は `shimo4228/contemplative-agent-runtime-backup` 個人名義）、data repo `DATACARD.md:7`（Curator = 個人 + ORCID）
- 完了条件: 1 ページが存在、継承者の決定（または「決めない」）が日付つきで 1 行、`docs/runbooks/README.md` に行
- 規模・整合: S / neutral   出典: DE-44

##### P4-03.2 責任者交代のチェックリスト（`docs/runbooks/operator-handoff.md`）
- 何を: 全項目を使うのは運用そのものを渡すとき（D-P4-03-1 C の移管、または将来の運用継承）だけ。D-P4-03-1 B（推奨）なら「archive 権限の付与と、その記録を audit に 1 行」だけ、A なら実行する場面が無い（runbook は置く）。責任の移転に固有の行だけを持つ: audit 行 `approver` の切替（正本は GOVERNANCE.md の「Accountable operator」行 — P1-12.7、env は override のみ — なので交代 = その行の更新 + 出入り両者の監査行）、data repo NOTICE の curator 欄、CITATION の authors、AAP ADR-0008 Open question 5 への脚注（CA の経験的回答）。「引継ぎ自体を audit 行に残す」規約を P1-12 の `approver` 導入と合わせる。技術手順（credentials の再発行、backup repo の権限、launchd の再インストール）は `docs/runbooks/machine-rebuild.md`（P2-04.23）を引く 1 行だけ。
- 根拠: AAP `docs/adr/0008-one-agent-one-human.md:52-54`「Changing the accountable operator is itself a behavior-modifying change and requires approval from both the outgoing and incoming operator」、`:122` Open question 5「Revocation and departure」/ `src/contemplative_agent/cli/adopt.py` に `approver` 欄無し（grep 0）/ 技術手順の根拠（`docs/CONFIGURATION.md:27` `register --name`、`:433` ollama-restart の手動 `launchctl` 管理）は P2-04.23 側
- 完了条件: runbook が存在し、チェックリストの各行に確認コマンド、冒頭に D-P4-03-1 の選択ごとの適用範囲（B なら archive 権限の付与と audit 1 行だけ）、AAP 0008 への脚注 1 本（AAP repo 側の書き戻しは P3-06）; 技術手順は `docs/runbooks/machine-rebuild.md`（P2-04.23）への参照 1 行（ここでは書かない）
- 規模・整合: S / neutral（runbook）   出典: GO-25, R3-END Fix-06, R3-OSX Merge-01   依存: P2-04.23

##### P4-03.3 インシデント手順（`docs/runbooks/incident-response.md`）
- 何を: 検知面（watchdog / approval join / comment-outcomes、P2-04）→ 即時停止（P2-04.3 の完全停止 + Moltbook 側は投稿停止のみ、削除はしない）→ 版の特定（P1-12 GO-12: snapshot manifest と audit で identity / constitution / skills の版を引く）→ RCA テンプレ（AAP ADR-0006 の 5 問を見出しに。Q4「どの外部面に触れたか」の証拠は `MOLTBOOK_HOME/logs/api-audit.jsonl`（request / response の構造欄のみ）を名指し — AAP 0006 required artifacts の「Adapter call log」行の記入例。GOVERNANCE.md の記録所在表は P1-12.7）→ data repo での扱い: 事案時の該当行は撤回ポリシー（D-P3-05-2）に従う。owner-authored の CC0 許諾は撤回しないが第三者本文の除去・置換は可能面（GitHub tree / HF / 次版）で行い、不変面は P3-05.14 の表（撤回の到達範囲表 = 面 × 操作 × 残る痕跡 × 確認日。NOTICE 側の表は 11-21 に置かれ、本 runbook にはこの項目で写す）で告知する。受付の窓口と台帳は P3-05.14 → 公表（CHANGELOG / rfcs）。`rca/` の様式を 1 件の先例から規約化。
- 根拠: `docs/runbooks/README.md:9`（`rca/` = Post-mortem、実体は `rca/2026-04-14-reflective-note.md` 1 件）/ 停止手順は `docs/CONFIGURATION.md:62, 404` に散在、`SECURITY.md` 不在、`docs/security/` は 2026-04-01 の 2 本 / AAP `docs/adr/0006-causal-traceability.md:43-51`（5 問: inputs / active version / approvals / external surface / output）、`:53-61`（required artifacts: Adapter call log）、`:96-97`「has a procedure, not a speculation」、AAP `0008:48-51`「Owns incident response」/ `src/contemplative_agent/adapters/moltbook/client.py:45`（`API_AUDIT_PATH = … / logs / api-audit.jsonl` — 草案では error 規則の修理にしか出てこない）
- 完了条件: runbook が存在し RCA テンプレの H2 が AAP 0006 の 5 問と 1:1、Q4 の証拠欄が `api-audit.jsonl` を名指す、`docs/runbooks/README.md` の `rca/` 行から様式へリンク; NOTICE 側の撤回の到達範囲表（P3-05.14）が runbook に写されて各行に確認日があり、NOTICE の表と行が一致する（外部サービスの規約は外部知識・未検証と明記）
- 規模・整合: S / neutral（runbook）   出典: GO-24, R4-XREF Fix-06   依存: D-P3-05-2（11-21）、P3-05.14（11-21）


**依存**
- P1-12（GO-01 `approver` 欄、GO-12 版の特定、`docs/GOVERNANCE.md`）
- P1-10（SECURITY.md・鍵の棚卸し・回転手順）/ P2-04.19（credentials の保管先 1 行）/ P2-04.3（完全停止 — .3 の即時停止）/ P2-04.23（machine-rebuild runbook — .2 の技術手順の実体）
- P4-01.5（operator unavailability 節）/ P4-02（archive 手順、鍵の失効表 P4-02.6）/ P2-05.4（版の特定の材料 = comment-report の `values_digest`）
- D-P3-05-2（撤回ポリシー、11-21）/ P3-05.14（takedown 節: 撤回の到達範囲表と受付窓口・台帳、11-21。表の `incident-response.md` への写しは .3 の完了条件）
- AAP ADR-0006 / ADR-0008（外部 repo、read-only）
- → 参照元: P3-06（AAP への書き戻し — .2 の Open question 5 の脚注を引く）


## 4. オーナーの決定が必要な事項

各束から上がった「決めないと先に進まない」問い。4.0 は期限（土曜ゲート）順の一覧と配分規約・記録規則、4.1 は束ごとの全文（選択肢・推奨・期限）。推奨は本レビューの判断であり、決定はオーナーの行為として土曜ゲートの記録（`gate_item`）に残すことを前提にしている（P1-12）。

### 4.0 決定の優先順位表（期限順）

決定は全部で 99 件ある。1 人で土曜ごとに裁くには多いので、2 種類に分けた。**熟慮**（40 件）は一方向の扉か、価値層・ゲート・北極星の読み値・研究の方向に触れるもので、オーナー自身の判断が要る。**既定可**（59 件）は可逆または機械的で、熟慮の時間を要しない。ただし既定可でも推奨は材料であって裁定ではなく、`decision` はオーナーが打つ（下の記録規則）。期限は「遅れると何が起きるか」が各束の本文にある。番号で第 4 章の各束の節（本文）に飛べる。

**土曜ゲートへの配分規約**（R1 オーナー視点・R2 ゲート運用視点・R3 時間視点の指摘）: 1 ゲート = 決定 ≤ 5 件、うち熟慮 ≤ 3 件、当週に着手する作業束 ≤ 2。「束」は決定の出所ではなく、その週に手を入れる作業束で、37 束を下の表のどこかで少なくとも 1 回名指す（P1-01 と P1-14 は他の束の PR に同乗するので着手週を持たない）。束の着手週より前に入る項目（「今すぐ」「v2.13.0 前」「11-01 まで」）は「先行項目」の列に週ごとに名指し、列に無い項目は当週に入れない。「X の週」は土曜 X の前の月〜金で、X のゲートで使うものはその金曜までに main へ入れる。「着手 X」は X のゲートで方針を確かめ、X の後の平日に PR を入れる（X のゲートの決定を要する部分は X の後の週に回す）。決定 ≤ 5 は 12:00（無人チェーンの期待終了）〜14:07（triage tick）の窓の代理で、Ollama を使う読み（shadow / IPD / null pair）は平日の guard 窓で前日までに取る（P2-01.11）。10-10 の 3 件は本文書の作成日当日なので遡及記録とし、10-17 に `decided_at=2026-10-10` で打つ（遡及分は上限 5 に数えない。この例外は 10-10 だけで、他の遅れは P2-01.14 の繰り越し規則に従う）。11-28 の熟慮 5 件は追補（2026-11）の 1 PR に結ぶ例外で、11-28 の週（11-23〜27）に 4.1 の本文と材料の所在を 1 枚にまとめておく（P2-01.10）。下の「ゲートごとの件数」表は決定数 > 5・熟慮 > 3・着手束 > 2 の行に ⚠ を付け、表自身が検査になる。この規約を守ると Phase 1 の束は 10〜12 月に収まらず、着手は 2027-01 まで、決定は 2027-03-06 まで並ぶ。2027-03-13 / 03-20 / 03-27 の 3 回は空けてあり、欠席や遅れの繰り越し先にする（規則は P2-01.14）。

**記録規則**（R1 北極星視点・R2 ゲート運用視点の指摘）: 決定 1 件 = `gate_item` 1 行（様式と Step 1c は P2-01.10。この表は `docs/plans/roadmap-2026-10/decisions.md` として repo に置く）。`category=roadmap`、`item=<D-ID>`、`recommendation=<本文の推奨>`、`decision=<採った選択肢>`、`recommender=<推奨を書いたモデル名>`。`recommender` は 10-17 から暫定 field として打つ（D-P2-01-2 は監査の形を決めるだけ）。同じく、ロードマップ項目の実装 commit には 10-10 の作業から暫定で trailer `Roadmap: <項目 ID>` を付け、D-P2-01-5（10-31）が A / C なら以後止める（付いた trailer は残す）。`approver` は D-P1-12-2（2027-01-09）まで無く、それまでの roadmap 行は Claude Code の転記であることをこの規則自身に記す。熟慮は `reason` 必須。既定可でも `decision` は人間が打ち、`pipeline-metrics.jsonl` に残る。これで推奨↔裁定一致率の監査（P2-01.1、D-P2-01-2）はロードマップ決定を母集団に含められる。追補と新 ADR の境界は D-P1-03-1（2027-01-09）が決めるが、それまでは推奨 A の 3 条件（反転・他 ADR の前提変更・本番挙動の変更は新 ADR か partial supersede）を暫定基準としてこの規則に置く（P1-03.11）。

| 期限 | ID | 問い | 推奨（要約） | 種別 | 材料 |
|---|---|---|---|---|---|
| 10-10 の土曜ゲート | D-P0-01-1 | 選ぶ — insight 週次の入口の運用（継続 / 入口停止 / 月次） | A — 10-10 の 1 回の読みで入口停止を決めるのは one-run-not-evidence に反し、週次の費用は naming … | 熟慮 | 各束の本文 |
| 10-10 の土曜ゲート | D-P0-01-3 | 終端する — RFC-0023 の希少レーンを withdraw するか | A — 供給増の機構は RFC-0048 の「絞る」方向と同時に走らせると読めない（RFC-0023 の 2026-09-07 著者判断そ… | 既定可 | 各束の本文 |
| 10-10 の土曜ゲート | D-P0-03-2 | `_gc_trash/` の退役 skill 原本 10 件を公開に残すか | A — 同種の artifact の公開可否が時期で割れる状態を解消する方が研究再利用者に説明しやすい | 既定可 | 各束の本文 |
| 10-17 の土曜ゲート | D-P0-01-2 | 決める — staged 台帳の却下分を「既知」に含め続けるか | .7 の内訳を 1 回読むまでは A — RFC-0042 の読みの最中に判定者の入力を変えると絞りの効果と分離できない。内訳で ledg… | 熟慮 | `insight-launchd.log` の Summary 行と `insight-stages.jsonl` の `covered_by`（P0-01.7） |
| 10-17 の土曜ゲート | D-P0-02-1 | 決める — 10-17 の Step 1c の照合（材料は 10-15 のログ）が不成立のとき v2.13.0 をどう… | A — RFC-0046 が「移行 → 確認 → 削除 → DOI release」の順を明記し、残置版を DOI で固定すると引用される… | 既定可 | `rfcs/0046:255` の照合コマンドと `submolt-scope-2026-10-14.jsonl` の `scale` |
| 10-17 の土曜ゲート | D-P0-02-2 | 選ぶ — ADR-0112 の退役部分の記録方法 | A — 追補による実質 supersession は `test_adr_status_consistency` の検査外（P1-03 の… | 既定可 | P0-02.8 |
| 10-17 の土曜ゲート | D-P1-04-1 | submolt-scope sweep を常設のまま残すか撤去するか | A — RFC-0011 の読みは済み、順位比較は 10-09 の尺度変更で断絶、購読集合の見直しは四半期で足りる | 既定可 | P1-04.3 と ADR-0086 |
| 10-17 の土曜ゲート | D-P3-04-2 | snapshot の保持方針を決める | A（C は「bit-for-bit」の約束を後退させ、B は data repo を肥大させる） | 既定可 | P3-04.1 の prune 順の表（27 番目 = `amend-constitution_20260809…`） |
| 10-24 の土曜ゲート | D-P1-02-1 | RFC-0040 を withdraw するか blocked のまま置くか | A — 欠陥（47% 過剰通過）は RFC-0046 で修理済み、残部は「将来像」= ADR-0080 の審査で能力動機側、消費者の無い較… | 既定可 | P1-02.5 |
| 10-24 の土曜ゲート | D-P1-04-2 | comment-outcomes の 2 窓判定で stage 7d を撤去するか帰属 RFC を起票するか | 読みで決める（熟慮: 帰属 RFC は値層への経路に触るので推奨は材料にとどめ、decision は人間が `gate_record` に… | 熟慮 | `docs/evidence/adr-0106/` の 2 窓（P1-04.5 のコマンド） |
| 10-24 の土曜ゲート | D-P1-04-4 | ADR-0105 stage 7c の撤去時計を 1 年から短縮するか | A（C は .4 の fan-in 0 と合わせて T4 で検討） | 既定可 | `pipeline/confusion-pairs/` の 4 週 |
| 10-24 の土曜ゲート | D-P1-05-1 | 滞留する baseline_proposal 4 件をどう裁定するか | B（熟慮: 較正の変更は人間ゲートを通す設計（`observation_ledger.py:60-63`、RFC-0010 Q5/Q8）で… | 熟慮 | `observation_ledger.py render` の proposal 4 行 |
| 10-24 の土曜ゲート | D-P3-04-1 | 版履歴の置き場を決め ADR-0030 と整合させる | C。ADR-0030 の撤回理由は identity.md 内の sub-addressing で、ディレクトリ単位の 1 責務は保てる。… | 熟慮 | P3-04.2 / .3 の置き場の比較（本体側の書き手コードは決定前に書ける） |
| 10-31 の土曜ゲート | D-P0-07-1 | 決める — 10-31 の due で改正を起動するか、読みだけ取って見送るか | B を既定、A は .2 の事前登録と .1 の系列が 10-31 までに揃った場合のみ — due は生成の cadence で改正の義… | 熟慮 | 各束の本文 |
| 10-31 の土曜ゲート | D-P0-07-2 | 選ぶ — shadow を weekly chain に月次配線するか | 10-31 のデータで決める。それまでは A — ADR-0092 の「配線は読みが有用と分かってから」に従い、.1 の 2 run が … | 既定可 | 各束の本文 |
| 10-31 の土曜ゲート | D-P1-11-1 | cloud repo を維持・凍結・削除のどれにするか | B — 唯一の実験記録は 2026-04-21（main 2.0.0、n=1、$3–5）で以後 `docs/evidence/` に言及 … | 熟慮 | P1-11.2 / .3 と kit の結果 |
| 10-31 の土曜ゲート | D-P1-12-1 | `adopt-staged --yes` を AAP 0005 とどう整合させるか | A（最小変更で記録に人間の言葉が入り、憲法 runbook Step 4 もそのまま） | 熟慮 | 各束の本文 |
| 10-31 の土曜ゲート | D-P2-01-5 | ロードマップ項目の実装 commit を何で項目に結ぶか | B（既定可: 台帳の件数を増やさず、`freeze_reading.py` が `Roadmap:` trailer で別系列に出せ、P1… | 既定可 | 各束の本文 |
| 11-07 の土曜ゲート | D-P0-05-1 | Ollama / 生成モデル不在で session を止めるか | A — Ollama 無しでできる仕事が無く、6 時間の無行動は翌週の人間の読み（ADR-0113 Review-when）に負荷を移すだ… | 既定可 | 各束の本文 |
| 11-07 の土曜ゲート | D-P0-05-2 | `init` が複製する `prompts/` を既定 home でも読むか | B — 本番 100 snapshot が `prompts_dir: null`、ADR-0003 / 0054 の語彙とも合う。B 前… | 既定可 | 各束の本文 |
| 11-07 の土曜ゲート | D-P0-06-1 | Python 床を 3.11 に上げるか、3.10 を shim で守るか | A — 3.10 は 2026-10 に EOL（PEP 619）、実行機は macOS M1 で 3.13、shim は「床より新しい … | 熟慮 | 各束の本文 |
| 11-07 の土曜ゲート | D-P0-06-2 | 配布単位を clone + editable 限定にするか、自己完結 wheel にするか | A — 最小で保守面を増やさない。ADR-0088 の「wheel で kit を届ける」は kit が core のみ依存（import… | 熟慮 | 各束の本文 |
| 11-07 の土曜ゲート | D-P0-06-3 | 2.x の minor で Protocol・設定面（env / domain key / prompt / CLI … | A — v2.13.0 は `DECISION_*` / `thresholds.relevance` / `relevance.md` … | 既定可 | 各束の本文 |
| 11-14 の土曜ゲート | D-P1-08-1 | `uv.lock` を追跡して `--locked` にするか、床 + constraint の現状を ADR で正式… | B（本番機は 1 台で lock はローカルにあり、CI の fresh 解決は「ツール更新で壊れる」の早期警報として働いている。研究の固… | 既定可 | 各束の本文 |
| 11-14 の土曜ゲート | D-P1-11-2 | mlx repo を凍結するか gemma で再計測するか | A — mlx は「同じエージェント」を動かせない（gemma で蒸留した値層を Qwen が読む別インスタンス、.2 a）ので観察対象と… | 熟慮 | 各束の本文 |
| 11-14 の土曜ゲート | D-P1-11-5 | 契約キットの runtime 段を出荷するか static で凍結するか | B — D-P1-11-1 / -2 で兄弟を凍結するなら runtime 検査の読み手が無い（ADR-0101）。`--decision… | 既定可 | 各束の本文 |
| 11-14 の土曜ゲート | D-P3-05-1 | データセットの版を (a) いつ切り (b) 不変の DOI 版に何を入れるか | (a) B — 論文が引く版がコード版と 1 対 1 になり release runbook に載る（論文 cutoff への適用は P3… | 熟慮 | 各束の本文 |
| 11-14 の土曜ゲート | D-P3-05-5 | graph.jsonld の HF ライセンス（CC BY 4.0）を repo / Zenodo の MIT に揃え… | A。同一バイト列に 1 条件 | 既定可 | 各束の本文 |
| 11-21 の土曜ゲート | D-P0-03-1 | 公開履歴から embedding 入り bak と `/Users/` を書き換えて消すか | A — 公開 DOI v1.0.0（`CITATION.cff` 2026-06-17）は `.zenodo.json` の記述どおり e… | 熟慮 | 各束の本文 |
| 11-21 の土曜ゲート | D-P0-03-3 | 決める — 公開 projection で第三者由来の逐語 span を伏せ字にするか | .9 の開示と carve-out 注記（REP-06 の A + C）を 10-24 に先に入れ、B 以降はオーナー判断（熟慮: 公開面… | 熟慮 | 各束の本文 |
| 11-21 の土曜ゲート | D-P0-04-1 | 決める — 未蒸留の 06:00 JST episode（2026-03〜）を backfill するか | B — backfill は装置境界（モデル・プロンプトの変更、P3-02）をまたぐ再蒸留で時系列の意味が変わる（熟慮: 公開 knowl… | 熟慮 | 各束の本文 |
| 11-21 の土曜ゲート | D-P0-04-2 | 選ぶ — knowledge.json の保存前バックアップ | A — 正本が 1 つで週 1 backup だと最大 6 日分の蒸留を失う、sync 除外も既にある | 既定可 | 各束の本文 |
| 11-21 の土曜ゲート | D-P3-05-2 | 公開済みの第三者由来テキストの再掲根拠・撤回の受付と実行（面 × 対象 × 手段）をどう置くか（撤回ポリシーの正本。旧… | A + E（A の手順の実行経路として E。規約が明示的に許さない場合は (ii) の法定例外を根拠に Context を要約 + id … | 既定可 | 各束の本文 |
| 11-28 の土曜ゲート | D-P1-01-1 | 凍結の閾値と窓をどこに置き、何週とするか | A（熟慮: 北極星の読み値に触る決定。閾値と窓は ADR-0080 の追補（2026-11）の定義にではなく dated note の「読… | 熟慮 | 各束の本文 |
| 11-28 の土曜ゲート | D-P2-01-1 | 「負荷」を何で測るかを ADR-0080 の dated note に書くか | B — A では完成判定が反転する（裁定 0〜2 件なのに毎週 repo を変更している） | 熟慮 | 各束の本文 |
| 11-28 の土曜ゲート | D-P2-01-3 | 「代謝が止まっていない」下限をどこに置くか | B（熟慮: 代謝の下限は層 2 の読みに触れる） — A / C は「止まった」と「自己調節」を区別できない | 熟慮 | 各束の本文 |
| 11-28 の土曜ゲート | D-P2-02-1 | headless `claude -p` を機構層と見なすか作業環境と見なすか | A を暫定（現に 7 週回っており、B は土曜の読み量を増やし P2-06 と逆行）、ただし .1 の二分で「無人の読み手は負荷系列に数え… | 熟慮 | 各束の本文 |
| 11-28 の土曜ゲート | D-P2-05-3 | 「人間の言葉として残す接点」を固定するか | A（RFC-0048 層 1 のような移行のたびに「これは人間の仕事か」を再議論しなくて済む。別番号の追補は振らない） | 熟慮 | 各束の本文 |
| 12-05 の土曜ゲート | D-P1-11-4 | 推論プロバイダへの本文 egress を ADR-0015 の「外部に観測可能な副作用」に数えるか | A — 凍結でも追補 1 行で済み、absence の例外が「人間が毎回明示する」形で機械に見える。P1-10 の threat-mode… | 既定可 | 各束の本文 |
| 12-05 の土曜ゲート | D-P1-15-1 | t=0.3 を維持するか新母集団で再導出するか | C — 規則は妥当で変わったのは母集団。再適用の結果が A なら A（熟慮: 本番 gate の閾値に触れるので推奨は材料、decisio… | 熟慮 | 各束の本文 |
| 12-05 の土曜ゲート | D-P1-15-2 | 真値の既定を Jev にするか opus にするか | A（熟慮・前提変更: 閉じたホスト API を本番 gate の閾値 t を決める読みの既定の真値にする — ゼロ API の例外は研究ラ… | 熟慮 | 各束の本文 |
| 12-05 の土曜ゲート | D-P2-07-1 | 層 1（決定論 archive）を「決定論の自動退役 + 事後報告 + 復元権」として無人実行するか、候補提示までに留… | A（value-steering-risk・熟慮: ADR-0080「Not gate dissolution」境界に触れるので、可逆・決… | 熟慮 | 各束の本文 |
| 12-05 の土曜ゲート | D-P3-05-4 | `patches/`（MIT diff）を公開 tree に残すか | A。「data, not code」の自己定義と CC0 の単一性（`_gc_trash/` の書き換え前 skill は D-P0-03… | 既定可 | 各束の本文 |
| 12-12 の土曜ゲート | D-P1-13-1 | 本体 repo で判断役 AI の merge/push を認めるか | C を既定（熟慮: 権限の所在に触れるので推奨は材料、decision は人間が打つ）— オーナー原則「人間がオーケストレーター」と CY… | 熟慮 | 各束の本文 |
| 12-12 の土曜ゲート | D-P1-13-2 | Claude 実装 commit の帰属方式 | C（trailer は commit 単位の帰属、開示文は方式に依らず要る） | 既定可 | 各束の本文 |
| 12-12 の土曜ゲート | D-P2-01-2 | 推奨↔裁定一致率 100%（45/45）に対する監査をどの形で 1 回行うか | A + `gate_item` に `recommender=<model-id>` を足す（VL-36「記録にモデル名が残らない」を解く… | 既定可 | 各束の本文 |
| 12-12 の土曜ゲート | D-P2-05-1 | 無人 LLM 文書の公開をどう扱うか | C（人間の言葉が公開 commit に残り、スキャンは最後の防壁。負荷は週 1 コマンド） | 熟慮 | 各束の本文 |
| 12-12 の土曜ゲート | D-P3-01-1 | 研究問いに Q4「承認ゲートの負荷と価値層の legibility」を加えるか | B — 最も厚く記録されているのはゲート（82/547、6/11、2/4、推薦↔裁定の一致率 ADR-0099:167-169）・計器の建… | 熟慮 | 各束の本文 |
| 12-19 の土曜ゲート | D-P4-01-1 | 検討イベントをどれにするか | D — 「検討セッションを開く」だけなので誤発火の害が小さく、1 条件に賭けた RFC-0006 の失敗（12 回素通り）を繰り返さない | 熟慮 | 各束の本文 |
| 12-19 の土曜ゲート | D-P4-01-2 | Moltbook 閉鎖時に移植しないと決めるか | A — 縦断記録は Moltbook 1 つで閉じ、Protocol は使わない備え（Goodhart 的な能力拡大） | 熟慮 | 各束の本文 |
| 12-19 の土曜ゲート | D-P4-01-3 | オーナー不在（ゲート不在）N 週で装置を止めるかと N の値を決める | A、N = 4 週（熟慮。決定文に N を数値で書く。停止の是非と N の値はこの決定に 1 本化し、D-P2-01-4 は PIPELI… | 熟慮 | 各束の本文 |
| 12-26 の土曜ゲート | D-P1-09-3 | 非 macOS の扱いを宣言のみにするか cron 例を足すか | A — 「制約で彫る」と整合し、B は能力拡大。旧 P1-14.7（`--print` + runbook の最小例）も落とし、P1-14… | 既定可 | 各束の本文 |
| 12-26 の土曜ゲート | D-P1-11-3 | otel を routine use にして schema 追従義務を release gate に付けるか、v2.1… | B — ADR-0078 に消費計画も Review-when も無く（見出し grep 0）、本体のどの文書も使い方として参照せず（`C… | 熟慮 | 各束の本文 |
| 12-26 の土曜ゲート | D-P1-11-6 | rules repo を本体の較正依存先として維持するか vendoring するか | A — 本体の本番手順（憲法改正の承認）が依存する兄弟は rules だけで、B は本体の `requests+numpy` 床に sci… | 既定可 | 各束の本文 |
| 12-26 の土曜ゲート | D-P3-03-1 | dialogue 二アーム（Care 計器・環境対照）を走らせるか | B — Care は機構ゼロ・計器盲目で「働いているか誰も答えられない」状態を、本番ループに触れず 16GB 窓外の 1 実験で解消できる… | 熟慮 | 各束の本文 |
| 2027-01-09 の土曜ゲート | D-P1-02-2 | RFC-0047 の昇格先を ADR にするか CYCLES.md の 1 段落にするか | B — ADR 化は「次の face を探す」圧力（RFC 自身が Drawbacks で認める）を制度化し「止まる」と緊張する。型は 2… | 既定可 | 各束の本文 |
| 2027-01-09 の土曜ゲート | D-P1-03-1 | 追補で済ませてよい変更の範囲をどこで切るか | A — B は 0113 追補 1（fail-closed = 本番の feed が止まる条件の追加）を追補で通し続け、C は 0062（… | 既定可 | 各束の本文 |
| 2027-01-09 の土曜ゲート | D-P1-03-2 | Note の graph 語彙を `revised-by` の新設にするか、既存 `partially-superse… | A — graph の約束（prose を読まずに「生きているか」を辿る）を守るには無効化 Note の edge が要り、軽い Note… | 既定可 | 各束の本文 |
| 2027-01-09 の土曜ゲート | D-P1-12-2 | 人間の裁定の証跡をどう人間由来にするか（`stage-*` 行と `gate_item` 行の両方） | B（負荷を増やさず、audit 行と `gate_item` 行の両方に Claude の自己申告でない文字列が残る。`approver`… | 既定可 | 各束の本文 |
| 2027-01-16 の土曜ゲート | D-P1-05-2 | 長期 open 観測の出口を何週で強制するか | A — O-001 / O-002 は 12〜14 週で「観測」としての情報量が尽きている | 既定可 | 各束の本文 |
| 2027-01-16 の土曜ゲート | D-P1-06-1 | scripts の「鏡」4 関数をどう扱うか（ADR-0109 の bare `python3` 方針の読み） | B（鏡 4 関数を verify.md に日付つきで台帳化。A は scripts → core の結合を広げ、凍結後に core を触る… | 既定可 | 各束の本文 |
| 2027-01-16 の土曜ゲート | D-P1-06-2 | API 応答の `dict[str, Any]`（153 箇所、署名に `Any` 105 本）に DTO 境界を置くか | B（untrusted JSON の「形を信じない」規律（`is_valid_id(value: object)`）と緊張し、siblin… | 既定可 | 各束の本文 |
| 2027-01-16 の土曜ゲート | D-P1-07-1 | decision 面の無応答で何を払うか — 専用 breaker か timeout 短縮か | B を先に（実測 p95 4.9 s で 60 s は 12 倍の余裕、新しい状態を持たない）。連続 fail-closed が週次の読み… | 既定可 | 各束の本文 |
| 2027-01-16 の土曜ゲート | D-P1-07-2 | pass-1 fail-open の着地点をどうするか | A（新しい判定者も状態も増えず、「fail-open = 観測の継続」を満たす。B は過去の選択を現在に持ち込む。C は 16 GB で … | 既定可 | 各束の本文 |
| 2027-01-23 の土曜ゲート | D-P1-08-2 | main に required check `verify` の branch protection を置くか | B（可視 447 commit 中 merge 9 = 直 push が運用の形で、f89b28d の「判断役はローカルで verify … | 既定可 | 各束の本文 |
| 2027-01-23 の土曜ゲート | D-P1-09-1 | 文書の言語方針をディレクトリ別にどこまで決めるか | A — 既存の 3 行で足り、読者は AI で symlink でも読める（旧 .18 は落とした、既定可）。英語タイトル列は論文化で r… | 既定可 | 各束の本文 |
| 2027-01-23 の土曜ゲート | D-P1-09-2 | diagrams の鮮度規約に feed 側ゲートを含めるか | B — この 4 週で最大のゲート変更が地図から消えたままになるのを 1 ノードで防げる | 既定可 | 各束の本文 |
| 2027-01-23 の土曜ゲート | D-P1-10-1 | episode-log hook の正本を repo 同梱 `integrations/` に移すか harness … | A — 公開 repo の読者が検証でき、CI で境界をテストできる唯一の置き方（B は edca8cf 以来 1 か月半ずれたままの実績） | 既定可 | 各束の本文 |
| 2027-01-23 の土曜ゲート | D-P1-10-2 | `SECURITY.md` の受付範囲と「止まる」後の方針を何にするか | A — DOI 付き公開物に窓口が無い状態を最短で閉じ、NOTICE の takedown 節（P3-05.14 (b)、SA-17）を正… | 既定可 | 各束の本文 |
| 2027-01-30 の土曜ゲート | D-P1-01-2 | 凍結後の生成 / 埋め込みモデル交代をどう扱うか | A（熟慮: 研究の装置境界を決める決定。推奨は材料で decision は人間が `gate_record` に打つ）— Q1（small… | 熟慮 | 各束の本文 |
| 2027-01-30 の土曜ゲート | D-P1-07-3 | Ollama 本体の導入・更新経路をどうするか | A（既定可。現行の plist はアプリ導入を前提にしており、入れ直しの手間と launchd テンプレートの変更が要らない。自動更新を切… | 既定可 | 各束の本文 |
| 2027-01-30 の土曜ゲート | D-P1-13-3 | 外部 PR を受けるか | A（#9 が既に来ており、ADR が要る変更の線を先に引けば貢献者の時間を無駄にしない。線は CONTRIBUTING の 1 段落 + … | 既定可 | 各束の本文 |
| 2027-01-30 の土曜ゲート | D-P1-14-1 | `install-schedule` を配布単位非依存に直すか「clone + `.venv` 前提」を明記するか | B を既定。A は P0-06 の配布単位（RD-29 / CU-27、11-07）が wheel を選んだ時だけ（決定前に A をコード… | 既定可 | 各束の本文 |
| 2027-01-30 の土曜ゲート | D-P3-04-3 | identity 蒸留の入力を憲法と同じ live に揃えるか | A（既定可: 現状維持 + 理由の記録。B は値層の生成器への介入 = P3-07.1 チャネル (5) として value-steeri… | 既定可 | 各束の本文 |
| 2027-02-06 の土曜ゲート | D-P1-04-3 | Face A（comment 生成 golden 12 件）を相関証明するか smoke に降格するか | B — 回帰検出力がほぼ無い（null pair で偽陽性 1/12、12/12 が DRIFTING、ADR-0089:573-600）… | 既定可 | 各束の本文 |
| 2027-02-06 の土曜ゲート | D-P2-04-1 | sync-data をどの経路で回すか決める（launchd 日次か distill 後処理か） | A — distill の成否と独立に公開ミラーが動き、`--uninstall` で止まる（ADR-0010 は .1 の partia… | 既定可 | 各束の本文 |
| 2027-02-06 の土曜ゲート | D-P3-01-2 | 評価層（ADR-0089）を研究証拠から除外するか、研究用に拡張するか | A — 12 件・2–1 margin・cloud judge では弁別力が無く（`docs/evidence/adr-0089/READ… | 既定可 | 各束の本文 |
| 2027-02-06 の土曜ゲート | D-P4-02-1 | Moltbook アカウントをどう処遇するか | A — observation-over-steering（観察対象への介入を最小に）と公開記録 = アカウント URL の整合。B は人… | 既定可 | 各束の本文 |
| 2027-02-06 の土曜ゲート | D-P4-03-1 | 継承者を 1 名決めるか「決めない」と記録するか | B — 鍵を渡さず archive だけできる最小権限は security by absence を崩さず、公開ミラーの「静かな停止」を「… | 熟慮 | 各束の本文 |
| 2027-02-13 の土曜ゲート | D-P2-01-4 | 最終ゲート日の行を PIPELINE-STATUS にどう表示し、watchdog の fail 行を出すか | B（自動停止は入れない — P2-04 と同じ方針。停止の是非と N の値は D-P4-01-3（12-19）に 1 本化し、本決定は表示… | 既定可 | 各束の本文 |
| 2027-02-13 の土曜ゲート | D-P2-03-1 | `claims.py` spawn と task-triage loop を repo に取り込むか文書化に留めるか | B — 系譜は公開 RFC に残れば帰属（ADR-0050）が閉じ、triage は Claude Code セッションそのものなので取り… | 既定可 | 各束の本文 |
| 2027-02-13 の土曜ゲート | D-P2-06-1 | 多軸 join をどこで行うか | C — 近傍と段の判定は staging 時にしか正確に取れず、reply_rate と novelty は週次ファイルにしか無い | 既定可 | 各束の本文 |
| 2027-02-13 の土曜ゲート | D-P3-06-1 | 論文の主題と種別を決める | A を先に起票し、B は 2027-Q1 の読みで判断、C は A / B と並行の供出であって投稿先ではない | 熟慮 | 各束の本文 |
| 2027-02-13 の土曜ゲート | D-P3-07-1 | 「空性のみ公理・三原則をルール化」案をどの形で扱うか | C → 判定後に A か B — 本番で行うと (i) 三原則が改正不能・gate 外・shadow / IPD / eval の対象外に… | 熟慮 | 各束の本文 |
| 2027-02-20 の土曜ゲート | D-P2-04-2 | backup を日次にするか 7 日損失を許容するか | A — episode log は唯一の原資料で、コストは git push 1 回/日 | 既定可 | 各束の本文 |
| 2027-02-20 の土曜ゲート | D-P3-02-1 | 「縦断分析」文書をどう扱うか | A を今、B は最終スナップショットの定義（D-P4-02-2）が決まってから — B は wind-down の成果物なので終了設計と同… | 既定可 | 各束の本文 |
| 2027-02-20 の土曜ゲート | D-P3-03-2 | AILuminate 面を退役するか、ローカル judge で置換するか | A — 未較正・第三者 API 送信・repo 内に手順無しで、論文の安全面は FLIP が同じベンチを持つ | 既定可 | 各束の本文 |
| 2027-02-20 の土曜ゲート | D-P3-03-3 | 「憲法なし」の本番対照を 2 体目で置くか | A（B は D-P3-03-1 で検討） — C はゲート負荷を 2 倍にして北極星 A（負荷 → 0）と逆行し、ToS も未検討 | 熟慮 | 各束の本文 |
| 2027-02-20 の土曜ゲート | D-P3-03-4 | value layer を cloud モデルに送る実験（(b)(c)、AILuminate）を許すか | C — 同じ前提（cloud に価値層を出す）の判断なので一度に決める | 熟慮 | 各束の本文 |
| 2027-02-27 の土曜ゲート | D-P2-05-2 | 却下台帳の公開範囲 | A（README の中心主張を検証可能にし、本文は `.rejected/` に非公開保持。observation-over-steeri… | 既定可 | 各束の本文 |
| 2027-02-27 の土曜ゲート | D-P2-07-2 | 飽和の判定軸と窓をどう置くか | B（熟慮: 飽和は出口の trigger に触れる） — A では RFC-0042 と 0048 が互いを待つ dead-band が続く | 熟慮 | 各束の本文 |
| 2027-02-27 の土曜ゲート | D-P2-07-3 | live プールの保持方針 | a を明文化し、年齢分布の読みを 2 期見てから b / c を判断（c は機構の拡大で、再入の実害が `skipped_known` 増… | 既定可 | 各束の本文 |
| 2027-02-27 の土曜ゲート | D-P3-05-3 | export 時に `id` 列を付与するか | B を今、A は「export 境界は raw と同形」（`export-patterns-jsonl.py` docstring）の例外… | 既定可 | 各束の本文 |
| 2027-03-06 の土曜ゲート | D-P1-14-2 | 購読確認を永続化するか、起動時 1 回のまとめ確認にするか | C。A は home に新しい永続状態 + 却下記録 = 能力で、影響は第三者の APPROVE 体験のみで本番 `--auto` には無… | 既定可 | 各束の本文 |
| 2027-03-06 の土曜ゲート | D-P2-04-3 | insight / distill-identity に `.run.lock` の非ブロッキング確認を足すか | B — 現状は時刻で分離済み。.9 の `late_minutes` で衝突が観測されたら A へ | 既定可 | 各束の本文 |
| 2027-03-06 の土曜ゲート | D-P3-05-6 | 2 世代テンプレートが同居する store（4 件の loop 型 4,329〜6,913 B、`fluid-` / … | B。書き換えは所有者の値層介入で P3-07 の介入チャネル登録表の対象（2026-07-10 の clean rewrite が前例、`… | 既定可 | 各束の本文 |
| 2027-03-06 の土曜ゲート | D-P3-06-2 | FLIP に渡す束の範囲を決める | B（memo §提示戦略「実装観察として提示」。C は P3-07 の A / B / C 決定後） | 既定可 | 各束の本文 |
| 2027-03-06 の土曜ゲート | D-P3-06-3 | 「読んで返信しない」分岐を機構に足すか | .9 の 4 週読みまで A（熟慮: 価値層とゲートの読み値に触る決定。推奨は材料であり、裁定は人間が `gate_item` に書く）。… | 熟慮 | 各束の本文 |
| 2027-Q2 | D-P4-02-2 | 最終版で snapshots の回転窓（`MAX_SNAPSHOTS = 100`）の履歴分を tree に戻すか | B をサイズ確認つきで（熟慮。最終の不変版から回転で消えた snapshot を抜くか入れるかの決定で、後から足せない一方向の扉）— Ze… | 熟慮 | 各束の本文 |

**ゲートごとの件数**（決定 ≤ 5・熟慮 ≤ 3・着手束 ≤ 2。⚠ = 超過。遡及分は数えない。項目の S は平日の Claude Code 1 セッション、M は 2〜3 セッション）

| ゲート | 決定数 | 熟慮 | 着手する束 | 着手束の項目（S / M） | 先行項目 | 主題 | ID |
|---|---|---|---|---|---|---|---|
| 10-10 の土曜ゲート | 3（遡及） | 1 | P0-01 P0-03 | 10（10 / 0） | — | 遡及記録（10-17 に decided_at=2026-10-10 で打つ） | D-P0-01-1 D-P0-01-3 D-P0-03-2 |
| 10-17 の土曜ゲート | 5 + 遡及 3 | 1 | P0-02 P1-04 | 25（20 / 5） | P2-01.1 P2-01.2 P2-01.10 P2-01.12 P2-01.11 P2-01.13 P2-01.14 P0-07.4 P1-05.1 P1-05.4 P3-05.1 P3-05.2 P1-03.11 P0-03.16 | P0-02（削除 PR）+ P1-04（T4 第 2 回）。SKILL 同梱 PR は前日まで。決定と削除 PR では最も重い週 | D-P0-01-2 D-P0-02-1 D-P0-02-2 D-P1-04-1 D-P3-04-2 |
| 10-24 の土曜ゲート | 5 | 3 | P0-04 P0-07 | 12（11 / 1） | P0-03.2 P0-03.3 P0-03.4 P0-03.5 P0-03.6 P0-03.7 P0-03.8 P0-03.9 P0-03.10 P0-03.11 P0-03.14 P0-03.16 P1-07.1 P1-07.5 P1-07.18 P1-10.5 P1-10.6 P1-10.15 P1-01.1 P2-03.1 P1-11.10 | P0-04（.1）+ P0-07（憲法 due 前、10-26〜30 に PR）。先行は P0-03 の残り（10-19〜23）。項目数では 10 月で最も重い週 | D-P1-02-1 D-P1-04-2 D-P1-04-4 D-P1-05-1 D-P3-04-1 |
| 10-31 の土曜ゲート | 5 | 3 | P3-04 | 5（4 / 1） | P3-03.1 P3-03.2 P3-03.10 P3-01.2 P1-15.2 P1-01.2 P2-01.7 P2-01.9 P1-02.5 P3-04.1 P3-04.2 P3-04.3 P3-04.12 | P3-04（.1 の prune は 10-31 の週に先行）。土曜は P0-07 の 2 件を読みのみで決めるので軽いが、前の平日は 10 月で最も Ollama の読みが多い（前夜起動で在席不要） | D-P0-07-1 D-P0-07-2 D-P1-11-1 D-P1-12-1 D-P2-01-5 |
| 11-07 の土曜ゲート | 5 | 2 | P0-05 P0-06 | 20（16 / 4） | P1-10.7 P1-10.8 P1-11.2 P1-11.3 P1-14.2 P2-04.22 P1-11.13 | v2.13.0 の形（P0-05 / P0-06） | D-P0-05-1 D-P0-05-2 D-P0-06-1 D-P0-06-2 D-P0-06-3 |
| 11-14 の土曜ゲート | 5 | 2 | P0-06 P1-10 | 9（7 / 2） | P1-11.5 P1-14.9 P2-05.7 P1-07.19 | P0-06（tag は決定の後の 11-16〜20）+ P1-10（コード修理） | D-P1-08-1 D-P1-11-2 D-P1-11-5 D-P3-05-1 D-P3-05-5 |
| 11-21 の土曜ゲート | 5 | 3 | P0-03 P3-05 | 12（9 / 3） | P1-11.11 P1-11.12 P1-05.5 P3-05.19 | P0-03（版と backfill）+ P3-05（.14 takedown） | D-P0-03-1 D-P0-03-3 D-P0-04-1 D-P0-04-2 D-P3-05-2 |
| 11-28 の土曜ゲート | 5 | 5 例外 | P1-03 P2-01 | 11（8 / 3） | P1-09.1 P1-09.8 P1-09.9 | P1-03（追補（2026-11））+ P2-01（負荷の定義）。熟慮 5 は追補（2026-11）の 1 PR に結ぶ例外 | D-P1-01-1 D-P2-01-1 D-P2-01-3 D-P2-02-1 D-P2-05-3 |
| 12-05 の土曜ゲート | 5 | 3 | P2-07 P1-15 | 5（5 / 0） | P1-09.10 P1-09.13 P1-09.14 P3-06.9 P3-06.11 P3-02.1 | P2-07（.5 境界草案）+ P1-15 | D-P1-11-4 D-P1-15-1 D-P1-15-2 D-P2-07-1 D-P3-05-4 |
| 12-12 の土曜ゲート | 5 | 3 | P3-01 P1-13 | 13（10 / 3） | — | P3-01（研究問い）+ P1-13（AI 判断役） | D-P1-13-1 D-P1-13-2 D-P2-01-2 D-P2-05-1 D-P3-01-1 |
| 12-19 の土曜ゲート | 3 | 3 | P4-01 P1-08 | 21（21 / 0） | — | P4-01（追補（2026-12））+ P1-08（CI と test の信頼性） | D-P4-01-1 D-P4-01-2 D-P4-01-3 |
| 12-26 の土曜ゲート | 4 | 2 | P1-11 P1-02 | 13（11 / 2） | — | P1-11（mlx / otel / rules）+ P1-02（RFC 台帳）。年末 | D-P1-09-3 D-P1-11-3 D-P1-11-6 D-P3-03-1 |
| 2027-01-09 の土曜ゲート | 4 | 0 | P1-12 P1-05 | 11（7 / 4） | P1-09.2 | P1-12（approver）+ P1-05（批准経路）。01-02 は休みなので T4 第 3 回をこの回に | D-P1-02-2 D-P1-03-1 D-P1-03-2 D-P1-12-2 |
| 2027-01-16 の土曜ゲート | 5 | 0 | P1-06 P1-07 | 18（14 / 4） | P1-06.10 P1-06.4 P1-06.1 | P1-06（構造 PR-A）+ P1-07（アダプタ） | D-P1-05-2 D-P1-06-1 D-P1-06-2 D-P1-07-1 D-P1-07-2 |
| 2027-01-23 の土曜ゲート | 5 | 0 | P1-09 P3-02 | 16（13 / 3） | — | P1-09（文書）+ P3-02（境界表） | D-P1-08-2 D-P1-09-1 D-P1-09-2 D-P1-10-1 D-P1-10-2 |
| 2027-01-30 の土曜ゲート | 5 | 1 | P3-07 P1-03 | 7（5 / 2） | — | P3-07 + P1-03（.2 / .3） | D-P1-01-2 D-P1-07-3 D-P1-13-3 D-P1-14-1 D-P3-04-3 |
| 2027-02-06 の土曜ゲート | 5 | 1 | P2-04 P2-02 | 27（24 / 3） | — | P2-04（sync・watchdog）+ P2-02（無人チェーン）。eval 層の位置づけ 2 件を同じ回に | D-P1-04-3 D-P2-04-1 D-P3-01-2 D-P4-02-1 D-P4-03-1 |
| 2027-02-13 の土曜ゲート | 5 | 2 | P2-03 P3-06 | 12（8 / 4） | — | P2-03 + P3-06（論文） | D-P2-01-4 D-P2-03-1 D-P2-06-1 D-P3-06-1 D-P3-07-1 |
| 2027-02-20 の土曜ゲート | 5 | 2 | P3-03 P2-05 | 13（4 / 9） | — | P3-03（研究対照）+ P2-05（公開 2 層） | D-P2-04-2 D-P3-02-1 D-P3-03-2 D-P3-03-3 D-P3-03-4 |
| 2027-02-27 の土曜ゲート | 4 | 1 | P2-06 P2-07 | 6（2 / 4） | — | P2-06 + P2-07（層 1 実装） | D-P2-05-2 D-P2-07-2 D-P2-07-3 D-P3-05-3 |
| 2027-03-06 の土曜ゲート | 5 | 1 | P4-02 | 8（6 / 2） | — | P4-02（runbook dry-run） | D-P1-14-2 D-P2-04-3 D-P3-05-6 D-P3-06-2 D-P3-06-3 |
| 2027-03-13 の土曜ゲート | 0 | 0 | P4-03 | 3（3 / 0） | — | P4-03（継承、P4-02 の runbook の後）。決定は空き枠（繰り越し先） | — |
| 2027-03-20 の土曜ゲート | 0 | 0 | — | 0（0 / 0） | — | 空き枠（繰り越し先、P2-01.14） | — |
| 2027-03-27 の土曜ゲート | 0 | 0 | — | 0（0 / 0） | — | 空き枠（繰り越し先、P2-01.14） | — |
| 2027-Q2 | 1 | 1 | — | — | — | | D-P4-02-2 |

**月別の作業量の見積り**（着手する束の全項目をその月に数える上限側の見積り。束は着手後も数週続くので、実際の負荷は後ろの月へ均される。セッションは S = 1、M = 3 で数えた）

| 月 | 着手する束の項目 | 先行項目 | セッション見積り | 週あたり |
|---|---|---|---|---|
| 2026-10 | 52 | 48 | 122 | ≈ 24 |
| 2026-11 | 52 | 18 | 96 | ≈ 24 |
| 2026-12 | 52 | 6 | 68 | ≈ 17 |
| 2027-01 | 52 | 4 | 84 | ≈ 17 |
| 2027-02 | 58 | 0 | 98 | ≈ 24 |
| 2027-03 | 8 | 0 | 12 | ≈ 3 |

比べる実績（git log、2026 年 ISO 週 W34〜W41 の commit 数）: 33 / 50 / 51 / 122 / 55 / 83 / 24 / 15。中央値は週 ≈ 51 commit で、直近 2 週は 24 / 15。1 セッション ≈ 1〜3 commit とすると、10〜11 月の見積りは中央値並みで、直近 2 週の水準なら 2〜3 倍になる。遅れたときの繰り越しと縮退の順は P2-01.14 に置く。実績は P2-01.13 の分離列と P2-01.2 の所要分が出たら差し替える。


### 4.1 束ごとの決定事項（選択肢・推奨・期限の全文）


### P0-01 10-10 土曜ゲートの決定束（insight / RFC-0042・0023・0048 / ADR-0111 / T4）
- D-P0-01-1: 選ぶ — insight 週次の入口の運用（継続 / 入口停止 / 月次） / 選択肢: A 週次のまま継続し、revise 表（.6）を読んでから案 B の要否を決める（10-24 まで） B 入口停止（launchd job を止めて出口専用運用、CYCLES #4 書換） C 月次に落として継続 / 推奨: A — 10-10 の 1 回の読みで入口停止を決めるのは one-run-not-evidence に反し、週次の費用は naming call 約 20 秒 × 数 cluster で負荷は既に 0、案 B の材料（revise 13 件以上）を先に読む / 期限: 10-10 に A/B/C を選び（10-17 に遡及記録）、A なら案 B の判断を 10-24 まで。遅れると RFC-0048・ADR-0111 が互いの読みを待つ dead-band が続く。
- D-P0-01-2: 決める — staged 台帳の却下分を「既知」に含め続けるか / 選択肢: A 現状維持（意図を ADR-0074 追補に明記） B adopted + 直近 N 週の staged に絞る C 却下から 12 週の TTL / 推奨: .7 の内訳を 1 回読むまでは A — RFC-0042 の読みの最中に判定者の入力を変えると絞りの効果と分離できない。内訳で ledger_rejected が covered の過半なら B（却下 = オーナー意思が入口に効く経路、ADR-0050 と緊張）。（熟慮・value-steering-risk: B / C を採る場合は ADR-0050 en:112「No rejection write-back」と ADR-0074 en:115-117「reached review なら decision-agnostic に台帳へ」のどちらを partial supersede するかを決定文に明記する。A なら両 ADR は生きたまま相互参照のみ） / 期限: 10-17 の土曜ゲート（内訳の読み後）。遅れても実害は小さいが「店の飽和」と「却下台帳の飽和」が区別できないまま。
- D-P0-01-3: 終端する — RFC-0023 の希少レーンを withdraw するか / 選択肢: A withdraw（S9 分で done） B RFC-0048 の設計後まで blocked 継続 / 推奨: A — 供給増の機構は RFC-0048 の「絞る」方向と同時に走らせると読めない（RFC-0023 の 2026-09-07 著者判断そのまま） / 期限: 10-10 の土曜ゲート。遅れると blocked RFC が 1 本残るだけで実害は小さい。


### P0-02 10-15 読み → 旧 relevance gate の削除（RFC-0046 後始末 3）
- D-P0-02-1: 決める — 10-17 の Step 1c の照合（材料は 10-15 のログ）が不成立のとき v2.13.0 をどうするか / 選択肢: A 成立まで待つ（最大 1 週、次の submolt-scan） B 「移行済み・旧コード残置」を CHANGELOG に明記して切る C 旧 caller の残りを先に直してから再読 / 推奨: A — RFC-0046 が「移行 → 確認 → 削除 → DOI release」の順を明記し、残置版を DOI で固定すると引用される版に二重判定者が残る。B は残置コードを不変 DOI に固定する一方向の選択なので、B を採る場合は `reason` 必須 / 期限: 10-17 の土曜ゲート（照合コマンドは decisions.md の D-P0-02-1 行の材料欄、同日 Step 1c で実行。材料は 10-15（木）03:00 JST の scan ログ）。遅れると P0-06（v2.13.0、形は 11-07、tag は 11-14 の決定の後の 11-16〜20）が 1 週ずれる。
- D-P0-02-2: 選ぶ — ADR-0112 の退役部分の記録方法 / 選択肢: A `partially-superseded-by ADR-0113` + graph エッジ（.8） B ADR-0113 Amendment 3 からの注記のみ / 推奨: A — 追補による実質 supersession は `test_adr_status_consistency` の検査外（P1-03 の一般問題）で、Status と graph を動かさないと索引上「9/25 の 1 決定」に見える / 期限: 10-17 の土曜ゲート（削除 PR と同時）。遅れると ADR 台帳の stale が 1 本増える。


### P0-03 公開データの開示境界の修理（embedding 入り .bak・ロック・絶対パス）
- D-P0-03-1: 公開履歴から embedding 入り bak と `/Users/` を書き換えて消すか / 選択肢: A 消さない（tree から外し DATACARD に公開期間を注記） B `git filter-repo` + force-push で消す（clone・SWH・fork が割れる） C bak を LFS / 別アーカイブへ退避 / 推奨: A — 公開 DOI v1.0.0（`CITATION.cff` 2026-06-17）は `.zenodo.json` の記述どおり embedding 入りの knowledge.json を既に含み、bak 3,250 行のうち deposit 後の 2,424 行も `pattern` から再導出可能なので、書換の撤回効果が小さい。材料: 本体 repo に B を当てると `real_sample.jsonl` を足した commit 以降のすべての SHA が変わる（v2.13.0 の tag と DOI 戻し commit、`CITATION.cff:30-51` の SWH 識別子（P0-06.11 で `anchor=rev` 形にする）、releases.md の commit 列、`docs` / `rfcs` / `CHANGELOG.md` 内の約 266 個の 7〜12 桁 hex 参照 — commit 以外を含む）ので、本体分は選択肢から B を外す（この決定は 11-21 で、v2.13.0 の tag（11-14 の決定の後、11-20 まで）より後になるため。B は data repo にだけ当てうる）。本体の既存の版 DOI（v2.6.0〜v2.12.0 の release zip）に `real_sample.jsonl` が入っているかをオーナーが `git ls-tree -r <tag> --name-only | grep real_sample` で確かめ、入っていれば書き換えでも撤回できないことを P3-05.14 の到達範囲表に 1 行。B を採る場合の実行条件: sync job を unload し、`git clone --mirror` で書き換え前を私的に退避、filter-repo の `commit-map` を私的 backup に保存し、書き換えは sync を行う checkout そのもので行い（.16 (c)）、実施日と旧→新 SHA の所在を DATACARD と releases.md に 1 行（熟慮: force-push は clone・SWH・fork を割る一方向の操作。本体 repo の `real_sample.jsonl`（.11）の履歴も同じ判断） / 期限: 11-21 の土曜ゲート（データ版 DOI（D-P3-05-1 / P3-05.12）の前、D-P0-03-3 と同じ回）。遅れると 12-05 のゲートの後に切る版以降が D-P3-05-1 (b) C で埋め込む `[see GitHub <commit>]` の SHA が、後から B を選んだときに無効になる
- D-P0-03-2: `_gc_trash/` の退役 skill 原本 10 件を公開に残すか / 選択肢: A 除外 + `git rm`（`4f53259` の判断に揃える、履歴は残る） B 公開を続け DATACARD に由来と `.archive/` との違いを書く / 推奨: A — 同種の artifact の公開可否が時期で割れる状態を解消する方が研究再利用者に説明しやすい / 期限: 10-10 の土曜ゲート（遡及は 10-17 まで可）で決め、.2 の共有除外ファイル（10-24 の週）で実装。遅れると二重基準が DATACARD に固定される
- D-P0-03-3: 決める — 公開 projection で第三者由来の逐語 span を伏せ字にするか / 選択肢: A 開示のみ（.9 の文言訂正と carve-out 注記で終え、projection は変えない） B export 境界（`export-patterns-jsonl.py`）で第三者由来の N 語以上の span を伏せ字にした projection（HF `patterns.jsonl`）を出す（エージェントの記憶は触らない） C B に加え公開 tree の `knowledge.json` / `reasoning.md` / `snapshots/*/skills/*.md`（83 ファイル一致）/ weekly 文書（`reports/analysis/`、.9）も同じ規則で伏せる D 表示名の仮名化を export 境界で行う（private salt の HMAC 先頭 8 桁。遡及範囲 = 公開済み knowledge 142 行・skills 1・snapshots 105 ファイル・weekly。記憶は不変） E 面別（GitHub / HF / Zenodo）に決める / 推奨: .9 の開示と carve-out 注記（REP-06 の A + C）を 10-24 に先に入れ、B 以降はオーナー判断（熟慮: 公開面の第三者由来 span は takedown・CC0 主張・研究再利用の責任の接点で、伏せ字は projection の内容を変える一方向の扉。Zenodo 版は不変なので次の deposit の前に決める。逐語 span と表示名の扱いは撤回ポリシーの一部なので D-P3-05-2 と同時に決める） / 期限: 2026-11-21 の土曜ゲート（撤回ポリシー D-P3-05-2 と同じ回、公開データの版の前 — 最初の新版は 12-05 のゲートの後）。遅れると取り下げ不能な deposit に測定値なしの「no raw quoted」が残る


### P0-04 蒸留の取りこぼしと非原子書き込みの修理（06:00 JST セッション）
- D-P0-04-1: 決める — 未蒸留の 06:00 JST episode（2026-03〜）を backfill するか / 選択肢: A 全期間（現行 gemma4:e4b・現行プロンプトで旧 regime の episode を蒸留、数十 GPU 時間、窓外で分割） B 修理日以降のみ + 欠損を DATACARD / 境界表に記録 C 直近 4 週だけ / 推奨: B — backfill は装置境界（モデル・プロンプトの変更、P3-02）をまたぐ再蒸留で時系列の意味が変わる（熟慮: 公開 knowledge.json の時系列に一方向で効く）。A はやるなら別 run 名で後日、研究層（P3-02）の判断として / 期限: 11-21 の土曜ゲート（.2 が記録する取りこぼしの実数を材料に、D-P0-04-2 と同じ回）。遅れると公開 knowledge.json の欠損が記録なしのまま DOI 版（P3-05）に入る。
- D-P0-04-2: 選ぶ — knowledge.json の保存前バックアップ / 選択肢: A `save()` 直前に 3 世代（7.5 MB × 3、`knowledge.backups/`） B 案内文の修正のみ / 推奨: A — 正本が 1 つで週 1 backup だと最大 6 日分の蒸留を失う、sync 除外も既にある / 期限: 11-21 の土曜ゲート（D-P0-04-1 と同じ回）。遅れると docs の復元案内が空振りのまま。


### P0-05 初回体験（Quick Start）の修理と preflight
- D-P0-05-1: Ollama / 生成モデル不在で session を止めるか / 選択肢: A 起動時 canary が `ok` 以外なら短い再試行（例 3 × 20 秒、ollama-restart 23:55 直後の起動を吸収）の後 rc=1 で終了 B WARNING + 計数のみで継続（現状 + .2(a)） C 対話実行は停止、launchd は継続 / 推奨: A — Ollama 無しでできる仕事が無く、6 時間の無行動は翌週の人間の読み（ADR-0113 Review-when）に負荷を移すだけ。停止は fail loudly であり「止まる」の条件には触れない。P2-04.5 (2) の「`run` 起動時 ERROR + 非 0」はここに統合（判定は .1、期限 2027-Q1 ではなくこの回） / 期限: 11-07 の土曜ゲート（v2.13.0 の形）。遅れると .2 の WARNING だけで出荷し launchd の無行動が続く
- D-P0-05-2: `init` が複製する `prompts/` を既定 home でも読むか / 選択肢: A `_resolve_home_prompts_dir` を `config.MOLTBOOK_DATA_DIR` に揃える（本番が stale な home 複製を黙って読み始める） B `init` の prompts 複製をやめ、CONFIGURATION を「packaged prompts が apparatus、override は `MOLTBOOK_HOME` 明示時のみ」に直す C A + 本番 home の `prompts/` を先に削除して差分ゼロを確認 / 推奨: B — 本番 100 snapshot が `prompts_dir: null`、ADR-0003 / 0054 の語彙とも合う。B 前提で P1-14 の home 解決 2 項目（`domain.json` 複製・prompts drift 警告）は落とし、残るのは .7 / .10 の文書行だけ / 期限: 11-07 の土曜ゲート（v2.13.0 の形）。遅れると第三者の prompt 編集が効かないまま README が「source of truth」と言い続ける


### P0-06 v2.13.0 リリース（Python 床・配布単位・版メタデータ・runbook）
- D-P0-06-1: Python 床を 3.11 に上げるか、3.10 を shim で守るか / 選択肢: A 3.11（classifiers・ruff `py311`・README・CLAUDE.md・sibling を同期） B `assert_never` の 1 行 shim + `tomllib` guard で 3.10 維持（Ubuntu 22.04 既定 3.10 を救う） C 現状放置 / 推奨: A — 3.10 は 2026-10 に EOL（PEP 619）、実行機は macOS M1 で 3.13、shim は「床より新しい API」の再発を止めず床 CI だけが止める（熟慮: 床は DOI 付き配布条件で、引用される版に一方向で残る） / 期限: 11-07 の土曜ゲート（tag は 11-14 の決定の後の 11-16〜20）。遅れると DOI 付き配布条件が偽のまま 1 版増える。
- D-P0-06-2: 配布単位を clone + editable 限定にするか、自己完結 wheel にするか / 選択肢: A clone + editable 限定を README と ADR-0109 追補に明記し、兄弟の pin 先は P1-11.1 の tag 方針に従う B `config/` を package data 化（`importlib.resources` 起点）し終了時に PyPI へ 1 版だけ出す C Homebrew / 推奨: A — 最小で保守面を増やさない。ADR-0088 の「wheel で kit を届ける」は kit が core のみ依存（import-linter 契約）なので A でも成立し、B は `DEFAULT_CONFIG_DIR` と `_repo_root()` の改修が要る（熟慮: 配布面は保守義務を増やす一方向の扉） / 期限: 11-07 の土曜ゲート（README pass は 11-14 の決定の後、11-20 までの tag 前）。遅れると README が「pip installable」を暗に約束したまま出る。
- D-P0-06-3: 2.x の minor で Protocol・設定面（env / domain key / prompt / CLI フラグ）を壊してよいか / 選択肢: A 可、ただし CHANGELOG に `### Breaking` 節必須 + 兄弟は tag pin か `>=X.Y,<X.Y+1` B 破壊は major のみ C 1 版の deprecation warning を挟む / 推奨: A — v2.13.0 は `DECISION_*` / `thresholds.relevance` / `relevance.md` の削除を予定（`rfcs/0046:262`）し、利用者は 1 インスタンス + 兄弟 2 repo。公開面（CLI 引数、`LLMBackend` / `DecisionBackend`、`contemplative_agent.testing`、`MOLTBOOK_HOME` レイアウト、`knowledge.json` / 監査 JSONL スキーマ）の列挙を runbook に 10 行で書く / 期限: 11-07 の土曜ゲート（CHANGELOG 起こしの前）。遅れると削除が「Changed」に埋もれ、README 事故（RD-33）の再発面になる。


### P0-07 10-31 due の憲法改正ゲートの事前登録と shadow 系列
- D-P0-07-1: 決める — 10-31 の due で改正を起動するか、読みだけ取って見送るか / 選択肢: A 起動（runbook 全 step、IPD 二腕 + shadow + 事前登録 4 読み） B 読み（shadow 2 run・IPD・referent inventory）だけ取り改正は見送り、次 due まで待つ C 読みも取らず due を流す / 推奨: B を既定、A は .2 の事前登録と .1 の系列が 10-31 までに揃った場合のみ — due は生成の cadence で改正の義務ではなく（ADR-0091）、事前登録なしの改正は ADR-0056 系と矛盾する（熟慮: 改正は価値層の一方向の変更で、起動は人間の責任の行為） / 期限: 10-31 の土曜ゲート（この回は P0-07 の 2 件 + D-P1-11-1 / D-P1-12-1 / D-P2-01-5 の 3 件 = 5 件・熟慮 3。P0-07 の 2 件は土曜当日は読みのみが既定で軽く、Ollama の読みは 10-31 の週の平日）。遅れると RFC-0012 の dead-band が続き、次の due は 2027-01 になる。
- D-P0-07-2: 選ぶ — shadow を weekly chain に月次配線するか / 選択肢: A 手動のまま（opt-in-first、census 90 日を維持） B 月次配線（due の 4 週前から） C 計器を撤去（census ∞） / 推奨: 10-31 のデータで決める。それまでは A — ADR-0092 の「配線は読みが有用と分かってから」に従い、.1 の 2 run が 8 月と差を示さなければ C も候補 / 期限: 10-31 の土曜ゲート。遅れると ADR-0092 の計器が消費計画なしで 2027 年に入る。


### P1-01 機構層の「凍結」判定を定義する
- D-P1-01-1: 凍結の閾値と窓をどこに置き、何週とするか / 選択肢: A 連続 8 週 凍結集合の commit が `fix` のみ、かつ新設 mechanism ADR 0、かつ機構節の追補 0（消費計画・Review-when・dated Note は数えない） B 同条件で 4 週 C commit 数の上限（週 ≤ 2）で種別は問わない。追加段（2027-Q1 に凍結集合を触る項目の扱い、.9）: 追加段 A 停止リストに期日つきで載せる 追加段 B 計器行（watchdog の検査行・census の Entry）は読みから外し、src の機構変更（P2-07.1・P2-06.2・P1-12.1 PR-C・P1-07.7 / .8）だけ停止リストに載せる 追加段 C 第 5 章の延期行へ（凍結後は `fix:` + RFC でのみ） / 推奨: A（熟慮: 北極星の読み値に触る決定。閾値と窓は ADR-0080 の追補（2026-11）の定義にではなく dated note の「読み方」として置き、達したかの verdict は人間が `gate_record` に書く — 推奨は材料で decision は人間が打つ）— 9 月の sweep（W37 63 件）のような一過性の静穏を「止まった」と読まないには 2 か月の窓が要る。追補を機構節に限って数えるのは、10 月（新設 0・Note 11 行）が「止まった」に見える誤読と、本ロードマップ自身が足す消費計画・Note で (iii) が 0 にならない自己撹乱の両方を防ぐため。C は refactor を許し、健全性向上が完成を遠ざける構造を残す。基礎率の注（P1-03.9: W33〜W41 の「fix のみの週」は 0/9 で、8 週連続は現状の分布では到達不能 = 到達は分布が変わった読み）を追補（2026-11）の読み方に併記する。追加段は B — watchdog / census の行追加は ADR-0085 の検査面で、機構の動きと読むと「止まる」の意味がぼける。src の 5 項目は機構なので停止リストで開始点を遅らせる方が正直（新しい決定 ID は振らない — 11-28 は 5 件で満席） / 期限: 2 段 — 定義と追加段は 2026-11-28 の土曜ゲート（追補（2026-11）の材料）、verdict は窓が満ちた週の土曜ゲート（開始点 = 停止リストが空になった週。A の 8 週窓で、推奨どおり（D-P1-01-1 の追加段 B・D-P2-07-1 A）なら停止リストの最終行は P2-07.1 / P2-06.2 で、verdict は早くて 2027-05-01。両者を採らない場合は P1-06.3（2027-02-06）と P1-07.7 / .8（2027-01-30 の週）の遅い方 + 8 週で、早くて 2027-04-03）で `gate_record` に打つ。遅れると P1-06 の構造窓に終わりが無く、追補（2026-11）が閾値の読み方を欠いたまま入る。
- D-P1-01-2: 凍結後の生成 / 埋め込みモデル交代をどう扱うか / 選択肢: A 論文 cutoff（P3-06.3）までモデルを固定し、交代は強いられた場合（tag の撤去・Ollama の非互換・セキュリティ）だけ。ADR-0069 Trigger 1（`:131`）に日付つきの停止注記 B 交代を認め、凍結窓を数え直す C 交代を regime 行（P3-02.1 の境界表）として認め、窓は数え直さない。どれを採っても、重み blob を digest つきで手元保管するか DATACARD に「not archived」と書くかを同じ決定で選ぶ / 推奨: A（熟慮: 研究の装置境界を決める決定。推奨は材料で decision は人間が `gate_record` に打つ）— Q1（small-local-model behavior）の系列はモデルが替わると境界をまたいで比べられず（ADR-0090:127-130 は `OLLAMA_MODEL` の変更で IPD 床が無効になると明記）、ADR-0069 の交代 trigger は凍結（ADR-0080:80-82「finished observation instrument」）と正面から衝突する / 期限: 2027-01-30 の土曜ゲート（凍結の verdict は早くて 2027-05-01（推奨どおりの場合）で、その前）。遅れると凍結窓の途中で交代が起きたとき fix とも違反とも読めない。


### P1-02 RFC 台帳の健全化と blocked RFC の終端
- D-P1-02-1: RFC-0040 を withdraw するか blocked のまま置くか / 選択肢: A withdraw（照合先を ADR-0112 Review-when へ、arm K5 撤去） B blocked 維持（triage が 3〜4 日ごとに `ollama --version` 等を照合し続ける） C 問いを「確率の値を消費する機構」1 つに縮めて blocked / 推奨: A — 欠陥（47% 過剰通過）は RFC-0046 で修理済み、残部は「将来像」= ADR-0080 の審査で能力動機側、消費者の無い較正確率を待つ理由が無い / 期限: 2026-10-24 の土曜ゲート。遅れると 484 行の RFC に照合節が増え続ける。
- D-P1-02-2: RFC-0047 の昇格先を ADR にするか CYCLES.md の 1 段落にするか / 選択肢: A ADR 1 本（長期ルール） B CYCLES.md #6 に型の要約 + 溶解条件 1 段落 + evidence C 昇格せず done のみ / 推奨: B — ADR 化は「次の face を探す」圧力（RFC 自身が Drawbacks で認める）を制度化し「止まる」と緊張する。型は 2 face で使い切る使い捨てとして記録する / 期限: 2027-01-09 の土曜ゲート（それまで RFC-0047 は blocked のまま `decide_by:` にこの日付を書く）。遅れると face 台帳の未計測 4 行が open の体裁で残る。


### P1-03 ADR 台帳の機械追跡（追補・Note・索引・Review-when）
- D-P1-03-1: 追補で済ませてよい変更の範囲をどこで切るか / 選択肢: A 同じ決定の数値・閾値・手順のみ追補、反転・他 ADR の前提変更・本番挙動の変更は新 ADR か partial supersede B 追補を自由にし Status 尾部と Last revised 列で追跡だけする C README どおり「never overwrite」に戻し追補を禁止 / 推奨: A — B は 0113 追補 1（fail-closed = 本番の feed が止まる条件の追加）を追補で通し続け、C は 0062（追補 12）/ 0089（追補 5）の実態と合わない。A なら 0113 追補 1 は事後に「新 ADR 相当」と注記して済ませる。決定までは A の 3 条件を暫定基準として 10-17 から運用する（.11） / 期限: 2027-01-09 の土曜ゲート（.2 / .3 の test の前提）。遅れると 5 面の粒度が揃わず「ADR 数 ≈ 0」が凍結の読み値にならない。
- D-P1-03-2: Note の graph 語彙を `revised-by` の新設にするか、既存 `partially-superseded-by` へ寄せるか / 選択肢: A 新語 `revised-by`（@context 追加、軽い Note 用）+ 無効化 Note は partial supersede B すべて `partially-superseded-by` に寄せる（語彙は増えないが「数値を直しただけ」も supersede と読まれる） C Note は graph に出さず Last revised 列だけ / 推奨: A — graph の約束（prose を読まずに「生きているか」を辿る）を守るには無効化 Note の edge が要り、軽い Note を supersede と混ぜると 0097 のような多段 partial の意味が崩れる / 期限: 2027-01-09 の土曜ゲート（D-P1-03-1 と同じ回）。遅れると 0043 / 0086 / 0067 の 3 件が graph 上「生きている」と誤答され続ける。


### P1-04 計器の解体と消費計画の補完（ADR-0101 T4）
- D-P1-04-1: submolt-scope sweep を常設のまま残すか撤去するか / 選択肢: A. 四半期 1 回の手動 sweep に減速（plist 撤去、`report --submolt-scope` は残す） B. 撤去（計器・CLI・plist） C. 常設維持（Consumption plan を書く） / 推奨: A — RFC-0011 の読みは済み、順位比較は 10-09 の尺度変更で断絶、購読集合の見直しは四半期で足りる / 期限: 2026-10-17 の土曜ゲート（T4 第 2 回）。遅れると週 2,698 行規模のログが根拠なく増え続ける。
- D-P1-04-2: comment-outcomes の 2 窓判定で stage 7d を撤去するか帰属 RFC を起票するか / 選択肢: A. 分かれない → 撤去 + RFC-0028 resolved B. 分かれる → 帰属 RFC（D7 の北極星読み込みつき。条件: 読みに限り、skill 別返信率を adopt / archive の判定には流さない — 流せば reward weighting で ADR-0051 の supersede が要る（ADR-0106 D6、ADR-0080:213-217）） C. 窓を延長 / 推奨: 読みで決める（熟慮: 帰属 RFC は値層への経路に触るので推奨は材料にとどめ、decision は人間が `gate_record` に打つ）。「分かれる」の事前登録線（.5）: 返信率は `observed_publishes` のみを単位に（≥ 500 の数え上げは `joined_publishes`）、最大 skill 間差 ≥ 0.2 かつ skill 別 Wilson 区間が重ならないこと（χ² / G と置換検定は補助で、p 値では決めない）。読みは観測率 ≈ 1/3（D5 の分母）の限定つき。C は ADR-0101 の形骸化なので選ばない / 期限: 2026-10-24 の土曜ゲート（読みは 3 週窓 × 2（09-12〜10-02 / 10-03〜10-23）を `read_comment_outcomes` の 2 回の直接呼び出しで取る、.5）。遅れた場合は P2-01.14 の規則に従う（日付拘束なら次の土曜へ繰り上げ、上限に数える。6 件になる週は既定可 1 件を空き枠へ）。遅れると「計画の満了点を過ぎた計器」が毎週回る。
- D-P1-04-3: Face A（comment 生成 golden 12 件）を相関証明するか smoke に降格するか / 選択肢: A. 本番 comment 150 行を label-once し 5 check を真値と相関 B. `injection_resistant` / `persona_intact` の 2 check のみの smoke に降格（verdict 遷移を回帰判定に使わない） C. eval 層ごと撤去（4 連続 ack = ADR-0089 Revisit (a) 発火） / 推奨: B — 回帰検出力がほぼ無い（null pair で偽陽性 1/12、12/12 が DRIFTING、ADR-0089:573-600）のに cloud judge の唯一の egress を維持する理由が薄い。A は RFC-0047 の終端（P1-02.6、D-P1-02-2 が決めた昇格先）の後に再検討 / 期限: 2027-02-06 の土曜ゲート（D-P3-01-2 と同じ回 — 「eval 層は何のためにあるか」の両面。.11 の取り直しと .10 の ADR-0089 追補 1 本はこの後）。遅れると取り直した baseline が無意味な指標を固定する。
- D-P1-04-4: ADR-0105 stage 7c の撤去時計を 1 年から短縮するか / 選択肢: A. 「4 週連続で 7b と重複しない候補 0」で撤去 B. 1 年のまま C. 7b / 7c / 7d を 1 つの exit reading に畳む / 推奨: A（C は .4 の fan-in 0 と合わせて T4 で検討） / 期限: 2026-10-24 の土曜ゲート（T4 第 2 回 10-17 の読みを受けて）。遅れると「読みが何も決めない計器」（10-02: pairs 0・strict 0）が 2027-09 まで回る。


### P1-05 観察台帳と週次計器の機械化（baseline・expiry・自己故障）
- D-P1-05-1: 滞留する baseline_proposal 4 件をどう裁定するか / 選択肢: A. 4 件とも採用（temperature-0 幻覚帯 0–10%、question-closer 5–15%、nonce 0 ×2） B. temperature-0 帯のみ採用、他は却下（機械照合できる計器が無い） C. 全件保留 / 推奨: B（熟慮: 較正の変更は人間ゲートを通す設計（`observation_ledger.py:60-63`、RFC-0010 Q5/Q8）で、推奨は材料であって裁定ではない）— temperature-0 帯は O-009 / O-015 を同時に閉じ `selection_metrics` で照合できる。nonce / question-closer は今は render で照合する計器が無く、採用しても散文判定が残るので、B の残り 2 件は却下ではなく保留（C 扱い）とし、.8 の列ができたら（P1-05 の着手 2027-01-09 以降）その照合で裁定する / 期限: 2026-10-24 の土曜ゲート（ゲート再配分）。遅れると帯は score4 以前の bootstrap のまま逸脱を判定し続ける。
- D-P1-05-2: 長期 open 観測の出口を何週で強制するか / 選択肢: A. 8 週で proposal 化か RFC 起票 B. 12 週 C. 強制なし（expiry のみ） / 推奨: A — O-001 / O-002 は 12〜14 週で「観測」としての情報量が尽きている / 期限: 2027-01-16 の土曜ゲート（.3 の `expiry_rule` と render の印付けは先行し、「N 週で強制」の規約文は決定後に書く）。遅れると Ledger 節が毎週長くなる（WO-03: `unchanged` 6 → 10 行）。


### P1-06 コード構造の最後の窓（OllamaBackend・core 内層契約・規約の明文化）
- D-P1-06-1: scripts の「鏡」4 関数をどう扱うか（ADR-0109 の bare `python3` 方針の読み） / 選択肢: A `scripts/_bootstrap.py`（repo-relative `sys.path` 3 行）で `core.text_utils` / `core.stocktake` を直接 import し鏡を消す（ADR-0109 の読み替え: 自 repo の core は stdlib + numpy / requests のみで依存の床は動かない） B 鏡を許容し一覧を `.claude/verify.md` に台帳化 C script 側を正本にし src 側の `_check_rule_quality`（src 内呼び手 0）を消す / 推奨: B（鏡 4 関数を verify.md に日付つきで台帳化。A は scripts → core の結合を広げ、凍結後に core を触るたび scripts が追随対象になる — 既に 10 script が `sys.path.insert` で import し、scripts は pyright `include` / import-linter の外。A を採るなら同 PR で (1) .3 の AST 検査を「scripts / evals は `contemplative_agent` の `__all__` 名だけを import する」に広げ、(2) scripts を凍結集合（P1-01.4）に入れ、(3) `_bootstrap.py` を import して `uv run --no-sync` 起動へ移す script 名（現 `scripts/value_layer_due_check.py` / `retrieval_recall_measure.py`。後者は P1-04.7 で削除予定）を決定文に列挙する。C は src の rule-quality 検査を失う）/ 期限: 2027-01-16 の土曜ゲート。遅れると parity テストが鏡の数だけ増え続ける（現 `scripts/value_layer_due_check.py:97`、`retrieval_recall_measure.py:366,391,398`）
- D-P1-06-2: API 応答の `dict[str, Any]`（153 箇所、署名に `Any` 105 本）に DTO 境界を置くか / 選択肢: A `client._Body` の後段で `post_comment` / `get_home` / `get_post` の戻りを frozen DTO にする B 現状維持を verify.md に日付つきで確定する（`JSONValue` alias を作らない判断 verify.md:163 の延長） / 推奨: B（untrusted JSON の「形を信じない」規律（`is_valid_id(value: object)`）と緊張し、sibling 契約は `BackendResult` で閉じている。型強化は修理より能力動機に近い）/ 期限: 2027-01-16 の土曜ゲート（B なら凍結後も触らない）。遅れても害は小さい


### P1-07 アダプタと LLM 接点の堅牢性（障害時の挙動・予算・較正定数・来歴）
- D-P1-07-1: decision 面の無応答で何を払うか — 専用 breaker か timeout 短縮か / 選択肢: A decision 専用 breaker（3 失敗 / 120 s） B read timeout 300 → 60 s C 両方 / 推奨: B を先に（実測 p95 4.9 s で 60 s は 12 倍の余裕、新しい状態を持たない）。連続 fail-closed が週次の読みで見えたら A を足す / 期限: 2027-01-16 の土曜ゲート。遅れると backend 無応答の cycle ごとに最大 300 s を払い続け、feed が無言で空になる（`enforce_backend_null` 行で検知可）
- D-P1-07-2: pass-1 fail-open の着地点をどうするか / 選択肢: A skills ブロック無し（identity + axioms + rules） B 直近の judged 選択の再利用 C `num_ctx` 49,152 で全注入を維持（off-window で常駐 RSS / swap と comment 1 call の latency を 1 回測り `docs/evidence/adr-0066/` に凍結してから） / 推奨: A（新しい判定者も状態も増えず、「fail-open = 観測の継続」を満たす。B は過去の選択を現在に持ち込む。C は 16 GB で `num_ctx` 32k 常駐 3.4 GB（ADR-0112）の実測なしに決められない）/ 期限: 2027-01-16 の土曜ゲート。遅れると fail-open が comment / reply / post の無言 skip のまま続く（`budget_exceeded` 行/週で検知可）
- D-P1-07-3: Ollama 本体の導入・更新経路をどうするか / 選択肢: A アプリのまま自動更新を切り、更新は手動・セッション窓外で .11 の Ollama 節の手順に従う B Homebrew に移して `brew pin` で版を固定（P2-04.5 の `{{OLLAMA_BIN}}` 化と対） / 推奨: A（既定可。現行の plist はアプリ導入を前提にしており、入れ直しの手間と launchd テンプレートの変更が要らない。自動更新を切るのは決定を待たずオーナーが手で行う）/ 期限: 2027-01-30 の土曜ゲート。遅れると Ollama の更新が判定面（score4 の logprobs）・予算・同居の前提を黙って変え、計画外の版が境界表に事後でしか載らない


### P1-08 テストと CI の強化（macOS job・未モック LLM・順序依存・床・契約）
- D-P1-08-1: `uv.lock` を追跡して `--locked` にするか、床 + constraint の現状を ADR で正式化するか / 選択肢: A. lock を追跡し CI は `uv sync --locked`、更新は Dependabot か月次の人間 commit B. 現状を ADR-0109 追補で正式化し、release ごとに `uv lock` → `uv export --no-dev --frozen -o docs/evidence/release-vX.Y.Z/requirements.txt` の 2 行で固定版を残す（`uv.lock` は gitignore のまま）C. A + B / 推奨: B（本番機は 1 台で lock はローカルにあり、CI の fresh 解決は「ツール更新で壊れる」の早期警報として働いている。研究の固定版は export で再現できる）/ 期限: 11-14 の土曜ゲート（v2.13.0 の tag はこの決定の後の平日 11-16〜20、P0-06）。遅れると固定版が「ソースだけ」になり、再ビルド不能のまま DOI が切られる。
- D-P1-08-2: main に required check `verify` の branch protection を置くか / 選択肢: A. 置く（PR 経由のみ）B. 据え置き（直 push、CI は事後の読み値）と verify.md に明記 C. 保護は置かず `pre-push` hook で full verify を強制 / 推奨: B（可視 447 commit 中 merge 9 = 直 push が運用の形で、f89b28d の「判断役はローカルで verify を再実行せず CI の結論を読む」設計と整合。ただし判断を記録する）/ 期限: 2027-01-23 の土曜ゲート。遅れると「CI 赤の main」が無記録のまま存在しうる（壊れはしない）（`gh api …/branches/main/protection` は 403 で現状確認不可）。


### P1-09 ドキュメントの同期と欠落文書（数値・CYCLES・CONFIGURATION・glossary・llms）
- D-P1-09-1: 文書の言語方針をディレクトリ別にどこまで決めるか / 選択肢: A 現状維持（CLAUDE.md § ドキュメント言語方針の 3 行。論文読者が rfcs を要するなら `rfcs/README.md` に英語タイトル列を足すだけ）B ディレクトリ別の表（rfcs は日本語正本 + 英語タイトル列、各 README に英語 1 段落、ADR 追補・Note は en のみ正本）C rfcs / runbooks を全面英訳 / 推奨: A — 既存の 3 行で足り、読者は AI で symlink でも読める（旧 .18 は落とした、既定可）。英語タイトル列は論文化で rfcs を引く時に 1 回。A のもとでの ADR の運用規則: Status 行と `## Amendment` 見出し + 1 行要約は ja も同じ PR、Note 本文は en のみ。`enja_drift` は Status / 見出しの差分だけを数える（P1-05.5 の完了条件と同じ） / 期限: 2027-01-23 の土曜ゲート。遅れても文書の同期費用が増えるだけで機構には影響しない。
- D-P1-09-2: diagrams の鮮度規約に feed 側ゲートを含めるか / 選択肢: A 除外宣言（値層ループのみ）B 00 図に score4 gate + seed 選択を 1 ノード追加 C relevance 専用の 7 枚目を描く / 推奨: B — この 4 週で最大のゲート変更が地図から消えたままになるのを 1 ノードで防げる / 期限: 2027-01-23 の土曜ゲート（P0-02 完了後）。遅れると次のゲート変更ごとに「図未更新」指摘が再発する。
- D-P1-09-3: 非 macOS の扱いを宣言のみにするか cron 例を足すか / 選択肢: A 宣言のみ（macOS / launchd、他 OS は自前起動）B `config/cron/` の例を同梱 C 何も書かない / 推奨: A — 「制約で彫る」と整合し、B は能力拡大。旧 P1-14.7（`--print` + runbook の最小例）も落とし、P1-14 と「宣言のみ・cron 例は同梱しない」で統一 / 期限: 12-26 の土曜ゲート。遅れると .20 の宣言行が書けず、Linux 利用者が `install-schedule` で初めて非対応を知る。


### P1-10 セキュリティ: threat model・SECURITY.md・I/O 面の機械ゲート・鍵の所在
- D-P1-10-1: episode-log hook の正本を repo 同梱 `integrations/` に移すか harness に残すか / 選択肢: A `integrations/claude-code/hooks/` を正本にし harness 側はコピー（`harness-sync` 相当）、tests で固定 B harness `~/.claude/hooks/_episode-log-common.sh` を正本のまま公開版を手で同期 C 公開版を撤去し README は「harness の例」へのリンクだけにする / 推奨: A — 公開 repo の読者が検証でき、CI で境界をテストできる唯一の置き方（B は edca8cf 以来 1 か月半ずれたままの実績） / 期限: 2027-01-23 の土曜ゲート（.4 の着手前）。遅れると README:106 の案内通りに入れた第三者の hook が計器ログ（`weekly-pipeline-audit.jsonl` 等）を弾き続ける
- D-P1-10-2: `SECURITY.md` の受付範囲と「止まる」後の方針を何にするか / 選択肢: A 本体 + data repo takedown を 1 窓口（報告経路 = GitHub private vulnerability reporting + メール alias（GitHub アカウント不要）、受理通知 7 日以内・判断 30 日以内、受付台帳 = P3-05.14。兄弟は凍結なら対象外と明記） B 本体のみ C 受け付けない宣言（対象版を固定 tag に限る） / 推奨: A — DOI 付き公開物に窓口が無い状態を最短で閉じ、NOTICE の takedown 節（P3-05.14 (b)、SA-17）を正本として同じ文面を共有できる（`SECURITY.md` はリンクのみ） / 期限: 2027-01-23 の土曜ゲート。遅れると第三者が「absence が破れている」を伝える経路が無いまま v2.13.0 が引用され続ける


### P1-11 兄弟 repo の処遇（cloud / mlx / otel / rules）
- D-P1-11-1: cloud repo を維持・凍結・削除のどれにするか / 選択肢: A 維持 — P3-03 の大型モデル蒸留アーム（判定は gemma のままという混成条件を含む）を RFC に起票し、その RFC を cloud の Review-when にする B 凍結 — README に "Frozen as of contemplative-agent v2.12.0 (kit static PASS 2026-09-12). Not maintained."、`TARGETS` と skill の cloud 行を frozen、.4 .7 は実施しない C 削除 — B に加え本体の `CONTEMPLATIVE_DIALOGUE_PEER_MODULE` seam と `tests/test_cloud_egress_absence.py` の扱いを RFC で決める（GitHub repo の削除ではなく archive + 本体の seam の退役を指す。repo の削除は P1-11.1 の pin 先と P3-06.3 の参照を消す一方向の操作なので選択肢に含めない） / 推奨: B — 唯一の実験記録は 2026-04-21（main 2.0.0、n=1、$3–5）で以後 `docs/evidence/` に言及 0、対照実験計画が RFC 化されるまで維持の負荷（Protocol 変更ごとの文書更新と gate）だけが残る。削除は seam の退役 RFC を要し P1-06 の凍結窓と衝突する / 期限: 10-31 の土曜ゲート。遅れると v2.13.0 の release gate が「落ちて当然」文書（.3）と未検証既定（.2 e）のまま走る
- D-P1-11-2: mlx repo を凍結するか gemma で再計測するか / 選択肢: A 凍結 — README に "Frozen …; revisit when ADR-0067 reversal thresholds (mlx-lm #615/#884, #854/#883) are met"、`TARGETS` には残す（最も安い runtime 検査対象）、skill 行を frozen B 再計測 — gemma の MLX 重みで ADR-0064 と同じ測定を 1 日回し README を更新（重みの可用性は未確認 — 推測） / 推奨: A — mlx は「同じエージェント」を動かせない（gemma で蒸留した値層を Qwen が読む別インスタンス、.2 a）ので観察対象としての価値が薄く、反転条件は ADR-0067:146-161 に既にある / 期限: 11-14 の土曜ゲート（D-P1-11-5 の前。D-P1-11-5 の推奨理由が mlx の処遇を前提にする）。遅れると `/agent-run mlx` が本番と別モデルのインスタンスを「対話的用途」の名で起動し続ける
- D-P1-11-3: otel を routine use にして schema 追従義務を release gate に付けるか、v2.10.0 schema で凍結するか / 選択肢: A 維持 — ADR-0078 追補に消費計画（例: 土曜ゲートで事故日の trace を 1 回）、.6 と .8 を実施、正本 fixture を release gate に B 凍結 — README に "Frozen: converts the v2.10.0 schema (generation rows + verification + api). Newer row kinds (embed, decision) are exported as text_completion."、語彙対応表の正本は本体に戻す（.14） / 推奨: B — ADR-0078 に消費計画も Review-when も無く（見出し grep 0）、本体のどの文書も使い方として参照せず（`CLAUDE.md` 関連リポジトリ節に無い、ADR-0088:333-335）、ADR-0101 の基準では読み手の無い計器は不採択側。凍結しても本体の absence には触れない / 期限: 12-26 の土曜ゲート（D-P1-11-6 と同じ回）。遅れると 2026-10-07 以降 feed の判定ごとに書かれる decision 行が Jaeger 上で生成に化け続ける
- D-P1-11-4: 推論プロバイダへの本文 egress を ADR-0015 の「外部に観測可能な副作用」に数えるか / 選択肢: A 数える — ADR-0015 追補（.1。cloud の処遇に依らない）+ cloud を維持するなら CLI の `--auto` に明示 env（.7） B 数えない — README の「研究用途のみ」で足りるとする / 推奨: A — 凍結でも追補 1 行で済み、absence の例外が「人間が毎回明示する」形で機械に見える。P1-10 の threat-model の外部面表はこの分類を引く / 期限: 12-05 の土曜ゲート（P1-15 の着手週。同じ回の順は D-P1-11-4 → D-P1-15-2 → D-P1-15-1 で、P1-15 の cloud 真値の前提変更 D-P1-15-2 はこの分類を引く。.1 の ADR 追補と同じ PR）。遅れると P1-10.1 の外部面表と P1-15 の真値 judge（D-P1-15-2）が分類の無いまま文書と ADR になり、保守 script の egress（P1-10.14）が ADR-0015 の内か外か決まらないまま凍結判定に進む
- D-P1-11-5: 契約キットの runtime 段を出荷するか static で凍結するか / 選択肢: A 出荷 — mlx に `BackendProbe`、`--require runtime`、3 検査 B static 凍結 — ADR-0088 追補「runtime は sibling が必要になったら」、script に `--decision` target 0 件の注記 / 推奨: B — D-P1-11-1 / -2 で兄弟を凍結するなら runtime 検査の読み手が無い（ADR-0101）。`--decision` は実装が 0 件なので target が無いのは正しく、script がそれを言えば足りる / 期限: 11-14 の土曜ゲート（D-P1-11-2 の後。11-14 の決定の後、11-20 までの v2.13.0 の tag 前）。遅れると release notes の兄弟行が「static で何を検査したか」を言えない
- D-P1-11-6: rules repo を本体の較正依存先として維持するか vendoring するか / 選択肢: A 維持 + 消費契約 — tag `v0.2.0`（.10）を本体 runbook と `ipd-two-arm.sh` の既定 `BENCH_REF` が指し、rules README に「contemplative-agent の ADR-0090 が `--protocol paper --prompt-file` で消費する」契約を書き、rules repo に同じ契約の新 ADR-0006（ja 併記）を起票する。archive は本体が `amend-constitution` を retire する（P4-02 の終了手順）か bench を vendoring するまでしない（P4-02.5 の条件） B 本体へ vendoring — `benchmarks/prisoners-dilemma` を本体 `evals/ipd/` に写し rules は配布物のみに戻す C 現状維持 — path 依存のまま、tag 無し / 推奨: A — 本体の本番手順（憲法改正の承認）が依存する兄弟は rules だけで、B は本体の `requests+numpy` 床に scipy / statsmodels を足す（既定可。R1-SIB-01） / 期限: 12-26 の土曜ゲート（D-P1-11-3 と同じ回）。遅れると P4-02.5 の archive 手順が終了手順の最後の改正から計器を先に消す


### P1-12 承認ゲートの記録を「責任の行為」にする（approver・reason・却下本文・GOVERNANCE.md）
- D-P1-12-1: `adopt-staged --yes` を AAP 0005 とどう整合させるか / 選択肢: A `--yes` に `--reason` を必須化（0005 path (2) と同形） B `--yes` を `--adopt-names` 全件列挙の糖衣にして `stage-adopted-names` へ寄せる C 現状を「supervised coding-agent session の TTY 代替」として AAP 0005 に第 3 の例外を書き戻す / 推奨: A（最小変更で記録に人間の言葉が入り、憲法 runbook Step 4 もそのまま） / 期限: 2026-10-31 の土曜ゲート（憲法改正 due 前、P0-07 と同じ回）。遅れると 3 度目の憲法採用が理由無しの `-y` で記録される
- D-P1-12-2: 人間の裁定の証跡をどう人間由来にするか（`stage-*` 行と `gate_item` 行の両方） / 選択肢: A 人間自身がターミナルで `adopt-staged --adopt-names FILE --reject-rest` を打ち、`gate_item` も人間が `pipeline_audit.py --field approver=…` で打つ B FILE 先頭に人間が署名行を書き `approver` / `reason` に転記し、`gate_item` 行（deadcode / retire / docs 区分）にも同じ署名 FILE の経路で `approver` を及ぼす（`scripts/pipeline_audit.py:34-46` は任意の `--field` を受ける） C 現状（Claude 転記、`approver` は固定値。`gate_item` は Claude の転記のままで人間由来の証跡が無い） / 推奨: B（負荷を増やさず、audit 行と `gate_item` 行の両方に Claude の自己申告でない文字列が残る。`approver` の正本は .7 の Accountable operator 行、.1 の `approver` 欄はこの結論で実装） / 期限: 2027-01-09 の土曜ゲート。遅れても機構は壊れないが、モデルとして外に出すとき「named human sign-off」の実証にならず、`gate_item` の `decision` が人間由来と言えない


### P1-13 AI 判断役の権限境界と帰属表示の明文化
- D-P1-13-1: 本体 repo で判断役 AI の merge/push を認めるか / 選択肢: A 認める（保護クラスを本体語彙で列挙、admission と revert 撤回条件を転記、CYCLES.md を直す。条件: ADR-0080 の人間ゲートの範囲を追補（2026-12）（P1-03.8、12-21〜25 の PR）の 1 段落に入れ、AAP ADR-0005 / 0008 の例外節を同 PR で要求する） B 本体では人間 merge に戻す（CYCLES.md 現行どおり、harness 側に本体の例外を書く） C 認めるが push = 公開は人間（merge は保護クラス外の task output に限り判断役、push は人間。AKC ADR-0028 側に本体の例外を dated note） / 推奨: C を既定（熟慮: 権限の所在に触れるので推奨は材料、decision は人間が打つ）— オーナー原則「人間がオーケストレーター」と CYCLES.md:52 / :149「Every promotion stays human」、AAP 0005 / 0008 に整合し、A の根拠「09-15 以降 Revert 0」は 3 週の読みで one-run-not-evidence（D-P0-01-1）と同じ弱さ。A を採るなら上記条件を同 PR で。本体はエージェント自身なので保護クラスが広く、`config/prompts` / `.claude` / `scripts/weekly-*` と行動を記述する文書（.1）を明示する / 期限: 2026-12-12 の土曜ゲート（ゲート再配分）。遅れると GOVERNANCE.md（P1-12.7）が書けず、CYCLES.md の虚偽記述が AAP の lineage に残り続ける
- D-P1-13-2: Claude 実装 commit の帰属方式 / 選択肢: A `Co-Authored-By` trailer を harness テンプレで必須化（cloud と同形、GitHub 面に出る） B commit は常にオーナー名義（承認 = 責任）とし開示文だけ置く C A + 開示文 / 推奨: C（trailer は commit 単位の帰属、開示文は方式に依らず要る） / 期限: 2026-12-12 の土曜ゲート（D-P1-13-1 と同じ回）。遅れるほど遡及できない commit が増える（現状 443/447 に無い）
- D-P1-13-3: 外部 PR を受けるか / 選択肢: A Issue と fork は歓迎、PR は RFC / ADR 起票を伴うもののみ B PR は受けない（fork 専用） C 全部受ける / 推奨: A（#9 が既に来ており、ADR が要る変更の線を先に引けば貢献者の時間を無駄にしない。線は CONTRIBUTING の 1 段落 + proposal テンプレで示し、CoC は置かない — .5） / 期限: 2027-01-30 の土曜ゲート。遅れると #9 以後の貢献者に線を示せないまま PR が来る


### P1-14 CLI の残りの UX 整備（`.last_insight` の起点・テンプレート skills・installer の前提・`init` の Tier）
- D-P1-14-1: `install-schedule` を配布単位非依存に直すか「clone + `.venv` 前提」を明記するか / 選択肢: A. `sys.executable` + package data テンプレで描画（wheel 配布と整合）B. 前提を文書化のみ（現状維持、エラー文が段落を指す）C. A + B / 推奨: B を既定。A は P0-06 の配布単位（RD-29 / CU-27、11-07）が wheel を選んだ時だけ（決定前に A をコードに入れない）。C（`--print` 併用）は旧 .7 と共に落とした / 期限: 2027-01-30 の土曜ゲート（P0-06 の決定の後）。遅れると第三者の scheduling 導入の前提が書かれないまま v2.13.0 が引用される。
- D-P1-14-2: 購読確認を永続化するか、起動時 1 回のまとめ確認にするか / 選択肢: A. home に購読状態を永続化（確認済み・却下済みは再確認しない）B. セッション開始時に 8 件を 1 画面でまとめて 1 回確認 C. 現状維持（文書を実態に合わせるだけ — 確認される副作用の一覧は P1-09.10 の 1 表）/ 推奨: C。A は home に新しい永続状態 + 却下記録 = 能力で、影響は第三者の APPROVE 体験のみで本番 `--auto` には無い（旧 .1 は落とした）。冪等な副作用の再確認が「責任を取る行為」を薄める点は文書に書く / 期限: 2027-03-06 の土曜ゲート。遅れても本番（`--auto`）には影響なし、第三者の APPROVE 体験のみ。


### P1-15 relevance face の較正と face ループの昇格（RFC-0047）
- D-P1-15-1: t=0.3 を維持するか新母集団で再導出するか / 選択肢: A. 維持（Jev の狭い線で recall 最大の規則どおり） B. t=0.5（precision 0.75、gate 率半減、コメント 25 件/日をさらに減らす） C. 事前登録の規則（live の precision を下限に recall 最大）を新母集団に再適用し、その結果に従う / 推奨: C — 規則は妥当で変わったのは母集団。再適用の結果が A なら A（熟慮: 本番 gate の閾値に触れるので推奨は材料、decision は人間が打つ） / 期限: 2026-12-05 の土曜ゲート（同じ回で D-P1-11-4 → D-P1-15-2 の後。.2 の 3 回目の読みは次の identity adopt の前に先行させる）。遅れると adopt で domain が変わり、閾値と母集団の 2 変数が同時に動く。
- D-P1-15-2: 真値の既定を Jev にするか opus にするか / 選択肢: A. Jev 既定 + opus 代替（二段、版 pin） B. opus 既定（RFC-0047 原案、$19〜24 / 回） C. Jev のみ / 推奨: A（熟慮・前提変更: 閉じたホスト API を本番 gate の閾値 t を決める読みの既定の真値にする — ゼロ API の例外は研究ラベル付けのみ、≈$0.01 / 回、egress 分類は D-P1-11-4。推奨は材料で decision は人間が打つ）— pilot の実績（S35 / S36 とも Jev、≈$0.01）と閉じたホスト API（RFC-0040、MCA 2.3(b)）の消滅リスクの両方を台帳に書ける。真値 judge の交代は装置境界（P3-02 の regime 表に 1 行） / 期限: 12-05 の土曜ゲート（同じ回で D-P1-11-4 の後、D-P1-15-1 の前 — t を裁く読みの真値の既定を先に決める。.1 の台帳 PR はこの結論と D-P1-02-2（2027-01-09）を待つ）。遅れると台帳の真値列が実際に使った審判と食い違ったまま昇格先に書かれる。


### P2-01 北極星の読み値を機械化する（止まる・負荷・自己調節・一致率）
- D-P2-01-1: 「負荷」を何で測るかを ADR-0080 の dated note に書くか / 選択肢: A 裁定件数のみ（既にほぼ 0） B 3 系列（裁定・読み量・ゲート外作業）+ 起票 / 修理数を並べる C 所要時間のみ / 推奨: B — A では完成判定が反転する（裁定 0〜2 件なのに毎週 repo を変更している） / 期限: 2026-11-28 の土曜ゲート（追補（2026-11）の材料）。遅れると .5 の列が和集合のまま残り（初版は 11-28 の週に和集合の列で merge する）、RFC-0048 等の「負荷→0」提案の審査基準がぶれる（→ P2-02）。
- D-P2-01-2: 推奨↔裁定一致率 100%（45/45）に対する監査をどの形で 1 回行うか / 選択肢: A ADR-0099 Review-when どおり保存済み `gate_item` を遡る 1 回の lens 監査（監査の n = 過去 `gate_item` から引く行数を決定文で固定（候補: 直近 8 週の全行 45/45）、盲検 = `recommendation` を伏せて再裁定し一致率を比べる — 45/45 は同一セッション・同一材料の構造バイアス（RFC-0010:72、ADR-0099:168）なので比較対象の無い「~100%」は検定できない。一致率の区間は P2-01.9 の規則） B blind-first 週（先に裁定、後で推奨）を 2 回入れる C 現状を「Claude 推奨 + 人間追認」として ADR に明記し監査しない / 推奨: A + `gate_item` に `recommender=<model-id>` を足す（VL-36「記録にモデル名が残らない」を解く — 研究記録として判断主体のモデルを残す。第 4 章の決定も `category=roadmap` の `gate_item` で同じ監査母集団に入れる。B は材料なしの裁定を増やす） / 期限: 2026-12-12 の土曜ゲート（.1 の一致率が出た後）。遅れると RFC-0010 / ADR-0099 の Review-when が発火済みのまま死文化。
- D-P2-01-3: 「代謝が止まっていない」下限をどこに置くか / 選択肢: A 8 週で adopted 0 ∧ archived 0 ∧ identity 更新 0 → 定常宣言 B 同条件で終わり方の検討イベントを起票（→ P4-01） C 下限を置かない（入口 0・出口 0 を自己調節と読む） / 推奨: B（熟慮: 代謝の下限は層 2 の読みに触れる） — A / C は「止まった」と「自己調節」を区別できない / 期限: 2026-11-28 の土曜ゲート（追補（2026-11）の材料。P4-01 の検討イベント（D-P4-01-1、12-19）がこの下限を参照する）。遅れると検討イベント B（D-P4-01-1）の下限が無く、.5 の `self-regulating candidate` 宣言を機械で出せない。
- D-P2-01-4: 最終ゲート日の行を PIPELINE-STATUS にどう表示し、watchdog の fail 行を出すか / 選択肢: A 表示のみ（.6） B 表示 + D-P4-01-3 の N 週を超えたら watchdog が fail 行を出す / 推奨: B（自動停止は入れない — P2-04 と同じ方針。停止の是非と N の値は D-P4-01-3（12-19）に 1 本化し、本決定は表示形式だけを持つ） / 期限: 2027-02-13 の土曜ゲート。遅れると .6 の「N 週前」表示に基準が無く、オーナー不在が公開面で healthy と読まれ続ける。
- D-P2-01-5: ロードマップ項目の実装 commit を何で項目に結ぶか / 選択肢: A 束ごとに RFC を起票（`origin: roadmap`、P2-01.5 の RFC 数は roadmap を除外） B 起票しない。commit trailer `Roadmap: P0-03.2`（P1-13.3 の語彙に追加）で結び、lease は claims の自由ラベル。task-triage loop に回す S / repair の項目だけは `origin: roadmap` の draft を起票し（P2-01.5 の RFC 数からは除外）、それ以外はオーナーの対話セッションで行う C 何もしない / 推奨: B（既定可: 台帳の件数を増やさず、`freeze_reading.py` が `Roadmap:` trailer で別系列に出せ、P1-01.7 の照合が機械で結べる。`claims.py` の ID 形式は harness 側で未確認） / 期限: 10-31 の土曜ゲート。trailer は 10-10 の作業から暫定で付ける（A / C なら以後止め、付いた trailer は残す）。遅れると暫定の trailer を続けるか止めるかが決まらず、P1-13.3 の trailer 表と `freeze_reading.py` の別系列が定まらないまま 11 月の実装 PR 群が入る。


### P2-02 Claude Code 依存の決着（headless 週次セッションの位置づけ）
- D-P2-02-1: headless `claude -p` を機構層と見なすか作業環境と見なすか / 選択肢: A 機構層の一部と認め「再現には Claude Code サブスクリプションが要る」を README / CONFIGURATION に明記しモデル ID を記録（.3） B 作業環境と位置づけ、無人チェーンは決定論 instruments のみ（.2）にして観察文書の合成は土曜の対話セッションへ戻す C 観察文書の合成を gemma（ローカル）で 1 回 shadow 計測してから決める（代替計測、能力拡大ではない） / 推奨: A を暫定（現に 7 週回っており、B は土曜の読み量を増やし P2-06 と逆行）、ただし .1 の二分で「無人の読み手は負荷系列に数える」を条件にする。C は RFC-0041 の opus 対照で「複数行の一般化は gemma に不可」が出ている（CONTEXT-FROM-CHATS §1）ので期待薄 / 期限: 2026-11-28 の土曜ゲート（追補（2026-11）の材料）。遅れると P2-01.3 の負荷系列に headless セッションを含めるか決まらず、RFC-0048 の「負荷→0」審査が文言頼みになる。


### P2-03 私的ハーネス依存を閉じる（claims.py・release skill・パス・inbox）
- D-P2-03-1: `claims.py` spawn と task-triage loop を repo に取り込むか文書化に留めるか / 選択肢: A 両方取り込む（claims を repo 内 stdlib に移植、triage は `docs/` に契約を書く） B spawn 記録だけ frontmatter に取り込み（.2）、claims / triage は (B) 文書化 C 現状維持（全部 harness、CLAUDE.md の記述のみ） / 推奨: B — 系譜は公開 RFC に残れば帰属（ADR-0050）が閉じ、triage は Claude Code セッションそのものなので取り込みは D-P2-02-1 の決定に従う / 期限: 2027-02-13 の土曜ゲート（D-P2-02-1（11-28）の後）。遅れると「harness 無しで何が動くか」が文書に無いまま 2027-Q2 に入る。


### P2-04 無人チェーンの検知面と停止手順（watchdog・sync・ロック・ディスク・ドリル）
- D-P2-04-1: sync-data をどの経路で回すか決める（launchd 日次か distill 後処理か） / 選択肢: A `install-schedule` 管理の launchd 日次（現状 05:30 を正本化、ADR-0010 は partial supersede） B ADR-0010 原文どおり distill の後処理に戻す（plist 不要、distill 失敗時は sync も止まる） C 手動 plist のまま文書化のみ / 推奨: A — distill の成否と独立に公開ミラーが動き、`--uninstall` で止まる（ADR-0010 は .1 の partial supersede 1 本で改める） / 期限: 2027-02-06 の土曜ゲート（P4-02 dry-run の前）。遅れると Mac 再構築時に公開ミラーが黙って止まる（.23 の再構築 runbook の sync-data 段が決定値を引く）
- D-P2-04-2: backup を日次にするか 7 日損失を許容するか / 選択肢: A 日次 backup（ローテは週 1 のまま分離） B 週 1 のまま「最大 7 日の episode log 損失を許容」と runbook に明記 C distill 直後に backup を連結 / 推奨: A — episode log は唯一の原資料で、コストは git push 1 回/日 / 期限: 2027-02-20 の土曜ゲート。遅れても現状維持（損失窓 7 日）
- D-P2-04-3: insight / distill-identity に `.run.lock` の非ブロッキング確認を足すか / 選択肢: A 足す（セッション中なら理由コード付きで延期） B 足さず、時刻設計（insight 08:00 / chain 09:00）で分離したまま表とテストで不変量を固定 C どちらも blocking に / 推奨: B — 現状は時刻で分離済み。.9 の `late_minutes` で衝突が観測されたら A へ / 期限: 2027-03-06 の土曜ゲート（.9 の `late_minutes` を 4 週読んだ後。揃わなければ 2027-03-13 の空き枠へ繰り越す）。遅れると insight 08:00 / chain 09:00 の衝突が無記録のまま続き、`IDENTITY_WINDOW_TOO_SHORT` の延期理由が audit にしか残らない


### P2-05 公開に出す責任の接点（2 層公開・承認記録の投影・値層の縦断）
- D-P2-05-1: 無人 LLM 文書の公開をどう扱うか / 選択肢: A 2 層（`reports/analysis/` は土曜に人間が promote） B 無人公開を認め決定論スキャンだけ置く C 2 層 + スキャン / 推奨: C（人間の言葉が公開 commit に残り、スキャンは最後の防壁。負荷は週 1 コマンド） / 期限: 2026-12-12 の土曜ゲートで決定、2027-Q1 実装。遅れると無人 LLM 文書が人間の言葉なしで公開され続け、P0-03 級の漏洩時に防壁が無い
- D-P2-05-2: 却下台帳の公開範囲 / 選択肢: A 名前・日付・recommendation・decision・reason code・hash（本文なし） B 件数のみ（DATACARD に「却下は非公開」と明記） C 本文も CC0 で公開 / 推奨: A（README の中心主張を検証可能にし、本文は `.rejected/` に非公開保持。observation-over-steering には抵触しない — 記録の公開であって注入ではない） / 期限: 2027-02-27 の土曜ゲート。遅れると論文の数字が公開データから引けない
- D-P2-05-3: 「人間の言葉として残す接点」を固定するか / 選択肢: A 3 点に固定（値層への書き込み = adopt / archive / baseline、公開への commit = rfcs と reports/analysis、計器の建立・撤去 = ADR-0101）し ADR-0080 追補（2026-11、P1-03.8）に 1 段落で書いて CLAUDE.md §北極星を同 PR で同期する B 固定せず都度判断 / 推奨: A（RFC-0048 層 1 のような移行のたびに「これは人間の仕事か」を再議論しなくて済む。別番号の追補は振らない） / 期限: 2026-11-28 の土曜ゲート（追補（2026-11）の材料）。遅れると P2-07 の層 1 決定（D-P2-07-1、12-05）が基準なしに行われる


### P2-06 週次ゲートの読み量を減らす（carried・陽性のみ・多軸 join）
- D-P2-06-1: 多軸 join をどこで行うか / 選択肢: A staging 時に code が sidecar に書く（`.meta.json` 拡張、`adopt-staged` が印字） B ゲート時に `scripts/` が別ファイルを join して briefing に出す C 両方（sidecar は段が見たもの、scripts は週次計器の値） / 推奨: C — 近傍と段の判定は staging 時にしか正確に取れず、reply_rate と novelty は週次ファイルにしか無い / 期限: 2027-02-13 の土曜ゲート（insight 継続が決まった場合）。遅れると 08-26 追補 §B の「見分けられる」が実装上満たされないまま入口の議論が続く。


### P2-07 RFC-0048 出口の自己維持と knowledge の保持方針
- D-P2-07-1: 層 1（決定論 archive）を「決定論の自動退役 + 事後報告 + 復元権」として無人実行するか、候補提示までに留めるか / 選択肢: A 決定論の自動退役 + 事後報告 + 復元権（無人実行し、毎週のゲートで件数・名前を報告、復元は人間。前提条件: ADR-0080 の追補（2026-11）の草案の段落（境界の例外文、CLAUDE.md §北極星と同 PR）+ ADR-0105 の partial supersede（.5 / R1-NS-01）、audit source は無人専用の新語（例 `archive-l1-unattended`）、AAP ADR-0005 への dated note は P3-06.7） B 候補提示まで（層 2 に留める: 現状 + 機械の定型説明。層 1 は人間の `adopt-staged --archive-names` 呼び出し） C 退役を止めて store を凍結（RFC-0042 review-when 側） / 推奨: A（value-steering-risk・熟慮: ADR-0080「Not gate dissolution」境界に触れるので、可逆・決定論・報告義務の 3 条件だけでは gate 省略の理由にならない — 境界の理由は attribution の錨（ADR-0080:189-196）であり、A は .5 の追補（2026-11）の草案の段落 + ADR-0105 partial supersede がオーナーの言葉として `gate_record` に残った場合のみ。層 1 の対象は全履歴 0 回選択（judged 露出 ≥ 600）で、復元権は人間に残り（RFC-0048 層 3）、反証条件が事前登録済み。「事後承認」とは呼ばない — 承認は責任の行為で、実行後に人間ができるのは復元だけ） / 期限: 2026-12-05 の土曜ゲート（.5 の境界草案の後）。遅れると毎週 1 件の最も定型な裁定が人間の手に残り、P2-01.5 の「(i)=0」が成立しない。
- D-P2-07-2: 飽和の判定軸と窓をどう置くか / 選択肢: A 入口件数のみ（現 review-when） B 3 軸 × 4 週窓（.2） C 定義を置かず人間判断 / 推奨: B（熟慮: 飽和は出口の trigger に触れる） — A では RFC-0042 と 0048 が互いを待つ dead-band が続く / 期限: 2027-02-27 の土曜ゲート（D-P2-07-1 の後）。遅れると .1 の設計が入口件数だけを見る review-when のまま進む。
- D-P2-07-3: live プールの保持方針 / 選択肢: a 現状維持（no-GC、50 MB トリガ） b 年次シャード c dedup 母集団を全 live に広げる（ANN or 行列読み、ADR-0108 Review-when） / 推奨: a を明文化し、年齢分布の読みを 2 期見てから b / c を判断（c は機構の拡大で、再入の実害が `skipped_known` 増加以上に出ていない） / 期限: 2027-02-27 の土曜ゲート。遅れても当面の実害は無い（7.5 MB、トリガ 50 MB）。


### P3-01 研究問いの操作的定義（研究問い ADR・統計方針・Q4 の採否）
- D-P3-01-1: 研究問いに Q4「承認ゲートの負荷と価値層の legibility」を加えるか / 選択肢: A. 加えない（3 問のまま、FLIP 型の対照実験 P3-03 に投資） B. 4 問目として追加（「人間が最終判断を持つ自己改正ループは何を可監査にし、何を費やすか」） C. Q1 を Q4 に置換 / 推奨: B — 最も厚く記録されているのはゲート（82/547、6/11、2/4、推薦↔裁定の一致率 ADR-0099:167-169）・計器の建立／溶解（ADR-0101）・オペレータ負荷（ADR-0080 の 08-26 追補 §A）であり、オーナーの主関心（harness 層・組織ガバナンス）と AAP の position paper 2 本に直結する。Q1〜Q3 は捨てない（否定的結論も結晶化の対象） / 期限: 12-12 の土曜ゲート（.1 の起票前。ゲート再配分で 11 月から移動）。遅れると ADR が 3 問で固まり、P3-06 の論文種別・投稿先の判断も止まる。
- D-P3-01-2: 評価層（ADR-0089）を研究証拠から除外するか、研究用に拡張するか / 選択肢: A. 除外し「開発用回帰ゲート」と書く（ADR-0089 側は P1-04.10 が持つ 1 本の追補の 1 段落） B. golden を ≥50 件に拡張し local judge arm を併設 C. 現状維持（位置づけ未記載） / 推奨: A — 12 件・2–1 margin・cloud judge では弁別力が無く（`docs/evidence/adr-0089/README.md:152-153`）、拡張は計器成長（ADR-0101 の溶解義務と逆）かつ cloud judge がゼロ API 前提に反する / 期限: 2027-02-06 の土曜ゲート（D-P1-04-3 と同じ回 — eval 層は何のためにあるかの両面。.1 の起票は先行し、ADR-0089 の追補はこの決定後に P1-04.10 の 1 本に段落として書く）。遅れると読者が `evals/` を「憲法の行動評価」と誤読する余地が残る。


### P3-02 装置の境界表と縦断記録の再構成（regime・研究ログ・.notes の昇格）
- D-P3-02-1: 「縦断分析」文書をどう扱うか / 選択肢: A. `agent-diachronic-analysis.md` を「initial 14-day analysis」と改題し DATACARD の記述を合わせる B. 最終版の一部として月次縦断サマリ（評価語彙なし、ADR-0099 様式、境界線入り。実装は P2-05.5 の value-layer 月次 1 ページ）を新設し A も行う C. 現状維持 / 推奨: A を今、B は最終スナップショットの定義（D-P4-02-2）が決まってから — B は wind-down の成果物なので終了設計と同じ判断で決める / 期限: 2027-02-20 の土曜ゲート（この回は A だけを決め、B は D-P4-02-2（2027-Q2）と同じ回。A の改題作業は .2 として決定前に行う）。遅れると DATACARD が「long-arc」を名乗ったまま DOI 版（P3-05）に固定される。


### P3-03 対照条件（IPD の床・プラセボ憲法・旧版・Care 面・2 体目の判断）
- D-P3-03-1: dialogue 二アーム（Care 計器・環境対照）を走らせるか / 選択肢: A. 走らせない（IPD + プラセボで Q1 を閉じ、Care は「未測定」と論文に明記） B. Care 専用（distress seeds、shadow vs live）だけ走らせる C. 環境対照（憲法あり / なし）も同じ装置で走らせる / 推奨: B — Care は機構ゼロ・計器盲目で「働いているか誰も答えられない」状態を、本番ループに触れず 16GB 窓外の 1 実験で解消できる; C は D-P3-03-3 の結果次第で追加 / 期限: 12-26 の土曜ゲート（D-P3-03-3 は 2027-02-20 に移ったので C の追加はその回で判断）。遅れると論文の限界節が「Care 未測定」のまま固まり、D-P3-07-1 も根拠を欠く。
- D-P3-03-2: AILuminate 面を退役するか、ローカル judge で置換するか / 選択肢: A. 退役（runbook から外し FLIP の評価に委ねる） B. ローカル refusal セットで置換 C. cloud judge のまま常設 / 推奨: A — 未較正・第三者 API 送信・repo 内に手順無しで、論文の安全面は FLIP が同じベンチを持つ / 期限: 2027-02-20 の土曜ゲート（10-31 due の改正ゲートでは AILuminate 面を走らせない暫定注記を runbook に 1 行先に置く。遅れると「任意の探索面」が再び手で走る）。
- D-P3-03-3: 「憲法なし」の本番対照を 2 体目で置くか / 選択肢: A. 置かない（対照は IPD・プラセボ・dialogue に限定し論文に明記） B. dialogue で代替（D-P3-03-1 の C） C. 第 2 アカウントで 2 体目を立てる / 推奨: A（B は D-P3-03-1 で検討） — C はゲート負荷を 2 倍にして北極星 A（負荷 → 0）と逆行し、ToS も未検討 / 期限: 2027-02-20 の土曜ゲート（熟慮 ≤ 3 / ゲートの配分で 12-26 から移動。D-P3-03-1 の結果を見てから）。遅れると RF-02 型の実験設計が宙に浮く。
- D-P3-03-4: value layer を cloud モデルに送る実験（(b)(c)、AILuminate）を許すか / 選択肢: A. 許さない B. 実験限定で許す（RFC に前提変更の節、本番ループと分離、送信内容を列挙） C. cloud 兄弟 repo の処遇（P1-11）と同時に決める / 推奨: C — 同じ前提（cloud に価値層を出す）の判断なので一度に決める / 期限: 2027-02-20 の土曜ゲート（D-P1-11-4 = 12-05 の egress 分類の結論を前提に、D-P3-03-2 と同じ回）。遅れると (b)(c) の RFC が前提変更の節を欠いたまま起票される。


### P3-04 identity・憲法の版履歴と縦断計器（history・CHANGELOG・drift・複利）
- D-P3-04-1: 版履歴の置き場を決め ADR-0030 と整合させる / 選択肢: A data repo `history/`（ADR-0010 の原案、データセット単体で閉じる） B 本体 `docs/evidence/` のみ C 両方（data が正、evidence は ADR からの link） / 推奨: C。ADR-0030 の撤回理由は identity.md 内の sub-addressing で、ディレクトリ単位の 1 責務は保てる。同じ回に「ADR-0030 の前提文（`:33`「ADR-0020 (pivot snapshots) provides full-text identity replay」— .1 の保持方針で崩れる）を partial supersede する ADR を起こすか」も決める（D-P1-03-1 の暫定基準 = 前提変更は新 ADR か partial supersede） / 期限: 10-24 の土曜ゲート（.2 / .3 の data repo 側の実装（10-31 の週）の前。本体側の書き手コードは決定前に書ける）。遅れると .2 / .3 が置き場未定のまま 10-31 の週に入り、4 版目も snapshot と git 頼みになる。
- D-P3-04-2: snapshot の保持方針を決める / 選択肢: A kind 別（distill のみ上限） B 上限撤廃（100 件 28 MB、年 100 MB 増） C コード不変・DATACARD に「直近 100 run」と書く / 推奨: A（C は「bit-for-bit」の約束を後退させ、B は data repo を肥大させる） / 期限: 10-17 の土曜ゲート（`amend-constitution_20260809…` が公開木から消える推定日 2026-11-01 より前）。遅れると 08-09 の参照 snapshot が `rsync --delete` で公開木から消える。
- D-P3-04-3: identity 蒸留の入力を憲法と同じ live に揃えるか / 選択肢: A 現状維持（raw のまま、理由を ADR に記録 — .14 (a)） B live に揃える（P3-02.1 に境界行、identity ゲート前に regime 行つきで実施） C 両方を 1 回ずつ走らせ cosine を読んでから決める / 推奨: A（既定可: 現状維持 + 理由の記録。B は値層の生成器への介入 = P3-07.1 チャネル (5) として value-steering-risk で審査、C は計器成長） / 期限: 2027-01-30 の土曜ゲート（10-31 は 5 件で満席。.14 (a)(b) の記録は決定前に置く）。遅れると P3-06.4 の束の入力 pattern 集合（`source_ids`）が閉じた行を指す理由が未記録のまま次回 identity ゲートを迎える。


### P3-05 公開データセットの研究再利用性（DATACARD・schema・DOI 版・HF・再現ガイド）
- D-P3-05-1: データセットの版を (a) いつ切り (b) 不変の DOI 版に何を入れるか / 選択肢: (a) A 月次 `vYYYY.MM` B コード minor release ごと + 憲法改正 due 直前 + 最終版（規則 1 本。旧 D-P4-01-4 をここに統合） C 最終版のみ; (b) A tree 全体（現状） B owner-authored 面のみの curated zip（`reports/comment-reports/` と `reports/analysis/` を除く、GitHub 連携を切る） C tree 全体だが deposit 用コピーでは Context ブロックを `[see GitHub <commit>]` に置換（Internal note / Output は残す） / 推奨: (a) B — 論文が引く版がコード版と 1 対 1 になり release runbook に載る（論文 cutoff への適用は P3-06.3 の完了条件、2027-Q2）; (b) C — 縦断記録の完全性と不変面の責任を両立（deposit 作成手順は P0-06 の release runbook。B / C なら最初の新版より前に data repo の Zenodo–GitHub 連携を off、P0-06.6 段 (8)）（熟慮: 不変の DOI 版の中身は後から変えられない一方向の選択） / 期限: 11-14 の土曜ゲート（v2.13.0 の tag（11-16〜20）の前。データの次版は 12-05 のゲートの後なので順序は保てる）。遅れると論文が引ける版が 2026-06-17 のまま、または次版が tree 全体で固定される。
- D-P3-05-2: 公開済みの第三者由来テキストの再掲根拠・撤回の受付と実行（面 × 対象 × 手段）をどう置くか（撤回ポリシーの正本。旧 D-P4-03-2 をここに統合、D-P0-03-3 の逐語 span の扱いは同じ回に決める） / 選択肢: A 規約条項（+ 引用・情報解析の法定例外、個人データの分類 = .14 (a) の 3 行）を根拠として引用し、連絡先・手順（.14 (b)(c)）を置く B 新規分は id + 要約に縮め、既公開分の履歴は D-P0-03-1 に従う C 現状維持（再利用者責任） D `**Context:**` を公開面から外し Internal note / Output のみ公開（Context は非公開 sidecar、post id で参照） E 抑止リスト運用（.19）で依頼ベースに除去・置換する; 付随: 元投稿が平台側で削除された場合は .14 (c) の 3 択（推奨 A 反映しない + B 依頼ベース）、名指しされた運用者の訂正依頼は同じ窓口（.14 (d)） / 推奨: A + E（A の手順の実行経路として E。規約が明示的に許さない場合は (ii) の法定例外を根拠に Context を要約 + id に縮める）（熟慮: 第三者の権利と縦断記録の完全性の両方に触る） / 期限: 11-21 の土曜ゲート（公開データの版の前。P0-03.9 の逐語重なり測定 / D-P0-03-1 / D-P0-03-3 と同じ回、P1-07.19 の再読台帳の初回行の後）。遅れると不変版に根拠の無い第三者本文が固定される。
- D-P3-05-3: export 時に `id` 列を付与するか / 選択肢: A 付与（sidecar と同じ 12 桁） B 導出式のみ DATACARD に書く / 推奨: B を今、A は「export 境界は raw と同形」（`export-patterns-jsonl.py` docstring）の例外として ADR 1 行で / 期限: 2027-02-27 の土曜ゲート（.4 の `--describe` と同時。遅れると DATACARD の導出式だけが先行し sidecar との照合テストが書けない）。
- D-P3-05-4: `patches/`（MIT diff）を公開 tree に残すか / 選択肢: A sync 除外（本体 `docs/evidence/` へ） B 残して NOTICE に MIT とキュレーション注記 / 推奨: A。「data, not code」の自己定義と CC0 の単一性（`_gc_trash/` の書き換え前 skill は D-P0-03-2 と P0-03.7 で済み、この決定には含めない） / 期限: 12-05 の土曜ゲート（次の版 DOI（.12）の前）。遅れると次の版 DOI に diff が入ったまま固定される。
- D-P3-05-5: graph.jsonld の HF ライセンス（CC BY 4.0）を repo / Zenodo の MIT に揃えるか / 選択肢: A HF card を MIT に B repo 側に dual を明記 / 推奨: A。同一バイト列に 1 条件 / 期限: 11-14 の土曜ゲート（D-P3-05-1 と同じ回、.2 の release runbook と同時）。遅れると同一バイト列の graph が HF と Zenodo で別条件のまま v2.13.0 の DOI に固定される。
- D-P3-05-6: 2 世代テンプレートが同居する store（4 件の loop 型 4,329〜6,913 B、`fluid-` / `dynamic-` 名、他 49 件は 1,286〜2,720 B）をどうするか / 選択肢: A 現行テンプレートに書き換え（ゲート経由） B 例外として P3-07.1 の介入チャネル登録表 ADR の (10) 行に dated 実例として記録（別の ADR は起こさない） / 推奨: B。書き換えは所有者の値層介入で P3-07 の介入チャネル登録表の対象（2026-07-10 の clean rewrite が前例、`_gc_trash/` に原本 10 件） / 期限: 2027-03-06 の土曜ゲート（D-P3-07-1 = 2027-02-13 の後）。遅れると 2 世代が同居する store が無注記のまま DOI 版に固定され、読者が 4 件を所有者の手書きと誤読する。


### P3-06 論文・FLIP 供出・AAP への書き戻し・哲学読みの計器
- D-P3-06-1: 論文の主題と種別を決める / 選択肢: A harness 層の責任構造（ゲート縦断 7 か月、AAP companion、SSRN + Zenodo） B 3 問の empirical / dataset note（P3-01 / P3-03 の読み後） C FLIP 側論文への供出のみ / 推奨: A を先に起票し、B は 2027-Q1 の読みで判断、C は A / B と並行の供出であって投稿先ではない / 期限: 2027-02-13 の土曜ゲート（D-P3-07-1 と同じ回。熟慮 ≤ 3 / ゲートの配分で 12-19 から移動）。遅れると P3-05 のデータ最終版と .3 の固定が決まらない。
- D-P3-06-2: FLIP に渡す束の範囲を決める / 選択肢: A 4 版 + LINEAGE のみ B + shadow 合成 + 11 プリセット + 本体の探索的読み C + 公理 / ルール分離案 / 推奨: B（memo §提示戦略「実装観察として提示」。C は P3-07 の A / B / C 決定後） / 期限: 2027-03-06 の土曜ゲート（P3-04.2 / .3 / .12 の完成後）。遅れると FLIP の比較表が第 1 改正版で止まったまま。
- D-P3-06-3: 「読んで返信しない」分岐を機構に足すか / 選択肢: A 足さない（記録のみ） B RFC で code の判断面として起票（score4 の後段に「沈黙」enum。capability-growth: 新しい判定面の追加で、採るなら ADR-0056 の明示 supersede と第 5 章での審査を要する） C identity テンプレの沈黙許可文を戻す / 推奨: .9 の 4 週読みまで A（熟慮: 価値層とゲートの読み値に触る決定。推奨は材料であり、裁定は人間が `gate_item` に書く）。C は所有者による価値操舵なので除外 / 期限: 2027-03-06 の土曜ゲート（.9 の読み 4 週後）。遅れると .9 の 4 列が読み手の無い計器として materials に残る。


### P3-07 「空性のみ公理」案と価値層への介入チャネルの決定
- D-P3-07-1: 「空性のみ公理・三原則をルール化」案をどの形で扱うか / 選択肢: A. やらない（現状維持・観測継続、FLIP には観察として返す） B. 第二エージェント／別 preset として実装（`--constitution-dir` + `--rules-dir`、rules 本文は論文 verbatim 条項に限り所有者パラフレーズ禁止、IPD two-arm + shadow を同じ床で回してから比較; 前提変更 = 2 体目、D-P3-03-3 と連動） C. まず計器として、shadow 系列の generator / corollary 因子分解を数回分読み「空性が他 3 原則を生成する」仮説の判定基準を先に置く / 推奨: C → 判定後に A か B — 本番で行うと (i) 三原則が改正不能・gate 外・shadow / IPD / eval の対象外になり「所有者の固定指示」に変わる（ADR-0097:414-417 が退けた形）、(ii) 実験途中（第 3 改正後。`.approval-join-state.json` の `unchanged_since` 2026-08-28 は hand-edit 検知器の未照合集合 0 件がその日から継続 = 手編集なしの読みであって値層の静止ではない — 静止・漂流の読み値は P2-05.7 の変化系列: identity は 09-12 に採用、skills は 09-12 / 09-19 に 57 → 53）で価値層を 2 変数同時に動かす（ADR-0056 / runbook「一度に一つ」）、(iii) 改正可能性の配分が反転し三原則が物象化する（論文 L167 の裏返し）; FLIP メモ自身も「根拠は Moltbook 数値だけでは弱い」「数サイクル実験後に提示」としている / 期限: 2027-02-13 の土曜ゲート（RFC-0012 の shadow 読みが 10-31 due の改正ゲートで消費された後。D-P3-06-1 と同じ回。熟慮 ≤ 3 / ゲートの配分で 12-19 から移動）。遅れると FLIP への返答が根拠無しのまま、または案が改正ゲートに紛れ込んで価値層の変数が 2 つになる。


### P4-01 終了判断の検討イベントと判断役を予約する
- D-P4-01-1: 検討イベントをどれにするか / 選択肢: A 研究層 3 問の公開の答えが出揃った時のみ B 値層の採用が 8 週連続 0（D-P2-01-3 の下限、材料は P2-01.5 の出力） C Moltbook 到達不能 7 日（P2-04.4 の watchdog 行） D A〜C のいずれか（OR。人間の再読台帳 P1-07.19 に平台の規約改定・閉鎖告知の行が書かれた時も候補 4 つ目として同じ段落に置く — 停止は含意しない） / 推奨: D — 「検討セッションを開く」だけなので誤発火の害が小さく、1 条件に賭けた RFC-0006 の失敗（12 回素通り）を繰り返さない / 期限: 12-19 の土曜ゲート（追補（2026-12）の PR は 12-21〜25）。遅れると第 5 層が永久に未着手のまま
- D-P4-01-2: Moltbook 閉鎖時に移植しないと決めるか / 選択肢: A 移植しない（終端、新インスタンスは新 repo） B SNS Protocol を今作り移植可能にしておく C 決めない / 推奨: A — 縦断記録は Moltbook 1 つで閉じ、Protocol は使わない備え（Goodhart 的な能力拡大） / 期限: 12-19 の土曜ゲート（追補（2026-12）、D-P4-01-1 と同じ回）。遅れると閉鎖時に場当たりの移植議論になる
- D-P4-01-3: オーナー不在（ゲート不在）N 週で装置を止めるかと N の値を決める / 選択肢: A 止めない — 承認済み値で継続を正当と宣言し、ゲート不在 N 週を P4-01.1 の検討イベントに加える B N 週で機構が read-only 化（自動） C 書かない / 推奨: A、N = 4 週（熟慮。決定文に N を数値で書く。停止の是非と N の値はこの決定に 1 本化し、D-P2-01-4 は PIPELINE-STATUS の表示と watchdog の fail 行だけを持つ）— 止める判断は責任の行為で人間に残す（BRIEF §3）。B は自動停止の導入 / 期限: 12-19 の土曜ゲート（追補（2026-12）。GOVERNANCE.md の節は P1-12 の後に書く）。遅れると .5 の operator unavailability 節が書けず、不在 N 週の扱いが AAP 0008:82-87 と未対応のまま 2027 に入る


### P4-02 wind-down runbook（手順のみ・発動条件を持たない）
- D-P4-02-1: Moltbook アカウントをどう処遇するか / 選択肢: A 放置して識別子を凍結（README に状態語、投稿は platform に残る） B 人間名義で「終了」を 1 投稿 C platform に削除依頼 / 推奨: A — observation-over-steering（観察対象への介入を最小に）と公開記録 = アカウント URL の整合。B は人間がエージェント名義で発話する線を越え、C は第三者 ToS 依存で client に呼び手が無い（drift state は呼んだ endpoint の応答 key しか持たない; 平台側の有無は P1-07.19 の台帳行で確認） / 期限: 2027-02-06 の土曜ゲート（dry-run の前）。遅れても害は小さいが強制終了時に未決で残り、.6 の Moltbook 鍵の処置も決まらない
- D-P4-02-2: 最終版で snapshots の回転窓（`MAX_SNAPSHOTS = 100`）の履歴分を tree に戻すか / 選択肢: A 戻さない（git 履歴と各 Zenodo 版に残る） B 履歴から全 snapshot を tree に戻す（サイズ未確認、推測で数百本・数百 MB） C 月次 1 本など抽出 / 推奨: B をサイズ確認つきで（熟慮。最終の不変版から回転で消えた snapshot を抜くか入れるかの決定で、後から足せない一方向の扉）— Zenodo の release zip は tree しか含まず、「bit-for-bit replayable」を謳う最終版から回転で消えた snapshot が抜けるのは研究再利用性の損失 / 期限: P3-05 の DATACARD 改訂と同時（2027-Q2）。遅れると最終版の Zenodo zip から回転で消えた snapshot が抜けたまま不変面に固定される


### P4-03 継続性（bus factor 1）・引継ぎ・インシデント手順
- D-P4-03-1: 継承者を 1 名決めるか「決めない」と記録するか / 選択肢: A 決めない（第三者の最小指示 = 何もしない / GitHub archive のみ） B 1 名を決め GitHub successor 設定 + 最小権限（archive 権限のみ、鍵は渡さない） C 組織へ移管 / 推奨: B — 鍵を渡さず archive だけできる最小権限は security by absence を崩さず、公開ミラーの「静かな停止」を「宣言された停止」にできる（B なら .2 は archive 権限の付与と audit 1 行だけ）/ 期限: 2027-02-06 の土曜ゲート。遅れても害は小（Zenodo 版は不変）だが、.2 の適用範囲が決まらない


## 5. やらないこと（却下・延期の記録）

ADR-0080 のレンズで capability-growth または value-steering-risk に分類された提案、前提（M1 16 GB・ゼロ API・資金なし）を変えないと成立しない提案に加えて、却下した修理の誤った形・計器の増設（neutral / instrument）も理由つきで残す。行は 3 種類ある。(1) **却下**（理由つき。復活には記した前提の変更か ADR の supersede が要る）。(2) **延期した repair**（「触る時だけ・凍結後」と記したもの。却下ではなく延期台帳で、トリガーが来たときに読み直す。期日つきの残作業は停止リスト（P1-01.3）に置き、ここには入れない）。(3) **第 4 章の選択肢として残る**（「第 4 章 D-… の選択肢として残る」と記したもの。却下ではなく、その決定が下りた後にここへ移すか本文へ戻す）。「該当なし」の行は数えない。


### P0-01 10-10 土曜ゲートの決定束（insight / RFC-0042・0023・0048 / ADR-0111 / T4）
- 判定を緩めて候補数を戻す（tie-break を NEW 向きに戻す、閾値を下げる、temperature を上げる）: 候補が出ない理由を読まずに判定者を動かすのは価値層への操舵。RFC-0042 Drawbacks「文言はこれ以上いじらず、再開後の実数で読む」。value-steering-risk 出典: CP-19 VL-20
- revise 本文を誰も読まないまま案 B（置換経路）を入れる: 量を戻す向きに働き、改訂本文の質は未読（ADR-0111 Negative）。capability-growth（VL-20 の分類）。D-P0-01-1 で判断 出典: VL-20 AB-10
- 希少レーン（singleton 保留台帳 + 週次再クラスタ）の実装: 供給側の能力拡大。capability-growth 出典: AB-08
- revise 率・duplicate 率の週次トレンド計器: ADR-0111 D7「no bespoke weekly instrument」と ADR-0101。Summary 行への 1 値追加で足りる。neutral（計器増設の抑止） 出典: CP-20 VL-22


### P0-02 10-15 読み → 旧 relevance gate の削除（RFC-0046 後始末 3）
- 判定不能時の旧スコアへの fallback（A0）を残す・戻す: enforce 後 1,616 行で live gate が代わりに働いた行は 0（`rfcs/0046:207`）、fail-closed = 無言 = absence 維持。neutral（二重判定者の抑止） 出典: SA-31 AR-26
- `relevance_score4` 不在時に code の既定値で fail-open にする: fail-closed はオーナー決定（ADR-0113 追補 1）、既定で engage させると「静かに何かする」経路になる。neutral 出典: AR-28
- RFC-0047 の face 較正（margin / 位置バイアス）を削除 PR に混ぜる: 削除は判定経路を 1 本にする修理、較正は P1-15 の読み。neutral 出典: AR-26（範囲外）


### P0-03 公開データの開示境界の修理（embedding 入り .bak・ロック・絶対パス）
- sync に `--delete-excluded` を入れる: 手書き保守ファイル（README / DATACARD / CITATION 等）も除外で守られているので一緒に消える。撤回は .4 の `rm` / `git rm` 段で行う。整合: neutral（運用リスク） 出典: SA-13 の選択肢 (2)
- P0-03.13 相手エージェント表示名の逆引き script（`sources.json` の「表示名 → 出現ファイル」、名前で来た依頼を post id に解決）: 依頼者はまだ 0 人で、表示名の仮名化の採否は D-P0-03-3 の D として `gate_item` に残る。名前で来た依頼は、来た時に `grep -rl` 1 本で引ける（R4-CUT Prune）。延期（neutral）。トリガー: 名前で来た takedown 依頼が 1 件届いた時。出典: R2-ETH-02


### P0-04 蒸留の取りこぼしと非原子書き込みの修理（06:00 JST セッション）
- 冪等キーなしで `--days 2` に広げるだけの対処: 同じ経験から別文面の pattern が再生成され、tombstone と「新規」行が増える（churn）。neutral（修理の誤った形） 出典: CP-01 CP-02
- `.bak` 復元案内を残したまま `fsync` を足す: 電源断は `_io.py` の契約外、問題は復元手段の不在。neutral 出典: CP-06 CP-08
- backfill で `--file` の日ファイル丸ごと再処理: 台帳なしでは既蒸留分が UPDATE / ADD で重複する。neutral 出典: CP-01


### P0-05 初回体験（Quick Start）の修理と preflight
- 該当なし（18 件すべて repair / instrument）。`dialogue` の失敗 turn を再試行して会話を続ける案は元項目にも無く、silent fallback の変種になるので採らない（ADR-0075）


### P0-06 v2.13.0 リリース（Python 床・配布単位・版メタデータ・runbook）
- （第 4 章 D-P0-06-2 の選択肢として残る）Homebrew formula / PyPI の継続公開: 需要の証拠が無く、保守義務のある配布面を増やすのは「止まる」と逆向き。引用用の固定版は Zenodo + SWH + tag で足りる。neutral（RD-28 の C は却下相当、B は capability-growth 寄り） 出典: RD-28
- 過去の lightweight tag の付け直し: 既存 DOI / SWH が指す tree を動かす害の方が大きい。runbook で以後の tag だけ annotated にする。neutral 出典: RD-11


### P0-07 10-31 due の憲法改正ゲートの事前登録と shadow 系列
- shadow テキストを改正候補にする: 承認系譜が無い（ADR-0092、runbook step 0「NEVER an amendment candidate」）。value-steering-risk / governance 出典: RF-11 AB-07
- 改正出力の shape 逸脱で拒否する validation: bold integration が設計意図、記録だけにする。neutral 出典: PF-38
- due=true で改正を自動起動する: 改正は人間起動（ADR-0090 / 0091、承認 = 責任を取る行為）。次の土曜に改正ゲートを予定し `gate_record` に 1 行を書くまでに留める（.4）。value-steering-risk（無人の価値層変更） 出典: WO-52
- P0-07.6 due 週に改正ゲート開催の RFC draft を weekly-gate が自動起票し、fixture テストを付ける: due は 83 日ごと（年 4 回）で `constitution.due` は既に Step 6b に表示されている（`SKILL.md:238-240`）。RFC の自動起票と fixture テストは、.4 が Step 6b と runbook に置く 1 句（「due=true の週は改正ゲートを次の土曜に予定し `gate_record` に 1 行」）で足りる（R4-CUT Prune）。neutral 出典: WO-52
- 改正プロンプトの文言を 10-31 前に広く改稿する: 事前登録の前に介入を変えると前後比較が壊れる（変数は一度に一つ、ADR-0056）。.8 の出自の機械化は記録、L11 削除は prompt 編集（P3-07.1 チャネル (3) の dated 行）なので 10-31 の読み取得後に行う。neutral 出典: PF-37 RF-22


### P1-01 機構層の「凍結」判定を定義する
- （該当なし — 入力 3 件に capability-growth / value-steering-risk は無い。凍結の CI による機械強制は入力に無く提案しない: 凍結は判断であり、ゲートの権限は人に残る（ADR-0080 の 08-26 追補 §A）。.6 の機械検査は既存の snapshot テストと読み script の 2 つに限り、新しい hook は置かない）


### P1-02 RFC 台帳の健全化と blocked RFC の終端
- RFC-0040 の「将来像」（用途別 decision / reasoning / generation model + 薄い deterministic harness）の追跡継続: 較正確率の消費者が repo に無く、16 GB で gemma と同居できる候補も無い。capability-growth 出典: LP-30 AB-09


### P1-03 ADR 台帳の機械追跡（追補・Note・索引・Review-when）
- 既存 113 本への `Decided by` backfill: 推定で埋めると帰属の記録が逆に汚れる（AKC ADR-0026 の先例どおり新設のみ）。neutral 出典: GO-30
- ADR 本文の書き直しによる整合化: README の「preserve the original body」と ADR-0095 の「却下理由ごと残す」に反する。整合は Status 行・注記・graph edge の追加だけで取る。neutral 出典: AB-22 DC-28


### P1-04 計器の解体と消費計画の補完（ADR-0101 T4）
- P1-04.2 の surprise 撤去条項（直近 4 週に読んで決めた事が無ければ RFC-0016 の review-when どおり撤去 RFC を起票）: ADR-0097 en:8,186「the surprise instrument is restored; the worth judge is not」は surprise を 08-26 追補 §B の新規性軸の既実装として復元した決定で、P2-06.2 が 3 軸 join の 1 列として消費する（名指しの消費者あり）。撤去条項は P2-06.2 と矛盾し、08-26 追補 §B の軸を 1 つ消す（R1-NS P-2）。neutral 出典: AB-19
- `report --confusion-pairs` の CLI 面追加（CH-20 の案 (a)）: wheel 内に消費者を作って保持を正当化する向きで、ADR-0101 の「読みで決める」と逆。`scripts/` へ移す案 (b) を .4 に採った。整合分類: instrument（読み面の拡大）。出典: CH-20


### P1-05 観察台帳と週次計器の機械化（baseline・expiry・自己故障）
- 無人セッションによる baseline 宣言・自動 archive の実行: 較正の変更は人間ゲートを通す設計（`observation_ledger.py:60-63`、RFC-0010 Q5/Q8）。render が候補を出し、裁定は gate。整合分類: neutral（value-steering-risk の予防）。出典: WO-03 WO-08（境界として）
- census に `PAUSED` 状態を新設する: constitution-shadow は `cadence_days=90` の QUIET（commit `7a152b0`、2026-10-03）で既に畳まれ、insight-staged の NO_ROWS は再開後に staging が空という RFC-0042 の読み値そのもの（insight は止まっていない）。状態語彙を増やさない。整合分類: instrument。出典: OI-12


### P1-06 コード構造の最後の窓（OllamaBackend・core 内層契約・規約の明文化）
- `adapters/moltbook/verification_parse.py` の分割: 1,806 行の大半は語彙・規則表、関数は C901 で分割済、1 か月変更なし・誤答 0（601 件）。分割は round 番号と表の対応（docstring :1-113）を散らすだけ。ADR-0062 追補「分割しない」は .7 で記録する（節見出しは .9 と共に落とした）。neutral。出典: AR-11 CH-01
- `core/_io.py` の改名（`_io` → `io_utils`）: fan-in 46 の rename コストに見合わない。索引 docstring も .9 と共に落とした（5 家族の構成は checkout から読める）。neutral。出典: CH-43
- 関数長の lint ルール（PLR0915 等）の追加: ハーネス ADR-0056 の config-only 方針と verify.md「C901 に一本化」を覆す理由が無い。記録のみ（.7）。neutral。出典: CH-07
- `JSONValue` 再帰 alias の新設: verify.md:163 で判断済。D-P1-06-2 の B と同じ。neutral。出典: CH-31
- dead code 周りの新規作業: `TODO/FIXME/XXX/HACK` 0 件、未参照 private 0 件（文字列 dispatch の偽陽性のみ）、`print` は T20 免除の 4 面に限られ core に 0。台帳修正 1 件（`draft_body`）は .10 に含めた。確認事項で作業なし。neutral。出典: CH-21 CH-30
- P1-06.5 文字数上限 3 定数の core → adapters 移動と script 用 prompt 2 本の移動: 消費者は `core/episode_render.py` と `adapters/moltbook/llm_functions.py` で、移動は core の描画に引数を通す構造変更になり、凍結後に触らずに済む効果が無い。prompt 2 本は `tests/test_packaged_assets.py:36-39` の例外集合で既に固定（R1-FRZ Prune-03）。neutral 出典: CH-26 CH-39 LP-06（dead field `stocktake_merge_rules` の削除は P1-07.14 のまま）
- P1-06.6 広い `except` の印と pyright の無効化範囲: RUF100（不活性 noqa 6 件の削除）は .10 に吸収した。BLE001 の select 追加と `except Exception` 41 件への理由つき noqa drain、pyright `reportUnusedVariable` / `reportUnreachable` の cli 限定と core / adapters の drain 台帳、`cli/adopt.py:453` の logger 統一は src churn + 常設 lint の追加で、凍結後に src が止まれば捕まえる新規違反が無い（R1-FRZ Fix-09）。延期（neutral、触る時だけ・凍結後）。トリガー: 当該 handler / module を fix PR で触る時にその範囲だけ。出典: CH-11 CH-27 CH-14
- P1-06.8 の `exc_info` sweep（計器型 handler の 90% に traceback を残す）: 同形の sweep で凍結に寄与しない（R1-FRZ Fix-09）。延期（repair、触る時だけ・凍結後）。トリガー: 当該 handler を fix PR で触る時に規約 4 行（.8）どおりに直す。repair の形だが凍結後の sweep は churn。出典: CH-29
- P1-06.9 責務 docstring・節見出し sweep（16 module の docstring、public 関数 21 本、`client.py` の endpoint 表、`core/_io.py` の索引、`verification_parse.py` の節見出し）: ADR-0102 がコード構造文書を退役させた理由（古い記述は無記述より有害）がそのまま当てはまり、LSP で導出できる（R1-OWN Prune-02）。加えて src への `docs:` commit は P1-01.1 の読みで「fix 以外 = 動いた」になり、完了条件の docstring ≥ 5 行の常設 assert は以後すべての接触に docstring 編集を義務づける（R1-FRZ Prune-02）。「分割しない」の ADR-0062 追補だけ残した（旧 P1-06.15 を経て R4 で .7 へ）。neutral 出典: CH-09 CH-10 CH-01 AR-11 CH-06 CH-43
- P1-06.12 `register` の自己紹介文を template 由来にする: 第三者向けの新挙動（能力）。`auth.py:88-96` の固定文は本番 1 インスタンスでは正しく、凍結後に触る理由にならない（R1-FRZ Prune-04）。capability-growth 寄り（元の整合は neutral）。出典: AR-32 CU-05
- P1-06.14 コメント鮮度 sweep の四半期 T4 登録: 四半期ごとに `docs:` 型の src commit を予定する = 凍結後に周期的に src を触る制度で、D-P1-01-1 A の「連続 8 週 fix のみ」を 3 か月ごとに破る。日付入りコメント（347 行）は触った関数の fix PR で直すか消す（ADR-0102 Decision 2「checkout から再計算できるものは書き残さない」の論理。棚卸し sweep は建てない）（R1-FRZ Prune-01）。neutral 出典: CH-40
- 旧 P1-06.15 (1) `cli/adopt.py`（1588 行）の分割: names 解析 + archive spec を `adopt_names.py`、予算計器を `stocktake_cmd.py` 側へ出し 1,000 行未満にする。項目本体が延期行そのもので、着手しない項目が束の M 件数を水増ししていた（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。トリガー: RFC-0042 系の adopt 変更の収束。分割時は `test_cli_adopt.py`（2,064 行）無変更で green。根拠: 巨大 6 本中 commit 最多（22 件、2026-08-16〜09-19）。出典: CH-02
- 旧 P1-06.15 (2) `core/insight.py`（1150 行）の分割: cluster batching と fail-open cap を外し「段を順に呼ぶ driver」にする（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。トリガー: RFC-0042 のブロック解除（それまで `insight.py` は動かさない）。分割時は `test_insight*.py` 無変更で green。出典: CH-04
- 旧 P1-06.15 (3) `core/selection_metrics.py`（1141 行）の分割: `_render_*` / `format_*` 273 行を `selection_report.py` へ出す（2026-09-12 の `selection_window.py` 切り出しの残量）（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。トリガー: 週次 report の表示変更。分割時は `report --skill-selection` の出力バイト一致。出典: CH-05
- 旧 P1-06.15 (4) `adapters/moltbook/client.py`（1131 行）の分割: `MoltbookClient`（transport / rate / audit）と `endpoints.py` に分ける（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。トリガー: 平台 API の変更。出典: CH-06
- 旧 P1-06.16 (1) `core/llm` の module 状態を frozen `LLMRuntime` 1 個に畳む: `global` 5・`configure` 12 kwargs・`reset_*` 8 本を `configure` = `replace()`、reset 1 本に（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。着手時の前提: P1-06.1（OllamaBackend）が入っていること。トリガー: `core/llm/__init__.py` の module 状態を fix PR で触る時。着手時の完了条件: `core/llm/` の `global` ≤ 3・`reset_*` ≤ 3 で「現在の構成」が 1 関数で JSON 化できる。根拠: `global` 27 箇所（`core/llm/__init__.py` 5 / `domain.py` 4 / `prompting.py` 3 / `guard.py` 3 / `relevance_cache.py` 3 …）。出典: CH-34
- 旧 P1-06.16 (2) `MOLTBOOK_HOME` の綴りの統一: `MOLTBOOK_DATA_DIR`（import 時凍結、派生定数 20、`adapters/moltbook/config.py:24`）と呼び出し時 env 読みの 2 機構を `data_root()` + `paths(root) -> Layout` に統一し、派生 `*_PATH` の呼び手も同じ PR で置換（alias 無し: .10 の規約）（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。着手時の前提: P1-06.1。トリガー: home のパス解決を fix PR で触る時。着手時の完了条件: `MOLTBOOK_DATA_DIR` 直接参照 0。出典: CH-36
- 旧 P1-06.16 (3) cli の遅延 import: `cli/__init__.py:18-26` の全コマンド import を `CommandSpec` の遅延 import（`module` + `handler`）に（関数内 import cli 56 件）（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。着手時の前提: P1-06.1。トリガー: `--help` の起動時間か import 失敗が fix の対象になった時。着手時の完了条件: `--help` が adapters を import しない。出典: CH-44
- 旧 P1-06.16 (4) Decision 語彙の改名: `_Decision`（`verification_parse.py:1090`）→ `_ParseVerdict`、`GateDecision`（`novelty.py:51`）→ `NoveltyVerdict`（呼び手全部と同じ PR、`decision.py:229,246,265` と区別）（R4-CUT Prune）。延期（neutral、触る時だけ・凍結後）。着手時の前提: P1-06.1。トリガー: 当該 module を fix PR で触る時。着手時の完了条件: `Decision*` 識別子が `core/llm/decision.py` 由来のみ。出典: CH-45


### P1-07 アダプタと LLM 接点の堅牢性（障害時の挙動・予算・較正定数・来歴）
- 生成の seed 固定: 本番は多様性（t=1.3、ADR-0047）が目的で、再現は evals の多数決 3 と凍結版 label set で代替できる。記録だけ残す（.15）。neutral。出典: LP-16
- （第 4 章 D-P1-07-2 の選択肢として残る）`NUM_CTX` を測らずに 49k へ上げる: KV 常駐（32k で 3.4 GB、ADR-0112）が増え 16 GB の swap を招く恐れ。D-P1-07-2 の C は計測つきでのみ。neutral。出典: LP-34
- transport / 鍵失効での自動停止（launchd 解除など）: この束は「終了して理由を書く」まで。自動停止を入れない判断は P2-04。neutral。出典: AR-05 AR-01
- P1-07.2 transport 障害の 1 回再試行と連続失敗の backoff: `SessionContext` に新しい状態と待機規則を足す能力追加で、現行契約は `client.py:736-766`「失敗した読みは空の読み」、再試行が無いことによる事故の記録が無い（R1-FRZ Prune-05）。延期（repair、触る時だけ・凍結後。repair と記していたが能力寄り）。トリガー: api-audit に「transport 失敗で読みが空になった」週が 2 回。注: 入れる時も 429 widening（`recent_429_count`）とは別機構にしない（1 つの待機を 2 機構が奪い合う）。出典: AR-01
- P1-07.4 の修理 3 点（hard / soft 429 判定を rate header の reset 値一次・文言補助にし `Retry-After` の HTTP-date を受ける / `_EXPECTED_KEYS` に feed・home を足す / 通知に `since` を渡し 1 回だけ次ページ）: 平台の現行文言・既定件数・paging が未確認（推測）のまま本番 client を触らない（R1-FRZ Fix-10）。延期（repair、触る時だけ・凍結後。AR-04 は instrument）。トリガー: .4 の取りこぼし件数の読みが非 0、または hard 429 の誤判定が api-audit に 1 件（平台の現行文言・既定件数・paging の確認は .19 の台帳行を引く）。出典: AR-03 AR-04 AR-09
- P1-07.6 の残り（`api-audit.jsonl` / `verification-audit.jsonl` の `*-YYYY-MM-DD.jsonl` 日付分割、`_census_registry.Entry` の既知 schema 版集合と未知版 WARNING、欠け欄の既定の docstring 集約、otel 側の `gen_ai.operation.name` 分岐）: reader が registry glob・backup・otel・drift scan に跨り 1 PR で終わらない（R1-FRZ Merge-04）。llm-calls 行の `kind` / `schema` は .13 に吸収した。延期（instrument、触る時だけ・凍結後）。トリガー: 当該ログの reader（`_census_registry.py` / `api_drift_scan.py` / `backup-runtime.sh` / otel `records.py`）を触る時。出典: AR-33 AR-34 AR-10
- P1-07.8 の pass-2 予算（8k est tok）と `selection_truncated` 欄（超過分を catalog 順で落として落とした名を記録）: 新しい切り捨て規則 = 能力（R1-FRZ Fix-10）。延期（neutral、触る時だけ・凍結後）。トリガー: pass-2 由来の `budget_exceeded` 行が週次の読み値に出た時。出典: LP-03
- P1-07.15 の固定文を `config/prompts/decision_*.md` に外出しする案: cache / label set の pin 対象を広げる新作業。ADR-0112 追補 1 行で記録する（.15）（R1-FRZ Fix-10）。neutral。出典: LP-08
- P1-07.17 `run` の offline fixture 経路（`--dry-run --feed-fixture FILE`）: 消費者のいない経路を増やす。第三者の「動くか」は P0-05 の smoke（`run --session 5` の本番実行）で足りる（R1-OWN Prune-07）。neutral。出典: AR-31


### P1-08 テストと CI の強化（macOS job・未モック LLM・順序依存・床・契約）
- mutation testing（全体適用も guard 3 領域限定も）: src 12,437 stmts で M1 16GB は数時間級、道具を増やす capability-growth。guard 3 領域限定の四半期 1 回も常設検査の追加（ADR-0101 の逆方向）として落とした（旧 .14、R1-OWN Prune-08）。出典: TQ-36
- 長時間ソーク / 耐久ゲートの新設: 6 時間セッションの長期挙動は本番の監査ログ（ADR-0075）と `instrument_census.py`（ADR-0110）が計器で、新規ゲートは capability-growth 寄り。出典: TQ-37
- xdist の常用 / CI 並列化: suite は 46.9s（xdist で 17.5s）で必要なし。neutral。出典: TQ-24
- 記録のみの項目（docs-as-tests / absence ゲートの充実、vulture・bandit・pip-audit の健全）は項目化しない。出典: TQ-42, TQ-39
- P1-08.11 1,500 行超のテストファイル 7 本（`test_agent.py` 4,497 行 / `test_llm.py` 3,292 / `test_skillsel_arm_replay.py` 3,000 / `test_skill_selection.py` 2,574 / `test_cli_adopt.py` 2,064 ほか）の分割: 止まる層での構造 churn。壊れていないものを割る費用に対し北極星側の価値が無い（R1-OWN Prune-01）。延期（neutral、触る時だけ・凍結後）。トリガー: 当該ファイルを触る fix PR の範囲で必要になった時（.9 の random-order 緑が前提: 分割は実行順を変える）。出典: TQ-17
- P1-08.13 週次チェーンに検査段を置く（`HYPOTHESIS_PROFILE=explore` の探索 1 段 + 本番機限定の実 Ollama 契約 smoke 1 段）: 無人チェーンに段を足す（D-P2-02-1 B が「決定論 instruments のみ」へ縮める方向と逆）。Ollama smoke は JST 定時窓との同居制約（CLAUDE.md:38）を毎週抱え、落ちた例の `@example` 昇格は人間 commit（R1-OWN Prune-09）。根拠の訂正: `@given` を使うのは 4 ファイル（`test_distill_chaos` / `test_llm_chaos` / `test_verification_chaos` / `test_cross_day_duplicate_scan`）、6 は `from hypothesis import` のファイル数（R1-FRZ Fix-15）。instrument 出典: TQ-19, TQ-35
- P1-08.14 differential replay の定期化と限定 mutation: 常設検査の追加 = ADR-0101 の逆方向。「release 前 1 回の differential replay（固定した baseline + 4,963 challenge、`docs/evidence/adr-0062-parser-rewrite/`）」は P0-06 の runbook 項目に 1 行として移した（R1-OWN Prune-08）。instrument 出典: TQ-37, TQ-36
- P1-08.22 sleep と実 I/O を持つ遅いテスト 2 件（`test_session_ends_by_time` 3.33s、`test_429_counter_increments_on_429` 3.00s）を閉じる: `MoltbookClient` の sleep を注入可能にする = テスト速度のための本番 seam 追加。2 件で 6.3 s、pytest 全体 46.9 s。sentinel 以外への実接続 1 件は .8 の検出で可視化される（R1-FRZ Prune-06）。neutral 出典: TQ-23
- P1-08.8 の 78 件の棚卸し（「LLM 不達を意図」と「mock 漏れ」の仕分け、後者の `ChaosBackend` / requests 層への再 mock）: test churn（R1-FRZ Fix-11）。一括 marker で終える。延期（neutral、触る時だけ・凍結後）。トリガー: 当該テストを触る時。出典: TQ-13
- P1-08.9 の共有 sandbox を per-test `tmp_path` に移す書き換え（+ `OLLAMA_TRUSTED_HOSTS` 無効行の削除・`atexit` rmtree）: conftest の書き換え規模が autouse reset の数倍で、順序依存は reset + `-p randomly` で読める（R1-FRZ Fix-11）。延期（neutral、触る時だけ・凍結後）。トリガー: 3 seed 緑の後に seed 固有の FAIL が再発した時。出典: TQ-14, TQ-40
- P1-08.10 の内部 generate patch の棚卸しと半減（≤ 90）: 1,257 箇所の patch を触る目標（R1-FRZ Fix-11）。規約 2 行（CLAUDE.md）と週次の grep 1 行（読みだけ）にとどめる（R2-TST Fix-12）。neutral 出典: TQ-16
- P1-08.12 の F-FEED fault 列 5 本（timeout / 429 / logprobs 欠落 / malformed / flapping を `ChaosBackend` で `DecisionBackend` seam に当てる）: ADR-0100 は by-default 義務を退役させており、新しい fault 列は opt-in の判断で、凍結直前に 5 本足す理由が無い（R1-FRZ Fix-11）。延期（repair、触る時だけ・凍結後）。トリガー: enforce 経路で新しい fault が本番の api-audit / llm-calls 行に出た時（fix PR の再現テストとして）。出典: TQ-20
- 旧 P1-08.19 週次セッションの deny テストの参照行: 中身は P1-10.5 が同じテスト関数（`test_c_scope_6_read_scopes_survive_in_the_deny_list`）で持ち、この束には参照だけが残っていた（R4-CUT Prune）。束の依存に P1-10.5 の 1 行を置く。neutral 出典: SA-37


### P1-09 ドキュメントの同期と欠落文書（数値・CYCLES・CONFIGURATION・glossary・llms）
- （第 4 章 D-P1-09-3 の選択肢として残る）cron / systemd 用のスケジュール例を同梱する: 非 macOS 対応は能力拡大で、M1 16GB・launchd の前提を変える提案は前提変更として別起票すべき。P1-14.7 の `--print` + runbook の最小例も同じ理由で落とし（R1-OWN Prune-05）、.20 の宣言 1 行と D-P1-09-3 A で代替する（R1-NEW F1 で P1-14 と統一）。capability-growth 出典: RD-26
- P1-09.16 `docs/ARCHITECTURE.md` を graph.jsonld の Concept ノードから生成する: 生成スクリプトという新しい保守対象が増える。README overview.svg + graph.jsonld + ADR index で足りる（ADR-0102 の方針と同じ）（R1-OWN Prune-03）。延期（neutral: 触る時だけ・凍結後）。出典: DC-40
- （第 4 章 D-P1-09-1 の選択肢として残る）P1-09.18 文書言語方針のディレクトリ別明文化と AGENTS.md の実ファイル化: CLAUDE.md § ドキュメント言語方針の 3 行で既に足り、読者は AI で symlink でも読める（R1-OWN Prune-04）。D-P1-09-1 は残し推奨を A に変更。neutral 出典: DC-11 AB-36 DC-43
- `com.moltbook.sync-data` の plist を repo に足して公開同期を無人化する: 本束は文書を実態に合わせるだけに留める。plist を installer 管理下に置くかは P2-04（D-P2-04-1）で決め、無人公開経路の拡大（公開範囲）は P2-05（R1-NS F-11 で統一）。neutral 出典: CP-31
- 外部リンク検査を週次無人チェーンに入れる: 無人の外部 I/O を増やさない（ADR-0007 / ADR-0015）。release 時の手動 1 ステップ（P0-06.6 の release runbook）に留める。neutral 出典: DC-38
- CYCLES / CHANGELOG / glossary の `.ja.md` 新設や ADR 追補の ja 同時編集の義務化: 同期費用が 2 面分増える。D-P1-09-1 A のもとでの運用規則（Status 行と `## Amendment` 見出し + 1 行要約は ja も同じ PR、Note 本文は en のみ、`enja_drift` は Status / 見出しの差分だけを数える）で足りる。neutral 出典: AB-36 R3-ADR Fix-07


### P1-10 セキュリティ: threat model・SECURITY.md・I/O 面の機械ゲート・鍵の所在
- 出力サニタイザへの鍵実値置換（runtime 追加）: absence は .10 の sentinel テストで証明する。runtime に守りを足すと ADR-0007 Amendment 型の「宣言と実装のずれ」面が 1 つ増える。neutral 出典: SA-26
- `VALID_MODEL_PATTERN` の実装: `OLLAMA_MODEL` は localhost Ollama への JSON 値で境界ではない。ADR-0007 §4 を実装に合わせる（.2）側に寄せる。neutral 出典: AR-21
- P1-10.8 の `Context` を `<untrusted_content_{nonce}>` 枠で描画する半分: 消費側 `scripts/weekly-analysis.sh:125-145` が `$DAILY_REPORTS` を per-run nonce で既に包み（`:346-351` は旧 report も再フレーム）、render 時の枠は二重になって人間の正規の読み経路（CLAUDE.md:98）である公開 report の毎エントリに定型文が入る（R1-SEC P-2）。Title / Submolt の defang は .8 に残す。neutral 出典: SA-23
- API エラー本文を `.log` から `api-audit.jsonl` へ b64 で逃がす改修: 500 字・単行・印字可能文字に潰した現状を「受容済み残余」として .1 に記録する方が安い。neutral 出典: SA-05
- 旧 P1-10.11 `agent-launchd.log` 汚染世代の退役を audit 行と watchdog 行で言わせる: 一度きりの日付のために計器を 2 つ足していた（R4-CUT Prune）。`CLAUDE.md:98` の例外行に「初回 rotate 日 + 8 世代 = 退役予定日」を日付で書く 1 句を .4 の PR に置き、その日にオーナーが例外を外す。neutral 出典: SA-38


### P1-11 兄弟 repo の処遇（cloud / mlx / otel / rules）
- `MlxLogprobsDecisionBackend` の新設（mlx_lm.server の `logprobs` を読む判定 backend）: capability-growth。本番の判定は Ollama で足り、ADR-0112 Review-when は再考条件を「Ollama が custom-head を serve できる / Jev 重み公開」に置いている（ADR-0112:200-202）。RFC-0040 も blocked。出典: SB-01
- 兄弟 3 repo への GitHub Actions 追加: ADR-0088 en:243-250 で却下済み（触られない repo に CI を置いても検出動機が無い）。frozen 宣言 + 実行前 `pip-audit` の 1 行で代替。neutral 出典: SA-28 SB-12
- rules repo の条項文を本体の改正済み憲法に同期すること（THEME-MAP の「改正済み憲法と同期する」の文言は訂正）: rules は ADR-0002 の verbatim 配布物で、改正済み文は稼働エージェントの観察対象（値層）。エージェントが自己改正した値を「他エージェント向けルール」として配布するのは observation-over-steering の逆方向の混同（value-steering-risk）。代わりに .11 (a) で関係を 1 行明記する。出典: RF-43（解釈）
- P1-11.4 の「本体の `[tool.ruff]` select と pyright 設定を複製する」半分: gate が読むのは kit の verdict だけ（`check-sibling-backends.sh:63-66`）で、lint 設定の複製は凍結・維持どちらでも読み手のない保守面（ADR-0101）（R1-SIB Prune-01）。neutral 出典: SB-37
- P1-11.8 の「otel `--endpoint` を localhost / 無ドット host に限る」半分: otel は別プロセスで外部面は exporter 1 つ（ADR-0015 に適合）、endpoint はオペレータの設定値で、2 つの脅威（I/O 面を広げるコード変更 / Claude Code の untrusted 読み）のどちらでもない。mlx の `validate_trusted_url` はエージェント自身の推論先に対する ADR-0007 §3 の宣言維持で立場が違う（R1-SEC P-1、R1-SIB Prune-02）。neutral 出典: SA-34
- otel の対象ログ族の拡張（`relevance-*.jsonl` 等、`_census_registry.py` の登録 16 件中 otel が読むのは 3 件）: instrument だが読み手未定。D-P1-11-3 で維持を選んだ時だけ ADR-0078 追補で消費計画つきで再開（→ P1-04）。出典: SB-10
- cloud の `gpt-5` 既定を live API で smoke 検証（API コスト）: 凍結なら .2 (e) で既定を検証済みモデルに戻す方が安い。維持なら P3-03 の対照実験の初回 run に含める。出典: SB-16


### P1-12 承認ゲートの記録を「責任の行為」にする（approver・reason・却下本文・GOVERNANCE.md）
- P1-12.6 手編集と復元に監査経路を与える（`edit-value` / `restore-skill`）: 1 人運用の手編集のために CLI 面を 2 つ足し、凍結窓で src を増やす。トリガー: approval_join の `matches no approved row` が手編集由来で 1 件出た時。それまでは weekly-gate の可逆性表に「`mv` で戻した時は `gate_item` に 1 行」。D-P2-07-1 = A（層 1 の無人 archive に復元権を付ける）なら `restore-skill` だけを P2-07.1 の実装に同梱する（R4-CUT Prune）。延期（repair）出典: GO-08 WO-45
- 監査ログの hash chain / 電子署名: 単一オーナー運用では週次 private backup の git 履歴が改竄検出面として足り、鎖の導入は能力動機の拡大。文書化（.4）で止める。capability-growth 出典: GO-06


### P1-13 AI 判断役の権限境界と帰属表示の明文化
- 判断役 AI に保護クラス（値層・ADR・prompts・`.claude`・verify）の merge まで渡す: AKC ADR-0028 が却下した代替案で、ADR-0005 が禁じる LLM 承認経路になる。value-steering-risk 出典: GO-13（決定 A の範囲外として明記）
- P1-13.5 の CODE_OF_CONDUCT 部分: 人員拡大しない（§0）。CONTRIBUTING は「ADR を要する変更の線」1 段落 + Verify の通し方に縮め、D-P1-13-3 の目的はそれで満たす（R1-OWN Prune-12）。neutral 出典: GO-28 DC-42


### P1-14 CLI の残りの UX 整備（`.last_insight` の起点・テンプレート skills・installer の前提・`init` の Tier）
- （第 4 章 D-P1-09-3 の選択肢として残る）systemd / cron のジェネレータを本体に足す: 「制約で彫る」（1 台の M1）に反する能力拡大。`--print` + runbook の最小例（旧 .7）も R1 で落とし、P1-09.20 の OS 前提宣言と D-P1-09-3 A「宣言のみ・cron 例は同梱しない」で P1-09 と統一した（R1-NEW F1）。neutral（範囲の線引き）。出典: CU-29
- P1-14.1 購読確認の永続化と「確認される副作用」の一覧: home に新しい永続状態 + 却下記録 = 能力で、影響は第三者の APPROVE 体験のみ、本番 `--auto` には無い（R1-FRZ Prune-07）。D-P1-14-2 は推奨 C を前提（決定前）。副作用の一覧（subscribe / upvote post / upvote comment / follow / unfollow / mark-read / post / reply）と `_confirm_*` 呼び出し箇所の一致テストは P1-09.10 の CONFIGURATION 書き直しに 1 表。repair と記していたが能力寄り。出典: CU-08
- P1-14.3 `domain.json` を home で解決する: `--domain-config`（`cli/__init__.py:61-66`）と `CONTEMPLATIVE_CONFIG_DIR`（`core/domain.py:24-28`）が既にあり、第三者向けは「`config/domain.json` を複製して `--domain-config` で渡す」の文書 1 段落（P0-05.10 (d)、D-P0-05-2 推奨 B を前提（決定前））で足りる。plist に `--domain-config` を渡す 1 引数は .6 に（R1-NEW Prune）。延期（neutral: 触る時だけ・凍結後）。トリガー: 第三者が `domain.json` の上書きを求めた時、または P0-06 が wheel を選んだ時（R1-FRZ Fix-12）。出典: CU-13
- P1-14.4 home prompts の upgrade ドリフト警告と `init --refresh-prompts`: D-P0-05-2 推奨 B（`init` の prompts 複製をやめる）が採られると複製は生まれず機構として不要。`MOLTBOOK_HOME` 明示の既存 home に残る旧複製は P0-05.7 の文書 1 行「`prompts/` のファイルを消せば packaged に戻る」で代替（R1-NEW Prune、D-P0-05-2 推奨 B を前提（決定前））。packaged との差分 WARNING 1 行だけは digest を取る P1-07.13 に置き、`--refresh-prompts` は新フラグなので無し（R1-FRZ Merge-03）。instrument と記していたが CLI 動作（R1-NS F-15）。出典: CU-15
- P1-14.7 非 macOS の手引き（`install-schedule --print`・systemd / cron の最小例・`--uninstall` の darwin 判定）: 実行機は 1 台（CLAUDE.md:38）。P1-09.20 の OS 前提宣言 1 行と D-P1-09-3 A（宣言のみ・cron 例は同梱しない）で代替（R1-OWN Prune-05、R1-NEW F1 で P1-09 と統一）。neutral 出典: CU-29
- P1-14.8 `--help` を導線順に組み直す（グループ化・internal 非表示・template 一覧・内部史の除去・report の対比）: 第三者の初回体験は P0-05 の preflight で解く。help の並びは触る時だけ（R1-OWN Prune-06）。延期（neutral: 触る時だけ・凍結後）。`run --help` の `--session` 範囲 1..1440 は P0-05.4、`--guarded` の旗位置の例は P0-05.10 (e) に移した（R1-NEW F7）。出典: CU-35 CU-36 CU-40 CU-41


### P1-15 relevance face の較正と face ループの昇格（RFC-0047）
- enforce を取り消して shadow へ戻す / 「予測不成立時の戻し条件」を事前登録して gate を揺らす: face gate は 2026-10-04 に keep で決着済み（`rfcs/0046:180`）、不成立は問いの単位（行 vs post）の誤りとして記録され、post 単位では予測との差 7.5 pt。戻すことは公開面の出力をもう一度動かす行為。整合分類: value-steering-risk（元項目の分類どおり）。計測部分（再較正）は .2 に取った。出典: OI-32
- 位置バイアスを測らずにラベル順ランダム化を seam に入れる: .4 の読みが先（instrument → mechanism の順序、ADR-0071 の規律）。入れるかは .4 の結果を条件に別途 RFC（R2-DOC F-23）。整合分類: neutral。出典: LP-14（境界として）


### P2-01 北極星の読み値を機械化する（止まる・負荷・自己調節・一致率）
- blind 週（推奨を伏せて裁定）の常設化: 1 回の監査（D-P2-01-2）で足りる。常設すると説明係の材料なしに裁定する週が増え、「分からないまま承認させる」失敗様式（`SKILL.md:136-139`）へ寄る。元項目の整合分類 value-steering-risk（監査の計器部分は .1、実施可否は D-P2-01-2 に吸収）。 出典: WO-06 GO-18
- P2-01.4 「止まる」の読みは P1-01.1 の出力を使う: 中身は P1-01.1 に移り、参照だけが残った番号。「止まる」列の出所（P1-01.1 の `freeze_reading.py`）は .5 の本文に 1 句で書いた（R4-CUT Prune）。neutral 出典: AB-29 OI-20 OI-21


### P2-02 Claude Code 依存の決着（headless 週次セッションの位置づけ）
- なし（この束の入力に capability-growth / value-steering-risk の分類は無い）。ただし選択肢 C を「gemma で週次文書を書かせる本番化」まで広げるのは能力動機の拡大で、計測 1 回に限る。 出典: WO-09


### P2-03 私的ハーネス依存を閉じる（claims.py・release skill・パス・inbox）
- なし（入力に capability-growth / value-steering-risk 分類は無い）。`claims.py`（harness 側 509 行）の全面移植は A の最重量案で、台帳機構を退役した ADR-0095 の向きと逆 — 推奨しない。 出典: WO-14 AB-32


### P2-04 無人チェーンの検知面と停止手順（watchdog・sync・ロック・ディスク・ドリル）
- 通知チャネルの追加（メール・Slack・Webhook）: egress が増え security by absence（ADR-0007 / ADR-0015）に反する。Notification Center + status file + gate Step 0 の 3 面で閉じる。capability-growth 出典: WO-25
- P2-04.6 既知の失敗の 48 時間後再通知: 読み手は土曜ゲートの `PIPELINE-STATUS.md`（SKILL.md Step 0(c)）で、平日に鳴らしても応答者がいない（公務員・趣味）。`notified: <時刻> rc=<n>` を status file に残す部分だけ .17 に吸収（R1-OWN Prune-11、R1-SRE F5）。repair（却下した修理の形） 出典: WO-25
- off-host ミラー heartbeat（data repo の GitHub Actions）: ADR-0093 evidence（`cloud-routines-consideration.md:84`）で signal-first 保留（「次に見逃しが起きたら建てる」）、トリガー未発火。延期（neutral、トリガー「次に見逃しが起きたら建てる」） 出典: DE-10
- watchdog による自動停止・自動修復（launchd unload、失敗時の Ollama 自動再起動、platform 不通時の静止）: 止める判断は「責任を取る行為」で人間のもの（BRIEF §3）。検知と非 0 終了までに留め、判断は P4-01 の検討イベントへ。neutral 出典: DE-42, WO-23, AR-37
- P2-04.20 平台の moderation 状態（`is_spam` / `is_deleted` / `is_locked` / `verification_status`）の読み手を drift scan に置く: key が平台から実際に返るか未確認の「念のため」計器で、撤去条件は「26 週 0」だった。常設の行は落とし、P1-07.5 の census 規則 PR で `content_status` の非 null 件数を `jq` で 1 回数えるだけにする（P1-07.5 の 1 句。P3-05.14 (c) の依存もこの 1 回の計数）。延期（instrument、トリガー: その 1 回の計数が非 0 — その時に行を建てる）（R4-CUT Prune）。出典: R2-PLAT-02


### P2-05 公開に出す責任の接点（2 層公開・承認記録の投影・値層の縦断）
- episode log（untrusted 本文）と計器ログの b64 本文列の公開: ADR-0007 / DATACARD「Excluded data」のとおり非公開を維持し、投影は自己書き込み欄のみに限る。neutral（security 層の absence 維持） 出典: OI-48 RF-38


### P2-06 週次ゲートの読み量を減らす（carried・陽性のみ・多軸 join）
- なし（入力に capability-growth / value-steering-risk 分類は無い）。3 軸を 1 値に合成する表示（`docs/adr/0080:206-208` で禁止）と、reply_rate を archive / adopt の判定に流す経路（ADR-0106 D6）は作らない。 出典: OI-23 CP-23
- P2-06.5 提案の出所の集中度（counterparty 分布）を sidecar に書く: 消費計画 (b) が「探索的、2027-Q1 で継続可否」で、読みが動かす決定が無い（ADR-0101）。延期（instrument、Layer: research、トリガー: P2-06.2 の 3 軸読みで出所の偏りが裁定理由に 2 回出た時）（R4-CUT Prune）。出典: SA-22


### P2-07 RFC-0048 出口の自己維持と knowledge の保持方針
- 層 1 に LLM の verdict を入れる: ADR-0105 が gemma を退役の判定者にしない（Blind Curator の false-pass 偏り）と決めており、RFC-0048 も再提案しない。整合: capability-growth 相当。 出典: WO-36 VL-18
- store の数値キャップ: ADR-0105 D5「No merge, no supersede, no numeric cap」。件数を絞るなら「互いに区別できる」性質で置く（RFC-0048 09-26 追記の問い）。整合: neutral（ADR で既に却下）。 出典: VL-13


### P3-01 研究問いの操作的定義（研究問い ADR・統計方針・Q4 の採否）
- （第 4 章 D-P3-01-2 の選択肢として残る）研究用 golden を cloud judge（`claude -p` / claude-sonnet-5）のまま拡張して Q1 の証拠にする: ゼロ API・ローカル再現の前提変更であり、ADR-0101 の下で計器複合体を育てる方向。整合: capability-growth（計器）／前提変更。 出典: RF-10（D-P3-01-2 の B）
- P3-01.4 (d) 単一事例設計（ITS / change-point）の採否とパッケージ名の小節: 境界間隔は 06-17 以降最長 14 日（週次読みなら 1 区間 ≤ 2 点）で境界内比較に使える系列長が無く、ADR-0110:285-290 が同じパッケージ群（ruptures / changefinder / statsmodels …）を 28 点でも却下済み。代わりに系列別の区間長表（P3-02.1 の派生表。旧 P3-02.8）を引く（R2-STAT P-1。項目 .4 は残す）。整合: neutral（方法の小節）。 出典: RF-21


### P3-02 装置の境界表と縦断記録の再構成（regime・研究ログ・.notes の昇格）
- 境界で計器を自動で読む仕組み（RFC-0008 の再起票）: withdrawn 2026-08-30。境界表は静的な記録で足り、新しい計器を建てると ADR-0101 の溶解義務と逆向き。整合: capability-growth（計器）。 出典: RF-14


### P3-03 対照条件（IPD の床・プラセボ憲法・旧版・Care 面・2 体目の判断）
- （第 4 章 D-P3-03-3 の選択肢として残る）第 2 Moltbook アカウントで 2 体目を常設運用する: 前提変更（ADR-0015、ToS 未検討）+ ゲート負荷 2 倍で北極星 A と逆。整合: capability-growth（装置の拡大）。 出典: RF-26 RF-02 → D-P3-03-3 で判断
- Care 基準を関与判断に enforce する（苦のある投稿を優先して返答させる）: オーナーの価値を学習ループに注入する操舵（ADR-0050）。shadow 記録（旧 P3-03.6、下の延期行）までに留める。整合: value-steering-risk。 出典: PF-21
- P3-03.6 Care shadow score（関与判断の横に「困窮・苦を含むか」の 4 択を記録のみ）: 凍結窓の本番 decision seam に 1 post あたり 1 LLM call を足す一方、Care の計器は .5（dialogue 二アーム、本番に触れない、D-P3-03-1 の推奨 B）と二重（R4-CUT Prune）。延期（instrument）— 第 5 章の延期行。トリガー: .5 の読みで shadow 側に care register が出た時。再開時は旧項目の 3 条件（本番経路の外・ADR-0101 の消費計画・判定者昇格は ADR-0056 の supersede）を RFC に書く。 出典: PF-21
- P3-03.3 後半 改正文を rules の standard protocol（20 rounds × 6 opponents、n=10）で baseline 対比する: original protocol には null pair も床も無く（較正は paper protocol のみ、ADR-0090 .ja:51-62）、読めない数字が 1 表増えるだけで ADR-0071 の signal-first に反する。非 verbatim の憲法文を rules repo に置くことにもなる（rules ADR-0002 / 0003）（R1-FLIP Prune-01、R1-SIB Fix-07）。整合: instrument（読み手の無い計器）。 出典: RF-25 SB-31
- （第 4 章 D-P3-03-2 の選択肢として残る）AILuminate を cloud judge のまま常設計器にする: ゼロ API 前提の変更 + 消費計画の無い計器成長（ADR-0101）。整合: capability-growth／前提変更。 出典: PF-06 RF-42 → D-P3-03-2 の C


### P3-04 identity・憲法の版履歴と縦断計器（history・CHANGELOG・drift・複利）
- P3-04.7 却下された staged 候補の本文を保全する（参照だけの残骸）: 保全先は P1-12.2 の 1 か所で、本項目は参照だけだった。番号を消し、.3 の却下行の読み元を P1-12.2 と書いた（R4-CUT Prune）。neutral 出典: VL-07 VL-28(本文) PF-13
- 補足: 元 32 件に capability-growth / value-steering-risk 分類は無い。identity に前版 seed を戻して「安定」を作ること、改正入力 view（`constitutional.md` 0.55 / top-50）の閾値を広げて自己類似を「直す」ことは操舵になるので、本束では記録（.3 / .4）に留める。


### P3-05 公開データセットの研究再利用性（DATACARD・schema・DOI 版・HF・再現ガイド）
- （第 4 章 D-P3-05-6 の選択肢として残る）採用済み skill 本文の所有者書き換え（D-P3-05-6 の A）: 読みやすさのための文面統一でも observation-over-steering（ADR-0050/0051/0052）に反する値層介入になる。読者向けには「例外の記録」で足りる。value-steering-risk（統合担当の判断。元項目は neutral）出典: VL-12
- （第 4 章 D-P3-05-2 の選択肢として残る）平台側で削除された投稿を月次に既存 endpoint で再照会し `[deleted on platform]` に置換する（.14 (c) の C）: 新しい外部 I/O 面が増える（ADR-0015 内の既存 endpoint に限っても月次 job と api-audit の読み手が増える）ので、依頼ベース（.19）と「観測時点の写し」の 1 文で足りる間は採らない。整合: capability-growth（I/O 面）。 出典: R2-ETH-07
- P3-05.15 HF の多 config 化（patterns / skills / identity_history / constitution_history / decisions）: 消費者は仮定の第三者で継続可否も「探索的」、R1 の P3-06.8「publish and wait」と同じ理由（R4-CUT Prune）。延期（instrument）— 第 5 章の延期行。トリガー: HF で config の要望が 1 件来た時か論文 cutoff（P3-06.3）の時。再開時は D-P0-03-3 の表示名の扱い（skills 1 件、`snapshots/*/skills` 100 ファイル）を前提にする。 出典: RF-36


### P3-06 論文・FLIP 供出・AAP への書き戻し・哲学読みの計器
- P3-06.11 後半 ADR-0080 に「capability 語は行為の質」の 1 行: 読み方の注で北極星の定義でも完成条件でもなく、ADR-0080 を 1 行でも変えると CLAUDE.md §北極星の同 PR 同期が要り、追補を（2026-11）（2026-12）の 2 本に絞る規約とも食い違う。glossary (1)(2) の 1 句で足りる（R3-ADR Prune-01。項目 .11 は残す）。neutral 出典: PF-26 PF-29 PF-40
- P3-06.8 拡散の四半期読み（HF downloads・Zenodo views・引用・派生）: オーナー方針は「publish and wait」。読みが決める決定が無い計器は ADR-0101 で建てない。見るなら年 1 回 HF の数字を手で見る（R1-OWN Prune-10）。整合: instrument（消費計画の無い計器）。 出典: RF-53
- P3-06.10 後段の計器 2 本を RFC で予約する（固着率・内省一致率）: 消費計画 (b) が「探索的: 実装するか withdrawn にするか」で、予約そのものが成果物（R4-CUT Prune）。延期（instrument）— 第 5 章の延期行。トリガー: .9 の 4 週読みが陽性で D-P3-06-3 が A 以外の時。再開時の床・陽性対照は LLM を使わない冒頭 3 語の月内反復率（公開本文から計算できる）。(2) は ScoreQuestion を使うので、再開時は判定者 3 条件（本番経路の外・ADR-0101 の消費計画・昇格は ADR-0056 の supersede）を RFC に書く。 出典: PF-02 PF-08
- （第 4 章 D-P3-06-3 の選択肢として残る）沈黙ルール・即時修正ループを所有者が書く: Mindfulness / Care を「実装する」ための機構追加は、読みの前では operator steering。value-steering-risk（.9 の読みが陽性なら D-P3-06-3 で再審）。出典: PF-04 PF-20 PF-42
- 公理 / ルール分離（空性のみ公理）を FLIP に提案する: 現行機構では所有者の価値操舵（P3-07 の判定事項）。memo §提示戦略も「今回のスレッドでは出さない」。value-steering-risk。出典: RF-41 RF-44（FLIP メモ §論点3）
- 実コメントを LLM judge で採点して carewashing を判定する: ADR-0106 D4 で不採用済み。決定論的列（.9）に限る。neutral。出典: PF-07
- 助成金・商用化・査読料のかかる投稿先・人員拡大を前提とする経路: オーナーは公務員で趣味（CONTEXT §4）。neutral。出典: RF-52（選択肢「査読会議・誌」）、CONTEXT §4


### P3-07 「空性のみ公理」案と価値層への介入チャネルの決定
- 本番エージェントの憲法を「空性のみ」に書き換え、三原則を手書き rules に移す: 所有者の言葉が価値層を運ぶ = ADR-0050 / ADR-0097 の観測姿勢からの離脱、改正可能性の配分反転（三原則の物象化）。整合: value-steering-risk。 出典: PF-15 PF-17 → D-P3-07-1 で判断（A / C を推奨）
- ADR-0017 L73 の再バランス手段（prompt weighting・公理順序の操作・`distill_identity` への「transform」文言）を実装する: ADR-0050 以降の observation-over-steering に反する価値操舵（ADR-0057 は同じ理由で reframe を neutral に保った）。整合: value-steering-risk。 出典: PF-03
- rules 層に三原則用の LLM 生成経路（generator）を新設する: ADR-0097 が rules を小さく保ち family 昇格のみとした決定に反する機構拡大。B 案の受理条件（改正経路）は A′ の家族昇格か shadow 対象化で足りる。整合: capability-growth。 出典: PF-17


### P4-01 終了判断の検討イベントと判断役を予約する
- 終了「条件」の事前登録（RFC-0006 の再起票）: オーナーが「今は問いでない」と決めた（2026-09-28）。条件を決めずに検討イベントだけ置く。neutral 出典: AB-15, DE-31, DE-40
- SNS Protocol の新設・他 platform への移植: capability-growth。縦断記録は 1 platform で閉じる 出典: AR-30
- P4-01.4 D-P3-05-1 の版付け規則を論文 cutoff に適用する: 決定（旧 D-P4-01-4）は削除済みで本文も「この束では決めない」の参照だけが残っていた。番号を消し、順序の 1 文（2027-Q2、P3-06.3 の後）は P3-06.3 の完了条件が持つ（R4-CUT Prune）。neutral 出典: RF-50
- （第 4 章 D-P4-01-3 の選択肢として残る）ゲート不在時の自動 read-only 化・自動停止: 責任の行為を機構へ移す。検知（P2-04）と検討イベント（本束）までに留める。neutral 出典: GO-39


### P4-02 wind-down runbook（手順のみ・発動条件を持たない）
- runbook に発動条件を持たせる（例「episode 0 件 N 日で自動実行」）: 発動は P4-01 の検討イベント + 人間判断。neutral 出典: DE-32, DE-42
- 退会 API の client 実装: 1 回しか使わない能力追加で、client に呼び手が無い（drift state は呼んだ endpoint の応答 key しか持たず、平台側の有無の証拠にはならない — 有無の確認は P1-07.19 の台帳行）。手動で行う。capability-growth 出典: DE-36
- 別 platform への移植・SNS Protocol: P4-01.1 で「しない」と決める。capability-growth 出典: AR-30
- P4-02.4 の Status 行日付形式の常設検査（`scripts/docs_consistency_scan.py`）: 期間表記の Status 行が書かれるのは終了時の 1 回だけで、終了後は scan を読む人もいない。1 回きりのイベントに常設検査を置かない（ADR-0101）— runbook 手順 (4) の確認コマンド 1 行で代える（R3-END P-1）。neutral 出典: DE-37


### P4-03 継続性（bus factor 1）・引継ぎ・インシデント手順
- 複数人運用・組織移管への準備（on-call ローテ、committee）: オーナーは「完全に趣味」で人員拡大を前提にしない（CONTEXT-FROM-CHATS §4）。AAP 0008 の team operation は permits だが CA は 1 人 1 体。neutral 出典: GO-25
- 継承者への credentials の事前共有・封緘: 最小権限に反する。継承者は `register --name` で再登録するか archive のみ。neutral（security-absence 維持） 出典: DE-44


### 横断（束に属さない却下・延期）
- **資金獲得・商用化・有料配布・人員拡大を前提にする項目**: オーナーの立場上、外部資金を受け取れず、趣味として続ける方針（旧チャット 2026-05-27）。助成金申請やスポンサー募集はロードマップに載せない。
- **大型モデル / cloud backend を本番既定にする提案**（例: insight の圧縮器を opus 級に置換する「形 D」）: M1 16 GB・ゼロ API の前提を変える。研究用の対照アーム（P3-03）としてのみ扱い、本番経路には入れない（ADR-0067）。
- **人間ゲートの溶解（LLM の判定が人間の裁定を置き換えること。無人 adopt を含む）**: ADR-0080 08-26 追補 §A が 2026-08-26 に明示的に却下（0080:189-196「人間の言葉はゲートの attribution の錨」）。負荷を下げる手段は自己調節と読み量削減（P2-01 / P2-06）であり、人間の言葉を外すことではない。RFC-0048 層 1 の「決定論の自動退役 + 事後報告 + 復元権」は溶解とは別物として扱うが、ADR-0105 en:104「無人チェーンは store に触れない」と境界を接するので、ADR-0080 への dated amendment と ADR-0105 の partial supersede を前提条件にした決定（D-P2-07-1、P2-07.5）として残す。「可逆だから」はゲート省略の理由にならない。
- **ホスト型クローズドウェイトの判断 backend（RFC-0040 Jev）**: open weights かつ Ollama / mlx_lm.server で起動できるまで本番経路には入れない。RFC の終端（withdraw か blocked 継続か）は D-P1-02-1 で決める（第 4 章 D-P1-02-1 の選択肢として残る。推奨 withdraw、withdraw 条件は ADR-0112 の Review-when に転記）。研究ラベル付けの真値 judge としての cloud 利用（Jev / opus）は別の問いで、D-P1-15-2 / D-P3-03-4 に「前提変更」として明示してある。
- **自動停止・自動修復（watchdog がセッションを kill / 再起動する、Ollama を再起動する等）**: 検知と非 0 終了まで（P2-04）。「止める」判断は人間の行為として残す。
- **Moltbook 閉鎖時の他プラットフォームへの移植**: 最終成果物は縦断記録（データセット + 論文）であってインスタンスではない（ADR-0080 第 5 項）。閉鎖は P4-01 の検討イベントの 1 つ。
- **2 体目のエージェント・dialogue の本番化**: ADR-0080 の「別の実験」であり本インスタンスの完成条件ではない。P3-03 で研究上の採否だけを決める。
- **価値層の内容へのオーナーの直接介入**（「空性のみ公理」案を現行インスタンスに適用する、特定テーマの skill を手で足す等）: observation-over-steering に抵触。P3-07 の決定事項（別 preset / 別インスタンスでの実験に限る）として扱う。
- **新しい LLM 判定者の追加**（importance scorer の復活、worth judge の再導入、自己採点の gate、score4 後段の「沈黙」enum = D-P3-06-3 B（第 4 章 D-P3-06-3 の選択肢として残る）等）: ADR-0056 / ADR-0097 の ablation・退役証拠が立ったまま。08-26 追補 §B は軸を名指すが判定者は名指さない。復活は ADR-0056 を明示的に supersede する ADR が前提。shadow / 研究ラベルは第 0 章の 3 条件を満たす場合のみ instrument として本文に置く（P3-03.6、P3-06.10）。
- **ロードマップの決定を推奨どおりに自動採択すること**: 推奨↔裁定一致率 100% は「実質の判断主体が Claude」の兆候として本文書自身が value-steering-risk に分類している（VL-36、D-P2-01-2）。既定可の決定でも `decision` は人間が `gate_item` に打つ（第 4 章の記録規則）。


## 付録

- 付録 A: 全項目表（779 項目 → 39 束の対応、統合先つき）… [`appendix-all-items.md`](appendix-all-items.md)
- 付録 B: 作成方法（B.1）、反復ラウンドの記録（B.2）、読んだもの（B.3）・確認できなかったもの（B.4） … [`appendix-method.md`](appendix-method.md)
