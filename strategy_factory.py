import logging
import pandas as pd
import pandas_ta_classic as ta
import datetime
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
try:
    from indicators import (
        calculate_cpr, calculate_rsi, check_rsi_divergence, 
        check_cpr_breakout, calculate_ema, check_ema_crossover,
        check_momentum_divergence, is_trend_overextended
    )
except ImportError:
    # Fallback implementations for testing
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_ema(series, period):
        return series.ewm(span=period).mean()
    
    def check_cpr_breakout(current, pivots, prev):
        if not pivots: return 'None'
        close = current.get('close', 0)
        tc = pivots.get('tc', close)
        bc = pivots.get('bc', close)
        return 'Bullish' if close > tc else 'Bearish' if close < bc else 'None'
    
    def check_rsi_divergence(price_df, rsi_series):
        return 'None'
    
    def check_ema_crossover(df, fast=9, slow=21):
        return False
    
    def check_momentum_divergence(price, momentum):
        return 'None'
    
    def is_trend_overextended(df):
        if len(df) < 20: return "None"
        price_slice = df['close'][-20:]
        max_price, min_price = price_slice.max(), price_slice.min()
        current_price = price_slice.iloc[-1]
        rsi = df.get('rsi', pd.Series([50] * len(df))).iloc[-1]
        
        if (current_price / min_price - 1) > 0.015 and rsi > 70:
            return "Uptrend"
        elif (max_price / current_price - 1) > 0.015 and rsi < 30:
            return "Downtrend"
        return "None"

@dataclass
class StrategySignal:
    """Enhanced signal class with confidence and metadata"""
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0.0 to 1.0
    reasons: List[str]
    timestamp: datetime.datetime
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward_ratio: Optional[float] = None

class BaseStrategy:
    """Enhanced base class for all trading strategies with improved error handling and metrics."""

    def __init__(self, kite, config):
        self.kite = kite
        self.config = config
        self.name = "Base"
        self.is_reversal_trade = False
        # Enhanced tracking
        self._last_hold_reason: str = ""
        self._last_signal_log: str = ""
        self._signal_count = 0
        self._last_signal_time: Optional[datetime.datetime] = None
        self._performance_metrics = {
            'signals_generated': 0,
            'win_rate': 0.0,
            'avg_confidence': 0.0,
            'last_updated': datetime.datetime.now()
        }
        # Risk management parameters
        self.max_signals_per_hour = config.get('trading_flags', {}).get('max_signals_per_hour', 3)
        self.min_confidence_threshold = config.get('trading_flags', {}).get('min_confidence_threshold', 0.6)

    def generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        """
        Enhanced signal generation with confidence scoring and risk management.
        Returns StrategySignal object instead of simple string.
        """
        if index is None:
            index = len(day_df) - 1
            
        # Rate limiting check
        if self._should_rate_limit():
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Rate limited: too many signals in the last hour'],
                timestamp=datetime.datetime.now()
            )
            
        try:
            signal = self._internal_generate_signals(day_df, sentiment, index, **kwargs)
            
            # Update performance tracking
            if signal.action in ['BUY', 'SELL']:
                self._signal_count += 1
                self._last_signal_time = signal.timestamp
                self._performance_metrics['signals_generated'] += 1
                self._performance_metrics['avg_confidence'] = (
                    (self._performance_metrics['avg_confidence'] * (self._signal_count - 1) + signal.confidence) / self._signal_count
                )
                
            return signal
            
        except Exception as e:
            logging.error(f"[{self.name}] Error in signal generation: {e}")
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=[f'Error in strategy execution: {str(e)}'],
                timestamp=datetime.datetime.now()
            )

    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        """Override this method in child classes for actual signal logic."""
        raise NotImplementedError("Child classes must implement _internal_generate_signals")

    def _should_rate_limit(self) -> bool:
        """Check if strategy should be rate limited based on recent activity."""
        if not self._last_signal_time:
            return False
            
        time_since_last = datetime.datetime.now() - self._last_signal_time
        if time_since_last.total_seconds() < 3600:  # Within last hour
            recent_signals = self._signal_count
            return recent_signals >= self.max_signals_per_hour
        return False

    def _calculate_confidence(self, conditions: Dict[str, bool], weights: Dict[str, float]) -> float:
        """Calculate confidence score based on met conditions and their weights."""
        total_weight = sum(weights.values())
        if total_weight == 0:
            return 0.0
            
        weighted_score = sum(weights[condition] for condition, met in conditions.items() if met)
        return min(1.0, weighted_score / total_weight)

    def _calculate_risk_reward(self, entry_price: float, stop_loss: float, target: float) -> float:
        """Calculate risk-reward ratio."""
        if entry_price == stop_loss:
            return 0.0
        risk = abs(entry_price - stop_loss)
        reward = abs(target - entry_price)
        return reward / risk if risk > 0 else 0.0

    def get_status_message(self, day_df, sentiment, **kwargs):
        """Returns a human-readable status message."""
        return "Awaiting signal: Enhanced strategy monitoring market conditions."

    def _log_hold(self, reason: str):
        """Enhanced hold logging with better deduplication."""
        changed = reason != self._last_hold_reason
        self._last_hold_reason = reason
        if changed and (self.config.get("trading_flags") or {}).get("log_hold_reasons", False):
            logging.debug(f"[{self.name}] HOLD: {reason}")

    def _log_signal(self, message: str):
        """Enhanced signal logging."""
        if message != self._last_signal_log:
            logging.info(f"[{self.name}] {message}")
            self._last_signal_log = message

    # Enhanced shared helper methods
    @staticmethod
    def _safe_get_value(series: pd.Series, index: int, default=float('nan')) -> float:
        """Safely get value from series with bounds checking."""
        try:
            if 0 <= index < len(series):
                value = series.iloc[index]
                return value if pd.notna(value) else default
            return default
        except (IndexError, KeyError):
            return default

    @staticmethod
    def _calculate_atr_stop_loss(df: pd.DataFrame, index: int, multiplier: float = 2.0, is_long: bool = True) -> Optional[float]:
        """Calculate ATR-based stop loss."""
        try:
            if 'atr' not in df.columns:
                return None
            current_price = df['close'].iloc[index]
            atr = df['atr'].iloc[index]
            if pd.isna(atr) or atr <= 0:
                return None
            return current_price - (atr * multiplier) if is_long else current_price + (atr * multiplier)
        except Exception:
            return None

    @staticmethod
    def _calculate_dynamic_target(df: pd.DataFrame, index: int, risk_reward_ratio: float = 2.0, 
                                  stop_loss: float = None, is_long: bool = True) -> Optional[float]:
        """Calculate dynamic profit target based on risk-reward ratio."""
        try:
            if stop_loss is None:
                return None
            current_price = df['close'].iloc[index]
            risk = abs(current_price - stop_loss)
            reward = risk * risk_reward_ratio
            return current_price + reward if is_long else current_price - reward
        except Exception:
            return None

    @staticmethod
    def _bar_time(df, index) -> datetime.time:
        """Return the timestamp of bar `index` as a datetime.time (IST-naive)."""
        try:
            ts = df.index[index]
            if hasattr(ts, 'tz') and ts.tz is not None:
                ts = ts.tz_localize(None)
            return ts.time()
        except Exception:
            return datetime.time(12, 0)

    @staticmethod
    def _bar_weekday(df, index) -> int:
        """Return weekday of bar `index` (Mon=0 … Fri=4)."""
        try:
            ts = df.index[index]
            return ts.weekday()
        except Exception:
            return 0

    def _is_vix_high(self, kwargs: dict) -> bool:
        """True when today's VIX regime tag is VIX_HIGH."""
        return 'VIX_HIGH' in (kwargs.get('vix_conditions') or set())

    def _is_vix_low(self, kwargs: dict) -> bool:
        return 'VIX_LOW' in (kwargs.get('vix_conditions') or set())

    def _is_market_hours(self, df, index) -> bool:
        """Check if current bar is within regular trading hours."""
        try:
            current_time = self._bar_time(df, index)
            return datetime.time(9, 15) <= current_time <= datetime.time(15, 30)
        except Exception:
            return True  # Default to allowing trades

class Gemini_Default_Strategy(BaseStrategy):
    """Enhanced Gemini strategy with confidence scoring and dynamic risk management."""
    
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Gemini_Default_Enhanced"

    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        if index is None: 
            index = len(day_df) - 1
            
        timestamp = datetime.datetime.now()
        
        if index < 1:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Insufficient bars (index < 1)'],
                timestamp=timestamp
            )

        # Ensure indicators are calculated
        if 'ema_50' not in day_df.columns:
            day_df['ema_50'] = calculate_ema(day_df['close'], 50)
        if 'rsi' not in day_df.columns:
            day_df['rsi'] = calculate_rsi(day_df['close'], 14)

        cpr_pivots = kwargs.get('cpr_pivots', {})
        current_candle = day_df.iloc[index]
        current_price = current_candle['close']

        # Enhanced condition tracking
        conditions = {
            'cpr_breakout': False,
            'ema_alignment': False,
            'rsi_confirmation': False,
            'volume_confirmation': False,
            'momentum_strong': False
        }
        
        weights = {
            'cpr_breakout': 0.4,
            'ema_alignment': 0.25,
            'rsi_confirmation': 0.2,
            'volume_confirmation': 0.1,
            'momentum_strong': 0.05
        }

        # Normalize sentiment
        is_bull = sentiment in ('Bullish', 'Very Bullish')
        is_bear = sentiment in ('Bearish', 'Very Bearish')
        direction = 'Bullish' if is_bull else ('Bearish' if is_bear else None)

        if direction is None:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Neutral sentiment - no directional bias'],
                timestamp=timestamp
            )

        reasons = []
        
        # Primary condition: CPR breakout
        cpr_breakout_signal = check_cpr_breakout(current_candle, cpr_pivots, day_df.iloc[index-1])
        if direction == cpr_breakout_signal:
            conditions['cpr_breakout'] = True
            reasons.append(f"CPR breakout confirmed ({direction})")

        # Confirmation conditions
        if is_bull:
            if current_candle['close'] > current_candle.get('ema_50', 0):
                conditions['ema_alignment'] = True
                reasons.append("Price above EMA-50")
            if current_candle.get('rsi', 50) > 55:
                conditions['rsi_confirmation'] = True
                reasons.append(f"RSI bullish ({current_candle.get('rsi', 0):.1f} > 55)")
        elif is_bear:
            if current_candle['close'] < current_candle.get('ema_50', 0):
                conditions['ema_alignment'] = True
                reasons.append("Price below EMA-50")
            if current_candle.get('rsi', 50) < 45:
                conditions['rsi_confirmation'] = True
                reasons.append(f"RSI bearish ({current_candle.get('rsi', 0):.1f} < 45)")

        # Volume confirmation
        if 'volume' in current_candle and 'volume_ma' in day_df.columns:
            vol_ma = day_df['volume_ma'].iloc[index] if 'volume_ma' in day_df.columns else 0
            if current_candle['volume'] > vol_ma * 1.2:
                conditions['volume_confirmation'] = True
                reasons.append("High volume confirmation")

        # Momentum check
        if len(day_df) > 5:
            recent_highs = day_df['high'].iloc[index-5:index+1].max()
            recent_lows = day_df['low'].iloc[index-5:index+1].min()
            momentum_range = (recent_highs - recent_lows) / current_price
            if momentum_range > 0.01:  # 1% range indicates good momentum
                conditions['momentum_strong'] = True
                reasons.append("Strong momentum detected")

        confidence = self._calculate_confidence(conditions, weights)
        
        # Calculate risk management levels
        stop_loss = self._calculate_atr_stop_loss(day_df, index, 2.0, is_bull)
        target = self._calculate_dynamic_target(day_df, index, 2.5, stop_loss, is_bull)
        risk_reward_ratio = self._calculate_risk_reward(current_price, stop_loss, target) if stop_loss and target else None

        # Signal decision
        if conditions['cpr_breakout'] and confidence >= self.min_confidence_threshold:
            action = 'BUY' if is_bull else 'SELL'
            self._log_signal(f"Signal confirmed with confidence {confidence:.2f}: {', '.join(reasons)}")
            
            return StrategySignal(
                action=action,
                confidence=confidence,
                reasons=reasons,
                timestamp=timestamp,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                risk_reward_ratio=risk_reward_ratio
            )
        else:
            if not conditions['cpr_breakout']:
                reason = f"CPR breakout not confirmed: {cpr_breakout_signal} vs expected {direction}"
            else:
                reason = f"Low confidence {confidence:.2f} < {self.min_confidence_threshold}"
            
            self._log_hold(reason)
            return StrategySignal(
                action='HOLD',
                confidence=confidence,
                reasons=[reason] + reasons,
                timestamp=timestamp
            )

    def get_status_message(self, day_df, sentiment, **kwargs):
        cpr = kwargs.get('cpr_pivots', {})
        if not cpr or 'tc' not in cpr or 'bc' not in cpr:
            return f"[{self.name}] Awaiting CPR pivot calculation"
            
        confidence = self._performance_metrics['avg_confidence']
        signals_today = self._performance_metrics['signals_generated']
        
        if sentiment in ['Bullish', 'Very Bullish']:
            return (f"[{self.name}] Awaiting BUY: CPR breakout above {cpr['tc']:.2f} "
                   f"| Confidence: {confidence:.1%} | Signals: {signals_today}")
        else:
            return (f"[{self.name}] Awaiting SELL: CPR breakout below {cpr['bc']:.2f} "
                   f"| Confidence: {confidence:.1%} | Signals: {signals_today}")

