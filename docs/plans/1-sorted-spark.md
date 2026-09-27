# T-VER-GRAMMAR-11 — ADR-0062 第 11 amendment（文法変更）

## Context

Contemplative Agent は Moltbook 上でコンテンツを作成するたびに数学 CAPTCHA を解く（ADR-0062 の create-time verification handshake）。解くのは決定論パーサ `code_parse_challenge` で、読めない形は **abstain（`None`）して黙る**のが設計原則 — 「誤答は abstain より悪い」が 10 回の amendment を貫く姿勢である。

健全性を測るのが ground-truth replay gate。2026-07-26 の実測:

```
unique challenges : 2236
abstained         : 394   (17.6%)
correct vs truth  : 1828
WRONG vs truth    : 9     ← HARD GATE: FAIL
```

**台帳で唯一「放置コストが単調増加する」行**（`.notes/TASKS.md` T-VER-GRAMMAR-11）。corpus はライブ traffic から成長するため、放置中に新しい文法失敗が積み上がる（07-25: 7 誤答 / 2149 unique → 07-26: 9 誤答 / 2236 unique）。誤答は server に `"Incorrect answer"` で弾かれ、rejected-answer memory に溜まり、platform から見える誤答 footprint になる。

9 件の監査レコードを直接確認: **全件がレコード 1 件・`solver_path=code_parse`・server 側 "Incorrect answer"**。退役済み `llm_reason` の残骸ではなく、パーサ自身が submit して弾かれた値である。

ADR-0062 第 10 amendment は「これを閉じるのは第 11 amendment であってリファクタではない」と明記済み。本作業がその第 11 amendment。

### 到達点

`replay_parser.py` の HARD GATE を PASS に戻す（wrong = 0 かつ unlabeled parses = 0）。予測される最終状態: **parsed 1836 (82.1%) / abstained 400 / correct 1828 / WRONG 0 / known-unresolvable 8**。correct は 1828 のまま不変 — 動くのは 6 件だけで、すべて wrong → abstain。

### 方針（確認済み）

1. **abstain 専用** — 新規ルール行は「読めないなら黙る」だけ。値を返す行は追加しない（新たな誤答経路を作らない）
2. **自然読み却下の 3 件は `answer: null` ラベル** — 既存 5 件と同じ excused 扱い
3. **Chaos fault column は別タスク** — 台帳に新規行を立てる

## 失敗 9 件の診断（コード上で検証済み）

| # | sha | 現在の出力 | 真因 |
|---|---|---|---|
| 1 | `46a9e0a1` | 17.00 (23−6) | `_TailSignals.contradicts_subtraction` が `c.word == "combined"` の**1 語だけ**を見ている。この challenge の cue は `total` なので、まさにこの形を止めるはずの `subtraction_chain_against_combined_cue` が発火しない |
| 2 | `90d922b8` | 512.00 (32×16) | `*` が operand と**その単位名詞の間**に挟まっている（2 つの operand が同じ単位名詞を共有）。受理済みの `*`+`and` 例 9 件ではすべて `*` は単位名詞の**後ろ**。※「MUL chain vs additive cue」の一般ルールは**不可** — 受理済み 140 件を殺す |
| 3 | `a21fc1a4` | 3703.00 (23×23×7) | 3 operand の chain で、最初の gap に `_AndEvent`（節境界）が入っている。2 文を 1 つの fold として畳んでいる |
| 4 | `2b56f579` | 3920.00 (14×40×7) | 同上の `and`-in-gap。※scene distractor ではない — `_dedup_numbers` が 9 atom 離れた**別々の** 14 を潰した結果（距離ガードは不可: 正しい dedup が距離 6/7/8 に実在） |
| 5 | `72f0ff56` | 13.00 (20−7) | `treee` が `tre`（3 文字）に collapse。round-8 near-miss poisoning tier は 4-5 文字ゲートなので素通りして**黙って落ちる**。tens 語の unit 半分が壊れた形 |
| 6 | `449bea27` | 8.00 (3+5) | `trween` が `trwen`（5 文字）に collapse し、全 canonical / collapsed 数詞から**距離 ≥2**（最近傍 `ten` が 2）。語彙的に到達不能。unit 語の tens 半分が壊れた形 |
| 7 | `03861657` | 40.00 (33+7) | 算術的に唯一自然な読み。server が却下 |
| 8 | `6661823a` | 5.00 (20−15) | 同上 |
| 9 | `cb59e684` | 23.00 (35−12) | 同上 |

7-9 は既存の `answer: null` 5 件と同型（うち 3 件は同じ「X and Y, total force → 加算が却下」族）。

## 実装

対象: `src/contemplative_agent/adapters/moltbook/verification_parse.py`

各ステップで **`differential_replay.py` を先に**回して「動いた challenge 集合」が予測と一致することを確認してから次へ進む。文法変更なので differential は mismatch を報告するのが正常（exit 0 を期待しない）。

