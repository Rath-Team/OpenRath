(pkg-config)=
# `rath.config`

Persistent local configuration for LLM providers and MCP servers.

## Source
| Module | Source |
| --- | --- |
| `rath.config.paths` | `src/rath/config/paths.py` |
| `rath.config.schema` | `src/rath/config/schema.py` |
| `rath.config.secrets` | `src/rath/config/secrets.py` |
| `rath.config.store` | `src/rath/config/store.py` |

## Public contract
OpenRath resolves config in this order:

```{figure} ../_static/config-resolution-stack.png
:alt: OpenRath configuration resolution stack

Config resolution starts with explicit `Provider` fields, then environment
variables, and finally the resolved `.openrath/config.json` store.
```

| Location | When used |
| --- | --- |
| `$OPENRATH_HOME/config.json` | Explicit override. |
| `./.openrath/config.json` | Project-local marker directory exists. |
| `~/.openrath/config.json` | Default user config. |

The file is JSON. Unknown fields round-trip through the Pydantic models so newer OpenRath or third-party tools can add sections without losing data.

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
  },
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

### Store helpers
| API | Behavior |
| --- | --- |
| `ConfigStore.load()` | Loads the resolved default path or seeds an empty config. |
| `store.save()` | Writes atomically, sets user-only permissions on POSIX, and writes `.gitignore` guards. |
| `store.get_llm_provider(name)` | Returns a named provider, or `llm.default_provider` when `name=None`. |
| `store.find_provider_by_kind(kind)` | Finds the default matching provider, then the first matching provider. |
| `store.get_mcp_server(name)` | Returns one MCP server entry. |
| `store.enabled_mcp_servers()` | Resolves every name in `mcp.default_enabled`. |

### Consumers
| Consumer | Config behavior |
| --- | --- |
| `Provider.from_config(name=None, **overrides)` | Builds a `Provider` from `llm.providers`; explicit overrides win. |
| `RathOpenAIChatClient` | Falls back to the first `provider_kind="openai"` config entry after Provider kwargs and environment variables. |
| `RathAnthropicChatClient` | Falls back to the first `provider_kind="anthropic"` config entry after Provider kwargs and environment variables. |
| `mcp_tools_from_config(name=None)` | Builds MCP tool wrappers from one configured stdio server. |

## Autodoc
```{eval-rst}
.. autofunction:: rath.config.resolve_config_dir

.. autofunction:: rath.config.resolve_config_path

.. autofunction:: rath.config.is_project_local

.. autoclass:: rath.config.RathConfig
   :members:

.. autoclass:: rath.config.LLMConfig
   :members:

.. autoclass:: rath.config.LLMProviderConfig
   :members:

.. autoclass:: rath.config.MCPConfig
   :members:

.. autoclass:: rath.config.MCPServerConfig
   :members:

.. autoclass:: rath.config.ConfigStore
   :members:

.. autoexception:: rath.config.ConfigError
```

[← API Reference](index.md)
