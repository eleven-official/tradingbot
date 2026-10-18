"""
Loki Real Market Data Integration
Live and historical data from Alpaca and Yahoo Finance
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class RealMarketDataProvider:
    """
    Real market data provider with multiple sources
    - Alpaca for intraday and real-time data
    - Yahoo Finance as fallback for historical data
    """

    def __init__(self, alpaca_key: str = None, alpaca_secret: str = None):
        self.alpaca_key = alpaca_key or os.getenv("ALPACA_API_KEY")
        self.alpaca_secret = alpaca_secret or os.getenv("ALPACA_SECRET_KEY")

        self.alpaca_rest = None
        self.alpaca_stream = None

        self._init_alpaca()

        logger.info("📊 Real Market Data Provider initialized")

    def _init_alpaca(self):
        """Initialize Alpaca connection"""
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.live import StockDataStream
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            if self.alpaca_key and self.alpaca_secret:
                self.alpaca_rest = StockHistoricalDataClient(self.alpaca_key, self.alpaca_secret)
                logger.info("✓ Alpaca API connected")
            else:
                logger.warning("⚠ Alpaca credentials not found, using fallback")
        except ImportError:
            logger.warning("⚠ Alpaca library not installed, using yfinance")

    def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str = "1Day"
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_date: Start date
            end_date: End date
            timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day'

        Returns:
            DataFrame with OHLCV data
        """
        logger.info(f"📥 Fetching {symbol} data from {start_date.date()} to {end_date.date()}")

        # Try Alpaca first
        if self.alpaca_rest:
            try:
                data = self._fetch_alpaca_data(symbol, start_date, end_date, timeframe)
                if data is not None and len(data) > 0:
                    logger.info(f"✓ Retrieved {len(data)} bars from Alpaca")
                    return data
            except Exception as e:
                logger.warning(f"Alpaca fetch failed: {e}, trying yfinance")

        # Fallback to yfinance
        data = self._fetch_yahoo_data(symbol, start_date, end_date, timeframe)
        logger.info(f"✓ Retrieved {len(data)} bars from Yahoo Finance")
        return data

    def _fetch_alpaca_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch data from Alpaca"""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        # Map timeframe string to Alpaca TimeFrame
        timeframe_map = {
            "1Min": TimeFrame(1, TimeFrameUnit.Minute),
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
            "1Day": TimeFrame(1, TimeFrameUnit.Day),
        }

        tf = timeframe_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Day))

        request_params = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=tf, start=start_date, end=end_date
        )

        bars = self.alpaca_rest.get_stock_bars(request_params)

        # Convert to DataFrame
        if symbol in bars:
            df = bars[symbol].df

            # Standardize column names
            df = df.rename(
                columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                }
            )

            return df[["open", "high", "low", "close", "volume"]]

        return None

    def _fetch_yahoo_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> pd.DataFrame:
        """Fetch data from Yahoo Finance"""
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed: pip install yfinance")
            return self._generate_demo_data(symbol, start_date, end_date)

        # Map timeframe to yfinance interval
        interval_map = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Hour": "1h", "1Day": "1d"}

        interval = interval_map.get(timeframe, "1d")

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)

            # Standardize column names
            df.columns = df.columns.str.lower()

            if len(df) > 0:
                return df[["open", "high", "low", "close", "volume"]]
            # Empty result means an invalid ticker or no history — never
            # fabricate demo data for what should be a real fetch.
            logger.warning(
                f"No data returned for '{symbol}' (invalid ticker?); returning empty frame"
            )
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        except Exception as e:
            # Do NOT silently fall back to synthetic prices on a live fetch
            # failure — a trading bot must never trade on fabricated data.
            logger.warning(f"yfinance error for '{symbol}': {e}; returning empty frame")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _generate_demo_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """Generate realistic demo data when APIs unavailable"""
        logger.info("📊 Generating realistic demo data")

        # Calculate number of trading days
        days = (end_date - start_date).days
        dates = pd.bdate_range(start=start_date, periods=min(days, 252))

        # Generate realistic price movements
        base_price = 150.0
        returns = np.random.normal(0.0008, 0.02, len(dates))  # ~20% annual return, 20% vol
        prices = base_price * (1 + returns).cumprod()

        # Generate OHLC from close prices
        data = []
        for i, (date, close) in enumerate(zip(dates, prices)):
            volatility = 0.015  # 1.5% intraday volatility

            open_price = close * (1 + np.random.uniform(-volatility, volatility))
            high = max(open_price, close) * (1 + abs(np.random.normal(0, volatility / 2)))
            low = min(open_price, close) * (1 - abs(np.random.normal(0, volatility / 2)))
            volume = np.random.randint(1000000, 10000000)

            data.append(
                {"open": open_price, "high": high, "low": low, "close": close, "volume": volume}
            )

        df = pd.DataFrame(data, index=dates)
        return df

    def get_latest_price(self, symbol: str) -> float:
        """Get latest price for symbol"""
        try:
            if self.alpaca_rest:
                from alpaca.data.requests import StockLatestQuoteRequest

                request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                quotes = self.alpaca_rest.get_stock_latest_quote(request)

                if symbol in quotes:
                    return quotes[symbol].ask_price

            # Fallback to yfinance
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if len(data) > 0:
                return data["Close"].iloc[-1]

        except Exception as e:
            logger.error(f"Error fetching latest price: {e}")

        return 0.0

    def stream_real_time_data(self, symbol: str, callback):
        """Stream real-time market data"""
        if not self.alpaca_key or not self.alpaca_secret:
            logger.warning("⚠ Alpaca credentials required for streaming")
            return

        try:
            from alpaca.data.live import StockDataStream

            stream = StockDataStream(self.alpaca_key, self.alpaca_secret)

            @stream.on_bar(symbol)
            async def on_bar(bar):
                callback(
                    {
                        "symbol": symbol,
                        "timestamp": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                )

            logger.info(f"📡 Starting real-time stream for {symbol}")
            stream.run()

        except Exception as e:
            logger.error(f"Streaming error: {e}")


class MarketDataCache:
    """Cache for market data to reduce API calls"""

    def __init__(self, cache_duration_minutes: int = 15):
        self.cache = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """Get cached data"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.cache_duration:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key: str, data: pd.DataFrame):
        """Cache data"""
        self.cache[key] = (data, datetime.now())

    def clear(self):
        """Clear cache"""
        self.cache.clear()


