"""
Academic Proven Trading Strategies
Implements strategies from peer-reviewed research papers
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod


class StrategyType(Enum):
    """Strategy categories."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    STATISTICAL_ARBITRAGE = "statistical_arbitrage"
    MACHINE_LEARNING = "machine_learning"
    HYBRID = "hybrid"


@dataclass
class StrategySignal:
    """Trading signal."""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0-1
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    timestamp: datetime
    metadata: Dict[str, any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """Base class for all strategies."""
    
    def __init__(self, name: str, params: Dict[str, any]):
        self.name = name
        self.params = params
        self.logger = logging.getLogger(__name__)

    def _resolve_symbol(self, data: pd.DataFrame) -> str:
        """Resolve the instrument from explicit strategy context, never the index."""
        symbol = data.attrs.get("symbol") or self.params.get("symbol")
        if not symbol or not isinstance(symbol, str):
            self.logger.warning("Strategy data has no explicit symbol; returning UNKNOWN for analysis only")
            return "UNKNOWN"
        return symbol
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        """Generate trading signals from data."""
        pass
    
    @abstractmethod
    def validate_params(self) -> bool:
        """Validate strategy parameters."""
        pass


class MomentumStrategy(BaseStrategy):
    """
    Momentum Strategy based on Jegadeesh and Titman (1993)
    "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency"
    
    Logic: Buy assets that have performed well over the past 3-12 months
    """
    
    def __init__(self, params: Dict[str, any] = None):
        default_params = {
            'lookback_period': 20,  # Trading days
            'holding_period': 5,
            'top_n': 10,
            'momentum_threshold': 0.02  # 2% minimum return
        }
        params = {**default_params, **(params or {})}
        super().__init__("Academic Momentum", params)
    
    def validate_params(self) -> bool:
        return (
            self.params['lookback_period'] > 0 and
            self.params['holding_period'] > 0 and
            0 < self.params['top_n'] <= 100
        )
    
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        if not self.validate_params():
            self.logger.error("Invalid parameters")
            return []
        
        if len(data) < self.params['lookback_period']:
            return []
        
        signals = []
        
        # Calculate momentum (returns over lookback period)
        returns = data['close'].pct_change(self.params['lookback_period'])
        latest_return = returns.iloc[-1]
        
        # Calculate volatility for position sizing
        volatility = data['close'].pct_change().std() * np.sqrt(252)
        
        current_price = data['close'].iloc[-1]
        
        if latest_return > self.params['momentum_threshold']:
            # Buy signal - momentum is positive
            atr = self._calculate_atr(data)
            stop_loss = current_price - (atr * 2)
            take_profit = current_price + (atr * 3)
            
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='BUY',
                confidence=min(abs(latest_return) * 10, 1.0),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self._calculate_position_size(volatility),
                timestamp=datetime.now(),
                metadata={
                    'momentum_return': latest_return,
                    'volatility': volatility
                }
            )
            signals.append(signal)
        
        elif latest_return < -self.params['momentum_threshold']:
            # Sell signal - momentum is negative
            atr = self._calculate_atr(data)
            stop_loss = current_price + (atr * 2)
            take_profit = current_price - (atr * 3)
            
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='SELL',
                confidence=min(abs(latest_return) * 10, 1.0),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self._calculate_position_size(volatility),
                timestamp=datetime.now(),
                metadata={
                    'momentum_return': latest_return,
                    'volatility': volatility
                }
            )
            signals.append(signal)
        
        return signals
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    def _calculate_position_size(self, volatility: float) -> float:
        """Calculate position size based on volatility."""
        risk_per_trade = 0.02  # 2% risk
        base_size = 1.0
        
        # Adjust for volatility - lower volatility = larger position
        if volatility > 0:
            adjusted_size = base_size / volatility
            return min(adjusted_size, 2.0)  # Cap at 2x
        
        return base_size


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy based on De Bondt and Thaler (1985)
    "Does the Stock Market Overreact?"
    
    Logic: Buy assets that have underperformed recently (oversold)
    """
    
    def __init__(self, params: Dict[str, any] = None):
        default_params = {
            'lookback_period': 20,
            'entry_threshold': -2.0,  # Z-score threshold
            'exit_threshold': 0.0,
            'bb_period': 20,
            'bb_std': 2.0
        }
        params = {**default_params, **(params or {})}
        super().__init__("Academic Mean Reversion", params)
    
    def validate_params(self) -> bool:
        return (
            self.params['lookback_period'] > 0 and
            self.params['entry_threshold'] < 0 and
            self.params['bb_period'] > 0
        )
    
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        if not self.validate_params():
            self.logger.error("Invalid parameters")
            return []
        
        if len(data) < self.params['lookback_period']:
            return []
        
        signals = []
        
        # Calculate Bollinger Bands
        sma = data['close'].rolling(window=self.params['bb_period']).mean()
        std = data['close'].rolling(window=self.params['bb_period']).std()
        upper_band = sma + (std * self.params['bb_std'])
        lower_band = sma - (std * self.params['bb_std'])
        
        # Calculate Z-score
        z_score = (data['close'] - sma) / std
        
        current_price = data['close'].iloc[-1]
        current_z = z_score.iloc[-1]
        
        # Calculate volatility
        volatility = data['close'].pct_change().std() * np.sqrt(252)
        
        if current_z < self.params['entry_threshold']:
            # Buy signal - price is below lower band (oversold)
            atr = self._calculate_atr(data)
            stop_loss = current_price - (atr * 1.5)
            take_profit = sma.iloc[-1]  # Target mean reversion
            
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='BUY',
                confidence=min(abs(current_z) / 2, 1.0),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self._calculate_position_size(volatility, abs(current_z)),
                timestamp=datetime.now(),
                metadata={
                    'z_score': current_z,
                    'lower_band': lower_band.iloc[-1],
                    'upper_band': upper_band.iloc[-1]
                }
            )
            signals.append(signal)
        
        elif current_z > -self.params['entry_threshold']:
            # Sell signal - price is above upper band (overbought)
            atr = self._calculate_atr(data)
            stop_loss = current_price + (atr * 1.5)
            take_profit = sma.iloc[-1]  # Target mean reversion
            
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='SELL',
                confidence=min(current_z / 2, 1.0),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self._calculate_position_size(volatility, current_z),
                timestamp=datetime.now(),
                metadata={
                    'z_score': current_z,
                    'lower_band': lower_band.iloc[-1],
                    'upper_band': upper_band.iloc[-1]
                }
            )
            signals.append(signal)
        
        return signals
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    def _calculate_position_size(self, volatility: float, z_score: float) -> float:
        """Calculate position size based on volatility and z-score."""
        risk_per_trade = 0.02
        base_size = 1.0
        
        # Higher z-score (more extreme) = larger position
        z_adjustment = min(abs(z_score) / 2, 2.0)
        
        if volatility > 0:
            adjusted_size = (base_size * z_adjustment) / volatility
            return min(adjusted_size, 2.0)
        
        return base_size * z_adjustment


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Strategy based on Brock, Lakonishok, and LeBaron (1992)
    "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns"
    
    Logic: Buy when price breaks above resistance, sell when breaks below support
    """
    
    def __init__(self, params: Dict[str, any] = None):
        default_params = {
            'lookback_period': 20,
            'breakout_threshold': 0.01,  # 1% above/below
            'volume_confirmation': True,
            'volume_multiplier': 1.5
        }
        params = {**default_params, **(params or {})}
        super().__init__("Academic Breakout", params)
    
    def validate_params(self) -> bool:
        return (
            self.params['lookback_period'] > 0 and
            0 < self.params['breakout_threshold'] < 1
        )
    
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        if not self.validate_params():
            self.logger.error("Invalid parameters")
            return []
        
        if len(data) < self.params['lookback_period']:
            return []
        
        signals = []
        
        # Calculate levels from completed candles only. Including the active
        # candle makes a standard OHLC breakout impossible.
        highest_high = data['high'].shift(1).rolling(window=self.params['lookback_period']).max()
        lowest_low = data['low'].shift(1).rolling(window=self.params['lookback_period']).min()
        
        current_price = data['close'].iloc[-1]
        current_high = highest_high.iloc[-1]
        current_low = lowest_low.iloc[-1]
        
        # Volume analysis
        avg_volume = data['volume'].rolling(window=20).mean()
        current_volume = data['volume'].iloc[-1]
        volume_confirmed = current_volume > (avg_volume.iloc[-1] * self.params['volume_multiplier'])
        
        # Calculate volatility
        volatility = data['close'].pct_change().std() * np.sqrt(252)
        
        # Check for breakout
        if current_price > current_high * (1 + self.params['breakout_threshold']):
            if not self.params['volume_confirmation'] or volume_confirmed:
                # Buy breakout
                atr = self._calculate_atr(data)
                stop_loss = current_low  # Below recent low
                take_profit = current_price + (atr * 3)
                
                signal = StrategySignal(
                    symbol=self._resolve_symbol(data),
                    action='BUY',
                    confidence=0.8,
                    entry_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_size=self._calculate_position_size(volatility),
                    timestamp=datetime.now(),
                    metadata={
                        'breakout_level': current_high,
                        'volume_confirmed': volume_confirmed
                    }
                )
                signals.append(signal)
        
        elif current_price < current_low * (1 - self.params['breakout_threshold']):
            if not self.params['volume_confirmation'] or volume_confirmed:
                # Sell breakout
                atr = self._calculate_atr(data)
                stop_loss = current_high  # Above recent high
                take_profit = current_price - (atr * 3)
                
                signal = StrategySignal(
                    symbol=self._resolve_symbol(data),
                    action='SELL',
                    confidence=0.8,
                    entry_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_size=self._calculate_position_size(volatility),
                    timestamp=datetime.now(),
                    metadata={
                        'breakdown_level': current_low,
                        'volume_confirmed': volume_confirmed
                    }
                )
                signals.append(signal)
        
        return signals
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    def _calculate_position_size(self, volatility: float) -> float:
        """Calculate position size based on volatility."""
        risk_per_trade = 0.02
        base_size = 1.0
        
        if volatility > 0:
            adjusted_size = base_size / volatility
            return min(adjusted_size, 2.0)
        
        return base_size


