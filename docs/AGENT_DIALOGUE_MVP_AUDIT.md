# 协作式文创设计 Agent MVP：现状审查与接入设计

## 范围与结论

本文件基于 `feat/agent-dialogue-mvp` 当前工作区的只读审查。未读取 `backend/.env`，未调用文本或图片模型，也未修改现有业务、数据库结构、前端或依赖版本。

结论是：现有项目已经具备可复用的 FastAPI 路由、受控 RAG、版本化 Skill、结构化文本生成、WAN 图片生成、`generation_logs` 持久化及用户历史读取边界，但尚不具备面向用户的多轮会话、确认状态机或“已确认产品设计文本驱动图片提示词”的生产链路。MVP 应新增一个独立的协作式入口；不得替换 `POST /api/v2/cultural-products/generate`，也不得把 Agent 会话误当作 `generation_attempts`。

旧 `FAST_AGENT_PRD.md` 的“自主执行 / 产品候选”方案仅作历史参考。此 MVP 以本轮给定的 Brief 确认、最多四次文本修订和图片确认状态机为准。

## 1. 当前快速生成表单与请求合同

前端生成工作区是 `frontend/src/App.vue`。它构造 `brief_version: "1.0"` 与 `brief`，提交到 `POST /api/v2/cultural-products/generate`。

### 1.1 用户可见的必填字段

| 字段 | 前端表现 | 后端要求 |
| --- | --- | --- |
| `brief.product_type` | 产品类型，必填输入框 | 必填，字符串 |
| `brief.presentation_mode` | 正反面 / 三视图 / 单品主视图，默认 `single_hero` | 必填且必须为 `flat_front_back`、`three_view`、`single_hero` 之一 |
| `brief.cultural_source.source_type` | 来源类型，下拉默认 `artifact` | 必填，字符串；当前后端不枚举其值 |
| `brief.cultural_source.name` | 文化原型或灵感来源，必填输入框 | 必填，字符串 |
| `brief.form_and_material` | 造型与材质，必填文本域 | 必填，最长 500 字符 |
| `brief.use_case` | 使用场景，必填输入框 | 必填，字符串 |
| `brief.visual_direction.preset_id` | 由画面方向卡片 / 自定义维度产生 | 必填，字符串 |
| `brief.visual_direction.cultural_context` | 文化语境选择 | 必填，字符串 |
| `brief.visual_direction.medium` | 表现媒介选择 | 必填，字符串 |
| `brief.visual_direction.palette` | 色彩倾向选择 | 必填，字符串 |
| `brief.visual_direction.composition` | 构图气质选择 | 必填，字符串 |

条件必填项：

- `presentation_mode=flat_front_back`：`back_design_requirements` 必填。
- `presentation_mode=three_view`：`front_design_requirements`、`back_design_requirements`、`side_design_requirements` 均必填。
- `presentation_mode=single_hero`：三个视图要求均可为空。

可选项：`cultural_source.era`、`cultural_source.creator`、`confirmed_facts`（至多 8 条）、`target_audience`、`visual_direction.additional_requirements`。前端将画面方案映射为 `visual_direction`；后端会限制拼接后的方向文本不超过 100 字符。

**MVP Brief 补全规则**：Agent 必须产出上述完整内部 Brief，且把默认或推断值明确放入“主动补充的假设”。不能把 Pydantic JSON 直接作为用户表单展示；用户看到的是文化主题、产品类型、场景、风格、造型/材质、展示方式、约束和假设的自然语言说明。确认前不得调用正式产品文本生成。

## 2. 当前前端到后端的真实生成链路

```text
App.vue 表单与 Axios（JWT + Idempotency-Key）
  -> POST /api/v2/cultural-products/generate
  -> backend/routes/generation.py 的 FastAPI 路由
  -> backend/routes/_bridge.py
  -> backend/routes/api.py::generate_cultural_product_api
  -> validate_cultural_product_request
  -> GenerationTracker / generation_attempts
  -> CulturalRagService.retrieve
  -> AIGCService.generate_cultural_product_text_with_evidence
  -> build_image_prompt + build_image_negative_prompt
  -> AIGCService.generate_image_from_prompt（必要时先生成参考图再 edit）
  -> image_storage.persist_generated_image
  -> INSERT generation_logs
  -> App.vue 结果区、GET /api/user/history、详情弹窗
```

路由已是原生 FastAPI，但生成处理函数仍通过 `_bridge.py` 调用兼容层中的同步业务函数。新增 Agent 路由应使用同一认证与 JSON 响应约定；第一版可采用兼容层以降低改动面，但不应继续把会话状态逻辑堆入 `api.py`，应放入新的领域服务。

当前快速生成在同一请求中完成检索、文本、图片与 `generation_logs` 写入。`GenerationTracker` 以用户、Brief hash 和可选 `Idempotency-Key` 维护一次最终生成尝试，并将成功行关联到 `generation_logs.id`。这条原流程必须原样保留。

