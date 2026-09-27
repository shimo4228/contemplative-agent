# T-CONSOLIDATOR-REDESIGN — 統合器 3 本と入口 / 出口の再設計

## Context（なぜ変えるか）

skill 抽出パイプライン（insight → staging → headless Claude review → 人間 adopt）は、週 46–55 件の候補を出し続け、採用は 12%、却下理由はほぼ「store に既にある」。store は 57 件で出口が無く（削除は人間が思い出したときだけ、5 ヶ月で 6 件）、19 件は直近 1 週間で一度も選ばれていない。統合器 3 本（skill-stocktake / rules-distill / rules-stocktake）は 08-15 の実測で、clean 段 47 件中 4 件しか有用でなく 3 件は逆効果、rules-distill は 48 件中 20 件しか読まず出力 8 本は全却下、rules-stocktake は 2 文書に対して動く。入口側では gemma の 2 つの gate（novelty: covered 12–30% vs 人間 80–90%、worth: 46/46 promote = ADR-0096 自身の事前登録した反証条件）が仕事をしていない。実効の判定者は headless Claude reviewer（4 週とも人間の採用集合と一致）だが、その「X と同じだから却下」という判断は `grep -q RECOMMEND:` で捨てられている。

探索（code map 2 本、wiki、外部文献、他分野の類推、architect、Codex premise challenge）の結論: **build はほぼ引き算＋出口＋語彙**。詳細な証拠は下の付録（§0〜§10）。

## 著者決定（2026-08-22）

- **Q1 実行範囲 = B: ADR ＋ スライス 1（削除）**。ただし「週に 1 変数」は暦でなく**観測量**で守る（§10 の観測ゲート表）。流量 ≈ 80–95 judged / 日なので、ほとんどのゲートは 1–2 日、rule 昇格の基準は既に満たす。次のスライスは前のゲートが読めた時点で進める
- **Q2 skill-stocktake = 全部ばらす**: grouping / merge / clean を落とし、description 監査 + usage 読み値だけの command に
- **Q3 rule 昇格 = A'**: 「制約」family の**共通の姿勢**を gemma が既存 `stocktake_merge_rules.md`（共有する核を 1 本に合成）で Practice/Rationale に描画 → 人間ゲート。**6 冊の skill は残す**（各冊は固有の手順を持つ。co-selection は add-on 関係）。選ばれなくなった冊は exit の読み値で退役

## 実行計画（このセッション: ADR ＋ スライス 1）

### 0. ADR（先に書く）
- 新 ADR「統合器の解体と出口 — 引き算 → 出口 → 語彙」（`docs/adr/0097-…md` + `.ja.md`、skill: `adr-writer`）。Decision: (1) ADR-0096 の事前登録 fallback 実行（worth 判定と surprise 計器の撤去、channel は残す）、(2) rules-distill / rules-stocktake 退役、(3) skill-stocktake を description 監査 + usage 読み値へ縮退、(4) 出口（archive / never-selected 読み値 / supersedes）と語彙（reviewer verdict 文法 + 1:1 検査）を後続スライスとして予約、(5) rule 昇格は A'、(6) 観測ゲート表（§10）を Review-when に。supersede 注記: ADR-0016（stocktake = 広い統合器）、ADR-0048（clean 段）、ADR-0096（worth 判定）、ADR-0046 amendment（summary grouping）。`docs/adr/README.md` 索引更新、`adr-reviewer` を通す

### 1a. worth 判定と surprise 計器の撤去（ADR-0096 fallback）
- `core/insight.py`: `_worth_gate` の LLM 呼び出し（`:302-383`）と `_worthgate_enabled` / `_append_worth_audit` を削除。**残す**: `NOTHING-PROMOTABLE` 抽出 abstain（Decision 1）、`ABSTAIN_NOTHING_PROMOTABLE` 理由コード、yield 行、fault / verdict の marker 規則（Decision 4–6）。`_read_surprise` / `insight_surprise.log_surprise`（`:745-753`）と `SkillResult.surprise`（`:133-136`）を削除
- 削除: `core/insight_surprise.py`、`config/prompts/insight_worth.md`、`core/prompts.py:35` の `INSIGHT_WORTH_PROMPT`、`cli/adopt.py:816 _print_surprise`、`cli/staging.py` の sidecar `surprise` field、`tests/test_insight_worth.py`、`tests/test_insight_surprise.py`、`tests/test_insight_chaos.py::TestWorthGateFailsOpen / TestWorthGateDisabledPath`
- `tests/test_packaged_assets.py`（prompt 数 38 → 37 hand-written）、`docs/CONFIGURATION.md:291`（40 → 39 loaded）
- `insight-recommendation.md` は surprise を読んでいないので変更なし

### 1b. rules-distill / rules-stocktake の退役
- 削除: `core/rules_distill.py`、`cli/memory_cmds.py:423-464 + :607`（handler と parser 登録）、`cli/stocktake_cmd.py:813-827`（rules 経路）、`config/prompts/rules_distill.md` / `rules_distill_refine.md` / `stocktake_rules.md` / `stocktake_merge_rules.md`（**`stocktake_merge_rules.md` は Q3 の合成で使うので残す** — 呼び出し元を gate セッション用の小さな入口 `promote-family`（後続スライス）に付け替えるまで prompt だけ保持）、`core/prompts.py` の該当 4 行、`tests/test_rules_distill.py`、`tests/test_stocktake.py` / `test_cli_stocktake.py` の rules ケース
- `core/thresholds.py` の `CLUSTER_THRESHOLD_RULES`、`core/stocktake.py` の `_check_rule_quality` は **残す**（rules 層の保守読み値に使う — codex 2）
- `.last_rules_distill` marker の read/write（`core/_io.py` 利用側）を削除

### 1c. skill-stocktake の縮退
- `cli/stocktake_cmd.py`: `_stocktake_merge_phase` / `_stocktake_clean_phase` / drop 段の staging 生成を削除、`_run_stocktake_phases` を report → description 監査のみに。`core/stocktake.py`: `_find_duplicate_groups` / `merge_group` / `clean_skill_triggers` / grouping 証拠（`_skill_grouping_evidence`）を削除、`run_skill_stocktake` は quality check（決定論）＋ usage 読み ＋ description 監査
- 削除: `config/prompts/stocktake_skills.md` / `stocktake_merge.md` / `stocktake_clean.md` / `stocktake_group_system.md` / `stocktake_merge_system.md` / `stocktake_clean_system.md`、`core/prompts.py` の該当行、`tests/test_stocktake.py` / `test_cli_stocktake.py` / `test_cli_stocktake_drop.py` の merge / clean / grouping ケース
- `--stage` は description 監査が advisory なので不要になる → flag 削除（staging 経路の `sources` 削除セマンティクスはスライス 2 の `--archive-names` が引き継ぐ）
- `Tier.LLM_RUNTIME_ONLY` 等の registry 設定は維持

