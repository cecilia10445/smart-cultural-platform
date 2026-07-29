# RAG 与文创生成逻辑演进记录

## 一、初始设计问题

原设计目标希望通过 RAG 降低模型幻觉：

```
用户输入
  ↓
RAG检索
  ↓
判断是否有依据
  ↓
LLM生成
```

## 二、发现的问题：RAG职责错误

初始逻辑实际上把 RAG 当成**事实验证系统**，导致：

```
用户提供文化信息
  ↓
RAG没有匹配
  ↓
认为资料不足
  ↓
阻止生成
```

**问题：** 用户输入可能来自真实但未收录资料。RAG不是完整知识库。未检索 ≠ 错误。

## 三、第一次修改：引入三态模型

增加三种 `evidence_status`：

| 状态 | 含义 | 要求 |
|------|------|------|
| `grounded` | RAG提供依据 | `used_source_ids` 必须来自RAG |
| `insufficient_evidence` | 用户明确要求历史考据但系统没有资料 | 不编造 |
| `creative_only` | 没有RAG依据但允许创意设计生成 | 无引用，不编造 |

## 四、第二次发现：三态仍然混淆

即使允许 `creative_only`，模型仍可能使用自身训练知识扩写历史信息，并自己声明 `source_type`。

例如用户输入"三兔共耳"，模型输出"敦煌莫高窟第407窟隋代藻井"并标记 `source_type=user`——实际上无法确认。

## 五、架构方向调整

系统目标从**判断内容真假**改为**记录内容来源**。

**原则：** 系统保证"这句话来自哪里"，而不是保证"这句话一定是真的"。

## 六、最终目标架构

### 数据来源分层

```
User Claims     用户输入事实
      +
RAG Evidence    系统检索资料
      +
Creative Gen    模型设计内容
```

### 输出协议

- `creative_origin`: `{ text, source_type: "user"|"rag"|"creative" }`
- `cultural_meaning`: `{ text, source_type: "user"|"rag"|"creative" }`
- `factual_background`: `{ text, source_type: "user"|"rag"|"none" }`

## 七、当前状态

### 已完成
- ✅ RAG 不再阻止生成
- ✅ `creative_only` 正常返回
- ✅ `grounded` 引用校验保留
- ✅ `used_source_ids` 校验保留
- ✅ 后端生成链路成功（HTTP 200）
- ✅ 数据库写入成功
- ✅ 前端适配新版响应结构

### 待优化
- ⬜ Evidence trace 进一步细化（`user_claims` / `rag_evidence` / `creative_generation` 分层）
- ⬜ 减少依赖 LLM 自报 `source_type`
- ⬜ 前端展示 `source_type` 标识
