(pkg-rath)=
# `rath`

顶层命名空间，对子系统做集中入口式导出。

## 说明

访问 `import rath` 时：

* **`rath.backend`**、`rath.flow`** — 常规 eager 导出。
* **`rath.session`** — **惰性加载**：首次访问 `rath.session` 时再导入，避免不必要依赖与导入顺序问题。

业务代码建议按需使用子模块（如 `from rath.session import Session`），与阅读 [用户指南](../user_guide/index.md) 的顺序一致。

---

[← API 参考](index.md)