### Step 1 — ラベル 3 件（コード変更なし）

`docs/evidence/adr-0062-parser-rewrite/manual_labels.json` に `03861657` / `6661823a` / `cb59e684` を `"answer": null` + 理由 `note` / `source` で追加（既存 `678acba8` / `95f581b1` の書式に合わせる）。

→ wrong 9 → 6。残り 6 件がすべて文法起因であることを確定させる。

### Step 2 — cue 語彙の穴を塞ぐ

`_TailSignals.contradicts_subtraction` を `any(c.word in _ADDITIVE_CUES for c in self.cues)` に。行名を `subtraction_chain_against_additive_cue` / `postfix_subtraction_against_additive_cue` へ改名（explicit / implicit 両テーブル）。新フィールド不要 — 両テーブルが既に同じ property を読んでいる（`_TailSignals` の存在意義そのもの）。

差分予測: **`46a9e0a1` 17.00 → None の 1 件のみ**。coverage 損失ゼロ（corpus 全体で `_SUB` chain + tail cue は 3 行しかなく、他 2 行は既に abstain）。

### Step 3 — `long_chain_broken_by_a_connective` 行（`_EXPLICIT_TAIL_RULES`）

`when: len(operands) > 2 and and_inside_chain` → `_ABSTAIN`。`_ExplicitCtx` に `and_inside_chain`（gap 内の `_AndEvent` の有無）を追加。`positions.ands` は `_resolve` に既にある。

根拠: `_resolve` の docstring が既に「operand と operation は厳密に交互」を要求している。`and` は新しい節・新しい主体を導入する。corpus で唯一正しい 3-operand chain（`453e7b97`）には gap 内 `and` が無く、誤答 2 件には両方ある。閾値を持たない述語なので magic number が入らない。

差分予測: **`a21fc1a4` と `2b56f579` の 2 件のみ**。

### Step 4 — `multiplicative_symbol_inside_a_unit_phrase` 行（`_EXPLICIT_TAIL_RULES`）

`_ExplicitCtx` に `mul_symbol_in_unit_phrase` を追加。新 module helper `_mul_symbol_inside_unit_phrase(atoms, operands, events)` が判定する: ある gap の唯一の演算が `*` **記号**で、記号の次の atom が右 operand の span 外にあり、かつ右 operand の直後の atom と一致（または 1 edit 以内、`_FUZZY_MIN_TOKEN` 床つき）。

`_MUL` 限定は意図的: corpus に `+` の同型が 1 件（`fe8bb27e`）あり、そこでは加算読みと implicit-add 読みが 39.00 で一致して受理されている。`+` を含めるとこの正答を失う。迷い `*` は答えを反転させるが、迷い `+` は反転させない。

差分予測: **`90d922b8` の 1 件のみ**。`fe8bb27e` が動いたら `_MUL` 限定が外れている。

### Step 5 — `_poison_broken_tens_compound(events, atoms)`（pre-table ガード、2 commit）

`code_parse_challenge` 内、`_scan` の後・`_dedup_numbers` の前。`_Abstain` を raise する（先例: `_apply_points`）。ルール行ではなく語彙ガード節 — round-8 near-miss tier の兄弟であり、ルールテーブルは atom にアクセスできない。

「tens+unit 複合語の片側が壊れて消える」という同じ現象の 2 つの腕:

- **Arm A（unit 側が壊れた）**: `is_tens` な `_NumEvent` の span 直後の atom が、event を持たず / `_FUZZY_STOPWORDS` に無く / collapsed 3 文字以上 / 数詞の collapsed 形から 1 edit 以内 → abstain。→ `72f0ff56`
- **Arm B（tens 側が壊れた）**: challenge の**最初の** `_NumEvent` が値 1-9 で、2 atom 以上に跨り、**先頭 atom が 1 文字**（分割された証拠）、かつ直前の atom が event を持たず collapsed 5 文字以上 → abstain。→ `449bea27`

3 文字床がここでだけ安全な理由は**位置に縛られている**から。全 corpus で number event の直後に来て数詞に near-miss する token は 4 種のみ（`cen` 61 回はすべて非 tens の後ろ、`is_tens` ゲートで除外 / `the` 1 回も非 tens / `fiv` / `tre`）。Arm A の発火は corpus 全体で 2 件、うち 1 件は元々 abstain。

同時に `_FUZZY_STOPWORDS` に `"the"` / `"ton"` / `"tons"` を追加する（`the` は collapsed `thre` から 1 edit、**`ton` は `ten` から 1 edit**）。`_match_fuzzy` に対しては検証済みの no-op なので coverage コストはゼロで、ガードの爆風半径を偶然でなく明示にする。

Arm A / Arm B は**別コミット**にして差分集合を分離可能に保つ。差分予測は各 1 件。

→ wrong 2 → 0。

### Step 6 — 既存テストの修理（必須・この変更は単独で落とせない）

