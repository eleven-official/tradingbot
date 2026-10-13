"""Regression tests for the paper-only hardening pass."""
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from core_engine.academic_strategies import MomentumStrategy
from core_engine.execution_cost_model import Order, OrderSide, OrderType
from core_engine.paper_trading_engine import PaperTradingEngine
from core_engine.main import MarketState, SystemHealth, QuantumTradingEngine
from risk_topology.circuit_breaker import CircuitBreaker
from risk_topology.kelly_allocator import KellyAllocator
from risk_topology.var_model import VaRModel
from core.risk_controller import RiskController


ROOT = Path(__file__).resolve().parents[1]


def test_quantum_config_is_valid_and_unwrapped_by_engine():
    raw = yaml.safe_load((ROOT / "config_quantum.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw["quantum_trading"], dict)
    engine = QuantumTradingEngine(str(ROOT / "config_quantum.yaml"))
    assert "risk_topology" in engine.config
    assert engine.config["risk_topology"]["circuit_breaker_enabled"] is True


def test_risk_components_initialize_and_breaker_accepts_dataclasses():
    config = {"risk_topology": {"circuit_breaker_enabled": True}}
    allocator = KellyAllocator(config)
    breaker = CircuitBreaker(config)
    asyncio.run(allocator.initialize())
    asyncio.run(breaker.initialize())
    assert hasattr(allocator, "logger")
    assert hasattr(breaker, "logger")
    assert asyncio.run(breaker.check_breakers(SystemHealth(), MarketState())) is False


def test_var_model_stores_only_returns():
    model = VaRModel({})
    for price in (100.0, 110.0, 121.0):
        asyncio.run(model.update_returns("TEST", price))
    assert list(model.returns_history["TEST"]) == [0.1, 0.1]
    assert model.last_prices["TEST"] == 121.0


def test_strategy_uses_explicit_symbol_not_timestamp():
    prices = np.linspace(100.0, 130.0, 30)
    data = pd.DataFrame(
        {"open": prices, "high": prices + 1, "low": prices - 1, "close": prices, "volume": 10000},
        index=pd.date_range("2026-01-01", periods=30, freq="D"),
    )
    data.attrs["symbol"] = "BTCUSDT"
    signal = MomentumStrategy().generate_signals(data)[0]
    assert signal.symbol == "BTCUSDT"
    assert isinstance(signal.symbol, str)


def test_paper_engine_rejects_missing_market_data():
    engine = PaperTradingEngine({"initial_balance": 100000.0})
    signal = MomentumStrategy({"symbol": "BTCUSDT"})
    prices = np.linspace(100.0, 130.0, 30)
    data = pd.DataFrame(
        {"open": prices, "high": prices + 1, "low": prices - 1, "close": prices, "volume": 10000},
        index=pd.date_range("2026-01-01", periods=30, freq="D"),
    )
    generated = signal.generate_signals(data.assign())
    # The explicit params symbol makes the signal valid, but no quote is loaded.
    assert generated
    assert asyncio.run(engine.process_signal(generated[0])) is None
    assert engine.positions == {}


def test_paper_engine_uses_matching_market_data_for_fill():
    engine = PaperTradingEngine({"initial_balance": 100000.0})
    order = Order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
    asyncio.run(engine.update_market_data("BTCUSDT", {"close": 100.0, "volume": 10000, "volatility": 0.01}))
    fill = asyncio.run(engine._execute_order(order, 100.0))
    assert fill is not None
    assert 99.0 < fill.fill_price < 102.0


def test_risk_controller_rejects_symbol_concentration_over_limit():
    config = {
        "execution": {
            "max_order_notional_percent": 10.0,
            "max_gross_exposure_percent": 50.0,
            "max_symbol_exposure_percent": 5.0,
            "max_open_positions": 10,
        }
    }
    controller = RiskController(config)
    permitted, reason = controller.validate_order(
        capital=100_000,
        price=100,
        quantity=10,
        gross_exposure=0,
        open_positions=0,
        symbol_exposure=4_500,
    )
    assert permitted is False
    assert "symbol-exposure" in reason
