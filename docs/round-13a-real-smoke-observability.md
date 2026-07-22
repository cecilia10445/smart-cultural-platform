# Round 13A 真实模型 Smoke：可观测性边界

Round 13A 将真实模型调用限制在显式授权的单例组件 Smoke 和单例业务 Smoke。组件 Smoke 与完整业务 Smoke 是不同的数据路径：组件 Smoke 只生成脱敏评测报告，不写入 `generation_logs`；完整业务 Smoke 使用本地 `user1`、`aigc_platform_demo` 和服务端 `data_origin=test`，成功记录与本地图片默认保留。

组件 Smoke 报告可记录供应商实际返回的 Token usage（存在时）和组件调用延迟。该信息不会被估算，也不保存模型正文、System Prompt、认证信息或供应商临时图片 URL。

完整 v2 业务链路目前只在 `generation_logs.generation_time` 与 v2 响应中记录端到端 `generation_time`。它尚未持久化或报告以下分阶段信息：

- 文本模型 Token usage；
- 文本模型调用延迟；
- 图片模型调用延迟；
- 图片下载与本地落盘延迟。

这些缺口留待 Round 13B 通过明确的、脱敏的业务可观测性契约解决；Round 13A 不会根据总耗时推算分阶段耗时，也不会补造 Token usage。
