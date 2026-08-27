"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hmac
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import errorlog, metrics, otel, ratecount, sentry
from .bodycap import MaxBodySizeMiddleware
from .db import SessionLocal, init_db
from .rbac import require_identified
from .resumable import MAX_UPLOAD_BYTES as _MAX_UPLOAD_BYTES
from .routers import (
    accounting,
    analysis,
    assistant,
    auth,
    authoring,
    bcf_api,
    benchmarking,
    bidding,
    bim,
    carbon,
    classify,
    client_portal,
    closeout,
    cloud,
    codecheck,
    conceptual,
    connections,
    construction,
    contracts,
    convert,
    cost,
    dashboard,
    design,
    digest,
    documents,
    drafting,
    drawings,
    exports,
    generate,
    ids,
    jurisdiction,
    market,
    modules,
    notices,
    observability,
    opendata,
    operations,
    parcels,
    payapp,
    payroll,
    plugins,
    prefab,
    prequal,
    pricing,
    procurement,
    proforma,
    properties,
    realestate,
    recipes,
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
    uploads,
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


def _worker_count() -> int:
    """Configured worker count, defaulting to 1. A non-numeric value reads as 1 — the safe direction,
    because it means we never CLAIM a limit is per-worker when we cannot actually tell."""
    raw = os.environ.get("UVICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1"
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _writer_processes() -> tuple[int, str]:
    """How many processes write this deployment's sidecar indexes, and in words why.

    Two independent routes to more than one, which is the whole point of computing it in one place:
    `UVICORN_WORKERS`, and `AEC_JOB_WORKER=off` moving the job worker into its own container. The
    boot guard asked only about the first for a release and a half after JOB-WORKER-SPLIT invented
    the second, so a deployment with one uvicorn worker and a dedicated worker sailed through it.

    Extracted so `_production_guard` (which refuses) and `/metrics` (which reports) count writers the
    same way. They answer different questions about the same condition and must not drift: the guard
    is only consulted at boot and only on a production deployment, so the deployments it deliberately
    lets past are precisely the ones with nothing but the gauge to say so.

    Both inputs are read at boot and cannot change under a running process, so this is a constant for
    the lifetime of the process — reported per scrape anyway, because the alternative is an operator
    inferring it from a restart they may not have performed.
    """
    from . import jobs
    n = _worker_count()
    if jobs.worker_enabled():
        return n, f"{n} uvicorn worker(s)"
    return n + 1, (f"{n} uvicorn worker(s) plus a dedicated job-worker process "
                   f"({jobs.WORKER_ENV}=off)")


def _rate_limit_is_per_worker() -> bool:
    """True when a rate limit is configured but each of several workers counts it separately.

    Without a shared store every worker keeps its own bucket, so the limit an operator configured is
    silently multiplied by the worker count.
    """
    try:
        rpm = int(os.environ.get("AEC_RATE_LIMIT_RPM", "0") or "0")
    except ValueError:
        return False
    return rpm > 0 and _worker_count() > 1 and not os.environ.get("AEC_REDIS_URL", "").strip()


def _tuned_throttle_buckets() -> list[str]:
    """Buckets whose cap an operator has SET explicitly, via AEC_THROTTLE_<BUCKET>_RPM.

    R39-THROTTLE-SHARED. `throttle.py`'s per-endpoint caps are always on, and until v0.3.876 they
    were counted per process — so on a multi-worker deployment every one of them was silently N x
    its stated value. The guard above covers `AEC_RATE_LIMIT_RPM` only, which is exactly how this
    stayed invisible: **a boot guard about "the rate limit" reads as covering rate limiting.**

    Scoped to buckets the operator TUNED rather than to every bucket, and that is a judgement worth
    stating. The precedent this follows (PERF-RATE, v0.3.721) refuses to boot because *a number the
    operator set* is being silently multiplied — the harm is the belief, not the looseness. A
    built-in default that ends up 4x on a four-worker box is looser than intended but was never
    promised to the operator, and refusing every multi-worker deployment that has not deployed Redis
    would turn "we ship sane defaults" into "you must run Redis". Tuned buckets get the refusal;
    untuned ones get the warning below, and the shared counter fixes both the moment Redis is set.
    """
    if _worker_count() <= 1 or os.environ.get("AEC_REDIS_URL", "").strip():
        return []
    out = []
    for name, raw in os.environ.items():
        if not (name.startswith("AEC_THROTTLE_") and name.endswith("_RPM")):
            continue
        try:                                # a bucket explicitly disabled (0) cannot be multiplied
            if int(raw) > 0:
                out.append(name)
        except ValueError:
            continue
    return sorted(out)


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
        # PERF-RATE — a limit silently N x its configured value is worse than none, because the
        # operator believes it is on. Until v0.3.721 this logged CRITICAL and then started anyway:
        # the loudest possible message, followed by the exact behaviour it warned about. It belongs
        # in `problems` with the rest — same refusal, same AEC_ALLOW_OPEN escape hatch, same
        # production-only scope, so a dev box on SQLite is untouched.
        if _rate_limit_is_per_worker():
            n = _worker_count()
            problems.append(
                f"AEC_RATE_LIMIT_RPM is set with {n} workers and no AEC_REDIS_URL — each worker "
                f"counts independently, so the effective limit is {n}x what you configured. Set "
                "AEC_REDIS_URL for a shared counter, or run a single worker.")
        # R39-THROTTLE-SHARED — the SAME failure, for the other limiter. The check above names
        # AEC_RATE_LIMIT_RPM and so reads as covering rate limiting; it never saw `throttle.py`'s
        # per-endpoint caps, which are always on and were counted per process. A generic-sounding
        # gate hid a missing one until R39-WORKER-SPLIT made two writer processes the norm.
        if (tuned := _tuned_throttle_buckets()):
            n = _worker_count()
            problems.append(
                f"{', '.join(tuned)} set with {n} workers and no AEC_REDIS_URL — each worker "
                f"counts independently, so those caps are {n}x what you configured. Set "
                "AEC_REDIS_URL for a shared counter, or run a single worker.")
        # R35-PIDLOCK-XPROC — the sidecar indexes (docmanager, edit_history) are read-modify-write on
        # a JSON blob in object storage, so nothing but a shared lock arbitrates two workers. On
        # Postgres `pid_lock` takes a session advisory lock; on any other backend serialisation is
        # in-process only, and a second worker can interleave a load->save and silently drop the
        # first writer's entry. That is a real deployment constraint, so it fails at boot rather than
        # living in a docstring — the same reasoning as the per-worker rate limit above.
        #
        # **The dialect comes from DATABASE_URL, and the reason this comment used to give for that
        # was false.** It said the status call "opens a live session, so a transient connection blip
        # would return '' and refuse to boot a perfectly configured Postgres deployment", and that
        # the live-truth surface "stays `cross_process_status()` on /health". Both halves were wrong.
        # It does not connect — `SessionLocal()` is lazy, `db.get_bind()` returns the engine, and the
        # dialect is parsed from the URL string, so it answers "postgresql" for a DSN pointing at an
        # unroutable address (pinned in `test_pid_lock_surface.py`). And nothing was ever added to
        # /health, which is dependency-free on purpose and was never going to be the home.
        #
        # **The true reason is testability, and it was written down in the OTHER file.** The engine is
        # built once, at import, from whatever DATABASE_URL said then — under the test runner that is
        # SQLite whatever a fixture's env claims. `test_perf_rate.py` records that an earlier
        # engine-probing version of this branch "shipped a guard no fixture could ever satisfy", and
        # switching this to the status call broke `test_a_correctly_configured_production_still_starts`
        # inside one run. At boot the two name the same database, so nothing is lost by reading the
        # env var — what had been lost was the *record* of why.
        #
        # They are also not quite the same question, which is why both now exist: this asks whether
        # the database this deployment is CONFIGURED for can serialise; `cross_process_status()` asks
        # whether the engine this process is actually USING can. `/metrics` exports the second as
        # `aec_pid_lock_cross_process` beside `aec_pid_lock_writers` — the runtime answer, for the
        # deployments this guard never sees (SQLite without AEC_ENV, or anything under
        # AEC_ALLOW_OPEN=1).
        #
        # *A stated reason that is false is worse than no comment at all*: the real constraint was
        # standing behind it unrecorded, and it cost a broken test to find.
        #
        # **The population, not just the count.** This asked `_worker_count() > 1` — one route to
        # having two writer processes. JOB-WORKER-SPLIT (v0.3.869) added a second, independent one:
        # `AEC_JOB_WORKER=off` moves the job worker into its OWN process, so a deployment with
        # UVICORN_WORKERS=1 and a dedicated worker container has two writers and sailed straight
        # through this guard. A mutating job in the worker and an API edit on the same project would
        # then interleave with nothing arbitrating them.
        #
        # The guard was correct when written and became wrong when the product grew a new way to do
        # the thing it forbids. That is the failure mode to watch for in any check that enumerates
        # causes rather than measuring the condition: it cannot know about a cause invented later.
        from . import jobs
        writers, why = _writer_processes()
        if writers > 1:
            dialect = db_url.split("://", 1)[0].split("+", 1)[0] if "://" in db_url else "sqlite"
            if dialect != "postgresql":
                problems.append(
                    f"this deployment runs {writers} writer processes ({why}) but the sidecar write "
                    f"lock cannot serialise across them on a {dialect!r} database — two writers can "
                    "interleave a document-index write and silently lose one. Use Postgres, or run "
                    f"a single uvicorn worker with {jobs.WORKER_ENV} unset (in-process job worker).")
        if problems:
            raise RuntimeError(
                "refusing to start a production deployment with an unsafe configuration:\n  - "
                + "\n  - ".join(problems)
                + "\nSet the required env vars, or AEC_ALLOW_OPEN=1 to accept an open deployment.")
    elif _rate_limit_is_per_worker():
        # Outside a production deployment (or with AEC_ALLOW_OPEN=1) this is still worth saying,
        # but a warning is the honest level: nobody is relying on it to hold back the internet.
        log.warning("AEC_RATE_LIMIT_RPM is per-worker with %s workers and no AEC_REDIS_URL — the "
                    "effective limit is %sx the configured one.", _worker_count(), _worker_count())
    # R39-THROTTLE-SHARED — the per-endpoint caps in `throttle.py` are ALWAYS on, so unlike the
    # limiter above there is no "configured" condition to gate this on. Untuned buckets get a
    # warning rather than a refusal (see `_tuned_throttle_buckets` for why), but they get one
    # unconditionally, because "nothing was said" is what let the per-worker multiplication survive
    # R39-WORKER-SPLIT unnoticed. Runs whether or not the production guard did.
    if _worker_count() > 1 and not os.environ.get("AEC_REDIS_URL", "").strip():
        log.warning("throttle.py's per-endpoint caps are counted per process: with %s workers and "
                    "no AEC_REDIS_URL every bucket (including stepup at 10/min) is effectively %sx "
                    "its stated limit. Set AEC_REDIS_URL for a shared counter.",
                    _worker_count(), _worker_count())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # External error alerting: no-op unless AEC_SENTRY_DSN/SENTRY_DSN is set. Init early so a failure
    # in any later startup step is itself reported; fail-open so it can never block boot.
    sentry.init()
    # Distributed tracing: no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set. Independent of Sentry and
    # equally fail-open. Configures the tracer provider/exporter + DB spans; the FastAPI request-span
    # middleware was already attached at app construction (see below) since Starlette forbids adding
    # middleware after startup.
    otel.init()
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
    # JOB-WORKER-SPLIT: unless AEC_JOB_WORKER=off, in which case a dedicated worker process must be
    # running. Log it loudly — an API with no worker anywhere accepts every enqueue, writes every row,
    # tells every caller the work is under way, and never does any of it. Nothing raises, so the only
    # signal that configuration is wrong is this line.
    from . import jobs
    if jobs.worker_enabled():
        jobs.start_worker()
    else:
        logging.getLogger("aec").warning(
            "JOB-QUEUE: in-process worker disabled (%s=off). A dedicated worker must be running "
            "(`python -m aec_api.worker`) or queued jobs will never run and nothing will raise.",
            jobs.WORKER_ENV)
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

# OTel FastAPI request-span instrumentation must be attached here, at construction, because Starlette
# refuses to add middleware once the app has started serving (and lifespan runs after that point).
# No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set; fail-open. The tracer provider is configured later
# in the lifespan (otel.init()) and resolves lazily at span time, so ordering is fine.
otel.instrument_app(app)


# Request-id: stamp every request with a short id (echo an inbound X-Request-ID if the client/proxy
# set one), expose it on the response header, and stash it on request.state so the error logger and
# the 500 handler can correlate a user-reported failure to its logged row.
@app.middleware("http")
async def _request_id(request: Request, call_next):
    rid = (request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12])[:64]
    request.state.request_id = rid
    # Correlate the trace with this request-id (no-op unless OTel tracing is enabled). Set here where
    # the id is known and the current span is the FastAPI server span.
    otel.set_request_id(rid)
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
    # Additive external alerting: this handler catches the exception before Sentry's auto-capture
    # would, so report it explicitly. No-op when unconfigured; fail-open so it never affects the 500.
    sentry.capture_exception(exc, request_id=rid)
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
# AEC_CORS_ORIGINS (comma-separated) overrides the dev default. The default covers BOTH the
# localhost and 127.0.0.1 forms of the Vite origin — they are distinct CORS origins, and the web
# app's own default API URL is the 127.0.0.1 form (apps/web/.env.local), so a dev opening the app at
# http://127.0.0.1:5173 would otherwise be blocked even with the API running.
# `_MAX_UPLOAD_BYTES` is imported at the top from `resumable`, which owns the single definition:
# the ASGI body-size middleware and the resumable handshake must refuse at the same size, and a
# second `int(os.environ[...])` here is the kind of value that drifts the first time it changes.

# R39-UPLOAD-CAP-APP / R41-UPLOAD-WARK — MEASURE the body, do not take its word for it. The
# Content-Length check in `security` below is kept as a cheap early refusal, but it is not the
# bound: with no such header (chunked transfer-encoding, the ordinary HTTP/1.1 case) that condition
# short-circuits and the body was never measured at all. See `bodycap` for why this has to sit on
# the ASGI `receive` rather than inside a BaseHTTPMiddleware.
#
# Registered BEFORE CORS on purpose. Starlette makes the LAST-added middleware the outermost, so
# adding this first leaves CORS outside it — which is what lets a cross-origin uploader read the
# 413 instead of seeing an opaque CORS failure with no explanation.
app.add_middleware(MaxBodySizeMiddleware, max_bytes=_MAX_UPLOAD_BYTES)

_cors = os.environ.get("AEC_CORS_ORIGINS",
                       "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    # A custom response header is INVISIBLE to cross-origin JS unless it is named here. Only the
    # seven CORS-safelisted ones (content-type, content-length, cache-control, …) come through for
    # free, so every `res.headers.get("X-…")` in the web client needs its name in this list or it
    # reads `null` — in a browser, always, with no error anywhere.
    #
    # Measured 2026-08-09 against the running API from a real cross-origin page: the browser could
    # see exactly ["content-length", "content-type"] and `X-Element-Guid` came back null. Three reads
    # had been dead since they were written:
    #
    #   X-Element-Guid   -> `|| ""` swallowed it, so an authored element's preview id silently fell
    #                       back to a timestamp instead of the GUID.
    #   X-Seal-Sealed    -> `=== "true"` on null is FALSE, so a PDF genuinely sealed by a licensed
    #                       PE/RA reported back as **not sealed**. A false negative about a
    #                       professional seal is the worst of the three by a distance.
    #   X-Seal-Compliance-> `|| ""` again: the compliance note vanished.
    #
    # This is the shape the codebase keeps meeting — a read that cannot fail loudly, wearing a
    # default that looks like a legitimate answer. `test_cors_expose_headers.py` now derives the
    # population from the client instead of trusting this list to be maintained by hand.
    expose_headers=["Content-Disposition", "X-Element-Guid", "X-Seal-Sealed", "X-Seal-Compliance"],
)

# First-layer per-IP rate limit (opt-in: set AEC_RATE_LIMIT_RPM>0 in production). Fixed 60s window.
# Single worker → in-process buckets; for multi-worker set AEC_REDIS_URL and the count is shared via
# an atomic Redis INCR+EXPIRE so the limit holds across processes. Redis is fail-open (any Redis error
# falls back to the in-process count) so limiter infra can never take the API down. Off by default so
# dev/tests aren't throttled; health/metrics are exempt.
_RATE_RPM = int(os.environ.get("AEC_RATE_LIMIT_RPM", "0") or "0")
_REDIS_URL = os.environ.get("AEC_REDIS_URL", "").strip()
if _RATE_RPM > 0:

    async def _rl_count(ip: str, win: int) -> int:
        """Hits for (ip, window). Shared via Redis when configured; fail-open to in-process on error.

        R39-THROTTLE-SHARED: the implementation moved to `ratecount`, unchanged, so the per-endpoint
        limiter in `throttle.py` can use the same counter instead of a second one. That limiter kept
        its own in-process dict — and the boot guard below, which covers THIS limiter, read to anyone
        checking as though rate limiting in general were protected against the multi-worker mistake.
        """
        return await ratecount.count("rl", ip, win)

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
app.include_router(bcf_api.router, tags=["bcf-api"])
app.include_router(properties.router, tags=["properties"])
app.include_router(plugins.router, tags=["plugins"])
app.include_router(jobs_router.router, tags=["jobs"])
app.include_router(exports.router, tags=["exports"])
app.include_router(analysis.router, tags=["analysis"])
app.include_router(client_portal.router, tags=["client-portal"])
app.include_router(drawings.router, tags=["drawings"])
app.include_router(authoring.router, tags=["authoring"])
app.include_router(modules.router, tags=["modules"])
app.include_router(cost.router, tags=["cost"])
app.include_router(contracts.router, tags=["contracts"])
app.include_router(reports.router, tags=["reports"])
app.include_router(recipes.router, tags=["recipes"])
app.include_router(schedule.router, tags=["schedule"])
app.include_router(prefab.router, tags=["prefab"])
app.include_router(site.router, tags=["site"])
app.include_router(bidding.router, tags=["bidding"])
app.include_router(templates.router, tags=["templates"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(digest.router, tags=["digest"])
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
app.include_router(notices.router, tags=["notices"])
app.include_router(payapp.router, tags=["payapp"])
app.include_router(accounting.router, tags=["accounting"])
app.include_router(carbon.router, tags=["carbon"])
app.include_router(codecheck.router, tags=["codecheck"])
app.include_router(classify.router, tags=["classify"])
app.include_router(ids.router, tags=["ids"])
app.include_router(procurement.router, tags=["procurement"])
app.include_router(conceptual.router, tags=["conceptual"])
app.include_router(parcels.router, tags=["parcels"])
app.include_router(pricing.router, tags=["pricing"])
app.include_router(closeout.router, tags=["closeout"])
app.include_router(convert.router, tags=["convert"])
app.include_router(uploads.router, tags=["uploads"])   # R41-UPLOAD-WARK resumable handshake
app.include_router(auth.router, tags=["auth"])
app.include_router(cloud.router, tags=["cloud"])
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
app.include_router(jurisdiction.router, tags=["jurisdiction"])
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
# `_MAX_UPLOAD_BYTES` is defined above, beside the MaxBodySizeMiddleware registration that is
# the real bound. It was declared here, next to the Content-Length check that reads it — which
# is exactly why that check read as the cap: the constant and the only visible use of it sat
# together, and nothing in view said the pair covered only requests that declare a length.
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
                       "/convert", "/interop", "/pipeline", "/routines", "/cloud")
# `/cloud` (CLOUD-LIBRARY) is here because every route under it reads one user's massing.cloud vault
# — tenant state by definition. Note `/auth/cloud/*` is deliberately NOT covered: sign-in has to be
# reachable by someone who is not signed in yet, which is the whole point of it. Those routes carry
# their own `require_identified` individually, except `login`/`callback`/`status`, which must serve
# an anonymous caller. This prefix is defence in depth and NOT the gate — the routes under it each
# take `require_identified`, because an armed middleware makes a guarded and an unguarded route look
# identical from outside, and then nothing is testing the route's own guard.


def _routed_path(request: Request) -> str:
    """The path the router actually matched on.

    Security decisions must key off `scope["path"]`, not `request.url.path`. The latter is
    *reconstructed* by re-parsing "http://{host}{path}", so a Host header carrying "/", "?" or "#"
    can make it disagree with the path that routing used — the bug class behind CVE-2026-48710.
    The pinned Starlette validates the Host header, so this is defence in depth rather than a live
    hole; it removes the dependency of an auth gate on a transport-layer parsing detail.
    """
    return request.scope.get("path") or request.url.path


def _has_identity(request: Request) -> bool:
    """A valid signed bearer / API key / cookie / signed-URL (or the dev X-User header when trusted)."""
    from . import auth as _auth
    from . import rbac as _rbac
    from . import signing as _signing
    # a valid signed download URL authorizes exactly that path (lets the gate pass without a session)
    qp = request.query_params
    if _signing.verify_path(_routed_path(request), qp.get("sig"), qp.get("exp")):
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
            and _routed_path(request).startswith(_PROTECTED_PREFIXES)
            and not _has_identity(request)):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    resp = await call_next(request)
    # 3) hardening headers on every response (safe set — does not restrict resource loading)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    if _HSTS:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    # 4) don't let tenant data sit in a cache we don't control. Until now nothing set Cache-Control
    #    outside the SSE streams, so project records, financials and audit feeds were served with no
    #    policy at all — free for a browser disk cache or a shared corporate proxy to retain, and for
    #    the back/forward cache to redisplay after a sign-out.
    #
    #    Scoped to JSON on purpose. `no-store` on everything would also kill caching of the .frag
    #    geometry stream and map tiles, which a viewer refetches constantly and which is where this
    #    product's bytes actually are — a real performance regression bought for no security. Binary
    #    payloads that ARE sensitive (a rendered contract PDF) are already reached through a signed,
    #    expiring URL. `setdefault` so the SSE routes keep their own `no-cache`.
    if resp.headers.get("content-type", "").startswith("application/json"):
        resp.headers.setdefault("Cache-Control", "no-store")
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


def _metrics_auth_enabled() -> bool:
    """Read per-request so operators can flip the gate without a code change / restart-only rebuild."""
    return os.environ.get("AEC_METRICS_AUTH", "").strip().lower() in ("1", "true", "yes", "on")


def _guard_metrics(request: Request) -> None:
    """Optional bearer gate for /metrics. OFF by default → open exactly as before (existing scrapers
    keep working, no breaking change). Set AEC_METRICS_AUTH=1 to require the AEC_API_KEY bearer when
    the scrape endpoint is reachable from an untrusted network. Reuses the same API-key credential as
    the other protected paths."""
    if not _metrics_auth_enabled():
        return
    from . import rbac as _rbac
    key = _rbac.API_KEY or os.environ.get("AEC_API_KEY")
    authz = request.headers.get("authorization", "")
    tok = authz[len("Bearer "):] if authz.startswith("Bearer ") else ""
    if not (key and hmac.compare_digest(tok, key)):
        raise HTTPException(status_code=401, detail="metrics authentication required")


@app.get("/metrics/budget")
def perf_budget_report(_: None = Depends(_guard_metrics)) -> dict:
    """R24-PERF-BUDGET — the stated performance budgets, and which of them anything measures.

    Three budgets are stated: request p95 < 100 ms, click echo < 100 ms, panel load < 1 s. As of
    v0.3.1063 **two of the three are measured**: the first from the live server histogram, and
    `click_echo` by browser beacon into `metrics.observe_client` — nothing here can see the interval
    between a click and the paint answering it. `panel_load` is still `unmeasured`, and its reason
    changed rather than vanished: the beacon it was waiting for exists, but this app has no single
    moment where a panel becomes usable, so there is nothing honest to time yet.

    Any budget still lacking a measurement is returned as `unmeasured` **with the reason**, and a
    measurable one with nothing reported comes back `no_observations`, never omitted. A report that
    lists three budgets and quietly evaluates one is how a green result comes to imply more than was
    tested; a budget that vanishes when its beacon breaks is the same failure arriving later.

    The p95 is a histogram bucket UPPER bound, not an interpolated point — and a None quantile has
    two opposite causes: no observations, or a tail beyond the largest bucket. The second is a
    FAILURE, because reading None as "no problem" would make this pass hardest exactly when latency
    is worst. That rule is applied to the client budgets by the SAME code, not a gentler copy.

    **`within_budget` is now an AND across every MEASURED budget**, so a slow client fails it.
    Whoever watches this should know the client figure is per-process and survivor-weighted — a
    browser that hung hard enough never to beacon is absent from it.

    Same gate as /metrics: open by default, behind the bearer with AEC_METRICS_AUTH=1.
    """
    from . import perf_budget
    client = {name: (metrics.client_quantile(name, 0.95), metrics.client_count(name))
              for name, spec in perf_budget.BUDGETS.items()
              if spec["side"] == "client" and spec["measurable"]}
    return perf_budget.report(metrics.quantile(0.95), metrics._hist_inf, client)


@app.post("/metrics/client")
def record_client_interval(body: dict = Body(...),
                           _user: str = Depends(require_identified)) -> dict:
    """R24-PERF-BUDGET — one client-side interval, reported by the browser beacon.

    The two client budgets (click echo, panel load) describe things only a browser can see, so the
    only way to measure them is to let the browser say. This is the sink; the beacon is
    `apps/web/src/ui/perfBeacon.ts`.

    **Not behind `_guard_metrics`.** That gate protects READING the metrics surface and is satisfied
    by an operator bearer no browser has. Writing needs the opposite test — is this one of our
    signed-in users — so it takes `require_identified`. Leaving it open would hand anyone on the
    internet a way to shift a percentile an operator makes decisions from: not a data breach, a way
    to make the instrument lie, which is harder to notice.

    **`require_identified`, not `Depends(current_user)`.** `current_user` IDENTIFIES and does not
    AUTHORISE — with RBAC on it returns the literal string "anonymous", so depending on it is a name
    rather than a gate. Routes have shipped with exactly that mistake twice, and the first draft of
    this one made it a third: it took `current_user` and hand-rolled the anonymous check in the body,
    which works but is invisible to the static walker in `test_global_authz` and would have gone into
    the baseline as an unguarded global route.

    **The budget name is matched against `BUDGETS`, never used as a key directly.** It arrives from a
    browser, and `observe_client` would happily create a histogram for any string it is given — so an
    unvalidated name is an unbounded, caller-controlled dict of series in a long-lived process.

    Out-of-range and non-numeric values are DROPPED rather than clamped to the boundary, and the
    response says so. Clamping a hostile 9,999 s to 10 s would file it in the slowest real bucket and
    quietly move the p95; dropping it leaves the percentile describing only intervals a browser could
    actually have produced. The same reasoning as the load-timing sink, which clamps because its rows
    are read individually — here they are only ever read as an aggregate.
    """
    from . import perf_budget
    name = str(body.get("budget") or "")
    spec = perf_budget.BUDGETS.get(name)
    if spec is None or spec.get("side") != "client" or not spec.get("measurable"):
        raise HTTPException(status_code=422, detail=f"not a measurable client budget: {name!r}")
    v = body.get("ms")
    # NaN and inf never compare into the range, so they fall out here rather than reaching a bucket.
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 <= v <= 600_000):
        return {"recorded": False, "reason": "not a plausible interval in milliseconds"}
    metrics.observe_client(name, float(v) / 1000.0)
    return {"recorded": True}


