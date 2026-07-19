"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import errorlog, metrics
from .db import SessionLocal, init_db
from .routers import (
    accounting,
    analysis,
    assistant,
    auth,
    authoring,
    benchmarking,
    bidding,
    bim,
    carbon,
    closeout,
    codecheck,
    conceptual,
    connections,
    construction,
    contracts,
    convert,
    cost,
    dashboard,
    design,
    documents,
    drafting,
    drawings,
    exports,
    generate,
    ids,
    market,
    modules,
    observability,
    opendata,
    operations,
    parcels,
    payapp,
    payroll,
    plugins,
    prequal,
    pricing,
    procurement,
    proforma,
    properties,
    realestate,
    reports,
    research,
    responsibility,
    review,
    saml,
    schedule,
    scim,
    site,
    standards,
    templates,
    turnover,
    verification,
)
from .routers import (
    jobs as jobs_router,
)

_access_log = logging.getLogger("aec.access")
_log = logging.getLogger("aec.autosync")


_AUTOSYNC_LOCK_KEY = 0x6165635F73796E63          # "aec_sync" — app-wide advisory-lock id


async def _autosync_loop() -> None:
    """Run due Procore auto-sync schedules every minute. With multiple uvicorn workers each process
    runs this loop, so on Postgres a session advisory lock elects one runner per tick (the others
    skip); SQLite deployments are single-process so no lock is needed. Disable with AEC_AUTOSYNC=0."""
    from sqlalchemy import text

    from . import sync
    from .db import SessionLocal

    def _run() -> list:
        with SessionLocal() as db:
            if db.get_bind().dialect.name == "postgresql":
                got = db.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                 {"k": _AUTOSYNC_LOCK_KEY}).scalar()
                if not got:                       # another worker holds this tick — skip quietly
                    return []
                try:
                    return sync.run_due(db)
                finally:
                    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _AUTOSYNC_LOCK_KEY})
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