### 1d. docs / 索引
- `CLAUDE.md` CLI 一覧（rules-distill / skill-stocktake の行）、`docs/CODEMAPS/architecture.md` Data Flow（鮮度規約: 同 PR）、`docs/CODEMAPS/core-modules.md` / `INDEX.md` / `moltbook-agent.md`、`docs/CONFIGURATION.md`、`README.md` / `README.ja.md` の該当行、`docs/CYCLES.md`
- 台帳: `T-CONSOLIDATOR-REDESIGN` → `decided`（この plan と ADR を結論として記録）、`T-CONSOLIDATOR-CADENCE` → `dropped`（壊れた道具に時計を付けない、の結論が「道具を外す」になった）、`T-SKILL-PROMOTE` → `candidate`（A' の形で再定義）

### 検証（スライス 1）
- `.claude/verify.sh`、`uv run pytest tests/ -v`、`uv run lint-imports`、`uv run ruff check src/ tests/ scripts/`
- `contemplative-agent --help` に `rules-distill` / `rules-stocktake` が無い、`skill-stocktake --help` に `--stage` が無い
- `grep -rn "insight_worth\|insight_surprise\|rules_distill\|stocktake_clean\|stocktake_merge\b" src/ config/ docs/` が空（`stocktake_merge_rules` は残る）
- 挙動への影響ゼロの確認（§10 1a–1c）: insight の yield 行が worth 呼び出しなしで出る（次の土曜 run、`insight-launchd.log`）— 待たずに次スライスへ進んでよい
- Review chain: `/code-review`、python-review、security-reviewer は診断どおり不要（新しい I/O 面なし）→ skip 理由を commit message に 1 行

### 後続スライス（観測ゲートが読めたら。§9 / §10 が正）
- スライス 2（出口）: `skills/.archive/`、`adopt-staged --archive-names`、packet の never-selected 節（strict / dormant / fail-open 併記）、`supersedes:`、co-selection family script、`value_layer_due_check.py` の `rules` 節、`promote-family`（Q3 A' の入口: family 名 → `stocktake_merge_rules.md` で合成 → staging）
- スライス 3（語彙と測定）: reviewer verdict 文法 + packet の 1:1 / 実在検査、offline replay、retrieval recall 測定 script、description 監査を 57 件に 1 回

---

# 付録: 探索ノート

> 以下は探索の記録。agent 4 本（code map ×2 / wiki / web ×2）と architect / codex の意見を束ねた。

## 0. 観測の確定（2026-08-22、実データ）

### 入口（insight → staging）
| 週 | clusters | gate covered | staged | adopted |
|---|---|---|---|---|
| 07-09 (bootstrap) | – | – | 54 | 13 |
| 07-18 | 117 | 0 (fail_open_llm) | 106 | 0 |
| 07-25 | 97 | 13 | 78 | 5 |
| 08-01 | 77 | 23 | 50 | 13 |
| 08-08 | 75 | 11 | 55 | 8 |
| 08-15 | 61 | 8 | 49 | 5 |
| 08-22 | 68 | 13 | 46 | 9 |

- 累計 staged 438 / adopted 53 (12%)。gate の「covered」は 12–30%、人間＋reviewer の「既存に覆われている」は 80–90% — **同じ問いに対して判定者の答えが 4〜6 倍ずれている**
- novelty gate の証拠: 候補側 = 3 pattern × 300 chars、store 側 = name+description のみ（本文なし）、ledger 397 件（うち実 skill 57、残りは却下済み候補）、prompt は「迷ったら NEW」に偏らせてある、batch 内重複は見ない（`core/insight_novelty.py`）
- worth gate（ADR-0096、08-21 が初回）: **46/46 promote**、抽出側の `NOTHING-PROMOTABLE` も 0（`insight-launchd.log:990` yield 46/55, nothing_promotable=0、残り 9 は `no_title` fault）。成果物を作ってから判定させても gemma は yes を返した（ADR-0084 v4 arm と同型）。**ADR-0096 自身が事前登録した反証条件「Rate = 0% → 設計は refuted、判定者を落として channel だけ残す」が初回の読みで発火している**（同 ADR Consequences）。deployed prompt copy（`$MOLTBOOK_HOME/prompts/`）は存在しないので packaged default が走った = 測定対象の構成
- 抽出は store を見ない設計（audit H6）。name / description / 本文は 1 コールで生成、description は本文と照合されないまま novelty gate の inventory と selector の catalog に流れる（`analyzing-systemic-governance-loops` の不一致はここで生まれる）
- 週次 reviewer（Claude headless, `--add-dir skills`, Read/Glob/Grep、`--output-format text`）は store 本文を Read できる唯一の段。実際に store skill を名指しして却下している（08-21 review）が、batch 内変奏 3 件（disaggregate / distinguish-persistence / degradation-gradient）は通した

### 店（store）と選択
- 57 skill、15.3k words。frontmatter は name / description / origin のみ — 抽出日・source pattern・採用日・選択回数は **ファイルに無い**（lineage は audit.jsonl だけ）
- 選択ログ（08-15〜08-22、judged 606 件、selected p50 = 6）: 上位 7 skill で選択の 56%、上位 14 で 79%。**0 回選択 = 19 件**（うち 7 件は 606 回提示で 0、`affirm-cognitive-possibility` 等 4 件は 1,845 回提示で 0）。`detecting-abstract-to-operational-constraint-shift` は 66% の action で選ばれる（= ほぼ無条件）
- 出口: `remove-skill` 6 件（手動）、stocktake merge 3 回（04/05/06 月）＋ 08-15 の 1 回。統合器は人間が回したときだけ動く
- **選択の単位は skill でなく family**（新しい読み、08-15〜22 judged 606）: `detecting-abstract-to-operational-constraint-shift` と `structural-constraint-mapping-scm` は P(b|a)=0.66 / P(a|b)=0.77 で一緒に選ばれる。「制約」family（6 件）のどれかが選ばれる action = **80%**、「主張の分解」family（5 件）= 72%。個々の skill は 45〜66% で状況的に見えるが、family 単位では常時に近い。T-SKILL-PROMOTE の前提（上位 3 件が 8 割超）は **skill 単位では失効**（catalog 成長で票が割れた）、**family 単位では成立**。共選択（co-selection）は embedding も LLM も要らない code-owned の family 信号
- co-selection から読める構造（同窓、両向き P ≥ 0.6 = selector が区別しない対）: `cross-reference-foundational-claims` ↔ `dissecting-asserted-agency-into-mechanisms`（0.63/0.65）、`internal-process-audit` ↔ `shifting-focus-from-state-to-process-mechanics`（0.64/0.69）、`detecting-abstract-to-operational-constraint-shift` ↔ `structural-constraint-mapping-scm`（0.66/0.77）。非対称（P(b|a) ≥ 0.7 かつ P(a|b) ≤ 0.4 = a は b の下位ケース）が 11 組: `suspend-interpretation-upon-premise-doubt → internal-process-audit`（0.96/0.23）、`scope-boundary-mapping → detecting-abstract…`（0.76/0.19）、`deconstruct-confidence-proxies → dissecting-asserted-agency`（0.75/0.10）等。**code だけで family の階層（兄弟 / 親子）が出る**
- selected_count は p50 6、最大 16。上限なし（ADR-0076）。catalog 24→37 で selector の語形幻覚が 13 倍（08-08 読み）— catalog サイズ自体が selector の容量制約

