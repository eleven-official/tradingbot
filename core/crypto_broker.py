"""
Crypto/Futures Broker Integration for Australian Markets
Supports Binance, Bybit, and other major crypto exchanges
"""
import logging
import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class Exchange(Enum):
    """Supported cryptocurrency exchanges."""
    BINANCE = "binance"
    BYBIT = "bybit"
    KRAKEN = "kraken"


class OrderSide(Enum):
    """Order sides."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"
    TRAILING_STOP = "trailing_stop"
    OCO = "oco"  # One-Cancels-the-Other


@dataclass
class Order:
    """Represents a trading order."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    client_order_id: Optional[str] = None
    reduce_only: bool = False  # For closing positions
    close_on_trigger: bool = False  # For conditional orders
    activation_price: Optional[float] = None  # For trigger orders
    callback_rate: Optional[float] = None  # For trailing stop
    callback_price: Optional[float] = None  # For trailing stop


@dataclass
class Position:
    """Represents a trading position."""
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int


@dataclass
class AccountBalance:
    """Account balance information."""
    total_balance: float
    available_balance: float
    unrealized_pnl: float
    currency: str = "AUD"


class CryptoBroker:
    """
    Generic crypto/futures broker interface for Australian markets.
    Supports multiple exchanges with unified API.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.broker_config = config.get('crypto_broker', {})
        
        # Configuration
        try:
            self.exchange = Exchange(self.broker_config.get('exchange', 'binance'))
        except ValueError:
            self.exchange = Exchange.BINANCE  # Default to binance if invalid
            
        self.api_key = self.broker_config.get('api_key', '')
        self.api_secret = self.broker_config.get('api_secret', '')
        self.testnet = self.broker_config.get('testnet', True)
        self.base_currency = self.broker_config.get('base_currency', 'AUD')
        
        # Multi-exchange support
        self.exchanges_config = config.get('exchanges', {})
        self.active_exchanges = {}
        
        # Initialize primary exchange
        self.base_url = self._get_base_url()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
        logging.info(f"CryptoBroker initialized for {self.exchange.value} "
                    f"({'testnet' if self.testnet else 'mainnet'})")
    
    def _get_base_url(self) -> str:
        """Get the appropriate base URL for the exchange."""
        if self.exchange == Exchange.BINANCE:
            if self.testnet:
                return "https://testnet.binance.vision"
            return "https://api.binance.com"
        elif self.exchange == Exchange.BYBIT:
            if self.testnet:
                return "https://api-testnet.bybit.com"
            return "https://api.bybit.com"
        elif self.exchange == Exchange.KRAKEN:
            return "https://api.kraken.com"
        else:
            raise ValueError(f"Unsupported exchange: {self.exchange}")
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC signature for API requests."""
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                     signed: bool = False) -> Dict[str, Any]:
        """Make an HTTP request to the exchange API."""
        import requests
        
        # Rate limiting
        current_time = time.time()
        if current_time - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval - (current_time - self.last_request_time))
        self.last_request_time = time.time()
        
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        if signed:
            if params is None:
                params = {}
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=params, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, json=params, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed: {e}")
            raise
    
    def get_account_balance(self) -> AccountBalance:
        """Get account balance information."""
        try:
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v2/balance', signed=True)
                
                total_balance = 0.0
                available_balance = 0.0
                unrealized_pnl = 0.0
                
                for asset in response:
                    if asset['asset'] == 'USDT':  # Assuming USDT as base
                        total_balance = float(asset['balance'])
                        available_balance = float(asset['availableBalance'])
                        unrealized_pnl = float(asset['crossUnPnl'])
                
                return AccountBalance(
                    total_balance=total_balance,
                    available_balance=available_balance,
                    unrealized_pnl=unrealized_pnl,
                    currency=self.base_currency
                )
            
            # Add other exchanges as needed
            return AccountBalance(total_balance=0.0, available_balance=0.0, unrealized_pnl=0.0)
            
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return AccountBalance(total_balance=0.0, available_balance=0.0, unrealized_pnl=0.0)
    
    def get_positions(self) -> List[Position]:
        """Get current open positions."""
        try:
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v2/positionRisk', signed=True)
                
                positions = []
                for pos in response:
                    if float(pos['positionAmt']) != 0:  # Only open positions
                        position = Position(
                            symbol=pos['symbol'],
                            side='long' if float(pos['positionAmt']) > 0 else 'short',
                            quantity=abs(float(pos['positionAmt'])),
                            entry_price=float(pos['entryPrice']),
                            current_price=float(pos['markPrice']),
                            unrealized_pnl=float(pos['unRealizedProfit']),
                            leverage=int(pos['leverage'])
                        )
                        positions.append(position)
                
                return positions
            
            return []
            
        except Exception as e:
            logging.error(f"Failed to get positions: {e}")
            return []
    
    def place_order(self, order: Order) -> Dict[str, Any]:
        """Place a trading order."""
        try:
            params = {
                'symbol': order.symbol,
                'side': order.side.value,
                'type': order.order_type.value,
                'quantity': order.quantity
            }
            
            if order.price:
                params['price'] = order.price
            
            if order.stop_price:
                params['stopPrice'] = order.stop_price
            
            if order.client_order_id:
                params['newClientOrderId'] = order.client_order_id
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('POST', '/fapi/v1/order', params=params, signed=True)
                logging.info(f"Order placed: {order.side.value} {order.quantity} {order.symbol}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to place order: {e}")
            raise
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('DELETE', '/fapi/v1/order', params=params, signed=True)
                logging.info(f"Order cancelled: {order_id} for {symbol}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to cancel order: {e}")
            raise
    
    def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Get the status of an order."""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/order', params=params, signed=True)
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to get order status: {e}")
            return {}
    
    def get_ticker_price(self, symbol: str) -> float:
        """Get current ticker price for a symbol."""
        try:
            params = {'symbol': symbol}
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/ticker/price', params=params)
                return float(response['price'])
            
            return 0.0
            
        except Exception as e:
            logging.error(f"Failed to get ticker price: {e}")
            return 0.0
    
    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """Get kline (candlestick) data."""
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/klines', params=params)
                return response
            
            return []
            
        except Exception as e:
            logging.error(f"Failed to get klines: {e}")
            return []
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol."""
        try:
            params = {
                'symbol': symbol,
                'leverage': leverage
            }
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('POST', '/fapi/v1/leverage', params=params, signed=True)
                logging.info(f"Leverage set to {leverage}x for {symbol}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to set leverage: {e}")
            raise
    
    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close the entire position for a symbol."""
        try:
            positions = self.get_positions()
            for position in positions:
                if position.symbol == symbol:
                    # Place opposite order to close position
                    close_order = Order(
                        symbol=symbol,
                        side=OrderSide.SELL if position.side == 'long' else OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=position.quantity,
                        reduce_only=True
                    )
                    return self.place_order(close_order)
            
            logging.warning(f"No open position found for {symbol}")
            return {}
            
        except Exception as e:
            logging.error(f"Failed to close position: {e}")
            raise
    
    def place_trailing_stop(self, symbol: str, quantity: float, callback_rate: float, 
                          activation_price: Optional[float] = None) -> Dict[str, Any]:
        """Place a trailing stop order."""
        try:
            params = {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'TRAILING_STOP_MARKET',
                'quantity': quantity,
                'callbackRate': callback_rate
            }
            
            if activation_price:
                params['activationPrice'] = activation_price
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('POST', '/fapi/v1/order', params=params, signed=True)
                logging.info(f"Trailing stop placed for {symbol} with callback rate {callback_rate}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to place trailing stop: {e}")
            raise
    
    def place_oco_order(self, symbol: str, side: OrderSide, quantity: float, 
                      price: float, stop_price: float, take_profit_price: float) -> Dict[str, Any]:
        """Place an OCO (One-Cancels-the-Other) order."""
        try:
            params = {
                'symbol': symbol,
                'side': side.value,
                'type': 'LIMIT',
                'quantity': quantity,
                'price': price,
                'stopPrice': stop_price,
                'takeProfitPrice': take_profit_price,
                'timeInForce': 'GTC'
            }
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('POST', '/fapi/v1/order/oco', params=params, signed=True)
                logging.info(f"OCO order placed for {symbol}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to place OCO order: {e}")
            raise
    
    def modify_order(self, symbol: str, order_id: str, new_quantity: Optional[float] = None,
                   new_price: Optional[float] = None) -> Dict[str, Any]:
        """Modify an existing order."""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            
            if new_quantity:
                params['quantity'] = new_quantity
            if new_price:
                params['price'] = new_price
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('PUT', '/fapi/v1/order', params=params, signed=True)
                logging.info(f"Order {order_id} modified for {symbol}")
                return response
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to modify order: {e}")
            raise
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders, optionally filtered by symbol."""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/openOrders', params=params, signed=True)
                return response
            
            return []
            
        except Exception as e:
            logging.error(f"Failed to get open orders: {e}")
            return []
    
    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Cancel all open orders, optionally filtered by symbol."""
        try:
            open_orders = self.get_open_orders(symbol)
            cancelled_count = 0
            
            for order in open_orders:
                try:
                    self.cancel_order(order['symbol'], order['orderId'])
                    cancelled_count += 1
                except Exception as e:
                    logging.error(f"Failed to cancel order {order['orderId']}: {e}")
            
            logging.info(f"Cancelled {cancelled_count} orders")
            return {'cancelled_count': cancelled_count}
            
        except Exception as e:
            logging.error(f"Failed to cancel all orders: {e}")
            raise
    
    def get_funding_rate(self, symbol: str) -> float:
        """Get the current funding rate for a symbol."""
        try:
            params = {'symbol': symbol}
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/premiumIndex', params=params)
                return float(response['lastFundingRate'])
            
            return 0.0
            
        except Exception as e:
            logging.error(f"Failed to get funding rate: {e}")
            return 0.0
    
    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24-hour ticker statistics."""
        try:
            params = {'symbol': symbol}
            
            if self.exchange == Exchange.BINANCE:
                response = self._make_request('GET', '/fapi/v1/ticker/24hr', params=params)
                return {
                    'price_change': float(response['priceChange']),
                    'price_change_percent': float(response['priceChangePercent']),
                    'high': float(response['highPrice']),
                    'low': float(response['lowPrice']),
                    'volume': float(response['volume'])
                }
            
            return {}
            
        except Exception as e:
            logging.error(f"Failed to get 24h ticker: {e}")
            return {}
    
    def calculate_position_size_risk(self, capital: float, risk_percent: float, 
                                     entry_price: float, stop_loss_price: float) -> float:
        """Calculate position size based on risk percentage."""
        try:
            risk_per_unit = abs(entry_price - stop_loss_price)
            if risk_per_unit == 0:
                return 0.0
            
            risk_amount = capital * (risk_percent / 100)
            position_size = risk_amount / risk_per_unit
            
            return position_size
            
        except Exception as e:
            logging.error(f"Failed to calculate position size: {e}")
            return 0.0


