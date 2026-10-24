# 機械ゲートの選定記録

入口は [`verify.sh`](verify.sh)（`--staged` = commit 境界 / 引数なし = 全体）。
ツールの版は `pyproject.toml` の `[dependency-groups] dev` が正本。

この記録の目的は **陳腐化を可視化すること**。ツールは数年で入れ替わるので、
「いつ・なぜ選んだか」と「いつ引き直すか」を残す。棚卸しは `~/.claude` の
`verify-bootstrap` skill を audit モードで呼ぶ。

選定日: **2026-07-31**（全 category 共通。調査は search-first 経由）

## category 別

| category | tool | mode | 判定 |
|---|---|---|---|
| format | ruff format | staged + full | block |
| lint | ruff check（rule set は pyproject で明示 select、C901 予算含む） | staged + full | block |
| type check | pyright | full | block |
| architecture | import-linter（ADR-0001 / ADR-0015 の依存方向） | full | block |
| security (SAST) | bandit `-ll -ii` | staged + full | block |
| dependency | pip-audit（project venv を直接監査） | full | block |
| test | pytest（+ pytest-cov / hypothesis） | full | block |
| shell | shellcheck `-S style` | staged + full | block |
| markdown | markdownlint-cli2 | staged + full | block（未導入なら skip） |

### 選定理由と再調査トリガー

**format / lint — ruff**
2026-07 時点で後発の代替なし。0.16 系で既定ルールが 59 → 413 に拡大したが、この repo は
`select` を明示 pin しているため影響は限定的（版を上げる時は `ruff check --diff` で差分確認）。
再調査: 12 ヶ月経過 / ruff に代わる標準の出現。

**lint — 予算系（C901）**（選定日 2026-08-28）
ruff の C901（mccabe）を `select` に足しただけで、既存の lint ゲートがそのまま発火する
（`verify.sh` は無変更 = hash 再承認なし。staged / full の両モードで pyproject が参照される）。
閾値は `[tool.ruff.lint.mccabe] max-complexity = 10`（2026-08-31 に 15 から引き下げ完了。下の
「閾値の推移」を見る）。
実測分布 as-of **2026-08-28**（対象は verify ゲートと同じ src / tests / scripts / evals、
関数 4,580 件）: p50=1 / p90=3 / p95=5 / **p99=10** / **max=35**。violation は
`>10` で 36 件 / `>15` で 13 件。計測コマンド:

```bash
uv run ruff check --isolated --no-cache --output-format json --select C901 \
  --config "lint.mccabe.max-complexity=0" -- src tests scripts evals
```

免除は `pyproject.toml` の `per-file-ignores` が正本（導入時の既存 13 件 = drain 台帳。
刈ったら行を消す、新規追加は不可）。ここには複製しない。
**2026-08-28: 導入同日に 13 件すべてを挙動保存リファクタで drain 完了、免除リストは空**
（最大 hotspot は 35 → 10。docs/evidence/ 配下の 2 件（16 / 20）は凍結された逐語記録なので
刈らない — full ゲートの対象外だが staged モードは stage された .py を全部見るため、
`docs/evidence/**` の per-file-ignores に C901 を恒久免除として明示した。drain 台帳とは別物）。

### 閾値の推移

**2026-08-31: 15 → 13**（3 段計画の 1 段目。到達点は 10、途中の段は 11）。
根拠は上の再調査トリガー「免除リストが空になった時」の発火。刈った 5 関数:

| 関数 | 15 → | 手段 |
|---|---|---|
| `adapters/moltbook/verification_parse.py::_classify_positions` | 9 | 位置づけ 2 パスを `_place_gap_ops` / `_place_marks` へ（`_gap_index` 共有）。abstain 条件と collapse/曖昧性判定は親に残置 |
| `adapters/moltbook/verification_parse.py::_scan` | 8 | マージ窓を `_merge_candidates`、6 way の kind ディスパッチを `_event_from` へ |
| `cli/skill_archive.py::_apply_archive_plan` | 8 | source 側 TOCTOU 3 ゲートを `_recheck_source(plan)`、destination 側 6 ゲートを `_resolve_destination(plan, text)` へ。両ヘルパとも plan だけを受け取る（loose path を渡さない不変条件を維持） |
| `scripts/value_layer_due_check.py::build_reading` | 10 | 層ごとに `_identity_section` / `_constitution_section` / `_rules_section`（+ `_count_patterns_since`）。`patterns_loader` の遅延読みは `amend_last is not None` の内側に残置 |
| `scripts/cross_day_duplicate_scan.py::collect` | 7 | 行単位の fault 分類を `_published_from_line`（成功はレコード、失敗は理由コード、非該当は None）へ |

挙動保存の証拠: `differential_replay.py` が凍結 baseline と 4,963 challenge で **mismatch 0**
（abstain 915 件含む）、`.claude/verify.sh` full 全 PASS。

