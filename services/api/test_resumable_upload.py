"""R41-UPLOAD-WARK — the resumable handshake, driven as a client would drive it.

Every check below goes through the HTTP routes rather than calling the helpers, because the thing that
matters is the PROTOCOL: that a client which loses its connection can re-handshake and be told what is
still missing, that an unchanged re-upload transfers nothing, and that a corrupted chunk is refused by
index rather than assembled into a broken object.

The pure arithmetic (`resumable.py`) is exercised here too, at the boundaries where it decides
something — the chunk plan for a small file, the manifest that does not match its own size.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_resumable_upload.py
"""
from __future__ import annotations

import hashlib
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_resumable_upload.db"
os.environ["STORAGE_DIR"] = "./test_storage_resumable_upload"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_resumable_upload.db"):
    os.remove("./test_resumable_upload.db")

import sys  # noqa: E402

sys.path.insert(0, "src")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import resumable  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def split(data: bytes, chunk: int) -> list[bytes]:
    return [data[i:i + chunk] for i in range(0, len(data), chunk)] or [b""]


# --- the pure half, at its decision points -------------------------------------------------------
check("a small file is ONE chunk of the minimum size, not many tiny ones",
      resumable.plan_chunk_size(40_000) == resumable.MIN_CHUNK
      and resumable.chunk_count(40_000, resumable.MIN_CHUNK) == 1)
# The property the design exists for: the manifest cannot grow without bound.
_big = 4 * 1024 ** 3
check("a 4 GiB file still fits the chunk CAP — the size grows, the count does not",
      resumable.chunk_count(_big, resumable.plan_chunk_size(_big)) <= resumable.MAX_CHUNKS,
      resumable.chunk_count(_big, resumable.plan_chunk_size(_big)))
