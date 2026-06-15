"""HTTP range serving (guide §2/§5): stream .frag tiles + attachments with byte ranges so
the viewer/CDN can request partial content. Works over either storage backend."""
from __future__ import annotations

import re

from fastapi import HTTPException, Request, Response

from . import storage

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def range_response(request: Request, key: str, media_type: str,
                   filename: str | None = None, disposition: str = "inline") -> Response:
    if not storage.exists(key):
        raise HTTPException(404, f"not found: {key}")
    total = storage.size(key)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=31536000, immutable"}
    if filename:
        headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'

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