再実測分布 as-of **2026-08-31**（同じ対象、関数 4,599 件）:
p50=1 / p90=3 / p95=5 / **p99=9** / **max=13**。violation は `>10` で 19 件 / `>11` で 6 件 /
`>12` で 2 件 / `>13` で 0 件。

**2026-08-31: 13 → 11**（2 段目。12 は増分 2 件しかないので段として飛ばした）。刈った 6 関数
（すべて 10 以下まで落とした — 3 段目の目標を先取り）:

| 関数 | 13/12 → | 手段 |
|---|---|---|
| `core/insight.py::extract_insight` | 9 | 前段の窓読み・クラスタリングを `_gather_batches`（error `str` センチネルをそのまま返す）、末尾のログを `_log_extraction_summary` へ |
| `scripts/value_layer_approval_join.py::build_reading` | 4 | 走査を `_select_rows`（frozen `_Selection` を返す）+ `_collect_approved_hash`、cap を `_cap_rows` へ |
| `scripts/retrieval_recall_measure.py::cosine_rankings` | 5 | 行列の退化判定 5 本を `_degenerate_arrays` へ（全部 `EMBEDDING_DEGENERATE` 1 コードに畳まれていたので分岐だけが移動） |
| `scripts/retrieval_recall_measure.py::build_pairs` | 10 | review ごとの候補集約を `_batch_candidates` へ |
| `core/selection_metrics.py::_scan_selection_window` | 4 | 日単位の走査を `_scan_selection_day` +（frozen）`_DayScan` へ。窓全体のコレクションは in-place のまま、日が「足す」スカラーだけ戻す。`_tally_selected` / `_record_reduction` も分離 |
| `core/insight_novelty.py::_load_known_themes` | 3 | 2 ソースを `_skill_file_themes` / `_staged_ledger_themes`（Iterator）へ。空名の扱いは元の非対称のまま（skill 側は通す、ledger 側は落とす） |

再実測分布 as-of **2026-08-31**（2 段目後、関数 4,611 件）:
p50=1 / p90=3 / p95=5 / **p99=9** / **max=11**。violation は `>10` で 13 件 / `>11` で 0 件。

**2026-08-31: 11 → 10（到達）**。刈った 13 関数（すべて 11、1 だけ削れば足りた）:

| 関数 | 手段 |
|---|---|
| `adapters/moltbook/client.py::_parse_rate_headers` | reset ヘッダの解釈を `_parse_reset_header` へ |
| `adapters/moltbook/client.py::_record_api_outcome` | dict body の構造フィールド抽出を `_describe_body` へ |
| `adapters/moltbook/client.py::post_comment` | 曖昧エンベロープの判定を `_comment_envelope`（`None` = 成功とみなす）へ |
| `adapters/moltbook/feed_manager.py::run_cycle` | 2 ソースの収集を `_gather_feed_posts` + `_extend_unseen` へ |
| `adapters/moltbook/submolt_scope.py::scan_submolt_scope` | 3 つの中断ガードを `_abort_verdict` へ（順序保存） |
| `adapters/moltbook/verification.py::_load_rejected_answers` | 行解析を `_collect_rejections` へ |
| `adapters/moltbook/verification_parse.py::_poison_broken_tens_compound` | Arm A / Arm B を `_poison_arm_a` / `_poison_arm_b` へ（docstring が元から 2 アーム構造を宣言していた） |
| `adapters/meditation/pomdp.py::classify_outcome` | 応答収集を `_collect_responses` へ |
| `cli/adopt.py::_print_system_budget_for_staged` | 本文収集 2 ループを `_budget_texts` へ（封じ込め判定はそのまま） |
| `cli/session_cmds.py::_handle_report` | `--skill-selection` の 2 読み値を `_print_selection_readings` へ（2 つの try は**統合しない** — 分離は構造で担保する意図的な設計） |
| `core/never_selected_metrics.py::format_never_selected_report` | strict / dormant の対称な列挙を `_population_lines` へ（WITHHELD が空リストに優先する順序を保存） |
| `core/report.py::_parse_log` | session メタのマージを `_merge_session_meta` へ |
| `evals/dataset.py::load_dataset` | 行の検証を `_validate_record` へ（重複 id だけは行間状態なので呼び出し側に残置） |

到達時点の分布 as-of **2026-08-31**（関数 4,626 件）:
p50=1 / p90=3 / p95=5 / **p99=9** / **max=10**。violation 0 件、免除 0 件。
上位帯は 10 が 26 件 / 9 が 27 件 / 8 が 43 件 — 予算は p99 に一致する位置にある。

**免除は足さない。** 刈り切れない関数が出たら閾値をその段で止め、理由をここに日付つきで記録する
（2026-08-31 著者判断）。「10 は却下」（下の捨てた選択肢）は *導入時の* 閾値としての却下であり、
刈って到達する道は対象外 — 到達時点で免除は 0 件のままなので、却下理由（24 ファイルが盲点）は
発生しない。

