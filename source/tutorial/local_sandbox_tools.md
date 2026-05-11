# 本地沙箱工具

本教程绕过 LLM，直接启动 `LocalBackend` 并调用后端工具，用来说明文件、命令和代码 payload 如何进入本地 workspace 执行。

## 覆盖内容
| 主题 | 结果 |
| --- | --- |
| backend registry | `get("local")` 如何取得本地后端。 |
| sandbox handle | local sandbox 对应一个工作目录。 |
| backend payload | 文件、命令、代码执行都通过 `BackendTool*` 数据类表达。 |
| structured result | 每次 dispatch 都返回结构化对象。 |
| lifecycle | `backend.close(sandbox)` 会关闭 sandbox，并可能清理工作目录。 |

## 步骤 1：打开 local backend
```python
from rath.backend import get

backend = get("local")
sandbox = backend.open()

print(backend.name)
print(backend.capabilities())
print(sandbox.handle)
```

关键行：

| 行 | 解释 |
| --- | --- |
| `get("local")` | 从 backend registry 里取出本地后端实例。 |
| `backend.open()` | 创建一个 `BackendSandbox` handle。 |
| `sandbox.handle` | local backend 管理的 workspace 路径。 |

观察结果：

- `backend.name` 为 `local`。
- `sandbox.handle` 为一个本地路径。
- 如果没有传入 `working_dir`，local backend 会创建临时目录。

## 步骤 2：写入并读取文件
```python
from rath.backend import BackendToolFilesRead, BackendToolFilesWrite

write_result = sandbox.dispatch(
    BackendToolFilesWrite(path="hello.txt", data="hello OpenRath")
)
content = sandbox.dispatch(
    BackendToolFilesRead(path="hello.txt", encoding="utf-8")
)

print(write_result)
print(content)
```

关键行：

| 行 | 解释 |
| --- | --- |
| `BackendToolFilesWrite(...)` | 描述一次文件写入，不直接执行。 |
| `sandbox.dispatch(...)` | 把 payload 交给当前 sandbox 执行。 |
| `BackendToolFilesRead(...)` | 在同一个 workspace 里读取刚写入的文件。 |

观察结果：

- 写入结果会包含写入字节数。
- 读取结果会包含文件内容。
- 相对路径 `hello.txt` 基于 `sandbox.handle` 解析。

## 步骤 3：运行 shell 命令
```python
from rath.backend import BackendToolCommandRun

result = sandbox.dispatch(
    BackendToolCommandRun(cmd="pwd && cat hello.txt")
)

print(result.exit_code)
print(result.stdout.decode())
print(result.stderr.decode())
```

关键行：

| 行 | 解释 |
| --- | --- |
| `BackendToolCommandRun(...)` | 描述一次 shell 命令执行。 |
| `exit_code` | 让调用方判断命令是否成功。 |
| `stdout` / `stderr` | 当前实现以 bytes 保存输出，读取时需要 decode。 |

观察结果：

- `pwd` 输出的目录和 local sandbox workspace 对应。
- `cat hello.txt` 能读到上一步写入的内容。
- 命令失败时，应优先看 `exit_code` 和 `stderr`。

## 步骤 4：运行 Python code
```python
from rath.backend import BackendToolCodeRun

result = sandbox.dispatch(
    BackendToolCodeRun(code="print(21 * 2)")
)

print(result.stdout.decode())
print(result.stderr.decode())
print(result.error)
```

当前 local backend 会把 code 写成临时 Python 文件，再用当前 Python 解释器执行。它适合验证工具路径和脚本行为；涉及不可信代码时，应使用更严格的隔离后端。

## 步骤 5：关闭 sandbox
```python
backend.close(sandbox)
print(sandbox.closed)
```

关键点：

| 行为 | 说明 |
| --- | --- |
| `backend.close(sandbox)` | 关闭 sandbox handle。 |
| local workspace cleanup | local backend 会清理它管理的目录。 |
| bound directory risk | 绑定真实目录时确认目录可重建，降低误删重要内容的风险。 |

## 常见问题
| 现象 | 检查方向 |
| --- | --- |
| `get("local")` 报错 | 确认 OpenRath 已安装，`rath.backend` 能正常 import。 |
| 文件读不到 | 确认写入和读取发生在同一个 sandbox 上。 |
| 命令没有输出 | 先打印 `exit_code` 和 `stderr.decode()`。 |
| close 后继续 dispatch 报错 | sandbox 关闭后需要重新 `backend.open()`。 |

## 练习
1. 把 `hello.txt` 改成 `notes/hello.txt`，观察目录是否会自动创建。
2. 改写 shell 命令，让它列出 workspace 下的所有文件。
3. 把 Python code 改成读取 `hello.txt` 并打印长度。

## 小结

- `BackendTool*` payload 描述后端侧操作。
- `BackendSandbox.dispatch(...)` 执行 payload 并返回结构化结果。
- 文件、命令和代码 payload 围绕同一个 sandbox workspace 工作。
- session loop 中的内置工具最终也会落到这一层 backend dispatch。
