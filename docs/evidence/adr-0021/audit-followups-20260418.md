# ADR-0021 Audit Follow-ups — 2026-04-18

Audit report: `implementation-audit-20260418.md` (本 follow-up の source)

6 follow-up 項目 (F1–F6) のうち、ADR-0028 / ADR-0029 で **F1 / F2 / F3 は解消**。残 3 項目 (F4 / F5 / F6) を新セッションで 1 つずつ片付けるためのチェックリスト。

## 進捗サマリ

| # | タイトル | 状態 | 対応 |
|---|---|---|---|
| **F1** | mark_accessed persistence gap 修正 | ✅ 解消 | ADR-0028 で forgetting 撤回 (241bf8a) — mark_accessed 経路自体が不要に |
| **F2** | `user_input` / `external_post` / `sanitized` dormant 整理 | ✅ 解消 | ADR-0029 (本セッション、commit 予定) — schema 削除 + production migration 完了 |
| **F3** | feedback live 配線 or schema removal | ✅ 解消 | ADR-0028 で feedback 撤回 (241bf8a) — schema から削除 |
| **F4** | Retrieval scoring rank-reversal behavioral test 追加 | ✅ 解消 | commit `d9074ae` で `tests/test_views.py:154-226` に `TestRankADR0021` 追加 (5 tests) |
| **F5** | Dry-run rank-reversal 効果測定 | ✅ 解消 | `retrieval-scoring-effect-20260418.md` — trust keep 判定 |
| **F6** | `is_live()` consumer 適用網羅性確認 | ✅ 解消 | `is-live-consumer-audit-20260418.md` + commit `4e8eca3` で distill 2 gap 修正 |

---

## F4: Retrieval scoring rank-reversal behavioral test 追加

**Severity**: 🟡 medium (今後 trust discrimination を修正する時の regression guard になる)

**現状**: `test_views.py` の既存テストは「同一 cosine + 異なる trust → trust 高い方が上位」の単純ケース。cosine 優位 × low-trust (0.4 × 0.9 = 0.36) を cosine 劣位 × high-trust (0.9 × 0.7 = 0.63) が逆転するケース未検証。

**やること**:
- `tests/test_views.py` に `TestRankReversal` class を追加
- 2 pattern を用意:
  - A: cosine 0.4、trust 0.9 → score 0.36
  - B: cosine 0.9、trust 0.7 → score 0.63
- `_rank` で B が A を上回ることを assert
- 逆パターン (cosine 高 × trust 低、cosine 低 × trust 高) も網羅

**新規ファイル**: なし (既存 `test_views.py` への追加のみ)

**完了定義**:
- 新規テスト 2-4 件追加、全 pass
- 将来 `trust_score` の migration default を変える時 (F5 後に 0.6 → 別値にする可能性) に自動で regression を catch

**開始コマンド**: 新セッションで以下を読む
- `src/contemplative_agent/core/views.py:308` (`_rank` の実装)
- `tests/test_views.py` (既存 `TestRankADR0021`)

---

## F5: Dry-run rank-reversal 効果測定

**Severity**: 🟢 low (F4 後、かつ trust discrimination 改善の準備段階)

**現状**: production 377 patterns で `trust_score` 91.5% が migration default 0.6 に張り付いている。cosine × trust 乗算の trust 因子が実質的に discrimination を提供していない。cosine がほぼ単独で ranking を決めている。

**やること**:
1. `distill --dry-run` / `insight --dry-run` の top-K 出力を記録するスクリプトを書く
2. ADR-0021 前 (83b6a8b^) vs 現在 で top-K の差を比較
3. trust が 0.6 constant + strength 撤回済み (ADR-0028) の状況下で、cosine 以外の因子が top-K を変えているかを実データで測る
4. 結果を `retrieval-scoring-effect-20260418.md` に記録

**判断材料**:
- 差がほぼない → trust discrimination は実運用で意味を成していない → `trust_score` 自体を retire するか、migration default を分布させる (ADR 候補)
- 差がある → どのような軸で効いているかを記述 → trust_score を残す justification

**依存**: F4 完了後 (rank-reversal test が green の状態を reference として使う)

**完了定義**:
- 測定 script + report
- retrieval scoring の将来方向 (retire / reshape / keep) の判断材料が揃う

**注意**: `prototype-before-scale` rule に従い、5-10 件の sample で先にトライアルしてから全件対象に広げる。

---

## F6: `is_live()` consumer 適用網羅性確認

**Severity**: 🟢 low (現状 bug はない、将来の query path 追加時の regression 予防)

**現状**: `views._rank` は `is_live(p)` で filter するが、`insight` / `memory.get_context` / `skill_router` 等の独自 query path が is_live を適用しているか未検証。ADR-0021 landing 直後に `insight.py` の `valid_until` 無視バグが commit `9086c90` で発覚した経緯があり、他の consumer に同様の漏れが残っている可能性。

**やること**:
1. `grep -rn "knowledge.get_raw_patterns\|knowledge.get_live_patterns\|_filtered_pool" src/` で pattern を読む経路を棚卸し
2. 各経路について is_live filter (or valid_until + TRUST_FLOOR 等価チェック) の適用を確認
3. 未適用の path があれば修正 commit

**チェック対象** (audit section 4 P2.4 より):
- `core/insight.py`
- `core/memory.py` (`get_context` 系)
- `core/memory_evolution.py`
- `core/skill_router.py`
- `core/rules_distill.py`
- `core/constitution.py`
- `core/distill.py` (`_dedup_patterns` 経路)

**完了定義**:
- 棚卸し結果を `is-live-consumer-audit-20260418.md` に記録
- 未適用 path があれば修正 + test 追加

**参考**: `forgetting.is_live` は ADR-0028 で scope 縮小済み (`valid_until is None and trust_score >= TRUST_FLOOR`)。strength floor は撤回。

---

## セッション推奨順序

低依存 → 高依存、clean task → 判断タスク の順:

1. **F6 (is_live 棚卸し)** — 純粋な grep + read タスク。bug 発見なら修正、なければ confirmation として report
2. **F4 (rank-reversal test)** — F5 の baseline として必要。clean な test 追加
3. **F5 (効果測定)** — F4 完了後。判断タスク (trust_score 将来の扱い)

---

## 参考

- Audit report: `implementation-audit-20260418.md`
- ADR-0028: `docs/decision-history/0028-retire-pattern-level-forgetting-feedback.md` (F1, F3 解消)
- ADR-0029: `docs/decision-history/0029-retire-dormant-provenance-elements.md` (F2 解消)
- 関連 memory: `project_adr0028_retirement`
