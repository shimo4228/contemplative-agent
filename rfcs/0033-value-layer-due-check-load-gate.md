---
state: draft 2026-09-12
review-when: knowledge.json が embedding sidecar 化（RFC-0031）されれば、このロードは安価になり本 RFC は自動的に無効
---

## Summary

`value_layer_due_check` が毎週 180MB の `knowledge.json` を読む。ゲート条件が事実上
恒真になっており、docstring の主張（「due な週だけ払う」）と実際が食い違っている。

## Motivation

`_constitution_section` のコメントはこう書いている:

> The knowledge.json read stays inside the ``amend_last is not None`` branch:
> the file is >100 MB in production and a weekly reading must not pay for a
> field it will not render

だが `amend_last` は「承認済みの amend-constitution 行が存在するか」であり、live の
audit log には 2 件ある（2026-05-05、2026-08-09）。つまり恒真で、ロードは**毎週**走る。
得られる `patterns_since` は本文冒頭で "Informational only" と明記されたフィールド。

週次無人チェーンの中で 16GB の機体（Ollama 同居）が ~1.5GB のピークを払っている。

## Guide-level explanation

ロードを「改正が due な週」だけにするか、全件パースをやめて `distilled` タイムスタンプを
数えるストリーミング走査に置き換える。

## Reference-level explanation

選択肢:

1. **ゲートを `constitution["due"]` に変える** — docstring が既に主張している条件。
   ただし due でない週の `patterns_since` は null になり、**理由コード無しの null** が
   生まれる。この計器は「unknown が due に見えてはならない」を設計の中心に置いており、
   無印の null はその規律に反する。`KNOWLEDGE_DEFERRED` のような理由コードを足すなら整合する
2. **ストリーミング計数** — 全件 `json.loads` をやめ、`distilled` フィールドだけ拾う。
   読み値は変わらず、メモリだけ落ちる。bare `python3` 前提なので stdlib で書く必要がある
3. **RFC-0031 を先に通す** — sidecar 化すれば元ファイルが ~5MB になり問題自体が消える

## Drawbacks

- 1 は読み値の意味が変わる（null の種類が増える）ので、消費側（土曜ゲート）の読み方も変わる
- 2 は JSON の部分パーサを持つことになり、スキーマ変更に弱くなる

## Rationale and alternatives

`state_invariant_check` では `object_pairs_hook` で embedding を parse 時に捨てる手が
効いた（実測 1.84GB → 1.50GB、出力同一、`a223f36`）。同じ手はここにも効くが、
同じ実験を `export-patterns-jsonl` に当てたら**逆に悪化した**（1.57GB → 1.74GB）ので、
採用するなら計測してからにする。

## Status

draft — 2026-09-12 の simplify 走査で同定。ゲートの恒真化を live の audit log で確認済み。

## Next action

3 案のどれを取るか。RFC-0031 を先に通すなら本 RFC は待ちで良い。
