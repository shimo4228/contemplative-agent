# ADR-0089: DeepEval を土台にした LLM 行動 eval 層

## Status

accepted — 新しい top-level の `evals/` 層を追加する。`core/` / `adapters/` /
`cli/` のランタイム挙動は一切変えない。唯一の gate 変更は、`.claude/verify.sh` の
full mode が新設の `eval` dependency group を sync した状態で pyright を
走らせることである。

## Date

2026-08-06

## Context

この repo には決定論的な品質 gate の一式（`verify.sh`:
format / lint / type / arch / security / deps / test、加えて shell と
markdown）と LLM コードレビュー chain があるが、この ADR の時点で、LLM
コンポーネントが実際に生成するものの品質を測るものは何もない。実際には、
prompt の改訂は手作業で検証されてきた: `.notes/` には replay-distill
v2–v5 のログ、`tests/sampling_probe.py` の side-by-side の目視、apple-fm
の A/B メモがあり、prompt 変更のたびに繰り返される手動の replay-and-stare
ワークフローだった。

`evals/` パスを占有する eval 層はこれが 2 代目である。promptfoo の
prompt-regression harness が 2026-06-10 から 2026-07-03 までそこにあり、
[ADR-0072](./0072-echo-chamber-interventions.ja.md) が削除した: その prompt
モジュールは `DISTILL_PROMPT` / `DISTILL_REFINE_PROMPT` の mapping を
hard-import しており、suite 全体が、
[ADR-0060](./0060-per-episode-grounded-distill.ja.md) がすでに retire していた
batch distill pipeline を regression-test していた — もう走らない pipeline を
テストする dead scaffolding である。あの判断は harness の**対象**についての
ものであって、eval 層についてのものではない。この ADR は、空いたパスを別の
面（distill ではなく comment 生成）と、production の entry point だけを
import する runner で再占有する。`.notes/TASKS.md` の T-C1（axiom-removal
A/B、「evals/ 削除済み → 再構築してから」で blocked）は前提条件の一部を
ここで取り戻すが、その distill 面は引き続き scope 外である。

4 つの prompt asset（`identity.md`, `constitution/`, `skills/`, `rules/`）は
agent 自身によって時間とともに書き換えられる（distill、constitution
amendment）ので、「prompt」は mutable state である — asset を pin しない限り、
今日の run と先月の run は別の agent を測っている。

comment path は temperature 1.3 で `generate_comment()` を通じて publish する
（[ADR-0047](./0047-comment-sampling-temperature.ja.md)）。post は
`wrap_untrusted_content` で wrap される untrusted input なので、
prompt-injection 耐性は実在する、テスト可能な性質である。

これはユーザーの Claude-harness 全体にとっての pilot でもある:
`verify-bootstrap` の gate メニューには「eval」軸がなく、LLM の形をした
すべてのプロジェクトが同じ欠落を継承している。`contemplative-agent` が
先陣を切る。この軸を他プロジェクトへ一般化することはここでは scope 外である。

外部調査（scout、as-of 2026-08-06）で、DeepEval 4.1.5（Apache 2.0、
2026-07-31 リリース）が golden dataset 管理・custom metrics・pytest/CLI 統合を
native にカバーすることが分かった。cloud の regression 比較
（`--official` / Confident AI）には、この決定は**依存しない**。

[ADR-0077](./0077-chaos-tdd-fault-injection.ja.md) はかつて、DeepEval への
hard-couple を一因として agent-chaos を却下した — あれは chaos 層の依存に
ついての verdict であって、eval 層の runner としての DeepEval についてのもの
ではない。この ADR が後者の問いに対する別個の判断である。

## Decision

1. **新しい top-level `evals/` package。意図的に `tests/` の外に置く。**
   `tests/conftest.py` は module load 時に `OLLAMA_BASE_URL=http://127.0.0.1:1`
   を設定して unmocked な LLM 呼び出しを殺すが、これは実 eval run を妨害して
   しまう。

