"""
Advanced Trading Strategies for Australian Crypto/Futures Markets
Implements sophisticated trading strategies with multi-timeframe analysis
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta


class StrategySignal(Enum):
    """Trading signal types."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class StrategyResult:
    """Result from a trading strategy."""
    signal: StrategySignal
    confidence: float  # 0.0 to 1.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    reasoning: str = ""
    additional_data: Dict[str, Any] = None


class AdvancedTradingStrategies:
    """Collection of advanced trading strategies for crypto/futures."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategy_config = config.get('advanced_strategies', {})
        
        # Strategy parameters
        self.enable_ml_filter = self.strategy_config.get('enable_ml_filter', False)
        self.multi_timeframe_analysis = self.strategy_config.get('multi_timeframe_analysis', True)
        self.regime_aware = self.strategy_config.get('regime_aware', True)
        
        logging.info("Advanced Trading Strategies initialized")
    
    def multi_timeframe_trend_following(self, 
                                      symbol: str, 
                                      df_5m: pd.DataFrame,
                                      df_15m: pd.DataFrame,
                                      df_1h: pd.DataFrame) -> StrategyResult:
        """
        Multi-timeframe trend following strategy.
        Aggregates signals from multiple timeframes for stronger confirmation.
        """
        try:
            # Analyze each timeframe
            signal_5m = self._analyze_trend(df_5m, period=9)
            signal_15m = self._analyze_trend(df_15m, period=21)
            signal_1h = self._analyze_trend(df_1h, period=50)
            
            # Weight signals based on timeframe importance
            weights = {5: 1.0, 15: 1.5, 60: 2.0}
            
            weighted_score = 0
            total_weight = 0
            
            timeframe_map = {5: signal_5m, 15: signal_15m, 60: signal_1h}
            
            for tf_minutes, signal in timeframe_map.items():
                weight = weights.get(tf_minutes, 1.0)
                weighted_score += signal * weight
                total_weight += weight
            
            # Normalize score
            normalized_score = weighted_score / total_weight if total_weight > 0 else 0
            
            # Generate final signal
            if normalized_score > 0.6:
                signal = StrategySignal.BUY if normalized_score < 0.8 else StrategySignal.STRONG_BUY
                confidence = normalized_score
            elif normalized_score < -0.6:
                signal = StrategySignal.SELL if normalized_score > -0.8 else StrategySignal.STRONG_SELL
                confidence = abs(normalized_score)
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
            
            current_price = df_5m['close'].iloc[-1]
            atr = self._calculate_atr(df_5m, period=14)
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=current_price - (2 * atr) if signal in [StrategySignal.BUY, StrategySignal.STRONG_BUY] else current_price + (2 * atr),
                take_profit=current_price + (3 * atr) if signal in [StrategySignal.BUY, StrategySignal.STRONG_BUY] else current_price - (3 * atr),
                reasoning=f"Multi-timeframe trend: 5m={signal_5m:.2f}, 15m={signal_15m:.2f}, 1h={signal_1h:.2f}, weighted={normalized_score:.2f}",
                additional_data={'timeframe_signals': timeframe_map}
            )
            
        except Exception as e:
            logging.error(f"Multi-timeframe trend following error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def _analyze_trend(self, df: pd.DataFrame, period: int) -> float:
        """Analyze trend for a single timeframe."""
        try:
            if len(df) < period:
                return 0.0
            
            # Calculate EMAs
            ema_short = df['close'].ewm(span=period).mean()
            ema_long = df['close'].ewm(span=period * 2).mean()
            
            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Calculate MACD
            ema_12 = df['close'].ewm(span=12).mean()
            ema_26 = df['close'].ewm(span=26).mean()
            macd = ema_12 - ema_26
            macd_signal = macd.ewm(span=9).mean()
            
            # Calculate trend score
            score = 0.0
            
            # EMA trend
            if ema_short.iloc[-1] > ema_long.iloc[-1]:
                score += 0.3
            else:
                score -= 0.3
            
            # RSI momentum
            if rsi.iloc[-1] > 50:
                score += 0.2
            else:
                score -= 0.2
            
            # MACD momentum
            if macd.iloc[-1] > macd_signal.iloc[-1]:
                score += 0.3
            else:
                score -= 0.3
            
            # Price momentum
            if df['close'].iloc[-1] > df['close'].iloc[-5]:
                score += 0.2
            else:
                score -= 0.2
            
            return score
            
        except Exception as e:
            logging.error(f"Trend analysis error: {e}")
            return 0.0
    
    def mean_reversion_bollinger(self, df: pd.DataFrame, 
                                period: int = 20,
                                std_dev: float = 2.0) -> StrategyResult:
        """
        Mean reversion strategy using Bollinger Bands.
        Buys when price touches lower band, sells when it touches upper band.
        """
        try:
            if len(df) < period:
                return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning="Insufficient data")
            
            # Calculate Bollinger Bands
            sma = df['close'].rolling(window=period).mean()
            std = df['close'].rolling(window=period).std()
            upper_band = sma + (std * std_dev)
            lower_band = sma - (std * std_dev)
            
            current_price = df['close'].iloc[-1]
            
            # Calculate %B (Percent B)
            percent_b = (current_price - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1])
            
            # Generate signal
            if percent_b <= 0.1:  # Near or below lower band
                signal = StrategySignal.BUY
                confidence = (0.1 - percent_b) / 0.1  # Stronger signal when closer to band
                stop_loss = lower_band.iloc[-1] - (std.iloc[-1] * 0.5)
                take_profit = sma.iloc[-1]
                
            elif percent_b >= 0.9:  # Near or above upper band
                signal = StrategySignal.SELL
                confidence = (percent_b - 0.9) / 0.1
                stop_loss = upper_band.iloc[-1] + (std.iloc[-1] * 0.5)
                take_profit = sma.iloc[-1]
                
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
                stop_loss = None
                take_profit = None
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Bollinger Mean Reversion: %B={percent_b:.2f}, Upper={upper_band.iloc[-1]:.2f}, Lower={lower_band.iloc[-1]:.2f}",
                additional_data={'percent_b': percent_b, 'upper_band': upper_band.iloc[-1], 'lower_band': lower_band.iloc[-1]}
            )
            
        except Exception as e:
            logging.error(f"Bollinger mean reversion error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def breakout_strategy(self, df: pd.DataFrame, 
                        period: int = 20,
                        atr_multiplier: float = 2.0) -> StrategyResult:
        """
        Breakout strategy using Donchian channels and ATR.
        Buys on breakout above resistance, sells on breakdown below support.
        """
        try:
            if len(df) < period:
                return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning="Insufficient data")
            
            # Calculate Donchian channels
            donchian_high = df['high'].rolling(window=period).max()
            donchian_low = df['low'].rolling(window=period).min()
            
            # Calculate ATR for dynamic stops
            atr = self._calculate_atr(df, period=14)
            
            current_price = df['close'].iloc[-1]
            current_high = df['high'].iloc[-1]
            current_low = df['low'].iloc[-1]
            
            # Check for breakout
            if current_high > donchian_high.iloc[-2]:  # Breakout above previous high
                signal = StrategySignal.BUY
                confidence = min(0.9, 0.6 + (current_high - donchian_high.iloc[-2]) / atr)
                stop_loss = current_price - (atr * atr_multiplier)
                take_profit = current_price + (atr * atr_multiplier * 2)
                
            elif current_low < donchian_low.iloc[-2]:  # Breakdown below previous low
                signal = StrategySignal.SELL
                confidence = min(0.9, 0.6 + (donchian_low.iloc[-2] - current_low) / atr)
                stop_loss = current_price + (atr * atr_multiplier)
                take_profit = current_price - (atr * atr_multiplier * 2)
                
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
                stop_loss = None
                take_profit = None
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Breakout: Price={current_price:.2f}, Donchian High={donchian_high.iloc[-1]:.2f}, Donchian Low={donchian_low.iloc[-1]:.2f}",
                additional_data={'donchian_high': donchian_high.iloc[-1], 'donchian_low': donchian_low.iloc[-1], 'atr': atr}
            )
            
        except Exception as e:
            logging.error(f"Breakout strategy error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def momentum_diverggence(self, df: pd.DataFrame,
                          rsi_period: int = 14,
                          ema_period: int = 9) -> StrategyResult:
        """
        Momentum divergence strategy using RSI and price action.
        Identifies divergences between price momentum and indicator momentum.
        """
        try:
            if len(df) < rsi_period + ema_period:
                return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning="Insufficient data")
            
            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Calculate price momentum
            price_momentum = df['close'].diff(ema_period)
            
            # Calculate EMA for trend direction
            ema = df['close'].ewm(span=ema_period).mean()
            
            # Look for divergences
            rsi_trend = rsi.diff(5)
            price_trend = price_momentum.diff(5)
            
            current_price = df['close'].iloc[-1]
            atr = self._calculate_atr(df, period=14)
            
            # Bullish divergence: price making lower lows, RSI making higher lows
            if (price_trend.iloc[-5:].mean() < 0 and 
                rsi_trend.iloc[-5:].mean() > 0 and 
                rsi.iloc[-1] < 30):
                signal = StrategySignal.BUY
                confidence = 0.7
                stop_loss = current_price - (atr * 1.5)
                take_profit = current_price + (atr * 2.5)
                
            # Bearish divergence: price making higher highs, RSI making lower highs
            elif (price_trend.iloc[-5:].mean() > 0 and 
                  rsi_trend.iloc[-5:].mean() < 0 and 
                  rsi.iloc[-1] > 70):
                signal = StrategySignal.SELL
                confidence = 0.7
                stop_loss = current_price + (atr * 1.5)
                take_profit = current_price - (atr * 2.5)
                
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
                stop_loss = None
                take_profit = None
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Momentum Divergence: RSI={rsi.iloc[-1]:.1f}, Price Trend={price_trend.iloc[-5:].mean():.2f}",
                additional_data={'rsi': rsi.iloc[-1], 'price_momentum': price_momentum.iloc[-1]}
            )
            
        except Exception as e:
            logging.error(f"Momentum divergence error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def volume_profile_strategy(self, df: pd.DataFrame,
                             period: int = 20) -> StrategyResult:
        """
        Volume profile strategy for identifying support/resistance levels.
        Uses volume at price levels to identify key trading zones.
        """
        try:
            if len(df) < period:
                return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning="Insufficient data")
            
            # Calculate volume profile
            current_price = df['close'].iloc[-1]
            
            # Identify high volume nodes
            volume_ma = df['volume'].rolling(window=period).mean()
            high_volume_bars = df[df['volume'] > volume_ma * 1.5]
            
            if len(high_volume_bars) > 0:
                # Find support and resistance from high volume
                resistance = high_volume_bars['high'].max()
                support = high_volume_bars['low'].min()
                
                # Calculate distance from key levels
                resistance_distance = (resistance - current_price) / current_price
                support_distance = (current_price - support) / current_price
                
                # Generate signal based on proximity to key levels
                if support_distance < 0.01:  # Near support
                    signal = StrategySignal.BUY
                    confidence = min(0.8, 0.5 + (0.01 - support_distance) / 0.01)
                    stop_loss = support * 0.99
                    take_profit = resistance * 0.95
                    
                elif resistance_distance < 0.01:  # Near resistance
                    signal = StrategySignal.SELL
                    confidence = min(0.8, 0.5 + (0.01 - resistance_distance) / 0.01)
                    stop_loss = resistance * 1.01
                    take_profit = support * 1.05
                    
                else:
                    signal = StrategySignal.HOLD
                    confidence = 0.5
                    stop_loss = None
                    take_profit = None
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
                stop_loss = None
                take_profit = None
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Volume Profile: Support={support:.2f}, Resistance={resistance:.2f}, Current={current_price:.2f}",
                additional_data={'support': support, 'resistance': resistance, 'high_volume_bars': len(high_volume_bars)}
            )
            
        except Exception as e:
            logging.error(f"Volume profile strategy error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def combined_strategy(self, 
                         df_5m: pd.DataFrame,
                         df_15m: pd.DataFrame,
                         df_1h: pd.DataFrame) -> StrategyResult:
        """
        Combined strategy that aggregates signals from multiple strategies.
        Uses weighted voting to generate consensus signals.
        """
        try:
            # Get signals from individual strategies
            strategies = [
                ('Multi-timeframe Trend', self.multi_timeframe_trend_following(df_5m, df_15m, df_1h)),
                ('Bollinger Mean Reversion', self.mean_reversion_bollinger(df_5m)),
                ('Breakout', self.breakout_strategy(df_5m)),
                ('Momentum Divergence', self.momentum_divergence(df_5m)),
                ('Volume Profile', self.volume_profile_strategy(df_5m))
            ]
            
            # Weight signals based on strategy performance
            weights = {
                'Multi-timeframe Trend': 1.5,
                'Bollinger Mean Reversion': 1.0,
                'Breakout': 1.2,
                'Momentum Divergence': 1.0,
                'Volume Profile': 0.8
            }
            
            buy_score = 0
            sell_score = 0
            total_weight = 0
            
            strategy_votes = []
            
            for strategy_name, result in strategies:
                weight = weights.get(strategy_name, 1.0)
                
                if result.signal == StrategySignal.BUY:
                    buy_score += result.confidence * weight
                elif result.signal == StrategySignal.STRONG_BUY:
                    buy_score += result.confidence * 1.5 * weight
                elif result.signal == StrategySignal.SELL:
                    sell_score += result.confidence * weight
                elif result.signal == StrategySignal.STRONG_SELL:
                    sell_score += result.confidence * 1.5 * weight
                
                total_weight += weight
                strategy_votes.append((strategy_name, result.signal, result.confidence))
            
            # Generate consensus signal
            if buy_score > sell_score and buy_score > total_weight * 0.3:
                signal = StrategySignal.BUY if buy_score < total_weight * 0.6 else StrategySignal.STRONG_BUY
                confidence = buy_score / total_weight
            elif sell_score > buy_score and sell_score > total_weight * 0.3:
                signal = StrategySignal.SELL if sell_score < total_weight * 0.6 else StrategySignal.STRONG_SELL
                confidence = sell_score / total_weight
            else:
                signal = StrategySignal.HOLD
                confidence = 0.5
            
            # Use the first strategy's entry details (can be enhanced)
            reference_result = strategies[0][1]
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=reference_result.entry_price,
                stop_loss=reference_result.stop_loss,
                take_profit=reference_result.take_profit,
                reasoning=f"Combined Strategy: Buy Score={buy_score:.2f}, Sell Score={sell_score:.2f}, Votes={strategy_votes}",
                additional_data={'strategy_votes': strategy_votes, 'buy_score': buy_score, 'sell_score': sell_score}
            )
            
        except Exception as e:
            logging.error(f"Combined strategy error: {e}")
            return StrategyResult(signal=StrategySignal.HOLD, confidence=0.0, reasoning=f"Error: {str(e)}")
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            return atr.iloc[-1]
            
        except Exception as e:
            logging.error(f"ATR calculation error: {e}")
            return 0.0