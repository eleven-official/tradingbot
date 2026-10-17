# Reproducible strategy validation

Loki's new research integrations are implemented and tested as software. Their
existence does not establish better returns or a 70% winning-trade rate. A valid
commercial claim needs appropriate data rights and strategy-specific evidence
after fees, slippage and losses. Win rate alone is not profitability.

## Data rights and the private historical audit

The earlier downloaded Vision snapshots and their derived audit artifacts are
kept in ignored local research storage. They are not bundled in Loki, displayed
as commercially licensed evidence, or distributed with this repository.

The publisher's current terms apply noncommercial conditions to the datasets and
derived analyses and require a separate agreement for commercial use. See the
[official dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).
That source must not be treated as licensed input for this commercial product.

The format implementation accounted for the publisher's documented 2025 spot
timestamp-unit change and archive checksums. See the
[official format documentation](https://github.com/binance/binance-public-data).
Those technical checks establish format/integrity, not commercial permission.

No public product-performance assertion is made from that private audit. No
strategy is promoted to live trading. Prior results must not be relabeled as a
new untouched holdout after parameters are changed.

## Operator-supplied licensed input

`scripts/validate_frozen_research.py` performs no downloads. It accepts local
normalized snapshots and provenance manifests. Its default paths point to an
empty ignored `licensed-research` directory, not the downloaded snapshots. The
default usage context is `commercial_research`.

Each daily/intraday directory needs a `manifest.json`. A minimal shape is:

```json
{
  "source": "Operator's licensed provider and dated export",
  "interval": "1d",
  "quote_currency": "USDT",
  "usage_rights": {
    "basis": "Actual written agreement or owned data rights",
    "reference": "Operator's license document/version or contract record",
    "permitted_uses": ["commercial_research"]
  },
  "training_snapshots": {
    "BTCUSDT": {
      "file": "BTCUSDT-training.json",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256",
      "rows": 1461,
      "start": "2021-01-01T00:00:00+00:00",
      "end": "2024-12-31T00:00:00+00:00"
    }
  },
  "snapshots": {
    "BTCUSDT": {
      "file": "BTCUSDT.json",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256",
      "rows": 1826,
      "start": "2021-01-01T00:00:00+00:00",
      "end": "2025-12-31T00:00:00+00:00"
    }
  }
}
```

Repeat the entries for `ETHUSDT` and `SOLUSDT`. Each JSON snapshot is an array of
`{timestamp, open, high, low, close, volume}` completed candles. Exact-byte SHA-256
digests and metadata are verified; daily training is a separate file so freezing
does not inspect the reserved daily test prices.

The intraday manifest uses `interval: "5m"` and snapshot names such as
`BTCUSDT-5m-2024-01` and `BTCUSDT-5m-2025-01`, with the same file/hash/rows/start/end
metadata. It needs January, April, July and October for each of those years and
all three symbols. Do not concatenate nonadjacent months. Optional `sources`
entries may identify retained raw archive URLs and SHA-256 digests; when present,
the corresponding local `raw/` files and `.CHECKSUM` sidecars are verified too.

Permission references are operator assertions; the tool does not grant a license
or authenticate a contract. Input dates, point-in-time availability, split and
corporate-action treatment, and any previous inspection still need substantiation.

## Freeze, then evaluate

From the repository root, using appropriately licensed local snapshots:

```console
python scripts/validate_frozen_research.py freeze --daily PATH_TO_DAILY --intraday PATH_TO_5M
python scripts/validate_frozen_research.py evaluate --daily PATH_TO_DAILY --intraday PATH_TO_5M
```

The first command writes an immutable code/configuration checkpoint before
opening training prices, then records training-only trend selections in a second
sidecar. Existing checkpoints are never overwritten. The second verifies code,
manifest and snapshot hashes before loading test observations and refuses to
overwrite an existing result. Both checkpoints and results default to ignored
local storage. Code changes invalidate the matching checkpoint. Keep dated
immutable source copies when preserving an earlier research run.

The fixed protocol trains the existing three-pair trend candidate set on daily
2021–2024 data and tests daily 2025. Each 5-minute 2024 month selects its recipe
for the matching 2025 month, with 60 test-month bars reserved for warmup. Cash is
a valid training decision. The Fusion rule is frozen without a parameter search.
Each asset/month is an independent 10,000 USDT research account; returns are not
combined into a fictional portfolio.

Signals use completed candles and opening fills on the next candle. Base fees
are 10 basis points and adverse slippage 5 basis points on each side; fixed
parameters are also tested at twice and three times those costs. Every result
includes trades, downsampled equity, benchmark, drawdown, net expectancy, win
counts and descriptive Wilson intervals. Correlated trades make those intervals
too weak to certify a persistent win rate. No historical test guarantees future
profitability, execution or a 70% win rate.

## Council evidence boundaries

The Fusion council labels itself `deterministic_role_pipeline`. It does not call
AutoHedge's LLM agents. Missing news produces missing sentiment evidence. Existing
asset and total portfolio exposure reduce new-position capacity, quote currencies
must agree, and entry/exit costs enter stop sizing and reward/risk checks.

An existing trend-strategy report cannot validate the different Fusion factor
rule. Every draft is `executable: false`; the evidence gate blocks promotion by
default. Explicitly disabling the gate allows hypothetical paper planning only.
A single portfolio snapshot cannot establish its equity high-water history or
enforce a full account drawdown limit.
