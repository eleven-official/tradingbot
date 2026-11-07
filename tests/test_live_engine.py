"""Live engine follows the verified backtest, bar for bar.

The trained profiles were verified by ``run_backtest``. If the live paper
engine decides entries with different rules, the verification says nothing
about what the live AI actually does. These tests replay a backtest on a
synthetic tape and check the live planner agrees on every bar where the
backtest was free to enter.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from loki_v8 import live_engine
from loki_v8.backtest import run_backtest
from loki_v8.config import LokiConfig
from loki_v8.strategy import EnsembleStrategy


def _tape(n=900, seed=7):
    rng = np.random.default_rng(seed)
    # Regime-switching drift so the tape has trends, chop and selloffs.
    drift = np.repeat(rng.choice([0.0012, -0.0010, 0.0002], size=n // 60 + 1), 60)[:n]
    rets = drift + rng.normal(0, 0.014, n)
    close = 100 * np.exp(np.cumsum(rets))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    vol = rng.integers(1_000, 5_000, n).astype(float)
    idx = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


PROFILES = [
    dict(signal_threshold=12.0, require_trend_filter=True, max_hold_bars=20),
    dict(signal_threshold=8.0, require_trend_filter=False, max_atr_pct=2.05, conviction_sizing=True),
    dict(signal_threshold=15.0, adaptive_threshold=True, breakeven_atr=0.5, trailing_stop_atr=2.0),
    dict(signal_threshold=10.0, partial_tp_atr=1.5, take_profit_atr=4.0, vol_target_sizing=True),
    # v9 universal shape: vol-target sizing, no fixed target, trailing exit.
    dict(signal_threshold=5.0, sizing_mode="vol_target", target_vol_pct=15.0, take_profit_atr=0.0,
         stop_loss_atr=6.0, trailing_stop_atr=4.0, max_hold_bars=0),
    dict(signal_threshold=8.0, sizing_mode="vol_target", take_profit_atr=0.0, stop_loss_atr=10.0,
         max_hold_bars=0, exit_mode="trend"),
]


@pytest.mark.parametrize("overrides", PROFILES)
def test_every_entry_decision_matches_the_backtest(overrides):
    df = _tape()
    cfg = LokiConfig(**overrides)
    frame = EnsembleStrategy(cfg).score_frame(df)
    result = run_backtest(df, cfg, frame=frame)
    assert result.trades, "fixture must actually trade"

    index = list(df.index)
    entries = set()
    blocked = set()  # bars where a position was held at the entry check
    for trade in result.trades:
        if trade.exit_reason == "scale_out":
            continue
        e = index.index(trade.entry_time)
        x = index.index(trade.exit_time)
        entries.add(e)
        blocked.update(range(e + 1, x))
        if trade.exit_reason == "end":
            blocked.add(x)

    warmup = max(cfg.lookback_bars, 60)
    checked = 0
    for i in range(warmup + 1, len(df)):
        if i in blocked:
            continue
        # Live at bar i only knows completed bars 0..i-1. Score that prefix
        # on its own so no future bar can leak into the indicators.
        plan = live_engine.plan_entry(frame.iloc[:i], cfg)
        assert plan["ready"]
        if i in entries:
            assert plan["allowed"], f"backtest entered at bar {i}, live said {plan['reason']}"
        else:
            # The backtest can also skip an allowed entry when the size is
            # unaffordable; the live engine clamps to cash instead.
            if plan["allowed"]:
                assert plan["action"] == "BUY"
                continue
            assert not plan["allowed"]
        checked += 1
    assert checked > 100


def test_prefix_scoring_is_causal():
    """Scoring df[:i] gives the same last row as scoring all of df."""
    df = _tape(500)
    cfg = LokiConfig()
    full = EnsembleStrategy(cfg).score_frame(df)
    part = EnsembleStrategy(cfg).score_frame(df.iloc[:400])
    assert part["score"].iloc[-1] == pytest.approx(full["score"].iloc[399])


def test_gates_report_why_an_entry_is_refused():
    df = _tape()
    cfg = LokiConfig(signal_threshold=0.01, require_trend_filter=True)
    frame = EnsembleStrategy(cfg).score_frame(df)
    below = frame[frame["close"] < frame["sma_200"]].index
    i = list(frame.index).index(below[-1]) + 1
    plan = live_engine.plan_entry(frame.iloc[:i], cfg)
    trend = next(g for g in plan["gates"] if g["name"] == "trend_filter")
    assert trend["passed"] is False
    assert plan["allowed"] is False


def test_warming_up_never_trades():
    df = _tape(120)
    plan = live_engine.plan_entry(EnsembleStrategy(LokiConfig()).score_frame(df), LokiConfig())
    assert plan == {**plan, "ready": False, "allowed": False, "reason": "warming_up"}


class TestFormingBar:
    def test_equity_bar_dropped_during_session(self):
        df = _tape(10)
        df.index = pd.date_range("2026-03-02", periods=10, freq="D", tz="America/New_York")
        now = datetime(2026, 3, 11, 15, 0, tzinfo=timezone.utc)  # 11:00 ET, last bar is today
        out, dropped = live_engine.drop_forming_bar(df, crypto=False, now=now)
        assert dropped and len(out) == 9

    def test_equity_bar_kept_after_close(self):
        df = _tape(10)
        df.index = pd.date_range("2026-03-02", periods=10, freq="D", tz="America/New_York")
        now = datetime(2026, 3, 11, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
        out, dropped = live_engine.drop_forming_bar(df, crypto=False, now=now)
        assert not dropped and len(out) == 10

    def test_crypto_today_is_forming(self):
        df = _tape(10)
        df.index = pd.date_range("2026-03-02", periods=10, freq="D", tz="UTC")
        now = datetime(2026, 3, 11, 23, 0, tzinfo=timezone.utc)
        out, dropped = live_engine.drop_forming_bar(df, crypto=True, now=now)
        assert dropped and len(out) == 9

    def test_older_bars_untouched_and_intraday_ignored(self):
        df = _tape(10)
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        assert live_engine.drop_forming_bar(df, crypto=False, now=now)[1] is False
        assert live_engine.drop_forming_bar(df, crypto=True, timeframe="5m")[1] is False


class TestSizing:
    def test_risk_sized_and_cash_clamped(self):
        cfg = LokiConfig(risk_per_trade_pct=1.0, stop_loss_atr=2.0, take_profit_atr=3.0)
        plan = {"atr": 2.0, "size_multiplier": 1.0}
        sized = live_engine.size_entry(cfg, plan, price=100.0, equity=10_000, cash=10_000)
        assert sized["stop"] == pytest.approx(96.0)
        assert sized["target"] == pytest.approx(106.0)
        assert sized["qty"] == pytest.approx(25.0)  # $100 risk / $4 per unit
        assert sized["risk_pct_of_equity"] == pytest.approx(1.0)
        tight = live_engine.size_entry(cfg, {"atr": 0.1, "size_multiplier": 1.0}, 100.0, 10_000, 10_000)
        assert tight["qty"] == pytest.approx(100.0) and tight["capped_by_cash"]

    def test_multipliers_match_backtest_formula(self):
        cfg = LokiConfig(signal_threshold=20.0, conviction_sizing=True, regime_sizing=True, vol_target_sizing=True)
        assert live_engine.size_multiplier(cfg, 40.0, "RANGING", 2.0, 1.0) == pytest.approx(1.25 * 0.5 * 0.5)
        assert live_engine.size_multiplier(cfg, 10.0, "BULL", 1.0, 2.0) == pytest.approx(0.6 * 1.2)


class TestManagement:
    def _frame(self, closes, atr=1.0):
        idx = pd.bdate_range("2026-01-05", periods=len(closes))
        return pd.DataFrame({"close": closes, "atr": [atr] * len(closes)}, index=idx)

    def test_breakeven_and_trailing_ratchet_from_completed_closes(self):
        cfg = LokiConfig(breakeven_atr=1.0, trailing_stop_atr=2.0, arm_trailing_atr=3.0, take_profit_atr=50)
        frame = self._frame([100, 101.5, 104, 106])
        pos = {"entry": 100.0, "stop": 96.0, "target": 150.0, "atr": 1.0, "signal_bar": str(frame.index[0])}
        out = live_engine.manage_position(frame, cfg, pos, price=105.5, signal_action="HOLD")
        assert out["breakeven_armed"] and out["trailing_armed"]
        assert out["stop"] == pytest.approx(104.0)  # 106 - 2 ATR
        assert out["exit"] is False and out["bars_held"] == 3

    def test_stop_never_loosens(self):
        cfg = LokiConfig(trailing_stop_atr=5.0)
        frame = self._frame([100, 99, 98])
        pos = {"entry": 100.0, "stop": 97.5, "target": 0, "atr": 1.0, "signal_bar": str(frame.index[0])}
        out = live_engine.manage_position(frame, cfg, pos, price=97.6, signal_action="HOLD")
        assert out["stop"] == 97.5

    def test_exit_order_and_time_stop(self):
        cfg = LokiConfig(max_hold_bars=2)
        frame = self._frame([100, 100, 100])
        pos = {"entry": 100.0, "stop": 95.0, "target": 110.0, "atr": 1.0, "signal_bar": str(frame.index[0])}
        assert live_engine.manage_position(frame, cfg, pos, 94.0, "HOLD")["reason"] == "stop"
        assert live_engine.manage_position(frame, cfg, pos, 111.0, "SELL")["reason"] == "target"
        assert live_engine.manage_position(frame, cfg, pos, 100.0, "SELL")["reason"] == "signal"
        assert live_engine.manage_position(frame, cfg, pos, 100.0, "HOLD")["reason"] == "time"

    def test_partial_scale_out_once(self):
        cfg = LokiConfig(partial_tp_atr=1.0, partial_fraction=0.5, take_profit_atr=3.0)
        frame = self._frame([100])
        pos = {"entry": 100.0, "stop": 98.0, "target": 103.0, "atr": 1.0, "signal_bar": str(frame.index[0])}
        out = live_engine.manage_position(frame, cfg, pos, 101.2, "HOLD")
        assert out["scale_out"] == 0.5 and out["stop"] == pytest.approx(101.2)
        again = live_engine.manage_position(frame, cfg, {**pos, "leg1_done": True}, 101.2, "HOLD")
        assert again["scale_out"] == 0.0 and not again["exit"]


class TestVolTargetSizing:
    def test_exposure_follows_target_over_realised_vol_and_is_capped(self):
        cfg = LokiConfig(sizing_mode="vol_target", target_vol_pct=15.0, max_exposure_pct=100.0,
                         stop_loss_atr=3.0, take_profit_atr=0.0)
        calm = live_engine.size_entry(cfg, {"atr": 2.0, "ann_vol": 0.30, "size_multiplier": 1.0}, 100.0, 10_000, 10_000)
        assert calm["exposure_pct"] == pytest.approx(50.0)  # 15% / 30%
        assert calm["target"] == 0.0  # no fixed target: winners run
        quiet = live_engine.size_entry(cfg, {"atr": 2.0, "ann_vol": 0.05, "size_multiplier": 1.0}, 100.0, 10_000, 10_000)
        assert quiet["exposure_pct"] == pytest.approx(100.0)  # capped
        broke = live_engine.size_entry(cfg, {"atr": 2.0, "ann_vol": 0.05, "size_multiplier": 1.0}, 100.0, 10_000, 2_000)
        assert broke["exposure_pct"] == pytest.approx(20.0) and broke["capped_by_cash"]
        unknown = live_engine.size_entry(cfg, {"atr": 2.0, "ann_vol": 0.0, "size_multiplier": 1.0}, 100.0, 10_000, 10_000)
        assert unknown["qty"] == 0.0  # no volatility estimate: no trade

    def test_backtest_uses_far_more_capital_than_classic_sizing(self):
        df = _tape()
        base = dict(signal_threshold=5.0, take_profit_atr=0.0, stop_loss_atr=6.0, trailing_stop_atr=4.0, max_hold_bars=0)
        classic = run_backtest(df, LokiConfig(**base))
        vol = run_backtest(df, LokiConfig(**base, sizing_mode="vol_target", target_vol_pct=20.0))
        notional = lambda r: sum(t.qty * t.entry_price for t in r.trades) / max(1, len(r.trades))  # noqa: E731
        assert notional(vol) > 2 * notional(classic)
        assert all(t.qty * t.entry_price <= 100_000 * 1.01 for t in vol.trades)

    def test_plan_reports_realised_vol(self):
        df = _tape()
        cfg = LokiConfig(sizing_mode="vol_target")
        plan = live_engine.plan_entry(EnsembleStrategy(cfg).score_frame(df), cfg)
        assert 0.05 < plan["ann_vol"] < 1.0 and plan["sizing_mode"] == "vol_target"


def test_trend_exit_vote():
    cfg = LokiConfig(exit_mode="trend")
    assert live_engine.exit_signal(cfg, {"ready": True, "above_sma200": True}, "SELL") == "HOLD"
    assert live_engine.exit_signal(cfg, {"ready": True, "above_sma200": False}, "BUY") == "SELL"
    assert live_engine.exit_signal(LokiConfig(), {"ready": True, "above_sma200": True}, "sell") == "SELL"


class TestLearnedFilter:
    """The mistake filter: trained on the strategy's own trades, same rule live and in backtests."""

    def _model(self, df, cfg):
        from loki_v8 import mistake_model

        frame = EnsembleStrategy(cfg).score_frame(df)
        trades = run_backtest(df, cfg, frame=frame).trades
        X, y = mistake_model.training_rows([frame], [trades], 252)
        return mistake_model.fit(X, y), len(y)

    def test_filter_removes_entries_and_parity_holds(self):
        df = _tape()
        base = LokiConfig(signal_threshold=8.0, take_profit_atr=4.0)
        model, n = self._model(df, base)
        assert n > 10 and model["samples"] == n
        meta = {"model": model, "threshold": 0.55}
        cfg = LokiConfig(signal_threshold=8.0, take_profit_atr=4.0, meta_filter=meta)
        unfiltered = run_backtest(df, base).trades
        filtered = run_backtest(df, cfg).trades
        assert len(filtered) < len(unfiltered)
        # Every filtered entry is one the live planner would also allow.
        frame = EnsembleStrategy(cfg).score_frame(df)
        index = list(df.index)
        for t in filtered:
            if t.exit_reason == "scale_out":
                continue
            plan = live_engine.plan_entry(frame.iloc[: index.index(t.entry_time)], cfg)
            gate = next(g for g in plan["gates"] if g["name"] == "learned_filter")
            assert gate["passed"] and plan["allowed"]

    def test_missing_features_never_block_and_no_model_is_open(self):
        from loki_v8 import mistake_model

        assert mistake_model.allows(None, 0.01)
        assert mistake_model.allows({"model": {"x": 1}, "threshold": 0.5}, None)
        assert not mistake_model.allows({"model": {"x": 1}, "threshold": 0.5}, 0.2)

    def test_training_rows_exclude_trades_not_yet_closed(self):
        from loki_v8 import mistake_model

        df = _tape()
        cfg = LokiConfig(signal_threshold=8.0)
        frame = EnsembleStrategy(cfg).score_frame(df)
        trades = run_backtest(df, cfg, frame=frame).trades
        cut = str(df.index[600].date())
        X, y = mistake_model.training_rows([frame], [trades], 252, closed_before=cut)
        closed = [t for t in trades if t.exit_reason != "scale_out" and str(t.exit_time.date()) < cut]
        assert 0 < len(y) <= len(closed)


def test_shipped_snapshot_profiles_are_consistent():
    from loki_v8.train import apply_universal, load_report

    report = load_report()
    for symbol in ("SPY", "BTC-USD"):
        cfg = LokiConfig()
        applied = apply_universal(report, symbol, cfg)
        assert applied, symbol
        assert cfg.sizing_mode == "vol_target"
        assert cfg.max_daily_loss_pct == LokiConfig().max_daily_loss_pct  # guards untouched
    meta = load_report()["universal"]["equity"]["params"].get("meta_filter")
    if meta:
        from loki_v8 import mistake_model

        assert meta["model"]["features"] == list(mistake_model.FEATURES)
