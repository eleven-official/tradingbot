# Website trading check — 2.37.0

Tested through the local website with an authorized Alpaca paper account.
No strategy conditions or market-clock checks were bypassed.

- Connect, portfolio refresh, train, Start, decision cycle, Stop, cancellation
  and fill reconciliation returned successfully through the website.
- SPY: 1,254 daily IEX bars, 2021-10-26 through 2026-10-23.
- Validation trials: 19 closed trades / -0.3116% return at threshold 0.55;
  one closed trade / -0.1196% at 0.60; no trades at 0.65.
- Selected model: no validation edge; wait in cash.
- Untouched later test: zero trades, 0% net return. Matched passive 10%
  allocation: +0.7398%. These are historical model results, not account fills.
- The earlier transport-test order remained unfilled. Canceled it through
  the website and verified the journal's final `canceled` state, zero fills.
- On the clean Start, Alpaca's clock reported market closed. The runner sent
  no order and was stopped after the check.
- Paper account cash/equity remained $25,000 with no positions.

Conclusion: the connected website workflow works. This evaluation did not
demonstrate profitable autonomous trading. No win rate can be calculated from
zero completed test trades. A longer market-hours forward test is still needed.

The animated overview chart is explicitly labeled illustrative, not market
data. Desktop/mobile rendering and reduced-motion behavior were checked.
