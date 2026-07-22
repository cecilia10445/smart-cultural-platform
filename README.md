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
