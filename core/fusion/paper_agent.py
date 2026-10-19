"""Explicitly started, browser-heartbeat AI trader; fixed Alpaca PAPER transport.

One model/account, cash-funded whole units, persistent claims and actual fills.
No synthetic balance, chat content, or client-supplied model drives these orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import threading
import time
from urllib.parse import quote
import uuid

from core.fusion.broker_link import AlpacaClient, BrokerUnavailable, finite, refresh_account
from core.fusion.learning import predict
from core.fusion.paper_models import database, load_model, feature_vector
from core.strategy_lab import validate_bars

_locks, _guard = {}, threading.Lock()
TERMINAL = {"filled", "canceled", "expired", "rejected"}
ORDER_STATES = TERMINAL | {
    "new",
    "accepted",
    "pending_new",
    "partially_filled",
    "done_for_day",
    "pending_cancel",
    "pending_replace",
    "accepted_for_bidding",
    "stopped",
    "suspended",
    "calculated",
}


def _lock(scope):
    with _guard:
        return _locks.setdefault(scope, threading.RLock())


def _owner(identifier):
    return hashlib.sha256(identifier.encode()).hexdigest()


def _paper(profile):
    if profile.provider != "alpaca" or profile.mode != "paper":
        raise ValueError(
            "AI automation requires a verified Alpaca PAPER connection. Live accounts cannot use this runner."
        )
    if profile.expires <= time.time():
        raise ValueError("Broker connection expired")


def _read(db, profile):
    row = db.execute("SELECT owner,state FROM agents WHERE scope=?", (profile.scope,)).fetchone()
    if not row:
        return None, None
    return row["owner"], json.loads(row["state"])


def _save(db, profile, owner, state):
    db.execute(
        "INSERT OR REPLACE INTO agents VALUES(?,?,?)", (profile.scope, owner, json.dumps(state))
    )


def status(profile, identifier):
    _paper(profile)
    with _lock(profile.scope), database() as db:
        owner, state = _read(db, profile)
        if state and state["running"] and state["active_until"] < time.time():
            state.update(
                running=False,
                message="Paper AI paused because its browser heartbeat expired. Venue orders and holdings remain.",
            )
            _save(db, profile, owner, state)
        if not state:
            return {
                "running": False,
                "message": "Train an instrument model, then explicitly start the paper AI.",
                "paper_only": True,
                "journal": [],
            }
        result = dict(
            state, controlled_by_this_session=owner == _owner(identifier), paper_only=True
        )
        rows = db.execute(
            "SELECT id,created,state,body,response FROM paper_actions WHERE scope=? ORDER BY created DESC LIMIT 30",
            (profile.scope,),
        ).fetchall()
        result["journal"] = [
            {
                "id": r["id"],
                "created_at": r["created"],
                "state": r["state"],
                "request": json.loads(r["body"]),
                "order": json.loads(r["response"]) if r["response"] else None,
            }
            for r in rows
        ]
        return result


def start(profile, identifier, model_id, max_notional=1000.0):
    _paper(profile)
    if not 1 <= finite(max_notional) <= 1000:
        raise ValueError("Paper order budget must be 1–1000 USD")
    report = load_model(profile.scope, model_id)
    if "/" in report["symbol"]:
        raise ValueError(
            "The Alpaca AI runner currently supports US equities; crypto models remain local research"
        )
    client = AlpacaClient(profile)
    with _lock(profile.scope), database() as db:
        owner, previous = _read(db, profile)
        if previous:
            if previous.get("pending") or previous.get("owned_qty", 0) > 0:
                if previous["model_id"] != model_id or (
                    owner != _owner(identifier)
                    and previous["running"]
                    and previous["active_until"] > time.time()
                ):
                    raise ValueError(
                        "Resolve the existing paper runner's orders/holdings before changing its model or session"
                    )
                previous.update(running=True, active_until=time.time() + 90)
                _save(db, profile, _owner(identifier), previous)
                return status(profile, identifier)
            if (
                previous["running"]
                and previous["active_until"] > time.time()
                and owner != _owner(identifier)
            ):
                raise ValueError("Another browser session is controlling this paper account")
        refresh_account(profile)
        if (
            profile.account["trading_blocked"]
            or profile.account["status"] != "ACTIVE"
            or profile.account["cash"] <= 0
        ):
            raise ValueError("The paper account is blocked, inactive or has no available cash")
        positions = client.request("GET", "/v2/positions")
        orders = client.request(
            "GET",
            "/v2/orders",
            params={"status": "open", "symbols": report["symbol"], "limit": 500},
        )
        if any(p.get("symbol") == report["symbol"] for p in positions) or orders:
            raise ValueError(
                "Start with no position or open order in the selected symbol; the AI will not take ownership of manual trades"
            )
        unresolved = db.execute(
            "SELECT 1 FROM paper_actions WHERE scope=? AND state NOT IN ('filled','canceled','expired','rejected') LIMIT 1",
            (profile.scope,),
        ).fetchone()
        if unresolved:
            raise ValueError(
                "A prior paper submission is unresolved; reconcile it before starting a new runner"
            )
        state = {
            "running": True,
            "model_id": model_id,
            "symbol": report["symbol"],
            "max_notional": max_notional,
            "active_until": time.time() + 90,
            "owned_qty": 0.0,
            "entry_price": None,
            "pending": None,
            "last_entry_day": None,
            "decision_day": None,
            "held_sessions": 0,
            "last_held_day": None,
            "peak_equity": profile.account["equity"],
            "probability": None,
            "threshold": report["artifact"]["threshold"],
            "message": "Paper AI started. Waiting for a fresh market/account decision.",
            "events": [],
        }
        _save(db, profile, _owner(identifier), state)
    return status(profile, identifier)


def stop(profile, identifier):
    _paper(profile)
    with _lock(profile.scope), database() as db:
        owner, state = _read(db, profile)
        if state:
            state.update(
                running=False,
                active_until=0,
                message="Paper AI paused. Existing venue orders and positions remain; monitoring stops with this page.",
            )
            _save(db, profile, owner, state)
    return status(profile, identifier)


def _evidence(value, body):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("id"), str)
        or not 1 <= len(value["id"]) <= 100
    ):
        raise ValueError("Paper venue did not return a usable order identity")
    for field in ("symbol", "side", "client_order_id"):
        if value.get(field) != body[field]:
            raise ValueError("Paper venue order does not match the persisted request")
    if value.get("status") not in ORDER_STATES:
        raise ValueError("Paper venue returned an unknown order status")
    filled = finite(value.get("filled_qty"), minimum=0)
    if finite(value.get("qty")) != float(body["qty"]) or filled > float(body["qty"]):
        raise ValueError("Paper venue quantities contradict the request")
    average = finite(value.get("filled_avg_price"), minimum=0) if filled else None
    if filled and not average:
        raise ValueError("Filled paper order has no execution price")
    return {
        "id": value["id"],
        "status": value["status"],
        "filled_qty": filled,
        "filled_avg_price": average,
    }


def _apply(state, evidence):
    pending = state["pending"]
    delta = evidence["filled_qty"] - pending["applied_filled"]
    if delta < 0:
        raise ValueError("Paper venue filled quantity moved backwards")
    state["owned_qty"] += delta if pending["side"] == "buy" else -delta
    if state["owned_qty"] < -1e-6:
        raise ValueError("Paper fill exceeds AI-owned units")
    if pending["side"] == "buy" and evidence["filled_qty"]:
        state["entry_price"] = evidence["filled_avg_price"]
    pending["applied_filled"] = evidence["filled_qty"]
    if evidence["status"] in TERMINAL:
        state["pending"] = None
        if state["owned_qty"] <= 1e-6:
            state.update(owned_qty=0.0, entry_price=None, held_sessions=0)


def _reconcile(client, db, profile, state):
    pending = state["pending"]
    row = db.execute(
        "SELECT * FROM paper_actions WHERE id=? AND scope=?", (pending["id"], profile.scope)
    ).fetchone()
    if not row:
        raise ValueError("Paper submission journal is incomplete")
    body = json.loads(row["body"])
    try:
        raw = client.request(
            "GET",
            "/v2/orders:by_client_order_id",
            params={"client_order_id": body["client_order_id"]},
        )
    except BrokerUnavailable:
        state["message"] = (
            "Paper order outcome remains uncertain. No duplicate submission was made; check the paper account."
        )
        return
    evidence = _evidence(raw, body)
    db.execute(
        "UPDATE paper_actions SET state=?,response=? WHERE id=?",
        (evidence["status"], json.dumps(evidence), pending["id"]),
    )
    _apply(state, evidence)
    state["message"] = "Paper order status reconciled with actual venue fills."


def _submit(client, db, profile, state, side, quantity, price):
    if not state["running"] or state["active_until"] < time.time():
        raise ValueError("Paper browser heartbeat expired before submission")
    if quantity < 1 or not float(quantity).is_integer():
        raise ValueError(
            "This runner requires whole-share holdings; review fractional partial fills manually"
        )
    now, identifier = time.time(), uuid.uuid4().hex
    body = {
        "symbol": state["symbol"],
        "side": side,
        "qty": str(int(quantity)),
        "type": "limit",
        "limit_price": str(price),
        "time_in_force": "day",
        "client_order_id": "loki-paper-" + identifier,
    }
    db.execute("BEGIN IMMEDIATE")
    try:
        count = db.execute(
            "SELECT count(*) FROM paper_actions WHERE scope=? AND created>=?",
            (profile.scope, now // 86400 * 86400),
        ).fetchone()[0]
        if count >= 5:
            raise ValueError("The five-order UTC daily paper limit has been reached")
        state["pending"] = {"id": identifier, "side": side, "applied_filled": 0.0}
        db.execute(
            "INSERT INTO paper_actions VALUES(?,?,?,?,?,?)",
            (identifier, profile.scope, now, "claimed", json.dumps(body), None),
        )
        _save(db, profile, _owner(client.session_identifier), state)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        state["pending"] = None
        raise
    try:
        raw = client.request("POST", "/v2/orders", body=body)
        evidence = _evidence(raw, body)
        db.execute(
            "UPDATE paper_actions SET state=?,response=? WHERE id=?",
            (evidence["status"], json.dumps(evidence), identifier),
        )
        _apply(state, evidence)
        state["message"] = "Paper order submitted. Holdings update only from venue-confirmed fills."
    except Exception as exc:
        if isinstance(exc, BrokerUnavailable) and exc.code in {400, 401, 403, 422}:
            db.execute("UPDATE paper_actions SET state='rejected' WHERE id=?", (identifier,))
            state["pending"] = None
            state["message"] = (
                "Paper venue rejected the order. No retry was made. Review the account before the next session."
            )
            return
        db.execute("UPDATE paper_actions SET state='submission_unknown' WHERE id=?", (identifier,))
        state["message"] = (
            "Paper submission outcome is uncertain. No retry was made; the next cycle only reconciles this client order ID."
        )


def reconcile(profile, identifier, *, cancel=False):
    """Refresh fills while paused; an explicit cancellation never implies a fill reversal."""
    _paper(profile)
    client = AlpacaClient(profile)
    with _lock(profile.scope), database() as db:
        owner, state = _read(db, profile)
        if not state:
            raise ValueError("No paper AI journal exists for this account")
        if cancel:
            state.update(running=False, active_until=0)
            _save(db, profile, owner, state)
        if state.get("pending"):
            _reconcile(client, db, profile, state)
            if cancel and state.get("pending"):
                row = db.execute(
                    "SELECT response FROM paper_actions WHERE id=?", (state["pending"]["id"],)
                ).fetchone()
                evidence = json.loads(row[0]) if row and row[0] else None
                if not evidence:
                    state["message"] = (
                        "The pending paper order has no verified venue ID. Check the paper account; no cancellation was sent."
                    )
                else:
                    try:
                        client.request("DELETE", "/v2/orders/" + quote(evidence["id"], safe=""))
                        state["message"] = (
                            "Paper cancellation requested. Refresh fills to confirm the final status; an order may already have partially filled."
                        )
                    except Exception:
                        state["message"] = (
                            "Paper cancellation outcome is uncertain. Refresh fills and inspect the paper venue; no automatic retry was made."
                        )
        _save(db, profile, owner, state)
    return status(profile, identifier)


def tick(profile, identifier):
    _paper(profile)
    client = AlpacaClient(profile)
    client.session_identifier = identifier
    with _lock(profile.scope), database() as db:
        owner, state = _read(db, profile)
        if not state or owner != _owner(identifier):
            raise ValueError("Start the paper AI in this browser session first")
        if not state["running"] or state["active_until"] < time.time():
            raise ValueError("Paper AI is paused; explicitly start it to continue")
        state["active_until"] = time.time() + 90
        try:
            if state["pending"]:
                _reconcile(client, db, profile, state)
                if state["pending"]:
                    _save(db, profile, owner, state)
                    return status(profile, identifier)
            report = load_model(profile.scope, state["model_id"])
            clock = client.request("GET", "/v2/clock")
            if clock.get("is_open") is not True:
                state["message"] = "Market closed. Paper AI waits; no order was sent."
                _save(db, profile, owner, state)
                return status(profile, identifier)
            stamp = datetime.fromisoformat(str(clock.get("timestamp")).replace("Z", "+00:00"))
            if stamp.tzinfo is None or abs(time.time() - stamp.timestamp()) > 120:
                raise ValueError("Broker market clock is stale")
            day = stamp.date().isoformat()
            refresh_account(profile)
            equity = profile.account["equity"]
            state["peak_equity"] = max(equity, state["peak_equity"])
            if (
                profile.account["trading_blocked"]
                or profile.account["status"] != "ACTIVE"
                or equity <= 0
                or 1 - equity / state["peak_equity"] >= 0.03
            ):
                raise ValueError(
                    "Paper account is blocked or the 3% equity drawdown pause was reached"
                )
            positions = client.request("GET", "/v2/positions")
            position = next((p for p in positions if p.get("symbol") == state["symbol"]), None)
            actual = finite(position["qty"], minimum=0) if position else 0.0
            if abs(actual - state["owned_qty"]) > 1e-6:
                raise ValueError(
                    "Venue holdings differ from AI-owned fills. Manual or external activity requires review; no order sent"
                )
            quote_data = client.request(
                "GET",
                "/v2/stocks/" + quote(state["symbol"], safe="") + "/quotes/latest",
                data=True,
                params={"feed": "iex"},
            ).get("quote", {})
            bid, ask = finite(quote_data.get("bp"), minimum=0), finite(
                quote_data.get("ap"), minimum=0
            )
            quote_stamp = datetime.fromisoformat(str(quote_data.get("t")).replace("Z", "+00:00"))
            if (
                not 0 < bid <= ask
                or (ask - bid) / bid > 0.02
                or quote_stamp.tzinfo is None
                or not -5 <= time.time() - quote_stamp.timestamp() <= 120
            ):
                raise ValueError("Paper quote is missing, stale, crossed or too wide")
            if state["decision_day"] != day:
                bars = validate_bars(client.recent_bars(state["symbol"]))
                if not bars or (stamp.date() - bars[-1].timestamp.date()).days > 5:
                    raise ValueError("Recent completed daily history is stale")
                state["probability"] = predict(report["artifact"]["model"], feature_vector(bars))
                state["decision_day"] = day
                if state["owned_qty"] and state["last_held_day"] != day:
                    state["held_sessions"] += 1
                    state["last_held_day"] = day
            signal = state["threshold"] is not None and state["probability"] >= state["threshold"]
            quantum = Decimal(".01") if ask >= 1 else Decimal(".0001")
            if state["owned_qty"]:
                entry = state["entry_price"]
                exit_needed = (
                    not signal
                    or bid <= entry * 0.98
                    or bid >= entry * 1.04
                    or state["held_sessions"] >= 5
                )
                if exit_needed:
                    _submit(
                        client,
                        db,
                        profile,
                        state,
                        "sell",
                        state["owned_qty"],
                        Decimal(str(bid)).quantize(quantum, rounding=ROUND_FLOOR),
                    )
                else:
                    state["message"] = (
                        "Holding AI-owned paper units; monitoring the 2% stop, 4% take-profit and five-session limit."
                    )
            elif signal and state["last_entry_day"] != day:
                asset = client.request("GET", "/v2/assets/" + quote(state["symbol"], safe=""))
                if (
                    asset.get("symbol") != state["symbol"]
                    or asset.get("tradable") is not True
                    or asset.get("status") != "active"
                    or asset.get("class") != "us_equity"
                ):
                    raise ValueError("The paper asset is not a confirmed active tradable US equity")
                price = Decimal(str(ask)).quantize(quantum, rounding=ROUND_CEILING)
                budget = min(
                    state["max_notional"], equity * 0.10, max(0, profile.account["cash"]) / 1.01
                )
                qty = math.floor(budget / float(price))
                state["last_entry_day"] = day
                if qty:
                    state.update(held_sessions=0, last_held_day=day)
                    _submit(client, db, profile, state, "buy", qty, price)
                else:
                    state["message"] = (
                        "Available cash/risk budget cannot fund one whole share. No borrowing or fractional order was attempted."
                    )
            else:
                state["message"] = (
                    "Waiting in paper cash: no validation-supported entry signal, or this session's entry was already evaluated."
                )
        except Exception:
            state.update(
                running=False,
                message="Paper AI paused because market, account or journal checks failed. Review the account and connection before restarting. Existing paper positions/orders remain.",
            )
        _save(db, profile, owner, state)
    return status(profile, identifier)
