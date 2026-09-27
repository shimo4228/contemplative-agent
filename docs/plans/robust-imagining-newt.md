# T-INSIGHT-NOVELTY 再定義 — distill の収量を学習量に結び直す

## Context

### なぜこの変更をするか

ADR-0074 の weekly staged insight は、2 回連続で人間ゲートに大量の候補を送り、ほぼ全部が却下された（07-18: 0/106、07-25: 5/78 = **通算 5/184、2.7%**）。当初の診断は novelty gate の判定軸（intra-batch 重複を見ない / メタ動作の同一性を見ない）だったが、grill で前提を潰した結果、**欠陥は gate ではなく上流の distill にあることが実測で確定した**。

### 実測（このセッションで取得）

`knowledge.json`（live 4,031 件）と launchd stderr ログ（1,700 エピソード）:

| 指標 | 実測値 |
|---|---|
| 1 エピソードあたりの pattern 数 | 中央値 **2.00**（1:313 / **2:985** / 3:392 / 4〜6:8） |
| **ゼロ件で返したエピソード** | **1,700 件中 2 件 = 0.1%** |
| 14 日間の pat/ep のブレ | 1.82〜2.18（ほぼ一定） |
| `_is_valid_pattern` の発火 | 12 件 = 0.7% |
| live pattern の増加 | 約 121/日、800/週 |

**distill は 99.9% のエピソードに「durable pattern がある」と判定している。** 出力量は学習量ではなく活動量の関数になっている。1 日 68 回の SNS 行動の 99.9% が持ち越す価値のある一般化を含む、という判定は成立しない。

### 原因（プロンプト側の 2 箇所）

`config/prompts/distill_episode.md` の返却指示:

> Return a JSON object: `{"patterns": ["pattern1", "pattern2"]}` — **1 to 3 patterns**, or `{"patterns": []}` if nothing is generalizable.

1. **abstain が出力形式の縮退ケースになっている。** 「何も無ければ空リスト」が、件数帯と 2 要素の例示と同じ行で競合している。観測分布の中央値が例示のアリティ（2）に一致し、abstain が 0.1% しか発火しないのは、この構造で説明がつく。
2. **件数を指定している。** 「1 to 3」は重要度と無関係な収量の下限 1 を暗に与える。

コード側にも観測の穴がある: `AbstainReason` は `llm_none` / `shape_violation` / `empty_render` の 3 つで**すべて障害**。正当な空リストには reason code も集計も無く、`distill.py:555` は空リストを返したエピソードも `all N episodes produced output` と数える（ADR-0075 の observability 規約から漏れている）。今回は INFO ログの `→ N patterns` 行から偶然測れただけで、計器としては存在しない。

### Phase 0 External Research

`/search-first` 実行済み。

```
Verdict: Extend — custom（mem0 の抽出プロンプト設計 + Generative Agents の
importance/accumulation パターンを実践として取り込み、パッケージは非導入）
```

根拠: mem0 / Letta / Zep はサーバ・外部 API・大きな依存木を持ち、依存 requests+numpy と ADR-0007/0015 の security by absence に反する。欠けているのは機構ではなく既定 2 点で、いずれも `config/prompts/` の固定 apparatus 内で完結する（ADR-0054）。

取り込む既定:
- **abstain は独立した選択肢**（mem0 は `add_to_memory(facts=[...])` / `skip_memory()` を選ばせる）
- **件数でなく importance を出させる**（Generative Agents の poignancy 1–10）

**取り込まない既定**: 「atomic normalized fact で書け」。これは ADR-0072 が echo chamber 対策として意図的に入れた一人称・moment-indexed register と正面衝突するため、**register は変更しない**。

### 意図的にやらないこと

- novelty gate の判定軸（旧 T-INSIGHT-NOVELTY の軸①②）は**変更しない**。gate は上流の製造された一般性を後から消す装置として働いており、上流を直さずに軸を足しても効かない
- insight の週次カレンダートリガー → importance 累積トリガーへの置換は**今回の範囲外**（importance の実測分布が出る前に閾値を決めることになるため）
- B / C1 / C2、embedding threshold suppression、T-INSIGHT-C12 は従来どおり不採用・保留

---

## 実装

### 種別と chain

`fix`（実測済みの機構欠陥の修理）。LLM 呼び出しと untrusted 応答の parse を含むため、CLAUDE.md 開発原則により **chaos-TDD の fault column と replayable audit log を同じ PR で出荷**する。

Plan 確認 → TDD → python-reviewer / security-reviewer / codex-review → Doc Sync → Verify → 意図確認 → commit。

### 1. `config/prompts/distill_episode.md` — abstain の独立化と件数アンカーの除去

現行の返却行を差し替える。狙いは 3 つ:

- abstain を「出力形式の一種」でなく**先に判定する独立した選択**として提示する（"First decide whether this episode evidences anything durable at all." を判定順序として明示し、abstain の返却形を件数帯と同じ行に置かない）
- 「1 to 3 patterns」という件数帯と `["pattern1", "pattern2"]` の 2 要素例示を**両方**外す
- 各 pattern に `importance`（1–10、Generative Agents の poignancy 定義に準拠：1 = 完全に routine、10 = その後の振る舞いを変える）を付けさせる

register 指示（first-person / moment-indexed / 「platitude に潰すな」）の段落は**そのまま維持**する（ADR-0072）。

### 2. `core/distill.py` — 正当な abstain の計器化

