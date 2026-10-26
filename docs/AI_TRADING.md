# AI trading: paper, Alpaca live and Lucid

## Paper simulator

The AI trading page's paper controls fill a browser journal with simulated
money. The simulator calls `/api/fusion/ai/step`, which never sends orders.
Changing a chart timeframe does not change the trained daily strategy.

## Portfolio display

Portfolio refresh failures are shown as unavailable, not as zero holdings or
fresh balances. A failed key check clears the verified connection state.
Chart refreshes retain the previous candles for the same symbol/timeframe
while fetching; the status distinguishes a failed refresh from current data.

An accepted test order proves order transport, not autonomous strategy
performance or a fill. A model with no validated entry threshold waits in cash.

When an Alpaca paper account is connected, the workspace shows exactly what
the venue reports as held: key facts (status, cash, equity, buying power) plus
the actual holdings table from Alpaca (`/v2/positions`, whitelisted keys). An
account with no positions honestly shows a cash-only portfolio; a failed
holdings read shows an unavailable note instead of invented rows. The hard-keys
panel (Real account) reads positions per request with browser-held keys; the
launcher panel reads the same feed for the connected server session. Open
orders appear in the order log and, for the AI runner, in its journal.

## Alpaca live runner

Run the local launcher. Under AI trading, connect **Alpaca live**, enter a
maximum USD order value, daily account-equity loss pause, and daily entry cap,
then press **Start LIVE AI trading**. The connection alone sends no orders.

The runner supports trained SPY, QQQ and AAPL profiles and whole-share,
cash-funded long entries. It requires a flat account at Start and checks
the broker clock, asset, quotes, account and outstanding orders before entry.
It submits a GTC limit entry with an Alpaca stop-loss/take-profit bracket.
The daily strategy supplies the signal and stop/target; current Alpaca IEX
quotes determine the entry limit. The order budget and a stop-risk allocation
of 25% of the remaining daily loss allowance cap size. There is at most one
entry per symbol per UTC day; all account positions/orders block more entries.

The daily equity baseline is recorded on the first Start that UTC day and
survives Stop/Start. The daily loss setting pauses new entries; it is not a
guarantee of maximum loss and does not flatten holdings or cancel orders.
Exits are handled by the broker bracket, not an AI reversal signal. Stops can
gap, partial fills can affect bracket activation, and existing orders require
management at Alpaca when the runner is stopped.

Keep the page open. A browser heartbeat expires after 90 seconds and the
runner stops new entries at a UTC day change. Restarting the browser/server
does not automatically restart live trading. Start/Stop authority is separate
from paper controls. Credentials remain in the existing four-hour server-memory
session; a server restart or expiry requires reconnecting.

Claims are persisted in the local SQLite journal (`LOKI_PAPER_AI_DB`, otherwise
`state/paper_ai/research.sqlite3`) before transport. Never delete that journal
to clear an uncertain order. **Refresh broker order status** reconciles the
same client order ID; a timeout never causes an automatic resubmission.
Use one local deployment with durable storage for an account.

## Lucid funded / Tradovate

Lucid funded is not the browser simulator. A prop-firm connection can use
Tradovate demo infrastructure while still being consequential funded trading.
No direct Tradovate API entitlement or account connection has been verified
for this installation; no Lucid orders can be sent by this release.

[TradersPost documents Lucid via Tradovate](https://traderspost.io/connections/lucid-trading).
This is a third-party connection option, not an installed Loki integration.
The account owner must select/authorize an available connector before a
funded runner can be implemented against its actual order/fill API. Do not
substitute a personal Tradovate API key or assume a funded login grants API
access. Lucid's official FAQ returned HTTP 403 during this review, so no
claim about this particular account's permissions is based on that page.

## Candles

The chart requests Yahoo Finance OHLCV through Loki's cached provider.
Timeframes: 1m, 5m, 15m, 1h, 1d. It refreshes every 20 seconds while visible,
with a 60-second provider cache. Data may be delayed and the latest bar may
be incomplete. Source, latest-bar time and fetch time are displayed.
ES=F, NQ=F and GC=F are reference series, not a specific tradable futures
contract, a Lucid execution feed, or a trained futures trading strategy.

Tests cover simulated broker responses; no real account order was placed
during development. Real broker verification needs the owner's connection.
