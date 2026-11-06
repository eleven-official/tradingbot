"""Owner-bound bridge to the cloud research worker; never proxies broker orders."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from loki.api import site_access
from loki.api.member_data import require_member

router = APIRouter(prefix="/api/account/research", tags=["Cloud research"])
ROUTES = {
    ("GET", "state"),
    ("POST", "datasets"),
    ("POST", "jobs"),
    ("PATCH", "jobs"),
    ("POST", "ingest"),
}
MAX_BODY = 1_000_000


def bridge_config() -> tuple[str, str, str]:
    target = os.environ.get("LOKI_RESEARCH_URL", "").strip().rstrip("/")
    secret = os.environ.get("LOKI_RESEARCH_BRIDGE_SECRET", "")
    try:
        parsed = urlsplit(target)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and parsed.port in (None, 443)
        )
    except ValueError:
        valid = False
    if not valid or len(secret) < 32:
        raise HTTPException(
            503,
            "Cloud research is not configured. Set the HTTPS cloud deployment URL and shared bridge secret on the Loki server.",
        )
    project, _ = site_access._supabase_config()
    return target, secret, project.rstrip("/")


def forward(method: str, resource: str, body: bytes, owner: str) -> tuple[int, dict]:
    target, secret, project = bridge_config()
    timestamp, nonce = str(int(time.time() * 1000)), str(uuid4())
    identity = (
        base64.urlsafe_b64encode(
            json.dumps({"uid": owner, "project": project}, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    path = "/api/" + resource
    payload = "\n".join(
        (timestamp, nonce, method, path, hashlib.sha256(body).hexdigest(), identity)
    )
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Loki-Time": timestamp,
        "X-Loki-Nonce": nonce,
        "X-Loki-Identity": identity,
        "X-Loki-Signature": signature,
    }
    try:
        with requests.request(
            method,
            target + path,
            data=body or None,
            headers=headers,
            timeout=40,
            allow_redirects=False,
            stream=True,
        ) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError("Oversized cloud response")
                chunks.append(chunk)
            result = json.loads(b"".join(chunks))
            if not isinstance(result, dict) or response.status_code not in {
                200,
                201,
                401,
                403,
                422,
                503,
            }:
                raise ValueError("Unexpected cloud response")
            return response.status_code, result
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            503,
            "Cloud research could not be reached. No automatic mutation retry was sent; refresh state before retrying.",
        ) from exc


@router.api_route("/{resource}", methods=["GET", "POST", "PATCH"])
async def research_bridge(resource: str, request: Request) -> JSONResponse:
    member = require_member(request)
    if request.headers.get("x-workspace-owner", member["uid"]) != member["uid"]:
        raise HTTPException(409, "Account changed. Reload before accessing cloud research.")
    if resource == "status" and request.method == "GET":
        try:
            bridge_config()
            configured = True
        except HTTPException:
            configured = False
        return JSONResponse(
            {
                "configured": configured,
                "execution_enabled": False,
                "note": "Uses your Loki account in the same Supabase project; cloud models do not enable broker execution.",
            },
            headers={"Cache-Control": "private, no-store"},
        )
    if (request.method, resource) not in ROUTES:
        raise HTTPException(404, "Unknown research operation.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(
                413, "Research upload exceeds the 1 MB bridge limit; use smaller feature batches."
            )
    if request.method == "GET" and body:
        raise HTTPException(400, "State requests must not contain a body.")
    status, result = await run_in_threadpool(
        forward, request.method, resource, bytes(body), member["uid"]
    )
    return JSONResponse(result, status_code=status, headers={"Cache-Control": "private, no-store"})
