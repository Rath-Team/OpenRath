# OpenRath

<p align="center">
  <img src="assets/readme/logos/openrath-logo-white.png" alt="OpenRath logo" width="860" />
</p>

<p align="center">
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/v/openrath.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/openrath/"><img src="https://img.shields.io/pypi/pyversions/openrath.svg" alt="Python"></a>
  <a href="https://github.com/Rath-Team/OpenRath/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-blue.svg" alt="License"></a>
  <a href="https://docs.openrath.com"><img src="https://img.shields.io/badge/docs-openrath.com-blue" alt="Docs"></a>
  <a href="https://arxiv.org/abs/2606.19409"><img src="https://img.shields.io/badge/arXiv-2606.19409-b31b1b.svg?logo=arxiv&amp;logoColor=white" alt="arXiv"></a>
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
- **Tool** 是暴露给模型的"算子调用"。
- **Agent** 是可复用、可组合的 Session 变换层。
- **Workflow** 把多个 Agent/Workflow 组合成更大的系统。
- **Selector** 在运行时于自描述的 Workflow 之间路由，使 `if` / `while` 控制流仍是普通 Python。

---

## OpenRath 的 PyTorch 视角

<p align="center">
  <img src="assets/readme/diagrams/pytorch-lens.png" alt="OpenRath 的 PyTorch 视角" width="860" />
</p>

| PyTorch 理念 | OpenRath 理念 | 含义 |
| --- | --- | --- |
| `Tensor` | `Session` | 流动的运行时值：有序 chunks、placement、lineage 和 usage。 |
| `Device` | `Sandbox` / `Backend` | 工具运行的执行环境：本地进程、OpenSandbox 或其他后端。 |
| `Parameter` | `Memory` | 绑定到 Agent 或 store 的持久状态，可在跨运行时 recall 和 commit。 |
| `Function` | `Tool` | 带模型可见 schema 和运行时行为的 callable operation。 |
| `nn.Linear` | `Agent` | 使用 prompt、provider、tools 和 memory 将一个 Session 映射到另一个 Session 的可复用层。 |
| `nn.Module` | `Workflow` | 用于 agent、tools、session 变换和嵌套 workflows 的可组合容器。 |
| control flow | `Selector` | 一个 LLM 驱动的路由器，在运行时选择下一个 workflow，实现 Agent 间的动态 `if` / `while`。 |

大多数 Agent 框架从 agent loop 开始。OpenRath 从 **Session** 开始。当需要一个应用同时处理多个 Agent、多个分支、持久记忆、沙箱执行和可追踪谱系时，这种差异就很重要。

OpenRath 为此而设计：多个 Agent 在多个可分支 Session 上协作，同时仍能追踪每个 role、workspace、memory 写入和最终输出。

<p align="center">
  <img src="assets/readme/diagrams/paradigm-map.png" alt="多智能体多会话映射" width="860" />
</p>

| 范式 | 典型形态 | 示例 |
| --- | --- | --- |
| 单 Agent，单 Session | 一个模型处理一条对话 | ChatGPT 式聊天 |
| 多 Agent，单 Session | 多个角色读写同一份共享状态 | 子代理式多 Agent 协作 |
| 单 Agent，多 Session | 一个 Agent 管理多个 Session 分支 | OpenClaw 式 session 扇出 |
| 多 Agent，多 Session | 多个 Agent 共享多个 Session，通过 Session 协作或演化 | **OpenRath** |

---

## 为什么是多 Agent 多 Session 范式

一个 Agent 是 Session 上的变换层，因此真正需要被 fork、merge、复用和追踪的是 Session 数据流，而不是每个 Agent 各自维护的一段 message history。

<p align="center">
  <img src="assets/readme/diagrams/multi-agent-multi-session.png" alt="为什么是多 Agent 多 Session" width="860" />
</p>

OpenRath 的设计解决的是 Agent 系统从单个助手走向大型集群时出现的问题：

- **Session 作为数据流核心。** 上下文以结构化 chunks 存储，而不是反复复制 message 字符串。Workflow 可以直接复用、fork、压缩和传递上下文，极大提高上下文复用率并减少 token 消耗。
- **面向大规模 Agent 集群的 Session Graph。** 大型运行需要解释哪个 role、分支、tool call 和 workspace 产生了某个答案。Session lineage 为运行时提供图状的 provenance 层，而不是一堆事后日志。
- **Session 加上 Agent Memory。** 短期 Session 状态和长期记忆协同工作：Agent 可以在运行前 recall 事实，在运行后 commit 新知识，使 Agent 集群在使用过程中持续改进。
- **模块化 Workflow。** 管理成百上千个 Agent 变成一个组合问题，而不是 prompt 意大利面。Agent 是小层；Workflow 是可嵌套、可复用、可检查的模块，使大规模 Agent 管理变得可行。
- **Sandbox 作为后端。** 执行不硬编码到一个 shell。本地、OpenSandbox 或未来的第三方后端都可以在同一个 session placement 模型后面，使第三方执行后端可以灵活接入。
- **Memory 作为后端。** Recall 不硬编码到一个数据库。本地 memory、OpenViking 或未来的第三方 memory 系统可以共享同一个 memory plane，使第三方 memory 后端可以灵活接入。

