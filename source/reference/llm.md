(pkg-llm)=
# `rath.llm`

OpenAI 兼容的聊天客户端、请求/响应数据类与 Provider。用户指南：[LLM 客户端与配置](../user_guide/llm.md)。

## `rath.llm`

包级导出：`RathOpenAIChatClient`、`Provider`、请求/响应类型等。

## `rath.llm.client`

同步 HTTP 补全：`RathOpenAIChatClient`。

## `rath.llm.provider`

`Provider` 冻结数据类：端点 `base_url` / `api_key`、模型 ID、采样与 `tool_choice` 等。在应用中请自行从环境或配置构造 `Provider`（仓库内示例见 `example/_openai_provider.py`）。

## `rath.llm.chat_request` / `rath.llm.chat_response`

`RathLLMChatRequest`、`RathLLMChatResponse` 及消息/工具线协议对齐结构。

## `rath.llm.openai_create_kwargs` / `openai_normalize`

与 OpenAI Python SDK / 网关之间的参数归一化辅助。

---

[← API 参考](index.md)
