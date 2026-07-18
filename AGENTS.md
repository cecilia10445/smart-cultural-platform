# Repository Working Rules

- 项目开发目录为 `/home/lily/桌面/smart-cultural-platform`；主要技术栈为 Vue、Flask、MySQL 和 DashScope，后续阶段将引入 Redis/Celery 与 MySQL → HDFS → Hive → Spark → MySQL 数据链路。
- 分阶段目标依次为：先恢复 Ubuntu 上的同步运行基线，再实施 Redis/Celery 异步任务，最后完成数据链路。
- 每轮只处理一个明确目标；修改后必须运行相关测试，并如实报告通过、失败和跳过结果，不得编造测试结果。
- 禁止使用 `git add .`、`git add -A` 或通配符暂存；只能使用明确文件路径暂存本轮文件。
- 不提交 `.env`、密码、密钥、虚拟环境、`node_modules`、`dist`、日志、测试用户 JSON 或数据集。
- `scripts/update_mysql.sql` 具有破坏性，不得直接执行。Spark 不得覆盖 MySQL 在线原始 `generation_logs` 表。
- 提交前必须展示 diff、待暂存文件、测试结果和建议的 commit message；未经用户确认不得暂存或提交。
- 提交后按约定将 `summary.md`、`git-status.txt`、`commit-info.txt`、`changes.patch` 和 `test-results.txt` 导出到对应的共享交接目录；共享目录不可写时立即停止导出并报告。