## 3. Pydantic AI、RAG 与 Skill 现状

### 3.1 Pydantic AI

- 锁定依赖为 `pydantic-ai-slim[openai]==2.14.1`；本 MVP 不升级到预发布版本，也不需要 LangChain、LangGraph、OpenAI Agents SDK 或 MCP。
- `backend/agents/skill_routing.py` 存在 `Agent`、`RunContext`、`UsageLimits` 的受控路由器。它使用 Pydantic `SkillRoutingOutput` 结构化输出、禁止并行工具调用、限制 4 次模型请求和 3 次工具调用。
- 该路由器只暴露 `retrieve_cultural_sources` 与 `load_generation_skill`；真实模型默认关闭，`run_skill_routing(..., model=None)` 会返回 `REAL_AGENT_DISABLED`。它当前未注册到 FastAPI 生产路由。
- `evaluation/round17c_runner.py` 是另一条离线/实验性文本 Skill 流程：通过 `AsyncOpenAI` + `AlibabaProvider` + `OpenAIChatModel` 构造模型，规划阶段只可调用一次文本 `load_generation_skill`，最终阶段以 Pydantic 结构化输出返回 `Round17CFinalOutput`。`backend/services/round17c_business.py` 将此文本实验与图片业务隔离。
- 当前仓库没有 Pydantic AI `message_history` 的生产使用方式，也没有会话消息表。新 MVP 需要自行从数据库恢复并裁剪上下文；不能误称已经有多轮消息续接能力。

模型配置仅从 `backend/config/__init__.py` 加载。与此功能相关的环境变量名称包括 `DASHSCOPE_API_KEY`、`DASHSCOPE_OPENAI_BASE_URL`、`DASHSCOPE_API_BASE_URL`、`DASHSCOPE_TEXT_MODEL`、`DASHSCOPE_TEXT_REASONING_EFFORT`、`DASHSCOPE_IMAGE_MODEL`、`DASHSCOPE_IMAGE_EDIT_MODEL`、`DASHSCOPE_IMAGE_SIZE` 及对应超时变量；本审查未读取其值。

### 3.2 RAG

`backend/rag/service.py::CulturalRagService` 使用本地 Met Open Access 小型语料和 BM25。它从产品类型、文化来源、时代、作者、画面方向和确认事实构造查询，最多返回三条来源；只有满足最低相关度且不含歧义的结果才作为 evidence。输出为受控的 `source_id`、标题和官方字段，不把检索别名送入 evidence。

生产图文路径允许 `grounded`、`creative_only`、`insufficient_evidence` 三种证据状态。无可靠 RAG 不是失败；模型不得据此虚构历史事实。新工具 `retrieve_cultural_evidence` 应直接包装此服务，并保存 source ID、状态、原因和精简 evidence 摘要。

### 3.3 Skill

`backend/agents/skill_registry.py` 提供固定、带版本和完整性校验的 3 个 text Skill 与 3 个 visual Skill：

- text：`museum-product-explainer`、`retail-product-copy`、`social-cultural-story`；
- visual：`heritage-motif-translation`、`product-material-realism`、`commercial-product-presentation`。

视觉 Skill **确实存在**，但当前只是 Registry 资产和 `skill_routing.py` 的结构化路由输出：生产 `POST /api/v2/cultural-products/generate` 从未调用该路由器或 `load_skill`。特别是 `commercial-product-presentation` 的说明要求把结果写入实验性 `image_design_spec`，没有定义生产级正向/负向图片提示词包。因此不能宣称生产图片已“根据确认的产品设计文本选择视觉 Skill”。

## 4. 文本与图片的当前真实行为

### 4.1 文本模型输出

`backend/prompts/cultural_product_v1.py` 要求文本模型仅返回 JSON，字段严格为：

```text
product_name
creative_origin { text, source_type }
design_concept
cultural_meaning { text, source_type }
selling_points[3..5]
factual_background { text, source_type }
used_source_ids[]
evidence_status
```

`AIGCService.generate_cultural_product_text_with_evidence` 使用现有 DashScope OpenAI-compatible Responses 客户端，随后通过 `validate_text_response` 校验完整结构和来源边界。此结果可作为 Agent 的“产品设计文本”基础；但它没有分别输出产品结构、材质、配色、场景等独立字段。MVP 可以在新的、受限的 Pydantic `ProductDesignDraft` 中把现有字段归一化为展示分区，同时保留原始已验证输出，避免修改当前快速生成合同。

### 4.2 图片提示词

生产路径在文本完成后调用：

```python
build_image_prompt(brief, text_result['product_name'])
build_image_negative_prompt()
```

