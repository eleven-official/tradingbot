"""A Vercel-friendly, paper-only web surface for Loki."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from loki.api.bot_copilot import answer_bot_question
from loki.api.daily_risk import DailyRiskError, build_daily_risk_summary
from loki.api.binance_market_data import (
    MarketDataError,
    get_binance_spot_history,
    get_binance_spot_snapshot,
)
from loki.api.risk_planner import RiskPlanError, RiskPlanInput, build_risk_plan
from loki.api.strategy_backtest import (
    BacktestInputError,
    run_strategy_backtest,
)
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


class StrategyBacktestRequest(BaseModel):
    """Bounded settings for a historical paper replay."""

    symbol: str = Field(default="BTCUSDT", min_length=5, max_length=20)
    interval: str = "1h"
    strategy: str = "trend_following"
    bars: int = Field(default=500, ge=120, le=1000)
    starting_capital: float = Field(default=10000.0, gt=0)
    risk_percent: float = Field(default=1.0, ge=0.05, le=5)
    fee_bps: float = Field(default=10.0, ge=0, le=100)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)
    max_holding_bars: int = Field(default=20, ge=1, le=100)


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


class BotMarketContext(BaseModel):
    symbol: str = Field(default="", max_length=20)
    interval: str = Field(default="", max_length=8)
    current_price: float | None = None
    change_24h_percent: float | None = None
    trend: str = Field(default="UNKNOWN", max_length=20)
    rsi_14: float | None = None
    volume_ratio: float | None = None
    spread_percent: float | None = None
    data_age_seconds: float | None = None


class BotReviewContext(BaseModel):
    agent: str = Field(default="", max_length=40)
    verdict: str = Field(default="", max_length=12)
    reason: str = Field(default="", max_length=300)
    next_step: str = Field(default="", max_length=300)


class BotPlanContext(BaseModel):
    quantity: float | None = None
    estimated_loss: float | None = None
    reward_risk_ratio: float | None = None
    notional: float | None = None
    projected_profit: float | None = None


class BotDecisionContext(BaseModel):
    action: str = Field(default="", max_length=12)
    rationale: str = Field(default="", max_length=300)
    setup_name: str = Field(default="", max_length=80)
    setup_score: float | None = None
    reviews: list[BotReviewContext] = Field(default_factory=list)
    plan: BotPlanContext | None = None


class BotSetupStats(BaseModel):
    name: str = Field(default="", max_length=80)
    closed: int = Field(default=0, ge=0, le=250)
    wins: int = Field(default=0, ge=0, le=250)
    win_rate_percent: float | None = None
    average_r: float | None = None
    pnl: float | None = None


class BotJournalContext(BaseModel):
    closed_trades: int = Field(default=0, ge=0, le=250)
    wins: int = Field(default=0, ge=0, le=250)
    win_rate_percent: float | None = None
    average_r: float | None = None
    pnl: float | None = None
    setups: list[BotSetupStats] = Field(default_factory=list)


class DailyRiskRequest(BaseModel):
    """Browser journal totals for an advisory daily paper-risk check."""

    capital: float = Field(gt=0)
    loss_limit_percent: float = Field(gt=0, le=100)
    realized_pnl: float
    realized_loss: float = Field(ge=0)
    open_planned_risk: float = Field(ge=0)
    closed_today: int = Field(default=0, ge=0)
    open_positions: int = Field(default=0, ge=0)


class BotDailyRiskContext(BaseModel):
    status: str = Field(default="", max_length=16)
    limit_amount: float | None = None
    realized_pnl: float | None = None
    realized_loss: float | None = None
    open_planned_risk: float | None = None
    committed_loss: float | None = None
    remaining_amount: float | None = None
    utilization_percent: float | None = None
    closed_today: int = Field(default=0, ge=0)
    open_positions: int = Field(default=0, ge=0)


class BotChatRequest(BaseModel):
    """A bounded question with ephemeral dashboard context; no chat is persisted."""

    question: str = Field(min_length=1, max_length=500)
    market: BotMarketContext | None = None
    decision: BotDecisionContext | None = None
    journal: BotJournalContext = Field(default_factory=BotJournalContext)
    daily_risk: BotDailyRiskContext | None = None


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


@app.get("/strategy-lab", response_class=HTMLResponse)
async def strategy_lab(request: Request) -> HTMLResponse:
    """Render the historical, out-of-sample strategy workbench."""
    return templates.TemplateResponse(
        request=request,
        name="strategy_lab.html",
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


@app.post("/api/strategy-backtest")
async def create_strategy_backtest(payload: StrategyBacktestRequest) -> dict[str, object]:
    """Replay a fixed strategy against recent completed, public candles."""
    values = _model_data(payload)
    try:
        candles = get_binance_spot_history(
            str(values["symbol"]), str(values["interval"]), int(values["bars"])
        )
        result = run_strategy_backtest(
            candles,
            str(values["strategy"]),
            starting_capital=float(values["starting_capital"]),
            risk_percent=float(values["risk_percent"]),
            fee_bps=float(values["fee_bps"]),
            slippage_bps=float(values["slippage_bps"]),
            max_holding_bars=int(values["max_holding_bars"]),
        )
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except BacktestInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "mode": "historical-paper-replay",
        "provider": "Binance Spot public candles",
        "symbol": str(values["symbol"]).upper().strip(),
        "interval": str(values["interval"]),
        "bar_count": len(candles),
        **result,
        "disclaimer": (
            "Historical replay is not a forecast. Fees, slippage, gaps, limited sample "
            "size and changing market conditions can materially change outcomes."
        ),
    }


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


@app.post("/api/daily-risk")
async def create_daily_risk_summary(payload: DailyRiskRequest) -> dict[str, object]:
    """Summarize a user-configured daily paper-risk cap without blocking actions."""
    try:
        summary = build_daily_risk_summary(
            capital=payload.capital,
            loss_limit_percent=payload.loss_limit_percent,
            realized_pnl=payload.realized_pnl,
            realized_loss=payload.realized_loss,
            open_planned_risk=payload.open_planned_risk,
            closed_today=payload.closed_today,
            open_positions=payload.open_positions,
        )
    except DailyRiskError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "mode": "paper-only",
        **asdict(summary),
        "disclaimer": (
            "Advisory journal estimate only. It excludes mark-to-market, fees and slippage, "
            "and never blocks a plan or order."
        ),
    }


@app.post("/api/bot-chat")
async def chat_with_loki(payload: BotChatRequest) -> dict[str, object]:
    """Answer from the dashboard context supplied for this message only."""
    values = _model_data(payload)
    return {
        "mode": "local-context-coach",
        "answer": answer_bot_question(values),
        "context_used": {
            "market": bool(payload.market and payload.market.symbol),
            "decision": bool(payload.decision and payload.decision.action),
            "journal": bool(payload.journal.closed_trades),
            "daily_risk": payload.daily_risk is not None,
        },
        "disclaimer": "Contextual paper research only; not a forecast, financial advice or an order.",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> Response:
    favicon = STATIC_DIR / "favicon.ico"
    return FileResponse(favicon) if favicon.exists() else Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png() -> Response:
    favicon = STATIC_DIR / "favicon.png"
    return FileResponse(favicon) if favicon.exists() else Response(status_code=204)


