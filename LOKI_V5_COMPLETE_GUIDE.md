# 🚀 LOKI NEURAL TRADING TERMINAL v5.0 - Complete Guide

## 🎉 What's New in v5.0

### Major Upgrades:
- ✅ **Auto-Save Functionality** - Session state saves every 6 seconds automatically
- ✅ **Session Persistence** - Restores positions, settings, and strategy on restart
- ✅ **Windows Start Menu Integration** - Install LOKI as a searchable Windows app
- ✅ **Enhanced Search** - Search with visual highlighting in watchlist
- ✅ **Trade Export** - Export all trade history to CSV for analysis
- ✅ **Advanced Analytics** - Avg Win, Avg Loss, and R:Multiple metrics
- ✅ **Enhanced Launcher** - Automatic dependency checking and error handling
- ✅ **Graceful Shutdown** - Proper save on window close
- ✅ **Self-Improvement Engine** - Learns from closed trades and adapts
- ✅ **Audio Alerts** - Windows-native sound effects for trades
- ✅ **Windows Taskbar Integration** - Proper app grouping and pinning

---

## 🚀 Quick Start

### Option 1: Double-Click Launcher (Easiest)
```bash
# Double-click this file:
LOKI_LAUNCHER.bat
```

### Option 2: Windows Start Menu (After Installation)
1. Right-click `install_start_menu_shortcut.ps1`
2. Select "Run with PowerShell"
3. Click "Yes" if prompted
4. Search for "LOKI" in Windows Start menu
5. Click "LOKI Neural Terminal"

### Option 3: Command Line
```bash
cd C:\Users\MatheJ3\OneDrive - CEDR\tradingbot
python loki_desktop.py
```

---

## 🆕 New Features

### 1. Auto-Save & Session Persistence
- **What it does:** Automatically saves your entire session every 6 seconds
- **What gets saved:**
  - Selected symbol and strategy
  - All open positions
  - Account cash and settings
  - Risk management parameters
  - Guard halt status
- **How it works:**
  - State saved to `state/loki_session.json`
  - Automatically restored on next launch
  - If no saved state exists, starts fresh
  - Saves on graceful shutdown

### 2. Windows Start Menu Integration
- **Install:**
  ```powershell
  # Right-click and run with PowerShell:
  install_start_menu_shortcut.ps1
  ```
- **Use:**
  - Press Windows key
  - Type "LOKI"
  - Press Enter to launch
- **Uninstall:**
  - Run "Uninstall LOKI" from Start Menu
  - Or run `uninstall_start_menu_shortcut.ps1`

### 3. Enhanced Search
- Type in the search bar in the watchlist
- Matching symbols highlight in blue
- Non-matching symbols hide
- Clear search to show all symbols
- Category filter still works

### 4. Trade Export
- Go to "Order History" tab
- Click "📥 Export Trades to CSV"
- Choose save location
- CSV includes: Timestamp, Symbol, Action, Quantity, Price, P&L, Strategy, Reason

### 5. Advanced Analytics
New metrics in "Institutional Analytics" tab:
- **Avg Win** - Average profit per winning trade
- **Avg Loss** - Average loss per losing trade
- **Avg R:Multiple** - Average risk-to-reward ratio

### 6. Enhanced Launcher
- Checks if Python is installed
- Verifies all dependencies
- Auto-installs missing packages
- Provides helpful error messages
- Checks for missing files

---

## 🎨 Interface Overview

### Header Bar
- **LOKI v5 PAPER** - Branding and version
- **SIMULATED MARKET** - Mode indicator
- **Status Badge** - Trading status (Standby/Trading/Halted)
- **Equity/P&L/Win Rate** - Real-time metrics
- **Strategy Selector** - Choose active strategy
- **LET AI TRADE** - Toggle autonomous trading
- **⛔ LIQUIDATE ALL** - Emergency stop

### Sidebar - Watchlist
- **Market Watchlist** - All tradable symbols
- **Category Filter** - ALL/CRYPTO/STOCKS/INDICES
- **Search Bar** - Filter symbols instantly
- **Symbol Cards** - Click to view chart
- **Price/Change** - Real-time updates

### Center - Chart
- **Price Chart** - Candlestick with EMA/BB/RSI
- **Timeframe Selector** - 1m/5m/15m/1h
- **Overlay Toggles** - EMA, Bollinger Bands, RSI
- **Trade Markers** - Shows buy/sell executions

