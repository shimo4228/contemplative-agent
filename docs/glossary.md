# Contemplative Agent Glossary

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
- **noise as seed** — ADR-0027 retention policy.
- **pivot snapshots** — ADR-0020 replay mechanism.
- **observability without steering** — ADR-0050 headline principle;
  enforced by ADR-0051 (trust retirement) and ADR-0052 (session-insight
  retirement). Bilingual first-use allowed: 「observability without
  steering（操縦なき可観測性）」.
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

- `distill` — Extract (behavioral / constitutional knowledge)
- `distill-identity` — Promote (whole-file identity)
- `insight` — Curate (extract skills from patterns)
- `rules-distill` — Promote (skills → rules)
- `amend-constitution` — Curate (constitutional knowledge → constitution)
- `adopt-staged` — Promote (staging → active)
- `meditate` — adapter-specific (meditation simulation)

### CCAI axioms (English, paper-faithful)

The four axioms from Laukkonen et al. (2025) are cited verbatim in all
languages so they remain linkable to the paper. A bilingual gloss is
allowed on first use if the surrounding prose benefits from it.

- **Emptiness** — 空 / 空 / 空 / Vacuidade / Vacuidad
- **Non-Duality** — 非二元性 / 非二元 / 非二元 / Não-Dualidade / No-Dualidad
- **Mindfulness** — マインドフルネス / 正念 / 正念 / Atenção Plena / Atención Plena
- **Boundless Care** — 無限の慈愛 / 无量悲悯 / 無量悲憫 / Cuidado Ilimitado / Cuidado Ilimitado

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
- The local working directory is named `contemplative-moltbook/` for filesystem-historical reasons; this does not change the project's official name.

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
`contemplative-agent`, `contemplative-agent-cloud`, `qwen3.5:9b`,
`nomic-embed-text`, `knowledge.json`, `identity.md`, `logs/*.jsonl`,
`noise-YYYY-MM-DD.jsonl`, `numpy`, `requests`, `Q4_K_M`,
`embedding cosine`, `LLMBackend`, `AnthropicBackend`, `OpenAIBackend`,
`CONTEMPLATIVE_CLOUD_PROVIDER`, `CONTEMPLATIVE_CLOUD_MODEL`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`$MOLTBOOK_HOME/prompts/`, `$MOLTBOOK_HOME/views/`, `snapshots/`.

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
