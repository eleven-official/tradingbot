"""Alpaca paper relay: gate-only access, browser-held keys, honest error maps.

The relay must never invent account facts or order statuses, never reach the
network for badly shaped keys or orders, touch only Alpaca's PAPER endpoint
with the caller's credentials, surface Alpaca's own rejections as plain human
messages, and keep the keys out of the workspace backup export entirely.
The order rail is explicit-clicks-only: day orders, relay caps, whitelist.
"""

import io
import json
import urllib.error
from pathlib import Path

from fastapi.testclient import TestClient

import loki.api.broker_alpaca as module
from loki.api.server import app

ROOT = Path(__file__).resolve().parents[1]

client = TestClient(app)

KEYS = {
    "key_id": "PKTESTKEY123456",
    "secret_key": "abcdefghij0123456789abcdefghij0123456789",
}

ORDER = {**KEYS, "symbol": "SPY", "side": "buy", "quantity": 2, "order_type": "market"}

ACCOUNT_PAYLOAD = {
    "id": "e0f9secret-identity-value",
    "contact_email": "someone@alpaca.invalid",
    "status": "ACTIVE",
    "account_number": "PA0001XYZ9",
    "currency": "USD",
    "cash": "100000.505",
    "equity": 120000.333,
    "buying_power": "400000",
    "trading_blocked": False,
    "account_blocked": False,
    "pattern_day_trader": False,
}

ORDER_PAYLOAD = {
    "id": "order-identity-0001",
    "client_order_id": "lorem-internal-uptime-guid",
    "created_at": "2026-10-21T11:50:00.000000Z",
    "submitted_at": "2026-10-21T11:50:01.000000Z",
    "symbol": "SPY",
    "qty": "2",
    "side": "buy",
    "type": "market",
    "time_in_force": "day",
    "extended_hours": False,
    "status": "accepted",
    "filled_qty": 0,
    "hwm": None,
}


class FakeResponse:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _deferred(assert_later):
    """Return a fake urlopen that always records and never fires locally."""
    def fake(request, timeout=None):
        assert_later["request"] = request
        return FakeResponse(json.dumps(ACCOUNT_PAYLOAD).encode())
    return fake


class TestRelayAccess:
    def test_relay_requires_the_access_door(self, monkeypatch):
        fresh = TestClient(app)
        response = fresh.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 403
        assert "access door" in response.json()["detail"]


