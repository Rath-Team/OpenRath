# OpenRath

![OpenRath logo](assets/readme/logo.png)

<p align="center">
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/v/openrath.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/pyversions/openrath.svg" alt="Python"></a>
  <a href="https://github.com/Rath-Team/OpenRath/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-blue.svg" alt="License"></a>
  <a href="https://docs.openrath.com"><img src="https://img.shields.io/badge/docs-openrath.com-blue" alt="Docs"></a>
</p>

<div align="center">

[English](README.md) | 简体中文

</div>

---

**OpenRath 是一个类似 PyTorch 的多智能体 & 多会话框架。**

它把 Agent 运行时状态拆成明确的、可灵活组合的 Python 对象：

- **Session** 承载对话状态与 Agent 间协作谱系。
- **Sandbox** 决定工具到底在哪里运行。
- **Memory** 持久化跨运行保留的 Agent 记忆状态。
- **Tool** 是暴露给模型的“算子调用”。
- **Agent** 是可复用、可组合的 Session 变换层。
- **Workflow** 把多个 Agent/Workflow 组合成更大的系统。
- **Selector** 在运行时于自描述的 Workflow 之间路由，使 `if` / `while` 控制流仍是普通 Python。

---

## OpenRath 在 PyTorch 中的照应

| PyTorch 概念 | OpenRath 概念 | 含义 |
| --- | --- | --- |
| `Tensor` | `Session` | 流动的运行时值：有序 chunks、placement、lineage、usage。 |
| `Device` | `Sandbox` / `Backend` | 工具运行的执行环境：local process、OpenSandbox 或其他 backend。 |
| `Parameter` | `Memory` | 绑定到 Agent 或 store 的持久状态，可 recall、commit、跨运行保留。 |
| `Function` | `Tool` | 带模型可见 schema 和运行时行为的 callable operation。 |
| `nn.Linear` | `Agent` | 用 prompt、provider、tools、memory 把一个 Session 映射成另一个 Session 的可复用层。 |
| `nn.Module` | `Workflow` | 组合 Agent、Tool、Session transform 和嵌套 Workflow 的容器。 |
| 控制流 | `Selector` | 由 LLM 驱动的路由器，在运行时挑选下一个该运行的 Workflow，让 Agent 间的 `if` / `while` 动态控制流成为可能。 |

大多数 Agent 框架从 agent loop 开始。OpenRath 从 **Session** 开始。当一个应用同时需要多个 Agent、多个分支、持久记忆、沙箱执行和可追踪谱系时，这个差异会变得很关键。

OpenRath 面向的是：多个 Agent 在多个可分支 Session 上协作，仍能同时追踪每个角色、工作区、memory 写入和最终输出。

| 范式 | 典型形态 | 案例 |
| --- | --- | --- |
| Single agent, single session | 一个模型处理一条对话 | ChatGPT 式聊天 |
| Multi-agent, single session | 多个角色读写同一份共享状态 | 子代理式多 Agent 协作 |
| Single agent, multi-session | 一个 Agent 管理多个 Session 分支 | OpenClaw 式 session fanout |
| Multi-agent, multi-session | 多个 Agent 共享多个 Session，且通过 Session 进行协作/自我进化 | **OpenRath** |

---

## 为什么使用 Multi-Agent-Multi-Session 范式

Agent 其实是 Session 的变换层，因此真正需要被 fork、merge、复用和追踪的是 Session 这条数据流，而不是每个 Agent 各自维护的一段 message history。

OpenRath 的设计针对的是 Agent 系统从单个助手走向大规模集群时出现的问题：

