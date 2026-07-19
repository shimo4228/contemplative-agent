# ADR-0080: North Star — 層別の最終状態定義（能力目標にしない）

## Status

accepted

## Date

2026-07-20

## Context

これは `docs/adr/README.md` の「ADR の種別」でいう **worldview ADR** である:
機構ではなく立場を記録する。

これまでプロジェクトには、望ましい最終状態の明示的な定義がなかった。
「X を作るべきか」の判断は、照らし合わせる固定の基準点なしに都度議論されてきた。
今後の作業から品質ベンチマークが派生してくることは予想されるが、先行する定義が
ないままでは、最適化対象として唯一具体的に存在するそれらのベンチマークが、
なし崩しに事実上の目標になってしまう。

能力目標として表現した north star —「より高性能で、より自律的なエージェント」—
も検討したが、framing として棄却した。2 つの既存コミットメントと矛盾するためである:

1. Contemplative 公理の Emptiness 条項: 目標は軽く保持し、単一の目標を最終の
   ものとして固定化しない（ADR-0002）。
2. Observation-over-steering の方針: オーナーは目標とする人格や行動を学習
   ループに注入しない（ADR-0050 / ADR-0051 / ADR-0052）。

最も近い先行言明は ADR-0017 の「プロジェクトの目標は transformation であって
elimination ではない」だが、これはシステムと困難の関わり方についての哲学的
フレームであり、「完成」が何を指すかの定義ではない。

本 ADR は 2026-07-20 のオーナーとアシスタントの作業会話で決定された。

## Decision

望ましい最終状態を、能力目標ではなく**層別の完成条件**として定義する。
エージェントが何に*なる*かは意図的に未定義のままにする。定義できるのは、
実験装置がいつ完成したと言えるか、である。

1. **機構層（コード）** — 完成とはこの層が*動かなくなる*こと。変更は修理のみに
   なり、機構層の ADR はゼロに近づく。メタファー: 望遠鏡の改良をやめ、それで
   観測する。計器 / 監査ログ / chaos-TDD の系譜（ADR-0071 / ADR-0075 /
   ADR-0077）は、すでに「触らなくてよいほど信頼できる」への動きである。
2. **価値層（identity / constitution / skills / rules）** — 完成は到達点では
   *ない*。望ましい状態とは legible な進化が続いていること: 価値層のすべての
   変化が記録から追跡でき、オフラインで説明できる。この層に目標状態を定義する
   ことは observation-over-steering により禁じられている。
3. **研究層** — 完成とは、建立時の問い（contemplative constitution は小型
   ローカルモデルの行動を形づくるか。蒸留は複利的に働くか。identity は安定
   するか）に — 肯定・否定いずれであれ — 答えが出て、論文・エッセイに結晶し、
   machine-reference 圏に拡散されること。他者と LLM による派生が成功基準である
   （AI 時代のオーセンティシティ反転: scarcity より diffusion）。
4. **セキュリティ層** — 完成とは absence が維持されること。外部アダプタは
   1 つ（ADR-0015）、権限は増やさない（ADR-0007）。この層は*変わらないこと*で
   成功する。
5. **終わり方の設計** — 設計された終了は最終状態の一部である: read-only 計器が
   代謝の定常状態を示し、残る問いが別の実験（例: framework/worldview 分離の
   ための 2 体目のエージェント）を要求するようになったとき、6 時間ごとの
   heartbeat を止める。最終成果物は縦断記録 — データセット
   （`contemplative-agent-data`）と論文 — であって、エージェントインスタンス
   そのものではない。

一文で言えば: 望ましい最終状態とは、完成した観測装置の上で価値層だけが動き
続けている状態であり、durable artifact は走者ではなく走行の記録である。

**ベンチマーク非還元条項。** この定義から層別のゲートとして品質ベンチマークが
派生することは十分ありうるが、定義そのものは、いかなるベンチマークスイートにも
置き換えられない価値層の言明として固定する。ベンチマークは個々の層に仕える。
この定義の代替には決してならない（Goodhart ガード）。

## Alternatives Considered

### 能力目標型の north star

「より賢く、より自律的なエージェント」を目標として掲げる。棄却: Emptiness 条項
および observation-over-steering と矛盾する。能力の成長はこのプロジェクトの
眼目ではない — 小型ローカルモデルで堅牢に動くこと自体が達成である。

### 定義しない（現状維持）

最終状態を未定義のまま、目的を都度議論し続ける。棄却: 改善判断のたびに目的を
ゼロから再審理することになり、派生してくるベンチマークが空白を埋めて、なし崩し
に目標になる。

### ベンチマークスイートを定義とする

品質メトリクスの集合に north star を代行させる。オーナーが明示的に棄却:
価値層のメトリクスへの還元であり、Goodhart リスクがある。

## Consequences

### Positive

- 今後の「X を作るべきか」の提案が固定の基準を得る: 機構層の提案は「収束する
  はずの装置の修理か、それとも改良か」で審査され、価値層への介入は「どこかへ
  誘導するか」ではなく「進化を legible に保つか」で審査される。
- `docs/CYCLES.md` に本 ADR を指す短い North-star セクションが追加される
  （正本は本 ADR。複製しない）。

### Negative

- リスク: 「機構層が動かなくなる」は修理の凍結と誤読されうる — 修理・観測性・
  セキュリティ修正は完全にスコープ内に残る。終わるのは能力動機の機構拡大である。
- この定義は意図的に機械検証不能である。ドリフトは lint ゲートではなく週次の
  内省・診断サイクルで見張る。

### Neutral / Follow-ups

- 終了条件の具体化（heartbeat を正確にいつ止めるか）は将来の決定として予約し、
  タスク台帳（T-ENDSTATE-TERM）で追跡する。計器が代謝の定常状態を示したことを
  トリガーとする。

## References

- [ADR-0002](./0002-paper-faithful-ccai.md) — Emptiness 条項の根拠
- [ADR-0017](./0017-yogacara-eight-consciousness-frame.md) — 最近接の先行
  目的言明（worldview の先例）
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)、
  [ADR-0051](./0051-retire-trust-weighting.md)、
  [ADR-0052](./0052-retire-session-insight.md) — 価値層条項が依存する
  observation-over-steering の系譜
- [ADR-0071](./0071-read-only-pattern-composition-instruments.md)、
  [ADR-0075](./0075-observability-by-default.md)、
  [ADR-0077](./0077-chaos-tdd-fault-injection.md) — 第 1 層で引いた機構層の
  成熟トレンド
- [ADR-0015](./0015-one-external-adapter-per-agent.md)、
  [ADR-0007](./0007-security-boundary-model.md) — セキュリティ層の absence 定義
- `docs/CYCLES.md` — この定義が方向づける駆動サイクルマップ
- Sibling repo
  [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data)
  — 第 5 層で名指しした縦断記録の器
