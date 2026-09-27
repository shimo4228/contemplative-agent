# `observed` epistemic key の退役

## Context

`epistemic_counts` の `observed` キーは ADR-0060 以降**構造的に常時ゼロ**である。distill が
`activity` レコードのみを取り込み、全 activity を `self` → `generated` にマップするため、
`external_reply` → `observed` の経路に到達しない。

これは 2 箇所の docstring（`knowledge_store.py:102-109`、`cli/approval.py:82-85`）と
ADR-0071 M2 レビューに記録済みだが、**値そのものは meta.json と audit.jsonl に毎回書き出され
続けている**。読む側は値の存在から「意味のある指標」と解釈し、`observed=0` を
「外部 grounding が無い」と誤読する。2026-07-25 のセッションで実際にこの誤読が発生した
（78 件の staged skill を「全て echo」と誤って結論した）。

docstring による警告は、値を見る前に読まれる保証がない。**dead field が active field の顔をして
永続化されている**構造そのものを消すのが目的。

実データによる裏付け（`audit.jsonl` 全 405 レコード）:

| command | observed | generated | unknown |
|---|---:|---:|---:|
| insight | **0** | 1,618 | 0 |
| distill-identity | **0** | 231 | **119** |

`unknown` は distill-identity で実際に埋まる（provenance 未設定の legacy 行）ため**残す**。
退役対象は `observed` のみ。

## 種別と chain

**種別: `refactor`**（振る舞いを変えない構造変更。ただし audit レコードのスキーマは変わる
ので Doc Sync が必須）

```
Parallel Group 1: [python-reviewer, refactor-cleaner]
Sequential: 実装 → Review → Doc Sync → Verify
```

- TDD: `-`（新規挙動なし。既存テストの期待値更新のみ）
- Security Review: `-`（入力検証・認証・秘匿情報に触れない）
- Cross-Model Review: `-`（公開 API / 並行処理 / セキュリティ境界のいずれにも触れない内部整理）
- Doc Sync: **`Y`** — スキーマ変更 + ADR 新設 → CODEMAPS と graph.jsonld の両面更新

## 実装

### 1. コード（`src/contemplative_agent/core/knowledge_store.py`）

枝ごと完全に退役する（ユーザー選択）。2 箇所のみ:

- `:76-80` `_EPISTEMIC_KIND_BY_SOURCE` から `"external_reply": "observed"` の行を削除
- `:111` `counts = {"observed": 0, "generated": 0, "unknown": 0}` → `{"generated": 0, "unknown": 0}`

あわせて `:83-92` `epistemic_kind_for` と `:95-110` `epistemic_counts_for` の docstring を改訂:
`observed` の説明と「structurally zero」の注意書きを削除し、ADR 参照を新 ADR に repoint。
`:73-75` のコメント（`{observed, generated} only`）も同様。

**degradation は安全**: `epistemic_kind_for` は `.get(source_type)` なので、万一
`external_reply` の provenance 行が現れても `None` → `unknown` に落ちるだけで `KeyError` に
ならない（`:114` の `counts[kind or "unknown"]`）。

**production の読み取り側は変更不要** — `["observed"]` を索引するコードは production に存在
せず、dict は全て opaque な `dict[str,int]` として copy / JSON 直列化されるのみ
（`cli/staging.py:161`、`cli/adopt.py:100`、`cli/approval.py:103`、`cli/memory_cmds.py:228,354`）。

**スコープ外（明示）**: `core/episode_render.py:79,90` の `_derive_source_type` が返す
`"external_reply"` **文字列自体は残す**。これは provenance レコードの source_type であって
epistemic tally とは別レイヤであり、退役判断には別途 provenance 側の棚卸しが要る。

### 2. テスト（5 ファイル / 9 assertion）

3 キーのリテラルを 2 キーに更新する。`external_reply` を使った合成行のテストは、
「`external_reply` は `unknown` に落ちる」を主張する形に**書き換える**（削除しない —
枝を消したことの回帰ガードになる）:

- `tests/test_knowledge_store.py:415-450` — `TestEpistemicKindForADR0050` のマッピング表から
  `("external_reply", "observed")` を外し、`external_reply → None` を主張。
  `TestEpistemicCountsForADR0050` の `:435-445` / `:448-450` を 2 キーに
