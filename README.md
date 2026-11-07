# Loki Trading Workspace

One FastAPI application: the information workspace at the gate, a Supabase-gated sign-in, AI paper trading, a market planner, research and strategy lab surfaces, news desk, watchtower, and the "Bored?" game — Loki Dive, a nova-deep trivia ride with seven 25-second rounds per dive, streak combos, typo forgiveness, and example answers after every miss — plus a browser-held Alpaca paper order rail and an in-page autopilot with published, hand-railed rules.

Everything ships over Vercel: every push to `main` reaches https://loki-joshua-5183.vercel.app through the connected Vercel project. Access is code-gated; the gate code lives in the deployment env, not in this repository.

## Integrated cloud research

The current workspace includes **Cloud research** at `/#cloud-research`, using
the existing Loki login through a signed server bridge. The Next.js optimizer
in `cloud/` runs separately on Vercel and shares the same Supabase Auth project.
Existing paper accounts, local models and broker controls are preserved; cloud
certification does not enable orders. This addition still requires deployment,
reviewed database setup and server environment configuration.

See [docs/CLOUD_INTEGRATION.md](docs/CLOUD_INTEGRATION.md) for the combined setup
and [cloud/README.md](cloud/README.md) for the worker and research protocol.

## Run locally

Requires Python 3.12. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8124
```

Optional environment variables: `LOKI_SITE_GATE=1` enables the gate (default code `flathead`; set `LOKI_SITE_CODE` to change it), `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` enable the login flow, Alpaca keys are browser-held and verify through the relay (`/api/broker/alpaca/*`) whenever the user enters them.

## Guarantees

- The honest-error contract: degraded states are visible, empty logs say empty, headline cards say "information, never advice", the autopilot's published rule is its contract, and the relay caps order size server-side regardless of what the panel says.
- Keys and secrets never enter the repository; the backup export excludes credentials.
- The "Bored?" game is entirely local: scores and dive history never leave the browser, and its rarity tiers are hand-written bank data, not measurements from other players.
- `pytest` (all Python tests), plus `node --test` for the two JavaScript test modules. The CI workflows in `.github/` run both on every push.

## Live markets

`/#live-markets` is a self-refreshing board (every ~15 s while the view is open and the tab is visible) covering crypto majors, US mega-caps, indices, commodities and FX, with session status, top movers, flash-on-change tiles and a personal watchlist saved in the browser. Clicking a tile opens its chart and the AI engine's review-only read for that symbol. Served by `loki/api/live_markets.py` (`/api/markets/live`, `/api/markets/quotes`); crypto comes from Binance Spot (live), everything else from Yahoo Finance (near-live). Failed feeds stay visible per tile.

## Live AI follows the verified rules

The AI paper trader (`/api/fusion/ai/step`) decides through `loki_v8/live_engine.py`, which mirrors `run_backtest` bar for bar: it scores only the last *completed* daily bar (today's forming candle is excluded), applies the same trend / regime / volatility gates and conviction / vol-target sizing, and manages open positions with the profile's time stop, breakeven lock, trailing stop and partial target. `tests/test_live_engine.py` replays backtests and checks the live planner agrees on every entry decision.

## 20-year universal profiles (current live AI)

`train_long_history.py` fits ONE rulebook for stocks/ETFs and one for crypto on daily data from 2004 (crypto from 2014), using the same `run_backtest` the live engine mirrors, with 10 bps fees + 5 bps slippage per side:

- **select** on the worse of development (2005-2018; crypto 2015-2020) and validation (2019-2022; crypto 2021-2022) scores;
- **report once** on the untouched holdout (2023 onward); the live AI only uses a block marked `verified` (made money on the holdout).

Results shipped in `loki_v8/training_report_snapshot.json` (`universal`), data through 2026-11-06:

| Holdout 2023→ | AI avg / yr | Profitable | AI avg worst DD | Buy & hold avg / yr | B&H avg worst DD |
|---|---|---|---|---|---|
| Stocks/ETFs (13) | +12.3% | 12/13 | −20.9% | +27.8% | −26.7% |
| Crypto (8) | +9.2% | 7/8 | −29.4% | +17.3% | −71.3% |

Stocks use trend-only scoring, entry at score ≥ 30, vol-target sizing (20%), and hold until price breaks its 200-day average (10 ATR protective stop). Crypto uses trend-leader scoring, entry ≥ 8, SELL-signal exit. The AI makes money out of sample but trails buy-and-hold in the strong 2023-26 bull market; its edge is far smaller drawdowns. Historical results, not a promise.

```powershell
python train_long_history.py --write-snapshot        # ~30 min on 4 cores
```

## Learning from mistakes

`loki_v8/mistake_model.py` replays the AI's own trades, records 15 market features at every entry's signal bar and whether the trade made money after costs, and fits a small regularised logistic model. Live and in backtests the same gate then skips setups whose estimated win chance is below a threshold. It is trained only on trades that had already closed before the window it is judged on, the threshold is chosen on 2019-2022, and it ships only if the 2023+ holdout is not worse. Current result: on for stocks (validation score 0.44 → 0.51; holdout same +12.3%/yr with 108 instead of 127 trades), off for crypto (no validation gain). Rerun with `python train_long_history.py --from-report state/long_history_report.json --write-snapshot`.

## Talk to Loki

Both the workspace "Talk to Loki" panel and the `/ai-chat` room share `loki/api/loki_brain.py`: name any ticker or coin and it runs the live AI engine and explains every check in plain English; it also answers market checks, the AI's track record, how the AI works, and ~30 trading terms. No external language model is used; questions about your own portfolio/research go to the context-aware copilot.

## Older per-symbol book

`loki_v8/train.py` still provides the earlier 10-year per-symbol walk-forward book (`python -m loki_v8.train`). The live AI uses it only as a fallback when no verified universal profile exists for an asset class.

## Layout

- `main.py` — Vercel/uvicorn entry point; `loki/api/` — the HTTP surface (server, gate, Supabase auth, news desk, market feed, Alpaca relay, fusion research, watchtower, terminal).
- `core/` + `core_engine` history reduced to what the app imports; `loki_v8/` — the strategy engine behind the terminal; `components/` + `third_party/` — vendored originals pinned by hash-guards (`tests/test_fusion_provenance.py` fails on byte changes, on purpose).
- `templates/`, `static/` — the served pages and their assets; `tests/` — the regression suite.

Older desktop-era launchers, installers, duplicated guides and unreferenced modules were removed in 2026-10 and 2026-11 (old standalone bot, crypto trainer, Supabase vault); history retains them.
