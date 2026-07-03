"""RFQ dispatch bridge — OPTIONAL, a stub until a supplier channel is provisioned.

Sending an RFQ to suppliers means email/EDI/a supplier portal, which is a per-deployment integration
(and sending on the user's behalf needs their explicit channel). Mirrors the other bridges: OFF unless
`RFQ_PROVIDER` is set, and `send_rfq` raises an actionable error rather than pretending to send. The
value we own without it is the *quote leveling* and *3-way match* — the RFQ blast is the last mile."""
from __future__ import annotations

from . import settings_store


def provider() -> str:
    return (settings_store.get("RFQ_PROVIDER") or "").strip()


def is_enabled() -> bool:
    return bool(provider())


def status() -> dict:
    if not is_enabled():
        return {"enabled": False, "provider": None,
                "message": "RFQ dispatch is not configured. Massing levels quotes and 3-way-matches "
                           "POs; to blast an RFQ to suppliers, set RFQ_PROVIDER and wire an email/EDI/"
                           "supplier-portal channel in your deployment."}
    return {"enabled": True, "provider": provider(),
            "message": f"RFQ dispatch via '{provider()}'."}


def send_rfq(suppliers: list[str], items: list[dict]) -> dict:
    """Dispatch an RFQ — raises until a channel is wired (never pretends to have sent)."""
    if not is_enabled():
        raise RuntimeError("RFQ dispatch is not configured (set RFQ_PROVIDER and wire a supplier "
                           "channel). Massing does not send on your behalf until that's provisioned.")
    raise NotImplementedError(
        f"RFQ to {len(suppliers)} supplier(s) for {len(items)} item(s) dispatches through the configured "
        f"channel '{provider()}'. Implement the provider send in your deployment to enable it.")
