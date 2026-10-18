# Connect the actual MiroFish service

The complete supplied source is now included at
`components/mirofish/upstream`. Use that path with the setup helper below; an
external clone is no longer needed. Its native ReportManager reader and report
classes also run directly through Loki's council without this service or its
project HTTP API. See [native report integration](SIMULATED_MARKET.md).
That working artifact-read path does not run graph generation, OASIS agents or
new provider reports. Their genuine runtime prerequisites below still apply.

MiroFish's native graph, agent simulation and report capabilities require its
separate service and provider configuration. Loki's local scenario calculator is
not a substitute for those capabilities. An unconfigured adapter does not mean
the native service has been installed or tested.

## What currently prevents startup

In the supplied archive, `backend/run.py` calls `Config.validate()` before
creating the Flask app. That validation requires both `LLM_API_KEY` and
`ZEP_API_KEY`, even if the intended first request is only `/health`. It also
rejects `ZEP_API_URL`: this implementation targets Zep Cloud, not a self-hosted
replacement. `create_app()` imports graph, simulation and report modules and
their provider SDKs before registering the health route.

The inspected Loki environment has Python 3.12 but lacks `flask-cors`, `openai`,
`zep-cloud`, `camel-oasis`, `camel-ai`, `PyMuPDF`, and `chardet`. Neither required
provider key was configured. No actual native service or provider job was
started, and no placeholder keys were installed to make readiness appear green.

## Check an installation without executing it

Run this from Loki's repository, replacing the paths with your separate install:

```powershell
python scripts/setup_mirofish.py --source 'C:\Engines\MiroFish' --python 'C:\Engines\MiroFish\.venv\Scripts\python.exe'
```

The helper reads selected source/requirements files, checks installed package
metadata in the selected interpreter using isolated Python, and reports only
whether the required configuration exists. It does not import MiroFish, execute
its `.env`, print credential values, install packages, start a server, or make
network requests. Root `.env` values override environment values in the same
order as the inspected upstream config. Template and unresolved-variable values
do not count as configured credentials. Complex multiline configuration requires
local review.

Exit code `0` means configuration is ready to **try** the original startup; it
does not authenticate providers, confirm available credits, or verify service
health. Exit code `1` reports concrete missing configuration or dependencies.
Exit code `2` means the check itself could not complete. Suggested commands in
the JSON result are data for review and are never executed by the helper.

## Separate environment and real configuration

Keep the supplied service, its license, source, and data separate from Loki. The
archive's `backend/pyproject.toml` specifies Python `>=3.11,<3.13`. Create a
dedicated Python 3.11/3.12 environment and install the supplied dependency file:

```powershell
$miroRoot = 'C:\Engines\MiroFish'
py -3.12 -m venv (Join-Path $miroRoot '.venv')
& (Join-Path $miroRoot '.venv\Scripts\python.exe') -m pip install -r (Join-Path $miroRoot 'backend\requirements.txt')
```

Review the original source-root `.env.example` and create a private `.env` there
with your actual provider settings. Do not send keys to Loki chat or commit
them. Configure the intended LLM model/base URL, genuine LLM and Zep Cloud keys,
and provider-side spending limits. The sample mentions optional accelerated LLM
settings; omit those unless explicitly needed. Installing dependencies or merely
supplying keys does not establish that a simulation is affordable or authorized.

Keep the service local by setting `FLASK_HOST=127.0.0.1`, `FLASK_PORT=5001`, and
`FLASK_DEBUG=false` in its root configuration. The original launcher defaults to
`0.0.0.0`; root `.env` uses override precedence, so verify it does not undo the
loopback/debug settings supplied at launch. Then start the original launcher:

```powershell
$env:FLASK_HOST = '127.0.0.1'
$env:FLASK_PORT = '5001'
$env:FLASK_DEBUG = 'false'
& (Join-Path $miroRoot '.venv\Scripts\python.exe') (Join-Path $miroRoot 'backend\run.py')
```

After the service starts, a health request and existing-project list are
read-only checks. Do not create graphs, prepare/start simulations, generate
reports, or submit report-chat requests merely to test a connection: those paths
can consume external provider resources.

In Loki's local configuration, set `mirofish_url` to
`http://127.0.0.1:5001` and keep `mirofish_allow_jobs: false`. Use the real
connection check to verify the native service identity and existing-project
route. The adapter does not automatically retry paid jobs. See
[external-engine integration](FUSION_EXTERNAL_ENGINES.md) for endpoint contracts
and the explicit job opt-in.

## AGPL boundary

The uploaded source carries AGPL version 3. Preserve its original license and
notices and determine the corresponding-source obligations that apply to the
specific distribution, modifications and network deployment. Modified network
service deployments can carry source-offer requirements; distributing source or
binaries can add obligations. Calling a separate HTTP process is an architectural
boundary, not a guarantee that every combined commercial deployment satisfies
the license. Keep the actual source and license accessible as applicable. This
guide does not relicense MiroFish or certify compliance for a business deployment.

The concrete startup/configuration findings above come from the uploaded archive,
not assumptions about another version. Upstream project:
[MiroFish](https://github.com/666ghj/MiroFish). License text:
[GNU AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html).