### 機構の事実（code map、file:line は agent 報告から）
- 抽出 `core/insight.py:196-247`: 1 コールで name / description / 本文。store を見ない（audit H6）。`canonicalize_frontmatter_name` は heading → name の揃えだけで description は検証しない
- novelty gate `core/insight_novelty.py:356-424`: 証拠 = store + ledger の name/description、候補 3 pattern×300 chars。fail-open per chunk。batch 内重複は見ない（`insight-recommendation.md:14-17` が reviewer に委ねる）
- worth gate `core/insight.py:302-383`（ADR-0096、proposed）: 店を見ない設計。初回 46/46 promote
- stocktake `cli/stocktake_cmd.py:584`: grouping 1（summary 証拠）→ merge G（全文、union、CANNOT_MERGE）→ drop（決定論）→ clean N（ADR-0048、`CLEAN_NOOP`）→ description 監査 N（advisory）。**≈ 1 + G + 2N コール**（57 件で ≈115）。usage 次元は `stocktake.py:609-611`「統計のみ、gate も閾値も消費しない」、退役は staging に載らない（report のみ）。marker は触らない
- rules-distill `core/rules_distill.py:189-242`: `cluster_patterns(max_size=10)` → `singletons[:10]`、全 dict が同スコア 0.1 なので列挙順。既存 rule / 憲法 / identity は渡さない（`:106-108`、system = base prompt）。skill の退役経路なし。`.last_rules_distill` は対話承認経路でしか書かれない（`--stage` は書かない）
- rules-stocktake: 全文 grouping、merge は「共通核の合成」（skill 側の union と逆）、clean / description / usage なし
- selector `core/skill_selection.py:185-250`: catalog = `name — description` 1 行/skill、system = identity+axioms、think=False、cap なし。ログは judged-only で exposure を数える（`:729`）
- store file: frontmatter は name / description / origin の 3 つだけ。抽出日は filename suffix、lineage（source_ids）は audit.jsonl と sidecar にしか無く adopt で sidecar は消える

### 統合器 3 本（台帳 A〜I、08-15 実測）
- skill-stocktake: 68 分 / 97 コール、clean 段 47 件中 14 件がバイト同一の書き戻し、採用 5 / 却下 21
- rules-distill: 48 件中 20 件しか LLM に渡らず（列挙順）、上位層・同位層と照合せず、skill の退役経路なし。8 候補全却下
- rules-stocktake: 2 rule に対して動く意味が薄い

## 1. 設計軸（候補を並べる前の座標）

1. **判定者と証拠の配置** — coverage を「誰が・何を見て」判定するか（gemma/descriptions → Claude/bodies → 人間）
2. **統合のトリガー** — 人間起動 / 定期 / 採用時イベント（on-insert）
3. **店の単位** — 平坦 57 件 / capability family + 代表 1 件 / 常時層（rule）と状況層（skill）
4. **出口の信号** — 人間の気づき / 提示回数条件付き never-selected / 採用時の supersede / 保管（archive）と削除の区別
5. **入口流量の決まり方** — エピソード数比例（現状） / 店の飽和に依存 / 複数週の再出現（attestation）
6. **生成と判定の分離** — 強いモデルは判定・組織化まで、本文生成は agent のモデルに残す（ADR-0013 / ADR-0050 の観測スタンス）

### 人間ゲートの実態
- 4 週とも人間の adopt 集合 = reviewer の `RECOMMEND: adopt` 集合（13/8/5/9、08-22 は名前集合まで一致）。**実効の判定者は headless Claude reviewer**。人間は ADR-0085 の想定どおり intent summary を読んで承認している。したがって store の質は reviewer prompt と**その証拠**で決まる — 今日の name/description/本文不一致 1 件と変奏 3 件は、その reviewer が通した

## 1.5 wiki / 文献から借りる判断材料（出典は wiki concept ページ、一次は arXiv id）

- **add-all は no-memory より悪い**（Experience-Following 2505.16067）。選択的記憶が効くかは **judge の質**で決まる。10% の誤経験混入で Pass@1 −5.3（EDV 2606.24428）
- **自己確証の罠**（EDV）: 実行・蒸留・検証を同じ agent がやると verify が系統的に甘くなる。third-party distill > self-distill。→ gemma の worth gate 46/46 promote はこの型。判定は producer と別系統に置く
- **プログラム的信号 > 自由記述の内省**（Honest Lying 2605.29463: 内省記録は 0/121 で正しい対象を名指し、プログラム抽出に替えて 86%）。GSME（2607.13683）「why は操舵だけ、credit は gate が決定論で」
- **使用頻度は退役信号として検証されていない**（ContinualSkillBench 2608.03874: 69.5% 再利用でも効果なし / Backtrace 2607.27484: 宣言的使用 ≠ 因果的依存）。**ただし CA の never-selected は「一度も注入されていない」= 効果の経路が構造的に無い**ので、退役が挙動に影響しない（挙動中立）ことが構成から言える — 効果測定を要しない唯一の退役信号
- **平均限界寄与で退役すると振動する**（SLIM 2605.10923 vs Skill0.5 2605.28424）: 難しい尾で効く一般 skill を平均が殺す。退役は「削除」と「吸収（absorb）」を分ける
- **Trace2Skill（2603.25158）**: 階層マージで編集頻度を核/周辺の証拠に。**EvoAgentBench（2607.05202）**: 7,326 → 170 canonical を embedding blocking + 3-way LLM consensus で
- **Skills in the Wild（2604.04323）**: marketplace の 46% が重複、34k skill で no-skill baseline に戻る。SkillReducer（2603.29919）: description 圧縮で質が上がる
- **Instruction Stacking Collapse（2608.02639）**: 指示 1 → 20 で遵守率 96% → 20–60%。rule 層は少数に保つ根拠
- **AuthMem（2608.01679）**: 統合は主張を残して authority を落とす（48/49）→ lineage をファイルに残す根拠
- **多様性の錯覚**（R-Diverse 2602.13103）: batch 内だけの多様性（local）/ 語が違うだけ（surface）。候補 46 件の「相互に違う」は local illusion の疑い
- 未 ingest: ACE（2510.04618）/ Dynamic Cheatsheet / MemoryBank 忘却曲線

## 1.6 外部 Web 調査（as-of 2026-08-22、一次ソース照合済み。設計に効く点だけ）