- **以 Session 作为数据流动核心。** 上下文以结构化 chunk 保存，而不是反复复制 message 字符串。Workflow 可以直接复用、fork、compress、传递上下文，从而极大提高上下文复用率，减少 token 消耗。
- **面向超大规模 Agent Cluster 的 Session Graph。** 大型运行需要解释哪个角色、哪个分支、哪个工具调用、哪个 workspace 产生了某个答案。Session lineage 给运行时提供图状 provenance，而不是一堆事后日志。
- **Session 与 Agent Memory 的长短期记忆机制。** 短期 Session 状态和长期 Memory 协作：Agent 可以在运行前 recall 事实，在运行后 commit 新知识，让 Agent Cluster 在使用中持续进化。
- **模块化 Workflow。** 管理成百上千个 Agent 会变成组合问题，而不是 prompt spaghetti。Agent 是小层，Workflow 是可嵌套、可复用、可检查的模块，让大规模 Agent 管理不再困难。
- **Sandbox 作为 Backend。** 执行环境不硬编码到某一个 shell。Local、OpenSandbox 或未来第三方 backend 都可以接到同一个 Session placement 模型后面，灵活接入第三方执行后端。
- **Memory 作为 Backend。** Recall 不硬编码到某一个数据库。Local memory、OpenViking 或未来第三方 memory 系统可以共享同一条 memory plane，灵活接入第三方记忆后端。

结果是一个状态、执行、记忆、编排彼此解耦但又通过同一个流动值连接起来的运行时：`Session`。

---

## 一个极小但组件完整的 OpenRath Workflow

```python
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from rath import flow
from rath.flow.tool import FlowToolCall
from rath.session import Session


class WordCountInput(BaseModel):
    text: str = Field(description="Text to count.")


# OpenRath Tool
class WordCountTool(FlowToolCall):
    @property
    def name(self) -> str:
        return "word_count"

    @property
    def description(self) -> str:
        return "Count words in a short text."

    @property
    def parameters(self) -> Mapping[str, Any]:
        return WordCountInput.model_json_schema()

    def __call__(self, session: Session, arguments: Mapping[str, Any]) -> dict[str, int]:
        data = WordCountInput.model_validate(dict(arguments))
        return {"words": len(data.text.split())}


# OpenRath Workflow
class ReadmeWorkflow(flow.Workflow):
    def __init__(self) -> None:
        # OpenRath Provider
        provider = flow.Provider(model="gpt-5.5")

        # OpenRath Agent
        self.agent = flow.Agent(
            "Use the `word_count` tool, then answer briefly.",
            provider,
            tools=[WordCountTool()],
            memory="local",
        )

        # OpenRath Compressor
        self.compressor = flow.Compressor(
            "Compress the run into one concise assistant message.",
            provider,
        )

    def forward(self, session: Session) -> Session:
        # OpenRath Memory
        self.agent.remember_memory("The user likes compact technical summaries.")
        session = self.agent(session)
        self.agent.commit_memory(session)
        return self.compressor(session)


workflow = ReadmeWorkflow()

# OpenRath Session
user_session = Session.from_user_message(
    "Count the words in: OpenRath makes agent clusters traceable."
)

# OpenRath Sandbox
user_session = user_session.to("local", spec="./")
out = workflow(user_session)
```

这个小程序在很短篇幅里展示了完整形状：`Session` 承载数据，`Sandbox` 放置执行，`Tool` 注册到 `Agent`，`Memory` 跨运行持久化，`Workflow` 组合路径，`Compressor` 压缩最终上下文。

---

## 运行时组件

### Session — 流动的状态载体

`Session` 是 OpenRath 的中心运行时值。它持有一个有序 chunk table，包含 system、user、assistant、tool-result 等行，同时记录 sandbox placement、lineage、token usage 和 pending lazy work。

这也是 OpenRath 能表达「不止一条聊天记录」的原因。Session 可以 fork 出新分支，可以 detach 切断父链，可以与兼容分支 merge，可以序列化为 JSONL，也可以交给另一个 workflow。Agent 侧指令同样表示为自己的 session chunks，由 loop prepend，而不是反复拼接进不透明 prompt。

常用入口：

