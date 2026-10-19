"""
LOKI v7.0 - Advanced Predictive Analytics Engine
Provides ML-based price prediction, trend forecasting, and volatility analysis
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Trend direction prediction"""

    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class PricePrediction:
    """Price prediction with confidence intervals"""

    timestamp: datetime
    current_price: float
    predicted_price: float
    lower_bound: float
    upper_bound: float
    confidence: float  # 0-100%
    timeframe: str  # "1h", "4h", "1d"

    @property
    def expected_change_pct(self) -> float:
        """Expected price change percentage"""
        if self.current_price == 0:
            return 0.0
        return ((self.predicted_price - self.current_price) / self.current_price) * 100


@dataclass
class TrendForecast:
    """Trend direction forecast"""

    timestamp: datetime
    direction: TrendDirection
    strength: float  # 0-100%
    confidence: float  # 0-100%
    duration_estimate: str  # "short", "medium", "long"
    key_levels: Dict[str, float]  # support/resistance levels


@dataclass
class VolatilityPrediction:
    """Volatility forecast"""

    timestamp: datetime
    current_volatility: float
    predicted_volatility: float
    volatility_regime: str  # "low", "normal", "high", "extreme"
    confidence: float  # 0-100%


@dataclass
class SupportResistanceForecast:
    """Dynamic support/resistance levels"""

    timestamp: datetime
    support_levels: List[float]  # sorted nearest first
    resistance_levels: List[float]  # sorted nearest first
    pivot_point: float
    confidence: float  # 0-100%


