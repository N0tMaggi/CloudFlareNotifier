import datetime

import pytest

from cloudflare_notifier import CloudFlareWatcher, SecurityEvent

UTC = datetime.timezone.utc


# ------------------------------------------------------------------ construction

class TestInit:
    def test_requires_credentials(self):
        with pytest.raises(ValueError, match="api_token"):
            CloudFlareWatcher(zone_ids=["z1"])

    def test_requires_zone_ids(self):
        with pytest.raises(ValueError, match="zone_id"):
            CloudFlareWatcher(api_token="tok", zone_ids=[])

    def test_valid_with_token(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])
        assert w._zone_ids == ["z1"]

    def test_valid_with_key_and_email(self):
        w = CloudFlareWatcher(api_key="k", email="me@x.com", zone_ids=["z1"])
        assert w._api_key == "k"
        assert w._email == "me@x.com"

    def test_default_poll_interval(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])
        assert w._poll_interval == 60

    def test_custom_poll_interval(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"], poll_interval=30)
        assert w._poll_interval == 30


# ------------------------------------------------------------------ on_event

class TestOnEvent:
    def test_decorator_registers_handler(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])

        @w.on_event
        async def handler(event: SecurityEvent) -> None:
            pass

        assert handler in w._handlers

    def test_decorator_returns_original_function(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])

        async def handler(event: SecurityEvent) -> None:
            pass

        result = w.on_event(handler)
        assert result is handler

    def test_multiple_handlers(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])

        async def h1(e): pass
        async def h2(e): pass

        w.on_event(h1)
        w.on_event(h2)
        assert len(w._handlers) == 2


# ------------------------------------------------------------------ _parse_ts

class TestParseTs:
    def test_z_suffix(self):
        raw = {"occurred_at": "2024-01-15T10:30:00Z"}
        ts = CloudFlareWatcher._parse_ts(raw)
        assert ts is not None
        assert ts.year == 2024

    def test_plus_offset(self):
        raw = {"datetime": "2024-01-15T10:30:00+00:00"}
        ts = CloudFlareWatcher._parse_ts(raw)
        assert ts is not None

    def test_falls_back_through_keys(self):
        raw = {"timestamp": "2024-06-01T00:00:00Z"}
        assert CloudFlareWatcher._parse_ts(raw) is not None

    def test_returns_none_on_missing_keys(self):
        assert CloudFlareWatcher._parse_ts({}) is None

    def test_returns_none_on_invalid_value(self):
        assert CloudFlareWatcher._parse_ts({"occurred_at": "not-a-date"}) is None


# ------------------------------------------------------------------ _ts_str

class TestTsStr:
    def test_utc_aware_ends_with_z(self):
        ts = datetime.datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        assert CloudFlareWatcher._ts_str(ts).endswith("Z")

    def test_naive_treated_as_utc(self):
        ts = datetime.datetime(2024, 6, 1, 12, 0, 0)
        result = CloudFlareWatcher._ts_str(ts)
        assert result.endswith("Z")


# ------------------------------------------------------------------ _to_event

class TestToEvent:
    RAW = {
        "action": "block",
        "source": "firewall",
        "client_ip": "1.2.3.4",
        "client_country_name": "DE",
        "rule_id": "rid123",
        "rule_message": "SQLi detected",
        "ray_id": "abc",
    }

    def test_maps_fields_correctly(self):
        ts = datetime.datetime(2024, 1, 1, tzinfo=UTC)
        ev = CloudFlareWatcher._to_event("zid", "example.com", self.RAW, ts)
        assert ev.zone_id == "zid"
        assert ev.zone_name == "example.com"
        assert ev.action == "block"
        assert ev.client_ip == "1.2.3.4"
        assert ev.country == "DE"
        assert ev.occurred_at == ts
        assert ev.raw is self.RAW

    def test_missing_fields_default_to_empty_string(self):
        ev = CloudFlareWatcher._to_event("zid", "example.com", {}, None)
        assert ev.action == ""
        assert ev.client_ip == ""
        assert ev.occurred_at is None


# ------------------------------------------------------------------ dispatch

class TestDispatch:
    @pytest.mark.asyncio
    async def test_calls_all_handlers(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])
        calls = []

        async def h1(e): calls.append("h1")
        async def h2(e): calls.append("h2")

        w.on_event(h1)
        w.on_event(h2)

        fake_event = CloudFlareWatcher._to_event("zid", "example.com", {}, None)
        await w._dispatch(fake_event)
        assert calls == ["h1", "h2"]

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_stop_others(self):
        w = CloudFlareWatcher(api_token="tok", zone_ids=["z1"])
        calls = []

        async def bad(e): raise RuntimeError("oops")
        async def good(e): calls.append("good")

        w.on_event(bad)
        w.on_event(good)

        await w._dispatch(CloudFlareWatcher._to_event("z", "z", {}, None))
        assert calls == ["good"]
