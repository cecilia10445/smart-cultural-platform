# Smart Cultural Platform

## Windows unit-test environment

Windows tests use Flask's test client and mocks for DashScope, MySQL, and Hive. They do not require an API key, Hadoop, HiveServer2, HDFS, YARN, or a Linux shell.

```powershell
python -m pytest backend/tests -q
```

Copy `backend/.env.example` to `backend/.env` only for local application runs. Never commit a real `.env` file.

## Linux integration environment

The complete data pipeline must be verified separately in the Ubuntu virtual machine: MySQL, Hadoop/HDFS, HiveServer2, YARN, Spark, the MySQL JDBC driver, and the project shell scripts are required. These integrations are not covered by the Windows unit tests and must not be reported as passed until they are run there.

Current first-batch scope: Flask security, honest dependency failures, and mocked Windows unit tests. Spark ETL and front-end changes are deliberately deferred.
