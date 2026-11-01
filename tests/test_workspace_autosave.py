from fastapi.testclient import TestClient
import pytest

from loki.api import member_data, site_access
from loki.api.server import app

OWNER = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def signed_client():
    with TestClient(app) as client:
        client.cookies.set(site_access.SESSION_COOKIE,
                           site_access.issue_session_cookie_value(OWNER, 'check@example.com', 'Check'))
        client.headers['X-Workspace-Owner'] = OWNER
        yield client


def test_partial_save_derives_owner_and_uses_atomic_rpc(signed_client, monkeypatch):
    calls = []
    def database(*args):
        calls.append(args)
        return [{'updated_at': '2026-11-01T00:00:00Z'}]
    monkeypatch.setattr(member_data, 'database', database)
    result = signed_client.patch('/api/account/workspace', json={
        'items': {'loki_currency':'AUD'}, 'removed':['loki_watchlist_v1']})
    assert result.status_code == 200
    assert calls[0] == ('POST','/rest/v1/rpc/merge_member_workspace',
                        {'p_user_id':OWNER,'p_items':{'loki_currency':'AUD'},'p_removed':['loki_watchlist_v1']})
    assert 'no-store' in result.headers['cache-control']


@pytest.mark.parametrize('body', [
    {'items':{'api_key':'secret'}},
    {'items':{},'removed':['loki_alpaca_keys_v1']},
    {'items':{'loki_currency':'AUD'},'removed':['loki_currency']},
])
def test_credentials_or_contradictory_changes_never_reach_database(signed_client, monkeypatch, body):
    def forbidden(*args):
        raise AssertionError('Database must not be reached')
    monkeypatch.setattr(member_data,'database',forbidden)
    assert signed_client.patch('/api/account/workspace', json=body).status_code == 400


def test_stale_owner_and_cross_origin_are_blocked(signed_client):
    body = {'items':{'loki_currency':'AUD'}}
    assert signed_client.patch('/api/account/workspace', json=body,
                               headers={'X-Workspace-Owner':'other'}).status_code == 409
    assert signed_client.patch('/api/account/workspace', json=body,
                               headers={'Origin':'https://attacker.example'}).status_code == 403


def test_database_must_confirm_save(signed_client, monkeypatch):
    monkeypatch.setattr(member_data,'database',lambda *args: [])
    assert signed_client.patch('/api/account/workspace',json={'items':{}}).status_code == 503
