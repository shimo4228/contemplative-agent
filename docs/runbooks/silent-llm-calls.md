# Runbook: Silent LLM Calls in Tests

> **対象**: Contemplative Agent の pytest が不自然に遅い (全 pass だがフルスイートが分単位)、mock 漏れを疑うとき、新しいテストで LLM / 外部呼び出しを追加したとき。
>
> **ねらい**: Ollama への silent な実呼び出しを `--durations=N` で診断、`tests/conftest.py` の unreachable-URL + `_circuit.reset()` パターンで構造的に遮断する。fail-open 設計 + ローカル Ollama 常駐で 1 ヶ月気づかなかった 2026-04-16 の実例と、症状対処 hook が根本原因診断を隠蔽するアンチパターンを含む。

2026-04-16 に発見: `pytest tests/` が 17 分かかっていた原因は、**テストから実 Ollama インスタンス (localhost:11434) への silent 呼び出し**だった。全テストは pass していた (fail-open セマンティクスで通過)。この runbook は同じ silent bug を次回 5 分以内に検出・予防するための運用手順。

## なぜ silent になるのか (三条件)

以下の三条件が揃うとテストは気づかれずに実サービスを叩く:

1. **Mock 漏れ**: 個別テストで `@patch("...generate")` `@patch("...requests.post")` を張り忘れ
2. **Fail-open 設計**: `core/llm.py::generate()` は例外を握り潰して `None` を返す。呼び出し側 (`check_topic_novelty`, `select_submolt` など) は `None` を「fail-open = 通す」として処理
3. **ローカルで Ollama が常駐**: `ollama serve` が 11434 で動いているので ECONNREFUSED にならず、実応答が 1–8 秒かけて返る

全テストが pass し、唯一の症状は「遅さ」だけ。個別ファイル単位では誰も気にしない水準。フルスイートで積算されて 17 分になる。

## 診断手順 (遅いと感じたら最初に)

### Step 1. `--durations=N` で slowest を特定

```bash
# 個別ファイル単位で測定 (hook に引っかからない)
uv run pytest tests/test_agent.py --durations=15 -q
```

判断基準:

- **<0.005s** (top-N に入らない): 正常な mock 済みテスト
- **0.1–1s**: conftest setup コストの累積、SQLite init 等の疑い
- **1s 以上**: **まず LLM / HTTP の mock 漏れを疑う**。通常 mock 済みで数 ms のテストが秒単位になるのは実呼び出しの証拠

### Step 2. 呼び出し鎖を辿る

遅いテストが呼んでいる関数の LLM 呼び出しを grep:

```bash
# 例: post_pipeline 系のテストが遅い場合
grep -n "generate\|embed_texts" src/contemplative_agent/adapters/moltbook/post_pipeline.py
grep -n "generate\|embed_texts" src/contemplative_agent/adapters/moltbook/llm_functions.py
```

テスト側の `@patch` 一覧と突き合わせ、patch されていない関数を特定。Contemplative Agent で過去に漏れやすかったのは:

- `select_submolt` (llm_functions.py:172)
- `summarize_post_topic` (llm_functions.py:161)
- `generate_session_insight` (llm_functions.py:199)
- `interpret_and_save` の prompt_template=None 経路 (adapters/meditation/report.py:108)

## 予防策 (conftest.py の 2 パターン)

`tests/conftest.py` は既にこの 2 パターンを含んでいる。新しいテストを追加する時は **個別 patch に依存せず、この conftest が保険として機能していることを前提にしてよい**。

### Pattern 1. Ollama URL を unreachable ポートに固定

```python
# tests/conftest.py (モジュールロード前に env を固定)
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
os.environ.setdefault("OLLAMA_TRUSTED_HOSTS", "127.0.0.1")
```

- Port 1 は常に closed → `requests.post` が ~ms で `ConnectionRefusedError`
- `core/llm.py::generate()` の fail-open で `None` に落ちる
- 開発者マシンで Ollama が動いていようといまいと **同じ挙動** になる
- `@patch("...requests.post")` を張っているテスト (test_llm.py 等) は patch が優先

**重要**: conftest.py のトップレベル (import 直下) で env を設定する必要がある。`contemplative_agent.core.config` はモジュールロード時に `MOLTBOOK_HOME` / `OLLAMA_BASE_URL` を定数として capture するので、autouse fixture では遅すぎる。

### Pattern 2. Circuit breaker を毎テストリセット

```python
@pytest.fixture(autouse=True)
def _reset_llm_circuit_breaker():
    from contemplative_agent.core.llm import _circuit
    _circuit.reset()
    yield
    _circuit.reset()
```

これが無いと: Pattern 1 で ECONNREFUSED が連続 → `_circuit` が OPEN → 後続の **mock 済み** テスト (test_llm.py::TestGenerate) で `mock_post` すら呼ばれずに skip → `TypeError: 'NoneType' object is not subscriptable` で失敗する。2026-04-16 に実際に遭遇した罠。

## 新テストを書く時のチェックリスト

新しく `@patch` を張るテストを追加する時:

- [ ] そのテストを `--durations=5` 込みで単独実行し、wall time が `<0.1s` であることを確認
- [ ] 遅い場合、テストが呼ぶ関数の依存 LLM 関数を 1 つずつ grep し、patch 漏れを特定
- [ ] 時間依存 (`time.sleep`, `time.time`) がある場合は `patch("...agent.time")` で `time.sleep = MagicMock()` も含める
- [ ] `mock_time.time.side_effect = [...]` を使う場合、枯渇で実時計に fallback しないよう `chain([...], repeat(終端値))` で無限化する

## 症状対処 hook は根本原因診断を隠蔽する (アンチパターン)

2026-04-11 に `.claude/hookify.require-targeted-tests.local.md` を導入し、`pytest tests/` フル実行を block する運用にした。17 分という discomfort が hook で封印され、**根本原因 (silent LLM 呼び出し) の診断機会が消えた**。2026-04-16 まで 5 日間、診断不可能な状態が続いた。

運用原則:

1. 遅さを感じたら **先に `--durations=N` で 5 分診断する** 。hook を入れるのは診断後
2. discipline hook は「本質的に避けられない遅さ」に対する最後の手段
3. この runbook が存在する以上、`pytest tests/` のフル実行時間が数分を超えたら、再度 silent call を疑う (新規テストで mock を忘れた可能性)

## 関連ファイル

- `tests/conftest.py` — Pattern 1 + Pattern 2 の実装
- `src/contemplative_agent/core/llm.py:127` `reset_llm_config()`, `:144` `_CircuitBreaker`, `:485` `requests.post` — fail-open の実装
- `src/contemplative_agent/adapters/moltbook/llm_functions.py` — mock 漏れが起きやすい LLM 関数群
- commit `362dcf8` — 17 min → 7.4s への縮約コミット
