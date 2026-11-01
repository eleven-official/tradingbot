import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from loki.api import cloud_research, site_access
from loki.api.server import app

OWNER = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('LOKI_GATE_SECRET', 'offline-test-cookie-signing')
    monkeypatch.setenv('LOKI_SITE_GATE', '0')
    monkeypatch.delenv('LOKI_RESEARCH_URL', raising=False)
    monkeypatch.delenv('LOKI_RESEARCH_BRIDGE_SECRET', raising=False)
    with TestClient(app) as result:
        result.cookies.set(site_access.SESSION_COOKIE,
                           site_access.issue_session_cookie_value(OWNER, 'offline@example.invalid', 'Offline'))
        yield result


def test_research_requires_existing_login():
    with TestClient(app) as client:
        assert client.get('/api/account/research/state').status_code == 401


def test_missing_bridge_reports_setup_without_breaking_loki(client):
    response = client.get('/api/account/research/status')
    assert response.status_code == 200
    assert response.json()['configured'] is False
    assert response.json()['execution_enabled'] is False
    assert 'no-store' in response.headers['cache-control']
    response = client.get('/')
    assert response.status_code == 200
    assert 'data-view="cloud-research"' in response.text
    assert '/static/js/cloud_research.js' in response.text


def test_bridge_derives_owner_from_session_and_forwards_only_allowlisted_operation(client, monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_research, 'forward', lambda *args: (calls.append(args) or (201, {'id': 'dataset'})))
    response = client.post('/api/account/research/datasets', json={'symbol': 'SPY'})
    assert response.status_code == 201
    assert calls[0][0:2] == ('POST', 'datasets')
    assert json.loads(calls[0][2]) == {'symbol': 'SPY'}
    assert calls[0][3] == OWNER
    assert client.post('/api/account/research/optimizer', json={}).status_code == 404
    assert client.post('/api/account/research/orders', json={}).status_code == 404
    assert len(calls) == 1


def test_stale_owner_and_cross_origin_are_rejected_before_forward(client, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Must not forward')
    monkeypatch.setattr(cloud_research, 'forward', forbidden)
    assert client.post('/api/account/research/jobs', json={}, headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert client.get('/api/account/research/state', headers={'X-Workspace-Owner': 'different'}).status_code == 409
    assert client.post('/api/account/research/jobs', content=b'x' * 1_000_001).status_code == 413


@pytest.mark.parametrize('url', ['http://cloud.example', 'https://cloud.example/api', 'https://user:password@cloud.example', 'https://cloud.example?token=x', 'https://cloud.example:bad'])
def test_bridge_rejects_invalid_config(monkeypatch, url):
    monkeypatch.setenv('LOKI_RESEARCH_URL', url)
    monkeypatch.setenv('LOKI_RESEARCH_BRIDGE_SECRET', 'x' * 40)
    with pytest.raises(HTTPException):
        cloud_research.bridge_config()


def test_signature_binds_real_owner_method_path_and_exact_body(monkeypatch):
    secret = 'test-bridge-secret-' * 3
    monkeypatch.setenv('LOKI_RESEARCH_URL', 'https://cloud.example')
    monkeypatch.setenv('LOKI_RESEARCH_BRIDGE_SECRET', secret)
    monkeypatch.setattr(site_access, '_supabase_config', lambda: ('https://test.supabase.co', 'never-forward-this-key'))
    seen = {}
    class Reply:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'{"status":"queued"}'
    def transport(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return Reply()
    monkeypatch.setattr(cloud_research.requests, 'request', transport)
    assert cloud_research.forward('POST', 'jobs', b'{"dataset_id":"d"}', OWNER) == (200, {'status': 'queued'})
    headers = seen['headers']
    encoded = headers['X-Loki-Identity']
    identity = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    assert identity == {'uid': OWNER, 'project': 'https://test.supabase.co'}
    canonical = '\n'.join((headers['X-Loki-Time'], headers['X-Loki-Nonce'], 'POST', '/api/jobs', hashlib.sha256(seen['data']).hexdigest(), encoded))
    assert hmac.compare_digest(headers['X-Loki-Signature'], hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest())
    assert seen['allow_redirects'] is False
    assert 'never-forward-this-key' not in str(seen)
    assert 'Cookie' not in headers


def test_frontend_is_navigation_wired_and_never_stores_bridge_credentials():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'static/js/cloud_research.js').read_text(encoding='utf-8')
    assert '/api/account/research/' in script
    assert 'localStorage' not in script
    assert 'LOKI_RESEARCH_BRIDGE_SECRET' not in script
    assert 'innerHTML' not in script
    assert 'cloud_research:window.lokiCloudResearch.summary()' in (root / 'static/js/workspace.js').read_text(encoding='utf-8')


def test_transport_rejects_redirects_and_malformed_cloud_responses(monkeypatch):
    monkeypatch.setattr(cloud_research, 'bridge_config', lambda: ('https://cloud.example', 'x' * 40, 'https://test.supabase.co'))
    class Reply:
        status_code = 302
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'{"redirect":"somewhere"}'
    monkeypatch.setattr(cloud_research.requests, 'request', lambda *a, **kw: Reply())
    with pytest.raises(HTTPException) as error:
        cloud_research.forward('GET', 'state', b'', OWNER)
    assert error.value.status_code == 503


def test_transport_has_a_bounded_response_size(monkeypatch):
    monkeypatch.setattr(cloud_research, 'bridge_config', lambda: ('https://cloud.example', 'x' * 40, 'https://test.supabase.co'))
    class Reply:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'x' * 2_000_001
    monkeypatch.setattr(cloud_research.requests, 'request', lambda *a, **kw: Reply())
    with pytest.raises(HTTPException) as error:
        cloud_research.forward('GET', 'state', b'', OWNER)
    assert error.value.status_code == 503
