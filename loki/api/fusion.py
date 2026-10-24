"""Unified application routes for local research and explicitly configured engines."""

from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from core.fusion.portfolio import apply_portfolio_action, stress_portfolio

router = APIRouter(prefix="/api/fusion", tags=["Loki Fusion"])
_LOCAL_TOKEN = secrets.token_urlsafe(32)


def _local_request(request: Request) -> bool:
    if os.environ.get("LOKI_FUSION_LOCAL") != "1" or os.environ.get("VERCEL") or not request.client:
        return False
    # A public reverse proxy can otherwise appear to be a loopback client.
    # Native desktop data must never be exposed through forwarded requests.
    if any(
        name in request.headers
        for name in (
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
        )
    ):
        return False
    if request.headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
        return False
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            return False
        authority = urlsplit("http://" + request.headers.get("host", ""))
        if (
            authority.hostname not in {"localhost", "127.0.0.1", "::1"}
            or authority.username is not None
            or authority.password is not None
            or authority.path
            or authority.query
            or authority.fragment
            or (authority.port is not None and not 1 <= authority.port <= 65535)
        ):
            return False
        origin = request.headers.get("origin")
        if origin:
            supplied = urlsplit(origin)
            own = urlsplit(str(request.base_url))
            if (
                supplied.scheme not in {"http", "https"}
                or supplied.username is not None
                or supplied.password is not None
                or supplied.path
                or supplied.query
                or supplied.fragment
            ):
                return False
            supplied_port = supplied.port or (443 if supplied.scheme == "https" else 80)
            own_port = own.port or (443 if own.scheme == "https" else 80)
            if (supplied.scheme, supplied.hostname, supplied_port) != (
                own.scheme,
                own.hostname,
                own_port,
            ):
                return False
    except (ValueError, TypeError):
        return False
    return True


def _require_local_action(request: Request):
    token = request.headers.get("x-loki-local-token", "")
    if (
        not _local_request(request)
        or len(token) != len(_LOCAL_TOKEN)
        or not hmac.compare_digest(token.encode("utf-8"), _LOCAL_TOKEN.encode("ascii"))
    ):
        raise HTTPException(
            403, "Native engine access requires the local Loki launcher and its session token"
        )


def _private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Origin, X-Loki-Local-Token"


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ConnectionError, TimeoutError, OSError) as exc:
        raise HTTPException(
            503,
            "The configured local engine is unavailable; check its installation and service status",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class QuantRequest(StrictModel):
    bars: list[dict] = Field(min_length=61, max_length=5000)
    symbol: str = Field(default="BTC/USDT", min_length=1, max_length=40)
    periods_per_year: int = Field(default=365, ge=1, le=525600)
    config: dict = Field(default_factory=dict)


@router.post("/learn-history")
def learn_history():
    from core.fusion.history import public_history
    from core.fusion.learning import train_research

    dataset = _call(public_history)
    return _call(train_research, dataset["observations"], source=dataset["source"])


@router.post("/quant")
def quant(payload: QuantRequest):
    from core.fusion.quant import analyze_factors, run_shadow_replay

    config = dict(payload.config, periods_per_year=payload.periods_per_year)
    return {
        "analysis": _call(
            analyze_factors,
            payload.bars,
            symbol=payload.symbol,
            periods_per_year=payload.periods_per_year,
        ),
        "replay": _call(run_shadow_replay, payload.bars, config, symbol=payload.symbol),
    }


@router.post("/pullback")
def pullback(payload: QuantRequest):
    from core.fusion.reversion import evaluate_pullback

    settings = dict(payload.config, periods_per_year=payload.periods_per_year)
    return _call(evaluate_pullback, payload.bars, settings, symbol=payload.symbol)


class CouncilRequest(StrictModel):
    bars: list[dict] = Field(min_length=61, max_length=5000)
    symbol: str = Field(default="BTC/USDT", min_length=1, max_length=40)
    portfolio: dict | None = None
    research: dict | None = None
    config: dict = Field(default_factory=dict)
    miro_report_id: str | None = Field(
        default=None, min_length=8, max_length=110, pattern=r"^report_[A-Za-z0-9_-]+$"
    )
    miro_reviewed: bool = False
    news_evidence: dict | None = Field(
        default=None,
        description="Desk news agent JSON packet (bounded); council validates it strictly.",
    )


@router.post("/council")
def council(payload: CouncilRequest, request: Request, response: Response):
    from core.fusion.council import build_council_report

    native = None
    if payload.miro_report_id:
        from core.fusion.miro_native import load_report
        from core.fusion.quant import _symbol

        _require_local_action(request)
        _private_response(response)
        native = _call(load_report, payload.miro_report_id, _call(_symbol, payload.symbol))
    return _call(
        build_council_report,
        payload.bars,
        symbol=payload.symbol,
        portfolio=payload.portfolio,
        research=payload.research,
        config=payload.config,
        miro_research=native,
        miro_reviewed=payload.miro_reviewed,
        news_evidence=payload.news_evidence,
    )


class NarrativeRequest(StrictModel):
    seed_text: str = Field(min_length=1, max_length=100000)
    question: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=120)
    rounds: int = Field(default=6, ge=2, le=12)
    agents_per_family: int = Field(default=3, ge=1, le=3)
    save: bool = True


