from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import math
import json

import pytest
from fastapi.testclient import TestClient

from core.fusion import analogue, analogue_store
from core.strategy_lab import validate_bars
from loki.api.server import app
from test_paper_models import historical_fixture


@pytest.fixture(scope='module')
def rows():
    values=historical_fixture(21)
    for row in values:
        row['timestamp']=(date.fromisoformat(row['timestamp'])-timedelta(days=4383)).isoformat()
    cutoff=date.fromisoformat(values[-1]['timestamp'])-timedelta(days=round(20*365.25))
    return [row for row in values if date.fromisoformat(row['timestamp'])>=cutoff]


@pytest.fixture(scope='module')
def built(rows):
    return analogue.build(rows,symbol='SPY',timeframe='1d',years=20,source='SYNTHETIC TEST')


def test_rebuilt_model_has_no_broker_authority_and_purges_split_labels(built):
    report,artifact=built
    assert report['broker_execution_enabled'] is False
    assert report['future_profitability_proven'] is False
    assert artifact['training_labels_through'] < report['validation']['start']
    assert artifact['training_labels_through'] < report['calibration']['start']
    assert artifact['fitted_labels_through'] < report['validation']['start']
    assert report['validation']['end'] < report['test']['start']
    assert len(artifact['features'])==16
    assert report['training']['references']<=analogue.MAX_REFERENCES
    assert report['test']['examples']<=analogue.MAX_EVALUATIONS
    json.dumps(report,allow_nan=False)


def test_future_test_changes_never_change_prototypes_scaling_or_validation(rows,built):
    original,artifact=built
    changed=deepcopy(rows)
    for row in changed:
        if row['timestamp']>=original['test']['start'][:10]:
            for key in ('open','high','low','close'):
                row[key]*=1.25
    altered,other=analogue.build(changed,symbol='SPY',timeframe='1d',years=20,source='SYNTHETIC TEST')
    assert artifact==other
    assert original['validation']==altered['validation']
    assert original['data_sha256'] != altered['data_sha256']


def test_validation_labels_cannot_fit_the_probability_calibration(rows,built):
    original,artifact=built
    changed=deepcopy(rows)
    for row in changed:
        if row['timestamp']>=original['validation']['start'][:10]:
            for key in ('open','high','low','close'):
                row[key]*=1.25
    altered,other=analogue.build(changed,symbol='SPY',timeframe='1d',years=20,source='SYNTHETIC TEST')
    assert artifact==other
    assert original['calibration']==altered['calibration']


def test_probability_shrinkage_can_fall_back_to_baseline(built):
    _,artifact=built
    candidate=deepcopy(artifact)
    candidate['calibration']['selected_weight']=0.0
    features=candidate['means']
    result=analogue.neighbors(candidate,features)
    assert result['estimated_up_probability']==candidate['training_up_frequency']
    assert result['calibration_weight']==0


def test_calibration_weight_is_selected_only_from_its_declared_trials(built):
    report,_=built
    calibration=report['calibration']
    winner=min(calibration['trials'],key=lambda row:(row['brier_score'],row['weight']))
    assert winner['weight']==calibration['selected_weight']
    assert calibration['selected_weight'] in analogue.CALIBRATION_WEIGHTS


def test_regime_matching_uses_only_the_selected_training_pool(built):
    _,artifact=built
    for name,members in artifact['regime_members'].items():
        if len(members)<analogue.NEIGHBORS*3:
            continue
        index=members[0]
        features=[mean+scale*z for mean,scale,z in zip(artifact['means'],artifact['scales'],artifact['standardized_reference'][index])]
        result=analogue.neighbors(artifact,features)
        assert result['reference_regime']==name
        allowed={artifact['reference_examples'][i]['signal_at'] for i in members}
        assert all(row['signal_at'] in allowed for row in result['analogues'])


def test_sparse_regime_falls_back_without_inventing_neighbors(built):
    _,artifact=built
    artifact=deepcopy(artifact)
    features=artifact['means']
    name=analogue.regime(features,artifact['regime_volatility_cutoff'])
    artifact['regime_members'][name]=[0]
    result=analogue.neighbors(artifact,features)
    assert result['reference_regime']=='all_regimes'
    assert len(result['analogues'])==5


def test_nearest_cases_are_earlier_training_outcomes(built):
    report,_=built
    assert report['latest']
    for match in report['latest']['analogues']:
        assert match['outcome_at'] < report['validation']['start']


