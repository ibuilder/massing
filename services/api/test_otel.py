"""OpenTelemetry tracing: env-gated no-op, fail-open init, request-id correlation, probe exclusion,
and privacy (no header/body/param capture). Everything runs against fake OTel SDK/exporter/
instrumentation modules injected into sys.modules, so nothing touches the network or needs the real
(unpinned-in-this-sandbox) packages installed.
Run: PYTHONPATH=src:../data/src python3 test_otel.py"""
import os
import sys
import types

os.environ["DATABASE_URL"] = "sqlite:///./test_otel.db"
os.environ["STORAGE_DIR"] = "./test_storage_otel"
os.environ["AEC_LOCAL_MODE"] = "1"          # single-operator mode → no IdP needed in tests
os.environ.pop("AEC_RBAC", None)
for _k in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
           "AEC_OTEL_TRACES_SAMPLE_RATE", "AEC_OTEL_SERVICE_NAME"):
    os.environ.pop(_k, None)                 # start from a known endpoint-unset state
for _f in ("./test_otel.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from opentelemetry import trace as _real_trace  # noqa: E402  (real API pkg; SDK is faked below)

from aec_api import otel  # noqa: E402
from aec_api.main import app  # noqa: E402


# --- a registry capturing everything the fakes were asked to do -----------------------------------
class _Rec:
    def __init__(self):
        self.exporter_raises = False
        self.exporter_kwargs = None
        self.processors = []
        self.provider = None
        self.resource_attrs = None
        self.sampler = None                  # ("ParentBased", ratio)
        self.set_provider_arg = None
        self.instrument_app_kwargs = None
        self.sqla_instrument_kwargs = None
        self.span_attrs = {}


rec = _Rec()


def _install_fake_otel(r: _Rec):
    """Inject a fake OTel SDK / OTLP exporter / instrumentation tree into sys.modules. otel.py
    lazy-imports these inside its functions, so installing them before calling init()/instrument_app()
    is enough — no real package required, no network."""

    class OTLPSpanExporter:
        def __init__(self, **kw):
            if r.exporter_raises:
                raise RuntimeError("otlp exporter construction failed")
            r.exporter_kwargs = kw

    class BatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter
            r.processors.append(self)

    class Resource:
        @staticmethod
        def create(attrs):
            r.resource_attrs = attrs
            return ("resource", attrs)

    class TraceIdRatioBased:
        def __init__(self, ratio):
            self.ratio = ratio

    class ParentBased:
        def __init__(self, root):
            self.root = root
            r.sampler = ("ParentBased", getattr(root, "ratio", None))

    class TracerProvider:
        def __init__(self, resource=None, sampler=None):
            self.resource = resource
            self.sampler = sampler
            self.processors = []
            r.provider = self

        def add_span_processor(self, p):
            self.processors.append(p)

    class FastAPIInstrumentor:
        @classmethod
        def instrument_app(cls, app, **kw):
            r.instrument_app_kwargs = kw
            app._is_instrumented_by_opentelemetry = True

    class SQLAlchemyInstrumentor:
        def instrument(self, **kw):
            r.sqla_instrument_kwargs = kw

    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    # Parent packages must exist in sys.modules so the dotted `from a.b.c import X` resolves without
    # trying to import the (absent) real submodules.
    mods = {
        "opentelemetry.sdk": _mod("opentelemetry.sdk"),
        "opentelemetry.sdk.resources": _mod("opentelemetry.sdk.resources",
                                            Resource=Resource, SERVICE_NAME="service.name"),
        "opentelemetry.sdk.trace": _mod("opentelemetry.sdk.trace", TracerProvider=TracerProvider),
        "opentelemetry.sdk.trace.export": _mod("opentelemetry.sdk.trace.export",
                                               BatchSpanProcessor=BatchSpanProcessor),
        "opentelemetry.sdk.trace.sampling": _mod("opentelemetry.sdk.trace.sampling",
                                                 ParentBased=ParentBased,
                                                 TraceIdRatioBased=TraceIdRatioBased),
        "opentelemetry.exporter": _mod("opentelemetry.exporter"),
        "opentelemetry.exporter.otlp": _mod("opentelemetry.exporter.otlp"),
        "opentelemetry.exporter.otlp.proto": _mod("opentelemetry.exporter.otlp.proto"),
        "opentelemetry.exporter.otlp.proto.http": _mod("opentelemetry.exporter.otlp.proto.http"),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter":
            _mod("opentelemetry.exporter.otlp.proto.http.trace_exporter",
                 OTLPSpanExporter=OTLPSpanExporter),
        "opentelemetry.instrumentation": _mod("opentelemetry.instrumentation"),
        "opentelemetry.instrumentation.fastapi":
            _mod("opentelemetry.instrumentation.fastapi", FastAPIInstrumentor=FastAPIInstrumentor),
        "opentelemetry.instrumentation.sqlalchemy":
            _mod("opentelemetry.instrumentation.sqlalchemy",
                 SQLAlchemyInstrumentor=SQLAlchemyInstrumentor),
    }
    sys.modules.update(mods)


def _reset(endpoint=None, **env):
    """Reset module state + fakes for an independent case."""
    global rec
    rec = _Rec()
    otel._ENABLED = False
    for k in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
              "AEC_OTEL_TRACES_SAMPLE_RATE", "AEC_OTEL_SERVICE_NAME"):
        os.environ.pop(k, None)
    if endpoint:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
    os.environ.update(env)
    _install_fake_otel(rec)


