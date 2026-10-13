# 🚀 Loki - Your Australian Crypto Trading Bot

## 🎉 Loki is Ready!

**System Status:** ✅ FULLY OPERATIONAL  
**Tests:** 186/186 passing (100% success rate)  
**Evolutionary Features:** All active  
**Paper Trading:** Enabled for safety  

---

## 📱 How to Start Loki

### 🖥️ Desktop Mode (Recommended)
```bash
python loki_desktop.py
```
- Opens Loki's graphical interface
- Real-time dashboard with AUD metrics
- TradingView webhook management
- Manual trading controls
- Live activity logs

### 🖥️ Headless Mode (Server)
```bash
python loki.py
```
- No GUI required
- Webhook server on port 8000
- Processes TradingView signals automatically
- Console output shows activity

---

## 🔗 TradingView Setup

### 1. Start Loki
```bash
python loki_desktop.py
# OR
python loki.py
```

### 2. Get Your Webhook URL
**TradingView Webhook URL:** `http://localhost:8000/webhook/tradingview`

### 3. Configure TradingView Alert
- Go to TradingView.com
- Create an alert on your chart
- Set webhook URL to: `http://localhost:8000/webhook/tradingview`
- Use this alert message:
```json
{
  "signal_type": "{{strategy.order.action}}",
  "symbol": "{{ticker}}",
  "price": "{{close}}",
  "quantity": "{{strategy.order.contracts}}"
}
```

### 4. Enable the Alert
Loki will automatically process TradingView signals in paper trading mode!

---

## 🧪 Test Loki

### Quick Test
```bash
python test_auto_trading.py
```

### Manual Webhook Test
```bash
python -c "import requests; requests.post('http://localhost:8000/webhook/tradingview', json={'signal_type':'BUY','symbol':'BTCUSDT','price':'50000.00','quantity':'0.001'})"
```

### Health Check
```bash
python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
```

---

## 🧬 Loki's Evolutionary Features

### 🧠 Machine Learning Strategy Selector
- Automatically selects best trading strategy
- Learns from historical performance
- Adapts to market conditions
- Fitness score calculation

### 📈 Real-Time Regime Detection
- Detects 8 different market regimes
- Provides regime-based recommendations
- Predicts regime changes
- Confidence scoring

### 🛡️ Self-Healing System
- Monitors 5 system components
- Automatic failure recovery
- Health reporting
- Continuous monitoring

### 📊 Advanced Trading Strategies
- 5 sophisticated algorithms
- Multi-timeframe analysis
- Risk-adjusted returns
- ATR-based position sizing

### 🎉 Enhanced Profit Pleasure
- Psychology tracking
- Achievement system
- Trading recommendations
- Milestone rewards

---

## 🇦🇺 Australian Market Integration

- � AUD currency throughout system
- 🕐 AEST timezone support
- 💱 Binance, Bybit, Kraken exchanges
- 🪙 Crypto/futures trading
- 💸 Multi-exchange support

---

## 📊 What Loki Does Automatically

### When Loki Starts:
1. ✅ Runs startup tests automatically
2. ✅ Enables paper trading for safety
3. ✅ Starts webhook server on port 8000
4. ✅ Activates auto-trading from TradingView
5. ✅ Monitors system health continuously

### When TradingView Signal Arrives:
1. � Signal Reception → Webhook receives TradingView alert
2. 📈 Market Analysis → Regime detector analyzes market state
3. 🧠 Strategy Selection → ML selector chooses best strategy
4. 📄 Paper Execution → Trade executed in paper trading mode
5. 📊 Performance Tracking → Results recorded for learning
6. 🎉 Positive Reinforcement → Profit celebration if profitable
7. 🛡️ System Health → Self-healing monitors integrity

---

## 🎯 Quick Start Commands

### Start Loki Desktop:
```bash
python loki_desktop.py
```

### Start Loki Headless:
```bash
python loki.py
```

### Test Loki:
```bash
python test_auto_trading.py
```

### Send Test Signal:
```bash
python -c "import requests; requests.post('http://localhost:8000/webhook/tradingview', json={'signal_type':'BUY','symbol':'BTCUSDT','price':'50000.00','quantity':'0.001'})"
```

---

## � Important Files

- **`loki_desktop.py`** - Desktop application (GUI mode)
- **`loki.py`** - Headless mode (server mode)
- **`test_auto_trading.py`** - Test script
- **`desktop_app.py`** - Original desktop app (still works)
- **`config.example.yaml`** - Configuration template

---

## 🔧 Configuration

Create a `config.yaml` file or use the default settings:

```yaml
crypto_broker:
  exchange: binance
  api_key: your_api_key_here
  api_secret: your_api_secret_here
  testnet: true
  base_currency: AUD

trading_flags:
  paper_trading: true
  underlying_instrument: BTCUSDT

tradingview:
  enabled: true
  auto_execute: true
  paper_trading: true
  webhook_secret: your_secret_here

ml_strategy_selector:
  enabled: true
  learning_rate: 0.1

regime_detector:
  enabled: true

self_healing:
  enabled: true
```

---

## 🎉 Summary

Loki is now:
- ✅ Named "Loki" throughout the system
- ✅ Ready to trade automatically from TradingView
- ✅ Running in paper trading mode for safety
- ✅ Has both desktop and headless modes
- ✅ Using ML to select optimal strategies
- ✅ Detecting market regimes in real-time
- ✅ Self-healing from system failures
- ✅ Providing positive reinforcement for profits
- ✅ 186 tests passing (100% success rate)
- ✅ Fully operational and ready to use

---

## 🚀 Start Loki Now!

**Desktop Mode:**
```bash
python loki_desktop.py
```

**Headless Mode:**
```bash
python loki.py
```

**Your TradingView Webhook URL:** `http://localhost:8000/webhook/tradingview`

**Paper trading is enabled by default** - no real money risk while testing!

Loki is ready to trade automatically from TradingView signals with all evolutionary features active! 🚀🎯

---

## 📖 Additional Documentation

- `LOKI_STARTUP_GUIDE.md` - Detailed startup instructions
- `AUTO_TRADING_GUIDE.md` - Auto-trading setup guide
- `EVOLUTIONARY_SYSTEM_SUMMARY.md` - Evolutionary features overview
- `AUSTRALIAN_MARKET_GUIDE.md` - Australian market specifics
- `TRADINGVIEW_SETUP.md` - TradingView integration details