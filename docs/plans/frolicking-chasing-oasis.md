# T-CTX-TOKENIZER — C2 予算ガードに実トークン計数の seam を足す

## Context

`core/llm/__init__.py:389-427` の C2 予算ガードは、入力トークン数を実測せず
`_estimate_tokens`（`prompting.py:306`）の**上振れ推定**で測っている。推定器は ASCII を
3 chars/tok・**CJK を 2 tok/char** で数える設計上の上限値であり、バグではない
(ADR-0066 §5 が意図的にそう硬めた — 当時は under-count がガードを素通りさせる方が危険だった)。

2026-08-01 に別セッションが macOS 26.6 の `apple-fm-sdk` `SystemLanguageModel.token_count` で
初めて実測し、**過大率 1.73〜1.95x** を定量化した（identity.md 232→134 / constitution 867→453 /
rules 516→264 / skills 37 件 31,009→17,958 / 10 patterns 479→263）。日本語主体の入力ほど乖離する。

**影響**: 4,096 窓の backend では実効入力天井が 2,048 推定 ≒ **1,140 実トークン = 窓の 28%** に
なり、残り 72% を使わずに `budget_exceeded` で skip する。Ollama 路（32,768）でも同じ倍率で
早期に clamp / skip している。

**到達したい状態**: `LLMBackend` が実トークン計数を**持てるなら使い、無ければ推定器に落ちる**。
先例は隣にある `LLMBackend.context_window`（ADR-0066）— Protocol に宣言して pyright に
促させつつ、ガードは実行時に不在を許容する、という規律。それに揃える。

**Ollama 路が推定器のままである理由**（2026-08-01 実測。「repo に tokenizer 依存が無い」より
一段強い理由がある）:

