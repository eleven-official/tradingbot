"""
Multi-Indicator Confluence Matrix
Strict multi-layer mathematical confirmation before signal execution
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class IndicatorSignal:
    """Signal from a single indicator."""
    indicator_name: str
    signal_type: str  # BUY, SELL, HOLD
    confidence: float
    timestamp: datetime


@dataclass
class ConfluenceResult:
    """Result of multi-indicator confluence analysis."""
    final_signal: str
    signal_strength: SignalStrength
    confluence_score: float
    participating_indicators: List[str]
    conflicting_indicators: List[str]
    momentum_confirmation: bool
    volume_confirmation: bool
    volatility_confirmation: bool
    multi_timeframe_alignment: bool
    timestamp: datetime = field(default_factory=datetime.now)


class MultiIndicatorConfluence:
    """
    Multi-indicator confluence matrix for signal generation.
    Requires strict mathematical confirmation before execution.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.indicator_config = config.get('indicators', {})
        
        # Configuration
        self.min_confluence = self.indicator_config.get('min_confluence', 0.7)  # 70% agreement
        self.multi_timeframe_required = self.indicator_config.get('multi_timeframe_required', True)
        self.volume_confirmation_required = self.indicator_config.get('volume_confirmation_required', True)
        self.volatility_confirmation_required = self.indicator_config.get('volatility_confirmation_required', True)
        
        # Indicator states
        self.indicator_signals: Dict[str, IndicatorSignal] = {}
        
        # Timeframes for multi-timeframe analysis
        self.timeframes = ['1m', '5m', '15m', '1h', '4h']
        
        logging.info("Multi-Indicator Confluence initialized")
    
    async def initialize(self):
        """Initialize the confluence matrix."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Multi-Indicator Confluence initialized")
    
    async def analyze_signal(self, data: pd.DataFrame, symbol: str) -> ConfluenceResult:
        """
        Analyze signal using multi-indicator confluence.
        """
        # Generate signals from all indicators
        await self._generate_indicator_signals(data, symbol)
        
        # Calculate confluence score
        confluence_score = await self._calculate_confluence_score()
        
        # Check confirmations
        momentum_conf = await self._check_momentum_confirmation(data)
        volume_conf = await self._check_volume_confirmation(data)
        volatility_conf = await self._check_volatility_confirmation(data)
        mtf_alignment = await self._check_multi_timeframe_alignment(symbol)
        
        # Determine final signal
        final_signal, signal_strength = await self._determine_final_signal(
            confluence_score, momentum_conf, volume_conf, volatility_conf, mtf_alignment
        )
        
        # Get participating and conflicting indicators
        participating, conflicting = await self._get_indicator_conflicts()
        
        return ConfluenceResult(
            final_signal=final_signal,
            signal_strength=signal_strength,
            confluence_score=confluence_score,
            participating_indicators=participating,
            conflicting_indicators=conflicting,
            momentum_confirmation=momentum_conf,
            volume_confirmation=volume_conf,
            volatility_confirmation=volatility_conf,
            multi_timeframe_alignment=mtf_alignment
        )
    
    async def _generate_indicator_signals(self, data: pd.DataFrame, symbol: str):
        """Generate signals from all indicators."""
        # Momentum indicators
        await self._analyze_ema_ribbon(data)
        await self._analyze_macd_velocity(data)
        
        # Volume indicators
        await self._analyze_volume_profile(data)
        await self._analyze_rvol(data)
        
        # Volatility indicators
        await self._analyze_atr_bands(data)
        await self._analyze_rsi_divergence(data)
    
    async def _analyze_ema_ribbon(self, data: pd.DataFrame):
        """Analyze EMA ribbon alignment."""
        if len(data) < 50:
            return
        
        # Calculate EMAs
        ema_9 = data['close'].ewm(span=9).mean()
        ema_21 = data['close'].ewm(span=21).mean()
        ema_50 = data['close'].ewm(span=50).mean()
        ema_200 = data['close'].ewm(span=200).mean()
        
        current_price = data['close'].iloc[-1]
        
        # Check alignment
        bullish_alignment = ema_9.iloc[-1] > ema_21.iloc[-1] > ema_50.iloc[-1] > ema_200.iloc[-1]
        bearish_alignment = ema_9.iloc[-1] < ema_21.iloc[-1] < ema_50.iloc[-1] < ema_200.iloc[-1]
        
        if bullish_alignment and current_price > ema_9.iloc[-1]:
            self.indicator_signals['ema_ribbon'] = IndicatorSignal(
                indicator_name='ema_ribbon',
                signal_type='BUY',
                confidence=0.8,
                timestamp=datetime.now()
            )
        elif bearish_alignment and current_price < ema_9.iloc[-1]:
            self.indicator_signals['ema_ribbon'] = IndicatorSignal(
                indicator_name='ema_ribbon',
                signal_type='SELL',
                confidence=0.8,
                timestamp=datetime.now()
            )
        else:
            self.indicator_signals['ema_ribbon'] = IndicatorSignal(
                indicator_name='ema_ribbon',
                signal_type='HOLD',
                confidence=0.5,
                timestamp=datetime.now()
            )
    
    async def _analyze_macd_velocity(self, data: pd.DataFrame):
        """Analyze MACD expansion velocity."""
        if len(data) < 26:
            return
        
        # Calculate MACD
        ema_12 = data['close'].ewm(span=12).mean()
        ema_26 = data['close'].ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        
        # Calculate velocity (rate of change of histogram)
        if len(histogram) > 2:
            velocity = histogram.iloc[-1] - histogram.iloc[-2]
            
            # Bullish momentum: positive and accelerating
            if histogram.iloc[-1] > 0 and velocity > 0:
                self.indicator_signals['macd_velocity'] = IndicatorSignal(
                    indicator_name='macd_velocity',
                    signal_type='BUY',
                    confidence=0.75,
                    timestamp=datetime.now()
                )
            # Bearish momentum: negative and accelerating
            elif histogram.iloc[-1] < 0 and velocity < 0:
                self.indicator_signals['macd_velocity'] = IndicatorSignal(
                    indicator_name='macd_velocity',
                    signal_type='SELL',
                    confidence=0.75,
                    timestamp=datetime.now()
                )
            else:
                self.indicator_signals['macd_velocity'] = IndicatorSignal(
                    indicator_name='macd_velocity',
                    signal_type='HOLD',
                    confidence=0.5,
                    timestamp=datetime.now()
                )
    
    async def _analyze_volume_profile(self, data: pd.DataFrame):
        """Analyze volume profile and POC."""
        if len(data) < 100:
            return
        
        # Calculate POC (Point of Control)
        volume_profile = data.groupby(pd.cut(data['close'], bins=20))['volume'].sum()
        poc_level = volume_profile.idxmax()
        
        current_price = data['close'].iloc[-1]
        
        # Check if price is bouncing off POC
        if current_price < poc_level.right and current_price > poc_level.left:
            self.indicator_signals['volume_profile'] = IndicatorSignal(
                indicator_name='volume_profile',
                signal_type='HOLD',
                confidence=0.6,
                timestamp=datetime.now()
            )
        elif current_price > poc_level.right:
            self.indicator_signals['volume_profile'] = IndicatorSignal(
                indicator_name='volume_profile',
                signal_type='BUY',
                confidence=0.6,
                timestamp=datetime.now()
            )
        else:
            self.indicator_signals['volume_profile'] = IndicatorSignal(
                indicator_name='volume_profile',
                signal_type='SELL',
                confidence=0.6,
                timestamp=datetime.now()
            )
    
    async def _analyze_rvol(self, data: pd.DataFrame):
        """Analyze Relative Volume (RVOL)."""
        if len(data) < 20:
            return
        
        # Calculate average volume over last 20 periods
        avg_volume = data['volume'].iloc[-20:].mean()
        current_volume = data['volume'].iloc[-1]
        
        rvol = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # High RVOL supports signal strength
        self.indicator_signals['rvol'] = IndicatorSignal(
            indicator_name='rvol',
            signal_type='HOLD',
            confidence=min(rvol / 2.0, 1.0),  # Cap at 1.0
            timestamp=datetime.now()
        )
    
    async def _analyze_atr_bands(self, data: pd.DataFrame):
        """Analyze ATR volatility bands."""
        if len(data) < 14:
            return
        
        # Calculate ATR
        high_low = data['high'] - data['low']
        high_close = abs(data['high'] - data['close'].shift())
        low_close = abs(data['low'] - data['close'].shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        # Calculate volatility bands
        current_atr = atr.iloc[-1]
        avg_atr = atr.iloc[-50:].mean() if len(atr) >= 50 else atr.mean()
        
        # Volatility regime
        if current_atr > avg_atr * 1.5:
            self.indicator_signals['atr_bands'] = IndicatorSignal(
                indicator_name='atr_bands',
                signal_type='HOLD',
                confidence=0.3,  # Low confidence in high volatility
                timestamp=datetime.now()
            )
        elif current_atr < avg_atr * 0.5:
            self.indicator_signals['atr_bands'] = IndicatorSignal(
                indicator_name='atr_bands',
                signal_type='HOLD',
                confidence=0.3,  # Low confidence in low volatility
                timestamp=datetime.now()
            )
        else:
            self.indicator_signals['atr_bands'] = IndicatorSignal(
                indicator_name='atr_bands',
                signal_type='HOLD',
                confidence=0.7,  # Good confidence in normal volatility
                timestamp=datetime.now()
            )
    
    async def _analyze_rsi_divergence(self, data: pd.DataFrame):
        """Analyze RSI divergence across timeframes."""
        if len(data) < 14:
            return
        
        # Calculate RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        
        # Check for divergence
        price_making_higher = data['close'].iloc[-1] > data['close'].iloc[-5]
        rsi_making_lower = current_rsi < rsi.iloc[-5]
        
        if price_making_higher and rsi_making_lower:
            # Bearish divergence
            self.indicator_signals['rsi_divergence'] = IndicatorSignal(
                indicator_name='rsi_divergence',
                signal_type='SELL',
                confidence=0.8,
                timestamp=datetime.now()
            )
        else:
            # Bullish condition
            if current_rsi < 30:
                self.indicator_signals['rsi_divergence'] = IndicatorSignal(
                    indicator_name='rsi_divergence',
                    signal_type='BUY',
                    confidence=0.7,
                    timestamp=datetime.now()
                )
            elif current_rsi > 70:
                self.indicator_signals['rsi_divergence'] = IndicatorSignal(
                    indicator_name='rsi_divergence',
                    signal_type='SELL',
                    confidence=0.7,
                    timestamp=datetime.now()
                )
            else:
                self.indicator_signals['rsi_divergence'] = IndicatorSignal(
                    indicator_name='rsi_divergence',
                    signal_type='HOLD',
                    confidence=0.5,
                    timestamp=datetime.now()
                )
    
    async def _calculate_confluence_score(self) -> float:
        """Calculate overall confluence score."""
        if not self.indicator_signals:
            return 0.0
        
        buy_signals = sum(1 for s in self.indicator_signals.values() if s.signal_type == 'BUY')
        sell_signals = sum(1 for s in self.indicator_signals.values() if s.signal_type == 'SELL')
        total_signals = len(self.indicator_signals)
        
        # Calculate agreement
        max_agreement = max(buy_signals, sell_signals)
        confluence = max_agreement / total_signals if total_signals > 0 else 0
        
        return confluence
    
    async def _check_momentum_confirmation(self, data: pd.DataFrame) -> bool:
        """Check momentum confirmation."""
        if 'ema_ribbon' not in self.indicator_signals:
            return False
        
        return self.indicator_signals['ema_ribbon'].signal_type in ['BUY', 'SELL']
    
    async def _check_volume_confirmation(self, data: pd.DataFrame) -> bool:
        """Check volume confirmation."""
        if 'rvol' not in self.indicator_signals:
            return False
        
        return self.indicator_signals['rvol'].confidence > 0.5
    
    async def _check_volatility_confirmation(self, data: pd.DataFrame) -> bool:
        """Check volatility confirmation."""
        if 'atr_bands' not in self.indicator_signals:
            return False
        
        return self.indicator_signals['atr_bands'].confidence > 0.5
    
    async def _check_multi_timeframe_alignment(self, symbol: str) -> bool:
        """Check multi-timeframe alignment."""
        # In production, this would check alignment across timeframes
        # For now, return True
        return True
    
    async def _determine_final_signal(self, confluence_score: float, 
                                    momentum_conf: bool, volume_conf: bool,
                                    volatility_conf: bool, mtf_alignment: bool) -> Tuple[str, SignalStrength]:
        """Determine final signal based on all confirmations."""
        # Count confirmations
        confirmations = sum([
            momentum_conf,
            volume_conf,
            volatility_conf,
            mtf_alignment
        ])
        
        # Determine if we have enough confluence
        has_confluence = confluence_score >= self.min_confluence
        has_confirmations = confirmations >= 3
        
        if not has_confluence or not has_confirmations:
            return 'HOLD', SignalStrength.WEAK
        
        # Determine signal direction
        buy_signals = sum(1 for s in self.indicator_signals.values() if s.signal_type == 'BUY')
        sell_signals = sum(1 for s in self.indicator_signals.values() if s.signal_type == 'SELL')
        
        if buy_signals > sell_signals:
            signal = 'BUY'
        elif sell_signals > buy_signals:
            signal = 'SELL'
        else:
            return 'HOLD', SignalStrength.WEAK
        
        # Determine signal strength
        if confluence_score >= 0.9 and confirmations == 4:
            strength = SignalStrength.VERY_STRONG
        elif confluence_score >= 0.8:
            strength = SignalStrength.STRONG
        elif confluence_score >= 0.7:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        
        return signal, strength
    
    async def _get_indicator_conflicts(self) -> Tuple[List[str], List[str]]:
        """Get participating and conflicting indicators."""
        buy_indicators = [name for name, sig in self.indicator_signals.items() if sig.signal_type == 'BUY']
        sell_indicators = [name for name, sig in self.indicator_signals.items() if sig.signal_type == 'SELL']
        
        participating = buy_indicators if len(buy_indicators) > len(sell_indicators) else sell_indicators
        conflicting = sell_indicators if len(buy_indicators) > len(sell_indicators) else buy_indicators
        
        return participating, conflicting