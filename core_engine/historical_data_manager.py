"""
Historical Data Manager - Real Market Data Fetching and Storage
Handles fetching, storing, and retrieving historical market data for backtesting
"""
import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor


class DataFrequency(Enum):
    """Data frequency types."""
    TICK = "tick"
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"


class DataSource(Enum):
    """Data sources."""
    CCXT = "ccxt"
    LOCAL = "local"
    POLYGON = "polygon"
    ALPHA_VANTAGE = "alpha_vantage"


@dataclass
class DataRequest:
    """Data request specification."""
    symbol: str
    exchange: str
    frequency: DataFrequency
    start_date: datetime
    end_date: datetime
    source: DataSource = DataSource.CCXT


@dataclass
class DataSnapshot:
    """Data snapshot."""
    symbol: str
    exchange: str
    frequency: DataFrequency
    data: pd.DataFrame
    fetched_at: datetime
    source: DataSource


class HistoricalDataManager:
    """
    Production-ready historical data manager.
    Fetches, stores, and retrieves real market data for backtesting.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_path = Path(config.get('data_db_path', 'data/historical_data.db'))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Cache
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.cache_ttl = timedelta(minutes=30)
        
        # Thread pool for parallel fetching
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Exchange manager reference (will be set later)
        self.exchange_manager = None
        
        # Database connection
        self.db_conn = None
        
        logging.info("Historical Data Manager initialized")
    
    async def initialize(self, exchange_manager):
        """Initialize the data manager."""
        self.logger = logging.getLogger(__name__)
        self.exchange_manager = exchange_manager
        
        # Initialize database
        await self._init_database()
        
        self.logger.info("Historical Data Manager initialized")
    
    async def _init_database(self):
        """Initialize SQLite database for data storage."""
        self.db_conn = sqlite3.connect(self.db_path)
        cursor = self.db_conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                frequency TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(symbol, exchange, frequency, timestamp)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol ON ohlcv_data(symbol)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON ohlcv_data(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_timestamp ON ohlcv_data(symbol, timestamp)
        """)
        
        self.db_conn.commit()
        self.logger.info("Database initialized")
    
    async def fetch_data(self, request: DataRequest) -> Optional[pd.DataFrame]:
        """Fetch historical data based on request."""
        cache_key = f"{request.symbol}_{request.exchange}_{request.frequency}_{request.start_date}_{request.end_date}"
        
        # Check cache first
        if cache_key in self.data_cache:
            self.logger.info(f"Using cached data for {request.symbol}")
            return self.data_cache[cache_key]
        
        # Try to fetch from database
        db_data = await self._fetch_from_db(request)
        if db_data is not None and len(db_data) > 0:
            self.data_cache[cache_key] = db_data
            return db_data
        
        # Fetch from exchange
        if request.source == DataSource.CCXT and self.exchange_manager:
            exchange_data = await self._fetch_from_exchange(request)
            if exchange_data is not None and len(exchange_data) > 0:
                # Store in database
                await self._store_in_db(request, exchange_data)
                self.data_cache[cache_key] = exchange_data
                return exchange_data
        
        self.logger.warning(f"Failed to fetch data for {request.symbol}")
        return None
    
    async def _fetch_from_db(self, request: DataRequest) -> Optional[pd.DataFrame]:
        """Fetch data from local database."""
        try:
            cursor = self.db_conn.cursor()
            
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM ohlcv_data
                WHERE symbol = ? AND exchange = ? AND frequency = ?
                AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
            """
            
            cursor.execute(query, (
                request.symbol,
                request.exchange,
                request.frequency.value,
                request.start_date,
                request.end_date
            ))
            
            rows = cursor.fetchall()
            
            if rows:
                df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                return df
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error fetching from database: {e}")
            return None
    
    async def _fetch_from_exchange(self, request: DataRequest) -> Optional[pd.DataFrame]:
        """Fetch data from exchange via CCXT."""
        try:
            from core_engine.real_exchange_manager import RealExchangeManager
            
            if not self.exchange_manager:
                return None
            
            # Fetch data in chunks
            all_data = []
            current_date = request.start_date
            chunk_size = 1000  # Max candles per request
            
            while current_date < request.end_date:
                end_date = min(current_date + timedelta(days=30), request.end_date)
                
                df = await self.exchange_manager.get_historical_ohlcv(
                    symbol=request.symbol,
                    timeframe=request.frequency.value,
                    limit=chunk_size,
                    exchange_id=request.exchange
                )
                
                if df is not None and len(df) > 0:
                    all_data.append(df)
                
                current_date = end_date
                
                # Rate limiting
                await asyncio.sleep(1)
            
            if all_data:
                combined_df = pd.concat(all_data)
                combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                combined_df.sort_index(inplace=True)
                return combined_df
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error fetching from exchange: {e}")
            return None
    
    async def _store_in_db(self, request: DataRequest, data: pd.DataFrame):
        """Store data in database."""
        try:
            cursor = self.db_conn.cursor()
            
            for timestamp, row in data.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO ohlcv_data
                    (symbol, exchange, frequency, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.symbol,
                    request.exchange,
                    request.frequency.value,
                    timestamp,
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume']
                ))
            
            self.db_conn.commit()
            self.logger.info(f"Stored {len(data)} records for {request.symbol}")
            
        except Exception as e:
            self.logger.error(f"Error storing in database: {e}")
    
    async def fetch_multiple_symbols(self, requests: List[DataRequest]) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols in parallel."""
        results = {}
        
        tasks = [self.fetch_data(request) for request in requests]
        data_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        for request, data in zip(requests, data_list):
            if isinstance(data, Exception):
                self.logger.error(f"Error fetching {request.symbol}: {data}")
            elif data is not None:
                results[request.symbol] = data
        
        return results
    
    async def get_available_symbols(self, exchange: str) -> List[str]:
        """Get list of symbols with historical data available."""
        try:
            cursor = self.db_conn.cursor()
            
            cursor.execute("""
                SELECT DISTINCT symbol
                FROM ohlcv_data
                WHERE exchange = ?
                ORDER BY symbol
            """, (exchange,))
            
            rows = cursor.fetchall()
            return [row[0] for row in rows]
            
        except Exception as e:
            self.logger.error(f"Error fetching available symbols: {e}")
            return []
    
    async def get_data_coverage(self, symbol: str, exchange: str) -> Dict[str, datetime]:
        """Get data coverage (start and end dates) for a symbol."""
        try:
            cursor = self.db_conn.cursor()
            
            cursor.execute("""
                SELECT MIN(timestamp), MAX(timestamp)
                FROM ohlcv_data
                WHERE symbol = ? AND exchange = ?
            """, (symbol, exchange))
            
            row = cursor.fetchone()
            
            if row and row[0] and row[1]:
                return {
                    'start_date': pd.to_datetime(row[0]),
                    'end_date': pd.to_datetime(row[1])
                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching data coverage: {e}")
            return {}
    
    async def clean_old_data(self, days_to_keep: int = 365):
        """Clean old data from database."""
        try:
            cursor = self.db_conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            cursor.execute("""
                DELETE FROM ohlcv_data
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            deleted = cursor.rowcount
            self.db_conn.commit()
            
            self.logger.info(f"Cleaned {deleted} old records")
            
        except Exception as e:
            self.logger.error(f"Error cleaning old data: {e}")
    
    async def export_data(self, symbol: str, exchange: str, output_path: Path):
        """Export data to CSV file."""
        try:
            request = DataRequest(
                symbol=symbol,
                exchange=exchange,
                frequency=DataFrequency.DAY_1,
                start_date=datetime.now() - timedelta(days=365),
                end_date=datetime.now()
            )
            
            data = await self.fetch_data(request)
            
            if data is not None:
                data.to_csv(output_path)
                self.logger.info(f"Exported data to {output_path}")
            
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
    
    async def import_data(self, input_path: Path, symbol: str, exchange: str, frequency: DataFrequency):
        """Import data from CSV file."""
        try:
            data = pd.read_csv(input_path)
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data.set_index('timestamp', inplace=True)
            
            request = DataRequest(
                symbol=symbol,
                exchange=exchange,
                frequency=frequency,
                start_date=data.index.min(),
                end_date=data.index.max()
            )
            
            await self._store_in_db(request, data)
            self.logger.info(f"Imported data from {input_path}")
            
        except Exception as e:
            self.logger.error(f"Error importing data: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            cursor = self.db_conn.cursor()
            
            # Total records
            cursor.execute("SELECT COUNT(*) FROM ohlcv_data")
            total_records = cursor.fetchone()[0]
            
            # Unique symbols
            cursor.execute("SELECT COUNT(DISTINCT symbol) FROM ohlcv_data")
            unique_symbols = cursor.fetchone()[0]
            
            # Exchanges
            cursor.execute("SELECT COUNT(DISTINCT exchange) FROM ohlcv_data")
            unique_exchanges = cursor.fetchone()[0]
            
            # Date range
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv_data")
            date_range = cursor.fetchone()
            
            return {
                'total_records': total_records,
                'unique_symbols': unique_symbols,
                'unique_exchanges': unique_exchanges,
                'date_range_start': date_range[0] if date_range[0] else None,
                'date_range_end': date_range[1] if date_range[1] else None
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching statistics: {e}")
            return {}
    
    async def shutdown(self):
        """Shutdown the data manager."""
        if self.db_conn:
            self.db_conn.close()
        
        self.executor.shutdown(wait=True)
        self.logger.info("Historical Data Manager shutdown complete")