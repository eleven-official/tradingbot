# SPY research check — 2026-11-06

Engine: existing `loki_instrument_daily_rich_v3`, fixed 60/20/20 chronological
split, three predefined thresholds (0.55, 0.60, 0.65). No changes were selected
using the final test results. Historical evaluation, not live profit.

Data: 1,254 Yahoo Finance daily candles, 2021-11-08 through 2026-11-05.
Training ended 2024-11-14; validation ran 2024-11-15 through 2025-11-11;
the held-out test ran 2025-11-12 through 2026-11-05 (247 sessions).
Costs: 10 bps fee + 5 bps adverse slippage per side, also replayed at 2× costs.
Starting simulated equity: $10,000; whole-unit sizing capped at 10% / $1,000.

| Threshold | Validation net | Trades | Validation net, 2× costs |
|---|---:|---:|---:|
| 0.55 | -0.6870% | 55 | -1.8496% |
| 0.60 | +0.0394% | 7 | -0.0794% |
| 0.65 | +0.2500% | 2 | +0.2117% |

No candidate passed the existing minimum-five-trades and cost-stress gates.
The frozen policy therefore stayed in cash: **0 test trades, 0% test return**.
The matched 10%-allocation passive benchmark returned **+0.4608%**.
This model has **not demonstrated profitability**. The two-trade result is
insufficient evidence, and the seven-trade result does not survive doubled costs.

The upgrade exposes cost stress and benchmark comparisons in the website and
charges fees/slippage in new browser-paper fills. It does not loosen selection
rules to force a positive backtest.

Local reproducibility files (ignored runtime data):
- `state/research-checks/spy-5y.json`
- `state/research-checks/spy-5y-report.json`

Data SHA-256: `f4d23a7540cff9d5f99b67e82aed16892cd8aadccdb9ca6c3a77b67da1a7ef46`

Artifact SHA-256: `e202dc9073b72544c7f64cd930daf7edd99c1a8d91e3b59de57609b6188fca58`

The evaluated rich daily model and the browser Director/Quant paper runner are
different paths. This result does not measure every strategy or the chat assistant.
