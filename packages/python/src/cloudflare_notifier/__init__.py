"""cloudflare-notifier — poll Cloudflare security events and react to them."""

from cloudflare_notifier._models import SecurityEvent
from cloudflare_notifier.watcher import CloudFlareWatcher

__all__ = ["CloudFlareWatcher", "SecurityEvent"]
__version__ = "0.1.0"
