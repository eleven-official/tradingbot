# Strategy research and paper-trading protocol

## Write down the live rule before changing it

The dashboard's **Strategy brief** reads the active strategy, its current status message, the classified regime, and the configured entry/exit limits from the running bot. A live regime router can select a different strategy, so the dashboard's active strategy name and status are authoritative for that session.

For the repository's example configuration, the default is **Momentum_VWAP_RSI**:

- **Market condition:** the strategy stands down when VIX is classified high. Otherwise it needs directional sentiment and a price/VWAP/RSI alignment.
- **Entry:** bullish or very bullish sentiment plus close above VWAP and RSI above 55 produces a BUY candidate. Bearish or very bearish sentiment plus close below VWAP and RSI below 45 produces a SELL candidate. All other combinations return HOLD. With the example **buy_only** setting, bullish/bearish candidates buy a call/put; the bot does not open a short option.
- **Entry gates:** the example setup score must reach 65/100, raised to 80 after 14:00. A counter-daily-trend setup is hard-blocked. Regime, VIX, cost/net-edge, trap, re-entry, and loss-risk checks still apply; a strategy candidate alone does not place an order.
- **Exit:** the example caps option-premium loss at 25%, trails by 15% (10% in range mode), and uses a 14:00 time exit. The PSAR indicator exit protects profit after its minimum hold. Enabled structure-target and confirmed-reversal exits can close earlier. A high-conviction aligned trending trade may use the configured 15:15 hold-to-close time.

These are example-config values; the running bot can use different settings. An open position shows its actual stop and target levels in the brief. Read the closed-trade journal row to inspect entry/exit prices, quantity, exit reason, gross result, charges, and net result. Live transaction charges are recorded, but live bid/ask spread and slippage are not separately measured per fill; the dashboard says so on the trade row.

## Backtest costs and metrics

`loki.backtest.backtesting_engine.ExecutionModel` uses explicit assumptions when realistic fills are enabled:

- Commission is charged on each filled order.
- The default full-spread assumption is 0.02%, charged as half on each side of a fill.
- The default slippage assumption is 0.05% per market fill, with stop-gap slippage added to stop orders.
- Limit orders keep their requested fill price; assumed spread and commission are listed separately as cash costs.

Historical OHLC bars do not contain the actual bid and ask. Replace the spread assumption with quote data when available. These modeled costs are estimates, and the limit fill model does not prove that a real order would have filled.

Backtest reports now distinguish gross P&L from net P&L and show commission, spread, slippage, trade count, expectancy, profit factor after costs, and drawdown. Monte Carlo resampling accepts a `random_seed` so a stress run can be reproduced. Compare against a simple buy-and-hold baseline using `core_engine.research_harness.ResearchHarness`; use `core_engine.walk_forward.PurgedWalkForwardValidator` for sequential windows with a gap.

## Test procedure

1. Record a rule version and change one rule at a time. `ResearchHarness.record_trial` keeps the strategy name, parameter hash, and notes.
2. Use chronological rising, falling, and sideways periods. Tune on the earlier portion and use walk-forward validation to compare multiple windows.
3. Keep the later holdout period out of all rule changes. Evaluate it once after freezing the rule version; after examining that result, treat the holdout as spent.
4. Compare net expectancy, trade count, drawdown, and after-cost profit factor against a baseline. Do not select a rule by return or win rate alone.
5. Paper-test the frozen version and preserve its journal outcomes before changing it again.

Run the focused execution-cost and council checks with:

```bash
python -m unittest tests.test_deployment_config tests.test_backtesting_spread_costs tests.test_strategy_council tests.test_research_harness -v
```

These tests validate cost accounting, council explanations, and research controls. They are not historical evidence that any strategy has an edge. No strategy should be called improved until it has passed a multi-regime, after-cost replay with an untouched holdout and a frozen-rule paper run.

