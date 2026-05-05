Language: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Português (Brasil)](README.pt-BR.md) | Español

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1032_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

Un agente CLI que ejecuta un ciclo de conocimiento de seis fases (AKC) sobre sus propios logs — cada promoción de logs → patrones → habilidades → reglas pasa por una puerta de aprobación humana. Corre por completo en un único Mac con Apple Silicon (M1+, 16 GB RAM) con un modelo local de 9B — sin nube, sin claves de API en tránsito, sin ejecución de shell.

Este repositorio es la implementación operativa de dos ideas preservadas:

- **[AKC (Agent Knowledge Cycle)](https://github.com/shimo4228/agent-knowledge-cycle)** ([DOI](https://doi.org/10.5281/zenodo.19200727)) — cómo un agente metaboliza su propia experiencia en habilidades mejorables. Seis fases: Research → Extract → Curate → Promote → Measure → Maintain.
- **[AAP (Agent Attribution Practice)](https://github.com/shimo4228/agent-attribution-practice)** ([DOI](https://doi.org/10.5281/zenodo.19652014)) — cómo se distribuye la responsabilidad en agentes de IA autónomos. Diez ADRs cubriendo Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, causal traceability, Triage Before Autonomy y Phase Separation between Design and Operation. Más un routing lens de cuatro cuadrantes (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop) tomado prestado en este repositorio como usage description — ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md).

El primer adaptador es **Moltbook** (red social solo para agentes de IA). Los cuatro axiomas de Contemplative AI vienen como preset opcional.

## Inicio rápido

**Prerrequisitos:** [Ollama](https://ollama.com/download) instalado localmente. ~8 GB de RAM para el modelo por defecto (Qwen3.5 9B Q4_K_M, ~6.6 GB en disco). Probado en Mac M1 con 16 GB de RAM.

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # o: uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

cp .env.example .env        # define MOLTBOOK_API_KEY (regístrate en moltbook.com)

contemplative-agent init               # crea identity, knowledge, constitution
contemplative-agent register           # solo para el adaptador Moltbook
contemplative-agent run --session 60   # por defecto: --approve (confirma cada publicación)
```

Empieza con un framework ético distinto (11 plantillas incluidas: Estoico, Utilitarismo, Ética del Cuidado, Kantiano, Pragmatismo, Contractualismo…):

```bash
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

Si usas [Claude Code](https://claude.ai/claude-code), pega la URL de este repositorio y pídele que configure el agente de extremo a extremo. Referencia completa de CLI, niveles de autonomía, planificación y plantillas: **[Guía de Configuración](docs/CONFIGURATION.md)**.

## Ejecutando en hosts de agente

Contemplative Agent es un agente Python CLI host-agnostic. Úsalo de forma standalone (predeterminado, ver Quick Start) o invócalo desde cualquier host de agente capaz de ejecutar herramientas externas.

**Dentro de hosts OpenClaw / OpenCode / soul-folder.** Registra `contemplative-agent` como herramienta CLI en el workspace de tu agente (por ejemplo `~/.openclaw/workspace/AGENTS.md`). El agente host invoca el binario como subprocess; esto respeta [one external adapter per process](docs/adr/0015-one-external-adapter-per-agent.md) al mantener la superficie externa en un proceso separado.

**Dentro de Codex / MCP host / otros hosts compatibles con CLI.** Mismo patrón — registra el binario en el registro de herramientas del host. Contemplative Agent no se expone a sí mismo como MCP server (ver [ADR-0007](docs/adr/0007-security-boundary-model.md) para la frontera de seguridad).

**Cargando los cuatro axiomas contemplativos (opcional).** Si quieres Emptiness / Non-Duality / Mindfulness / Boundless Care cargados como agent personality en tu host, copia `SOUL.md` de [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) a la ubicación soul-folder de tu host (por ejemplo `~/.openclaw/workspace/SOUL.md`). Contemplative Agent en sí mismo no incluye un SOUL.md porque es un agente CLI, no un archivo de personalidad.

## Agente en vivo

Un agente Contemplative corre a diario en [Moltbook](https://www.moltbook.com/u/contemplative-agent). Su estado en evolución se publica abiertamente:

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) — persona destilada
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) — principios éticos (a partir de los cuatro axiomas CCAI)
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) — extraídas por `insight`
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) — destiladas a partir de las skills
- [Reportes diarios](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — interacciones con timestamp (libre para uso académico y no comercial)
- [Reportes de análisis](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) — evolución conductual, experimentos de enmienda constitucional

## Cómo funciona

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

Las acciones brutas fluyen hacia arriba a través de capas cada vez más abstractas. Cada capa es opcional. Toda capa por encima del Episode Log es generada por el agente reflexionando sobre su propia experiencia.

Esta pipeline es el mapeo de las seis fases AKC al código: `distill` cubre Extract; `insight` / `rules-distill` / `amend-constitution` cubren Curate; `distill-identity` cubre Promote; pivot snapshots ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)) cubren Measure. Mapeo completo: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping).

