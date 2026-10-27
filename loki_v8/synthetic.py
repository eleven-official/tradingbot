"""Simulated-tape augmentation and robustness validation.

The problem this solves
-----------------------
A grid sweep over one real tape cannot tell structure from accident. Ten years
of daily bars is ~3,650 observations, and a 370-combination search will always
find a corner of that sample where one parameter set looks like an edge — the
optimizer is *supposed* to find it. The honest question is not "does it make
money on the bars it was fitted to" but "does it still work on a tape with the
same statistics that it has never seen".

So the book is validated twice beyond the historical holdout:

1. **Cross-window.** The winning parameter set is re-run over the trailing 5,
   7 and 10 years independently. Parameters that only work because of one
   regime (the 2021 crypto mania, then the 2022 bust) fail the short windows.
2. **Simulated tape.** Tapes are rebuilt from the symbol's *own* return
   distribution with a stationary block bootstrap: contiguous blocks of
   realised log returns are resampled with replacement, and each sampled bar
   carries its donor bar's own OHLC geometry (open/high/low relative to close)
   and volume. That preserves fat tails, volatility clustering at the block
   scale, and the intra-bar shape that ATR-based stops depend on — while
   destroying the specific sequence the optimizer memorised.

Both checks are diagnostics, not evidence of future profit. They are reported
next to the metrics they gate, never instead of them, and the snapshot records
that they reuse the same underlying history.

Everything here is deterministic: same tape + same seed ⇒ byte-identical bars,
so a re-run of training cannot move the goalposts.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

OHLCV_COLUMNS: Sequence[str] = ("open", "high", "low", "close", "volume")

# Blocks long enough to keep volatility clustering, short enough to break the
# year-over-year path the optimizer saw. 20 daily bars ≈ one trading month.
DEFAULT_BLOCK_SIZE = 20

# Tapes the validator generates per symbol. Five, not three, because the gate
# pools fills across tapes and a wide-target profile only fires a handful of
# times per tape: at three seeds a good profile could fail the pooled-fill
# floor without the tapes ever saying anything about its edge. Each extra seed
# is one backtest over an already-generated tape, so the cost is small next to
# the grid sweep it validates.
DEFAULT_SEEDS: Sequence[int] = (11, 23, 37, 53, 71)

# Windows re-tested after selection. Mirrors the ask: 10→5 years of history.
DEFAULT_WINDOWS: Sequence[int] = (5, 7, 10)

# Gating thresholds. Deliberately loose: these exist to catch a profile that
# only works on its own sample, not to re-run the hurdle set. The historical
# hurdles are the strict test; these are the "does it survive anything else"
# test. A single unlucky seed must not be able to fail an otherwise sound
# profile, hence the pooled-profit-factor floor rather than per-seed.
WINDOW_MIN_TRADES = 3
WINDOW_MIN_PROFIT_FACTOR = 1.05
WINDOW_MIN_RETURN_PCT = 0.0

SYNTHETIC_MIN_TRADES = 10
SYNTHETIC_MIN_PROFIT_FACTOR = 1.05
SYNTHETIC_MIN_RETURN_PCT = 0.0
SYNTHETIC_MIN_PROFITABLE_SHARE = 0.66
SYNTHETIC_MAX_DRAWDOWN_PCT = -45.0

# Anything shorter cannot warm up the factor stack (lookback 250 + trades).
MIN_TAPE_BARS = 400


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one robustness check (a window or a synthetic tape)."""

    label: str
    bars: int
    metrics: Dict[str, float]
    passes: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "bars": self.bars,
            "metrics": self.metrics,
            "passes": self.passes,
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Tape construction
# ---------------------------------------------------------------------------


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise columns/order and drop rows that cannot describe a bar."""
    df = frame.rename(columns={c: str(c).lower() for c in frame.columns}).copy()
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"tape missing column(s): {', '.join(missing)}")
    df = df[list(OHLCV_COLUMNS)]
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["open", "high", "low", "close"])
    df = df[df["close"] > 0]
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = df["volume"].fillna(0.0).clip(lower=0.0)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _infer_freq(index: pd.DatetimeIndex) -> Optional[str]:
    """Best-effort calendar step for the generated tape."""
    if len(index) < 3:
        return None
    try:
        freq = pd.infer_freq(index)
    except (ValueError, TypeError):
        freq = None
    if freq in {"D", "B", "h", "H", "min", "T"}:
        return freq
    return None


def tape_fingerprint(frame: pd.DataFrame) -> str:
    """Deterministic id for a tape, so a report can name what it ran on."""
    close = np.round(frame["close"].to_numpy(dtype=float), 10)
    digest = hashlib.blake2b(close.tobytes(), digest_size=8).hexdigest()
    return f"{len(frame)}b:{digest}"


def block_bootstrap(
    frame: pd.DataFrame,
    n_bars: int,
    *,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seed: int = 0,
    anchor_price: Optional[float] = None,
) -> pd.DataFrame:
    """Rebuild a tape of ``n_bars`` bars from contiguous return blocks.

    Sampling is over *transitions*, not bars: a block of ``b`` consecutive log
    returns is lifted whole, so the within-block volatility pattern (a quiet
    week, then a liquidation cascade) survives. Each generated bar also takes
    the donor bar's own shape — ``open/close``, ``high/close``, ``low/close``
    and volume — which is what keeps ATR, wick ratios and volume-flow factors
    inside the same distribution as reality.

    The result starts at ``anchor_price`` (default: the source's first close),
    so price-level dependent filters behave as they would on the real tape.
    """
    df = _clean(frame)
    if len(df) < block_size + 2:
        raise ValueError(f"need at least {block_size + 2} bars, got {len(df)}")
    if n_bars < 2:
        raise ValueError("n_bars must be >= 2")

    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)

    # Donor bar k is the transition close[k-1] -> close[k]; its shape is
    # expressed relative to its own close so it can be re-applied at any price.
    log_ret = np.diff(np.log(close))                    # length n-1
    shape_open = open_[1:] / close[1:]
    shape_high = high[1:] / close[1:]
    shape_low = low[1:] / close[1:]
    donor_volume = volume[1:]

    usable = len(log_ret)
    block_size = int(max(2, min(block_size, usable)))
    starts_pool = usable - block_size + 1

    rng = np.random.default_rng(seed)
    n_transitions = n_bars - 1
    picks: List[np.ndarray] = []
    collected = 0
    while collected < n_transitions:
        start = int(rng.integers(0, starts_pool))
        picks.append(np.arange(start, start + block_size))
        collected += block_size
    donor_idx = np.concatenate(picks)[:n_transitions]

    rets = log_ret[donor_idx]
    level = anchor_price if anchor_price is not None else float(close[0])
    closes = level * np.exp(np.cumsum(rets))
    prev_closes = np.concatenate(([level], closes[:-1]))

    opens = prev_closes * shape_open[donor_idx]
    body_high = np.maximum(opens, closes)
    body_low = np.minimum(opens, closes)
    # Keep donor wicks but never invert the bar: high >= body, low <= body.
    highs = np.maximum(body_high, closes * shape_high[donor_idx])
    lows = np.minimum(body_low, closes * shape_low[donor_idx])
    vols = donor_volume[donor_idx]

    freq = _infer_freq(df.index)
    if freq:
        index = pd.date_range(start=df.index[0], periods=n_bars, freq=freq)
    else:
        # Fall back to the source cadence: replay the observed step pattern.
        step = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(days=1)
        index = pd.DatetimeIndex([df.index[0] + step * i for i in range(n_bars)])

    # Bar 0 is the anchor: it carries the price level, not a transition.
    out = pd.DataFrame(
        {
            "open": np.concatenate(([level], opens)),
            "high": np.concatenate(([level], highs)),
            "low": np.concatenate(([level], lows)),
            "close": np.concatenate(([level], closes)),
            "volume": np.concatenate(([float(volume[0])], vols)),
        },
        index=index,
    )
    out.index.name = df.index.name or "datetime"
    return out


def synthetic_tapes(
    frame: pd.DataFrame,
    *,
    count: int = len(DEFAULT_SEEDS),
    bars: Optional[int] = None,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seeds: Optional[Sequence[int]] = None,
) -> List[pd.DataFrame]:
    """Generate ``count`` deterministic tapes from one real tape."""
    seed_list = tuple(seeds) if seeds else DEFAULT_SEEDS[:count]
    n_bars = int(bars or max(MIN_TAPE_BARS, len(frame)))
    return [
        block_bootstrap(frame, n_bars, block_size=block_size, seed=int(seed))
        for seed in seed_list
    ]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _evaluate(
    frame: pd.DataFrame,
    params: Dict[str, Any],
    cfg: Any,
    symbol: str,
    bars_per_year: int,
) -> tuple[Dict[str, float], List[Any]]:
    """Score ``frame`` once, run the backtest, return (metrics, trades)."""
    from loki_v8.backtest import run_backtest
    from loki_v8.strategy import EnsembleStrategy
    from loki_v8.train import _cfg_with, _oos_metrics

    candidate = _cfg_with(cfg, params or {})
    scored = EnsembleStrategy(candidate).score_frame(frame)
    result = run_backtest(
        frame,
        candidate,
        symbol=symbol,
        bars_per_year=bars_per_year,
        frame=scored,
    )
    return _oos_metrics(result.trades, candidate.initial_cash), list(result.trades)


def evaluate_params(
    frame: pd.DataFrame,
    params: Dict[str, Any],
    cfg: Any,
    symbol: str,
    bars_per_year: int,
) -> Dict[str, float]:
    """Metrics only — the shape most callers want."""
    metrics, _ = _evaluate(frame, params, cfg, symbol, bars_per_year)
    return metrics


def _window_reasons(metrics: Dict[str, float]) -> List[str]:
    reasons: List[str] = []
    if metrics.get("trades", 0) < WINDOW_MIN_TRADES:
        reasons.append(f"trades {metrics.get('trades', 0)} < {WINDOW_MIN_TRADES}")
    if metrics.get("profit_factor", 0.0) < WINDOW_MIN_PROFIT_FACTOR:
        reasons.append(
            f"profit factor {metrics.get('profit_factor', 0.0)} < {WINDOW_MIN_PROFIT_FACTOR}"
        )
    if metrics.get("return_pct", 0.0) <= WINDOW_MIN_RETURN_PCT:
        reasons.append(f"return {metrics.get('return_pct', 0.0)}% <= {WINDOW_MIN_RETURN_PCT}%")
    return reasons


def validate_windows(
    history: pd.DataFrame,
    params: Dict[str, Any],
    cfg: Any,
    symbol: str,
    bars_per_year: int,
    windows: Sequence[int] = DEFAULT_WINDOWS,
) -> Dict[str, Any]:
    """Re-run one parameter set over trailing N-year slices of the same tape.

    A parameter set that needs the full decade to work is fragile: it means
    the edge lives in a regime that has already happened. Short windows are
    the cheapest honest check available because the bars are already on disk.
    """
    df = _clean(history)
    results: List[Dict[str, Any]] = []
    for years in sorted({int(y) for y in windows if int(y) > 0}):
        bars = int(years * bars_per_year)
        window = df if bars >= len(df) else df.iloc[-bars:]
        if len(window) < MIN_TAPE_BARS:
            results.append(
                CheckResult(
                    label=f"{years}y",
                    bars=len(window),
                    metrics={},
                    passes=False,
                    reasons=[f"insufficient history ({len(window)} bars)"],
                ).to_dict()
            )
            continue
        try:
            metrics = evaluate_params(window, params, cfg, symbol, bars_per_year)
            reasons = _window_reasons(metrics)
        except Exception as exc:  # noqa: BLE001 - one bad slice is a failed check
            logger.warning("%s %dy window failed: %s", symbol, years, exc)
            metrics, reasons = {}, [f"error: {exc}"]
        results.append(
            CheckResult(
                label=f"{years}y",
                bars=len(window),
                metrics=metrics,
                passes=not reasons,
                reasons=reasons,
            ).to_dict()
        )

    passes = bool(results) and all(item["passes"] for item in results)
    return {
        "windows": results,
        "passes": passes,
        "min_trades": WINDOW_MIN_TRADES,
        "min_profit_factor": WINDOW_MIN_PROFIT_FACTOR,
        "note": (
            "Trailing slices of the same history, re-run with the selected parameters. "
            "Overlapping data: this tests regime dependence, not independent samples."
        ),
    }


def _pooled_metrics(trades: List[Any], tape_count: int, initial_cash: float) -> Dict[str, float]:
    """Aggregate metrics across tapes from the pooled trade list."""
    if not trades:
        return {
            "trades": 0,
            "return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
        }
    pnls = [float(t.pnl) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    curve = pd.Series(pnls).cumsum()
    max_dd = float((curve - curve.cummax()).min())
    mean_return = sum(pnls) / max(1, tape_count) / initial_cash * 100.0 if initial_cash else 0.0
    return {
        "trades": len(pnls),
        "return_pct": round(mean_return, 2),
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1),
        "profit_factor": round(pf, 2) if math.isfinite(pf) else 999.0,
        "max_drawdown_pct": round(max_dd / initial_cash * 100.0, 2) if initial_cash else 0.0,
    }


def validate_synthetic(
    history: pd.DataFrame,
    params: Dict[str, Any],
    cfg: Any,
    symbol: str,
    bars_per_year: int,
    *,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    bars: Optional[int] = None,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> Dict[str, Any]:
    """Run the selected parameters on bootstrapped tapes the optimizer never saw."""
    df = _clean(history)
    n_bars = int(bars or max(MIN_TAPE_BARS, len(df)))
    initial_cash = float(getattr(cfg, "initial_cash", 100_000.0))

    per_tape: List[Dict[str, Any]] = []
    metrics_list: List[Dict[str, float]] = []
    pooled_trades: List[Any] = []
    for seed in seeds:
        try:
            tape = block_bootstrap(df, n_bars, block_size=block_size, seed=int(seed))
            metrics, trades = _evaluate(tape, params, cfg, symbol, bars_per_year)
        except Exception as exc:  # noqa: BLE001 - one bad tape is a failed check
            logger.warning("%s synthetic seed %s failed: %s", symbol, seed, exc)
            per_tape.append(
                {"seed": int(seed), "metrics": {}, "fingerprint": "", "error": str(exc)}
            )
            continue
        per_tape.append(
            {"seed": int(seed), "metrics": metrics, "fingerprint": tape_fingerprint(tape)}
        )
        metrics_list.append(metrics)
        pooled_trades.extend(trades)

    if not metrics_list:
        return {
            "tapes": per_tape,
            "passes": False,
            "pooled": {},
            "reasons": ["every synthetic tape failed to evaluate"],
            "seeds": list(seeds),
            "bars": n_bars,
            "block_size": int(block_size),
            "thresholds": {
                "min_trades": SYNTHETIC_MIN_TRADES,
                "min_profit_factor": SYNTHETIC_MIN_PROFIT_FACTOR,
                "min_return_pct": SYNTHETIC_MIN_RETURN_PCT,
                "min_profitable_share": SYNTHETIC_MIN_PROFITABLE_SHARE,
                "max_drawdown_pct": SYNTHETIC_MAX_DRAWDOWN_PCT,
            },
        }

    pooled = _pooled_metrics(pooled_trades, len(metrics_list), initial_cash)
    profitable = [m for m in metrics_list if float(m.get("return_pct", 0.0)) > 0.0]
    profitable_share = round(len(profitable) / len(metrics_list), 3)

    # Two different failures live in this block, and conflating them mislabels
    # the result. "The tapes lost money" is evidence against an edge. "The
    # tapes only traded six times" is the absence of evidence — a wide target
    # against a wide stop simply does not fire often enough on a three-tape
    # sample to measure anything. Both must keep `passes` False (never promote
    # on thin evidence), but only the first is a verdict about the strategy.
    reasons: List[str] = []
    evidence: List[str] = []
    if pooled["trades"] < SYNTHETIC_MIN_TRADES:
        evidence.append(f"pooled trades {pooled['trades']} < {SYNTHETIC_MIN_TRADES}")
    edge_reasons: List[str] = []
    if pooled["profit_factor"] < SYNTHETIC_MIN_PROFIT_FACTOR:
        edge_reasons.append(
            f"pooled profit factor {pooled['profit_factor']} < {SYNTHETIC_MIN_PROFIT_FACTOR}"
        )
    if pooled["return_pct"] <= SYNTHETIC_MIN_RETURN_PCT:
        edge_reasons.append(f"mean return {pooled['return_pct']}% <= {SYNTHETIC_MIN_RETURN_PCT}%")
    if profitable_share < SYNTHETIC_MIN_PROFITABLE_SHARE:
        edge_reasons.append(
            f"profitable tapes {profitable_share:.0%} < {SYNTHETIC_MIN_PROFITABLE_SHARE:.0%}"
        )
    if pooled["max_drawdown_pct"] < SYNTHETIC_MAX_DRAWDOWN_PCT:
        edge_reasons.append(
            f"worst tape drawdown {pooled['max_drawdown_pct']}% < {SYNTHETIC_MAX_DRAWDOWN_PCT}%"
        )
    reasons = evidence + edge_reasons
    # `powered` = there were enough fills to actually judge the edge. It is what
    # separates "untested" from "failed", and it never implies a pass.
    powered = not evidence

    return {
        "tapes": per_tape,
        "pooled": pooled,
        "profitable_share": profitable_share,
        "passes": not reasons,
        "powered": powered,
        "evidence_reasons": evidence,
        "edge_reasons": edge_reasons,
        "reasons": reasons,
        "seeds": [int(s) for s in seeds],
        "bars": n_bars,
        "block_size": int(block_size),
        "source_fingerprint": tape_fingerprint(df),
        "thresholds": {
            "min_trades": SYNTHETIC_MIN_TRADES,
            "min_profit_factor": SYNTHETIC_MIN_PROFIT_FACTOR,
            "min_return_pct": SYNTHETIC_MIN_RETURN_PCT,
            "min_profitable_share": SYNTHETIC_MIN_PROFITABLE_SHARE,
            "max_drawdown_pct": SYNTHETIC_MAX_DRAWDOWN_PCT,
        },
        "note": (
            "Bars are bootstrapped from this symbol's own realised return blocks, "
            "not new information. Passing means the parameters do not depend on the "
            "specific path they were fitted to; it is not evidence of future profit."
        ),
    }


def summarise(window: Optional[Dict[str, Any]], synthetic: Optional[Dict[str, Any]]) -> str:
    """One-line status for the training log."""
    parts: List[str] = []
    if window:
        failed = [w["label"] for w in window.get("windows", []) if not w["passes"]]
        parts.append("windows ok" if window.get("passes") else f"windows fail ({','.join(failed)})")
    if synthetic:
        pooled = synthetic.get("pooled") or {}
        if synthetic.get("passes"):
            parts.append(
                f"sim ok (pf {pooled.get('profit_factor', 0)}, {synthetic.get('profitable_share', 0):.0%} profitable)"
            )
        elif synthetic.get("powered") is False:
            # Not a failed edge — the tapes could not fill enough orders to
            # measure one. Say that instead of printing "fail".
            parts.append(
                f"sim untested ({'; '.join(synthetic.get('evidence_reasons', []))[:60]})"
            )
        else:
            parts.append(f"sim fail ({'; '.join(synthetic.get('reasons', []))[:60]})")
    return " | ".join(parts) if parts else ""
