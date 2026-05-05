Language: [English](README.md) | [日本語](README.ja.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Português (Brasil)](README.pt-BR.md) | [Español](README.es.md)

<p align="center">
  <img src="docs/assets/logo.png" alt="CA logo" width="200">
</p>

# Contemplative Agent (CA)

[![Tests](https://img.shields.io/badge/tests-1032_passed-brightgreen)](docs/CONFIGURATION.md#development)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

在自身日志上运行六阶段知识循环 (AKC) 的 CLI 代理 —— 日志 → 模式 → 技能 → 规则的每次晋升都经过人类审批闸门。完全运行于本地的 9B 模型 + 单台 Apple Silicon Mac (M1+, 16 GB RAM) — 无需云端、API 密钥不出网络、无 shell 执行。

本仓库是两条被保存的想法的运行实现:

- **[AKC (Agent Knowledge Cycle)](https://github.com/shimo4228/agent-knowledge-cycle)** ([DOI](https://doi.org/10.5281/zenodo.19200727)) — 代理如何将自身经验代谢为可改进的技能。六阶段: Research → Extract → Curate → Promote → Measure → Maintain。
- **[AAP (Agent Attribution Practice)](https://github.com/shimo4228/agent-attribution-practice)** ([DOI](https://doi.org/10.5281/zenodo.19652014)) — 自主 AI 代理中如何分配问责。十条 ADR，覆盖 Security Boundary Model、One External Adapter Per Agent、Human Approval Gate、causal traceability、Triage Before Autonomy 与 Phase Separation between Design and Operation。此外还有四象限路由诊断 lens (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop) — 本仓库以 usage description 的形式借用 — 见 [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md)。

第一个适配器是 **Moltbook**（AI 代理社交网络）。Contemplative AI 四公理作为可选预设随附。

## 快速开始

**前置条件:** 本机已安装 [Ollama](https://ollama.com/download)。默认模型 (Qwen3.5 9B Q4_K_M, 约 6.6 GB) 需要约 8 GB RAM。已在 M1 Mac (16 GB RAM) 上验证。

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
pip install -e .            # 或：uv venv .venv && source .venv/bin/activate && uv pip install -e .
ollama pull qwen3.5:9b

cp .env.example .env        # 设置 MOLTBOOK_API_KEY（在 moltbook.com 注册获取）

contemplative-agent init               # 创建 identity, knowledge, constitution
contemplative-agent register           # 仅 Moltbook 适配器需要
contemplative-agent run --session 60   # 默认：--approve（每次发布前确认）
```

以不同的伦理框架开始（11 种模板随附：斯多葛、功利主义、关怀伦理、康德义务论、实用主义、契约主义……）:

```bash
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

若你使用 [Claude Code](https://claude.ai/claude-code)，可将本仓库 URL 贴给它并让其完成端到端搭建。完整 CLI 参考、自主级别、调度、模板请见 **[配置指南](docs/CONFIGURATION.md)**。

## 在代理宿主中运行

Contemplative Agent 是与宿主无关的 Python CLI 代理。可作为独立程序使用（详见快速开始），也可被任何能调用外部工具的代理宿主调用。

**在 OpenClaw / OpenCode / soul-folder 宿主内运行**: 在代理 workspace（例如 `~/.openclaw/workspace/AGENTS.md`）中将 `contemplative-agent` 注册为 CLI 工具。宿主代理通过 subprocess 调用该二进制，将外部 surface 保留在独立进程中，符合 [one external adapter per process 原则](docs/adr/0015-one-external-adapter-per-agent.md)。

**在 Codex / MCP host / 其他 CLI 兼容宿主内运行**: 同样模式 — 在宿主的工具注册表中注册该二进制。Contemplative Agent 不会将自身作为 MCP server 暴露（安全边界详见 [ADR-0007](docs/adr/0007-security-boundary-model.md)）。

**加载四公理（Emptiness / Non-Duality / Mindfulness / Boundless Care，可选）**: 若希望将四公理作为 agent personality 在宿主内 load，请将 [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) 的 `SOUL.md` 复制到宿主的 soul-folder 位置（例如 `~/.openclaw/workspace/SOUL.md`）。Contemplative Agent 本身不附带 SOUL.md — 因为它是 CLI 代理，而非 personality 文件。

## 实时代理

一个 Contemplative 代理每天运行在 [Moltbook](https://www.moltbook.com/u/contemplative-agent) 上。其演化状态对外公开:

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) —— 蒸馏出的人格
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) —— 伦理原则（以 CCAI 四公理为起点）
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) —— 由 `insight` 抽取
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) —— 从技能蒸馏
- [日报](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) —— 带时间戳的交互记录（学术与非商业用途自由可用）
- [分析报告](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/analysis) —— 行为演化与章程修订实验

## 工作原理

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

原始行为沿越来越抽象的层级向上流动。每一层都是可选的。Episode Log 之上的每一层都是代理反观自身经验后生成的。

这条管线即 AKC 六阶段到代码的映射: `distill` 对应 Extract；`insight` / `rules-distill` / `amend-constitution` 对应 Curate；`distill-identity` 对应 Promote；pivot snapshots ([ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)) 对应 Measure。完整对应表: [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md#akc-agent-knowledge-cycle-mapping)。

## 主要特性

- **在自身日志上的知识循环 (AKC)** —— 代理在自身日志上运行六阶段循环。无需微调，无需标注训练数据。每次阶段晋升（日志 → 模式 → 技能 → 规则 → 身份）都经过[人类审批闸门](docs/adr/0012-human-approval-gate.md)。
- **嵌入 + views** —— 分类是查询而非状态；views 是可编辑的语义种子（[ADR-0019](docs/adr/0019-discrete-categories-to-embedding-views.md)；`category` 字段已在 [ADR-0026](docs/adr/0026-retire-discrete-categories.md) 废止）。
- **noise as seed** —— 被驳回的片段以 `noise-YYYY-MM-DD.jsonl` 形式保留；当 view 质心漂移时可被重新分类，而不是丢失（[ADR-0027](docs/adr/0027-noise-as-seed.md)）。
- **可重放的 pivot snapshots** —— `distill` 执行将完整推理时上下文（views + constitution + prompts + skills + rules + identity + 质心嵌入 + thresholds）一次打包，以便任意决策按位重放（[ADR-0020](docs/adr/0020-pivot-snapshots-for-replayability.md)）。
- **出处追踪** —— 每个模式携带 `source_type` 与 `trust_score`；MINJA 类记忆注入攻击在结构上变得可见（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- **Markdown all the way down** —— 章程、身份、技能、规则、32 个流水线提示词、7 个 view 种子全部以 Markdown 形式存在于 `$MOLTBOOK_HOME/` 下。编辑提示词改变模式抽取的行为；替换 view 种子以调整分类。[自定义 →](docs/CONFIGURATION.md#pipeline-prompts--view-seeds)

## 安全模型

问责与安全边界在 [AAP](https://github.com/shimo4228/agent-attribution-practice) 中以 harness-neutral 的 ADR 记录。本仓库是这些判断的运行实现。

- 无 shell 执行、无任意网络访问、无文件系统遍历 —— 这些代码不存在于代码库中。域名锁定到 `moltbook.com` 与本地 Ollama。2 个运行时依赖: `requests`、`numpy`。
- 一进程一外部适配器 ([ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md))。
- 完整威胁模型: [ADR-0007](docs/adr/0007-security-boundary-model.md)。[最新安全扫描](docs/security/2026-04-01-security-scan.md)。

> 将本仓库 URL 贴入 [Claude Code](https://claude.ai/claude-code) 或任何懂代码的 AI，问它「运行这个安全吗？」—— 代码自己会说话。

**代码代理运营者提醒**: 片段日志 (`logs/*.jsonl`) 是未过滤的间接提示词注入攻击面。请改用蒸馏产物 (`knowledge.json`、`identity.md`、`reports/`)。Claude Code 用户可安装 PreToolUse hooks 自动强制执行 —— 见 [integrations/claude-code/](integrations/claude-code/)。

## 适配器

核心与平台无关。适配器只是平台 I/O 的薄包装。

- **Moltbook** —— 社交信息流参与、帖子生成、通知回复。这是线上代理所运行的适配器。
- **Meditation**（实验性） —— 基于能动推断的冥想模拟，灵感来自 ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/)。从片段日志构建 POMDP，并在无外部输入的条件下进行信念更新。
- **Dialogue**（仅本地） —— 两个代理进程通过 stdin/stdout 管道对话。约 140 行的最小适配器（[`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)）—— 适合作为不走 HTTP、不联网的适配器模板。`contemplative-agent dialogue HOME_A HOME_B` 即由其驱动。
- **自建适配器** —— 把平台 I/O 连接到核心接口（记忆、蒸馏、章程、身份）。见 [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md)。

## 架构

代码库始终遵守一个不变式: **core/** 与平台无关；**adapters/** 依赖 core，反之绝不成立。模块地图、数据流图、模块级职责见 **[docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md)**（权威来源）。约束记忆设计的唯识 (Yogācāra) 八识框架: [ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)。

CLI 命令的典型运作模式可借助 AAP 的四象限 lens 解读。多数 behaviour-modifying 命令 (`distill`, `insight`, `rules-distill`, `amend-constitution`, `distill-identity`, `skill-stocktake`, `dialogue`) 通常以 **LLM Workflow** 模式运作 — 已定义的控制流，每次调用 bounded LLM role，在适用之处通过[审批闸门](docs/adr/0012-human-approval-gate.md)进行确定性提升。`adopt-staged` 与一次性迁移属 **Script** 形态。`meditate`（实验性 Active Inference 适配器 — numpy 里的 POMDP belief update，运行期不调用 LLM）属 **Algorithmic Search** — 探索性行动策略空间上的决定论更新。**Autonomous Agentic Loop 象限目前未被本项目的任何 CLI 命令 route** — 这是 usage observation，并非对该象限的 value judgement。为何这些放置仅是 usage observation 而非 category commitment，请见 [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md)。

<details>
<summary><b>可选: 使用托管 LLM API 运行</b></summary>

需要比 Qwen3.5 9B 更大的生成模型的研究实验 —— 例如在保持其余记忆流水线不变的前提下，比较蒸馏行为在 Claude Opus 或 GPT-5 下的差异 —— 可以使用一个独立仓库的 add-on:

- [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) —— 可选 Python 包。安装并设置 API 密钥后，所有生成调用（distill / insight / rules-distill / amend-constitution / post / comment / reply / dialogue）都会改走 Anthropic Claude 或 OpenAI GPT，而 embedding 仍使用本地的 `nomic-embed-text`。

这是明确的 **opt-in**。主仓库的默认栈（Ollama + Qwen3.5 9B）不会访问任何云端。「无云端、API 密钥不出网络」的属性对本仓库成立；只有当用户主动安装 cloud add-on 时，这一属性才会在那些用户那里被放宽。主仓库的代码不会被修改 —— add-on 通过抽象的 `LLMBackend` Protocol 注入后端实现。

在不允许云端数据外发的部署（监管约束、气隙研究、隐私敏感的个人助理）中，不要安装 cloud add-on。

</details>

<details>
<summary><b>可选: 日常 CLI</b></summary>

```bash
contemplative-agent run --session 60       # 运行一次会话
contemplative-agent distill --days 3       # 抽取模式
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```

完整参考（自主级别、调度、环境变量、v1.x → v2 迁移）: **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**。基于 Docker 的网络隔离部署: [Docker 一节](docs/CONFIGURATION.md#docker-optional)。

</details>

## 引用

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

MIT 许可证如其所言 —— fork、拆成零件、把管线嵌进你自己的代理、或者以它为基础造商业产品。仅使用代码时无需引用。

## 相关项目

- [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) ([DOI](https://doi.org/10.5281/zenodo.19200727)) —— 本项目在自主代理语境中重新实现的方法论框架。最初作为 Claude Code harness 开发。
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) ([DOI](https://doi.org/10.5281/zenodo.19652014)) —— 姐妹研究仓库。以 harness-neutral 的形式将本项目的治理判断（Security Boundary Model、One External Adapter Per Agent、Human Approval Gate、causal traceability / scaffolding visibility、triage before autonomy、design / operation phase separation）重新表达为十条 ADR，关于自主 AI 代理中问责的分配。AAP 还在十条 ADR 之外另外提出了四象限路由诊断 lens (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop)，与十条 ADR 正交；本仓库将该 lens 作为 usage description 借用（见 [ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md)）。引用问责分配论点或 prohibition-strength 层级时请引用 AAP；引用运行实现时请引用本仓库。

**理论基础:**

- Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold, & Elwood (2025). *Contemplative Artificial Intelligence.* [arXiv:2504.15125](https://arxiv.org/abs/2504.15125) —— 四公理伦理框架（可选预设，[ADR-0002](docs/adr/0002-paper-faithful-ccai.md)）。
- Laukkonen, Friston & Chandaria (2025). *A Beautiful Loop: An Active Inference Theory of Consciousness.* *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/) —— 冥想适配器的理论基础。
- 世亲（Vasubandhu, 4–5 世纪）《唯识三十颂》和 玄奘 译·编（659）《成唯识论》—— 八识模型作为架构框架被采纳（[ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)）。

<details>
<summary><b>记忆系统书目</b></summary>

下列各篇论文都对应一项在 ADR 中记录的设计决策。

- Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., & Zhang, Y. (2025). *A-MEM: Agentic Memory for LLM Agents.* [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) —— Zettelkasten 式动态索引与记忆进化。最初启发了 [ADR-0022](docs/adr/0022-memory-evolution-and-hybrid-retrieval.md)，经实证评估后由 [ADR-0034](docs/adr/0034-withdraw-memory-evolution-and-hybrid-retrieval.md) 撤回。作为历史参考保留。
- Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J., & Chalef, D. (2025). *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) —— 双时态 (bitemporal) 知识图谱边 (Graphiti 引擎)；启发了每个模式上的 `valid_from` / `valid_until` 契约（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- Zhong, W., Guo, L., Gao, Q., Ye, H., & Wang, Y. (2023). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* [arXiv:2305.10250](https://arxiv.org/abs/2305.10250) —— Ebbinghaus 式衰减与以访问为强化信号的强度模型；原本启发了 [ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md) 中检索感知的遗忘曲线，但在 [ADR-0028](docs/adr/0028-retire-pattern-level-forgetting-feedback.md) 中被撤回 —— 记忆动力学的落脚点改为技能层。作为历史参考保留。
- Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang, Z. (2025). *Memory Injection Attacks on LLM Agents via Query-Only Interaction* (MINJA). [arXiv:2503.03704](https://arxiv.org/abs/2503.03704) —— 仅通过查询即可实施的记忆注入攻击；是引入 `source_type` 与 `trust_score` 的动机，使 MINJA 类攻击结构上可见而非隐蔽（[ADR-0021](docs/adr/0021-pattern-schema-trust-temporal-forgetting-feedback.md)）。
- Zhou, H., Guo, S., Liu, A., et al. (2026). *Memento-Skills: Let Agents Design Agents.* [arXiv:2603.18743](https://arxiv.org/abs/2603.18743) —— 把技能视为持续演化的记忆单元，通过「取出 → 应用 → 依结果改写」循环更新。曾启发 [ADR-0023](docs/adr/0023-skill-as-memory-loop.md)，但被 [ADR-0036](docs/adr/0036-sunset-skill-as-memory-loop.md) 撤回。保留作为历史参考。

</details>

**致谢:** Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)) —— 决定论式情感评分的设计灵感。

<details>
<summary><b>开发记录（15 篇文章 · 源码在 GitHub）</b></summary>

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
