# Simulated market and account modes

Select **Paper** at the top or **Simulated market** in the sidebar. This is an
interactive generated market with its own practice cash account, distinct from
the main paper journal, research dataset and any real exchange account.

The virtual clock advances one minute per candle. Play/pause, single steps,
ten-candle advances and playback speed are supported. BTC/USD, ETH/USD and
SOL/USD share correlated synthetic shocks. Choose balanced, trending up/down,
range, high volatility or a flash-crash scenario. A seed reproduces the same
path. Each session supports 1,440 steps after 120 warmup candles. The browser
saves the practice state; JSON export preserves the complete practice journal.

Market buys use the generated ask and sells the bid, then include 5 bps adverse
slippage and 10 bps fees on each side. Open positions mark to the generated mid.
Limit orders become eligible on the next candle, honor their limit price, and
expire after 480 steps. Each order is capped at 0.5% of preceding synthetic
volume. The illustrative depth is not an order-book queue model; there are no
partial fills or cash/inventory reservations. Pending orders can be rejected
when reached if funds or inventory are insufficient.

Optional protective stops on buy orders execute as the clock advances. A stop
gap fills at the worse open. Resting stops run before profit limits on ambiguous
OHLC candles, and an attached stop touched in the entry candle takes the adverse
outcome. Stops are practice orders only, not exchange orders. The account is
long-only and cash-funded. Reset replaces only the synthetic practice session.

**Ask council about this market** reviews generated observations and the practice
account without submitting orders. No synthetic data, practice accuracy, model
opinion or simulated win counts as real-market evidence toward a 70% win rate.
All responses retain `synthetic: true` and
`performance_evidence_eligible: false`. Talk to Loki can explain that distinction.

## Real mode

**Real** opens a separate real-account view and does not change the practice
ledger, authenticate a venue or arm a trading engine. The current implementation
supports explicit read-only spot balance inspection through the genuine CCXT
Kraken, Coinbase or Binance client. The legacy Binance adapter in this repository
inherits Alpaca behavior and is deliberately not used for real crypto accounts.

Set host environment variables before launching Loki:

- `LOKI_REAL_EXCHANGE`: `kraken`, `coinbase` or `binance`.
- `LOKI_REAL_API_KEY`, `LOKI_REAL_API_SECRET`, optional `LOKI_REAL_API_PASSPHRASE`.
- `LOKI_REAL_READS_ENABLED=1` to allow account inspection.

Use exchange read-only permissions for this feature. No credentials are supplied
by browser requests, retained in browser storage, or exposed in responses. Reads
require the local launcher, its session token and origin checks. Failed reads
show unknown balances; totals are actual asset units, with no invented common
USD equity. Merely configured keys are never labeled authenticated.

**Real order submission is not implemented in this workspace yet.** The top
switch therefore exposes actual connection/readiness state and cannot advertise
an enabled live bot. A funded execution workflow, venue precision/minimums,
reconciliation, idempotency and measured risk gates remain integration work.

## Native MiroFish council input

The full supplied MiroFish source is retained under `components/mirofish/upstream`.
Its exact native `ReportManager.get_report` and Report/Outline/Section/Status
classes run in a separate local process. A completed native report can be
inspected and attached in Agent council without the MiroFish project's HTTP API.
Set `mirofish_data_path` in local launcher JSON, or `LOKI_MIROFISH_DATA_PATH`, to
the MiroFish backend uploads directory. The default is the bundled backend's
uploads directory. It reads `reports/<report_id>/meta.json`, optional native
`full_report.md`, and legacy flat reports using the original file reader.

The scenario changes the council's sentiment-review packet and adds an explicit
scenario-review check. Acknowledgement never bypasses cash, currency, exposure,
cost or strategy-performance gates. Scenario prose is source data, never
authority to disable controls. Instrument binding, freshness and point-in-time
availability are unverified. No genuine provider simulation was run merely by
reading an artifact; new native simulations still need their actual dependencies
and configured LLM/Zep providers. The complete source and AGPL license, extraction
provenance and corresponding-source location are supplied with the component.
