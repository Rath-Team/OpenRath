# OpenRath Site 展示决策记录

> 目标：在正式开发网页之前，先确定 OpenRath 站点的内容策略、展示重点、页面结构、视觉取向和可信度表达。本文用于记录讨论过程、备选方案、当前倾向和最终决策。

## 当前原则

- 先讨论，不急着开发页面。
- 站点内容必须基于当前真实代码能力，不夸大尚未完成的功能。
- 不堆 Mermaid 图；优先使用清晰文字、表格、代码片段、真实 tutorial 截图和运行日志。
- 对标 PyTorch 这类成熟开源项目：清楚的学习路径、教程入口、API 入口、版本感、可信工程气质。
- 展示页可以更产品化，但不能变成空泛营销页。
- 第一版 site 不依赖定制插图。先用文字、代码块、表格、真实 tutorial 链接和日志链接把信息架构跑通；图片作为下一阶段视觉增强内容。
- 站点文案采用正向定义式表达。优先写“OpenRath 是什么、提供什么、适用于什么场景”，少用否定式对比。必要的边界说明放在“当前边界 / 适用范围 / 暂不承诺”中，用事实列出。

## 决策记录格式

后续每个关键决策都要尽量记录到可以直接支撑 site 写作的程度，而不只是记录“选了哪个选项”。每个决策至少包含：

- 最终结论：我们选择什么。
- 决策理由：为什么这个选择适合 OpenRath 当前阶段。
- 内容影响：它会如何影响首页、教程页、用户指南、API 入口和导航。
- 可直接使用的文案：标题、副标题、短句、说明句、warning 或边界说明。
- 不要做什么：避免哪些误导、夸大、错误气质或无效表达。
- 相关资产：图片、截图、日志、代码片段或后续需要制作的素材。

这些记录会作为后续开发 site 的内容源。网页实现阶段应优先复用本文已经确认的表述，不临时重新发明叙事。

## 决策总览

| ID | 决策点 | 当前倾向 | 状态 |
| --- | --- | --- | --- |
| D01 | 站点首要受众 | 工程师优先，面向广泛 Python/LLM agent 用户 | 已决策 |
| D02 | 首页一句话定位 | PyTorch-inspired runtime for LLM agent workflows | 已决策 |
| D03 | 是否突出 PyTorch 类比 | 作为核心传播 hook，但不做唯一叙事 | 已决策 |
| D04 | 首屏主 CTA | Start with Tutorials / Developer Notes / GitHub | 已决策，已修订 |
| D05 | 首页第一屏是否放代码 | 放短 Python API 片段，不放完整输出 | 已决策 |
| D06 | 首页是否展示 tutorial 截图 | 不作为首页主体；代码优先，保持干净 | 已决策 |
| D07 | 文档入口分层 | Install / Tutorials / Developer Notes / API Reference | 已决策，已修订 |
| D08 | Showcase 是否公开 | 保留为内部素材库，不进入正式 site | 已决策 |
| D09 | Sandbox 的表达方式 | 分层表达 backend/sandbox，不夸大 local 安全性 | 已决策 |
| D10 | 工具系统怎么讲 | FlowToolCall schema + Backend execution + Session 记录 | 已决策 |
| D11 | Session 怎么讲 | chunk transcript + sandbox placement + lineage carrier | 已决策 |
| D12 | LLM provider 怎么讲 | OpenAI-compatible default client + replaceable SessionLoopExecutor | 已决策 |
| D13 | 示例路径 | Tutorials 页面统一承载 tutorials + examples | 已决策 |
| D14 | 可信度证据 | 源码/API/确定性教程为主，测试说明为辅 | 已决策 |
| D15 | 视觉风格 | 工程文档站为主体，保留克制的精致感 | 已决策 |
| D16 | 是否做交互 demo | 第一版不做复杂交互，先静态 HTML | 待决策 |
| D17 | 导航结构 | 顶部导航使用 Installation / Tutorials / Developer Notes / API Reference | 已决策，已修订 |
| D18 | 语言策略 | 正式站点正文中文优先，导航和少数固定入口可用英文 | 已决策，已修订 |
| D19 | 未完成功能如何呈现 | Roadmap/Experimental 明确标注 | 待决策 |
| D20 | 首页最终目标 | 让新读者 3 分钟理解并愿意跑 tutorial | 待决策 |

## 关键决策点

### D01. 站点首要受众

备选：

- A. Python/LLM agent 框架开发者。
- B. 研究者与论文读者。
- C. 投资人/路演观众。
- D. 内部团队协作成员。

最终决策：A 为主。OpenRath site 的第一受众是 Python / LLM Agent 工程师，因为这个 repo 的目标是成为一个可用、可信、易上手的开源仓库，而不是学术工具或纯展示页。

补充原则：工程师优先不等于只面向专家。文档需要足够清楚、门槛足够低，让更广泛的用户能够理解 OpenRath 是什么、如何安装、如何跑通 tutorial、如何基于它开发自己的 agent workflow。

决策理由：

- OpenRath 当前最强的证据是实际代码、API、测试、tutorial、截图和日志，而不是论文结果或商业 demo。
- 开源仓库的第一目标是降低试用成本，让开发者快速判断“这个抽象是否值得我依赖”。
- 面向工程师可以自然承接 PyTorch-inspired 的叙事，因为 PyTorch 本身就是工程师熟悉的抽象体系。
- 低门槛不意味着弱技术表达。相反，文档要把复杂运行时拆清楚，让新用户和高级用户都能找到入口。

首页内容影响：

- 首屏必须在 5 秒内回答：OpenRath 是什么、为什么值得看、下一步点哪里。
- 首页应优先展示代码、tutorial、运行截图、API 入口，而不是长篇愿景。
- 首屏文案不能假设用户已经知道 `Session`、`Backend` 或 `FlowToolCall`，必须有一层短解释。
- 首页不要写成“AI agent 革命”这类泛化表达，要回到具体工程抽象。

文档结构影响：

- 第一层导航应包含 `Tutorials`、`Developer Notes`、`API Reference`，其中可运行 examples 归入 `Tutorials`。
- `Tutorials` 要面向第一次使用者，尽量 deterministic，不依赖真实 LLM key。
- `Developer Notes` 负责讲核心组件、运行模型和设计边界。
- `API Reference` 负责让已经开始集成的人能快速查接口。

可直接使用的文案：

> Built for engineers who want explicit state, tools, and execution boundaries in LLM agent workflows.

> Start from a deterministic tutorial, then move into real LLM-backed workflows when you are ready.

> OpenRath is designed as an open-source Python framework first: readable abstractions, reproducible examples, and inspectable runtime behavior.

不要做什么：

