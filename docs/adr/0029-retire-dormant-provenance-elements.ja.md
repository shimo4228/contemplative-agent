# ADR-0029: dormant な provenance 要素を撤回 — `user_input` / `external_post` / `sanitized`

## ステータス

accepted

## 日付

2026-04-18

## 背景

ADR-0021 (2026-04-16) は `knowledge.json` に provenance + trust 層を追加した。着地後 audit ([evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)) で Provenance 群に schema 宣言だけされ実挙動が伴わない要素が 3 件見つかった。ADR-0028 (2026-04-18) で forgetting / feedback 群を撤回した延長として、本 ADR は Provenance 群の残りの dormant 要素を整理する。

### 1. `source_type = "user_input"` — producer なし、security 境界と矛盾

`SOURCE_TYPES` に trust base `0.7` で宣言されているが、emit する経路が存在しない:

- `_episode_source_kind` は episode を `self` / `external` / `unknown` にしか分類しない
- `_derive_source_type` は `self_reflection` / `external_reply` / `mixed` / `unknown` しか返さない
- `memory_evolution.apply_revision` は `mixed` しか書かない
- `migrate_patterns_to_adr0021` は `unknown` しか書かない

本番 `source_type = "user_input"` は **0 件**。trust `0.7` は ADR-0007 (全外部入力は untrusted) とも矛盾する。

### 2. `source_type = "external_post"` — producer なし、主防御は quarantine

`SOURCE_TYPES` に trust base `0.5` で宣言され、ADR-0021 L133 の MINJA defense narrative で参照されているが、本番に producer は存在しない:

- `_episode_source_kind` は `activity` / `post` / `insight` 型 episode を全て `self` に分類する。他人の post に対するリアクション (like 等) が `activity` record に入っても `external_post` には流れない
- `summarize_record(activity)` は `"{action} {target}"` しか返さず、対象 post の本文は distill LLM prompt に到達しない
- `_derive_source_type` に `external_post` を emit する分岐はない

本番 `source_type = "external_post"` は **0 件**。audit (§6) が示したとおり、実際の主防御は **Model B: summarize 境界での quarantine** — 外部 post 本文は構造的に distill pipeline に到達しない。distill に到達する唯一の外部入力経路 (`external_reply`, trust `0.55`) が secondary defense として機能する。

### 3. `provenance.sanitized` — 常に `True`、consumer なし

provenance schema に宣言され、ADR-0021 L52 で `sanitized=false` のとき trust を `−0.2` する規則が明記されている。実装は書き込み専用:

- `distill.py:700` は `"sanitized": True` を無条件 hardcode
- `memory_evolution.py:173` は継承値を単に copy
- `views._rank` は flag を読まず、`−0.2` 補正は未配線
- 本番: 77/77 件が `True`、`False` は一度も観測されない

LLM output 自体は `llm._sanitize_output` (`llm.generate()` 内から呼ばれる) で upstream sanitize されるが、この関数は clean 後の文字列しか返さず、「置換が発生したか」の signal を provenance まで伝搬しない。つまりこの flag は「検査結果」ではなく「hardcode された True」で、情報を持たない。

## 決定

dormant な 3 要素を撤回する。

### Schema 削除

- `SOURCE_TYPES` タプルから `"user_input"` / `"external_post"` を除去 (残: `self_reflection`, `external_reply`, `mixed`, `unknown`)
- `TRUST_BASE_BY_SOURCE` dict から `user_input` / `external_post` 行を削除
- `provenance.sanitized` フィールドを schema から除去

### Producer 削除

- `distill.py` は新規 pattern に `"sanitized": True` を書き込まない
- `memory_evolution.apply_revision` は revised row に `sanitized` を copy しない

### Load 経路での silent strip

`knowledge_store._parse_json` は読み込み時に `provenance.sanitized` を落とす。legacy file は clean に load され、本 ADR 後の次回 save で `knowledge.json` は flag なしに書き直される。ADR-0028 で確立された retired-field 削除パターンに倣う。

### Migration (一度限り)

`migrate_patterns_to_adr0021` は既に `knowledge.json` の backup + 全 pattern rewrite を行う。`_ensure_adr0021_defaults` に `provenance.sanitized` の明示 pop を追加し、strip-drift 検出器は `provenance.sanitized` を含む on-disk pattern を count するように拡張した (他フィールド変更なしでも save が走る)。本番 77 件を即時 strip するには `contemplative-agent migrate-patterns` を 1 回実行すれば良い。

### ADR-0021 の partial supersede

ADR-0021 の Provenance セクションが本 ADR で部分撤回される:

