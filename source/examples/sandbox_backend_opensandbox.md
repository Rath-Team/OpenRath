(example-sandbox-opensandbox)=
# 如何绑定 OpenSandbox

与本地示例对应，将 **`SANDBOX_BACKEND`** 设为 **`opensandbox`**，演示在无主机绑定与绑定 **`spec="."`** 两种情况下通过 **`flow.Agent`** 列出并总结目录内容。

## 运行

```bash
python example/sandbox_backend_opensandbox.py
```

需安装 **`.[opensandbox]`** extra，运行中的 OpenSandbox 服务，并在环境中配置 `OPEN_SANDBOX_DOMAIN`（及部署所需的密钥）；且 `backend.get("opensandbox").is_available()` 为真。

## 要点

* 远程隔离环境内 `/workspace` 与主机目录挂载的差异（`spec=None` vs `spec="."`）。
* 与 [本地沙箱示例](sandbox_backend_local.md) 相同的 `flow.Agent` 用法，仅后端实现不同。

## 源码

* [GitHub：`example/sandbox_backend_opensandbox.py`](https://github.com/Rath-Team/OpenRath/blob/main/example/sandbox_backend_opensandbox.py)

## 延伸阅读

* [沙箱后端](../user_guide/backends.md)
* [安装](../install.md)（可选 OpenSandbox 一节）

---

[← 示例索引](index.md)
