# 架构故事

OpenRath 的核心不是“再写一个 chat wrapper”，而是给 Agent 运行时补上四个工程对象：状态、工具、执行环境、组合。

## 1. 状态：Session 不是字符串

Agent 的运行状态天然包含多种信息：

- 用户输入；
- system / agent 指令；
- assistant 回复；
- tool calls；
- tool results；
- sandbox 绑定；
- lineage 元数据。

如果这些东西都塞进字符串，系统很快失去结构。OpenRath 用 `ChunkTable` 记录分块，并用 `Session` 承载 sandbox 和 lineage。

## 2. 工具：FlowToolCall 是模型和运行时之间的桥

一个工具需要同时回答两个问题：

1. 模型看到什么 schema？
2. 真实执行时怎么处理 arguments？

所以 `FlowToolCall` 同时提供 `name`、`description`、`parameters` 和 `__call__`。这比“全局函数注册表”更直接，也便于把工具实例交给不同 agent。

## 3. 执行环境：Backend 把副作用隔离出去

命令执行、文件写入、代码运行都是副作用。OpenRath 把这些副作用交给 `Backend`：

这样同一个上层工具可以运行在本地进程，也可以运行在 OpenSandbox 容器里。

## 4. 组合：Workflow 让 agent 成为模块

`Workflow` 的目标是让多 agent 组合像写模块一样清晰：

```python
class ResearchWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.planner = AgentParam(...)
        self.executor = AgentParam(...)

    def forward(self, session):
        ...
```

当前源码中的 `Workflow` 很轻，只负责收集 `AgentParam` 和提供 `forward` 约定。复杂编排可以在用户层实现。

## 展示重点

讲架构时不要一开始讲“多智能体宏大愿景”。先讲一个很具体的问题：当 agent 调工具时，状态、工具 schema、执行环境和返回结果如何被结构化保存。这个问题讲清楚，OpenRath 的价值自然成立。
