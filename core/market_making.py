"""Simple order-book tracking and event-driven processing.

This implements the most useful features from the Hummingbot-style orderbook
pattern: snapshot ingestion, delta updates, bid/ask extraction, mid-price and
spread calculations. It is intentionally compact and can be expanded later to
track full L2 depth or exchange-specific event streams.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class BookLevel:
    price: float
    quantity: float


@dataclass
class OrderBook:
    bids: Dict[float, float] = field(default_factory=dict)
    asks: Dict[float, float] = field(default_factory=dict)

    def apply_snapshot(self, snapshot: Dict[str, Iterable[Tuple[float, float]]]) -> None:
        """Replace book state with a snapshot from an exchange."""
        self.bids = {float(price): float(quantity) for price, quantity in snapshot.get("bids", [])}
        self.asks = {float(price): float(quantity) for price, quantity in snapshot.get("asks", [])}

    def apply_delta(self, delta: Dict[str, Iterable[Tuple[float, float]]]) -> None:
        """Apply a L2 incremental delta update."""
        for side in ("bids", "asks"):
            updates = delta.get(side, [])
            book = getattr(self, side)
            for price, quantity in updates:
                price = float(price)
                quantity = float(quantity)
                if quantity <= 0:
                    book.pop(price, None)
                else:
                    book[price] = quantity

    @property
    def best_bid(self) -> Optional[float]:
        if not self.bids:
            return None
        return max(self.bids.keys())

    @property
    def best_ask(self) -> Optional[float]:
        if not self.asks:
            return None
        return min(self.asks.keys())

    @property
    def mid_price(self) -> Optional[float]:
        bid = self.best_bid
        ask = self.best_ask
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    @property
    def spread_pct(self) -> Optional[float]:
        mid = self.mid_price
        bid = self.best_bid
        ask = self.best_ask
        if mid is None or bid is None or ask is None:
            return None
        return (ask - bid) / mid * 100.0

    def top_of_book(self) -> Dict[str, Optional[float]]:
        return {"bid": self.best_bid, "ask": self.best_ask, "mid_price": self.mid_price, "spread_pct": self.spread_pct}


class OrderBookTracker:
    """Tracks a single symbol's order book and emits book snapshots."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.order_book = OrderBook()

    def process_snapshot(self, snapshot: Dict[str, Iterable[Tuple[float, float]]]) -> OrderBook:
        self.order_book.apply_snapshot(snapshot)
        return self.order_book

    def process_delta(self, delta: Dict[str, Iterable[Tuple[float, float]]]) -> OrderBook:
        self.order_book.apply_delta(delta)
        return self.order_book

    def get_order_book(self) -> OrderBook:
        return self.order_book


__all__ = ["BookLevel", "OrderBook", "OrderBookTracker"]