class TestRelay:
    def gate(self):
        opened = client.post("/api/gate", json={"code": "flathead"})
        assert opened.status_code == 200

    def test_bad_key_shapes_never_reach_the_network(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("badly shaped keys must be refused before any network hop")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        assert client.post("/api/broker/alpaca/test", json={**KEYS, "key_id": "short"}).status_code == 422
        assert client.post(
            "/api/broker/alpaca/test",
            json={**KEYS, "secret_key": "tooshort"},
        ).status_code == 422
        assert client.post("/api/broker/alpaca/test", json={"key_id": "okokayok1!2"}).status_code == 422
        assert attempts["n"] == 0

    def test_valid_keys_reach_the_paper_endpoint_with_credential_headers(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            return FakeResponse(json.dumps(ACCOUNT_PAYLOAD).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 200
        assert response.json() == {"ok": True, "account_status": "ACTIVE", "paper": True}
        request = later["request"]
        assert request.full_url == "https://paper-api.alpaca.markets/v2/account"
        headers = {name.lower(): value for name, value in request.header_items()}
        assert headers.get("apca-api-key-id") == KEYS["key_id"]
        assert headers.get("apca-api-secret-key") == KEYS["secret_key"]
        assert "lokiworkspace" in (headers.get("user-agent") or "").lower()

    def test_account_view_whitelists_what_leaves_the_relay(self, monkeypatch):
        self.gate()
        later = {}
        monkeypatch.setattr(module.urllib.request, "urlopen", _deferred(later))
        response = client.post("/api/broker/alpaca/account", json=KEYS)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "paper",
            "status",
            "account_number",
            "currency",
            "cash",
            "equity",
            "buying_power",
            "trading_blocked",
            "account_blocked",
        }
        assert body["paper"] is True
        assert body["cash"] == 100000.51  # relay rounds to cents (0.505 floats above)
        assert body["equity"] == 120000.33
        assert body["account_number"] == "01XYZ9"  # masked to the tail: no full identity
        assert "contact_email" not in body
        assert "id" not in body

    def test_rejected_keys_answer_honestly_as_401(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/account", 401, "no", None, None)

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 401
        assert "rejected those keys" in response.json()["detail"]

    def test_unreachable_alpaca_answers_503_not_a_fake_success(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.URLError(OSError("no route to host"))

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 503
        assert "unreachable" in response.json()["detail"]

    def test_unparseable_answer_answers_502(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            return FakeResponse(b'<<"nope"')

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 502
        assert "could not parse" in response.json()["detail"]

    def test_rate_limit_maps_to_503_with_patience(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/account", 429, "slow", None, None)

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 503
        assert "rate-limiting" in response.json()["detail"]


class TestOrderRail:
    def gate(self):
        opened = client.post("/api/gate", json={"code": "flathead"})
        assert opened.status_code == 200

    def test_semantics_a_limit_order_needs_a_price(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("a priceless limit order must stop at the door")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        response = client.post(
            "/api/broker/alpaca/order",
            json={**ORDER, "order_type": "limit"},
        )
        assert response.status_code == 422
        assert "needs a limit price" in response.json()["detail"]
        assert attempts["n"] == 0

    def test_semantics_a_market_order_refuses_a_price(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("a priced market order must stop at the door")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        response = client.post(
            "/api/broker/alpaca/order",
            json={**ORDER, "limit_price": 123.5},
        )
        assert response.status_code == 422
        assert "takes no limit price" in response.json()["detail"]
        assert attempts["n"] == 0

    def test_order_body_travels_shaped_as_specced(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            return FakeResponse(json.dumps(ORDER_PAYLOAD).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/order", json=ORDER)
        assert response.status_code == 200
        request = later["request"]
        assert request.full_url == "https://paper-api.alpaca.markets/v2/orders"
        assert request.get_method() == "POST"
        body = json.loads(request.data.decode())
        assert body == {
            "symbol": "SPY",
            "qty": "2",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "extended_hours": False,
        }
        view = response.json()["order"]
        assert view["symbol"] == "SPY"
        assert view["qty"] == 2
        assert view["status"] == "accepted"

    def test_limit_price_travels_as_cents_not_float_dust(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            return FakeResponse(json.dumps(ORDER_PAYLOAD).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post(
            "/api/broker/alpaca/order",
            json={**ORDER, "order_type": "limit", "limit_price": 123.454},
        )
        assert response.status_code == 200
        body = json.loads(later["request"].data.decode())
        assert body["limit_price"] == "123.45"

    def test_order_answer_is_whitelisted(self, monkeypatch):
        self.gate()
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(json.dumps(ORDER_PAYLOAD).encode()),
        )
        body = client.post("/api/broker/alpaca/order", json=ORDER).json()["order"]
        assert set(body) <= {
            "id", "symbol", "qty", "side", "type", "time_in_force", "status",
            "created_at", "submitted_at", "filled_qty", "filled_avg_price",
        }
        assert "client_order_id" not in body
        assert "hwm" not in body

    def test_bad_order_shapes_never_reach_the_network(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("badly shaped orders must be refused before any network hop")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "side": "sideways"}).status_code == 422
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "quantity": 0}).status_code == 422
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "quantity": 101}).status_code == 422
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "symbol": "SP Y"}).status_code == 422
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "order_type": "nonsense"}).status_code == 422
        assert client.post("/api/broker/alpaca/order", json={**ORDER, "quantity": 1.5}).status_code == 422
        assert attempts["n"] == 0

    def test_alpacas_own_refusal_travels_honestly(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            body = json.dumps({"code": 40110000, "message": "insufficient buying power"}).encode()
            raise urllib.error.HTTPError(
                "https://paper-api.alpaca.markets/v2/orders", 422, "Unprocessable Entity", None, io.BytesIO(body)
            )

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/order", json=ORDER)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "refused" in detail
        assert "insufficient buying power" in detail

    def test_order_log_asks_for_the_recent_book_and_maps_it(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            books = [
                {**ORDER_PAYLOAD, "id": f"order-{i:04d}", "created_at": f"2026-10-2{1}"
                 f"T1{i % 10}:00:00.000000Z"}
                for i in range(12)
            ]
            return FakeResponse(json.dumps(books).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/orders", json=KEYS)
        assert response.status_code == 200
        assert "status=all&limit=12&direction=desc" in later["request"].full_url
        body = response.json()
        assert body["ok"] is True and body["paper"] is True
        assert len(body["orders"]) == 12
        created = [order["created_at"] for order in body["orders"]]
        assert created == sorted(created, reverse=True), "the panel reads newest first"
        assert "client_order_id" not in body["orders"][0]

    def test_empty_order_book_is_an_honest_empty_list(self, monkeypatch):
        self.gate()
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(b"[]"),
        )
        response = client.post("/api/broker/alpaca/orders", json=KEYS)
        assert response.status_code == 200
        assert response.json() == {"ok": True, "paper": True, "orders": []}

    def test_non_list_order_log_answers_502(self, monkeypatch):
        self.gate()
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(b'{"nope": true}'),
        )
        response = client.post("/api/broker/alpaca/orders", json=KEYS)
        assert response.status_code == 502
        assert "not the expected list" in response.json()["detail"]


BARS_PAYLOAD = {
    "bars": [
        {"t": f"2026-10-21T11:{i:02d}:00Z", "o": 480 + i / 10, "h": 481, "l": 479,
         "c": 480.5 + i / 100, "v": 1000 + i}
        for i in range(25)
    ] + [{"junk": True}],
}


class TestAutopilotBars:
    def gate(self):
        opened = client.post("/api/gate", json={"code": "flathead"})
        assert opened.status_code == 200

    def test_bars_read_reaches_alpacas_data_host_not_the_paper_host(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            return FakeResponse(json.dumps(BARS_PAYLOAD).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "spy", "minutes": 25})
        assert response.status_code == 200
        request = later["request"]
        assert request.full_url == "https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&limit=25&feed=iex&sort=asc"
        headers = {name.lower(): value for name, value in request.header_items()}
        assert headers.get("apca-api-key-id") == KEYS["key_id"]
        assert request.get_method() == "GET"
        assert request.data is None, "the bars read never sends a body upstream"

    def test_bar_view_is_whitelisted_and_junk_bars_drop_out(self, monkeypatch):
        self.gate()
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(json.dumps(BARS_PAYLOAD).encode()),
        )
        body = client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "SPY"}).json()
        assert set(body) == {"ok", "paper", "symbol", "bars"}
        first = body["bars"][0]
        assert set(first) == {"t", "o", "h", "l", "c", "v"}
        assert body["bars"][0]["t"] == "2026-10-21T11:00:00Z"
        assert len(body["bars"]) == 25, "the junk bar dropped out, the real ones stayed"

    def test_bar_feed_oversized_rows_are_capped(self, monkeypatch):
        self.gate()
        huge = {"bars": [{"t": "2026-10-21T11:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for _ in range(200)]}
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(json.dumps(huge).encode()),
        )
        body = client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "SPY", "minutes": 60}).json()
        assert len(body["bars"]) <= module.BARS_MAX

    def test_bar_requests_stay_in_band_before_any_network(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("out-of-band bar requests must be refused before any network hop")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        assert client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "SPY", "minutes": 5}).status_code == 422
        assert client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "SPY", "minutes": 61}).status_code == 422
        assert client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "s.p y"}).status_code == 422
        assert attempts["n"] == 0

    def test_shapeless_bar_feed_answers_502(self, monkeypatch):
        self.gate()
        monkeypatch.setattr(
            module.urllib.request, "urlopen",
            lambda request, timeout=None: FakeResponse(b'{"bars": "nope"}'),
        )
        response = client.post("/api/broker/alpaca/bars", json={**KEYS, "symbol": "SPY"})
        assert response.status_code == 502
        assert "unexpected shape" in response.json()["detail"]


