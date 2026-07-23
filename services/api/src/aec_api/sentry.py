"""Sentry-compatible external error alerting — server-side only, no-op until configured.

The DB `error_log` (errorlog.py) is a *record* of what broke; it never alarms anyone. This wires the
global 500 handler to an external Sentry-compatible sink (Sentry / GlitchTip — both take a DSN-style
integration) so a production 500 pages on-call, dedups, and tracks releases.

No-op by default: nothing initializes unless `AEC_SENTRY_DSN` (or `SENTRY_DSN`) is set — DSN unset =
identical app behavior. Error reporting only: `traces_sample_rate` defaults to 0 (performance/tracing
is a separate concern). Everything here fails open — an init or capture failure is logged and
swallowed so it can never block boot or mask a response.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger("aec.sentry")

# Flipped true only once sentry_sdk.init() has succeeded, so capture_exception() is a cheap no-op
# otherwise (and so the DSN-unset path provably never touches the SDK / network).
_ENABLED = False

# Request headers that must never leave the process — auth material. Compared case-insensitively.
_SCRUB_HEADERS = frozenset({"authorization", "cookie", "x-api-key"})


def _dsn() -> str:
    return (os.environ.get("AEC_SENTRY_DSN") or os.environ.get("SENTRY_DSN") or "").strip()


def enabled() -> bool:
    return _ENABLED


def _before_send(event, _hint):
    """Strip credential-bearing headers + request body before an event leaves the process.
    `send_default_pii=False` already omits cookies/bodies, but we scrub explicitly as defense in
    depth. If scrubbing itself fails we drop the whole request payload rather than risk leaking it."""
    try:
        req = event.get("request")
        if isinstance(req, dict):
            headers = req.get("headers")
            if isinstance(headers, dict):
                for k in list(headers):
                    if k.lower() in _SCRUB_HEADERS:
                        headers[k] = "[scrubbed]"
            # request bodies can carry credentials (login payloads, API tokens) — never send them
            if "data" in req:
                req["data"] = "[scrubbed]"
    except Exception:                       # noqa: BLE001 — never leak, never raise out of before_send
        _log.warning("sentry before_send scrub failed; dropping request payload", exc_info=True)
        try:
            event.pop("request", None)
        except Exception:                   # noqa: BLE001
            pass
    return event


def init() -> bool:
    """Initialize Sentry iff a DSN is configured. Returns True when Sentry was enabled. Safe to call
    once at startup; any failure is logged and swallowed (fail-open)."""
    global _ENABLED
    dsn = _dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk

        # Explicit FastAPI/Starlette integrations (the spec's "with the FastAPI integration"). These
        # are default integrations in modern sentry-sdk, so if the submodules can't be imported we
        # simply let the SDK auto-detect — never fatal.
        integrations = []
        try:
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
            integrations = [StarletteIntegration(), FastApiIntegration()]
        except Exception:                   # noqa: BLE001 — optional; SDK auto-detects FastAPI anyway
            pass

        try:
            traces = float(os.environ.get("AEC_SENTRY_TRACES_SAMPLE_RATE", "0") or "0")
        except ValueError:
            traces = 0.0
        environment = (os.environ.get("AEC_SENTRY_ENVIRONMENT")
                       or os.environ.get("AEC_ENV") or "development")
        release = os.environ.get("AEC_SENTRY_RELEASE") or None

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces,      # 0 = error reporting only, no performance/tracing overhead
            send_default_pii=False,
            before_send=_before_send,
            integrations=integrations,
        )
        _ENABLED = True
        _log.info("Sentry error alerting enabled (environment=%s, traces_sample_rate=%s)",
                  environment, traces)
        return True
    except Exception:                       # noqa: BLE001 — a Sentry failure must never block boot
        _ENABLED = False
        _log.warning("Sentry init failed; error alerting disabled", exc_info=True)
        return False


def capture_exception(exc: BaseException, *, request_id: str | None = None) -> None:
    """Send one exception to Sentry (no-op unless init() enabled it). Tags the event with the
    request-id so it correlates with the JSON access log and the DB error_log row. Fails open — a
    capture failure must never mask the original 500."""
    if not _ENABLED:
        return
    try:
        import sentry_sdk

        if request_id:
            try:
                sentry_sdk.set_tag("request_id", request_id)
            except Exception:               # noqa: BLE001 — tagging is best-effort
                pass
        sentry_sdk.capture_exception(exc)
    except Exception:                       # noqa: BLE001 — capture must never mask the original 500
        _log.warning("Sentry capture_exception failed", exc_info=True)
