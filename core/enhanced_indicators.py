"""
Enhanced Technical Indicators Module
Integrated from FinceptTerminal project
Comprehensive technical analysis indicators for Loki
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union


class EnhancedIndicators:
    """Comprehensive technical indicators from FinceptTerminal."""
    
    def __init__(self):
        self.momentum_indicators = [
            'rsi', 'stochastic', 'stoch_rsi', 'williams_r', 
            'awesome_oscillator', 'kama', 'roc', 'tsi', 
            'ultimate_oscillator', 'ppo', 'pvo'
        ]
        self.trend_indicators = [
            'sma', 'ema', 'wma', 'macd', 'trix', 'mass_index',
            'ichimoku', 'kst', 'dpo', 'cci', 'adx', 'vortex',
            'psar', 'stc', 'aroon'
        ]
        self.volatility_indicators = [
            'bollinger_bands', 'atr', 'keltner_channel', 'donchian_channel'
        ]
        self.volume_indicators = [
            'obv', 'mfi', 'cmf', 'vwap', 'adi'
        ]
    
    def calculate_sma(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """Simple Moving Average."""
        return df['close'].rolling(window=window).mean()
    
    def calculate_ema(self, df: pd.DataFrame, window: int = 12) -> pd.Series:
        """Exponential Moving Average."""
        return df['close'].ewm(span=window, adjust=False).mean()
    
    def calculate_rsi(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(
        self, 
        df: pd.DataFrame, 
        fast: int = 12, 
        slow: int = 26, 
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """MACD (Moving Average Convergence Divergence)."""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def calculate_bollinger_bands(
        self, 
        df: pd.DataFrame, 
        window: int = 20, 
        num_std: float = 2.0
    ) -> Dict[str, pd.Series]:
        """Bollinger Bands."""
        sma = self.calculate_sma(df, window)
        std = df['close'].rolling(window=window).std()
        
        return {
            'middle': sma,
            'upper': sma + (std * num_std),
            'lower': sma - (std * num_std),
            'bandwidth': (std * num_std * 2) / sma,
            'percent_b': (df['close'] - (sma - std * num_std)) / (std * num_std * 2)
        }
    
    def calculate_atr(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """Average True Range."""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        return true_range.rolling(window=window).mean()
    
    def calculate_stochastic(
        self, 
        df: pd.DataFrame, 
        k_window: int = 14, 
        d_window: int = 3
    ) -> Dict[str, pd.Series]:
        """Stochastic Oscillator."""
        low_min = df['low'].rolling(window=k_window).min()
        high_max = df['high'].rolling(window=k_window).max()
        
        k_percent = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d_percent = k_percent.rolling(window=d_window).mean()
        
        return {
            'stoch_k': k_percent,
            'stoch_d': d_percent
        }
    
    def calculate_adx(self, df: pd.DataFrame, window: int = 14) -> Dict[str, pd.Series]:
        """Average Directional Index."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr1 = high - low
        tr2 = np.abs(high - close.shift())
        tr3 = np.abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=window).mean()
        plus_di = 100 * (plus_dm.rolling(window=window).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=window).mean() / atr)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=window).mean()
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }
    
    def calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """On-Balance Volume."""
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return obv
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Volume Weighted Average Price."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return vwap
    
    def calculate_williams_r(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """Williams %R."""
        high_max = df['high'].rolling(window=window).max()
        low_min = df['low'].rolling(window=window).min()
        williams_r = -100 * ((high_max - df['close']) / (high_max - low_min))
        return williams_r
    
    def calculate_cci(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """Commodity Channel Index."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        sma = typical_price.rolling(window=window).mean()
        mad = typical_price.rolling(window=window).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (typical_price - sma) / (0.015 * mad)
        return cci
    
    def calculate_roc(self, df: pd.DataFrame, window: int = 12) -> pd.Series:
        """Rate of Change."""
        roc = ((df['close'] - df['close'].shift(window)) / df['close'].shift(window)) * 100
        return roc
    
    def calculate_mfi(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """Money Flow Index."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        money_flow = typical_price * df['volume']
        
        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)
        
        positive_mf = positive_flow.rolling(window=window).sum()
        negative_mf = negative_flow.rolling(window=window).sum()
        
        mfi = 100 - (100 / (1 + positive_mf / negative_mf))
        return mfi
    
    def calculate_all_indicators(
        self, 
        df: pd.DataFrame, 
        include_all: bool = True
    ) -> pd.DataFrame:
        """
        Calculate all technical indicators at once.
        
        Args:
            df: DataFrame with OHLCV columns
            include_all: Whether to include all indicators or just key ones
        
        Returns:
            DataFrame with all calculated indicators
        """
        result = df.copy()
        
        # Basic Moving Averages
        result['sma_20'] = self.calculate_sma(df, 20)
        result['sma_50'] = self.calculate_sma(df, 50)
        result['sma_200'] = self.calculate_sma(df, 200)
        result['ema_9'] = self.calculate_ema(df, 9)
        result['ema_21'] = self.calculate_ema(df, 21)
        result['ema_50'] = self.calculate_ema(df, 50)
        
        # Momentum Indicators
        result['rsi'] = self.calculate_rsi(df, 14)
        result['roc'] = self.calculate_roc(df, 12)
        result['williams_r'] = self.calculate_williams_r(df, 14)
        
        # MACD
        macd = self.calculate_macd(df)
        result['macd'] = macd['macd']
        result['macd_signal'] = macd['signal']
        result['macd_hist'] = macd['histogram']
        
        # Stochastic
        stoch = self.calculate_stochastic(df)
        result['stoch_k'] = stoch['stoch_k']
        result['stoch_d'] = stoch['stoch_d']
        
        # ADX
        adx = self.calculate_adx(df)
        result['adx'] = adx['adx']
        result['plus_di'] = adx['plus_di']
        result['minus_di'] = adx['minus_di']
        
        # Bollinger Bands
        bb = self.calculate_bollinger_bands(df)
        result['bb_upper'] = bb['upper']
        result['bb_middle'] = bb['middle']
        result['bb_lower'] = bb['lower']
        result['bb_bandwidth'] = bb['bandwidth']
        result['bb_percent_b'] = bb['percent_b']
        
        # ATR
        result['atr'] = self.calculate_atr(df)
        
        # CCI
        result['cci'] = self.calculate_cci(df)
        
        # Volume Indicators
        result['obv'] = self.calculate_obv(df)
        result['vwap'] = self.calculate_vwap(df)
        result['mfi'] = self.calculate_mfi(df)
        
        if include_all:
            # Additional indicators
            result['sma_10'] = self.calculate_sma(df, 10)
            result['ema_12'] = self.calculate_ema(df, 12)
            result['ema_26'] = self.calculate_ema(df, 26)
            
            # Multiple RSI periods
            result['rsi_7'] = self.calculate_rsi(df, 7)
            result['rsi_21'] = self.calculate_rsi(df, 21)
            
            # Multiple ATR periods
            result['atr_7'] = self.calculate_atr(df, 7)
            result['atr_21'] = self.calculate_atr(df, 21)
        
        return result
    
    def get_indicator_signals(
        self, 
        df: pd.DataFrame
    ) -> Dict[str, str]:
        """
        Generate trading signals from indicators.
        
        Returns:
            Dictionary with signal names and directions (BUY/SELL/HOLD)
        """
        signals = {}
        
        # RSI Signal
        rsi = self.calculate_rsi(df, 14).iloc[-1]
        if rsi < 30:
            signals['rsi'] = 'BUY'
        elif rsi > 70:
            signals['rsi'] = 'SELL'
        else:
            signals['rsi'] = 'HOLD'
        
        # MACD Signal
        macd = self.calculate_macd(df)
        if macd['macd'].iloc[-1] > macd['signal'].iloc[-1]:
            signals['macd'] = 'BUY'
        else:
            signals['macd'] = 'SELL'
        
        # ADX Trend Strength
        adx = self.calculate_adx(df)
        if adx['adx'].iloc[-1] > 25:
            if adx['plus_di'].iloc[-1] > adx['minus_di'].iloc[-1]:
                signals['adx'] = 'BUY'
            else:
                signals['adx'] = 'SELL'
        else:
            signals['adx'] = 'HOLD'
        
        # Bollinger Bands
        bb = self.calculate_bollinger_bands(df)
        price = df['close'].iloc[-1]
        if price < bb['lower'].iloc[-1]:
            signals['bollinger'] = 'BUY'
        elif price > bb['upper'].iloc[-1]:
            signals['bollinger'] = 'SELL'
        else:
            signals['bollinger'] = 'HOLD'
        
        return signals
