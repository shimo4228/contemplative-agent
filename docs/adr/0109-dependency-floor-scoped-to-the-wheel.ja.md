# ADR-0109: 依存の床は wheel のもので repo のものではない — runtime は requests + numpy のまま、外側は search-first に従う

## Status

accepted

## Date

2026-09-12

## Context

「requests + numpy のみ」は repo 全体で方針として適用されているが、それを決定として
所有する ADR は無く、何に適用されるかを書いた文も無い。事実は `pyproject.toml` の
`[project].dependencies = ["requests>=2.33.0", "numpy>=1.24.0"]`。その事実の記述は
以下（すべて 2026-09-12 に照合）:

- `README.md` 108 行（`README.ja.md` に同文）: 「Security by absence」の項目が
  「moltbook.com と localhost の Ollama にしか話さない」と並べて「runtime 依存は 2 つ
  (requests, numpy)」を公開のセキュリティ主張の一部として掲げる。
  `docs/security/2026-04-01-security-scan.md` 69 行は同じ主張の日付つきスナップショット。
- `CLAUDE.md` 32 行: 素の事実（`依存: requests, numpy`）で、禁止文ではない。
- `src/contemplative_agent/core/llm/prompting.py` 345 行: production の前提として使う
  （「requests+numpy しか出荷しないので本物の tokenizer は無い」）。
- [ADR-0075](0075-observability-by-default.ja.md)（§Alternatives、OpenTelemetry）と
  [ADR-0078](0078-otel-connection-via-vocabulary-and-offline-export.ja.md)（Context、16 行）は
  「意図的に最小の依存フロア（requests + numpy）」を runtime observability フレームワーク
  却下の前提に引く。
- [ADR-0077](0077-chaos-tdd-fault-injection.ja.md)（§Alternatives「ChaosBackend を src/ に置く」）:
  「runtime 依存は requests + numpy のみを維持し、テスト専用コードを production の import
  経路に入れない」。他の 3 案（chaostoolkit / toxiproxy、agent-chaos、requests-mock）は
  dev 層で、依存フットプリントを高度や冗長性と並べて秤にかけている。
- [ADR-0071](0071-read-only-pattern-composition-instruments.ja.md)（§Alternatives「embedding
  drift 監視スタック（evidently、whylogs）の採用」）: 「pandas/scikit-learn の依存
  フットプリントが requests+numpy のみの方針と衝突」を理由に却下。その計器は
  `core/view_metrics.py` で、`distill.py` と `insight.py` が import する — wheel の内側。
- `.claude/verify.md` 158 行（git 追跡下）: `Unpack[TypedDict]` のための `typing_extensions`
  を「新依存（requests+numpy のみ方針に抵触）」で棄却。対象の注釈は
  `adapters/moltbook/client.py` — wheel の内側。
- [ADR-0007](0007-security-boundary-model.ja.md)（§Alternatives「外部 security scanner」）:
  「依存が増える。現在の規模では組み込みのパターン照合で足りる」— 依存を却下理由に
  使った最初の例で、規模の議論と対。
- [ADR-0011](0011-knowledge-injection-to-skills.ja.md) 92 行の「Minimal Dependency 原則」は
  無関係の意味: orchestrator が Claude Code に縛られない（「CLI を叩けるものなら何でも
  よい」）。同じ語で別の主張。

記録にある拒否権としての適用はすべて wheel のコードに対するもので、そこでは規則は健全である。無いのは
スコープの文だ。規則が wheel 境界で止まるとはどこにも書いていないので、ADR-0071 や
`verify.md` の「requests+numpy のみの方針」を読んだ agent は repo 全体の規則として読む。
2026-09-12、その読みが `scripts/` 配下の計器 script の groupby / pivot 集計を
stdlib + sqlite3 で手書きしかける草稿を生んだ。著者が訂正した: pandas や scipy のような
基礎ライブラリは入れてよい、避けると再発明を強いられる、例外は 1 関数のためにライブラリを
入れること（「過剰なのなら入れなくていい」）。規則が wheel の外へ届いた例はこの 1 件で、
止めたのは文書でなく著者だった。

global harness は逆向きに配線されている。`~/.claude/rules/common/planning.md` は依存追加と
自作 utility をすべて skill `search-first` へ先に通す。`search-first` は依存フットプリントを
複数ある評価軸の 1 つ（Step 2）として扱い、依存に関する anti-pattern は 1 つだけ —
「dependency bloat: 1 つの小機能のために巨大パッケージを入れる」— を挙げ、
Adopt / Extend / Compose / Build の verdict に落とす。skill `implementation-chain` は依存を
追加する plan を Build-or-not 4 問（build 層では agent `architect`）に通すが、問うのは
「それは存在すべきか」であって依存の禁止ではない。「依存を追加するな」という global rule は
無い。

