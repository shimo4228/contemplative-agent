# weekly-analysis.sh 決定論的 intake 層 — T-SWEEP-ATOMIC + T-DUP-DETERMINISTIC

## Context

週次レポートの決定論的 intake 層に、2 週連続で表面化した欠陥が 2 つ残っている。どちらも
`scripts/weekly-analysis.sh` の同じブロック（収集 → 組立 → 生成 → promote）を触るので 1 PR で扱う。

1. **T-SWEEP-ATOMIC**（findings F1.2）— `weekly-analysis.sh:208-209` が収集フェーズで
   anomaly sweep の state を書く。生成が失敗した実行もその週の新規性ベースラインを消費するため、
   次の成功実行の Δ / 🆕 は部分窓に対する値になる。07-18（セッション上限）と 07-25（PATH 欠落）で
   2 回連続発生し、2 列が 2 週続けて無情報になった。2026-07-25 の `9bb4615` はレポート本体だけを
   不可分化した（temp file + `mv`）ので、同じ欠陥クラスの残り半分。

2. **T-DUP-DETERMINISTIC**（findings F3.1）— 上流レポートが「記録上初のクロスデー完全一致出力」を
   捏造した。全履歴 141 日・公開レコード 9043 件を sha256 照合したが、日をまたいだ完全一致本文は
   1 件も存在しない。同型の誤りは 2026-06-15 にもある（「6 日連続 re-reply」が実は 6 人の別 agent）。
   **クロスデー重複の具体的主張は 2 回中 2 回外している**。構造的理由: E の他エントリは単一エントリの
   引用で検証可能だが、重複の主張だけが複数エントリ・複数日を跨ぐ比較を要する。しかも
   「バイト列が一致するか」は意味理解の要らない構造的性質であり、code に当てるべき問いを LLM に
   投げている（skill: `when-code-when-llm`）。

**意図する結果**: 失敗した実行が新規性ベースラインを消費しなくなること、そしてレポートの
C — Duplicate 節が実測値の上に立つこと。**観測であって介入ではない** — post 単位 reply dedup は
`config/prompts/principles.md` の appendix で却下済みの機構であり、生成を抑止する方向へは踏み込まない。

---

## 変更 1 — sweep state の不可分化

### `scripts/log_anomaly_sweep.py`

`--emit-state PATH` を追加する。`--state` は読むだけ、スナップショットは PATH へ書く。

- `main()` の argparse に 1 引数（help: 「`--no-update` と併用し、呼び出し側が promote する
  pending スナップショットを書き出す」）
- `main()` 末尾、既存の `if not args.no_update: write_state(args.state, findings)`（214-215 行）の
  隣に `if args.emit_state: write_state(args.emit_state, findings)` を置く。
  **既存の `write_state()`（142 行）をそのまま再利用**し、新しい書き込みロジックは足さない
- `--emit-state` 単独指定時に `--state` の更新が止まらないこと（後方互換）

**なぜ 2 回走らせる案を採らないか**: `claude -p` は数分走り、その間 launchd の stderr が
**同じ `logs/` 配下の `weekly-analysis-launchd.log`** に書かれる。promote 後にもう一度 sweep すると
その行を読むので、「レポートに載らなかったのに state には入る」署名が毎週生まれる — 直そうとしている
欠陥の縮小版がそのまま残る。コスト差（実測 1 回 10.8 秒 / `*.log` 140MB）は数分のジョブでは無視できるが、
一致しない state は直せない。

### `scripts/weekly-analysis.sh`

- 204-213 行のブロック: `SWEEP_PENDING="${SWEEP_STATE}.pending.$$"` を定義し、sweep 呼び出しに
  `--no-update --emit-state "$SWEEP_PENDING"` を渡す。既存の `2>/dev/null || true` は維持（非致命）
- **trap を 1 つに統合し、収集フェーズより前へ移す**。現状 `trap 'rm -f "$OUTPUT_TMP"' EXIT` は
  生成直前（261 行）にあり、収集途中で落ちると pending が残る。
  `trap 'rm -f "$OUTPUT_TMP" "$SWEEP_PENDING"' EXIT` を両変数の定義後に 1 回だけ設置する
- `mv "$OUTPUT_TMP" "$OUTPUT"`（276 行）と `echo "Size: ..."` の直後、**日本語訳ブロック（281 行〜）より前**に:
  ```bash
  if [[ -s "$SWEEP_PENDING" ]]; then
      mv "$SWEEP_PENDING" "$SWEEP_STATE" || echo "WARNING: sweep state promote failed" >&2
  fi
  ```
  訳は best-effort であり、新規性ベースラインの確定条件ではない
