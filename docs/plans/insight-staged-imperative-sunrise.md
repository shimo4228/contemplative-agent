# insight staged バッチ（2026-07-25、78 件）の採否

## Context

2026-07-25 の weekly `insight --stage`（ADR-0074）が **78 件**を `.staged/` に積んだ。これは T-INSIGHT-OBS (c)「修理後の次回週次」の観察窓であり、同時に採否の人間ゲートでもある。前回 2026-07-18 は 106 件 → **0 採用 / 106 却下**。

### 読み（監査ログの実測）

`logs/insight-novelty.jsonl` の当該 run（2026-07-24T23:02 / 23:03 UTC）:

| 指標 | 値 | 意味 |
|---|---|---|
| verdict | `judged` × 2 チャンク（batch 0/2, 1/2） | **chunking 修理は機能**。fail-open ゼロ（前回は `fail_open_llm`） |
| known_themes | 166 | 却下 106 件が ledger の known に入っている |
| clusters | 66 + 31 = 97 | |
| covered | 12 + 1 = **13（13.4%）** | 既知テーマによる抑制は弱い |
| staged | 78 | 生存 84 − 抽出失敗 ~6（T-EXTRACT-TITLE 系、~7%） |

→ **T-INSIGHT-NOVELTY の再評価入力はこれで揃った**: chunking（案 A）は容量問題を解いたが、**既知テーマ照合という軸自体が抑制軸として弱い**。理由は 2 つ:

1. novelty gate は「既知テーマ vs 候補クラスタ」しか見ず、**候補どうし（intra-batch）の重複を判定しない**（`insight_novelty.py:320` `_filter_novel_batches`）。
2. 判定材料が name+description の文字列であり、**メタ動作の同一性**を見ていない。

### 内容の質（78 件全部の description を精査した結果）

約 6 割が同一のメタ動作の言い換え —「表層／抽象／成果／指標 から 構造・制約・境界・機構・出自 へ焦点を移す」。description の動詞が `Shift / Shifting / Pivot / Pivoting / Reorienting / Redirecting / Switching / Elevate / Refocusing` で始まるものが 40 件超。既存 19 件にも同族が 6 件ある（`constraint-shift-analysis-pivot-point-identificati`, `detecting-abstract-to-operational-constraint-shift`, `anchoring-abstraction-to-measurable-constraints`, `structure-authority-tracing`, `scope-failure-diagnosis`, `mapping-epistemic-boundaries`）。

バッチ内の露骨な重複ファミリー例:
- 境界: `tracing-system-boundaries` / `pinpointing-conceptual-boundaries` / `examining-system-boundaries-for-embedded-drift` / `identifying-boundary-maintenance-mechanisms` / `assumptions-governing-boundaries-audit` / `analyzing-structural-boundaries-in-technical-dicho`
- 制約: `identifying-structural-constraints` / `structural-constraint-analysis` / `grounding-abstract-critique-in-system-constraints` / `grounding-abstraction-with-structural-mechanics` / `formalizing-constraints-from-conceptual-discussion` / `detecting-structural-systemic-limitations` / `isolate-system-limitations`
- 権威・出自: `auditing-structural-authority-gaps` / `shifting-focus-to-authority-constraint-modeling` / `structural-audit-of-accountability-claims` / `identifying-systemic-provenance-deficits`（既存 `structure-authority-tracing` / `validating-provenance-chains` と重なる）
- 確実性: `deconstruct-certainty-mechanism` / `deconstructing-claims-of-system-certainty` / `diagnosing-rhetorical-vs-structural-claims` / `structural-critique-of-assurance-gaps`（既存 `deconstructing-confidence-proxies` と重なる）

これは register collapse（MEMORY: `stocktake-grouping` / T-UTIL-SELECT の echo 懸念）の可視化。全採用は skill 数 19→97、ADR-0081 の pass-1 カタログが 5 倍になり、**ほぼ同文の description が並ぶためセレクタ精度を直接損なう**（ADR-0081 が description 監査を入れた理由そのもの）。ロールバックは無い（`remove-skill --reason` による前進的削除のみ）。

## 判断（ユーザー確定済み）

**選別採用 4〜5 件 / 残り 73〜74 件 reject。** 採用するのは「構造へのピボット」族**でない**少数派のみ — 語彙の単一栽培を薄める方向に働き、次回 stocktake の description 監査の材料にもなる。

