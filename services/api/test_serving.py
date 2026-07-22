"""HTTP range serving test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_serving.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./serve_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
for f in ("./serve_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api import storage  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tiles"}).json()["id"]
    storage.put(f"{pid}/model.frag", bytes(range(256)))  # 256 known bytes

    # full request: 200 + Accept-Ranges
    full = c.get(f"/projects/{pid}/model.frag")
    assert full.status_code == 200, full.status_code
    assert full.headers["accept-ranges"] == "bytes"
    assert len(full.content) == 256

    # range request: 206 + Content-Range + exact slice
    r = c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206, r.status_code
    assert r.headers["content-range"] == "bytes 10-19/256", r.headers.get("content-range")
    assert r.content == bytes(range(10, 20)), r.content

    # open-ended range
    r2 = c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=250-"})
    assert r2.status_code == 206 and r2.content == bytes(range(250, 256))

    # unsatisfiable
    assert c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=999-"}).status_code == 416

    # --- ETag revalidation (stale-cache fix for republished models) ------------
    etag = full.headers.get("etag")
    assert etag, "frag must carry an ETag"
    assert "must-revalidate" in full.headers.get("cache-control", ""), full.headers.get("cache-control")
    # unchanged → 304, no body
    nm = c.get(f"/projects/{pid}/model.frag", headers={"If-None-Match": etag})
    assert nm.status_code == 304 and not nm.content, (nm.status_code, len(nm.content))
    # republish (new bytes) → ETag changes → full 200 (not a stale 304)
    storage.put(f"{pid}/model.frag", bytes(range(128)))
    again = c.get(f"/projects/{pid}/model.frag", headers={"If-None-Match": etag})
    assert again.status_code == 200 and again.headers.get("etag") != etag, "republished frag must refetch"

    # --- observability: /metrics in Prometheus text format ---------------------
    c.get("/health"); c.get("/health")          # generate some traffic on a stable route
    m = c.get("/metrics")
    assert m.status_code == 200 and m.headers["content-type"].startswith("text/plain")
    body = m.text
    assert "# TYPE http_requests_total counter" in body
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in body
    assert "http_request_duration_seconds_sum" in body and "http_requests_in_flight" in body
    # the matched route TEMPLATE is used, not the raw path (bounded label cardinality)
    assert "/projects/{pid}/model.frag" in body and pid not in body

    # --- Content-Disposition hardening (SEC F8): header-injection-safe filenames ----------------
    from aec_api.serving import content_disposition
    # path components and CR/LF are stripped so a client filename can't traverse or inject headers
    cd = content_disposition("../../etc/passwd")
    assert "\r" not in cd and "\n" not in cd, cd
    assert 'filename="passwd"' in cd, cd                 # basename only, no path
    inj = content_disposition("evil\r\nSet-Cookie: x=1.frag")
    assert "\r" not in inj and "\n" not in inj, inj      # CRLF injection neutralized
    # a double-quote is stripped from the ASCII fallback so it can't break out of the quoted-string
    assert 'filename="ab.ifc"' in content_disposition('a"b.ifc'), content_disposition('a"b.ifc')
    # empty/blank falls back to the default
    assert 'filename="download"' in content_disposition("   "), content_disposition("   ")
    # non-ASCII gets an RFC 5987 filename* form and a safe ASCII fallback (never crashes latin-1 headers)
    uni = content_disposition("план-façade.ifc")
    assert "filename*=UTF-8''" in uni, uni
    uni.encode("latin-1")                                # must be a legal HTTP header value

    print("SERVING OK — 200 full / 206 ranged / 416 unsatisfiable; Accept-Ranges; /metrics exposed; "
          "Content-Disposition strips traversal/CRLF and RFC-5987-encodes non-ASCII")