決定を制約する事実が 2 つある。`uv.lock` は gitignore され、耐久性のある pin の記録は
`pyproject.toml` — `[dependency-groups]` の版の床と、`[tool.uv].constraint-dependencies` の
推移依存のセキュリティ床（2026-07-31 の pip-audit drain）。group は `dev`（`uv run` が
自動同期）と `eval`（opt-in、[ADR-0089](0089-llm-behavioral-eval-layer-on-deepeval.ja.md)）。
そして `scripts/` のいくつかは意図的に stdlib-only で、起動元が venv でなく weekly チェーン /
launchd 下の bare `python3` だから — 例: `scripts/weekly-pipeline.sh` 799 行（「stdlib-only →
python3, no uv」）、[ADR-0105](0105-skill-store-exit-confusion-pairs.ja.md) の「venv の外で
走れるよう stdlib-only」。venv のパッケージが要る script の先例は `scripts/weekly-analysis.sh`
の skill-selection 段で、無人の weekly チェーンが `uv run --no-sync python` で起動している。

## Decision

1. **床は wheel の runtime 依存集合であり、`requests` + `numpy` のまま。** 理由は README の
   security-by-absence 主張: wheel は利用者がインストールするものであり、runtime 依存は
   すべてその主張が記述する production プロセス内で実行されるコードである。runtime 依存の
   追加は ADR（新設か本 ADR の追補）を要し、その ADR はゲートも更新する:
   `tests/test_dependency_floor.py` が `[project].dependencies` の配布名が床と一致すること
   （版指定は自由に動かせる）と `[project.optional-dependencies]` が無いことを assert する —
   extra は利用者がインストールする runtime コードなので D1 の内側であって抜け道ではない。
   pyproject だけの編集はテストが落ちる。「依存が増える」だけで却下理由として十分
   なのはこのスコープだけ。
2. **wheel の外 — `[dependency-groups]` の dev と eval、`scripts/`、`tests/`、`evals/` — では
   依存の重さは拒否権を持たない。** 決めるのは search-first の verdict で、判定の問いは
   「その道具の本業か、1 関数のためか」。基礎ライブラリ（pandas、scipy など）は本業なら
   採用、1 関数の必要は numpy か stdlib に留める。「requests+numpy 方針に抵触」はこの
   スコープでは有効な却下理由ではない。既存のゲートは verdict の前に残る: 依存を追加する
   plan は `implementation-chain` の Build-or-not 4 問に答え、`verify.sh` の dependency audit
   は group にも走る。
3. **dev group の依存を使う script は起動元を宣言する。** 依存は `[dependency-groups] dev` に
   置き、script は `uv run --no-sync python` で起動する（先例: `scripts/weekly-analysis.sh`
   の skill-selection 段）。bare `python3` では起動しない。逆に、起動元が venv 外の
   bare `python3` である script では「stdlib-only」は正当な script 単位の性質として残る。
   その制約は script の冒頭コメントに起動元の要件として書き、repo 方針として引用しない。
4. **呼称。** 本 ADR は D1 の集合を「runtime 依存の床」と呼ぶ。ADR-0011 の「Minimal
   Dependency 原則」（orchestrator の Claude Code からの独立）は別の主張で、影響を受けない。

同じ変更での doc sync: `CLAUDE.md` 32 行にスコープ（runtime の床とそのゲート。dev / scripts
は search-first の verdict）を加える。過去の ADR に注記は置かない。ADR-0071 の却下は wheel
スコープでまさに D1。`verify.md` の却下は記録どおり D1。もし import が `TYPE_CHECKING` で
守られていれば（pyright 専用の import は runtime 依存ではない）D2 に落ちた — D1 / D2 の線は
まさにそこを通る。ADR-0075 / 0078 と ADR-0077 の `src/` 却下は D1。
ADR-0077 の dev 層の却下はフットプリントを複数理由の 1 つとして秤にかけており、D2 の
「軸であって拒否権ではない」読みそのもの。ADR-0007 の却下は `core/` のサニタイズに
関するもので D1。README は主張（runtime 依存は 2 つ）が真のままなので変えない。

## Review-when

- README が runtime 依存 2 つの床を security by absence の一部として掲げなくなる → D1 は
  理由を失い、本 ADR はその半分について supersede される。（ADR を*通して*足された
  runtime 依存は D1 の追補であって失効ではない。ADR *無しに*入った runtime 依存はゲートが
  迂回されたことを意味し、D1 は実態として死んでいる。）
