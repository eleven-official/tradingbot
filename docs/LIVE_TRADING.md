Live trading
============

This repository supports both simulated (paper) trading using live market data and an optional real-account mode. For safety the real-account mode is disabled by default and requires server-side configuration.

How to enable live trading (safe flow)
-------------------------------------
1. On the server where you run the trading bot, set the following environment variables (do NOT commit them to Git):

   - LIVE_TRADING=true          # enables the process to forward orders to exchanges
   - ALLOW_LIVE=true            # allows remote toggle endpoint to turn on live mode (optional)
   - BINANCE_API_KEY=your_key
   - BINANCE_API_SECRET=your_secret

2. Start the dashboard/server. The `Enable live trading` button in the dashboard only toggles live mode if ALLOW_LIVE=true on the server to avoid accidental remote activation.

3. Test with small orders using the dashboard in paper mode before using real funds.

Important safety notes
----------------------
- Live trading should be enabled only after you understand the strategy and risks.
- API keys must be kept secret. Use environment variables or secrets managers; do not store keys in repo or public places.
- Rotate keys immediately if they are ever exposed.

Supported flows
---------------
- Paper trading with live market data (default): uses public market data (e.g., Binance REST) to simulate fills.
- Live trading (manual opt-in): when LIVE_TRADING and broker keys are set in the environment, the server can be configured to forward orders to the broker SDK (Alpaca, Binance, etc.).

Next steps the maintainer will complete
--------------------------------------
- Add formal exchange adapters (Alpaca, Binance) to forward orders securely once tested.
- Add persisted order/position storage (DB) and auditing for compliance.
- Add user-level encrypted key storage if you want to enter API keys in the dashboard GUI. Currently keys must be configured as environment variables.