- `Session.from_user_message(...)` 创建用户侧 Session。
- `Session.from_agent_prompt(...)` 创建 Agent/system prompt Session。
- `session.to("local", spec="./")` 绑定 sandbox backend 和 workspace。
- `session.fork()` 创建可追踪分支。
- `session.detach()` 创建不带父链的新 Session。
- `session.merge(...)` 合并兼容分支并记录 merge lineage。

### Sandbox — 工具真正落地的位置

Sandbox 是 Session 的执行 placement，类似决定计算落在哪个 device 上。工具不是在抽象 prompt 里运行，而是在当前 Session 绑定的 sandbox 中执行。

```python
session = Session.from_user_message("List files").to("local", spec="./")
```

`local` backend 始终可用，会在宿主工作区中运行文件、命令和代码工具。可选的 `opensandbox` backend 会把同一套 tool layer 接到容器化的 OpenSandbox runtime。返回的 Session 会保留 active sandbox ownership，因此后续工具调用仍从同一执行上下文继续，而不会悄悄漂移到另一个目录或机器。

### Memory — 跨运行保留的记忆

Memory 是与 sandbox 执行平行的持久平面。它不是 tool result，也不只是 prompt 文本；它是可绑定到 Agent、可在运行前 recall、可在运行后 commit 的状态。

基础安装自带零依赖的 local memory backend。它把数据存到 `.openrath/memory/`，无需 LLM 即可用 BM25 做 lexical recall；如果配置了 embedding provider，也可以使用 embedding 排序。需要更丰富外部 memory 服务的用户可以选择 OpenViking backend。

```python
with flow.Agent("You remember useful facts.", model="gpt-5.5", memory="local") as agent:
    agent.remember_memory("The user works mostly in Python.")
    hits = agent.recall_memory("preferred programming language")
```

Agent memory API 刻意做得容易发现：

- `memory=` 在构造时绑定 store。
- `remember_memory(...)` 写入明确事实。
- `recall_memory(...)` 检索相关条目。
- `commit_memory(...)` 在运行后保存 transcript。
- `commit_on_forward=True` 可以自动 commit。

### Tool — 模型可见的函数面

`FlowToolCall` 是模型可见的工具抽象。它同时拥有工具的两侧：展示给 LLM 的 name、description、JSON schema，以及针对 `Session` 执行的 Python call。

这样 tool schema 和 tool behavior 会保持在一起。内置工具覆盖常见文件系统、shell 和代码执行路径；自定义 Python 工具可以实现同一接口；stdio MCP 工具也可以被适配成普通 `FlowToolCall` 加入 loop。

关键分层是：

- `FlowToolCall` 是 flow layer 中模型可见的 function。
- `BackendTool*` 是 sandbox backend 消费的底层 payload。

### Agent — 可复用的一层变换

`flow.Agent` 是大多数用户首先接触的小型可复用层。它更像 `nn.Linear`，而不是完整应用：它有 prompt、provider、可选 tools、可选 memory，以及一条 `forward(session) -> session` 路径。

Agent 不拥有整个世界。Session loop 仍然是引擎，sandbox 仍然是 Session placement，memory 仍然是独立 store。这样既让单 Agent 场景足够简单，也允许同一个 Agent 被放进更大的 workflow。

### Workflow — 从容组合大规模 Agent

`flow.Workflow` 是组合面。子类实现：

```python
def forward(self, session: Session) -> Session:
    ...
```

一个 Workflow 可以串联多个 Agent、fork Session、压缩上下文、调用工具、分发到子 Workflow，并返回新的 Session。因为输入和输出都是 `Session`，嵌套 Workflow 时不需要为每一层发明新的 state format。

若路由需要在运行时依据对话内容决定，`flow.Selector` 是一个由 LLM 驱动、面向自描述 Workflow（各自带 `description`）的路由器。它返回下一个该运行的 Workflow，或在任务结束时返回空操作 `flow.EmptyWorkflow`——于是 `if` / `while` 仍是普通 Python：

