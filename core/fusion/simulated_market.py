"""Seeded synthetic exchange for practice, never market-performance evidence.

Prices are generated locally. This module has no market-data, provider, broker
or credential dependency. A separate cash-funded paper ledger models costs and
pending limits; stops take priority over intrabar profit limits. Client-owned
state is internally checked, not authenticated as a real trading record.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import random
from uuid import uuid4

from core.fusion.portfolio import (
    apply_portfolio_action,
    new_portfolio,
    validate_portfolio,
    portfolio_metrics,
)

ASSETS = {
    "BTC/USD": (68000.0, 0.0015, 500),
    "ETH/USD": (3500.0, 0.002, 8000),
    "SOL/USD": (145.0, 0.003, 80000),
}
SCENARIOS = {"balanced", "uptrend", "downtrend", "range", "volatile", "crash"}
WARMUP, MAX_STEPS, HALF_SPREAD = 120, 1440, 0.0004
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _positive(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 < value <= 1e9
    ):
        raise ValueError(f"{name} must be finite, positive and at most 1e9")
    return float(value)


def market_path(seed, scenario, steps):
    _integer(seed, "seed", 0, 2**31 - 1)
    _integer(steps, "step", 0, MAX_STEPS)
    if scenario not in SCENARIOS:
        raise ValueError("Choose balanced, uptrend, downtrend, range, volatile or crash")
    rng, history = random.Random(seed), {symbol: [] for symbol in ASSETS}
    prices = {symbol: params[0] for symbol, params in ASSETS.items()}
    for index in range(WARMUP + steps):
        common = rng.gauss(0, 1)
        for symbol, (anchor, vol, liquidity) in ASSETS.items():
            opening = prices[symbol]
            drift = 0.0003 if scenario == "uptrend" else -0.0003 if scenario == "downtrend" else 0
            if scenario == "range":
                drift += 0.02 * math.log(anchor / opening)
            volatility = vol * (2.5 if scenario == "volatile" else 1)
            movement = drift + volatility * (0.7 * common + 0.71414284285 * rng.gauss(0, 1))
            if scenario == "crash" and index == WARMUP + 40:
                movement -= 0.12
            elif scenario == "crash" and WARMUP + 40 < index < WARMUP + 140:
                movement += 0.0005
            close = opening * math.exp(max(-0.2, min(0.2, movement)))
            wick = abs(rng.gauss(0, volatility / 2))
            high, low = max(opening, close) * (1 + wick), min(opening, close) / (1 + wick)
            history[symbol].append(
                {
                    "timestamp": (START + timedelta(minutes=index)).isoformat(),
                    "open": opening,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": rng.lognormvariate(math.log(liquidity), 0.4),
                }
            )
            prices[symbol] = close
    return history


def new_session(seed=42, scenario="balanced", initial_capital=10000.0):
    market_path(seed, scenario, 0)
    return {
        "schema_version": 1,
        "mode": "synthetic_market_only",
        "seed": seed,
        "scenario": scenario,
        "step": 0,
        "account": new_portfolio(initial_capital),
        "orders": [],
        "events": [],
        "equity_curve": [],
        "revision": 0,
    }


def validate_session(value):
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("mode") != "synthetic_market_only"
    ):
        raise ValueError("Use a version-one synthetic practice session")
    state = deepcopy(value)
    _integer(state.get("seed"), "seed", 0, 2**31 - 1)
    _integer(state.get("step"), "step", 0, MAX_STEPS)
    _integer(state.get("revision"), "revision", 0, 1_000_000)
    if state.get("scenario") not in SCENARIOS:
        raise ValueError("Invalid synthetic scenario")
    if not isinstance(state.get("account"), dict):
        raise ValueError("A practice session requires its explicit account ledger")
    state["account"] = validate_portfolio(state["account"])
    if state["account"]["fee_bps"] != 10 or state["account"]["slippage_bps"] != 5:
        raise ValueError(
            "Practice account costs must remain 10 bps fee and 5 bps slippage per side"
        )
    if state["account"]["quote_currency"] != "USD" or any(
        symbol not in ASSETS for symbol in state["account"]["positions"]
    ):
        raise ValueError("Synthetic practice supports BTC/USD, ETH/USD and SOL/USD in USD")
    for name, maximum in (("orders", 100), ("events", 100), ("equity_curve", MAX_STEPS + 1)):
        if not isinstance(state.get(name), list) or len(state[name]) > maximum:
            raise ValueError(f"Practice {name} exceeds its history limit")
    identifiers = set()
    for order in state["orders"]:
        if (
            not isinstance(order, dict)
            or order.get("symbol") not in ASSETS
            or order.get("side") not in {"buy", "sell"}
            or order.get("type") != "limit"
            or order.get("status") not in {"pending", "filled", "cancelled", "rejected", "expired"}
            or not isinstance(order.get("id"), str)
            or len(order["id"]) != 32
            or order["id"] in identifiers
        ):
            raise ValueError("Invalid synthetic limit order")
        identifiers.add(order["id"])
        _positive(order.get("quantity"), "order quantity")
        _positive(order.get("limit_price"), "limit price")
        _integer(order.get("created_step"), "order creation step", 0, state["step"])
        _integer(
            order.get("expires_step"),
            "order expiry step",
            order["created_step"] + 1,
            MAX_STEPS + 480,
        )
        if order.get("stop_loss") is not None:
            _positive(order["stop_loss"], "order stop")
    for point in state["equity_curve"]:
        if not isinstance(point, dict):
            raise ValueError("Invalid practice equity point")
        _positive(point.get("equity"), "practice equity")
        _integer(point.get("step"), "equity step", 0, state["step"])
    # Events are labels only; cap strings so an imported journal stays bounded.
    if any(
        not isinstance(event, dict)
        or not isinstance(event.get("message"), str)
        or len(event["message"]) > 400
        for event in state["events"]
    ):
        raise ValueError("Invalid practice event")
    return state


def _event(state, text):
    state["events"].append({"step": state["step"], "message": text[:400]})
    state["events"] = state["events"][-100:]


def _fill(state, symbol, side, quantity, reference, timestamp, stop_loss=None):
    result = apply_portfolio_action(
        {
            "state": state["account"],
            "action": side,
            "symbol": symbol,
            "quantity": quantity,
            "price": reference,
            "stop_loss": stop_loss,
        }
    )
    state["account"] = result["state"]
    trade = state["account"]["trades"][-1]
    trade["simulation_timestamp"] = timestamp
    trade["simulation_step"] = state["step"]
    trade["data_kind"] = "synthetic"
    _event(
        state,
        f"{side.upper()} {quantity:.6g} {symbol} filled at {trade['price']:.6f}; fee {trade['fees']:.4f} USD.",
    )


def _advance_one(state, history):
    state["step"] += 1
    index = WARMUP + state["step"] - 1
    account = state["account"]
    # A stop is already resting before this candle. It wins over all profit
    # limits when OHLC cannot reveal intrabar event order; gaps fill worse.
    for symbol, position in list(account["positions"].items()):
        bar = history[symbol][index]
        stop = position.get("stop_loss")
        if stop is not None and bar["low"] * (1 - HALF_SPREAD) <= stop:
            reference = min(bar["open"] * (1 - HALF_SPREAD), stop)
            _fill(state, symbol, "sell", position["quantity"], reference, bar["timestamp"])
            _event(state, f"Protective stop triggered for {symbol}; adverse gaps and costs apply.")
    for order in state["orders"]:
        if order["status"] != "pending":
            continue
        if state["step"] > order["expires_step"]:
            order["status"] = "expired"
            continue
        symbol, side, limit = order["symbol"], order["side"], order["limit_price"]
        bar, previous = history[symbol][index], history[symbol][index - 1]
        slip = state["account"]["slippage_bps"] / 10000
        factor = (1 + HALF_SPREAD) * (1 + slip) if side == "buy" else (1 - HALF_SPREAD) * (1 - slip)
        touched = bar["low"] * factor <= limit if side == "buy" else bar["high"] * factor >= limit
        if not touched:
            continue
        desired = (
            min(bar["open"] * factor, limit) if side == "buy" else max(bar["open"] * factor, limit)
        )
        reference = desired / (1 + slip if side == "buy" else 1 - slip)
        try:
            if order["quantity"] > previous["volume"] * 0.005:
                raise ValueError("Order exceeds the simplified prior-volume liquidity cap")
            _fill(
                state,
                symbol,
                side,
                order["quantity"],
                reference,
                bar["timestamp"],
                order.get("stop_loss"),
            )
            order.update(status="filled", filled_step=state["step"])
            # A newly attached stop may be touched in this same candle. Choose
            # the adverse feasible outcome rather than invent an event order.
            position = state["account"]["positions"].get(symbol)
            stop = position.get("stop_loss") if position else None
            if side == "buy" and stop is not None and bar["low"] * (1 - HALF_SPREAD) <= stop:
                _fill(
                    state,
                    symbol,
                    "sell",
                    position["quantity"],
                    min(bar["open"] * (1 - HALF_SPREAD), stop),
                    bar["timestamp"],
                )
        except ValueError as exc:
            order.update(status="rejected", reason=str(exc))
            _event(state, f"Limit {order['id'][:8]} rejected: {exc}")
    marks = {symbol: rows[index]["close"] for symbol, rows in history.items()}
    state["account"] = apply_portfolio_action(
        {"state": state["account"], "action": "mark", "marks": marks}
    )["state"]
    state["equity_curve"].append(
        {"step": state["step"], "equity": portfolio_metrics(state["account"])["equity"]}
    )
    if state["scenario"] == "crash" and state["step"] == 41:
        _event(state, "Synthetic flash-crash shock: all three generated markets dropped together.")


def snapshot(state, history=None):
    history = history or market_path(state["seed"], state["scenario"], state["step"])
    for symbol, position in state["account"]["positions"].items():
        position["mark_price"] = history[symbol][-1]["close"]
    quotes = []
    for symbol, rows in history.items():
        price, previous = rows[-1]["close"], rows[-2]["close"]
        quotes.append(
            {
                "symbol": symbol,
                "price": price,
                "change": price / previous - 1,
                "bid": price * (1 - HALF_SPREAD),
                "ask": price * (1 + HALF_SPREAD),
                "volume": rows[-1]["volume"],
                "timestamp": rows[-1]["timestamp"],
            }
        )
    return {
        "state": state,
        "quotes": quotes,
        "bars": {symbol: rows[-180:] for symbol, rows in history.items()},
        "metrics": portfolio_metrics(state["account"]),
        "mode": "synthetic_market_only",
        "remaining_steps": MAX_STEPS - state["step"],
        "synthetic": True,
        "performance_evidence_eligible": False,
        "live_trading_enabled": False,
        "assumptions": [
            "All prices, candles, volume and depth displays are synthetic, generated locally from a seed.",
            "Separate long-only practice cash account; no broker or real-market data is connected.",
            "Market buys use ask, sells use bid; fees and adverse slippage apply on both sides.",
            "Limits can fill only on a later candle, honor their price, and expire after 480 steps. Costs may still make a round trip lose money.",
            "Resting protective stops take priority over profit limits on ambiguous candles. Stop gaps can increase losses.",
            "Simplified liquidity caps each order to 0.5% of preceding synthetic volume; queue priority and partial fills are not modeled. Pending orders do not reserve cash or inventory and can be rejected when touched.",
            "Practice results, council opinions and synthetic wins cannot establish real-market profitability or the 70% trading-win target.",
            "Session state is stored in this browser; imported paper history is not authenticated. Export it before reset.",
        ],
    }


def act(payload):
    if not isinstance(payload, dict):
        raise ValueError("Supply a synthetic practice action")
    action = payload.get("action", "snapshot")
    if action not in {"create", "snapshot", "advance", "order", "cancel", "council"}:
        raise ValueError("Unknown simulated-market action")
    if action == "create":
        return snapshot(
            new_session(
                payload.get("seed", 42),
                payload.get("scenario", "balanced"),
                payload.get("initial_capital", 10000.0),
            )
        )
    state = validate_session(payload.get("state"))
    symbol = payload.get("symbol", "BTC/USD")
    if symbol not in ASSETS:
        raise ValueError("Choose BTC/USD, ETH/USD or SOL/USD")
    if action == "advance":
        count = _integer(payload.get("steps", 1), "steps", 1, 30)
        if state["step"] + count > MAX_STEPS:
            raise ValueError("The practice session is complete; export and start a new session")
        history = market_path(state["seed"], state["scenario"], state["step"] + count)
        for _ in range(count):
            _advance_one(state, history)
    else:
        history = market_path(state["seed"], state["scenario"], state["step"])
        bar = history[symbol][-1]
        if action == "order":
            side, kind = payload.get("side"), payload.get("order_type", "market")
            if side not in {"buy", "sell"} or kind not in {"market", "limit"}:
                raise ValueError("Choose buy/sell and market/limit")
            quantity = _positive(payload.get("quantity"), "quantity")
            stop = payload.get("stop_loss") if side == "buy" else None
            reference = bar["close"] * (1 + HALF_SPREAD if side == "buy" else 1 - HALF_SPREAD)
            if stop is not None:
                stop = _positive(stop, "protective stop")
                if stop >= reference:
                    raise ValueError("A protective long stop must be below the current ask")
            if kind == "market":
                if quantity > bar["volume"] * 0.005:
                    raise ValueError("Order exceeds the simplified synthetic liquidity cap")
                _fill(state, symbol, side, quantity, reference, bar["timestamp"], stop)
            else:
                limit = _positive(payload.get("limit_price"), "limit price")
                if stop is not None and stop >= limit / (
                    1 + state["account"]["slippage_bps"] / 10000
                ):
                    raise ValueError("Protective stop must also be below the buy limit reference")
                if sum(order["status"] == "pending" for order in state["orders"]) >= 20:
                    raise ValueError("Cancel pending orders before adding more than 20")
                state["orders"] = [
                    order for order in state["orders"] if order["status"] == "pending"
                ] + [order for order in state["orders"] if order["status"] != "pending"][-79:]
                state["orders"].append(
                    {
                        "id": uuid4().hex,
                        "symbol": symbol,
                        "side": side,
                        "type": "limit",
                        "quantity": quantity,
                        "limit_price": limit,
                        "stop_loss": stop,
                        "created_step": state["step"],
                        "expires_step": state["step"] + 480,
                        "status": "pending",
                    }
                )
                _event(
                    state,
                    f"{side.upper()} limit queued for {symbol} at {limit:.6f}; eligible from the next candle.",
                )
        elif action == "cancel":
            order = next(
                (
                    order
                    for order in state["orders"]
                    if order["id"] == payload.get("order_id") and order["status"] == "pending"
                ),
                None,
            )
            if order is None:
                raise ValueError("No pending limit order has that ID")
            order["status"] = "cancelled"
            _event(state, f"Limit {order['id'][:8]} cancelled.")
        elif action == "council":
            from core.fusion.council import build_council_report

            report = build_council_report(
                history[symbol],
                symbol=symbol,
                portfolio=state["account"],
                config={"periods_per_year": 525600},
            )
            report.update(synthetic=True, performance_evidence_eligible=False)
            report["limitations"].insert(
                0,
                "This review uses generated synthetic prices and is practice feedback, not historical market evidence.",
            )
            result = snapshot(state, history)
            result["council"] = report
            return result
    state["revision"] += action != "snapshot"
    return snapshot(state, history)
