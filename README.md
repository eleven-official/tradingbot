# Loki Trading Workspace

One FastAPI application: the information workspace at the gate, a Supabase-gated sign-in, AI paper trading, a market planner, research and strategy lab surfaces, news desk, watchtower, and the "Bored?" game — Loki Dive, a nova-deep trivia ride with seven 25-second rounds per dive, streak combos, typo forgiveness, and example answers after every miss — plus a browser-held Alpaca paper order rail and an in-page autopilot with published, hand-railed rules.

Everything ships over Vercel: every push to `main` reaches https://loki-joshua-5183.vercel.app through the connected Vercel project. Access is code-gated; the gate code lives in the deployment env, not in this repository.

## Run locally

Requires Python 3.12. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8124
```

Optional environment variables: `LOKI_SITE_GATE=1` enables the gate, `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` enable the login flow, Alpaca keys are browser-held and verify through the relay (`/api/broker/alpaca/*`) whenever the user enters them.

## Guarantees

- The honest-error contract: degraded states are visible, empty logs say empty, headline cards say "information, never advice", the autopilot's published rule is its contract, and the relay caps order size server-side regardless of what the panel says.
- Keys and secrets never enter the repository; the backup export excludes credentials.
- The "Bored?" game is entirely local: scores and dive history never leave the browser, and its rarity tiers are hand-written bank data, not measurements from other players.
- `pytest` (all Python tests), plus `node --test` for the two JavaScript test modules. The CI workflows in `.github/` run both on every push.

## Layout

- `main.py` — Vercel/uvicorn entry point; `loki/api/` — the HTTP surface (server, gate, Supabase auth, news desk, market feed, Alpaca relay, fusion research, watchtower, terminal).
- `core/` + `core_engine` history reduced to what the app imports; `loki_v8/` — the strategy engine behind the terminal; `components/` + `third_party/` — vendored originals pinned by hash-guards (`tests/test_fusion_provenance.py` fails on byte changes, on purpose).
- `templates/`, `static/` — the served pages and their assets; `tests/` — the regression suite.

Older desktop-era launchers, installers, duplicated guides and unreferenced modules were removed from the repository in 2026-10; history retains them.
