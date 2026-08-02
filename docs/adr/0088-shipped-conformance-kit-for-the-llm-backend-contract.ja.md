# ADR-0088: `LLMBackend` 契約の適合キットを出荷物に入れる

## Status

accepted — [ADR-0066](./0066-backend-aware-context-budget-guard.ja.md) /
[ADR-0087](./0087-optional-token-counting-capability-for-the-context-budget-guard.ja.md)
の backend seam を運用可能にする。ランタイム挙動は一切変えない: `core/` /
`adapters/` / `cli/` のいずれもこのキットを import できず、キットが報告する契約違反は
名前が付く前からすでに違反だった。

## Date

2026-08-02

## Context

`contemplative-agent-cloud` の最終変更は 2026-04-21（`d6d2da7`）。それ以降 2026-08-01
までに `LLMBackend` Protocol は `temperature` を得て、`think` を得て、戻り値型を
`str | None` から `BackendResult | None` へ変え、`context_window` プロパティを得て、
optional な `count_tokens` capability を得た — 5 つの変更のどれも sibling に届いていない。
今 main から呼ぶと最初の `generate()` で `TypeError` になる。

その 3 か月が気づかれなかった。**なぜ**についての 2 つの事実が、この ADR の決定を規定する。

### sibling にはすでに適合テストがあった

`contemplative-agent-cloud/tests/test_anthropic_backend.py:100` は
`isinstance(backend, LLMBackend)` を assert している。`AnthropicBackend` は
`context_window` を持たないので、この assert は今日走らせれば落ちる。テストは正しく、
drift の一部を捕まえたはずだった。誰も走らせなかっただけである。

これは素朴な枠組みを否定する。問題は「テストが無いこと」ではなく、同じ場所により良く
書かれたテストも同じ運命を辿る。作るべきものは、**動機を持つ側**——契約変更を publish
する瞬間の main——が走らせられるものであって、四半期のあいだ触られていない repo が
走らせるものではない。

### `isinstance` は drift の後半を見られない

`LLMBackend` は `runtime_checkable` であり、runtime-checkable Protocol はメンバーが
**存在するか**しか見ない。シグネチャも戻り値型も不可視である。cloud の
`generate(prompt, system, num_predict, format) -> Optional[str]` はメンバー検査を完全に
通る。`isinstance` が落ちる理由は、それとは別の `context_window` の不在だけである。

つまり backend は `isinstance` 的に綺麗なまま、最初の実呼び出しで `TypeError` になりうる。
それを検出するには別の問いが要る: 「メンバーは存在するか」ではなく
**「このオブジェクトは呼び出し側が実際に発行する呼び出しを bind できるか」**。

### 正本ヘルパが一度も再利用されなかった理由

`tests/chaos.py` は fault-injection の正本キットとして書かれ（ADR-0077）、どの sibling も
import していない。`[tool.hatch.build.targets.wheel]` は `src/contemplative_agent` しか
package しないので `tests/` は wheel に入らない: `contemplative-agent` に依存する sibling は
import できないし、できたことがない。「main が正本を持つ」は意図としては真、配布の仕組み
としては偽だった。

## Decision

1. **キットは出荷物に入れる。** `src/contemplative_agent/testing/` に置き、wheel の内側に
   入れるので sibling は既存の依存経由で到達できる。`tests/` 案は上記の配布の事実により
   却下 — 要件を満たさない。それが、踏襲するはずだった先例の消費者がゼロである理由でもある。

2. **キットは標準ライブラリと `contemplative_agent.core.llm` しか import しない。**
   pytest / hypothesis / `responses` は dev グループ限定であり、実行時依存は
   `requests` + `numpy` のまま。`tests/chaos.py` がすでに「再利用可能なテスト部品に
   pytest は要らない」ことを実証している。キットは出荷物なので、より強い理由で同じ規律に従う。