def _production_guard() -> None:
    """Fail-fast on the misconfigurations that silently ship an open platform.

    "Production" is detected as **not obviously dev**: any non-SQLite DATABASE_URL (Postgres, MySQL,
    MSSQL — dev and the test gate run SQLite) or an explicit `AEC_ENV=production`. On a production
    deployment we refuse to start unless RBAC is on and the auth secret is set — a forgotten env var
    must be a loud crash at boot, not an open API discovered later. A SQLite prod (e.g. a small
    self-host) opts in via `AEC_ENV=production` to get the same protection.
    `AEC_ALLOW_OPEN=1` is the explicit escape hatch for intentionally-open internal deployments."""
    log = logging.getLogger("aec")
    db_url = os.environ.get("DATABASE_URL", "")
    is_server_db = bool(db_url) and not db_url.startswith("sqlite")
    declared_prod = os.environ.get("AEC_ENV", "").strip().lower() in ("production", "prod")
    if (is_server_db or declared_prod) and os.environ.get("AEC_ALLOW_OPEN") != "1":
        from . import auth, rbac
        problems = []
        if not rbac.RBAC_ON:
            problems.append("AEC_RBAC is not '1' — every authenticated user would see every project")
        if auth.secret_is_default():
            problems.append("AEC_AUTH_SECRET is unset — auth tokens are signed with a public dev "
                            "secret and are forgeable")
        if rbac.TRUST_XUSER:
            problems.append("AEC_TRUST_XUSER is '1' — the unauthenticated X-User header is fully "
                            "trusted, allowing anyone to impersonate any user (test-only flag)")
        if os.environ.get("S3_ENDPOINT") and (
                os.environ.get("S3_ACCESS_KEY", "minioadmin") == "minioadmin"
                or os.environ.get("S3_SECRET_KEY", "minioadmin") == "minioadmin"):
            problems.append("S3_ENDPOINT is set but S3_ACCESS_KEY/S3_SECRET_KEY are the default "
                            "'minioadmin' — object storage would be world-accessible")
        if problems:
            raise RuntimeError(
                "refusing to start a production deployment with an unsafe configuration:\n  - "
                + "\n  - ".join(problems)
                + "\nSet the required env vars, or AEC_ALLOW_OPEN=1 to accept an open deployment.")
    # multi-worker + rate limit without Redis: each worker counts independently → limit is per-worker
    workers = os.environ.get("UVICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1"
    if (int(os.environ.get("AEC_RATE_LIMIT_RPM", "0") or "0") > 0
            and not os.environ.get("AEC_REDIS_URL", "").strip()):
        try:
            if int(workers) > 1:
                log.critical("SECURITY: AEC_RATE_LIMIT_RPM is set with %s workers but no "
                             "AEC_REDIS_URL — the limit is per-worker, not global.", workers)
        except ValueError:
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Production safety: tokens signed with the public dev secret are forgeable. Warn loudly when
    # RBAC is on, and hard-fail when AEC_REQUIRE_SECRET=1 (set this in real deployments).
    from . import auth, rbac
    _production_guard()                          # non-SQLite or AEC_ENV=production ⇒ RBAC + real secret, or refuse to boot
    if auth.secret_is_default():
        msg = ("AEC_AUTH_SECRET is not set — auth tokens are signed with a public dev secret and "
               "are forgeable. Set AEC_AUTH_SECRET to a strong random value.")
        if os.environ.get("AEC_REQUIRE_SECRET") == "1":
            raise RuntimeError("refusing to start: " + msg)
        if rbac.RBAC_ON:
            logging.getLogger("aec").critical("SECURITY: %s", msg)
    # PLUGIN-REGISTRY: discover + load recipe plugins at boot (no-op unless AEC_PLUGINS_ENABLED=1 —
    # plugins execute Python at load, so discovery is strictly opt-in). Refusals are logged, never fatal.
    from . import plugin_registry
    plugin_registry.load_all()
    # JOB-QUEUE: start the per-process durable job worker (recovers orphaned running jobs from a crash).
    from . import jobs
    jobs.start_worker()
    task = asyncio.create_task(_autosync_loop()) if os.environ.get("AEC_AUTOSYNC", "1") == "1" else None
    try:
        yield
    finally:
        if task:
            task.cancel()


# RT-ORJSON: Rust-backed JSON for every default response — our biggest payloads (property indexes,
# dashboards, module lists, 4D frames) are exactly orjson's sweet spot (measured 7.1–9.4× vs stdlib
# on representative payloads). Values reaching the response class have already passed FastAPI's
# jsonable_encoder, so this is a drop-in serializer swap. We ship our OWN thin subclass rather than
# fastapi.responses.ORJSONResponse: that class is deprecated (annotated routes now serialize natively
# via Pydantic), but the majority of our endpoints return plain un-annotated dicts, which still render
# through the default response class — where orjson is the win. Graceful fallback keeps any
# orjson-less environment (stale venv) fully functional.
try:
    import orjson as _orjson

    class _OrjsonResponse(JSONResponse):
        # OPT_NON_STR_KEYS mirrors stdlib json (int-keyed rollups, e.g. escalation's by_level {3:1});
        # OPT_SERIALIZE_NUMPY mirrors it for numpy.float64 — a float SUBCLASS stdlib accepted
        # silently, which the analysis engines (takeoff/finance/geometry) emit throughout.
        _OPTS = _orjson.OPT_NON_STR_KEYS | _orjson.OPT_SERIALIZE_NUMPY

        def render(self, content: object) -> bytes:
            return _orjson.dumps(content, option=self._OPTS)

    _DefaultResponse: type[JSONResponse] = _OrjsonResponse
except ImportError:                                                    # pragma: no cover
    _DefaultResponse = JSONResponse

app = FastAPI(title="Massing API", version="0.1.0", lifespan=lifespan,
              default_response_class=_DefaultResponse)


# Request-id: stamp every request with a short id (echo an inbound X-Request-ID if the client/proxy
# set one), expose it on the response header, and stash it on request.state so the error logger and
# the 500 handler can correlate a user-reported failure to its logged row.
@app.middleware("http")
async def _request_id(request: Request, call_next):
    rid = (request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12])[:64]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception):
    """Catch any unhandled server exception: record it to the error-log feed (best-effort, never
    re-raising) and return a clean 500 carrying the request id so a user can quote it. HTTPException,
    validation errors, etc. have their own handlers and never reach here — only real 500s do."""
    rid = getattr(request.state, "request_id", None)
    try:
        db = SessionLocal()
        try:
            errorlog.record(db, source="server", level="error", exc=exc, status=500,
                            method=request.method, path=str(request.url.path),
                            actor=request.headers.get("X-User"), request_id=rid)
        finally:
            db.close()
    except Exception:                        # noqa: BLE001 — the logger must never mask the original
        logging.getLogger("aec").exception("error-log persist failed")
    logging.getLogger("aec").exception("unhandled [%s] %s %s", rid, request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error", "request_id": rid},
                        headers={"X-Request-ID": rid or ""})


