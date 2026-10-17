from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from loki.version import __version__
from loki_v8.bot import LokiBot
from loki_v8.config import default_config

logger = logging.getLogger("loki.api")

# Resolve repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates_dir = PROJECT_ROOT / "templates"
static_dir = PROJECT_ROOT / "static"

app = FastAPI(
    title="Loki Quantum Trading Platform",
    version=__version__,
    description="Institutional AI Algorithmic Trading Engine and Live Web Command Center",
)

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates = Jinja2Templates(directory=str(templates_dir))

# Singleton bot instance
_bot: Optional[LokiBot] = None


def get_bot() -> LokiBot:
    global _bot
    if _bot is None:
        _bot = LokiBot(default_config())
    return _bot


class OrderRequest(BaseModel):
    symbol: str
    action: str  # "BUY", "SELL", "CLOSE"
    qty: Optional[float] = None
    price: Optional[float] = None


class ModeRequest(BaseModel):
    mode: str  # "paper" or "live"


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render the cyber-institutional trading terminal."""
    bot = get_bot()
    context = {
        "request": request,
        "version": __version__,
        "mode": bot.mode,
        "symbols": bot.cfg.symbols,
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@app.get("/health")
async def health():
    bot = get_bot()
    return JSONResponse({
        "status": "online",
        "service": "loki",
        "version": __version__,
        "mode": bot.mode,
        "open_positions": len(bot.broker.positions),
    })


@app.get("/api/status")
async def get_status():
    bot = get_bot()
    quotes = bot.provider.get_quotes(list(bot.broker.positions.keys())) if bot.broker.positions else {}
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
    }


@app.get("/api/scan")
async def get_scan(symbols: Optional[str] = Query(None)):
    bot = get_bot()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else bot.cfg.symbols
    signals = bot.scan(sym_list)
    results = []
    for s in signals:
        results.append({
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
        })
    return {"count": len(results), "signals": results}


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

        positions_data.append({
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
        })

    trades_data = []
    for t in reversed(bot.broker.trades[-20:]):
        trades_data.append({
            "symbol": t.symbol,
            "side": t.side,
            "qty": round(t.qty, 4),
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2),
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct, 2),
        })

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
    price = order.price or bot.provider.get_latest_price(sym)

    if price <= 0:
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
    try:
        bot.switch_mode(mode)
        return {"success": True, "mode": bot.mode}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/council")
async def get_council(symbols: Optional[str] = Query(None)):
    bot = get_bot()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else bot.cfg.symbols[:6]
    report = bot.agent_scan(sym_list)
    return report


@app.get("/api/backtest")
async def run_backtest_endpoint(symbol: str = "AAPL", period: str = "2y"):
    bot = get_bot()
    try:
        res = bot.backtest(symbol.strip().upper(), period=period)
        return {
            "symbol": res.symbol,
            "initial_capital": res.initial_capital,
            "final_equity": round(res.final_equity, 2),
            "total_return_pct": round(res.total_return_pct, 2),
            "cagr_pct": round(res.cagr_pct, 2),
            "win_rate_pct": round(res.win_rate_pct, 2),
            "profit_factor": round(res.profit_factor, 2),
            "max_drawdown_pct": round(res.max_drawdown_pct, 2),
            "sharpe": round(res.sharpe, 2),
            "sortino": round(res.sortino, 2),
            "total_trades": res.total_trades,
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


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    static_fav = static_dir / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)
    root_fav = PROJECT_ROOT / "loki.ico"
    if root_fav.exists():
        return FileResponse(root_fav)
    return JSONResponse(status_code=204, content=None)
