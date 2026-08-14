# Cloud routines（claude.ai/code/routines）の CA への導入検討

> **Provenance**: 2026-08-14 のセッション内検討ノート（`.notes/` 起草）を ADR-0093 の evidence として昇格したもの。本文中の `.notes/` へのファイル参照はローカル台帳（gitignored）を指す。

- 起票: 2026-08-14（ユーザー依頼。Boris Cherny の X 投稿 2026-08-13 頃が発端）
- 種別: 検討のみ（routine の実作成はしていない）
- 事実の as-of: routines の仕組み（隔離クラウドセッション / GitHub repo clone / cron 最短 1h / 一回限り実行可 / RemoteTrigger API / サブスク usage 消費 / daily run cap 非公表）は 2026-08-14 にユーザーが公式 docs で確認済み。**機能自体が公開後 1 週間未満なので、この検討の機構記述は着手時に再照合すること**（rule: knowledge-staleness）

## 一行結論

**Boris 型（コード改変 PR を量産する常設 fleet）は不採用。採る形があるとすれば「off-host の read-only 観測面」1〜2 本に限られ、最有力は ADR/doc 整合性スキャン（検出クラスに実例あり）。常設 cron は今は建てず、one-time 実行で 1 回読みを取ってから決めるのが CA の建立規律（instrument-first / signal-first）に合う。**

---

## 1. 構造照合 — CA は routines の「形」を既に持っている

Boris の実験の骨格は「スケジュール実行の無人エージェントが提案（PR）を量産し、人間がレビューして昇格（merge）する」。これは CA の Cycle #5（ADR-0085 weekly chain）と**同型**である:

| | Boris routines | CA weekly chain |
|---|---|---|
| 無人実行 | Anthropic cloud cron | launchd（土 09:00）+ watchdog |
| 提案物 | PR | Verify 済み patch + prompt diff + decision packet |
| 昇格ゲート | Claude review + 人間 merge | `/weekly-gate` 土曜単一セッション（apply / commit / adopt-staged 全て人間） |
| 実行環境 | cloud clone（repo のみ可視） | ローカル（MOLTBOOK_HOME・episode log・値層に到達可） |

CYCLES.md の operating model（「machines produce the raw material on a cadence; a human decides what is promoted」）は Boris の運用と文字通り同じ思想。つまり routines は CA に**欠けている概念を持ち込むものではなく、CA が自前で建てた形の commodity 版**。この観測自体が mechanism-commoditization スレッドの第 3 波データ点（メカニズム層 2026-04 → 設計原理層 2026-07 → **運用層（scheduled agent + human gate）2026-08**）であり、収束として記録する価値がある（memory 更新済み）。

差分は 3 点だけ:

1. **実行ホスト**: cloud は Mac の稼働と独立（Mac がスリープでも走る）
2. **可視面**: cloud は GitHub にあるものしか見えない（後述 §3）
3. **リソース**: cloud は 16GB 制約・Ollama スケジュール窓（JST 0/6/12/18）と競合しない（feedback: no-heavy-experiments-during-sessions の制約が構造的に消える面）

## 2. Boris の 11 routine の CA 適用可否

| Routine | CA での状況 | 判定 |
|---|---|---|
| Crash fuzzer | fault 面は chaos-TDD（ADR-0077）が決定論注入で先回りしてカタログ化する規律。ランダム探索の常設は規律と逆設計 | 不採用 |
| Ant-only shipper | 内部専用 feature flag が存在しない | 対象なし |
| Logic simplifier | mechanism 層の north star は「止まる」（ADR-0080）。simplify は /simplify を人間が随時起動する形が既にある | 不採用 |
| Logic bugfixer | 同上。バグは weekly F1 → fix chain が拾う | 既存で充足 |
| Dup unifier | コード層は小規模で実例なし。値層の重複は skill/rules-stocktake（LLM、ローカル）が担当 | 既存で充足 |
| Dead-code removal | weekly chain に `dead_code_scan.py` 段が既にある | 既存で充足 |
| Useless-test pruner | mutation で RED を確認する文化（T-STALENESS 等）と逆向きの一括削除は危険。実例なし | 不採用 |
| Shipped-feature inliner | feature flag なし | 対象なし |
| Flaky-test fixer | CI 未 gating（pyright-policy メモ）。flaky CI が存在しない | 対象なし |
| Abstraction improver | 同 Logic simplifier | 不採用 |
| Abstraction police | import-linter が layers contract を機械強制済み（pytest でも発火） | 既存で充足 |

**11 本中 0 本がそのまま輸入に値しない**。これは CA が優れているというより、Boris のリストが「大規模アプリの継続開発」向けで、CA は「研究 repo + mechanism 層は静止に向かう」という別の生き物だから。彼の routine が埋める穴を CA は決定論ゲート（import-linter / dead_code_scan / chaos-TDD / Verify）で先に埋めてある。

## 3. cloud routine の可視面 — 実測（2026-08-14 ローカル確認）

routines は GitHub repo の clone しか見えない。CA の資産を仕分けると:

