import gzip
import hashlib
import json

import pytest

from core.fusion import analogue_store
import train_analogue


def test_futures_and_intraday_never_fall_back_to_daily_prices():
    with pytest.raises(ValueError,match='requires a licensed'):
        train_analogue.train(['ES'],timeframe='15m')


def test_csv_is_one_instrument():
    with pytest.raises(ValueError,match='exactly one'):
        train_analogue.train(['ES','NQ'],csv_path='not-opened.csv')


def test_csv_reader_preserves_session_contract_metadata(tmp_path):
    path=tmp_path/'history.csv'
    path.write_text('timestamp,open,high,low,close,volume,session,contract\n2020-01-01T14:30:00Z,100,101,99,100.5,1000,2020-01-01,ESH2020\n')
    row=train_analogue.read_csv(path)[0]
    assert row['contract']=='ESH2020' and row['close']==100.5


def test_training_saves_reproducible_snapshot_without_network(monkeypatch,tmp_path):
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    rows=[{'timestamp':'2020-01-01','open':100.0,'high':101.0,'low':99.0,'close':100.0,'volume':1000.0}]
    artifact={'version':'fixture'}
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    model_hash=analogue_store.fingerprint(artifact)
    report={'id':hashlib.sha256((digest+model_hash).encode()).hexdigest(),'version':'fixture',
            'data_sha256':digest,'artifact_sha256':model_hash,'coverage':{},'validation':{},'test':{},
            'status':'fixture','latest':None}
    monkeypatch.setattr(train_analogue,'yahoo_history',lambda *args:rows)
    monkeypatch.setattr(train_analogue.analogue,'build',lambda *args,**kwargs:(report,artifact))
    result=train_analogue.train(['SPY'])[0]
    assert result['trained']
    with gzip.open(tmp_path/result['snapshot'],'rt') as stream:
        saved=json.load(stream)
    assert hashlib.sha256(json.dumps(saved,sort_keys=True,separators=(',',':')).encode()).hexdigest()==digest


def test_wrong_existing_snapshot_is_preserved_and_rejected(monkeypatch,tmp_path):
    monkeypatch.setenv('LOKI_ANALOGUE_DIR',str(tmp_path))
    rows=[{'timestamp':'2020-01-01'}]
    report={'id':'a'*64,'data_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    path=tmp_path/(report['id']+'.data.json.gz')
    with gzip.open(path,'wb') as stream:
        stream.write(b'[]')
    original=path.read_bytes()
    with pytest.raises(ValueError,match='failed integrity'):
        train_analogue.write_snapshot(report,rows)
    assert path.read_bytes()==original
