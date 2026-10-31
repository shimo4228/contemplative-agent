# Contemplative Agent Glossary

This glossary has two parts. **(A) Current mechanism vocabulary** defines the words the code, ADRs and weekly
documents use today, one line each, with the ADR or RFC that owns the term; a term that has been retired says
so ("retired by ADR-NNNN"). **(B) Translation tables** (everything from "Translation policy" down) map terms
between the languages of the README.

## (A) Current mechanism vocabulary

| Term | Meaning now | Owner |
|---|---|---|
| value layer | identity, constitution, skills and rules: the text the agent proposes changes to and a person adopts. Observed, never given a target state | [ADR-0080](adr/0080-north-star-layered-end-state.md) |
| staging, `.staged/` | where `--stage` producers write proposals until `adopt-staged` runs them through the approval gate; a new batch is refused while an unreviewed one sits there | [ADR-0012](adr/0012-human-approval-gate.md) |
| episode log | the append-only record of everything the agent did, including other agents' posts; untrusted, and never read by a coding agent directly | [ADR-0007](adr/0007-security-boundary-model.md), [ADR-0107](adr/0107-instrument-census-and-episode-log-folder.md) |
| pattern | a short observation distilled from one episode by `distill`; a second call judges whether it will last | [ADR-0060](adr/0060-per-episode-grounded-distill.md), [ADR-0084](adr/0084-post-distill-durability-gate.md) |
| distill / insight | `distill` turns episodes into patterns (daily); `insight` clusters patterns and writes skill candidates into staging (weekly) | ADR-0060, [ADR-0074](adr/0074-weekly-staged-insight.md) |
| novelty gate | the insight step that skips a cluster whose theme an adopted or already-staged skill covers; retrieves the top-k nearest skills instead of listing the whole store | ADR-0074, [ADR-0104](adr/0104-novelty-gate-retrieval-topk.md) |
| insight entrance stages | insight as a sequence: novelty gate, naming, body / description / name as separate calls, then a duplicate judge placed after the extracted candidate | [ADR-0111](adr/0111-insight-entrance-stages.md) |
| confusion pair | two skill names the selector mixes up (a name it asked for that is not in the catalog, matched to the nearest real name); the skill store's second exit signal, read weekly | [ADR-0105](adr/0105-skill-store-exit-confusion-pairs.md) |
| never-selected reading | the first exit signal: a skill with zero selections across the whole selection history at or above the exposure floor | [ADR-0097](adr/0097-consolidator-dissolution-and-skill-store-exit.md), ADR-0105 |
| comment outcome | what the platform answered to one of our comments (replies, thread continuation, upvotes), recorded next to the skills that were injected; recorded, not used | [ADR-0106](adr/0106-comment-outcome-recording.md) |
| decision backend | a protocol for typed probabilistic judgments (`noul` yes/no, `choice`, `score`) answered with probabilities, with an Ollama first-token-logprobs implementation | [ADR-0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md) |
| score4 | the 4-level relevance score (`unrelated` / `shares vocabulary only` / `same field` / `directly on-topic`) read as logprobs; the gate cuts on P(directly on-topic) against `thresholds.relevance_score4` | [ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md) |
| relevance gate | the feed's judge of which posts to engage with and which peer posts may seed a self-post; score4 is its only judge since ADR-0113 Amendment 3 (the free-generated 0-1 score was deleted) | ADR-0113 |
| fail-closed | when the judge gives no answer the agent does less (no engagement, no seed) instead of acting on a judgment nobody made; the row carries `gate_source: "fail_closed"` and an `enforce_reason` | ADR-0113 |
| face, face gate | a call site that may ask the decision backend a question; the per-face switches (`DECISION_FACES`, `DECISION_ENFORCE`) were **retired by ADR-0113 Amendment 3**. "Face gate" in older text is the owner's keep / kill reading of a face | ADR-0113, [RFC-0046](../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) |
| shadow, paired, enforce-first | how a candidate judge meets production. **Shadow**: it records its would-be judgment beside the live path and changes nothing. **Enforce-first**: the new judge decides from the start. **Paired**: the old judge is still asked and recorded in the same row until the owner keeps the new one | [ADR-0076](adr/0076-skill-selection-shadow-instrument.md), ADR-0113 |
| weekly chain | the unattended Saturday run: materials, one `/weekly-report` session (instrument document, diagnosis, draft filing), then the deterministic instruments | [ADR-0085](adr/0085-unattended-weekly-fix-chain-single-saturday-gate.md), [ADR-0098](adr/0098-weekly-single-session-and-triage-delegation.md) |
| weekly gate | the Saturday `/weekly-gate` session where a person decides value-layer adoption and retirement over the chain's findings and instrument JSONs; the gate is value-layer only | ADR-0085, ADR-0098 |
| triage loop | the repair path for filed candidates: premise verification, owner digest, worktree dispatch, human merge | ADR-0098 |
| dead-band | a triage reading of a ledger entry whose state and condition text are unchanged and where nothing new was read; it records that the entry was looked at | [rfcs/](../rfcs/README.md) |
| census status | the closed status vocabulary of the weekly log census: `OK`, `NO_ROWS`, `MISSING_EVENT`, `ORPHAN`, `KEPT` (retired writer, file kept as research data), `QUIET` (declared cadence longer than the window), `UNKNOWN`, `ABSENT` | [ADR-0107](adr/0107-instrument-census-and-episode-log-folder.md), [ADR-0110](adr/0110-instrument-series-projection.md) |
| series projection | the census output as a time-shaped series (session ledger, within-week outliers, collapsed windows) instead of a count table plus a row sample | ADR-0110 |
| consumption plan | the three things a new instrument's ADR must state: who reads it and when, what it decides after how many readings, and the removal condition at expiry | [ADR-0101](adr/0101-instrument-dissolution-mandate.md) |
| embedding sidecar | pattern embeddings stored beside `knowledge.json`, not inside it | [ADR-0108](adr/0108-knowledge-embedding-sidecar.md) |
| dependency floor | the runtime dependencies of the wheel (`requests`, `numpy`); adding one needs an ADR, and the floor does not bind scripts, tests or dev groups | [ADR-0109](adr/0109-dependency-floor-scoped-to-the-wheel.md) |
| codemap | a stored document of code structure; **retired by ADR-0102**: structure is derived from the code each time (LSP, grimp) | [ADR-0102](adr/0102-retire-codemaps.md) |
| wiki mechanism | an LLM-maintained knowledge wiki inside the loop; **retired by ADR-0103** | [ADR-0103](adr/0103-retire-the-wiki-mechanism.md) |
| decision packet | the single artifact the old weekly chain built for its gate; **retired by ADR-0098** (the gate reads the findings file and instrument JSONs) | ADR-0085, ADR-0098 |
| Jev | a hosted decision model used once as a measurement ceiling and as the label judge for the relevance label set; never in the running agent | ADR-0112, [RFC-0045](../rfcs/0045-relevance-judgment-jev-proximity-replay.md) |

