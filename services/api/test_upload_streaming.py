"""R41-UPLOAD-WARK back half — the big uploads are STREAMED, not held whole.

WHAT THIS EXISTS TO STOP GOING BACK. `storage.put_stream` shipped in v0.3.876 with **no adopters**,
so every upload route still did `data = await file.read()` and materialised the object. A primitive
with no callers is indistinguishable from a missing feature at runtime, and nothing in the suite
could tell the two apart — which is the same failure the reachability ratchet exists for, one layer
down.

THE ASSERTION IS ON CHUNK SIZE, NOT ON MEMORY. Measuring peak RSS in-process is noisy and would fail
on an unrelated allocation, so this instruments the storage boundary instead and asserts the
property that actually matters: **no single chunk handed to storage is the whole object**, and there
is more than one of them. That is what "streamed" means operationally, and it is exactly what
reverting a route to `.read()` + `put()` destroys.

Every claim is PAIRED with an integrity check. A route that streamed correctly but stored the wrong
bytes would satisfy a chunk-size assertion perfectly, so each case also reads the object back and
compares it byte for byte with what was uploaded. Streaming that loses data is worse than buffering.

WHY THESE FOUR ROUTES. They are the store-and-forward ones — the bytes go to storage and are not
parsed. Sites that hand the bytes to ifcopenshell / openpyxl / an XML parser are deliberately NOT
converted: those need the object in memory regardless, so streaming the write would change the code
without changing the peak. The classification was made by walking every `await …read()` site in
`src/aec_api` and looking at what the bound name is used for, not by picking the obvious ones.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_upload_streaming.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_upload_streaming.db"
os.environ["STORAGE_DIR"] = "./test_storage_upload_streaming"
for _f in ("./test_upload_streaming.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import storage  # noqa: E402
from aec_api.main import app  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# A body several times the chunk size, with a recognisable structure so a truncation or a reorder
# shows up as a mismatch rather than as a plausible-looking blob.
CHUNK = storage.UPLOAD_CHUNK
BODY = bytes(bytearray((i * 31 + (i >> 13)) % 251 for i in range(CHUNK * 3 + 12345)))
assert len(BODY) > CHUNK * 3


class Recorder:
    """Wraps the storage entry points the routes use and records the size of every chunk.

    Wraps the MODULE attributes because that is what the routes call (`storage.put_stream(...)`),
    so this measures the real path rather than a backend the routes might not be using.
    """

    def __init__(self) -> None:
        self.chunks: list[int] = []
        self.calls: list[str] = []
        self._orig = {k: getattr(storage, k) for k in ("put_stream", "stream_to_path", "put")}

    def _tap(self, it):
        for c in it:
            self.chunks.append(len(c))
            yield c

    def __enter__(self):
        rec = self

        def put_stream(key, chunks, max_bytes=None):
            rec.calls.append(f"put_stream:{key}")
            return rec._orig["put_stream"](key, rec._tap(chunks), max_bytes)

        def stream_to_path(dest, chunks, max_bytes=None):
            rec.calls.append(f"stream_to_path:{dest}")
            return rec._orig["stream_to_path"](dest, rec._tap(chunks), max_bytes)

        def put(key, data):
            # Recorded as a single chunk of the full length — which is precisely what makes a
            # reverted route fail the assertion below instead of passing quietly.
            rec.calls.append(f"put:{key}")
            rec.chunks.append(len(data))
            return rec._orig["put"](key, data)

        storage.put_stream, storage.stream_to_path, storage.put = put_stream, stream_to_path, put
        return self

    def __exit__(self, *a):
        for k, v in self._orig.items():
            setattr(storage, k, v)
        return False

    def reset(self) -> None:
        self.chunks.clear()
        self.calls.clear()

    @property
    def biggest(self) -> int:
        return max(self.chunks) if self.chunks else 0


def assert_streamed(rec: Recorder, label: str) -> None:
    """The two halves of "streamed": bounded chunks AND more than one of them.

    Either alone is satisfiable by accident — a one-chunk upload of a small file has a bounded
    biggest chunk, and a route could hand over many chunks one of which is the whole object.
    """
    check(f"{label}: no single chunk is the whole object",
          rec.biggest <= CHUNK and rec.biggest < len(BODY),
          f"biggest chunk {rec.biggest} of {len(BODY)} (limit {CHUNK}); calls={rec.calls}")
    check(f"{label}: ...and it took more than one chunk to get there",
          len(rec.chunks) > 1, f"{len(rec.chunks)} chunk(s); calls={rec.calls}")


with TestClient(app) as c, Recorder() as rec:
    pid = c.post("/projects", json={"name": "Streaming"}).json()["id"]

    # ---- 1. the project source IFC: the largest object the product accepts -------------------
    rec.reset()
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("model.ifc", BODY, "application/octet-stream")})
    check("source-ifc upload succeeds", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    assert_streamed(rec, "source-ifc")
    check("source-ifc reports the size it actually wrote",
          r.status_code == 200 and r.json().get("size") == len(BODY),
          f"{r.json().get('size') if r.status_code == 200 else r.text} vs {len(BODY)}")
    # INTEGRITY — both copies. The local one is what the converter opens; the durable one is what
    # survives a redeploy. A route that streamed one and lost the other would pass a chunk check.
    local = r.json().get("source_ifc") if r.status_code == 200 else None
    check("...and the LOCAL copy is byte-identical",
          bool(local) and open(local, "rb").read() == BODY,
          f"local={local}")
    check("...and the DURABLE copy is byte-identical",
          storage.get(f"{storage.safe_seg(pid)}/source.ifc") == BODY)

    # ---- 2. a discipline model (federated clash may carry several) ----------------------------
    rec.reset()
    r = c.post(f"/projects/{pid}/models", data={"discipline": "STR"},
               files={"file": ("str.ifc", BODY, "application/octet-stream")})
    check("discipline-model upload succeeds", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    assert_streamed(rec, "project model")
    mid = r.json().get("id") if r.status_code == 201 else None
    check("...and its durable copy is byte-identical",
          bool(mid) and storage.get(f"{storage.safe_seg(pid)}/models/{mid}.ifc") == BODY, str(mid))

    # ---- 3 + 4. the two attachment routes, which claim to be the same shape -------------------
    tid = c.post(f"/projects/{pid}/topics",
                 json={"type": "rfi", "title": "T", "author": "a", "status": "open"}).json()["id"]

    rec.reset()
    r = c.post(f"/projects/{pid}/topics/{tid}/attachments", data={"kind": "drawing"},
               files={"file": ("plan.pdf", BODY, "application/pdf")})
    check("native attachment upload succeeds", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    assert_streamed(rec, "attachment")
    check("attachment size is the bytes STORED, not the bytes intended",
          r.status_code == 201 and r.json().get("size") == len(BODY),
          f"{r.json().get('size') if r.status_code == 201 else r.text}")
    check("...and it reads back byte-identical",
          storage.get(f"{pid}/{tid}/plan.pdf") == BODY)

    guid = c.get(f"/bcf/3.0/projects/{pid}/topics").json()[0]["guid"]
    rec.reset()
    r = c.post(f"/bcf/3.0/projects/{pid}/topics/{guid}/document_references",
               files={"file": ("doc.pdf", BODY, "application/pdf")})
    check("BCF 3.0 document upload succeeds", r.status_code in (200, 201),
          f"{r.status_code} {r.text[:200]}")
    # The twin. Its docstring says "same storage path and filename hardening as the native
    # attachment route" — a pair that claims to be the same shape is exactly where a one-sided
    # conversion hides, so it is asserted rather than assumed.
    assert_streamed(rec, "BCF document")
    check("...and it reads back byte-identical", storage.get(f"{pid}/{tid}/doc.pdf") == BODY)

# ---- the refusal path: a bounded write must leave NOTHING, not a truncated file ---------------
# `stream_to_path` writes to `.part` and renames. Without that, a cap tripped mid-write leaves a
# plausible file at the real name that `exists()` reports and every reader treats as complete.
import pathlib  # noqa: E402

tmp = pathlib.Path(os.environ["STORAGE_DIR"]) / "refusal" / "capped.bin"
try:
    storage.stream_to_path(tmp, iter([b"x" * 1000, b"y" * 1000]), max_bytes=1500)
    check("a write over the cap raises", False, "no exception")
except storage.TooLarge:
    check("a write over the cap raises", True)
check("...and leaves no file at the destination", not tmp.exists(), str(tmp))
check("...and no .part debris either", not tmp.with_name(tmp.name + ".part").exists())

# A cap that never fires must not break the ordinary write — the refusal test above passes just as
# well against a function that always raises.
ok_path = pathlib.Path(os.environ["STORAGE_DIR"]) / "refusal" / "fine.bin"
n = storage.stream_to_path(ok_path, iter([b"x" * 1000, b"y" * 400]), max_bytes=1500)
check("a write under the cap still lands", n == 1400 and ok_path.read_bytes() == b"x" * 1000 + b"y" * 400,
      f"wrote {n}")

print(f"\ntest_upload_streaming {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
