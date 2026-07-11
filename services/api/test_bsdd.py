"""bSDD lookup client — parsing, cache, defensive parse, and endpoints (fully mocked, no network).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bsdd.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./_tb.db"
os.environ["STORAGE_DIR"] = "./_stb"
os.environ["AEC_TRUST_XUSER"] = "1"
for f in ("./_tb.db",):
    if os.path.exists(f):
        os.remove(f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bsdd  # noqa: E402
from aec_api.main import app  # noqa: E402

H = {"X-User": "admin"}

# Mocked bSDD payloads (shapes mirror the live API; we only assert our parsing).
SEARCH_BODY = {"classes": [
    {"uri": "https://identifier.buildingsmart.org/uri/bs/ifc/4.3/class/IfcWall",
     "name": "Wall", "code": "IfcWall", "dictionaryName": "IFC 4.3"},
    {"namespaceUri": "https://identifier.buildingsmart.org/uri/x/class/PartitionWall",
     "name": "Partition Wall", "referenceCode": "PW", "dictionaryUri": "https://x"},
]}
CLASS_BODY = {
    "uri": "https://identifier.buildingsmart.org/uri/bs/ifc/4.3/class/IfcWall",
    "name": "Wall", "code": "IfcWall", "dictionaryName": "IFC 4.3",
    "classProperties": [
        {"name": "Fire Rating", "code": "FireRating", "dataType": "String"},
        {"name": "Load Bearing", "propertyCode": "LoadBearing", "dataTypeName": "Boolean"},
    ],
}


def make_handler(counter):
    """A MockTransport handler that counts calls and routes by path."""
    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if request.url.path == "/api/TextSearch/v1":
            return httpx.Response(200, json=SEARCH_BODY)
        if request.url.path == "/api/Class/v1":
            return httpx.Response(200, json=CLASS_BODY)
        return httpx.Response(404, json={})
    return handler


# --- reset the module cache so ordering can't mask a cache miss/hit ----------
bsdd._cache.clear()

# --- search parses into the expected list shape ------------------------------
counter = {"n": 0}
transport = httpx.MockTransport(make_handler(counter))
rows = bsdd.search_classes("wall", transport=transport)
assert len(rows) == 2, rows
assert rows[0]["uri"].endswith("IfcWall") and rows[0]["name"] == "Wall"
assert rows[0]["code"] == "IfcWall" and rows[0]["dictionary"] == "IFC 4.3"
# second row uses the alternate field names (namespaceUri/referenceCode/dictionaryUri)
assert rows[1]["uri"].endswith("PartitionWall") and rows[1]["code"] == "PW"
assert counter["n"] == 1, "first search should hit the transport once"

# --- cache: an identical call must NOT touch the transport again -------------
rows2 = bsdd.search_classes("wall", transport=transport)
assert rows2 == rows
assert counter["n"] == 1, f"cache miss — transport hit {counter['n']} times"

# --- get_class parses the class + its properties -----------------------------
cls = bsdd.get_class("https://identifier.buildingsmart.org/uri/bs/ifc/4.3/class/IfcWall",
                     transport=transport)
assert cls is not None and cls["name"] == "Wall" and cls["code"] == "IfcWall"
assert len(cls["properties"]) == 2
assert cls["properties"][0] == {"name": "Fire Rating", "code": "FireRating", "dataType": "String"}
assert cls["properties"][1]["code"] == "LoadBearing" and cls["properties"][1]["dataType"] == "Boolean"
assert counter["n"] == 2, "get_class should have hit the transport once more"

# --- defensive parse: missing optional fields must not raise -----------------
def sparse_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/TextSearch/v1":
        # a class with no fields at all + a non-dict entry that must be skipped
        return httpx.Response(200, json={"classes": [{}, "not-a-dict"]})
    return httpx.Response(200, json={"uri": "https://x/class/Bare", "name": "Bare"})

bsdd._cache.clear()
sparse = httpx.MockTransport(sparse_handler)
srows = bsdd.search_classes("anything", transport=sparse)
assert srows == [{"uri": None, "name": None, "code": None, "dictionary": None}], srows
bare = bsdd.get_class("https://x/class/Bare", transport=sparse)
assert bare is not None and bare["name"] == "Bare" and bare["properties"] == []

# --- empty / not-found class returns None ------------------------------------
bsdd._cache.clear()
empty = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
assert bsdd.get_class("https://x/class/Missing", transport=empty) is None

# --- network failure raises a clean RuntimeError (never a raw httpx error) ---
bsdd._cache.clear()
def boom(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")

try:
    bsdd.search_classes("wall", transport=httpx.MockTransport(boom))
    raise AssertionError("expected RuntimeError on network failure")
except RuntimeError:
    pass

# --- bSDD URI recognition + linked-data alignment (pure, no network) ---------
WALL_URI = "https://identifier.buildingsmart.org/uri/buildingsmart/uniclass2015/1.2/class/Pr_20_93_52"
assert bsdd.is_bsdd_uri(WALL_URI) is True
assert bsdd.is_bsdd_uri("Pr_20_93_52") is False          # a bare code is not a URI
assert bsdd.is_bsdd_uri(None) is False and bsdd.is_bsdd_uri("") is False
p = bsdd.parse_uri(WALL_URI)
assert p["organization"] == "buildingsmart" and p["dictionary"] == "uniclass2015", p
assert p["version"] == "1.2" and p["code"] == "Pr_20_93_52", p
assert p["dictionary_uri"] == "https://identifier.buildingsmart.org/uri/buildingsmart/uniclass2015/1.2", p
assert bsdd.parse_uri("nope")["code"] is None            # non-bSDD string → all-None, no raise

# alignment separates "has any classification" from "is a real bSDD URI"
from aec_api import model_query, openbim_quality  # noqa: E402
_IDX = {
    "g1": {"guid": "g1", "ifc_class": "IfcWall", "type_name": "WT1", "name": "W1",
           "classification": WALL_URI},                  # bSDD-linked
    "g2": {"guid": "g2", "ifc_class": "IfcWall", "type_name": "WT1", "name": "W2",
           "classification": "Pr_20_93_52"},             # classified but bare code (not linked)
    "g3": {"guid": "g3", "ifc_class": "IfcSlab", "name": "S1"},   # unclassified
}
al = openbim_quality.bsdd_alignment(_IDX)
assert al["total"] == 3 and al["classified"] == 2 and al["bsdd_linked"] == 1, al
assert al["bsdd_linked_pct"] == round(100 / 3, 1), al
assert al["dictionaries"] and al["dictionaries"][0]["count"] == 1, al

# JSON-LD emits the bSDD URI as a resolvable @id-typed classification only for the linked element
ld = model_query.to_jsonld(_IDX)
assert ld["@context"]["classification"] == {"@type": "@id"}, ld["@context"]
nodes = {n["@id"]: n for n in ld["@graph"]}
assert nodes["g1"].get("classification") == WALL_URI, nodes["g1"]
assert "classification" not in nodes["g2"] and "classification" not in nodes["g3"]

# --- endpoints (monkeypatch the engine so the router never touches network) --
def fake_search(text, dictionary_uri=None, limit=20, *, transport=None):
    return [{"uri": "u", "name": text, "code": "C", "dictionary": "d"}]

def fake_get(uri, *, transport=None):
    return {"uri": uri, "name": "Wall", "code": "IfcWall", "dictionary": "IFC",
            "properties": [{"name": "Fire Rating", "code": "FireRating", "dataType": "String"}]}

bsdd.search_classes = fake_search
bsdd.get_class = fake_get

with TestClient(app) as c:
    r = c.get("/bsdd/search", params={"q": "wall"}, headers=H)
    assert r.status_code == 200, r.text[:160]
    assert r.json()["classes"][0]["name"] == "wall"

    r = c.get("/bsdd/class", params={"uri": "https://x/class/IfcWall"}, headers=H)
    assert r.status_code == 200, r.text[:160]
    assert r.json()["code"] == "IfcWall" and len(r.json()["properties"]) == 1

    # not-found → 404
    bsdd.get_class = lambda uri, *, transport=None: None
    assert c.get("/bsdd/class", params={"uri": "https://x/none"}, headers=H).status_code == 404

    # bSDD outage → 502 (not 500)
    def raiser(*a, **k):
        raise RuntimeError("bSDD down")
    bsdd.search_classes = raiser
    assert c.get("/bsdd/search", params={"q": "x"}, headers=H).status_code == 502

print("BSDD OK - TextSearch/v1 + Class/v1 parsed; cache hit verified (no re-fetch); "
      "defensive parse + None-on-empty + RuntimeError on network failure; "
      "endpoints 200/404/502 via monkeypatch; bSDD-URI recognition + parse; alignment separates "
      "classified vs bsdd_linked; JSON-LD emits bSDD URIs as resolvable @id classifications")
