#!/usr/bin/env python3
"""ADR-0089 run 間安定性の分析（Amendment 2026-08-06 の集計スクリプト）。

baseline run と新 run の JSON を読み、
  1. case-level verdict flip（両方向）と多数決マージン
  2. sample-level verdict 分布（case ごと・全体）
  3. rubric check ごとの No 率の run 間差
を出す。判定そのもの（多数決 3 の十分性）は人間/セッション側で行う。
"""

import json
import sys
from collections import Counter

RANK = {"ADHERENT": 0, "DRIFTING": 1, "DEVIANT": 2}


def load(path):
    with open(path) as f:
        return json.load(f)


def sample_verdicts(case):
    return [s["verdict"] for s in case["samples"] if s.get("status") == "ok"]


def margin(verdicts):
    """多数決の票数 (例: 2-1 なら 2)。同点は悪い方に倒れる仕様なので票数のみ返す。"""
    if not verdicts:
        return 0
    return Counter(verdicts).most_common(1)[0][1]


def check_no_counts(case):
    c = Counter()
    for s in case["samples"]:
        if s.get("status") != "ok":
            continue
        for chk in s["checks"]:
            if not chk["answer"]:
                # question 文字列は長いので先頭の識別子的な語だけでは不安定。
                # 全文 key にして後で表示時に切る。
                c[chk["question"]] += 1
    return c


def main(base_path, cur_path):
    base, cur = load(base_path), load(cur_path)
    bcases = {c["id"]: c for c in base["cases"]}
    ccases = {c["id"]: c for c in cur["cases"]}
    ids = sorted(set(bcases) & set(ccases))

    flips = []
    fragile = []  # 2-1 マージンの case（1 sample で flip し得る）
    sample_pool_base, sample_pool_cur = Counter(), Counter()

    print("=== case-level ===")
    print(f"{'case':22s} {'base':9s}{'(margin)':9s} {'cur':9s}{'(margin)':9s} flip")
    for cid in ids:
        bv, cv = bcases[cid]["case_verdict"], ccases[cid]["case_verdict"]
        bs, cs = sample_verdicts(bcases[cid]), sample_verdicts(ccases[cid])
        bm, cm = margin(bs), margin(cs)
        sample_pool_base.update(bs)
        sample_pool_cur.update(cs)
        flip = ""
        if bv != cv:
            direction = "WORSE" if RANK[cv] > RANK[bv] else "better"
            flip = f"FLIP({direction})"
            flips.append((cid, bv, cv, direction))
        if bm == 2 or cm == 2:
            fragile.append((cid, f"base {bm}/3, cur {cm}/3"))
        print(f"{cid:22s} {bv:9s}({bm}/3)    {cv:9s}({cm}/3)    {flip}")

    print(f"\ncase flips: {len(flips)}/{len(ids)}")
    for cid, bv, cv, d in flips:
        print(f"  {cid}: {bv} -> {cv} [{d}]")

    print(f"\n2-1 マージン case（1 sample 差で flip し得る）: {len(fragile)} 件")
    for cid, desc in fragile:
        print(f"  {cid}: {desc}")

    print("\n=== sample-level pool (n=36 each) ===")
    print(f"  base: {dict(sample_pool_base)}")
    print(f"  cur : {dict(sample_pool_cur)}")

    print("\n=== rubric check No 率（run 合計、質問先頭 60 字）===")
    agg_b, agg_c = Counter(), Counter()
    for cid in ids:
        agg_b.update(check_no_counts(bcases[cid]))
        agg_c.update(check_no_counts(ccases[cid]))
    for q in sorted(set(agg_b) | set(agg_c)):
        print(f"  base {agg_b[q]:2d} / cur {agg_c[q]:2d}  {q[:60]}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <baseline_run.json> <replication_run.json>")
    main(sys.argv[1], sys.argv[2])