3. **`layers` の 4 つ目のエントリではなく `forbidden` contract を 2 本。**
   production 層はキットを import してはならず、キットは `cli` / `adapters` を import しては
   ならない。`layers` エントリは方向を正しく述べる一方で `testing -> adapters` も許してしまい、
   Moltbook の HTTP クライアントを sibling のテスト依存に引きずり込む。欲しいのは両側からの
   狭い禁止である。

4. **効く検査はメンバーの存在ではなく bind 可能性。**
   `generate.binds_canonical_call` は `_generate_via_backend` が発行する呼び出しそのもの
   ——位置 4 つ、`temperature` と `think` がキーワード専用——を bind する。パラメータ**名**の
   一致は要求しないので、`**kwargs` を取る backend も適合のまま。要求するのは、呼び出し側が
   実際にする呼び出しが raise しないことである。これが `isinstance` に表現できない検査。

5. **失敗は raise でなく戻り値。** `check_backend` は `ConformanceReport` を返す。埋めたい
   失敗は累積した drift であって単発のバグではない: 最初の不一致で raise すると「壊れているか」
   には答えるが「何通りに、どこが」を壊す。レポートは `__bool__` と複数行 `__repr__` を持つので、
   `assert check_backend(b)` は 1 行のままで、落ちたときには全ての失敗検査を名指しする。

6. **実行を決めるのは検出であり、宣言は下限。**
   capability が検査されるのは backend 上で**検出された**からであり、宣言し忘れが被覆を
   黙って消すことはない。宣言したのに検出されなければ失敗する。検出されたのに未宣言なのは
   失敗に**しない** — さもないと capability 定数をこのモジュールに 1 つ足すだけで、純粋に
   宣言的な理由で 3 repo が赤くなる。その水準で観測できない宣言は、棄却ではなく保留である。

7. **`require=LEVEL_STATIC` は恒久の既定。** level（`static` / `runtime` / `full`）は
   sibling が自分の被覆水準を宣言する仕組みで、宣言に届かなければ失敗する。だが**既定**を
   後から上げると、何も変えていない sibling が赤くなる — drift を減らすためのキットが
   決して起こしてはならない破壊そのもの。被覆は sibling 自身の呼び出しを編集して上げる。
   そこなら grep できる。`level_reached` は登録済み検査が存在する最高 level で上限を掛ける。
   将来用 `BackendProbe` を渡しただけで、今日の static-only キットが full の false green を
   返すことはない。

8. **出荷は段階化し、API は最初の段階で凍結する。** 今回は static 6 検査を載せ、
   sibling 側の作業ゼロで cloud に現在観測される static の 3 failure を捕まえる。
   stale な `Optional[str]` return は検査しない。それは runtime の
   `result.is_backend_result` として明示的に収録されている。runtime / 構築時の検査
   （残り 23、下表に収録）は後続。`check_backend` のシグネチャ、`ConformanceReport`、
   `BackendProbe`、level と capability の語彙は今すでに完成形であり、以降の段階は検査を
   足すだけで引数は足さない。

9. **`circuit_reading()` を read-only 計器として `core.llm` に足す。**
   sibling のテストが `_circuit._consecutive_failures` を直読みしているので、
   `_CircuitBreaker` 内部の rename が 3 repo を静かに壊す。この読み値は
   [ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) の意味での計器
   ——既存状態、機構なし、ゲートに供給しない——であり、すでに公開されている制御
   `circuit_shield()` の隣に並ぶ。

10. **キットは sibling でなく main から走らせる。** `python -m
    contemplative_agent.testing --backend pkg.mod:Name` は sibling 側にテストファイルを
    一切必要とせず、`scripts/check-sibling-backends.sh` が既知の全 sibling に対して回す。
    強制ゲートはリリース手順中の人間ゲート——
    [`docs/runbooks/sibling-backend-conformance.md`](../runbooks/sibling-backend-conformance.md)、
    `release-doi` skill の検証と push の間から呼ぶ。これは
    [ADR-0012](./0012-human-approval-gate.ja.md) の「人間がすでに立っている場所に判断を置く」
    パターンに従う。

