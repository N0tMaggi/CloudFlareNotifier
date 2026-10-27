# @maggidev/cloudflare-notifier

Poll Cloudflare security events from Node.js or TypeScript apps. Register a handler, get called on every new event, and decide what to do next.

## Install

```bash
npm install @maggidev/cloudflare-notifier
```

Requires Node.js 18 or newer. The package has no runtime dependencies.

## Usage

```typescript
import { CloudFlareWatcher, SecurityEvent } from "@maggidev/cloudflare-notifier";

const watcher = new CloudFlareWatcher({
  apiToken: process.env.CF_API_TOKEN!,
  zoneIds: ["your_zone_id"],
  pollInterval: 60,
  lookbackMinutes: 15,
});

watcher.onEvent((event: SecurityEvent) => {
  console.log(`${event.zoneName}: [${event.action}] ${event.clientIp} (${event.country})`);
  console.log(`rule: ${event.ruleMessage || event.ruleId}`);
  console.log(`ray: ${event.rayId}`);
});

watcher.onError((error) => {
  console.error("Cloudflare polling failed:", error);
});

watcher.start();
```

Stop the watcher when needed. This cancels in-flight requests and resolves once polling has exited:

```typescript
await watcher.stop();
```

Run it server-side only (Node.js backend, API route, worker). Never ship your API token to a browser.

## API

`CloudFlareWatcher` accepts:

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `apiToken` | `string` | required unless using `apiKey` | Recommended Cloudflare API token |
| `apiKey` | `string` | required unless using `apiToken` | Legacy Global API Key |
| `email` | `string` | required with `apiKey` | Cloudflare account email |
| `zoneIds` | `string[]` | required | Cloudflare zone IDs to poll |
| `pollInterval` | `number` | `60` | Seconds between polls |
| `lookbackMinutes` | `number` | `15` | Initial lookback window (max 44640 = 31 days) |
| `overlap` | `number` | `300` | Seconds re-read each poll to catch late-ingested events; duplicates are skipped |
| `pageSize` | `number` | `1000` | Events per zone and page |
| `requestTimeout` | `number` | `15` | Seconds per request |
| `maxRetries` | `number` | `3` | Retries on network errors, timeouts, 429 and 5xx |
| `fetch` | `typeof fetch` | global `fetch` | Custom fetch implementation |

Zone IDs must be 32 hex characters; invalid options throw in the constructor.

`SecurityEvent` contains `zoneId`, `zoneName`, `action`, `source`, `clientIp`, `country`, `ruleId`, `ruleMessage`, `rayId`, `host`, `method`, `path`, `query`, `userAgent`, `asn`, `occurredAt`, and `raw` (the original GraphQL object). Fields Cloudflare does not expose are empty strings. `path`, `query` and `userAgent` are attacker-controlled: escape them before rendering.

Errors passed to `onError` are usually a `CloudflareApiError` (exported) with `status`, `endpoint` and Cloudflare's `errors`.

## How it works

Events are read from the GraphQL Analytics API (`firewallEventsAdaptive`):

- Up to 10 zones per request; an error for one zone does not affect the others.
- Oldest first, paginated, so bursts larger than one page are not lost.
- Each poll re-reads the last `overlap` seconds and skips events already dispatched.
- On first use the schema is introspected so only available fields are requested.
- Every request has a timeout and is retried with exponential backoff (honouring `Retry-After`).

## Security

Use a scoped Cloudflare API token with read-only permissions:

- `Zone -> Zone -> Read` for zone lookup
- `Zone -> Analytics -> Read` for security events via GraphQL

Scope the token to only the zones/accounts you need. Do not commit credentials; pass them through environment variables or a secrets manager.

## Repository

Source and Python package: https://github.com/N0tMaggi/CloudFlareNotifier
