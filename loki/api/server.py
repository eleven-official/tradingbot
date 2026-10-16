from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from loki.version import __version__

app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Loki trading API and lightweight landing page",
)

# Serve a small /static directory for CSS/JS/images used by the landing page.
project_root = Path(__file__).resolve().parents[2]
static_dir = project_root / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates dir
templates_dir = project_root / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render a small landing page so the repo is a website-ready deployment."""
    context = {"version": __version__}
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "loki", "version": __version__})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    # Prefer static/favicon.ico if present, fallback to repo root loki.ico if available.
    static_fav = Path("static") / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)
    root_fav = Path("loki.ico")
    if root_fav.exists():
        return FileResponse(root_fav)
    return JSONResponse(status_code=204, content=None)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    static_fav = Path("static") / "favicon.png"
    if static_fav.exists():
        return FileResponse(static_fav)
    return JSONResponse(status_code=204, content=None)
