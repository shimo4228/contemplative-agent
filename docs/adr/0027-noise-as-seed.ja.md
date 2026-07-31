# ADR-0027: Noise as Seed — binary gate から salience-based forgetting へ

## Status

accepted

## Date

2026-04-16

## Context

ADR-0026 で binary gate が完成した: `core/distill.py` の `_classify_episodes` は `noise` view centroid に対する `noise_sim` を計算し、`noise_sim >= NOISE_THRESHOLD` を満たす episode を **完全に破棄** する — `knowledge.json` に書かれず、ログにも残らず、カウントもされない。唯一の痕跡は `logger.info` の進捗行だけ。一度 gate された episode は消える。

独立した 3 つの理論的枠組みが、同じ反論に収束する: 「破棄」がデフォルトとして誤っている。

1. **唯識 (ADR-0017 の枠組み)。** `阿頼耶識 (ālaya-vijñāna)` は明示的に **未発現の種子 (bīja)** の貯蔵庫である。種子がまだ然るべき縁 (`pratyaya`) に出会っていないだけのことを「ノイズ」と判定するのは誤り — それは未熟 (unripe) なだけ。これを捨てることは、後の縁がそれを現行化させる可能性を閉ざす。現状の binary gate は分類を最終判定としてモデル化しているが、唯識は分類を「瞬間の読み取り」としてモデル化する。

2. **人間記憶 (consolidation と reconsolidation)。** エピソード記憶痕は符号化段階でフィルタされない — フィルタは忘却曲線、salience gating、schema accommodation を通じて、**保持された痕跡に対して** 時間をかけて動く。特に reconsolidation は新しい文脈が到着したときに蓄積済みの痕跡を **再評価** する。符号化時にフィルタして二度と読み返さないシステムには、schema accommodation のメカニズムが存在しない。

3. **Active Inference / Free Energy Principle。** `adapters/meditation/` adapter は FEP に基づいて構築されており、その目的は生成モデルを更新して予測誤差を最小化することにある。この枠組みでは、**既存のどの view centroid からも遠い episode** こそが、システムが注目すべきシグナルである — 高い surprise を持ち、モデル更新のための高い情報量を持つからだ。現状の gate は「既知の構造から遠い」を「捨てる」と扱っており、これは FEP が規定することの真逆である。meditation adapter と distill パイプラインは **矛盾する原理** で動いている。

3 つの枠組みは語彙では異なるが、構造的主張では一致する: **エピソード痕は保持されるべき、分類は改訂可能であるべき、高 surprise の痕跡はモデル更新を優先的に駆動するべき** — 破棄されるべきではない。

本 ADR のスコープを詰める過程で、もう 1 つ重要な観察が浮上した。以前のプラン素案 (`~/.claude/plans/wondrous-gliding-feigenbaum.md`) は Phase 1 schema として `{noise_sim, const_sim, view_centroids_hash, ...}` を、Phase 3 式として `salience = 1 - max(noise_sim, const_sim, *view_sims)` を提案していた。両方とも `const_sim` を `noise_sim` と並ぶ特別な軸として扱っている。この非対称性は ADR-0026 以前の 3 値 classify (`noise` / `constitutional` / `uncategorized`) の残滓であり、当時は constitutional 軸が first-class な state field だった。ADR-0026 後にはこの非対称性に根拠がない: `constitutional` は多数ある view のうちの 1 つに過ぎず、`_classify_episodes` レイヤで特権的な地位は持たない。正しい定式化は全 view を統一的に扱う:

```text
salience(episode) = 1 - max(cosine(episode, centroid(v)) for v in all_views)
```

`noise` view が他の view と異なるのは (a) gating 閾値 `NOISE_THRESHOLD` を持つことと、(b) Phase 3 で同様に分布の反対側に `REVELATION_THRESHOLD` を追加する可能性があること、だけ。特権軸ではない。

## Decision

gate された episode を永続的な **種子 (seed)** として保持し、分類を binary gate から salience 加重の retention へ進化させる — 3 段階で順序立てて。

