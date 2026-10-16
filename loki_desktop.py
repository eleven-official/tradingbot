# -*- coding: utf-8 -*-
"""
LOKI PRO - Professional Trading Terminal v7.0
=============================================
Enterprise-Grade Algorithmic Trading Workstation
- Real market data integration (CCXT/Binance) + simulated mode
- Professional candlestick visualization with real OHLCV
- Paper execution with explicit data provenance
- Josh's Strategy v2.0 (experimental; requires independent validation)
- Enhanced ML Ensemble with 7 market regimes
- Autonomous paper pilot with measured outcomes
- Self-learning with advanced performance tracking
- Risk guards: daily loss limit, max drawdown halt, trailing stops
- Professional charting, backtester, and audit log
- Modern ultra-dark professional interface
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import math
import random
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional, Tuple, Any
from core.copilot import LokiCopilot
from core.strategy_lab import evaluate_strategy
from core.desktop_presenter import (
    candle_is_current, performance_evidence, quote_is_fresh, risk_sized_quantity, validate_risk_settings,
)

# Force UTF-8 on stdio so emoji/Unicode log output never raises on a Windows
# cp1252 console, or when stdout/stderr is redirected to a pipe or file.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

# Native Windows Audio and App ID
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

try:
    import ctypes
    # Sets unique Windows Taskbar App ID for proper taskbar grouping and pinning
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Loki.TradingTerminal.Pro.v4")
except Exception:
    pass

# CustomTkinter UI Framework
import customtkinter as ctk

# Matplotlib for Trading Charts
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

# mplfinance for Professional Candlestick Charts
import mplfinance as mpf

# CCXT for Real Market Data
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False


class RealMarketData:
    """Real market data fetcher using CCXT for live crypto prices."""
    
    def __init__(self):
        self.exchange = None
        self.symbols = {
            "BTC/USD": "BTC/USDT",
            "ETH/USD": "ETH/USDT",
            "SOL/USD": "SOL/USDT",
        }
        self.connected = False
        
    def connect(self):
        """Connect to Binance for real market data."""
        if not CCXT_AVAILABLE:
            return False
        
        try:
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'timeout': 10000,
                'options': {'defaultType': 'spot'},
            })
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to exchange: {e}")
            return False
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100):
        """Fetch OHLCV data from exchange."""
        if not self.connected or not self.exchange:
            return None
        
        try:
            exchange_symbol = self.symbols.get(symbol, symbol)
            ohlcv = self.exchange.fetch_ohlcv(exchange_symbol, timeframe, limit=limit)
            
            # Convert to internal format
            bars = []
            for candle in ohlcv:
                bars.append({
                    'timestamp': pd.to_datetime(candle[0], unit='ms', utc=True),
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                })
            
            return bars
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None
    
    def fetch_ticker(self, symbol: str):
        """Fetch current ticker price."""
        if not self.connected or not self.exchange:
            return None
        
        try:
            exchange_symbol = self.symbols.get(symbol, symbol)
            ticker = self.exchange.fetch_ticker(exchange_symbol)
            source_time = ticker.get('timestamp')
            if source_time is not None and not quote_is_fresh(float(source_time) / 1000, time.time()):
                return None
            return ticker['last']
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return None

# Configure Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("loki_terminal.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("LokiTerminal")


def _json_default(obj: Any) -> Any:
    """Convert numpy scalars to native Python types for safe JSON serialization."""
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# =====================================================================
# PALETTE & DESIGN SYSTEM
# =====================================================================
COLORS = {
    "bg_dark": "#0A0E27",       # Deep rich dark blue
    "card_bg": "#151932",       # Elevated dark cards
    "card_alt": "#1F2450",      # Secondary cards
    "card_border": "#2A2F63",   # Border lines
    "accent_cyan": "#00D9FF",   # Bright cyan
    "accent_blue": "#4A7CFF",   # Vibrant blue
    "accent_purple": "#A78BFA", # Soft purple
    "accent_pink": "#F472B6",   # Soft pink
    "success": "#00E676",       # Bright green
    "success_dim": "#00804A",   # Dark green
    "danger": "#FF5252",        # Bright red
    "danger_dim": "#B71C1C",    # Dark red
    "warning": "#FFB74D",       # Bright orange
    "warning_dim": "#E65100",   # Dark orange
    "text_primary": "#FFFFFF",  # Pure white
    "text_secondary": "#B8C5D6",# Soft gray-blue
    "text_muted": "#A1AEC3",    # Readable supporting text on dark surfaces
}


# =====================================================================
# ADVANCED MARKET SIMULATOR (9 DIVERSE ASSETS)
# =====================================================================
class AdvancedMarketSimulator:
    """
    Simulates tick data with GARCH volatility clustering, mean-reversion drift,
    jump-diffusion, and realistic OHLCV bars across multiple timeframes.
    """

    SYMBOLS = {
        "crypto": {
            "BTC/USD": {"base": 67450.0, "vol": 0.032, "trend": 0.0001, "category": "crypto"},
            "ETH/USD": {"base": 3520.0, "vol": 0.038, "trend": 0.00015, "category": "crypto"},
            "SOL/USD": {"base": 172.5, "vol": 0.048, "trend": 0.0002, "category": "crypto"},
        },
        "stocks": {
            "AAPL": {"base": 218.4, "vol": 0.018, "trend": 0.00004, "category": "stocks"},
            "TSLA": {"base": 252.3, "vol": 0.035, "trend": 0.00008, "category": "stocks"},
            "NVDA": {"base": 884.2, "vol": 0.029, "trend": 0.00012, "category": "stocks"},
            "MSFT": {"base": 421.5, "vol": 0.016, "trend": 0.00005, "category": "stocks"},
        },
        "indices": {
            "SPY": {"base": 546.0, "vol": 0.011, "trend": 0.00003, "category": "indices"},
            "QQQ": {"base": 469.5, "vol": 0.015, "trend": 0.00004, "category": "indices"},
        }
    }

    def __init__(self):
        self.all_symbols: Dict[str, Dict[str, Any]] = {}
        for cat, syms in self.SYMBOLS.items():
            self.all_symbols.update(syms)

        self.prices: Dict[str, float] = {s: d["base"] for s, d in self.all_symbols.items()}
        self.last_prices: Dict[str, float] = self.prices.copy()
        self.tick_directions: Dict[str, str] = {s: "flat" for s in self.all_symbols}
        self.vol_states: Dict[str, float] = {s: 1.0 for s in self.all_symbols}
        self.trend_states: Dict[str, float] = {s: 0.0 for s in self.all_symbols}

        self.histories: Dict[str, deque] = {s: deque(maxlen=600) for s in self.all_symbols}
        self.ohlcv_data: Dict[str, deque] = {s: deque(maxlen=250) for s in self.all_symbols}
        self.bar_seconds = 300

        self._lock = threading.Lock()
        self._seed_histories()

    def set_bar_seconds(self, seconds: int):
        with self._lock:
            self.bar_seconds = max(60, int(seconds))

    def _seed_histories(self):
        """Seed realistic historical OHLCV data."""
        for sym, data in self.all_symbols.items():
            price = data["base"]
            vol = data["vol"]
            now = datetime.now()

            for i in range(240):
                bar_time = now - timedelta(minutes=(240 - i) * 5)
                open_p = price
                drift = np.random.normal(0, vol * 0.4) * price
                high_p = open_p + abs(np.random.normal(0, vol * 0.7)) * price
                low_p = open_p - abs(np.random.normal(0, vol * 0.7)) * price
                close_p = open_p + drift
                close_p = max(min(close_p, high_p), low_p)

                vol_qty = int(np.random.lognormal(9, 1.2))

                bar = {
                    "timestamp": bar_time,
                    "open": round(open_p, 4 if open_p < 10 else 2),
                    "high": round(high_p, 4 if high_p < 10 else 2),
                    "low": round(low_p, 4 if low_p < 10 else 2),
                    "close": round(close_p, 4 if close_p < 10 else 2),
                    "volume": vol_qty
                }
                self.ohlcv_data[sym].append(bar)
                self.histories[sym].append(close_p)
                price = close_p

            self.prices[sym] = round(price, 4 if price < 10 else 2)
            self.last_prices[sym] = self.prices[sym]

    def tick(self) -> Dict[str, float]:
        """Generate realistic price tick across all assets."""
        with self._lock:
            for sym, data in self.all_symbols.items():
                curr = self.prices[sym]
                self.last_prices[sym] = curr

                # GARCH-style volatility clustering
                shock = abs(np.random.normal(0, 0.12))
                self.vol_states[sym] = 0.90 * self.vol_states[sym] + 0.10 * shock
                eff_vol = data["vol"] * (0.8 + 0.4 * self.vol_states[sym])

                # Persistent trend drift
                t_shock = np.random.normal(0, 0.0008)
                self.trend_states[sym] = 0.94 * self.trend_states[sym] + 0.06 * t_shock
                drift = data["trend"] + self.trend_states[sym]

                # Jump diffusion (0.15% chance)
                jump = 0.0
                if np.random.random() < 0.0015:
                    jump = np.random.normal(0, eff_vol * 2.5) * curr

                noise = np.random.normal(drift, eff_vol * 0.05) * curr
                new_p = max(curr + noise + jump, 0.01)
                new_p = round(new_p, 4 if new_p < 10 else 2)

                if new_p > curr:
                    self.tick_directions[sym] = "up"
                elif new_p < curr:
                    self.tick_directions[sym] = "down"
                else:
                    self.tick_directions[sym] = "flat"

                self.prices[sym] = new_p
                self.histories[sym].append(new_p)

                # Update OHLCV bar
                if len(self.ohlcv_data[sym]) > 0:
                    last_bar = self.ohlcv_data[sym][-1]
                    now = datetime.now()
                    if (now - last_bar["timestamp"]).total_seconds() > self.bar_seconds:
                        new_bar = {
                            "timestamp": now,
                            "open": curr,
                            "high": max(curr, new_p),
                            "low": min(curr, new_p),
                            "close": new_p,
                            "volume": int(np.random.lognormal(8.5, 1.0))
                        }
                        self.ohlcv_data[sym].append(new_bar)
                    else:
                        last_bar["high"] = max(last_bar["high"], new_p)
                        last_bar["low"] = min(last_bar["low"], new_p)
                        last_bar["close"] = new_p
                        last_bar["volume"] += random.randint(1, 15)

            return self.prices.copy()

    def get_ohlcv(self, symbol: str, bars: int = 80) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.ohlcv_data.get(symbol, []))[-bars:]

    def get_price(self, symbol: str) -> float:
        with self._lock:
            return self.prices.get(symbol, 0.0)

    def get_change_pct(self, symbol: str) -> float:
        with self._lock:
            base = self.all_symbols.get(symbol, {}).get("base", 0.0)
            curr = self.prices.get(symbol, base)
            if base <= 0:
                return 0.0
            return (curr - base) / base * 100.0


# =====================================================================
# MATHEMATICALLY SOUND TRADING STRATEGIES
# =====================================================================
class MomentumStrategy:
    """Multi-indicator Trend Momentum (EMA 12/26, MACD Histogram, SMA 50, RSI 14)."""

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 30:
            return None

        closes = df['close']
        ema_12 = closes.ewm(span=12, adjust=False).mean()
        ema_26 = closes.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        sma_50 = closes.rolling(window=min(50, len(closes))).mean()

        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        latest_close = closes.iloc[-1]
        latest_hist = macd_hist.iloc[-1]
        prev_hist = macd_hist.iloc[-2]
        latest_rsi = rsi.iloc[-1]

        bull_conditions = [
            latest_close > sma_50.iloc[-1],
            latest_hist > 0,
            latest_hist > prev_hist,
            44 < latest_rsi < 72,
            ema_12.iloc[-1] > ema_26.iloc[-1],
        ]
        bear_conditions = [
            latest_close < sma_50.iloc[-1],
            latest_hist < 0,
            latest_hist < prev_hist,
            28 < latest_rsi < 56,
            ema_12.iloc[-1] < ema_26.iloc[-1],
        ]

        bull_score = sum(bull_conditions) / len(bull_conditions)
        bear_score = sum(bear_conditions) / len(bear_conditions)

        if bull_score >= 0.7:
            return {
                "action": "BUY",
                "confidence": round(bull_score, 2),
                "strategy": "momentum",
                "entry_price": latest_close,
                "stop_loss": round(latest_close * 0.975, 2),
                "take_profit": round(latest_close * 1.050, 2),
                "reason": f"EMA/MACD Momentum ({bull_score:.0%}), RSI={latest_rsi:.1f}"
            }
        elif bear_score >= 0.7:
            return {
                "action": "SELL",
                "confidence": round(bear_score, 2),
                "strategy": "momentum",
                "entry_price": latest_close,
                "reason": f"Bearish MACD Momentum ({bear_score:.0%}), RSI={latest_rsi:.1f}"
            }
        return None


class MeanReversionStrategy:
    """Bollinger Bands & Statistical Z-Score with RSI extreme detection."""

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 25:
            return None

        closes = df['close']
        sma_20 = closes.rolling(20).mean()
        std_20 = closes.rolling(20).std() + 1e-9
        upper_bb = sma_20 + (std_20 * 2.0)
        lower_bb = sma_20 - (std_20 * 2.0)
        z_score = (closes - sma_20) / std_20

        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        latest_close = closes.iloc[-1]
        latest_z = z_score.iloc[-1]
        latest_rsi = rsi.iloc[-1]

        oversold_hits = sum([
            latest_close <= lower_bb.iloc[-1] * 1.005,
            latest_z < -1.8,
            latest_rsi < 33,
        ])
        overbought_hits = sum([
            latest_close >= upper_bb.iloc[-1] * 0.995,
            latest_z > 1.8,
            latest_rsi > 67,
        ])

        if oversold_hits >= 2:
            conf = min(0.95, 0.62 + abs(latest_z) * 0.15)
            return {
                "action": "BUY",
                "confidence": round(conf, 2),
                "strategy": "mean_reversion",
                "entry_price": latest_close,
                "stop_loss": round(lower_bb.iloc[-1] * 0.985, 2),
                "take_profit": round(sma_20.iloc[-1], 2),
                "reason": f"Oversold BB bounce (Z={latest_z:.2f}, RSI={latest_rsi:.1f})"
            }
        elif overbought_hits >= 2:
            conf = min(0.95, 0.62 + abs(latest_z) * 0.15)
            return {
                "action": "SELL",
                "confidence": round(conf, 2),
                "strategy": "mean_reversion",
                "entry_price": latest_close,
                "reason": f"Overbought BB exhaustion (Z={latest_z:.2f}, RSI={latest_rsi:.1f})"
            }
        return None


class BreakoutStrategy:
    """Breakout Hunter with PRIOR-BAR rolling extremes and volume surge filter (Bug-free!)."""

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 25:
            return None

        df = df.copy()
        # Correct 20-bar lookback (excludes current bar)
        df['prior_high_20'] = df['high'].shift(1).rolling(20).max()
        df['prior_low_20'] = df['low'].shift(1).rolling(20).min()

        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        atr = tr.rolling(14).mean()
        vol_sma = df['volume'].rolling(20).mean() + 1e-9
        vol_ratio = df['volume'] / vol_sma

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        latest_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else latest['close'] * 0.02
        latest_vol_ratio = vol_ratio.iloc[-1]

        if (latest['close'] > latest['prior_high_20'] and 
            prev['close'] <= prev['prior_high_20'] and 
            latest_vol_ratio >= 1.2):
            
            conf = min(0.95, 0.70 + (latest_vol_ratio - 1.2) * 0.15)
            return {
                "action": "BUY",
                "confidence": round(conf, 2),
                "strategy": "breakout",
                "entry_price": latest['close'],
                "stop_loss": round(latest['close'] - latest_atr * 1.5, 2),
                "take_profit": round(latest['close'] + latest_atr * 3.0, 2),
                "reason": f"20-Bar Channel Breakout + {latest_vol_ratio:.1f}x volume surge"
            }
        elif (latest['close'] < latest['prior_low_20'] and 
              prev['close'] >= prev['prior_low_20'] and 
              latest_vol_ratio >= 1.2):
            
            conf = min(0.95, 0.70 + (latest_vol_ratio - 1.2) * 0.15)
            return {
                "action": "SELL",
                "confidence": round(conf, 2),
                "strategy": "breakout",
                "entry_price": latest['close'],
                "reason": f"20-Bar Breakdown + {latest_vol_ratio:.1f}x volume surge"
            }
        return None


class VolatilitySurfaceStrategy:
    """Volatility compression squeeze & VWAP expansion."""

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 30:
            return None

        vwap = (df['close'] * df['volume']).rolling(20).sum() / (df['volume'].rolling(20).sum() + 1e-9)
        returns = df['close'].pct_change()
        realized_vol = returns.rolling(20).std() * np.sqrt(252)

        vol_low = realized_vol.iloc[-1] < realized_vol.quantile(0.35)
        latest_close = df['close'].iloc[-1]
        latest_vwap = vwap.iloc[-1]

        if vol_low and latest_close > latest_vwap * 1.002:
            return {
                "action": "BUY",
                "confidence": 0.74,
                "strategy": "volatility_surface",
                "entry_price": latest_close,
                "stop_loss": round(latest_vwap * 0.992, 2),
                "take_profit": round(latest_close * 1.045, 2),
                "reason": f"Volatility compression squeeze above VWAP (${latest_vwap:.2f})"
            }
        return None


class JoshStrategy:
    """
    Josh's Strategy v2.0 - Enhanced Professional Trading System
    
    Advanced multi-factor momentum strategy with evolutionary features:
    1. EMA 9/21/50 triple confirmation for trend
    2. MACD histogram for momentum confirmation
    3. Volume surge detection (1.5x average)
    4. RSI 14 with overbought/oversold filtering
    5. ATR-based dynamic stop loss (1.5x ATR)
    6. Support/Resistance level detection
    7. Trend strength indicator (ADX-style)
    8. Market structure analysis (higher highs/lows)
    
    Uses indicator confluence; scores are not calibrated probabilities of profit.
    """

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 50:
            return None

        closes = df['close']
        highs = df['high']
        lows = df['low']
        volumes = df['volume']
        
        # Triple EMA for trend confirmation
        ema_9 = closes.ewm(span=9, adjust=False).mean()
        ema_21 = closes.ewm(span=21, adjust=False).mean()
        ema_50 = closes.ewm(span=50, adjust=False).mean()
        
        # MACD for momentum
        ema_12 = closes.ewm(span=12, adjust=False).mean()
        ema_26 = closes.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        # Enhanced volume analysis
        vol_sma_20 = volumes.rolling(20).mean()
        vol_sma_50 = volumes.rolling(50).mean()
        vol_ratio_20 = volumes / vol_sma_20
        vol_ratio_50 = volumes / vol_sma_50
        
        # RSI for timing
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        
        # ATR for dynamic stops
        high_low = highs - lows
        high_close = np.abs(highs - closes.shift())
        low_close = np.abs(lows - closes.shift())
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        atr = tr.rolling(14).mean()
        
        # Support/Resistance levels (local highs/lows)
        recent_highs = highs.rolling(20).max()
        recent_lows = lows.rolling(20).min()
        
        # Trend strength (using price vs EMAs)
        trend_strength_long = (closes - ema_50) / ema_50 * 100
        trend_strength_short = (ema_50 - closes) / ema_50 * 100
        
        latest_close = closes.iloc[-1]
        latest_high = highs.iloc[-1]
        latest_low = lows.iloc[-1]
        latest_ema_9 = ema_9.iloc[-1]
        latest_ema_21 = ema_21.iloc[-1]
        latest_ema_50 = ema_50.iloc[-1]
        latest_rsi = rsi.iloc[-1]
        latest_vol_ratio_20 = vol_ratio_20.iloc[-1]
        latest_vol_ratio_50 = vol_ratio_50.iloc[-1]
        latest_macd_hist = macd_hist.iloc[-1]
        latest_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else latest_close * 0.02
        latest_resistance = recent_highs.iloc[-1]
        latest_support = recent_lows.iloc[-1]
        
        # Enhanced EMA cross detection
        ema_9_cross_21_up = (latest_ema_9 > latest_ema_21) and (ema_9.iloc[-2] <= ema_21.iloc[-2])
        ema_9_cross_21_down = (latest_ema_9 < latest_ema_21) and (ema_9.iloc[-2] >= ema_21.iloc[-2])
        
        # Triple EMA alignment
        ema_aligned_up = latest_ema_9 > latest_ema_21 > latest_ema_50
        ema_aligned_down = latest_ema_9 < latest_ema_21 < latest_ema_50
        
        # Trend strength
        strong_trend_up = trend_strength_long.iloc[-1] > 2.0
        strong_trend_down = trend_strength_short.iloc[-1] > 2.0
        
        # MACD confirmation
        macd_bullish = latest_macd_hist > 0 and macd_hist.iloc[-1] > macd_hist.iloc[-2]
        macd_bearish = latest_macd_hist < 0 and macd_hist.iloc[-1] < macd_hist.iloc[-2]
        
        # Volume surge (stronger requirement)
        vol_surge = latest_vol_ratio_20 >= 1.5 and latest_vol_ratio_50 >= 1.3
        
        # RSI timing (wider acceptable range)
        rsi_buy_zone = 42 < latest_rsi < 68
        rsi_sell_zone = 32 < latest_rsi < 58
        
        # Price not at resistance/support
        not_at_resistance = latest_close < latest_resistance * 0.995
        not_at_support = latest_close > latest_support * 1.005
        
        # Long conditions (seven independent indicator checks)
        long_conditions = [
            ema_9_cross_21_up or ema_aligned_up,  # EMA cross or alignment
            latest_close > latest_ema_50,         # Above long-term trend
            vol_surge,                            # Strong volume surge
            rsi_buy_zone,                         # RSI in buy zone
            macd_bullish,                         # MACD momentum
            not_at_resistance,                    # Not at resistance
            strong_trend_up or trend_strength_long.iloc[-1] > 1.0,  # Trend strength
        ]
        
        # Short conditions (seven independent indicator checks)
        short_conditions = [
            ema_9_cross_21_down or ema_aligned_down,  # EMA cross or alignment
            latest_close < latest_ema_50,              # Below long-term trend
            vol_surge,                                 # Strong volume surge
            rsi_sell_zone,                             # RSI in sell zone
            macd_bearish,                              # MACD momentum
            not_at_support,                            # Not at support
            strong_trend_down or trend_strength_short.iloc[-1] > 1.0,  # Trend strength
        ]
        
        long_score = sum(long_conditions) / len(long_conditions)
        short_score = sum(short_conditions) / len(short_conditions)
        
        # Long signal (higher threshold for better quality)
        if long_score >= 0.857:  # 6/7 conditions
            sl = round(latest_close - (latest_atr * 1.5), 2)
            tp = round(latest_close + (latest_atr * 3.5), 2)  # Better R:R
            return {
                "action": "BUY",
                "confidence": round(long_score, 2),
                "strategy": "josh",
                "entry_price": latest_close,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"Josh v2: Triple EMA + MACD + Vol {latest_vol_ratio_20:.1f}x + RSI {latest_rsi:.1f}"
            }
        
        # Short signal (higher threshold for better quality)
        elif short_score >= 0.857:  # 6/7 conditions
            sl = round(latest_close + (latest_atr * 1.5), 2)
            tp = round(latest_close - (latest_atr * 3.5), 2)  # Better R:R
            return {
                "action": "SELL",
                "confidence": round(short_score, 2),
                "strategy": "josh",
                "entry_price": latest_close,
                "stop_loss": sl,
                "take_profit": tp,
                "reason": f"Josh v2: Triple EMA Down + MACD + Vol {latest_vol_ratio_20:.1f}x + RSI {latest_rsi:.1f}"
            }
        
        return None


class MLEnsembleStrategy:
    """
    Revolutionary Adaptive Multi-Factor AI Consensus Engine v2.0
    Classifies Market Regime and weights votes from all strategies.
    Enhanced with adaptive learning and regime-based optimization.
    """

    def __init__(self):
        self.strat_josh = JoshStrategy()
        self.strat_momentum = MomentumStrategy()
        self.strat_mean_rev = MeanReversionStrategy()
        self.strat_breakout = BreakoutStrategy()
        self.strat_vol = VolatilitySurfaceStrategy()
        
        # Adaptive weights that evolve based on performance
        self.adaptive_weights = {
            "bull_trend": {"josh": 0.35, "momentum": 0.30, "breakout": 0.20, "mean_reversion": 0.10, "volatility_surface": 0.05},
            "bear_trend": {"josh": 0.35, "momentum": 0.30, "breakout": 0.20, "mean_reversion": 0.10, "volatility_surface": 0.05},
            "ranging": {"josh": 0.25, "mean_reversion": 0.35, "momentum": 0.20, "breakout": 0.10, "volatility_surface": 0.10},
            "high_volatility": {"josh": 0.30, "breakout": 0.30, "volatility_surface": 0.25, "momentum": 0.10, "mean_reversion": 0.05},
        }

    def classify_regime(self, df: pd.DataFrame) -> str:
        """Enhanced market regime classification with more granular detection."""
        closes = df['close']
        sma_20 = closes.rolling(20).mean()
        sma_50 = closes.rolling(min(50, len(closes))).mean()
        returns = closes.pct_change()
        # Rolling annualized volatility (Series) — a scalar .std() here would break .iloc later.
        volatility = returns.rolling(20).std() * np.sqrt(252)
        
        # ADX-style trend strength (using price range)
        high_low = df['high'] - df['low']
        tr = high_low.rolling(14).mean()
        atr_pct = tr / closes * 100
        
        # Enhanced regime detection
        latest_close = closes.iloc[-1]
        latest_sma_20 = sma_20.iloc[-1]
        latest_sma_50 = sma_50.iloc[-1]
        latest_vol = volatility.iloc[-1]
        latest_atr_pct = atr_pct.iloc[-1] if not pd.isna(atr_pct.iloc[-1]) else 2.0
        
        # Strong uptrend
        if latest_close > latest_sma_20 > latest_sma_50 and latest_vol > 0.20:
            return "strong_bull"
        # Strong downtrend
        elif latest_close < latest_sma_20 < latest_sma_50 and latest_vol > 0.20:
            return "strong_bear"
        # Moderate uptrend
        elif latest_close > latest_sma_20 > latest_sma_50:
            return "bull_trend"
        # Moderate downtrend
        elif latest_close < latest_sma_20 < latest_sma_50:
            return "bear_trend"
        # High volatility
        elif latest_vol > 0.40 or latest_atr_pct > 3.0:
            return "high_volatility"
        # Low volatility (consolidation)
        elif latest_vol < 0.10:
            return "low_volatility"
        # Ranging
        else:
            return "ranging"

    def generate_signal(self, df: pd.DataFrame, weight_overrides: Optional[Dict[str, Dict[str, float]]] = None) -> Optional[Dict[str, Any]]:
        if len(df) < 30:
            return None

        closes = df['close']
        
        # Enhanced regime classification
        regime = self.classify_regime(df)
        
        # Gather signals
        sig_josh = self.strat_josh.generate_signal(df)
        sig_mom = self.strat_momentum.generate_signal(df)
        sig_mr = self.strat_mean_rev.generate_signal(df)
        sig_bo = self.strat_breakout.generate_signal(df)
        sig_vol = self.strat_vol.generate_signal(df)

        sub_signals = [s for s in [sig_josh, sig_mom, sig_mr, sig_bo, sig_vol] if s is not None]

        # Enhanced adaptive weights
        enhanced_weights = {
            "strong_bull": {"josh": 0.40, "momentum": 0.35, "breakout": 0.15, "mean_reversion": 0.05, "volatility_surface": 0.05},
            "strong_bear": {"josh": 0.40, "momentum": 0.35, "breakout": 0.15, "mean_reversion": 0.05, "volatility_surface": 0.05},
            "bull_trend": {"josh": 0.35, "momentum": 0.30, "breakout": 0.20, "mean_reversion": 0.10, "volatility_surface": 0.05},
            "bear_trend": {"josh": 0.35, "momentum": 0.30, "breakout": 0.20, "mean_reversion": 0.10, "volatility_surface": 0.05},
            "ranging": {"josh": 0.25, "mean_reversion": 0.35, "momentum": 0.20, "breakout": 0.10, "volatility_surface": 0.10},
            "high_volatility": {"josh": 0.30, "breakout": 0.30, "volatility_surface": 0.25, "momentum": 0.10, "mean_reversion": 0.05},
            "low_volatility": {"josh": 0.20, "mean_reversion": 0.40, "volatility_surface": 0.20, "momentum": 0.15, "breakout": 0.05},
        }
        
        source = weight_overrides if weight_overrides else enhanced_weights
        weights = source.get(regime, enhanced_weights["ranging"])

        buy_weight = 0.0
        sell_weight = 0.0
        reasons = []
        sl_targets = []
        tp_targets = []

        for s in sub_signals:
            name = s.get("strategy")
            w = weights.get(name, 0.25)
            conf = s.get("confidence", 0.6)

            if s["action"] == "BUY":
                buy_weight += w * conf
                reasons.append(f"{name.upper()} ({conf:.0%})")
                if "stop_loss" in s: sl_targets.append(s["stop_loss"])
                if "take_profit" in s: tp_targets.append(s["take_profit"])
            elif s["action"] == "SELL":
                sell_weight += w * conf
                reasons.append(f"{name.upper()} ({conf:.0%})")

        latest_close = closes.iloc[-1]

        if buy_weight >= 0.35 and buy_weight > sell_weight * 1.4:
            final_conf = min(0.96, max(0.65, buy_weight * 1.3))
            sl = min(sl_targets) if sl_targets else round(latest_close * 0.97, 2)
            tp = max(tp_targets) if tp_targets else round(latest_close * 1.06, 2)
            return {
                "action": "BUY",
                "confidence": round(final_conf, 2),
                "strategy": "ml_ensemble",
                "entry_price": latest_close,
                "stop_loss": sl,
                "take_profit": tp,
                "regime": regime,
                "factors": {"josh": 0.9 if sig_josh else 0.1, "momentum": 0.8 if sig_mom else 0.2, "mean_rev": 0.8 if sig_mr else 0.2, "breakout": 0.9 if sig_bo else 0.1},
                "reason": f"Regime: {regime.upper()} | Confluence: " + ", ".join(reasons)
            }
        elif sell_weight >= 0.35 and sell_weight > buy_weight * 1.4:
            final_conf = min(0.96, max(0.65, sell_weight * 1.3))
            sl = max(sl_targets) if sl_targets else round(latest_close * 1.03, 2)
            tp = min(tp_targets) if tp_targets else round(latest_close * 0.94, 2)
            return {
                "action": "SELL",
                "confidence": round(final_conf, 2),
                "strategy": "ml_ensemble",
                "entry_price": latest_close,
                "stop_loss": sl,
                "take_profit": tp,
                "regime": regime,
                "factors": {"josh": 0.9 if sig_josh else 0.1, "momentum": 0.8 if sig_mom else 0.2, "mean_rev": 0.8 if sig_mr else 0.2, "breakout": 0.9 if sig_bo else 0.1},
                "reason": f"Regime: {regime.upper()} | Confluence: " + ", ".join(reasons)
            }
        return None


# =====================================================================
# RAPID HISTORICAL QUANT BACKTESTER
# =====================================================================
class QuantBacktester:
    """Instantaneous bar-by-bar historical backtest and Monte Carlo simulation."""

    @staticmethod
    def run_backtest(ohlcv_bars: List[Dict[str, Any]], strategy_name: str = "ml_ensemble",
                     initial_cash: float = 25000.0) -> Dict[str, Any]:
        """Exploratory selected-strategy test; signals execute at the next bar open."""
        if len(ohlcv_bars) < 40:
            return {"error": "Insufficient historical bars"}
        df = pd.DataFrame(ohlcv_bars)
        strategies = {"josh": JoshStrategy(), "ml_ensemble": MLEnsembleStrategy(),
                      "momentum": MomentumStrategy(), "mean_reversion": MeanReversionStrategy(),
                      "breakout": BreakoutStrategy(), "volatility_surface": VolatilitySurfaceStrategy()}
        strategy = strategies.get(strategy_name, strategies["josh"])
        fee, slippage = 0.0005, 0.0001
        cash, quantity, entry, entry_cost = initial_cash, 0.0, 0.0, 0.0
        stop, target = 0.0, 0.0
        entry_time = None
        trades, equity, benchmark = [], [], []
        total_fees = 0.0
        first_open = float(df.iloc[30]["open"])

        def close_position(reference, timestamp, reason):
            nonlocal cash, quantity, total_fees
            fill = reference * (1 - slippage)
            exit_fee = fill * quantity * fee
            proceeds = fill * quantity - exit_fee
            cash += proceeds
            total_fees += exit_fee
            trades.append({"entry_time": entry_time, "exit_time": timestamp,
                "entry_price": entry, "exit_price": fill, "pnl": proceeds - entry_cost,
                "reason": reason})
            quantity = 0.0

        for index in range(30, len(df)):
            bar = df.iloc[index]
            open_price, high, low, close = (float(bar[key]) for key in ("open", "high", "low", "close"))
            signal = strategy.generate_signal(df.iloc[:index])  # Excludes this execution candle.
            closed_this_bar = False
            if quantity > 0:
                if open_price <= stop:
                    close_position(open_price, bar["timestamp"], "GAP_STOP")
                elif open_price >= target:
                    close_position(target, bar["timestamp"], "TAKE_PROFIT")
                elif signal and signal.get("action") == "SELL":
                    close_position(open_price, bar["timestamp"], "STRATEGY_EXIT")
                closed_this_bar = quantity == 0
            if quantity == 0 and not closed_this_bar and signal and signal.get("action") == "BUY" and signal.get("confidence", 0) >= 0.65:
                fill = open_price * (1 + slippage)
                candidate_stop = signal.get("stop_loss", fill * 0.97)
                candidate_target = signal.get("take_profit", fill * 1.06)
                if candidate_stop is not None and candidate_target is not None and 0 < candidate_stop < fill < candidate_target:
                    entry, stop, target = fill, candidate_stop, candidate_target
                    entry_cost = cash * 0.15
                    quantity = entry_cost / (fill * (1 + fee))
                    total_fees += fill * quantity * fee
                    cash -= entry_cost
                    entry_time = bar["timestamp"]
            if quantity > 0:
                # A stop takes precedence when both levels touch in one candle.
                if low <= stop:
                    close_position(stop, bar["timestamp"], "STOP_LOSS")
                elif high >= target:
                    close_position(target, bar["timestamp"], "TAKE_PROFIT")
            equity.append(cash + quantity * close)
            benchmark.append(initial_cash * close / first_open)
        if quantity > 0:
            close_position(float(df.iloc[-1]["close"]), df.iloc[-1]["timestamp"], "BACKTEST_END")
            equity[-1] = cash
        wins = [trade for trade in trades if trade["pnl"] > 0]
        losses = [trade for trade in trades if trade["pnl"] <= 0]
        gross_profit = sum(trade["pnl"] for trade in wins)
        gross_loss = abs(sum(trade["pnl"] for trade in losses))
        peak, drawdown = initial_cash, 0.0
        for value in equity:
            peak = max(peak, value)
            drawdown = max(drawdown, (peak - value) / peak)
        return {"initial_cash": initial_cash, "final_equity": cash,
            "net_profit": cash - initial_cash, "return_pct": (cash / initial_cash - 1) * 100,
            "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "max_drawdown": drawdown * 100, "total_trades": len(trades),
            "equity_curve": equity, "benchmark_curve": benchmark, "trades": trades,
            "total_fees": total_fees, "evaluation": "exploratory_same_sample",
            "assumptions": ["Signals use prior closed candles and execute at next open.",
                "5 bps fee and 1 bp adverse slippage per side; stop wins ambiguous candles.",
                "Exploratory sample; use independent holdouts to assess a market edge."]}


# =====================================================================
# RISK MANAGEMENT & PORTFOLIO ENGINE
# =====================================================================
class AdvancedRiskManager:
    """Stop-distance risk budgets with cost and portfolio allocation caps."""

    def __init__(self):
        self.risk_per_trade_pct = 0.02
        self.max_open_positions = 5

    def calculate_position_size(self, capital: float, entry_price: float, 
                                stop_loss: Optional[float], confidence: float = 0.7,
                                cash: Optional[float] = None, fee_fraction: float = 0.0005,
                                slippage_fraction: float = 0.0001) -> float:
        if stop_loss is None or not math.isfinite(confidence) or confidence <= 0:
            return 0.0
        try:
            budget = min(capital * 0.20, capital if cash is None else cash)
            return risk_sized_quantity(capital, budget, entry_price, stop_loss,
                self.risk_per_trade_pct * min(1.0, confidence), fee_fraction, slippage_fraction)
        except ValueError:
            return 0.0


DEFAULT_REGIME_WEIGHTS = {
    "bull_trend": {"momentum": 0.40, "breakout": 0.35, "mean_reversion": 0.15, "volatility_surface": 0.10},
    "bear_trend": {"momentum": 0.40, "breakout": 0.35, "mean_reversion": 0.15, "volatility_surface": 0.10},
    "ranging": {"mean_reversion": 0.45, "momentum": 0.25, "breakout": 0.15, "volatility_surface": 0.15},
    "high_volatility": {"breakout": 0.40, "volatility_surface": 0.30, "mean_reversion": 0.15, "momentum": 0.15},
}


class SelfImprovementEngine:
    """Retunes ensemble weights from closed-trade outcomes. Paper-learning only."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path("state") / "loki_self_improve.json"
        self.strategy_stats: Dict[str, Dict[str, float]] = {}
        self.regime_weights = json.loads(json.dumps(DEFAULT_REGIME_WEIGHTS))
        self.adaptations = 0
        self.last_note = "Waiting for closed trades before retuning weights."
        self.min_confidence = 0.70
        self.enabled = True

        # Performance tracking
        self.total_trades = 0
        self.total_wins = 0
        self.total_pnl = 0.0
        self.current_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.performance_score = 0.5

        # Learning history
        self.mistake_patterns: Dict[str, int] = {}

        self.load()

    def _stat(self, name: str) -> Dict[str, float]:
        if name not in self.strategy_stats:
            self.strategy_stats[name] = {"trades": 0.0, "wins": 0.0, "pnl": 0.0, "confidence_sum": 0.0}
        return self.strategy_stats[name]

    def record_closed_trade(self, strategy: str, pnl: float, confidence: float = 0.7, reason: str = ""):
        name = (strategy or "unknown").split()[0]
        st = self._stat(name)
        st["trades"] += 1
        st["pnl"] += float(pnl)
        st["confidence_sum"] += confidence
        if pnl > 0:
            st["wins"] += 1
            self.current_streak = max(0, self.current_streak + 1)
            self.max_win_streak = max(self.max_win_streak, self.current_streak)
        else:
            self.current_streak = min(0, self.current_streak - 1)
            self.max_loss_streak = max(self.max_loss_streak, abs(self.current_streak))
            if "oversold" in reason.lower():
                self.mistake_patterns["oversold_reversal"] = self.mistake_patterns.get("oversold_reversal", 0) + 1
            elif "breakout" in reason.lower():
                self.mistake_patterns["false_breakout"] = self.mistake_patterns.get("false_breakout", 0) + 1

        self.total_trades += 1
        self.total_wins += 1 if pnl > 0 else 0
        self.total_pnl += pnl

        self._update_performance_score()

        if self.enabled and st["trades"] >= 3 and int(st["trades"]) % 3 == 0:
            self._retune()
            self.save()

    def _update_performance_score(self):
        if self.total_trades < 5:
            self.performance_score = 0.5
            return

        win_rate = self.total_wins / self.total_trades
        avg_pnl_per_trade = self.total_pnl / self.total_trades

        score = (win_rate * 0.4) + (min(avg_pnl_per_trade / 100, 1.0) * 0.3) + (self.current_streak / 10 * 0.3)
        self.performance_score = max(0.0, min(1.0, score))

    def _retune(self):
        scores: Dict[str, float] = {}
        for name, st in self.strategy_stats.items():
            if name == "ml_ensemble" or st["trades"] < 2:
                continue
            wr = st["wins"] / max(1.0, st["trades"])
            avg = st["pnl"] / max(1.0, st["trades"])
            avg_conf = st["confidence_sum"] / max(1.0, st["trades"])
            scores[name] = wr + (0.15 if avg > 0 else -0.15) + (avg_conf - 0.5) * 0.1

        if not scores:
            self.last_note = "Not enough strategy-specific samples to retune yet."
            return

        best = max(scores, key=scores.get)
        worst = min(scores, key=scores.get)
        for regime, weights in self.regime_weights.items():
            if best in weights and worst in weights and best != worst:
                take = min(0.05, weights[worst] * 0.25)
                weights[worst] = max(0.05, weights[worst] - take)
                weights[best] = min(0.55, weights[best] + take)
                total = sum(weights.values())
                for k in weights:
                    weights[k] = round(weights[k] / total, 4)

        closed = sum(int(s["trades"]) for s in self.strategy_stats.values())
        wins = sum(int(s["wins"]) for s in self.strategy_stats.values())
        wr = wins / max(1, closed)

        if wr < 0.40 or self.performance_score < 0.4:
            self.min_confidence = min(0.90, self.min_confidence + 0.03)
        elif wr > 0.60 and self.performance_score > 0.6:
            self.min_confidence = max(0.60, self.min_confidence - 0.01)

        self.adaptations += 1
        self.last_note = (
            f"Adaptation #{self.adaptations}: boosted {best}, reduced {worst}. "
            f"Performance: {self.performance_score:.1%}, Conviction floor: {self.min_confidence:.0%}."
        )
        logger.info(self.last_note)

    def get_ai_readiness(self) -> Dict[str, Any]:
        if self.total_trades < 10:
            return {
                "ready": False,
                "reason": f"Need at least 10 trades (current: {self.total_trades})",
                "score": 0.0,
                "min_confidence": self.min_confidence
            }

        if self.performance_score < 0.45:
            return {
                "ready": False,
                "reason": f"Performance too low ({self.performance_score:.1%} < 45%)",
                "score": self.performance_score,
                "min_confidence": self.min_confidence
            }

        if self.total_wins / self.total_trades < 0.45:
            return {
                "ready": False,
                "reason": f"Win rate too low ({self.total_wins/self.total_trades:.1%} < 45%)",
                "score": self.performance_score,
                "min_confidence": self.min_confidence
            }

        return {
            "ready": True,
            "reason": "AI performing well - ready for auto-trading",
            "score": self.performance_score,
            "min_confidence": self.min_confidence
        }

    def summary_line(self) -> str:
        closed = int(sum(s["trades"] for s in self.strategy_stats.values()))
        wins = int(sum(s["wins"] for s in self.strategy_stats.values()))
        pnl = sum(s["pnl"] for s in self.strategy_stats.values())
        score = f"Learning score {self.performance_score:.1%}" if closed >= 5 else "Learning score: awaiting 5 exits"
        return f"Closed {closed} | Wins {wins} | {score} | Paper P&L ${pnl:+,.2f} | Tweaks {self.adaptations}"

    def load(self):
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.strategy_stats = data.get("strategy_stats", self.strategy_stats)
                self.regime_weights = data.get("regime_weights", self.regime_weights)
                self.adaptations = int(data.get("adaptations", 0))
                self.last_note = data.get("last_note", self.last_note)
                self.min_confidence = float(data.get("min_confidence", self.min_confidence))
                self.total_trades = int(data.get("total_trades", 0))
                self.total_wins = int(data.get("total_wins", 0))
                self.total_pnl = float(data.get("total_pnl", 0.0))
                self.performance_score = float(data.get("performance_score", 0.5))
                self.mistake_patterns = data.get("mistake_patterns", {})
        except Exception as ex:
            logger.warning(f"Could not load self-improve state: {ex}")

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "strategy_stats": self.strategy_stats,
                "regime_weights": self.regime_weights,
                "adaptations": self.adaptations,
                "last_note": self.last_note,
                "min_confidence": self.min_confidence,
                "total_trades": self.total_trades,
                "total_wins": self.total_wins,
                "total_pnl": self.total_pnl,
                "performance_score": self.performance_score,
                "mistake_patterns": self.mistake_patterns,
            }
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as ex:
            logger.warning(f"Could not save self-improve state: {ex}")


