"""Speckle interoperability bridge — OPTIONAL, open-data exchange with the Speckle ecosystem.

OFF unless SPECKLE_SERVER + SPECKLE_TOKEN are set. Speckle is open-source and self-hostable, so this
stays true to the offline/self-hosted ethos: point it at your own Speckle server. IFC/Fragments remain
the source of truth here; this lets a project's data round-trip to/from the wider AEC tool ecosystem
(Rhino/Grasshopper, Revit, Blender, web) that speaks Speckle.

When configured, status() performs a real connectivity check (GraphQL `serverInfo`). The full object
send/receive (Speckle's chunked base-object model) runs against a credentialed server and raises an
actionable error until wired — never fabricates a commit. All network calls are lazy + isolated so the
feature-flag gate is testable without a server."""
from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import settings_store


def _server() -> str:
    # settings_store: a value saved in the Settings UI (DB) wins, else the env var — so a
    # non-technical user can configure Speckle from the app without touching code/env.
    return (settings_store.get("SPECKLE_SERVER") or "").rstrip("/")


def _allow_private() -> bool:
    # Escape hatch for genuinely self-hosted Speckle on a private LAN / localhost dev. Off by
    # default: the URL is admin-settable, so an unguarded fetch is an SSRF vector (an attacker who
    # can set it could probe internal services / cloud metadata). Opt in explicitly per deployment.
    v = (settings_store.get("SPECKLE_ALLOW_PRIVATE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _validate_server_url(url: str) -> None:
    """Guard the admin-settable Speckle URL against SSRF before any request.

    Require https and a hostname; unless SPECKLE_ALLOW_PRIVATE is set, refuse hosts that resolve to
    a private, loopback, link-local, or otherwise non-global address (blocks cloud-metadata / intranet
    probing). Raises ValueError with an actionable message; callers surface it as an unreachable state."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("SPECKLE_SERVER must be an https:// URL.")
    host = parsed.hostname
    if not host:
        raise ValueError("SPECKLE_SERVER has no host.")
    if _allow_private():
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"SPECKLE_SERVER host does not resolve: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_loopback or ip.is_link_local:
            raise ValueError(
                "SPECKLE_SERVER resolves to a private/loopback address; refused to prevent "
                "server-side request forgery. Set SPECKLE_ALLOW_PRIVATE=1 to allow a self-hosted "
                "LAN server.")


def _token() -> str:
    return settings_store.get("SPECKLE_TOKEN") or ""


def is_enabled() -> bool:
    """Available only when a Speckle server URL + a personal access token are configured."""
    return bool(_server() and _token())


def _graphql(query: str, timeout: int = 15) -> dict:
    server = _server()
    _validate_server_url(server)                       # SSRF guard on the admin-settable URL
    req = urllib.request.Request(
        f"{server}/graphql", data=json.dumps({"query": query}).encode(),
        method="POST", headers={"Content-Type": "application/json",
                                "Authorization": f"Bearer {_token()}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def status() -> dict:
    """What the UI checks before offering Speckle send/receive (and how to turn it on)."""
    if not is_enabled():
        return {
            "enabled": False, "connected": False, "server": _server() or None,
            "message": "Speckle bridge not configured — set SPECKLE_SERVER (e.g. your self-hosted "
                       "https://speckle.yourco.com) and SPECKLE_TOKEN (a personal access token). "
                       "Speckle is open-source; IFC stays the source of truth.",
        }
    try:
        info = _graphql("query{ serverInfo { name version } }")
        si = (info.get("data") or {}).get("serverInfo") or {}
        return {"enabled": True, "connected": bool(si), "server": _server(),
                "server_name": si.get("name"), "server_version": si.get("version"),
                "message": f"Connected to Speckle server '{si.get('name', _server())}'."}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return {"enabled": True, "connected": False, "server": _server(),
                "message": f"Speckle configured but unreachable: {e}. Check SPECKLE_SERVER / SPECKLE_TOKEN."}


def send_model(pid: str, project_name: str, source_ifc: str | None) -> dict:
    """Send a project's model/data to a Speckle stream as a new commit.

    Raises a clear, actionable error until the send is wired against your server — rather than
    fabricating a commit. The object serialization (Speckle base-object model + chunked upload) runs
    in a credentialed deployment; use specklepy or the object API there."""
    if not is_enabled():
        raise RuntimeError("Speckle bridge not configured (set SPECKLE_SERVER / SPECKLE_TOKEN).")
    raise NotImplementedError(
        "Speckle send serializes the model to Speckle's base-object model and uploads a commit — "
        "this runs against your configured Speckle server. Provision specklepy (or the object API) "
        "in your deployment to enable it; connectivity is verified by status().")
