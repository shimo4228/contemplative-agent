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

## 較正（ECE）の初回の読み（2026-10-31、P1-15.4）

[ece-recorded-p-top-20261031.json](ece-recorded-p-top-20261031.json): 同じ 150 行で、本番が記録した `decision_p_top` の 5 帯の
信頼度と ECE（0.082、母集団重み付き 0.085）。`calibration()` を本体の行と Jev のラベルにそのまま当てた値で、モデルは呼んでいない。
`score` の再採点（Ollama logprobs）での ECE ではない。0.2〜0.4 帯の 17 行は on-topic 0、0.4〜0.6 帯の 10 行は 0.7 で、
帯をまたいで単調でない（各帯の行数が少ない）。

## 3 回目の読み（2026-10-24 事前登録）

enforce 後の母集団・post 単位での t=0.3 の再読は [preregistration-third-reading.md](preregistration-third-reading.md) に読みの前に固定した
（規則・下限・検出力・実行手順）。結果は読みの後に同じディレクトリへ追記する。`relevance_label_set.py check --latest` は
`.claude/verify.sh` full mode の advisory として回る（label set の pin が現在の tree とずれたら warn）。
