"""LOKI v8 — multi-agent orchestration layer (AutoHedge-inspired).

    Director ──► Quant ──► Risk ──► Execution

Each agent emits a structured JSON decision so the whole chain is auditable.
The pipeline is deterministic (no LLM key required); an LLM reasoning hook can
be slotted into the Director later without changing the interface.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .broker import make_broker
from .config import LokiConfig
from .data import get_provider
from .regime import Regime, detect_regime, is_bearish, is_bullish
from .risk import RiskManager
from .strategy import EnsembleStrategy, Signal

logger = logging.getLogger(__name__)


def _json(obj) -> str:
    return json.dumps(obj, default=str, indent=2)


class DirectorAgent:
    """Sets the market posture (long/flat/short) and a one-line thesis."""

    def __init__(self, cfg: LokiConfig):
        self.cfg = cfg

    def run(self, symbol: str, regime: Regime) -> Dict:
        state = regime.state
        if is_bullish(state):
            posture = "long"
            strength = "strong" if state == "STRONG_BULL" else "developing"
            thesis = (
                f"{symbol}: {strength} uptrend "
                f"(trend_score={regime.trend_score:+.0f}, ADX={regime.adx:.0f})"
            )
        elif is_bearish(state):
            posture = "short" if (self.cfg.allow_short and state == "BEAR") else "flat"
            if state == "CRISIS":
                thesis = f"{symbol}: CRISIS regime — high volatility, capital preserved"
            else:
                thesis = (
                    f"{symbol}: downtrend — {'shorting' if posture == 'short' else 'no new longs'}"
                )
        else:
            posture = "long"  # ranging: trade longs on strong signals, tighter size
            thesis = f"{symbol}: ranging market — trade only high-confidence longs"

        return {
            "symbol": symbol,
            "posture": posture,
            "thesis": thesis,
            "regime": regime.state,
            "confidence": round(regime.confidence, 1),
        }


class QuantAgent:
    """Technical/statistical analysis — wraps the ensemble strategy."""

    def __init__(self, cfg: LokiConfig):
        self.strategy = EnsembleStrategy(cfg)

    def run(self, symbol: str, df) -> Optional[Dict]:
        sig = self.strategy.generate_signal(df, symbol)
        if sig is None:
            return None
        return {
            "symbol": symbol,
            "action": sig.action,
            "score": round(sig.score, 1),
            "confidence": round(sig.confidence, 1),
            "entry": sig.entry_price,
            "stop": sig.stop_loss,
            "target": sig.take_profit,
            "target_2": sig.target_2,
            "risk_reward": sig.risk_reward,
            "squeeze_status": sig.squeeze_status,
            "reasons": sig.reasons,
        }


class RiskAgent:
    """Position sizing + approval, reconciling Director posture with the signal."""

    def __init__(self, cfg: LokiConfig):
        self.cfg = cfg
        self.risk = RiskManager(cfg)

    def run(
        self, posture: str, signal: Optional[Dict], equity: float, open_positions: int, price: float
    ) -> Dict:
        if signal is None:
            return {"approved": False, "reason": "no_signal"}

        # Posture/signal agreement
        if posture == "flat" and signal["action"] == "BUY":
            return {"approved": False, "reason": "director_posture_flat"}
        if posture == "short" and signal["action"] == "BUY":
            return {"approved": False, "reason": "director_posture_short"}
        if posture == "long" and signal["action"] == "SELL":
            # In long posture, SELL is treated as an exit, not a short entry.
            pass

        ok, reason = self.risk.can_trade(equity, open_positions)
        if not ok:
            return {"approved": False, "reason": reason}

        if signal["action"] == "BUY":
            qty = self.risk.position_size(equity, price, signal["stop"])
            # Tighter size in ranging markets
            if posture == "long" and signal.get("regime") == "RANGING":
                qty *= 0.5
            return {
                "approved": qty > 0,
                "reason": "ok",
                "qty": qty,
                "action": "BUY",
                "stop": signal["stop"],
                "target": signal["target"],
            }
        elif signal["action"] == "SELL":
            return {"approved": True, "reason": "ok", "action": "SELL", "qty": 0.0}
        return {"approved": False, "reason": "hold"}


class ExecutionAgent:
    """Order generation + execution against the broker."""

    def __init__(self, cfg: LokiConfig, broker=None):
        self.broker = broker or make_broker(cfg)

    def run(self, symbol: str, decision: Dict, price: float) -> Dict:
        if not decision.get("approved"):
            return {"executed": False, "reason": decision.get("reason")}
        if decision.get("action") == "BUY":
            if symbol in self.broker.positions:
                return {"executed": False, "reason": "position_already_open"}
            qty = decision["qty"]
            ok = self.broker.buy(symbol, qty, price)
            if ok and symbol in self.broker.positions:
                pos = self.broker.positions[symbol]
                pos.stop_loss = decision["stop"]
                pos.take_profit = decision["target"]
            return {"executed": ok, "action": "BUY", "qty": qty, "price": price}
        elif decision.get("action") == "SELL":
            ok = self.broker.close(symbol, price)
            return {"executed": ok, "action": "SELL", "price": price}
        return {"executed": False, "reason": "unknown_action"}


class LokiAgentPipeline:
    """Runs the full Director→Quant→Risk→Execution chain over a symbol."""

    def __init__(self, cfg: LokiConfig, broker=None):
        self.cfg = cfg
        self.provider = get_provider()
        self.director = DirectorAgent(cfg)
        self.quant = QuantAgent(cfg)
        self.risk = RiskAgent(cfg)
        self.executor = ExecutionAgent(cfg, broker)

    def run_symbol(
        self,
        symbol: str,
        equity: float,
        open_positions: int,
        price: float,
        *,
        execute: bool = False,
    ) -> List[Dict]:
        """Run the pipeline and return the ordered decision trail."""
        trail: List[Dict] = []
        try:
            df = self.provider.fetch_history(symbol, self.cfg.period, self.cfg.timeframe)
            regime = detect_regime(df)
        except Exception as exc:  # noqa: BLE001
            return [{"agent": "director", "error": str(exc)}]

        d = self.director.run(symbol, regime)
        trail.append({"agent": "director", **d})

        sig = self.quant.run(symbol, df)
        if sig:
            sig["regime"] = regime.state
        trail.append({"agent": "quant", **(sig or {"action": "HOLD"})})

        r = self.risk.run(d["posture"], sig, equity, open_positions, price)
        trail.append({"agent": "risk", **r})

        e = (
            self.executor.run(symbol, r, price)
            if execute
            else {"executed": False, "reason": "review_only", "approved": r.get("approved", False)}
        )
        trail.append({"agent": "execution", **e})

        return trail

    def run_universe(
        self,
        symbols: Optional[List[str]] = None,
        equity: Optional[float] = None,
        *,
        execute: bool = False,
    ) -> Dict:
        """Run the pipeline across a symbol list and return a full report."""
        syms = symbols or self.cfg.symbols
        quotes = self.provider.get_quotes(syms)
        equity = equity or self.cfg.initial_cash
        open_positions = len(self.executor.broker.positions)

        report = {"trails": {}, "signals": 0, "executed": 0}
        for sym in syms:
            price = quotes.get(sym, 0.0)
            trail = self.run_symbol(sym, equity, open_positions, price, execute=execute)
            report["trails"][sym] = trail
            if any(t.get("agent") == "quant" and t.get("action") in ("BUY", "SELL") for t in trail):
                report["signals"] += 1
            if any(t.get("agent") == "execution" and t.get("executed") for t in trail):
                report["executed"] += 1
                open_positions = len(self.executor.broker.positions)
                equity = self.executor.broker.equity(quotes)
        return report
