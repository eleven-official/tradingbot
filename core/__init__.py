"""Institutional-style pure market making primitives.

This is intentionally compact and safe: it places quotes around the mid price,
adds inventory skewing, and exposes a single method to generate a quote pair.
It is meant to be used as a strategy-building block inside the existing ensemble
system rather than as a complete live market-making engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Quote:
    symbol: str
    side: str
    price: float
    quantity: float


class PureMarketMaker:
    """Simple market-making engine that places symmetric bid/ask quotes."""

    def __init__(self, spread_pct: float = 0.10, base_quantity: float = 1.0, inventory_skew: float = 0.2):
        self.spread_pct = float(spread_pct)
        self.base_quantity = float(base_quantity)
        self.inventory_skew = float(inventory_skew)

    def generate_quotes(self, symbol: str, mid_price: float, inventory: float = 0.0) -> List[Quote]:
        if mid_price <= 0:
            return []

        spread = mid_price * (self.spread_pct / 100.0)
        skew = inventory * self.inventory_skew
        bid_price = mid_price - spread - skew
        ask_price = mid_price + spread - skew
        qty = max(0.0, self.base_quantity + abs(inventory) * 0.1)

        return [
            Quote(symbol=symbol, side="BUY", price=bid_price, quantity=qty),
            Quote(symbol=symbol, side="SELL", price=ask_price, quantity=qty),
        ]

    def quote_levels(self, symbol: str, order_book: Optional[Dict[str, float]], inventory: float = 0.0) -> List[Quote]:
        if not order_book:
            return []
        mid_price = float(order_book.get("mid_price") or 0)
        return self.generate_quotes(symbol, mid_price, inventory=inventory)


__all__ = ["Quote", "PureMarketMaker"]
