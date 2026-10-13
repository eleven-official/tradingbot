"""
Broker Factory - Create broker instances dynamically
Supports multiple brokers with unified interface
"""
from typing import Optional, Dict, Any
from loki.brokers.base import BaseBroker
from loki.brokers.alpaca_broker import AlpacaBrokerAdapter
from loki.brokers.interactive_brokers import InteractiveBrokersAdapter
from loki.brokers.binance_broker import BinanceBrokerAdapter
import logging

logger = logging.getLogger(__name__)


class BrokerFactory:
    """
    Factory for creating broker instances
    
    Usage:
        broker = BrokerFactory.create('alpaca', api_key='...', api_secret='...')
        async with broker:
            positions = await broker.get_positions()
    """
    
    _broker_registry: Dict[str, type] = {
        'alpaca': AlpacaBrokerAdapter,
        'interactive_brokers': InteractiveBrokersAdapter,
        'ib': InteractiveBrokersAdapter,  # Alias
        'binance': BinanceBrokerAdapter,
        # Add more brokers here
        # 'td_ameritrade': TDAmeritradeBrokerAdapter,
        # 'coinbase': CoinbaseBrokerAdapter,
    }
    
    @classmethod
    def create(
        cls,
        broker_name: str,
        api_key: str,
        api_secret: str,
        paper: bool = True,
        **kwargs
    ) -> BaseBroker:
        """
        Create a broker instance
        
        Args:
            broker_name: Name of broker ('alpaca', 'interactive_brokers', 'binance')
            api_key: API key
            api_secret: API secret
            paper: Use paper trading (default True)
            **kwargs: Additional broker-specific parameters
        
        Returns:
            BaseBroker instance
        
        Raises:
            ValueError: If broker not supported
        """
        broker_name = broker_name.lower()
        
        if broker_name not in cls._broker_registry:
            available = ', '.join(cls._broker_registry.keys())
            raise ValueError(
                f"Unsupported broker: {broker_name}. "
                f"Available brokers: {available}"
            )
        
        broker_class = cls._broker_registry[broker_name]
        logger.info(f"Creating {broker_name} broker instance (paper={paper})")
        
        return broker_class(
            api_key=api_key,
            api_secret=api_secret,
            paper=paper,
            **kwargs
        )
    
    @classmethod
    def register_broker(cls, name: str, broker_class: type):
        """
        Register a custom broker implementation
        
        Args:
            name: Broker name
            broker_class: Broker class (must inherit from BaseBroker)
        """
        if not issubclass(broker_class, BaseBroker):
            raise TypeError("Broker class must inherit from BaseBroker")
        
        cls._broker_registry[name.lower()] = broker_class
        logger.info(f"Registered broker: {name}")
    
    @classmethod
    def list_brokers(cls) -> list:
        """List all supported brokers"""
        return list(cls._broker_registry.keys())


# Example usage
if __name__ == "__main__":
    # List available brokers
    print("Available brokers:", BrokerFactory.list_brokers())
    
    # Create broker instance
    broker = BrokerFactory.create(
        'alpaca',
        api_key='your_api_key',
        api_secret='your_api_secret',
        paper=True
    )
    
    print(f"Created broker: {broker.__class__.__name__}")
    print(f"Capabilities: {broker.capabilities}")