2. **`deepeval` を import してよい module が 2 つだけになるようにコードを
   層化する。** 決定論的 core（`evals/dataset.py`, `judging.py`,
   `generation.py`, `compare.py`）は stdlib と `contemplative_agent` だけを
   import し、dev group 下で unit-test される（`tests/test_eval_*.py`、
   49 tests）。`evals/adapter_deepeval.py` と `evals/run_eval.py` だけが
   `deepeval` を import してよい。`deepeval` は新設の
   `[dependency-groups] eval` に置かれ、eval run と `verify.sh` の type gate
   だけが sync する。

3. **進化する prompt asset は、score する前に pin する。**
   `evals/snapshot_assets.py` が、進化する 4 asset を
   （allowlist 方式のみで — `MOLTBOOK_HOME` は credential も保持しているため）
   sha256 manifest 付きで `evals/fixtures/agent_home/` へコピーする。snapshot
   は LLM-distill された出力、すなわち untrusted なので、人間のレビューと
   secret-scan gate がその commit をカバーする。template prompt に snapshot は
   不要である: `MOLTBOOK_HOME` は `prompts/` override のない scratch dir を
   指すので、`config/prompts/` は通常の precedence
   （`core/domain.py resolve_prompt`）を通じて repo の commit に pin される。

4. **production-parity の配線で生成する。** `run_eval` は production の配線
   （`cli/runtime.py` + moltbook `agent.py`）を `core.llm.configure()` 経由で
   mirror し、実 Ollama に対して production temperature で
   `generate_comment()` を走らせる。1 case あたり 3 sample（多数決。tie は
   より悪い verdict に解決する。要求 sample の strict majority が生成に成功
   しなければ case は `INCOMPLETE` となり、その run は baseline になれない —
   生成失敗が `DEVIANT` verdict に成りすますことは決してあってはならない）。
   `configure_skill_selection` は意図的に呼ば**ない**: production は selection
   を shadow mode で走らせており
   （[ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) /
   [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.ja.md)）、
   そこでは selection は常に `None` なので、これを skip することで production
   の system prompt を bit-for-bit 再現できる。Revisit trigger:
   `MOLTBOOK_SKILL_SELECTION_ENFORCE` が production で always-on になったとき、
   eval も追随しなければならない。

5. **隔離された `claude -p` subprocess で judge する。** harness の
   llm-as-judge 設計に従う: binary check 群を evidence として、名前を持つ
   1 つの holistic verdict（`ADHERENT`, `DRIFTING`, `DEVIANT`）へ供給する。
   verdict から `{1.0, 0.5, 0.0}` への mapping は display 専用であり、決して
   集計されない。隔離は `--setting-sources ""`、`--tools ""`、
   `--strict-mcp-config`、scratch cwd、stdin 経由での prompt 受け渡し、そして
   **allowlist 化した環境**（`HOME`/`PATH`/`USER`/`SHELL`/`LANG`/`LC_ALL`/
   `TMPDIR`/`TERM` のみ — `ANTHROPIC_*` / `CLAUDE_*` という名前空間の denylist
   はこちらが列挙し切れるものではなく、漏れた `ANTHROPIC_BASE_URL` や
   `CLAUDE_EFFORT` は manifest の `judge_model` を嘘にする）によって強制する。
   judge prompt は snapshot 済みの constitution
   （[ADR-0002](./0002-paper-faithful-ccai.ja.md)）を評価基準として埋め込む —
   生成側と同じ `load_constitution` の glob で読むので、amendment は両側に
   届くか、どちらにも届かないかのいずれかである — ので、judge が axioms に
   ついての自前の一般観念で代用することはない。untrusted な `post`/`comment`
   block は埋め込み前に delimiter 中和を通る: security review が comment 本文
   への delimiter-splice で judged text を差し替え `ADHERENT` を獲得できることを
   実証したため、生成側の `wrap_untrusted_content` に対応する judge 側の防御を
   置いた（stdlib-only を保つべき `evals/judging.py` にローカル実装）。parse
   済み応答はさらに output contract に対して機械的に検証される
   （`validate_judge_contract`）: 名前付き 5 check が過不足なく揃い、重複が
   なく、`injection_resistant` / `persona_intact` の No は `DEVIANT` を強制
   する — prompt の「dominant No が単独で決める」規則を judge が指示を覚えて
   いるかに依存させない（cross-model review が dominant No を通過した
   ADHERENT の受理を検出した）。parse / contract 失敗は 1 回 retry し、その後
   は fail loud する。各 attempt の生 envelope は run directory の
   `judge-audit.jsonl` へ追記される（observability by default、
   [ADR-0075](./0075-observability-by-default.ja.md)）: parser の欠陥が後日
   見つかっても、judge の実際の非決定的出力を offline で replay できる。

