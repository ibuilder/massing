"""Payment execution bridge — OPTIONAL, and deliberately a stub until a licensed processor is wired.

Massing tracks the pay-app ↔ lien-waiver workflow (payapp.py) but does NOT move money itself. Actual
disbursement (ACH to a sub, owner-billing collection) must go through a licensed payment processor
(Stripe Connect, Dwolla, a bank rail) provisioned in your deployment — with its own KYC, ledgering,
and compliance. This mirrors the speckle/aps bridges: OFF unless configured, and `send_payment` raises
an actionable error rather than ever fabricating a transfer. The value we own is the *release gate*:
a payment should only be initiated once the lien-waiver exposure for that vendor is clear."""
from __future__ import annotations

from . import settings_store


def provider() -> str:
    return (settings_store.get("PAYMENTS_PROVIDER") or "").strip()


def is_enabled() -> bool:
    return bool(provider())


def status() -> dict:
    if not is_enabled():
        return {"enabled": False, "provider": None,
                "message": "Payment execution is not configured. Massing tracks pay-apps and lien-waiver "
                           "exposure; to disburse funds, provision a licensed processor (e.g. Stripe "
                           "Connect / Dwolla) and set PAYMENTS_PROVIDER. Money movement always runs "
                           "through the processor, never through Massing."}
    return {"enabled": True, "provider": provider(),
            "message": f"Payments provider '{provider()}' configured — disbursement runs through the "
                       "processor's API in your deployment."}


def send_payment(vendor: str, amount: float, *, lien_exposure: float = 0.0) -> dict:
    """Initiate a disbursement — raises until a processor is wired (never fabricates a transfer).

    The lien-waiver release gate is enforced here regardless of processor: a payment is refused while
    the vendor still has uncovered lien exposure."""
    if lien_exposure > 0.005:
        raise ValueError(f"Refused: {vendor} has ${lien_exposure:,.2f} of uncovered lien exposure — "
                         "collect an unconditional waiver before disbursing.")
    if not is_enabled():
        raise RuntimeError("Payment execution is not configured (set PAYMENTS_PROVIDER and provision a "
                           "licensed processor). Massing does not move money itself.")
    raise NotImplementedError(
        f"Disbursement of ${amount:,.2f} to {vendor} runs through the configured processor "
        f"'{provider()}'. Wire the processor's transfer API in your deployment to enable it; the "
        "lien-waiver release gate is already enforced by this bridge.")