class TestSiteHygiene:
    def test_backup_export_excludes_alpaca_keys(self):
        source = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        assert "loki_alpaca" not in source, "live API keys must never ride the backup export"

    def test_panel_script_and_router_are_wired(self):
        index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'id="alpaca-keys-form"' in index
        assert "static/js/alpaca_keys.js" in index
        server = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        assert "broker_alpaca_router" in server

    def test_arrival_verification_keys_on_a_fingerprint(self):
        module = (ROOT / "static" / "js" / "alpaca_keys.js").read_text(encoding="utf-8")
        assert "verifiedFor !== fingerprint" in module, \
            "arrival verification must compare the key-ID fingerprint"
        assert "verifiedFor !== load()" not in module, \
            "object-identity comparison would re-hit Alpaca on every single visit"
        assert "savedOnInit.key_id" in module

    def test_panel_carries_the_order_rail(self):
        index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        for marker in (
            'id="alpaca-order-form"', 'id="alpaca-order-symbol"', 'id="alpaca-order-qty"',
            'id="alpaca-order-side"', 'id="alpaca-order-type"', 'id="alpaca-order-limit"',
            'id="alpaca-order-send"', 'id="alpaca-order-message"', 'id="alpaca-order-log"',
            'id="alpaca-orders-refresh"',
        ):
            assert marker in index, f"the order rail is missing {marker}"
        copy = index
        assert "armed, then confirmed" in copy, "the panel must say orders are armed then confirmed"
        assert "100 shares a ticket" in copy, "the panel must state the relay cap in plain words"

    def test_panel_stays_guarded_against_double_fires(self):
        module_source = (ROOT / "static" / "js" / "alpaca_keys.js").read_text(encoding="utf-8")
        assert "orderArmed !== summary" in module_source, \
            "the send button must arm first, never fire on the first click"
        assert "mirrors the relay cap" in module_source, \
            "the browser cap must be labeled as a mirror of the relay's, not independent"
        assert "15 s to send it" in module_source or "15000" in module_source, \
            "the armed window must expire"

    def test_relay_and_browser_caps_are_one_number(self):
        server = (ROOT / "loki" / "api" / "broker_alpaca.py").read_text(encoding="utf-8")
        module = (ROOT / "static" / "js" / "alpaca_keys.js").read_text(encoding="utf-8")
        import re as _re
        server_cap = _re.search(r"ORDER_QTY_MAX\s*=\s*(\d+)", server)
        js_cap = _re.search(r"ORDER_QTY_MAX = (\d+)", module)
        assert server_cap and js_cap, "both sides must declare the cap"
        assert server_cap.group(1) == js_cap.group(1), "the panel cap must mirror the relay cap exactly"

    def test_autopilot_is_published_rails_not_a_shrug(self):
        index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        for marker in (
            'id="alpaca-autopilot-switch"', 'id="alpaca-autopilot-status"',
            'id="alpaca-autopilot-log"', "averages the last ten closes",
            "buys exactly 1 share", "Closing the tab or reloading turns it off — it never restarts on its own",
            "never touches positions you opened by hand",
        ):
            assert marker in index, f"the published rule is missing its own words: {marker}"

    def test_autopilot_engine_holds_the_rails(self):
        module = (ROOT / "static" / "js" / "alpaca_keys.js").read_text(encoding="utf-8")
        assert "AUTOPILOT_MAX_ORDERS = 10" in module, "the session ceiling must be declared"
        assert "AUTOPILOT_COOLDOWN_MS = 90000" in module, "a cooldown must follow every send"
        assert "document.hidden" in module, "the loop must pause while the tab is hidden"
        assert "async function autopilotTick" in module
        assert "autopilot.lastSide && side && side !== autopilot.lastSide" in module, \
            "orders fire only on a real crossing, never on a side already held"
        assert "crossingUp ? 'buy' : 'sell'" in module and "quantity: 1" in module, \
            "the rule trades exactly one share per crossing"
        assert "if (!bars" not in module, "placeholder shipped"  # honest mistake guard
        assert "stopAutopilot('the session ceiling of '" in module, "the ceiling must stand the train down honestly"