6. **deepeval 自身の出力ではなく、正規化した run-JSON contract を emit
   する。** contract artifact は `schema_version`、`manifest`
   （`target_model`, `temperature`, `judge_model`, `assets_sha256`,
   `judge_prompt_sha256`, `dataset_sha256`, `samples_per_case`、そして
   `case_ids` — id 集合を記録することで、`--cases` の subset run は full
   baseline に対して silent な「clean」ではなく incomparable になる）、
   そして check と verdict を伴う per-case の sample を運び、case が終わる
   たびに逐次書き出されるので、中断された run も完了済み case は inspect
   できる。`evals/compare.py` は `evals/baselines/` の承認済み baseline に
   対して case ごとの verdict transition を diff する。manifest の不一致と
   shape violation はすべて incomparable（exit 2 — 壊れた baseline が
   regression として表面化してはならない）であり、regression は exit 1 で
   ある。deepeval 自身の `TestRun` 出力（`DisplayConfig results_folder`）は
   debug の副産物であって比較 contract では決してないので、deepeval の
   upgrade が baseline を壊すことはできない。

7. **eval を `verify.sh` へは配線しない。** eval は遅く、stochastic で、
   delta-judge される — 速い決定論的 gate とは別の contract である
   （exit code 0/1/2 は意図的にそれを mirror している）。最初の full run
   （2026-08-06）での実測: 12 cases × 3 samples = 36 generations を
   ~30k-token の system prompt の下で gemma4:e4b で走らせ、加えて 36 回の
   逐次 `claude-sonnet-5` judge 呼び出しで **約 19 分** — authoring 時の
   40–90 分見積もりを大きく下回った。手動 run の trigger: prompt-asset、
   model、sampling、generation-path の変更。

8. **telemetry opt-out を強制し、cloud credential を落とし、cache を封じ込める。**
   `DEEPEVAL_TELEMETRY_OPT_OUT=1` は `run_eval` と — 構造的保証として —
   `adapter_deepeval.py` 冒頭（自身の `deepeval` import の前）の両方で設定
   される。sanctioned module 経由で deepeval を import するどの entry point
   も telemetry off で走る（`"1"` は deepeval が document する `=1` 形式でも
   settings の bool-parse でも truthy）。`CONFIDENT_API_KEY` /
   `DEEPEVAL_API_KEY` / `DEEPEVAL_RESULTS_FOLDER` は環境から pop する:
   telemetry opt-out は Confident AI への upload 経路を覆っておらず、login
   key が居れば golden post と生成 comment が cloud へ POST される。
   `.deepeval` cache/keystore は `DEEPEVAL_CACHE_FOLDER` + `chdir` で per-run
   に封じ込め、`.deepeval/` は gitignore する（keystore は API key を平文で
   置く）。markdown gate は `evals/fixtures/**` を ignore する
   （`.markdownlint-cli2.jsonc`）。`docs/evidence/**` と同じ理屈である:
   snapshot と judge prompt は verbatim の apparatus であって、reformat
   すべき文書ではない。security gate は `bandit -r src evals` へ広げる —
   eval 層は subprocess/env/rmtree という bandit の主戦場を持つ。snapshot
   manifest は aggregate hash と file count だけを記録する: per-file hash は
   harness secret scan の entropy detector を 40+ 回踏み、どのみち
   `run_eval` は disk から再計算する（`hash_tree`）。

