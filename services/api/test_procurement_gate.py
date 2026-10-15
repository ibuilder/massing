"""Procurement compliance gate — can-bid / can-bill verdicts + the outbound nudge feed.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_procurement_gate.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_procgate.db"
os.environ["STORAGE_DIR"] = "./test_storage_procgate"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_procgate.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


today = date.today()
future = (today + timedelta(days=200)).isoformat()
soon = (today + timedelta(days=10)).isoformat()
past = (today - timedelta(days=5)).isoformat()

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # Vendor A — fully compliant: approved prequal + active COI + executed subcontract + waiver
    pqa = _create(c, pid, "prequalification", {"company": "Acme Concrete", "trade": "Concrete",
        "status": "Approved", "expires": future})
    _act(c, pid, "prequalification", pqa["id"], "submit")     # invited -> submitted
    _act(c, pid, "prequalification", pqa["id"], "approve")
    coia = _create(c, pid, "coi", {"vendor": "Acme Concrete", "coverage_type": "General Liability",
        "carrier": "Travelers", "expires": future})
    _act(c, pid, "coi", coia["id"], "approve")
    sca = _create(c, pid, "subcontract", {"vendor": "Acme Concrete", "trade": "Concrete", "value": 500000})
    _act(c, pid, "subcontract", sca["id"], "execute")
    wa = _create(c, pid, "lien_waiver", {"vendor": "Acme Concrete", "amount": 50000, "waiver_type": "Conditional Progress"})
    _act(c, pid, "lien_waiver", wa["id"], "receive")

    ga = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Acme Concrete"}).json()
    assert ga["can_bid"] is True and ga["can_bill"] is True, ga
    assert ga["coi"]["status"] == "active" and ga["waiver_on_file"] is True, ga

    # Vendor B — expired COI, prequal submitted (not approved), no subcontract
    pqb = _create(c, pid, "prequalification", {"company": "Bedrock LLC", "trade": "Earthwork",
        "status": "Submitted"})
    _act(c, pid, "prequalification", pqb["id"], "submit")     # submitted, deliberately NOT approved
    coib = _create(c, pid, "coi", {"vendor": "Bedrock LLC", "coverage_type": "General Liability",
        "carrier": "Hartford", "expires": past})
    _act(c, pid, "coi", coib["id"], "approve")

    gb = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Bedrock LLC"}).json()
    assert gb["can_bid"] is False and gb["can_bill"] is False, gb
    assert "no approved prequalification" in gb["bid_blockers"], gb["bid_blockers"]
    assert any("insurance" in b for b in gb["bid_blockers"]), gb["bid_blockers"]

    # Vendor C — active but soon-expiring COI, approved prequal
    pqc = _create(c, pid, "prequalification", {"company": "Crane Co", "trade": "Steel", "status": "Approved", "expires": future})
    _act(c, pid, "prequalification", pqc["id"], "submit")
    _act(c, pid, "prequalification", pqc["id"], "approve")
    coic = _create(c, pid, "coi", {"vendor": "Crane Co", "coverage_type": "General Liability",
        "carrier": "Chubb", "expires": soon})
    _act(c, pid, "coi", coic["id"], "approve")

    # --- compliance feed: B (expired + unapproved) and C (expiring) flagged; A clean ---------------
    feed = c.get(f"/projects/{pid}/procurement/compliance-feed").json()
    flagged = {v["vendor"] for v in feed["vendors"]}
    assert "Bedrock LLC" in flagged and "Crane Co" in flagged, flagged
    assert "Acme Concrete" not in flagged, "compliant vendor should not be nudged"
    bedrock = next(v for v in feed["vendors"] if v["vendor"] == "Bedrock LLC")
    assert any("expired" in i for i in bedrock["issues"]) and any("prequal" in i for i in bedrock["issues"]), bedrock

    # --- a vendor REJECTED once, then remediated and APPROVED, is not blocked by the old record ----
    # `list_records` orders by `created_at` ASCENDING, and the gate used to take the FIRST match per
    # vendor — so it judged a sub on their OLDEST prequalification. Delivered as `can_bid: False`
    # with "no approved prequalification" while an approved, unexpired one was on file: a false
    # blocker whose message sends someone to redo work already done.
    #
    # The direction matters. Every other filter defect found on this repo let something through;
    # this one refused a qualified vendor, which is why no money check would ever have surfaced it.
    dq = _create(c, pid, "prequalification", {"company": "Redeemed Steel", "expires": future})
    _act(c, pid, "prequalification", dq["id"], "submit")
    _act(c, pid, "prequalification", dq["id"], "reject")
    aq = _create(c, pid, "prequalification", {"company": "Redeemed Steel", "expires": future})
    _act(c, pid, "prequalification", aq["id"], "submit")
    _act(c, pid, "prequalification", aq["id"], "approve")
    rc = _create(c, pid, "coi", {"vendor": "Redeemed Steel", "expires": future,
                                 "gl_each_occurrence": 1_000_000})
    _act(c, pid, "coi", rc["id"], "approve")
    g = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Redeemed Steel"}).json()
    assert g["can_bid"] is True, g
    assert "no approved prequalification" not in g["bid_blockers"], g["bid_blockers"]
    assert g["prequal"]["status"] == "approved", g["prequal"]

    # ...and the converse still holds: rejected-only is still blocked, so the fix did not
    # turn the check into one that passes whenever ANY record exists.
    oq = _create(c, pid, "prequalification", {"company": "Never Qualified", "expires": future})
    _act(c, pid, "prequalification", oq["id"], "submit")
    _act(c, pid, "prequalification", oq["id"], "reject")
    g2 = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Never Qualified"}).json()
    assert g2["can_bid"] is False and "no approved prequalification" in g2["bid_blockers"], g2

    # --- PREQUAL-LAPSE: the state between "fine" and "blocked" --------------------------------
    # An approved prequalification lapsing in 10 days used to report `can_bid: True` with
    # `bid_blockers: []` and `prequal: {"status": "approved"}` -- nothing to say the approval dies
    # inside the fortnight, and the approval's own date is the only thing that ends it (the module
    # declares no transition out of `approved`). The verdict is deliberately UNCHANGED: a document
    # still valid today is not a blocker. What was missing was a way to say it.
    soon10 = (date.today() + timedelta(days=10)).isoformat()
    lq = _create(c, pid, "prequalification", {"company": "Lapsing Steel", "expires": soon10})
    _act(c, pid, "prequalification", lq["id"], "submit")
    _act(c, pid, "prequalification", lq["id"], "approve")
    lc = _create(c, pid, "coi", {"vendor": "Lapsing Steel", "expires": future,
                                 "gl_each_occurrence": 1_000_000})
    _act(c, pid, "coi", lc["id"], "approve")
    gl = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Lapsing Steel"}).json()
    assert gl["can_bid"] is True and gl["bid_blockers"] == [], gl
    assert gl["prequal"]["expiring_soon"] is True, gl["prequal"]
    assert gl["prequal"]["expires"] == soon10, gl["prequal"]
    assert any("prequalification lapses" in w for w in gl["bid_warnings"]), gl["bid_warnings"]
    assert gl["coi"]["expiring_soon"] is False, gl["coi"]
    # `expiring_soon` is on EVERY branch of the COI block, including `missing` -- an absent key is
    # falsy and reads as "not expiring soon" when the truth is "there is nothing to expire".
    gm = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Never Qualified"}).json()
    assert gm["coi"]["status"] == "missing" and gm["coi"]["expiring_soon"] is False, gm["coi"]
    # an ALREADY-lapsed approval is a blocker, not a warning: "expiring soon" is only ever said
    # about something currently valid, so the two states can never both fire for one document
    gx = c.get(f"/projects/{pid}/procurement/gate", params={"vendor": "Bedrock LLC"}).json()
    assert gx["can_bid"] is False and gx["prequal"]["expiring_soon"] is False, gx["prequal"]

    # `within_days` was accepted, clamped to 1..365 by its route, echoed, and used for NOTHING:
    # the windows were a literal 30 inside the COI branch, so a caller asking for 7 days got a
    # 30-day answer labelled 7. It now controls both registers' warning horizon.
    f7 = c.get(f"/projects/{pid}/procurement/compliance-feed", params={"within_days": 7}).json()
    f30 = c.get(f"/projects/{pid}/procurement/compliance-feed", params={"within_days": 30}).json()
    assert f7["warn_days"] == 7 and f30["warn_days"] == 30, (f7["warn_days"], f30["warn_days"])
    in7 = {v["vendor"] for v in f7["vendors"]}
    in30 = {v["vendor"] for v in f30["vendors"]}
    assert "Lapsing Steel" in in30, in30          # 10 days out, inside a 30-day window
    assert "Lapsing Steel" not in in7, in7        # ...and outside a 7-day one
    assert in7 < in30, (in7, in30)                # a narrower window is a strict subset
    # ...while a BLOCKER is reported whatever the window, because expired is expired
    assert "Bedrock LLC" in in7 and "Bedrock LLC" in in30, (in7, in30)
    lap = next(v for v in f30["vendors"] if v["vendor"] == "Lapsing Steel")
    assert any("prequal lapses" in i for i in lap["issues"]), lap

print("PROCUREMENT GATE OK - Acme fully compliant (can bid + bill, waiver on file); Bedrock blocked "
      "(expired COI + unapproved prequal); Crane COI expiring; feed nudges Bedrock+Crane, not Acme; a rejected-then-approved vendor can bid and a rejected-only vendor still cannot. "
      "PREQUAL-LAPSE: an approval lapsing in 10 days keeps can_bid True with empty blockers and "
      "raises a bid WARNING instead; `expiring_soon` is present on the missing-COI branch too; an "
      "already-lapsed approval is a blocker and never also 'expiring soon'; and `within_days` now "
      "moves the horizon -- a 7-day window is a strict subset of a 30-day one, while the expired "
      "blocker shows in both")
