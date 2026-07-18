# 可靠型 AI 内容生成与质量分析平台改造方案

> 文档性质：基于当前代码的只读审查与分阶段设计，不代表这些能力已经实现或验证。  
> 项目定位：面向测试开发/大模型测试开发校招的开发项目，重点解决第三方模型调用可靠性、离线数据闭环和自动化质量验证。  
> 技术边界：保留 Flask、Vue、MySQL、Hive、PySpark；允许为异步任务引入 Redis 和 Celery；不引入 RAG、Agent、LoRA、微服务或 Kubernetes。

## 1. 审查结论摘要

当前 `/api/generate` 是一个长耗时同步接口。Flask 请求线程依次完成文本生成、提交图片任务、轮询 DashScope、下载图片、写本地日志和写 MySQL，最后才向前端返回结果。代码中的“异步”仅指 DashScope 图片服务返回 `task_id` 后的供应商任务轮询，项目本身没有后台任务队列、Worker、持久化任务状态、任务查询接口或故障恢复系统。

当前数据链路也不是“MySQL -> HDFS -> Hive -> Spark -> MySQL 统计表”的闭环。在线接口并行写 MySQL 和本地 JSON 日志；上传脚本将本地日志上传 HDFS；Spark直接读取HDFS文件和本地/公开数据集，再直接写 MySQL。Hive虽然被后端查询，但现有 Spark 主流程没有把在线数据规范地写入 Hive 明细表。更严重的是，Spark使用 `overwrite` 写 `generation_logs`，可能覆盖在线原始记录。

因此改造分为两个必做阶段：第一阶段建立项目自身的最小异步任务闭环；第二阶段建立可追溯、可增量、可重复执行的数据闭环。租约恢复、Celery Beat、复杂 checksum 和 Flower 等能力放入可选增强阶段。

## 2. 当前生成接口完整调用链

```text
Vue generateContent()
  -> POST /api/generate，携带 JWT、prompt、style
  -> Flask authenticate_user()
  -> AIGCService.generate_text_content()
  -> 同步请求 DashScope qwen-turbo
  -> 严格解析 title/content JSON
  -> AIGCService.generate_image()
  -> 提交 DashScope wanx-v1 图片任务，获得 provider task_id
  -> wait_for_image_task() 在 Flask 请求线程内循环轮询
  -> 下载结果图片到 static/images
  -> log_event() 写本地 JSON 日志
  -> MySQL 查询一小时内相同 user/prompt/style 记录
  -> 插入 generation_logs
  -> 返回 title、content、image_url 和临时 log_id
```

代码证据：

