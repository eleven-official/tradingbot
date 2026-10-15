"""Historical paper replay for transparent, long-only strategy rules.

Signals use completed candle data only and enter on the following candle open.
The replay includes adverse slippage, round-trip fees, capped spot exposure,
and a chronological holdout window. Results are historical diagnostics, not
forecasts or recommendations.
"""
from __future__ import annotations

from math import isfinite
from statistics import fmean
from typing import Any, Mapping, Sequence

STRATEGY_NAMES = {
    "trend_following": "EMA trend continuation",
    "breakout": "Volume-confirmed breakout",
    "pullback_reclaim": "Trend pullback reclaim",
}
MIN_HISTORY_BARS = 120


class BacktestInputError(ValueError):
    """Invalid replay settings or candle data."""


def _normalize_candles(candles: Sequence[Mapping[str, Any]]) -> list[dict[str, float]]:
    if not isinstance(candles, (list, tuple)) or len(candles) < MIN_HISTORY_BARS:
        raise BacktestInputError(f"at least {MIN_HISTORY_BARS} completed candles are required")
    normalized: list[dict[str, float]] = []
    previous_time = -1.0
    for row in candles:
        try:
            candle = {
                key: float(row[key])
                for key in ("time", "open", "high", "low", "close", "volume")
            }
        except (KeyError, TypeError, ValueError) as error:
            raise BacktestInputError("candle rows must contain finite OHLCV values") from error
        if not all(isfinite(value) for value in candle.values()):
            raise BacktestInputError("candle rows must contain finite OHLCV values")
        if (
            candle["time"] <= previous_time
            or min(candle["open"], candle["high"], candle["low"], candle["close"]) <= 0
            or candle["volume"] < 0
            or candle["high"] < max(candle["open"], candle["close"])
            or candle["low"] > min(candle["open"], candle["close"])
            or candle["high"] < candle["low"]
        ):
            raise BacktestInputError("candles must be valid and strictly chronological")
        previous_time = candle["time"]
        normalized.append(candle)
    return normalized


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def _rsi_at(closes: Sequence[float], index: int, period: int = 14) -> float:
    changes = [closes[pos] - closes[pos - 1] for pos in range(index - period + 1, index + 1)]
    gains = [change for change in changes if change > 0]
    losses = [-change for change in changes if change < 0]
    average_gain = fmean(gains) if gains else 0.0
    average_loss = fmean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain else 50.0
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)


def _indicator_series(candles: Sequence[Mapping[str, float]]) -> tuple[list[float], list[float], list[float]]:
    closes = [candle["close"] for candle in candles]
    fast_ema = _ema_series(closes, 20)
    slow_ema = _ema_series(closes, 50)
    true_ranges = []
    for index, candle in enumerate(candles):
        previous_close = closes[index - 1] if index else candle["close"]
        true_ranges.append(
            max(
                candle["high"] - candle["low"],
                abs(candle["high"] - previous_close),
                abs(candle["low"] - previous_close),
            )
        )
    atr = [
        fmean(true_ranges[index - 13 : index + 1]) if index >= 13 else 0.0
        for index in range(len(candles))
    ]
    return fast_ema, slow_ema, atr


def _has_signal(
    candles: Sequence[Mapping[str, float]],
    index: int,
    strategy_key: str,
    fast_ema: Sequence[float],
    slow_ema: Sequence[float],
) -> bool:
    if index < 50 or fast_ema[index] <= slow_ema[index]:
        return False
    closes = [candle["close"] for candle in candles]
    current = candles[index]
    rsi = _rsi_at(closes, index)
    if strategy_key == "trend_following":
        return current["close"] > fast_ema[index] and 50 <= rsi <= 70
    if strategy_key == "pullback_reclaim":
        return (
            closes[index - 1] <= fast_ema[index - 1]
            and current["close"] > fast_ema[index]
            and 40 <= rsi <= 65
        )
    prior_high = max(candle["high"] for candle in candles[index - 20 : index])
    prior_volume = fmean(candle["volume"] for candle in candles[index - 20 : index])
    volume_confirmed = prior_volume <= 0 or current["volume"] >= prior_volume * 1.2
    return current["close"] > prior_high and volume_confirmed