- L31-32 `source_type` enum から `user_input` / `external_post` を削除
- L34 `sanitized` field を削除
- L47-48 trust 表から 2 行削除
- L52 `−0.2 if sanitized flag is false` 補正節を削除
- L133 MINJA defense narrative を audit の Model B / Model A 分析 (quarantine が primary、trust-weighting は `external_reply` 経由の secondary) に合わせて書き換え

ADR-0021 status を `partially-superseded-by ADR-0028, ADR-0029` に更新。

## 検討した代替案

1. **`sanitized` consumer を実装する**: `_sanitize_output` を `(text, was_modified)` タプル戻りに変更し、`llm.generate()` → `distill.py` と伝搬、`views._rank` に `−0.2` 補正を配線。却下: 本番の False 発火率は 0/77 で signal がほぼゼロ。`FORBIDDEN_SUBSTRING_PATTERNS` は identity-leak 句が対象 (汎用 prompt injection ではない) で、REDACTED hit は retrieval の nudge より調査アラートの方が適切。LLM output は flag の有無に関わらず upstream で sanitize される。

2. **`external_post` を将来の post-observation adapter 用に reserved で残す**: schema に宣言のまま producer 不在を documentation する。却下: dormant schema は rot する (audit で偶然発見)。実 producer が登場したタイミングで enum を追加し直すほうが安い。残すと ADR-0028 が指摘した同じ drift を招く。

3. **`user_input` を仮想的な手動 `add-pattern` CLI 用に残す**: 却下: そのような CLI は存在も計画もない。手動 user input に trust `0.7` は ADR-0007「全外部入力は untrusted」原則と矛盾する。もし将来そういう CLI が登場しても、正しい入り口は `external_reply` もしくは脅威モデルを伴う新 ADR で新規追加する source_type である。

4. **ADR-0029 を立てず ADR-0028 のスコープを拡張する**: 却下: ADR-0028 は forgetting / feedback 機能群の撤回に特化している。provenance 整理を混ぜると将来の読者に narrative が濁る。撤回判断 1 件につき 1 ADR を残すことで audit trail が clean に保たれる。

## 影響

- **Schema 掃除**: provenance dict が 1 key (`sanitized`) 減、source_type enum が 2 値減。77 件 × ~15 byte ≒ 1 KB 回収。enum 削減は runtime 上の利得はないが認知負荷を下げる。
- **Security 姿勢は不変**: MINJA 級攻撃に対する主防御 (Model B quarantine) は影響を受けない。唯一 distill に到達する外部入力経路 (直接返信 / mention) の secondary defense (`external_reply` trust `0.55`) はそのまま。外部 post 本文は distill に一度も到達していないので、使われなかった enum を削除しても運用は変わらない。
- **ADR-0021 の narrative 是正**: MINJA defense 書き換えで audit trail が正確になる。紙上でしか動いていなかった trust-weighting を読者が推測する余地をなくす。
- **Load 後方互換**: `provenance.sanitized` を含む legacy file は clean に load される (key は silent に strip)。rollback は既存の `cp knowledge.json.bak.<ts> knowledge.json` 経路。
- **Migration は net-reductive**: 本 ADR 後に `migrate-patterns` を走らせると `knowledge.json` は入力より 1 key × 77 件分小さくなる。
- **Test surface 縮小**: `external_post` / `user_input` / `sanitized` への fixture 参照を削除、strip 検証用 migration test を 1 件追加。
- **スコープ外**: 本 ADR は (a) `source_episode_ids` / `pipeline_version` / `valid_from` が passive (書かれるが挙動経路で読まれない) 問題、(b) `trust_score` が本番 91.5% が migration default 集中している問題、(c) retrieval scoring が `distill-identity` / `amend-constitution` CLI からしか呼ばれない問題、を扱わない。それぞれ別 ADR / 非 ADR タスクで対応する。

## キーインサイト

ADR-0021 は defensive surface として source_type 6 値 + sanitize flag を宣言した。audit が示したのは、これらの schema 要素が守ろうとしていた脅威は既に構造的防御 (summarize 境界 quarantine + llm.py の upstream sanitize) で覆われていたということ。schema 要素は間違っていたのではなく、**既に成立している構造と冗長だった**。撤回で実際の防御が可視化される: MINJA は distill が何を LLM に渡すかで防がれており、distill が事後に何という label を書くかでは防がれていない。

このパターンは ADR-0028 と通底する: per-turn retrieval system から借用した schema は agent のアーキテクチャが要求する範囲を超えて走ることがある。schema を構造に合わせて剪定すべきで、逆ではない。

## 参照

- Audit report: [evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md) (§2.D1, §2.D2, §2.D3, §6)
- 撤回対象セクション: ADR-0021 L31-32, L34, L47-48, L52, L133
- 併走する撤回: ADR-0028 (forgetting / feedback)
- 構造的防御の参照: ADR-0007 (security boundary model), ADR-0015 (1 エージェント 1 外部アダプタ)
