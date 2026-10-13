"""
Strategy Interface for Freqtrade-Inspired Backtesting
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class IStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> str:
        """
        Generate trading signal based on data.
        Returns: 'BUY', 'SELL', or 'HOLD'
        """
        pass
    
    @abstractmethod
    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        """Calculate stop loss level."""
        pass
    
    @abstractmethod
    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        """Calculate take profit level."""
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Get current strategy parameters."""
        pass
    
    @abstractmethod
    def set_parameters(self, parameters: Dict[str, Any]):
        """Set strategy parameters."""
        pass


class RSI_MACD_Strategy(IStrategy):
    """RSI + MACD combined strategy."""
    
    def __init__(self, rsi_period: int = 14, rsi_oversold: int = 30, rsi_overbought: int = 70,
                 macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
    
    def generate_signal(self, data: pd.DataFrame) -> str:
        if len(data) < self.macd_slow:
            return 'HOLD'
        
        # Calculate RSI
        rsi = self._calculate_rsi(data['close'], self.rsi_period)
        
        # Calculate MACD
        macd_line, signal_line, _ = self._calculate_macd(data['close'], self.macd_fast, self.macd_slow, self.macd_signal)
        
        # Generate signal
        if rsi < self.rsi_oversold and macd_line.iloc[-1] > signal_line.iloc[-1]:
            return 'BUY'
        elif rsi > self.rsi_overbought and macd_line.iloc[-1] < signal_line.iloc[-1]:
            return 'SELL'
        else:
            return 'HOLD'
    
    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        atr = self._calculate_atr(data, 14)
        return entry_price - atr * 2
    
    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        atr = self._calculate_atr(data, 14)
        return entry_price + atr * 3
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            'rsi_period': self.rsi_period,
            'rsi_oversold': self.rsi_oversold,
            'rsi_overbought': self.rsi_overbought,
            'macd_fast': self.macd_fast,
            'macd_slow': self.macd_slow,
            'macd_signal': self.macd_signal
        }
    
    def set_parameters(self, parameters: Dict[str, Any]):
        for key, value in parameters.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> float:
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
    
    def _calculate_macd(self, prices: pd.Series, fast: int, slow: int, signal: int):
        """Calculate MACD."""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist_line = macd_line - signal_line
        return macd_line, signal_line, hist_line
    
    def _calculate_atr(self, data: pd.DataFrame, period: int) -> float:
        """Calculate ATR."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0.0


class Bollinger_Reversal_Strategy(IStrategy):
    """Bollinger Bands mean reversion strategy."""
    
    def __init__(self, bb_length: int = 20, bb_mult: float = 2.0):
        self.bb_length = bb_length
        self.bb_mult = bb_mult
    
    def generate_signal(self, data: pd.DataFrame) -> str:
        if len(data) < self.bb_length:
            return 'HOLD'
        
        # Calculate Bollinger Bands
        bb_middle, bb_upper, bb_lower = self._calculate_bb(data['close'], self.bb_length, self.bb_mult)
        
        current_price = data['close'].iloc[-1]
        bb_lower_val = bb_lower.iloc[-1]
        bb_upper_val = bb_upper.iloc[-1]
        
        # Generate signal
        if current_price < bb_lower_val:
            return 'BUY'
        elif current_price > bb_upper_val:
            return 'SELL'
        else:
            return 'HOLD'
    
    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        bb_middle, _, bb_lower = self._calculate_bb(data['close'], self.bb_length, self.bb_mult)
        return bb_lower
    
    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        bb_middle, bb_upper, _ = self._calculate_bb(data['close'], self.bb_length, self.bb_mult)
        return bb_upper
    
    def get_parameters(self) -> Dict[str, Any]:
        return {
            'bb_length': self.bb_length,
            'bb_mult': self.bb_mult
        }
    
    def set_parameters(self, parameters: Dict[str, Any]):
        for key, value in parameters.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def _calculate_bb(self, prices: pd.Series, length: int, mult: float):
        """Calculate Bollinger Bands."""
        bb_middle = prices.rolling(window=length).mean()
        bb_std = prices.rolling(window=length).std()
        bb_upper = bb_middle + bb_std * mult
        bb_lower = bb_middle - bb_std * mult
        return bb_middle, bb_upper, bb_lower