# Plan — 候補検索の計測 + 後続タスクの RFC 化（wiki は閉じる）

## Context

2026-09-03〜04 の設計議論（`/mondo`、`.notes/handoff-rfc-0017-wiki-form-2026-09-03.md` 起点）の決着:

- **wiki 散文形は閉じる。** gemma smoke（8/25–27）は 9 ページ全部が一般論で、Proposer dry-run
  （本セッション）の patch も一般論同士の糊付けだった。opus アーム（本セッション、同 3 日・同形、
  $8.4）は具体的で行動を変えるページと patch を出した — **平坦化は形でなく gemma**。本番は
  gemma 固定（ADR-0069）なので wiki は成立しない。著者判断 2026-09-04: 閉じる、RFC-0017 / 0022 は
  `obsoleted`。
- **次に解くのは insight 段の 2 問題**: (1) 同じような skill が大量に提案される（boundary 族 7 本、
  deconstructing-* 4 本、detecting-* 4 本）(2) 珍しい skill が抽出されない（singleton は surprise が
  読む前にクラスタ床で落ちる）。両方とも**既存 skill 群からの距離**の両端で、1 本の候補検索
  （BM25 + nomic）で読める。
- **先に計測、型の話は後。** 著者指示「BM25 と embedding でクラスタがどう変わるかをすぐテスト、
  確定してから skill の中身へ」。
- 抽出の型（Problem / Solution 固定、「複数を 1 つに溶かせ」「普遍的な指示に訳せ」）は平坦化を
  指示している。選択 pass 1 は `name — description` しか読まず、本文は生成時に自由文として注入
  されるので、機械契約は frontmatter 2 欄のみ（`core/skill_selection.py:196`、stocktake の
  `## Problem` / `## Solution` 検査 `core/stocktake.py:165` だけが様式依存）。

成果物: 計測の読み値（docs/evidence）、RFC 3 本の起票 + 2 本の終端化 + 1 本の追記、opus 結果の凍結、
memory 更新。**実装（gate の置換・型の変更・wiki 退役）はこのプランでは行わない。**

## Part A — 候補検索の計測（read-only、このプランで実行）

Ollama 埋め込みは skill 57 本 + 候補数百件で軽いが、**JST 0 / 6 / 12 / 18 時の 30 分は避ける**。

### A1. `scripts/retrieval_recall_measure.py` を初めて実走（ADR-0097 D6、コード変更なし）

一度も走っていない計器（RFC-0017 L539）。ground truth = 週次レビューの reject が名指しした store skill、
query = staged 台帳の候補。データは揃っている（`reports/analysis/weekly-*-insight-review.md` 3 本、
`logs/insight-staged.jsonl` 481 行）。

```
uv run python scripts/retrieval_recall_measure.py \
  --review-dir "$HOME/.config/moltbook/reports/analysis" \
  --candidates "$HOME/.config/moltbook/logs/insight-staged.jsonl" \
  --skills-dir "$HOME/.config/moltbook/skills" \
  --arm lexical --arm cosine --arm union [--rrf-k 60|10|5]
```

- **labelled pair 数を先に読む**（< 30 は決定入力にしない — script 自身が言う）
- レビュー md は外部本文を引用するので **script に読ませ、自分では Read しない**（CLAUDE.md の境界）
- 出力 JSON を `docs/evidence/rfc-0023/retrieval-recall-20260904.json` に凍結（rrf-k 3 通り）

### A2. `bm25` アームを同 script に足す（小さな追加）

- 純 Python Okapi BM25（k1=1.2, b=0.75、`_normalize` の whitespace token）。同じ corpus・同じ
  `MAX_TEXT_CHARS` 切り詰め・同じ `_rank` / `_no_spread` 規律。`ARMS` に `bm25` を追加、
  `union` は lexical + cosine のまま（定義を変えない）。必要なら `union-bm25`（bm25 + cosine の RRF）
- テスト: `tests/test_retrieval_recall_measure.py` の synthetic fixture 様式に bm25 の 2〜3 ケース
- A1 を bm25 込みで再実行し同じ evidence に上書き

### A3. 今のクラスタに対する dry-run（新規 read-only script）

`scripts/novelty_retrieval_dry_run.py`（一発計器、ADR-0075 の 2026-08-29 追補により監査ログ不要、
結果を evidence へ凍結）:

1. `KnowledgeStore.load()`（`core/memory.py:133`）→ `gated != True` の live 行
2. `core/clustering.cluster_patterns(threshold=CLUSTER_THRESHOLD_INSIGHT=0.70, min_size=3, max_size=10)`
   で insight と同じクラスタ + singleton（`insight._build_cluster_batches` は singleton を捨てるので
   `cluster_patterns` を直接呼ぶ）
