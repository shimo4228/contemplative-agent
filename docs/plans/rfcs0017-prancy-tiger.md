# RFC-0017 着手 — Step A: skills-on/off baseline を 1 回読む

## Context

RFC-0017（insight 抽出の再設計、`rfcs/0017-insight-extraction-redesign.md`、`state: draft`）の
着手条件は 2 つ。(2) 新 Fable のリリースは成立（このセッションが Fable 5.1）。
(1) **skills-on/off の baseline を 1 回読む**は未実施 — `evals/baselines/` に skills-off アームの
run は無く、`evals/run_eval.py` には空カタログを拒否する preflight（regime pin +
`selection_preconditions_unmet`）があるので、今のコードでは skills-off は exit 2 で走らない。

この読みが決めるのは本 RFC の前提: 「抽出器を治す」か「抽出物がまだ元を取っていない」か
（WikiSkill の gating は空 skill set の検証スコアで初期化する — CA はこの読み値を一度も取っていない）。
読み終えたら設計セッション（grill-me）へ進み、Unresolved questions 残り 3 点を潰して `accepted`。
設計と実装は読み値を持ってから — 本プランは Step A（計測）だけを実行対象にする。

RFC-0020 の教訓（2026-08-31）: **受け入れ幅を run の前に宣言しないと事後に都合よく読む**。
本プランは事前登録を run より前の commit に固定する。

### Build-or-not（judge-tier 自答）

- 既存解: 無い。`evals/` に arm / ablation 機構は無く、`scripts/ipd-two-arm.sh` は憲法用で別物
- 大きさ: `run_eval.py` に `--arm` 1 本（~40 行）+ テスト数本。**読み終えたら撤去**（RFC-0017 の
  消費計画 — ADR-0101。コードは git 履歴に残り、再設計後の再読が要る時は revert で復元）
- 代替: monkeypatch の一発スクリプト → 記録に残らず却下。fixture の `skills/` を空にする →
  preflight が exit 2、かつ `check_staleness` の on-arm 基準を壊すので却下
- 消費計画: RFC-0017 本文に記載済み（読み手 = 設計セッション、1 回で前提を決める、撤去条件）

## 事前登録（run の前に RFC-0017 へ書いて commit する内容）

**アーム**: on = 承認済み baseline `evals/baselines/comment_golden-2026-08-31.json`（2 日前、同一
manifest。run 前に `uv run python evals/check_staleness.py` が exit 0 であることを preflight にする —
これが「on アームを再実行しない」根拠）。off = `--arm skills-off` 1 run、12 ケース × 3 サンプル = 36。

**on アームの参照帯**（two_pass_selected の同一設定 3 run: 08-08 / 08-16 / 08-31。厳密な雑音床は
08-16↔08-31 の対 = nonce 以外同一で、動いたのは 2〜3 サンプル / 1 ケース）:

| 指標（36 サンプル中） | 08-08 | 08-16 | 08-31 | 帯 | run 間の最大振れ |
|---|---|---|---|---|---|
| ADHERENT | 0 | 0 | 2 | 0–2 | 2 |
| DEVIANT | 4 | 3 | 2 | 2–4 | 2 |
| DRIFTING | 32 | 33 | 32 | 32–33 | 1 |
| `register_natural` 失敗 | 35 | 36 | 34 | 34–36 | 2 |
| `persona_intact` 失敗 | 4 | 3 | 2 | 2–4 | 2 |
| `engages_post` 失敗 | 0 | 1 | 0 | 0–1 | 1 |
| `axiom_consistent` 失敗 | 0 | 0 | 0 | 0 | 0 |
| ケース verdict が DRIFTING 以外 | 0 | 0 | 1 | 0–1 | 1 |

参考: 08-06（全 45 skill 注入の旧 regime）は DEVIANT 9 / persona 失敗 9 — 別 regime なので帯には入れない。
on アームの選択実態（08-31 の selection audit）: 1 コメントあたり 3–7 skill（中央値 4–5）注入。

**可読の閾値**（帯の端 + 最大振れ + 1。これを越えなければ「判定不能」であって「効いていない」ではない）:

- H1 「skill は効いている」（off で悪化）: DEVIANT ≥ 7、または `persona_intact` 失敗 ≥ 7、
  または DEVIANT ケース ≥ 3
- H2 「skill は効いていない / 害」（off で改善）: ADHERENT ≥ 5、または `register_natural` 失敗 ≤ 31、
  または ADHERENT ケース ≥ 3
- 方向仮説（事前に 1 つ）: skill 本文は用語が重い（stocktake の jargon 所見）ので、off で
  `register_natural` の失敗が減る。他の指標に方向仮説は置かない
- どちらも越えない → **判定不能**。「Face A の n=36 では skill の効果を見分けられない」と記録し、
  RFC の前提は動かさない。設計セッションに「skill の値打ちを測る面が無い」を持ち込む
- H1 と H2 が同時に立つ（例: DEVIANT 増 + register 改善）→ 混合として両方記録、前提は動かさない

**確認 run（条件付き）**: H1 か H2 が可読なら off アームをもう 1 run（同条件）して方向を確認する
（measurement-discipline 原則 1: 1 回は分布の 1 標本）。2 run 目が閾値を割ったら判定不能に落とす。
判定不能なら 2 run 目はしない。

**記述的読み値（判定に使わない）**: prompt 規模（on の `would_be_skill_tokens` 中央値 vs off = 0）、
コメント長 p50、on アームの selected 分布。

## 実装（`--arm` seam、最小）

対象: `evals/run_eval.py`（+ `tests/test_eval_injection_regime.py`）。`compare.py` /
`check_staleness.py` / `judging.py` / `generation.py` / dataset は触らない。

