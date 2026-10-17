"""Vibe-derived factor research and causal, cost-aware shadow replay.

All functions consume local observations. No market-data connection, broker,
credential access, generated code execution, or live orders exist here.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from typing import Any

from core.strategy_lab import Bar, validate_bars
from third_party.vibe_trading.factor_analysis import compute_group_equity, compute_ic_series
from third_party.vibe_trading.indicators import compute_rsi

PROVENANCE = {
    "project": "Vibe-Trading",
    "license": "MIT",
    "archive_sha256": "7ab43d041d44ca9b4bc0c32e69ec763c6e406972edd9201f6e539be0bc8f8f76",
    "modules": [
        "agent/src/shadow_account/indicators.py",
        "agent/src/factors/factor_analysis_core.py",
    ],
    "adaptation": "Dependency-free Wilder RSI and paired-rank factor analysis; Loki fixed-rule replay.",
}


@dataclass(frozen=True)
class ShadowConfig:
    initial_capital: float = 10_000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    periods_per_year: int = 365
    max_exposure: float = 0.20
    risk_per_trade: float = 0.005
    max_drawdown: float = 0.15
    max_holding_bars: int = 30
    stop_atr_multiple: float = 2.0
    min_win_rate: float = 0.70

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{item.name} must be a finite number")
        for name in ("periods_per_year", "max_holding_bars"):
            if not isinstance(getattr(self, name), int):
                raise ValueError(f"{name} must be an integer")
        if not 0 < self.initial_capital <= 1e15:
            raise ValueError("initial_capital must be in (0, 1e15]")
        if not 0 <= self.fee_bps <= 500 or not 0 <= self.slippage_bps <= 500:
            raise ValueError("fee_bps and slippage_bps must be between 0 and 500")
        if not 1 <= self.periods_per_year <= 525_600:
            raise ValueError("periods_per_year must match the bar frequency (1..525600)")
        if not 0 < self.max_exposure <= 1 or not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("max_exposure must be in (0, 1]; risk_per_trade in (0, 0.05]")
        if not 0 < self.max_drawdown < 1:
            raise ValueError("max_drawdown must be between 0 and 1")
        if not 1 <= self.max_holding_bars <= 10_000 or not 0.5 <= self.stop_atr_multiple <= 10:
            raise ValueError("max_holding_bars must be 1..10000 and stop_atr_multiple 0.5..10")
        if not 0 <= self.min_win_rate <= 1:
            raise ValueError("min_win_rate must be between 0 and 1")


def _config(config: Mapping[str, Any] | ShadowConfig | None) -> ShadowConfig:
    if config is None:
        return ShadowConfig()
    if isinstance(config, ShadowConfig):
        return config
    if not isinstance(config, Mapping):
        raise ValueError("config must contain shadow-replay settings")
    try:
        return ShadowConfig(**config)
    except TypeError as exc:
        raise ValueError("Unknown shadow-replay settings") from exc


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 40:
        raise ValueError("symbol must contain 1..40 characters")
    if any(ord(character) < 32 for character in value):
        raise ValueError("symbol cannot contain control characters")
    return value.strip().upper()


def _bars(data: Sequence[Mapping[str, Any]], minimum: int) -> list[Bar]:
    bars = validate_bars(data)
    if len(bars) < minimum:
        raise ValueError(f"Need at least {minimum} completed OHLCV bars")
    prices = [value for bar in bars for value in (bar.open, bar.high, bar.low, bar.close)]
    if min(prices) < 1e-12 or max(prices) > 1e12 or max(prices) / min(prices) > 1e6:
        raise ValueError("Price range is too extreme for reliable factor accounting")
    if any(bar.volume > 1e15 for bar in bars):
        raise ValueError("Volume is too extreme for reliable factor accounting")
    return bars


def _features(bars: list[Bar], periods_per_year: int) -> list[dict[str, Any]]:
    closes = [bar.close for bar in bars]
    rsi = compute_rsi(closes)
    ranges = [
        (
            max(
                bar.high - bar.low,
                abs(bar.high - bars[index - 1].close),
                abs(bar.low - bars[index - 1].close),
            )
            if index
            else bar.high - bar.low
        )
        for index, bar in enumerate(bars)
    ]
    output = []
    for index, bar in enumerate(bars):
        if index < 20:
            output.append({"ready": False})
            continue
        recent = closes[index - 19 : index + 1]
        returns = [
            right / left - 1
            for left, right in zip(closes[index - 20 : index + 1], closes[index - 19 : index + 1])
        ]
        volume_mean = statistics.mean(item.volume for item in bars[index - 19 : index + 1])
        output.append(
            {
                "ready": True,
                "momentum5": bar.close / closes[index - 5] - 1,
                "momentum20": bar.close / closes[index - 20] - 1,
                "trend_gap": statistics.mean(recent[-5:]) / statistics.mean(recent) - 1,
                "above_sma20": bar.close / statistics.mean(recent) - 1,
                "rsi14": rsi[index],
                "relative_volume": bar.volume / volume_mean if volume_mean else None,
                "annualized_volatility": statistics.stdev(returns) * math.sqrt(periods_per_year),
                "atr14": statistics.mean(ranges[index - 13 : index + 1]),
                "drawdown20": bar.close / max(recent) - 1,
                "average_volume20": volume_mean,
                "support20": min(item.low for item in bars[index - 19 : index + 1]),
                "resistance20": max(item.high for item in bars[index - 19 : index + 1]),
            }
        )
    return output


def _conditions(feature: dict[str, Any], volume: float) -> list[dict[str, Any]]:
    if not feature["ready"]:
        return []
    rsi = feature["rsi14"]
    return [
        {
            "name": "Short trend above long trend",
            "passed": feature["trend_gap"] > 0,
            "observed": feature["trend_gap"],
            "threshold": "> 0",
        },
        {
            "name": "Close above 20-bar average",
            "passed": feature["above_sma20"] > 0,
            "observed": feature["above_sma20"],
            "threshold": "> 0",
        },
        {
            "name": "Five-bar momentum positive",
            "passed": feature["momentum5"] > 0,
            "observed": feature["momentum5"],
            "threshold": "> 0",
        },
        {
            "name": "RSI avoids weak or overheated entry",
            "passed": rsi is not None and 45 <= rsi <= 72,
            "observed": rsi,
            "threshold": "45..72",
        },
        {
            "name": "Completed candle has reported volume",
            "passed": volume > 0,
            "observed": volume,
            "threshold": "> 0",
        },
    ]


def analyze_factors(
    data: Sequence[Mapping[str, Any]], *, symbol: str = "BTC/USDT", periods_per_year: int = 365
) -> dict[str, Any]:
    """Inspect completed bars using causal Vibe-derived indicators.

    The score is the fraction of explicit entry conditions satisfied. It is
    deliberately not a calibrated trade-success probability.
    """
    symbol = _symbol(symbol)
    _config({"periods_per_year": periods_per_year})
    bars = _bars(data, 21)
    feature = _features(bars, periods_per_year)[-1]
    conditions = _conditions(feature, bars[-1].volume)
    labels = [
        ("momentum5", "5-bar momentum", "fraction", 5, "Recent directional price change."),
        ("momentum20", "20-bar momentum", "fraction", 20, "Medium-term directional price change."),
        (
            "trend_gap",
            "5/20 moving-average gap",
            "fraction",
            20,
            "Positive values indicate a rising short trend.",
        ),
        ("rsi14", "Wilder RSI", "index_0_100", 14, "Causal SMA seed; flat prices are undefined."),
        (
            "relative_volume",
            "Relative volume",
            "multiple",
            20,
            "Current completed volume divided by its 20-bar mean.",
        ),
        (
            "annualized_volatility",
            "Annualized volatility",
            "fraction",
            20,
            "Historical variability; frequency must match periods_per_year.",
        ),
        (
            "atr14",
            "14-bar average true range",
            "price",
            14,
            "Simple mean of true ranges, used for stop planning.",
        ),
        (
            "drawdown20",
            "Drawdown from 20-bar high close",
            "fraction",
            20,
            "Negative values describe recent loss from peak.",
        ),
    ]
    return {
        "symbol": symbol,
        "as_of": bars[-1].timestamp.isoformat(),
        "observations": len(bars),
        "mode": "research_only",
        "signal": {
            "stance": "long_candidate" if all(row["passed"] for row in conditions) else "cash",
            "score": sum(row["passed"] for row in conditions) / len(conditions),
            "score_meaning": "Fraction of fixed entry conditions met; not a win probability.",
            "conditions": conditions,
            "execution": "next_open_only",
        },
        "factors": [
            {
                "id": key,
                "label": label,
                "value": feature[key],
                "unit": unit,
                "lookback": lookback,
                "interpretation": interpretation,
            }
            for key, label, unit, lookback, interpretation in labels
        ],
        "risk": {
            key: feature[key]
            for key in (
                "annualized_volatility",
                "atr14",
                "drawdown20",
                "average_volume20",
                "support20",
                "resistance20",
            )
        },
        "provenance": dict(PROVENANCE),
        "limitations": [
            "All supplied candles must be completed and correctly ordered.",
            "Fixed indicators are descriptive, not validated predictive probabilities.",
            "No exchange calendar, corporate actions or point-in-time data audit is supplied.",
            "A 70% winning-trade target is a research threshold, never a guarantee.",
        ],
    }


def _win_interval(wins: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = statistics.NormalDist().inv_cdf(0.975)
    fraction = wins / count
    denominator = 1 + z * z / count
    centre = (fraction + z * z / (2 * count)) / denominator
    half = (
        z * math.sqrt(fraction * (1 - fraction) / count + z * z / (4 * count * count)) / denominator
    )
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _summary(initial: float, equity: list[float], trades: list[dict[str, Any]]) -> dict[str, Any]:
    peak, drawdown = initial, 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    wins = [row["pnl"] for row in trades if row["pnl"] > 0]
    losses = [row["pnl"] for row in trades if row["pnl"] < 0]
    final = equity[-1] if equity else initial
    return {
        "initial_capital": initial,
        "final_capital": final,
        "total_return": final / initial - 1,
        "max_drawdown": drawdown,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(trades) if trades else None,
        "win_rate_ci95": _win_interval(len(wins), len(trades)),
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "expectancy": statistics.mean(row["pnl"] for row in trades) if trades else None,
        "total_fees": sum(row["fees"] for row in trades),
        "total_slippage": sum(row["slippage"] for row in trades),
    }


def _replay(
    bars: list[Bar],
    features: list[dict[str, Any]],
    config: ShadowConfig,
    multiplier: float = 1.0,
    *,
    start_index: int = 21,
) -> dict[str, Any]:
    cash = config.initial_capital
    units = 0.0
    entry: dict[str, Any] | None = None
    high_close = 0.0
    equity: list[float] = []
    trades: list[dict[str, Any]] = []
    fee, slip = config.fee_bps * multiplier / 10_000, config.slippage_bps * multiplier / 10_000
    peak, halted = config.initial_capital, False
    if (
        isinstance(start_index, bool)
        or not isinstance(start_index, int)
        or not 21 <= start_index < len(bars)
    ):
        raise ValueError(
            "Replay start_index must leave at least 21 completed warmup bars and one test bar"
        )
    start = start_index

    def close(index: int, raw: float, reason: str) -> None:
        nonlocal cash, units, entry
        fill = raw * (1 - slip)
        proceeds, exit_fee = units * fill, units * fill * fee
        cash += proceeds - exit_fee
        trades.append(
            {
                "entry_timestamp": entry["timestamp"],
                "exit_timestamp": bars[index].timestamp.isoformat(),
                "entry_price": entry["price"],
                "exit_price": fill,
                "quantity": units,
                "pnl": proceeds - exit_fee - entry["outlay"],
                "fees": entry["fee"] + exit_fee,
                "slippage": entry["slippage"] + units * (raw - fill),
                "exit_reason": reason,
            }
        )
        units, entry = 0.0, None

    for index in range(start, len(bars)):
        bar, previous, feature = bars[index], bars[index - 1], features[index - 1]
        conditions = _conditions(feature, previous.volume)
        signal = bool(conditions) and all(row["passed"] for row in conditions)
        closed = False
        if units:
            high_close = max(high_close, previous.close)
            stop = previous.close <= high_close * (1 - entry["stop_fraction"])
            timed_out = index - entry["index"] >= config.max_holding_bars
            # A risk halt is decided from the previous completed mark, then
            # executed on this opening. The current candle is never consulted.
            if stop or timed_out or not signal or halted:
                reason = (
                    "drawdown_halt"
                    if halted
                    else (
                        "trailing_close_signal"
                        if stop
                        else "holding_limit" if timed_out else "factor_exit"
                    )
                )
                close(index, bar.open, reason)
                closed = True
        if not units and signal and not closed and not halted and index < len(bars) - 1:
            stop_fraction = min(
                0.15, max(0.02, config.stop_atr_multiple * feature["atr14"] / previous.close)
            )
            fill = bar.open * (1 + slip)
            risk_per_unit = fill * (1 + fee) - bar.open * (1 - stop_fraction) * (1 - slip) * (
                1 - fee
            )
            # Completed-bar volume caps participation; same-bar volume is unknown.
            units = min(
                cash * config.max_exposure / (fill * (1 + fee)),
                cash * config.risk_per_trade / risk_per_unit,
                previous.volume * 0.005,
            )
            outlay = units * fill * (1 + fee)
            cash -= outlay
            entry = {
                "index": index,
                "timestamp": bar.timestamp.isoformat(),
                "price": fill,
                "outlay": outlay,
                "fee": units * fill * fee,
                "slippage": units * (fill - bar.open),
                "stop_fraction": stop_fraction,
            }
            high_close = bar.open
        if index == len(bars) - 1 and units:
            close(index, bar.close, "window_end")
        mark = cash + units * bar.close
        equity.append(mark)
        peak = max(peak, mark)
        if mark / peak - 1 <= -config.max_drawdown:
            halted = True
    return {
        "equity": equity,
        "trades": trades,
        "summary": _summary(config.initial_capital, equity, trades),
        "drawdown_halt_triggered": halted,
    }


def run_shadow_replay(
    data: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | ShadowConfig | None = None,
    *,
    symbol: str = "BTC/USDT",
) -> dict[str, Any]:
    """Replay a fixed factor rule with next-open fills and both-side costs.

    This describes the supplied history. It is deliberately separated from the
    existing untouched-forward strategy lab and cannot certify a future win rate.
    """
    symbol, config = _symbol(symbol), _config(config)
    bars = _bars(data, 61)
    features = _features(bars, config.periods_per_year)
    primary = _replay(bars, features, config)
    stress = _replay(bars, features, config, 2.0)
    fee, slip = config.fee_bps / 10_000, config.slippage_bps / 10_000
    benchmark_units = config.initial_capital / (bars[21].open * (1 + slip) * (1 + fee))
    benchmark = [benchmark_units * bar.close for bar in bars[21:]]
    benchmark[-1] *= (1 - slip) * (1 - fee)
    summary = primary["summary"]
    interval = summary["win_rate_ci95"]
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                for bar in bars
            ],
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return {
        "symbol": symbol,
        "mode": "historical_shadow_replay",
        "data_fingerprint": fingerprint,
        "as_of": bars[-1].timestamp.isoformat(),
        "config": asdict(config),
        "summary": summary,
        "equity_curve": [
            {"timestamp": bar.timestamp.isoformat(), "equity": value, "benchmark": reference}
            for bar, value, reference in zip(bars[21:], primary["equity"], benchmark)
        ],
        "trades": primary["trades"],
        "benchmark": {
            "total_return": benchmark[-1] / config.initial_capital - 1,
            "final_capital": benchmark[-1],
        },
        "cost_stress": [
            {
                "cost_multiplier": multiplier,
                **{
                    key: result["summary"][key]
                    for key in ("total_return", "max_drawdown", "win_rate")
                },
            }
            for multiplier, result in ((1, primary), (2, stress))
        ],
        "target": {
            "win_rate": config.min_win_rate,
            "observed_met": summary["win_rate"] is not None
            and summary["win_rate"] >= config.min_win_rate,
            "descriptive_lower_bound_met": interval is not None
            and interval[0] >= config.min_win_rate,
            "supported": False,
        },
        "drawdown_halt_triggered": primary["drawdown_halt_triggered"],
        "live_trading_enabled": False,
        "provenance": dict(PROVENANCE),
        "limitations": [
            "Historical fixed-rule replay is not untouched out-of-sample validation.",
            "Signals use completed bars; fills use the following open with fees and slippage on both sides.",
            "Stops use a completed close and fill on the following open; a price gap can exceed planned loss.",
            "Participation is capped at 0.5% of the preceding candle's volume; order-book liquidity is not modeled.",
            "No leverage, shorting, exchange minimums, funding, tax, corporate actions or partial fills.",
            "The 95% Wilson interval is descriptive and assumes independent trades; no future win rate is guaranteed.",
        ],
    }


def evaluate_factor_panel(
    factors: Mapping[str, Mapping[str, float | None]],
    forward_returns: Mapping[str, Mapping[str, float | None]],
    *,
    n_groups: int = 5,
) -> dict[str, Any]:
    """Evaluate aligned cross-sectional panels using Vibe's paired-rank math.

    Returns must be point-in-time labels after each factor timestamp. This API
    cannot establish that provenance itself. Use nonoverlapping label periods
    when interpreting cumulative quantile equity.
    """
    if not isinstance(factors, Mapping) or not isinstance(forward_returns, Mapping):
        raise ValueError("factors and forward_returns must be timestamp-to-symbol mappings")
    if len(factors) > 10_000 or len(forward_returns) > 10_000:
        raise ValueError("Factor panels support at most 10000 observations")
    total_cells = 0
    for panel_index, panel in enumerate((factors, forward_returns)):
        for timestamp, row in panel.items():
            if not isinstance(timestamp, str) or not isinstance(row, Mapping) or len(row) > 1000:
                raise ValueError(
                    "Each factor-panel timestamp needs a symbol mapping of at most 1000 assets"
                )
            total_cells += len(row)
            if total_cells > 200_000:
                raise ValueError("Factor panels support at most 200000 total cells")
            for symbol, value in row.items():
                if not isinstance(symbol, str) or (
                    value is not None
                    and (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                    )
                ):
                    raise ValueError("Factor values must be finite numbers or None")
                if panel_index == 1 and value is not None and value < -1:
                    raise ValueError("Unlevered forward returns cannot be less than -1")
    ic = compute_ic_series(factors, forward_returns)
    values = [row["ic"] for row in ic]
    deviation = statistics.stdev(values) if len(values) > 1 else 0
    return {
        "mode": "factor_diagnostics",
        "observations": len(ic),
        "ic_series": ic,
        "mean_ic": statistics.mean(values) if values else None,
        "ic_information_ratio": statistics.mean(values) / deviation if deviation else None,
        "group_equity": compute_group_equity(factors, forward_returns, n_groups),
        "provenance": dict(PROVENANCE),
        "limitations": [
            "IC needs five paired assets per timestamp; missing/constant ranks are omitted.",
            "Factor labels must occur strictly after factor observation; caller supplies that evidence.",
            "Quantile equity is gross and omits fees; overlapping labels are not investable compounded returns.",
        ],
    }
