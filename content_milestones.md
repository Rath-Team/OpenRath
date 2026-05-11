# OpenRath 中文站内容建设 Milestones

本文档记录中文站从“可预览”走向“可发布”的内容建设路径。当前先把中文站写扎实；英文站后续从稳定中文站翻译过去。

## Milestone 总览

| ID | 名称 | 目标 | 状态 |
| --- | --- | --- | --- |
| M1 | Session 深度化 | 把 `Session` 写成真正的核心概念页，并把 Session 基础 tutorial 改成带读式教程。 | 已完成 |
| M2 | Tool 与 Sandbox 深度化 | 讲清 `FlowToolCall`、backend payload、tool result、local/OpenSandbox 生命周期和选择标准。 | 已完成 |
| M3 | Workflow 与多智能体深度化 | 讲清 `Workflow`、`AgentParam`、单 agent 到 multi-agent 的演进方式。 | 已完成 |
| M4 | Tutorials 全量带读 | 所有 tutorial 增加目标、关键行解释、观察点、失败检查和练习。 | 已完成 |
| M5 | 端到端验证 | 使用 DeepSeek/OpenAI-compatible 配置、local backend、OpenSandbox 和 multi-agent examples 跑通发布前验证。 | 已完成 |
| M6 | 发布前审计 | 检查搜索、导航、链接、API Reference、示例命令、默认 key、OpenSandbox 安装路径。 | 已完成 |
| M7 | 英文站启动 | 中文站稳定后，创建英文站独立 source tree 并翻译，不在中文站中维护英文括号别名。 | 待开始 |

## 页面写作标准

每个核心概念页都应该回答五类问题：

| 问题 | 写法 |
| --- | --- |
| 这个组件解决什么问题 | 用一段中文先建立直觉，避免只列 API。 |
| 为什么 OpenRath 这样组织 | 说明设计动机和对应的源码行为。 |
| 用户什么时候会直接接触它 | 给出常见开发场景和判断标准。 |
| 关键 API 如何改变运行状态 | 说明输入、输出、状态迁移和副作用。 |
| 容易误解或失败的边界 | 写清异常、生命周期、默认行为和检查方法。 |

每个 tutorial 都应该包含五个部分：

| 部分 | 作用 |
| --- | --- |
| 学习目标 | 说明读完后应该建立什么直觉。 |
| 代码步骤 | 每步只引入一个新概念。 |
| 关键行解释 | 解释为什么这一行重要。 |
| 观察点 | 告诉读者应该看到什么现象。 |
| 失败检查与小练习 | 帮读者从复制运行过渡到主动修改。 |

## M1 验收标准

- `docs/source/developer_notes/session.md` 从源码地图扩展为核心概念讲解页。
- `docs/source/tutorial/session_basics.md` 从最小示例扩展为带读式教程。
- 文档仍严格对应当前源码，不引入未实现能力。
- 不使用中英文括号混排标题。
- Sphinx HTML build 通过。
