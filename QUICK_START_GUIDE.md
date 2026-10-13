# 🚀 LOKI - QUICK START GUIDE

## The Fastest Way to Get Started

---

## 📋 Your Situation

You have Loki AI Trading Platform installed, but:
- ❌ Windows Search doesn't find "Loki"
- ❌ Some errors when trying to start
- ✅ Want everything working perfectly

---

## ⚡ INSTANT FIX (2 Minutes)

### Step 1: Run the Ultimate Fix
1. Open File Explorer
2. Go to: `c:\Users\MatheJ3\OneDrive - CEDR\tradingbot`
3. **Double-click: `ULTIMATE_FIX.bat`**
4. Wait 2-3 minutes (it will install everything)
5. When prompted, press **Y** to launch Loki

### Step 2: Restart Computer (for Windows Search)
1. Close Loki if it's running
2. **Restart your computer**
3. After restart, Windows Search will work

### Step 3: Launch Loki
**Use Desktop Shortcut** (Fastest):
- Double-click **"Loki Trading"** icon on your Desktop

**Or use Windows Search**:
- Press **Windows Key**
- Type: **Loki Trading**
- Click: **Loki Trading Platform**

---

## 🎯 All Available Scripts

### 🌟 Main Scripts (Use These)

| Script | What It Does | When to Use |
|--------|--------------|-------------|
| **ULTIMATE_FIX.bat** | Fixes everything, installs all packages | First time, or when broken |
| **START_LOKI.bat** | Launches Loki (clean, no console) | Normal daily use |
| **TEST_LOKI.bat** | Launches Loki with console (debug mode) | When troubleshooting |
| **Desktop Shortcut** | Quick launch from desktop | Daily use (fastest) |

### 🔍 Diagnostic Scripts

| Script | What It Does | When to Use |
|--------|--------------|-------------|
| **RUN_DIAGNOSTICS.bat** | Tests all components, finds problems | Check system health |
| **TEST_WINDOWS_SEARCH.bat** | Tests Windows Search registration | Verify search works |
| **test_ai_agent.py** | Tests AI components specifically | Verify AI is working |

### ⚙️ Setup Scripts

| Script | What It Does | When to Use |
|--------|--------------|-------------|
| **SETUP_AUTO_START.bat** | Make Loki start on login | Want auto-start |
| **FIX_AND_TEST_EVERYTHING.bat** | Alternative fix script | If ULTIMATE_FIX fails |

---

## 🎮 How to Use Each Method

### Method 1: Desktop Shortcut ⭐ (RECOMMENDED)
```
1. Look at your Desktop
2. Find "Loki Trading" icon
3. Double-click it
4. Loki opens!
```
**Pros**: Instant, always works, no waiting  
**Cons**: None!

### Method 2: Windows Search 🔍
```
1. Press Windows Key (⊞)
2. Type: Loki Trading
3. Click: "Loki Trading Platform"
4. Loki opens!
```
**Pros**: Professional, integrated with Windows  
**Cons**: Requires computer restart first

### Method 3: Start Menu 📋
```
1. Click Start Menu
2. Scroll to "L"
3. Find "Loki Trading" folder
4. Click "Loki Trading Platform"
```
**Pros**: Organized, always available  
**Cons**: More clicks than other methods

### Method 4: Debug Mode 🐛
```
1. Double-click TEST_LOKI.bat
2. Console window opens showing progress
3. See any errors that occur
4. Loki opens with debug info
```
**Pros**: See exactly what's happening, troubleshoot issues  
**Cons**: Console window stays open

### Method 5: Command Line 💻
```
cd c:\Users\MatheJ3\OneDrive - CEDR\tradingbot
python launch_loki.py
```
**Pros**: For advanced users, scriptable  
**Cons**: Requires command line knowledge

---

## 🆘 Troubleshooting Decision Tree

### Problem: Windows Search doesn't find "Loki"

**Quick fixes:**
1. Try searching: **"Loki Trading Platform"** (full name)
2. **Restart your computer** (search index needs refresh)
3. **Use Desktop shortcut** instead (works instantly)
4. Run **ULTIMATE_FIX.bat** again

### Problem: "Module not found" or "Import Error"

**Solution:**
```bash
# Run this
Double-click: ULTIMATE_FIX.bat

# Or manually install
pip install PyQt6 pyqtgraph pandas numpy
```

### Problem: Loki doesn't launch

**Diagnostic steps:**
1. Run **TEST_LOKI.bat** (see actual error)
2. Run **RUN_DIAGNOSTICS.bat** (comprehensive check)
3. Follow diagnostic suggestions
4. Run **ULTIMATE_FIX.bat** (repair everything)

### Problem: AI doesn't work

**Solution:**
1. Check `.env` file has your API keys
2. Verify internet connection
3. Run **test_ai_agent.py** to identify issue
4. Check API key validity (OpenAI/Anthropic)

---

## ✅ Quick Health Check

Run these to verify everything works:

```bash
# Check Windows Search registration
Double-click: TEST_WINDOWS_SEARCH.bat

# Check system components
Double-click: RUN_DIAGNOSTICS.bat

# Check AI functionality
python test_ai_agent.py

# Launch Loki
Double-click: START_LOKI.bat
```

All green? You're good to go! 🎉

---

## 📁 File Locations

### Configuration
- **API Keys**: `.env` file
- **Trading Config**: `config.loki.paper.yaml`
- **Broker Settings**: `config.alpaca_paper.yaml`

### Logs
- **Application Logs**: `logs/loki.log`
- **AI Decision Log**: `logs/ai_decisions.log`
- **Trading Log**: `logs/trades.log`