正向提示词含产品类型、产品名、**原始** `form_and_material`、**原始**文化来源名，以及原始 `visual_direction.medium/palette/composition` 和 `presentation_mode` 布局；不读取 `design_concept`、`creative_origin`、`cultural_meaning`、`selling_points`、RAG evidence 或视觉 Skill 正文。负向提示词为固定的“人物、手持、场景、文字、水印、重复产品”等列表。

因此，当前图片生成本质上只使用最初表单 Brief 的 style/prompt 派生字段和文本模型给出的产品名。对 `flat_front_back` 或 `three_view`，先生成参考图，再调用现有图片编辑模型组织版式；`single_hero` 直接生成一张图。这与本 MVP 的“一轮图片、无图片修改”不冲突：Agent 新路径应在确认后选择与 Brief 兼容的现有调用分支，但不暴露编辑能力。

## 5. 建议的显式业务状态机与领域工具

```text
created
  -> extracting_brief
  -> waiting_brief_confirmation
  -> generating_product_text
  -> waiting_text_feedback
  -> building_visual_prompt
  -> waiting_image_confirmation
  -> generating_image
  -> completed
                    \-> failed
```

状态迁移只能由后端服务执行。模型只在 `extracting_brief`、文本生成与视觉提示词构造等受限阶段输出 Pydantic 模型；它不决定状态，不保存隐藏思维链，不访问数据库、网络、路径或任意工具。

建议的内部能力及复用关系：

| 能力 | MVP 处理 | 复用 / 新增 |
| --- | --- | --- |
| `retrieve_cultural_evidence` | 调用后保存精简证据和来源 ID | 包装 `CulturalRagService` |
| `load_design_skill` | 从固定 Registry 读取一项 text 或一项 visual Skill，并记回执/hash | 复用安全 `load_skill`；按阶段限制 kind |
| `generate_product_text` | Brief 已确认后，检索、可选 text Skill、调用现有结构化文本生成 | 复用 `AIGCService` 与 prompt 校验；新增 Agent 编排适配 |
| `build_visual_prompt` | 从已确认文本、Brief、evidence 与可选 visual Skill 形成包 | 新增，不调用图片模型 |
| `generate_product_image` | 仅在图片确认后调用现有 WAN 与本地图片持久化 | 包装现有 `AIGCService` / `image_storage` |
| `save_generation_result` | 图片成功后写一条最终在线结果 | 复用 `generation_logs` 写入边界；新增会话关联更新 |

工具不是为了凑数量：实现时可以把它们作为显式服务方法，而非把每一步都注册成可自由循环的模型工具。Pydantic AI 可用于 Brief 提取、受限 Skill 选择与结构化提示词输出；FastAPI 服务负责状态、权限、预算和持久化。

## 6. 新增模型与图片提示词层

### 6.1 内部 Pydantic 输出

建议新增以下仅服务端使用的模型（名称可在实施时按领域命名调整）：

- `BriefProposal`：完整快速生成 Brief、`understanding`（主题/产品/场景/风格/约束）、`assumptions[]`、`missing_or_defaulted_fields[]`。
- `ProductDesignDraft`：保留当前已验证文本输出，并增加归一化展示字段 `structure`、`materials`、`color_plan`、`usage_scene`、`revision_summary`。这不是给旧 V2 接口新增字段。
- `ImagePromptPackage`：`positive_prompt`、`negative_prompt`、`required_constraints[]`、`product_form`、`materials`、`color_plan`、`composition`、`scene`、`avoid[]`、`presentation_mode`、`selected_visual_skill`（可空）、`evidence_source_ids[]`、`user_facing_direction`。

`ImagePromptPackage` 的正向提示词必须优先使用确认后的 `ProductDesignDraft`，再以结构化 Brief 补齐硬约束；RAG 仅以实际 evidence 支持文化描述，视觉 Skill 只提供已校验的设计约束。固定负向约束必须合并当前 `build_image_negative_prompt()`，并保留展示方式的白底、完整产品、无水印/文字等限制。模型输出和 Pydantic 校验失败时，状态为 `failed`，但此前确认的 Brief/文本仍可恢复查看。

## 7. MySQL 最小持久化设计

优先新增三张表，不新增 `agent_artifacts`：

### `agent_sessions`

独立列：`id`（UUID/CHAR(36)）、`user_id`、`status`、`current_stage`、`text_revision_count`（0–4）、`generation_log_id`（nullable FK 至 `generation_logs.id`）、`failure_stage`、`error_code`、`created_at`、`updated_at`、`completed_at`、`version`（乐观并发控制）。建立 `(user_id, updated_at)` 与 `(user_id, id)` 索引。

JSON 列：`brief_json`（当前规范化 Brief 与假设摘要）、`confirmed_text_json`（当前确认设计稿及原始已验证文本）、`image_prompt_json`（确认前提示词包）、`context_summary_json`（早期对话和证据摘要）、`error_json`（脱敏、稳定错误细节）。`generation_log_id` 必须独立列，便于 owner-only history/detail 关联和完整性检查。

