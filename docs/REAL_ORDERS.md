# Manual real-order workflow

The web Real account view has a separate manual Kraken **spot limit order**
workflow. It is disabled by default. Paper/Real changes the view; it never arms
trading. Chat, strategy research and council results cannot submit orders.
Coinbase and Binance remain account-inspection integrations only.

## Host configuration

Keep credentials in the local launcher's host environment. Never put them in
chat, browser storage, source control or a public deployment. Account inspection
uses `LOKI_REAL_READS_ENABLED=1`, `LOKI_REAL_API_KEY`, `LOKI_REAL_API_SECRET`,
optional `LOKI_REAL_API_PASSPHRASE` and `LOKI_REAL_EXCHANGE=kraken`.
Read-only keys suffice for balances; actual placement/cancellation needs the
corresponding venue order permissions. Loki does not need withdrawal permissions.

Additional host settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `LOKI_REAL_ORDERS_ENABLED` | off | Only `1` permits previewing and submitting new manual orders |
| `LOKI_REAL_MAX_ORDER_USD` | `100` | Maximum notional plus estimated fee buffer; range 1–10,000 USD |
| `LOKI_REAL_DAILY_ORDER_LIMIT` | `5` | Durable submission claims per UTC day; integer 1–100 |
| `LOKI_REAL_ORDER_JOURNAL` | `state/real/orders.sqlite3` in the repository | Persistent host-side journal; never an ephemeral directory |

The default journal directory is ignored by Git. Back up and protect this file
as account data. All processes for a given account key must share the same file.
Limits and order history are scoped to the configured API key, not to every key
or manual order on an exchange account. Changing a key or using a different
journal loses access to the old key's local order history; resolve outstanding
orders at the venue before doing so. This local workflow is not a multi-user
brokerage deployment or a portfolio drawdown-control system.

## Order lifecycle

1. Select Real, inspect readiness and explicitly read balances if desired.
2. Enter BTC/USD, ETH/USD or SOL/USD, buy/sell, base-asset quantity and limit.
   Only held assets can be sold. Borrowing, margin and shorts are not supported.
3. Preview loads actual CCXT venue metadata, precision, minimums, bid/ask and
   available funds. Amount precision must never increase the requested units.
   Review the final displayed quantity and price, including any price rounding.
   The limit must be within 5% of the observed midpoint, spread no wider than
   2%, and a supplied venue timestamp no older than 30 seconds. Missing venue
   timestamps are labeled unknown; local receipt time is not venue freshness.
4. The immutable preview expires after 60 seconds. Type **PLACE REAL ORDER**
   for this exact preview. The server rechecks market metadata, funds, limits,
   expiry, and host permission before durably claiming the submission.
5. A GTC limit can fill immediately or stay open. No automatic protective stop
   or autonomous trade management is attached. Inspect venue status and fills.
6. Load the durable order journal. Refresh venue status to reconcile an order.
   For a known order, review cancellation and type **CANCEL REAL ORDER**.
   Cancellation remains available when the host disables new placements; a
   request can race a fill, and an incomplete response needs reconciliation.

At least a 1% quote-currency fee buffer is reserved for buy previews, increased
if metadata indicates higher fees. It is an estimate, not a guaranteed charge.
Market data, available funds and fees can change between checks and execution;
the exchange can reject a locally valid preview.

## Recovery and evidence

SQLite commits the claim with full synchronization **before** the transport
call. CCXT network retries are disabled. The request uses a unique UUID client
order ID. Double clicks and restarts return the saved state instead of creating
another order. One open or unresolved Loki order blocks another submission.
Rejected and uncertain claims both count toward the day's claim limit.

A timeout, malformed response or crash leaves an unresolved state. Loki never
automatically repeats an order creation. Reconciliation queries a known venue
ID, or searches open/closed orders for the saved client ID. A missing result does
not prove the order was absent: pagination or venue retention may omit it.
Check the exchange directly if uncertainty remains. In-flight crash claims wait
at least 60 seconds before reconciliation. Do not delete the journal to bypass
an unresolved outcome.

Kraken's client ID uniqueness applies to open orders; durable local claims
provide the additional restart/double-click protection. See
[Kraken Add Order](https://docs.kraken.com/api-reference/trading/add-order) and
the installed CCXT Kraken implementation for venue semantics.

Vibe-Trading's original MIT `PendingOrderRequest` validator executes unchanged
inside this workflow, with byte-hashed original source and AST parity checks.
The transport and durable journal are Loki implementations. Tests use mocked
venue clients and mocked transport responses; **no real account or funded order
was used to validate this implementation**. Software checks, synthetic practice
and manual order capability do not establish a profitable strategy or 70% wins.
