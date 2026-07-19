"""CODE-1 jurisdiction code-context: the family/edition catalog is factual, and resolve() maps a
jurisdiction to adopted editions with a baseline fallback and a mandatory verify note.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_codes.py"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_codes.db"
os.environ["STORAGE_DIR"] = "./test_storage_codes"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_codes.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import codes  # noqa: E402

# --- families catalog: the I-Codes on their 3-year cycle -------------------------------------------
fam = codes.families()
assert "IBC" in fam["families"] and fam["families"]["IBC"]["name"].startswith("International Building")
assert 2021 in fam["families"]["IBC"]["editions"] and 2024 in fam["families"]["IBC"]["editions"]
assert fam["baseline"]["IBC"] == 2021

# --- a seeded jurisdiction resolves to its editions with an as-of year ------------------------------
ca = codes.resolve("ca")                       # case-insensitive
assert ca["jurisdiction"] == "CA" and ca["resolved"] is True and ca["as_of"], ca
ibc = next(c for c in ca["codes"] if c["family"] == "IBC")
assert ibc["edition"] == 2021 and ibc["source"] == "seed", ibc
assert ca["primary"]["IBC"] == 2021 and ca["primary"]["A117.1"] == 2017, ca["primary"]
assert ca["verify"], "must carry a verify-with-AHJ note"

# a partially-seeded state fills the rest from the baseline
il = codes.resolve("IL")
assert il["resolved"] and next(c for c in il["codes"] if c["family"] == "IBC")["source"] == "seed"
assert next(c for c in il["codes"] if c["family"] == "IECC")["source"] == "baseline", "unseeded family → baseline"

# --- an unseeded / empty jurisdiction falls back to the baseline, still with the verify note --------
zz = codes.resolve("ZZ")
assert zz["resolved"] is False and zz["as_of"] is None, zz
assert all(c["source"] == "baseline" for c in zz["codes"]) and zz["verify"], zz
base = codes.resolve(None)
assert base["jurisdiction"] is None and base["primary"]["IBC"] == 2021, base

assert "CA" in codes.seeded_jurisdictions() and "FL" in codes.seeded_jurisdictions()

# --- endpoints ------------------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///./_codes_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_codes")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

c = TestClient(app)
h = {"X-User": "tester"}
assert c.get("/codes/families", headers=h).json()["baseline"]["IBC"] == 2021
r = c.get("/codes/adoptions?jurisdiction=FL", headers=h).json()
assert r["resolved"] and r["primary"]["IBC"] == 2021 and r["verify"], r
assert "CA" in c.get("/codes/seeded", headers=h).json()["jurisdictions"]

# --- CODE-5: applicable code requirements → buildingSMART IDS -----------------
import xml.etree.ElementTree as ET  # noqa: E402

ids = c.get("/codes/ids", params={"description": "5-story R-2 apartment building, 40,000 sf",
                                  "edition": "IBC 2021"}, headers=h).json()
assert ids["spec_count"] > 0 and "<ids" in ids["ids_xml"], ids.get("spec_count")
# a fire-resistance-rated occupancy pulls in the rated-element groups
assert "walls" in ids["groups"] and "slabs" in ids["groups"], ids["groups"]
root = ET.fromstring(ids["ids_xml"])                       # schema-valid, well-formed IDS
assert root.tag.endswith("ids"), root.tag
assert any(t["code"] == "IBC" for t in ids["topics"]), ids["topics"]
# the download variant returns the .ids attachment
dl = c.get("/codes/ids", params={"description": "office, 8000 sf", "download": "true"}, headers=h)
assert dl.status_code == 200 and dl.headers["content-type"].startswith("application/xml")
assert "code-requirements.ids" in dl.headers.get("content-disposition", "")

# --- CODE-4: local-amendment overlay (pure functions) ----------------------------------------------
assert codes.validate_amendments([{"family": "IBC", "edition": 2018}]) == []
assert codes.validate_amendments([{"family": "IBC", "section": "1005.1", "note": "wider stairs"}]) == []
errs = codes.validate_amendments([{"family": "XYZ", "edition": 2018},        # unknown family
                                  {"family": "IBC", "edition": 2019},        # unpublished edition
                                  {"family": "IBC"},                          # nothing amended
                                  "not-a-dict"])                              # wrong shape
assert len(errs) == 4, errs
tx = codes.apply_amendments(codes.resolve("TX"), [{"family": "IBC", "edition": 2021},
                                                  {"family": "IECC", "section": "C402",
                                                   "note": "local envelope amendment"}])
ibc_tx = next(x for x in tx["codes"] if x["family"] == "IBC")
assert ibc_tx["edition"] == 2021 and ibc_tx["source"] == "amendment", ibc_tx   # beats the 2015 seed
assert tx["primary"]["IBC"] == 2021
assert next(x for x in tx["codes"] if x["family"] == "IRC")["edition"] == 2015, "unamended stays seeded"
assert len(tx["amendments"]) == 2 and "Local amendments" in tx["verify"], tx["amendments"]
# invalid overlays are skipped whole (validate first for the hard gate); context stays clean
bad = codes.apply_amendments(codes.resolve("TX"), [{"family": "IBC", "edition": 2019}])
assert next(x for x in bad["codes"] if x["family"] == "IBC")["edition"] == 2015 and bad["amendments"] == []

# --- CODE-1b/3/4: per-project jurisdiction + amendment overlay through the API ---------------------
with TestClient(app) as c2:                     # lifespan runs create_all for the project tables
    pid = c2.post("/projects", json={"name": "Juris Test"}, headers=h).json()["id"]
    pr = c2.patch(f"/projects/{pid}", json={"jurisdiction": "FL"}, headers=h)
    assert pr.status_code == 200 and pr.json()["jurisdiction"] == "FL", pr.text[:200]
    assert c2.get(f"/projects/{pid}", headers=h).json()["jurisdiction"] == "FL"   # round-trips on GET

    # CODE-4 endpoints: empty by default; PUT validates hard; the context reflects the overlay
    g0 = c2.get(f"/projects/{pid}/code/amendments", headers=h).json()
    assert g0["amendments"] == [] and g0["context"]["jurisdiction"] == "FL", g0
    bad_put = c2.put(f"/projects/{pid}/code/amendments",
                     json=[{"family": "IBC", "edition": 2019}], headers=h)
    assert bad_put.status_code == 422 and "2019" in bad_put.json()["detail"], bad_put.text[:200]
    ok_put = c2.put(f"/projects/{pid}/code/amendments",
                    json=[{"family": "IBC", "edition": 2018, "note": "city ordinance 24-101"}],
                    headers=h)
    assert ok_put.status_code == 200, ok_put.text[:300]
    ctx = ok_put.json()["context"]
    ibc_am = next(x for x in ctx["codes"] if x["family"] == "IBC")
    assert ibc_am["edition"] == 2018 and ibc_am["source"] == "amendment", ibc_am
    g1 = c2.get(f"/projects/{pid}/code/amendments", headers=h).json()
    assert g1["amendments"][0]["edition"] == 2018 and g1["context"]["primary"]["IBC"] == 2018

    # the amendment steers the CODE-3 auto-edition used by every model code check
    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.models import Project as _Proj  # noqa: E402
    from aec_api.routers.codecheck import _project_ibc_edition  # noqa: E402
    with SessionLocal() as _s:
        assert _project_ibc_edition(_s.get(_Proj, pid)) == 2018, "amendment beats the FL 2021 seed"

    # clearing restores the jurisdiction resolve
    assert c2.put(f"/projects/{pid}/code/amendments", json=[], headers=h).status_code == 200
    with SessionLocal() as _s:
        assert _project_ibc_edition(_s.get(_Proj, pid)) == 2021, "cleared → back to the FL seed"
from aec_api.routers.codecheck import _project_ibc_edition  # noqa: E402, F811


class _P:  # the resolver only reads .jurisdiction (+ optionally .id)
    jurisdiction = "FL"


assert _project_ibc_edition(_P()) == 2021, "FL seed adopts IBC 2021"
_P.jurisdiction = None
assert _project_ibc_edition(_P()) is None, "no jurisdiction → baseline (None)"

print("CODES OK - CODE-1 catalog lists the I-Code families + editions and the baseline; resolve() maps a "
      "jurisdiction to adopted editions (seed vs baseline per family), falls back to the baseline when "
      "unseeded, always carries a verify-with-AHJ note; /codes/families, /codes/adoptions, /codes/seeded serve it; "
      "CODE-5 /codes/ids emits the applicable requirements as well-formed buildingSMART IDS (+ .ids download).")