- **出口が無い店は必ず肥大し利用率が落ちる**: AutoRefine v1（2601.22758）— 保守なしで 108 pattern / 利用率 0.08、保守ありで ~24 / 0.71。SkillBrew（2605.29440）— add-only は「休眠・有害 skill が retrieval 枠を奪う」47.0 vs 59.0。SkillFlow（2604.17308）— 弱いモデルは「ほぼ全タスクを skill に要約」し重複が無制御に増える、強いモデルは 1–2 skill を**繰り返し改訂**する（CA の gemma は前者の型）
- **add-all < none の再現**: Dynamic Cheatsheet（2504.07952）Full-History が GPT-4o を 20.0→13.3 に落とし curated は 40.0
- **全量書き換え型の統合は壊す**: ACE（2510.04618）「context collapse」— 一枚岩の書き換えで 18,282→122 tok、精度が無適応 baseline 以下。ACE は itemized delta + 決定論 merge + embedding dedup。→ stocktake の全量 batch より、触った近傍だけの差分統合（S1）
- **Mem0 v3（2026-04）は UPDATE/DELETE を捨てて ADD-only + 同値 skip + 検索時 decay に戻した**（「reconciliation が context を壊していた」「delete は後で要る情報を消した」）。→ S1 は「既存を上書き」より「新を採用＋旧を archive（`superseded_by`）」の形を既定に。削除はしない
- **SkillOps（2605.13716）**: 退役は「低利用 AND 重複が存在」の複合条件、`red`（同値）/ `alt`（同目的別手段）edge で merge。CA の co-selection 両向き対 = `red`、非対称対 = 特殊化
- **「同じ family の違う兄弟を選ぶ」問題**: SameCapRisk-Bench（2606.10388 v2、08-20）— family は当たるが兄弟を取り違える HSR@3 0.35 → family ごとに代表 1 件へ解決してから rank すると 0.007。retrieval 時の family 解決であって store 構造ではない。→ Shape C の根拠（selector 側）
- **description だけの routing は本文込みより Hit@1 で 37–44 pt 落ちる**（SkillRouter 2603.22455）。本文から蒸留した description で半分戻る → E4 の根拠。summary 判定は「微妙な区別を潰す」（2512.05334）→ coverage 判定に本文が要る（E1）
- **小型 judge の信頼性**: JudgeBoard で Qwen3-4B 0.64、Gemma-2B は人間との π 26（2406.12624）。self-judge の leniency P₊ 0.87–0.99。外部 verifier を生成後に置くと 5%→38%（2402.08115）。→ gemma を coverage / worth の判定者にしない（E2 / E3）
- **listwise の位置バイアス**: 1 prompt に 90 件で「尾の識別はほぼ消える」、≤30/batch（2505.12570）。→ reviewer の 46 件一括 prompt と novelty gate の chunk サイズは見直し対象
- **retrieval の盲点**: anisotropy（cosine が高値帯に集まる）/ hubness / 語彙一致優先。SkillRouter 自身の near-dup filter は trigram Jaccard>0.6 が cosine>0.92 の **42 倍**の対を拾った。→ E1 の列挙は cosine top-k + 字面（trigram / BM25）top-k の和集合
- **usage ≠ utility は再現多数**（SkillFlow / SkillsBench / AWM 18.5% / Memento-Skills「訓練で最適化した skill の大半が test で発火せず」）。rich-get-richer / cold-start を分析した論文は無い（absent）。→ X1 は利用率でなく「注入された事実が無い」だけを使う
- **Anthropic Skills の運用規約**: 「作者は自分の reviewer になるな」「description が広すぎて他 skill のトリガーを奪う」「merge は評価で同等と確認してから」「listing budget は呼ばれない skill から落とす（降格）」

## 1.7 他分野の類推（as-of 2026-08-22、一次ページ照合済み。設計に効く点だけ）

- **図書館 CREW / Slote**: 「最終貸出日は filter であって verdict ではない — 司書が必ず見る」（X1 の形そのもの）。puller と decider を分ける、書面の方針、候補を掲示して異議期間。**Slote 法**: 退役の idle 閾値を「現に使われている本の idle 分布」から経験的に読む → X1 の floor を「選ばれた skill が初選択までに要した露出数」の分布から取る。**失敗**: just-in-case（書面の理由を義務化するまで 98% が保持された — `remove-skill --reason` 必須は正しい）、reviewer を飛ばしたデータだけの大量除籍（Urbana / Berkeley）→ 自動 archive はしない。「足した分だけ抜く」（inflow ≈ outflow）
- **Wikipedia**: redirect は安い — 名前は残し本文だけ消す（S5 + ledger）。**新しい重複は古い本記事へ merge する**（逆ではない）→ `adopt-superseding X` は既定にしない: X には選択履歴と hub 位置があり、新を採って旧を archive すると cold start に戻る。既定は `reject: covered-by X`、supersede は reviewer が「新が明確に優る」と書いたときだけ。merge backlog（提案して誰も実行しない）は人間起動 stocktake の 5 ヶ月と同型
- **API 廃止**: Blink「削除が安全な閾値は無い」、use counter の盲点（計測 off 環境）、Piranha「stale = 目的達成 + 8 週未変更、owner を reviewer に」。→ 数値 floor は "考慮に値する" 目安であって自動条件にしない
- **神経科学**: schema 整合が高い → 同化、低い → 新規、中間 → 失われる（reviewer の 3 値 covered-by / adopt / vague と同型）。replay の優先度 = gain × need、**一度も想起されない項目は need ≈ 0 → 統合（merge）に LLM を使わない**。忘却が既定で持続は獲得するもの — 57 件中 1/3 が未選択なのは既定が逆
- **Zettelkasten**: 出口は削除でなく非リンク化。collector's fallacy（集めることと知ることは別）、inbox は空になるまで処理（staging の単一 batch 不変条件と同型）
- **辞書 / ISO**: 採録は独立出典×期間（attestation — ただし本 corpus は全テーマが毎週再出現するので濾さない、E5 却下の根拠と整合）。「一度載せたら消さず obsolete 印」「用語でなく概念の特徴で比較」（名前でなく挙動で dedupe — prompt が既にそう書いている）
- **分類学**: senior synonym + junior は pointer（S4 `superseded_by`）、nomen dubium は保留状態（`--hold-names` が既にある）、WoRMS は削除せず status 変更
- **生態学（stock-and-flow）**: 人間起動だけの outflow は止まる（Valley Forge の鹿）。目標は個体数でなく植生（outcome）で決める → store の目標は件数でなく selector の読み値（幻覚率 / p50 選択数）

### Slote 読み（この session で実測、judged 3,941 記録）
- 初選択までの露出数: p50 7 / p90 99 / p95 302 / **max 569**（`fluid-dynamic-resonance…`）。→ X1 の floor は **≥ 600 judged 露出**（≈ 1 週）が「観測された最遅の初選択」を超える最小値
- **履歴全体で一度も選ばれていない skill（strict）**: 3 件 — `pre-processing-state-validation`（2,531 露出）/ `assume-perfect-adversarial-understanding`（1,845）/ `introducing-intentional-systemic-ambiguity`（1,845）。今日採用の 9 件は露出 2 で判定外
- 直近窓（08-15〜）で 0 選択の 7 件のうち 4 件は以前に 1〜5 回選ばれている（dormant）。**挙動中立の主張が立つのは strict の 3 件だけ**。dormant は読み値として併記し、退役根拠にはしない（§0 の「7 件」はこの区別で読み替える）

## 2. 診断（3 つの根）

- **RC1 入口の判定者の非対称**: 安い判定者（gemma、description、3 サンプル、「迷ったら NEW」）が 85% を通し、強い判定者（Claude reviewer + 人間、本文）が 85% を落とす。本当の判定者は reviewer だが、その証拠は自分で Read する ad hoc（ログ無し）で、語彙は adopt/reject の 2 値 — 「X に覆われている」という判断は毎週捨てられる
- **RC2 店に代謝が無い**: 統合は人間起動・115 コール・低歩留まり（clean 4/47 有用、3 件は逆向き、grouping は summary 証拠で recall 未測定）。出口は無い。lineage は adopt 時に sidecar ごと消え、store は自分の由来も採用日も言えない
- **RC3 単位の不一致**: selector は family 単位で選び（co-selection）、store は平坦な skill、gate は description を比べ、description は本文と照合されない（name/description/本文の三重 identity）

