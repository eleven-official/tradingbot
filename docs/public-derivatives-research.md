# Public derivatives research

Run from the repository root:

```powershell
python train_public_derivatives.py
```

This fits two independent, five-feature ridge-logistic research models. It does
not replace the browser's equity strategy or enable derivatives order execution.

## Sources and sampling

- SPY ETF options: unauthenticated SQL API for
  `https://www.dolthub.com/repositories/post-no-preference/options`, table
  `option_chain`. Weekday queries cover 2023–2025. Each downloaded response is
  cached locally. A 20,000-row query ceiling fails rather than silently truncating.
- VX volatility futures: official Cboe per-expiration daily CSVs, 2018 through
  January 2026 expirations. Contract identity comes from the expiration-specific
  URL. These are individual futures, not the VIX index or a continuous proxy.
  Standard monthly dates are calculated; inaccessible URLs (403/404) are recorded
  in the manifest and omitted. Bars dated 2026 or later are excluded from training.

Raw responses, SHA-256 manifest, derived examples, coefficients, scaling,
threshold trials and evaluation reports are stored in ignored
`state/public_derivatives/`. Re-running reuses successful cached downloads.
The public Dolt branch can change; hashes fingerprint the actual responses used.
No source data is redistributed in Git.

## Modeling and execution assumptions

Training labels end before 2024, validation is 2024 and untouched holdout is 2025.
Examples crossing split boundaries are excluded. Scaling uses training data only.
Thresholds 0.55, 0.60 and 0.65 are selected on validation only, requiring at least
five trades and positive P&L at both baseline and doubled costs. Failure to pass
selects cash, not a relaxed threshold. Holdout prediction metrics are also saved.

Options features: delta, implied volatility, gamma, time to expiration and
relative bid/ask spread. Training uses all matched call-contract observations;
multiple contracts on a date are correlated examples, not independent sessions.
Yahoo Finance SPY daily dates filter out non-trading-day quotes. For replay,
one near-ATM call is selected from the signal-date chain,
with 7–60 days to expiry. Entry is the following available observation's ask;
exit is the subsequent observation's bid, always the **same contract**. Each gap
is limited to four calendar days. Costs add $0.65 commission and $0.01 adverse
price per share per side, using the standard 100-share multiplier. Missing future
quotes cause an omitted example, never retrospective replacement by another
contract. There is no verified underlying price, size or corporate-action feed;
this is quote-based research and does not validate adjusted deliverables.

VX features: last return, five/20-observation mean returns, 20-observation
volatility and positive-return fraction, all within one contract. Select the
highest-volume eligible contract using signal-date volume, at least seven days
before expiration. Buy the next observed day's open and exit its close, with
$1,000 per point, $3 commission and 0.05-point adverse slippage per side. Reject
invalid OHLC and volume below 100. No return crosses a contract roll.

Both replays use a $50,000 initial account, one contract at a time, and avoid
overlapping trades. VX reserves an assumed $10,000 collateral per contract;
historical exchange margin, intraday mark-to-market and forced liquidation are
not modeled. Daily OHLC and indicative option quotes cannot demonstrate actual
fills. Missing observations and source coverage introduce selection bias.

These models cover **SPY calls and VX futures only**: they do not establish
performance for puts, option spreads, ES/NQ, or options on futures.

## Completed run — 2026-11-07

Downloaded 783 weekday option responses (including empty days), 93 VX contract
CSVs and a SPY session calendar. Four VX URLs returned 403 and are recorded in
the local manifest. The dates below describe retained examples, not continuous
coverage guarantees.

| Model | Example date range | Train / validation / holdout | Holdout trades |
|---|---|---|---:|
| SPY calls | 2023-01-04–2025-12-31 | 413 / 761 / 1,659 | 0 |
| VX futures | 2017-06-07–2025-12-31 | 1,653 / 251 / 250 | 0 |

Both models were actually fitted and saved. Neither selected a trading threshold:
each validation threshold produced zero trades, so the selected policy stayed
in cash (0% holdout return). **No profitability was demonstrated.**

The options archive is particularly unsuitable for evaluating this near-ATM
policy: after contract matching and market-session filtering, there are **zero
replay-eligible validation examples**. Its classifier can be trained on other
matched calls, but this is not a completed assessment of an executable options
strategy. The report labels this `insufficient_replay_coverage`.

Holdout prediction results also do not demonstrate an edge:

| Model | Classification accuracy | Training-majority baseline | Brier score | Constant baseline Brier |
|---|---:|---:|---:|---:|
| SPY calls | 76.25% | 77.94% | 0.18042 | 0.17632 |
| VX futures | 66.00% | 66.00% | 0.22501 | 0.22466 |

Lower Brier is better. Labels mean a positive after-cost outcome for the defined
long-contract trade, not raw market direction. The high options accuracy largely
reflects an imbalanced target; balanced accuracy was approximately 50.19%.

Derived-example SHA-256:
- SPY calls: `1678e14f156c8be0a1d4d2f6cf7fbf19c2546e55b2f4a043a0207fc194c3e4ac`
- VX futures: `39d73eec59bccd1ccb16ecb03cbe7b35dc3b31f5b99a8de21bf361216bb01227`

Model files: `state/public_derivatives/SPY-options-report.json` and
`state/public_derivatives/VX-futures-report.json`. These are local research
artifacts; the website's trading policy remains separate.
