# 协作式文创设计 Agent MVP：实施轮次

本计划以 `AGENT_DIALOGUE_MVP_AUDIT.md` 的现状为准，最多五轮。每轮只有一个核心目标；每轮完成后运行列出的聚焦测试并如实报告。除最后一轮外，不进行真实文本或图片模型调用。所有迁移必须是非破坏性 Alembic 增量迁移；不引入 Redis、Celery、PostgreSQL、pgvector、多 Agent、LoRA、LangChain、LangGraph、MCP 或第二套 Agent 框架。

共同保护项：现有 `POST /api/v2/cultural-products/generate`、`generation_logs` 历史、`generation_attempts` 幂等、SQLAlchemy MySQL 连接池和图片持久化必须保持既有合同。任何轮次都不得让 Spark 覆盖、重建或删除 `generation_logs`。

## 轮次一：持久会话骨架与状态机

**唯一核心目标**：建立 owner-scoped 的 Agent session/message/step 持久化和不调用模型的显式状态迁移。

**预计修改文件**：

- `backend/migrations/versions/0007_agent_dialogue_sessions.py`（新建）；
- `backend/domain/agent_dialogue.py`（新建：状态、DTO、Pydantic 请求/响应模型）；
- `backend/services/agent_dialogue_repository.py`（新建）；
- `backend/services/agent_dialogue_service.py`（新建：创建、查询、乐观并发、步骤写入）；
- `backend/routes/agent_dialogue.py`（新建）；
- `backend/app.py`（仅注册新 router）；
- `backend/tests/test_agent_dialogue_repository.py`（新建）；
- `backend/tests/test_agent_dialogue_routes.py`（新建）；
- `backend/tests/test_migration_0007_agent_dialogue.py`（新建）。

**完成条件**：

- 创建 session 得到 `created`，`GET` 只能读取本人 session；
- `agent_sessions`、`agent_messages`、`agent_steps` 均由迁移建立，`generation_log_id` 为 nullable FK；
- 状态只能按设计图转移；重复 `client_turn_id` / `decision_id` 和版本冲突可预测地返回，不调用模型；
- `text_revision_count` 受 0–4 边界约束；失败仍保留已有消息、步骤和结果 JSON；
- 定义稳定的 `AgentSessionDetailResponse` 与所有状态的成功 response envelope；所有顶层字段始终存在且类型稳定，缺失单对象为 `null`、集合为 `[]`；
- repository/database row 只能进入后端投影函数，绝不能直接作为 API response；增加 response-model 合同测试，覆盖 `created`、三个 waiting 状态、`completed` 与 `failed`；
- 不写 `generation_logs`，不创建 `generation_attempts`。

**聚焦测试**：新建迁移单测、repository CRUD/owner scope/顺序测试、FastAPI 路由鉴权和 409 冲突测试；回归 `backend/tests/test_fastapi_app.py`、`backend/tests/test_generation_tracking.py`。

## 轮次二：Brief 自然语言理解与确认

**唯一核心目标**：实现“消息 -> 受限 BriefProposal -> 自然语言说明 -> Brief 确认/局部修改/重新理解”，仍不生成正式产品文本或图片。

**预计修改文件**：

- `backend/domain/agent_dialogue.py`；
- `backend/services/agent_dialogue_service.py`；
- `backend/services/agent_brief_agent.py`（新建：Pydantic AI `BriefProposal`、最小模型工厂适配、上下文裁剪）；
- `backend/routes/agent_dialogue.py`；
- `backend/tests/test_agent_brief_agent.py`（新建，官方 `TestModel` / stub）；
- `backend/tests/test_agent_dialogue_routes.py`；
- `backend/tests/test_agent_dialogue_service.py`（新建）。

**完成条件**：

- 初始消息进入 `extracting_brief` 后停在 `waiting_brief_confirmation`；
- 内部 Brief 可通过既有 `validate_cultural_product_request` 归一化，所有默认值都出现在假设摘要；
- 用户不会看到 JSON 表单，只收到主题、产品、场景、风格、约束、假设的自然语言 assistant message；
- `confirm_brief` 才允许转入 `generating_product_text`；局部自然语言修改重新产生 Brief，`全部重新理解` 清除未确认下游内容；
- 每新增 Brief 字段，都同步更新 Pydantic response model、投影函数和 response-contract fixture；不得为方便而返回模型原始 JSON 或 provider payload；
- 旧 `POST /api/v2/cultural-products/generate` 响应合同不得发生变化；
- 不调用 RAG、正式文本模型、图片模型，也不触碰 `generation_logs`。

