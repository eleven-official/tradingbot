"""A Vercel-friendly, paper-only web surface for Loki."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from loki.api.binance_market_data import MarketDataError, get_binance_spot_snapshot
from loki.api.risk_planner import RiskPlanError, RiskPlanInput, build_risk_plan
from loki.api.trade_council import CouncilRequest, evaluate_trade_council
from loki.version import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Paper-only risk planning tools for the Loki trading project.",
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class RiskPlanRequest(BaseModel):
    """The browser-safe request schema for a paper trade plan."""

    side: str
    capital: float = Field(gt=0)
    risk_percent: float = Field(gt=0, le=100)
    entry_price: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    target_price: float = Field(gt=0)
    max_notional_percent: float = Field(default=10.0, gt=0, le=100)
    minimum_reward_risk: float = Field(default=1.5, gt=0)


class TradeCouncilRequest(RiskPlanRequest):
    """Optional market context used by the six paper-trade defence roles."""

    current_price: float = Field(gt=0)
    trend: str = "NEUTRAL"
    volatility_percent: float = Field(default=2.0, ge=0)
    volume_ratio: float = Field(default=0.0, ge=0)
    market_data_age_seconds: float = Field(default=61.0, ge=0)
    spread_percent: float = Field(default=0.1, ge=0)
    market_open: bool = False
    max_data_age_seconds: float = Field(default=60.0, ge=0)
    min_volume_ratio: float = Field(default=0.8, ge=0)
    max_volatility_percent: float = Field(default=5.0, ge=0)
    max_spread_percent: float = Field(default=0.5, ge=0)
    max_entry_deviation_percent: float = Field(default=0.5, ge=0)
    setup_name: str = Field(default="", max_length=60)
    setup_score: float | None = Field(default=None, ge=0, le=100)
    min_setup_score: float = Field(default=80.0, ge=0, le=100)


def _model_data(payload: BaseModel) -> dict[str, object]:
    """Support both Pydantic v2 (`model_dump`) and v1 (`dict`) runtimes."""
    model_dump = getattr(payload, "model_dump", None)
    return model_dump() if model_dump else payload.dict()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """Render the paper-only risk-planning dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"version": __version__},
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "loki",
            "version": __version__,
            "mode": "paper-tools-only",
        }
    )


@app.get("/api/market-snapshot")
def market_snapshot(symbol: str = "BTCUSDT", interval: str = "1m") -> dict[str, object]:
    """Read public Binance Spot data for the selected dashboard symbol.

    This endpoint is read-only and does not use API credentials.  Its brief
    in-process cache reduces repeat requests while a dashboard is open.
    """
    try:
        snapshot = get_binance_spot_snapshot(symbol, interval)
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"mode": "read-only-market-data", "snapshot": asdict(snapshot)}


@app.post("/api/risk-plan")
async def create_risk_plan(payload: RiskPlanRequest) -> dict[str, object]:
    """Create a non-executable plan from supplied entry, stop and target data."""
    try:
        plan = build_risk_plan(RiskPlanInput(**_model_data(payload)))
    except RiskPlanError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "mode": "paper-only",
        "disclaimer": "This is a calculation, not financial advice or an order.",
        **plan.__dict__,
    }


@app.post("/api/trade-council")
async def run_trade_council(payload: TradeCouncilRequest) -> dict[str, object]:
    """Run the six explainable paper-trade gates for a proposed long entry."""
    try:
        decision = evaluate_trade_council(CouncilRequest(**_model_data(payload)))
    except RiskPlanError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "mode": "paper-only",
        "disclaimer": "This is a calculation, not financial advice or an order.",
        "action": decision.action,
        "rationale": decision.rationale,
        "reviews": [asdict(review) for review in decision.reviews],
        "plan": asdict(decision.plan),
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> Response:
    favicon = STATIC_DIR / "favicon.ico"
    return FileResponse(favicon) if favicon.exists() else Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png() -> Response:
    favicon = STATIC_DIR / "favicon.png"
    return FileResponse(favicon) if favicon.exists() else Response(status_code=204)


