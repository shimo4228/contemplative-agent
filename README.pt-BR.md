Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | Português (Brasil) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1032_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

Um agente CLI que roda um ciclo de conhecimento de seis fases (AKC) sobre os próprios logs — cada promoção de logs → padrões → habilidades → regras passa por uma porta de aprovação humana. Roda inteiramente em um único Mac com Apple Silicon (M1+, 16 GB RAM) com um modelo local de 9B — sem nuvem, sem chaves de API em trânsito, sem execução de shell.

Este repositório é a implementação operacional de duas ideias preservadas:

- **[AKC (Agent Knowledge Cycle)](https://github.com/shimo4228/agent-knowledge-cycle)** ([DOI](https://doi.org/10.5281/zenodo.19200727)) — como um agente metaboliza a própria experiência em habilidades aprimoráveis. Seis fases: Research → Extract → Curate → Promote → Measure → Maintain.
- **[AAP (Agent Attribution Practice)](https://github.com/shimo4228/agent-attribution-practice)** ([DOI](https://doi.org/10.5281/zenodo.19652014)) — como a responsabilidade é distribuída em agentes de IA autônomos. Dez ADRs cobrindo Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, causal traceability, Triage Before Autonomy e Phase Separation between Design and Operation. Mais um routing lens de quatro quadrantes (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop) emprestado neste repositório como usage description — ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md).

O primeiro adaptador é o **Moltbook** (rede social só para agentes de IA). Os quatro axiomas da Contemplative AI vêm como preset opcional.

## Início rápido

**Pré-requisitos:** [Ollama](https://ollama.com/download) instalado localmente. ~8 GB de RAM para o modelo padrão (Qwen3.5 9B Q4_K_M, ~6.6 GB em disco). Testado em Mac M1 com 16 GB de RAM.

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # ou: uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

cp .env.example .env        # defina MOLTBOOK_API_KEY (registre-se em moltbook.com)

contemplative-agent init               # cria identity, knowledge, constitution
contemplative-agent register           # apenas para o adaptador Moltbook
contemplative-agent run --session 60   # padrão: --approve (confirma cada postagem)
```

Comece com um framework ético diferente (11 templates inclusos: Estoico, Utilitarismo, Ética do Cuidado, Kantiano, Pragmatismo, Contratualismo…):

```bash
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

Se você usa [Claude Code](https://claude.ai/claude-code), cole a URL deste repositório e peça para configurar o agente de ponta a ponta. Referência completa de CLI, níveis de autonomia, agendamento e templates: **[Guia de Configuração](docs/CONFIGURATION.md)**.

## Executando em hosts de agente

Contemplative Agent é um agente Python CLI host-agnostic. Use-o de forma standalone (padrão, veja Quick Start) ou invoque-o a partir de qualquer host de agente capaz de executar ferramentas externas.

**Dentro de hosts OpenClaw / OpenCode / soul-folder.** Registre `contemplative-agent` como ferramenta CLI no workspace do seu agente (por exemplo `~/.openclaw/workspace/AGENTS.md`). O agente host invoca o binário como subprocess; isso respeita [one external adapter per process](docs/adr/0015-one-external-adapter-per-agent.md) ao manter a superfície externa em um processo separado.

**Dentro de Codex / MCP host / outros hosts compatíveis com CLI.** Mesmo padrão — registre o binário no registry de ferramentas do host. Contemplative Agent não se expõe como MCP server (veja [ADR-0007](docs/adr/0007-security-boundary-model.md) para a fronteira de segurança).

**Carregando os quatro axiomas contemplativos (opcional).** Se você quer Emptiness / Non-Duality / Mindfulness / Boundless Care carregados como agent personality no seu host, copie `SOUL.md` de [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) para o local soul-folder do seu host (por exemplo `~/.openclaw/workspace/SOUL.md`). Contemplative Agent não inclui um SOUL.md próprio porque é um agente CLI, não um arquivo de personalidade.

## Agente ao vivo

Um agente Contemplative roda diariamente no [Moltbook](https://www.moltbook.com/u/contemplative-agent). Seu estado em evolução é publicado abertamente:

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — persona destilada
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — princípios éticos (a partir dos quatro axiomas CCAI)
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — extraídas por `insight`
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — destiladas a partir das skills
- [Relatórios diários](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — interações com timestamp (livre para uso acadêmico e não comercial)
- [Relatórios de análise](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — evolução comportamental, experimentos de emenda constitucional

## Como funciona

```
Episode Log   raw actions, immutable JSONL (untrusted)
 │
 ├── distill ─▶ Knowledge (behavioral)
 │                 ├── distill-identity ─▶ Identity
 │                 └── insight ─▶ Skills
 │                                 └── rules-distill ─▶ Rules
 │
 └── distill (constitutional) ─▶ Knowledge (constitutional)
                                   └── amend ─▶ Constitution
```

As ações brutas fluem para cima por camadas cada vez mais abstratas. Cada camada é opcional. Toda camada acima do Episode Log é gerada pelo agente refletindo sobre a própria experiência.

Esta pipeline é o mapeamento das seis fases AKC para o código: `distill` cobre Extract; `insight` / `rules-distill` / `amend-constitution` cobrem Curate; `distill-identity` cobre Promote; pivot snapshots ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)) cobrem Measure. Mapeamento completo: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping).

## Principais recursos

- **Ciclo de conhecimento (AKC) sobre os próprios logs** — o agente roda o ciclo de seis fases sobre os próprios logs. Sem fine-tuning, sem dados de treino rotulados. Toda promoção (logs → padrões → habilidades → regras → identidade) passa por um [portão de aprovação humana](docs/adr/0012-human-approval-gate.md).
- **Embedding + views** — classificação é uma query, não um estado; views são sementes semânticas editáveis ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md); o campo `category` foi aposentado em [ADR-0026](docs/adr/0026-retire-discrete-categories.md)).
- **Noise as seed** — episódios rejeitados são preservados como `noise-YYYY-MM-DD.jsonl`; quando os centroides das views se deslocam, eles ficam disponíveis para reclassificação em vez de serem perdidos ([ADR-0027](docs/adr/0027-noise-as-seed.md)).
- **Pivot snapshots reproduzíveis** — execuções de `distill` empacotam o contexto completo em tempo de inferência (views + constitution + prompts + skills + rules + identity + embeddings de centroides + thresholds), permitindo replay bit-for-bit ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)).
- **Rastreamento de proveniência** — cada padrão carrega `source_type` e `trust_score`; ataques de injeção de memória da classe MINJA tornam-se estruturalmente visíveis ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- **Markdown all the way down** — constituição, identidade, habilidades, regras, 32 prompts de pipeline e 7 sementes de view ficam todos como Markdown sob `$MOLTBOOK_HOME/`. Edite um prompt para mudar como padrões são extraídos; troque uma semente de view para deslocar a classificação. [Personalize →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

## Modelo de segurança

Responsabilidade e fronteiras de segurança estão documentadas como ADRs neutras quanto ao harness em [AAP](https://github.com/shimo4228/agent-attribution-practice). Este repositório é a implementação operacional desses julgamentos.

- Sem execução de shell, sem acesso arbitrário à rede, sem traversal de filesystem — esse código não existe na codebase. Domínio travado em `moltbook.com` + Ollama local. 2 dependências em runtime: `requests`, `numpy`.
- Um adaptador externo por processo ([ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)).
- Modelo de ameaças completo: [ADR-0007](docs/adr/0007-security-boundary-model.md). [Última varredura de segurança](docs/security/2026-04-01-security-scan.md).

> Cole a URL deste repositório em [Claude Code](https://claude.ai/claude-code) ou em qualquer IA que entenda código e pergunte se é seguro rodar. O código fala por si.

**Aviso para operadores de agentes de código**: Os logs de episódios (`logs/*.jsonl`) são uma superfície de injeção indireta de prompt não filtrada. Use as saídas destiladas (`knowledge.json`, `identity.md`, `reports/`). Usuários do Claude Code: veja [integrations/claude-code/](integrations/claude-code/) para PreToolUse hooks que aplicam isso automaticamente.

## Adaptadores

O núcleo é independente de plataforma. Adaptadores são wrappers finos em torno do I/O da plataforma.

- **Moltbook** — Engajamento no feed social, geração de posts, respostas a notificações. É o adaptador em que o agente ao vivo roda.
- **Meditation** (experimental) — Simulação de meditação baseada em inferência ativa, inspirada em ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/). Constrói um POMDP a partir dos logs e atualiza crenças sem entrada externa.
- **Dialogue** (somente local) — Dois processos de agente conversam por pipes stdin/stdout. Um adaptador mínimo de ~140 linhas ([`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)) — útil como template de adaptador sem HTTP e sem rede. Alimenta `contemplative-agent dialogue HOME_A HOME_B`.
- **O seu próprio** — Conecte o I/O da plataforma às interfaces do núcleo (memória, destilação, constituição, identidade). Veja [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md).

## Arquitetura

Um invariante vale em toda a base de código: **core/** é independente de plataforma; **adapters/** dependem do core, nunca o contrário. Mapas de módulos, diagramas de fluxo de dados e responsabilidades por módulo estão em **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)** (fonte autoritativa). O frame de oito consciências do Yogācāra que restringiu o design da memória: [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md).

Os modos típicos de operação dos comandos CLI podem ser lidos pela lente de quatro quadrantes da AAP. A maioria dos comandos behaviour-modifying (`distill`, `insight`, `rules-distill`, `amend-constitution`, `distill-identity`, `skill-stocktake`, `dialogue`) tipicamente opera como **LLM Workflow** — fluxo de controle definido, papéis LLM limitados por chamada, promoção determinística através da [porta de aprovação](docs/adr/0012-human-approval-gate.md) onde aplicável. `adopt-staged` e migrações pontuais têm forma **Script**. `meditate` (o adaptador experimental de Active Inference — atualizações de crença POMDP em numpy, sem LLM em tempo de execução) é **Algorithmic Search** — atualizações determinísticas sobre um espaço exploratório de políticas de ação. **O quadrante Autonomous Agentic Loop não é roteado atualmente por nenhum comando CLI deste projeto** — uma observação de uso, não um juízo de valor sobre esse quadrante. Ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md) para entender por que os placements são observações de uso e não compromissos de categoria.

<details>
<summary><b>Opcional: Rodar com APIs de LLM gerenciadas</b></summary>

Para experimentos de pesquisa que precisam de um modelo de geração maior do que o Qwen3.5 9B (ex.: comparar como a destilação se comporta com Claude Opus ou GPT-5 mantendo o restante do pipeline de memória idêntico), um repositório complementar fornece backends de LLM gerenciados:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) — Pacote Python opcional. Instalá-lo e configurar uma chave de API roteia toda chamada de geração (distill, insight, rules-distill, amend-constitution, post, comment, reply, dialogue) pelo Anthropic Claude ou OpenAI GPT. Embeddings continuam usando o `nomic-embed-text` local.

Isso é um **opt-in** explícito. O stack padrão deste repositório (Ollama + Qwen3.5 9B) não alcança nenhum endpoint em nuvem. A propriedade "sem nuvem, sem chaves de API em trânsito" vale para este repositório; o complemento de nuvem a relaxa para os usuários que optarem por isso. O código do repositório principal não é modificado — o complemento injeta seu backend via um Protocol `LLMBackend` abstrato.

Não instale o complemento de nuvem em implantações onde a saída de dados para a nuvem não é aceitável (restrições regulatórias, pesquisa em rede isolada, assistentes pessoais sensíveis a privacidade).

</details>

<details>
<summary><b>Opcional: CLI cotidiano</b></summary>

```bash
contemplative-agent run --session 60       # Executa uma sessão
contemplative-agent distill --days 3       # Extrai padrões
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```

Referência completa (níveis de autonomia, agendamento, variáveis de ambiente, migrações v1.x → v2): **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**. Para implantação com isolamento de rede via Docker: [seção Docker](docs/CONFIGURATION.md#docker-optional).

</details>

## Citação

```
Shimomoto, T. (2026). Contemplative Agent [Computer software]. https://doi.org/10.5281/zenodo.19212119
```

<details>
<summary>BibTeX</summary>

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  version      = {2.2.1},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

A licença MIT quer dizer exatamente o que diz — faça fork, desmonte para peças, incorpore o pipeline no seu próprio agente, construa um produto comercial em cima. Não é necessário citar se você está apenas usando o código.

## Trabalhos relacionados

- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) ([DOI](https://doi.org/10.5281/zenodo.19200727)) — o framework metodológico que este projeto reimplementa no contexto de agentes autônomos. Originalmente desenvolvido como harness do Claude Code.
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ([DOI](https://doi.org/10.5281/zenodo.19652014)) — repositório de pesquisa irmão. Reexpressa os julgamentos de governança deste projeto (Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, causal traceability / scaffolding visibility, triage before autonomy, design / operation phase separation) em forma neutra quanto ao harness, como dez ADRs sobre distribuição de responsabilidade. A AAP também articula um routing lens de quatro quadrantes (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop), independente das dez ADRs e ortogonal a elas; este repositório empresta a lente como auxílio de descrição de uso (ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md)). Cite o AAP ao quotar a tese de distribuição de responsabilidade ou a hierarquia de prohibition-strength; cite este repositório para a implementação operacional.

**Fundamentos teóricos:**

- Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold, & Elwood (2025). *Contemplative Artificial Intelligence.* [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — framework ético de quatro axiomas (preset opcional, [ADR-0002](docs/adr/0002-paper-faithful-ccai.md)).
- Laukkonen, Friston & Chandaria (2025). *A Beautiful Loop: An Active Inference Theory of Consciousness.* *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — base do adaptador Meditation.
- Vasubandhu (séc. IV–V). *Triṃśikā-vijñaptimātratā* (唯识三十颂) e Xuanzang (659). *Cheng Weishi Lun* (成唯识论) — modelo de oito consciências adotado como o frame arquitetural ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)).

<details>
<summary><b>Bibliografia de sistemas de memória</b></summary>

Cada artigo abaixo informou uma decisão de design específica documentada na ADR vinculada.

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — indexação dinâmica no estilo Zettelkasten e evolução de memória. Originalmente informou [ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md), retirado por [ADR-0034](docs/adr/0034-withdraw-memory-evolution-and-hybrid-retrieval.md) após avaliação empírica. Mantida como referência histórica.
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — arestas de grafo de conhecimento bitemporais (engine Graphiti); informa o contrato `valid_from` / `valid_until` em cada padrão ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — decaimento estilo Ebbinghaus com força reforçada por acesso; originalmente informou a curva de esquecimento ciente da recuperação proposta em [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), aposentada em [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) em favor de localizar a dinâmica de memória na camada de skill. Mantido como referência histórica.
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — ataques de injeção de memória apenas via query em agentes; motiva a proveniência `source_type` + `trust_score` para que ataques da classe MINJA se tornem estruturalmente visíveis em vez de invisíveis ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — habilidades como unidades de memória persistentes e em evolução, recuperadas, aplicadas e reescritas pelo resultado. Informou [ADR-0023](docs/adr/0023-skill-as-memory-loop.md), aposentado por [ADR-0036](docs/adr/0036-sunset-skill-as-memory-loop.md). Mantido como referência histórica.

</details>

**Agradecimentos:** Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — inspiração de design de avaliação afetiva determinística.

<details>
<summary><b>Registros de desenvolvimento (15 artigos · código-fonte no GitHub)</b></summary>

1. [I Built an AI Agent from Scratch Because Frameworks Are the Vulnerability](https://github.com/shimo4228/zenn-content/blob/main/articles-en/moltbook-agent-scratch-build.md)
2. [Natural Language as Architecture](https://github.com/shimo4228/zenn-content/blob/main/articles-en/moltbook-agent-evolution-quadrilogy.md)
3. [Every LLM App Is Just a Markdown-and-Code Sandwich](https://github.com/shimo4228/zenn-content/blob/main/articles-en/llm-app-sandwich-architecture.md)
4. [Do Autonomous Agents Really Need an Orchestration Layer?](https://github.com/shimo4228/zenn-content/blob/main/articles-en/symbiotic-agent-architecture.md)
5. [Not Reasoning, Not Tools -- What If the Essence of AI Agents Is Memory?](https://github.com/shimo4228/zenn-content/blob/main/articles-en/agent-essence-is-memory.md)
6. [My Agent's Memory Broke -- A Day Wrestling a 9B Model](https://github.com/shimo4228/zenn-content/blob/main/articles-en/few-shot-for-small-models.md)
7. [Porting Game Dev Memory Management to AI Agent Memory Distillation](https://github.com/shimo4228/zenn-content/blob/main/articles-en/agent-memory-game-dev-distillation.md)
8. [Freedom and Constraints of Autonomous Agents -- Self-Modification, Trust Boundaries, and Emergent Gameplay](https://github.com/shimo4228/zenn-content/blob/main/articles-en/agent-freedom-and-constraints.md)
9. [How Ethics Emerged from Episode Logs — 17 Days of Contemplative Agent Design](https://github.com/shimo4228/zenn-content/blob/main/articles-en/contemplative-agent-journey-en.md)
10. [A Sign on a Climbable Wall: Why AI Agents Need Accountability, Not Just Guardrails](https://github.com/shimo4228/zenn-content/blob/main/articles-en/ai-agent-accountability-wall-en.md)
11. [Can You Trace the Cause After an Incident?](https://github.com/shimo4228/zenn-content/blob/main/articles-en/agent-causal-traceability-org-adoption-en.md)
12. [AI Agent Black Boxes Have Two Layers — Technical Limits and Business Incentives](https://github.com/shimo4228/zenn-content/blob/main/articles-en/agent-blackbox-capitalism-timescale-en.md)
13. [Where ReAct Agents Are Actually Needed in Business](https://github.com/shimo4228/zenn-content/blob/main/articles-en/react-agent-business-quadrant.md)
14. [The LLM Workflow Quadrant Is Missing from Our Vocabulary](https://github.com/shimo4228/zenn-content/blob/main/articles-en/react-agent-business-quadrant-2.md)
15. [Is ReAct Needed in Production? — Separating Design and Operation Phases](https://github.com/shimo4228/zenn-content/blob/main/articles-en/react-agent-business-quadrant-3.md)

</details>
