# T-GAP1 — distill prompt に mode 7/8/9 を足すか

## Context

ADR-0072 は Gap-1 モード（aspirational / aesthetic / negation）を意図的に見送った
（`docs/adr/0072-...md:198-201`「One concept — register — per change.」）。T-GAP1 はその
唯一生きている後継分岐で、「足すと pairwise cosine が下がるか」を dry-run 計器の A/B で決める。

**Phase 0 で前提が 3 つ崩れた。** うち 1 つ（下の (b)）は A/B そのものを前倒しで無意味に
しうるので、**再計数を A/B の前に置く**（オーナー承認済み、2026-08-16）。

## Phase 0 の結果（全件 file:line 付き。詳細は `.notes/premise-check-T-GAP1.md` に書く）

**検証済み（計測装置は台帳の主張どおり動く）**

| 前提 | 根拠 |
|---|---|
| `--dry-run` は何も書かない | `cli/memory_cmds.py:128`、`core/distill.py:830` / `:833-835` / `:199`。加えて `embeddings.sqlite` は adapter 側のエピソード埋め込み専用（`adapters/moltbook/config.py:45`）で distill は通らない |
| 計器は post-dedup の add 集合だけを測る | `core/distill.py:789-798`（コメント自体が宣言） |
| ログ行の実文字列 | `core/view_metrics.py:337-339` + `distill.py:800` → `dry-run instrument: diversity — n=... pairwise cosine mean=... p50=... p90=...`。`:.2f` 固定 |
| run lock を取る | `cli/memory_cmds.py:53-54`（`blocking=True`） |
| memory guard の発火条件 | pairwise は `n>3000`（`view_metrics.py:69,247`）で不発の見込み、cluster は `n>500`（`:63,263`）で**発火しうる**ので毎回目視 |
| worktree 隔離が load-bearing | 本番 distill は `com.moltbook.distill.plist` が 03:30 JST に**メインの `.venv`** で起動。`core/domain.py:23` の `_PROJECT_ROOT` 解決どおり、worktree の venv なら漏れない |

**反証（私の初回報告の訂正）**

- **一次資料は存在する。** `.notes/archive/self-reflection-pipeline-future-work-2026-05-13.md:44-71`
  に 10-mode 表・カバレッジ判定・追加案の文言例・リスク注記。ADR がリンクしなかったのは
  `.notes/` が gitignored で CLAUDE.md が ADR→`.notes` 参照を禁じているため

**崩れている前提（深刻度順）**

- **(a) 「mode 7/8/9」は列挙の続きではない。** 番号はプロンプト内の体系ではなく外から当てた
  分析フレーム。`distill_episode.md:5` は 4 項目のフラット列挙で、同一 4 項目が
  `distill_postgate.md:7` に複写。表の ✓ は「散文が結果的にその mode を誘発している」の意味
- **(b) 「0 件」は介入前のコーパスの読み。** `.notes/self-reflection-classification-2026-07-03.md:32-45`
  で 7/8/9 = 0/0/0（mode 10 は自然解消）。だが読んだのは日付 06-23〜07-02 のパターン（`:29-30`）で、
  ADR-0072 の register 介入は同じ 07-03 に `5912f5b` で出荷。以後コーパスの 75% が入れ替わった
  （T-P3 の読み）。**現行プロンプトで数え直した人はいない**
- **(c) mode 7 は現行プロンプトと構造的に衝突する。** `distill_episode.md:5`「Describe what was
  observed, not what to do about it」と `:7` の moment-indexed 過去形レジスタに対し、
  05-13 note `:56` は mode 7 を「未来志向、現 prompt は過去形」と明記。2026-05 時点では単なる
  未カバーだったが、ADR-0072 が過去形レジスタを強化した今は既存 2 節との**矛盾**になる

## Phase 1（先行・read-only）— mode 別再計数

`.notes/self-reflection-classification-2026-07-03.md` と同じ手順・同じ view・同じ n=30 で
現行コーパスを数え直す。生成 LLM は使わない（seed 埋め込みのみ）。**定時窓を気にせず着手可**。

1. worktree に venv: `uv venv .venv && uv pip install -e ".[dev]"`
2. worktree の venv で read-only スクリプトを 1 本書く（`scratchpad/` に置く。repo に残さない）:
   `KnowledgeStore.get_raw_patterns()`（`core/knowledge_store.py:196`）→
   `ViewRegistry.find_by_view("self_reflection", ...)`（`core/views.py:293`）→ 上位 30 件の本文を出力
3. 30 件を 10-mode に分類し、07-03 の表と並べる
4. 読み値を `.notes/mode-recount-T-GAP1-2026-08-16.md` に書く

