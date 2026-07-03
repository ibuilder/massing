"""Design-phase spine (RIBA↔AIA) + itemized soft costs.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_design_phase.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_design_phase.db"
os.environ["STORAGE_DIR"] = "./test_storage_design_phase"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_design_phase.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import soft_costs                       # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- soft-cost itemization ---
it = soft_costs.itemize(1_000_000, 25.0)
assert abs(it["total"] - 250_000) <= len(it["lines"]), it["total"]     # sums to hard*25% (± rounding)
assert len(it["lines"]) == 9, it["lines"]
ae = next(x for x in it["lines"] if x["key"] == "architecture_engineering")
assert ae["amount"] == 70_000, ae                                      # 7% of hard
# A/E fee scheduled across the design phases, summing to the A/E fee
assert abs(sum(x["amount"] for x in it["ae_schedule"]) - it["ae_fee"]) <= len(it["ae_schedule"]), it["ae_schedule"]
cd = next(x for x in it["ae_schedule"] if x["phase"] == "CD")
assert cd["amount"] == round(70_000 * 0.35, 0), cd                     # CD gets the biggest slice
# a custom soft % scales the total (still itemized)
it30 = soft_costs.itemize(1_000_000, 30.0)
assert it30["total"] > it["total"], (it30["total"], it["total"])

# --- endpoints ---
with TestClient(app) as c:
    assert c.get("/lifecycle/reference").json()["phases"][2]["aia"] == "Schematic Design (SD)"
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # seed the 8 phases
    s = c.post(f"/projects/{pid}/lifecycle/seed")
    assert s.status_code == 200 and s.json()["phases"] == 8, s.text[:200]
    assert c.post(f"/projects/{pid}/lifecycle/seed").json()["seeded"] is False   # idempotent
    lc = c.get(f"/projects/{pid}/lifecycle").json()
    assert lc["count"] == 8 and lc["current_stage"]["aia_phase"].startswith("Pre-Design"), lc["current_stage"]
    # the SD phase (order 2) carries a 15% design fee
    sd = next(p for p in lc["phases"] if p["order"] == 2)
    assert float(sd["design_fee_pct"]) == 15.0, sd

    # --- gate: Architect+Owner approve (requires signed_by) ---
    ph_id = lc["phases"][0]["id"]
    # move to in_review
    tr = c.post(f"/projects/{pid}/modules/project_phase/{ph_id}/transition", json={"action": "submit_for_review"})
    assert tr.status_code == 200 and tr.json()["workflow_state"] == "in_review", tr.text[:200]
    # approve requires signed_by — set it, then approve
    c.patch(f"/projects/{pid}/modules/project_phase/{ph_id}", json={"signed_by": "A. Architect, AIA"})
    ap = c.post(f"/projects/{pid}/modules/project_phase/{ph_id}/transition", json={"action": "approve_gate"})
    assert ap.status_code == 200 and ap.json()["workflow_state"] == "approved", ap.text[:200]
    # after approving stage 0, current stage advances to stage 1 (Preparation & Briefing)
    lc2 = c.get(f"/projects/{pid}/lifecycle").json()
    assert lc2["current_stage"]["riba_stage"].startswith("1 "), lc2["current_stage"]

print("DESIGN PHASE OK - soft costs itemized (9 lines sum to 25%; A/E 7%, phase-split CD biggest); "
      "8 RIBA/AIA phases seeded (idempotent); gate submit->approve (Architect+Owner, requires signed_by); "
      "current stage advances after gate")
