<!-- Status: Deferred -->
# Knowledge ベクトル検索 — get_context_string() の知能化

## Context

knowledge.json にパターンが蓄積されるが、`get_context_string()` は最新1個しか返さない。パターンが100個あっても使われるのは1個。distill で蓄積する意味が実質ない。

**解決**: knowledge.json と並列にベクトル DB を持ち、distill 時にパターンを embedding して格納。`get_context_string()` が「今の状況に最も関連するパターン」を返せるようにする。

knowledge.json はそのまま残す（可読性・git 追跡・バックアップ）。ベクトル DB は検索インデックスとして並走。壊れても knowledge.json から再構築可能。

## 技術選定（semantic-memory-proposal.md から踏襲）

- **Embedding モデル**: nomic-embed-text (Ollama, 274MB, 768次元, ~10ms/文)
- **Vector DB**: sqlite-vec (SQLite 拡張, pip ~5MB, サーバー不要)
- **M1 制約**: distill 時にバッチ embedding（セッション中は qwen3.5 のみ）

## データフロー

```
distill 実行時:
  エピソード → LLM → パターン抽出
    → knowledge.json に追加（テキスト保存、現行通り）
    → nomic-embed-text でベクトル化 → knowledge.db に追加

get_context_string(query) 呼び出し時:
  query（直近の話題・行動）→ nomic-embed-text でベクトル化
    → knowledge.db で k-NN 検索
    → 関連性の高いパターン top_n 件を返す

フォールバック:
  nomic-embed-text 未インストール or knowledge.db なし
    → 現行動作（最新1パターン）にフォールバック
```

## 変更対象ファイル

### `core/embedding.py` — **新規** (~80行)

Ollama embedding API のラッパー。

```python
def embed_text(text: str, model: str = "nomic-embed-text") -> Optional[List[float]]:
    """Ollama /api/embed エンドポイントでテキストをベクトル化。
    Ollama 未起動 or モデル未インストール時は None を返す。"""

def embed_batch(texts: List[str], model: str = "nomic-embed-text") -> List[Optional[List[float]]]:
    """複数テキストを一括 embedding。"""
```

既存の `core/llm.py` の Ollama 接続設定（LOCALHOST_HOSTS, OLLAMA_TRUSTED_HOSTS）を再利用。

### `core/knowledge_index.py` — **新規** (~150行)

sqlite-vec によるベクトルインデックス。

```python
class KnowledgeIndex:
    def __init__(self, db_path: Optional[Path] = None) -> None: ...
    def add(self, pattern: str, vector: List[float], distilled: str) -> None: ...
    def search(self, query_vector: List[float], top_n: int = 3) -> List[str]: ...
    def rebuild(self, patterns: List[dict], embed_fn: Callable) -> int: ...
    def count(self) -> int: ...
```

DB パス: `~/.config/moltbook/knowledge.db`

### `core/knowledge_store.py` — 変更 (~30行)

- `__init__` に `index_path` 引数追加
- `_index: Optional[KnowledgeIndex]` を保持
- `add_learned_pattern()` 時に embedding → index 追加（embed 失敗時はスキップ）
- `get_context_string()` を拡張:

```python
def get_context_string(self, query: Optional[str] = None, top_n: int = 3) -> str:
    # ベクトル検索が可能ならそちらを使う
    if query and self._index and self._index.count() > 0:
        query_vec = embed_text(query)
        if query_vec:
            patterns = self._index.search(query_vec, top_n=top_n)
            if patterns:
                return "\n".join(f"- {p}" for p in patterns)
    # フォールバック: 最新パターン
    if not self._learned_patterns:
        return ""
    last = self._learned_patterns[-1]["pattern"]
    return f"Pattern: {last}"
```

### `core/distill.py` — 変更 (~5行)

distill 完了後に新パターンを index に追加。embed 失敗時はスキップ（knowledge.json への保存は影響なし）。

### `adapters/moltbook/post_pipeline.py` — 変更 (~5行)

`get_context_string()` に query（直近のフィード話題）を渡す。

### `adapters/moltbook/config.py` — 変更 (~2行)

`KNOWLEDGE_INDEX_PATH` 追加。

### `cli.py` — 変更 (~20行)

`reindex` サブコマンド追加（knowledge.json の全パターンをベクトル化して DB 再構築）。

### `config/` — 変更なし

knowledge.json はそのまま。

## 依存追加

| パッケージ | サイズ | 必須？ |
|-----------|--------|--------|
| `sqlite-vec` | ~5MB | Optional（なければフォールバック） |
| `nomic-embed-text` (Ollama) | 274MB | Optional（なければフォールバック） |

既存の `requests` のみ依存ポリシーに `sqlite-vec` を追加。ただしオプショナル扱い（import 失敗時は機能無効化）。

## セキュリティ

- embedding API は既存の Ollama 接続（LOCALHOST_HOSTS + OLLAMA_TRUSTED_HOSTS）を使用
- knowledge.db は `write_restricted()` で 0600 パーミッション
- ベクトルには生テキストを含まない（パターン文字列は knowledge.json が正）
  → いや、検索結果でテキストを返す必要があるので、DB にもテキストを格納する
  → forbidden pattern 検証は knowledge_store.load() で既に実施済み

## 変えないもの

- knowledge.json — そのまま（正のデータソース）
- EpisodeLog — そのまま
- identity.md — そのまま
- セッション中の動作 — そのまま（embedding はバッチ処理のみ）
- distill のロジック — パターン抽出は変えない。追加で embed するだけ

## 実装規模

| 項目 | 行数 |
|------|------|
| `core/embedding.py` | ~80 |
| `core/knowledge_index.py` | ~150 |
| `core/knowledge_store.py` 変更 | ~30 |
| `core/distill.py` 変更 | ~5 |
| `adapters/` 変更 | ~10 |
| `cli.py` 変更 | ~20 |
| テスト | ~150 |
| **合計** | **~445行** |

## Verification

```bash
# 1. 依存インストール
pip install sqlite-vec
ollama pull nomic-embed-text

# 2. 既存テスト全パス（回帰なし）
uv run pytest tests/ -v

# 3. reindex で既存パターンをベクトル化
contemplative-agent reindex
# → "Indexed N patterns" と表示

# 4. distill で新パターンが自動的に index に追加されること
contemplative-agent distill --dry-run --days 1

# 5. get_context_string() がベクトル検索結果を返すこと
# → テストで検証

# 6. nomic-embed-text 未インストール時にフォールバックすること
# → テストで検証

# 7. sqlite-vec 未インストール時にフォールバックすること
# → テストで検証
```
