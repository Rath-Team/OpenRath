# 配置

OpenRath 现在有一个持久本地配置层，用来保存 LLM provider 和 MCP stdio server。它不是必需入口：小脚本仍然可以直接构造 `Provider(...)`；当你需要在多脚本、多项目之间复用密钥和 server 定义时，再使用配置文件。

## 解析顺序

配置文件固定名为 `config.json`，OpenRath 按下面顺序查找：

| 位置 | 何时使用 |
| --- | --- |
| `$OPENRATH_HOME/config.json` | 显式指定 OpenRath home。 |
| `./.openrath/config.json` | 当前项目存在 `.openrath/` 目录。 |
| `~/.openrath/config.json` | 默认用户级配置。 |

`ConfigStore.save()` 会原子写入 JSON，并在 POSIX 上把权限设为仅当前用户可读写。配置目录旁边也会写入 `.gitignore`，避免把密钥误提交。

## LLM provider

最小配置：

```json
{
  "version": 1,
  "llm": {
    "default_provider": "openai-main",
    "providers": {
      "openai-main": {
        "provider_kind": "openai",
        "model": "gpt-5.5",
        "api_key": "sk-...",
        "base_url": "https://api.openai.com/v1"
      },
      "claude": {
        "provider_kind": "anthropic",
        "model": "claude-sonnet-4-5",
        "api_key": "sk-ant-..."
      }
    }
  }
}
```

使用默认 provider：

```python
from rath.llm import Provider

provider = Provider.from_config()
```

使用指定 provider，并覆盖一个字段：

```python
provider = Provider.from_config("openai-main", temperature=0.2)
```

优先级是：显式 `Provider(...)` / `Provider.from_config(..., overrides)` 字段最高，其次是环境变量，最后才是 `config.json` 中同 kind 的 provider fallback。

## MCP server

MCP server 也放在同一个配置文件里：

```json
{
  "version": 1,
  "mcp": {
    "default_enabled": ["filesystem"],
    "servers": {
      "filesystem": {
        "command": ["python", "-m", "mcp_server_filesystem"],
        "env": {}
      }
    }
  }
}
```

`command` 是 argv 列表，不是 shell 字符串。这样 adapter 不需要 shell 解析，也更容易跨平台。

## 代码接口

```python
from rath.config import ConfigStore

store = ConfigStore.load()
provider_entry = store.get_llm_provider(None)
mcp_entries = store.enabled_mcp_servers()
store.save()
```

常用 API：

| API | 用途 |
| --- | --- |
| `ConfigStore.load()` | 读取默认路径；文件不存在时返回空配置。 |
| `store.save()` | 原子保存，写权限保护和 `.gitignore` 防护。 |
| `store.get_llm_provider(name)` | 读取指定 provider；`name=None` 时使用默认 provider。 |
| `store.find_provider_by_kind(kind)` | 给 OpenAI / Anthropic client 做 fallback。 |
| `store.get_mcp_server(name)` | 读取一个 MCP server。 |
| `store.enabled_mcp_servers()` | 按 `mcp.default_enabled` 解析 server 列表。 |

**下一篇：** [会话](session.md)
