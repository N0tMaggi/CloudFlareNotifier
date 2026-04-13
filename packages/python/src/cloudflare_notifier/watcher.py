from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable

from cloudflare_notifier._connection import CloudflareConnectionManager
from cloudflare_notifier._models import SecurityEvent

logger = logging.getLogger(__name__)

_Handler = Callable[[SecurityEvent], Awaitable[None]]
_ErrorHandler = Callable[[Exception], Awaitable[None]]


class CloudFlareWatcher:
    """Poll Cloudflare security events and dispatch them to registered handlers.

    Basic usage::

        import asyncio
        from cloudflare_notifier import CloudFlareWatcher

        watcher = CloudFlareWatcher(
            api_token="YOUR_TOKEN",
            zone_ids=["zone_id_1"],
        )

        @watcher.on_event
        async def handle(event):
            print(event.action, event.client_ip)

        asyncio.run(watcher.start())
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        api_key: str | None = None,
        email: str | None = None,
        zone_ids: list[str],
        poll_interval: int = 60,
        lookback_minutes: int = 15,
        verify_ssl: bool = True,
    ) -> None:
        if not api_token and not (api_key and email):
            raise ValueError("Provide api_token or both api_key and email.")
        if not zone_ids:
            raise ValueError("Provide at least one zone_id.")

        self._api_token = api_token
        self._api_key = api_key
        self._email = email
        self._zone_ids = list(zone_ids)
        self._poll_interval = poll_interval
        self._lookback_minutes = lookback_minutes
        self._verify_ssl = verify_ssl

        self._handlers: list[_Handler] = []
        self._error_handlers: list[_ErrorHandler] = []
        self._last_seen: dict[str, datetime.datetime | None] = {}
        self._running = False
        self._stop_event: asyncio.Event | None = None

    def on_event(self, func: _Handler) -> _Handler:
        """Register an async handler for every new security event.

        Can be used as a decorator or called directly::

            @watcher.on_event
            async def handle(event: SecurityEvent) -> None: ...

            # or
            watcher.on_event(my_async_handler)
        """
        self._handlers.append(func)
        return func

    def on_error(self, func: _ErrorHandler) -> _ErrorHandler:
        """Register an async handler for polling and event handler errors."""
        self._error_handlers.append(func)
        return func

    async def start(self) -> None:
        """Start polling. Blocks until :meth:`stop` is called or the task is cancelled."""
        self._running = True
        self._stop_event = asyncio.Event()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=self._lookback_minutes
        )

        try:
            async with CloudflareConnectionManager(
                api_token=self._api_token,
                api_key=self._api_key,
                email=self._email,
                verify_ssl=self._verify_ssl,
            ) as client:
                zone_names: dict[str, str] = {}
                for zone_id in self._zone_ids:
                    zone_names[zone_id] = await client.fetch_zone_name(zone_id)
                    self._last_seen.setdefault(zone_id, cutoff)
                    if not self._running:
                        return

                while self._running:
                    await self._poll(client, zone_names)
                    if not self._running:
                        break

                    stop_event = self._stop_event
                    if stop_event is None:
                        break
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval)
                    except TimeoutError:
                        pass
        finally:
            self._running = False
            self._stop_event = None

    async def stop(self) -> None:
        """Signal the polling loop to exit after the current cycle."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()

    async def _poll(
        self,
        client: CloudflareConnectionManager,
        zone_names: dict[str, str],
    ) -> None:
        for zone_id in self._zone_ids:
            if not self._running:
                return
            since = self._last_seen.get(zone_id)
            raw_events = await client.fetch_security_events(
                zone_id, since=self._ts_str(since) if since else None
            )
            if not self._running:
                return
            if raw_events is None:
                await self._dispatch_error(
                    RuntimeError(f"Failed to fetch Cloudflare security events for zone {zone_id}.")
                )
                continue

            new: list[tuple[datetime.datetime | None, dict[str, object]]] = []
            for raw in raw_events:
                ev_ts = self._parse_ts(raw)
                if since and ev_ts and ev_ts <= since:
                    continue
                new.append((ev_ts, raw))

            if not new:
                continue

            new.sort(key=lambda x: x[0] or datetime.datetime.now(datetime.timezone.utc))
            latest = since
            for ev_ts, raw in new:
                event = self._to_event(zone_id, zone_names.get(zone_id, zone_id), raw, ev_ts)
                await self._dispatch(event)
                if ev_ts:
                    latest = ev_ts if latest is None else max(latest, ev_ts)

            if latest:
                self._last_seen[zone_id] = latest

    async def _dispatch(self, event: SecurityEvent) -> None:
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.exception("Event handler raised for ray_id=%s", event.ray_id)
                await self._dispatch_error(exc)

    async def _dispatch_error(self, error: Exception) -> None:
        for handler in self._error_handlers:
            try:
                await handler(error)
            except Exception:
                logger.exception("Error handler raised")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _parse_ts(raw: dict[str, object]) -> datetime.datetime | None:
        for key in ("occurred_at", "datetime", "timestamp", "time"):
            value = raw.get(key)
            if not value:
                continue
            try:
                return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:
                continue
        return None

    @staticmethod
    def _ts_str(ts: datetime.datetime) -> str:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return ts.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _to_event(
        zone_id: str,
        zone_name: str,
        raw: dict[str, object],
        occurred_at: datetime.datetime | None,
    ) -> SecurityEvent:
        return SecurityEvent(
            zone_id=zone_id,
            zone_name=zone_name,
            action=str(raw.get("action") or raw.get("outcome") or ""),
            source=str(raw.get("source") or raw.get("kind") or raw.get("service") or ""),
            client_ip=str(raw.get("client_ip") or raw.get("ip") or ""),
            country=str(raw.get("client_country_name") or raw.get("country") or ""),
            rule_id=str(raw.get("rule_id") or ""),
            rule_message=str(raw.get("rule_message") or ""),
            ray_id=str(raw.get("ray_id") or raw.get("rayid") or ""),
            occurred_at=occurred_at,
            raw=raw,
        )
