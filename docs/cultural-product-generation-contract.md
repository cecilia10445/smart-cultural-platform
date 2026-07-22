# 文创产品生成契约（v2）

`POST /api/generate` 是兼容旧页面的 legacy 接口。`POST /api/v2/cultural-products/generate` 接收 `brief_version: "1.0"` 和结构化 `brief`，返回 `generation_kind: "cultural_product"`、模板版本、产品名称、事实背景、设计解读、产品讲解、图片提示、图片地址、耗时和真实 `log_id`。

Brief 包含产品类型、文化来源、用户确认事实、造型材质、使用场景、受众和画面方向。未知字段和错误类型返回 HTTP 400 与稳定错误码。`generation_logs` 新增的 JSON 字段只保存已验证的 Brief 与业务响应，不保存 API Key、Token 或 System Prompt。

MySQL→Hive ODS 增量同步继续显式投影既有字段；本轮新增 JSON 字段尚未进入 ODS。`response_json` 不重复保存 `log_id`：数据库行主键 `generation_logs.id` 就是 API 返回的 `log_id`。

图片下载成功后才保存为本地 `/static/images/...` 路径并写入日志。供应商图片下载超时、非 200、非图片、过大或落盘失败时，接口返回 `IMAGE_PERSIST_FAILED`（502），不将未经验证的远程 URL 写入数据库。
