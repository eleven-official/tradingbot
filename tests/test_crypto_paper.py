"""Offline tests for the crypto paper session (loki_v8.crypto_paper).

Nothing here touches the network: parameter resolution, curve combination,
summary arithmetic, the Alpaca symbol mapping and the fail-closed guards on
order mirroring are all pure functions.
"""

import pandas as pd
import pytest

from loki_v8 import crypto_paper as cp
from loki_v8.config import LokiConfig
from loki_v8.train import apply_crypto_consensus, apply_params


CRYPTO_BLOCK = {
    "params": {
        "signal_threshold": 25.0,
        "stop_loss_atr": 5.0,
        "take_profit_atr": 0.5,
        "factor_weights": {"trend": 0.1, "momentum": 0.1, "volume_flow": 0.3, "squeeze": 0.1, "volatility": 0.4},
    },
    "support_pct": 80.0,
}
EQUITY_BLOCK = {"params": {"signal_threshold": 40.0, "stop_loss_atr": 1.5}}


def book_with(symbols=None, crypto_consensus=CRYPTO_BLOCK, consensus=EQUITY_BLOCK):
    return {
        "generated_at": "2026-01-01T00:00:00",
        "symbols": symbols or [],
        "crypto_consensus": crypto_consensus,
        "consensus": consensus,
    }


class TestProfileResolution:
    def test_prefers_symbol_profile(self):
        book = book_with(
            symbols=[{"symbol": "BTC-USD", "ok": True, "best_params": {"signal_threshold": 8.0}}]
        )
        params, source = cp.profile_for(book, "BTC-USD")
        assert source == "trained"
        assert params["signal_threshold"] == 8.0

    def test_ignores_failed_symbol(self):
        book = book_with(
            symbols=[{"symbol": "BTC-USD", "ok": False, "best_params": {"signal_threshold": 8.0}}]
        )
        _, source = cp.profile_for(book, "BTC-USD")
        assert source == "crypto_consensus"

    def test_falls_back_to_crypto_consensus(self):
        params, source = cp.profile_for(book_with(), "BTC-USD")
        assert source == "crypto_consensus"
        assert params["stop_loss_atr"] == 5.0

    def test_falls_back_to_mixed_consensus(self):
        params, source = cp.profile_for(book_with(crypto_consensus=None), "BTC-USD")
        assert source == "consensus"
        assert params["signal_threshold"] == 40.0

    def test_defaults_when_book_is_empty(self):
        params, source = cp.profile_for({}, "BTC-USD")
        assert (params, source) == ({}, "defaults")

    def test_symbol_match_is_case_insensitive(self):
        book = book_with(
            symbols=[{"symbol": "btc-usd", "ok": True, "best_params": {"signal_threshold": 9.0}}]
        )
        params, source = cp.profile_for(book, "BTC-USD")
        assert source == "trained" and params["signal_threshold"] == 9.0


class TestConfigBuild:
    def test_trained_params_land_on_config(self):
        cfg = cp.build_config(
            {"signal_threshold": 12.0, "max_hold_bars": 45, "factor_weights": {"trend": 1.0}},
            sleeve=2500.0,
            period="3y",
            timeframe="1d",
        )
        assert isinstance(cfg, LokiConfig)
        assert cfg.initial_cash == 2500.0
        assert cfg.period == "3y"
        assert cfg.signal_threshold == 12.0
        assert cfg.max_hold_bars == 45
        assert cfg.factor_weights["trend"] == 1.0
        assert sum(cfg.factor_weights.values()) == 1.0

    def test_non_config_keys_are_ignored(self):
        cfg = cp.build_config(
            {"factor_preset": "balanced", "win_rate_pct": 91.0, "signal_threshold": 11.0},
            sleeve=1000.0,
            period="2y",
            timeframe="1d",
        )
        assert cfg.signal_threshold == 11.0
        assert not hasattr(cfg, "win_rate_pct")

    def test_apply_params_tolerates_none(self):
        cfg = LokiConfig()
        assert apply_params(cfg, None) == {}

    def test_report_cannot_override_account_fields(self):
        cfg = LokiConfig()
        applied = apply_params(
            cfg,
            {
                "mode": "live",
                "initial_cash": 1.0,
                "state_dir": "elsewhere",
                "period": "1mo",
                "alpaca_api_secret": "leaked",
                "signal_threshold": 30.0,
            },
        )
        assert cfg.mode == "paper"
        assert cfg.initial_cash == 100_000.0
        assert cfg.state_dir == "state"
        assert cfg.period == "2y"
        assert cfg.alpaca_api_secret is None
        assert applied == {"signal_threshold": 30.0}


class TestCryptoConsensusFallback:
    def test_uses_crypto_block(self):
        cfg = LokiConfig()
        applied = apply_crypto_consensus(book_with(), cfg)
        assert cfg.stop_loss_atr == 5.0
        assert applied["signal_threshold"] == 25.0

    def test_degrades_to_mixed_consensus(self):
        cfg = LokiConfig()
        apply_crypto_consensus(book_with(crypto_consensus=None), cfg)
        assert cfg.signal_threshold == 40.0

    def test_no_consensus_leaves_defaults(self):
        cfg = LokiConfig()
        before = cfg.signal_threshold
        assert apply_crypto_consensus({}, cfg) == {}
        assert cfg.signal_threshold == before