## 3. 設計原則（候補を縛る制約）

- P1 生成は agent のモデル（gemma）に残す。強いモデルは判定と組織化まで（ADR-0013 / 0050、audit H6）
- P2 観測 > 操舵: 却下は学習へ戻さない。計器は gate しない。ただし **containment（何を配備するか）は人間が決めてよく、code の統計は提案してよい**（ADR-0081 の分業）
- P3 数値キャップを品質フィルタにしない。容量の読み値（C2 guard の型）は可
- P4 変数は一度に一つ（ADR-0056）→ 計器を先に、機構は後に、1 週 1 変数
- P5 signal-first（起きていない障害の退避先を作らない）
- P6 新しい判定は replayable audit 付き（ADR-0075）、fail-open、理由コード
- P7 人間ゲートは土曜 1 セッション（ADR-0085）
- P8 judge ≠ producer（EDV）
- P9 プログラム的信号が取れるところで LLM に内省させない（co-selection / exposure / recurrence）

## 4. 候補機構（軸別。採否は §6 の shape で束ねる）

### 入口
- **E1 reviewer の証拠束を code が作る**: staged 候補ごとに、embedding（nomic、既存）cosine top-k と字面（trigram Jaccard / BM25）top-k の**和集合**で store 候補 k=3〜5 件を**列挙**（抑止ではない — ADR-0074 の却下は閾値分類であって ranked retrieval は未測定、07-18 note Q1。字面側は SkillRouter の 42 倍の知見）し、その**本文**＋直近 14 日の selected/exposure＋batch 内近傍 3 件を reviewer prompt に inline。reviewer は Read しない。1 prompt の候補数は ≤30 に分割（位置バイアス）。verdict 語彙を拡張: `adopt` / `adopt-revising <skill>` / `adopt-superseding <skill>` / `reject: covered-by <skill>` / `reject: sibling-of <cand>` / `reject: vague`。束は記録され replay 可。**offline 検証が可能**: 438 件の人間ラベル + reviewer が名指しした covering skill（`logs/weekly-pipeline/<run>/insight-input.md` に候補全文、review.md に verdict）で recall@k を測れる
- **E2 gemma worth gate（ADR-0096、proposed）の失効条件を明記**: 次 2 run も ≥95% promote なら自己確証の罠（P8）として退役。1 run では判断しない（one-run-not-evidence）
- **E3 novelty gate は ledger 係として残す**（3 コール、安い）。coverage 判定は期待しない。prompt を 3 値（new / covered-by-skill / recurs-rejected）にして「却下テーマの再出現」を読み値にする案は ADR-0050 Decision 5（attractor persistence の測定）の実装になる
- **E4 description を本文から導出**（抽出後の 2 コール目、selector の register で ≤25 語）＋ ADR-0081 の description 監査を stage 時に左遷（sidecar に verdict、reviewer に見せる）。RC3 の源を塞ぐ
- **E5 attestation（複数窓の再出現を抽出条件に）**: 辞書の採録基準の型。gate の照合精度に依存するので E3 の 3 値化の後でしか評価できない。後回し

### 店・統合
- **S1 採用時の近傍統合（event-driven、差分のみ）**: reviewer が `adopt-superseding X` なら候補を採用し X を archive（`superseded_by` を両側に記録）— **上書きも削除もしない**（Mem0 v3 が UPDATE/DELETE を捨てた理由、ACE の collapse）。`adopt-revising X` は gate セッションで既存 `merge_group([X, 候補])`（union prompt、gemma）を回し、人間が diff を見て X を置換する経路（`sources=[X]` の自己上書きは clean 段で実在）— 既定ではなく人間が選んだときだけ。統合が「触った近傍」に限定され、115 コールの全量 batch は不要になる
- **S2 family view（co-selection の計器）**: 選択ログから P(b|a) ≥ 0.6 両向きの群を code で出し、packet に「selector が区別していない群」として提示。stocktake の grouping 段の**証拠**（または代替）にする — ADR-0046 amendment が認める recall 未測定の summary grouping を、観測された信号で置く。selector が区別しない 2 skill は selector にとって 1 skill
- **S3 ADR-0048 clean 段の退役**（Inward dissolution）: 抽出段が構造トリガーを強制済み（`c20ec5f`）、08-15 実測 14/47 バイト同一・3 件逆向き・4/47 採用。merge と description 監査と usage 読みは残す。stocktake は ≈1+G+2N → ≈1+G+N 以下
- **S4 frontmatter に lineage を残す**: `adopted:` / `source_ids:` / `supersedes:` を adopt 時に書く（AuthMem: 統合は authority を落とす）。年齢条件付きの読み値と「dated」ラベルの前提
- **S5 削除でなく保管**: 退役 skill は `skills/.archive/`（`_gc_trash` の先例）へ。ledger には残るので同テーマは再提案されない。研究データは消えない

### 出口
- **X1 exposure 条件付き never-selected の読み値を packet に**: judged 露出 ≥ N（データから、~500 ≈ 1 週）で 0 選択の skill を退役候補として列挙（今日時点 7 件、うち 4 件は 1,845 露出で 0）。人間が gate で archive。挙動中立性が構成から言えるので効果測定を要しない。「統計は code、決定は人間」— LLM の提案段は不要（P9）
- **X2 supersede-on-adopt**（S1）: 入口と出口の結合
- **X3 catalog 容量の読み値**: selector 幻覚率が catalog 24→37 で 13 倍（08-08 読み）。§8 に「catalog N / 較正済み上限」を出す。cap ではなく容量計器。超過時は gate セッションが採用前に S2 の群を片付ける順序になる

### rule 層
- **R1 rules-distill / rules-stocktake を LLM 生成器としては退役し、使用証拠による昇格に置換**: family の any-of 選択率 ≥ ~80%（露出 ≥ N）を昇格候補とし、gate セッションで gemma に family の union を Practice/Rationale へ描画させ（既存 `merge_group` + `rules_distill_refine` の書式）、採用時に member skill を archive（観測 F の退役経路）。rule 数は少数に保つ（Instruction Stacking Collapse）。rules-stocktake は 2–5 rule に対する手動 one-off
- **R2（対案）** rules-distill の 20/48 切り捨てを直し既存 rule/憲法を渡す — 道具の前提（skill batch から LLM が rule を蒸留する）が公理の言い換えしか出さなかった事実は変わらない。低価値

## 5. 検証できること（実装前）
- E1: 過去 7 週の候補全文 + reviewer verdict + 名指し skill → retrieval recall@k、bundle 判定と人間ラベルの一致率
- S2: co-selection 群 vs 08-15 stocktake の grouping 結果 vs 今日の変奏 3 件（手で照合）
- X1: never-selected 7 件の exposure 推移（既に取れている）
- R1: family any-of 率の週次安定性（3 週）

## 6. 束ね方（shape）

