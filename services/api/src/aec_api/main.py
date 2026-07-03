"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import metrics
from .db import init_db
from .routers import (accounting, analysis, auth, authoring, benchmarking, bidding, bim, carbon, closeout, codecheck, conceptual, connections, contracts, convert, cost,
                      dashboard, drafting, drawings, ids, exports, generate, modules, opendata, payapp, prequal, pricing, procurement, realestate, reports, research, review, proforma, properties, schedule,
                      templates, verification, payroll, assistant, construction)

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
    # Production safety: tokens signed with the public dev secret are forgeable. Warn loudly when
    # RBAC is on, and hard-fail when AEC_REQUIRE_SECRET=1 (set this in real deployments).
    from . import auth, rbac
    if auth.secret_is_default():
        msg = ("AEC_AUTH_SECRET is not set — auth tokens are signed with a public dev secret and "
               "are forgeable. Set AEC_AUTH_SECRET to a strong random value.")
        if os.environ.get("AEC_REQUIRE_SECRET") == "1":
            raise RuntimeError("refusing to start: " + msg)
        if rbac.RBAC_ON:
            logging.getLogger("aec").critical("SECURITY: %s", msg)
    task = asyncio.create_task(_autosync_loop()) if os.environ.get("AEC_AUTOSYNC", "1") == "1" else None
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="Massing API", version="0.1.0", lifespan=lifespan)

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