- `AbstainReason` に **障害ではない** reason（例 `nothing_durable`）を追加し、`_distill_one` が空リストを受けた場合にそれを返す。既存 3 種（`llm_none` / `shape_violation` / `empty_render`）は障害として据え置き、集計行で**障害由来の abstain と正当な abstain を分けて出す**（現行の `all N episodes produced output` は正当 abstain を隠すので廃止）
- `_PATTERNS_SCHEMA` を `{"patterns": [{"pattern": str, "importance": int}]}` 相当に拡張。`_parse_patterns` は旧形（文字列配列）も受理し、`parse_mode` で区別する（後方互換 — 既存テストと過去ログの replay を壊さない）
- `_is_valid_pattern` の判定は変更しない

### 3. importance は計器として持つ（store には入れない）

`knowledge.json` の row スキーマは**変更しない**。importance は append-only JSONL の計器ログへ、`{ts, episode_id, pattern_sha256, importance, abstained}` の形で書く（`_io.append_jsonl_restricted` を再利用、`insight_novelty._append_novelty_audit` と同型）。

理由: 4,288 行の substrate 移行を避けられること、および `read-only-instruments` の規律 —— **importance はまず読み値として置き、いかなる判定にも使わない**。閾値・promotion への接続は実測分布が出てから別 ADR で決める（`no-numeric-caps` の再演を避ける）。

### 4. fault column（`tests/test_distill_chaos.py`）

`tests/chaos.py` の `ChaosBackend` を使い、決定論的に注入する:

- importance 欠落 / 範囲外（0, 11, 負, 文字列）→ pattern は採るが importance は記録せず理由コードを残す（silent fallback 禁止）
- 旧形（文字列配列）応答 → 後方互換で採る
- `{"patterns": []}` → `nothing_durable` を 1 回だけ計上し、障害カウンタは増えない
- 空配列と `null` / 欠落キーの区別（後者は `shape_violation`）
- 計器ログの書き込み失敗 → distill 本体は継続する（instrumentation must never break distill）

### 5. 主要ファイル

| ファイル | 変更 |
|---|---|
| `config/prompts/distill_episode.md` | 返却指示の差し替え（register 段落は不変） |
| `src/contemplative_agent/core/distill.py` | abstain reason 追加、schema 拡張、後方互換 parse、計器ログ |
| `tests/test_distill.py` | 既存の parse / abstain テストの拡張 |
| `tests/test_distill_chaos.py` | fault column（新規） |
| `docs/CODEMAPS/architecture.md` | Data Flow の distill 段（鮮度規約により同 PR） |
| `docs/adr/00XX-*.md` (+ `.ja.md`) | 後述 |
| `.notes/TASKS.md` | T-INSIGHT-NOVELTY 行の書き換え |

---

## Verification

### 本番配線の前に — オフライン replay で読み値を出す

**これが合格判定の本体。** `.notes/replay-novelty-chunking-20260718.py` と同型の read-only スクリプトを `.notes/` に置き、固定エピソード集合（直近 1 週間ぶん）に対して現行プロンプトと新プロンプトを両方走らせ、比較する:

- abstain 率（正当 abstain のみ）
- pat/ep の分布（中央値が 2 から動くか、例示アンカーが消えたか）
- importance の分布（**閾値はまだ決めない** — 分布を見るだけ）
- 生存した pattern の register が変わっていないこと（ADR-0072 の flattening 再発チェック。件数減少を品質改善の証拠にしない）

本番スケジュールへの反映は、この読み値を人間ゲートで確認してから。エピソード本文は script 側だけが読む（Claude Code は episode log を直読みしない）。

### Verify ステップ（commit の門）

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing   # ≥80%
uv run ruff check src/ tests/ scripts/
uv run mypy src/            # または pyright（型エラー 0 維持）
uv run lint-imports
```

加えて: secret scan（PreToolUse hook が自動）、`git status` 確認、doc sync 確認。依存は変えないので `pip-audit` は省略可。

### 合格条件

- 正当 abstain が測定可能になっている（reason code + 集計行で障害と分離）
- replay で abstain 率が 0.1% から有意に上がり、pat/ep 中央値が 2 に張り付かなくなっている
- 生存 pattern の register が ADR-0072 の指示どおりで、平板化していない
- fault column が全部通る

**「候補数が減った」ことだけを成功の証拠にしない**（ADR-0060 の flattening 前科がある）。

---

## Doc Sync

### ADR を書く（3 条件を全部満たす）

- **不可逆か**: プロンプトは可逆だが、`knowledge.json` に入る pattern の性質が変わるため**過去分と将来分が非同質になる**。研究記録として遡って揃え直せない
- **文脈なしでは驚くか**: 「distill の収量を減らす」は、パターンを研究材料として貴重視してきた本 repo の姿勢（`no-delete-episodes`）と逆に見える
- **本物のトレードオフか**: 収束した既定「atomic normalized fact」を **ADR-0072 との衝突ゆえに意図的に採らない**という判断を含む

記録すべき内容: 実測（0.1% / 中央値 2.0）、abstain を独立 action にする根拠、importance を計器に留める根拠、register を変えない根拠、旧 T-INSIGHT-NOVELTY の軸①②を採らない根拠。ADR-0060 / 0072 / 0074 / 0075 と相互リンクし、**graph.jsonld も同 PR で更新**（CLAUDE.md の両面更新規約）。

### 台帳

`.notes/TASKS.md` の `T-INSIGHT-NOVELTY` を「gate の判定軸」課題から「distill の収量が学習量と切れている」課題へ書き換える。旧軸①②は削除せず、**採らない理由（上流が原因のため軸を足しても効かない）を添えて残す**。`T-INSIGHT-C12` は deferred のまま。`T-INSIGHT-OBS` の観察対象に「replay の読み値」を追加。