- 非致命性: pending が無い（sweep 失敗 / logs 不在）なら promote をスキップ → 旧 state が残り、
  次回の 🆕 はより長い窓に対する値になる（保守側に倒れる、正しい方向）

---

## 変更 2 — `scripts/cross_day_duplicate_scan.py`（3 つ目の決定論的 intake）

既存 2 本と同じ作法の standalone スクリプト（`contemplative_agent` を import しない。
`from _md import md_safe` のみ — `scripts/_md.py` を 3 本目も共有する）。

### 位置づけ

- sweep = イベント流（logs 署名、novelty state **あり**）
- `state_invariant_check.py` = 蓄積状態（knowledge/agents、絶対検査、state なし）
- **本スクリプト = 公開レコードの同一性（episode logs、絶対検査、state なし）**

state を持たないので変更 1 の不可分性問題は構造的に発生しない。docstring に明記する。

### 入力と境界（設計の中心）

**episode log を読む最初の intake** なので、境界を実装で固定する。

| 項目 | 決定 |
|---|---|
| 読むファイル | `logs/????-??-??.jsonl` のみ。`*.bak` 除外（二重計上）、symlink スキップ（`log_anomaly_sweep.py:149-156` と同じ規律） |
| 拾うレコード | `type == "activity"` かつ `data.action ∈ {post, reply, comment}`（エージェント自筆の公開本文。`follow`/`unfollow`/`upvote` は content を持たない） |
| ハッシュ対象 | `data.content` の生バイト列 `sha256(content.encode("utf-8"))`。**正規化しない** — near-identical wording は register 観察としてプロンプト側に残す |
| 日付 | **ファイル名由来**（`data.ts` ではない）。「どの日のファイルに載ったか」が主張の単位 |
| 出力してよい | sha256 先頭 12 hex / 件数 / 日付 / action 名（固定語彙）/ skipped 件数 |
| **出力してはならない** | `content` の断片、`post_id`、`target_agent`、`internal_note`、`thinking` |

`post_id` と相手 agent 名を落とすのは意図的。C 節に必要なのは「一致が何件あるか」だけで、どの投稿かは
ハッシュで一意に指せる。外部由来文字列の経路を 1 本も開けないほうが安い。

### CLI

```bash
python3 scripts/cross_day_duplicate_scan.py \
    --log-dir "$MOLTBOOK_HOME/logs" --start "$START_DATE" --end "$END_DATE" [--top 25]
```

- **exit code は常に 0**（重複の存在は corruption ではない）。`state_invariant_check.py:245` の
  FAIL→1 とは意図的に違え、docstring に理由を書く
- 全履歴走査を毎回実行（実測 ~1 秒 / 47MB / 141 ファイル）。窓と lifetime は **1 パス**から両方導出する
- hex にも `md_safe()` を通す（実質 no-op だが、3 本目も同じ経路を通ることを保証）

### 出力形式

```markdown
## Cross-Day Duplicate Scan

Window 2026-07-18..2026-07-24: 431 published bodies (post/reply/comment) across 7 day files.
**Cross-day exact duplicates: 0.**
Lifetime (141 day files, 9043 bodies): **cross-day exact duplicates: 0.**
Intra-day exact repeats in window: 2 groups (4 bodies).

| Hash | Bodies | Dates | Actions |
|----|------|-------|---------|
| `a1b2c3d4e5f6` | 2 | 2026-07-23 | reply×2 |

_Exact SHA-256 of published body text; no normalization. Hashes and counts only —
no body text, post id, or counterparty name crosses this boundary. **Observation
only**: hash-equality dedup as an intervention is a rejected mechanism
(principles.md appendix) and this table is not a case for it._
```

- **0 件のときは「一致は存在しない」を明文で言い切る**。0 の行を出すだけでは今回の捏造は止まらない
  （上流は「決定できない」と書いた上で見出しにした）
- 末尾の *Observation only* 行は Principle 1 対策。ハッシュ表を見た読み手が「では hash dedup ゲートを」と
  書き戻すのを構造的に塞ぐ
- **intra-day 行を含める**。同じ grouping から追加コストゼロで出る上、findings F3.2 が示したとおり
  実在するのは intra-day 側。cross-day 0 だけでは「重複なし」と読まれ、真の信号が消える
- malformed 行があれば `skipped: N malformed records` を本文に出す（silent fallback 禁止）

### `scripts/weekly-analysis.sh` への配線

- 216-228 行（invariant check）の直後に同型のブロックを置く。`2>/dev/null || true` で捕捉し、
  空なら `"## Cross-Day Duplicate Scan"$'\n\n'"No duplicate scan available."` にフォールバック
