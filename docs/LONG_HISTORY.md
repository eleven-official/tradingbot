# Longer daily model history

The Alpaca paper workspace supports 5, 10, 15 and 20-year research windows.
The selected window is the total history: first 60% fits model weights, next
20% selects settings, final 20% evaluates later performance. A 20-year window
does not mean all 20 years are used to fit weights.

## Sources

- **Alpaca IEX:** account data entitlements apply. Requesting 20 years does not
  create history the feed does not supply. Incomplete coverage fails training.
- **Yahoo Finance:** explicitly select the research source in the form. Daily
  OHLCV is obtained via yfinance, without dividend auto-adjustment. This is not
  broker-verified Alpaca history; vendor adjustments, revisions and venue
  differences remain limitations. Vendor terms apply.
- **CSV:** use the dedicated long-history file input in the instrument form.
  Up to 10,000 completed daily candles and 4 MB are accepted. The separate Quant
  lab retains its 5,000-bar evaluation limit.

CSV headers: `timestamp,open,high,low,close,volume`. Dates must be unique,
chronological and completed. Invalid bars, long gaps and insufficient coverage
are rejected; no synthetic padding or silent provider substitution is used.

## Actual research run, 2026-11-01

Two windows were declared before checking results, using the existing logistic
baseline and the five existing rule candidates without changing parameters:

| SPY window | Bars | Actual coverage | Validation selection | Later net | 2× cost later net |
|---|---:|---|---|---:|---:|
| 10 years | 2,513 | 2016-11-01–2026-10-30 | 20/100 momentum | +0.127% | −0.475% |
| 20 years | 5,030 | 2006-11-01–2026-10-30 | Cash | 0% / no trades | 0% / no trades |

Returns are percentages of a modeled $10,000 account, with a maximum $1,000 / 10%
allocation, not returns on invested capital. The 10-year window's later period
begins 2024-11-04; the 20-year window's begins 2022-11-02. Results from different
evaluation periods are not directly comparable rankings.

Both fail new-entry eligibility. No order was placed, and neither was promoted
to active automation. Exact private snapshots and reports were saved under the
existing paper account scope. Recent evaluation dates had already been inspected;
these are development results, not new independent holdouts.

Longer history tests more regimes, including 2008 and 2020 in the full 20-year
window. It does not enable certain predictions. Further changes require new
chronological/forward evidence, cost stress and comparison with passive exposure,
not repeated tuning until a green result appears.
