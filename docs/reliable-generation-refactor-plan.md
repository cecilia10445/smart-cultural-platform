# 可靠性与数据闭环改造计划

本文是基于当前仓库真实状态的工程计划，不把未实现能力描述为已完成。

## 当前技术边界

项目保持 Flask、Vue、MySQL、Hive 和 PySpark。当前明确不引入 Redis、Celery、PostgreSQL、pgvector、FastAPI、多 Agent、RAG 或 LoRA。在线生成仍是 Flask 同步调用模型并写入 MySQL 的路径；模型供应商自身的图片任务轮询不等同于项目异步任务系统。

## 已完成基础工作（Round 03–09）

- Round 03 建立了最小 MySQL `aigc_platform` 与 `generation_logs` 基线。
- Round 04 强制生成结果以真实 MySQL `insert_id` 成功落库后才返回成功。
- Round 05 使用一次性 MySQL 容器覆盖真实 API→MySQL 集成。
- Round 06 删除后端运行时伪数据，并区分 liveness/readiness。
- Round 07 删除前端运行时模拟回退，按真实 API 契约展示加载、空和错误状态。
- Round 08 引入 Alembic 0001 作为新环境 schema 来源，并保护基线 downgrade。
- Round 09 定义 0002 增量字段、批次/质量控制表、Hive ODS 契约和旧 Spark ETL 安全边界；完整数据搬运尚未实现。

## 当前可靠性边界

`generation_logs` 是在线事实来源。`created_at`/`updated_at` 与 `(updated_at,id)` 复合水位支持未来增量抽取；`etl_batches` 和 `data_quality_results` 记录批次和质量结果。Spark 不得覆盖、重建或删除在线原始表，模拟和公开数据必须有显式 `data_origin`。

## Round 10：实际数据闭环

Round 10 才实现并验证 MySQL→Hive ODS→PySpark 聚合→受控 MySQL 统计表写回，包括增量边界、批次状态、质量检查、失败处理和生产表保护。实现前必须对现有生产 schema 做只读对比，不能直接 stamp 或 downgrade。

## 已废弃历史提案

早期文档曾提出 Redis/Celery、202 任务接口、Worker、`generation_task`、幂等键和 RAG/Agent 等方案。这些不是当前路线，也未在仓库中实现；不应据此声称项目具备异步任务系统。任何未来架构变化必须单独立项并更新本计划。