### Right - AI Trading Deck
- **AI Pilot** - Autonomous trading control
- **AI Confluence Radar** - Signal strength meter
- **Direct Execution** - Manual trading controls
- **Risk/Reward Preview** - Live calculation

### Bottom - Operations Deck
- **Active Positions** - Open trades with P&L
- **AI Scanner Leaderboard** - Multi-asset scan results
- **Quant Backtester** - Historical strategy testing
- **Order History** - Complete trade log (with export)
- **Institutional Analytics** - Advanced metrics
- **Bot & Risk Settings** - Configuration
- **Audit Logs** - System messages

---

## 🧠 Trading Strategies

### 1. ML Ensemble (Default - Recommended)
- Combines all 4 strategies
- Adapts to market regime
- Self-learning weights
- **Best for:** All market conditions

### 2. Momentum
- EMA 12/26 crossover
- MACD histogram
- RSI confirmation
- **Best for:** Trending markets

### 3. Mean Reversion
- Bollinger Bands
- Z-score extreme detection
- RSI oversold/overbought
- **Best for:** Range-bound markets

### 4. Breakout
- 20-bar channel breakout
- Volume surge confirmation
- Prior-bar correct calculation
- **Best for:** Volatile markets

### 5. Volatility Surface
- Volatility compression squeeze
- VWAP expansion
- **Best for:** High-volatility environments

---

## ⚙️ Settings & Configuration

### Risk Settings (Bot & Risk Settings Tab)
- **Risk Per Trade (%)** - Position sizing (default: 2%)
- **Default Stop Loss (%)** - Exit level (default: 3%)
- **Default Take Profit (%)** - Target level (default: 6%)
- **Trailing Stop (%)** - Trailing stop distance (default: 2%)
- **Daily Loss Halt (%)** - Daily loss limit (default: 4%)
- **Max Drawdown Halt (%)** - Portfolio drawdown limit (default: 12%)
- **Min AI Conviction (%)** - Minimum signal confidence (default: 70%)

### Toggles
- **Audio Execution Chimes** - Sound effects for trades
- **Scan All Assets** - Multi-asset autonomous trading
- **Self-Learn From Closed Trades** - Auto-tune weights

### Apply Settings
- Click "Apply Configuration" to save
- Settings apply immediately
- Auto-saved to session state

---

## 🎯 Trading Modes

### Manual Trading
1. Select symbol from watchlist
2. Enter quantity (or use risk buttons)
3. Optional: Set stop loss / take profit
4. Click BUY or SELL
5. Trade executes instantly

### AI Pilot (Autonomous)
1. Click "LET AI TRADE BY ITSELF"
2. AI scans all assets
3. Executes when conviction ≥ 70%
4. Self-learns from results
5. Auto-manages risk limits

### Emergency Stop
- Click "⛔ LIQUIDATE ALL"
- Closes all positions
- Halts auto-trading
- Use in emergencies only

---

## 📊 Session Persistence

### What's Saved Automatically:
- ✅ Selected symbol
- ✅ Active strategy
- ✅ Open positions (with entry prices, SL/TP)
- ✅ Account cash
- ✅ Risk settings
- ✅ Guard halt status
- ✅ AI pilot state

### What's Not Saved:
- ❌ Historical price data (simulated fresh each run)
- ❌ Trade history (export to CSV to keep)
- ❌ Equity curve charts

### When It Saves:
- Every 6 seconds (auto-save)
- On window close (graceful shutdown)
- On settings apply

### Reset Session:
- Delete `state/loki_session.json`
- Restart application
- Starts fresh with $25,000

---

## 💡 Pro Tips

### For Best Results:
1. **Start with AI Pilot** - Let it learn first
2. **Monitor scanner** - Watch conviction scores
3. **Check analytics** - Review avg win/loss
4. **Export trades** - Analyze in Excel/Python
4. **Use risk buttons** - 1%/2%/5% risk sizing
5. **Set SL/TP** - Always protect positions
6. **Watch drawdown** - Stop if > 10%
7. **Learn from results** - Self-improvement adapts

