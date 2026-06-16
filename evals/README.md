# evals/ — promptfoo prompt-regression harness

`config/prompts/*.md` を変更したときに distill パイプラインの出力契約が壊れていないかを
ローカル Ollama 相手に検証する回帰スイート。§C1（公理除去 A/B）/ §C2（モデル比較）の
実験基盤を兼ねる。npm 依存はリポジトリに追加しない（`npx` 実行のみ）。

## 実行方法

```bash
cd contemplative-agent
export PROMPTFOO_PYTHON=$PWD/.venv/bin/python   # prompt functions が src/ を import する
unset MOLTBOOK_HOME                              # ランタイム prompt override の混入防止（必須）

# 回帰スイート（temperature 0 + seed 固定）
npx promptfoo@latest eval -c evals/promptfooconfig.step1.yaml \
  -o evals/results/step1-$(date +%Y%m%d-%H%M%S).json
npx promptfoo@latest eval -c evals/promptfooconfig.step2.yaml

npx promptfoo@latest view   # ブラウザ UI で出力・差分を確認
```

`evals/results/` は gitignore（promptfoo 自身の eval DB は `~/.promptfoo/` でリポジトリ外）。

## 構成

| パス | 役割 |
|---|---|
| `prompts/distill_prompts.py` | prompt functions。**本番コードを import して描画**（`core.prompts` の lazy loader + `summarize_record` + `get_distill_system_prompt()`）。テンプレート複製ゼロ、ドリフトゼロ |
| `promptfooconfig.step{1,2}.yaml` | 回帰スイート 2 本（抽出 / refine）。Step 3（importance 採点）は ADR-0056 で廃止 |
| `asserts/common.py` | Python assertion。本番の `strip_code_fence` + `_is_valid_pattern` で判定 |
| `fixtures/` | 合成 episode fixture（下記ポリシー参照） |
| `experiments/` | §C1 / §C2 の A/B 雛形（実施は別セッション、§B1 観察窓明け後） |

## 設計ノート

- **temperature 0 の回帰は「能力下限」のテスト**であり、本番分布（temperature 1.0）とは
  別物。回帰スイートは構造契約（JSON 形・件数・injection token 不在）だけを見る。
  golden text 比較はしない
- 実験スイート（experiments/）は本番 temperature 1.0 + `--repeat 5` で分布を比較する。
  assertion は最小限にし、判断は `view` UI と出力 JSON の目視で行う
- provider は `ollama:chat`（Ollama 内部で `/api/generate`+system と同一の chat template に
  解決される）。`num_ctx: 32768` / `num_predict: 3000` / `top_p: 0.95` / `top_k: 20` /
  `think: false` は本番 `core/llm.py` payload と同値

## Fixture ポリシー（重要）

- episode fixture は **合成データのみ**。正本は `tests/fixtures/benchmark/synthetic.jsonl`
  （40 件）で、`fixtures/synthetic_small_{a,b}.jsonl` はその派生、
  `synthetic_injection.jsonl` は injection canary 入りの新規合成
- `~/.config/moltbook/logs/*.jsonl`（実エピソードログ）を fixtures に転用する場合は
  **事前にユーザー承認 + 無害化（injection token 除去・固有情報マスク）が必須**。
  Claude Code は実ログを直接読まない（CLAUDE.md セキュリティ方針）
- `fixtures/raw_outputs/`（Step 2 入力）は Step 1 の実出力を一度採取して固定したもの。
  再採取するときは step1 スイートを流して出力をコピーし、無害であることを確認してから
  commit する
