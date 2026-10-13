#!/usr/bin/env python3
"""
Advanced Execution Engine
Smart order routing, execution cost optimization, and market impact minimization.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
import datetime
import numpy as np
from dataclasses import dataclass
from enum import Enum
import threading
import time

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    ICEBERG = "ICEBERG"
    TWAP = "TWAP"
    VWAP = "VWAP"

class OrderStatus(Enum):
    PENDING = "PENDING"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    """Advanced order object with execution parameters."""
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: int
    order_type: OrderType
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"
    
    # Advanced execution parameters
    max_participation_rate: float = 0.1  # Max % of volume
    min_fill_size: int = 1
    hidden_quantity: Optional[int] = None
    
    # Execution state
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    commission_paid: float = 0.0
    created_time: datetime.datetime = None
    last_update_time: datetime.datetime = None
    
    # Smart routing parameters
    urgency_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH, URGENT
    max_market_impact: float = 0.005  # 0.5% max impact
    
    def __post_init__(self):
        if self.created_time is None:
            self.created_time = datetime.datetime.now()
        self.last_update_time = self.created_time

@dataclass
class Fill:
    """Individual fill record."""
    order_id: str
    fill_id: str
    quantity: int
    price: float
    commission: float
    timestamp: datetime.datetime
    liquidity_flag: str  # 'MAKER' or 'TAKER'

class MarketDataFeed:
    """Real-time market data feed simulator."""
    
    def __init__(self):
        self.subscribers = []
        self.current_prices = {}
        self.bid_ask_spreads = {}
        self.volume_profiles = {}
        
    def subscribe(self, callback):
        """Subscribe to market data updates."""
        self.subscribers.append(callback)
    
    def update_market_data(self, symbol: str, bid: float, ask: float, 
                          last_price: float, volume: int):
        """Update market data for a symbol."""
        self.current_prices[symbol] = {
            'bid': bid,
            'ask': ask,
            'last': last_price,
            'volume': volume,
            'timestamp': datetime.datetime.now()
        }
        self.bid_ask_spreads[symbol] = ask - bid
        
        # Notify subscribers
        for callback in self.subscribers:
            try:
                callback(symbol, self.current_prices[symbol])
            except Exception as e:
                logging.error(f"Error in market data callback: {e}")
    
    def get_current_price(self, symbol: str) -> Dict:
        """Get current market data for symbol."""
        return self.current_prices.get(symbol, {})
    
    def estimate_market_impact(self, symbol: str, quantity: int) -> float:
        """Estimate market impact for a given order size."""
        market_data = self.current_prices.get(symbol, {})
        if not market_data:
            return 0.01  # Default 1% impact
        
        # Simplified impact model
        spread = self.bid_ask_spreads.get(symbol, 0.01)
        avg_volume = market_data.get('volume', 1000)
        
        # Impact increases with order size relative to average volume
        relative_size = quantity / max(avg_volume, 100)
        impact = spread * 0.5 + relative_size * 0.002  # Base impact model
        
        return min(impact, 0.05)  # Cap at 5%

class SmartOrderRouter:
    """Intelligent order routing with execution cost optimization."""
    
    def __init__(self, market_data_feed: MarketDataFeed):
        self.market_data = market_data_feed
        self.active_orders = {}
        self.fill_history = []
        self.execution_strategies = {}
        
        # Execution venues (simulated)
        self.venues = {
            'PRIMARY': {'maker_fee': 0.0005, 'taker_fee': 0.001, 'fill_probability': 0.8},
            'DARK_POOL': {'maker_fee': 0.0002, 'taker_fee': 0.0008, 'fill_probability': 0.6},
            'ECN': {'maker_fee': 0.0003, 'taker_fee': 0.0009, 'fill_probability': 0.9}
        }
        
        self._setup_execution_strategies()
    
    def _setup_execution_strategies(self):
        """Setup different execution algorithms."""
        self.execution_strategies = {
            'AGGRESSIVE': self._aggressive_execution,
            'PASSIVE': self._passive_execution,
            'SMART': self._smart_execution,
            'TWAP': self._twap_execution,
            'VWAP': self._vwap_execution,
            'ICEBERG': self._iceberg_execution
        }
    
    def submit_order(self, order: Order) -> str:
        """Submit order for smart routing."""
        logging.info(f"Received order {order.order_id}: {order.side} {order.quantity} {order.symbol}")
        
        # Pre-trade risk checks
        if not self._pre_trade_risk_check(order):
            order.status = OrderStatus.REJECTED
            return order.order_id
        
        # Select execution strategy based on order characteristics
        strategy_name = self._select_execution_strategy(order)
        execution_strategy = self.execution_strategies.get(strategy_name, self._smart_execution)
        
        # Add to active orders
        self.active_orders[order.order_id] = order
        
        # Start execution in background
        threading.Thread(
            target=execution_strategy,
            args=(order,),
            daemon=True
        ).start()
        
        logging.info(f"Order {order.order_id} routed using {strategy_name} strategy")
        return order.order_id
    
    def _pre_trade_risk_check(self, order: Order) -> bool:
        """Pre-trade risk validation."""
        
        # Basic validations
        if order.quantity <= 0:
            logging.error(f"Invalid quantity: {order.quantity}")
            return False
        
        if order.order_type == OrderType.LIMIT and order.price is None:
            logging.error("Limit order missing price")
            return False
        
        # Market data availability check
        market_data = self.market_data.get_current_price(order.symbol)
        if not market_data:
            logging.error(f"No market data available for {order.symbol}")
            return False
        
        # Price reasonableness check
        if order.order_type == OrderType.LIMIT and order.price:
            last_price = market_data.get('last', 0)
            if last_price > 0:
                price_deviation = abs(order.price - last_price) / last_price
                if price_deviation > 0.1:  # 10% price deviation limit
                    logging.error(f"Price deviation too high: {price_deviation:.1%}")
                    return False
        
        # Position size check (simplified)
        daily_volume = market_data.get('volume', 1000) * 8 * 60  # Estimate daily volume
        if order.quantity > daily_volume * 0.05:  # Max 5% of daily volume
            logging.warning(f"Large order relative to daily volume: {order.quantity} vs {daily_volume}")
        
        return True
    
    def _select_execution_strategy(self, order: Order) -> str:
        """Select optimal execution strategy for the order."""
        
        market_data = self.market_data.get_current_price(order.symbol)
        if not market_data:
            return 'SMART'
        
        # Estimate market impact
        estimated_impact = self.market_data.estimate_market_impact(order.symbol, order.quantity)
        
        # Strategy selection logic
        if order.urgency_level == "URGENT" or estimated_impact < 0.001:
            return 'AGGRESSIVE'
        elif order.urgency_level == "LOW" and estimated_impact > 0.01:
            return 'TWAP'  # Time-weighted for large orders
        elif order.order_type == OrderType.ICEBERG:
            return 'ICEBERG'
        elif estimated_impact > 0.005:
            return 'VWAP'  # Volume-weighted for high impact orders
        else:
            return 'SMART'  # Default intelligent routing
    
    def _aggressive_execution(self, order: Order):
        """Aggressive execution - prioritize speed over cost."""
        market_data = self.market_data.get_current_price(order.symbol)
        
        if order.side == 'BUY':
            execution_price = market_data.get('ask', 0)
        else:
            execution_price = market_data.get('bid', 0)
        
        if execution_price > 0:
            # Execute immediately at market price
            fill = Fill(
                order_id=order.order_id,
                fill_id=f"{order.order_id}_1",
                quantity=order.quantity,
                price=execution_price,
                commission=execution_price * order.quantity * 0.001,
                timestamp=datetime.datetime.now(),
                liquidity_flag='TAKER'
            )
            
            self._process_fill(order, fill)
    
    def _passive_execution(self, order: Order):
        """Passive execution - prioritize cost over speed."""
        market_data = self.market_data.get_current_price(order.symbol)
        
        # Place order inside the spread for better fill price
        if order.side == 'BUY':
            target_price = market_data.get('bid', 0) + 0.01
        else:
            target_price = market_data.get('ask', 0) - 0.01
        
        # Simulate waiting for fill
        time.sleep(np.random.uniform(1, 5))  # Wait 1-5 seconds
        
        if np.random.random() < 0.7:  # 70% fill probability for passive orders
            fill = Fill(
                order_id=order.order_id,
                fill_id=f"{order.order_id}_1",
                quantity=order.quantity,
                price=target_price,
                commission=target_price * order.quantity * 0.0005,  # Lower maker fee
                timestamp=datetime.datetime.now(),
                liquidity_flag='MAKER'
            )
            
            self._process_fill(order, fill)
        else:
            # If not filled, try aggressive execution
            self._aggressive_execution(order)
    
    def _smart_execution(self, order: Order):
        """Intelligent execution balancing speed and cost."""
        market_data = self.market_data.get_current_price(order.symbol)
        estimated_impact = self.market_data.estimate_market_impact(order.symbol, order.quantity)
        
        if estimated_impact < 0.002:  # Low impact - be aggressive
            self._aggressive_execution(order)
        elif estimated_impact > 0.01:  # High impact - use TWAP
            self._twap_execution(order)
        else:
            # Moderate impact - use mixed strategy
            partial_size = order.quantity // 3
            
            # Execute 1/3 aggressively
            partial_order = Order(
                order_id=f"{order.order_id}_part1",
                symbol=order.symbol,
                side=order.side,
                quantity=partial_size,
                order_type=OrderType.MARKET
            )
            self._aggressive_execution(partial_order)
            
            # Execute remaining passively
            remaining_order = Order(
                order_id=f"{order.order_id}_part2",
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity - partial_size,
                order_type=OrderType.LIMIT
            )
            self._passive_execution(remaining_order)
    
    def _twap_execution(self, order: Order):
        """Time-Weighted Average Price execution."""
        total_slices = min(10, order.quantity // 100)  # Max 10 slices, min 100 shares per slice
        if total_slices < 1:
            total_slices = 1
        
        slice_size = order.quantity // total_slices
        remaining_quantity = order.quantity
        
        for i in range(total_slices):
            if remaining_quantity <= 0:
                break
                
            current_slice = min(slice_size, remaining_quantity)
            
            # Execute slice
            market_data = self.market_data.get_current_price(order.symbol)
            
            if order.side == 'BUY':
                execution_price = market_data.get('ask', 0)
            else:
                execution_price = market_data.get('bid', 0)
            
            fill = Fill(
                order_id=order.order_id,
                fill_id=f"{order.order_id}_{i+1}",
                quantity=current_slice,
                price=execution_price,
                commission=execution_price * current_slice * 0.0008,
                timestamp=datetime.datetime.now(),
                liquidity_flag='TAKER'
            )
            
            self._process_fill(order, fill)
            remaining_quantity -= current_slice
            
            # Wait before next slice (except last)
            if i < total_slices - 1:
                time.sleep(np.random.uniform(10, 30))  # 10-30 second intervals
    
    def _vwap_execution(self, order: Order):
        """Volume-Weighted Average Price execution."""
        # Simplified VWAP - would use real volume profile in production
        self._twap_execution(order)  # Fallback to TWAP for now
    
    def _iceberg_execution(self, order: Order):
        """Iceberg order execution - show only small portion."""
        visible_size = order.hidden_quantity or (order.quantity // 10)
        visible_size = max(visible_size, 1)
        
        remaining_quantity = order.quantity
        
        while remaining_quantity > 0:
            current_visible = min(visible_size, remaining_quantity)
            
            # Execute visible portion
            market_data = self.market_data.get_current_price(order.symbol)
            
            if order.side == 'BUY':
                execution_price = market_data.get('bid', 0)  # More passive pricing
            else:
                execution_price = market_data.get('ask', 0)
            
            fill = Fill(
                order_id=order.order_id,
                fill_id=f"{order.order_id}_{datetime.datetime.now().microsecond}",
                quantity=current_visible,
                price=execution_price,
                commission=execution_price * current_visible * 0.0006,
                timestamp=datetime.datetime.now(),
                liquidity_flag='MAKER'
            )
            
            self._process_fill(order, fill)
            remaining_quantity -= current_visible
            
            # Wait before showing next iceberg slice
            if remaining_quantity > 0:
                time.sleep(np.random.uniform(5, 15))
    
    def _process_fill(self, order: Order, fill: Fill):
        """Process an order fill."""
        order.filled_quantity += fill.quantity
        order.commission_paid += fill.commission
        
        # Update average fill price
        total_filled_value = order.avg_fill_price * (order.filled_quantity - fill.quantity)
        total_filled_value += fill.price * fill.quantity
        order.avg_fill_price = total_filled_value / order.filled_quantity
        
        order.last_update_time = fill.timestamp
        
        # Update order status
        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
            logging.info(f"Order {order.order_id} fully filled at avg price {order.avg_fill_price:.2f}")
        else:
            order.status = OrderStatus.PARTIAL_FILLED
        
        # Store fill
        self.fill_history.append(fill)
        
        # Remove from active orders if fully filled
        if order.status == OrderStatus.FILLED:
            self.active_orders.pop(order.order_id, None)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an active order."""
        if order_id in self.active_orders:
            order = self.active_orders[order_id]
            order.status = OrderStatus.CANCELLED
            self.active_orders.pop(order_id)
            logging.info(f"Order {order_id} cancelled")
            return True
        return False
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current order status."""
        return self.active_orders.get(order_id)
    
    def get_execution_report(self) -> Dict:
        """Generate execution performance report."""
        total_fills = len(self.fill_history)
        if total_fills == 0:
            return {}
        
        total_volume = sum(fill.quantity for fill in self.fill_history)
        total_commission = sum(fill.commission for fill in self.fill_history)
        
        maker_fills = [f for f in self.fill_history if f.liquidity_flag == 'MAKER']
        maker_rate = len(maker_fills) / total_fills
        
        avg_commission_rate = total_commission / sum(f.quantity * f.price for f in self.fill_history)
        
        return {
            'total_fills': total_fills,
            'total_volume': total_volume,
            'total_commission': total_commission,
            'avg_commission_rate': avg_commission_rate,
            'maker_rate': maker_rate,
            'active_orders': len(self.active_orders)
        }