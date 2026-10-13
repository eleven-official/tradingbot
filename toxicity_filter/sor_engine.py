"""
Smart Order Routing (SOR) Engine
Fragment large orders into randomized, stealthy iceberg slices across multiple venues
"""
import asyncio
import logging
import random
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import time


class OrderType(Enum):
    """Order types."""
    LIMIT = "limit"
    MARKET = "market"
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill


class Venue(Enum):
    """Trading venues."""
    BINANCE = "binance"
    BYBIT = "bybit"
    KRAKEN = "kraken"
    OKX = "okx"


@dataclass
class OrderSlice:
    """A single slice of a larger order."""
    slice_id: str
    parent_order_id: str
    venue: Venue
    symbol: str
    side: str
    order_type: OrderType
    size: float
    price: Optional[float]
    timestamp: datetime
    status: str = "pending"
    filled_size: float = 0.0
    fill_price: Optional[float] = None


@dataclass
class ParentOrder:
    """Parent order that gets sliced."""
    order_id: str
    symbol: str
    side: str
    total_size: float
    target_price: float
    slices: List[OrderSlice] = field(default_factory=list)
    filled_size: float = 0.0
    average_fill_price: Optional[float] = None
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class SOREngine:
    """
    Smart Order Routing engine for optimal execution.
    Fragments orders across venues to minimize market impact.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sor_config = config.get('sor', {})
        
        # Configuration
        self.enabled = self.sor_config.get('enabled', True)
        self.iceberg_slices = self.sor_config.get('iceberg_slices', 10)
        self.randomize_venues = self.sor_config.get('randomize_venues', True)
        self.min_order_size = self.sor_config.get('min_order_size', 0.001)
        
        # Available venues
        self.venues = [Venue.BINANCE, Venue.BYBIT, Venue.KRAKEN, Venue.OKX]
        
        # Order tracking
        self.parent_orders: Dict[str, ParentOrder] = {}
        self.slice_executions: Dict[str, OrderSlice] = {}
        
        # Execution statistics
        self.execution_stats = {
            'total_orders': 0,
            'total_slices': 0,
            'successful_slices': 0,
            'failed_slices': 0,
            'avg_slippage': 0.0,
            'avg_execution_time': 0.0
        }
        
        self.logger = logging.getLogger(__name__)
        logging.info("SOR Engine initialized")
    
    async def initialize(self):
        """Initialize the SOR engine."""
        self.logger.info("SOR Engine initialized")
    
    
    async def execute_order(self, symbol: str, side: str, size: float, 
                          target_price: float, order_type: OrderType = OrderType.LIMIT) -> ParentOrder:
        """Execute an order using smart routing."""
        if not self.enabled:
            # Execute directly without SOR
            return await self._execute_direct(symbol, side, size, target_price, order_type)
        
        # Create parent order
        order_id = f"order_{int(time.time() * 1000)}"
        parent_order = ParentOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            total_size=size,
            target_price=target_price
        )
        
        # Determine if we should slice the order
        should_slice = size > self.min_order_size * 2  # Slice if > 2x min size
        
        if should_slice:
            # Iceberg execution
            await self._execute_iceberg(parent_order, order_type)
        else:
            # Direct execution
            await self._execute_direct(parent_order, order_type)
        
        self.parent_orders[order_id] = parent_order
        self.execution_stats['total_orders'] += 1
        
        return parent_order
    
    async def _execute_iceberg(self, parent_order: ParentOrder, order_type: OrderType):
        """Execute order as iceberg slices."""
        total_size = parent_order.total_size
        num_slices = min(self.iceberg_slices, int(total_size / self.min_order_size))
        
        # Calculate slice sizes (vary slightly for randomness)
        base_slice_size = total_size / num_slices
        slice_sizes = []
        
        for i in range(num_slices):
            # Add random variation (±10%)
            variation = random.uniform(0.9, 1.1)
            slice_size = base_slice_size * variation
            slice_sizes.append(slice_size)
        
        # Normalize to ensure total size matches
        total_slice_size = sum(slice_sizes)
        slice_sizes = [s * total_size / total_slice_size for s in slice_sizes]
        
        # Execute slices
        for i, slice_size in enumerate(slice_sizes):
            slice_id = f"{parent_order.order_id}_slice_{i}"
            
            # Select venue
            if self.randomize_venues:
                venue = random.choice(self.venues)
            else:
                venue = self.venues[0]  # Default to first venue
            
            # Create slice
            slice_order = OrderSlice(
                slice_id=slice_id,
                parent_order_id=parent_order.order_id,
                venue=venue,
                symbol=parent_order.symbol,
                side=parent_order.side,
                order_type=order_type,
                size=slice_size,
                price=parent_order.target_price if order_type == OrderType.LIMIT else None,
                timestamp=datetime.now()
            )
            
            parent_order.slices.append(slice_order)
            self.execution_stats['total_slices'] += 1
            
            # Execute slice
            await self._execute_slice(slice_order)
            
            # Random delay between slices (1-5 seconds)
            delay = random.uniform(1, 5)
            await asyncio.sleep(delay)
        
        # Update parent order status
        parent_order.status = "completed"
        parent_order.completed_at = datetime.now()
    
    async def _execute_slice(self, slice_order: OrderSlice):
        """Execute a single order slice."""
        try:
            # In production, this would send to exchange
            # For now, simulate execution
            self.logger.info(
                f"Executing slice {slice_order.slice_id}: "
                f"{slice_order.size} {slice_order.symbol} @ {slice_order.venue.value}"
            )
            
            # Simulate fill
            await asyncio.sleep(random.uniform(0.1, 0.5))
            
            # Assume 95% fill rate
            fill_probability = 0.95
            if random.random() < fill_probability:
                slice_order.status = "filled"
                slice_order.filled_size = slice_order.size
                slice_order.fill_price = slice_order.price if slice_order.price else slice_order.price
                
                self.execution_stats['successful_slices'] += 1
            else:
                slice_order.status = "partial"
                slice_order.filled_size = slice_order.size * 0.5
                self.execution_stats['failed_slices'] += 1
            
            self.slice_executions[slice_order.slice_id] = slice_order
            
        except Exception as e:
            self.logger.error(f"Slice execution error: {e}")
            slice_order.status = "failed"
            self.execution_stats['failed_slices'] += 1
    
    async def _execute_direct(self, parent_order: ParentOrder, order_type: OrderType):
        """Execute order directly without slicing."""
        # Create single slice
        slice_id = f"{parent_order.order_id}_direct"
        venue = self.venues[0]
        
        slice_order = OrderSlice(
            slice_id=slice_id,
            parent_order_id=parent_order.order_id,
            venue=venue,
            symbol=parent_order.symbol,
            side=parent_order.side,
            order_type=order_type,
            size=parent_order.total_size,
            price=parent_order.target_price if order_type == OrderType.LIMIT else None,
            timestamp=datetime.now()
        )
        
        parent_order.slices.append(slice_order)
        self.execution_stats['total_slices'] += 1
        
        # Execute
        await self._execute_slice(slice_order)
        
        # Update parent order
        parent_order.status = "completed"
        parent_order.completed_at = datetime.now()
    
    async def _execute_direct(self, symbol: str, side: str, size: float,
                          target_price: float, order_type: OrderType) -> ParentOrder:
        """Execute order directly (fallback when SOR disabled)."""
        order_id = f"order_{int(time.time() * 1000)}"
        
        parent_order = ParentOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            total_size=size,
            target_price=target_price
        )
        
        # Execute as single slice
        await self._execute_direct(parent_order, order_type)
        
        return parent_order
    
    async def get_best_venue(self, symbol: str, size: float) -> Venue:
        """Get best venue for order based on liquidity and fees."""
        # In production, this would query all venues for:
        # - Current liquidity
        # - Fee structure
        # - Recent fill rates
        # - Latency
        
        # For now, return random venue
        return random.choice(self.venues)
    
    async def choose_order_type(self, regime: str, momentum: float) -> OrderType:
        """Choose optimal order type based on market conditions."""
        # In choppy regimes, use limit orders for maker rebates
        if regime == "choppy" or abs(momentum) < 0.01:
            return OrderType.LIMIT
        
        # In high momentum, use aggressive orders for fills
        if regime == "trending" and abs(momentum) > 0.02:
            return OrderType.IOC
        
        # Default to limit
        return OrderType.LIMIT
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order and all its slices."""
        if order_id not in self.parent_orders:
            return False
        
        parent_order = self.parent_orders[order_id]
        
        # Cancel all pending slices
        for slice_order in parent_order.slices:
            if slice_order.status == "pending":
                slice_order.status = "cancelled"
        
        parent_order.status = "cancelled"
        
        return True
    
    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an order."""
        if order_id not in self.parent_orders:
            return None
        
        parent_order = self.parent_orders[order_id]
        
        filled_slices = [s for s in parent_order.slices if s.status == "filled"]
        filled_size = sum(s.filled_size for s in filled_slices)
        
        return {
            'order_id': parent_order.order_id,
            'status': parent_order.status,
            'total_size': parent_order.total_size,
            'filled_size': filled_size,
            'fill_percentage': (filled_size / parent_order.total_size * 100) if parent_order.total_size > 0 else 0,
            'slices_total': len(parent_order.slices),
            'slices_filled': len(filled_slices),
            'created_at': parent_order.created_at.isoformat(),
            'completed_at': parent_order.completed_at.isoformat() if parent_order.completed_at else None
        }
    
    async def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return self.execution_stats
    
    async def shutdown(self):
        """Shutdown the SOR engine."""
        self.logger.info("SOR Engine shutdown complete")