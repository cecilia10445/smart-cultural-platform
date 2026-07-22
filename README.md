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

当前开发入口为 Vite `http://localhost:3000`，Flask API 默认在 5000。v2 文创产品接口使用确定性 Prompt 编排与用户提供事实边界；它不是 RAG、Agent 或自动事实核验。

DashScope 运行配置使用独立连接与读取超时：文本默认为 5 秒连接、120 秒读取，图片默认为 5 秒连接、30 秒读取。请以 `backend/.env.example` 的变量名配置；离线测试与 CI 不会调用模型服务。

`cultural-product-v1` 文本调用将 `DASHSCOPE_TEXT_REASONING_EFFORT` 默认为 `none`，以稳定输出严格 JSON；不发送 `enable_thinking`。图片使用 wan2.6 同步 `messages` 输入和默认 `1280*1280` 尺寸。