# --- 1. ENDPOINT UNSET → no-op: app boots, nothing initialized, SDK never touched -----------------
_reset(endpoint=None)
assert otel.init() is False, "init() with no endpoint returns False"
assert otel.instrument_app(FastAPI()) is False, "instrument_app with no endpoint returns False"
assert otel.enabled() is False, "no endpoint → tracing disabled"
assert rec.provider is None and rec.instrument_app_kwargs is None, "no endpoint → SDK never touched"
otel.set_request_id("rid-unset")            # must be a silent no-op, not raise
with TestClient(app, raise_server_exceptions=False) as c:
    assert c.get("/health").status_code == 200, "app boots + serves with tracing unset"
print("1. endpoint unset: init()/instrument_app() no-op, app boots, SDK untouched")


# --- 2. ENDPOINT SET → provider/exporter/instrumentors initialized with safe defaults -------------
_reset(endpoint="http://collector:4318")
sub_app = FastAPI()
assert otel.instrument_app(sub_app) is True, "instrument_app attaches when endpoint set"
assert otel.init() is True, "init() enables tracing when endpoint set"
assert otel.enabled() is True
# sampler: ParentBased(TraceIdRatioBased(0.1)) — default 10%, NOT 100%
assert rec.sampler == ("ParentBased", 0.1), ("default sampler is ParentBased/0.1", rec.sampler)
# exporter wrapped in a BatchSpanProcessor (off-request-path export)
assert len(rec.processors) == 1 and rec.provider.processors == rec.processors, rec.processors
# service name default
assert rec.resource_attrs == {"service.name": "massing-api"}, rec.resource_attrs
# FastAPI: probe URLs excluded, and NO header/body capture kwargs
ia = rec.instrument_app_kwargs
assert ia == {"excluded_urls": "health,ready,metrics"}, ("only excluded_urls passed", ia)
for probe in ("health", "ready", "metrics"):
    assert probe in ia["excluded_urls"], probe
assert not any("capture" in k or "header" in k or "body" in k for k in ia), \
    ("no header/body capture enabled", ia)
# SQLAlchemy: engine instrumented, commenter/param capture OFF
sq = rec.sqla_instrument_kwargs
assert sq is not None and sq.get("enable_commenter") is False, ("no SQL commenter/params", sq)
assert "engine" in sq, "instruments the shared engine"
# idempotent: a second init() does not build a second provider
first = rec.provider
assert otel.init() is True and rec.provider is first, "init() is idempotent"
print("2. endpoint set: ParentBased/0.1 sampler, batch exporter, probes excluded, "
      "no header/body capture, SQLAlchemy commenter off, idempotent")


