# Round 15 评测框架选型

核对日期：2026-07-27。此轮的目标是为既有文创生成 v2 链路增加一套可在本机和 CI 离线运行的 Stub 评测，以及框架原生的 JSON、HTML、JUnit 输出；它不是生产模型质量结论，也不调用 DashScope、数据库、Met API 或任何云端评测服务。

## 核对结果

| 框架 | 当前稳定版本 | 许可证 | 维护与兼容性 | CI、报告与离线能力 |
| --- | --- | --- | --- | --- |
| Promptfoo | 0.121.19 | MIT | 官方 npm registry 的 `engines` 为 `^20.20.0 || >=22.22.0`；本项目 Node 22.23.1 满足要求。官方仓库持续提交并维护文档。 | CLI 有自定义 Python Provider 与 Python assertion；`promptfoo eval -o` 原生支持 JSON、HTML、JUnit XML。自定义本地 Provider 可完全离线运行。 |
| DeepEval | 4.1.3 | Apache-2.0 | PyPI 要求 Python >=3.9,<4.0；官方定位包含 LLM-as-a-judge/NLP 评测。 | 有 Python/pytest 与 CI 文档，但本轮无需新增 Python 主评测框架或 judge 模型调用。 |
| Langfuse | 4.14.1 | MIT | PyPI 要求 Python >=3.10,<4.0；v4 是近期重写，核心是 tracing/observability SDK。 | 可连接观测与评测工作流，但需要项目级遥测与服务配置，超出离线 MVP 范围。 |

版本和许可证以各项目在上述日期的官方 npm/PyPI/GitHub 页面为准：

- Promptfoo：[文档](https://www.promptfoo.dev/docs/intro/)、[npm](https://www.npmjs.com/package/promptfoo)、[GitHub](https://github.com/promptfoo/promptfoo)。官方 CLI 输出格式、Python Provider 和 Python assertion 分别见[命令行文档](https://www.promptfoo.dev/docs/usage/command-line/)、[Provider 文档](https://www.promptfoo.dev/docs/providers/python/)与[断言文档](https://www.promptfoo.dev/docs/configuration/expected-outputs/)。
- DeepEval：[文档](https://deepeval.com/docs/getting-started)、[PyPI](https://pypi.org/project/deepeval/)、[GitHub](https://github.com/confident-ai/deepeval)。
- Langfuse：[文档](https://langfuse.com/docs)、[PyPI](https://pypi.org/project/langfuse/)、[GitHub](https://github.com/langfuse/langfuse)。

## 本轮选择 Promptfoo

Promptfoo 是唯一主框架。它与现有 Vue/Flask/Python 项目边界契合：独立的 Node 子目录固定 `promptfoo@0.121.19`，通过官方 Python Provider 接入既有组件，借助框架断言与原生导出生成报告。这样无需把 Prompt、Brief 校验、RAG 或 Stub 业务逻辑复制到另一套 Runner，也无需自建 HTML 报告器。报告会保留在本机和 GitHub Actions Artifact；不使用 `share`、Promptfoo Cloud 或任何 API key。

本轮不选择 DeepEval，是因为它会引入第二套主评测框架，且其常见价值在 judge/NLP 指标；本 MVP 明确禁止额外真实模型调用。暂不选择 Langfuse，是因为它解决的是跨调用 tracing/observability 与远程项目配置，不是当前所需的离线、固定数据集、一次性报告闭环。两者均不作为依赖引入。

## 安全与解释边界

评测只运行 `executor_type=stub`、`data_origin=test`、`measurement_scope=harness_self_test`。任何测得的耗时都是本地 harness 运行时间，绝不标注为真实模型延迟。Provider 只把冻结语料中经现有 RAG 服务验证的来源放入引用；检索别名、原始 Prompt、环境变量和凭据不进入输出。Promptfoo 官方也提示导出可能包含变量、Prompt 和原始输出，因此本轮会在生成后对三份报告进行限定敏感信息扫描，再作为 CI Artifact 保存。
