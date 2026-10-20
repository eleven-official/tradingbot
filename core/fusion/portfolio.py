"""Client-owned paper ledger shared by Loki's research and review workflows.

These functions transform supplied simulation state; they do not store accounts,
connect a broker, or submit real orders. Every price must use one quote currency.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
import re
from typing import Any, Mapping
from uuid import uuid4


def _number(value, name, minimum=0.0, maximum=1e12, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
        or value > maximum
        or (positive and value == 0)
    ):
        raise ValueError(
            f"{name} must be a finite number {'above' if positive else 'at least'} {minimum:g} and at most {maximum:g}"
        )
    return float(value)


def _symbol(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/^:-]{0,31}", value):
        raise ValueError(
            "Use an instrument identifier of 1–32 letters, numbers, or market separators"
        )
    return value.upper()


def new_portfolio(initial_capital=10000.0, fee_bps=10.0, slippage_bps=5.0, quote_currency="USD"):
    capital = _number(initial_capital, "initial_capital", positive=True)
    fee = _number(fee_bps, "fee_bps", maximum=1000)
    slip = _number(slippage_bps, "slippage_bps", maximum=1000)
    if not isinstance(quote_currency, str) or not re.fullmatch(r"[A-Z0-9]{2,12}", quote_currency):
        raise ValueError("Use an explicit quote currency such as USD or USDT")
    return {
        "schema_version": 1,
        "mode": "paper_only",
        "initial_capital": capital,
        "cash": capital,
        "fee_bps": fee,
        "slippage_bps": slip,
        "quote_currency": quote_currency,
        "positions": {},
        "trades": [],
        "revision": 0,
    }


def _reconcile_ledger(state):
    """Reject internally impossible imported balances and lifecycle statistics.

    A client can supply a wholly invented, self-consistent paper history. This
    check establishes accounting consistency, never broker authenticity or
    measured market performance. Marks and stop annotations remain user inputs.
    """
    positions = state["positions"]
    market_value = sum(row["quantity"] * row["mark_price"] for row in positions.values())
    if not math.isfinite(market_value) or state["cash"] + market_value > 1e12:
        raise ValueError("Portfolio valuation exceeds the paper ledger's numeric range")

    def same(actual, expected, name):
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError(f"Paper ledger {name} does not reconcile with its recorded fills")

    inventory, cash, identifiers = {}, state["initial_capital"], set()
    fee_rate, slippage = state["fee_bps"] / 10000, state["slippage_bps"] / 10000
    for trade in state["trades"]:
        symbol, side = trade["symbol"], trade["side"]
        if _symbol(symbol) != symbol or (
            "/" in symbol and symbol.rsplit("/", 1)[1] != state["quote_currency"]
        ):
            raise ValueError("Paper fill symbol or quote currency is inconsistent")
        identifier = trade.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Paper fills require unique identifiers")
        identifiers.add(identifier)
        if trade.get("mode") != "paper_only":
            raise ValueError("Imported paper fills must retain their paper-only identity")
        quantity, price, fees = trade["quantity"], trade["price"], trade["fees"]
        notional = quantity * price
        if not math.isfinite(notional) or notional > 1e12:
            raise ValueError("Paper fill notional exceeds the ledger's numeric range")
        same(fees, notional * fee_rate, "fill fees")
        reference = _number(trade.get("reference_price"), "fill reference price", positive=True)
        same(price, reference * (1 + slippage if side == "BUY" else 1 - slippage), "fill slippage")
        current = inventory.get(symbol)
        if side == "BUY":
            if any(key in trade for key in ("pnl", "completed_pnl", "position_closed")):
                raise ValueError(
                    "A BUY fill cannot claim a completed position lifecycle or realized profit"
                )
            outlay = notional + fees
            if outlay > cash + max(1e-8, cash * 1e-12):
                raise ValueError("Paper fill history spends more cash than the account held")
            cash = max(0.0, cash - outlay)
            if current is None:
                inventory[symbol] = {
                    "quantity": quantity,
                    "average_price": price,
                    "entry_fees": fees,
                    "realized_pnl": 0.0,
                }
            else:
                combined = current["quantity"] + quantity
                current["average_price"] = (
                    current["average_price"] * current["quantity"] + notional
                ) / combined
                current["quantity"] = combined
                current["entry_fees"] += fees
            continue
        if current is None or quantity > current["quantity"] * (1 + 1e-12):
            raise ValueError("Paper SELL fill history exceeds the held long quantity")
        entry_fees = current["entry_fees"] * quantity / current["quantity"]
        pnl = quantity * (price - current["average_price"]) - fees - entry_fees
        same(
            _number(trade.get("pnl"), "SELL realized P&L", minimum=-1e12), pnl, "SELL realized P&L"
        )
        cash += notional - fees
        remaining = current["quantity"] - quantity
        closed = remaining <= current["quantity"] * 1e-12
        if type(trade.get("position_closed")) is not bool or trade["position_closed"] != closed:
            raise ValueError("Paper fill lifecycle closure disagrees with the remaining quantity")
        if closed:
            same(trade["completed_pnl"], current["realized_pnl"] + pnl, "completed lifecycle P&L")
            del inventory[symbol]
        else:
            if "completed_pnl" in trade:
                raise ValueError("A partial exit cannot claim completed lifecycle P&L")
            current.update(
                quantity=remaining,
                entry_fees=current["entry_fees"] - entry_fees,
                realized_pnl=current["realized_pnl"] + pnl,
            )
    same(state["cash"], cash, "cash balance")
    if inventory.keys() != positions.keys():
        raise ValueError("Paper open positions do not reconcile with recorded fills")
    for symbol, expected in inventory.items():
        for key, value in expected.items():
            same(positions[symbol].get(key, 0.0), value, f"{symbol} {key}")


def validate_portfolio(state: Mapping[str, Any] | None):
    if state is None:
        return new_portfolio()
    if (
        not isinstance(state, Mapping)
        or type(state.get("schema_version")) is not int
        or state.get("schema_version") != 1
        or state.get("mode") != "paper_only"
    ):
        raise ValueError("Unsupported paper portfolio format")
    result = deepcopy(dict(state))
    for name in ("initial_capital", "cash", "fee_bps", "slippage_bps"):
        _number(
            result.get(name),
            name,
            maximum=1000 if name.endswith("bps") else 1e12,
            positive=name == "initial_capital",
        )
    if not isinstance(result.get("quote_currency"), str) or not re.fullmatch(
        r"[A-Z0-9]{2,12}", result["quote_currency"]
    ):
        raise ValueError("A paper quote currency is required")
    positions, trades = result.get("positions"), result.get("trades")
    if not isinstance(positions, dict) or len(positions) > 100:
        raise ValueError("A paper account supports up to 100 instruments")
    if not isinstance(trades, list) or len(trades) > 2000:
        raise ValueError("Export this paper account before exceeding 2,000 fills")
    for symbol, position in positions.items():
        if _symbol(symbol) != symbol or not isinstance(position, dict):
            raise ValueError("Invalid paper position")
        if "/" in symbol and symbol.rsplit("/", 1)[1] != result["quote_currency"]:
            raise ValueError(
                "Instrument and paper account quote currencies must match; no FX conversion is available"
            )
        for name in ("quantity", "average_price", "mark_price", "entry_fees"):
            _number(position.get(name), name, positive=name != "entry_fees")
        _number(position.get("realized_pnl", 0), "realized_pnl", minimum=-1e12)
        if position.get("stop_loss") is not None:
            _number(position["stop_loss"], "stop_loss", positive=True)
    for trade in trades:
        if not isinstance(trade, dict) or trade.get("side") not in {"BUY", "SELL"}:
            raise ValueError("Invalid paper fill history")
        _symbol(trade.get("symbol"))
        for name in ("quantity", "price", "fees"):
            _number(trade.get(name), name, positive=name != "fees")
        for name in ("pnl", "completed_pnl"):
            if trade.get(name) is not None:
                _number(trade[name], name, minimum=-1e12)
        if trade.get("position_closed") is True and trade.get("completed_pnl") is None:
            raise ValueError("A completed paper position needs its realized lifecycle P&L")
    revision = result.get("revision", 0)
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or not 0 <= revision <= 1_000_000
    ):
        raise ValueError("Invalid paper account revision")
    if revision < len(trades):
        raise ValueError("Paper account revision is older than its recorded fills")
    _reconcile_ledger(result)
    return result


def portfolio_metrics(state):
    state = validate_portfolio(state)
    cash, positions = state["cash"], state["positions"]
    value = sum(p["quantity"] * p["mark_price"] for p in positions.values())
    equity = cash + value
    if not math.isfinite(equity) or equity > 1e12:
        raise ValueError("Portfolio valuation exceeds the paper ledger's numeric range")
    completed = [t["completed_pnl"] for t in state["trades"] if t.get("position_closed") is True]
    wins = [pnl for pnl in completed if pnl > 0]
    losses = [pnl for pnl in completed if pnl < 0]
    realized = sum(t.get("pnl", 0.0) for t in state["trades"] if t["side"] == "SELL")
    unrealized = sum(
        p["quantity"] * (p["mark_price"] - p["average_price"]) - p["entry_fees"]
        for p in positions.values()
    )
    return {
        "equity": equity,
        "cash": cash,
        "gross_exposure": value,
        "gross_exposure_pct": value / equity * 100 if equity > 0 else None,
        "total_pnl": equity - state["initial_capital"],
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "total_return_pct": (equity / state["initial_capital"] - 1) * 100,
        "open_positions": len(positions),
        "closed_trades": len(completed),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(completed) * 100 if completed else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "expectancy": sum(completed) / len(completed) if completed else None,
        "quote_currency": state["quote_currency"],
        "mode": "paper_only",
    }


def apply_portfolio_action(payload: Mapping[str, Any]):
    """Apply one explicit simulated action and return a new state, never a broker order."""
    if not isinstance(payload, Mapping):
        raise ValueError("Paper action must be a mapping")
    action = payload.get("action", "snapshot")
    if action not in {"snapshot", "buy", "sell", "mark", "reset"}:
        raise ValueError("Choose snapshot, buy, sell, mark, or reset")
    state = validate_portfolio(payload.get("state"))
    last_action = {"action": action, "mode": "paper_only"}
    if action == "reset":
        state = new_portfolio(
            payload.get("initial_capital", state["initial_capital"]),
            payload.get("fee_bps", state["fee_bps"]),
            payload.get("slippage_bps", state["slippage_bps"]),
            payload.get("quote_currency", state["quote_currency"]),
        )
    elif action == "mark":
        marks = payload.get("marks", {})
        if not isinstance(marks, Mapping) or len(marks) > 100:
            raise ValueError("Provide up to 100 paper mark prices")
        for symbol, price in marks.items():
            symbol = _symbol(symbol)
            price = _number(price, "mark price", positive=True)
            if symbol not in state["positions"]:
                raise ValueError(f"No open paper position for {symbol} to mark")
            state["positions"][symbol]["mark_price"] = price
            state["positions"][symbol]["mark_updated_at"] = datetime.now(timezone.utc).isoformat()
            state["positions"][symbol]["mark_source"] = "manual mark"
        state["revision"] += 1
    elif action in {"buy", "sell"}:
        if len(state["trades"]) >= 2000:
            raise ValueError("Export the ledger and start a new paper account after 2,000 fills")
        symbol = _symbol(payload.get("symbol"))
        if "/" in symbol and symbol.rsplit("/", 1)[1] != state["quote_currency"]:
            raise ValueError(
                "Instrument and paper account quote currencies must match; reset an empty account to the correct currency"
            )
        reference = _number(payload.get("price"), "price", positive=True)
        quantity = _number(payload.get("quantity"), "quantity", positive=True)
        position = state["positions"].get(symbol)
        if action == "sell":
            if not position or quantity > position["quantity"] * (1 + 1e-12):
                raise ValueError("Paper sells cannot exceed the held long quantity")
            quantity = min(quantity, position["quantity"])
        fee, slip = state["fee_bps"] / 10000, state["slippage_bps"] / 10000
        price = reference * (1 + slip if action == "buy" else 1 - slip)
        notional = price * quantity
        if not math.isfinite(notional) or notional > 1e12:
            raise ValueError("Paper order notional is too large")
        fees = notional * fee
        trade = {
            "id": uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "side": action.upper(),
            "quantity": quantity,
            "price": price,
            "reference_price": reference,
            "fees": fees,
            "slippage": abs(price - reference) * quantity,
            "mode": "paper_only",
        }
        fingerprint = payload.get("report_fingerprint")
        if fingerprint is not None:
            if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                raise ValueError("Invalid research fingerprint")
            trade["report_fingerprint"] = fingerprint
        if action == "buy":
            outlay = notional + fees
            if outlay > state["cash"] + max(1e-8, state["cash"] * 1e-12):
                raise ValueError("The paper account has insufficient cash including entry costs")
            stop = payload.get("stop_loss")
            if stop is not None:
                stop = _number(stop, "stop_loss", positive=True)
                if stop >= reference:
                    raise ValueError("A long-position stop must be below the reference entry")
            if not position and len(state["positions"]) >= 100:
                raise ValueError("Maximum number of paper instruments reached")
            if position:
                total_quantity = position["quantity"] + quantity
                position["average_price"] = (
                    position["average_price"] * position["quantity"] + notional
                ) / total_quantity
                position["quantity"] = total_quantity
                position["entry_fees"] += fees
                position["mark_price"] = reference
                position["mark_updated_at"] = trade["timestamp"]
                position["mark_source"] = "entry fill"
                if stop is not None:
                    position["stop_loss"] = stop
            else:
                state["positions"][symbol] = {
                    "quantity": quantity,
                    "average_price": price,
                    "entry_fees": fees,
                    "mark_price": reference,
                    "stop_loss": stop,
                    "realized_pnl": 0.0,
                    "opened_at": trade["timestamp"],
                    "mark_updated_at": trade["timestamp"],
                    "mark_source": "entry fill",
                }
            state["cash"] = max(0.0, state["cash"] - outlay)
        else:
            if not position or quantity > position["quantity"] * (1 + 1e-12):
                raise ValueError("Paper sells cannot exceed the held long quantity")
            quantity = min(quantity, position["quantity"])
            entry_fees = position["entry_fees"] * quantity / position["quantity"]
            pnl = quantity * (price - position["average_price"]) - fees - entry_fees
            trade["pnl"] = pnl
            state["cash"] += notional - fees
            remaining = position["quantity"] - quantity
            trade["position_closed"] = remaining <= position["quantity"] * 1e-12
            if trade["position_closed"]:
                trade["completed_pnl"] = position.get("realized_pnl", 0.0) + pnl
                del state["positions"][symbol]
            else:
                position.update(
                    quantity=remaining,
                    entry_fees=position["entry_fees"] - entry_fees,
                    realized_pnl=position.get("realized_pnl", 0.0) + pnl,
                    mark_price=reference,
                )
        state["trades"].append(trade)
        state["revision"] += 1
        last_action = trade
    return {
        "state": state,
        "metrics": portfolio_metrics(state),
        "last_action": last_action,
        "assumptions": [
            "Client-maintained simulated account; no real orders or broker connection.",
            "All prices must use the account quote currency; no FX conversion is modeled.",
            "Fees and adverse slippage apply on entry and exit.",
            "Stops are annotations in this manual ledger, not automatic or guaranteed fills.",
            "Only fully closed position lifecycles count toward the win rate.",
        ],
    }


def stress_portfolio(state, shock_pct=-10.0, volatility_multiplier=1.0):
    state = validate_portfolio(state)
    shock = _number(shock_pct, "shock_pct", minimum=-99, maximum=500)
    multiplier = _number(volatility_multiplier, "volatility_multiplier", minimum=0.1, maximum=10)
    effective = shock * multiplier
    if effective <= -100 or effective > 1000:
        raise ValueError("Scaled hypothetical price shock must be above -100% and at most 1,000%")
    baseline = portfolio_metrics(state)["equity"]
    rows = []
    for symbol, position in state["positions"].items():
        price = position["mark_price"]
        stressed = price * (1 + effective / 100)
        rows.append(
            {
                "symbol": symbol,
                "current_price": price,
                "stressed_price": stressed,
                "quantity": position["quantity"],
                "pnl": (stressed - price) * position["quantity"],
            }
        )
    pnl = sum(row["pnl"] for row in rows)
    return {
        "mode": "hypothetical_stress",
        "baseline_equity": baseline,
        "stressed_equity": baseline + pnl,
        "pnl": pnl,
        "return_pct": pnl / baseline * 100 if baseline else None,
        "effective_shock_pct": effective,
        "volatility_multiplier": multiplier,
        "positions": rows,
        "quote_currency": state["quote_currency"],
        "assumptions": [
            "A user-selected parallel shock is multiplied by the stated stress factor.",
            "This is a numerical stress exercise, not a MiroFish simulation or a forecast.",
            "Cash is unchanged; liquidation costs, FX, market impact and correlations are not modeled.",
        ],
    }
