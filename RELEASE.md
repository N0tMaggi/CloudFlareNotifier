# Releasing

## npm — `@n0tmaggi/cloudflare-notifier`

Releases are triggered by pushing a `v*` tag. The
[publish-npm workflow](.github/workflows/publish-npm.yml) runs automatically:
type-checks, builds, and publishes to npm.

### Steps

**1. Bump the version in `packages/npm/package.json`**
```bash
# edit manually, or use npm version (no git tag yet)
npm version patch --no-git-tag-version --prefix packages/npm
# patch = 0.1.0 → 0.1.1 | minor = 0.1.0 → 0.2.0 | major = 0.1.0 → 1.0.0
```

**2. Commit**
```bash
git add packages/npm/package.json
git commit -m "chore: bump npm to $(node -p "require('./packages/npm/package.json').version")"
```

**3. Tag and push**
```bash
VERSION=$(node -p "require('./packages/npm/package.json').version")
git tag "v$VERSION"
git push origin main --tags
```

The workflow starts automatically. Check progress at:
`https://github.com/N0tMaggi/CloudFlareNotifier/actions`

---

## Python — `cloudflare-notifier` (PyPI, not yet set up)

When ready to publish to PyPI:

**1. Add a `PYPI_TOKEN` secret** to the repository
(PyPI → Account Settings → API tokens → Add token scoped to the project)

**2. Bump the version in `packages/python/pyproject.toml`**
```bash
# edit version = "x.y.z" manually
```

**3. Commit + tag + push** (same flow as npm above)

**4. Add a publish-pypi workflow** — example:
```yaml
- name: Build
  run: pip install build && python -m build
  working-directory: packages/python

- name: Publish
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    packages-dir: packages/python/dist
    password: ${{ secrets.PYPI_TOKEN }}
```

---

## Workflows overview

| File | Trigger | What it does |
|------|---------|--------------|
| `ci.yml` | push to `main`, PRs | pytest · mypy · ruff (Py 3.10–3.12) · tsc (Node 18–22) |
| `pip-audit.yml` | push, PRs, every Monday | pip-audit + npm audit |
| `publish-npm.yml` | push `v*` tag | typecheck → build → npm publish |
