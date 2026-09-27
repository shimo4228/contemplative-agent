# Plan: distill salience×utility read-only 計器（K）+ wiki-harvest skill 修正

## Deliverables

1. **K 計器**（CA repo コード）— 蓄積 pattern の salience×utility を撮る read-only instrument。
2. **wiki-harvest skill 修正**（`~/.claude/skills/wiki-harvest/SKILL.md`）— J の死から出た 2 構造欠陥を潰す。
3. **ledger 仕上げ**（CA `.notes/wiki-harvest/ledger.md`、gitignored）— 候補 E/K の訂正反映。
4. **plan の Codex prompt-driven レビュー**（下記フロー）。

---

## Context（なぜ作るか）

CA の distill（episode→knowledge）は **ungated な自動処理**（`core/distill.py:9-11,144-147`: *"there is no ingest-time noise gate"*）。旧 ingest-time noise gate は **ADR-0026→0027→0060** の系譜で撤去され、noise は今 **query 時に view centroid で濾す**（ADR-0031）方式に移った。人間承認ゲート（ADR-0012）は identity/constitution 書き込みのみ。

蓄積 pattern は**行動時に注入されない**（`adapters/` は knowledge を読まない）。消費者は `core/distill.py:266` `find_by_view("self_reflection")`→identity 蒸留 と `core/constitution.py:86` `find_by_view("constitutional")`→amend の 2 つ。つまり pattern は**価値層蒸留の substrate**。

**問題**: distill が ungated で query 時濾過に移った以上、蒸留され蓄積される pattern が「高 salience（新規）・高 utility（消費 view が欲する）の signal」なのか「低 salience の冗長エコー」なのかは未観測。ADR-0027 は salience-as-surprise を提案しつつ ADR-0060 で gate 自体を落としたので、「query 時濾過は効いているか／後継 gate は要るか」は**空いた問い**。memory-pollution 研究と D-MEM（arXiv:2603.14597、Surprise×Utility）が、ungated 蓄積は下流（identity/constitution 蒸留）を静かに劣化させうると外部から補強する。

**K の目的**: 蓄積 pattern の salience×utility 分布を **read-only 計器**で撮り、distill が signal を promote しているか冗長エコーを溜めているかを可視化する。読みが「低 salience エコー偏重」を示せば、旧 ADR-0026/0027 gate の後継（knowledge 層 gate）を作る根拠になる。その後継 gate は**自動層に置くので ADR-0012 の人間承認境界に触れない**。

**成果**: 計器の読み値（quadrant composition + 3 点較正）。**gate は作らない。実装判断は読みを見てから別ステップ**（signal-first: 読みが action を変えるから建てる／答えが出たら撤去も検討）。

## 確定事実（コードで照合済み — wiki 要約は drift していたため一次で確認）

- pattern は行動時未注入（`adapters/` に knowledge 読み込み無し）→ 旧候補 J（行動 A/B）は無効・却下済み。
- knowledge 昇格は自動（`core/distill.py` に noise gate 無し）。人間承認は identity/constitution のみ。
- **語彙訂正（Codex P2）**: ADR-0027 salience = `1 − max cosine(episode, **view centroid**)` は本計器の novelty 軸（最近傍 **pattern** 距離）と**別物**。本計器は ADR-0027 salience を再利用しない — 軸名は正直に `novelty`（corpus 冗長度）と `view_affinity` にする。ADR-0027 salience は関連する別メトリクスとして脚注参照に留める（後日 all-view 版を足す余地あり）。

---

## Deliverable 1: K 計器（設計 — 実装調査で scope 縮小、Option A 確定）

**実装調査の発見**: `core/view_metrics.py` は既に K の 2 軸の **marginal を両方出している** —
`compute_view_supply`（消費 view threshold 通過数 = affinity marginal）と `compute_diversity`
（pairwise cosine mean = novelty-ish marginal、docstring に *echo-chamber signature* と明記）。
`_embedding_of` / `nearest_view` / per-view threshold も既存。→ **K の真の新規性は per-pattern の
joint（低novelty×below-threshold の pollution セル）だけ**。新規モジュールをゼロから作る前提は過大だった。

**方針（Option A、ユーザー確定）**: 新規モジュール・新規 flag を作らず、`core/view_metrics.py` に
**3 つ目の instrument** として per-pattern joint を薄く足す（~60 行）。既存 `_embedding_of` /
`pattern_dedup._best_existing_sim` / per-view threshold / formatter idiom を再利用。marginal は既存のまま。
出力は既存 `report --patterns`（`format_pattern_report`）に 1 ブロック追加（新 flag なし）。
- 語彙: `novelty`（corpus 冗長度 = 最近傍 pattern 距離）/ `view_affinity`（消費 view threshold 適格性）。
  ADR-0027 salience（view centroid 版）とは別物・誤アンカーしない。D-MEM は external convergent reference。