- 不把站点写成学术项目主页。
- 不把首页写成融资或路演材料。
- 不使用只有内部团队才懂的项目进度语言。
- 不为了显得高级而隐藏安装、运行、示例和 API。

次级受众处理：

- 研究者可以通过设计概览理解抽象，但不主导首页。
- 投资人或非技术读者可以通过首屏和架构图理解方向，但不牺牲工程准确性。
- 内部团队资料可以放在单独文档中，不进入正式站点主导航。

### D02. 首页一句话定位

备选：

- A. OpenRath is a Session-centered Python framework for building agent workflows.
- B. OpenRath brings PyTorch-like runtime structure to LLM agents.
- C. OpenRath separates agent state, tools, sandbox execution, and LLM requests.

最终决策：选择 PyTorch-inspired 方向作为首页第一定位，但文案要组织得更清楚，避免读者误以为 OpenRath 是 PyTorch 插件、深度学习训练框架或 tensor/autograd 相关项目。

推荐主标题：

> A PyTorch-inspired runtime for LLM agent workflows.

推荐副标题：

> OpenRath brings PyTorch-style composability to agents: explicit sessions for state, tools as callable interfaces, and backends for sandboxed execution.

中文含义：

> OpenRath 借鉴 PyTorch 的抽象方式，为 LLM agent workflow 提供清晰的运行时结构：`Session` 承载状态，工具暴露可调用接口，`Backend` 负责执行位置与副作用。

决策理由：

- “Session-centered Python framework”准确，但传播记忆点不够强。
- “PyTorch-inspired runtime”能让工程师立刻建立心智模型：显式对象、组合、可调用接口、执行位置。
- OpenRath 的代码结构确实有类似 PyTorch 的表达方式：`Session` 类似状态载体，`Workflow` / `Agent` 类似可组合模块，`Backend` 类似 placement，`FlowToolCall` 类似可调用接口。
- 这个定位能兼顾高级感和工程准确性，但必须加边界说明。

首页内容影响：

- 主标题可以直接使用英文，形成开源项目气质。
- 副标题解释 OpenRath 自己的抽象，不能只停留在“像 PyTorch”。
- 首屏附近需要出现一个非常短的边界说明，避免误解：

> Not a PyTorch extension. No tensors, autograd, or model training. OpenRath applies the composable runtime mindset to LLM agents.

可直接使用的首屏文案组合：

主标题：

> A PyTorch-inspired runtime for LLM agent workflows.

副标题：

> OpenRath brings PyTorch-style composability to agents: explicit sessions for state, tools as callable interfaces, and backends for sandboxed execution.

短解释：

> Think less prompt glue, more explicit runtime objects.

中文站点说明：

> OpenRath 借鉴 PyTorch 的工程抽象，但服务的是 LLM agent workflow，而不是模型训练。它把状态、工具、执行位置和 LLM 请求拆成可以组合、可以检查、可以测试的 Python 对象。

不要做什么：

- 不写成 “OpenRath is PyTorch for agents” 作为唯一标题，这句话有传播力但容易过度简化。
- 不让读者误以为项目依赖 PyTorch。
- 不使用 tensor/autograd/training 相关视觉元素作为主视觉。
- 不用类比替代真实 API 说明。

后续页面影响：

- 首页讲定位。
- 第二屏讲映射表。
- Developer Notes 讲边界和真实运行路径。
- Tutorials 完全回到代码和截图。

### D03. PyTorch 类比的使用程度

备选：

- A. 首页强绑定 PyTorch 类比。
- B. 用户指南中使用类比，首页只轻轻提。
- C. 完全不使用类比。

最终决策：PyTorch 类比作为核心传播 hook，但不是整站唯一叙事。

宣传表达：

> PyTorch made model building composable. OpenRath brings that style of composability to LLM agent workflows.

展示方式：

- 首页首屏可以强打 `A PyTorch-inspired runtime for LLM agent workflows.`
- 第二屏用简洁映射解释抽象来源：`Tensor -> Session`、`Module -> Workflow / Agent`、`device -> Backend`、`callable modules -> FlowToolCall`。
- 教程和 API 页面不反复讲类比，而是回到真实代码：`Session -> Tool Call -> Backend -> Result Chunk`。
- 必须写清楚边界：OpenRath 不是 PyTorch extension，不做 tensor、autograd 或 training。

映射表内容：

| PyTorch 心智模型 | OpenRath 对应 | 站点解释 |
| --- | --- | --- |
| Tensor carries data | Session carries agent state | `Session` 保存对话 chunk、sandbox placement 和 lineage。 |
| Module composes computation | Workflow / Agent composes behavior | `Workflow` / `Agent` 组织 agent 行为和参数。 |
| device controls placement | Backend controls execution | `Backend` 决定工具和副作用在哪里执行。 |
| callable modules expose reusable interfaces | FlowToolCall exposes tool | `FlowToolCall` 把 schema 和 Python 执行逻辑绑定为模型可见工具。 |

内容节奏：

- 首页第一屏：只说定位和 CTA。
- 首页第二屏：放 PyTorch / OpenRath 对比图，帮助工程师建立直觉。
- 首页第三屏：展示真实 tutorial 截图，证明这个抽象已经跑起来。
- 后续文档：少讲比喻，多讲真实 API、执行路径、边界条件和示例。

可直接使用的文案：

> PyTorch gave engineers a composable way to think about model computation. OpenRath adapts that mental model to agent runtime design.

> Sessions carry state. Workflows compose behavior. Backends control execution. Tools expose callable capabilities.

> The analogy is a starting point, not the API contract. The tutorials show the actual runtime path.

不要做什么：

- 不在每个页面都重复 PyTorch 类比，避免显得单薄。
- 不把 PyTorch logo 或品牌视觉作为主视觉中心。
- 不制造“完全等价”的映射。类比是帮助理解，不是语义等价。
- 不用复杂大图解释所有模块，保持极简、清晰、可扫描。

配套资产：

- PyTorch / OpenRath 对比图：`docs/source/_static/site/pytorch-openrath-comparison.png`
- 视觉参考：Anthropic Research blog 图形风格，例如 `Teaching Claude why` 与 `Natural Language Autoencoders`。采用暖白背景、黑色主文字、细线箭头、浅黄色强调、轻量虚线/边框、研究解释图气质。避免 glossy icon、厚卡片阴影、强渐变和过度产品化装饰。

后续绘图要求：

- 使用 image2 生成 bitmap 资产，不使用 SVG 手工绘制。
- 图像风格应更接近研究博客中的 explanatory figure，而不是 SaaS landing page 插画。
- 文字必须少、清楚、可扫描；如果 image2 文字不稳定，后续应减少图中文字量，把精确文字放回 HTML/CSS。

### D04. 首屏 CTA

备选：