11. **日常の Verify では sibling code を import しない。** runner は隣接 checkout の
    Python を import して constructor を実行する。advisory 判定であっても
    `.claude/verify.sh` から自動実行すれば、侵害された sibling が main-only の検証中に動ける。
    明示的な release gate は、人間の判断点であると同時に、operator が sibling checkout を
    executable input として受け入れる点でもある。

12. **unusable と non-conforming を潰さない。** CLI と runner は exit taxonomy
    `0` 適合 / `1` 非適合 / `2` target または kit が利用不能、を保ち、infra failure は backend
    verdict より優先する。CLI の constructor kwarg は argv に露出するため `base_url` / `model`
    の allowlist に限定する。`base_url` は credential-free な HTTP(S) origin のみ許可し、
    それ以外は local factory に委ねる。module / constructor 由来の任意 exception 本文は
    出さず型だけを報告する。

### 新しい検査を書くときの規約

**`contemplative_agent.core.llm` が公開再輸出しているシンボルにしか assert してはならない。**
telemetry のフィールド名や estimator の定数をハードコードする検査は、内部 rename のたびに
契約上の理由なく 3 repo を赤くする。そうした値はキットが export する定数に逃がすか、導出する
——over-budget 検査はプロンプト長を `backend.context_window` から構成し、estimator の
chars-per-token からは決して構成しない。

### 検査カタログ

今回出荷（6 件）:

| check_id | level | capability |
|---|---|---|
| `protocol.members` | static | — |
| `model.type` | static | — |
| `context_window.positive_int` | static | — |
| `generate.binds_canonical_call` | static | — |
| `generate.kwonly_defaults` | static | — |
| `count_tokens.signature` | static | `counts_tokens` |

加えて backend でなく実行そのものを報告する meta 検査 2 件:
`meta.level_reached` と `meta.declared_capabilities_present`。

収録済み・未実装（23 件）。"core" 検査は呼び出し側の保証がこの backend でも成り立つことを
assert し、"direct" 検査は backend 自身が契約を守ることを assert する。この区別が要るのは、
2 つの失敗が別のことを意味するからである:

| check_id | level | 経路 | capability |
|---|---|---|---|
| `result.is_backend_result` | runtime | direct | — |
| `result.finish_reason_passthrough` | runtime | direct | `reports_finish_reason` |
| `result.counters_absent_stay_none` | runtime | direct | — |
| `result.null_content_becomes_empty_string` | runtime | direct | — |
| `result.prefill_accounting_parsed` | runtime | direct | `reports_prefill` |
| `result.thinking_parsed` | runtime | direct | `produces_thinking` |
| `sampling.top_p_top_k_sent` | runtime | direct | — |
| `sampling.temperature_default_one` | runtime | direct | — |
| `request.empty_system_omitted` | runtime | direct | — |
| `parse.malformed_raises` | runtime | direct | — |
| `transport.error_propagates` | runtime | direct | — |
| `core.sanitization_applies` | runtime | core | — |
| `core.temperature_reaches_backend` | runtime | core | — |
| `core.drop_truncated_returns_none` | runtime | core | `reports_finish_reason` |
| `core.truncated_kept_when_not_dropped` | runtime | core | `reports_finish_reason` |
| `core.truncation_is_not_circuit_failure` | runtime | core | `reports_finish_reason` |
| `core.transport_failure_counts_as_circuit_failure` | runtime | core | — |
| `core.over_budget_skips_before_backend` | runtime | core | — |
| `core.telemetry_records_model` | runtime | core | — |
| `core.telemetry_records_prefill` | runtime | core | `reports_prefill` |
| `construct.rejects_untrusted_host` | full | 構築時 | — |
| `construct.rejects_non_http_scheme` | full | 構築時 | — |
| `construct.rejects_non_positive_context_window` | full | 構築時 | — |

このうち 3 件は素直な配置を拒むので、推論を再発見せずに済むようここに記録する:

- `request.empty_system_omitted` は core 経由にできない。`_generate_impl` が
  `request.system or _build_system_prompt()` を評価するので、空の system 文字列は falsy と
  判定され、backend が見る前に置換される。backend が空 system をどう扱うかは直接呼び出しでしか
  観測できない。
