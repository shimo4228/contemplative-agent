---
state: accepted 2026-09-12
review-when: セッションループが固定長（`duration_minutes`）でなくなったら、この待ち処理ごと消えるので本提案は無効になる
---

## Summary

セッション終了時刻の直前、`_wait_for_next_cycle` が待たずに戻り、ループが毎秒 `GET /home` を叩いて空転する。

## Motivation

2026-09-05〜09-11 の `api-audit.jsonl` を `GET /home`（サイクル開始）で切ると、セッション
`a6eac8ae`（09-07 15:00→16:00 UTC）は 23 回のうち末尾 12 回が 15:59:09〜15:59:20 に
0〜1 秒間隔で並ぶ。全部 200、`rate_remaining` は 29 のまま。他のセッションにも同じ尾がある
（30 秒以上離れた呼び出しだけ数えると 28 セッションの最大は 14 サイクル、生カウントでは 23）。

正常な呼び出しの反復なので、WARNING も不変条件違反も出ず、週次の 7 intake のどれにも
掛からない。ADR-0107 の Phase 0 が拾うべき形の実例で、記事執筆中の手集計で見つかった。

実害は小さい（GET 予算を数十回消費するだけ）が、`api-audit.jsonl` の `/home` 件数と
サイクル数の対応を壊すので、テレメトリの読み手（ADR-0107 の census / Phase 0）にとっては
ノイズになる。

## Reference-level explanation

`src/contemplative_agent/adapters/moltbook/agent.py` `_wait_for_next_cycle`:

```python
wait = min(wait, max(0.0, end_time - time.time()))
if wait > 0 and time.time() + wait < end_time and not self._shutdown_requested:
    time.sleep(wait)
```

残り時間が本来の待ち（60 秒以上）より短いとき、`wait` は残り時間に切り詰められ、直後の
`time.time() + wait < end_time` が（等号で）成立せず sleep が飛ぶ。ループ条件
`while time.time() < end_time` はまだ真なので、`_run_session_cycle` が即座に再実行され、
`home_refresh` の GET だけを残り時間いっぱい毎秒繰り返す。

修理の候補は 2 つで、どちらも小さい。

- 残り時間が本来の待ちより短いなら、待たずに**ループを抜ける**（次サイクルを回す時間が無い）
- または残り時間ぶん sleep してから抜ける

いずれも回帰テストは「`end_time` まで残り 5 秒・待ち 60 秒のとき、`_run_session_cycle` が
再実行されない」の 1 本で足りる。`tests/` の agent セッションループのテストに足す。

## Drawbacks

無し。終了間際の空転は成果を生んでいない。

## Status

accepted 2026-09-12 — 著者指示で起票し、build セッションへ dispatch。

## Next action

build セッションが `_wait_for_next_cycle` を直し、回帰テスト 1 本を足して commit する。