- A. Get Started。
- B. View Tutorials。
- C. API Reference。
- D. GitHub。

最终决策：首页首屏使用三个 CTA。

2026-05-11 修订：由于 `Examples` 合并进入 `Tutorials`，并新增 `Developer Notes` 作为核心组件说明入口，第二个 CTA 使用明确的 `Developer Notes`。

```text
[Start with Tutorials] [Developer Notes] [GitHub]
```

CTA 层级：

| 层级 | 文案 | 目标页面 | 目标用户 |
| --- | --- | --- | --- |
| Primary | Start with Tutorials | `tutorial/index.html` | 第一次接触 OpenRath、想快速跑通的人。 |
| Secondary | Developer Notes | `developer_notes/index.html` | 想理解核心组件、架构和模块边界的人。 |
| Secondary | GitHub | GitHub repository | 想看源码、star、fork、提 issue 的开源用户。 |

决策理由：

- OpenRath 当前最能建立信任的内容是 deterministic tutorials、运行日志和真实代码路径。
- 对新用户来说，先跑通一个 tutorial 比先读完整架构更容易形成信任。
- `Start with Tutorials` 比 `Get Started` 更具体，降低点击前的不确定性。
- `Developer Notes` 明确指向核心组件说明，比泛化的 docs 入口更适合当前信息架构。
- `GitHub` 必须在首屏可见，因为 OpenRath 的定位是开源仓库，但不能作为唯一主 CTA。

首页内容影响：

- 首屏应围绕主标题、副标题、短边界说明和三个 CTA 组织。
- CTA 顺序固定为：Tutorials -> Developer Notes -> GitHub。
- 三个按钮视觉层级不同：Tutorials 最强，Developer Notes 次强，GitHub 更克制但清晰。
- 首屏不需要塞太多导航解释，CTA 下面可以用一行短说明补充：

> New to OpenRath? Start with a deterministic tutorial that runs without a real LLM key.

可直接使用的按钮文案：

```text
Start with Tutorials
Developer Notes
GitHub
```

可直接使用的辅助文案：

> Tutorials are the fastest path: run a scripted session loop, inspect tool calls, and see how Session, Tool, and Backend fit together.

不要做什么：

- 不把 GitHub 作为唯一首屏 CTA，避免用户还没理解项目就跳走。
- 不使用泛泛的 `Learn More` 作为主按钮。
- 不把 API Reference 放在首屏主按钮位置；它适合已经理解项目的人。
- 不在第一版做复杂 interactive demo 替代 CTA。

### D05. 首页是否放代码片段

备选：

- A. 放极短代码。
- B. 放完整 tutorial 链接，不放代码。
- C. 放终端截图。

最终决策：首页首屏放一个短 Python API 片段，用来展示 OpenRath 的工程使用感；不在首屏放完整运行输出、长日志或复杂 terminal 截图。完整输出、日志和分步证据放在 Tutorials 页面。

推荐代码片段：

```python
from rath import flow
from rath.session import Session

agent = flow.Agent(
    system_prompt="Use tools when helpful.",
    model="gpt-5.5",
)

user = Session.from_user_message(
    "Create a file, then read it back."
).to("local")

out = agent(user)
```

配套说明：

> The tutorials use scripted LLM responses for deterministic runs; real agents use the same Session and Tool abstractions with your configured model provider.

决策理由：

- 工程师进入开源项目首页时，通常会先看 API 是否自然、抽象是否清楚。
- 短代码片段能快速展示 OpenRath 的核心心智模型：`Agent`、`Session`、`.to("local")`、agent invocation。
- 不展示完整 `run_session_loop` 是为了避免首屏过重；细节应该交给 tutorial 和 user guide。
- 不用 terminal 输出作为首屏主体，因为输出能证明运行过，但不如代码直接表达框架 API。
- 代码必须基于真实 API，不能写伪代码；但需要用说明澄清真实 agent 运行需要 LLM 配置。

首页内容影响：

- 首屏布局可以采用左侧定位 + CTA，右侧短代码块。
- 代码块只展示 API 形态，不承担完整教程职责。
- 代码块下方或附近需要有一行 deterministic tutorial 说明，引导用户去 `Start with Tutorials`。
- 第一版 site 不需要首屏图片；代码块就是首屏主要视觉资产。

可直接使用的代码块标题：

```text
Minimal agent workflow
```

可直接使用的辅助文案：

> Same runtime objects, two ways to learn: start with scripted tutorials, then connect a real model provider.

不要做什么：

- 不在首屏放超过 20 行代码。
- 不把需要大量环境变量、真实模型调用和完整工具循环的代码放在首屏。
- 不写伪 API。
- 不在首屏混合代码、长日志、截图和复杂图表，避免信息拥挤。

### D06. 是否展示真实 tutorial 截图

备选：

- A. 首页直接展示 2-3 张。
- B. Tutorials 页展示，首页只引用。
- C. 不展示截图，只展示代码。

最终决策：首页不把 tutorial 截图作为主体内容。第一版 site 采用更干净的 code-first 展示方式：用短代码片段说明 API 和使用路径，不在首页堆截图，也不放具体日志链接。截图和日志可以保留在 tutorial 详情页或后续视觉增强阶段。

决策理由：

- OpenRath 的目标是开源工程仓库，首页应该先让用户看到 API 和抽象，而不是像 demo 页面一样展示运行截图。
- Transformer Engine 等成熟工程文档更强调库的定位、代码用法、Examples 和 API，而不是在首页放日志或截图。
- 日志链接对复现有价值，但不是首页第一版必须承担的内容；过早放日志会让页面显得杂。
- 干净的首页能更好承载 PyTorch-inspired 定位、三个 CTA 和短代码块。

首页内容影响：

- 首页主体使用短代码块、简洁说明、文档入口卡片。
- 不放 tutorial screenshot carousel。
- 不放逐步日志链接。
- 如果需要证明可运行性，只用一句简短说明即可，例如：

> Tutorials use deterministic scripted runs so new users can inspect the runtime path without a model key.

可直接使用的 section 标题：

```text
Code-first tutorials
```

可直接使用的辅助文案：

> Learn the runtime by reading and running small Python examples, not by watching a demo.

> Start with clean API examples; deeper tutorial pages can include generated artifacts when needed.

不要做什么：

- 不在首页放大段 terminal output。
- 不在首页展示日志链接表格。
- 不使用截图堆叠来证明项目可用。
- 不做截图轮播或复杂视觉 demo 作为第一版首页主体。

后续阶段：

- Tutorial 详情页可以保留截图和日志作为可追溯材料。
- Site 视觉增强阶段可以重新设计少量解释图，但不阻塞第一版 site。

### D07. 文档入口分层

备选：

- A. Tutorials / Developer Notes / API Reference。
- B. Getting Started / Concepts / API / Roadmap。
- C. Learn / Build / Reference / Internals。

