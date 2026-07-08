# Publishing

`mcp-server-doctor` is configured for PyPI Trusted Publishing through GitHub Actions.

## PyPI Trusted Publisher

Create a pending publisher on PyPI before the first release:

- PyPI project name: `mcp-server-doctor`
- Owner: `Uky0Yang`
- Repository: `mcp-server-doctor`
- Workflow name: `release.yml`
- Environment name: `pypi`

After that, pushing a version tag runs `.github/workflows/release.yml`, builds the wheel and source distribution, checks them with Twine, and publishes to PyPI through OIDC.

```bash
git tag v0.2.0
git push origin v0.2.0
```

## Why Trusted Publishing

Trusted Publishing avoids long-lived PyPI API tokens in GitHub secrets. PyPI mints a short-lived token only for the configured repository, workflow, and environment.

## Manual Build Check

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```
