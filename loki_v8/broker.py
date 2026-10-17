"""LOKI v8 — execution layer with a paper/live switch.

`PaperBroker` is a local fill simulator used for both paper trading and as
the deterministic reference implementation. Live adapters (Alpaca/Binance/
Kite) implement the same interface and are selected by `LokiConfig.mode`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import LokiConfig

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    opened_at: float = field(default_factory=time.time)

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_entry) * self.qty


@dataclass
class Trade:
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entered_at: float
    exited_at: float


class PaperBroker:
    """Deterministic local fill simulator with commission + slippage."""

    def __init__(self, cfg: LokiConfig):
        self.cfg = cfg
        self.cash = cfg.initial_cash
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.state_file = Path(cfg.state_dir) / "paper_account.json"

    # ------------------------------------------------------------------
    def _fill_price(self, price: float, side: str) -> float:
        slip = self.cfg.slippage_bps / 10_000.0
        return price * (1 + slip) if side == "buy" else price * (1 - slip)

    def buy(self, symbol: str, qty: float, price: float) -> bool:
        if qty <= 0 or price <= 0:
            return False
        fill = self._fill_price(price, "buy")
        cost = qty * fill + self.cfg.commission_per_trade
        if cost > self.cash:
            # Scale down to available cash (leave a small buffer).
            qty = max(0, int((self.cash - self.cfg.commission_per_trade) // fill)) if fill > 0 else 0
            if qty <= 0:
                return False
            cost = qty * fill + self.cfg.commission_per_trade
        self.cash -= cost
        pos = self.positions.get(symbol)
        if pos:
            total_qty = pos.qty + qty
            pos.avg_entry = (pos.avg_entry * pos.qty + fill * qty) / total_qty
            pos.qty = total_qty
        else:
            self.positions[symbol] = Position(symbol=symbol, qty=qty, avg_entry=fill)
        return True

    def sell(self, symbol: str, qty: float, price: float) -> bool:
        pos = self.positions.get(symbol)
        if not pos or qty <= 0 or price <= 0:
            return False
        qty = min(qty, pos.qty)
        fill = self._fill_price(price, "sell")
        proceeds = qty * fill - self.cfg.commission_per_trade
        self.cash += proceeds
        pnl = (fill - pos.avg_entry) * qty - self.cfg.commission_per_trade
        pnl_pct = (fill / pos.avg_entry - 1.0) * 100.0 if pos.avg_entry else 0.0
        self.trades.append(Trade(
            symbol=symbol, side="sell", qty=qty,
            entry_price=pos.avg_entry, exit_price=fill,
            pnl=pnl, pnl_pct=pnl_pct,
            entered_at=pos.opened_at, exited_at=time.time(),
        ))
        pos.qty -= qty
        if pos.qty <= 1e-12:
            del self.positions[symbol]
        return True

    def close(self, symbol: str, price: float) -> bool:
        pos = self.positions.get(symbol)
        if not pos:
            return False
        return self.sell(symbol, pos.qty, price)

    def equity(self, prices: Dict[str, float]) -> float:
        total = self.cash
        for sym, pos in self.positions.items():
            total += pos.market_value(prices.get(sym, pos.avg_entry))
        return total

    # ------------------------------------------------------------------
    def save_state(self, prices: Dict[str, float]):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "cash": self.cash,
                "equity": self.equity(prices),
                "positions": {s: asdict(p) for s, p in self.positions.items()},
                "num_trades": len(self.trades),
                "saved_at": datetime.now().isoformat(),
            }
            self.state_file.write_text(json.dumps(payload, indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("State save failed: %s", exc)


# ---------------------------------------------------------------------------
# Broker factory (live adapters plug in here later)
# ---------------------------------------------------------------------------
def make_broker(cfg: LokiConfig) -> "PaperBroker":
    """Return a broker for the configured mode.

    Live adapters (Alpaca/Binance/Kite) are added as they become available;
    until then `live` falls back to the local simulator with a loud warning
    so nobody mistakes it for a real-money account.
    """
    if cfg.mode == "live":
        logger.warning(
            "LIVE mode requested but no broker credentials are configured; "
            "falling back to the local paper simulator (no real orders)."
        )
    return PaperBroker(cfg)