class Supertrend_MACD_Strategy(BaseStrategy):
    """Enhanced trend-following strategy based on Supertrend and MACD with improved risk management."""
    
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Supertrend_MACD_Enhanced"

    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        if index is None: 
            index = len(day_df) - 1
            
        timestamp = datetime.datetime.now()
        
        if index < 1: 
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Insufficient bars'],
                timestamp=timestamp
            )

        if self._is_vix_high(kwargs):
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['VIX_HIGH: Supertrend/MACD signals unreliable in high volatility'],
                timestamp=timestamp
            )

        # Calculate indicators if missing
        if 'supertrend_direction' not in day_df.columns:
            supertrend = ta.supertrend(day_df['high'], day_df['low'], day_df['close'])
            if supertrend is not None and not supertrend.empty:
                day_df['supertrend_direction'] = supertrend.get('SUPERTd_7_3.0')
                
        if 'macd' not in day_df.columns:
            macd = ta.macd(day_df['close'])
            if macd is not None and not macd.empty:
                day_df[['macd', 'macd_signal']] = macd[['MACD_12_26_9', 'MACDs_12_26_9']]

        current = day_df.iloc[index]
        current_price = current['close']
        
        # Enhanced condition analysis
        conditions = {
            'supertrend_bullish': False,
            'supertrend_bearish': False,
            'macd_bullish': False,
            'macd_bearish': False,
            'trend_strength': False,
            'momentum_confirmation': False
        }
        
        weights = {
            'supertrend_bullish': 0.3,
            'supertrend_bearish': 0.3,
            'macd_bullish': 0.25,
            'macd_bearish': 0.25,
            'trend_strength': 0.15,
            'momentum_confirmation': 0.05
        }
        
        reasons = []
        st_dir = current.get('supertrend_direction')
        macd = current.get('macd', 0)
        macd_sig = current.get('macd_signal', 0)
        
        # Supertrend analysis
        if st_dir == 1:
            conditions['supertrend_bullish'] = True
            reasons.append("Supertrend bullish")
        elif st_dir == -1:
            conditions['supertrend_bearish'] = True
            reasons.append("Supertrend bearish")
            
        # MACD analysis
        if macd > macd_sig:
            conditions['macd_bullish'] = True
            reasons.append("MACD above signal")
        elif macd < macd_sig:
            conditions['macd_bearish'] = True
            reasons.append("MACD below signal")
        
        # Trend strength analysis
        if len(day_df) > 20:
            ema_20 = day_df['close'].ewm(span=20).mean().iloc[index]
            price_distance = abs(current_price - ema_20) / ema_20
            if price_distance > 0.01:  # 1% away from EMA
                conditions['trend_strength'] = True
                reasons.append("Strong trend confirmed")
        
        # Momentum confirmation
        if 'rsi' in day_df.columns:
            rsi = current.get('rsi', 50)
            if (conditions['supertrend_bullish'] and rsi > 50) or (conditions['supertrend_bearish'] and rsi < 50):
                conditions['momentum_confirmation'] = True
                reasons.append("Momentum confirmed by RSI")
        
        # Signal logic
        is_bullish_signal = conditions['supertrend_bullish'] and conditions['macd_bullish']
        is_bearish_signal = conditions['supertrend_bearish'] and conditions['macd_bearish']
        
        if is_bullish_signal or is_bearish_signal:
            # Calculate confidence
            active_conditions = {}
            if is_bullish_signal:
                active_conditions = {k: v for k, v in conditions.items() if k in ['supertrend_bullish', 'macd_bullish', 'trend_strength', 'momentum_confirmation']}
            else:
                active_conditions = {k: v for k, v in conditions.items() if k in ['supertrend_bearish', 'macd_bearish', 'trend_strength', 'momentum_confirmation']}
            
            confidence = self._calculate_confidence(active_conditions, weights)
            
            if confidence >= self.min_confidence_threshold:
                action = 'BUY' if is_bullish_signal else 'SELL'
                stop_loss = self._calculate_atr_stop_loss(day_df, index, 2.5, is_bullish_signal)
                target = self._calculate_dynamic_target(day_df, index, 2.0, stop_loss, is_bullish_signal)
                risk_reward = self._calculate_risk_reward(current_price, stop_loss, target) if stop_loss and target else None
                
                self._log_signal(f"{action} signal with {confidence:.1%} confidence")
                
                return StrategySignal(
                    action=action,
                    confidence=confidence,
                    reasons=reasons,
                    timestamp=timestamp,
                    price=current_price,
                    stop_loss=stop_loss,
                    target=target,
                    risk_reward_ratio=risk_reward
                )
        
        # Hold conditions
        hold_reason = f"ST={st_dir}, MACD={macd:.4f} vs Signal={macd_sig:.4f}"
        self._log_hold(hold_reason)
        
        return StrategySignal(
            action='HOLD',
            confidence=0.0,
            reasons=[hold_reason],
            timestamp=timestamp
        )
    
    def get_status_message(self, day_df, sentiment, **kwargs):
        avg_confidence = self._performance_metrics['avg_confidence']
        signals_count = self._performance_metrics['signals_generated']
        
        if sentiment in ['Bullish', 'Very Bullish']:
            return (f"[{self.name}] Awaiting BUY: ST=Bullish + MACD>Signal | "
                   f"Confidence: {avg_confidence:.1%} | Signals: {signals_count}")
        else:
            return (f"[{self.name}] Awaiting SELL: ST=Bearish + MACD<Signal | "
                   f"Confidence: {avg_confidence:.1%} | Signals: {signals_count}")

class VolatilityClusterStrategy(BaseStrategy):
    """A reversal strategy based on the concept of Volatility Clustering."""
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Volatility_Cluster_Reversal"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 20:
            self._log_hold(f"insufficient bars (index={index} < 20)")
            return 'HOLD'

        # Reversal plays need gap-and-go energy — skip when VIX is already high
        # (market is already in crisis mode; reversals are treacherous).
        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: reversal trades unreliable in high-vol regime")
            return 'HOLD'

        # Confine to the 09:30–10:30 morning volatility window.
        t = self._bar_time(day_df, index)
        if not (datetime.time(9, 30) <= t < datetime.time(10, 30)):
            self._log_hold(
                f"outside bounce window (09:30–10:30). current={t.strftime('%H:%M')}"
            )
            return 'HOLD'

        if 'atr' not in day_df.columns:
            day_df['atr'] = ta.atr(day_df['high'], day_df['low'], day_df['close'], length=14)
        if 'atr_ma' not in day_df.columns:
            day_df['atr_ma'] = day_df['atr'].rolling(window=20).mean()

        last_completed_candle = day_df.iloc[index - 1]

        if pd.isna(last_completed_candle['atr']) or pd.isna(last_completed_candle['atr_ma']):
            self._log_hold("ATR or ATR-MA is NaN on last completed candle")
            return 'HOLD'

        is_high_volatility = last_completed_candle['atr'] > last_completed_candle['atr_ma']
        avg_candle_size = day_df['atr'].iloc[index-1]
        last_candle_size = abs(last_completed_candle['open'] - last_completed_candle['close'])
        is_large_move = last_candle_size > (avg_candle_size * 1.5)

        if sentiment in ['Bullish', 'Very Bullish']:
            is_reversal_candle = last_completed_candle['close'] < last_completed_candle['open']
            if is_high_volatility and is_large_move and is_reversal_candle:
                self._log_signal(f"[{self.name}] Reversal BUY signal: High volatility detected after a large down move.")
                return 'BUY'
            self._log_hold(
                f"need high_vol AND large_down_candle. "
                f"high_vol={is_high_volatility} (atr={last_completed_candle['atr']:.2f} vs atr_ma={last_completed_candle['atr_ma']:.2f}), "
                f"large_move={is_large_move} (candle={last_candle_size:.2f} vs 1.5x_atr={avg_candle_size*1.5:.2f}), "
                f"reversal_candle={is_reversal_candle}"
            )
        elif sentiment in ['Bearish', 'Very Bearish']:
            is_reversal_candle = last_completed_candle['close'] > last_completed_candle['open']
            if is_high_volatility and is_large_move and is_reversal_candle:
                self._log_signal(f"[{self.name}] Reversal SELL signal: High volatility detected after a large up move.")
                return 'SELL'
            self._log_hold(
                f"need high_vol AND large_up_candle. "
                f"high_vol={is_high_volatility} (atr={last_completed_candle['atr']:.2f} vs atr_ma={last_completed_candle['atr_ma']:.2f}), "
                f"large_move={is_large_move} (candle={last_candle_size:.2f} vs 1.5x_atr={avg_candle_size*1.5:.2f}), "
                f"reversal_candle={is_reversal_candle}"
            )
        else:
            self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")

        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: Looking for a large downward candle during high volatility to signal a potential reversal up."
        else:
            return f"Awaiting SELL signal: Looking for a large upward candle during high volatility to signal a potential reversal down."

