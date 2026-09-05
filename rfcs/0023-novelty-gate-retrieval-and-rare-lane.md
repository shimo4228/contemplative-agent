---
state: accepted 2026-09-05
state_since: 2026-09-04
review-when: 候補検索の recall@10 が reviewer の名指しに対して 0.8 を下回る読みが 2 回続く（検索が reviewer の判断を再現しない — 判定を LLM に戻す）、または RFC-0015 の selector 幻覚率が catalog サイズと無相関だと分かる（重複を減らす動機の半分が消える）
---

## Summary

insight の novelty gate を「既知テーマ全部を LLM に読ませる」から「既存 skill 群への候補検索（BM25 + nomic の hybrid）で top-k に絞ってから LLM が判定する」に置き換え、検索が遠いと読む singleton を保留台帳に溜めて希少 skill の抽出経路を作る。

## Motivation

skill store（57 本、2026-09-04）には 2 つの症状がある。

1. **同型 skill の量産。** 名前だけ並べても boundary 族 7 本（`boundary-assumption-verification` /
   `identifying-simulation-boundaries` / `identifying-systemic-boundary-stressors` /
   `mapping-epistemic-boundaries` / `pinpointing-systemic-boundary-conditions` / `scope-boundary-mapping` /
   `recognizing-boundary-declarations-in-content-flow`）、`deconstructing-*` 4 本、`detecting-*` 4 本。
   現行の gate（`core/insight_novelty.py`、ADR-0074 D6）は既知テーマ 442 本 + クラスタ標本 3 件を 1 プロンプトに
   詰めて gemma に被りを判定させる。40k 超過で fail-open した履歴（2026-07-18）があり、chunk 化後も
   判定は「全部を読んだ上での yes / no」で、実測の covered 率は低い（`logs/insight-novelty.jsonl`）。
2. **希少 skill が抽出されない。** insight は embedding クラスタ（cosine ≥ 0.70、3 行以上）だけを LLM に渡し、
   singleton はログに残して落とす。surprise（RFC-0016、read-only）はその**後**にクラスタへ付く読み値なので、
   希少な行は surprise が見る前に消えている。しかも surprise は「直近 k 行からの距離」で「skill 店からの距離」
   ではない — 2026-08-17 の較正で最も surprise が高い候補が飽和族の出だったのはこのため。

両症状は同じ 1 本の距離の両端になる: 新しい候補（クラスタでも行でも）を**既存 skill 群**に対して引き、
近ければ重複、遠ければ希少。別の計器は要らない。

順序は 2026-09-04 の著者判断: **先に計測、抽出の型（RFC-0024）はその後。**

## Guide-level explanation

- **検索は候補生成、判定は LLM。** ADR-0074 が code 閾値の embedding 抑制を反証済みなので、閾値で捨てない。
  既知テーマ 442 本を全部見せる代わりに、候補検索の top-k（数本）だけを gate プロンプトに載せる。gate の
  プロンプトは小さくなり、fail-open の経路が消える。
- **hybrid の意味。** nomic は語彙の違いを均す。「webhook」「rate limit」のような固有語は BM25 側に残り、
  それが具体性の信号になる。RRF で束ねる（`scripts/retrieval_recall_measure.py` の `union` と同じ形。
  corpus が 57 本なので rrf_k は 60 でなく 5〜10 を読む）。
- **希少レーン。** top-1 が分布の下位にある singleton は捨てず保留台帳（append-only JSONL）に溜め、週次で
  保留同士を再クラスタして床（3 行）を越えたら抽出する。床は下げない（one-run-not-evidence）。
- **surprise は read-only のまま。** 母集団が違う（直近行からの距離）。skill 抽出の軸には使わない。
- BM25 は純 Python で依存追加なし（`scripts/retrieval_recall_measure.py` の `bm25` アームを `core/` に移す）。

## Reference-level explanation

触るもの: `core/insight_novelty.py`（既知テーマの供給を「全部」から「候補検索 top-k」へ）、
`core/insight.py`（singleton の保留経路、`_log_dropped_singletons` の隣）、`config/prompts/insight_novelty*.md`
（k 本だけを見せる文言）、保留台帳 `logs/insight-pending.jsonl`（ADR-0075: 理由コード、b64 不要 — 自己書き込みの
distill 出力）、`core/` に BM25 + RRF の小さな関数（`text_utils` か新 module）。skill 側の embedding は
`name — description` と本文の 2 表現を nomic で（57 本、抽出のたびに再計算してよい規模）。

読み値（入場条件、ADR-0101 の消費計画）: `scripts/retrieval_recall_measure.py`（ADR-0097 D6、2026-09-04 に初実走）と
`scripts/novelty_retrieval_dry_run.py`（今のクラスタと singleton に対する dry-run）。読み手は本 RFC の
設計セッションと土曜ゲート。読みは Status 節。

