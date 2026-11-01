import pytest

from loki.api import site_access, member_data


@pytest.mark.parametrize("url", [
    "http://project.supabase.co", "https://user:password@project.supabase.co",
    "https://project.supabase.co/path", "https://project.supabase.co?x=1",
    "https://project.supabase.co:8443", "https://project.supabase.co.evil.test",
])
def test_account_origin_rejects_unsafe_destinations(monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_fixture")
    with pytest.raises(site_access.HTTPException):
        site_access._supabase_config()


def test_account_calls_never_forward_credentials_through_redirects(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_fixture")
    calls = []

    class Reply:
        status_code = 302
        content = b""

    def request(*args, **kwargs):
        calls.append(kwargs)
        return Reply()

    monkeypatch.setattr(site_access.requests, "request", request)
    with pytest.raises(site_access.HTTPException):
        site_access._supa_request("POST", "/auth/v1/token?grant_type=password", json_body={})
    with pytest.raises(site_access.HTTPException):
        member_data.database("GET", "/rest/v1/member_workspace")
    assert len(calls) == 2
    assert all(call["allow_redirects"] is False for call in calls)
