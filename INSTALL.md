# Install & Setup

## Prerequisites
- Windows 10/11
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

## First run (creates config)
```powershell
python src/main.py
```
- If `%APPDATA%/CloudFlareNotifier/config.cfg` does not exist, the app writes a template, tries to open it in your default editor, and exits with a message.

## Configure
Edit `%APPDATA%/CloudFlareNotifier/config.cfg`:
```
[cloudflare]
api_token = YOUR_API_TOKEN          # or leave blank if using api_key + email
api_key =                           # only if using the legacy key
email =                             # account email, only for api_key flow
zone_ids = zone1,zone2              # comma-separated zone IDs
poll_interval = 60                  # seconds between polls
lookback_minutes = 15               # initial window on first run
verify_ssl = true
```

## Run continuously
```powershell
python src/main.py
```
Logs: `%APPDATA%/CloudFlareNotifier/logs/app.log`

## Optional: run on login (schtasks)
```powershell
schtasks /Create /TN "CloudFlareNotifier" /TR "\"C:\\Program Files\\Python311\\python.exe\" \"C:\\path\\to\\CloudFlareNotifier\\src\\main.py\"" /SC ONLOGON /RL HIGHEST
```
Adjust the Python and project paths to your system. Remove with `schtasks /Delete /TN "CloudFlareNotifier" /F`.

## Build a one-file EXE
```powershell
BUILD.bat
```
Output: `dist/CloudFlareNotifier.exe` (no console window).

## Update dependencies
```powershell
python -m pip install --upgrade -r requirements.txt
```

## Troubleshooting
- **Missing config**: run once; the template is created and opened automatically.
- **Credential errors**: ensure `api_token` or (`api_key` + `email`) is set, not both blank.
- **No notifications**: check `app.log` for API errors; confirm `zone_ids` are correct; increase `lookback_minutes` when testing to capture recent events.
- **Duplicate or stale alerts**: delete `%APPDATA%/CloudFlareNotifier/state.json` to reset seen timestamps.