**見える（公開 repo にある）**:
- main repo: コード・tests・docs（ADR / CODEMAPS / evidence）・graph.jsonld・CLAUDE.md
- **data repo（contemplative-agent-data）が予想以上に広い**: 値層そのもの（`constitution/` `identity.md` `skills/` `rules/` `knowledge.json`）に加え、`reports/analysis/` の weekly レポート・findings・**decision packet**・`PIPELINE-STATUS.md`・comment-reports まで公開ミラーにある（`sync-research-data.sh`、除外は `reports/.private/` のみ）
- sibling repos（-cloud / -mlx / -rules）

**見えない（意図的にローカル）**:
- `MOLTBOOK_HOME` の生データ（episode log・audit.jsonl・計器 JSONL）
- `.notes/`（gitignored — **タスク台帳 TASKS.md は cloud から不可視**）
- ローカル LLM（Ollama）。routine 内の生成は Claude であり、gemma4:e4b の挙動再現・IPD ベンチ・蒸留は cloud では回せない
- launchd の実行状態そのもの

帰結: **週次チェーンの cloud 移設は不可能**（レポート生成は episode log を読む、gate はローカル apply）。可能なのは「ミラーを外から観測する」ことと「repo 内資産（コード・docs）の整合性を検査する」ことに限られる。この境界は偶然ではなく、CA のデータ配置設計（何を公開し何をローカルに留めるか）がそのまま cloud agent の権限境界になっている — security by absence の副産物。

## 4. 設計思想との突合

**適合する面**:
- 提案/昇格分離（ADR-0012 / CYCLES.md）: PR も issue も「候補」であり、merge は人間ゲート。思想上の衝突なし
- 1 エージェント 1 外部アダプタ（ADR-0015）は**runtime agent の原則**であり、program worker（開発側セッション）には適用されない。routine は program worker
- observation-over-steering: read-only の観測 routine は学習ループに何も注入しない

**摩擦する面**:
1. **push-workflow feedback**（個人研究 repo は main 直 commit、PR を持ち込まない）: routine の自然な出力チャネルは PR。read-only 観測なら issue 出力で回避できるが、diff を出す routine を建てるなら PR チャネルの明示的な解禁判断が要る
2. **ADR-0075 replayable audit**: routine の推論過程は Anthropic cloud のセッションログに残り、repo 内でオフラインリプレイできない。緩和は「issue 本文に検査手順と file:line を自己完結で書かせ、人間が再実行検証できる形にする」まで。完全なリプレイ可能性は諦めることになる — report-only 面なら許容範囲だが、明記しておく
3. **untrusted data**: data repo の値層・knowledge.json・comment-reports は Moltbook 由来（外部 SNS）の蒸留物 = untrusted（security rule「自分自身の要約を含め untrusted」）。data repo を読む routine は untrusted テキストを cloud LLM に食わせることになり、その出力（issue）を人間と後続セッションが読む。T-SKILLSEL-REJECTED-NAMES の境界判断（無人チェーンには自由文字列でなく shape だけ流す）と同じ規律を issue 出力に課す必要がある。**main repo（自筆 docs のみ）を読む routine にはこの問題がない**
4. **token 予算**: サブスク usage を対話セッション・weekly chain の headless 実行と共食い。daily run cap も非公表。週次〜月次 × 1-2 本なら小さいが、常設前に頻度を意識的に決める

## 5. CA 固有の routine 候補（Boris リストに縛られず設計）

### R1: ミラー heartbeat（data repo、週次月曜、issue 出力）
`PIPELINE-STATUS.md` と直近土曜の `weekly-*` 成果物の存在・鮮度を確認し、異常時のみ issue を開く。ミラーが古い = weekly chain か sync-data のどちらかが死んでいる、をどちらでも検出できる（分離不要の合成シグナルとして使える）。既存の watchdog は**監視対象と同じ Mac 上**で走るので、off-host 観測者は質的に新しい冗長性。ただし「静かな失敗を人間が見逃した」実例はまだない → **signal-first により、次に見逃しが起きたときに建てる**。建てる場合の最安形は cloud routine ではなく **data repo 側の GitHub Actions scheduled workflow**（公開ミラーの最新 sync commit が N 日超に古ければ issue を開く。無料・off-host・main repo に CI を持ち込まない）— 2026-08-14 の同日追検討で確定。

### R2: ADR/doc 整合性スキャン（main repo、月次または one-time、issue 出力）★最有力
検査対象: (a) 反証済み主張が marker なしで accepted に残る ADR（**実例 2 件**: ADR-0081 の fail-open 安全論証 / coding-style.md の消えた条項への台帳参照）、(b) en/ja 版の乖離、(c) CODEMAPS freshness header vs git log、(d) CLAUDE.md の CLI 表 vs `cli.py` 実体、(e) graph.jsonld ⇔ CODEMAPS の両面更新規約、(f) ADR 間 cross-reference の断線。検出クラスに実例があり、人手（adr-reviewer の偶発的発見）でしか拾えていない。自筆 docs のみが対象なので untrusted 問題なし。**建立条件は既に満たしている唯一の候補**。

