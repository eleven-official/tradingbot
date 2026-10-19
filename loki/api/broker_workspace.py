"""Local-only key entry, historical model training and PAPER-only AI control."""

from fastapi import APIRouter, Request, Response
from pydantic import Field, SecretStr
from typing import Literal
import json

from loki.api.fusion import StrictModel, _call, _require_local_action, _private_response
from core.fusion import broker_link, paper_models, paper_agent

router = APIRouter(prefix="/api/fusion/broker", tags=["Private broker workspace"])


def _private(request, response):
    _require_local_action(request)
    _private_response(response)


def _session(request):
    identifier = request.cookies.get(broker_link.COOKIE, "")
    return _call(broker_link.get_profile, identifier), identifier


class ConnectRequest(StrictModel):
    provider: Literal["alpaca", "kraken", "coinbase", "binance"] = "alpaca"
    mode: Literal["paper", "live"] = "paper"
    api_key: SecretStr
    api_secret: SecretStr
    passphrase: SecretStr = SecretStr("")


@router.post("/connect")
def connect(payload: ConnectRequest, request: Request, response: Response):
    _private(request, response)
    previous = request.cookies.get(broker_link.COOKIE)
    # Pause an existing paper runner before replacing its session/credentials.
    if previous:
        try:
            profile = broker_link.get_profile(previous)
            if profile.provider == "alpaca" and profile.mode == "paper":
                _call(paper_agent.stop, profile, previous)
        except ValueError:
            pass
    identifier, result = _call(
        broker_link.connect,
        payload.provider,
        payload.mode,
        payload.api_key.get_secret_value(),
        payload.api_secret.get_secret_value(),
        payload.passphrase.get_secret_value(),
        previous,
    )
    response.set_cookie(
        broker_link.COOKIE,
        identifier,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=broker_link.TTL,
        path="/api/fusion/broker",
    )
    return result


@router.get("/connection")
def connection(request: Request, response: Response):
    _private(request, response)
    try:
        return broker_link.get_profile(request.cookies.get(broker_link.COOKIE, "")).public()
    except ValueError:
        return {"connected": False, "paper_ai_available": False, "live_automation_available": False}


@router.post("/account")
def account(request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    return _call(broker_link.refresh_account, profile)


@router.post("/disconnect")
def disconnect(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    if profile.provider == "alpaca" and profile.mode == "paper":
        _call(paper_agent.stop, profile, identifier)
    broker_link.disconnect(identifier)
    response.delete_cookie(broker_link.COOKIE, path="/api/fusion/broker")
    return {
        "connected": False,
        "message": "Disconnected. Credentials are no longer retained by this session. Existing paper orders and positions remain at the venue.",
    }


class HistoryRequest(StrictModel):
    symbol: str = Field(default="SPY", pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
    years: Literal[5, 10] = 10


class UploadTrainingRequest(StrictModel):
    symbol: str = Field(min_length=1, max_length=16, pattern=r"^[A-Z][A-Z0-9./-]{0,15}$")
    years: Literal[5, 10] = 10
    bars: list[dict] = Field(min_length=500, max_length=5000)


@router.post("/train-history")
def train_history(payload: HistoryRequest, request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    rows = _call(
        lambda: broker_link.AlpacaClient(profile).historical_bars(payload.symbol, payload.years)
    )
    report = _call(
        paper_models.train_instrument,
        rows,
        payload.symbol,
        payload.years,
        source={
            "provider": "Alpaca",
            "feed": "IEX",
            "adjustment": "split",
            "rights": "Account-specific market-data agreement and entitlements; no public redistribution license inferred.",
            "kind": "provider daily OHLCV",
        },
    )
    return _call(paper_models.save_model, profile.scope, report, rows)


@router.post("/train-upload")
def train_upload(payload: UploadTrainingRequest, request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    report = _call(
        paper_models.train_instrument,
        payload.bars,
        payload.symbol,
        payload.years,
        source={
            "provider": "operator-uploaded daily OHLCV",
            "rights": "Operator-supplied data; rights/provenance not independently verified.",
        },
    )
    return _call(paper_models.save_model, profile.scope, report, payload.bars)


@router.get("/models/{identifier}")
def model(identifier: str, request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    return _call(paper_models.load_model, profile.scope, identifier)


@router.get("/models")
def models(request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    with paper_models.database() as db:
        rows = db.execute(
            "SELECT report FROM models WHERE owner=? ORDER BY rowid DESC LIMIT 10", (profile.scope,)
        ).fetchall()
    return {
        "models": [
            {key: report[key] for key in ("id", "symbol", "coverage", "status")}
            for report in (json.loads(row[0]) for row in rows)
        ]
    }


@router.get("/models/{identifier}/dataset")
def dataset(identifier: str, request: Request, response: Response):
    _private(request, response)
    profile, _ = _session(request)
    return _call(paper_models.load_dataset, profile.scope, identifier)


class StartRequest(StrictModel):
    model_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_notional: float = Field(default=1000.0, ge=1, le=1000)


@router.post("/paper-ai/start")
def start(payload: StartRequest, request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.start, profile, identifier, payload.model_id, payload.max_notional)


@router.post("/paper-ai/stop")
def stop(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.stop, profile, identifier)


@router.post("/paper-ai/tick")
def tick(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.tick, profile, identifier)


@router.get("/paper-ai")
def agent_status(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.status, profile, identifier)


@router.post("/paper-ai/reconcile")
def reconcile(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.reconcile, profile, identifier)


@router.post("/paper-ai/cancel-pending")
def cancel_pending(request: Request, response: Response):
    _private(request, response)
    profile, identifier = _session(request)
    return _call(paper_agent.reconcile, profile, identifier, cancel=True)
