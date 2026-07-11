"""buildingSMART Data Dictionary (bSDD) lookup client.

A thin, read-only httpx client over the public bSDD API v1
(https://api.bsdd.buildingsmart.org). It backs the reference-data lookups
in routers/standards.py (classes + their properties) so authors can align
model data to bSDD classifications.

Security: the host is a FIXED trusted constant (overridable only by the
operator via AEC_BSDD_BASE) — never user-controlled, so there is no SSRF
surface. Only query params come from the caller.

Testability: every request goes through `_client(transport=...)`; passing an
`httpx.MockTransport` lets tests exercise the parsing without touching the
network (see test_bsdd.py).
"""
from __future__ import annotations

import os

import httpx

BSDD_BASE = "https://api.bsdd.buildingsmart.org"
# Canonical root for bSDD (and IFC) dictionary/class identifiers. A classification value that starts
# with this is a real linked-data reference into a buildingSMART Data Dictionary — not just a local code.
BSDD_URI_ROOT = "https://identifier.buildingsmart.org"
_TIMEOUT = 8.0


def is_bsdd_uri(value: str | None) -> bool:
    """True when `value` is a buildingSMART Data Dictionary URI (the identifier a fully bSDD-aligned
    classification carries), as opposed to a bare code like 'Pr_20_93_52' or a free-text label."""
    return isinstance(value, str) and value.strip().lower().startswith(BSDD_URI_ROOT.lower() + "/")


def parse_uri(uri: str) -> dict[str, str | None]:
    """Best-effort split of a bSDD class URI into its parts. bSDD URIs look like
    `https://identifier.buildingsmart.org/uri/<org>/<dictionary>/<version>/class/<code>`.
    Returns `{"organization","dictionary","version","code","dictionary_uri"}` — any part that
    can't be located is None. Never raises; a non-bSDD string yields all-None."""
    out: dict[str, str | None] = {"organization": None, "dictionary": None, "version": None,
                                  "code": None, "dictionary_uri": None}
    if not is_bsdd_uri(uri):
        return out
    rest = uri.strip().split("/uri/", 1)[1] if "/uri/" in uri else ""
    parts = [p for p in rest.split("/") if p]
    if len(parts) >= 1:
        out["organization"] = parts[0]
    if len(parts) >= 2:
        out["dictionary"] = parts[1]
    if len(parts) >= 3:
        out["version"] = parts[2]
    if "class" in parts:
        i = parts.index("class")
        if i + 1 < len(parts):
            out["code"] = parts[i + 1]
    if out["organization"] and out["dictionary"]:
        ver = f"/{out['version']}" if out["version"] else ""
        out["dictionary_uri"] = f"{BSDD_URI_ROOT}/uri/{out['organization']}/{out['dictionary']}{ver}"
    return out
_CACHE_MAX = 512
# Module-level response cache keyed by (path, sorted-params). Bounded (oldest
# evicted first) so repeated lookups are cheap without growing unbounded.
_cache: dict[str, object] = {}


def _base() -> str:
    return os.environ.get("AEC_BSDD_BASE", BSDD_BASE).rstrip("/")


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The one place an httpx.Client is built. Tests inject an httpx.MockTransport
    here to run fully offline; production passes nothing (real network)."""
    kwargs: dict[str, object] = {"base_url": _base(), "timeout": _TIMEOUT}
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.Client(**kwargs)


def _cache_key(path: str, params: dict[str, object]) -> str:
    parts = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{path}?{parts}"


def _get(path: str, params: dict[str, object], transport: httpx.BaseTransport | None = None) -> object:
    """GET `path` with `params`, returning parsed JSON. Cached by URL. Any
    network/HTTP/parse failure is re-raised as a clear RuntimeError so the
    caller never sees a raw httpx exception."""
    key = _cache_key(path, params)
    if key in _cache:
        return _cache[key]
    try:
        with _client(transport) as client:
            resp = client.get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"bSDD request failed: {exc}") from exc
    except ValueError as exc:  # non-JSON body
        raise RuntimeError(f"bSDD returned a non-JSON response: {exc}") from exc
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))  # evict oldest (insertion order)
    _cache[key] = data
    return data


def search_classes(text: str, dictionary_uri: str | None = None, limit: int = 20,
                   *, transport: httpx.BaseTransport | None = None) -> list[dict]:
    """Free-text search for bSDD classes matching `text`.

    Endpoint: GET /api/TextSearch/v1?SearchText=<text>&Limit=<n>[&DictionaryUris=<uri>].
    Returns a normalized list of `{"uri","name","code","dictionary"}`. The live
    response shape varies, so every field is read defensively via `.get(...)`.
    """
    params: dict[str, object] = {"SearchText": text, "Limit": limit}
    if dictionary_uri:
        params["DictionaryUris"] = dictionary_uri
    data = _get("/api/TextSearch/v1", params, transport)
    out: list[dict] = []
    classes = (data or {}).get("classes") if isinstance(data, dict) else None
    for c in classes or []:
        if not isinstance(c, dict):
            continue
        out.append({
            "uri": c.get("uri") or c.get("namespaceUri"),
            "name": c.get("name"),
            "code": c.get("code") or c.get("referenceCode"),
            "dictionary": c.get("dictionaryName") or c.get("dictionaryUri"),
        })
    return out


def get_class(uri: str, *, transport: httpx.BaseTransport | None = None) -> dict | None:
    """Fetch one bSDD class (with its properties) by its full `uri`.

    Endpoint: GET /api/Class/v1?Uri=<uri>&IncludeClassProperties=true.
    Returns `{"uri","name","code","dictionary","properties":[{"name","code","dataType"}...]}`
    or None when the class isn't found. Parsed defensively via `.get(...)`.
    """
    params = {"Uri": uri, "IncludeClassProperties": "true"}
    # A network/HTTP failure propagates as RuntimeError (endpoint → 502); a
    # well-formed response with no class parses to None (endpoint → 404).
    data = _get("/api/Class/v1", params, transport)
    if not isinstance(data, dict) or not (data.get("uri") or data.get("name")):
        return None
    props: list[dict] = []
    for p in data.get("classProperties") or data.get("properties") or []:
        if not isinstance(p, dict):
            continue
        props.append({
            "name": p.get("name"),
            "code": p.get("code") or p.get("propertyCode"),
            "dataType": p.get("dataType") or p.get("dataTypeName"),
        })
    return {
        "uri": data.get("uri") or data.get("namespaceUri"),
        "name": data.get("name"),
        "code": data.get("code") or data.get("referenceCode"),
        "dictionary": data.get("dictionaryName") or data.get("dictionaryUri"),
        "properties": props,
    }
