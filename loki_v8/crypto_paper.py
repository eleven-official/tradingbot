"""Simulated crypto paper-trading session on the trained Loki book.

Two modes, one ledger, no real orders unless an Alpaca paper account is
explicitly wired in:

``replay`` (default)
    Walks every symbol in the crypto universe through the event-driven
    engine using the *trained* profile for that symbol (or the crypto
    consensus when the symbol has no verified profile). Fills are simulated
    at real historical prices with the configured slippage, so the blotter
    is a paper record of what the book would have done — not a prediction
    and not a claim about future returns.

``step``
    Runs the Director → Quant → Risk → Execution chain on the latest closed
    bar for each symbol, persisting the resulting fills to an isolated
    crypto paper account. ``--mirror`` forwards each fill to Alpaca's PAPER
    endpoint, which is the only way a simulated decision can appear in his
    Alpaca paper account: Alpaca only fills at live prices, so a historical
    replay cannot be mirrored — it would book today's price against a fill
    that happened weeks ago.

Capital is divided into equal sleeves across the symbols actually traded,
so one volatile symbol cannot dominate the session P&L.

Run:
    python -m loki_v8.crypto_paper
    python -m loki_v8.crypto_paper --mode step --mirror
    python -m loki_v8.crypto_paper --bars 120 --capital 25000 --symbols BTC-USD,ETH-USD
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

# Liquid majors with enough daily history to split honestly. Mirrors
# ``train_crypto.DEFAULT_CRYPTO_UNIVERSE`` so the book and the session agree.
DEFAULT_UNIVERSE: Tuple[str, ...] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "LINK-USD",
    "AVAX-USD",
    "LTC-USD",
)

# Crypto trades every calendar day, so annualisation uses 365 — not 252.
BARS_PER_YEAR = 365

ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"

SESSION_DIR = Path("state") / "crypto_paper_sessions"
LEDGER_PATH = Path("state") / "crypto_paper_ledger.jsonl"


# ---------------------------------------------------------------------------
# Book / config resolution
# ---------------------------------------------------------------------------
def load_book() -> Dict[str, Any]:
    """Return the trained report (state dir first, bundled snapshot second)."""
    from loki_v8.train import load_report

    return load_report() or {}


def profile_for(report: Dict[str, Any], symbol: str) -> Tuple[Dict[str, Any], str]:
    """Pick the parameter block a symbol should trade with.

    Order of preference: the symbol's own verified profile, then the
    crypto-only consensus, then the mixed consensus, then the shipped
    defaults. The source label travels with the params so the blotter can
    say which one was actually used instead of implying every symbol is
    individually trained.
    """
    for entry in report.get("symbols") or []:
        if (
            str(entry.get("symbol", "")).upper() == symbol.upper()
            and entry.get("ok")
            and entry.get("best_params")
        ):
            return dict(entry["best_params"]), "trained"
    for key in ("crypto_consensus", "consensus"):
        block = report.get(key) or {}
        if block.get("params"):
            return dict(block["params"]), key
    return {}, "defaults"


def build_config(
    params: Dict[str, Any],
    *,
    sleeve: float,
    period: str,
    timeframe: str,
    state_dir: str = "state/crypto",
):
    """A per-symbol config with the trained block applied."""
    from loki_v8.config import LokiConfig
    from loki_v8.train import apply_params

    cfg = LokiConfig(period=period, timeframe=timeframe, initial_cash=sleeve, state_dir=state_dir)
    apply_params(cfg, params)
    return cfg


# ---------------------------------------------------------------------------
# replay — historical paper session
# ---------------------------------------------------------------------------
def replay(
    symbols: Sequence[str],
    *,
    report: Optional[Dict[str, Any]] = None,
    bars: int = 180,
    capital: float = 100_000.0,
    period: str = "3y",
    timeframe: str = "1d",
    slippage_bps: float = 3.0,
    write_ledger: bool = True,
) -> Dict[str, Any]:
    """Simulate the book over the last ``bars`` tradeable bars per symbol."""
    from loki_v8.backtest import run_backtest
    from loki_v8.data import get_provider

    book = report if report is not None else load_book()
    provider = get_provider()
    universe = list(dict.fromkeys(s.upper() for s in symbols))
    sleeve = capital / max(1, len(universe))

    trades: List[Dict[str, Any]] = []
    per_symbol: List[Dict[str, Any]] = []
    curves: Dict[str, pd.Series] = {}
    skipped: List[Dict[str, str]] = []

    for symbol in universe:
        params, source = profile_for(book, symbol)
        cfg = build_config(
            params, sleeve=sleeve, period=period, timeframe=timeframe, state_dir="state/crypto"
        )
        cfg.slippage_bps = slippage_bps
        need = cfg.lookback_bars + 60 + bars

        try:
            history = provider.fetch_history(symbol, period, timeframe)
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not kill the session
            skipped.append({"symbol": symbol, "reason": f"data fetch failed: {exc}"})
            continue
        if history is None or history.empty:
            skipped.append({"symbol": symbol, "reason": "no bars returned"})
            continue
        if len(history) < need:
            skipped.append(
                {"symbol": symbol, "reason": f"only {len(history)} bars, need {need} for warmup + window"}
            )
            continue

        window = history.iloc[-need:]
        result = run_backtest(window, cfg, symbol=symbol, bars_per_year=BARS_PER_YEAR)

        for t in result.trades:
            trades.append(
                {
                    "symbol": symbol,
                    "side": t.side,
                    "qty": round(float(t.qty), 8),
                    "entry_time": str(t.entry_time),
                    "exit_time": str(t.exit_time),
                    "entry_price": round(float(t.entry_price), 6),
                    "exit_price": round(float(t.exit_price), 6),
                    "pnl": round(float(t.pnl), 2),
                    "pnl_pct": round(float(t.pnl_pct), 3),
                    "exit_reason": t.exit_reason,
                    "holding_bars": _bars_between(window.index, t.entry_time, t.exit_time),
                    "profile": source,
                    "preset": (params.get("factor_preset") or ""),
                }
            )

        curves[symbol] = result.equity_curve
        per_symbol.append(
            {
                "symbol": symbol,
                "profile": source,
                "preset": params.get("factor_preset") or "",
                "trades": result.total_trades,
                "return_pct": round(result.total_return_pct, 2),
                "win_rate_pct": round(result.win_rate_pct, 1),
                "profit_factor": round(result.profit_factor, 2) if result.profit_factor != float("inf") else "inf",
                "max_drawdown_pct": round(result.max_drawdown_pct, 2),
                "sharpe": round(result.sharpe, 2),
                "final_equity": round(result.final_equity, 2),
            }
        )

    portfolio = _combine_curves(curves, sleeve)
    summary = _session_summary(trades, portfolio, capital, sleeve, len(per_symbol))
    trades.sort(key=lambda row: row["exit_time"])

    payload: Dict[str, Any] = {
        "session_id": datetime.now().strftime("%Y%m%dT%H%M%S"),
        "mode": "replay",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "book_generated_at": book.get("generated_at"),
        "bars": bars,
        "timeframe": timeframe,
        "slippage_bps": slippage_bps,
        "capital": round(capital, 2),
        "sleeve": round(sleeve, 2),
        "portfolio": summary,
        "symbols": per_symbol,
        "skipped": skipped,
        "trades": trades,
        "equity_curve": [
            {"t": str(idx), "equity": round(float(value), 2)} for idx, value in portfolio.items()
        ],
        "disclaimer": (
            "Simulated fills at historical prices. No order was sent anywhere. "
            "Backtested behaviour does not predict future returns."
        ),
    }

    if write_ledger and trades:
        _write_session(payload)
    payload["ledger_path"] = str(SESSION_DIR) if write_ledger and trades else None
    return payload


def _bars_between(index: pd.Index, entry, exit_) -> int:
    """Bars held, tolerant of timestamps that fall between index values."""
    try:
        start = index.get_indexer([entry], method="nearest")[0]
        end = index.get_indexer([exit_], method="nearest")[0]
    except Exception:  # noqa: BLE001 - a tz mismatch must not break the blotter
        return 0
    if start < 0 or end < 0:
        return 0
    return int(max(0, end - start))


def _combine_curves(curves: Dict[str, pd.Series], sleeve: float) -> pd.Series:
    """Sum equally-sized sleeves into one portfolio equity curve."""
    if not curves:
        return pd.Series(dtype=float)
    frame = pd.concat(curves, axis=1).sort_index()
    frame = frame.ffill()
    # A symbol whose first bar lands after another's contributes its sleeve
    # until it actually trades, so the portfolio starts at full capital.
    frame = frame.fillna(sleeve)
    return frame.sum(axis=1)


def _session_summary(
    trades: List[Dict[str, Any]],
    portfolio: pd.Series,
    capital: float,
    sleeve: float,
    active_symbols: int,
) -> Dict[str, Any]:
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win else 0.0)

    max_dd = 0.0
    if len(portfolio) > 1:
        running = portfolio.cummax()
        max_dd = float(((portfolio - running) / running * 100.0).min())

    return {
        "capital": round(capital, 2),
        "equity_start": round(sleeve * active_symbols, 2),
        "equity_end": round(float(portfolio.iloc[-1]) if len(portfolio) else capital, 2),
        "pnl": round(sum(pnls), 2),
        "return_pct": round(sum(pnls) / capital * 100.0, 2) if capital else 0.0,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1) if pnls else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0.0,
        # Mean P&L per fill. The trainer ranks profiles on this, so the paper
        # session reports it too: a high hit rate with a tiny average win and a
        # large average loss is visible in one number instead of hidden behind
        # the win percentage.
        "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "active_symbols": active_symbols,
    }


def _write_session(payload: Dict[str, Any]) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSION_DIR / f"session_{payload['session_id']}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        for trade in payload["trades"]:
            handle.write(
                json.dumps(
                    {
                        "session_id": payload["session_id"],
                        "mode": "replay",
                        "recorded_at": payload["generated_at"],
                        **trade,
                    },
                    default=str,
                )
                + "\n"
            )
    payload["session_file"] = str(path)


# ---------------------------------------------------------------------------
# step — one live decision per symbol, persisted paper fills
# ---------------------------------------------------------------------------
def step(
    symbols: Sequence[str],
    *,
    report: Optional[Dict[str, Any]] = None,
    capital: float = 100_000.0,
    period: str = "3y",
    state_dir: str = "state/crypto",
    mirror: bool = False,
    write_ledger: bool = True,
) -> Dict[str, Any]:
    """Run the agent chain on the latest bar and persist any paper fills."""
    from loki_v8.agents import LokiAgentPipeline
    from loki_v8.broker import PaperBroker
    from loki_v8.config import LokiConfig
    from loki_v8.data import get_provider

    book = report if report is not None else load_book()
    provider = get_provider()
    universe = list(dict.fromkeys(s.upper() for s in symbols))

    base = LokiConfig(period=period, initial_cash=capital, state_dir=state_dir)
    broker = PaperBroker(base)
    quotes = provider.get_quotes(universe)

    decisions: List[Dict[str, Any]] = []
    fills: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for symbol in universe:
        params, source = profile_for(book, symbol)
        cfg = build_config(
            params, sleeve=capital, period=period, timeframe=base.timeframe, state_dir=state_dir
        )
        price = float(quotes.get(symbol) or 0.0)
        if price <= 0:
            try:
                price = float(provider.get_latest_price(symbol) or 0.0)
            except Exception:  # noqa: BLE001
                price = 0.0
        if price <= 0:
            errors.append({"symbol": symbol, "reason": "no price available"})
            continue

        # Protective exits live outside the signal path: a stop that only
        # fires when the ensemble flips is not a stop.
        exit_leg = _protective_exit(broker, symbol, price)

        try:
            pipeline = LokiAgentPipeline(cfg, broker=broker)
            trail = pipeline.run_symbol(
                symbol,
                broker.equity(quotes),
                len(broker.positions),
                price,
                execute=True,
            )
        except Exception as exc:  # noqa: BLE001 - one symbol must not abort the session
            errors.append({"symbol": symbol, "reason": f"pipeline failed: {exc}"})
            continue

        execution = next((leg for leg in trail if leg.get("agent") == "execution"), {})
        decision = next((leg for leg in trail if leg.get("agent") == "quant"), {})
        director = next((leg for leg in trail if leg.get("agent") == "director"), {})
        risk = next((leg for leg in trail if leg.get("agent") == "risk"), {})

        decisions.append(
            {
                "symbol": symbol,
                "price": round(price, 6),
                "profile": source,
                "regime": director.get("regime"),
                "posture": director.get("posture"),
                "action": decision.get("action", "HOLD"),
                "score": decision.get("score"),
                "approved": risk.get("approved", False),
                # "ok" from the risk agent only means the order was allowed;
                # when nothing filled, the execution leg's reason (position
                # already open, unknown action) is the informative one.
                "reason": (
                    risk.get("reason") or execution.get("reason")
                    if execution.get("executed")
                    else execution.get("reason") or risk.get("reason")
                ),
                "executed": bool(execution.get("executed")),
                "protective_exit": exit_leg,
            }
        )

        for leg in (exit_leg, _fill_from_execution(execution, symbol, price)):
            if leg:
                leg["profile"] = source
                fills.append(leg)

    if write_ledger and fills:
        _write_step_session({
            "session_id": datetime.now().strftime("%Y%m%dT%H%M%S"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "book_generated_at": book.get("generated_at"),
            "capital": capital,
            "decisions": decisions,
            "fills": fills,
            "errors": errors,
        })

    broker.save_state(quotes)
    equity = broker.equity(quotes)

    mirrored = _mirror_fills(fills) if mirror else []
    return {
        "mode": "step",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "capital": round(capital, 2),
        "cash": round(broker.cash, 2),
        "equity": round(equity, 2),
        "open_positions": {
            sym: {
                "qty": round(pos.qty, 8),
                "avg_entry": round(pos.avg_entry, 6),
                "stop_loss": round(pos.stop_loss, 6),
                "take_profit": round(pos.take_profit, 6),
            }
            for sym, pos in broker.positions.items()
        },
        "decisions": decisions,
        "fills": fills,
        "alpaca_mirror": mirrored,
        "errors": errors,
        "state_file": str(broker.state_file),
    }


def _protective_exit(broker, symbol: str, price: float) -> Optional[Dict[str, Any]]:
    """Close a position that has crossed its own stop or target."""
    pos = broker.positions.get(symbol)
    if not pos or pos.qty <= 0:
        return None
    hit = None
    if pos.stop_loss and price <= pos.stop_loss:
        hit = "stop"
    elif pos.take_profit and price >= pos.take_profit:
        hit = "target"
    if not hit:
        return None
    qty = float(pos.qty)
    entry = float(pos.avg_entry)
    if not broker.close(symbol, price):
        return None
    return {
        "symbol": symbol,
        "side": "sell",
        "qty": round(qty, 8),
        "price": round(price, 6),
        "reason": hit,
        "realized_pnl": round((price - entry) * qty, 2),
        "stamp": datetime.now().isoformat(timespec="seconds"),
    }


def _fill_from_execution(
    execution: Dict[str, Any], symbol: str, price: float
) -> Optional[Dict[str, Any]]:
    if not execution.get("executed"):
        return None
    action = execution.get("action")
    return {
        "symbol": symbol,
        "side": "buy" if action == "BUY" else "sell",
        "qty": round(float(execution.get("qty") or 0.0), 8),
        "price": round(price, 6),
        "reason": "signal",
        "realized_pnl": None,
        "stamp": datetime.now().isoformat(timespec="seconds"),
    }


def _write_step_session(payload: Dict[str, Any]) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSION_DIR / f"step_{payload['session_id']}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        for fill in payload["fills"]:
            handle.write(
                json.dumps(
                    {
                        "session_id": payload["session_id"],
                        "mode": "step",
                        "recorded_at": payload["generated_at"],
                        **fill,
                    },
                    default=str,
                )
                + "\n"
            )


# ---------------------------------------------------------------------------
# Alpaca paper mirror
# ---------------------------------------------------------------------------
def alpaca_symbol(symbol: str) -> str:
    """BTC-USD -> BTC/USD (Alpaca's crypto notation)."""
    return symbol.upper().replace("-", "/")


def _fmt_qty(qty: float) -> str:
    text = f"{max(0.0, qty):.9f}".rstrip("0").rstrip(".")
    return text or "0"


def mirror_order(
    symbol: str,
    side: str,
    qty: float,
    key_id: str,
    secret: str,
    *,
    base: str = ALPACA_PAPER_BASE,
    timeout: float = 20.0,
) -> Tuple[bool, Dict[str, Any]]:
    """Place one market order on Alpaca's PAPER endpoint. Fails closed."""
    if side not in ("buy", "sell"):
        return False, {"error": f"unsupported side {side!r}"}
    if qty <= 0:
        return False, {"error": "qty must be positive"}
    payload = {
        "symbol": alpaca_symbol(symbol),
        "qty": _fmt_qty(qty),
        "side": side,
        "type": "market",
        "time_in_force": "gtc",
    }
    request = urllib.request.Request(
        f"{base}/v2/orders",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8") or "{}"
            parsed = json.loads(body)
            return True, {"id": parsed.get("id"), "status": parsed.get("status"), "symbol": parsed.get("symbol")}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return False, {"status": exc.code, "error": detail}
    except Exception as exc:  # noqa: BLE001 - network is allowed to be down
        return False, {"error": f"{exc.__class__.__name__}: {exc}"}


def _mirror_fills(fills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    key_id = os.environ.get("ALPACA_PAPER_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_PAPER_API_SECRET", "").strip()
    if not fills:
        return []
    if not key_id or not secret:
        return [
            {
                "mirrored": False,
                "reason": "ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET not set",
                "fills": len(fills),
            }
        ]
    results = []
    for fill in fills:
        ok, detail = mirror_order(fill["symbol"], fill["side"], float(fill["qty"]), key_id, secret)
        results.append({"symbol": fill["symbol"], "side": fill["side"], "qty": fill["qty"], "mirrored": ok, "detail": detail})
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_replay(payload: Dict[str, Any]) -> None:
    summary = payload["portfolio"]
    print()
    print(f"CRYPTO PAPER SESSION  {payload['session_id']}   (replay, {payload['bars']} bars @ {payload['timeframe']})")
    print(f"book trained at       {payload.get('book_generated_at')}    slippage {payload['slippage_bps']} bps/side")
    print()
    header = f"{'symbol':>10} {'profile':<15} {'preset':<17} {'tr':>4} {'ret%':>8} {'win%':>6} {'pf':>6} {'dd%':>7}"
    print(header)
    print("-" * len(header))
    for row in payload["symbols"]:
        print(
            f"{row['symbol']:>10} {row['profile']:<15} {str(row['preset'])[:17]:<17} "
            f"{row['trades']:>4} {row['return_pct']:>8.2f} {row['win_rate_pct']:>6.1f} "
            f"{str(row['profit_factor']):>6} {row['max_drawdown_pct']:>7.2f}"
        )

    if payload["trades"]:
        print()
        print(f"BLOTTER ({len(payload['trades'])} simulated fills)")
        head = f"{'exit':<20} {'symbol':>10} {'side':<5} {'qty':>12} {'entry':>12} {'exit':>12} {'pnl':>10} {'%':>7} {'why':<8}"
        print(head)
        print("-" * len(head))
        for t in payload["trades"]:
            print(
                f"{t['exit_time'][:19]:<20} {t['symbol']:>10} {t['side']:<5} {t['qty']:>12.6f} "
                f"{t['entry_price']:>12.4f} {t['exit_price']:>12.4f} {t['pnl']:>10.2f} "
                f"{t['pnl_pct']:>7.2f} {t['exit_reason']:<8}"
            )

    print()
    print("PORTFOLIO")
    print(f"  start equity   ${summary['equity_start']:,.2f}")
    print(f"  end equity     ${summary['equity_end']:,.2f}")
    print(f"  net P&L        ${summary['pnl']:,.2f}  ({summary['return_pct']:+.2f}%)")
    print(f"  trades         {summary['trades']}  ({summary['wins']}W / {summary['losses']}L, {summary['win_rate_pct']}%)")
    print(f"  profit factor  {summary['profit_factor']}")
    print(f"  expectancy     ${summary['expectancy']:,.2f} per fill")
    print(f"  max drawdown   {summary['max_drawdown_pct']:.2f}%")
    if payload.get("session_file"):
        print(f"  session file   {payload['session_file']}")
    if payload["skipped"]:
        print()
        for row in payload["skipped"]:
            print(f"  skipped {row['symbol']}: {row['reason']}")
    print()
    print("simulated fills at historical prices; no order was sent.")


def print_step(payload: Dict[str, Any]) -> None:
    print()
    print(f"CRYPTO PAPER STEP  {payload['generated_at']}")
    print(f"cash ${payload['cash']:,.2f}   equity ${payload['equity']:,.2f}   positions {len(payload['open_positions'])}")
    print()
    head = f"{'symbol':>10} {'regime':<14} {'posture':<7} {'action':<6} {'score':>6} {'approved':>8}  reason"
    print(head)
    print("-" * (len(head) + 14))
    for d in payload["decisions"]:
        print(
            f"{d['symbol']:>10} {str(d['regime'])[:14]:<14} {str(d['posture']):<7} {str(d['action']):<6} "
            f"{str(d['score']):>6} {str(d['approved']):>8}  {d['reason'] or ''}"
        )
    if payload["fills"]:
        print()
        print("FILLS")
        for fill in payload["fills"]:
            pnl = fill.get("realized_pnl")
            tail = f"  pnl ${pnl:,.2f}" if pnl not in (None, "") else ""
            print(f"  {fill['side'].upper():<4} {fill['symbol']:>10} {fill['qty']:.8f} @ ${fill['price']:,.4f}  ({fill['reason']}){tail}")
    else:
        print("\nno fills this step.")
    if payload["alpaca_mirror"]:
        print()
        print("ALPACA PAPER MIRROR")
        for row in payload["alpaca_mirror"]:
            print(f"  {row}")
    for err in payload["errors"]:
        print(f"  error {err['symbol']}: {err['reason']}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Simulated crypto paper session on the trained Loki book.")
    parser.add_argument("--mode", choices=("replay", "step"), default="replay")
    parser.add_argument("--symbols", default="", help="comma-separated; default is the crypto universe")
    parser.add_argument("--bars", type=int, default=180, help="tradeable bars in the replay window (default 180)")
    parser.add_argument("--capital", type=float, default=100_000.0, help="session capital, split evenly across symbols")
    parser.add_argument("--period", default="3y", help="history window for indicators (default 3y)")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--mirror", action="store_true", help="step mode only: forward fills to Alpaca PAPER")
    parser.add_argument("--no-ledger", action="store_true", help="do not write session files")
    parser.add_argument("--json", action="store_true", help="print the raw session JSON instead of tables")
    args = parser.parse_args(argv)

    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip()) or DEFAULT_UNIVERSE

    if args.mode == "replay":
        if args.mirror:
            print("--mirror applies to --mode step only: Alpaca fills at live prices, so a historical replay cannot be mirrored.")
        payload = replay(
            symbols,
            bars=args.bars,
            capital=args.capital,
            period=args.period,
            timeframe=args.timeframe,
            slippage_bps=args.slippage_bps,
            write_ledger=not args.no_ledger,
        )
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print_replay(payload)
    else:
        payload = step(
            symbols,
            capital=args.capital,
            period=args.period,
            mirror=args.mirror,
            write_ledger=not args.no_ledger,
        )
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print_step(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
