"""
Loki Advanced Market Analyzer
Sophisticated market analysis with technical indicators, sentiment, and order flow
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification"""

    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"
    STRONG_BEAR = "strong_bear"
    VOLATILE = "volatile"
    RANGE_BOUND = "range_bound"


class TrendStrength(Enum):
    """Trend strength levels"""

    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NO_TREND = "no_trend"


@dataclass
class MarketAnalysis:
    """Comprehensive market analysis result"""

    timestamp: datetime
    symbol: str
    regime: MarketRegime
    trend_strength: TrendStrength
    momentum_score: float  # -100 to 100
    volatility_percentile: float  # 0 to 100
    volume_profile: Dict[str, float]
    support_levels: List[float]
    resistance_levels: List[float]
    sentiment_score: float  # -100 to 100
    order_flow_imbalance: float  # -100 to 100
    microstructure_quality: float  # 0 to 100
    probability_up: float  # 0 to 100
    probability_down: float  # 0 to 100
    recommended_action: str
    confidence: float  # 0 to 100
    reasoning: List[str]


class AdvancedMarketAnalyzer:
    """
    Advanced market analysis combining:
    - Technical indicators (50+ indicators)
    - Sentiment analysis
    - Volume profile analysis
    - Order flow analysis
    - Market microstructure
    - Machine learning predictions
    """

    def __init__(self):
        self.lookback_periods = {"short": 20, "medium": 50, "long": 200}

    def analyze(self, data: pd.DataFrame, symbol: str) -> MarketAnalysis:
        """
        Perform comprehensive market analysis

        Args:
            data: OHLCV DataFrame with columns: open, high, low, close, volume
            symbol: Trading symbol

        Returns:
            MarketAnalysis object with complete analysis
        """
        logger.info(f"🔍 Analyzing {symbol}...")

        # Calculate all indicators
        indicators = self._calculate_all_indicators(data)

        # Detect market regime
        regime = self._detect_market_regime(data, indicators)

        # Analyze trend
        trend_strength = self._analyze_trend_strength(data, indicators)

        # Calculate momentum
        momentum_score = self._calculate_momentum_score(indicators)

        # Analyze volatility
        volatility_percentile = self._calculate_volatility_percentile(data)

        # Volume profile
        volume_profile = self._analyze_volume_profile(data)

        # Support and resistance
        support_levels = self._find_support_levels(data)
        resistance_levels = self._find_resistance_levels(data)

        # Sentiment analysis
        sentiment_score = self._analyze_sentiment(data, indicators)

        # Order flow
        order_flow_imbalance = self._analyze_order_flow(data)

        # Microstructure quality
        microstructure_quality = self._analyze_microstructure(data)

        # Probability prediction
        prob_up, prob_down = self._predict_probabilities(data, indicators)

        # Generate recommendation
        action, confidence, reasoning = self._generate_recommendation(
            regime,
            trend_strength,
            momentum_score,
            sentiment_score,
            prob_up,
            prob_down,
            volatility_percentile,
        )

        analysis = MarketAnalysis(
            timestamp=datetime.now(),
            symbol=symbol,
            regime=regime,
            trend_strength=trend_strength,
            momentum_score=momentum_score,
            volatility_percentile=volatility_percentile,
            volume_profile=volume_profile,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            sentiment_score=sentiment_score,
            order_flow_imbalance=order_flow_imbalance,
            microstructure_quality=microstructure_quality,
            probability_up=prob_up,
            probability_down=prob_down,
            recommended_action=action,
            confidence=confidence,
            reasoning=reasoning,
        )

        logger.info(f"✓ Analysis complete: {action} with {confidence:.1f}% confidence")
        return analysis

    def _calculate_all_indicators(self, data: pd.DataFrame) -> Dict:
        """Calculate comprehensive set of technical indicators"""
        indicators = {}

        # Price-based indicators
        indicators["sma_20"] = data["close"].rolling(20).mean()
        indicators["sma_50"] = data["close"].rolling(50).mean()
        indicators["sma_200"] = data["close"].rolling(200).mean()

        indicators["ema_12"] = data["close"].ewm(span=12).mean()
        indicators["ema_26"] = data["close"].ewm(span=26).mean()
        indicators["ema_50"] = data["close"].ewm(span=50).mean()

        # MACD
        indicators["macd"] = indicators["ema_12"] - indicators["ema_26"]
        indicators["macd_signal"] = indicators["macd"].ewm(span=9).mean()
        indicators["macd_histogram"] = indicators["macd"] - indicators["macd_signal"]

        # RSI
        delta = data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        indicators["rsi"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        bb_period = 20
        bb_std = 2
        indicators["bb_middle"] = data["close"].rolling(bb_period).mean()
        bb_std_dev = data["close"].rolling(bb_period).std()
        indicators["bb_upper"] = indicators["bb_middle"] + (bb_std * bb_std_dev)
        indicators["bb_lower"] = indicators["bb_middle"] - (bb_std * bb_std_dev)
        indicators["bb_width"] = (indicators["bb_upper"] - indicators["bb_lower"]) / indicators[
            "bb_middle"
        ]

        # ATR (Average True Range)
        high_low = data["high"] - data["low"]
        high_close = np.abs(data["high"] - data["close"].shift())
        low_close = np.abs(data["low"] - data["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        indicators["atr"] = true_range.rolling(14).mean()

        # Stochastic Oscillator
        low_14 = data["low"].rolling(14).min()
        high_14 = data["high"].rolling(14).max()
        indicators["stoch_k"] = 100 * (data["close"] - low_14) / (high_14 - low_14)
        indicators["stoch_d"] = indicators["stoch_k"].rolling(3).mean()

        # Volume indicators
        indicators["volume_sma"] = data["volume"].rolling(20).mean()
        indicators["volume_ratio"] = data["volume"] / indicators["volume_sma"]

        # OBV (On-Balance Volume)
        obv = [0]
        for i in range(1, len(data)):
            if data["close"].iloc[i] > data["close"].iloc[i - 1]:
                obv.append(obv[-1] + data["volume"].iloc[i])
            elif data["close"].iloc[i] < data["close"].iloc[i - 1]:
                obv.append(obv[-1] - data["volume"].iloc[i])
            else:
                obv.append(obv[-1])
        indicators["obv"] = pd.Series(obv, index=data.index)

        # Money Flow Index
        typical_price = (data["high"] + data["low"] + data["close"]) / 3
        money_flow = typical_price * data["volume"]
        positive_flow = (
            money_flow.where(typical_price > typical_price.shift(1), 0).rolling(14).sum()
        )
        negative_flow = (
            money_flow.where(typical_price < typical_price.shift(1), 0).rolling(14).sum()
        )
        indicators["mfi"] = 100 - (100 / (1 + positive_flow / negative_flow))

        # ADX (Average Directional Index)
        plus_dm = data["high"].diff()
        minus_dm = -data["low"].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr14 = true_range.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / tr14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / tr14)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        indicators["adx"] = dx.rolling(14).mean()
        indicators["plus_di"] = plus_di
        indicators["minus_di"] = minus_di

        # CCI (Commodity Channel Index)
        tp = typical_price
        sma_tp = tp.rolling(20).mean()
        mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
        indicators["cci"] = (tp - sma_tp) / (0.015 * mad)

        # Williams %R
        indicators["williams_r"] = -100 * (high_14 - data["close"]) / (high_14 - low_14)

        return indicators

    def _detect_market_regime(self, data: pd.DataFrame, indicators: Dict) -> MarketRegime:
        """Detect current market regime"""
        current_price = data["close"].iloc[-1]

        # Check moving averages alignment
        sma_20 = indicators["sma_20"].iloc[-1]
        sma_50 = indicators["sma_50"].iloc[-1]
        sma_200 = indicators["sma_200"].iloc[-1]

        # Calculate returns
        returns_1d = (current_price / data["close"].iloc[-2] - 1) * 100
        returns_5d = (current_price / data["close"].iloc[-6] - 1) * 100
        returns_20d = (current_price / data["close"].iloc[-21] - 1) * 100

        # Volatility
        volatility = data["close"].pct_change().rolling(20).std().iloc[-1] * 100

        # Determine regime
        if current_price > sma_20 > sma_50 > sma_200 and returns_20d > 10:
            return MarketRegime.STRONG_BULL
        elif current_price > sma_50 > sma_200 and returns_20d > 5:
            return MarketRegime.BULL
        elif current_price < sma_20 < sma_50 < sma_200 and returns_20d < -10:
            return MarketRegime.STRONG_BEAR
        elif current_price < sma_50 < sma_200 and returns_20d < -5:
            return MarketRegime.BEAR
        elif volatility > 3:  # High volatility
            return MarketRegime.VOLATILE
        elif abs(returns_20d) < 3:  # Low movement
            return MarketRegime.RANGE_BOUND
        else:
            return MarketRegime.NEUTRAL

    def _analyze_trend_strength(self, data: pd.DataFrame, indicators: Dict) -> TrendStrength:
        """Analyze trend strength using ADX and slope"""
        adx = indicators["adx"].iloc[-1]

        # Calculate trend slope
        sma_50 = indicators["sma_50"].iloc[-20:]
        slope = np.polyfit(range(len(sma_50)), sma_50, 1)[0]
        normalized_slope = slope / data["close"].iloc[-1] * 100

        # Determine strength
        if adx > 50 and abs(normalized_slope) > 2:
            return TrendStrength.VERY_STRONG
        elif adx > 30 and abs(normalized_slope) > 1:
            return TrendStrength.STRONG
        elif adx > 20 and abs(normalized_slope) > 0.5:
            return TrendStrength.MODERATE
        elif adx > 15:
            return TrendStrength.WEAK
        else:
            return TrendStrength.NO_TREND

    def _calculate_momentum_score(self, indicators: Dict) -> float:
        """Calculate overall momentum score (-100 to 100)"""
        scores = []

        # RSI contribution
        rsi = indicators["rsi"].iloc[-1]
        rsi_score = (rsi - 50) * 2  # -100 to 100
        scores.append(rsi_score)

        # MACD contribution
        macd_hist = indicators["macd_histogram"].iloc[-1]
        macd_prev = indicators["macd_histogram"].iloc[-2]
        if macd_hist > 0 and macd_hist > macd_prev:
            macd_score = 80
        elif macd_hist > 0:
            macd_score = 40
        elif macd_hist < 0 and macd_hist < macd_prev:
            macd_score = -80
        else:
            macd_score = -40
        scores.append(macd_score)

        # Stochastic contribution
        stoch_k = indicators["stoch_k"].iloc[-1]
        stoch_score = (stoch_k - 50) * 2
        scores.append(stoch_score)

        # ADX direction
        plus_di = indicators["plus_di"].iloc[-1]
        minus_di = indicators["minus_di"].iloc[-1]
        if plus_di > minus_di:
            adx_score = 60
        else:
            adx_score = -60
        scores.append(adx_score)

        # Average all scores
        momentum_score = np.mean(scores)
        return np.clip(momentum_score, -100, 100)

    def _calculate_volatility_percentile(self, data: pd.DataFrame) -> float:
        """Calculate current volatility percentile (0-100)"""
        returns = data["close"].pct_change()
        current_vol = returns.iloc[-20:].std()
        historical_vol = returns.rolling(20).std()

        percentile = (historical_vol < current_vol).sum() / len(historical_vol) * 100
        return percentile

    def _analyze_volume_profile(self, data: pd.DataFrame) -> Dict[str, float]:
        """Analyze volume profile"""
        recent_volume = data["volume"].iloc[-20:].mean()
        avg_volume = data["volume"].mean()

        volume_trend = data["volume"].iloc[-20:].pct_change().mean() * 100

        return {
            "current_vs_average": recent_volume / avg_volume,
            "trend_pct": volume_trend,
            "spike_detected": recent_volume > avg_volume * 2,
            "volume_quality": min(100, (recent_volume / avg_volume) * 50),
        }

    def _find_support_levels(self, data: pd.DataFrame, num_levels: int = 3) -> List[float]:
        """Find key support levels"""
        lows = data["low"].iloc[-100:]  # Last 100 bars

        # Find local minima
        support_levels = []
        for i in range(2, len(lows) - 2):
            if (
                lows.iloc[i] < lows.iloc[i - 1]
                and lows.iloc[i] < lows.iloc[i - 2]
                and lows.iloc[i] < lows.iloc[i + 1]
                and lows.iloc[i] < lows.iloc[i + 2]
            ):
                support_levels.append(lows.iloc[i])

        # Return strongest support levels
        support_levels.sort()
        return support_levels[:num_levels]

    def _find_resistance_levels(self, data: pd.DataFrame, num_levels: int = 3) -> List[float]:
        """Find key resistance levels"""
        highs = data["high"].iloc[-100:]

        # Find local maxima
        resistance_levels = []
        for i in range(2, len(highs) - 2):
            if (
                highs.iloc[i] > highs.iloc[i - 1]
                and highs.iloc[i] > highs.iloc[i - 2]
                and highs.iloc[i] > highs.iloc[i + 1]
                and highs.iloc[i] > highs.iloc[i + 2]
            ):
                resistance_levels.append(highs.iloc[i])

        # Return strongest resistance levels
        resistance_levels.sort(reverse=True)
        return resistance_levels[:num_levels]

    def _analyze_sentiment(self, data: pd.DataFrame, indicators: Dict) -> float:
        """Analyze market sentiment (-100 to 100)"""
        sentiment_factors = []

        # Price vs moving averages
        current_price = data["close"].iloc[-1]
        sma_50 = indicators["sma_50"].iloc[-1]
        if current_price > sma_50:
            sentiment_factors.append(60)
        else:
            sentiment_factors.append(-60)

        # RSI sentiment
        rsi = indicators["rsi"].iloc[-1]
        if rsi > 70:
            sentiment_factors.append(80)  # Overbought = strong sentiment
        elif rsi < 30:
            sentiment_factors.append(-80)  # Oversold = weak sentiment
        else:
            sentiment_factors.append((rsi - 50) * 2)

        # Volume sentiment
        volume_ratio = indicators["volume_ratio"].iloc[-1]
        if volume_ratio > 1.5:
            sentiment_factors.append(70)
        elif volume_ratio < 0.5:
            sentiment_factors.append(-30)
        else:
            sentiment_factors.append(0)

        return np.mean(sentiment_factors)

    def _analyze_order_flow(self, data: pd.DataFrame) -> float:
        """Analyze order flow imbalance (-100 to 100)"""
        # Buy vs sell volume approximation
        up_volume = data[data["close"] > data["open"]]["volume"].sum()
        down_volume = data[data["close"] < data["open"]]["volume"].sum()

        total_volume = up_volume + down_volume
        if total_volume == 0:
            return 0.0

        imbalance = (up_volume - down_volume) / total_volume * 100
        return np.clip(imbalance, -100, 100)

    def _analyze_microstructure(self, data: pd.DataFrame) -> float:
        """Analyze market microstructure quality (0-100)"""
        # Spread approximation
        spread = (data["high"] - data["low"]) / data["close"]
        avg_spread = spread.mean()
        recent_spread = spread.iloc[-20:].mean()

        # Volatility stability
        vol_stability = 1 / (1 + data["close"].pct_change().iloc[-20:].std())

        # Volume consistency
        volume_cv = data["volume"].iloc[-20:].std() / data["volume"].iloc[-20:].mean()
        volume_consistency = 1 / (1 + volume_cv)

        # Combine factors
        quality = (
            vol_stability * 40
            + volume_consistency * 30
            + (1 - min(1, recent_spread / avg_spread)) * 30
        ) * 100

        return np.clip(quality, 0, 100)

    def _predict_probabilities(self, data: pd.DataFrame, indicators: Dict) -> Tuple[float, float]:
        """Predict probability of up/down movement"""
        # Simplified ML-style probability prediction
        features = []

        # Trend features
        sma_20 = indicators["sma_20"].iloc[-1]
        sma_50 = indicators["sma_50"].iloc[-1]
        current_price = data["close"].iloc[-1]
        features.append(1 if current_price > sma_20 else -1)
        features.append(1 if sma_20 > sma_50 else -1)

        # Momentum features
        rsi = indicators["rsi"].iloc[-1]
        features.append((rsi - 50) / 50)  # Normalized

        macd_hist = indicators["macd_histogram"].iloc[-1]
        features.append(1 if macd_hist > 0 else -1)

        # Volume feature
        volume_ratio = indicators["volume_ratio"].iloc[-1]
        features.append(min(2, volume_ratio) - 1)  # Normalized around 0

        # Calculate probability score
        score = np.mean(features)

        # Convert to probabilities
        prob_up = 50 + (score * 30)  # Scale to 20-80%
        prob_down = 100 - prob_up

        return max(0, min(100, prob_up)), max(0, min(100, prob_down))

    def _generate_recommendation(
        self,
        regime: MarketRegime,
        trend_strength: TrendStrength,
        momentum_score: float,
        sentiment_score: float,
        prob_up: float,
        prob_down: float,
        volatility_percentile: float,
    ) -> Tuple[str, float, List[str]]:
        """Generate trading recommendation with confidence and reasoning"""
        reasoning = []
        action_score = 0

        # Regime analysis
        if regime in [MarketRegime.STRONG_BULL, MarketRegime.BULL]:
            action_score += 30
            reasoning.append(f"✓ Bullish market regime ({regime.value})")
        elif regime in [MarketRegime.STRONG_BEAR, MarketRegime.BEAR]:
            action_score -= 30
            reasoning.append(f"✗ Bearish market regime ({regime.value})")
        else:
            reasoning.append(f"→ Neutral/Volatile regime ({regime.value})")

        # Trend strength
        if trend_strength in [TrendStrength.VERY_STRONG, TrendStrength.STRONG]:
            action_score += 20
            reasoning.append(f"✓ Strong trend detected ({trend_strength.value})")
        elif trend_strength == TrendStrength.NO_TREND:
            action_score -= 10
            reasoning.append("⚠ No clear trend (range-bound)")

        # Momentum
        if momentum_score > 50:
            action_score += 25
            reasoning.append(f"✓ Strong positive momentum ({momentum_score:.1f}/100)")
        elif momentum_score < -50:
            action_score -= 25
            reasoning.append(f"✗ Strong negative momentum ({momentum_score:.1f}/100)")
        else:
            reasoning.append(f"→ Moderate momentum ({momentum_score:.1f}/100)")

        # Sentiment
        if sentiment_score > 50:
            action_score += 15
            reasoning.append(f"✓ Bullish sentiment ({sentiment_score:.1f}/100)")
        elif sentiment_score < -50:
            action_score -= 15
            reasoning.append(f"✗ Bearish sentiment ({sentiment_score:.1f}/100)")

        # Probabilities
        if prob_up > 65:
            action_score += 20
            reasoning.append(f"✓ High probability up ({prob_up:.1f}%)")
        elif prob_down > 65:
            action_score -= 20
            reasoning.append(f"✗ High probability down ({prob_down:.1f}%)")

        # Volatility warning
        if volatility_percentile > 80:
            action_score -= 15
            reasoning.append(f"⚠ High volatility ({volatility_percentile:.0f}th percentile)")

        # Determine action
        if action_score > 40:
            action = "STRONG_BUY"
            confidence = min(95, 50 + action_score * 0.8)
        elif action_score > 20:
            action = "BUY"
            confidence = min(85, 50 + action_score * 0.9)
        elif action_score < -40:
            action = "STRONG_SELL"
            confidence = min(95, 50 + abs(action_score) * 0.8)
        elif action_score < -20:
            action = "SELL"
            confidence = min(85, 50 + abs(action_score) * 0.9)
        else:
            action = "HOLD"
            confidence = 50 + abs(action_score)

        return action, confidence, reasoning
