# 本地沙箱工具

这个教程绕过 LLM，直接启动 `LocalBackend` 并调用后端工具。它用于确认 command、filesystem 和 code execution payload 的基本行为。

## 步骤 1：打开 local backend（Step 1）

```python
from rath.backend import get

backend = get("local")
sandbox = backend.open()

print(backend.name)
print(backend.capabilities())
print(sandbox.handle)
```

`sandbox.handle` 是 local backend 管理的工作目录。相对路径会基于这个目录解析。

## 步骤 2：写入并读取文件（Step 2）

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

文件 payload 直接通过 `sandbox.dispatch(...)` 执行。返回值是结构化 result object。

## 步骤 3：运行 shell 命令（Step 3）

```python
from rath.backend import BackendToolCommandRun

result = sandbox.dispatch(
    BackendToolCommandRun(cmd="pwd && cat hello.txt")
)

print(result.exit_code)
print(result.stdout.decode())
```

local backend 使用 host-side subprocess 执行命令，默认工作目录是 sandbox workspace。

## 步骤 4：运行 Python code（Step 4）

```python
from rath.backend import BackendToolCodeRun

result = sandbox.dispatch(
    BackendToolCodeRun(code="print(21 * 2)")
)

print(result.stdout.decode())
```

当前 local backend 会把 code 写成临时 Python 文件，并用当前 Python 解释器执行。

## 步骤 5：关闭 sandbox（Step 5）

```python
backend.close(sandbox)
print(sandbox.closed)
```

`LocalBackend.close(...)` 会删除它管理的工作目录。绑定真实目录时应使用可重建目录或明确的临时目录。

## 关键结论

- `BackendTool*` payload 描述后端侧操作。
- `BackendSandbox.dispatch(...)` 执行 payload 并返回结构化结果。
- 文件、命令和代码 payload 围绕同一个 sandbox workspace 工作。