### `agent_messages`

独立列：`id`、`session_id` FK、`sequence_no`（session 内唯一）、`role`（`user` / `assistant` / `system`）、`message_type`（`request`、`brief_summary`、`text_feedback`、`visual_summary`、`decision_receipt`、`error`）、`content_text`、`created_at`。`content_json` 可选，保存可展示的局部字段/引用 ID，不能保存模型隐藏推理或完整 provider payload。索引 `(session_id, sequence_no)`。

### `agent_steps`

独立列：`id`、`session_id` FK、`ordinal`、`stage`、`status`、`tool_name`（nullable）、`skill_id`/`skill_version`（nullable）、`started_at`、`finished_at`、`latency_ms`、`error_code`。JSON 列：`input_summary_json`、`output_summary_json`、`tool_result_summary_json`、`error_json`。保留工具调用及结果摘要、evidence source IDs、hash 和错误信息；不保存完整 RAG 语料、完整 trace、密钥或思维链。

不需要 `agent_artifacts`：MVP 的可恢复业务状态分别在 session JSON、消息和步骤中，最终用户生成物仍以 `generation_logs` 为唯一在线事实来源。只有未来需要储存不可变的大型评测文件、外部媒体版本或多份二进制附件时，才重新评估独立 artifact 表。

`generation_attempts` 仍只表达一次实际生成 HTTP/模型工作流的幂等/指标，不应用于长寿命、多轮 Agent session。最终图片调用可以复用其已有机制，`agent_sessions.generation_log_id` 指向最终成功记录；不能在每个对话 turn 创建一条 `generation_attempts`，也不能改写既有记录。所有新表只通过一个新的非破坏性 Alembic 迁移创建，禁止回填、修改或删除历史数据。

## 8. Context 管理与审计边界

数据库保留完整可展示消息和步骤；每次模型调用只取同一 `session_id` 的数据，组装：当前规范化状态、当前阶段所需 Brief/确认文本/提示词包、最近 6 条用户与助手可见消息、早期 `context_summary_json`，以及当前阶段最小化的 evidence/Skill 摘要。

达到例如 12 条消息或 8 KB 可展示文本阈值时，在一次受控模型调用后生成基础摘要，替换早期消息进入模型的部分；原消息不删除。不得把完整 trace、全部历史草稿、完整 RAG 文档或全部旧版本文本反复传入。第一版不实现用户画像、跨 session 记忆、长期记忆或跨用户上下文。

## 9. 最小 API 合同

所有接口均要求现有 JWT；服务端从令牌取得 `user_id`，绝不接受请求体指定 owner。响应只能返回当前用户的 session。

| 接口 | 用途 |
| --- | --- |
| `POST /api/v2/agent-design/sessions` | 创建空 session，返回 `created` 与 `session_id`；不触发模型 |
| `GET /api/v2/agent-design/sessions/{session_id}` | 刷新恢复：状态、可展示消息、步骤、Brief、确认文本、视觉方向、结果和错误 |
| `POST /api/v2/agent-design/sessions/{session_id}/messages` | 初始自然语言需求、局部文本修改、要求重新理解；请求含 `client_turn_id`，同一 session 去重 |
| `POST /api/v2/agent-design/sessions/{session_id}/decisions` | 仅按钮型确认/拒绝：Brief、文本、图片；请求含 `decision_id` 与期望状态 |

建议把“自然语言消息”和“按钮确认”拆开，而不是统一为 turns：自然语言需要在 `extracting_brief` 或文本反馈阶段经过受限理解；按钮确认必须是无歧义、可幂等、可校验当前状态的业务命令。分离后能防止“确认生成图片”被模型误解为改写需求，也更容易处理双击、刷新和 409 状态冲突。

示例：

```json
POST /api/v2/agent-design/sessions/{id}/messages
{
  "client_turn_id": "uuid",
  "text": "以青花折枝纹做一件适合博物馆商店的现代书签，避免仿古感"
}
```

成功后服务端推进至 `waiting_brief_confirmation`，返回自然语言 Brief 说明和结构化 `brief_summary`（非原始 JSON 表单）。在 `waiting_text_feedback`，同一接口接受“把材质改为磨砂金属，名称保留”等局部意见，或“全部重新理解”；重新理解必须清除未确认的后续文本/提示词，并回到 `extracting_brief`。

```json
POST /api/v2/agent-design/sessions/{id}/decisions
{
  "decision_id": "uuid",
  "expected_status": "waiting_text_feedback",
  "decision": "confirm_product_text"
}
```

