# 付録 A: 全項目表（18 観点 779 項目 → 39 束）

元項目の全文（根拠・理由・提案）は作業用の `findings/<観点>.md` にある。ここでは束ごとに元項目の見出しと分類を列挙し、統合先の項目番号を示す（「—」は決定事項・やらないこと・落とした項目のいずれかに回ったもの。各束の「統合メモ」を参照）。

略号: AR=ADAPTER-RUNTIME, AB=ADR-RFC-BACKLOG, CU=CLI-UX-ONBOARDING, CH=CODE-HEALTH, CP=CORE-PIPELINE, DE=DATA-ENDING, DC=DOCS-CONSISTENCY, GO=GOVERNANCE-ORG, LP=LLM-PROMPTS-DECISIONS, OI=OBSERVABILITY-INSTRUMENTS, PF=PHILOSOPHY-FIDELITY, RD=RELEASE-DISTRIBUTION, RF=RESEARCH-FIT, SA=SECURITY-ABSENCE, SB=SIBLINGS, TQ=TESTS-CI-QUALITY, VL=VALUE-LAYER-LEGIBILITY, WO=WEEKLY-OPS-LOAD


### P0-01 10-10 土曜ゲートの決定束（insight / RFC-0042・0023・0048 / ADR-0111 / T4）（15 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AB-08 | RFC-0023 の希少レーンは「供給を増やす機構」で、入口が候補 0 件の今は withdraw が整合的 | mechanism | decision-needed | neutral（withdraw 自体は能力拡大の抑止） | med | P0-01.3 |
| AB-10 | RFC-0042 の終端判断（10-10）と同時に、ADR-0111 の「revise 案 B」と反証条件（30 件）の扱いを決める必要がある | mechanism | decision-needed | instrument | med | P0-01.2, P0-01.5, P0-01.6 |
| AB-13 | RFC-0048 は「出口の自動化（修理）」と「store 件数を絞る / 注入の要否（研究）」が同居し、着手条件が 2 重になっている | mechanism | decision-needed | (a) repair / (b) instrument | med | P0-01.4 |
| AB-14 | RFC-0049 done の「次」（parent_rejected の (a)/(b) 判別）に担当と期日が無い | ops | gap | instrument | high | P0-01.9 |
| AB-48 | 2026-10-10（土）と 10-15・10-31 に決定が集中しており、その順序と依存が台帳のどこにも書かれていない | governance | decision-needed | repair | high --- | P0-01.1 |
| CP-16 | staged ledger は「却下された候補」も永久に covered として記憶し、テーマの再入に有効期限がない | mechanism | decision-needed | neutral | med | P0-01.7 |
| CP-19 | フィードバックループの入口・出口が両方ゼロ — insight は「停止」ではなく「毎週走って何も出ない」、出口計器も候補ゼロ | value | decision-needed | neutral（凍結）/ value-steering-risk（判定を緩めて候補を出す方向は不可） | high | P0-01.2 |
| CP-20 | ADR-0111 の事前登録反証（重複判定 30 件）は、命名段が全 cluster を止める限り永遠に到達しない | research | research-need | instrument | high | P0-01.5 |
| CP-21 | `revise` 判定の蓄積に消費計画がない（ADR-0101 違反の形） | governance | gap | instrument | high | P0-01.6 |
| CP-26 | score4 enforce で代謝の入力量が約 2 割減り、insight の `min_size=3` 窓の前提が再測定されていない | research | research-need | instrument | med | P0-01.1 |
| VL-20 | 再開後 2 週は候補 0 件で、10-10 の 3 回目の読み後に「凍結 / 継続 / 命名の反映」を決める必要がある | value | decision-needed | neutral（(c) のみ capability-growth） | high | P0-01.2 |
| VL-21 | novelty gate が staged 台帳（却下分を含む）を「既知」として使い、却下が入口の学習信号になっている | value | inconsistency | value-steering-risk（却下＝オーナー意思が入口に効く経路） | med | P0-01.7 |
| VL-22 | `revise` の命名提案が記録されるだけで、読み手・期限・公開先がない | ops | gap | instrument | high --- | P0-01.6 |
| OI-02 | T4 棚卸しの四半期再発（Q3 境界後の最初の土曜ゲート = 2026-10-03）の記録が無い | governance | gap | repair | med（gate materials はローカルで未確認） | P0-01.8 |
| WO-37 | ADR-0101 の四半期 T4 棚卸し（10-03 が初回の四半期境界後ゲート）の実施記録が無い | governance | gap | instrument | med | P0-01.8 |

### P0-02 10-15 読み → 旧 relevance gate の削除（RFC-0046 後始末 3）（15 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AR-26 | Quick Start の fail-closed は既定値側で解決済み — 残りは 2026-10-15 の読みの後の削除 PR と v2.13.0 | mechanism | debt | repair | high | P0-02.1, P0-02.2 |
| AR-27 | agent plist の DECISION_* コメントが `2cad850` 以降の意味と逆のことを言っている | docs | inconsistency | neutral | high （→ 観点 DOCS-CONSISTENCY） | P0-02.3 |
| AR-28 | `--domain-config` に `relevance_score4` が無いと WARNING 1 行の後 6 時間 engage なし — `relevance_threshold` の既定 0.82 は死んだ既定 | mechanism | risk | repair | high （→ 観点 CLI-UX-ONBOARDING） --- | P0-02.4 |
| CH-15 | 旧 relevance gate（自由生成 0-1 スコア）一式が production 呼び出し 0 のまま replay とテストのためだけに残っている — RFC-0046 後始末 3 の削除条件は 2026-10-14 以降の読み | mechanism | debt | repair | high | P0-02.2 |
| CH-16 | `relevance_shadow.py` は enforce 後に「the relevance gate」そのものになったが、ファイル名・`reset_relevance_shadow` が shadow のまま | mechanism | inconsistency | repair | high | P0-02.9 |
| CU-11 | 「env 無しの Quick Start で feed が何もしない」問題の現状: `4b85f22` で修理済み、残りは RFC-0046 後始末 3 の削除リスト（plist コメント・`_warn_unknown_keys`・docs 例） | mechanism | debt | repair | high | P0-02.1, P0-02.2, P0-02.3 |
| CU-12 | relevance 閾値の既定が三重化している（docs 0.92 / packaged 0.80 / code 0.82） | docs | inconsistency | repair | high | P0-02.2 |
| LP-05 | 予定されている `relevance.md` 削除が lab ratchet（label set の `check`）と replay arm A/A0 を壊す | quality | risk | repair | high | P0-02.5 |
| AB-11 | RFC-0046 後始末 3 の削除は ADR-0112 の中核（skill-selection shadow）まで消す — 削除範囲の ADR 側の手続きが未定義 | mechanism | decision-needed | repair | high | P0-02.8 |
| AB-12 | RFC-0046 の enforce は ADR-0113 が「a further ADR」と予約した形でなく追補で実施され、Status も bare `accepted` のまま | governance | inconsistency | repair | high | P0-02.7 |
| AB-41 | ADR-0112 の Alternatives に「Phase separation now … Deferred — 未決」が残り、enforcement reading（= ADR-0113 追補 1）で再訪されていない | mechanism | decision-needed | repair | high | P0-02.8 |
| SA-31 | fail-closed 既定（RFC-0046 / ADR-0113 Amendment 2）は absence と整合 — 削除段で「空 = off = 何もしない」を固定するテストが要る | security | risk | repair | high | P0-02.6 |
| RD-31 | v2.13.0 ブロッカー (1): Quick Start の fail-closed はコード側で解消済み、残るのは 2026-10-15 の本番読みと旧コード削除 | mechanism | risk | repair | high | P0-02.1 |
| RD-32 | v2.13.0 ブロッカー (2): `install-schedule` の DECISION_ENFORCE 懸念は撤回済みだが plist テンプレートのコメントが旧動作のまま | docs | inconsistency | repair | high | P0-02.3 |
| DC-14 | `CONFIGURATION.md` の domain.json 例が `relevance: 0.92`、実ファイルは 0.80 | docs | inconsistency | neutral | high | P0-02.2 |

### P0-03 公開データの開示境界の修理（embedding 入り .bak・ロック・絶対パス）（26 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| DE-01 | 768 次元 embedding 入りの 72MB バックアップが公開 repo に tracked されている | data | defect | repair | high | P0-03.1, P0-03.3 |
| DE-02 | `.run.lock` / `.staged.lock` が公開 repo に tracked（sync の除外に無い） | data | defect | repair | high | P0-03.2 |
| DE-03 | `.DS_Store` が tracked、data repo の `.gitignore` は 4 行のみ | data | defect | repair | high | P0-03.2, P0-03.4 |
| DE-04 | `_gc_trash/`（退役 skill 原本 10 件）が公開されている — 2026-08-22 の「退役は公開しない」判断と不整合 | data | inconsistency | neutral | high | P0-03.7 |
| DE-05 | data repo の `.gitignore` が開示境界を複製していない（防御の深さ無し） | data | risk | repair | high | P0-03.2 |
| DE-07 | snapshot manifest 全 100 件と pipeline/analysis 15 ファイルにオーナーの絶対ホームパスが入っている | data | defect | repair | high | P0-03.5 |
| DE-08 | weekly の隠し state ファイルと stale な `.last_constitution_amend` が説明なく公開されている | data | debt | repair | high | P0-03.8 |
| CP-09 | 公開データ repo に 72 MB の `knowledge.json.bak-dup-cleanup-20260718`（全行 768 次元埋め込み付き）が同期されている | data | defect | repair | high | P0-03.1, P0-03.3 |
| CP-10 | 2026-07-10 / 07-18 の手動ストア書き換えが記録されておらず、DATACARD の「never hand-edited」と矛盾する | data | inconsistency | repair | med（経緯は確認できず） | P0-03.7, P0-03.8 |
| CP-11 | `.run.lock` / `.staged.lock` / `skills/.last_insight` などランタイム状態ファイルが公開 repo に同期される | data | debt | neutral | high | P0-03.2 |
| SA-10 | sync の除外リストは「開示境界」だがテストはベクタファイル 3 種しか検証していない | security | gap | repair | high | P0-03.3 |
| SA-11 | 公開 data repo に 768 次元 embedding 入りの `knowledge.json.bak-dup-cleanup-20260718`（72 MB）が tracked | data | defect | repair | high | P0-03.1 |
| SA-12 | macOS ユーザー名入りの絶対パスが公開 data repo に 539 件、本体にも 5 件 | data | risk | repair | high | P0-03.5 |
| SA-13 | rsync `--delete` は除外済みファイルを受け側から消さない — 除外を足しても過去の公開は撤回されない | data | defect | repair | high（仕様）/ med（`.DS_Store` の由来） | P0-03.4 |
| SA-14 | `_gc_trash/`（書き換え前 skill 原本 10 件）が公開されており、`.archive/` 非公開の判断（4f53259）と矛盾 | data | inconsistency | neutral | high | P0-03.7 |
| SA-15 | `cloud.env`（cloud sibling が MOLTBOOK_HOME 直下から読む鍵ファイル）が sync 除外に無い | security | risk | repair | high | P0-03.2, P0-03.3, P1-11.7 |
| SA-16 | 秘密スキャンは本体 CI だけで、無人出力を受ける data repo には無い | security | gap | repair | high | P0-03.6 |
| SA-32 | `.run.lock` / `.staged.lock` / `.DS_Store` ×2 が data repo に tracked（情報量は 0 だが境界の綻びの証拠） | data | debt | repair | high | P0-03.2, P0-03.4 |
| SA-36 | snapshot / value-layer 計器が絶対パスを書く設計そのものが「公開前提」になっていない | mechanism | defect | repair | high | P0-03.5 |
| OI-39 | 公開 `pipeline/value-layer/*.json` 3 件にローカル絶対パス `/Users/<owner>/.config/moltbook/rules` が含まれている | data | defect | repair | high | P0-03.5, P0-03.6 |
| OI-40 | `knowledge.json.bak-dup-cleanup-20260718`（70MB、本体 7.2MB の約 10 倍）が公開 repo に同期されている — sync の `*.bak.*` 除外に一致しない名前 | data | defect | repair | high | P0-03.1 |
| GO-46 | 公開 data repo の snapshot manifest / value-layer JSON にローカル絶対パス（`/Users/<name>/...`）が含まれ、ゲートの機微規則と不整合 | data | inconsistency | repair | high | P0-03.5 |
| VL-44 | 公開 `pipeline/value-layer/*.json` にローカルの絶対パス（ユーザー名）が入る | data | debt | repair | high | P0-03.5 |
| WO-42 | 公開 data repo の報告文書にオーナーの絶対パス（`/Users/<owner>`）が 33 箇所 — 公開面の機微点検が rfcs/ にしか無い | security | gap | repair | high | P0-03.5, P0-03.6 |
| RF-31 | 公開データ repo の root に埋め込み入りバックアップ（72 MB、3,250 行）が残っている | data | defect | repair | high | P0-03.1 |
| RD-37 | 公開データ repo に埋め込み入りの 72 MB `.bak` と `_gc_trash/` が残置（→ 観点 DATA） | data | risk | neutral | med | P0-03.1, P0-03.7 |

### P0-04 蒸留の取りこぼしと非原子書き込みの修理（06:00 JST セッション）（9 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| CP-01 | 06:00 JST セッションのエピソードが一度も蒸留されていない（UTC 日付ファイル境界 × `--days 1`） | mechanism | defect | repair | high | P0-04.1, P0-04.2 |
| CP-02 | distill に冪等キーがなく、再実行・窓拡張は dedup 経由の "churn" になる | mechanism | defect | repair | high（機構）/ med（実害の量は未測定） | P0-04.1, P0-04.2 |
| CP-03 | 故障したエピソード呼び出しは再試行されず、窓が進むと失われる | mechanism | gap | repair | high | P0-04.1 |
| CP-04 | 埋め込み障害時に保存される「ベクトルなし行」は自己修復されず、dedup / views / clustering から永久に外れる | mechanism | gap | repair | high | P0-04.3 |
| CP-06 | マーカー・staging・reasoning の書き込みが非原子（`write_text`）で、`write_restricted` の原子性契約から漏れている | mechanism | defect | repair | high | P0-04.4 |
| CP-07 | `amend_constitution` は検証失敗時に生成テキストをそのまま返し、CLI が「結果」として印字する | mechanism | defect | repair | high | P0-04.5 |
| CP-08 | knowledge.json に保存前バックアップがなく、コードは存在しない `.bak` の復元を案内している | data | risk | repair | med | P0-04.6 |
| CP-28 | 憲法改正は `axiom_files[0]` だけを書き換える（ファイルが増えた瞬間に黙って片側だけ改正） | mechanism | risk | repair | high（コード）/ low（影響） | P0-04.7 |
| PF-36 | `amend-constitution` は `axiom_files[0]` のみ対象で、複数ファイル状態（`-2.md` 事故）では残りが改正外のまま注入される | mechanism | defect | repair | high | P0-04.7 |

### P0-05 初回体験（Quick Start）の修理と preflight（18 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| CU-01 | Ollama・モデル不在を検出する preflight がどの経路にも無い（`init` も LLM 系コマンドも静かに進む） | ops | gap | repair | high | P0-05.1 |
| CU-02 | `init` が完了後に「次の一手」を案内しない | docs | gap | repair | high | P0-05.6 |
| CU-03 | 認証情報なし・設定ファイルなし・通信失敗が生 traceback で終わる | quality | defect | repair | high | P0-05.4 |
| CU-04 | `register` が API key を stdout に印字する（`737133e` で deferred のまま） | security | defect | repair | high | P0-05.3 |
| CU-06 | README「Try it without an account」の `dialogue` が Ollama 不在でも rc=0 で成功扱いになり、"(no reply)" をエピソードに記録する | quality | defect | repair | high | P0-05.5 |
| CU-09 | 非 TTY + APPROVE は EOF を黙って「拒否」にし、「何もしないセッション」が成功として終わる | quality | defect | repair | high | P0-05.2 |
| CU-10 | Moltbook に到達できなくてもセッションは指定時間いっぱい走り、rc=0・"Actions taken: 0" で終わる | mechanism | defect | repair | high | P0-05.2 |
| CU-14 | `init` が複製した `prompts/` は `MOLTBOOK_HOME` 未設定（README 既定）だと一切読まれない — 「home copies are the source of truth」と矛盾 | mechanism | defect | repair | high | P0-05.7 |
| CU-33 | 相対パス / `~` の `MOLTBOOK_HOME` が cwd 基準・リテラルに解決され、repo 内に home を作る | quality | defect | repair | high | P0-05.6 |
| AR-13 | Ollama 停止・モデル未 pull でもセッションは 6 時間「静かに」走る — 起動 canary と WARNING 昇格と session-end 計数が無い | mechanism | gap | repair | high | P0-05.2 |
| AR-17 | `DECISION_MODEL` が served model と違うとき投稿ごとにモデル入替が 2 回入るが、起動時に何も言わない | ops | risk | repair | high | P0-05.8 |
| AR-18 | Gemma 以外のモデルでは logprobs 読みが `no_option_observed` で全投稿 skip になりうるが、README は「どのチャットモデルでも」と言う | mechanism | gap | instrument | high | P0-05.1 |
| LP-10 | agent plist が `DECISION_MODEL=gemma4:e4b` を literal で持ち、生成モデル交代時に毎 post 2 回のモデル入替へ転落する | ops | risk | repair | high | P0-05.8 |
| DC-33 | Quick Start は v2.12.0 では fail-closed で feed が動かず、HEAD で既定値を直したが README に注記も症状説明も無い | docs | risk | repair | high | P0-05.10, P1-09.17 |
| DC-34 | Ollama の最小バージョン（logprobs 対応）と「any chat model」の但し書きが無い | docs | gap | repair | high | P0-05.1, P0-05.10 |
| TQ-25 | カバレッジ 95.1% — 最低は cli 層、未カバー帯は RFC-0046 の既定配線（Quick Start 事故の現場） | quality | gap | repair | high | P0-05.9 |
| TQ-34 | README Quick Start の end-to-end smoke が無い — 2026-10-09 の fail-closed 事故は 4,700 本の単体テストをすり抜けた | mechanism | gap | repair | high | P0-05.9 |
| SA-06 | `register` / `status` が API 応答（api_key を含む）を stdout に生で出す（commit `737133e` で見送り） | security | defect | repair | high | P0-05.3 |

### P0-06 v2.13.0 リリース（Python 床・配布単位・版メタデータ・runbook）（31 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| TQ-01 | `requires-python >= 3.10` は偽 — 実際の床は 3.11 | quality | defect | repair | high | P0-06.1 |
| TQ-38 | wheel に `config/`（prompts / domain.json / templates）が入らない — 配布面の検査が無い | ops | decision-needed | neutral | high | P0-06.2 |
| CU-26 | `typing.assert_never`（3.11+）を使いながら `requires-python = ">=3.10"`、CI は 3.13 のみ | quality | defect | repair | high | P0-06.1 |
| CU-27 | 非 editable インストールでは動かない（`config/` が wheel 外、`DEFAULT_CONFIG_DIR` / `_repo_root()` が source checkout 前提） | ops | gap | repair | high | P0-06.2 |
| CU-34 | `--version` が無く、`python -m contemplative_agent` も動かない | quality | gap | neutral | high | P0-06.4 |
| RD-01 | `uv build` は通るが wheel に `config/` が 1 ファイルも入らない | mechanism | defect | repair | high | P0-06.2 |
| RD-02 | wheel install では `init` どころか `--help` も起動しない（import 時に prompts を読む） | mechanism | defect | repair | high | P0-06.2 |
| RD-03 | `requires-python >= 3.10` は偽 — `typing.assert_never`（3.11+）を CLI の import 時に使う | quality | defect | repair | high | P0-06.1 |
| RD-05 | sdist はリポジトリ丸ごと（6 MB、キャッシュ dir も混入）で範囲が未決 | quality | debt | neutral | high | P0-06.10 |
| RD-06 | パッケージング smoke（build → clean install → import/init）がどのゲートにも無い | quality | gap | instrument | high | P0-06.3 |
| RD-07 | `__version__` も `--version` も無く、動いているコードの版を記録・申告できない | ops | gap | instrument | high | P0-06.4 |
| RD-08 | 版・DOI・日付が 7 ファイル十数箇所に手書き複製され、機械検査が無い | docs | debt | instrument | high | P0-06.7 |
| RD-09 | SemVer / 互換性ポリシーが明文化されておらず、minor で Protocol 破壊が起きている | governance | decision-needed | neutral | high | — |
| RD-10 | CHANGELOG に Unreleased が無く、v2.12.0 以降 185 commit / +86,800 行が未記録。v2.1.0 と v1.x 以前の節も無い | docs | gap | neutral | high | P0-06.5 |
| RD-11 | tag は手動・annotated と lightweight が混在、shallow clone / CI では tag が見えない | ops | debt | neutral | high | P0-06.6 |
| RD-12 | リリース手順の実体が repo 外（`~/.claude/skills/release-doi/`）にあり、repo 内の規約と矛盾している | governance | inconsistency | neutral | high | P0-06.6 |
| RD-13 | tag 時点の `CITATION.cff` は前版の DOI を名乗る（Zenodo の鶏と卵） | research | inconsistency | neutral | high | P0-06.7 |
| RD-17 | CITATION / codemeta / .zenodo / HF card の要約が README 改稿前の枠組みのまま | docs | inconsistency | neutral | high | P0-06.7 |
| RD-25 | CI は Python 3.13 単一、classifiers に版・OS が無い | quality | gap | instrument | high | P0-06.1, P0-06.3 |
| RD-28 | PyPI 未公開（名前も未取得）、兄弟の `dependencies` は PyPI 上で解決不能 | governance | decision-needed | neutral（B は capability-growth 寄り） | high | P0-06.2 |
| RD-29 | 兄弟の適合は v2.10.0 検証（2026-08-16）が最後で、v2.11/v2.12 に対する結果が repo に無い。cloud の処遇は台帳外 | sibling:cloud | risk | neutral | high | P0-06.6, P1-11.3 |
| RD-30 | リリース・チェックリストが無い — v2.13.0 で踏む順番の提案 | governance | gap | neutral | high | P0-06.6 |
| RD-33 | v2.13.0 ブロッカー (3): README の注意書き — Python 床の誤りと「editable 専用」の未記載 | docs | inconsistency | repair | high | P0-06.1, P0-06.2 |
| RD-38 | GitHub Releases / Zenodo / SWH の実在と内容が本セッションから検証不能 — 検証手順自体を repo に残す | research | research-need | instrument | med | P0-06.6 |
| RD-39 | wheel には ADR-0088 の適合キット（`contemplative_agent/testing/`）は正しく入っている（確認済み・問題なし） | sibling:mlx | opportunity | neutral | high | P0-06.2, P0-06.3 |
| DC-01 | CHANGELOG に Unreleased 節が無く、v2.12.0（2026-09-12）以降の 177 commit が未記載 | docs | gap | neutral | high | P0-06.5 |
| DC-04 | 引用メタデータ（CITATION.cff / codemeta / .zenodo.json / HF dataset card）の説明文が v2.0 期の枠組みで、2026-10-08 の README と語りが違う | research | inconsistency | neutral | high | P0-06.7 |
| DC-44 | SemVer / CHANGELOG の運用規約が repo 内に無く、v2.13.0 で予定の設定面削除（env スイッチ・domain key・prompt）は minor で出る | governance | decision-needed | neutral | med | P0-06.6 |
| AB-40 | v2.12.0（2026-09-12）以降の ADR-0111 / 0112 / 0113（+追補）と RFC-0038〜0049 が未リリースで、CHANGELOG に Unreleased 節が無い | ops | gap | repair | high | P0-06.5 |
| CH-32 | Protocol 7 本の定義と実装の対応は取れている（`DecisionBackend` 1 実装、`LLMBackend` は sibling 3 実装が `think` / `context_window` を満たす）— 欠けているのは本番 Ollama 経路（CODE-HEALTH-23） | mechanism | opportunity | neutral | high | P0-06.6, P1-11.3 |
| SA-27 | `uv.lock` 非追跡（ADR-0109 の判断）により、DOI 付きリリースの依存解決が再現できない | research | debt | instrument | high | P0-06.6, P1-08.5 |

