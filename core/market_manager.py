"""
Unified market manager for multi-market trading operations.
Coordinates between different market adapters and provides a unified interface.
"""
import logging
from typing import Dict, Any, List, Optional
from core.market_factory import MarketFactory, MarketType, MarketAdapter
from core.tradingview_bridge import TradingViewBridge


class MarketManager:
    """Manages multiple market adapters and provides unified trading interface."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapters: Dict[MarketType, MarketAdapter] = {}
        self.primary_market = MarketType(config.get('markets', {}).get('primary_market', 'equity'))
        self.tradingview_bridge = None
        
        # Initialize TradingView bridge if enabled
        if config.get('tradingview', {}).get('enabled', False):
            self.tradingview_bridge = TradingViewBridge(config)
        
        # Initialize enabled market adapters
        self._initialize_adapters()
    
    def _initialize_adapters(self):
        """Initialize enabled market adapters."""
        enabled_markets = self.config.get('markets', {}).get('enabled_markets', [])
        
        for market_name in enabled_markets:
            try:
                market_type = MarketType(market_name)
                market_config = self.config.get('markets', {}).get(market_name, {})
                
                if market_config.get('enabled', True):
                    adapter = MarketFactory.create_adapter(market_type, market_config)
                    self.adapters[market_type] = adapter
                    logging.info(f"Initialized {market_name} adapter")
            except ValueError as e:
                logging.warning(f"Unknown market type: {market_name}")
            except Exception as e:
                logging.error(f"Failed to initialize {market_name} adapter: {e}")
    
    def connect_all(self) -> bool:
        """Connect to all enabled markets."""
        all_connected = True
        for market_type, adapter in self.adapters.items():
            try:
                if adapter.connect():
                    logging.info(f"Connected to {market_type.value}")
                else:
                    logging.warning(f"Failed to connect to {market_type.value}")
                    all_connected = False
            except Exception as e:
                logging.error(f"Error connecting to {market_type.value}: {e}")
                all_connected = False
        
        return all_connected
    
    def disconnect_all(self):
        """Disconnect from all markets."""
        for market_type, adapter in self.adapters.items():
            try:
                adapter.disconnect()
                logging.info(f"Disconnected from {market_type.value}")
            except Exception as e:
                logging.error(f"Error disconnecting from {market_type.value}: {e}")
    
    def get_adapter(self, market_type: MarketType) -> Optional[MarketAdapter]:
        """Get adapter for specific market type."""
        return self.adapters.get(market_type)
    
    def get_primary_adapter(self) -> Optional[MarketAdapter]:
        """Get primary market adapter."""
        return self.adapters.get(self.primary_market)
    
    def get_quote(self, symbol: str, market_type: Optional[MarketType] = None) -> Dict[str, Any]:
        """Get quote for symbol from specified market or primary market."""
        adapter = self._get_adapter_for_symbol(symbol, market_type)
        if not adapter:
            raise RuntimeError(f"No adapter available for symbol: {symbol}")
        
        return adapter.get_quote(symbol)
    
    def get_historical_data(self, symbol: str, from_date: str, to_date: str, 
                          interval: str, market_type: Optional[MarketType] = None) -> List[Dict[str, Any]]:
        """Get historical data for symbol."""
        adapter = self._get_adapter_for_symbol(symbol, market_type)
        if not adapter:
            raise RuntimeError(f"No adapter available for symbol: {symbol}")
        
        return adapter.get_historical_data(symbol, from_date, to_date, interval)
    
    def place_order(self, order_params: Dict[str, Any], 
                   market_type: Optional[MarketType] = None) -> str:
        """Place order on specified market or primary market."""
        adapter = self._get_adapter_for_order(order_params, market_type)
        if not adapter:
            raise RuntimeError(f"No adapter available for order")
        
        return adapter.place_order(order_params)
    
    def cancel_order(self, order_id: str, market_type: Optional[MarketType] = None) -> bool:
        """Cancel order on specified market."""
        adapter = market_type and self.adapters.get(market_type)
        if not adapter:
            # Try to cancel on all markets
            for adapter in self.adapters.values():
                try:
                    if adapter.cancel_order(order_id):
                        return True
                except Exception:
                    continue
            return False
        
        return adapter.cancel_order(order_id)
    
    def get_positions(self, market_type: Optional[MarketType] = None) -> List[Dict[str, Any]]:
        """Get positions from specified market or all markets."""
        if market_type:
            adapter = self.adapters.get(market_type)
            if adapter:
                return adapter.get_positions()
            return []
        
        # Get positions from all markets
        all_positions = []
        for adapter in self.adapters.values():
            try:
                positions = adapter.get_positions()
                all_positions.extend(positions)
            except Exception as e:
                logging.error(f"Error getting positions: {e}")
        
        return all_positions
    
    def get_account_balance(self, market_type: Optional[MarketType] = None) -> Dict[str, Any]:
        """Get account balance from specified market or primary market."""
        adapter = market_type and self.adapters.get(market_type) or self.get_primary_adapter()
        if not adapter:
            raise RuntimeError("No adapter available")
        
        return adapter.get_account_balance()
    
    def _get_adapter_for_symbol(self, symbol: str, market_type: Optional[MarketType] = None) -> Optional[MarketAdapter]:
        """Determine appropriate adapter for a symbol."""
        if market_type:
            return self.adapters.get(market_type)
        
        # Auto-detect market based on symbol format
        if '_' in symbol:  # Forex format (EUR_USD)
            return self.adapters.get(MarketType.FOREX)
        elif symbol.endswith('.NS') or symbol.endswith('.BO'):  # Indian stocks
            return self.adapters.get(MarketType.EQUITY)
        else:
            # Default to primary market
            return self.get_primary_adapter()
    
    def _get_adapter_for_order(self, order_params: Dict[str, Any], 
                               market_type: Optional[MarketType] = None) -> Optional[MarketAdapter]:
        """Determine appropriate adapter for an order."""
        if market_type:
            return self.adapters.get(market_type)
        
        # Check if order specifies market
        if 'market_type' in order_params:
            try:
                return self.adapters.get(MarketType(order_params['market_type']))
            except ValueError:
                pass
        
        # Default to primary market
        return self.get_primary_adapter()
    
    def start_tradingview_bridge(self):
        """Start TradingView webhook bridge."""
        if self.tradingview_bridge:
            self.tradingview_bridge.start()
            logging.info("TradingView bridge started")
    
    def stop_tradingview_bridge(self):
        """Stop TradingView webhook bridge."""
        if self.tradingview_bridge:
            self.tradingview_bridge.stop()
            logging.info("TradingView bridge stopped")
    
    def process_tradingview_alerts(self):
        """Process queued TradingView alerts."""
        if not self.tradingview_bridge:
            return []
        
        processed_alerts = []
        while True:
            alert = self.tradingview_bridge.get_next_alert(timeout=0.1)
            if not alert:
                break
            
            try:
                # Process alert (placeholder - implement actual trading logic)
                logging.info(f"Processing TradingView alert: {alert}")
                processed_alerts.append(alert)
            except Exception as e:
                logging.error(f"Error processing alert: {e}")
        
        return processed_alerts
    
    def get_supported_markets(self) -> List[str]:
        """Get list of supported markets."""
        return [market_type.value for market_type in self.adapters.keys()]
    
    def get_market_status(self) -> Dict[str, Any]:
        """Get status of all markets."""
        status = {
            'primary_market': self.primary_market.value,
            'supported_markets': self.get_supported_markets(),
            'adapters': {}
        }
        
        for market_type, adapter in self.adapters.items():
            status['adapters'][market_type.value] = {
                'connected': adapter.connected,
                'type': type(adapter).__name__
            }
        
        if self.tradingview_bridge:
            status['tradingview'] = {
                'enabled': True,
                'running': self.tradingview_bridge.running,
                'alerts_queued': len(self.tradingview_bridge.alert_queue)
            }
        
        return status