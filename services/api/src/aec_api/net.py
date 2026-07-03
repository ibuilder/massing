"""Shared outbound-URL guard for the bridges/connectors that fetch an operator-configured URL.

The concrete risk these close: `urllib.request.urlopen` will happily follow *any* scheme, so a
mis-set (or maliciously set) config value of `file:///etc/passwd`, `gopher://…`, etc. becomes a
local-file-read / SSRF primitive. Every outbound fetch of a settable URL should pass through
`validate_outbound_url` first.

`speckle_bridge._validate_server_url` predates this and keeps its own (stricter, https-only) guard;
this is the reusable baseline for the rest.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse

_SAFE_SCHEMES = ("http", "https")


def validate_outbound_url(url: str, *, require_https: bool = False, allow_private: bool = True,
                          label: str = "URL") -> None:
    """Reject a settable outbound URL before it is fetched.

    Always: require an http/https scheme (blocks file://, gopher://, ftp://, data://, …) and a host.
    When ``require_https`` is set, refuse plain http. When ``allow_private`` is False, refuse hosts
    that resolve to a private/loopback/link-local/non-global address (blocks cloud-metadata + intranet
    probing) — most callers keep this True because on-prem/LAN endpoints (Power Automate, a local
    DocuSeal) are a legitimate operator choice, and the URL is operator-set rather than attacker-set.
    Raises ValueError with an actionable message; callers surface it as an unreachable/misconfigured
    state (they already treat the fetch as best-effort)."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in _SAFE_SCHEMES:
        raise ValueError(f"{label} must be an http(s):// URL (got scheme "
                         f"'{parsed.scheme or '(none)'}'); refused to prevent local-file/SSRF access.")
    if require_https and parsed.scheme != "https":
        raise ValueError(f"{label} must use https://.")
    host = parsed.hostname
    if not host:
        raise ValueError(f"{label} has no host.")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"{label} host does not resolve: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"{label} resolves to a private/loopback address; refused to prevent "
                             "server-side request forgery.")
