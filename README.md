# cloudflare-notifier

[![PyPI](https://img.shields.io/pypi/v/cloudflare-notifier?label=PyPI)](https://pypi.org/project/cloudflare-notifier/)
[![Python](https://img.shields.io/pypi/pyversions/cloudflare-notifier)](https://pypi.org/project/cloudflare-notifier/)
[![npm](https://img.shields.io/npm/v/%40maggidev%2Fcloudflare-notifier?label=npm)](https://www.npmjs.com/package/@maggidev/cloudflare-notifier)
[![npm downloads](https://img.shields.io/npm/dm/%40maggidev%2Fcloudflare-notifier)](https://www.npmjs.com/package/@maggidev/cloudflare-notifier)
[![CI](https://img.shields.io/github/actions/workflow/status/N0tMaggi/CloudFlareNotifier/pip-audit.yml?label=security+audit)](https://github.com/N0tMaggi/CloudFlareNotifier/actions)
[![License](https://img.shields.io/github/license/N0tMaggi/CloudFlareNotifier)](LICENSE)

Poll Cloudflare security events in Python or Node.js. Register a handler, get called on every new event. No built-in notifications, no opinions on what you do next.

---

## The problem

Cloudflare doesn't push security events — you have to poll. Doing this yourself means:

- Three different API endpoints depending on your plan (`/security/events`, `/firewall/events`, GraphQL `firewallEventsAdaptive`)
- Inconsistent field names between REST and GraphQL responses
- Deduplication logic to avoid re-processing events across restarts
- Timestamp normalization across different Cloudflare event formats

This library handles all of that. You write the handler.

---

## Install

**Python** (requires 3.10+, one dependency: `aiohttp`):
```bash
pip install cloudflare-notifier
```

**Node.js** (requires 18+, zero runtime dependencies):
```bash
npm install @maggidev/cloudflare-notifier
```

---

## Usage

### Python

```python
import asyncio
import os
from cloudflare_notifier import CloudFlareWatcher, SecurityEvent

watcher = CloudFlareWatcher(
    api_token=os.environ["CF_API_TOKEN"],
    zone_ids=["your_zone_id"],
    poll_interval=60,        # seconds between polls (default: 60)
    lookback_minutes=15,     # how far back to look on first start (default: 15)
)

@watcher.on_event
async def handle(event: SecurityEvent) -> None:
    print(f"{event.zone_name}: [{event.action}] {event.client_ip} ({event.country})")
    print(f"  rule: {event.rule_message or event.rule_id}")
    print(f"  ray:  {event.ray_id}")

@watcher.on_error
async def handle_error(error: Exception) -> None:
    print(f"Cloudflare polling failed: {error}")

asyncio.run(watcher.start())
```

Multiple handlers and multiple zones are both supported:

```python
watcher = CloudFlareWatcher(
    api_token=os.environ["CF_API_TOKEN"],
    zone_ids=["zone_id_1", "zone_id_2"],
)

@watcher.on_event
async def log_to_db(event: SecurityEvent) -> None:
    await db.insert(event.raw)

@watcher.on_event
async def alert_on_block(event: SecurityEvent) -> None:
    if event.action == "block":
        await send_alert(event)
```

### Node.js / TypeScript

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
    console.log(`  rule: ${event.ruleMessage || event.ruleId}`);
    console.log(`  ray:  ${event.rayId}`);
});

watcher.start();
```

Stop when needed:

```typescript
// stop after 10 minutes
setTimeout(() => watcher.stop(), 10 * 60 * 1000);
```

---

## API Reference

### `CloudFlareWatcher`

| Parameter | Python | TypeScript | Default | Description |
|-----------|--------|-----------|---------|-------------|
| API token | `api_token` | `apiToken` | — | Recommended auth method |
| API key | `api_key` | `apiKey` | — | Legacy — requires `email` |
| Email | `email` | `email` | — | Required with `api_key` |
| Zone IDs | `zone_ids` | `zoneIds` | required | List of Cloudflare zone IDs |
| Poll interval | `poll_interval` | `pollInterval` | `60` | Seconds between polls |
| Lookback | `lookback_minutes` | `lookbackMinutes` | `15` | Window on first start |
| SSL verify | `verify_ssl` | — | `true` | Python only — see [Security](#security) |

### `SecurityEvent` fields

| Field | Python | TypeScript | Example |
|-------|--------|-----------|---------|
| Zone ID | `zone_id` | `zoneId` | `"abc123def456"` |
| Zone name | `zone_name` | `zoneName` | `"example.com"` |
| Action | `action` | `action` | `"block"`, `"challenge"`, `"log"` |
| Source | `source` | `source` | `"firewall"`, `"waf"`, `"rateLimit"` |
| Client IP | `client_ip` | `clientIp` | `"203.0.113.5"` |
| Country | `country` | `country` | `"DE"` |
| Rule ID | `rule_id` | `ruleId` | `"..."` |
| Rule message | `rule_message` | `ruleMessage` | `"SQLi detected"` ¹ |
| Ray ID | `ray_id` | `rayId` | `"6e4d7f0abc123456"` |
| Timestamp | `occurred_at` | `occurredAt` | `datetime` / `Date \| null` |
| Raw event | `raw` | `raw` | original dict / object from Cloudflare |

Fields may be empty strings when Cloudflare omits them — always check before using.

¹ `rule_message` / `ruleMessage` is only populated on **Enterprise** plans. The library auto-detects this per zone: it first requests the field, and if Cloudflare rejects it, retries without — no configuration needed. The field will simply be an empty string on Free/Pro/Business zones.

---

## Auth

Create a token at **Cloudflare dashboard → My Profile → API Tokens → Create Token → Custom token**.

Recommended read-only permissions:

- `Zone → Zone → Read` for zone lookup
- `Account → Account Analytics → Read` for GraphQL security event fallback

Scope the token to only the zones/accounts you need.

The legacy Global API Key (`api_key` + `email`) works but grants full account access — prefer a scoped token.

---

## Security

**Keep credentials out of source code.** Use environment variables or a secrets manager:

```python
# Python
api_token=os.environ["CF_API_TOKEN"]
```
```typescript
// TypeScript
apiToken: process.env.CF_API_TOKEN!
```

**Never set `verify_ssl=False` in production** (Python only). It disables TLS certificate verification entirely and makes your traffic vulnerable to MITM attacks. The library will emit a `UserWarning` if you do.

**The library does not log credentials.** Exceptions from failed requests are logged at WARNING level via the standard `logging` module — they contain zone IDs and HTTP status codes, not tokens or keys.

**Event data may contain personal information** (IP addresses, user agents). Handle it according to the privacy laws that apply to your users.

---

## How it works

Both packages try Cloudflare's endpoints in this order, stopping at the first success:

```
1. GET /zones/{id}/security/events      (REST — newer plans)
2. GET /zones/{id}/firewall/events      (REST — older plans)
3. POST /graphql  firewallEventsAdaptive (GraphQL — all plans)
```

GraphQL field names are normalized to match REST field names before they reach your handler, so `SecurityEvent` always has the same shape regardless of which endpoint responded.

The GraphQL query adapts automatically per zone: `ruleMessage` is requested if the zone supports it (Enterprise), and silently dropped for zones that don't. This is detected on the first poll and cached for the lifetime of the watcher instance.

Deduplication is in-memory per watcher instance using the `occurred_at` timestamp of the last seen event. State is not persisted — on restart, the watcher fetches events from the last `lookback_minutes` window.

---

## Development

```bash
# Python
cd packages/python
pip install -e ".[dev]"
python -m pytest tests/ -v

# TypeScript
cd packages/npm
npm install
npm run build
```

Python tests cover `CloudFlareWatcher` construction, event handler registration, timestamp parsing, event mapping, dispatch error isolation, and the internal API client. Run them before submitting changes.
