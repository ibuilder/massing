"""Design-change instruments — ASI (G710), Bulletin, Sketch (SK), + CCD (G714) document.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_change_instruments.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_change_instruments.db"
os.environ["STORAGE_DIR"] = "./test_storage_change_instruments"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_change_instruments.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- ASI (G710): architect issues, contractor acknowledges, no cost/time ---
    asi = _create(c, pid, "asi", {"subject": "Ceiling height clarification",
        "instruction": "Set corridor ceiling to 2.7 m per attached SK-01.",
        "drawing_ref": "A-201", "cost_time_impact": "No cost or schedule impact (G710)"})
    assert asi["workflow_state"] == "issued", asi
    ack = c.post(f"/projects/{pid}/modules/asi/{asi['id']}/transition", json={"action": "acknowledge"})
    assert ack.status_code == 200 and ack.json()["workflow_state"] == "acknowledged", ack.text[:160]

    # --- Bulletin with cost impact -> linked to a change_event ---
    ce = _create(c, pid, "change_event", {"subject": "Added canopy"})
    bul = _create(c, pid, "bulletin", {"subject": "Entry canopy revision", "discipline": "Architectural",
        "description": "Add a steel-and-glass entry canopy per revised A-101.",
        "cost_time_impact": "Affects cost or schedule (route to change event)",
        "change_event": ce["id"], "drawings_affected": "A-101, S-101"})
    assert bul["data"]["change_event"] == ce["id"], "bulletin links to the change event"
    iss = c.post(f"/projects/{pid}/modules/bulletin/{bul['id']}/transition", json={"action": "issue"})
    assert iss.status_code == 200 and iss.json()["workflow_state"] == "issued", iss.text[:160]

    # --- Sketch (SK) attached to the ASI ---
    sk = _create(c, pid, "sketch", {"subject": "Corridor ceiling detail", "sk_number": "SK-01",
        "discipline": "Architectural", "asi": asi["id"]})
    assert sk["data"]["asi"] == asi["id"], "sketch attaches to the ASI"

    # --- CCD (G714) rendered from a directive record ---
    dir_ = _create(c, pid, "directive", {"subject": "Proceed with canopy", "scope": "Fabricate + install canopy",
        "mode": "Proceed & Pricing", "basis": "Time & Materials", "not_to_exceed": 85000})

    # --- documents render (%PDF) via the generic contract-document endpoint ---
    for key, rid, doc in [("asi", asi["id"], "asi"), ("bulletin", bul["id"], "bulletin"),
                          ("directive", dir_["id"], "ccd")]:
        pdf = c.get(f"/projects/{pid}/contracts/{key}/{rid}/document.pdf?doc={doc}")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", f"{doc}: {pdf.status_code}"
        assert len(pdf.content) > 1200, f"{doc} pdf too small ({len(pdf.content)})"

print("CHANGE INSTRUMENTS OK - ASI issue->acknowledge (G710, no cost); Bulletin w/ cost impact links a "
      "change_event + issues; Sketch (SK-01) attaches to the ASI; ASI/Bulletin/CCD(G714) render as PDFs")
