# ADR-0070: MLX バックエンドを sibling repo へ退役し、Docker を main から削除する

## Status

accepted — ADR-0064（MLX 生成バックエンド）と ADR-0006（Docker network isolation）を supersede する。ADR-0065 の MLX 部分の supersession を完了させる（served-model-id テレメトリ契約は存続）。ADR-0067 の Decision #3 を改訂する（main に温存していた opt-in MLX エントリポイントを削除し、移設する）

## Date

2026-06-28

## Context

[ADR-0067](./0067-keep-ollama-for-unattended-production.md) は、16GB Apple Silicon の無人連続運用では
`mlx_lm.server` が不適と判断し、本番を Ollama に revert した。ただし **MLX バックエンドのコードと
全 opt-in エントリポイントを温存した**（Decision #3）: `core/mlx_backend.py`、`scripts/serve-mlx.sh`、
`scripts/run-with-mlx.sh`、`cli.py` の `LLM_BACKEND=mlx` 分岐、そして `agent-run` skill の `mlx`
オプションである。MLX も Docker も本番経路には乗っていない: launchd ジョブは Ollama を直接呼び、
[ADR-0006](./0006-docker-network-isolation.md) のコンテナデプロイはメンテナの研究運用では使われずに
来た。

本 ADR の動機は 2 つの非対称性にある:

- **MLX は構造的には cloud と対称だが、配線が非対称だった。** `MlxLmBackend` は、
  `contemplative-agent-cloud` add-on が `configure(backend=...)` 経由で out-of-band に注入するのと
  同じ `LLMBackend` Protocol を実装する。にもかかわらず MLX は `cli.py` *の中に* ハードコードされた
  `LLM_BACKEND=mlx` 分岐として配線されていた — cloud の zero-in-tree-footprint な注入とは違い、
  in-tree なバックエンドである。本番で使わないバックエンドを composition root の中に抱えることは
  security-by-absence に反する。
- **Docker はそもそも Protocol 形ではない。** アプリ全体をコンテナに包むものであり、ワンポイントの
  `LLMBackend` seam を通じて注入するものではない。

オーナーの決定: 両方を main から退役させる。MLX は cloud と対称なので *移設* する — sibling の
`contemplative-agent-mlx` repo（後続作成）が `MlxLmBackend` を Protocol 注入の add-on として担い、
`contemplative-agent-cloud` をそのまま鏡写しにする。Docker はインフラ wrapper なので単純に *削除* する。
どちらも git history が移行元であり、失われるものは何もない。

## Decision

1. **MLX バックエンドを main から削除する。** `core/mlx_backend.py`、`scripts/serve-mlx.sh`、
   `scripts/run-with-mlx.sh`、`tests/test_mlx_backend.py`、そして `cli.py` の `LLM_BACKEND=mlx`
   分岐（およびその session-meta 分岐）を削除する。`cli.py` はもはやバックエンド選択をハードコード
   しない。

2. **backend 非依存の注入 seam は保持する。** `LLMBackend` Protocol、`BackendResult`、
   `configure(backend=...)`、`_generate_via_backend`、served-model-id テレメトリ契約（ADR-0065）、
   backend-aware な context-budget guard（ADR-0066）はすべて残す — これらは provider 非依存で、
   cloud add-on を運ぶものである。代替バックエンドは cloud が使うのと同じ seam を通じて out-of-band に
   注入される。main 自身は default の Ollama 経路のみを宣言する。

3. **MLX は破壊せず移設する。** sibling の `contemplative-agent-mlx` repo（後続）が、
   `MlxLmBackend` + `serve-mlx.sh` を Protocol 注入の add-on として再構成し、
   `contemplative-agent-cloud` と対称にする。git history が移行元である。

4. **Docker を main から削除する。** `Dockerfile`、`docker-compose.yml`、
   `docker-compose.override.yml`、`docker-entrypoint.sh`、`.dockerignore`、`setup.sh` を削除する。
   Docker は `git revert` で復元可能であり、sibling repo へは移設しない（Alternatives 参照）。

5. **evidence と apple-silicon skill は保持する。** `docs/evidence/adr-0064/` と
   `docs/evidence/adr-0067/` は、退役の実証的根拠として、また将来の再評価のために残す。
   `apple-silicon-local-llm-serving` skill は、MLX コードがどこに置かれるかとは独立に再利用可能な
   Apple-Silicon-runtime の判断として残す。

6. **Supersession。** ADR-0064 と ADR-0006 は本 ADR により supersede される。ADR-0065 の launchd
   半分は既に revert 済み（ADR-0067）であり、その MLX バックエンド参照も今 supersede されるが、
   served-model-id テレメトリ契約は存続する。ADR-0066（context guard）と ADR-0068（per-call think
   flag）は backend 非依存であり無改変である。

## Alternatives Considered

### MLX を main の opt-in のまま維持する（ADR-0067 Decision #3 の status quo）

