# ADR-0085: 無人 weekly fix チェーンと土曜単一ゲート

## Status

accepted

## Date

2026-07-29

## Context

週次内省サイクル（CYCLES.md の Cycle #5）には人間の手動介入点が 3 つあった:
土曜レポート後の `/weekly-report-diagnosis` 手動実行、F1 findings の手動実装、
`adopt-staged` による staging レビュー。介入点のそれぞれがサイクルの停滞点であり、
オペレータがレポートを数日遅れで開く運用は、2026-07-25 の障害（死んだ launchd
実行が 0 byte レポートを出荷）が読む時点まで発覚しなかった構造そのものである。

ADR-0040 は診断の自動化を意図的に開けたままにしていた（「cron 側の自動化は本 ADR の
スコープ外」）。さらに進める際の制約面は文書化済み: CYCLES.md は人間所有の昇格エッジを
2 つ挙げ（#5 findings → code、#6 実装 diff → commit）、ADR-0012 は行動改変コマンドの
`--auto` を禁じ、ADR-0013 は有能なモデルが承認ゲートの両側に座るとゲートが共著ループに
縮退する機構を記録し、ADR-0050 はゲートを「containment であって training signal では
ない」と定義している。

診断品質は無人実装が現実的になる閾値を越えた: 2026-05-17 週の F1 はコード照合で
3 件中 3 件誤りだったが、2026-07-24 週の F1 は行番号検証済みの複数サイト参照と
実レンダリング再現を伴っていた。

## Decision

`scripts/weekly-pipeline.sh`（launchd `com.moltbook.weekly-pipeline`、土 09:00、
`--weekly-analysis` を置換）を出荷する。既存レポートを Stage 1 として実行した後、
診断（既存 skill を別の headless `claude -p` セッションで）、決定論的 F1 パース
（`scripts/parse_findings.py`）、使い捨て git worktree での per-finding 修正実装と
オーケストレータ実行の Verify、第 3 セッションでの advisory fix レビュー、insight
staging の advisory レビュー、決裁パケット（`scripts/build_decision_packet.py`）を
連結する。コミットする約束事:

1. **機械は commit も push も adopt もしない。** 昇格はすべて土曜の `/weekly-gate`
   セッションで行う: 承認 patch の apply → 再 Verify → 人間の単一 commit、
   `adopt-staged` もそこで実行。CYCLES.md の 2 つの昇格エッジは 1 セッションに
   統合されて存続する（human-gate.md の 1 作業 1 ゲート）。
2. **パース時のスコープ分割。** `src/ scripts/ tests/` に閉じる F1 は `code`
   スコープ（自動実装・Verify ゲート・patch 出力）。行動形成系 artifact
   （`config/prompts/`・`.claude/` 等）に触れる F1 は `prompt` スコープ: diff 案は
   作るがゲートで本文全文提示、Verify 認証はしない。曖昧なら `prompt` に分類。
   F2 は人間専用のまま。
3. **役割分離はセッション間で維持する**: 診断者・実装者・レビュアは別々の
   fresh-context `claude -p` 起動（ADR-0013 の失敗機構は*共有された*会話文脈
   だった）。レビュアの verdict は人間ゲートへの参考情報 — LLM 単独の承認経路は
   存在しない。
4. **有界の反復**（coding-style の Iteration Bounds）: fix 試行はラウンドあたり
   ≤ 2、finding あたり ≤ 1 + MAX_REVIEW_ROUNDS ラウンド（再試行の入力には Verify
   失敗出力を含める — 同一入力の再試行はしない。2026-08-01 Amendment が原文の
   「1 finding あたり ≤ 2」から改訂）、週 ≤ 5 findings、セッション毎 timeout、
   全体 3 時間の wall-clock deadline。上限到達はすべて reason code として packet
   に載る。
5. **packet への fail-forward。** 全 stage の失敗は reason code になり、packet は
   常に生成を試みる（Stage 1 のレポート欠如のみ abort）。したがって packet の不在は
   「チェーンが起動しなかった/即死した」ことを意味し、それこそが watchdog の検査対象。
