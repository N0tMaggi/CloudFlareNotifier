# cloudflare-notifier

[![npm](https://img.shields.io/npm/v/%40maggidev%2Fcloudflare-notifier?label=npm)](https://www.npmjs.com/package/@maggidev/cloudflare-notifier)
[![npm downloads](https://img.shields.io/npm/dm/%40maggidev%2Fcloudflare-notifier)](https://www.npmjs.com/package/@maggidev/cloudflare-notifier)
[![CI](https://img.shields.io/github/actions/workflow/status/N0tMaggi/CloudFlareNotifier/ci.yml?branch=main&label=CI)](https://github.com/N0tMaggi/CloudFlareNotifier/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/N0tMaggi/CloudFlareNotifier)](LICENSE)

**Poll Cloudflare security events from Node.js or Python and react to them in your own code.**

Register a handler, get called once for every new WAF, firewall, rate-limit or bot event across your zones. No built-in notifications, no opinions on what you do next: send it to Slack, write it to a database, block an IP, page someone.

```ts
watcher.onEvent((event) => {
  console.log(`[${event.action}] ${event.clientIp} ${event.method} ${event.path} – ${event.ruleMessage}`);
});
```

---

## Contents

- [Why](#why)
- [Features](#features)
- [Install](#install)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Event fields](#event-fields)
- [How it works](#how-it-works)
- [Security](#security)
- [Documentation](#documentation)
- [License](#license)

---

## Why

Cloudflare doesn't push security events, you have to poll the GraphQL Analytics API. Doing that reliably means handling:

- one GraphQL query per zone, or batching them yourself,
- pagination, so a burst during an attack doesn't truncate results,
- events that Cloudflare ingests with a delay,
- duplicates when time windows overlap,
- timeouts, rate limits (HTTP 429) and transient 5xx errors,
- schema differences between plans.

This library does all of that. You write the handler.

## Features

| | Node.js / TypeScript | Python |
|---|:---:|:---:|
| Callback / event API | ✅ | ✅ |
| Multiple zones | ✅ batched, 10 per request | ✅ one request per zone |
| GraphQL Analytics API (`firewallEventsAdaptive`) | ✅ only source | ✅ fallback after REST |
| Pagination for bursts | ✅ | — |
| Overlap window and dedupe for late events | ✅ | — |
| Schema introspection (request only available fields) | ✅ | — |
| Request timeout | ✅ configurable | ✅ fixed 15 s |
| Retries with backoff and `Retry-After` | ✅ | — |
| Typed errors (`CloudflareApiError`) | ✅ | — |
| Runtime dependencies | none | `aiohttp` |

The TypeScript package is the reference implementation. The Python package will be brought to the same feature set.

## Install

**Node.js** 22.12 or newer:

```bash
npm install @maggidev/cloudflare-notifier
```

**Python** 3.10 or newer. Not on PyPI yet; install from GitHub:

```bash
pip install "git+https://github.com/N0tMaggi/CloudFlareNotifier.git#subdirectory=packages/python"
```

You need a Cloudflare API token with **Zone → Zone → Read** and **Zone → Analytics → Read**. [INSTALL.md](INSTALL.md) walks through creating one, configuring environment variables and running the watcher as a service.

## Quick start

### Node.js / TypeScript

```ts
import { CloudFlareWatcher, CloudflareApiError } from "@maggidev/cloudflare-notifier";

const watcher = new CloudFlareWatcher({
  apiToken: process.env.CLOUDFLARE_API_TOKEN!,
  zoneIds: process.env.CLOUDFLARE_ZONE_IDS!.split(","),
});

watcher.onEvent(async (event) => {
  console.log(`${event.zoneName}: [${event.action}] ${event.clientIp} (${event.country}) ${event.path}`);
});

watcher.onError((error) => {
  if (error instanceof CloudflareApiError) {
    console.error(`Cloudflare API ${error.endpoint} failed with HTTP ${error.status}`, error.errors);
  } else {
    console.error(error);
  }
});

process.on("SIGTERM", () => void watcher.stop());

await watcher.start(); // resolves after stop()
```

Run it server-side only: a Node.js process, an API backend, a worker. Never ship an API token to a browser.

### Python

```python
import asyncio
import os

from cloudflare_notifier import CloudFlareWatcher, SecurityEvent

watcher = CloudFlareWatcher(
    api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    zone_ids=os.environ["CLOUDFLARE_ZONE_IDS"].split(","),
)

@watcher.on_event
async def handle(event: SecurityEvent) -> None:
    print(f"{event.zone_name}: [{event.action}] {event.client_ip} ({event.country})")

@watcher.on_error
async def handle_error(error: Exception) -> None:
    print(f"Cloudflare polling failed: {error}")

asyncio.run(watcher.start())
```

Both packages support multiple handlers. Each handler runs for every event; an exception in one is reported to the error handlers and does not stop the others.

## Configuration

| Option | TypeScript | Python | Default | Description |
|---|---|---|---|---|
| API token | `apiToken` | `api_token` | — | Recommended authentication |
| API key | `apiKey` | `api_key` | — | Legacy Global API Key, requires `email` |
| Email | `email` | `email` | — | Required with the API key |
| Zone IDs | `zoneIds` | `zone_ids` | required | Zones to watch (32 hex characters each) |
| Poll interval | `pollInterval` | `poll_interval` | `60` | Seconds between polls |
| Lookback | `lookbackMinutes` | `lookback_minutes` | `15` | Minutes read on first start (TS: max 44640 = 31 days) |
| Overlap | `overlap` | — | `300` | Seconds re-read each poll to catch late events |
| Page size | `pageSize` | — | `1000` | Events per zone and page |
| Request timeout | `requestTimeout` | — | `15` | Seconds per request |
| Retries | `maxRetries` | — | `3` | Retries on network errors, timeouts, 429 and 5xx |
| Custom fetch | `fetch` | — | global `fetch` | For proxies or tests |
| TLS verification | — | `verify_ssl` | `true` | Python only; never disable in production |

The TypeScript constructor validates every option and throws on invalid values.

## Event fields

| Field | TypeScript | Python | Example |
|---|---|---|---|
| Zone ID | `zoneId` | `zone_id` | `"023e105f4ecef8ad9ca31a8372d0c353"` |
| Zone name | `zoneName` | `zone_name` | `"example.com"` |
| Action | `action` | `action` | `"block"`, `"managed_challenge"`, `"log"` |
| Source | `source` | `source` | `"firewallManaged"`, `"ratelimit"`, `"bic"` |
| Client IP | `clientIp` | `client_ip` | `"203.0.113.5"` |
| Country | `country` | `country` | `"DE"` |
| Rule ID | `ruleId` | `rule_id` | `"5de7edfa648c4d6891dc3e7f84534ffa"` |
| Rule description | `ruleMessage` | `rule_message` | `"SQLi - Comment"` |
| Ray ID | `rayId` | `ray_id` | `"8d1f2a3b4c5d6e7f"` |
| Host | `host` | — | `"shop.example.com"` |
| Method | `method` | — | `"POST"` |
| Path | `path` | — | `"/wp-login.php"` |
| Query | `query` | — | `"?id=1%27"` |
| User agent | `userAgent` | — | `"curl/8.5.0"` |
| ASN | `asn` | — | `"64496"` |
| Time | `occurredAt` | `occurred_at` | `Date` / `datetime`, or `null` |
| Raw event | `raw` | `raw` | Original object from Cloudflare |

Fields Cloudflare does not return for your plan are empty strings. `path`, `query` and `userAgent` come from the attacker: escape them before rendering them anywhere.

## How it works

### TypeScript

1. On start, zone names are resolved and the GraphQL schema is introspected once, so the query only asks for fields your account exposes.
2. Every `pollInterval` seconds, one GraphQL request covers up to 10 zones (`firewallEventsAdaptive`, oldest first). An error for one zone doesn't affect the others.
3. A full page continues from its newest timestamp until the window is read completely.
4. Each poll starts `overlap` seconds before the end of the previous window, to pick up events Cloudflare ingests late. Events already dispatched are skipped by a key of Ray ID, rule, source, action, time and IP.
5. Requests time out after `requestTimeout` seconds. Network errors, timeouts, 429 and 5xx responses are retried with exponential backoff, honouring `Retry-After`.
6. `await watcher.stop()` cancels in-flight requests and the wait between polls.

State lives in memory. After a restart the watcher reads the last `lookbackMinutes` again, so handlers should tolerate seeing an event twice across restarts.

### Python

The Python package tries `GET /zones/{id}/security/events`, then `GET /zones/{id}/firewall/events`, then the GraphQL API, and uses the first that answers. It tracks the newest event time per zone in memory.

## Security

- Use a scoped API token with read-only permissions, limited to the zones you watch. Avoid the Global API Key.
- Keep credentials in environment variables or a secrets manager, never in source code or client-side bundles.
- The libraries never log credentials. Error messages contain endpoints, HTTP status codes and Cloudflare's error messages.
- Event data contains personal data (IP addresses, user agents). Handle it according to the privacy laws that apply to you.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Documentation

| Document | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | Token setup, environment variables, running as a service, troubleshooting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, tests, commit conventions |
| [SECURITY.md](SECURITY.md) | Supported versions and how to report vulnerabilities |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [RELEASE.md](RELEASE.md) | How releases are published (maintainers) |
| [packages/npm](packages/npm/README.md) | npm package README |
| [packages/python](packages/python/README.md) | Python package README |

## License

[MIT](LICENSE) © 2026 Maggi
