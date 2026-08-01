# Smart Cultural Platform

> **A Human-in-the-loop Cultural Creative Design Agent**

面向博物馆文创、文化 IP 衍生品和数字内容创作的工程化 AI Agent 平台。它以自然语言协作为入口，把文化研究、设计讨论、方案沉淀与图片生成组织为一条可追踪、可审批、可恢复的设计过程，而不是一次性 Prompt 包装器或固定表单生成器。

传统生成式应用通常是“一次输入 → 一次结果”。本项目将持续 Conversation、可切换的设计目标、版本化设计产物和有副作用的业务命令分层建模：用户可以先研究文化意象、比较方案或讨论修改；只有在需要保存正式设计稿、生成图片或归档设计时，系统才进入明确的 Human-in-the-loop确认路径。

运行时采用基于 Function Calling 与 Tool Call / Observation 回注的 ReAct-style Runtime。模型负责在上下文中选择直接回答或请求只读工具；Tool Policy、Action Policy 和服务端事务负责约束能力边界。这样既保留开放式对话的灵活性，也让正式产物、成本动作和历史版本保持可控。

## 核心能力

| 能力域 | 已实现能力 |
| --- | --- |
| 自然语言协作 | 文化资料研究、设计方向讨论、方案比较、文字稿批评、非正式创意探索，以及图片结果后的继续对话。 |
| ReAct-style Runtime | Pydantic AI 适配器、结构化 Function Calling、Tool Registry、Tool Policy、Tool Executor、Observation 回注、调用预算、运行事件与安全 Trace。 |
| Human-in-the-loop Action | Agent 只提出业务动作；服务端验证来源 Proposal；用户 approve / reject 后才允许执行副作用。 |
| Task-scoped Context | Conversation 与具体设计目标分离；消息、Runtime Run 与摘要可按 Design Task 隔离；没有 Task 时仍可普通聊天。 |
| Artifact 版本化 | Brief、产品文字设计稿、视觉方向、正式图片提示与生成图片均可保存为不可变 Artifact；支持 confirmed、superseded、父子版本关系与历史保留。 |
| 图片 Action | 支持 Conversation Snapshot、Confirmed Artifact 和旧图片再生成三种来源；以 generation_logs 记录追加式生成事实，并产生 generated_image Artifact。 |
| Agent Workspace | Vue 全高三栏工作区：多 Conversation、当前设计、设计档案、图片版本与上下文确认卡；协作式设计为默认创作入口。 |
| 快速生成 | 保留结构化 Brief 驱动的快速生成、历史记录、评分与下载能力，与协作式设计并列可用。 |

## 从固定 Workflow 到可控 Agent

文创设计会在研究、讨论、比较、试稿和修改之间反复切换。平台不会把用户锁定在单一的“Brief → 文案 → 图片 → 结束”页面流程中：

```text
自然对话
├─ 文化研究与资料查询
├─ 方案解释、比较与设计批评
├─ 非正式创意构思
├─ 保存正式 Artifact
├─ 请求图片生成或再生成
├─ 用户审批副作用
└─ 回到持续对话
```

这里的边界是清晰的：**Workflow Boundary** 负责确定性的业务约束和数据一致性；**ReAct Runtime** 负责开放式推理、工具选择与自然语言输出；**Human-in-the-loop** 负责保存、生成等副作用的授权。Conversation、Design Task、Artifact、Action 与 Runtime Run 各自拥有独立生命周期，图片完成不会关闭 Conversation 或 Task。

## 系统架构

```mermaid
flowchart LR
    U[设计用户] --> UI[Vue 3 Agent Workspace]
    UI --> API[FastAPI API Layer]

    API --> CS[AgentRuntimeTurnService]
    CS --> RT[DesignConversationService]
    RT --> RE[ReAct-style Runtime Engine]
    RE --> LLM[Pydantic AI / DashScope-compatible Model]
    RE --> TR[Tool Registry]
    TR --> TP[Tool Policy]
    TP --> TE[Tool Executor]
    TE --> OBS[Structured Observation]
    OBS --> RE

    CS --> CTX[RuntimeContextBuilder]
    CTX --> MYSQL[(MySQL)]

    API --> AP[Action Policy]
    AP --> HITL[Explicit User Approval]
    HITL --> EX[Action Executor]
    EX --> AR[Artifact Repository]
    EX --> IP[Image Generation Port]
    IP --> GL[(generation_logs)]
    AR --> MYSQL
    API --> MYSQL
```

