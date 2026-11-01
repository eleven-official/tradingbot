from datetime import date, timedelta

import pandas as pd
import pytest

from core.fusion import instrument_history, paper_models, paper_research
from core.fusion.broker_link import AlpacaClient, Profile
from loki.api.broker_workspace import HistoryRequest, UploadTrainingRequest
from test_paper_models import historical_fixture


@pytest.fixture(scope='module')
def long_rows():
    rows = historical_fixture(21)
    for row in rows:
        row['timestamp'] = (date.fromisoformat(row['timestamp']) - timedelta(days=4383)).isoformat()
    return rows


def test_twenty_year_models_and_comparisons_support_more_than_5000_bars(long_rows):
    assert len(UploadTrainingRequest(symbol='SPY',years=20,bars=long_rows).bars) > 5000
    report = paper_models.train_instrument(long_rows, 'SPY', 20, source={'kind':'synthetic test'})
    assert report['coverage']['bars'] > 5000
    assert report['coverage']['years'] >= 19.8
    assert report['training']['end'] < report['validation']['start'] < report['test']['start']
    selected = [row for row in long_rows if report['coverage']['start'] <= row['timestamp'] <= report['coverage']['end']]
    compared = paper_research.compare(report, selected)
    assert compared['requested_years'] == 20
    assert compared['forward_evidence']['historical_dates_already_inspected']


@pytest.mark.parametrize('years', [10,15,20])
def test_api_accepts_long_windows_without_switching_default_provider(years):
    payload = HistoryRequest(symbol='SPY',years=years)
    assert payload.source == 'alpaca'
    assert HistoryRequest(symbol='SPY',years=years,source='yahoo').source == 'yahoo'


def test_twenty_year_request_rejects_short_coverage():
    with pytest.raises(ValueError,match='incomplete'):
        paper_models.train_instrument(historical_fixture(5),'SPY',20,source={})


def test_alpaca_accepts_twenty_year_request_and_keeps_feed_explicit(monkeypatch):
    calls=[]
    def request(client, method, path, **kwargs):
        calls.append(kwargs['params'])
        return {'bars':[], 'next_page_token':None}
    monkeypatch.setattr(AlpacaClient,'request',request)
    assert AlpacaClient(Profile('alpaca','paper','fixture-key','fixture-secret')).historical_bars('SPY',20) == []
    assert calls[0]['feed'] == 'iex'
    assert calls[0]['start'] < '2010-01-01'


def test_yahoo_maps_real_columns_without_inventing_candles(monkeypatch):
    import yfinance as yf
    frame=pd.DataFrame({'Open':[100.0,101.0], 'High':[102.0,103.0],
                        'Low':[99.0,100.0], 'Close':[101.0,102.0], 'Volume':[1000,1100]},
                       index=pd.date_range('2020-01-01',periods=2))
    calls=[]
    class Ticker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return frame
    monkeypatch.setattr(yf,'Ticker',lambda symbol:Ticker())
    rows=instrument_history.yahoo_history('SPY',20)
    assert len(rows)==2 and rows[0]['close']==101
    assert calls[0]['auto_adjust'] is False
    assert calls[0]['start'] < '2010-01-01'


def test_yahoo_empty_history_fails_without_fallback(monkeypatch):
    import yfinance as yf
    class Ticker:
        def history(self, **kwargs):
            return pd.DataFrame()
    monkeypatch.setattr(yf,'Ticker',lambda symbol:Ticker())
    with pytest.raises(ConnectionError,match='no daily research history'):
        instrument_history.yahoo_history('SPY',20)
