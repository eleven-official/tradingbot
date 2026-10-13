"""
Realistic Slippage and Transaction Cost Modeling
Implements realistic execution costs, slippage, and market impact
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill


class OrderSide(Enum):
    """Order sides."""
    BUY = "buy"
    SELL = "sell"


class MarketCondition(Enum):
    """Market conditions affecting slippage."""
    NORMAL = "normal"
    VOLATILE = "volatile"
    LOW_LIQUIDITY = "low_liquidity"
    HIGH_VOLUME = "high_volume"
    FLASH_CRASH = "flash_crash"


@dataclass
class Order:
    """Order specification."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Fill:
    """Order fill result."""
    order: Order
    filled_quantity: float
    fill_price: float
    slippage_bps: float  # Basis points
    commission: float
    total_cost: float
    timestamp: datetime
    market_condition: MarketCondition


@dataclass
class TransactionCostModel:
    """Transaction cost model configuration."""
    maker_fee_bps: float = 0.02  # 0.02% maker fee
    taker_fee_bps: float = 0.04  # 0.04% taker fee
    base_slippage_bps: float = 1.0  # Base slippage 1 bps
    volatility_multiplier: float = 2.0  # Volatility multiplier for slippage
    volume_impact_factor: float = 0.001  # Volume impact factor
    minimum_fee: float = 0.0  # Minimum fee
    stress_multiplier: float = 1.0
    random_seed: Optional[int] = None


class SlippageModel:
    """
    Realistic slippage model based on market microstructure.
    Accounts for volatility, volume, order size, and market conditions.
    """
    
    def __init__(self, config: TransactionCostModel = None):
        self.config = config or TransactionCostModel()
        self.logger = logging.getLogger(__name__)
        if self.config.stress_multiplier <= 0:
            raise ValueError("stress_multiplier must be positive")
        self._rng = np.random.default_rng(self.config.random_seed)
    
    def calculate_slippage(self, order: Order, orderbook: Optional[Dict] = None,
                          market_data: Optional[Dict] = None) -> Tuple[float, MarketCondition]:
        """
        Calculate realistic slippage for an order.
        
        Returns:
            Tuple of (slippage_bps, market_condition)
        """
        market_condition = self._determine_market_condition(market_data)
        
        # Base slippage
        slippage = self.config.base_slippage_bps * self.config.stress_multiplier
        
        # Adjust for market condition
        slippage *= self._get_condition_multiplier(market_condition)
        
        # Adjust for volatility
        if market_data and 'volatility' in market_data:
            volatility_adjustment = 1 + (market_data['volatility'] * self.config.volatility_multiplier)
            slippage *= volatility_adjustment
        
        # Adjust for order size (market impact)
        if orderbook and 'volume' in orderbook:
            volume_impact = self._calculate_volume_impact(order.quantity, orderbook['volume'])
            slippage += volume_impact
        
        # Adjust for order type
        slippage *= self._get_order_type_multiplier(order.order_type)
        
        # Add random noise for realism
        noise = self._rng.normal(0, slippage * 0.2)
        slippage += noise
        
        # Ensure non-negative
        slippage = max(0, slippage)
        
        return slippage, market_condition
    
    def _determine_market_condition(self, market_data: Optional[Dict]) -> MarketCondition:
        """Determine current market condition."""
        if not market_data:
            return MarketCondition.NORMAL
        
        volatility = market_data.get('volatility', 0)
        volume = market_data.get('volume', 0)
        avg_volume = market_data.get('avg_volume', 1)
        
        # Flash crash detection
        if market_data.get('price_change', 0) < -0.05:  # 5% drop
            return MarketCondition.FLASH_CRASH
        
        # High volatility
        if volatility > 0.03:  # 3% daily volatility
            return MarketCondition.VOLATILE
        
        # Low liquidity
        if volume < avg_volume * 0.5:
            return MarketCondition.LOW_LIQUIDITY
        
        # High volume
        if volume > avg_volume * 2.0:
            return MarketCondition.HIGH_VOLUME
        
        return MarketCondition.NORMAL
    
    def _get_condition_multiplier(self, condition: MarketCondition) -> float:
        """Get slippage multiplier for market condition."""
        multipliers = {
            MarketCondition.NORMAL: 1.0,
            MarketCondition.VOLATILE: 2.0,
            MarketCondition.LOW_LIQUIDITY: 3.0,
            MarketCondition.HIGH_VOLUME: 0.8,
            MarketCondition.FLASH_CRASH: 5.0
        }
        return multipliers.get(condition, 1.0)
    
    def _calculate_volume_impact(self, order_quantity: float, market_volume: float) -> float:
        """Calculate volume impact on slippage."""
        if market_volume == 0:
            return 0
        
        order_size_ratio = order_quantity / market_volume
        
        # Volume impact is non-linear
        impact = self.config.volume_impact_factor * (order_size_ratio ** 1.5)
        
        return impact * 100  # Convert to basis points
    
    def _get_order_type_multiplier(self, order_type: OrderType) -> float:
        """Get slippage multiplier for order type."""
        multipliers = {
            OrderType.MARKET: 1.0,
            OrderType.LIMIT: 0.5,  # Less slippage if filled
            OrderType.STOP_MARKET: 1.2,
            OrderType.STOP_LIMIT: 0.6,
            OrderType.IOC: 0.9,
            OrderType.FOK: 0.8
        }
        return multipliers.get(order_type, 1.0)


