"""Regression tests for the paper-only execution route."""
import copy
import json
from unittest.mock import patch

import pytest

from core.exceptions import OrderExecutionError
from core.paper_broker import PaperTradingBroker
from loki import LokiBot


class MemoryPaperState:
    """In-memory replacement for atomic state I/O used by these unit tests."""

    def __init__(self):
        self.value = None

    def read(self, _path, default=None):
        return copy.deepcopy(self.value) if self.value is not None else default

    def write(self, _path, value):
        self.value = copy.deepcopy(value)


def paper_config(**overrides):
    config = {
        "paper_broker": {
            "initial_cash": 1_000,
            "currency": "AUD",
            "fee_bps": 10,
            "slippage_bps": 10,
            "state_file": "test-paper.json",
        }
    }
    config["paper_broker"].update(overrides)
    return config


def test_local_paper_broker_tracks_cash_positions_and_realised_pnl():
    storage = MemoryPaperState()
    with patch("core.paper_broker.state_path", return_value="memory.json"), patch(
        "core.paper_broker.read_json", side_effect=storage.read
    ), patch("core.paper_broker.atomic_write_json", side_effect=storage.write):
        broker = PaperTradingBroker(paper_config())
        buy = broker.submit_order("buy", "BTCUSDT", 1, 100, "entry-1")

        assert buy["status"] == "filled"
        assert buy["fill_price"] == pytest.approx(100.1)  # adverse buy slippage
        assert broker.get_account()["cash"] == pytest.approx(899.7999)
        assert broker.get_positions()[0]["quantity"] == 1

        sell = broker.submit_order("sell", "BTCUSDT", 1, 110, "exit-1")
        assert sell["realized_pnl"] == pytest.approx(9.58001)
        assert broker.get_positions() == []
        assert broker.get_account()["equity"] == pytest.approx(1_009.58001)


def test_local_paper_broker_rejects_overselling_and_is_idempotent():
    storage = MemoryPaperState()
    with patch("core.paper_broker.state_path", return_value="memory.json"), patch(
        "core.paper_broker.read_json", side_effect=storage.read
    ), patch("core.paper_broker.atomic_write_json", side_effect=storage.write):
        broker = PaperTradingBroker(paper_config())
        first = broker.submit_order("buy", "ETHUSDT", 1, 100, "same-entry")
        duplicate = broker.submit_order("buy", "ETHUSDT", 1, 100, "same-entry")
        assert duplicate == first
        assert broker.get_positions()[0]["quantity"] == 1
        with pytest.raises(OrderExecutionError, match="Cannot sell more"):
            broker.submit_order("sell", "ETHUSDT", 2, 100, "bad-exit")


class FakeStateManager:
    def __init__(self, _config):
        self.starting_capital = None
        self.trades_today_count = 0
        self.entries = []
        self.closed = []

    def record_entry(self, entry):
        self.entries.append(entry)
        self.trades_today_count += 1

    def record_trade(self, trade):
        self.closed.append(trade)

    def check_daily_loss_limit(self, *_args):
        return False

    def check_consecutive_loss_limit(self, *_args):
        return False

    def check_weekly_loss_limit(self, *_args):
        return False


def test_loki_executes_only_authenticated_unique_and_risk_checked_paper_signals():
    storage = MemoryPaperState()
    config = LokiBot.get_default_config()
    config["tradingview"].update({"webhook_secret": "test-secret", "allowed_symbols": ["BTCUSDT"]})
    config["paper_broker"].update({"initial_cash": 1_000, "state_file": "loki-test.json"})
    config["execution"].update({"max_order_notional_percent": 20, "max_gross_exposure_percent": 30})

    with patch.object(LokiBot, "load_config", return_value=config), patch("loki.StateManager", FakeStateManager), patch(
        "core.paper_broker.state_path", return_value="memory.json"
    ), patch("core.paper_broker.read_json", side_effect=storage.read), patch(
        "core.paper_broker.atomic_write_json", side_effect=storage.write
    ):
        bot = LokiBot()
        client = bot.app.test_client()
        buy_payload = {
            "token": "test-secret",
            "signal_id": "buy-1",
            "signal_type": "buy",
            "symbol": "BTCUSDT",
            "price": 100,
            "quantity": 1,
        }
        buy = client.post("/webhook/tradingview", data=json.dumps(buy_payload), content_type="application/json")
        assert buy.status_code == 200
        assert buy.get_json()["result"]["status"] == "filled"

        duplicate = client.post("/webhook/tradingview", data=json.dumps(buy_payload), content_type="application/json")
        assert duplicate.status_code == 200
        assert duplicate.get_json()["message"] == "Duplicate signal rejected"

        unauthenticated = client.post(
            "/webhook/tradingview",
            data=json.dumps({**buy_payload, "signal_id": "buy-2", "token": "wrong"}),
            content_type="application/json",
        )
        assert unauthenticated.status_code == 422

        sell = client.post(
            "/webhook/tradingview",
            data=json.dumps({**buy_payload, "signal_id": "sell-1", "signal_type": "sell", "price": 110}),
            content_type="application/json",
        )
        assert sell.status_code == 200
        assert bot.execution_broker.get_positions() == []
        assert len(bot.state_manager.closed) == 1