### 採用候補（5 件）

| ファイル | 採用理由（既存・同バッチとの差分） |
|---|---|
| `pre-processing-state-validation-20260725.md` | 分析レンズでなく**自分の手続き**（探究前に既定フレームを意図的に停止）。同族なし |
| `subjective-attention-calibration-20260725.md` | 外部記録の検証でなく**自分の理解機構の監視**。自己指向で既存に無い |
| `handling-non-optimizable-concepts-20260725.md` | 最適化不能な対象で**予測効用でなく接続の持続**へ切る。価数が他と逆 |
| `pivot-accountability-from-record-to-action-20260725.md` | 診断・文書化で停滞した議論を**行動要求で断ち切る**。分析でなく介入 |
| `affirm-cognitive-possibility-20260725.md` | 曖昧さを欠損でなく**素材**として肯定。`defining-structural-residue-meaning` / `operationalizing-systematic-absence` と 3 者重複するので**この 1 件だけ**採る |

残り 73 件はすべて reject。

## 実行手順

1. **順序の確定**（最重要）— `adopt-staged` は 1 件 1 プロンプト（`_approve_write`、`cli/adopt.py:159`）で、順序は `_staged_sort_key` = `(meta.seq, meta ファイル名)`（`adopt.py:186`）。まず読み取り専用で処理順を出力する:
   ```bash
   python3 - <<'PY'
   import json,pathlib,sys
   d=pathlib.Path.home()/".config/moltbook/.staged"
   metas=sorted(d.glob("*.meta.json"),
       key=lambda p:(json.loads(p.read_text()).get("seq", sys.maxsize), p.name))
   for i,m in enumerate(metas,1): print(i, json.loads(m.read_text())["seq"], m.name)
   PY
   ```
2. **y/n 列の生成** — 上の順序に対し、採用 5 件の位置だけ `y`、他は `n` の 78 行を作る（機械生成し、目視で `y` が 5 個・行数 78 であることを確認）。
3. **投入** — `--yes` は**使わない**（全件自動承認になる）。非 TTY での piping は 2026-07-09 の実績経路:
   ```bash
   printf 'n\ny\n...' | contemplative-agent adopt-staged
   ```
   実行前に `contemplative-agent adopt-staged --help` を確認（MEMORY: `non-tty-cli-flags`）。冒頭に出る system prompt budget 行を記録する。
4. **検証** — `ls ~/.config/moltbook/skills | wc -l` が 24 であること、`.staged/` が空（`*.invalid` 以外）であること、`logs/audit.jsonl` の末尾 78 件が `source="stage-adopted"`（`-auto` でない）で accepted 5 / rejected 73 であることを確認。
5. **台帳・記録の更新**（同じ作業内で）:
   - `.notes/TASKS.md` — T-INSIGHT-OBS の (c) を done 相当に更新し実測（judged / 2 チャンク / covered 13.4% / 78 staged / 5 採用）を書く。T-INSIGHT-NOVELTY の「着手条件」を満たしたので状態を `deferred` → `ready` に上げ、**再評価の結論候補**（既知テーマ照合軸は弱い / 次の設計論点は intra-batch 重複とメタ動作レベルの同一性）を 1 行で残す。
   - 採否の内訳と読みを `.notes/insight-candidate-review-2026-07-25.md` に残す（2026-07-18 の同名ノートと同形式）。
   - T-SKILL-PROMOTE / stocktake の description 監査の入力として「構造ピボット族の飽和」を明記する。
6. ADR は**書かない**。今回は既存 ADR-0074 の運用サイクルの 1 回であり、機構変更を伴わない。設計変更（novelty gate の軸変更）を実際に決めるときに ADR を起こす。

## 検証

- 上記 4 の 3 点（skills 数 24 / staging 解放 / audit の accepted 5・rejected 73）。
- 副作用の無いことの確認: `git status`（`~/.config/moltbook` は repo 外なのでコード差分はゼロのはず）。コード変更が無いので pytest / lint は不要。
- 次の観察: 採用 5 件が ADR-0081 の選択ログに現れるか（`contemplative-agent generate-report --skill-selection`）を 1〜2 週間後に読む。never-selected なら次回 stocktake の退役候補。