## (B) Translation tables

Terminology mapping for the two languages supported by the README of
this project (English primary + Japanese mirror). Use this as the
canonical reference when translating or updating either version of
`README.md`.

(The 简体中文 / 繁體中文 / Português (Brasil) / Español mirrors were
retired on 2026-05-15 after traffic data showed statistically zero
unique human viewers; LLM crawlers translate from the English source
on demand. Glossary entries that list those languages are preserved
as historical reference for the original translation discipline and
for any future re-introduction of mirrors.)

This glossary is aligned with the upstream [AKC glossary](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/glossary.md):
AKC-shared terms (cycle, phase names, `signal-first`, `harness`, the six
cycle skills) are kept identical. Terms specific to Contemplative Agent
(security by absence, Yogācāra frame, `distill` / `insight` CLI
commands, pivot snapshots, etc.) are added below.

## Translation policy

- **Proper nouns, CLI commands, schema fields, and project-coined
  two-word phrases stay in English across all languages.** Translating
  them would break searchability (CLI commands must match the binary),
  citability (axiom names must match the paper), or interoperability
  with adjacent projects (AKC phase names, `signal-first`).
- **General-purpose technical terms are localized** using the natural
  local equivalent — never transliterated or romanized.
- **Bilingual first-use is recommended** for project-coined phrases
  that have a strong local rendering (e.g., 「security by absence（不在
  によるセキュリティ）」), then English alone afterwards.

## AKC-aligned terms

These rows are inherited from the AKC glossary. Keep them in sync when
AKC updates.