def test_forecast_rejects_self_matching_training_time(rows,built):
    report,artifact=built
    with pytest.raises(ValueError,match='in-sample'):
        analogue.forecast(report,artifact,rows[100:120])
    result=analogue.forecast(report,artifact,rows[-20:])
    assert result['broker_execution_enabled'] is False


def test_readiness_cannot_use_test_outcomes_from_after_the_forecast(rows,built):
    report,artifact=built
    after_fit=[i for i,row in enumerate(rows) if artifact['fitted_labels_through'][:10]<row['timestamp']<report['test']['start'][:10]]
    index=after_fit[-1]
    with pytest.raises(ValueError,match='readiness'):
        analogue.forecast(report,artifact,rows[index-19:index+1])


def test_out_of_distribution_features_abstain(built):
    _,artifact=built
    forecast=analogue.neighbors(artifact,[100.0]*16)
    assert not forecast['within_training_distance']
    assert analogue.direction(forecast,100,analogue.INSTRUMENTS['SPY'],0.01,1)==0


def test_entry_signal_cannot_use_future_open_to_clear_cost_hurdle(monkeypatch):
    bars=validate_bars([
        {'timestamp':'2020-01-01','open':100,'high':101,'low':99,'close':100,'volume':1000},
        {'timestamp':'2020-01-02','open':200,'high':202,'low':199,'close':201,'volume':1000},
    ])
    forecast={'within_training_distance':True,'up_frequency_smoothed':0.6,
              'return_quantiles':{'p25':0.0007,'p75':0.001}}
    monkeypatch.setattr(analogue,'vector',lambda *args: [])
    monkeypatch.setattr(analogue,'neighbors',lambda *args: forecast)
    result=analogue.evaluate_period({'training_up_frequency':0.5},bars,[0],
                                   analogue.INSTRUMENTS['SPY'],0.01,1,1,False)
    assert result['signals']==0
    assert result['unit_net_pnl']==0


def test_futures_require_actual_contracts_and_costs(rows):
    futures=[dict(row,contract='ESZ'+row['timestamp'][:4]) for row in rows]
    with pytest.raises(ValueError,match='commission'):
        analogue.build(futures,symbol='ES',timeframe='1d',years=20,source='SYNTHETIC TEST')
    with pytest.raises(ValueError,match='actual root'):
        analogue.build(rows,symbol='ES',timeframe='1d',years=20,commission=2.5,source='SYNTHETIC TEST')


def test_actual_contract_rolls_are_purged(rows):
    futures=[dict(row,contract='ESZ'+row['timestamp'][:4]) for row in rows]
    report,artifact=analogue.build(futures,symbol='ES',timeframe='1d',years=20,commission=2.5,source='SYNTHETIC CONTRACT TEST')
    assert artifact['instrument']['multiplier']==50
    assert artifact['commission_per_side']==2.5
    for example in artifact['reference_examples']:
        assert example['entry_at'][:4] == example['outcome_at'][:4]
        assert example['contract']=='ESZ'+example['signal_at'][:4]
    assert report['broker_execution_enabled'] is False


def test_continuous_history_cannot_be_mislabeled_as_one_contract(rows):
    futures=[dict(row,contract='ESZ2026') for row in rows]
    with pytest.raises(ValueError,match='contract year'):
        analogue.build(futures,symbol='ES',timeframe='1d',years=20,commission=2.5,source='TEST')


def test_short_history_cannot_be_called_twenty_years(rows):
    with pytest.raises(ValueError,match='Actual coverage'):
        analogue.build(rows[-1000:],symbol='SPY',timeframe='1d',years=20,source='TEST')


def test_extra_years_cannot_silently_change_declared_window(rows):
    with pytest.raises(ValueError,match='extra years'):
        analogue.build(rows,symbol='SPY',timeframe='1d',years=10,source='TEST')


def test_intraday_requires_timezone_and_sessions(rows):
    with pytest.raises(ValueError,match='timezone-aware'):
        analogue.build(rows,symbol='SPY',timeframe='15m',years=20,source='TEST')


def test_intraday_futures_training_uses_session_bounded_labels():
    values=[]
    day=date(2010,1,4)
    end=date(2020,1,3)
    day_index=0
    while day<=end:
        if day.weekday()<5:
            for i in range(24):
                opening=4000+day_index*0.02+math.sin(day_index/9+i/3)
                closing=opening+math.sin(day_index/7+i/4)*0.5
                stamp=datetime(day.year,day.month,day.day,14,30,tzinfo=timezone.utc)+timedelta(minutes=15*i)
                values.append({'timestamp':stamp.isoformat(),'open':opening,'high':max(opening,closing)+0.25,
                               'low':min(opening,closing)-0.25,'close':closing,'volume':1000+i*10,
                               'session':day.isoformat(),'contract':f'NQZ{day.year}'})
            day_index+=1
        day+=timedelta(days=1)
    report,artifact=analogue.build(values,symbol='NQ',timeframe='15m',years=10,
                                   commission=2.5,source='SYNTHETIC INTRADAY TEST')
    assert report['timeframe']=='15m' and report['coverage']['bars']>60000
    for match in artifact['reference_examples']:
        assert match['signal_at'][:10]==match['outcome_at'][:10]
    assert report['broker_execution_enabled'] is False


