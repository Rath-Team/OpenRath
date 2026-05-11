# 网站首页草案

这一版更像官网首页，不像 API 文档。

## Hero

**OpenRath**

Session-centered runtime for tool-using agent workflows.

把 Agent 的对话状态、工具调用、沙箱执行和 LLM 请求拆成可组合的 Python 对象。

```python
agent = flow.Agent("You are helpful.", model="gpt-5.5")
user = Session.from_user_message("Summarize this workspace.").to("local")
out = agent(user)
```

## 三个卖点

### 1. State is explicit

`Session` 保存 chunk、sandbox placement 和 lineage。工作流输入输出都是 `Session`，不是裸字符串。

### 2. Tools are structured

`FlowToolCall` 同时定义 LLM schema 和执行逻辑。内置 shell / file-write 工具可以走本地或 OpenSandbox 后端。

### 3. Workflows compose

`Workflow` 用 `forward(session) -> session` 组织 agent。`AgentParam` 像子模块一样通过属性登记。

## 架构区

## CTA

- Read the user guide
- Run the local sandbox example
- Write your first FlowToolCall

## 适合删减的部分

如果首页要更短，可以删掉三段解释，只保留 hero、代码和架构图。详细解释放进 docs。
