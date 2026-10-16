# Loki trading research and paper terminal

Loki provides a desktop paper-trading terminal and a browser research workspace. Strategies are experimental. No win rate or return is guaranteed; a 70% observed win rate can still lose money when losses and costs outweigh gains.

## Browser workspace

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The browser workspace includes:

- CSV strategy research: chronological train/test windows, training-only parameter selection, next-open execution, entry volatility sizing, trailing-close exits, fees and slippage, buy-and-hold comparison, and cost stress.
- Measured returns, initial-equity drawdown, completed-trade expectancy, profit factor, win-rate uncertainty, research rejection reasons, and downloadable JSON evidence.
- A cost-aware long-position sizing preview with cash and risk caps.
- A local conversational copilot that explains supplied research and sizing, handles followups, and identifies missing evidence.

Upload **161–5,000 bars from a single instrument** with columns `timestamp,open,high,low,close,volume`. Use ISO 8601 timestamps (timezone recommended; naive timestamps are interpreted as UTC) in ascending order. Set bars per year to match the data frequency. All monetary values use the input data's quote currency. Historical data provenance is not independently verified.

This web surface does not connect a broker, share account data, or submit orders. Research stays in the current browser page until export or reload; restarting a research run replaces the current report. No external AI service is used.

## Desktop paper terminal

```powershell
.\.venv\Scripts\python -m pip install -r requirements_desktop.txt
.\.venv\Scripts\python loki_desktop.py
```

The primary desktop supports simulated paper trading, optional public crypto market data, charting, risk settings, paper portfolio analytics, strategy comparison, walk-forward research, and the same read-only copilot. Data provenance and quote freshness are shown. Live execution is unavailable in this terminal. Changing data sources with open positions requires closing those paper positions first.

Other legacy launchers and engines remain in the repository; these instructions target `main.py` and `loki_desktop.py`.

## Command-line strategy evaluation

```powershell
python run_strategy_lab.py history.csv --output reports/research.json --periods-per-year 365 --fee-bps 10 --slippage-bps 5
```

This command needs only Python's standard library. See [Strategy Lab methodology](docs/STRATEGY_LAB.md) for configuration, assumptions and limitations. Passing research criteria means only that a strategy is a candidate for further paper evaluation. Repeated research on the same holdout can overfit; use a fresh dataset for confirmation.

## Verification

```powershell
.\.venv\Scripts\python -m pip install pytest httpx
.\.venv\Scripts\python -m pytest tests/test_copilot.py tests/test_strategy_lab.py tests/test_desktop_presenter.py tests/test_research_api.py -o addopts= -q
```

The larger legacy suite includes tests for endpoints absent from the existing minimal web server and modules requiring additional optional dependencies. Passing focused checks does not establish live profitability.
