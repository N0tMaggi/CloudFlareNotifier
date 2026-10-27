# Contributing

Thanks for your interest in improving cloudflare-notifier. Bug reports, fixes, documentation and feature ideas are all welcome.

## Before you start

- **Bugs:** [open an issue](https://github.com/N0tMaggi/CloudFlareNotifier/issues/new/choose) with steps to reproduce, the package and version, and your runtime version.
- **Features:** open an issue first, so we can agree on the approach before you write code.
- **Security issues:** do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Repository layout

```
packages/
  npm/       TypeScript package @maggidev/cloudflare-notifier
    src/     library source
    test/    Vitest tests (fake Cloudflare API, no network)
  python/    Python package cloudflare-notifier
    src/     library source
    tests/   pytest tests
.github/workflows/   CI, security audit, npm publishing
```

The TypeScript package is the reference implementation. When you change behaviour in one package, mention in your pull request whether the other one needs the same change.

## Development setup

### TypeScript

Requires Node.js 22.12 or newer.

```bash
cd packages/npm
npm ci
npm test            # Vitest
npm run typecheck   # tsc --noEmit
npm run build       # emits dist/
```

### Python

Requires Python 3.10 or newer.

```bash
cd packages/python
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -v
python -m mypy src/
python -m ruff check src/ tests/
```

## Guidelines

- **Tests:** every bug fix gets a test that fails without the fix. Tests must not call the real Cloudflare API; use the fakes in `packages/npm/test/helpers.ts` or monkeypatching in Python.
- **No new runtime dependencies** in the npm package without discussion. The Python package depends on `aiohttp` only.
- **Public API:** changes to exported names, option names or `SecurityEvent` fields are breaking changes; call them out in the pull request.
- **Style:** follow the surrounding code. CI enforces `tsc --strict`, `mypy --strict` and `ruff`.
- **Secrets:** never commit tokens, zone IDs from real accounts, or captured event data.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>
```

- **Types:** `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`
- **Scopes:** `npm` or `python` when a change touches only one package
- **Breaking changes:** add a `BREAKING CHANGE:` footer

Examples: `fix(python): catch asyncio.TimeoutError on Python 3.10`, `feat(npm): batch zones per GraphQL request`.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests.
3. Run the checks for the package(s) you touched, as listed above.
4. Add an entry under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. Open the pull request and fill in the template.

CI runs on Node.js 22, 24 and 26 and on Python 3.10 to 3.14. A pull request needs green CI before it can be merged.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