# First-layer per-IP rate limit (opt-in: set AEC_RATE_LIMIT_RPM>0 in production). Fixed 60s window.
# Single worker → in-process buckets; for multi-worker set AEC_REDIS_URL and the count is shared via
# an atomic Redis INCR+EXPIRE so the limit holds across processes. Redis is fail-open (any Redis error
# falls back to the in-process count) so limiter infra can never take the API down. Off by default so
# dev/tests aren't throttled; health/metrics are exempt.
_RATE_RPM = int(os.environ.get("AEC_RATE_LIMIT_RPM", "0") or "0")
_REDIS_URL = os.environ.get("AEC_REDIS_URL", "").strip()
if _RATE_RPM > 0:
    _rl_buckets: dict[str, list[int]] = {}      # ip -> [window_minute, count] (in-process fallback)
    _rl_redis = None
    if _REDIS_URL:
        try:                                    # lazy: redis is only a dependency when REDIS_URL is set
            import redis.asyncio as _aioredis
            _rl_redis = _aioredis.from_url(_REDIS_URL, socket_timeout=0.25, socket_connect_timeout=0.25)
        except Exception:                        # noqa: BLE001 — redis not installed / bad URL → in-process
            _rl_redis = None

    def _rl_local(ip: str, win: int) -> int:
        b = _rl_buckets.get(ip)
        if not b or b[0] != win:
            b = [win, 0]
            if len(_rl_buckets) > 10_000:        # bound memory: drop stale windows
                _rl_buckets.clear()
            _rl_buckets[ip] = b
        b[1] += 1
        return b[1]

    async def _rl_count(ip: str, win: int) -> int:
        """Hits for (ip, window). Shared via Redis when configured; fail-open to in-process on error."""
        if _rl_redis is not None:
            try:
                key = f"rl:{ip}:{win}"
                async with _rl_redis.pipeline(transaction=True) as pipe:
                    pipe.incr(key)
                    pipe.expire(key, 65)         # auto-drop one window after it closes
                    count, _ = await pipe.execute()
                return int(count)
            except Exception:                    # noqa: BLE001 — Redis hiccup must not throttle/break requests
                pass
        return _rl_local(ip, win)

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        if request.url.path in ("/health", "/healthz", "/ready", "/readyz", "/metrics"):
            return await call_next(request)
        ip = request.client.host if request.client else "?"
        win = int(time.time() // 60)
        if await _rl_count(ip, win) > _RATE_RPM:
            return Response('{"detail":"rate limit exceeded"}', status_code=429,
                            media_type="application/json", headers={"Retry-After": "60"})
        return await call_next(request)

app.include_router(bim.router, tags=["bim"])
app.include_router(properties.router, tags=["properties"])
app.include_router(exports.router, tags=["exports"])
app.include_router(analysis.router, tags=["analysis"])
app.include_router(drawings.router, tags=["drawings"])
app.include_router(authoring.router, tags=["authoring"])
app.include_router(modules.router, tags=["modules"])
app.include_router(cost.router, tags=["cost"])
app.include_router(contracts.router, tags=["contracts"])
app.include_router(reports.router, tags=["reports"])
app.include_router(schedule.router, tags=["schedule"])
app.include_router(bidding.router, tags=["bidding"])
app.include_router(templates.router, tags=["templates"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(proforma.router, tags=["proforma"])
app.include_router(generate.router, tags=["generate"])
app.include_router(research.router, tags=["research"])
app.include_router(review.router, tags=["review"])
app.include_router(drafting.router, tags=["drafting"])
app.include_router(benchmarking.router, tags=["benchmarking"])
app.include_router(prequal.router, tags=["prequal"])
app.include_router(payapp.router, tags=["payapp"])
app.include_router(accounting.router, tags=["accounting"])
app.include_router(carbon.router, tags=["carbon"])
app.include_router(codecheck.router, tags=["codecheck"])
app.include_router(ids.router, tags=["ids"])
app.include_router(procurement.router, tags=["procurement"])
app.include_router(conceptual.router, tags=["conceptual"])
app.include_router(pricing.router, tags=["pricing"])
app.include_router(closeout.router, tags=["closeout"])
app.include_router(convert.router, tags=["convert"])
app.include_router(auth.router, tags=["auth"])
app.include_router(connections.router, tags=["connections"])
app.include_router(opendata.router, tags=["opendata"])
app.include_router(realestate.router, tags=["realestate"])
app.include_router(verification.router, tags=["verification"])
app.include_router(payroll.router, tags=["payroll"])
app.include_router(assistant.router, tags=["assistant"])
app.include_router(construction.router, tags=["construction"])


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


# --- security hardening: body-size cap · RBAC gate · response headers ---------
_MAX_UPLOAD_BYTES = int(os.environ.get("AEC_MAX_UPLOAD_MB", "1024")) * 1024 * 1024  # default 1 GB
_HSTS = os.environ.get("AEC_HSTS") == "1"   # only when served over HTTPS
# Content-Security-Policy. Default is framing-only (safe everywhere — never restricts resource loads).
# AEC_CSP=1 turns on a strict resource policy tuned for the production bundle (external same-origin
# scripts, inline styles, WASM, blob workers, same-origin XHR); set AEC_CSP=<policy> to fully override.
_CSP_STRICT = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; font-src 'self' data:; worker-src 'self' blob:; "
               "connect-src 'self' https:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
_CSP_ENV = os.environ.get("AEC_CSP", "").strip()
_CSP = "frame-ancestors 'none'" if not _CSP_ENV else (_CSP_STRICT if _CSP_ENV == "1" else _CSP_ENV)
# When AEC_RBAC=1, these prefixes require an authenticated identity — defense in depth so an endpoint
# that lacks its own require_role dependency still can't be reached anonymously. Public auth / health /
# capability / catalog / stateless-compute paths stay open.
_PROTECTED_PREFIXES = ("/projects", "/proforma", "/connections", "/settings", "/audit", "/auth/users",
                       "/convert", "/interop")


def _has_identity(request: Request) -> bool:
    """A valid signed bearer / API key / cookie / signed-URL (or the dev X-User header when trusted)."""
    from . import auth as _auth
    from . import rbac as _rbac
    from . import signing as _signing
    # a valid signed download URL authorizes exactly that path (lets the gate pass without a session)
    qp = request.query_params
    if _signing.verify_path(request.url.path, qp.get("sig"), qp.get("exp")):
        return True
    authz = request.headers.get("authorization", "")
    if authz.startswith("Bearer "):
        tok = authz[len("Bearer "):]
        if _rbac.API_KEY and tok == _rbac.API_KEY:
            return True
        if _auth.verify_token(tok):
            return True
    ck = request.cookies.get("aec_token")
    if ck and _auth.verify_token(ck):
        return True
    return bool(_rbac.TRUST_XUSER and request.headers.get("x-user"))


@app.middleware("http")
async def security(request: Request, call_next):
    from . import rbac as _rbac
    # 1) reject oversized bodies up front (cheap Content-Length check — avoids reading them into memory)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_UPLOAD_BYTES:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    # 2) RBAC gate: when enabled, anonymous callers can't reach protected prefixes at all
    if (_rbac.RBAC_ON and request.method != "OPTIONS"
            and request.url.path.startswith(_PROTECTED_PREFIXES) and not _has_identity(request)):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    resp = await call_next(request)
    # 3) hardening headers on every response (safe set — does not restrict resource loading)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    if _HSTS:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness — the process is up and serving. Cheap, no dependencies; for restart probes."""
    return {"status": "ok"}


_READY_TIMEOUT = float(os.environ.get("AEC_READY_TIMEOUT", "3"))
# Persistent single-thread pool for the readiness ping. A context-managed executor would
# shutdown(wait=True) on exit and block on a hung ping thread — defeating the timeout — so we keep
# one around and never wait on a stuck future (the leaked thread unblocks when the DB recovers or
# its socket timeout fires).
_ready_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ready")


def _db_ping() -> None:
    from sqlalchemy import text as _text
    from .db import engine as _engine
    with _engine.connect() as conn:
        conn.execute(_text("SELECT 1"))


@app.get("/ready")
def ready() -> Response:
    """Readiness — the process can serve real traffic (DB reachable). Pings the DB with a
    trivial `SELECT 1`; returns 503 if it's unreachable so a load balancer / orchestrator stops
    routing to (or restarts) this instance instead of serving 500s. Kept separate from /health
    so a DB blip doesn't kill a still-live process. The ping runs under a hard wall-clock timeout
    so a black-holed DB (paused host / network partition) yields a prompt 503 instead of hanging
    the probe itself."""
    try:
        _ready_pool.submit(_db_ping).result(timeout=_READY_TIMEOUT)
    except concurrent.futures.TimeoutError:
        return JSONResponse({"status": "unavailable", "db": "timeout",
                             "error": f"DB did not respond within {_READY_TIMEOUT:g}s"}, status_code=503)
    except Exception as exc:        # noqa: BLE001 — any DB error means "not ready"
        return JSONResponse({"status": "unavailable", "db": "down", "error": str(exc)[:200]},
                            status_code=503)
    return JSONResponse({"status": "ready", "db": "up"})


# Common orchestrator aliases so probes "just work" regardless of convention.
app.add_api_route("/healthz", health, methods=["GET"], include_in_schema=False)
app.add_api_route("/readyz", ready, methods=["GET"], include_in_schema=False)


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
