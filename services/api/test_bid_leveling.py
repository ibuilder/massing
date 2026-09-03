"""Bid leveling — deterministic (offline) apples-to-apples comparison of bid_submission records:
base-bid stats + outliers, scope matrix, scope-gap detection, scope-adjusted low recommendation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bid_leveling.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bid_leveling.db"
os.environ["STORAGE_DIR"] = "./test_storage_bid_leveling"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)          # deterministic path
for _f in ("./test_bid_leveling.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bid_leveling  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- engine unit test ---
bids = [
    {"data": {"bidder": "Ace Mechanical", "base_bid": 480000, "bond_provided": True,
              "inclusions": ["Ductwork", "Furnish and install VAV boxes"], "exclusions": ["Controls"]}},
    {"data": {"bidder": "Best HVAC", "base_bid": 455000,
              "inclusions": ["Ductwork"], "exclusions": ["Controls", "VAV boxes"]}},
    {"data": {"bidder": "Cut-Rate Air", "base_bid": 300000,          # outlier low, missing scope
              "inclusions": ["Ductwork"], "exclusions": ["Controls", "VAV boxes", "Test and balance"]}},
]
res = bid_leveling.level(bids)
assert res["source"] == "rules", res
assert res["base_stats"]["low"] == 300000 and res["base_stats"]["high"] == 480000, res["base_stats"]
assert "Cut-Rate Air" in res["outliers"], res["outliers"]      # >25% below median -> outlier
# VAV boxes is a scope gap: included by Ace, excluded by the others
gap_items = {g["item"] for g in res["gaps"]}
assert any("vav" in i for i in gap_items), gap_items
# recommendation flags the apparent-low as missing scope others carry
rec = res["recommendation"]
assert rec["apparent_low"] == "Cut-Rate Air" and rec["is_outlier"] and rec["missing_scope"], rec

# --- responsiveness: a `["No","Yes"]` SELECT is not a truthy object ---------------------------
#
# `bond_provided` was read as `bool(d.get("bond_provided"))`, and its options are the STRINGS "No"
# and "Yes". `bool("No")` is True, so a bidder who explicitly answered No reported as bonded while
# one who left the field blank reported as not bonded -- inverted exactly where it matters, since an
# explicit No is the answer somebody typed on purpose.
resp = bid_leveling.level([
    {"data": {"bidder": "Yes Co", "base_bid": 100, "bond_provided": "Yes",
              "addenda_acknowledged": "1-3"}},
    {"data": {"bidder": "No Co", "base_bid": 110, "bond_provided": "No",
              "addenda_acknowledged": "1-3"}},
    {"data": {"bidder": "Blank Co", "base_bid": 120}},
])
by = {b["bidder"]: b for b in resp["bids"]}
assert by["Yes Co"]["bond"] is True, by["Yes Co"]
assert by["No Co"]["bond"] is False, f'an explicit "No" still read as bonded: {by["No Co"]}'
assert by["Blank Co"]["bond"] is False, by["Blank Co"]

# `addenda_acknowledged` is captured by the register and was read by nothing. A bidder who
# acknowledged no addenda has not bid the current documents -- that disqualifies before price.
nr = {x["bidder"]: x["issues"] for x in resp["non_responsive"]}
assert "Yes Co" not in nr, nr
assert nr["No Co"] == ["no bid bond"], nr
assert set(nr["Blank Co"]) == {"no addenda acknowledged", "no bid bond"}, nr

# ...and the apparent low carries its own responsiveness, so a tab sorted by price cannot hide it.
assert resp["recommendation"]["responsiveness"] == [], resp["recommendation"]

# empty -> clean message, no fabrication
assert bid_leveling.level([])["vendors"] == []

# --- endpoint ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    pkg = c.post(f"/projects/{pid}/modules/bid_package",
                 json={"data": {"name": "HVAC", "trade": "Mechanical"}}).json()
    pkg_id = pkg["id"]
    for b in bids:
        d = dict(b["data"]); d["package"] = pkg_id
        assert c.post(f"/projects/{pid}/modules/bid_submission", json={"data": d}).status_code == 201
    r = c.get(f"/projects/{pid}/bids/leveling/{pkg_id}")
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["package"] and len(j["vendors"]) == 3, j
    assert j["recommendation"]["apparent_low"] == "Cut-Rate Air", j["recommendation"]
    # the existing summary endpoint still works (not shadowed by the new /{package_rid} route)
    assert c.get(f"/projects/{pid}/bids/leveling").status_code == 200

print("BID LEVELING OK - bond select read as a select (explicit 'No' is NOT bonded); "
      "addenda_acknowledged surfaced as non-responsive; base stats + >25% outlier flag; scope matrix + gap detection (VAV boxes); "
      "scope-adjusted recommendation flags low bidder missing scope; endpoint 200; summary route intact")