@router.post("/narrative")
def narrative(payload: NarrativeRequest, request: Request, response: Response):
    """Run the local narrative engine (no LLM, no Zep, no OASIS).

    Running the simulation is pure text statistics and stays public. Saving
    the resulting MiroFish-shaped report artifact requires the launcher's
    session token, because it writes inside the native data directory.
    """
    from core.fusion.narrative import analyze_narrative, save_report

    report = _call(
        analyze_narrative,
        payload.seed_text,
        question=payload.question,
        rounds=payload.rounds,
        agents_per_family=payload.agents_per_family,
        title=payload.title,
    )
    result = dict(report)
    result["saved"] = None
    if payload.save:
        _require_local_action(request)
        _private_response(response)
        result["saved"] = {
            "report_id": report["report_id"],
            "path": str(_call(save_report, report)),
        }
    return result


class PortfolioRequest(StrictModel):
    action: str = Field(default="snapshot", max_length=20)
    state: dict | None = None
    symbol: str | None = Field(default=None, max_length=32)
    price: float | None = Field(default=None, gt=0, le=1e12)
    quantity: float | None = Field(default=None, gt=0, le=1e12)
    stop_loss: float | None = Field(default=None, gt=0, le=1e12)
    marks: dict[str, float] = Field(default_factory=dict)
    initial_capital: float | None = Field(default=None, gt=0, le=1e12)
    fee_bps: float | None = Field(default=None, ge=0, le=1000)
    slippage_bps: float | None = Field(default=None, ge=0, le=1000)
    quote_currency: str | None = Field(default=None, min_length=2, max_length=12)
    report_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)


@router.get("/portfolio")
def portfolio_snapshot():
    return apply_portfolio_action({"action": "snapshot"})


@router.post("/portfolio")
def portfolio(payload: PortfolioRequest):
    return _call(apply_portfolio_action, payload.model_dump(exclude_none=True))


class ScenarioRequest(StrictModel):
    portfolio: dict | None = None
    shock_pct: float = Field(default=-10, ge=-99, le=500)
    volatility_multiplier: float = Field(default=1, ge=0.1, le=10)


class SimulatedMarketRequest(StrictModel):
    action: Literal["create", "snapshot", "advance", "order", "cancel", "council"] = "snapshot"
    state: dict | None = None
    seed: int = Field(default=42, ge=0, le=2147483647)
    scenario: Literal["balanced", "uptrend", "downtrend", "range", "volatile", "crash"] = "balanced"
    initial_capital: float = Field(default=10000, gt=0, le=1e9)
    steps: int = Field(default=1, ge=1, le=30)
    symbol: Literal["BTC/USD", "ETH/USD", "SOL/USD"] = "BTC/USD"
    side: Literal["buy", "sell"] | None = None
    order_type: Literal["market", "limit"] = "market"
    quantity: float | None = Field(default=None, gt=0, le=1e9)
    limit_price: float | None = Field(default=None, gt=0, le=1e9)
    stop_loss: float | None = Field(default=None, gt=0, le=1e9)
    order_id: str | None = Field(default=None, max_length=32)