### Data
- **Database**: `loki.db` (SQLite)
- **Cache**: `cache/` folder
- **Backtest Results**: `backtest_results/`

---

## 🎯 Daily Usage Workflow

### Morning Routine
```
1. Double-click "Loki Trading" on Desktop
2. Check AI status (should show "Active")
3. Review overnight AI decisions
4. Check portfolio performance
5. Adjust risk settings if needed
```

### During Trading Day
```
1. Monitor AI decision panel
2. Watch real-time charts
3. Check position sizes
4. Review risk metrics
5. Override AI if needed (emergency only)
```

### Evening Review
```
1. Review day's performance
2. Check AI learning progress
3. Analyze winning/losing trades
4. Adjust strategy parameters
5. Prepare for tomorrow
```

---

## 💡 Pro Tips

### Tip 1: Always Keep TEST_LOKI.bat Handy
When something goes wrong, TEST_LOKI.bat shows you exactly what the error is. No guessing!

### Tip 2: Desktop Shortcut is Your Friend
Don't wait for Windows Search to work. Desktop shortcut is instant and reliable.

### Tip 3: Run Diagnostics Before Trading
Start each week by running RUN_DIAGNOSTICS.bat to catch issues early.

### Tip 4: Monitor AI Consciousness
The consciousness monitor shows when AI is fatigued or biased. Pay attention to it!

### Tip 5: Start with Paper Trading
Always test new strategies in paper trading mode first. Verify AI behaves correctly.

### Tip 6: Regular Updates
Run ULTIMATE_FIX.bat monthly to get latest improvements and bug fixes.

### Tip 7: Backup Your .env File
Your API keys are in .env. Back it up somewhere safe!

---

## 🎓 Learning Path

### Week 1: Getting Started
- [ ] Run ULTIMATE_FIX.bat
- [ ] Configure API keys in .env
- [ ] Launch Loki successfully
- [ ] Understand the interface
- [ ] Watch AI make simulated trades

### Week 2: Understanding the AI
- [ ] Read REVOLUTIONARY_AI_FEATURES.md
- [ ] Monitor consciousness states
- [ ] Review decision reasoning
- [ ] Check confidence scores
- [ ] Understand multi-model consensus

### Week 3: Strategy Tuning
- [ ] Adjust risk parameters
- [ ] Try different strategies
- [ ] Compare performance
- [ ] Fine-tune thresholds
- [ ] Review analytics

### Week 4: Going Live
- [ ] Verify paper trading results
- [ ] Set conservative limits
- [ ] Start with small position sizes
- [ ] Monitor closely first week
- [ ] Gradually increase as confidence grows

---

## 📊 Success Metrics

You'll know you're successful when:

✅ **Technical**
- Windows Search finds "Loki Trading" instantly
- No error messages in console
- All imports work correctly
- AI status shows "Active"
- Charts update smoothly

✅ **Trading**
- AI makes autonomous decisions
- Positions open and close correctly
- Risk limits are respected
- Performance metrics track accurately
- Profit > losses (over time)

✅ **Confidence**
- You understand AI reasoning
- You trust the system
- You sleep well at night
- You can explain decisions
- You're comfortable with automation

---

## 🚨 Emergency Procedures

### If Everything Breaks

1. **Stay calm** - Everything is fixable
2. **Close Loki** - Stop trading temporarily
3. **Run TEST_LOKI.bat** - See what's wrong
4. **Run RUN_DIAGNOSTICS.bat** - Get full report
5. **Run ULTIMATE_FIX.bat** - Repair everything
6. **Restart computer** - Fresh start
7. **Test with TEST_LOKI.bat** - Verify fix
8. **Resume trading** - You're back!

### If AI Makes Bad Decision

1. **Don't panic** - AI learns from mistakes
2. **Manual override** - Close position manually
3. **Check logs** - Understand reasoning
4. **Adjust parameters** - Prevent recurrence
5. **Monitor closely** - Watch for improvement
6. **Review after hours** - Full analysis

### If Market Crash

1. **Check circuit breakers** - Risk limits active?
2. **Review positions** - What's exposed?
3. **Let AI manage** - It's trained for volatility
4. **Don't override emotion** - Trust the system
5. **After crash** - Review AI performance
6. **Learn** - What worked? What didn't?

---

## 🎉 You're Ready!

You now have:
- ✅ Complete installation
- ✅ Windows Search integration
- ✅ Multiple launch methods
- ✅ Diagnostic tools
- ✅ Troubleshooting guides
- ✅ Pro tips and workflows

**Start with:**
1. Double-click **ULTIMATE_FIX.bat**
2. Wait for completion
3. Restart computer
4. Double-click **"Loki Trading"** on Desktop
5. **Trade!** 🚀📈

---

## 📞 Quick Command Reference

| What You Want | What to Do |
|---------------|------------|
| **First-time setup** | `ULTIMATE_FIX.bat` |
| **Launch Loki** | Desktop shortcut |
| **See errors** | `TEST_LOKI.bat` |
| **Check health** | `RUN_DIAGNOSTICS.bat` |
| **Test search** | `TEST_WINDOWS_SEARCH.bat` |
| **Test AI** | `python test_ai_agent.py` |
| **Auto-start** | `SETUP_AUTO_START.bat` |
| **Fix everything** | `ULTIMATE_FIX.bat` |

---

*Happy Trading! May your profits be high and your drawdowns be low! 🤖💰*

**Loki Trading Platform** - Where Artificial Intelligence Meets Wall Street
