from modules.importHandler import aiohttp, sys
from modules.loggingHandler import logger


class NotificationManager:
    def __init__(self, config):
        self.config = config
        self.webhook_url = (config.get("webhook_url") or "").strip()
        self.no_windows_server = bool(config.get("no_windows_server", False))
        self.send_windows_toast = bool(config.get("send_windows_toast", True))
        self.toast_available = False
        self.toaster = None
        self.session = None
        self._warned_no_dest = False

    async def start(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        self._init_windows_toast()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _init_windows_toast(self):
        if self.no_windows_server or not self.send_windows_toast:
            return
        if sys.platform != "win32":
            return
        try:
            import windows_toasts

            self.toaster = windows_toasts.WindowsToaster("Cloudflare Notifier")
            self.toast_available = True
        except Exception as exc:
            logger.warning("Windows toast unavailable: %s", exc)
            self.toast_available = False

    async def send_notification(self, title, message, embed=None):
        if not self.webhook_url and not self.toast_available:
            if not self._warned_no_dest:
                logger.warning("No webhook configured and toast unavailable. Notifications will be dropped.")
                self._warned_no_dest = True
            return
        await self._send_webhook(embed or self._build_simple_embed(title, message))
        self._send_toast(title, message)

    async def _send_webhook(self, embed):
        if not self.webhook_url:
            return
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        payload = {"embeds": [embed]}
        try:
            async with self.session.post(self.webhook_url, json=payload) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Webhook error {resp.status}: {text[:200]}")
                logger.info("Notification sent: %s", embed.get("title", "Cloudflare event"))
        except Exception as exc:
            logger.error("Failed to send webhook notification: %s", exc)

    def _send_toast(self, title, message):
        if not self.toast_available or not self.toaster:
            return
        try:
            import windows_toasts

            new_toast = windows_toasts.Toast()
            new_toast.text_fields = [title, message]
            self.toaster.show_toast(new_toast)
        except Exception as exc:
            logger.error("Failed to send toast: %s", exc)

    @staticmethod
    def _build_simple_embed(title, message):
        return {
            "title": title,
            "description": message,
            "color": 15105570,
        }
