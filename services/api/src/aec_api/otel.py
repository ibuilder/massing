"""OpenTelemetry distributed tracing — TRACES ONLY, env-gated no-op until an OTLP endpoint is set.

The request-id + JSON access log tell you *that* a request was slow or failed; they can't show you
*where* the time went once the request hops API → Postgres → MinIO → converter. This wires OTel
tracing so that hop-by-hop span tree is exported to any OTLP-compatible collector (Jaeger / Tempo /
Datadog all accept OTLP/HTTP).

No-op by default: nothing initializes unless `OTEL_EXPORTER_OTLP_ENDPOINT` (or the traces-specific
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) is set — endpoint unset = identical app behavior, no provider,
no exporter, no network. Traces only: this module never exports metrics or logs. Everything fails
open — an init or export error is logged and swallowed so it can never block boot or mask a response.

This coexists with `sentry.py` (PR #73): Sentry stays error alerting (`traces_sample_rate=0`), OTel
owns tracing. Both init independently and idempotently in the FastAPI lifespan.

Why FastAPI instrumentation is attached at app construction, not here in init(): Starlette refuses to
`add_middleware` once the app has started serving (and the lifespan runs *after* the middleware stack
is built), so `instrument_app()` must run while the app is still being wired up. See
`instrument_app()` below, called from main.py right after the FastAPI() instance is created. The
tracer provider it will use is configured later, in init() during lifespan — the tracer resolves the
active provider lazily at span-creation time, and lifespan startup always runs before the first
request, so spans always see the configured provider.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger("aec.otel")

# Flipped true only once init() has fully succeeded, so set_request_id() is a cheap no-op otherwise
# (and so the endpoint-unset path provably never touches the SDK / network).
_ENABLED = False

# Liveness/readiness/scrape probes fire constantly and carry no useful trace — matched as substrings
# against the request path by the FastAPI instrumentation's excluded_urls.
_EXCLUDED_URLS = "health,ready,metrics"

_DEFAULT_SAMPLE_RATE = 0.1


def _endpoint() -> str:
    return (os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()


def enabled() -> bool:
    return _ENABLED


def _sample_rate() -> float:
    """Fraction of *root* traces to sample (children follow their parent — see ParentBased below).
    Defaults to 0.1 so enabling tracing never means a 100% overhead surprise; set 1.0 during an
    incident to capture everything. Malformed/out-of-range values clamp to the [0, 1] default."""
    try:
        rate = float(os.environ.get("AEC_OTEL_TRACES_SAMPLE_RATE", str(_DEFAULT_SAMPLE_RATE))
                     or _DEFAULT_SAMPLE_RATE)
    except (TypeError, ValueError):
        return _DEFAULT_SAMPLE_RATE
    if rate < 0.0:
        return 0.0
    if rate > 1.0:
        return 1.0
    return rate


def _service_name() -> str:
    return (os.environ.get("AEC_OTEL_SERVICE_NAME")
            or os.environ.get("AEC_ENV") or "massing-api")


def instrument_app(app) -> bool:
    """Attach FastAPI request-span instrumentation to `app`. MUST be called at app construction time
    (Starlette forbids adding middleware once the app has started). No-op unless an OTLP endpoint is
    configured; idempotent; fail-open. Returns True when instrumentation was attached.

    Privacy: no header or body capture is enabled (we pass no capture_* kwargs and set none of the
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_* env vars), so auth headers, cookies and request
    bodies never become span attributes. Probe URLs are excluded to cut noise."""
    if not _endpoint():
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if getattr(app, "_is_instrumented_by_opentelemetry", False):
            return True
        FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)
        return True
    except Exception:                       # noqa: BLE001 — instrumentation must never block boot
        _log.warning("OpenTelemetry FastAPI instrumentation failed; request spans disabled",
                     exc_info=True)
        return False


def init() -> bool:
    """Configure the tracer provider + OTLP/HTTP exporter + DB instrumentation. Called once early in
    the FastAPI lifespan (alongside sentry.init()). No-op unless an OTLP endpoint is set; idempotent;
    fail-open. Returns True when tracing was enabled."""
    global _ENABLED
    if _ENABLED:
        return True                         # idempotent — never build a second provider/exporter
    if not _endpoint():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

        rate = _sample_rate()
        service = _service_name()
        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: service}),
            # ParentBased: honor an upstream service's sampling decision (so a trace isn't half
            # captured), and for root spans sample at `rate`.
            sampler=ParentBased(TraceIdRatioBased(rate)),
        )
        # OTLPSpanExporter reads the endpoint (and any OTEL_EXPORTER_OTLP_HEADERS) from the standard
        # env vars — no request headers/bodies are ever attached to spans by us. BatchSpanProcessor
        # exports off the request path so exporter latency/errors never block a response.
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        _instrument_db()

        _ENABLED = True
        _log.info("OpenTelemetry tracing enabled (service=%s, sample_rate=%s, endpoint=%s)",
                  service, rate, _endpoint())
        return True
    except Exception:                       # noqa: BLE001 — an OTel failure must never block boot
        _ENABLED = False
        _log.warning("OpenTelemetry init failed; tracing disabled", exc_info=True)
        return False


def _instrument_db() -> None:
    """Instrument the shared SQLAlchemy engine for query spans. enable_commenter=False: do NOT inject
    a SQL comment or capture bound parameter values — the span's db.statement carries the
    parametrized query shape only, never user data."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from .db import engine
    SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=False)


def set_request_id(request_id: str | None) -> None:
    """Attach the middleware's request-id to the current (FastAPI server) span so a trace correlates
    with the JSON access log and the Sentry event tag. Called from the request-id middleware where
    the id is already known — not via an instrumentation hook whose ordering is uncertain. No-op
    unless tracing is enabled; fails open."""
    if not _ENABLED or not request_id:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None:
            span.set_attribute("request_id", request_id)
    except Exception:                       # noqa: BLE001 — correlation is best-effort, never fatal
        pass
