# Local verification — 2026-11-01

## Verified

- Latest full suite: **934 passed, 50 subtests passed**, 3 dependency deprecation
  warnings, no failures (145.96 seconds). No application code changed afterward.
- `git diff --check` passed; Git reported only Windows line-ending notices.
- Running local workspace: `http://127.0.0.1:8178/#simulated-market`.
- Health, model catalog and all four current daily forecast endpoints returned
  HTTP 200. SPY, QQQ, AAPL and MSFT v3 bundles loaded with no unreadable bundles.
- All forecasts returned WAIT with explanatory checks, using completed candles
  through 2026-10-30. Broker execution is disabled for this research model.
- All eight Supabase vault/account tables passed live read-only checks.
- Alpaca paper API: ACTIVE, unblocked, no positions. Browser/server paper
  connection restored after the backend restart. Runner remains stopped with
  zero AI-owned units; no automation start was requested.
- The previously requested one-share AAPL buy remains accepted/queued while the
  equities market is closed. It was not created, canceled or modified during
  final verification. Review it in the broker before trying to start a clean
  AAPL AI runner.

## Limits and handoff

- Functional software and passing tests do not establish profitable predictions.
  No evaluated model currently passes all trading-readiness gates.
- Futures/intraday implementation is tested, but real training still needs
  licensed, correctly timestamped actual-contract/session historical data.
- The local broker link expires/disconnects on restart; saved research and venue
  orders persist. A browser heartbeat is still required for the old paper runner.
- These are local changes, not proof that a hosted deployment has been updated.
- Rotate credentials exposed in chat before public/production use and update
  private server settings. Do not commit `.env` or private state snapshots.
- See `HISTORICAL_ANALOGUE_MODEL.md`, `ACCOUNT_STORAGE.md` and `LOKI_MEMORY.md`
  for model, account/session and memory setup details.