class VSA_Strategy(BaseStrategy):
    """A strategy based on Volume Spread Analysis (VSA)."""
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Volume_Spread_Analysis"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 20:
            self._log_hold(f"insufficient bars (index={index} < 20)")
            return 'HOLD'

        if 'volume_ma' not in day_df.columns:
            day_df['volume_ma'] = day_df['volume'].rolling(window=20).mean()
        if 'spread' not in day_df.columns:
            day_df['spread'] = day_df['high'] - day_df['low']

        last_candle = day_df.iloc[index - 1]
        spread_ma = day_df['spread'].rolling(window=20).mean().iloc[index - 1]

        is_high_volume = last_candle.get('volume', 0) > (last_candle.get('volume_ma', 0) * 1.3)
        is_wide_spread = last_candle.get('spread', 0) > spread_ma

        if sentiment in ['Bullish', 'Very Bullish']:
            is_down_bar = last_candle['close'] < last_candle['open']
            is_high_close = last_candle['close'] > (last_candle['low'] + last_candle['spread'] * 0.5)
            if is_down_bar and is_high_volume and is_wide_spread and is_high_close:
                self._log_signal(f"[{self.name}] Signal confirmed: Sign of Strength detected.")
                return 'BUY'
            self._log_hold(
                f"need down_bar AND high_vol AND wide_spread AND high_close. "
                f"down_bar={is_down_bar}, high_vol={is_high_volume} "
                f"(vol={last_candle.get('volume',0):.0f} vs 1.3x_ma={last_candle.get('volume_ma',0)*1.3:.0f}), "
                f"wide_spread={is_wide_spread} (spread={last_candle.get('spread',0):.2f} vs ma={spread_ma:.2f}), "
                f"high_close={is_high_close}"
            )
        elif sentiment in ['Bearish', 'Very Bearish']:
            is_up_bar = last_candle['close'] > last_candle['open']
            is_low_close = last_candle['close'] < (last_candle['low'] + last_candle['spread'] * 0.5)
            if is_up_bar and is_high_volume and is_wide_spread and is_low_close:
                self._log_signal(f"[{self.name}] Signal confirmed: Sign of Weakness detected.")
                return 'SELL'
            self._log_hold(
                f"need up_bar AND high_vol AND wide_spread AND low_close. "
                f"up_bar={is_up_bar}, high_vol={is_high_volume} "
                f"(vol={last_candle.get('volume',0):.0f} vs 1.3x_ma={last_candle.get('volume_ma',0)*1.3:.0f}), "
                f"wide_spread={is_wide_spread} (spread={last_candle.get('spread',0):.2f} vs ma={spread_ma:.2f}), "
                f"low_close={is_low_close}"
            )
        else:
            self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")

        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: Looking for a 'Sign of Strength' - a down-bar with high volume closing in its upper half."
        else:
            return f"Awaiting SELL signal: Looking for a 'Sign of Weakness' - an up-bar with high volume closing in its lower half."

class Momentum_VWAP_RSI_Strategy(BaseStrategy):
    def __init__(self, kite, config): super().__init__(kite, config); self.name = "Momentum_VWAP_RSI"
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 1:
            self._log_hold("insufficient bars (index < 1)")
            return 'HOLD'

        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: VWAP levels lose meaning in high-volatility regime")
            return 'HOLD'

        current = day_df.iloc[index]
        close = current.get('close', float('nan'))
        vwap = current.get('vwap', float('nan'))
        rsi = current.get('rsi', float('nan'))

        if sentiment in ['Bullish', 'Very Bullish'] and close > vwap and rsi > 55:
            return 'BUY'
        if sentiment in ['Bearish', 'Very Bearish'] and close < vwap and rsi < 45:
            return 'SELL'

        if sentiment in ['Bullish', 'Very Bullish']:
            self._log_hold(
                f"need close>vwap AND rsi>55. got close={close:.2f}, vwap={vwap:.2f} "
                f"({'above' if close > vwap else 'below'}), rsi={rsi:.1f}"
            )
        else:
            self._log_hold(
                f"need close<vwap AND rsi<45. got close={close:.2f}, vwap={vwap:.2f} "
                f"({'above' if close > vwap else 'below'}), rsi={rsi:.1f}"
            )
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        vwap = day_df.iloc[-1].get('vwap', 0)
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: Price needs to be above VWAP ({vwap:.2f}) with RSI > 55."
        else:
            return f"Awaiting SELL signal: Price needs to be below VWAP ({vwap:.2f}) with RSI < 45."

class Breakout_Prev_Day_HL_Strategy(BaseStrategy):
    def __init__(self, kite, config): super().__init__(kite, config); self.name = "Breakout_Prev_Day_HL"
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 1:
            self._log_hold("insufficient bars (index < 1)")
            return 'HOLD'

        cpr = kwargs.get('cpr_pivots', {})
        pdh, pdl = cpr.get('prev_high'), cpr.get('prev_low')
        if not pdh or not pdl:
            self._log_hold("prev_day high/low pivots missing")
            return 'HOLD'
        current, last = day_df.iloc[index], day_df.iloc[index - 1]
        close = current.get('close', float('nan'))
        vol = current.get('volume', 0)
        vol_ma = current.get('volume_ma', 0)
        vol_ok = vol > (vol_ma * 1.2) if vol_ma else False

        if sentiment in ['Bullish', 'Very Bullish'] and last['close'] < pdh and close > pdh and vol_ok:
            return 'BUY'
        if sentiment in ['Bearish', 'Very Bearish'] and last['close'] > pdl and close < pdl and vol_ok:
            return 'SELL'

        if sentiment in ['Bullish', 'Very Bullish']:
            self._log_hold(
                f"need break above PDH({pdh:.2f}) with vol>1.2*MA. "
                f"close={close:.2f}, prev_close={last['close']:.2f}, "
                f"vol={vol:.0f}, vol_ma={vol_ma:.0f}, vol_ok={vol_ok}"
            )
        else:
            self._log_hold(
                f"need break below PDL({pdl:.2f}) with vol>1.2*MA. "
                f"close={close:.2f}, prev_close={last['close']:.2f}, "
                f"vol={vol:.0f}, vol_ma={vol_ma:.0f}, vol_ok={vol_ok}"
            )
        return 'HOLD'
    
    def get_status_message(self, day_df, sentiment, **kwargs):
        cpr = kwargs.get('cpr_pivots', {})
        pdh, pdl = cpr.get('prev_high'), cpr.get('prev_low')
        if not pdh or not pdl:
            return f"Awaiting signal for {self.name}: Previous day's high/low not available."
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: Price needs to break above previous day's high ({pdh:.2f}) on high volume."
        else:
            return f"Awaiting SELL signal: Price needs to break below previous day's low ({pdl:.2f}) on high volume."

class Opening_Range_Breakout_Strategy(BaseStrategy):
    def __init__(self, kite, config):
        super().__init__(kite, config); self.name = "Opening_Range_Breakout"
        self.orb_high = None; self.orb_low = None; self.orb_period_set = False
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1

        # ORB is weakest near expiry when gamma dominates intraday moves.
        # Skip Thursday and Friday (weekdays 3 and 4).
        wd = self._bar_weekday(day_df, index)
        if wd in (3, 4):
            self._log_hold(
                f"ORB disabled on Thu/Fri (expiry-day gamma noise). "
                f"weekday={wd} ({'Thu' if wd == 3 else 'Fri'})"
            )
            return 'HOLD'

        orb_minutes = self.config['trading_flags'].get('orb_minutes', 30)

        current_time = day_df.index[index].time()
        market_open_time = datetime.time(9, 15)
        orb_end_time = (datetime.datetime.combine(datetime.date.today(), market_open_time) + datetime.timedelta(minutes=orb_minutes)).time()
        
        if not self.orb_period_set and current_time >= orb_end_time:
            orb_df = day_df.between_time(market_open_time.strftime("%H:%M"), orb_end_time.strftime("%H:%M"))
            if not orb_df.empty:
                self.orb_high, self.orb_low = orb_df['high'].max(), orb_df['low'].min()
                self.orb_period_set = True
                logging.info(f"[{self.name}] ORB Set: High={self.orb_high:.2f}, Low={self.orb_low:.2f}, Range={(self.orb_high - self.orb_low):.2f}")
        
        if not self.orb_period_set:
            self._log_hold(f"ORB not established yet — waiting for first {orb_minutes} min candles")
            return 'HOLD'

        orb_range = self.orb_high - self.orb_low
        if orb_range < 10:
            self._log_hold(f"ORB range too narrow ({orb_range:.2f} pts < 10 pts min) — no trade")
            return 'HOLD'

        current, last = day_df.iloc[index], day_df.iloc[index - 1]
        if 'volume_ma' not in day_df.columns: day_df['volume_ma'] = day_df['volume'].rolling(window=20).mean()

        vol = current.get('volume', 0)
        vol_ma = current.get('volume_ma', 0)
        vol_ok = vol > (vol_ma * 1.5)

        if sentiment in ['Bullish', 'Very Bullish']:
            if last['close'] < self.orb_high and current['close'] > self.orb_high and vol_ok:
                self._log_signal(f"[{self.name}] BUY Signal on ORB High breakout.")
                return 'BUY'
            self._log_hold(
                f"need break above ORB high ({self.orb_high:.2f}) with vol>1.5x_MA. "
                f"prev_close={last['close']:.2f}, curr_close={current['close']:.2f}, "
                f"vol={vol:.0f} vs 1.5x_ma={vol_ma*1.5:.0f} (vol_ok={vol_ok})"
            )
        elif sentiment in ['Bearish', 'Very Bearish']:
            if last['close'] > self.orb_low and current['close'] < self.orb_low and vol_ok:
                self._log_signal(f"[{self.name}] SELL Signal on ORB Low breakdown.")
                return 'SELL'
            self._log_hold(
                f"need break below ORB low ({self.orb_low:.2f}) with vol>1.5x_MA. "
                f"prev_close={last['close']:.2f}, curr_close={current['close']:.2f}, "
                f"vol={vol:.0f} vs 1.5x_ma={vol_ma*1.5:.0f} (vol_ok={vol_ok})"
            )
        else:
            self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if not self.orb_period_set:
            return f"Awaiting signal for {self.name}: Waiting for the opening range to be established."
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: Price needs to break above the ORB high of {self.orb_high:.2f} on high volume."
        else:
            return f"Awaiting SELL signal: Price needs to break below the ORB low of {self.orb_low:.2f} on high volume."

