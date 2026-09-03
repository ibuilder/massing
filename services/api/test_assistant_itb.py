"""Project assistant (whole-project Q&A snapshot) + ITB invitation tracking.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_assistant_itb.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_asitb.db"
os.environ["STORAGE_DIR"] = "./test_storage_asitb"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)        # AI off -> snapshot path
for _f in ("./test_asitb.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


def trans(c, pid, key, rid, action):
    return c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tower B"}).json()["id"]

    # --- G4: project assistant snapshot ---------------------------------------
    r1 = mk(c, pid, "rfi", {"subject": "Beam", "question": "size?"})
    mk(c, pid, "rfi", {"subject": "Door", "question": "swing?"})
    trans(c, pid, "rfi", r1, "submit")               # one open, one draft

    snap = c.get(f"/projects/{pid}/assistant/snapshot").json()
    assert snap["project"] == "Tower B", snap
    assert snap["modules"]["rfi"], snap["modules"]   # has rfi state counts
    assert sum(snap["modules"]["rfi"].values()) == 2, snap["modules"]["rfi"]

    ans = c.post(f"/projects/{pid}/assistant", json={"question": "How many open RFIs?"})
    assert ans.status_code == 200, ans.text[:160]
    body = ans.json()
    assert body["source"] == "disabled", body.get("source")        # no AI key -> snapshot
    assert body["snapshot"]["modules"]["rfi"], body["snapshot"]
    assert c.post(f"/projects/{pid}/assistant", json={"question": ""}).status_code == 422

    # --- G6: ITB invitations + tracking ---------------------------------------
    pkg = mk(c, pid, "bid_package", {"name": "Concrete", "trade": "Concrete", "budget": 500000})
    inv = c.post(f"/projects/{pid}/bidding/packages/{pkg}/invite",
                 json={"companies": ["ABC Concrete", "BuildRight", "ABC Concrete"]})  # dup ignored
    assert inv.status_code == 200 and inv.json()["bidders_invited"] == 2, inv.text[:160]

    # two of the invited respond, one with a bond
    mk(c, pid, "bid_submission", {"bidder": "ABC Concrete", "package": "Concrete", "amount": 480000, "bond_provided": True})
    mk(c, pid, "bid_submission", {"bidder": "BuildRight", "package": "Concrete", "amount": 510000, "bond_provided": False})
    # a second package nobody bid on (coverage gap)
    mk(c, pid, "bid_package", {"name": "Glazing", "trade": "Glass", "budget": 200000, "bidders_invited": 3})

    itb = c.get(f"/projects/{pid}/bidding/itb").json()
    assert itb["package_count"] == 2, itb
    concrete = next(r for r in itb["rows"] if r["package"] == "Concrete")
    assert concrete["invited"] == 2 and concrete["responses"] == 2 and concrete["bonded"] == 1, concrete
    assert concrete["low_bid"] == 480000, concrete
    assert itb["packages_without_bids"] == 1, itb       # Glazing
    glazing = next(r for r in itb["rows"] if r["package"] == "Glazing")
    assert glazing["coverage"] == "no bids", glazing

print("ASSISTANT+ITB OK - project snapshot (modules/schedule/budget) grounds the assistant (2 RFIs); "
      "ITB: invite dedupes to 2, 2 responses (1 bonded, low $480k), 1 coverage-gap package flagged")