# Global provider instance
_provider = None


def get_market_data_provider() -> RealMarketDataProvider:
    """Get global market data provider"""
    global _provider
    if _provider is None:
        _provider = RealMarketDataProvider()
    return _provider


# Convenience functions
def get_stock_data(symbol: str, period: str = "1y", timeframe: str = "1Day") -> pd.DataFrame:
    """
    Quick function to get stock data.

    Accepts both calling conventions:
      * ``get_stock_data(symbol, period='6mo', timeframe='1Day')``
      * legacy ``get_stock_data(symbol, start_date, end_date)`` (datetimes)

    Args:
        symbol: Stock symbol
        period: Period like '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y',
            or a start ``datetime`` (legacy two-date form).
        timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day', or an end
            ``datetime`` (legacy two-date form).

    Returns:
        DataFrame with OHLCV data
    """
    provider = get_market_data_provider()

    # Legacy form: get_stock_data(symbol, start_date, end_date)
    if isinstance(period, (datetime, pd.Timestamp)):
        start_date = period
        end_date = timeframe if isinstance(timeframe, (datetime, pd.Timestamp)) else datetime.now()
        timeframe = "1Day"
    else:
        # Convert period to dates
        period_map = {
            "1d": 1,
            "5d": 5,
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
            "5y": 1825,
        }
        days = period_map.get(period, 365)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

    return provider.get_historical_data(symbol, start_date, end_date, timeframe)


def get_multiple_stocks(
    symbols: List[str], period: str = "1y", timeframe: str = "1Day"
) -> Dict[str, pd.DataFrame]:
    """Get data for multiple stocks"""
    result = {}
    provider = get_market_data_provider()

    period_map = {
        "1d": 1,
        "5d": 5,
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
    }

    days = period_map.get(period, 365)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    for symbol in symbols:
        try:
            result[symbol] = provider.get_historical_data(symbol, start_date, end_date, timeframe)
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")

    return result


if __name__ == "__main__":
    # Test the data provider
    logging.basicConfig(level=logging.INFO)

    print("Testing Real Market Data Provider")
    print("=" * 50)

    # Test 1: Get historical data
    print("\n1. Fetching AAPL historical data...")
    data = get_stock_data("AAPL", period="3mo", timeframe="1Day")
    print(f"   Retrieved {len(data)} bars")
    print(f"   Latest close: ${data['close'].iloc[-1]:.2f}")
    print(f"   Date range: {data.index[0].date()} to {data.index[-1].date()}")

    # Test 2: Get multiple stocks
    print("\n2. Fetching multiple stocks...")
    symbols = ["AAPL", "MSFT", "GOOGL"]
    multi_data = get_multiple_stocks(symbols, period="1mo")
    for symbol, df in multi_data.items():
        print(f"   {symbol}: {len(df)} bars, latest ${df['close'].iloc[-1]:.2f}")

    print("\n✓ All tests passed!")
