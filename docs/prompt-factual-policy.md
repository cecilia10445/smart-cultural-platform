# Prompt 与事实边界

模板版本为 `cultural-product-v1`。System Prompt 固定，用户 Brief 通过 JSON 数据边界发送，不能覆盖系统规则。文本模型只输出产品名称、设计解读和产品讲解；图片模型只接收由 Brief 与产品名称构造的产品展示图 Prompt。

文化背景不由模型生成：它只整理 `confirmed_facts`。没有确认事实时固定返回 `insufficient_evidence`。`evidence_mode` 始终为 `user_supplied_only`，`citations` 始终为空数组。本轮没有 RAG、实时检索、自动事实核验或 Agent。