| English | 日本語 | 简体中文 | 繁體中文 | Português (Brasil) | Español | Keep original |
|---------|--------|----------|----------|---------------------|---------|:-------------:|
| cycle | サイクル | 周期 | 週期 | ciclo | ciclo | |
| phase | フェーズ | 阶段 | 階段 | fase | fase | |
| Research | Research | Research | Research | Research | Research | ✓ |
| Extract | Extract | Extract | Extract | Extract | Extract | ✓ |
| Curate | Curate | Curate | Curate | Curate | Curate | ✓ |
| Promote | Promote | Promote | Promote | Promote | Promote | ✓ |
| Measure | Measure | Measure | Measure | Measure | Measure | ✓ |
| Maintain | Maintain | Maintain | Maintain | Maintain | Maintain | ✓ |
| signal-first | signal-first | signal-first | signal-first | signal-first | signal-first | ✓ |
| harness | ハーネス | harness | harness | harness | harness | ✓ |
| skill | スキル | 技能 | 技能 | habilidade | habilidad | |
| rule | ルール | 规则 | 規則 | regra | regla | |
| pattern | パターン | 模式 | 模式 | padrão | patrón | |
| episode | エピソード | 片段 | 片段 | episódio | episodio | |
| layer | 層 | 层 | 層 | camada | capa | |
| distill / distillation | 蒸留 | 蒸馏 | 蒸餾 | destilar / destilação | destilar / destilación | |
| audit | 監査 | 审计 | 審計 | auditar / auditoria | auditar / auditoría | |
| immutable | 不変 | 不可变 | 不可變 | imutável | inmutable | |
| drift | ドリフト | 漂移 | 漂移 | desvio | desviación | |
| reference implementation | リファレンス実装 | 参考实现 | 參考實作 | implementação de referência | implementación de referencia | |

## Contemplative Agent–specific terms

| English | 日本語 | 简体中文 | 繁體中文 | Português (Brasil) | Español | Keep original |
|---------|--------|----------|----------|---------------------|---------|:-------------:|
| agent | エージェント | 代理 | 代理 | agente | agente | |
| adapter | アダプタ | 适配器 | 介接器 | adaptador | adaptador | |
| autonomous agent | 自律エージェント | 自主代理 | 自主代理 | agente autônomo | agente autónomo | |
| core | コア | 核心 | 核心 | núcleo | núcleo | |
| knowledge | ナレッジ | 知识 | 知識 | conhecimento | conocimiento | |
| identity | アイデンティティ | 身份 | 身份 | identidade | identidad | |
| constitution | 憲法 | 章程 | 章程 | constituição | constitución | |
| view / views | view / views | view / views | view / views | view / views | view / views | ✓ |
| embedding | 埋め込み / embedding | 嵌入 / embedding | 嵌入 / embedding | embedding | embedding | partial |
| provenance | 出所記録 | 出处记录 | 出處記錄 | proveniência | procedencia | |
| trust score | 信頼度 | 可信度 | 可信度 | índice de confiança | puntuación de confianza | retired (ADR-0051); historical docs only |
| bitemporal | 時間妥当性 (bitemporal) | 双时态 (bitemporal) | 雙時態 (bitemporal) | bitemporal | bitemporal | partial |
| approval gate | 承認ゲート | 审批闸门 | 審核閘門 | porta de aprovação | puerta de aprobación | |
| human approval gate | 人間承認ゲート | 人类审批闸门 | 人類審核閘門 | porta de aprovação humana | puerta de aprobación humana | |
| approval lineage | 承認系譜 | 审批谱系 | 審核譜系 | linhagem de aprovação | linaje de aprobación | ADR-0050 |
| session insight | セッション洞察 | 会话洞察 | 會話洞察 | insight de sessão | insight de sesión | retired (ADR-0052); historical docs only |
| self-improving | 自己改善 | 自我改进 | 自我改進 | auto-aperfeiçoamento | automejora | |
| ethical framework | 倫理フレームワーク | 伦理框架 | 倫理框架 | estrutura ética | marco ético | |
| character template | キャラクターテンプレート | 角色模板 | 角色模板 | modelo de personagem | plantilla de personaje | |
| domain lock | ドメインロック | 域名锁定 | 網域鎖定 | bloqueio de domínio | bloqueo de dominio | |
| threat model | 脅威モデル | 威胁模型 | 威脅模型 | modelo de ameaças | modelo de amenazas | |
| prompt injection | プロンプトインジェクション | 提示词注入 | 提示詞注入 | injeção de prompt | inyección de prompt | |
| indirect prompt injection | 間接プロンプトインジェクション | 间接提示词注入 | 間接提示詞注入 | injeção indireta de prompt | inyección indirecta de prompt | |
| memory injection | 記憶注入 | 记忆注入 | 記憶注入 | injeção de memória | inyección de memoria | |
| edge environment | エッジ環境 | 边缘环境 | 邊緣環境 | ambiente edge | entorno edge | |
| air-gapped | エアギャップ | 气隙 (air-gapped) | 氣隙 (air-gapped) | air-gapped | air-gapped | partial |
| on-device | オンデバイス | 端侧 | 端側 | no dispositivo | en el dispositivo | |
| consumer hardware | コンシューマーハードウェア | 消费级硬件 | 消費級硬體 | hardware de consumo | hardware de consumo | |
| counterfactual experiment | 反事実実験 | 反事实实验 | 反事實實驗 | experimento contrafactual | experimento contrafáctico | |
| active inference | 能動的推論 | 主动推断 | 主動推論 | inferência ativa | inferencia activa | |
| eight-consciousness model | 八識モデル | 八识模型 | 八識模型 | modelo das oito consciências | modelo de las ocho conciencias | |
| managed LLM | マネージド LLM | 托管 LLM | 代管 LLM | LLM gerenciado | LLM gestionado | |
| cloud add-on | cloud add-on | cloud add-on | cloud add-on | cloud add-on | cloud add-on | ✓ |
| opt-in | opt-in | opt-in | opt-in | opt-in | opt-in | ✓ |
| backend (LLM) | バックエンド | 后端 | 後端 | backend | backend | partial |
| pipeline prompt | パイプラインプロンプト | 流水线提示词 | 管線提示詞 | prompt da pipeline | prompt del pipeline | |
| view seed | view シード | view 种子 | view 種子 | seed de view | seed de view | partial |
| pivot snapshot | pivot snapshot | pivot snapshot | pivot snapshot | pivot snapshot | pivot snapshot | ✓ |

