from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Literal

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from loki.api.fusion import _require_local_action

from loki.version import __version__
from loki_v8 import train as train_module
from loki_v8.bot import LokiBot
from loki_v8.config import default_config
from loki_v8.montecarlo import monte_carlo_simulation
from loki_v8.persistence import get_logger as get_db_logger
from loki_v8.regime import detect_regime, regime_distribution
from loki_v8.strategy import EnsembleStrategy

logger = logging.getLogger("loki.api")

# Resolve repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates_dir = PROJECT_ROOT / "templates"
static_dir = PROJECT_ROOT / "static"

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    title="Loki Quantum Trading Platform",
    version=__version__,
    description="Institutional AI Algorithmic Trading Engine, REST/WebSocket API and Live Web Command Center",
)


@app.middleware("http")
async def private_terminal(request: Request, call_next):
    path = request.scope["path"]
    prefix = request.scope.get("root_path", "")
    if prefix and path.startswith(prefix):
        path = path[len(prefix) :] or "/"
    if path not in {"/", "/health", "/favicon.ico"}:
        try:
            _require_local_action(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


templates = Jinja2Templates(directory=str(templates_dir))

# Singleton bot instance
_bot: Optional[LokiBot] = None


def get_bot() -> LokiBot:
    global _bot
    if _bot is None:
        _bot = LokiBot(default_config())
    return _bot


def _safe_number(value, digits: int = 2):
    """Round a numeric value to JSON-safe form (NaN/inf become ``None``)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if math.isfinite(number) else None


# ---------------------------------------------------------------------------
# Background Autonomous Trading Engine
# ---------------------------------------------------------------------------
class AutonomousEngineState:
    def __init__(self):
        self.is_running = False
        self.interval = 60
        self.iterations = 0
        self.last_run: Optional[str] = None
        self.logs: List[str] = []
        self._task: Optional[asyncio.Task] = None
        self._trading = threading.Event()
        self._wake = asyncio.Event()

    def add_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.insert(0, f"[{ts}] {msg}")
        if len(self.logs) > 100:
            self.logs.pop()

    async def _loop(self):
        bot = get_bot()
        self.add_log(
            f"Autonomous Trading Engine STARTED ({bot.mode.upper()} mode, interval={self.interval}s)"
        )
        while self.is_running:
            try:
                self.iterations += 1
                self.last_run = datetime.now().isoformat()
                equity = await asyncio.to_thread(bot.step, self._trading.is_set)
                self.add_log(
                    f"Paper cycle #{self.iterations}: equity ${equity:,.2f}; {len(bot.broker.positions)} open positions; stops and risk limits checked."
                )
            except Exception as exc:
                self.add_log(f"Cycle #{self.iterations} exception: {exc}")
            if self.is_running:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    pass

    def start(self, interval: int = 60):
        if get_bot().mode != "paper":
            raise HTTPException(409, "Automatic execution is available in paper mode only")
        if not self.is_running:
            if self._task and not self._task.done():
                raise HTTPException(
                    409, "The previous paper cycle is stopping; wait for it to finish"
                )
            self.is_running = True
            self._trading.set()
            self._wake.clear()
            self.interval = interval
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self.is_running:
            self.is_running = False
            self._trading.clear()
            self._wake.set()
            self.add_log(
                "Paper engine stopping. A broker call already in flight may finish; new entries are disabled."
            )


auto_engine = AutonomousEngineState()

_STARTED_AT = time.monotonic()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class TerminalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class OrderRequest(TerminalModel):
    symbol: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9.^=/-]+$")
    action: Literal["BUY", "SELL", "CLOSE"]
    qty: Optional[float] = Field(default=None, gt=0, le=1e9)
    price: Optional[float] = Field(default=None, gt=0, le=1e9)


class ModeRequest(TerminalModel):
    mode: Literal["paper", "live"]


class V1OrderRequest(TerminalModel):
    symbol: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9.^=/-]+$")
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=1e9)
    order_type: Literal["market"] = "market"


class AutoLoopRequest(TerminalModel):
    action: Literal["start", "stop"]
    interval: int = Field(default=60, ge=15, le=3600)


# ---------------------------------------------------------------------------
# Core UI & Status Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def root(request: Request):
    """Render the web command center for browsers, or JSON for API test clients."""
    accept = request.headers.get("accept", "")
    ua = request.headers.get("user-agent", "").lower()
    is_browser = "text/html" in accept or (
        "mozilla" in ua or "chrome" in ua or "safari" in ua or "edge" in ua
    )
    if not is_browser:
        return JSONResponse(
            {
                "application": "Loki Trading Platform",
                "version": __version__,
                "status": "operational",
            }
        )

    bot = get_bot()
    context = {
        "request": request,
        "version": __version__,
        "mode": bot.mode,
        "symbols": bot.cfg.symbols,
    }
    return templates.TemplateResponse(request=request, name="v8_terminal.html", context=context)


@app.get("/health")
async def health():
    bot = get_bot()
    return JSONResponse(
        {
            "status": "healthy",
            "service": "loki",
            "version": __version__,
            "uptime_seconds": round(time.monotonic() - _STARTED_AT),
            "active_strategies": 1,
            "market_connection": "not_verified",
            "mode": bot.mode,
            "open_positions": len(bot.broker.positions),
        }
    )


@app.get("/api/status")
async def get_status():
    bot = get_bot()
    quotes = (
        bot.provider.get_quotes(list(bot.broker.positions.keys())) if bot.broker.positions else {}
    )
    eq = bot.broker.equity(quotes)
    open_pos = len(bot.broker.positions)
    pnl = eq - bot.cfg.initial_cash
    pnl_pct = (eq / bot.cfg.initial_cash - 1.0) * 100.0 if bot.cfg.initial_cash > 0 else 0.0

    return {
        "status": "online",
        "mode": bot.mode,
        "version": __version__,
        "equity": round(eq, 2),
        "cash": round(bot.broker.cash, 2),
        "initial_capital": bot.cfg.initial_cash,
        "total_pnl": round(pnl, 2),
        "total_pnl_pct": round(pnl_pct, 2),
        "open_positions": open_pos,
        "total_trades": len(bot.broker.trades),
        "symbols": bot.cfg.symbols,
        "max_open_positions": bot.cfg.max_open_positions,
        "server_time": datetime.now().isoformat(),
        "autonomous_running": auto_engine.is_running,
        "factor_weights": bot.cfg.factor_weights,
        "supabase": get_db_logger().status(),
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@app.post("/token")
async def login():
    raise HTTPException(
        410,
        "Default passwords are disabled. Use the local launcher's session token in X-Loki-Local-Token.",
    )


def verify_bearer(request: Request):
    _require_local_action(request)
    return "local-session"


# ---------------------------------------------------------------------------
# V1 API Compatibility Endpoints (for institutional tests & integrations)
# ---------------------------------------------------------------------------
@app.get("/api/v1/portfolio")
async def get_portfolio_v1(auth: str = Depends(verify_bearer)):
    bot = get_bot()
    quotes = (
        bot.provider.get_quotes(list(bot.broker.positions.keys())) if bot.broker.positions else {}
    )
    eq = bot.broker.equity(quotes)
    return {
        "total_value": eq,
        "cash": bot.broker.cash,
        "daily_pnl": eq - bot.cfg.initial_cash,
        "positions_count": len(bot.broker.positions),
    }


@app.get("/api/v1/positions")
async def get_positions_v1(auth: str = Depends(verify_bearer)):
    bot = get_bot()
    return [
        {
            "symbol": p.symbol,
            "side": p.side,
            "quantity": p.qty,
            "entry_price": p.avg_entry,
        }
        for p in bot.broker.positions.values()
    ]


@app.post("/api/v1/orders")
async def place_order_v1(order: V1OrderRequest, auth: str = Depends(verify_bearer)):
    bot = get_bot()
    side = order.side.lower()
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="side must be 'buy' or 'sell'")

    price = bot.provider.get_latest_price(order.symbol)
    if not price or not math.isfinite(price) or price <= 0:
        raise HTTPException(503, "No valid market quote; order was not placed")
    if side == "sell" and order.symbol not in bot.broker.positions and not bot.cfg.allow_short:
        raise HTTPException(409, "No paper position to sell; short entries are disabled")
    if side == "buy":
        filled = bot.broker.buy(order.symbol, order.quantity, price)
    else:
        filled = bot.broker.sell(order.symbol, order.quantity, price)
    if not filled:
        raise HTTPException(409, "Paper broker rejected the order")
    bot.broker.save_state({order.symbol: price})

    return {
        "order_id": f"ord_{int(time.time() * 1000)}",
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "status": "paper_filled",
    }


class StrategySettings(TerminalModel):
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=5)
    max_open_positions: int = Field(default=4, ge=1, le=20)


def _strategy_name(name):
    if name != "Ensemble":
        raise HTTPException(404, "Unknown strategy. The v8 multi-factor strategy is Ensemble.")


@app.get("/api/v1/strategies")
async def get_strategies_v1(auth: str = Depends(verify_bearer)):
    cfg = get_bot().cfg
    return [
        {
            "name": "Ensemble",
            "enabled": auto_engine.is_running,
            "risk_per_trade_pct": cfg.risk_per_trade_pct,
            "max_open_positions": cfg.max_open_positions,
            "symbols": cfg.symbols,
        }
    ]


@app.put("/api/v1/strategies/{name}")
async def update_strategy_v1(
    name: str, config: StrategySettings, auth: str = Depends(verify_bearer)
):
    _strategy_name(name)
    if auto_engine.is_running:
        raise HTTPException(409, "Stop the paper loop before changing risk settings")
    cfg = get_bot().cfg
    cfg.risk_per_trade_pct = config.risk_per_trade_pct
    cfg.max_open_positions = config.max_open_positions
    return {"status": "updated", "strategy": name, "config": config.model_dump()}


@app.post("/api/v1/strategies/{name}/start")
async def start_strategy_v1(name: str, auth: str = Depends(verify_bearer)):
    _strategy_name(name)
    auto_engine.start()
    return {"status": "started", "strategy": name, "mode": "paper"}


@app.post("/api/v1/strategies/{name}/stop")
async def stop_strategy_v1(name: str, auth: str = Depends(verify_bearer)):
    _strategy_name(name)
    auto_engine.stop()
    return {"status": "stopped", "strategy": name}


# ---------------------------------------------------------------------------
# Quantum Trading Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/scan")
async def get_scan(symbols: Optional[str] = Query(None)):
    bot = get_bot()
    sym_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else bot.cfg.symbols
    )
    signals = bot.scan(sym_list)
    results = []
    for s in signals:
        results.append(
            {
                "symbol": s.symbol,
                "action": s.action,
                "score": round(s.score, 1),
                "confidence": round(s.confidence, 1),
                "entry_price": round(s.entry_price, 2),
                "stop_loss": round(s.stop_loss, 2),
                "take_profit": round(s.take_profit, 2),
                "target_2": round(getattr(s, "target_2", 0.0), 2),
                "risk_reward": getattr(s, "risk_reward", 1.5),
                "squeeze_status": getattr(s, "squeeze_status", "OFF"),
                "reasons": getattr(s, "reasons", []),
            }
        )
    # Regime context per symbol (cheap: provider cache is warm from the scan).
    regimes = {}
    for sym in sym_list:
        try:
            r = detect_regime(bot.provider.fetch_history(sym, bot.cfg.period, bot.cfg.timeframe))
            regimes[sym] = {
                "state": r.state,
                "confidence": r.confidence,
                "volatility_rank": r.volatility_rank,
                "description": r.description,
            }
        except Exception:  # noqa: BLE001 — regime context must never break the scan
            continue
    return {"count": len(results), "signals": results, "regimes": regimes}


@app.get("/api/portfolio")
async def get_portfolio():
    bot = get_bot()
    symbols = list(bot.broker.positions.keys())
    quotes = bot.provider.get_quotes(symbols) if symbols else {}
    positions_data = []

    for sym, pos in bot.broker.positions.items():
        cur_price = quotes.get(sym, pos.avg_entry)
        val = pos.market_value(cur_price)
        unrealized = pos.unrealized_pnl(cur_price)
        pos_invested = pos.avg_entry * abs(pos.qty)
        unrealized_pct = (unrealized / pos_invested) * 100.0 if pos_invested > 0 else 0.0

        positions_data.append(
            {
                "symbol": sym,
                "side": pos.side,
                "qty": round(pos.qty, 4),
                "avg_entry": round(pos.avg_entry, 2),
                "current_price": round(cur_price, 2),
                "market_value": round(val, 2),
                "unrealized_pnl": round(unrealized, 2),
                "unrealized_pnl_pct": round(unrealized_pct, 2),
                "stop_loss": round(pos.stop_loss, 2),
                "take_profit": round(pos.take_profit, 2),
            }
        )

    trades_data = []
    for t in reversed(bot.broker.trades[-20:]):
        trades_data.append(
            {
                "symbol": t.symbol,
                "side": t.side,
                "qty": round(t.qty, 4),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
            }
        )

    eq = bot.broker.equity(quotes)
    return {
        "equity": round(eq, 2),
        "cash": round(bot.broker.cash, 2),
        "positions": positions_data,
        "recent_trades": trades_data,
    }


@app.post("/api/order")
async def place_order(order: OrderRequest):
    bot = get_bot()
    sym = order.symbol.strip().upper()
    action = order.action.strip().upper()
    if action == "SELL" and sym not in bot.broker.positions and not bot.cfg.allow_short:
        raise HTTPException(409, "No paper position to sell; short entries are disabled")
    price = order.price or bot.provider.get_latest_price(sym)

    if not price or not math.isfinite(price) or price <= 0:
        raise HTTPException(status_code=400, detail=f"Cannot fetch valid market price for {sym}")

    success = False
    if action == "BUY":
        qty = order.qty or bot.risk.position_size(bot.broker.cash, price, price * 0.95)
        if qty <= 0:
            qty = max(1.0, round(bot.broker.cash * 0.05 / price, 2))
        success = bot.broker.buy(sym, qty, price)
    elif action == "SELL":
        qty = order.qty or (bot.broker.positions[sym].qty if sym in bot.broker.positions else 0.0)
        success = bot.broker.sell(sym, qty, price)
    elif action == "CLOSE":
        success = bot.broker.close(sym, price)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    # Persist state
    bot.broker.save_state({sym: price})

    # Fire-and-forget vault log for manual orders
    if success:
        if action == "BUY":
            get_db_logger().log_trade(
                symbol=sym,
                side="long",
                qty=order.qty or 0.0,
                entry_price=price,
                mode=bot.mode,
                source="manual",
                equity_at_trade=bot.broker.cash,
            )
        elif action == "SELL" and bot.broker.trades:
            t = bot.broker.trades[-1]
            get_db_logger().log_trade(
                symbol=t.symbol,
                side=t.side,
                qty=t.qty,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct,
                exit_reason="manual",
                mode=bot.mode,
                source="manual",
            )

    return {
        "success": success,
        "symbol": sym,
        "action": action,
        "fill_price": round(price, 2),
        "new_cash": round(bot.broker.cash, 2),
    }


@app.post("/api/mode")
async def switch_mode(req: ModeRequest):
    bot = get_bot()
    mode = req.mode.lower().strip()
    if auto_engine.is_running:
        raise HTTPException(409, "Stop the paper loop before switching modes")
    try:
        bot.switch_mode(mode)
        return {"success": True, "mode": bot.mode}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/council")
async def get_council(symbols: Optional[str] = Query(None)):
    bot = get_bot()
    sym_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else bot.cfg.symbols[:6]
    )
    report = bot.agent_scan(sym_list)
    return report


@app.get("/api/backtest")
async def run_backtest_endpoint(symbol: str = "AAPL", period: str = "2y"):
    bot = get_bot()
    try:
        res, trained_profile = bot.backtest_trained(symbol.strip().upper(), period=period)

        # Downsample the full equity curve so the UI can draw the real
        # account trajectory instead of reconstructing it from the last 15 trades.
        curve_points = []
        try:
            equity = res.equity_curve
            if equity is not None and len(equity) > 0:
                step = max(1, len(equity) // 220)
                sampled = list(zip(equity.index, equity.values))[::step]
                last_index = equity.index[-1]
                if sampled and sampled[-1][0] != last_index:
                    sampled.append((last_index, equity.iloc[-1]))
                curve_points = [
                    {
                        "t": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                        "v": _safe_number(value),
                    }
                    for idx, value in sampled
                ]
        except Exception:  # noqa: BLE001 — chart data must never break the endpoint
            curve_points = []

        return {
            "symbol": res.symbol,
            "trained_profile_applied": bool(trained_profile),
            "trained_profile": trained_profile,
            "initial_capital": _safe_number(res.initial_capital),
            "final_equity": _safe_number(res.final_equity),
            "total_return_pct": _safe_number(res.total_return_pct),
            "cagr_pct": _safe_number(res.cagr_pct),
            "win_rate_pct": _safe_number(res.win_rate_pct),
            "profit_factor": _safe_number(res.profit_factor),
            "max_drawdown_pct": _safe_number(res.max_drawdown_pct),
            "sharpe": _safe_number(res.sharpe),
            "sortino": _safe_number(res.sortino),
            "total_trades": res.total_trades,
            "equity_curve": curve_points,
            "trades": [
                {
                    "side": t.side,
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "exit_reason": t.exit_reason,
                }
                for t in res.trades[-15:]
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Strategy Trainer — walk-forward parameter training on historical data
# ---------------------------------------------------------------------------
class ApplyTrainingRequest(TerminalModel):
    symbol: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9.^=/-]+$")


@app.get("/api/training/run")
async def run_training(
    symbols: Optional[str] = Query(None),
    period: str = Query("5y"),
    train_frac: float = Query(0.7, ge=0.5, le=0.9),
    optimize_weights: bool = Query(False, description="Sweep the 14 factor-weight presets"),
    refine_rounds: int = Query(
        1, ge=1, le=3, description="Auto-refinement rounds until hurdles pass"
    ),
    objective: str = Query("sharpe", pattern="^(sharpe|win_rate|return)$"),
    target_win_rate: Optional[float] = Query(None, ge=1.0, le=100.0),
    target_profitable_months: Optional[float] = Query(None, ge=1.0, le=100.0),
):
    """Train ensemble parameters on historical bars (walk-forward, honest OOS).

    ``objective="win_rate"`` + ``target_win_rate=90`` is the aggressive mode:
    it keeps refining the search neighborhood (small take-profits, wide
    stops, re-weighted factors) until the 90% profitability target is met —
    or plainly reports the best verified configuration.
    """
    bot = get_bot()
    sym_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else list(bot.cfg.symbols)
    )
    try:
        report = await asyncio.to_thread(
            train_module.train,
            sym_list,
            bot.cfg,
            period=period,
            train_frac=train_frac,
            optimize_weights=optimize_weights,
            refine_rounds=refine_rounds,
            objective=objective,
            target_win_rate=target_win_rate,
            target_profitable_months=target_profitable_months,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"training failed: {exc}")

    # Vault: persist a trimmed summary of the run (fire-and-forget).
    good = [s["symbol"] for s in report.get("symbols", []) if s.get("good")]
    get_db_logger().log_training_report(
        period=str(period),
        payload={
            "period": period,
            "generated_at": report.get("generated_at"),
            "objective": report.get("objective"),
            "target_win_rate": target_win_rate,
            "symbols_trained": len(report.get("symbols", [])),
            "good_symbols": good,
            "consensus": report.get("consensus"),
        },
    )
    return report


@app.get("/api/training/report")
async def get_training_report():
    """Return the most recent persisted training report (empty if none)."""
    report = train_module.load_report(get_bot().cfg)
    if report is None:
        return {"generated_at": None, "symbols": []}
    return report


@app.post("/api/training/apply-consensus")
async def apply_consensus_training():
    """Apply the cross-symbol consensus parameters to every symbol's config."""
    bot = get_bot()
    if auto_engine.is_running:
        raise HTTPException(409, "Stop the paper loop before applying training parameters")
    report = train_module.load_report(bot.cfg)
    if not report:
        raise HTTPException(status_code=404, detail="no training report found")
    applied = train_module.apply_consensus(report, bot.cfg)
    if not applied:
        raise HTTPException(status_code=400, detail="report has no consensus to apply")
    return {"symbol": "ALL", "applied": applied, "success": True}


# ---------------------------------------------------------------------------
# Monte Carlo risk engine — bootstrap thousands of replayed trade sequences
# ---------------------------------------------------------------------------
@app.get("/api/montecarlo")
async def run_montecarlo(
    symbol: str = "AAPL",
    period: str = "2y",
    n_sims: int = Query(2000, ge=100, le=10000),
    seed: Optional[int] = Query(None),
):
    """Backtest the current config on history, then bootstrap the trade
    sequence into ``n_sims`` alternate lifetimes (percentile fan, drawdown
    distribution, VaR/CVaR, risk-of-ruin)."""
    bot = get_bot()

    def _run():
        res, trained_profile = bot.backtest_trained(symbol.strip().upper(), period=period)
        mc = monte_carlo_simulation(
            res.trades,
            initial_equity=res.initial_capital,
            n_sims=n_sims,
            seed=seed,
        )
        summary = {
            "initial_capital": _safe_number(res.initial_capital),
            "total_return_pct": _safe_number(res.total_return_pct),
            "win_rate_pct": _safe_number(res.win_rate_pct, 1),
            "profit_factor": _safe_number(res.profit_factor),
            "max_drawdown_pct": _safe_number(res.max_drawdown_pct),
            "total_trades": res.total_trades,
        }
        return {
            "symbol": res.symbol,
            "period": period,
            "trained_profile_applied": bool(trained_profile),
            "trained_profile": trained_profile,
            "backtest": summary,
            "monte_carlo": mc,
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Market Regime Monitor — trend/vol classification per symbol
# ---------------------------------------------------------------------------
@app.get("/api/regime")
async def get_regime(
    symbols: Optional[str] = Query(None),
    period: str = Query("5y"),
):
    """Regime classification (STRONG_BULL/BULL/RANGING/BEAR/CRISIS) plus the
    share of history each symbol spent in each regime."""
    bot = get_bot()
    raw = symbols or ",".join(bot.cfg.symbols[:6])
    sym_list = [s.strip().upper() for s in raw.split(",") if s.strip()][:8]

    def _run():
        out = []
        for sym in sym_list:
            try:
                df = bot.provider.fetch_history(sym, period, bot.cfg.timeframe)
                r = detect_regime(df)
                dist = regime_distribution(EnsembleStrategy(bot.cfg).compute_factors(df))
                out.append(
                    {
                        "symbol": sym,
                        "state": r.state,
                        "confidence": r.confidence,
                        "trend_score": r.trend_score,
                        "adx": round(r.adx, 1),
                        "volatility_pct": round(r.volatility_pct, 3),
                        "volatility_rank": r.volatility_rank,
                        "description": r.description,
                        "distribution": dist,
                        "bars": int(len(df)),
                    }
                )
            except Exception as exc:  # noqa: BLE001 — one bad ticker must not kill the panel
                out.append({"symbol": sym, "error": str(exc)})
        states = [s["state"] for s in out if "state" in s]
        summary = {
            st: states.count(st)
            for st in ("STRONG_BULL", "BULL", "RANGING", "BEAR", "CRISIS")
            if states.count(st)
        }
        return {"symbols": out, "summary": summary}

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Supabase Data Vault — optional cloud persistence (configure any time)
# ---------------------------------------------------------------------------
@app.get("/api/supabase/status")
async def supabase_status():
    return get_db_logger().status()


@app.post("/api/supabase/test")
async def supabase_test():
    """Read-only verification of the configured Supabase table."""
    return await asyncio.to_thread(get_db_logger().test_connection)


@app.post("/api/training/apply")
async def apply_training(req: ApplyTrainingRequest):
    """Apply a symbol's best trained parameters to the running engine."""
    bot = get_bot()
    if auto_engine.is_running:
        raise HTTPException(409, "Stop the paper loop before applying training parameters")
    report = train_module.load_report(bot.cfg)
    if report is None:
        raise HTTPException(status_code=404, detail="no training report; run training first")
    symbol = req.symbol.strip().upper()
    applied = train_module.apply_best(report, symbol, bot.cfg)
    if not applied:
        raise HTTPException(status_code=404, detail=f"no successful training result for {symbol}")
    return {"symbol": symbol, "applied": applied}


# ---------------------------------------------------------------------------
# Autonomous Background Trading Engine Controls
# ---------------------------------------------------------------------------
@app.post("/api/bot/autonomous")
async def control_autonomous_loop(req: AutoLoopRequest):
    if req.action == "start":
        auto_engine.start(req.interval or 60)
    elif req.action == "stop":
        auto_engine.stop()
    else:
        raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'")

    return {
        "is_running": auto_engine.is_running,
        "interval": auto_engine.interval,
        "iterations": auto_engine.iterations,
        "last_run": auto_engine.last_run,
        "logs": auto_engine.logs[:20],
    }


@app.get("/api/bot/autonomous")
async def get_autonomous_loop_status():
    return {
        "is_running": auto_engine.is_running,
        "interval": auto_engine.interval,
        "iterations": auto_engine.iterations,
        "last_run": auto_engine.last_run,
        "logs": auto_engine.logs[:20],
    }


# ---------------------------------------------------------------------------
# WebSocket Real-Time Stream
# ---------------------------------------------------------------------------
@app.websocket("/ws/market-data")
async def websocket_market_data(websocket: WebSocket):
    # Send the launcher token in a subprotocol, never in a URL or access log.
    offered = websocket.scope.get("subprotocols", [])
    token = next((p[5:] for p in offered if p.startswith("loki.")), "")
    scope = dict(websocket.scope)
    scope["type"] = "http"
    scope["scheme"] = "https" if scope.get("scheme") == "wss" else "http"
    scope["headers"] = list(scope["headers"]) + [(b"x-loki-local-token", token.encode())]
    try:
        _require_local_action(Request(scope))
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept(subprotocol="loki" if "loki" in offered else None)
    bot = get_bot()
    try:
        # Initial heartbeat. Quote fetching touches the network, so it must
        # never prevent the first message: if quotes fail we still send the
        # heartbeat with cached/zeroed equity (a silent close here would hang
        # clients waiting for data).
        try:
            quotes = (
                bot.provider.get_quotes(list(bot.broker.positions.keys()))
                if bot.broker.positions
                else {}
            )
        except Exception:
            quotes = {}
        eq = bot.broker.equity(quotes)
        await websocket.send_json(
            {
                "timestamp": datetime.now().isoformat(),
                "portfolio_value": eq,
                "cash": bot.broker.cash,
                "open_positions": len(bot.broker.positions),
                "mode": bot.mode,
            }
        )
        while True:
            # Echo or stream
            data = await websocket.receive_text()
            await websocket.send_json(
                {
                    "timestamp": datetime.now().isoformat(),
                    "portfolio_value": bot.broker.equity({}),
                    "received": data,
                }
            )
    except (WebSocketDisconnect, Exception):
        pass


# ---------------------------------------------------------------------------
# Prometheus Metrics Endpoint
# ---------------------------------------------------------------------------
@app.get("/metrics")
async def get_metrics():
    bot = get_bot()
    eq = bot.broker.equity({})
    content = (
        f"# HELP loki_portfolio_value_dollars Current portfolio value\n"
        f"# TYPE loki_portfolio_value_dollars gauge\n"
        f"loki_portfolio_value_dollars {eq:.2f}\n"
        f"# HELP loki_open_positions_total Total open positions count\n"
        f"# TYPE loki_open_positions_total gauge\n"
        f"loki_open_positions_total {len(bot.broker.positions)}\n"
        f"# HELP loki_trades_total Total executed trades\n"
        f"# TYPE loki_trades_total counter\n"
        f"loki_trades_total {len(bot.broker.trades)}\n"
    )
    return Response(content=content, media_type="text/plain; version=0.0.4")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    static_fav = static_dir / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)
    root_fav = PROJECT_ROOT / "loki.ico"
    if root_fav.exists():
        return FileResponse(root_fav)
    return JSONResponse(status_code=204, content=None)