class TransactionCostCalculator:
    """
    Calculates realistic transaction costs including fees, slippage, and market impact.
    """
    
    def __init__(self, config: TransactionCostModel = None):
        self.config = config or TransactionCostModel()
        self.slippage_model = SlippageModel(config)
        self.logger = logging.getLogger(__name__)
    
    def calculate_total_cost(self, order: Order, execution_price: float,
                            orderbook: Optional[Dict] = None,
                            market_data: Optional[Dict] = None) -> Fill:
        """
        Calculate total transaction cost including fees and slippage.
        """
        # Calculate slippage
        slippage_bps, market_condition = self.slippage_model.calculate_slippage(
            order, orderbook, market_data
        )
        
        # Calculate execution price with slippage
        if order.side == OrderSide.BUY:
            filled_price = execution_price * (1 + slippage_bps / 10000)
        else:
            filled_price = execution_price * (1 - slippage_bps / 10000)
        
        # Calculate commission
        commission = self._calculate_commission(order, filled_price)
        
        # Calculate total cost
        trade_value = order.quantity * filled_price
        total_cost = trade_value + commission
        
        # Ensure minimum fee
        if commission < self.config.minimum_fee:
            commission = self.config.minimum_fee
            total_cost = trade_value + commission
        
        return Fill(
            order=order,
            filled_quantity=order.quantity,
            fill_price=filled_price,
            slippage_bps=slippage_bps,
            commission=commission,
            total_cost=total_cost,
            timestamp=datetime.now(),
            market_condition=market_condition
        )
    
    def _calculate_commission(self, order: Order, execution_price: float) -> float:
        """Calculate commission based on order type and value."""
        trade_value = order.quantity * execution_price
        
        # Determine if maker or taker
        is_maker = order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]
        
        if is_maker:
            fee_rate = self.config.maker_fee_bps / 10000
        else:
            fee_rate = self.config.taker_fee_bps / 10000
        
        commission = trade_value * fee_rate
        
        return max(commission, self.config.minimum_fee)
    
    def calculate_spread_cost(self, order: Order, bid: float, ask: float) -> float:
        """Calculate cost of crossing the spread."""
        if order.side == OrderSide.BUY:
            execution_price = ask
        else:
            execution_price = bid
        
        mid_price = (bid + ask) / 2
        spread_bps = abs(execution_price - mid_price) / mid_price * 10000
        
        return spread_bps


class MarketImpactModel:
    """
    Models market impact of large orders.
    Based on Almgren-Chriss model and Kyle's lambda.
    """
    
    def __init__(self, config: TransactionCostModel = None):
        self.config = config or TransactionCostModel()
        self.logger = logging.getLogger(__name__)
    
    def calculate_permanent_impact(self, order_quantity: float, 
                                  market_volume: float,
                                  volatility: float) -> float:
        """
        Calculate permanent market impact (price displacement that persists).
        Based on Kyle's lambda model.
        """
        if market_volume == 0:
            return 0
        
        # Kyle's lambda: impact proportional to order size / market volume
        lambda_param = volatility / (market_volume * 0.01)
        permanent_impact = lambda_param * order_quantity
        
        return permanent_impact
    
    def calculate_temporary_impact(self, order_quantity: float,
                                  market_volume: float,
                                  execution_time: float = 1.0) -> float:
        """
        Calculate temporary market impact (cost due to liquidity consumption).
        Reverts after order execution.
        """
        if market_volume == 0:
            return 0
        
        # Temporary impact is higher for larger orders
        temporary_impact = (order_quantity / market_volume) ** 0.5
        
        # Adjust for execution time (longer execution = less impact)
        time_decay = 1 / (execution_time ** 0.5)
        
        return temporary_impact * time_decay
    
    def calculate_optimal_execution(self, total_quantity: float,
                                   market_volume: float,
                                   volatility: float,
                                   time_horizon: float) -> List[float]:
        """
        Calculate optimal execution schedule using Almgren-Chriss model.
        Returns list of trade sizes for each time slice.
        """
        # Simplified Almgren-Chriss: execute in equal slices
        num_slices = max(1, int(time_horizon))
        slice_size = total_quantity / num_slices
        
        return [slice_size] * num_slices