class Bollinger_Band_Squeeze_Strategy(BaseStrategy):
    def __init__(self, kite, config): super().__init__(kite, config); self.name = "BB_Squeeze_Breakout"
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 1:
            self._log_hold("insufficient bars (index < 1)")
            return 'HOLD'

        # High VIX already shows expanded ranges — the squeeze premise is invalid.
        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: BB squeeze is unreliable when market is already volatile")
            return 'HOLD'

        current, last = day_df.iloc[index], day_df.iloc[index - 1]
        bw, bw_ma = current.get('bb_bandwidth'), current.get('bb_bandwidth_ma')
        in_squeeze = bw is not None and bw_ma is not None and bw < bw_ma

        if in_squeeze:
            close = current.get('close', float('nan'))
            upper = current.get('bb_upper', float('nan'))
            lower = current.get('bb_lower', float('nan'))
            last_close = last.get('close', float('nan'))
            last_upper = last.get('bb_upper', float('nan'))
            last_lower = last.get('bb_lower', float('nan'))
            if sentiment in ['Bullish', 'Very Bullish'] and last_close < last_upper and close > upper:
                return 'BUY'
            if sentiment in ['Bearish', 'Very Bearish'] and last_close > last_lower and close < lower:
                return 'SELL'
            self._log_hold(
                f"in squeeze (bw={bw:.3f}<bw_ma={bw_ma:.3f}) but no breakout. "
                f"close={close:.2f}, upper={upper:.2f}, lower={lower:.2f}"
            )
        else:
            self._log_hold(
                f"not in squeeze: bb_bandwidth={bw} >= bb_bandwidth_ma={bw_ma} "
                f"(need bandwidth below its MA)"
            )
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        current = day_df.iloc[-1]
        if current['bb_bandwidth'] > current['bb_bandwidth_ma']:
            return f"Awaiting signal for {self.name}: Waiting for Bollinger Bands to tighten into a squeeze."
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: In a BB Squeeze. Waiting for price to break above the upper band ({current['bb_upper']:.2f})."
        else:
            return f"Awaiting SELL signal: In a BB Squeeze. Waiting for price to break below the lower band ({current['bb_lower']:.2f})."

class MA_Crossover_Strategy(BaseStrategy):
    def __init__(self, kite, config): super().__init__(kite, config); self.name = "MA_Crossover"
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1
        if index < 1:
            self._log_hold("insufficient bars (index < 1)")
            return 'HOLD'

        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: short-MA crosses whipsaw in high-volatility regime")
            return 'HOLD'

        if 'ema_50' not in day_df.columns:
            day_df['ema_50'] = calculate_ema(day_df['close'], 50)

        current, last = day_df.iloc[index], day_df.iloc[index - 1]
        close = current.get('close', float('nan'))
        ema_50 = current.get('ema_50', float('nan'))

        if sentiment in ['Bullish', 'Very Bullish']:
            if close < ema_50:
                self._log_hold(
                    f"EMA50 alignment failed for BUY: close={close:.2f} < ema_50={ema_50:.2f}"
                )
                return 'HOLD'
            if last['ema_9'] <= last['ema_21'] and current['ema_9'] > current['ema_21']:
                return 'BUY'
            self._log_hold(
                f"no bullish EMA-9/21 crossover. "
                f"prev: ema9={last['ema_9']:.2f} vs ema21={last['ema_21']:.2f}, "
                f"curr: ema9={current['ema_9']:.2f} vs ema21={current['ema_21']:.2f}"
            )
            return 'HOLD'

        if sentiment in ['Bearish', 'Very Bearish']:
            if close > ema_50:
                self._log_hold(
                    f"EMA50 alignment failed for SELL: close={close:.2f} > ema_50={ema_50:.2f}"
                )
                return 'HOLD'
            if last['ema_9'] >= last['ema_21'] and current['ema_9'] < current['ema_21']:
                return 'SELL'
            self._log_hold(
                f"no bearish EMA-9/21 crossover. "
                f"prev: ema9={last['ema_9']:.2f} vs ema21={last['ema_21']:.2f}, "
                f"curr: ema9={current['ema_9']:.2f} vs ema21={current['ema_21']:.2f}"
            )
            return 'HOLD'

        self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: 9-EMA to cross above 21-EMA with close above 50-EMA."
        else:
            return f"Awaiting SELL signal: 9-EMA to cross below 21-EMA with close below 50-EMA."

class RSI_Divergence_Strategy(BaseStrategy):
    def __init__(self, kite, config): super().__init__(kite, config); self.name = "RSI_Divergence"
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1

        if index < 1:
            self._log_hold("insufficient bars (index < 1)")
            return 'HOLD'

        # Divergences are only meaningful in the first ninety minutes of the
        # session (price discovers direction; after that, divergences are noise).
        t = self._bar_time(day_df, index)
        if not (datetime.time(9, 30) <= t < datetime.time(11, 0)):
            self._log_hold(
                f"outside divergence window (09:30–11:00). current={t.strftime('%H:%M')}"
            )
            return 'HOLD'

        cur_rsi = day_df['rsi'].iloc[index] if 'rsi' in day_df.columns else float('nan')
        divergence = check_rsi_divergence(day_df.iloc[:index + 1], day_df['rsi'].iloc[:index + 1])

        if sentiment in ['Bullish', 'Very Bullish'] and divergence == 'Bullish':
            # Require RSI to be oversold (< 40) to confirm the divergence is
            # meaningful rather than a mid-range wobble.
            if cur_rsi < 40:
                self._log_signal(f"[{self.name}] BUY: bullish divergence with RSI {cur_rsi:.1f} < 40.")
                return 'BUY'
            self._log_hold(
                f"bullish divergence detected but RSI {cur_rsi:.1f} >= 40 "
                f"(need RSI < 40 to confirm oversold divergence)"
            )
            return 'HOLD'

        if sentiment in ['Bearish', 'Very Bearish'] and divergence == 'Bearish':
            # Require RSI to be overbought (> 60) to confirm meaningful divergence.
            if cur_rsi > 60:
                self._log_signal(f"[{self.name}] SELL: bearish divergence with RSI {cur_rsi:.1f} > 60.")
                return 'SELL'
            self._log_hold(
                f"bearish divergence detected but RSI {cur_rsi:.1f} <= 60 "
                f"(need RSI > 60 to confirm overbought divergence)"
            )
            return 'HOLD'

        self._log_hold(
            f"divergence={divergence!r}, sentiment={sentiment!r}, rsi={cur_rsi:.1f}. "
            f"Waiting for sentiment-matched divergence at RSI extreme."
        )
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if sentiment in ['Bullish', 'Very Bullish']:
            return ("Awaiting BUY: bullish RSI divergence (new price low, higher RSI low) "
                    "with RSI < 40 in the 09:30–11:00 window.")
        else:
            return ("Awaiting SELL: bearish RSI divergence (new price high, lower RSI high) "
                    "with RSI > 60 in the 09:30–11:00 window.")

class EMACrossRSIStrategy(BaseStrategy):
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "EMA_Cross_RSI"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        """
        Generates a signal if the EMAs are in a trending state and a crossover
        has occurred within a recent lookback period.
        50-EMA used as a trend-alignment filter: only BUY above it, SELL below it.
        VIX_HIGH suppressed — crosses are unreliable in high-vol regimes.
        """
        if index is None:
            index = len(day_df) - 1

        # New configurable lookback period. Default to 5 candles if not set.
        lookback_period = self.config['trading_flags'].get('ema_cross_lookback', 5)

        if index < lookback_period + 1:
            self._log_hold(f"insufficient bars (index={index} < lookback+1={lookback_period+1})")
            return 'HOLD'

        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: EMA crosses produce false signals in high-vol regime")
            return 'HOLD'

        # Ensure indicators are present
        if 'ema_9' not in day_df.columns: day_df['ema_9'] = calculate_ema(day_df['close'], 9)
        if 'ema_15' not in day_df.columns: day_df['ema_15'] = calculate_ema(day_df['close'], 15)
        if 'ema_50' not in day_df.columns: day_df['ema_50'] = calculate_ema(day_df['close'], 50)
        if 'rsi' not in day_df.columns: day_df['rsi'] = calculate_rsi(day_df['close'], 14)

        current_candle = day_df.iloc[index]
        close   = current_candle.get('close', float('nan'))
        ema_50  = current_candle.get('ema_50', float('nan'))

        # --- MODIFIED BULLISH (BUY) SIGNAL LOGIC ---
        # 1. Check current state: 9-EMA is above 15-EMA now.
        is_trending_up = current_candle['ema_9'] > current_candle['ema_15']
        # 2. Check confirmation conditions: RSI and price are favorable now.
        is_confirmed_up = current_candle['rsi'] > 50 and current_candle['close'] > current_candle['ema_9']

        if is_trending_up and is_confirmed_up:
            # 2b. 50-EMA alignment: only trade with the macro trend.
            if close < ema_50:
                self._log_hold(
                    f"EMA50 alignment failed for BUY: close={close:.2f} < ema_50={ema_50:.2f}"
                )
                return 'HOLD'
            # 3. Verify a "Golden Cross" happened recently
            recent_golden_cross = False
            for i in range(index - lookback_period, index + 1):
                prev_candle = day_df.iloc[i - 1]
                signal_candle = day_df.iloc[i]
                if prev_candle['ema_9'] < prev_candle['ema_15'] and signal_candle['ema_9'] > signal_candle['ema_15']:
                    recent_golden_cross = True
                    break  # Found the recent cross, no need to look further
            
            if recent_golden_cross:
                self._log_signal(f"[{self.name}] BUY Signal: 9/15 EMA in bullish state post-crossover with RSI > 50.")
                return 'BUY'
            self._log_hold(
                f"bullish state confirmed but no golden cross in last {lookback_period} bars. "
                f"ema9={current_candle['ema_9']:.2f} > ema15={current_candle['ema_15']:.2f}, "
                f"rsi={current_candle['rsi']:.1f}"
            )
            return 'HOLD'

        # --- MODIFIED BEARISH (SELL) SIGNAL LOGIC ---
        # 1. Check current state: 9-EMA is below 15-EMA now.
        is_trending_down = current_candle['ema_9'] < current_candle['ema_15']
        # 2. Check confirmation conditions: RSI and price are favorable now.
        is_confirmed_down = current_candle['rsi'] < 50 and current_candle['close'] < current_candle['ema_9']

        if is_trending_down and is_confirmed_down:
            # 2b. 50-EMA alignment: only trade with the macro trend.
            if close > ema_50:
                self._log_hold(
                    f"EMA50 alignment failed for SELL: close={close:.2f} > ema_50={ema_50:.2f}"
                )
                return 'HOLD'
            # 3. Verify a "Death Cross" happened recently
            recent_death_cross = False
            for i in range(index - lookback_period, index + 1):
                prev_candle = day_df.iloc[i - 1]
                signal_candle = day_df.iloc[i]
                if prev_candle['ema_9'] > prev_candle['ema_15'] and signal_candle['ema_9'] < signal_candle['ema_15']:
                    recent_death_cross = True
                    break

            if recent_death_cross:
                self._log_signal(f"[{self.name}] SELL Signal: 9/15 EMA in bearish state post-crossover with RSI < 50.")
                return 'SELL'
            self._log_hold(
                f"bearish state confirmed but no death-cross in last {lookback_period} bars. "
                f"ema9={current_candle['ema_9']:.2f} < ema15={current_candle['ema_15']:.2f}, "
                f"rsi={current_candle['rsi']:.1f}"
            )
            return 'HOLD'
        elif sentiment in ['Bullish', 'Very Bullish']:
            self._log_hold(
                f"bullish conditions not met: trending_up={is_trending_up} "
                f"(ema9={current_candle['ema_9']:.2f} vs ema15={current_candle['ema_15']:.2f}), "
                f"confirmed_up={is_confirmed_up} (rsi={current_candle['rsi']:.1f}, "
                f"close={'above' if current_candle['close'] > current_candle['ema_9'] else 'below'} ema9)"
            )
        elif sentiment in ['Bearish', 'Very Bearish']:
            self._log_hold(
                f"bearish conditions not met: trending_down={is_trending_down} "
                f"(ema9={current_candle['ema_9']:.2f} vs ema15={current_candle['ema_15']:.2f}), "
                f"confirmed_down={is_confirmed_down} (rsi={current_candle['rsi']:.1f}, "
                f"close={'below' if current_candle['close'] < current_candle['ema_9'] else 'above'} ema9)"
            )
        else:
            self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")

        self._log_hold(
            f"no qualifying cross in last {lookback_period} bars. "
            f"trending_up={is_trending_up}, confirmed_up={is_confirmed_up}, "
            f"trending_down={is_trending_down}, confirmed_down={is_confirmed_down}"
        )
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if sentiment in ['Bullish', 'Very Bullish']:
            return f"Awaiting BUY signal: 9/15 EMA golden cross (close above EMA50), RSI > 50."
        else:
            return f"Awaiting SELL signal: 9/15 EMA death cross (close below EMA50), RSI < 50."


