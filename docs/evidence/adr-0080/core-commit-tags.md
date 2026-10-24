# Core commit tags: repair / instrument / capability-growth (P1-01.2)

Scope: the 90 commits that touch `src/contemplative_agent/core/` since 2026-08-16 (`git log --since=2026-08-16 -- src/contemplative_agent/core/`, counted 2026-10-24 at main 68f76c0). **Commits before 2026-08-16 are out of scope** (v2.7.0 to v2.11.0 in the CHANGELOG; git does hold them, 268 further `core/` commits back to 2026-03-10, but the roadmap asked only for the post-08-16 set and the CHANGELOG sections are release-level, not commit-level).

Status: **proposal for the owner's review.** Tags are one reader's judgment from the subject and the surrounding ADR/RFC, not from re-reading every diff. Borderline rows say so in the last column. No re-tagging later: after the freeze, `fix` type plus an RFC `alignment:` carries this (P1-01.6).

Tag meanings: `repair` = fixes, simplification, retirement, or work needed for the loop to self-regulate (ADR-0080:178-182); `instrument` = reads/records without changing what the agent does or says; `capability` = adds or replaces a mechanism that judges, generates or acts.

## Tally

| tag | count |
|---|---|
| repair | 65 |
| instrument | 16 |
| capability | 9 |

Capability-growth (9) and why: the abstain route in the promotion-worth judgement (`e5dec38`), the wiki store, Maintainer and Proposer loops and their reshaping (`b522822` `7ea1ed9` `5b5ddd4` `0d49628` `6057dd8` `c367962`; all retired by RFC-0025, `947d204`), the `DecisionBackend` seam (`e0aba3f`) and the enforce-first score4 gate (`128fe60`).

## The two questions the roadmap asked to record

- **ADR-0112 `DecisionBackend` seam (`e0aba3f`)**: recorded as `capability`. It was motivated by a repair (the hallucinated-row rate of the judgement call), but it is a new judgement mechanism with its own protocol and default implementation. Owner may overrule to `repair`.
- **ADR-0113 score4 gate (`128fe60`)**: recorded as `capability` (a new judge that enforces). Its follow-ups (`96881f5`, `4b85f22`, `b8db6c9`, `dc62d19`) are `repair`: making the one judge the only judge and deleting the old one (RFC-0046). Owner may overrule.

## Table