class RealisticExecutionSimulator:
    """
    Combines slippage, transaction costs, and market impact for realistic execution simulation.
    """
    
    def __init__(self, config: TransactionCostModel = None):
        self.config = config or TransactionCostModel()
        self.cost_calculator = TransactionCostCalculator(config)
        self.market_impact = MarketImpactModel(config)
        self.logger = logging.getLogger(__name__)
    
    def simulate_execution(self, order: Order, market_data: Dict,
                          orderbook: Optional[Dict] = None) -> Fill:
        """
        Simulate realistic order execution.
        """
        # Get execution price from market data
        if order.side == OrderSide.BUY:
            execution_price = market_data.get('ask', market_data.get('close', 0))
        else:
            execution_price = market_data.get('bid', market_data.get('close', 0))
        if not np.isfinite(execution_price) or execution_price <= 0:
            raise ValueError("Execution requires a finite positive market price")
        if not np.isfinite(order.quantity) or order.quantity <= 0:
            raise ValueError("Execution requires a finite positive order quantity")
        
        # Calculate total cost with slippage and fees
        fill = self.cost_calculator.calculate_total_cost(
            order, execution_price, orderbook, market_data
        )
        
        # Adjust for market impact if order is large
        order_size = order.quantity
        market_volume = market_data.get('volume', 1)
        volatility = market_data.get('volatility', 0.01)
        
        if order_size > market_volume * 0.01:  # If order is >1% of volume
            permanent_impact = self.market_impact.calculate_permanent_impact(
                order_size, market_volume, volatility
            )
            
            # Adjust fill price for permanent impact
            if order.side == OrderSide.BUY:
                fill.fill_price += permanent_impact
            else:
                fill.fill_price -= permanent_impact
            
            fill.total_cost = fill.filled_quantity * fill.fill_price + fill.commission
        
        return fill
    
    def simulate_large_order(self, order: Order, market_data: Dict,
                           time_horizon: float = 1.0) -> List[Fill]:
        """
        Simulate execution of a large order over time using optimal slicing.
        """
        market_volume = market_data.get('volume', 1)
        volatility = market_data.get('volatility', 0.01)
        
        # Calculate optimal execution schedule
        slice_sizes = self.market_impact.calculate_optimal_execution(
            order.quantity, market_volume, volatility, time_horizon
        )
        
        fills = []
        accumulated_quantity = 0
        
        for i, slice_size in enumerate(slice_sizes):
            if accumulated_quantity >= order.quantity:
                break
            
            # Create slice order
            slice_order = Order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=min(slice_size, order.quantity - accumulated_quantity),
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                timestamp=datetime.now()
            )
            
            # Simulate execution
            fill = self.simulate_execution(slice_order, market_data)
            fills.append(fill)
            
            accumulated_quantity += fill.filled_quantity
        
        return fills
    
    def get_statistics(self, fills: List[Fill]) -> Dict[str, float]:
        """Get execution statistics."""
        if not fills:
            return {}
        
        total_slippage = sum(fill.slippage_bps for fill in fills)
        total_commission = sum(fill.commission for fill in fills)
        total_cost = sum(fill.total_cost for fill in fills)
        total_quantity = sum(fill.filled_quantity for fill in fills)
        
        avg_slippage = total_slippage / len(fills)
        avg_commission = total_commission / len(fills)
        
        return {
            'total_fills': len(fills),
            'total_quantity': total_quantity,
            'total_cost': total_cost,
            'total_commission': total_commission,
            'total_slippage_bps': total_slippage,
            'avg_slippage_bps': avg_slippage,
            'avg_commission': avg_commission,
            'cost_per_unit': total_cost / total_quantity if total_quantity > 0 else 0
        }