## Drawbacks

- 検索が reviewer の判断を再現しない部分は LLM 判定に残る。recall が低ければ top-k を広げるだけで、
  ゲートの安さは目減りする
- 保留台帳は新しい状態を 1 つ増やす（週次の再クラスタが消費者。消費者が消えたら台帳ごと撤去）

## Rationale and alternatives

- **既存流用**: 計器は既にあった（`retrieval_recall_measure.py`、書かれてから一度も走っていなかった）。
  `insight_novelty.py` の chunk 化を捨てて top-k にするので code は減る方向
- **wiki（RFC-0017 D4〜D10）**: 中間物にもう 1 段の抽象化を足す形は gemma で平坦化した（RFC-0025）。
  足りないのは抽象化でなく「既存 skill との距離」だった
- **surprise を抽出の軸にする**: 母集団が違うので不採用（上）
- **code 閾値で捨てる**: ADR-0074 で反証済み

## Prior art

ADR-0074 D6（novelty gate）、ADR-0097 D6（retrieval evidence bundle、recall@5 ≥ 0.9 の Review-when）、
RFC-0016（surprise）、RFC-0021（stocktake の family 飽和 — 供給列として本 RFC の検索を再利用）、
vault の LLM wiki（1 source 1 ingest、名寄せは code の正規タグ + LLM は候補の中で判断 — RFC-0017 議論 4）。

## Unresolved questions

- 検索の単位: クラスタ（新設）と行（計数）の両方を持つか。クラスタが既存 skill に寄ったとき、捨てるか
  その skill の provenance に足すか（RFC-0021 の供給列と同じ問い）
- top-k の k と、希少レーンの「下位」の線（dry-run の分布から読む）

## Future possibilities

- RFC-0021 の供給列（各 skill に今も行が届いているか）は同じ検索で出る
- RFC-0024（抽出の型）は本 RFC の読みの後

## 2026-09-05 決定（著者回答: 案 A 採用 + 切り替え前に差分リプレイ）

`draft` → `accepted`。**検索は gate にしない。候補生成のみ。** 判定者（gemma）・出力契約
（`{"covered": [ids]}`）・「迷ったら NEW」の較正・id 検証・chunk 単位の fail-open・人間の承認ゲートは
**すべて不変**。変わるのは `insight_novelty.md` の `{known}` スロットに何を入れるかだけ
（現在は既知テーマ全在庫、切り替え後は検索の top-k）。ADR-0074（code 閾値で捨てない）は
反証されず、むしろ再確認された。

### 採用の根拠（2026-09-04 の 3 読み、いずれも同じ向き）

recall@5 は全アーム 0.61 以下で ADR-0097 の 0.9 線に届かない / 類似度に閾値を置くと
クラスタの 85〜100% が covered に落ちる（LLM 実測 0.186）/ 一般論 skill が hub 化し
top-1 の 25〜28% を 1〜3 本が吸う。**検索単独では判定者になれない。**

### 切り替え前の必須条件 — 差分リプレイ 1 回

**「12 本渡された gemma は 485 本渡された gemma より正しく判定するか」は未測。**
2026-09-04 の計測が答えたのは「検索が正解を見つけられるか」であって、この問いではない。
交換の構造があるため、期待だけで切り替えない:

- **上がる側**: 現行プロンプトは実測 p50 **91 KB ≈ 2.3 万トークン**で、`NUM_CTX = 32768`
  （`core/llm/backend.py:30`、入力と出力が共有）の 7 割を在庫一覧が占める。絞れば
  「干し草から針」から「12 本との見比べ」になり、`budget_overflow` の fail-open も消える
- **下がりうる側**: 照合機会が 485 → 12 に減る。正解が絞り込みから漏れれば gemma が
  どれだけ丁寧に読んでも「新しい」としか答えられない（recall@10 = 0.77 がその実害の目安）

事前登録する読み: (1) 485 本版で covered だったものが top-k 版で落ちる率（網が狭くなった実害）、
(2) top-k 版で新たに covered になる率（注意が上がった効果）。両方を出して交換の収支を見る。

**リプレイの原資は既にある**（新規データ収集不要、課金ゼロ、read-only）:
`logs/insight-novelty.jsonl` は judged 26 コール / 510 クラスタ / 7 run 分を保持し、
`prompt_truncated` / `output_truncated` が**全件 false** — プロンプトと出力が丸ごと残っている
（ADR-0075 の observability が効いた場所）。

### 順序への効果

