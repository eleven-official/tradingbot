# Cloud deployment verification — 2026-11-01

Verified application revision: `d961b65`.

## Production

- Existing Loki: https://lokitrading.vercel.app/#cloud-research
- Research worker: https://loki-cloud.vercel.app
- Both Vercel projects deployed successfully from GitHub main.
- The reviewed initial research schema is installed in the existing Supabase
  project. Existing `loki_*` and `member_*` tables were retained.
- Both production apps have the shared server-only bridge configuration.
- The verified Joshua Auth account has the research operator role.
- GitHub Actions has the worker origin and scheduler secret configured.
  Manual run [41298952787](https://github.com/eleven-official/tradingbot/actions/runs/41298952787)
  completed successfully and received the authenticated worker's `idle` response.

## Checks completed

- 46 cloud/UI tests, TypeScript checking and Next.js production build passed.
- Signed production state reads returned the operator profile for its owner
  and the default researcher profile for the other existing account.
- Replayed assertions, invalid signatures and nonexistent Auth users returned 401.
- Unauthenticated state and optimizer requests returned 401.
- Authenticated optimizer invocation returned 200 with no queued work.
- Database catalog checks confirmed research RLS and restricted mutations/RPCs.
- Reviewed transaction-only checks verified tenant isolation, role-write denial,
  nonce replay rejection, null/expired lease rejection and single-use holdout
  locking. The checks used the two existing Auth identities, created no Auth
  users, and rolled back the temporary research records.

## Deployment fixes

- Internal optimizer implementation moved to `cloud/services/optimizer.ts`.
  A root `cloud/api/optimizer.ts` was discovered as a standalone Vercel Function
  and shadowed the Next.js route, causing a production-only module-loading error.
- Missing scheduler configuration now fails the workflow rather than returning
  a misleading green result.
- `.vercelignore` excludes local secrets, databases, memory and runtime state.

## Remaining evidence and inputs

- The production browser is still at Loki's access gate. An ordinary signed-in
  browser walkthrough of the original-site bridge remains unverified.
- No historical datasets or optimization campaigns are queued in the cloud.
  Licensed history/provider credentials must be supplied before useful work can run.
- The deployed service credential is the existing Supabase server credential;
  this deployment did not rotate it.
- Cloud broker execution is disabled and unimplemented. Deployment and an idle
  worker response do not establish a profitable model or a 75% performance result.
- GitHub's five-minute schedule is approximate and may be delayed.

## Model state (2026-11-01)

The instrument direction model (`loki_instrument_daily_logistic_v2`) and the
market-direction research model (`loki_market_direction_logistic_v2`) now fit
to convergence with damped ridge Newton steps (λ=0.01, max 25 iterations,
tolerance 1e-9) instead of 60 fixed-epoch full-batch gradient descent. The
convex problem is solved to the maximum-likelihood optimum, so the same
features, splits and frozen evaluation windows are unchanged; previously saved
v1 artifacts remain comparable and loadable. No performance change is claimed:
recompute validation and test evidence when licensed history is supplied.

## Rich instrument family (2026-11-01)

The research protocol gained a separate rich daily family
(`loki_instrument_daily_rich_v3`, `core/fusion/paper_models_rich.py`): nine
causal OHLCV features (last/5/10/20-session means, 20-day volatility, 14-day
ATR% and stochastic range, overnight gap, 10-day momentum) fit with the same
ridge Newton solver. Threshold selection runs the frozen validation table
through a doubled-cost gate (at least 5 trades, positive 1x and 2x net and
expectancy, drawdown at most 3%); the final 20% stays diagnostic. The v3
family is accepted by `paper_evidence.assess` and the workspace compare pin,
and is trained on the cached Yahoo datasets: all six instruments (SPY, QQQ,
AAPL, MSFT, NVDA at 20y; TSLA at 15y) report `no_validation_edge_wait_in_cash`
— the only validation candidate that cleared 1x costs (AAPL 0.55, +0.02%)
failed the doubled-cost gate (−1.6%). Whole-unit sizing also skips entries
when the 1000 USD cap cannot afford one unit. No edge is claimed; the family
ships as honest cash-only research tooling alongside v1/v2.
