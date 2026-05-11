# 设计概览

OpenRath 采用与 **PyTorch 式易用性**一致的隐喻，但并不包装 PyTorch 本体：

- **有状态磁带** — [`Session`](session.md) 保存有序的会话分块（system、user、assistant、tool 结果等），是贯穿工作流的主要对象。
- **组合** — [`Workflow`](workflow_agent.md) 通过属性赋值聚合具名的 [`AgentParam`](workflow_agent.md)，类似 `nn.Module` 的子模块。
- **函数式工具载荷** — 结构化调用（`FlowToolCall`）由 `rath.flow.tool` 下的小工厂构造，类比 `torch.nn.functional` 风格。
- **后端** — 沙箱（`BackendSandbox`）与并发辅助（`Stream`、`Event`）类似为执行选择**设备**或运行时。

该模型仅用于帮助理解：OpenRath **不包含** autograd 或张量。

若需对照大型项目如何区分叙述文与 API 参考，可见 [PyTorch 文档](https://docs.pytorch.org/docs/stable/index.html)。

## 分层

| 层次 | 包 | 职责 |
|------|-----|------|
| 会话运行时 | `rath.session` | 分块、谱系、注册表、会话循环 |
| 执行 | `rath.backend` | 沙箱句柄、分发、结果、流 |
| Flow 门面 | `rath.flow` | `Workflow`、`AgentParam`、工具表辅助 |
| LLM I/O | `rath.llm` | 兼容 OpenAI 的请求/响应、客户端 |

经验法则：**`rath.flow.tool` 定义工具调用值**；**`rath.backend` 在沙箱上执行它们**。`rath.flow.tool` **不** import `rath.backend`。

**下一篇：** [主要组件](main_components.md)