3. skill corpus = `skills/*.md` の `name — description`（`text_utils.skill_theme`）と全文の 2 表現。
   nomic は `core/embeddings.embed_texts`、BM25 は A2 と同じ関数（`scripts/` 内で import）
4. 各クラスタ（query = 行テキスト連結）と各 singleton について top-3 skill とスコア（cosine / bm25 / RRF）
5. 出力: (a) クラスタごとの最近傍表 (b) top-1 スコアの分布（percentile）(c) 候補閾値 3 点で
   「被り」と読める率 (d) singleton のうち top-1 が分布の下位にある件数 = 希少レーンの母集団
   (e) 比較用に `logs/insight-novelty.jsonl`（自己書き込み、17 records）の `covered` 率
   — cluster id は run を跨がないので**率だけ**比べる
6. `docs/evidence/rfc-0023/novelty-retrieval-dry-run-20260904.json`

### A4. 読み

- A1/A2: `union`（または bm25 系）の recall@5 が ≥ 0.9 かつ pair ≥ 30 → ADR-0097 Review-when
  第 2 腕が発火 = 検索は reviewer が名指す skill を見つけられる → gate の置換は成立
- A3: boundary 族などの既知の重複が top-1 で互いを引くか、希少レーンの母集団が何件か
- 読み値を RFC-0023 の Status に書き、`draft → accepted`（pair < 30 なら `blocked` + 3 行）

## Part B — RFC の起票と状態更新（skill: `rfc-writer` 規約）

採番: 現在の最大 0022 → **0023 / 0024 / 0025**。`rfcs/README.md` に index 行 3 本。
`claims.py spawn RFC-00NN --origin idea --parent RFC-0017`。公開文なので機微はリンク先へ。

### RFC-0023 — insight の novelty gate を候補検索（BM25 + nomic）に置き換え、希少レーンを持つ

- Summary（1 行目 = 90 字要約）: 既存 skill 群への hybrid 検索で、クラスタの被り判定を LLM 40k
  プロンプトから code の候補生成 + 小さな LLM 判定へ縮め、遠い singleton を保留に溜める
- Motivation: 同型 skill の量産（名前一覧の族）/ 希少 skill の不抽出（床の前で消える）/
  novelty gate の fail-open 履歴（`insight_novelty.py` 2026-07-18）
- Guide-level: 検索は候補生成、判定は LLM（ADR-0074 が code 閾値の embedding 抑制を反証済み — 閾値で
  捨てない）。既知テーマ 442 本を全部見せる代わりに top-k だけ見せる。希少レーン: top-1 が分布下位の
  singleton を保留台帳に溜め、週次で保留同士を再クラスタし床（3）を越えたら抽出 — 床は下げない
  （one-run-not-evidence）。surprise（RFC-0016）は read-only のまま（母集団が違う: 直近行からの距離）
- Reference-level: 触るもの `core/insight_novelty.py`（既知テーマの供給を top-k に）、
  `core/insight.py`（singleton の保留経路）、`config/prompts/insight_novelty*.md`、保留台帳の JSONL
  （append-only、ADR-0075）。BM25 は依存追加なし（純 Python）。**A の読み値が入場条件**
- review-when: recall@5 < 0.9（検索が reviewer の判断を再現しない）/ RFC-0015 の幻覚率が catalog
  サイズと無相関と分かる
- state: `draft 2026-09-04` → A4 で accepted

### RFC-0024 — skill 抽出の型を解く（本文自由記述、frontmatter は別コール）

- Summary: 抽出を 本文 → description → name の 3 コールに分け、本文は自由記述、長さは prompt の
  目安 + 保存時の**拒否**（切断しない、理由コード）、Problem / Solution 様式と「複数を溶かせ」
  「普遍化せよ」の指示を外す
- Motivation: 機械契約は frontmatter 2 欄のみ（`skill_selection.py:196` は `name — description`、
  本文は生成時に自由文注入）。When to Use を読む code は無い。様式強制は gemma に効かず
  （禁止語 fluid-/dynamic- が store に残存）、様式が平坦化を指示している
- Guide-level: description は行からでなく本文から書く（stocktake の description 忠実度監査の先取り、
  llm-pipeline-layering の順序則）。stocktake の `## Problem` / `## Solution` 検査は撤去
- 順序: RFC-0023 の読みの後（著者指示）。合成を残すか行の引用（few-shot）にするかは Unresolved
- review-when: 本番モデルが様式を守れる世代に替わる（分割が不要になる）
- state: `draft 2026-09-04`

