"""LOKI v8 — advanced position management & dynamic sizing.

This module handles everything after the signal is generated:
- Dynamic position sizing (volatility targeting, regime-aware, conviction)
- Portfolio-level risk (correlation, sector, factor exposure)
- Trade lifecycle management (scale-in, scale-out, breakeven, trailing)
- Risk budgeting across symbols
- Greeks-style risk decomposition for the portfolio

All decisions are causal (no lookahead) and auditable.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .risk import RiskManager
from .regime import regime_series, is_bullish, is_bearish, STATES

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "position_mgr"
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Position Sizing Models
# ---------------------------------------------------------------------------

@dataclass
class SizingParams:
    """Parameters for dynamic position sizing."""
    # Base risk per trade (percent of equity)
    base_risk_pct: float = 1.0

    # Volatility targeting
    target_vol_pct: float = 15.0  # annualized portfolio vol target
    vol_lookback: int = 60
    max_vol_scalar: float = 2.0
    min_vol_scalar: float = 0.3

    # Regime sizing
    regime_scalars: Dict[str, float] = field(default_factory=lambda: {
        "STRONG_BULL": 1.2,
        "BULL": 1.0,
        "RANGING": 0.6,
        "BEAR": 0.4,
        "CRISIS": 0.2,
    })

    # Conviction sizing (signal strength)
    conviction_enabled: bool = True
    conviction_min: float = 0.5
    conviction_max: float = 1.5

    # Correlation adjustment
    corr_adjustment: bool = True
    max_corr_exposure: float = 0.5  # max portfolio weight in correlated group

    # Kelly fraction (fraction of Kelly criterion to use)
    kelly_fraction: float = 0.25

    # Maximum position size (percent of equity)
    max_position_pct: float = 20.0


def compute_volatility_scalar(
    returns: pd.Series,
    target_vol: float,
    lookback: int,
    max_scalar: float,
    min_scalar: float,
) -> float:
    """Compute position scalar to target portfolio volatility."""
    if len(returns) < lookback:
        return 1.0

    recent_vol = returns.tail(lookback).std() * math.sqrt(252) * 100  # annualized %
    if recent_vol <= 0:
        return 1.0

    scalar = target_vol / recent_vol
    return float(np.clip(scalar, min_scalar, max_scalar))


def compute_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> float:
    """Kelly criterion position size (fraction of full Kelly)."""
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return fraction

    # Kelly % = (bp - q) / b where b = avg_win/avg_loss, p = win_rate, q = 1-p
    b = avg_win / avg_loss
    p = win_rate / 100.0
    q = 1.0 - p

    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(0, min(kelly, 1.0))  # clamp 0-1

    return kelly * fraction


def compute_dynamic_size(
    equity: float,
    price: float,
    stop: float,
    sizing: SizingParams,
    regime: str,
    recent_returns: Optional[pd.Series] = None,
    signal_strength: float = 1.0,  # 0-1, how strong is the signal
    win_rate: Optional[float] = None,
    avg_win: Optional[float] = None,
    avg_loss: Optional[float] = None,
    current_positions: Optional[Dict[str, float]] = None,
    corr_matrix: Optional[pd.DataFrame] = None,
) -> float:
    """Compute dynamic position size with all adjustments."""
    # Base size from risk per trade
    risk_amount = equity * sizing.base_risk_pct / 100.0
    per_unit_risk = abs(price - stop)
    if per_unit_risk <= 0:
        return 0.0

    base_qty = risk_amount / per_unit_risk

    # 1. Volatility targeting
    vol_scalar = 1.0
    if recent_returns is not None and len(recent_returns) >= 20:
        vol_scalar = compute_volatility_scalar(
            recent_returns, sizing.target_vol_pct, sizing.vol_lookback,
            sizing.max_vol_scalar, sizing.min_vol_scalar
        )

    # 2. Regime adjustment
    regime_scalar = sizing.regime_scalars.get(regime, 1.0)

    # 3. Conviction sizing
    conviction_scalar = 1.0
    if sizing.conviction_enabled:
        conviction_scalar = np.clip(
            sizing.conviction_min + (sizing.conviction_max - sizing.conviction_min) * signal_strength,
            sizing.conviction_min, sizing.conviction_max
        )

    # 4. Kelly criterion
    kelly_scalar = 1.0
    if win_rate is not None and avg_win is not None and avg_loss is not None:
        kelly_scalar = compute_kelly_fraction(win_rate, avg_win, avg_loss, sizing.kelly_fraction)

    # 5. Correlation adjustment
    corr_scalar = 1.0
    if sizing.corr_adjustment and current_positions and corr_matrix is not None:
        # Estimate portfolio correlation if we add this position
        # Simplified: reduce size if we're already heavy in correlated assets
        pass  # TODO: implement when we have portfolio context

    # Combined scalar
    total_scalar = vol_scalar * regime_scalar * conviction_scalar * kelly_scalar * corr_scalar

    # Apply
    qty = base_qty * total_scalar

    # Cap at max position %
    max_qty = equity * sizing.max_position_pct / 100.0 / price
    qty = min(qty, max_qty)

    return max(0.0, qty)


# ---------------------------------------------------------------------------
# Portfolio Risk Manager
# ---------------------------------------------------------------------------

@dataclass
class PortfolioRisk:
    """Portfolio-level risk metrics and limits."""
    positions: Dict[str, Dict[str, Any]]  # symbol -> {qty, price, stop, target, regime, factor_exposure}
    equity: float
    cash: float

    # Limits
    max_gross_exposure: float = 1.0      # max sum of |position| / equity
    max_net_exposure: float = 0.5        # max net long / equity
    max_single_position: float = 0.20    # max single position / equity
    max_sector_exposure: float = 0.30    # max sector / equity
    max_factor_exposure: Dict[str, float] = field(default_factory=lambda: {
        "trend": 0.5, "momentum": 0.4, "flow": 0.3, "squeeze": 0.3, "volatility": 0.3
    })

    def gross_exposure(self) -> float:
        return sum(abs(p["qty"] * p["price"]) for p in self.positions.values()) / self.equity

    def net_exposure(self) -> float:
        return sum(p["qty"] * p["price"] for p in self.positions.values()) / self.equity

    def check_limits(self, new_symbol: str, new_qty: float, new_price: float) -> Tuple[bool, str]:
        """Check if adding a position violates limits."""
        new_gross = self.gross_exposure() + abs(new_qty * new_price) / self.equity
        if new_gross > self.max_gross_exposure:
            return False, f"Gross exposure would be {new_gross:.1%} > {self.max_gross_exposure:.1%}"

        new_net = self.net_exposure() + (new_qty * new_price) / self.equity
        if abs(new_net) > self.max_net_exposure:
            return False, f"Net exposure would be {new_net:.1%} > {self.max_net_exposure:.1%}"

        position_pct = abs(new_qty * new_price) / self.equity
        if position_pct > self.max_single_position:
            return False, f"Position size {position_pct:.1%} > {self.max_single_position:.1%}"

        return True, "ok"

    def get_factor_exposure(self) -> Dict[str, float]:
        """Compute portfolio factor exposure."""
        exposure = {k: 0.0 for k in self.max_factor_exposure}
        for pos in self.positions.values():
            for factor, exp in pos.get("factor_exposure", {}).items():
                if factor in exposure:
                    exposure[factor] += exp * pos["qty"] * pos["price"] / self.equity
        return exposure


# ---------------------------------------------------------------------------
# Trade Lifecycle Manager
# ---------------------------------------------------------------------------

@dataclass
class TradePlan:
    """Complete trade plan from entry to exit."""
    symbol: str
    side: str  # "long" | "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    target_2: float = 0.0
    qty: float = 0.0

    # Scale-in/out
    scale_in_levels: List[Tuple[float, float]] = field(default_factory=list)  # [(price, fraction), ...]
    scale_out_levels: List[Tuple[float, float]] = field(default_factory=list)

    # Dynamic stops
    breakeven_trigger: float = 0.0     # ATR multiple to move to breakeven
    trailing_trigger: float = 0.0      # ATR multiple to start trailing
    trailing_distance: float = 0.0     # ATR distance for trailing

    # Time stop
    max_hold_bars: int = 30

    # Metadata
    regime: str = ""
    signal_strength: float = 0.0
    factor_values: Dict[str, float] = field(default_factory=dict)
    expected_hold_bars: int = 0

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "target_2": self.target_2,
            "qty": self.qty,
            "scale_in_levels": self.scale_in_levels,
            "scale_out_levels": self.scale_out_levels,
            "breakeven_trigger": self.breakeven_trigger,
            "trailing_trigger": self.trailing_trigger,
            "trailing_distance": self.trailing_distance,
            "max_hold_bars": self.max_hold_bars,
            "regime": self.regime,
            "signal_strength": self.signal_strength,
            "factor_values": self.factor_values,
            "expected_hold_bars": self.expected_hold_bars,
        }


class TradeManager:
    """Manages active trade lifecycle: entries, exits, adjustments."""

    def __init__(self, cfg: LokiConfig, risk_mgr: RiskManager):
        self.cfg = cfg
        self.risk = risk_mgr
        self.active_trades: Dict[str, TradePlan] = {}
        self.closed_trades: List[Dict] = []

    def create_plan(
        self,
        symbol: str,
        side: str,
        entry: float,
        atr: float,
        regime: str,
        signal_strength: float,
        factor_values: Dict[str, float],
    ) -> TradePlan:
        """Create a trade plan from signal."""
        cfg = self.cfg

        if side == "long":
            stop = entry - cfg.stop_loss_atr * atr
            target = entry + cfg.take_profit_atr * atr
            target2 = entry + cfg.take_profit_atr * 1.6 * atr
        else:
            stop = entry + cfg.stop_loss_atr * atr
            target = entry - cfg.take_profit_atr * atr
            target2 = entry - cfg.take_profit_atr * 1.6 * atr

        # Dynamic qty
        qty = self.risk.position_size(self.risk.day_start_equity or cfg.initial_cash, entry, stop)

        # Scale-out plan
        scale_out = []
        if cfg.partial_tp_atr > 0 and cfg.partial_tp_atr < cfg.take_profit_atr:
            partial_price = entry + cfg.partial_tp_atr * atr * (1 if side == "long" else -1)
            scale_out.append((partial_price, cfg.partial_fraction))

        plan = TradePlan(
            symbol=symbol,
            side=side,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            target_2=target2,
            qty=qty,
            scale_out_levels=scale_out,
            breakeven_trigger=cfg.breakeven_atr,
            trailing_trigger=cfg.arm_trailing_atr,
            trailing_distance=cfg.trailing_stop_atr,
            max_hold_bars=cfg.max_hold_bars,
            regime=regime,
            signal_strength=signal_strength,
            factor_values=factor_values,
        )

        return plan

    def update(self, symbol: str, current_price: float, current_atr: float, bars_held: int) -> Optional[Dict]:
        """Update trade, return exit signal if any."""
        if symbol not in self.active_trades:
            return None

        plan = self.active_trades[symbol]
        long = plan.side == "long"

        # Check exits in priority order
        # 1. Stop loss
        if long and current_price <= plan.stop_loss:
            return {"action": "exit", "reason": "stop_loss", "price": min(current_price, plan.stop_loss)}
        if not long and current_price >= plan.stop_loss:
            return {"action": "exit", "reason": "stop_loss", "price": max(current_price, plan.stop_loss)}

        # 2. Take profit
        if long and current_price >= plan.take_profit:
            return {"action": "exit", "reason": "take_profit", "price": max(current_price, plan.take_profit)}
        if not long and current_price <= plan.take_profit:
            return {"action": "exit", "reason": "take_profit", "price": min(current_price, plan.take_profit)}

        # 3. Scale out
        for level_price, fraction in plan.scale_out_levels:
            if long and current_price >= level_price:
                return {"action": "scale_out", "reason": "partial_tp", "price": level_price, "fraction": fraction}
            if not long and current_price <= level_price:
                return {"action": "scale_out", "reason": "partial_tp", "price": level_price, "fraction": fraction}

        # 4. Target 2 (runner)
        if plan.target_2 > 0:
            if long and current_price >= plan.target_2:
                return {"action": "exit", "reason": "target_2", "price": max(current_price, plan.target_2)}
            if not long and current_price <= plan.target_2:
                return {"action": "exit", "reason": "target_2", "price": min(current_price, plan.target_2)}

        # 5. Time stop
        if bars_held >= plan.max_hold_bars:
            return {"action": "exit", "reason": "time_stop", "price": current_price}

        # 6. Breakeven
        if plan.breakeven_trigger > 0:
            gain_atr = (current_price - plan.entry_price) / current_atr if long else (plan.entry_price - current_price) / current_atr
            if gain_atr >= plan.breakeven_trigger:
                new_stop = plan.entry_price + (0.05 * current_atr if long else -0.05 * current_atr)
                if long and new_stop > plan.stop_loss:
                    plan.stop_loss = new_stop
                    return {"action": "adjust", "reason": "breakeven", "new_stop": new_stop}
                elif not long and new_stop < plan.stop_loss:
                    plan.stop_loss = new_stop
                    return {"action": "adjust", "reason": "breakeven", "new_stop": new_stop}

        # 7. Trailing stop
        if plan.trailing_distance > 0 and plan.trailing_trigger > 0:
            gain_atr = (current_price - plan.entry_price) / current_atr if long else (plan.entry_price - current_price) / current_atr
            if gain_atr >= plan.trailing_trigger:
                new_stop = current_price - plan.trailing_distance * current_atr if long else current_price + plan.trailing_distance * current_atr
                if long and new_stop > plan.stop_loss:
                    plan.stop_loss = new_stop
                    return {"action": "adjust", "reason": "trailing", "new_stop": new_stop}
                elif not long and new_stop < plan.stop_loss:
                    plan.stop_loss = new_stop
                    return {"action": "adjust", "reason": "trailing", "new_stop": new_stop}

        return None

    def on_fill(self, symbol: str, plan: TradePlan) -> None:
        """Called when entry fill confirmed."""
        self.active_trades[symbol] = plan

    def on_exit(self, symbol: str, exit_price: float, reason: str, pnl: float) -> Dict:
        """Called when trade exits."""
        plan = self.active_trades.pop(symbol, None)
        if plan:
            trade_record = {
                **plan.to_dict(),
                "exit_price": exit_price,
                "exit_reason": reason,
                "pnl": pnl,
                "bars_held": 0,  # filled by caller
                "closed_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.closed_trades.append(trade_record)
            self.risk.record_trade(pnl)
            return trade_record
        return {}


# ---------------------------------------------------------------------------
# Portfolio Optimizer (mean-variance with regime constraints)
# ---------------------------------------------------------------------------

def optimize_portfolio_weights(
    expected_returns: Dict[str, float],
    cov_matrix: pd.DataFrame,
    current_positions: Dict[str, float],
    regime: str,
    max_weight: float = 0.20,
    min_weight: float = 0.0,
    target_vol: Optional[float] = None,
    risk_free: float = 0.02,
) -> Dict[str, float]:
    """Optimize portfolio weights using mean-variance with regime constraints."""
    symbols = list(expected_returns.keys())
    n = len(symbols)

    if n == 0:
        return {}

    mu = np.array([expected_returns[s] for s in symbols])
    cov = cov_matrix.loc[symbols, symbols].values

    # Current weights
    w_current = np.array([current_positions.get(s, 0.0) for s in symbols])
    w_current = w_current / w_current.sum() if w_current.sum() > 0 else np.ones(n) / n

    # Regime-based expected return adjustment
    regime_adj = {
        "STRONG_BULL": 1.1, "BULL": 1.0, "RANGING": 0.8, "BEAR": 0.6, "CRISIS": 0.4
    }
    adj = regime_adj.get(regime, 1.0)
    mu = mu * adj

    # Simple optimization: maximize Sharpe with constraints
    # Using analytical solution for unconstrained, then project to constraints
    inv_cov = np.linalg.pinv(cov)
    ones = np.ones(n)

    # Unconstrained max Sharpe
    A = ones @ inv_cov @ ones
    B = ones @ inv_cov @ mu
    C = mu @ inv_cov @ mu

    # Target return = risk_free + target_sharpe * sqrt(var)
    if target_vol:
        target_var = (target_vol / 100.0) ** 2
    else:
        target_var = 0.15 ** 2  # default 15% vol

    # Analytical solution
    w_opt = inv_cov @ (mu - risk_free * ones) / (ones @ inv_cov @ (mu - risk_free * ones))

    # Project to constraints
    w_opt = np.clip(w_opt, min_weight, max_weight)
    w_opt = w_opt / w_opt.sum() if w_opt.sum() > 0 else np.ones(n) / n

    # Scale to target vol
    port_vol = math.sqrt(w_opt @ cov @ w_opt)
    if target_vol and port_vol > 0:
        scale = (target_vol / 100.0) / port_vol
        w_opt = np.clip(w_opt * scale, 0, max_weight)
        w_opt = w_opt / w_opt.sum() if w_opt.sum() > 0 else w_opt

    return {s: float(w) for s, w in zip(symbols, w_opt)}


# ---------------------------------------------------------------------------
# Save/Load
# ---------------------------------------------------------------------------

def save_trade_plan(plan: TradePlan, path: Optional[Path] = None) -> Path:
    if path is None:
        path = STATE_DIR / f"trade_plan_{plan.symbol}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test position management")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--equity", type=float, default=100000)
    parser.add_argument("--price", type=float, default=50000)
    parser.add_argument("--stop", type=float, default=48000)
    parser.add_argument("--regime", default="BULL")
    parser.add_argument("--signal", type=float, default=0.8)
    args = parser.parse_args()

    cfg = LokiConfig(initial_cash=args.equity)
    sizing = SizingParams()
    risk = RiskManager(cfg)

    recent_rets = pd.Series(np.random.normal(0, 0.02, 100))  # dummy

    qty = compute_dynamic_size(
        equity=args.equity,
        price=args.price,
        stop=args.stop,
        sizing=sizing,
        regime=args.regime,
        recent_returns=recent_rets,
        signal_strength=args.signal,
        win_rate=55, avg_win=100, avg_loss=-80,
    )

    print(f"Dynamic size: {qty:.6f} units (${qty * args.price:.2f})")
    print(f"Risk amount: ${args.equity * sizing.base_risk_pct / 100:.2f}")
    print(f"Position %: {qty * args.price / args.equity * 100:.2f}%")


if __name__ == "__main__":
    main()