**聚焦测试**：`BriefProposal` schema、字段补全和边界注入测试、消息幂等/重新理解/非 owner 测试；回归 `backend/tests/test_cultural_product_contract.py`、`backend/tests/test_skill_routing_agent.py`。

## 轮次三：已确认 Brief 的文本设计与四次修订

**唯一核心目标**：在确认 Brief 后复用现有 RAG、text Skill 与结构化文本生成，支持最多四次自然语言文本修订并可恢复。

**预计修改文件**：

- `backend/domain/agent_dialogue.py`；
- `backend/services/agent_dialogue_service.py`；
- `backend/services/agent_product_text.py`（新建：RAG/Skill/现有 `AIGCService` 适配，`ProductDesignDraft` 归一化）；
- `backend/services/agent_context.py`（新建：最近消息与摘要裁剪）；
- `backend/routes/agent_dialogue.py`；
- `backend/tests/test_agent_product_text.py`（新建，全部 stub）；
- `backend/tests/test_agent_context.py`（新建）；
- `backend/tests/test_agent_dialogue_routes.py`；
- `backend/tests/test_agent_dialogue_service.py`。

**完成条件**：

- 仅在 `confirm_brief` 后调用 `retrieve_cultural_evidence`、可选 text `load_design_skill`、现有结构化文本逻辑；
- 结果停在 `waiting_text_feedback`，展示产品名、设计理念、文化转译、结构、材质、配色、场景以及 evidence/Skill 摘要；
- 用户文本反馈可造成一次整体或局部重生成，每次递增 `text_revision_count`，第五次请求稳定拒绝；
- `confirm_product_text` 才能进入视觉阶段；刷新可恢复最新确认稿、修订数和已完成步骤；
- 每新增产品设计字段，都同步更新 Pydantic response model、后端 projection 与合同测试；不返回模型原始 JSON 或 provider payload，也不改动旧快速生成响应；
- RAG 为 `creative_only` 不视为失败；不调用图片、不会写最终 `generation_logs`。

**聚焦测试**：成功/creative-only/RAG 失败/Skill 加载失败/输出校验失败、四次修订边界、上下文裁剪、恢复测试；回归 `backend/tests/test_aigc_service.py`、`backend/tests/test_cultural_product_contract.py`、`backend/tests/test_skill_assets.py`、`backend/tests/test_skill_routing_agent.py`、`backend/tests/test_generation_tracking.py`。

## 轮次四：视觉提示词确认与最小前端交互

**唯一核心目标**：建立已确认文本驱动的 `ImagePromptPackage` 与 `waiting_image_confirmation`，并接入最小页面以完成会话恢复、自然语言消息和按钮确认；不调用真实模型。

**预计修改文件**：

- `backend/domain/agent_dialogue.py`；
- `backend/services/agent_visual_prompt.py`（新建：visual Skill 选择/安全加载、正负提示词包）；
- `backend/services/agent_dialogue_service.py`；
- `backend/routes/agent_dialogue.py`；
- `backend/tests/test_agent_visual_prompt.py`（新建）；
- `backend/tests/test_agent_dialogue_routes.py`；
- `frontend/src/components/AgentDesignPanel.vue`（新建）；
- `frontend/src/components/AgentDialogueTimeline.vue`（新建）；
- `frontend/src/components/AgentDecisionCard.vue`（新建）；
- `frontend/src/services/agentDialogueApi.js`（新建）；
- `frontend/src/App.vue`（仅新增“快速生成 / 协作式设计”局部切换，不重写原表单）；
- `frontend/tests/e2e/agent-dialogue-stub.spec.js`（新建）。

**完成条件**：

- `ImagePromptPackage` 的输入只允许确认文本、规范化 Brief、精简 evidence 和可选 visual Skill；输出包括正向、负向、产品形态、材质、色彩、构图、场景和避免项；
- assistant 以自然语言展示视觉方向，`confirm_image_generation` 前绝不进入图片 provider；
- 前端从后端 session 读取 timeline、Brief 摘要、文本结果与视觉确认；刷新后以 `session_id` 恢复，不以 `setTimeout` 伪造步骤；
- 前端 API client 必须提供 normalize/adapter 边界，使用实际后端 `AgentSessionDetailResponse` fixture 开发，不自行猜测字段；对 `null`、空数组、旧 session 与未知额外字段安全渲染；
- DTO 数据不完整时显示“结果暂时无法展示”，不得误报“生成失败”；组件渲染异常不得自动发起重新生成请求；
- 增加 `completed`、`failed`、`waiting_brief_confirmation`、`waiting_text_feedback`、`waiting_image_confirmation` 的前端渲染测试；
- 快速生成的字段、请求地址、`Idempotency-Key`、结果区和历史读取保持不变；
- 使用 Mock/Stub 验证而非真实文本/图片模型。