可用 `confirm_brief`、`regenerate_product_text`、`confirm_product_text`、`confirm_image_generation` 四种决定；`regenerate_product_text` 只可在修订次数小于 4 时执行。状态不符返回 `409 SESSION_STATE_CONFLICT`，达到上限返回 `409 TEXT_REVISION_LIMIT_REACHED`，不存在/非 owner 返回 `404`，模型或外部服务失败返回稳定错误码和可恢复 session 快照。图片确认后立即进入 `generating_image`，成功完成；第一版不提供图片重绘或编辑决定。

## 10. 可直接复用、必须新增与风险

### 可直接复用

- FastAPI 应用与 JWT / owner scope 模式：`backend/app.py`、`backend/routes/*`；
- Brief 验证与 canonical JSON：`backend/domain/cultural_product_brief.py`；
- RAG 检索、证据和来源验证：`backend/rag/*`；
- 固定 Registry 与安全 Skill loader：`backend/agents/skill_registry.py`；
- Pydantic AI Agent、output type、tool budget 和 TestModel 测试范式：`backend/agents/skill_routing.py`、`evaluation/round17c_runner.py`；
- 结构化文本、图片、图片持久化及稳定错误：`backend/services/aigc_service.py`、`backend/prompts/cultural_product_v1.py`、`backend/services/image_storage.py`；
- 连接池、最终记录和历史 DTO：`backend/services/mysql_service.py`；
- 请求幂等、模型指标和 `generation_logs` 关联：`backend/services/generation_tracking.py`；
- `App.vue` 的结果/历史展示可作为新 Agent 组件的视觉和 DTO 参考，但不应直接改动快速生成状态。

### 必须新增

- Agent session/message/step Pydantic 模型、repository/service、显式状态转换和 owner-scope 查询；
- 非破坏性 Alembic 迁移与针对并发/重复 decision 的约束；
- Brief 提取、文本反馈、视觉提示词包的受限 Pydantic AI 适配；
- 当前文本输出到 `ProductDesignDraft` 的归一化与 `ImagePromptPackage` 构造层；
- Agent 专用 FastAPI 路由和测试；
- 新的前端 Agent 面板、session 恢复、消息与确认交互；快速表单保持独立；
- 面向 Agent history/详情的最终 `generation_logs` 投影策略（可先在 session 详情展示，历史卡片只在最后一轮决定是否扩展）。

### 风险与兼容点

- 文本正式生成只有在 Brief 确认后执行；图片只在文本与视觉方向确认后执行，避免隐藏的付费调用。
- 一次 HTTP 请求内直接跑到模型结果可能超时；状态服务应先持久化阶段，再同步执行受控阶段，后续可演进为受控恢复，不引入 Celery/Redis。
- 并发浏览器标签与双击必须通过 `version`、`client_turn_id` / `decision_id` 和 `expected_status` 返回确定结果；不允许两次图片生成。
- `flat_front_back`/`three_view` 目前会调用图片编辑模型。MVP“只生成一轮图片”指不支持用户对已生成图片再编辑，不应错误改成只调用一次 provider。
- 现有 `generation_logs` 历史投影只认识 V2 图片和 Round17C text 类型；引入新的 `generation_kind` 前必须为历史 DTO 增加 allow-list，不能让 Agent JSON 落入旧图片卡片。
- 现有 `skill_routing.py` 强制同时加载一项 text 与一项 visual Skill，不能原样用于阶段化 Agent；应抽取安全 loader 或新增阶段专用 Agent，保留原测试行为。
- README 中仍有旧 Flask 表述，而实际 `backend/app.py` 已是 FastAPI；本 MVP 以代码为准，避免据文档假设路由形态。

## 11. 前后端结果合同与渲染兼容性

### 11.1 已核验的快速生成合同与真实渲染依赖

现有 `POST /api/v2/cultural-products/generate` 仅在图片已落地、`generation_logs` 已插入后返回 200。成功响应包含 `status: "success"`、`generation_kind: "cultural_product"`、`prompt_template_version`、`product_name`、`factual_background`、`evidence_status`、`used_source_ids`、`creative_origin`、`design_concept`、`cultural_meaning`、`selling_points`、`image_prompt`、`image_url`、`generation_time`、`log_id`、`request_id`。

但 `frontend/src/App.vue` 不会只因 HTTP 200 就展示结果：`validGeneration()` 还要求非空 `image_url`、`product_name`、`log_id`、数值 `generation_time`、`factual_background.text`、合法 evidence/citations，以及完整的结构化设计字段（或旧 `design_interpretation` + `product_copy` 回退）。任何缺失都会在 2xx 成功后显示“生成结果不完整，请稍后重试”。这正是“模型、图片、数据库均成功但用户看见失败”的实际触发点。

