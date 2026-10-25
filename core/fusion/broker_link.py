"""Verified local broker sessions. Secrets live in server memory, never exports.

Alpaca order writes default to the fixed paper host. Only the explicitly
started live runner constructs a client with live-order authority.
CCXT connections remain account inspection only here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import secrets
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

PAPER_HOST = "https://paper-api.alpaca.markets"
LIVE_HOST = "https://api.alpaca.markets"
DATA_HOST = "https://data.alpaca.markets"
COOKIE = "loki_broker_session"
TTL = 4 * 3600


class BrokerUnavailable(ConnectionError):
    def __init__(self, code=None):
        self.code = code
        super().__init__(
            "Broker request failed. Check account access, data entitlement and connectivity; credentials were not returned."
        )


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise BrokerUnavailable()


def finite(value, *, minimum=None):
    if isinstance(value, bool) or value is None:
        raise ValueError("Broker returned an invalid numeric account value")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Broker returned an invalid numeric account value") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError("Broker returned an invalid numeric account value")
    return result


@dataclass(repr=False)
class Profile:
    provider: str
    mode: str
    key: str = field(repr=False)
    secret: str = field(repr=False)
    passphrase: str = field(default="", repr=False)
    account: dict = field(default_factory=dict)
    scope: str = ""
    expires: float = field(default_factory=lambda: time.time() + TTL)

    def public(self):
        return {
            "connected": True,
            "provider": self.provider,
            "mode": self.mode,
            "account": self.account,
            "expires_at": self.expires,
            "paper_ai_available": self.provider == "alpaca" and self.mode == "paper",
            "live_automation_available": self.provider == "alpaca" and self.mode == "live",
            "credential_storage": "Server memory for four hours or until disconnect/restart; never browser storage or source files.",
        }


_profiles = {}
_lock = threading.RLock()


def _prune():
    for identifier, profile in list(_profiles.items()):
        if profile.expires <= time.time():
            _profiles.pop(identifier, None)


def get_profile(identifier):
    with _lock:
        _prune()
        result = _profiles.get(identifier)
        if result is None:
            raise ValueError("Connect a broker account in this browser session first")
        return result


def disconnect(identifier):
    with _lock:
        _profiles.pop(identifier, None)


def connect(provider, mode, key, secret, passphrase="", previous=None):
    if provider not in {"alpaca", "kraken", "coinbase", "binance"} or mode not in {"paper", "live"}:
        raise ValueError("Choose a supported provider and paper or live account")
    if provider != "alpaca" and mode != "live":
        raise ValueError(
            "Exchange links support live account inspection; use Alpaca for a broker paper account"
        )
    for value in (key, secret):
        if (
            not isinstance(value, str)
            or not 8 <= len(value) <= 256
            or not value.isascii()
            or any(c.isspace() or not c.isprintable() for c in value)
        ):
            raise ValueError(
                "Enter valid broker key and secret values; credentials cannot contain whitespace"
            )
    if (
        not isinstance(passphrase, str)
        or len(passphrase) > 256
        or any(c in passphrase for c in "\r\n\x00")
    ):
        raise ValueError("Broker passphrase is invalid")
    profile = Profile(provider, mode, key, secret, passphrase)
    refresh_account(profile)  # Never label a key verified before a real account response.
    identifier = secrets.token_urlsafe(32)
    with _lock:
        _prune()
        if len(_profiles) >= 50:
            raise ValueError("Too many local broker sessions; disconnect unused sessions")
        _profiles[identifier] = profile
        if previous:
            _profiles.pop(previous, None)
    return identifier, profile.public()


class AlpacaClient:
    def __init__(self, profile, *, live_orders=False):
        if profile.provider != "alpaca":
            raise ValueError("This operation requires an Alpaca connection")
        self.profile = profile
        self.live_orders = live_orders

    def request(self, method, path, *, data=False, params=None, body=None):
        if self.profile.expires <= time.time():
            raise ValueError("Broker connection expired; reconnect before continuing")
        if not path.startswith("/v2/") or "?" in path or "#" in path or ".." in path:
            raise ValueError("Unsupported fixed broker resource")
        if method not in {"GET", "POST", "DELETE"}:
            raise ValueError("Unsupported broker operation")
        if method != "GET" and (
            data or (self.profile.mode != "paper" and not self.live_orders) or not path.startswith("/v2/orders")
        ):
            raise ValueError("Automated order writes are restricted to the Alpaca paper endpoint")
        host = DATA_HOST if data else PAPER_HOST if self.profile.mode == "paper" else LIVE_HOST
        url = host + path + ("?" + urlencode(params) if params else "")
        headers = {
            "APCA-API-KEY-ID": self.profile.key,
            "APCA-API-SECRET-KEY": self.profile.secret,
            "Accept": "application/json",
            "User-Agent": "Loki-Paper-Research/1.0",
        }
        raw = json.dumps(body).encode() if body is not None else None
        if raw is not None:
            headers["Content-Type"] = "application/json"
        try:
            req = Request(url, headers=headers, data=raw, method=method)
            with build_opener(_NoRedirects()).open(req, timeout=12) as response:
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise BrokerUnavailable()
            return json.loads(raw) if raw else {}
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise ValueError(
                    "Broker rejected account access or data entitlement. Check that the keys match the selected paper/live account."
                ) from None
            raise BrokerUnavailable(exc.code) from None
        except (OSError, ValueError) as exc:
            raise BrokerUnavailable() from exc

    def historical_bars(self, symbol, years):
        if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol) or years not in {5, 10}:
            raise ValueError("Use a US equity symbol and a five- or ten-year history window")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=round(years * 365.25))
        rows, token, seen = [], None, set()
        for _ in range(5):
            params = {
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": "split",
                "feed": "iex",
                "sort": "asc",
                "limit": 10000,
            }
            if token:
                params["page_token"] = token
            result = self.request(
                "GET", "/v2/stocks/" + quote(symbol, safe="") + "/bars", data=True, params=params
            )
            for bar in result.get("bars") or []:
                if str(bar.get("t", ""))[:10] >= end.isoformat():
                    continue  # Never train on the current incomplete daily candle.
                rows.append(
                    {
                        "timestamp": bar.get("t"),
                        "open": bar.get("o"),
                        "high": bar.get("h"),
                        "low": bar.get("l"),
                        "close": bar.get("c"),
                        "volume": bar.get("v"),
                    }
                )
                if len(rows) > 5000:
                    raise ValueError("Daily history exceeded the bounded 5000-bar limit")
            token = result.get("next_page_token")
            if not token:
                break
            if token in seen:
                raise BrokerUnavailable()
            seen.add(token)
        else:
            raise ValueError("History pagination was incomplete; no partial dataset was trained")
        return rows

    def recent_bars(self, symbol):
        today = datetime.now(timezone.utc).date()
        result = self.request(
            "GET",
            "/v2/stocks/" + quote(symbol, safe="") + "/bars",
            data=True,
            params={
                "timeframe": "1Day",
                "start": (today - timedelta(days=90)).isoformat(),
                "end": today.isoformat(),
                "feed": "iex",
                "adjustment": "split",
                "sort": "asc",
                "limit": 1000,
            },
        )
        if result.get("next_page_token"):
            raise ValueError("Recent daily history was incomplete")
        return [
            {
                "timestamp": b["t"],
                "open": b["o"],
                "high": b["h"],
                "low": b["l"],
                "close": b["c"],
                "volume": b["v"],
            }
            for b in result.get("bars", [])
            if str(b["t"])[:10] < today.isoformat()
        ]


def refresh_account(profile):
    if profile.provider == "alpaca":
        account = AlpacaClient(profile).request("GET", "/v2/account")
        if (
            not isinstance(account, dict)
            or not isinstance(account.get("id"), str)
            or account.get("currency") != "USD"
            or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", account.get("id", ""))
            or not re.fullmatch(r"[A-Z_]{1,40}", str(account.get("status", "")))
        ):
            raise ValueError("Broker did not return a verifiable USD account")
        profile.account = {
            "id_hint": account["id"][-4:],
            "currency": "USD",
            "status": account.get("status"),
            "cash": finite(account.get("cash")),
            "equity": finite(account.get("equity"), minimum=0),
            "trading_blocked": account.get("trading_blocked") is not False
            or account.get("account_blocked") is not False,
        }
        identity = account["id"]
    else:
        from core.fusion.real_account import account_snapshot

        result = account_snapshot(
            {
                "LOKI_REAL_EXCHANGE": profile.provider,
                "LOKI_REAL_READS_ENABLED": "1",
                "LOKI_REAL_API_KEY": profile.key,
                "LOKI_REAL_API_SECRET": profile.secret,
                "LOKI_REAL_API_PASSPHRASE": profile.passphrase,
            }
        )
        profile.account = {
            "assets": result["assets"],
            "valuation": None,
            "status": "connected_read_only",
        }
        identity = profile.key
    profile.scope = hashlib.sha256(
        (profile.provider + "|" + profile.mode + "|" + identity).encode()
    ).hexdigest()
    return profile.public()