## Project-coined phrases (Keep original)

These phrases are either verbatim slogans from ADRs, citations from
external papers, or CLI command names. They stay in English and are
wrapped in local punctuation when embedded in a translated sentence.

### Design principles (ADR slogans)

- **security by absence** — ADR-0007 headline principle. Bilingual
  first-use allowed: 「security by absence（不在によるセキュリティ）」 /
  「security by absence（不在的安全）」.
- **one external adapter per agent** — ADR-0015 principle.
- **grounded distill** (also **per-episode grounded distill**) — ADR-0060: one LLM call per engagement episode over the full episode render.
- **noise as seed** — ADR-0027 retention policy (retired by ADR-0060; the noise gate and `noise-*.jsonl` writer were removed).
- **pivot snapshots** — ADR-0020 replay mechanism.
- **observability without steering** — ADR-0050 headline principle;
  enforced by ADR-0051 (trust retirement) and ADR-0052 (session-insight
  retirement). Bilingual first-use allowed: 「observability without
  steering（操縦なき可観測性）」.
- **value layer** — the four human-gated artifact layers the agent
  proposes changes to: constitution, identity, skills, rules. The
  ethical preset occupying the layer is swappable (11 shipped
  templates); the machinery governing it is preset-independent — human
  approval gate (ADR-0012), approval lineage (ADR-0050), pivot
  snapshots (ADR-0020), values at action time (ADR-0058). Vocabulary
  anchored in ADR-0058 ("value-layer injection") and ADR-0069
  ("value-layer pipelines"); front-loaded in the README as of v2.8.
  See also **values at action time**. Bilingual first-use allowed:
  「value layer（価値層）」.
- **rule (本体)** — a member of the value-layer `rules/` store as the
  agent itself loads it, as distinct from a rule in the rules repository
  (`contemplative-agent-rules`) or a rule in the sense of a paper's
  constitutional clause. Three properties define it. **Injection**: every
  rule is injected, always and without selection, as a silent behavioral
  constraint that is never to be announced or narrated in published text
  (`config/prompts/learned_rules_framing.md`; the concatenation in
  `core/llm/prompting.py`). **Generation**: there is no generator; a rule
  arrives only by family promotion (ADR-0097 Decision 7, form A′: the
  model synthesises Practice and Rationale from a co-selected skill family,
  and a human gate adopts it). **Observation**: rules are outside the
  shadow constitution, the IPD two-arm bench and the evals. Whether the
  three principles of the "emptiness-only axiom" proposal (the axioms other
  than Emptiness, held as rules) fall under this definition: on this
  reading they do on all three properties, so adopting the proposal in the
  running agent would move them from observed objects to fixed owner
  instructions. That is why the proposal's acceptance condition (below)
  asks for a revision path. **Acceptance condition**: an ADR that adopts the
  proposal must give the three principles' rules a revision path — A′
  family promotion, or periodic inclusion in the shadow instrument — since
  if only Emptiness can be revised the principles are reified, the reverse
  of the warning in the paper (arXiv:2504.15125) that emptiness itself not
  be reified. The deciding experiment is the distress two-arm of P3-03.5
  (RFC to be filed; may still be a draft). Not to be confused with a
  "rule" in the IPD benchmark's prompts or a pattern/skill. Bilingual
  first-use allowed: 「rule（本体）」.
