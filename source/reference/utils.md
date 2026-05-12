(pkg-utils)=
# `rath.utils`

`rath.utils.env` 提供项目根路径定位；`rath.utils` 包还 re-export 解码等工具（见包自动文档）。

## 源码（Source）

| 模块 | 源码 |
| --- | --- |
| `rath.utils.env` | `src/rath/utils/env.py` |
| `rath.utils.decoding` | `src/rath/utils/decoding.py` |

## 公共契约（Public Contract）

| 符号 | 说明 |
| --- | --- |
| `project_root_with_pyproject()` | 返回含 `pyproject.toml` 的仓库根目录（相对 `src/rath/...` 固定深度）。 |
| `TEST_BASE_URL` / `TEST_API_KEY` / `TEST_MODEL` | 惰性读取同名环境变量，供 pytest 与示例使用（空则视为未设置）。 |

## 自动文档（Autodoc）

```{eval-rst}
.. autofunction:: rath.utils.env.project_root_with_pyproject

.. autofunction:: rath.utils.decoding.decode_subprocess_output
```

[← API 参考](index.md)