1. `--arm {skills-on,skills-off}`（既定 `skills-on`）。`ARM_REGIMES = {"skills-on": INJECTION_REGIME,
   "skills-off": "full_corpus"}`。`INJECTION_REGIME` 定数は on の pin としてそのまま残す
   （`check_staleness.py:95` と `test_eval_pins_the_two_pass_selected_regime` が読む）
2. `_configure_pinned_assets(fixture, selection_audit_dir, *, skills: bool = True)` —
   `skills=False` なら `configure(skills_dir=…)` と `configure_skill_selection(…)` の両方を呼ばない。
   `prompting._skills_dir` の既定は `None`（`core/llm/prompting.py:32`）なので、それだけで
   `<learned_skills>` ブロックが system prompt から消える（`prompting.py:284-292`）
3. `_preflight(fixture, judge_bin, regime)` — `configured_injection_regime()` を arm の regime と比較
   （off は `REGIME_FULL_CORPUS = "full_corpus"`）。空カタログ検査は two_pass のときだけ（現状どおり）
4. manifest に `"injection_regime": regime` と `"arm": args.arm` を記録。`--baseline` を off run に
   渡すと `injection_regime` 不一致で exit 2 のまま（fail-closed 維持 — 比較は手で行う）
5. `injection_observed`: off アームは selector が走らないので `expected_observations = 0`、
   「regime not uniform」警告を出さない（off で `unobserved = 36` と出るのは誤報）
6. run dir 名を `<run_id>-skills-off` にする（人間が results/ を見て取り違えない）
7. テスト（TDD、RED → GREEN）: off で `configured_injection_regime() == "full_corpus"`、
   `_build_system_prompt()` に `<learned_skills>` が無い、`_preflight` が off の regime を通す、
   既存の on テストが無改変で通る

## 実行手順

1. `python3 ~/.claude/scripts/claims.py claim RFC-0017 --label "skills-off-baseline"`。
   frontmatter を `state: in_progress` / `state_since: 2026-09-02` に
2. RFC-0017 に「## 2026-09-02 事前登録（skills-on/off baseline）」節を書く（上の内容）→ **commit 1**
   （run の前に固定する。RFC-0020 の積み残しをここで実施）
3. `--arm` 実装 + テスト → `.claude/verify.sh` PASS → code-reviewer agent（省略不可）→ **commit 2**
4. preflight: `uv run python evals/check_staleness.py` exit 0（on = 08-31 baseline が現行と同一）
5. run: `uv run --group eval python evals/run_eval.py --arm skills-off`（nohup + PID + Monitor。
   ~34 分、Ollama 占有 + sonnet 判定 36 回）。**JST 06:00–07:00 / 12:00–13:00 / 18:00–19:00 /
   00:00–01:00 の定期セッションと重ねない**（16GB、Metal OOM 実績）。今は 04:40 JST なので
   実装が 05:10 までに終わらなければ 07:00 以降に回す
6. 読み: `evals/results/<id>-skills-off/run.json` と 08-31 baseline を突き合わせ（RFC-0020 と同じ
   手計算、scratchpad の一発 python）。閾値表で判定 → 条件付き確認 run
7. 記録: RFC-0017 に「## 2026-09-0X Reading」節（表は全部写す — `evals/results/` は gitignored）、
   off run.json を `docs/evidence/rfc-0017/comment_golden-skills-off-2026090X.json` に凍結 +
   `docs/evidence/README.md` に行追加（RFC 単位のサブフォルダは初例 — 前提として明記）→ **commit 3**
8. `--arm` とテストを撤去（RFC-0017 の消費計画どおり。復元は revert）→ **commit 4**
9. 手放す: `claims.py release RFC-0017 --outcome handoff`（次は設計セッション）。
   RFC の Next action を「設計セッション（grill-me）→ 残り 3 点を潰して accepted」に更新

並行セッションの未コミット物（`rfcs/0020-…md` の Resolution 節、未追跡
`evals/baselines/comment_golden-2026-08-31.json`）は触らない — `git add` はパス指定のみ。
ただし 08-31 baseline が on アームなので、その commit が先に無いと clone 先で照合先が消える。
実行時に未コミットのままなら、読みの commit 3 で同梱するか著者に確認する。

## Step A の後（本プランの実行対象外、順序だけ）

- 設計セッション（grill-me）: 飽和シグナルの判定者 / cluster 床 3 の扱い / 環境の反応の入れ方。
  探索で判明した設計制約を持ち込む — 却下理由の機械可読な教師データは reviewer prose
  （ADR-0098 で退役、再生成なし）にしか無く `audit.jsonl` の `reason` は adopt/reject で null、
  ADR-0097 slice 3 の verdict 語彙は producer を失っている、`scripts/retrieval_recall_measure.py`
  は一度も走っていない、singleton 分布は `insight.py:256` が既に記録している
- accepted → 教師データ（`.notes/insight-candidate-review-2026-07-25.md` 等）での offline 較正から実装

## Verification

- `.claude/verify.sh` 全 PASS（format / lint / pyright / bandit / pytest / staleness advisory）
- `uv run pytest tests/test_eval_injection_regime.py -q` — on の既存テスト無改変で通り、off の新テストが通る
- `uv run --group eval python evals/run_eval.py --arm skills-off --cases emptiness-1 --samples 1`
  のスモーク（~2 分）で manifest.arm / injection_regime / `<learned_skills>` 不在を確認してから本 run
- 本 run: exit 0、INCOMPLETE 0、run.json の `manifest.arm == "skills-off"`
- 撤去後: `check_staleness.py` exit 0 のまま、`tests/test_eval_injection_regime.py` が撤去前の形に戻る
