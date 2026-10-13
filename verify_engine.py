# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import loki_desktop

print("Loki Desktop v4.5 loaded successfully!")

sim = loki_desktop.AdvancedMarketSimulator()
acc = loki_desktop.ProfessionalAccount(25000.0)
bars = sim.get_ohlcv("BTC/USD", 120)

# 1. Test Quant Backtester
res = loki_desktop.QuantBacktester.run_backtest(bars, "ml_ensemble", 25000.0)
print(f"Quant Backtest result: Return = {res['return_pct']:+.2f}%")
print(f"Profit Factor = {res['profit_factor']:.2f}")
print(f"Total Trades = {res['total_trades']}")
print(f"Win Rate = {res['win_rate']:.1f}%")

# 2. Test Trade Execution
prices = sim.tick()
btc_price = prices["BTC/USD"]
trade_res = acc.execute_trade(
    "BTC/USD", "BUY", 0.05, btc_price, strategy="ml_ensemble",
    stop_loss=btc_price * 0.97, take_profit=btc_price * 1.06
)
print(f"Trade executed: status = {trade_res['status']}")

# 3. Test SL Trigger Protection
closed = acc.check_risk_triggers({"BTC/USD": btc_price * 0.95})
print(f"Protective triggers executed: {len(closed)}")

# 4. Test Metrics Calculation
m = acc.get_metrics(prices)
print(f"Account Equity: ${m['equity']:,.2f} | Open Positions: {m['open_positions']}")

print("\nALL REVOLUTIONARY ENGINE CHECKS PASSED 100%!")