class PredictiveAnalyticsEngine:
    """
    Advanced ML-based predictive analytics for trading

    Uses ensemble methods combining:
    - Linear regression with technical indicators
    - Momentum-based forecasting
    - Volatility clustering (GARCH-like)
    - Support/resistance detection
    """

    def __init__(self):
        self.prediction_history: List[PricePrediction] = []
        self.trend_history: List[TrendForecast] = []
        self.volatility_history: List[VolatilityPrediction] = []

        # Model parameters
        self.lookback_period = 100
        self.prediction_accuracy = 0.0  # Updated with actual performance

        logger.info("Predictive Analytics Engine initialized")

    def predict_price(
        self, prices: pd.Series, timeframe: str = "1h", horizon: int = 1
    ) -> PricePrediction:
        """
        Predict future price using ensemble methods

        Args:
            prices: Historical price series
            timeframe: Prediction timeframe ("1h", "4h", "1d")
            horizon: Number of periods ahead to predict

        Returns:
            PricePrediction with confidence intervals
        """
        try:
            if len(prices) < self.lookback_period:
                logger.warning(f"Insufficient data: {len(prices)} < {self.lookback_period}")
                return self._fallback_prediction(prices, timeframe)

            current_price = float(prices.iloc[-1])

            # Ensemble prediction
            predictions = []
            weights = []

            # 1. Linear trend extrapolation (35% weight)
            linear_pred = self._linear_trend_prediction(prices, horizon)
            predictions.append(linear_pred)
            weights.append(0.35)

            # 2. Momentum-based prediction (30% weight)
            momentum_pred = self._momentum_prediction(prices, horizon)
            predictions.append(momentum_pred)
            weights.append(0.30)

            # 3. Mean reversion prediction (20% weight)
            reversion_pred = self._mean_reversion_prediction(prices, horizon)
            predictions.append(reversion_pred)
            weights.append(0.20)

            # 4. Volatility-adjusted prediction (15% weight)
            vol_pred = self._volatility_adjusted_prediction(prices, horizon)
            predictions.append(vol_pred)
            weights.append(0.15)

            # Weighted ensemble
            predicted_price = sum(p * w for p, w in zip(predictions, weights))

            # Calculate confidence intervals
            volatility = self._calculate_volatility(prices)
            std_dev = prices.pct_change().std() * np.sqrt(horizon)

            lower_bound = predicted_price * (1 - 2 * std_dev)
            upper_bound = predicted_price * (1 + 2 * std_dev)

            # Confidence based on prediction consistency and volatility
            pred_std = np.std(predictions)
            confidence = max(50, min(95, 100 * (1 - pred_std / predicted_price) * (1 - volatility)))

            prediction = PricePrediction(
                timestamp=datetime.now(),
                current_price=current_price,
                predicted_price=predicted_price,
                lower_bound=max(0, lower_bound),
                upper_bound=upper_bound,
                confidence=confidence,
                timeframe=timeframe,
            )

            self.prediction_history.append(prediction)
            logger.info(
                f"Price prediction: ${predicted_price:.2f} ({prediction.expected_change_pct:+.2f}%), confidence: {confidence:.1f}%"
            )

            return prediction

        except Exception as e:
            logger.error(f"Price prediction failed: {e}")
            return self._fallback_prediction(prices, timeframe)

    def forecast_trend(
        self, prices: pd.Series, volume: Optional[pd.Series] = None
    ) -> TrendForecast:
        """
        Forecast trend direction and strength

        Args:
            prices: Historical price series
            volume: Optional volume series for confirmation

        Returns:
            TrendForecast with direction and confidence
        """
        try:
            if len(prices) < 50:
                return self._fallback_trend(prices)

            # Calculate multiple EMAs for trend identification
            ema_9 = prices.ewm(span=9, adjust=False).mean()
            ema_21 = prices.ewm(span=21, adjust=False).mean()
            ema_50 = prices.ewm(span=50, adjust=False).mean()
            ema_200 = prices.ewm(span=200, adjust=False).mean() if len(prices) >= 200 else ema_50

            current_price = float(prices.iloc[-1])

            # Trend scoring system
            trend_score = 0

            # 1. Price vs EMAs (±40 points)
            if current_price > ema_9.iloc[-1]:
                trend_score += 10
            if current_price > ema_21.iloc[-1]:
                trend_score += 10
            if current_price > ema_50.iloc[-1]:
                trend_score += 10
            if current_price > ema_200.iloc[-1]:
                trend_score += 10

            if current_price < ema_9.iloc[-1]:
                trend_score -= 10
            if current_price < ema_21.iloc[-1]:
                trend_score -= 10
            if current_price < ema_50.iloc[-1]:
                trend_score -= 10
            if current_price < ema_200.iloc[-1]:
                trend_score -= 10

            # 2. EMA alignment (±30 points)
            if ema_9.iloc[-1] > ema_21.iloc[-1] > ema_50.iloc[-1]:
                trend_score += 30
            elif ema_9.iloc[-1] < ema_21.iloc[-1] < ema_50.iloc[-1]:
                trend_score -= 30

            # 3. Recent momentum (±20 points)
            recent_change = (prices.iloc[-1] - prices.iloc[-10]) / prices.iloc[-10] * 100
            trend_score += np.clip(recent_change * 2, -20, 20)

            # 4. Volume confirmation if available (±10 points)
            if volume is not None and len(volume) >= 20:
                vol_trend = volume.iloc[-5:].mean() / volume.iloc[-20:-5].mean()
                if vol_trend > 1.2:
                    trend_score += 10 if trend_score > 0 else -10

            # Determine trend direction
            if trend_score > 60:
                direction = TrendDirection.STRONG_BULLISH
            elif trend_score > 20:
                direction = TrendDirection.BULLISH
            elif trend_score > -20:
                direction = TrendDirection.NEUTRAL
            elif trend_score > -60:
                direction = TrendDirection.BEARISH
            else:
                direction = TrendDirection.STRONG_BEARISH

            # Calculate strength and confidence
            strength = min(100, abs(trend_score))
            confidence = self._calculate_trend_confidence(prices, direction)

            # Estimate duration
            volatility = self._calculate_volatility(prices)
            if volatility < 0.15:
                duration = "long"
            elif volatility < 0.30:
                duration = "medium"
            else:
                duration = "short"

            # Identify key levels
            key_levels = self._identify_key_levels(prices)

            forecast = TrendForecast(
                timestamp=datetime.now(),
                direction=direction,
                strength=strength,
                confidence=confidence,
                duration_estimate=duration,
                key_levels=key_levels,
            )

            self.trend_history.append(forecast)
            logger.info(
                f"Trend forecast: {direction.value}, strength: {strength:.1f}%, confidence: {confidence:.1f}%"
            )

            return forecast

        except Exception as e:
            logger.error(f"Trend forecasting failed: {e}")
            return self._fallback_trend(prices)

    def predict_volatility(self, prices: pd.Series) -> VolatilityPrediction:
        """
        Predict future volatility using GARCH-like approach

        Args:
            prices: Historical price series

        Returns:
            VolatilityPrediction with regime classification
        """
        try:
            if len(prices) < 30:
                return self._fallback_volatility(prices)

            # Calculate returns
            returns = prices.pct_change().dropna()

            # Current volatility (20-period rolling std)
            current_vol = float(returns.rolling(20).std().iloc[-1])

            # Volatility of volatility (clustering effect)
            vol_series = returns.rolling(20).std()
            vol_of_vol = float(vol_series.pct_change().std())

            # Simple GARCH-like prediction
            # predicted_vol = ω + α * recent_shock + β * current_vol
            omega = 0.0001  # Base volatility
            alpha = 0.15  # Shock weight
            beta = 0.80  # Persistence weight

            recent_shock = abs(returns.iloc[-1]) ** 2
            predicted_vol = np.sqrt(omega + alpha * recent_shock + beta * current_vol**2)

            # Determine volatility regime
            vol_percentile = vol_series.iloc[-1] / vol_series.quantile(0.95)

            if vol_percentile < 0.5:
                regime = "low"
            elif vol_percentile < 0.75:
                regime = "normal"
            elif vol_percentile < 1.0:
                regime = "high"
            else:
                regime = "extreme"

            # Confidence based on stability of volatility
            confidence = max(60, min(95, 100 * (1 - vol_of_vol * 10)))

            prediction = VolatilityPrediction(
                timestamp=datetime.now(),
                current_volatility=current_vol,
                predicted_volatility=predicted_vol,
                volatility_regime=regime,
                confidence=confidence,
            )

            self.volatility_history.append(prediction)
            logger.info(
                f"Volatility prediction: {predicted_vol:.4f} ({regime}), confidence: {confidence:.1f}%"
            )

            return prediction

        except Exception as e:
            logger.error(f"Volatility prediction failed: {e}")
            return self._fallback_volatility(prices)

    def forecast_support_resistance(
        self, prices: pd.Series, num_levels: int = 3
    ) -> SupportResistanceForecast:
        """
        Forecast dynamic support and resistance levels

        Args:
            prices: Historical price series
            num_levels: Number of levels to identify

        Returns:
            SupportResistanceForecast with key levels
        """
        try:
            if len(prices) < 50:
                current_price = float(prices.iloc[-1])
                return SupportResistanceForecast(
                    timestamp=datetime.now(),
                    support_levels=[current_price * 0.98],
                    resistance_levels=[current_price * 1.02],
                    pivot_point=current_price,
                    confidence=50.0,
                )

            current_price = float(prices.iloc[-1])

            # Calculate pivot point (traditional method)
            high = float(prices.iloc[-1:].max())
            low = float(prices.iloc[-1:].min())
            close = current_price
            pivot = (high + low + close) / 3

            # Find support levels (local minima)
            support_candidates = []
            for i in range(5, len(prices) - 5):
                if prices.iloc[i] == prices.iloc[i - 5 : i + 5].min():
                    support_candidates.append(float(prices.iloc[i]))

            # Find resistance levels (local maxima)
            resistance_candidates = []
            for i in range(5, len(prices) - 5):
                if prices.iloc[i] == prices.iloc[i - 5 : i + 5].max():
                    resistance_candidates.append(float(prices.iloc[i]))

            # Filter and sort support levels (below current price)
            supports = sorted([s for s in support_candidates if s < current_price], reverse=True)
            support_levels = (
                supports[:num_levels]
                if supports
                else [current_price * (1 - 0.02 * (i + 1)) for i in range(num_levels)]
            )

            # Filter and sort resistance levels (above current price)
            resistances = sorted([r for r in resistance_candidates if r > current_price])
            resistance_levels = (
                resistances[:num_levels]
                if resistances
                else [current_price * (1 + 0.02 * (i + 1)) for i in range(num_levels)]
            )

            # Calculate confidence based on level clustering
            confidence = self._calculate_level_confidence(support_candidates, resistance_candidates)

            forecast = SupportResistanceForecast(
                timestamp=datetime.now(),
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                pivot_point=pivot,
                confidence=confidence,
            )

            logger.info(
                f"S/R forecast: Supports {support_levels[:2]}, Resistances {resistance_levels[:2]}"
            )

            return forecast

        except Exception as e:
            logger.error(f"S/R forecasting failed: {e}")
            current_price = float(prices.iloc[-1])
            return SupportResistanceForecast(
                timestamp=datetime.now(),
                support_levels=[current_price * 0.98],
                resistance_levels=[current_price * 1.02],
                pivot_point=current_price,
                confidence=50.0,
            )

    # Private helper methods

    def _linear_trend_prediction(self, prices: pd.Series, horizon: int) -> float:
        """Linear regression trend extrapolation"""
        x = np.arange(len(prices))
        y = prices.values

        # Simple linear regression
        x_mean = np.mean(x)
        y_mean = np.mean(y)

        slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        intercept = y_mean - slope * x_mean

        # Predict
        future_x = len(prices) + horizon - 1
        predicted = slope * future_x + intercept

        return float(predicted)

    def _momentum_prediction(self, prices: pd.Series, horizon: int) -> float:
        """Momentum-based prediction"""
        recent_change = prices.iloc[-10:].pct_change().mean()
        current_price = float(prices.iloc[-1])

        # Project momentum forward
        predicted = current_price * (1 + recent_change * horizon)

        return float(predicted)

    def _mean_reversion_prediction(self, prices: pd.Series, horizon: int) -> float:
        """Mean reversion prediction"""
        sma_50 = prices.rolling(50).mean().iloc[-1]
        current_price = float(prices.iloc[-1])

        # Assume partial reversion to mean
        reversion_factor = 0.3  # 30% reversion
        predicted = current_price + (sma_50 - current_price) * reversion_factor * (horizon / 10)

        return float(predicted)

    def _volatility_adjusted_prediction(self, prices: pd.Series, horizon: int) -> float:
        """Volatility-adjusted prediction"""
        current_price = float(prices.iloc[-1])
        volatility = prices.pct_change().std()

        # Random walk with drift
        drift = prices.pct_change().mean()
        predicted = current_price * (1 + drift * horizon)

        return float(predicted)

    def _calculate_volatility(self, prices: pd.Series) -> float:
        """Calculate normalized volatility"""
        returns = prices.pct_change().dropna()
        return float(returns.std())

    def _calculate_trend_confidence(self, prices: pd.Series, direction: TrendDirection) -> float:
        """Calculate confidence in trend forecast"""
        # Based on consistency of recent price action
        recent_changes = prices.pct_change().iloc[-20:]

        if direction in [TrendDirection.STRONG_BULLISH, TrendDirection.BULLISH]:
            positive_ratio = (recent_changes > 0).sum() / len(recent_changes)
            confidence = 50 + positive_ratio * 50
        elif direction in [TrendDirection.STRONG_BEARISH, TrendDirection.BEARISH]:
            negative_ratio = (recent_changes < 0).sum() / len(recent_changes)
            confidence = 50 + negative_ratio * 50
        else:
            # Neutral - look for low volatility
            vol = recent_changes.std()
            confidence = max(60, 100 * (1 - vol * 10))

        return float(confidence)

    def _identify_key_levels(self, prices: pd.Series) -> Dict[str, float]:
        """Identify key price levels"""
        current_price = float(prices.iloc[-1])

        return {
            "current": current_price,
            "high_20": float(prices.iloc[-20:].max()),
            "low_20": float(prices.iloc[-20:].min()),
            "sma_50": (
                float(prices.rolling(50).mean().iloc[-1]) if len(prices) >= 50 else current_price
            ),
            "ema_20": float(prices.ewm(span=20, adjust=False).mean().iloc[-1]),
        }

    def _calculate_level_confidence(self, supports: List[float], resistances: List[float]) -> float:
        """Calculate confidence in support/resistance levels"""
        total_levels = len(supports) + len(resistances)

        if total_levels < 3:
            return 50.0
        elif total_levels < 6:
            return 65.0
        elif total_levels < 10:
            return 80.0
        else:
            return 90.0

    def _fallback_prediction(self, prices: pd.Series, timeframe: str) -> PricePrediction:
        """Fallback prediction when insufficient data"""
        current_price = float(prices.iloc[-1])

        return PricePrediction(
            timestamp=datetime.now(),
            current_price=current_price,
            predicted_price=current_price,
            lower_bound=current_price * 0.95,
            upper_bound=current_price * 1.05,
            confidence=50.0,
            timeframe=timeframe,
        )

    def _fallback_trend(self, prices: pd.Series) -> TrendForecast:
        """Fallback trend when insufficient data"""
        current_price = float(prices.iloc[-1])

        return TrendForecast(
            timestamp=datetime.now(),
            direction=TrendDirection.NEUTRAL,
            strength=50.0,
            confidence=50.0,
            duration_estimate="short",
            key_levels={"current": current_price},
        )

    def _fallback_volatility(self, prices: pd.Series) -> VolatilityPrediction:
        """Fallback volatility when insufficient data"""
        return VolatilityPrediction(
            timestamp=datetime.now(),
            current_volatility=0.02,
            predicted_volatility=0.02,
            volatility_regime="normal",
            confidence=50.0,
        )

    def get_accuracy_metrics(self) -> Dict[str, float]:
        """Calculate prediction accuracy from history"""
        if len(self.prediction_history) < 10:
            return {"accuracy": 0.0, "mae": 0.0, "samples": 0}

        # Calculate metrics from recent predictions
        # (In production, compare predictions to actual outcomes)
        return {
            "accuracy": self.prediction_accuracy,
            "mae": 0.0,  # Mean Absolute Error
            "samples": len(self.prediction_history),
        }


