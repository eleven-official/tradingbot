"""Bounded Tradovate account reads through fixed official API hosts."""
import json
import math

import requests

HOSTS = {"demo": "https://demo.tradovateapi.com/v1", "live": "https://live.tradovateapi.com/v1"}
RESOURCES = {"account/list", "position/list", "cashBalance/list", "currency/list", "contract/items"}


class TradovateError(ValueError):
    pass


def read(environment, token, resource, params=None):
    if environment not in HOSTS or resource not in RESOURCES:
        raise TradovateError("Choose the Tradovate server assigned to your account.")
    try:
        with requests.get(
            HOSTS[environment] + "/" + resource,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            params=params, timeout=(4, 8), allow_redirects=False, stream=True,
        ) as response:
            if response.status_code in (401, 403):
                raise TradovateError("Tradovate rejected access. Reconnect with a current token for the selected server and API-enabled account.")
            if response.status_code == 429:
                raise TradovateError("Tradovate is rate limiting requests. Wait a minute before refreshing.")
            if response.status_code != 200:
                raise TradovateError("Tradovate is unavailable. Try refreshing shortly.")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 1_000_000:
                    raise TradovateError("Tradovate response exceeded the account-read limit.")
                chunks.append(chunk)
            rows = json.loads(b"".join(chunks))
            if not isinstance(rows, list) or len(rows) > 5000 or any(not isinstance(r, dict) for r in rows):
                raise TradovateError("Tradovate returned an unexpected account response.")
            return rows
    except (requests.RequestException, json.JSONDecodeError) as exc:
        raise TradovateError("Could not read Tradovate. Check your connection and retry.") from exc


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def snapshot(environment, token):
    accounts = read(environment, token, "account/list")
    if not accounts:
        raise TradovateError("No accounts were returned. Check the selected server and your firm's API access.")
    if len(accounts) > 100:
        raise TradovateError("This connection exceeds the 100-account limit.")
    accounts = [{k: a.get(k) for k in ("id", "name", "closed", "restricted", "readonly", "active")} for a in accounts]
    if any(not isinstance(a["id"], int) or isinstance(a["id"], bool) for a in accounts):
        raise TradovateError("Tradovate returned an invalid account identifier.")
    owners = {a["id"] for a in accounts}
    result = {"connected": True, "environment": environment, "accounts": accounts,
              "positions": None, "balances": None, "messages": [], "execution_enabled": False}
    # An account can connect without granting every optional read permission.
    try:
        positions = read(environment, token, "position/list")
        result["positions"] = [{"account_id": p.get("accountId"), "contract_id": p.get("contractId"),
                                "quantity": number(p.get("netPos")), "net_price": number(p.get("netPrice"))}
                               for p in positions if p.get("accountId") in owners and p.get("netPos") != 0]
    except TradovateError as exc:
        result["messages"].append(str(exc))
    try:
        balances = read(environment, token, "cashBalance/list")
        result["balances"] = [{"account_id": b.get("accountId"), "currency_id": b.get("currencyId"),
                               "cash": number(b.get("amount")), "realized_pnl": number(b.get("realizedPnL")),
                               "timestamp": b.get("timestamp")}
                              for b in balances if b.get("accountId") in owners]
    except TradovateError as exc:
        result["messages"].append(str(exc))
    return result


def request_token(environment, name, password, cid, sec, app_id="Loki", app_version="1.0"):
    """Exchange Tradovate API credentials for an access token (password never stored).

    Uses Tradovate's documented /auth/accesstokenrequest. Returns
    ``(access_token, expires_epoch_seconds or None)``.
    """
    if environment not in HOSTS:
        raise TradovateError("Choose the Tradovate server assigned to your account.")
    body = {"name": name, "password": password, "appId": app_id, "appVersion": app_version,
            "cid": cid, "sec": sec}
    try:
        response = requests.post(HOSTS[environment] + "/auth/accesstokenrequest", json=body,
                                 headers={"Accept": "application/json"}, timeout=(4, 10),
                                 allow_redirects=False)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TradovateError("Could not reach Tradovate. Check your connection and retry.") from exc
    if response.status_code == 429:
        raise TradovateError("Tradovate is rate limiting sign-ins. Wait a minute and retry.")
    if not isinstance(data, dict):
        raise TradovateError("Tradovate returned an unexpected sign-in response.")
    if data.get("p-ticket"):
        wait = data.get("p-time")
        raise TradovateError(
            f"Tradovate paused sign-in after repeated attempts; wait {int(wait)} seconds and retry."
            if isinstance(wait, (int, float)) else "Tradovate paused sign-in after repeated attempts; wait and retry."
        )
    if data.get("errorText"):
        raise TradovateError(str(data["errorText"])[:200])
    token = data.get("accessToken")
    if not isinstance(token, str) or len(token) < 16:
        raise TradovateError("Tradovate did not issue an access token for these credentials.")
    expires = None
    stamp = data.get("expirationTime")
    if isinstance(stamp, str):
        try:
            from datetime import datetime

            expires = int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
        except ValueError:
            expires = None
    return token, expires