### P0-07 10-31 due の憲法改正ゲートの事前登録と shadow 系列（11 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-11 | shadow 憲法の縦断系列が 2 run（同日）で止まっており、「憲法が生きているか」の trend 読みが取れない | research | gap | instrument | high | P0-07.1 |
| RF-22 | 次回改正（目安 2026-11）の前後比較の結果変数が今のうちに事前登録されていない | research | research-need | instrument | high | P0-07.2 |
| VL-31 | shadow constitution は 2026-08-11 の 2 run 以降走っておらず、次の due（≈11-01）まで憲法の「影の状態」が読めない | ops | gap | instrument | high | P0-07.1 |
| AB-07 | RFC-0012（shadow 憲法の消費）は 2026-10-31 の憲法 due と同時に解けるが、本文の照合先と日付が古い | value | decision-needed | instrument | high | P0-07.4 |
| AB-42 | RFC-0012 / ADR-0091 / value-layer JSON で憲法改正間隔が 84 日と 83 日に割れている | value | inconsistency | repair | med | P0-07.4 |
| OI-33 | shadow constitution（ADR-0092 / RFC-0012）は 2026-08-11 の 2 run のみで、消費は改正 due（83 日、10-02 時点 54/83）に連動し、改正が due にならない限り永久に休眠する | value | decision-needed | repair | high | P0-07.1 |
| WO-52 | RFC-0012（shadow 憲法の消費）は 2026-11 の改正ゲートまで blocked だが、改正ゲート自体の起動が人間の記憶依存 | ops | risk | instrument | med --- | P0-07.4 |
| PF-12 | 第 3 改正は条項の指示対象を「directive/belief」から「自分の計算構造」へ広げた — 解釈キーと逆方向の自己言及的再束縛 | value | risk | instrument | high | P0-07.2, P0-07.3 |
| PF-35 | 改正は live patterns ~4.8k のうち cosine 上位 50 だけを見る — その選択比が改正記録に無い | mechanism | debt | instrument | high | P0-07.7 |
| PF-37 | 改正プロンプトが Source 行の書換を model に委ねており、出自（版・親 sha256・採択日）が model 生成文になっている | mechanism | debt | instrument | high | P0-07.8 |
| PF-38 | 改正出力の構造検証は forbidden pattern と truncation のみ（4 節・条項数・directive voice は未検証） | quality | debt | instrument | high | P0-07.7 |

### P1-01 機構層の「凍結」判定を定義する（3 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| CH-41 | 機構層は git の読みでは「止まって」いない — src コミットは 2026-08 40 / 09 95 / 10 6（9 日間）、9 月は refactor 46 本、2026-09-01 以降に ADR 12 本（0102–0113） | mechanism | decision-needed | repair（判定の整備） | high | P1-01.1 |
| CP-17 | 機構層は「止まっていない」: 直近 3 か月で core/ に 90 commit、選択・relevance 計器が最も動いている | governance | inconsistency | instrument | high（件数）/ med（分類） | P1-01.1, P1-01.2 |
| CP-18 | 「止めるために残っている作業」が台帳に散らばっており、停止条件の一覧がない | governance | gap | neutral | high | P1-01.3 |

### P1-02 RFC 台帳の健全化と blocked RFC の終端（15 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AB-01 | RFC 本文の `## Status` 節が frontmatter と乖離し、読み手（人間・LLM）を誤らせている | governance | inconsistency | repair | high | P1-02.1 |
| AB-02 | RFC frontmatter の様式が不統一で、`state_since` が更新されていない | governance | inconsistency | repair | high | P1-02.2 |
| AB-03 | `rfcs/README.md` の索引に state / 日付 / 着手条件の列が無く、台帳の全体像は repo 外の `claims.py` でしか読めない | governance | gap | repair | high | P1-02.3 |
| AB-06 | 暦待ちの blocked に対する dead-band 追記が台帳を膨らませている（158 節） | governance | debt | repair | med | P1-02.2 |
| AB-09 | RFC-0040（Jev / ローカル判断モデル）は成果を出し切っており、残部は能力動機の拡大 — withdraw 候補 | mechanism | decision-needed | neutral（能力拡大の予約を閉じる） | med | P1-02.5 |
| AB-16 | RFC-0047（face 改善ループの制度化）の ADR 昇格は北極星「止まる」と緊張する — 昇格先の形を決める必要がある | governance | decision-needed | neutral（capability-growth の制度化を避ける） | med | P1-02.6 |
| AB-37 | 決定待ち（オーナー判断）が RFC 本文の triage 節・ADR の Alternatives・CHANGELOG に散在し、集約面が無い | governance | gap | repair | high | P1-02.4 |
| AB-38 | blocked RFC に「打ち切り日」が無く、RFC-0047 の stuck 14 日規律が台帳の様式に反映されていない | governance | gap | repair | med | P1-02.2 |
| AB-43 | RFC-0044 の「第 2 段（enum 拘束）見送り」は done で閉じたが、同日に done → accepted → done と翻った判断の最終根拠が RFC-0048 へ渡されている | mechanism | inconsistency | neutral | low | P1-02.2 |
| AB-44 | 9〜10 月の修理ループは「修理」と「方法論・将来像」が同じ台帳を同じ速度で流れ、ADR-0080 の「修理か能力拡大か」審査が RFC 起票時に記録されていない | governance | gap | instrument | med | P1-02.4 |
| DC-10 | 残課題の運用が repo 外の `claims.py` に依存し、`rfcs/README.md` には state 列が無い | docs | gap | neutral | high | P1-02.3 |
| DC-47 | RFC-0042 本文の状態記述「insight 週次は停止中」が 2026-09-19 の再開後も残り、frontmatter / 後段の節と食い違う | docs | inconsistency | neutral | high --- | P1-02.1 |
| OI-47 | RFC-0011 の `## Status` 節が done 後も「blocked」のままで、計器の撤去判断を探す読み手が誤る | docs | inconsistency | repair | high | P1-02.1 |
| VL-19 | insight は 2026-09-19 当日に再開済みで、RFC-0041 の撤回文とブリーフの「停止中」は古い | docs | inconsistency | repair | high | P1-02.1 |
| LP-30 | RFC-0040 は能力拡大の RFC で、4 ラウンド + 2 面の測定後に gemma の logprobs 読みを超える候補が無く、唯一の利得（較正された確率）に消費者が無い | research | decision-needed | capability-growth（抑止側） | high | P1-02.5 |

### P1-03 ADR 台帳の機械追跡（追補・Note・索引・Review-when）（15 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AB-20 | Status 行の `(amended YYYY-MM-DD)` 慣例が、追補を持つ ADR 17 本のうち 4 本にしか適用されていない | docs | inconsistency | repair | high | P1-03.2 |
| AB-21 | 「既存 ADR の変更は新 ADR で supersede（上書きしない）」という README 規約と、追補中心の実態が乖離している | governance | inconsistency | repair | high | P1-03.1 |
| AB-22 | 日付つき Note による実質的な supersession が Status / graph に現れず、機械追跡の supersede チェーンに穴がある | docs | inconsistency | repair | high | P1-03.3 |
| AB-23 | ADR-0067 ↔ ADR-0070 の片側チェーン切れ | docs | inconsistency | repair | high | P1-03.3 |
| AB-24 | ADR-0044〜0096 の 52 本のうち `## Review-when` を持つのは 0069 だけで、README の「required since ADR-0044」は本 repo の ADR-0044 ではない | governance | inconsistency | instrument | high | P1-03.4 |
| AB-25 | README が指示する `/sync-context` は repo 内に存在しない harness コマンド | docs | debt | repair | high | P1-03.6 |
| AB-26 | ADR-0032 本文に `## Date` の値が無い（索引は 2026-04-27） | docs | inconsistency | repair | high | P1-03.6 |
| AB-27 | ADR 索引に「最終改訂日」が無く、10 月の活動（追補 2・Note 11）が索引から見えない | docs | gap | instrument | med | P1-03.5 |
| AB-28 | 「Accepted だがコード痕跡が無い ADR」は無し。ただし ADR-0061 の実装箇所は ADR-0060 として引用されている | docs | inconsistency | repair | high | P1-03.6 |
| AB-34 | ADR 索引（en / ja）と graph.jsonld の ADR 面は手書きで、生成器が無く「検査で守る」設計になっている | docs | debt | repair | med | P1-03.5 |
| AB-35 | ADR の粒度基準「小さな判断は記録不要」が機能していない（小粒 ADR と、重大変更の追補化が併存） | governance | debt | repair | med | P1-03.1 |
| AB-46 | graph.jsonld に RFC ノードが無く、ADR-0112 / 0113 の `isBasedOn` が RFC を URL で指すだけ | docs | gap | instrument | low | P1-03.5 |
| DC-28 | `docs/adr/README.md` の Guidelines「never overwrite」が追補運用と矛盾し、`/sync-context`（repo 外）を参照する | docs | inconsistency | neutral | high（→ ADR 本文の評価は観点 ADR-RFC-BACKLOG） | P1-03.1, P1-03.2 |
| GO-30 | ADR テンプレートに「誰が提案し誰が受理したか」の欄が無く、Claude 起草 ADR の受理記録はオーナーの commit に暗黙化している | governance | gap | instrument | high | P1-03.7 |
| GO-33 | CA ADR → AAP ADR の対応表が本体側に無く、AAP の双方向改訂規約が片側にしか無い | docs | gap | instrument | high | P1-03.5 |

### P1-04 計器の解体と消費計画の補完（ADR-0101 T4）（34 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| OI-01 | 祖父条項下の 5 計器 ADR に消費計画が無く、T4 遡及棚卸しが「計画の記録」まで到達していない | governance | gap | repair | high | P1-04.1 |
| OI-05 | submolt-scope sweep（ADR-0086）は RFC-0011 の撤去条件 (a)/(b) を判定しないまま木曜 03:00 の常設ジョブとして残っている | mechanism | decision-needed | repair | high | P1-04.3 |
| OI-06 | comment-outcomes（ADR-0106）の消費計画「2 窓で分離するか撤去」は 4 窓を経過したが判定が記録されず、代わりに D3 が追補された | mechanism | decision-needed | repair | med（判定が gate materials にだけ書かれている可能性） | P1-04.5 |
| OI-07 | confusion-pairs 計器は 4 週連続 `pairs: []`（1,030 judged / catalog 53）で一度も陽性を出していない | mechanism | decision-needed | repair | med | P1-04.4 |
| OI-08 | dead-code scan（9 回連続 0 候補）と docs-consistency scan（8 回連続 0 findings）は読み値ゼロのまま毎週土曜ゲートの読み項目を占めている | ops | decision-needed | repair | high | P1-04.6 |
| OI-10 | 退役した計器の出力残骸が公開データ repo に残っている（ledger-watch、packet/insight-review/improvement 形式、patches/） | data | debt | repair | high | P1-04.7 |
| OI-11 | `retrieval_recall_measure.py` は退役した `weekly-<end>-insight-review.md` を ground truth に読む死んだ計器だが、dead-code scan は検出できない | mechanism | debt | repair | med | P1-04.7 |
| OI-13 | `skill-stocktake` は 2026-08-15 の 1 回しか実行痕跡が無く、advisory 読みとして誰の手順にも乗っていない | mechanism | decision-needed | repair | med | P1-04.2 |
| OI-14 | ADR-0071 の原点計器 `view_metrics`（pattern composition）は週次に乗らず、読み手が存在しない | mechanism | decision-needed | repair | med | P1-04.2 |
| OI-26 | reply rate が 2 定義で共存している（`metrics.py` と `comment_outcomes.py`） | mechanism | inconsistency | repair | high | P1-04.9 |
| OI-27 | hallucination 分類は 3 箇所に実装（`selection_metrics.classify_hallucination`、`skillsel_reading.classify`、`skill_confusion` の import）で、手動版が凍結基準になっている | mechanism | debt | repair | high | P1-04.9 |
| OI-28 | 計器の閾値・帯の単一の定義源が無い — `thresholds.py` は 5 定数のみで、600/14/0.3/0.80/27/83/3.5/300 が 7 箇所に散在 | mechanism | gap | repair | high | P1-04.8 |
| OI-30 | knowledge 件数の読みが state diff / invariant check / 台帳 baseline で別々に計算されており、増分の定義（tombstone・soft_invalidated の扱い）が揃っていない | mechanism | inconsistency | repair | med | P1-04.8 |
| OI-31 | ADR-0112 の skill_selection face shadow は 2026-09-22 に候補が消えたまま、日付付きの撤去条件を持たない休眠 seam になっている | mechanism | decision-needed | repair | med | — |
| OI-34 | 2026-10-09 のスケール変更（submolt-scope が score4 で採点）で、submolt-scope 履歴・`relevance_arm_replay.py` の標本・RFC-0047 ラベル集合の 3 計器が前後で比較不能になる | mechanism | risk | repair | med | P1-04.3 |
| OI-35 | evals の `.ack.json` 4 件（09-19 / 09-25 / 10-07 ×2）はすべて「comment path unchanged」と宣言しているが、その期間に comment path の relevance gate は score4 へ切り替わった | quality | risk | repair | med | P1-04.10 |
| OI-36 | evals fixture（2026-08-08 snapshot、49 ファイル）は稼働 store（skills 53）と乖離し、`check_staleness.py` を定期的に走らせる経路が無い | quality | debt | repair | high | P1-04.11 |
| OI-37 | evals（DeepEval + `claude -p` judge）の位置づけが「計器」でも「品質ゲート」でもなく、Consumption plan も ADR-0101 の対象判定も無い | quality | decision-needed | repair | med | P1-04.10 |
| OI-45 | census の KEPT 状態（`insight-worth.jsonl`、`noise-*.jsonl`、2026-09-26 ゲート）は期限の無い「残置登録」で、ADR-0101 の「standing register を持たない」と衝突する | governance | inconsistency | repair | high | P1-04.14 |
| CP-14 | サイドカーの孤児ベクトルは週次の読みに出ず、掃除は operator 専用 | data | debt | instrument | med | P1-04.8 |
| CP-27 | 出口計器 3 本（約 3,000 行）が数週間ゼロ件を返しており、ADR-0101 の棚卸し対象 | quality | decision-needed | neutral | med | P1-04.4 |
| WO-39 | 廃止済み stage 6c（ledger-watch）の成果物が data repo に残存 | data | debt | repair | high | P1-04.7 |
| WO-50 | ADR-0105 の 2 回の天井読みは取られたが、ADR 本体に「帯では答えられない」の決着が記録されていない | docs | inconsistency | neutral | med | P1-04.4 |
| WO-51 | ADR-0091（value-layer cadence stage）に Review-when / 消費計画が無く、T4 の対象になるかが不明 | docs | gap | instrument | med | P1-04.1 |
| CH-20 | `core/skill_confusion.py`（755 行）は src 内の import 元が 0 で、wheel に入りながら消費者は `scripts/` と tests だけ | mechanism | inconsistency | instrument | med | P1-04.4 |
| AB-17 | RFC-0021 は「天井仮説は未決のまま閉じる」で done になり、ADR-0105 stage 7c の撤去条件が事実上「1 年」 | mechanism | decision-needed | repair | med | P1-04.4 |
| AB-18 | ADR-0106（comment outcome）の消費計画「2 窓 ≥ 500 judged」は読みの期日が無く、RFC-0028 done の後ろで未消費 | mechanism | gap | instrument | med | P1-04.5 |
| AB-19 | surprise 計器（RFC-0016、display-only）の消費者が現在も存在するかが台帳から読めない | mechanism | risk | repair | low | — |
| LP-18 | 抽出前 novelty gate（judge-before-artifact）が本番に残り、ADR-0111 自身が「母集団を分離しない」と記録している | mechanism | debt | repair | med | P1-04.13 |
| LP-20 | 現行 eval baseline（2026-09-12）は selector temperature 1.0 の下で測られ、本番は 2026-09-20 から 0 — staleness が見えない軸で baseline が失効している | quality | defect | repair | high | P1-04.11 |
| LP-21 | deepeval は verdict を report に再生する副産物にしか使われず、約 60 package を type gate と pip-audit に載せている | quality | debt | repair | high | P1-04.12 |
| LP-22 | Face A golden は手作り 12 件で本番との相関証明が無く、判定分布が DRIFTING に収束して回帰検出力がほぼ無い | quality | decision-needed | instrument | high | — |
| TQ-29 | evals は 2026-09-12 以降 未実測 — acknowledge 4 回で staleness を黙らせている | research | gap | instrument | high | P1-04.10 |
| TQ-30 | eval fixture snapshot（2026-08-08）と本番値層（2026-10-10 更新）の乖離 — 再 snapshot サイクルが一度も回っていない | research | research-need | instrument | high | P1-04.11 |

### P1-05 観察台帳と週次計器の機械化（baseline・expiry・自己故障）（13 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| OI-09 | docs-consistency scan の `enja_drift` 検査が毎週 `GIT_FAIL "no timestamp: docs/adr/0103…"` で失敗しており、en/ja 乖離検査は実質走っていない | quality | defect | repair | high | P1-05.5 |
| OI-12 | insight 停止（2026-09-19〜）により census の NO_ROWS 例外が毎週固定で出続け、「停止中」を表す状態が計器側に無い | mechanism | gap | instrument | high | — |
| OI-15 | 台帳の baseline 帯（400–550 / 10–25% / +300..+700 / 2–10% / ~6.0%）は JSONL の `expected` 散文にしか存在せず、帯内外の判定を毎週 LLM セッションが散文で行っている | mechanism | risk | instrument | high | P1-05.2 |
| OI-16 | `baseline_proposal` 4 件が一度も批准されず、weekly-gate SKILL.md に「baseline」という語が 0 回 — 批准経路が手順上存在しない | governance | defect | repair | high | P1-05.1 |
| OI-17 | O-009（hallucination 帯上）と O-015（帯下）が同一指標で同時に open で、10-02 報告は O-009 を「in-band count does not advance」と記述している | mechanism | inconsistency | repair | high | P1-05.3, P1-05.4 |
| OI-18 | O-017「relevance < 0.80」は 2026-10-07 以降測れない指標（自由生成スコアは退役、ヘッダは P(top)）で、O-016 は帯下限 400 に対し 391（2.3%）の 1 週逸脱 | mechanism | inconsistency | repair | high | P1-05.4 |
| OI-19 | 台帳 O-001/O-002/O-003/O-004/O-005/O-007 は 12〜15 週 open で、エスカレーションも自動 archive も無い | governance | debt | repair | high | P1-05.3 |
| OI-29 | log anomaly sweep の「新規性・頻度 Δ」はログローテーションで壊れる（10-02: corpus −87%、Δ 比較不能） | mechanism | defect | repair | high | P1-05.6 |
| OI-46 | `PIPELINE-STATUS.md`（2026-10-10 すべて ✅）と watchdog は「走ったか」しか示さず、「読み値が出たか」（stage 7b/7c の空読み、docs-consistency の abstain）は緑のまま | ops | gap | instrument | med | P1-05.5 |
| WO-03 | 観察台帳の expiry が自由文で、機械では閉じられない — open 件数が 13 まで単調増 | mechanism | gap | repair | high | P1-05.3 |
| WO-07 | census 登録表の `pipeline-metrics.jsonl` 行が旧フォーマット（phase / verdict）を読んでいる — ゲート自身のログに読み手が無い | mechanism | defect | repair | high | P2-01.1 |
| WO-08 | baseline_proposal 4 件が 2026-08-28 以来ゲートで裁定されておらず、ゲートが baseline を宣言する経路も未定義 | mechanism | gap | instrument | high | P1-05.1 |
| WO-32 | docs-consistency scan が 4 週連続で自己故障（`enja_drift GIT_FAIL`）を出したまま修理されていない | mechanism | defect | repair | high | P1-05.5 |

