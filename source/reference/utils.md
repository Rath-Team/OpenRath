(pkg-utils)=
# `rath.utils`

The current public utilities are in `rath.utils.env`. They locate the project root, load `.env`, and read individual dotenv values.

## Source
| Module | Source |
| --- | --- |
| `rath.utils.env` | `src/rath/utils/env.py` |

## Public contract
| Function | Returns | Behavior |
| --- | --- | --- |
| `project_root_with_pyproject()` | `Path` | Walks upward from the current file to find the project root containing `pyproject.toml`. |
| `default_env_file_path()` | `Path` | Returns `.env` under the project root. |
| `load_dotenv_if_present(path, override=False)` | `None` | Calls `python-dotenv` when the file exists. |
| `read_dotenv_value(env_path, key)` | `str` \| `None` | Reads a single key from a `.env` file. |

## Autodoc
```{eval-rst}
.. autofunction:: rath.utils.env.project_root_with_pyproject

.. autofunction:: rath.utils.env.default_env_file_path

.. autofunction:: rath.utils.env.load_dotenv_if_present

.. autofunction:: rath.utils.env.read_dotenv_value
```

[← API Reference](index.md)
