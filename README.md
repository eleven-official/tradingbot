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

## Strategy book and paper sessions

The ensemble's execution parameters are trained walk-forward per symbol and verified out of sample (`loki_v8/train.py`). The verified profiles ship in `loki_v8/training_report_snapshot.json`, and that snapshot is what the server applies to a symbol before it emits a decision.

Crypto has its own pass, because a 24/7 tape is not an equity tape: 365 bars a year instead of 252, higher realised volatility, and hurdle targets scaled to crypto noise.

```powershell
python -m loki_v8.train_crypto --rounds 2 --workers 6 --period 10y
```

That pass writes a crypto-only `crypto_consensus` next to the mixed one, and merges forward any symbol it did not evaluate, so nothing already verified is dropped. A re-run that fails (crashed worker, dead feed) never demotes a stored verified profile - the failure is recorded on the entry as `stale_reason` and the previously verified parameters stay in the book.

### How the winner is chosen

The sweep is not a hit-rate hunt. Two rules decide the book:

- **Rank on expectancy, not win rate.** Candidates are ordered by mean return per trade (`return_pct / trades`) with a profit-factor floor of 1.25 ahead of it and a 20-trade sample-size layer in front of that. A 92%-win profile with a 0.62-ATR target behind a 4.25-ATR stop earns its return in many tiny wins and gives several back on one loss; the same total return made in fewer, larger pieces ranks higher. The exit grid was widened to match (`CRYPTO_GRID`): take-profit up to 4.0 ATR against stops from 2.0 ATR, so a 45% hit rate is allowed to be profitable.
- **Select on forward folds, not in-sample rank.** The leaderboard winner is by construction the best fit to the training block. The top four finalists are therefore re-run on two anchored forward folds that start strictly after the fitted data (`fold_bounds`, `walk_forward_score` in `loki_v8/train.py`), and the winner is the one with the best *worst* fold - one blow-up fold disqualifies a candidate regardless of how good the others looked. Each report records `selection: "walk_forward"` and the fold detail.

The cross-symbol consensus is edge-weighted (`_edge_weight`): each symbol's vote scales with its own out-of-sample return and profit factor, and a symbol that trained but never traded out of sample gets a near-zero vote. A book with no out-of-sample metrics still produces the plain median, so fixtures and old snapshots behave exactly as before.

The hurdles moved with the objective (`CRYPTO_HURDLES`): 10 trades, profit factor 1.5, positive return, drawdown better than -30%, 45% win rate, profits in 55% of months. A low hit-rate bar plus a high profit-factor bar is a materially harder pair than 70% / 1.3 was, because it stops rewarding the tiny-target geometry.

### Robustness gate (windows + simulated tape)

Clearing the out-of-sample hurdle set is necessary but not sufficient: a 370-combination sweep over one decade will always find a corner of that decade that looks like an edge. After the sweep, each winning parameter set is re-tested twice (`loki_v8/synthetic.py`):

- **Cross-window** — the same parameters re-run over the trailing 5, 7 and 10 years independently. An edge that only exists in one regime fails the short windows.
- **Simulated tape** — tapes rebuilt from the symbol's *own* realised returns by block bootstrap (contiguous 20-bar blocks resampled with replacement, each sampled bar carrying its donor bar's OHLC geometry and volume). Fat tails, volatility clustering and intra-bar shape survive; the memorised path does not.

```powershell
python -m loki_v8.train_crypto --windows 5,7,10            # seeds default to 11,23,37,53,71
python -m loki_v8.train_crypto --synthetic-seeds 11,23,37   # fewer tapes, faster
python -m loki_v8.train_crypto --no-robustness              # hurdle result only, for comparison
```

`good` is only true when the hurdle set, every window and the bootstrapped tapes all pass. Anything else is reported with the verdict naming which check failed, and there are three states rather than two:

- `verified` - all three agreed.
- `research only` - a check ran and the edge failed it.
- `untested` - the tapes could not reach the pooled-fill floor, so they never got to measure the edge.

The third state exists because the two failures look identical in raw output and they are not the same finding. A wide target against a wide stop fires rarely; at three tapes a genuinely good profile could pool six fills and be printed as "sim fail" beside a profile that lost money on thirty-two. Both keep `good` false - thin evidence is never promotion - but only the second is a verdict about the strategy. Five tapes are the default for the same reason: raising the tape count lifts the pooled fill count without lowering the floor, so the evidence gets stronger instead of the bar getting lower.

Bytes are deterministic per seed, so a re-run cannot move the goalposts. Both checks reuse the same underlying history, so they measure regime and path dependence - not independent evidence of future profit. The research-book card shows the verdict per symbol.

Alongside the three-check gate, every card reports the final 20% of history - the segment the optimiser never saw - judged against the same thresholds. It is published as a finding rather than folded into `good`, because four to six trades in that tail is too small a sample to promote or demote on: a profile can clear every gate and still lose its last handful of trades, and the card says both things instead of the flattering one.

Simulated crypto trading runs off the same book:

```powershell
python -m loki_v8.crypto_paper                 # 180-bar replay blotter
python -m loki_v8.crypto_paper --mode step     # one decision on the latest bar
```

`replay` fills at historical prices with slippage and writes a session ledger; `step` persists fills to an isolated crypto paper account. Neither places a real order. `--mode step --mirror` forwards fills to Alpaca's paper endpoint when `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_API_SECRET` are set; without them it reports the missing keys instead of ordering. A replay cannot be mirrored, because Alpaca only fills at live prices.

## Layout

- `main.py` — Vercel/uvicorn entry point; `loki/api/` — the HTTP surface (server, gate, Supabase auth, news desk, market feed, Alpaca relay, fusion research, watchtower, terminal).
- `core/` + `core_engine` history reduced to what the app imports; `loki_v8/` — the strategy engine behind the terminal; `components/` + `third_party/` — vendored originals pinned by hash-guards (`tests/test_fusion_provenance.py` fails on byte changes, on purpose).
- `templates/`, `static/` — the served pages and their assets; `tests/` — the regression suite.

Older desktop-era launchers, installers, duplicated guides and unreferenced modules were removed from the repository in 2026-10; history retains them.
