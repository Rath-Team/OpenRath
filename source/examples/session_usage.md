(example-session-usage)=
# 如何使用 Session

演示 **`Session` 构造**、**`fork` / `detach`**，以及在 `__main__` 中走通 **`run_session_loop` 与 `run_session_compress`**，并绑定**本地沙箱**。

## 运行

在仓库根目录：

```bash
python example/session_usage.py
```

`__main__` 中通过 `example/_openai_provider.py` 的 `provider_from_env()` 与显式 `model` 构造 `Provider`，因此需可用的 **LLM** 进程环境变量（至少 `OPENAI_API_KEY`）；详见[安装](../install.md)。

## 要点

* `Session.from_agent_prompt` / `Session.from_user_message` 构造 agent 侧与用户侧会话。
* `user_session.to("local", spec="./")` 将工作目录绑定到本地后端。
* `run_session_loop` 交替补全与工具轮次；`run_session_compress` 对结果会话做压缩。

## 源码

* [GitHub：`example/session_usage.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/session_usage.py)

## 延伸阅读

* [会话](../user_guide/session.md)
* [沙箱后端](../user_guide/backends.md)
* [工作流](../user_guide/workflow_agent.md)
* [LLM 请求接口](../user_guide/llm.md)

---

[← 示例索引](index.md)