- `transport.error_propagates` も core 経由にできない。core は backend が raise しても
  `None` を返しても等しく circuit failure を記録するので、そこからは区別できない。契約は
  backend が **raise すること**である——さもないと telemetry の
  `error_kind="backend_exception"` が `outcome="empty"` に潰れ、診断が失われる。
- `core.over_budget_skips_before_backend` はプロンプト長を `backend.context_window` から
  構成しなければならない。リテラルは estimator の現在の chars-per-token を焼き込み、再調整で
  壊れる — 上記の規約の具体形。

## Alternatives Considered

### sibling-local test と手動確認を維持する

現状では却下。cloud にはすでに sibling-local な適合テストがあったが、3 か月にわたり誰も
実行も更新もしなかった。手動比較にも同じく trigger が無く、名前付きで再現可能な verdict を
残さない。全 sibling に active maintainer と独立に強制される release gate が存在すれば再び
成立し得るが、その実証は今日存在しない。

### キットを `tests/` に置き sibling に vendoring させる

先例（`tests/chaos.py`）どおりの案。好みではなく配布の事実により却下: `tests/` は wheel に
入らないので sibling は import できない。コピーによる vendoring は、drift を生んだ手写しを
そのまま再現する。

### 各 sibling に GitHub Actions を足す

当初のプランであり最初の直感。**このファミリーのどの repo にも CI が存在しない**——main /
`-mlx` / `-cloud` のいずれにも `.github/workflows/` が無い——と判明したため却下。この
プロジェクトが一度も使っていないインフラを、何か月も触られない 2 つの repo に導入して、
「その repo が何か月も触られないこと」が生んだ問題を検出しようとすることになる。ゲートは
動機のある場所——リリース時の main——に属する。

### 注入点を個別の callable として渡す

`check_backend(b, sent_sampling_params=..., stub_malformed=..., ...)` の 6〜7 個。却下:
呼び出し側で読めず、sibling に pyright が検査できる型的ターゲットを何も与えない。ADR-0087 が
`TokenCountingBackend` を `LLMBackend` から切り出したのと同じ理由である。`BackendProbe` は
2 メソッドで、素直なアクセサ群は意図的に含めていない: `sent_messages()` は chat messages 配列を
キットに焼き込むが、Anthropic（system が配列の外）や completion 型 backend はそれを持たない。

### キットが `_circuit` を直接読む

private 結合を 3 repo から 1 repo に移すので改善ではある。しかしキットは**出荷される** —
出荷モジュールが自パッケージの private を読むこと自体が契約の穴であり、どのみち
`_CircuitBreaker` の属性名を固定してしまう。

### circuit の挙動をブラックボックスで観測する

5 回失敗させて 6 回目が短絡するか見る。遅く、かつ「この呼び出しは失敗に数えられたか」と
「閾値は機能するか」を混同する。引き上げたい検査は前者（truncation drop がカウンタを増やさない）
であり、それは読み値でしか表現できない。

### `forbidden` 2 本でなく `layers` エントリにする

Decision 3 を参照 — `testing -> adapters` を許してしまう。

## Consequences

### Positive

- cloud に観測された static の 3 failure が**実測**になった。今日 main からキットを走らせると:
  `contemplative_agent_cloud.backends.anthropic:AnthropicBackend` と
  `...openai:OpenAIBackend` が `protocol.members` /
  `context_window.positive_int` / `generate.binds_canonical_call` を名指しして exit 1、
  `contemplative_agent_mlx.backends.mlx:MlxLmBackend` は exit 0。キットは初回実行で
  生きている sibling と古い sibling を区別した。
- 登録済み検査が被覆する契約変更は、沈黙ではなくリリース時の赤を生む。runtime の return semantics
  は収録済み runtime stage まで保留である。
- `T-CLOUD-SIBLING-STALE` の未決事項（アーカイブ / 書き直し / 最小修正）に具体的な入力が
  加わる — 「何かが壊れている」という記憶でなく、壊れている箇所の名前付きリスト。
