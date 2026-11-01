# Paper-model readiness

The runner's entry gate and model dashboard use
`core/fusion/paper_evidence.py`. Training alone does not enable entries.

For non-cash policies the gate requires:

- A recognized model version; fixed rule models must pass frozen validation.
- At least three completed later-period trades (a minimum sanity check, not a
  statistically convincing sample).
- Positive modeled net return and average P&L after costs in the later period.
- Measured account drawdown no greater than 3% in that period.
- A positive later-period replay with fees and slippage doubled.

These previously inspected dates are development evidence. Using negative
results to reject deployment does not turn a positive result into an untouched
holdout. Passing means **experimental paper candidate**, not proven profitable.
New forward observations remain necessary. Models without stress results need
the strategy comparison before new paper entries can be enabled.

Entry quotes must also fit the replay cost assumptions: half the bid/ask spread
cannot exceed modeled per-side slippage. This is not a fill guarantee. Spread
or research entry failures do not disable protective exits for AI-owned units.

Cash-only policies may run as no-entry monitors. They cannot claim profits.
Existing AI holdings/pending actions can be resumed for reconciliation and exit
management even when new entries fail evidence checks. Manual holdings/orders
remain separate and are not adopted by the runner.

## Inspection on 2026-11-01

The Alpaca paper account was active and unblocked, with no positions, but had a
previously requested one-share AAPL buy still queued for a closed market. No new
order was submitted or canceled during this inspection.

Saved histories end 2026-10-30. Recomputed validation selections: AAPL and TSLA
stay in cash; SPY, QQQ, MSFT and NVDA have negative later-period returns after
costs. No evaluated selection passes the entry gate. The account's cash/equity
balance and a manual accepted order are not strategy performance evidence.

The runner still requires an active browser heartbeat; it is not an unattended
server daemon. Reload/relaunch the updated application to use changed Python
code. Do not delete runner state to bypass ownership or reconciliation checks.