却下。main が本番で一度も使わないバックエンドを抱え、`cli.py` が `LLM_BACKEND=mlx` をハードコード
する — cloud add-on の out-of-tree な注入と非対称である。これを削除して Protocol 注入に標準化する方が
cleaner であり、security-by-absence を強化する（in-tree な生成経路は Ollama だけになる）。

### Docker のように MLX も丸ごと削除する（sibling repo なし）

却下。MLX は `LLMBackend` を実装するため、`contemplative-agent-cloud` と同じ sibling-add-on 形に
収まる。sibling repo は ADR-0064 の ~1.8 倍速・~3.4GB 軽の優位を対話用途の opt-in として保存し、
Protocol 注入パターンを 2 度目に実演する — 小さなコストで。丸ごと削除すればそれを捨てることになる。

### 対称性のため Docker も sibling repo へ移設する（MLX との対称）

却下。Docker はワンポイントの Protocol を通じて注入するのではなくアプリ全体を包むので、sibling は
main のバージョンを pin して追従し続けねばならない — 研究で使われていないデプロイモードのための
継続的メンテナンスである。`git revert` の方が安い復元経路だ。MLX と Docker を別扱いにするのは、
まさに両者の構造が異なるからこそ正しい。

### evidence や apple-silicon skill を削除する

却下。A/B テレメトリと prefill-degradation の記録は、退役の load-bearing な正当化であり、いかなる
再試行の baseline でもある。削除すれば ADR-0067 の論拠が opaque になる。skill は MLX コードがどこに
あろうと有用な Apple-Silicon runtime の判断（mlx_lm.server vs Ollama のトレードオフ）を encode して
いる。

## Consequences

### Positive

- main がより lean になり（core 25 → 24 モジュール）、backend seam が均一になる: MLX（sibling）も
  cloud（sibling）も `configure(backend=...)` を通じて注入する。in-repo のバックエンド分岐は残らない。
- security-by-absence が強化される — in-tree な生成経路は Ollama だけになり、あらゆる代替バックエンドは
  opt-in かつ out-of-tree になる。
- Docker のコンテナ / 2 サーバという運用面が main から消える。

### Negative

- MLX を使うには、今や（まだ作成されていない）`contemplative-agent-mlx` sibling のインストールが
  必要になる。その repo が存在するまで、MLX はこの変更の `git revert` でのみ到達可能である。
- Docker の復元は `git revert` であり、維持された経路ではない。

### Cross-repo / follow-up

- git history から `contemplative-agent-mlx` を作成する: `MlxLmBackend` + `serve-mlx.sh` を Protocol
  注入の add-on として再構成する。インストールパターンは `contemplative-agent-cloud` を鏡写しにする。
  それまでの間、`agent-run` skill の `mlx` バックエンドオプションは削除され（ollama default + cloud は
  存続）、`.env.example` / CLAUDE.md / CODEMAPS の MLX 参照は落とされる。
- **更新（2026-06-28）: 完了。** sibling repo `contemplative-agent-mlx` が存在するようになった —
  `MlxLmBackend` + `serve-mlx.sh` / `run-with-mlx.sh` を commit `c291ab0` から Protocol 注入の add-on
  として再構成した（`contemplative-agent-cloud` を鏡写しにし、`MlxLmBackend` が
  `context_window=32768` を宣言するので ADR-0066 の budget guard が適用される）。`agent-run` skill の
  `mlx` オプションは新しい `contemplative-agent-mlx` エントリポイントへ再配線され、README / CLAUDE.md の
  cross-link は復元された。MLX は今や add-on としてインストール可能であり、`git revert` がそこへの唯一の
  経路ではなくなった。

### Reversibility

- MLX: 本コミットを `git revert` すれば in-tree バックエンドが復元される。あるいは sibling repo が存在
  するようになれば、それをインストールする。
- Docker: `git revert` で 6 つのインフラファイルすべてが復元される。

## References

- [ADR-0064](./0064-mlx-generation-backend.md) — opt-in MLX backend；本 ADR により **superseded**
- [ADR-0006](./0006-docker-network-isolation.md) — Docker network isolation；本 ADR により **superseded**
- [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) — launchd 配線は ADR-0067 で revert 済み；MLX バックエンド参照は本 ADR で superseded；served-model-id テレメトリ契約は存続
- [ADR-0066](./0066-backend-aware-context-budget-guard.md) — backend-aware context guard；backend 非依存、無改変
- [ADR-0067](./0067-keep-ollama-for-unattended-production.md) — MLX を opt-in のまま温存した（Decision #3）；本 ADR はその in-tree コードを削除して退役を完了させる
- [ADR-0007](./0007-security-boundary-model.md) — security-by-absence / reversibility 姿勢
- `contemplative-agent-cloud` — MLX が今や倣う Protocol 注入の先例（sibling add-on）
- 保持された evidence: [docs/evidence/adr-0064/](../evidence/adr-0064/)、[docs/evidence/adr-0067/](../evidence/adr-0067/)