- ローカル稼働中の **Ollama 0.30.11 で `/api/tokenize` / `/api/detokenize` は 404** — route
  自体が存在しない。上流 PR [ollama#12030](https://github.com/ollama/ollama/pull/12030) は
  2025-08-22 に出て 2026-06-04 更新・**未マージのまま open**、要望 issue
  [#12031](https://github.com/ollama/ollama/issues/12031) も open。依存追加の可否以前に、
  **呼べる計数 API が無い**
- `/api/generate` が返す `prompt_eval_count` は実入力トークン数だが**呼んだ後**にしか得られず、
  pre-flight ガードには原理的に使えない。これを推定器と突き合わせる較正は台帳が言う read-only
  計器＝範囲外の項目そのもの

したがって Ollama 路は無改変（制約 1）。ただし本 PR で足す seam は、上流 PR が入った時点で
**ガードを触らずに** Ollama 路へ実計数を差し込める形になる（ADR の follow-up に発火条件を記録）。

## External Research Findings（Phase 0 / `/search-first`）

`Verdict: Build — custom (~40 行の seam)`。依存追加が制約で不可（tiktoken / tokenizers は
積めない）なので採用対象の library は存在しない。借りるのはパターンのみ:

- **LangChain** `BaseLanguageModel.get_num_tokens(text) -> int` — 基底が approximate default を
  持ち、model 固有実装が override する。今回の優先順位（推定器が既定、backend が上書き）と同型
- **LlamaIndex** `OpenAILike.tokenizer: Union[Tokenizer, str, None] = None`（"If left as None,
  then this disables inference of max_tokens."）— capability が無ければ**依存する推論だけ**を
  degrade させる nullable capability。`context_window` を借りたのと同じ object 上の作法
- **LiteLLM** `token_counter(...)` は tokenizer 不在時に tiktoken へ fallback。fallback 前提は
  業界標準だが、その fallback 先が実 tokenizer である点だけは制約 1 により模倣できない

命名は LiteLLM の新 public API `count_tokens` に合わせる（Apple の `token_count` とも読みが一致）。

## Implementation Chain（種別: `feat`）

`feat` を選ぶ理由: 振る舞いを変えない構造変更ではなく、`LLMBackend` に**新しい任意 capability**を
足し、ガードの測定源を増やす。

| ステップ | 実施 |
|---|---|
| Plan | 本ファイル（介入点 1） |
| Phase 0 External Research | 済（上記 Verdict） |
| TDD | Y — 失敗するテストを先に置く。chaos fault column も同じ PR |
| Code Review (python-reviewer) | Y |
| Security Review (security-reviewer) | Y — 外部 backend が返す値を信頼境界越しに受ける |
| Cross-Model Review (codex-review) | Y — 実装差分に対して。plan には走らせない |
| Doc Sync | Y — ADR-0087 新設 / CODEMAPS Data Flow / graph.jsonld / otel mapping |
| Verify | Y — `.claude/verify.sh` |
| User-Run `/code-review` | U — 意図確認 gate で提案（自動枠の代替ではない） |

Review 3 種は同じ diff に**並列起動**。早期停止: いずれかが CRITICAL を返したら中断して報告。

## 設計

### 1. `core/llm/backend.py` — 任意 capability の Protocol

`count_tokens` を `LLMBackend` 本体には**足さない**。Protocol は structural typing なので、
本体に足すと body の有無に関わらず既存 implementer が静的に非適合になり、sibling repo
(`contemplative-agent-cloud` / `-mlx`) が「実装しないと型が通らない」状態になる。トークナイザを
持てない backend が正当に存在する以上、それは誤った要求。よって**別 Protocol** で表現する:

```python
@runtime_checkable
class TokenCountingBackend(LLMBackend, Protocol):
    def count_tokens(self, text: str) -> int: ...
```

- 実装しない backend は `LLMBackend` のままで従来どおり有効（**制約 2 を満たす**）
- 実装する backend には pyright が検証する型付きの的ができる（`context_window` と同じ意図）
- ガードの実行時解決は `getattr(_backend, "count_tokens", None)` + `callable()`
  （`context_window` の `getattr` idiom と同一。`isinstance` は属性が callable でなくても通るため使わない）

理由コードの語彙も同ファイルに定数として置く（テストが「発行された理由は語彙内」を検査する）:

```python
TOKEN_COUNT_FALLBACK_REASONS = (
    "counter_exception", "counter_none", "counter_type",
    "counter_negative", "counter_degenerate",
)
```

### 2. `core/llm/__init__.py` — 測定の解決

`served_model()` と同じく `_backend` を直読みする private 関数を `_generate_impl` の直上に置く:

```python
@dataclass(frozen=True)
class _InputTokenMeasurement:
    system: int
    prompt: int
    source: str                  # "backend" | "estimator"
    fallback_reason: str | None  # sparse — counter が在って棄却された時のみ

def _measure_input_tokens(system: str, prompt: str) -> _InputTokenMeasurement: ...
```

解決規則（すべて明示・silent fallback なし）:

1. counter が無い → `source="estimator"`, `fallback_reason=None`
   （**不在は fallback ではなく既定**。理由コードを立てるとノイズになる）
2. counter が在る → system / prompt の両方を数える。**両方が妥当な時だけ**採用する
   （measured system と estimated prompt を混ぜた予算は不整合になるので原子的に扱う）
3. 妥当性: `bool` を除く `int` / 非負 / **非空白テキストに対する 0 を棄却**。
   実トークナイザが中身のあるテキストに 0 を返すことはない。under-count はガードを素通りさせる
   方向の故障（Ollama の front-truncation / メモリ制約 backend の KV 超過）なので、
   ここだけは「安全側 = 推定器に戻る」で倒す
4. 例外は捕捉して推定器に戻す。**circuit breaker には触らない** —
   計数の失敗は生成の失敗ではない（over-budget skip が breaker を触らないのと同じ論理）

### 3. ガード本体（`__init__.py:390-427`）の変更

`est_system` / `est_prompt` を測定値に差し替えるのみ。**`MIN_CLAMPED_NUM_PREDICT` は触らない**
（制約 3 — T-NUMPREDICT-FLOOR と同じ変数。同 PR で床を動かすと寄与が判別不能になる）。
clamp / skip の分岐構造も不変。WARNING 文言に `source=` を足す
（既存テストが assert する `"audit C2"` / `"Clamping num_predict"` の部分文字列は保持）。

### 4. テレメトリ（Observability by default）

`_generate_full` の base record に dense フィールドを 2 本追加（ガード未実行時は `None`）:

- `token_count_source`: `None` | `"estimator"` | `"backend"`
- `input_tokens`: ガードが実際に使った system+prompt の合計

sparse で 1 本:

- `token_count_fallback_reason`: counter が在って棄却された時のみ

「推定器を使ったか実測を使ったか」が `llm-calls-{date}.jsonl` から後で判別でき、clamp 判断が
オフラインでリプレイできる（値が無いと「どちらを使ったか」は半分の答えにしかならない）。

副産物として、`input_tokens`（ガードが使った値）が既存の `prompt_eval_count`（Ollama が返す
実入力トークン数）と**同じ行に並ぶ**。較正計器を作らなくても突き合わせデータは行の中に揃うので、
T-NUMPREDICT-FLOOR 側は後から読むだけでよくなる（計器は依然として本 PR の範囲外）。

### 範囲外（意図的に触らない）

- **`BackendResult.prompt_tokens` を使った推定器の実測比計器** — 台帳行にあるが T-NUMPREDICT-FLOOR
  側の入力。ここでは seam だけ
- **`core/insight_novelty.py` の packing budget** — 同じく `_estimate_tokens` + `context_window` を
  読むが別の消費者。ガードが実測で**緩む**方向に動いても、packing 側は推定器のまま =
  preflight より**きつい**ままなので安全側（`_novelty_ctx_window()` の docstring が明記する
  「packing tighter than the preflight is safe」が成立し続ける）。追随は別タスク
- **skill 注入数**（制約 4 — T-SKILLSEL の観察窓が 08-07〜08-21）
- **Ollama 路への実計数** — 上流に endpoint が無い（上記）。ADR の follow-up に発火条件だけ記録
  する: PR ollama#12030 がマージされ稼働版に載ったら、`count_tokens` seam 経由で
  `_measure_input_tokens` に差し込む（ガード本体は無改変で済む）。ただし generate 毎に
  HTTP 往復が 1 回増えるので、採用は無人運用の latency 影響を測ってから

## TDD（テスト先行）

### 正常系 — `tests/test_llm.py`

`TestGenerateBudgetGuard` / `TestGenerateBudgetClamp` の隣に追加:

- **回帰 fixture（このタスクの本体）**: `context_window=4096` + `count_tokens` が実測相当を返す
  backend に、推定器なら `available < MIN_CLAMPED_NUM_PREDICT` で skip される日本語主体の入力を
  渡す → **skip されずに委譲される**。1.73〜1.95x の発見をテストに焼く
- counter を持つ backend では clamp 値が実測から計算される
- counter を持たない backend / Ollama 路は推定器のまま（既存テストが不変で通ることが証拠）

### Fault column — `tests/test_llm_chaos.py`（ADR-0077）

`tests/chaos.py` に `TokenCountingChaosBackend(ChaosBackend)` を追加する
（既存 `ChaosBackend` は無改変 = 既存 chaos テストに影響しない）。counting 側の fault schedule:
`COUNT_OK` / `COUNT_EXC` / `COUNT_NONE` / `COUNT_TYPE` / `COUNT_NEGATIVE` / `COUNT_ZERO`。

各 fault について**望ましいガード挙動を先に主張する**:

1. 推定器へ落ちる（測定が壊れてもガードが無効化**されない** — 一番危険な故障モード）
2. `token_count_fallback_reason` が `TOKEN_COUNT_FALLBACK_REASONS` 内の値で立つ
3. circuit breaker が触られない（計数の失敗は生成の失敗ではない）
4. 片側だけ壊れた場合も両方推定器（原子性）
5. hypothesis: `count_tokens` の返り値を任意スカラーで fuzz し、**int 以外は一つも採用されない**

### テレメトリ — `tests/test_llm_telemetry.py`

3 フィールドが期待値で載ること、ガード未実行（`context_window` を持たない backend）では
`None` のままであること。

## 変更ファイル

| ファイル | 変更 |
|---|---|
| `src/contemplative_agent/core/llm/backend.py` | `TokenCountingBackend` Protocol + 理由コード語彙 |
| `src/contemplative_agent/core/llm/__init__.py` | `_InputTokenMeasurement` / `_measure_input_tokens` / ガード差し替え / telemetry 3 本 / re-export |
| `tests/chaos.py` | `TokenCountingChaosBackend` + count fault 語彙 |
| `tests/test_llm.py` | 正常系 + 回帰 fixture |
| `tests/test_llm_chaos.py` | fault column |
| `tests/test_llm_telemetry.py` | telemetry フィールド |
| `docs/adr/0087-*.md` + `.ja.md` | 新 ADR（ADR-0066 との override 関係を明記） |
| `docs/adr/README.md` / `README.ja.md` | index 行 |
| `docs/CODEMAPS/architecture.md` | Data Flow 51 行目（鮮度規約 — 同じ PR で） |
| `graph.jsonld` | ADR node（ADR 新設は両面更新） |
| `docs/otel-semconv-mapping.md` | 新フィールドを `ca.audit.*` 行へ |

## Verify

1. `uv run pytest tests/ -v`（新規テストが先に赤 → 実装後に緑）
2. `.claude/verify.sh`（format / lint / type check / security / dependency / test）
3. `uv run lint-imports`（`core/` ← `adapters/` ← `cli.py` の一方向依存）
4. secret scan / `git status` 確認
5. **sibling 非破壊の確認**: `count_tokens` を持たない stub backend（既存
   `test_guard_skipped_when_backend_omits_context_window` の StubBackend 形）が
   `TypeError` を起こさず従来どおり委譲すること = 制約 2 の機械的証拠

その後 python-reviewer / security-reviewer / codex-review を diff に並列起動 → 全 PASS で
意図確認（`plan との差分` の 3 値宣言）→ commit。
