from modules.importHandler import aiohttp
from modules.loggingHandler import logger


class CloudflareConnectionManager:
    def __init__(self, api_token=None, api_key=None, email=None, verify_ssl=True, timeout=15):
        self.api_token = api_token
        self.api_key = api_key
        self.email = email
        self.verify_ssl = verify_ssl
        self.base_url = "https://api.cloudflare.com/client/v4"
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
        Fetch security events for a zone. Optionally filter by a since timestamp (ISO 8601).
        """
        await self.start()
        params = {"per_page": per_page, "page": 1}
        if since:
            params["since"] = since
        url = f"{self.base_url}/zones/{zone_id}/security/events"

        try:
            async with self.session.get(url, headers=self._headers(), params=params, ssl=self.verify_ssl) as resp:
                payload = await resp.json(content_type=None)
                if resp.status != 200 or not payload.get("success", False):
                    logger.error("Cloudflare API error [%s] for zone %s: %s", resp.status, zone_id, payload.get("errors"))
                    return []
                return self._extract_events(payload.get("result"))
        except Exception as exc:
            logger.error("Failed to fetch events for zone %s: %s", zone_id, exc)
            return []

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