@router.post("/simulated-market")
def simulated_market(payload: SimulatedMarketRequest):
    from core.fusion.simulated_market import act

    return _call(act, payload.model_dump(exclude_none=True))


@router.post("/scenario")
def scenario(payload: ScenarioRequest):
    return _call(
        stress_portfolio, payload.portfolio, payload.shock_pct, payload.volatility_multiplier
    )


@router.get("/capabilities")
def capabilities(request: Request, response: Response):
    from core.fusion.external import FinceptAdapter, MiroFishAdapter
    from core.fusion.quant import PROVENANCE

    fincept = _call(lambda: FinceptAdapter.from_env().status())
    mirofish = _call(lambda: MiroFishAdapter.from_env().status(probe=False))
    result = {
        "application": "Loki Fusion",
        "mode": "paper_research",
        "local_actions_enabled": _local_request(request),
        "components": [
            {
                "id": "loki",
                "name": "Loki",
                "status": "ready",
                "license": "Project license",
                "capabilities": [
                    "walk_forward_research",
                    "risk_sizing",
                    "grounded_chat",
                    "paper_journal",
                ],
            },
            {
                "id": "vibe",
                "name": "Vibe-Trading",
                "status": "ready",
                "license": "MIT",
                "capabilities": ["factor_analytics", "shadow_replay"],
                "provenance": PROVENANCE,
            },
            {
                "id": "autohedge",
                "name": "AutoHedge",
                "status": "ready",
                "license": "MIT",
                "capabilities": ["director_quant_risk_execution_review"],
                "reason": "Local rules implement the review roles; no external LLM is implied.",
            },
            dict(
                fincept,
                id="fincept",
                name="Fincept Terminal",
                status=fincept.get("status", fincept.get("state", "unconfigured")),
            ),
            dict(
                mirofish,
                id="mirofish",
                name="MiroFish",
                status=mirofish.get("status", mirofish.get("state", "unconfigured")),
            ),
        ],
        "live_trading_enabled": False,
        "data_policy": "Paper state is supplied by the browser; external engines require explicit host configuration.",
    }
    if result["local_actions_enabled"]:
        result["local_token"] = _LOCAL_TOKEN
    _private_response(response)
    return result


@router.get("/mirofish/status")
def mirofish_status(request: Request, response: Response):
    from core.fusion.external import MiroFishAdapter

    _require_local_action(request)
    _private_response(response)
    return _call(lambda: MiroFishAdapter.from_env().status())


@router.get("/fincept/status")
def fincept_status(request: Request, response: Response):
    from core.fusion.external import FinceptAdapter

    _require_local_action(request)
    _private_response(response)
    return _call(lambda: FinceptAdapter.from_env().status())


@router.get("/real/status")
def real_status(request: Request, response: Response):
    from core.fusion.real_account import status

    _require_local_action(request)
    _private_response(response)
    return _call(status)


@router.get("/native-mirofish/status")
def native_mirofish_status(request: Request, response: Response):
    from core.fusion.miro_native import native_status

    _require_local_action(request)
    _private_response(response)
    return _call(native_status)


@router.get("/native-mirofish/report/{identifier}")
def native_mirofish_report(
    identifier: str,
    request: Request,
    response: Response,
    symbol: str = Query(default="BTC/USDT", min_length=1, max_length=40),
):
    from core.fusion.miro_native import load_report
    from core.fusion.quant import _symbol

    _require_local_action(request)
    _private_response(response)
    return _call(load_report, identifier, _call(_symbol, symbol))


