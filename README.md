# OpenRath 文档维护说明

当前 `docs/source` 是中文站的正式 source tree。我们先在中文站完成内容结构、接口准确性、端到端验证和视觉 polish。

后续英文站会作为独立 source tree 从稳定中文站翻译过去，建议路径为 `docs/source_en`。中文站不通过标题括号维护英文别名；中文标题就写中文，API/class/package 名称保留英文原名。

构建当前中文站：

```bash
bash scripts/build_docs.sh
```

生成结果位于 `docs/_build/html/`。

后续英文站准备好后，可以用同一个脚本指定 source 和 build 目录：

```bash
DOCS_SOURCE=docs/source_en DOCS_BUILD=docs/_build_en bash scripts/build_docs.sh
```
