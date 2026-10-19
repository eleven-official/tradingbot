"""
Tests for the v8 upgrade batch: regime engine, factor weighting, Monte Carlo
risk simulation, aggressive trainer mode, and the Supabase persistence layer.

All engine tests are offline (synthetic OHLCV bars); the persistence tests
monkeypatch the network layer.
"""

import numpy as np
import pandas as pd
import pytest

from loki_v8 import train as T
from loki_v8.backtest import Trade
from loki_v8.config import LokiConfig
from loki_v8.montecarlo import monte_carlo_simulation
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
class TestMonteCarlo:
    def _trades(self):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        wins = [
            Trade("X", "long", idx[i], idx[i], 100, 101, 1, 10.0, 1.0, "target") for i in range(36)
        ]  # +1%
        losses = [
            Trade("X", "long", idx[i], idx[i], 100, 96, 1, -40.0, -4.0, "stop") for i in range(4)
        ]
        return wins + losses

    def test_deterministic_with_seed(self):
        a = monte_carlo_simulation(self._trades(), n_sims=300, seed=42)
        b = monte_carlo_simulation(self._trades(), n_sims=300, seed=42)
        assert a["final_return"] == b["final_return"]

    def test_high_win_rate_stats(self):
        mc = monte_carlo_simulation(self._trades(), n_sims=500, seed=1)
        assert mc["prob_profit_pct"] >= 95.0
        assert mc["fan"]["p50"][0] == 100000.0
        assert len(mc["fan"]["p50"]) == 41  # n trades + start step
        assert mc["verdict"] in ("ROBUST", "ACCEPTABLE", "FRAGILE", "DANGEROUS")

    def test_empty_trades_safe(self):
        mc = monte_carlo_simulation([], n_sims=100)
        assert mc["verdict"] == "NO_TRADES" and mc["n_sims"] == 0

    def test_var_cvar_ordered(self):
        mc = monte_carlo_simulation(self._trades(), n_sims=500, seed=3)
        assert mc["cvar_95_pct"] <= mc["var_95_pct"]


# ---------------------------------------------------------------------------
# Trainer: aggressive objective, hurdles, refinement, consensus
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
        import dataclasses

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
class TestPersistence:
    def _post_capture(self, monkeypatch, status=201, raise_exc=None):
        calls = []

        def fake_post(method, url, json, headers, timeout, params, allow_redirects):
            calls.append({"method": method, "url": url, "row": json[0] if json else None, "apikey": headers.get("apikey")})
            if raise_exc:
                raise raise_exc

            class R:
                status_code = status
                text = "ok"
                content = b"[]"
                def json(self):
                    return []

            return R()

        monkeypatch.setattr("requests.request", fake_post)
        return calls

    def test_not_configured_is_noop(self, monkeypatch):
        from loki_v8.persistence import SupabaseLogger

        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
        lg = SupabaseLogger()
        assert not lg.configured()
        r = lg.test_connection()
        assert r["reason"] == "not_configured"

    def test_trade_log_posts_row(self, monkeypatch):
        from loki_v8.persistence import SupabaseLogger

        monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test_key")
        calls = self._post_capture(monkeypatch)
        lg = SupabaseLogger()
        lg.log_trade(
            symbol="AAPL",
            side="long",
            qty=1,
            entry_price=100.0,
            exit_price=110.0,
            pnl=10.0,
            pnl_pct=10.0,
            exit_reason="target",
        )
        lg.flush()
        row = calls[0]["row"]
        assert calls[0]["url"].endswith("/rest/v1/loki_trades")
        assert row["symbol"] == "AAPL" and row["pnl_pct"] == 10.0
        assert calls[0]["apikey"] == "sb_secret_test_key"

    def test_network_failure_never_raises(self, monkeypatch):
        from loki_v8.persistence import SupabaseLogger

        monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test_key")
        self._post_capture(monkeypatch, raise_exc=ConnectionError("boom"))
        lg = SupabaseLogger()
        r = lg.test_connection()
        assert r["ok"] is False
        st = lg.status()
        assert st["failures"] >= 1 and "Vault connection failed" in (st["last_error"] or "")

    def test_http_error_counted(self, monkeypatch):
        from loki_v8.persistence import SupabaseLogger

        monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "sb_secret_test_key")
        self._post_capture(monkeypatch, status=401)
        lg = SupabaseLogger()
        r = lg.test_connection()
        assert r["ok"] is False
        assert lg.status()["failures"] >= 1

    def test_status_reports_schema_env(self, monkeypatch):
        from loki_v8.persistence import SupabaseLogger

        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
        st = SupabaseLogger().status()
        assert st["schema_file"] == "supabase_schema.sql"
        assert "SUPABASE_URL" in st["env_vars"][0]