class DualMomentumStrategy(BaseStrategy):
    """
    Dual Momentum Strategy based on Gary Antonacci (2013)
    "Dual Momentum Investing"
    
    Logic: Combine absolute momentum (time series) and relative momentum (cross-sectional)
    """
    
    def __init__(self, params: Dict[str, any] = None):
        default_params = {
            'lookback_period': 12,  # Months
            'risk_free_rate': 0.02,
            'n_assets': 3
        }
        params = {**default_params, **(params or {})}
        super().__init__("Dual Momentum", params)
    
    def validate_params(self) -> bool:
        return self.params['lookback_period'] > 0
    
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        if not self.validate_params():
            self.logger.error("Invalid parameters")
            return []
        
        if len(data) < self.params['lookback_period']:
            return []
        
        signals = []
        
        # Calculate absolute momentum (time series)
        returns = data['close'].pct_change(self.params['lookback_period'])
        latest_return = returns.iloc[-1]
        
        # Calculate risk-free rate adjusted return
        risk_free_adjusted = latest_return - self.params['risk_free_rate']
        
        current_price = data['close'].iloc[-1]
        
        # Calculate volatility
        volatility = data['close'].pct_change().std() * np.sqrt(252)
        
        if risk_free_adjusted > 0:
            # Absolute momentum positive - buy
            atr = self._calculate_atr(data)
            stop_loss = current_price - (atr * 2)
            take_profit = current_price + (atr * 4)
            
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='BUY',
                confidence=min(abs(risk_free_adjusted) * 5, 1.0),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self._calculate_position_size(volatility, risk_free_adjusted),
                timestamp=datetime.now(),
                metadata={
                    'absolute_momentum': risk_free_adjusted,
                    'risk_free_rate': self.params['risk_free_rate']
                }
            )
            signals.append(signal)
        
        else:
            # Absolute momentum negative - stay in cash (or sell)
            signal = StrategySignal(
                symbol=self._resolve_symbol(data),
                action='SELL',
                confidence=0.7,
                entry_price=current_price,
                stop_loss=current_price * 1.05,
                take_profit=current_price * 0.95,
                position_size=0,
                timestamp=datetime.now(),
                metadata={
                    'absolute_momentum': risk_free_adjusted,
                    'risk_free_rate': self.params['risk_free_rate']
                }
            )
            signals.append(signal)
        
        return signals
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    def _calculate_position_size(self, volatility: float, momentum: float) -> float:
        """Calculate position size based on volatility and momentum."""
        risk_per_trade = 0.02
        base_size = 1.0
        
        # Higher momentum = larger position
        momentum_adjustment = min(abs(momentum) * 2, 2.0)
        
        if volatility > 0:
            adjusted_size = (base_size * momentum_adjustment) / volatility
            return min(adjusted_size, 2.0)
        
        return base_size * momentum_adjustment