- `tests/test_distill.py:1269-1301` — `{"generated":1,"unknown":1}` へ（合成 `external_reply` 行が
  `unknown` に落ちる）
- `tests/test_insight.py:508-527` — 同様に 2 キーへ
- `tests/test_constitution.py:231-249` — `{"generated":0,"unknown":len(live)}` へ
- `tests/test_cli_approval.py:149-277` — `:162`, `:192`, `:238` のリテラルと
  `:166`, `:201`, `:249`, `:272` の assertion を 2 キーへ。`:179` の nullable-but-present
  シェイプ検証はそのまま

### 3. ADR（新規 `docs/adr/0082-*`、EN 正本 + `.ja.md`）

ADR-0050 の `epistemic_counts` スキーマ部分を**部分 supersede** する（ユーザー選択）。
判断の系譜を時系列で残す: 0050 で決めた → 0060 で到達不能になった → 0071 M2 で誤読が
観測された → 0082 で退役。

Context に「docstring 警告が読まれる保証がない」= documented-invariant を構造で消す、という
根拠を書く（rules `patterns.md` の「文書化された不変条件はゲートに落とす」の一形態）。
Consequences に**過去レコードの非遡及**を明記（下記）。

既存 ADR には supersede ポインタを 1 行足すに留め、本文は改変しない:
`0050`（EN+JA）、`0060`、`0071`、`0072`。

### 4. Doc Sync

- `docs/CODEMAPS/architecture.md:385` — スキーマ段落を 2 キーに。`:291, 346, 377, 383` の言及も確認
- `docs/CODEMAPS/core-modules.md:64`（スキーマ行）、`:98`（"generated/unknown split"）、
  `:20, 56-58, 149`
- `graph.jsonld` — ADR-0082 ノードを新設し `supersedes` edge を ADR-0050 へ。
  `:1276-1286`（ADR-0050 ノードの description に `{observed, generated}` が書かれている）を更新。
  `:610, 702, 731, 2080, 2089, 2232` の参照も確認
- `llms-full.txt:197, 243, 246` / `llms.txt:107`
- `CHANGELOG.md` — Unreleased に退役エントリ
- `.claude/skills/read-only-instruments/SKILL.md:43` — M2 の「signal-first で保留した修理」を
  例として引いている箇所。保留が解けたので記述を更新

## 過去データの扱い（非遡及）

既存の `audit.jsonl` レコードと `.staged/*.meta.json`（現在 78 件）は**書き換えない**。

- `cli/adopt.py:100` は meta.json の `epistemic_counts` を verbatim で pass-through するため、
  既存 staged ファイルはそのまま adopt 可能
- audit.jsonl は append-only の監査ログであり、遡及書き換えは監査性を壊す
- 外部パーサは存在しない（`scripts/log_anomaly_sweep.py` は行単位 regex のみで JSON
  フィールドを触らない。`evals/` なし）

結果として audit.jsonl は「ある時点を境にキーが 2 つになる」履歴を持つ。これは ADR-0082 の
Consequences に明記し、オフライン解析側が `.get("observed", 0)` で読めることを保証する。

## Verify

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing   # ≥80%
uv run ruff check src/ tests/ scripts/
uv run lint-imports
uv run pyright   # 型エラー 0 維持
```

加えて:

1. **退役の実証** — `grep -rn '"observed"' src/` が 0 件（テストの `unknown` 落ち検証を除く）
2. **エンドツーエンド** — `contemplative-agent distill-identity --dry-run` 等で
   `epistemic_counts` を含むレコードが生成される経路を 1 回通し、出力が 2 キーであることを確認
   （**注意**: 重い Ollama 実験はスケジュールセッション JST 0/6/12/18 時を避ける）
3. **後方互換の実証** — 既存 `.staged/*.meta.json`（3 キーを持つ 78 件）に対して
   `adopt-staged` のパース経路が壊れないことを確認。`--help` で non-interactive フラグを
   事前確認してから（承認ゲート対象コマンド）
4. `git status` — 意図しないファイルが含まれていないか

## 補足: この誤読自体の再発防止

フィールド退役で `observed` の誤読は構造的に消えるが、「meta.json の値を読んだが、それを
生成するコードの docstring を読まなかった」という**読み方の癖**は残る。
memory の `Operational Gotchas` に 1 行足すかは、本 PR とは別に判断する（本 PR のスコープ外）。
