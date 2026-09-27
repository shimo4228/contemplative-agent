# C901 予算を 15 → 13 → 11 → 10 へ段階的に引き下げる

## Context

`pyproject.toml` の `[tool.ruff.lint.mccabe] max-complexity = 15` は 2026-08-28 に導入され、
同日に既存 13 件の over-budget 関数を全部刈って **免除台帳（per-file-ignores）は空**になった。

`.claude/verify.md` の C901 節が持つ再調査トリガーの 1 つが
**「免除リストが空になった時（分布を再実測して閾値引き下げを検討）」** — これは既に発火している。
同節が「閾値 10 は却下」と書いているのは *免除で逃げる場合* の話（24 ファイルが盲点になる）で、
実際に刈って下げる道は塞いでいない。今回はその道を通す。

目的は「一関数あたりの分岐予算を締めて、`もう 1 本 if を足す` を既定で通さない状態にする」こと。
ハーネス ADR-0056 の予算規約（drain, do not raise）と同じ向き。

## 到達点と段

対象は verify ゲートと同じ `src / tests / scripts / evals`
（`docs/evidence/**` は凍結逐語記録として C901 恒久免除済み・対象外）。

| 閾値 | violation | その段で刈る関数 |
|---|---|---|
| 15（現状） | 0 | — |
| 13 | 5 | 5 |
| 11 | 11 | +6 |
| 10 | 24 | +13 |

**12 は飛ばす**（増分 2 件しかなく段として痩せている）。**3 段 = 3 コミット**。

### 逃げ道を作らない規約（今回の決定）

- `per-file-ignores` に C901 の行を**足さない**。前回 drain の規約「新規追加は不可」を維持する
- 刈り切れない関数が出たら、**免除ではなく閾値をその段で止める**。止めた理由を
  `.claude/verify.md` に日付つきで記録し、閾値は下がった分だけ確定させる

## 段 1: 15 → 13（5 関数）

**リスク順に並べ、危ない 2 本を先に試す**（後回しにすると、最後の 1 本が刈れないだけで
段全体が 15 のまま無駄になる）。

| # | 関数 | 現 | 分解方針 | 直接テスト |
|---|---|---|---|---|
| 1 | `verification_parse.py::_classify_positions` | 15 | `_place_gap_ops` / `_place_marks` を抽出（各々 abstain 時 `None` を返す）。**abstain 条件と collapse/曖昧性判定は親に残し 1 バイトも触らない** | 名前直接は 0。`TestCodeParse` の round-7/8/9 guard-abstain パラメトリで挙動被覆 |
| 2 | `cli/skill_archive.py::_apply_archive_plan` | 15 | `_recheck_source(plan) -> str \| None`（TOCTOU 3 ゲート）と `_resolve_destination(plan, text)`（衝突ガード + destination 系 refusal）を抽出。**ヘルパは `plan` を受け取る — `source` / `data_root` を引数に戻さない**（docstring 明示、`test_a_plan_is_never_applied_with_a_different_source` が pin） | `tests/test_cli_skill_archive.py` 70 件、`TestArchivePlanAgreesWithTheRun` が直接呼ぶ。強い |
| 3 | `verification_parse.py::_scan` | 15 | `_merge_candidates(atoms, i)`（マージ窓）と `_event_from(result, i, last)`（6 way kind ディスパッチ）を抽出 → 親 ~6 | 名前直接は 0。`test_verification.py`(77) + `test_verification_chaos.py`(26) で end-to-end 被覆 |
| 4 | `scripts/value_layer_due_check.py::build_reading` | 15 | `_identity_section` / `_constitution_section`（`patterns_since` 込み） / `_rules_section` を抽出。**`patterns_loader` の呼び出しは `amend_last is not None` 分岐の内側に残す**（>100MB knowledge.json / ~1.5GB peak RSS、`test_patterns_loader_is_lazy` が pin） | `tests/test_value_layer_due_check.py` 40 件、~20 が直接呼ぶ。強い |
| 5 | `scripts/cross_day_duplicate_scan.py::collect` | 14 | `_published_from_line(raw) -> Published \| str`（成功はレコード、失敗は理由コード）を抽出 → 親はファイルループ + `Counter` で ~4。**ヘルパは理由コードだけを返す。本文を返さない**（ADR-0083 の出力境界） | `tests/test_cross_day_duplicate_scan.py` 36 件、~20 が直接呼ぶ。強い |

### #1 に関する既知の反論（着手前に読む）

ADR-0062 の 10th amendment（`docs/adr/0062-create-time-verification-handshake.md:283-300`）は
`_classify_positions` を「rule table 化しなかった意図的な例外」として記録しており、
docstring（:1134-1141）も同じことを言う。また、tail signal を 2 箇所で導出した過去版が
サーバ拒否 2 件を出した経緯も残っている。