def _resolve_exit(
    candle: Mapping[str, float], stop_price: float, target_price: float
) -> tuple[float, str] | None:
    """Resolve one long candle conservatively when both barriers are touched."""
    if candle["open"] <= stop_price:
        return candle["open"], "stop_gap"
    if candle["open"] >= target_price:
        return target_price, "target_gap"
    stop_hit = candle["low"] <= stop_price
    target_hit = candle["high"] >= target_price
    if stop_hit and target_hit:
        return stop_price, "stop_both_touched"
    if stop_hit:
        return stop_price, "stop"
    if target_hit:
        return target_price, "target"
    return None


def _benchmark_return(
    candles: Sequence[Mapping[str, float]],
    start: int,
    end: int,
    fee_rate: float,
    slippage_rate: float,
) -> float:
    first_price = candles[start]["close"] * (1 + slippage_rate)
    last_price = candles[end - 1]["close"] * (1 - slippage_rate)
    if first_price <= 0:
        return 0.0
    quantity = 1 / first_price
    pnl = quantity * (last_price - first_price)
    pnl -= fee_rate * quantity * (first_price + last_price)
    return pnl * 100


def _simulate_segment(
    candles: Sequence[Mapping[str, float]],
    start: int,
    end: int,
    strategy_key: str,
    starting_capital: float,
    risk_percent: float,
    fee_rate: float,
    slippage_rate: float,
    max_holding_bars: int,
    fast_ema: Sequence[float],
    slow_ema: Sequence[float],
    atr: Sequence[float],
) -> dict[str, Any]:
    equity = starting_capital
    peak_equity = equity
    max_drawdown_percent = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve = [{"time": candles[start]["time"], "equity": round(equity, 2)}]
    index = max(start, 50)

    while index + 1 < end and equity > 0:
        if not _has_signal(candles, index, strategy_key, fast_ema, slow_ema) or atr[index] <= 0:
            index += 1
            continue

        entry_index = index + 1
        entry_candle = candles[entry_index]
        entry_price = entry_candle["open"] * (1 + slippage_rate)
        risk_distance = atr[index] * 1.5
        if entry_price <= risk_distance:
            index += 1
            continue
        quantity = min(
            equity * risk_percent / 100 / risk_distance,
            equity / entry_price,
        )
        if quantity <= 0 or not isfinite(quantity):
            index += 1
            continue

        stop_price = entry_price - risk_distance
        target_price = entry_price + risk_distance * 2
        last_exit_index = min(end - 1, entry_index + max_holding_bars - 1)
        exit_index = last_exit_index
        exit_price: float | None = None
        exit_reason = "time" if last_exit_index == entry_index + max_holding_bars - 1 else "sample_end"

        for candle_index in range(entry_index, last_exit_index + 1):
            resolved = _resolve_exit(candles[candle_index], stop_price, target_price)
            if resolved is not None:
                exit_index = candle_index
                exit_price, exit_reason = resolved
                break
        if exit_price is None:
            exit_price = candles[exit_index]["close"]

        exit_fill = exit_price * (1 - slippage_rate)
        gross_pnl = quantity * (exit_fill - entry_price)
        fees = fee_rate * quantity * (entry_price + exit_fill)
        net_pnl = gross_pnl - fees
        net_r = net_pnl / (quantity * risk_distance)
        equity += net_pnl
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 100.0
        max_drawdown_percent = max(max_drawdown_percent, drawdown)
        trades.append(
            {
                "entry_time": candles[entry_index]["time"],
                "exit_time": candles[exit_index]["time"],
                "entry_price": round(entry_price, 8),
                "stop_price": round(stop_price, 8),
                "target_price": round(target_price, 8),
                "exit_price": round(exit_fill, 8),
                "bars_held": exit_index - entry_index + 1,
                "exit_reason": exit_reason,
                "gross_pnl_quote": round(gross_pnl, 4),
                "fees_quote": round(fees, 4),
                "net_pnl_quote": round(net_pnl, 4),
                "net_r": round(net_r, 4),
            }
        )
        equity_curve.append({"time": candles[exit_index]["time"], "equity": round(equity, 2)})
        index = exit_index + 1

    if equity_curve[-1]["time"] != candles[end - 1]["time"]:
        equity_curve.append({"time": candles[end - 1]["time"], "equity": round(equity, 2)})

    wins = [trade for trade in trades if trade["net_pnl_quote"] > 0]
    losses = [trade for trade in trades if trade["net_pnl_quote"] < 0]
    gross_wins = sum(trade["net_pnl_quote"] for trade in wins)
    gross_losses = abs(sum(trade["net_pnl_quote"] for trade in losses))
    profit_factor = gross_wins / gross_losses if gross_losses else None
    metrics = {
        "sample_bars": end - start,
        "sample_start": candles[start]["time"],
        "sample_end": candles[end - 1]["time"],
        "trade_count": len(trades),
        "win_rate_percent": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "net_pnl_quote": round(equity - starting_capital, 2),
        "net_return_percent": round((equity / starting_capital - 1) * 100, 2),
        "expectancy_r": round(fmean(trade["net_r"] for trade in trades), 3) if trades else 0.0,
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "max_drawdown_percent": round(max_drawdown_percent, 2),
        "buy_hold_return_percent": round(
            _benchmark_return(candles, start, end, fee_rate, slippage_rate), 2
        ),
        "sample_end_exits": sum(trade["exit_reason"] == "sample_end" for trade in trades),
    }
    return {"metrics": metrics, "equity_curve": equity_curve, "trades": trades}


