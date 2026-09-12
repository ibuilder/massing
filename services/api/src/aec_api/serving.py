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


# 255 bytes is the ext4/APFS/NTFS path-component limit; `modules.add_attachment` prefixes the
# stored name with a 36-char uuid and an underscore, so reserve that much of the budget.
_STORED_NAME_BYTES = 255 - 37


def stored_filename(filename: str | None, fallback: str = "file") -> str:
    """Normalise a client-supplied filename for PERSISTENCE — the value that goes in a row and is
    later rendered back to other users.

    Strips any path component and every control character, and caps the length. It deliberately
    does NOT touch `&`, `<`, `>` or quotes: those are legal in a filename (`Q&A notes.pdf`), and
    mangling them here would corrupt real names while giving a false sense of safety. **Escaping is
    the renderer's job** — an XSS fixed by input filtering stays fixed only until the next sink.

    This is hygiene, not the XSS control. The control is `escapeHtml` at the point of interpolation.

    One surprise worth naming, because the first check written against this "failed" on it: a name
    containing `/` is truncated at the last one, so `Q&A <b>notes</b>.pdf` stores as `b>.pdf`. That
    is `os.path.basename` doing its job, not this function mangling markup — `/` is a path separator
    and is not legal in a filename on any mainstream filesystem, so a multipart value carrying one
    is already either a path or an attack. `Q&A notes.pdf`, `a<b>c.pdf` and quoted names all pass
    through untouched. *The check was wrong, not the code* — which is only obvious once you print
    `os.path.basename` on its own.
    """
    raw = os.path.basename(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    raw = "".join(c for c in raw if ord(c) >= 32 and c != "\x7f").strip()
    # Truncate by UTF-8 BYTES, not characters, and leave room for the caller's prefix. `modules.
    # add_attachment` builds its storage key as `.../{aid}_{filename}`, and on the local backend
    # that key becomes a filesystem path whose component limit is 255 BYTES on ext4/APFS. 255
    # characters of non-ASCII is up to 1020 bytes, so a character cap let a legitimate upload fail
    # at write time with nothing in `validate_key` to explain it. `encode`/`decode(errors=ignore)`
    # drops a split multibyte character rather than storing a mojibake tail.
    return raw.encode("utf-8")[:_STORED_NAME_BYTES].decode("utf-8", "ignore").strip() or fallback


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
