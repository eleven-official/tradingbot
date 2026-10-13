"""
Local compatibility shim for the ``pandas_ta_classic`` package.

The Loki codebase calls a small, well-defined subset of the ``pandas_ta``
API: ``ta.ema``, ``ta.rsi``, ``ta.macd``, ``ta.atr``, ``ta.bbands``,
``ta.supertrend``, ``ta.psar``, ``ta.adx``, and the ``df.ta.vwap()``
DataFrame accessor.  ``pandas_ta_classic`` is an unmaintained fork that is
incompatible with pandas 3.x / numpy 2.x, so this module re-implements those
indicators from first principles with pure pandas/numpy.

It is intentionally a *drop-in* replacement: the column names returned by the
functions (e.g. ``MACD_12_26_9``, ``SUPERTd_10_3.0``, ``BBU_20_2.0``) match
pandas_ta's naming exactly, so the rest of the codebase works unchanged.

If you later install the real ``pandas-ta-classic`` and it works on your
pandas version, you can delete this file.  Until then, keep it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Rolling / smoothing helpers
# ---------------------------------------------------------------------------
def _wilder_smooth(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (EMA with alpha = 1/length), used by RSI/ATR/ADX."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


def ema(close, length: int = 10, **kwargs) -> pd.Series:
    """Exponential moving average."""
    if length is None or length <= 0:
        length = int(kwargs.get("period", 10))
    return pd.Series(close, copy=True).ewm(span=length, adjust=False).mean()


def rsi(close, length: int = 14, **kwargs) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    close = pd.Series(close, copy=True)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_smooth(gain, length)
    avg_loss = _wilder_smooth(loss, length)
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - 100.0 / (1.0 + rs)


def _true_range(high, low, close) -> pd.Series:
    high = pd.Series(high, copy=True)
    low = pd.Series(low, copy=True)
    close = pd.Series(close, copy=True)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high, low, close, length: int = 14, **kwargs) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    return _wilder_smooth(_true_range(high, low, close), length)


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9, **kwargs) -> pd.DataFrame:
    """Moving Average Convergence Divergence (EMA 12/26, signal 9)."""
    close = pd.Series(close, copy=True)
    macd_line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {
            f"MACD_{fast}_{slow}_{signal}": macd_line,
            f"MACDs_{fast}_{slow}_{signal}": signal_line,
            f"MACDh_{fast}_{slow}_{signal}": hist,
        }
    )


def bbands(close, length: int = 20, std: float = 2.0, **kwargs) -> pd.DataFrame:
    """Bollinger Bands (simple moving average ± std × population stdev)."""
    close = pd.Series(close, copy=True)
    mid = close.rolling(length, min_periods=length).mean()
    sd = close.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    bandwidth = (upper - lower) / mid
    percent = (close - lower) / (upper - lower + 1e-9)
    suffix = f"{length}_{std:.1f}"
    return pd.DataFrame(
        {
            f"BBL_{suffix}": lower,
            f"BBM_{suffix}": mid,
            f"BBU_{suffix}": upper,
            f"BBB_{suffix}": bandwidth,
            f"BBP_{suffix}": percent,
        }
    )


def supertrend(high, low, close, length: int = 7, multiplier: float = 3.0, **kwargs) -> pd.DataFrame:
    """Supertrend (ATR trailing stop)."""
    high = pd.Series(high, copy=True)
    low = pd.Series(low, copy=True)
    close = pd.Series(close, copy=True)

    hl2 = (high + low) / 2.0
    atr_ = atr(high, low, close, length)

    upper_basic = hl2 + multiplier * atr_
    lower_basic = hl2 - multiplier * atr_

    upper = upper_basic.to_numpy(dtype=float).copy()
    lower = lower_basic.to_numpy(dtype=float).copy()
    close_arr = close.to_numpy(dtype=float)
    n = len(close_arr)

    trend = np.ones(n)          # +1 = up, -1 = down
    st = np.full(n, np.nan)

    for i in range(1, n):
        if np.isnan(upper[i - 1]) or np.isnan(lower[i - 1]):
            continue
        if close_arr[i] > upper[i - 1]:
            trend[i] = 1.0
        elif close_arr[i] < lower[i - 1]:
            trend[i] = -1.0
        else:
            trend[i] = trend[i - 1]
            if trend[i] == 1.0 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if trend[i] == -1.0 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]
        st[i] = lower[i] if trend[i] == 1.0 else upper[i]

    suffix = f"{length}_{multiplier:.1f}"
    return pd.DataFrame(
        {f"SUPERT_{suffix}": st, f"SUPERTd_{suffix}": trend}, index=close.index
    )


def psar(high, low, close, af: float = 0.02, max_af: float = 0.2, **kwargs) -> pd.DataFrame:
    """Parabolic Stop And Reverse (Wilder's algorithm)."""
    high = pd.Series(high, copy=True).to_numpy(dtype=float)
    low = pd.Series(low, copy=True).to_numpy(dtype=float)
    close = pd.Series(close, copy=True)
    n = len(close)

    psar_long = np.full(n, np.nan)
    psar_short = np.full(n, np.nan)

    if n < 3:
        suffix = f"{af}_{max_af}"
        return pd.DataFrame(
            {f"PSARl_{suffix}": psar_long, f"PSARs_{suffix}": psar_short},
            index=close.index,
        )

    # Initial trend: bullish if the first two closes rose.
    bullish = close.iloc[1] >= close.iloc[0]
    accel = af

    if bullish:
        sar = float(np.min(low[:2]))
        ep = float(np.max(high[:2]))
    else:
        sar = float(np.max(high[:2]))
        ep = float(np.min(low[:2]))

    for i in range(2, n):
        sar = sar + accel * (ep - sar)

        if bullish:
            sar = min(sar, low[i - 1], low[i - 2])
            psar_long[i] = sar
            if low[i] < sar:
                bullish = False
                sar = ep
                ep = float(np.min(low[i - 2 : i + 1]))
                accel = af
                psar_short[i] = sar
            else:
                if high[i] > ep:
                    ep = high[i]
                    accel = min(accel + af, max_af)
        else:
            sar = max(sar, high[i - 1], high[i - 2])
            psar_short[i] = sar
            if high[i] > sar:
                bullish = True
                sar = ep
                ep = float(np.max(high[i - 2 : i + 1]))
                accel = af
                psar_long[i] = sar
            else:
                if low[i] < ep:
                    ep = low[i]
                    accel = min(accel + af, max_af)

    suffix = f"{af}_{max_af}"
    return pd.DataFrame(
        {f"PSARl_{suffix}": psar_long, f"PSARs_{suffix}": psar_short},
        index=close.index,
    )


def adx(high, low, close, length: int = 14, **kwargs) -> pd.DataFrame:
    """Average Directional Index (ADX) with +DI / -DI columns."""
    high = pd.Series(high, copy=True)
    low = pd.Series(low, copy=True)
    close = pd.Series(close, copy=True)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=close.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=close.index
    )

    atr_ = _wilder_smooth(_true_range(high, low, close), length)
    atr_safe = atr_.replace(0.0, np.nan)

    plus_di = 100.0 * _wilder_smooth(plus_dm, length) / atr_safe
    minus_di = 100.0 * _wilder_smooth(minus_dm, length) / atr_safe

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx_line = _wilder_smooth(dx, length)

    return pd.DataFrame(
        {f"ADX_{length}": adx_line, f"DMP_{length}": plus_di, f"DMN_{length}": minus_di}
    )


# ---------------------------------------------------------------------------
# DataFrame accessor: ``df.ta.vwap(append=True)``
# ---------------------------------------------------------------------------
@pd.api.extensions.register_dataframe_accessor("ta")
class _TAAccessor:
    """Minimal ``.ta`` accessor providing ``vwap`` (cumulative, daily-anchored)."""

    def __init__(self, pandas_obj):
        self._df = pandas_obj

    def vwap(self, append: bool = False, **kwargs) -> pd.Series:
        typical = (self._df["high"] + self._df["low"] + self._df["close"]) / 3.0
        tpv = typical * self._df["volume"]

        # Daily-anchored when the index is a DatetimeIndex; otherwise cumulative.
        if isinstance(self._df.index, pd.DatetimeIndex):
            idx = self._df.index
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            groups = idx.normalize()
        else:
            groups = pd.Series(0, index=self._df.index)

        cum_tpv = tpv.groupby(groups).cumsum()
        cum_vol = self._df["volume"].groupby(groups).cumsum()
        vwap = cum_tpv / cum_vol.replace(0.0, np.nan)
        vwap.index = self._df.index

        if append:
            # The strategies read a lowercase ``vwap`` column.
            self._df["vwap"] = vwap
        return vwap