捨てた選択肢:

- **閾値 10（導入時の一発設定として）** — p99 と同値まで締めると免除が 24 ファイルに膨らみ、
  `moltbook/client.py` / `feed_manager.py` / `core/insight.py` / `core/report.py` など編集が
  集中するモジュールが丸ごと盲点になる。11–15 帯（23 関数）はこのコーパスでは「密だが正常」な尾部。
  **2026-08-31 追記**: 却下されたのはこの設定の仕方であって 10 という数字ではない。段階的に
  刈って到達する道（上の「閾値の推移」）は免除を 1 件も作らないので、この理由は当たらない
- **PLR09x** — PLR0913（引数数）は既定閾値で 80 件あり drain コストが釣り合わない。
  PLR0912 / PLR0915 は hotspot が C901 とほぼ重複するので、指標は C901 に一本化する
- **ファイル LOC 予算** — Ruff に該当 rule が無く（astral-sh/ruff#970）、9 repo 実測でも
  violation の過半が test だった。別ツールを足すのはハーネス ADR-0056 の
  「増えるのは config の行だけ」に反する

再調査: 12 ヶ月経過 / **10 で 1 度でも「刈れないので上げる」提案が出た時**（規約側の再訪。
上げる前にこの節へ日付つきで理由を書く）/ **9 以下への引き下げを検討するなら 10 帯 26 件が
「密だが正常」かを先に実測してから**（2026-08-28 の「免除リストが空になった時」と
「閾値が 10 に到達した時」は 2026-08-31 に消費済み）/
ruff が cognitive complexity（astral-sh/ruff#2418）を実装した時（指標を引き直す）/
**閾値引き上げによる回避を観測した 1 回目**（ハーネス ADR-0056 の Review-when — 規約側の再訪）。

**lint — 境界型強制（ANN 系）**（選定日 2026-08-31）
verify-bootstrap skill の LLM-first 4 軸（harness 棚卸し 2026-08-31）との照合で、軸 4
「境界の明示型強制」だけが gap だった（pyright は明示 mode なし = standard で、注釈の
存在は強制しない）。`ANN001-003`（引数）+ `ANN201`（戻り値）+ `ANN401`（裸の `Any` 禁止）を
select に追加。ANN202/204-206 は非選択（明示 pin の方針 — family でなく個別に議論して足す）。

実測 as-of **2026-08-31**: production 側（src / scripts / evals）は ANN001-003/201 が
**違反 0**（コードは既に完備 — ゲートは現状凍結）。ANN401 は 24 件 / 9 ファイルで、
導入同日に**免除ゼロ・inline noqa ゼロ・挙動保存**で drain 完了:

- `object` 置換 13 件（untrusted JSON 境界は narrowing 済みで下流無影響。`_is_int` は
  TypeGuard、`log_published` の `*args`、scripts の `raw_ts` / `**extra` 含む）
- `np.ndarray` 2 件（`retrieval_recall_measure._degenerate_arrays` — TYPE_CHECKING import で
  遅延 import 方針を維持）
- TypeVar 化 2 件（`state_invariant_check._load_typed`）
- union 記載 1 件（`memory_cmds._handle_single_result` → `str | IdentityResult | AmendmentResult`）
- TYPE_CHECKING import + facade 宣言への追随 2 件（`memory_repos` の 2 `record` → `Interaction` /
  `PostRecord`。Generic 化は unbound T への属性アクセスと `asdict` stub が Protocol bound を
  要求し機構過剰なので不採用）
- **難所 4 件 — `client.py` の requests への `**kwargs` パススルーは明示 named params 化**
  （実測で流れるのは `json` と `params` のみ。`timeout` / `allow_redirects=False`（Bearer
  リーク防止）は `_request` 内へ直書きし、呼び出し側から上書き不能に凍結 — 境界強化の副産物）。
  Unpack[TypedDict] は typing_extensions 新依存（requests+numpy のみ方針に抵触）で棄却
- **難所 3 件 — `publish.py` verification 系は annotation-only**（`dict[str, Any] | None` 化、
  runtime 1 バイト不変。handler は既に `dict` 宣言で `.get` を呼ぶ = dict 前提だった）

