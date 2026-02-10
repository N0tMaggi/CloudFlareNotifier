# Install & Setup

## Prerequisites
- Python 3.10+ on PATH (`python --version` to check)
- Cloudflare account with access to the zones you want to monitor
- API token (recommended) or Global API key + account email

## Create a Cloudflare API token (recommended)
1) Log in to the Cloudflare dashboard.  
2) Top-right avatar -> **My Profile** -> **API Tokens** -> **Create Token** -> **Custom token**.  
3) Add permission: `Account -> Account Analytics -> Read`.  
4) Resources: select your account; add each zone you want (or all zones).  
5) Create and copy the token (shown once).

## Find your zone IDs
For each site: dashboard -> **Overview** -> copy the **Zone ID** in the right column.

## Install dependencies
```powershell
python -m pip install -r requirements.txt
```

## Linux service installer (systemd)
```bash
sudo ./install.sh
```
This will create a virtual environment, install dependencies, generate a systemd service, and start it.
Logs: `journalctl -u cloudflarenotifier -f`

## Service commands (systemd)
```bash
sudo systemctl status cloudflarenotifier
sudo systemctl start cloudflarenotifier
sudo systemctl stop cloudflarenotifier
sudo systemctl restart cloudflarenotifier
sudo systemctl enable cloudflarenotifier
sudo systemctl disable cloudflarenotifier
journalctl -u cloudflarenotifier -f
```

## First run (creates config)
```powershell
python src/main.py
```
- If `.env` does not exist, the app writes a template in the project folder and exits with a message.

## Configure
Edit `.env`:
```
CLOUDFLARE_API_TOKEN=               # or leave blank if using api_key + email
CLOUDFLARE_API_KEY=                 # only if using the legacy key
CLOUDFLARE_EMAIL=                   # account email, only for api_key flow
CLOUDFLARE_ZONE_IDS=zone1,zone2     # comma-separated zone IDs
POLL_INTERVAL=60                    # seconds between polls
LOOKBACK_MINUTES=15                 # initial window on first run
VERIFY_SSL=true

WEBHOOK_URL=https://discord.com/api/webhooks/...
NO_WINDOWS_SERVER=true             # disable toast import on non-Windows servers
SEND_WINDOWS_TOAST=true             # only relevant on Windows
```

## Run continuously
```powershell
python src/main.py
```
Logs: `logs/app.log`

## Optional: run on login (Windows schtasks)
```powershell
schtasks /Create /TN "CloudFlareNotifier" /TR "\"C:\\Program Files\\Python311\\python.exe\" \"C:\\path\\to\\CloudFlareNotifier\\src\\main.py\"" /SC ONLOGON /RL HIGHEST
```
Adjust the Python and project paths to your system. Remove with `schtasks /Delete /TN "CloudFlareNotifier" /F`.

## Update dependencies
```powershell
python -m pip install --upgrade -r requirements.txt
```

## Troubleshooting
- **Missing config**: run once; the template is created automatically.
- **Credential errors**: ensure `api_token` or (`api_key` + `email`) is set, not both blank.
- **No notifications**: check `logs/app.log` for API errors; confirm `zone_ids` are correct; increase `lookback_minutes` when testing to capture recent events.
- **Duplicate or stale alerts**: delete `state.json` to reset seen timestamps.