最终决策：采用 A 的工程文档分层，并补上 `Install` 作为明确入口。

2026-05-11 修订：`Examples` 与 `Tutorials` 合并为一个学习入口；新增 `Developer Notes` 作为核心组件深度说明入口。正式 site 顶层文档入口为：

```text
Install
Tutorials
Developer Notes
API Reference
```

首页展示层可以按用户任务重新组织为：

```text
Start
- Install
- Tutorials

Understand
- Developer Notes
- Core Components

Build
- Tools
- Backends
- Workflows

Reference
- API Reference
```

决策理由：

- 这个结构最接近成熟开源项目的文档心智模型，用户不需要学习新的导航命名。
- `Install` 独立出来能降低第一次使用门槛，尤其是 OpenRath 涉及 LLM 环境变量和可选 sandbox backend。
- `Tutorials` 是新用户的主路径，同时承载可运行 tutorial 和可改写 example，减少入口数量。
- `Developer Notes` 承担核心组件说明，按 `session / sandbox / tool / agent param / workflow / llm` 组织。
- `API Reference` 服务查接口，保持比 Developer Notes 更机械、更接近源码导出。

首页内容影响：

- 首页可以出现一个 “Choose your path” 或 “Where to start” 区块。
- 卡片不直接照搬目录，而是按用户任务组织，让入口更友好。
- 每张卡片只放一两句说明，避免像 sitemap。
- `Showcase` 不作为正式导航入口。

可直接使用的导航文案：

```text
Install
Tutorials
Developer Notes
API Reference
GitHub
```

可直接使用的首页卡片文案：

```text
Start
Install OpenRath and run tutorials without needing a model key.

Understand
Read Developer Notes for the core components behind sessions, sandboxes, tools, workflows, and LLM calls.

Build
Start from runnable examples inside Tutorials, then adapt the code for your own workflow.

Reference
Look up exported modules, important signatures, and integration points.
```

不要做什么：

- 不使用过度产品化的 `Learn / Build / Scale` 命名替代清晰文档入口。
- 不把 `Showcase` 放入正式导航。
- 不再把 Examples 做成独立顶层入口；Examples 作为 Tutorials 页面中的可运行代码路径。
- 不隐藏 Install；安装和环境变量是开源项目第一门槛。

Developer Notes 组件大纲：

| 组件 | 需要讲清楚的内容 |
| --- | --- |
| `session` | `Session` 是上下文，通过表的形式组织 chunk；`Session` 在不同 agent 之间流动，OpenRath 维护 session graph；详细说明 `create`、`fork`、`detach`、`loop`、`compress` 五个原语及其 graph 行为；`Session` 与 sandbox 的生命周期关系指向 sandbox 章。 |
| `sandbox` | sandbox 以 backend 抽象注册，目前包含 `local` 和可选 `opensandbox`；说明 session 与 sandbox 的绑定和生命周期；说明 local backend 的工作目录实现；说明 OpenSandbox backend 的工作目录/文件传递实现。 |
| `tool` | tool call 在 loop 中形成 assistant/tool result chunk，并由 `run_session_loop` 产生新的 session lineage；backend stream 支持同 stream FIFO、不同 stream 并发；用户可以继承 `FlowToolCall` 自定义 tool；session loop 接收实例化后的 `FlowToolCall` 列表，让 agent 获得对应工具 schema。 |
| `agent param` | `AgentParam` 维护 system prompt、provider 等 agent 配置；agent session 保存 system prompt；session loop 会把 user session 与 agent session 拼成 request messages；loop 结束返回以 user-side rows 为主体的输出 session。 |
| `workflow` | `Workflow` 是高级组件，以模块化方式组织 agent 工作流；用户可以实现、嵌套、拼接或扩展 workflow；OpenRath 通过 session graph、sandbox binding 和 tool result chunks 维护运行记录；预设子类包含 `Agent` 与 `SessionCompressor`。 |
| `llm` | LLM 组件负责构造 chat request、发起 LLM API 请求、解析响应字段，并把 provider 参数合并到 request。 |

实现核对点：

- tool graph 表达需要按当前代码写成：tool call/result 记录在 chunk table，`run_session_loop` 作为 session graph operation 记录 lineage。
- `run_session_compress` 当前是压缩路径，默认 tool choice 为 `none`；Developer Notes 中把 compress 作为 session graph 原语讲。
- backend stream 的 FIFO 与并发语义已有 `tests/conformance/test_stream_event.py` 覆盖，可作为 Developer Notes 的实现依据。

后续实现要求：

- `docs/source/index.md` 的主入口表格要与这个分层一致。
- 如果开发独立 site 首页，也应复用这套导航和首页卡片结构。
- `Showcase` 可保留在仓库，但正式站点第一版不把它放到主导航中。

### D08. Showcase 是否公开

备选：

- A. 公开，作为主导航。
- B. 公开但弱化。
- C. 内部保留，不进正式站点导航。

最终决策：选择 C。`docs/source/showcase/` 保留在仓库中，作为内部 site 文案素材库和展示叙事草稿；但它不进入正式 site 的主导航，不作为普通用户的阅读入口。

Showcase 当前内容：

| 文件 | 内容角色 | 后续用途 |
| --- | --- | --- |
| `one_page_pitch.md` | 一页纸介绍、最小代码、当前能力、demo 候选。 | 可提炼成首页 hero、副标题、项目简介。 |
| `architecture_story.md` | 解释 Session、FlowToolCall、Backend、Workflow 为什么这样拆。 | 可提炼成 Developer Notes 前言或首页架构区。 |
| `pytorch_analogy.md` | PyTorch 类比表、推荐话术、不该怎么讲。 | 可用于首页第二屏和定位说明。 |
| `session_lifecycle.md` | 创建、绑定 backend、进入 loop、工具结果 chunk、派生/压缩。 | 可用于 Tutorials 或 Developer Notes 中的 Session 页面。 |
| `tools_sandbox_story.md` | 工具调用与 sandbox 执行边界，含风险提醒。 | 可用于 Tools/Backend 说明和安全边界文案。 |
| `developer_quickstart.md` | 安装、写 agent、创建 session、运行、加工具。 | 可迁移为正式 Quickstart 或 Tutorials 内容。 |
| `website_homepage_draft.md` | Hero、卖点、架构区、CTA 的早期草案。 | 作为 site 首页开发参考，不直接发布。 |
| `docs_strategy.md` | 首页、用户指南、API 参考、展示材料的职责划分。 | 内部文档策略参考。 |

决策理由：