6. **独立 watchdog**（`scripts/pipeline_watchdog.sh`、launchd
   `com.moltbook.watchdog`）: 純 bash — 監視対象と PATH 依存（claude・uv・python）を
   意図的に共有しない（2026-07-25 の障害は PATH 依存だった）。各 job の**終端成果物**を
   期間アンカー付き期待表で検査し（レポート ≥1KB 土 12:00 まで、packet 13:00 まで、
   insight/distill/backup はログの liveness）、毎回 `reports/PIPELINE-STATUS.md` を
   書き直し、失敗集合が変化したときだけ通知センターに通知する。セッション hook の
   面は持たない: 大部分のセッションはこのパイプラインと無関係であり、status は消費
   される場所で読む — gate セッションの Step 0。
7. **自己計測と減衰付き自己修正ループ。** `logs/pipeline-metrics.jsonl` に実行毎の
   `phase:"auto"` と決裁毎の `phase:"gate"`（adopt/reject 数、推奨一致率 — F1 的中率
   = adopted / patch-ready）を記録。pipeline 改善提案は同一 reason code が 2 週連続
   したときのみ起草され（診断 skill の P4 と同型）、それ自体も本文全文ゲート。計測は
   毎週、自己編集は証拠があるときだけ — 毎週の自己修正は Scaffold Dissolution の逆行。

## Alternatives Considered

1. **完全無人 commit（Verify green で自動 commit）。** 却下: CYCLES.md エッジ #6 を
   上書きし、却下する第三者が残らない形で ADR-0013 のループを再現する。同一 PR 義務
   （CODEMAPS 鮮度・ADR-0075/0077）は認証される側の当事者が自己認証できない。
2. **診断のみ自動化し修正は手動。** 主モードとしては却下（最大の停滞点 = 実装が残る）
   だが、shadow モードとして出荷: `MOLTBOOK_PIPELINE_STAGES` から `fix` を外せば
   report → diagnosis → packet で走り、初週のロールアウト構成として必須。
3. **チェーンからの `adopt-staged --yes`**（insight 完全自動化）。却下: ADR-0012 の
   `--yes` は監督下の coding-agent セッション向けのライセンスであり、無人スケジューラが
   使えば ADR-0074 が設計の中心に置いた唯一のゲートを消す。チェーンは staging に
   *注釈するだけ*（read-only 推奨）で、ADR-0050 はこれを正当と枠付け済み。
4. **失敗面としての session-start hook。** レビューで却下: 大部分の Claude セッションは
   このパイプラインと無関係で、全セッション注入はノイズ。status ファイル + gate Step 0 +
   通知センターが 3 つの読取時点（任意時 / 決裁時 / 失敗時）をカバーする。

## Consequences

- オペレータの週次関与は土曜 1 セッションに圧縮される。pending guard の停滞
  （未レビュー staging による翌週 insight スキップ）は、staging レビューが gate
  セッションに住むことで構造的にカバーされる。
- ADR-0033 の「Autonomous Agentic Loop 象限をルーティングする CLI はない」という
  観察には脚注が要る: チェーンは stage 単位では agentic だが、ループ自体は硬い上限
  付きの決定論 bash であり、LLM がツール選択や open-ended 反復を行うことはない。
  ランタイムレベルでは主張は生き残り、本 ADR がそのニュアンスを記録する。
- 新しい失敗モード: Verify と APPROVE verdict を生き延びた plausible-but-wrong な
  patch。gate は意図の要約を提示するため人間は diff を再検査しない。緩和はメトリクス
  ループ（誤 adopt は revert commit と翌週の finding として現れる）と、gate で diff
  本文を要求できる昇格規則。
- `install-schedule` の再実行は `--weekly-pipeline --watchdog` を含む全フラグを渡す
  必要がある。渡さなければ宣言的 reconcile が削除する（既知の T-PLIST-LOSS の
  尖り、種類は不変）。
