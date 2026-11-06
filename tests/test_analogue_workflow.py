from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib

from fastapi.testclient import TestClient
import pytest

from core.fusion import analogue_store, instrument_history
from loki.api import analogue as api
from loki.api.server import app
from test_analogue import rows, built  # noqa: F401 — fixtures discovered by pytest


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('LOKI_FUSION_LOCAL','1')
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as browser:
        token=browser.get('/api/fusion/capabilities').json()['local_token']
        browser.headers['X-Loki-Local-Token']=token
        yield browser


def save_as(built,source,version=None):
    report,artifact=deepcopy(built)
    report['source']=artifact['source']=source
    if version:
        report['version']=artifact['version']=version
    report['artifact_sha256']=analogue_store.fingerprint(artifact)
    report['id']=hashlib.sha256((report['data_sha256']+report['artifact_sha256']).encode()).hexdigest()
    analogue_store.save(report,artifact)
    return report,artifact


def test_catalog_finds_saved_models_and_skips_corrupt_files(client,built):
    report,_=save_as(built,'Yahoo Finance via yfinance; synthetic test only')
    (analogue_store.directory()/('a'*64+'.json')).write_text('{broken json')
    result=client.get('/api/fusion/analogue')
    assert result.status_code==200
    assert result.json()['models'][0]['id']==report['id']
    assert result.json()['unreadable_models']==1
    assert 'standardized_reference' not in str(result.json())
    assert 'no-store' in result.headers['cache-control']
    assert TestClient(app).get('/api/fusion/analogue').status_code==403


def test_latest_daily_estimate_works_without_a_csv(client,built,rows,monkeypatch):
    report,_=save_as(built,'Yahoo Finance via yfinance; synthetic test only')
    calls=[]
    def recent(symbol):
        calls.append(symbol)
        return rows[-30:]
    monkeypatch.setattr(api,'yahoo_recent_history',recent)
    result=client.post('/api/fusion/analogue/'+report['id']+'/forecast-latest',json={})
    assert result.status_code==200
    assert calls==['SPY']
    assert result.json()['bars_used']==30
    assert result.json()['as_of'].startswith(rows[-1]['timestamp'])
    assert result.json()['broker_execution_enabled'] is False
    assert result.json()['abstention_reasons'] or result.json()['readiness']['research_checks_passed']


@pytest.mark.parametrize('source,version', [('Operator CSV',None),('Yahoo Finance via yfinance','loki_historical_analogue_v2')])
def test_latest_never_substitutes_data_or_fetches_for_legacy_models(client,built,monkeypatch,source,version):
    report,_=save_as(built,source,version)
    def forbidden(symbol):
        raise AssertionError('Provider must not be called')
    monkeypatch.setattr(api,'yahoo_recent_history',forbidden)
    assert client.post('/api/fusion/analogue/'+report['id']+'/forecast-latest',json={}).status_code==422


def test_latest_cross_origin_requests_are_blocked(client,built):
    report,_=save_as(built,'Yahoo Finance via yfinance; synthetic test only')
    result=client.post('/api/fusion/analogue/'+report['id']+'/forecast-latest',json={},headers={'Origin':'https://attacker.example'})
    assert result.status_code==403


def test_recent_cache_is_bounded_and_never_returns_mutable_shared_rows(monkeypatch):
    monkeypatch.setattr(instrument_history,'_recent_cache',{})
    today=datetime.now(timezone.utc).date()
    values=[{'timestamp':(today-timedelta(days=i)).isoformat(),'open':100,'high':101,'low':99,'close':100,'volume':1000} for i in range(30,0,-1)]
    calls=[]
    monkeypatch.setattr(instrument_history,'_yahoo_rows',lambda *args:(calls.append(args) or values))
    first=instrument_history.yahoo_recent_history('SPY')
    first[0]['close']=999
    second=instrument_history.yahoo_recent_history('SPY')
    assert second[0]['close']==100 and len(calls)==1
    with pytest.raises(ValueError):
        instrument_history.yahoo_recent_history('ES')


def test_stale_daily_provider_data_is_not_cached_or_presented_as_current(monkeypatch):
    monkeypatch.setattr(instrument_history,'_recent_cache',{})
    values=[{'timestamp':'2020-01-01'} for _ in range(30)]
    monkeypatch.setattr(instrument_history,'_yahoo_rows',lambda *args:values)
    with pytest.raises(ConnectionError,match='stale'):
        instrument_history.yahoo_recent_history('SPY')
    assert not instrument_history._recent_cache
