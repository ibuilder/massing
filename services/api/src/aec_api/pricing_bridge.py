"""Live material-pricing bridge — OPTIONAL, a stub until a pricing feed is provisioned.

Static cost books go stale; a live feed (a supplier API — Home Depot/Lowe's/ABC, or RSMeans) keeps unit
costs current. Mirrors the other bridges: OFF unless PRICING_PROVIDER is set, and `unit_price` returns
None (so the caller falls back to the built-in book) rather than fabricating a number. Wire the provider's
lookup in a deployment to enable live pricing."""
from __future__ import annotations

from . import settings_store


def provider() -> str:
    return (settings_store.get("PRICING_PROVIDER") or "").strip()


def is_enabled() -> bool:
    return bool(provider())


def status() -> dict:
    if not is_enabled():
        return {"enabled": False, "provider": None,
                "message": "Live pricing is not configured — takeoff is priced from the built-in unit "
                           "price book. Set PRICING_PROVIDER and wire a supplier/RSMeans feed for "
                           "current localized costs."}
    return {"enabled": True, "provider": provider(),
            "message": f"Live pricing via '{provider()}'."}


def unit_price(material: str, unit: str) -> float | None:
    """Current unit price from the live feed, or None if unavailable (caller falls back to the book).

    A real deployment implements the provider lookup here; the stub never fabricates a price."""
    return None