[RFC-0025](0025-retire-wiki-mechanism.md)（wiki 機構の退役）と
[RFC-0021](0021-skill-stocktake-family-saturation.md) が待っていた「RFC-0023 の決着」は本日成立。
方向（検索は gate にしない）が確定したので、両者の順序ブロックは解ける。

### この決定の次の一手

- 差分リプレイを build-tier へ dispatch（measurement、read-only）。**実装は読みの後**
- 読みが事前登録の 2 点に答えたら、`{known}` の差し替えを別スライスで dispatch

## Status

draft（2026-09-04）。計測 2 本を同日に実走中。読み値は下に追記する。

- `retrieval_recall_measure.py` v1（frontmatter name のみで照合、54 pairs、決定入力可）: recall@5 は
  lexical 0.28 / cosine 0.59 / union(rrf 60) 0.39、recall@10 は cosine 0.83 / union(rrf 10) 0.83
  （`docs/evidence/rfc-0023/retrieval-recall-v1-*.json`）。**ADR-0097 の 0.9 線には届かない。**
  ただし reviewer の名指し 93 件が未解決で、うち 54 件は store の filename stem（`-YYYYMMDD` 付き）
  だった — script が frontmatter name しか引かない読み落とし。v2（filename 解決 + bm25 アーム）で再読
- **v2（同日、filename stem 解決 + `bm25` / `union_bm25` アーム、123 pairs）**
  `docs/evidence/rfc-0023/retrieval-recall-v2-rrf{60,10,5}-20260904.json`:

  | arm | @1 | @3 | @5 | @10 |
  |---|---|---|---|---|
  | lexical（trigram Jaccard） | 0.12 | 0.21 | 0.30 | 0.46 |
  | bm25 | 0.23 | 0.40 | 0.47 | 0.64 |
  | cosine（nomic） | **0.30** | **0.50** | **0.61** | **0.77** |
  | union_bm25（rrf 5） | 0.31 | 0.52 | 0.61 | 0.76 |

  BM25 は lexical の約 2 倍だが cosine 単独に届かず、融合はどの rrf_k でも cosine を上回らない。
  **ADR-0097 の recall@5 ≥ 0.9 には全アームが遠い（最良 0.61）。** reviewer が名指す skill は top-10 に
  77% しか入らない
- **dry-run（同日、live 7,134 行 → 912 クラスタ + 2,796 singleton、57 skill）**
  `docs/evidence/rfc-0023/novelty-retrieval-dry-run-20260904.json`:
  - **類似度に閾値は置けない。** singleton の top-1 分布から p50 / p75 / p90 を閾値に取ると、クラスタの
    85〜100% が「covered」になる（cosine_full: クラスタ p50 0.765 vs singleton p50 0.678 で重なる）。
    LLM gate の実測 covered 率は 0.186（16 records、83/446）。ADR-0074 の反証（code 閾値で捨てない）は
    そのまま立つ
  - **generic skill が hub になる。** top-1 が少数の skill に集中する — cosine_full は
    `dissecting-asserted-agency-into-mechanisms` 89 / `pinpointing-systemic-boundary-conditions` 88 /
    `shifting-focus-from-state-to-process-mechanics` 79（3 本で 912 の 28%）、bm25_full は
    `map-abstract-theory-to-structural-constraints` 1 本で 225（25%）。一般論の skill は何にでも近く、
    検索を gate にすると「一番曖昧な skill に吸われて covered」になる。これは RFC-0024（register）と
    RFC-0021（hub の退役）の材料でもある
  - 希少レーンの母集団: rrf top-1 < singleton p25 で 638 / 2,796。ただし rrf スコアは 2 アームの
    `1/(10+rank)` 和で離散階段（クラスタと singleton の p50 が同値 0.1603）なので、線は cosine_full で
    引き直す

**読み（2026-09-04）: 検索は gate にならないが、候補生成にはなる。** 判定は LLM に残し、既知テーマ 442 本の
代わりに cosine（+ bm25 の補助）top-k（k ≈ 10〜15、recall@10 0.77 を見て）だけを見せる。これで prompt は
40k → 数 k に縮み fail-open の経路が消える。gate の精度は LLM 側のままで、上がる保証は無い（reviewer の
skill が top-k に無い 23% は LLM も見えない）。閾値で捨てる設計・融合で精度を取る設計は本読みで却下。

## Next action

- 著者判断: 上の「候補生成のみ」の縮小設計で `accepted` にするか、recall 0.77 では足りないとして
  `blocked`（照合先: reviewer の名指しが top-k に入る率を上げる手 — skill の description 改善は RFC-0024 /
  hub の退役は RFC-0021 の後に再読）にするか
- accepted 後は build-tier へ dispatch（skill: task-triage）。k は dry-run の分布から packet で決める
