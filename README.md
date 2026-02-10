# CloudFlareNotifier
[![Cloudflare badge](https://img.shields.io/badge/Cloudflare-Security%20Events-f38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com)
[![Python badge](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)

Cross-platform Python service for Cloudflare security events. It polls Cloudflare's APIs for your zones and surfaces new security events via Discord webhooks and optional Windows toast notifications.

## Why this exists
- Keep personal or small-team sites observable without a full SIEM stack.
- Discord embeds with attack-vector context are easy to share with teams.
- Optional Windows toasts on Windows hosts.
- One `.env` config file and persistent state to prevent duplicate pings.

## Highlights
- Rich embeds: action/outcome, source, client IP, country, rule message, Ray ID, attack-vector description.
- Multiple zones in one process.
- Stateful deduplication via `state.json` in the project folder.
- `.env` template is created on first run.
- Works with Cloudflare API token (preferred) or legacy Global API key.

## Visuals
- **Notification example**: title `example.com: block`; body `Firewall - 203.0.113.5 (DE) | SQLi detected | Ray ID: 6e4d7f0abc123456`.
- **Data flow**:
```mermaid
flowchart LR
    CF[Cloudflare Security Events] -->|API token/key| Client[CloudFlareNotifier]
    Client --> Webhook[Discord Webhook]
    Client --> Toast[Windows Toast UI (optional)]
    Client --> Logs[logs/app.log]
    Client --> State[state.json]
```

## Quick install
Full guide: [INSTALL.md](INSTALL.md). Short version:
```powershell
python -m pip install -r requirements.txt
python src/main.py
```
- First start writes `.env` in the project folder and exits with a message.
- Fill `CLOUDFLARE_API_TOKEN` **or** (`CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL`), set `CLOUDFLARE_ZONE_IDS`, tweak `POLL_INTERVAL`, `LOOKBACK_MINUTES`, `VERIFY_SSL` as needed.
- Set `WEBHOOK_URL` to enable Discord embeds. For non-Windows servers, set `NO_WINDOWS_SERVER=true`.

## Running
```powershell
python src/main.py
```
Logs live at `logs/app.log`.

## What a toast contains
- Title: `<zone name>: <action>`
- Body: `<source> - <client IP> (<country>) | <rule message> | Ray ID: <id>`
- Missing fields in the event are omitted.

## Operational notes
- `lookback_minutes` defines the initial fetch window to avoid alert floods after downtime.
- State is at `state.json`; delete it to force a full refresh.
- No system tray icon: stop with `Ctrl+C` in the console or end the `CloudFlareNotifier` process in Task Manager. Restart with the same command. Config is always at `.env`.
