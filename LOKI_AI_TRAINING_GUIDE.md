# 🧠 LOKI AI Training & Self-Evolution Guide

## 🎯 What's New: AI Learning & Self-Evolution

The AI in LOKI v5.0 now:
- ✅ **Learns from historical data** - Train on simulated backtests
- ✅ **Tracks performance metrics** - Win rate, P&L, streaks
- ✅ **Adapts confidence thresholds** - Auto-adjusts based on performance
- ✅ **Validates before auto-trading** - Won't trade unless performing well
- ✅ **Learns from mistakes** - Tracks mistake patterns
- ✅ **Shows performance dashboard** - Visual score and progress bar
- ✅ **Self-evolves over time** - Improves strategy weights automatically

---

## 🎓 AI Training Mode

### How to Train the AI:
1. Open LOKI Desktop
2. Look at the "AI PILOT" card on the right panel
3. Click **"🎓 TRAIN AI ON DATA"**
4. AI will backtest all 9 symbols (BTC, ETH, SOL, AAPL, TSLA, NVDA, MSFT, SPY, QQQ)
5. Simulates hundreds of trades to learn patterns
6. Updates performance score

### What Training Does:
- Runs backtests on all symbols
- Simulates trades using ML Ensemble strategy
- Learns which signals work best
- Tracks simulated wins and losses
- Updates the AI's performance score
- Improves strategy weights automatically

### Training Results:
- Shows total simulated trades
- Shows simulated win rate
- Shows simulated P&L
- Shows updated performance score
- AI becomes "ready" for auto-trading

---

## 📊 Performance Score

### What It Measures:
The AI's performance score (0% to 100%) is calculated from:
- **Win Rate (40% weight)** - Percentage of winning trades
- **Average P&L per Trade (30% weight)** - Average profit/loss
- **Current Streak (30% weight)** - Recent performance momentum

### Score Thresholds:
- **< 40%** - Poor performance (red)
- **40-60%** - Average performance (yellow)
- **> 60%** - Good performance (green)

### Where to See It:
- Right panel → AI PILOT card
- Visual progress bar with color coding
- Updated in real-time as trades close

---

## 🛡️ AI Readiness Validation

### Before Auto-Trading:
The AI checks if it's ready:
1. **Minimum 10 trades** - Needs enough data
2. **Performance score ≥ 45%** - Must be performing decently
3. **Win rate ≥ 45%** - Must be winning more than losing

### If Not Ready:
- Shows warning dialog
- Explains why (e.g., "Need at least 10 trades")
- Shows current performance score
- Asks if you want to start anyway (not recommended)
- Suggests manual trading or training first

### If Ready:
- Allows auto-trading to start
- Shows "AI performing well - ready for auto-trading"
- Auto-trades with confidence threshold

---

## 🧠 Self-Improvement Engine

### What It Learns:
- **Strategy performance** - Which strategies work best
- **Market regimes** - How to adapt to different conditions
- **Confidence calibration** - How confident signals should be
- **Mistake patterns** - Which signal types fail most often

### How It Adapts:
1. **Weight Optimization** - Boosts winning strategies, reduces losing ones
2. **Confidence Adjustment** - Increases threshold if performing poorly
3. **Regime Adaptation** - Adjusts weights per market condition
4. **Mistake Avoidance** - Tracks patterns to avoid repeating errors

### Adaptation Triggers:
- Every 3 closed trades per strategy
- Automatic and continuous
- Saves state to disk
- Persists across sessions

---

## 📈 Adaptive Confidence Threshold

### How It Works:
- **Default**: 70% confidence required
- **If performing poorly** (< 40% win rate or < 40% score): Increases to 90%
- **If performing well** (> 60% win rate and > 60% score): Decreases to 60%

### Why It Matters:
- **Conservative when losing** - Prevents bad trades during streaks
- **Aggressive when winning** - Takes more opportunities when hot
- **Self-regulating** - Automatically adjusts to performance

---

## 🔍 Mistake Pattern Tracking

### What It Tracks:
- **Oversold Reversal Failures** - Times "oversold" signals didn't work
- **False Breakouts** - Times breakout signals failed
- **Other patterns** - Tracks any repeating mistakes

### How It Helps:
- Identifies which signal types are unreliable
- Can be used to adjust strategy weights
- Shows in the learning state file
- Future enhancement: automatically adjust based on patterns

---

## 🎨 AI Performance Dashboard

### Visual Elements:
1. **Performance Score Label** - Shows current score (e.g., "Performance Score: 72%")
2. **Progress Bar** - Visual representation (0-100%)
3. **Color Coding**:
   - Green (> 60%) - Good performance
   - Yellow (40-60%) - Average performance
   - Red (< 40%) - Poor performance
4. **Real-time Updates** - Updates every 0.5 seconds

### Location:
- Right panel → AI PILOT card
- Below the "LET AI TRADE BY ITSELF" button
- Above the learning summary

---

## 🚀 Recommended Workflow

### Step 1: Train the AI First
```
1. Open LOKI
2. Click "🎓 TRAIN AI ON DATA"
3. Wait for training to complete
4. Check performance score
```