- Showcase 里有“候选”“草案”“策略”等内部语气，直接公开会降低正式文档成熟度。
- 这些内容对我们开发 site 很有价值，因为它们保存了不同讲法和可复用文案。
- 正式文档入口应保持稳定、清晰、用户任务导向；showcase 的用途是辅助创作，不是服务最终读者。
- 保留它可以避免丢失之前沉淀的表达，但隐藏它可以避免用户误读项目还停留在草稿阶段。

首页内容影响：

- 正式首页不出现 `Showcase` 导航项。
- 首页文案可以吸收 showcase 中的优质表达，但要改写成最终态。
- 若后续需要“About / Design Philosophy”页面，也应从 showcase 抽取并重新编辑，不直接链接原文。

文档结构影响：

- `docs/source/showcase/` 可以留在源码树中。
- Sphinx 正式导航第一版不应包含 showcase。
- 如果需要构建内部版本，可通过单独入口或隐藏页面访问，但不放主导航。

可直接使用的内部说明：

> Showcase files are internal narrative drafts. Use them as source material for the public site, but do not expose them as primary documentation pages.

不要做什么：

- 不把 `website_homepage_draft.md` 直接发布为首页。
- 不让外部用户看到“候选文案”“草案”这种未收敛内容。
- 不把 showcase 当作 Tutorials 或 Developer Notes 的替代品。
- 不删除 showcase，因为它是后续 site 写作素材库。

后续处理建议：

- 开发 site 前，从 showcase 提取可复用短句，写入正式首页。
- `developer_quickstart.md` 中有用内容可迁移到正式 `Tutorials` 或 `Quickstart`。
- `pytorch_analogy.md` 应与 D02/D03 的最终决策合并，避免多个版本的类比话术互相冲突。

### D09. Sandbox 的表达方式

备选：

- A. 强调安全隔离。
- B. 强调执行位置与生命周期。
- C. 弱化 sandbox，只讲 tools。

最终决策：采用分层表达。OpenRath 要强调 backend/sandbox 是工具副作用发生的位置与执行边界。当前默认 `local` backend 表达为本地执行位置，不表达为强安全隔离。项目长期可以参考 OpenSandbox 和 Anthropic sandbox 这类执行环境设计；OpenRath 在 agent runtime 中提供清晰、可替换、可演进的执行 backend 抽象。

分层表达：

| 层级 | 表达重点 | 站点写法 |
| --- | --- | --- |
| 抽象层 | `Backend` 决定工具在哪里执行。 | A Session can bind to a backend so tools know where side effects happen. |
| 默认层 | `local` backend 适合开发、测试和可信负载。 | Start with local subprocess execution for development. |
| 可选层 | `opensandbox` extra 代表更强 sandbox/service backend 的方向。 | Move to stronger sandbox backends when your workflow needs isolation. |
| 长期方向 | 借鉴 OpenSandbox / Anthropic sandbox 的执行环境思路。 | The backend abstraction leaves room for stricter execution environments. |

决策理由：

- `sandbox` 是 OpenRath 的重要差异点，不能弱化成普通 tool calling。
- 但当前 `LocalBackend` 真实行为是 host-side subprocess + filesystem workspace，不是安全容器。
- 准确的分层表达可以同时保持工程可信度和长期想象空间。
- 站点应该让用户理解“执行位置是显式的”，而不是承诺“默认安全运行任意代码”。

首页内容影响：

- 首页可以使用 `sandboxed execution`，但必须配合更准确的解释，例如 `execution backends`。
- 首页不写 “securely run arbitrary code”。
- 首屏副标题中的 `backends for sandboxed execution` 可以保留，但后续 section 需要解释 local 与 stronger sandbox backend 的区别。

可直接使用的首页文案：

> Execution is explicit. Bind sessions to backends so tools know where side effects happen.

> Start local for development, then move to stronger sandbox backends when your workflow needs stricter isolation.

> OpenRath does not try to replace Docker. It gives agent workflows a backend abstraction for local, sandboxed, and future execution environments.

Developer Notes / Sandbox 页面 warning 文案：

> LocalBackend is for development and trusted workloads. It runs subprocesses on the host and removes its managed working directory on close.

不要做什么：

- 不宣传 `local` backend 是强安全隔离。
- 不写 “run arbitrary untrusted code safely”。
- 不把 OpenRath 定位成 Docker 替代品。
- 不把 OpenSandbox 描述成核心默认能力；它是 optional extra/backend direction。

后续实现要求：

- 首页使用 `execution backend` 作为更准确的主词，`sandbox` 作为具体 backend 能力。
- Backend 文档必须明确 local 的行为和风险。
- OpenSandbox 页面可以作为 optional backend，而不是默认路径。
- 如果后续 site 有 architecture section，应把 `Session -> Tool -> Backend` 的执行边界讲清楚。

### D10. 工具系统怎么讲

备选：

- A. 从 LLM function calling 讲。
- B. 从 `FlowToolCall` + `BackendTool` 分层讲。
- C. 从用户自定义工具讲。

最终决策：采用 B。OpenRath 的工具系统讲成三层：`FlowToolCall` 提供模型可见的结构化工具接口，`BackendTool*` payload 表达后端侧副作用请求，Session loop 记录 assistant tool call 与 `tool_result` chunk。

核心表达：

> Tools are structured runtime interfaces. A `FlowToolCall` exposes a JSON schema to the model and a Python callable to OpenRath. Backend-facing tools route side effects through the active backend, and the session loop records the call and result as inspectable chunks.

中文站点说明：

> OpenRath 的工具系统是结构化 runtime 接口。`FlowToolCall` 负责向模型暴露工具名称、描述和参数 schema，同时把调用交给 Python runtime。涉及 shell、文件写入和代码执行的工具会通过当前 `Backend` 执行，工具调用和工具结果都会进入 `Session`。

分层说明：

| 层级 | 对应代码概念 | 站点解释 |
| --- | --- | --- |
| 模型接口 | `FlowToolCall` | 暴露 `name`、`description`、`parameters`，让模型获得可调用工具 schema。 |
| 执行逻辑 | `__call__(session, arguments)` | runtime 调用 Python 工具对象，并传入当前 `Session`。 |
| 后端副作用 | `BackendToolCommandRun`、`BackendToolFilesWrite` 等 | 把 shell、文件、代码执行等请求交给 active backend。 |
| 记录结果 | `tool_result` chunk | Session loop 保存工具调用结果，方便检查、继续和调试。 |

内容影响：

- 首页可以使用一句短表达：`Structured tools with explicit execution.`
- Developer Notes 需要有一节解释 `FlowToolCall`、built-in tools、custom tools 和 backend-facing tools 的关系。
- Tutorial 应展示一个最小 custom tool，并展示 built-in shell/file 工具如何通过 backend 执行。
- API Reference 需要把 `FlowToolCall` 与 backend payload 类分开组织，避免读者混淆模型工具接口和后端执行请求。

