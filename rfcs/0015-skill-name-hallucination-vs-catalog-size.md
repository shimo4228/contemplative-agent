---
state: blocked
state_since: 2026-08-22
---

## タスク

**幻覚率が catalog サイズと相関する（2026-08-08 第 2 読みの新規発見）**。judged に対する rejected_names 非空率を catalog_count で条件付けると 19 件 0.57% / 24 件 0.58% / **37 件 7.72%** / 45 件 4.76%（n=21）。19→24 では動かず 24→37 で 13 倍。enforcement の境界（07-24）とは一致しないので説明変数は catalog サイズ。**幻覚名の 9 割超は実在 skill 名の語形変化**（`identify-` 対 `identifying-`、`detect-` 対 `detecting-`、`trace-` 対 `translate-`、`internal-` 対 `interpretative-`）で、作話は 3 件のみ。伝播はゼロ（全件 rejected 止まり）なので実害は「選ばれるはずの skill が落ちる」取りこぼし。**2026-08-08 追記 — 仮説 (ii) は棄却、機構は 3 種に分解された**（読み（`.notes/skillname-backfill-reading-2026-08-08.md`））。旧記述の 2 仮説は (i) catalog が長いほど逐語コピー精度が落ちる (ii) frontmatter `name` の非一貫性が語形変化を誘発、の交絡だった。**(ii) は成立しない** — 成立するならファイル名由来の語形が幻覚に現れるはずだが **0/67**。現れようがない: カタログは `(frontmatter name, frontmatter description)` の 2 スカラーだけで構成され、`# heading`（ファイル名の元）はプロンプトに一度も出ない（45 件全部が `description:` を持つので `skill_theme` の `description or title` フォールバックも発火しない）。**したがって backfill は自然実験にならず、切り分けるべき交絡が存在しなかった。** 残るのは (i) 単独。**あわせて、幻覚 67 件は 3 機構に分かれることが判明**: 語形変化 51 件（76%、`identify-`/`identifying-` 等）、意味的取り違え 8 件（12%、`translate-` 対 `trace-`）、**値層テキストの混入 8 件（12%）**。最後のものは旧記述で「作話 3 件」としたもので、実際は作話でなく**プロンプト内の別箇所からの引用** — 例 `interpretative process for moments when strict adherence creates artificial sepa` は Mindfulness 公理と非二元性公理の接ぎ木（`config/templates/contemplative/constitution/contemplative-axioms.md:13`）、`interpretative-process-audit`（5 回）の `internal` → `interpretative` も同じ語彙の侵入。**幻覚率を単一の数字で読むと 3 機構が混ざる**

## 着手条件

再開条件: 次の読み窓 2026-08-22 に到達
照合先:   日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
成立時:   ready（読む対象は catalog サイズと語形変化率の相関 + 値層混入の推移。それまで selector を変更しない）

## 詳細

[skillsel-reading-2026-08-08.md](../docs/evidence/adr-0081/skillsel-reading-2026-08-08.md) §3、[ADR-0081 Amendment 2026-08-08](../docs/adr/0081-skill-selection-two-pass-injection-enforcement.md) の「読みが許可しなかったもの」、`core/skill_selection.py` `select_applicable_skills`

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19 < 読み窓 2026-08-22（次回 Sat 14:07 の cycle で成立見込み）。

## 2026-08-22 triage 照合（無人 cycle）

成立 → `ready`。日付 2026-08-22 = 読み窓到達。T-SKILLSEL と同一 packet で dispatch（catalog サイズ × 語形変化率の相関、値層混入の推移）。

## 2026-08-22 triage — 第 3 読み完了（T-SKILLSEL と同一 packet S1）

読み: `.notes/skillsel-reading-2026-08-22.md` §4。幻覚率 4.83%→19.25%（4.0 倍）、増分の 91% は語形変化。機構別（規則を明文化して前回窓にも当て直し）: 語形変化 206 (88.8%) / 意味的取り違え 21 (9.1%) / 値層混入 5 (2.2%、横ばい）。catalog 条件付け: 45→20.16% / 48→17.38% / 50→34.78% (n=23)。**catalog 45→48 でエントリは増えたのに幻覚率は下がり corpus トークンは 35,992→33,745 に減った** — トークン数で並べると 7 レジーム全部が単調。エントリ数 vs トークン数を分離する最初の 1 対。伝播 0。08-15 採用の `structural-constraint-mapping-scm` 1 件が 4 語形に崩れ延べ 28 回。分類器は scratchpad `s1_halluc.py`（セッション限り）。

## 着手条件（2026-08-22 更新）

再開条件: 次の読み窓 2026-09-05 に到達
照合先:   日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
成立時:   ready（読む対象: catalog 57 での率、トークン仮説の再現可否、`structural-constraint-mapping-scm` の変異が定常か。それまで selector を変更しない）

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。日付 2026-08-24 < 読み窓 2026-09-05。

旧 ID: T-SKILLSEL-HALLUC-CATALOG（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## Status

blocked（≈ issue-tracker 標準の blocked。RFC 標準に state 語彙は無い） — 第 3 読み（2026-08-22）で幻覚率 4.83% → 19.25%、増分の 91% が語形変化と
判明。次の読み窓 2026-09-05 まで selector を変更しない（2026-08-25）。直近の照合 2026-08-24 も
未成立。

## Next action

- 再開条件: 次の読み窓 2026-09-05 に到達
- 照合先: 日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
- 成立時: ready（読む対象: catalog 57 での率、トークン仮説の再現可否、
  `structural-constraint-mapping-scm` の変異が定常か。それまで selector を変更しない）
