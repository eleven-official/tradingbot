"""
LOKI v7.0 - Multi-Timeframe Analysis System
Provides simultaneous analysis across multiple timeframes with confluence scoring
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Timeframe(Enum):
    """Available timeframes"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class Signal(Enum):
    """Trading signal"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class TimeframeAnalysis:
    """Analysis for a single timeframe"""
    timeframe: Timeframe
    signal: Signal
    strength: float  # 0-100%
    trend: str  # "bullish", "bearish", "neutral"
    momentum: float  # -100 to +100
    rsi: float
    macd_signal: str  # "bullish", "bearish", "neutral"
    volume_trend: str  # "increasing", "decreasing", "stable"
    key_levels: Dict[str, float]
    confidence: float  # 0-100%


@dataclass
class ConfluenceAnalysis:
    """Multi-timeframe confluence analysis"""
    timestamp: datetime
    overall_signal: Signal
    confluence_score: float  # 0-100%, higher = more agreement
    timeframe_analyses: Dict[Timeframe, TimeframeAnalysis]
    aligned_timeframes: List[Timeframe]
    conflicting_timeframes: List[Timeframe]
    recommended_action: str
    risk_level: str  # "low", "medium", "high"
    confidence: float  # 0-100%


@dataclass
class MarketStructure:
    """Market structure analysis"""
    higher_highs: bool
    higher_lows: bool
    lower_highs: bool
    lower_lows: bool
    structure_type: str  # "uptrend", "downtrend", "ranging", "choppy"
    breakout_level: Optional[float]


class MultiTimeframeAnalyzer:
    """
    Analyzes market across multiple timeframes simultaneously
    
    Provides:
    - Individual timeframe analysis
    - Cross-timeframe confluence scoring
    - Structure alignment detection
    - Trade signal generation
    """
    
    def __init__(self):
        self.timeframes = [
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.H1,
            Timeframe.H4,
            Timeframe.D1
        ]
        
        # Timeframe weights (longer timeframes have more weight)
        self.timeframe_weights = {
            Timeframe.M1: 0.05,
            Timeframe.M5: 0.10,
            Timeframe.M15: 0.15,
            Timeframe.H1: 0.20,
            Timeframe.H4: 0.25,
            Timeframe.D1: 0.25
        }
        
        self.analysis_history: List[ConfluenceAnalysis] = []
        
        logger.info("Multi-Timeframe Analyzer initialized")
    
    def analyze_timeframe(
        self,
        prices: pd.Series,
        volume: Optional[pd.Series],
        timeframe: Timeframe
    ) -> TimeframeAnalysis:
        """
        Analyze a single timeframe
        
        Args:
            prices: Price series for the timeframe
            volume: Optional volume series
            timeframe: Timeframe being analyzed
            
        Returns:
            TimeframeAnalysis with indicators and signal
        """
        try:
            if len(prices) < 50:
                logger.warning(f"Insufficient data for {timeframe.value}: {len(prices)} bars")
                return self._fallback_analysis(timeframe, prices)
            
            current_price = float(prices.iloc[-1])
            
            # Calculate indicators
            rsi = self._calculate_rsi(prices)
            macd_signal = self._calculate_macd_signal(prices)
            trend = self._determine_trend(prices)
            momentum = self._calculate_momentum(prices)
            
            # Volume analysis
            volume_trend = "stable"
            if volume is not None and len(volume) >= 20:
                volume_trend = self._analyze_volume_trend(volume)
            
            # Identify key levels
            key_levels = self._identify_key_levels(prices)
            
            # Generate signal based on multiple factors
            signal, strength = self._generate_signal(
                rsi=rsi,
                macd_signal=macd_signal,
                trend=trend,
                momentum=momentum,
                volume_trend=volume_trend
            )
            
            # Calculate confidence
            confidence = self._calculate_confidence(
                rsi, momentum, trend, volume_trend
            )
            
            analysis = TimeframeAnalysis(
                timeframe=timeframe,
                signal=signal,
                strength=strength,
                trend=trend,
                momentum=momentum,
                rsi=rsi,
                macd_signal=macd_signal,
                volume_trend=volume_trend,
                key_levels=key_levels,
                confidence=confidence
            )
            
            logger.debug(f"{timeframe.value}: {signal.value} ({strength:.1f}%), trend: {trend}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Timeframe analysis failed for {timeframe.value}: {e}")
            return self._fallback_analysis(timeframe, prices)
    
    def analyze_confluence(
        self,
        multi_timeframe_data: Dict[Timeframe, tuple]
    ) -> ConfluenceAnalysis:
        """
        Analyze confluence across all timeframes
        
        Args:
            multi_timeframe_data: Dict mapping Timeframe to (prices, volume) tuples
            
        Returns:
            ConfluenceAnalysis with overall signal and scoring
        """
        try:
            timestamp = datetime.now()
            
            # Analyze each timeframe
            timeframe_analyses = {}
            for tf, (prices, volume) in multi_timeframe_data.items():
                analysis = self.analyze_timeframe(prices, volume, tf)
                timeframe_analyses[tf] = analysis
            
            # Calculate confluence score
            confluence_score = self._calculate_confluence_score(timeframe_analyses)
            
            # Determine overall signal (weighted by timeframe)
            overall_signal = self._determine_overall_signal(timeframe_analyses)
            
            # Find aligned and conflicting timeframes
            aligned_tfs = self._find_aligned_timeframes(timeframe_analyses, overall_signal)
            conflicting_tfs = self._find_conflicting_timeframes(timeframe_analyses, overall_signal)
            
            # Generate recommendation
            recommendation = self._generate_recommendation(
                overall_signal, confluence_score, aligned_tfs
            )
            
            # Assess risk level
            risk_level = self._assess_risk_level(
                confluence_score, len(conflicting_tfs), timeframe_analyses
            )
            
            # Calculate overall confidence
            confidence = self._calculate_overall_confidence(
                timeframe_analyses, confluence_score
            )
            
            confluence = ConfluenceAnalysis(
                timestamp=timestamp,
                overall_signal=overall_signal,
                confluence_score=confluence_score,
                timeframe_analyses=timeframe_analyses,
                aligned_timeframes=aligned_tfs,
                conflicting_timeframes=conflicting_tfs,
                recommended_action=recommendation,
                risk_level=risk_level,
                confidence=confidence
            )
            
            self.analysis_history.append(confluence)
            
            logger.info(
                f"Confluence: {overall_signal.value} (score: {confluence_score:.1f}%, "
                f"aligned: {len(aligned_tfs)}, conflicting: {len(conflicting_tfs)})"
            )
            
            return confluence
            
        except Exception as e:
            logger.error(f"Confluence analysis failed: {e}")
            return self._fallback_confluence()
    
    def analyze_market_structure(
        self,
        prices: pd.Series,
        lookback: int = 50
    ) -> MarketStructure:
        """
        Analyze market structure (higher highs/lows, etc.)
        
        Args:
            prices: Price series
            lookback: Number of periods to analyze
            
        Returns:
            MarketStructure analysis
        """
        try:
            if len(prices) < lookback:
                lookback = len(prices)
            
            recent_prices = prices.iloc[-lookback:]
            
            # Find swing highs and lows
            highs = []
            lows = []
            
            for i in range(5, len(recent_prices) - 5):
                # Swing high
                if recent_prices.iloc[i] == recent_prices.iloc[i-5:i+5].max():
                    highs.append(float(recent_prices.iloc[i]))
                
                # Swing low
                if recent_prices.iloc[i] == recent_prices.iloc[i-5:i+5].min():
                    lows.append(float(recent_prices.iloc[i]))
            
            # Analyze structure
            higher_highs = False
            higher_lows = False
            lower_highs = False
            lower_lows = False
            
            if len(highs) >= 2:
                higher_highs = highs[-1] > highs[-2]
                lower_highs = highs[-1] < highs[-2]
            
            if len(lows) >= 2:
                higher_lows = lows[-1] > lows[-2]
                lower_lows = lows[-1] < lows[-2]
            
            # Determine structure type
            if higher_highs and higher_lows:
                structure_type = "uptrend"
            elif lower_highs and lower_lows:
                structure_type = "downtrend"
            elif (higher_highs and lower_lows) or (lower_highs and higher_lows):
                structure_type = "choppy"
            else:
                structure_type = "ranging"
            
            # Identify potential breakout level
            breakout_level = None
            if structure_type == "ranging" and len(highs) > 0:
                breakout_level = float(np.mean(highs))
            
            structure = MarketStructure(
                higher_highs=higher_highs,
                higher_lows=higher_lows,
                lower_highs=lower_highs,
                lower_lows=lower_lows,
                structure_type=structure_type,
                breakout_level=breakout_level
            )
            
            logger.debug(f"Market structure: {structure_type}")
            
            return structure
            
        except Exception as e:
            logger.error(f"Market structure analysis failed: {e}")
            return MarketStructure(
                higher_highs=False,
                higher_lows=False,
                lower_highs=False,
                lower_lows=False,
                structure_type="unknown",
                breakout_level=None
            )
    
    # Private helper methods
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1])
    
    def _calculate_macd_signal(self, prices: pd.Series) -> str:
        """Calculate MACD signal"""
        ema_12 = prices.ewm(span=12, adjust=False).mean()
        ema_26 = prices.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        current_macd = float(macd.iloc[-1])
        current_signal = float(signal.iloc[-1])
        
        if current_macd > current_signal:
            return "bullish"
        elif current_macd < current_signal:
            return "bearish"
        else:
            return "neutral"
    
    def _determine_trend(self, prices: pd.Series) -> str:
        """Determine trend direction"""
        if len(prices) < 50:
            return "neutral"
        
        ema_20 = prices.ewm(span=20, adjust=False).mean()
        ema_50 = prices.ewm(span=50, adjust=False).mean()
        
        current_price = float(prices.iloc[-1])
        current_ema_20 = float(ema_20.iloc[-1])
        current_ema_50 = float(ema_50.iloc[-1])
        
        if current_price > current_ema_20 > current_ema_50:
            return "bullish"
        elif current_price < current_ema_20 < current_ema_50:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_momentum(self, prices: pd.Series, period: int = 10) -> float:
        """Calculate momentum (-100 to +100)"""
        if len(prices) < period:
            return 0.0
        
        change = (prices.iloc[-1] - prices.iloc[-period]) / prices.iloc[-period] * 100
        
        # Normalize to -100 to +100
        momentum = np.clip(change * 5, -100, 100)
        
        return float(momentum)
    
    def _analyze_volume_trend(self, volume: pd.Series) -> str:
        """Analyze volume trend"""
        recent_vol = volume.iloc[-10:].mean()
        older_vol = volume.iloc[-30:-10].mean()
        
        ratio = recent_vol / older_vol
        
        if ratio > 1.2:
            return "increasing"
        elif ratio < 0.8:
            return "decreasing"
        else:
            return "stable"
    
    def _identify_key_levels(self, prices: pd.Series) -> Dict[str, float]:
        """Identify key price levels"""
        return {
            "current": float(prices.iloc[-1]),
            "high_20": float(prices.iloc[-20:].max()),
            "low_20": float(prices.iloc[-20:].min()),
            "ema_20": float(prices.ewm(span=20, adjust=False).mean().iloc[-1]),
            "ema_50": float(prices.ewm(span=50, adjust=False).mean().iloc[-1]) if len(prices) >= 50 else float(prices.iloc[-1])
        }
    
    def _generate_signal(
        self,
        rsi: float,
        macd_signal: str,
        trend: str,
        momentum: float,
        volume_trend: str
    ) -> tuple[Signal, float]:
        """Generate trading signal and strength"""
        score = 0
        
        # RSI contribution (±20 points)
        if rsi < 30:
            score += 20
        elif rsi < 40:
            score += 10
        elif rsi > 70:
            score -= 20
        elif rsi > 60:
            score -= 10
        
        # MACD contribution (±15 points)
        if macd_signal == "bullish":
            score += 15
        elif macd_signal == "bearish":
            score -= 15
        
        # Trend contribution (±25 points)
        if trend == "bullish":
            score += 25
        elif trend == "bearish":
            score -= 25
        
        # Momentum contribution (±30 points)
        score += momentum * 0.3
        
        # Volume contribution (±10 points)
        if volume_trend == "increasing":
            if score > 0:
                score += 10
            else:
                score -= 10
        
        # Determine signal
        if score > 60:
            signal = Signal.STRONG_BUY
        elif score > 20:
            signal = Signal.BUY
        elif score > -20:
            signal = Signal.NEUTRAL
        elif score > -60:
            signal = Signal.SELL
        else:
            signal = Signal.STRONG_SELL
        
        strength = min(100, abs(score))
        
        return signal, strength
    
    def _calculate_confidence(
        self,
        rsi: float,
        momentum: float,
        trend: str,
        volume_trend: str
    ) -> float:
        """Calculate confidence in the analysis"""
        confidence = 70.0  # Base confidence
        
        # RSI in extreme zones increases confidence
        if rsi < 30 or rsi > 70:
            confidence += 10
        
        # Strong momentum increases confidence
        if abs(momentum) > 50:
            confidence += 10
        
        # Clear trend increases confidence
        if trend in ["bullish", "bearish"]:
            confidence += 10
        
        # Volume confirmation
        if volume_trend == "increasing":
            confidence += 5
        
        return min(100, confidence)
    
    def _calculate_confluence_score(
        self,
        analyses: Dict[Timeframe, TimeframeAnalysis]
    ) -> float:
        """Calculate confluence score across timeframes"""
        if not analyses:
            return 0.0
        
        # Count signals
        signal_counts = {
            Signal.STRONG_BUY: 0,
            Signal.BUY: 0,
            Signal.NEUTRAL: 0,
            Signal.SELL: 0,
            Signal.STRONG_SELL: 0
        }
        
        for analysis in analyses.values():
            signal_counts[analysis.signal] += 1
        
        # Find dominant signal
        max_count = max(signal_counts.values())
        total_count = len(analyses)
        
        # Confluence score is the percentage of alignment
        confluence = (max_count / total_count) * 100
        
        return float(confluence)
    
    def _determine_overall_signal(
        self,
        analyses: Dict[Timeframe, TimeframeAnalysis]
    ) -> Signal:
        """Determine weighted overall signal"""
        weighted_score = 0.0
        
        signal_values = {
            Signal.STRONG_BUY: 2.0,
            Signal.BUY: 1.0,
            Signal.NEUTRAL: 0.0,
            Signal.SELL: -1.0,
            Signal.STRONG_SELL: -2.0
        }
        
        for tf, analysis in analyses.items():
            weight = self.timeframe_weights.get(tf, 0.1)
            signal_value = signal_values[analysis.signal]
            weighted_score += signal_value * weight * (analysis.strength / 100)
        
        # Convert score back to signal
        if weighted_score > 1.0:
            return Signal.STRONG_BUY
        elif weighted_score > 0.3:
            return Signal.BUY
        elif weighted_score > -0.3:
            return Signal.NEUTRAL
        elif weighted_score > -1.0:
            return Signal.SELL
        else:
            return Signal.STRONG_SELL
    
    def _find_aligned_timeframes(
        self,
        analyses: Dict[Timeframe, TimeframeAnalysis],
        overall_signal: Signal
    ) -> List[Timeframe]:
        """Find timeframes aligned with overall signal"""
        aligned = []
        
        # Define compatible signals
        if overall_signal in [Signal.STRONG_BUY, Signal.BUY]:
            compatible = [Signal.STRONG_BUY, Signal.BUY]
        elif overall_signal in [Signal.STRONG_SELL, Signal.SELL]:
            compatible = [Signal.STRONG_SELL, Signal.SELL]
        else:
            compatible = [Signal.NEUTRAL]
        
        for tf, analysis in analyses.items():
            if analysis.signal in compatible:
                aligned.append(tf)
        
        return aligned
    
    def _find_conflicting_timeframes(
        self,
        analyses: Dict[Timeframe, TimeframeAnalysis],
        overall_signal: Signal
    ) -> List[Timeframe]:
        """Find timeframes conflicting with overall signal"""
        conflicting = []
        
        signal_direction = {
            Signal.STRONG_BUY: "bullish",
            Signal.BUY: "bullish",
            Signal.NEUTRAL: "neutral",
            Signal.SELL: "bearish",
            Signal.STRONG_SELL: "bearish"
        }
        
        overall_direction = signal_direction[overall_signal]
        
        for tf, analysis in analyses.items():
            analysis_direction = signal_direction[analysis.signal]
            
            if overall_direction != "neutral" and analysis_direction != "neutral":
                if overall_direction != analysis_direction:
                    conflicting.append(tf)
        
        return conflicting
    
    def _generate_recommendation(
        self,
        signal: Signal,
        confluence: float,
        aligned_tfs: List[Timeframe]
    ) -> str:
        """Generate trading recommendation"""
        if confluence < 50:
            return "Wait for better confluence"
        
        if signal in [Signal.STRONG_BUY, Signal.BUY]:
            if confluence > 75:
                return "Strong BUY - High confluence across timeframes"
            else:
                return "Consider BUY - Moderate confluence"
        elif signal in [Signal.STRONG_SELL, Signal.SELL]:
            if confluence > 75:
                return "Strong SELL - High confluence across timeframes"
            else:
                return "Consider SELL - Moderate confluence"
        else:
            return "HOLD - No clear direction"
    
    def _assess_risk_level(
        self,
        confluence: float,
        conflicting_count: int,
        analyses: Dict[Timeframe, TimeframeAnalysis]
    ) -> str:
        """Assess risk level of the trade"""
        if confluence > 80 and conflicting_count == 0:
            return "low"
        elif confluence > 60 and conflicting_count <= 1:
            return "medium"
        else:
            return "high"
    
    def _calculate_overall_confidence(
        self,
        analyses: Dict[Timeframe, TimeframeAnalysis],
        confluence: float
    ) -> float:
        """Calculate overall confidence"""
        if not analyses:
            return 50.0
        
        # Average individual confidences
        avg_confidence = np.mean([a.confidence for a in analyses.values()])
        
        # Weight by confluence
        overall = (avg_confidence * 0.6) + (confluence * 0.4)
        
        return float(overall)
    
    def _fallback_analysis(
        self,
        timeframe: Timeframe,
        prices: pd.Series
    ) -> TimeframeAnalysis:
        """Fallback analysis when insufficient data"""
        current_price = float(prices.iloc[-1]) if len(prices) > 0 else 0.0
        
        return TimeframeAnalysis(
            timeframe=timeframe,
            signal=Signal.NEUTRAL,
            strength=50.0,
            trend="neutral",
            momentum=0.0,
            rsi=50.0,
            macd_signal="neutral",
            volume_trend="stable",
            key_levels={"current": current_price},
            confidence=50.0
        )
    
    def _fallback_confluence(self) -> ConfluenceAnalysis:
        """Fallback confluence analysis"""
        return ConfluenceAnalysis(
            timestamp=datetime.now(),
            overall_signal=Signal.NEUTRAL,
            confluence_score=50.0,
            timeframe_analyses={},
            aligned_timeframes=[],
            conflicting_timeframes=[],
            recommended_action="Wait for data",
            risk_level="high",
            confidence=50.0
        )


def demo_multi_timeframe():
    """Demonstration of multi-timeframe analysis"""
    # Generate sample data for multiple timeframes
    np.random.seed(42)
    base_dates = pd.date_range(end=datetime.now(), periods=500, freq='1min')
    base_prices = 100 + np.cumsum(np.random.randn(500) * 0.2)
    
    # Simulate different timeframes
    data = {
        Timeframe.M1: (
            pd.Series(base_prices, index=base_dates),
            pd.Series(np.random.randint(1000, 10000, 500), index=base_dates)
        ),
        Timeframe.M5: (
            pd.Series(base_prices[::5], index=base_dates[::5]),
            pd.Series(np.random.randint(5000, 50000, 100), index=base_dates[::5])
        ),
        Timeframe.H1: (
            pd.Series(base_prices[::60], index=base_dates[::60]),
            pd.Series(np.random.randint(50000, 500000, 8), index=base_dates[::60])
        )
    }
    
    # Initialize analyzer
    analyzer = MultiTimeframeAnalyzer()
    
    # Perform confluence analysis
    confluence = analyzer.analyze_confluence(data)
    
    print(f"\n{'='*70}")
    print("MULTI-TIMEFRAME CONFLUENCE ANALYSIS")
    print(f"{'='*70}")
    print(f"Overall Signal: {confluence.overall_signal.value}")
    print(f"Confluence Score: {confluence.confluence_score:.1f}%")
    print(f"Confidence: {confluence.confidence:.1f}%")
    print(f"Risk Level: {confluence.risk_level}")
    print(f"Recommendation: {confluence.recommended_action}")
    print(f"\nAligned Timeframes: {[tf.value for tf in confluence.aligned_timeframes]}")
    print(f"Conflicting Timeframes: {[tf.value for tf in confluence.conflicting_timeframes]}")
    
    print(f"\n{'='*70}")
    print("INDIVIDUAL TIMEFRAME ANALYSIS")
    print(f"{'='*70}")
    for tf, analysis in confluence.timeframe_analyses.items():
        print(f"\n{tf.value}:")
        print(f"  Signal: {analysis.signal.value} ({analysis.strength:.1f}%)")
        print(f"  Trend: {analysis.trend}, Momentum: {analysis.momentum:+.1f}")
        print(f"  RSI: {analysis.rsi:.1f}, MACD: {analysis.macd_signal}")
        print(f"  Confidence: {analysis.confidence:.1f}%")


if __name__ == "__main__":
    demo_multi_timeframe()