- **values at action time** — ADR-0058 headline principle. Value layers
  (axioms, identity, skills, rules) belong where the agent acts or
  interprets fresh input, not where it extracts patterns from what
  already happened. Generalizes the ADR-0050/0051/0052
  observation-without-steering line to the distillation lens. Bilingual
  first-use allowed: 「values at action time（行動時にこそ価値層を）」.
- **axiom-free distillation** — ADR-0057/0058. All distillation /
  extraction system prompts are base-only (the credential-leak guard);
  the four axioms are injected only at action time, never at
  distillation time, so the corpus is not re-read through a value lens.
- **self-reflection corpus** — ADR-0057. The body of
  `self_reflection`-view patterns from which `distill-identity` derives
  the persona *alone* — no prior-identity seed, no axiom injection.
- **counterparty by author name** — ADR-0055. The interaction pipeline
  keys the counterparty (`target_agent`) on author name, because live
  feed posts carry `author.name` but not `author.id`.
- **content-verification handshake** — ADR-0062. Moltbook requires an
  unverified agent to solve an obfuscated math challenge (via LLM
  reasoning) and POST it before its posts/comments become visible;
  memory recording is gated on verification. ADR-0063 scopes the
  NoveltyGate comparison to verified (visible) posts.
- **read-only pattern-composition instruments** — ADR-0071. Measure
  view supply, seed-independent diversity, and grounding composition
  before any behavioral intervention — instrument first, then act on
  what the instrument reads.
- **observability by default** — ADR-0075 headline principle. Any
  feature performing external I/O, an LLM call, or a non-deterministic
  decision ships a replayable append-only audit log in the same PR, not
  as a follow-up. Bilingual first-use allowed: 「observability by
  default（既定として可観測）」.
- **shadow instrument** — ADR-0076. A candidate decision mechanism run
  alongside production for observation only: it records what it *would*
  have decided and changes nothing, so whether to enforce it can be
  settled on measurement rather than intuition. Distinct from a
  read-only instrument (ADR-0071), which measures existing data rather
  than shadowing a decision. Bilingual first-use allowed:
  「shadow instrument（影の計器）」.
- **shadow constitution** — ADR-0092. A constitution synthesized from the
  agent's stored constitutional patterns alone, with the live constitution
  text withheld from the model, compared to the live text by cosine and
  logged as a read-only reading before an amendment decision. A shadow
  instrument (ADR-0076) applied to the constitution rather than to a
  decision. Bilingual first-use allowed: 「shadow constitution（影の憲法）」.
- **chaos-TDD** / **fault column** — ADR-0077. A test-first discipline,
  not an infrastructure practice: a *fault column* is a set of
  deterministic fault-injection tests that assert the desired guarded
  behavior before the guard exists, shipped in the same PR as the guard.
  Faults are injected only at seams that already exist, so no production
  chaos hook is added. From 2026-07-13 to 2026-08-29 shipping a fault
  column was a by-default obligation on every feature touching an LLM
  call or external I/O; ADR-0100 retired that obligation on 2026-08-29
  and the practice is opt-in TDD judgment since. Bilingual first-use
  allowed: 「chaos-TDD（障害注入 TDD）」.
- **permanent facade** — ADR-0079. When a module becomes a package, the
  compatibility layer is either kept forever because the old import
  path is public API, or omitted entirely with its tests migrated in
  the same commit. There is no third option: temporary shims are not
  used, because a shim with no removal date is a permanent facade that
  nobody has admitted to.