### ReAct Runtime：模型选择，服务端执行

```mermaid
sequenceDiagram
    participant User
    participant Runtime as Runtime
    participant Model as Pydantic AI Model
    participant Policy as Tool Policy
    participant Tool as Read-only Tool

    User->>Runtime: user turn + task-scoped context
    Runtime->>Model: messages + context + tool schema
    alt Direct response
        Model-->>Runtime: validated ConversationReply
    else Tool call
        Model-->>Runtime: structured ToolCall
        Runtime->>Policy: tool / risk / budget validation
        Policy->>Tool: execute approved call
        Tool-->>Runtime: structured Observation
        Runtime->>Model: observation-backed follow-up
        Model-->>Runtime: final ConversationReply
    end
    Runtime-->>User: natural-language response first
```

模型不会直接操作数据库、Action 或图片 Provider。`ToolExecutor` 只消费 Registry 中注册的能力，并受 Tool Policy、工具风险等级和每回合调用预算限制；最终面向用户的结果统一为经过 Pydantic 校验的 `ConversationReply`。运行 Trace 保存安全事件与错误摘要，不展示或持久化隐藏推理链。

### 领域模型：对话、任务、产物与动作分层

```mermaid
erDiagram
    CONVERSATION ||--o{ DESIGN_TASK : contains
    DESIGN_TASK ||--o{ ARTIFACT : owns
    DESIGN_TASK ||--o{ ACTION : receives
    DESIGN_TASK ||--o{ RUNTIME_RUN : scopes
    ACTION ||--o{ ARTIFACT : produces
    ARTIFACT ||--o{ ARTIFACT : parent_version
    RUNTIME_RUN ||--o{ ACTION : proposes
    GENERATION_LOG ||--o{ ARTIFACT : records
    GENERATION_LOG ||--o{ ACTION : records
```

`Conversation` 映射到持久会话，保存持续协作上下文；`DesignTask` 表示一个可切换的设计目标；`Artifact` 是正式且可版本化的结果；`Action` 是需要确认或会产生副作用的命令；`Runtime Run` 则仅表示一次模型运行。Action 的来源 Artifact 集合以受校验引用保存，产物与生成日志通过外键记录来源关系。

### Human-in-the-loop Action 生命周期

```mermaid
stateDiagram-v2
    [*] --> requested: server validates runtime proposal
    requested --> approved: user approves
    requested --> rejected: user rejects
    approved --> running: executor claims
    running --> completed: effect persisted
    running --> failed: safe failure
    running --> recovery_required: external outcome is uncertain
    recovery_required --> running: verified recovery only
```

`requested`、`approved`、`rejected`、`running`、`completed` 与 `failed` 是 Action 合同状态。`recovery_required` 是外部图片结果不确定时的保护性响应：系统停止自动重试，避免重复扣费或重复产物；它不是把一次图片生成伪装成理论上的绝对 exactly-once 调用。

## Agent 工程化设计

### Runtime 与业务领域解耦

- **Conversation**：管理持续自然语言协作，状态为 `active` 或 `archived`，不以“图片完成”作为终止条件。
- **Design Task**：管理一个具体设计目标，状态包括 `exploring`、`active`、`paused`、`closed`；同一 Conversation 可以保存多个 Task 并切换当前设计。
- **Artifact**：保存正式结果。Brief、`product_design_text`、`visual_direction`、`image_prompt` 与 `generated_image` 都具有独立 ID、内容哈希、版本号、来源 Run / Action 和可选父版本。
- **Action**：建模 `save_brief`、`save_design_text`、`apply_revision`、`build_visual_direction`、三种图片动作与 `archive_task`，而不是让一个 Session 状态字段承担所有业务语义。
- **Runtime Run**：记录一次模型—工具执行，与 Conversation 或 Task 关联，但 `completed` 只表示本次运行结束，不表示设计会话结束。

### Prompt、结构化输出与 Provider Adapter

`backend/agents/design_conversation` 将系统指令、上下文与工具 schema 组合为设计对话定义。`ConversationReply` 以自然语言 `message` 为主，按需携带未保存的 Artifact Proposal 或需确认的 Business Action：

- Pydantic Structured Output 校验返回结构；
- Provider 输出可经过受控 repair 后再次验证；
- 不可恢复的结构化失败走安全 `system_fallback`，不会从普通文本猜测业务动作；
- Artifact Proposal 与正式 Artifact 分离，非正式构思不会被静默写入设计档案；
- 输出投影避免向前端泄漏内部协议文本、完整 Provider 原始响应或隐藏思维链。

