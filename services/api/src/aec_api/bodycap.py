"""R39-UPLOAD-CAP-APP / R41-UPLOAD-WARK (front half) — count the body as it arrives.

**The cap existed and could not see the ordinary case.** `main.security` rejected an oversized body
with a 413 by reading `Content-Length`:

    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_UPLOAD_BYTES:

Every term in that condition is a way to skip the check, and the first one is the one that matters:
**when the header is absent the expression short-circuits and the body is never measured at all.**
`Transfer-Encoding: chunked` is the ordinary HTTP/1.1 way to send a body of unknown length — it is
what `curl -T`, most streaming clients and any generated-on-the-fly upload do — and it carries no
`Content-Length` by definition. So the guard covered the polite case and nothing else.

This is the shape recorded in the project notes as *a gate whose scope is narrower than its claim*:
the check was real, ran on every request, and returned a confident "within limits" for a request it
had not looked at. `cl.isdigit()` has the same property in miniature — a malformed or negative
`Content-Length` also silently disables it rather than being rejected.

**Why an ASGI middleware and not a fix inside `security`.** `security` is a `BaseHTTPMiddleware`
handler, which sees a `Request` whose body is consumed downstream; to count bytes as they arrive you
must sit on the `receive` callable itself, below that abstraction. Wrapping `receive` also means the
bound applies to **every** route with no per-route change — which matters here, because the
36+ `await file.read()` call sites are spread over fifteen routers and any list of them would be
out of date the day it was written. A cap enforced per-route is a cap someone will forget to add.

**What it does NOT do.** It does not stop a handler materialising the body it *did* receive: a
request under the cap is still read into memory by `await file.read()`. That is the back half of the
same item (`storage.put_stream`), and neither half closes it alone — bounding the front stops the
unbounded case, bounding the back stops the bounded-but-still-whole-file case.
"""
from __future__ import annotations

import json


class _BodyTooLarge(Exception):
    """Raised out of the wrapped `receive` once the running total passes the cap.

    An exception rather than a flag because the read happens deep inside the application (in a
    multipart parser, usually) and there is no return path from there back to the middleware. It
    propagates up through whatever was awaiting the body.
    """


_TOO_LARGE = json.dumps({"detail": "payload too large"}).encode("utf-8")


class MaxBodySizeMiddleware:
    """Reject a request body larger than `max_bytes`, measured rather than declared.

    Declared size is still honoured as a fast path: when `Content-Length` says the body is too big
    there is no reason to read a single chunk of it. But the header is treated as a *shortcut*, never
    as the measurement — the count below runs regardless of what the header said, so a lying or
    absent header changes only how early the request is refused, not whether it is.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":                      # websockets/lifespan have no request body
            return await self.app(scope, receive, send)

        if self._declared_over(scope):
            return await self._refuse(send)

        read = 0
        started = False

        async def counting_receive():
            nonlocal read
            message = await receive()
            if message.get("type") == "http.request":
                read += len(message.get("body", b"") or b"")
                if read > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def watching_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
        except _BodyTooLarge:
            # If the handler already began responding we cannot replace the status — the client has
            # the headers. Dropping out here still stops the read, which is the point; pretending we
            # could send a 413 on top would raise "response already started" and mask the refusal.
            if not started:
                await self._refuse(send)

    def _declared_over(self, scope) -> bool:
        for name, value in scope.get("headers") or []:
            if name.lower() != b"content-length":
                continue
            try:
                return int(value) > self.max_bytes
            except ValueError:
                return False          # unparseable: fall through to MEASURING, never to allowing
        return False

    async def _refuse(self, send) -> None:
        await send({"type": "http.response.start", "status": 413, "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(_TOO_LARGE)).encode("ascii")),
            (b"connection", b"close"),
        ]})
        await send({"type": "http.response.body", "body": _TOO_LARGE})