# --- 3. no auth headers / cookies / bearer tokens / bodies exported (privacy) ---------------------
# We never enable capture, so none of OTel's capture knobs are passed and no auth material can become
# a span attribute. Assert the negative explicitly on both instrumentors.
assert all(k == "excluded_urls" for k in rec.instrument_app_kwargs), rec.instrument_app_kwargs
assert "enable_commenter" in rec.sqla_instrument_kwargs and \
    rec.sqla_instrument_kwargs["enable_commenter"] is False, "params/SQL-comment capture off"
print("3. privacy: no header/cookie/token/body capture kwargs on FastAPI or SQLAlchemy instrumentors")


# --- 4. INIT FAILURE → fail-open: init() False, tracing disabled, app unaffected ------------------
_reset(endpoint="http://collector:4318")
rec.exporter_raises = True                  # OTLP exporter construction blows up
assert otel.init() is False, "exporter failure → init() returns False"
assert otel.enabled() is False, "failed init leaves tracing disabled (fail-open)"
with TestClient(app, raise_server_exceptions=False) as c:
    assert c.get("/health").status_code == 200, "boot/serve unaffected by OTel init failure"
print("4. init failure: swallowed, tracing disabled, app still serves (fail-open)")


# --- 5. request-id attached to the current span ---------------------------------------------------
_reset(endpoint="http://collector:4318")
assert otel.init() is True

class _FakeSpan:
    def set_attribute(self, k, v):
        rec.span_attrs[k] = v

_orig_get = _real_trace.get_current_span
_real_trace.get_current_span = lambda: _FakeSpan()
try:
    otel.set_request_id("rid-abc123")
    assert rec.span_attrs.get("request_id") == "rid-abc123", ("request-id on span", rec.span_attrs)
    # disabled → no-op even with a live span
    otel._ENABLED = False
    rec.span_attrs.clear()
    otel.set_request_id("rid-should-not-appear")
    assert rec.span_attrs == {}, "set_request_id is a no-op when tracing disabled"
finally:
    _real_trace.get_current_span = _orig_get
print("5. request-id: attached to current span when enabled, no-op when disabled")


# --- 6. sample-rate configuration: default, override, clamp, malformed ----------------------------
_reset(endpoint="http://collector:4318")
assert otel._sample_rate() == 0.1, "default sample rate 0.1"
os.environ["AEC_OTEL_TRACES_SAMPLE_RATE"] = "1.0"
assert otel._sample_rate() == 1.0, "override to 1.0 (incident debugging)"
os.environ["AEC_OTEL_TRACES_SAMPLE_RATE"] = "5"        # out of range → clamp
assert otel._sample_rate() == 1.0, "clamp above 1.0"
os.environ["AEC_OTEL_TRACES_SAMPLE_RATE"] = "-1"
assert otel._sample_rate() == 0.0, "clamp below 0.0"
os.environ["AEC_OTEL_TRACES_SAMPLE_RATE"] = "not-a-number"
assert otel._sample_rate() == 0.1, "malformed → default 0.1"
os.environ["AEC_OTEL_TRACES_SAMPLE_RATE"] = "0.5"
_reset(endpoint="http://collector:4318", AEC_OTEL_TRACES_SAMPLE_RATE="0.5",
       AEC_OTEL_SERVICE_NAME="massing-api-staging")
assert otel.init() is True
assert rec.sampler == ("ParentBased", 0.5), rec.sampler
assert rec.resource_attrs == {"service.name": "massing-api-staging"}, rec.resource_attrs
print("6. sample rate: default 0.1, override, clamp, malformed→default; service name honored")


# --- cleanup so import side effects don't leak to other test modules ------------------------------
for _k in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
           "AEC_OTEL_TRACES_SAMPLE_RATE", "AEC_OTEL_SERVICE_NAME"):
    os.environ.pop(_k, None)
otel._ENABLED = False
print("test_otel OK")
