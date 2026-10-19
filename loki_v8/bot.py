"""LOKI v8 — orchestrator.

Wires the subsystems together and exposes the three operating modes:

    backtest  — validate a strategy on historical data (walk-forward + MC)
    paper     — trade the live market with the local simulator (no real money)
    live      — trade a real broker (requires credentials; fails closed)

Both paper and live consume the *same* live market data, so the only
difference between the modes is where orders are routed.
"""

from __future__ import annotations

import logging
import time
import logging
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .agents import LokiAgentPipeline
from .backtest import (
    BacktestResult,
    bars_per_year_for,
    monte_carlo,
    portfolio_backtest,
    run_backtest,
    walk_forward,
)
from .broker import PaperBroker, make_broker
from .config import LokiConfig, default_config
from .data import get_provider, is_crypto
from .persistence import get_logger as get_db_logger
from .regime import Regime, detect_regime
from .risk import RiskManager
from .strategy import EnsembleStrategy, Signal
from .train import apply_best as _train_apply_best
from .train import load_report as _train_load_report

logger = logging.getLogger(__name__)


class LokiBot:
    def __init__(self, cfg: Optional[LokiConfig] = None):
        self.cfg = cfg or default_config()
        self.provider = get_provider()
        self.strategy = EnsembleStrategy(self.cfg)
        self.risk = RiskManager(self.cfg)
        self.broker = make_broker(self.cfg)
        self.mode = self.cfg.mode
        self.last_quotes: Dict[str, float] = {}
        # Per-symbol latest-bar context (ATR) for smart exit management
        self._last_context: Dict[str, Dict[str, float]] = {}
        # Symbols that already had a partial scale-out this position life
        self._scaled_out: set = set()
        # Optional Supabase vault logging state (no-op unless configured)
        self._db = get_db_logger()
        self._db_trades_logged = 0
        self._last_equity_log = 0.0
        self._last_regime_check = 0.0
        self._last_regimes: Dict[str, str] = {}
        self._risk_day = datetime.now(timezone.utc).date()
        self._risk_trades_recorded = 0

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def switch_mode(self, mode: str):
        """Switch between 'paper' and 'live'. Live fails closed without keys."""
        if mode not in ("paper", "live"):
            raise ValueError(f"unknown mode: {mode}")
        if mode == self.mode:
            return
        if self.broker.positions:
            raise ValueError("Close paper positions before switching mode")
        candidate = make_broker(replace(self.cfg, mode=mode))
        self.broker = candidate
        self.mode = mode
        self.cfg.mode = mode
        logger.info("Switched to %s mode", mode.upper())

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def scan(self, symbols: Optional[List[str]] = None) -> List[Signal]:
        """Generate current signals for a list of symbols."""
        signals: List[Signal] = []
        for sym in symbols or self.cfg.symbols:
            try:
                df = self.provider.fetch_history(sym, self.cfg.period, self.cfg.timeframe)
                frame = self.strategy.score_frame(df)
                if len(frame):
                    last = frame.iloc[-1]
                    raw_atr = last.get("atr", float("nan"))
                    atr_val = float(raw_atr) if np.isfinite(raw_atr) else 0.0
                    self._last_context[sym] = {"atr": max(atr_val, 0.0)}
                sig = self.strategy.generate_signal(df, sym)
                if sig is not None:
                    signals.append(sig)
            except Exception as exc:  # noqa: BLE001
                logger.warning("scan failed for %s: %s", sym, exc)
        signals.sort(key=lambda s: -abs(s.score))
        return signals

    def agent_scan(self, symbols: Optional[List[str]] = None, *, execute: bool = False) -> Dict:
        """Run the full Director→Quant→Risk→Execution pipeline.

        Returns a structured decision trail per symbol (auditable JSON),
        and executes paper orders only when explicitly requested.
        """
        pipeline = LokiAgentPipeline(self.cfg, broker=self.broker)
        report = pipeline.run_universe(
            symbols, equity=self.broker.equity(self.last_quotes), execute=execute
        )
        return report

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------
    def backtest(
        self, symbol: str, period: Optional[str] = None, interval: Optional[str] = None
    ) -> BacktestResult:
        interval = interval or self.cfg.timeframe
        df = self.provider.fetch_history(symbol, period or self.cfg.period, interval)
        if df.empty:
            raise RuntimeError(f"no data for {symbol}")
        bpy = bars_per_year_for(interval, crypto=is_crypto(symbol))
        return run_backtest(df, self.cfg, self.strategy, symbol, bars_per_year=bpy)

    def backtest_trained(
        self, symbol: str, period: Optional[str] = None, interval: Optional[str] = None
    ) -> Tuple[BacktestResult, Dict[str, Any]]:
        """Backtest with the symbol's trained profile applied.

        The training report's per-symbol winner (threshold, stops, smart-exit
        knobs, factor weights) is applied to an EPHEMERAL config + strategy
        pair, so the shared live bot is never mutated. When no trained
        profile exists for the symbol (e.g. a fresh deployment), it degrades
        gracefully to the plain config. Returns ``(result, applied_params)``.
        """
        interval = interval or self.cfg.timeframe
        df = self.provider.fetch_history(symbol, period or self.cfg.period, interval)
        if df.empty:
            raise RuntimeError(f"no data for {symbol}")
        cfg = replace(self.cfg)
        applied: Dict[str, Any] = {}
        try:
            report = _train_load_report(cfg)
            if report:
                applied = _train_apply_best(report, symbol, cfg)
        except Exception as exc:  # noqa: BLE001 - analytics must not break on a bad file
            logger.warning("trained profile unavailable for %s: %s", symbol, exc)
        if applied:
            strategy = EnsembleStrategy(cfg)
        else:
            strategy = self.strategy
        bpy = bars_per_year_for(interval, crypto=is_crypto(symbol))
        res = run_backtest(df, cfg, strategy, symbol, bars_per_year=bpy)
        return res, applied

    def backtest_all(self, symbols: Optional[List[str]] = None) -> Dict[str, BacktestResult]:
        out: Dict[str, BacktestResult] = {}
        for sym in symbols or self.cfg.symbols:
            try:
                out[sym] = self.backtest(sym)
            except Exception as exc:  # noqa: BLE001
                logger.warning("backtest failed for %s: %s", sym, exc)
        return out

    def walk_forward(
        self, symbol: str, n_splits: int = 4, period: str = "10y"
    ) -> List[BacktestResult]:
        df = self.provider.fetch_history(symbol, period, self.cfg.timeframe)
        return walk_forward(df, self.cfg, symbol, n_splits=n_splits)

    def portfolio_backtest(
        self, symbols: Optional[List[str]] = None, period: str = "5y"
    ) -> BacktestResult:
        """Backtest an equal-weight portfolio of symbols with shared capital."""
        dfs: Dict[str, pd.DataFrame] = {}
        for sym in symbols or self.cfg.symbols:
            df = self.provider.fetch_history(sym, period, self.cfg.timeframe)
            if not df.empty:
                dfs[sym] = df
        return portfolio_backtest(dfs, self.cfg)

    # ------------------------------------------------------------------
    # Paper / live loop
    # ------------------------------------------------------------------
    def _refresh_quotes(self) -> Dict[str, float]:
        quotes = self.provider.get_quotes(self.cfg.symbols)
        self.last_quotes = quotes
        return quotes

    def _manage_exits(self, quotes: Dict[str, float]):
        """Manage open paper positions.

        Order of operations mirrors the backtester:
        1. legacy stop/target check on the remaining quantity,
        2. smart management — breakeven lock once up ``cfg.breakeven_atr``
           ATR (stop moved to entry + a small cost cushion), optional
           (``cfg.arm_trailing_atr``-armed) ATR trailing ratchet,
        3. one-time partial scale-out at ``cfg.partial_tp_atr`` ATR banking
           ``cfg.partial_fraction`` of the position.
        """
        for sym in list(self.broker.positions.keys()):
            price = quotes.get(sym)
            if price is None:
                continue
            pos = self.broker.positions[sym]
            long = pos.qty >= 0

            # 1) Legacy stop / target on the remaining quantity
            if long:
                if pos.stop_loss > 0 and price <= pos.stop_loss:
                    self.broker.close(sym, price)
                    self._scaled_out.discard(sym)
                    logger.info("STOP hit: %s @ %.2f", sym, price)
                    continue
                elif pos.take_profit > 0 and price >= pos.take_profit:
                    self.broker.close(sym, price)
                    self._scaled_out.discard(sym)
                    logger.info("TARGET hit: %s @ %.2f", sym, price)
                    continue
            else:
                if pos.stop_loss > 0 and price >= pos.stop_loss:
                    self.broker.close(sym, price)
                    self._scaled_out.discard(sym)
                    logger.info("SHORT STOP hit: %s @ %.2f", sym, price)
                    continue
                elif pos.take_profit > 0 and price <= pos.take_profit:
                    self.broker.close(sym, price)
                    self._scaled_out.discard(sym)
                    logger.info("SHORT TARGET hit: %s @ %.2f", sym, price)
                    continue

            atr = float(self._last_context.get(sym, {}).get("atr", 0.0))
            if atr <= 0 or price <= 0:
                continue
            entry = pos.avg_entry
            gain = (price - entry) / atr if long else (entry - price) / atr

            # 2) Breakeven lock + (optionally armed) trailing ratchet
            if self.cfg.breakeven_atr > 0 and gain >= self.cfg.breakeven_atr:
                be_stop = entry + 0.05 * atr if long else entry - 0.05 * atr
                applied = False
                if long and pos.stop_loss < be_stop:
                    pos.stop_loss = be_stop
                    applied = True
                elif not long and (pos.stop_loss <= 0 or pos.stop_loss > be_stop):
                    pos.stop_loss = be_stop
                    applied = True
                if applied:
                    logger.info("BREAKEVEN locked: %s stop -> %.2f", sym, be_stop)
            if self.cfg.trailing_stop_atr > 0 and (
                self.cfg.arm_trailing_atr <= 0 or gain >= self.cfg.arm_trailing_atr
            ):
                ns = (
                    price - self.cfg.trailing_stop_atr * atr
                    if long
                    else price + self.cfg.trailing_stop_atr * atr
                )
                if long and ns > pos.stop_loss:
                    pos.stop_loss = ns
                    logger.info("TRAIL raised: %s stop -> %.2f", sym, ns)
                elif not long and (pos.stop_loss <= 0 or ns < pos.stop_loss):
                    pos.stop_loss = ns
                    logger.info("TRAIL lowered: %s stop -> %.2f", sym, ns)

            # 3) One-time partial scale-out
            if self.cfg.partial_tp_atr > 0 and sym not in self._scaled_out and abs(pos.qty) > 1e-12:
                plevel = entry + self.cfg.partial_tp_atr * atr * (1.0 if long else -1.0)
                hit_partial = price >= plevel if long else price <= plevel
                if hit_partial:
                    frac = min(0.9, max(0.1, self.cfg.partial_fraction))
                    leg_qty = abs(pos.qty) * frac
                    if long:
                        self.broker.sell(sym, leg_qty, price)
                    else:
                        self.broker.buy_to_cover(sym, leg_qty, price)
                    self._scaled_out.add(sym)
                    if long and price > pos.stop_loss:
                        pos.stop_loss = price
                    elif not long and (pos.stop_loss <= 0 or price < pos.stop_loss):
                        pos.stop_loss = price
                    logger.info(
                        "SCALE-OUT %s %.4f @ %.2f (stop -> %.2f)",
                        sym,
                        leg_qty,
                        price,
                        pos.stop_loss,
                    )

    def step(self, continue_trading=None):
        """One iteration: fetch live data, act on signals, manage risk."""
        quotes = self._refresh_quotes()
        if continue_trading is not None and not continue_trading():
            return self.broker.equity(quotes)
        self._manage_exits(quotes)

        equity = self.broker.equity(quotes)
        today = datetime.now(timezone.utc).date()
        if today != self._risk_day:
            self.risk.reset_day(equity)
            self._risk_day = today
        for closed in self.broker.trades[self._risk_trades_recorded :]:
            self.risk.record_trade(closed.pnl)
        self._risk_trades_recorded = len(self.broker.trades)
        self.risk.day_start_equity = self.risk.day_start_equity or equity

        signals = self.scan(self.cfg.symbols)
        for sig in signals:
            if continue_trading is not None and not continue_trading():
                break
            price = quotes.get(sig.symbol, sig.entry_price)
            if price <= 0:
                continue
            ok, reason = self.risk.can_trade(equity, len(self.broker.positions))
            if not ok and sig.symbol not in self.broker.positions:
                logger.info("skip %s: %s", sig.symbol, reason)
                continue

            pos = self.broker.positions.get(sig.symbol)
            if sig.action == "BUY":
                if pos is None:
                    qty = self.risk.position_size(equity, price, sig.stop_loss)
                    if qty > 0 and self.broker.buy(sig.symbol, qty, price):
                        p = self.broker.positions[sig.symbol]
                        p.stop_loss = sig.stop_loss
                        p.take_profit = sig.take_profit
                        self._scaled_out.discard(sig.symbol)
                        logger.info(
                            "BUY  %s x%.4f @ %.2f (score %.1f)", sig.symbol, qty, price, sig.score
                        )
                elif pos.qty < 0:
                    self.broker.buy_to_cover(sig.symbol, -pos.qty, price)
                    logger.info("COVER %s @ %.2f (score %.1f)", sig.symbol, price, sig.score)
            elif sig.action == "SELL":
                if pos is None:
                    if self.cfg.allow_short:
                        qty = self.risk.position_size(equity, price, sig.stop_loss)
                        if qty > 0 and self.broker.sell_short(sig.symbol, qty, price):
                            p = self.broker.positions[sig.symbol]
                            p.stop_loss = sig.stop_loss
                            p.take_profit = sig.take_profit
                            self._scaled_out.discard(sig.symbol)
                            logger.info(
                                "SHORT %s x%.4f @ %.2f (score %.1f)",
                                sig.symbol,
                                qty,
                                price,
                                sig.score,
                            )
                elif pos.qty > 0:
                    self.broker.close(sig.symbol, price)
                    logger.info("SELL %s @ %.2f (score %.1f)", sig.symbol, price, sig.score)

        self.broker.save_state(quotes)
        self._log_vault(quotes, signals, equity)
        return equity

    def _log_vault(self, quotes: Dict[str, float], signals: List[Signal], equity: float):
        """Best-effort Supabase logging — never touches trading behaviour."""
        try:
            if not self._db.configured():
                return
            now = time.time()
            if now - self._last_equity_log > 60.0:
                self._last_equity_log = now
                self._db.log_equity_snapshot(
                    equity=equity,
                    cash=self.broker.cash,
                    open_positions=len(self.broker.positions),
                    mode=self.mode,
                )
            trades = self.broker.trades
            for t in trades[self._db_trades_logged :]:
                self._db.log_trade(
                    symbol=t.symbol,
                    side=t.side,
                    qty=t.qty,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    pnl=t.pnl,
                    pnl_pct=t.pnl_pct,
                    exit_reason=getattr(t, "exit_reason", "paper_close"),
                    mode=self.mode,
                    source="engine",
                )
            self._db_trades_logged = len(trades)
            for sig in signals[:5]:
                if sig.action in ("BUY", "SELL"):
                    self._db.log_signal(
                        symbol=sig.symbol,
                        action=sig.action,
                        score=sig.score,
                        confidence=sig.confidence,
                        entry_price=sig.entry_price,
                        stop_loss=sig.stop_loss,
                        take_profit=sig.take_profit,
                        timeframe=self.cfg.timeframe,
                    )
            # Regime-change events (throttled to every 5 minutes)
            if now - self._last_regime_check > 300.0:
                self._last_regime_check = now
                for sym in self.cfg.symbols:
                    try:
                        r: Regime = detect_regime(
                            self.provider.fetch_history(sym, self.cfg.period, self.cfg.timeframe)
                        )
                        prev = self._last_regimes.get(sym)
                        if prev is not None and prev != r.state:
                            self._db.log_regime_event(
                                symbol=sym,
                                from_state=prev,
                                to_state=r.state,
                                confidence=r.confidence,
                            )
                        self._last_regimes[sym] = r.state
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001 — vault must never crash the loop
            logger.debug("vault logging skipped: %s", exc)

    def run(self, interval: float = 60.0, once: bool = False):
        """Run the trading loop (paper or live)."""
        logger.info(
            "Starting %s loop (interval=%.0fs, %d symbols)",
            self.mode.upper(),
            interval,
            len(self.cfg.symbols),
        )
        while True:
            try:
                equity = self.step()
                logger.info(
                    "Equity: $%.2f | positions: %d | trades: %d",
                    equity,
                    len(self.broker.positions),
                    len(self.broker.trades),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("loop error: %s", exc)
            if once:
                break
            time.sleep(interval)
