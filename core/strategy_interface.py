"""
Strategy abstraction and ensemble support.

This file adds a lightweight strategy ensemble wrapper so multiple strategy
modules can be run together and weighted by recent performance or a fixed
blended allocation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


class IStrategy(ABC):
    """Abstract base class for trading strategies."""

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> str:
        """Generate trading signal based on data."""
        raise NotImplementedError

    @abstractmethod
    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        """Calculate stop loss level."""
        raise NotImplementedError

    @abstractmethod
    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        """Calculate take profit level."""
        raise NotImplementedError

    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Get current strategy parameters."""
        raise NotImplementedError

    @abstractmethod
    def set_parameters(self, parameters: Dict[str, Any]):
        """Set strategy parameters."""
        raise NotImplementedError


class RSI_MACD_Strategy(IStrategy):
    """RSI + MACD combined strategy."""

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

    def generate_signal(self, data: pd.DataFrame) -> str:
        if len(data) < self.macd_slow:
            return "HOLD"

        rsi = self._calculate_rsi(data["close"], self.rsi_period)
        macd_line, signal_line, _ = self._calculate_macd(
            data["close"], self.macd_fast, self.macd_slow, self.macd_signal
        )

        if rsi < self.rsi_oversold and macd_line.iloc[-1] > signal_line.iloc[-1]:
            return "BUY"
        if rsi > self.rsi_overbought and macd_line.iloc[-1] < signal_line.iloc[-1]:
            return "SELL"
        return "HOLD"

    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        atr = self._calculate_atr(data, 14)
        return entry_price - atr * 2

    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        atr = self._calculate_atr(data, 14)
        return entry_price + atr * 3

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
        }

    def set_parameters(self, parameters: Dict[str, Any]):
        for key, value in parameters.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def _calculate_rsi(self, prices: pd.Series, period: int) -> float:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0)

    def _calculate_macd(self, prices: pd.Series, fast: int, slow: int, signal: int):
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist_line = macd_line - signal_line
        return macd_line, signal_line, hist_line

    def _calculate_atr(self, data: pd.DataFrame, period: int) -> float:
        high = data["high"]
        low = data["low"]
        close = data["close"]
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return float(atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0.0)


class BollingerReversalStrategy(IStrategy):
    """Bollinger Bands mean reversion strategy."""

    def __init__(self, bb_length: int = 20, bb_mult: float = 2.0):
        self.bb_length = bb_length
        self.bb_mult = bb_mult

    def generate_signal(self, data: pd.DataFrame) -> str:
        if len(data) < self.bb_length:
            return "HOLD"

        bb_middle, bb_upper, bb_lower = self._calculate_bb(
            data["close"], self.bb_length, self.bb_mult
        )
        current_price = float(data["close"].iloc[-1])
        if current_price < float(bb_lower.iloc[-1]):
            return "BUY"
        if current_price > float(bb_upper.iloc[-1]):
            return "SELL"
        return "HOLD"

    def get_stop_loss(self, data: pd.DataFrame, entry_price: float) -> float:
        _, _, bb_lower = self._calculate_bb(data["close"], self.bb_length, self.bb_mult)
        return float(bb_lower.iloc[-1])

    def get_take_profit(self, data: pd.DataFrame, entry_price: float) -> float:
        _, bb_upper, _ = self._calculate_bb(data["close"], self.bb_length, self.bb_mult)
        return float(bb_upper.iloc[-1])

    def get_parameters(self) -> Dict[str, Any]:
        return {"bb_length": self.bb_length, "bb_mult": self.bb_mult}

    def set_parameters(self, parameters: Dict[str, Any]):
        for key, value in parameters.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def _calculate_bb(self, prices: pd.Series, length: int, mult: float):
        bb_middle = prices.rolling(window=length).mean()
        bb_std = prices.rolling(window=length).std(ddof=0)
        bb_upper = bb_middle + bb_std * mult
        bb_lower = bb_middle - bb_std * mult
        return bb_middle, bb_upper, bb_lower


class StrategyEnsemble:
    """Weighted ensemble runner for multiple strategies."""

    def __init__(
        self,
        strategies: Optional[Sequence[IStrategy]] = None,
        weights: Optional[Sequence[float]] = None,
    ):
        self.strategies = list(strategies or [])
        self.weights = list(weights or [1.0] * len(self.strategies))
        if len(self.weights) != len(self.strategies):
            self.weights = [1.0] * len(self.strategies)

    def add_strategy(self, strategy: IStrategy, weight: float = 1.0):
        self.strategies.append(strategy)
        self.weights.append(weight)

    def generate_signal(self, data: pd.DataFrame) -> str:
        if not self.strategies:
            return "HOLD"

        weighted_votes = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        for strategy, weight in zip(self.strategies, self.weights):
            signal = strategy.generate_signal(data)
            weighted_votes[signal] += float(weight)

        if (
            weighted_votes["BUY"] > weighted_votes["SELL"]
            and weighted_votes["BUY"] > weighted_votes["HOLD"]
        ):
            return "BUY"
        if (
            weighted_votes["SELL"] > weighted_votes["BUY"]
            and weighted_votes["SELL"] > weighted_votes["HOLD"]
        ):
            return "SELL"
        return "HOLD"


__all__ = [
    "IStrategy",
    "RSI_MACD_Strategy",
    "BollingerReversalStrategy",
    "StrategyEnsemble",
]

# Backward-compatible import used by the existing backtest modules.
Bollinger_Reversal_Strategy = BollingerReversalStrategy
