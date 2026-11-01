# Loki's rebuilt historical analogue model

This is a new research model, version `loki_historical_analogue_v3`, not a rename
of the previous logistic/rule system. Existing models, orders and broker state
are left intact. It is not connected to execution and is not established profitable.

## How it works

1. Validate real, completed OHLCV candles over the selected 10/15/20-year span.
2. Build 16 causal features from each eligible 20-bar window: recent returns,
   volatility, candle/range position, relative volume and intraday clock phase.
3. Fit scaling and retain up to 4,096 historical training prototypes from the
   first 60% of dates. Labels run from the next bar's open to the horizon close.
4. Prefer prototypes in the same training-defined trend/volatility regime; use
   all regimes when a matching pool has fewer than 93 examples. Find the 31
   nearest earlier training patterns, showing five actual examples
   with signal/outcome dates, realized moves and distances.
5. Estimate historical up-frequency and 10th/25th/50th/75th/90th return quantiles.
   These are empirical distributions, not calibrated probabilities or guaranteed
   future-price intervals. Unfamiliar patterns abstain using a training-only
   distance threshold.
6. Use the next 10% for probability calibration: select from fixed analogue
   weights 0/0.25/0.5/0.75/1 blended toward the frozen training baseline. Evaluate
   the next 10% and final 20%, purging label overlap at each boundary.
   No nearest-neighbour search uses those periods as training memory. A new
   forecast must follow all fitted calibration outcomes AND the evaluation
   outcomes used for readiness; self-matching and future-readiness leakage are
   rejected.

Parameters are fixed rather than optimized until a test turns green. Directional
research views require a conservative return quantile to exceed doubled costs,
and an estimated up probability of at least 60% (long) or at most 40% (short).
Validation **and** later evaluation must have at least 20 signals, positive
doubled-cost unit P&L and a better Brier score than the frozen training-frequency
baseline. Otherwise the displayed view remains **WAIT**. Passing still only means
experimental research evidence, not permission to trade or proof of an edge.

## Supported research instruments

- Futures: ES ($50/point), NQ ($20/point), MES ($5/point), MNQ ($2/point), all with
  a 0.25-point tick. Verify current exchange/broker specifications before trading.
- Liquid equities/ETFs: SPY, QQQ, AAPL, MSFT, NVDA, TSLA; outcomes are per one share.
- Bar intervals: 5, 15, 30, 60 minutes, or daily. Horizon: 1–12 bars.

The instrument and timeframe are separate model contexts; daily results cannot
be used to claim intraday performance. No futures, short-stock execution, margin
simulation, liquidation handling, options or order-book feed is implemented.

## Data contract

Open **Paper → What followed similar market conditions?** after relaunching the
updated application. Upload a licensed historical CSV, or choose a saved daily
instrument snapshot for a daily-only experiment. Specify provenance and actual
commission/slippage costs; never include account credentials in CSV/source labels.

Required columns:

```text
timestamp,open,high,low,close,volume
```

Intraday additionally requires `session` (the exchange trading-session date) and
timezone-aware ISO8601 **bar-close** timestamps. Futures additionally require
`contract`, such as `ESZ2020` or `NQH21`, on every row. Use unadjusted actual-contract
prices, choosing one contract per timestamp. The model does not construct a roll
schedule. Contract years must be consistent with bar dates. Windows and targets
crossing sessions, missing intervals, or contract rolls are excluded.

There is no automatic paid-vendor download or invented intraday substitute.
Twenty years of daily data is not twenty years of day-trading data. The existing
Alpaca paper account does not by itself supply licensed decades of futures bars.
Broker/vendor rights, timestamps, roll choices and survivorship still require
independent source verification.

Input is bounded at 500,000 candles / 80 MB in the browser. Twenty years of full
session five-minute futures bars may exceed that: use a genuine coarser interval
such as 15/30 minutes, not missing/truncated history disguised as a full sample.
Dates must cover the declared span with at least 170 observed trading days or
sessions per requested year. Short or sparse date spans fail validation.

## Evaluation limits

Training references and up to 512 evaluation opportunities per period are sampled
deterministically. Opportunity labels do not overlap. Financial metrics are
sampled **one-contract/one-share outcome P&L**, not account returns, a full trading
ledger, a margin-aware strategy, or a simulation of all possible executions.

Costs include a positive commission per side/unit and 1–20 slippage ticks per side,
with a doubled-cost stress. Futures commission must be at least $0.50 per side;
use the actual all-in exchange/broker charges. Gross historical returns shown for
individual analogues exclude costs. No future fills are assumed confirmed.

Prior project work inspected recent historical dates. Reusing those dates is
development evidence, not a new untouched holdout. Forecast quality can change
with regimes, vendor revisions, contract selection, serial dependence and costs.
Fresh forward-paper evidence is still needed.

## Saved memory and API

Local-only research endpoints require the launcher's session token:

- `POST /api/fusion/analogue/evaluate`: validate, build, evaluate, save a bundle.
- `GET /api/fusion/analogue`: discover saved models, with current-version models
  first. Corrupt/unreadable bundles are reported and skipped, not deleted.
- `GET /api/fusion/analogue/{id}`: load its research report.
- `POST /api/fusion/analogue/{id}/forecast`: use 20–10,000 new same-context bars.
- `POST /api/fusion/analogue/{id}/forecast-latest`: for current Yahoo-trained daily
  equity models, fetch the last completed daily candles and estimate the next
  horizon. Data is cached for five minutes; data older than five calendar days
  is rejected. Futures, intraday and other data sources require a matching CSV.