def test_intraday_session_and_gap_boundaries_prevent_forecasts(built):
    report,artifact=built
    artifact=deepcopy(artifact)
    artifact['timeframe']='15m'
    values=[{'timestamp':f'2024-01-02T{9+(i//4):02d}:{15*(i%4):02d}:00+00:00',
             'open':100.0,'high':101.0,'low':99.0,'close':100.5,'volume':1000,
             'session':'2024-01-02' if i<10 else '2024-01-03'} for i in range(20)]
    with pytest.raises(ValueError,match='uninterrupted'):
        analogue.forecast(report,artifact,values)
    for row in values:
        row['session']='2024-01-02'
    values[-1]['timestamp']='2024-01-02T18:00:00+00:00'
    with pytest.raises(ValueError,match='uninterrupted'):
        analogue.forecast(report,artifact,values)


def test_chunk_boundaries_cannot_hide_bad_ordering(rows):
    doubled=rows+rows
    with pytest.raises(ValueError,match='ascending'):
        analogue.prepare(doubled,'SPY','1d',20,3)


def test_immutable_bundle_integrity_and_path_validation(built,tmp_path,monkeypatch):
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    report,artifact=built
    analogue_store.save(report,artifact)
    assert analogue_store.load(report['id'])==(report,artifact)
    with pytest.raises(ValueError,match='identifier'):
        analogue_store.load('../outside')
    path=tmp_path/(report['id']+'.json')
    bundle=json.loads(path.read_text())
    bundle['artifact']['means'][0]+=1
    path.write_text(json.dumps(bundle))
    with pytest.raises(ValueError,match='integrity'):
        analogue_store.load(report['id'])


def test_saved_report_cannot_change_eligibility_without_detection(built,tmp_path,monkeypatch):
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    report,artifact=built
    analogue_store.save(report,artifact)
    path=tmp_path/(report['id']+'.json')
    bundle=json.loads(path.read_text())
    bundle['report']['status']='modified_status'
    path.write_text(json.dumps(bundle))
    with pytest.raises(ValueError,match='report failed its integrity'):
        analogue_store.load(report['id'])


def test_legacy_bundle_is_viewable_but_never_directionally_enabled(built,rows,tmp_path,monkeypatch):
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    report,artifact=built
    path=tmp_path/(report['id']+'.json')
    path.write_text(json.dumps({'report':report,'artifact':artifact}))
    legacy,loaded=analogue_store.load(report['id'])
    assert legacy['status']=='legacy_research_retrain_required'
    assert analogue.forecast(legacy,loaded,rows[-20:])['decision']=='WAIT'


def test_research_api_is_local_only_and_returns_no_training_array(built,rows,tmp_path,monkeypatch):
    monkeypatch.setenv('LOKI_FUSION_LOCAL','1')
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    report,artifact=built
    analogue_store.save(report,artifact)
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
        url='/api/fusion/analogue/'+report['id']
        assert client.get(url).status_code==403
        token=client.get('/api/fusion/capabilities').json()['local_token']
        headers={'X-Loki-Local-Token':token}
        saved=client.get(url,headers=headers)
        assert saved.status_code==200
        assert 'no-store' in saved.headers['cache-control']
        assert 'standardized_reference' not in saved.json()
        fresh=client.post(url+'/forecast',json={'bars':rows[-20:]},headers=headers)
        assert fresh.status_code==200
        assert fresh.json()['broker_execution_enabled'] is False
        payload={'symbol':'SPY','timeframe':'1d','years':20,'horizon':3,'commission':0.01,
                 'slippage_ticks':1.0,'source':'SYNTHETIC TEST','bars':rows}
        assert client.post('/api/fusion/analogue/evaluate',json=payload).status_code==403
        evaluated=client.post('/api/fusion/analogue/evaluate',json=payload,headers=headers)
        assert evaluated.status_code==200
        assert evaluated.json()['id']==report['id']
        assert client.get(url,headers={**headers,'Origin':'https://attacker.example'}).status_code==403
