"""Outbound webhooks — fire a JSON POST to configured URLs when a module record transitions, so
external automation (Power Automate / Zapier / Teams / a custom listener) can react to RFIs answered,
COs approved, etc. Opt-in (set AEC_WEBHOOK_URLS, comma-separated, or the same key in Settings) and
**fail-open**: a slow/broken endpoint never blocks or breaks the transition.

Delivery is fire-and-forget on a daemon thread; set AEC_WEBHOOK_SYNC=1 (tests) for synchronous send.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from . import settings_store
from .net import validate_outbound_url

_log = logging.getLogger("aec.webhooks")


def _urls() -> list[str]:
    raw = settings_store.get("AEC_WEBHOOK_URLS", "") or ""
    return [u.strip() for u in raw.split(",") if u.strip()]


def _secret() -> str:
    return (settings_store.get("AEC_WEBHOOK_SECRET", "") or "").strip()


def _sign(ts: str, body: bytes) -> str | None:
    """GitHub-style HMAC-SHA256 over `<ts>.<body>` (the timestamp binds the signature to a moment,
    so a captured request can't be replayed later). None when no secret is configured."""
    secret = _secret()
    if not secret:
        return None
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def build_payload(event: str, **fields: Any) -> dict:
    return {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}


# Recent delivery log — a bounded, process-local ring for "did my webhook fire?" observability.
# (Per-worker; not durable across restarts — deliberately lightweight, no DB migration.)
_DELIVERIES: collections.deque[dict] = collections.deque(maxlen=int(os.environ.get("AEC_WEBHOOK_LOG_MAX", "200")))
_LOG_LOCK = threading.Lock()


def record_delivery(entry: dict) -> None:
    with _LOG_LOCK:
        _DELIVERIES.appendleft(entry)


def recent(limit: int = 100) -> list[dict]:
    """Most-recent delivery attempts first (url, event, ok, status, attempts, ts, error)."""
    with _LOG_LOCK:
        return list(_DELIVERIES)[:max(0, limit)]


def _retries() -> int:
    return max(1, int(os.environ.get("AEC_WEBHOOK_RETRIES", "3")))


def _retry_base() -> float:
    return float(os.environ.get("AEC_WEBHOOK_RETRY_BASE", "0.5"))


def _allow_private() -> bool:
    """REL-6: whether webhook targets may resolve to private/loopback addresses. Default yes —
    on-prem listeners (Power Automate gateway, a LAN automation host) are a legitimate operator
    choice and the URLs are operator-set. Set AEC_WEBHOOK_ALLOW_PRIVATE=0 (env or Settings) in
    hosted/multi-tenant deployments to refuse them (blocks cloud-metadata + intranet probing via a
    compromised settings key)."""
    return (settings_store.get("AEC_WEBHOOK_ALLOW_PRIVATE", "1") or "1").strip() != "0"


def _send(url: str, body: bytes) -> int:
    """POST `body` to `url`, HMAC-signing it when a secret is set. Returns the HTTP status."""
    validate_outbound_url(url, label="AEC_WEBHOOK_URLS entry",  # block file:// etc; see _allow_private
                          allow_private=_allow_private())
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "User-Agent": "Massing-Webhook",
               "X-Massing-Event-Timestamp": ts}
    sig = _sign(ts, body)
    if sig:
        headers["X-Massing-Signature"] = sig
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    timeout = float(os.environ.get("AEC_WEBHOOK_TIMEOUT", "3"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — scheme-validated above
        return getattr(resp, "status", 200) or 200


def _deliver(urls: list[str], body: bytes, event: str = "") -> None:
    """Deliver to each URL with bounded exponential-backoff retries; log every final outcome."""
    retries = _retries()
    for u in urls:
        status: int | None = None
        err: str | None = None
        attempt = 0
        for attempt in range(1, retries + 1):
            try:
                status = _send(u, body)
                err = None
                break
            except Exception as e:                   # noqa: BLE001 — never fail over a webhook
                err = str(e)[:200]
                if attempt < retries:
                    time.sleep(_retry_base() * (2 ** (attempt - 1)))   # 0.5s, 1s, 2s, …
        if err:
            _log.warning("webhook to %s failed after %d attempt(s): %s", u, attempt, err)
        record_delivery({"ts": datetime.now(timezone.utc).isoformat(), "url": u, "event": event,
                         "ok": err is None, "status": status, "attempts": attempt, "error": err})


def dispatch(event: str, payload: dict) -> int:
    """POST {event, ts, ...payload} to every configured webhook URL. Returns the number of URLs
    attempted (0 when none configured). Non-blocking unless AEC_WEBHOOK_SYNC=1."""
    urls = _urls()
    if not urls:
        return 0
    body = json.dumps({**payload, "event": event}, default=str).encode("utf-8")
    if os.environ.get("AEC_WEBHOOK_SYNC") == "1":
        _deliver(urls, body, event)
    else:
        threading.Thread(target=_deliver, args=(urls, body, event), daemon=True).start()
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
