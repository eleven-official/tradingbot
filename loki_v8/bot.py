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
from typing import Dict, List, Optional

from .agents import LokiAgentPipeline
from .backtest import (BacktestResult, bars_per_year_for, monte_carlo,
                       portfolio_backtest, run_backtest, walk_forward)
from .broker import PaperBroker, make_broker
from .config import LokiConfig, default_config
from .data import get_provider, is_crypto
from .risk import RiskManager
from .strategy import EnsembleStrategy, Signal

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

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def switch_mode(self, mode: str):
        """Switch between 'paper' and 'live'. Live fails closed without keys."""
        if mode not in ("paper", "live"):
            raise ValueError(f"unknown mode: {mode}")
        self.mode = mode
        self.cfg.mode = mode
        self.broker = make_broker(self.cfg)
        logger.info("Switched to %s mode", mode.upper())

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def scan(self, symbols: Optional[List[str]] = None) -> List[Signal]:
        """Generate current signals for a list of symbols."""
        signals: List[Signal] = []
        for sym in (symbols or self.cfg.symbols):
            try:
                df = self.provider.fetch_history(sym, self.cfg.period, self.cfg.timeframe)
                sig = self.strategy.generate_signal(df, sym)
                if sig is not None:
                    signals.append(sig)
            except Exception as exc:  # noqa: BLE001
                logger.warning("scan failed for %s: %s", sym, exc)
        signals.sort(key=lambda s: -abs(s.score))
        return signals

    def agent_scan(self, symbols: Optional[List[str]] = None) -> Dict:
        """Run the full Director→Quant→Risk→Execution pipeline.

        Returns a structured decision trail per symbol (auditable JSON),
        and executes approved orders on the bot's own broker.
        """
        pipeline = LokiAgentPipeline(self.cfg, broker=self.broker)
        report = pipeline.run_universe(symbols, equity=self.broker.equity(self.last_quotes))
        return report

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------
    def backtest(self, symbol: str, period: Optional[str] = None,
                 interval: Optional[str] = None) -> BacktestResult:
        interval = interval or self.cfg.timeframe
        df = self.provider.fetch_history(symbol, period or self.cfg.period, interval)
        if df.empty:
            raise RuntimeError(f"no data for {symbol}")
        bpy = bars_per_year_for(interval, crypto=is_crypto(symbol))
        return run_backtest(df, self.cfg, self.strategy, symbol, bars_per_year=bpy)

    def backtest_all(self, symbols: Optional[List[str]] = None) -> Dict[str, BacktestResult]:
        out: Dict[str, BacktestResult] = {}
        for sym in (symbols or self.cfg.symbols):
            try:
                out[sym] = self.backtest(sym)
            except Exception as exc:  # noqa: BLE001
                logger.warning("backtest failed for %s: %s", sym, exc)
        return out

    def walk_forward(self, symbol: str, n_splits: int = 4,
                     period: str = "10y") -> List[BacktestResult]:
        df = self.provider.fetch_history(symbol, period, self.cfg.timeframe)
        return walk_forward(df, self.cfg, symbol, n_splits=n_splits)

    def portfolio_backtest(self, symbols: Optional[List[str]] = None,
                           period: str = "5y") -> BacktestResult:
        """Backtest an equal-weight portfolio of symbols with shared capital."""
        dfs: Dict[str, "pd.DataFrame"] = {}
        for sym in (symbols or self.cfg.symbols):
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
        """Close paper positions whose stop/target is hit (long or short)."""
        for sym in list(self.broker.positions.keys()):
            price = quotes.get(sym)
            if price is None:
                continue
            pos = self.broker.positions[sym]
            if pos.qty >= 0:  # long: stop below, target above
                if pos.stop_loss > 0 and price <= pos.stop_loss:
                    self.broker.close(sym, price)
                    logger.info("STOP hit: %s @ %.2f", sym, price)
                elif pos.take_profit > 0 and price >= pos.take_profit:
                    self.broker.close(sym, price)
                    logger.info("TARGET hit: %s @ %.2f", sym, price)
            else:  # short: stop above, target below
                if pos.stop_loss > 0 and price >= pos.stop_loss:
                    self.broker.close(sym, price)
                    logger.info("SHORT STOP hit: %s @ %.2f", sym, price)
                elif pos.take_profit > 0 and price <= pos.take_profit:
                    self.broker.close(sym, price)
                    logger.info("SHORT TARGET hit: %s @ %.2f", sym, price)

    def step(self):
        """One iteration: fetch live data, act on signals, manage risk."""
        quotes = self._refresh_quotes()
        self._manage_exits(quotes)

        equity = self.broker.equity(quotes)
        self.risk.day_start_equity = self.risk.day_start_equity or equity

        signals = self.scan(self.cfg.symbols)
        for sig in signals:
            price = quotes.get(sig.symbol, sig.entry_price)
            if price <= 0:
                continue
            ok, reason = self.risk.can_trade(equity, len(self.broker.positions))
            if not ok:
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
                        logger.info("BUY  %s x%.4f @ %.2f (score %.1f)",
                                    sig.symbol, qty, price, sig.score)
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
                            logger.info("SHORT %s x%.4f @ %.2f (score %.1f)",
                                        sig.symbol, qty, price, sig.score)
                elif pos.qty > 0:
                    self.broker.close(sig.symbol, price)
                    logger.info("SELL %s @ %.2f (score %.1f)", sig.symbol, price, sig.score)

        self.broker.save_state(quotes)
        return equity

    def run(self, interval: float = 60.0, once: bool = False):
        """Run the trading loop (paper or live)."""
        logger.info("Starting %s loop (interval=%.0fs, %d symbols)",
                    self.mode.upper(), interval, len(self.cfg.symbols))
        while True:
            try:
                equity = self.step()
                logger.info("Equity: $%.2f | positions: %d | trades: %d",
                            equity, len(self.broker.positions), len(self.broker.trades))
            except Exception as exc:  # noqa: BLE001
                logger.exception("loop error: %s", exc)
            if once:
                break
            time.sleep(interval)
