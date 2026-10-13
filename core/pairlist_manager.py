"""
Freqtrade-Inspired Pairlist Management
Dynamic pair selection based on volume, price, and performance
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logging.warning("ccxt not available - pairlist manager will use static mode only")


class PairlistMethod(Enum):
    """Pairlist selection methods."""
    STATIC = "static"
    VOLUME_PAIRLIST = "volume_pairlist"
    AGE_FILTER = "age_filter"
    PERFORMANCE_FILTER = "performance_filter"
    PRESET = "preset"


@dataclass
class PairInfo:
    """Information about a trading pair."""
    symbol: str
    volume_24h: float
    price: float
    change_24h: float
    age_days: int
    last_traded: datetime
    performance_score: float


class PairlistManager:
    """
    Freqtrade-inspired pairlist manager for dynamic pair selection.
    Automatically selects the best pairs to trade based on various criteria.
    """

    # Expose the enum on the class (FreqTrade-style API: manager.PairlistMethod.VOLUME_PAIRLIST)
    PairlistMethod = PairlistMethod

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pairlist_config = config.get('pairlist', {})
        
        # Configuration
        self.method = PairlistMethod(self.pairlist_config.get('method', 'static'))
        self.refresh_pairs = self.pairlist_config.get('refresh_pairs', 60)  # minutes
        self.number_of_pairs = self.pairlist_config.get('number_of_pairs', 20)
        self.stake_currency = self.pairlist_config.get('stake_currency', 'AUD')
        
        # Static pairlist
        self.static_pairs = self.pairlist_config.get('static_pairs', [
            'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'SOL/USDT'
        ])
        
        # Blacklist
        self.blacklist = set(self.pairlist_config.get('blacklist', []))
        
        # Whitelist
        self.whitelist = set(self.pairlist_config.get('whitelist', []))
        
        # Exchange connection
        self.exchange = None
        self._init_exchange()
        
        # Cached pair info
        self.pair_cache: Dict[str, PairInfo] = {}
        self.last_refresh: Optional[datetime] = None
        
        logging.info("Pairlist Manager initialized")
    
    def _init_exchange(self):
        """Initialize exchange connection."""
        if not CCXT_AVAILABLE:
            logging.warning("ccxt not available - using static pairlist only")
            self.exchange = None
            return
        
        try:
            exchange_config = self.config.get('crypto_broker', {})
            exchange_id = exchange_config.get('exchange', 'binance')
            
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            
            logging.info(f"Exchange initialized: {exchange_id}")
            
        except Exception as e:
            logging.error(f"Exchange initialization error: {e}")
            self.exchange = None
    
    def get_pairlist(self) -> List[str]:
        """Get the current pairlist based on configured method."""
        if self.method == PairlistMethod.STATIC:
            return self._get_static_pairlist()
        elif self.method == PairlistMethod.VOLUME_PAIRLIST:
            return self._get_volume_pairlist()
        elif self.method == PairlistMethod.AGE_FILTER:
            return self._get_age_filtered_pairlist()
        elif self.method == PairlistMethod.PERFORMANCE_FILTER:
            return self._get_performance_filtered_pairlist()
        else:
            return self.static_pairs
    
    def _get_static_pairlist(self) -> List[str]:
        """Get static pairlist."""
        pairs = [p for p in self.static_pairs if p not in self.blacklist]
        
        if self.whitelist:
            pairs = [p for p in pairs if p in self.whitelist]
        
        return pairs[:self.number_of_pairs]
    
    def _get_volume_pairlist(self) -> List[str]:
        """Get pairlist based on 24h volume."""
        if not self.exchange or not CCXT_AVAILABLE:
            logging.warning("Exchange not available - using static pairlist")
            return self._get_static_pairlist()
        
        try:
            # Fetch markets
            markets = self.exchange.load_markets()
            
            # Get tickers for USDT pairs
            usdt_pairs = [symbol for symbol in markets if '/USDT' in symbol]
            
            # Fetch tickers
            tickers = self.exchange.fetch_tickers(usdt_pairs)
            
            # Sort by volume
            sorted_pairs = sorted(
                tickers.items(),
                key=lambda x: x[1].get('quoteVolume', 0),
                reverse=True
            )
            
            # Filter and return top pairs
            pairs = []
            for symbol, ticker in sorted_pairs:
                if symbol in self.blacklist:
                    continue
                if self.whitelist and symbol not in self.whitelist:
                    continue
                
                pairs.append(symbol)
                
                if len(pairs) >= self.number_of_pairs:
                    break
            
            logging.info(f"Volume pairlist generated: {len(pairs)} pairs")
            return pairs
            
        except Exception as e:
            logging.error(f"Volume pairlist error: {e}")
            return self._get_static_pairlist()
    
    def _get_age_filtered_pairlist(self) -> List[str]:
        """Get pairlist filtered by age (time since listing)."""
        if not self.exchange:
            return self._get_static_pairlist()
        
        try:
            # Get static pairs first
            pairs = self._get_static_pairlist()
            
            # Filter by age (simulated - in real implementation, check listing date)
            # For now, we'll use volume as a proxy for age
            tickers = self.exchange.fetch_tickers(pairs)
            
            filtered_pairs = []
            for symbol, ticker in tickers.items():
                # High volume pairs are usually older/stable
                if ticker.get('quoteVolume', 0) > 1000000:  # $1M volume threshold
                    filtered_pairs.append(symbol)
            
            return filtered_pairs[:self.number_of_pairs]
            
        except Exception as e:
            logging.error(f"Age filter error: {e}")
            return self._get_static_pairlist()
    
    def _get_performance_filtered_pairlist(self) -> List[str]:
        """Get pairlist filtered by recent performance."""
        # This would use historical performance data
        # For now, return static pairlist
        return self._get_static_pairlist()
    
    def get_pair_info(self, symbol: str) -> Optional[PairInfo]:
        """Get detailed information about a specific pair."""
        if not self.exchange:
            return None
        
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            
            return PairInfo(
                symbol=symbol,
                volume_24h=ticker.get('quoteVolume', 0),
                price=ticker.get('last', 0),
                change_24h=ticker.get('percentage', 0),
                age_days=0,  # Would need listing date
                last_traded=datetime.now(),
                performance_score=0.0  # Would need historical data
            )
            
        except Exception as e:
            logging.error(f"Error fetching pair info for {symbol}: {e}")
            return None
    
    def refresh_pairlist(self):
        """Refresh the pairlist (fetch latest data)."""
        if self.last_refresh:
            time_since_refresh = (datetime.now() - self.last_refresh).total_seconds() / 60
            if time_since_refresh < self.refresh_pairs:
                return
        
        self.last_refresh = datetime.now()
        logging.info("Refreshing pairlist...")
        
        # Clear cache
        self.pair_cache.clear()
        
        # Fetch new data
        if self.method != PairlistMethod.STATIC:
            self.get_pairlist()
    
    def add_to_blacklist(self, symbol: str):
        """Add a symbol to the blacklist."""
        self.blacklist.add(symbol)
        logging.info(f"Added {symbol} to blacklist")
    
    def remove_from_blacklist(self, symbol: str):
        """Remove a symbol from the blacklist."""
        self.blacklist.discard(symbol)
        logging.info(f"Removed {symbol} from blacklist")
    
    def add_to_whitelist(self, symbol: str):
        """Add a symbol to the whitelist."""
        self.whitelist.add(symbol)
        logging.info(f"Added {symbol} to whitelist")
    
    def remove_from_whitelist(self, symbol: str):
        """Remove a symbol from the whitelist."""
        self.whitelist.discard(symbol)
        logging.info(f"Removed {symbol} from whitelist")
    
    def get_pairlist_status(self) -> Dict[str, Any]:
        """Get current pairlist status."""
        current_pairs = self.get_pairlist()
        
        return {
            'method': self.method.value,
            'total_pairs': len(current_pairs),
            'pairs': current_pairs,
            'blacklisted': list(self.blacklist),
            'whitelisted': list(self.whitelist),
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None
        }