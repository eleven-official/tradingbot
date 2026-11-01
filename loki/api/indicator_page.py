"""Private Loki Pine page: the NQ structural-KNN indicator, gated like the site.

The indicator source ships as a template asset and is rendered server-side into
a copy-paste block. The page rides the site-access gate: the middleware only
admits browsers holding a valid gate + terms cookie for ``/indicator``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from loki.api import site_access
from loki.version import __version__

router = APIRouter(tags=["Loki Pine indicator"])

# Same convention as loki.api.server: resolve assets independent of cwd.
_repo_dir = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(_repo_dir / "templates"))

# Read once per cold start; the Pine text is static by design.
PINE_SOURCE = (_repo_dir / "templates" / "loki_nq.pine").read_text(encoding="utf-8")
PINE_SHA256 = None  # filled below to avoid a second hashing import in templates


@router.get("/indicator", response_class=HTMLResponse, include_in_schema=False)
async def indicator_page(request: Request) -> HTMLResponse:
    """Gated copy-paste page for the Loki NQ Pine indicator."""
    import hashlib

    global PINE_SHA256
    if PINE_SHA256 is None:
        PINE_SHA256 = hashlib.sha256(PINE_SOURCE.encode("utf-8")).hexdigest()
    return templates.TemplateResponse(
        request=request,
        name="indicator.html",
        context={
            "version": __version__,
            "pine_source": PINE_SOURCE,
            "pine_sha256": PINE_SHA256,
            "gate_note": site_access.gate_enabled(),
        },
    )
