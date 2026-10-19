# GitHub upgrade integration — 2026-10-19

Repository: `eleven-official/tradingbot`.

| Source | Integrated result |
| --- | --- |
| `main` at `2d5512c` | v8.7.4 strategies, smart exits/sizing, trainer, indicators, Monte Carlo, regimes and terminal |
| `merge/unify-loki-main-2026-10-19` at `e79dc65` | Merge ancestry for main, Fusion, dashboard/council, planner, Supabase and Next.js prototype |
| `codex/loki-research-copilot-upgrade` at `79a189a` | Fusion UI, integration boundaries, synthetic exchange, historical research and manual-order workflow |
| Local checkpoint `f196962` | Broker sessions, Alpaca paper runner and 5/10-year models preserved before upstream merge |
| `codex/dashboard-council-research` at `5747a9c` | CSV agent, versioned strategies, local profile and research desk at `/research-desk` |
| `codex/paper-risk-planner` at `c1c0f78` | Planner, snapshots, candle replay, six-role council and chat at `/paper-tools` |
| `codex/ci-reliability-and-portfolio-foundation` at `012ee83` | Unique stateless portfolio module, `/portfolio/summary`, tests and Dependabot ported selectively |
| `improve/next-level-strategy` at `b050f81` | Unique order-book tracker, execution-planning primitives and weighted strategy interface ported with compatibility alias |
| `feature/live-paper-candles` at `2e40b05` | Newer merged public-candle adapter supplies capability; obsolete backend/dashboard replacement not applied |
| Backup/selective-auth/cleanup/Vercel branches | Duplicated ancestry/prototypes retained by upstream unification; no customer-auth implementation inferred |

Fusion remains the entrypoint. Advanced v8 routes are namespaced at `/terminal`.
Older tools use isolated styles/scripts in the same Python application. The
Next.js prototype does not replace the FastAPI deployment.

## Repaired defects

- Duplicate TOML tables/dependencies and missing deployment assets.
- Broken Docker packaging: include the actual core/strategy/UI sources, use a
  non-root runtime with readable dependencies, and smoke-test before release.
  Container publication targets this repository and occurs only on a release.
- Council GET placing paper orders; default-password/arbitrary-bearer auth;
  mock strategy controls; fabricated fallback order prices; fake live fallback.
- Unbounded order/loop inputs, missing exit management in the background loop,
  ignored paper-stop requests and leaked private account endpoints.
- Incorrect crypto ticker normalization, single-ticker quote parsing and stale
  history cache.
- Duplicate Supabase clients, modern secret-key headers, redirected credentials,
  exposed provider errors and configured/verified status confusion.
- Missing RLS/browser grants; connection tests inserting fabricated trades.
- Refinement reusing all later data: final 20% is now reserved separately, with
  validation reuse, consensus limitations and unproven target labels.

## Environment-dependent checks

Offline tests/browser fixtures do not validate funded execution, hosted Supabase
permissions, real Alpaca data entitlements or provider-backed MiroFish jobs.
No real financial trade is part of verification. Passing software tests does not
prove 70% winning trades.