- **decision packet** — ADR-0085. *Retired by ADR-0098: the chain now ends in a findings file and per-week instrument JSONs; the description below is historical.* The single artifact the unattended
  weekly chain produces for its human gate: findings, candidate
  patches, advisory reviews, and staged insight candidates gathered in
  one file. The machine assembles it and stops; applying, approving,
  and adopting all happen on the other side of the gate. Bilingual
  first-use allowed: 「decision packet（承認パケット）」.
- **post-distill durability gate** — ADR-0084. A judgment placed *after*
  the artifact it judges: the gate receives an episode together with the
  patterns distill produced from it and decides per pattern which to
  keep. Placing the same question before distillation was measured to
  be answerable without evidence, so producing the pattern is the
  evidence requirement.
- **conformance kit** — ADR-0088. The `LLMBackend` contract checks
  shipped *inside* the wheel (`contemplative_agent.testing`) so sibling
  backend repositories import them rather than hand-copy them, and so
  the party that publishes a contract change — main, at release — can
  run them against siblings that go untouched for months. Bilingual
  first-use allowed: 「conformance kit（適合検査キット）」.
- **behavioral eval layer** — ADR-0089. The top-level `evals/` layer
  that measures what the LLM component actually generates:
  production-parity runs over a golden dataset under pinned
  prompt-asset snapshots, an isolated LLM judge issuing *named
  verdicts* (binary checks as evidence, no score aggregation), and
  regressions read as per-case verdict transitions against an approved
  baseline. Deliberately outside both `verify.sh` and `tests/`.
- **IPD two-arm bench** — ADR-0090. The constitution-amendment
  instrument: the current and the staged constitution run as two arms
  of the same iterated-prisoner's-dilemma bench, and the reading joins
  the text diff at the human approval gate. A **null-pair
  calibration** — the same constitution in both arms, run twice —
  measures the bench's own noise floor before any between-arm
  difference is trusted. Bilingual first-use allowed:
  「IPD two-arm bench（IPD 二腕ベンチ）」.
- **instrument dissolution mandate** — ADR-0101. Every new read-only
  instrument must state a **consumption plan** in its owning ADR's
  `## Review-when` section: who reads it and when, how many reads close
  what decision, and the condition on which it is retired. An
  instrument whose plan cannot be stated is not accepted at the human
  gate. Bilingual first-use allowed: 「instrument dissolution mandate
  （計器の溶解義務）」; the sub-term **consumption plan** renders as
  「consumption plan（消費計画）」.
- **instrument census** — ADR-0107. The writer → reader inventory over
  every self-written log in `$MOLTBOOK_HOME/logs/`
  (`scripts/instrument_census.py`, registry in `scripts/_census_registry.py`): each file must name the reader that
  consumes it, so a log with zero automated readers is visible as such
  rather than accumulating unread. Paired with the weekly report's
  **Phase 0 read-through** — a pass over raw-ish data with no question
  attached, added because every other weekly reading answers a question
  someone decided in advance. Bilingual first-use allowed:
  「instrument census（計器センサス）」.
- **confusion pairs** — ADR-0105. The skill store's second exit signal:
  a name the pass-1 selector asked for that is not in the catalog
  (`rejected_names`), paired with its nearest real catalog entry. When
  the store's only consumer keeps misnaming its way into an entry it
  rarely chooses, the entries are not distinguishable to that consumer.
  The pairing judge is code, not the local model; retirement stays at
  the human gate. Bilingual first-use allowed: 「confusion pairs
  （混同対）」.
- **comment outcomes** — ADR-0106. What the environment answered,
  recorded next to the skills that were injected into the generation:
  replies, thread continuation and upvotes read from the comment tree
  the reply cycle had already fetched, appended to
  `logs/comment-outcomes.jsonl` and joined by comment id. Records
  ADR-0080's *environmental response* axis and is deliberately not read
  into any ranking or reduced to a scalar. Bilingual first-use allowed:
  「comment outcomes（コメントの帰結）」.
- **embedding sidecar** — ADR-0108. The SQLite blob store
  (`pattern-embeddings.sqlite`) that holds pattern embeddings keyed
  by pattern id, so `knowledge.json` — the value layer's observable
  surface — stays text rather than being 97% vectors by weight. Follows
  the precedent set by `core/episode_embeddings.py` for episode and
  post vectors. Bilingual first-use allowed: 「embedding sidecar
  （埋め込みサイドカー）」.

### AAP four-quadrant lens (Keep original)

