---
state: done 2026-09-05
state_since: 2026-08-22
---

## タスク

**幻覚率が catalog サイズと相関する（2026-08-08 第 2 読みの新規発見）**。judged に対する rejected_names 非空率を catalog_count で条件付けると 19 件 0.57% / 24 件 0.58% / **37 件 7.72%** / 45 件 4.76%（n=21）。19→24 では動かず 24→37 で 13 倍。enforcement の境界（07-24）とは一致しないので説明変数は catalog サイズ。**幻覚名の 9 割超は実在 skill 名の語形変化**（`identify-` 対 `identifying-`、`detect-` 対 `detecting-`、`trace-` 対 `translate-`、`internal-` 対 `interpretative-`）で、作話は 3 件のみ。伝播はゼロ（全件 rejected 止まり）なので実害は「選ばれるはずの skill が落ちる」取りこぼし。**2026-08-08 追記 — 仮説 (ii) は棄却、機構は 3 種に分解された**（読み（`.notes/skillname-backfill-reading-2026-08-08.md`））。旧記述の 2 仮説は (i) catalog が長いほど逐語コピー精度が落ちる (ii) frontmatter `name` の非一貫性が語形変化を誘発、の交絡だった。**(ii) は成立しない** — 成立するならファイル名由来の語形が幻覚に現れるはずだが **0/67**。現れようがない: カタログは `(frontmatter name, frontmatter description)` の 2 スカラーだけで構成され、`# heading`（ファイル名の元）はプロンプトに一度も出ない（45 件全部が `description:` を持つので `skill_theme` の `description or title` フォールバックも発火しない）。**したがって backfill は自然実験にならず、切り分けるべき交絡が存在しなかった。** 残るのは (i) 単独。**あわせて、幻覚 67 件は 3 機構に分かれることが判明**: 語形変化 51 件（76%、`identify-`/`identifying-` 等）、意味的取り違え 8 件（12%、`translate-` 対 `trace-`）、**値層テキストの混入 8 件（12%）**。最後のものは旧記述で「作話 3 件」としたもので、実際は作話でなく**プロンプト内の別箇所からの引用** — 例 `interpretative process for moments when strict adherence creates artificial sepa` は Mindfulness 公理と非二元性公理の接ぎ木（`config/templates/contemplative/constitution/contemplative-axioms.md:13`）、`interpretative-process-audit`（5 回）の `internal` → `interpretative` も同じ語彙の侵入。**幻覚率を単一の数字で読むと 3 機構が混ざる**

## 着手条件

再開条件: 次の読み窓 2026-08-22 に到達
照合先:   日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
成立時:   accepted（読む対象は catalog サイズと語形変化率の相関 + 値層混入の推移。それまで selector を変更しない）

## 詳細

[skillsel-reading-2026-08-08.md](../docs/evidence/adr-0081/skillsel-reading-2026-08-08.md) §3、[ADR-0081 Amendment 2026-08-08](../docs/adr/0081-skill-selection-two-pass-injection-enforcement.md) の「読みが許可しなかったもの」、`core/skill_selection.py` `select_applicable_skills`

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19 < 読み窓 2026-08-22（次回 Sat 14:07 の cycle で成立見込み）。

## 2026-08-22 triage 照合（無人 cycle）

成立 → `accepted`。日付 2026-08-22 = 読み窓到達。T-SKILLSEL と同一 packet で dispatch（catalog サイズ × 語形変化率の相関、値層混入の推移）。

## 2026-08-22 triage — 第 3 読み完了（T-SKILLSEL と同一 packet S1）

読み: `.notes/skillsel-reading-2026-08-22.md` §4。幻覚率 4.83%→19.25%（4.0 倍）、増分の 91% は語形変化。機構別（規則を明文化して前回窓にも当て直し）: 語形変化 206 (88.8%) / 意味的取り違え 21 (9.1%) / 値層混入 5 (2.2%、横ばい）。catalog 条件付け: 45→20.16% / 48→17.38% / 50→34.78% (n=23)。**catalog 45→48 でエントリは増えたのに幻覚率は下がり corpus トークンは 35,992→33,745 に減った** — トークン数で並べると 7 レジーム全部が単調。エントリ数 vs トークン数を分離する最初の 1 対。伝播 0。08-15 採用の `structural-constraint-mapping-scm` 1 件が 4 語形に崩れ延べ 28 回。分類器は scratchpad `s1_halluc.py`（セッション限り）。

## 着手条件（2026-08-22 更新）

再開条件: 次の読み窓 2026-09-05 に到達
照合先:   日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
成立時:   accepted（読む対象: catalog 57 での率、トークン仮説の再現可否、`structural-constraint-mapping-scm` の変異が定常か。それまで selector を変更しない）

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。日付 2026-08-24 < 読み窓 2026-09-05。

旧 ID: T-SKILLSEL-HALLUC-CATALOG（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-26 < 読み窓 2026-09-05。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-29 < 読み窓 2026-09-05。

## 2026-09-02 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-09-02 < 読み窓 2026-09-05（残り 3 日）。

## 2026-09-05 triage 照合（無人 cycle）

**成立 → `blocked` → `accepted`。** 読み窓 2026-09-05 に到達（今日）。同じ窓に 1,030 行（[RFC-0014](0014-skill-selection-instrument-reading.md) と同一のログ源・同一窓なので 読みは 1 パケットにまとめる）。読む対象: catalog 57 での率、トークン仮説の再現可否、`structural-constraint-mapping-scm` の変異が定常か。

## 2026-09-05 dispatch（S5）

`accepted` → `in_progress`。worktree `task/skillsel-read-4` で measurement セッション `ca/s5-skillsel-read-4` を起動（RFC-0014 と同一パケット（ログ源・窓が同一））。
packet は read-only 指定 — 書いてよいのは読みメモ 1 本と分析スクリプトのみで、selector / 購読集合 / production コードには触れない。判定はしない（判断役とオーナーがする）。

## 2026-09-05 done（merge 716226a）

第 4 読み（RFC-0014 と同一パケット・同一ログ源）。幻覚率 **19.17% → 25.44%** [22.9..28.2]、catalog 57 レジーム全体で 24.95%。**機構の向きが変わった** — 前窓は増分の 91% が語形変化だったが、今窓は語形変化が延べ横ばい（218→223）で増分の 83% が意味的取り違え（語形変化 79.4% / 意味的取り違え 18.5% / 値層混入 2.1%）。伝播 0（未知名 52/52 が全履歴の catalog_names に一度も無い）。トークン仮説は 50→57 の対で分離できず（n=23 側の CI 幅 36pt に 率差 9.8pt が丸ごと入る）— 第 3 読み §7 の「分離は再現しない見込み」が当たった。

検収は判断役（triage-ca）が独立に実施 — worktree で `verify.sh` 再実行、commit body の chain 遵守と逸脱の名指しを確認。merge 後の main でも exit 0。読みは取得済みで、**判定（selector の変更・購読集合の見直し）は行っていない** — それは別の判断。

## Status

blocked — 第 3 読み（2026-08-22）で幻覚率 4.83% → 19.25%、増分の 91% が語形変化と
判明。次の読み窓 2026-09-05 まで selector を変更しない（2026-08-25）。直近の照合 2026-08-24 も
未成立。

## Next action

- 再開条件: 次の読み窓 2026-09-05 に到達
- 照合先: 日付、および `logs/skill-selection-*.jsonl` の `rejected_names`
- 成立時: accepted（読む対象: catalog 57 での率、トークン仮説の再現可否、
  `structural-constraint-mapping-scm` の変異が定常か。それまで selector を変更しない）
