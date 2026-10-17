# Local research engines in Loki

Loki's fusion workspace can call MiroFish's actual REST API and the licensed
Fincept portfolio risk CLI. These adapters do not place trades. They do not
interpret simulated opinions, portfolio risk statistics, or winning days as
evidence of a 70% closed-trade win rate.

## Fincept: licensed, offline portfolio risk

The user confirmed possession of the commercial license needed for business and
internal use. Keep the installation, license agreement, copyright notices, and
original source private unless that agreement explicitly permits redistribution.
Loki's public repository contains the independently written adapter, not Fincept
source. Confirm the agreement covers the intended deployment and users.

Install the supplied Fincept archive independently, retaining its directory
structure and notices. Configure the Python environment with its analytics
dependencies, including NumPy, pandas, and SciPy. Set these **host** environment
variables before starting Loki:

```powershell
$env:LOKI_FINCEPT_PATH = 'C:\path\to\FinceptTerminal-main'
$env:LOKI_FINCEPT_PYTHON = 'C:\path\to\python.exe'
$env:LOKI_FINCEPT_LICENSE_CONFIRMED = '1'
$env:LOKI_FINCEPT_ALLOW_ANALYTICS = '1'
```

`LOKI_FINCEPT_PYTHON` is optional; it defaults to Loki's Python interpreter.
`LOKI_FINCEPT_PATH` is the directory containing `fincept-qt`, not a browser-supplied
filename. No process starts during capability discovery.

The adapter runs only:

```text
fincept-qt/scripts/Analytics/portfolioManagement/risk_management.py
    comprehensive_risk_analysis <validated JSON>
```

The original module runs in a separate Python process. A fixed stdin bridge
avoids Windows' command-line length limit. The browser cannot select a Python
module, script, command, interpreter, or working directory. The inspected risk
module performs local calculations from supplied daily returns; it does not
fetch prices, request broker credentials, or call Fincept data services.

Supply 20–2000 aligned daily return observations per asset as fractional changes
(for example, `0.01` means 1%). Up to 20 assets are supported, with positive weights
that sum to 1. The adapter returns the original engine's daily and annual
volatility, drawdown, 95%/99% historical and parametric VaR, conditional VaR,
Monte Carlo estimates, stress tests, and dollar risk metrics. Higher moments
that the upstream engine cannot define are represented by `null`.

The upstream annualization assumption is **252 days**. This is displayed in the
result and should not be confused with a 365-day crypto risk model. Monte Carlo
figures are estimates and can vary between runs. This integration exposes the
portfolio risk module; it does not claim to embed every Fincept terminal module.

Status values distinguish `license_required`, `unconfigured`, `unavailable`,
`disabled`, and `configured`. `configured` confirms local files and interpreter
exist; the first report verifies installed dependencies and computation.

## MiroFish: separate AGPL research service

MiroFish remains an independently installed, unmodified research service with its
own source, AGPL notices, configuration, and runtime. Preserve its applicable
source availability obligations for your deployment. Loki calls its HTTP API;
no MiroFish implementation is copied into Loki or relicensed as proprietary code.

Install and start the supplied MiroFish service according to its own README in a
separate environment. Bind its backend to loopback; review and configure its
LLM/Zep provider credentials and budgets there. Loki does not start the service,
install packages into it, buy credits, or copy its credentials.

```powershell
$env:LOKI_MIROFISH_URL = 'http://127.0.0.1:5001'
# Enable only after configuring the engine and its provider budgets:
$env:LOKI_MIROFISH_ALLOW_JOBS = '1'
```

With only the URL configured, Loki can inspect existing projects, graph data,
simulations, run status, task progress, and reports. Starting any ontology,
graph, simulation, report, or report-chat job requires the explicit host job
flag. A stop request remains available when new jobs have been disabled.

The integration uses these real routes from the supplied backend:

| Loki adapter operation | Upstream route |
| --- | --- |
| Check identity | `GET /health` and `GET /api/graph/project/list` |
| Upload source text and create project | `POST /api/graph/ontology/generate` with multipart fields `files`, `project_name`, `simulation_requirement` |
| Build graph | `POST /api/graph/build` |
| Read graph/build task | `GET /api/graph/data/{graph_id}`, `GET /api/graph/task/{task_id}` |
| Create simulation | `POST /api/simulation/create` |
| Prepare agents/configuration | `POST /api/simulation/prepare` |
| Poll preparation | `POST /api/simulation/prepare/status` |
| Start or stop simulation | `POST /api/simulation/start`, `POST /api/simulation/stop` |
| Read running status | `GET /api/simulation/{simulation_id}/run-status` |
| Generate report | `POST /api/report/generate` |
| Poll report generation | `POST /api/report/generate/status` |
| Read report | `GET /api/report/{report_id}`, `GET /api/report/by-simulation/{simulation_id}` |
| Ask report agent | `POST /api/report/chat` |

The workflow is explicit: upload seed text, build graph, poll until finished,
create a simulation, prepare, poll until ready, start a bounded run, wait for a
terminal run state, and generate/read its report. Each step shows real engine
state. Loki does not replace missing provider output with a generated result or
retry paid jobs automatically. Source documents and agent replies are research
data, never instructions to change Loki's execution or risk controls.

Only literal loopback HTTP origins with an explicit port are accepted. The
`localhost` alias is converted to `127.0.0.1` without DNS resolution. Redirects,
remote hosts, credentials in URLs, proxy environment variables, and caller
provided API paths are rejected. Identifiers are checked before URL construction.
Responses are limited to 2 MiB; upstream tracebacks and provider error bodies are
not forwarded to the browser. Health checks have at most two one-second HTTP
requests; ordinary reads and job submissions have an eight-second request
timeout. Timing out while observing a job does **not** imply the upstream job
stopped: use its returned project/task/simulation IDs to inspect current state.

Capability discovery uses `status(probe=False)` and makes no network requests.
An explicit connection check uses `status()` and verifies actual engine identity
and a real project API route. `configured` and `ready` are distinct states.

## Deployment and validation

All native-service reads, status checks and jobs require Loki's local session
token, the loopback launcher and a matching browser origin. Forwarded/proxied
requests cannot obtain native access. Native replies and tokens are marked
private and non-cacheable. Engine locations and flags can be set only by the host operator. On Vercel, both
environment factories disable local components: serverless hosting cannot
access a user's desktop Python installation or loopback MiroFish process.

`tests/test_fusion_external.py` exercises the adapters with a real local HTTP
server, including multipart upload, job opt-in, actual read-only POST polling,
redirect rejection, origin/path controls, response limits, missing dependencies,
and fixed-command subprocess transport. No credentials or paid providers are
needed for those tests. Separately run a Fincept report against the licensed
installation to verify the real implementation and installed dependencies.

The [MiroFish setup guide](MIROFISH_SETUP.md) includes a no-network readiness
helper and the actual provider/dependency prerequisites found in the supplied
source. An API adapter alone does not mean the native service is running.

Source references: [Fincept Terminal](https://github.com/Fincept-Corporation/FinceptTerminal)
and [MiroFish](https://github.com/666ghj/MiroFish). The uploaded archives, not claims
about a newer remote version, were used to establish these integration contracts.
