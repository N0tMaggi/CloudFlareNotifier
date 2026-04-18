"""Internal Cloudflare API client. Not part of the public API."""
from __future__ import annotations

import datetime
import logging
import warnings

import aiohttp

logger = logging.getLogger(__name__)


class CloudflareConnectionManager:
    """Async context manager that wraps an aiohttp session.

    Tries the REST security/events and firewall/events endpoints in order,
    then falls back to the GraphQL analytics API so the library works across
    all Cloudflare plans.
    """

    def __init__(
        self,
        api_token: str | None = None,
        api_key: str | None = None,
        email: str | None = None,
        verify_ssl: bool = True,
        timeout: int = 15,
    ) -> None:
        if not verify_ssl:
            warnings.warn(
                "verify_ssl=False disables TLS certificate verification. "
                "Do not use this in production.",
                stacklevel=2,
            )
        self.api_token = api_token
        self.api_key = api_key
        self.email = email
        self.verify_ssl = verify_ssl
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.graphql_url = f"{self.base_url}/graphql"
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: aiohttp.ClientSession | None = None
        self._zone_cache: dict[str, str] = {}

    async def __aenter__(self) -> CloudflareConnectionManager:
        await self._start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _start(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        elif self.api_key and self.email:
            headers["X-Auth-Key"] = self.api_key
            headers["X-Auth-Email"] = self.email
        return headers

    async def fetch_security_events(
        self,
        zone_id: str,
        since: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, object]] | None:
        """Return a list of raw event dicts, or None on unrecoverable error."""
        await self._start()
        params: dict[str, str | int] = {"per_page": per_page, "page": 1}
        if since:
            params["since"] = since

        for path in (
            f"/zones/{zone_id}/security/events",
            f"/zones/{zone_id}/firewall/events",
        ):
            url = f"{self.base_url}{path}"
            try:
                async with self.session.get(  # type: ignore[union-attr]
                    url, headers=self._headers(), params=params, ssl=self.verify_ssl
                ) as resp:
                    payload = await resp.json(content_type=None)
                    if resp.status == 404:
                        continue
                    if any(e.get("code") in (7000, 7003) for e in payload.get("errors", [])):
                        continue
                    if resp.status != 200 or not payload.get("success", False):
                        logger.warning(
                            "Cloudflare API error [%s] for zone %s via %s: %s",
                            resp.status, zone_id, path, payload.get("errors"),
                        )
                        continue
                    return self._extract_events(payload.get("result"))
            except Exception as exc:
                logger.warning("Request failed for zone %s via %s: %s", zone_id, path, exc)

        return await self._fetch_graphql(zone_id, since=since, limit=per_page)

    async def _fetch_graphql(
        self,
        zone_id: str,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]] | None:
        await self._start()
        if not since:
            since = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=60)
            ).isoformat().replace("+00:00", "Z")

        query = """
        query($zone: String!, $limit: Int!, $since: Time!) {
          viewer {
            zones(filter: { zoneTag: $zone }) {
              firewallEventsAdaptive(
                limit: $limit
                orderBy: [datetime_DESC]
                filter: { datetime_geq: $since }
              ) {
                action source clientIP clientCountryName
                ruleId ruleMessage rayName datetime
              }
            }
          }
        }
        """
        try:
            async with self.session.post(  # type: ignore[union-attr]
                self.graphql_url,
                json={
                    "query": query,
                    "variables": {"zone": zone_id, "limit": limit, "since": since},
                },
                headers=self._headers(),
                ssl=self.verify_ssl,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or data.get("errors"):
                    logger.error(
                        "GraphQL error [%s] for zone %s: %s",
                        resp.status, zone_id, data.get("errors"),
                    )
                    return None
                events = (
                    data.get("data", {})
                    .get("viewer", {})
                    .get("zones", [{}])[0]
                    .get("firewallEventsAdaptive", [])
                ) or []
                return [
                    {
                        "action": ev.get("action"),
                        "source": ev.get("source"),
                        "client_ip": ev.get("clientIP"),
                        "client_country_name": ev.get("clientCountryName"),
                        "rule_id": ev.get("ruleId"),
                        "rule_message": ev.get("ruleMessage") or "",
                        "ray_id": ev.get("rayName"),
                        "datetime": ev.get("datetime"),
                    }
                    for ev in events
                ]
        except Exception as exc:
            logger.error("GraphQL request failed for zone %s: %s", zone_id, exc)
            return None

    async def fetch_zone_name(self, zone_id: str) -> str:
        """Resolve and cache the human-readable zone name."""
        if zone_id in self._zone_cache:
            return self._zone_cache[zone_id]
        await self._start()
        try:
            async with self.session.get(  # type: ignore[union-attr]
                f"{self.base_url}/zones/{zone_id}",
                headers=self._headers(),
                ssl=self.verify_ssl,
            ) as resp:
                payload = await resp.json(content_type=None)
                name = (
                    payload.get("result", {}).get("name", zone_id)
                    if payload.get("success")
                    else zone_id
                )
        except Exception:
            name = zone_id
        self._zone_cache[zone_id] = name
        return name

    @staticmethod
    def _extract_events(result: object) -> list[dict[str, object]]:
        if not result:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("security_events", "events", "result"):
                if isinstance(result.get(key), list):
                    return [dict(e) for e in result[key]]
        return []
