"""
Execution manager and order-routing primitives.

This module captures the most useful execution patterns from institutional
trading systems: TWAP/VWAP slicing, spread and slippage checks, and a simple
order-routing score for venue selection. The design is intentionally lightweight
and can be dropped into the existing risk / strategy framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class OrderRequest:
    """Minimal order object used by execution logic."""

    symbol: str
    side: str
    quantity: float
    price: float
    order_type: str = "limit"
    post_only: bool = False
    immediate_or_cancel: bool = False


@dataclass
class ExecutionPlan:
    """Execution plan for splitting an order into smaller child orders."""

    symbol: str
    side: str
    total_quantity: float
    chunks: List[Tuple[float, float]] = field(default_factory=list)
    reason: str = "sliced"


def twap_chunks(total_quantity: float, steps: int = 5) -> List[Tuple[float, float]]:
    """Split a total order quantity into equal TWAP slices."""
    total_quantity = float(total_quantity)
    if total_quantity <= 0 or steps <= 0:
        return []
    chunk = total_quantity / steps
    return [(chunk, float(i + 1)) for i in range(steps)]


def vwap_chunks(
    total_quantity: float, volume_profile: Sequence[float]
) -> List[Tuple[float, float]]:
    """Split quantity proportionally to a volume profile."""
    total_quantity = float(total_quantity)
    if total_quantity <= 0:
        return []
    profile = [float(v) for v in volume_profile]
    if not profile or sum(profile) <= 0:
        return twap_chunks(total_quantity, max(1, len(profile) or 1))
    total_volume = sum(profile)
    chunks: List[Tuple[float, float]] = []
    for idx, weight in enumerate(profile):
        ratio = weight / total_volume
        chunks.append((total_quantity * ratio, float(idx + 1)))
    return chunks


def spread_guard(price: float, mid_price: float, max_spread_pct: float = 0.25) -> bool:
    """Return True when the order is within an acceptable spread band."""
    if mid_price <= 0 or price <= 0:
        return False
    spread_pct = abs(price - mid_price) / mid_price * 100.0
    return spread_pct <= max_spread_pct


def slippage_guard(expected_price: float, fill_price: float, max_slippage_pct: float = 0.5) -> bool:
    """Return True if the observed slippage is below the configured tolerance."""
    if expected_price <= 0:
        return False
    slippage_pct = abs(fill_price - expected_price) / expected_price * 100.0
    return slippage_pct <= max_slippage_pct


def order_routing_candidates(
    symbol: str, venues: Iterable[Dict[str, float]]
) -> List[Dict[str, float]]:
    """Return venues ranked by best available execution conditions."""
    ranked = []
    for venue in venues:
        bid = float(venue.get("bid", 0.0))
        ask = float(venue.get("ask", 0.0))
        fee = float(venue.get("fee", 0.1))
        liquidity = float(venue.get("liquidity", 0.0))
        weighted = (liquidity * 0.7) - (fee * 10.0) + (bid + ask) * 0.001
        ranked.append({**venue, "symbol": symbol, "weighted_score": weighted})
    return sorted(ranked, key=lambda item: item["weighted_score"], reverse=True)


def build_execution_plan(
    symbol: str,
    side: str,
    total_quantity: float,
    volume_profile: Optional[Sequence[float]] = None,
    steps: int = 5,
) -> ExecutionPlan:
    """Create a single-step execution plan for an order."""
    if volume_profile is None:
        chunks = twap_chunks(total_quantity, steps=steps)
        reason = "twap"
    else:
        chunks = vwap_chunks(total_quantity, volume_profile)
        reason = "vwap"
    return ExecutionPlan(
        symbol=symbol, side=side, total_quantity=float(total_quantity), chunks=chunks, reason=reason
    )


def paper_fill(order: OrderRequest, fill_price: Optional[float] = None) -> Dict[str, float]:
    """Simulate a fill using a paper execution engine for validation only."""
    if fill_price is None:
        fill_price = order.price
    return {
        "symbol": order.symbol,
        "side": order.side,
        "quantity": float(order.quantity),
        "price": float(fill_price),
        "status": "filled",
        "order_type": order.order_type,
        "post_only": bool(order.post_only),
        "immediate_or_cancel": bool(order.immediate_or_cancel),
    }


__all__ = [
    "OrderRequest",
    "ExecutionPlan",
    "twap_chunks",
    "vwap_chunks",
    "spread_guard",
    "slippage_guard",
    "order_routing_candidates",
    "build_execution_plan",
    "paper_fill",
]
