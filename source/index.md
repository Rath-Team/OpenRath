(openrath-documentation)=
# OpenRath

<div class="or-home-hero">
  <h2>面向大模型智能体工作流的 PyTorch 式运行时</h2>
  <p>OpenRath 把 PyTorch 式的组合性带到智能体工作流：用 Session 管理状态，用 FlowToolCall 暴露工具能力，用 Backend 控制执行位置。</p>
  <p class="or-cta">
    <a class="or-button or-button-primary" href="tutorial/index.html">开始教程</a>
    <a class="or-button" href="developer_notes/index.html">阅读 Developer Notes</a>
    <a class="or-button or-button-muted" href="https://github.com/Rath-Team/OpenRath">GitHub</a>
  </p>
</div>

```python
from rath import flow
from rath.session import Session

agent = flow.Agent(
    system_prompt="需要时使用工具。",
    model="gpt-5.5",
)

user = Session.from_user_message(
    "创建一个文件，然后读回来。"
).to("local")

out = agent(user)
```

教程使用 scripted LLM response 保证运行过程可复现。真实智能体工作流使用同一组 `Session`、`FlowToolCall`、`Workflow` 和 `Backend` 抽象，换成已配置的模型 provider 即可运行。

## 从哪里开始

| 路径 | 适合做什么 | 入口 |
| --- | --- | --- |
| Installation | 安装 OpenRath，配置模型凭证，并按需连接 sandbox backend。 | [Installation](install.md) |
| Tutorials | 从可运行代码开始学习，再改写示例，包括多智能体工作流。 | [Tutorials](tutorial/index.md) |
| Developer Notes | 理解核心运行时组件、调用边界和源码对应关系。 | [Developer Notes](developer_notes/index.md) |
| API Reference | 查询公开模块、函数签名和集成点。 | [API Reference](reference/index.md) |

## 核心模型

| 概念 | 作用 |
| --- | --- |
| `Session` | 承载对话表、backend placement 和 lineage metadata。 |
| `FlowToolCall` | 向模型暴露 JSON schema，向运行时暴露 Python callable。 |
| `Backend` | 打开 sandbox，并执行 command、file、code payload。 |
| `Workflow` | 用普通 Python module 组合智能体和 session transformation。 |
| `Provider` | 保存 OpenAI-compatible chat completion 使用的模型和请求参数。 |

## 可运行工作流

| 示例 | 展示内容 |
| --- | --- |
| [Trading Agents](tutorial/examples/trading_agents.md) | 顺序研究工作流：analyst、bear/bull researchers、trader、risk/PM。 |
| [Engineering Agents](tutorial/examples/engineering_agents.md) | 嵌套工程工作流：lead、feature squad、backend pair、frontend、QA。 |

## PyTorch 心智模型

| PyTorch 心智模型 | OpenRath 对应 |
| --- | --- |
| Tensor 承载数据 | `Session` 承载智能体状态 |
| Module 组合计算 | `Workflow` / `Agent` 组合行为 |
| device 控制放置位置 | `Backend` 控制执行位置 |
| callable module 暴露可复用接口 | `FlowToolCall` 暴露工具 |

```{toctree}
---
maxdepth: 3
caption: OpenRath
hidden:
---

Installation <install>
Tutorials <tutorial/index>
Developer Notes <developer_notes/index>
API Reference <reference/index>
```
