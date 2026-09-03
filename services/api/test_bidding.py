"""Bid leveling: tabulate bid_submission records by bid_package; low/high/avg/spread + low flag.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bidding.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./bidding_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_bid"
os.environ.pop("AEC_RBAC", None)
for f in ("./bidding_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Bids"}).json()["id"]
    pkg = c.post(f"/projects/{pid}/modules/bid_package", json={"data": {"name": "Concrete", "trade": "03"}}).json()
    pkid = pkg["id"]
    for bidder, amt in [("Ace Concrete", 480000), ("BuildRight", 442000), ("CastCo", 510000)]:
        c.post(f"/projects/{pid}/modules/bid_submission",
               json={"data": {"bidder": bidder, "amount": amt, "package": pkid}})
    # a package with no bids should still appear
    c.post(f"/projects/{pid}/modules/bid_package", json={"data": {"name": "Steel", "trade": "05"}})

    lv = c.get(f"/projects/{pid}/bids/leveling").json()
    assert lv["package_count"] == 2 and lv["bid_count"] == 3, lv
    concrete = next(p for p in lv["packages"] if p["package"] == "Concrete")
    assert concrete["bid_count"] == 3 and concrete["low"] == 442000 and concrete["high"] == 510000, concrete
    assert concrete["avg"] == round((480000 + 442000 + 510000) / 3, 2)
    assert concrete["spread"] == 510000 - 442000
    low = [b for b in concrete["bids"] if b["is_low"]]
    assert len(low) == 1 and low[0]["bidder"] == "BuildRight", low
    assert concrete["bids"][0]["bidder"] == "BuildRight"          # sorted low-first
    steel = next(p for p in lv["packages"] if p["package"] == "Steel")
    assert steel["bid_count"] == 0 and steel["low"] is None and steel["spread"] == 0.0

    print("BIDDING OK - leveling by package: low/high/avg/spread, low-bidder flagged, empty package handled")