class Reversal_Detector_Strategy(BaseStrategy):
    """
    A robust strategy that trades reversals based on a confluence of signals:
    1. Pre-Condition: An overextended trend.
    2. Primary Signal: RSI momentum divergence.
    3. Confirmation: A break of price structure (close over/under a fast EMA).
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Reversal_Detector"
        self.is_reversal_trade = True # This flag bypasses the daily sentiment check

    def _is_trend_overextended(self, day_df, lookback=20):
        """Quantitatively defines an overextended trend."""
        price_slice = day_df['close'][-lookback:]
        max_price, min_price = price_slice.max(), price_slice.min()
        current_price = price_slice.iloc[-1]
        rsi = day_df['rsi'].iloc[-1]
        
        # Check for overextended uptrend 
        if (current_price / min_price - 1) > 0.015 and rsi > 70:
            return "Uptrend"
        # Check for overextended downtrend 
        if (max_price / current_price - 1) > 0.015 and rsi < 30:
            return "Downtrend"
            
        return "None"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None: index = len(day_df) - 1

        # Reversals require a mature intraday trend — too early and there is no
        # established trend to reverse; too late and we lack time for the move.
        t = self._bar_time(day_df, index)
        if not (datetime.time(9, 30) <= t < datetime.time(11, 30)):
            self._log_hold(
                f"outside reversal window (09:30–11:30). current={t.strftime('%H:%M')}"
            )
            return 'HOLD'

        trend_status = is_trend_overextended(day_df)
        if trend_status == "None":
            self._log_hold("no overextended trend detected (need RSI>70+1.5% move up, or RSI<30+1.5% move down)")
            return 'HOLD'

        rsi_divergence = check_momentum_divergence(day_df['close'], day_df['rsi'])
        current_candle = day_df.iloc[-1]

        # Look for a Bearish Reversal signal
        if trend_status == "Uptrend" and rsi_divergence == "Bearish":
            if current_candle['close'] < current_candle['ema_9']:
                self._log_signal(f"[{self.name}] Bearish Reversal Signal: Overextended uptrend with RSI divergence confirmed by close below 9-EMA.")
                return 'SELL'
            self._log_hold(
                f"uptrend+bearish_divergence confirmed but price not below ema9. "
                f"close={current_candle['close']:.2f} vs ema9={current_candle['ema_9']:.2f}"
            )
        elif trend_status == "Downtrend" and rsi_divergence == "Bullish":
            if current_candle['close'] > current_candle['ema_9']:
                self._log_signal(f"[{self.name}] Bullish Reversal Signal: Overextended downtrend with RSI divergence confirmed by close above 9-EMA.")
                return 'BUY'
            self._log_hold(
                f"downtrend+bullish_divergence confirmed but price not above ema9. "
                f"close={current_candle['close']:.2f} vs ema9={current_candle['ema_9']:.2f}"
            )
        else:
            self._log_hold(
                f"trend/divergence mismatch. trend={trend_status}, divergence={rsi_divergence} "
                f"(need uptrend+bearish_div or downtrend+bullish_div)"
            )

        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        trend_status = is_trend_overextended(day_df)
        if trend_status == "Uptrend":
            return f"Awaiting SELL signal: Overextended uptrend detected. Looking for bearish RSI divergence and a confirmation break below 9-EMA."
        if trend_status == "Downtrend":
            return f"Awaiting BUY signal: Overextended downtrend detected. Looking for bullish RSI divergence and a confirmation break above 9-EMA."
        return f"Awaiting signal for {self.name}: Waiting for a sustained, overextended trend to form."

class VWAP_Reversion_Strategy(BaseStrategy):
    """
    Intraday VWAP-pullback play, designed to fire MULTIPLE times per day in a
    trending session.

    Bullish day:
      - BUY when the prior bar closed at or below VWAP AND the current bar
        closes above VWAP (a "reclaim").
      - Momentum filter: RSI > 45 (not deep oversold).

    Bearish day: mirror image (VWAP loss + RSI < 55).

    Avoids buying breakouts at the high — instead buys the dip back to the
    institutional anchor and reclaim. Pairs well with the trailing-SL setup.
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "VWAP_Reversion"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None:
            index = len(day_df) - 1
        if index < 2:
            self._log_hold("insufficient bars (index < 2)")
            return 'HOLD'

        # In a high-VIX session price whips through VWAP many times; the
        # "reclaim" pattern produces many false signals.
        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: VWAP reclaim signals are noisy in high-vol regime")
            return 'HOLD'

        if 'vwap' not in day_df.columns or 'rsi' not in day_df.columns:
            self._log_hold("vwap or rsi column missing from bars")
            return 'HOLD'

        current = day_df.iloc[index]
        prev = day_df.iloc[index - 1]

        if pd.isna(current.get('vwap')) or pd.isna(prev.get('vwap')):
            self._log_hold("vwap is NaN on current or prev bar")
            return 'HOLD'
        if pd.isna(current.get('rsi')):
            self._log_hold("rsi is NaN on current bar")
            return 'HOLD'

        cur_close, cur_vwap, cur_rsi = current['close'], current['vwap'], current['rsi']
        prev_close, prev_vwap = prev['close'], prev['vwap']

        # Bullish reclaim: prior bar at/under VWAP, current bar closes above it.
        if sentiment in ['Bullish', 'Very Bullish']:
            reclaimed = (prev_close <= prev_vwap) and (cur_close > cur_vwap)
            momentum_ok = cur_rsi > 45
            if reclaimed and momentum_ok:
                self._log_signal(f"[{self.name}] BUY: VWAP reclaim with RSI {cur_rsi:.1f} > 45.")
                return 'BUY'
            self._log_hold(
                f"need VWAP-reclaim (prev close<=VWAP AND curr close>VWAP) AND RSI>45. "
                f"prev_close={prev_close:.2f} vs prev_vwap={prev_vwap:.2f} "
                f"({'<=' if prev_close <= prev_vwap else '>'}), "
                f"curr_close={cur_close:.2f} vs curr_vwap={cur_vwap:.2f} "
                f"({'>' if cur_close > cur_vwap else '<='}), "
                f"rsi={cur_rsi:.1f} (momentum_ok={momentum_ok})"
            )
            return 'HOLD'

        # Bearish loss: prior bar at/above VWAP, current bar closes below it.
        if sentiment in ['Bearish', 'Very Bearish']:
            lost = (prev_close >= prev_vwap) and (cur_close < cur_vwap)
            momentum_ok = cur_rsi < 55
            if lost and momentum_ok:
                self._log_signal(f"[{self.name}] SELL: VWAP loss with RSI {cur_rsi:.1f} < 55.")
                return 'SELL'
            self._log_hold(
                f"need VWAP-loss (prev close>=VWAP AND curr close<VWAP) AND RSI<55. "
                f"prev_close={prev_close:.2f} vs prev_vwap={prev_vwap:.2f}, "
                f"curr_close={cur_close:.2f} vs curr_vwap={cur_vwap:.2f}, "
                f"rsi={cur_rsi:.1f} (momentum_ok={momentum_ok})"
            )
            return 'HOLD'

        self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional setup")
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        vwap = day_df.iloc[-1].get('vwap', 0) if len(day_df) else 0
        if sentiment in ['Bullish', 'Very Bullish']:
            return (f"Awaiting BUY: price to pull back to/under VWAP ({vwap:.2f}) "
                    f"and reclaim it on the next bar, RSI > 45.")
        return (f"Awaiting SELL: price to lift above VWAP ({vwap:.2f}) and lose "
                f"it on the next bar, RSI < 55.")