ただしその反論が守っているのは **「tail signal の導出を 2 箇所に分けるな」** であって、
1 関数内の配置ループを抽出することは該当しない。したがって:

- 抽出は placement ループ 2 本のみ。導出ロジックの複製・移動はしない
- 受け入れ基準は差分リプレイ **mismatch 0**（下記）。1 件でも出たら revert する
- revert になった場合は **段 1 全体を諦めて 15 に据え置き**、理由を `verify.md` に日付つきで
  記録して終了する（免除は足さない = 今回の決定）。その時点で ADR-0062 を根拠にした
  規約改正を検討するかは著者判断であり、このプランでは決めない

## 段 2: 13 → 11（+6 関数）

構造的に素直な順（安全側）:

- `core/insight.py::extract_insight` (13) — 事前ガード連鎖を `_prepare_batches(...) -> tuple[...] | str`
  へ、ログ末尾を `_summarize(...)` へ。**`str` センチネル channel を保存する**
  （error string が `InsightResult` になると呼び出し側が `.last_insight` marker を
  進めてしまい、バックエンド障害が増分窓を食う）
- `scripts/value_layer_approval_join.py::build_reading` (13) — 大ループを
  `_select_rows(records, section, start, end)`（frozen dataclass を返す）と `_cap_rows(...)` に分割。
  **`approved_by_hash` は window filter より前に埋める / 退役行は orphan 側だけから除く**（named test あり）
- `scripts/retrieval_recall_measure.py::cosine_rankings` (12), `build_pairs` (12)
- `core/selection_metrics.py::_scan_selection_window` (12)
- `core/insight_novelty.py::_load_known_themes` (12)

## 段 3: 11 → 10（+13 関数、すべて 11）

`adapters/moltbook/`: `submolt_scope.scan_submolt_scope` / `feed_manager.run_cycle` /
`client.post_comment` / `client._record_api_outcome` / `client._parse_rate_headers` /
`verification.py::_load_rejected_answers` / `verification_parse._poison_broken_tens_compound`
`core/`: `never_selected_metrics.format_never_selected_report` / `report._parse_log`
`cli/`: `adopt._print_system_budget_for_staged` / `session_cmds._handle_report`
`adapters/meditation/pomdp.classify_outcome` / `evals/dataset.load_dataset`

## リファクタの規律（全段共通）

- **挙動保存が唯一の目的**。仕様変更・「ついでの改善」を混ぜない
- 手段は guard clause 早期 return / ヘルパ抽出 / dispatch テーブル化。前回 drain と同じ
- 着手前に対象関数のテストを確認する。private helper は公開呼び出し口経由で実質被覆されて
  いることが多いが、`_scan_selection_window` / `cosine_rankings` / `_handle_report` /
  `_poison_broken_tens_compound` は名前ヒットが 0 だった。呼び出し口の被覆を確認し、
  足りなければ**先に characterization test を書いてから**刈る
- `scripts/value_layer_due_check.py` / `value_layer_approval_join.py` /
  `cross_day_duplicate_scan.py` は一発計測でなく **無人 weekly チェーンの production 経路**
  （`weekly-pipeline.sh:617` / `weekly-analysis.sh:201` / `:455`）。回帰は「静かに間違った週次読み値」
  として出るので、リファクタ後に実データで 1 回手動実行し、出力が変更前と一致することを確認する

## 変更ファイル

- `pyproject.toml` — `max-complexity` を段ごとに 13 → 11 → 10。上部コメントの
  「10 は却下」記述を、免除前提の話だったと分かる形に更新
- `.claude/verify.md` — C901 節に段ごとの日付つき記録（閾値・刈った関数・再実測分布）。
  消費済みの「免除リストが空になった時」トリガーを書き換える
- 上記 24 関数のソース（＋必要なら characterization test）

## Verification

各段のコミット前に:

```bash
# 予算が実際に通ること
uv run ruff check src/ tests/ scripts/ evals/

# 分布の再実測（verify.md に記録する読み値）
uv run ruff check --isolated --no-cache --output-format json --select C901 \
  --config "lint.mccabe.max-complexity=0" -- src tests scripts evals

# repo ゲート一式（format / lint / pyright / import-linter / bandit / pip-audit / pytest 3714 件）
.claude/verify.sh

# verification_parse.py を触った段（= 段 1 と段 3）のみ。mismatch 0 が受け入れ基準
python3 docs/evidence/adr-0062-parser-rewrite/differential_replay.py
```

加えて `git diff` を code-reviewer に通す（決定論ゲート全 PASS でも Review agent は省略不可）。
`skill_archive.py` を触る段 1 は security-reviewer も回す（ADR-0097 の containment ゲート）。