### 算出（live pattern ごと、degrade-don't-raise）
- **novelty** = `1 − max(0, best_sim)`。pool = `_live_embedded(store.get_live_patterns())`（**p 自身を除外**）を `_best_existing_sim(emb_p, pool)` に渡す（`core/pattern_dedup.py:107,119` + `embeddings.cosine` 再利用）。
  - **embedding 検証（Codex P2）**: pool 構築前に各行を `view_metrics._embedding_of`（欠損/ragged/非数値 → None ガード）で pre-filter する。`_live_embedded` の生 `np.asarray(float32)` に ragged 行を渡すと **skip 前に raise** する／dim 不一致は cosine 0 → novelty 1.0 の偽陽性、を両方防ぐ。
  - **no-neighbor（Codex P2）**: 有効 pool が空（単一 pattern・全 skip）で `_best_existing_sim` が `-1` を返す時は **novelty=1.0 にせず `unscored`** に分類し、unscored 件数を reading に出す。
- **view_affinity** = 消費 view（`CONSUMED_VIEWS=("self_reflection","constitutional")`）への**適格性**。生 cosine の max ではなく、各 view の threshold（self_reflection 0.66 / constitutional 0.55）を**超えているか**で判定（`find_by_view` が実際に consumer に供給する条件 = threshold[+top_k]。生 max cosine は top_k 外や低 threshold view を過大評価する）。閾値超え無し = `below_threshold`。**取得不能（`nearest_view`→None: Ollama 落ち/view 欠落/centroid embed 失敗）は `0` にせず `unavailable` として別集計**（Codex P1: unavailable と真の低 affinity を混同しない。coverage を報告）。
- メモリガード（Codex P2）: novelty の max-NN は per-pattern O(N)・全体 O(N²)。現行 corpus は ~100 patterns（`thresholds.py` evidence: 97 patterns）なので**厳密計算で問題なし**。**サンプリングしない**（max をサンプルすると系統的に過小→novelty を inflate）。高 N（例 >2000）では**計器を skip して coverage note を出す**（近似で嘘の分布を出さない）。

### 出力（frozen DTO + formatter、view_metrics.py に追加）
- `@dataclass(frozen=True) NoveltyJoint`: 4 象限セル数（redundant×below=pollution-prone / redundant×passing / distinct×below / distinct×passing）、coverage（total / no_embedding / unscored_novelty / affinity_available）、novelty_threshold(=1−SIM_UPDATE)。unscored・no_embedding・affinity 不能は象限に混ぜず coverage で別出し（Codex P1/P2）。
- `compute_novelty_joint(patterns, registry, views=CONSUMED_VIEWS) -> NoveltyJoint`。`format_novelty_joint(joint) -> List[str]`（既存 `format_view_supply`/`format_diversity` と同 idiom、List[str]）。`instrument_lines` に registry 有り時のみ追加（view supply と同様 affinity に registry 必須）。→ `format_pattern_report` 経由で `report --patterns` に自動で出る。
- novelty 帯（2 値）: `redundant` = max_sim ≥ SIM_UPDATE(0.80) → novelty ≤ 0.20 / `distinct` = else。affinity（2 値）: `passing` = いずれかの消費 view で cosine ≥ その view の threshold / `below`。
- ADR-0071 契約 docstring 明記（既存モジュールの observability-only 契約を継承・拡張）。

### CLI 露出（新 flag なし）
- 新 flag も新モジュールも作らない。`format_pattern_report` に joint ブロックが乗るので既存 `report --patterns`（`cli/session_cmds.py:142` の branch）でそのまま出力される。CLI 変更は原則不要（`report --patterns` の出力が1ブロック増えるだけ）。

### read-only 不変条件（CRITICAL — K の存在意義そのもの）
- ADR-0071 契約を docstring 明記: gate / ranking / promotion / retrieval に一切配線しない。view_affinity/novelty を *読み値* として使うのは可、判断経路に繋ぐと契約違反。
- **fault surface（Codex P1 訂正）**: novelty は蓄積 embedding + cosine で外部 I/O 無し。だが **view_affinity は `get_centroid` が消費 view seed を遅延 Ollama embed する**（registry 内で view 数ぶんキャッシュ、hot path でないが Ollama 呼び出しは**発生する**）→ 「外部 I/O 皆無」は誤り。chaos-TDD は「Ollama 不達 → view_affinity を `unavailable` に degrade（0 でなく）」を決定論テストで主張。スケジュール窓（JST 0/6/12/18）懸念は軽微（seed embed は view 数ぶん・キャッシュ済み）だが**皆無ではない** — 手動起動時は窓外を選ぶ。

