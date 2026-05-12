(pkg-rath)=
# `rath`

The package-level entrypoint is `src/rath/__init__.py`. The package root exposes only high-level modules and does not promote all session/backend/flow symbols into the root namespace.

## Public contract
| Name | Source | Description |
| --- | --- | --- |
| `backend` | eager import | Backend public API. |
| `flow` | eager import | Workflow and agent API. |
| `session` | lazy import through `__getattr__` | Imported on first access to `rath.session`. |

Explicit import style:

```python
from rath import flow
from rath.backend import get
from rath.session import Session, run_session_loop
```

## Autodoc
```{eval-rst}
.. automodule:: rath
```

[← API Reference](index.md)
