"""LOKI v8 — event-driven backtester with long/short, walk-forward, Monte Carlo.

The loop is fully causal: a signal computed at the close of bar i-1 is
executed at bar i's open, and stops/targets are resolved intrabar against
bar i's high/low (gap-aware). No lookahead.

Regime-adaptive entries:
  * long  — allowed in BULL/RANGING (blocked in BEAR when `regime_filter`)
  * short — allowed in BEAR (requires `allow_short`), blocked in BULL
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .regime import regime_series
from .risk import RiskManager
from .strategy import EnsembleStrategy


@dataclass
class Trade:
    symbol: str
    side: str          # "long" | "short"
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    exit_reason: str   # "stop" | "target" | "signal" | "trailing" | "time" | "end"


@dataclass
class BacktestResult:
    symbol: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    calmar: float
    equity_curve: pd.Series = field(default_factory=pd.Series)
    trades: List[Trade] = field(default_factory=list)

    def summary(self) -> str:
        return "\n".join([
            f"=== Backtest: {self.symbol} ===",
            f"Initial capital : ${self.initial_capital:,.2f}",
            f"Final equity    : ${self.final_equity:,.2f}",
            f"Total return    : {self.total_return_pct:+.2f}%",
            f"CAGR            : {self.cagr_pct:+.2f}%",
            f"Trades          : {self.total_trades}",
            f"Win rate        : {self.win_rate_pct:.1f}%",
            f"Profit factor   : {self.profit_factor:.2f}",
            f"Avg win / loss  : ${self.avg_win:,.2f} / ${self.avg_loss:,.2f}",
            f"Max drawdown    : {self.max_drawdown_pct:.2f}%",
            f"Sharpe          : {self.sharpe:.2f}",
            f"Sortino         : {self.sortino:.2f}",
            f"Calmar          : {self.calmar:.2f}",
        ])


def _fill(price: float, side: str, cfg: LokiConfig) -> float:
    slip = cfg.slippage_bps / 10_000.0
    return price * (1 + slip) if side == "buy" else price * (1 - slip)


def bars_per_year_for(interval: str, crypto: bool = False) -> int:
    """Approximate bars/year for annualizing metrics at a given interval."""
    base = 365 if crypto else 252
    return {
        "1m": base * 390, "2m": base * 195, "5m": base * 78, "15m": base * 26,
        "30m": base * 13, "1h": base * 7, "4h": base * 2, "1d": base,
        "1wk": 52, "1mo": 12,
    }.get(interval, base)


def run_backtest(
    df: pd.DataFrame,
    cfg: LokiConfig,
    strategy: Optional[EnsembleStrategy] = None,
    symbol: str = "SYMBOL",
    bars_per_year: int = 252,
) -> BacktestResult:
    """Run an event-driven long/short backtest over `df` (OHLCV)."""
    strategy = strategy or EnsembleStrategy(cfg)
    df = df.copy()
    frame = strategy.score_frame(df)
    scores = frame["score"]
    atrs = frame["atr"]
    regimes = regime_series(frame)

    warmup = max(cfg.lookback_bars, 60)
    cash = cfg.initial_cash
    risk = RiskManager(cfg)

    pos = None  # dict(side, qty, entry, stop, target, entry_time, entry_bar)
    trades: List[Trade] = []
    equity_curve: List[float] = []
    times: List[pd.Timestamp] = []

    def equity_at(price: float) -> float:
        if pos is None:
            return cash
        return cash + pos["qty"] * price if pos["side"] == "long" else cash - pos["qty"] * price

    n = len(df)
    for i in range(warmup + 1, n):
        sig_score = float(scores.iloc[i - 1])
        action = strategy.action_for(sig_score)
        o = float(df["open"].iloc[i]); h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i]); c = float(df["close"].iloc[i])
        t = df.index[i]
        atr_prev = float(atrs.iloc[i - 1]); atr_now = float(atrs.iloc[i])
        regime = str(regimes.iloc[i - 1])

        # ------------------------------------------------------------------
        # Manage the existing position (stop / target / signal / time)
        # ------------------------------------------------------------------
        if pos is not None:
            exit_price: Optional[float] = None
            reason: Optional[str] = None
            long = pos["side"] == "long"

            if long:
                if pos["stop"] > 0 and l <= pos["stop"]:
                    exit_price, reason = min(o, pos["stop"]), "stop"
                elif pos["target"] > 0 and h >= pos["target"]:
                    exit_price, reason = max(o, pos["target"]), "target"
                elif action == "SELL":
                    exit_price, reason = c, "signal"
            else:  # short
                if pos["stop"] > 0 and h >= pos["stop"]:
                    exit_price, reason = max(o, pos["stop"]), "stop"
                elif pos["target"] > 0 and l <= pos["target"]:
                    exit_price, reason = min(o, pos["target"]), "target"
                elif action == "BUY":
                    exit_price, reason = c, "signal"

            if exit_price is None and cfg.max_hold_bars > 0 and (i - pos["entry_bar"]) >= cfg.max_hold_bars:
                exit_price, reason = c, "time"

            if exit_price is not None:
                if long:
                    fill = _fill(exit_price, "sell", cfg)
                    pnl = (fill - pos["entry"]) * pos["qty"] - cfg.commission_per_trade
                    pnl_pct = (fill / pos["entry"] - 1.0) * 100.0 if pos["entry"] else 0.0
                    cash += fill * pos["qty"] - cfg.commission_per_trade
                else:
                    fill = _fill(exit_price, "buy", cfg)
                    pnl = (pos["entry"] - fill) * pos["qty"] - cfg.commission_per_trade
                    pnl_pct = (pos["entry"] / fill - 1.0) * 100.0 if fill else 0.0
                    cash -= fill * pos["qty"] + cfg.commission_per_trade

                trades.append(Trade(
                    symbol=symbol, side=pos["side"], entry_time=pos["entry_time"], exit_time=t,
                    entry_price=pos["entry"], exit_price=fill, qty=pos["qty"],
                    pnl=pnl, pnl_pct=pnl_pct, exit_reason=reason or "end",
                ))
                risk.record_trade(pnl)
                pos = None
            else:
                # ATR trailing-stop ratchet
                if cfg.trailing_stop_atr > 0:
                    if long:
                        ns = c - cfg.trailing_stop_atr * atr_now
                        if ns > pos["stop"]:
                            pos["stop"] = ns
                    else:
                        ns = c + cfg.trailing_stop_atr * atr_now
                        if ns < pos["stop"]:
                            pos["stop"] = ns

        # ------------------------------------------------------------------
        # New entry (regime-gated long / short)
        # ------------------------------------------------------------------
        if pos is None:
            atr_pct_prev = float(frame["atr_pct"].iloc[i - 1]) if np.isfinite(frame["atr_pct"].iloc[i - 1]) else 0.0
            above_ma = float(frame["close"].iloc[i - 1]) > float(frame["sma_200"].iloc[i - 1])
            allow_vol = not (cfg.max_atr_pct > 0 and atr_pct_prev > cfg.max_atr_pct)
            bear = regime == "BEAR"

            if action == "BUY":
                allow_trend = (not cfg.require_trend_filter) or above_ma
                allow_regime = (not cfg.regime_filter) or (not bear)
                if allow_vol and allow_trend and allow_regime:
                    entry = _fill(o, "buy", cfg)
                    atr_val = atr_prev if np.isfinite(atr_prev) else entry * 0.02
                    stop = entry - cfg.stop_loss_atr * atr_val
                    target = entry + cfg.take_profit_atr * atr_val
                    qty = risk.position_size(equity_at(entry), entry, stop)
                    cost = qty * entry + cfg.commission_per_trade
                    if qty > 0 and cost <= cash:
                        cash -= cost
                        pos = {"side": "long", "qty": qty, "entry": entry, "stop": stop,
                               "target": target, "entry_time": t, "entry_bar": i}

            elif action == "SELL" and cfg.allow_short:
                allow_regime = (not cfg.regime_filter) or bear
                if allow_vol and allow_regime:
                    entry = _fill(o, "sell", cfg)
                    atr_val = atr_prev if np.isfinite(atr_prev) else entry * 0.02
                    stop = entry + cfg.stop_loss_atr * atr_val
                    target = entry - cfg.take_profit_atr * atr_val
                    qty = risk.position_size(equity_at(entry), entry, stop)
                    if qty > 0:
                        cash += entry * qty - cfg.commission_per_trade
                        pos = {"side": "short", "qty": qty, "entry": entry, "stop": stop,
                               "target": target, "entry_time": t, "entry_bar": i}

        equity_curve.append(equity_at(c))
        times.append(t)

    # Force-close any open position at the end
    if pos is not None:
        last_c = float(df["close"].iloc[-1])
        long = pos["side"] == "long"
        fill = _fill(last_c, "sell" if long else "buy", cfg)
        if long:
            pnl = (fill - pos["entry"]) * pos["qty"] - cfg.commission_per_trade
            pnl_pct = (fill / pos["entry"] - 1.0) * 100.0 if pos["entry"] else 0.0
            cash += fill * pos["qty"] - cfg.commission_per_trade
        else:
            pnl = (pos["entry"] - fill) * pos["qty"] - cfg.commission_per_trade
            pnl_pct = (pos["entry"] / fill - 1.0) * 100.0 if fill else 0.0
            cash -= fill * pos["qty"] + cfg.commission_per_trade
        trades.append(Trade(
            symbol=symbol, side=pos["side"], entry_time=pos["entry_time"], exit_time=df.index[-1],
            entry_price=pos["entry"], exit_price=fill, qty=pos["qty"],
            pnl=pnl, pnl_pct=pnl_pct, exit_reason="end",
        ))
        pos = None

    eq = pd.Series(equity_curve, index=times)
    return _build_result(symbol, cfg.initial_cash, eq, trades, bars_per_year)


def _build_result(symbol: str, initial: float, equity: pd.Series,
                  trades: List[Trade], bars_per_year: int) -> BacktestResult:
    final = float(equity.iloc[-1]) if len(equity) else initial
    total_ret = (final / initial - 1.0) * 100.0

    n_bars = len(equity)
    cagr = 0.0
    if n_bars > 1 and final > 0:
        years = n_bars / bars_per_year
        if years > 0:
            cagr = ((final / initial) ** (1.0 / years) - 1.0) * 100.0

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls) * 100.0) if pnls else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0

    returns = equity.pct_change().dropna()
    sharpe = _sharpe(returns, bars_per_year)
    sortino = _sortino(returns, bars_per_year)
    max_dd, _ = _max_drawdown(equity)
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else 0.0

    return BacktestResult(
        symbol=symbol, initial_capital=initial, final_equity=final,
        total_return_pct=total_ret, cagr_pct=cagr, total_trades=len(trades),
        win_rate_pct=win_rate, profit_factor=profit_factor, avg_win=avg_win,
        avg_loss=avg_loss, max_drawdown_pct=max_dd, sharpe=sharpe, sortino=sortino,
        calmar=calmar, equity_curve=equity, trades=trades,
    )


def _sharpe(returns: pd.Series, bars_per_year: int, rf: float = 0.02) -> float:
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    excess = returns - rf / bars_per_year
    return float(np.sqrt(bars_per_year) * excess.mean() / excess.std())


def _sortino(returns: pd.Series, bars_per_year: int, rf: float = 0.02) -> float:
    if len(returns) == 0:
        return 0.0
    excess = returns - rf / bars_per_year
    downside = np.minimum(excess.to_numpy(), 0.0)
    downside_dev = float(np.sqrt((downside ** 2).mean()))
    if downside_dev == 0 or np.isnan(downside_dev):
        return 0.0
    return float(np.sqrt(bars_per_year) * excess.mean() / downside_dev)


def _max_drawdown(equity: pd.Series) -> Tuple[float, pd.Series]:
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max * 100.0
    return float(dd.min()) if len(dd) else 0.0, dd


def monte_carlo(trades: List[Trade], n_sims: int = 1000) -> Dict[str, float]:
    """Bootstrap trade sequence to estimate return distribution."""
    pct_returns = [t.pnl_pct for t in trades]
    if not pct_returns:
        return {"mean": 0.0, "p5": 0.0, "p95": 0.0, "p_positive": 0.0}
    arr = np.array(pct_returns)
    finals = []
    for _ in range(n_sims):
        sample = np.random.choice(arr, size=len(arr), replace=True)
        finals.append((1 + sample / 100.0).prod() * 100.0 - 100.0)
    finals = np.array(finals)
    return {
        "mean": float(finals.mean()),
        "p5": float(np.percentile(finals, 5)),
        "p95": float(np.percentile(finals, 95)),
        "p_positive": float((finals > 0).mean() * 100.0),
    }


def walk_forward(
    df: pd.DataFrame,
    cfg: LokiConfig,
    symbol: str = "SYMBOL",
    n_splits: int = 4,
    bars_per_year: int = 252,
) -> List[BacktestResult]:
    """Backtest n_splits contiguous, non-overlapping out-of-sample folds."""
    n = len(df)
    warmup = max(cfg.lookback_bars, 60)
    tradeable = n - warmup
    if tradeable <= 0:
        return []
    fold_size = max(tradeable // n_splits, 1)

    results = []
    for k in range(n_splits):
        seg_start = k * fold_size
        seg_end = n if k == n_splits - 1 else warmup + (k + 1) * fold_size
        seg = df.iloc[seg_start:seg_end]
        if len(seg) < warmup + 10:
            continue
        results.append(run_backtest(seg, cfg, symbol=symbol, bars_per_year=bars_per_year))
    return results


def portfolio_backtest(
    dfs: Dict[str, pd.DataFrame],
    cfg: LokiConfig,
    bars_per_year: int = 252,
) -> BacktestResult:
    """Equal-weight portfolio backtest across multiple symbols.

    Splits the starting capital evenly, backtests each symbol independently,
    then combines the equity curves into one portfolio curve. Diversification
    usually smooths the drawdown versus any single symbol.
    """
    n = len(dfs)
    if n == 0:
        raise ValueError("no dataframes supplied")

    per_symbol = cfg.initial_cash / n
    curves: Dict[str, pd.Series] = {}
    all_trades: List[Trade] = []

    for sym, df in dfs.items():
        sub = LokiConfig(**{**cfg.to_dict(), "initial_cash": per_symbol})
        r = run_backtest(df, sub, symbol=sym, bars_per_year=bars_per_year)
        curves[sym] = r.equity_curve
        all_trades.extend(r.trades)

    combined = pd.DataFrame(curves).ffill().sum(axis=1).dropna()
    return _build_result("PORTFOLIO", cfg.initial_cash, combined, all_trades, bars_per_year)
