"""Module-record attachment download. Regression for the route-collision bug: bim.py's
/attachments/{id}/download (Attachment table, registered first) shadowed the module-record handler
(RecordAttachment table) and 404'd every portal image thumbnail. The module attachment now lives at a
distinct /module-attachments/{id}/download path.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_attachments.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_attachments.db"
os.environ["STORAGE_DIR"] = "./test_storage_attachments"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_attachments.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)    # enough bytes to stand in for an image

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Att"}).json()["id"]
    rid = c.post(f"/projects/{pid}/modules/rfi",
                 json={"data": {"subject": "Photo test", "question": "see attached"}}).json()["id"]

    up = c.post(f"/projects/{pid}/modules/rfi/{rid}/attachments",
                files={"file": ("site.png", PNG, "image/png")})
    assert up.status_code == 201, up.text[:200]
    aid = up.json()["id"]

    # download at the NEW distinct path -> 200 with the bytes + inline (so <img> renders it)
    dl = c.get(f"/module-attachments/{aid}/download")
    assert dl.status_code == 200, dl.status_code
    assert dl.content == PNG, "bytes round-trip"
    assert dl.headers.get("content-type", "").startswith("image/png"), dl.headers.get("content-type")
    assert "inline" in dl.headers.get("content-disposition", ""), dl.headers.get("content-disposition")
    # CORP header so a COEP-isolated SPA can embed the image cross-origin (else <img> is blocked)
    assert dl.headers.get("cross-origin-resource-policy") == "cross-origin", dict(dl.headers)

    # a safe raster image renders inline, with the anti-sniff + sandbox headers
    assert dl.headers.get("x-content-type-options") == "nosniff", dict(dl.headers)
    assert "sandbox" in dl.headers.get("content-security-policy", ""), dict(dl.headers)

    # SECURITY: a text/html (or SVG) upload must NOT be served inline as text/html — that would let a
    # malicious attachment run JS on the API origin against a lured member's session (stored-XSS).
    # It is forced to attachment + octet-stream so nothing executes.
    xss = c.post(f"/projects/{pid}/modules/rfi/{rid}/attachments",
                 files={"file": ("evil.html", b"<script>alert(document.cookie)</script>", "text/html")})
    assert xss.status_code == 201, xss.text[:200]
    xdl = c.get(f"/module-attachments/{xss.json()['id']}/download")
    assert xdl.status_code == 200
    assert xdl.headers.get("content-type", "").startswith("application/octet-stream"), xdl.headers.get("content-type")
    assert "attachment" in xdl.headers.get("content-disposition", ""), xdl.headers.get("content-disposition")
    # an SVG (a classic XSS vector) is likewise never inline
    svg = c.post(f"/projects/{pid}/modules/rfi/{rid}/attachments",
                 files={"file": ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "image/svg+xml")})
    sdl = c.get(f"/module-attachments/{svg.json()['id']}/download")
    assert "attachment" in sdl.headers.get("content-disposition", ""), sdl.headers.get("content-disposition")

    # the OLD shared path routes to bim.py's Attachment-table handler -> 404 for a module attachment id
    # (this is exactly the collision that broke thumbnails; the distinct path above is the fix)
    old = c.get(f"/attachments/{aid}/download")
    assert old.status_code == 404, f"expected the module id to miss bim's Attachment table, got {old.status_code}"

    # the attachment is listed on the record (so the UI knows to render a thumbnail)
    rec = c.get(f"/projects/{pid}/modules/rfi/{rid}").json()
    assert any(a["id"] == aid for a in rec.get("attachments", [])), rec.get("attachments")

    # --- BULK: every file must land, with ITS OWN bytes -------------------------------------------
    # The bulk route had no content assertion anywhere. Mutation-checked and it mattered: stubbing the
    # write so nothing was stored left `test_evidence_gate` GREEN, because that test only counts rows
    # (count == 3, three attachments listed) and a row is created whether or not bytes arrive.
    #
    # Distinct payloads of DIFFERENT LENGTHS on purpose, so a batch that stores one file three times
    # — or crosses two files' bytes — fails on content AND on size rather than only on the row count.
    #
    # What this does NOT prove, stated because the obvious claim is wrong: it does not guard the
    # route's `lambda f=f:` late-binding capture. That was checked by mutation — removing `f=f`
    # leaves this test green, and correctly so: the route awaits each `run_in_threadpool` INSIDE the
    # loop, so every lambda is invoked before the loop advances and the classic late-binding defect
    # cannot occur. The binding is harmless insurance, not load-bearing, and a comment claiming this
    # test defends it would be a confident wrong answer about our own coverage.
    BULK = [("one.bin", b"A"), ("two.bin", b"BB"), ("three.bin", b"CCC")]
    rid2 = c.post(f"/projects/{pid}/modules/rfi",
                  json={"data": {"subject": "Bulk", "question": "batch"}}).json()["id"]
    blk = c.post(f"/projects/{pid}/modules/rfi/{rid2}/attachments/bulk",
                 files=[("files", (n, b, "application/octet-stream")) for n, b in BULK])
    assert blk.status_code == 201, blk.text[:200]
    rows = blk.json()["attachments"]
    assert len(rows) == 3, rows

    by_name = {r["filename"]: r for r in rows}
    for name, payload in BULK:
        r = by_name.get(name)
        assert r is not None, f"{name} missing from {sorted(by_name)}"
        # size is put_stream's WRITTEN count, so a stored-nothing bug shows up here and not only
        # in the bytes below.
        assert r["size"] == len(payload), f"{name}: size {r['size']} != {len(payload)}"
        got = c.get(f"/module-attachments/{r['id']}/download")
        assert got.status_code == 200, (name, got.status_code)
        assert got.content == payload, f"{name}: stored {got.content!r}, expected {payload!r}"

    # ...and the three are genuinely distinct objects, not one file listed three times.
    assert len({r["id"] for r in rows}) == 3, rows

print("ATTACHMENTS OK - module-record attachment uploads + downloads at /module-attachments/{id}/download "
      "(200, bytes round-trip, image/png, inline disposition); the old /attachments/{id}/download path "
      "correctly 404s for a module id (bim.py's Attachment-table route no longer shadows thumbnails)")
