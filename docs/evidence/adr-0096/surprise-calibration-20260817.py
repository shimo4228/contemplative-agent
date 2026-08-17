#!/usr/bin/env python3
"""T-INSIGHT-WORTH 較正: surprise の識別力を 07-25 の 78 候補で測る。

LLM 呼び出しゼロ・本番非配線・read-only。

ラベル:  `logs/audit.jsonl` の `source="stage-adopted"` / `ts` が 2026-07-25 の
         78 行（approved 5 / rejected 73）。同 audit 行が `source_ids`
         （クラスタ構成 pattern の content-hash id、`knowledge_store.pattern_id`）
         を持つので、候補ごとにクラスタ centroid を復元できる。
埋め込み: `knowledge.json` の各行の `embedding`（nomic-embed-text, 768d）。

surprise の定義（2 種を並べる。閾値は持たせない — 計器であってゲートではない）:
  s_nn   = 1 - max_j cos(centroid_i, ref_j)      「直近 k 件の最近傍からの距離」
  s_mean = 1 - mean_j cos(centroid_i, ref_j)     「直近 k 件の分布中心からの距離」
参照集合 ref = run 時刻より前に distill された直近 k 件。**候補自身の source_ids は
除外する**（自分の材料が ref に居ると max cos が 1.0 に張り付く）。

Z 正規化の罠の検査: 生の cos 分布（NN 天井 ~0.80 で潰れているか）と、Z 正規化後の
分布を必ず並べて出す。Z は入力が潰れていても常にきれいな広がりを作る。
"""

import hashlib
import json
import os
import sys
from collections import Counter

import numpy as np

HOME = os.environ.get("MOLTBOOK_HOME", os.path.expanduser("~/.config/moltbook"))
KNOWLEDGE = os.path.join(HOME, "knowledge.json")
AUDIT = os.path.join(HOME, "logs", "audit.jsonl")
RUN_DAY = "2026-07-25"
K_VALUES = (100, 300, 1000)


def pattern_id(distilled: str, text: str) -> str:
    return hashlib.sha256(f"{distilled}|{text}".encode()).hexdigest()[:12]