### RFC-0025 — wiki 機構の退役（RFC-0017 D4〜D10 / RFC-0022 の閉鎖）

- Summary: WikiSkill 形の Maintainer / Proposer / replay / `install-schedule --wiki-maintain` を退役。
  根拠 = gemma smoke の平坦化 + Proposer dry-run + opus アームの対照（形は正しいが本番モデルで回らない）
- Reference-level: `core/wiki*.py`（5 本）、`cli/wiki_cmds.py`、`cli/schedule.py` の `--wiki-maintain`、
  `config/prompts/wiki_*.md`（4 本）、`scripts/wiki_replay.py`、`testing/claude_cli.py`（唯一の cloud
  到達路。退役で production から cloud 経路が消える = セキュリティ層の absence 回復）、対応 tests、
  CODEMAPS（architecture Data Flow / moltbook-agent CLI 表）、CLAUDE.md CLI 節、
  `.claude/skills/llm-pipeline-layering` の 3 則（「サンプルでなく batch」→ 「1 件ずつ足す。まとめる
  動詞は別コール・別判定者。散文の書き直しは小型モデルに持たせない」）。残置 worktree
  `.claude/worktrees/rfc-0022-a` と Herdr セッションの片付け
- 退役のタイミング: RFC-0023 が accepted になった後の単独 PR（launchd 未配線で害は無い、焦らない）
- review-when: 本番生成モデルが ADR-0069 を supersede して大型化する（opus の読みを prior に再開可）
- state: `accepted 2026-09-04`（著者判断済み。実装は dispatch）

### 状態更新

- `rfcs/0017-*.md`: `state: obsoleted 2026-09-04`、Status に「WikiSkill 形は smoke + opus アームで
  閉じた（RFC-0025）。動機（insight 抽出の再設計）は RFC-0023 / 0024 が引き継ぐ」
- `rfcs/0022-*.md`: `state: obsoleted 2026-09-04`、同旨（packet A は main にあるが配線しない）
- `rfcs/0021-*.md`: Next action に「供給列」を追記 — 各 skill に今も行が届いているか（RFC-0023 の
  検索の再利用）を stocktake の読みに足す。review-when の「RFC-0017 が withdrawn / rejected」は
  obsoleted で発火 → 本文の前提（並列実験機構）を RFC-0023 に差し替える 1 行
- `.notes/handoff-rfc-0017-wiki-form-2026-09-03.md` 冒頭に「2026-09-04 決着、RFC-0023〜0025」の 1 行

## Part C — opus アームの凍結

- `replay-opus-3d/opus/summary.json` → `docs/evidence/rfc-0017/replay-opus-3days-20260904.json`
- ページ 9 本 + proposal + 監査 JSONL → `.notes/replay-opus-20260904/`（**非公開**: 他 agent の
  handle と本文引用を含む。gemma smoke の `.notes/smoke-wiki-20260902/` と同じ扱い）
- RFC-0025 本文には定性的な読み（具体 / 行動指示 / patch 比率 0.53 / PAGE_FULL 8 件 / $8.4）だけ書く

## Part D — memory

- `project_rfc_0017_wikiskill_design.md`: 決着を追記（wiki 閉鎖、gemma 固定、opus は形の正しさの
  証拠、後続 RFC-0023〜0025、却下ガード「散文 wiki を gemma で再提案しない」+ 失効条件 = 本番モデルの
  大型化）。MEMORY.md の該当行を同期
- 新規 feedback は無し（既存の measurement-discipline / llm-pipeline-layering に吸収）

## Commit

- main 直 commit（memory `push-workflow`）。**working tree の既存 7 本の rfcs 変更（weekly 無人 draft）は
  stage しない** — 土曜ゲートの領分
- 単位: (1) A2 の bm25 アーム + test (2) A3 script + evidence 2 本 + opus evidence (3) RFC 3 本 + 状態更新
  + index + handoff 注記。各 commit で `.claude/verify.sh --staged` が hook から走る

## Verification

- `uv run pytest tests/test_retrieval_recall_measure.py -q`（A2）、`uv run ruff check scripts/ tests/`
- A1/A2/A3 の JSON が evidence に存在し、pair 数・アーム・rrf-k が記録されている
- `python3 ~/.claude/scripts/claims.py ready` に RFC-0023（accepted 時）/ RFC-0025 が出る
- `uv run python scripts/docs_consistency_scan.py`（rfcs index と frontmatter の整合）
- `.claude/verify.sh`（全体）が PASS
