"""LOKI v8 — risk management: position sizing and portfolio guards."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .config import LokiConfig


@dataclass
class RiskManager:
    cfg: LokiConfig
    day_start_equity: float = 0.0
    _consecutive_losses: int = 0
    _last_trade_pnl: Optional[float] = None

    def __post_init__(self):
        if self.day_start_equity == 0.0:
            self.day_start_equity = self.cfg.initial_cash

    # ------------------------------------------------------------------
    def position_size(self, equity: float, price: float, stop: float) -> float:
        """Return the number of units to trade so that a stop-out loses only
        `risk_per_trade_pct`% of equity."""
        if price <= 0 or stop <= 0 or abs(price - stop) <= 0:
            return 0.0
        risk_amount = equity * self.cfg.risk_per_trade_pct / 100.0
        per_unit_risk = abs(price - stop)
        return max(0.0, risk_amount / per_unit_risk)

    def daily_loss_hit(self, equity: float) -> bool:
        if self.day_start_equity <= 0:
            return False
        pct = (equity / self.day_start_equity - 1.0) * 100.0
        return pct <= -self.cfg.max_daily_loss_pct

    def too_many_losses(self) -> bool:
        return self._consecutive_losses >= self.cfg.max_consecutive_losses

    def record_trade(self, pnl: float):
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._last_trade_pnl = pnl

    def can_trade(self, equity: float, open_positions: int) -> tuple[bool, str]:
        """Gate a new entry behind risk limits. Returns (allowed, reason)."""
        if open_positions >= self.cfg.max_open_positions:
            return False, "max_open_positions"
        if self.daily_loss_hit(equity):
            return False, "daily_loss_limit"
        if self.too_many_losses():
            return False, "consecutive_losses"
        return True, "ok"

    def reset_day(self, equity: float):
        self.day_start_equity = equity
        self._consecutive_losses = 0
