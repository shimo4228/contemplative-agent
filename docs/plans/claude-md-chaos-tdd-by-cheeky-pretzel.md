# chaos-TDD by default に撤退の書式を入れる

## Context

著者の問い: 「chaos-TDD by default と observability by default が、ガード 1 つに対して
テストと説明を義務づけている。テスト比 3.2:1 は方針の帰結ではないか。Claude 5 世代には
過剰な指示になっていないか」

**実測は過剰実装を否定した。** 代わりに別の欠陥が出た。

| 検査 | 結果 |
|---|---|
| src:tests 行数比 | **1.84:1**（`scripts/` を本番に算入すると 1.47:1）。3.2:1 はスイート全体では成立しない |
| 3.2:1 の出所 | テスト比上位モジュール（constitution 4.59 / agent 4.31 / memory 4.24、上位 5 平均 4.2:1）と直近 churn 5.15:1。ただし churn の分母から `scripts/` 4,887 行が抜けており、算入すると 1:1.7 |
| 方針への帰属 | 関数 20% / 行 30〜35%。うち observability は assert 行の **5.2%** で主因ではない |
| ガード追加時の膨張 | 1.3〜2.8:1（`396126d` 1.3、`7fc271e` 2.1、`1dec2d6` 2.8）。TDD として標準 |
| fault 列 104 関数の質 | 独立した価値 **60%** / 重複 **25%** / キット自己 pin **15%** |

fault 列は義務の産物ではない。`tests/chaos.py:299` は codex-review 2026-08-02 の P2 指摘、
`test_verification_chaos.py` に `/code-review` 参照 5 箇所、`insight_chaos` に grill 2026-07-18。
回帰捕捉の実証もある — `tests/test_verification.py:477` の F-VER-1 は既存テストの期待値を
**反転**させ、`reason_fallback_disabled` が退役フォールバックの復活判断に使う日次カウントを
汚染していたことを暴いた。fault 列がなければ緑のまま誤カウントが積まれ続けていた。

**では何が問題か。** `generation-audit` の 4 軸で ADR-0077 を測ると、Intent（黙った劣化の防止）
は有効、Evidence（実インシデント 5 件 + 上記の回帰捕捉）は強い、Freshness（2026-07）は新鮮。
欠けているのは **Expiry だけ**:

- 例外条項が ADR-0075 / ADR-0077 / skill のいずれにも **0 件**（`does not apply` / `例外` の grep が全滅）
- 追記 3 回はすべて拡張方向（F-VER / F-NOV / F8）。**縮小の判断は ADR にも `.notes/tasks/` にも一度も無い**
- chaos 言及タスク 7 件はすべて適用・拡張側。方針自体を疑うタスクはゼロ

台帳が拡張だけ記録して縮小を記録しない形になっているので、方針は評価されずに単調増加する。
rule `akc-cycle.md` の「ADR も足場、supersede が正常系」は、この単調増加を止めるための条項として
既に手元にある。使われていないだけ。

**Claude 5 世代への「過剰」は、義務の存在ではなく義務の向き。** 「fault column を必ず出荷せよ」は
Claude 5 が言われなくても TDD として書く領域で、blanket 義務は判断でなく網羅を生む —
それが重複 25% の正体（thinking guard 1 つを 2 seam で 21 本、うち 4 ペアが同一フィールド対の再 assert）。
一方 skill §1 の「Do not invent faults from imagination — mine them from operational history」は
substrate がどう賢くても供給できない。CA の運用履歴は Claude 5 の中に無い。

→ **溶かすのは「必ず書け」の側、残すのは「どこから起こすか」の側。**

## Scope（著者判断 2026-08-16）

- 方針文言のみ。**テストコードは触らない**（重複 4 ペア・恒真 assert・conftest 集約は今回やらない）
- **ADR-0075 は対象外** — Negative にコスト予測を自分で持ち、帰属も行 10% で主因ではない
- **hypothesis の去就は判断しない** — 実測から削る理由も広げる理由も出ない。事実だけ記録する

## 変更

### 1. `CLAUDE.md:75` — 発火条件をカテゴリから出所へ

現行は「発火条件は上と同じ」で ADR-0075 の一文（外部 I/O・LLM 呼び出し・非決定的判定）に寄生し、
カテゴリ該当だけで義務が立つ。これを **fault の出所**で発火する形に変え、書かない条件を明記する。

- 冒頭ラベルを `**Chaos-TDD by default（発火条件は上と同じ）**` から
  `**Chaos-TDD by default（fault の出所で発火する）**` へ
- 対象を「…を含む機能」から「…を含む機能のうち、**運用履歴に同型の障害があるもの**」へ
- 末尾に **書かない条件** を 2 つ追加（2026-08-16 実測、ADR-0077 Status 参照）:
  1. fault を運用履歴から起こせず想像でしか作れないなら書かない —
     想像由来の fault 行は方針の遵守ではなく違反
  2. 1 ガードの主張は 1 seam。別 seam で同じフィールド対を再 assert するのは、
     その seam でしか出ない fault を本文で名指しできる時だけ