@router.post("/real/account")
def real_account(request: Request, response: Response):
    from core.fusion.real_account import account_snapshot

    _require_local_action(request)
    _private_response(response)
    return _call(account_snapshot)


class RealOrderRequest(StrictModel):
    symbol: Literal["BTC/USD", "ETH/USD", "SOL/USD"]
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, le=1e9)
    limit_price: float = Field(gt=0, le=1e9)


class RealOrderAction(StrictModel):
    identifier: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmation: str = Field(min_length=1, max_length=40)


@router.post("/real/orders/preview")
def real_order_preview(payload: RealOrderRequest, request: Request, response: Response):
    from core.fusion.real_execution import preview_order

    _require_local_action(request)
    _private_response(response)
    order = dict(payload.model_dump(), notional=None, order_type="limit", time_in_force="gtc")
    return _call(preview_order, order)


@router.get("/real/orders")
def real_orders(request: Request, response: Response):
    from core.fusion.real_execution import list_orders

    _require_local_action(request)
    _private_response(response)
    return _call(list_orders)


@router.post("/real/orders/submit")
def real_order_submit(payload: RealOrderAction, request: Request, response: Response):
    from core.fusion.real_execution import submit_order

    _require_local_action(request)
    _private_response(response)
    return _call(submit_order, payload.identifier, payload.confirmation)


@router.post("/real/orders/cancel")
def real_order_cancel(payload: RealOrderAction, request: Request, response: Response):
    from core.fusion.real_execution import cancel_order

    _require_local_action(request)
    _private_response(response)
    return _call(cancel_order, payload.identifier, payload.confirmation)


@router.post("/real/orders/{identifier}/reconcile")
def real_order_reconcile(identifier: str, request: Request, response: Response):
    from core.fusion.real_execution import reconcile_order

    _require_local_action(request)
    _private_response(response)
    return _call(reconcile_order, identifier)


@router.get("/mirofish/{collection}")
def mirofish_collection(collection: str, request: Request, response: Response):
    from core.fusion.external import MiroFishAdapter

    _require_local_action(request)
    _private_response(response)
    engine = _call(MiroFishAdapter.from_env)
    calls = {
        "projects": engine.projects,
        "simulations": engine.simulations,
        "reports": engine.reports,
    }
    if collection not in calls:
        raise HTTPException(404, "Unknown MiroFish resource")
    return _call(calls[collection])


