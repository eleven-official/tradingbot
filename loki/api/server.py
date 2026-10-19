from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from loki.version import __version__
from core.copilot import LokiCopilot
from core.risk_preview import preview_position
from core.strategy_lab import evaluate_strategy
from loki.api.fusion import router as fusion_router

app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Loki research workspace and read-only trading copilot",
)
app.include_router(fusion_router)

# Resolve assets independently of the process working directory.
repo_dir = Path(__file__).resolve().parents[2]
static_dir = repo_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates dir
templates_dir = repo_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render the workspace; real orders use separately gated local routes."""
    context = {"request": request, "version": __version__}
    return templates.TemplateResponse(request=request, name="index.html", context=context)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bars: list[dict] = Field(min_length=161, max_length=5000)
    config: dict = Field(default_factory=dict)


@app.post("/api/research/evaluate")
def research(payload: ResearchRequest):
    try:
        return evaluate_strategy(payload.bars, payload.config)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class CopilotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    context: dict = Field(default_factory=dict)


@app.post("/api/copilot")
def copilot(payload: CopilotRequest):
    return LokiCopilot().respond(payload.message, payload.context).as_dict()


class SizingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    equity: float = Field(gt=0, le=1e12)
    entry: float = Field(gt=0, le=1e12)
    stop: float = Field(gt=0, le=1e12)
    risk_pct: float = Field(default=0.5, gt=0, le=5)
    max_exposure_pct: float = Field(default=20, gt=0, le=100)
    fee_bps: float = Field(default=10, ge=0, le=1000)
    slippage_bps: float = Field(default=5, ge=0, le=1000)


@app.post("/api/risk/preview")
def risk_preview(payload: SizingRequest):
    try:
        return preview_position(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "loki", "version": __version__})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    # Prefer static/favicon.ico if present, fallback to repo root loki.ico if available.
    static_fav = static_dir / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)
    root_fav = repo_dir / "loki.ico"
    if root_fav.exists():
        return FileResponse(root_fav)
    return Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    static_fav = static_dir / "favicon.png"
    if static_fav.exists():
        return FileResponse(static_fav)
    return Response(status_code=204)
