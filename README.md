# Loki Trading Workspace

One Python application combines Loki Fusion research, the v8 strategy engine,
market planning, broker sessions and Supabase persistence.

## Run locally

Requires Python 3.12. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_desktop.txt
.\.venv\Scripts\python.exe launch_loki_fusion.py --port 8123
```

Open http://127.0.0.1:8123/. The local launcher enables private native tools and
broker sessions only for loopback, same-origin requests with its session token.
Use `--config fusion.config.local.json` for optional private engine settings;
copy the example file and keep local settings outside Git.

## Integrated features

- Quant lab: imported OHLCV, factor diagnostics, purged walk-forward evaluation,
  pullback research, cost assumptions and benchmark comparisons.
- Agent council: inspect deterministic reviews and provenance. Viewing a council
  never places an order.
- Paper portfolio and simulated market: practice ledgers, synthetic regimes,
  limits/stops and scenario stress. Synthetic results cannot establish an edge.
- Broker connection: Alpaca paper/live keys and supported exchange inspection
  keys stay in local server memory for up to four hours, outside browser storage,
  exports and source control.
- Alpaca paper AI: explicitly train on 5 or 10 years of completed daily history,
  inspect training/validation/test dates, then Start/Pause the runner. It pauses
  when its page is hidden; venue orders and positions remain until reconciled or
  explicitly canceled. Live automation is disabled.
- Advanced terminal: the merged v8 multi-factor engine, TTM Squeeze, CMF, regime
  monitor, backtests, Monte Carlo scenarios and parameter trainer. Its explicit
  paper loop manages stops/risk against an independent local simulated balance.
- Market planner: public Binance snapshots, six-role paper council, daily
  loss-cap estimates, risk sizing and a context-aware local coach.
- Research desk: preserved CSV paper agent, versioned strategies and local
  profile at `/research-desk`.
- Supabase vault: shared server-only transport for the engine and domain manager.
  See [setup](SUPABASE_SETUP.md).

Manual Kraken real orders use the separate host-enabled preview/confirmation
workflow and journal. Selecting Real places no order. Broker credentials and
market entitlements are necessary for actual account access.

## Evidence and limits

**A 70% closed-trade win rate has not been proven. Future returns are not
guaranteed.** The v8 trainer reserves the final 20% of downloaded history before
development search/refinement. Reports label validation reuse, final-holdout
metrics, fingerprints and trade counts. Repeated inspection and multiple
experiments mean a strong holdout remains exploratory. Costs, profit factor,
losses and drawdown matter alongside win rate. Applying parameters changes the
running engine globally. A cross-symbol consensus is a research proposal.

The optional Yahoo/yfinance feed supplies observations, not commercial data
rights or brokerage streaming. Use entitled data or appropriately licensed
imports for commercial deployment. Installation creates no paid data account.

The private Supabase vault is single-server storage, not customer authentication
or tenant isolation. Native broker tools are unavailable to public/Vercel
clients. A customer-facing account service needs owner-scoped authentication and
database policies before private remote operations are enabled.

Provenance/license boundaries remain in `components/` and `third_party/`.
Fincept loads from a separately configured licensed private installation.
Retained MiroFish code carries AGPL notices. Optional model/graph/simulation jobs
need their configured dependencies and provider credentials.

## Tests and deployment

```powershell
python -m pip install -r requirements_test.txt
python -m pytest -o addopts= tests/ -q
```

GitHub checks run offline; broker/database transports are mocked. `vercel.json`
explicitly selects FastAPI with `main:app` and bundles templates/static assets.
The historical Next.js prototype remains in `app/`; it is not the deployed
application. Long-running local paper loops are not serverless jobs.

See [the integration inventory](docs/GITHUB_UNIFICATION.md) for branch provenance,
conflict resolutions and environment-dependent checks.