check("...and a fixed 1 MiB part size would NOT have — that is the comparison",
      _big // resumable.MIN_CHUNK > resumable.MAX_CHUNKS)
check("zero bytes is one empty chunk, not zero chunks",
      resumable.chunk_count(0, resumable.MIN_CHUNK) == 1)

# The identity is content-derived AND project-scoped.
_h = [sha(b"a"), sha(b"b")]
check("the same content in the same project gets the same id",
      resumable.upload_id("p1", 10, _h) == resumable.upload_id("p1", 10, _h))
check("...and a DIFFERENT project gets a different one — no cross-tenant existence oracle",
      resumable.upload_id("p1", 10, _h) != resumable.upload_id("p2", 10, _h))
check("...and a changed chunk changes it", resumable.upload_id("p1", 10, _h)
      != resumable.upload_id("p1", 10, [sha(b"a"), sha(b"c")]))
check("...and a changed size changes it too",
      resumable.upload_id("p1", 10, _h) != resumable.upload_id("p1", 11, _h))


with TestClient(app) as c:
    c.headers.update({"X-User": "uploader@test"})
    pid = c.post("/projects", json={"name": "Uploads"}).json()["id"]

    # A file big enough to split into several chunks at the 1 MiB floor.
    DATA = bytes((i * 7 + 11) % 251 for i in range(3 * 1024 * 1024 + 1234))
    CHUNK = resumable.plan_chunk_size(len(DATA))
    parts = split(DATA, CHUNK)
    hashes = [sha(p) for p in parts]
    check("the fixture really does split into several chunks", len(parts) > 1, len(parts))

    # --- handshake ------------------------------------------------------------------------------
    r = c.post(f"/projects/{pid}/uploads/handshake",
               json={"size": len(DATA), "chunk_hashes": hashes, "filename": "model.ifc"})
    check("the handshake is accepted", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    hs = r.json()
    uid = hs["upload_id"]
    check("  it answers with the chunk size the client must use", hs["chunk_size"] == CHUNK, hs)
    check("  and needs every chunk on a first upload", hs["need"] == list(range(len(parts))), hs["need"])
    check("  and says it is not complete", hs["complete"] is False)

    # --- a corrupted chunk is refused BY INDEX ---------------------------------------------------
    bad = c.put(f"/projects/{pid}/uploads/{uid}/chunk/0",
                content=b"not the promised bytes", headers={"X-Chunk-Sha256": hashes[0]})
    check("a chunk that does not match its promised hash is REFUSED",
          bad.status_code == 422, f"{bad.status_code} {bad.text[:120]}")
    check("  ...and the refusal names the chunk index, so one chunk can be retried",
          "chunk 0" in bad.text, bad.text[:160])
    # The twin: the refusal must not have stored anything, or a later `complete` would assemble it.
    after = c.post(f"/projects/{pid}/uploads/handshake",
                   json={"size": len(DATA), "chunk_hashes": hashes}).json()
    check("  ...and nothing was stored, so chunk 0 is still needed", 0 in after["need"], after["need"])

    # --- upload half the chunks, then RESUME -----------------------------------------------------
    half = len(parts) // 2
    for i in range(half):
        r = c.put(f"/projects/{pid}/uploads/{uid}/chunk/{i}",
                  content=parts[i], headers={"X-Chunk-Sha256": hashes[i]})
        assert r.status_code == 200, f"chunk {i}: {r.status_code} {r.text[:120]}"

    # Resuming is the SAME request as starting. There is no resume endpoint and no session to expire.
    r2 = c.post(f"/projects/{pid}/uploads/handshake",
                json={"size": len(DATA), "chunk_hashes": hashes})
    hs2 = r2.json()
    check("RESUMING IS THE SAME REQUEST — re-handshaking returns the same id",
          hs2["upload_id"] == uid, (uid[:12], hs2["upload_id"][:12]))
    check("  ...and asks only for the chunks still missing",
          hs2["need"] == list(range(half, len(parts))), hs2["need"])

    # --- finish and assemble ---------------------------------------------------------------------
    for i in range(half, len(parts)):
        r = c.put(f"/projects/{pid}/uploads/{uid}/chunk/{i}",
                  content=parts[i], headers={"X-Chunk-Sha256": hashes[i]})
        assert r.status_code == 200, f"chunk {i}: {r.status_code} {r.text[:120]}"

    hs3 = c.post(f"/projects/{pid}/uploads/handshake",
                 json={"size": len(DATA), "chunk_hashes": hashes}).json()
    check("with every chunk in, the handshake reports complete", hs3["complete"] is True, hs3)

    r = c.post(f"/projects/{pid}/uploads/{uid}/complete", json={"chunks": len(parts)})
    check("the upload assembles", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    done = r.json()
    check("  the assembled size matches the bytes sent", done["bytes"] == len(DATA),
          (done.get("bytes"), len(DATA)))

    # THE LOAD-BEARING ASSERTION: the object is byte-identical to what the client had. Everything else
    # could pass over a file assembled in the wrong chunk order.
    from aec_api import storage  # noqa: E402
    stored = storage.get(done["key"])
    check("THE ASSEMBLED OBJECT IS BYTE-IDENTICAL to the original", stored == DATA,
          f"{len(stored)} vs {len(DATA)}, sha {sha(stored)[:12]} vs {sha(DATA)[:12]}")

    # --- deduplication: an unchanged re-upload transfers nothing ---------------------------------
    r4 = c.post(f"/projects/{pid}/uploads/handshake",
                json={"size": len(DATA), "chunk_hashes": hashes})
    hs4 = r4.json()
    check("AN UNCHANGED RE-UPLOAD NEEDS NOTHING — deduplication falls out of the identity",
          hs4["need"] == [] and hs4["complete"] is True, hs4)
    check("  ...and says so explicitly, rather than looking like a fresh empty upload",
          hs4.get("already") is True, hs4)
    # This is the case the first version got wrong: `complete` deletes the parts, so a handshake that
    # only looked for CHUNKS would have answered "I need all of them" for a file already stored.

    # --- completing twice is idempotent ----------------------------------------------------------
    r5 = c.post(f"/projects/{pid}/uploads/{uid}/complete", json={"chunks": len(parts)})
    check("completing an already-assembled upload is idempotent, not a 409",
          r5.status_code == 200 and r5.json()["bytes"] == len(DATA),
          f"{r5.status_code} {r5.text[:120]}")

    # --- refusals ---------------------------------------------------------------------------------
    r = c.post(f"/projects/{pid}/uploads/handshake",
               json={"size": len(DATA), "chunk_hashes": hashes[:-1]})
    check("a manifest whose chunk count disagrees with its size is refused",
          r.status_code == 422 and "chunk size" in r.text, f"{r.status_code} {r.text[:160]}")

    r = c.post(f"/projects/{pid}/uploads/handshake",
               json={"size": 10, "chunk_hashes": ["nothexdigest"]})
    check("a manifest entry that is not a sha256 digest is refused, by index",
          r.status_code == 422 and "chunk 0" in r.text, f"{r.status_code} {r.text[:160]}")

    r = c.post(f"/projects/{pid}/uploads/handshake",
               json={"size": resumable.MAX_UPLOAD_BYTES + 1, "chunk_hashes": [sha(b"x")]})
    check("an oversized declared size is refused at the HANDSHAKE, before any transfer",
          r.status_code == 422 and "cap" in r.text, f"{r.status_code} {r.text[:160]}")

    r = c.put(f"/projects/{pid}/uploads/{uid}/chunk/0", content=b"x",
              headers={"X-Chunk-Sha256": "short"})
    check("a chunk with a malformed hash header is refused", r.status_code == 422)

    r = c.post(f"/projects/{pid}/uploads/{uid}x/complete", json={"chunks": 3})
    check("completing an upload whose chunks are absent is a 409, naming what is missing",
          r.status_code == 409 and "missing" in r.text, f"{r.status_code} {r.text[:140]}")

    r = c.post("/projects/does-not-exist/uploads/handshake",
               json={"size": 10, "chunk_hashes": [sha(b"x")]})
    check("an unknown project is a 404 before any key is derived from it", r.status_code == 404)

    # --- THE CONSUMER: an assembled upload becomes a discipline model ------------------------------
    # Without this the handshake is an endpoint nobody can reach a feature through, which is the shape
    # this repo's reachability gate exists to catch.
    # IFC-shaped bytes, large enough to need several chunks. Deliberately free of escape sequences:
    # this literal is written by tooling, and a mangled escape here would look like a parser bug in
    # the code under test rather than a broken fixture.
    IFC = (b"ISO-10303-21;HEADER;FILE_DESCRIPTION((''),'2;1');ENDSEC;DATA;ENDSEC;"
           b"END-ISO-10303-21;") * 40_000
    iparts = split(IFC, resumable.plan_chunk_size(len(IFC)))
    ihashes = [sha(p) for p in iparts]
    ihs = c.post(f"/projects/{pid}/uploads/handshake",
                 json={"size": len(IFC), "chunk_hashes": ihashes}).json()
    for i in ihs["need"]:
        c.put(f"/projects/{pid}/uploads/{ihs['upload_id']}/chunk/{i}",
              content=iparts[i], headers={"X-Chunk-Sha256": ihashes[i]})
    ikey = c.post(f"/projects/{pid}/uploads/{ihs['upload_id']}/complete",
                  json={"chunks": len(iparts)}).json()["key"]

    r = c.post(f"/projects/{pid}/models/from-upload", json={"key": ikey, "discipline": "STR"})
    check("an assembled upload registers as a discipline model",
          r.status_code == 201, f"{r.status_code} {r.text[:160]}")
    reg = r.json() if r.status_code == 201 else {}
    check("  the registered size matches the uploaded bytes", reg.get("size") == len(IFC),
          (reg.get("size"), len(IFC)))
    check("  ...and it carries the discipline it was given", reg.get("discipline") == "STR", reg)
    listed = c.get(f"/projects/{pid}/models").json()
    check("  ...and it appears in the project's models",
          any(m.get("id") == reg.get("id") for m in (listed if isinstance(listed, list)
                                                     else listed.get("models", []))),
          str(listed)[:160])
    check("  the assembled upload is consumed, not left doubling the storage",
          not storage.exists(ikey))

    # --- the key check is the whole security of that route ----------------------------------------
    other = c.post("/projects", json={"name": "Someone else"}).json()["id"]
    oparts = split(IFC, resumable.plan_chunk_size(len(IFC)))
    ohashes = [sha(p) for p in oparts]
    ohs = c.post(f"/projects/{other}/uploads/handshake",
                 json={"size": len(IFC), "chunk_hashes": ohashes}).json()
    for i in ohs["need"]:
        c.put(f"/projects/{other}/uploads/{ohs['upload_id']}/chunk/{i}",
              content=oparts[i], headers={"X-Chunk-Sha256": ohashes[i]})
    okey = c.post(f"/projects/{other}/uploads/{ohs['upload_id']}/complete",
                  json={"chunks": len(oparts)}).json()["key"]

    r = c.post(f"/projects/{pid}/models/from-upload", json={"key": okey})
    check("A KEY FROM ANOTHER PROJECT IS REFUSED — a role check says you may write HERE, not that "
          "the object you named is yours", r.status_code == 403, f"{r.status_code} {r.text[:140]}")
    check("  ...and the other project's object is untouched by the refusal", storage.exists(okey))

    for bad in ("projects/../etc/passwd", f"projects/{pid}/uploads/", "", f"{pid}/models/x.ifc"):
        r = c.post(f"/projects/{pid}/models/from-upload", json={"key": bad})
        check(f"  a key outside the project prefix is refused: {bad!r}",
              r.status_code == 403, f"{r.status_code} {r.text[:90]}")

    r = c.post(f"/projects/{pid}/models/from-upload",
               json={"key": f"projects/{pid}/uploads/deadbeef"})
    check("  a well-formed key with nothing behind it is a 404, not a 500", r.status_code == 404)


if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_resumable_upload OK")
