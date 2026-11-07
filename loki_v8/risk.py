"""LOKI v8 — risk management: position sizing and portfolio guards."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

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


def realized_vol(close: pd.Series, lookback: int, bars_per_year: int) -> pd.Series:
    """Causal annualised volatility of log returns (fraction, e.g. 0.18)."""
    rets = np.log(close.astype(float)).diff()
    return rets.rolling(lookback, min_periods=max(5, lookback // 2)).std() * math.sqrt(bars_per_year)


def entry_quantity(
    cfg: LokiConfig, equity: float, cash: float, price: float, stop: float, ann_vol: float
) -> float:
    """Units to buy for a new long, before conviction/regime multipliers.

    ``vol_target`` sizes exposure to target_vol / realised vol (capped);
    ``risk`` sizes so a stop-out costs risk_per_trade_pct of equity.
    Vol-target sizes never exceed max_exposure_pct of equity.
    """
    if price <= 0 or equity <= 0:
        return 0.0
    if cfg.sizing_mode != "vol_target":
        # Classic mode is left exactly as verified: the caller decides what
        # happens when the risk-based size is larger than the cash on hand.
        return RiskManager(cfg).position_size(equity, price, stop)
    if not (ann_vol > 0 and math.isfinite(ann_vol)):
        return 0.0
    exposure = min(max(0.0, cfg.max_exposure_pct) / 100.0, (cfg.target_vol_pct / 100.0) / ann_vol)
    return max(0.0, equity * exposure / price)