class AustralianCryptoBroker(CryptoBroker):
    """
    Australian-specific crypto broker with AUD support and local time zones.
    """
    
    def __init__(self, config: Dict[str, Any]):
        try:
            super().__init__(config)
        except Exception as e:
            logging.warning(f"Parent initialization had issues: {e}, using defaults")
            # Initialize with defaults if parent fails
            self.config = config
            self.broker_config = config.get('crypto_broker', {})
            self.exchange = Exchange.BINANCE
            self.api_key = ''
            self.api_secret = ''
            self.testnet = True
            self.base_currency = 'AUD'
            self.base_url = self._get_base_url()
            self.last_request_time = 0
            self.min_request_interval = 0.1
        
        self.timezone = "Australia/Sydney"
        self.australian_instruments = config.get('australian_instruments', {
            'BTC': 'BTCUSDT',
            'ETH': 'ETHUSDT',
            'XRP': 'XRPUSDT',
            'ADA': 'ADAUSDT',
            'SOL': 'SOLUSDT',
            'MATIC': 'MATICUSDT',
            'DOT': 'DOTUSDT'
        })
        
        logging.info("AustralianCryptoBroker initialized with AUD support")
    
    def get_australian_time(self) -> datetime:
        """Get current Australian Eastern Standard Time."""
        from datetime import timezone
        import pytz
        
        aus_tz = pytz.timezone(self.timezone)
        return datetime.now(aus_tz)
    
    def is_market_open(self) -> bool:
        """Check if the market is open (crypto markets are 24/7)."""
        # Crypto markets are always open, but we can implement trading hours
        # if we want to limit trading to specific Australian business hours
        return True
    
    def convert_to_aud(self, amount_usd: float) -> float:
        """Convert USD to AUD (simplified - in production, use live rates)."""
        # In production, integrate with a forex API for live rates
        aud_usd_rate = 1.5  # Example rate
        return amount_usd / aud_usd_rate
    
    def get_instrument_symbol(self, instrument: str) -> str:
        """Convert instrument name to exchange symbol."""
        return self.australian_instruments.get(instrument.upper(), instrument)
    
    def add_exchange(self, exchange_name: str, config: Dict[str, Any]):
        """Add additional exchange for multi-exchange trading."""
        try:
            exchange_enum = Exchange(exchange_name)
            # Create a new broker instance for the additional exchange
            # We avoid recursion by creating a minimal instance
            additional_broker = CryptoBroker.__new__(CryptoBroker)
            additional_broker.config = config
            additional_broker.broker_config = config.get('crypto_broker', {})
            additional_broker.exchange = exchange_enum
            additional_broker.api_key = additional_broker.broker_config.get('api_key', '')
            additional_broker.api_secret = additional_broker.broker_config.get('api_secret', '')
            additional_broker.testnet = additional_broker.broker_config.get('testnet', True)
            additional_broker.base_currency = additional_broker.broker_config.get('base_currency', 'AUD')
            additional_broker.base_url = additional_broker._get_base_url()
            additional_broker.last_request_time = 0
            additional_broker.min_request_interval = 0.1
            
            self.active_exchanges[exchange_name] = {
                'config': config,
                'client': additional_broker
            }
            logging.info(f"Added exchange: {exchange_name}")
        except Exception as e:
            logging.error(f"Failed to add exchange {exchange_name}: {e}")
    
    def get_best_price(self, symbol: str) -> Dict[str, float]:
        """Get best prices across all active exchanges."""
        prices = {self.exchange.value: self.get_ticker_price(symbol)}
        
        for exchange_name, exchange_data in self.active_exchanges.items():
            try:
                price = exchange_data['client'].get_ticker_price(symbol)
                prices[exchange_name] = price
            except Exception as e:
                logging.error(f"Failed to get price from {exchange_name}: {e}")
        
        return prices
    
    def route_order(self, symbol: str, order: Order) -> Dict[str, Any]:
        """Route order to the best exchange based on price/liquidity."""
        prices = self.get_best_price(symbol)
        
        # Simple routing logic - choose exchange with best price
        # In production, consider fees, liquidity, and other factors
        best_exchange = min(prices, key=prices.get)
        
        if best_exchange == self.exchange.value:
            return self.place_order(order)
        else:
            return self.active_exchanges[best_exchange]['client'].place_order(order)