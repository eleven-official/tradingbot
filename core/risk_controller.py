"""
Risk management and position sizing controller.
Extracted from trading_bot.py for better code organization.
"""
import logging
import math
from typing import Optional, Dict, Any


class RiskController:
    """Manages risk parameters, position sizing, and risk limit enforcement."""
    
    def __init__(self, config):
        self.config = config
        self.risk_config = config.get('risk_management', {})
        self.trading_flags = config.get('trading_flags', {})
        
        # Risk parameters
        self.base_risk_per_trade = self.trading_flags.get('risk_per_trade_percent', 1.0)
        self.stop_loss_percent = self.trading_flags.get('stop_loss_percent', 15.0)
        self.max_trades_per_day = self.trading_flags.get('max_trades_per_day', 5)
        
        # Professional risk controls
        self._trade_size_multiplier = 1.0  # reduced after losses, restored on wins
        
        # Risk tier configuration
        self.risk_tiers = config.get('risk_tiers', [])
    
    def get_risk_per_trade(self, capital: float) -> float:
        """
        Calculate risk per trade based on capital tiers if configured,
        otherwise use base risk percentage.
        """
        if self.risk_tiers:
            for tier in self.risk_tiers:
                max_cap = tier.get('max_capital')
                if max_cap is None or capital <= max_cap:
                    return tier.get('risk_pct', self.base_risk_per_trade)
        
        return self.base_risk_per_trade
    
    def calculate_position_size(self, capital: float, option_price: float) -> int:
        """
        Calculate position size based on risk per trade and option price.
        Returns the number of lots to trade.
        """
        risk_amount = capital * (self.get_risk_per_trade(capital) / 100)
        risk_per_lot = option_price * (self.stop_loss_percent / 100)
        
        if risk_per_lot <= 0:
            logging.warning(f"Invalid risk per lot: {risk_per_lot}, using minimum size")
            return 1
        
        lots = int(risk_amount / risk_per_lot)
        # Apply size multiplier (reduced after losses)
        lots = int(lots * self._trade_size_multiplier)
        
        return max(1, lots)  # At least 1 lot
    
    def reduce_size_after_loss(self):
        """Reduce position size after a loss."""
        self._trade_size_multiplier = max(0.5, self._trade_size_multiplier * 0.8)
        logging.info(f"Reduced position size multiplier to {self._trade_size_multiplier:.2f}")
    
    def restore_size_after_win(self):
        """Restore position size after a win."""
        self._trade_size_multiplier = min(1.0, self._trade_size_multiplier * 1.2)
        logging.info(f"Restored position size multiplier to {self._trade_size_multiplier:.2f}")
    
    def validate_risk_coherence(self, capital: float):
        """
        Validate that risk parameters are coherent.
        Warn if risk_per_trade > max_daily_loss / 2.
        """
        max_daily_loss = self.risk_config.get('max_daily_loss_percent', 2.5)
        risk_per_trade = self.get_risk_per_trade(capital)
        
        if risk_per_trade > max_daily_loss / 2:
            logging.warning(
                f"[RiskCoherence] risk_per_trade ({risk_per_trade}%) > max_daily_loss/2 "
                f"({max_daily_loss/2:.1f}%). A single stop-out could exceed daily limit."
            )
    
    def should_enable_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is enabled."""
        return self.risk_config.get('enable_daily_loss_limit', True)
    
    def should_enable_consecutive_loss_limit(self) -> bool:
        """Check if consecutive loss limit is enabled."""
        return self.risk_config.get('enable_consecutive_loss_limit', True)
    
    def should_enable_weekly_loss_limit(self) -> bool:
        """Check if weekly loss limit is enabled."""
        return self.risk_config.get('enable_weekly_loss_limit', False)
    
    def get_max_daily_loss_percent(self) -> float:
        """Get maximum daily loss percentage."""
        return self.risk_config.get('max_daily_loss_percent', 2.5)
    
    def get_max_consecutive_losses(self) -> int:
        """Get maximum consecutive losses before stopping."""
        return self.risk_config.get('max_consecutive_losses', 3)
    
    def get_max_weekly_loss_percent(self) -> float:
        """Get maximum weekly loss percentage."""
        return self.risk_config.get('max_weekly_loss_percent', 5.0)
    
    def should_enable_volatility_adjustment(self) -> bool:
        """Check if volatility-based risk adjustment is enabled."""
        return self.risk_config.get('enable_volatility_adjustment', True)
    
    def get_high_vix_threshold(self) -> float:
        """Get VIX threshold for high volatility regime."""
        return self.risk_config.get('high_vix_threshold', 22.0)
    
    def get_high_vix_risk_reduction(self) -> float:
        """Get risk reduction factor for high VIX."""
        return self.risk_config.get('high_vix_risk_reduction_factor', 0.5)
    
    def adjust_for_volatility(self, vix: float, base_risk: float) -> float:
        """Adjust risk based on VIX if volatility adjustment is enabled."""
        if not self.should_enable_volatility_adjustment():
            return base_risk
        
        if vix >= self.get_high_vix_threshold():
            adjusted_risk = base_risk * self.get_high_vix_risk_reduction()
            logging.info(f"High VIX ({vix:.1f}) - reducing risk from {base_risk:.1f}% to {adjusted_risk:.1f}%")
            return adjusted_risk
        
        return base_risk
    
    def can_take_trade(self, trades_today: int, state_manager) -> tuple[bool, str]:
        """
        Check if a new trade can be taken based on all risk limits.
        Returns (can_trade, reason).
        """
        # Check max trades per day
        if trades_today >= self.max_trades_per_day:
            return False, f"Max trades per day ({self.max_trades_per_day}) reached"
        
        # Check daily loss limit
        if self.should_enable_daily_loss_limit():
            if state_manager.check_daily_loss_limit(
                self.get_max_daily_loss_percent(), 
                state_manager.starting_capital or 100000
            ):
                return False, f"Daily loss limit ({self.get_max_daily_loss_percent()}%) reached"
        
        # Check consecutive loss limit
        if self.should_enable_consecutive_loss_limit():
            if state_manager.check_consecutive_loss_limit(self.get_max_consecutive_losses()):
                return False, f"Consecutive loss limit ({self.get_max_consecutive_losses()}) reached"
        
        # Check weekly loss limit
        if self.should_enable_weekly_loss_limit():
            if state_manager.check_weekly_loss_limit(
                self.get_max_weekly_loss_percent(),
                state_manager.starting_capital or 100000
            ):
                return False, f"Weekly loss limit ({self.get_max_weekly_loss_percent()}%) reached"
        
        return True, "All risk checks passed"

    def validate_order(
        self,
        capital: float,
        price: float,
        quantity: float,
        gross_exposure: float = 0.0,
        open_positions: int = 0,
        symbol_exposure: float = 0.0,
    ) -> tuple[bool, str]:
        """Reject an entry that exceeds explicit portfolio-level paper limits.

        A signal is not a risk model.  This check keeps a malformed or overly
        optimistic alert from consuming a paper account even when its quantity
        is below the TradingView per-alert maximum.
        """
        execution = self.config.get('execution', {}) or {}
        try:
            capital = float(capital)
            price = float(price)
            quantity = float(quantity)
            gross_exposure = float(gross_exposure)
            open_positions = int(open_positions)
            symbol_exposure = float(symbol_exposure)
        except (TypeError, ValueError):
            return False, "Order risk inputs must be numeric"
        if not all(math.isfinite(value) for value in (capital, price, quantity, gross_exposure, symbol_exposure)):
            return False, "Order risk inputs must be finite"
        if capital <= 0 or price <= 0 or quantity <= 0 or gross_exposure < 0 or symbol_exposure < 0:
            return False, "Capital, price and quantity must be positive"

        try:
            max_order_pct = float(execution.get('max_order_notional_percent', 2.0))
            max_gross_pct = float(execution.get('max_gross_exposure_percent', 10.0))
            max_positions = int(execution.get('max_open_positions', 3))
            max_symbol_pct = float(execution.get('max_symbol_exposure_percent', 0.0))
        except (TypeError, ValueError):
            return False, "Execution risk limits are invalid"
        if not 0 < max_order_pct <= 100 or not 0 < max_gross_pct <= 100 or max_positions < 1 or not 0 <= max_symbol_pct <= 100:
            return False, "Execution risk limits must be positive and no more than 100%"

        notional = price * quantity
        if notional > capital * max_order_pct / 100:
            return False, f"Order notional exceeds {max_order_pct:g}% per-order limit"
        if gross_exposure + notional > capital * max_gross_pct / 100:
            return False, f"Order would exceed {max_gross_pct:g}% gross-exposure limit"
        if max_symbol_pct and symbol_exposure + notional > capital * max_symbol_pct / 100:
            return False, f"Order would exceed {max_symbol_pct:g}% symbol-exposure limit"
        if open_positions >= max_positions:
            return False, f"Maximum open positions ({max_positions}) reached"

        # A stop-loss-based risk check is a second independent cap.  It is
        # deliberately applied to gross notional because alerts have no
        # verifiable attached stop order.
        estimated_loss = notional * self.stop_loss_percent / 100
        permitted_loss = capital * self.get_risk_per_trade(capital) / 100
        if estimated_loss > permitted_loss:
            return False, "Estimated stop-loss risk exceeds the configured per-trade risk"
        return True, "Order risk checks passed"