- **Shape A「ゲートを計器化」（最小）**: E1 + X1 + S2 + X3 の読み値 + S4。新しい LLM 機構なし。既存の判定者が見る証拠を変えるだけ
- **Shape B「event-driven な代謝」**: A + S1 + S3 + R1 + S5。統合器 3 本は週次ゲートに溶ける — stocktake → (co-selection grouping + on-demand merge)、rules-distill → 昇格、rules-stocktake → 手動
- **Shape C「family 構造の store」**: B + store を canonical + variants に再編し selector の catalog を family 単位に。selector に触るので本タスクの外（horizon として記録）

順序（P4）: 計器（X1 / S2 / X3）→ E1 → S3 / S4 → S1 → R1 → E4 → E3
**（architect 後の改訂 → §9 を正とする）**

## 9. 推奨（architect を畳んだ後の形 — 「引き算 → 出口 → 語彙」の 3 スライス、1 週 1 変数）

**スライス 1: 削除だけ**（新しい code path ゼロ）
- ADR-0096 の事前登録 fallback を実行: `insight._worth_gate` の LLM 呼び出しを落とし、Decision 4–9（理由コード・tally・yield 行・marker 規則・replay ログ）は残す。surprise 計器（D10–12）も同 ADR の撤去条件に該当するので同時に落とす
- rules-distill / rules-stocktake を退役（CLI・prompt・marker・docs）
- skill-stocktake を**解体**（著者決定 2026-08-22、Q2 = 全部ばらす）: grouping（summary 証拠、recall 未測定）/ merge（union、過広 skill の実績）/ clean（反証済み）を落とし、`skill-stocktake` は **description 監査 + usage 読み値の report だけ**の command にする（LLM 呼び出しは description 監査の N 回のみ、≈115 → ≈57）。統合の代替は co-selection の読み値（S2）と「新を採って旧を倉庫へ」（X2）。`stocktake_skills.md` / `stocktake_merge.md` / `stocktake_clean.md` と merge / clean の staging 経路（`sources` 削除セマンティクスは `--archive-names` 側で引き継ぐ）を削除
- novelty gate は code 不変、目的の書き換え（ledger 係 + 安い pre-filter）と失効条件（inventory 肥大で chunking が再び壊れる）を ADR に明記

**スライス 2: 出口**
- S5 `skills/.archive/` への `mv`（`remove-skill` に `--archive` 既定、削除は明示 flag）。`adopt-staged` に `--archive-names FILE`（明示引数。reviewer 出力から自動導出しない — codex 4）
- X1 packet 新節「never-selected」— code-owned。**strict**（履歴全体で 0 選択、judged 露出 ≥ 600 = Slote 読みの最遅初選択 569 を超える床）を archive 候補として列挙（今日 3 件）、**dormant**（直近 14 日 0 選択だが過去に選択あり）は読み値のみ。`read_skill_selection_log` は 14 日窓なので strict には全履歴走査が要る（`never_selected_exposure` の窓引数を全期間にするか、別集計）。**同窓の fail-open 件数と `full_skill_tokens` vs NUM_CTX を併記**（codex 1: 中立性の例外経路を読み値に出す）。人間が gate で archive、`--reason` 必須（CREW: 書面の理由で just-in-case を止める）
- S4 `supersedes:` / `superseded_by:` を archive / 採用時に書く
- S2 co-selection family script（one-off、`scripts/`）。packet 常設は gate が 2 回使ってから
- rules 層の保守: `value_layer_due_check.py` に `rules` 節（件数 / mtime / `_check_rule_quality` の決定論検査）— LLM 生成器を退役しても所有者を残す（codex 2）

**スライス 3: 語彙と測定**
- E1-lite: `insight-recommendation.md` の verdict 文法を `adopt` / `adopt-superseding <skill>` / `reject: covered-by <skill>` / `reject: sibling-of <cand>` / `reject: vague` に拡張。既定は `reject: covered-by X`（古い方を残す — Wikipedia「新しい重複は本記事へ merge」、X の選択履歴と hub 位置を捨てない）、`adopt-superseding` は reviewer が「新が明確に優る」理由を書いたときだけ。`build_decision_packet.py` が parse し、(a) staged 全件との **1:1 対応**（欠落 / 重複 → `INSIGHT_REVIEW_INCOMPLETE`）、(b) 名指し store skill の**実在**（不在 = reviewer の幻覚として読み値に）を code で検査。語彙は**提案**で、mutation は gate の明示引数だけ（codex 4）
- **retrieval recall の offline 測定**（codex 3）: 過去 7 週の `logs/weekly-pipeline/<run>/insight-input.md`（候補全文）＋ `weekly-*-insight-review.md`（名指し）から、cosine top-k / 字面 top-k / 和集合の recall@k を測る script（read-only、著者が実行 — `logs/` は hook で Claude から読めない）。recall@5 が高ければ E1 の束を作り、低ければ作らない
- E4: ADR-0081 の description 監査を 57 件に 1 回回す（`skill-stocktake --describe-only` 相当の入口が無ければ足す）

**その後の判断点（読み値で決める、今は作らない）**
- offline recall 測定（スライス 3）で recall@5 が高く、かつ 08-22 型の miss（変奏 3 件採用 = 観測済み n=1）が再発したら → E1 の retrieval 束（cosine + 字面の和集合、≤30/prompt）
- rule 層への昇格（基準は既に満たす: any-of 0.72–0.81 × 4 窓）: **著者決定 A'** — family の共通の姿勢を gemma が `stocktake_merge_rules.md`（共有する核の合成）で Practice/Rationale に描画 → 人間ゲート。6 冊の skill は残す（固有の手順を持つ。「代表をそのまま移す」は 5 冊の手順を落とすので撤回）。選ばれなくなった冊は exit の読み値で退役
- 週次候補のうち ledger 既出テーマの比率が高止まりなら → `--weekly-insight` 月次化（plist 1 行、可逆。1 回の batch が 100–150 件になる副作用あり）
- Shape C（family 単位の catalog / SameCapRisk 型の retrieval 時 family 解決）は selector の問題として別 task

**捨てたもの**: E5 / X3 / R2 / S1 の merge 呼び出し / E3 の 3 値化 / S4 の `source_ids`

## 10. 観測ゲート（著者指示 2026-08-22: 暦の週でなく証拠量で次へ進む）

前提となる流量: judged 選択記録 ≈ **80–95 / 日**（4 セッション × ~20、直近 14 日）。≈ 600 / 週。
ADR-0056「値層の変数は一度に一つ」は**暦でなく観測量の単位**で守る: 変更ごとに (a) 期待する効果、(b) それを読める最小記録数、(c) 読み値が出たら次へ、を事前に書く。挙動中立な変更（データで効果ゼロが確定しているもの）は変数に数えない。

