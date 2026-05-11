# 教程运行记录索引（Tutorial Run Logs）

这一页只保留 tutorial 的本地运行记录，不再展示代码截图。正式教程页面以 Markdown 代码块为主；这些日志和 HTML 只用于复现当时生成 tutorial 内容时的中间结果。

重新生成运行记录：

```bash
python docs/source/tutorial/scripts/run_tutorial_steps.py
```

## Session 基础

| Step | 日志 | 源 HTML |
| --- | --- | --- |
| 创建 sessions | [txt](assets/session-basics/logs/session-basics-01-create-sessions.txt) | [html](assets/session-basics/html/session-basics-01-create-sessions.html) |
| fork 与 detach | [txt](assets/session-basics/logs/session-basics-02-fork-and-detach.txt) | [html](assets/session-basics/html/session-basics-02-fork-and-detach.html) |
| lazy local sandbox | [txt](assets/session-basics/logs/session-basics-03-lazy-local-sandbox.txt) | [html](assets/session-basics/html/session-basics-03-lazy-local-sandbox.html) |

## 本地沙箱工具

| Step | 日志 | 源 HTML |
| --- | --- | --- |
| 打开 local backend | [txt](assets/local-sandbox-tools/logs/local-sandbox-tools-01-open-local-backend.txt) | [html](assets/local-sandbox-tools/html/local-sandbox-tools-01-open-local-backend.html) |
| 写入 workspace 文件 | [txt](assets/local-sandbox-tools/logs/local-sandbox-tools-02-write-workspace-file.txt) | [html](assets/local-sandbox-tools/html/local-sandbox-tools-02-write-workspace-file.html) |
| 运行 shell 命令 | [txt](assets/local-sandbox-tools/logs/local-sandbox-tools-03-run-shell-command.txt) | [html](assets/local-sandbox-tools/html/local-sandbox-tools-03-run-shell-command.html) |
| 读取文件并运行代码 | [txt](assets/local-sandbox-tools/logs/local-sandbox-tools-04-read-file-and-run-code.txt) | [html](assets/local-sandbox-tools/html/local-sandbox-tools-04-read-file-and-run-code.html) |
| 关闭 sandbox | [txt](assets/local-sandbox-tools/logs/local-sandbox-tools-05-close-local-sandbox.txt) | [html](assets/local-sandbox-tools/html/local-sandbox-tools-05-close-local-sandbox.html) |

## Session Loop 工具调用

| Step | 日志 | 源 HTML |
| --- | --- | --- |
| 准备 scripted LLM | [txt](assets/session-loop-tools/logs/session-loop-tools-01-prepare-scripted-llm.txt) | [html](assets/session-loop-tools/html/session-loop-tools-01-prepare-scripted-llm.html) |
| 运行 session loop | [txt](assets/session-loop-tools/logs/session-loop-tools-02-run-session-loop.txt) | [html](assets/session-loop-tools/html/session-loop-tools-02-run-session-loop.html) |
| 验证副作用 | [txt](assets/session-loop-tools/logs/session-loop-tools-03-verify-loop-side-effect.txt) | [html](assets/session-loop-tools/html/session-loop-tools-03-verify-loop-side-effect.html) |

## 自定义 FlowToolCall

| Step | 日志 | 源 HTML |
| --- | --- | --- |
| 定义自定义工具 | [txt](assets/custom-flow-tool/logs/custom-flow-tool-01-define-custom-tool.txt) | [html](assets/custom-flow-tool/html/custom-flow-tool-01-define-custom-tool.html) |
| 注册并运行 loop | [txt](assets/custom-flow-tool/logs/custom-flow-tool-02-run-custom-tool-loop.txt) | [html](assets/custom-flow-tool/html/custom-flow-tool-02-run-custom-tool-loop.html) |
