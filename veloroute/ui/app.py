"""
VeloRoute Dashboard API
=======================
Fully dynamic REST API with token auth.
All state is managed in memory on the running VeloRoute client instance.
"""
from pathlib import Path
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as api_router
from veloroute.gateway.keys import GatewayAuthError

# ─── App setup ───────────────────────────────────────────────────────────────
app = FastAPI(title="VeloRoute Dashboard API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    # The dashboard is served by this app, so same-origin requests need no
    # CORS exception. Deployments with a separate frontend can opt in to the
    # exact trusted origins through VELOROUTE_CORS_ORIGINS.
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("VELOROUTE_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Serve static files from the root public directory if it exists
public_dir = Path(__file__).resolve().parent.parent.parent.parent / "public"
if public_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/public", StaticFiles(directory=str(public_dir)), name="public")

app.include_router(api_router)


@app.exception_handler(GatewayAuthError)
async def gateway_auth_error_handler(request: Request, exc: GatewayAuthError):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers=exc.headers,
    )

@app.on_event("startup")
async def startup_event():
    from .routes.deps import llm_client
    if llm_client.storage:
        await llm_client.storage.connect()
        await llm_client.router.groups.load()
        await llm_client.router.load()
        await llm_client.virtual_keys.load()

# ─── Serve SPA ───────────────────────────────────────────────────────────────
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg_icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">⚡</text></svg>'
    return Response(content=svg_icon, media_type="image/svg+xml")

@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    try:
        return templates.TemplateResponse(request, "base.html")
    except TypeError:
        return templates.TemplateResponse(name="base.html", context={"request": request})


from fastapi.responses import PlainTextResponse

@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    from veloroute.observability import get_metrics
    return get_metrics().render()


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "veloroute"}

