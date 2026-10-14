from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI(
    title="Loki Trading Platform",
    version="2.0.0",
    description="Loki trading API and webhook surface",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "loki"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "loki"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png() -> Response:
    return Response(status_code=204)
