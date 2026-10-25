"""Explicit-start Alpaca live entries, durable claims and venue-held brackets.

One controller per account. Browser heartbeat grants a short execution lease;
restarts do not recreate authority. No order is retried after an uncertain POST.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import time
import uuid

from core.fusion.broker_link import AlpacaClient, finite, refresh_account
from core.fusion.paper_models import database


def _check(profile):
    if profile.provider != "alpaca" or profile.mode != "live" or profile.expires <= time.time():
        raise ValueError("Connect a current Alpaca LIVE account first")


def _owner(identifier):
    return hashlib.sha256(identifier.encode()).hexdigest()


@contextmanager
def _db():
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS live_agents(scope TEXT PRIMARY KEY, state TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS live_days(scope TEXT, day TEXT, equity REAL NOT NULL, PRIMARY KEY(scope,day))")
        db.execute("CREATE TABLE IF NOT EXISTS live_claims(id TEXT PRIMARY KEY, scope TEXT NOT NULL, day TEXT NOT NULL, body TEXT NOT NULL, result TEXT)")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            if db.in_transaction:
                db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise


def _read(db, profile):
    row = db.execute("SELECT state FROM live_agents WHERE scope=?", (profile.scope,)).fetchone()
    return json.loads(row[0]) if row else None


def _save(db, profile, state):
    db.execute("INSERT OR REPLACE INTO live_agents VALUES(?,?)", (profile.scope, json.dumps(state)))


def _day():
    return datetime.now(timezone.utc).date().isoformat()


def status(profile, identifier):
    _check(profile)
    with _db() as db:
        state = _read(db, profile) or {"running": False, "message": "Live runner has not been started."}
        result = dict(state)
        result["running"] = bool(state.get("running") and state.get("until", 0) > time.time())
        result["controlled_by_this_session"] = state.get("owner") == _owner(identifier)
        result.pop("owner", None)
        result["mode"] = "live"
        result["journal"] = [
            {"client_order_id": r["id"], "day": r["day"], "request": json.loads(r["body"]),
             "order": json.loads(r["result"]) if r["result"] else None}
            for r in db.execute("SELECT * FROM live_claims WHERE scope=? ORDER BY rowid DESC LIMIT 20", (profile.scope,))
        ]
        if state.get("running") and not result["running"]:
            result["message"] = "Heartbeat expired. No new entries; existing broker orders and positions remain."
        return result


def start(profile, identifier, symbol, max_notional, daily_loss, max_orders):
    _check(profile)
    if symbol not in {"SPY", "QQQ", "AAPL"}:
        raise ValueError("Choose a trained Alpaca equity: SPY, QQQ or AAPL")
    if not 1 <= finite(max_notional) <= 100000 or not 1 <= finite(daily_loss) <= 10000:
        raise ValueError("Set a positive order budget and daily loss limit within the displayed bounds")
    if isinstance(max_orders, bool) or not isinstance(max_orders, int) or not 1 <= max_orders <= 10:
        raise ValueError("Daily entry limit must be 1–10")
    refresh_account(profile)
    if profile.account["trading_blocked"] or profile.account["status"] != "ACTIVE":
        raise ValueError("Alpaca account is not active for trading")
    client = AlpacaClient(profile)
    with _db() as db:
        old = _read(db, profile)
        if old and old.get("running") and old.get("until", 0) > time.time() and old["owner"] != _owner(identifier):
            raise ValueError("Another browser session controls this live account")
        if old and old.get("pending"):
            raise ValueError("Reconcile the existing order claim before starting again")
        # Starting is not taking ownership of orders somebody else placed.
        if client.request("GET", "/v2/positions") or client.request("GET", "/v2/orders", params={"status": "open", "limit": 500}):
            raise ValueError("Start with a flat account and no open orders. Existing orders/positions remain at Alpaca.")
        day = _day()
        db.execute("INSERT OR IGNORE INTO live_days VALUES(?,?,?)", (profile.scope, day, profile.account["equity"]))
        baseline = db.execute("SELECT equity FROM live_days WHERE scope=? AND day=?", (profile.scope, day)).fetchone()[0]
        if baseline - profile.account["equity"] >= daily_loss:
            raise ValueError("Today's account-equity loss limit has already been reached")
        _save(db, profile, {"running": True, "owner": _owner(identifier), "until": time.time() + 90,
                           "symbol": symbol, "max_notional": max_notional, "daily_loss": daily_loss,
                           "max_orders": max_orders, "day": day, "baseline": baseline, "pending": None,
                           "next_check": 0, "message": "Live AI started. Entries use limit orders with broker-held stop/target brackets."})
    return status(profile, identifier)


def stop(profile, identifier):
    _check(profile)
    with _db() as db:
        state = _read(db, profile)
        if state:
            state.update(running=False, until=0, message="New AI entries stopped. Existing Alpaca orders and protective brackets remain; manage them at the broker.")
            _save(db, profile, state)
    return status(profile, identifier)


def _evidence(raw, body):
    if not isinstance(raw, dict) or not raw.get("id"):
        raise ValueError("Broker returned no order identity")
    if any(raw.get(k) != body[k] for k in ("symbol", "side", "client_order_id")):
        raise ValueError("Broker order identity differs from the claim")
    if raw.get("order_class") != "bracket" or raw.get("type") != "limit":
        raise ValueError("Broker did not confirm the requested bracket order")
    if finite(raw.get("qty")) != float(body["qty"]):
        raise ValueError("Broker order quantity differs from the claim")
    filled = finite(raw.get("filled_qty"), minimum=0)
    if filled > float(body["qty"]):
        raise ValueError("Broker filled quantity exceeds the claim")
    from core.fusion.paper_agent import ORDER_STATES
    if raw.get("status") not in ORDER_STATES:
        raise ValueError("Broker returned an unknown status")
    price = finite(raw.get("filled_avg_price"), minimum=0) if filled else None
    if filled and not price:
        raise ValueError("Broker fill has no price")
    return {"id": str(raw["id"]), "status": raw["status"], "filled_qty": filled, "filled_avg_price": price,
            "order_class": "bracket"}


def _reconcile(db, client, profile, state):
    claim = db.execute("SELECT body FROM live_claims WHERE id=? AND scope=?", (state["pending"], profile.scope)).fetchone()
    if not claim:
        raise ValueError("Live order journal is incomplete")
    body = json.loads(claim[0])
    raw = client.request("GET", "/v2/orders:by_client_order_id", params={"client_order_id": state["pending"]})
    result = _evidence(raw, body)
    db.execute("UPDATE live_claims SET result=? WHERE id=?", (json.dumps(result), state["pending"]))
    if result["status"] in {"filled", "canceled", "expired", "rejected"}:
        state["pending"] = None
    state["message"] = "Broker order status: " + result["status"] + ". Holdings and fills are confirmed by Alpaca."


def reconcile(profile, identifier):
    _check(profile)
    with _db() as db:
        state = _read(db, profile)
        if state and state.get("pending"):
            _reconcile(db, AlpacaClient(profile), profile, state)
            _save(db, profile, state)
    return status(profile, identifier)


def _analysis(symbol):
    from loki.api.ai_paper import _analyze
    return _analyze(symbol)


def _fresh(stamp):
    value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if value.tzinfo is None or not -5 <= time.time() - value.timestamp() <= 120:
        raise ValueError("Alpaca clock/quote is stale")


def tick(profile, identifier):
    _check(profile)
    client = AlpacaClient(profile, live_orders=True)
    failed = False
    with _db() as db:
        state = _read(db, profile)
        if not state or state.get("owner") != _owner(identifier):
            raise ValueError("Start live AI in this browser session first")
        if not state["running"] or state["until"] <= time.time():
            raise ValueError("Live runner is stopped or its heartbeat expired")
        if state["day"] != _day():
            state.update(running=False, message="UTC trading day changed. Start a new session with your limits.")
            _save(db, profile, state)
        elif state.get("next_check", 0) <= time.time():
            state.update(until=time.time() + 90, next_check=time.time() + 20)
            try:
                _cycle(db, client, profile, state)
            except Exception:
                failed = True
                state.update(running=False, message="Live AI stopped: account, market or order verification failed. Reconcile any pending claim; no order is automatically retried.")
            _save(db, profile, state)
    if failed:
        raise ConnectionError(state["message"])
    return status(profile, identifier)


def _cycle(db, client, profile, state):
    if state["pending"]:
        _reconcile(db, client, profile, state)
        return
    clock = client.request("GET", "/v2/clock")
    _fresh(clock.get("timestamp"))
    if clock.get("is_open") is not True:
        state["message"] = "US equity market closed. Waiting; no order submitted."
        return
    refresh_account(profile)
    if profile.account["trading_blocked"] or profile.account["status"] != "ACTIVE" or state["baseline"] - profile.account["equity"] >= state["daily_loss"]:
        state.update(running=False, message="Account blocked or daily equity-loss limit reached. New entries stopped; broker brackets remain.")
        return
    if client.request("GET", "/v2/positions") or client.request("GET", "/v2/orders", params={"status": "open", "limit": 500}):
        state["message"] = "Account has a position or working order. No additional entry; broker manages existing brackets."
        return
    claims = db.execute("SELECT body FROM live_claims WHERE scope=? AND day=?", (profile.scope, state["day"])).fetchall()
    if len(claims) >= state["max_orders"] or any(json.loads(c[0])["symbol"] == state["symbol"] for c in claims):
        state["message"] = "Daily entry allowance used (at most one entry per symbol per UTC day)."
        return
    analysis = _analysis(state["symbol"])
    signal = analysis.get("quant") or {}
    if not analysis.get("trained_profile_applied") or signal.get("action") != "BUY" or analysis["director"]["posture"] != "long":
        state["message"] = "Waiting for a trained BUY signal and long Director posture."
        return
    asset = client.request("GET", "/v2/assets/" + state["symbol"])
    if asset.get("symbol") != state["symbol"] or asset.get("tradable") is not True or asset.get("class") != "us_equity" or asset.get("status") != "active":
        raise ValueError("Asset is not a tradable US equity")
    q = client.request("GET", "/v2/stocks/" + state["symbol"] + "/quotes/latest", data=True, params={"feed": "iex"})["quote"]
    _fresh(q.get("t"))
    bid, ask = finite(q.get("bp")), finite(q.get("ap"))
    if not 1 <= bid <= ask or (ask - bid) / bid > 0.02:
        raise ValueError("Quote crossed, too wide, or below supported price")
    price = Decimal(str(ask)).quantize(Decimal(".01"), rounding=ROUND_CEILING)
    stop_price = Decimal(str(finite(signal.get("stop")))).quantize(Decimal(".01"), rounding=ROUND_FLOOR)
    target = Decimal(str(finite(signal.get("target")))).quantize(Decimal(".01"), rounding=ROUND_CEILING)
    if not 0 < stop_price < price < target:
        raise ValueError("Trained stop/target no longer bracket the current quote")
    budget = min(state["max_notional"], max(0, profile.account["cash"]) / 1.01)
    remaining_loss = state["daily_loss"] - max(0, state["baseline"] - profile.account["equity"])
    qty = math.floor(min(budget / float(price), remaining_loss * 0.25 / float(price - stop_price)))
    if qty < 1:
        state["message"] = "Order budget or stop-risk allowance cannot fund one whole share."
        return
    if state["until"] <= time.time():
        raise ValueError("Execution lease expired during market checks")
    cid = "loki-live-" + uuid.uuid4().hex
    body = {"symbol": state["symbol"], "side": "buy", "qty": str(qty), "type": "limit",
            "limit_price": str(price), "time_in_force": "gtc", "order_class": "bracket",
            "take_profit": {"limit_price": str(target)}, "stop_loss": {"stop_price": str(stop_price)},
            "client_order_id": cid}
    db.execute("INSERT INTO live_claims VALUES(?,?,?,?,NULL)", (cid, profile.scope, state["day"], json.dumps(body)))
    state["pending"] = cid
    state["message"] = "Order claimed; waiting for broker confirmation."
    _save(db, profile, state)
    db.execute("COMMIT")  # Durable BEFORE transport. An interrupted send is never replayed.
    try:
        raw = client.request("POST", "/v2/orders", body=body)
    finally:
        db.execute("BEGIN IMMEDIATE")
        latest = _read(db, profile)
        state.clear()
        state.update(latest)  # Preserve a Stop that landed while transport was in flight.
    result = _evidence(raw, body)
    db.execute("UPDATE live_claims SET result=? WHERE id=?", (json.dumps(result), cid))
    state["message"] = "Live bracket submitted; broker status: " + result["status"] + ". This is not assumed to be a fill."