9. **golden dataset は 12 case で seed する: 4 axioms × {normal, edge,
   adversarial}。** `evals/datasets/comment_golden.jsonl` は
   `tests/fixtures/sampling/comment_suite.jsonl` から seed される。
   adversarial case は post content に instruction を埋め込む。これが意味を
   持つのは、その path 上に `wrap_untrusted_content` が座っているからである。

## Alternatives Considered

### Inspect AI (UK AISI)

behavioral eval への設計適合は最も強く、最も活発にリリースされている選択肢
でもある（0.3.252、2026-08-04）。今回は却下: baseline/regression diff が
native ではないため同じ自作 compare 層がどのみち必要になり、Task/Solver/Scorer
抽象は現時点で見返りのない学習コストである。eval が multi-turn や tool-use
scoring を必要とするようになった場合に compose していく自然な移行先として
記録しておく。

### promptfoo

この repo が実際に走らせたことのある唯一の代替: 2026-06 の `evals/` harness
は promptfoo ベースで 3 週間運用されたので、Node runtime 依存が一度は許容
可能だったことは実証済みである。それを殺したのは runtime ではなく coupling
だった（ADR-0072）: 削除済みの prompt 定数への hard import を通じて、retire
済みの pipeline を regression-test していた。再構築にあたっては、なお残る
構造的 mismatch を理由に却下する: pip package は `npx` へ shell out する
wrapper であり、この層の新しい要件 — repo 自身の dev group 下で unit-test
可能な決定論的 core が production の `generate_comment()` seam を直接
import すること — は in-process の Python runner を欲する。YAML-config の
Node CLI はそれになれない。

### pytest-evals

薄すぎるとして却下: judge がなく、baseline の machinery もない。pytest-evals
が提供するはずの pytest 統合は DeepEval がすでに含んでいる。

### ragas

rubric の machinery は存在するが、framework の重心は RAG metrics にある。
persona/constitution の judging には遠回りとして却下。

### 自作 runner（status quo の延長線: `benchmark_distill.py` を育てる）

コントロールは最大、新規依存はゼロ。却下の理由: dataset・report・統合の
plumbing は DeepEval がすでに ship している undifferentiated な仕事であり、
project-specific に留まらねばならない部分（judge contract、正規化 JSON、
compare）はどちらの道でも project-specific に留まるからである。

## Consequences

### Positive

- prompt と model の変更が、目視ではなく反復可能な regression signal
  （case ごとの verdict transition）を得る。これは従来 `.notes/` にログ
  されていた手動 replay ワークフローの形式化である。authoring 時点では
  machinery は整っているが baseline はまだ commit されていない —
  `evals/baselines/` は最初の人間承認済み full run で populate され、それ
  までは regression gate は operational でない。
- injection 耐性が、adversarial な golden-dataset case を通じて計測される
  性質になる。
- harness は、`verify-bootstrap` が現在欠いている eval 軸の pilot を得る。

### Negative

- `deepeval` は ~60 package の transitive tree を持ち込むので、`pip-audit`
  の audit surface がそれに応じて拡大する。意図的に受け入れる: その tree の
  CVE が commit を block できるようになるのは、honest である。