- 前端只发送一次请求并等待最终响应，没有项目任务轮询：[frontend/src/App.vue:409](../frontend/src/App.vue#L409)。
- Flask请求线程直接调用完整生成流程：[backend/app.py:349](../backend/app.py#L349)、[backend/app.py:363](../backend/app.py#L363)。
- 文本完成后才提交图片生成：[backend/services/aigc_service.py:36](../backend/services/aigc_service.py#L36)。
- DashScope图片任务默认最多轮询12次、每次间隔5秒：[backend/services/aigc_service.py:84](../backend/services/aigc_service.py#L84)。
- 图片轮询使用 `time.sleep()`，会继续占用Web请求线程：[backend/services/aigc_service.py:108](../backend/services/aigc_service.py#L108)。
- 图片下载同样位于HTTP请求内：[backend/app.py:372](../backend/app.py#L372)。
- MySQL写入发生在所有模型调用和图片下载之后：[backend/app.py:424](../backend/app.py#L424)。
- MySQL插入返回 `None` 时仅打印警告，接口仍可能返回成功：[backend/app.py:468](../backend/app.py#L468)。
- 返回的 `log_id` 是时间戳拼接值，不是数据库记录ID：[backend/app.py:479](../backend/app.py#L479)。

`app.py` 中虽然保留了 `MockAIGCService`，但导入异常分支先执行 `raise RuntimeError`，后续Mock代码不可达，不能将其描述为正式降级能力：[backend/app.py:128](../backend/app.py#L128)。

## 3. 当前“异步轮询”的准确表述

当前能力应表述为：“服务端同步调用文本模型，并在同一个Flask请求中轮询DashScope图片异步任务。”不能表述为“项目实现了异步任务系统”。

当前缺失：

- 没有 Redis、Celery 或其他消息队列；
- 没有独立 Worker；
- 没有 `generation_task` 持久化状态；
- 没有 `POST提交 -> 202 -> GET查询状态` 协议；
- Web进程退出后无法从项目数据库恢复执行位置；
- 无法可靠区分排队耗时、模型耗时、图片轮询耗时和持久化耗时；
- 现有“一小时内相同 prompt/style”查询不是可靠幂等，并发请求仍可能重复调用模型和重复扣费。

## 4. 目标架构与 Redis/Celery 必要性

```text
Vue
  -> Flask POST /api/generate
       -> 校验请求和 Idempotency-Key
       -> MySQL创建 generation_task
       -> Celery投递任务到Redis
       -> 立即返回 202 + task_id

Celery Worker
  -> 从Redis取任务
  -> 原子更新MySQL任务状态
  -> 调用文本模型
  -> 提交并轮询图片任务
  -> 保存图片和生成结果
  -> 唯一写入generation_logs
  -> 更新generation_task终态

Vue
  -> GET /api/generate/{task_id}
  -> 展示 QUEUED/RUNNING/RETRYING/SUCCEEDED/FAILED
```

Redis只承担Celery broker职责；MySQL是任务状态和业务结果的唯一可信来源，不把Redis当业务数据库，也不依赖Celery result backend保存最终结果。

引入Redis/Celery的必要性来自真实问题：模型调用和图片轮询耗时较长，不能持续占用Flask请求线程；任务需要独立重试；Web进程和Worker需要解耦；重复提交必须在调用模型前被拦截。若不做这些需求，则没有必要引入Redis/Celery。

## 5. 第一阶段：最小异步任务闭环和 pytest

### 5.1 阶段范围

第一阶段只实现：

1. Redis作为Celery broker，增加一个Celery Worker；
2. MySQL增加 `generation_task` 表；
3. `POST /api/generate` 改为创建任务并返回 `202 + task_id`；
4. 增加一个任务状态查询接口；
5. Worker执行现有DashScope文本与图片流程，并写回状态和结果；
6. `Idempotency-Key`、请求指纹和数据库唯一约束；
7. 有上限的分类重试和指数退避；
8. Celery延迟确认带来的基础消息重投；
9. 使用Mock/Fake隔离DashScope、Redis和MySQL的pytest自动化测试。

第一阶段不实现租约字段扫描、Celery Beat、复杂checksum、Flower、任务取消、独立调用明细表和前端管理后台。

### 5.2 generation_task 表

建议最小字段如下：

| 字段 | 建议类型 | 用途 |
| --- | --- | --- |
| `id` | `BIGINT AUTO_INCREMENT` | 数据库主键 |
| `task_id` | `CHAR(36) UNIQUE` | 对外任务ID，同时作为Celery task id |
| `user_id` | `VARCHAR(64)` | 任务所有者 |
| `idempotency_key` | `VARCHAR(128)` | 客户端幂等键 |
| `request_hash` | `CHAR(64)` | 规范化请求SHA-256 |
| `prompt`、`style` | `TEXT`、`VARCHAR(100)` | 原始请求 |
| `status` | `VARCHAR(20)` | `QUEUED/RUNNING/RETRYING/SUCCEEDED/FAILED` |
| `stage` | `VARCHAR(30)` | `TEXT/IMAGE_SUBMIT/IMAGE_POLL/IMAGE_DOWNLOAD/PERSIST` |
| `attempt_count`、`max_attempts` | `INT` | 重试计数和上限 |
| `provider_task_id` | `VARCHAR(128)` | DashScope图片任务ID |
| `title`、`content`、`image_url` | `TEXT` | 中间结果与最终结果 |
| `error_category`、`error_code` | `VARCHAR(50)` | 可统计的错误分类 |
| `error_message` | `VARCHAR(500)` | 脱敏后的错误摘要 |
| `retryable` | `BOOLEAN` | 是否可重试 |
| `queued_at`、`started_at`、`finished_at` | `DATETIME(3)` | 状态时间 |
| `created_at`、`updated_at` | `DATETIME(3)` | 审计时间 |

唯一约束为 `(user_id, idempotency_key)`；`generation_logs.task_id`也需要唯一约束，防止重复消息产生两条成功记录。

最小状态机：

```text
QUEUED -> RUNNING -> SUCCEEDED
             |
             +-> RETRYING -> RUNNING
             |
             +-> FAILED
```

状态更新使用条件SQL，例如 `UPDATE ... WHERE task_id=? AND status='QUEUED'`。只有更新成功的Worker可以执行任务，以抵御同一消息被重复投递。第一阶段不加入租约恢复状态。

### 5.3 幂等提交

客户端发送UUID格式的 `Idempotency-Key`。服务端对规范化后的 `user_id + prompt + style` 计算：

```text
request_hash = SHA256(canonical_json(user_id, prompt, style))
```

处理规则：

- 同一用户、同一幂等键、同一请求指纹：返回已有任务，不重复调用模型；
- 同一幂等键但请求指纹不同：返回 `409 IDEMPOTENCY_KEY_CONFLICT`；
- 并发插入由MySQL唯一索引裁决，不能依赖“先查后插”；
- API创建任务成功但Redis投递失败：任务保留为 `QUEUED`，接口返回明确不可用，第一阶段提供人工重新投递命令；自动扫描放入增强阶段；
- Worker重复执行时，状态条件更新和 `generation_logs.task_id` 唯一索引共同保证结果只有效落库一次。

第三方模型调用无法保证严格的 exactly-once。项目承诺的是“任务至少一次执行、业务结果有效一次落库”，并明确供应商接受请求后、本地尚未持久化 `provider_task_id` 的极小不确定窗口。

### 5.4 重试分类

| 可重试 | 不可重试 |
| --- | --- |
| 连接失败、连接重置、临时DNS错误 | prompt/style参数错误 |
| 请求超时 | 401/403、API Key错误 |
| HTTP 429，尊重 `Retry-After` | 内容安全拒绝 |
| DashScope 5xx | 明确余额不足或账户冻结 |
| MySQL死锁、锁等待超时、连接中断 | 幂等键冲突、数据完整性错误 |
| 图片下载超时或5xx | 图片404、明确不支持的格式 |

模型空响应或JSON格式错误最多重试一次，之后明确失败，避免持续消耗额度。退避采用指数退避加随机抖动，并设置最大尝试次数和任务总超时。错误分类应集中在一个策略模块中，不能分散为多处字符串判断。

第一阶段使用 `task_acks_late` 和 `task_reject_on_worker_lost` 获得Celery基础重投能力。Worker异常后可能重新执行，因此所有持久化步骤必须幂等。基于数据库租约的精确恢复属于增强阶段。

### 5.5 第一阶段 pytest 矩阵

| 测试层 | 必须覆盖的用例 |
| --- | --- |
| API | 未认证、参数错误、成功返回202、状态查询权限、任务不存在 |
| 幂等 | 同键同请求返回原任务、同键异请求409、并发提交只有一个任务 |
| 队列 | 投递成功、Redis不可用、投递异常不伪造成功 |
| 状态机 | 合法转换、非法转换拒绝、重复消息无法重复抢占 |
| 模型 | timeout、429、5xx、400、401、空响应、错误JSON、图片FAILED/CANCELED |
| 重试 | 可重试错误达到预期调用次数、不可重试错误只调用一次、达到上限后FAILED |
| Worker | 成功落库、模型失败不写成功日志、重复执行只产生一条generation_logs |
| 安全 | 日志不包含JWT、API Key、数据库密码和完整Authorization头 |

Windows pytest不得连接真实DashScope、Redis、MySQL或Hive，不消耗模型额度；使用Flask test client、Celery eager模式或注入式任务调用、Fake repository和HTTP Mock。Redis/Celery/MySQL真实集成测试回Ubuntu执行。

### 5.6 第一阶段验收证据

- `POST /api/generate`真实返回202和可查询的 `task_id`；
- 状态查询能观察到真实状态序列，而不是前端定时动画；
- 并发提交相同幂等键后，数据库仅有一个任务，Fake模型调用计数为一次；
- 注入 `500/500/200` 后，报告显示真实尝试次数和最终状态；
- 注入401或内容安全拒绝后，不发生重试；
- 重复投递同一Celery任务后，`generation_logs`仍只有一条对应记录；
- pytest报告保存实际通过、失败、跳过数量，不预先填写准确率或性能提升。

## 6. 第二阶段：MySQL、HDFS、Hive、Spark真实数据闭环

### 6.1 当前链路问题

当前在线接口同时写本地日志和MySQL，并不是从MySQL导出到HDFS：[backend/app.py:403](../backend/app.py#L403)、[backend/app.py:424](../backend/app.py#L424)。上传脚本上传整份 `app.log`，成功后备份并清空本地文件：[scripts/upload_to_hdfs.sh:43](../scripts/upload_to_hdfs.sh#L43)、[scripts/upload_to_hdfs.sh:54](../scripts/upload_to_hdfs.sh#L54)。

Spark读取三类来源并合并：本地合成数据、HDFS在线日志、Flickr公开数据：[scripts/spark_etl.py:27](../scripts/spark_etl.py#L27)、[scripts/spark_etl.py:44](../scripts/spark_etl.py#L44)、[scripts/spark_etl.py:57](../scripts/spark_etl.py#L57)。这些数据不能共同作为“真实用户数据”。

Spark还会为缺失评分、下载数、年龄和性别生成随机值：[scripts/spark_etl.py:247](../scripts/spark_etl.py#L247)。正式统计必须保留 `NULL` 并报告缺失率，不能把随机填充值称为降级或真实数据。

最危险的问题是Spark以 `overwrite` 模式回写在线 `generation_logs`：[scripts/spark_etl.py:908](../scripts/spark_etl.py#L908)、[scripts/spark_etl.py:929](../scripts/spark_etl.py#L929)。第二阶段必须彻底取消Spark对该原始表的写权限。

### 6.2 统一数据契约

定义版本化逻辑契约 `generation_event_v1`：

| 字段 | 语义 |
| --- | --- |
| `schema_version` | 固定为 `generation_event_v1` |
| `event_id` | MySQL原始事件主键，全链路唯一 |
| `task_id` | 关联异步生成任务 |
| `user_id` | 用户标识 |
| `event_type` | `generate/rate/download` |
| `occurred_at_utc` | UTC毫秒时间 |
| `prompt`、`style` | 生成输入，仅generate事件必填 |
| `title`、`content`、`image_url` | 真实模型输出 |
| `provider`、`text_model`、`image_model` | 供应商和模型版本 |
| `generation_ms`、`content_length` | 可验证指标 |
| `user_rating` | 真实用户评分，缺失时为NULL |
| `data_origin` | `production/public/synthetic/test` |
| `created_at_utc` | 源记录创建时间 |

`batch_id`属于ETL批次信封：HDFS/Hive记录带有它，MySQL源记录通过 `etl_batch` 的主键区间映射到批次。所有时间统一UTC，所有组件使用相同字段名和可兼容类型。未知字段不能随机补齐；不兼容Schema进入隔离目录并使批次失败。

现有Hive `generation_logs`字段少于MySQL实际写入字段，需要通过非破坏性迁移建立版本化外部表：[scripts/hive_setup.sql:14](../scripts/hive_setup.sql#L14)。

### 6.3 真实增量链路

```text
MySQL generation_logs（在线追加、唯一事实源）
  -> export_generation_events.py 按 event_id 水位导出
  -> HDFS /raw/generation_events/schema=v1/batch_id=...
  -> Hive external table 注册批次分区
  -> Spark读取指定batch_id并做Schema校验、去重和聚合
  -> MySQL统计暂存表
  -> MySQL事务按batch_id合并统计并标记批次成功
  -> Flask/Vue只读取统计结果表
```

增加必要的 `etl_batch` 控制表：`batch_id、dataset、cursor_from、cursor_to、status、hdfs_path、source_count、valid_count、invalid_count、started_at、finished_at、error_code`。

批次流程：

1. 读取上次成功水位并固定本批次最大 `event_id`；
2. 创建唯一 `batch_id`，导出 `(cursor_from, cursor_to]`；
3. 写HDFS临时目录，完成字段和行数校验后原子重命名；
4. 为Hive外部表增加该 `batch_id` 分区；
5. Spark只读取这个批次，按 `event_id` 去重；
6. Spark只写统计暂存/结果表，绝不写 `generation_logs`；
7. MySQL事务检查批次尚未完成，合并统计并标记成功；
8. 相同 `batch_id` 重跑时替换该批暂存结果，不重复累计。

第二阶段先使用源行数、有效行数、无效行数和主键边界完成基础核对。跨文件复杂checksum放入增强阶段。

为了保持增量语义，`generation_logs`应逐步改为追加事件：生成、评分和下载各自追加事件并通过 `task_id`关联。当前评分和下载直接更新原行的方式会导致纯 `event_id` 水位无法捕获后续变化：[backend/app.py:642](../backend/app.py#L642)、[backend/app.py:709](../backend/app.py#L709)。迁移期间保留旧字段和旧数据，不删除表或历史记录。

### 6.4 第二阶段测试与验收

- 契约测试：字段名、类型、必填规则、UTC时间、Schema版本和 `data_origin`；
- 增量边界测试：空批次、单条记录、上下界、连续批次和重复 `event_id`；
- 坏数据测试：字段缺失、错误类型、非法时间进入隔离区且批次明确失败；
- 批次幂等测试：同一 `batch_id` 连续执行两次，统计结果不重复增加；
- 故障注入：HDFS写一半、Hive注册失败、Spark失败、MySQL合并失败后可用同一批次重跑；
- 原始表保护：ETL前后比较 `generation_logs` 主键集合和历史记录，证明Spark未覆盖；
- 数据核对：保存MySQL源记录数、HDFS记录数、Hive记录数、Spark有效/隔离数和MySQL统计数；
- 数据来源隔离：production指标中不存在 `public/synthetic/test` 数据；
- Linux集成测试必须使用真实MySQL、HDFS、HiveServer2和Spark执行，未运行时明确标记未验证。

## 7. 可选增强阶段

以下能力有工程价值，但不进入前两个阶段的最小交付范围：

- 数据库租约：`lease_owner/lease_expires_at/version`，识别长时间停留在RUNNING的任务；
- Celery Beat定时扫描：恢复未投递QUEUED任务和租约过期任务；
- 分阶段断点恢复：已保存文本则只重试图片，已有 `provider_task_id` 则继续轮询；
- 复杂checksum：文件级或批次级内容哈希、Manifest及跨系统校验；
- Flower：观察Worker、队列和任务，不作为业务状态真相；
- `generation_attempt` 明细表：记录每次供应商调用、错误、耗时和Token，用于更细质量分析；
- 管理员失败任务重放和任务取消；
- 少量真实DashScope手工冒烟测试，单独记录调用量和成本；
- 压测报告：记录并发量、排队时间、执行时间、p50/p95、成功率和重试率。

增强阶段仍不包括RAG、Agent、LoRA、多Agent、视频、微服务和Kubernetes。

## 8. 预计修改与新增文件

本方案实施时预计修改：

- `backend/app.py`：提交任务、查询状态、移除请求线程内长耗时执行；
- `backend/config.py`、`backend/.env.example`：Redis/Celery和任务超时配置；
- `backend/requirements.txt`：Redis/Celery依赖；
- `backend/services/aigc_service.py`：可分阶段调用、错误分类和供应商任务ID；
- `backend/services/mysql_service.py`：事务、条件状态更新和批次查询；
- `backend/utils/logger.py`：加入 `task_id/stage/attempt` 上下文并继续脱敏；
- `frontend/src/App.vue`：提交任务并轮询项目自身状态；
- `scripts/spark_etl.py`：读取批次、契约校验、取消覆盖原始表；
- `scripts/hive_setup.sql`：增加版本化外部表；
- `README.md`：Windows Mock测试与Ubuntu集成环境运行说明。

预计新增：

- `backend/celery_app.py`；
- `backend/tasks/__init__.py`、`backend/tasks/generation.py`；
- `backend/services/generation_task_service.py`；
- `scripts/migrations/001_generation_task.sql`；
- `scripts/migrations/002_generation_event_contract.sql`；
- `scripts/migrations/003_etl_batch.sql`；
- `scripts/export_generation_events.py`；
- `backend/tests/test_generation_api.py`；
- `backend/tests/test_idempotency.py`；
- `backend/tests/test_retry_policy.py`；
- `backend/tests/test_generation_worker.py`；
- `backend/tests/test_etl_contract.py`；
- `backend/tests/integration/` 下的Ubuntu集成测试。

不删除现有文件、表或真实数据。现有 [scripts/update_mysql.sql:2](../scripts/update_mysql.sql#L2) 包含 `DROP TABLE`，应保留供审查但不能用于新迁移。

## 9. 如何用真实结果证明完成

| 技术点 | 必须保存的真实证据 |
| --- | --- |
| 项目异步任务 | POST返回202、数据库状态变迁、Worker日志和最终查询结果 |
| 幂等 | 并发相同键请求数、任务表行数、Fake/Stub模型实际调用计数 |
| 分类重试 | 故障序列、每次调用时间、尝试次数、最终错误码 |
| Worker基础重投 | Worker异常退出前后任务状态和唯一成功记录 |
| 数据契约 | 自动Schema测试报告和坏数据隔离样本 |
| 增量ETL | cursor范围、batch_id、各层行数及失败批次记录 |
| 批次幂等 | 同批次重跑前后统计表快照或数值对比 |
| 原始数据保护 | ETL前后 `generation_logs` 主键/行数核对和Spark账号权限 |
| 性能与成本 | 实际并发参数、p50/p95、模型调用次数、Token或账单记录 |

文档和简历中不得预先填写“准确率提升”“Token降低”或“性能提升”等百分比。只有基准测试实际执行后，才能报告对应环境、数据规模、命令、原始结果和计算方式。Mock故障注入可以证明分支逻辑，但不能冒充真实DashScope、Redis、MySQL、HDFS、Hive或Spark集成验证。

## 10. 推荐实施顺序

1. 先完成第一阶段的任务表、Redis/Celery、幂等、基础重试、状态查询和pytest；
2. 在Ubuntu用Redis/Celery/MySQL和本地可控模型Stub完成真实进程级集成验证；
3. 再完成第二阶段的数据契约、MySQL增量导出、HDFS分区、Hive外部表和Spark批次统计；
4. 在Ubuntu完成HDFS/Hive/Spark故障注入和批次幂等验证；
5. 只有前两阶段稳定后，再按面试价值选择租约恢复、Beat、checksum、Flower或调用明细分析。

这个顺序让每个新增组件都对应一个可解释、可测试、可复现的工程问题，避免把项目重新做成只展示技术名词的Demo。