- repo が `scripts/` か `evals/` を別パッケージに分割する → D2 / D3 の境界を新しい wheel
  境界に引き直す。
- `search-first` の verdict 規則が変わり、依存フットプリントが評価軸の 1 つでなく拒否権の
  軸になる → D2 を導き直す。skill は repo の外の harness にあるので、この引き金は repo の
  scan でなく harness の skill-stocktake 時に著者が確認する。
- 本 ADR の日付時点の `dev` group にあるパッケージが解決された版で `verify.sh` のゲートか
  `scripts/weekly-pipeline.sh` の段が壊れる（`uv.lock` は gitignore なので pin は pyproject
  の床） → 1 回目は修理、`dev` group の構成が 1 回目から変わらないまま起きた 2 回目がこの
  引き金で、lock の追跡や狭い pin を D3 に入れるかを
  再開する。

## Alternatives Considered

- **「requests + numpy のみ」を暗黙の repo 全体方針として維持する（現状）。** 却下: 所有する
  ADR が無く境界を引く文も無いので、agent は repo 全体の規則と読み、`scripts/` の計器の
  ために groupby / pivot / diff を `Counter` で手書きして行数とバグ面を増やす（著者の訂正、
  2026-09-12）。規則が適用されたのは wheel のコードだけで、現状はそのスコープを書かない
  まま残す。
- **スコープの 1 文を `CLAUDE.md` に書いて終わりにする — ADR もゲートも無し。** 却下: 1 文は
  読み方を縛るが、決定無しに runtime 依存が入るのを止めない（止めるのは D1 のゲート）。
  起動元の規則（D3）も、床が repo でなく wheel のものである理由を後の読者が辿る記録も
  1 文には載らない。その 1 文はどのみち書く。本 ADR はその 1 文の指す先である。
- **床を完全に撤廃し、runtime 依存も search-first に決めさせる。** 却下: README は runtime
  依存の数を公開の security-by-absence 主張の一部にしており、wheel の import 面がその
  主張の対象である。search-first のフットプリント軸はコスト見積もりであってセキュリティ
  境界ではない。
- **依存を足す代わりに小さな関数を vendor / コピーする。** 一般規則としては却下 — 保守性の
  劣る再発明である。numpy か stdlib で足りる 1 関数の必要に対する D2 の例外としては残る。
- **`scripts/` を独自の依存集合を持つ別の uv sub-project にする。** 未決 — dev group の
  成長で `uv run` の同期時間や pin の衝突が実感できるコストになったとき、または D2 / D3 の
  Review-when が発火したときに再訪する。

## Consequences

**楽になること。** `scripts/` / `evals/` / `tests/` での search-first の verdict が正直に
なる: 依存フットプリントは軸であって拒否権ではないので、Build の verdict が境界の無い
規則に強制されない。計器の手書き集計コードが減り、レビューする行が減る。床に所有者と
スコープと機械ゲートがつき、以後の ADR は方針を前提として言い直す代わりに本 ADR を引く。
「依存」の 2 つの意味（wheel と外側）に名前がつき、レビュアーは異議がどちらについてかを
言える。

**難しくなること。** 無人で実行される第三者コードが増える: weekly チェーンは既に
`$MOLTBOOK_HOME` に対して `uv run --no-sync python` の段を走らせており、D2 はまさにそれらの
段が import できるパッケージ集合を広げる。D1 が守るのは利用者がインストールする wheel で
あって無人プロセス全体ではない — その境界は README の主張であり、本 ADR はそれを広げ
ない。dev group が育ち、`uv.lock` が gitignore のままなので版 drift のリスクも育つ。pin は
`pyproject.toml` の床である。dev 依存を使う script は bare `python3` で起動できず、各 script
が起動元を持ち、weekly チェーンの起動行がそれに合っていなければならない。runtime 依存の
追加に明示的な ADR コストと落ちるテストがつく — これは意図。

## References

- `pyproject.toml` — `[project].dependencies`（D1 の床）、`[dependency-groups]`（D2 / D3 の
  スコープ）、`[tool.uv].constraint-dependencies`（`uv.lock` が gitignore の間の耐久性ある
  pin 記録）
- `tests/test_dependency_floor.py` — D1 のゲート
- `~/.claude/rules/common/planning.md`、skill `search-first`（Step 2 の verdict、
  「dependency bloat」anti-pattern）、skill `implementation-chain`（Build-or-not）— D2 が
  委ねる harness の配線
- `scripts/weekly-analysis.sh` の skill-selection 段 — D3 の `uv run --no-sync python`
  起動先例
- `README.md` §「Security by absence」— D1 が真のまま保つ公開主張
