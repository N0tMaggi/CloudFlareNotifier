from cloudflare_notifier._connection import CloudflareConnectionManager


class TestExtractEvents:
    def test_list_result(self):
        events = [{"action": "block"}, {"action": "challenge"}]
        assert CloudflareConnectionManager._extract_events(events) == events

    def test_dict_with_security_events_key(self):
        events = [{"action": "block"}]
        assert CloudflareConnectionManager._extract_events({"security_events": events}) == events

    def test_dict_with_events_key(self):
        events = [{"action": "block"}]
        assert CloudflareConnectionManager._extract_events({"events": events}) == events

    def test_dict_with_result_key(self):
        events = [{"action": "block"}]
        assert CloudflareConnectionManager._extract_events({"result": events}) == events

    def test_none_returns_empty(self):
        assert CloudflareConnectionManager._extract_events(None) == []

    def test_empty_dict_returns_empty(self):
        assert CloudflareConnectionManager._extract_events({}) == []


class TestHeaders:
    def test_token_auth(self):
        h = CloudflareConnectionManager(api_token="tok")._headers()
        assert h["Authorization"] == "Bearer tok"
        assert "X-Auth-Key" not in h

    def test_key_email_auth(self):
        h = CloudflareConnectionManager(api_key="k", email="me@x.com")._headers()
        assert h["X-Auth-Key"] == "k"
        assert h["X-Auth-Email"] == "me@x.com"
        assert "Authorization" not in h

    def test_token_takes_precedence_over_key(self):
        h = CloudflareConnectionManager(api_token="t", api_key="k", email="me@x.com")._headers()
        assert "Authorization" in h
        assert "X-Auth-Key" not in h

    def test_content_type_always_present(self):
        assert CloudflareConnectionManager()._headers()["Content-Type"] == "application/json"