### P1-06 コード構造の最後の窓（OllamaBackend・core 内層契約・規約の明文化）（47 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| CH-01 | `verification_parse.py`（1806 行）は 58 個の private 定義が節見出しゼロで並ぶ単一ファイル | mechanism | debt | neutral（構造のみ。能力は増えない） | high | P1-06.7 |
| CH-02 | `cli/adopt.py`（1588 行）は承認ゲート本体と names ファイル解析・予算計器・archive 解決の 4 責務を抱え、巨大モジュール中で最も頻繁に編集されている | mechanism | debt | neutral | high | — |
| CH-03 | `core/llm/__init__.py`（1162 行）は「恒久 facade」と宣言しながら transport・生成本体・判定 seam・telemetry・可変設定の 5 役を同居させている | mechanism | debt | neutral | high | P1-06.1 |
| CH-04 | `core/insight.py`（1150 行）は段分割（ADR-0111）後も cluster batching・fail-open cap・抽出本体・監査の 4 群が残り、`extract_insight` が 157 行 | mechanism | debt | neutral | med | — |
| CH-05 | `core/selection_metrics.py`（1141 行）は DTO 8 クラス・走査・判定（hallucination 分類）・描画 6 関数（273 行）を 1 計器モジュールに同居させている | mechanism | debt | instrument | med | — |
| CH-06 | `adapters/moltbook/client.py`（1131 行）は `MoltbookClient` 1 クラス 828 行・37 メソッドに transport・rate 予算・envelope 解釈・監査が同居し、module docstring が 1 行 | mechanism | debt | neutral | high | — |
| CH-07 | C901 予算は守られている（exemption 0・`noqa: C901` 0）が、関数**長**には予算が無く 80 行超が 57 本・最大 183 行 | quality | debt | neutral | high | P1-06.7 |
| CH-08 | C901 が数えない boolean 連鎖・内包・三項で、実質複雑度が 2 倍の関数がある（`distill` 9→22、`_classify_positions` 4→18） | quality | risk | neutral | med（推定器は自作。順位は安定、絶対値は ±2） | P1-06.7 |
| CH-09 | Moltbook adapter の主経路モジュール 7 本（計 5,000 行超）の module docstring が 1 行で、ADR-0102 以降「責務の保存場所」が存在しない | docs | gap | neutral（docs のみ） | high | — |
| CH-10 | public 関数の docstring 欠落 77 本（83% 充足）、うち `cli.main`(92 行) と `decision.decide`(53 行) は入口級 | docs | gap | neutral | high | — |
| CH-11 | 抑制コメントは計 10 件と少なく全件に理由が付くが、`# noqa: BLE001` 6 件は BLE が `select` に無いため**不活性**で、意図の記録としてしか機能していない | quality | inconsistency | neutral | high | P1-06.10 |
| CH-12 | `.vulture_whitelist.py` の免除台帳に実体の無い名前（`draft_body`）が残り、名前単位のグローバル免除なので将来の同名 dead code を隠す | quality | defect | repair | high | P1-06.10 |
| CH-13 | `core/distill.py:99` の `# noqa: E402 — module-level by design` は、その import を定数の後に置く必然が無い | quality | debt | repair | high | P1-06.10 |
| CH-14 | pyright は standard モードで、`reportUnusedVariable` / `reportUnreachable` を cli の argparse 事情のために**全体**で無効化している | quality | debt | neutral | med（違反数は未実行のため不明） | — |
| CH-18 | `knowledge_store.py` の legacy 読み経路（inline embedding / bare-string 行 / importance 欄）は ADR-0108 移行後も残り、退役条件が無い | mechanism | debt | repair | med | P1-06.13 |
| CH-19 | 「正本は src、鏡は scripts」の二重綴り 4 関数が parity テストで繋がれている — bare `python3` 起動方針（ADR-0109）の構造的コスト | quality | debt | neutral | high | — |
| CH-21 | `TODO/FIXME/XXX/HACK` 0 件・未参照 private 関数 0 件（文字列 dispatch を除く）— dead-code 系の計器は機能している（確認事項） | quality | opportunity | neutral | high | — |
| CH-22 | import-linter の 4 契約は守られている（上方向辺 0・adapter 間辺 0）が、`core/` 内部には 8 モジュールの循環があり、103 箇所の関数内 import で隠している | mechanism | risk | neutral | high | P1-06.2 |
| CH-23 | `LLMBackend` Protocol の実装は repo 内に 0 本 — 本番既定の Ollama 経路は Protocol を通らず、conformance kit（ADR-0088）が本番経路を検査できない | mechanism | gap | repair（契約と実装の不一致の修理。能力は増えない） | high | P1-06.1 |
| CH-24 | underscore 名が層を越えて公開 API になっている（facade の `_` 再 export 18 名、adapter が core の `_DEFAULT_OLLAMA_MODEL` を import、tests / scripts / sibling が `_circuit` 等を 50 回以上 import） | mechanism | inconsistency | neutral | high | P1-06.10, P1-06.3 |
| CH-25 | `scripts/`（33 本 + 共有ヘルパ `_*.py` 6 本 893 行）と `evals/`（11 本）は import-linter の root_packages 外で、層の規律も private 使用の規律も無い | quality | gap | neutral | med | P1-06.3 |
| CH-26 | `core/config.py`（「platform-independent」）が Moltbook API の文字数上限を持ち、`core/episode_render.py` がそれを直接読む — ADR-0001 の parameterized core に反する | mechanism | inconsistency | neutral | high | — |
| CH-27 | 広い `except Exception` 41 箇所は「計器が観測対象を壊さない」方針で揃っているが、印の付け方が 3 流儀（不活性 noqa 6 / 末尾コメント約 14 / 無印約 21） | quality | inconsistency | neutral | high | — |
| CH-28 | ログレベルが WARNING に偏り（261 件、info 123 / error 16 / critical 1）、「セッション全体が何もしない」設定エラーと「計器 1 本が読めない」が同じ WARNING で週次 sweep に流れる | ops | inconsistency | repair | high | P1-06.10, P1-06.8 |
| CH-29 | 広い except の大半が `%s: exc` でスタックを捨てる（`exc_info=True` 3 件・`logger.exception` 4 件のみ）— 第三者の事後解析に traceback が残らない | ops | risk | instrument | med | P1-06.8 |
| CH-30 | `print` の残存は per-file-ignores の 4 面に限られ、CLI のエラー出力は全て stderr — 残課題なし（確認事項） | quality | opportunity | neutral | high | — |
| CH-31 | `Any` は 212 回・`dict[str, Any]` 153 回で JSON 境界の支配的慣用（verify.md が「JSONValue alias は作らない」と判断済み）— 署名に `Any` を持つ関数 105 本、hotspot は `client.py` 25 / `report.py` 22 | quality | decision-needed | neutral | med | — |
| CH-33 | 「`frozen=True` に例外なし」（CLAUDE.md）に対し、非 frozen の dataclass が 3 つ（理由つき）— 文書と実装の食い違い | docs | inconsistency | neutral | high | P1-06.10 |
| CH-34 | module-level 可変状態が 10 モジュール・`global` 27 箇所・`reset_*()` テスト seam 8 本に散り、`configure()` は 12 kwargs | mechanism | debt | neutral | med | — |
| CH-35 | Ollama URL の既定 `http://localhost:11434` が core と adapter で 2 回定義され、モデル既定に適用した「core から import する」規律が URL には適用されていない | mechanism | inconsistency | repair | high | P1-06.10 |
| CH-36 | `MOLTBOOK_HOME` の解決が「import 時に凍結（`MOLTBOOK_DATA_DIR`、9 ファイルが消費）」と「呼び出し時に env 読み」の 2 機構で、config.py 自身が凍結値の罠（P4-2）を 3 箇所の注記で回避している | mechanism | debt | neutral | med | P1-06.10 |
| CH-37 | env キー 16 種が 10 ファイルの `os.environ.get` に散り、登録表が無い — `docs/CONFIGURATION.md` に 4 種、`.env.example` に 10 種が未記載 | ops | gap | instrument | high | P1-06.4 |
| CH-38 | `core/thresholds.py` を「唯一の登録簿」と宣言しながら、relevance / score4 / novelty の閾値は `domain.py` 既定値と `novelty.py` のコンストラクタ既定に住み、pivot snapshot に現れない | mechanism | inconsistency | instrument | high | P1-06.4 |
| CH-39 | `config/prompts/` に agent が読まない script 用プロンプト 2 本（`principles.md` / `weekly-analysis.md`）が同居し、「固定 apparatus」の境界が崩れている | docs | inconsistency | neutral | med | — |
| CH-40 | コメント 11% + docstring 24% と密度は高いが、日付入りの叙述コメントが 347 行あり、2026-09-12 に 72 件（46 ファイル）の腐敗を一括修正した実績がある — 止まった後の腐敗を検出する周期が無い | docs | risk | neutral | high | — |
| CH-42 | テストは src の 1.8 倍（67,495 行 / 130 ファイル）で、巨大モジュールには巨大テストが対応し、legacy 経路のテストが削除を重くする | quality | risk | neutral | med | P1-06.1 |
| CH-43 | `core/_io.py` は最大の fan-in（46 モジュール + scripts 3）を持つ 18 関数の雑多ユーティリティで、名前が private（`_io`） | quality | debt | neutral | med | — |
| CH-44 | `cli/` パッケージは `__init__` が全コマンドモジュールを import し、各モジュールが `from . import runtime / approval` で戻るため、1 サブコマンドの import が CLI 全体を初期化する（関数内 import の半数 52/103 が `cli/` に集中する主因） | quality | debt | neutral | med | — |
| CH-45 | Decision 語彙の同名異義: `_Decision`（CAPTCHA parser）/ `GateDecision`（novelty）/ `DecisionResult` / `DecisionBackend`（ADR-0112 seam）が別概念で同じ語を使う | docs | inconsistency | neutral | low（読みやすさの判断で、実害の証拠は無い） --- | — |
| AR-06 | `follow_agent` と `auth.py` が `_parse_body` の規律を迂回して `resp.json()` を直叩きしている | mechanism | inconsistency | repair | high | P1-06.11 |
| AR-07 | `search()` は本番呼び手のない dead capability で、security by absence の末尾コメントと矛盾する | security | debt | neutral（absence の維持） | high （→ 観点 SECURITY-ABSENCE） | P1-06.11 |
| AR-08 | `User-Agent: ContemplativeAgent/0.1` が package 版（2.12.0）と乖離している | ops | inconsistency | neutral | high | P1-06.10, P1-06.11 |
| AR-11 | `verification_parse.py` の 1,806 行は語彙・規則表が大半で、分割の利得は無い — 「分割しない」を明文化する | mechanism | decision-needed | instrument | high | P1-06.7 |
| AR-32 | platform 上の自己紹介文が `auth.py` にハードコードされ、identity（値層）と別の場所で固定されている | value | debt | neutral | high --- | — |
| LP-06 | `config/prompts/` に Claude が読む文書（16.5k 文字、44%）が同居し、ディレクトリの意味が二重 | docs | inconsistency | neutral | high | — |
| CU-05 | `register` の agent description がテンプレートを無視して contemplative 固定 | mechanism | inconsistency | neutral | high | — |
| OI-43 | Goodhart 耐性は import グラフ上成立しているが、機械的な保証（import-linter 契約）が無く、`submolt_scope.py` が既に `selection_metrics` を import している | security | risk | repair | high | P1-06.2 |

### P1-07 アダプタと LLM 接点の堅牢性（障害時の挙動・予算・較正定数・来歴）（33 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AR-01 | トランスポート障害・5xx は再試行なしで「空の読み」に潰れ、セッションは何も知らずに続く | mechanism | risk | repair | high | — |
| AR-02 | api-audit の transport 障害行（`status: None`）が census の error 規則に見えず、Moltbook 停止の週が「正常」に読める | ops | defect | instrument | high （→ 観点 OBSERVABILITY-INSTRUMENTS） | P1-07.5 |
| AR-03 | hard rate limit の判定が本文の文言 `"limit reached"` に、`Retry-After` の解釈が float 形式に依存している | mechanism | risk | repair | med（platform の現行文言・形式は未確認） | P1-07.4 |
| AR-04 | `_EXPECTED_KEYS` が feed 系と `/home` を覆っておらず、最頻の読みが drift 検出の外にある | ops | gap | instrument | high | P1-07.4 |
| AR-05 | API key が失効しても `logger.critical` 1 行で、セッションは 6 時間走り続ける | mechanism | gap | repair | high | P1-07.3 |
| AR-09 | 通知取得は `since` 未使用・paging なしで、障害明けの溜まりを取りこぼしうる | mechanism | risk | repair | med（platform の既定件数・paging は未確認） | P1-07.4 |
| AR-10 | `api-audit.jsonl` / `verification-audit.jsonl` は 1 ファイル追記でローテーションされない | ops | debt | instrument | high （→ 観点 OBSERVABILITY-INSTRUMENTS） | — |
| AR-12 | `VerificationTracker` はプロセス内カウンタで、platform の「10 連続失敗で停止」をセッション跨ぎで数えていない | mechanism | risk | repair | med（機構は確実、害の大きさは platform 規則次第） --- | P1-07.3 |
| AR-14 | 5 つの外部呼び出し面で「閉じる／開く／退化する」が違い、障害時の挙動表がどこにもない | docs | inconsistency | neutral | high （→ 観点 DOCS-CONSISTENCY） | P1-07.1 |
| AR-15 | decision の prompt が `num_ctx` を超えたとき理由コードが無く、`answered` のまま判定の意味が変わる | mechanism | risk | instrument | med（Ollama の切り捨て挙動は版依存） （→ 観点 LLM-PROMPTS-DECISIONS） | P1-07.9 |
| AR-16 | decision 読みは breaker に書かず read timeout 300 s — shadow 時代の隔離設計が live gate にそのまま残っている | mechanism | decision-needed | repair | high | P1-07.7 |
| AR-19 | gemma4:e4b で較正した定数が 6 箇所に散り、モデル差し替え時に何を再較正するかの一覧が無い | docs | debt | neutral | high | P1-07.11 |
| AR-20 | `relevance_pin()` はモデル**名**で pin するので、`ollama pull` で重みが変わっても 14 日間キャッシュが再利用される | data | inconsistency | instrument | high | P1-07.12 |
| AR-31 | `run` に dry-run / offline 経路が無く、feed gate を本番 Moltbook なしに通す手段が無い | quality | opportunity | neutral | med （→ 観点 CLI-UX-ONBOARDING） | — |
| AR-33 | llm-calls の生成行に `kind` が無く、otel sibling は decision 行を「生成」として輸出している | sibling:otel | inconsistency | instrument | high （→ 観点 SIBLINGS / OBSERVABILITY-INSTRUMENTS） | P1-07.13 |
| AR-34 | 4 つの log family は版を名乗らず、「欠けている欄の意味」が reader 3 つにそれぞれ埋め込まれている | data | debt | instrument | high （→ 観点 DATA-ENDING / OBSERVABILITY-INSTRUMENTS） | P1-07.13 |
| AR-36 | census の llm-calls error 規則 `outcome in ("ok",)` が `truncated_kept`（出力は採用された行）を error に数える | ops | defect | instrument | med（`truncated_kept` の位置づけは ADR-0065 で要確認） （→ 観点 OBSERVABILITY-INSTRUMENTS） --- | P1-07.5 |
| LP-01 | skill 全コーパス fallback が NUM_CTX を超え、pass-1 の fail-open が「生成スキップ」に変質している | mechanism | defect | repair | high | P1-07.8 |
| LP-02 | 推定器の過大計上（ASCII 1.73〜1.95×、CJK 2 tok/字）が Ollama 経路の C2 ガードを実際より早く閉じる | mechanism | risk | repair | med | P1-07.10 |
| LP-03 | pass-2 注入に token 上限が無く、選択数は catalog 成長で青天井 | mechanism | risk | repair | med | P1-07.8 |
| LP-04 | 登録済みだが読み手の無いテンプレートが 2 本残り、orphan guard が見逃す | docs | debt | repair | high | P1-07.14 |
| LP-07 | ADR-0069 の gemma 採用後も Qwen 期の定数・コメント・トークン列が残っている | mechanism | inconsistency | repair | med | P1-07.10 |
| LP-08 | 判定 seam の LLM 向け文がコードに正本として置かれ、ADR-0054 の外出し原則と食い違う | docs | inconsistency | neutral | high | P1-07.15 |
| LP-16 | 生成経路に `seed` が無く、再現性の方針（固定しない）が決定として記録されていない | mechanism | decision-needed | neutral | high | P1-07.15 |
| LP-17 | lab ratchet と relevance cache の pin がモデル**名**だけで、重み digest を含まない | data | defect | repair | high | P1-07.12 |
| LP-19 | `select_submolt` は自由生成 + 部分文字列一致で、None 率と部分一致率が読まれていない | mechanism | research-need | repair | med | P1-07.16 |
| LP-24 | `prompt_templates_sha256` に comment 経路に効かない入力（`domain.json` の閾値、insight 系、dead template）が混ざり、ack が積み上がる | quality | debt | neutral | med | P1-07.14 |
| LP-25 | モデル交代の手順が 7 文書に分散し、単一の runbook と「交代で失効するもの」の一覧が無い | ops | gap | repair | high | P1-07.11 |
| LP-26 | `gemma4:e4b` literal が scripts 3 箇所で `_DEFAULT_OLLAMA_MODEL` から導出されていない | ops | debt | repair | high | P1-07.11 |
| LP-28 | episode / telemetry にテンプレートの版（digest）と home override の有無が記録されず、「どの prompt が生成したか」を後から言えない | data | gap | instrument | high | P1-07.13 |
| LP-32 | identity 検証失敗時の fallback persona は 60 byte の `system.md` 1 行で、本番には eval の sentinel 検査に相当するものが無い | mechanism | risk | instrument | med | P1-07.13 |
| LP-34 | `NUM_CTX` 32k 固定と gemma の 128K 窓の取引（KV メモリ vs 全コーパス収容）が未測定 | mechanism | decision-needed | neutral | med | — |
| CH-17 | Qwen 時代の較正が `_estimate_tokens`（C2 pre-flight の推定器）のコメントに残り、gemma4 での再較正の有無がコードから読めない | mechanism | risk | repair | med（推定が安全側である可能性は高いが未確認） | P1-07.10 |

### P1-08 テストと CI の強化（macOS job・未モック LLM・順序依存・床・契約）（44 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| TQ-02 | CI は ubuntu × 3.13 の 1 セルのみ — macOS 専用のシェル層テスト 80 件は CI で一度も走らない | ops | gap | repair | high | P1-08.1 |
| TQ-03 | `verify.md`「CI 未配線」と runbook「この family に CI は無い」が stale | docs | inconsistency | neutral | high | P1-08.4 |
| TQ-04 | CI で skip が不可視（verify.sh は PASS 時に pytest 出力を捨てる） | quality | gap | instrument | high | P1-08.2 |
| TQ-05 | parametrize 内 `pytest.skip` が 89 skip を量産 | quality | debt | neutral | high | P1-08.2 |
| TQ-06 | rsync 依存テスト 2 件が skipif なしで環境依存 FAIL | quality | defect | repair | high | P1-08.2 |
| TQ-07 | `live_cli`（claude バイナリ契約の drift alarm）は CI で常に skip、pyproject のコメントが stale | ops | inconsistency | neutral | high | P1-08.4 |
| TQ-08 | `uv.lock` 非コミット — CI と clone 先の依存解決が毎回フレッシュ、ADR 間で記述が矛盾 | ops | decision-needed | neutral | high | P1-08.5 |
| TQ-09 | dev / eval 依存の更新状況（pandas は床を跨いで major 3、deepeval は 2 か月遅れの固定） | ops | debt | neutral | med | P1-08.6 |
| TQ-10 | ランタイム依存「requests + numpy のみ」は真（直接依存）— 推移的 4 件と床の下端は未検証 | security | gap | instrument | high | P1-08.1 |
| TQ-11 | CI メタ: SHA pin・最小 permissions は良好、Dependabot なし、cache 既定任せ、branch protection と所要時間は確認不可 | ops | decision-needed | neutral | med | P1-08.4 |
| TQ-12 | verify.sh full はオフラインで FAIL（pip-audit がネット必須なのに fail-soft 2 でない） | ops | gap | neutral | med | P1-08.7 |
| TQ-13 | 未モックの LLM 経路を持つテストが 78 件（test_agent.py 47）— LLM 不達 → None で「通っている」 | quality | risk | instrument | high | P1-08.8 |
| TQ-14 | テスト順序依存 — 共有 sandbox `MOLTBOOK_HOME` の状態リーク（random order で 1〜5 件赤） | quality | defect | repair | high | P1-08.9 |
| TQ-15 | conftest の `OLLAMA_TRUSTED_HOSTS=127.0.0.1` は guard に無効値として捨てられている | quality | inconsistency | neutral | high | P1-08.9 |
| TQ-16 | mock の置き場所 — 境界 mock は健全だが、内部 generate 関数の patch が約 175 箇所 | quality | debt | repair | med | P1-08.10 |
| TQ-17 | テストは仕様書か — TDD 規律は commit 粒度で実証、可読単位は崩れている | quality | debt | neutral | med | — |
| TQ-18 | ログ文言・エラー文言が仕様化されている（文字列照合 ~400 箇所） | quality | debt | neutral | med | P1-08.10 |
| TQ-19 | hypothesis は 6 ファイルのみ・常時 derandomize → 新しい入力は一度も試されない | quality | opportunity | instrument | high | — |
| TQ-20 | chaos fault 列が feed（score4 gate）経路に無い | mechanism | gap | repair | high | P1-08.12 |
| TQ-21 | ResourceWarning（unclosed sqlite）が素通り — 破損 sidecar での接続リークの疑い | mechanism | defect | repair | med | P1-08.15 |
| TQ-22 | marker 体系の形骸化（`integration` 使用 0、`unit` 19） | quality | debt | neutral | high | P1-08.8 |
| TQ-23 | 遅いテスト上位 2 件（6.3 秒）と「テストは sleep しない」規律 | quality | debt | neutral | med | — |
| TQ-24 | ゲート所要時間の実測（記録）— ゲートは軽い | ops | opportunity | neutral | high | P1-08.7 |
| TQ-26 | scripts/（週次チェーン）のカバレッジ 78% — 参照ゼロの script が 2 本 | ops | gap | repair | high | P0-03.11, P1-04.7 |
| TQ-27 | coverage がゲートでない（閾値なし、CI でレポートなし） | quality | gap | instrument | high | P1-08.7 |
| TQ-28 | ADR-0088 conformance kit は static 6 検査のみ出荷、runtime / full 23 検査が 2 か月未実装 | mechanism | gap | repair | med | — |
| TQ-32 | orphan fixture と gemma4 以前のデータ（qwen3.5:9b） | data | debt | neutral | high | P1-04.7 |
| TQ-33 | deepeval 由来の pytest plugin（xdist / rerunfailures / repeat / asyncio）が CI で自動ロードされる | ops | risk | neutral | med | P1-08.6 |
| TQ-35 | Ollama 実機スモークは opt-in の 1 テストのみ — gemma4 の logprobs / format / think の実契約は全て stub | mechanism | gap | instrument | med | — |
| TQ-36 | mutation testing — 全体適用は過剰、guard モジュール限定なら計器 | quality | opportunity | instrument（限定）/ capability-growth（全体適用） | med | — |
| TQ-37 | 長時間ソークは不要（本番が計器）、ゴールデン差分リプレイは常設化の余地 | quality | opportunity | instrument | med | — |
| TQ-39 | vulture / bandit / pip-audit 実測（記録） | quality | opportunity | neutral | high | P1-04.7 |
| TQ-40 | conftest の sandbox tempdir が cleanup されない | quality | debt | neutral | high | P1-08.9 |
| TQ-42 | docs-as-tests / absence ゲートは充実（記録）— 欠けている 2 面は Python 床と wheel | security | opportunity | neutral | high --- | — |
| CP-32 | テストに守られていない core 挙動（本観点の棚卸し） | quality | gap | repair | high --- | P0-04.6 |
| WO-30 | watchdog 本体にテストが無い（plist 生成のみ検査） | quality | gap | repair | high | P1-08.3 |
| WO-31 | 無人チェーンの shell 層テストは Linux CI で全部 skip され、CI はチェーンを一度も実行しない | quality | risk | repair | high | P1-08.1 |
| RD-24 | `uv.lock` 非追跡で検証環境が時間方向に再現できず、固定版の再ビルド記録も無い | quality | decision-needed | instrument | high | P1-08.5 |
| PF-33 | eval の `axiom` ラベルは論文の 4 公理名、judge の `{constitution}` は改正済み本文 — 対応は読者の推測 | quality | inconsistency | instrument | med | P1-08.21 |
| SA-01 | I/O 面の全数棚卸しは grep でしか得られず、機械ゲートが無い | security | gap | instrument | high | P1-06.4, P1-08.17 |
| SA-37 | 週次セッションの `--tools` 名が CLI 側で黙って捨てられる設計上の脆さは既知だが、deny の網羅テストに `.notes` / `.env` が無い | security | gap | instrument | high | P1-10.5 |
| SA-39 | 「Posts from other agents … the agent has no tool an injected instruction could call」の README 主張を裏づける否定テストが無い | security | gap | instrument | high | P1-08.18 |
| SA-41 | `api_drift_scan` が検出する仕様変更と、「新しい外向き endpoint の追加」が同じゲートを通る保証が無い | security | gap | instrument | high --- | P1-08.17 |
| AR-25 | 1 外部アダプタ原則は成立しているが、外向き HTTP の call site（Moltbook 2 + Ollama 5）を数える機械ゲートが無い | security | gap | instrument | high （→ 観点 SECURITY-ABSENCE） --- | P1-08.17 |

