"""Owner-bound encrypted Tradovate session, usable across serverless instances."""

import json
import os
import time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from typing import Any, Literal

from core import tradovate
from loki.api.member_data import require_member

router = APIRouter(prefix="/api/account/funded", tags=["Funded accounts"])
COOKIE = "loki_tradovate"
COOKIE_PATH = "/api/account/funded"
TTL = 3600


def cipher() -> Fernet:
    try:
        return Fernet(os.environ.get("LOKI_BROKER_ENCRYPTION_KEY", "").encode())
    except (ValueError, TypeError):
        raise HTTPException(
            503, "Direct account linking needs the server's broker encryption key."
        ) from None


def owner(request: Request) -> str:
    member = require_member(request)
    if request.headers.get("x-workspace-owner") != member["uid"]:
        raise HTTPException(
            409, "Your Loki account changed. Reload before connecting a funded account."
        )
    return str(member["uid"])


def unpack(request: Request, uid: str) -> dict[str, Any] | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        data = json.loads(cipher().decrypt(raw.encode(), ttl=TTL))
        if not isinstance(data, dict):
            return None
        if (
            data["owner"] != uid
            or data["expires"] <= time.time()
            or data["environment"] not in tradovate.HOSTS
        ):
            return None
        return data
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None


def set_session(response: Response, request: Request, data: dict[str, Any]) -> None:
    encoded = cipher().encrypt(json.dumps(data, separators=(",", ":")).encode()).decode()
    if len(encoded) > 3800:
        raise HTTPException(422, "This token exceeds the supported connection size.")
    response.set_cookie(
        COOKIE,
        encoded,
        max_age=TTL,
        httponly=True,
        secure=request.url.scheme == "https" or bool(os.getenv("VERCEL")),
        samesite="strict",
        path=COOKIE_PATH,
    )


async def account_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(tradovate.snapshot, data["environment"], data["token"])
        result["expires_at"] = data["expires"]
        return dict(result)
    except tradovate.TradovateError as exc:
        raise HTTPException(422, str(exc)) from None


class ConnectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["demo", "live"]
    access_token: SecretStr = Field(min_length=16, max_length=1800)


@router.get("")
async def status(request: Request) -> dict[str, Any]:
    uid = owner(request)
    configured = bool(os.environ.get("LOKI_BROKER_ENCRYPTION_KEY"))
    data = unpack(request, uid) if configured else None
    if not data:
        return {"connected": False, "configured": configured, "execution_enabled": False}
    return await account_snapshot(data)


@router.post("/connect")
async def connect(request: Request, response: Response) -> dict[str, Any]:
    uid = owner(request)
    cipher()
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, "Connection request is too large.")
    try:
        body = ConnectBody.model_validate_json(bytes(raw))
    except ValueError:
        # Validation errors must never echo submitted credentials.
        raise HTTPException(
            422, "Choose a server and enter an API access token of 16–1800 characters."
        ) from None
    token = body.access_token.get_secret_value().strip()
    if (
        len(token) < 16
        or not token.isascii()
        or any(c.isspace() or not c.isprintable() for c in token)
    ):
        raise HTTPException(422, "Enter a Tradovate access token, without the Bearer prefix.")
    data = {
        "owner": uid,
        "environment": body.environment,
        "token": token,
        "expires": int(time.time()) + TTL,
    }
    result = await account_snapshot(data)
    set_session(response, request, data)
    return result


@router.post("/disconnect")
async def disconnect(request: Request, response: Response) -> dict[str, Any]:
    owner(request)
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return {"connected": False, "execution_enabled": False}
