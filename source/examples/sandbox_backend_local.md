(example-sandbox-local)=
# 如何绑定本地沙箱

使用 **`local`** 后端名，演示 `Session.to("local", spec=...)`：先在**无工作目录绑定**（临时空 workspace）下执行一轮 `flow.Agent`，再在 **`spec="."`**（主机当前工程根）下再跑一轮。

## 运行

```bash
python example/sandbox_backend_local.py
```

需本地后端可用（`backend.get("local").is_available()` 为真），且 `flow.Agent` 所使用的模型/API 已正确配置。

## 要点

* `SANDBOX_BACKEND = "local"`，通过 `user_session.to(SANDBOX_BACKEND, spec=None)` 与 `spec="."` 对比绑定行为。
* 使用 **`flow.Agent`** 封装 `system_prompt` 与 `model`，以类似高层 API 的方式驱动会话循环。

## 源码

* [GitHub：`example/sandbox_backend_local.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/sandbox_backend_local.py)

## 延伸阅读

* [沙箱后端](../user_guide/backends.md)
* [API：`rath.backend`](../reference/backend.md)

---

[← 示例索引](index.md)