这条链路对应 Prompt Engineering、Schema Validation、Output Repair 与 Provider Adapter 等 AI 应用工程能力。

### Tool、Skill 与 Policy 边界

设计对话注册了受控只读工具，包括当前设计状态检查、文化知识检索、版本化设计 Skill 加载和正式候选约束校验。工具返回的是结构化 Observation，Runtime 不把工具内部实现直接暴露给模型或客户端。

- **Tool Registry** 管理名称、输入输出模型、风险等级、可用 Agent 与调用上限；
- **Tool Policy** 审核工具、风险和预算；
- **Tool Executor** 执行通过审核的调用，并产生安全 Observation；
- **Skill Registry** 加载固定版本的文创表达与产品呈现指南；
- 本地 RAG 以 BM25、`jieba` 和文化语料提供证据。资料不足时使用 `creative_only` 语义，不把创意联想包装成历史事实。

### Task-scoped Context，而不是跨会话记忆

`RuntimeContextBuilder` 以 `session_id` 和可选 `task_id` 组织上下文：当前 Task 的近期消息、对应摘要和最新 confirmed Artifact 可以进入本轮输入；其他 Task 的消息、摘要、产物、约束和未解决问题不会混入。没有 Task 时，系统只使用 Conversation 层的通用上下文，仍支持研究和普通设计讨论。

Context Summary 采用受预算约束的增量压缩与 scope key，保存事实来源类别，避免把所有历史消息、完整工具观察或旧版本全文重复发送给模型。它是 Session / Task 内的上下文管理，不被描述为跨 Session 用户 Memory。

### 可审批副作用、幂等与可恢复执行

业务副作用走明确链路：

```text
verified Runtime Proposal
→ Action Policy
→ requested Action
→ user approve / reject
→ executor claim
→ transactionally persist effect
```

- 客户端不能直接写 Artifact、替换服务端冻结的 Proposal Snapshot、Prompt 或来源 Artifact；
- Action 创建、审批和执行均使用 idempotency key 与 canonical request hash；`client_turn_id` 用于 Runtime Turn 去重；
- Repository 在 owner scope 内使用事务和 `SELECT ... FOR UPDATE` 处理并发 claim、Task 版本冲突与 Artifact 版本分配；
- Artifact 内容不可原地覆盖；新版本递增，旧 confirmed 版本可标记为 `superseded` 并保留历史；
- 图片 Action 在正常 claim / replay 路径上只调用一次 Provider；外部结果未知时返回 recovery-required，不自动再次调用；
- `generation_logs` 是图片生成完成事实的追加式来源，生成图片 Artifact 与 Action 均保存对应关联。

### 可观测性与数据一致性

Runtime Run、Runtime Event、工具请求/完成事件、预算快照和稳定错误码形成安全执行 Trace。MySQL 通过 PyMySQL / SQLAlchemy Engine 连接池提供持久化，Alembic 以增量迁移演进 Schema；领域表提供 owner scope、外键、检查约束、版本唯一约束与安全 downgrade 保护。敏感 API Key、隐藏推理链和完整 Provider 原始响应不写入 Action、Artifact 或用户可见 Trace。

## Agent Workspace

协作式设计是默认创作入口。Vue 工作区的三栏职责按用户心智模型划分：

```text
左栏：Conversation 列表
中栏：自然语言对话、Proposal、Action 确认与图片结果
右栏：当前设计、正式 Artifact、图片版本与待处理动作索引
```

- 新对话先作为本地草稿存在，首条消息发送时才创建持久 Session；
- Session 切换保留各自的草稿、消息、错误与当前设计，不串状态；
- “当前设计”是 Design Task 的产品化名称，可轻量创建和选择；
- Assistant Turn 会携带当前 `task_id`；Task 切换后，下一轮上下文与档案随之切换；
- 未保存 Proposal 只出现在对话流中，执行完成的正式 Artifact 才进入右侧设计档案；
- 图片版本保留父子关系，生成后输入框仍可继续对话；
- 中等与窄屏优先保留聊天区，档案和会话列表折叠为可访问的抽屉层级。

## 典型执行流程

### 1. 普通设计讨论

```text
用户提出文创需求
→ Runtime 构建 Task-scoped Context
→ 模型直接返回自然语言方案
→ 不创建 Artifact，也不触发副作用
→ Conversation 继续
```

### 2. 保存正式 Brief

