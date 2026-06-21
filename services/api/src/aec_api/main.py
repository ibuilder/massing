"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from . import metrics
from .db import init_db
from .routers import (analysis, auth, authoring, bidding, bim, connections, convert, cost, dashboard,
                      drawings, exports, generate, modules, proforma, properties, schedule, templates)

_access_log = logging.getLogger("aec.access")
_log = logging.getLogger("aec.autosync")


async def _autosync_loop() -> None:
    """Run due Procore auto-sync schedules every minute. Per-process (single-worker / dev);
    for multi-worker, run a single scheduler or use a DB lock. Disable with AEC_AUTOSYNC=0."""
    from . import sync
    from .db import SessionLocal

    def _run() -> list:
        with SessionLocal() as db:
            return sync.run_due(db)

    while True:
        try:
            await asyncio.sleep(60)
            ran = await asyncio.to_thread(_run)
            if ran:
                _log.info("auto-sync ran %d schedule(s)", len(ran))
        except asyncio.CancelledError:
            break
        except Exception as e:                   # noqa: BLE001 — the loop must survive any error
            _log.warning("auto-sync tick failed: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    task = asyncio.create_task(_autosync_loop()) if os.environ.get("AEC_AUTOSYNC", "1") == "1" else None
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="AEC BIM Platform API", version="0.1.0", lifespan=lifespan)

# In production the web app calls the API same-origin via nginx's /api proxy, so CORS
# is moot. CORS only matters for the dev server (:5173) or direct cross-origin access;
# AEC_CORS_ORIGINS (comma-separated) overrides the dev default.
_cors = os.environ.get("AEC_CORS_ORIGINS", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(bim.router, tags=["bim"])
app.include_router(properties.router, tags=["properties"])
app.include_router(exports.router, tags=["exports"])
app.include_router(analysis.router, tags=["analysis"])
app.include_router(drawings.router, tags=["drawings"])
app.include_router(authoring.router, tags=["authoring"])
app.include_router(modules.router, tags=["modules"])
app.include_router(cost.router, tags=["cost"])
app.include_router(schedule.router, tags=["schedule"])
app.include_router(bidding.router, tags=["bidding"])
app.include_router(templates.router, tags=["templates"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(proforma.router, tags=["proforma"])
app.include_router(generate.router, tags=["generate"])
app.include_router(convert.router, tags=["convert"])
app.include_router(auth.router, tags=["auth"])
app.include_router(connections.router, tags=["connections"])


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    """Record metrics + a structured access-log line per request. Uses the matched route
    template (not the raw path) so metric labels don't explode on ids."""
    t0 = time.perf_counter()
    metrics.inflight(1)
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        metrics.inflight(-1)
        dur = time.perf_counter() - t0
        route = getattr(request.scope.get("route"), "path", None) or "unmatched"
        metrics.observe(request.method, route, status, dur)
        _access_log.info(json.dumps({
            "method": request.method, "route": route, "status": status,
            "dur_ms": round(dur * 1000, 1),
        }))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def prometheus_metrics() -> Response:
    """Prometheus text exposition (request counts, latencies, in-flight, uptime)."""
    return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


# Single-process desktop build: serve the built web app from the same origin as the API, so the
# Tauri .exe (or `python -m aec_api.desktop`) needs no nginx. Gated on AEC_WEB_DIST so the Docker
# deployment (nginx serves the SPA, proxies /api) is unaffected. Registered LAST so every explicit
# API route still wins; the catch-all mount only handles the SPA + its assets. COOP/COEP keep the
# page cross-origin isolated for web-ifc's multithreaded WASM (SharedArrayBuffer).
_WEB_DIST = os.environ.get("AEC_WEB_DIST")
if _WEB_DIST and os.path.isdir(_WEB_DIST):
    from fastapi.staticfiles import StaticFiles

    @app.middleware("http")
    async def _cross_origin_isolation(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        return resp

    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
