# OpenRath Documentation Maintenance

`docs/source` is the primary English documentation source tree for OpenRath.
Chinese-language planning notes may remain in `docs/*.md`, but the published
Sphinx site should be maintained in English by default.

Build the primary English site:

```bash
bash scripts/build_docs.sh
```

The generated HTML is under `docs/_build/html/`.

The build script also accepts alternate source and output directories:

```bash
DOCS_SOURCE=docs/source_en DOCS_BUILD=docs/_build_en bash scripts/build_docs.sh
```