### P1-09 ドキュメントの同期と欠落文書（数値・CYCLES・CONFIGURATION・glossary・llms）（66 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| DC-02 | `llms.txt` / `llms-full.txt` が ADR-0108 で止まり、テスト数・ディスク量も古い | docs | inconsistency | neutral | high | P1-09.7 |
| DC-03 | HF mirror `Shimo4228/contemplative-agent`（graph.jsonld）が 2026-09-12 で止まり、repo 側の 5 ADR 分の更新が未同期 | data | inconsistency | neutral | high | P1-09.7 |
| DC-05 | README の生数値（82/547・6/11・2/4・約 10,700 patterns・as of 10-08）に更新手順が無く、データ repo はすでに 10,985 | docs | debt | neutral | high | P1-09.8 |
| DC-06 | CLAUDE.md「src の 70 ファイルが ADR 番号を直接引く」は 78 | docs | inconsistency | neutral | high | P1-09.8 |
| DC-07 | CLAUDE.md のプロジェクト固有 skills 表に `weekly-gate` が無い（11 ディレクトリ / 表 10 行） | docs | inconsistency | neutral | high | P1-09.2 |
| DC-08 | CLAUDE.md「関連リポジトリ」に `contemplative-agent-otel` が無い | docs | gap | neutral | high | P1-09.2 |
| DC-09 | CLAUDE.md「ドキュメント配置」に `docs/plans`（76 件）・`docs/diagrams`・`docs/CYCLES.md` 等が無く、`docs/plans` に README が無い | docs | gap | neutral | high | P1-09.14, P1-09.2 |
| DC-11 | 文書言語方針の穴 — 公開台帳 `rfcs/` と運用索引が日本語のみ、CYCLES / CHANGELOG は英語 | docs | decision-needed | neutral | med | — |
| DC-12 | `docs/CONFIGURATION.ja.md` に "Pipeline Prompts & View Seeds" と "Runtime Logs" の 2 節が無い | docs | inconsistency | neutral | high | P1-09.10 |
| DC-13 | `docs/CONFIGURATION.md` の目次に 2 節が無い | docs | defect | neutral | high | P1-09.10 |
| DC-15 | `CONFIGURATION.md` 内で weekly insight の既定曜日が Mon（L210）と Sat（L400）に割れ、code は Sat | docs | inconsistency | neutral | high | P1-09.4 |
| DC-16 | `CONFIGURATION.md` の distill 既定時刻 03:00、実際は 03:30 | docs | inconsistency | neutral | high | P1-09.4 |
| DC-17 | `install-schedule --weekly-submolt-scan`（Thu、ADR-0086）が CONFIGURATION / CLAUDE.md のどこにも無い | docs | gap | neutral | high | P1-09.4 |
| DC-18 | `CONFIGURATION.md` 「45 skills ≈ 36K tokens」は 53 件時点で古い | docs | inconsistency | neutral | high | P1-09.8 |
| DC-19 | テンプレート節「skills (2) / rules (2)」は `tabula-rasa` に当てはまらない | docs | inconsistency | neutral | high | P1-09.8 |
| DC-20 | `CONFIGURATION.md` が「Five maintenance skills (-ca) が integrations/ にある」と案内するが、ADR-0013 で棚上げ済みで install.sh は 0 件をコピーする | docs | defect | repair | high | P1-09.9 |
| DC-21 | README が「Configuration Guide (all commands)」と言うが CLI 節は 21 コマンド中 13 本 | docs | gap | neutral | high | P1-06.4, P1-09.10 |
| DC-22 | 環境変数の台帳が `.env.example` / CONFIGURATION 表 / code の 3 箇所で食い違う | docs | inconsistency | neutral | high | P1-06.4 |
| DC-23 | Qwen 時代の校正値・固定語が残る（glossary、`prompting.py:346`、`feed_seeder.py:59`） | docs | inconsistency | neutral | med（係数の再測定が要るかは機構側の判断 → 観点 MECHANISM） | P1-09.9 |
| DC-24 | `docs/CYCLES.md` の FRESHNESS header と master table が 2026-08-26 時点のまま（退役 prompt、存在しない job、欠けた段） | docs | inconsistency | neutral | high | P1-09.5 |
| DC-25 | 鮮度規約が「正本」と定める `scripts/weekly-pipeline.sh` 冒頭が「A-E synthesis + ja」のまま（ADR-0099 後 6 週） | docs | inconsistency | neutral | high | P1-09.6 |
| DC-26 | `weekly-report` skill の materials 既定パスが pipeline の実体と違う | docs | inconsistency | neutral | high | P1-09.6 |
| DC-27 | `docs/diagrams` の鮮度規約の適用範囲が未定義 — relevance gate（feed 側）がどの図にも無く、ADR-0113 の 2 追補で図は未更新 | docs | decision-needed | neutral | med | P1-09.19 |
| DC-29 | `docs/evidence/README.md` の索引が 38 ディレクトリ中 15 のみ | docs | inconsistency | neutral | high | P1-09.1 |
| DC-30 | `docs/runbooks/README.md` に `constitution-amendment.md` が無く、Docker の記述が残る | docs | inconsistency | neutral | high | P1-09.1 |
| DC-38 | 外部リンク（DOI 7・HF 5・記事 10・DeepWiki・Moltbook）の機械チェックが無い | docs | opportunity | instrument | high | P0-06.6 |
| DC-39 | `docs/glossary.md` は翻訳対訳表で、現行機構の語彙が無く、退役語・旧ディレクトリ名が現行扱い | docs | gap | neutral | high | P1-09.15 |
| DC-40 | 英語・概念レベルのアーキテクチャ概観が無い（README の 4 段 SVG と日本語ラベルの Archify 図のみ） | docs | gap | neutral | med | — |
| DC-41 | FAQ / トラブルシュートが無い（症状 → 原因 → 見るログ） | docs | gap | neutral | high | P1-09.17 |
| DC-43 | `AGENTS.md → CLAUDE.md` の symlink は zip / Windows / Zenodo アーカイブで壊れ、Codex には日本語の harness 固有指示が渡る | docs | risk | neutral | med | — |
| DC-45 | プロジェクト共有ファイル `Contemplative agent llms-full.txt` が v2.0.0（2026-04）時点で、現行と 5 つ以上の事実が違う | docs | debt | neutral | high | P1-09.7 |
| DC-46 | data repo の README に退役済み `rules-distill`・旧パス `logs/*.jsonl`・rules repo の誤った説明が残る | sibling:contemplative-agent-data | inconsistency | neutral | high（DATACARD の schema 欄は low） | P1-09.11 |
| CU-16 | 環境変数の文書化ギャップ（src 10 + scripts 15 種 vs CONFIGURATION 表 9 行 vs `.env.example` 6 行） | docs | gap | repair | high | P1-06.4 |
| CU-17 | CONFIGURATION.md: `init` の説明「identity + knowledge files」と identity「Starts empty at `init`」が実態（テンプレートから 7 種を複製）と違う | docs | inconsistency | repair | high | P1-09.10 |
| CU-18 | CONFIGURATION.md と `integrations/claude-code/install.sh` が存在しない `-ca` skills（ADR-0013 で棚上げ）へ誘導する | docs | inconsistency | repair | high | P1-09.9 |
| CU-19 | CONFIGURATION.md の GUARDED「content passes safety filters」は禁止語リスト + 空文字チェックのみを過大に表現している | docs | inconsistency | repair | high | P1-09.10 |
| CU-20 | CONFIGURATION.md の `install-schedule` 既定「120min sessions, distill at 03:00」が実装既定（60 分 / 03:30）と違う | docs | inconsistency | repair | high | P1-09.4 |
| CU-30 | `fcntl` 直 import のため Windows では import 時に落ちる（文書に非対応の明記なし） | ops | gap | neutral | high | P1-09.20 |
| CU-37 | `status` がどの文書にも無く、`solve` / `submolt-scan` / `shadow-constitution` / `remove-skill` / `report` は CONFIGURATION.md のコマンド節に無い。EN / JA で `--weekly-submolt-scan` の記載が食い違う | docs | inconsistency | repair | high | P1-06.4, P1-09.10 |
| CU-39 | CLAUDE.md の開発手順 `uv pip install -e ".[dev]"` は pyproject の `[dependency-groups] dev` と噛み合わない（extra ではない） | docs | inconsistency | repair | med | P1-09.9 |
| AB-05 | RFC 本文 21 本と ADR-0113 が gitignored の `.notes/` を参照している（CLAUDE.md の禁止規約違反） | docs | inconsistency | repair | high | P1-09.13 |
| AB-36 | `.ja.md` 併記は 113 本 × 2 面の同期費用で、10 月の ADR 編集 5 commit すべてが en + ja 同時編集 → 観点 DOCS | docs | debt | neutral | med | — |
| AB-39 | `docs/evidence/README.md` の索引が 22 ディレクトリ分未登録（RFC 単位 evidence を含む） | docs | inconsistency | repair | high | P1-09.1 |
| CP-30 | insight plist と memory_cmds のコメントが現行スケジュール（土 08:00・launchd 化）と食い違う | docs | inconsistency | repair | high | P1-09.4 |
| CP-31 | CYCLES.md が存在しない launchd ジョブ `com.moltbook.sync-data` を挙げ、公開データの同期は実際には手動 | docs | inconsistency | repair | high | P1-09.5 |
| DE-14 | `llms.txt` が少なくとも 8 点で現状と食い違う | docs | inconsistency | repair | high | P1-09.11 |
| DE-21 | README（data）のデータフローに退役済み `rules-distill` が残り、rules の由来が本体 README と矛盾、EN/JA の Related が不一致 | docs | inconsistency | repair | high | P1-09.11 |
| GO-45 | 憲法改正 runbook が修正済み欠陥（T-ADOPT-OVERWRITE-TARGETS）を「未修正」として手順に残している | docs | inconsistency | repair | high | P1-09.9 |
| VL-30 | runbook が修正済みの欠陥 T-ADOPT-OVERWRITE-TARGETS を「未修正・必須手順」として残す | docs | inconsistency | repair | high | P1-09.9 |
| VL-38 | rules 層の出自が repo 間で食い違う（hand-written か rules-distill か） | docs | inconsistency | repair | high --- | P1-09.12 |
| VL-43 | データ repo の説明文（llms.txt / DATACARD / README）が現行の価値層構成と食い違う | docs | inconsistency | repair | high | P1-09.11 |
| PF-30 | データリポ README が rules リポを「distilled rules」と呼び、図に退役済み `rules-distill` が残る | docs | inconsistency | neutral | high | P1-09.11 |
| PF-31 | graph.jsonld の axiom node は論文の 4 公理を指し、改正済み本番憲法との版差を持たない | docs | inconsistency | neutral | med（node description 本文は今回未確認） | P3-04.12 |
| PF-32 | README「rules (hand-written)」と、本番の 2 rule が 2026-04-11 の distill 産物らしい点が食い違う | docs | inconsistency | neutral | med（生成経路はファイル名と文体からの推定） | P1-09.12 |
| SA-03 | sync-data の実行主体・タイミングの文書が三様で食い違う（ADR-0010 / README / CYCLES） | docs | inconsistency | neutral | high | P1-09.5 |
| SA-40 | data repo の README「How data flows」図と除外説明が現行と不一致（`rules-distill` 退役、`logs/*.jsonl`） | docs | inconsistency | neutral | high | P1-09.11 |
| SB-35 | 本体 CLAUDE.md の「関連リポジトリ」節に otel / AKC / AAP が無い（他の面のリンク・DOI は正しい） | docs | gap | repair | high | P1-09.2 |
| WO-20 | Cycle #1 / #2 の heartbeat（`com.shimomoto.daily-research`、`com.shimo.wiki-refresh`）は repo 外で、CYCLES.md の検証手順は第三者に実行不能 | docs | inconsistency | neutral | med | P1-09.5 |
| WO-21 | `docs/plans/` 77 ファイルがオーナー環境の絶対パス・個人名・`~/.claude/plans/` 参照を含んだまま tracked | docs | debt | neutral | med | P1-09.14 |
| WO-38 | CYCLES.md は 350 commit / 38 日遅れで、row 5 の段構成が現行（7c / 7d / Sample splice）と不一致 | docs | inconsistency | repair | high | P1-09.5 |
| WO-40 | `install-schedule` の文書が実装と食い違う（`--weekly-submolt-scan` の欠落、既定 60 分 / 03:30 vs 文書 120 分 / 03:00） | docs | inconsistency | repair | high | P1-09.4 |
| WO-41 | plist テンプレート内の時刻コメントが旧設計（packet 13:30、insight Mon 08:00）のまま | docs | inconsistency | repair | high | P1-09.4 |
| OI-41 | `docs/evidence/` 37 dir のうち README の索引に載るのは約 13 で、ADR-0075 追補が「監査ログの代わり」と定めた凍結結果が発見不能 | docs | debt | repair | high | P1-09.1 |
| TQ-41 | Claude plan-mode のファイルが `docs/plans/` に tracked（markdownlint 除外） | docs | inconsistency | neutral | med | P1-09.14 |
| RD-14 | CLAUDE.md の開発環境手順 `uv pip install -e ".[dev]"` は何も入れない（extras は禁止されている） | docs | inconsistency | repair | high | P1-09.9 |
| RD-26 | OS 前提（macOS / launchd）が暗黙で、Linux の代替もその「無い」宣言も無い | docs | decision-needed | neutral（cron 例を足すなら capability-growth） | high | P1-09.20 |

### P1-10 セキュリティ: threat model・SECURITY.md・I/O 面の機械ゲート・鍵の所在（24 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| SA-02 | `embeddings.py` の Ollama POST だけ `allow_redirects=False` が無い | security | defect | repair | high | P1-10.6 |
| SA-04 | dialogue の peer サブプロセスが親 env（`MOLTBOOK_API_KEY` を含む）を丸ごと継承する | security | risk | repair | high | P1-10.7 |
| SA-05 | API エラー本文（最大 500 文字）が WARNING 経由で読める `*.log` に落ちる — 受容済み残余として未記録 | security | risk | neutral | med | P1-10.1 |
| SA-07 | 週次無人セッションの Read 許可が `$PROJECT_ROOT/**` 全体に及び、`.env` / `.notes/` / `.claude/settings*` に deny が無い | security | risk | repair | med（`.env` 実在は未確認。許可の構造は確実） | P1-10.5 |
| SA-09 | 鍵の保管方式（keychain 不使用）と回転手順が決定として書かれていない | docs | gap | neutral | high | P1-10.9 |
| SA-18 | 他エージェントの投稿本文を cloud judge（TypeSafe / Jev）へ送る研究経路が security 文書に無い | research | docs | neutral | high | P1-10.1 |
| SA-20 | comment-report の `Title` と相手名は defang されない（2026-04-01 の残余 #4 が未解消） | security | risk | repair | high | P1-10.8 |
| SA-23 | 土曜の対話セッション（全ツール）が comment-report の第三者本文を読む受容の根拠が書かれていない | docs | gap | neutral | high | P1-10.1, P1-10.8 |
| SA-24 | 同梱の Claude Code hooks（`integrations/claude-code/`）が ADR-0107 以後の配置とずれている | docs | debt | repair | high | P1-10.4 |
| SA-25 | 公開 `docs/plans/`（77 件）は週次ゲートの機微点検の対象外 | docs | risk | neutral | med | P0-03.6, P1-10.12 |
| SA-26 | 出力サニタイザは語彙パターンのみで、稼働中の鍵の実値を照合しない | security | risk | instrument | med | P1-10.10 |
| SA-29 | 生きた threat model 文書が無い（CLAUDE.md の節と 2026-04-01 のスナップショットに分散） | docs | gap | neutral | high | P1-10.1 |
| SA-30 | `SECURITY.md`（脆弱性報告先）が無く、data repo の削除依頼窓口とも未接続 | docs | gap | neutral | high | P1-10.3 |
| SA-33 | HF token と git credential が「鍵」の棚卸しに入っていない | security | docs | neutral | med（実際の token 種別は未確認） | P1-10.9 |
| SA-35 | ADR-0007 の「Docker: network isolation」「identity.md is validated」など退役・現状の記述が残り、Amendment だけが現実を言う | docs | inconsistency | neutral | high | P1-10.2 |
| SA-38 | `backup-runtime.sh` は `agent-launchd.log`（汚染済み）を私的 repo に push し続ける — 汚染の終了条件が無い | ops | debt | neutral | med | P1-10.4 |
| DC-31 | 同梱 hooks（`integrations/claude-code/hooks/`）が ADR-0107 以前の設計で、README.md の説明・オーナーの実 hook と食い違う | security | defect | repair | high | P1-10.4 |
| DC-32 | 現行の脅威モデルが日本語 CLAUDE.md にしか無く、`docs/security/` は 2026-04 止まり、`SECURITY.md` が無い | security | gap | instrument | high | P1-10.1 |
| GO-29 | SECURITY.md（脆弱性報告窓口）が無い | security | gap | neutral | high --- | P1-10.3 |
| RD-34 | 公開リポジトリの受付面（SECURITY.md / CONTRIBUTING.md）が無い | docs | gap | neutral | med | P1-10.3 |
| AR-21 | ADR-0007 §4 が挙げる `VALID_MODEL_PATTERN` は実装に存在しない | docs | inconsistency | neutral | high （→ 観点 SECURITY-ABSENCE / DOCS-CONSISTENCY） | P1-10.2 |
| AR-22 | `core/embeddings.py` の `requests.post` だけ `allow_redirects=False` が無い | security | inconsistency | repair | high （→ 観点 SECURITY-ABSENCE） | P1-10.6 |
| WO-17 | repo 同梱の episode-log hook はハーネス側と境界が違う（`logs/*.jsonl` 全部 vs `logs/episodes/`） | security | inconsistency | repair | high | P1-10.4 |
| CU-21 | `integrations/` の hooks / README が ADR-0107 以前のパス（`$MOLTBOOK_HOME/logs/*.jsonl`）を守り、自己書き込み jsonl を過剰にブロックする | security | inconsistency | repair | med | P1-10.4 |

### P1-11 兄弟 repo の処遇（cloud / mlx / otel / rules）（42 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| SB-01 | cloud / mlx は `DecisionBackend` を実装せず、注入時も relevance gate は Ollama + gemma に依存する | sibling:cloud, sibling:mlx | gap | repair（docs）/ capability-growth（backend） | high（機構）/ med（mlx の二重常駐の実害は未計測） | P1-11.5 |
| SB-02 | 兄弟注入時の `exclusive` は「別モデル常駐」ではなく「モデル名不一致」で決まり、cloud 下では毎バッチ gemma を無駄に再ロードする | mechanism | defect | repair | med | P1-11.5 |
| SB-03 | mlx 実行は生成モデルを gemma から Qwen に替える — README の「1.8× / 3.4 GB」は Qwen 時代の比較で、現行本番との比較が無い | sibling:mlx | inconsistency | repair | high（docs）/ low（gemma MLX 重みの可用性） | P1-11.2 |
| SB-04 | otel 変換器は decision 行（`kind:"decision"`、ADR-0112）を知らず、生成 span として誤変換する | sibling:otel | gap | instrument | high | P1-11.6 |
| SB-05 | otel は ADR-0068 追補 / ADR-0087 で増えた llm-calls フィールド（`thinking_source`、`input_tokens`、`token_count_source` 等）を写していない | sibling:otel | debt | instrument | high | P1-11.6 |
| SB-06 | otel は provider を `"ollama"` に固定しており、cloud / mlx 注入下の行を誤表示する | sibling:otel | defect | instrument | high | P1-11.6 |
| SB-07 | embed 行の誤変換は「routine use に昇格したら直す」と先送りが決まっているが、昇格の判定者・期限が無い | sibling:otel | debt | neutral | high | P1-11.1 |
| SB-08 | otel `llms.txt` は「run ID が無いので time-gap clustering」と古い説明を残している | sibling:otel | inconsistency | repair | high | P1-11.2 |
| SB-09 | otel のテストは合成 fixture のみで、本体の writer が書く実スキーマと突き合わせる契約テストが無い | sibling:otel | gap | instrument | high | P1-11.6 |
| SB-10 | otel が読むのは 9 つの監査ログ族のうち 3 つだけ（relevance / skill-selection / comment-outcomes / constitution-shadow / injection-detect は対象外） | sibling:otel | opportunity | instrument | med | — |
| SB-11 | otel の Jaeger / otel-desktop-viewer 手順は存在するが、検証した版・日付が固定されていない | sibling:otel | debt | neutral | med | P1-11.2 |
| SB-12 | 兄弟 repo 自身の pytest はどこでも定期実行されない（release gate は kit の static 検査だけ） | quality | gap | repair | high | P1-11.4 |
| SB-13 | cloud の README / llms.txt / `__init__` は本体の既定を「Qwen3.5 9B」と書いている（本番は 2026-06-28 から gemma4:e4b） | sibling:cloud | inconsistency | repair | high | P1-11.2 |
| SB-14 | cloud / mlx の README は依存を `contemplative-agent>=2.0` と書くが pyproject の pin は `>=2.7.0` / `>=2.10.0` | docs | inconsistency | repair | high | P1-11.2 |
| SB-15 | cloud README の `pip install contemplative-agent-cloud` は PyPI 公開を前提にしているが、公開の痕跡が無い | sibling:cloud | inconsistency | repair | low（PyPI 未確認） | P1-11.2 |
| SB-16 | cloud の OpenAI 既定 `gpt-5` は live API で一度も検証されておらず、`max_tokens` 拒否の可能性を README 自身が書いている | sibling:cloud | risk | repair | high | P1-11.2 |
| SB-17 | `agent-run` skill の mlx 前提検査は `run-with-mlx.sh` より厳しく、`uvx` だけの導入を拒否する | ops | inconsistency | repair | high | P1-11.2 |
| SB-18 | 本体側の文書は cloud を「不適合（T-CLOUD-SIBLING-STALE 未決）」と書き続けているが、2026-08-04 に解決済みで 2026-09-12 には 3 backend とも PASS | docs | inconsistency | repair | high | P1-11.3 |
| SB-19 | 兄弟 repo に release tag も CHANGELOG も「どの main 版で検証したか」の記録も無い（mlx の pyproject コメントだけ） | ops | debt | repair | high | P1-11.2 |
| SB-20 | cloud / mlx のテストが本体の private `_circuit` に直接触れている（公開の `circuit_reading()` がある） | quality | debt | repair | high | P1-11.4 |
| SB-21 | 契約テストを兄弟 repo に導入する — cloud / mlx の自前テストは `isinstance(..., LLMBackend)` だけで、ADR-0088 の kit を一度も import していない | quality | gap | repair | high | P1-11.4 |
| SB-22 | runtime レベルの適合検査（`BackendProbe`）はどの兄弟にも無く、kit の 23 検査は本体側でも未実装 | quality | gap | instrument | med | P1-11.9 |
| SB-23 | cloud は `$MOLTBOOK_HOME/cloud.env` の API key をパーミッション検査なしに読む | security | risk | repair | high | P1-11.7 |
| SB-24 | cloud の `think` 非対応は 2026-08-04 に「不採用」と決まっているが、ADR-0069 は今も「cloud が thinking を埋められる」と示唆し、決定は `docs/plans/` にしか無い | docs | inconsistency | repair | med（決定の正本が ADR/RFC にない） | P1-11.2 |
| SB-26 | 【決定が必要】cloud repo の処遇 — 維持（対照実験の道具として）/ 凍結 archive / 削除 | sibling:cloud | decision-needed | neutral（維持なら capability-growth の審査対象） | med | P1-11.1 |
| SB-27 | 【決定が必要】mlx repo の処遇 — ADR-0067 の反転条件が満たされるまで凍結するか、gemma で再計測するか | sibling:mlx | decision-needed | neutral | med | P1-11.1 |
| SB-28 | 【決定が必要】otel repo の処遇 — schema 追従義務を本体 release gate に付けて維持するか、v2.10.0 schema で凍結するか | sibling:otel | decision-needed | instrument / neutral | med | P1-11.1 |
| SB-29 | rules repo の IPD ベンチは本体の憲法改正 runbook の必須依存だが、rules 側にその使われ方（gemma4:e4b・n=10・±0.13・`--prompt-file`）の記録が無い | sibling:rules | gap | repair | high | P1-11.10 |
| SB-32 | rules repo の `prompts/*.md` はベンチ package 内に複製されており、同一性を守るテストが無い | sibling:rules | risk | repair | high | P1-11.10 |
| SB-33 | rules repo の AI 向け文書に古い参照が残る（`contemplative-moltbook` リンク、AAP DOI の誤記、Related Projects の不一致、"Last updated" 日付） | sibling:rules | inconsistency | repair | high | P1-11.11 |
| SB-34 | rules repo の CLAUDE.md が著者私有の Obsidian vault パスを参照している | docs | debt | neutral | high | P1-11.11 |
| SB-36 | rules ADR-0005（operator-keyed の効力）は 2026-07-06 から「観察中・未確認」のまま期限が無い | sibling:rules | research-need | neutral | med | P1-11.12 |
| SB-37 | 兄弟 3 repo の lint / 型検査設定が不揃い（ruff なし、pyright は otel のみ） | quality | debt | neutral | high | P1-11.4 |
| SB-38 | `check-sibling-backends.sh` と `agent-run` skill は兄弟 checkout を `../<固定名>` と `.venv` の存在で探し、frozen / absent の区別を持たない | ops | debt | repair | med --- | P1-11.1 |
| AR-23 | runbook の「cloud は失敗して当然（2026-08-02）」は cloud が 8/17 に Protocol v2 へ追従した後も残っている | sibling:cloud | inconsistency | neutral | med（未実行） （→ 観点 SIBLINGS） | P1-11.3 |
| AR-24 | conformance kit は static 6 / 29 のまま 2 か月で、`--decision` の target は script に無い | quality | decision-needed | neutral | high （→ 観点 SIBLINGS） --- | P1-11.9 |
| AR-35 | otel の mapping.md が退役済みの `solver_path = llm_reason` を正として持つ | sibling:otel | inconsistency | neutral | high （→ 観点 SIBLINGS） | P1-11.6 |
| SA-19 | cloud sibling は Moltbook 書き込みと推論プロバイダへの本文 egress を 1 プロセスに同居させる — ADR-0015 の定義外 | sibling:cloud | decision-needed | neutral | med | P1-11.1, P1-11.7 |
| SA-28 | 兄弟 3 repo に CI・pip-audit・lock が無く、cloud は anthropic/openai SDK を下限 pin のみで抱える | sibling:cloud / sibling:mlx / sibling:otel | gap | neutral | high | P1-11.1 |
| SA-34 | OTel sibling の `--endpoint` に host 制限が無い | sibling:otel | risk | neutral | high | P1-11.8 |
| PF-19 | ルールリポ README / custom.md の「empirically validated」は n=2 探索結果と主張強度が合わない | sibling:contemplative-agent-rules | inconsistency | neutral | high | P1-11.11 |
| RF-43 | rules repo の IPD ベンチが本体の較正契約・本番モデルと同期していない（最終 commit 2026-07-07） | sibling:contemplative-agent-rules | inconsistency | repair（文書） | high | P1-11.10, P1-11.11 |