快速结果区直接读取 `image_url`、`product_name`、`factual_background.text/citations`、`evidence_status`、`creative_origin`、`design_concept`、`cultural_meaning`、`selling_points`、`generation_time`、`log_id`；评分和下载还依赖 `image_url` 与 `log_id`。图片加载失败有专门的“图片暂时无法加载”降级，不会改写生成状态。`ProductDetailDialog.vue` 可容忍部分文本字段缺失，并对 citations 做 allow-list，但其仍假定 `detail` 是对象；它适合普通已完成产品 DTO，不是等待中 Agent session 的通用容器。

历史路径是：`GET /api/user/history` -> `MySQLService.get_user_history()` -> allow-listed list DTO -> `App.vue`。该投影目前：

- 对 `generation_kind=round17c_text_skill` 使用专用 `record_type=text_skill_generation`，避免无图记录落入普通图片卡；
- 对 `prompt_template_version=cultural-product-rag-v2` 生成 V2 图片卡 DTO；
- 其余记录退回 legacy DTO 和普通图片卡。

当前没有普通 V2 的单条“历史详情”接口；列表 DTO 被直接交给 `ProductDetailDialog`。只有 Round17C 文本记录有独立的 owner-scoped `GET /api/v2/cultural-products/text-skill-generations/{run_id}`，且通过 `read_text_skill_generation()` 对 `response_json` 做固定字段投影。数据库行、`brief_json`、`response_json` 不应直接透传给任何前端。

### 11.2 已发现的失败分类与风险

| 情形 | 当前表现 | Agent MVP 必须避免的误判 |
| --- | --- | --- |
| 后端业务/模型失败 | HTTP 502/500，稳定 `code`；`requestError()` 显示“生成服务暂时不可用”等 | 不得把 session 已完成阶段和模型错误混为渲染错误 |
| 数据服务失败 | HTTP 503，`status=unavailable` | 不得把数据库不可用写成“模型生成失败” |
| HTTP 200 但返回 DTO 不完整 | `validGeneration()` 拒绝，显示“生成结果不完整” | Agent 不得使用此旧校验，也不得把可恢复的 completed session 标为 failed |
| 图片 URL 失效 | 结果/详情/历史显示图片降级，文本仍可见 | 图片加载错误不触发重新生成 |
| 组件渲染异常 | 当前没有全局前端 error boundary 或专门错误状态；可能只出现控制台错误/局部空白 | Agent 面板必须将 DTO normalize 后渲染，不能以异常自动重试或重发图片请求 |
| `generation_kind` 未识别 | 历史投影落入 legacy DTO，前端按普通图片卡显示 | Agent 记录必须进入明确 allow-list 分支，绝不能成为结构损坏的普通图片卡 |

另外，历史 V2 判断依赖 `prompt_template_version` 而不是 `generation_kind`；新记录若只新增 kind、未定义投影，会在历史上错误归类。`get_user_history()` 对单行异常采取跳过或 broad failure 的策略，因此新 JSON 的 `null`、对象/数组类型、字段改名和双重 JSON 编码都必须在后端投影层统一吸收。

### 11.3 独立的 AgentSessionDetailResponse

Agent **不能直接复用或修改**旧快速生成成功响应合同，也不能将 `generation_logs.response_json`、repository row、模型原始 JSON 或 provider payload直接返回。新增 Agent API 的成功 envelope 固定为：

```json
{
  "status": "success",
  "request_id": "uuid",
  "data": { "...": "AgentSessionDetailResponse" }
}
```

`AgentSessionDetailResponse` 是 Agent session 的唯一详情合同。无论处于哪个状态，以下顶层字段必须始终存在且类型固定；尚不存在的单对象使用 `null`，集合使用 `[]`，数值使用稳定默认值，禁止按状态删除字段：

| 字段 | 固定类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 如 `agent-session-detail-v1` |
| `session_id` | string | session 主键 |
| `status` / `current_stage` | string | 受控状态机值 |
| `revision_count` | integer | 0–4 |
| `generation_log_id` | integer \| null | 最终在线生成记录关联 |
| `brief_summary` | object \| null | 用户可读 Brief 摘要和 assumptions，不是原始表单 JSON |
| `product_design` | object \| null | 已生成/确认的产品设计投影 |
| `visual_direction` | object \| null | 用户可读视觉方向和已校验提示词摘要 |
| `final_result` | object \| null | 最终图片/展示结果的 allow-listed 投影 |
| `messages` | array | 仅可展示对话消息 |
| `steps` | array | 仅摘要、工具回执和稳定错误；不含思维链 |
| `error` | object \| null | `{code,message,retryable,stage}`，不含 provider payload |
| `created_at` / `updated_at` | string | ISO-8601 时间 |

