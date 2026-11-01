# Loki Cloud

Next.js / Supabase historical-analogue research application. Existing Python trading/model behavior is preserved. Production research work runs in Vercel functions and Supabase; no local worker or filesystem is required. Local commands below are build/test tooling only.

**Current Loki integration:** the existing workspace now includes a Cloud research section with its own signed server bridge and shared account identity. See [`../docs/CLOUD_INTEGRATION.md`](../docs/CLOUD_INTEGRATION.md) for the two-deployment / same-Supabase setup. Standalone deployment below remains supported. The existing local algorithms and broker runner are preserved, not ported into this Next.js runtime.

## Implemented / not implemented

- Supabase cookie-based login, confirmation callback, persistent sessions, RLS tenant isolation, read-only researcher and privileged operator roles.
- Historical data ingestion, causal12 vectors, pgvector retrieval with weighted reranking, bounded resumable optimization, trial ledger, one-use final holdout.
- Responsive dashboard with 15-second polling, research metrics, campaign controls and recorded trade/equity/position displays. Empty state is not fabricated broker data.
- **Not implemented:** broker credentials storage, order execution, broker reconciliation, live signals, options exercise/assignment, live position ingestion. `TRADING_ENABLED` is reserved and does not enable anything. Do not treat this as a ready-to-trade system.
- No model or 75% performance claim is shipped. Actual provider coverage and entitlements must be verified.

## Deploy

1. Use a **new Supabase project**. Review and run `schema.sql` once in its SQL editor. It is an initial schema, not a rerunnable migration. Do not apply it blindly to the legacy Loki database. It creates pgvector in `extensions`; Supabase Auth and the `supabase_realtime` publication must exist.
2. In Supabase Auth, enable email/password and email confirmation, set the deployed site URL and allow `https://YOUR_DOMAIN/auth/callback`. Configure production SMTP, password policy, and Auth rate limits. Disable public signup if this is a private workspace.
3. Import the GitHub repository in Vercel; select **`cloud` as Root Directory** when the repository is `tradingbot`, Next.js framework, Node 24, install `npm ci`, build `npm run build`.
4. Copy the variable **names** in `.env.example` into Vercel production environment settings. Obtain public URL/publishable key and server-only service key from the **new** Supabase project. Set a newly generated random `CRON_SECRET` of at least 32 characters. Never put the service key in `NEXT_PUBLIC_*`. Rotate previously exposed legacy credentials separately.
5. Configure server-only licensed `ALPACA_DATA_KEY` / `ALPACA_DATA_SECRET` if using provider ingestion. The built-in adapter requests **IEX daily split-adjusted bars**, not consolidated SIP, total-return history, intraday options or futures. It will wait on missing coverage rather than invent 20 years of data.
6. Deploy through Vercel's GitHub integration. The default scheduler is `.github/workflows/cloud-worker.yml`, compatible with Vercel Hobby: set repository variable `LOKI_CLOUD_WORKER_URL` to the verified production `https://PROJECT.vercel.app` origin and repository secret `LOKI_CLOUD_CRON_SECRET` to the same value as the worker's server-only `CRON_SECRET`. GitHub runs one authenticated tick approximately every five minutes; schedules may be delayed or disabled by GitHub for inactivity. Use `workflow_dispatch` for a manual authenticated tick. No paid Vercel Cron is required. Never expose an unauthenticated manual trigger. Preview deployments must not share production secrets/datasets.
7. Sign up and confirm email, then grant your account operator access in SQL (replace UUID from Supabase Auth):

```sql
insert into public.profiles(id,role) values ('AUTH_USER_UUID','operator')
on conflict(id) do update set role=excluded.role;
```

8. Create a dataset, observe ingestion and any missing-data state, then queue an explicit trial budget. Sign out/in and verify your session and another user's isolation. Check Vercel function logs and Supabase query/storage usage. Nothing is deployed merely by generating these files.

### GitHub Actions

`../.github/workflows/cloud-ci.yml` installs the locked dependencies, tests, typechecks and production-builds on changes to this application. Vercel's Git integration performs deployment; no deployment token is embedded in Actions. Enable branch protection and require CI before merging. Configure Supabase/Vercel accounts and select your repository/project yourself before a real deployment.

## Research protocol

Daily provider features use 21 completed bars. Signal at completed session t is labeled by next session open-to-close long return, less round-trip fees and slippage. Train/validation/final boundaries are chronological 60/20/20; labels crossing a boundary are excluded. The training reference pool stays frozen throughout validation and final evaluation. Validation is **development**, not unbiased proof.

Each scheduled invocation claims one task with a 90-second lease. Ingestion writes at most 10,000 raw bars or 500 features; evaluation handles at most 16 examples. Checkpoints, trial results and the final-holdout lock commit atomically. A worker without the current unexpired fencing token cannot checkpoint; pause clears that token. Errors leave the last committed cursor intact for later lease-based resume. Failed work can retry on subsequent ticks; monitor repeated 503s and pause the campaign rather than assuming progress.