### Strategy Selection:
- **Trending** → ML Ensemble or Momentum
- **Ranging** → Mean Reversion
- **Volatile** → Volatility Surface or Breakout
- **Unsure** → ML Ensemble (adapts automatically)

### Risk Management:
- Start with 1-2% risk per trade
- Use stop losses (automatic in strategies)
- Monitor drawdown constantly
- Use emergency stop if needed
- Keep leverage low

---

## 🔧 Troubleshooting

### Application won't start:
```bash
# The launcher now handles this automatically
# It checks Python and dependencies
# Follow the on-screen error messages
```

### Missing dependencies:
```bash
pip install customtkinter matplotlib pandas numpy
```

### Session not restoring:
- Check `state/loki_session.json` exists
- Verify file is not corrupted
- Delete file to start fresh

### Search not working:
- Try clearing the search bar
- Check spelling (case-insensitive)
- Ensure symbol exists in watchlist

### Auto-save not working:
- Check `state/` folder exists
- Verify write permissions
- Check logs for errors

### Start menu shortcut not appearing:
- Run PowerShell as Administrator
- Re-run `install_start_menu_shortcut.ps1`
- Check Windows Start menu search

---

## 🎯 What Makes v5.0 Better

### vs. v4.0:
- ✅ Auto-save every 6 seconds (new)
- ✅ Session persistence (new)
- ✅ Windows Start menu integration (new)
- ✅ Search highlighting (new)
- ✅ Trade export to CSV (new)
- ✅ Advanced analytics (new)
- ✅ Enhanced launcher (new)
- ✅ Graceful shutdown (new)
- ✅ Self-improvement engine (enhanced)
- ✅ Audio alerts (enhanced)
- ✅ Taskbar integration (enhanced)

### Key Improvements:
1. **Auto-Save** - Never lose your session
2. **Persistence** - Restore exactly where you left off
3. **Start Menu** - Searchable like a real app
4. **Export** - Analyze trades externally
5. **Analytics** - More metrics for better decisions
6. **Reliability** - Better error handling
7. **Convenience** - Auto-install dependencies

---

## 📖 File Structure

```
tradingbot/
├── loki_desktop.py              # Main application
├── LOKI_LAUNCHER.bat            # Enhanced launcher
├── install_start_menu_shortcut.ps1  # Install to Start menu
├── uninstall_start_menu_shortcut.ps1 # Remove from Start menu
├── state/
│   ├── loki_session.json        # Auto-saved session
│   └── loki_self_improve.json   # Learning state
├── loki_terminal.log            # Application logs
└── .env.alpaca                  # Alpaca API keys (your config)
```

---

## 🚀 Installation Guide

### Step 1: Verify Python
```bash
python --version
# Should be 3.10 or higher
```

### Step 2: Install Dependencies
```bash
# The launcher does this automatically
# Or manually:
pip install customtkinter matplotlib pandas numpy
```

### Step 3: Run Application
```bash
# Double-click:
LOKI_LAUNCHER.bat

# Or from Start menu (after installation):
# Search for "LOKI"
```

### Step 4: (Optional) Install to Start Menu
```powershell
# Right-click and run with PowerShell:
install_start_menu_shortcut.ps1
```

---

## 🎉 Ready to Use!

**LOKI Neural Trading Terminal v5.0 is fully operational with:**
- ✅ Auto-save every 6 seconds
- ✅ Session persistence on restart
- ✅ Windows Start menu integration
- ✅ Enhanced search with highlighting
- ✅ Trade export to CSV
- ✅ Advanced analytics (Avg Win/Loss/R:Multiple)
- ✅ Enhanced launcher with dependency checking
- ✅ Graceful shutdown handling
- ✅ Self-improvement engine
- ✅ Audio alerts
- ✅ Windows taskbar integration
- ✅ $25,000 starting balance
- ✅ Your Alpaca API keys configured

**Start LOKI by double-clicking LOKI_LAUNCHER.bat!** 🚀

---

## 📞 Support

### If something doesn't work:
1. Check `loki_terminal.log` for errors
2. Verify all dependencies are installed
3. Delete `state/` folder to reset
4. Re-run the launcher
5. Check this guide for troubleshooting

### For issues or suggestions:
- Check the logs first
- Verify Python version
- Ensure all packages installed
- Try resetting session state

---

**Happy Trading with LOKI v5.0!** 🎯
