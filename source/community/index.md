# Community

OpenRath is open source. Project norms mirror common PyTorch community docs pages—linking governance,
contribution expectations, and design discussions—without duplicating content that belongs in the main
repository `README.md`.

## Contributing

* Start from the repository `README.md` for clone/install expectations.
* Run `pytest`, `flake8`, and `mypy` before submitting changes (see `pyproject.toml` tooling pins).
* Optional integrations (`opensandbox`) should remain guarded imports so core installs stay lightweight.

## Design collateral

Higher-level planning notes may live alongside your checkout under `.claude/` depending on workspace layout.

```{note}
As canonical URLs stabilize (GitHub organization, docs hosting domain), wire them into `docs/source/conf.py`
via `html_theme_options["github_url"]` to enable PyData's edit-this-page affordances similar to PyTorch docs.
```
