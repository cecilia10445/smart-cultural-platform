# Smart Cultural Platform

## Unit-test environment

Default tests use Flask's test client and controlled substitutes for external services. They do not start Docker, Hive, Spark, or DashScope. The explicitly enabled MySQL integration test uses an isolated Testcontainers database and Alembic migrations.

```bash
backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
```

Copy `backend/.env.example` to `backend/.env` only for local application runs. Never commit a real `.env` file.

## Data pipeline status

MySQL `generation_logs` is the online source of truth. Alembic defines the target schema for new environments. MySQL→Hive ODS incremental synchronization is implemented and versioned. PySpark aggregation, controlled statistics-table writeback, and a complete analytics dashboard loop are not implemented yet.

Do not run the legacy Spark ETL entry point or any destructive legacy SQL. See `docs/data-pipeline-contract.md` for the implemented contract and the remaining Round 10 work.
# 智能文创平台

当前开发入口为 Vite `http://localhost:3000`，Flask API 默认在 5000。项目定位为面向 AI 测试开发、测试开发和 AI 应用开发求职的智能文创大模型应用与质量评测平台。

v2 文创产品接口使用确定性 Prompt 编排，并接入一个边界明确的小型本地 RAG：六件 Met Open Access 对象冻结在仓库中，进程内 BM25 只读检索，不在运行时访问 Met API。只有通过保守相关性与歧义规则的官方字段可以进入证据块；模型返回的 `used_source_ids` 必须是实际提供来源的子集。没有可靠证据时返回 `insufficient_evidence`。这不是 Agent、实时检索或自动事实核验。

DashScope 运行配置使用独立连接与读取超时：文本默认为 5 秒连接、120 秒读取，图片默认为 5 秒连接、30 秒读取。请以 `backend/.env.example` 的变量名配置；离线测试与 CI 不会调用模型服务。

`cultural-product-v1` 文本调用将 `DASHSCOPE_TEXT_REASONING_EFFORT` 默认为 `none`，以稳定输出严格 JSON；不发送 `enable_thinking`。图片使用 wan2.6 同步 `messages` 输入和默认 `1280*1280` 尺寸。
