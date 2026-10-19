"""No real broker requests: credential handling, fixed hosts and account sessions."""

from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient
import pytest

from core.fusion import broker_link as link
from loki.api.server import app

ACCOUNT = {
    "id": "fixture-paper-account-1234",
    "currency": "USD",
    "status": "ACTIVE",
    "cash": "10000",
    "equity": "10000",
    "trading_blocked": False,
    "account_blocked": False,
}


@pytest.fixture(autouse=True)
def sessions():
    link._profiles.clear()
    yield
    link._profiles.clear()


def profile(mode="paper"):
    return link.Profile("alpaca", mode, "fixture-api-key", "fixture-api-secret")


def response(payload):
    value = MagicMock()
    value.__enter__.return_value = value
    value.read.return_value = json.dumps(payload).encode()
    return value


def test_paper_account_verification_is_real_response_based_and_never_exports_credentials():
    with patch.object(link.AlpacaClient, "request", return_value=ACCOUNT):
        identifier, result = link.connect(
            "alpaca", "paper", "fixture-api-key", "fixture-api-secret"
        )
    assert result["connected"] is True
    assert result["account"]["cash"] == 10000
    assert result["account"]["id_hint"] == "1234"
    assert result["paper_ai_available"] is True
    assert result["live_automation_available"] is False
    assert "fixture-api" not in json.dumps(result)
    assert "fixture-api" not in repr(link.get_profile(identifier))
    link.disconnect(identifier)
    with pytest.raises(ValueError, match="Connect"):
        link.get_profile(identifier)


def test_invalid_credentials_never_create_a_verified_session_or_echo_the_secret():
    with patch.object(link.AlpacaClient, "request", side_effect=link.BrokerUnavailable()):
        with pytest.raises(ConnectionError) as error:
            link.connect("alpaca", "paper", "fixture-api-key", "fixture-api-secret")
    assert not link._profiles
    assert "fixture-api" not in str(error.value)
    with patch.object(link.AlpacaClient, "request") as transport:
        with pytest.raises(ValueError):
            link.connect("alpaca", "paper", "bad\nkey-header", "fixture-api-secret")
        transport.assert_not_called()


def test_credential_expiry_is_enforced_for_reads_and_order_transport():
    item = profile()
    item.expires = 0
    with patch.object(link, "build_opener") as opener:
        with pytest.raises(ValueError, match="expired"):
            link.AlpacaClient(item).request("POST", "/v2/orders", body={})
        opener.assert_not_called()
    link._profiles["expired"] = item
    with pytest.raises(ValueError):
        link.get_profile("expired")


def test_transport_uses_the_fixed_paper_host_with_secret_headers_and_no_redirects():
    with patch.object(link, "build_opener") as opener:
        opener.return_value.open.return_value = response({"id": "fixture-order"})
        result = link.AlpacaClient(profile()).request("POST", "/v2/orders", body={"symbol": "SPY"})
        request = opener.return_value.open.call_args.args[0]
        assert request.full_url == "https://paper-api.alpaca.markets/v2/orders"
        assert request.method == "POST"
        assert request.get_header("Apca-api-secret-key") == "fixture-api-secret"
        assert result["id"] == "fixture-order"
    with pytest.raises(link.BrokerUnavailable):
        link._NoRedirects().redirect_request(
            None, None, 302, "redirect", {}, "https://other.example/collect"
        )


@pytest.mark.parametrize(
    "path,data",
    [("/v2/orders", False), ("/v2/orders/anything", False), ("/v2/stocks/SPY/bars", True)],
)
def test_live_connection_cannot_write_any_order_or_data_resource(path, data):
    with patch.object(link, "build_opener") as opener:
        with pytest.raises(ValueError, match="paper endpoint"):
            link.AlpacaClient(profile("live")).request("POST", path, data=data, body={})
        opener.assert_not_called()


def test_http_errors_do_not_return_response_bodies_or_signed_secret_urls():
    with patch.object(link, "build_opener") as opener:
        opener.return_value.open.side_effect = HTTPError(
            "https://paper-api.alpaca.markets/?fixture-api-secret",
            401,
            "fixture-api-secret",
            {},
            BytesIO(b"fixture-api-secret"),
        )
        with pytest.raises(ValueError) as error:
            link.AlpacaClient(profile()).request("GET", "/v2/account")
    assert "fixture-api-secret" not in str(error.value)


def test_history_paginates_completed_daily_bars_without_synthetic_substitution():
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()
    bar = lambda day: {"t": day + "T05:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000}
    with patch.object(
        link.AlpacaClient,
        "request",
        side_effect=[
            {"bars": [bar("2016-11-01")], "next_page_token": "page-2"},
            {"bars": [bar(yesterday), bar(today)]},
        ],
    ) as transport:
        rows = link.AlpacaClient(profile()).historical_bars("SPY", 10)
    assert len(rows) == 2
    assert rows[-1]["timestamp"][:10] == yesterday
    assert transport.call_args_list[0].kwargs["params"]["feed"] == "iex"
    assert transport.call_args_list[1].kwargs["params"]["page_token"] == "page-2"
    with patch.object(
        link.AlpacaClient, "request", return_value={"bars": [], "next_page_token": "repeat"}
    ):
        with pytest.raises(link.BrokerUnavailable):
            link.AlpacaClient(profile()).historical_bars("SPY", 10)


def test_missing_usd_account_identity_cannot_be_labeled_verified():
    with patch.object(
        link.AlpacaClient, "request", return_value={"cash": "99999", "equity": "99999"}
    ):
        with pytest.raises(ValueError):
            link.connect("alpaca", "paper", "fixture-api-key", "fixture-api-secret")
    assert not link._profiles


def test_local_key_entry_is_private_http_only_and_isolated_from_another_browser(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    monkeypatch.setenv("LOKI_PAPER_AI_DB", str(tmp_path / "paper.sqlite3"))
    payload = {
        "provider": "alpaca",
        "mode": "paper",
        "api_key": "fixture-api-key",
        "api_secret": "fixture-api-secret",
    }
    with (
        TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as first,
        TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1235)) as second,
    ):
        token = first.get("/api/fusion/capabilities").json()["local_token"]
        headers = {"X-Loki-Local-Token": token}
        assert first.post("/api/fusion/broker/connect", json=payload).status_code == 403
        assert (
            first.post(
                "/api/fusion/broker/connect",
                json=payload,
                headers=dict(headers, Origin="https://untrusted.test"),
            ).status_code
            == 403
        )
        with patch.object(link.AlpacaClient, "request", return_value=ACCOUNT):
            result = first.post("/api/fusion/broker/connect", json=payload, headers=headers)
        assert result.status_code == 200, result.text
        assert "fixture-api" not in result.text
        assert "httponly" in result.headers["set-cookie"].lower()
        assert "samesite=strict" in result.headers["set-cookie"].lower()
        assert result.headers["cache-control"] == "private, no-store"
        assert (
            first.get("/api/fusion/broker/connection", headers=headers).json()["connected"] is True
        )
        assert (
            second.get("/api/fusion/broker/connection", headers=headers).json()["connected"]
            is False
        )
        bad = first.post(
            "/api/fusion/broker/connect",
            json=dict(payload, api_secret="fixture-api-secret\n"),
            headers=headers,
        )
        assert bad.status_code == 422
        assert "fixture-api-secret" not in bad.text
        assert (
            first.post("/api/fusion/broker/disconnect", headers=headers).json()["connected"]
            is False
        )