```python
selector = flow.Selector(provider)
while not isinstance(
    nxt := selector.forward(session, triage, tech, wrapup), flow.EmptyWorkflow
):
    session = nxt(session)
```

---

## 快速安装

```bash
pip install openrath
```

可选的 sandbox 与 memory 集成：

```bash
pip install "openrath[opensandbox]"
pip install "openrath[openviking]"
```

源码开发：

```bash
git clone https://github.com/Rath-Team/OpenRath.git
cd OpenRath
uv sync --group dev --group docs
```

大多数 LLM 示例使用 OpenAI-compatible 环境变量：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://your-gateway/v1
export OPENAI_DEFAULT_MODEL=your-model-name
```

也可以在 `~/.openrath/config.json` 中配置 provider。环境变量优先级更高。

---

## 跑起来理解

`example/` 目录是一组编号递进的学习阶梯。每个脚本只介绍一个概念，把样板代码放进 `_shared/`，重点展示核心对象如何配合。

运行第一层：

```bash
python example/01_hello_agent.py
```

| # | 文件 | 概念 | 需要 key? |
| --- | --- | --- | :---: |
| 01 | [`01_hello_agent.py`](example/01_hello_agent.py) | 最小 OpenRath 程序：构造 `flow.Agent`，在 `Session` 上调用，并流式输出。 | 是 |
| 02 | [`02_session_lineage.py`](example/02_session_lineage.py) | 用 `fork` 创建分支，用 `detach` 切断 lineage，查看 session graph 并导出 JSONL。 | 否 |
| 03 | [`03_sandbox_backend.py`](example/03_sandbox_backend.py) | 将同一个 Session 放到 `local` 或 `opensandbox`，观察工具在哪里执行。 | 是 |
| 04 | [`04_tools_builtin.py`](example/04_tools_builtin.py) | 使用每个 loop 可以暴露的内置文件系统和 shell 工具。 | 是 |
| 05 | [`05_custom_tool.py`](example/05_custom_tool.py) | 实现带 JSON schema 和 Python runtime behavior 的自定义 `FlowToolCall`。 | 是 |
| 06 | [`06_mcp_tool.py`](example/06_mcp_tool.py) | 包装一个极小的 stdio MCP server，不写新 tool class 也能借用工具。 | 否 |
| 07 | [`07_streaming.py`](example/07_streaming.py) | 接收 streaming deltas，并在运行后查看累计 token usage。 | 是 |
| 08 | [`08_compress.py`](example/08_compress.py) | 用 `flow.Compressor` 把长 Session 压缩成更小的上下文 Session。 | 是 |
| 09 | [`09_memory.py`](example/09_memory.py) | 使用 local memory backend 进行 remember、recall，并可选 commit 一次真实对话。 | 否 |
| 10 | [`10_provider_variation.py`](example/10_provider_variation.py) | 通过修改 `Provider` 切换模型厂商，同时保持 Session 和 Workflow 代码稳定。 | 是 |
| 11 | [`11_dynamic_selector.py`](example/11_dynamic_selector.py) | 用 `flow.Selector` 在自描述的 Workflow 之间路由：`if` 分支与在 `flow.EmptyWorkflow` 时结束的 `while` 循环。 | 是 |

更多设置和 shared helpers 见 [`example/README.md`](example/README.md)。

---

## 文档与链接

- 文档：[https://docs.openrath.com](https://docs.openrath.com)
- 仓库：[https://github.com/Rath-Team/OpenRath](https://github.com/Rath-Team/OpenRath)
- Issues：[https://github.com/Rath-Team/OpenRath/issues](https://github.com/Rath-Team/OpenRath/issues)

本地构建文档：

```bash
uv run sphinx-build -M html docs/source docs/_build
```

---

## License

OpenRath 使用 BSD 风格许可证。详见 [LICENSE](LICENSE)。
