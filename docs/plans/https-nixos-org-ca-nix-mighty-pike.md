# Ollama モデル digest と Ollama 版を監査面に記録する

## Context

Nix 導入を検討した結果、CA の再現性で本当に欠けているのは「どの重み・どの Ollama で出力が出たか」であり、Nix はここに届かない。現状:

- 監査面はモデル**名**しか持たない。`core/llm/__init__.py::served_model()` → llm-calls 各行、`core/snapshot.py` の manifest（`generation_model` / `embedding_model`、ADR-0069）、`cli/runtime.py::_llm_session_meta()` → session start episode。
- `gemma4:e4b` / `nomic-embed-text` は mutable tag。pull し直せば別の重みになるが、docs/evidence の凍結値と紐付ける手段が無い。
- Ollama 側は `GET /api/version` と `GET /api/tags`（各モデルに `digest` sha256）で取得可能（localhost 0.30.11 で確認済み）。

fix 種別。新計器ではなく既存監査レコードへのフィールド追加（ADR-0101 の消費計画は不要）。observability は best-effort、生成の正否に影響させない（ADR-0020/0075 の既存規約）。

## 変更

### 1. `core/llm/__init__.py` — `serving_environment()` を追加

プロセス内 1 回だけ Ollama に問い、結果をキャッシュして返す純メタデータ関数。

```python
def serving_environment() -> dict[str, Any]:
    # 返り値（キーは常に全部出す。取れない値は None + reason）
    {
      "ollama_version": "0.30.11" | None,
      "generation_model_digest": "<sha256 先頭 12>" | None,
      "embedding_model_digest": "<sha256 先頭 12>" | None,
      "serving_environment_reason": "ok" | "ollama_unreachable" | "backend_injected"
                                    | "model_not_listed:<name>" | ...,
    }
```

- `GET {_get_ollama_url()}/api/version`、`GET .../api/tags`。timeout 短め（5s）。`requests.RequestException` / 形状不一致は捕まえて None + reason。**決して raise しない**。
- tag 正規化: 名前に `:` が無ければ `:latest` を付けて `/api/tags` の `name` と照合（`nomic-embed-text` → `nomic-embed-text:latest`）。
- `_backend` 注入時（cloud / mlx）は generation digest を None、reason `backend_injected`。embedding は常に Ollama なので引き続き取る。
- digest は 12 hex に切る（`prompt_sha256[:12]` と同じ流儀）。
- キャッシュは module-level 変数、`reset_llm_config()` で消す（テスト分離）。
- embedding モデル名は `core.embeddings._get_embedding_model()` を使う（既存 import 方向で問題なし。llm → embeddings は既に telemetry seam で逆向きがあるので循環に注意 — 関数内 import にする）。

### 2. 記録先 2 箇所

- `cli/runtime.py::_llm_session_meta()` — 返す dict に `**serving_environment()` をマージ。`run` セッションは session start episode 1 行に載る（per-call の llm-calls には**載せない** — 行の肥大を避け、session_id / run_id で join できる）。
- `core/snapshot.py::write_snapshot()` — 新 kwarg `serving_env: dict[str, Any] | None = None` を追加し、manifest に `generation_model` の隣で展開。snapshot は LLM module から decoupled という既存方針に従い、`cli/memory_cmds.py::_take_snapshot()` が `serving_environment()` を呼んで渡す。

### 3. テスト

- `tests/test_llm_telemetry.py` か新規 `tests/test_serving_environment.py`: `requests.get` を patch して (a) 正常系 digest 12 hex + version、(b) 到達不能 → 全 None + `ollama_unreachable`、(c) tag 正規化、(d) backend 注入 → `backend_injected`、(e) 1 プロセス 1 回のキャッシュ。
- `tests/test_snapshot.py`: `serving_env` が manifest に出る / None なら省略される。
- `_llm_session_meta` の既存 consumer（`cli/agent_cmds.py` の session start dict）が壊れないこと。

### 4. Doc sync

- ADR-0069（en + ja）に日付付き追補 1 節: manifest と session start episode が digest / Ollama 版を持つこと、理由（mutable tag と evidence の紐付け）、Nix 検討の経緯 1 行。
- `docs/adr/README.md` の変更不要（新 ADR なし）。graph.jsonld 変更不要。

## Verify

```bash
uv run pytest tests/test_snapshot.py tests/test_llm_telemetry.py tests/test_serving_environment.py -v
.claude/verify.sh
# 実機: Ollama 稼働中に
uv run python -c "from contemplative_agent.core.llm import serving_environment; print(serving_environment())"
# → ollama_version 0.30.11、gemma4:e4b の digest 先頭 c6eb396dbd59
```

`contemplative-agent distill --dry-run` は snapshot を取らないので、manifest 実機確認は次回の週次 insight の `snapshots/*/manifest.json` で行う。