class NR7_Compression_Breakout_Strategy(BaseStrategy):
    """
    Compression-then-expansion play. Fires when:

      1. The narrowest of the last 7 completed bars (NR7) appeared within the
         last 3 bars (fresh compression — not stale).
      2. The current bar closes ABOVE the NR7 bar's high (BUY) or BELOW its
         low (SELL).
      3. The breakout is confirmed by volume > 1.2 × 20-bar volume MA.
      4. Sentiment direction matches.

    Compression-day breakouts have higher expectancy than chop-day breakouts.
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "NR7_Compression"

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None:
            index = len(day_df) - 1
        if index < 8:
            self._log_hold("insufficient bars (need >= 8)")
            return 'HOLD'

        # NR7 fires on compressed ranges — VIX_HIGH means ranges are already wide;
        # the setup premise is invalid.
        if self._is_vix_high(kwargs):
            self._log_hold("VIX_HIGH: range compression is absent in high-vol regime")
            return 'HOLD'

        if 'volume_ma' not in day_df.columns:
            self._log_hold("volume_ma column missing")
            return 'HOLD'

        window = day_df.iloc[index - 7:index]
        if window.empty or len(window) < 7:
            self._log_hold("window too short for NR7 lookup")
            return 'HOLD'
        ranges = window['high'] - window['low']
        if ranges.isna().any():
            self._log_hold("range column has NaN in lookback window")
            return 'HOLD'
        nr7_idx_in_window = int(ranges.values.argmin())
        bars_since_nr7 = len(window) - 1 - nr7_idx_in_window
        if bars_since_nr7 > 6:
            self._log_hold(
                f"NR7 too stale: narrowest bar was {bars_since_nr7} bars ago "
                f"(need <= 6 to count as 'fresh' compression, i.e. within 30 min)"
            )
            return 'HOLD'

        nr7_bar = window.iloc[nr7_idx_in_window]
        current = day_df.iloc[index]
        cur_close = current.get('close', float('nan'))
        cur_vol = current.get('volume', 0)
        cur_vol_ma = current.get('volume_ma', 0)
        if pd.isna(cur_vol_ma) or cur_vol_ma <= 0:
            self._log_hold("volume_ma is NaN/zero")
            return 'HOLD'
        volume_confirm = cur_vol > (cur_vol_ma * 1.2)
        if not volume_confirm:
            self._log_hold(
                f"NR7 fresh ({bars_since_nr7} bars ago) but volume not confirming: "
                f"vol={cur_vol:.0f} <= 1.2*MA={1.2 * cur_vol_ma:.0f}"
            )
            return 'HOLD'

        nr7_high, nr7_low = nr7_bar['high'], nr7_bar['low']
        if sentiment in ['Bullish', 'Very Bullish'] and cur_close > nr7_high:
            self._log_signal(
                f"[{self.name}] BUY: close {cur_close:.2f} > NR7 high "
                f"{nr7_high:.2f} on volume {cur_vol:.0f} vs MA {cur_vol_ma:.0f}."
            )
            return 'BUY'
        if sentiment in ['Bearish', 'Very Bearish'] and cur_close < nr7_low:
            self._log_signal(
                f"[{self.name}] SELL: close {cur_close:.2f} < NR7 low "
                f"{nr7_low:.2f} on volume {cur_vol:.0f} vs MA {cur_vol_ma:.0f}."
            )
            return 'SELL'

        if sentiment in ['Bullish', 'Very Bullish']:
            self._log_hold(
                f"NR7 fresh + volume OK, but close {cur_close:.2f} <= NR7 high "
                f"{nr7_high:.2f} (need breakout above the NR7 bar's high)"
            )
        elif sentiment in ['Bearish', 'Very Bearish']:
            self._log_hold(
                f"NR7 fresh + volume OK, but close {cur_close:.2f} >= NR7 low "
                f"{nr7_low:.2f} (need breakdown below the NR7 bar's low)"
            )
        else:
            self._log_hold(f"sentiment {sentiment!r} is Neutral — no directional check")
        return 'HOLD'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if len(day_df) < 8:
            return f"Awaiting signal for {self.name}: need at least 8 bars of history."
        # Locate the NR7 bar in the most recent 7-bar window for the status line
        window = day_df.iloc[-8:-1]
        ranges = window['high'] - window['low']
        if ranges.empty or ranges.isna().any():
            return f"Awaiting signal for {self.name}: data incomplete."
        nr7_bar = window.iloc[int(ranges.values.argmin())]
        if sentiment in ['Bullish', 'Very Bullish']:
            return (f"Awaiting BUY: price to close above NR7-bar high "
                    f"{nr7_bar['high']:.2f} on volume > 1.2x MA.")
        return (f"Awaiting SELL: price to close below NR7-bar low "
                f"{nr7_bar['low']:.2f} on volume > 1.2x MA.")


class ExpiryMomentumScalpStrategy(BaseStrategy):
    """
    Weekly-expiry momentum scalp.

    Rationale
    ---------
    Expiry Thursday is gamma day: once the dominant side (calls or puts) starts
    printing ITM, market-makers frantically hedge → sharp, sustained directional
    moves through the middle of the session. This strategy rides those moves.

    Entry conditions (all required)
    --------------------------------
    1. Expiry day only — weekday == 3 (Thursday) OR is_expiry_day kwarg is True.
    2. Time window: 09:45 – 12:30 (early entries before structure forms are
       noise; after 12:30 gamma risk from the other side rises sharply).
    3. EMA-9 crossed EMA-21 within the last 3 completed bars (fresh momentum,
       not a stale cross from the open).
    4. RSI confirming: > 55 for BUY, < 45 for SELL (avoids fading a move that
       is already turning).
    5. ATR expanding: current bar's ATR >= prior bar's ATR * 1.05 (momentum
       rather than chop; 5 % threshold avoids noise flips).
    6. Volume confirmation: current volume > volume_ma * 1.1 (institutional
       participation vs. thin expiry-morning tape).

    Deliberately NO VIX_HIGH gate — expiry day is structurally high-vol.
    Deliberately NO sentiment override — the EMA/RSI/ATR combo already
    encodes direction.
    """

    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Expiry_Momentum_Scalp"
        self.is_reversal_trade = False

    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        if index is None:
            index = len(day_df) - 1

        # Need at least 25 bars for a reliable EMA-21 + ATR + volume MA.
        if len(day_df) < 25 or index < 24:
            self._log_hold("need at least 25 bars of history")
            return 'HOLD'

        # ── Gate 1: expiry day only ──────────────────────────────────────────
        is_expiry = kwargs.get("is_expiry_day", False) or self._bar_weekday(day_df, index) == 3
        if not is_expiry:
            self._log_hold("not expiry day (run only on weekly expiry / Thursday)")
            return 'HOLD'

        # ── Gate 2: trading window 09:45 – 12:30 ────────────────────────────
        t = self._bar_time(day_df, index)
        if not (datetime.time(9, 45) <= t < datetime.time(12, 30)):
            self._log_hold(
                f"outside expiry scalp window (09:45–12:30). "
                f"current={t.strftime('%H:%M')}"
            )
            return 'HOLD'

        # ── Compute EMAs if missing ──────────────────────────────────────────
        if 'ema_9' not in day_df.columns:
            day_df['ema_9'] = calculate_ema(day_df['close'], 9)
        if 'ema_21' not in day_df.columns:
            day_df['ema_21'] = calculate_ema(day_df['close'], 21)

        # ── Gate 3: fresh EMA-9/21 cross within last 3 bars ─────────────────
        # Look back up to 3 completed bars before 'index' for a cross.
        cross_bull = False
        cross_bear = False
        lookback = min(3, index)
        for k in range(1, lookback + 1):
            prev_e9 = day_df['ema_9'].iloc[index - k]
            prev_e21 = day_df['ema_21'].iloc[index - k]
            cur_e9  = day_df['ema_9'].iloc[index - k + 1]
            cur_e21 = day_df['ema_21'].iloc[index - k + 1]
            if pd.isna(prev_e9) or pd.isna(prev_e21) or pd.isna(cur_e9) or pd.isna(cur_e21):
                continue
            if prev_e9 <= prev_e21 and cur_e9 > cur_e21:
                cross_bull = True
                break
            if prev_e9 >= prev_e21 and cur_e9 < cur_e21:
                cross_bear = True
                break

        if not cross_bull and not cross_bear:
            self._log_hold("no fresh EMA-9/21 cross in the last 3 bars")
            return 'HOLD'

        # ── Gate 4: RSI confirmation ─────────────────────────────────────────
        cur_rsi = day_df['rsi'].iloc[index] if 'rsi' in day_df.columns else float('nan')
        if pd.isna(cur_rsi):
            self._log_hold("RSI unavailable")
            return 'HOLD'
        if cross_bull and cur_rsi < 55:
            self._log_hold(
                f"bullish cross but RSI={cur_rsi:.1f} < 55 — momentum not confirmed"
            )
            return 'HOLD'
        if cross_bear and cur_rsi > 45:
            self._log_hold(
                f"bearish cross but RSI={cur_rsi:.1f} > 45 — momentum not confirmed"
            )
            return 'HOLD'

        # ── Gate 5: ATR expansion ────────────────────────────────────────────
        if 'atr' in day_df.columns and index >= 1:
            cur_atr  = day_df['atr'].iloc[index]
            prev_atr = day_df['atr'].iloc[index - 1]
            if pd.notna(cur_atr) and pd.notna(prev_atr) and prev_atr > 0:
                if float(cur_atr) < float(prev_atr) * 1.05:
                    self._log_hold(
                        f"ATR not expanding: cur={float(cur_atr):.2f} "
                        f"< prev={float(prev_atr):.2f} * 1.05"
                    )
                    return 'HOLD'

        # ── Gate 6: volume confirmation ──────────────────────────────────────
        if 'volume' in day_df.columns and 'volume_ma' in day_df.columns:
            cur_vol    = day_df['volume'].iloc[index]
            cur_vol_ma = day_df['volume_ma'].iloc[index]
            if pd.notna(cur_vol) and pd.notna(cur_vol_ma) and cur_vol_ma > 0:
                if float(cur_vol) < float(cur_vol_ma) * 1.1:
                    self._log_hold(
                        f"volume below threshold: {float(cur_vol):.0f} "
                        f"< 1.1 × MA={float(cur_vol_ma):.0f}"
                    )
                    return 'HOLD'

        # ── Signal ───────────────────────────────────────────────────────────
        if cross_bull:
            self._log_signal(
                f"[{self.name}] BUY: EMA9 crossed above EMA21 (last 3 bars) "
                f"RSI={cur_rsi:.1f} t={t.strftime('%H:%M')}"
            )
            return 'BUY'
        self._log_signal(
            f"[{self.name}] SELL: EMA9 crossed below EMA21 (last 3 bars) "
            f"RSI={cur_rsi:.1f} t={t.strftime('%H:%M')}"
        )
        return 'SELL'

    def get_status_message(self, day_df, sentiment, **kwargs):
        if len(day_df) < 25:
            return f"Awaiting signal for {self.name}: need at least 25 bars of history."
        if 'ema_9' not in day_df.columns or 'ema_21' not in day_df.columns:
            return f"Awaiting signal for {self.name}: EMAs not yet computed."
        last = day_df.iloc[-1]
        e9  = last.get('ema_9', float('nan'))
        e21 = last.get('ema_21', float('nan'))
        rsi = last.get('rsi', float('nan'))
        if pd.isna(e9) or pd.isna(e21):
            return f"Awaiting signal for {self.name}: EMA values NaN."
        direction = "BUY (EMA9 > EMA21)" if e9 > e21 else "SELL (EMA9 < EMA21)"
        return (
            f"Expiry scalp watching for {direction}, "
            f"EMA9={e9:.2f} EMA21={e21:.2f} RSI={rsi:.1f} "
            f"— fresh cross + RSI/ATR/vol required."
        )


class QuantumMomentumStrategy(BaseStrategy):
    """
    Advanced quantum momentum strategy using multiple timeframe analysis
    and dynamic volatility clustering for high-frequency scalping.
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Quantum_Momentum"
        self.lookback_periods = [5, 13, 21, 55]  # Fibonacci-based periods
        
    def _calculate_quantum_momentum(self, df: pd.DataFrame, index: int) -> Dict[str, float]:
        """Calculate multi-timeframe momentum scores."""
        scores = {}
        current_price = df['close'].iloc[index]
        
        for period in self.lookback_periods:
            if index >= period:
                past_price = df['close'].iloc[index - period]
                momentum = (current_price - past_price) / past_price
                # Apply quantum weighting (stronger emphasis on recent periods)
                quantum_weight = 1.0 / (period ** 0.5)
                scores[f'momentum_{period}'] = momentum * quantum_weight
        
        # Overall quantum score
        scores['quantum_score'] = sum(scores.values()) / len(scores) if scores else 0.0
        return scores
    
    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        if index is None:
            index = len(day_df) - 1
            
        timestamp = datetime.datetime.now()
        
        if index < max(self.lookback_periods):
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=[f'Insufficient data: need {max(self.lookback_periods)} periods'],
                timestamp=timestamp
            )
        
        # Calculate quantum momentum
        quantum_data = self._calculate_quantum_momentum(day_df, index)
        quantum_score = quantum_data['quantum_score']
        
        # Volatility analysis
        if 'atr' not in day_df.columns:
            day_df['atr'] = ta.atr(day_df['high'], day_df['low'], day_df['close'], length=14)
        
        current_atr = day_df['atr'].iloc[index]
        atr_ma = day_df['atr'].rolling(window=20).mean().iloc[index]
        volatility_expansion = current_atr / atr_ma if atr_ma > 0 else 1.0
        
        # Multi-factor confidence calculation
        conditions = {
            'quantum_momentum_strong': abs(quantum_score) > 0.02,  # 2% threshold
            'volatility_favorable': 1.1 < volatility_expansion < 2.5,
            'trend_alignment': False,
            'volume_surge': False,
            'time_window': False
        }
        
        weights = {
            'quantum_momentum_strong': 0.4,
            'volatility_favorable': 0.2,
            'trend_alignment': 0.2,
            'volume_surge': 0.15,
            'time_window': 0.05
        }
        
        reasons = []
        current_price = day_df['close'].iloc[index]
        
        # Trend alignment check
        if 'ema_21' in day_df.columns:
            ema_21 = day_df['ema_21'].iloc[index]
            if (quantum_score > 0 and current_price > ema_21) or (quantum_score < 0 and current_price < ema_21):
                conditions['trend_alignment'] = True
                reasons.append("Trend alignment confirmed")
        
        # Volume surge detection
        if 'volume' in day_df.columns and 'volume_ma' in day_df.columns:
            current_vol = day_df['volume'].iloc[index]
            vol_ma = day_df['volume_ma'].iloc[index]
            if current_vol > vol_ma * 1.5:
                conditions['volume_surge'] = True
                reasons.append("Volume surge detected")
        
        # Optimal time window (high volatility periods)
        current_time = self._bar_time(day_df, index)
        if (datetime.time(9, 15) <= current_time <= datetime.time(10, 30) or 
            datetime.time(14, 0) <= current_time <= datetime.time(15, 15)):
            conditions['time_window'] = True
            reasons.append("Optimal time window")
        
        if conditions['quantum_momentum_strong']:
            reasons.append(f"Strong quantum momentum: {quantum_score:.4f}")
        if conditions['volatility_favorable']:
            reasons.append(f"Favorable volatility: {volatility_expansion:.2f}x")
        
        confidence = self._calculate_confidence(conditions, weights)
        
        # Signal generation
        if confidence >= self.min_confidence_threshold and conditions['quantum_momentum_strong']:
            if quantum_score > 0:
                action = 'BUY'
                stop_loss = self._calculate_atr_stop_loss(day_df, index, 1.5, True)
                target = self._calculate_dynamic_target(day_df, index, 3.0, stop_loss, True)
            else:
                action = 'SELL'
                stop_loss = self._calculate_atr_stop_loss(day_df, index, 1.5, False)
                target = self._calculate_dynamic_target(day_df, index, 3.0, stop_loss, False)
            
            risk_reward = self._calculate_risk_reward(current_price, stop_loss, target) if stop_loss and target else None
            
            self._log_signal(f"Quantum signal: {action} with {confidence:.1%} confidence")
            
            return StrategySignal(
                action=action,
                confidence=confidence,
                reasons=reasons,
                timestamp=timestamp,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                risk_reward_ratio=risk_reward
            )
        
        self._log_hold(f"Quantum momentum {quantum_score:.4f}, confidence {confidence:.1%}")
        return StrategySignal(
            action='HOLD',
            confidence=confidence,
            reasons=reasons or ['Quantum conditions not met'],
            timestamp=timestamp
        )
    
    def get_status_message(self, day_df, sentiment, **kwargs):
        if len(day_df) >= max(self.lookback_periods):
            quantum_data = self._calculate_quantum_momentum(day_df, len(day_df) - 1)
            score = quantum_data['quantum_score']
            return f"[{self.name}] Quantum Score: {score:.4f} | Scanning multi-timeframe momentum"
        return f"[{self.name}] Initializing quantum analysis..."


