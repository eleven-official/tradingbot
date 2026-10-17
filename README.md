# Loki Fusion — research and paper trading

Loki brings strategy research, factor diagnostics, a role-based council, a paper portfolio, stress scenarios and conversation into one workspace. Selected Vibe-Trading and AutoHedge engines run inside Loki; licensed Fincept analytics and the separate MiroFish service connect locally. This is a research and paper application. No strategy has established the requested 70% future winning-trade rate or improved future profitability.

## Start the unified workspace

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python launch_loki_fusion.py
```

Open http://127.0.0.1:8000. The seven views share the dataset and paper journal:

- **Overview:** forward-test equity versus buy-and-hold, costs, uncertainty and evidence gaps.
- **Quant lab:** CSV walk-forward trend research, Vibe-derived causal factors and a separate fixed-rule historical shadow replay.
- **Agent council:** AutoHedge-derived director/analyst role contracts with deterministic signal, evidence, cash, currency and exposure checks. Drafts are inert and blocked when checks fail; no LLM agents are silently invoked.
- **Paper portfolio:** manual long entries, partial exits, marks, costs, lifecycle P&L, browser persistence, export and cost-aware sizing.
- **Scenarios:** explicit price-shock sensitivity on current paper positions, plus the actual MiroFish service workflow when configured.
- **Talk to Loki:** grounded local explanations of research, factors, council decisions, portfolios and stress results; multi-topic questions, instrument followups, loss reviews and useful next checks. Chat has no execution authority.
- **Integrations:** real readiness states and licensed Fincept daily-return portfolio risk reports.

Upload **161–5,000 bars from a single instrument** with columns `timestamp,open,high,low,close,volume`. Use ISO 8601 timestamps (timezone recommended; naive timestamps are interpreted as UTC) in ascending order. Set bars per year to match the data frequency. All monetary values use the input data's quote currency. Historical data provenance is not independently verified.

Paper journal state is saved in this browser's local storage. Research, council and stress results remain in the current page until export or reload. The workspace export includes uploaded bars and paper records; handle it as business data. Server endpoints compute from caller-supplied state and do not provide accounts, authentication, durable storage or broker orders. Default local research and chat do not call external AI providers.

## Use the supplied external engines

Copy `fusion.config.example.json` to the ignored `fusion.config.local.json`, set local installation paths, then run:

```powershell
.\.venv\Scripts\python launch_loki_fusion.py --config fusion.config.local.json --check
.\.venv\Scripts\python launch_loki_fusion.py --config fusion.config.local.json
```

| Component | Included integration | Runtime and license boundary |
| --- | --- | --- |
| Vibe-Trading | Adapted RSI, factor IC/rank-group math, causal factor diagnostics and replay | Selected MIT source and attribution in `third_party/vibe_trading`; no hosted Vibe or Qlib runtime |
| AutoHedge | Adapted role contracts and evidence pipeline | Selected MIT source in `third_party/autohedge`; deterministic local implementation, not Swarms/LLM agents |
| Fincept | Original portfolio-risk CLI, invoked in a separate local Python process | Requires the user's commercially licensed private installation and NumPy/pandas/SciPy; original source is not redistributed |
| MiroFish | Actual graph/project, preparation, simulation, report and report-chat API workflow | Separate AGPL service, its dependencies and configured LLM/Zep providers; preserve applicable source obligations |

The Fincept commercial license was confirmed for this installation. Distribution rights are not inferred from that confirmation. Keep its installation and agreement outside public source control. MiroFish jobs can incur provider usage and require an explicit host flag; Loki never starts them automatically. Simulation opinions and risk statistics do not certify a trading edge.

Native engine reads and jobs require the loopback launcher, same-origin session token and explicit host configuration. They are disabled on Vercel. A hosted preview supports the pure research/paper features; it cannot reach your desktop engines. See [external engine setup and contracts](docs/FUSION_EXTERNAL_ENGINES.md) and [MiroFish's concrete readiness check](docs/MIROFISH_SETUP.md).

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

## Verification and strategy evidence

```powershell
.\.venv\Scripts\python -m pip install -r requirements_test.txt
.\.venv\Scripts\python -m pytest tests -o addopts= -q
```

The regression suite tests software behavior with synthetic or mocked data. Separately, local Fincept reports verify the original licensed analytics. No paid MiroFish provider run is part of CI. See [frozen strategy validation](docs/research/VALIDATION.md) for an immutable training/holdout protocol using operator-supplied licensed data. Trading profitability remains unproven; a 70% observed win rate can still lose money when losses and costs outweigh gains.