class TradingGuard:
    """Halts autonomous trading on daily loss or max drawdown."""

    def __init__(self):
        self.max_daily_loss_pct = 0.04
        self.max_drawdown_pct = 0.12
        self.halted = False
        self.halt_reason = ""
        self.day_key: Optional[str] = None
        self.day_start_equity: Optional[float] = None

    def evaluate(self, metrics: Dict[str, Any], day_key: Optional[str] = None) -> Optional[str]:
        today = day_key or datetime.now(timezone.utc).date().isoformat()
        equity = metrics.get("equity", 0)
        if today != self.day_key and math.isfinite(equity) and equity > 0:
            self.day_key, self.day_start_equity = today, equity
        if self.halted:
            return self.halt_reason
        start = self.day_start_equity
        if start and (equity - start) / start <= -self.max_daily_loss_pct:
            self.halted = True
            self.halt_reason = f"UTC daily loss limit ({self.max_daily_loss_pct:.0%}) hit"
            return self.halt_reason
        if metrics.get("max_drawdown_pct", 0) / 100.0 >= self.max_drawdown_pct:
            self.halted = True
            self.halt_reason = f"Max drawdown ({self.max_drawdown_pct:.0%}) hit"
            return self.halt_reason
        return None

    def reset(self):
        self.halted = False
        self.halt_reason = ""


