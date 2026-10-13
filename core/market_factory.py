"""
Market abstraction layer for multi-market support.
Provides a unified interface for different market types (equity, forex, futures).
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from enum import Enum
import logging


class MarketType(Enum):
    """Supported market types."""
    EQUITY = "equity"      # Indian equities via Zerodha
    FOREX = "forex"         # Forex via OANDA/FXCM
    FUTURES = "futures"     # Futures via Interactive Brokers
    CRYPTO = "crypto"       # Crypto via various exchanges


class MarketAdapter(ABC):
    """Abstract base class for market-specific adapters."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the market data provider."""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from the market data provider."""
        pass
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol."""
        pass
    
    @abstractmethod
    def get_historical_data(self, symbol: str, from_date: str, to_date: str, 
                           interval: str) -> List[Dict[str, Any]]:
        """Get historical data for a symbol."""
        pass
    
    @abstractmethod
    def place_order(self, order_params: Dict[str, Any]) -> str:
        """Place an order and return order ID."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        pass
    
    @abstractmethod
    def get_account_balance(self) -> Dict[str, Any]:
        """Get account balance and margin information."""
        pass
    
    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol is supported by this market."""
        pass


class ZerodhaEquityAdapter(MarketAdapter):
    """Adapter for Indian equity markets via Zerodha Kite."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.kite = None
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(
                api_key=config.get('api_key'),
                timeout=config.get('timeout', 120)
            )
            if config.get('access_token'):
                self.kite.set_access_token(config['access_token'])
                self.connected = True
        except ImportError:
            logging.warning("kiteconnect not installed - Zerodha adapter unavailable")
    
    def connect(self) -> bool:
        """Connect to Zerodha Kite."""
        if not self.kite:
            return False
        
        try:
            if not self.connected and self.config.get('access_token'):
                self.kite.set_access_token(self.config['access_token'])
                self.kite.profile()  # Test connection
                self.connected = True
                return True
            return self.connected
        except Exception as e:
            logging.error(f"Zerodha connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Zerodha."""
        self.connected = False
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get quote from Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        return self.kite.quote(symbol)
    
    def get_historical_data(self, symbol: str, from_date: str, to_date: str, 
                           interval: str) -> List[Dict[str, Any]]:
        """Get historical data from Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        return self.kite.historical_data(symbol, from_date, to_date, interval)
    
    def place_order(self, order_params: Dict[str, Any]) -> str:
        """Place order via Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        return self.kite.place_order(**order_params)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order via Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        try:
            self.kite.cancel_order(order_id)
            return True
        except Exception as e:
            logging.error(f"Order cancellation failed: {e}")
            return False
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get positions from Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        return self.kite.positions()
    
    def get_account_balance(self) -> Dict[str, Any]:
        """Get account balance from Zerodha."""
        if not self.connected:
            raise RuntimeError("Not connected to Zerodha")
        return self.kite.margins()
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate Zerodha symbol."""
        # Basic validation - can be enhanced with instrument lookup
        return bool(symbol and len(symbol) > 0)


class OANDAForexAdapter(MarketAdapter):
    """Adapter for Forex markets via OANDA API."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = None
        try:
            import v20
            self.client = v20.Context(
                config.get('hostname', 'api-fxpractice.oanda.com'),
                port=config.get('port', 443),
                token=config.get('api_token'),
                datetime_format='RFC3339'
            )
            self.connected = True
        except ImportError:
            logging.warning("v20 library not installed - OANDA adapter unavailable")
    
    def connect(self) -> bool:
        """Connect to OANDA."""
        if not self.client:
            return False
        
        try:
            # Test connection
            self.client.account.get(config.get('account_id'))
            self.connected = True
            return True
        except Exception as e:
            logging.error(f"OANDA connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from OANDA."""
        self.connected = False
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get forex quote from OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        response = self.client.pricing.get(
            config.get('account_id'),
            instruments=symbol
        )
        
        if response.status != 200:
            raise RuntimeError(f"OANDA API error: {response.status}")
        
        prices = response.body['prices']
        if not prices:
            raise RuntimeError(f"No price data for {symbol}")
        
        price = prices[0]
        return {
            'symbol': symbol,
            'bid': float(price['bids'][0]['price']),
            'ask': float(price['asks'][0]['price']),
            'spread': float(price['asks'][0]['price']) - float(price['bids'][0]['price']),
            'timestamp': price['time']
        }
    
    def get_historical_data(self, symbol: str, from_date: str, to_date: str, 
                           interval: str) -> List[Dict[str, Any]]:
        """Get historical forex data from OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        # Map interval to OANDA granularity
        granularity_map = {
            'minute': 'M1',
            '5minute': 'M5',
            '15minute': 'M15',
            'hour': 'H1',
            'day': 'D'
        }
        granularity = granularity_map.get(interval, 'M5')
        
        response = self.client.instrument.candles(
            symbol,
            granularity=granularity,
            fromTime=from_date,
            toTime=to_date
        )
        
        if response.status != 200:
            raise RuntimeError(f"OANDA API error: {response.status}")
        
        candles = response.body['candles']
        return [
            {
                'date': candle['time'],
                'open': float(candle['mid']['o']),
                'high': float(candle['mid']['h']),
                'low': float(candle['mid']['l']),
                'close': float(candle['mid']['c']),
                'volume': int(candle['volume'])
            }
            for candle in candles
        ]
    
    def place_order(self, order_params: Dict[str, Any]) -> str:
        """Place forex order via OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        response = self.client.order.create(
            config.get('account_id'),
            order=order_params
        )
        
        if response.status != 201:
            raise RuntimeError(f"Order placement failed: {response.status}")
        
        return response.body['orderCreateTransaction']['id']
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel forex order via OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        response = self.client.order.cancel(config.get('account_id'), order_id)
        return response.status == 200
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get forex positions from OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        response = self.client.trade.list_open(config.get('account_id'))
        if response.status != 200:
            raise RuntimeError(f"Failed to get positions: {response.status}")
        
        return response.body['trades']
    
    def get_account_balance(self) -> Dict[str, Any]:
        """Get forex account balance from OANDA."""
        if not self.connected:
            raise RuntimeError("Not connected to OANDA")
        
        response = self.client.account.get(config.get('account_id'))
        if response.status != 200:
            raise RuntimeError(f"Failed to get account info: {response.status}")
        
        account = response.body['account']
        return {
            'balance': float(account['balance']),
            'margin_available': float(account['marginAvailable']),
            'margin_used': float(account['marginUsed']),
            'currency': account['currency']
        }
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate forex symbol format."""
        # OANDA uses format like "EUR_USD"
        return bool(symbol and '_' in symbol)


class IBFuturesAdapter(MarketAdapter):
    """Adapter for Futures markets via Interactive Brokers."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = None
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
            # IB API requires more complex setup - placeholder
            logging.warning("IB adapter requires additional setup")
        except ImportError:
            logging.warning("ibapi library not installed - IB adapter unavailable")
    
    def connect(self) -> bool:
        """Connect to Interactive Brokers."""
        # IB API connection requires complex async setup
        logging.warning("IB adapter connection not fully implemented")
        return False
    
    def disconnect(self):
        """Disconnect from IB."""
        self.connected = False
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get futures quote from IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def get_historical_data(self, symbol: str, from_date: str, to_date: str, 
                           interval: str) -> List[Dict[str, Any]]:
        """Get historical futures data from IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def place_order(self, order_params: Dict[str, Any]) -> str:
        """Place futures order via IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel futures order via IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get futures positions from IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def get_account_balance(self) -> Dict[str, Any]:
        """Get futures account balance from IB."""
        raise NotImplementedError("IB adapter not fully implemented")
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate futures symbol."""
        return bool(symbol)


class MarketFactory:
    """Factory for creating market adapters based on market type."""
    
    @staticmethod
    def create_adapter(market_type: MarketType, config: Dict[str, Any]) -> MarketAdapter:
        """Create appropriate market adapter."""
        adapters = {
            MarketType.EQUITY: ZerodhaEquityAdapter,
            MarketType.FOREX: OANDAForexAdapter,
            MarketType.FUTURES: IBFuturesAdapter,
            MarketType.CRYPTO: None  # TODO: Implement crypto adapter
        }
        
        adapter_class = adapters.get(market_type)
        if not adapter_class:
            raise ValueError(f"No adapter available for market type: {market_type}")
        
        return adapter_class(config)
    
    @staticmethod
    def get_supported_markets() -> List[MarketType]:
        """Get list of supported market types."""
        return [MarketType.EQUITY, MarketType.FOREX, MarketType.FUTURES]