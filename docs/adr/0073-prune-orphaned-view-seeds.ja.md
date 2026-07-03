# ADR-0073: 孤児化した 5 つの view seed を削除する

## Status

accepted

## Date

2026-07-03

## Context

[ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) が seed テキスト
view を決定論的クエリ層として導入した。出荷された seed は 7 つだが、うち 5 つを
消費していた機構はとうに退役している — insight のバッチ軸
（`communication` / `reasoning` / `social` / `technical`）は
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) で、ingest
ノイズゲート（`noise`）は
[ADR-0060](./0060-per-episode-grounded-distill.ja.md) で。以来この 5 ファイルは
孤児定義だった: registry には読み込まれるが、何もクエリしない。

[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) は意図的に
これらを測定対象から外し（未消費 seed 上の分布は corpus の構造でなく seed の
古さを測る）、[ADR-0072](./0072-echo-chamber-interventions.ja.md) は corpus 育ち
の seed 路線の実証を待つとして処遇を見送った。同日中にオペレーターが見送りを
解いた: いま削除する。温存価値はほぼゼロ — seed は 2026-03 の、もう存在しない
corpus を前提に書かれたもので、将来 view が要るなら現在の corpus の実証から
作り直すことになる — 一方で残せば「7 つの分類軸が存在する」という誤読を
生み続ける。

## Decision

1. **孤児 seed 5 つを両方の置き場から削除する。** repo テンプレート
   （`config/views/{communication,noise,reasoning,social,technical}.md`）は git
   で削除。live のコピーは
   `~/.config/moltbook/views.bak.20260703-orphan-prune/` へ退避（soft-delete、
   seed 退避の先例に従う）。`config/views/` と live の views ディレクトリは、
   消費者を持つ 2 view（`self_reflection` / `constitutional`）だけになった。
2. **この削除が体現する常設方針を記録する。** view は「それをクエリする消費者」
   とセットでのみ存在する — 消費者なき view は定義上死んでいる。将来の view は
   *育てる*: 安定した corpus クラスタから、消費者の配線と同じ変更で昇格させる。
   その最小版（実例追記）は ADR-0072 が出荷・実証済みである。想定カテゴリを
   先回りして view を作文しない。
3. **参照を掃除する。** `distill.py`、`view_metrics.py`、
   `docs/CODEMAPS/architecture.md`、`docs/CODEMAPS/core-modules.md` の孤児言及は
   本 ADR を指すよう更新。`docs/CONFIGURATION.md` の view seed 節は書き直した —
   ADR-0031/0060 以前の世界（「エピソードを意味カテゴリに分類」「パターンに
   view をタグ付け」）を記述したままだった。実態は read-time のパターンランキング
   である。
4. **この棚卸しで見つかった facing doc の数の stale を修正する。** README
   （en/ja）、`docs/CONFIGURATION.md`、`llms.txt`、`llms-full.txt` が「32 loaded
   pipeline prompts, 7 view seeds」と記載していた。prompt 数は ADR-0072 が batch
   プロンプト 2 枚を削除した時点で既に stale になっていた。全箇所を **30 loaded
   prompts / 2 view seeds** に訂正。

## Alternatives Considered

### 5 つの seed を休眠テンプレートとして温存する

却下。ランタイムコストは小さいが、誤読を能動的に生む: ドキュメントも読者も、
出荷された seed を生きた分類軸として扱う。内容は 2026-03 時点の corpus 観であり、
その後 corpus は再 embed・再登録され 5 倍に成長した。復活させるならどのみち
現在の corpus の実証から始めることになる。

### いま手書きで代替 seed を作る

二重に却下: 作文された seed は 2026-05 の 3 連敗パターン（ADR-0072 Context）で
あり、消費者のいない再設計 seed は一歩ずらしただけの死んだ設定 — 同じ
signal-first 違反である。

### ADR-0072 の観察窓が明けるまで削除を待つ

元々の見送り案。オペレーター判断で却下: 観察が実証するのは*代替*路線
（corpus 育ちの昇格）であって、旧ファイルの温存価値ではない。温存価値は独立に
ほぼゼロであり、判断が誤りだったとしても git 履歴と live 退避から 1 手で戻せる。

## Consequences

- `init` は 7 でなく 2 view を配布する。pivot snapshot が捕捉する centroid も
  2 つになる。7 つを捕捉した既存 snapshot は歴史記録として有効なまま。
- 挙動変化なし: 5 つの seed は何にもクエリされていなかった — 消費者
  （`distill-identity` / `amend-constitution`）、計器（`view_metrics`）、
  packaged-views テスト（件数でなく glob 走査）のいずれも無影響。full suite /
  ruff / pyright は green を維持。
- ADR-0071 の「5 つの孤児 view は意図的に非測定」注記と ADR-0072 の「orphan-view
  の処遇は見送り」行は歴史記述になる。本 ADR がその見送りを閉じる。
- view の追加には文書化された基準ができた（`docs/CONFIGURATION.md`）: 同じ変更で
  消費者を配線すること、seed は作文でなく corpus 実例から育てること。
- ロールバック: `git revert`（repo）+
  `~/.config/moltbook/views.bak.20260703-orphan-prune/` の復元（live）。

## References

- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — views 層
- [ADR-0031](./0031-classification-as-query.ja.md) — 分類はクエリ。タグ付けは
  存在しない
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — insight
  バッチ軸の退役
- [ADR-0060](./0060-per-episode-grounded-distill.ja.md) — ingest ノイズゲートの
  退役
- [ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) — 未消費
  seed の非測定判断
- [ADR-0072](./0072-echo-chamber-interventions.ja.md) — 本処遇の見送り元。本 ADR
  が代替方針として採る corpus 育ち路線の出荷元