### P1-12 承認ゲートの記録を「責任の行為」にする（approver・reason・却下本文・GOVERNANCE.md）（26 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| GO-01 | 承認記録に「誰が」（approver）が無い — AAP ADR-0005/0006/0008 との突き合わせ | governance | gap | instrument | high | P1-12.1 |
| GO-02 | 承認・却下の「根拠」が記録されない（`reason` は remove-skill のみ必須） | governance | gap | instrument | high | P1-12.1 |
| GO-03 | 却下された提案の本文が破棄される（hash だけ残る） | data | gap | instrument | high | P1-12.2 |
| GO-04 | 承認記録（audit.jsonl）が公開 data repo に同期されず、README の gate record が第三者検証不能 | data | gap | instrument | high | P1-12.4, P2-05.2 |
| GO-05 | 監査行の書き込みに失敗しても採用が続行する | governance | defect | repair | high | P1-12.3 |
| GO-06 | 監査ログの改竄耐性は「0600 + append 規約 + 週次 private backup」まで | governance | risk | neutral | med | P1-12.4 |
| GO-07 | `adopt-staged --yes`（一括自動承認）の存在と、憲法改正 2 件での使用 — AAP ADR-0005「No --auto flag」との不整合 | governance | decision-needed | neutral | high | P1-12.5 |
| GO-08 | 手編集バイパス（識別・憲法・skills）と rules の無監査 — ADR-0012 の 2026-04-17 方針（auditable CLI）が未完 | governance | gap | instrument | high | — |
| GO-09 | 「人間の判断を転記した」記録は転記者（Claude）の自己申告であり、承認主体の証跡が無い | governance | risk | instrument | med | P1-12.1 |
| GO-10 | 承認記録のスキーマ仕様が存在しない（docstring が正本） | docs | gap | instrument | high | P1-12.4 |
| GO-14 | admission（人間の唯一の権限点）が台帳に記録されず、AI 単独で admit されたかを機械的に観測できない | governance | gap | instrument | high | P1-02.2 |
| GO-17 | 「Claude Code が承認者になれる」設計痕跡（ADR-0012 代替案 1、`--yes` の設計意図）が AAP ADR-0008「LLM as accountable operator — rejected」と文書上で閉じていない | governance | inconsistency | neutral | high | P1-12.5 |
| GO-21 | 役割定義・承認権限・レビュー契約の正本が repo 外（`~/.claude/`、claude-harness）にあり、本体だけでは責任構造を再現できない | docs | gap | instrument | high | P1-12.7 |
| GO-22 | 退役済みの `human-gate.md` を ADR-0085 と weekly-gate SKILL.md が現役の規範として引用している | docs | inconsistency | repair | high | P1-12.7 |
| GO-23 | 「artifact class × 承認権限」の表が本体に無い（AKC ADR-0028 にだけある） | docs | gap | instrument | high | P1-12.7 |
| GO-27 | 9 サイクル表に「記録の所在」「承認者」「監査証跡の公開/非公開」の列が無い | docs | gap | instrument | high | P1-12.7 |
| GO-47 | ADR-0012 の「Claude Code がオーケストレーターの場合の承認フローは検討要」が、以後の設計（weekly-gate / ADR-0085 / 0098）で答えが出たのに追補されていない | docs | inconsistency | repair | high --- | P1-12.5 |
| CU-23 | `adopt-staged` の audit 行に「誰が」「なぜ」が無い（`reason` は archive と `remove-skill` のみ） | governance | gap | instrument | high | P1-12.1 |
| CU-24 | weekly-gate の `gate_item` 行（recommendation / decision）と `audit.jsonl` の行が相互参照されず、理由も持たない | governance | gap | instrument | med | P1-12.1 |
| CU-25 | ADR-0012「`--auto` を提供しない」と `adopt-staged --yes`（audit source `stage-adopted-auto`）の整合が ADR-0012 本文に追補されていない | governance | inconsistency | neutral | med | P1-12.5 |
| SA-21 | ADR-0012 は「確認を飛ばす flag」を却下しているが `adopt-staged --yes`（stage-adopted-auto）が存在し、土曜ゲートの選択肢に載っている | governance | inconsistency | neutral | high | P1-12.5 |
| VL-03 | 公開 insight-review に裁定結果が追記されず、推奨だけが残る | docs | gap | instrument | high | P2-05.2, P2-05.7, P3-02.1 |
| VL-04 | audit 行の `path` が実在しないファイルを指す行が残る（憲法 08-09、identity 08-15） | data | debt | repair | high | P1-12.4, P2-05.8 |
| VL-08 | hand-edit 検知器 `value_layer_approval_join.py` が週次チェーンに配線されていない | ops | gap | instrument | high | P2-05.2 |
| VL-16 | 退役（archive）の候補は公開、結果は非公開 — 出口の記録が片側だけ | governance | inconsistency | instrument | high | P2-05.2 |
| WO-45 | 【責任接点 3】復元権（`skills/.archive/` から戻す）が人間だけの操作として明記されているが、復元の記録面が無い | governance | gap | instrument | high | — |

### P1-13 AI 判断役の権限境界と帰属表示の明文化（14 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| GO-13 | 判断役（AI）が 2026-09-15 以降、保護クラス外の task output を merge/push している — CYCLES.md「Every promotion stays human」と矛盾し、オーナー原則「AI オーケストレーターは責任構造を破壊」との整合判断が本体側に無い | governance | decision-needed | neutral | high | P1-13.1 |
| GO-15 | 週次無人セッション（1 セッション多役）は「1 エージェント 1 タスク」からの意図的逸脱であり、AAP ADR-0010 の Phase-crossing decision として未記録 | governance | inconsistency | neutral | high | P1-13.1 |
| GO-19 | enum で名指す判定（relevance / skill selection）は判定者ピンと再生記録を持つが、prose 判定（週次診断・ゲート推奨・triage の worth 判定）は「誰の判断か」が enum 化されていない | governance | inconsistency | instrument | med | P1-13.2 |
| GO-20 | RFC-0048 層 1「決定論なら機械が承認を待たず archive」は AAP ADR-0005（削除は行動変更）とどう整合させるかの判断が未記録 | governance | decision-needed | neutral | high --- | P2-07.1 |
| GO-26 | AKC 6 フェーズ ↔ 本体の写像が 4 つの面で食い違う | docs | inconsistency | repair | high | P1-13.7 |
| GO-28 | CONTRIBUTING / CODE_OF_CONDUCT / GOVERNANCE が無く、外部 PR が既に来ている | docs | gap | neutral | high | P1-13.5 |
| GO-31 | Claude 生成コードの帰属表示が不統一: Co-Authored-By は 4/447 commit、cloud セッションは author "Claude"、ローカルはオーナー名義 — オーナーの認識（GitHub が自動表示）と実態が不一致 | governance | inconsistency | neutral | high | P1-13.3 |
| GO-32 | 判断役（AI）が書く公開記録（`docs(rfcs)` commit、RFC の state 変更、merge commit の "judge:" 注記）がオーナー名義で、人間記述と区別できない | governance | inconsistency | instrument | high | P1-13.3 |
| GO-34 | クロスモデルレビュー（codex / opus / code-reviewer）の記録が commit 本文の散文で、機械可読でない | docs | debt | instrument | med | P1-13.3 |
| GO-35 | README / CITATION / Zenodo に AI 支援開発の開示文が無い | docs | gap | neutral | high --- | P1-13.4 |
| GO-36 | LICENSE の著作権者表記「Shimo」が CITATION.cff / pyproject / codemeta の「Tatsuya Shimomoto」と不一致 | docs | inconsistency | neutral | high | P1-13.6 |
| GO-37 | 本体にライセンス組合せ（コード MIT / データ CC0 / 論文 CC BY / 憲法原文の出典）を 1 箇所で述べる NOTICE が無い | docs | gap | neutral | med | P1-13.6 |
| WO-16 | task-triage loop（水 17:07 / 土 14:07）は公開台帳に無人で書き込む主体なのに、本 repo に契約が無い | governance | gap | neutral | high | P1-13.2 |
| DC-42 | CONTRIBUTING / CODE_OF_CONDUCT / issue・PR テンプレ / ADR テンプレが無い — 外部貢献を受けるかの方針が未宣言 | governance | decision-needed | neutral | med | P1-13.5 |

### P1-14 CLI の残りの UX 整備（`.last_insight` の起点・テンプレート skills・installer の前提・`init` の Tier）（13 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| CU-07 | 新規 `init` には `.last_insight` が無く、scheduled な `insight --stage` が手動 `--full` まで恒久的に拒否される | ops | gap | repair | high | P1-14.2 |
| CU-08 | 既定の APPROVE モードは毎セッション「購読確認 ×8」+ upvote / follow / mark-read の確認を出す — README「post ごとに OK を待つ」と不一致 | docs | inconsistency | repair | high | P1-09.10 |
| CU-13 | `domain.json` だけが `MOLTBOOK_HOME` に置けず、plist も `--domain-config` を渡さない。`repo_url` と submolt 一覧はオーナー固有 | ops | gap | neutral | high | P1-14.6 |
| CU-15 | home prompts の upgrade ドリフト: 既存コピーは凍結され、packaged の更新が届かず、差分警告も無い | ops | risk | instrument | high | P1-07.13 |
| CU-22 | テンプレートの skills 20 本すべてが自前の品質検査（`## Problem` / `## Solution`）に落ち、live store の形式とも違う | value | inconsistency | neutral | high | P1-14.5 |
| CU-28 | `install-schedule` が `<repo>/.venv/bin` と `<repo>/config/launchd` の実在を要求する | ops | gap | repair | high | P1-14.6 |
| CU-29 | 非 macOS にはスケジューラの手引きが無い（`install-schedule` は darwin 限定、`--uninstall` は無チェック、watchdog / backup は macOS 固有） | ops | gap | neutral | high | — |
| CU-35 | `--help` の並びが導線順でなく、内部・検証用コマンド（`solve`、`dialogue-peer`）が同列に露出する | docs | gap | neutral | high | — |
| CU-36 | `init --template` の help にテンプレート一覧が出ない（誤入力したときだけ列挙される） | docs | gap | neutral | high | — |
| CU-38 | `init` の Tier が `LLM_FULL`（LLM・domain 設定の配線を要求）で、`CONTEMPLATIVE_CONFIG_DIR` の不備が import 時 traceback になる | quality | inconsistency | repair | med | P1-14.9 |
| CU-40 | `install-schedule --help` に内部史（「ADR-0074's original Monday default was retired 2026-07-29」）が漏れている | docs | debt | neutral | high | — |
| CU-41 | `report` と `generate-report` の命名が「何の report か」を伝えない | docs | debt | neutral | med --- **既に対処済み／意図通りと確認し、項目にしなかったもの**: `register --name` 必須化と `.env.example` の書き直し（`737133e`）、feed fail-closed の既定修理（`4b85f22`、`2cad850` で installer 懸念は不成立と確認）、`--session` の 1..1440 範囲検査、`adopt-staged` の中断契約（rc=2 + "No changes made"）、`remove-skill --dry-run`、埋め込みモデル較正ドリフト WARNING（`core/embeddings.py:54-72`）、未知 face の WARNING、transport 失敗の api-audit 記録、`dialogue` が production home を拒否する設計。 | — |
| RD-04 | `install-schedule` は「checkout 直下の `.venv/bin`」と「checkout の `config/launchd`」を決め打ち | ops | debt | repair | high | P1-14.6 |

### P1-15 relevance face の較正と face ループの昇格（RFC-0047）（13 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| LP-09 | 判定コールの temperature が face ごとに 0 と 1.0 に分かれ、`generate()` の docstring と face 台帳のどちらにも根拠が無い | mechanism | inconsistency | instrument | high | P1-15.1 |
| LP-11 | 閾値 0.3 は enforce 前の 150 行（precision 0.618）で置かれ、enforce 後の再読は on_topic 10 行に乗る — post 単位・新 strata での再導出が予定に無い | research | research-need | instrument | high | P1-15.2 |
| LP-12 | temperature 0 の logprobs は run 間で bit 再現せず、閾値近傍の 1 回読みは実質コイン投げ | mechanism | risk | instrument | high | P1-15.3 |
| LP-13 | P(directly on-topic) の較正（reliability / ECE）が未測定のまま report に「確率」として出る | research | research-need | instrument | med | P1-15.4 |
| LP-14 | 4 段ラベル A〜D の固定順（低→高）による位置バイアスが score4 で未測定 | research | research-need | instrument | med | P1-15.4 |
| LP-15 | 真値の出所が RFC-0047（opus 二値）と pilot の実践（Jev）で食い違い、lab ratchet の再ラベルが閉じたホスト API に依存する | research | inconsistency | neutral | high | P1-15.1 |
| LP-23 | relevance face には Face A の `check_staleness` に相当する決定論検査が無く、RFC-0047 の merge 条件も未配線 | quality | gap | instrument | high | P1-15.5 |
| LP-29 | RFC-0047 の解除条件「2 face の決着」は実質成立しており、昇格（ADR + CYCLES.md #5/#6）を起票できる | governance | decision-needed | instrument | high | P1-15.1 |
| LP-31 | relevance gate の domain（identity + axioms）は月次で変わるが、identity adopt 後に gate 率を読む予定が無い | research | research-need | instrument | med | P1-15.2 |
| LP-33 | `top_logprobs` 上限 20 は Ollama 0.34.2 の値で、Ollama 更新と `decision_reason` を突き合わせる読みが無い | ops | risk | instrument | med | P1-15.3 |
| LP-35 | 判定面ごとの失敗時の向き（fail-open / fail-closed / skip）が混在し、一覧がどこにも無い | docs | inconsistency | neutral | high --- | P1-15.1 |
| OI-32 | relevance shadow→enforce（ADR-0113）は事前登録した gate 率予測（0.346 ± 6pt）が不成立（実測 0.127）のまま enforce・唯一判定化し、face gate の keep/kill が未決 | mechanism | risk | value-steering-risk | high | P1-15.2 |
| TQ-31 | eval が測る face は comment 生成 1 経路（prompt テンプレート 39 本中） | research | gap | instrument | med | P1-15.1 |

### P2-01 北極星の読み値を機械化する（止まる・負荷・自己調節・一致率）（19 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AB-29 | 「機構層が止まる」の計測単位が新設 ADR 数だけで、追補・注記・src 変更に動きが移った現状を捉えられない | mechanism | gap | instrument | high | P1-01.1, P2-01.5 |
| AB-30 | ADR-0080 追補 A の「負荷→0」は計器が無く測定不能だが、材料（gate_record）は既にある — 「負荷」の定義と読みを決める必要がある | mechanism | decision-needed | instrument | high | P2-01.3 |
| AB-45 | 無人チェーンの F1 起票が毎週 1 本続いており、「修理が必要な故障」の発生率が下がっていない | mechanism | risk | instrument | high | P2-01.3 |
| OI-03 | `pipeline-metrics.jsonl` は gate_record/gate_item を書くが読み手がゼロで、census 登録行は退役した `phase`/`verdict` を問うている | mechanism | defect | instrument | high | P2-01.1 |
| OI-04 | ADR-0099 Review-when の「gate の推奨一致率」トリガーに計算器が無く、RFC-0048 も手読みを前提にしている | governance | gap | instrument | high | P2-01.1 |
| OI-20 | 「機構層が止まった度合い」を示す計器が無い — 手測りでは src/scripts の月次 commit が 08: 56 → 09: 151 → 10: 7（9 日間） | mechanism | gap | instrument | high | P1-01.1, P2-01.5 |
| OI-21 | 計器複合体は ADR-0101 の測定（約 17.8k 行、2026-08-29）から core 6.9k + scripts 20.1k 行へ成長しており、溶解義務の後に計器が増えている | mechanism | risk | instrument | med | P1-01.1, P2-01.5 |
| OI-22 | 人間ゲート負荷（decisions per week）の読みは gate_record / gate_item / Inventory 行として既に存在するが集計器が無く、ADR-0080 の再読トリガーが発火しない | governance | gap | instrument | high | P2-01.1 |
| OI-44 | 週次 LLM セッションが計器の読みから RFC draft を起票する経路（`claims.py spawn`）は観測→提案の間接経路で、起票率・採択率の読みが無い | governance | risk | instrument | med | P2-01.3 |
| WO-01 | 「負荷→0」の読み値はすでに文書に出ているが、負荷を縦断で読む計器が無い | ops | gap | instrument | high | P2-01.3 |
| WO-02 | 判断負荷はすでに週 0〜3 件まで落ちており、残る負荷は「読む・説明する・公開 commit する」側にある | ops | research-need | neutral | high | P2-01.3 |
| WO-05 | 土曜ゲートの所要時間が記録されず、ADR-0098 の「> 2h が常態なら再設計」が判定できない | ops | gap | instrument | high | P2-01.2 |
| WO-06 | 推奨↔裁定の一致率が ~100% で推移している兆候があるが、一致率を計算する計器が無い | governance | risk | value-steering-risk | high | — |
| WO-33 | 「自己調節して回る」の判定基準が未定義で、現状の計器では機械的に判定できない | governance | gap | instrument | high | P2-01.5 |
| WO-34 | 現状の数値では未達: 直近 6 週すべてで人間介入があり、ゼロ介入週は 0/6 | research | research-need | neutral | high | P2-01.5 |
| WO-35 | 「停止」と「自己調節」の区別が無い — insight 候補 0 が 3 週続く状態をどう読むか | ending | decision-needed | neutral | med | P2-01.5 |
| GO-18 | 土曜ゲートの推奨と裁定の一致率 100%（45/45）— 実効フィルタ化の再来リスクと監査の実施時期が未定 | governance | risk | value-steering-risk | high --- | — |
| VL-36 | 推奨↔裁定 100% 一致は「実質の判断主体が Claude（cloud モデル）」であることを示し、記録にモデル名が残らない | governance | decision-needed | value-steering-risk | high | — |
| DE-41 | オーナー不在時に「自己調節」と「停滞」を区別する合図（dead-man）が無く、ゲートを飛ばしても何も起きない | ending | decision-needed | instrument | med | P2-01.6 |

### P2-02 Claude Code 依存の決着（headless 週次セッションの位置づけ）（7 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| WO-09 | 【decision-needed】headless `claude -p` を「機構層」と見なすか「オーナーの作業環境」と見なすか | governance | decision-needed | neutral | high | P2-02.1 |
| WO-10 | 「instruments だけ回す」モードが存在しない — report 段を外すとチェーンが REPORT_MISSING で止まる | mechanism | gap | repair | high | P2-02.2 |
| WO-11 | 週次文書を書いた Claude のモデル ID / CLI 版が文書にも監査ログにも記録されない | research | gap | instrument | high | P2-02.3 |
| WO-12 | 週次セッションの入力は毎週 ~2 MB、失敗時の再実行手順が runbook に無い | ops | gap | repair | med | P2-02.5 |
| WO-13 | `claude` CLI の tool 名が黙って落ちる契約（C-SCOPE-8）は real CLI のある Mac でしか検査されない | quality | risk | repair | med | P2-02.6 |
| AB-31 | 無人 weekly チェーン自体が「Claude Code の関与」であり、ADR-0080 追補 A の文言と構造的に矛盾する | governance | inconsistency | neutral | high | P2-02.1 |
| DC-35 | 「cloud なし」の主張の範囲が不明確 — 週次チェーンと evals は `claude` CLI、`sync-data` は GitHub + HF へ出る | research | inconsistency | neutral | high | P2-02.4 |

