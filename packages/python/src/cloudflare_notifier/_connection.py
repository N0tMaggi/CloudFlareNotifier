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
        self._rule_message_support: dict[str, bool] = {}

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
    ) -> list[dict[str, object]]:
        """Return a list of raw event dicts, or raise RuntimeError on unrecoverable error."""
        await self._start()
        params: dict[str, str | int] = {"per_page": per_page, "page": 1}
        if since:
            params["since"] = since

        failures: list[str] = []

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
                        errs = payload.get("errors") or []
                        detail = ", ".join(
                            f"[{e.get('code')}] {e.get('message', '')}" for e in errs
                        )
                        suffix = f" – {detail}" if detail else ""
                        failures.append(f"{path}: HTTP {resp.status}{suffix}")
                        continue
                    return self._extract_events(payload.get("result"))
            except Exception as exc:
                failures.append(f"{path}: {exc}")

        return await self._fetch_graphql(
            zone_id, since=since, limit=per_page, prior_failures=failures
        )

    async def _fetch_graphql(
        self,
        zone_id: str,
        since: str | None = None,
        limit: int = 50,
        prior_failures: list[str] | None = None,
    ) -> list[dict[str, object]]:
        await self._start()
        failures = prior_failures or []
        if not since:
            since = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=60)
            ).isoformat().replace("+00:00", "Z")

        use_rule_message = self._rule_message_support.get(zone_id) is not False

        def build_query(with_rule_message: bool) -> str:
            extra = " ruleMessage" if with_rule_message else ""
            return f"""
        query($zone: String!, $limit: Int!, $since: Time!) {{
          viewer {{
            zones(filter: {{ zoneTag: $zone }}) {{
              firewallEventsAdaptive(
                limit: $limit
                orderBy: [datetime_DESC]
                filter: {{ datetime_geq: $since }}
              ) {{
                action source clientIP clientCountryName
                ruleId{extra} rayName datetime
              }}
            }}
          }}
        }}
        """

        async def attempt(with_rule_message: bool) -> list[dict[str, object]]:
            async with self.session.post(  # type: ignore[union-attr]
                self.graphql_url,
                json={
                    "query": build_query(with_rule_message),
                    "variables": {"zone": zone_id, "limit": limit, "since": since},
                },
                headers=self._headers(),
                ssl=self.verify_ssl,
            ) as resp:
                data = await resp.json(content_type=None)
                errors = data.get("errors") or []

                if resp.status == 200 and not errors:
                    if with_rule_message:
                        self._rule_message_support[zone_id] = True
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
                            "rule_message": (
                                ev.get("ruleMessage") or "" if with_rule_message else ""
                            ),
                            "ray_id": ev.get("rayName"),
                            "datetime": ev.get("datetime"),
                        }
                        for ev in events
                    ]

                is_rule_message_error = with_rule_message and any(
                    "unknown field" in (e.get("message") or "")
                    and "ruleMessage" in (e.get("message") or "")
                    for e in errors
                )
                if is_rule_message_error:
                    self._rule_message_support[zone_id] = False
                    return await attempt(False)

                detail = ", ".join(e.get("message", "") for e in errors)
                suffix = f" – {detail}" if detail else ""
                failures.append(f"graphql: HTTP {resp.status}{suffix}")
                raise RuntimeError(
                    f"All Cloudflare endpoints failed for zone {zone_id}:\n  "
                    + "\n  ".join(failures)
                )

        try:
            return await attempt(use_rule_message)
        except RuntimeError:
            raise
        except Exception as exc:
            failures.append(f"graphql: {exc}")
            raise RuntimeError(
                f"All Cloudflare endpoints failed for zone {zone_id}:\n  " + "\n  ".join(failures)
            ) from exc

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
