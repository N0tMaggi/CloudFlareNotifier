# cloudflare-notifier (Python)

Poll Cloudflare security events from Python and react to them with async handlers.

## Install

Requires Python 3.10 or newer. The package isn't on PyPI yet; install it from GitHub:

```bash
pip install "git+https://github.com/N0tMaggi/CloudFlareNotifier.git#subdirectory=packages/python"
```

## Usage

```python
import asyncio
import os

from cloudflare_notifier import CloudFlareWatcher, SecurityEvent

watcher = CloudFlareWatcher(
    api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    zone_ids=os.environ["CLOUDFLARE_ZONE_IDS"].split(","),
    poll_interval=60,      # seconds between polls
    lookback_minutes=15,   # how far back to read on first start
)

@watcher.on_event
async def handle(event: SecurityEvent) -> None:
    print(f"{event.zone_name}: [{event.action}] {event.client_ip} ({event.country})")

@watcher.on_error
async def handle_error(error: Exception) -> None:
    print(f"Cloudflare polling failed: {error}")

asyncio.run(watcher.start())
```

Call `await watcher.stop()` to end polling; `start()` then returns.

## Documentation

- [Project README](https://github.com/N0tMaggi/CloudFlareNotifier#readme): options, event fields, how it works
- [INSTALL.md](https://github.com/N0tMaggi/CloudFlareNotifier/blob/main/INSTALL.md): API token, environment variables, running as a service
- [CHANGELOG.md](https://github.com/N0tMaggi/CloudFlareNotifier/blob/main/CHANGELOG.md)

## License

MIT