knowledge.json は蒸留済み自己出力なので直読み可（CLAUDE.md がエピソードログの代替として明示）。
138 MB あるのでロードに 1 分程度かかる。

**分岐**

- **7/8/9 が今も 0 件** → gap 実在。Phase 2 へ（arm の文言を承認にかける）
- **いずれかが非ゼロ** → register 介入が副次的に埋めた（mode 10 の先例あり）。**Phase 2 を実行せず
  T-GAP1 を `dropped` で閉じる。** 成果物は読み値のみ、コード変更 0 ファイル、Ollama 0 分

## Phase 2（条件付き）— arm 定義と A/B

**先に主張を立てる**（台帳手順 0）。予測と機構を測定前に `.notes/` に固定する:

> **予測: 下がる。** ADR-0072 の register 介入は pairwise を 0.55→0.58 に**上げた** — 1 つの指示が
> 1 つの書き方を強制し、コーパスが単一軸に寄ったため。mode 7/8/9 は互いに異質な 3 軸
> （未来志向 / 価値判断 / 否定）なので、同じ機構が逆向きに働き、バッチ内の分散が増えて
> pairwise mean が下がると予測する。
> **反証条件**: 上がった場合、機構は「軸が増えた」ではなく「3 モードがチェックリスト化し、
> 各エピソードに定型 3 文が生成された」。その場合は singletons が減り largest cluster が増える
> はずなので、cluster 行で 2 つの機構を弁別する。

arm の文言は 05-13 note `:63-71` の追加案から起こし、`distill_episode.md:5` の列挙を伸ばす形に
する（`distill_postgate.md:7` にも鏡写し — 片方だけだと postgate が新モードを drop する）。
**(c) の矛盾をどう扱うかを含めて、着手前に文言そのものを承認にかける。**

A/B は台帳どおり `--days 2` を 2〜3 ペア。`--file` でエピソード集合を pin する道もあるが、
日付名のログ path を Bash に書くと episode-log hook（`_episode-log-common.sh:73`）が止めるので使わない。
`read_range` は **UTC** 日付（`episode_log.py:62-63`）なので JST 19:00–23:30 = UTC 10:00–14:30 は
日付境界を跨がず、次の定時セッション（00:00 JST）まで母集団は凍結する。19:00 以降に開始し
23:30 までに 4 本を収める。毎回 memory guard 警告の有無を確認する。

## 出荷判断

**下がらなければ出荷しない。** その場合の成果物は測定記録 + `dropped` で、コード変更 0 ファイルが
正常な終わり方。出荷する場合のみ:

- `tests/test_distill.py:786-795`（`TestDistillEpisodePromptTemplate`、brace escape 回帰）を通す
- ADR-0072:198-201 の Rejected を覆すので、新規 ADR か ADR-0072 への Amendment を書く
- **eval baseline が STALE になる。** `evals/run_eval.py:120-121` が `PromptTemplates` 全 field 名に
  一致する `config/prompts/*.md` を hash し、`distill_episode` / `distill_postgate` は両方 field
  （`core/domain.py:64-65`）。ただし現行 baseline は `comment_golden` でコメント生成用、distill
  プロンプトを読まないので**中身のない STALE**。`verify.sh:175-176` は `warn` 経由でブロックしない。
  この事実を ADR に書く（7cfbf31 が sampling_state に理由を埋めたのと同じ耐久性の要求）
- `/implementation-chain` → Review agent 群 → `bash .claude/verify.sh` → commit。
  **push しない。main に merge しない**（branch `task/gap1`）

## 台帳

承認直後に claim（plan mode 中は非 read-only ツールを禁じられていたため未取得）:

```
CLAUDE_PROJECT_DIR=~/MyAI_Lab/contemplative-agent \
  python3 ~/.claude/scripts/claims.py claim T-GAP1 --label "distill prompt mode 7/8/9 の A/B"
```

終了時に `release --outcome done|abandoned --commit <SHA>`、台帳ファイルの `state:` を更新。

## Verification

- Phase 1: 07-03 の表と今日の表が同じ形式で並ぶこと。n=30 が両方で満たされていること
- Phase 2（実行時）: A/B 各回で `dry-run instrument: diversity` 行が出ること、memory guard 警告が
  無いこと、A と B で `n` が同オーダーであること（大きくずれたら母集団が変わった合図）
- 出荷時: `uv run pytest tests/test_distill.py -v` → `bash .claude/verify.sh` 全 PASS
- 全過程で `git -C ~/MyAI_Lab/contemplative-agent status` がクリーンなこと
  （`.notes/` の指定ファイル以外、メイン側に触れていない証明）