- `USER_PROMPT`（233-247 行）の `$INVARIANTS` の次に `$DUP_SCAN` を挿入

---

## 変更 3 — プロンプト・ドキュメント・ADR

### `config/prompts/weekly-analysis.md`（48 行、C の Duplicate 指標）

1 文追加:

> Cross-day identity claims must cite the Cross-Day Duplicate Scan section. If it reports 0
> cross-day duplicates, no such claim may appear in C, D, E, or the summary.

`principles.md` の Principle 5（既に本文にある）は「決定論的入力に依拠せよ」を一般則として述べている。
上の 1 文はそれを C 節の具体的な参照先に結線するもので、重複しない。**`principles.md` は無変更**。

### ADR-0083（新規、en + ja + index + graph）

タイトル: *Episode logs enter the weekly prompt as hashes only*

3 本目の intake は**境界の変更**なので記録する。CLAUDE.md のセキュリティ方針は「Claude Code は
episode log を直読みするな」であり、決定論スクリプトが読んでハッシュだけ射影するのは新しい前例。
次に誰かが「post_id も出そう」と言ったときに参照できる正本が要る。

- Context: F3.1（捏造）と 2026-06-15 の 2 事例、構造的性質を LLM に投げていたこと
- Decision: 出力語彙の固定（hex / 件数 / 日付 / action）、state を持たない絶対検査、exit 0 常時
- Consequences: 違反は `TestOutputBoundary` がゲートする
- Alternatives: post_id を出す案（injection 面を開く）、窓のみ走査（"first in the record" 主張を支えられない）、
  正規化ハッシュ（near-identical は意味的性質なので code に当てない）

**必須の同伴更新**（テストが gate している）:
- `docs/adr/0083-*.md` + `docs/adr/0083-*.ja.md` — `test_doc_links.py::test_adr_english_japanese_pairing`
- `docs/adr/README.md` の索引行
- `graph.jsonld` に ADR node — `test_graph_integrity.py::test_adr_nodes_match_adr_files_bidirectionally`
  が双方向一致を要求するので、node が無いと pytest が落ちる

T-SWEEP-ATOMIC 側は純粋なバグ修正で ADR 不要。

### CODEMAPS

- `docs/CODEMAPS/architecture.md` — 週次 intake 段（3 本 + state の確定順序）を 3〜4 行で追加。
  現状 sweep / invariant check は CODEMAPS にも ADR にも記述がないので、ここが初出になる。
  CLAUDE.md の鮮度規約（段構成の変更は同 PR で Data Flow を更新）に照らして必要
- `docs/CODEMAPS/moltbook-agent.md:196`（script-read prompts の記述）に 1 行追記

### `.notes/TASKS.md`

完了時に T-SWEEP-ATOMIC / T-DUP-DETERMINISTIC を Done 節へ移す（同じ作業内）。

---

## テスト計画（chaos-TDD by default）

### `tests/test_cross_day_duplicate_scan.py`（新規）

`tests/test_log_anomaly_sweep.py:11-13` の `sys.path` 挿入方式をそのまま踏襲する。
hypothesis は conftest の `ci` プロファイル（derandomize）下で走る。

| クラス | 主張 |
|---|---|
| `TestCollect` | `post/reply/comment` だけ拾う / `follow` 等を無視 / `.bak` を無視 / symlink スキップ / 日付はファイル名由来 |
| `TestGrouping` | 2 日に同一本文 → cross-day 1 群 / 同日 2 回 → cross-day 0・intra-day 1 群 / 別本文 → 0 / 空白 1 文字違いは別（正規化しないことの pin） |
| `TestWindow` | 窓は両端含む / lifetime と窓を同一パスから正しく分離 / 窓外の日は lifetime にのみ効く |
| **`TestOutputBoundary`**（load-bearing） | 敵対的本文（`\|`、backtick、`</untrusted_content>`、"IGNORE PREVIOUS INSTRUCTIONS"、CJK/emoji、100KB）を仕込み、**レンダ出力に本文の 8 文字以上の部分文字列が 1 つも現れない**ことを assert。加えて hypothesis property: 任意テキストに対し出力が固定語彙 + `[0-9a-f]{12}` + 日付 + 数字のみで構成される |
| **`TestFaults`**（chaos カラム） | 壊れた JSON 行 / 末尾切れ行（append-only クラッシュ）/ `data` が dict でない / `content` が `None`・int・list / 不正 UTF-8 バイト / 読めないファイル（chmod 000）/ `logs/` 不在 / 日付形でないファイル名 → 例外を投げず、正常行の結果は保たれ、`skipped: N` が出力に現れる。exit は常に 0 |
| `TestDeterminism` | 同一入力 → バイト同一出力（並び順が dict 反復に依存しない） |