class StrategyLibrary:
    """Library of academic trading strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.logger = logging.getLogger(__name__)
        
        # Register strategies
        self._register_strategies()
    
    def _register_strategies(self):
        """Register all available strategies."""
        self.strategies['momentum'] = MomentumStrategy
        self.strategies['mean_reversion'] = MeanReversionStrategy
        self.strategies['breakout'] = BreakoutStrategy
        self.strategies['dual_momentum'] = DualMomentumStrategy
        
        self.logger.info(f"Registered {len(self.strategies)} strategies")
    
    def get_strategy(self, name: str, params: Dict[str, any] = None) -> Optional[BaseStrategy]:
        """Get a strategy instance by name."""
        if name not in self.strategies:
            self.logger.error(f"Strategy {name} not found")
            return None
        
        return self.strategies[name](params)
    
    def list_strategies(self) -> List[str]:
        """List all available strategies."""
        return list(self.strategies.keys())
    
    def get_strategy_info(self, name: str) -> Optional[Dict[str, any]]:
        """Get information about a strategy."""
        if name not in self.strategies:
            return None
        
        strategy_class = self.strategies[name]
        instance = strategy_class()
        
        return {
            'name': instance.name,
            'params': instance.params,
            'description': self._get_strategy_description(name)
        }
    
    def _get_strategy_description(self, name: str) -> str:
        """Get strategy description."""
        descriptions = {
            'momentum': 'Based on Jegadeesh and Titman (1993). Buy assets with positive momentum over 3-12 months.',
            'mean_reversion': 'Based on De Bondt and Thaler (1985). Buy oversold assets expecting mean reversion.',
            'breakout': 'Based on Brock et al. (1992). Buy on breakouts above resistance, sell on breakdowns.',
            'dual_momentum': 'Based on Gary Antonacci (2013). Combines absolute and relative momentum.'
        }
        
        return descriptions.get(name, 'No description available')

