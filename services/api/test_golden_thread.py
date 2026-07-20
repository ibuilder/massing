"""GOLDEN-THREAD — the compliance evidence ledger rollup: every requirement traced to evidence + a
sign-off. Module registration + the summary engine (completeness %, outcome/category spread, and the
risk-ranked broken-thread list) + the /golden-thread route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_golden_thread.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_golden_thread.db"
os.environ["STORAGE_DIR"] = "./test_storage_goldenthread"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_golden_thread.db"):
    os.remove("./test_golden_thread.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import golden_thread  # noqa: E402
from aec_api import modules_registry as mr
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

mr.load_registry()
assert "compliance_evidence" in mr.REGISTRY and mr.REGISTRY["compliance_evidence"]["section"] == "Quality"


def _mk(c, pid, data):
    return c.post(f"/projects/{pid}/modules/compliance_evidence", json={"data": data}).json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Golden Thread"}).json()["id"]

    # a fully signed-off requirement (evidence attached → sign off)
    r1 = _mk(c, pid, {"requirement": "Egress width per IBC 1005", "category": "Egress", "outcome": "Pass",
                      "responsible": "AOR", "evidence_type": "Drawing", "evidence_ref": "A-101 rev C"})
    c.post(f"/projects/{pid}/modules/compliance_evidence/{r1['id']}/transition", json={"action": "attach_evidence"})
    s1 = c.post(f"/projects/{pid}/modules/compliance_evidence/{r1['id']}/transition", json={"action": "sign_off"})
    assert s1.json()["workflow_state"] == "signed_off", s1.text[:160]

    # an evidenced-but-not-signed requirement (medium risk once we look — actually has evidence → low)
    r2 = _mk(c, pid, {"requirement": "Fire rating of shaft", "category": "Fire Protection", "outcome": "Pass",
                      "evidence_type": "Document", "evidence_ref": "UL design X528"})
    c.post(f"/projects/{pid}/modules/compliance_evidence/{r2['id']}/transition", json={"action": "attach_evidence"})

    # a FAILED requirement with NO evidence → the highest-risk broken link
    _mk(c, pid, {"requirement": "Accessible route slope", "category": "Accessibility", "outcome": "Fail"})
    # a pending requirement, no evidence → high risk
    _mk(c, pid, {"requirement": "Energy envelope U-factor", "category": "Energy", "outcome": "Pending"})

    with SessionLocal() as db:
        g = golden_thread.summary(db, pid)

    assert g["total"] == 4, g
    assert g["signed_off"] == 1 and g["completeness_pct"] == 25.0, g          # 1 of 4 signed
    assert g["evidenced"] == 2, g                                            # r1 + r2 have evidence
    assert g["by_outcome"] == {"Pass": 2, "Fail": 1, "Pending": 1}, g["by_outcome"]
    assert g["broken_count"] == 3, g                                         # everything except r1
    # the highest-risk broken link (Fail/Pending, no evidence) sorts first
    top = g["broken_thread"][0]
    assert top["risk"] == "high" and top["outcome"] in ("Fail", "Pending") and not top["has_evidence"], top
    # exactly the two no-evidence items are high risk
    assert sum(1 for b in g["broken_thread"] if b["risk"] == "high") == 2, g["broken_thread"]

    # --- route ------------------------------------------------------------------------------------
    jr = c.get(f"/projects/{pid}/golden-thread")
    assert jr.status_code == 200, jr.status_code
    assert jr.json()["completeness_pct"] == 25.0 and jr.json()["broken_count"] == 3, jr.json()
    assert c.get("/projects/no-such/golden-thread").status_code == 404

print("GOLDEN-THREAD OK - the compliance_evidence ledger (Quality) registers; the summary rolls up 4 "
      "requirements — 1 signed off (25%% complete), 2 evidenced, outcome spread Pass2/Fail1/Pending1 — and "
      "the broken-thread list ranks the 3 unfinished links worst-first (the two Fail/Pending items with no "
      "evidence are high risk); the /golden-thread route returns the rollup and 404s on an unknown project.")
