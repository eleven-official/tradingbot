# 🚀 HOW TO LAUNCH LOKI NEURAL TERMINAL v6.0

## Choose Your Launch Method

### ✨ Method 1: SUPER SIMPLE (Recommended)

**Just double-click this file:**
```
START_LOKI.bat
```

That's it! The terminal will open immediately.

---

### 🐍 Method 2: Python Launcher

**Run this command:**
```powershell
python start_neural_terminal.py
```

This automatically installs missing packages and launches the terminal.

---

### 🎯 Method 3: Direct Launch

**Run this command:**
```powershell
python loki_neural_terminal.py
```

Fastest way if you already have all dependencies installed.

---

## 📋 First Time Setup

### 1. Install Python
- Download from: https://python.org
- Version: 3.8 or higher
- Make sure "Add to PATH" is checked during installation

### 2. Create .env File
Create a file named `.env` in this folder with your Alpaca credentials:

```env
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 3. Get Alpaca Keys
1. Sign up at: https://alpaca.markets (free)
2. Go to Dashboard → API Keys
3. Generate new keys
4. Copy them into your `.env` file

---

## 🎮 Quick Start Guide

1. **Launch** the terminal using any method above
2. **Wait** for the welcome dialog
3. **Select** a symbol (AAPL, MSFT, etc.) from the dropdown
4. **Click** "🎓 Train AI" to train on data (first time)
5. **Click** "🔍 Analyze Now" to get a trading signal
6. **Review** the BUY/SELL/HOLD signal and confidence
7. **Trade** manually based on signals (or use Execute button)

---

## ⚠️ Troubleshooting

### "Python not found"
- Install Python from python.org
- Make sure it's added to PATH

### "PyQt6 required"
Run this command:
```powershell
pip install PyQt6 pyqtgraph pandas numpy alpaca-py yfinance
```

### "Missing .env file"
Create `.env` file with your Alpaca API credentials (see step 2 above)

### "Import error: No module named 'loki'"
Make sure you're running the command from the `tradingbot` folder.

### Terminal won't open
1. Check Python version: `python --version` (should be 3.8+)
2. Try Method 2 (auto-installs packages)
3. Check logs in `logs/loki_neural_*.log`

---

## 📝 Files Explained

| File | What It Does |
|------|-------------|
| **START_LOKI.bat** | Simplest launcher (just double-click) |
| **start_neural_terminal.py** | Python launcher with auto-install |
| **loki_neural_terminal.py** | Main application file |
| **launch_loki.py** | Alternative launcher |
| **LAUNCH_NEURAL_TERMINAL.bat** | Batch launcher with checks |

**Use START_LOKI.bat for the easiest experience!**

---

## 🎉 You're Ready!

Your terminal is completely upgraded to v6.0 with:
- ✅ Real market data
- ✅ Professional interface  
- ✅ Joshua's Strategy (7 indicators)
- ✅ AI training (80% target)
- ✅ Live trading support
- ✅ Beautiful charts

**Just double-click START_LOKI.bat and start trading!**

---

*Need more help? See NEURAL_TERMINAL_README.md for the full guide.*
