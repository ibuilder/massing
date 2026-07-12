"""Capital-markets / syndication bridge — OPTIONAL, feature-flagged (off unless a platform URL + key set).

Massing owns the fund data — the investor cap table, commitments, contributed/distributed positions and
the JV waterfall — and can serialize it to a neutral **syndication package** any time. Digital-securities
issuance, KYC/AML, accredited-investor verification, subscription docs and the actual custody / transfer
of funds live in a dedicated securitization platform. Rather than rebuild that regulated stack, this
bridge **pushes** the syndication package (already serialized by `syndication_payload()`) into that
platform over its REST API (stdlib urllib, no SDK).

Scope guard — this connector **never moves money**. It syncs the *ledger* (positions, ownership %,
contributed/distributed totals recorded elsewhere) so the external platform's investor records match
Massing's. Capital calls, distributions and transfers are executed by the licensed platform, not here.

The package export itself (`GET /projects/{pid}/securities/package`) is always available offline; this
module is only the outbound push. A generic authenticated REST endpoint is implemented; named platforms
raise an actionable error until their credentialed endpoint is wired per deployment.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from . import settings_store
from .net import validate_outbound_url

_TARGETS = {
    "generic": "Investor-management REST API",
    "securitize": "Securitize (digital securities platform)",
}
_IMPLEMENTED = ("generic",)
_TIMEOUT = 30
SCHEMA = "massing.syndication.v1"


def target() -> str:
    return (settings_store.get("SECURITIES_TARGET", "generic") or "generic").strip().lower() or "generic"


def base_url() -> str:
    return (settings_store.get("SECURITIES_PLATFORM_URL", "") or "").rstrip("/")


def is_enabled() -> bool:
    """Configured with a platform URL and an API key."""
    return bool(base_url() and settings_store.get("SECURITIES_API_KEY"))


def status() -> dict[str, Any]:
    t = target()
    return {
        "enabled": is_enabled(),
        "target": _TARGETS.get(t, t),
        "implemented": t in _IMPLEMENTED,
        "targets_supported": list(_TARGETS.values()),
        "moves_money": False,
        "message": (
            f"{_TARGETS.get(t, t)} syndication configured ({base_url()}). Pushes the investor ledger "
            "only — no funds are transferred by this connector." if is_enabled() else
            "Capital-markets syndication bridge not configured. The syndication package export "
            "(GET /projects/{pid}/securities/package) is available now; set SECURITIES_PLATFORM_URL + "
            "SECURITIES_API_KEY (Settings → integrations) to sync the cap table into an investor / "
            "digital-securities platform. This connector syncs positions only and never moves money."),
    }


def syndication_payload(project_name: str, cap_table: dict, disclosures: dict | None = None) -> dict[str, Any]:
    """Serialize the cap table into a neutral syndication package a securitization platform can ingest.
    `cap_table` is a `capital.cap_table()` result. Amounts are the *recorded* ledger totals — informational,
    not an instruction to transfer. Optional `disclosures` (offering name, exemption, min investment)
    are passed through if the project supplies them."""
    rows = cap_table.get("rows", [])
    positions = [{
        "investor": r.get("investor"),
        "investor_class": r.get("investor_class") or "LP",
        "entity_type": r.get("entity_type"),
        "external_ref": r.get("ref"),
        "commitment": r.get("commitment"),
        "ownership_pct": r.get("ownership_pct"),
        "contributed": r.get("contributed"),
        "distributed": r.get("distributed"),
        "unreturned": r.get("unreturned"),
        "status": r.get("status"),
    } for r in rows]
    return {
        "schema": SCHEMA,
        "project": project_name,
        "fund": {
            "investor_count": cap_table.get("investor_count", len(positions)),
            "total_commitment": cap_table.get("total_commitment", 0.0),
            "total_contributed": cap_table.get("total_contributed", 0.0),
            "total_distributed": cap_table.get("total_distributed", 0.0),
            "total_unreturned": cap_table.get("total_unreturned", 0.0),
            "by_class": cap_table.get("by_class", {}),
        },
        "positions": positions,
        "disclosures": disclosures or {},
        "disclaimer": ("Positions and amounts reflect Massing's internal ledger and are informational. "
                       "This package registers/updates investor records only; it does not instruct, "
                       "authorize, or execute any transfer of funds or securities."),
    }


# --- transport seam (monkeypatched in tests) --------------------------------
def _http_json(method: str, url: str, headers: dict[str, str], payload: dict | None) -> Any:
    validate_outbound_url(url, label="SECURITIES_PLATFORM_URL")  # block file:// etc on the operator URL
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — operator URL, scheme-validated
        body = resp.read().decode() or "{}"
    return json.loads(body)


def post_json(url: str, headers: dict[str, str], payload: dict) -> Any:
    return _http_json("POST", url, headers, payload)


def _generic_push(package: dict, project_ref: str | None) -> dict[str, Any]:
    """POST the syndication package to a generic investor-management REST endpoint. The platform keys
    the record by our project ref so re-syncing updates rather than duplicates."""
    base = base_url()
    key = settings_store.get("SECURITIES_API_KEY", "") or ""
    headers = {"Authorization": f"Bearer {key}"}
    body = {"project_ref": project_ref, **package} if project_ref else dict(package)
    resp = post_json(f"{base}/api/syndications", headers, body)
    remote_id = None
    if isinstance(resp, dict):
        remote_id = resp.get("id") or resp.get("syndication_id") or resp.get("record_id")
    return {"target": _TARGETS["generic"], "remote_id": remote_id,
            "positions_pushed": len(package.get("positions", [])), "moves_money": False,
            "status": "synced"}


def syndicate(package: dict, project_ref: str | None = None) -> dict[str, Any]:
    """Push a syndication package to the configured platform (ledger sync only — no funds move). The
    generic REST target is implemented; named platforms raise an actionable error until their
    credentialed endpoint is wired per deployment."""
    if not is_enabled():
        raise RuntimeError("No syndication platform configured (set SECURITIES_PLATFORM_URL + "
                           "SECURITIES_API_KEY). The package export is available now for manual import.")
    t = target()
    if t == "generic":
        return _generic_push(package, project_ref)
    raise NotImplementedError(
        f"The {_TARGETS.get(t, t)} issuance flow runs in a credentialed deployment; wire its "
        "REST ingest endpoint in securities_bridge.py. The generic REST push is implemented, and the "
        "package export (GET /projects/{pid}/securities/package) is available now for manual import.")
