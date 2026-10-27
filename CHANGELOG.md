# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The packages follow [Semantic Versioning](https://semver.org/); while they are below 1.0.0, a minor version bump (0.x.0) can contain breaking changes.

## [Unreleased]

### Python: `cloudflare-notifier`

#### Fixed

- On Python 3.10 the watcher no longer crashes after the first poll interval (`asyncio.TimeoutError` is not the built-in `TimeoutError` there).

#### Changed

- Requires `aiohttp>=3.14`.

## [0.2.0] - 2026-10-27

### npm: `@maggidev/cloudflare-notifier`

#### Breaking

- Requires Node.js 22.12 or newer; Node.js 18 and 20 are no longer supported.
- Reads security events only from the GraphQL Analytics API (`firewallEventsAdaptive`). The REST endpoints `/zones/{id}/security/events` and `/zones/{id}/firewall/events` are no longer called.
- `raw` now holds the original GraphQL event object (camelCase field names).
- Invalid zone IDs and option values throw in the constructor.
- `stop()` returns a `Promise` that resolves once polling has exited.

#### Added

- Batching of up to 10 zones per GraphQL request; an error for one zone doesn't affect the others.
- Pagination, so bursts larger than one page are no longer truncated.
- Overlap window (`overlap`, default 300 s) with deduplication, to catch events Cloudflare ingests late.
- Schema introspection: only fields the API exposes are requested.
- New `SecurityEvent` fields: `host`, `method`, `path`, `query`, `userAgent`, `asn`.
- `ruleMessage` is filled from the rule `description`.
- Per-request timeout (`requestTimeout`) and retries with exponential backoff (`maxRetries`) for network errors, timeouts, HTTP 429 (honouring `Retry-After`) and 5xx.
- Exported `CloudflareApiError` with `status`, `endpoint` and Cloudflare's `errors`.
- `fetch` option for custom fetch implementations.

#### Fixed

- Calling `start()` twice no longer starts two polling loops.
- `stop()` interrupts in-flight requests and the wait between polls.

### Project

- Updated tooling: TypeScript 7, Vitest 5, pytest 9, mypy 2, ruff 0.17.
- CI tests Node.js 22, 24 and 26 and Python 3.10 to 3.14, and builds the npm package.
- Added INSTALL, CONTRIBUTING and SECURITY guides, plus issue and pull request templates.

## [0.1.x] - 2026-04 (npm)

First releases of `@maggidev/cloudflare-notifier`: `CloudFlareWatcher` with `onEvent` and `onError`. Events are read via REST with GraphQL as a fallback.

[Unreleased]: https://github.com/N0tMaggi/CloudFlareNotifier/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/N0tMaggi/CloudFlareNotifier/compare/v0.1.9...v0.2.0
