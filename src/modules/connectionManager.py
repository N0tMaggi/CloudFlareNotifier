from modules.importHandler import aiohttp, datetime
from modules.loggingHandler import logger


class CloudflareConnectionManager:
    def __init__(self, api_token=None, api_key=None, email=None, verify_ssl=True, timeout=15):
        self.api_token = api_token
        self.api_key = api_key
        self.email = email
        self.verify_ssl = verify_ssl
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.graphql_url = f"{self.base_url}/graphql"
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session = None
        self.zone_cache = {}

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def start(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        elif self.api_key and self.email:
            headers["X-Auth-Key"] = self.api_key
            headers["X-Auth-Email"] = self.email
        return headers

    async def fetch_security_events(self, zone_id, since=None, per_page=50):
        """
        Fetch security events for a zone. Cloudflare recently moved these
        endpoints; some accounts expose /security/events while others only
        have /firewall/events. We try both to stay compatible.
        If all REST variants fail, fall back to GraphQL analytics.
        """
        await self.start()
        params = {"per_page": per_page, "page": 1}
        if since:
            params["since"] = since

        paths = (
            f"/zones/{zone_id}/security/events",
            f"/zones/{zone_id}/firewall/events",
        )

        for path in paths:
            url = f"{self.base_url}{path}"
            try:
                async with self.session.get(
                    url, headers=self._headers(), params=params, ssl=self.verify_ssl
                ) as resp:
                    payload = await resp.json(content_type=None)
                    if resp.status == 404:
                        logger.debug("Endpoint %s returned 404 for zone %s, trying fallback", path, zone_id)
                        continue
                    if any(err.get("code") in (7000, 7003) for err in payload.get("errors", [])):
                        logger.debug("Endpoint %s not routable for zone %s, trying fallback", path, zone_id)
                        continue
                    if resp.status != 200 or not payload.get("success", False):
                        logger.error(
                            "Cloudflare API error [%s] for zone %s via %s: %s",
                            resp.status,
                            zone_id,
                            path,
                            payload.get("errors"),
                        )
                        return None
                    return self._extract_events(payload.get("result"))
            except Exception as exc:
                logger.error("Failed to fetch events for zone %s via %s: %s", zone_id, path, exc)
                # Try next path if there is one
        # REST endpoints unavailable; try GraphQL analytics API
        return await self._fetch_security_events_graphql(zone_id, since=since, limit=per_page)

    async def _fetch_security_events_graphql(self, zone_id, since=None, limit=50):
        """
        Fallback to Cloudflare GraphQL analytics (firewallEventsAdaptive) to fetch events.
        Works on all plans; returns None on errors, [] on no data.
        """
        await self.start()

        # Cloudflare requires a filter on firewallEventsAdaptive; use datetime_geq
        # as a safe default (last 60 minutes) when no "since" was provided.
        if not since:
            fallback_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=60)
            since = fallback_dt.isoformat().replace("+00:00", "Z")

        query = """
        query($zone: String!, $limit: Int!, $since: Time!) {
          viewer {
            zones(filter: { zoneTag: $zone }) {
              firewallEventsAdaptive(
                limit: $limit
                orderBy: [datetime_DESC]
                filter: { datetime_geq: $since }
              ) {
                action
                source
                clientIP
                clientCountryName
                ruleId
                rayName
                datetime
              }
            }
          }
        }
        """
        variables = {"zone": zone_id, "limit": limit, "since": since}

        payload = {"query": query, "variables": variables}

        try:
            async with self.session.post(
                self.graphql_url,
                json=payload,
                headers=self._headers(),
                ssl=self.verify_ssl,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or data.get("errors"):
                    logger.error(
                        "Cloudflare GraphQL error [%s] for zone %s: %s",
                        resp.status,
                        zone_id,
                        data.get("errors"),
                    )
                    return None

                zones = (
                    data.get("data", {})
                    .get("viewer", {})
                    .get("zones", [])
                )
                if not zones:
                    return []

                events = zones[0].get("firewallEventsAdaptive", []) or []
                # Normalize field names to align with REST payload expectations
                normalized = []
                for ev in events:
                    normalized.append(
                        {
                            "action": ev.get("action"),
                            "source": ev.get("source"),
                            "client_ip": ev.get("clientIP"),
                            "client_country_name": ev.get("clientCountryName"),
                            "rule_id": ev.get("ruleId"),
                            # GraphQL schema may not expose rule_message; leave blank if absent
                            "rule_message": ev.get("ruleMessage") or "",
                            "ray_id": ev.get("rayName"),
                            "datetime": ev.get("datetime"),
                        }
                    )
                logger.debug("Fetched %d events via GraphQL for zone %s", len(normalized), zone_id)
                return normalized
        except Exception as exc:
            logger.error("Failed to fetch events via GraphQL for zone %s: %s", zone_id, exc)
            return None

    async def fetch_zone_name(self, zone_id):
        """
        Fetch and cache the human-readable zone name.
        """
        if zone_id in self.zone_cache:
            return self.zone_cache[zone_id]

        await self.start()
        url = f"{self.base_url}/zones/{zone_id}"
        try:
            async with self.session.get(url, headers=self._headers(), ssl=self.verify_ssl) as resp:
                payload = await resp.json(content_type=None)
                if resp.status != 200 or not payload.get("success", False):
                    logger.warning("Could not resolve zone name for %s: %s", zone_id, payload.get("errors"))
                    self.zone_cache[zone_id] = zone_id
                    return zone_id
                name = payload.get("result", {}).get("name", zone_id)
                self.zone_cache[zone_id] = name
                return name
        except Exception as exc:
            logger.warning("Failed to resolve zone name for %s: %s", zone_id, exc)
            self.zone_cache[zone_id] = zone_id
            return zone_id

    @staticmethod
    def _extract_events(result):
        """
        Handle Cloudflare's varied result shapes.
        """
        if not result:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            if isinstance(result.get("security_events"), list):
                return result["security_events"]
            if isinstance(result.get("events"), list):
                return result["events"]
            if isinstance(result.get("result"), list):
                return result["result"]
        return []