| 段 | 変更 | 挙動への影響 | 必要な観測 | 所要 |
|---|---|---|---|---|
| 1a | worth gate の LLM 呼び出し除去 | なし（46/46 promote = 除去しても候補集合は同じ） | 不要。tests + verify | 同日 |
| 1b | rules-distill / rules-stocktake 退役 | なし（schedule に無く、rules/ は 04-11 から不変） | 不要 | 同日 |
| 1c | clean 段削除 | なし（人間起動時のみ動く段） | 不要 | 同日 |
| 2a | strict never-selected 3 件を archive（露出 1,845–2,531、0 選択） | judged action では中立。例外は fail-open（40 日 0 件、現状 abstain） | `catalog_count`=54、archive 名が `catalog_names` / `selected` / `rejected_names` に出ない、fail-open 0 — **判定に ≥ 80 judged（≈ 1 日）** | 1 日 |
| 2b | `supersedes:` / `--archive-names` / packet の never-selected 節 | なし（読み値と配管） | 不要。次の packet で節が出ることを確認（土曜） | 同日 + 土曜 |
| 2c | co-selection family script | なし（read-only） | 不要 | 同日 |
| 3a | reviewer verdict 語彙 + packet の 1:1 / 実在検査 | なし（reviewer は advisory） | **offline replay**: 08-21 の staged 46 件（`logs/weekly-pipeline/<run>/insight-input.md`）に新 prompt を headless で当て、46/46 section・名指し skill の実在率を読む — 同日。本番は次の土曜 run | 同日 + 土曜 |
| 3b | E1 retrieval 束の要否 | — | offline recall 測定（過去 7 週の候補全文 + 名指し）— 同日 | 同日 |
| 4 | rule 昇格の判断（「制約」family） | あり（常時注入が 1 本増え、member が catalog から消える） | 基準「any-of ≥ 0.75 が互いに素な ≥ 500 judged の窓 2 つ以上」— **既に満たす**: 07-25〜 の 4 窓で 0.78 / 0.74 / 0.72 / 0.81（deconstruct family も 0.83 / 0.85 / 0.80 / 0.72）。実行後の観測: 昇格した rule の member 名が `selected` から消え、selected_count p50 が下がる（6 → 5 前後）— **≥ 100 judged（1–2 日）** | 判断は今日、観測 1–2 日 |
| 5 | co-selection 両向き対の merge / supersede（3 組） | あり（catalog が変わる） | 対ごとに 1 つずつ。直接の読み: その名前の語形幻覚が消える（例: `structural-constraint-mapping-scm` 系の幻覚 32/606 ≈ 5%/record → 100 judged で 0 なら p ≈ 0.006）— **≥ 100 judged（1–2 日）/ 対** | 1–2 日 / 対 |
| 6 | 新規採用 9 件の never-selected 判定 | — | 露出 ≥ 600（Slote 床）— 採用から ≈ 1 週 | 暦ではなく露出数で自動 |

暦に縛られるのは**土曜の無人 chain（reviewer の本番 run）だけ**。それも 3a の offline replay で同日に検証できるので、実装は土曜を待たずに進められる。
週次 packet の gate 記録（`pipeline-metrics.jsonl` の `phase:"gate"`）は残るが、判断の単位は「記録数」にする。

### 今日の読み値で追加で分かったこと（2026-08-22）
- selector の**幻覚率**（rejected_names 非空 / judged）: catalog 24 → 0.6%、37 → 7.7%、45 → **20.2%**、48–57 → **18.0%**（109/606）。ほぼ全部が実在名の語形変化（`suspending-` vs `suspend-`、`identifying-` vs `identify-`、`structuring-constraint-mapping-scm` 等）。**catalog の健康度の outcome 読み値はこれ**（生態学の類推: 個体数でなく植生で目標を決める）。出口と merge の効果はこの数字で読む
- 語形の不一致（gerund / 命令形の混在）は catalog 側の規約で消せる（adopt 時に動詞形を 1 つに正規化）。rename は露出計数を name で切るので、archive / merge と同時に動かさない（別変数）

**変更対象（ファイル）**
- `src/contemplative_agent/core/insight.py`（worth gate 呼び出し除去、surprise 除去）、`core/insight_surprise.py`（削除）、`config/prompts/insight_worth.md`（削除）、`tests/test_insight_worth.py` / `test_insight_chaos.py`（該当 class 削除）
- `core/rules_distill.py` / `config/prompts/rules_distill*.md` / `stocktake_rules.md` / `stocktake_merge_rules.md` / `cli/memory_cmds.py` / `cli/stocktake_cmd.py`（rules 経路）/ tests
- `core/stocktake.py` + `cli/stocktake_cmd.py`（clean 段）/ `config/prompts/stocktake_clean.md` / tests
- `cli/adopt.py`（archive、supersedes）、`scripts/build_decision_packet.py`（verdict 文法 + never-selected 節）、`config/prompts/insight-recommendation.md`、`scripts/weekly-pipeline.sh`（grep 条件）、`.claude/skills/weekly-gate/SKILL.md`
- `scripts/coselection_families.py`（新規、read-only）
- docs: 新 ADR（統合器 3 本の再編 — 0016 / 0048 / 0096 の supersede 注記）、`docs/CODEMAPS/architecture.md` Data Flow、`docs/CONFIGURATION.md` prompt 数、`docs/CYCLES.md`

**検証**
- 各スライスで `.claude/verify.sh`、`uv run pytest`、`uv run lint-imports`
- スライス 1: `insight --dry-run` で yield 行が worth 呼び出しなしで出る / `rules-distill` が CLI から消えている / stocktake の call 数が ≈1+G+N
- スライス 2: gate セッションで X1 節の 7 件を実際に archive し、翌週の selector catalog から消えたことを選択ログの `catalog_count` で確認
- スライス 3: 翌週 packet の verdict 文法が parse され、名指し skill の実在照合が読み値に出る

## 7. 採らない方向（理由つき）
- embedding 閾値で抑止（ADR-0074 較正: 分離なし）/ 数値キャップ / Claude が merge 本文を書く（P1）/ daily capsule 層（07-18 alt A、ADR-0060 の平坦化）/ 全自動 adopt（ADR-0085 却下 3）

## 8. 外部意見

### architect（fresh-context、build-or-not）— 要旨と採否

見出し: 「**build はほぼ引き算＋field 1 つ＋list 1 つ**。順序は 反証済みの削除 → 出口 → 既に存在する判断の捕捉。計器は最後」。実効判定者（reviewer）は既に coverage 判断を散文で出しており、`weekly-pipeline.sh:990` の `grep -q "RECOMMEND:"` がそれを捨てている。