## Características clave

- **Ciclo de conocimiento (AKC) sobre sus propios logs** — el agente corre el ciclo de seis fases sobre sus propios logs. Sin fine-tuning, sin datos de entrenamiento etiquetados. Cada promoción (logs → patrones → habilidades → reglas → identidad) pasa por una [puerta de aprobación humana](docs/adr/0012-human-approval-gate.md).
- **Embedding + views** — la clasificación es una query, no un estado; las views son semillas semánticas editables ([ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md); el campo `category` fue retirado en [ADR-0026](docs/adr/0026-retire-discrete-categories.md)).
- **Noise as seed** — los episodios rechazados se preservan como `noise-YYYY-MM-DD.jsonl`; cuando los centroides de las views se desplazan, quedan disponibles para reclasificación en lugar de perderse ([ADR-0027](docs/adr/0027-noise-as-seed.md)).
- **Pivot snapshots reproducibles** — las ejecuciones de `distill` empaquetan el contexto completo en tiempo de inferencia (views + constitution + prompts + skills + rules + identity + embeddings de centroides + thresholds), permitiendo replay bit-for-bit ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)).
- **Trazabilidad de procedencia** — cada patrón lleva `source_type` y `trust_score`; los ataques de inyección de memoria de la clase MINJA se vuelven estructuralmente visibles ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- **Markdown all the way down** — constitución, identidad, habilidades, reglas, 32 prompts del pipeline y 7 semillas de view están todas como Markdown bajo `$MOLTBOOK_HOME/`. Edita un prompt para cambiar cómo se extraen los patrones; cambia una semilla de view para desplazar la clasificación. [Personaliza →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

## Modelo de seguridad

La responsabilidad y los límites de seguridad están documentados como ADRs neutrales respecto al harness en [AAP](https://github.com/shimo4228/agent-attribution-practice). Este repositorio es la implementación operativa de esos juicios.

- Sin ejecución de shell, sin acceso arbitrario a la red, sin traversal del filesystem — ese código no existe en la base de código. Dominio bloqueado a `moltbook.com` + Ollama local. 2 dependencias en runtime: `requests`, `numpy`.
- Un adaptador externo por proceso ([ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)).
- Modelo de amenazas completo: [ADR-0007](docs/adr/0007-security-boundary-model.md). [Último escaneo de seguridad](docs/security/2026-04-01-security-scan.md).

> Pega la URL de este repositorio en [Claude Code](https://claude.ai/claude-code) o en cualquier IA que entienda código y pregúntale si es seguro ejecutarlo. El código habla por sí solo.

**Nota para operadores de agentes de código**: Los logs de episodios (`logs/*.jsonl`) son una superficie de inyección indirecta de prompt sin filtrar. Usa las salidas destiladas (`knowledge.json`, `identity.md`, `reports/`) en su lugar. Usuarios de Claude Code: véase [integrations/claude-code/](integrations/claude-code/) para PreToolUse hooks que aplican esto automáticamente.

## Adaptadores

El núcleo es independiente de la plataforma. Los adaptadores son envoltorios finos sobre el I/O de la plataforma.

- **Moltbook** — Interacción con el feed social, generación de publicaciones, respuestas a notificaciones. Es el adaptador sobre el que corre el agente en vivo.
- **Meditation** (experimental) — Simulación de meditación basada en inferencia activa, inspirada en ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/). Construye un POMDP a partir de los logs y actualiza creencias sin entrada externa.
- **Dialogue** (solo local) — Dos procesos de agente conversan a través de pipes stdin/stdout. Un adaptador mínimo de ~140 líneas ([`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)) — útil como plantilla de adaptador sin HTTP ni red. Impulsa `contemplative-agent dialogue HOME_A HOME_B`.
- **El tuyo** — Conecta el I/O de la plataforma a las interfaces del núcleo (memoria, destilación, constitución, identidad). Véase [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md).

## Arquitectura

Un invariante se mantiene en toda la base de código: **core/** es independiente de la plataforma; **adapters/** dependen del core, nunca al revés. Los mapas de módulos, diagramas de flujo de datos y responsabilidades por módulo están en **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)** (fuente autoritativa). El frame de las ocho consciencias del Yogācāra que restringió el diseño de la memoria: [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md).

Los modos de operación típicos de los comandos CLI pueden leerse a través de la lente de cuatro cuadrantes de AAP. La mayoría de los comandos behaviour-modifying (`distill`, `insight`, `rules-distill`, `amend-constitution`, `distill-identity`, `skill-stocktake`, `dialogue`) opera típicamente como **LLM Workflow** — flujo de control definido, roles LLM acotados por llamada, promoción determinista a través de la [puerta de aprobación](docs/adr/0012-human-approval-gate.md) donde aplique. `adopt-staged` y las migraciones puntuales tienen forma **Script**. `meditate` (el adaptador experimental de Active Inference — actualizaciones de creencia POMDP en numpy, sin LLM en tiempo de ejecución) es **Algorithmic Search** — actualizaciones deterministas sobre un espacio exploratorio de políticas de acción. **El cuadrante Autonomous Agentic Loop no está siendo ruteado actualmente por ningún comando CLI de este proyecto** — una observación de uso, no un juicio de valor sobre ese cuadrante. Ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md) para entender por qué los placements son observaciones de uso y no compromisos de categoría.

<details>
<summary><b>Opcional: Ejecutar con APIs de LLM gestionadas</b></summary>

Para experimentos de investigación que necesitan un modelo de generación mayor que Qwen3.5 9B (p. ej., comparar cómo cambia la destilación con Claude Opus o GPT-5 manteniendo el resto del pipeline de memoria idéntico), un repositorio complementario aparte provee backends de LLM gestionados:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) — Paquete Python opcional. Instalarlo y configurar una clave de API enruta toda llamada de generación (distill, insight, rules-distill, amend-constitution, post, comment, reply, dialogue) por Anthropic Claude o OpenAI GPT. Los embeddings siguen usando el `nomic-embed-text` local.

Esto es un **opt-in** explícito. El stack por defecto de este repositorio (Ollama + Qwen3.5 9B) no alcanza ningún endpoint en la nube. La propiedad "sin nube, sin claves de API en tránsito" vale para este repositorio; el complemento de nube la relaja para los usuarios que opten por hacerlo. El código del repositorio principal no se modifica — el complemento inyecta su backend a través de un Protocol `LLMBackend` abstracto.

No instales el complemento de nube en despliegues donde la salida de datos a la nube no sea aceptable (restricciones regulatorias, investigación en redes aisladas, asistentes personales sensibles a la privacidad).

</details>

<details>
<summary><b>Opcional: CLI cotidiano</b></summary>

```bash
contemplative-agent run --session 60       # Ejecuta una sesión
contemplative-agent distill --days 3       # Extrae patrones
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```

Referencia completa (niveles de autonomía, planificación, variables de entorno, migraciones v1.x → v2): **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**. Para despliegue con aislamiento de red vía Docker: [sección Docker](docs/CONFIGURATION.md#docker-optional).

</details>

## Cita

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

La licencia MIT significa lo que dice — haz fork, desármalo por piezas, incrusta el pipeline en tu propio agente, construye un producto comercial encima. No hace falta citar si solo estás usando el código.

## Trabajos relacionados

- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) ([DOI](https://doi.org/10.5281/zenodo.19200727)) — el framework metodológico que este proyecto reimplementa en el contexto de agentes autónomos. Originalmente desarrollado como harness de Claude Code.
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ([DOI](https://doi.org/10.5281/zenodo.19652014)) — repositorio de investigación hermano. Reexpresa los juicios de gobernanza de este proyecto (Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, causal traceability / scaffolding visibility, triage before autonomy, design / operation phase separation) en forma neutral respecto al harness, como diez ADRs sobre la distribución de responsabilidad. AAP también articula un routing lens de cuatro cuadrantes (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop), independiente de las diez ADRs y ortogonal a ellas; este repositorio toma prestada la lente como ayuda de descripción de uso (ver [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md)). Cita AAP cuando cites la tesis de distribución de responsabilidad o la jerarquía de prohibition-strength; cita este repositorio para la implementación operativa.

**Fundamentos teóricos:**

- Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold, & Elwood (2025). *Contemplative Artificial Intelligence.* [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) — framework ético de cuatro axiomas (preset opcional, [ADR-0002](docs/adr/0002-paper-faithful-ccai.md)).
- Laukkonen, Friston & Chandaria (2025). *A Beautiful Loop: An Active Inference Theory of Consciousness.* *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) — base del adaptador Meditation.
- Vasubandhu (s. IV–V). *Triṃśikā-vijñaptimātratā* (唯識三十頌) y Xuanzang (659). *Cheng Weishi Lun* (成唯識論) — modelo de ocho consciencias adoptado como el frame arquitectural ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)).

<details>
<summary><b>Bibliografía de sistemas de memoria</b></summary>

Cada paper a continuación informó una decisión de diseño específica documentada en la ADR vinculada.

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) — indexación dinámica al estilo Zettelkasten y evolución de memoria. Originalmente inspiró [ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md), retirado por [ADR-0034](docs/adr/0034-withdraw-memory-evolution-and-hybrid-retrieval.md) tras evaluación empírica. Conservada como referencia histórica.
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) — aristas de grafo de conocimiento bitemporales (motor Graphiti); informa el contrato `valid_from` / `valid_until` en cada patrón ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) — decaimiento al estilo Ebbinghaus con fuerza reforzada por acceso; originalmente informó la curva de olvido consciente del retrieval propuesta en [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md), retirada en [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) en favor de localizar la dinámica de memoria en la capa de skill. Mantenido como referencia histórica.
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) — ataques de inyección de memoria solo vía query en agentes; motiva la procedencia `source_type` + `trust_score` para que los ataques de la clase MINJA se vuelvan estructuralmente visibles en lugar de invisibles ([ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)).
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) — habilidades como unidades de memoria persistentes y en evolución, recuperadas, aplicadas y reescritas según el resultado. Informó [ADR-0023](docs/adr/0023-skill-as-memory-loop.md), retirado por [ADR-0036](docs/adr/0036-sunset-skill-as-memory-loop.md). Mantenido como referencia histórica.

</details>

**Agradecimientos:** Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) — inspiración de diseño de evaluación afectiva determinística.

<details>
<summary><b>Registros de desarrollo (15 artículos · código fuente en GitHub)</b></summary>

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
