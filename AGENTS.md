# Repository Working Rules

- 项目开发目录为 `/home/lily/桌面/smart-cultural-platform`；保持 Vue、Flask、MySQL、Hive、PySpark 和 DashScope 技术路线。
- 当前不引入 Redis、Celery、PostgreSQL、pgvector、FastAPI、多 Agent 或 LoRA；先建立真实、可验证的 MySQL → Hive → PySpark → MySQL 数据链路。
- 每轮只处理一个明确目标；修改后必须运行相关测试，并如实报告通过、失败和跳过结果，不得编造测试结果。
- 禁止使用 `git add .`、`git add -A` 或通配符暂存；只能使用明确文件路径暂存本轮文件。
- 不提交 `.env`、密码、密钥、虚拟环境、`node_modules`、`dist`、日志、测试用户 JSON 或数据集。
- MySQL `generation_logs` 是在线生成日志的唯一事实来源；Spark 不得覆盖、重建或删除该表。
- 模拟数据只能进入明确的 `test`/`synthetic` 数据路径；前端看板不得将模拟数据表示为生产统计。
- 破坏性遗留脚本 `scripts/update_mysql.sql` 已删除；禁止重新引入等价的 `DROP`/`TRUNCATE` 逻辑，数据库结构只通过受审查的 Alembic 迁移演进。
- 提交前必须展示 diff、待暂存文件、测试结果和建议的 commit message；未经用户确认不得暂存或提交。
- 提交后按约定将 `summary.md`、`git-status.txt`、`commit-info.txt`、`changes.patch` 和 `test-results.txt` 导出到对应的共享交接目录；共享目录不可写时立即停止导出并报告。