| sha | date | subject | tag | reason |
|---|---|---|---|---|
| e5dec38 | 2026-08-17 | feat(insight): promotion-worth に abstain 経路を開け、surprise を材料として列挙する (T-INSIGHT-WORTH) | capability | new abstain route for the promotion-worth judgement |
| 47616da | 2026-08-22 | feat(adr-0097): 統合器を解体し skill store の出口を予約 — 引き算 → 出口 → 語彙 (slice 1) | repair | dissolves the consolidator (subtraction before exit; ADR-0097) |
| 2361e40 | 2026-08-22 | feat(skill-selection): 計器に UTC 暦日窓・catalog_count レジーム表・幻覚 3 機構分類を足す (T-SKILLSEL-REPORT-WIN | instrument | selection instrument: window, regime table, hallucination classes |
| 8757683 | 2026-08-22 | feat(adr-0097): 週次 packet に 2 つの read-only 節を足す (slice 2 unit B) — never-selected の出口読み値 ( | instrument | two read-only sections in the weekly packet |
| ab14d37 | 2026-08-22 | refactor(adr-0097): fold the archive exit's duplicated shapes into one owner each (simplif | repair | simplify: one owner per duplicated shape |
| 10dcc31 | 2026-08-22 | fix(adr-0097): 3 レビューの指摘を反映 (slice 2 unit B) — 出口読み値が自分の証拠不足を数えて見せる: 落ちた日/行を unreadable_fi | instrument | review fixes to the exit reading |
| b5751ec | 2026-08-22 | fix(adr-0097): close the archive exit's silent failures — symlink delete, source-not-path  | repair | closes silent failures in the archive exit |
| db6d810 | 2026-08-22 | Merge branch 'worktree-agent-aea1ab081a7b18e24' | instrument | merge of the exit-reading branch (inherits 10dcc31) |
| 8089e91 | 2026-08-22 | Merge branch 'worktree-agent-a60da73f204bbd540' | repair | merge of the archive-exit fix branch (inherits b5751ec) |
| edca8cf | 2026-08-24 | feat(adr-0098): weekly チェーンを無人 claude 7 本 → 1 本の /weekly-report セッションに再設計し、修理を task-triage | repair | weekly chain redesign to cut human/LLM load (ADR-0098); borderline, owner may read as capability |
| a65650a | 2026-08-25 | refactor(skill-selection): split the runtime selector from its two read-only instruments | repair | split runtime selector from its instruments |
| 009baee | 2026-08-28 | refactor(lint): drain the C901 exemption ledger to empty — all 13 over-budget functions (m | repair | drain C901 ledger, behavior-preserving |
| 4838be2 | 2026-08-29 | feat(insight): restore the ADR-0096 surprise instrument, display-only (RFC-0016) | instrument | restores the surprise instrument, display-only |
| d9751c4 | 2026-08-29 | refactor(cli): remove the enrich subcommand and core.distill.enrich — deprecated no-op sin | repair | removes a dead no-op subcommand |
| 249282e | 2026-08-31 | refactor(lint): drain C901 to 11 — six 12-13 functions split behavior-preserving, step 2 o | repair | drain C901 |
| 5be5ef6 | 2026-08-31 | refactor(lint): drain C901 to 10 — the last thirteen functions, target reached with an emp | repair | drain C901 |
| f64cf41 | 2026-08-31 | refactor: undo three signature smears the C901 walk left behind — accumulator state belong | repair | undo signature smears |
| 323d780 | 2026-08-31 | chore(lint): adopt ANN boundary typing (LLM-first axis 4) and drain all 24 bare-Any sites; | repair | boundary typing |
| b522822 | 2026-09-02 | feat(wiki): RFC-0017 S1 — wiki store + 4 動詞 + 進化ログ / skill-impact の決定論描画 (RFC-0017) | capability | wiki store and verbs (RFC-0017) |
| 7ea1ed9 | 2026-09-02 | feat(wiki): RFC-0017 S2 — Maintainer ループ（索引 + read_file、予算詰め全文 episode、4 動詞、fail-closed）+  | capability | wiki Maintainer loop |
| 5b5ddd4 | 2026-09-02 | feat(wiki): RFC-0017 S3 — Proposer ループ（wiki + skill 索引 + 進化ログ + skill-impact、read_file、ato | capability | wiki Proposer loop |
| 14fe9d0 | 2026-09-02 | feat(wiki): RFC-0017 S4 — offline replay ハーネス（gemma-constrained / opus-constrained / opus- | instrument | offline replay harness for the wiki loops |
| 5578e85 | 2026-09-02 | fix(wiki): ultrareview 指摘 3 件 — insert_after の複数行アンカー無言 no-op（applied=true の嘘）を拒否、select_e | repair | fixes silent no-op that reported applied=true |
| 0d49628 | 2026-09-02 | feat(wiki): Maintainer を 1 形 + 日次全件 batch に、constrained / 200k / capacity を削除、replay を 2 ア | capability | reshapes the Maintainer into a daily batch |
| 6057dd8 | 2026-09-02 | feat(wiki): ページ長の上限を保存時に強制（PAGE_FULL、索引に長さ列）(RFC-0017 D4) | capability | page length cap enforced at store time |
| c367962 | 2026-09-02 | feat(cli): wiki-maintain --catch-up-days（plist 既定 2、fail_closed_budget 後は skipped_after_bu | capability | wiki-maintain catch-up flag |
| 947d204 | 2026-09-05 | refactor(wiki): retire the WikiSkill mechanism and the repo's cloud-egress seam (RFC-0025) | repair | retires WikiSkill and the cloud-egress seam (RFC-0025) |
| a174714 | 2026-09-06 | feat(llm): serving_environment() — モデル重みの digest と Ollama 版を session start episode と snaps | instrument | records serving environment digest per session |
| 764958b | 2026-09-06 | merge: task/retire-wiki — WikiSkill 機構と cloud 到達路の退役 (RFC-0025)。衝突解決: CODEMAPS 3 本は main の | repair | merge of the wiki retirement (inherits 947d204) |
| cce368a | 2026-09-07 | feat(insight): novelty gate の {known} を在庫全部から cosine top-10 の和集合へ (ADR-0104 / RFC-0023 S9) | repair | novelty gate known-set via cosine top-10 so the store stops overflowing context; borderline |
| 769bb07 | 2026-09-07 | feat(exit): 混同対の読みを weekly stage 7c に足し、archive 候補ファイルを書く (ADR-0105 / RFC-0021) | instrument | confusion-pair reading and archive candidate file (read-only) |
| 6d17266 | 2026-09-08 | feat: add RFC-0027 skill revision comparison harness | instrument | skill revision comparison harness (later removed, bcc97e2) |
| 99ea8bb | 2026-09-09 | feat(outcome): skill outcome 記録 — comment id を selection record に、logs/comment-outcomes.js | instrument | comment outcome recording and weekly reading (RFC-0028) |
| cc25989 | 2026-09-12 | refactor(llm): simplify core/llm — generate を generate_full へ委譲、telemetry seam を 1 本化、thin | repair | simplify sweep (2026-09-12): behavior-preserving |
| 34f814f | 2026-09-12 | refactor(core): simplify 記憶/蒸留群 — 禁止文字列走査を config の共有述語に集約（190MB の lower() コピーを除去）、upsert  | repair | simplify sweep (2026-09-12): behavior-preserving |
| 0933bd5 | 2026-09-12 | refactor(core): simplify insight/skill_selection 群 — skills/*.md の走査を text_utils.iter_mark | repair | simplify sweep (2026-09-12): behavior-preserving |
| d836eaf | 2026-09-12 | refactor(core): simplify 計器群 — _WindowTally の 16 行コピーを accumulator へ畳み、_DayScan の五重記録を sum | repair | simplify sweep (2026-09-12): behavior-preserving |
| 256434c | 2026-09-12 | refactor(core): simplify 残り core — prompt テンプレートの 3 重リストを dataclass から導出、report を EpisodeL | repair | simplify sweep (2026-09-12): behavior-preserving |
| 8a2cce8 | 2026-09-12 | refactor(moltbook): client の冪等 write 4 本を 1 body へ（409/400 方針を data 化）、rate 予備量の既定を ADAPTI | repair | simplify sweep (2026-09-12): behavior-preserving |
| 2aca11c | 2026-09-12 | refactor(adapters): percentile を core の 1 実装へ統合、pomdp の timestamp 解析を parse_aware_utc に寄せ  | repair | simplify sweep (2026-09-12): behavior-preserving |
| 5d559a5 | 2026-09-12 | refactor(core/llm): prompting の 5 つの module global を frozen PromptConfig に集約し、budget 計器の退避 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 1f4bce1 | 2026-09-12 | refactor(core/llm): 入力トークン計測を語彙の所有者である backend.py へ移し、facade は backend と estimator を束ねる 1  | repair | simplify sweep (2026-09-12): behavior-preserving |
| 705a913 | 2026-09-12 | refactor(core): 選択ログの窓を SelectionWindow DTO にし、包含判定と since/until の綴りの 3 コピーを解消 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 395c5e6 | 2026-09-12 | refactor(core/llm): thinking trace の採否も語彙の所有者 backend.py へ移し、facade からは 400 行離れた実装を消す | repair | simplify sweep (2026-09-12): behavior-preserving |
| 3b9d4b8 | 2026-09-12 | refactor(core): 選択ログの全履歴 walk と名前長の上限を selection_window へ移し、skill_confusion が never_select | repair | simplify sweep (2026-09-12): behavior-preserving |
| d9b3b2f | 2026-09-12 | refactor(core): log-health の理由コード 5 条件と宣言順フィルタを selection_window に 1 本化し、2 つの exit reading | repair | simplify sweep (2026-09-12): behavior-preserving |
| 529265c | 2026-09-12 | refactor(core): observed_injection_outcomes を write 側から selection_metrics へ移し、共有 walk を通して | repair | simplify sweep (2026-09-12): behavior-preserving |
| fef9e8e | 2026-09-12 | refactor(core): 2 つの exit reading から呼び出し側ゼロの exposure_floor 引数を落とす（DTO の欄はそのまま） | repair | simplify sweep (2026-09-12): behavior-preserving |
| a989d9f | 2026-09-12 | refactor(core): 憲法テキストの読み出しを domain.read_constitution に 1 本化し shadow 計器の再実装を解消 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 602a946 | 2026-09-12 | refactor(core): outcome log の行文法を _outcome_records に畳み、write 側 dedupe と read 側集計の食い違いを解消 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 0f17014 | 2026-09-12 | refactor(core): pivot snapshot の threshold 一覧を thresholds registry から導出し手書きミラーの漏れ 2 件を解消 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 1b8b417 | 2026-09-12 | perf(core): EpisodeLog の日次ファイル読みを mtime キーでメモ化し feed gate の 7 日分再パースを解消（4.2ms→0.41ms/call、 | repair | simplify sweep (2026-09-12): behavior-preserving |
| a3bc1a0 | 2026-09-12 | refactor(core): untrusted id の検証を config.is_valid_id へ 1 本化し create-post 側にも長さ上限を効かせる | repair | simplify sweep (2026-09-12): behavior-preserving |
| fdbe4a6 | 2026-09-12 | refactor(core): _DedupResult を add_indices だけに絞り、テキスト・埋め込みの並行タプルと 2 箇所の zip strict を index | repair | simplify sweep (2026-09-12): behavior-preserving |
| f95897b | 2026-09-12 | refactor(core): distill に postgate 引数を生やし env 読みの決定点を composition root へ渡せる形にする（既定 None で従 | repair | simplify sweep (2026-09-12): behavior-preserving |
| 162a6c0 | 2026-09-12 | refactor(moltbook): cooperation の選択をモジュール global でなく GenerationOutput.selected_skills で ti | repair | simplify sweep (2026-09-12): behavior-preserving |
| 347b913 | 2026-09-12 | refactor(core): 本文 dedup キーを core.memory.content_hash へ移し PostRecord.content_hash と同居させる | repair | simplify sweep (2026-09-12): behavior-preserving |
| 3f4dd27 | 2026-09-12 | fix(distill): dry-run 計器の embedding 参照を 1 回の束縛にして pyright の narrowing を通す（_DedupResult 整理の | repair | simplify sweep (2026-09-12): behavior-preserving |
| 64ee9fb | 2026-09-12 | refactor(memory): follow ランキングからテスト fixture 名の除外リストを外す (RFC-0035) | repair | simplify sweep (2026-09-12): behavior-preserving |
| 2079ee2 | 2026-09-12 | feat(publish): 失敗した publish 行に HTTP status と閉じた reason code を載せる (RFC-0029) | instrument | reason code and status on failed publish rows |
| cf0b87b | 2026-09-12 | fix(insight): novelty 監査ログの 2 つの書き手に kind を持たせ、リプレイが deferral 行を verdict と数えないようにする (RFC-0 | instrument | kind on novelty audit rows so replay counts correctly |
| d1f8339 | 2026-09-12 | feat(observability): 自己書き込みログ全部に読み手を付ける計器センサス + weekly-report Phase 0 通読 + エピソードログを logs/e | instrument | instrument census |
| 4c4257d | 2026-09-12 | feat(memory): pattern embedding を SQLite sidecar へ出す (RFC-0031, ADR-0108) | repair | embeddings move to a SQLite sidecar (storage, RFC-0031); borderline |
| 271e3fe | 2026-09-12 | docs(comments): コード変更後に追従していなかったコメント 72 件を現行の挙動に合わせる | repair | comments brought in line with behavior |
| c58bb94 | 2026-09-19 | fix(insight): novelty gate を temperature 0 にし tie-break を covered 向きへ (RFC-0042) | repair | novelty gate temperature 0, tie-break toward covered (RFC-0042) |
| f6faecd | 2026-09-19 | refactor(adopt): adopt-staged から保留 (--hold-names / decision="held") を撤去 (RFC-0042) | repair | removes adopt-staged hold path |
| cf04ec8 | 2026-09-19 | feat(insight): 入口を段の列にする — 名乗り・コール分割・抽出後の重複判定 (RFC-0042) | repair | insight entrance as stages (RFC-0042); borderline, owner may read as capability |
| bcc97e2 | 2026-09-19 | refactor(scripts): RFC-0027 の比較経路と RFC-0041 の測定スクリプトを撤去 (RFC-0042 項目 7 / 8) | repair | removes retired comparison scripts |
| 3b45956 | 2026-09-19 | fix(docs): 撤去済み script を現存として引く docstring 2 箇所を直し、S21 の prompt 欄 6 つを vulture whitelist へ  | repair | docstring fixes, vulture whitelist |
| 4159264 | 2026-09-20 | fix(skill-selection): 判断コールを temperature 0 に — 幻覚のある行 21〜29% → 7.3%（offline 150 行）、天井との一致と | repair | temperature 0 on the judgement call to cut hallucinated rows |
| 90ab113 | 2026-09-20 | docs(skill-selection): temperature 0 を渡す判定コールの列挙を実コードに合わせ、RFC-0043 の再実行の注意を evidence に足す | repair | docs follow the temperature change |
| e0aba3f | 2026-09-22 | feat(llm): DecisionBackend protocol と Ollama logprobs 既定実装、core 側の decide seam | capability | DecisionBackend protocol and decide seam: a new judgement mechanism (ADR-0112); motivated by a repair, recorded as capability for owner review |
| 03d1f9b | 2026-09-22 | feat(skill-selection): 判断 backend の shadow 欄 7 つを既存レコードに足し、census に登録する | instrument | shadow fields on selection records, census registration |
| 45bdc82 | 2026-09-22 | fix(decision): code-review の 4 件を反映（影の判定者が観測対象を道連れにしないように） | repair | review fixes so the shadow judge does not take the observed path with it |
| 8fd0639 | 2026-09-23 | fix(insight-surprise): mask the run window before cutting the reference to ref_k (RFC-0039 | repair | masks run window before cutting the reference |
| 6b6f819 | 2026-09-23 | docs(decision): 出所コメントを撤去後の事実に合わせる — skillsel_arm_replay.py は 2bcc274 で撤去、行番号は 817ecf3 時点を | repair | comment follows removals |
| 5cf42b7 | 2026-09-25 | feat(relevance): shadow の 4 段 Score logprobs 読みを relevance gate に並走させる (RFC-0046) | instrument | shadow score4 reading beside the relevance gate |
| 128fe60 | 2026-09-26 | feat(relevance): enforce-first の score4 gate と paired 記録、readiness 読み値、label-once 資産 (RFC- | capability | enforce-first score4 gate (ADR-0113); recorded as capability for owner review, it replaced a judge |
| 6685e75 | 2026-09-26 | fix(relevance): 「自分の分野」を本番定義（identity + axioms）に統一 — shadow / enforce / label_set / replay | repair | one definition of the production domain |
| a7fa263 | 2026-10-03 | fix(publish): reply publish rows name their target — reply_key_sha256 + parent_comment_id  | instrument | reply publish rows name their target |
| 8a526ca | 2026-10-04 | fix(relevance): remember relevance readings across sessions — key post_id + text sha256 +  | repair | relevance reading cache across sessions |
| 96881f5 | 2026-10-07 | fix(relevance): make score4 the feed's only relevance judge, fail-closed (RFC-0046) | repair | score4 as the only judge, fail-closed (RFC-0046) |
| 4b85f22 | 2026-10-09 | feat(relevance): move seed selection and the submolt-scope instrument to the score4 gate;  | repair | RFC-0046 migration; typed feat but repair (roadmap R1-FRZ) |
| eb07ef0 | 2026-10-11 | feat(insight): novelty gate の「既知」判定を store / 台帳別に 1 回だけ数える (#16) | repair | count known once per store/ledger |
| 1637962 | 2026-10-12 | fix(snapshot): manifest path columns are MOLTBOOK_HOME-relative, never the home path (RFC- | repair | path columns MOLTBOOK_HOME-relative |
| 1df51c3 | 2026-10-15 | fix(privacy): published writers record MOLTBOOK_HOME-relative paths; sync refuses to commi | repair | published writers record relative paths |
| c751f05 | 2026-10-17 | fix(insight): pass the distill system prompt to the description and name calls (RFC-0052) | repair | system prompt passed to two calls |
| e1288dc | 2026-10-17 | docs(insight): the body call's system comment said axioms-only; get_distill_system_prompt  | repair | comment correction |
| b8db6c9 | 2026-10-11 | refactor(relevance): 旧 relevance gate 一式を削除し、score4 gate を唯一の判定者に固定する（RFC-0046 後始末 3、ADR-0 | repair | deletes the old relevance gate (RFC-0046 cleanup 3) |
| dc62d19 | 2026-10-11 | refactor(relevance): relevance_shadow.py を relevance_gate.py に改名する | repair | rename |
