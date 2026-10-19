"""
Loki Sophisticated Trading Strategies
Advanced strategies: momentum, mean reversion, statistical arbitrage, pairs trading, ML-driven
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Trading strategy types"""

    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    PAIRS_TRADING = "pairs_trading"
    STATISTICAL_ARBITRAGE = "statistical_arbitrage"
    SENTIMENT_DRIVEN = "sentiment_driven"
    MACHINE_LEARNING = "machine_learning"
    MULTI_FACTOR = "multi_factor"


@dataclass
class StrategySignal:
    """Strategy trading signal"""

    timestamp: datetime
    strategy_name: str
    strategy_type: StrategyType
    symbol: str
    signal: str  # BUY, SELL, HOLD
    confidence: float
    entry_price: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    position_size: float
    reasoning: List[str]
    risk_reward_ratio: float
    expected_return: float
    expected_volatility: float


class MomentumStrategy:
    """
    Advanced Momentum Strategy
    Combines multiple momentum indicators with adaptive thresholds
    """

    def __init__(self, lookback_period: int = 20, threshold: float = 0.6):
        self.lookback_period = lookback_period
        self.threshold = threshold
        self.name = "Adaptive Momentum"

    def analyze(self, data: pd.DataFrame) -> StrategySignal:
        """Analyze and generate momentum signal"""
        # Calculate multiple momentum metrics

        # 1. Rate of Change (ROC)
        roc = (data["close"].iloc[-1] / data["close"].iloc[-self.lookback_period] - 1) * 100

        # 2. Relative Strength (RS)
        gains = data["close"].diff()
        avg_gain = gains.where(gains > 0, 0).rolling(14).mean().iloc[-1]
        avg_loss = -gains.where(gains < 0, 0).rolling(14).mean().iloc[-1]
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))

        # 3. MACD Momentum
        ema_12 = data["close"].ewm(span=12).mean()
        ema_26 = data["close"].ewm(span=26).mean()
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9).mean()
        macd_histogram = (macd - macd_signal).iloc[-1]

        # 4. ADX (trend strength)
        high_low = data["high"] - data["low"]
        high_close = np.abs(data["high"] - data["close"].shift())
        low_close = np.abs(data["low"] - data["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean()

        plus_dm = data["high"].diff()
        minus_dm = -data["low"].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(14).mean().iloc[-1]

        # 5. Volume Momentum
        volume_ma = data["volume"].rolling(20).mean()
        volume_ratio = data["volume"].iloc[-1] / volume_ma.iloc[-1]

        # Combine signals
        momentum_score = 0
        reasoning = []

        # ROC analysis
        if roc > 5:
            momentum_score += 25
            reasoning.append(f"✓ Strong price momentum ({roc:.1f}% gain)")
        elif roc < -5:
            momentum_score -= 25
            reasoning.append(f"✗ Negative momentum ({roc:.1f}% decline)")

        # RSI analysis
        if 50 < rsi < 70:
            momentum_score += 20
            reasoning.append(f"✓ Bullish RSI ({rsi:.1f})")
        elif 30 < rsi < 50:
            momentum_score -= 20
            reasoning.append(f"✗ Bearish RSI ({rsi:.1f})")
        elif rsi > 70:
            momentum_score += 10
            reasoning.append(f"⚠ Overbought RSI ({rsi:.1f}) - caution")

        # MACD analysis
        if macd_histogram > 0:
            momentum_score += 20
            reasoning.append("✓ Positive MACD histogram")
        else:
            momentum_score -= 20
            reasoning.append("✗ Negative MACD histogram")

        # ADX trend strength
        if adx > 25:
            momentum_score += 15
            reasoning.append(f"✓ Strong trend (ADX: {adx:.1f})")
        else:
            reasoning.append(f"⚠ Weak trend (ADX: {adx:.1f})")

        # Volume confirmation
        if volume_ratio > 1.5:
            momentum_score += 20
            reasoning.append(f"✓ High volume confirmation ({volume_ratio:.1f}x avg)")
        elif volume_ratio < 0.7:
            momentum_score -= 10
            reasoning.append("⚠ Low volume")

        # Generate signal
        confidence = min(95, abs(momentum_score) + 20)

        if momentum_score > 50:
            signal = "BUY"
            target = data["close"].iloc[-1] * 1.05
            stop_loss = data["close"].iloc[-1] * 0.97
        elif momentum_score < -50:
            signal = "SELL"
            target = data["close"].iloc[-1] * 0.95
            stop_loss = data["close"].iloc[-1] * 1.03
        else:
            signal = "HOLD"
            target = None
            stop_loss = None

        return StrategySignal(
            timestamp=datetime.now(),
            strategy_name=self.name,
            strategy_type=StrategyType.MOMENTUM,
            symbol="SYMBOL",
            signal=signal,
            confidence=confidence,
            entry_price=data["close"].iloc[-1],
            target_price=target,
            stop_loss=stop_loss,
            position_size=1.0,
            reasoning=reasoning,
            risk_reward_ratio=3.0 if target else 0,
            expected_return=5.0 if signal == "BUY" else -5.0,
            expected_volatility=atr.iloc[-1] / data["close"].iloc[-1] * 100,
        )


class MeanReversionStrategy:
    """
    Mean Reversion Strategy
    Identifies oversold/overbought conditions for reversal trades
    """

    def __init__(self, lookback: int = 20, std_threshold: float = 2.0):
        self.lookback = lookback
        self.std_threshold = std_threshold
        self.name = "Mean Reversion"

    def analyze(self, data: pd.DataFrame) -> StrategySignal:
        """Analyze for mean reversion opportunities"""
        reasoning = []

        # Calculate Bollinger Bands
        sma = data["close"].rolling(self.lookback).mean()
        std = data["close"].rolling(self.lookback).std()

        upper_band = sma + (self.std_threshold * std)
        lower_band = sma - (self.std_threshold * std)

        current_price = data["close"].iloc[-1]
        bb_position = (current_price - lower_band.iloc[-1]) / (
            upper_band.iloc[-1] - lower_band.iloc[-1]
        )

        # Z-Score
        z_score = (current_price - sma.iloc[-1]) / std.iloc[-1]

        # RSI for oversold/overbought
        delta = data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]

        # Price distance from SMA
        distance_from_mean = (current_price / sma.iloc[-1] - 1) * 100

        # Volume analysis
        volume_ratio = data["volume"].iloc[-1] / data["volume"].rolling(20).mean().iloc[-1]

        reversion_score = 0

        # Bollinger Band position
        if bb_position < 0.2:  # Near lower band
            reversion_score += 30
            reasoning.append(f"✓ Price at lower BB ({bb_position:.1%} position)")
        elif bb_position > 0.8:  # Near upper band
            reversion_score -= 30
            reasoning.append(f"✗ Price at upper BB ({bb_position:.1%} position)")

        # Z-Score extremes
        if z_score < -2:
            reversion_score += 25
            reasoning.append(f"✓ Oversold (Z-Score: {z_score:.2f})")
        elif z_score > 2:
            reversion_score -= 25
            reasoning.append(f"✗ Overbought (Z-Score: {z_score:.2f})")

        # RSI extremes
        if rsi < 30:
            reversion_score += 25
            reasoning.append(f"✓ RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            reversion_score -= 25
            reasoning.append(f"✗ RSI overbought ({rsi:.1f})")

        # Distance from mean
        if distance_from_mean < -3:
            reversion_score += 20
            reasoning.append(f"✓ {abs(distance_from_mean):.1f}% below mean")
        elif distance_from_mean > 3:
            reversion_score -= 20
            reasoning.append(f"✗ {distance_from_mean:.1f}% above mean")

        # Generate signal
        confidence = min(95, abs(reversion_score) + 25)

        if reversion_score > 50:
            signal = "BUY"
            target = sma.iloc[-1]  # Target is mean
            stop_loss = current_price * 0.95
        elif reversion_score < -50:
            signal = "SELL"
            target = sma.iloc[-1]
            stop_loss = current_price * 1.05
        else:
            signal = "HOLD"
            target = None
            stop_loss = None

        return StrategySignal(
            timestamp=datetime.now(),
            strategy_name=self.name,
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SYMBOL",
            signal=signal,
            confidence=confidence,
            entry_price=current_price,
            target_price=target,
            stop_loss=stop_loss,
            position_size=1.0,
            reasoning=reasoning,
            risk_reward_ratio=2.0 if target else 0,
            expected_return=abs(distance_from_mean),
            expected_volatility=std.iloc[-1] / current_price * 100,
        )


class BreakoutStrategy:
    """
    Breakout Strategy
    Identifies and trades breakouts from consolidation patterns
    """

    def __init__(self, lookback: int = 20, breakout_threshold: float = 1.5):
        self.lookback = lookback
        self.breakout_threshold = breakout_threshold
        self.name = "Breakout Hunter"

    def analyze(self, data: pd.DataFrame) -> StrategySignal:
        """Analyze for breakout opportunities"""
        reasoning = []

        # Calculate recent high/low
        recent_high = data["high"].rolling(self.lookback).max().iloc[-1]
        recent_low = data["low"].rolling(self.lookback).min().iloc[-1]

        current_price = data["close"].iloc[-1]

        # Calculate ATR for volatility
        high_low = data["high"] - data["low"]
        high_close = np.abs(data["high"] - data["close"].shift())
        low_close = np.abs(data["low"] - data["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]

        # Calculate consolidation (low volatility period)
        volatility = data["close"].pct_change().rolling(20).std().iloc[-1]
        avg_volatility = data["close"].pct_change().rolling(100).std().iloc[-1]
        consolidation_ratio = volatility / avg_volatility

        # Volume analysis
        recent_volume = data["volume"].iloc[-5:].mean()
        avg_volume = data["volume"].rolling(50).mean().iloc[-1]
        volume_breakout = recent_volume / avg_volume

        # Price position in range
        range_size = recent_high - recent_low
        price_in_range = (current_price - recent_low) / range_size if range_size > 0 else 0.5

        breakout_score = 0

        # Check for breakout
        if current_price > recent_high:
            breakout_score += 40
            reasoning.append(f"✓ Breakout above resistance ({recent_high:.2f})")
        elif current_price < recent_low:
            breakout_score -= 40
            reasoning.append(f"✗ Breakdown below support ({recent_low:.2f})")

        # Consolidation before breakout
        if consolidation_ratio < 0.7:
            breakout_score += 20
            reasoning.append(f"✓ Tight consolidation ({consolidation_ratio:.2f}x avg vol)")

        # Volume confirmation
        if volume_breakout > 1.5:
            breakout_score += 25
            reasoning.append(f"✓ Volume surge ({volume_breakout:.1f}x avg)")
        elif volume_breakout < 0.8:
            breakout_score -= 15
            reasoning.append("⚠ Weak volume")

        # Trend before breakout
        sma_20 = data["close"].rolling(20).mean().iloc[-1]
        sma_50 = data["close"].rolling(50).mean().iloc[-1]

        if sma_20 > sma_50:
            breakout_score += 15
            reasoning.append("✓ Bullish trend context")
        else:
            breakout_score -= 15
            reasoning.append("⚠ Bearish trend context")

        # Generate signal
        confidence = min(95, abs(breakout_score) + 20)

        if breakout_score > 50:
            signal = "BUY"
            target = current_price + (atr * 3)  # 3 ATR target
            stop_loss = recent_high * 0.98
        elif breakout_score < -50:
            signal = "SELL"
            target = current_price - (atr * 3)
            stop_loss = recent_low * 1.02
        else:
            signal = "HOLD"
            target = None
            stop_loss = None

        return StrategySignal(
            timestamp=datetime.now(),
            strategy_name=self.name,
            strategy_type=StrategyType.BREAKOUT,
            symbol="SYMBOL",
            signal=signal,
            confidence=confidence,
            entry_price=current_price,
            target_price=target,
            stop_loss=stop_loss,
            position_size=1.0,
            reasoning=reasoning,
            risk_reward_ratio=3.0 if target else 0,
            expected_return=atr / current_price * 300,  # 3 ATR
            expected_volatility=volatility * 100,
        )


class MultiFactorStrategy:
    """
    Multi-Factor Strategy
    Combines multiple strategies with weighted voting
    """

    def __init__(self):
        self.momentum_strategy = MomentumStrategy()
        self.mean_reversion_strategy = MeanReversionStrategy()
        self.breakout_strategy = BreakoutStrategy()
        self.name = "Multi-Factor Alpha"

    def analyze(self, data: pd.DataFrame) -> StrategySignal:
        """Analyze using multiple strategies and combine signals"""
        # Get signals from all strategies
        momentum_signal = self.momentum_strategy.analyze(data)
        reversion_signal = self.mean_reversion_strategy.analyze(data)
        breakout_signal = self.breakout_strategy.analyze(data)

        # Weighted voting
        weights = {"momentum": 0.4, "mean_reversion": 0.3, "breakout": 0.3}

        signals = {
            "momentum": momentum_signal,
            "mean_reversion": reversion_signal,
            "breakout": breakout_signal,
        }

        # Calculate consensus
        buy_score = 0
        sell_score = 0
        reasoning = []

        for name, signal in signals.items():
            weight = weights[name]

            if signal.signal == "BUY":
                buy_score += weight * signal.confidence
                reasoning.append(
                    f"✓ {signal.strategy_name}: BUY ({signal.confidence:.0f}% confidence)"
                )
            elif signal.signal == "SELL":
                sell_score += weight * signal.confidence
                reasoning.append(
                    f"✗ {signal.strategy_name}: SELL ({signal.confidence:.0f}% confidence)"
                )
            else:
                reasoning.append(f"→ {signal.strategy_name}: HOLD")

        # Determine final signal
        if buy_score > sell_score and buy_score > 40:
            final_signal = "BUY"
            confidence = buy_score
        elif sell_score > buy_score and sell_score > 40:
            final_signal = "SELL"
            confidence = sell_score
        else:
            final_signal = "HOLD"
            confidence = max(buy_score, sell_score)

        # Combine targets (weighted average)
        target_price = None
        stop_loss = None

        if final_signal != "HOLD":
            targets = [s.target_price for s in signals.values() if s.target_price]
            stops = [s.stop_loss for s in signals.values() if s.stop_loss]

            if targets:
                target_price = np.mean(targets)
            if stops:
                stop_loss = np.mean(stops)

        reasoning.append(f"\n🎯 Consensus: {final_signal} ({confidence:.1f}% confidence)")

        return StrategySignal(
            timestamp=datetime.now(),
            strategy_name=self.name,
            strategy_type=StrategyType.MULTI_FACTOR,
            symbol="SYMBOL",
            signal=final_signal,
            confidence=confidence,
            entry_price=data["close"].iloc[-1],
            target_price=target_price,
            stop_loss=stop_loss,
            position_size=1.0,
            reasoning=reasoning,
            risk_reward_ratio=2.5,
            expected_return=5.0 if final_signal == "BUY" else -5.0,
            expected_volatility=data["close"].pct_change().rolling(20).std().iloc[-1] * 100,
        )


class SentimentDrivenStrategy:
    """
    Sentiment-Driven Strategy
    Uses market sentiment and behavioral signals
    """

    def __init__(self):
        self.name = "Sentiment Alpha"

    def analyze(self, data: pd.DataFrame, sentiment_score: float = 0) -> StrategySignal:
        """
        Analyze using sentiment signals

        Args:
            data: Price data
            sentiment_score: External sentiment score (-100 to 100)
        """
        reasoning = []

        # Technical sentiment indicators

        # 1. Put/Call ratio proxy (using volume patterns)
        up_volume = data[data["close"] > data["open"]]["volume"].sum()
        down_volume = data[data["close"] < data["open"]]["volume"].sum()
        volume_sentiment = (up_volume - down_volume) / (up_volume + down_volume) * 100

        # 2. New highs/lows
        recent_high = data["high"].rolling(20).max().iloc[-1]
        recent_low = data["low"].rolling(20).min().iloc[-1]
        current_price = data["close"].iloc[-1]

        at_high = current_price >= recent_high * 0.99
        at_low = current_price <= recent_low * 1.01

        # 3. Momentum divergence (contrarian indicator)
        price_change = (data["close"].iloc[-1] / data["close"].iloc[-20] - 1) * 100
        volume_change = (
            data["volume"].iloc[-5:].mean() / data["volume"].iloc[-25:-5].mean() - 1
        ) * 100

        divergence = abs(price_change) > 5 and volume_change < -20  # Price move without volume

        sentiment_combined = 0

        # External sentiment
        if abs(sentiment_score) > 0:
            sentiment_combined += sentiment_score * 0.4
            if sentiment_score > 50:
                reasoning.append(f"✓ Bullish sentiment ({sentiment_score:.0f}/100)")
            elif sentiment_score < -50:
                reasoning.append(f"✗ Bearish sentiment ({sentiment_score:.0f}/100)")

        # Volume sentiment
        sentiment_combined += volume_sentiment * 0.3
        if volume_sentiment > 20:
            reasoning.append(f"✓ Bullish volume pattern ({volume_sentiment:.0f})")
        elif volume_sentiment < -20:
            reasoning.append(f"✗ Bearish volume pattern ({volume_sentiment:.0f})")

        # High/low extremes (contrarian)
        if at_high and price_change > 10:
            sentiment_combined -= 20  # Contrarian at extremes
            reasoning.append("⚠ At recent highs - potential reversal")
        elif at_low and price_change < -10:
            sentiment_combined += 20
            reasoning.append("✓ At recent lows - potential bounce")

        # Divergence warning
        if divergence:
            sentiment_combined *= 0.7  # Reduce confidence
            reasoning.append("⚠ Price/volume divergence detected")

        # Generate signal
        confidence = min(95, abs(sentiment_combined) + 30)

        if sentiment_combined > 40:
            signal = "BUY"
            target = current_price * 1.05
            stop_loss = current_price * 0.97
        elif sentiment_combined < -40:
            signal = "SELL"
            target = current_price * 0.95
            stop_loss = current_price * 1.03
        else:
            signal = "HOLD"
            target = None
            stop_loss = None

        return StrategySignal(
            timestamp=datetime.now(),
            strategy_name=self.name,
            strategy_type=StrategyType.SENTIMENT_DRIVEN,
            symbol="SYMBOL",
            signal=signal,
            confidence=confidence,
            entry_price=current_price,
            target_price=target,
            stop_loss=stop_loss,
            position_size=1.0,
            reasoning=reasoning,
            risk_reward_ratio=2.0,
            expected_return=5.0 if signal == "BUY" else -5.0,
            expected_volatility=data["close"].pct_change().rolling(20).std().iloc[-1] * 100,
        )


class StrategyManager:
    """Manages and coordinates multiple trading strategies"""

    def __init__(self):
        self.strategies = {
            "momentum": MomentumStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "breakout": BreakoutStrategy(),
            "multi_factor": MultiFactorStrategy(),
            "sentiment": SentimentDrivenStrategy(),
        }
        logger.info(f"📊 Strategy Manager initialized with {len(self.strategies)} strategies")

    def analyze_all(self, data: pd.DataFrame, sentiment: float = 0) -> Dict[str, StrategySignal]:
        """Run all strategies and return signals"""
        signals = {}

        for name, strategy in self.strategies.items():
            try:
                if name == "sentiment":
                    signal = strategy.analyze(data, sentiment)
                else:
                    signal = strategy.analyze(data)
                signals[name] = signal
                logger.info(f"✓ {strategy.name}: {signal.signal} ({signal.confidence:.1f}%)")
            except Exception as e:
                logger.error(f"✗ Error in {strategy.name}: {e}")

        return signals

    def get_best_strategy(self, signals: Dict[str, StrategySignal]) -> StrategySignal:
        """Select the best strategy based on confidence and context"""
        if not signals:
            return None

        # Filter by minimum confidence
        high_confidence = {k: v for k, v in signals.items() if v.confidence > 60}

        if not high_confidence:
            # Return highest confidence even if below threshold
            return max(signals.values(), key=lambda x: x.confidence)

        # Prefer multi-factor if available and confident
        if "multi_factor" in high_confidence and high_confidence["multi_factor"].confidence > 70:
            return high_confidence["multi_factor"]

        # Otherwise return highest confidence
        return max(high_confidence.values(), key=lambda x: x.confidence)