- 診断 skill の F1 見出し + Code reference ブロックは機械契約になった
  （`parse_findings.py`）。SKILL.md にその旨を明記。skill 自身の out-of-scope
  （「F1 は plan であって code 変更ではない」）は不変 — fix は別セッションで
  起きるのであり、それは役割境界が機能しているということ。

## Amendment（2026-07-29）: 4 レビュアーによる hardening ラウンド

初回実装はレビューチェーンなしで出荷された（プロセス違反。オペレータの指摘で発覚）。
commit 後のラウンド — code-reviewer / python-reviewer / security-reviewer / codex
（cross-model）— が収束的な指摘を挙げ、以下の修理が本決定の一部となった:

- **実スコープの強制**: export された patch の**実際の**変更ファイルを決定論で再検査。
  code scope の patch が `src/ scripts/ tests/` 外に触れていたら本文全文ゲートへ格上げ
  （`SCOPE_ESCALATED`）、prompt scope の patch がコードに触れていたら Verify を通す。
  宣言スコープだけが提示内容を決めていた — injection された fix セッションが
  governance ファイルの編集を表 1 行としてゲートを通し得た間隙。
- **セッション権限の縮小**: `Bash(python3:*)` / `Bash(uv run:*)` の grant を撤去
  （任意実行は read-only allowlist を無効化する）。`Edit`/`Write` は worktree に
  パススコープ。`--add-dir` は診断が `reports/` + `logs/`、insight が `skills/` に
  限定され、`credentials.json` は全無人セッションの許可ツリー外。finding 本文は
  `<untrusted_finding>` で包む（ADR-0007 との連続性）。
- **fail-forward の全面化**: 全 artifact 読み込みが非 UTF-8 を理由コード
  （`*_UNREADABLE`）で生き延びる。走査形パス参照は抽出時に拒否。単一行
  `**Code reference**:` 形式（歴史的 findings の約半数）がパースされる。Verify は
  各ステップ個別に時間制限。同週再実行は P4 再発判定の基準から除外され patch dir は
  クリアされる。watchdog は未スケジュール job をスキップし、回復時にも通知する。

残余リスク（許容・記録）: fix セッションは `uv run pytest` 経由で worktree **内**の
テストコードとして任意コードを実行でき、テストコードからの network egress は
遮断されない — 境界は export された diff のレビューと人間ゲートであり、プロセス
隔離ではない。

## Amendment (2026-08-01): review フィードバックループ (T-PIPELINE-REVIEWLOOP)

初のゲート週（packet `weekly-2026-07-31`）が原設計の非対称を露呈した: Verify 失敗は
有界リトライに戻るのに、review は終端 — 1 回起動して `VERDICT:` 行だけを grep し、
本文は捨てられていた。F1.1 の CONCERNS 本文には実欠陥 3 件（本番が出さない行形を
検査する回帰テスト / 起きていない漏れを事実として書くコメント / `_RUNTIME_LINE_RE`
の過剰マッチ）が含まれていたが packet に届かず、人間はその情報なしに採用を決裁した。
review を Verify と対称の有界ループにする:

- **再突入**: `CONCERNS` verdict は review 本文全文を同一 worktree の新しい fix
  セッションに戻す（`<untrusted_review>` で包む — 本文は finding テキストから連鎖
  するため `<untrusted_finding>` と同じ根拠）。予算は `MAX_REVIEW_ROUNDS` 再突入
  ラウンド（既定 1）で、`MAX_FIX_ATTEMPTS` とは直交 — 後者はラウンドごとに再付与
  され、1 回の flaky Verify が concern フィードバックを飢えさせない。re-review の
  入力には前回 review を含め、review プロンプトに check 0 を追加: 対処済みの指摘の
  蒸し返しで CONCERNS を維持しない。
