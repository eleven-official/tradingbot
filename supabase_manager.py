"""
Supabase Database Manager for Loki Trading Platform
Handles database operations for trades, signals, equity, regimes, and training reports
"""

import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from types import SimpleNamespace
from loki_v8.persistence import get_logger


class _Query:
    def __init__(self, vault, table):
        self.vault, self.name, self.params, self.row = vault, table, {}, None

    def select(self, columns):
        self.params["select"] = columns
        return self

    def insert(self, row):
        self.row = row
        return self

    def order(self, column, desc=False):
        self.params["order"] = column + (".desc" if desc else ".asc")
        return self

    def limit(self, count):
        self.params["limit"] = str(max(1, min(int(count), 10000)))
        return self

    def eq(self, column, value):
        self.params[column] = "eq." + str(value)
        return self

    def execute(self):
        result = self.vault.request(
            "POST" if self.row is not None else "GET", self.name, row=self.row, params=self.params
        )
        if not result["ok"]:
            raise RuntimeError(result.get("error") or result.get("reason"))
        return SimpleNamespace(data=result.get("data", []))


class LokiSupabaseManager:
    """Domain operations backed by the same private vault as the engine."""

    def __init__(self):
        self.vault = get_logger()
        self.client = self

    @property
    def connected(self):
        return self.vault.status()["verified"]

    def table(self, name):
        return _Query(self.vault, name)

    def test_connection(self) -> bool:
        return self.vault.test_connection()["ok"]

    # ============================================
    # TRADES
    # ============================================

    def insert_trade(self, trade_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert a trade record.

        Args:
            trade_data: Dictionary with trade details (symbol, side, qty, entry_price, etc.)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_trades").insert(trade_data).execute()
            if response.data:
                print(f"Trade inserted: {trade_data.get('symbol')} {trade_data.get('side')}")
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_trades(
        self, symbol: Optional[str] = None, limit: int = 100, mode: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve trade records.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records
            mode: Filter by mode (paper/live)

        Returns:
            List of trade records
        """
        if not self.connected:
            return []

        try:
            query = (
                self.client.table("loki_trades")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )

            if symbol:
                query = query.eq("symbol", symbol)
            if mode:
                query = query.eq("mode", mode)

            response = query.execute()
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # SIGNALS
    # ============================================

    def insert_signal(self, signal_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert a trading signal.

        Args:
            signal_data: Dictionary with signal details (symbol, action, score, confidence, etc.)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_signals").insert(signal_data).execute()
            if response.data:
                print(f"Signal inserted: {signal_data.get('symbol')} {signal_data.get('action')}")
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_signals(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Retrieve signal records.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records

        Returns:
            List of signal records
        """
        if not self.connected:
            return []

        try:
            query = (
                self.client.table("loki_signals")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )

            if symbol:
                query = query.eq("symbol", symbol)

            response = query.execute()
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # EQUITY SNAPSHOTS
    # ============================================

    def insert_equity_snapshot(self, equity_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert an equity snapshot.

        Args:
            equity_data: Dictionary with equity details (equity, cash, open_positions, mode)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_equity_snapshots").insert(equity_data).execute()
            if response.data:
                print(f"Equity snapshot inserted: ${equity_data.get('equity')}")
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_equity_history(self, limit: int = 1000) -> List[Dict]:
        """
        Retrieve equity history.

        Args:
            limit: Maximum number of records

        Returns:
            List of equity snapshots
        """
        if not self.connected:
            return []

        try:
            response = (
                self.client.table("loki_equity_snapshots")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # REGIME EVENTS
    # ============================================

    def insert_regime_event(self, regime_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert a regime change event.

        Args:
            regime_data: Dictionary with regime details (symbol, from_state, to_state, confidence)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_regime_events").insert(regime_data).execute()
            if response.data:
                print(
                    f"Regime event inserted: {regime_data.get('symbol')} {regime_data.get('from_state')} -> {regime_data.get('to_state')}"
                )
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_regime_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Retrieve regime change history.

        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of records

        Returns:
            List of regime events
        """
        if not self.connected:
            return []

        try:
            query = (
                self.client.table("loki_regime_events")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )

            if symbol:
                query = query.eq("symbol", symbol)

            response = query.execute()
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # TRAINING REPORTS
    # ============================================

    def insert_training_report(self, report_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert a training report.

        Args:
            report_data: Dictionary with training details (period, payload as JSON)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_training_reports").insert(report_data).execute()
            if response.data:
                print(f"Training report inserted: {report_data.get('period')}")
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_training_reports(self, limit: int = 50) -> List[Dict]:
        """
        Retrieve training reports.

        Args:
            limit: Maximum number of records

        Returns:
            List of training reports
        """
        if not self.connected:
            return []

        try:
            response = (
                self.client.table("loki_training_reports")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # EVENTS
    # ============================================

    def insert_event(self, event_data: Dict[str, Any]) -> Optional[Dict]:
        """
        Insert a system event.

        Args:
            event_data: Dictionary with event details (kind, payload as JSON)

        Returns:
            Inserted record or None on failure
        """
        if not self.connected:
            return None

        try:
            response = self.client.table("loki_events").insert(event_data).execute()
            if response.data:
                print(f"Event inserted: {event_data.get('kind')}")
                return response.data[0]
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")

        return None

    def get_events(self, kind: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Retrieve system events.

        Args:
            kind: Filter by event kind (optional)
            limit: Maximum number of records

        Returns:
            List of events
        """
        if not self.connected:
            return []

        try:
            query = (
                self.client.table("loki_events")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )

            if kind:
                query = query.eq("kind", kind)

            response = query.execute()
            return response.data
        except Exception as e:
            print("Vault operation failed; inspect the private vault status")
            return []

    # ============================================
    # ANALYTICS
    # ============================================

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Calculate performance summary from trades.

        Returns:
            Dictionary with performance metrics
        """
        trades = self.get_trades(limit=10000)

        if not trades:
            return {}

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
        losing_trades = total_trades - winning_trades

        total_pnl = sum(t.get("pnl", 0) for t in trades)
        wins = [t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0]
        losses = [t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0]

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": winning_trades / total_trades if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "profit_factor": sum(wins) / abs(sum(losses)) if losses else 0,
        }


def test_supabase_connection():
    """Explicit read-only CLI check; does not seed fabricated trading records."""
    manager = LokiSupabaseManager()
    result = manager.test_connection()
    print("Supabase connection verified" if result else "Supabase is unconfigured or unavailable")
    return result


if __name__ == "__main__":
    test_supabase_connection()
