"""Real mode readiness is not authentication, balances or order permission."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from core.fusion.real_account import status, account_snapshot
from loki.api.server import app


def test_mode_metadata_never_authenticates_or_submits_and_missing_keys_block_client_creation():
    result = status({})
    assert result["ready_to_connect"] is False
    assert result["authenticated"] is False
    assert result["live_trading_enabled"] is False
    assert result["order_submission_available"] is False
    with patch("ccxt.kraken") as client:
        with pytest.raises(ValueError, match="credentials"):
            account_snapshot({})
        client.assert_not_called()


def test_real_spot_read_returns_actual_units_and_no_fabricated_common_equity():
    env = {
        "LOKI_REAL_READS_ENABLED": "1",
        "LOKI_REAL_API_KEY": "fixture-key",
        "LOKI_REAL_API_SECRET": "fixture-secret",
    }
    with patch("ccxt.kraken") as constructor:
        client = constructor.return_value
        client.fetch_balance.return_value = {
            "total": {"BTC": 0.25, "USD": 100, "BAD": float("nan")},
            "free": {"BTC": 0.2},
            "used": {"BTC": 0.05},
        }
        result = account_snapshot(env)
        assert result["authenticated"] is True
        assert result["assets"][0]["total"] == 0.25
        assert result["assets"][1]["free"] is None
        assert result["valuation"] is None
        assert result["orders_submitted"] == 0
        assert "fixture-key" not in str(result)
        client.create_order.assert_not_called()
        assert constructor.call_args.args[0]["options"]["defaultType"] == "spot"


def test_failed_real_read_never_displays_zero_balance_or_secret_error_text():
    env = {
        "LOKI_REAL_READS_ENABLED": "1",
        "LOKI_REAL_API_KEY": "fixture-key",
        "LOKI_REAL_API_SECRET": "fixture-secret",
    }
    with patch("ccxt.kraken") as constructor:
        constructor.return_value.fetch_balance.side_effect = RuntimeError(
            "signed URL fixture-secret"
        )
        with pytest.raises(ConnectionError) as result:
            account_snapshot(env)
        assert "fixture-secret" not in str(result.value)


def test_remote_client_cannot_inspect_config_or_read_real_account():
    with TestClient(app) as client:
        assert client.get("/api/fusion/real/status").status_code == 403
        assert client.post("/api/fusion/real/account").status_code == 403
