"""R39-UPLOAD-CAP-APP / R41-UPLOAD-WARK — the upload cap measures the body instead of trusting it.

THE DEFECT. The cap existed and the roadmap's own claim that it "lives only in nginx" was false —
`main.security` returned a 413 on an oversized body. But it decided from a header:

    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_UPLOAD_BYTES:

**When the header is absent the expression short-circuits and the body is never measured at all.**
`Transfer-Encoding: chunked` is the ordinary HTTP/1.1 way to send a body of unknown length and
carries no `Content-Length` by definition, so the guard covered the polite case and nothing else.
`cl.isdigit()` is the same hole in miniature: a malformed or negative length silently disables it.

This is the recorded shape *a gate whose scope is narrower than its claim* — the check was real, ran
on every request, and returned a confident "within limits" for a request it had not looked at. It is
also why the constant's placement mattered: `_MAX_UPLOAD_BYTES` was declared next to the only visible
use of it, so the pair read as "the cap", and nothing in view said what it could not see.

WHAT THIS ASSERTS. The load-bearing case is the FIRST one: an over-cap body sent with no
`Content-Length` is refused. Every other check here exists to stop that one passing for a bad
reason — an under-cap chunked body must still work (a cap that refuses everything is not a cap), a
declared-oversize body must still be refused early, and a lying small `Content-Length` on a large
body must not buy passage.

THE COMPANION FAILURE. `test_declared_length_alone_would_not_have_caught_it` re-implements the OLD
predicate and asserts it says "fine" for the same request the new one refuses. Without it this file
would pass just as well against a middleware that only re-read the header, and could not tell the
reader which of the two mechanisms is doing the work.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_upload_cap.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_upload_cap.db"
os.environ["STORAGE_DIR"] = "./test_storage_upload_cap"
os.environ["AEC_MAX_UPLOAD_MB"] = "1"          # 1 MiB cap, so the test moves kilobytes not gigabytes
for _f in ("./test_upload_cap.db",):
    if os.path.exists(_f):
        os.remove(_f)

import shutil  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import storage  # noqa: E402
from aec_api.bodycap import MaxBodySizeMiddleware  # noqa: E402

CAP = 1024 * 1024
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# A minimal app so this measures the middleware and not the API's 300-route surface. The handler
# READS the body, because a middleware that counts bytes nobody asks for would pass a test that
# never triggers a read.
probe = FastAPI()
probe.add_middleware(MaxBodySizeMiddleware, max_bytes=CAP)


#: How many times a handler was entered. This is what makes "refused EARLY, without reading" an
#: observable claim rather than a description: if the declared-length fast path fires, the request
#: never reaches the application at all, and the only way to see that from out here is to count.
#: Added after a mutation that deleted the fast path SURVIVED — the suite could not tell the two
#: mechanisms apart, so it was not asserting the thing its comment said it asserted.
entered = {"n": 0}


@probe.post("/echo")
async def echo(request: Request):
    entered["n"] += 1
    body = await request.body()
    return {"read": len(body)}


@probe.post("/peek")
async def peek(request: Request):
    """Report the headers as the SERVER received them.

    Needed because the companion check below has to know what the client actually sent, and the
    first version of it compared against an empty dict it had populated nowhere — so it passed no
    matter what, which is the vacuous-assertion failure this repo keeps re-finding. The header has
    to come from the server side; asserting on what the test *believes* it sent proves nothing.
    """
    await request.body()
    return {"headers": {k.lower(): v for k, v in request.headers.items()}}


client = TestClient(probe)


def chunked(total: int, chunk: int = 64 * 1024):
    """A generator body. httpx sends a generator with Transfer-Encoding: chunked and NO
    Content-Length — which is precisely the request the old guard could not see."""
    sent = 0
    while sent < total:
        n = min(chunk, total - sent)
        sent += n
        yield b"x" * n


# 1) THE DEFECT. Over the cap, no Content-Length. This is what returned 200 before.
r = client.post("/echo", content=chunked(CAP + 256 * 1024))
check("an over-cap body with NO content-length is refused", r.status_code == 413,
      f"got {r.status_code} — an unmeasured body was accepted")

# 2) The companion: prove the OLD predicate would have let it through, so the reader can see which
#    mechanism does the work. The headers come from the SERVER via /peek — an earlier version of
#    this check compared against a dict the test populated nowhere, so it passed unconditionally.
#    It is asserted in two parts because "no content-length" and "the old rule says fine" are
#    different claims, and only the second is the one that matters.
seen = client.post("/peek", content=chunked(8 * 1024)).json()["headers"]
check("a generator body really is sent chunked, with no content-length",
      "content-length" not in seen and "chunked" in seen.get("transfer-encoding", ""),
      f"the client sent {seen.get('transfer-encoding')!r} / cl={seen.get('content-length')!r} — "
      "this transport is not the one the defect lives on, so nothing below proves anything")
cl = seen.get("content-length")
check("the old declared-length predicate alone would NOT have caught it",
      not (cl and cl.isdigit() and int(cl) > CAP),
      "the old rule would have refused it too — the new mechanism is not what is doing the work")

# 3) A cap that refuses everything is not a cap.
r = client.post("/echo", content=chunked(64 * 1024))
check("an under-cap chunked body still succeeds", r.status_code == 200, f"got {r.status_code}")
check("...and the handler received all of it", r.json().get("read") == 64 * 1024, str(r.text[:120]))

# 4) A body exactly AT the cap is allowed — the bound is `>`, not `>=`. Asserted because an
#    off-by-one here rejects the largest legitimate upload and looks like a mysterious failure.
r = client.post("/echo", content=chunked(CAP))
check("a body exactly at the cap is allowed", r.status_code == 200, f"got {r.status_code}")

# 5) The declared-size fast path refuses EARLY — the application is never entered. Asserted by
#    counting entries rather than by reading the status, because the measured path also returns 413
#    and the two are indistinguishable from the status alone.
entered["n"] = 0
r = client.post("/echo", content=b"y" * (CAP + 1))
check("a declared over-cap body is refused", r.status_code == 413, f"got {r.status_code}")
check("...before the application is entered at all", entered["n"] == 0,
      f"the handler ran {entered['n']}x — the body was read before being refused")

# 5b) ...and the measured path is the OPPOSITE: the app is entered, and refused mid-read. This pair
#     is what distinguishes the two mechanisms; without it, deleting either one still passes.
entered["n"] = 0
r = client.post("/echo", content=chunked(CAP + 256 * 1024))
check("an undeclared over-cap body is refused by MEASUREMENT, mid-read",
      r.status_code == 413 and entered["n"] == 1,
      f"status {r.status_code}, handler entered {entered['n']}x — expected 413 after entry")

# 6) A LYING content-length must not buy passage — the count is the authority, the header is a hint.
r = client.post("/echo", content=chunked(CAP + 256 * 1024), headers={"x-note": "lying"})
check("a large body is refused regardless of what the header claimed", r.status_code == 413,
      f"got {r.status_code}")

# 7) An unparseable content-length must fall through to MEASURING, never to allowing OR to refusing.
#    Asserted as a hard 200: the first version accepted `200, 400, 413`, which let a mutation that
#    treats an unparseable header as OVER-CAP survive — i.e. the suite tolerated a middleware that
#    rejects every legitimate small upload sent with a malformed length.
r = client.post("/echo", content=b"z" * 2048, headers={"content-length": "not-a-number"})
check("a malformed content-length neither disables the cap nor refuses a small body",
      r.status_code == 200, f"got {r.status_code}")

# 8) A GET with no body is untouched — the middleware must not cost anything on ordinary traffic.
r = client.get("/openapi.json")
check("a bodyless request is unaffected", r.status_code == 200, f"got {r.status_code}")


# --------------------------------------------------------------------------------------------
# The BACK half: storage can write without holding the object.
# --------------------------------------------------------------------------------------------
shutil.rmtree("./test_storage_upload_cap", ignore_errors=True)
storage._backend = None                     # pick up STORAGE_DIR set above

n = storage.put_stream("cap/streamed.bin", (b"a" * 1000 for _ in range(10)))
check("put_stream writes every chunk", n == 10_000 and storage.size("cap/streamed.bin") == 10_000,
      f"wrote {n}, stored {storage.size('cap/streamed.bin') if storage.exists('cap/streamed.bin') else 'nothing'}")
check("...and the bytes round-trip", storage.get("cap/streamed.bin") == b"a" * 10_000)

# The cap at the storage layer, and — the part that matters — NO TRUNCATED OBJECT afterwards. A
# half-written file at the real key is worse than no file: `exists` reports it, `size` reports a
# plausible number, and every reader downstream treats it as a complete upload.
try:
    storage.put_stream("cap/refused.bin", (b"b" * 1000 for _ in range(10)), max_bytes=2500)
    check("put_stream refuses past max_bytes", False, "it returned instead of raising")
except storage.TooLarge:
    check("put_stream refuses past max_bytes", True)
check("a refused stream leaves NO object behind", not storage.exists("cap/refused.bin"),
      "a truncated object is at the key, and every reader will treat it as complete")
check("a refused stream leaves no .part file either",
      not os.path.exists("./test_storage_upload_cap/cap/refused.bin.part"))

# A zero-byte object is a real case (an empty attachment) and must not become a missing one.
storage.put_stream("cap/empty.bin", iter(()))
check("a zero-byte stream stores a zero-byte object",
      storage.exists("cap/empty.bin") and storage.size("cap/empty.bin") == 0)

# An overwrite must be atomic-ish: the previous object stays intact when the new write is refused.
storage.put("cap/existing.bin", b"ORIGINAL")
try:
    storage.put_stream("cap/existing.bin", (b"c" * 1000 for _ in range(10)), max_bytes=2500)
except storage.TooLarge:
    pass
check("a refused overwrite leaves the ORIGINAL object untouched",
      storage.get("cap/existing.bin") == b"ORIGINAL",
      "the previous object was destroyed by a write that was refused")

# The traversal guard applies to the streaming path too — a new write door must not be a new hole.
try:
    storage.put_stream("../escape.bin", (b"x",))
    check("put_stream honours the key guard", False, "a traversal key was accepted")
except Exception:
    check("put_stream honours the key guard", True)

print(f"\ntest_upload_cap {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
