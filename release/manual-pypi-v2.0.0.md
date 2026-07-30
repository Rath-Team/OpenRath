# Manual PyPI publication for OpenRath 2.0.0

This procedure uploads only the immutable distributions produced by the
protected `Prepare v2.0.0 GA bundle` workflow. Never rebuild the wheel or sdist
locally and never place a PyPI token in this repository, a command-line
argument, an environment variable, or a GitHub secret.

## One-time PyPI setup

1. Sign in to PyPI with an owner of the `openrath` project.
2. Open <https://pypi.org/manage/account/token/>.
3. Create an API token scoped only to the existing `openrath` project.
4. Copy it to a password manager. The value starts with `pypi-`.

## Prepare the local handoff

After the GA preparation workflow succeeds, check out the exact annotated tag
and download its artifact:

```powershell
git fetch origin --tags
git switch --detach v2.0.0
gh run download <PREPARATION_RUN_ID> `
  --repo Rath-Team/OpenRath `
  --name openrath-2.0.0-ga-candidate `
  --dir release-bundle
```

The helper verifies the SHA-bound manifest, every artifact hash, the current
PyPI state, and Twine metadata before it offers to upload:

```powershell
uv run python scripts/release/publish_pypi_manual.py `
  --bundle-dir release-bundle
```

Type the exact confirmation displayed by the helper. Twine then prompts for
the API token without echoing it. Use the complete value including its
`pypi-` prefix. In Windows Terminal, paste with `Ctrl+Shift+V` if `Ctrl+V`
does not work inside the hidden prompt. The helper performs a second hash
comparison against PyPI after the upload.

Do not use `dist/` from another checkout and do not run `uv build` during this
handoff.

## Finalize the release

Dispatch `Finalize v2.0.0 GA` from `main` with the same annotated tag and the
preparation workflow run ID. Its protected job refuses to continue unless
PyPI exposes exactly the wheel and sdist from the candidate bundle. It then
promotes the already-attested OCI digest to `2.0.0`, creates or verifies the
GitHub Release, and performs fresh public installation and provenance checks.