def load_labels():
    rows = []
    with open(AUDIT, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("source") == "stage-adopted" and d.get("ts", "")[:10] == RUN_DAY:
                rows.append(
                    {
                        "name": d["path"].rsplit("/", 1)[-1].replace(".md", ""),
                        "approved": d["decision"] == "approved",
                        "source_ids": tuple(d.get("source_ids") or ()),
                        "ts": d["ts"],
                    }
                )
    return rows


def load_patterns():
    with open(KNOWLEDGE, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for p in raw:
        emb = p.get("embedding")
        if not emb:
            continue
        out.append((pattern_id(p.get("distilled", ""), p.get("pattern", "")),
                    p.get("distilled", ""), np.asarray(emb, dtype=np.float32)))
    return out


def unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def main() -> int:
    labels = load_labels()
    print(f"labeled candidates: {len(labels)} "
          f"(approved {sum(l['approved'] for l in labels)})")

    pats = load_patterns()
    print(f"patterns with embeddings: {len(pats)}")
    by_id = {pid: (ts, vec) for pid, ts, vec in pats}
    print(f"unique ids: {len(by_id)}")

    # クラスタ centroid の復元可能性
    cov = Counter()
    cands = []
    for lab in labels:
        vecs = [by_id[i][1] for i in lab["source_ids"] if i in by_id]
        cov[f"{len(vecs)}/{len(lab['source_ids'])}"] += 1
        if not vecs:
            continue
        c = unit(np.mean(unit(np.stack(vecs)), axis=0))
        cands.append({**lab, "centroid": c, "n_found": len(vecs)})
    print(f"source_id coverage (found/total): {dict(cov)}")
    print(f"candidates with a recoverable centroid: {len(cands)}")

    run_ts = min(c["ts"] for c in cands)
    # 参照候補: run より前に distill された行を新しい順に
    hist = sorted(((ts, pid, v) for pid, ts, v in pats if ts and ts < run_ts),
                  key=lambda r: r[0], reverse=True)
    print(f"history before {run_ts}: {len(hist)} patterns "
          f"(newest {hist[0][0]}, oldest {hist[-1][0]})")

    for k in K_VALUES:
        ref = hist[:k]
        ref_ids = [pid for _, pid, _ in ref]
        ref_mat = unit(np.stack([v for _, _, v in ref]))
        print(f"\n{'='*72}\nk = {k}  (ref window {ref[-1][0][:10]} .. {ref[0][0][:10]})")

        rows = []
        for c in cands:
            own = set(c["source_ids"])
            mask = np.array([pid not in own for pid in ref_ids])
            m = ref_mat[mask]
            cos = m @ c["centroid"]
            rows.append({
                "name": c["name"], "approved": c["approved"],
                "excluded": int((~mask).sum()),
                "max_cos": float(cos.max()), "mean_cos": float(cos.mean()),
                "s_nn": 1 - float(cos.max()), "s_mean": 1 - float(cos.mean()),
            })

        mx = np.array([r["max_cos"] for r in rows])
        mn = np.array([r["mean_cos"] for r in rows])
        print(f"  self-exclusions per candidate: "
              f"min={min(r['excluded'] for r in rows)} max={max(r['excluded'] for r in rows)}")
        print("  --- RAW distribution (Z 正規化の罠の検査対象) ---")
        for nm, arr in (("max_cos (NN)", mx), ("mean_cos", mn)):
            print(f"    {nm:14s} min={arr.min():.4f} p10={np.percentile(arr,10):.4f} "
                  f"p50={np.percentile(arr,50):.4f} p90={np.percentile(arr,90):.4f} "
                  f"max={arr.max():.4f}  spread={arr.max()-arr.min():.4f}  sd={arr.std():.4f}")

        for key, label in (("s_nn", "s_nn = 1 - max cos"), ("s_mean", "s_mean = 1 - mean cos")):
            ordered = sorted(rows, key=lambda r: -r[key])
            for i, r in enumerate(ordered, 1):
                r[f"rank_{key}"] = i
            adopted = [(r[f"rank_{key}"], r["name"], r[key]) for r in ordered if r["approved"]]
            n = len(ordered)
            ranks = [a[0] for a in adopted]
            # AUC = P(ランダムな採用 1 件がランダムな却下 1 件より上位)。0.5 = 無情報。
            pos = np.array([r[key] for r in ordered if r["approved"]])
            neg = np.array([r[key] for r in ordered if not r["approved"]])
            auc = float(((pos[:, None] > neg[None, :]).sum()
                         + 0.5 * (pos[:, None] == neg[None, :]).sum())
                        / (pos.size * neg.size))
            # 順列検定（n=5 なので効果量より不確かさの表示が主目的）
            rng = np.random.default_rng(0)
            allv = np.concatenate([pos, neg])
            null = np.array([
                (lambda s: ((s[:5, None] > s[5:][None, :]).sum()
                            + 0.5 * (s[:5, None] == s[5:][None, :]).sum()) / (5 * (n - 5)))(
                    rng.permutation(allv))
                for _ in range(20000)
            ])
            pval = float((null >= auc).mean())
            print(f"\n  --- {label} ---")
            print(f"    adopted ranks (of {n}): {ranks}   "
                  f"median={np.median(ranks):.1f}  "
                  f"(random expectation median ≈ {(n+1)/2:.1f})")
            print(f"    AUC={auc:.3f} (0.5 = 無情報)  permutation p(one-sided)={pval:.3f}  n_pos=5")
            for rk, nm, val in adopted:
                print(f"      #{rk:2d}  {val:+.4f}  {nm}")
            print(f"    top 10 by {key}:")
            for r in ordered[:10]:
                mark = "★ADOPTED" if r["approved"] else "        "
                print(f"      #{r[f'rank_{key}']:2d} {mark} {r[key]:+.4f}  {r['name']}")

        # Z 正規化: 入力が潰れていても常にきれいな広がりを作るかの実演
        z = (mx - mx.mean()) / mx.std()
        print("\n  --- Z 正規化後（max_cos ベース） ---")
        print(f"    z: min={z.min():.2f} p10={np.percentile(z,10):.2f} "
              f"p50={np.percentile(z,50):.2f} p90={np.percentile(z,90):.2f} max={z.max():.2f}")
        print(f"    raw spread {mx.max()-mx.min():.4f} cos → z spread {z.max()-z.min():.2f} sd")

    return 0


if __name__ == "__main__":
    sys.exit(main())