```text
模型提出 save_brief
→ 前端显示服务端派生的确认卡
→ 用户确认
→ request / approve / execute
→ 创建 Brief V1 Artifact
→ 后续修改形成新版本，不覆盖历史内容
```

### 3. 直接从对话生成试稿图片

```text
Conversation Snapshot
→ 服务端冻结已确认约束与暂定假设
→ 用户确认展示方式与成本
→ Action Executor / Image Generation Port
→ generation_logs append
→ generated_image Artifact
→ Conversation 与 Task 继续 active
```

这种路径不要求先伪造正式 Brief：`source_type=conversation_snapshot` 会明确标记它来自对话快照。

### 4. 基于旧图片再次生成

```text
V1 图片 Artifact
→ 用户提出修改
→ 新 regenerate_image Action
→ 用户再次批准
→ 新 generation_log 与 V2 图片 Artifact
→ parent_artifact_id 指向 V1
```

旧图片和旧生成日志始终保留；系统不会因为生成完成而自动开始下一张图片。

## 技术栈

| Layer | Technology |
| --- | --- |
| Frontend | Vue 3、Vite、Axios、Chart.js、Playwright |
| Backend | FastAPI、Pydantic、PyJWT、Uvicorn |
| Agent Runtime | Pydantic AI、OpenAI-compatible Function Calling、ReAct-style Tool Loop |
| Model Provider | DashScope-compatible text endpoint；图片服务经已有 AIGC adapter 与 Image Generation Port 适配 |
| Persistence | MySQL 8、PyMySQL、SQLAlchemy Engine、Alembic |
| Retrieval & Skills | BM25、`rank-bm25`、`jieba`、本地文化语料、版本化 Skill Registry |
| Offline Data | Hive、HDFS、PyHive、PySpark、Pandas |
| Validation | pytest、MySQL 集成测试、Fake Provider、Playwright Mock E2E |

## 目录结构

```text
smart-cultural-platform/
├── backend/
│   ├── agents/
│   │   ├── actions/                 # Action policy 与 executor
│   │   ├── context/                 # Task-scoped Context V2
│   │   ├── design_conversation/     # Prompt、输出合同与设计工具
│   │   ├── runtime/                 # Runtime、policy、registry、adapters
│   │   └── skills/                  # 版本化文创设计 Skill
│   ├── domain/                      # Conversation / Task / Artifact / Action DTO
│   ├── routes/                      # FastAPI HTTP 边界
│   ├── services/                    # Repository、业务服务、图片端口
│   ├── migrations/versions/         # Alembic 增量迁移
│   └── tests/                       # 单元、路由、集成与回归测试
├── frontend/
│   ├── src/components/              # Workspace 与对话组件
│   ├── src/services/                # Agent API client
│   └── tests/e2e/                   # Playwright E2E
├── scripts/                         # 数据初始化与离线辅助脚本
└── alembic.ini
```

## 快速开始

### 环境要求

- Python 3.10+；
- Node.js 18+；
- MySQL 8（建议使用独立开发数据库）；
- 真实模型调用需要本地配置 DashScope 凭据。默认测试使用 Fake / Mock Provider，不需要真实额度。

### 安装依赖

在仓库根目录执行：

```bash
# 后端
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt

# 前端
cd frontend
npm ci
cd ..
```

### 配置本地环境

复制 `backend/.env.example` 为 `backend/.env`，仅在本机填入实际配置，禁止提交该文件。应用配置读取的主要变量包括：

```env
JWT_SECRET=replace_with_a_local_secret
JWT_ALGORITHM=HS256

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=app_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=smart_cultural_platform

DASHSCOPE_API_KEY=your_key
DASHSCOPE_OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_API_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_TEXT_MODEL=qwen3.7-plus
DASHSCOPE_IMAGE_MODEL=wan2.6-t2i

AGENT_RUNTIME_PROVIDER=dashscope
AGENT_RUNTIME_MODEL=qwen3.7-plus
AGENT_RUNTIME_ALLOW_REAL_MODEL=false
```

`AGENT_RUNTIME_ALLOW_REAL_MODEL` 默认关闭；需要受控真实 Runtime 验证时才显式开启。迁移使用独立的 `MIGRATION_DATABASE_URL`，避免把目标数据库隐含在命令中：

```bash
export MIGRATION_DATABASE_URL='mysql+pymysql://app_user:your_password@127.0.0.1:3306/smart_cultural_platform'
backend/.venv/bin/alembic -c alembic.ini upgrade head
```

### 启动服务

