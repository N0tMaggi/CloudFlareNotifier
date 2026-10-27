# Releasing

## npm — `@maggidev/cloudflare-notifier`

Releases are triggered by pushing a `v*` tag. The
[publish-npm workflow](.github/workflows/publish-npm.yml) runs automatically:
it checks that the tag matches `package.json` and that the version isn't published yet,
then type-checks, tests, builds, and publishes to npm.

Publishing uses [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers) (OIDC),
so no npm token is stored in GitHub and every release gets a provenance attestation.
One-time setup on npmjs.com: package → **Settings** → **Trusted Publisher** → **GitHub Actions**,
repository `N0tMaggi/CloudFlareNotifier`, workflow `publish-npm.yml`.

If a publish fails after the tag is pushed, fix the cause and start the workflow manually from `main`
(**Actions → Publish npm → Run workflow**, or `gh workflow run publish-npm.yml --ref main`)
instead of moving the tag.

Before releasing, move the **Unreleased** entries in [CHANGELOG.md](CHANGELOG.md) under a new version heading.

### Steps

**1. Bump the version in `packages/npm/package.json`**
```bash
# edit manually, or use npm version (no git tag yet)
npm version patch --no-git-tag-version --prefix packages/npm
# patch = 0.1.0 → 0.1.1 | minor = 0.1.0 → 0.2.0 | major = 0.1.0 → 1.0.0
```

**2. Commit**
```bash
git add packages/npm/package.json CHANGELOG.md
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
| `ci.yml` | push to `main`, PRs | pytest · mypy · ruff (Py 3.10–3.14) · tsc · Vitest · build (Node 22–26) |
| `pip-audit.yml` | push, PRs, every Monday | pip-audit + npm audit (GitHub disables the schedule after 60 days without repository activity; re-enable it under Actions) |
| `publish-npm.yml` | push `v*` tag, manual | version check → typecheck → test → build → npm publish (OIDC, provenance) |
