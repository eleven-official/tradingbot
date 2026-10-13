"""Loki Market Data Module"""

from loki.data.real_market_data import (
    RealMarketDataProvider,
    get_market_data_provider,
    get_stock_data,
    get_multiple_stocks
)

__all__ = [
    'RealMarketDataProvider',
    'get_market_data_provider',
    'get_stock_data',
    'get_multiple_stocks'
]
