(pkg-rath)=
# `rath`

包级入口位于 `src/rath/__init__.py`。包根只暴露高层模块，不把 session/backend/flow 的全部符号提升到根命名空间。

## 公共契约（Public Contract）

| 名称 | 来源 | 说明 |
| --- | --- | --- |
| `backend` | eager import | 后端公共 API。 |
| `flow` | eager import | workflow 与 agent API。 |
| `session` | lazy import through `__getattr__` | 首次访问 `rath.session` 时导入。 |

推荐显式导入：

```python
from rath import flow
from rath.backend import get
from rath.session import Session, run_session_loop
```

## 自动文档（Autodoc）

```{eval-rst}
.. automodule:: rath
```

[← API 参考](index.md)
