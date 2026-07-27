# Round 16 评测框架选型

核对日期：2026-07-27。资料来源：Promptfoo 官方文档与 GitHub、npm；NVIDIA garak GitHub；Microsoft PyRIT GitHub 与 Releases。

| 框架 | 当前核对版本/许可证 | 能力与兼容性 | 本轮结论 |
| --- | --- | --- | --- |
| Promptfoo | npm `0.121.19`，MIT，持续维护；官方文档要求 Node `^20.20.0` 或 `>=22.22.0` | Node CLI；Python Provider；参数化断言；Red Team；原生 HTML/JSON/JUnit；CI Artifact；离线 Stub 可运行 | 选择。与 Node 22.23.1、现有 Provider、CI 和报告链路兼容 |
| garak | GitHub 当前持续维护，Apache-2.0；Python 工具 | 面向模型漏洞探测，探针/生成策略以真实模型或目标服务为中心；报告和 CI 方式不同于本项目现有 Promptfoo 链路 | 暂不引入第二套框架；会重复 Provider、断言和报告门禁 |
| Microsoft PyRIT | GitHub v0.13.0，MIT，持续维护 | Python 风险识别与 Red Team 组件，支持复杂攻击编排；依赖和运行模型明显重于本轮离线契约测试 | 暂不选择；本轮禁止新增 Python Red Team 框架和运行时依赖 |

Promptfoo 仍固定为 `0.121.19`：npm 元数据显示该版本已发布且仍为公开稳定版本；Round 15C 的 10/10 离线基线保持不变。Round 16 只扩展同一配置的离线安全用例，不调用真实模型。框架负责用例参数化、Provider 调度、Assertions、失败退出码和 HTML/JSON/JUnit；项目只提供薄的确定性边界适配。

本轮不实现获授权的真实执行器；`executor_type=real` 固定 fail closed，因此 CI 和本地默认路径都不会调用 DashScope。未来如经新授权增加真实通道，只能默认关闭、最多 12 条、仅文本组件，并继续禁止图片、数据库写入、自动重试、模型正文持久化和 LLM Judge。

## v2 预算例外记录

Round 16 原定自定义生产代码预算为 220 行。外部审查后新增的明确需求要求运营评测成为独立页面，因此本次不通过机械压缩代码来满足旧预算：后端报告适配约 106 行，独立 `QualityDashboard.vue` 约 207 行，合计超过原预算。该超额只来自独立可视化页面；本轮没有自研评测框架、通用 Runner 或报告生成器。Promptfoo Provider 为 76/80 行，security assertion 为 58/100 行，仍符合评测适配预算。

官方资料：

- Promptfoo Red Team 配置：<https://www.promptfoo.dev/docs/red-team/configuration/>
- Promptfoo Red Team 快速开始：<https://www.promptfoo.dev/docs/red-team/quickstart/>
- Promptfoo npm：<https://www.npmjs.com/package/promptfoo>
- Promptfoo GitHub：<https://github.com/promptfoo/promptfoo>
- garak GitHub：<https://github.com/NVIDIA/garak>
- PyRIT GitHub：<https://github.com/microsoft/PyRIT>
- PyRIT Releases：<https://github.com/microsoft/PyRIT/releases>