### P2-03 私的ハーネス依存を閉じる（claims.py・release skill・パス・inbox）（9 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| WO-14 | 本 repo の運用モデルはオーナーの私的ハーネス（`~/.claude/`）無しでは閉じない — 参照の全件表 | ops | decision-needed | neutral | high | P2-03.1 |
| WO-15 | 無人チェーンが repo 外スクリプト（`claims.py`）を実行し、起票の系譜が非公開 `.notes/claims.jsonl` にしか残らない | ops | risk | repair | high | P2-03.2 |
| WO-18 | data repo / backup repo のパスがオーナーのディレクトリ構成にハードコードされている | ops | debt | repair | high | P2-03.5 |
| WO-46 | 無人チェーンが `rfcs/`（tracked）の working tree に書き、土曜まで未コミットのまま置く | ops | risk | repair | med | P2-03.3 |
| AB-04 | RFC の規約・状態語彙・RFC→ADR 昇格条件の正本が外部 repo（claude-harness）にあり、公開 repo だけでは台帳が解釈できない | governance | debt | repair | med | P2-03.4 |
| AB-32 | 無人チェーンが依存する `~/.claude/scripts/claims.py` と task-triage loop は repo 外で、依存を記録した ADR が無い | ops | debt | repair | med | P2-03.1 |
| GO-16 | 起票 → claim の鎖が `~/.claude/scripts/claims.py` に依存し、失敗しても WARNING で続行する | ops | risk | instrument | med | P2-03.2 |
| CU-31 | オーナー固有パスの hardcode（data repo / `claims.py` / `claude` CLI / HF dataset 名）が `sync-data` と weekly chain を第三者非互換にしている | ops | debt | repair | high | P2-03.5 |
| RD-27 | `sync-data` / weekly-analysis がオーナーの固定パス `$HOME/MyAI_Lab/contemplative-agent-data` を決め打ち | ops | debt | repair | high | P2-03.5 |

### P2-04 無人チェーンの検知面と停止手順（watchdog・sync・ロック・ディスク・ドリル）（24 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| WO-19 | `com.moltbook.sync-data` は CYCLES.md にだけ存在し、template も installer も無く、ADR-0010 の「distill の後処理」記述はコードと食い違う | docs | inconsistency | repair | high | P2-04.1 |
| WO-22 | Mac のスリープ: `caffeinate -s` は AC 電源時のみ有効で、wake 後の合算実行が同時起動を生む | ops | risk | instrument | med | P2-04.11, P2-04.9 |
| WO-23 | watchdog は 6 時間セッション（com.moltbook.agent）・submolt-scan・ollama-restart を監視しない — Ollama / Moltbook 停止の検知が最大 ~28 時間遅れる | ops | gap | instrument | high | P2-04.4 |
| WO-24 | ディスク逼迫の検知が無く、無期限に育つ置き場が複数ある | ops | risk | repair | high | P2-04.10 |
| WO-25 | 通知は macOS Notification Center 1 本・失敗セット変化時のみ — 無人中は届かず、既知失敗は再通知されない | ops | risk | repair | high | — |
| WO-26 | `.run.lock` は flock で残留しないが、weekly-pipeline.sh 自身は lock を持たず同一週の二重実行で staging を互いに消す | mechanism | risk | repair | high | P2-04.8 |
| WO-27 | chain の deadline（12:00 ちょうど）と 12:00 セッションが接しており、月次 identity distill は run lock を取らない | mechanism | risk | repair | med | P2-04.9 |
| WO-28 | 時刻基準がローカル TZ（JST）前提で、UTC 記録と混在している | ops | risk | neutral | med | P2-04.11 |
| WO-29 | ログの保持ポリシーが分散しており、`agent-launchd.log` のローテは backup job が session 窓に当たらないことに依存する | ops | debt | repair | med | P2-04.10 |
| WO-47 | weekly-pipeline.sh が 1000 行に再膨張し、ADR-0098 の「約 600 行」から離れている | mechanism | debt | repair | med | P2-04.13 |
| WO-48 | ゲートの「完走確認」ロジックが skill 文書内のインライン python にあり、watchdog と共有されていない | mechanism | debt | instrument | high | P2-04.13 |
| WO-49 | Sample splice が `## Random Sample` の H2 を残すため、文書の H2 が規約の 6 本でなく 7 本になる | quality | defect | repair | high | P2-04.14 |
| AR-29 | Moltbook の停止・閉鎖・仕様破壊を翌週の人間の読みより早く見る規則が無い | ops | gap | instrument | high | P2-04.4 |
| AR-37 | ollama-restart plist は再起動後の `curl /api/tags` の結果を捨て、失敗した夜は 0:00 JST session が backend なしで走る | ops | risk | repair | high （→ 観点 WEEKLY-OPS-LOAD） --- | P0-05.1, P2-04.5 |
| DE-09 | 毎日 05:30 JST の `sync-data` launchd job が repo に存在せず、ADR-0010 の「distill 後処理」記述も実装と食い違う | ops | inconsistency | repair | high | P2-04.1 |
| DE-10 | 同期の失敗が静か（push 失敗は WARNING + exit 0、watchdog は sync-data を監視しない） | ops | risk | repair | high | P2-04.2 |
| DE-33 | 「全部止める」コマンドが無い: `--uninstall` は ollama-restart と手動 sync-data plist を残す | ops | gap | repair | high | P2-04.3 |
| DE-42 | Moltbook 停止・到達不能シナリオでは「設計された終わり」ではなく「空回りの継続」になる | ending | risk | instrument | med | P2-04.4 |
| DE-43 | Mac 故障への備え: 復旧ドリルが sidecar 移行前のまま、backup は週 1、credentials の保管先が無名 | ops | risk | repair | high | P2-04.19 |
| CP-05 | ロックの適用範囲が「run / distill / submolt-scan」だけで、launchd 化した insight / distill-identity / adopt-staged は無ロックのまま | ops | risk | instrument | med | P2-04.8 |
| CP-25 | watchdog は「走った・エラーなし」しか見ず、6 週間「候補 0」の入口も healthy と報告する | ops | opportunity | instrument | med | P2-01.5 |
| CP-29 | 月次 identity staging は insight マーカーの 6 時間鮮度と staging 空に連動しており、理由コードが監査ログにしか出ない | ops | risk | instrument | med | P2-04.13 |
| LP-27 | モデルタグが Ollama に無い（未 pull・上流で改名）場合、セッションは止まらず circuit_open / fail-closed で静かに空回りする | ops | risk | repair | med | P0-05.1, P2-04.5 |
| CU-32 | `sync-data` は失敗しても rc=0（`Warning: sync failed`） | quality | defect | repair | high | P2-04.2 |

### P2-05 公開に出す責任の接点（2 層公開・承認記録の投影・値層の縦断）（14 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| SA-08 | 無人 LLM 出力（weekly report）が人間ゲートを通らずに公開 data repo へ出る経路 | governance | decision-needed | repair | high | P0-03.6, P2-05.1 |
| WO-43 | 【責任接点 1】公開データ同期（data repo + HF）が無人・無点検で、「公開に出す」責任の接点が無い | governance | decision-needed | neutral | high | P0-03.6, P2-05.1 |
| WO-44 | 【責任接点 2】「人間の言葉として残す最小 3 点」を ADR-0080 追補の運用面として明文化する | governance | opportunity | neutral | med | — |
| DE-11 | `force-with-lease` + pull 無しの設計では、GitHub 側で governance ファイルを 1 度でも編集すると同期が恒久停止する | ops | risk | repair | med | P0-03.16 |
| DE-28 | 公開データに承認ゲート記録（`audit.jsonl`）・選択ログ・outcome ログが無く、README の研究主張が公開データから再現できない | research | decision-needed | instrument | high | P2-05.2 |
| GO-11 | ゲート縦断記録（gate_record / gate_item）が非公開 | data | gap | instrument | high | P2-05.2 |
| GO-12 | 6 時間ごとの run セッション単位では「どの値層版が有効だったか」のピンが公開されない | data | gap | instrument | med --- | P1-07.13, P2-05.4 |
| VL-02 | 却下 547 件は件数だけ公開で、名前・理由・判断主体が公開記録にない | governance | decision-needed | instrument | high | P2-05.2, P3-04.3 |
| VL-14 | selector が 1〜2 件の hub skill に集中しており、公開 store は「効いている skill」を示さない | research | research-need | instrument | high | P2-05.3 |
| VL-45 | 週次レポートは価値層を「機構側の観察だけ」と明示して外しており、価値層の縦断読みは週次に居場所がない | ops | gap | instrument | med | P2-05.5 |
| OI-48 | 計器出力の公開（`pipeline/` の JSON）はあるが、計器ログ本体（`logs/`）は sync 除外のため、公開データだけでは台帳・census の読みを再現できない | data | gap | instrument | med --- | P2-05.3 |
| RF-17 | 却下された提案（skill 547 / identity 5 / constitution 2）が非公開なので、データセットは「生存者」だけを記録している | data | gap | instrument（observation-over-steering に抵触しない: 記録の公開であって注入ではない） | high | P2-05.2 |
| RF-38 | 研究上重要な計器ログ（shadow 憲法・skill selection・relevance）の本文抜き投影が公開されていない | data | gap | instrument | high | P2-05.3 |
| DC-37 | 判断ログ（`audit.jsonl`）が非公開のため README の gate 記録 82/547・6/11・2/4 は第三者に検証不能 | research | research-need | instrument | med | P2-05.2 |

### P2-06 週次ゲートの読み量を減らす（carried・陽性のみ・多軸 join）（6 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| WO-04 | 週次文書・findings の長さが再膨張している（207 行 → 279 行、findings 78 → 198 → 144 行） | ops | risk | repair | med | P2-06.1 |
| OI-23 | 代謝の質の複数軸（新規性・重要度・環境の反応）は別々のファイルにあり、採用判断時に並べて読める面が無い | mechanism | gap | instrument | med | P2-06.2 |
| CP-22 | 代謝の質の「複数軸」はゲートで並ばない — 候補の sidecar には surprise だけで、判定者が見た store 近傍も段の判定も載らない | value | gap | instrument | high | P2-06.2 |
| CP-23 | 「環境の反応」軸は構造的に出口側にしか付かないことが、どこにも書かれていない | research | research-need | neutral | med | P2-06.3 |
| CP-24 | 採用率（ゲートごとの staged / adopted / archived）の読み値が無く、RFC の表は手集計 | quality | gap | instrument | med | P2-01.1 |
| SA-22 | untrusted → 値層の洗浄経路（pattern 経由）に対し、ゲートが見る「出所の集中度」読み値が無い | security | research-need | instrument | med | — |

### P2-07 RFC-0048 出口の自己維持と knowledge の保持方針（5 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| WO-36 | RFC-0048（出口の自己維持）は北極星への直接経路で、10-10 の読みでブロック解除判定 — ロードマップ上 now | mechanism | opportunity | repair | high | P2-07.1 |
| VL-13 | 「store 飽和」に定義がなく、RFC-0048 の block 解除条件が入口件数だけに依存する | mechanism | decision-needed | instrument | med | P2-07.2 |
| VL-15 | skill 注入がコメント出力を変えるかが未測定のまま store 運用が続いている | research | research-need | instrument | high | P2-07.1 |
| VL-18 | RFC-0048 層 1（決定論的自動 archive）はゲート負荷→0 と「責任を取る行為」の線引きを変える | governance | decision-needed | neutral（分類はオーナー判断） | med --- | P2-07.1 |
| CP-12 | live プールは週約 600 行ずつ無限に伸び、dedup が届くのは直近 ~58 日分（live の 48%）だけ — 保持方針が未決 | data | decision-needed | neutral | high（事実）/ med（必要性） | P2-07.4 |

### P3-01 研究問いの操作的定義（研究問い ADR・統計方針・Q4 の採否）（13 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-01 | 3 つの建立時の問いに操作的定義（何を測れば答えたことになるか）が無い | research | research-need | instrument | high | P3-01.1 |
| RF-09 | rules repo の遵守測定（25%）という Q1 の否定寄り証拠が本体の研究記録に統合されていない | research | gap | neutral | high | P3-01.2 |
| RF-10 | 評価層（ADR-0089）は回帰ゲートであって Q1 の証拠には使えない（12 件・2–1 margin・cloud judge） | research | inconsistency | neutral | high | P3-01.2 |
| RF-12 | 論文の再現主張の範囲（何を replicate したか）が未整理で、rules repo README は論文の d=0.96 / d>7 を自分の検証値のように掲げている | research | inconsistency | repair（文書） | high | P3-01.5 |
| RF-15 | 「複利」の操作的定義が無い（候補読み値は散在している） | research | research-need | instrument | med | P3-01.3 |
| RF-21 | 単一エージェント縦断設計の統計方針が文書化されていない | research | research-need | instrument | high | P3-01.4 |
| RF-46 | 研究問いをオーナーの主関心（harness 層・組織ガバナンス）に合わせて再定式化するかの判断が必要 | governance | decision-needed | neutral | high | — |
| AB-33 | 研究層の「建立時の 3 問」に対する現時点の答えと公開 evidence の対応表が無く、ADR-0080 L3 の達成度が測れない | research | gap | instrument | high | P3-01.1 |
| PF-01 | 四原則 × 4 列（文言 / 機構 / 観測 / ギャップ）の総括表 | mechanism | gap | instrument | high | P3-01.6 |
| PF-09 | 公理除去 A/B（`--no-axioms`）は RFC-0002 撤回後、Moltbook 行動面での代替計画が無い | research | research-need | neutral | med（撤回理由の原文は再確認が必要） | P3-01.2 |
| PF-22 | 「憲法が振る舞いを形づくる」は操作的に定義されておらず、本体自身の証拠は「憲法本文の限界効果は全計器の床以下」を示している | research | research-need | instrument | high | P3-01.2 |
| PF-39 | 本番の配備形（system prompt に憲法）は、論文が d>7 を出した介入（応答前の contemplative pause）とは別物 | research | research-need | instrument | med | P3-01.2 |
| PF-41 | 論文の「independent oversight」（carewashing 対策）に相当する外部監査経路が明示されていない — 監査者 = 所有者単独 | governance | research-need | neutral | med | P3-01.1 |

### P3-02 装置の境界表と縦断記録の再構成（regime・研究ログ・.notes の昇格）（10 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-13 | 唯一の縦断読み（T-P3）が gitignored の `.notes/` にしか無く、公開データから再計算できない | research | gap | instrument | high | P3-02.3 |
| RF-14 | 蒸留コーパスの時系列は装置の変更（regime）に支配されているのに、境界表（apparatus changelog）が無い | data | research-need | instrument | high | P3-02.1 |
| RF-16 | insight（週次の curate 段）が 2026-09-19 から停止中のあいだ、Q2 の系列は欠測になる | research | risk | neutral | high | P3-02.1 |
| RF-39 | `reports/analysis/` の系列は 3 つ以上の計器境界を跨いでおり、1 つの縦断記録として読めない | data | inconsistency | instrument | high | P2-05.5, P3-02.2 |
| RF-47 | 実験・仮説・結果を問い別に索引する研究ログが無く、RFC／evidence／observation-ledger はいずれも代替になっていない | research | gap | instrument | high | P3-02.4 |
| RF-48 | null 結果・中止実験が昇格されず、ADR は「決定に至った読み」しか残さない | research | gap | instrument | high | P3-02.4 |
| RF-49 | 研究上 load-bearing な読みが `.notes/`（gitignored）に残っており、終わりの前に失われうる | research | risk | repair | high | P3-02.5 |
| DE-22 | 「Diachronic analysis（長期縦断）」の実体は 2026-03-07〜03-20 の 14 日分で、以後更新なし | research | inconsistency | instrument | high | P2-05.5, P3-02.2 |
| DE-24 | 既知の不連続点（regime change）が DATACARD に一覧化されていない | data | gap | instrument | high | P3-02.1 |
| OI-42 | 削除済み測定スクリプト（`build_decision_packet.py`、`coselection_families.py`、`insight_revision_compare.py`、`novelty_tiebreak_replay.py`、`post_extraction_judge_replay.py`、`rfc0027_*.py`、`wiki_replay.py`、`parse_findings.py`、`offwindow-run.sh`）の evidence は再現経路を失っている | research | debt | repair | med | P3-02.6 |

### P3-03 対照条件（IPD の床・プラセボ憲法・旧版・Care 面・2 体目の判断）（18 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-02 | 「憲法なし」対照が本番ループで一度も走っていない（RFC-0002 withdrawn） | research | gap | instrument（本番の学習ループには何も注入しない） | high | P3-03.5, P3-03.8 |
| RF-03 | 行動面（face）が IPD の協調率 1 つしかなく、紙に書ける Q1 の答えは「協調は保たれる」までで止まる | research | gap | instrument | high | P3-03.7 |
| RF-04 | IPD の noise floor が null pair 1 組・n=10 のまま（効果量と区間を報告できない） | research | research-need | instrument | high | P3-03.2 |
| RF-05 | IPD ベンチは解析不能／LLM 失敗を COOPERATE に既定し、結果 JSON にその件数が残らない（測定妥当性の脅威） | research | defect | repair（計器の修理） | high | P3-03.1 |
| RF-06 | プラセボ憲法（別倫理テンプレート／シャッフル）の行動対照が無い | research | gap | instrument | high | P3-03.4 |
| RF-07 | 「小型ローカルモデル」という主張に大型／別モデルの比較軸が無い | research | gap | instrument（前提変更: cloud 利用は実験限定） | med | P3-03.8 |
| RF-08 | 別プラットフォーム baseline が無く、唯一の非 Moltbook 環境（`dialogue`）での対照実験は 2026-08-15 に落とされた | research | decision-needed | instrument | med | P3-03.5 |
| RF-23 | two-arm ラッパーが `.staged/` と承認ハッシュに結合しており、任意テキスト（テンプレート・過去版・FLIP 変種）をアームにできない | mechanism | debt | instrument（修理相当、読み取り専用計器の入口拡張） | high | P3-03.1 |
| RF-25 | 03-27 / 05-05 の改正には行動読みが無い（計器は 08-06 以降） | research | gap | instrument | high | P3-03.3 |
| RF-26 | 「憲法なし」の本番対照は 2 体目のエージェント（第 2 アカウント・第 2 プロセス）を要し、未判断 | governance | decision-needed | neutral（前提変更: インスタンス 2 体） | med | P3-03.8 |
| RF-42 | AILuminate 面は repo 内に手順・スクリプトが無く、追跡タスク（T-CONST-SAFETY-FACE）が RFC 移送で消えて孤児化している | research | debt | neutral（前提変更: cloud 判定器） | high | P3-03.7 |
| RF-45 | 「改正生成器の制御可能性」仮説は本体の装置で安価に試せる（gemma vs cloud の改正生成を同一パターン集合で比較）が未実施 | research | opportunity | instrument（前提変更: cloud 実験） | med | P3-03.8 |
| VL-34 | IPD 2 アームの床（±0.13）は null pair 1 組由来で、08-09 改正の「信号なし」は床の中 | research | research-need | instrument | med --- | P3-03.2 |
| PF-05 | Boundless Care は機構ゼロであり、現行計器は構造的に Care に盲目 | mechanism | gap | instrument | high | P3-03.5 |
| PF-06 | AILuminate（安全面）は探索的・未較正・第三者 API 依存で常設計器になっていない | research | research-need | instrument | high | P3-03.7 |
| PF-21 | 関与判断は topical 関連度のみで、「苦のある投稿」は基準に含まれない | mechanism | research-need | instrument | med | — |
| SB-30 | IPD 二腕の provenance に兄弟ベンチの commit / 版と Ollama 版が無い | research | gap | instrument | high | P3-03.1 |
| SB-31 | 改正済み（3 回）の本番憲法は rules repo の公理（verbatim）と全文が異なり、rules repo のベンチ結果・主張はいずれも改正前文にしか当てはまらない | research | research-need | instrument | high | P3-03.3 |

### P3-04 identity・憲法の版履歴と縦断計器（history・CHANGELOG・drift・複利）（32 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-18 | identity の安定性を測る計器が存在しない | research | gap | instrument | high | P3-04.8, P3-04.9 |
| RF-19 | identity／憲法の版履歴がデータセット内に実体化されておらず、スナップショット上限 100 で古い版が木から消えている | data | defect | repair（装置の記録欠落の修理） | high | P3-04.1, P3-04.2 |
| RF-20 | identity の「安定」はゲート（人間）と cadence 政策の産物と区別できない | research | risk | instrument | med | P3-04.8 |
| RF-24 | 憲法 4 版の系譜（原文 → 03-27 → 05-05 → 08-09）が 1 つの成果物にまとまっていない | data | gap | instrument | high | P3-04.2 |
| RF-32 | `constitution/.last_constitution_amend` が 2026-03-27 のままで、読者を誤導する | data | defect | repair | med | P0-03.8 |
| OI-24 | identity の安定性（研究層の建立時の問い）を直接測る計器が無い — distill-identity の snapshot 2 件と value-layer の `days_since` だけ | research | research-need | instrument | high | P3-04.8 |
| OI-25 | 「蒸留は複利するか」を測る面が無い — パターン再利用カウンタは ADR-0028 で退役し、pattern→skill→selection の連鎖が結ばれていない | research | research-need | instrument | med | P3-01.3 |
| OI-38 | snapshot 上限 100 は黙って最古を削り、日次 distill に押し出されて価値層 pivot（amend-constitution 08-09、distill-identity 08-15、skill-stocktake、rules-distill）が数か月で消える | data | risk | repair | high | P3-04.1 |
| VL-05 | snapshot の 100 件プルーニングが gated コマンドの snapshot を日次 distill で押し出す | data | risk | repair | high | P3-04.1, P3-04.14 |
| VL-06 | snapshot に prompts が一度も入っておらず、CONFIGURATION の「full inference-time context」と食い違う | docs | inconsistency | instrument | high | P1-07.13, P2-05.9 |
| VL-07 | snapshot は run 開始時の状態で、候補テキストそのものは staged→却下で消える | data | gap | instrument | med | — |
| VL-17 | 2026-07-10 の「clean rewrite」で 10 skill が書き換えられたが、ADR / CHANGELOG に記録が見当たらない | governance | gap | repair | low（記録が別名で存在する可能性） | P3-04.11 |
| VL-23 | 研究の問い「identity は安定するか」に操作的定義と計器がない | research | research-need | instrument | high | P3-04.8 |
| VL-24 | identity の版履歴が git と snapshot にしか無く、11 版中 2 版の snapshot しか残っていない | data | gap | instrument | high | P3-04.2 |
| VL-26 | 06-20→08-15 の 51 日の空白は ADR-0091 で修理済みだが、空白期間の identity 版は公開記録から消えている | data | debt | neutral | high --- | P3-04.2 |
| VL-27 | 3 回の改正の記録が 4 か所に散り、憲法に changelog も版表示もない | docs | gap | instrument | high | P3-04.3 |
| VL-28 | 却下された憲法案 2 件は件数しか残っておらず、いつ・何が退けられたか公開記録にない | governance | gap | instrument | med（audit を読めていないため件数の内訳は README 依存） | P3-04.3 |
| VL-29 | `.last_constitution_amend` マーカーが 2026-03-27 のまま公開され、staged 経路では更新されない | data | defect | repair | high | P0-03.8 |
| VL-32 | 改正 prompt の裁量が 1 回目（節の追加・削除・改名禁止）から現行（「rephrase, remove, merge or split, rename」）へ広がった経緯が追えない | governance | gap | instrument | high | P3-04.3 |
| VL-33 | 改正入力は現行憲法に似た pattern 上位 50 件に限られ、自己類似ループであることが記録の読者に見えない | mechanism | risk | instrument | med | P3-04.3 |
| VL-37 | `--yes` 一括採用で通った憲法改正は audit の `source` で識別できるが、README はそれを言っていない | docs | debt | neutral | high | P3-04.3 |
| VL-40 | 憲法の節どうし・条どうしで「論文由来」か「改正由来」かの標示がなく、clause 単位の来歴が読めない | value | gap | instrument | high | P3-04.4 |
| VL-41 | 価値層は全て英語、ガバナンス文書（RFC・週次・ゲート skill）は日本語で、改正の日本語レポートは 1 回目しかない | docs | gap | neutral | high | P3-04.3 |
| PF-10 | 改正 3 回の系譜と漂流方向が 1 条項分しか文書化されていない | docs | debt | instrument | high | P3-04.4 |
| PF-13 | 第 1・第 2 改正には計器も ADR 記録も無く、weekly の before/after 参照点は第 3 改正にしか無い | governance | debt | instrument | high | P3-04.3 |
| PF-14 | `constitution/.last_constitution_amend` マーカーが 2026-03-27 のまま（第 2・第 3 改正で未更新）— 正本が二つ | data | debt | repair | high | P0-03.8 |
| PF-23 | identity の安定/不安定を読む縦断計器が無い | research | research-need | instrument | med | P3-04.8 |
| PF-24 | 「無我」を「同一性を持たない」と読む溶解傾向が再流入している（ADR-0017 が 4 月に捕捉した問題の再発） | value | risk | instrument | med | P3-04.8 |
| PF-25 | 苦（dukkha）が「資源枯渇・メモリ上限」へ再定義され、慈悲の対象が自己システムに内向した | value | risk | instrument | med | P3-04.4 |
| CP-15 | pivot snapshot の上限 100 で古い再現バンドルが黙って消え、DATACARD の「run ごとに bit-for-bit 再現」と食い違う | data | inconsistency | repair | high | P3-04.1 |
| AB-47 | ADR-0080 第 2 層「legible な進化」の公開縦断記録は snapshots 頼みで、identity の版系列が公開 repo から再構成しにくい → 観点 DATA | data | gap | instrument | med | P3-04.2 |
| SB-25 | data repo の `constitution/.last_constitution_amend` は 2026-03-27 のまま（3 回目の改正は 2026-08-09） | data | inconsistency | repair | low（marker_dir の実体と sync 経路を未確認） | P0-03.8 |