结果是一个运行时，其中状态、执行、记忆和编排保持足够的解耦以扩展，但仍通过一个流动的值连接：`Session`。

---

## 一个极简但完整的 OpenRath Workflow

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

这个小程序在很短篇幅里展示了完整的形态：`Session` 承载数据，`Sandbox` 放置执行，`Tool` 注册到 `Agent`，`Memory` 跨运行持久化，`Workflow` 组合路径，`Compressor` 压缩最终上下文。

---

## 运行时组件

### Session — 流动的状态

`Session` 是 OpenRath 的中心运行时值。它持有一个有序 chunk 表，包含 system、user、assistant 和 tool-result 行。它还记录 sandbox placement、lineage、token usage 和待处理的延迟工作。

这就是 OpenRath 能够建模超过单一聊天会话的原因。Session 可以 fork 到新分支，从父链中 detach，与另一个兼容分支 merge，序列化为 JSONL，或交给不同的 workflow。Agent 侧的指令被表示为自己的 session chunks，由循环 prepend，而不是反复粘贴到不透明的 prompt 中。

常用入口：

- `Session.from_user_message(...)` 创建用户侧 Session。
- `Session.from_agent_prompt(...)` 创建 Agent/system prompt Session。
- `session.to("local", spec="./")` 绑定 sandbox 后端和工作区。
- `session.fork()` 创建可追踪分支。
- `session.detach()` 创建不带父谱系的新 Session。
- `session.merge(...)` 合并兼容分支并记录 merge 谱系。

### Sandbox — 工具落地之处

Sandbox 是 Session 的执行 placement。它类似于决定计算落在哪里的概念。工具不是在抽象 prompt 中运行；它们是在当前绑定到 Session 的 sandbox 中运行。

```python
session = Session.from_user_message("List files").to("local", spec="./")
```

`local` 后端始终可用，在宿主机工作区中运行文件、命令和代码工具。可选的 `opensandbox` 后端将同一 tool 层连接到容器化的 OpenSandbox runtime。返回的 Session 会保留活跃的 sandbox 所有权，因此后续工具调用继续从同一执行上下文进行，而不会静默漂移到一个不同的目录或机器。

### Memory — 跨运行留存的东西

Memory 是与 sandbox 执行平行持久平面。它不是 tool result，也不只是 prompt 文本；它是可以绑定到 Agent、在运行前 recall、在运行后 commit 的状态。

基础安装包含一个零依赖的本地 memory 后端。它将数据存储在 `.openrath/memory/` 下，无需 LLM 即可支持 lexical BM25 recall，并在配置了 embedding 提供程序时可以使用 embeddings。OpenViking 作为可选后端，为需要更丰富外部 memory 服务的用户提供。

```python
with flow.Agent("You remember useful facts.", model="gpt-5.5", memory="local") as agent:
    agent.remember_memory("The user works mostly in Python.")
    hits = agent.recall_memory("preferred programming language")
```

Agent memory API 有意设计得易于发现：

- `memory=` 在构造时绑定 store。
- `remember_memory(...)` 写入明确事实。
- `recall_memory(...)` 检索相关条目。
- `commit_memory(...)` 在运行后保存 transcript。
- `commit_on_forward=True` 可以自动 commit。

### Tool — 模型的可调用函数

`FlowToolCall` 是模型可见的工具抽象。它同时拥有工具的两面：展示给 LLM 的 name、description 和 JSON schema，以及针对 `Session` 执行的 Python call。

这使得 tool schema 和 tool 行为结合在一起。内置工具覆盖常见的文件系统、shell 和代码执行路径。自定义 Python 工具可以实现相同的接口，stdio MCP 工具也可以被适配为循环中的普通 `FlowToolCall` 实例。

重要的区分是：

- `FlowToolCall` 是模型可见的 flow 层函数。
- `BackendTool*` 是 sandbox 后端消费的更底层负载。

### Agent — 可复用的一层

`flow.Agent` 是大多数用户开始使用的小型可复用层。它更接近 `nn.Linear` 而不是完整应用：它有 prompt、provider、可选 tools、可选 memory，以及一条 `forward(session) -> session` 路径。

