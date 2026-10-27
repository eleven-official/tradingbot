"""
Tests for walk-forward selection and the expectancy ranking objective.

All offline: synthetic OHLCV frames, canned metric dicts, no network and no
clock. The rule being pinned down here is "the winner is the candidate whose
worst forward fold survived", plus the expectation objective that replaced the
hit-rate chase — a 92%-win profile with a 7:1 stop geometry must not outrank a
45%-win profile with the same total return.
"""

import numpy as np
import pandas as pd
import pytest

from loki_v8 import train as T
from loki_v8.config import LokiConfig
from loki_v8.strategy import EnsembleStrategy


def synthetic_bars(n=420, seed=7):
    """Trending + oscillating OHLCV series that produces crossing signals."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n, freq="D")
    drift = np.linspace(0.0, 40.0, n)
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
            "volume": rng.uniform(5e5, 2e6, n),
        },
        index=idx,
    )


SMALL_GRID = {
    "signal_threshold": [18.0, 30.0],
    "stop_loss_atr": [1.5, 2.5],
    "take_profit_atr": [2.5],
    "require_trend_filter": [True],
}


def _metrics(**overrides):
    base = {
        "trades": 30,
        "return_pct": 9.0,
        "win_rate_pct": 55.0,
        "profit_factor": 1.6,
        "max_drawdown_pct": -8.0,
        "month_profit_rate_pct": 60.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# fold_bounds
# ---------------------------------------------------------------------------


class TestFoldBounds:
    def test_folds_start_at_or_after_the_sweep_split(self):
        for n in (200, 420, 2500):
            for first_frac in (0.5, 0.7, 0.9):
                folds = T.fold_bounds(n, folds=2, first_frac=first_frac)
                assert folds, (n, first_frac)
                assert folds[0][0] >= int(n * first_frac) - 1

    def test_folds_are_contiguous_ordered_and_bounded(self):
        n = 1000
        folds = T.fold_bounds(n, folds=3, first_frac=0.7)
        assert len(folds) == 3
        for i, (train_end, val_end) in enumerate(folds):
            assert 0 <= train_end < val_end <= n
            if i:
                prev_val_end = folds[i - 1][1]
                assert train_end == prev_val_end
            # Each fold validates at least two bars, otherwise scoring is noise.
            assert val_end - train_end >= 2

    def test_single_fold_covers_the_whole_forward_window(self):
        n = 500
        (train_end, val_end), *rest = T.fold_bounds(n, folds=1, first_frac=0.7)
        assert rest == []
        assert val_end == n
        assert train_end >= int(n * 0.7) - 1

    def test_degenerate_inputs_return_no_folds(self):
        assert T.fold_bounds(0) == []
        assert T.fold_bounds(3) == []
        # clamps rather than raising on nonsense fractions
        assert T.fold_bounds(100, folds=2, first_frac=5.0)


# ---------------------------------------------------------------------------
# expectancy objective
# ---------------------------------------------------------------------------


class TestExpectancyObjective:
    def test_small_target_high_hit_rate_loses_to_real_expectancy(self):
        # Same total return. The hit-rate profile earns it in many tiny wins
        # behind a huge stop; the trend profile earns it in fewer, bigger ones.
        grinder = {
            "params": {},
            "train": _metrics(
                trades=80, return_pct=6.0, win_rate_pct=92.0, profit_factor=1.30
            ),
        }
        trend = {
            "params": {},
            "train": _metrics(
                trades=24, return_pct=6.0, win_rate_pct=44.0, profit_factor=1.30
            ),
        }
        assert T._rank_key(trend, "expectancy") > T._rank_key(grinder, "expectancy")
        board = sorted([grinder, trend], key=lambda e: T._rank_key(e, "expectancy"))
        assert board[-1] is trend

    def test_profit_factor_floor_beats_raw_expectancy(self):
        # A knockout trade can push mean return up on a thin sample; the pf
        # band sits ahead of it so a sub-1.25 profile cannot win on one outlier.
        outlier = {
            "params": {},
            "train": _metrics(
                trades=25, return_pct=30.0, win_rate_pct=20.0, profit_factor=1.1
            ),
        }
        steady = {
            "params": {},
            "train": _metrics(
                trades=25, return_pct=8.0, win_rate_pct=50.0, profit_factor=1.8
            ),
        }
        assert T._rank_key(steady, "expectancy") > T._rank_key(outlier, "expectancy")

    def test_thin_sample_cannot_win(self):
        lucky = {"params": {}, "train": _metrics(trades=2, return_pct=60.0)}
        real = {"params": {}, "train": _metrics(trades=30, return_pct=4.0)}
        assert T._rank_key(real, "expectancy") > T._rank_key(lucky, "expectancy")

    def test_expectancy_is_mean_return_per_trade(self):
        a = {"params": {}, "train": _metrics(trades=20, return_pct=10.0)}
        b = {"params": {}, "train": _metrics(trades=40, return_pct=10.0)}
        # Same return over twice the trades is a worse edge per trade. Both
        # clear the rich-trade floor, so expectancy is what separates them.
        assert T._rank_key(a, "expectancy") > T._rank_key(b, "expectancy")

    def test_objective_is_a_stable_total_order(self):
        entries = [
            {"params": {"i": i}, "train": _metrics(trades=5 + i, return_pct=1.0 * i)}
            for i in range(12)
        ]
        first = sorted(entries, key=lambda e: T._rank_key(e, "expectancy"))
        second = sorted(entries, key=lambda e: T._rank_key(e, "expectancy"))
        assert [e["params"]["i"] for e in first] == [e["params"]["i"] for e in second]
        keys = [T._rank_key(e, "expectancy") for e in first]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# walk_forward_score
# ---------------------------------------------------------------------------


class TestWalkForwardScore:
    def _fixture(self, n=520):
        df = synthetic_bars(n=n)
        cfg = LokiConfig(lookback_bars=20)
        strategy = EnsembleStrategy(cfg)
        factors = strategy.compute_factors(df)
        return df, cfg, strategy, factors

    def test_scores_one_entry_per_fold_and_is_deterministic(self):
        df, cfg, strategy, factors = self._fixture()
        entry = {"params": {"signal_threshold": 18.0, "stop_loss_atr": 2.0}}
        args = (entry, factors, df, cfg, strategy, int(len(df) * 0.7), 60, 365)

        first = T.walk_forward_score(*args, symbol="TEST", folds=2)
        second = T.walk_forward_score(*args, symbol="TEST", folds=2)

        assert len(first["folds"]) == 2
        assert first["score"] == second["score"]
        assert first["worst_fold_pf"] == second["worst_fold_pf"]
        assert first["trades"] == second["trades"]
        for fold in first["folds"]:
            assert fold["start"] < fold["end"]
            assert "profit_factor" in fold
            assert "return_pct" in fold

    def test_worst_fold_drives_the_score(self):
        df, cfg, strategy, factors = self._fixture()
        entry = {"params": {"signal_threshold": 18.0}}
        wf = T.walk_forward_score(
            entry, factors, df, cfg, strategy, int(len(df) * 0.7), 60, 365,
            symbol="TEST", folds=2,
        )
        fold_pfs = [f["profit_factor"] for f in wf["folds"]]
        if fold_pfs:
            assert wf["worst_fold_pf"] == pytest.approx(min(fold_pfs), abs=0.01)

    def test_unusable_input_returns_a_losing_score_instead_of_raising(self):
        df, cfg, strategy, factors = self._fixture(n=120)
        # No fold can validate inside 120 bars at first_frac 0.7 with 2 folds.
        wf = T.walk_forward_score(
            {"params": {}}, factors, df, cfg, strategy, int(len(df) * 0.7), 60, 365,
            symbol="TEST", folds=2,
        )
        assert wf["folds"] == [] or wf["score"][0] == 0.0
        assert wf["score"] < (1.0, 1e9, 1e9, 1e9)


# ---------------------------------------------------------------------------
# train_symbol wiring
# ---------------------------------------------------------------------------


class TestTrainSymbolSelection:
    def test_walk_forward_off_keeps_the_leaderboard_winner(self):
        rep = T.train_symbol(
            synthetic_bars(), LokiConfig(), "TEST", grid=SMALL_GRID, train_frac=0.7
        )
        assert rep.ok, rep.error
        assert rep.selection == "leaderboard"
        assert rep.walk_forward == {}

    def test_walk_forward_on_records_selection_and_promotes_a_finalist(self):
        rep = T.train_symbol(
            synthetic_bars(n=520),
            LokiConfig(),
            "TEST",
            grid=SMALL_GRID,
            train_frac=0.7,
            top_n=2,
            objective="expectancy",
            walk_forward=True,
            folds=2,
        )
        assert rep.ok, rep.error
        assert rep.selection == "walk_forward"
        assert rep.walk_forward["folds"] == 2
        assert rep.walk_forward["finalists"] >= 2
        assert "worst_fold_pf" in rep.walk_forward
        # The promoted winner is still leaderboard[0] and still drives best_params.
        assert rep.leaderboard[0]["params"] == rep.best_params
        assert "walk_forward" in rep.leaderboard[0]
        # Every scored finalist carries its fold detail.
        scored = [e for e in rep.leaderboard if "walk_forward" in e]
        assert len(scored) >= 2
        for entry in scored:
            assert "folds" in entry["walk_forward"]

    def test_walk_forward_promotes_the_best_worst_fold(self, monkeypatch):
        # Force fold scores so the in-sample runner-up is the forward winner.
        ranks = iter([(1.0, 0.4, -1.0, 3.0), (1.0, 2.5, 4.0, 9.0)])

        def fake_wf(*args, **kwargs):
            score = next(ranks)
            return {
                "folds": [{"profit_factor": score[1], "return_pct": score[2]}],
                "worst_fold_pf": score[1],
                "mean_return_pct": score[2],
                "worst_drawdown_pct": -3.0,
                "trades": int(score[3]),
                "min_fold_trades": 1,
                "score": score,
            }

        monkeypatch.setattr(T, "walk_forward_score", fake_wf)
        rep = T.train_symbol(
            synthetic_bars(n=520),
            LokiConfig(),
            "TEST",
            grid=SMALL_GRID,
            train_frac=0.7,
            top_n=2,
            walk_forward=True,
        )
        assert rep.ok, rep.error
        assert rep.selection == "walk_forward"
        assert rep.walk_forward["rank_promoted_from"] == 1
        assert rep.leaderboard[0]["walk_forward"]["worst_fold_pf"] == 2.5
        assert rep.best_params == rep.leaderboard[0]["params"]


# ---------------------------------------------------------------------------
# edge-weighted consensus
# ---------------------------------------------------------------------------


class TestEdgeWeightedConsensus:
    def test_strong_out_of_sample_profile_pulls_the_consensus(self):
        strong = {
            "ok": True,
            "best_params": {"signal_threshold": 30.0, "stop_loss_atr": 3.0},
            "validation_metrics": {"trades": 60, "return_pct": 12.0, "profit_factor": 3.0},
            "factor_preset": "trend_leader",
        }
        weak_a = {
            "ok": True,
            "best_params": {"signal_threshold": 8.0, "stop_loss_atr": 1.5},
            "validation_metrics": {"trades": 30, "return_pct": 0.4, "profit_factor": 1.05},
            "factor_preset": "defensive_flow",
        }
        weak_b = dict(weak_a, validation_metrics={"trades": 30, "return_pct": 0.5, "profit_factor": 1.06})
        cons = T.consensus_params([weak_a, weak_b, strong])
        assert cons["edge_weighted"] is True
        # Two weak votes no longer outvote the one profile with real edge.
        assert cons["params"]["signal_threshold"] > 20.0

    def test_metrics_free_book_is_still_a_plain_median(self):
        entries = [
            {"ok": True, "best_params": {"signal_threshold": 20.0}},
            {"ok": True, "best_params": {"signal_threshold": 30.0}},
        ]
        cons = T.consensus_params(entries)
        assert cons["params"]["signal_threshold"] == 25.0
        assert cons["edge_weighted"] is False

    def test_symbol_with_no_out_of_sample_trades_gets_a_whisper_of_a_vote(self):
        never_traded = {
            "ok": True,
            "best_params": {"signal_threshold": 45.0},
            "validation_metrics": {"trades": 0, "return_pct": 0.0, "profit_factor": 0.0},
        }
        real = [
            {
                "ok": True,
                "best_params": {"signal_threshold": 10.0},
                "validation_metrics": {"trades": 40, "return_pct": 5.0, "profit_factor": 1.8},
            },
            {
                "ok": True,
                "best_params": {"signal_threshold": 12.0},
                "validation_metrics": {"trades": 40, "return_pct": 6.0, "profit_factor": 1.9},
            },
        ]
        cons = T.consensus_params(real + [never_traded])
        assert cons["params"]["signal_threshold"] <= 12.0

    def test_weighted_median_matches_plain_median_when_weights_are_equal(self):
        values = [3.0, 1.0, 2.0, 9.0]
        assert T._weighted_median(values, [1.0] * 4) == pytest.approx(
            float(pd.Series(values).median())
        )

    def test_consensus_survives_malformed_metrics(self):
        entries = [
            {"ok": True, "best_params": {"signal_threshold": 20.0}, "validation_metrics": {"return_pct": "n/a"}},
            {"ok": True, "best_params": {"signal_threshold": 30.0}, "validation_metrics": None},
        ]
        cons = T.consensus_params(entries)
        assert cons["params"]["signal_threshold"] == pytest.approx(25.0, abs=5.0)



# ---------------------------------------------------------------------------
# grid + hurdle definitions used by the crypto sweep
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# snapshot merge: a failed re-run must not demote a verified profile
# ---------------------------------------------------------------------------


class TestSnapshotMerge:
    def test_failed_rerun_keeps_the_verified_profile(self):
        from loki_v8 import train_crypto as C

        existing = {
            "symbols": [
                {"symbol": "BTC-USD", "ok": True, "good": True, "best_params": {"signal_threshold": 14.0}},
                {"symbol": "OLD-USD", "ok": True, "good": True, "best_params": {}},
            ]
        }
        fresh = [{"symbol": "BTC-USD", "ok": False, "error": "worker crashed"}]
        merged = {e["symbol"]: e for e in C._merge(existing, fresh)}
        assert merged["BTC-USD"]["ok"] is True
        assert merged["BTC-USD"]["stale_reason"] == "worker crashed"
        # Untouched symbols are still carried forward.
        assert merged["OLD-USD"]["ok"] is True

    def test_fresh_trained_profile_wins_over_the_stored_one(self):
        from loki_v8 import train_crypto as C

        existing = {"symbols": [{"symbol": "BTC-USD", "ok": True, "best_params": {"signal_threshold": 30.0}}]}
        fresh = [{"symbol": "BTC-USD", "ok": True, "good": True, "best_params": {"signal_threshold": 14.0}}]
        merged = {e["symbol"]: e for e in C._merge(existing, fresh)}
        assert merged["BTC-USD"]["best_params"]["signal_threshold"] == 14.0

    def test_failed_symbol_with_no_history_stays_failed(self):
        from loki_v8 import train_crypto as C

        merged = {e["symbol"]: e for e in C._merge({"symbols": []}, [{"symbol": "X", "ok": False, "error": "no data"}])}
        assert merged["X"]["ok"] is False


class TestCryptoGridShape:
    def test_grid_is_not_the_hit_rate_geometry(self):
        from loki_v8 import train_crypto as C

        grid = C.CRYPTO_GRID
        # Take-profit is allowed to exceed the stop: a 45% profile must be
        # able to clear the hurdles, which the 1.0-ATR cap made impossible.
        assert max(grid["take_profit_atr"]) > min(grid["stop_loss_atr"])
        assert min(grid["stop_loss_atr"]) >= 2.0
        assert C._grid_size(grid) == 108

    def test_hurdles_do_not_require_a_hit_rate_that_forces_a_tiny_target(self):
        from loki_v8 import train_crypto as C

        assert C.CRYPTO_HURDLES["win_rate_pct"] <= 50.0
        assert C.CRYPTO_HURDLES["profit_factor"] >= 1.5
        assert C.CRYPTO_HURDLES["trades"] >= 10.0
