# Strategy Lab

Strategy Lab measures a reproducible trend strategy against supplied historical
OHLCV bars. It does not place orders, fetch market data, update a learner, or enable
live trading. No historical result guarantees future profitability or a 70% win
rate. The lab reports win rate separately from return, drawdown and trade expectancy.

## Evaluate a dataset

The dependency-free command-line runner writes a complete JSON report:

```bash
python run_strategy_lab.py daily_ohlcv.csv --fee-bps 10 --slippage-bps 5 --periods-per-year 252 --output reports/research.json
```

It also accepts a JSON list of bars and `--config path/to/settings.json` for other
`LabConfig` settings. Command-line options override corresponding settings in the
config file. The input dataset is never altered.

```python
import csv
from core.strategy_lab import evaluate_strategy

with open("daily_ohlcv.csv", newline="", encoding="utf-8-sig") as source:
    report = evaluate_strategy(list(csv.DictReader(source)), {
        "fee_bps": 10,
        "slippage_bps": 5,
        "periods_per_year": 252,
    })

print(report["status"])
print(report["summary"])
print(report["rejection_reasons"])
```

CSV/JSON records require `timestamp,open,high,low,close,volume`. Timestamps must be
unique, ISO8601 and increasing. Naive timestamps are interpreted as UTC. DataFrames
are accepted without requiring pandas at runtime; their index supplies timestamps
when a timestamp column is absent. Prices must be finite and positive, candles
consistent, and volume non-negative. The default settings require at least 161
bars. Inputs are limited to 10,000 bars per run.

Set `periods_per_year` to the bar frequency: 252 for daily exchange sessions,
365 for daily continuous-market bars, and the appropriate count for intraday bars.
The lab does not infer exchange calendars. Correct corporate actions, survivorship
bias, point-in-time availability, missing bars and data provenance remain the
dataset provider's responsibility. A SHA256 fingerprint identifies the exact
normalized dataset evaluated.

## Evaluation process

1. Expand the training window chronologically. Exclude at least one gap bar from
   fitting before each later test window.
2. Compare only three fixed moving-average pairs (5/20, 10/40 and 20/60) on the
   training window, after costs. Stay in cash if none beats a zero training score.
   Record every candidate in the returned trial ledger.
3. Enter long when the completed close and fast mean exceed the slow mean. Size
   the entry using completed-bar volatility and the configured entry exposure cap.
   Keep that entry size until an exit. These are entry sizing limits; exposure and
   volatility may drift as prices change.
4. Execute each signal at the next open. Exit when the completed-bar trend fails
   or its close falls below the trailing close threshold. Gap losses can exceed
   that threshold. No high/low intrabar ordering is assumed.
5. Deduct adverse slippage and fees on entry and exit, then liquidate remaining
   holdings at each fold's last close. Join only forward test equity to calculate
   headline metrics. Initial capital is included when computing drawdown.
6. Compare with full-exposure buy and hold over the same forward windows, with
   the same entry/exit costs and fold liquidations.
7. Re-run the chosen forward strategies at 1x, 1.5x, 2x and 3x fees/slippage,
   holding the selected parameters fixed.

Completed prior bars, including the gap bars, can warm up indicators at the start
of a test window. No test-window observation enters that fold's parameter choice.
Earlier test data becomes past training data in later expanding folds. A future
change to the grid or strategy requires fresh untouched data for reliable research.

## Reading results

`summary` includes net return, annualized return, Sharpe, maximum drawdown, net
trade expectancy, fees/slippage and a descriptive 95% Wilson interval around the
observed trade win rate. A small sample can have a wide interval despite a high
observed win rate. Trades can be dependent, so the interval is not a guarantee and
can understate actual uncertainty. Sharpe assumes a zero risk-free rate.

No-trade win rate and expectancy are `null`. Profit factor is `null` without any
losing trades; an unbounded ratio is not proof of a safe strategy. The report is
strict JSON and includes all net closed trades, equity, fold results, configuration,
trial counts, the dataset fingerprint and explicit modeling assumptions.

`needs_more_evidence` identifies any unmet research check: too few trades,
nonpositive forward return, failure to beat the baseline, excessive drawdown, too
few profitable folds, or nonpositive return under 3x costs. `paper_candidate`
means only that these retrospective checks passed. It never changes trading mode.
Choose research limits before inspecting results to avoid moving the goalposts.

The model excludes spreads beyond configured slippage, market impact, funding,
taxes, dividends and execution latency. A zero-volume completed bar blocks the
next entry; exits still assume liquidity. Buy-and-hold can take more market risk
than the strategy because it uses full exposure. Validate separately on fresh
data and paper execution before considering any real capital.

Run the deterministic offline regressions with:

```bash
python -m unittest discover -s tests -p test_strategy_lab.py -v
```