**聚焦测试**：提示词包 contract、visual Skill kind 限制、确认前 provider 不可达、session 恢复 API、前端构建和 stub Playwright；回归 `backend/tests/test_round15c_image_workflow.py`、`backend/tests/test_generation_persistence.py`、`backend/tests/test_mysql_history.py`、`frontend/tests/e2e/generation-workspace.spec.js`。

## 轮次五：受控真实生成接线与页面演示验证

**唯一核心目标**：在图片确认后将新 Agent 路径接到现有图片生成/本地持久化/`generation_logs`，完成一条经授权的真实演示验证。

**预计修改文件**：

- `backend/services/agent_image_generation.py`（新建：调用现有 `AIGCService`、`image_storage`、`GenerationTracker` 的窄适配）；
- `backend/services/agent_dialogue_service.py`；
- `backend/services/mysql_service.py`（仅增加 Agent 最终记录的 allow-listed persistence/read DTO，如确有必要）；
- `backend/routes/agent_dialogue.py`；
- `backend/tests/test_agent_image_generation.py`（新建）；
- `backend/tests/test_agent_dialogue_routes.py`；
- `backend/tests/test_agent_dialogue_service.py`；
- `frontend/src/components/AgentDesignPanel.vue`；
- `frontend/tests/e2e/agent-dialogue.spec.js`（新建）；
- `docs/AGENT_DIALOGUE_MVP_AUDIT.md`（仅在实际结果与设计有差异时更新）。

**完成条件**：

- 只有 `waiting_image_confirmation + confirm_image_generation` 能进入 `generating_image`；每个 session 最多一次最终图片生成；
- 成功时写入一条受现有约束保护的 `generation_logs`，更新 `agent_sessions.generation_log_id`，完成状态为 `completed`；
- 失败时状态为 `failed`，已确认 Brief、文本和 `ImagePromptPackage` 完整保留；不得伪造图片、不得覆盖或删除 `generation_logs`；
- 检查历史 DTO：新记录必须是 allow-listed Agent 类型或明确保持在 Agent session 详情中，不能以破损普通图片卡片展示；
- 完成四条端到端一致性验证：`confirm_image_generation` 的即时成功 response 可展示；刷新后的 `GET agent session` 可恢复并展示；`GET /api/user/history` 不因 Agent 记录失败；历史详情展示与同一 `generation_log_id` 对应的结果；
- 验证数据库已写入但前端字段映射失败时，不显示为模型生成失败；Agent 记录绝不能作为结构损坏的普通图片卡；只有前端成功展示后才把真实演示记为通过；
- `generation_logs` 插入、session 更新与 completed 状态必须原子提交；若 HTTP 响应序列化失败，以 `GET` 恢复，不得重跑图片。对遗留的“日志已写/session 未更新”必须有按 `agent_session_id` 补偿绑定的可恢复策略，禁止再次调用图片模型；
- 在人工明确授权、有效测试账号和真实配置可用的前提下，才进行一次文本 + 图片 + 页面演示。未获授权或环境不可用时，只完成 mock/stub 验证并如实标记真实演示未运行。

**聚焦测试**：图片确认门禁、一次性生成、成功关联 `generation_log_id`、图片/provider/数据库失败恢复、owner scope、快速 V2 幂等回归；运行 `backend/tests/test_generation_tracking.py`、`backend/tests/test_generation_persistence.py`、`backend/tests/test_mysql_history.py`、`backend/tests/test_cultural_product_contract.py`、`backend/tests/test_round15c_image_workflow.py`、相关 Agent 测试、`npm run build` 与 Agent Playwright。真实调用不是单元测试替代品，必须单独报告。

## 各轮统一验收清单

每轮结束前：

1. 展示 `git diff`、待暂存的精确文件清单、测试通过/失败/跳过结果和建议 commit message；未经确认不暂存或提交。
2. 运行 `git diff --check`。
3. 不使用 `git add .`、`git add -A` 或通配符。
4. 不读取或输出 `.env` 密钥，不提交测试用户 JSON、日志、数据集、虚拟环境、`node_modules` 或 `dist`。
5. 不把模拟数据展示成生产统计；测试仅使用明确 stub/mock/test 路径。