fault カタログの出所は運用実績: episode log は追記型で launchd kill と同居しており、末尾切れ行は現実の障害形。

### `tests/test_log_anomaly_sweep.py`（追記）

- `--emit-state` が指定パスへ書き、`--state` を変更しない
- `--emit-state` 単独（`--no-update` なし）でも `--state` は従来どおり更新される（後方互換 pin）
- emit されたスナップショット == 同一 findings に対する `write_state()` の出力

### `tests/test_weekly_analysis_shell.py`（新規、macOS 限定 skipif）

不変条件「**生成に失敗した実行は sweep state を変更しない**」を違反注入で発火実証する。
シェルを実行するテストは現在 1 本も無いので新カテゴリ（`date -j` = BSD 依存のため skipif）。

1. 一時 `MOLTBOOK_HOME` に comment-report 1 本 + `logs/*.log` を置き、既知の state を仕込む
2. PATH 先頭に `claude` スタブを置く
3. **exit 1 のスタブ** → 非 0 終了・`weekly-*.md` 未生成・**state はバイト同一**・pending が残っていない
4. **exit 0 で本文を吐くスタブ** → レポート生成 + state が更新される

---

## Verify ゲート（コミットの門）

| # | 項目 | 具体 |
|---|---|---|
| 1 | build | `uv pip install -e ".[dev]"`（`scripts/` はパッケージ外なので実質 no-op） |
| 2 | type check | `uv run pyright`（型エラー 0 維持）。**注**: `pyproject.toml` の `include = ["src","tests"]` により `scripts/` は対象外 — テスト経由で間接的にしか見られない。include 拡張は既存スクリプトの未知エラーを巻き込むため本 PR のスコープ外 |
| 3 | lint | `uv run ruff check src/ tests/ scripts/` |
| 4 | tests | `uv run pytest tests/ -v` 全 PASS + `--cov` で新規スクリプト 80% 以上。`test_graph_integrity` / `test_doc_links` が ADR 同伴更新を gate する |
| 5 | secret scan | staged diff（PreToolUse hook が自動発火） |
| 6 | doc sync | ADR-0083 en/ja + README 索引 + graph.jsonld node + architecture.md Data Flow + moltbook-agent.md が**同じ diff にある**こと |
| 7 | git status | `.pending.*` / probe 出力が混ざっていないこと |
| — | **手動 smoke** | `./scripts/weekly-analysis.sh --end-date 2026-07-24` を実データで 1 回。**事前に `weekly-2026-07-24.md` / `.ja.md` を退避**（上書きされる）。確認: dup scan 節が 0 を明示して出る / sweep state の mtime が promote 後に更新される / レポート本文に episode log の本文が 1 文字も混ざっていない |
| — | review | `security-reviewer`（境界変更のため必須）+ `codex-review`（シェルの trap / rename 順序は別モデルの目が効く） |

重い Ollama 実験は伴わないが、smoke は `claude -p` を数分回すので **スケジュールセッション（JST 0/6/12/18 時）を避ける**。

---

## コミット分割

1. `fix: a failed weekly run no longer spends the week's novelty baseline`
   — `--emit-state` + シェル配線 + trap 統合 + sweep テスト + シェル回帰テスト
2. `feat: a deterministic cross-day duplicate scan backs the report's C section`
   — 新スクリプト + テスト + シェル配線 + `weekly-analysis.md` 1 文
3. `docs: record the hash-only episode-log projection (ADR-0083)`
   — ADR en/ja + README 索引 + graph.jsonld + CODEMAPS

## スコープ外（意図的に踏み込まない）

- **生成側の抑止**（post 単位 reply dedup、hash dedup ゲート、cosine ゲート）— principles.md appendix の
  却下済み機構。本 PR は観測のみ
- **near-duplicate / 意味的類似の検出** — 意味的性質なので code に当てない。register 観察としてプロンプト側に残す
- `pyright` の `include` に `scripts/` を足すこと（既存スクリプトの未知エラーを巻き込む）
- ログローテーション（`*.log` が 140MB に達しており将来の論点だが、本 PR の欠陥とは独立）

## Post-commit（ユーザー判断）

`graph.jsonld` を更新するので HF Datasets mirror（`Shimo4228/contemplative-agent`）の同期が
best-effort で残る。外部書き込みなので実行前に確認する。