tests/** は恒久免除（5,810 件 — テスト関数は消費される境界ではない。drain 台帳ではない）。
JSONValue alias は**作らない**: 用途 3 面のみで `object` + narrowing が足り、`dict[str, Any]` が
支配的慣用、core の公開面を増やす対価が立たない（将来 API 境界の型付けを本格化するなら
`core/json_types.py` に再帰 alias が適合位置、という判断だけ残す）。

再調査トリガー: 12 ヶ月経過 / ANN401 で「刈れないので noqa」提案が出た 1 回目（規約側の再訪 —
noqa の前にこの節へ日付つきで理由を書く）/ pyright を strict 化する時（ANN001-003/201 が冗長化
するか再評価）。

**lint — 不活性 noqa（RUF100）**（選定日 2026-10-24、P1-06.10）
`RUF100` を `select` に足した。不活性な `# noqa: BLE001` 6 件（`feed_seeder.py` /
`cli/session_cmds.py` / `cli/stocktake_cmd.py` / `core/constitution_shadow.py` /
`core/llm/guard.py` / `core/memory.py`）は理由コメントだけ残して noqa を外した。ゲートは **src のみ**:
`tests/**` / `scripts/**` / `evals/**` は編集側の既定集合向けの noqa 54 件（E402 / BLE001 / A002 /
S603 ...）を抱えており、wheel の外では害が無いので刈らず `per-file-ignores` で `RUF100` を外した
（ここに日付つきで「残す」と記録）。確認は素の `ruff check src`（`--select RUF100` 単独だと `B` の
noqa まで「非選択」と読まれて 1 件余計に出る）。
既存 alias の畳み込み（同日 1 回限り）: `write_text_atomic` は呼び手 9 本ごと `write_restricted` へ、
`_ATTR_ALIASES` 2 件は `PromptTemplates` の field 名（`STOCKTAKE_DESCRIPTION_PROMPT` /
`STOCKTAKE_DESCRIPTION_SYSTEM_PROMPT`）へ。**「残す」と判断したものは 0 件**。以後の改名・移動は
CLAUDE.md の規約どおり呼び手全部と同じ PR で行い、alias は置かない。

**関数長と拡張複雑度の読み（P1-06.7、2026-10-24。新ルールは足さない）**
C901（上記、予算 10）は分岐の数しか見ない。長さと、boolop・内包・三項を数えた複雑度を
読みとして残す。ゲートにはしない（長さの閾値を足す案は「捨てた選択肢」の PLR0915 と同じ理由で
C901 と hotspot が重なり、重複する指標は足さない）。計測は `src/` の全関数を `ast` で読んだ。

| 指標 | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|
| 関数の物理行数（docstring・空行込み）— 台帳の読み | 16 | 56 | 80 | — | 183 |
| 同上 — 2026-10-24 再計測（関数 1,090 本） | 15 | 55 | 80 | — | 183（`reply_handler._process_reply`） |
| 拡張複雑度 ccx（分岐 + boolop の項 + 内包 + 三項）— 台帳の読み | — | 9 | — | 15 | 22 |
| 同上 — 2026-10-24 再計測（定義はこの表の見出しのとおり） | 3 | 9 | — | 15 | 24 |

ccx の上位（台帳の読み、C901 → ccx）: `distill` 9→22 / `compute_diversity` 6→20 / `_apply_points` 8→19 /
`_classify_positions` 4→18 / `extract_agent_fields` 1→15。**ccx ≥ 18 の 4 本
（`distill` / `compute_diversity` / `_apply_points` / `_classify_positions`）は次にその関数を触る PR で
名前付き述語（`_is_x()`）へ畳み、15 未満にする**（触らない限り動かさない）。
同日の再計測（ブール演算子の数え方が少し違う別実装）では、上の 4 本に加えて
`insight_novelty._filter_novel_batches`（C901 は予算内、ccx 24）と
`submolt_scope.scan_submolt_scope`（ccx 18）が ≥ 18 に出た。定義で順位が入れ替わるので、触る時に
その場で数え直す。

再調査トリガー: **100 行超の関数を新設する PR**（その PR の説明に、なぜ分けないかを 1 行書く）/
上の 4 本のどれかを触った PR（畳んで 15 未満を確認）/ 12 ヶ月経過。

80 行超の関数は 54 本ある。うち最長の 7 本は「密だが正常」: 理由は 1 行ずつ。

- `reply_handler._process_reply`（183）— 返信 1 件の生成・検証・送信・記録を 1 本の順序つき手続きに保っている（途中で抜ける全出口が outcome を記録する）。
- `insight_novelty._filter_novel_batches`（179）— chunk の組み立て・LLM 判定・理由コード付き降格が 1 つのループに閉じていて、分けると理由コードの網が切れる。
- `insight.extract_insight`（163）— 段（novelty → 名乗り → 本文 → 重複判定 → staging）の順序そのものが仕様（ADR-0111）。
- `submolt_scope.scan_submolt_scope`（159）— read-only 計器の 1 回の sweep。書き込み 0 を保つ分岐が 1 箇所に見えている方が検査しやすい。
- `constitution_shadow.synthesize_shadow_constitution`（150）— `amend_constitution` と同じ検索・ガード構造を意図的に写している（比較可能性のため）。
- `feed_manager._post_comment_and_record`（147）— 投稿・記録・ペーシングの全出口が selection の outcome を 1 つ記録する手続き。
- `remove_skill._handle_remove_skill`（147）— 監査ログ・archive/delete・確認の各分岐を 1 本で読める（ADR-0097 D5）。

**ログ水準の規約（P1-06.8、2026-10-24）**
4 行で固定する。`logger.warning` 261 / `error` 16 / `critical` 1（2026-10-24 の計数）の中で、
水準が読み手に何も言わない箇所を作らないための最小の約束。

- **CRITICAL** = 資格情報 / 権限（鍵が使えない、権限を持つべきでない面に触れた）。
- **ERROR** = このセッション（この実行）の目的が達成されない。設定が原因で feed 全体が閉じる、計器の書き込み先が死んでいる、など。
- **WARNING** = 劣化して続行する（個別の投稿のスキップ、フォールバック、再試行）。
- **INFO** = 通常の進行。

2026-10-24 の re-level 2 件（`feed_manager._fail_closed` の閾値未設定、`core/llm` の telemetry
書き込み失敗）は WARNING → ERROR。計器型 `except` の `logger.warning(..., exc)` を
`exc_info=exc` に揃える sweep は **やらない**（延期。トリガー: 当該 handler を fix PR で触る時に
規約どおりに直す。untrusted 本文を含み得る例外は `type(exc).__name__` のみ、`backend.py` の既存規約）。

**import-linter — core 内層契約と計器の隔離（P1-06.2、2026-10-24）**
`[tool.importlinter]` は 6 契約になった（既存 4 + 下の 2）。コードは 1 行も動かしていない:
今ある辺は `ignore_imports` に列挙して pin し、新しい辺だけが赤になる（drain はしない）。

- core 内の層（下から）: `config / _io / text_utils` < `thresholds / prompts / domain` < `llm` < `embeddings`。
  pin 2 件: `domain -> llm`（`validate_identity_content`）/ `llm -> embeddings`（serving-environment の埋め込み
  モデル名）。どちらも循環を避けるための関数内 import。
- 計器 → 判定経路の禁止: `selection_metrics` / `never_selected_metrics` / `skill_confusion` /
  `view_metrics` / `constitution_shadow` を、adapters と `core.skill_selection / insight / distill` から
  import 禁止。pin 3 件: `submolt_scope -> selection_metrics`（`percentile`。`core/_stats.py` は作らない）/
  `distill -> view_metrics` / `insight -> view_metrics`（どちらも報告行を読むだけ）。
  `comment_outcomes.read_*` は module が書き手と同居しているため、この契約には載せていない。
- `ignore_imports` の件数（2026-10-24）: 2 + 3 = **5**。増やす PR は、ここへ日付つきで理由を書く。
- 表面 literal の固定は `tests/test_surface_snapshot.py`（CLI の name + tier / launchd label / env キー /
  prompt の stem 集合 / `KIT_VERSION` / 外向き host / モデル literal の所在）。変更は ADR 追補と同じ変更でのみ。
  `scripts/` と `evals/` の `contemplative_agent` の `_` 名 import は `tests/test_architecture.py` の AST 検査で
  固定（`core.llm` 宛ては 0、他 module 宛て 15 件は pin）。

**scripts の「鏡」4 関数の台帳（D-P1-06-1 = B（owner, 2026-10-24））**
bare `python3` で起動する script（ADR-0109）は package を import できないので、core の 4 関数を
鏡として持つ。A（`scripts/_bootstrap.py` で core を直接 import して鏡を消す）は採らない:
scripts → core の結合が広がり、core を凍結後に触るたびに script が巻き込まれる。鏡は許容し、
ここに台帳として置く。ずれは各 script の parity test が検出する（鏡の docstring に明記済み）。

| 鏡 | 元 | 置き場所 | 固定する test |
|---|---|---|---|
| `_split_frontmatter` | `core.text_utils.split_frontmatter` | `scripts/retrieval_recall_measure.py` | `tests/test_retrieval_recall_measure.py`（parity） |
| `_strip_to_printable` | `core._io.strip_to_printable` | 同上 | 同上 |
| `_skill_theme` | `core.text_utils.skill_theme` | 同上 | 同上（staged ledger 側の結合を含む） |
| `_check_rule_quality`（+ `read_rules_layer` の file rules） | `core.stocktake._check_rule_quality` + `core.text_utils.read_markdown_documents` の file rules | `scripts/value_layer_due_check.py` | `tests/test_value_layer_due_check.py`（verdict ごとの parity） |

`retrieval_recall_measure.py` が P1-04.7 で削除されたら、鏡は 1 本ずつ減る（上の 3 行が消える）。
新しい鏡を足す PR は、この表に 1 行と parity test を同時に足す。

**API 応答の型境界（D-P1-06-2 = B（owner, 2026-10-24））**
`dict[str, Any]` で受ける API 応答（約 153 箇所）に DTO 境界は**置かない**。untrusted JSON は
「形を信じない」規律（`is_valid_id(value: object)` のように `object` で受けて narrowing する）で
扱い、DTO を置くとその規律と緊張する。sibling が消費する面（`LLMBackend` 系）は既に Protocol で
型付き。再調査: 応答形の変化による事故が 2 回続いた時。

**docs/evidence の根本除外（2026-08-31、per-file-ignores の積み増しを終了）**
`[tool.ruff]` の `extend-exclude = ["docs/evidence"]` + `force-exclude = true` でディレクトリごと
検査対象集合から外した（凍結された逐語記録 = データであってコードではない — markdown ゲートの
「検査対象から外したもの」と同じ判定基準）。旧 `"docs/evidence/**" = ["T20", "C901"]` 免除行は
削除 — rule を足すたびに evidence の免除行が増える構造（T20 → C901 → ANN で 3 回目）を閉じた。
これで lint に加えて **format も** 両モードで外れる（per-file-ignores は format に元から効いて
いなかった）。staged モードの bandit も `-x ./docs/evidence` で同基準に揃えた（verify.sh 変更 —
内容 hash の再承認が必要）。実証: 違反入り .py（format 崩し + shell=True + 未注釈）を evidence 配下に
stage して `verify.sh --staged` が PASS、明示パス指定の `ruff check` も excluded。
トレードオフ（許容）: F 系も evidence では見なくなる — 凍結記録は編集されない前提。

**type check — pyright**
Rust 製の後発が実際に来ている（Meta の pyrefly が 2026-05 に v1.0、pandas で pyright 比
約 75 倍高速）が、conformance（型仕様準拠度）が ~58% で pyright を置換する段階にない。
Astral の ty は 2026-07 時点で beta（1.0 は 2026 年内目標）。
再調査: **pyrefly の conformance が 90% 超え or ty が 1.0 到達**。乗り換え時は主軸交代でなく
「高速セカンドチェック併用」から始める。

**security — bandit**
ruff の S ルール（flake8-bandit）で 1 本に減らせないか検討したが、bandit のルール全量が
移植されておらず（暗号系チェック等）、判定ロジックも異なるため検出漏れが出る。
opengrep / semgrep はこの規模には重量級。bandit は 1.9.4（2026-02）、直近更新 2026-07-21。
再調査: ruff S のカバレッジが bandit 相当に到達したら 1 本化。

**dependency — pip-audit（venv 直接監査）**
`pip-audit -r <uv export の requirements>` は隔離 venv 構築中に ensurepip が SIGABRT で
落ちる（2026-07-31 実測）ため、`uv run pip-audit` で project venv をそのまま監査する。
uv 純正の `uv audit` は 2026-06-08 発表で Astral 自身が preview / unstable と明言。
uv-secure は開発側が deprecated 表明済みで採用しない。
再調査: **`uv audit` の stable 化**（したら pip-audit を捨てて一本化）。

**shell — shellcheck `-S style`**
2026-07 時点でも業界標準。shellharden 等は置換でなく補完。
閾値を最も厳しい `style` にした理由: `warning` では未クォート変数（SC2086, info 相当）が
素通りするため。導入時の既存負債は 14 本中 2 件のみで drain 可能な量だった。
再調査: 12 ヶ月経過。

**markdown — markdownlint-cli2（block、2026-07-31 に advisory から昇格）**
ratchet 完了。8099 → 0（内訳は下記「markdown の drain」）。ルール選択と除外の理由は
`.markdownlint-cli2.jsonc` に各項目のコメントとして書いてある（ここに二重に持たない）。
実行可否は **実行ファイルの有無**で判定する — 未導入なら告げて skip し、ネットワーク取得は
起こさない。グローバル導入 (`npm i -g markdownlint-cli2`) かローカル `node_modules/.bin` を見る。

**prose（日本語 textlint）— 導入しない**
2026-07-31 に一度導入して同日撤去した。判断と実測は下記「prose ゲートを見送った経緯」。

## 導入時に見つかった既存負債（2026-07-31 に drain 済み）

導入日に検出した 5 件はすべて解消し、**full mode は exit 0**。以下は「何をどう畳んだか」の記録
（同じ負債が再発したときに、当時どちらに倒したかを引ける形で残す）。

| 項目 | 畳み方 | commit |
|---|---|---|
| dependency（脆弱性 7 件 / 4 パッケージ） | `uv.lock` は gitignored なので lock 更新だけでは clone 先に残らない。`pyproject.toml` に security floor を置いた — dev の `pytest>=9.0.3`、および直接依存でない 3 件（urllib3 / idna / pygments）は `[tool.uv] constraint-dependencies` で表現（直接依存に昇格させない） | `67c29e0` |
| security B608 | **偽陽性**（f-string に入るのは `?` とカンマのみ、値は全てバインド済み）。`# nosec` で黙らせず、id を接続ローカルの TEMP テーブルへ stage して `IN (SELECT ...)` で引く形にし、全ステートメントを定数化。副産物として `SQLITE_MAX_VARIABLE_NUMBER` のチャンク分割ロジックが不要になり削除 | `bcd8601` → `26d0e14` |
| shell SC1125 / SC2034 | directive を単独行に分離し説明を別行へ（抑制が本来の意図どおり有効化）。`NOW_EPOCH` は参照ゼロにつき削除 | `edc1d55` |
| format | `ruff format` を src / tests / scripts に一括適用（41 files）。全変更ファイルの AST が commit 前後で同一であることを確認したうえで、`.git-blame-ignore-revs` に SHA を登録 | `e7928c0` |

### drain 中に見つかった gate 自身の欠陥

| 項目 | 内容 | commit |
|---|---|---|
| staged mode の I001 偽陽性 | staged mode は index を tmpdir へ**部分展開**するため、src 本体を含まず test だけを stage した commit では ruff の isort が `contemplative_agent` を third-party に誤分類し、full mode が正とみなす import 順に I001 が出る（実測 14 件）。`[tool.ruff.lint.isort] known-first-party` を宣言して、分類をファイルシステムの実在から切り離した。`verify.sh` 側は無変更 | `7ef9c92` |
| markdown 未導入判定の破綻 | 「未導入なら skip して告げる」を npx の失敗メッセージの文字列照合（`*"npm ERR"*` 等）で実装していたが、npm が表記を `npm error` に変えたため照合が外れ、**配管エラーが `[markdown advisory]` として lint 指摘の顔で出ていた**。実行ファイルの有無で判定する形に変更（ツールの出力文言に依存する判定を残さない） | 下記 |

この種の「full mode は通るが staged mode だけ落ちる」は、部分展開が前提を欠くことに起因する。
同型の症状（設定ファイル不在による既定値判定、パッケージ解決の失敗）を見たら、まず
**tmpdir に何が無いか**を疑う — 検出内容そのものより先に。

### drain 中に review が拾った回帰（決定論ゲートは全 PASS だった）

B608 の解消は当初 `json_each()` で行い、ruff / pyright / bandit / pytest はすべて PASS した。
python-reviewer が指摘したのは **json1 が SQLite 3.38+（2022）でのみ既定ビルトイン**という点で、
この repo は `requires-python >=3.10` の配布パッケージであり `sqlite3` はホストの libsqlite3 に
リンクする（Ubuntu 22.04 = 3.37 / Debian 11 = 3.34）。旧来の `IN (?,?,...)` はどのビルドでも
動いていたので、lint の指摘 1 件と引き換えに読み取りホットパスの移植性を落としていた。
TEMP テーブル方式へ差し替えて解消。

**教訓**: 「ゲートを黙らせる書き換え」は、ゲートが見ていない軸（配布先の実行環境、
依存の可用性）を代償にしうる。決定論ゲートの全 PASS は review の代替にならない。

## markdown の drain（2026-07-31、advisory → block）

| 段階 | 違反数 |
|---|---|
| 既定ルールのまま | 8099 |
| `.markdownlint-cli2.jsonc` 適用後 | 593 |
| `--fix` 適用後 | 96 |
| 手作業 drain 後 | **0**（214 ファイル） |

内訳の大半は MD013/line-length 6151 と MD060/table-column-style 1157 で、どちらも
レンダリング結果に影響しない層（前者は 200 字閾値でもなお 1821 件で、長さは意図的）。
残り 96 件は MD040（コードフェンスの言語指定）71・MD036（太字の疑似見出し）10・
MD041（1 行目が h1 でない）15 で、MD040 は 1 件ずつ中身を読んで
`text` / `bash` / `yaml` を割り当て、MD036 は ADR-0007 の `**N. …**` を h3 に変換、
MD041 は「h1 の上に言語切替行を置く二言語規約」なのでルール側を無効化した。

### auto-fix に判断を任せて壊した 3 件（適用前に検分して差し戻し）

| ルール | auto-fix がやったこと | なぜ壊れるか |
|---|---|---|
| MD038 | `` `- ` `` → `` `-` `` | ADR-0062 の「`- ` パーサー破損」の記述で、**空白そのものが記述対象**だった |
| MD029 | `4. 5. 6.` → `1. 2. 3.` | 先行する列挙の続きとして意図的に 4 から始めていた |
| MD004 | `- ` → `+ ` | 既定 `consistent` は**ファイル内で最初のマーカー**に合わせるため、repo 全体ではむしろ不揃いになった |

3 件とも設定側で無効化・固定した（`MD004` は `"style": "dash"` に固定）。
これはハーネス側 rule `common/patterns.md` の enumerate / decide 分割そのもので、
**lint は列挙して報告するところまで、どれを採るかは判断**に属する。auto-fix は
「機械には見えない軸」（その空白が有意か、その番号が参照されるか）で静かに壊す。

### 検査対象から外したもの

`config/prompts/**`・`config/templates/**`（LLM が読む固定 apparatus であって document ではない
— プレースホルダ `<answer>` が MD033 として上がる）、`docs/evidence/**`（起きたことの逐語記録。
実測で `--fix` がモデル出力サンプルから行末空白を落とした）、`integrations/skills/**`（ADR-0013 で
棚上げ・gitignored。repo が所有しない資産をゲートで縛ると clone 先で FAIL しうる）、
`.venv/**`・`**/*.local.md`。判定基準は **repo が所有し、かつ document であるか**。

## prose ゲートを見送った経緯（2026-07-31）

textlint + preset-ja-technical-writing を一度導入し、同日中に**過剰適用として撤去**した。
同じ提案を繰り返さないよう、測った数字だけ残す（対象は日本語を含む tracked .md 107 本）。

| 構成 | 違反数 |
|---|---|
| preset 全体 | 2629（`sentence-length` が 1795） |
| 意見の層を落とした構造サブセット | 38 |
| 偽陽性を出すルールも落とした構成 | 0 |
| 上に「文体混在」を足した最終構成 | 0 |

**preset をそのまま入れる案は否定された。** 落とした層の内訳:

- `sentence-length` — max=300 まで緩めても 109 件。密度の高い文はこのコーパスの文体そのもの
- `ja-no-mixed-period` — 195 件 / 75 ファイル。「箇条書きに句点を打たない」という一貫した記法
- `no-doubled-joshi` — 254 件。著者の文体であって欠陥ではない
- `no-unmatched-pair` 25 件 / `ja-unnatural-alphabet` / `ja-no-successive-word` — **全て偽陽性**。
  順に、日本語 prose を手で折り返すので `（` が行末で `）` が次行に来る／「経路 a、b、c」の
  列挙ラベル／`docs/glossary.md` の中国語訳カラム（反事实实验）

残ったのは「目で気づけない文字化け」（半角カナ / ゼロ幅スペース / NFD / 制御文字 / ら抜き）と
「1 doc 内の文体混在」で、導入時の違反は 0 件だった。有効ルールは違反注入で発火を確認しており
機能はしていたが、**得られるものに対して機構（依存 2 つ、設定 2 ファイル、ゲート 1 段）が
重すぎる**という判断で撤去した。

派生的に分かったこと（再調査時に有用）:

- 日本語 tracked .md 107 本のうち **106 本が である で一貫し、`README.ja.md` だけが ですます で
  一貫**していた。文体の規約は既に守られている
- textlint の既定は 本文=ですます / 箇条書き=である という**独自の意見**を持つ。規約どおりに
  書かれた `README.ja.md` が 18 件上がるので、既定のまま使うことはできない
- **textlint 15.7 の `overrides` はルール option の上書きに効かない**（files パターン 4 種で確認）。
  per-file に文体を切り替える設定は書けない

再検討の条件: 上記の構造的な文字化けが実際に混入し始めたとき。あるいは preset ではなく
`textlint-rule-prh` で **自分の規約**（固有名詞の表記、glossary の訳語）を強制する形なら、
既存の Voice 規約と競合しないので別途検討してよい。

## 棚卸し履歴

**2026-08-31 audit（verify-bootstrap --audit）— 全 category 据え置き、乗り換えなし。**
stack 不変（py 231 / sh 18 / md 456、新生態系なし）。verify.sh / verify.md は git 追跡済み。
イベントトリガーの照合結果:

| トリガー | 読み値 as-of 2026-08 | 判定 |
|---|---|---|
| ty 1.0 到達 | beta のまま（0.0.x、最終リリース 2026-08-26） | 未発火 |
| pyrefly conformance 90% 超え | 一次ソース（pyrefly 公式 blog）は **87.8%**（2026-03 計測、pyright 97.8%）。二次 blog に「97% 超え」の主張があるが一次で未確認 | **境界上**。発火しても手順は「高速セカンドチェック併用」であり主軸交代ではない — pyright 据え置き。次回 audit で一次の再計測値を見る |
| `uv audit` stable 化 | 依然 preview / unstable（`--preview-features audit` ゲート） | 未発火 — pip-audit 据え置き |
| ruff cognitive complexity（#2418） | OPEN のまま（最終更新 2026-01） | 未発火 — C901 据え置き |
| ruff S の bandit カバレッジ到達 | parity issue #20129 が open。flake8-bandit 上流が停滞し B324 / B613 / B614 / B615 / B703 等が未移植 | 未発火 — bandit 据え置き |

時間トリガー（12 ヶ月経過: ruff / shellcheck）は選定 1 ヶ月時点で未達。

## CI

未配線。`.github/workflows/` が存在しないため、現状ゲートはローカルのみ。
CI を作るときは **`.claude/verify.sh` を引数なしで呼ぶ 1 job** にする
（CI 用に別のコマンド列を書くと必ずローカルと drift する）。
