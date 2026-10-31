# ロードマップ 2026-10 — 束の閉じ表

**退役条件**: 39 束がすべて closed か moved-to-§5 になった週、または P4-02 の最終 sync の早い方でこの表を凍結し、以後は追記しない。次のロードマップは別の日付ディレクトリに起こす。

束を閉じるのは、その束の「束の完了条件」のコマンドを回して満たしたときだけ（土曜ゲートでも、オーナーがいる対話セッションでも）。土曜ゲート（weekly-gate Step 1c）で閉じたら同時に `gate_item category=roadmap item=<束ID> decision=closed` を 1 行打ち、この表の行は Step 6d の commit に含める。対話セッションで閉じた行は状態を `closed（gate_item 未転記）` と書き、次の Step 1c が転記して `closed` に直す。満たせない項目は第 5 章の延期行か RFC 起票のどちらかを「移した項目」に書く（黙って消さない）。P2-01.12。

| 束 | 題 | 状態 | 閉じた日 | 証跡 commit | 未達で §5 / RFC に移した項目 |
|---|---|---|---|---|---|
| P0-01 | 10-10 土曜ゲートの決定束（insight / RFC-0042・0023・0048 / ADR-0111 / T4） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P0-01.6 → RFC-0066 |
| P0-02 | 10-15 読み → 旧 relevance gate の削除（RFC-0046 後始末 3） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P0-03 | 公開データの開示境界の修理（embedding 入り .bak・ロック・絶対パス） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P0-03.6 → RFC-0067 |
| P0-04 | 蒸留の取りこぼしと非原子書き込みの修理（06:00 JST セッション） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P0-05 | 初回体験（Quick Start）の修理と preflight | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P0-05.10 → RFC-0070 |
| P0-06 | v2.13.0 リリース（Python 床・配布単位・版メタデータ・runbook） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P0-07 | 10-31 due の憲法改正ゲートの事前登録と shadow 系列 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P0-07.1 → RFC-0012、P0-07.1 → RFC-0012、P0-07.4 → RFC-0012、P0-07.8 → RFC-0055 |
| P1-01 | 機構層の「凍結」判定を定義する | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-02 | RFC 台帳の健全化と blocked RFC の終端 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-03 | ADR 台帳の機械追跡（追補・Note・索引・Review-when） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-03.5 → RFC-0069、P1-03.8 → RFC-0073、P1-03.9 → RFC-0073 |
| P1-04 | 計器の解体と消費計画の補完（ADR-0101 T4） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-04.2 → RFC-0065、P1-04.8 → RFC-0071、P1-04.11 → RFC-0071、P1-04.13 → RFC-0071、P1-04.15 → RFC-0071 |
| P1-05 | 観察台帳と週次計器の機械化（baseline・expiry・自己故障） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-06 | コード構造の最後の窓（OllamaBackend・core 内層契約・規約の明文化） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-06.1 → RFC-0071 |
| P1-07 | アダプタと LLM 接点の堅牢性（障害時の挙動・予算・較正定数・来歴） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-07.10 → RFC-0073、P1-07.11 → RFC-0070、P1-07.19 → RFC-0068 |
| P1-08 | テストと CI の強化（macOS job・未モック LLM・順序依存・床・契約） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-09 | ドキュメントの同期と欠落文書（数値・CYCLES・CONFIGURATION・glossary・llms） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-10 | セキュリティ: threat model・SECURITY.md・I/O 面の機械ゲート・鍵の所在 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-10.9 → RFC-0068 |
| P1-11 | 兄弟 repo の処遇（cloud / mlx / otel / rules） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-11.12 → RFC-0069、P1-11.14 → RFC-0069 |
| P1-12 | 承認ゲートの記録を「責任の行為」にする（approver・reason・却下本文・GOVERNANCE.md） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-13 | AI 判断役の権限境界と帰属表示の明文化 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-13.1 → RFC-0069、P1-13.3 → RFC-0069、P1-13.7 → RFC-0069 |
| P1-14 | CLI の残りの UX 整備（`.last_insight` の起点・テンプレート skills・installer の前提・`init` の Tier） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P1-15 | relevance face の較正と face ループの昇格（RFC-0047） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P1-15.2 → RFC-0073、P1-15.4 → RFC-0071 |
| P2-01 | 北極星の読み値を機械化する（止まる・負荷・自己調節・一致率） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P2-01.3 → RFC-0073、P2-01.5 → RFC-0073 |
| P2-02 | Claude Code 依存の決着（headless 週次セッションの位置づけ） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P2-03 | 私的ハーネス依存を閉じる（claims.py・release skill・パス・inbox） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P2-04 | 無人チェーンの検知面と停止手順（watchdog・sync・ロック・ディスク・ドリル） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P2-04.5 → RFC-0070、P2-04.19 → RFC-0070、P2-04.22 → RFC-0070、P2-04.23 → RFC-0074 |
| P2-05 | 公開に出す責任の接点（2 層公開・承認記録の投影・値層の縦断） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P2-05.1 → RFC-0067、P2-05.2 → RFC-0067、P2-05.3 → RFC-0067、P2-05.5 → RFC-0074、P2-05.8 → RFC-0067、P2-05.9 → RFC-0067 |
| P2-06 | 週次ゲートの読み量を減らす（carried・陽性のみ・多軸 join） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P2-06.1 → RFC-0073 |
| P2-07 | RFC-0048 出口の自己維持と knowledge の保持方針 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P2-07.1 → RFC-0048、P2-07.2 → RFC-0048 |
| P3-01 | 研究問いの操作的定義（研究問い ADR・統計方針・Q4 の採否） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-01.3 → RFC-0071 |
| P3-02 | 装置の境界表と縦断記録の再構成（regime・研究ログ・.notes の昇格） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-02.2 → RFC-0067、P3-02.3 → RFC-0071 |
| P3-03 | 対照条件（IPD の床・プラセボ憲法・旧版・Care 面・2 体目の判断） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-03.2 → RFC-0072、P3-03.3 → RFC-0072、P3-03.4 → RFC-0072、P3-03.9 → RFC-0071 |
| P3-04 | identity・憲法の版履歴と縦断計器（history・CHANGELOG・drift・複利） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-04.8 → RFC-0071、P3-04.9 → RFC-0071、P3-04.11 → RFC-0065 |
| P3-05 | 公開データセットの研究再利用性（DATACARD・schema・DOI 版・HF・再現ガイド） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-05.1 → RFC-0067、P3-05.8 → RFC-0067、P3-05.14 → RFC-0069 |
| P3-06 | 論文・FLIP 供出・AAP への書き戻し・哲学読みの計器 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P3-06.3 → RFC-0062、P3-06.6 → RFC-0069、P3-06.7 → RFC-0069 |
| P3-07 | 「空性のみ公理」案と価値層への介入チャネルの決定 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P4-01 | 終了判断の検討イベントと判断役を予約する | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | — |
| P4-02 | wind-down runbook（手順のみ・発動条件を持たない） | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P4-02.2 → RFC-0074 |
| P4-03 | 継続性（bus factor 1）・引継ぎ・インシデント手順 | closed（gate_item 未転記） | 2026-10-31 | roadmap/closeout-1031 | P4-03.3 → RFC-0069 |