```bash
# 终端一：FastAPI（仓库根目录）
PYTHONPATH=. backend/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 5000 --reload

# 终端二：Vue
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000 --strictPort
```

浏览器访问 `http://127.0.0.1:3000/index.html`，健康检查为 `http://127.0.0.1:5000/api/health`。

## API 能力

所有 Agent API 位于 `/api/v2/agent-design`，通过 Bearer JWT 推导 owner，不接受客户端指定 owner。

| 域 | 代表性接口 |
| --- | --- |
| Conversation / Runtime | `POST /sessions`、`GET /sessions`、`POST /sessions/{session_id}/assistant-turns`、`GET /sessions/{session_id}/assistant-turns/{run_id}` |
| Runtime Proposal | `GET /sessions/{session_id}/assistant-turns/{run_id}/action-proposal` |
| Design Task | `GET/POST /sessions/{session_id}/tasks`、`POST /sessions/{session_id}/tasks/{task_id}/select`、`GET /sessions/{session_id}/available-actions` |
| Action | `POST /sessions/{session_id}/tasks/{task_id}/actions`、`POST /actions/{action_id}/approve`、`POST /actions/{action_id}/reject`、`POST /actions/{action_id}/execute` |
| Artifact | `GET /sessions/{session_id}/tasks/{task_id}/artifacts`、`GET /sessions/{session_id}/tasks/{task_id}/artifacts/{artifact_id}` |
| 兼容接口 | 既有 `/messages` 与 `/decisions` 仍可读取和服务历史线性会话；新协作入口使用 `assistant-turns` 与显式 Action。 |

## 测试与质量

项目以不同层级覆盖 Agent 核心路径：

- Runtime、Tool Policy、结构化输出、Provider Adapter 与安全 fallback 单元测试；
- Action Policy、审批、执行、Artifact 版本、owner scope 和幂等测试；
- Task-scoped Context 隔离、会话 Runtime Turn 和兼容接口回归；
- Alembic 迁移与 MySQL 集成测试，覆盖约束、事务、版本唯一性与安全 downgrade；
- Fake Image Provider 测试，覆盖单次调用、重放、失败与 recovery-required 边界，不消耗真实图片额度；
- Playwright Mock E2E 覆盖 Agent Workspace、任务选择、确认卡、档案与图片版本交互；
- 前端 production build、FastAPI schema 检查与 `git diff --check` 作为发布前质量门。

常用本地命令：

```bash
# 后端测试
backend/.venv/bin/python -m pytest backend/tests -q

# Agent Runtime 与领域聚焦测试
backend/.venv/bin/python -m pytest \
  backend/tests/test_agent_runtime_executor.py \
  backend/tests/test_agent_action_policy.py \
  backend/tests/test_agent_action_executor.py \
  backend/tests/test_agent_image_actions.py \
  backend/tests/test_context_v2.py -q

# 前端构建与浏览器测试
cd frontend
npm run build
npm run test:e2e
```

## 安全设计

- owner-scoped Repository 与 JWT 身份边界防止跨用户读取 Session、Task、Artifact 或 Action；
- Action 仅从已完成且经结构化验证的 Runtime Proposal 派生，普通消息与 `system_fallback` 不会触发业务命令；
- 用户显式确认保存与图片成本；前端只能提交批准字段白名单，不能覆盖服务端冻结快照；
- 客户端没有任意创建、修改或删除正式 Artifact 的接口；Legacy projection 始终只读；
- Action、审批、执行和图片生成均有幂等键、请求哈希和并发 claim 边界；
- API Key、完整 Provider 原始响应、内部 Tool Observation 与隐藏 Chain-of-Thought 不进入用户可见 DTO、Artifact 或 Action Trace；
- 图片外部结果不确定时阻止自动重试，等待明确恢复处理，避免重复费用与重复产物。

## 当前项目边界与改进方向

平台聚焦文创设计场景中的持续对话、受控工具调用、正式设计产物沉淀与需确认的生成动作。它以 Conversation、Design Task、Artifact、Action 和 Runtime Run 的分层合同支撑多轮协作，并保留快速生成与既有历史能力。

在这一边界内，后续可以围绕更丰富的文化资料覆盖、更多可配置的设计 Skill、Provider 结果恢复体验和端到端可观测性继续增强；这些演进保持在现有的 Task-scoped Context、Human-in-the-loop 与追加式生成记录边界之内，不改变正式产物可追溯、用户确认副作用和图片版本保留的核心原则。