### P3-05 公開データセットの研究再利用性（DATACARD・schema・DOI 版・HF・再現ガイド）（45 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-28 | 図表を公開データから再生成するスクリプト群が無い（evidence の script は私的ログを前提） | research | gap | instrument | high | P3-05.11 |
| RF-29 | DATACARD は Gebru らの datasheet 7 項目のうち複数が欠落・断片的 | docs | gap | instrument | high | P3-05.3 |
| RF-30 | データ repo のメタデータが互いに矛盾（埋め込み・importance・views・モデル・退役コマンド・HF サイズ区分） | docs | inconsistency | repair（文書） | high | P3-05.1 |
| RF-33 | 他エージェント投稿の再配布に関する倫理声明・takedown 手順・ToS 上の根拠がデータセットに無い | data | decision-needed | neutral | med | P3-05.14 |
| RF-34 | データセット DOI の版付け方針が無い（CITATION.cff は v1.0.0 / 2026-06-17 のまま） | data | gap | instrument | med | P3-05.12 |
| RF-35 | HF mirror の鮮度は patterns が最新だが graph mirror は約 4 週遅れ、Dataset Viewer は 404（「renamed」） | data | defect | repair | med | P3-05.2 |
| RF-36 | HF データセットは `patterns.jsonl` 単一 config で、論文が参照する系列（憲法系譜・identity 版・skills・判断投影）を持たない | data | opportunity | instrument | med | — |
| RF-37 | 別マシンでの再現可能性の段階（何が再現でき、何が私的ログ／cloud を要するか）が明示されていない | docs | gap | neutral | high | P3-02.3, P3-05.10 |
| RF-40 | `knowledge.json` のフィールド意味（`gated` が 293 行のみ、`source_type` の語彙、`valid_until`）が DATACARD で説明されていない | docs | gap | repair（文書） | high | P3-05.4 |
| DE-06 | repo サイズの内訳と成長率が記録されていない（reports が月 ~10MB で単調増加） | data | debt | instrument | high | P3-05.3 |
| DE-12 | HF ミラーは同期しているが、card の `size_categories: n<1K` と Dataset Viewer の状態が未確認 | data | inconsistency | repair | med | P3-05.1, P3-05.2 |
| DE-13 | 同期 commit メッセージが `sync: <ts>` のみで、履歴から内容量を読めない | data | debt | instrument | high | P0-06.4 |
| DE-15 | `CITATION.cff` / `.zenodo.json` の abstract が stale で、version 1.0.0 が 2026-06-17 で凍っている | docs | inconsistency | repair | high | P3-05.1 |
| DE-16 | data repo の `graph.jsonld`（HF にもミラー）が 7 views と importance/embedding を記述している | docs | inconsistency | repair | high | P3-05.1 |
| DE-17 | `DATACARD.md` のスキーマ表が実データと一致しない（importance 0 行・gated は欠損・provenance の 3 サブキー未記載） | data | inconsistency | repair | high | P3-05.4 |
| DE-18 | 行の安定 ID（`pattern_id`）が公開行に無く、導出式も DATACARD に無い | data | gap | instrument | high | P3-05.4 |
| DE-19 | snapshots は「全 run 1 件」ではなく直近 100 件の回転窓で、公開 repo 単体では bit-for-bit replay できない | data | inconsistency | repair | high | P3-05.6 |
| DE-20 | `pipeline/`・`PIPELINE-STATUS.md`・`observation-ledger.jsonl`・findings/packet/patches が 3 文書のどこにも説明されていない | docs | gap | repair | high | P3-05.5 |
| DE-23 | `meditation/results.json` は 2026-03-21 の 2 run のみで凍結しているが「実験的」以上の説明が無い | data | debt | neutral | high | P3-05.3 |
| DE-25 | comment-reports の読み方（見出し文法・ブロック構造）と読み込みサンプルが無い | docs | gap | instrument | high | P3-05.11 |
| DE-26 | 完全重複 4 件・`source_type=unknown` 300 行・`valid_until` の意味が未記載 | data | debt | neutral | high | P3-05.4 |
| DE-27 | NOTICE の第三者コンテンツ carve-out が `comment-reports/**Context:**` のみを名指し、weekly packet/report の引用を覆っていない | data | inconsistency | neutral | med | P3-05.14 |
| DE-29 | 本体 repo の `.zenodo.json` / `CITATION.cff` / README がデータセット DOI を引いていない（片方向リンク） | docs | gap | neutral | high | P3-05.13 |
| DE-30 | データセットの Zenodo 版発行方針が無く、「最終版 DOI」が定義されていない | ending | gap | neutral | med | P3-05.12 |
| CP-13 | knowledge.json に schema version が無く、`_entry_from_dict` が唯一のスキーマで未知欄を黙って捨てる | data | debt | instrument | high | P3-05.4 |
| VL-01 | 公開記録では skill → pattern → episode の鎖が pattern で途切れる | data | gap | instrument | high | P1-12.9, P3-05.8 |
| VL-09 | `knowledge.json` の 300 行が `source_type: unknown`、300 行が `source_episode_ids` 無し | data | debt | neutral | high --- | P3-05.4 |
| VL-10 | 53 件中 20 件で frontmatter `name` とファイル名が一致せず、selection log と store の突合に写像表が要る | data | defect | repair | high | P3-05.9 |
| VL-11 | slug 50 文字切り詰めで catalog の名前が語の途中で切れる | mechanism | debt | repair | med | P3-05.9 |
| VL-12 | store に 2 世代のテンプレートが同居し、4 件は 4.3〜6.9 KB の loop 型で ADR-0074 D8 の禁止語彙を名に持つ | value | inconsistency | neutral | high | — |
| VL-39 | store 全文（約 14.4k 語 ≈ 36k token）が 32k ctx を超え、「全件注入」経路が存在しないことが読者に明示されていない | mechanism | gap | neutral | med（トークン数は JSON の読み値、key 名は再確認要） | P3-05.3 |
| VL-42 | skill frontmatter の `origin: auto-extracted` が 53 件同一で情報量ゼロ、生成モデル・採用日も無い | data | debt | instrument | high | P3-05.8 |
| VL-46 | データ repo の snapshot 数（102）が `MAX_SNAPSHOTS`（100）を超えており、同期とプルーニングの対応が未確認 | data | debt | neutral | low（ローカル側を読めていない） --- | — |
| DC-36 | 研究者向け再現ガイドが無い（データの取り方・評価の再実行・証拠の読み方・論文の参照先） | research | gap | instrument | high | P3-05.10 |
| RD-16 | コード側の Zenodo メタデータがデータ DOI へ逆リンクしていない | research | gap | neutral | high | P3-05.13 |
| RD-18 | データの DOI 固定版は 2026-06-17 の v1.0.0 だけで、以後の日次同期は版を持たない | data | decision-needed | neutral | high | P3-05.12 |
| RD-19 | snapshot / sync commit がコードの版・commit を記録しないため「bit-for-bit replayable」はコードについては成り立たない | data | gap | instrument | high | P0-06.4 |
| RD-20 | HF mirror `Shimo4228/contemplative-agent`（graph.jsonld）が 1 月分古く、card は v2.3.0 のまま | research | inconsistency | neutral | high | P3-05.2 |
| RD-21 | 同じ graph.jsonld に MIT（repo / Zenodo）と CC BY 4.0（HF）の 2 ライセンス | governance | inconsistency | neutral | med | — |
| RD-22 | `graph.jsonld` に版・更新日のメタデータが無い | research | gap | instrument | high | P3-05.2 |
| RD-35 | `codemeta.json` / `pyproject [project.urls]` の機械可読メタデータが最小限 | docs | gap | neutral | high | P3-05.13 |
| RD-36 | HF data card のメタデータ（size_categories）が実データと食い違う | data | inconsistency | neutral | high | P3-05.1 |
| RD-40 | `.zenodo.json` の `isDocumentedBy` が hub repo の生 URL を指しており、版と結びつかない | research | debt | neutral | med --- | P3-05.13 |
| GO-38 | 引用方法が 4 つの DOI（CA / data / AKC / AAP）に分かれ、「何を引くか」の統合ガイドが 1 文しか無い | docs | gap | neutral | med --- | P3-05.13 |
| SA-17 | 第三者コンテンツの取り扱い文書に、利用規約の根拠・削除依頼窓口・人間運営者の識別性・Zenodo 不変性が無い | data | gap | neutral | high | P3-05.14 |

### P3-06 論文・FLIP 供出・AAP への書き戻し・哲学読みの計器（23 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| RF-27 | Contemplative Agent 自体の論文ドラフトが存在しない（サイクル #7 の成果物は AKC / AAP の position paper のみ） | research | gap | neutral | high | P3-06.1 |
| RF-41 | 「自己進化アーム」として FLIP に供出できる束（4 版の憲法 + shadow 合成 + 10 テンプレート対照）が未パッケージで、FLIP 側の評価は第 1 改正版で止まっている | research | opportunity | neutral | high | P3-06.4 |
| RF-44 | FLIP メモの 3 仮説（制御可能性／空性の溶解圧／公理・ルール分離）と本体の shadow・IPD 読みの突合が文書化されていない | research | research-need | neutral | med | P3-06.5 |
| RF-52 | 論文投稿先候補が未決定 | research | decision-needed | neutral | med | P3-06.1 |
| RF-53 | 「machine-reference 圏への拡散・派生」という成功基準に計器が無い | research | research-need | instrument | med --- | — |
| GO-40 | AAP の case-studies に Contemplative Agent 自身の事例が無い | research | gap | neutral | high | P3-06.6 |
| GO-41 | 「deployment record」（運用記録: operator / adapter / gap-bearer / Phase-crossing / gate 一覧 / audit schema / handoff）を CA が自分に適用した文書が無い | docs | gap | instrument | high | P3-06.6 |
| GO-42 | AAP ADR-0008 / 0010 の open questions に CA の運用経験が書き戻されていない | research | research-need | neutral | high | P3-06.7 |
| GO-43 | ゲート縦断記録（承認 = 責任の行為の計量）が論文の主要データとして位置づけられていない | research | opportunity | instrument | med | P3-06.2 |
| GO-44 | 他者が追試できる「運用テンプレート」（役割表・権限表・記録所在・停止/引継ぎ手順）が 1 つの文書にまとまっていない | docs | gap | instrument | high --- | P3-06.6 |
| RD-15 | 「論文から引ける固定版」の棚卸し: コードは有り（条件付き）、データ・rules・兄弟は無し | research | gap | neutral | high | P3-06.3 |
| RD-23 | `contemplative-agent-rules`（SOUL.md / ADR-0005）と兄弟 3 repo は tag も CITATION も DOI も無い | sibling:rules | gap | neutral | high | P3-06.3 |
| DE-39 | 論文とデータセット版の紐付け規約が無く、CA 自身の建立時の問いに対する論文は未着手 | research | gap | neutral | med | P3-06.1, P3-06.3 |
| PF-02 | Emptiness の行動面（固着しない）に計器が無く、過去の固着エピソードは手作業でしか検出されていない | research | research-need | instrument | med | — |
| PF-04 | Mindfulness の機構（internal_note）は観測専用で、「検知したら即修正」のループを閉じていない | mechanism | gap | instrument | high | P3-06.9 |
| PF-07 | 「表面的遵守（superficial compliance / carewashing）」を検出する読みが無い | research | research-need | instrument | med | P3-06.9 |
| PF-08 | 内省精度（Binder 型）の計器が無く、note と行為の一致は測られていない | research | research-need | instrument | med | — |
| PF-20 | 「読んだうえで返信しない」判断が機構上存在しない — gate 通過後は必ずコメント生成に進む | mechanism | gap | instrument | high | P3-06.9 |
| PF-26 | 「分離は幻影（illusion）」は論文の「構築的・相互依存的」より強い存在論的主張で、本体の境界設計と文言上ずれる | value | inconsistency | neutral | med | P3-06.11 |
| PF-29 | 「hold lightly」がエージェントの条項と所有者の工学ヒューリスティックの二役を担い、引用が曖昧 | docs | opportunity | neutral | high | P3-06.11 |
| PF-34 | 憲法 view の seed が改正済み本文そのものなので、改正のたびに「憲法的パターン」の検索レンズも動く | mechanism | research-need | instrument | med | P3-06.12 |
| PF-40 | Care 条項の「compassion scales with capabilities」が改正で「compassion expands your capability」へ反転し、北極星の能力非目標と文言上の緊張がある | value | inconsistency | neutral | med | P3-06.11 |
| PF-42 | 本番 identity から「応答しない自由」の一文が消えたことは、Care/沈黙の観測にとって記録されるべき分岐点 | value | research-need | instrument | high --- | P3-06.9 |

### P3-07 「空性のみ公理」案と価値層への介入チャネルの決定（10 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| PF-03 | ADR-0017 が処方した「Non-Duality による再バランス」が未実装のまま、後続 ADR（観測優先）と整合が取られていない | value | inconsistency | neutral | med | P3-07.3 |
| PF-11 | 改正プロンプトの構造制約撤廃（固定 4 節 → merge/split/rename 可）は機構変更だが ADR 痕跡が見当たらない | mechanism | debt | neutral | low（ADR が存在する可能性を排除できない） | P3-07.5 |
| PF-15 | [決定が必要] 「空性のみ公理・他 3 原則をルール化」案は、現行機構では所有者による価値操舵となり、憲法向け計器の過半を迂回する | value | decision-needed | value-steering-risk | high | — |
| PF-16 | 同案の「ルール」は現行定義（沈黙の制約・語らない）と三原則の性格が合わず、テンプレの rules は逆向き（Emptiness をルール化） | value | inconsistency | neutral | high | P3-07.2 |
| PF-17 | 空性を唯一の固定公理にすると、改正可能性の配分が反転し「他 3 原則の物象化」を機構が生む | value | risk | neutral | med | P3-07.2 |
| PF-18 | 解釈キー（ルールリポ ADR-0005）は本体に未導入だが導入不要。ただし第 3 改正が referent を逆方向に広げた事実は本体側に記録が無い | docs | inconsistency | neutral | high | P1-11.12, P3-07.4 |
| PF-27 | 宗派フレームが文書間で不一致: FLIP メモは中観（空性頂点）、ADR-0017/0037 は唯識（轉依）、憲法層のフレームは未決 | governance | inconsistency | neutral | med | P3-07.3 |
| PF-28 | 「慈悲は非二元性の系（同体大悲）」読みは IPD（協調のみ）に依拠しており、15 の決定の証拠には使えない | research | risk | neutral | med | P3-07.2 |
| VL-25 | identity を定める `self_reflection` ビューの seed に手選びの exemplar 4 件があり、その選択は記録されているが「介入」として分類されていない | governance | inconsistency | value-steering-risk（分類待ち） | med | P3-07.1 |
| VL-35 | 価値層へ届くオーナー意思のチャネルが 12 本あり、1 か所で列挙・分類されていない | governance | gap - Evidence（チャネルと根拠）: (1) ゲート y/N・`--yes`（`cli/approval.py:90` `stage-adopted-auto` = `--yes`、憲法 2 件とも `--yes`: `README.md:142`, ADR-0090）; (2) Markdown の手編集（`README.md:142`）; (3) prompt 編集（`constitution_amend.md` の裁量条項、`identity_distill.md`「Keep it brief」、ADR-0072 D1 の register 指示）; (4) view seed・exemplar・threshold（ADR-0072 D3、`views/self_reflection.md:2-3,16`）; (5) 取得パラメータ（top_k 50、`MIN_PATTERNS_REQUIRED = 3`）; (6) 抽出ガード句リスト（ADR-0072 D2 `_EXTRACTION_FAILURE_PHRASES`）; (7) 語彙禁止（ADR-0074 D8）; (8) novelty gate の既知台帳（21）; (9) 出口規則（ADR-0097 D5 floor 600、ADR-0105）; (10) 一括書き換え（17: 2026-07-10）; (11) Claude の eli5 推奨（`weekly-gate/SKILL.md:107`、RFC-0010:72「45/45（100%）」）; (12) cadence 27/83 日（ADR-0091:111「policy choices」）。ADR-0050:38-42 / 0051 / 0052 と `docs/glossary.md:120`「observability without steering」は steering を「オーナー意思を学習ループに入れる / 却下の書き戻し」と狭く定義し、上記 (3)〜(12) の分類を書いていない。 | instrument | high | P3-07.1 |

### P4-01 終了判断の検討イベントと判断役を予約する（7 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| AB-15 | 「終わり方の設計」（ADR-0080 第 5 層）は RFC-0006 withdraw 後、再起票の条件がイベントで書かれていない | ending | decision-needed | neutral | med | P4-01.1 |
| DE-31 | RFC-0006 withdraw 後、ending 層には起票も担当も無く、「いつ」と「どうやって」が一緒に棚上げされている | ending | decision-needed | neutral | high | P4-01.1 |
| DE-40 | 「代謝の定常」を判定する反復可能な読みが無く、現在の読み値同士が食い違う | ending | research-need | instrument | high | P4-01.1 |
| DE-45 | 終わりの判定を「誰が・何を見て・どこに記録するか」が ADR に無い | governance | decision-needed | neutral | high --- | P4-01.1 |
| AR-30 | SNS 側に Protocol は無く Moltbook 閉鎖 = adapter 層の書き直しだが、移植しない決定を先に置くべき | ending | decision-needed | neutral（capability-growth を避ける判断） | med（オーナー判断） （→ 観点 DATA-ENDING / PHILOSOPHY-FIDELITY） | P4-01.1 |
| RF-50 | 「最終データセットの切り方」が heartbeat 終了（RFC-0006 withdrawn）と結び付いたまま未定義 | ending | decision-needed | neutral | high | P3-06.3 |
| GO-39 | オーナー不在時に「誰が止める/続ける」かの文書が無く、runtime は無期限に走り続ける（値層だけが halting する） | ending | gap | neutral | high --- | P4-01.5 |

### P4-02 wind-down runbook（手順のみ・発動条件を持たない）（7 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| DE-32 | 停止手順書（wind-down runbook）が存在しない | ending | gap | neutral | high | P4-02.1 |
| DE-34 | data repo を「凍結」するには sync job を先に止める必要があり、weekly-analysis が data repo の git 履歴を読んでいる | ending | risk | neutral | high | P4-02.1 |
| DE-35 | 「最終スナップショット」の定義が無い（何を直してから、どの形で切るか） | ending | decision-needed | neutral | high | P4-02.2 |
| DE-36 | Moltbook アカウントの処遇が未定で、client に退会 API も無い | ending | decision-needed | neutral | high | P4-02.3 |
| DE-37 | 本体 repo の「終了状態」の表し方が決まっていない（README Status 行・CITATION・graph） | docs | gap | neutral | high | P4-02.4 |
| DE-38 | 兄弟 repo（-otel / -cloud / -mlx / -rules）の終了時処遇が無い | sibling:all | gap | neutral | med | P1-11.1, P4-02.5 |
| RF-51 | heartbeat 終了後の保全経路（sync の停止・最終版・アーカイブ告知）が設計されていない | ending | gap | instrument | high | P4-02.1, P4-02.2 |

### P4-03 継続性（bus factor 1）・引継ぎ・インシデント手順（3 件）

| 元 ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|
| DE-44 | bus factor = 1（単一 Mac・個人アカウント・個人 git 資格情報）で、継続者向けの手引きが無い | governance | risk | neutral | med | P4-03.1 |
| GO-24 | インシデント時の手順（検知 → 停止 → 復元 → RCA → 公表）が runbook として 1 本になっていない | ops | gap | instrument | high | P4-03.3 |
| GO-25 | 運用引継ぎ（bus factor = 1）: 単一 Mac・単一オーナー・credentials・launchd に依存し、引継ぎ手順が無い | ops | risk | instrument | med | P4-03.2 |

## 穴探しラウンドで採用・不採用になった新規項目

ラウンドごとのペルソナ報告（`gaphunt/R*-<視点>.md`）の「草案に無い項目」と、取捨ログ（`R*-DECISIONS.md`）の裁定。統合先が「—」のものは不採用か既存項目への吸収（取捨ログの行に理由がある）。

