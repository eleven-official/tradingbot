# 🤖 Loki AI Trading Bot - Quick Start Guide

Welcome to **Loki**, your enterprise-grade AI-powered trading platform! This guide will get you up and running in minutes.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [First Launch](#first-launch)
5. [Understanding the Interface](#understanding-the-interface)
6. [Paper Trading (Safe Mode)](#paper-trading-safe-mode)
7. [Live Trading (Real Money)](#live-trading-real-money)
8. [Joshua's Strategy](#joshuas-strategy)
9. [AI Training & Reliability](#ai-training--reliability)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Features](#advanced-features)

---

## ✅ Prerequisites

Before you begin, ensure you have:

- **Python 3.8 or higher** (Python 3.10 or 3.11 recommended)
  - Check version: `python --version`
  - Download from: https://python.org

- **Alpaca Account** (Free paper trading account)
  - Sign up: https://alpaca.markets
  - Get API keys from dashboard

- **Internet Connection** (for market data)

- **Windows 10/11** (this guide is Windows-specific)

---

## 🚀 Installation

### Option 1: Quick Install (Recommended)

1. **Open PowerShell** in the project directory
2. **Run the launcher** (it will auto-install dependencies):
   ```powershell
   .\LAUNCH_LOKI.bat
   ```

The launcher will:
- Check Python version
- Install missing dependencies automatically
- Verify your .env configuration
- Launch the application

### Option 2: Manual Install

1. **Create virtual environment** (recommended):
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Verify installation**:
   ```powershell
   python TEST_LOKI_SYSTEM.py
   ```

---

## ⚙️ Configuration

### 1. Create .env File

Create a file named `.env` in the project root with your Alpaca credentials:

```env
# Alpaca API Configuration
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here

# Paper Trading (Safe - Uses fake money)
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Live Trading (Real money - Use with caution!)
# ALPACA_BASE_URL=https://api.alpaca.markets
```

### 2. Get Your Alpaca Keys

1. Go to https://alpaca.markets
2. Sign up for a free account
3. Navigate to **Dashboard → API Keys**
4. Generate new API keys
5. Copy the **API Key** and **Secret Key** into your `.env` file

⚠️ **Important**: Start with paper trading! Keep `ALPACA_BASE_URL` pointed to `paper-api.alpaca.markets`

---

## 🎯 First Launch

### Launch the Application

**Method 1: Use the Launcher (Easiest)**
```powershell
.\LAUNCH_LOKI.bat
```

**Method 2: Direct Python**
```powershell
python -m loki.ui.main_app
```

### What to Expect

1. **Splash Screen**: Shows "LOKI AI Trading Platform"
2. **Loading**: Initializes modules and connects to Alpaca
3. **Main Window**: Opens the full trading interface

If you see errors:
- Check `.env` file exists and has correct credentials
- Verify internet connection
- Check logs in `logs/loki_YYYYMMDD.log`

---

## 🖥️ Understanding the Interface

### Top Section: Trading Mode & Account Info

```
┌─────────────────────────────────────────────┐
│ 📄 Paper Trading | 🔴 LIVE Trading          │
│ Portfolio: $125,450  Cash: $25,000          │
└─────────────────────────────────────────────┘
```

- **Paper Trading Button** (Green): Safe mode with fake money
- **LIVE Trading Button** (Red): Real money mode (requires confirmation)
- **Account Metrics**: Real-time portfolio value, cash, buying power

### Middle Section: Charts & AI

```
┌──────────────────────┬─────────────┐
│  Candlestick Chart   │   AI Status │
│                      │             │
│  [Interactive]       │ 🤖 Active   │
│  Zoom, Pan           │ Signal: BUY │
│  Moving Averages     │ Conf: 87%   │
└──────────────────────┴─────────────┘
```

- **Left**: Professional candlestick chart with technical indicators
  - **Zoom**: Mouse wheel
  - **Pan**: Click and drag
  - **Indicators**: EMA 9, 21, 50, 200
  
- **Right**: AI Trading Assistant
  - **Latest Signal**: BUY/SELL/HOLD with confidence
  - **Reasoning**: Why the AI made this decision
  - **Reliability Score**: AI accuracy (target: 80%+)

### Bottom Section: Tabs

- **📊 Positions**: Open positions and P&L
- **📋 Orders**: Order history and status
- **📈 Performance**: Trading metrics and statistics

---

## 🛡️ Paper Trading (Safe Mode)

**Paper trading uses fake money** - perfect for testing strategies without risk!

### How to Use Paper Trading

1. **Verify Mode**: Ensure "📄 Paper Trading" button is highlighted green
2. **Check Status**: Should say "Mode: Paper Trading (Safe)"
3. **Trade Freely**: All trades use simulated money
4. **Learn the System**: Practice before going live

### What You Can Do

✅ Test strategies with real market data  
✅ Learn the interface safely  
✅ Validate AI signals  
✅ Build confidence  
✅ No financial risk  

### Limitations

⚠️ Orders may not reflect real market conditions perfectly  
⚠️ No slippage simulation  
⚠️ Instant fills (unrealistic for large orders)  

---

## 💰 Live Trading (Real Money)

⚠️ **WARNING**: Live trading uses **REAL MONEY**. Only proceed when you're confident!

### Prerequisites for Live Trading

Before switching to live mode:

1. ✅ **Test thoroughly** in paper trading
2. ✅ **Understand the strategy** completely
3. ✅ **Set risk limits** in your account
4. ✅ **Start small** - don't risk money you can't afford to lose
5. ✅ **Monitor constantly** - automation doesn't mean "set and forget"

### How to Switch to Live Trading

1. **Update .env** (IMPORTANT):
   ```env
   ALPACA_BASE_URL=https://api.alpaca.markets
   ```

2. **Restart the application**

3. **Click "🔴 LIVE Trading"** button

4. **Confirm the warning dialog**:
   ```
   ⚠️ You are about to switch to LIVE trading mode.
   This will use REAL MONEY!
   
   Continue? [Yes] [No]
   ```

5. **Status changes** to: "Mode: 🔴 LIVE TRADING (Real Money!)"

### Safety Features

- ⚠️ Confirmation dialog before switching
- ⚠️ Visual warnings (red color, bold text)
- ⚠️ All trades logged to file
- ⚠️ Account limits enforced by Alpaca

### Emergency Stop

To stop all trading immediately:
1. Click "📄 Paper Trading" button (switches back to paper)
2. Close the application
3. Cancel orders manually in Alpaca dashboard

---

## 🎓 Joshua's Strategy

**Joshua's Strategy** is Loki's flagship multi-indicator trading strategy, designed to be the best.

### What Makes It Special

Joshua's Strategy combines **7 powerful indicators**:

1. **EMA Trend Analysis** (9, 21, 50, 200 EMAs)
   - Identifies trend direction and strength
   - Golden/Death cross detection

2. **RSI (Relative Strength Index)**
   - Overbought/oversold conditions
   - Momentum confirmation

3. **MACD (Moving Average Convergence Divergence)**
   - Trend reversals
   - Momentum shifts

4. **Volume Analysis**
   - Confirms price movements
   - Detects institutional activity

5. **ADX (Average Directional Index)**
   - Measures trend strength
   - Filters choppy markets

6. **Support & Resistance**
   - Key price levels
   - Entry/exit points

7. **Market Structure**
   - Higher highs/lows (uptrend)
   - Lower highs/lows (downtrend)

### How It Works

```
Each indicator votes: BUY (+), SELL (-), or NEUTRAL (0)
Scores are weighted and combined
Final signal: BUY, SELL, or HOLD with confidence %
```

Example:
- EMA: +1 (bullish alignment)
- RSI: +0.5 (slightly oversold)
- MACD: +1 (bullish crossover)
- Volume: +1 (high confirmation)
- ADX: +1 (strong trend)
- S&R: +0.5 (near support)
- Structure: +1 (higher highs)

**Total**: +6 out of 7 = **85% confidence BUY**

### Using Joshua's Strategy

The strategy runs automatically on the selected symbol. To use it:

1. **Select Symbol**: Choose from the dropdown (default: AAPL)
2. **AI Analyzes**: Joshua's Strategy evaluates all indicators
3. **Signal Generated**: BUY/SELL/HOLD with confidence
4. **Review Reasoning**: Check what indicators contributed
5. **Execute Trade**: Manual or automatic (if configured)

---

## 🤖 AI Training & Reliability

Loki's AI learns from market data to improve predictions. The target reliability is **80%+**.

### What is Reliability Score?

The **reliability score** measures how often the AI's predictions are correct:

- **80-100%**: Excellent - High confidence in signals
- **70-79%**: Good - Acceptable for trading
- **60-69%**: Fair - Use with caution
- **Below 60%**: Poor - Needs more training

### How to Train the AI

**Option 1: Quick Training** (in code)
```python
from loki.ml import quick_train
from loki.data import get_stock_data

# Get training data
df = get_stock_data("SPY", start_date, end_date)

# Train AI
result = quick_train(df)
print(f"Reliability: {result.reliability_score:.1f}%")
```

**Option 2: Advanced Training**
```python
from loki.ml import AITrainer
from loki.strategies import JoshuasStrategy

trainer = AITrainer()
strategy = JoshuasStrategy()

result = trainer.train_strategy(
    df=training_data,
    strategy=strategy,
    validation_split=0.2  # 80/20 train/test
)
```

### Improving Reliability

To achieve 80%+ reliability:

1. **More Data**: Train on 6-12 months of data
2. **Multiple Symbols**: Diversify training data
3. **Walk-Forward Validation**: Test on unseen data
4. **Parameter Tuning**: Optimize indicator settings
5. **Market Conditions**: Train on various market regimes

### Current Reliability

Check the AI status widget in the interface:
```
AI Reliability: [████████░░] 83.5%
```

If below 80%, retrain with more recent data.

---

## 🔧 Troubleshooting

### Problem: "PyQt6 required" Error

**Solution**:
```powershell
pip install PyQt6 pyqtgraph
```

### Problem: "Missing .env file"

**Solution**:
1. Create `.env` file in project root
2. Add Alpaca credentials (see [Configuration](#configuration))
3. Restart application

### Problem: "Could not connect to Alpaca"

**Possible Causes**:
- ❌ Wrong API keys
- ❌ Internet connection issue
- ❌ Alpaca service down

**Solution**:
1. Verify API keys in `.env`
2. Check internet connection
3. Visit https://alpaca.markets/status

### Problem: "No data for symbol"

**Possible Causes**:
- ❌ Invalid symbol
- ❌ Market closed
- ❌ Data provider issue

**Solution**:
1. Verify symbol is correct (e.g., "AAPL" not "Apple")
2. Check if market is open
3. Try different symbol

### Problem: "AI Reliability Below 80%"

**Solution**:
1. Train on more data (6+ months)
2. Use recent data (last 6 months)
3. Retrain periodically
4. Check strategy parameters

### Check Logs

All errors are logged to `logs/loki_YYYYMMDD.log`:

```powershell
# View today's log
notepad logs\loki_20261002.log

# View latest errors
Select-String -Path logs\*.log -Pattern "ERROR" | Select-Object -Last 10
```

---

## 🚀 Advanced Features

### Custom Indicators

Add your own indicators to `loki/strategies/`:

```python
from loki.core.strategy_interface import StrategyInterface

class MyCustomStrategy(StrategyInterface):
    def analyze(self, data):
        # Your logic here
        return signal
```

### Backtesting

Test strategies on historical data:

```python
from loki.backtest import BacktestEngine

engine = BacktestEngine()
results = engine.run_backtest(
    strategy=JoshuasStrategy(),
    data=historical_data,
    initial_capital=100000
)
```

### API Integration

Use Loki's modules programmatically:

```python
# Get market data
from loki.data import get_stock_data
df = get_stock_data("AAPL", start, end)

# Run strategy
from loki.strategies import run_joshuas_strategy
signal = run_joshuas_strategy(df)

# Execute trade
from loki.trading import get_alpaca_trader
trader = get_alpaca_trader()
trader.place_market_order("AAPL", 10, "buy")
```

---

## 📊 System Testing

Verify everything works before trading:

```powershell
# Run comprehensive system test
python TEST_LOKI_SYSTEM.py
```

Expected output:
```
========================================
LOKI TRADING BOT - SYSTEM TEST
========================================

[TEST 1] Testing Imports
  ✓ PASS Import alpaca-py
  ✓ PASS Import yfinance
  ...

[TEST 8] Testing Error Handling
  ✓ PASS Invalid symbol handling

========================================
TEST SUMMARY
========================================
Total Tests: 20
Passed: 20
Failed: 0
Pass Rate: 100.0%

✓ SYSTEM IS PRODUCTION READY
```

---

## 📚 Additional Resources

- **Full Documentation**: See `COMPLETE_SYSTEM_OVERVIEW.md`
- **Alpaca Docs**: https://alpaca.markets/docs
- **Support**: Check logs first, then review code
- **Updates**: Keep dependencies updated: `pip install --upgrade -r requirements.txt`

---

## ⚖️ Disclaimer

**IMPORTANT LEGAL NOTICE**:

This software is provided for educational purposes only. Trading involves substantial risk of loss. You are solely responsible for:

- ✅ Understanding the risks
- ✅ Testing thoroughly in paper mode
- ✅ Setting appropriate risk limits
- ✅ Monitoring your positions
- ✅ Complying with local regulations

**Past performance does not guarantee future results.**  
**The developers are not liable for any financial losses.**  
**Use at your own risk.**

---

## 🎉 You're Ready!

You now have everything you need to start using Loki. Here's your checklist:

- [ ] Python 3.8+ installed
- [ ] Dependencies installed
- [ ] .env configured with Alpaca keys
- [ ] System test passed
- [ ] Understand paper vs live trading
- [ ] Know Joshua's Strategy
- [ ] Read safety warnings

**Start with paper trading and build confidence before going live!**

Good luck, and may your trades be profitable! 🚀📈

---

*Last Updated: 2026-10-02*  
*Version: 1.0.0 Production*
