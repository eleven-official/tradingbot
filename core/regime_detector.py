"""
Real-time Market Regime Detection System
Detects and adapts to different market regimes for optimal trading performance
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque, defaultdict
from datetime import datetime, timedelta


class MarketRegime(Enum):
    """Market regime types."""
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"
    UNCERTAIN = "uncertain"


@dataclass
class RegimeCharacteristics:
    """Characteristics of a market regime."""
    regime: MarketRegime
    volatility: float
    trend_strength: float
    momentum: float
    volume_profile: str
    support_level: float
    resistance_level: float
    confidence: float
    duration_minutes: int
    expected_moves: List[str]


class RealTimeRegimeDetector:
    """
    Real-time market regime detection using multiple indicators
    and statistical analysis for adaptive trading.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.regime_config = config.get('regime_detector', {})
        
        # Configuration
        self.enabled = self.regime_config.get('enabled', True)
        self.lookback_period = self.regime_config.get('lookback_period', 100)
        self.volatility_threshold = self.regime_config.get('volatility_threshold', 0.02)
        self.trend_threshold = self.regime_config.get('trend_threshold', 0.01)
        self.min_regime_duration = self.regime_config.get('min_regime_duration', 30)
        
        # State tracking
        self.current_regime: Optional[MarketRegime] = None
        self.regime_history: deque = deque(maxlen=100)
        self.regime_start_time: Optional[datetime] = None
        self.regime_transitions: List[Tuple[MarketRegime, MarketRegime, datetime]] = []
        
        # Data storage
        self.price_history: deque = deque(maxlen=self.lookback_period)
        self.volume_history: deque = deque(maxlen=self.lookback_period)
        
        # Indicator states
        self.current_volatility = 0.0
        self.current_trend_strength = 0.0
        self.current_momentum = 0.0
        
        logging.info("Real-time Regime Detector initialized")
    
    def update_market_data(self, price: float, volume: float, timestamp: Optional[datetime] = None):
        """Update market data for regime detection."""
        if not self.enabled:
            return
        
        self.price_history.append(price)
        self.volume_history.append(volume)
        
        if len(self.price_history) >= 20:  # Minimum for calculation
            self._update_indicators()
            new_regime = self._detect_regime()
            
            if new_regime != self.current_regime:
                self._handle_regime_change(new_regime, timestamp or datetime.now())
    
    def _update_indicators(self):
        """Update technical indicators for regime detection."""
        try:
            prices = list(self.price_history)
            volumes = list(self.volume_history)
            
            # Calculate volatility (rolling standard deviation)
            returns = pd.Series(prices).pct_change().dropna()
            self.current_volatility = returns.std() if len(returns) > 0 else 0.0
            
            # Calculate trend strength (linear regression slope)
            if len(prices) >= 20:
                x = np.arange(len(prices))
                slope, _ = np.polyfit(x, prices, 1)
                self.current_trend_strength = slope / np.mean(prices) if np.mean(prices) > 0 else 0.0
            
            # Calculate momentum (price change over period)
            if len(prices) >= 10:
                self.current_momentum = (prices[-1] - prices[-10]) / prices[-10]
            
        except Exception as e:
            logging.error(f"Indicator update error: {e}")
    
    def _detect_regime(self) -> MarketRegime:
        """Detect current market regime based on indicators."""
        try:
            if len(self.price_history) < 20:
                return MarketRegime.UNCERTAIN
            
            # Get current indicators
            volatility = self.current_volatility
            trend_strength = self.current_trend_strength
            momentum = self.current_momentum
            
            # Volatility analysis
            high_volatility = volatility > self.volatility_threshold
            low_volatility = volatility < self.volatility_threshold * 0.5
            
            # Trend analysis
            strong_bull = trend_strength > self.trend_threshold and momentum > 0.01
            strong_bear = trend_strength < -self.trend_threshold and momentum < -0.01
            weak_trend = abs(trend_strength) < self.trend_threshold * 0.5
            
            # Regime determination
            if high_volatility:
                if momentum > 0.02:
                    return MarketRegime.BREAKOUT_UP
                elif momentum < -0.02:
                    return MarketRegime.BREAKOUT_DOWN
                else:
                    return MarketRegime.HIGH_VOLATILITY
            elif low_volatility:
                return MarketRegime.LOW_VOLATILITY
            elif strong_bull:
                return MarketRegime.BULL_TREND
            elif strong_bear:
                return MarketRegime.BEAR_TREND
            elif weak_trend:
                return MarketRegime.SIDEWAYS
            else:
                return MarketRegime.UNCERTAIN
                
        except Exception as e:
            logging.error(f"Regime detection error: {e}")
            return MarketRegime.UNCERTAIN
    
    def _handle_regime_change(self, new_regime: MarketRegime, timestamp: datetime):
        """Handle regime transition."""
        # Check minimum duration requirement
        if self.regime_start_time:
            duration = (timestamp - self.regime_start_time).total_seconds() / 60
            if duration < self.min_regime_duration:
                logging.debug(f"Regime change rejected - duration {duration:.1f}m below minimum {self.min_regime_duration}m")
                return
        
        # Record transition
        if self.current_regime:
            self.regime_transitions.append((self.current_regime, new_regime, timestamp))
            logging.info(f"Regime transition: {self.current_regime.value} -> {new_regime.value}")
        
        # Update current regime
        self.current_regime = new_regime
        self.regime_start_time = timestamp
        
        # Add to history
        self.regime_history.append({
            'regime': new_regime,
            'timestamp': timestamp,
            'volatility': self.current_volatility,
            'trend_strength': self.current_trend_strength,
            'momentum': self.current_momentum
        })
    
    def get_current_regime(self) -> Optional[MarketRegime]:
        """Get current market regime."""
        return self.current_regime
    
    def get_regime_characteristics(self) -> Optional[RegimeCharacteristics]:
        """Get detailed characteristics of current regime."""
        if not self.current_regime:
            return None
        
        try:
            prices = list(self.price_history)
            if len(prices) < 20:
                return None
            
            # Calculate support and resistance
            recent_prices = prices[-20:]
            support = min(recent_prices)
            resistance = max(recent_prices)
            
            # Determine expected moves based on regime
            expected_moves = self._get_expected_moves(self.current_regime)
            
            # Calculate confidence based on regime stability
            confidence = self._calculate_regime_confidence()
            
            # Calculate duration
            duration = 0
            if self.regime_start_time:
                duration = int((datetime.now() - self.regime_start_time).total_seconds() / 60)
            
            return RegimeCharacteristics(
                regime=self.current_regime,
                volatility=self.current_volatility,
                trend_strength=self.current_trend_strength,
                momentum=self.current_momentum,
                volume_profile="high" if self.current_volatility > self.volatility_threshold else "normal",
                support_level=support,
                resistance_level=resistance,
                confidence=confidence,
                duration_minutes=duration,
                expected_moves=expected_moves
            )
            
        except Exception as e:
            logging.error(f"Regime characteristics error: {e}")
            return None
    
    def _get_expected_moves(self, regime: MarketRegime) -> List[str]:
        """Get expected market moves for a regime."""
        regime_moves = {
            MarketRegime.BULL_TREND: ["continuation_up", "pullback", "breakout"],
            MarketRegime.BEAR_TREND: ["continuation_down", "rally", "breakdown"],
            MarketRegime.SIDEWAYS: ["range_trading", "false_breakout", "consolidation"],
            MarketRegime.HIGH_VOLATILITY: ["explosive_moves", "reversals", "gap_moves"],
            MarketRegime.LOW_VOLATILITY: ["slow_drift", "accumulation", "distribution"],
            MarketRegime.BREAKOUT_UP: ["acceleration_up", "consolidation", "reversal"],
            MarketRegime.BREAKOUT_DOWN: ["acceleration_down", "consolidation", "reversal"],
            MarketRegime.UNCERTAIN: ["uncertain", "mixed_signals", "low_confidence"]
        }
        return regime_moves.get(regime, ["unknown"])
    
    def _calculate_regime_confidence(self) -> float:
        """Calculate confidence in current regime."""
        try:
            if not self.regime_history:
                return 0.5
            
            # Check recent regime stability
            recent_regimes = list(self.regime_history)[-10:]
            if len(recent_regimes) < 2:
                return 0.5
            
            # Count how many of the last regimes match current
            matches = sum(1 for r in recent_regimes if r['regime'] == self.current_regime)
            confidence = matches / len(recent_regimes)
            
            # Factor in indicator strength
            indicator_confidence = min(1.0, abs(self.current_trend_strength) / self.trend_threshold * 2)
            
            return (confidence + indicator_confidence) / 2
            
        except Exception as e:
            logging.error(f"Confidence calculation error: {e}")
            return 0.5
    
    def get_regime_recommendations(self) -> List[str]:
        """Get trading recommendations based on current regime."""
        if not self.current_regime:
            return ["No regime detected - proceed with caution"]
        
        characteristics = self.get_regime_characteristics()
        if not characteristics:
            return ["Unable to determine regime characteristics"]
        
        recommendations = []
        
        # Regime-specific recommendations
        regime_recommendations = {
            MarketRegime.BULL_TREND: [
                "Focus on long positions and trend-following strategies",
                "Use pullbacks as entry opportunities",
                "Set wider stop-losses to allow for volatility",
                "Consider trailing stops to protect profits"
            ],
            MarketRegime.BEAR_TREND: [
                "Focus on short positions or stay in cash",
                "Use rallies as shorting opportunities",
                "Tighten stop-losses due to downward momentum",
                "Consider hedging strategies"
            ],
            MarketRegime.SIDEWAYS: [
                "Use range-trading strategies",
                "Buy at support, sell at resistance",
                "Use mean-reversion strategies",
                "Avoid trend-following approaches"
            ],
            MarketRegime.HIGH_VOLATILITY: [
                "Reduce position sizes significantly",
                "Use wider stop-losses",
                "Consider options for defined risk",
                "Focus on short-term trades"
            ],
            MarketRegime.LOW_VOLATILITY: [
                "Consider increasing position sizes slightly",
                "Look for breakout opportunities",
                "Use tighter stop-losses",
                "Monitor for volatility expansion"
            ],
            MarketRegime.BREAKOUT_UP: [
                "Enter long positions on breakout confirmation",
                "Use momentum strategies",
                "Set aggressive take-profit targets",
                "Be prepared for potential pullbacks"
            ],
            MarketRegime.BREAKOUT_DOWN: [
                "Enter short positions on breakdown confirmation",
                "Use momentum strategies",
                "Set aggressive take-profit targets",
                "Be prepared for potential rallies"
            ],
            MarketRegime.UNCERTAIN: [
                "Reduce trading activity",
                "Wait for clearer signals",
                "Use smaller position sizes",
                "Focus on risk management"
            ]
        }
        
        regime_recs = regime_recommendations.get(self.current_regime, [])
        recommendations.extend(regime_recs)
        
        # Add confidence-based recommendations
        if characteristics.confidence < 0.5:
            recommendations.append("Low regime confidence - reduce position sizes")
        elif characteristics.confidence > 0.8:
            recommendations.append("High regime confidence - can increase position sizes")
        
        return recommendations
    
    def get_regime_statistics(self) -> Dict[str, Any]:
        """Get statistics about regime detection."""
        return {
            'current_regime': self.current_regime.value if self.current_regime else None,
            'regime_duration_minutes': int((datetime.now() - self.regime_start_time).total_seconds() / 60) if self.regime_start_time else 0,
            'total_transitions': len(self.regime_transitions),
            'current_volatility': self.current_volatility,
            'current_trend_strength': self.current_trend_strength,
            'current_momentum': self.current_momentum,
            'regime_history_length': len(self.regime_history),
            'confidence': self._calculate_regime_confidence() if self.current_regime else 0.0
        }
    
    def predict_regime_change(self) -> Optional[Tuple[MarketRegime, float]]:
        """Predict likely next regime and probability."""
        if not self.current_regime or len(self.regime_history) < 5:
            return None
        
        try:
            # Analyze recent transitions
            recent_transitions = self.regime_transitions[-10:] if self.regime_transitions else []
            
            if not recent_transitions:
                return None
            
            # Count transition patterns
            transition_counts = defaultdict(int)
            for old_regime, new_regime, _ in recent_transitions:
                if old_regime == self.current_regime:
                    transition_counts[new_regime] += 1
            
            if not transition_counts:
                return None
            
            # Find most likely next regime
            total_transitions = sum(transition_counts.values())
            likely_regime = max(transition_counts.items(), key=lambda x: x[1])
            probability = likely_regime[1] / total_transitions
            
            return (likely_regime[0], probability)
            
        except Exception as e:
            logging.error(f"Regime prediction error: {e}")
            return None