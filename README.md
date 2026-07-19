# Smart Cultural Platform

## Unit-test environment

Default tests use Flask's test client and controlled substitutes for external services. They do not start Docker, Hive, Spark, or DashScope. The explicitly enabled MySQL integration test uses an isolated Testcontainers database and Alembic migrations.

```bash
backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
```

Copy `backend/.env.example` to `backend/.env` only for local application runs. Never commit a real `.env` file.

## Data pipeline status

MySQL `generation_logs` is the online source of truth. Alembic defines the target schema for new environments. The Hive ODS contract and ETL safety boundary are versioned in this repository, but the actual incremental MySQL-to-Hive transfer, Spark aggregation, and analytics-table writeback are not implemented yet.

Do not run the legacy Spark ETL entry point or any destructive legacy SQL. See `docs/data-pipeline-contract.md` for the implemented contract and the remaining Round 10 work.
