# Historical market learning

Quant lab's **Fetch history & train** downloads the canonical daily market factor
published by Stoeckl and Pukrop's Open Crypto Pricing project. No registration,
personal account, key or paid subscription is used. Downloads are bounded,
validated, cached for 24 hours per server worker, and fail without synthetic
fallbacks. The application never downloads the underlying vendor coin data.

Source: [Open Crypto Pricing](https://opencryptopricing.com/download.html),
[publisher's Hugging Face dataset](https://huggingface.co/datasets/sstoeckl/opencryptoassetpricing).
Their **factor series** are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Commercial reuse requires attribution. Loki displays the credit and includes it
in exports. This license does not cover the underlying CoinGecko/CoinMarketCap
coin histories. The current source has daily data starting in December 2013;
actual coverage is reported from the downloaded file.

## What learns

A fixed regularized logistic classifier predicts the sign of a future **daily
excess-market-return factor**. This is actual supervised model fitting, separate
from Loki's deterministic conversational assistant and the OHLCV trading rules.
It does not fine-tune an LLM. Input features are the last return, five- and
twenty-day means, twenty-day volatility, and the fraction of positive days.
Features end two days before each target. Missing dates reset the window.

Weights and normalization use target dates through 2023 only. The 2024 period is
validation; it never tunes the settings or weights. Headline tests start in
2026. The previously inspected 2025 market period is excluded from those tests.
The schedule is 60 full-batch gradient steps, learning rate .08, L2 penalty .01;
there is no search over models or thresholds. Scores are not calibrated trade
win probabilities. Results include direction and balanced accuracy, Brier error,
a constant training-frequency baseline, fixed .60 positive-signal precision,
date counts, per-year tests, all weights, data fingerprints and a model hash.

Direction accuracy is not completed-trade win rate. Factor returns are not
execution quotations: no OHLCV, volume, fills or profit are fabricated from them.
The factor design was chosen retrospectively by its publisher, and revisions
and publication latency can create hindsight bias. Historical evaluation remains
exploratory; no untouched-holdout certification or 70% trading edge is claimed.
No model can enable broker trading through these routes or council approval.

## Reproduce and scale locally

```powershell
python scripts/train_market_research.py --public --output .test-tmp/learning/run-001.json
python scripts/train_market_research.py --csv path/to/licensed-returns.csv --output .test-tmp/learning/run-002.json
```

Local CSVs use `date,CMKT` with one observed daily return per date, decimals
(`.01` = 1%), and strictly increasing ISO dates. The offline loader accepts up to
250,000 observations and a 100 MB file. More rows are not automatically more
independent evidence; duplicated assets, revised factors, and overlapping
returns must not inflate sample counts. The fixed historical date partitions
must contain at least 200 training labels, 50 validation labels and 50 test labels.

Each CLI experiment first saves the exact normalized dataset and a protocol with
code and input hashes before fitting/evaluation. It then writes the JSON report
and model. Existing files are never overwritten; choose a new run name. Keep
the dataset, protocol and result together for reproduction. The JSON contains no
executable model deserialization. Treat an untrusted externally supplied model
as data and validate it before using it for any separate prediction workflow.

The browser button trains this same small benchmark model independently of the
active OHLCV upload. Full results and the trained model can be exported, and
Talk to Loki can explain the supplied report. A failed source request leaves
the previous completed report labeled as the previous report; it never invents
new evidence. Training and testing do not change the paper portfolio.

## Other research candidate

The separate pullback button compares three declared RSI/band/ATR hypotheses
using only the first 60% of an uploaded OHLCV history; the remainder tests the
chosen recipe. It can select cash. It uses next-open entries, adverse costs,
stop-first ambiguous bars, gap-aware stops and prior-volume sizing, and repeats
tests at doubled/tripled costs. Repeatedly exploring that same split does not
create a fresh holdout. No profitable market edge is established for this rule.

## Attribution

Stoeckl, S. and Pukrop, M. (2026), **Open Crypto Pricing**, University of
Liechtenstein. Factor series adapted by Loki under CC BY 4.0. See also Liu,
Tsyvinski and Wu (2022), *Journal of Finance* 77(2), and Fieberg, Günther, Poddig
and Zaremba (2024), *International Review of Financial Analysis* 92.
