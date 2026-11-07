"""
Tests for the v8 upgrade batch: regime engine, factor weighting, Monte Carlo
risk simulation, aggressive trainer mode, and the Supabase persistence layer.

All engine tests are offline (synthetic OHLCV bars); the persistence tests
monkeypatch the network layer.
"""

import numpy as np
import pandas as pd

from loki_v8 import train as T
from loki_v8.backtest import Trade
from loki_v8.config import LokiConfig
from loki_v8.regime import Regime, detect_regime, is_bearish, is_bullish, regime_distribution
from loki_v8.strategy import FACTOR_KEYS, EnsembleStrategy, normalize_weights


def synth_bars(n=420, seed=7, trend=40.0):
    """Trending + oscillating OHLCV series that produces crossing signals."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n, freq="D")
    drift = np.linspace(0.0, trend, n)
    cycle = 6.0 * np.sin(np.arange(n) / 11.0)
    close = 100.0 + drift + cycle + rng.normal(0.0, 0.8, n).cumsum() * 0.3
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = np.abs(rng.normal(0.0, 0.6, n)) + 0.2
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.integers(1_000_000, 3_000_000, n),
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Regime engine
# ---------------------------------------------------------------------------
class TestRegimeEngine:
    def test_default_regime_on_short_history(self):
        r = detect_regime(synth_bars(100))
        assert r.state == "RANGING"

    def test_helpers_cover_all_five_states(self):
        for st in ("STRONG_BULL", "BULL"):
            assert is_bullish(st) and not is_bearish(st)
        for st in ("BEAR", "CRISIS"):
            assert is_bearish(st) and not is_bullish(st)
        assert not is_bullish("RANGING") and not is_bearish("RANGING")

    def test_detect_regime_fields(self):
        r = detect_regime(synth_bars())
        assert r.state in ("STRONG_BULL", "BULL", "RANGING", "BEAR", "CRISIS")
        assert 0.0 <= r.confidence <= 100.0
        assert 0.0 <= r.volatility_rank <= 1.0
        assert r.description

    def test_distribution_sums_within_zero_one(self):
        cfg = LokiConfig()
        frame = EnsembleStrategy(cfg).compute_factors(synth_bars())
        dist = regime_distribution(frame)
        assert sum(dist.values()) <= 1.001
        assert all(k in ("STRONG_BULL", "BULL", "RANGING", "BEAR", "CRISIS") for k in dist)

    def test_regime_dataclass_defaults(self):
        r = Regime()
        assert r.state == "RANGING" and r.description


# ---------------------------------------------------------------------------
# Multi-factor weighting
# ---------------------------------------------------------------------------
class TestFactorWeights:
    def test_normalize_defaults_sum_to_one(self):
        w = normalize_weights(None)
        assert set(w) == set(FACTOR_KEYS)
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_normalize_rejects_all_zero(self):
        w = normalize_weights({k: 0.0 for k in FACTOR_KEYS})
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_factor_columns_present(self):
        cfg = LokiConfig()
        f = EnsembleStrategy(cfg).compute_factors(synth_bars())
        for k in FACTOR_KEYS:
            assert f"f_{k}" in f.columns
        # factor columns are bounded (ignore indicator warmup NaNs)
        for k in FACTOR_KEYS:
            col = f[f"f_{k}"].dropna()
            assert len(col) > 0
            assert col.abs().max() <= 1.0 + 1e-9

    def test_weights_change_composite_score(self):
        cfg = LokiConfig()
        s = EnsembleStrategy(cfg)
        f = s.compute_factors(synth_bars())
        trend_only = s.score_from_factors(f, {"trend": 1.0})
        mom_only = s.score_from_factors(f, {"momentum": 1.0})
        assert not np.allclose(trend_only["score"], mom_only["score"])

    def test_score_bounded(self):
        cfg = LokiConfig()
        s = EnsembleStrategy(cfg)
        out = s.score_frame(synth_bars())
        assert out["score"].abs().max() <= 100.0 + 1e-9


# ---------------------------------------------------------------------------
# Monte Carlo risk engine
# ---------------------------------------------------------------------------
class TestTrainerUpgrades:
    def test_monthly_profitability_metric(self):
        bars = synth_bars()
        cfg = LokiConfig()
        rep = T.train_symbol(
            bars,
            cfg,
            "TEST",
            grid={
                "signal_threshold": [20.0],
                "stop_loss_atr": [2.0],
                "take_profit_atr": [3.0],
                "require_trend_filter": [True],
            },
        )
        assert rep.ok
        assert "month_profit_rate_pct" in rep.validation_metrics

    def test_check_hurdles_target_override(self):
        vm = {
            "trades": 10,
            "return_pct": 5.0,
            "win_rate_pct": 72.0,
            "profit_factor": 2.0,
            "max_drawdown_pct": -10.0,
            "month_profit_rate_pct": 55.0,
        }
        defaults = T.check_hurdles(vm)
        assert len(defaults) == 5

        checks = T.check_hurdles(vm, {"win_rate_pct": 90.0})
        win_check = next(c for c in checks if c["key"] == "win_rate_pct")
        assert not win_check["ok"] and win_check["target"] == 90.0

        checks2 = T.check_hurdles(vm, {"month_profit_rate_pct": 50.0})
        assert any(c["key"] == "month_profit_rate_pct" and c["ok"] for c in checks2)
        # months hurdle only added when an explicit target is passed
        assert not any(c["key"] == "month_profit_rate_pct" for c in defaults)

    def test_refined_grid_small_window(self):
        base_grid = dict(T.DEFAULT_GRID)
        refined = T._refined_grid(
            base_grid,
            {
                "signal_threshold": 25.0,
                "stop_loss_atr": 2.5,
                "take_profit_atr": 4.0,
                "require_trend_filter": False,
            },
        )
        assert refined["require_trend_filter"] == [False]
        assert 25.0 in refined["signal_threshold"]
        assert 2.5 in refined["stop_loss_atr"]
        assert 4.0 in refined["take_profit_atr"]
        size = 1
        for v in refined.values():
            size *= len(v)
        assert size <= T._REFINE_MAX_COMBOS

    def test_consensus_and_apply(self):
        entries = [
            {
                "ok": True,
                "best_params": {
                    "signal_threshold": 20.0,
                    "stop_loss_atr": 2.0,
                    "take_profit_atr": 3.0,
                    "require_trend_filter": True,
                },
                "factor_preset": "trend_leader",
            },
            {
                "ok": True,
                "best_params": {
                    "signal_threshold": 30.0,
                    "stop_loss_atr": 2.0,
                    "take_profit_atr": 3.0,
                    "require_trend_filter": False,
                },
                "factor_preset": "trend_leader",
            },
        ]
        cons = T.consensus_params(entries)
        p = cons["params"]
        assert p["signal_threshold"] == 25.0
        assert isinstance(p["require_trend_filter"], bool)
        assert p["factor_preset"] == "trend_leader"

        cfg = LokiConfig()
        applied = T.apply_consensus({"consensus": cons}, cfg)
        assert applied["signal_threshold"] == 25.0
        assert cfg.signal_threshold == 25.0

    def test_objective_changes_ranking(self):
        e_sharpe = {
            "params": {},
            "train": {
                "trades": 10,
                "sharpe": 1.5,
                "profit_factor": 2.0,
                "return_pct": 20.0,
                "win_rate_pct": 40.0,
            },
        }
        e_winrate = {
            "params": {},
            "train": {
                "trades": 10,
                "sharpe": 0.5,
                "profit_factor": 1.1,
                "return_pct": 5.0,
                "win_rate_pct": 92.0,
            },
        }
        assert max(e_sharpe, e_winrate, key=lambda e: T._rank_key(e, "sharpe")) is e_sharpe
        assert max(e_sharpe, e_winrate, key=lambda e: T._rank_key(e, "win_rate")) is e_winrate

    def test_apply_best_copies_weights(self):

        cfg = LokiConfig()
        params = {
            "signal_threshold": 18.0,
            "factor_weights": {
                "trend": 2.0,
                "momentum": 1.0,
                "volume_flow": 1.0,
                "squeeze": 1.0,
                "volatility": 1.0,
            },
        }
        rep = {"symbols": [{"symbol": "TEST", "ok": True, "best_params": params}]}
        applied = T.apply_best(rep, "test", cfg)
        assert cfg.signal_threshold == 18.0
        assert abs(sum(cfg.factor_weights.values()) - 1.0) < 1e-9
        assert "factor_weights" in applied

    def test_train_symbol_honors_explicit_hurdle_targets(self):
        bars = synth_bars()
        cfg = LokiConfig()
        rep = T.train_symbol(
            bars,
            cfg,
            "TEST",
            grid={
                "signal_threshold": [18.0, 25.0],
                "stop_loss_atr": [1.5, 2.5],
                "take_profit_atr": [2.5, 4.0],
                "require_trend_filter": [True, False],
            },
            hurdle_targets={"win_rate_pct": 99.0},
        )
        assert rep.ok
        win_check = next(c for c in rep.hurdles if c["key"] == "win_rate_pct")
        assert win_check["target"] == 99.0
        # 99% win rate isn't happening — the report must say so honestly
        assert win_check["ok"] is False


# ---------------------------------------------------------------------------
# Supabase persistence layer
# ---------------------------------------------------------------------------