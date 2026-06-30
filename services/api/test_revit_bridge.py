"""Massing pyRevit bridge — the std-lib REST client (integrations/pyrevit/.../lib/massing_api.py)
that the Revit buttons use. The HTTP transport is faked so the create -> upload -> poll -> BCF flow
is verified without Revit/pyRevit. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_revit_bridge.py"""
import json
import os
import sys

# the bridge client lives with the pyRevit extension, not on the api path — import it directly
_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "integrations", "pyrevit",
                    "Massing.extension", "lib")
sys.path.insert(0, os.path.abspath(_LIB))

import massing_api as ma  # noqa: E402


class FakeTransport(object):
    """Records (method, url, headers, body) and replays queued (status, bytes) responses."""
    def __init__(self):
        self.calls = []
        self.queue = []

    def push(self, status, obj):
        self.queue.append((status, obj if isinstance(obj, bytes) else json.dumps(obj).encode()))

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.queue.pop(0) if self.queue else (200, b"{}")


# --- multipart encoder -------------------------------------------------------
ctype, body = ma.build_multipart("file", "m.ifc", b"ISO-10303-21;")
assert ctype.startswith("multipart/form-data; boundary=----massing"), ctype
assert b'name="file"; filename="m.ifc"' in body and b"ISO-10303-21;" in body, body

# --- auth header + base URL normalization ------------------------------------
t = FakeTransport()
c = ma.MassingClient("https://host/api/", "KEY123", app_url="https://host", transport=t)
assert c.base == "https://host/api" and c.app_url == "https://host"

# --- find_or_create: reuse by name -------------------------------------------
t.push(200, [{"id": "p1", "name": "Tower"}, {"id": "p2", "name": "Annex"}])
assert c.find_or_create_project("Annex") == "p2"
assert t.calls[-1]["method"] == "GET" and t.calls[-1]["url"].endswith("/projects")
assert t.calls[-1]["headers"]["Authorization"] == "Bearer KEY123"

# --- find_or_create: create when absent --------------------------------------
t.push(200, [])                        # list -> empty
t.push(201, {"id": "p9", "name": "New"})
assert c.find_or_create_project("New") == "p9"
create = t.calls[-1]
assert create["method"] == "POST" and create["url"].endswith("/projects")
assert json.loads(create["body"].decode())["name"] == "New"

# --- upload_ifc: multipart POST to source-ifc with publish flag ---------------
t.push(200, {"source_ifc": "/x/source.ifc", "size": 12, "publish": "running"})
res = c.upload_ifc("p9", b"ISO-10303-21;DATA;", filename="New.ifc")
up = t.calls[-1]
assert up["method"] == "POST" and "/projects/p9/source-ifc?publish=true" in up["url"], up["url"]
assert up["headers"]["Content-Type"].startswith("multipart/form-data"), up["headers"]
assert res["publish"] == "running"

# --- wait_for_publish: running -> done ---------------------------------------
t.push(200, {"state": "running"})
t.push(200, {"state": "done"})
done = c.wait_for_publish("p9", timeout=30, interval=0, sleeper=lambda s: None)
assert done["state"] == "done", done

# --- publish error surfaces as MassingError ----------------------------------
t.push(200, {"state": "error", "detail": {"error": "bad geometry"}})
try:
    c.wait_for_publish("p9", timeout=30, interval=0, sleeper=lambda s: None)
    raise AssertionError("expected MassingError on publish error")
except ma.MassingError as e:
    assert "bad geometry" in str(e), e

# --- BCF round-trip ----------------------------------------------------------
t.push(200, b"PK\x03\x04bcfzip-bytes")
blob = c.bcf_export("p9")
assert blob.startswith(b"PK") and t.calls[-1]["url"].endswith("/projects/p9/bcf/export")
t.push(201, {"imported": 3})
imp = c.bcf_import("p9", b"PK\x03\x04", filename="i.bcfzip")
assert imp["imported"] == 3 and t.calls[-1]["headers"]["Content-Type"].startswith("multipart/form-data")

# --- HTTP >=400 raises -------------------------------------------------------
t.push(404, {"detail": "nope"})
try:
    c.list_projects()
    raise AssertionError("expected MassingError on 404")
except ma.MassingError as e:
    assert "404" in str(e), e

# --- deep link ---------------------------------------------------------------
assert c.viewer_url("p9") == "https://host/?project=p9"

print("REVIT-BRIDGE OK - massing_api: multipart encode; bearer auth; find-or-create (reuse + create); "
      "IFC upload to source-ifc?publish=true; wait_for_publish running->done + error raises; BCF "
      "export/import multipart; HTTP>=400 raises; viewer deep link")
