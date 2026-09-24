"""SITE-1 review — `PUT /projects/{pid}/property` must MERGE, not replace.

`dev_property` is one JSON blob with several owners: the property & tax form owns parcel, areas,
purchase and tax keys; `realestate.save_appraisal` owns `appraisal`; and SITE-1 added a third writer,
the feasibility tab, which saves `parcel_boundary` **and nothing else**.

The route preserved exactly one key across a write — `appraisal` — and let `body` replace the rest.
That was safe for as long as every caller round-tripped the whole blob, which the property form does:
it GETs the record, mutates the object in place and PUTs it back. **The narrow carve-out was not a
merge, it was a replace with one exception, and it read as a merge for as long as there was only one
kind of caller.** The moment a writer sent a single key, that write deleted the address, the
block/lot, the purchase price, the areas and every tax line.

*A merge written for one key is a replace for every other, and the bill arrives with the next
caller.* SITE-1 is the next caller, which is why this is filed against it rather than against the
change that introduced the carve-out.

The clear must still clear: `parcel_boundary: None` is a key PRESENT in the body, so it wins over the
stored value — which is what distinguishes "omitted, keep it" from "sent as null, drop it", and is
the distinction a full merge is built on.

Run from ``services/api``:
    PYTHONPATH="src:../data/src" .venv/bin/python test_property_merge.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_property_merge.db"
os.environ["STORAGE_DIR"] = "./test_storage_property_merge"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_property_merge.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FULL = {"purchase_price": 15_744_700, "building_sf": 249_749, "land_sf": 598_668,
        "address": "120 Mill Street", "block": "14", "lot": "7",
        "taxes": {"school": 955_533, "county": 239_731}}
RING = {"ring_m": [[0, 0], [30, 0], [30, 20]], "area_m2": 600.0, "vertices": 3}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Merge"}).json()["id"]

    # The property form writes the whole blob, as it always has.
    assert c.put(f"/projects/{pid}/property", json=FULL).status_code == 200

    # A second owner writes `appraisal` into the SAME blob.
    stored = c.get(f"/projects/{pid}/property").json()["property"]
    assert c.put(f"/projects/{pid}/property",
                 json={**stored, "appraisal": {"value": 21_000_000}}).status_code == 200

    # THE DEFECT: the feasibility tab saves ONE key. Before the fix this reply — and the stored row —
    # came back as `{"parcel_boundary": …}` and nothing else.
    r = c.put(f"/projects/{pid}/property", json={"parcel_boundary": RING})
    assert r.status_code == 200, r.text
    after = r.json()["property"]
    for k, v in FULL.items():
        assert after.get(k) == v, f"the single-key write DELETED {k!r}: {after.get(k)!r} != {v!r}"
    assert after.get("appraisal") == {"value": 21_000_000}, "the other owner's key was dropped"
    assert after["parcel_boundary"] == RING

    # The RESPONSE must describe the row that was written, not the body that was sent — the contract
    # defect the route's own comment records having shipped once already.
    reread = c.get(f"/projects/{pid}/property").json()["property"]
    assert reread == after, ("the response and the stored row disagree; a caller reading the reply "
                            f"sees a different record than the next GET returns\n{after}\n{reread}")

    # `body` still WINS where the two overlap — a merge that preferred the stored value would make
    # the form unable to change anything, which is the opposite failure and just as total.
    won = c.put(f"/projects/{pid}/property", json={"purchase_price": 1}).json()["property"]
    assert won["purchase_price"] == 1, "the stored value overrode the caller's — nothing can be edited"
    assert won["address"] == "120 Mill Street", "and the rest must still survive that write"

    # A CLEAR is a key present with a null value, and must still clear. This is the one case a merge
    # can get wrong in the quiet direction: drop it and a removed parcel comes back.
    cleared = c.put(f"/projects/{pid}/property", json={"parcel_boundary": None}).json()["property"]
    assert cleared["parcel_boundary"] is None, "an explicit null did not clear the boundary"
    assert cleared["address"] == "120 Mill Street" and cleared["appraisal"] == {"value": 21_000_000}

print("PROPERTY-MERGE OK - `dev_property` is one blob with three owners and the route preserved "
      "exactly one key across a write, letting the body replace everything else. That read as a "
      "merge only because every caller round-tripped the whole record; SITE-1 added a writer that "
      "sends `parcel_boundary` alone, and that write deleted the address, block/lot, purchase "
      "price, areas and every tax line. A merge written for one key is a replace for every other, "
      "and the bill arrives with the next caller. The route now merges the body over the stored "
      "record: the body still wins where they overlap, so the form can still edit; an explicit "
      "null still clears, because the distinction that matters is a key OMITTED versus a key sent "
      "as null; and the response describes the row that was written rather than the body that was "
      "sent, which the route had already got wrong once.")
