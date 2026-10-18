"""Manual Kraken spot orders with immutable previews and durable side-effect claims.

No strategy, council result, chat message or mode change calls this transport.
Only an explicitly confirmed, locally authenticated request can claim an order.
An uncertain response is never retried automatically, including after restart.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from core.fusion.real_account import make_client, status
from third_party.vibe_trading.order_contracts import PendingOrderRequest

SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD")
CONFIRMATION = "PLACE REAL ORDER"
CANCEL_CONFIRMATION = "CANCEL REAL ORDER"
TERMINAL = {"closed", "canceled", "expired", "rejected"}
DEFAULT_JOURNAL = Path(__file__).resolve().parents[2] / "state/real/orders.sqlite3"


def _number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("A finite numeric value is required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("A finite numeric value is required") from exc
    if not result.is_finite():
        raise ValueError("A finite numeric value is required")
    return result


def _config(environ, *, writing=False):
    env = os.environ if environ is None else environ
    state = status(env)
    if not state["ready_to_connect"]:
        raise ValueError(" ".join(state["reasons"]))
    if state["exchange"] != "kraken":
        raise ValueError("Manual orders currently support Kraken spot only")
    if writing and env.get("LOKI_REAL_ORDERS_ENABLED") != "1":
        raise ValueError("The host has not enabled real order submission")
    cap = _number(env.get("LOKI_REAL_MAX_ORDER_USD", "100"))
    daily = _number(env.get("LOKI_REAL_DAILY_ORDER_LIMIT", "5"))
    if not 1 <= cap <= 10000 or not 1 <= daily <= 100 or daily != int(daily):
        raise ValueError(
            "Real order limits are invalid; cap must be 1–10000 USD and daily count 1–100"
        )
    scope = hashlib.sha256(("kraken\n" + env["LOKI_REAL_API_KEY"]).encode()).hexdigest()
    return env, scope, cap, int(daily)


@contextmanager
def _database(env):
    path = Path(env.get("LOKI_REAL_ORDER_JOURNAL", str(DEFAULT_JOURNAL))).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS intents ("
            "id TEXT PRIMARY KEY, scope TEXT NOT NULL, state TEXT NOT NULL, "
            "created REAL NOT NULL, expires REAL NOT NULL, updated REAL NOT NULL, "
            "submitted REAL, request TEXT NOT NULL, preview TEXT NOT NULL, "
            "venue_order TEXT, message TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "id INTEGER PRIMARY KEY, intent TEXT NOT NULL, at REAL NOT NULL, state TEXT NOT NULL)"
        )
        yield db
    except sqlite3.Error as exc:
        raise ConnectionError(
            "Real order journal is unavailable; no automatic submission retry is permitted"
        ) from exc
    finally:
        db.close()


@contextmanager
def _transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def _row(db, scope, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Unknown real order preview")
    row = db.execute("SELECT * FROM intents WHERE id=? AND scope=?", (identifier, scope)).fetchone()
    if row is None:
        raise ValueError("Unknown real order preview for this account key")
    return row


def _public(row):
    return {
        "id": row["id"],
        "client_order_id": row["id"],
        "state": row["state"],
        "created_at": row["created"],
        "expires_at": row["expires"],
        "submitted_at": row["submitted"],
        "request": json.loads(row["request"]),
        "preview": json.loads(row["preview"]),
        "order": json.loads(row["venue_order"]) if row["venue_order"] else None,
        "message": row["message"],
        "mode": "real_account",
    }


def _update(db, identifier, state, message, order=None):
    # Commit to stable storage before the caller is allowed to make a side effect.
    db.execute(
        "UPDATE intents SET state=?, updated=?, message=?, venue_order=COALESCE(?,venue_order) WHERE id=?",
        (state, time.time(), message, json.dumps(order) if order else None, identifier),
    )
    db.execute(
        "INSERT INTO events(intent,at,state) VALUES(?,?,?)", (identifier, time.time(), state)
    )


@contextmanager
def _exchange(env):
    client = make_client(env)
    try:
        yield client
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def _preflight(client, request, cap):
    # The original Vibe validation rejects unknown fields, ambiguous sizes and NaNs.
    order = PendingOrderRequest.model_validate(request)
    if (
        order.symbol not in SYMBOLS
        or order.order_type != "limit"
        or order.time_in_force != "gtc"
        or order.quantity is None
    ):
        raise ValueError("Use a quantity-based GTC limit order in BTC/USD, ETH/USD or SOL/USD")
    markets = client.load_markets()
    market = markets.get(order.symbol, {})
    if market.get("spot") is not True or market.get("active") is not True:
        raise ValueError("The venue has not confirmed this spot market is active")
    quantity = _number(client.amount_to_precision(order.symbol, order.quantity))
    price = _number(client.price_to_precision(order.symbol, order.limit_price))
    if not 0 < quantity <= _number(order.quantity) or price <= 0:
        raise ValueError("Venue precision left no valid quantity or increased the requested size")
    cost = quantity * price
    for field, value in (("amount", quantity), ("price", price), ("cost", cost)):
        bounds = (market.get("limits") or {}).get(field) or {}
        if bounds.get("min") is not None and value < _number(bounds["min"]):
            raise ValueError(f"Order is below the venue {field} minimum")
        if bounds.get("max") is not None and value > _number(bounds["max"]):
            raise ValueError(f"Order exceeds the venue {field} maximum")
    # This is an estimate, not a guaranteed fee quote. Reserve at least 1% in cash.
    fee_rate = max(
        Decimal("0.01"), _number(market.get("taker") or 0), _number(market.get("maker") or 0)
    )
    if fee_rate > Decimal("0.05") or cost * (1 + fee_rate) > cap:
        raise ValueError("Order plus the fee buffer exceeds the host USD order cap")
    ticker = client.fetch_ticker(order.symbol)
    bid, ask = _number(ticker.get("bid")), _number(ticker.get("ask"))
    if not 0 < bid <= ask or (ask - bid) / bid > Decimal("0.02"):
        raise ValueError("The venue quote is missing, crossed or too wide")
    stamp = ticker.get("timestamp")
    observed = time.time()
    if stamp is not None and not -5 <= observed - float(_number(stamp) / 1000) <= 30:
        raise ValueError("The venue quote timestamp is stale or in the future")
    if abs(price / ((ask + bid) / 2) - 1) > Decimal("0.05"):
        raise ValueError("The limit is more than 5% from the observed venue quote")
    balance = client.fetch_balance()
    free = balance.get("free")
    currency = "USD" if order.side == "buy" else order.symbol.split("/")[0]
    if not isinstance(free, dict) or currency not in free:
        raise ValueError("The venue did not provide the required available asset balance")
    available = _number(free[currency])
    required = cost * (1 + fee_rate) if order.side == "buy" else quantity
    if available < required:
        raise ValueError(
            "Insufficient available spot assets; borrowing and short sales are disabled"
        )
    completed = time.time()
    if completed - observed > 15 or (
        stamp is not None and completed - float(_number(stamp) / 1000) > 30
    ):
        raise ValueError("Quote became stale during account checks; request a new preview")
    canonical = order.model_dump()
    canonical.update(quantity=float(quantity), limit_price=float(price))
    preview = {
        "exchange": "kraken",
        "estimated_notional_usd": str(cost),
        "fee_buffer_usd": str(cost * fee_rate),
        "host_order_cap_usd": str(cap),
        "available_asset": currency,
        "available_units": str(available),
        "required_units": str(required),
        "bid": str(bid),
        "ask": str(ask),
        "observed_at": observed,
        "venue_timestamp": stamp,
        "notes": [
            "Prices and quantities shown here include venue precision adjustments.",
            "The fee buffer is an estimate; venue fees and execution may differ.",
            "A GTC limit can fill immediately or remain open until canceled. No automatic stop is attached.",
            "Manual placement does not indicate a validated strategy or a proven 70% win rate.",
        ],
    }
    return canonical, preview


def _complete(db, scope, identifier, expected, state, message, order=None):
    with _transaction(db):
        # A late transport response must not overwrite a newer reconciliation.
        if _row(db, scope, identifier)["state"] == expected:
            _update(db, identifier, state, message, order)


def preview_order(request, environ=None):
    env, scope, cap, _ = _config(environ, writing=True)
    try:
        with _exchange(env) as client:
            canonical, preview = _preflight(client, request, cap)
    except ValueError:
        raise
    except Exception as exc:
        raise ConnectionError(
            "The exchange could not complete the order preview; no order was submitted"
        ) from exc
    identifier, now = uuid.uuid4().hex, time.time()
    with _database(env) as db, _transaction(db):
        db.execute(
            "INSERT INTO intents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                scope,
                "prepared",
                now,
                now + 60,
                now,
                None,
                json.dumps(canonical),
                json.dumps(preview),
                None,
                "Preview only. No order has been sent.",
            ),
        )
        _update(db, identifier, "prepared", "Preview only. No order has been sent.")
        return _public(_row(db, scope, identifier))


def _order_evidence(value, row):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("id"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["id"])
    ):
        raise ValueError("Missing venue order identity")
    request = json.loads(row["request"])
    for field, expected in (
        ("clientOrderId", row["id"]),
        ("symbol", request["symbol"]),
        ("side", request["side"]),
        ("type", "limit"),
        ("timeInForce", "GTC"),
    ):
        if value.get(field) is not None and value[field] != expected:
            raise ValueError("Venue order evidence contradicts the saved request")
    for field, expected in (("amount", request["quantity"]), ("price", request["limit_price"])):
        if value.get(field) is not None and _number(value[field]) != _number(expected):
            raise ValueError("Venue size or limit contradicts the saved request")
    state = value.get("status")
    if state not in {None, "open", "closed", "canceled", "expired", "rejected"}:
        raise ValueError("Unrecognized venue order status")
    filled = value.get("filled")
    if filled is not None and not 0 <= _number(filled) <= _number(request["quantity"]):
        raise ValueError("Invalid venue filled quantity")
    previous = json.loads(row["venue_order"]) if row["venue_order"] else {}
    return {
        "id": value["id"],
        "status": state,
        "filled": str(filled) if filled is not None else previous.get("filled"),
    }


def submit_order(identifier, confirmation, environ=None):
    if confirmation != CONFIRMATION:
        raise ValueError(f"Type {CONFIRMATION} to submit the reviewed real order")
    env, scope, cap, daily = _config(environ, writing=True)
    with _database(env) as db:
        row = _row(db, scope, identifier)
        if row["state"] != "prepared":
            return _public(row)  # Persistent idempotency, including ambiguous outcomes.
        if row["expires"] < time.time():
            raise ValueError("Preview expired; request and review a new preview")
        try:
            with _exchange(env) as client:
                canonical, _ = _preflight(client, json.loads(row["request"]), cap)
                if canonical != json.loads(row["request"]):
                    raise ValueError("Venue precision changed; request a new preview")
                with _transaction(db):
                    row = _row(db, scope, identifier)
                    if row["state"] != "prepared":
                        return _public(row)
                    now = time.time()
                    if row["expires"] < now:
                        raise ValueError(
                            "Preview expired during account recheck; request a new preview"
                        )
                    if db.execute(
                        "SELECT 1 FROM intents WHERE scope=? AND id<>? AND state NOT IN ('prepared','closed','canceled','expired','rejected') LIMIT 1",
                        (scope, identifier),
                    ).fetchone():
                        raise ValueError(
                            "Resolve or cancel the existing real order before placing another"
                        )
                    count = db.execute(
                        "SELECT count(*) FROM intents WHERE scope=? AND submitted>=?",
                        (scope, now // 86400 * 86400),
                    ).fetchone()[0]
                    if count >= daily:
                        raise ValueError("The host daily real-order limit has been reached")
                    db.execute("UPDATE intents SET submitted=? WHERE id=?", (now, identifier))
                    _update(
                        db,
                        identifier,
                        "submitting",
                        "Submission claimed durably. Do not resubmit; reconcile if the response is lost.",
                    )
                try:
                    # Exactly one transport call after the claim. CCXT network retries are disabled.
                    result = client.create_order(
                        canonical["symbol"],
                        "limit",
                        canonical["side"],
                        canonical["quantity"],
                        canonical["limit_price"],
                        {"clientOrderId": identifier, "timeInForce": "GTC"},
                    )
                    evidence = _order_evidence(result, row)
                    next_state = (
                        evidence["status"] if evidence["status"] in TERMINAL else "submitted"
                    )
                    _complete(
                        db,
                        scope,
                        identifier,
                        "submitting",
                        next_state,
                        "Venue response recorded. Refresh order status to reconcile fills.",
                        evidence,
                    )
                except Exception as exc:
                    import ccxt

                    definite = isinstance(
                        exc,
                        (
                            ccxt.InvalidOrder,
                            ccxt.InsufficientFunds,
                            ccxt.AuthenticationError,
                            ccxt.PermissionDenied,
                        ),
                    )
                    _complete(
                        db,
                        scope,
                        identifier,
                        "submitting",
                        "rejected" if definite else "submission_unknown",
                        (
                            "Venue rejected this request; create a new preview after checking the account."
                            if definite
                            else "Submission outcome is unknown. No retry was made. Reconcile with the venue before any new order."
                        ),
                    )
                return _public(_row(db, scope, identifier))
        except ValueError:
            raise
        except Exception as exc:
            raise ConnectionError(
                "Real order workflow unavailable. Inspect the durable journal before attempting another order"
            ) from exc


def list_orders(environ=None):
    env, scope, _, _ = _config(environ)
    with _database(env) as db:
        return {
            "orders": [
                _public(row)
                for row in db.execute(
                    "SELECT * FROM intents WHERE scope=? ORDER BY created DESC LIMIT 50", (scope,)
                )
            ]
        }


def reconcile_order(identifier, environ=None):
    env, scope, _, _ = _config(environ)
    with _database(env) as db:
        row = _row(db, scope, identifier)
        if row["state"] == "prepared" or row["state"] in TERMINAL:
            return _public(row)
        if row["state"] in {"submitting", "canceling"} and time.time() - row["updated"] < 60:
            raise ValueError("An exchange request is still pending; wait before reconciliation")
        order = json.loads(row["venue_order"]) if row["venue_order"] else None
        request = json.loads(row["request"])
        try:
            with _exchange(env) as client:
                if order:
                    value = client.fetch_order(order["id"], request["symbol"])
                else:
                    # No match does not prove absence; list pagination/venue retention may omit it.
                    candidates = client.fetch_open_orders(
                        request["symbol"]
                    ) + client.fetch_closed_orders(request["symbol"], int(row["created"] * 1000))
                    matches = [
                        item for item in candidates if item.get("clientOrderId") == identifier
                    ]
                    if len(matches) != 1:
                        return _public(row)
                    value = matches[0]
                evidence = _order_evidence(value, row)
                if order and evidence["id"] != order["id"]:
                    raise ValueError("Venue identity changed during reconciliation")
        except Exception as exc:
            raise ConnectionError(
                "Venue reconciliation did not return trustworthy order evidence. No retry or new order was sent"
            ) from exc
        with _transaction(db):
            latest = _row(db, scope, identifier)
            if latest["updated"] != row["updated"]:
                return _public(latest)
            next_state = evidence["status"] if evidence["status"] in TERMINAL else "submitted"
            _update(db, identifier, next_state, "Order status read from the venue.", evidence)
        return _public(_row(db, scope, identifier))


def cancel_order(identifier, confirmation, environ=None):
    if confirmation != CANCEL_CONFIRMATION:
        raise ValueError(f"Type {CANCEL_CONFIRMATION} to request cancellation")
    # Cancellation remains available when the host disables new order submission.
    env, scope, _, _ = _config(environ)
    with _database(env) as db:
        with _transaction(db):
            row = _row(db, scope, identifier)
            if row["state"] in TERMINAL or row["state"] in {"canceling", "cancel_unknown"}:
                return _public(row)
            if row["state"] != "submitted" or not row["venue_order"]:
                raise ValueError("Reconcile a known venue order before requesting cancellation")
            _update(
                db,
                identifier,
                "canceling",
                "Cancellation claimed. A request does not prove the order has stopped filling.",
            )
        try:
            with _exchange(env) as client:
                result = client.cancel_order(
                    json.loads(row["venue_order"])["id"], json.loads(row["request"])["symbol"]
                )
            evidence = _order_evidence(result, row)
            if evidence["id"] != json.loads(row["venue_order"])["id"]:
                raise ValueError("Cancellation returned a different order identity")
            next_state = evidence["status"] if evidence["status"] in TERMINAL else "cancel_unknown"
            _complete(
                db,
                scope,
                identifier,
                "canceling",
                next_state,
                "Cancellation response recorded. Reconcile status and fills with the venue.",
                evidence,
            )
        except Exception:
            _complete(
                db,
                scope,
                identifier,
                "canceling",
                "cancel_unknown",
                "Cancellation outcome is unknown. Reconcile venue status; no automatic cancellation retry was made.",
            )
        return _public(_row(db, scope, identifier))
