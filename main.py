"""Loki Trading Platform application entrypoint for local runners."""

import uvicorn
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=False)

from loki.api.server import app

if __name__ == "__main__":
    # Loopback by default: a dev server on 0.0.0.0 is reachable by anyone on
    # the same network. Set LOKI_HOST=0.0.0.0 deliberately to expose it.
    import os

    uvicorn.run("main:app", host=os.environ.get("LOKI_HOST", "127.0.0.1"), port=8000, reload=True)
