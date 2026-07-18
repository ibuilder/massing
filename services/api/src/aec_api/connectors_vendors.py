"""REL-3 leaf: raw vendor HTTP clients — the outbound I/O half of `connectors.py`.

The per-vendor REST reads/writes (Procore, Autodesk Construction Cloud, QuickBooks Online, generic
Sage/Viewpoint ERP) as plain urllib functions: token in, parsed JSON out. No DB, no app imports, no
dispatch logic. `connectors.py` imports these and keeps the *overridable seams* (`procore_rfis = …`,
`acc_projects = …`) plus the per-vendor test/info dispatchers on its own module namespace — tests
monkeypatch the seams there (`connectors.acc_projects = fake`), and that contract is unchanged.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any


# --- Procore -------------------------------------------------------------------
def _procore_get(path: str, token: str) -> Any:
    req = urllib.request.Request(f"https://api.procore.com{path}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 — fixed Procore host
        return json.loads(r.read().decode())


def _procore_rfis(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.0/projects/{project_id}/rfis", token) or []


def _procore_submittals(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.0/projects/{project_id}/submittals", token) or []


def _procore_change_events(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.1/projects/{project_id}/change_events", token) or []


def _procore_update_rfi(token: str, project_id: str, rfi_id: str, payload: dict) -> Any:
    body = json.dumps({"rfi": payload}).encode()
    req = urllib.request.Request(
        f"https://api.procore.com/rest/v1.0/projects/{project_id}/rfis/{rfi_id}",
        data=body, method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — fixed Procore host
        return json.loads(r.read().decode() or "{}")


# --- Autodesk Construction Cloud (APS) -----------------------------------------
# ACC is another major BIM data platform; same adapter pattern as Procore. A 3-legged OAuth
# token reaches the user profile + (with an account_id) the account's projects and their issues.
def _aps_get(path: str, token: str) -> Any:
    req = urllib.request.Request(f"https://developer.api.autodesk.com{path}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 — fixed Autodesk host
        return json.loads(r.read().decode())


def _acc_list(payload: Any) -> list[dict]:
    """ACC list endpoints wrap rows under 'results' (Issues/Admin) or 'data' (Data Mgmt)."""
    if isinstance(payload, dict):
        for key in ("results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return payload if isinstance(payload, list) else []


def _acc_projects(token: str, account_id: str) -> list[dict]:
    # ACC Admin API: projects under an account (account_id == ACC account/hub GUID)
    return _acc_list(_aps_get(f"/construction/admin/v1/accounts/{account_id}/projects", token))


def _acc_issues(token: str, project_id: str) -> list[dict]:
    return _acc_list(_aps_get(f"/construction/issues/v1/projects/{project_id}/issues", token))


# --- QuickBooks Online (accounting / ERP) --------------------------------------
# The financial-backbone connector — read the chart of accounts, vendors, and bills so cost data
# can reconcile against the books. OAuth access token + realm_id (company id). Same adapter shape.
def _qb_get(path: str, token: str) -> Any:
    req = urllib.request.Request(f"https://quickbooks.api.intuit.com{path}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 — fixed Intuit host
        return json.loads(r.read().decode())


def _qb_query(realm: str, token: str, entity: str, limit: int = 50) -> list[dict]:
    import urllib.parse
    q = urllib.parse.quote(f"select * from {entity} maxresults {limit}")
    data = _qb_get(f"/v3/company/{realm}/query?query={q}&minorversion=70", token)
    return (data.get("QueryResponse") or {}).get(entity, []) or []


def _qb_accounts(token: str, realm: str) -> list[dict]:
    return _qb_query(realm, token, "Account")


def _qb_vendors(token: str, realm: str) -> list[dict]:
    return _qb_query(realm, token, "Vendor")


def _qb_bills(token: str, realm: str) -> list[dict]:
    return _qb_query(realm, token, "Bill")


# --- Sage / Viewpoint (generic REST ERP) ---------------------------------------
# Same adapter shape as QuickBooks but vendor-agnostic: the operator supplies their tenant's API
# `base_url` + token; we read accounts / vendors / bills as JSON lists. Exact paths vary by tenant,
# so base_url is configurable and the read is an overridable seam (testable without a live ERP).
def _erp_get(base_url: str, path: str, token: str) -> Any:
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 — operator-supplied tenant host
        return json.loads(r.read().decode())


def _erp_read(config: dict, entity: str) -> list[dict]:
    return _acc_list(_erp_get(config.get("base_url") or "", f"/{entity}", config.get("access_token") or ""))