def demo_predictive_analytics():
    """Demonstration of predictive analytics"""
    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=200, freq="1h")
    prices = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.5), index=dates)

    # Initialize engine
    engine = PredictiveAnalyticsEngine()

    # Price prediction
    price_pred = engine.predict_price(prices, timeframe="1h", horizon=1)
    print(f"\n{'='*60}")
    print("PRICE PREDICTION")
    print(f"{'='*60}")
    print(f"Current Price: ${price_pred.current_price:.2f}")
    print(
        f"Predicted Price: ${price_pred.predicted_price:.2f} ({price_pred.expected_change_pct:+.2f}%)"
    )
    print(f"Range: ${price_pred.lower_bound:.2f} - ${price_pred.upper_bound:.2f}")
    print(f"Confidence: {price_pred.confidence:.1f}%")

    # Trend forecast
    trend_pred = engine.forecast_trend(prices)
    print(f"\n{'='*60}")
    print("TREND FORECAST")
    print(f"{'='*60}")
    print(f"Direction: {trend_pred.direction.value}")
    print(f"Strength: {trend_pred.strength:.1f}%")
    print(f"Confidence: {trend_pred.confidence:.1f}%")
    print(f"Duration: {trend_pred.duration_estimate}")

    # Volatility prediction
    vol_pred = engine.predict_volatility(prices)
    print(f"\n{'='*60}")
    print("VOLATILITY PREDICTION")
    print(f"{'='*60}")
    print(f"Current: {vol_pred.current_volatility:.4f}")
    print(f"Predicted: {vol_pred.predicted_volatility:.4f}")
    print(f"Regime: {vol_pred.volatility_regime}")
    print(f"Confidence: {vol_pred.confidence:.1f}%")

    # Support/Resistance
    sr_pred = engine.forecast_support_resistance(prices)
    print(f"\n{'='*60}")
    print("SUPPORT/RESISTANCE LEVELS")
    print(f"{'='*60}")
    print(f"Pivot: ${sr_pred.pivot_point:.2f}")
    print(f"Resistance: {[f'${r:.2f}' for r in sr_pred.resistance_levels[:3]]}")
    print(f"Support: {[f'${s:.2f}' for s in sr_pred.support_levels[:3]]}")
    print(f"Confidence: {sr_pred.confidence:.1f}%")


if __name__ == "__main__":
    demo_predictive_analytics()