当前边界：

- 当前代码有 `global_system_tools()`，包括 `run_shell_command` 和 `write_workspace_file` 等内置工具。
- 自定义工具通过 `FlowToolCall` 进入 loop；工具名称需要避开内置工具名，冲突会触发 `ToolNameConflictError`。
- 当前不宣传完整 plugin registry、自动工具发现或强安全默认隔离。

不要做什么：

- 不把工具系统讲成单纯的 function calling API。
- 不暗示当前已经存在完整插件市场或全局工具注册中心。
- 不把 local backend 的工具副作用写成强安全沙箱能力。

### D11. Session 怎么讲

备选：

- A. 对话历史容器。
- B. Agent runtime state。
- C. chunk + sandbox placement + lineage 的组合对象。

最终决策：采用 C。`Session` 是 OpenRath workflow 中流动的运行时状态对象。它保存 chunk transcript，携带 backend placement，并记录轻量 lineage。站点应把 `Session` 作为 OpenRath 的核心抽象来讲，首页只用短句建立心智模型，详细行为放到 Developer Notes 和 Tutorials。

核心表达：

> `Session` is the runtime state object that flows through OpenRath workflows. It carries the chunk transcript, the backend placement for tool execution, and lightweight lineage metadata for inspecting how new sessions are produced.

中文站点说明：

> `Session` 是 OpenRath workflow 中流动的运行时状态对象。它保存对话 chunk，记录工具执行使用的 backend placement，并携带轻量 lineage，用来说明一个新 session 是如何从已有 session 派生出来的。

首页短句：

> Sessions carry state, placement, and lineage.

分层说明：

| 层级 | 对应代码字段/行为 | 站点解释 |
| --- | --- | --- |
| 对话状态 | `chunk_table` | 按时间顺序保存 `system`、`user`、`assistant`、`tool_result` chunk。 |
| 执行位置 | `sandbox_backend`、`sandbox`、`_sandbox_open_spec` | Session 记录工具副作用应该进入哪个 backend/sandbox。 |
| 生命周期 | `to()`、`with_sandbox()`、`require_sandbox()`、`take_sandbox()` | 支持显式绑定、lazy open、loop 输出接管 sandbox。 |
| 派生关系 | `fork()`、`detach()` | 复制 transcript 和 sandbox target，并产生不同 lineage 语义。 |
| 运行记录 | `parent_session_ids`、`lineage_operator`、`lineage_kind` | 记录 session 由哪个操作、哪些父 session 产生。 |

内容影响：

- 首页：只使用一句 `Sessions carry state, placement, and lineage.`，不要在首屏解释完整生命周期。
- Concepts：把 `Session` 放在第一个核心组件，作为 `Workflow`、`Tool`、`Backend` 的共同载体。
- Developer Notes：展开创建、绑定 backend、进入 loop、fork/detach、compress 的实际行为。
- Tutorials：第一个 tutorial 继续以 `Session.from_agent_prompt(...)`、`Session.from_user_message(...)`、`fork()`、`detach()`、`to("local")` 为入门路径。
- API Reference：把 `Session`、`ChunkTable`、`ChunkRow`、lineage helpers、loop/compress 分开列出。

推荐讲解顺序：

1. 创建：`from_agent_prompt()` 创建 system chunk，`from_user_message()` 创建 user chunk。
2. 绑定：`session.to("local")` 设置 backend target，sandbox handle 在需要时打开。
3. 运行：`run_session_loop()` 读取 agent/user chunk，追加 assistant/tool result，并把 sandbox 绑定到输出 session。
4. 派生：`fork()` 复制 transcript 并记录 parent；`detach()` 复制 transcript 并创建新的 lineage root。
5. 压缩：`run_session_compress()` 把已有上下文压成新的 user-only session。

当前边界：

- `fork()` 和 `detach()` 复制 chunk rows 与 sandbox target，不复制已经打开的 sandbox handle。
- `Session` 负责承载状态、placement 和 lineage；具体工具副作用由 backend 执行。
- `run_session_loop()` 会把 user session 的 sandbox 取出并绑定到返回的输出 session。
- agent session 参与 LLM request；loop 输出的 transcript 以 user rows、assistant rows 和 tool result rows 为主体。

不要做什么：

- 不把 `Session` 简化成普通 chat history。
- 不把 `Session` 写成具体工具执行器。
- 不在首页塞完整 lifecycle 细节。
- 不暗示 fork/detach 会共享同一个 open sandbox handle。

### D12. LLM Provider 怎么讲

备选：

- A. OpenAI-compatible 默认客户端。
- B. 可替换 provider/executor 协议。
- C. 支持任意模型。

最终决策：采用 A + B。OpenRath 默认使用 OpenAI-compatible chat client，同时把 `SessionLoopExecutor` 作为高级替换点。站点应把 `Provider`、默认 client、executor protocol、内部 request/response 格式分层讲清楚。

核心表达：

> OpenRath uses an OpenAI-compatible chat client by default. Advanced users can replace the session loop executor to control model routing, response parsing, and tool dispatch.

中文站点说明：

> OpenRath 默认使用 OpenAI-compatible chat client。`Provider` 保存模型和采样参数，`SessionLoopExecutor` 提供替换模型调用与工具派发的接口，适合接入自定义网关、本地模型服务或测试 executor。

分层说明：

| 层级 | 对应代码对象 | 站点解释 |
| --- | --- | --- |
| 请求参数 | `Provider` | 保存 `model`、`temperature`、`tool_choice`、`parallel_tool_calls`、`response_format` 等请求选项。 |
| 默认客户端 | `RathOpenAIChatClient` | 使用 OpenAI SDK，读取 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_DEFAULT_MODEL`。 |
| loop 替换点 | `SessionLoopExecutor` | 接管 `complete()`、`dispatch_tool()`、`tool_schemas()`。 |
| 默认执行器 | `DefaultSessionLoopExecutor` | 连接默认 LLM client 与 `FlowToolCall` 执行。 |
| 内部格式 | `RathLLMChatRequest` / `RathLLMChatResponse` | OpenRath 内部标准化 chat completion 输入输出。 |

内容影响：

- 首页：只写“OpenAI-compatible by default”，不展开 provider 细节。
- Developer Notes / `llm`：解释 `Provider` 如何合并到 chat request，默认 client 如何加载环境变量，executor 如何替换。
- Tutorials：deterministic tutorial 继续使用 scripted executor，真实 LLM tutorial 再展示 `.env`、`OPENAI_API_KEY`、`OPENAI_DEFAULT_MODEL`。
- API Reference：`Provider`、`RathOpenAIChatClient`、`SessionLoopExecutor`、`DefaultSessionLoopExecutor`、request/response dataclass 分开列。

当前边界：

- 当前默认路径是同步、non-streaming chat completions。
- 模型名来自 `Provider.model` 或 `OPENAI_DEFAULT_MODEL`。
- `OPENAI_BASE_URL` 可用于 OpenAI-compatible endpoint。
- 更复杂的模型路由、自定义响应解析、本地模型服务接入通过 `SessionLoopExecutor` 实现。

不要做什么：

- 不宣传“任意模型全支持”。
- 不把 `Provider` 写成完整 provider registry。
- 不暗示当前默认 client 支持 streaming。
- 不把 deterministic tutorial 写成真实 LLM 行为；它使用 scripted executor 来稳定复现。

### D13. Tutorials 与 Examples 的合并路径

备选：

- A. 先真实 LLM 示例。
- B. 先 deterministic tutorial，再真实 LLM 示例。
- C. 只给源码示例。
- D. Tutorials 页面统一承载 step-by-step tutorials 和可改写 examples。

当前倾向：D。`Tutorials` 是统一学习入口：先放基础 tutorial，随后放真实 LLM 示例和可改写 example。页面内部按学习顺序和主题排序，顶层导航只保留一个入口。

建议页面结构：

```text
Tutorials
- First steps
  - Session basics
  - Local sandbox tools