class TestCurveCombination:
    def test_single_curve_passes_through(self):
        curve = pd.Series([100.0, 110.0], index=pd.date_range("2026-01-01", periods=2))
        assert cp._combine_curves({"BTC-USD": curve}, 100.0).tolist() == [100.0, 110.0]

    def test_late_starting_symbol_contributes_its_sleeve(self):
        idx = pd.date_range("2026-01-01", periods=3)
        first = pd.Series([100.0, 100.0, 100.0], index=idx)
        second = pd.Series([50.0], index=idx[2:])
        combined = cp._combine_curves({"A": first, "B": second}, 50.0)
        assert combined.tolist() == [150.0, 150.0, 150.0]

    def test_missing_symbols_sum_to_full_capital(self):
        idx = pd.date_range("2026-01-01", periods=2)
        curves = {s: pd.Series([100.0, 105.0], index=idx) for s in ("BTC-USD", "ETH-USD")}
        assert cp._combine_curves(curves, 100.0).iloc[-1] == 210.0

    def test_empty_curves(self):
        assert cp._combine_curves({}, 10.0).empty


class TestSessionSummary:
    def trades(self):
        return [
            {"pnl": 100.0},
            {"pnl": -40.0},
            {"pnl": 20.0},
        ]

    def test_win_loss_arithmetic(self):
        curve = pd.Series([1000.0, 1080.0], index=pd.date_range("2026-01-01", periods=2))
        summary = cp._session_summary(self.trades(), curve, 1000.0, 500.0, 2)
        assert summary["pnl"] == 80.0
        assert summary["return_pct"] == 8.0
        assert summary["trades"] == 3
        assert summary["wins"] == 2 and summary["losses"] == 1
        assert summary["win_rate_pct"] == pytest.approx(66.7, abs=0.1)
        assert summary["profit_factor"] == pytest.approx(3.0)
        assert summary["avg_win"] == pytest.approx(60.0)
        assert summary["avg_loss"] == pytest.approx(40.0)

    def test_no_trades_does_not_divide_by_zero(self):
        curve = pd.Series([1000.0, 1000.0], index=pd.date_range("2026-01-01", periods=2))
        summary = cp._session_summary([], curve, 1000.0, 500.0, 2)
        assert summary["trades"] == 0
        assert summary["win_rate_pct"] == 0.0
        assert summary["profit_factor"] == 0.0

    def test_drawdown_measured_from_running_peak(self):
        curve = pd.Series(
            [1000.0, 1200.0, 900.0, 1100.0], index=pd.date_range("2026-01-01", periods=4)
        )
        summary = cp._session_summary([], curve, 1000.0, 500.0, 2)
        assert summary["max_drawdown_pct"] == pytest.approx(-25.0)


class TestAlpacaMirror:
    def test_crypto_symbol_uses_slash(self):
        assert cp.alpaca_symbol("BTC-USD") == "BTC/USD"
        assert cp.alpaca_symbol("eth-usd") == "ETH/USD"
        assert cp.alpaca_symbol("SPY") == "SPY"

    def test_qty_formatting_keeps_fractions_and_drops_zeros(self):
        assert cp._fmt_qty(0.0123456789) == "0.012345679"  # 9 decimals, rounded
        assert cp._fmt_qty(1.0) == "1"
        assert cp._fmt_qty(-3.0) == "0"

    def test_bad_side_fails_closed_without_network(self):
        ok, detail = cp.mirror_order("BTC-USD", "hold", 1.0, "k", "s")
        assert ok is False and "side" in detail["error"]

    def test_non_positive_qty_fails_closed_without_network(self):
        ok, detail = cp.mirror_order("BTC-USD", "buy", 0.0, "k", "s")
        assert ok is False and "qty" in detail["error"]

    def test_missing_keys_reports_instead_of_order(self, monkeypatch):
        monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_PAPER_API_SECRET", raising=False)
        result = cp._mirror_fills([{"symbol": "BTC-USD", "side": "buy", "qty": 1.0}])
        assert result[0]["mirrored"] is False
        assert "ALPACA_PAPER_API_KEY" in result[0]["reason"]

    def test_no_fills_no_report(self):
        assert cp._mirror_fills([]) == []


class TestReplayWindowGuard:
    def test_short_history_is_skipped_not_crashed(self, monkeypatch):
        """A symbol without warmup + window bars is reported, never simulated."""

        class FakeProvider:
            def fetch_history(self, symbol, period, interval):
                idx = pd.date_range("2026-01-01", periods=30, freq="D")
                return pd.DataFrame(
                    {
                        "open": 1.0,
                        "high": 1.1,
                        "low": 0.9,
                        "close": 1.0,
                        "volume": 10.0,
                    },
                    index=idx,
                )

        monkeypatch.setattr("loki_v8.data.get_provider", lambda: FakeProvider())
        payload = cp.replay(["BTC-USD"], report=book_with(), bars=180, write_ledger=False)
        assert payload["symbols"] == []
        assert payload["skipped"][0]["symbol"] == "BTC-USD"
        assert "need" in payload["skipped"][0]["reason"]