**指導原理 (view 軸の統一)。** `noise` と `constitutional` は salience 計算の観点では特別な view ではない。全 view が `max(cosine(episode, centroid(v)))` に統一的に寄与する。`noise` が他の view と違う唯一の軸は (a) gating 閾値を持つこと、(b) Phase 3 で分布の反対側に `REVELATION_THRESHOLD` を追加する可能性、の 2 つのみ。Phase 1 で `noise_sim` のみを記録するのは、現状の `_classify_episodes` が既にそれを計算しているから。Phase 3 は全ベクトルを統一的に計算する。

### Phase 1 — Noise JSONL writer (スキーマ変更なし、~30 LOC)

いかなる pattern / episode schema も変更せずに、観測チャンネルを追加する。

`core/distill.py`:

- `_classify_episodes(records, view_registry=None, log_dir=None)` に `log_dir: Optional[Path] = None` 引数を追加
- 既存の for-loop 内で gated episode について `(record, noise_sim, summary)` tuple を蓄積 (per-iteration I/O を避ける)
- `return _ClassifiedRecords(...)` の直前で: `view_centroids_hash` (ソート済み `name + centroid.tobytes()` 連結の SHA-256、先頭 8 hex 文字) を計算し、gated episode 1 件ごとに `log_dir / f"noise-{today}.jsonl"` へ `_io.append_jsonl_restricted()` で JSON 行を追記

Record schema (Phase 1):

```json
{
  "ts": "2026-04-16T20:07",
  "episode_ts": "2026-04-16T19:42:00+00:00",
  "episode_summary": "[2026-04-16T19:42] post: ...",
  "noise_sim": 0.7134,
  "view_centroids_hash": "a1b2c3d4",
  "record_type": "post"
}
```

`core/distill.py` の `distill(...)` 関数は `log_dir` 引数を受け取って `_classify_episodes` に転送する。adapter の `EPISODE_LOG_DIR` (`adapters/moltbook/config.py` から) は `cli.py` で注入 — `core` は `adapters` を決して import しない (ADR-0015 を保つ)。

`dry_run=True` のパスは `log_dir=None` を渡す — 既存の「dry_run 時は副作用禁止」の不変条件と揃える。

**Phase 1 単体で提供される価値**: base-rate の可観測性。Phase 2 / 3 が実装されなくても、`noise-YYYY-MM-DD.jsonl` の系列は「1 日あたり何件 gated されるか」「`noise_sim` がどう分布するか」を即座に明らかにする。また `view_centroids_hash` で centroid の drift を検出できる。Phase 2 と Phase 3 の判断 (`REVELATION_THRESHOLD` 含む) はこの base rate に依存する; Phase 1 データが ≥2 週間揃う前にいかなる閾値も決めない。

### Phase 2 — View centroid reload + re-classify CLI (~200 LOC)

Phase 1 の base rate が ≥2 週間揃った後に、過去の noise log を更新済み centroid に対して読み直す機能を追加。

- `core/views.py`: `ViewRegistry.reload_centroid(name)` と `reload_all()` を追加 — seed ファイルを再読み込みして再 embed する。現状 registry は lazy に embed してキャッシュし続ける; Phase 2 では明示的なリロードが必要。
- `core/re_classify.py` (新規): `re_classify_past_episodes(days, view_registry, noise_log_dir)` — 過去 N 日分の `noise-*.jsonl` を読み、現在の centroid に対して `noise_sim` を再計算し、レポートを発行。
- CLI: `contemplative-agent re-classify --days N [--dry-run]`。承認ゲートなし (可観測性のみ、データ変更なし)。

出力: 過去 gated された episode のうち、現在の centroid では閾値を下回るもの — 古い centroid のせいで pseudo-noise 判定されていたもの。

### Phase 3 — Salience weighting と revelation 昇格 (~150 LOC)

binary `noise_sim >= NOISE_THRESHOLD` を、salience 分布の両側に対する判定に置き換える。

各 episode について全ベクトルを計算:

```text
salience = 1 - max(cosine(episode, centroid(v)) for v in all_views)
```

判定表:

| 条件 | アクション |
|---|---|
| `noise_sim >= NOISE_THRESHOLD` かつ `salience < REVELATION_THRESHOLD` | gated (現状通り) — `noise-*.jsonl` に書き出し |
| `noise_sim >= NOISE_THRESHOLD` かつ `salience >= REVELATION_THRESHOLD` | revelation — `noise-revelation-*.jsonl` に書き出し、次回 distill の LLM prompt に `trust_score = 0.3` で昇格 |
| `noise_sim < NOISE_THRESHOLD` | kept (現状通り) |