- Agent loops
  - Session loop with tools
  - Custom FlowToolCall
- Examples
  - Local backend workspace
  - OpenSandbox backend
  - Session compression
```

内容原则：

- 基础 tutorial 排在最前面，用于第一次建立 `Session`、sandbox、tool、loop 的操作经验。
- examples 以可复制、可改写的脚本形式进入同一页面。
- multi-agent examples 也进入同一页面，但应放在 Runnable Examples 后段，作为 `Workflow` 抽象的真实演示。
- 页面标题使用 `Tutorials`，小节中使用 `Examples`。
- 首页和导航只给 `Tutorials` 一个入口。
- 不在 Tutorials 主页面设置 `Generated Assets / Figures and logs` 区块；截图、日志、HTML 中间产物是内部验证和附录材料，不作为正式学习路径的核心内容。
- 不做依赖标签系统。站点默认用户已经按安装文档完成环境配置；只有在具体 tutorial 或 example 需要额外服务时，正文中用一句前置条件说明。
- 2026-05-11 从 `origin/main` 合入的 `example/trading_agents/` 与 `example/engineering_agents/` 应进入 Tutorials，并在 Workflow Developer Notes 中作为 multi-agent composition 的真实例子引用。

### D14. 可信度证据

备选：

- A. 测试数量。
- B. 本地运行日志和截图。
- C. API 参考与源码链接。
- D. 路线图。

最终决策：以源码对应、API Reference 和 deterministic tutorials 作为主要可信度证据，配合测试覆盖说明；截图、日志和生成产物保留为内部验证材料或附录素材，不进入首页和正式学习主路径。

推荐方向：

| 证据类型 | 站点位置 | 表达方式 |
| --- | --- | --- |
| 源码对应 | Developer Notes / API Reference | 每个核心组件给出 source map、public contract、autodoc。 |
| 可运行教程 | Tutorials | 先用 scripted executor 跑通 loop，再进入真实 LLM 示例。 |
| 测试覆盖 | Developer Notes / API Reference | 写清楚哪些行为有测试覆盖，例如 stream FIFO、session lineage、tool merge。 |
| 构建可验证 | Install / README | 给出 `sphinx-build`、tutorial scripts、pytest 的本地命令。 |
| GitHub 透明度 | 顶栏 / CTA | 让读者可以直接看源码、issue、提交历史。 |

决策理由：

- OpenRath 目前最可信的证据是代码结构、API reference、tutorial 和测试，而不是宣传图。
- 测试数量容易过期，行为覆盖更有长期价值。
- 日志和截图适合内部验证，也可以作为 tutorial 附录材料；正式 site 主路径保持干净。
- 路线图可以解释方向，但不能替代当前能力证据。

可直接使用的文案：

> Every concept page links back to the implementation: source files, public contracts, and API reference.

> Tutorials are deterministic first, so new users can inspect the runtime path before connecting a real model provider.

> Developer Notes call out tested behavior and current boundaries where the implementation matters.

不要做什么：

- 不在首页堆测试数量、截图表格或日志链接。
- 不把 roadmap 当作能力证明。
- 不使用容易过期的覆盖率数字作为主证据。
- 不把 generated assets 作为正式 tutorial 的核心结构。

### D15. 视觉风格

备选：

- A. 强产品 landing page。
- B. 工程文档站。
- C. 研究项目主页。

最终决策：B。首页可以有清晰价值表达，但整体应像成熟开源文档。当前视觉方向保留：工程化、清爽、代码优先、低饱和强调色、克制留白，后续只做细节 polish，不重做视觉体系。

补充原则：

- 第一版不依赖复杂插画或强交互来建立高级感，主要靠排版、代码块、清晰层级和稳定导航建立可信度。
- Homepage 可以保留更强的第一屏表达，但正文页面保持文档站气质，避免营销式卡片堆叠。
- 代码示例是核心视觉证据，tutorial 中优先展示代码与简洁输出，而不是大量截图。
- 后续若加入图片资产，应服务于解释抽象或展示运行模型，不能盖过代码和文档结构。

### D16. 是否做交互 demo

备选：

- A. 第一版做交互 demo。
- B. 第一版静态 HTML，后续再做交互。
- C. 不做 demo。

当前倾向：B。当前优先级是文档可信和完整，复杂交互容易拖慢交付。

### D17. 导航结构

备选：

- A. Home / Tutorials / Developer Notes / API Reference / GitHub。
- B. Home / Docs / Examples / Roadmap / GitHub。
- C. Docs-first 单站点导航，侧边栏再展开 Tutorials 和 Developer Notes。

最终决策：A 的收紧版。顶部导航使用四个英文入口：`Installation`、`Tutorials`、`Developer Notes`、`API Reference`。不在导航里使用中文栏目名和英文栏目名并列的混排格式。

补充原则：

- `Developer Notes` 直接保留英文，因为“开发者笔记”作为正式栏目名显得笨拙。
- `API Reference` 直接保留英文，因为这是开发者文档里的稳定栏目名。
- 正式页面可以在正文中解释中文含义，但标题和导航避免中英括号并列。

### D18. 语言策略

备选：

- A. 全中文。
- B. 全英文。
- C. 中文站点优先，保留英文 README 与未来英文站点空间。

最终决策：采用中英文双站点策略。当前先完成中文站，英文站后续从稳定中文站翻译过去。正式中文站正文中文优先，英文用于栏目名、API/class 名、代码概念和少数稳定技术术语。标题里不把中文名称和英文别名并列；中文就中文，英文就英文。

补充原则：

- Homepage 的核心定位句可以保留英文，但正文解释以中文为主。
- 顶部导航使用英文四项，降低“开发者笔记”这类中文直译带来的生硬感。
- Developer Notes 内部组件页可以直接使用 `Session`、`Sandbox`、`Tool`、`Agent Param`、`Workflow`、`LLM` 作为页面标题。
- 正文小标题优先中文；如果是 class、package 或 API 名，则直接使用英文原名。
- `docs/source` 是当前中文站的唯一正式 source tree。
- 英文站后续单独维护为独立 source tree，不在中文站标题里通过括号提前维护英文名。
- 翻译英文站之前，先把中文站的结构、内容准确性、端到端验证和视觉 polish 做完。

### D19. 未完成功能如何呈现

备选：

- A. 不提未完成功能。
- B. Roadmap 中标注 experimental/planned。
- C. 首页直接宣传。

当前倾向：B。避免夸大，同时让读者知道项目方向。

### D20. 首页最终目标

备选：

- A. 让读者 star GitHub。
- B. 让读者跑通 tutorial。
- C. 让读者理解架构。
- D. 让读者联系团队。

当前倾向：B + C。3 分钟理解核心模型，10 分钟跑通 tutorial。

## 待讨论顺序建议

1. 先定 D01-D04：受众、定位、类比、CTA。
2. 再定 D07-D09：文档结构、showcase 去留、sandbox 表达边界。
3. 再定 D15-D18：视觉风格、交互深度、导航、语言。
4. 最后定 D19-D20：未完成功能与首页成功标准。

## 已确认决策

- D01：站点首要受众为工程师优先，面向广泛 Python/LLM agent 用户。OpenRath site 应作为开源项目文档站，而不是学术工具页或路演 landing page。
- D02：首页一句话定位选择 PyTorch-inspired 方向，强调 OpenRath 的抽象来自 PyTorch 的工程心智模型，但必须清楚说明它服务于 LLM agent workflow，而不是 PyTorch 插件或训练框架。
- D03：PyTorch 类比作为核心传播 hook，但解释必须快速落到 OpenRath 自己的真实抽象、代码和 tutorial，不作为整站唯一叙事。
- D04：首页首屏使用三个 CTA：`Start with Tutorials`、`Developer Notes`、`GitHub`，其中 Tutorials 是主 CTA。
- D05：首页首屏放短 Python API 片段，不放完整输出；deterministic 运行证据放到 Tutorials。
- D06：首页不展示 tutorial 截图或日志链接作为主体；采用干净的 code-first 展示。
- D07：正式文档入口修订为 `Install / Tutorials / Developer Notes / API Reference`；`Examples` 合并进入 `Tutorials`，`Developer Notes` 承担核心组件深度说明。
- D08：`docs/source/showcase/` 保留为内部 site 文案素材库，不进入正式 site 主导航。
- D09：sandbox/backend 采用分层表达；强调显式执行位置和可替换 backend，不夸大 local 安全性，也不把 OpenRath 说成 Docker 替代品。
- D10：工具系统采用 `FlowToolCall`、backend-facing payload、Session loop 记录三层表达；全站文案采用正向定义式表达，少用否定式对比。
- D11：`Session` 采用 chunk transcript、sandbox placement、lineage carrier 三层表达；首页短句为 `Sessions carry state, placement, and lineage.`。
- D12：LLM 层采用 OpenAI-compatible 默认客户端 + 可替换 `SessionLoopExecutor` 表达；当前默认路径是同步 non-streaming chat completions。
- D13：`Tutorials` 作为统一学习入口，内部承载 step-by-step tutorials 和 runnable examples；不把 generated assets 或依赖标签系统作为正式页面结构。
- D14：可信度证据采用源码对应、API Reference 和 deterministic tutorials 为主，测试覆盖说明为辅；截图、日志和 generated assets 保留为内部验证材料或附录素材。
- D15：视觉风格采用工程文档站为主体，保留克制的精致感。当前视觉方向整体可接受，后续只做细节 polish，不重做视觉体系。
- D17：顶部导航使用 `Installation`、`Tutorials`、`Developer Notes`、`API Reference` 四个英文入口；正式站点不使用中英括号混排栏目名。
- D18：采用中英文双站点策略；当前先完成中文站，英文站后续从稳定中文站翻译过去。中文站标题不维护英文括号别名。

## 变更记录

- 2026-05-11：创建初始决策记录，列出 20 个站点展示关键决策点。
- 2026-05-11：确认 D01，站点首要受众为工程师优先，同时强调低门槛与广泛可用性。
- 2026-05-11：确认 D02，首页定位采用 PyTorch-inspired runtime for LLM agent workflows。
- 2026-05-11：确认 D03，并新增 PyTorch / OpenRath 对比图资产。
- 2026-05-11：确认阶段性原则，第一版 site 先做无定制图片版本，配图后置到下一阶段。
- 2026-05-11：确认 D04，首屏采用三 CTA 结构，主 CTA 指向 Tutorials。
- 2026-05-11：修订 D04，第二 CTA 使用 `Developer Notes`，与新增核心组件入口保持一致。
- 2026-05-11：确认 D05，首页首屏使用短 Python API 片段展示工程使用感。
- 2026-05-11：确认 D06，首页代码优先，不展示 tutorial 截图和日志链接。
- 2026-05-11：确认 D07，采用成熟开源项目式文档入口分层。
- 2026-05-11：确认 D08，showcase 保留为内部素材库，不进入正式 site。
- 2026-05-11：确认 D09，sandbox/backend 采用分层表达，长期参考 OpenSandbox 与 Anthropic sandbox 思路。
- 2026-05-11：确认 D10，工具系统采用结构化 runtime 接口、backend 执行边界和 Session 记录三层表达；新增正向定义式文案原则。
- 2026-05-11：确认 D11，Session 作为 workflow 中流动的运行时状态对象，承载 chunk transcript、sandbox placement 和 lineage。
- 2026-05-11：修订 D07，合并 Examples 与 Tutorials，并新增 Developer Notes 作为核心组件说明入口；记录 session、sandbox、tool、agent param、workflow、llm 六个组件大纲。
- 2026-05-11：确认 D12，LLM 层强调 OpenAI-compatible 默认 client、`Provider` 请求参数、`SessionLoopExecutor` 替换点和 non-streaming 当前边界。
- 2026-05-11：确认 D13，Tutorials 与 Examples 合并为一个入口，页面按 First Steps、Agent Loops、Runnable Examples 组织，截图/日志产物留作内部验证材料。
- 2026-05-11：确认 D14，可信度表达以源码/API/确定性教程为主，测试覆盖说明为辅，不把截图日志作为正式 site 主路径。
