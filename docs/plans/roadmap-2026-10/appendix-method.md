# 付録 B: 作成方法

## B.1 手順
1. **現状把握**（2026-10-09）: 本体 README / CLAUDE.md / ADR-0080（追補含む）/ docs/CYCLES.md / rfcs の blocked 7 本 / CHANGELOG を読み、旧プロジェクトのチャット 4 本（RFC-0041 設計対話、RFC-0040、論文アクション項目、学術インフラ）からオーナーの関心と制約を拾った。
2. **18 観点の並列レビュー**: 観点ごとに 1 担当が本体と兄弟 repo を実際に読み、証拠（`path:line` / commit）つきの項目を書いた。観点と件数: ADAPTER-RUNTIME 37、ADR-RFC-BACKLOG 48、CLI-UX-ONBOARDING 41、CODE-HEALTH 45、CORE-PIPELINE 32、DATA-ENDING 45、DOCS-CONSISTENCY 47、GOVERNANCE-ORG 47、LLM-PROMPTS-DECISIONS 35、OBSERVABILITY-INSTRUMENTS 48、PHILOSOPHY-FIDELITY 42、RELEASE-DISTRIBUTION 40、RESEARCH-FIT 53、SECURITY-ABSENCE 41、SIBLINGS 38、TESTS-CI-QUALITY 42、VALUE-LAYER-LEGIBILITY 46、WEEKLY-OPS-LOAD 52。合計 **779 項目**。TESTS-CI 担当は実際に venv を作り pytest / coverage / ruff / pyright / import-linter / 依存床テストを走らせ、RELEASE 担当は wheel を build して `--help` を実行した。
3. **作業束への割り当て**: 779 項目を 39 の作業束（Phase 0: 7、Phase 1: 15、Phase 2: 7、Phase 3: 7、Phase 4: 3）に重複なく全件割り当てた（付録 A）。
4. **統合**: 束ごとに統合担当が元項目の全文を読み、同一論点を 1 項目に統合し、完了条件を機械判定できる形に書き直し、証拠を再検証した（各束 5 件以上を実際に開いて確認）。capability-growth / value-steering-risk は第 5 章へ、decision-needed は第 4 章へ分けた。
5. **抜け漏れ探索**: ラウンドごとに異なるペルソナが草案全文を読み、Prune / Merge / Fix と新規項目を証拠つきで挙げ、無作為 8 件の証拠を再検証した。統合担当が各報告を取捨（採用 ✔ / 一部 ✔△ / 不採用 ✘）し、束ごとの担当が反映した。ペルソナ: R1（10 視点）= AAP の著者、FLIP の共同研究者、コード凍結のレビュアー、初見ユーザー、ADR-0080 の番人、オーナー本人、外部の再現者、security by absence の監査者、兄弟 repo のメンテナ、無人運用の SRE; R2（8 視点）= 文書整合の校閲者、データ倫理・takedown の担当、土曜ゲートを回す運用者、実装担当の Claude Code、Moltbook 側の変化を見る人、統計・研究設計の査読者、テスト・CI の担当、価値層 legibility の読み手; R3（8 視点）= ADR の校閲者、agent-knowledge-cycle の著者、終了手順の執行者、1 年後の自分、Claude Code ハーネスのメンテナ、モデル交代の担当、macOS / launchd / Ollama の更新担当、オーナーの時間の監査者; R4（5 視点）= エージェントの実挙動を見る人、前提知識なしで実行する人、削る人（項目を減らす側）、戻せない操作の監査者、相互参照の校閲者。当初は新規項目が 0 件のラウンドが出るまで繰り返す計画だったが、第 4 ラウンドで新規が 5 視点で 2 件（第 3 ラウンドは 23 件）に減り、指摘の大半が既存項目の整合の直し（吸収・削除・依存の向き・週の言い方）になった。ペルソナに穴を探させれば何かは必ず出るので、オーナーの判断で第 4 ラウンドの反映をもって打ち切った（第 5 ラウンドは行っていない。第 4 ラウンドの新規 2 件は本文に入っている。B.2）。