@router.get("/mirofish/{resource}/{identifier}")
def mirofish_resource(
    resource: str,
    identifier: str,
    request: Request,
    response: Response,
    task_id: str | None = Query(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
):
    from core.fusion.external import MiroFishAdapter

    _require_local_action(request)
    _private_response(response)
    engine = _call(MiroFishAdapter.from_env)
    calls = {
        "project": engine.project,
        "graph": engine.graph,
        "task": engine.task,
        "simulation": engine.simulation,
        "run-status": engine.run_status,
        "report": engine.report,
        "report-for-simulation": engine.report_for_simulation,
        "preparation-status": engine.preparation_status,
        "report-status": engine.report_status,
    }
    if resource not in calls:
        raise HTTPException(404, "Unknown MiroFish resource")
    if resource in {"preparation-status", "report-status"}:
        return _call(calls[resource], identifier, task_id)
    return _call(calls[resource], identifier)


class MiroJobRequest(StrictModel):
    action: Literal[
        "create_project",
        "build_graph",
        "create_simulation",
        "prepare_simulation",
        "start_simulation",
        "stop_simulation",
        "generate_report",
        "chat",
    ]
    project_id: str | None = Field(default=None, max_length=100)
    graph_id: str | None = Field(default=None, max_length=100)
    simulation_id: str | None = Field(default=None, max_length=100)
    seed_text: str | None = Field(default=None, max_length=100000)
    title: str | None = Field(default=None, max_length=120)
    requirements: str | None = Field(default=None, max_length=4000)
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    max_rounds: int = Field(default=10, ge=1, le=40)


@router.post("/mirofish/jobs")
def mirofish_job(payload: MiroJobRequest, request: Request, response: Response):
    from core.fusion.external import MiroFishAdapter

    _require_local_action(request)
    _private_response(response)
    engine = _call(MiroFishAdapter.from_env)
    if payload.action == "create_project":
        return _call(engine.create_project, payload.title, payload.seed_text, payload.requirements)
    if payload.action == "build_graph":
        return _call(engine.build_graph, payload.project_id)
    if payload.action == "create_simulation":
        return _call(engine.create_simulation, payload.project_id, payload.graph_id)
    if payload.action == "prepare_simulation":
        return _call(engine.prepare_simulation, payload.simulation_id)
    if payload.action == "start_simulation":
        return _call(engine.start_simulation, payload.simulation_id, payload.max_rounds)
    if payload.action == "stop_simulation":
        return _call(engine.stop_simulation, payload.simulation_id)
    if payload.action == "generate_report":
        return _call(engine.generate_report, payload.simulation_id)
    if payload.action == "chat":
        return _call(engine.chat, payload.simulation_id, payload.message)
    raise HTTPException(422, "Unknown MiroFish job action")


class FinceptRequest(StrictModel):
    returns: list[Annotated[list[float], Field(min_length=20, max_length=2000)]] = Field(
        min_length=1, max_length=20
    )
    weights: list[float] = Field(min_length=1, max_length=20)
    portfolio_value: float = Field(default=10000, gt=0, le=1e12)
    confidence: float = Field(default=0.95, gt=0.5, lt=1)


@router.post("/fincept/analyze")
def fincept_analyze(payload: FinceptRequest, request: Request, response: Response):
    from core.fusion.external import FinceptAdapter

    _require_local_action(request)
    _private_response(response)
    if payload.confidence != 0.95:
        raise HTTPException(
            422,
            "The licensed native analytics use their documented confidence levels; this adapter accepts 0.95",
        )
    returns = (
        payload.returns[0]
        if len(payload.returns) == 1
        else {f"asset_{index + 1}": row for index, row in enumerate(payload.returns)}
    )
    return _call(
        _call(FinceptAdapter.from_env).risk,
        returns,
        weights=payload.weights,
        portfolio_value=payload.portfolio_value,
    )


# ---------------------------------------------------------------------------
# Public trained-strategy book: the verified out-of-sample evidence shipped
# with the repo. Stateless and read-only — it touches no engine state and
# requires no launcher session; it only reads the bundled snapshot.
# ---------------------------------------------------------------------------
@router.get("/research-book")
def research_book(response: Response):
    from loki_v8.train import load_report as _load_trained_report

    report = _load_trained_report()
    _private_response(response)
    if not report:
        return {
            "generated_at": None,
            "period": None,
            "evaluation_protocol": None,
            "consensus_support_pct": None,
            "symbols": [],
        }
    summary = []
    for entry in report.get("symbols", []):
        if not entry.get("ok"):
            continue
        dev = entry.get("validation_metrics") or {}
        holdout = entry.get("final_holdout") or {}
        metrics = holdout.get("metrics") or {}
        summary.append(
            {
                "symbol": entry.get("symbol"),
                "win_rate_pct": dev.get("win_rate_pct"),
                "profitable_months_pct": dev.get("month_profit_rate_pct"),
                "profit_factor": dev.get("profit_factor"),
                "trades": dev.get("trades"),
                "final_holdout": {
                    "start": holdout.get("start"),
                    "end": holdout.get("end"),
                    "win_rate_pct": metrics.get("win_rate_pct"),
                    "profitable_months_pct": metrics.get("month_profit_rate_pct"),
                    "profit_factor": metrics.get("profit_factor"),
                    "trades": metrics.get("trades"),
                },
            }
        )
    consensus = report.get("consensus") or {}
    return {
        "generated_at": report.get("generated_at"),
        "period": report.get("period"),
        "evaluation_protocol": report.get("evaluation_protocol"),
        "consensus_support_pct": consensus.get("support_pct"),
        "symbols": summary,
    }
