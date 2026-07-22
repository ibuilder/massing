"""HTTP range serving (guide §2/§5): stream .frag tiles + attachments with byte ranges so
the viewer/CDN can request partial content. Works over either storage backend."""
from __future__ import annotations

import os
import re
from urllib.parse import quote

from fastapi import HTTPException, Request, Response

from . import storage

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def content_disposition(filename: str | None, disposition: str = "attachment",
                        fallback: str = "download") -> str:
    """Build a header-injection-safe Content-Disposition value from a (possibly attacker-controlled)
    filename. Strips any path and CR/LF, quotes an ASCII fallback for `filename="..."`, and adds an
    RFC 5987 `filename*=UTF-8''...` form so non-ASCII names survive without crashing latin-1 header
    encoding. Used for attachment/model/export downloads where the name comes from the client."""
    raw = os.path.basename(filename or "").replace("\r", "").replace("\n", "").strip()
    raw = raw or fallback
    # ASCII fallback: drop control chars and anything that could break the quoted-string / header
    ascii_name = "".join(c for c in raw if 32 <= ord(c) < 127 and c not in '"\\').strip() or fallback
    encoded = quote(raw, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def range_response(request: Request, key: str, media_type: str,
                   filename: str | None = None, disposition: str = "inline",
                   immutable: bool = True) -> Response:
    if not storage.exists(key):
        raise HTTPException(404, f"not found: {key}")
    total = storage.size(key)
    etag = storage.version(key)
    # `immutable` for assets that never change at a URL; otherwise revalidate so a republished model
    # (stable URL, new bytes) is refetched — a 304 keeps re-opens instant *and* correct.
    cache = "public, max-age=31536000, immutable" if immutable else "public, max-age=0, must-revalidate"
    # CORP so a COEP-isolated SPA (require-corp, for the viewer's SharedArrayBuffer WASM) can embed
    # these bytes cross-origin — otherwise <img>/fetch of attachments + model.frag are blocked.
    headers = {"Accept-Ranges": "bytes", "Cache-Control": cache, "ETag": etag,
               "Cross-Origin-Resource-Policy": "cross-origin"}
    if filename:
        headers["Content-Disposition"] = content_disposition(filename, disposition)

    inm = request.headers.get("if-none-match") or request.headers.get("If-None-Match")
    if inm and etag in [t.strip() for t in inm.split(",")]:   # conditional GET → 304, no body re-sent
        return Response(status_code=304, headers=headers)

    rng = request.headers.get("range") or request.headers.get("Range")
    if rng:
        m = _RANGE.fullmatch(rng.strip())
        if m:
            start = int(m.group(1)) if m.group(1) else 0
            end = int(m.group(2)) if m.group(2) else total - 1
            end = min(end, total - 1)
            if start > end or start >= total:
                raise HTTPException(416, "range not satisfiable")
            chunk = storage.backend().get_range(key, start, end)
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"
            return Response(chunk, status_code=206, media_type=media_type, headers=headers)

    return Response(storage.get(key), media_type=media_type, headers=headers)
