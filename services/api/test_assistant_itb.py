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

    # --- ITB-DOUBLE: five defects, every one of them flattering -------------------------------
    #
    # The fixture above never reached any of them, and the reason is worth naming: `mk` posts a
    # record and the module engine assigns the REF, so a package's `name` is never equal to its
    # `ref` here -- while a user who names a package after its own reference hits defect (1) on
    # the first bid. *A test whose data-creation helper cannot produce the colliding case cannot
    # see a defect conditioned on that collision.* Both packages above also record an invite
    # count, which is what hid (2) and (3).
    #
    # (1) DOUBLE-COUNT. `subs_by_pkg.get(name) + subs_by_pkg.get(ref)`, two lookups concatenated
    # with no dedupe: every bid counted twice when the keys coincide.
    same = mk(c, pid, "bid_package", {"name": "Masonry", "bidders_invited": 10})
    pref = c.get(f"/projects/{pid}/modules/bid_package/{same}").json()["ref"]
    # Rename the package to its own ref, which is what a user does when the ref IS the name.
    c.patch(f"/projects/{pid}/modules/bid_package/{same}", json={"name": pref})
    for i in range(5):
        mk(c, pid, "bid_submission", {"bidder": f"M{i}", "package": pref, "amount": 1000,
                                      "bond_provided": True})
    it2 = c.get(f"/projects/{pid}/bidding/itb").json()
    row = next(r for r in it2["rows"] if r["package"] == pref)
    assert row["responses"] == 5, f"five bids counted as {row['responses']} (ITB-DOUBLE)"
    assert row["bonded"] == 5, row
    assert row["response_rate"] == 50.0, row       # 5 of 10, not 10 of 10
    assert row["coverage"] == "covered", row
    # Derived from the submissions actually posted, so the count cannot drift from the fixture.
    assert it2["submission_count"] >= 7 and it2["unmatched_submissions"] == 0, it2

    # (2) An unknown denominator is not 0%. A package with bids and no invite list recorded.
    noinv = mk(c, pid, "bid_package", {"name": "Painting"})
    mk(c, pid, "bid_submission", {"bidder": "P1", "package": "Painting", "amount": 500})
    it3 = c.get(f"/projects/{pid}/bidding/itb").json()
    pr = next(r for r in it3["rows"] if r["package"] == "Painting")
    assert pr["invited"] == 0 and pr["responses"] == 1, pr
    assert pr["response_rate"] is None, f"an unknown denominator reported as {pr['response_rate']}"
    assert pr["rate_basis"] == "no invite list recorded", pr
    assert noinv, "package id unused"

    # (3) The headline rate is over ONE population. `Painting` has bids and no invite count, so its
    # responses must not land on top of the other packages' invited totals.
    assert it3["unrated_packages"] >= 1 and it3["rated_packages"] >= 1, it3
    assert it3["rated_responses"] < it3["total_responses"], it3
    _rated = [r for r in it3["rows"] if r["invited"]]
    assert it3["overall_response_rate"] == round(
        100 * sum(r["responses"] for r in _rated) / sum(r["invited"] for r in _rated), 1), it3
    # (4) ...and so it cannot exceed 100%, which is what (1) and (3) looked like together.
    assert it3["overall_response_rate"] <= 100.0, it3["overall_response_rate"]
    assert "not in it" in it3["coverage_note"], it3["coverage_note"]

    # (5) A bid naming no package was dropped silently. Counted and named now.
    mk(c, pid, "bid_submission", {"bidder": "Ghost", "package": "Concrete Work", "amount": 1})
    it4 = c.get(f"/projects/{pid}/bidding/itb").json()
    assert it4["unmatched_submissions"] == 1, it4
    assert it4["submission_count"] == it4["total_responses"] + it4["unmatched_submissions"], it4
    assert "does not exist here" in it4["coverage_note"], it4["coverage_note"]

print("ASSISTANT+ITB OK - project snapshot (modules/schedule/budget) grounds the assistant (2 RFIs); "
      "ITB: invite dedupes to 2, 2 responses (1 bonded, low $480k), 1 coverage-gap package flagged")
