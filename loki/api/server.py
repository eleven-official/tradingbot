from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from loki.portfolio import PortfolioInputError, Position, build_portfolio_summary
from loki.version import __version__


class PortfolioPositionPayload(BaseModel):
    """A caller-supplied long position and its latest price."""

    symbol: str = Field(min_length=1, max_length=32)
    quantity: float = Field(ge=0)
    average_cost: float = Field(ge=0)
    current_price: float = Field(ge=0)


class PortfolioSummaryPayload(BaseModel):
    """Input for the read-only portfolio summary endpoint."""

    positions: list[PortfolioPositionPayload] = Field(default_factory=list)
    cash: float = Field(default=0, ge=0)
    currency: str = Field(default="AUD", min_length=3, max_length=3)


app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Loki trading API and lightweight landing page",
)

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render a small landing page so the repo is a website-ready deployment."""
    context = {"request": request, "version": __version__}
    return templates.TemplateResponse("index.html", context)


@app.get("/health")
async def health():
    return JSONResponse(
        {
            "status": "ok",
            "service": "loki",
            "version": __version__,
            "portfolio_summary": "available",
        }
    )


@app.post("/portfolio/summary", tags=["portfolio"])
async def portfolio_summary(payload: PortfolioSummaryPayload) -> dict[str, object]:
    """Value caller-supplied holdings without storing them or placing trades."""
    try:
        positions = [
            Position(
                symbol=position.symbol,
                quantity=position.quantity,
                average_cost=position.average_cost,
                current_price=position.current_price,
            )
            for position in payload.positions
        ]
        return build_portfolio_summary(
            positions,
            cash=payload.cash,
            currency=payload.currency,
        )
    except PortfolioInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    static_fav = static_dir / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)

    root_fav = Path(__file__).parents[2] / "loki.ico"
    if root_fav.exists():
        return FileResponse(root_fav)
    return JSONResponse(status_code=204, content=None)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    static_fav = static_dir / "favicon.png"
    if static_fav.exists():
        return FileResponse(static_fav)
    return JSONResponse(status_code=204, content=None)
