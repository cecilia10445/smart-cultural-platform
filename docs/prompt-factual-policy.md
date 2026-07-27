# Prompt 与事实边界

模板版本为 `cultural-product-rag-v1`。System Prompt 固定，用户 Brief 通过 JSON 数据边界发送，不能覆盖系统规则。文本模型结构化输出产品名称、事实背景、设计解读、产品讲解、`used_source_ids` 和证据状态；图片模型只接收由 Brief 与产品名称构造的产品展示图 Prompt。

Prompt 将用户确认事实、冻结 RAG 官方事实和资料不足状态分别标记。检索别名只进入 BM25 索引，永远不进入证据块或引用。服务端校验 `used_source_ids` 是本次证据来源的无重复子集；越界引用返回 `MODEL_INVALID_CITATIONS`，不回显模型内容。无可靠证据时 `used_source_ids` 必须为空并返回 `insufficient_evidence`。

本地语料只有六件 Met Open Access 对象，运行时不访问 Met API。这是用于完成可解释引用闭环的小型检索模块，不是实时检索、通用知识库、自动事实核验或 Agent。