固定子类型：`brief_summary={cultural_theme,product_type,use_case,style,design_constraints,assumptions}`，其中字符串字段可为 `null`、数组字段恒为数组；`product_design={product_name,design_concept,cultural_translation,structure,materials,color_plan,usage_scene,selling_points,evidence}`；`visual_direction={summary,selected_visual_skill,positive_prompt_summary,negative_constraints,presentation_mode}`；`final_result={generation_log_id,product_name,image_url,generation_time,evidence_status,citations}`。`messages` 的项固定为 `{id,sequence_no,role,message_type,text,created_at}`，`steps` 的项固定为 `{id,ordinal,stage,status,summary,tool,started_at,finished_at,error}`。未知额外字段可由后端忽略；前端 adapter 不得依赖它们。

所有 mutation/read 接口都返回这一完整 detail DTO：创建后为 `created`，消息/确认完成后返回新快照，`GET` 刷新恢复返回相同形状。业务错误继续使用现有稳定错误 envelope；如可安全读取 session，可额外带该 DTO 快照，但不得把错误响应伪装为 `status=success`。

### 11.4 所有状态的完整响应样例

以下样例为类型和字段存在性契约，文本内容仅作示意。每个 `messages` / `steps` 均可为空，但不得缺席。

```json
{"status":"success","request_id":"r1","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"created","current_stage":"created","revision_count":0,"generation_log_id":null,"brief_summary":null,"product_design":null,"visual_direction":null,"final_result":null,"messages":[],"steps":[],"error":null,"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:00:00Z"}}
```

```json
{"status":"success","request_id":"r2","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"waiting_brief_confirmation","current_stage":"waiting_brief_confirmation","revision_count":0,"generation_log_id":null,"brief_summary":{"cultural_theme":"青花折枝纹","product_type":"书签","use_case":"博物馆商店","style":"当代东方","design_constraints":["避免仿古"],"assumptions":["采用单品主视图"]},"product_design":null,"visual_direction":null,"final_result":null,"messages":[{"id":"m1","sequence_no":1,"role":"user","message_type":"request","text":"设计现代青花书签","created_at":"2026-07-30T00:01:00Z"},{"id":"m2","sequence_no":2,"role":"assistant","message_type":"brief_summary","text":"我理解为……","created_at":"2026-07-30T00:01:01Z"}],"steps":[{"id":"st1","ordinal":1,"stage":"extracting_brief","status":"completed","summary":"已形成待确认 Brief","tool":null,"started_at":"2026-07-30T00:01:00Z","finished_at":"2026-07-30T00:01:01Z","error":null}],"error":null,"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:01:01Z"}}
```

```json
{"status":"success","request_id":"r3","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"waiting_text_feedback","current_stage":"waiting_text_feedback","revision_count":1,"generation_log_id":null,"brief_summary":{"cultural_theme":"青花折枝纹","product_type":"书签","use_case":"博物馆商店","style":"当代东方","design_constraints":["避免仿古"],"assumptions":[]},"product_design":{"product_name":"折枝留白书签","design_concept":"以边饰转译纹样","cultural_translation":"现代连续边框","structure":"窄长书签","materials":"磨砂金属","color_plan":"靛青与暖白","usage_scene":"阅读与礼赠","selling_points":["轻薄","留白","耐用"],"evidence":[]},"visual_direction":null,"final_result":null,"messages":[],"steps":[],"error":null,"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:03:00Z"}}
```

```json
{"status":"success","request_id":"r4","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"waiting_image_confirmation","current_stage":"waiting_image_confirmation","revision_count":1,"generation_log_id":null,"brief_summary":{"cultural_theme":"青花折枝纹","product_type":"书签","use_case":"博物馆商店","style":"当代东方","design_constraints":["避免仿古"],"assumptions":[]},"product_design":{"product_name":"折枝留白书签","design_concept":"以边饰转译纹样","cultural_translation":"现代连续边框","structure":"窄长书签","materials":"磨砂金属","color_plan":"靛青与暖白","usage_scene":"阅读与礼赠","selling_points":["轻薄","留白","耐用"],"evidence":[]},"visual_direction":{"summary":"白底单品展示，靛青边饰与磨砂金属","selected_visual_skill":"commercial-product-presentation","positive_prompt_summary":"完整书签，白底，现代产品摄影","negative_constraints":["人物","文字","水印"],"presentation_mode":"single_hero"},"final_result":null,"messages":[],"steps":[],"error":null,"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:04:00Z"}}
```

```json
{"status":"success","request_id":"r5","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"completed","current_stage":"completed","revision_count":1,"generation_log_id":701,"brief_summary":{"cultural_theme":"青花折枝纹","product_type":"书签","use_case":"博物馆商店","style":"当代东方","design_constraints":["避免仿古"],"assumptions":[]},"product_design":{"product_name":"折枝留白书签","design_concept":"以边饰转译纹样","cultural_translation":"现代连续边框","structure":"窄长书签","materials":"磨砂金属","color_plan":"靛青与暖白","usage_scene":"阅读与礼赠","selling_points":["轻薄","留白","耐用"],"evidence":[]},"visual_direction":{"summary":"白底单品展示","selected_visual_skill":"commercial-product-presentation","positive_prompt_summary":"完整书签，白底，现代产品摄影","negative_constraints":["人物","文字","水印"],"presentation_mode":"single_hero"},"final_result":{"generation_log_id":701,"product_name":"折枝留白书签","image_url":"/static/images/example.png","generation_time":4.2,"evidence_status":"creative_only","citations":[]},"messages":[],"steps":[],"error":null,"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:05:00Z"}}
```