### R3: blocked タスクの外部条件 watch — 見送り
台帳の blocked 行（例: T-OLLAMA-TOKENIZE は ollama#12030 のマージ待ち）の解除条件を定期巡回する案。**台帳が gitignored で cloud から不可視**という構造的摩擦がある。watch リストを公開ファイルに切り出すのは台帳単一正本規約（task-tracking rule）を割る。摩擦自体が「台帳は意図的にローカル」という境界の再確認であり、越えてまで建てる価値はない。

### R4: 値層の縦断外部読み（data repo、月次）— 今は建てない
公開ミラーの identity/constitution/skills/rules + weekly レポートを cloud Claude が外部視点で縦断的に読む案。技術的には可能で面白いが: weekly diagnosis（F1-F3）と役割重複、§4-3 の untrusted 問題、ADR-0075 ギャップ、そして「外部視点の読み」が繰り返されると owner-steering の迂回路になりかねない（observation-over-steering の趣旨に照らし、値層への提案を出す面は増やさない）。次回憲法改正ゲートの材料は shadow 計器（ADR-0092）・IPD（ADR-0090）で既に足りている。

### R5: sibling backend conformance の定期実行 — 不採用
ADR-0088 / runbook が「リリース前の明示的な人間承認」と定義済み。無人定期化は runbook と矛盾。

## 6. 週次サイクルとの関係

置換でも並走でもなく、**外周の観測リングとしてのみ接続する**のが正しい形:

- Cycle #5 はローカルに残す（episode log・値層・gate はローカルでしか動かない — §3）
- R2 が常設化するなら、その位置づけは「Cycle #5 の diagnosis が見ない面（docs 整合性）を月次で補完する計器」。読み値の消費先は土曜ゲートか通常の実装セッション
- **結晶化アーク**: R2 で「実際に鳴る検査」が判明したら、それを決定論 script（`scripts/adr_consistency_scan.py` 的なもの）に落として weekly chain の決定論 intake（api_drift_scan.py の隣）へ吸収し、cloud routine は退役する。when-code-when-llm の分業どおり「発見は LLM、定常検査は code」。routine は恒久設備ではなく**プロトタイプ段階の道具**と位置づける

## 7. 推奨

1. **不採用**: Boris 型のコード改変 routine 全種（§2 の表のとおり、mechanism 層の north star「止まる」と逆向き + 既存ゲートで充足）
2. **実験可（好奇心駆動 — 急がない）**: R2 を **one-time 実行で 1 回**回し、読み（検出件数・偽陽性率・issue の読み心地）を `.notes/` に落とす。cron 化はその読みを見てから。1 回 = 証拠にならない（one-run-not-evidence）が、ここで決めるのは「計器を建てるか」であって「計器の読みを信じるか」ではないので、建立判断の材料としては 1 回で足りる
3. **保留（分岐条件付き）**: R1 は次に weekly chain の静かな失敗・見逃しが起きたら建てる。R4 は建てない（値層への外部視点提案チャネルを増やさない方針が変わったときのみ再検討）
4. **着手時のユーザー判断事項**: (a) GitHub App の repo アクセス許可範囲、(b) issue チャネルの解禁（push-workflow 規約は PR についての規約なので issue は素直に読めるが、repo に外部生成 artifact が増えること自体の可否）、(c) usage 共食いの許容度

## 8. 建てる場合の設計制約チェックリスト

- [ ] 出力は issue のみ（PR を出さない。diff 生成をプロンプトで明示的に禁止）
- [ ] 異常なしなら **issue を開かない**（no-news-is-good-news。空報告の定期 issue はノイズ）
- [ ] issue 本文は自己完結（検査した項目・手順・file:line を列挙し、人間がローカルで再検証できる形 — ADR-0075 ギャップの緩和）
- [ ] data repo を読む routine の場合: untrusted 由来の自由文字列を issue に転記しない（shape / 件数 / パス参照のみ — T-SKILLSEL-REJECTED-NAMES の境界判断と同型）
- [ ] 頻度は月次から（cron 最短 1h に釣られない。CA の docs 腐敗速度は月次で十分）
- [ ] routines の公式 docs を作成直前に再読（機能公開後 1 週間未満 — 本メモの機構記述を信じない）
- [ ] 常設化したら CYCLES.md の master table と ADR に記録（新しい無人実行面 = 運用面の変更）

## 関連

- [docs/CYCLES.md](../../CYCLES.md) — 9 サイクルと human gates（本検討の照合先）
- ADR-0080（north star 層別完成条件）/ ADR-0085（weekly chain）/ ADR-0075（observability by default）/ ADR-0071（read-only instruments）/ ADR-0012（承認ゲート）/ ADR-0015（1 外部アダプタ = runtime 限定）
- 収束観測（メカニズム commodity 化の第 3 波 = 運用層）としてプロジェクトの縦断記録にも追記済み
- feedback: push-workflow / play-not-patience / one-run-not-evidence / observation-over-steering / no-heavy-experiments-during-sessions