## B.2 反復ラウンドの記録
| ラウンド | ペルソナ | 新規 | Prune | Merge | Fix | 採用 / 一部 / 不採用 | 採用した新規 |
|---|---|---|---|---|---|---|---|
| R1 | AAP AAP の著者 | 1 | 0 | 0 | 12 | 13 / 0 / 0 | 1 |
| R1 | FLIP FLIP の共同研究者 | 4 | 1 | 3 | 13 | 14 / 0 / 0 | 4 |
| R1 | FRZ コード凍結のレビュアー | 4 | 7 | 6 | 15 | 27 / 5 / 0 | 4 |
| R1 | NEW 初見ユーザー | 2 | 2 | 3 | 9 | 14 / 2 / 0 | 2 |
| R1 | NS ADR-0080 の番人 | 4 | 3 | 4 | 18 | 26 / 2 / 1 | 4 |
| R1 | OWN オーナー本人 | 3 | 12 | 9 | 10 | 31 / 3 / 0 | 3 |
| R1 | REP 外部の再現者 | 7 | 0 | 2 | 10 | 19 / 0 / 0 | 7 |
| R1 | SEC security by absence の監査者 | 3 | 2 | 3 | 15 | 22 / 1 / 0 | 3 |
| R1 | SIB 兄弟 repo のメンテナ | 5 | 2 | 5 | 7 | 17 / 2 / 0 | 5 |
| R1 | SRE 無人運用の SRE | 5 | 0 | 1 | 8 | 14 / 0 / 0 | 5 |
| R1 計 | 10 視点 | 38 | | | | | 38 |
| R2 | DOC 文書整合の校閲者 | 0 | 0 | 2 | 28 | 25 / 5 / 0 | 0 |
| R2 | ETH データ倫理・takedown の担当 | 10 | 0 | 2 | 12 | 19 / 5 / 0 | 10 |
| R2 | GATE 土曜ゲートを回す運用者 | 2 | 0 | 1 | 14 | 16 / 1 / 0 | 2 |
| R2 | IMPL 実装担当の Claude Code | 1 | 0 | 4 | 17 | 19 / 3 / 0 | 1 |
| R2 | PLAT Moltbook 側の変化を見る人 | 6 | 0 | 1 | 7 | 13 / 1 / 0 | 6 |
| R2 | STAT 統計・研究設計の査読者 | 6 | 1 | 1 | 17 | 24 / 1 / 0 | 6 |
| R2 | TST テスト・CI の担当 | 2 | 0 | 3 | 22 | 27 / 0 / 0 | 2 |
| R2 | VL 価値層 legibility の読み手 | 6 | 0 | 1 | 9 | 15 / 1 / 0 | 6 |
| R2 計 | 8 視点 | 33 | | | | | 33 |
| R3 | ADR ADR の校閲者 | 3 | 1 | 9 | 8 | 21 / 0 / 0 | 3 |
| R3 | AKC agent-knowledge-cycle の著者 | 1 | 0 | 1 | 4 | 6 / 0 / 0 | 1 |
| R3 | END 終了手順の執行者 | 3 | 1 | 1 | 6 | 11 / 0 / 0 | 3 |
| R3 | FUT 1 年後の自分 | 1 | 0 | 0 | 8 | 9 / 0 / 0 | 1 |
| R3 | HRN Claude Code ハーネスのメンテナ | 5 | 0 | 0 | 7 | 11 / 1 / 0 | 5 |
| R3 | MDL モデル交代の担当 | 2 | 0 | 2 | 6 | 9 / 1 / 0 | 2 |
| R3 | OSX macOS / launchd / Ollama の更新担当 | 5 | 0 | 1 | 3 | 9 / 0 / 0 | 5 |
| R3 | TIME オーナーの時間の監査者 | 3 | 0 | 0 | 6 | 8 / 1 / 0 | 3 |
| R3 計 | 8 視点 | 23 | | | | | 23 |
| R4 | BEHAV エージェントの実挙動を見る人 | 1 | 0 | 0 | 4 | 5 / 0 / 0 | 1 |
| R4 | COLD 前提知識なしで実行する人 | 0 | 0 | 0 | 17 | 17 / 0 / 0 | 0 |
| R4 | CUT 削る人（項目を減らす側） | 0 | 16 | 32 | 7 | 38 / 1 / 1 | 0 |
| R4 | ONEWAY 戻せない操作の監査者 | 1 | 0 | 1 | 16 | 18 / 0 / 0 | 1 |
| R4 | XREF 相互参照の校閲者 | 0 | 0 | 2 | 20 | 22 / 0 / 0 | 0 |
| R4 計 | 5 視点 | 2 | | | | | 2 |