- Verify の問い（「fault カタログ行はどこか」）と注入キットへの参照はそのまま

observability by default の項は**変更しない**。

### 2. `docs/adr/0077-chaos-tdd-fault-injection.md` — Status に 4 度目の追記

`## Status` の末尾（現行 52 行目、F8 追記の直後）に「Amended 2026-08-16」を足す。
既存 3 追記と同じ密度・同じ英語正本の文体。内容:

- **初の縮小方向の追記であること**を宣言 — 3 度の追記が列を足し限界を一度も記録せず、
  台帳に拡張の書式はあって縮小の書式が無かった
- 発端は著者の「by-default 義務がテストを過剰生産していないか」という問い
- 実測: 量の異議は支持されない（1.84:1 / 1.47:1、方針帰属 20%、guard commit 1.3〜2.8:1）
- 代わりに見つかった欠陥: fault 列 104 関数中 ~25% 重複 / ~15% キット自己 pin、
  そして重複には形がある — **claim 単位でなく seam 単位で網羅している**
- Decision に 2 つの limit が加わる: (a) 想像でしか作れない fault は範囲外
  （§1 は元から規則だったが、列を**拒否する**根拠を持っていなかった）、
  (b) 1 ガード 1 seam、例外は本文が「その seam でしか出ない fault」を名指しした時のみ
- 併記の記録: `hypothesis` は本 ADR が Negative に挙げた唯一の依存コストだが `@given` 9 個
  （全テスト関数の 0.3%）で対価が回収されていない。去就は著者が保留した

`docs/adr/0077-chaos-tdd-fault-injection.ja.md` に同じ追記の日本語版を**同一 PR で**入れる
（en 正本 / *.ja.md の規約）。ja は 127 行と en の半分なので、既存の圧縮度に合わせる。

### 3. `.claude/skills/chaos-tdd-fault-injection/SKILL.md` — 拒否の条件を足す

現行の `## When to reach for this skill`（130 行）は 3 項ともすべて**適用を促す**条件で、
列を拒否する条件が無い。ここに「When NOT to write a column」を足す:

- §1 のカタログ手順を通しても**運用履歴から起こせない** fault は書かない
  （§1 の "Do not invent faults from imagination" に拒否の効力を与える）
- 既に別 seam で主張済みのガードは再 assert しない。二重にするなら
  「その seam でしか出ない fault」を名指しする

§1〜§6 の設計ノウハウ本体は変更しない。公開版 fork
（[chaos-tdd-fault-injection](https://github.com/shimo4228/chaos-tdd-fault-injection)）へは
同期しない（CLAUDE.md の運用版 / 汎用化版の別系統規約）。

### 4. `.notes/tasks/` — 記録

`claims.py spawn --origin gate` で **T-CHAOS-SEAM-DEDUP** を起票（今回やらないテスト側の掃除）:
thinking guard の二重 seam 4 ペア（`test_llm_telemetry.py:335,347,366,375,384` ↔
`test_llm_chaos.py:675,615,599,639`）、`test_distill_chaos.py:439` の恒真 assert、
`conftest.py` への fault fixture 集約（`telemetry_dir` が 3 ファイル・`no_sleep` が 2 ファイルに
同一実装、`_read_records` はテストモジュール間 import）。着手条件は「次に fault 列を書く時」。

## 触らないもの

- テストコード全般（`tests/**`）
- ADR-0075 と CLAUDE.md の observability 項
- `pyproject.toml` の hypothesis 依存と `conftest.py` の ci profile
- `docs/CODEMAPS/architecture.md` の Data Flow — 鮮度規約はパイプラインのゲート・式・閾値・
  段構成の変更に発火する。今回は開発規約の文言変更でパイプライン機構は動かない

## Verification

1. `git diff` で変更が 4 ファイル（CLAUDE.md / ADR en / ADR ja / SKILL.md）に収まることを確認
2. `uv run markdownlint-cli2 '**/*.md'` 相当 — `.claude/verify.sh` の markdown 段で足りる
3. `bash .claude/verify.sh` を通す。**既知の失敗を修正と誤認しないこと**:
   eval baseline の staleness（`prompt_templates_sha256`）で exit 1 になるのは `d190f4f` 由来で
   本変更と無関係（直近コミット `e215812` が同じ状態を記録している）。
   markdownlint / ruff / pyright / import-linter / pytest が通っていれば OK
4. テストを変えていないので pytest 件数は変化しないはず — 変化したら scope 逸脱
5. 意味の検算: ADR-0077 に `does not apply` / 免除に相当する記述が**初めて 1 件以上**
   ヒットすること（`grep -n "out of scope\|does not apply" docs/adr/0077-*.md`）
6. Review chain — 文書変更なので `adr-reviewer`（Status 追記が Context-Decision と整合するか、
   一方的な Consequences になっていないか）を回す。コード変更が無いので
   code-reviewer / security-reviewer は不要
