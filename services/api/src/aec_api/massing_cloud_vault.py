"""CLOUD-LIBRARY — read a signed-in user's **massing.cloud project library** (the Vault API).

This is the second half of the massing.cloud integration: [[massing_cloud_auth]] establishes *who*
the user is, and the access token it obtains **is** the credential here. The Vault API is
Bearer-scoped — the token is the identity, and the site ownership-checks every per-record call — so
this module never sends a user id and never has to be trusted to filter by one. A 403 from the site
is the authoritative answer, not a bug to route around.

Namespace: `{site}/wp-json/massing-vault/v1`

    GET    /projects           → the user's vaults        {user_id, projects:[…]}
    GET    /projects/{id}      → one vault
    GET    /models/{id}        → a model + a signed, ~15-min `download_url`
    POST   /models             → save a model back (pointer; see the `.mass` note below)
    DELETE /models/{id}        → remove a model

**Reading is what ships here.** `save_model` is included because the round trip is the point of a
library, but the byte-upload half of it is an open joint decision in massing.cloud docs/31 §3 — the
site's `POST /models` records a *pointer* (`storage_key`) and assumes the bytes already live in
storage. A recent site commit adds a `.mass` binary upload endpoint; until this app actually writes
`.mass` containers there is nothing to push, so `save_model` is deliberately not wired to a route
yet. Wiring it before the container writer exists would give us a save button that silently records
a pointer to nothing.

Plan limits are enforced site-side and come back as **409** with a message meant for the user —
surfaced verbatim rather than reworded, because it names the actual limit they hit.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import massing_cloud_auth as cloud
from .net import safe_urlopen

_TIMEOUT = 20


class VaultError(Exception):
    """A Vault call that failed in a way the user should see (status + site message)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _api(path: str) -> str:
    return f"{cloud.site_url()}/wp-json/massing-vault/v1{path}"


def _call(path: str, token: str, method: str = "GET", body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_api(path), data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data is not None else {}),
    })
    try:
        with safe_urlopen(req, timeout=_TIMEOUT, require_https=True, label="massing.cloud Vault") as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            payload = json.loads(e.read().decode())
            detail = str(payload.get("message") or payload.get("error") or "")
        except Exception:
            pass
        raise VaultError(e.code, detail or f"massing.cloud returned HTTP {e.code}") from e


# Overridable seam for the suite (same recipe as `massing_cloud_auth.exchange_code`).
call = _call


def list_projects(token: str) -> list[dict]:
    """The user's vaults. Returns `[]` rather than raising when the shape is unexpected — an empty
    library and an unreadable one look the same to the caller only in that both show nothing, and
    the route above logs the distinction."""
    data = call("/projects", token)
    projects = data.get("projects") if isinstance(data, dict) else data
    return [_shape_project(p) for p in projects] if isinstance(projects, list) else []


def get_project(token: str, project_id: int | str) -> dict:
    return _shape_project(call(f"/projects/{urllib.parse.quote(str(project_id))}", token))


def get_model(token: str, model_id: int | str) -> dict:
    """A model record including the signed `download_url`. That URL carries its own short-lived,
    model-scoped token and needs **no** Authorization header — so it must never be handed a Bearer
    header on fetch, and it must never be cached or logged."""
    return _shape_model(call(f"/models/{urllib.parse.quote(str(model_id))}", token))


def save_model(token: str, payload: dict) -> dict:
    """Ingest/update a model pointer. See the module note: not routed until the `.mass` writer lands."""
    return _shape_model(call("/models", token, method="POST", body=payload))


def delete_model(token: str, model_id: int | str) -> None:
    call(f"/models/{urllib.parse.quote(str(model_id))}", token, method="DELETE")


def _shape_project(p: Any) -> dict:
    """Project the site's record onto a stable shape. Extra keys the site grows are dropped rather
    than forwarded, so a site-side addition can never surprise the browser."""
    p = p if isinstance(p, dict) else {}
    return {
        "id": p.get("id"),
        "title": str(p.get("title") or "Untitled project"),
        "cloud_project_id": p.get("cloud_project_id"),
        "status": p.get("status") or "active",
        "model_count": int(p.get("model_count") or 0),
        "updated": p.get("updated"),
    }


def _shape_model(m: Any) -> dict:
    m = m if isinstance(m, dict) else {}
    return {
        "id": m.get("id"),
        "title": str(m.get("title") or "Untitled model"),
        "project_id": m.get("project_id"),
        "format": m.get("format") or "mass",
        "size_bytes": int(m.get("size_bytes") or 0),
        "version": int(m.get("version") or 1),
        "cloud_model_id": m.get("cloud_model_id"),
        "thumb_url": m.get("thumb_url"),
        "preview_url": m.get("preview_url"),
        "metrics": m.get("metrics") if isinstance(m.get("metrics"), dict) else {},
        "download_url": m.get("download_url"),
        "updated": m.get("updated"),
    }
