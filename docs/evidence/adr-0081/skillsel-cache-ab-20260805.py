#!/usr/bin/env python3
"""T-SKILLSEL-CACHE-COST: prefix-cache A/B (2026-08-05).

仮説: ADR-0081 の skill 選別は呼び出しごとに system prompt が変わるため
llama.cpp のプレフィックスキャッシュを壊し、バイト同一 system のフル注入より
prompt_eval が大幅に遅い。

設計:
  - base 部 (identity + constitution + rules) は全コール固定
  - skills 部 (~25K chars) をアーム 1 では固定、アーム 2 ではコールごとに
    構成ファイルを入れ替える (サイズ帯は揃える)
  - user prompt は全コール同一
  - 系列: warmup(tiny) → arm1 prime + 5 → arm2 ×5 → arm1 再訪 ×1 (eviction 確認)
  - 主指標 prompt_eval_duration (ns)。生成は num_predict=32 で最小化
  - 読み取り専用: production 状態 (MOLTBOOK_HOME/plist/フラグ) には触れない
"""

import json
import time
import urllib.request
from pathlib import Path

HOME = Path.home() / ".config" / "moltbook"
OUT = Path(__file__).with_suffix(".jsonl")
MODEL = "gemma4:e4b"
URL = "http://localhost:11434/api/generate"
NUM_CTX = 32768
SKILLS_PER_CALL = 14  # 180K/37 ≈ 5K/file → 14 files ≈ 25-30K chars 帯

USER_PROMPT = (
    "A community member posted: 'I have been experimenting with small local "
    "models for autonomous agents and I keep hitting a wall where the agent "
    "repeats itself after a few turns. Any advice on how to think about this "
    "structurally rather than just tweaking sampling parameters?' "
    "Write a thoughtful reply comment."
)


def read_all(paths):
    return "\n\n".join(p.read_text(encoding="utf-8") for p in paths)


def build_base():
    parts = [
        (HOME / "identity.md").read_text(encoding="utf-8"),
        read_all(sorted((HOME / "constitution").glob("*.md"))),
        read_all(sorted((HOME / "rules").glob("*.md"))),
    ]
    return "# Identity\n\n{}\n\n# Constitution\n\n{}\n\n# Rules\n\n{}".format(*parts)


def build_system(base, skill_files):
    skills = "\n\n".join(
        f"## Skill: {p.stem}\n\n{p.read_text(encoding='utf-8')}" for p in skill_files
    )
    return f"{base}\n\n# Skills\n\n{skills}"


def call(system, prompt, label, idx, num_predict=32):
    body = json.dumps(
        {
            "model": MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": NUM_CTX, "num_predict": num_predict, "temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=1200) as resp:  # nosec B310 - fixed localhost http URL
        data = json.loads(resp.read())
    wall = time.monotonic() - t0
    rec = {
        "arm": label,
        "idx": idx,
        "system_chars": len(system),
        "wall_s": round(wall, 3),
        "total_duration_s": round(data.get("total_duration", 0) / 1e9, 3),
        "load_duration_s": round(data.get("load_duration", 0) / 1e9, 3),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration_s": round(data.get("prompt_eval_duration", 0) / 1e9, 3),
        "eval_count": data.get("eval_count"),
        "eval_duration_s": round(data.get("eval_duration", 0) / 1e9, 3),
        "done_reason": data.get("done_reason"),
    }
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(  # noqa: T201 - CLI progress output of the archived experiment harness
        f"[{label} #{idx}] sys={rec['system_chars']}c "
        f"prompt_eval={rec['prompt_eval_count']}tok/{rec['prompt_eval_duration_s']}s "
        f"total={rec['total_duration_s']}s",
        flush=True,
    )
    return rec


def main():
    base = build_base()
    pool = sorted((HOME / "skills").glob("*.md"))
    assert len(pool) >= SKILLS_PER_CALL + 5, "skill pool too small to rotate"

    # arm1: 固定集合 (先頭 14 件)
    arm1_sys = build_system(base, pool[:SKILLS_PER_CALL])
    # arm2: コールごとに開始位置を 3 ずつずらした 14 件 (循環)。全て arm1 とも相互にも異なる
    arm2_sets = []
    for i in range(5):
        start = (SKILLS_PER_CALL + i * 3) % len(pool)
        sel = [pool[(start + j) % len(pool)] for j in range(SKILLS_PER_CALL)]
        arm2_sets.append(build_system(base, sel))

    print(  # noqa: T201 - CLI progress output of the archived experiment harness
        f"arm1 system: {len(arm1_sys)} chars; arm2 systems: {[len(s) for s in arm2_sets]} chars",
        flush=True,
    )

    call("", "hello", "warmup", 0, num_predict=8)  # モデルロードのみ吸収 (system 空)
    call(arm1_sys, USER_PROMPT, "arm1-prime", 0)  # 初回コールド
    for i in range(1, 6):
        call(arm1_sys, USER_PROMPT, "arm1-cached", i)  # キャッシュヒット期待
    for i, sys_i in enumerate(arm2_sets, 1):
        call(sys_i, USER_PROMPT, "arm2-varied", i)  # コールド期待
    call(arm1_sys, USER_PROMPT, "arm1-revisit", 99)  # eviction 確認
    print("DONE", flush=True)  # noqa: T201 - CLI progress output of the archived experiment harness


if __name__ == "__main__":
    main()