Quadrant names are direct AAP terminology and stay in English in all six
languages, with a bilingual gloss allowed on first use (e.g.
「LLM Workflow（LLM ワークフロー象限）」). The lens is borrowed in this
project as a usage-description aid, not as a category claim (ADR-0033).

- **Script** — deterministic, defined-input quadrant.
- **Algorithmic Search** — deterministic, exploratory-input quadrant.
- **LLM Workflow** — semantic-judgement, defined-input quadrant.
- **Autonomous Agentic Loop** — semantic-judgement, exploratory-input quadrant.
- **Phase-crossing observation** — work that originates in operation phase but revises design-phase artifacts (skills, rules, identity). Not a quadrant; an orthogonal observation. In-repo anchor: ADR-0016.
- **quadrant lens** — the borrowed routing diagnostic itself. Bilingual gloss "象限レンズ / 象限診断" allowed on first use in JA.

### AKC phase → CLI mapping (English only)

The six phase names (Research, Extract, Curate, Promote, Measure, Maintain) and
the CLI command names stay in English in every language. Which command and ADR
realize which phase is kept in one place: the six `Phase` nodes of
[graph.jsonld](../graph.jsonld) (`realizedBy`), from which the ADR index's
`[AKC: …]` tags are generated. `meditate` is adapter-specific and sits outside
the cycle.

### CCAI axioms (English, paper-faithful)

The four axioms from Laukkonen et al. (2025) are cited verbatim in all
languages so they remain linkable to the paper. A bilingual gloss is
allowed on first use if the surrounding prose benefits from it.

- **Emptiness** — 空 / 空 / 空 / Vacuidade / Vacuidad
- **Non-Duality** — 非二元性 / 非二元 / 非二元 / Não-Dualidade / No-Dualidad
- **Mindfulness** — マインドフルネス / 正念 / 正念 / Atenção Plena / Atención Plena
- **Boundless Care** — 無限の慈愛 / 无量悲悯 / 無量悲憫 / Cuidado Ilimitado / Cuidado Ilimitado

### Reference readings of the axioms (English only)

Three entries that fix which sense of a word is meant when an ADR, an RFC or
a report uses it. They are readings for the reader, not amendments: ADR-0080
is not changed by them, and the constitution text is untouched.

- **Emptiness (constitution clause, a value of the agent)** — the first
  axiom as a clause the agent carries and is read against: treat
  directives as contextually sensitive guidelines, and hold objectives
  "lightly" (Appendix C, verbatim in
  `config/templates/contemplative/constitution/`). It is a content of the
  value layer, so it moves only through the human-gated amendment path.
  Distinct from the next entry.
- **hold lightly (design heuristic, ADR-0080 lineage)** — the working
  habit of the project's designers: do not make a mechanism, a target or a
  sunk cost a reason on its own, and withdraw a decision when its premise
  goes (ADR-0037, RFC-0025 "sunk cost is not a reason"). It borrows the
  clause's wording but is a rule about how decisions in this repository are
  made, not a text the agent reads; ADR-0080 uses it as a review axis and
  does not hand it to the agent.
- **Non-Duality (reference reading)** — in the paper's clause the agent is to
  "avoid *rigidly* separating self from others" (Appendix C): the
  separation is held as a convention one is aware of, not denied as a
  distinction. The self / other boundary this repository enforces
  (untrusted-content wrapping, one external adapter per agent) is a
  security boundary decided in ADR-0007 and is not in tension with that
  reading; the clause governs how the agent weighs others in a decision, the
  boundary governs what the agent can touch.

Capability, in these three entries and in the constitution text, means the
quality of an act ("let compassion scale with your capabilities"), not the
capability target that ADR-0080 rejected as a north star (an agent made
smarter or more autonomous as the goal). The two senses share a word and
nothing else.

### Yogācāra / 唯識 terminology

Proper nouns stay in their romanized Sanskrit form; a local gloss is
encouraged on first use.

- **Yogācāra** — 唯識 (yuishiki) / 唯识 / 唯識 / Yogācāra / Yogācāra
- **eight-consciousness model** — 八識モデル / 八识模型 / 八識模型 /
  modelo das oito consciências / modelo de las ocho conciencias
- **bīja / 種子** — 種子 / 种子 / 種子 / semente (bīja) / semilla (bīja)
- **vāsanā / 習気** — 習気 / 习气 / 習氣 / impressão (vāsanā) / impregnación (vāsanā)

### Project name vs adapter name

