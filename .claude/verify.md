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
| lint | ruff check（rule set は pyproject で明示 select） | staged + full | block |
| type check | pyright | full | block |
| architecture | import-linter（ADR-0001 / ADR-0015 の依存方向） | full | block |
| security (SAST) | bandit `-ll -ii` | staged + full | block |
| dependency | pip-audit（project venv を直接監査） | full | block |
| test | pytest（+ pytest-cov / hypothesis） | full | block |
| shell | shellcheck `-S style` | staged + full | block |
| markdown | markdownlint-cli2 | staged | **advisory**（未導入なら skip） |

### 選定理由と再調査トリガー

**format / lint — ruff**
2026-07 時点で後発の代替なし。0.16 系で既定ルールが 59 → 413 に拡大したが、この repo は
`select` を明示 pin しているため影響は限定的（版を上げる時は `ruff check --diff` で差分確認）。
再調査: 12 ヶ月経過 / ruff に代わる標準の出現。

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

**markdown — markdownlint-cli2（advisory）**
346 本の .md に初日から block を掛けると回避の作法が育つので **ratchet 中**。
commit 境界でのネットワーク取得を避けるため `npx --no-install`（未導入なら skip して告げる）。
日本語 prose の文法チェック（textlint + preset-ja-technical-writing）は false positive が
多く advisory 運用が前提になるため、markdown 構造の drain が済むまで導入しない。
昇格条件: 既存 .md の違反を drain し切ったら `check` に上げる。

## 導入時に見つかった既存負債（drain 対象）

| 項目 | 内容 | 状態 |
|---|---|---|
| format | `ruff format` 未適用のファイルが repo 全体に存在（`ruff check` だけ運用されていた） | 未対応 |
| shell SC1125 | `scripts/weekly-pipeline.sh:413` の `# shellcheck disable=SC2086 — ...` は em-dash で directive が壊れており、**この抑制は一度も効いていない** | 未対応 |
| shell SC2034 | `scripts/pipeline_watchdog.sh:32` の `NOW_EPOCH` 未使用 | 未対応 |
| security B608 | `src/contemplative_agent/core/episode_embeddings.py:140` SQL 文字列構築 — 偽陽性かの人間判断が要る | 未対応 |
| dependency | 4 パッケージに既知脆弱性 7 件 — urllib3 2.6.3 → 2.7.0（PYSEC-2026-141/142）、idna 3.11 → 3.15（PYSEC-2026-215）、pygments 2.19.2 → 2.20.0（PYSEC-2026-2987）、pytest 9.0.2 → 9.0.3（PYSEC-2026-1845） | 未対応 |

これらが残っている間、full mode は FAIL する。staged mode は該当ファイルを触った時だけ止まる。

## CI

未配線。`.github/workflows/` が存在しないため、現状ゲートはローカルのみ。
CI を作るときは **`.claude/verify.sh` を引数なしで呼ぶ 1 job** にする
（CI 用に別のコマンド列を書くと必ずローカルと drift する）。