```json
{"status":"success","request_id":"r6","data":{"schema_version":"agent-session-detail-v1","session_id":"s1","status":"failed","current_stage":"generating_image","revision_count":1,"generation_log_id":null,"brief_summary":{"cultural_theme":"青花折枝纹","product_type":"书签","use_case":"博物馆商店","style":"当代东方","design_constraints":["避免仿古"],"assumptions":[]},"product_design":{"product_name":"折枝留白书签","design_concept":"以边饰转译纹样","cultural_translation":"现代连续边框","structure":"窄长书签","materials":"磨砂金属","color_plan":"靛青与暖白","usage_scene":"阅读与礼赠","selling_points":["轻薄","留白","耐用"],"evidence":[]},"visual_direction":{"summary":"白底单品展示","selected_visual_skill":"commercial-product-presentation","positive_prompt_summary":"完整书签，白底，现代产品摄影","negative_constraints":["人物","文字","水印"],"presentation_mode":"single_hero"},"final_result":null,"messages":[],"steps":[{"id":"st9","ordinal":9,"stage":"generating_image","status":"failed","summary":"图片服务未完成","tool":"generate_product_image","started_at":"2026-07-30T00:05:00Z","finished_at":"2026-07-30T00:05:05Z","error":{"code":"MODEL_READ_TIMEOUT","message":"图片服务暂时不可用","retryable":true,"stage":"generating_image"}}],"error":{"code":"MODEL_READ_TIMEOUT","message":"图片服务暂时不可用","retryable":true,"stage":"generating_image"},"created_at":"2026-07-30T00:00:00Z","updated_at":"2026-07-30T00:05:05Z"}}
```

### 11.5 `generation_logs`、session 与历史投影的边界

最终 Agent 图片成功后，`generation_logs` 仅保存在线生成事实：`user_id`、事件/时间、`generation_kind`、模板版本、最终产品名/内容摘要、样式摘要、`image_url`、生成耗时、最终规范化 Brief、最终结果投影、evidence source IDs、`agent_session_id` 和 `generation_log_id` 关联信息。`agent_sessions` 保留会话专属状态：完整可展示消息、步骤、假设、修订次数、当前/确认文本版本、`ImagePromptPackage`、上下文摘要和失败摘要。不得把全对话或模型/provider 原始 payload 塞入 `generation_logs.response_json`。

`agent_sessions.generation_log_id` 是即时成功响应、`GET` 刷新恢复和历史详情的同一锚点：成功即时 response 的 `final_result.generation_log_id` 必须等于该列；刷新时从 session 读取同一 ID；历史 Agent 卡片也携带该 ID，并链接回 owner-scoped Agent session 详情。新 Agent 路径应将“插入 `generation_logs` + 写入 `agent_sessions.generation_log_id` + completed 状态”设计为同一数据库事务。若提交后 HTTP 响应序列化失败，客户端必须通过 `GET` 恢复，绝不能再次调用图片模型；若遗留“已写 generation_logs、未更新 session”的历史异常，恢复逻辑以 `response_json.agent_session_id` 查询并补偿绑定，同样禁止重跑图片。

若定义例如 `generation_kind=agent_dialogue_mvp`，必须同步修改并测试：

1. `backend/services/mysql_service.py::get_user_history()` 的 generation-kind allow-list 和 Agent history DTO；
2. Agent owner-scoped session/detail projection（而不是把数据库 JSON 交给 `ProductDetailDialog`）；
3. `backend/routes/api.py::get_user_history()` 的完整性/详情 URL 处理；
4. `frontend/src/App.vue` 的 `isAgentDialogueRecord`、卡片、打开详情与未知记录降级映射；
5. 如新建 Agent 详情组件，则该组件的 normalize adapter；`ProductDetailDialog` 仅继续接收旧普通产品 DTO；
6. 对 `generation_kind`、`prompt_template_version` 和旧数据的合同测试。

普通快速生成卡片、旧 `generation_logs` 行、V2 `cultural-product-rag-v2` 投影与 Round17C text Skill 卡片必须保持不变。未知 kind 不得假定为可展示图片结果：应在后端投影为稳定的“暂不支持的历史记录”摘要，或由前端显示“结果暂时无法展示”，但不能把它显示为模型失败。