# Host-header pinning (DNS-rebind / stray-vhost protection): set AEC_ALLOWED_HOSTS to the
# comma-separated production hostnames (e.g. "app.example.com,api.example.com") and any other Host
# is rejected with 400. Unset (dev/desktop) = no restriction.
_hosts = [h.strip() for h in os.environ.get("AEC_ALLOWED_HOSTS", "").split(",") if h.strip()]
if _hosts:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

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
            # bound memory under IP churn by evicting the OLDEST buckets (LRU-ish via dict insertion
            # order), never clear() — a bulk clear would reset every active counter at once and let a
            # scanning botnet erase the limiter's state for legitimate throttling.
            while len(_rl_buckets) > 10_000:
                _rl_buckets.pop(next(iter(_rl_buckets)), None)
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
app.include_router(plugins.router, tags=["plugins"])
app.include_router(jobs_router.router, tags=["jobs"])
app.include_router(exports.router, tags=["exports"])
app.include_router(analysis.router, tags=["analysis"])
app.include_router(drawings.router, tags=["drawings"])
app.include_router(authoring.router, tags=["authoring"])
app.include_router(modules.router, tags=["modules"])
app.include_router(cost.router, tags=["cost"])
app.include_router(contracts.router, tags=["contracts"])
app.include_router(reports.router, tags=["reports"])
app.include_router(schedule.router, tags=["schedule"])
app.include_router(site.router, tags=["site"])
app.include_router(bidding.router, tags=["bidding"])
app.include_router(templates.router, tags=["templates"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(proforma.router, tags=["proforma"])
app.include_router(generate.router, tags=["generate"])
app.include_router(design.router, tags=["design"])
app.include_router(documents.router, tags=["documents"])
app.include_router(market.router, tags=["market"])
app.include_router(turnover.router, tags=["turnover"])
app.include_router(research.router, tags=["research"])
app.include_router(responsibility.router, tags=["responsibility"])
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
app.include_router(parcels.router, tags=["parcels"])
app.include_router(pricing.router, tags=["pricing"])
app.include_router(closeout.router, tags=["closeout"])
app.include_router(convert.router, tags=["convert"])
app.include_router(auth.router, tags=["auth"])
app.include_router(scim.router, tags=["scim"])
app.include_router(saml.router, tags=["saml"])
app.include_router(connections.router, tags=["connections"])
app.include_router(opendata.router, tags=["opendata"])
app.include_router(realestate.router, tags=["realestate"])
app.include_router(verification.router, tags=["verification"])
app.include_router(payroll.router, tags=["payroll"])
app.include_router(assistant.router, tags=["assistant"])
app.include_router(construction.router, tags=["construction"])
app.include_router(operations.router, tags=["operations"])
app.include_router(standards.router, tags=["standards"])
app.include_router(observability.router, tags=["observability"])


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
        logging.getLogger("aec").warning("readiness DB check failed: %s", exc)   # detail to logs, not response
        return JSONResponse({"status": "unavailable", "db": "down",
                             "error": "database unavailable"}, status_code=503)
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
