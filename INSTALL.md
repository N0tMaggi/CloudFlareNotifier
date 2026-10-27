# Installation and setup

This guide takes you from zero to a watcher that runs permanently on a server.

1. [Requirements](#1-requirements)
2. [Install the package](#2-install-the-package)
3. [Create a Cloudflare API token](#3-create-a-cloudflare-api-token)
4. [Find your zone IDs](#4-find-your-zone-ids)
5. [Configure environment variables](#5-configure-environment-variables)
6. [Write and run a watcher](#6-write-and-run-a-watcher)
7. [Run it as a service](#7-run-it-as-a-service)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Requirements

| | Node.js package | Python package |
|---|---|---|
| Runtime | Node.js **22.12** or newer | Python **3.10** or newer |
| Dependencies | none | `aiohttp` (installed automatically) |
| Network | outbound HTTPS to `api.cloudflare.com` | same |

Any Cloudflare plan works. The amount of event detail and how far back you can read depend on your plan.

## 2. Install the package

**Node.js**

```bash
npm install @maggidev/cloudflare-notifier
```

**Python** (not on PyPI yet; installs from GitHub)

```bash
pip install "git+https://github.com/N0tMaggi/CloudFlareNotifier.git#subdirectory=packages/python"
```

Use a virtual environment (`python -m venv .venv`) so the package doesn't end up in your system Python.

## 3. Create a Cloudflare API token

1. Open the Cloudflare dashboard → **My Profile** → **API Tokens** → **Create Token**.
2. Choose **Create Custom Token**.
3. Add these permissions:

   | Scope | Resource | Access |
   |---|---|---|
   | Zone | Zone | Read |
   | Zone | Analytics | Read |

4. Under **Zone Resources**, include only the zones you want to watch.
5. Optional but recommended: restrict **Client IP Address Filtering** to your server's IP and set a **TTL**.
6. Create the token and copy it. Cloudflare shows it only once.

Check that it works:

```bash
curl -s https://api.cloudflare.com/client/v4/user/tokens/verify -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"
```

The response should contain `"status": "active"`.

> The legacy Global API Key (`apiKey` + `email`) also works, but it grants full access to your account. Use a scoped token instead.

## 4. Find your zone IDs

Open the zone in the Cloudflare dashboard. On the **Overview** page, the **API** section in the right sidebar shows the **Zone ID**: 32 hexadecimal characters, for example `023e105f4ecef8ad9ca31a8372d0c353`.

## 5. Configure environment variables

Keep credentials out of your source code. A `.env` file next to your script is the simplest option:

```dotenv
# .env  (add it to .gitignore, never commit it)
CLOUDFLARE_API_TOKEN=your-token
CLOUDFLARE_ZONE_IDS=023e105f4ecef8ad9ca31a8372d0c353,1f2e3d4c5b6a79880f1e2d3c4b5a6978
```

| Variable | Meaning |
|---|---|
| `CLOUDFLARE_API_TOKEN` | The token from step 3 |
| `CLOUDFLARE_ZONE_IDS` | Comma-separated zone IDs from step 4 |

The libraries don't read environment variables themselves; your script passes them in (see below). That keeps configuration explicit and works the same in every environment. The names above follow Cloudflare's own tooling (Wrangler uses `CLOUDFLARE_API_TOKEN`).

Loading the file:

- **Node.js:** `node --env-file=.env watch.mjs` (built in, no package needed)
- **Python:** `pip install python-dotenv`, then `from dotenv import load_dotenv; load_dotenv()` at the top of your script
- **systemd / Docker:** pass the file directly (`EnvironmentFile=` / `--env-file`), see step 7

## 6. Write and run a watcher

**Node.js**: `watch.mjs`

```js
import { CloudFlareWatcher } from "@maggidev/cloudflare-notifier";

const watcher = new CloudFlareWatcher({
  apiToken: process.env.CLOUDFLARE_API_TOKEN,
  zoneIds: process.env.CLOUDFLARE_ZONE_IDS.split(","),
});

watcher.onEvent((event) => {
  console.log(JSON.stringify({
    time: event.occurredAt,
    zone: event.zoneName,
    action: event.action,
    ip: event.clientIp,
    country: event.country,
    path: event.path,
    rule: event.ruleMessage || event.ruleId,
  }));
});

watcher.onError((error) => console.error("cloudflare-notifier:", error.message));

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => void watcher.stop());
}

await watcher.start();
```

```bash
node --env-file=.env watch.mjs
```

**Python**: `watch.py`

```python
import asyncio
import os
import signal

from cloudflare_notifier import CloudFlareWatcher, SecurityEvent

watcher = CloudFlareWatcher(
    api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    zone_ids=os.environ["CLOUDFLARE_ZONE_IDS"].split(","),
)

@watcher.on_event
async def handle(event: SecurityEvent) -> None:
    print(f"{event.occurred_at} {event.zone_name} [{event.action}] {event.client_ip} {event.rule_message or event.rule_id}")

@watcher.on_error
async def handle_error(error: Exception) -> None:
    print(f"cloudflare-notifier: {error}")

async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(watcher.stop()))
    await watcher.start()

asyncio.run(main())
```

```bash
python watch.py
```

`loop.add_signal_handler` isn't available on Windows; there, stop with Ctrl+C.

Within a minute or two you should see events, provided your zones had security events in the last 15 minutes (the default lookback). The dashboard's **Security → Events** page shows whether there were any.

## 7. Run it as a service

### systemd (Linux)

`/etc/systemd/system/cloudflare-notifier.service`:

```ini
[Unit]
Description=Cloudflare security event watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cfwatch
WorkingDirectory=/opt/cloudflare-notifier
EnvironmentFile=/opt/cloudflare-notifier/.env
ExecStart=/usr/bin/node /opt/cloudflare-notifier/watch.mjs
# Python: ExecStart=/opt/cloudflare-notifier/.venv/bin/python /opt/cloudflare-notifier/watch.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --no-create-home cfwatch
sudo chmod 600 /opt/cloudflare-notifier/.env
sudo chown cfwatch: /opt/cloudflare-notifier/.env
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflare-notifier
journalctl -u cloudflare-notifier -f
```

### Docker

`Dockerfile` for the Node.js example:

```dockerfile
FROM node:24-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY watch.mjs ./
USER node
CMD ["node", "watch.mjs"]
```

```bash
docker build -t cloudflare-notifier .
docker run -d --name cloudflare-notifier --restart unless-stopped --env-file .env cloudflare-notifier
```

`docker stop` sends `SIGTERM`, which the example handles with a clean `watcher.stop()`.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `HTTP 403` / `[10000] Authentication error` | The token lacks **Zone → Analytics → Read**, or the zone is not in its **Zone Resources**. Edit the token in the dashboard. |
| `Invalid zoneId(s)` (Node.js) | A zone ID is not 32 hex characters. Check for spaces or a trailing comma in `CLOUDFLARE_ZONE_IDS`. |
| Zone shows up as its ID instead of its name | The token lacks **Zone → Zone → Read**. Events still work. |
| No events at all | Check **Security → Events** in the dashboard for the same time range. Raise `lookbackMinutes` to see older events on first start. |
| `HTTP 429` errors | Cloudflare allows 300 GraphQL queries per 5 minutes. Raise `pollInterval`, or watch fewer zones per token. Node.js retries automatically. |
| `cannot request data older than …` | `lookbackMinutes` goes beyond what your plan retains. Lower it. |
| `more than … events share one timestamp` | Raise `pageSize` (Node.js). |
| `host`, `path`, `userAgent` are empty | Your plan or token doesn't expose these fields. The watcher requests only fields the API offers. |

Still stuck? [Open an issue](https://github.com/N0tMaggi/CloudFlareNotifier/issues) with the error message. Remove tokens, zone IDs and IP addresses first.
