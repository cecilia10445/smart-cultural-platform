# Round 15B 产品展示方案选型（2026-07-27）

本轮目标是给文创概念提供清晰、可解释的产品展示图，而不是 CAD 级三视图或工业设计定稿。官方 [wan2.6-t2i 图像生成 API](https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference) 支持现有的异步图像生成接口；每张图独立计费，适合一次生成一张展示板。

| 方案 | 官方能力与一致性 | 调用/改造 | 结论 |
| --- | --- | --- | --- |
| A. `wan2.6-t2i` 单张展示板 | 文本到图接口与现有调用兼容；以严格正、负提示词要求正反面、三视图或主视图。单图中的多视图是概念表达，不承诺 CAD 精度。 | 1 次图片调用，无参考图，无新框架；只改契约、提示词和展示。 | 采用。 |
| B. `wan2.6-image` | 官方 [图像生成/编辑 API](https://help.aliyun.com/zh/model-studio/wan-image-generation-api-reference) 面向编辑或图文交错；编辑模式需要输入参考图。官方也建议纯文生图选用 `wan2.6-t2i`。 | 需更换接口；参考图和多图数量会增加成本、状态与测试面。 | 暂不采用。 |
| C. 多次生成加 Pillow 合成 | 可由本地代码拼图，但不同调用之间的形态、纹样和材质无法天然一致。 | 至少多次图片调用，增加成本、合成逻辑与失败面，并引入图片处理依赖。 | 不采用。 |

因此 Round 15B 保持 `wan2.6-t2i`、单次调用和一张白底产品展示图；`presentation_mode` 仅确定性约束画面布局。负提示词继续使用图像接口支持的字段，并限制在官方长度边界内。不会使用参考图、增加图片调用或引入新框架。

## v5 图像方案复核（离线设计，不代表已授权真实调用）

官方文档确认 `wan2.6-t2i` 支持文生图和 1:4 至 4:1 的画面比例；`wan2.6-image` 的北京同步接口支持 `enable_interleave=false` 的图像编辑模式，要求 1–4 张参考图，可通过公开 URL 或受控 Base64 输入，`n=1` 可将成本限制为一张输出。该模式用于主体一致性、视角编辑与基于参考图的编辑；临时 URL 只作为请求输入，不持久化。[Wan2.6 文生图 API](https://help.aliyun.com/en/model-studio/text-to-image-v2-api-reference)、[Wan2.6 图像生成与编辑 API](https://help.aliyun.com/en/model-studio/wan-image-generation-api-reference)、[Wan 图像编辑示例](https://help.aliyun.com/en/model-studio/wan-image-edit)

比较结果：A 单次加强 Prompt 成本最低但无法可靠保持正反面/多视角身份；C 多次独立生成再拼接会增加调用和一致性风险；B 先用 `wan2.6-t2i` 生成主图，再用北京工作空间可见的 `wan2.6-image` 同步编辑，能够把参考图、背面要求和视角布局放在同一编辑契约中。因此 v5 默认选择 B。实现预算控制在约 220 行，不新增迁移或通用框架；真实调用仍需单独授权。

文案仍使用当前 Responses API 调用与严格服务端字段校验。官方 [Qwen 结构化输出说明](https://help.aliyun.com/zh/model-studio/qwen-structured-output) 展示的是 Chat Completions / DashScope Generation 的 `response_format` 用法，未证明当前 Responses 调用可可靠采用该字段；本轮不切换 API，也不假定兼容性。

## 详情与图片预览交互

比较 Vue 内置 `Teleport`、原生 HTML `dialog` 与 Headless UI/PrimeVue Dialog 后，本轮选择 `Teleport + dialog`：详情和图片预览挂载到 `body`，使用浏览器原生 modal、焦点和 Escape 语义；不增加 UI 框架，且可由 Playwright 直接验证。Headless UI/PrimeVue 会增加依赖和主题适配面；手写 div/aria 模态框则重复实现焦点管理，因此不采用。