def run_strategy_backtest(
    candles: Sequence[Mapping[str, Any]],
    strategy_key: str,
    starting_capital: float = 10000.0,
    risk_percent: float = 1.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    max_holding_bars: int = 20,
) -> dict[str, Any]:
    """Replay one fixed rule set and report separate train and holdout windows."""
    if strategy_key not in STRATEGY_NAMES:
        raise BacktestInputError("choose one of the supported paper strategies")
    numeric_settings = (starting_capital, risk_percent, fee_bps, slippage_bps)
    if not all(isfinite(float(value)) for value in numeric_settings):
        raise BacktestInputError("replay settings must be finite numbers")
    if starting_capital <= 0 or not 0.05 <= risk_percent <= 5:
        raise BacktestInputError("capital must be positive and risk must be between 0.05% and 5%")
    if not 0 <= fee_bps <= 100 or not 0 <= slippage_bps <= 100:
        raise BacktestInputError("fee and slippage must be between 0 and 100 basis points")
    if isinstance(max_holding_bars, bool) or not isinstance(max_holding_bars, int) or not 1 <= max_holding_bars <= 100:
        raise BacktestInputError("maximum holding time must be between 1 and 100 candles")

    normalized = _normalize_candles(candles)
    split = int(len(normalized) * 0.7)
    if split <= 50 or split >= len(normalized):
        raise BacktestInputError("history must leave enough candles in both sample windows")
    fast_ema, slow_ema, atr = _indicator_series(normalized)
    fee_rate = fee_bps / 10000
    slippage_rate = slippage_bps / 10000
    training = _simulate_segment(
        normalized, 50, split, strategy_key, starting_capital, risk_percent,
        fee_rate, slippage_rate, max_holding_bars, fast_ema, slow_ema, atr,
    )
    out_of_sample = _simulate_segment(
        normalized, split, len(normalized), strategy_key, starting_capital, risk_percent,
        fee_rate, slippage_rate, max_holding_bars, fast_ema, slow_ema, atr,
    )
    return {
        "strategy": {"key": strategy_key, "name": STRATEGY_NAMES[strategy_key]},
        "training": training["metrics"],
        "out_of_sample": out_of_sample["metrics"],
        "equity_curve": out_of_sample["equity_curve"],
        "trades": out_of_sample["trades"][-100:],
    }
