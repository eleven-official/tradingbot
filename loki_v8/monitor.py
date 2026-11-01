"""LOKI v8 — real-time signal monitor & alerting.

Runs the Director→Quant→Risk→Execution pipeline on a schedule,
emits signals to stdout/JSON/Slack/Discord/Telegram, and maintains
a live dashboard state file that the web UI can poll.

Modes:
- `daemon`: run continuously, poll at intervals
- `once`: run one cycle and exit (for cron)
- `backtest`: replay historical signals for verification

The monitor is stateless between runs (except for position tracking
via the PaperBroker), so it can be horizontally scaled.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from .agents import LokiAgentPipeline
from .broker import PaperBroker, make_broker
from .config import LokiConfig
from .data import get_provider
from .position_mgr import TradeManager, TradePlan, SizingParams, compute_dynamic_size

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "monitor"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MonitorConfig:
    """Configuration for the signal monitor."""
    symbols: List[str] = field(default_factory=lambda: [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
        "ADA-USD", "DOGE-USD", "LINK-USD", "AVAX-USD", "LTC-USD",
    ])
    interval_seconds: int = 300  # 5 minutes
    period: str = "3y"
    timeframe: str = "1d"
    capital: float = 100_000.0
    state_dir: str = "state/crypto"
    log_level: str = "INFO"

    # Alerting
    alert_on_signal: bool = True
    alert_on_fill: bool = True
    alert_on_exit: bool = True
    alert_on_risk: bool = True
    webhook_url: Optional[str] = None  # Slack/Discord/Telegram webhook

    # Position management
    use_dynamic_sizing: bool = True
    max_positions: int = 5


@dataclass
class SignalEvent:
    """A signal event from the monitor."""
    timestamp: str
    symbol: str
    regime: str
    posture: str
    action: str  # BUY, SELL, HOLD, SCALE_OUT, EXIT
    score: float
    confidence: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    qty: float
    reason: str
    executed: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "regime": self.regime,
            "posture": self.posture,
            "action": self.action,
            "score": self.score,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "qty": self.qty,
            "reason": self.reason,
            "executed": self.executed,
            "metadata": self.metadata,
        }


class SignalMonitor:
    """Real-time signal monitor with alerting and state persistence."""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.cfg = LokiConfig(
            period=config.period,
            timeframe=config.timeframe,
            initial_cash=config.capital,
            state_dir=config.state_dir,
        )
        self.broker = make_broker(self.cfg)
        self.provider = get_provider()
        self.pipeline = LokiAgentPipeline(self.cfg, broker=self.broker)
        self.trade_mgr = TradeManager(self.cfg, self.broker.risk if hasattr(self.broker, 'risk') else None)

        # Dynamic sizing
        self.sizing = SizingParams()

        # State
        self.running = False
        self.cycle_count = 0
        self.signals_history: List[SignalEvent] = []
        self.last_prices: Dict[str, float] = {}

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False

    def run_once(self) -> List[SignalEvent]:
        """Run one monitoring cycle."""
        events = []
        quotes = self.provider.get_quotes(self.config.symbols)

        for symbol in self.config.symbols:
            price = quotes.get(symbol, 0.0)
            if price <= 0:
                try:
                    price = float(self.provider.get_latest_price(symbol) or 0.0)
                except Exception:
                    price = 0.0
            if price <= 0:
                continue

            self.last_prices[symbol] = price

            # Get pipeline decision
            equity = self.broker.equity(quotes)
            open_positions = len(self.broker.positions)

            trail = self.pipeline.run_symbol(
                symbol, equity, open_positions, price, execute=False
            )

            # Extract decisions
            director = next((t for t in trail if t.get("agent") == "director"), {})
            quant = next((t for t in trail if t.get("agent") == "quant"), {})
            risk = next((t for t in trail if t.get("agent") == "risk"), {})
            execution = next((t for t in trail if t.get("agent") == "execution"), {})

            action = quant.get("action", "HOLD")
            score = quant.get("score", 0.0)
            confidence = quant.get("confidence", 0.0)
            regime = director.get("regime", "UNKNOWN")
            posture = director.get("posture", "flat")

            # Dynamic sizing
            qty = 0.0
            if action == "BUY" and risk.get("approved"):
                entry = price
                stop = quant.get("stop", 0.0)
                if stop > 0:
                    # Get recent returns for vol targeting
                    try:
                        history = self.provider.fetch_history(symbol, "60d", "1d")
                        if history is not None and len(history) > 30:
                            rets = history["close"].pct_change().dropna()
                        else:
                            rets = None
                    except Exception:
                        rets = None

                    qty = compute_dynamic_size(
                        equity=equity,
                        price=entry,
                        stop=stop,
                        sizing=self.sizing,
                        regime=regime,
                        recent_returns=rets,
                        signal_strength=min(1.0, abs(score) / 50.0),
                    )

            event = SignalEvent(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                symbol=symbol,
                regime=regime,
                posture=posture,
                action=action,
                score=round(score, 1),
                confidence=round(confidence, 1),
                entry_price=quant.get("entry") if action == "BUY" else None,
                stop_loss=quant.get("stop") if action == "BUY" else None,
                take_profit=quant.get("target") if action == "BUY" else None,
                qty=round(qty, 8),
                reason=risk.get("reason", "") or execution.get("reason", ""),
                executed=False,
                metadata={
                    "director_thesis": director.get("thesis", ""),
                    "squeeze_status": quant.get("squeeze_status", ""),
                    "reasons": quant.get("reasons", []),
                    "risk_reward": quant.get("risk_reward", 0),
                }
            )

            events.append(event)
            self.signals_history.append(event)

            # Alert
            if self.config.alert_on_signal and action in ("BUY", "SELL"):
                self._alert(event)

        # Save state
        self._save_state()
        return events

    def run_daemon(self) -> None:
        """Run continuous monitoring loop."""
        self.running = True
        logger.info("Starting signal monitor for %d symbols every %ds",
                    len(self.config.symbols), self.config.interval_seconds)

        while self.running:
            self.cycle_count += 1
            start = time.time()

            try:
                events = self.run_once()
                if events:
                    logger.info("Cycle %d: %d signals generated", self.cycle_count, len(events))
            except Exception as e:
                logger.error("Cycle %d failed: %s", self.cycle_count, e)

            # Sleep until next interval
            elapsed = time.time() - start
            sleep_time = max(0, self.config.interval_seconds - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info("Monitor stopped after %d cycles", self.cycle_count)

    def _alert(self, event: SignalEvent) -> None:
        """Send alert via webhook."""
        if not self.config.webhook_url:
            # Log to stdout as fallback
            print(f"🚨 SIGNAL: {event.symbol} {event.action} @ {event.entry_price} "
                  f"(score={event.score}, conf={event.confidence}, regime={event.regime})")
            return

        # TODO: Implement webhook posting (Slack/Discord/Telegram)
        # For now just log
        logger.info("ALERT: %s %s", event.symbol, event.action)

    def _save_state(self) -> None:
        """Persist monitor state for dashboard."""
        state = {
            "cycle": self.cycle_count,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "config": {
                "symbols": self.config.symbols,
                "interval_seconds": self.config.interval_seconds,
                "capital": self.config.capital,
            },
            "broker": {
                "cash": round(self.broker.cash, 2),
                "equity": round(self.broker.equity(self.last_prices), 2),
                "positions": {
                    sym: {
                        "qty": round(pos.qty, 8),
                        "avg_entry": round(pos.avg_entry, 6),
                        "stop_loss": round(pos.stop_loss, 6),
                        "take_profit": round(pos.take_profit, 6),
                        "unrealized_pnl": round(pos.unrealized_pnl(self.last_prices.get(sym, pos.avg_entry)), 2),
                    }
                    for sym, pos in self.broker.positions.items()
                },
            },
            "recent_signals": [e.to_dict() for e in self.signals_history[-50:]],
        }

        path = STATE_DIR / "monitor_state.json"
        path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    def load_state(self) -> bool:
        """Load monitor state."""
        path = STATE_DIR / "monitor_state.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.cycle_count = data.get("cycle", 0)
            # Broker state is loaded automatically via PaperBroker
            logger.info("Loaded monitor state: cycle %d", self.cycle_count)
            return True
        except Exception as e:
            logger.warning("Failed to load state: %s", e)
            return False


# ---------------------------------------------------------------------------
# Historical Signal Replay (for verification)
# ---------------------------------------------------------------------------

def replay_signals(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "3y",
    timeframe: str = "1d",
    cfg: Optional[LokiConfig] = None,
) -> List[SignalEvent]:
    """Replay historical signals for verification."""
    provider = get_provider()
    history = provider.fetch_history(symbol, period, timeframe)
    if history is None or history.empty:
        return []

    # Filter date range
    history = history[(history.index >= start_date) & (history.index <= end_date)]

    cfg = cfg or LokiConfig(period=period, timeframe=timeframe)
    broker = PaperBroker(cfg)
    pipeline = LokiAgentPipeline(cfg, broker=broker)

    events = []
    for i in range(max(cfg.lookback_bars, 60) + 1, len(history)):
        bar_time = history.index[i]
        price = float(history["open"].iloc[i])  # Next bar open

        # Run on data up to previous bar
        df = history.iloc[:i].copy()

        # Mock quotes
        quotes = {symbol: price}

        trail = pipeline.run_symbol(symbol, cfg.initial_cash, 0, price, execute=False)

        quant = next((t for t in trail if t.get("agent") == "quant"), {})
        director = next((t for t in trail if t.get("agent") == "director"), {})
        risk = next((t for t in trail if t.get("agent") == "risk"), {})

        action = quant.get("action", "HOLD")
        if action in ("BUY", "SELL"):
            events.append(SignalEvent(
                timestamp=str(bar_time),
                symbol=symbol,
                regime=director.get("regime", ""),
                posture=director.get("posture", ""),
                action=action,
                score=quant.get("score", 0),
                confidence=quant.get("confidence", 0),
                entry_price=quant.get("entry"),
                stop_loss=quant.get("stop"),
                take_profit=quant.get("target"),
                qty=0.0,  # Not executed
                reason=risk.get("reason", ""),
                executed=False,
            ))

    return events


# ---------------------------------------------------------------------------
# Dashboard Data Provider
# ---------------------------------------------------------------------------

def get_dashboard_data() -> Dict[str, Any]:
    """Get current dashboard state (for web UI polling)."""
    path = STATE_DIR / "monitor_state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"error": "Monitor not running", "updated_at": ""}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LOKI v8 Signal Monitor")
    parser.add_argument("--mode", choices=["daemon", "once", "replay"], default="once")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--period", default="3y")
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--webhook", default="", help="Alert webhook URL")
    parser.add_argument("--start", help="Replay start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Replay end date (YYYY-MM-DD)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    config = MonitorConfig(
        symbols=symbols or config.symbols if 'config' in dir() else [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
            "ADA-USD", "DOGE-USD", "LINK-USD", "AVAX-USD", "LTC-USD",
        ],
        interval_seconds=args.interval,
        period=args.period,
        capital=args.capital,
        webhook_url=args.webhook or None,
    )

    monitor = SignalMonitor(config)
    monitor.load_state()

    if args.mode == "daemon":
        monitor.run_daemon()
    elif args.mode == "once":
        events = monitor.run_once()
        for e in events:
            if e.action != "HOLD":
                print(f"{e.timestamp} | {e.symbol:>10} | {e.action:>8} | "
                      f"score={e.score:>6.1f} | conf={e.confidence:>5.1f} | "
                      f"regime={e.regime:>12} | {e.reason}")
    elif args.mode == "replay":
        if not args.start or not args.end:
            print("--start and --end required for replay")
            return
        for symbol in config.symbols:
            print(f"\n=== {symbol} ===")
            events = replay_signals(symbol, args.start, args.end, args.period)
            for e in events:
                print(f"{e.timestamp} | {e.action:>4} | score={e.score:>6.1f} | "
                      f"regime={e.regime:>12} | entry={e.entry_price} | "
                      f"stop={e.stop_loss} | target={e.take_profit}")


if __name__ == "__main__":
    main()