Candidates deterministically vary k, confidence, distance, 12 indicator weights and risk fraction. This is bounded parameter search, not a trained neural network. pgvector retrieves at most 256 candidates using unweighted Euclidean distance, followed by weighted reranking; this is not an exact full-dataset weighted k-NN guarantee. Training analogue outcomes are deduplicated by UTC outcome date; evaluated opportunities exclude overlapping label intervals. These restrictions reduce apparent independence inflation but do **not** establish IID returns or eliminate all serial dependence. Wilson bounds are screening gates, not rigorous financial confidence guarantees.

Qualification requires at least 400 executed historical signals, 100 per regime, overall and per-regime 95% Wilson lower bounds ≥75%, positive net return and positive doubled-cost aggregate expectancy, Brier improvement over training base rate, and ≤10% simulated drawdown. Simulated wealth allocates the candidate fraction to each nonoverlapping long trade; cash earns zero. No dividends, borrow, tax, corporate-action universe or delisting engine is modeled. Do not infer return forecasts from this simplified backtest.

A passing development candidate is frozen and consumes the final holdout **before reading it**. Failure blocks certification; retuning on that holdout is not supported. Budget exhaustion enters `waiting_new_data`; new independent data/review is required. Uploading duplicated data to obtain a fresh dataset ID is not new evidence. Cross-dataset duplicate fingerprint enforcement is not implemented, so this requires operational governance. With 20 years of daily data, a four-year final slice may have too few qualified opportunities per regime to pass; abstention is expected.

Every five-minute tick evaluates at most 16 opportunities: 1,000 examples take roughly 5.25 hours per candidate before database latency/retries. A 128-trial campaign can take weeks. Size budgets and paid cloud capacity accordingly; continuous does not mean unlimited free compute or guaranteed convergence.

## Licensed upload API

Authenticated **operators only**, same-origin browser requests with Supabase session cookies:

- `POST /api/datasets`: `{ "symbol":"SPY", "asset_kind":"stock", "timeframe":"1d", "years":20, "source":"upload" }`. Options use `asset_kind:"option"`; supported timeframes: `1d`, `15m`, `5m`.
- `POST /api/ingest`: `{ "dataset_id":"UUID", "features":[...], "finish":false }`. At most 500 rows per request, chronologically ordered across batches. Finish seals the dataset after minimum span/day checks; it does not approve provenance.

Each feature requires `observed_at`, `outcome_at` (ISO timestamps, future labels rejected), `embedding` (12 finite values in [-1,1]), `regime` (`up`, `down`, `range`, `stress`), `net_return` (after modeled costs), `cost_return` (incremental return cost for doubled-cost stress), and `contract_key` (empty for stocks). Match stock embedding generation in `services/features.ts`. You are responsible for causal computation and licensing; bounds and dates alone cannot prove causality.

Options require an OCC key such as `SPY261218C00600000` matching the dataset underlying and `option_context:{delta,iv,dte,moneyness,entry_ask,exit_bid}` at the relevant historical times. Entry ask and exit bid must be executable historical quotes, not today's quotes or underlying-stock proxies. The API recomputes vector components 8–11 and quote-based net returns plus commission; delta, IV, DTE and moneyness must be known at signal time. This is a long-option quote research input, not an option trade simulator. Splits, expirations, liquidity and survivorship require dataset audit.

After checking source licensing, complete coverage, timestamp ordering, causal features, quote freshness, splits, Greeks, horizons and costs, an administrator can explicitly approve a dataset:

```sql
update public.market_datasets set source_verified=true
where id='AUDITED_DATASET_UUID' and source='upload' and status='ready';
```

Never approve based solely on backtest performance. Uploads remain unverified until this audit; certification is blocked. Provider imports are marked provider-verified, which describes provenance only, not data quality or an independently audited market history.

Other APIs: `POST /api/jobs` accepts `dataset_id`, `max_trials` (1–512); `PATCH /api/jobs` accepts `id`, `action` (`pause`/`resume`). Failed final holdouts cannot be resumed. Dataset quota is 20 per user; concurrent campaign quota is 3. These application-level quotas are not transactionally race-proof billing controls: restrict operator grants and apply platform spending limits.

## Verification

```bash
npm ci
npm test
npm run typecheck
npm run build
```

Builds require no real database credentials; runtime needs configured variables. Unit tests cover metrics, causal feature bounds, analogue deduplication/leakage, optimizer transitions, ingestion failures and HTTP boundaries. They do not replace deployed database RLS/lease concurrency tests or live provider integration tests. `tests/database.sql` supplies rollback-only tenant-isolation, privilege, stale-lease and single-use-holdout checks for a disposable Supabase project; it has not been executed against a live database. Before production, validate schema execution, concurrent lease/final-holdout claims, worker crash recovery, auth confirmation/session refresh and provider coverage. The schema has not been applied to the existing database by this code-generation task.
