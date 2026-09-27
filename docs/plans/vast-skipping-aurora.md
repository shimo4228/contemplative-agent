# 予算系 lint（C901）導入プラン — contemplative-agent

## Context

ハーネス ADR-0056（2026-08-28 accepted）が「予算系 lint は既定に頼らず明示的に問う」を
verify-bootstrap の但し書きとして規約化した。この repo は verify.sh 保有 3 repo の 1 つで、
pyproject の `select` を明示 pin しているため予算系（C901 / PLR09x）は現在ゼロカバー。
本プランは同規約をこの repo に適用する — Ruff 内蔵 rule の select 追加のみ、ツール新設なし。

規約の正本: `~/.claude/docs/adr/0056-budget-lints-as-verify-bootstrap-annotation.md` と
skill `verify-bootstrap` Step 2 / 3 / 5（読了済み）。免除境界の原則は skill `review-to-lint`
（「ゲートを初日に赤くする lint は免除境界の設計ミス」）。

## 実測（2026-08-28、repo lock 版 ruff 0.16.0、対象 = verify ゲートと同じ src/tests/scripts/evals）

- **C901**: 関数 4,580 件、p50=1 / p90=3 / p95=5 / **p99=10** / **max=35**
  （`core/never_selected_metrics.py:254 read_never_selected`）
- violation 数: >10 → **36 件 / 24 ファイル**、>15 → **13 件 / 11 ファイル**、>20 → 7 件
- **PLR09x**（既定閾値）: PLR0913=80 / PLR0912=23 / PLR0911=16 / PLR0915=12
- 計測コマンド: `uv run ruff check --isolated --no-cache --output-format json --select C901 --config "lint.mccabe.max-complexity=0" -- src tests scripts evals`

## 採用する rule と閾値

**C901 一本、`max-complexity = 15`。**

分布根拠:

- p99=10 なので 11–15 帯（23 関数）はこのコーパスの「密だが正常」な尾部
  （計器の read/report 関数群）。外れ値バンドは >15 の 13 件 — ADR-0056 の 9 repo 実測でも
  「C901 > 15 は全て production コード」で、genuine outlier の境界と一致する
- 閾値 10 だと免除リストが 24 ファイルに膨らみ、`moltbook/client.py` / `feed_manager.py` /
  `core/insight.py` / `core/report.py` 等、今後の編集が集中するモジュールが盲点化する。
  15 なら免除は 11 ファイルに収まる

## ratchet の要否 — warn 段は置かず、免除リスト方式で初日から error

- Ruff は verify ゲート内で常に block（warn モードが無い）。warn 段を作るには verify.sh に
  advisory 経路を足すことになり、verify.sh 編集 = 人間の hash 再承認 + 機構増 — 避ける
- 代わりに **既存違反 13 件を `per-file-ignores` で理由付き免除**（verify-bootstrap Step 3
  「例外は設定ファイルの許可リストで理由付き」の Ruff-native 形）。初日は green、
  新規コードには即日 15 が効く。**drain = 免除行の削除**で進捗が可視
- drain 自体は本タスクの範囲外（動作中の計器関数 13 本のリファクタは回帰リスクを持つ別作業。
  該当ファイルを修理で触ったときに opportunistic に刈る）

### drain 対象一覧（= per-file-ignores に載せる 11 ファイル / 13 関数）

| file | C901 実測値 |
|---|---|
| `src/.../core/never_selected_metrics.py` | 35 |
| `src/.../core/selection_metrics.py` | 31, 26 |
| `src/.../adapters/moltbook/submolt_scope.py` | 30 |
| `src/.../cli/adopt.py` | 28 |
| `src/.../cli/schedule.py` | 28 |
| `src/.../cli/remove_skill.py` | 21 |
| `src/.../adapters/moltbook/verification_parse.py` | 20 |
| `scripts/coselection_families.py` | 19 |
| `scripts/retrieval_recall_measure.py` | 18, 18 |
| `scripts/observation_ledger.py` | 17 |
| `evals/run_eval.py` | 17 |

## 変更骨子

### 1. `pyproject.toml`（これだけでゲートに効く — verify.sh は無変更 = hash 再承認不要）

