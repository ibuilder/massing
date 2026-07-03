"""Outbound webhooks — fire a JSON POST to configured URLs when a module record transitions, so
external automation (Power Automate / Zapier / Teams / a custom listener) can react to RFIs answered,
COs approved, etc. Opt-in (set AEC_WEBHOOK_URLS, comma-separated, or the same key in Settings) and
**fail-open**: a slow/broken endpoint never blocks or breaks the transition.

Delivery is fire-and-forget on a daemon thread; set AEC_WEBHOOK_SYNC=1 (tests) for synchronous send.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Any

from . import settings_store
from .net import validate_outbound_url

_log = logging.getLogger("aec.webhooks")


def _urls() -> list[str]:
    raw = settings_store.get("AEC_WEBHOOK_URLS", "") or ""
    return [u.strip() for u in raw.split(",") if u.strip()]


def build_payload(event: str, **fields: Any) -> dict:
    return {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}


def _send(url: str, body: bytes) -> None:
    validate_outbound_url(url, label="AEC_WEBHOOK_URLS entry")  # block file://etc; LAN targets allowed
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Massing-Webhook"})
    timeout = float(os.environ.get("AEC_WEBHOOK_TIMEOUT", "3"))
    urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — operator-configured URL, scheme-validated above


def _deliver(urls: list[str], body: bytes) -> None:
    for u in urls:
        try:
            _send(u, body)
        except Exception as e:                       # noqa: BLE001 — never fail over a webhook
            _log.warning("webhook to %s failed: %s", u, e)


def dispatch(event: str, payload: dict) -> int:
    """POST {event, ts, ...payload} to every configured webhook URL. Returns the number of URLs
    attempted (0 when none configured). Non-blocking unless AEC_WEBHOOK_SYNC=1."""
    urls = _urls()
    if not urls:
        return 0
    body = json.dumps({**payload, "event": event}, default=str).encode("utf-8")
    if os.environ.get("AEC_WEBHOOK_SYNC") == "1":
        _deliver(urls, body)
    else:
        threading.Thread(target=_deliver, args=(urls, body), daemon=True).start()
    return len(urls)


def record_transition(project_id: str, module: str, rid: str, ref: str | None,
                      frm: str, to: str, action: str, actor: str | None,
                      distribution: list[str] | None = None) -> None:
    """Emit a `record.transition` webhook (best-effort). `distribution`: resolved CC emails so an
    external automation can notify the record's distribution list."""
    try:
        dispatch("record.transition", build_payload(
            "record.transition", project_id=project_id, module=module, record_id=rid,
            ref=ref, **{"from": frm}, to=to, action=action, actor=actor,
            distribution=distribution or []))
    except Exception as e:                            # noqa: BLE001
        _log.warning("webhook dispatch error: %s", e)
