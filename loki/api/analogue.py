"""Explicit local-only historical research, separate from broker-order APIs."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from core.fusion import analogue, analogue_store
from core.fusion.instrument_history import yahoo_recent_history
from loki.api.fusion import StrictModel, _call, _private_response, _require_local_action

router=APIRouter(prefix='/api/fusion/analogue',tags=['Historical analogue research'])


class ResearchRequest(StrictModel):
    symbol: Literal['ES','NQ','MES','MNQ','SPY','QQQ','AAPL','MSFT','NVDA','TSLA']
    timeframe: Literal['5m','15m','30m','1h','1d']
    years: Literal[10,15,20]=20
    horizon: int=Field(default=3,ge=1,le=12)
    commission: float=Field(default=2.5,gt=0,le=100)
    slippage_ticks: float=Field(default=1.0,ge=1,le=20)
    source: str=Field(min_length=1,max_length=200)
    bars: list[dict]=Field(min_length=600,max_length=analogue.MAX_BARS)


class ForecastRequest(StrictModel):
    bars: list[dict]=Field(min_length=20,max_length=10000)


def private(request,response):
    _require_local_action(request)
    _private_response(response)


@router.get('')
def catalog(request:Request,response:Response):
    private(request,response)
    return _call(analogue_store.catalog)


@router.post('/evaluate')
def evaluate(payload:ResearchRequest,request:Request,response:Response):
    private(request,response)
    values=payload.model_dump()
    rows=values.pop('bars')
    report,artifact=_call(analogue.build,rows,**values)
    return _call(analogue_store.save,report,artifact)


@router.get('/{identifier}')
def saved(identifier:str,request:Request,response:Response):
    private(request,response)
    report=_call(analogue_store.load,identifier)[0]
    return dict(report,readiness=analogue.readiness(report))


@router.post('/{identifier}/forecast')
def forecast(identifier:str,payload:ForecastRequest,request:Request,response:Response):
    private(request,response)
    report,artifact=_call(analogue_store.load,identifier)
    return _call(analogue.forecast,report,artifact,payload.bars)


@router.post('/{identifier}/forecast-latest')
def forecast_latest(identifier:str,request:Request,response:Response):
    private(request,response)
    report,artifact=_call(analogue_store.load,identifier)
    if artifact.get('version')!=analogue.VERSION:
        raise HTTPException(422,'This saved model is legacy; retrain it with the current model version before requesting a new estimate.')
    if artifact.get('timeframe')!='1d' or not artifact.get('source','').startswith('Yahoo Finance via yfinance'):
        raise HTTPException(422,'Automatic latest estimates require a Yahoo-trained daily equity model. Futures, intraday and other sources need a matching CSV; no substitute is used.')
    rows=_call(yahoo_recent_history,artifact['symbol'])
    result=_call(analogue.forecast,report,artifact,rows)
    return dict(result,history_source='Yahoo Finance via yfinance',timeframe='1d',bars_used=len(rows),
                data_note='Last completed daily candles, not a real-time quote or intraday forecast. Recent history is cached for up to five minutes.')