```toml
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "B", "I", "T20", "UP", "C901"]

[tool.ruff.lint.mccabe]
# 予算: 上げずに刈る — 変更は .claude/verify.md に日付つき理由 (ADR-0056 準拠)。
# 2026-08-28 実測: 4,580 関数、p99=10 / max=35。>15 の既存 13 件は per-file-ignores で
# 免除（免除行の削除が drain。閾値 10 は免除が 24 ファイルに膨らむため不採用）
max-complexity = 15

[tool.ruff.lint.per-file-ignores]
# --- C901 免除 = drain 台帳（2026-08-28 導入時の既存違反。刈ったら行を消す。追加は不可）---
"src/contemplative_agent/core/never_selected_metrics.py" = ["C901"]  # 35
# …（上表の 11 ファイル分。既存 T20 エントリとは union されるので併存可）
```

コメントに閾値行の「上げずに刈る」規約・分布 as-of・免除の凍結（新規追加禁止）を明記。

### 2. `.claude/verify.md` — 予算系 entry を追記（Step 5 規約）

「category 別」表の lint 行の下に節を追加:

- tool: ruff C901（select 追加のみ、既存 lint ゲートで発火）
- 閾値: `max-complexity=15` — p99=10 / max=35、>15 で 13 件（2026-08-28 実測、対象 =
  src/tests/scripts/evals、計測コマンド付き）
- 選定日: 2026-08-28
- 免除: pyproject の per-file-ignores が正本（drain 台帳。ここに複製しない）
- 捨てた選択肢: 閾値 10（免除 24 ファイルで盲点過大）/ PLR09x（0913 は 80 件で drain
  コスト過大、0912/0915 は C901 と hotspot がほぼ重複 — C901 一本）/ ファイル LOC 予算
  （Ruff に rule が無い astral-sh/ruff#970、9 repo 実測で violation の過半が test —
  別ツール導入は ADR-0056 の「増えるのは config の行だけ」に反する）
- 再調査トリガー: 12 ヶ月経過 / 免除リストが空になった時（閾値引き下げを分布再実測で検討）/
  ruff の cognitive complexity（astral-sh/ruff#2418）実装時（指標を引き直す）/
  閾値引き上げによる回避を観測した 1 回目（ADR-0056 Review-when — ハーネス側規約の再訪）

### 3. 触らないもの

- `.claude/verify.sh` — 無変更（ruff は pyproject を staged / full 両モードで自動参照）
- repo ADR — 起票しない（判断はハーネス ADR-0056 の適用。記録は verify.md が Step 5 の指定先）
- CLAUDE.md — 不変（鮮度規約の対象はパイプライン機構。lint 詳細は verify.md の層）

## 実行体制

**実装チェーンは Opus subagent に委任する**（オーナー指示 2026-08-28）。承認後、
Fable（本セッション）はこのプランを packet として Agent tool（model: opus）へ渡し、
Opus が pyproject / verify.md の編集・probe 発火実証・verify.sh 両モード実行までを行う。
Fable は検収（実測値と免除リストの突き合わせ、early red ゼロの確認）と commit 判断のみ持つ。

## Verification

1. `uv run ruff check src tests scripts evals` → **exit 0**（early red なしの実証）
2. 発火実証（verify-bootstrap Step 4「PASS するだけの確認は証拠にならない」）:
   免除外ファイルに複雑度 16 の probe 関数を一時注入 → C901 発火を確認 → probe 削除。
   免除ファイル内でも 1 回発火しないことを確認（union の動作確認）
3. `.claude/verify.sh --staged`（pyproject を staged に含めて）と引数なし full を各 1 回 →
   両モード PASS
4. commit（main 直、push まで — feedback: push-workflow）

## 補足

- PostToolUse autofix hook は PATH/uvx の ruff を使うが、C901 は autofix を持たず
  select は pyproject で共有されるため木の二層化は起きない
- 「免除リストへの新規追加禁止」はコメントによる運用規約（機械強制なし）— ADR-0056 と同じ
  立て付けで、回避 1 回目の観測で再訪
