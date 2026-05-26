# Skills Router

[![Version](https://img.shields.io/badge/version-v0.0.2-orange.svg)](../CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](../LICENSE)
[![Author](https://img.shields.io/badge/author-the--long--ride-green.svg)](https://github.com/the-long-ride)
[![Build Status](https://img.shields.io/badge/tests-199%20passed-success.svg)](../tests/)

[English](../README.md) | [Español](es.md) | [简体中文](zh.md) | [日本語](ja.md) | [Deutsch](de.md) | [Français](fr.md)

`skills-router` 是 CLI 命令和 PyPI 软件包名称。npm 包装器包是
[`@the-long-ride/skills-router`](https://www.npmjs.com/package/@the-long-ride/skills-router)。

**Skills Router 是一个 AI 智能体技能集管理器。** 它对 AI 智能体技能/插件进行审核、
注册、发现、索引、对比和路由，以便宿主智能体能够使用正确的技能，而不会悄无声息地占用包资源。

Skills Router 不是常规的包管理器。它管理元数据、决策、审计日志和路由状态。包文件、
虚拟环境、IDE 扩展和宿主智能体的技能目录仍由安装它们的工具所有。

## 为什么选择 skills-router？

AI 智能体的技能非常有用，但它们散落在 CLI、IDE、MCP 服务器、全局文件夹、工作区文件夹以及特定于宿主的包管理器中。
这使得回答一些简单的问题变得很困难：该智能体应该使用哪种技能、谁批准了它、它在何处处于活动状态，以及如果另一个包与其重叠会发生什么？

`skills-router` 为智能体提供了一个共享控制平面来解决这一问题。它允许您一次性安装或发现技能，
通过信任和行为检查进行审核，并将每个智能体路由到正确的技能，而无需复制包文件或在 Prompt 中塞入庞大的路由表。
包管理器依然管理包资源，而 Skills Router 管理决策、元数据、审计轨迹和路由层。

## 功能特性

- 通过信任、依赖、语义、能力和健康检查，对完整的技能/插件清单进行审核。
- 在 Brain 索引库中存储已批准的包元数据。
- 编写 `skills-router.json` 规则，宿主智能体可通过 MCP 或 CLI 进行查询。
- 使用 `--all-agents` 或 `/skills-router install <package> for all agents` 一次性为所有配置的宿主智能体安装技能。
- 支持通过目标列表限制多智能体安装，例如 `--agent-target codex,cursor`。
- 在智能体调用 `route_task` 或 `skills-router route --target <agent>` 时，强制执行目标感知的路由。
- 支持默认的多智能体宿主集合：`antigravity`、`antigravity-cli`、`antigravity-ide`、`codex`、`claude`、`hermes-agent`、`opencode`、`cline`、`cursor` 和 `windsurf`。
- 将部分安装视为选择性的路由激活，而不是部分包提取。
- 在卸载时移除 Skills Router 所拥有的元数据/路由，然后重新索引剩余的路由表面。
- 使用 `/skills-router index` 对路由进行对账。
- 使用 `/skills-router refine` 发现工作区或全局安装的外部技能。
- 扫描共享的和特定于宿主的工作区/全局技能目录，包括嵌套的系统技能文件夹。
- 将新发现的外部路由保持在 `needs_selection` 状态，直到用户确认激活。
- 在推送标签时，从相应的 `CHANGELOG.md` 章节发布版本说明，CI 会附带包链接。

## 非功能特性

- 它不会删除包拥有的文件、仓库、虚拟环境或 IDE/插件资源。
- 它不会取代 `pip`、`npm`、IDE 插件管理器或宿主智能体的插件管理器。
- 除非用户明确同意接受风险，否则它不会自动批准信任警告、依赖冲突、重复路由或未知行为。
- 它不会在智能体 Prompt 中注入庞大的路由表。智能体应该动态查询 Skills Router。

## 架构

```mermaid
flowchart LR
    Human[用户] --> Host[AI 智能体宿主]
    Host --> Bridge[智能体桥接器]
    Host --> MCP[MCP stdio 服务器]
    Host --> CLI[CLI]

    Bridge --> Parser[斜杠指令解析器]
    Parser --> Executor[桥接器执行器]
    MCP --> Executor
    CLI --> Commands[严格命令]

    Commands --> Install[安装管道]
    Executor --> Install
    Commands --> Reconcile[索引与提炼]
    Executor --> Reconcile
    Commands --> Lookup[路由查找]
    Executor --> Lookup
    Commands --> Remove[卸载元数据]
    Executor --> Remove

    Install --> Resolver[注册表解析器]
    Resolver --> Trust[信任门控]
    Trust --> Deps[依赖解析器]
    Deps --> Semantic[语义评估器]
    Semantic --> Capability[能力检查器]
    Capability --> WG[工作区/全局 Prompt]
    WG --> Health[健康检查]

    Reconcile --> Discovery[技能发现]
    Discovery --> SkillDirs[工作区/全局技能目录]
    Discovery --> GlobalIndex[全局 Skills Router 索引]
    Reconcile --> Conflict[冲突检测器]

    Install --> Store[(Brain 索引库)]
    Reconcile --> Store
    Conflict --> Routes[(skills-router.json)]
    Lookup --> Routes
    Remove --> Store
    Remove --> Routes
    Remove --> Lock
    Remove --> Audit
    Install --> Lock[(锁文件)]
    Install --> Audit[(审计日志)]
```

## 核心工作流

```mermaid
flowchart TD
    A[用户向 AI 智能体提问] --> B{请求形式}
    B -->|/skills-router install pkg for me| C[解析斜杠指令请求]
    B -->|MCP 结构化调用| D[调用 MCP 工具]
    B -->|严格 CLI 命令| E[运行命令]

    C --> F[解析包或清单]
    D --> F
    E --> F
    F --> G[信任与依赖检查]
    G -->|直接拒绝| H[停止并总结]
    G -->|需要审核| I[询问用户]
    I -->|取消| H
    I -->|批准| J[语义和能力对比]
    G -->|安全| J
    J -->|重叠| K[推荐路由选择]
    K --> L[用户选择路由]
    J -->|无冲突| M[持久化元数据]
    L --> M
    M --> N[写入路由和锁文件]
    N --> O[健康检查]
    O -->|失败| P[清理 Skills Router 状态]
    O -->|通过| Q[审计和简短总结]

    R[宿主包管理器更改文件] --> S["/skills-router index"]
    T[出现外部技能] --> U["/skills-router refine"]
    S --> V[刷新路由并标记过期]
    U --> W[发现并导入元数据]
    V --> X[推荐路由决策]
    W --> X
```

## 安装

```bash
# Core local install
pip install -e .

# Optional real embedding support
pip install -e ".[ml]"

# Optional pgvector backend
pip install -e ".[pgvector]"

# Run through npm/npx
npx @the-long-ride/skills-router --help
```

默认的存储后端是位于 `~/.skills-router` 下的 JSON 本地内存。
在 `skills-router-npx/` 中提供了一个本地 Node 包装器，用于 `npx` 和 IDE 工作流；请参阅 [GUIDELINE.md](../GUIDELINE.md)。

## 快速开始

```bash
# Review and register a local manifest
skills-router install examples/sample_manifests/weather_tool.json --scope global

# Review and register by registry package name
skills-router install writer-pack --package-type skillset --scope workspace:codex-local

# Install once and make routes visible to all configured AI-agent hosts
skills-router install writer-pack --package-type skillset --all-agents --json

# Install once but expose routes only to selected agent hosts
skills-router install writer-pack --package-type skillset --all-agents --agent-target codex,cursor --json

# Install the full package but leave routes inactive until selection
skills-router install writer-pack --package-type skillset --routing-mode selective_routes --scope workspace:codex-local --json

# Preview review decisions without writing state
skills-router install writer-pack --dry-run --explain --json

# Remove Skills Router metadata/routing only
skills-router uninstall writer-pack --json

# Reconcile already indexed packages and routes
skills-router index --json

# Discover workspace/global host-agent skills and refine routes
skills-router refine --json
skills-router refine writer-pack engram --json
skills-router refine --workspace-scope workspace:codex-local --json

# Ask Skills Router which route matches a task for the current host
skills-router route "draft article about release notes" --scope workspace:codex-local --target codex --json

# Let an AI-agent host execute a human slash request
skills-router chat "/skills-router install writer-pack for me" --target codex --agent-id codex-local --json
skills-router chat "/skills-router install writer-pack for all installed agents" --target codex --agent-id codex-local --json
skills-router chat "/skills-router refine writer-pack engram" --target codex --agent-id codex-local --json

# Expose Skills Router through stdio JSON-RPC
skills-router mcp

# Render bridge instructions for a host
skills-router prompt --target codex
skills-router prompt --list
```

## 命令集

| 命令 | 用途 |
| :--- | :--- |
| `install <manifest-or-package>` | 解析、审核、注册并路由软件包。 |
| `index` | 重建已索引的向量/路由，并检测冲突或过期路由。 |
| `refine [skillset ...]` | 发现外部技能，导入元数据，并对账路由。 |
| `route <task>` | 查询某项任务的活动路由或需要审核的路由。 |
| `uninstall <tool_id>` | 仅删除 Skills Router 所有的元数据/路由。 |
| `list` | 列出已索引的工具。 |
| `inspect <tool_id>` | 打印一条 Brain 索引条目。 |
| `audit` | 查询审计事件。 |
| `watch` | 单次运行或以守护进程运行 Registry Watch。 |
| `prompt` | 渲染特定于宿主的桥接器说明。 |
| `chat` | 解析并执行聊天格式的 `/skills-router` 请求。 |
| `mcp` | 运行本地 stdio JSON-RPC 工具服务器。 |

## 一键式多智能体安装

多智能体（All-agent）安装是 v0.0.2 的核心工作流：

```bash
skills-router install writer-pack --package-type skillset --all-agents --json
```

该包依然只在 Skills Router 中注册一次。生成的路由是全局的，每个配置的宿主都可通过 MCP 或 CLI 桥接器来访问。Skills Router 仅管理元数据和路由，软件包资源仍归宿主包管理器或技能安装程序所有。

默认的智能体目标集：

```text
antigravity, antigravity-cli, antigravity-ide, codex, claude,
hermes-agent, opencode, cline, cursor, windsurf
```

若技能仅适用于部分智能体，请使用 `--agent-target`：

```bash
skills-router install writer-pack \
  --package-type skillset \
  --all-agents \
  --agent-target codex,cursor \
  --json
```

当存储了目标列表时，路由查找仅在调用者识别出当前宿主时才会生效：

```bash
skills-router route "draft release notes" --target codex --json
skills-router route "draft release notes" --target cursor --json
```

对于聊天格式的请求，智能体可以使用：

```text
/skills-router install <package> for all installed agents
```

## 路由模型

Skills Router 将包的存在与智能体激活分离开来：

- **包的存在 (Package presence)：** 宿主包管理器安装或更新完整的软件包。
- **Brain 索引库：** Skills Router 存储清单、信任、依赖关系、向量、行为和范围等元数据。
- **路由：** Skills Router 写入 `skills-router.json` 规则和包。
- **选择 (Selection)：** 路由冲突和外部发现的技能在人工确认激活前将处于 `needs_selection` 状态。
- **查找：** 智能体通过调用 MCP `route_task` 或 `skills-router route` 并带上其 `target` 来查询，而不是直接读取路由文件。
- **过期路由 (Stale routes)：** `index` 将缺失的包标记为 `missing_from_index`；它不会删除软件包文件。

## 提炼与发现

`skills-router refine` 填补了人工在工作区外安装技能的空白，例如通过 `npx`、宿主智能体技能安装器或全局 Codex 技能目录安装的情况。

发现源：

- 工作区技能目录：`.agents/skills` 加上特定宿主目录，如 `.codex/skills`、`.claude/skills`、`.cline/skills`、`.cursor/skills`、`.windsurf/skills`、`.opencode/skills`、`.agent/skills`、`.antigravity/skills`、`.hermes/skills` 以及 `.kiro/skills`。
- 全局技能目录：`$CODEX_HOME/skills`、`~/.codex/skills` 以及相对应的宿主全局技能目录。
- 嵌套的技能文件夹，包括 `.system/.../SKILL.md`。
- 来自 `global_data_dir` 的全局 Skills Router 状态。

空的提炼操作会发现所有可见的已安装技能。命名的提炼则只发现并报告匹配的技能集，同时将其与可见的路由表面进行对比。聊天格式的 `/skills-router refine` 将工作区发现的路由分配给 `workspace:<agent-id>`，但依然会与所有可见范围进行对比。

## 智能体斜杠指令

智能体桥接器（Agent Bridge）接受自然的口语化请求，并将其转化为严格的操作：

```text
/skills-router install <package> for me
/skills-router install <package> for all agents
/skills-router install <package> globally dry run
/skills-router install <package> skillset only needed skills for me
/skills-router uninstall <tool_id>
/skills-router index
/skills-router refine
/skills-router refine <skillset> <skillset>
/skills-router route <task>
/skills-router list
/skills-router inspect <tool_id>
/skills-router audit --tool <tool_id>
/skills-router watch --once
```

除非用户指出是全局的，否则桥接器默认将安装范围限制为 `workspace:<agent-id>`。`for all agents` 表示为默认的全部智能体目标集进行一次全局安装；自定义的 `--agent-target` 列表会通过目标感知路由查找来强制执行。解析器会去除如 `for me` 这样的修饰词，并返回用于智能体简短回答的 `human_summary`。

## MCP 工具集

`skills-router mcp` 暴露了：

- `get_agent_prompt`
- `parse_slash_command`
- `run_slash_command`
- `install_tool`
- `uninstall_tool`
- `index_routes`
- `refine_routes`
- `route_task`
- `list_tools`
- `inspect_tool`
- `watch_once`

请在输入人类聊天文本时使用 `run_slash_command`。只有当宿主已经有了干净的参数时，才使用结构化工具。MCP `content` 文本特意保持精简；完整的机器可读数据保存在 `structuredContent` 中。

结构化的 MCP 安装调用可以传入 `all_agents: true` 和可选的 `target_agents`。结构化路由调用可以传入 `target`，以便对调用者强制执行存储的目标列表。

## 支持的智能体宿主

| 目标 | 指令存放位置 |
| :--- | :--- |
| `antigravity` | `.agent/rules/skills-router.md`, `AGENTS.md` |
| `antigravity-cli` | `.agent/rules/skills-router.md`, `AGENTS.md` |
| `antigravity-ide` | `.agent/rules/skills-router.md`, `.antigravity/rules/skills-router.md`, `AGENTS.md` |
| `codex` | `AGENTS.md` |
| `cline` | `.clinerules/skills-router.md`, `AGENTS.md` |
| `cursor` | `.cursor/rules/skills-router.md`, `AGENTS.md` |
| `kiro` | `.kiro/steering/skills-router.md`, `AGENTS.md` |
| `claude` | `CLAUDE.md`, `.claude/commands/skills-router.md` |
| `github-copilot` | `.github/copilot-instructions.md`, `AGENTS.md` |
| `opencode` | `AGENTS.md`, `.opencode/agent/skills-router.md` |
| `hermes-agent` | `SOUL.md`, `AGENTS.md` |
| `windsurf` | `.windsurf/rules/skills-router.md`, `AGENTS.md` |

使用以下命令渲染特定目标的桥接文本：

```bash
skills-router prompt --target codex
skills-router prompt --target cursor
skills-router prompt --target windsurf
skills-router prompt --target codex --detail full
```

默认的 Prompt 是精简的，这样持久的智能体指令所消耗的 Token 就更少。只在生成文档或调试集成时，才使用 `--detail full`。

## 配置

`~/.skills-router/config.json` 可以覆盖 `SkillsRouterConfig` 的字段，例如：

```json
{
  "storage_backend": "memory",
  "workspace_root": "/path/to/workspace",
  "workspace_skill_dirs": [".agents/skills", ".codex/skills", ".cursor/skills"],
  "global_skill_dirs": ["$CODEX_HOME/skills", "~/.codex/skills", "~/.cursor/skills"],
  "pgvector_dsn": "postgresql://user:pass@localhost:5432/skills_router"
}
```

## 发布自动化

仓库 CI 会验证 Python、Node 包装器以及包构建。在推送标签时，工作流可以发布 npm 包装器，然后创建或更新 GitHub 发布。版本说明基于 `CHANGELOG.md` 中对应的条目生成，并附加如下链接：

- 标签特定的变更日志
- npm 软件包：https://www.npmjs.com/package/@the-long-ride/skills-router

## 路线图

- [x] 核心安装审核通道。
- [x] 面向主流 AI 智能体宿主的智能体桥接器（Agent Bridge）。
- [x] 带有已生成路由计划的完整包安装。
- [x] 带有目标感知路由的一键式多智能体安装。
- [x] `/skills-router index` 对账与冲突建议。
- [x] `/skills-router refine` 发现与路由提炼。
- [x] 通过 MCP 和 CLI 的动态路由查找。
- [x] 带有信任降级警报的 Registry Watch 守护进程。
- [ ] 用于应用人类选择的路由选择持久化 API。
- [ ] pgvector 原生生产环境迁移。
- [ ] 用于路由历史记录、审计日志和冲突决策的仪表板。

## 开源协议

该项目基于 **GNU 通用公共许可证 (GPLv3)** 授权。

由 **the-long-ride** 开发。