- **CONCERNS は export を止めない**（2026-08-01 のオペレータ決裁 — 最終 CONCERNS の
  patch を `failed` に降格する代替案を却下）: 最終 verdict が
  何であれ patch は `patch_ready` のまま — reviewer は検査者であって承認者ではない
  （human-gate.md）。降格は本 ADR コミットメント 3 が approve 方向で禁じた LLM 単独
  経路を reject 方向に作ることになる。変わるのは人間が見るもの: packet の fix
  テーブルは verdict 履歴全体（`CONCERNS→APPROVE`）を示し、「Review notes」小節が
  最終ラウンドの review 本文全文を inline する（`--run-log-dir`。読めないログは
  `REVIEW_LOG_UNREADABLE` で fail-forward）。
- **単調性 / 巻き戻し**: 各ラウンドの verify 済み diff をスナップショットし、再突入
  ラウンドが Verify を再通過できない（またはセッション死・deadline 到達）場合は
  前ラウンドの verify 済み diff に巻き戻す（`REVIEW_ROUND_ABANDONED`）— 動く patch
  を失敗に変えない。再突入後に diff が不変なら re-review しない（同一入力にリトライ
  しない）。既存の CONCERNS は記録に残る（`DIFF_UNCHANGED`）。
- **迎合防止条項** を fix-implementation.md に追加: 再突入時、implementer は各指摘に
  対処するか、不同意ならサマリで明示的に反論してコードを変えない — そして reviewer を
  黙らせるためにテスト・assertion・検査を緩めることは決してしない。07-31 の反例:
  F1.3 の「テストが finding の求めた範囲より狭い」を機械的に満たすと store 全件改修に
  膨らんでいた。
- **REVIEW_FAIL は終端**（verdict 行なし → 戻す本文がない）。prompt-scope findings は
  引き続き review 経路の外（既に全文ゲート対象）。
- **信頼リンクの強化**（2026-08-01 の security + code review ラウンド）: ループは
  reviewer の出力を read-only の終点から tool-using セッションの入力に変えるため、
  (a) review セッション自身の入力も finding を `<untrusted_finding>` で包み、
  fix-review.md に data-not-instructions 条項を明記 (b) reviewer 本文内の偽装
  `</untrusted_review>` は再注入前に無害化 (c) 埋め込み fence（packet の inline・
  review 入力）は本文中の最長 backtick 連より長く取る (d) 事後 scope チェックは
  diff テキストのパースでなく、選択 round の git 計算による touched-path
  snapshot を読む — binary 変更と pure rename は `---`/`+++` ヘッダを出さず、
  `diff.noprefix` はテキストパースを全盲にする（いずれもレビューで再現済み、
  F-REV-6 で回帰固定）。

fault column: `tests/test_weekly_pipeline_shell.py`（F-REV-1..5）が stub の
`claude`/`uv` で実 script を駆動する — weekly-pipeline.sh を実行する初のテストであり、
7 月のシェル層欠陥の後に `test_weekly_analysis_shell.py` が Stage 1 に対して塞いだ
のと同じギャップを塞ぐ。

本 Amendment は Decision コミットメント 4 を改訂する: fix 試行の上限は finding
あたりでなくラウンドあたりになる。finding あたりの最悪コストは review 1 回から
`MAX_FIX_ATTEMPTS × (1 + MAX_REVIEW_ROUNDS)` fix セッション +
`(1 + MAX_REVIEW_ROUNDS)` review（既定値で 4 セッション + review 2 回）に増える。
3 時間のチェーン deadline がハードストップのまま残り、再突入ラウンド中の deadline
到達は中断でなく巻き戻しになる。二次コスト: 追加ラウンドは同じ deadline 内の
wall-clock を消費するため、concern の多い週は ≤ 5 findings のうち完走できる数が
ループ導入前より減りうる。残余リスク（許容）: implementer 迎合の対称形 —
指摘された行に触れただけで欠陥が残る diff に reviewer が満足する — への機械的
ガードは無い。緩和は、人間が 4 文字の verdict でなく最終 review 本文を読むように
なったこと自体。