`tests/test_verification.py::TestCodeParse::test_and_as_add_guard0_never_overrides_explicit_verb_cue`（1236 行付近）が `"twenty five newtons and slows by seven newtons what is total force" == "18.00"` を主張している。これは `46a9e0a1` とまったく同じ形で、その減算読みは **server が却下した**もの。Step 2 でこれは abstain になる。

このテストのコメントは rewrite 以降存在しない `_try_and_as_add` / `_ConjunctionEvent` を参照しており、すでに陳腐化している。`subtraction_chain_against_additive_cue` の下での abstain 主張に変換し、コメントを書き直す。フルスイート中で落ちるのはこの 1 本だけ。

### Step 7 — 回帰 fixture

動いた 6 件の base64 fixture を `test_regression_round9_*_abstain` の parametrize ブロックに追加（`test_regression_round8_number_near_miss_abstains` に倣う。challenge 文は untrusted なので base64 のまま、decode は実行時のみ）。CI はローカル corpus を見ないので、この fixture が唯一の永続的な証拠になる。

## ドキュメント同期（同一 PR）

- **`verification_parse.py` module docstring** — round-7 / round-8 ブロックの書式で "Round 9 (2026-07-26, ADR-0062 11th amendment)" 節を追加
- **`docs/adr/0062-create-time-verification-handshake.md` + `.ja.md`** — 第 11 amendment を Status 節に追記。4 つの文法変更、棄却した代替（blanket MUL-vs-cue = 受理済み 140 件を殺す / `_dedup_numbers` 距離ガード / `_classify_positions` での記号 declassify = `fe8bb27e` を失うか、7th amendment の twin 基準を満たさない新値 48.00 を生む）、known-unresolvable が 8/2236 (0.36%) になったこと、うち 4 件が同じ「X and Y, total → 加算却下」族であること（server 側パターンの疑い）
- **`docs/evidence/adr-0062-parser-rewrite/README.md`** — round 9 の result block（unique / parsed+coverage / abstained / correct / WRONG / known-unresolvable）と、前ラウンドのパーサを同じ corpus に replay した比較。label caveats 節に null 3 件を追記
- **`docs/CODEMAPS/architecture.md` Data Flow** — CLAUDE.md の鮮度規約（パイプラインのゲート・段構成の変更は同 PR で更新）。現状は第 7/9 amendment 止まりで第 8/10 も反映されていないため、verification parse 段を現在の姿（rule table + round 9 のガード群、coverage 実測値）まで更新する
- **`verification_parse_baseline.py`** — ADR-0062 第 10 amendment の指示「次の amendment が来たら baseline を削除または更新する」に従い、第 11 amendment 後のパーサへ refresh（次のリファクタが diff 相手を持てるように）
- **`graph.jsonld`** — 新規 ADR ではなく既存 ADR への amendment なので更新不要（PR 内で明示的に確認する）
- **`.notes/TASKS.md`** — T-VER-GRAMMAR-11 を Done 節へ。新規行として「verification の chaos fault column 新設」を Pending に追加

## 検証

Review（Author-Reviewer 分離）:
- `python-reviewer` — パーサ変更全体
- `security-reviewer` — untrusted CAPTCHA テキストの parse 境界に触るため必須。出力信頼境界（code が再計算した数値のみ submit）が不変であることを確認させる
- `codex-review` — 別モデルによる脱相関レビュー。第 10 amendment でも 20,000 件ランダムファジングで貢献した経路

Verify ゲート（全 PASS でのみコミット）:
1. `uv run ruff check src/ tests/ scripts/`
2. `uv run lint-imports`
3. pyright（型エラー 0 維持）
4. `uv run pytest tests/ -v` — 特に `TestRuleTableTotality`（両テーブルの終端行が無条件であること。新規 2 行は `adjacent_multiplicative_tail_overrides_change_verb` の後・`tail_operation_contradicts_the_chain` の前に挿入し、終端 `explicit_chain` は最後のまま）
5. secret scan（PreToolUse hook が自動）
6. `pip-audit` — 依存変更なしのため省略
7. doc sync — 上記 6 ファイル
8. `git status`

corpus ゲート（ローカル、CI 外）:
- `python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py` — 各ステップで movement set が予測と一致すること
- `.venv/bin/python docs/evidence/adr-0062-parser-rewrite/replay_parser.py` — 最終的に **HARD GATE: PASS**（wrong 0 / unlabeled 0）

## リスク

- **Arm B の 4 条件が最も動機の弱い箇所**。グリッド探索では 4 条件すべてが load-bearing（第 1 operand 制限を外すと正答 3 件、`value < 10` を外すと 53 件、1 文字断片を ≤2 に緩めると 9 件を失う）。差分が予測の 1 件と一致しなければ条件を戻す
- **Plan agent の実測値は再検証対象**。各ステップの differential 予測がその再検証そのものであり、一致しなければそのステップを止める
- **coverage は 82.4% → 82.1% に下がる**。方針どおり許容し、README に記録する
