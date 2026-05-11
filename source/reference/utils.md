(pkg-utils)=
# `rath.utils`

当前公共工具集中在 `rath.utils.env`，用于定位项目根目录、加载 `.env` 和读取单个 dotenv value。

## 源码（Source）

| 模块 | 源码 |
| --- | --- |
| `rath.utils.env` | `src/rath/utils/env.py` |

## 公共契约（Public Contract）

| 函数 | 返回 | 行为 |
| --- | --- | --- |
| `project_root_with_pyproject()` | `Path` | 从当前文件向上寻找包含 `pyproject.toml` 的项目根。 |
| `default_env_file_path()` | `Path` | 返回项目根目录下 `.env`。 |
| `load_dotenv_if_present(path, override=False)` | `None` | 文件存在时调用 `python-dotenv` 加载。 |
| `read_dotenv_value(env_path, key)` | `str` \| `None` | 从 `.env` 文件读取单个 key。 |

## 自动文档（Autodoc）

```{eval-rst}
.. autofunction:: rath.utils.env.project_root_with_pyproject

.. autofunction:: rath.utils.env.default_env_file_path

.. autofunction:: rath.utils.env.load_dotenv_if_present

.. autofunction:: rath.utils.env.read_dotenv_value
```

[← API 参考](index.md)