class ProfessionalAccount:
    """Trading Account with continuous protective exits and realistic fees."""

    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.equity_curve: deque = deque(maxlen=1000)
        self.drawdown_curve: deque = deque(maxlen=1000)

        self.commission_pct = 0.0005
        self.slippage_bps = 1.0
        self.trailing_stop_enabled = True
        self.trailing_stop_pct = 0.02
        self.default_stop_loss_pct = 0.03
        self.default_take_profit_pct = 0.06

        self._lock = threading.Lock()
        self.equity_curve.append(initial_capital)
        self.drawdown_curve.append(0.0)

    def get_equity(self, prices: Dict[str, float]) -> float:
        with self._lock:
            val = sum(
                p["quantity"] * prices.get(sym, p["avg_price"])
                for sym, p in self.positions.items()
            )
            return self.cash + val

    def execute_trade(self, symbol: str, action: str, quantity: float, price: float,
                      strategy: str = "manual", stop_loss: Optional[float] = None,
                      take_profit: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
        if action.upper() not in {"BUY", "SELL"}:
            return {"status": "rejected", "reason": "Use BUY or SELL."}
        if not all(math.isfinite(v) and v > 0 for v in (quantity, price)):
            return {"status": "rejected", "reason": "Price and quantity must be finite and positive."}
        if action.upper() == "BUY" and (
            (stop_loss is not None and (not math.isfinite(stop_loss) or not 0 < stop_loss < price))
            or (take_profit is not None and (not math.isfinite(take_profit) or take_profit <= price))
        ):
            return {"status": "rejected", "reason": "Stop must be below entry; target must be above entry."}
        with self._lock:
            if action.upper() == "BUY":
                return self._buy(symbol, quantity, price, strategy, stop_loss, take_profit, reason)
            else:
                return self._sell(symbol, quantity, price, strategy, reason)

    def _buy(self, symbol: str, quantity: float, price: float, strategy: str,
             stop_loss: Optional[float], take_profit: Optional[float], reason: str) -> Dict[str, Any]:
        slippage = price * (self.slippage_bps / 10000.0)
        fill_price = price + slippage
        cost = quantity * fill_price
        comm = cost * self.commission_pct
        total_cost = cost + comm

        if total_cost > self.cash:
            return {"status": "rejected", "reason": f"Insufficient funds (${self.cash:,.2f} available, ${total_cost:,.2f} required)"}

        self.cash -= total_cost

        if stop_loss is None:
            stop_loss = fill_price * (1 - self.default_stop_loss_pct)
        if take_profit is None:
            take_profit = fill_price * (1 + self.default_take_profit_pct)

        if symbol in self.positions:
            pos = self.positions[symbol]
            new_qty = pos["quantity"] + quantity
            new_avg = (pos["avg_price"] * pos["quantity"] + fill_price * quantity) / new_qty
            pos["quantity"] = new_qty
            pos["avg_price"] = new_avg
            pos["entry_fees"] = pos.get("entry_fees", 0.0) + comm
            pos["peak_price"] = max(pos.get("peak_price", new_avg), fill_price)
            pos["stop_loss"] = stop_loss
            pos["take_profit"] = take_profit
        else:
            self.positions[symbol] = {
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": fill_price,
                "entry_time": datetime.now(),
                "peak_price": fill_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "trailing_stop": self.trailing_stop_enabled,
                "strategy": strategy,
                "entry_fees": comm,
            }

        trade = {
            "timestamp": datetime.now(),
            "symbol": symbol,
            "action": "BUY",
            "quantity": quantity,
            "price": fill_price,
            "commission": comm,
            "strategy": strategy,
            "reason": reason or strategy,
            "status": "filled"
        }
        self.trade_history.append(trade)
        return {"status": "filled", "trade": trade}

    def _sell(self, symbol: str, quantity: float, price: float, strategy: str, reason: str) -> Dict[str, Any]:
        if symbol not in self.positions:
            return {"status": "rejected", "reason": f"No open position in {symbol}"}

        pos = self.positions[symbol]
        strategy = pos.get("strategy", strategy)
        avg_price = pos["avg_price"]
        sell_qty = min(quantity, pos["quantity"])

        slippage = price * (self.slippage_bps / 10000.0)
        fill_price = price - slippage
        revenue = sell_qty * fill_price
        comm = revenue * self.commission_pct
        net_revenue = revenue - comm

        entry_fee_share = pos.get("entry_fees", 0.0) * sell_qty / pos["quantity"]
        net_pnl = (fill_price - avg_price) * sell_qty - comm - entry_fee_share

        self.cash += net_revenue
        pos["quantity"] -= sell_qty
        pos["entry_fees"] = max(0.0, pos.get("entry_fees", 0.0) - entry_fee_share)

        if pos["quantity"] < 1e-7:
            del self.positions[symbol]

        trade = {
            "timestamp": datetime.now(),
            "symbol": symbol,
            "action": "SELL",
            "quantity": sell_qty,
            "price": fill_price,
            "commission": comm,
            "pnl": net_pnl,
            "pnl_pct": net_pnl / (avg_price * sell_qty + entry_fee_share) * 100 if avg_price * sell_qty else 0.0,
            "strategy": strategy,
            "reason": reason or strategy,
            "status": "filled"
        }
        self.trade_history.append(trade)
        return {"status": "filled", "trade": trade}

    def close_single_position(self, symbol: str, current_price: float, reason: str = "MANUAL_CLOSE") -> Optional[Dict[str, Any]]:
        if not math.isfinite(current_price) or current_price <= 0:
            return {"status": "rejected", "reason": "A valid price is required to close a paper position."}
        with self._lock:
            if symbol not in self.positions:
                return None
            qty = self.positions[symbol]["quantity"]
            return self._sell(symbol, qty, current_price, self.positions[symbol].get("strategy", "manual"), reason)

    def check_risk_triggers(self, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        closed_trades = []
        with self._lock:
            symbols = list(self.positions.keys())
            for sym in symbols:
                pos = self.positions[sym]
                curr_p = current_prices.get(sym, 0.0)
                if curr_p <= 0: continue

                # Upward Trailing Stop adjustment
                if curr_p > pos.get("peak_price", pos["avg_price"]):
                    pos["peak_price"] = curr_p
                    if pos.get("trailing_stop"):
                        new_sl = round(curr_p * (1.0 - self.trailing_stop_pct), 2)
                        if new_sl > pos.get("stop_loss", 0):
                            pos["stop_loss"] = new_sl

                # Stop Loss
                sl = pos.get("stop_loss")
                if sl and curr_p <= sl:
                    res = self._sell(sym, pos["quantity"], curr_p, pos["strategy"], f"STOP_LOSS (${sl:,.2f})")
                    if res["status"] == "filled": closed_trades.append(res["trade"])
                    continue

                # Take Profit
                tp = pos.get("take_profit")
                if tp and curr_p >= tp:
                    res = self._sell(sym, pos["quantity"], curr_p, pos["strategy"], f"TAKE_PROFIT (${tp:,.2f})")
                    if res["status"] == "filled": closed_trades.append(res["trade"])
                    continue

        return closed_trades

    def update_equity_curve(self, prices: Dict[str, float]):
        eq = self.get_equity(prices)
        self.equity_curve.append(eq)
        peak = max(self.equity_curve) if self.equity_curve else self.initial_capital
        dd = (peak - eq) / peak if peak > 0 else 0.0
        self.drawdown_curve.append(dd)

    def get_metrics(self, prices: Dict[str, float]) -> Dict[str, Any]:
        eq = self.get_equity(prices)
        total_pnl = eq - self.initial_capital
        total_ret_pct = (total_pnl / self.initial_capital) * 100.0

        trades = self.trade_history
        sell_trades = [t for t in trades if t["action"] == "SELL" and "pnl" in t]
        wins = [t for t in sell_trades if t.get("pnl", 0) > 0]
        losses = [t for t in sell_trades if t.get("pnl", 0) <= 0]

        win_rate = (len(wins) / len(sell_trades) * 100.0) if sell_trades else 0.0
        tot_win = sum(t["pnl"] for t in wins)
        tot_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (tot_win / tot_loss) if tot_loss > 0 else (99.0 if tot_win > 0 else 1.0)

        if len(self.equity_curve) > 10:
            arr = np.array(list(self.equity_curve), dtype=float)
            returns = np.diff(arr) / (arr[:-1] + 1e-9)
            std = np.std(returns)
            # Session information ratio (not fake-annualized from sub-second ticks)
            sharpe = (np.mean(returns) / (std + 1e-9)) * np.sqrt(min(len(returns), 252)) if std > 1e-7 else 0.0
        else:
            sharpe = 0.0

        max_dd = max(self.drawdown_curve) * 100.0 if self.drawdown_curve else 0.0

        # Additional advanced metrics
        if sell_trades:
            avg_win = tot_win / len(wins) if wins else 0.0
            avg_loss = tot_loss / len(losses) if losses else 0.0
            avg_r_multiple = (avg_win / avg_loss) if avg_loss > 0 else 0.0
        else:
            avg_win = 0.0
            avg_loss = 0.0
            avg_r_multiple = 0.0

        return {
            "equity": eq,
            "cash": self.cash,
            "total_pnl": total_pnl,
            "total_return_pct": total_ret_pct,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sharpe": sharpe,
            "max_drawdown_pct": max_dd,
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "open_positions": len(self.positions),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "avg_r_multiple": avg_r_multiple,
        }


# =====================================================================
# MODERN TRADING INTERFACE (CUSTOMTKINTER DESKTOP)
# =====================================================================
class ModernTradingInterface:
    """Paper trading workstation with explicit evidence and source status."""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("LOKI PRO - Professional Trading Terminal")
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        dpi_scale = self.root._get_window_scaling()
        display_scale = max(0.75, min(dpi_scale, (screen_width - 60) / 1180,
                                     (screen_height - 80) / 740))
        # Respect high DPI where it fits; keep the complete terminal within a small screen.
        ctk.set_widget_scaling(display_scale / dpi_scale)
        ctk.set_window_scaling(display_scale / dpi_scale)
        width = min(1600, int((screen_width - 60) / display_scale))
        height = min(960, int((screen_height - 80) / display_scale))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(1180, 740)
        self.root.configure(fg_color=COLORS["bg_dark"])
        
        # Set customtkinter theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Set Window Icon
        icon_path = Path(__file__).parent / "loki.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # Auto-save state path
        self.state_path = Path(__file__).parent / "state" / "loki_session.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        # Core Engines
        self.market_sim = AdvancedMarketSimulator()
        self.account = ProfessionalAccount(initial_capital=25000.0)
        self.risk_manager = AdvancedRiskManager()
        self.learner = SelfImprovementEngine()
        self.guard = TradingGuard()
        self.copilot = LokiCopilot()

        self.strategies = {
            "ml_ensemble": MLEnsembleStrategy(),
            "josh": JoshStrategy(),
            "momentum": MomentumStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "breakout": BreakoutStrategy(),
            "volatility_surface": VolatilitySurfaceStrategy(),
        }

        # Operational States
        self.is_running = False
        self.multi_asset_scan_enabled = True
        self.audio_alerts_enabled = True
        self.selected_symbol = "BTC/USD"
        self.selected_strategy_var = tk.StringVar(value="josh")  # Josh's Strategy is default
        self.active_strategy = "josh"
        self.active_timeframe = "5m"
        self.current_prices: Dict[str, float] = self.market_sim.prices.copy()
        
        # Data Mode: simulated or real
        self.data_mode = "simulated"  # "simulated" or "real"
        self.data_mode_var = tk.StringVar(value="SIM")
        self.ccxt_exchange = None
        self.real_market_data = RealMarketData()
        
        # Trading Mode: paper or live
        self.trading_mode = "paper"  # "paper" or "live"
        self.trading_mode_var = tk.StringVar(value="PAPER")
        self.alpaca_client = None
        self._real_bars: Dict[str, List[Dict[str, Any]]] = {}
        self._real_bar_keys: Dict[str, str] = {}
        self._bars_updated_at: Dict[str, float] = {}
        self._quote_updated_at: Dict[str, float] = {}
        self._last_real_poll = 0.0
        self.latest_signal: Optional[Dict[str, Any]] = None
        self.latest_backtest: Optional[Dict[str, Any]] = None
        self._research_busy = False
        self._data_generation = 0
        self._data_lock = threading.RLock()

        # UI & Throttling
        self._last_chart_draw_time = 0.0
        self.watchlist_widgets: Dict[str, Dict[str, Any]] = {}
        self.trade_markers: List[Dict[str, Any]] = []
        self._log_lock = threading.Lock()
        self._pending_logs: List[str] = []
        self._last_pos_sig = ""
        self._last_order_count = -1
        self._auto_save_timer = 0

        # Crash-proofing: stop signal for the feed loop + route Tk callback
        # exceptions into the in-app log instead of silent stderr spam.
        self._shutdown = threading.Event()
        self.root.report_callback_exception = self._on_tk_exception

        # Build Full Interface
        self._create_layout()

        # Load saved state
        self._load_session_state()

        # Start Continuous Market Feed & Autonomous Scanner
        self._start_continuous_feed()

        # Start Auto-Save Scheduler
        self._schedule_auto_save()

        self._log("Loki paper terminal online. Simulated prices only — not connected to a live broker.", "SYSTEM")
        self.root.after(80, self._flush_logs)

        # Register window close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Control-f>", lambda event: self.search_entry.focus_set())
        self.root.bind("<Control-l>", lambda event: self._focus_copilot())
        self.root.bind("<Escape>", lambda event: self._pause_pilot())

    # -----------------------------------------------------------------
    # SOUND EFFECTS (NATIVE WINDOWS AUDIO)
    # -----------------------------------------------------------------
    def _play_chime(self, sound_type: str = "buy"):
        if not self.audio_alerts_enabled or not WINSOUND_AVAILABLE:
            return
        def _beep():
            try:
                if sound_type == "buy":
                    winsound.Beep(880, 100)
                    winsound.Beep(1175, 150)
                elif sound_type == "sell":
                    winsound.Beep(1175, 100)
                    winsound.Beep(880, 150)
                elif sound_type == "tp":
                    winsound.Beep(1046, 80)
                    winsound.Beep(1318, 100)
                    winsound.Beep(1568, 160)
                elif sound_type == "sl":
                    winsound.Beep(440, 150)
                    winsound.Beep(330, 220)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()

    # -----------------------------------------------------------------
    # LAYOUT CONFIGURATION
    # -----------------------------------------------------------------
    def _create_layout(self):
        self.root.grid_columnconfigure(0, weight=0, minsize=245)  # Watchlist
        self.root.grid_columnconfigure(1, weight=1)              # Chart Center
        self.root.grid_columnconfigure(2, weight=0, minsize=315)  # AI & Trading Deck
        self.root.grid_rowconfigure(1, weight=1)                 # Main row
        self.root.grid_rowconfigure(2, weight=0, minsize=270)    # Operations Deck

        self._build_header()
        self._build_watchlist_panel()
        self._build_center_chart_panel()
        self._build_ai_trading_deck()
        self._build_bottom_operations_deck()

    # -----------------------------------------------------------------
    # HEADER BAR
    # -----------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COLORS["card_bg"])
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="LOKI / PAPER TERMINAL", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=COLORS["accent_cyan"]).grid(row=0, column=0, sticky="w", padx=18, pady=(10, 3))
        pills = ctk.CTkFrame(header, fg_color="transparent")
        pills.grid(row=0, column=1, sticky="w", padx=10, pady=(10, 3))
        self.data_source_pill = ctk.CTkLabel(pills, text="SIMULATED DATA", corner_radius=6,
            fg_color="#332408", text_color=COLORS["warning"], padx=10, pady=4,
            font=ctk.CTkFont(size=12, weight="bold"))
        self.data_source_pill.pack(side="left", padx=4)
        self.trading_mode_pill = ctk.CTkLabel(pills, text="PAPER ONLY", corner_radius=6,
            fg_color="#064E3B", text_color=COLORS["success"], padx=10, pady=4,
            font=ctk.CTkFont(size=12, weight="bold"))
        self.trading_mode_pill.pack(side="left", padx=4)
        self.status_badge = ctk.CTkLabel(pills, text="STANDBY", corner_radius=6,
            text_color=COLORS["warning"], padx=10, font=ctk.CTkFont(size=12, weight="bold"))
        self.status_badge.pack(side="left", padx=4)
        ctk.CTkButton(header, text="HALT + CLOSE PAPER", command=self._emergency_halt,
            fg_color=COLORS["danger_dim"], hover_color=COLORS["danger"], width=165,
            height=32).grid(row=0, column=2, padx=18, pady=(10, 3))

        stats = ctk.CTkFrame(header, fg_color=COLORS["card_alt"], corner_radius=8)
        stats.grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=5)
        stats.grid_columnconfigure(2, weight=1)
        self.hdr_equity_lbl = ctk.CTkLabel(stats, text="Paper equity: $25,000.00",
            font=ctk.CTkFont(size=15, weight="bold"))
        self.hdr_equity_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=4)
        self.hdr_pnl_lbl = ctk.CTkLabel(stats, text="Paper P&L: $0.00",
            font=ctk.CTkFont(size=14), text_color=COLORS["text_primary"])
        self.hdr_pnl_lbl.grid(row=0, column=1, sticky="w", padx=16, pady=4)
        self.hdr_winrate_lbl = ctk.CTkLabel(stats, text="Win rate: awaiting closed paper trades",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"])
        self.hdr_winrate_lbl.grid(row=0, column=2, sticky="e", padx=12, pady=4)

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(1, 8))
        ctk.CTkLabel(controls, text="Data", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.data_mode_seg = ctk.CTkSegmentedButton(controls, values=["SIM", "REAL"],
            variable=self.data_mode_var, command=self._on_data_mode_change, height=32,
            selected_color=COLORS["accent_blue"])
        self.data_mode_seg.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(controls, text="Strategy", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.strategy_selector = ctk.CTkComboBox(controls, values=list(self.strategies),
            variable=self.selected_strategy_var, command=self._on_strategy_change, width=150,
            height=32, state="readonly")
        self.strategy_selector.pack(side="left", padx=(0, 16))
        self.start_btn = ctk.CTkButton(controls, text="START PAPER PILOT", command=self._toggle_bot,
            fg_color="#087F5B", hover_color="#059669", width=155, height=32)
        self.start_btn.pack(side="left", padx=(0, 10))
        ctk.CTkButton(controls, text="Talk to Loki", command=self._focus_copilot,
            fg_color=COLORS["accent_blue"], width=110, height=32).pack(side="left", padx=4)
        ctk.CTkLabel(controls, text="Esc: pause  |  Ctrl+F: find  |  Ctrl+L: chat",
            font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]).pack(side="right", padx=4)

    # -----------------------------------------------------------------
    # LEFT PANEL: WATCHLIST
    # -----------------------------------------------------------------
    def _build_watchlist_panel(self):
        panel = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COLORS["card_bg"])
        panel.grid(row=1, column=0, sticky="nsew", padx=(6, 3), pady=(6, 3))
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(panel, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        ctk.CTkLabel(title_box, text="MARKET WATCHLIST", font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["accent_cyan"]).pack(side="left")

        self.cat_seg = ctk.CTkSegmentedButton(
            panel,
            values=["ALL", "CRYPTO", "STOCKS", "INDICES"],
            command=self._filter_watchlist,
            selected_color=COLORS["accent_blue"],
            unselected_color=COLORS["card_alt"],
            height=32,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.cat_seg.set("ALL")
        self.cat_seg.grid(row=1, column=0, sticky="ew", padx=14, pady=6)

        self.search_entry = ctk.CTkEntry(panel, placeholder_text="Search ticker...", height=36, placeholder_text_color=COLORS["text_muted"])
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=14, pady=8)
        self.search_entry.bind("<KeyRelease>", lambda e: self._filter_watchlist())

        self.watch_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.watch_scroll.grid(row=3, column=0, sticky="nsew", padx=8, pady=6)

        for sym, d in self.market_sim.all_symbols.items():
            self._create_watchlist_card(sym, d)

    def _create_watchlist_card(self, symbol: str, data: Dict[str, Any]):
        card = ctk.CTkFrame(self.watch_scroll, height=60, fg_color=COLORS["card_alt"], corner_radius=10)
        card.pack(fill="x", padx=6, pady=4)
        card.pack_propagate(False)

        card.bind("<Button-1>", lambda e, s=symbol: self._select_symbol(s))

        lbl_sym = ctk.CTkLabel(card, text=symbol, font=ctk.CTkFont(size=14, weight="bold"), anchor="w", text_color=COLORS["text_primary"])
        lbl_sym.pack(side="left", padx=14, pady=10)
        lbl_sym.bind("<Button-1>", lambda e, s=symbol: self._select_symbol(s))

        r_frame = ctk.CTkFrame(card, fg_color="transparent")
        r_frame.pack(side="right", padx=12, pady=6)
        r_frame.bind("<Button-1>", lambda e, s=symbol: self._select_symbol(s))

        price_lbl = ctk.CTkLabel(r_frame, text=f"${data['base']:,.2f}", font=ctk.CTkFont(size=13, weight="bold"), anchor="e", text_color=COLORS["text_primary"])
        price_lbl.pack(anchor="e")
        price_lbl.bind("<Button-1>", lambda e, s=symbol: self._select_symbol(s))

        change_lbl = ctk.CTkLabel(r_frame, text="+0.00%", font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"], anchor="e")
        change_lbl.pack(anchor="e")
        change_lbl.bind("<Button-1>", lambda e, s=symbol: self._select_symbol(s))

        self.watchlist_widgets[symbol] = {
            "card": card,
            "price_lbl": price_lbl,
            "change_lbl": change_lbl,
            "category": data["category"],
        }

    # -----------------------------------------------------------------
    # CENTER PANEL: PRO DUAL-AXIS CHART (PRICE + RSI)
    # -----------------------------------------------------------------
    def _build_center_chart_panel(self):
        panel = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COLORS["card_bg"])
        panel.grid(row=1, column=1, sticky="nsew", padx=3, pady=(6, 3))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # Chart Control Top Bar
        top_bar = ctk.CTkFrame(panel, height=44, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=15, pady=(8, 0))

        self.chart_title = ctk.CTkLabel(
            top_bar,
            text=f"{self.selected_symbol}  $67,450.00",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.chart_title.pack(anchor="w")

        chart_controls = ctk.CTkFrame(top_bar, fg_color="transparent")
        chart_controls.pack(fill="x", pady=(3, 0))

        # Timeframe pills
        self.tf_var = tk.StringVar(value="5m")
        tf_box = ctk.CTkSegmentedButton(
            chart_controls,
            values=["1m", "5m", "15m", "1h"],
            variable=self.tf_var,
            selected_color=COLORS["accent_cyan"],
            height=26,
            command=self._on_timeframe_change
        )
        tf_box.pack(side="left", padx=(0, 8))

        # Overlays
        self.show_ema_var = tk.BooleanVar(value=True)
        self.show_bb_var = tk.BooleanVar(value=True)
        self.show_rsi_var = tk.BooleanVar(value=True)

        ctk.CTkCheckBox(chart_controls, text="RSI", variable=self.show_rsi_var, font=ctk.CTkFont(size=11), width=50, command=self._force_chart_redraw).pack(side="left", padx=5)
        ctk.CTkCheckBox(chart_controls, text="Bands", variable=self.show_bb_var, font=ctk.CTkFont(size=11), width=65, command=self._force_chart_redraw).pack(side="left", padx=5)
        ctk.CTkCheckBox(chart_controls, text="EMA", variable=self.show_ema_var, font=ctk.CTkFont(size=11), width=55, command=self._force_chart_redraw).pack(side="left", padx=5)

        # Chart Frame
        chart_container = ctk.CTkFrame(panel, fg_color="#0D121F", corner_radius=6)
        chart_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        chart_container.grid_rowconfigure(0, weight=1)
        chart_container.grid_columnconfigure(0, weight=1)

        # Figure with 3 subplots: Price, RSI, Volume
        self.fig = Figure(figsize=(8, 5.0), dpi=100, facecolor="#0D121F")
        self.fig.subplots_adjust(left=0.14, right=0.97, top=0.95, bottom=0.10, hspace=0.12)
        gs = self.fig.add_gridspec(3, 1, height_ratios=[3.0, 1.2, 0.8])
        self.ax_price = self.fig.add_subplot(gs[0])
        self.ax_rsi = self.fig.add_subplot(gs[1], sharex=self.ax_price)
        self.ax_vol = self.fig.add_subplot(gs[2], sharex=self.ax_price)

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_container)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    # -----------------------------------------------------------------
    # RIGHT PANEL: AI NEURAL RADAR & DIRECT TRADING DECK
    # -----------------------------------------------------------------
    def _build_ai_trading_deck(self):
        panel = ctk.CTkScrollableFrame(self.root, corner_radius=0, fg_color=COLORS["card_bg"])
        panel.grid(row=1, column=2, sticky="nsew", padx=(3, 6), pady=(6, 3))

        # 0. Autonomous AI Pilot
        pilot_card = ctk.CTkFrame(panel, fg_color=COLORS["card_alt"], corner_radius=10)
        pilot_card.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(
            pilot_card, text="AI PILOT",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["accent_purple"]
        ).pack(anchor="w", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            pilot_card,
            text="Scans every symbol and places paper trades when conviction is high. Learning from closed P&L.",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"],
            wraplength=245,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 8))

        self.ai_pilot_btn = ctk.CTkButton(
            pilot_card,
            text="START PAPER PILOT",
            command=self._toggle_bot,
            fg_color=COLORS["success"],
            hover_color="#059669",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44
        )
        self.ai_pilot_btn.pack(fill="x", padx=14, pady=(0, 8))

        # Train AI Button
        self.ai_train_btn = ctk.CTkButton(
            pilot_card,
            text="COMPARE STRATEGIES",
            command=self._train_ai,
            fg_color=COLORS["accent_purple"],
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36
        )
        self.ai_train_btn.pack(fill="x", padx=14, pady=(0, 4))

        self.ai_pilot_status = ctk.CTkLabel(
            pilot_card,
            text="Idle — press the button to start autonomous paper trading.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["warning"],
            wraplength=245,
            justify="left"
        )
        self.ai_pilot_status.pack(anchor="w", padx=14, pady=(0, 4))

        self.ai_learn_lbl = ctk.CTkLabel(
            pilot_card,
            text=self.learner.summary_line(),
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"],
            wraplength=245,
            justify="left"
        )
        self.ai_learn_lbl.pack(anchor="w", padx=14, pady=(0, 4))

        # AI Performance Score Card
        perf_card = ctk.CTkFrame(pilot_card, fg_color=COLORS["card_bg"], corner_radius=10)
        perf_card.pack(fill="x", padx=14, pady=(6, 6))

        self.ai_perf_score_lbl = ctk.CTkLabel(
            perf_card,
            text="Paper learning score: awaiting outcomes",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent_cyan"]
        )
        self.ai_perf_score_lbl.pack(anchor="w", padx=10, pady=(8, 2))

        self.ai_perf_bar = ctk.CTkProgressBar(perf_card, height=10, progress_color=COLORS["accent_blue"])
        self.ai_perf_bar.pack(fill="x", padx=10, pady=(0, 8))

        # Signal Strength Meter
        signal_card = ctk.CTkFrame(pilot_card, fg_color=COLORS["card_bg"], corner_radius=10)
        signal_card.pack(fill="x", padx=14, pady=(6, 6))

        ctk.CTkLabel(
            signal_card,
            text="Signal Strength",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self.signal_strength_bar = ctk.CTkProgressBar(signal_card, height=12, progress_color=COLORS["success"])
        self.signal_strength_bar.pack(fill="x", padx=10, pady=(0, 2))
        self.signal_strength_bar.set(0.0)

        self.signal_strength_lbl = ctk.CTkLabel(
            signal_card,
            text="Awaiting a signal; scores are not win probabilities",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"]
        )
        self.signal_strength_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        self.ai_perf_bar.set(0.0)

        self.ai_note_lbl = ctk.CTkLabel(
            pilot_card,
            text=self.learner.last_note,
            font=ctk.CTkFont(size=10),
            text_color=COLORS["accent_cyan"],
            wraplength=245,
            justify="left"
        )
        self.ai_note_lbl.pack(anchor="w", padx=14, pady=(0, 12))

        # 1. AI Signal Radar Card
        radar_card = ctk.CTkFrame(panel, fg_color=COLORS["card_alt"], corner_radius=10)
        radar_card.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(radar_card, text="🧠 AI CONFLUENCE RADAR", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["accent_cyan"]).pack(anchor="w", padx=14, pady=(12, 6))

        self.ai_action_lbl = ctk.CTkLabel(
            radar_card,
            text="NEUTRAL / SCANNING",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#263148",
            text_color=COLORS["text_secondary"],
            corner_radius=8,
            padx=16, pady=8
        )
        self.ai_action_lbl.pack(fill="x", padx=14, pady=4)

        cf_row = ctk.CTkFrame(radar_card, fg_color="transparent")
        cf_row.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(cf_row, text="AI Conviction Score:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.ai_conf_num = ctk.CTkLabel(cf_row, text="—", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["accent_cyan"])
        self.ai_conf_num.pack(side="right")

        self.ai_conf_bar = ctk.CTkProgressBar(radar_card, height=10, progress_color=COLORS["accent_blue"])
        self.ai_conf_bar.pack(fill="x", padx=14, pady=(2, 6))
        self.ai_conf_bar.set(0.0)

        # Factor breakdown
        self.factors_box = ctk.CTkFrame(radar_card, fg_color="#141B2D", corner_radius=6)
        self.factors_box.pack(fill="x", padx=14, pady=(4, 8))
        self.factor_labels = {}
        for factor_name in ["Josh Strategy", "Trend Momentum", "Bollinger Z-Score", "Channel Breakout"]:
            f_row = ctk.CTkFrame(self.factors_box, fg_color="transparent")
            f_row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(f_row, text=factor_name, font=ctk.CTkFont(size=10)).pack(side="left")
            fl = ctk.CTkLabel(f_row, text="NEUTRAL", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_secondary"])
            fl.pack(side="right")
            self.factor_labels[factor_name] = fl

        self.ai_reason_txt = ctk.CTkLabel(
            radar_card,
            text="Autonomous multi-factor scanner active.",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"],
            justify="left",
            wraplength=245
        )
        self.ai_reason_txt.pack(fill="x", padx=14, pady=(2, 12))

        # 2. Direct Execution Deck
        order_card = ctk.CTkFrame(panel, fg_color=COLORS["card_alt"], corner_radius=10)
        order_card.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(order_card, text="⚡ DIRECT EXECUTION DECK", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["accent_blue"]).pack(anchor="w", padx=14, pady=(12, 6))

        ctk.CTkLabel(order_card, text="Quantity / Units:", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=14, pady=(4, 2))
        self.qty_entry = ctk.CTkEntry(order_card, height=32, font=ctk.CTkFont(size=12))
        self.qty_entry.insert(0, "0.10")
        self.qty_entry.pack(fill="x", padx=14, pady=2)
        self.qty_entry.bind("<KeyRelease>", lambda e: self._update_risk_reward_preview())

        risk_row = ctk.CTkFrame(order_card, fg_color="transparent")
        risk_row.pack(fill="x", padx=14, pady=6)
        ctk.CTkButton(risk_row, text="0.5% risk", width=72, height=28, fg_color="#1E293B", command=lambda: self._calc_risk_qty(0.005)).pack(side="left", padx=2)
        ctk.CTkButton(risk_row, text="1% risk", width=68, height=28, fg_color="#1E293B", command=lambda: self._calc_risk_qty(0.01)).pack(side="left", padx=2)
        ctk.CTkButton(risk_row, text="2% risk", width=68, height=28, fg_color="#1E293B", command=lambda: self._calc_risk_qty(0.02)).pack(side="left", padx=2)

        sl_tp_row = ctk.CTkFrame(order_card, fg_color="transparent")
        sl_tp_row.pack(fill="x", padx=14, pady=4)

        sl_box = ctk.CTkFrame(sl_tp_row, fg_color="transparent")
        sl_box.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(sl_box, text="Stop Loss ($):", font=ctk.CTkFont(size=10)).pack(anchor="w")
        self.sl_entry = ctk.CTkEntry(sl_box, height=30, placeholder_text="Optional")
        self.sl_entry.pack(fill="x")
        self.sl_entry.bind("<KeyRelease>", lambda e: self._update_risk_reward_preview())

        tp_box = ctk.CTkFrame(sl_tp_row, fg_color="transparent")
        tp_box.pack(side="right", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(tp_box, text="Take Profit ($):", font=ctk.CTkFont(size=10)).pack(anchor="w")
        self.tp_entry = ctk.CTkEntry(tp_box, height=30, placeholder_text="Optional")
        self.tp_entry.pack(fill="x")
        self.tp_entry.bind("<KeyRelease>", lambda e: self._update_risk_reward_preview())

        # Live Risk / Reward Visualizer Box
        self.rr_preview_box = ctk.CTkFrame(order_card, fg_color="#121826", corner_radius=6)
        self.rr_preview_box.pack(fill="x", padx=14, pady=6)
        self.rr_preview_lbl = ctk.CTkLabel(
            self.rr_preview_box,
            text="Risk: $0.00  |  Reward: $0.00  |  R:R: 1:2.0",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["accent_cyan"], wraplength=280
        )
        self.rr_preview_lbl.pack(padx=8, pady=6)

        btn_row = ctk.CTkFrame(order_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(8, 14))

        self.btn_buy = ctk.CTkButton(
            btn_row, text="📈 BUY / LONG", command=lambda: self._manual_execute("BUY"),
            fg_color=COLORS["success"], hover_color=COLORS["success_dim"],
            font=ctk.CTkFont(size=13, weight="bold"), height=38
        )
        self.btn_buy.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_sell = ctk.CTkButton(
            btn_row, text="📉 SELL / EXIT", command=lambda: self._manual_execute("SELL"),
            fg_color=COLORS["danger"], hover_color=COLORS["danger_dim"],
            font=ctk.CTkFont(size=13, weight="bold"), height=38
        )
        self.btn_sell.pack(side="right", fill="x", expand=True, padx=(5, 0))

    # -----------------------------------------------------------------
    # BOTTOM OPERATIONS DECK (TABBED)
    # -----------------------------------------------------------------
    def _build_bottom_operations_deck(self):
        deck = ctk.CTkFrame(self.root, height=270, corner_radius=0, fg_color=COLORS["card_bg"])
        deck.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=6, pady=(3, 6))
        deck.grid_propagate(False)

        tabview = ctk.CTkTabview(deck, fg_color="transparent")
        self.operations_tabs = tabview
        tabview.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        tab_pos = tabview.add("Active Positions")
        tab_scanner = tabview.add("Scanner")
        tab_backtest = tabview.add("Backtest")
        tab_chat = tabview.add("Talk to Loki")
        tab_orders = tabview.add("Orders")
        tab_analytics = tabview.add("Analytics")
        tab_settings = tabview.add("Risk Settings")
        tab_logs = tabview.add("Audit Log")

        self._build_positions_tab(tab_pos)
        self._build_scanner_tab(tab_scanner)
        self._build_backtest_tab(tab_backtest)
        self._build_copilot_tab(tab_chat)
        self._build_orders_tab(tab_orders)
        self._build_analytics_tab(tab_analytics)
        self._build_settings_tab(tab_settings)
        self._build_logs_tab(tab_logs)

    def _build_positions_tab(self, parent):
        bar = ctk.CTkFrame(parent, height=36, fg_color="transparent")
        bar.pack(fill="x", padx=6, pady=(2, 6))

        ctk.CTkButton(
            bar, text="✕ Close Selected Position", command=self._close_selected_position,
            fg_color=COLORS["danger_dim"], hover_color=COLORS["danger"], height=28
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="Automated Trailing Stop & Take Profit watchdogs are actively guarding open trades.", font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]).pack(side="right", padx=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Loki.Treeview", background="#111624", foreground="#F8FAFC", fieldbackground="#111624", font=("Consolas", 10), rowheight=26)
        style.configure("Loki.Treeview.Heading", background="#1D263B", foreground="#00D2FF", font=("Segoe UI", 10, "bold"))
        style.map("Loki.Treeview", background=[("selected", "#2D3748")])

        cols = ("Symbol", "Side", "Qty", "Avg Price", "Mark Price", "Stop Loss", "Take Profit", "Unrealized P&L", "Return %", "Strategy")
        self.pos_tree = ttk.Treeview(parent, columns=cols, show="headings", style="Loki.Treeview", selectmode="browse")

        for c in cols:
            self.pos_tree.heading(c, text=c)
            width = 110 if "Price" in c or "P&L" in c else 90
            self.pos_tree.column(c, width=width, anchor="center")

        pos_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.pos_tree.yview)
        self.pos_tree.configure(yscrollcommand=pos_scroll.set)

        self.pos_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        pos_scroll.pack(side="right", fill="y", padx=(0, 6), pady=4)

        self.pos_tree.tag_configure("green", foreground=COLORS["success"])
        self.pos_tree.tag_configure("red", foreground=COLORS["danger"])

    def _build_scanner_tab(self, parent):
        """Real-time Multi-Asset Scanner Leaderboard."""
        cols = ("Symbol", "Category", "Source Price", "Window Chg", "Market Regime", "Signal Score", "Signal", "Readiness")
        self.scanner_tree = ttk.Treeview(parent, columns=cols, show="headings", style="Loki.Treeview", selectmode="browse")

        for c in cols:
            self.scanner_tree.heading(c, text=c)
            self.scanner_tree.column(c, width=105, anchor="center")

        scan_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.scanner_tree.yview)
        self.scanner_tree.configure(yscrollcommand=scan_scroll.set)

        self.scanner_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        scan_scroll.pack(side="right", fill="y", padx=(0, 6), pady=4)

        self.scanner_tree.tag_configure("green", foreground=COLORS["success"])
        self.scanner_tree.tag_configure("red", foreground=COLORS["danger"])

    def _build_backtest_tab(self, parent):
        """Interactive Quant Backtester Tab."""
        top_ctrls = ctk.CTkFrame(parent, height=44, fg_color="transparent")
        top_ctrls.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(top_ctrls, text="Asset:", font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        self.bt_asset_combo = ctk.CTkComboBox(top_ctrls, values=list(self.market_sim.all_symbols.keys()), width=120, state="readonly")
        self.bt_asset_combo.set(self.selected_symbol)
        self.bt_asset_combo.pack(side="left", padx=4)

        ctk.CTkLabel(top_ctrls, text="Strategy:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 4))
        self.bt_strat_combo = ctk.CTkComboBox(top_ctrls, values=list(self.strategies.keys()), width=150, state="readonly")
        self.bt_strat_combo.set("ml_ensemble")
        self.bt_strat_combo.pack(side="left", padx=4)

        ctk.CTkButton(
            top_ctrls, text="Explore selected strategy", command=self._run_quant_backtest,
            fg_color=COLORS["accent_blue"], hover_color="#2563EB", font=ctk.CTkFont(size=12, weight="bold"), width=180
        ).pack(side="left", padx=15)
        self.oos_btn = ctk.CTkButton(top_ctrls, text="OOS trend validation", command=self._run_oos_validation,
            fg_color="#6843A8", hover_color="#7C3AED", width=165)
        self.oos_btn.pack(side="left", padx=4)

        self.bt_result_lbl = ctk.CTkLabel(
            parent, text="Explore the selected strategy, or validate the separate trend model with walk-forward holdouts and cost stress. Synthetic data cannot establish market profitability.",
            font=ctk.CTkFont(size=11), text_color=COLORS["accent_cyan"], wraplength=1080, justify="left"
        )
        self.bt_result_lbl.pack(anchor="w", padx=12, pady=3)

        # Backtest Plot Canvas
        bt_canvas_box = ctk.CTkFrame(parent, fg_color="#0D121F")
        bt_canvas_box.pack(fill="both", expand=True, padx=10, pady=(2, 6))

        self.bt_fig = Figure(figsize=(7, 2.5), dpi=100, facecolor="#0D121F")
        self.bt_fig.subplots_adjust(left=0.08, right=0.96, top=0.90, bottom=0.20)
        self.bt_ax = self.bt_fig.add_subplot(111)
        self.bt_ax.set_facecolor("#0D121F")
        self.bt_ax.tick_params(colors="#94A3B8", labelsize=8)

        self.bt_canvas = FigureCanvasTkAgg(self.bt_fig, master=bt_canvas_box)
        self.bt_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_orders_tab(self, parent):
        bar = ctk.CTkFrame(parent, height=36, fg_color="transparent")
        bar.pack(fill="x", padx=6, pady=(2, 6))

        ctk.CTkButton(
            bar, text="📥 Export Trades to CSV", command=self._export_trades,
            fg_color=COLORS["accent_blue"], hover_color="#2563EB", height=28, width=180
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="Export all trade history to CSV file for analysis.", font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]).pack(side="right", padx=10)

        cols = ("Time", "Symbol", "Side", "Quantity", "Price", "Realized P&L", "Fee", "Status", "Reason")
        self.orders_tree = ttk.Treeview(parent, columns=cols, show="headings", style="Loki.Treeview", selectmode="browse")

        for c in cols:
            self.orders_tree.heading(c, text=c)
            self.orders_tree.column(c, width=100, anchor="center")

        ord_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=ord_scroll.set)

        self.orders_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        ord_scroll.pack(side="right", fill="y", padx=(0, 6), pady=4)

        self.orders_tree.tag_configure("green", foreground=COLORS["success"])
        self.orders_tree.tag_configure("red", foreground=COLORS["danger"])

    def _build_analytics_tab(self, parent):
        grid = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=10)

        for col in range(4):
            grid.grid_columnconfigure(col, weight=1)

        # Real-Time Profit Calculator (Top Row)
        profit_card = ctk.CTkFrame(grid, fg_color=COLORS["card_alt"], corner_radius=10)
        profit_card.grid(row=0, column=0, columnspan=4, padx=8, pady=8, sticky="nsew")
        
        ctk.CTkLabel(
            profit_card,
            text="PAPER ACCOUNT / OBSERVED OUTCOMES",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent_cyan"]
        ).pack(anchor="w", padx=14, pady=(10, 4))
        
        self.real_time_profit_lbl = ctk.CTkLabel(
            profit_card,
            text="Unrealized P&L: $0.00 (0 positions)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.real_time_profit_lbl.pack(anchor="w", padx=14, pady=(2, 10))

        self.analytics_labels = {}
        metrics_def = [
            ("Total Equity", "equity", "$25,000.00"),
            ("Available Cash", "cash", "$25,000.00"),
            ("Net Profit / Loss", "pnl", "$0.00"),
            ("Return On Capital", "return_pct", "0.00%"),
            ("Session Sharpe", "sharpe", "0.00"),
            ("Max Portfolio Drawdown", "drawdown", "0.00%"),
            ("Observed Win Rate", "win_rate", "Awaiting closed trades"),
            ("Profit Factor", "profit_factor", "—"),
            ("Avg Win", "avg_win", "$0.00"),
            ("Avg Loss", "avg_loss", "$0.00"),
            ("Avg win / avg loss", "avg_r_multiple", "—"),
        ]

        for i, (title, key, default) in enumerate(metrics_def):
            row = (i // 4) + 1  # Start from row 1 (row 0 is profit calculator)
            col = i % 4
            card = ctk.CTkFrame(grid, fg_color=COLORS["card_alt"], corner_radius=8)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]).pack(anchor="w", padx=12, pady=(10, 2))
            val_lbl = ctk.CTkLabel(card, text=default, font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_primary"])
            val_lbl.pack(anchor="w", padx=12, pady=(2, 10))
            self.analytics_labels[key] = val_lbl

        # Configure extra rows for 11 metrics + profit calculator (4 rows)
        for row in range(4):
            grid.grid_rowconfigure(row, weight=1)

    def _build_settings_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=15, pady=8)

        card_risk = ctk.CTkFrame(scroll, fg_color=COLORS["card_alt"], corner_radius=8)
        card_risk.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(card_risk, text="Autonomous Bot & Risk Controls", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLORS["accent_cyan"]).pack(anchor="w", padx=14, pady=8)

        r_grid = ctk.CTkFrame(card_risk, fg_color="transparent")
        r_grid.pack(fill="x", padx=14, pady=6)

        ctk.CTkLabel(r_grid, text="Risk Per Trade (%):").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.cfg_risk_pct = ctk.CTkEntry(r_grid, width=90)
        self.cfg_risk_pct.insert(0, "2.0")
        self.cfg_risk_pct.grid(row=0, column=1, padx=6, pady=4)

        ctk.CTkLabel(r_grid, text="Default Stop Loss (%):").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        self.cfg_sl_pct = ctk.CTkEntry(r_grid, width=90)
        self.cfg_sl_pct.insert(0, "3.0")
        self.cfg_sl_pct.grid(row=0, column=3, padx=6, pady=4)

        ctk.CTkLabel(r_grid, text="Default Take Profit (%):").grid(row=1, column=0, padx=6, pady=4, sticky="w")
        self.cfg_tp_pct = ctk.CTkEntry(r_grid, width=90)
        self.cfg_tp_pct.insert(0, "6.0")
        self.cfg_tp_pct.grid(row=1, column=1, padx=6, pady=4)

        ctk.CTkLabel(r_grid, text="Trailing Stop (%):").grid(row=1, column=2, padx=6, pady=4, sticky="w")
        self.cfg_trail_pct = ctk.CTkEntry(r_grid, width=90)
        self.cfg_trail_pct.insert(0, "2.0")
        self.cfg_trail_pct.grid(row=1, column=3, padx=6, pady=4)

        self.cfg_audio_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r_grid, text="Audio Execution Chimes", variable=self.cfg_audio_var).grid(row=2, column=0, columnspan=2, padx=6, pady=8, sticky="w")

        self.cfg_multiscan_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r_grid, text="Scan all assets (not just the chart)", variable=self.cfg_multiscan_var).grid(row=2, column=2, columnspan=2, padx=6, pady=8, sticky="w")

        self.cfg_learn_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r_grid, text="Self-learn from closed trades", variable=self.cfg_learn_var).grid(row=3, column=0, columnspan=2, padx=6, pady=8, sticky="w")

        ctk.CTkLabel(r_grid, text="UTC daily loss halt (%):").grid(row=4, column=0, padx=6, pady=4, sticky="w")
        self.cfg_daily_loss = ctk.CTkEntry(r_grid, width=90)
        self.cfg_daily_loss.insert(0, "4.0")
        self.cfg_daily_loss.grid(row=4, column=1, padx=6, pady=4)

        ctk.CTkLabel(r_grid, text="Max drawdown halt (%):").grid(row=4, column=2, padx=6, pady=4, sticky="w")
        self.cfg_max_dd = ctk.CTkEntry(r_grid, width=90)
        self.cfg_max_dd.insert(0, "12.0")
        self.cfg_max_dd.grid(row=4, column=3, padx=6, pady=4)

        ctk.CTkLabel(r_grid, text="Min AI conviction (%):").grid(row=5, column=0, padx=6, pady=4, sticky="w")
        self.cfg_min_conf = ctk.CTkEntry(r_grid, width=90)
        self.cfg_min_conf.insert(0, "70")
        self.cfg_min_conf.grid(row=5, column=1, padx=6, pady=4)

        ctk.CTkLabel(
            card_risk,
            text="Paper execution only. REAL data covers BTC, ETH and SOL from Binance (USDT quote). Signal scores are indicator agreement, not probabilities of profit. Compare strategies on research data before assessing independent results.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["warning"],
            wraplength=720,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(4, 8))

        btn_save = ctk.CTkButton(card_risk, text="Apply Configuration", command=self._save_settings, width=160)
        btn_save.pack(anchor="w", padx=14, pady=10)

    def _build_logs_tab(self, parent):
        self.log_textbox = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#0D121F", text_color="#E2E8F0")
        self.log_textbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        btn_bar = ctk.CTkFrame(parent, fg_color="transparent")
        btn_bar.pack(side="right", fill="y", padx=6, pady=6)
        ctk.CTkButton(btn_bar, text="Clear", width=70, command=lambda: self.log_textbox.delete("1.0", "end")).pack(pady=4)

    def _build_copilot_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        prompts = ctk.CTkFrame(parent, fg_color="transparent")
        prompts.grid(row=0, column=0, sticky="ew", padx=8, pady=3)
        for label, prompt in (("Account overview", "How is my portfolio doing?"),
                              ("Explain signal", "Explain the current strategy and signal"),
                              ("Risk check", "Review my risk controls"),
                              ("70% goal", "Can you guarantee a 70% win rate?")):
            ctk.CTkButton(prompts, text=label, width=130, height=28,
                fg_color=COLORS["card_alt"], command=lambda p=prompt: self._ask_copilot(p)
            ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(prompts, text="Local assistant · reads this session · no trade execution",
            font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]
        ).pack(side="right", padx=4)
        self.copilot_transcript = ctk.CTkTextbox(parent, wrap="word", state="disabled",
            font=ctk.CTkFont(size=13), fg_color="#0D121F")
        self.copilot_transcript.grid(row=1, column=0, sticky="nsew", padx=8, pady=3)
        composer = ctk.CTkFrame(parent, fg_color="transparent")
        composer.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        composer.grid_columnconfigure(0, weight=1)
        self.copilot_entry = ctk.CTkEntry(composer, height=34,
            placeholder_text="Ask about positions, signals, evidence or risk…")
        self.copilot_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.copilot_entry.bind("<Return>", lambda event: self._ask_copilot())
        ctk.CTkButton(composer, text="Ask Loki", width=110, height=34,
            command=self._ask_copilot).grid(row=0, column=1)
        self._append_copilot("Loki", "Ask me about your paper account, risk, or selected strategy. "
            "I use the current session snapshot. I cannot place trades or guarantee returns.")

    def _append_copilot(self, speaker: str, text: str):
        self.copilot_transcript.configure(state="normal")
        self.copilot_transcript.insert("end", f"{speaker}: {text}\n\n")
        # Keep a long-running session responsive without storing an unbounded transcript.
        if int(self.copilot_transcript.index("end").split(".")[0]) > 1200:
            self.copilot_transcript.delete("1.0", "200.0")
        self.copilot_transcript.see("end")
        self.copilot_transcript.configure(state="disabled")

    def _focus_copilot(self):
        self.operations_tabs.set("Talk to Loki")
        self.copilot_entry.focus_set()

    def _ask_copilot(self, prompt: Optional[str] = None):
        message = (prompt if prompt is not None else self.copilot_entry.get()).strip()
        if not message:
            return
        self.copilot_entry.delete(0, "end")
        self._focus_copilot()
        self._append_copilot("You", message[:4000])
        with self.account._lock:
            positions = {symbol: dict(position) for symbol, position in self.account.positions.items()}
        context = {
            "metrics": self.account.get_metrics(self.current_prices),
            "positions": positions, "prices": self.current_prices.copy(),
            "symbol": self.selected_symbol, "strategy": self.active_strategy,
            "signal": self.latest_signal, "data_source": self.data_mode,
            "trading_mode": "paper", "is_running": self.is_running,
            "as_of": (datetime.fromtimestamp(self._quote_updated_at[self.selected_symbol]).isoformat()
                      if self.data_mode == "real" and self.selected_symbol in self._quote_updated_at
                      else datetime.now().isoformat() if self.data_mode == "simulated" else "No source timestamp"),
            "data_fresh": self._has_fresh_data(self.selected_symbol),
            "quote_age_seconds": (max(0, time.time() - self._quote_updated_at[self.selected_symbol])
                if self.data_mode == "real" and self.selected_symbol in self._quote_updated_at else None),
            "risk": {"halted": self.guard.halted, "halt_reason": self.guard.halt_reason,
                     "max_daily_loss_pct": self.guard.max_daily_loss_pct,
                     "max_drawdown_pct": self.guard.max_drawdown_pct},
            "validation": self.latest_backtest,
        }
        try:
            reply = self.copilot.respond(message[:4000], context)
            self._append_copilot("Loki", reply.text)
        except Exception:
            logger.exception("Copilot response failed")
            self._append_copilot("Loki", "I could not read the session snapshot. Try again in a moment.")

    def _pause_pilot(self):
        self.is_running = False
        self._sync_pilot_buttons()
        self._log("Paper pilot paused; protective exits remain active.", "BOT")

    def _get_active_bars(self, symbol: str, limit: int = 150):
        if self.data_mode == "simulated":
            return self.market_sim.get_ohlcv(symbol, limit)
        if self._real_bar_keys.get(symbol) != self.active_timeframe:
            return []
        return list(self._real_bars.get(symbol, []))[-limit:]

    def _can_enter(self, symbol: str) -> bool:
        if self.guard.halted or self.trading_mode != "paper":
            return False
        return self._has_fresh_data(symbol)

    def _has_fresh_data(self, symbol: str) -> bool:
        if self.data_mode == "simulated":
            return True
        now = time.time()
        interval = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[self.active_timeframe]
        with self._data_lock:
            price = self.current_prices.get(symbol)
            bars = self._real_bars.get(symbol, [])
            return (symbol in self.real_market_data.symbols
                    and price is not None and math.isfinite(price) and price > 0
                    and quote_is_fresh(self._quote_updated_at.get(symbol), now)
                    and quote_is_fresh(self._bars_updated_at.get(symbol), now, max_age=180)
                    and self._real_bar_keys.get(symbol) == self.active_timeframe
                    and bool(bars) and candle_is_current(bars[-1].get("timestamp"), now, interval))

    def _poll_real_market(self):
        """Worker-only I/O; publish only into the same locked source generation."""
        if time.time() - self._last_real_poll < 5:
            return
        self._last_real_poll = time.time()
        generation, timeframe = self._data_generation, self.active_timeframe
        interval = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[timeframe]
        for symbol in self.real_market_data.symbols:
            with self._data_lock:
                if self.data_mode != "real" or generation != self._data_generation:
                    return
            price = self.real_market_data.fetch_ticker(symbol)
            with self._data_lock:
                if self.data_mode != "real" or generation != self._data_generation:
                    return
                if price and math.isfinite(price) and price > 0:
                    self.current_prices = {**self.current_prices, symbol: price}
                    self._quote_updated_at[symbol] = time.time()
                need_bars = (self._real_bar_keys.get(symbol) != timeframe
                    or time.time() - self._bars_updated_at.get(symbol, 0) > 60)
            if need_bars:
                bars = self.real_market_data.fetch_ohlcv(symbol, timeframe, 250)
                with self._data_lock:
                    if (self.data_mode != "real" or generation != self._data_generation
                            or timeframe != self.active_timeframe):
                        return
                    if bars and candle_is_current(bars[-1].get("timestamp"), time.time(), interval):
                        self._real_bars[symbol] = bars
                        self._real_bar_keys[symbol] = timeframe
                        self._bars_updated_at[symbol] = time.time()

    # -----------------------------------------------------------------
    # CONTINUOUS FEED & AUTONOMOUS MULTI-ASSET SCANNER
    # -----------------------------------------------------------------
    def _start_continuous_feed(self):
        def feed_loop():
            scan_tick_counter = 0
            while not self._shutdown.is_set():
                try:
                    with self._data_lock:
                        generation, mode = self._data_generation, self.data_mode
                    # 1. Price Tick (Real or Simulated)
                    if mode == "real":
                        if self.real_market_data.connected:
                            self._poll_real_market()
                        new_prices = self.current_prices.copy()
                    else:
                        # Simulated prices
                        new_prices = self.market_sim.tick()
                    
                    applied = self._apply_feed_prices(new_prices, generation, mode)
                    if applied is None:
                        continue
                    closed_trades, halt = applied
                    for tr in closed_trades:
                        sound = "tp" if tr.get("pnl", 0) > 0 else "sl"
                        self._play_chime(sound)
                        self.learner.record_closed_trade(tr.get("strategy", "unknown"), tr.get("pnl", 0.0), 0.7, tr.get("reason", ""))
                        self._log(f"PROTECTIVE EXIT: {tr['action']} {tr['symbol']} @ ${tr['price']:,.2f} | Reason: {tr['reason']} | Net PnL: ${tr['pnl']:+,.2f}", "RISK")
                        self.trade_markers.append({
                            "symbol": tr["symbol"], "action": "SELL", "price": tr["price"], "time": tr["timestamp"]
                        })

                    if halt and self.is_running:
                        self.is_running = False
                        self._log(f"AI PILOT HALTED: {halt}", "ALERT")
                        self.root.after(0, self._sync_pilot_buttons)

                    # 4. Multi-Asset Autonomous Scanner every 4 ticks (2 seconds)
                    scan_tick_counter += 1
                    if scan_tick_counter >= 4:
                        scan_tick_counter = 0
                        self._run_multi_asset_scanner()

                    # 5. UI Refresh
                    self.root.after(0, self._render_ui_updates)

                except Exception as ex:
                    logger.error(f"Feed loop error: {ex}", exc_info=True)

                self._shutdown.wait(0.5)

        threading.Thread(target=feed_loop, daemon=True).start()

    def _apply_feed_prices(self, prices, generation, mode):
        """Reject a feed result from a source that changed during its I/O."""
        with self._data_lock:
            if generation != self._data_generation or mode != self.data_mode:
                return None
            self.current_prices = prices
            protective = prices if mode == "simulated" else {
                symbol: price for symbol, price in prices.items()
                if quote_is_fresh(self._quote_updated_at.get(symbol), time.time())}
            closed = self.account.check_risk_triggers(protective)
            halt = self.guard.evaluate(self.account.get_metrics(prices))
            self.account.update_equity_curve(prices)
            return closed, halt

    def _run_multi_asset_scanner(self):
        """Scans all assets across crypto, stocks, and indices simultaneously."""
        strat_key = self.active_strategy
        snapshot = (self._data_generation, strat_key, self.active_timeframe)
        strat_obj = self.strategies.get(strat_key, self.strategies["ml_ensemble"])
        scanner_results = []
        min_conf = self.learner.min_confidence
        weights = self.learner.regime_weights if strat_key == "ml_ensemble" else None

        for sym, d in self.market_sim.all_symbols.items():
            if self.data_mode == "real" and not self._has_fresh_data(sym):
                continue
            ohlcv = self._get_active_bars(sym, 150)
            if self.data_mode == "real":
                ohlcv = ohlcv[:-1]  # The exchange's current candle is still forming.
            if len(ohlcv) < 30:
                continue
            df = pd.DataFrame(ohlcv)
            if strat_key == "ml_ensemble":
                sig = strat_obj.generate_signal(df, weight_overrides=weights)
            else:
                sig = strat_obj.generate_signal(df)

            with self._data_lock:
                if snapshot != (self._data_generation, self.active_strategy, self.active_timeframe):
                    continue
                curr_p = self.current_prices.get(sym)
                if curr_p is None or not math.isfinite(curr_p) or curr_p <= 0:
                    continue
            chg = (curr_p / ohlcv[0]["close"] - 1) * 100 if ohlcv[0]["close"] else 0
            regime = sig.get("regime", "neutral") if sig else "ranging"
            conf = sig.get("confidence", 0.0) if sig else 0.0
            action = sig.get("action", "HOLD") if sig else "HOLD"

            scanner_results.append({
                "symbol": sym, "category": d["category"], "price": curr_p,
                "change": chg, "regime": regime, "confidence": conf, "action": action, "sig": sig
            })

            with self._data_lock:
                scan_symbol = self.multi_asset_scan_enabled or sym == self.selected_symbol
                same_snapshot = snapshot == (self._data_generation, self.active_strategy, self.active_timeframe)
                if self.is_running and scan_symbol and same_snapshot and self._can_enter(sym):
                    if action == "BUY" and sym not in self.account.positions and conf >= min_conf:
                        if len(self.account.positions) < self.risk_manager.max_open_positions:
                            eq = self.account.get_equity(self.current_prices)
                            stop = sig.get("stop_loss")
                            if stop is None:
                                stop = curr_p * (1 - self.account.default_stop_loss_pct)
                            qty = self.risk_manager.calculate_position_size(eq, curr_p, stop, conf,
                                cash=self.account.cash, fee_fraction=self.account.commission_pct,
                                slippage_fraction=self.account.slippage_bps / 10000)
                            if qty <= 0:
                                continue
                            res = self.account.execute_trade(
                                sym, "BUY", qty, curr_p, sig["strategy"],
                                stop, sig.get("take_profit"), sig.get("reason", "")
                            )
                            if res["status"] == "filled":
                                self._play_chime("buy")
                                tr = res["trade"]
                                self._log(f"AI BUY: {sym} x {qty:.4f} @ ${tr['price']:,.2f} | Conf: {conf:.0%}", "BOT")
                                self.trade_markers.append({
                                    "symbol": sym, "action": "BUY", "price": tr["price"], "time": tr["timestamp"]
                                })
                    elif action == "SELL" and sym in self.account.positions and conf >= min_conf:
                        res = self.account.close_single_position(sym, curr_p, reason=f"AI_EXIT {sig.get('reason', '')}")
                        if res and res.get("status") == "filled":
                            self._play_chime("sell")
                            tr = res["trade"]
                            self.learner.record_closed_trade(tr.get("strategy", "unknown"), tr.get("pnl", 0.0), conf, sig.get("reason", ""))
                            self._log(f"AI SELL: {sym} @ ${tr['price']:,.2f} | PnL ${tr.get('pnl' ,0):+,.2f}", "BOT")
                            self.trade_markers.append({
                                "symbol": sym, "action": "SELL", "price": tr["price"], "time": tr["timestamp"]
                            })

        # Update scanner leaderboard on main thread
        self.root.after(0, lambda r=scanner_results, key=snapshot: self._publish_scanner_results(r, key))

    def _publish_scanner_results(self, results, snapshot):
        if snapshot != (self._data_generation, self.active_strategy, self.active_timeframe):
            return
        self._refresh_scanner_tree(results)
        active = next((row["sig"] for row in results if row["symbol"] == self.selected_symbol), None)
        self._update_ai_radar(active or {})

    # -----------------------------------------------------------------
    # UI RENDERING & REFRESH (MAIN THREAD)
    # -----------------------------------------------------------------
    def _render_ui_updates(self):
        """Safely refresh all UI widgets; a single widget error never kills the loop."""
        try:
            self._render_ui_updates_impl()
        except Exception as ex:
            logger.error(f"UI render error: {ex}", exc_info=True)

    def _render_ui_updates_impl(self):
        now = time.time()
        metrics = self.account.get_metrics(self.current_prices)

        self.hdr_equity_lbl.configure(text=f"Paper equity: ${metrics['equity']:,.2f}")
        pnl_col = COLORS["success"] if metrics["total_pnl"] >= 0 else COLORS["danger"]
        self.hdr_pnl_lbl.configure(
            text=f"Paper P&L: ${metrics['total_pnl']:+,.2f} ({metrics['total_return_pct']:+.2f}%)",
            text_color=pnl_col
        )
        self.hdr_winrate_lbl.configure(text=performance_evidence(
            metrics['winning_trades'], metrics['winning_trades'] + metrics['losing_trades']))
        if self.data_mode == "simulated":
            source, source_color = "SIMULATED DATA", COLORS["warning"]
        elif self._has_fresh_data(self.selected_symbol):
            age = max(0, int(now - self._quote_updated_at.get(self.selected_symbol, now)))
            source, source_color = f"BINANCE / USDT · fetched {age}s ago", COLORS["success"]
        else:
            source, source_color = "REAL DATA: UNAVAILABLE / STALE", COLORS["danger"]
        self.data_source_pill.configure(text=source, text_color=source_color)
        self.btn_buy.configure(state="normal" if self._can_enter(self.selected_symbol) else "disabled")

        # Watchlist Prices & Pulse
        for sym, w in self.watchlist_widgets.items():
            curr = self.current_prices.get(sym, 0.0)
            chg = self.market_sim.get_change_pct(sym)
            col = COLORS["success"] if chg >= 0 else COLORS["danger"]
            available = self.data_mode == "simulated" or sym in self.current_prices
            w["price_lbl"].configure(text=(f"${curr:,.2f}" if curr >= 10 else f"${curr:,.4f}") if available else "Unavailable")
            w["change_lbl"].configure(text=f"{chg:+.2f}%" if self.data_mode == "simulated" else "USDT quote" if available else "No real feed", text_color=col)

        # Chart Title
        curr_sel = self.current_prices.get(self.selected_symbol, 0.0)
        sel_chg = self.market_sim.get_change_pct(self.selected_symbol)
        chg_sign = "+" if sel_chg >= 0 else ""
        source_note = f"SIM · {chg_sign}{sel_chg:.2f}% session" if self.data_mode == "simulated" else "BINANCE / USDT"
        self.chart_title.configure(text=f"{self.selected_symbol}   ${curr_sel:,.2f}  / {source_note}")

        # Throttled Chart Draw
        if now - self._last_chart_draw_time >= 1.5:
            self._draw_chart()
            self._last_chart_draw_time = now

        self._flush_logs()
        self._refresh_positions_tree()
        self._refresh_orders_tree()
        self._refresh_analytics_tab(metrics)
        self._update_real_time_profit()
        if hasattr(self, "ai_learn_lbl"):
            self.ai_learn_lbl.configure(text=self.learner.summary_line())
            self.ai_note_lbl.configure(text=self.learner.last_note)
            if hasattr(self, "ai_perf_score_lbl"):
                samples = self.learner.total_trades
                self.ai_perf_score_lbl.configure(text=(f"Paper learning score: {self.learner.performance_score:.1%} ({samples} exits)"
                    if samples >= 5 else f"Learning score: needs 5 exits ({samples}/5)"))
                self.ai_perf_bar.set(self.learner.performance_score if samples >= 5 else 0)
                perf_color = COLORS["success"] if self.learner.performance_score >= 0.6 else (COLORS["warning"] if self.learner.performance_score >= 0.4 else COLORS["danger"])
                self.ai_perf_bar.configure(progress_color=perf_color)

    def _draw_chart(self):
        try:
            bars = self._get_active_bars(self.selected_symbol, 100)
            if len(bars) < 15:
                for axis in (self.ax_price, self.ax_rsi, self.ax_vol):
                    axis.clear()
                    axis.set_facecolor("#0D121F")
                self.ax_price.text(0.5, 0.5, "No candles from the selected source.\nReal data supports BTC, ETH and SOL only.",
                    ha="center", va="center", color=COLORS["text_secondary"], transform=self.ax_price.transAxes)
                self.canvas.draw_idle()
                return

            df = pd.DataFrame(bars)
            times = df['timestamp']
            opens = df['open']
            highs = df['high']
            lows = df['low']
            closes = df['close']
            vols = df['volume']

            self.ax_price.clear()
            self.ax_rsi.clear()
            self.ax_vol.clear()

            up_mask = closes >= opens
            down_mask = ~up_mask

            # 1. Price Subplot with Professional Candlesticks
            # Calculate bar width based on data
            if len(times) > 1:
                time_range = (times.iloc[-1] - times.iloc[0]).total_seconds()
                bar_width = time_range / len(times) * 0.5 / 86400.0
            else:
                bar_width = 3600 / 86400.0  # Matplotlib dates are measured in days.

            # Draw professional candlesticks with bodies and wicks
            for i in range(len(df)):
                if up_mask[i]:
                    # Green candle - brighter green
                    self.ax_price.bar(
                        [times[i]], [closes[i] - opens[i]],
                        bottom=[opens[i]],
                        width=bar_width,
                        color=COLORS["success"],
                        alpha=0.95,
                        edgecolor=COLORS["success"],
                        linewidth=2.0
                    )
                    # Wick - same color
                    self.ax_price.vlines(
                        times[i], lows[i], highs[i],
                        color=COLORS["success"], linewidth=3.0, alpha=0.9
                    )
                else:
                    # Red candle - brighter red
                    self.ax_price.bar(
                        [times[i]], [opens[i] - closes[i]],
                        bottom=[closes[i]],
                        width=bar_width,
                        color=COLORS["danger"],
                        alpha=0.95,
                        edgecolor=COLORS["danger"],
                        linewidth=2.0
                    )
                    # Wick - same color
                    self.ax_price.vlines(
                        times[i], lows[i], highs[i],
                        color=COLORS["danger"], linewidth=3.0, alpha=0.9
                    )

            if self.show_ema_var.get() and len(closes) >= 21:
                ema9 = closes.ewm(span=9, adjust=False).mean()
                ema21 = closes.ewm(span=21, adjust=False).mean()
                self.ax_price.plot(times, ema9, color=COLORS["accent_cyan"], linewidth=2.5, label="EMA 9")
                self.ax_price.plot(times, ema21, color=COLORS["accent_pink"], linewidth=2.5, label="EMA 21")
                if len(closes) >= 50:
                    ema50 = closes.ewm(span=50, adjust=False).mean()
                    self.ax_price.plot(times, ema50, color=COLORS["accent_purple"], linewidth=2.0, label="EMA 50")
                self.ax_price.legend(loc="upper left", fontsize=10, facecolor=COLORS["card_bg"], edgecolor=COLORS["card_border"], labelcolor=COLORS["text_primary"])

            if self.show_bb_var.get() and len(closes) >= 20:
                sma20 = closes.rolling(20).mean()
                std20 = closes.rolling(20).std()
                upper = sma20 + 2 * std20
                lower = sma20 - 2 * std20
                self.ax_price.plot(times, upper, color=COLORS["text_muted"], linestyle="--", linewidth=2.0)
                self.ax_price.plot(times, lower, color=COLORS["text_muted"], linestyle="--", linewidth=2.0)
                self.ax_price.fill_between(times, lower, upper, color=COLORS["accent_blue"], alpha=0.1)

            # Trade Execution Markers
            last_time = times.iloc[-1] if len(times) > 0 else None
            for tm in self.trade_markers:
                if tm["symbol"] == self.selected_symbol and last_time and (last_time - tm["time"]).total_seconds() < 3600 * 4:
                    col = COLORS["success"] if tm["action"] == "BUY" else COLORS["danger"]
                    m = "^" if tm["action"] == "BUY" else "v"
                    self.ax_price.scatter(tm["time"], tm["price"], color=col, marker=m, s=150, zorder=5, edgecolors="white", linewidth=2.0)

            # 2. RSI Subplot
            if self.show_rsi_var.get():
                delta = closes.diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                rsi = 100 - (100 / (1 + rs))

                self.ax_rsi.plot(times, rsi, color=COLORS["accent_purple"], linewidth=2.5)
                self.ax_rsi.axhline(70, color=COLORS["danger"], linestyle="--", linewidth=2.0, alpha=0.9)
                self.ax_rsi.axhline(30, color=COLORS["success"], linestyle="--", linewidth=2.0, alpha=0.9)
                self.ax_rsi.set_ylim(10, 90)
                self.ax_rsi.set_ylabel("RSI", color=COLORS["text_secondary"], fontsize=8, fontweight="bold")
                self.ax_rsi.fill_between(times, rsi, 70, where=(rsi >= 70), color=COLORS["danger"], alpha=0.3)
                self.ax_rsi.fill_between(times, rsi, 30, where=(rsi <= 30), color=COLORS["success"], alpha=0.3)

            # 3. Volume Subplot
            vol_colors = [COLORS["success"] if up else COLORS["danger"] for up in up_mask]
            self.ax_vol.bar(times, vols, color=vol_colors, alpha=0.7, width=bar_width, edgecolor="none")
            self.ax_vol.set_ylabel("Vol", color=COLORS["text_secondary"], fontsize=8, fontweight="bold")

            for ax in [self.ax_price, self.ax_rsi, self.ax_vol]:
                ax.set_facecolor(COLORS["card_bg"])
                ax.grid(True, linestyle=":", alpha=0.25, color=COLORS["card_border"])
                ax.tick_params(colors=COLORS["text_secondary"], labelsize=8)
                for sp in ax.spines.values(): sp.set_color(COLORS["card_border"])

            self.ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            self.fig.autofmt_xdate(bottom=0.15, rotation=0, ha="center")
            self.canvas.draw_idle()

        except Exception as e:
            logger.error(f"Chart redraw error: {e}")

    def _force_chart_redraw(self):
        self._last_chart_draw_time = 0.0

    def _refresh_positions_tree(self):
        selected = self.pos_tree.selection()
        selected_id = self.pos_tree.item(selected[0])["values"][0] if selected else None

        self.pos_tree.delete(*self.pos_tree.get_children())
        for sym, p in self.account.positions.items():
            curr = self.current_prices.get(sym, p["avg_price"])
            unreal_pnl = (curr - p["avg_price"]) * p["quantity"]
            ret_pct = (curr - p["avg_price"]) / p["avg_price"] * 100.0
            tag = "green" if unreal_pnl >= 0 else "red"

            item_id = self.pos_tree.insert("", "end", values=(
                sym, "LONG", f"{p['quantity']:.4f}", f"${p['avg_price']:,.2f}",
                f"${curr:,.2f}", f"${p.get('stop_loss', 0):,.2f}", f"${p.get('take_profit', 0):,.2f}",
                f"${unreal_pnl:+,.2f}", f"{ret_pct:+.2f}%", p.get("strategy", "manual")
            ), tags=(tag,))

            if sym == selected_id:
                self.pos_tree.selection_set(item_id)

    def _refresh_orders_tree(self):
        if len(self.account.trade_history) == len(self.orders_tree.get_children()):
            return
        self.orders_tree.delete(*self.orders_tree.get_children())
        for tr in reversed(self.account.trade_history[-40:]):
            time_str = tr["timestamp"].strftime("%H:%M:%S")
            pnl_str = f"${tr['pnl']:+,.2f}" if "pnl" in tr else "-"
            tag = "green" if tr.get("pnl", 0) > 0 else ("red" if tr.get("pnl", 0) < 0 else "")

            self.orders_tree.insert("", "end", values=(
                time_str, tr["symbol"], tr["action"], f"{tr['quantity']:.4f}",
                f"${tr['price']:,.2f}", pnl_str, f"${tr.get('commission', 0):.2f}",
                tr["status"].upper(), tr.get("reason", tr.get("strategy", ""))
            ), tags=(tag,))

    def _refresh_scanner_tree(self, results: List[Dict[str, Any]]):
        self.scanner_tree.delete(*self.scanner_tree.get_children())
        for r in sorted(results, key=lambda x: x["confidence"], reverse=True):
            tag = "green" if r["action"] == "BUY" else ("red" if r["action"] == "SELL" else "")
            self.scanner_tree.insert("", "end", values=(
                r["symbol"], r["category"].upper(), f"${r['price']:,.2f}",
                f"{r['change']:+.2f}%", r["regime"].upper(),
                f"{r['confidence']:.0%}" if r["action"] != "HOLD" else "—",
                r["action"], "PAPER ELIGIBLE" if r["action"] == "BUY" and self._can_enter(r["symbol"]) and r["confidence"] >= self.learner.min_confidence else "WAIT"
            ), tags=(tag,))

    def _refresh_analytics_tab(self, m: Dict[str, Any]):
        lbls = self.analytics_labels
        lbls["equity"].configure(text=f"${m['equity']:,.2f}")
        lbls["cash"].configure(text=f"${m['cash']:,.2f}")
        pnl_col = COLORS["success"] if m["total_pnl"] >= 0 else COLORS["danger"]
        lbls["pnl"].configure(text=f"${m['total_pnl']:+,.2f}", text_color=pnl_col)
        lbls["return_pct"].configure(text=f"{m['total_return_pct']:+.2f}%", text_color=pnl_col)
        lbls["sharpe"].configure(text=f"{m['sharpe']:.2f}")
        lbls["drawdown"].configure(text=f"{m['max_drawdown_pct']:.2f}%", text_color=COLORS["danger"] if m["max_drawdown_pct"] > 5 else COLORS["text_primary"])
        closed = m['winning_trades'] + m['losing_trades']
        lbls["win_rate"].configure(text=f"{m['win_rate']:.1f}% ({closed} exits)" if closed else "Awaiting exits")
        factor = (f"{m['profit_factor']:.2f}" if m['losing_trades'] else "∞ (no losses)" if m['winning_trades'] else "—")
        lbls["profit_factor"].configure(text=factor)
        lbls["avg_win"].configure(text=f"${m.get('avg_win', 0):,.2f}", text_color=COLORS["success"])
        lbls["avg_loss"].configure(text=f"${m.get('avg_loss', 0):,.2f}", text_color=COLORS["danger"])
        lbls["avg_r_multiple"].configure(text=f"{m.get('avg_r_multiple', 0):.2f}")

    def _update_ai_radar(self, sig: Dict[str, Any]):
        self.latest_signal = dict(sig) if sig else None
        action = sig.get("action", "NEUTRAL")
        conf = max(0.0, min(1.0, float(sig.get("confidence", 0.0))))

        if action == "BUY":
            col = COLORS["success"]
            bg = COLORS["success_dim"]
            text = f"STRONG BUY ({conf:.0%})" if conf >= 0.85 else f"BUY SIGNAL ({conf:.0%})"
        elif action == "SELL":
            col = COLORS["danger"]
            bg = COLORS["danger_dim"]
            text = f"STRONG SELL ({conf:.0%})" if conf >= 0.85 else f"SELL SIGNAL ({conf:.0%})"
        else:
            col = COLORS["text_secondary"]
            bg = "#263148"
            text = "NEUTRAL / SCANNING"

        self.ai_action_lbl.configure(text=text, text_color=col, fg_color=bg)
        self.ai_conf_num.configure(text=f"{conf:.0%}" if sig else "—")
        self.ai_conf_bar.set(conf)
        self.ai_conf_bar.configure(progress_color=col)
        self.ai_reason_txt.configure(text=sig.get("reason", "No qualifying signal for the selected source and strategy."))
        
        # Update signal strength meter
        self.signal_strength_bar.set(conf)
        if conf >= 0.85:
            strength_text = "Very Strong"
            strength_color = COLORS["success"]
        elif conf >= 0.70:
            strength_text = "Strong"
            strength_color = COLORS["accent_cyan"]
        elif conf >= 0.50:
            strength_text = "Moderate"
            strength_color = COLORS["warning"]
        else:
            strength_text = "Weak"
            strength_color = COLORS["danger"]
        
        self.signal_strength_lbl.configure(text=f"Score: {conf:.0%} ({strength_text}) · not a win probability" if sig else "Awaiting a qualifying signal", text_color=strength_color)
        self.signal_strength_bar.configure(progress_color=strength_color)

        # Factors
        f = sig.get("factors", {})
        if "Josh Strategy" in self.factor_labels:
            j_sc = f.get("josh", 0.5)
            self.factor_labels["Josh Strategy"].configure(
                text="BULLISH" if j_sc > 0.6 else ("BEARISH" if j_sc < 0.4 else "NEUTRAL"),
                text_color=COLORS["success"] if j_sc > 0.6 else (COLORS["danger"] if j_sc < 0.4 else COLORS["text_secondary"])
            )
        if "Trend Momentum" in self.factor_labels:
            m_sc = f.get("momentum", 0.5)
            self.factor_labels["Trend Momentum"].configure(
                text="BULLISH" if m_sc > 0.6 else ("BEARISH" if m_sc < 0.4 else "NEUTRAL"),
                text_color=COLORS["success"] if m_sc > 0.6 else (COLORS["danger"] if m_sc < 0.4 else COLORS["text_secondary"])
            )
        if "Bollinger Z-Score" in self.factor_labels:
            mr_sc = f.get("mean_rev", 0.5)
            self.factor_labels["Bollinger Z-Score"].configure(
                text="OVERSOLD" if mr_sc > 0.6 else ("OVERBOUGHT" if mr_sc < 0.4 else "NEUTRAL"),
                text_color=COLORS["success"] if mr_sc > 0.6 else (COLORS["danger"] if mr_sc < 0.4 else COLORS["text_secondary"])
            )
        if "Channel Breakout" in self.factor_labels:
            bo_sc = f.get("breakout", 0.5)
            self.factor_labels["Channel Breakout"].configure(
                text="SURGE" if bo_sc > 0.6 else "CONSOLIDATING",
                text_color=COLORS["accent_cyan"] if bo_sc > 0.6 else COLORS["text_secondary"]
            )

    # -----------------------------------------------------------------
    # QUANT BACKTEST RUNNER
    # -----------------------------------------------------------------
    def _run_quant_backtest(self):
        asset = self.bt_asset_combo.get()
        strat = self.bt_strat_combo.get()
        bars = self._get_active_bars(asset, 240)

        if len(bars) < 40:
            messagebox.showwarning("Data Limit", "Collecting more historical bars for backtest...")
            return

        res = QuantBacktester.run_backtest(bars, strategy_name=strat, initial_cash=25000.0)
        self.latest_backtest = {**res, "data_source": self.data_mode, "symbol": asset,
                                "strategy": strat, "evaluation": "exploratory_same_sample"}

        self.bt_result_lbl.configure(
            text=f"EXPLORATORY / {self.data_mode.upper()} · {asset} / {strat} | Return {res['return_pct']:+.2f}% | Wins {res['win_rate']:.1f}% | Max DD {res['max_drawdown']:.2f}% | {res['total_trades']} exits · not held out",
            text_color=COLORS["success"] if res["return_pct"] >= 0 else COLORS["danger"]
        )

        # Plot Equity vs Benchmark
        self.bt_ax.clear()
        eq = res["equity_curve"]
        bench = res["benchmark_curve"]

        self.bt_ax.plot(eq, color=COLORS["accent_cyan"], linewidth=1.8, label="Loki Strategy")
        self.bt_ax.plot(bench, color="#64748B", linestyle="--", linewidth=1.1, label="Buy & Hold")
        self.bt_ax.legend(loc="upper left", facecolor="#141B2D", edgecolor="#283452", labelcolor="#F8FAFC", fontsize=8)
        self.bt_ax.grid(True, linestyle=":", alpha=0.25, color="#334155")
        self.bt_ax.set_facecolor("#0D121F")
        self.bt_ax.tick_params(colors="#94A3B8", labelsize=8)

        self.bt_canvas.draw()
        self._log(f"Backtest executed for {asset} ({strat}): Net Return {res['return_pct']:+.2f}%, PF: {res['profit_factor']}", "QUANT")

    def _run_oos_validation(self):
        asset, source = self.bt_asset_combo.get(), self.data_mode
        bars = self._get_active_bars(asset, 250)
        if source == "real":
            bars = bars[:-1]
        if len(bars) < 161:
            messagebox.showinfo("More data needed", "OOS trend validation needs at least 161 candles from the selected source.")
            return
        timeframe = self.active_timeframe
        self.oos_btn.configure(state="disabled", text="VALIDATING…")
        self.bt_result_lbl.configure(text="Running chronological walk-forward trend selection, next-open execution and cost stress…")

        def run():
            try:
                differences = sorted((bars[index]["timestamp"] - bars[index - 1]["timestamp"]).total_seconds()
                                     for index in range(1, len(bars)))
                interval_seconds = differences[len(differences) // 2]
                report = evaluate_strategy(bars, {"initial_capital": 25000.0,
                    "periods_per_year": max(1, round(365 * 24 * 3600 / interval_seconds))})
                report["assumptions"].append(f"Annualization uses the observed median candle interval: {interval_seconds:g} seconds.")
                report["data_source"], report["symbol"] = source, asset
                self.root.after(0, lambda: self._display_oos_report(report))
            except Exception as error:
                self.root.after(0, lambda message=str(error): self.bt_result_lbl.configure(text=f"Validation failed: {message}"))
            finally:
                self.root.after(0, lambda: self.oos_btn.configure(state="normal", text="OOS trend validation"))
        threading.Thread(target=run, daemon=True).start()

    def _display_oos_report(self, report: Dict[str, Any]):
        self.latest_backtest = report
        result = report["summary"]
        reasons = "; ".join(report["rejection_reasons"][:2]) or "Paper research candidate only; future returns remain unknown."
        self.bt_result_lbl.configure(text=(
            f"OOS TREND / {report['data_source'].upper()} · {report['symbol']} | "
            f"Return {result['total_return']:+.2%} vs benchmark {report['benchmark']['total_return']:+.2%} | "
            f"DD {result['max_drawdown']:.2%} | {result['total_trades']} exits | {report['status']}\n{reasons}"),
            text_color=COLORS["accent_cyan"])
        self.bt_ax.clear()
        points = report["equity_curve"]
        self.bt_ax.plot([point["equity"] for point in points], color=COLORS["accent_cyan"], label="OOS trend")
        self.bt_ax.plot([point["benchmark_equity"] for point in points], color="#A1AEC3", linestyle="--", label="Buy & hold")
        self.bt_ax.legend(facecolor="#141B2D", labelcolor="white", fontsize=8)
        self.bt_ax.set_facecolor("#0D121F")
        self.bt_ax.tick_params(colors="#A1AEC3", labelsize=8)
        self.bt_canvas.draw_idle()
        self._log(f"OOS trend report for {report['symbol']}: {report['status']}; return {result['total_return']:+.2%}", "RESEARCH")

    # -----------------------------------------------------------------
    # USER INTERACTIONS & CONTROLS
    # -----------------------------------------------------------------
    def _select_symbol(self, symbol: str):
        self.selected_symbol = symbol
        self._update_ai_radar({})
        self._force_chart_redraw()
        for s, w in self.watchlist_widgets.items():
            w["card"].configure(fg_color=COLORS["card_border"] if s == symbol else COLORS["card_alt"])
        self._update_risk_reward_preview()
        self._log(f"Switched active asset to: {symbol}", "UI")

    def _filter_watchlist(self, *args):
        query = self.search_entry.get().strip().upper()
        selected_cat = self.cat_seg.get().lower()

        for sym, w in self.watchlist_widgets.items():
            matches_cat = (selected_cat == "all") or (w["category"] == selected_cat)
            matches_query = (query == "") or (query in sym)
            if matches_cat and matches_query:
                w["card"].pack(fill="x", padx=4, pady=3)
                # Highlight matching text
                if query and query in sym:
                    w["card"].configure(fg_color=COLORS["accent_blue"])
                else:
                    w["card"].configure(fg_color=COLORS["card_border"] if sym == self.selected_symbol else COLORS["card_alt"])
            else:
                w["card"].pack_forget()

    def _calc_risk_qty(self, risk_fraction: float):
        curr = self.current_prices.get(self.selected_symbol, 0.0)
        if curr <= 0: return
        eq = self.account.get_equity(self.current_prices)
        try:
            stop = float(self.sl_entry.get().strip()) if self.sl_entry.get().strip() else curr * (1 - self.account.default_stop_loss_pct)
            qty = risk_sized_quantity(eq, self.account.cash, curr, stop, risk_fraction,
                self.account.commission_pct, self.account.slippage_bps / 10000)
        except ValueError as error:
            messagebox.showerror("Risk sizing", str(error))
            return
        self.qty_entry.delete(0, "end")
        self.qty_entry.insert(0, f"{math.floor(qty * 10000) / 10000:.4f}")
        self._update_risk_reward_preview()

    def _update_risk_reward_preview(self):
        try:
            curr = self.current_prices.get(self.selected_symbol, 0.0)
            qty = float(self.qty_entry.get().strip() or "0")
            if curr <= 0 or qty <= 0: return

            sl_txt = self.sl_entry.get().strip()
            tp_txt = self.tp_entry.get().strip()

            sl = float(sl_txt) if sl_txt else curr * (1 - self.account.default_stop_loss_pct)
            tp = float(tp_txt) if tp_txt else curr * (1 + self.account.default_take_profit_pct)
            if not all(math.isfinite(value) for value in (curr, qty, sl, tp)) or not 0 < sl < curr < tp:
                self.rr_preview_lbl.configure(text="Use a stop below entry and a target above entry.", text_color=COLORS["danger"])
                return

            fee, slip = self.account.commission_pct, self.account.slippage_bps / 10000
            entry_cost = curr * (1 + slip) * (1 + fee) * qty
            risk_dol = entry_cost - sl * (1 - slip) * (1 - fee) * qty
            reward_dol = tp * (1 - slip) * (1 - fee) * qty - entry_cost
            rr = (reward_dol / risk_dol) if risk_dol > 0 else 0.0

            col = COLORS["success"] if rr >= 1.5 else (COLORS["warning"] if rr >= 1.0 else COLORS["danger"])
            self.rr_preview_lbl.configure(
                text=f"Est. risk: ${risk_dol:.2f} | Reward: ${reward_dol:.2f}\nR:R 1:{rr:.2f} · incl. costs; gaps may exceed stop",
                text_color=col
            )
        except Exception:
            pass

    def _update_real_time_profit(self):
        """Update real-time profit/loss for all open positions."""
        total_unreal_pnl = 0.0
        position_count = 0
        
        for sym, pos in self.account.positions.items():
            curr = self.current_prices.get(sym, pos["avg_price"])
            unreal_pnl = (curr - pos["avg_price"]) * pos["quantity"]
            total_unreal_pnl += unreal_pnl
            position_count += 1
        
        # Update profit calculator if it exists
        if hasattr(self, 'real_time_profit_lbl'):
            pnl_color = COLORS["success"] if total_unreal_pnl >= 0 else COLORS["danger"]
            self.real_time_profit_lbl.configure(
                text=f"Unrealized P&L: ${total_unreal_pnl:+,.2f} ({position_count} positions)",
                text_color=pnl_color
            )

    def _on_timeframe_change(self, value: str):
        if self.data_mode == "simulated" and value != "5m":
            self.tf_var.set("5m")
            messagebox.showinfo("Synthetic candle interval", "The simulator uses five-minute historical candles. Select REAL data to use other candle intervals.")
            return
        self.active_timeframe = value
        self._update_ai_radar({})
        mapping = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
        self.market_sim.set_bar_seconds(mapping.get(value, 300))
        self._log(f"Chart/bar interval set to {value}. New candles will form at that pace.", "UI")
        self._force_chart_redraw()

    def _sync_pilot_buttons(self):
        if self.guard.halted:
            label = "AI HALTED"
            color = COLORS["danger"]
            hover = COLORS["danger_dim"]
            status = f"Halted: {self.guard.halt_reason}"
            badge = "● RISK HALT"
            badge_col = COLORS["danger"]
            badge_bg = COLORS["danger_dim"]
        elif self.is_running:
            label = "PAUSE AI PILOT"
            color = COLORS["warning"]
            hover = "#D97706"
            status = f"Autonomous paper trading ON · min conviction {self.learner.min_confidence:.0%}"
            badge = "● AI TRADING"
            badge_col = COLORS["success"]
            badge_bg = COLORS["success_dim"]
        else:
            label = "START PAPER PILOT"
            color = COLORS["success"]
            hover = "#059669"
            status = "Idle — press the button to start autonomous paper trading."
            badge = "● STANDBY"
            badge_col = COLORS["warning"]
            badge_bg = "#332408"

        self.start_btn.configure(text="PAUSE PAPER PILOT" if self.is_running else "START PAPER PILOT", fg_color=color, hover_color=hover)
        if hasattr(self, "ai_pilot_btn"):
            self.ai_pilot_btn.configure(text=label, fg_color=color, hover_color=hover)
            self.ai_pilot_status.configure(
                text=status,
                text_color=COLORS["success"] if self.is_running and not self.guard.halted else (
                    COLORS["danger"] if self.guard.halted else COLORS["warning"]
                )
            )
        self.status_badge.configure(text=badge, text_color=badge_col, fg_color=badge_bg)

    def _toggle_bot(self):
        if self.guard.halted and not self.is_running:
            if not messagebox.askyesno("Reset risk halt?", f"{self.guard.halt_reason}\n\nReset the guard and start the AI pilot again?"):
                return
            self.guard.reset()

        if self.is_running:
            self.is_running = False
            self._log("AI pilot paused. Scanner still runs; no new auto orders.", "BOT")
        else:
            # Check AI readiness before starting
            readiness = self.learner.get_ai_readiness()
            if not readiness["ready"]:
                if not messagebox.askyesno(
                    "AI Not Ready",
                    f"AI is not ready for auto-trading:\n\n{readiness['reason']}\n\n"
                    f"Performance Score: {readiness['score']:.1%}\n"
                    f"Min Confidence: {readiness['min_confidence']:.0%}\n\n"
                    f"Start anyway? (Not recommended - do manual trades first to train the AI)"
                ):
                    return

            self.is_running = True
            self._log(
                f"AI pilot started. It will paper-trade across the watchlist when conviction ≥ {self.learner.min_confidence:.0%}.",
                "BOT"
            )
        self._sync_pilot_buttons()

    def _train_ai(self):
        """Compare exploratory strategies without altering measured learner outcomes."""
        if self._research_busy:
            return
        asset = self.selected_symbol
        bars = self._get_active_bars(asset, 240)
        source = self.data_mode
        if len(bars) < 40:
            messagebox.showinfo("Research data", "At least 40 candles from the selected source are needed.")
            return
        self._research_busy = True
        self.ai_train_btn.configure(state="disabled", text="COMPARING…")
        self._log(f"Comparing strategies on {source} candles for {asset}. Learner outcomes remain separate.", "RESEARCH")

        def compare():
            try:
                results = [(name, QuantBacktester.run_backtest(bars, strategy_name=name))
                           for name in self.strategies]
                results.sort(key=lambda row: row[1].get("return_pct", -float("inf")), reverse=True)
                lines = [f"{name}: {result['return_pct']:+.2f}% | {result['total_trades']} exits | "
                         f"DD {result['max_drawdown']:.2f}%" for name, result in results]
                text = (f"{asset} / {source.upper()} / {len(bars)} candles\n\n" + "\n".join(lines)
                        + "\n\nExploratory results reuse the same sample. They do not prove future profitability "
                        "or train the learner. Use OOS trend validation for a separate held-out assessment.")
                self.root.after(0, lambda: messagebox.showinfo("Strategy comparison", text))
            except Exception as error:
                self._log(f"Strategy comparison failed: {error}", "ERROR")
            finally:
                self.root.after(0, self._finish_research)
        threading.Thread(target=compare, daemon=True).start()

    def _finish_research(self):
        self._research_busy = False
        self.ai_train_btn.configure(state="normal", text="COMPARE STRATEGIES")

    def _emergency_halt(self):
        if messagebox.askyesno("Close paper positions", "Halt the paper pilot and close all paper positions at the last available prices? Stale or missing quotes may prevent a close."):
            self.is_running = False
            self.guard.halted = True
            self.guard.halt_reason = "Manual liquidate-all"
            self._sync_pilot_buttons()

            symbols = list(self.account.positions.keys())
            closed = 0
            for s in symbols:
                curr = self.current_prices.get(s, 0.0)
                if self.data_mode == "real" and not quote_is_fresh(self._quote_updated_at.get(s), time.time()):
                    self._log(f"Paper close skipped for {s}: quote unavailable or stale.", "ALERT")
                    continue
                result = self.account.close_single_position(s, curr, reason="EMERGENCY_HALT")
                if result and result.get("status") == "filled":
                    closed += 1
                    trade = result["trade"]
                    self.learner.record_closed_trade(trade.get("strategy", "manual"), trade.get("pnl", 0), 0.5, "EMERGENCY_HALT")
                    self._log(f"PAPER POSITION CLOSED: {s} @ ${curr:,.2f}", "ALERT")

            self._play_chime("sl")
            self._force_chart_redraw()
            messagebox.showinfo("Paper pilot halted", f"Closed {closed} position(s). {len(self.account.positions)} remain open. Paper trading is halted.")

    def _manual_execute(self, action: str):
        try:
            sym = self.selected_symbol
            qty = float(self.qty_entry.get().strip())
            curr = self.current_prices.get(sym, 0.0)
            if self.data_mode == "real" and not quote_is_fresh(self._quote_updated_at.get(sym), time.time()):
                messagebox.showwarning("Price unavailable", "Wait for a fresh quote from the selected source.")
                return

            if action == "BUY" and not self._can_enter(sym):
                messagebox.showwarning("Paper entry blocked", "The risk guard or selected data source is not ready. Use fresh quotes and review the risk status.")
                return

            if not all(math.isfinite(value) and value > 0 for value in (qty, curr)):
                messagebox.showerror("Invalid Input", "Please enter a valid positive quantity.")
                return

            sl_val = float(self.sl_entry.get().strip()) if self.sl_entry.get().strip() else None
            tp_val = float(self.tp_entry.get().strip()) if self.tp_entry.get().strip() else None

            res = self.account.execute_trade(
                symbol=sym, action=action, quantity=qty, price=curr,
                strategy="manual", stop_loss=sl_val, take_profit=tp_val, reason="MANUAL_ORDER"
            )

            if res["status"] == "filled":
                tr = res["trade"]
                if action == "SELL":
                    self.learner.record_closed_trade(tr.get("strategy", "manual"), tr.get("pnl", 0), 0.5, "MANUAL_ORDER")
                self._play_chime("buy" if action == "BUY" else "sell")
                self._log(f"MANUAL ORDER: {action} {sym} x {qty:.4f} @ ${tr['price']:,.2f}", "MANUAL")
                self.trade_markers.append({
                    "symbol": sym, "action": action, "price": tr["price"], "time": tr["timestamp"]
                })
                self._force_chart_redraw()
                messagebox.showinfo("Order Filled", f"{action} order executed at ${tr['price']:,.2f}")
            else:
                messagebox.showwarning("Rejected", res.get("reason", "Order rejected"))

        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric quantities.")

    def _close_selected_position(self):
        sel = self.pos_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please click a position in the table to select it.")
            return

        sym = self.pos_tree.item(sel[0])["values"][0]
        curr = self.current_prices.get(sym, 0.0)
        if self.data_mode == "real" and not quote_is_fresh(self._quote_updated_at.get(sym), time.time()):
            messagebox.showwarning("Price unavailable", "Wait for a fresh quote from the selected source.")
            return

        res = self.account.close_single_position(sym, curr, reason="MANUAL_UI_CLOSE")
        if res and res["status"] == "filled":
            tr = res["trade"]
            self.learner.record_closed_trade(tr.get("strategy", "manual"), tr.get("pnl", 0.0), 0.5, "MANUAL_CLOSE")
            self._play_chime("tp" if tr.get("pnl", 0) > 0 else "sl")
            self._log(f"CLOSED POSITION: {sym} @ ${tr['price']:,.2f} | Net PnL: ${tr['pnl']:+,.2f}", "MANUAL")
            self._force_chart_redraw()
            messagebox.showinfo("Position Closed", f"Position in {sym} closed at ${tr['price']:,.2f} (P&L: ${tr['pnl']:+,.2f})")

    def _on_strategy_change(self, new_val: str):
        self.active_strategy = new_val
        self._update_ai_radar({})
        self._log(f"Active strategy set to: {new_val}", "STRATEGY")

    def _on_trading_mode_change(self, value: str):
        """This execution path is paper-only until a real broker is implemented."""
        self.trading_mode = "paper"
        self.trading_mode_var.set("PAPER")
        self.trading_mode_pill.configure(text="PAPER ONLY")
        if value == "LIVE":
            messagebox.showinfo("Paper terminal", "This desktop account simulates fills. Live broker execution is not implemented here.")

    def _on_data_mode_change(self, value: str):
        desired = "real" if value == "REAL" else "simulated"
        if desired == self.data_mode:
            return
        if self.account.positions:
            self.data_mode_var.set("REAL" if self.data_mode == "real" else "SIM")
            messagebox.showinfo("Open paper positions", "Close open paper positions before changing price sources, so entries and exits use the same source.")
            return
        if desired == "real" and (not CCXT_AVAILABLE or not self.real_market_data.connect()):
            self.data_mode_var.set("SIM")
            messagebox.showerror("Real data unavailable", "A CCXT connection is required for Binance crypto data. The simulator remains selected.")
            return
        self._pause_pilot()
        with self._data_lock:
            if self.account.positions:
                self.data_mode_var.set("REAL" if self.data_mode == "real" else "SIM")
                messagebox.showinfo("Open paper positions", "A paper position opened during the source change. Close positions first.")
                return
            self._data_generation += 1
            self.data_mode = desired
            self.latest_backtest = None
            self._last_real_poll = 0
            self._real_bars.clear()
            self._real_bar_keys.clear()
            self._bars_updated_at.clear()
            self._quote_updated_at.clear()
            self.current_prices = {} if desired == "real" else self.market_sim.prices.copy()
            if desired == "simulated":
                self.active_timeframe = "5m"
                self.tf_var.set("5m")
                self.market_sim.set_bar_seconds(300)
        self._update_ai_radar({})
        self._force_chart_redraw()
        self._log(f"Source changed to {desired.upper()}; pilot paused. Real feed supports BTC/ETH/SOL quoted in USDT.", "DATA")

    def _export_trades(self):
        """Export all trade history to CSV file."""
        try:
            if not self.account.trade_history:
                messagebox.showinfo("No Trades", "No trade history to export.")
                return

            from tkinter import filedialog
            export_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                initialfile=f"loki_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                title="Export Trade History"
            )

            if not export_path:
                return

            # Create CSV with trade data
            import csv
            with open(export_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Symbol", "Action", "Quantity", "Price",
                    "Commission", "Realized P&L", "P&L %", "Strategy", "Reason", "Status"
                ])

                for trade in self.account.trade_history:
                    writer.writerow([
                        trade.get("timestamp", ""),
                        trade.get("symbol", ""),
                        trade.get("action", ""),
                        trade.get("quantity", ""),
                        trade.get("price", ""),
                        trade.get("commission", ""),
                        trade.get("pnl", ""),
                        trade.get("pnl_pct", ""),
                        trade.get("strategy", ""),
                        trade.get("reason", ""),
                        trade.get("status", "")
                    ])

            self._log(f"Exported {len(self.account.trade_history)} trades to {export_path}", "EXPORT")
            messagebox.showinfo("Export Complete", f"Successfully exported {len(self.account.trade_history)} trades to:\n{export_path}")

        except Exception as e:
            logger.error(f"Export failed: {e}")
            messagebox.showerror("Export Failed", f"Failed to export trades:\n{e}")

    def _save_settings(self):
        try:
            settings = validate_risk_settings({
                "risk_per_trade_pct": self.cfg_risk_pct.get(),
                "stop_loss_pct": self.cfg_sl_pct.get(),
                "take_profit_pct": self.cfg_tp_pct.get(),
                "trailing_stop_pct": self.cfg_trail_pct.get(),
                "daily_loss_pct": self.cfg_daily_loss.get(),
                "max_drawdown_pct": self.cfg_max_dd.get(),
                "min_confidence": self.cfg_min_conf.get(),
            })
        except ValueError as error:
            messagebox.showerror("Invalid risk setting", str(error))
            return
        self.risk_manager.risk_per_trade_pct = settings["risk_per_trade_pct"]
        self.account.default_stop_loss_pct = settings["stop_loss_pct"]
        self.account.default_take_profit_pct = settings["take_profit_pct"]
        self.account.trailing_stop_pct = settings["trailing_stop_pct"]
        self.guard.max_daily_loss_pct = settings["daily_loss_pct"]
        self.guard.max_drawdown_pct = settings["max_drawdown_pct"]
        self.learner.min_confidence = settings["min_confidence"]
        self.audio_alerts_enabled = self.cfg_audio_var.get()
        self.multi_asset_scan_enabled = self.cfg_multiscan_var.get()
        self.learner.enabled = self.cfg_learn_var.get()
        self.learner.save()
        self._save_session_state()
        self._sync_pilot_buttons()
        self._update_risk_reward_preview()
        self._log("Validated settings applied. Defaults affect new orders.", "SETTINGS")
        messagebox.showinfo("Settings applied", "Risk settings saved. Stop and target defaults apply to new orders.")

    def _on_tk_exception(self, exc_type, exc_value, exc_tb):
        """Route uncaught Tk callback exceptions into the in-app log instead of stderr."""
        try:
            msg = f"{exc_type.__name__}: {exc_value}"
            logger.error(msg, exc_info=(exc_type, exc_value, exc_tb))
            self._log(f"UI error: {msg}", "ERROR")
        except Exception:
            pass

    def _log(self, message: str, tag: str = "INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = f"[{now_str}] [{tag}] {message}\n"
        logger.info(f"[{tag}] {message}")
        with self._log_lock:
            self._pending_logs.append(entry)

    def _flush_logs(self):
        with self._log_lock:
            entries = self._pending_logs[:]
            self._pending_logs.clear()
        if not entries or not hasattr(self, "log_textbox"):
            return
        self.log_textbox.insert("end", "".join(entries))
        self.log_textbox.see("end")

    # -----------------------------------------------------------------
    # AUTO-SAVE & SESSION PERSISTENCE
    # -----------------------------------------------------------------
    def _save_session_state(self):
        """Auto-save all session state to disk with enterprise-grade error handling."""
        try:
            state = {
                "selected_symbol": self.selected_symbol,
                "selected_strategy": self.selected_strategy_var.get(),
                "is_running": self.is_running,
                "audio_enabled": self.audio_alerts_enabled,
                "multi_scan_enabled": self.multi_asset_scan_enabled,
                "data_mode": self.data_mode,
                "trading_mode": self.trading_mode,
                "account": {
                    "cash": self.account.cash,
                    "positions": {
                        sym: {
                            "quantity": pos["quantity"],
                            "avg_price": pos["avg_price"],
                            "peak_price": pos.get("peak_price", pos["avg_price"]),
                            "stop_loss": pos.get("stop_loss"),
                            "take_profit": pos.get("take_profit"),
                            "strategy": pos.get("strategy", "manual"),
                            "entry_fees": pos.get("entry_fees", 0.0),
                            "trailing_stop": pos.get("trailing_stop", True),
                            "entry_time": pos.get("entry_time").isoformat() if isinstance(pos.get("entry_time"), datetime) else None,
                        }
                        for sym, pos in self.account.positions.items()
                    },
                    "trade_history": [
                        {**t, "timestamp": t.get("timestamp").isoformat() if isinstance(t.get("timestamp"), datetime) else t.get("timestamp")}
                        for t in self.account.trade_history
                    ],
                },
                "risk_settings": {
                    "risk_per_trade_pct": self.risk_manager.risk_per_trade_pct,
                    "trailing_stop_pct": self.account.trailing_stop_pct,
                    "default_stop_loss_pct": self.account.default_stop_loss_pct,
                    "default_take_profit_pct": self.account.default_take_profit_pct,
                },
                "guard": {
                    "max_daily_loss_pct": self.guard.max_daily_loss_pct,
                    "max_drawdown_pct": self.guard.max_drawdown_pct,
                    "halted": self.guard.halted,
                    "halt_reason": self.guard.halt_reason,
                    "day_key": self.guard.day_key,
                    "day_start_equity": self.guard.day_start_equity,
                },
                "learner": {
                    "total_trades": self.learner.total_trades,
                    "total_wins": self.learner.total_wins,
                    "total_pnl": self.learner.total_pnl,
                    "performance_score": self.learner.performance_score,
                },
                "timestamp": datetime.now().isoformat(),
            }
            # Atomic write: write to a temp file then rename, so a crash mid-write
            # can never corrupt the session state on disk.
            tmp_path = self.state_path.with_name(self.state_path.name + ".tmp")
            tmp_path.write_text(json.dumps(state, indent=2, default=_json_default), encoding="utf-8")
            os.replace(tmp_path, self.state_path)
            logger.debug("Session state auto-saved successfully")
        except PermissionError as e:
            logger.error(f"Permission denied saving session state: {e}")
        except json.JSONEncodeError as e:
            logger.error(f"Failed to encode session state: {e}")
        except Exception as e:
            logger.error(f"Failed to auto-save session state: {e}")

    def _load_session_state(self):
        """Load saved session state on startup with enterprise-grade error handling."""
        try:
            if not self.state_path.exists():
                self._log("No saved session found. Starting fresh.", "SYSTEM")
                return

            state = json.loads(self.state_path.read_text(encoding="utf-8"))

            # Restore UI state
            if state.get("selected_symbol") in self.market_sim.all_symbols:
                self.selected_symbol = state["selected_symbol"]
                self._log(f"Restored selected symbol: {self.selected_symbol}", "SYSTEM")

            if state.get("selected_strategy") in self.strategies:
                self.selected_strategy_var.set(state["selected_strategy"])
                self.active_strategy = state["selected_strategy"]
                self._log(f"Restored strategy: {state['selected_strategy']}", "SYSTEM")

            if "audio_enabled" in state:
                self.audio_alerts_enabled = state["audio_enabled"]

            if "multi_scan_enabled" in state:
                self.multi_asset_scan_enabled = state["multi_scan_enabled"]

            self.data_mode = "real" if state.get("data_mode") == "real" else "simulated"
            self.data_mode_var.set("REAL" if self.data_mode == "real" else "SIM")
            if self.data_mode == "real":
                self.current_prices = {}
                self.real_market_data.connect()
            self.trading_mode = "paper"
            self.trading_mode_var.set("PAPER")
            self.trading_mode_pill.configure(text="PAPER ONLY")

            # Restore account state
            if "account" in state:
                acc = state["account"]
                self.account.cash = acc.get("cash", 25000.0)
                if "positions" in acc:
                    for sym, pos_data in acc["positions"].items():
                        if "entry_time" in pos_data and pos_data["entry_time"]:
                            pos_data["entry_time"] = datetime.fromisoformat(pos_data["entry_time"])
                        self.account.positions[sym] = pos_data
                if "trade_history" in acc:
                    for tr in acc["trade_history"]:
                        if isinstance(tr.get("timestamp"), str):
                            try:
                                tr["timestamp"] = datetime.fromisoformat(tr["timestamp"])
                            except (ValueError, TypeError):
                                pass
                    self.account.trade_history = acc["trade_history"]
                self._log(f"Restored account with {len(self.account.positions)} positions and {len(self.account.trade_history)} orders", "SYSTEM")

            # Restore risk settings
            if "risk_settings" in state:
                rs = state["risk_settings"]
                self.risk_manager.risk_per_trade_pct = rs.get("risk_per_trade_pct", 0.02)
                self.account.trailing_stop_pct = rs.get("trailing_stop_pct", 0.02)
                self.account.default_stop_loss_pct = rs.get("default_stop_loss_pct", 0.03)
                self.account.default_take_profit_pct = rs.get("default_take_profit_pct", 0.06)

            # Restore guard state
            if "guard" in state:
                g = state["guard"]
                self.guard.max_daily_loss_pct = g.get("max_daily_loss_pct", 0.04)
                self.guard.max_drawdown_pct = g.get("max_drawdown_pct", 0.12)
                self.guard.day_key = g.get("day_key")
                self.guard.day_start_equity = g.get("day_start_equity")
                if g.get("halted"):
                    self.guard.halted = True
                    self.guard.halt_reason = g.get("halt_reason", "Unknown")
                    self._log(f"Guard was halted: {self.guard.halt_reason}", "WARNING")

            # Restore learner state
            if "learner" in state:
                l = state["learner"]
                self.learner.total_trades = l.get("total_trades", 0)
                self.learner.total_wins = l.get("total_wins", 0)
                self.learner.total_pnl = l.get("total_pnl", 0.0)
                self.learner.performance_score = l.get("performance_score", 0.5)
                self.learner._update_performance_score()

            self._log(f"Session restored from {state.get('timestamp', 'unknown')}", "SYSTEM")
            self.cfg_audio_var.set(self.audio_alerts_enabled)
            self.cfg_multiscan_var.set(self.multi_asset_scan_enabled)
            self.cfg_learn_var.set(self.learner.enabled)
            for entry, value in ((self.cfg_risk_pct, self.risk_manager.risk_per_trade_pct),
                                 (self.cfg_sl_pct, self.account.default_stop_loss_pct),
                                 (self.cfg_tp_pct, self.account.default_take_profit_pct),
                                 (self.cfg_trail_pct, self.account.trailing_stop_pct),
                                 (self.cfg_daily_loss, self.guard.max_daily_loss_pct),
                                 (self.cfg_max_dd, self.guard.max_drawdown_pct),
                                 (self.cfg_min_conf, self.learner.min_confidence)):
                entry.delete(0, "end")
                entry.insert(0, f"{value * 100:g}")
            self._sync_pilot_buttons()

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode session state (corrupted): {e}")
            self._log("Session state corrupted. Starting fresh.", "WARNING")
        except Exception as e:
            logger.warning(f"Failed to load session state: {e}")
            self._log("Could not restore previous session. Starting fresh.", "WARNING")

    def _schedule_auto_save(self):
        """Schedule periodic auto-save."""
        self._auto_save_timer += 1
        if self._auto_save_timer >= 12:  # Save every 6 seconds (12 * 0.5s ticks)
            self._auto_save_timer = 0
            self._save_session_state()
        self.root.after(500, self._schedule_auto_save)

    def _on_closing(self):
        """Handle window close event with graceful shutdown."""
        self._shutdown.set()
        try:
            self._log("Shutting down Loki Terminal...", "SYSTEM")
            self._save_session_state()
            self.learner.save()
            self._log("Session saved. Goodbye!", "SYSTEM")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    try:
        app = ModernTradingInterface()
        app.run()
    except Exception as e:
        logger.critical(f"Terminal crash: {e}", exc_info=True)
        print(f"Fatal error running LOKI Terminal: {e}")


if __name__ == "__main__":
    main()
