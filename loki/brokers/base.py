"""
Base broker interface for multi-broker support
Unified API for all brokers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class BrokerCapabilities:
    """Broker feature support"""

    supports_stocks: bool = True
    supports_options: bool = False
    supports_crypto: bool = False
    supports_forex: bool = False
    supports_futures: bool = False
    supports_fractional_shares: bool = False
    supports_extended_hours: bool = False
    supports_margin: bool = False
    supports_short_selling: bool = False
    min_order_value: float = 0
    max_positions: Optional[int] = None
    commission_per_trade: float = 0


@dataclass
class Position:
    """Position data"""

    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    market_value: float
    cost_basis: float


@dataclass
class Order:
    """Order data"""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    quantity: float
    filled_quantity: float
    price: Optional[float]
    filled_price: Optional[float]
    created_at: datetime
    updated_at: datetime


@dataclass
class AccountInfo:
    """Account information"""

    account_id: str
    cash_balance: float
    portfolio_value: float
    buying_power: float
    equity: float
    positions_value: float
    is_paper: bool = True


class BaseBroker(ABC):
    """
    Base broker interface - all brokers must implement this

    This provides a unified API across all supported brokers:
    - Alpaca
    - Interactive Brokers
    - TD Ameritrade
    - Binance
    - etc.
    """

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        self._connected = False

    @property
    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """Return broker capabilities"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to broker
        Returns True if successful
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from broker"""
        pass

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all open positions"""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol"""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Order:
        """Place a new order"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Get order status"""
        pass

    @abstractmethod
    async def get_orders(
        self, status: Optional[OrderStatus] = None, limit: int = 100
    ) -> List[Order]:
        """Get all orders"""
        pass

    @abstractmethod
    async def close_position(self, symbol: str, quantity: Optional[float] = None) -> Order:
        """Close a position"""
        pass

    @abstractmethod
    async def close_all_positions(self) -> List[Order]:
        """Close all open positions"""
        pass

    @abstractmethod
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price"""
        pass

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str = "1D"
    ) -> List[Dict[str, Any]]:
        """Get historical price data"""
        pass

    def is_connected(self) -> bool:
        """Check if broker is connected"""
        return self._connected

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
