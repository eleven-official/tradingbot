"""
Alpaca Broker Integration
Connects to Alpaca for stock and crypto trading
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

try:
    import alpaca_trade_api as tradeapi
    from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    tradeapi = None
    # Try to import without submodules for basic check
    try:
        import alpaca_trade_api
        ALPACA_AVAILABLE = True
        tradeapi = alpaca_trade_api
    except ImportError:
        ALPACA_AVAILABLE = False
        tradeapi = None


class AccountType(Enum):
    """Account types."""
    PAPER = "paper"
    LIVE = "live"


@dataclass
class AlpacaConfig:
    """Alpaca configuration."""
    api_key: str
    api_secret: str
    account_type: AccountType = AccountType.PAPER
    base_url: str = "https://paper-api.alpaca.markets"  # Paper trading URL


@dataclass
class AlpacaPosition:
    """Alpaca position."""
    symbol: str
    qty: int
    side: str
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float
    market_value: float


@dataclass
class AlpacaOrder:
    """Alpaca order."""
    id: str
    symbol: str
    side: str
    type: str
    qty: int
    filled_qty: int
    filled_avg_price: float
    status: str
    created_at: datetime


class AlpacaBroker:
    """
    Alpaca broker integration for stocks and crypto.
    """
    
    def __init__(self, config: AlpacaConfig):
        self.config = config
        self.api = None
        self.is_connected = False
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize Alpaca connection."""
        if not ALPACA_AVAILABLE:
            self.logger.error("alpaca-trade-api not installed. Install with: pip install alpaca-trade-api")
            return False
        
        try:
            # Try to use tradeapi.REST first
            if hasattr(tradeapi, 'REST'):
                self.api = tradeapi.REST(
                    key_id=self.config.api_key,
                    secret_key=self.config.api_secret,
                    base_url=self.config.base_url
                )
            else:
                # Fallback to direct import
                from alpaca_trade_api import REST
                self.api = REST(
                    key_id=self.config.api_key,
                    secret_key=self.config.api_secret,
                    base_url=self.config.base_url
                )
            
            # Test connection
            account = self.api.get_account()
            self.is_connected = True
            
            self.logger.info(f"Connected to Alpaca ({self.config.account_type.value} account)")
            self.logger.info(f"Account ID: {account.id}")
            self.logger.info(f"Buying Power: ${float(account.buying_power):,.2f}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca: {e}")
            return False
    
    def get_account(self) -> Dict[str, any]:
        """Get account information."""
        if not self.is_connected:
            return {}
        
        try:
            account = self.api.get_account()
            
            return {
                'id': account.id,
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity),
                'long_market_value': float(account.long_market_value),
                'short_market_value': float(account.short_market_value),
                'initial_margin': float(account.initial_margin),
                'maintenance_margin': float(account.maintenance_margin),
                'daytrading_buying_power': float(account.daytrading_buying_power),
                'regt_buying_power': float(account.regt_buying_power)
            }
        except Exception as e:
            self.logger.error(f"Error getting account: {e}")
            return {}
    
    def get_positions(self) -> List[AlpacaPosition]:
        """Get current positions."""
        if not self.is_connected:
            return []
        
        try:
            positions = self.api.list_positions()
            
            alpaca_positions = []
            for pos in positions:
                position = AlpacaPosition(
                    symbol=pos.symbol,
                    qty=int(pos.qty),
                    side=pos.side,
                    avg_entry_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    unrealized_pl=float(pos.unrealized_pl),
                    unrealized_plpc=float(pos.unrealized_plpc),
                    market_value=float(pos.market_value)
                )
                alpaca_positions.append(position)
            
            return alpaca_positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_bars(self, symbol: str, timeframe: str = '1Day', 
                  limit: int = 100) -> Optional[pd.DataFrame]:
        """Get historical bars for a symbol."""
        if not self.is_connected:
            return None
        
        try:
            # Map timeframe strings to Alpaca TimeFrame
            timeframe_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame(5, TimeFrameUnit.Minute),
                '15Min': TimeFrame(15, TimeFrameUnit.Minute),
                '1Hour': TimeFrame.Hour,
                '1Day': TimeFrame.Day,
                '1Week': TimeFrame.Week
            }
            
            tf = timeframe_map.get(timeframe, TimeFrame.Day)
            
            bars = self.api.get_bars(symbol, tf, limit=limit)
            
            if not bars:
                return None
            
            # Convert to DataFrame
            data = []
            for bar in bars:
                data.append({
                    'timestamp': bar.t,
                    'open': bar.o,
                    'high': bar.h,
                    'low': bar.l,
                    'close': bar.c,
                    'volume': bar.v
                })
            
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error getting bars for {symbol}: {e}")
            return None
    
    def place_order(self, symbol: str, side: str, qty: int, 
                   order_type: str = 'market', limit_price: Optional[float] = None) -> Optional[AlpacaOrder]:
        """Place an order."""
        if not self.is_connected:
            return None
        
        try:
            if order_type == 'market':
                order = self.api.submit_order(
                    symbol=symbol,
                    side=side,
                    type='market',
                    qty=qty,
                    time_in_force='day'
                )
            elif order_type == 'limit' and limit_price:
                order = self.api.submit_order(
                    symbol=symbol,
                    side=side,
                    type='limit',
                    qty=qty,
                    limit_price=limit_price,
                    time_in_force='day'
                )
            else:
                self.logger.error(f"Invalid order type: {order_type}")
                return None
            
            alpaca_order = AlpacaOrder(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                qty=int(order.qty),
                filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
                status=order.status,
                created_at=order.created_at
            )
            
            self.logger.info(f"Order placed: {side} {qty} {symbol} ({order_type})")
            
            return alpaca_order
            
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self.is_connected:
            return False
        
        try:
            self.api.cancel_order(order_id)
            self.logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_orders(self, status: Optional[str] = None) -> List[AlpacaOrder]:
        """Get orders."""
        if not self.is_connected:
            return []
        
        try:
            orders = self.api.list_orders(status=status)
            
            alpaca_orders = []
            for order in orders:
                alpaca_order = AlpacaOrder(
                    id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    type=order.type,
                    qty=int(order.qty),
                    filled_qty=int(order.filled_qty) if order.filled_qty else 0,
                    filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
                    status=order.status,
                    created_at=order.created_at
                )
                alpaca_orders.append(alpaca_order)
            
            return alpaca_orders
            
        except Exception as e:
            self.logger.error(f"Error getting orders: {e}")
            return []
    
    def get_clock(self) -> Dict[str, any]:
        """Get market clock."""
        if not self.is_connected:
            return {}
        
        try:
            clock = self.api.get_clock()
            
            return {
                'timestamp': clock.timestamp,
                'is_open': clock.is_open,
                'next_open': clock.next_open,
                'next_close': clock.next_close
            }
        except Exception as e:
            self.logger.error(f"Error getting clock: {e}")
            return {}
    
    def get_assets(self) -> List[Dict[str, any]]:
        """Get available assets."""
        if not self.is_connected:
            return []
        
        try:
            assets = self.api.list_assets()
            
            asset_list = []
            for asset in assets:
                asset_list.append({
                    'symbol': asset.symbol,
                    'name': asset.name,
                    'exchange': asset.exchange,
                    'tradable': asset.tradable,
                    'marginable': asset.marginable,
                    'shortable': asset.shortable,
                    'easy_to_borrow': asset.easy_to_borrow
                })
            
            return asset_list
            
        except Exception as e:
            self.logger.error(f"Error getting assets: {e}")
            return []
    
    async def shutdown(self):
        """Shutdown the connection."""
        self.is_connected = False
        self.api = None
        self.logger.info("Alpaca connection closed")