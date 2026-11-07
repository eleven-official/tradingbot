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

## Portfolio AI (21 markets at once)

`loki_v8/portfolio_ai.py` replays each market's verified profile (13 stocks/ETFs incl. gold and bonds, 8 coins), gives every active market an equal share of capital, and scales the whole book toward a target yearly volatility — capped so total holdings never exceed 100% of the account. The target (10%) was chosen on 2005-2022 only. Untouched holdout 2023 → Nov 2026: **+13.7%/yr, Sharpe 1.25, worst drop −10.5%, 64% of months profitable**, versus equal-weight buy-and-hold of the same markets at +21.9%/yr, Sharpe 0.98, worst drop −28.3%. `GET /api/fusion/ai/portfolio` returns what that exact book holds at the latest completed bar; the AI trading page's Portfolio AI panel mirrors it with paper money. Historical results, not a promise.

## Security

- **Isolation between users:** account data is keyed only by the uid inside the signed session cookie (validated as a UUID); a request naming another owner is refused before the database; credentials can never be saved to the cloud; chat history is per browser session; Tradovate tokens are encrypted and owner-bound.
- **Cookies:** HMAC-signed, HttpOnly, SameSite, Secure on HTTPS. Public deployments without `LOKI_GATE_SECRET` (or a Supabase key) now sign with a random per-process key instead of a constant from the source, so cookies cannot be forged; chat admin claims additionally require `LOKI_CHAT_ADMIN_CODE`.
- **Headers:** strict Content-Security-Policy (scripts only from this site — no inline scripts exist), `frame-ancestors 'self'`, nosniff, Permissions-Policy, COOP, HSTS on HTTPS. Cross-site writes to account/chat endpoints are rejected.
- **Rate limits** (`loki/api/rate_limit.py`): sign-in, sign-up, broker sign-in, revenue operator key, and the heavy AI/market endpoints.
- Real orders, broker and native-engine routes only work from the local launcher with its session token and are off on Vercel. `main.py` binds to 127.0.0.1 unless `LOKI_HOST` says otherwise.
- **Operators should set:** `LOKI_GATE_SECRET` (long random), `LOKI_CHAT_SESSION_SECRET`, `LOKI_SITE_CODE`, `LOKI_BROKER_ENCRYPTION_KEY`, and `LOKI_SECURE_COOKIES=1` behind any non-Vercel HTTPS proxy.

## Privacy, terms and age

- `/privacy`, `/cookies` and `/terms` (v6) are public and describe exactly what the code does: functional first-party cookies only (no analytics, advertising or third-party cookies — so no consent banner), browser-local storage for journals/watchlists/chat, optional account saves, chat turns kept at most 30 days, broker credentials never stored.
- **Age:** entry and sign-up require an "I am 18 or older" confirmation, enforced server-side; no birth date is asked for or stored.
- **Data rights:** `GET /api/account/export` (download my data), `POST /api/account/delete` (type DELETE; removes saves, published score and the login), and a "clear Loki data from this browser" control on `/privacy`.
- **Minimisation:** no third-party requests from the browser (Google Fonts removed; CSP allows no external hosts).
- **Claims:** performance figures are labelled as hypothetical/simulated with a limitations disclaimer; marketing lines that the evidence did not support were rewritten.
- Set `LOKI_OPERATOR_NAME` and `LOKI_OPERATOR_EMAIL` so the policies name the data controller and a contact address. Have the policies reviewed for your jurisdiction.

## Opening experience

`static/js/loki_scene.js` + `static/css/loki_scene.css` add a once-per-visit intro, animated market canvases, a live price tape and motion to the gate page and overview, plus an interface motion system: view transitions, 3D card tilt, a cursor aura, ambient aurora, numbers that count to new values, self-drawing charts and an animated allocation ring. `static/js/loki_radar.js` draws the **AI Market Radar** in the home banner — the Portfolio AI's 21 markets placed by live trend score, held positions glowing and pinging under a rotating sweep (data from `/api/fusion/ai/portfolio`). All presentation only; honours reduced-motion and pauses in hidden tabs.

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