The panel automatically discovers and loads a current saved model. Use the
saved-model selector rather than copying an ID, then **Latest completed daily
estimate** for supported models. Changing models clears the previous forecast.
Detailed WAIT reasons distinguish insufficient evidence, cost/quantile failures
and unfamiliar patterns from a software error. A 60%+ direction estimate alone
does not pass the research-readiness gates.

If the panel appears but the model API returns 404, the Python process is older
than the files on disk. Restart the correct local service and reload capabilities
to get a fresh private token. Do not enable automatic trading or delete journals
to work around an old backend. Restarting clears in-memory broker connections;
existing venue orders and saved research remain intact.

Bundles are atomically written under `state/analogue_models/` (override with
`LOKI_ANALOGUE_DIR`). They contain the frozen numerical prototype memory and
sanitized historical example metadata, with data/artifact hashes. Raw uploaded
history is not retained by this module: keep the licensed source file to reproduce
the dataset hash. Bundles are private local files, not uploaded to Supabase and
not read as instructions by Obsidian or OpenCode. New bundles checksum both the
artifact and report and verify the combined data/model identity. Older bundles
remain viewable as legacy research but require retraining for current forecasts.
The saved model ID can be loaded
from the panel after a restart. No report/forecast endpoint submits an order.

## First v1 real-data run, 2026-11-01 — superseded evaluation

Version 1 mistakenly used the future entry open to set its cost hurdle when
evaluating a historical signal. Version 2 uses the completed signal close,
matching the forecast path. The historical metrics below are retained only as
an earlier experiment; use the v2 run for current results.

Both runs used 5,030 actual Yahoo daily bars, 2006-11-01–2026-10-30, a three-bar
horizon, 999 frozen prototypes and 250 sampled opportunities per later period.

| Instrument | Later direction accuracy | Later Brier / baseline | Later signals | Sampled unit net P&L | Status |
|---|---:|---:|---:|---:|---|
| SPY | 53.2% | 0.2469 / 0.2396 | 4 | −$11.59 | Insufficient evidence / WAIT |
| QQQ | 60.8% | 0.2409 / 0.2425 | 6 | +$30.23 | Insufficient evidence / WAIT |

QQQ's small positive later sample does not override its failed validation period
or inadequate signal count. Neither was connected to broker execution. Futures
and intraday paths passed synthetic implementation tests, not real historical
profitability tests: licensed real intraday/futures data is still needed.

## Corrected v2 training run

Reproducible daily training command from `tradingbot/`:

```powershell
python train_analogue.py --symbols SPY QQQ AAPL MSFT --years 20 --horizon 3
```

All four trained on 5,030 real daily candles, 2006-11-01–2026-10-30. Models and
exact hash-checked source snapshots (`*.data.json.gz`) were saved privately under
`state/analogue_models/`. CLI snapshots use atomic writes; existing files are
verified rather than silently replaced. Browser-uploaded history still needs
its original source file retained separately.

| Instrument | v2 later signals | v2 sampled unit net P&L | Validation/readiness |
|---|---:|---:|---|
| SPY | 4 | −$11.59 | Insufficient evidence / WAIT |
| QQQ | 6 | +$30.23 | Insufficient evidence / WAIT |
| AAPL | 1 | +$0.03, negative at doubled costs | Insufficient evidence / WAIT |
| MSFT | 0 | $0, no trades | Insufficient evidence / WAIT |

These are sampled one-share outcomes, not account returns. None passed both
chronological evaluation gates. No orders were submitted or broker settings
changed. The price-hurdle fix did not change signals for these particular runs;
a dedicated gap-opening regression test proves future prices cannot affect
the pre-entry eligibility decision.

For licensed intraday futures data, specify actual costs and metadata:

```powershell
python train_analogue.py --symbols ES --years 20 --timeframe 15m --horizon 3 --commission 2.5 --slippage-ticks 1 --csv "path/to/licensed-es-history.csv" --source "Vendor name; actual-contract unadjusted bars"
```

The CLI rejects attempts to substitute Yahoo daily prices for intraday/futures
data. Neither this example nor synthetic tests are an actual futures training
run; that still requires the source file.

## v3 reliability upgrade and fixed retraining run

Version 3 adds trend/volatility-conditioned reference pools, pool-specific
unfamiliarity thresholds and a separate probability calibration block. It also
prevents a historical forecast from using a readiness decision based on outcomes
that occur after its forecast time. V1/v2 reports remain viewable but must be
retrained for v3 forecasts; their files are not overwritten.

The same four-symbol, 20-year daily command above was run without changing the
weight candidates or acceptance gates based on the later results. Each model
used 5,030 real bars, 999 numerical training references and 166 separate
calibration examples. New bundles and exact snapshots were saved locally.

| Instrument | Selected analogue weight | Later raw Brier | Later calibrated Brier | Baseline Brier | Readiness |
|---|---:|---:|---:|---:|---|
| SPY | 0.50 | 0.2437 | 0.2400 | 0.2396 | WAIT |
| QQQ | 0.00 | 0.2401 | 0.2425 | 0.2425 | WAIT |
| AAPL | 0.25 | 0.2513 | 0.2473 | 0.2478 | WAIT |
| MSFT | 0.25 | 0.2518 | 0.2472 | 0.2471 | WAIT |

Lower Brier is better. The table compares raw and calibrated probabilities from
the same v3 regime-aware forecasts, not all v3 performance against v2. Calibration
improved later probability error for three instruments and worsened QQQ relative
to its raw forecasts. A baseline-weight fallback is intentional when earlier
calibration evidence does not support confidence in analogues. No model passed
the full validation/test/signal-count checks, so no profitability claim or broker
activation follows from these improvements.