Agent 不拥有整个世界。Session 循环仍然是引擎，sandbox 仍然是 Session placement，memory 仍然是独立 store。这使单 Agent 场景保持简单，同时仍允许同一个 Agent 出现在更大的 workflows 中。

### Workflow — 无混乱地组合

`flow.Workflow` 是组合表面。子类实现：

```python
def forward(self, session: Session) -> Session:
    ...
```

Workflow 可以串联 agents、fork sessions、压缩上下文、调用 tools、分发到子 workflows，并返回新的 Session。因为输入和输出都是 `Session`，workflows 可以嵌套，而不需要在每一层发明新的 state 格式。

对于在运行时依赖于对话的路由，`flow.Selector` 是一个 LLM 驱动的路由器，面向自描述的 workflows（各自携带 `description`）。它返回下一个要运行的 workflow，或在任务完成时返回无操作的 `flow.EmptyWorkflow`——因此 `if` / `while` 保持为普通 Python：

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

可选的 sandbox 和 memory 集成：

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

大多数 LLM 示例使用 OpenAI 兼容的环境变量：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://your-gateway/v1
export OPENAI_DEFAULT_MODEL=your-model-name
```

你也可以在 `~/.openrath/config.json` 中配置 providers。环境变量优先级更高。

---

## 通过运行来学习

`example/` 目录是一个编号的学习阶梯。每个脚本引入一个概念，将样板代码保存在 `_shared/` 中，并展示核心对象如何组合在一起。

运行第一层：

```bash
python example/01_hello_agent.py
```

| # | 文件 | 概念 | 需要 key? |
| --- | --- | --- | :---: |
| 01 | [`01_hello_agent.py`](example/01_hello_agent.py) | 最小的 OpenRath 程序：构建 `flow.Agent`，在 `Session` 上调用，流式输出响应。 | 是 |
| 02 | [`02_session_lineage.py`](example/02_session_lineage.py) | 用 `fork` 分支 session，用 `detach` 切断谱系，检查 session graph，导出 JSONL。 | 否 |
| 03 | [`03_sandbox_backend.py`](example/03_sandbox_backend.py) | 将同一个 session 放到 `local` 或 `opensandbox`，观察工具在哪里执行。 | 是 |
| 04 | [`04_tools_builtin.py`](example/04_tools_builtin.py) | 使用每个循环可以暴露的内置文件系统和 shell 工具。 | 是 |
| 05 | [`05_custom_tool.py`](example/05_custom_tool.py) | 实现带 JSON schema 和 Python 运行时行为的自定义 `FlowToolCall`。 | 是 |
| 06 | [`06_mcp_tool.py`](example/06_mcp_tool.py) | 包装一个微型 stdio MCP server，无需编写新 tool 类即可借用其工具。 | 否 |
| 07 | [`07_streaming.py`](example/07_streaming.py) | 接收流式 delta，并在运行后检查累积 token 使用情况。 | 是 |
| 08 | [`08_compress.py`](example/08_compress.py) | 使用 `flow.Compressor` 将长 session 缩减为更小的上下文 session。 | 是 |
| 09 | [`09_memory.py`](example/09_memory.py) | 使用本地 memory 后端进行 remember、recall，并可选地 commit 一个真实回合。 | 否 |
| 10 | [`10_provider_variation.py`](example/10_provider_variation.py) | 通过更改 `Provider` 切换模型厂商，同时保持 Session 和 Workflow 代码稳定。 | 是 |
| 11 | [`11_dynamic_selector.py`](example/11_dynamic_selector.py) | 使用 `flow.Selector` 在自描述的 workflows 之间路由：`if` 分支和一个在 `flow.EmptyWorkflow` 时结束的 `while` 循环。 | 是 |
| 12 | [`12_compile.py`](example/12_compile.py) | 静态 `compile()` 一个 workflow：查看其资源清单、离线 `validate()`、并使用生命周期上下文管理器。 | 否 |

阅读 [`example/README.md`](example/README.md) 获取设置细节和共享 helpers。

---

## 文档与链接

- 文档：[https://docs.openrath.com](https://docs.openrath.com)
- 仓库：[https://github.com/Rath-Team/OpenRath](https://github.com/Rath-Team/OpenRath)
- 问题：[https://github.com/Rath-Team/OpenRath/issues](https://github.com/Rath-Team/OpenRath/issues)

本地构建文档：

```bash
uv run sphinx-build -M html docs/source docs/_build
```

---

## License

OpenRath 使用 BSD 风格许可证。详见 [LICENSE](LICENSE)。