## B.3 読んだもの
- 読んだ commit: 本体 `2cad850` / data `a0428f4` / rules `eec96a4` / otel `ca9479f` / cloud `65b0526` / mlx `2f6c7fd` / AKC `3d42a66` / AAP `af2db90`。本文の `path:line` はすべてこの commit の行。
- 本体 `contemplative-agent`（HEAD `2cad850`、shallow clone・直近 447 commit）: README / CLAUDE.md / docs/adr 113 本（必要箇所）/ rfcs 49 本 / docs/CYCLES.md / docs/CONFIGURATION.md / docs/runbooks / docs/evidence（必要箇所）/ src 全体 / tests / scripts / config/prompts / .claude/skills / pyproject / CHANGELOG / .github/workflows
- `contemplative-agent-data`: README / DATACARD / CITATION / knowledge.json（先頭と件数のみ）/ skills / rules / snapshots / reports（メタ構造のみ。他エージェント投稿の引用本文は読まない）/ pipeline / graph.jsonld
- `contemplative-agent-otel` / `-cloud` / `-mlx` / `-rules`、`agent-knowledge-cycle`、`agent-attribution-practice`
- 旧プロジェクトの共有ファイル（論文全文、FLIP 論点メモ、憲法改正レポート、旧 llms-full）
- 旧プロジェクトのチャット 4 本

## B.4 確認できなかったもの
- repo 外の出典（旧プロジェクトの共有ファイルの論文全文・論点メモ、旧プロジェクトのチャット）は第三者が再現できない。本文はこれらを補助的にだけ引き、判断の根拠は repo の行に置いた。
- オーナーの Mac 上のランタイム実体（`~/.config/moltbook/` の episode ログ・audit.jsonl・gate 記録・launchd の実状態・`~/.claude/` のハーネス）。これらに依存する件数（蒸留取りこぼしの実数、介入ゼロ週の実数など）は repo 内の記述と commit から推定した。
- Moltbook の現行 API 挙動（`skill.md` の最新）。
- HF mirror の実際の更新日時（API で確認していない）。
- PyPI の公開状況（未公開と判断したのは `pyproject` と README の記述から）。
- Zenodo API と Software Heritage API（本セッションの proxy で 403）。版 DOI の一覧、`CITATION.cff` の `swh:1:snp:` 識別子に対応する release / directory の実在は未確認（識別子の種別の問題は仕様から言える）。
- GitHub REST（本セッションで repo 未有効）。Releases の一覧、過去 commit 時点の `CITATION.cff`、data repo tag `v1.0.0` の日付。
- shallow clone のため tag と古い履歴（`git show <sha>:<path>`、`git log --diff-filter=D`）は読めない。tag 名は `git ls-remote --tags` で取った。
- HF Dataset Viewer は大文字 id で 404「renamed」。小文字 id では未確認。
- `docs/evidence/adr-0097/` は本体 repo に存在しない（R2 の統計視点が `ls` で確認）。ADR-0097 の退役証拠は ADR 本文の記述で読んだ。本文書はこの path を根拠にしていない（P1-04 の統合メモに同じ確認がある）。
- 第三者投稿との逐語重なり（P0-03.9）は n-gram のヒューリスティックで件数だけを測った（本文は出力していない）。言い換えや引用符付き短句の扱いで ±数十行は動く。
- 旧プロジェクトの知識ファイルと 2026-10-09 以前の作業メモは、本体の 2026-10 の状態と食い違う箇所がある（モデル名、insight 再開の有無、AAP の ADR 数）。本文書は repo の `git log` と ADR 本文を優先した。