`REVELATION_THRESHOLD` は **今選ばない**。≥2 週間観測された Phase-1 `salience` 分布の 80 percentile に設定する。観測前にハードコードするのは confirmation bias の典型的失敗モードであり、意図的に延期する。

Revelation の重複除去: revelation 行を書き出す前に直近 7 日の revelation との cosine を比較し、`cosine > 0.85` ならスキップ (トピックストームを防ぐ)。

`generate-report` に revelation セクションを追加 — salience 分布と昇格率を表示。`trust_score = 0.3` で昇格した pattern は、validating feedback が蓄積されなければ ADR-0021 forgetting で自然に減衰する。

### 理論的統合 (analogical, not causal)

3 つの枠組みは共通の構造に収束する。下の表は **類比 (analogy)** であって、等価性の主張ではない — 主張は「これら 4 つの概念レイヤは 3 枠組み全てに現れ、実装を共有できる」こと。この表から「唯識 = FEP」を読み取るのはカテゴリーエラー。

| レイヤ | 唯識 (Yogācāra) | 人間記憶 | Active Inference / FEP | moltbook 実装 |
|---|---|---|---|---|
| 感受 | 前五識 | 感覚記憶 | sensory sample | episode JSONL |
| 選別 | 第六識 意識 (末那) | 注意 | precision weighting | `_classify_episodes` |
| 蓄積 | 末那+阿頼耶識 | 長期記憶 | prior update | views/ + knowledge.json |
| 顕現 | 種子→現行 | 想起/創発 | surprise minimisation | Phase 3 salience seed |

統合を明示する価値は、`adapters/meditation/` (FEP) と `core/distill.py` (retention / distillation) を **同じ枠組みで議論できるようになる** こと。本 ADR 以前は矛盾する原理で動いていたが、以後は同じ階層計算の 2 実装となる。

## Alternatives Considered

1. **Phase 1 をスキップして直接 salience weighting に行く。** 却下: base-rate 観測なしでは `REVELATION_THRESHOLD` を盲目的にハードコードすることになる。≥2 週間の観測ウィンドウは遅延のための遅延ではない — 非恣意的な閾値の前提条件である。

2. **gated だけでなく kept episode もログする。** Phase 1 では却下。kept episode は既に `knowledge.json` で蒸留経由で保存されている。別途ログすると書き込みパスを二重化するだけで、distill 出力が既に持っているシグナルを超える情報は得られない。Phase 3 で full salience テレメトリが有用なら再検討の余地あり。Phase 1 は最小に留める。

3. **Phase 1 の record に `const_sim` を含める (初期プラン素案のとおり)。** 却下 — 理由は Context / 指導原理で述べた通り。ADR-0026 後 view 軸は統一的であり、`constitutional` を `noise` と並んで特権化するのは残滓的非対称性。Phase 3 で全 view 類似度を統一的に計算し、その時初めて full salience ベクトルが record に入る。

4. **gated episode を `knowledge.json` に "dormant" flag で永続化する (JSONL の代わり)。** Phase 1 では却下: 2 つのデータライフサイクル (curated pattern vs 生の観測記録) を混ぜることになり、schema 変更が必要になり、forgetting を複雑化させる。JSONL なら gated-seed アーカイブを append-only、human-readable、scan も安価に保てる。

5. **`_classify_episodes` から full similarity ベクトルを返して、書き込みを caller に押し上げる。** 検討したが却下。`_classify_episodes` は既に summary の embedding を保有し、`view_registry` も持っている — 書き込み責務を分けると利益なしに結合が増える。関数は少し大きくなるが self-contained のまま保たれる。

6. **Phase 1 から per-episode per-view cosine を保存する ("一度計算して全部保存" オプション)。** 検討したが Phase 1 では却下。(a) 全 view との cosine は episode 1 件あたり実計算になり、agent-loop レイテンシに現れる。(b) Phase 2 の centroid 更新で保存値は無効化されるため、保存された多 view cosine の replay utility は限定的。Phase 3 は「必要になる瞬間に」判定のために計算する。

## Consequences

**Positive**:

- Phase 3 以後、`adapters/meditation/` (FEP) と `core/distill.py` が同一枠組みで動く。本 ADR が冒頭で提起した理論的矛盾が解消される。
- Phase 1 単体で base-rate 可観測性が得られる。Phase 2 と 3 が永遠に実装されなくても、noise log は `_classify_episodes` を「silent discarder」から「監査可能なフィルター」へ変える。
- いかなる Phase でも schema migration なし。3 Phase 全てが additive (JSONL ファイル) か behavioural (コードのみ)。
- Phase 境界は独立にロールバック可能。Phase 1 のロールバックは `append_jsonl_restricted` 呼び出し 1 行と `log_dir` 引数の削除のみ。

**Negative / リスク**:

- Noise JSONL のディスク増。最悪 gated episode 1 件あたり ~1KB × 100 件/日 ≈ 年 ~30MB。管理可能だが非ゼロ。Phase 2 で月次ローテーションを追加可能。
- Phase 3 の revelation 昇格には失敗モードがある: `REVELATION_THRESHOLD` が低すぎると revelation が次の LLM prompt に溢れ、`num_ctx` truncation を引き起こす (`project_ollama_num_ctx` メモリ参照)。閾値を Phase 1 データに依存させて意図的に延期しているのは、まさにこの失敗モードを避けるためだが、記載して flag しておく。
- 類比テーブルは誤読を招く。「analogical, not causal」の明示フレーミングが必須であり、コードのインラインコメントではなく ADR 本文にテーブルを置いている理由である。
- `trust_score = 0.3` の revelation-derived pattern が knowledge store に入る。大きな割合が spurious なら ADR-0021 forgetting が追いつかないと累積する。Phase 3 の検証: `generate-report` で昇格率と trust-score ドリフトを追跡する。

**明示的に扱わない** (将来 ADR の領域):

- noise view 自体が「ゴミ」の正しい表現であるか。現状の seed ファイルは under-specified の可能性あり; 再 seed は view ファイル編集で本 ADR とは直交。
- noise JSONL の privacy / retention ポリシー。現状は episode JSONL と同じポリシー (ローカルのみ、0600 パーミッション、アップロードなし) が適用される。Phase 2 で過去ログを読み直すようになったら別ポリシーが必要になる可能性あり。
- `generate-report` の revelation セクションのフォーマット。Phase 3 実装時に延期。

## Rollback Plan

- **Phase 1**: `_classify_episodes` と `distill` から `log_dir` パラメタを削除、`append_jsonl_restricted` 呼び出しと `view_centroids_hash` 計算を削除。既存の `noise-*.jsonl` は残しておく (read-only 観測物) か削除する。データロスなし。
- **Phase 2**: `ViewRegistry.reload_centroid`/`reload_all` と `core/re_classify.py` を削除、CLI subcommand を削除。Phase 1 の writer は動き続ける。
- **Phase 3**: salience ベクトル計算と revelation 分岐を削除、Phase 2 の挙動に戻す。`noise-revelation-*.jsonl` はアーカイブとして残してよい。

各 Phase は独立 commit; どの Phase も後の Phase が land していることに依存しない。

## Migration

データ migration なし。Phase 1 は新規 JSONL ファイルを書く; 既存物は一切改変されない。Phase 2 と 3 は Phase 1 が書いたものを読むだけ。

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.md) — worldview 枠組み。本 ADR は阿頼耶識 / 種子の構造を distill パイプラインに実装化する。
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + views 枠組み。本 ADR は「分類はクエリ、state ではない」原理を noise 分類にも拡張する。
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — forgetting / trust メカニズム。Phase 3 の revelation 昇格は同じ `trust_score` スケールを使う。
- [ADR-0026](0026-retire-discrete-categories.md) — 本 ADR が緩める binary gate。`NOISE_THRESHOLD` gate は残る; 変わるのは gated episode がもう破棄されないこと。
- `adapters/meditation/` — 本 ADR が distill パイプラインレイヤで整合させる Active Inference adapter。
- `~/.claude/plans/wondrous-gliding-feigenbaum.md` — 初期プラン素案; Phase 1 record schema は L92 から乖離 (`const_sim` を落とす) — Decision の view 軸統一論拠に基づく。
