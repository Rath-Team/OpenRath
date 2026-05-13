(pkg-utils)=
# `rath.utils`

The current public utilities are in `rath.utils.env`. They locate the project root and expose test-oriented environment helpers.

## Source
| Module | Source |
| --- | --- |
| `rath.utils.env` | `src/rath/utils/env.py` |

## Public contract
| Function | Returns | Behavior |
| --- | --- | --- |
| `project_root_with_pyproject()` | `Path` | Returns the repository root that contains `pyproject.toml`. |
| `TEST_BASE_URL` | `str` \| `None` | Lazily reads `TEST_BASE_URL` from the process environment. |
| `TEST_API_KEY` | `str` \| `None` | Lazily reads `TEST_API_KEY` from the process environment. |
| `TEST_MODEL` | `str` \| `None` | Lazily reads `TEST_MODEL` from the process environment. |

## Autodoc
```{eval-rst}
.. autofunction:: rath.utils.env.project_root_with_pyproject
```

[← API Reference](index.md)
