"""Real-estate syndication bridge — OPTIONAL, feature-flagged (off unless REALWISE_URL + key set).

Massing owns the BIM + cost + income data and can market a listing off-plan; the disposition CRM /
agent portal / tours / property management / live MLS feed live in **WPRealWise** (the same owner's
WordPress system). Rather than rebuild that stack, this bridge **pushes** a listing — already serialized
to the RESO Data Dictionary by `marketing.to_reso()` — into WPRealWise over its REST API
(stdlib urllib, no SDK). This is Phase 4 of docs/realestate-marketing.md.

The RESO export itself (`GET /projects/{pid}/listings/{lid}/reso`) is always available; this module is
only the outbound push. WPRealWise is implemented end-to-end; other targets raise an actionable error
until their credentialed endpoint is wired per deployment.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_TARGETS = {
    "wprealwise": "WPRealWise (self-hosted WordPress)",
    "mls": "MLS / RESO Web API",
}
_IMPLEMENTED = ("wprealwise",)
_TIMEOUT = 30


def target() -> str:
    return (os.environ.get("RE_SYNDICATION_TARGET", "wprealwise").strip().lower() or "wprealwise")


def base_url() -> str:
    return os.environ.get("REALWISE_URL", "").rstrip("/")


def is_enabled() -> bool:
    """Configured with a base URL and an API key."""
    return bool(base_url() and os.environ.get("REALWISE_API_KEY"))


def status() -> dict[str, Any]:
    t = target()
    return {
        "enabled": is_enabled(),
        "target": _TARGETS.get(t, t),
        "implemented": t in _IMPLEMENTED,
        "targets_supported": list(_TARGETS.values()),
        "message": (f"{_TARGETS.get(t, t)} syndication configured ({base_url()})." if is_enabled() else
                    "Real-estate syndication bridge not configured. The RESO export "
                    "(GET /projects/{pid}/listings/{lid}/reso) is available now; set REALWISE_URL + "
                    "REALWISE_API_KEY to push listings into WPRealWise / an MLS RESO Web API."),
    }


# --- transport seam (monkeypatched in tests) --------------------------------
def _http_json(method: str, url: str, headers: dict[str, str], payload: dict | None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — operator-configured URL
        body = resp.read().decode() or "{}"
    return json.loads(body)


def post_json(url: str, headers: dict[str, str], payload: dict) -> Any:
    return _http_json("POST", url, headers, payload)


def _wprealwise_push(reso: dict, listing_ref: str | None) -> dict[str, Any]:
    """Upsert a RESO listing into WPRealWise. The plugin exposes a REST route keyed by ListingKey
    (we use our listing ref) so re-syndicating the same listing updates rather than duplicates."""
    base = base_url()
    key = os.environ.get("REALWISE_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"}
    payload = {"ListingKey": listing_ref, **reso} if listing_ref else dict(reso)
    resp = post_json(f"{base}/wp-json/realwise/v1/listings", headers, payload)
    remote_id = None
    listing_url = None
    if isinstance(resp, dict):
        remote_id = resp.get("id") or resp.get("ListingId") or resp.get("post_id")
        listing_url = resp.get("permalink") or resp.get("url") or resp.get("link")
    return {"target": _TARGETS["wprealwise"], "remote_id": remote_id, "url": listing_url,
            "fields_pushed": len(reso), "status": "syndicated"}


def syndicate(reso: dict, listing_ref: str | None = None) -> dict[str, Any]:
    """Push a RESO-serialized listing to the configured target. WPRealWise is implemented; other
    targets raise an actionable error until their credentialed endpoint is wired per deployment."""
    if not is_enabled():
        raise RuntimeError("No syndication target configured (set REALWISE_URL + REALWISE_API_KEY).")
    t = target()
    if t == "wprealwise":
        return _wprealwise_push(reso, listing_ref)
    raise NotImplementedError(
        f"The {_TARGETS.get(t, t)} syndication flow runs in a credentialed deployment; wire its "
        "RESO Web API endpoint in re_bridge.py. The WPRealWise push is implemented, and the RESO "
        "export (GET /projects/{pid}/listings/{lid}/reso) is available now for manual import.")