@app.get("/metrics")
def prometheus_metrics(_: None = Depends(_guard_metrics)) -> Response:
    """Prometheus text exposition (request counts, latencies, in-flight, uptime). Open by default;
    gate behind the AEC_API_KEY bearer by setting AEC_METRICS_AUTH=1.

    JOB-STALL-VISIBLE appends the queue gauges. The DB read is deliberately wrapped: a scrape that
    500s because the database blinked loses the request metrics too, which are in-process and were
    perfectly fine. On failure the queue block reports `aec_jobs_stats_ok 0` and omits the rest —
    that is why the ok-gauge exists, so "could not measure" never renders as "nothing queued".
    """
    from . import jobs, pid_lock
    body = metrics.render()
    stats = None
    try:
        with SessionLocal() as db:
            stats = jobs.queue_stats(db)
    except Exception:                                  # noqa: BLE001 — never fail a scrape on this
        logging.getLogger("aec").warning("metrics: could not read the job queue", exc_info=True)
    body += "\n".join(metrics.render_queue(stats, jobs.worker_enabled())) + "\n"
    # R37-TESTED-UNWIRED — the sidecar write lock's real serialisation. Unwrapped, unlike the queue
    # read above, because `cross_process_status()` never connects: it reads the dialect off the
    # engine, which parses it from DATABASE_URL. It also swallows its own exceptions and degrades to
    # dialect "unknown". Wrapping it here would suggest a failure mode it does not have.
    body += "\n".join(metrics.render_pid_lock(pid_lock.cross_process_status(),
                                              _writer_processes()[0])) + "\n"
    return Response(body, media_type="text/plain; version=0.0.4; charset=utf-8")


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
