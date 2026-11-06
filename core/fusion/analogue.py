"""Frozen historical-analogue forecasts. Research only; no broker authority.

Training prototypes and scaling use earlier dates only. Label horizons are
purged at split, session and contract boundaries. Evaluation uses bounded,
non-overlapping samples, not a simulated leveraged portfolio.
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re

import numpy as np

from core.strategy_lab import Bar, validate_bars

VERSION = 'loki_historical_analogue_v3'
LOOKBACK, NEIGHBORS = 20, 31
MAX_BARS, MAX_REFERENCES, MAX_EVALUATIONS = 500000, 4096, 512
FEATURES = ['return_1','return_3','return_5','return_10','return_19',
            'mean_5','mean_19','volatility_19','range_20','body','candle_range',
            'volume_relative','range_location','volatility_ratio','clock_sin','clock_cos']
MINUTES = {'5m':5,'15m':15,'30m':30,'1h':60,'1d':1440}
CALIBRATION_WEIGHTS = (0.0,0.25,0.5,0.75,1.0)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    kind: str
    multiplier: float
    tick: float


INSTRUMENTS = {s: Instrument(s,'equity',1.0,0.01) for s in ('SPY','QQQ','AAPL','MSFT','NVDA','TSLA')}
INSTRUMENTS.update({s:Instrument(s,'future',m,0.25) for s,m in (('ES',50.0),('NQ',20.0),('MES',5.0),('MNQ',2.0))})


def _thin(indices, cap, gap):
    if len(indices) == 0:
        return []
    stride = max(1, math.ceil(len(indices) / cap))
    result: list[int] = []
    for index in indices[::stride]:
        index = int(index)
        if not result or index - result[-1] >= gap:
            result.append(index)
    return result


def prepare(rows, symbol, timeframe, years, horizon, *, require_coverage=True):
    if symbol not in INSTRUMENTS or timeframe not in MINUTES or years not in (10,15,20):
        raise ValueError('Choose a supported instrument, timeframe, and 10/15/20 years')
    if isinstance(horizon,bool) or not isinstance(horizon,int) or not 1 <= horizon <= 12:
        raise ValueError('Forecast horizon must be 1–12 bars')
    minimum,maximum=(600,MAX_BARS) if require_coverage else (LOOKBACK,10000)
    if not isinstance(rows,list) or not minimum <= len(rows) <= maximum:
        raise ValueError(f'Supply {minimum}–{maximum} completed OHLCV candles')
    instrument = INSTRUMENTS[symbol]
    intraday = timeframe != '1d'
    bars: list[Bar] = []
    segments, segment = [], 0
    previous_session = previous_contract = None
    for offset in range(0,len(rows),10000):
        chunk = validate_bars(rows[offset:offset+10000])
        for local,bar in enumerate(chunk):
            row = rows[offset+local]
            raw_stamp = str(row['timestamp'])
            if intraday and ('T' not in raw_stamp or not re.search(r'(Z|[+-]\d\d:\d\d)$',raw_stamp)):
                raise ValueError('Intraday timestamps must be timezone-aware ISO8601 bar-close timestamps')
            if bar.timestamp >= datetime.now(timezone.utc) or (not intraday and bar.timestamp.date() >= datetime.now(timezone.utc).date()):
                raise ValueError('Current/incomplete or future candles cannot train the model')
            if max(bar.open,bar.high,bar.low,bar.close) > 1e9 or min(bar.open,bar.high,bar.low,bar.close)<1e-6 or bar.volume > 1e15:
                raise ValueError('OHLCV values exceed supported instrument bounds')
            session = row.get('session')
            if intraday and (not isinstance(session,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',session)):
                raise ValueError('Intraday rows need an exchange trading-session date in session')
            if intraday:
                try:
                    date.fromisoformat(session)
                except ValueError:
                    raise ValueError('Invalid exchange trading-session date') from None
            contract = row.get('contract')
            if instrument.kind == 'future':
                match=re.fullmatch(re.escape(symbol)+r'[FGHJKMNQUVXZ](\d{2}|\d{4})',contract) if isinstance(contract,str) else None
                if not match:
                    raise ValueError('Futures rows need the actual root/month/year contract, for example ESZ2020; continuous adjusted tickers are not accepted')
                contract_year=int(match[1])+(2000 if len(match[1])==2 else 0)
                if not 0<=contract_year-bar.timestamp.year<=2:
                    raise ValueError('Futures contract year is inconsistent with the bar date; do not label an entire continuous history as one contract')
            if bars:
                seconds = (bar.timestamp-bars[-1].timestamp).total_seconds()
                if seconds <= 0:
                    raise ValueError('All candles must have unique, ascending timestamps, including file chunk boundaries')
                if not intraday and bar.timestamp.date() == bars[-1].timestamp.date():
                    raise ValueError('Daily history must contain at most one candle per date')
                discontinuity = (abs(seconds-MINUTES[timeframe]*60)>1 if intraday else seconds>7*86400)
                if discontinuity or (intraday and session != previous_session) or contract != previous_contract:
                    segment += 1
            bars.append(bar)
            segments.append(segment)
            previous_session,previous_contract = session,contract
    coverage=(bars[-1].timestamp-bars[0].timestamp).total_seconds()/(365.25*86400)
    if require_coverage and coverage < years-0.2:
        raise ValueError(f'Actual coverage is {coverage:.2f} years, not the requested {years}; no padding or synthetic substitutes are used')
    if require_coverage and coverage > years+0.25:
        raise ValueError('Upload only the selected historical window; extra years must not silently change the split')
    observed_days=len({row['session'] for row in rows}) if intraday else len({bar.timestamp.date() for bar in bars})
    if require_coverage and observed_days<years*170:
        raise ValueError('Too few observed trading days/sessions for the requested history; a sparse date span is not complete history')
    return bars,np.asarray(segments),instrument,coverage


def vector(bars,index,intraday):
    window=bars[index-LOOKBACK+1:index+1]
    closes=np.asarray([b.close for b in window])
    returns=np.diff(np.log(closes))
    high,low=max(b.high for b in window),min(b.low for b in window)
    bar=window[-1]
    vol=float(np.std(returns))
    average_volume=sum(b.volume for b in window)/LOOKBACK
    angle=2*math.pi*(bar.timestamp.hour*60+bar.timestamp.minute)/1440 if intraday else 0.0
    result=[float(np.log(closes[-1])-np.log(closes[-1-k])) for k in (1,3,5,10,19)]
    result += [float(np.mean(returns[-5:])),float(np.mean(returns)),vol,
               (high-low)/bar.close,(bar.close-bar.open)/bar.open,(bar.high-bar.low)/bar.open,
               bar.volume/average_volume-1 if average_volume else 0.0,
               (bar.close-low)/(high-low) if high>low else 0.5,
               float(np.std(returns[-5:]))/vol if vol else 1.0,math.sin(angle),math.cos(angle)]
    if not all(math.isfinite(x) for x in result):
        raise ValueError('Feature values are non-finite')
    return result


def cost(price,instrument,commission,slippage_ticks,multiple=1):
    # Currency cost per one share/contract, both entry and exit.
    return multiple*(2*commission+2*slippage_ticks*instrument.tick*instrument.multiplier)


def regime(features,volatility_cutoff):
    return ('up' if features[4]>=0 else 'down')+('/high_volatility' if features[7]>=volatility_cutoff else '/low_volatility')


def reference_pool(artifact,features):
    name=regime(features,artifact['regime_volatility_cutoff'])
    members=artifact['regime_members'].get(name,[])
    if len(members)>=NEIGHBORS*3:
        return name,np.asarray(members,dtype=int)
    return 'all_regimes',np.arange(len(artifact['standardized_reference']))


def neighbors(artifact,features):
    x=(np.asarray(features)-np.asarray(artifact['means']))/np.asarray(artifact['scales'])
    reference=np.asarray(artifact['standardized_reference'])
    pool_name,pool=reference_pool(artifact,features)
    distances=np.sqrt(np.mean((reference[pool]-x)**2,axis=1))
    positions=np.argsort(distances,kind='stable')[:NEIGHBORS]
    chosen=pool[positions]
    outcomes=np.asarray(artifact['reference_returns'])[chosen]
    probability=(int(np.sum(outcomes>0))+1)/(len(outcomes)+2)
    base=artifact['training_up_frequency']
    alpha=artifact.get('calibration',{}).get('selected_weight',1.0)
    estimate=base+alpha*(probability-base)
    quantiles=np.quantile(outcomes,[0.1,0.25,0.5,0.75,0.9]).tolist()
    return {'up_frequency_smoothed':probability,'return_quantiles':dict(zip(('p10','p25','p50','p75','p90'),quantiles)),
            'estimated_up_probability':estimate,'calibration_weight':alpha,'reference_regime':pool_name,
            'mean_neighbor_distance':float(np.mean(distances[positions])),
            'within_training_distance':bool(np.mean(distances[positions])<=artifact['distance_limits'][pool_name]),
            'analogues':[dict(artifact['reference_examples'][int(i)],distance=float(distances[int(p)])) for i,p in zip(chosen[:5],positions[:5])]}


def direction(forecast,price,instrument,commission,slippage_ticks):
    if not forecast['within_training_distance']:
        return 0
    hurdle=cost(price,instrument,commission,slippage_ticks,2)/(price*instrument.multiplier)
    q=forecast['return_quantiles']
    probability=forecast.get('estimated_up_probability',forecast.get('up_frequency_smoothed',0.5))
    if q['p25']>hurdle and probability>=0.6:
        return 1
    if q['p75'] < -hurdle and probability<=0.4:
        return -1
    return 0


def evaluate_period(artifact,bars,indices,instrument,commission,slippage_ticks,horizon,intraday):
    probabilities,raw_probabilities,labels,pnls,stress=[],[],[],[],[]
    for index in indices:
        forecast=neighbors(artifact,vector(bars,index,intraday))
        entry,exit_=bars[index+1].open,bars[index+horizon].close
        probabilities.append(forecast.get('estimated_up_probability',forecast['up_frequency_smoothed']))
        raw_probabilities.append(forecast['up_frequency_smoothed'])
        labels.append(int(exit_>entry))
        # Entry is next-bar information. Signal eligibility must use the last
        # completed close, exactly as the live research forecast does.
        side=direction(forecast,bars[index].close,instrument,commission,slippage_ticks)
        if side:
            gross=side*(exit_-entry)*instrument.multiplier
            pnls.append(gross-cost(entry,instrument,commission,slippage_ticks))
            stress.append(gross-cost(entry,instrument,commission,slippage_ticks,2))
    base=artifact['training_up_frequency']
    return {'examples':len(indices),'start':bars[indices[0]].timestamp.isoformat(),
            'end':bars[indices[-1]+horizon].timestamp.isoformat(),
            'direction_accuracy':float(np.mean([(p>=0.5)==bool(y) for p,y in zip(probabilities,labels)])),
            'brier_score':float(np.mean([(p-y)**2 for p,y in zip(probabilities,labels)])),
            'uncalibrated_brier_score':float(np.mean([(p-y)**2 for p,y in zip(raw_probabilities,labels)])),
            'baseline_brier_score':float(np.mean([(base-y)**2 for y in labels])),
            'training_majority_baseline_accuracy':float(np.mean([(base>=0.5)==bool(y) for y in labels])),
            'signals':len(pnls),'unit_net_pnl':sum(pnls),'unit_stress_pnl':sum(stress),
            'average_unit_net_pnl':float(np.mean(pnls)) if pnls else None,
            'metric_scope':'Sampled non-overlapping one-share/one-contract outcomes, not account return or a margin-aware portfolio backtest'}


def fit_calibration(artifact,bars,indices,horizon,intraday):
    raw=[neighbors(artifact,vector(bars,index,intraday))['up_frequency_smoothed'] for index in indices]
    labels=[int(bars[index+horizon].close>bars[index+1].open) for index in indices]
    base=artifact['training_up_frequency']
    trials=[{'weight':alpha,'brier_score':float(np.mean([(base+alpha*(p-base)-y)**2 for p,y in zip(raw,labels)]))}
            for alpha in CALIBRATION_WEIGHTS]
    chosen=min(trials,key=lambda row:(row['brier_score'],row['weight']))
    return {'selected_weight':chosen['weight'],'examples':len(indices),'trials':trials,
            'start':bars[indices[0]].timestamp.isoformat(),'labels_through':bars[indices[-1]+horizon].timestamp.isoformat(),
            'method':'Predeclared shrinkage weights toward the frozen training up-frequency; earlier calibration dates only'}


def readiness(report):
    reasons=[]
    if report.get('version')!=VERSION or report.get('status')=='legacy_research_retrain_required':
        reasons.append('This is a legacy research report; retrain the current model version.')
    for name in ('validation','test'):
        metrics=report.get(name,{})
        count=metrics.get('signals')
        if not isinstance(count,int) or isinstance(count,bool) or count<20:
            reasons.append(f'{name.title()}: fewer than 20 qualifying signals; positive examples alone are insufficient.')
        stress=metrics.get('unit_stress_pnl')
        if not isinstance(stress,(int,float)) or isinstance(stress,bool) or not math.isfinite(stress) or stress<=0:
            reasons.append(f'{name.title()}: sampled unit P&L must be positive at doubled costs.')
        score,baseline=metrics.get('brier_score'),metrics.get('baseline_brier_score')
        if not all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) for value in (score,baseline)) or score>=baseline:
            reasons.append(f'{name.title()}: probability error must beat the frozen training-frequency baseline.')
    return {'research_checks_passed':not reasons,'reasons':reasons,'broker_execution_enabled':False,
            'note':'A directional probability estimate is not a trade signal. Even passing research checks does not establish future profitability.'}


def build(rows,*,symbol,timeframe,years,horizon=3,commission=0.01,slippage_ticks=1.0,source='Operator CSV'):
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in (commission,slippage_ticks)):
        raise ValueError('Costs must be finite and nonnegative')
    if not 0<commission<=100 or not 1<=slippage_ticks<=20:
        raise ValueError('Commission must be positive and at most 100 per side/unit; slippage is 1–20 ticks per side')
    if not isinstance(source,str) or not 1<=len(source)<=200:
        raise ValueError('Provide a source label of 1–200 characters, without credentials')
    bars,segments,instrument,coverage=prepare(rows,symbol,timeframe,years,horizon)
    if instrument.kind=='future' and commission<0.5:
        raise ValueError('Futures commission must include exchange/broker costs; use at least 0.50 per side/contract')
    n=len(bars)
    cut1,calibration_end,cut2=int(n*0.6),int(n*0.7),int(n*0.8)
    valid=np.flatnonzero((segments[LOOKBACK-1:n-horizon]==segments[:n-horizon-LOOKBACK+1]) &
                         (segments[LOOKBACK-1:n-horizon]==segments[LOOKBACK-1+horizon:n]))+LOOKBACK-1
    train=_thin(valid[valid+horizon<cut1],MAX_REFERENCES,horizon)
    calibration=_thin(valid[(valid>=cut1+horizon)&(valid+horizon<calibration_end)],MAX_EVALUATIONS,horizon)
    validation=_thin(valid[(valid>=calibration_end+horizon)&(valid+horizon<cut2)],MAX_EVALUATIONS,horizon)
    test=_thin(valid[valid>=cut2+horizon],MAX_EVALUATIONS,horizon)
    if len(train)<100 or len(calibration)<50 or len(validation)<50 or len(test)<50:
        raise ValueError('Need at least 100 training, 50 calibration, 50 validation and 50 test examples after session/contract/gap purging')
    x=np.asarray([vector(bars,i,timeframe!='1d') for i in train])
    means=x.mean(axis=0)
    scales=x.std(axis=0)
    scales[scales<1e-8]=1.0
    z=(x-means)/scales
    returns=[bars[i+horizon].close/bars[i+1].open-1 for i in train]
    examples=[{'signal_at':bars[i].timestamp.isoformat(),'entry_at':bars[i+1].timestamp.isoformat(),
               'outcome_at':bars[i+horizon].timestamp.isoformat(),'gross_return':r,
               'contract':rows[i].get('contract')} for i,r in zip(train,returns)]
    volatility_cutoff=float(np.median(x[:,7]))
    regime_members: dict[str, list[int]] = {}
    for index,features in enumerate(x):
        regime_members.setdefault(regime(features,volatility_cutoff),[]).append(index)
    distance_limits={}
    pools={'all_regimes':list(range(len(z))),**{key:value for key,value in regime_members.items() if len(value)>=NEIGHBORS*3}}
    for name,members in pools.items():
        pool=np.asarray(members)
        samples=[]
        for position in np.linspace(0,len(pool)-1,min(64,len(pool)),dtype=int):
            distances=np.sqrt(np.mean((z[pool]-z[pool[position]])**2,axis=1))
            distances[position]=np.inf
            samples.append(float(np.mean(np.sort(distances)[:NEIGHBORS])))
        distance_limits[name]=float(np.quantile(samples,0.95))
    artifact={'version':VERSION,'symbol':symbol,'timeframe':timeframe,'horizon':horizon,'requested_years':years,'source':source,
              'specification':{'lookback':LOOKBACK,'neighbors':NEIGHBORS,'reference_cap':MAX_REFERENCES,
                               'evaluation_cap':MAX_EVALUATIONS,'split':[0.6,0.7,0.8],
                               'cost_hurdle_price':'completed_signal_close_not_future_open',
                               'direction_rule':'25th/75th return quantile exceeds doubled costs and calibrated direction probability clears 60/40',
                               'calibration_weights':list(CALIBRATION_WEIGHTS)},
              'features':FEATURES,'means':means.tolist(),'scales':scales.tolist(),
              'standardized_reference':z.tolist(),'reference_returns':returns,
              'reference_examples':examples,'distance_limits':distance_limits,
              'regime_volatility_cutoff':volatility_cutoff,'regime_members':regime_members,
              'training_up_frequency':sum(r>0 for r in returns)/len(returns),
              'training_labels_through':examples[-1]['outcome_at'],
              'instrument':asdict(instrument),'commission_per_side':commission,'slippage_ticks_per_side':slippage_ticks}
    artifact['calibration']=fit_calibration(artifact,bars,calibration,horizon,timeframe!='1d')
    artifact['fitted_labels_through']=artifact['calibration']['labels_through']
    validation_metrics=evaluate_period(artifact,bars,validation,instrument,commission,slippage_ticks,horizon,timeframe!='1d')
    test_metrics=evaluate_period(artifact,bars,test,instrument,commission,slippage_ticks,horizon,timeframe!='1d')
    def passes(metrics):
        return metrics['signals']>=20 and metrics['unit_stress_pnl']>0 and metrics['brier_score']<metrics['baseline_brier_score']
    eligible=passes(validation_metrics) and passes(test_metrics)
    latest=None
    if segments[-1]==segments[-LOOKBACK]:
        latest=neighbors(artifact,vector(bars,n-1,timeframe!='1d'))
        side=direction(latest,bars[-1].close,instrument,commission,slippage_ticks)
        latest.update(as_of=bars[-1].timestamp.isoformat(),decision=('LONG' if side==1 else 'SHORT') if eligible and side else 'WAIT',
                      reason='Research-only; no broker execution. Eligibility and analogue uncertainty both gate a directional view.')
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    artifact_hash=hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    report={'id':hashlib.sha256((digest+artifact_hash).encode()).hexdigest(),'version':VERSION,
            'symbol':symbol,'timeframe':timeframe,'horizon_bars':horizon,'requested_years':years,
            'coverage':{'start':bars[0].timestamp.isoformat(),'end':bars[-1].timestamp.isoformat(),'years':coverage,'bars':n},
            'source':source,'data_sha256':digest,'artifact_sha256':artifact_hash,
            'training':{'references':len(train),'labels_through':artifact['training_labels_through']},
            'calibration':artifact['calibration'],
            'validation':validation_metrics,'test':test_metrics,'latest':latest,
            'status':'experimental_research_candidate' if eligible else 'insufficient_predictive_evidence',
            'broker_execution_enabled':False,'future_profitability_proven':False,
            'limitations':[
                'Historical analogues estimate distributions, not certain next prices. Smoothed up-frequency is not a calibrated probability.',
                'Regime pools use training-only trend and volatility thresholds. Sparse pools fall back to all regimes. Probability shrinkage uses a separate 10% calibration block, not validation/test labels.',
                'Parameters are fixed. Scaling, prototypes and distance threshold use training dates only; horizons are purged at splits, gaps, sessions and contract rolls.',
                'Reference/evaluation caps sample long histories deterministically. Reported P&L is per-unit sampled opportunities, not a fully executed portfolio, margin simulation, or investment return.',
                'Futures need licensed unadjusted actual-contract bars and exchange session labels. Windows cannot cross a roll. Commission, spread, slippage, margin, liquidation and execution need independent validation.',
                'Intraday labels stay in the supplied session. Timestamps must denote completed bar closes with timezone. Daily history does not validate day trading.',
                'Recent dates in this project have already been inspected; do not call reused evaluation dates a fresh untouched holdout. New forward paper observations remain necessary.',
                'Futures/short execution is not connected to the existing Alpaca equities runner. No orders are submitted by this research module.'
            ]}
    return report,artifact


def forecast(report,artifact,rows):
    if artifact.get('version') != VERSION or artifact.get('features') != FEATURES:
        raise ValueError('Unsupported historical analogue artifact')
    bars,segments,instrument,_=prepare(rows,artifact['symbol'],artifact['timeframe'],
                                      artifact['requested_years'],artifact['horizon'],require_coverage=False)
    trained_through=datetime.fromisoformat(artifact['fitted_labels_through'])
    if bars[-1].timestamp <= trained_through:
        raise ValueError('Forecast time must follow every training outcome; in-sample self-matches are not forecasts')
    if bars[-1].timestamp < datetime.fromisoformat(report['test']['end']):
        raise ValueError('Forecast time must follow the evaluation outcomes used for readiness; historical point-in-time replay is a separate evaluation')
    if segments[-1] != segments[-LOOKBACK]:
        raise ValueError('Need 20 uninterrupted same-session/same-contract bars before forecasting')
    result=neighbors(artifact,vector(bars,len(bars)-1,artifact['timeframe']!='1d'))
    side=direction(result,bars[-1].close,instrument,artifact['commission_per_side'],artifact['slippage_ticks_per_side'])
    checks=readiness(report)
    allowed=report['status']=='experimental_research_candidate' and checks['research_checks_passed']
    reasons=list(checks['reasons'])
    if not result['within_training_distance']:
        reasons.append('The latest pattern is outside the training-distance acceptance range.')
    elif not side:
        reasons.append('The calibrated direction estimate and return quantiles do not jointly clear the doubled-cost hurdle.')
    result.update(as_of=bars[-1].timestamp.isoformat(),horizon_bars=artifact['horizon'],
                  decision=('LONG' if side==1 else 'SHORT') if side and allowed else 'WAIT',
                  broker_execution_enabled=False,future_profitability_proven=False,
                  readiness=checks,abstention_reasons=reasons)
    return result