---

## Deliverable 2: wiki-harvest skill 修正（`~/.claude/skills/wiki-harvest/SKILL.md`）

J の死が炙り出した 2 つの構造欠陥（今セッションで加えた Step 3.5 triage の続き）:

1. **Step 2 抽出表に ⑤ 行を追加** — 現状 ①OQ / ②矛盾 / ③外部出典 / ④関連概念 からしか拾わず、実装・計測 signal が眠る `## 主要な主張` を素通りする（K/M はそこから出た）。追加:
   `| ⑤ | ## 主要な主張 の実装・計測に落ちる知見 | prototype 候補（gate/test/計器） | → Step 3.5 triage |`
2. **Step 3.5 に surface-existence check を追加** — J は「外部研究が前提とする surface（行動時 retrieval）を CA が持つか照合せず intake」した失敗。triage 判定に 1 問追加: 「この研究が前提とする surface（retrieval 経路・gate・層）を repo は**コードで**持つか？ wiki 要約でなく実コードで照合（wiki は repo 内部についても drift する）。無ければ dismiss（外部 framing の空 import）」。

## Deliverable 3: ledger 仕上げ（`.notes/wiki-harvest/ledger.md`）

- 候補 E 訂正: 「自動ゲート vs 人間承認の構造的対立」は誤り。knowledge 層は既に自動なので D-MEM 型 auto-gate と*対立しない*（対立は identity 層に auto-gate を提案した場合のみ）。
- 候補 K 精緻化: 軸を `novelty`（corpus 冗長度）/`view_affinity` と正しく命名（**ADR-0027 salience は view centroid 版で別物**の脚注付き）。「approval 対立回避のため read-only 必須」の caveat を削除し、正しい理由（分布を見てから gate する sequencing／後継 gate は knowledge 層なので ADR-0012 と両立）に差し替え。

---

## 実行順（chain）

種別: `feat`（新規計器モジュール）+ skill/docs 修正。

1. **Deliverable 2/3（skill・ledger 修正）を先に** — 低リスク・可逆、J 実証の落とし込み。
2. **Deliverable 1（K 計器）を TDD** — テスト先行（salience/utility 算出・quadrant binning・degrade・read-only mtime 不変）→ 最小実装 → green。
3. **Review**（並列）: python-reviewer + （入力処理境界を触るため）security-reviewer は限定的、+ codex-review は実装 diff に対して実行。
4. **Verify**: build / pyright / ruff / pytest（cov≥80）/ secret scan / `lint-imports`（core←cli 方向）/ git status。
5. commit（main 直・push、branch/PR は持ち込まない）。

## Codex レビュー（planning.md rule との整合）

- **完了**: 本 plan を codex-review prompt-driven で cross-model レビュー済み。verdict HIGH（CRITICAL なし・read-only/no-gate 境界は保たれると確認）。6 findings（P1×1: get_centroid Ollama I/O + None→0 混同 / P2×5: novelty≠ADR-0027 salience・top_k 適格性・ragged embedding raise・no-neighbor 偽1.0・大 pool サンプリング bias）は全て real と判定し**上の設計に反映済み**。
- **実装後**: Deliverable 1 の diff に対し codex-review を通常起動（`planning.md` の「diff review を plan review で置き換えない」を維持）。

## Verification（end-to-end）

- **単体**: 既知 cosine の tiny fixture で novelty=1−maxNN・view_affinity=threshold 適格性を検証。quadrant binning 境界。エッジ（Codex 指摘を回帰固定）:
  - ragged/非数値 embedding 行 → pool 構築で raise せず skip+warning。
  - 単一 pattern / 全 skip（空 pool）→ novelty=`unscored`（1.0 でない）、unscored 件数が出る。
  - `nearest_view`→None（Ollama 不達 模擬）→ view_affinity=`unavailable`（0 でない）、coverage に計上。
  - dim 不一致 → cosine 0 が novelty 1.0 の偽陽性を生まないこと。
- **read-only 保証**: `report --patterns` 実行前後で `knowledge.json` の mtime 不変・書き込み無しを assert。
- **E2E**: 実 knowledge store に `contemplative-agent report --patterns` を 1 回実行し、既存 marginal に加え新 joint ブロック（quadrant + coverage）が出ること・「redundant×below = pollution-prone 質量」が読めること・no_embedding/unscored が別出しされることを目視。
- **import ゲート**: `uv run lint-imports`（core が cli を import しない）。

## Non-goals

- gate を作らない（salience/utility を*計算* ≠ *弾く*）。knowledge store に書き込まない。行動パスを変えない（J は死）。identity/constitution の人間承認境界に触れない。`view_metrics` の observability-only 契約を越えない。