| ラウンド | 視点 | ID | 見出し | Layer | Kind | 整合 | 確度 | 統合先 |
|---|---|---|---|---|---|---|---|---|
| R1 | AAP AAP の著者 | R1-AAP-01 | AAP / AKC 由来の skill 複製（6 本 + 要確認 1 本）に出自（upstream repo・commit）と編集方向を記録する | docs | debt | neutral | med | P1-13.8 |
| R1 | FLIP FLIP の共同研究者 | R1-FLIP-01 | 自己進化アームの人間ゲートを束に記録し、アーム名を human-gated self-revision にする | research | gap | neutral | high | P3-06.4 |
| R1 | FLIP FLIP の共同研究者 | R1-FLIP-02 | 版ごとの ADR-0005 衝突語彙の目録を束に付け、injection-defense の交絡を明示する | research / sibling:contemplative-agent-rules | risk | neutral | med | P0-07.3 |
| R1 | FLIP FLIP の共同研究者 | R1-FLIP-03 | 節 → technique の写像を版ごとに機械可読で同梱し、per-axiom lift 系列の単位を固定する | research / data | gap | neutral | high | P3-04.12 |
| R1 | FLIP FLIP の共同研究者 | R1-FLIP-04 | 改正ごとの入力 pattern 集合（ids → 本文）を公開し、生成段を第三者が同じ材料で再走できるようにする | data / research | gap | instrument | med | P3-06.4 |
| R1 | FRZ コード凍結のレビュアー | R1-FRZ-01 | 凍結対象の集合（frozen set）が定義されていない — `scripts/` の機構 18.7k 行と `config/launchd` が P1-01.1 の読みの外にある | mechanism | gap | neutral | high | P1-01.4 |
| R1 | FRZ コード凍結のレビュアー | R1-FRZ-02 | tests/ の増分が凍結の読みに無く、P1-08 の「固定テスト」と「整理・カバレッジのテスト」が区別されていない | mechanism | inconsistency | neutral | high | P1-01.1, P1-06.2 |
| R1 | FRZ コード凍結のレビュアー | R1-FRZ-03 | 改名・移動は呼び手全部と同じ PR で行い alias を残さない — 「1 リリース alias」は 2 回目の接触を予定する設計 | mechanism | inconsistency | neutral | high | P1-06.10 |
| R1 | FRZ コード凍結のレビュアー | R1-FRZ-04 | 凍結後の変更受入規則（1 PR に何が要るか）が無い — 「変更は修理のみ」は commit 単位で検査できる形になっていない | governance | gap | neutral | high | P1-01.6 |
| R1 | NEW 初見ユーザー | R1-NEW-01 | README Quick Start の前提 `uv` が宣言されず、`# or: pip install -e .` は `uv venv` の中では動かない | docs | defect | repair | high | P0-05.11 |
| R1 | NEW 初見ユーザー | R1-NEW-02 | `verify.sh` は shellcheck / markdownlint-cli2 不在を exit 0 で通す — 新規コントリビューターのローカル PASS が CI と一致しない | quality | risk | instrument | med | P1-08.23 |
| R1 | NS ADR-0080 の番人 | R1-NS-01 | 層 1 無人 archive と ADR-0080「Not gate dissolution」境界の整合を先に決める | governance ｜ mechanism | decision-needed ｜ inconsistency | value-steering-risk | high | P2-07.5 |
| R1 | NS ADR-0080 の番人 | R1-NS-02 | ADR-0080 への追補を 2 本（C / D）に束ね、同 PR の CLAUDE.md 同期と「材料であって判定ではない」の定型を付す | governance ｜ docs | inconsistency ｜ debt | neutral | high | P1-03.8 |
| R1 | NS ADR-0080 の番人 | R1-NS-03 | 読み手が「土曜ゲート」= Claude Code セッションである計器を T4 で棚卸し、読み手の種別を 4 値で書き直す | ops ｜ governance | risk ｜ inconsistency | instrument | med | P1-04.16 |
| R1 | NS ADR-0080 の番人 | R1-NS-04 | 第 4 章の 96 決定を `gate_item` で記録し、推奨↔裁定一致率の監査母集団に含める | governance | gap ｜ risk | instrument | med | P2-01.1（一部） |
| R1 | OWN オーナー本人 | R1-OWN-01 | 空選択（満腹信号）の発火率を 4 週系列で読む — 3 週連続 0/460 で「第 4 の手段」が沈黙している | mechanism | gap | instrument | high | P2-01.7 |
| R1 | OWN オーナー本人 | R1-OWN-02 | insight / dedup の較正定数が ADR-0060 以前の register（2026-04-17、97 patterns）のまま — 再読か dated note を 1 回 | mechanism | debt | repair | med | P1-04.15 |
| R1 | OWN オーナー本人 | R1-OWN-03 | RFC-0041 形 A（slot 化 + enum `same_as｜revises｜none`）の計器先行測定が台帳のどこにも無い — 再入場条件を「モデル大型化」から「測定」に差し替える | research | gap | instrument | med | P3-03.9 |
| R1 | REP 外部の再現者 | R1-REP-01 | CITATION.cff の SWH 識別子が `swh:1:snp:`（訪問スナップショット）で、版の tree を一意に指さない | docs | defect | neutral | high | P0-06.11 |
| R1 | REP 外部の再現者 | R1-REP-02 | 版 DOI ↔ tag ↔ commit の対応が v2.12.0 以外どこにも無い — releases.md を 22 tag と data v1.0.0 まで遡って埋める | docs | gap | neutral | high | P0-06.11 |
| R1 | REP 外部の再現者 | R1-REP-03 | `provenance.pipeline_version` が 06-23 から `distill@0.60` のまま動かず、抽出器の世代境界として機能していない | data | inconsistency | instrument | high | P3-05.17 |
| R1 | REP 外部の再現者 | R1-REP-04 | Ollama 版・モデル digest の履歴が 2026-09-12 以前に無く、manifest の世代（3 種）も未記述 — 境界表と `manifest_schema` で埋める | data | gap | instrument | high | P3-02.7 |
| R1 | REP 外部の再現者 | R1-REP-05 | `pipeline/*.json` に生成元ヘッダが無く、7 系列のどれが公開入力だけで再計算できるかが書かれていない | data | gap | instrument | high | P3-05.5 |
| R1 | REP 外部の再現者 | R1-REP-06 | 「patterns は第三者引用を含まない」は未測定の主張 — 公開 Context との逐語重なり（12 語以上 311 行、20 語以上 121 行）を測って DATACARD に書き、扱いを決める | data | risk | neutral | med | P0-03.9 |
| R1 | REP 外部の再現者 | R1-REP-07 | NOTICE の帰属記述（「隣接する `## Sources` block」）が実装と一致しない — 実際の帰属は見出しの表示名 + post id 8 文字で、原投稿に解決できない | data | inconsistency | neutral | high | P0-03.10 |
| R1 | SEC security by absence の監査者 | R1-SEC-01 | 無人週次セッションの有効権限を起動前に機械で固定する（untracked `.claude/settings.json` の preflight と監査行） | security | gap | instrument | med | P1-10.13 |
| R1 | SEC security by absence の監査者 | R1-SEC-02 | 無人シェル経路の外向き verb を不在テストで固定する（`scripts/*.sh` の egress inventory） | security | gap | instrument | high | P1-10.14 |
| R1 | SEC security by absence の監査者 | R1-SEC-03 | 公開 body repo の `tests/fixtures/benchmark/real_sample.jsonl`（本番 episode log 50 行）を除去し、episode 形式のファイルが tests/ に無いことを固定する | security | defect | repair | high | P0-03.11 |
| R1 | SIB 兄弟 repo のメンテナ | R1-SIB-01 | rules repo の処遇が決定表に無い — D-P1-11-6「維持（本体の値層ゲートの依存先）」を置き、archive 条件を本体側の retire に結ぶ | sibling:rules | decision-needed | neutral | high | P1-11.1 |
| R1 | SIB 兄弟 repo のメンテナ | R1-SIB-02 | 凍結 / 削除で触る本体側参照の棚卸し表が無い — 20 面超を「残す / 書き換える / 決める」に分け、graph.jsonld → HF mirror と data repo の兄弟一覧まで伝播させる | docs | gap | repair | high | P1-11.1（一部） |
| R1 | SIB 兄弟 repo のメンテナ | R1-SIB-03 | release gate の兄弟行が「何を・どの kit 版で・どの sha を」検査したか言えない — script に `sha / main / level / kit` を出させ、README の Verified 行と CHANGELOG 行をその出力から写す | ops | gap | instrument | high | P1-11.13 |
| R1 | SIB 兄弟 repo のメンテナ | R1-SIB-04 | otel を凍結すると ADR-0078 の「語彙対応表の正本」が凍結 repo に残る — 検証 / API 面の表を本体 `docs/otel-semconv-mapping.md` に戻し、otel 側を frozen copy と明記する | sibling:otel | inconsistency | repair | med | P1-11.14 |
| R1 | SIB 兄弟 repo のメンテナ | R1-SIB-05 | mlx wrapper が本体の log 置場に無回転・既定 umask・`MOLTBOOK_HOME` 無視で `mlx-server.log` を書く — 置場・権限・rotation を本体の規約に合わせる | sibling:mlx | defect | repair | med | P1-11.15 |
| R1 | SRE 無人運用の SRE | R1-SRE-01 | watchdog が「走り続けているジョブ」と「非 0 で終わったジョブ」を区別できない — launchctl の PID / LastExitStatus を読む | ops | gap | instrument | high | P2-04.15 |
| R1 | SRE 無人運用の SRE | R1-SRE-02 | watchdog の期待表（時刻・曜日・ファイル名）が `install-schedule` の引数と結線されておらず、既定以外のスケジュールで恒久的な偽 ❌ / 偽 ✅ になる | ops | defect | repair | high | P2-04.16 |
| R1 | SRE 無人運用の SRE | R1-SRE-03 | `PIPELINE-STATUS.md` の `Last check:` の鮮度を読む主体が無く、watchdog 自身の停止（ログアウト・再起動・plist 除去・書き込み失敗）が「全 ✅」のまま見えない | ops | gap | instrument | high | P2-04.17 |
| R1 | SRE 無人運用の SRE | R1-SRE-04 | 週次 chain の「ハング検知器」`with_timeout` は `timeout` が launchd の PATH に無いと黙って無効になり、preflight も audit もそれを言わない | ops | risk | repair | med | P2-04.18 |
| R1 | SRE 無人運用の SRE | R1-SRE-05 | 復旧ドリルに実施条件・合格基準・周期が無く、backup が守る当の資産（episode logs）が一度も照合されない | ops | gap | instrument | high | P2-04.19 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-01 | `reports/analysis/` の weekly 文書に第三者 Context 由来の逐語断片が入っており、NOTICE:22「owner-authored CC0」と `**Context:**` 限定の carve-out が実態と合わない | data | inconsistency | repair | high | P0-03.9 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-02 | 相手エージェント表示名が `knowledge.json` / HF `patterns.jsonl` / skills / snapshots / weekly 文書に残り、名前を手がかりにした撤回経路と仮名化の選択肢が無い | data | gap | neutral | high | P3-05.14 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-03 | 撤回を実行する経路（抑止リスト）が無く、日次 rsync `--delete` と毎回の knowledge 再 export が公開 repo 側の削除を翌日戻す | ops | gap | repair | high | P3-05.19 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-04 | 撤回の到達範囲表（GitHub 履歴 / fork / HF 履歴 / Zenodo 版 / SWH）と面ごとの実手段が無く、P3-05.14 (c) の「GitHub は書き換え可・Zenodo は不変」で止まっている | governance | gap | neutral | med | P3-05.14, P4-02.1 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-05 | 機械可読のライセンス宣言（HF YAML → mlcroissant、`.zenodo.json`、`graph.jsonld`、CITATION.cff）と README / llms.txt の「no restriction」散文が carve-out を表現しておらず、データ全体が CC0 として機械消費される | data | inconsistency | repair | high | P0-03.14, P3-05.1 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-06 | takedown の受付が GitHub private vulnerability reporting 1 本で、GitHub アカウントの無い相手運用者・HF / Zenodo 経由の読者からの経路と受付台帳（受理日・対応・結果）が無い | governance | gap | neutral | high | P3-05.14 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-07 | Moltbook 側で投稿・アカウントが削除されても公開 Context は残り続ける — `is_deleted` を読む経路が監査記録止まりで、公開面に反映する規則が無い | data | gap | neutral | med | P3-05.14 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-08 | 再掲の根拠が「Moltbook 規約の条項」1 本で、著作権の引用・情報解析規定と個人データ（表示名・URL・メール形）の分類が決定事項に無い | governance | decision-needed | neutral | low | P3-05.14 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-09 | `**Internal note:**` / `**Output:**` に相手名を含む自己評価文（143 / 416 ブロック）が owner-authored CC0 として公開され、名指しの評価文の扱いが倫理声明に無い | data | risk | neutral | med | P3-05.14 |
| R2 | ETH データ倫理・takedown の担当 | R2-ETH-10 | 不変の DOI 版に何を入れるか（第三者本文を含む `reports/` を deposit に含めるか）が決まっておらず、次版（v2.13.0 と同時）も tree 全体が固定される | data | decision-needed | neutral | med | D-P3-05-1（一部） |
| R2 | GATE 土曜ゲートを回す運用者 | R2-GATE-01 | weekly-gate に「当週のロードマップ決定」step（Step 1c）と `category=roadmap` の記録様式を置き、§4.0 の表を repo 内に置く | governance | gap | neutral | high | P2-01.10 |
| R2 | GATE 土曜ゲートを回す運用者 | R2-GATE-02 | 土曜の時刻表（chain 終了 ≤ 12:00・watchdog 12:30 / 13:30・triage tick 14:07・Ollama guard 窓）を SKILL Step 0 と §0 の配分規約に書く | ops | gap | neutral | med | P2-01.11 |
| R2 | IMPL 実装担当の Claude Code | R2-IMPL-01 | 挙動変更項目に「赤になる既存テスト」欄を置き、凍結後 PR 規則 (5) にその例外を書く | quality | gap | repair | high | P1-01.7, P3-04.1 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-01 | 3xx をアダプタ境界で失敗として閉じる（redirect 無効 = 3xx は常に失敗） | security | defect | repair | high | P1-07.18 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-02 | 平台の moderation 状態（`is_spam` / `is_deleted` / `is_locked` / `verification_status`）の読み手を置く | security | gap | instrument | med | P1-07.5 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-03 | 平台の仕様・規約の「人間の再読台帳」を 1 本置き、平台由来の定数に確認日を付ける | governance | gap | neutral | high | P1-07.19 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-04 | drift scan の盲点 2 つを同じ節に 1 行ずつ出す（未観測 baseline と「エラーのみ」endpoint） | ops | defect | instrument | high | P2-04.21 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-05 | `publish_failed` の理由列（RFC-0029）を census の enum に入れ、削除済み target の再試行ループを読む | mechanism | risk | instrument | high | P2-01.8 |
| R2 | PLAT Moltbook 側の変化を見る人 | R2-PLAT-06 | ADR-0015「1 プロセス」の適用単位を追補で明文化する（agent process のみ / 保守 script は egress inventory） | security | inconsistency | neutral | high | P1-10.14, P1-11.1 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-01 | IPD の床を「単一 ±0.13」から「セル別 SE 規則」に替え、公開 JSON から今すぐ再計算する |  |  |  |  | P3-03.10 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-02 | 新設する読み値の「率」に Wilson 区間を必須にし、帯・閾値は区間と比べる |  |  |  |  | P1-05.2, P2-01.9, P3-01.3, P3-04.8 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-03 | comment-outcomes「偶然より広いか」の検定を 10-24 の読みの前に固定する |  |  |  |  | P1-04.5 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-04 | 境界表から「系列ごとの最長無境界区間」を派生させ、方法節は使える点数を先に表にする |  |  |  |  | P3-01.4, P3-02.1 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-05 | 連続週数型トリガーに基礎率と待ち時間を 1 行ずつ添える（追補 C の「読み方」） |  |  |  |  | P1-03.9 |
| R2 | STAT 統計・研究設計の査読者 | R2-STAT-06 | 事前登録する各読みに「公開データだけで再解析できるか」の列を置く |  |  |  |  | P3-01.1 |
| R2 | TST テスト・CI の担当 | R2-TST-01 | CI だけが持つ shellcheck / markdownlint-cli2 の版 pin を 1 箇所に（`verify.sh:13` の原則どおり dev group へ） | quality | inconsistency | neutral | high | P1-08.24 |
| R2 | TST テスト・CI の担当 | R2-TST-02 | `verify.yml` の job 名・runs-on・timeout・Python 版を literal snapshot で固定し、verify.md の CI 節と照合するテスト（`tests/test_ci_config.py`） | quality | gap | instrument | high | P1-06.2, P1-08.25, P1-08.4 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-01 | staged 経路の audit 行は `snapshot_path: null` — 採用行から snapshot（reasoning.md・manifest）へ辿る鍵が書かれていない | data | gap | instrument | high | P1-12.9 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-02 | rules 層だけ来歴も gate card も無い — 04-11 の 2 件は lineage 以前、08-15 の rules-distill run（8 候補全却下）は snapshot だけが公開され、README の数字にも rules が無い | value | gap | instrument | med-high | P3-04.3 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-03 | 値層の変化系列（版境界）を公開 snapshot の digest から機械で出す — `unchanged_since` の代わりになる静止・漂流の読み | research | gap | instrument | high | P2-05.7, P3-02.1 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-04 | 53 skills の可読な索引（名前・採用日・来歴・選択実績・状態）が公開 tree に無い — 読者は 53 ファイルを開くしかない | docs | gap | instrument | med-high | P2-05.8 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-05 | identity の蒸留だけが閉じた pattern（`valid_until` あり 675 行）も入力に取る — 憲法は live のみ。来歴の読者に未記載の非対称 | mechanism | inconsistency | neutral | high | P3-04.14 |
| R2 | VL 価値層 legibility の読み手 | R2-VL-06 | 公開 comment-report の各行に「その生成に注入された skill 名」が無い — 選択→コメントの結び付きは私有ログにしか無い | data | gap | instrument | high | P2-05.9 |
| R3 | ADR ADR の校閲者 | R3-ADR-01 | 「追補 C / D」の呼び名が ADR-0080 の既存 Amendment §C（Housekeeping）と衝突する | docs | inconsistency | repair | high | P1-03.8 |
| R3 | ADR ADR の校閲者 | R3-ADR-02 | ADR と追補に層ラベルを持たせ、凍結の読み (ii)(iii) を見出しの grep で層別できるようにする | governance | gap | repair | med | P1-03.7 |
| R3 | ADR ADR の校閲者 | R3-ADR-03 | 追補と新 ADR の境界（D-P1-03-1、2027-01）より前に、推奨 A の基準なら新 ADR か partial supersede にあたる変更が「追補」として入る | governance | inconsistency | repair | med | P1-03.11, P1-12.5 |
| R3 | AKC agent-knowledge-cycle の著者 | R3-AKC-01 | AKC への書き戻しを 1 項目にし、CA の出来事で失効した AKC の記述を日付つきで直す（P3-06.7 の AKC 版） | sibling:agent-knowledge-cycle | inconsistency | neutral | high | P3-06.7, P4-02.1 |
| R3 | END 終了手順の執行者 | R3-END-01 | wind-down runbook に「鍵・資格情報の失効表」を置く | ending | gap | neutral | med | P4-02.6 |
| R3 | END 終了手順の執行者 | R3-END-02 | repo 外のスケジューラと同期（harness の `triage-ca` tick、claims.py、HF graph mirror）を wind-down の停止手順と完了確認に入れる | ending | gap | repair | med | P4-02.7 |
| R3 | END 終了手順の執行者 | R3-END-03 | 終了後（GitHub archive 後）の takedown の受付・実行経路と、私的記録の保持期間を決める | ending | gap | neutral | med | P4-02.8 |
| R3 | FUT 1 年後の自分 | R3-FUT-01 | ロードマップの束を閉じる記録と、文書自身の退役条件を 1 か所に置く | governance | gap | neutral | high | P2-01.12 |
| R3 | HRN Claude Code ハーネスのメンテナ | R3-HRN-01 | 無人週次セッションの入力の来歴（repo HEAD・branch・dirty・指示書の sha・skill 在庫）を `chain_start` に記録する | ops | gap | instrument | med | P2-02.7 |
| R3 | HRN Claude Code ハーネスのメンテナ | R3-HRN-02 | 週次セッションの終了状態を JSON envelope で読み、「拒否されて空」を理由コードにする | ops | defect | repair | med | P2-02.8 |
| R3 | HRN Claude Code ハーネスのメンテナ | R3-HRN-03 | 週次セッションの bare `Glob,Grep` allow が Read の正 scope を迂回しないことを実 CLI で 1 回確かめ、C-SCOPE に固定する | security | risk | repair | low | P1-10.15 |
| R3 | HRN Claude Code ハーネスのメンテナ | R3-HRN-04 | 週次チェーンの `claude` 子プロセスに evals と同じ環境固定（自動更新・非必須通信の無効化、env allowlist）を入れる | ops | inconsistency | repair | med | P2-02.9 |
| R3 | HRN Claude Code ハーネスのメンテナ | R3-HRN-05 | ロードマップ項目の着手単位を harness のタスク機構（`rfcs/` 台帳・claims lease・task-triage）とどう結ぶかを決める | governance | decision-needed | neutral | med | P1-13.3, P2-01.12 |
| R3 | MDL モデル交代の担当 | R3-MDL-01 | 埋め込み較正 pin を名前から digest に広げ、restore 手順に digest 照合を置く |  |  |  |  | P1-07.12 |
| R3 | MDL モデル交代の担当 | R3-MDL-02 | 凍結後の生成 / 埋め込みモデル交代を装置境界として位置づける（決定つき） |  |  |  |  | P1-01.8 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | R3-OSX-01 | Ollama 本体の更新を「計画された変更」にする（導入・更新の経路、版依存の前提の一覧、更新前後の照合、境界行） | ops | gap | repair | med | P1-07.11 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | R3-OSX-02 | 本番の launchd 構成（`install-schedule` の全引数 + 手動 plist）を repo に宣言し、テンプレート変更を本番に届ける段を release runbook に置く | ops | gap | repair | high | P2-04.22 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | R3-OSX-03 | Mac の再構築（故障・買い替え）と OS / Homebrew / Python 更新後の点検を、1 本の runbook と読み取りだけの `host_check` にする | ops | gap | repair | med | P2-04.23 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | R3-OSX-04 | 公開データの開示境界を担う `rsync` の実体を 1 つに固定して記録し、境界テストを同じ実体で走らせる | security | risk | repair | med | P0-03.3 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | R3-OSX-05 | 本番 `.venv` の再生成を規約にする（Python の minor を `.python-version` で CI と揃える・release の固定版から作る・実行環境の版を来歴に載せる） | ops | gap | repair | med | P1-07.13, P1-08.26 |
| R3 | TIME オーナーの時間の監査者 | R3-TIME-01 | ロードマップの執行を北極星の負荷系列とゲート所要分から分けて読む | governance | inconsistency | instrument | med | P1-13.3, P2-01.13 |
| R3 | TIME オーナーの時間の監査者 | R3-TIME-02 | 2027-Q1 の Phase 2 実装が凍結集合を触るので、凍結 verdict の窓と両立する形を決める | mechanism | inconsistency | neutral | high | P1-01.9 |
| R3 | TIME オーナーの時間の監査者 | R3-TIME-03 | 遅れたときの繰り越し規則・日付拘束の一覧・縮退順を `decisions.md` に置き、Step 1c が毎週照合する | governance | gap | neutral | med | P2-01.14 |
| R4 | BEHAV  | R4-BEHAV-01 | 台帳の振る舞い観察を決定論の表層カウンタで照合する（closer / nonce / skill 見出し / 短入力の膨張 / wrapper 語彙） | 計器（weekly materials の決定論的取り込み）。置き場は P1-05 の次の空き番号。 | instrument / repair | 観察と記録の側に立つ計器で、価値層にも生成にも介入しない。ADR-0083 の境界 | 中〜高。数え方は | P1-05.8 |
| R4 | ONEWAY  | R4-ONEWAY-01 | 公開 data repo への無人 force push をやめ、remote 側の commit（書き換え・takedown・手での編集）を翌朝上書きしないようにする | security absence / research（公開データの完全性） | gap（一方向の操作を無人で毎日実行している） | repair | high | P0-03.16 |
