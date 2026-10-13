"""
State management and persistence for the trading bot.
Extracted from trading_bot.py for better code organization.
"""
import datetime
import logging
from typing import Optional, Dict, Any
from infra import (
    load_daily_pnl, load_weekly_pnl, save_daily_pnl, save_weekly_pnl,
    state_path, read_json, atomic_write_json, load_week_trade_days, add_week_trade_day
)
from core.profit_pleasure import ProfitPleasureSystem


class StateManager:
    """Manages bot state including P&L tracking, trade ledger, and session state."""
    
    def __init__(self, config):
        self.config = config
        self._today_str = datetime.date.today().isoformat()
        self._today_week_str = datetime.date.today().strftime("%G-W%V")
        
        # Initialize profit pleasure system
        self.profit_pleasure = ProfitPleasureSystem(config)
        
        # Realized P&L tracking for daily-loss and weekly-loss circuit breakers.
        # Both are persisted to disk so a same-day restart doesn't reset the caps.
        self.realized_pnl_today = load_daily_pnl(self._today_str)
        self.realized_pnl_week = load_weekly_pnl(self._today_week_str)
        
        if self.realized_pnl_today != 0.0:
            try:
                logging.info(
                    f"Resuming with persisted realized P&L for {self._today_str}: "
                    f"{float(self.realized_pnl_today):,.2f}"
                )
            except (TypeError, ValueError):
                logging.info(
                    f"Resuming with persisted realized P&L for {self._today_str}: "
                    f"{self.realized_pnl_today}"
                )
        if self.realized_pnl_week != 0.0:
            try:
                logging.info(
                    f"Resuming with weekly P&L for {self._today_week_str}: "
                    f"{float(self.realized_pnl_week):,.2f}"
                )
            except (TypeError, ValueError):
                logging.info(
                    f"Resuming with weekly P&L for {self._today_week_str}: "
                    f"{self.realized_pnl_week}"
                )
        
        # Session trade ledger for the live status line + end-of-day summary.
        self.wins_today: int = 0
        self.losses_today: int = 0
        self.scratch_today: int = 0
        self.completed_trades: list = []   # [{symbol, type, gross, costs, net, strategy}]
        self.trades_today_count = 0
        self.entries_today: list = []      # Filled entries; separate from closed-trade P&L.
        
        # Consecutive-loss counter — resets each bot restart (session-scoped).
        self.consecutive_losses: int = 0
        
        # Capital tracking
        self.starting_capital = None
        self.ending_capital = None
        
        # Restore today's trade ledger from disk so a same-day RESTART shows the
        # FULL day (trades, W/L, trade count) — not just trades since this run
        # started.
        self._load_ledger()
    
    def _load_ledger(self):
        """Restore today's trade ledger from disk."""
        ledger = read_json(state_path(f"trade_ledger_{self._today_str}.json"), default={})
        if ledger:
            self.wins_today = ledger.get('wins', 0)
            self.losses_today = ledger.get('losses', 0)
            self.scratch_today = ledger.get('scratches', 0)
            self.completed_trades = ledger.get('trades', [])
            self.trades_today_count = ledger.get('trade_count', 0)
            self.entries_today = ledger.get('entries', [])
            logging.info(
                f"Restored ledger: {self.wins_today}W/{self.losses_today}L/{self.scratch_today}S, "
                f"{self.trades_today_count} trades today"
            )
    
    def save_ledger(self):
        """Persist today's trade ledger to disk."""
        ledger = {
            'wins': self.wins_today,
            'losses': self.losses_today,
            'scratches': self.scratch_today,
            'trades': self.completed_trades,
            'trade_count': self.trades_today_count,
            'entries': self.entries_today,
            'date': self._today_str
        }
        atomic_write_json(state_path(f"trade_ledger_{self._today_str}.json"), ledger)
    
    def update_pnl(self, pnl_amount: float):
        """Update realized P&L and persist to disk."""
        self.realized_pnl_today += pnl_amount
        self.realized_pnl_week += pnl_amount
        save_daily_pnl(self._today_str, self.realized_pnl_today)
        save_weekly_pnl(self._today_week_str, self.realized_pnl_week)
    
    def record_trade(self, trade_result: Dict[str, Any]):
        """Record a completed trade in the ledger."""
        self.completed_trades.append(trade_result)
        self.trades_today_count += 1
        
        pnl = trade_result.get('net', 0)
        if pnl > 0:
            self.wins_today += 1
            self.consecutive_losses = 0  # Reset on winning trade
            # Trigger profit pleasure feedback
            pleasure_event = self.profit_pleasure.evaluate_profit(trade_result)
            if pleasure_event:
                logging.info(f"💖 {pleasure_event.message}")
        elif pnl < 0:
            self.losses_today += 1
            self.consecutive_losses += 1
        else:
            self.scratch_today += 1
            self.consecutive_losses = 0  # Reset on scratch
        
        self.update_pnl(pnl)
        self.save_ledger()

    def record_entry(self, entry: Dict[str, Any]):
        """Record a filled entry so the daily trade cap survives restarts.

        Entry records intentionally do not alter realised P&L; that happens
        only when the corresponding position is reduced or closed.
        """
        self.entries_today.append(entry)
        self.entries_today = self.entries_today[-1_000:]
        self.trades_today_count += 1
        self.save_ledger()
    
    def check_daily_loss_limit(self, limit_percent: float, capital: float) -> bool:
        """Check if daily loss limit has been exceeded."""
        if limit_percent <= 0:
            return False
        
        max_loss = capital * (limit_percent / 100)
        return self.realized_pnl_today <= -max_loss
    
    def check_weekly_loss_limit(self, limit_percent: float, capital: float) -> bool:
        """Check if weekly loss limit has been exceeded."""
        if limit_percent <= 0:
            return False
        
        max_loss = capital * (limit_percent / 100)
        return self.realized_pnl_week <= -max_loss
    
    def check_consecutive_loss_limit(self, max_losses: int) -> bool:
        """Check if consecutive loss limit has been exceeded."""
        return self.consecutive_losses >= max_losses
    
    def get_session_summary(self) -> str:
        """Get a summary of the current trading session."""
        total_trades = self.wins_today + self.losses_today + self.scratch_today
        # Win rate excludes scratches
        win_rate = (self.wins_today / (self.wins_today + self.losses_today) * 100) if (self.wins_today + self.losses_today) > 0 else 0
        
        try:
            pnl_str = f"${float(self.realized_pnl_today):,.2f}"
        except (TypeError, ValueError):
            pnl_str = f"${self.realized_pnl_today}"
        
        return (
            f"Session: {self.wins_today}W/{self.losses_today}L/{self.scratch_today}S "
            f"({total_trades} trades, {win_rate:.1f}% win rate) | "
            f"P&L: {pnl_str}"
        )
    
    def reset_session_counters(self):
        """Reset session-scoped counters (not persisted counters)."""
        self.consecutive_losses = 0
        logging.info("Session counters reset")