- sibling のテストは private な `_circuit` 直読みを落とせる。

### Negative

- **登録済み検査が被覆する契約変更が 3 repo を同時に赤くする。** これは**契約についての** assert では意図した
  挙動である。その赤が欠けていた通知であり、CI 相当の 1 回は 3 か月の沈黙に勝る。一方
  **実装詳細についての** assert では純コストであり、上記の規約はそれを防ぐために存在する。
  この区別をここに記録することが重要である: 無いと最初の赤が「キットが脆い」と読まれ、
  キットが撤去される。
- 出荷パッケージに、production 経路が一切使わないモジュールが増える。目的そのものである
  配布の性質のためにコストを受容する。forbidden contract 2 本が方向を正直に保つ。
- 29 検査のうち 23 件は収録のみで未実装。`LEVEL_STATIC` 止まりの sibling は表が示唆するより
  ずっと薄くしか検査されておらず、`expected_checks()` と implemented-level cap が runtime / full
  の被覆と読み違えることを防ぐ。
- 明示的な release command は隣接 sibling checkout の code を実行する。operator はその checkout
  を trusted code として扱う必要があり、日常 Verify へ移すと execution boundary が静かに広がる。
- 出荷 API の凍結には migration cost がある。破壊的変更には major version 境界か旧 call を受ける
  compatibility shim が必要で、退役時は先に sibling import と release-gate 呼び出しを除去する。
  consumer が import している間に wheel module だけを消すことはできない。

### Neutral / Follow-ups

- `_core_harness.py` を core 内部への結合を隔離する 4 つ目のモジュールとして計画していたが、
  今回は**作らない**: runtime 検査が未着地の段階では中身が無く、空の private モジュールは
  不在より悪い。runtime 検査と同時に生まれる。
- キットは `T-FINISHREASON-GATE` に居場所を与える。`reports_finish_reason` は
  「truncation ゲートを持たない backend」を事故ではなく宣言された事実に変える。これは同タスクの
  (a) / (b) / (c) の枠組みより安い決着である。
- `contemplative-agent-otel` が `CLAUDE.md` の関連リポジトリ表に無い。`LLMBackend` を実装
  しないので本 ADR の射程外でありキットの射程外でもあるが、欠落として記録しておく。

### Provenance

Context の 2 つの前提訂正——cloud にすでに適合テストがあったこと、`tests/` が wheel に
入らないこと——はこの変更の計画中に判明し、両方とも台帳に書かれていた元のタスク
（`T-BACKEND-CONTRACT-KIT`。目的を「`tests/chaos.py` と同じ形で export する」と記述していた）
を反転させた。CI 案は実装途中に判明した事実により却下した。Positive に引用した適合結果は、
2026-08-02 に出荷キットをチェックアウト済みの sibling に対して実行したものであり、
コード読解によるものではない。

## References

- `ADR-0066`（`0066-backend-aware-context-budget-guard.md`）— depends-on。このキットが検査する tolerate-absence の規律を確立した
- `ADR-0087`（`0087-optional-token-counting-capability-for-the-context-budget-guard.md`）— depends-on。`TokenCountingBackend`、および optional capability を別 Protocol として表現する先例
- `ADR-0077`（`0077-chaos-tdd-fault-injection.md`）— 先例。`tests/chaos.py` はこのキットが踏襲する pytest 非依存のスタイルであり、同時に配布についての反面教師
- `ADR-0012`（`0012-human-approval-gate.md`）— 先例。人間がすでに立っている場所に判断を置く
- `ADR-0071`（`0071-read-only-pattern-composition-instruments.md`）— 先例。`circuit_reading()` を機構でなく計器として置く
- `ADR-0001`（`0001-core-adapter-separation.md`）— forbidden contract 2 本が拡張する import 方向の規則
- `ADR-0079`（`0079-module-reorganization-package-splits.md`）— `contemplative_agent/testing/__init__.py` が従う facade 再輸出の規約
- [`docs/runbooks/sibling-backend-conformance.md`](../runbooks/sibling-backend-conformance.md) — リリースゲートの手順
