"""
Async market data fetching for improved performance.
Provides asynchronous data fetching capabilities to reduce latency.
"""
import asyncio
import aiohttp
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class AsyncMarketDataFetcher:
    """Asynchronous market data fetcher for improved performance."""
    
    def __init__(self, config, kite_client):
        self.config = config
        self.kite = kite_client
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_ttl = 60  # seconds
    
    async def __aenter__(self):
        """Create aiohttp session on context entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session on context exit."""
        if self.session:
            await self.session.close()
    
    def _get_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate cache key for request."""
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{endpoint}?{param_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self.cache:
            return False
        
        cached_time = self.cache[cache_key].get('timestamp')
        if not cached_time:
            return False
        
        age = (datetime.now() - cached_time).total_seconds()
        return age < self.cache_ttl
    
    async def fetch_multiple_quotes(self, instruments: List[str]) -> Dict[str, Any]:
        """
        Fetch quotes for multiple instruments concurrently.
        
        Args:
            instruments: List of instrument symbols/tokens
            
        Returns:
            Dictionary mapping instruments to their quote data
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
        
        tasks = [self._fetch_single_quote(instrument) for instrument in instruments]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        quotes = {}
        for instrument, result in zip(instruments, results):
            if isinstance(result, Exception):
                logging.error(f"Failed to fetch quote for {instrument}: {result}")
                quotes[instrument] = None
            else:
                quotes[instrument] = result
        
        return quotes
    
    async def _fetch_single_quote(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Fetch quote for a single instrument."""
        cache_key = self._get_cache_key('quote', {'instrument': instrument})
        
        if self._is_cache_valid(cache_key):
            logging.debug(f"Cache hit for {instrument}")
            return self.cache[cache_key]['data']
        
        try:
            # Run synchronous Kite call in thread pool
            quote = await asyncio.to_thread(self.kite.quote, instrument)
            
            # Cache the result
            self.cache[cache_key] = {
                'data': quote,
                'timestamp': datetime.now()
            }
            
            return quote
            
        except Exception as e:
            logging.error(f"Error fetching quote for {instrument}: {e}")
            raise
    
    async def fetch_historical_data(self, instrument: str, from_date: datetime, 
                                    to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        """
        Fetch historical data for an instrument.
        
        Args:
            instrument: Instrument symbol/token
            from_date: Start date
            to_date: End date
            interval: Candle interval (minute, day, etc.)
            
        Returns:
            List of historical data points
        """
        cache_key = self._get_cache_key('historical', {
            'instrument': instrument,
            'from_date': from_date.isoformat(),
            'to_date': to_date.isoformat(),
            'interval': interval
        })
        
        if self._is_cache_valid(cache_key):
            logging.debug(f"Cache hit for historical data {instrument}")
            return self.cache[cache_key]['data']
        
        try:
            # Run synchronous Kite call in thread pool
            historical_data = await asyncio.to_thread(
                self.kite.historical_data,
                instrument,
                from_date,
                to_date,
                interval
            )
            
            # Cache the result
            self.cache[cache_key] = {
                'data': historical_data,
                'timestamp': datetime.now()
            }
            
            return historical_data
            
        except Exception as e:
            logging.error(f"Error fetching historical data for {instrument}: {e}")
            raise
    
    async def fetch_ohlc(self, instruments: List[str]) -> Dict[str, Any]:
        """
        Fetch OHLC data for multiple instruments concurrently.
        
        Args:
            instruments: List of instrument symbols/tokens
            
        Returns:
            Dictionary mapping instruments to OHLC data
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
        
        try:
            # Run synchronous Kite call in thread pool
            ohlc_data = await asyncio.to_thread(self.kite.ohlc, instruments)
            return ohlc_data
            
        except Exception as e:
            logging.error(f"Error fetching OHLC data: {e}")
            raise
    
    async def fetch_instruments(self, exchange: str) -> List[Dict[str, Any]]:
        """
        Fetch instruments list for an exchange.
        
        Args:
            exchange: Exchange name (NSE, NFO, etc.)
            
        Returns:
            List of instrument details
        """
        cache_key = self._get_cache_key('instruments', {'exchange': exchange})
        
        if self._is_cache_valid(cache_key):
            logging.debug(f"Cache hit for instruments {exchange}")
            return self.cache[cache_key]['data']
        
        try:
            # Run synchronous Kite call in thread pool
            instruments = await asyncio.to_thread(self.kite.instruments, exchange)
            
            # Cache the result (longer TTL for instruments)
            self.cache[cache_key] = {
                'data': instruments,
                'timestamp': datetime.now()
            }
            self.cache_ttl = 3600  # 1 hour for instruments
            
            return instruments
            
        except Exception as e:
            logging.error(f"Error fetching instruments for {exchange}: {e}")
            raise
    
    def clear_cache(self):
        """Clear the data cache."""
        self.cache.clear()
        logging.info("Cache cleared")
    
    def set_cache_ttl(self, ttl_seconds: int):
        """Set cache time-to-live in seconds."""
        self.cache_ttl = ttl_seconds
        logging.info(f"Cache TTL set to {ttl_seconds} seconds")


class PerformanceOptimizer:
    """Optimizes performance through various techniques."""
    
    def __init__(self, config):
        self.config = config
        self.enabled = config.get('performance', {}).get('enabled', True)
        self.async_enabled = config.get('performance', {}).get('async_operations', True)
    
    async def optimize_data_fetch(self, kite_client, symbols: List[str], 
                                  operation: str = 'quote') -> Dict[str, Any]:
        """
        Optimize data fetching using async operations.
        
        Args:
            kite_client: KiteConnect client
            symbols: List of symbols to fetch
            operation: Type of operation (quote, ohlc, etc.)
            
        Returns:
            Dictionary of results
        """
        if not self.enabled or not self.async_enabled:
            # Fallback to synchronous
            return self._sync_fetch(kite_client, symbols, operation)
        
        async with AsyncMarketDataFetcher(self.config, kite_client) as fetcher:
            if operation == 'quote':
                return await fetcher.fetch_multiple_quotes(symbols)
            elif operation == 'ohlc':
                return await fetcher.fetch_ohlc(symbols)
            else:
                logging.warning(f"Unknown operation: {operation}")
                return {}
    
    def _sync_fetch(self, kite_client, symbols: List[str], operation: str) -> Dict[str, Any]:
        """Synchronous fallback for data fetching."""
        results = {}
        try:
            if operation == 'quote':
                # Fetch quotes synchronously
                for symbol in symbols:
                    try:
                        results[symbol] = kite_client.quote(symbol)
                    except Exception as e:
                        logging.error(f"Error fetching {symbol}: {e}")
                        results[symbol] = None
            elif operation == 'ohlc':
                # Fetch OHLC synchronously
                results = kite_client.ohlc(symbols)
        except Exception as e:
            logging.error(f"Error in sync fetch: {e}")
        
        return results
    
    def batch_requests(self, items: List[Any], batch_size: int = 10):
        """
        Split items into batches for processing.
        
        Args:
            items: List of items to batch
            batch_size: Size of each batch
            
        Yields:
            Batches of items
        """
        for i in range(0, len(items), batch_size):
            yield items[i:i + batch_size]


async def benchmark_async_performance(kite_client, symbols: List[str]):
    """
    Benchmark async vs sync performance.
    
    Args:
        kite_client: KiteConnect client
        symbols: List of symbols to test with
    """
    import time
    
    # Test synchronous performance
    start = time.time()
    sync_results = {}
    for symbol in symbols:
        try:
            sync_results[symbol] = kite_client.quote(symbol)
        except Exception as e:
            sync_results[symbol] = None
    sync_time = time.time() - start
    
    # Test async performance
    config = {'performance': {'enabled': True, 'async_operations': True}}
    optimizer = PerformanceOptimizer(config)
    
    start = time.time()
    async_results = await optimizer.optimize_data_fetch(kite_client, symbols, 'quote')
    async_time = time.time() - start
    
    logging.info(f"Sync time: {sync_time:.2f}s, Async time: {async_time:.2f}s")
    logging.info(f"Speedup: {sync_time/async_time:.2f}x")
    
    return {
        'sync_time': sync_time,
        'async_time': async_time,
        'speedup': sync_time / async_time if async_time > 0 else 0
    }