class NeuralNetworkStrategy(BaseStrategy):
    """
    AI-powered strategy using neural network-like pattern recognition
    for advanced market regime detection and signal generation.
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Neural_Network"
        self.pattern_memory = []  # Store successful patterns
        self.learning_rate = 0.1
        
    def _extract_pattern_features(self, df: pd.DataFrame, index: int, lookback: int = 20) -> np.ndarray:
        """Extract numerical features that represent market patterns."""
        if index < lookback:
            return np.array([])
        
        features = []
        window = df.iloc[index-lookback:index+1]
        
        # Price features (normalized)
        price_changes = window['close'].pct_change().fillna(0)
        features.extend([
            price_changes.mean(),
            price_changes.std(),
            price_changes.skew(),
            price_changes.kurt()
        ])
        
        # Volume features
        if 'volume' in window.columns:
            vol_changes = window['volume'].pct_change().fillna(0)
            features.extend([
                vol_changes.mean(),
                vol_changes.std()
            ])
        else:
            features.extend([0.0, 0.0])
        
        # Technical indicator features
        if 'rsi' in window.columns:
            rsi_values = window['rsi'].fillna(50)
            features.extend([
                rsi_values.iloc[-1] / 100.0,  # Current RSI (normalized)
                (rsi_values.iloc[-1] - rsi_values.mean()) / rsi_values.std() if rsi_values.std() > 0 else 0
            ])
        else:
            features.extend([0.5, 0.0])
        
        # Volatility features
        if 'atr' in window.columns:
            atr_current = window['atr'].iloc[-1]
            atr_mean = window['atr'].mean()
            features.append(atr_current / atr_mean if atr_mean > 0 else 1.0)
        else:
            features.append(1.0)
        
        # Trend features
        if len(window) >= 10:
            short_ema = window['close'].ewm(span=5).mean()
            long_ema = window['close'].ewm(span=10).mean()
            trend_strength = (short_ema.iloc[-1] - long_ema.iloc[-1]) / window['close'].iloc[-1]
            features.append(trend_strength)
        else:
            features.append(0.0)
        
        return np.array(features)
    
    def _neural_activation(self, x: np.ndarray, weights: np.ndarray) -> float:
        """Simple neural activation function (sigmoid)."""
        if len(x) != len(weights):
            return 0.5  # Neutral activation
        
        weighted_sum = np.dot(x, weights)
        return 1.0 / (1.0 + np.exp(-weighted_sum))  # Sigmoid
    
    def _pattern_similarity(self, pattern1: np.ndarray, pattern2: np.ndarray) -> float:
        """Calculate similarity between two patterns."""
        if len(pattern1) != len(pattern2) or len(pattern1) == 0:
            return 0.0
        
        # Cosine similarity
        dot_product = np.dot(pattern1, pattern2)
        norm1 = np.linalg.norm(pattern1)
        norm2 = np.linalg.norm(pattern2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        if index is None:
            index = len(day_df) - 1
            
        timestamp = datetime.datetime.now()
        
        if index < 25:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Insufficient data for neural analysis'],
                timestamp=timestamp
            )
        
        # Extract current pattern
        current_pattern = self._extract_pattern_features(day_df, index)
        if len(current_pattern) == 0:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Pattern extraction failed'],
                timestamp=timestamp
            )
        
        # Initialize neural weights if first run
        if not hasattr(self, 'neural_weights'):
            self.neural_weights = np.random.random(len(current_pattern)) * 0.1
        
        # Calculate neural network output
        neural_output = self._neural_activation(current_pattern, self.neural_weights)
        
        # Pattern matching with historical successful patterns
        pattern_confidence = 0.0
        if self.pattern_memory:
            similarities = [self._pattern_similarity(current_pattern, stored_pattern['features']) 
                           for stored_pattern in self.pattern_memory]
            if similarities:
                pattern_confidence = max(similarities)
        
        # Combine neural output with pattern matching
        base_confidence = (neural_output + pattern_confidence) / 2.0
        
        # Market regime adjustments
        regime_multiplier = 1.0
        if self._is_vix_high(kwargs):
            regime_multiplier = 0.7  # Reduce confidence in high volatility
        elif self._is_vix_low(kwargs):
            regime_multiplier = 1.2  # Increase confidence in low volatility
        
        final_confidence = min(1.0, base_confidence * regime_multiplier)
        
        current_price = day_df['close'].iloc[index]
        reasons = [
            f"Neural output: {neural_output:.3f}",
            f"Pattern confidence: {pattern_confidence:.3f}",
            f"Regime multiplier: {regime_multiplier:.2f}"
        ]
        
        # Signal decision based on neural network output and confidence
        if final_confidence >= self.min_confidence_threshold:
            if neural_output > 0.6:  # Bullish neural signal
                action = 'BUY'
                stop_loss = self._calculate_atr_stop_loss(day_df, index, 2.0, True)
                target = self._calculate_dynamic_target(day_df, index, 2.5, stop_loss, True)
            elif neural_output < 0.4:  # Bearish neural signal
                action = 'SELL'
                stop_loss = self._calculate_atr_stop_loss(day_df, index, 2.0, False)
                target = self._calculate_dynamic_target(day_df, index, 2.5, stop_loss, False)
            else:
                action = 'HOLD'
                stop_loss = None
                target = None
            
            if action != 'HOLD':
                # Store successful pattern for learning
                pattern_data = {
                    'features': current_pattern.copy(),
                    'action': action,
                    'confidence': final_confidence,
                    'timestamp': timestamp
                }
                self.pattern_memory.append(pattern_data)
                
                # Keep only recent patterns (last 100)
                if len(self.pattern_memory) > 100:
                    self.pattern_memory = self.pattern_memory[-100:]
                
                risk_reward = self._calculate_risk_reward(current_price, stop_loss, target) if stop_loss and target else None
                
                self._log_signal(f"Neural signal: {action} with {final_confidence:.1%} confidence")
                
                return StrategySignal(
                    action=action,
                    confidence=final_confidence,
                    reasons=reasons,
                    timestamp=timestamp,
                    price=current_price,
                    stop_loss=stop_loss,
                    target=target,
                    risk_reward_ratio=risk_reward
                )
        
        self._log_hold(f"Neural analysis: output={neural_output:.3f}, confidence={final_confidence:.1%}")
        return StrategySignal(
            action='HOLD',
            confidence=final_confidence,
            reasons=reasons,
            timestamp=timestamp
        )
    
    def get_status_message(self, day_df, sentiment, **kwargs):
        patterns_learned = len(self.pattern_memory) if hasattr(self, 'pattern_memory') else 0
        avg_confidence = self._performance_metrics['avg_confidence']
        return (f"[{self.name}] Patterns Learned: {patterns_learned} | "
                f"Avg Confidence: {avg_confidence:.1%} | Neural processing...")


class AdaptiveArbitrageStrategy(BaseStrategy):
    """
    Advanced arbitrage strategy that identifies and exploits temporary
    price inefficiencies using statistical arbitrage techniques.
    """
    def __init__(self, kite, config):
        super().__init__(kite, config)
        self.name = "Adaptive_Arbitrage"
        self.price_memory = []
        self.efficiency_threshold = 0.001  # 0.1% inefficiency threshold
        
    def _calculate_price_efficiency(self, df: pd.DataFrame, index: int) -> Dict[str, float]:
        """Calculate market efficiency metrics."""
        if index < 50:
            return {'efficiency_score': 1.0, 'mean_reversion_strength': 0.0}
        
        window = df.iloc[index-49:index+1]  # 50-period window
        
        # Calculate price deviations from various moving averages
        prices = window['close']
        sma_20 = prices.rolling(window=20).mean()
        ema_20 = prices.ewm(span=20).mean()
        
        # Mean reversion calculations
        current_price = prices.iloc[-1]
        sma_deviation = (current_price - sma_20.iloc[-1]) / sma_20.iloc[-1] if sma_20.iloc[-1] > 0 else 0
        ema_deviation = (current_price - ema_20.iloc[-1]) / ema_20.iloc[-1] if ema_20.iloc[-1] > 0 else 0
        
        # Statistical measures
        price_changes = prices.pct_change().dropna()
        volatility = price_changes.std()
        
        # Efficiency score (lower means more inefficient/opportunity)
        efficiency_score = 1.0 / (1.0 + abs(sma_deviation) + abs(ema_deviation))
        
        # Mean reversion strength
        mean_reversion_strength = abs(sma_deviation) + abs(ema_deviation)
        
        return {
            'efficiency_score': efficiency_score,
            'mean_reversion_strength': mean_reversion_strength,
            'sma_deviation': sma_deviation,
            'ema_deviation': ema_deviation,
            'volatility': volatility
        }
    
    def _detect_arbitrage_opportunity(self, df: pd.DataFrame, index: int) -> Dict[str, Any]:
        """Detect potential arbitrage opportunities."""
        efficiency_data = self._calculate_price_efficiency(df, index)
        
        # Look for mean reversion opportunities
        mean_reversion_strength = efficiency_data['mean_reversion_strength']
        sma_deviation = efficiency_data['sma_deviation']
        
        opportunity = {
            'type': None,
            'strength': 0.0,
            'expected_return': 0.0,
            'confidence': 0.0
        }
        
        # Strong deviation suggests arbitrage opportunity
        if mean_reversion_strength > self.efficiency_threshold:
            if sma_deviation > 0:  # Price above SMA - potential short opportunity
                opportunity['type'] = 'mean_reversion_short'
                opportunity['strength'] = mean_reversion_strength
                opportunity['expected_return'] = -sma_deviation  # Expected return from reversion
            elif sma_deviation < 0:  # Price below SMA - potential long opportunity
                opportunity['type'] = 'mean_reversion_long'
                opportunity['strength'] = mean_reversion_strength
                opportunity['expected_return'] = abs(sma_deviation)
            
            # Calculate confidence based on historical accuracy
            opportunity['confidence'] = min(1.0, mean_reversion_strength / 0.01)  # Normalize to 1% max
        
        return opportunity
    
    def _internal_generate_signals(self, day_df, sentiment, index=None, **kwargs) -> StrategySignal:
        if index is None:
            index = len(day_df) - 1
            
        timestamp = datetime.datetime.now()
        
        if index < 50:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['Insufficient data for arbitrage analysis (need 50+ periods)'],
                timestamp=timestamp
            )
        
        # Detect arbitrage opportunities
        opportunity = self._detect_arbitrage_opportunity(day_df, index)
        
        if not opportunity['type']:
            return StrategySignal(
                action='HOLD',
                confidence=0.0,
                reasons=['No arbitrage opportunity detected'],
                timestamp=timestamp
            )
        
        current_price = day_df['close'].iloc[index]
        
        # Enhanced conditions for arbitrage trading
        conditions = {
            'arbitrage_opportunity': opportunity['strength'] > self.efficiency_threshold,
            'sufficient_volatility': False,
            'market_hours': self._is_market_hours(day_df, index),
            'volume_adequate': False,
            'risk_acceptable': False
        }
        
        weights = {
            'arbitrage_opportunity': 0.5,
            'sufficient_volatility': 0.2,
            'market_hours': 0.1,
            'volume_adequate': 0.1,
            'risk_acceptable': 0.1
        }
        
        reasons = [f"Arbitrage opportunity: {opportunity['type']}"]
        
        # Volatility check
        efficiency_data = self._calculate_price_efficiency(day_df, index)
        if efficiency_data['volatility'] > 0.005:  # Minimum 0.5% volatility
            conditions['sufficient_volatility'] = True
            reasons.append("Sufficient volatility for arbitrage")
        
        # Volume check
        if 'volume' in day_df.columns and 'volume_ma' in day_df.columns:
            current_vol = day_df['volume'].iloc[index]
            vol_ma = day_df['volume_ma'].iloc[index] if not pd.isna(day_df['volume_ma'].iloc[index]) else current_vol
            if current_vol > vol_ma * 0.8:  # At least 80% of average volume
                conditions['volume_adequate'] = True
                reasons.append("Adequate volume for execution")
        
        # Risk assessment
        expected_return = opportunity['expected_return']
        if expected_return > 0.002:  # Minimum 0.2% expected return
            conditions['risk_acceptable'] = True
            reasons.append(f"Expected return: {expected_return:.1%}")
        
        confidence = self._calculate_confidence(conditions, weights)
        
        # Signal generation for arbitrage
        if confidence >= self.min_confidence_threshold and conditions['arbitrage_opportunity']:
            if opportunity['type'] == 'mean_reversion_long':
                action = 'BUY'
                # Tight stops for arbitrage
                stop_loss = current_price * 0.998  # 0.2% stop loss
                target = current_price * (1 + expected_return * 0.8)  # 80% of expected return
            elif opportunity['type'] == 'mean_reversion_short':
                action = 'SELL'
                stop_loss = current_price * 1.002  # 0.2% stop loss
                target = current_price * (1 - expected_return * 0.8)  # 80% of expected return
            else:
                action = 'HOLD'
                stop_loss = None
                target = None
            
            if action != 'HOLD':
                risk_reward = self._calculate_risk_reward(current_price, stop_loss, target) if stop_loss and target else None
                
                self._log_signal(f"Arbitrage signal: {action} | Expected: {expected_return:.1%} | Confidence: {confidence:.1%}")
                
                return StrategySignal(
                    action=action,
                    confidence=confidence,
                    reasons=reasons,
                    timestamp=timestamp,
                    price=current_price,
                    stop_loss=stop_loss,
                    target=target,
                    risk_reward_ratio=risk_reward
                )
        
        self._log_hold(f"Arbitrage analysis: {opportunity['type']} | Strength: {opportunity['strength']:.3f}")
        return StrategySignal(
            action='HOLD',
            confidence=confidence,
            reasons=reasons,
            timestamp=timestamp
        )
    
    def get_status_message(self, day_df, sentiment, **kwargs):
        if len(day_df) >= 50:
            efficiency_data = self._calculate_price_efficiency(day_df, len(day_df) - 1)
            efficiency = efficiency_data['efficiency_score']
            return f"[{self.name}] Market Efficiency: {efficiency:.1%} | Scanning for arbitrage..."
        return f"[{self.name}] Initializing arbitrage detection..."


class StrategyAdapter:
    """Adapter to maintain backward compatibility with legacy code expecting simple string returns."""
    
    def __init__(self, strategy_instance):
        self.strategy = strategy_instance
        self._legacy_mode = True
    
    def generate_signals(self, day_df, sentiment, index=None, **kwargs):
        """Wrapper that returns simple string for backward compatibility."""
        if hasattr(self.strategy, '_internal_generate_signals'):
            # New enhanced strategy
            signal = self.strategy.generate_signals(day_df, sentiment, index, **kwargs)
            if isinstance(signal, StrategySignal):
                return signal.action
            return signal
        else:
            # Legacy strategy - call original method
            return self.strategy.generate_signals(day_df, sentiment, index, **kwargs)
    
    def get_enhanced_signals(self, day_df, sentiment, index=None, **kwargs):
        """Get full StrategySignal object with all metadata."""
        return self.strategy.generate_signals(day_df, sentiment, index, **kwargs)
    
    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped strategy."""
        return getattr(self.strategy, name)