| 機構 | architect | 採否 | 理由 |
|---|---|---|---|
| E1 | Build smaller — verdict 語彙だけ。retrieval は非分離 corpus で未証明、reviewer の Read を固定 k と交換するのは損 | **採る（段階化）**: 語彙拡張を先に。reviewer が名指した covering skill が実在し正しいかを code で照合する読み値を 2 週取り、取りこぼしが観測されたら retrieval 束を足す | 判断は既に存在する。証拠の補強は観測してから（P5） |
| E2 | Don't wait — ADR-0096 の事前登録 fallback を今実行（0084 v4 40/40 → offline 18/18 → prod 46/46 の 3 連続） | **採る** | 事前登録した反証条件を「もう 2 run」で動かすのは goalpost 移動 |
| E3 | reframe のみ。安い pre-filter（週 ~13 抽出を節約）＋ ledger 書き手。3 値化は決定に繋がらない研究読み | **採る**（code 変更なし、docstring / ADR の目的書き換え）。3 値化は捨てる | 397 件の inventory が chunking を再び壊す失効条件を明記 |
| E4 | Not yet — ADR-0081 の description 監査は実装済み未実行。先に 57 件に一度回す | **採る**（gate セッションで `--describe-only` 相当を 1 回） | 既存の道具を動かしてから足す |
| E5 | Don't build — ADR-0074 の窓シミュレーションで 32/32 が再出現、再出現条件は何も濾さない | **捨てる** | 反証が既にある |
| S1 | Build smaller = X2 だけ。union merge は ADR-0048 が 10 トリガー skill を作った機構 | **採る**: `adopt-superseding X` = 採用＋archive、LLM なし。`adopt-revising`（merge 呼び出し）は捨てる | 統合 LLM を再発明しない |
| S2 | Build — one-off script。packet 常設は gate が 2 回使ってから | **採る** | 唯一の新情報、code-only |
| S3 | Build（削除） | **採る** | Inward dissolution の教科書例 |
| S4 | `supersedes:` だけ。`source_ids` は audit.jsonl の複製、採用日は filename にある | **採る** | 読み手のない field を足さない |
| S5 | Build — `mv` 1 つ。5 ヶ月で 6 件しか消えていないのは不可逆な出口が使われない証拠 | **採る** | — |
| X1 | Build — 構成から挙動中立が言える唯一の退役信号 | **採る** | — |
| X2 | Build | **採る** | — |
| X3 | Don't — 24→37 の幻覚跳ねは T-SKILLNAME-BACKFILL と交絡、較正済み上限は z-normalization の罠 | **捨てる** | `report --skill-selection` の幻覚率行で足りる |
| R1 | Don't build as mechanism — 生成器 3 本を 4 本目で置き換える形。S2 の family が 3 週安定したら人間が gate で rule を手書きし member を archive | **半分採る**: 機構は作らない。ただし「人間が手書き」は ADR-0050（観測 > 操舵）と衝突する — rule 層は agent 自身の語で書かれた B 層。代替: **family の代表 skill 本文をそのまま `rules/` へ移す**（LLM 書き換えなし、agent の言葉のまま）か、従来どおり gemma に描画させる。**ここは著者判断** | 操舵の回避 |
| R2 | Don't | **捨てる** | — |

統合器 3 本の結論（architect）: rules-stocktake = 退役（代替なし、2 文書に grouping は theater）。rules-distill = 退役（代替は上記 R1 の扱い）。skill-stocktake = **溶解**: grouping → S2、merge → X2、clean → 削除、usage → X1、**description 監査だけ `--describe-only` で残す**（~115 コール → ~N）。

`core/stocktake.py:126-128`「退役は LLM 提案＋人間判断、数値 auto-threshold にしない」: 後半（数値で自動退役しない）は生きている — X1 は列挙を数値で、決定を人間で、という ADR-0071 / 0096 D10 の分業そのもの。前半（LLM 提案）は programmatic な信号が無かった時代の既定 → supersede 候補。

architect の追加指摘（packet に無かったもの）:
1. **入力量を下げる候補が 1 つも無い** — `--weekly-insight` を月次にするのは plist 1 行で可逆。**私の評価**: 半分同意。週次は同じ ~30 standing theme を毎週再提案する（4 週で 4 回）。月次なら 1 回。ただし窓が伸びると cluster 数が増える（07-18 の 9 日窓で 117 clusters / 106 staged、ADR-0074 は 14 日で demoted 尾 47 を理由に 7 日を選んだ）ので、1 回の batch は 100–150 件になり listwise 位置バイアスを踏む。月次化は「総量」を下げ「1 回の量」を上げる。E3 の reframe と S2 の後に、読み値（週次候補のうち ledger 既出テーマの比率）で判断する
2. **ADR-0096 の surprise 計器（D10–12）に名指しの消費者がいない** — reviewer prompt は surprise に触れていない。同 ADR が事前約束した撤去条件に該当。→ 採る（E2 と同じ commit で）
3. marketplace 規模（7,326 / 34k）の文献を 57 件の store の先例にするのは Golden Hammer → 同意。§1.6 は「出口が無いと肥大する」の方向だけ借り、数値は借りない

### codex --plan（cross-model premise challenge、1 回）— VERDICT: premise-hole

repo 由来の未検証データとして読み、各 finding を code で照合した上で採否を 1 行ずつ:

1. **REFUTE「never-selected の退役は構成から挙動中立」** — `never_selected_exposure` は judged 記録だけを数え、fail-open（LLM 失敗 / template 欠落 / 例外）では全 skill 注入に戻るので「一度も注入されていない」とは言えない。→ **採る（文言を弱める）**。照合結果: 07-13 以降 3,716 記録で fail-open **0 件**、かつ現 catalog の `full_skill_tokens` = 38,867 > NUM_CTX 32,768 なので fail-open 経路は今日**注入でなく abstain**（ADR-0081 amendment）。7 件 archive しても ~34k で同じ。正しい主張: 「judged な全 action で中立。唯一の例外経路は 40 日間 0 回で、現状その経路は注入しない」。X1 の読み値に fail-open 件数を併記する（codex の ALTERNATIVE の前半を採る）
2. **MISSING「rules-distill / rules-stocktake 退役後、既存 rule の保守所有者が不在」** — → **採る**。LLM grouping / merge は退役するが、`_check_rule_quality`（決定論: Practice / Rationale の存在、≥200 chars）と件数・mtime を ADR-0091 型の read-only 読み値として packet §8 に残す（`value_layer_due_check.py` に `rules` 節）。所有者 = 土曜ゲート
3. **MISSING「reviewer の false negative（重複を見落として adopt）を 2 週で観測する観測器が無い」** — → **採る**。「取りこぼしが観測されたら retrieval 束」は観測器なしの条件だった。置換: (a) 08-22 の変奏 3 件採用を最初の観測済み miss と数える（n=1）、(b) スライス 3 で **過去 7 週の候補全文（`logs/weekly-pipeline/<run>/insight-input.md`）＋ review.md の名指し**から retrieval recall@k を offline で測る script を書き、recall@5 が高ければ E1 の束を足し、低ければ束は作らない。判断を読み値に縛る
4. **MISSING「verdict 語彙を副作用（adopt+archive）に繋ぐには完全性ゲートが弱い」** — `grep -q "RECOMMEND:"` 1 個で成功、packet builder は heading 数を数えるだけで staged との 1:1 対応・重複・欠落・対象の一意性を検証しない。→ **採る**。reviewer の語彙は**提案**に留め、mutation は gate セッションの `adopt-staged --adopt-names FILE --archive-names FILE` の**明示引数**だけが起こす（reviewer 出力から自動導出しない）。加えて packet builder に 1:1 対応検査（`INSIGHT_REVIEW_INCOMPLETE` 理由コード）と名指し skill の実在検査を入れる
5. **ALTERNATIVE「X1 は即 archive でなく `disabled-candidate` として記録」** — → **後半は捨てる**。archive は可逆（S5）で、例外経路は現状 abstain なので、状態を 1 つ増やすより archive の方が単純。前半（fail-open 併記）は 1 で採った

再設計の必要（re-plan）: **なし**。premise-hole は X1 の文言と、語彙→mutation の配線の強さに関するもので、3 スライスの順序と中身は保つ。§9 を上記 1–4 で更新済みとして読む