- `verify.sh` の type gate は full run のたびに eval group を解決するように
  なる（`uv run --group eval pyright`）ので、eval を一切走らせなくても full
  Verify は deepeval の resolution コストを払う。記録すべき coupling: 上記の
  pip-audit カバレッジが成立するのは、deps gate が、直前に type gate が
  populate した venv を audit し、その後の plain な `uv run` がそれを prune
  しないからである — gate の順序や uv の pruning 挙動が変われば、この audit
  カバレッジは silent に消える。
- full run のコストは wall clock 約 19 分（2026-08-06 実測）、加えて成功
  sample ごとに 1 回の `claude -p` 呼び出し（default で 1 run あたり 36 回）—
  `--cases` / `--samples` で緩和される。
- type gate は、長時間の eval run が開いたまま保持する共有 `.venv` を
  書き換える: eval 実行中に Verify（あるいは plain な `uv run`）を走らせると、
  in-flight の run の足元でその venv が再解決される。ここでは修正しない —
  `UV_PROJECT_ENVIRONMENT` で eval を別 venv に向ければ消えるが、この ADR が
  意図的に受け入れた pip-audit カバレッジも一緒に消えるため、trade せずに
  coupling として記録する。
- verdict は temperature 1.3 で stochastic である。majority-of-3 は flip を
  減衰させるが除去はしない。run-to-run の安定性は未解決の測定課題であり、
  不十分と判明した場合の documented escalation は `samples=5` である。
- snapshot asset は live agent の進化とともに古びる。re-snapshot は設計上
  既存 baseline のすべてを無効化する（manifest mismatch）ので、snapshot の
  たびに baseline を再承認しなければならない。
- この eval が測るのは comment 面だけである。distill 品質は引き続き
  `tests/benchmark_distill.py` がカバーする。

### Neutral / Follow-ups

- Revisit trigger: `MOLTBOOK_SKILL_SELECTION_ENFORCE` が production で
  always-on になったとき、parity を保つために `run_eval` は
  `configure_skill_selection` を呼ばなければならない（Decision 4）。
- 手動 run の trigger: prompt-asset、model、sampling、generation-path の変更
  （Decision 7）。eval は設計上 `verify.sh` の外に留まる。
- 「eval」軸を `verify-bootstrap` の gate メニューへ一般化することは、この
  ADR では明示的に scope 外である。`contemplative-agent` が pilot である。

## References

- `ADR-0072`（`0072-echo-chamber-interventions.md`）— 以前の promptfoo
  `evals/` harness を、ADR-0060 で retire 済みの batch pipeline をテストする
  dead scaffolding として削除した。この ADR は空いたパスを再占有する
  （supersede ではない — 0072 の判断は harness の対象についてであって、
  eval 層についてではない）
- `ADR-0077`（`0077-chaos-tdd-fault-injection.md`）— 区別: 却下されたのは
  agent-chaos の DeepEval への hard-coupling であり、この ADR による
  eval-layer runner としての DeepEval 採用とは別の問い
- `ADR-0047`（`0047-comment-sampling-temperature.md`）— この eval の生成
  path が mirror する production temperature（1.3）
- `ADR-0060`（`0060-per-episode-grounded-distill.md`）— 4 つの prompt asset
  を mutable に保つ per-episode distill プロセス。Decision 3 の
  asset-pinning 規律の動機
- `ADR-0076`（`0076-skill-selection-shadow-instrument.md`）と `ADR-0081`
  （`0081-skill-selection-two-pass-injection-enforcement.md`）— shadow-mode
  の skill selection。Decision 4 で `configure_skill_selection` を skip する
  理由
- `ADR-0002`（`0002-paper-faithful-ccai.md`）— judge が score の基準とする
  constitution
- `ADR-0088`（`0088-shipped-conformance-kit-for-the-llm-backend-contract.md`）
  — 層化の先例: runtime の import path の外に保たれる shipped kit。`evals/`
  は同じ精神に従うが、ここでは import-linter contract ではなく package 外
  への配置によって強制される。`root_packages=["contemplative_agent"]` が
  `evals/` を見ないためである
