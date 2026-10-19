"""Smart trade-management upgrades (v8.7).

Deterministic synthetic-candle tests for the exit/sizing engine:
  * breakeven lock turns would-be full losses into scratches/small wins
  * armed ATR trailing only ratchets once a real gain exists
  * partial scale-out banks a fraction at an intermediate level
  * conviction / regime / vol-target sizing scale position size
  * adaptive threshold demands stronger signals when vol expands
  * the live engine mirrors the backtester (bot._manage_exits)

Every backtest injects a hand-built score frame (``frame=``), so there is no
randomness and no network access anywhere in this module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import loki_v8.backtest as bt
import loki_v8.train as T
from loki_v8.bot import LokiBot
from loki_v8.backtest import run_backtest
from loki_v8.config import LokiConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _candles(closes, wick: float = 0.15):
    """Deterministic OHLCV frame: open = previous close, fixed small wicks."""
    opens = [closes[0]] + list(closes[:-1])
    n = len(closes)
    return pd.DataFrame(
        {
            "open": opens,
            "high": [max(o, c) + wick for o, c in zip(opens, closes)],
            "low": [min(o, c) - wick for o, c in zip(opens, closes)],
            "close": list(closes),
            "volume": [1_000.0] * n,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def _flat(n: int, px: float = 100.0):
    return [px] * n


def _frame(df: pd.DataFrame, score: float = 100.0, atr: float = 1.0, atr_pct=None):
    """Score frame with everything longs need: always-BUY, trend filter on."""
    n = len(df)
    if atr_pct is None:
        atr_pct = [100.0 * atr / np.mean(df["close"].values)] * n
    return pd.DataFrame(
        {
            "score": [score] * n,
            "atr": [atr] * n,
            "atr_pct": list(atr_pct),
            "close": df["close"].values,
            "sma_200": [0.0] * n,
            "sma_50": [0.0] * n,
            "adx": [30.0] * n,
        },
        index=df.index,
    )


def _base_cfg(**overrides) -> LokiConfig:
    cfg = LokiConfig(
        lookback_bars=20,  # warmup is max(lookback, 60) -> first entry bar 61
        max_hold_bars=0,  # no time-stop unless a test asks for it
        slippage_bps=3.0,
        commission_per_trade=0.0,
    )
    for k, v in overrides.items():
        if k in cfg.__dataclass_fields__:
            setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# Breakeven lock
# ---------------------------------------------------------------------------
class TestBreakevenLock:
    def _run(self, breakeven: float):
        closes = (
            _flat(61)
            + [101.5, 102.0, 102.5, 103.0, 103.5, 104.0]  # rally -> gain ~3 ATR
            + [96.0, 94.0, 93.0, 92.0, 91.0, 91.0, 91.0, 91.0, 91.0, 91.0, 91.0]
        )
        df = _candles(closes)
        cfg = _base_cfg(
            breakeven_atr=breakeven,
            stop_loss_atr=5.0,
            take_profit_atr=50.0,  # target never reached
            max_hold_bars=0,
        )
        return run_backtest(df, cfg, symbol="TEST", frame=_frame(df))

    def test_breakeven_converts_full_loss_into_a_win(self):
        with_be = self._run(breakeven=1.0)
        without_be = self._run(breakeven=0.0)

        assert with_be.trades, "expected at least one trade"
        assert without_be.trades
        # Classic wide stop: the crash floors the first trade
        assert without_be.trades[0].pnl < 0.0
        # Same path with a breakeven lock: stop ratcheted to entry (+cushion)
        assert with_be.trades[0].pnl > 0.0
        assert with_be.trades[0].exit_reason == "stop"

    def test_breakeven_off_by_default(self):
        closes = (
            _flat(61)
            + [101.5, 102.0, 102.5, 103.0, 103.5, 104.0]
            + [96.0, 94.0, 93.0, 92.0, 91.0, 91.0, 91.0, 91.0, 91.0, 91.0, 91.0]
        )
        df = _candles(closes)
        cfg = _base_cfg(stop_loss_atr=5.0, take_profit_atr=50.0)
        res = run_backtest(df, cfg, symbol="TEST", frame=_frame(df))
        assert res.trades[0].pnl < 0.0  # defaults preserve the classic engine


# ---------------------------------------------------------------------------
# Armed trailing stop
# ---------------------------------------------------------------------------
class TestArmedTrailing:
    def _run(self, arm: float):
        closes = (
            _flat(61)
            + [101.2, 101.0, 100.5, 99.8, 99.0, 98.3, 97.8, 97.2, 96.8, 96.4]
            + [96.2, 96.0, 96.0, 96.0, 96.0, 96.0, 96.0, 96.0]
        )
        df = _candles(closes)
        cfg = _base_cfg(
            trailing_stop_atr=0.3,
            arm_trailing_atr=arm,
            stop_loss_atr=5.0,
            take_profit_atr=50.0,
        )
        return run_backtest(df, cfg, symbol="TEST", frame=_frame(df))

    def test_unarmed_trailing_ratchets_and_locks_a_small_win(self):
        res = self._run(arm=0.0)
        first = res.trades[0]
        assert first.exit_reason == "stop"
        assert first.pnl > 0.0  # trailing stop raised above the entry

    def test_armed_trailing_does_not_fire_before_the_gain(self):
        # max gain was ~1.2 ATR < arm 2.0 -> trailing never engaged. The wide
        # stop is never touched either, so the position ends 'end' as a loss.
        res = self._run(arm=2.0)
        first = res.trades[0]
        assert first.pnl < 0.0


# ---------------------------------------------------------------------------
# Partial scale-out
# ---------------------------------------------------------------------------
class TestPartialScaleOut:
    def _closes(self):
        return (
            _flat(61)
            + [100.5, 101.1, 101.8, 102.4, 103.2, 104.0, 104.8, 105.6, 106.4, 107.2]
            + _flat(15, 107.2)
        )

    def test_scaleout_banks_half_before_the_full_target(self):
        df = _candles(self._closes())
        cfg = _base_cfg(
            stop_loss_atr=5.0,
            take_profit_atr=2.0,
            partial_tp_atr=0.6,
            partial_fraction=0.5,
        )
        res = run_backtest(df, cfg, symbol="TEST", frame=_frame(df))

        scale_legs = [t for t in res.trades if t.exit_reason == "scale_out"]
        assert scale_legs, "expected a scale-out leg"
        first_idx = res.trades.index(scale_legs[0])
        leg2 = res.trades[first_idx + 1]
        assert leg2.exit_reason == "target"
        assert scale_legs[0].qty == pytest.approx(leg2.qty, rel=1e-6)
        assert scale_legs[0].pnl > 0.0 and leg2.pnl > 0.0

    def test_no_partial_when_disabled(self):
        df = _candles(self._closes())
        cfg = _base_cfg(stop_loss_atr=5.0, take_profit_atr=2.0)
        res = run_backtest(df, cfg, symbol="TEST", frame=_frame(df))
        assert not any(t.exit_reason == "scale_out" for t in res.trades)


# ---------------------------------------------------------------------------
# Instrument sizing
# ---------------------------------------------------------------------------
class TestSizing:
    def _first_qty(self, cfg, regime_patch=None, atr_pct=None, score=100.0):
        df = _candles(_flat(70))
        kwargs = {}
        if score != 100.0:
            kwargs["score"] = score
        if atr_pct is not None:
            kwargs["atr_pct"] = atr_pct
        if regime_patch is not None:
            orig = bt.regime_series
            bt.regime_series = regime_patch
            try:
                res = run_backtest(df, cfg, symbol="TEST", frame=_frame(df, **kwargs))
            finally:
                bt.regime_series = orig
        else:
            res = run_backtest(df, cfg, symbol="TEST", frame=_frame(df, **kwargs))
        return res.trades[0].qty

    def test_conviction_sizing_scales_up_strong_signals(self):
        base = self._first_qty(
            _base_cfg(signal_threshold=25.0, stop_loss_atr=2.0, take_profit_atr=3.0),
            score=60.0,
        )
        boosted = self._first_qty(
            _base_cfg(
                signal_threshold=25.0,
                stop_loss_atr=2.0,
                take_profit_atr=3.0,
                conviction_sizing=True,
            ),
            score=60.0,  # strength 60/25 = 2.4 -> clamped to 1.25
        )
        assert boosted == pytest.approx(base * 1.25, rel=1e-4)

    def test_conviction_sizing_moderate_signal_within_cap(self):
        base = self._first_qty(
            _base_cfg(signal_threshold=25.0, stop_loss_atr=2.0, take_profit_atr=3.0),
            score=30.0,
        )
        boosted = self._first_qty(
            _base_cfg(
                signal_threshold=25.0,
                stop_loss_atr=2.0,
                take_profit_atr=3.0,
                conviction_sizing=True,
            ),
            score=30.0,  # strength 30/25 = 1.2 -> exactly 1.2 (inside the cap)
        )
        assert boosted == pytest.approx(base * 1.2, rel=1e-4)

    def test_regime_sizing_halves_in_ranging(self):
        base = self._first_qty(_base_cfg(stop_loss_atr=2.0, take_profit_atr=3.0))
        ranging = self._first_qty(
            _base_cfg(stop_loss_atr=2.0, take_profit_atr=3.0, regime_sizing=True),
            regime_patch=lambda frame: pd.Series(["RANGING"] * len(frame), index=frame.index),
        )
        assert ranging == pytest.approx(base * 0.5, rel=1e-4)

    def test_vol_target_sizing_shrinks_hot_markets(self):
        # atr_pct is 1.2% through bar 60, then jumps to 5%: the FIRST tradeable
        # bar (61) reads bar 60's hot 5% against a rolling median of 1.2
        # -> multiplier min(1.2, 1.2/5) = 0.24
        atr_pct = [1.2] * 60 + [5.0] * 10
        base = self._first_qty(_base_cfg(stop_loss_atr=2.0, take_profit_atr=3.0))
        shrunk = self._first_qty(
            _base_cfg(stop_loss_atr=2.0, take_profit_atr=3.0, vol_target_sizing=True),
            atr_pct=atr_pct,
        )
        assert shrunk == pytest.approx(base * 0.24, rel=0.05)


# ---------------------------------------------------------------------------
# Adaptive threshold
# ---------------------------------------------------------------------------
class TestAdaptiveThreshold:
    def _run(self, adaptive: bool):
        # Volatility sits at 8% until bar 60 (inclusive), so the FIRST
        # tradeable bar (61) already reads the expanded 20% from bar 60:
        # stress = min(1.6, 20/8) = 1.6 -> effective threshold = 40
        atr_pct = [8.0] * 60 + [20.0] * 10
        df = _candles(_flat(70))
        cfg = _base_cfg(
            signal_threshold=25.0,
            max_atr_pct=50.0,  # disable the plain vol gate for this test
            adaptive_threshold=adaptive,
        )
        return run_backtest(df, cfg, symbol="TEST", frame=_frame(df, score=39.0, atr_pct=atr_pct))

    def test_off_fires(self):
        assert len(self._run(adaptive=False).trades) >= 1

    def test_on_blocks_marginal_signal_in_vol_expansion(self):
        assert len(self._run(adaptive=True).trades) == 0


# ---------------------------------------------------------------------------
# Live engine parity (bot._manage_exits)
# ---------------------------------------------------------------------------
class TestLiveEngineParity:
    def _bot(self, tmp_path, **overrides):
        cfg = LokiConfig(state_dir=str(tmp_path), **overrides)
        return LokiBot(cfg)

    def test_breakeven_lock_applies_to_open_position(self, tmp_path):
        bot = self._bot(tmp_path, breakeven_atr=1.0, stop_loss_atr=5.0, take_profit_atr=6.0)
        assert bot.broker.buy("AAPL", 100, 100.0)
        bot._last_context["AAPL"] = {"atr": 1.2}

        bot._manage_exits({"AAPL": 101.5})  # gain = 1.47/1.2 = 1.22 ATR
        pos = bot.broker.positions["AAPL"]
        # entry fill = 100.03; BE stop = entry + 0.05*1.2
        assert pos.stop_loss == pytest.approx(100.03 + 0.05 * 1.2, rel=1e-4)
        assert bot.broker.positions["AAPL"].qty == pytest.approx(100)

    def test_partial_scaleout_banks_half_and_raises_stop(self, tmp_path):
        bot = self._bot(
            tmp_path,
            breakeven_atr=1.0,
            stop_loss_atr=5.0,
            take_profit_atr=6.0,
            partial_tp_atr=1.0,
            partial_fraction=0.5,
        )
        assert bot.broker.buy("AAPL", 100, 100.0)
        bot._last_context["AAPL"] = {"atr": 1.2}

        bot._manage_exits({"AAPL": 102.0})  # gain 1.6 ATR: BE locks, partial hits
        pos = bot.broker.positions["AAPL"]
        assert pos.qty == pytest.approx(50.0, rel=1e-6)  # half banked
        assert "AAPL" in bot._scaled_out
        assert pos.stop_loss == pytest.approx(102.0, rel=1e-4)  # stop moved to fill

    def test_partial_fires_only_once(self, tmp_path):
        bot = self._bot(
            tmp_path,
            breakeven_atr=0.0,
            stop_loss_atr=5.0,
            take_profit_atr=6.0,
            partial_tp_atr=1.0,
            partial_fraction=0.5,
        )
        assert bot.broker.buy("AAPL", 100, 100.0)
        bot._last_context["AAPL"] = {"atr": 1.2}

        bot._manage_exits({"AAPL": 101.5})
        qty_after_first = bot.broker.positions["AAPL"].qty
        assert qty_after_first == pytest.approx(50.0, rel=1e-6)

        bot._manage_exits({"AAPL": 102.5})  # still in range, no second leg
        assert bot.broker.positions["AAPL"].qty == pytest.approx(50.0, rel=1e-6)

    def test_no_smart_exits_by_default(self, tmp_path):
        bot = self._bot(tmp_path, stop_loss_atr=5.0, take_profit_atr=6.0)
        assert bot.broker.buy("AAPL", 100, 100.0)
        bot.broker.positions["AAPL"].stop_loss = 95.03  # set by step() in real flow
        bot._last_context["AAPL"] = {"atr": 1.2}

        bot._manage_exits({"AAPL": 104.0})  # far above breakeven trigger
        pos = bot.broker.positions["AAPL"]
        assert pos.qty == pytest.approx(100)  # untouched (partial off)
        assert pos.stop_loss == pytest.approx(95.03, rel=1e-3)  # original stop

    def test_short_position_breakeven_lock(self, tmp_path):
        cfg = LokiConfig(
            state_dir=str(tmp_path),
            breakeven_atr=1.0,
            allow_short=True,
            stop_loss_atr=5.0,
            take_profit_atr=6.0,
        )
        bot = LokiBot(cfg)
        assert bot.broker.sell_short("BTC-USD", 100, 200.0)
        pos = bot.broker.positions["BTC-USD"]
        avg_entry = pos.avg_entry  # 200 * (1 - 0.0003) = 199.94
        bot._last_context["BTC-USD"] = {"atr": 2.0}

        bot._manage_exits({"BTC-USD": 196.0})  # gain = (199.94-196)/2 ≈ 1.97 ATR
        pos = bot.broker.positions["BTC-USD"]
        be_stop = avg_entry - 0.05 * 2.0
        assert pos.stop_loss == pytest.approx(be_stop, rel=1e-4)


# ---------------------------------------------------------------------------
# Backtester: short-side exits (scale-out, BE lock, trailing)
# ---------------------------------------------------------------------------
class TestShortSideExits:
    def _run(self, **overrides):
        prices = (
            _flat(61) + [99.0, 98.0, 97.0, 96.0, 95.2, 94.6, 96.5, 97.8, 99.0, 100.5] + [100.5] * 10
        )
        df = _candles(prices)
        cfg = _base_cfg(
            allow_short=True,
            regime_filter=False,  # candles read STRONG_BULL; shorts need the gate off
            **overrides,
        )
        frame = _frame(df, score=-100.0)  # always SELL
        return run_backtest(df, cfg, symbol="SHORT", frame=frame)

    def test_short_scaleout_banks_half(self):
        res = self._run(stop_loss_atr=5.0, take_profit_atr=2.5, partial_tp_atr=0.6)
        legs = [t for t in res.trades if t.exit_reason == "scale_out"]
        assert legs, "expected a short scale-out leg"
        idx = res.trades.index(legs[0])
        leg2 = res.trades[idx + 1]
        assert legs[0].qty == pytest.approx(leg2.qty, rel=1e-6)
        assert legs[0].pnl > 0.0  # fell through the partial level

    def test_short_breakeven_lock(self):
        with_be = self._run(stop_loss_atr=5.0, take_profit_atr=50.0, breakeven_atr=1.0)
        without_be = self._run(stop_loss_atr=5.0, take_profit_atr=50.0)
        assert without_be.trades[0].pnl < 0.0  # recovery blows through the short
        assert with_be.trades[0].pnl > 0.0  # stop ratcheted below entry

    def test_short_armed_trailing(self):
        res = self._run(stop_loss_atr=5.0, take_profit_atr=50.0, trailing_stop_atr=0.3)
        first = res.trades[0]
        assert first.pnl > 0.0  # trailing stop trails the downside


# ---------------------------------------------------------------------------
# Trainer: months-consistency ranking
# ---------------------------------------------------------------------------
class TestMonthsRanking:
    def test_win_rate_objective_prefers_steady_months(self):
        lumpy = {
            "trades": 40,
            "win_rate_pct": 88.0,
            "profit_factor": 1.9,
            "return_pct": 6.0,
            "sharpe": 1.0,
            "month_profit_rate_pct": 40.0,
        }
        steady = dict(lumpy, month_profit_rate_pct=75.0)
        entry_lumpy = {"params": {}, "train": lumpy}
        entry_steady = {"params": {}, "train": steady}
        key_l = T._rank_key(entry_lumpy, "win_rate")
        key_s = T._rank_key(entry_steady, "win_rate")
        assert key_s > key_l
        # Best LAST convention: steady sorts above lumpy on reversal too
        board = sorted([entry_lumpy, entry_steady], key=lambda e: T._rank_key(e, "win_rate"))
        assert board[-1] is entry_steady

    def test_tiny_sample_cannot_outrank_rich_sample(self):
        # The 10-trade "100% win" profile must lose to the 147-trade record:
        # heavily filtered variants (hard ATR gates) otherwise tunnel into
        # the polish stage and starve a symbol of entries.
        tiny = {
            "trades": 3,
            "win_rate_pct": 100.0,
            "profit_factor": 3.0,
            "return_pct": 9.0,
            "sharpe": 2.0,
            "month_profit_rate_pct": 80.0,
        }
        rich = {
            "trades": 147,
            "win_rate_pct": 88.0,
            "profit_factor": 2.9,
            "return_pct": 10.0,
            "sharpe": 1.4,
            "month_profit_rate_pct": 70.0,
        }
        entry_t = {"params": {}, "train": tiny}
        entry_r = {"params": {}, "train": rich}
        board = sorted([entry_t, entry_r], key=lambda e: T._rank_key(e, "win_rate"), reverse=True)
        assert board[0] is entry_r
        # Sharpe objective is protected the same way.
        board = sorted([entry_t, entry_r], key=lambda e: T._rank_key(e, "sharpe"), reverse=True)
        assert board[0] is entry_r

    def test_within_90_band_months_decides(self):
        # Both candidates clear the 90% band: the steadier monthly profile
        # wins even when it gives up a fraction of a point of hit rate.
        a = {
            "trades": 147,
            "win_rate_pct": 92.5,
            "profit_factor": 2.8,
            "return_pct": 8.0,
            "sharpe": 1.2,
            "month_profit_rate_pct": 40.0,
        }
        b = dict(
            a, win_rate_pct=92.0, profit_factor=3.0, return_pct=8.5, month_profit_rate_pct=75.0
        )
        # A below-band candidate can never sneak past the band on months.
        c = dict(a, win_rate_pct=89.9, profit_factor=3.2, month_profit_rate_pct=85.0)
        ea, eb, ec = (
            {"params": {}, "train": a},
            {"params": {}, "train": b},
            {"params": {}, "train": c},
        )
        board = sorted([ea, eb, ec], key=lambda e: T._rank_key(e, "win_rate"), reverse=True)
        assert board[0] is eb  # months king inside the band
        assert board[1] is ea  # 92.5 with weak months beats 89.9 with great months

    def test_train_metrics_include_months(self):
        df = pd.DataFrame(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1.0,
            },
            index=pd.date_range("2023-01-01", periods=300, freq="D"),
        )
        cfg = LokiConfig(lookback_bars=20)
        rep = T.train_symbol(
            df,
            cfg,
            "TEST",
            grid={"signal_threshold": [45.0], "stop_loss_atr": [2.0], "take_profit_atr": [3.0]},
        )
        assert rep.ok
        entry = rep.leaderboard[0]
        assert "month_profit_rate_pct" in entry["train"]


# ---------------------------------------------------------------------------
# Whole-engine journeys with the knobs on
# ---------------------------------------------------------------------------
class TestKnobJourneys:
    def test_portfolio_backtest_with_smart_exits(self):
        # Frames must exceed 200 bars so sma_200 exists for the real scoring
        ramp = [100.0 + 0.8 * i for i in range(1, 14)] + _flat(60, 110.4)
        dip = [100.0 - 0.6 * i for i in range(1, 13)] + _flat(61, 92.8)
        df_a = _candles(_flat(215) + ramp)
        df_b = _candles(_flat(217) + dip)
        cfg = _base_cfg(
            stop_loss_atr=3.0,
            take_profit_atr=2.0,
            breakeven_atr=0.8,
            partial_tp_atr=0.6,
            partial_fraction=0.5,
            conviction_sizing=True,
            regime_sizing=True,
            vol_target_sizing=True,
        )
        cfg.max_hold_bars = 20
        res = bt.portfolio_backtest({"A": df_a, "B": df_b}, cfg)
        assert res.final_equity > 0.0
        assert res.total_trades >= 1

    def test_walk_forward_with_smart_exits(self):
        closes = _flat(61) + [100.6, 101.2, 101.8, 102.4, 103.0]
        closes = closes + [103.4, 104.2, 103.8, 104.6, 105.2, 104.8] + _flat(120, 104.8)
        df = _candles(closes)
        cfg = _base_cfg(
            stop_loss_atr=3.0,
            take_profit_atr=1.5,
            breakeven_atr=0.6,
            trailing_stop_atr=0.5,
            arm_trailing_atr=1.0,
        )
        results = bt.walk_forward(df, cfg, symbol="TEST", n_splits=2)
        assert results, "expected walk-forward folds"
        for r in results:
            assert r.final_equity > 0.0
