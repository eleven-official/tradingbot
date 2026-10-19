"""LOKI v8 — vectorized technical-indicator library.

Every function accepts pandas Series (and where needed, DataFrames) and
returns Series/DataFrames aligned to the input index. All indicators are
implemented without external TA libraries so the engine has zero
hard dependencies beyond numpy + pandas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------
def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def wilder(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (RMA) used by RSI/ATR/ADX."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()


# ---------------------------------------------------------------------------
# Volatility / range
# ---------------------------------------------------------------------------
def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), length)


# ---------------------------------------------------------------------------
# Momentum oscillators
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder(gain, length)
    avg_loss = wilder(loss, length)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 the RSI is 100 (all gains).
    return out.fillna(100.0).where(avg_gain != 0, 0.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line, signal)
    hist = line - signal_line
    return line, signal_line, hist


def stoch(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3):
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    k_line = 100.0 * (close - lowest_low) / (highest_high - lowest_low).replace(0.0, np.nan)
    d_line = k_line.rolling(d).mean()
    return k_line, d_line


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    highest_high = high.rolling(length).max()
    lowest_low = low.rolling(length).min()
    return -100.0 * (highest_high - close) / (highest_high - lowest_low).replace(0.0, np.nan)


def roc(close: pd.Series, length: int = 12) -> pd.Series:
    return close.pct_change(length) * 100.0


# ---------------------------------------------------------------------------
# Trend strength — ADX / DI
# ---------------------------------------------------------------------------
def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    atr_ = wilder(true_range(high, low, close), length)
    plus_di = 100.0 * wilder(plus_dm, length) / atr_.replace(0.0, np.nan)
    minus_di = 100.0 * wilder(minus_dm, length) / atr_.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_line = wilder(dx, length)
    return adx_line, plus_di, minus_di


# ---------------------------------------------------------------------------
# Bands / channels
# ---------------------------------------------------------------------------
def bollinger_bands(close: pd.Series, length: int = 20, num_std: float = 2.0):
    middle = sma(close, length)
    std = close.rolling(length).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series,
                     length: int = 20, mult: float = 2.0):
    middle = ema(close, length)
    atr_ = atr(high, low, close, length)
    upper = middle + mult * atr_
    lower = middle - mult * atr_
    return upper, middle, lower


def donchian(high: pd.Series, low: pd.Series, length: int = 20):
    upper = high.rolling(length).max()
    lower = low.rolling(length).min()
    middle = (upper + lower) / 2.0
    return upper, middle, lower


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------
def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3.0
    return (typical * volume).cumsum() / volume.cumsum().replace(0.0, np.nan)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 20) -> pd.Series:
    """Chaikin Money Flow (CMF).
    
    Measures institutional accumulation vs distribution over a rolling window.
    Positive (> 0.05) indicates institutional buying; negative (< -0.05) distribution.
    """
    hl_spread = (high - low).replace(0.0, np.nan)
    mfm = ((close - low) - (high - close)) / hl_spread
    mfm = mfm.fillna(0.0)
    mfv = mfm * volume
    vol_sum = volume.rolling(length).sum().replace(0.0, np.nan)
    flow = mfv.rolling(length).sum() / vol_sum
    return flow.fillna(0.0)


# ---------------------------------------------------------------------------
# Squeeze / Volatility Compression (TTM Squeeze)
# ---------------------------------------------------------------------------
def ttm_squeeze(high: pd.Series, low: pd.Series, close: pd.Series,
                length: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5):
    """Institutional TTM Squeeze indicator.

    Detects volatility compression when Bollinger Bands contract inside Keltner Channels.
    When squeeze is True, energy is coiling. When squeeze transitions to False, momentum
    explodes in the direction of the momentum histogram.
    """
    bb_up, bb_mid, bb_low = bollinger_bands(close, length, bb_mult)
    kc_up, kc_mid, kc_low = keltner_channels(high, low, close, length, kc_mult)

    squeeze_on = (bb_low > kc_low) & (bb_up < kc_up)

    # Momentum oscillator: delta of price from average of Donchian midline & 20 SMA
    donch_mid = (high.rolling(length).max() + low.rolling(length).min()) / 2.0
    delta = close - (donch_mid + bb_mid) / 2.0
    mom = ema(delta, 5)

    return squeeze_on, mom


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------
def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               length: int = 10, mult: float = 3.0):
    """Returns (direction, upper_band, lower_band).

    direction is +1 (uptrend) / -1 (downtrend). Bands flip at trend changes.
    """
    hl2 = (high + low) / 2.0
    atr_ = atr(high, low, close, length)
    upper_basic = hl2 + mult * atr_
    lower_basic = hl2 - mult * atr_

    n = len(close)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    direction = np.ones(n)

    upper[0] = upper_basic.iloc[0]
    lower[0] = lower_basic.iloc[0]

    for i in range(1, n):
        prev_close = close.iloc[i - 1]
        # Upper band
        if upper_basic.iloc[i] < upper[i - 1] or prev_close > upper[i - 1]:
            upper[i] = upper_basic.iloc[i]
        else:
            upper[i] = upper[i - 1]
        # Lower band
        if lower_basic.iloc[i] > lower[i - 1] or prev_close < lower[i - 1]:
            lower[i] = lower_basic.iloc[i]
        else:
            lower[i] = lower[i - 1]
        # Direction
        if direction[i - 1] == 1 and close.iloc[i] < lower[i]:
            direction[i] = -1
        elif direction[i - 1] == -1 and close.iloc[i] > upper[i]:
            direction[i] = 1
        else:
            direction[i] = direction[i - 1]

    return pd.Series(direction, index=close.index), pd.Series(upper, index=close.index), pd.Series(lower, index=close.index)


# ---------------------------------------------------------------------------
# Convenience: add the full indicator suite to a DataFrame
# ---------------------------------------------------------------------------
def add_all_indicators(df: pd.DataFrame, atr_len: int = 14, adx_len: int = 14,
                       supertrend_len: int = 10, supertrend_mult: float = 3.0) -> pd.DataFrame:
    """Attach a broad set of indicators to an OHLCV DataFrame (in place copy)."""
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    df["sma_20"] = sma(c, 20)
    df["sma_50"] = sma(c, 50)
    df["sma_200"] = sma(c, 200)
    df["ema_9"] = ema(c, 9)
    df["ema_21"] = ema(c, 21)
    df["ema_50"] = ema(c, 50)
    df["ema_200"] = ema(c, 200)
    df["rsi"] = rsi(c, 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(c)
    df["atr"] = atr(h, l, c, atr_len)
    df["adx"], df["plus_di"], df["minus_di"] = adx(h, l, c, adx_len)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(c)
    df["stoch_k"], df["stoch_d"] = stoch(h, l, c)
    df["williams_r"] = williams_r(h, l, c)
    df["obv"] = obv(c, v)
    df["roc_20"] = roc(c, 20)
    df["roc_60"] = roc(c, 60)
    df["vwap"] = vwap(h, l, c, v)
    df["cmf"] = cmf(h, l, c, v)
    df["squeeze_on"], df["squeeze_mom"] = ttm_squeeze(h, l, c)
    df["supertrend"], df["supertrend_upper"], df["supertrend_lower"] = supertrend(
        h, l, c, supertrend_len, supertrend_mult
    )
    df["atr_pct"] = df["atr"] / c * 100.0
    return df

