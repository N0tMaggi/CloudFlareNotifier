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

Stop the watcher when needed:

```typescript
watcher.stop();
```

## API

`CloudFlareWatcher` accepts:

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `apiToken` | `string` | required unless using `apiKey` | Recommended Cloudflare API token |
| `apiKey` | `string` | required unless using `apiToken` | Legacy Global API Key |
| `email` | `string` | required with `apiKey` | Cloudflare account email |
| `zoneIds` | `string[]` | required | Cloudflare zone IDs to poll |
| `pollInterval` | `number` | `60` | Seconds between polls |
| `lookbackMinutes` | `number` | `15` | Initial lookback window |

`SecurityEvent` contains normalized fields such as `zoneId`, `zoneName`, `action`, `source`, `clientIp`, `country`, `ruleId`, `ruleMessage`, `rayId`, `occurredAt`, and `raw`.

## Cloudflare endpoints

The watcher tries these Cloudflare APIs in order and stops at the first successful endpoint for a zone:

1. `GET /zones/{id}/security/events`
2. `GET /zones/{id}/firewall/events`
3. `POST /graphql` with `firewallEventsAdaptive`

GraphQL field names are normalized so your handler receives the same `SecurityEvent` shape across plans.

## Security

Use a scoped Cloudflare API token with read-only permissions:

- `Zone -> Zone -> Read` for zone lookup
- `Account -> Account Analytics -> Read` for GraphQL security event fallback

Scope the token to only the zones/accounts you need. Do not commit credentials; pass them through environment variables or a secrets manager.

## Repository

Source and Python package: https://github.com/N0tMaggi/CloudFlareNotifier