### Step 2: Manual Trading (If Score < 45%)
```
1. If score is low, do manual trades
2. Use different strategies
3. Close positions to give AI data
4. Watch performance score improve
```

### Step 3: Enable Auto-Trading (When Ready)
```
1. Wait for performance score ≥ 45%
2. Wait for at least 10 total trades
3. Click "LET AI TRADE BY ITSELF"
4. AI will auto-trade only when confident
```

### Step 4: Monitor and Adjust
```
1. Watch performance score in real-time
2. Check AI summary line for adaptations
3. Review trades in Order History
4. Export trades for external analysis
```

---

## 📊 Performance Metrics Explained

### Summary Line Format:
```
Closed 15 | Wins 9 | Performance 72% | Learned P&L $+1,250.00 | Tweaks 3
```

- **Closed** - Total closed trades
- **Wins** - Winning trades
- **Performance** - Overall performance score (0-100%)
- **Learned P&L** - Total profit/loss from learning
- **Tweaks** - Number of strategy weight adaptations

### Performance Score Calculation:
```
Score = (Win Rate × 0.4) + (Avg P&L / 100 × 0.3) + (Streak / 10 × 0.3)
```

Example:
- Win Rate: 60% → 0.6 × 0.4 = 0.24
- Avg P&L: $50 → 50/100 × 0.3 = 0.15
- Streak: +3 → 3/10 × 0.3 = 0.09
- **Total Score**: 0.24 + 0.15 + 0.09 = **48%**

---

## 🔧 Advanced Features

### Regime-Based Adaptation:
The AI adjusts strategy weights based on market regime:
- **Bull Trend** - Favors momentum and breakout
- **Bear Trend** - Favors momentum and breakout
- **Ranging** - Favors mean reversion
- **High Volatility** - Favors breakout and volatility surface

### Confidence Calibration:
- Tracks confidence levels of winning vs losing trades
- Adjusts scoring to favor well-calibrated strategies
- Prevents overconfident bad signals

### Streak Tracking:
- **Win Streak** - Consecutive winning trades
- **Loss Streak** - Consecutive losing trades
- **Influences performance score**
- Helps identify momentum

---

## 💡 Best Practices

### Before Auto-Trading:
1. ✅ Always train the AI first
2. ✅ Check performance score is ≥ 45%
3. ✅ Ensure at least 10 trades in history
4. ✅ Review learning summary line
5. ✅ Verify win rate is ≥ 45%

### During Auto-Trading:
1. ✅ Monitor performance score in real-time
2. ✅ Watch for adaptations (tweaks)
3. ✅ Check if confidence threshold adjusts
4. ✅ Review trades periodically
5. ✅ Use emergency stop if needed

### After Auto-Trading:
1. ✅ Export trades to CSV
2. ✅ Analyze performance
3. ✅ Check mistake patterns
4. ✅ Consider retraining if performance drops
5. ✅ Reset session if needed

---

## 🎯 AI Readiness Checklist

Before enabling auto-trading, ensure:
- [ ] AI has been trained on historical data
- [ ] Performance score ≥ 45%
- [ ] At least 10 trades in history
- [ ] Win rate ≥ 45%
- [ ] Confidence threshold is reasonable (60-80%)
- [ ] No major loss streaks recently
- [ ] Strategy weights have adapted

---

## 📈 Example Workflow

### Day 1: Training
```
1. Open LOKI
2. Click "TRAIN AI ON DATA"
3. Training completes: 200 simulated trades, 120 wins, 60% score
4. AI is ready!
```

### Day 2: Manual Validation
```
1. Do 5 manual trades
2. Performance score: 62%
3. AI learns from these trades
4. Strategy weights adapt
```

### Day 3: Auto-Trading
```
1. Performance score: 65%
2. Click "LET AI TRADE BY ITSELF"
3. AI auto-trades when confident
4. Performance score improves to 72%
5. AI adapts weights automatically
```

### Day 7: Review
```
1. Export trades to CSV
2. Analyze in Excel
3. Check mistake patterns
4. Retrain if needed
5. Continue auto-trading
```

---

## 🔍 Troubleshooting

### AI Won't Start Auto-Trading:
- **Reason**: Performance score too low
- **Solution**: Train AI, do manual trades, wait for score to improve

### Performance Score Stuck at 50%:
- **Reason**: Not enough trades
- **Solution**: Do more manual trades or train on historical data

### Confidence Threshold Too High:
- **Reason**: AI performing poorly
- **Solution**: Improve performance, threshold will auto-adjust

### AI Making Bad Trades:
- **Reason**: Mistake patterns not addressed
- **Solution**: Check learning state, consider resetting session

---

## 📞 Summary

**The AI in LOKI v5.0:**
- ✅ Learns from historical data (training mode)
- ✅ Tracks performance metrics (score, win rate, streaks)
- ✅ Adapts confidence thresholds (auto-adjusts)
- ✅ Validates before auto-trading (won't trade if performing poorly)
- ✅ Learns from mistakes (tracks patterns)
- ✅ Shows performance dashboard (visual score bar)
- ✅ Self-evolves (improves strategy weights)

**The AI is now smarter and safer - it won't trade unless it's performing well!** 🎯
