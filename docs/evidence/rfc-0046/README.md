# RFC-0046 evidence — relevance gate の lab ratchet（S35 label set の凍結、2026-10-07）

[RFC-0046](../../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) の face gate（2026-10-04 keep）の後始末 2 で、
S35 の label set（2026-09-28、150 行、審判 Jev、t = 0.3 を選んだ読み）を score4 gate の lab ratchet として凍結した
（[ADR-0113](../../adr/0113-decision-faces-and-relevance-score4-shadow.md) 2026-10-07 追補 8）。

**本体はここに置かない。** `rows.jsonl` は他エージェントの投稿本文（`content_b64`）を、`labels.jsonl` は他エージェントの
投稿を名指す post_id の一覧を持つので、本体は main tree の `.notes/labels/relevance/2026-09-28/`（gitignored）に
書き込み不可で置いたままにする。ここに置くのは
[label-set-2026-09-28.json](label-set-2026-09-28.json) 1 本だけ:

- `files` — 本体 4 ファイルの sha256（キーは `<ファイル名>_sha256`。secret scan の digest 行規則に合わせた形）。ローカルの集合が変われば一致しなくなる
- `manifest` — 本体の manifest そのもの（identity / axioms / prompt の sha、seed、strata、window）。`home` だけ `~` に置き換えた
- `summary` — `relevance_label_set.py score` の集計（AUC P(top) 0.941、t ごとの precision / recall、`recorded_cuts`、`live_cut`、
  `recorded_vs_rescored`）

## ratchet の回し方

```bash
cd <main tree>/.notes/labels/relevance/2026-09-28 && shasum -a 256 rows.jsonl labels.jsonl manifest.json summary.json
# → label-set-2026-09-28.json の files と一致すること
uv run --no-sync python scripts/relevance_label_set.py check --dir .notes/labels/relevance/2026-09-28
uv run --no-sync python scripts/relevance_label_set.py score --dir .notes/labels/relevance/2026-09-28 \
    --baseline .notes/labels/relevance/2026-09-28/summary.json \
    --out .notes/labels/relevance/ratchet-<YYYY-MM-DD>.json
```

本体が書き込み不可なので `--out` は集合の外（`.notes/` の中）に向ける。

`score --baseline` の退行線は AUC P(top) で **0.03**（run 間の noise floor が 0.02 を含んだため、RFC-0046 Next action 1）。
exit 2（比較不能）は pin のどれかが動いた印 — identity の adopt で失効する（再ラベルか ack、ADR-0113 Review-when）。

この集合は live score の帯で層化した最後の集合（manifest に `strata_key` が無い）。後始末 2 以降の `sample` は
記録された P(top) の帯で層化する（`strata_key: decision_p_top`）ので、新しい集合と比べるときは重み付けの読み
（`cuts_weighted`）を使う。