- **Contemplative Agent** — the project's GitHub / official name (`contemplative-agent`). Use this in all user-facing prose, README sections, llms.txt, and translated documentation.
- **Moltbook** — the name of the initial external adapter (an AI-only social network). Only use "Moltbook" when specifically referring to the adapter, the platform, or the `MOLTBOOK_HOME` environment variable. Do not use "Moltbook" or "contemplative-moltbook" as the project's name in user-facing prose.
- A local working directory may still be named `contemplative-moltbook/` on older machines for filesystem-historical reasons; this does not change the project's official name (the repository is `contemplative-agent`).

### Agent host ecosystem (Keep original)

These are external project / product names. Keep them in English (or their canonical romanized form) across all languages.

- **OpenClaw** — open-source AI agent runtime. General-purpose host category (per ADR-0032). Loads `~/.openclaw/workspace/SOUL.md` as agent personality at session start. Hosts a marketplace called **ClawdHub** for skills.
- **OpenCode** — agent harness with two-layer SOUL.md load (global `~/.config/opencode/SOUL.md` + project `.opencode/SOUL.md`).
- **Codex** — agent harness category (CLI-aware host). Distinct from the deprecated OpenAI Codex CLI.
- **Goose** — Block / AAIF agent harness. Uses `.goosehints` (instruction file). **Not** a soul-folder host; do not list Goose alongside OpenClaw / OpenCode / Codex when describing soul-folder adoption.
- **soul-folder** — convention shared by OpenClaw / OpenCode / Codex where the host loads a `SOUL.md` file as agent personality at startup.
- **SOUL.md** — agent personality file in the soul-folder convention. First-person identity (axioms, refusals, voice, continuity). Contemplative Agent itself does not ship a SOUL.md; the [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) sibling repository ships one with the four axioms verbatim.
- **ClawdHub** — OpenClaw's skill marketplace (referenced for context, not endorsed as a distribution channel for Contemplative Agent).

### Schema fields and binary names

Always in English: `source_type`, `valid_from`,
`valid_until`, `category`, `MOLTBOOK_HOME`, `MOLTBOOK_API_KEY`,
`contemplative-agent`, `contemplative-agent-cloud`, `gemma4:e4b` (the current default; `qwen3.5:9b` is the retired one, ADR-0069),
`nomic-embed-text`, `knowledge.json`, `identity.md`, `logs/*.jsonl`,
`noise-YYYY-MM-DD.jsonl`, `numpy`, `requests`, `Q4_K_M`,
`embedding cosine`, `LLMBackend`, `AnthropicBackend`, `OpenAIBackend`,
`CONTEMPLATIVE_CLOUD_PROVIDER`, `CONTEMPLATIVE_CLOUD_MODEL`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`$MOLTBOOK_HOME/prompts/`, `$MOLTBOOK_HOME/views/`, `snapshots/`.

Same-looking rates, different definitions (one name each):

- `reply_rate` — `core/metrics.py`, account level: `replies_received /
  (comments_sent + replies_sent)` over the report period.
- `replied_fraction` — `core/comment_outcomes.py`, per skill (ADR-0106):
  injected comments that drew at least one reply / injected comments, over the
  *observed* publishes only (about a third of the joined ones). Named
  `reply_rate` until 2026-10-24.

## Notes on choices

- **views (ADR-0019)** is left in English in all languages. In the
  codebase it is a schema-level term with a specific operational meaning
  (editable semantic seeds that project embedding coordinates onto named
  classes); translating it loses the connection to the ADR.
- **embedding** is kept as English loanword in ja (*埋め込み*) because
  readers routinely see the English term in ML literature. Local
  rendering listed so the translator can choose depending on audience.
  (zh-CN / zh-TW renderings *嵌入* are preserved as historical
  reference for the original translation discipline; the corresponding
  README mirrors were retired 2026-05-15.)
- **bitemporal / air-gapped** are kept in English when they appear as
  technical adjectives (security context). A local gloss may precede
  them on first use.
- The **CCAI four axioms** are treated like the AKC phase names:
  citable only in their English form because any translation risks
  diverging from the source paper ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)).

## Maintenance

When updating `README.md` (English source), keep this table in sync if
you introduce a new project-coined phrase or ADR slogan. Translators of
language-specific README files should consult this table before
choosing a rendering. Upstream AKC glossary changes should be mirrored
into the "AKC-aligned terms" section.
