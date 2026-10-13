"""Mock-only coverage for live-capable adapters; no network calls are allowed."""
import asyncio
from types import SimpleNamespace

from core_engine.alpaca_broker import AlpacaBroker, AlpacaConfig, AccountType
from core_engine.real_exchange_manager import RealExchangeManager, OrderBook


class FakeAlpacaAPI:
    def __init__(self):
        self.calls = []

    def submit_order(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="alpaca-test-order", symbol=kwargs["symbol"], side=kwargs["side"],
            type=kwargs["type"], qty=kwargs["qty"], filled_qty="0",
            filled_avg_price=None, status="accepted", created_at=None,
        )


class FakeCCXT:
    def __init__(self):
        self.calls = []

    async def create_order(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        return {"id": "ccxt-test-order", "symbol": symbol, **kwargs}



def test_alpaca_order_method_is_mock_only_and_uses_configured_client():
    broker = AlpacaBroker(AlpacaConfig("fake", "fake", AccountType.PAPER))
    broker.api = FakeAlpacaAPI()
    broker.is_connected = True
    order = broker.place_order("BTCUSD", "buy", 1)
    assert order.id == "alpaca-test-order"
    assert broker.api.calls[0]["symbol"] == "BTCUSD"


def test_ccxt_order_method_does_not_duplicate_symbol_argument():
    manager = RealExchangeManager({"exchanges": {"primary": "binance"}})
    fake = FakeCCXT()
    manager.exchanges["binance"] = fake
    manager.async_exchanges["binance"] = fake
    result = asyncio.run(manager.place_order("BTC/USDT", "buy", 1.0))
    assert result["id"] == "ccxt-test-order"
    assert result["type"] == "market"
    assert fake.calls[0][0] == "BTC/USDT"
    assert "symbol" not in fake.calls[0][1]


def test_best_price_handles_buy_and_sell_without_network():
    manager = RealExchangeManager({"exchanges": {"primary": "binance"}})
    manager.exchanges["binance"] = object()
    book = OrderBook("binance", "BTC/USDT", [(99.0, 2)], [(101.0, 2)], None, 0.02, 100.0)
    async def fake_book(_symbol, _exchange):
        return book
    manager.get_order_book = fake_book
    assert asyncio.run(manager.get_best_price("BTC/USDT", "buy", 1)) == (101.0, "binance")
    assert asyncio.run(manager.get_best_price("BTC/USDT", "sell", 1)) == (99.0, "binance")