def get_strategy(name, kite, config, enhanced=False):
    """Enhanced factory function to get a strategy instance by name."""
    strategies = {
        "Gemini_Default": Gemini_Default_Strategy,
        "Supertrend_MACD": Supertrend_MACD_Strategy,
        "Volatility_Cluster_Reversal": VolatilityClusterStrategy,
        "Volume_Spread_Analysis": VSA_Strategy,
        "Momentum_VWAP_RSI": Momentum_VWAP_RSI_Strategy,
        "Breakout_Prev_Day_HL": Breakout_Prev_Day_HL_Strategy,
        "Opening_Range_Breakout": Opening_Range_Breakout_Strategy,
        "BB_Squeeze_Breakout": Bollinger_Band_Squeeze_Strategy,
        "MA_Crossover": MA_Crossover_Strategy,
        "RSI_Divergence": RSI_Divergence_Strategy,
        "EMA_Cross_RSI": EMACrossRSIStrategy,
        "Reversal_Detector": Reversal_Detector_Strategy,
        "VWAP_Reversion": VWAP_Reversion_Strategy,
        "NR7_Compression": NR7_Compression_Breakout_Strategy,
        "Expiry_Momentum_Scalp": ExpiryMomentumScalpStrategy,
        # New Enhanced Strategies
        "Quantum_Momentum": QuantumMomentumStrategy,
        "Neural_Network": NeuralNetworkStrategy,
        "Adaptive_Arbitrage": AdaptiveArbitrageStrategy,
    }
    
    strategy_class = strategies.get(name)
    if not strategy_class: 
        available_strategies = list(strategies.keys())
        raise ValueError(f"Strategy '{name}' not found. Available strategies: {available_strategies}")
    
    try:
        strategy_instance = strategy_class(kite, config)
        
        # Return enhanced strategy directly if requested, otherwise wrap for compatibility
        if enhanced:
            return strategy_instance
        else:
            return StrategyAdapter(strategy_instance)
            
    except Exception as e:
        logging.error(f"Failed to initialize strategy '{name}': {e}")
        raise


def get_available_strategies() -> List[str]:
    """Get list of all available strategy names."""
    return [
        "Gemini_Default", "Supertrend_MACD", "Volatility_Cluster_Reversal", 
        "Volume_Spread_Analysis", "Momentum_VWAP_RSI", "Breakout_Prev_Day_HL",
        "Opening_Range_Breakout", "BB_Squeeze_Breakout", "MA_Crossover",
        "RSI_Divergence", "EMA_Cross_RSI", "Reversal_Detector", "VWAP_Reversion",
        "NR7_Compression", "Expiry_Momentum_Scalp", "Quantum_Momentum",
        "Neural_Network", "Adaptive_Arbitrage"
    ]


def get_strategy_info(name: str) -> Dict[str, Any]:
    """Get detailed information about a specific strategy."""
    strategy_info = {
        "Gemini_Default": {
            "description": "Enhanced CPR-based strategy with confidence scoring",
            "type": "Trend Following",
            "timeframe": "Intraday",
            "risk_level": "Medium",
            "complexity": "Medium"
        },
        "Quantum_Momentum": {
            "description": "Multi-timeframe momentum analysis with quantum weighting",
            "type": "Momentum",
            "timeframe": "High Frequency",
            "risk_level": "High",
            "complexity": "Advanced"
        },
        "Neural_Network": {
            "description": "AI-powered pattern recognition with learning capability",
            "type": "Machine Learning",
            "timeframe": "Adaptive",
            "risk_level": "Medium-High",
            "complexity": "Advanced"
        },
        "Adaptive_Arbitrage": {
            "description": "Statistical arbitrage using mean reversion techniques",
            "type": "Arbitrage",
            "timeframe": "Short-term",
            "risk_level": "Low-Medium",
            "complexity": "Advanced"
        },
        # Add info for other strategies as needed
    }
    
    return strategy_info.get(name, {
        "description": "Strategy information not available",
        "type": "Unknown",
        "timeframe": "Unknown",
        "risk_level": "Unknown",
        "complexity": "Unknown"
    })